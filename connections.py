"""
Conexões independentes e somente leitura com os seis bancos do SafraTech
(três agronômicos e três de pecuária de corte).

As URLs vêm de variáveis de ambiente (ou de um dicionário de segredos repassado pelo app):
    SOLO_DATABASE_URL, NUTRICAO_DATABASE_URL, PLANTIO_DATABASE_URL
    PECUARIA_COMPRA_DATABASE_URL, PECUARIA_DESEMPENHO_DATABASE_URL, PECUARIA_RENTABILIDADE_DATABASE_URL
Exemplo:  postgresql+psycopg://usuario:senha@localhost:5432/solo_database

Regras de segurança:
- toda sessão é aberta com `default_transaction_read_only=on` (o app nunca altera os bancos);
- `statement_timeout` limita consultas longas;
- consultas são sempre parametrizadas (SQLAlchemy `text()` + parâmetros nomeados `:nome`);
- a falha de um banco não afeta os outros (cada um tem seu próprio engine e status).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

import pandas as pd

BANCOS = {
    # agricultura
    "solo": {"env": "SOLO_DATABASE_URL", "nome": "solo_database", "tabela_teste": "solo.registro", "area": "agricultura"},
    "nutricao": {"env": "NUTRICAO_DATABASE_URL", "nome": "nutricao_database", "tabela_teste": "nutricao.registro",
                 "area": "agricultura"},
    "plantio": {"env": "PLANTIO_DATABASE_URL", "nome": "plantio_database", "tabela_teste": "plantio.zarc_indicacao",
                "area": "agricultura"},
    # pecuária de corte (tabelas no esquema public)
    "pecuaria_compra": {"env": "PECUARIA_COMPRA_DATABASE_URL", "nome": "pecuaria_compra_database",
                        "tabela_teste": "public.parametro_tecnico", "area": "pecuaria"},
    "pecuaria_desempenho": {"env": "PECUARIA_DESEMPENHO_DATABASE_URL", "nome": "pecuaria_desempenho_database",
                            "tabela_teste": "public.parametro_tecnico", "area": "pecuaria"},
    "pecuaria_rentabilidade": {"env": "PECUARIA_RENTABILIDADE_DATABASE_URL", "nome": "pecuaria_rentabilidade_database",
                               "tabela_teste": "public.parametro_tecnico", "area": "pecuaria"},
}

STATEMENT_TIMEOUT_MS = int(os.environ.get("SAFRATECH_STATEMENT_TIMEOUT_MS", "20000"))


class BancoIndisponivel(RuntimeError):
    """Banco sem URL configurada, driver ausente ou servidor inacessível."""


@dataclass
class StatusBanco:
    chave: str
    disponivel: bool
    mensagem: str


_segredos: dict[str, str] = {}
_engines: dict[str, Any] = {}
_lock = threading.Lock()

# Executor alternativo (usado apenas pelos testes automatizados para rodar o mesmo SQL sem driver Python).
_executor_externo: Optional[Callable[[str, str, Mapping[str, Any]], pd.DataFrame]] = None


def configurar_segredos(segredos: Optional[Mapping[str, Any]]) -> None:
    """Recebe, opcionalmente, URLs vindas de `st.secrets` (nunca gravadas em código)."""
    if segredos:
        for cfg in BANCOS.values():
            v = segredos.get(cfg["env"])
            if v:
                _segredos[cfg["env"]] = str(v)


def definir_executor_externo(func: Optional[Callable[[str, str, Mapping[str, Any]], pd.DataFrame]]) -> None:
    global _executor_externo
    _executor_externo = func


def obter_url(chave: str) -> Optional[str]:
    env = BANCOS[chave]["env"]
    url = os.environ.get(env) or _segredos.get(env)
    if not url:
        return None
    # aceita postgresql://... e escolhe o driver instalado
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        try:
            import psycopg  # noqa: F401
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        except ImportError:
            try:
                import psycopg2  # noqa: F401
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            except ImportError:
                pass
    return url


def _url_sem_senha(url: str) -> str:
    try:
        from sqlalchemy.engine import make_url
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url.split("@")[-1]


def obter_engine(chave: str):
    """Engine SQLAlchemy reutilizável (pool) para um banco. Criado uma única vez por processo."""
    if chave not in BANCOS:
        raise KeyError(chave)
    with _lock:
        if chave in _engines:
            return _engines[chave]
        url = obter_url(chave)
        if not url:
            raise BancoIndisponivel(f"Variável de ambiente {BANCOS[chave]['env']} não configurada.")
        try:
            from sqlalchemy import create_engine
        except ImportError as e:  # pragma: no cover
            raise BancoIndisponivel("Biblioteca SQLAlchemy não instalada (pip install -r requirements.txt).") from e
        opcoes = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
        try:
            engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=1800,
                                   connect_args={"connect_timeout": 5, "options": opcoes,
                                                 "application_name": "safratech_streamlit"})
        except Exception as e:
            raise BancoIndisponivel(f"URL inválida para {BANCOS[chave]['env']}: {e}") from e
        _engines[chave] = engine
        return engine


def consultar(chave: str, sql: str, params: Optional[Mapping[str, Any]] = None) -> pd.DataFrame:
    """Executa SELECT parametrizado e devolve DataFrame. A conexão é devolvida ao pool ao final."""
    params = dict(params or {})
    if _executor_externo is not None:
        return _executor_externo(chave, sql, params)
    engine = obter_engine(chave)
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql), params)
            linhas = res.fetchall()
            return pd.DataFrame(linhas, columns=list(res.keys()))
    except BancoIndisponivel:
        raise
    except Exception as e:
        raise BancoIndisponivel(f"Erro ao consultar {BANCOS[chave]['nome']}: {type(e).__name__}: {str(e).splitlines()[0]}") from e


def verificar(chave: str) -> StatusBanco:
    """Testa acesso ao banco e à tabela principal esperada. Nunca levanta exceção."""
    cfg = BANCOS[chave]
    try:
        df = consultar(chave, f"SELECT current_database() AS banco, EXISTS (SELECT 1 FROM {cfg['tabela_teste']} LIMIT 1) AS tem_dados")
        return StatusBanco(chave, True, f"{df.iloc[0]['banco']} — conectado")
    except BancoIndisponivel as e:
        return StatusBanco(chave, False, str(e))
    except Exception as e:  # pragma: no cover
        return StatusBanco(chave, False, f"{type(e).__name__}: {e}")


def descricao_conexao(chave: str) -> str:
    url = obter_url(chave)
    return _url_sem_senha(url) if url else "não configurada"


def descartar_engines() -> None:
    with _lock:
        for e in _engines.values():
            try:
                e.dispose()
            except Exception:
                pass
        _engines.clear()
