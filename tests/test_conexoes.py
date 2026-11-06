"""Conexões, configuração por variáveis de ambiente e salvaguardas de somente leitura."""
import re
from pathlib import Path

import pandas as pd
import pytest

from database import connections
from database.connections import BancoIndisponivel

RAIZ = Path(__file__).resolve().parent.parent


def test_url_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("SOLO_DATABASE_URL", "postgresql://u:segredo@h:5432/solo_database")
    url = connections.obter_url("solo")
    assert url.endswith("u:segredo@h:5432/solo_database")
    assert "segredo" not in connections.descricao_conexao("solo")


def test_sem_url_banco_indisponivel_sem_excecao(monkeypatch):
    connections.definir_executor_externo(None)
    connections.descartar_engines()
    for cfg in connections.BANCOS.values():
        monkeypatch.delenv(cfg["env"], raising=False)
    monkeypatch.setattr(connections, "_segredos", {})
    st = connections.verificar("solo")
    assert st.disponivel is False and "SOLO_DATABASE_URL" in st.mensagem
    with pytest.raises(BancoIndisponivel):
        connections.consultar("plantio", "SELECT 1")


def test_falha_de_um_banco_nao_afeta_os_outros():
    def executor(chave, sql, params):
        if chave == "nutricao":
            raise BancoIndisponivel("servidor fora do ar")
        return pd.DataFrame([{"banco": f"{chave}_database", "tem_dados": True}])
    connections.definir_executor_externo(executor)
    try:
        status = {s.chave: s.disponivel for s in (connections.verificar(k) for k in connections.BANCOS)}
    finally:
        connections.definir_executor_externo(None)
    assert status == {"solo": True, "nutricao": False, "plantio": True, "pecuaria_compra": True, "pecuaria_desempenho": True,
                      "pecuaria_rentabilidade": True}


def test_seis_bancos_com_variaveis_de_ambiente_pedidas():
    envs = {k: v["env"] for k, v in connections.BANCOS.items()}
    assert envs == {"solo": "SOLO_DATABASE_URL", "nutricao": "NUTRICAO_DATABASE_URL", "plantio": "PLANTIO_DATABASE_URL",
                    "pecuaria_compra": "PECUARIA_COMPRA_DATABASE_URL",
                    "pecuaria_desempenho": "PECUARIA_DESEMPENHO_DATABASE_URL",
                    "pecuaria_rentabilidade": "PECUARIA_RENTABILIDADE_DATABASE_URL"}
    assert {v["nome"] for v in connections.BANCOS.values()} >= {"pecuaria_compra_database", "pecuaria_desempenho_database",
                                                               "pecuaria_rentabilidade_database"}
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for env in envs.values():
        assert f"{env}=" in exemplo


def test_url_pecuaria_vem_do_ambiente_ou_segredos(monkeypatch):
    monkeypatch.delenv("PECUARIA_COMPRA_DATABASE_URL", raising=False)
    monkeypatch.setattr(connections, "_segredos", {})
    connections.configurar_segredos({"PECUARIA_COMPRA_DATABASE_URL": "postgresql://u:s@h:5432/pecuaria_compra_database"})
    assert connections.obter_url("pecuaria_compra").endswith("@h:5432/pecuaria_compra_database")
    assert "s@" not in connections.descricao_conexao("pecuaria_compra")


def test_sem_url_de_um_banco_pecuario_so_ele_fica_indisponivel(monkeypatch):
    connections.definir_executor_externo(None)
    connections.descartar_engines()
    monkeypatch.delenv("PECUARIA_RENTABILIDADE_DATABASE_URL", raising=False)
    monkeypatch.setattr(connections, "_segredos", {})
    st = connections.verificar("pecuaria_rentabilidade")
    assert st.disponivel is False and "PECUARIA_RENTABILIDADE_DATABASE_URL" in st.mensagem


def test_conexao_real_aos_seis_bancos(bancos):
    for chave in bancos.BANCOS:
        s = bancos.verificar(chave)
        assert s.disponivel, s.mensagem
        assert bancos.BANCOS[chave]["nome"] in s.mensagem


def test_sessao_somente_leitura_e_timeout_configurados():
    fonte = (RAIZ / "database" / "connections.py").read_text(encoding="utf-8")
    assert "default_transaction_read_only=on" in fonte
    assert "statement_timeout" in fonte
    assert "pool_pre_ping=True" in fonte


ARQS_APP = [p for p in RAIZ.rglob("*.py") if "tests" not in p.parts
            and not any(x.lower().replace("_", " ").startswith("banco de dados") for x in p.parts)]


def test_nenhuma_senha_no_codigo():
    padrao = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s\"']+:[^@\s\"']+@", re.IGNORECASE)
    achados = [str(p) for p in ARQS_APP if padrao.search(p.read_text(encoding="utf-8")) and "Exemplo:" not in p.read_text(encoding="utf-8")]
    assert not achados, achados
    # o único exemplo de URL é um texto de documentação com placeholders
    doc = (RAIZ / "database" / "connections.py").read_text(encoding="utf-8")
    assert "usuario:senha@localhost" in doc


def test_sql_do_app_nao_altera_bancos_nem_faz_select_estrela():
    proibido = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|COPY)\b\s", re.IGNORECASE)
    for p in (RAIZ / "database").glob("*_queries.py"):
        texto = p.read_text(encoding="utf-8")
        sqls = re.findall(r'"""(.*?)"""', texto, re.S)
        for s in sqls:
            if "SELECT" not in s.upper():
                continue
            assert not proibido.search(s), (p.name, s[:80])
            assert not re.search(r"SELECT\s+\*", s, re.IGNORECASE), (p.name, s[:80])


def test_zarc_sempre_filtrado_no_postgresql():
    texto = (RAIZ / "database" / "plantio_queries.py").read_text(encoding="utf-8")
    blocos = [b for b in re.findall(r'(?:f?""")(.*?)"""', texto, re.S) if "zarc_indicacao" in b]
    assert blocos
    for b in blocos:
        assert re.search(r"geocodigo\s*=\s*:g", b), b[:120]
