"""
Camada de comunicação com a API da DeepSeek (independente da interface).

Configuração (somente por variáveis de ambiente ou st.secrets — nunca no código):
    DEEPSEEK_API_KEY      chave da API (obrigatória)
    DEEPSEEK_BASE_URL     padrão https://api.deepseek.com
    DEEPSEEK_MODEL        padrão deepseek-chat
Opcionais:
    DEEPSEEK_TIMEOUT_S        tempo máximo de cada requisição (padrão 90)
    DEEPSEEK_MAX_REQ_MIN      limite local de requisições por minuto (padrão 20)
    DEEPSEEK_MAX_TOKENS       limite de tokens de cada resposta (padrão 4000)

Regras:
- a chamada é feita somente pelo backend Python; a chave nunca é enviada ao navegador nem gravada em log;
- os erros da API viram exceções `ErroIA` com mensagem em português para o usuário
  (chave inválida, sem saldo, limite de requisições, servidor indisponível, tempo esgotado...);
- não existe modo simulado: se a API não responder, a interface informa que a IA está indisponível.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests acompanha o Streamlit
    requests = None  # type: ignore

ENV_CHAVE = "DEEPSEEK_API_KEY"
ENV_URL = "DEEPSEEK_BASE_URL"
ENV_MODELO = "DEEPSEEK_MODEL"
URL_PADRAO = "https://api.deepseek.com"
MODELO_PADRAO = "deepseek-chat"

_segredos: dict[str, str] = {}


# =====================================================================================================
# Erros
# =====================================================================================================
class ErroIA(RuntimeError):
    """Falha ao usar a IA. `mensagem_usuario` é o texto exibido na interface (português)."""

    codigo = "erro_ia"
    mensagem_padrao = "A inteligência artificial está indisponível no momento."

    def __init__(self, mensagem_usuario: Optional[str] = None, detalhe: str = "", status_http: Optional[int] = None):
        self.mensagem_usuario = mensagem_usuario or self.mensagem_padrao
        self.detalhe = detalhe
        self.status_http = status_http
        super().__init__(f"{self.mensagem_usuario} {('(' + detalhe + ')') if detalhe else ''}".strip())


class IANaoConfigurada(ErroIA):
    codigo = "nao_configurada"
    mensagem_padrao = ("A IA não está configurada: defina DEEPSEEK_API_KEY no arquivo .env (veja .env.example) "
                       "e reinicie o aplicativo.")


class IAChaveInvalida(ErroIA):
    codigo = "chave_invalida"
    mensagem_padrao = "A chave da API DeepSeek foi recusada (chave inválida ou revogada). Verifique DEEPSEEK_API_KEY no .env."


class IASemSaldo(ErroIA):
    codigo = "sem_saldo"
    mensagem_padrao = ("A conta DeepSeek está sem saldo. Recarregue os créditos em platform.deepseek.com para voltar "
                       "a usar o tutor.")


class IALimiteRequisicoes(ErroIA):
    codigo = "limite_requisicoes"
    mensagem_padrao = "Muitas requisições em pouco tempo. Aguarde alguns segundos e tente novamente."

    def __init__(self, mensagem_usuario: Optional[str] = None, detalhe: str = "", status_http: Optional[int] = None,
                 espera_s: float = 0.0):
        super().__init__(mensagem_usuario, detalhe, status_http)
        self.espera_s = espera_s


class IAIndisponivel(ErroIA):
    codigo = "indisponivel"
    mensagem_padrao = ("O serviço da DeepSeek está indisponível ou sobrecarregado no momento. Tente novamente em "
                       "alguns minutos.")


class IATempoEsgotado(ErroIA):
    codigo = "tempo_esgotado"
    mensagem_padrao = "A DeepSeek demorou demais para responder. Tente novamente (ou faça uma pergunta mais curta)."


class IASemConexao(ErroIA):
    codigo = "sem_conexao"
    mensagem_padrao = "Não foi possível conectar à DeepSeek. Verifique a conexão com a internet e DEEPSEEK_BASE_URL."


class IARequisicaoInvalida(ErroIA):
    codigo = "requisicao_invalida"
    mensagem_padrao = "A DeepSeek recusou a requisição (formato ou parâmetros inválidos, ou modelo inexistente)."


class IARespostaInvalida(ErroIA):
    codigo = "resposta_invalida"
    mensagem_padrao = "A DeepSeek respondeu em um formato inesperado. Tente novamente."


# =====================================================================================================
# Configuração
# =====================================================================================================
@dataclass(frozen=True)
class ConfigDeepSeek:
    api_key: str = field(repr=False)
    base_url: str = URL_PADRAO
    modelo: str = MODELO_PADRAO
    timeout_s: float = 90.0
    max_req_min: int = 20
    max_tokens: int = 4000

    @property
    def configurada(self) -> bool:
        return bool(self.api_key)

    def descricao(self) -> str:
        """Descrição segura (sem a chave) para a interface e diagnósticos."""
        chave = f"carregada ({len(self.api_key)} caracteres)" if self.api_key else "NÃO configurada"
        return f"modelo {self.modelo} · {self.base_url} · chave {chave}"


def configurar_segredos(segredos: Optional[Mapping[str, Any]]) -> None:
    """Aceita as variáveis vindas de st.secrets (opcional). Variáveis de ambiente têm prioridade."""
    if not segredos:
        return
    for nome in (ENV_CHAVE, ENV_URL, ENV_MODELO, "DEEPSEEK_TIMEOUT_S", "DEEPSEEK_MAX_REQ_MIN", "DEEPSEEK_MAX_TOKENS"):
        try:
            v = segredos.get(nome)
        except Exception:
            v = None
        if v:
            _segredos[nome] = str(v)


def _ler(nome: str, padrao: str = "") -> str:
    return (os.environ.get(nome) or _segredos.get(nome) or padrao).strip()


def _num(nome: str, padrao: float) -> float:
    try:
        return float(_ler(nome, str(padrao)))
    except ValueError:
        return padrao


def carregar_config() -> ConfigDeepSeek:
    return ConfigDeepSeek(
        api_key=_ler(ENV_CHAVE),
        base_url=(_ler(ENV_URL, URL_PADRAO) or URL_PADRAO).rstrip("/"),
        modelo=_ler(ENV_MODELO, MODELO_PADRAO) or MODELO_PADRAO,
        timeout_s=max(5.0, _num("DEEPSEEK_TIMEOUT_S", 90.0)),
        max_req_min=max(1, int(_num("DEEPSEEK_MAX_REQ_MIN", 20))),
        max_tokens=max(256, int(_num("DEEPSEEK_MAX_TOKENS", 4000))),
    )


# =====================================================================================================
# Limite local de requisições (janela deslizante de 60 s, compartilhada pelo processo)
# =====================================================================================================
class LimitadorRequisicoes:
    def __init__(self, maximo_por_minuto: int, relogio=time.monotonic):
        self.maximo = maximo_por_minuto
        self._relogio = relogio
        self._marcas: deque[float] = deque()
        self._lock = threading.Lock()

    def reservar(self) -> None:
        """Registra uma requisição ou levanta IALimiteRequisicoes informando quanto esperar."""
        with self._lock:
            agora = self._relogio()
            while self._marcas and agora - self._marcas[0] >= 60:
                self._marcas.popleft()
            if len(self._marcas) >= self.maximo:
                espera = max(1.0, 60 - (agora - self._marcas[0]))
                raise IALimiteRequisicoes(
                    f"Limite de {self.maximo} perguntas por minuto atingido. Aguarde cerca de {espera:.0f} s e tente novamente.",
                    detalhe="limite local", espera_s=espera)
            self._marcas.append(agora)


# =====================================================================================================
# Respostas
# =====================================================================================================
@dataclass
class RespostaIA:
    texto: str
    modelo: str = ""
    motivo_fim: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0
    duracao_s: float = 0.0

    @property
    def truncada(self) -> bool:
        return self.motivo_fim == "length"


@dataclass
class StatusIA:
    disponivel: bool
    mensagem: str
    codigo: str = "ok"
    saldo: Optional[str] = None
    modelo: str = ""
    detalhes: dict = field(default_factory=dict)


# =====================================================================================================
# Cliente
# =====================================================================================================
class ClienteDeepSeek:
    """Cliente HTTP da API DeepSeek (compatível com o formato OpenAI de chat completions)."""

    TENTATIVAS = 3              # 1 + 2 novas tentativas para 429/500/503/rede
    ESPERA_BASE_S = 1.5

    def __init__(self, config: Optional[ConfigDeepSeek] = None, sessao=None, limitador: Optional[LimitadorRequisicoes] = None,
                 dormir=time.sleep):
        self.config = config or carregar_config()
        if sessao is None:
            if requests is None:  # pragma: no cover
                raise IANaoConfigurada("A biblioteca 'requests' não está instalada (pip install -r requirements.txt).")
            sessao = requests.Session()
        self._sessao = sessao
        self._limitador = limitador or LimitadorRequisicoes(self.config.max_req_min)
        self._dormir = dormir
        self.ultima_resposta: Optional[RespostaIA] = None

    # ------------------------------------------------------------------ utilidades
    @property
    def configurado(self) -> bool:
        return self.config.configurada

    def _cabecalhos(self) -> dict:
        if not self.config.api_key:
            raise IANaoConfigurada()
        return {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json",
                "Accept": "application/json"}

    def _ocultar(self, texto: str) -> str:
        """Remove a chave de qualquer texto (mensagens de erro nunca exibem a chave)."""
        t = str(texto or "")
        if self.config.api_key:
            t = t.replace(self.config.api_key, "***")
        return t[:300]

    @staticmethod
    def _mensagem_api(resp) -> str:
        try:
            dados = resp.json()
            if isinstance(dados, dict):
                err = dados.get("error")
                if isinstance(err, dict):
                    return str(err.get("message") or err)
                if err:
                    return str(err)
                return str(dados.get("message") or dados)[:300]
        except Exception:
            pass
        return (getattr(resp, "text", "") or "")[:300]

    def _erro_http(self, resp) -> ErroIA:
        status = resp.status_code
        detalhe = self._ocultar(f"HTTP {status}: {self._mensagem_api(resp)}")
        if status == 401:
            return IAChaveInvalida(detalhe=detalhe, status_http=status)
        if status == 402:
            return IASemSaldo(detalhe=detalhe, status_http=status)
        if status == 429:
            try:
                espera = float(resp.headers.get("Retry-After", "0") or 0)
            except (TypeError, ValueError):
                espera = 0.0
            return IALimiteRequisicoes(
                "A DeepSeek limitou a frequência de requisições desta conta. Aguarde alguns segundos e tente novamente.",
                detalhe=detalhe, status_http=status, espera_s=espera)
        if status in (400, 404, 422):
            return IARequisicaoInvalida(detalhe=detalhe, status_http=status)
        if status in (500, 502, 503, 504):
            return IAIndisponivel(detalhe=detalhe, status_http=status)
        return ErroIA(f"A DeepSeek retornou um erro inesperado (HTTP {status}).", detalhe=detalhe, status_http=status)

    @staticmethod
    def _recuperavel(e: ErroIA) -> bool:
        return isinstance(e, (IAIndisponivel, IASemConexao, IATempoEsgotado)) or (
            isinstance(e, IALimiteRequisicoes) and e.detalhe != "limite local")

    def _enviar(self, metodo: str, caminho: str, corpo: Optional[dict] = None, stream: bool = False, timeout=None):
        """Requisição com novas tentativas (backoff) para falhas temporárias. Retorna o objeto de resposta."""
        url = f"{self.config.base_url}{caminho}"
        cab = self._cabecalhos()
        ultimo: Optional[ErroIA] = None
        for tentativa in range(self.TENTATIVAS):
            try:
                resp = self._sessao.request(metodo, url, headers=cab, json=corpo, stream=stream,
                                            timeout=timeout or (10, self.config.timeout_s))
            except Exception as e:  # erros de rede do requests (ou de uma sessão de teste)
                nome = type(e).__name__
                if "Timeout" in nome:
                    ultimo = IATempoEsgotado(detalhe=self._ocultar(nome))
                else:
                    ultimo = IASemConexao(detalhe=self._ocultar(f"{nome}: {e}"))
            else:
                if 200 <= resp.status_code < 300:
                    return resp
                ultimo = self._erro_http(resp)
                try:
                    resp.close()
                except Exception:
                    pass
            if not self._recuperavel(ultimo) or tentativa == self.TENTATIVAS - 1:
                raise ultimo
            espera = getattr(ultimo, "espera_s", 0) or self.ESPERA_BASE_S * (2 ** tentativa)
            self._dormir(min(espera, 10.0))
        raise ultimo or IAIndisponivel()  # pragma: no cover

    def _corpo(self, mensagens: list[dict], temperatura: float, max_tokens: Optional[int], json_saida: bool,
               stream: bool) -> dict:
        if not mensagens:
            raise IARequisicaoInvalida("Nenhuma mensagem para enviar à IA.")
        corpo = {"model": self.config.modelo, "messages": mensagens, "temperature": float(temperatura),
                 "max_tokens": int(max_tokens or self.config.max_tokens), "stream": stream}
        if json_saida:
            corpo["response_format"] = {"type": "json_object"}
        return corpo

    # ------------------------------------------------------------------ chamadas
    def conversar(self, mensagens: list[dict], temperatura: float = 0.3, max_tokens: Optional[int] = None,
                  json_saida: bool = False) -> RespostaIA:
        """Chamada completa (sem streaming)."""
        self._limitador.reservar()
        inicio = time.monotonic()
        resp = self._enviar("POST", "/chat/completions", self._corpo(mensagens, temperatura, max_tokens, json_saida, False))
        try:
            dados = resp.json()
            escolha = dados["choices"][0]
            texto = escolha["message"].get("content") or ""
        except Exception as e:
            raise IARespostaInvalida(detalhe=self._ocultar(f"{type(e).__name__}: {e}")) from e
        uso = dados.get("usage") or {}
        r = RespostaIA(texto=texto, modelo=dados.get("model", self.config.modelo), motivo_fim=escolha.get("finish_reason") or "",
                       tokens_entrada=int(uso.get("prompt_tokens") or 0), tokens_saida=int(uso.get("completion_tokens") or 0),
                       duracao_s=time.monotonic() - inicio)
        if not texto.strip():
            raise IARespostaInvalida("A DeepSeek retornou uma resposta vazia. Tente novamente.")
        self.ultima_resposta = r
        return r

    def conversar_json(self, mensagens: list[dict], temperatura: float = 0.2, max_tokens: Optional[int] = None) -> dict:
        """Chamada em modo JSON. Levanta IARespostaInvalida se o conteúdo não for um objeto JSON."""
        r = self.conversar(mensagens, temperatura=temperatura, max_tokens=max_tokens, json_saida=True)
        texto = r.texto.strip()
        if texto.startswith("```"):
            texto = texto.strip("`")
            texto = texto[texto.find("{"):]
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as e:
            raise IARespostaInvalida("A IA não devolveu um JSON válido. Tente gerar novamente.", detalhe=str(e)) from e
        if not isinstance(dados, dict):
            raise IARespostaInvalida("A IA não devolveu um objeto JSON. Tente gerar novamente.")
        return dados

    def conversar_stream(self, mensagens: list[dict], temperatura: float = 0.3, max_tokens: Optional[int] = None) -> Iterator[str]:
        """Gera os pedaços de texto à medida que chegam (Server-Sent Events). Ao final, `ultima_resposta` é preenchida."""
        self._limitador.reservar()
        inicio = time.monotonic()
        resp = self._enviar("POST", "/chat/completions", self._corpo(mensagens, temperatura, max_tokens, False, True))
        partes: list[str] = []
        motivo, modelo, uso = "", self.config.modelo, {}
        try:
            for linha in resp.iter_lines(decode_unicode=True):
                if not linha:
                    continue
                if isinstance(linha, bytes):
                    linha = linha.decode("utf-8", "replace")
                if not linha.startswith("data:"):
                    continue  # comentários ": keep-alive"
                dado = linha[5:].strip()
                if dado == "[DONE]":
                    break
                try:
                    evento = json.loads(dado)
                except json.JSONDecodeError:
                    continue
                if evento.get("error"):
                    raise IAIndisponivel(detalhe=self._ocultar(str(evento["error"])))
                modelo = evento.get("model", modelo)
                uso = evento.get("usage") or uso
                for esc in evento.get("choices") or []:
                    pedaco = (esc.get("delta") or {}).get("content")
                    if pedaco:
                        partes.append(pedaco)
                        yield pedaco
                    if esc.get("finish_reason"):
                        motivo = esc["finish_reason"]
        except ErroIA:
            raise
        except Exception as e:
            nome = type(e).__name__
            if "Timeout" in nome:
                raise IATempoEsgotado(detalhe=self._ocultar(nome)) from e
            raise IASemConexao("A conexão com a DeepSeek caiu durante a resposta. Tente novamente.",
                               detalhe=self._ocultar(f"{nome}: {e}")) from e
        finally:
            try:
                resp.close()
            except Exception:
                pass
        texto = "".join(partes)
        if not texto.strip():
            raise IARespostaInvalida("A DeepSeek retornou uma resposta vazia. Tente novamente.")
        self.ultima_resposta = RespostaIA(texto=texto, modelo=modelo, motivo_fim=motivo,
                                          tokens_entrada=int((uso or {}).get("prompt_tokens") or 0),
                                          tokens_saida=int((uso or {}).get("completion_tokens") or 0),
                                          duracao_s=time.monotonic() - inicio)

    def saldo(self) -> dict:
        """GET /user/balance → {'is_available': bool, 'balance_infos': [...]}"""
        resp = self._enviar("GET", "/user/balance", timeout=(10, 20))
        try:
            return resp.json()
        except Exception as e:
            raise IARespostaInvalida(detalhe=self._ocultar(str(e))) from e

    def testar_conexao(self, com_chat: bool = False) -> StatusIA:
        """Diagnóstico real (sem simulação): consulta o saldo e, opcionalmente, faz uma chamada mínima ao modelo.
        Nunca levanta exceção."""
        if not self.configurado:
            e = IANaoConfigurada()
            return StatusIA(False, e.mensagem_usuario, e.codigo, modelo=self.config.modelo)
        try:
            dados = self.saldo()
            saldos = dados.get("balance_infos") or []
            txt_saldo = "; ".join(f"{s.get('total_balance')} {s.get('currency')}" for s in saldos) or None
            if not dados.get("is_available", True):
                return StatusIA(False, IASemSaldo.mensagem_padrao, IASemSaldo.codigo, saldo=txt_saldo, modelo=self.config.modelo)
            detalhes: dict = {}
            if com_chat:
                r = self.conversar([{"role": "user", "content": "Responda apenas: OK"}], temperatura=0, max_tokens=5)
                detalhes = {"resposta_teste": r.texto.strip()[:20], "modelo_resposta": r.modelo,
                            "duracao_s": round(r.duracao_s, 2)}
            return StatusIA(True, "DeepSeek conectada e com saldo disponível.", "ok", saldo=txt_saldo,
                            modelo=self.config.modelo, detalhes=detalhes)
        except ErroIA as e:
            return StatusIA(False, e.mensagem_usuario, e.codigo, modelo=self.config.modelo, detalhes={"detalhe": e.detalhe})


# =====================================================================================================
# Cliente compartilhado (um por configuração, para que o limite de requisições valha para o processo)
# =====================================================================================================
_clientes: dict[tuple, ClienteDeepSeek] = {}
_lock_clientes = threading.Lock()


def obter_cliente() -> ClienteDeepSeek:
    cfg = carregar_config()
    chave = (cfg.api_key, cfg.base_url, cfg.modelo, cfg.timeout_s, cfg.max_req_min, cfg.max_tokens)
    with _lock_clientes:
        if chave not in _clientes:
            _clientes.clear()
            _clientes[chave] = ClienteDeepSeek(cfg)
        return _clientes[chave]
