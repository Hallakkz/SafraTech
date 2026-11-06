"""
Busca na internet (Tavily) — usada pelo Tutor Agro SOMENTE quando a pergunta não encontra referências nos bancos do
SafraTech nem na Biblioteca.

Configuração (somente .env / variáveis de ambiente / st.secrets — nunca no código):
    TAVILY_API_KEY        chave da API (sem ela, a busca na internet fica desativada)
Opcionais:
    TAVILY_MAX_RESULTADOS número de páginas por busca (padrão 5)
    TAVILY_MAX_REQ_MIN    limite local de buscas por minuto (padrão 15)
    EDUAGRO_BUSCA_INTERNET  "0" desliga a busca na internet mesmo com a chave configurada

A chamada é feita pelo backend Python; a chave nunca vai ao navegador nem aparece em mensagens de erro.
O conteúdo das páginas é tratado como DADO não verificado (nunca como instrução) e é sempre exibido separado dos bancos.
Cada busca básica consome 1 crédito do plano Tavily.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from modules.eduagro_ai.deepseek_client import LimitadorRequisicoes

URL_BUSCA = "https://api.tavily.com/search"
ENV_CHAVE = "TAVILY_API_KEY"
_segredos: dict[str, str] = {}


class ErroBusca(RuntimeError):
    codigo = "erro_busca"
    mensagem_padrao = "A busca na internet está indisponível no momento."

    def __init__(self, mensagem_usuario: Optional[str] = None, detalhe: str = "", status_http: Optional[int] = None):
        self.mensagem_usuario = mensagem_usuario or self.mensagem_padrao
        self.detalhe = detalhe
        self.status_http = status_http
        super().__init__(f"{self.mensagem_usuario} {('(' + detalhe + ')') if detalhe else ''}".strip())


class BuscaNaoConfigurada(ErroBusca):
    codigo = "nao_configurada"
    mensagem_padrao = "A busca na internet não está configurada (defina TAVILY_API_KEY no .env)."


class BuscaChaveInvalida(ErroBusca):
    codigo = "chave_invalida"
    mensagem_padrao = "A chave do Tavily foi recusada (inválida ou expirada). Verifique TAVILY_API_KEY no .env."


class BuscaCotaEsgotada(ErroBusca):
    codigo = "cota_esgotada"
    mensagem_padrao = "A cota de buscas do Tavily acabou (limite do plano). As buscas na internet voltam quando a cota renovar."


class BuscaLimite(ErroBusca):
    codigo = "limite_requisicoes"
    mensagem_padrao = "Muitas buscas na internet em pouco tempo. Aguarde alguns segundos."


class BuscaIndisponivel(ErroBusca):
    codigo = "indisponivel"
    mensagem_padrao = "O serviço de busca na internet (Tavily) está indisponível ou não respondeu."


def configurar_segredos(segredos: Optional[Mapping[str, Any]]) -> None:
    if not segredos:
        return
    for nome in (ENV_CHAVE, "TAVILY_MAX_RESULTADOS", "TAVILY_MAX_REQ_MIN", "EDUAGRO_BUSCA_INTERNET"):
        try:
            v = segredos.get(nome)
        except Exception:
            v = None
        if v:
            _segredos[nome] = str(v)


def _ler(nome: str, padrao: str = "") -> str:
    return (os.environ.get(nome) or _segredos.get(nome) or padrao).strip()


@dataclass(frozen=True)
class ConfigBusca:
    api_key: str = field(repr=False)
    max_resultados: int = 5
    max_req_min: int = 15
    ativada: bool = True

    @property
    def disponivel(self) -> bool:
        return bool(self.api_key) and self.ativada

    def descricao(self) -> str:
        if not self.ativada:
            return "busca na internet desligada (EDUAGRO_BUSCA_INTERNET=0)"
        return f"Tavily · chave {'carregada' if self.api_key else 'NÃO configurada'} · até {self.max_resultados} páginas por busca"


def carregar_config() -> ConfigBusca:
    def inteiro(nome, padrao):
        try:
            return int(float(_ler(nome, str(padrao))))
        except ValueError:
            return padrao
    return ConfigBusca(api_key=_ler(ENV_CHAVE), max_resultados=max(1, min(10, inteiro("TAVILY_MAX_RESULTADOS", 5))),
                       max_req_min=max(1, inteiro("TAVILY_MAX_REQ_MIN", 15)),
                       ativada=_ler("EDUAGRO_BUSCA_INTERNET", "1") not in ("0", "nao", "não", "false"))


@dataclass
class ResultadoWeb:
    titulo: str
    url: str
    conteudo: str
    pontuacao: float = 0.0

    @property
    def site(self) -> str:
        try:
            return urlparse(self.url).netloc.replace("www.", "")
        except Exception:
            return ""


class ClienteBusca:
    TENTATIVAS = 2

    def __init__(self, config: Optional[ConfigBusca] = None, sessao=None, limitador: Optional[LimitadorRequisicoes] = None,
                 dormir=time.sleep):
        self.config = config or carregar_config()
        if sessao is None:
            if requests is None:  # pragma: no cover
                raise BuscaNaoConfigurada("A biblioteca 'requests' não está instalada.")
            sessao = requests.Session()
        self._sessao = sessao
        self._limitador = limitador or LimitadorRequisicoes(self.config.max_req_min)
        self._dormir = dormir

    @property
    def disponivel(self) -> bool:
        return self.config.disponivel

    def _ocultar(self, t: str) -> str:
        t = str(t or "")
        if self.config.api_key:
            t = t.replace(self.config.api_key, "***")
        return t[:300]

    def _erro(self, resp) -> ErroBusca:
        st = resp.status_code
        try:
            corpo = resp.json()
            msg = corpo.get("detail") or corpo.get("error") or corpo
        except Exception:
            msg = getattr(resp, "text", "")
        detalhe = self._ocultar(f"HTTP {st}: {msg}")
        if st == 401:
            return BuscaChaveInvalida(detalhe=detalhe, status_http=st)
        if st in (432, 433):
            return BuscaCotaEsgotada(detalhe=detalhe, status_http=st)
        if st == 429:
            return BuscaLimite(detalhe=detalhe, status_http=st)
        if st >= 500:
            return BuscaIndisponivel(detalhe=detalhe, status_http=st)
        return ErroBusca(f"A busca na internet recusou a consulta (HTTP {st}).", detalhe=detalhe, status_http=st)

    def buscar(self, consulta: str) -> list[ResultadoWeb]:
        if not self.config.api_key:
            raise BuscaNaoConfigurada()
        consulta = " ".join(str(consulta or "").split())[:380]
        if not consulta:
            return []
        try:
            self._limitador.reservar()
        except Exception as e:
            raise BuscaLimite(detalhe=str(e)) from e
        corpo = {"api_key": self.config.api_key, "query": consulta, "search_depth": "basic",
                 "max_results": self.config.max_resultados, "include_answer": False, "include_raw_content": False,
                 "include_images": False}
        cab = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        ultimo: Optional[ErroBusca] = None
        for tentativa in range(self.TENTATIVAS):
            try:
                resp = self._sessao.request("POST", URL_BUSCA, headers=cab, json=corpo, stream=False, timeout=(10, 30))
            except Exception as e:
                ultimo = BuscaIndisponivel(detalhe=self._ocultar(f"{type(e).__name__}: {e}"))
            else:
                if 200 <= resp.status_code < 300:
                    try:
                        dados = resp.json()
                    except Exception as e:
                        raise BuscaIndisponivel("A busca na internet respondeu em formato inesperado.",
                                                detalhe=self._ocultar(str(e))) from e
                    out = []
                    for r in dados.get("results") or []:
                        url = str(r.get("url") or "")
                        if not url.startswith(("http://", "https://")):
                            continue
                        out.append(ResultadoWeb(str(r.get("title") or url)[:200], url, str(r.get("content") or "")[:2500],
                                                float(r.get("score") or 0)))
                    return out
                ultimo = self._erro(resp)
            if not isinstance(ultimo, (BuscaIndisponivel, BuscaLimite)) or tentativa == self.TENTATIVAS - 1:
                raise ultimo
            self._dormir(1.5)
        raise ultimo or BuscaIndisponivel()  # pragma: no cover


_clientes: dict[tuple, ClienteBusca] = {}
_lock = threading.Lock()


def obter_cliente() -> ClienteBusca:
    cfg = carregar_config()
    chave = (cfg.api_key, cfg.max_resultados, cfg.max_req_min, cfg.ativada)
    with _lock:
        if chave not in _clientes:
            _clientes.clear()
            _clientes[chave] = ClienteBusca(cfg)
        return _clientes[chave]
