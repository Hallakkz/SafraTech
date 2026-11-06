"""
Sessão HTTP falsa para os TESTES AUTOMATIZADOS da camada DeepSeek (erros, novas tentativas, streaming, JSON).

Ela substitui `requests.Session` apenas dentro do pytest, para verificar o tratamento de cada código de erro da API sem
gastar créditos. NÃO é usada pelo aplicativo e não serve para afirmar que a integração real funciona: o teste real da API
é feito por `tests/validar_deepseek.py`, que chama a DeepSeek de verdade com a chave do .env.
"""
from __future__ import annotations

import json
from typing import Callable, Optional


class RespostaFalsa:
    def __init__(self, status: int = 200, dados: Optional[dict] = None, linhas: Optional[list[str]] = None,
                 cabecalhos: Optional[dict] = None, texto: str = ""):
        self.status_code = status
        self._dados = dados
        self._linhas = linhas
        self.headers = cabecalhos or {}
        self.text = texto or (json.dumps(dados) if dados is not None else "")
        self.fechada = False

    def json(self):
        if self._dados is None:
            raise ValueError("sem JSON")
        return self._dados

    def iter_lines(self, decode_unicode=False):
        for l in self._linhas or []:
            yield l

    def close(self):
        self.fechada = True


def resposta_chat(texto: str, modelo: str = "deepseek-chat") -> RespostaFalsa:
    return RespostaFalsa(200, {"model": modelo, "choices": [{"message": {"role": "assistant", "content": texto},
                                                             "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 10, "completion_tokens": 20}})


def resposta_stream(pedacos: list[str], modelo: str = "deepseek-chat") -> RespostaFalsa:
    linhas = [": keep-alive", ""]
    for p in pedacos:
        linhas.append("data: " + json.dumps({"model": modelo, "choices": [{"delta": {"content": p}, "finish_reason": None}]}))
    linhas.append("data: " + json.dumps({"model": modelo, "choices": [{"delta": {}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": len(pedacos)}}))
    linhas.append("data: [DONE]")
    return RespostaFalsa(200, linhas=linhas)


def erro(status: int, mensagem: str = "erro", cabecalhos: Optional[dict] = None) -> RespostaFalsa:
    return RespostaFalsa(status, {"error": {"message": mensagem, "type": "invalid_request_error"}}, cabecalhos=cabecalhos)


class SessaoFalsa:
    """`roteiro(metodo, url, corpo) -> RespostaFalsa | Exception`. Todas as chamadas ficam em `chamadas`."""

    def __init__(self, roteiro: Callable):
        self.roteiro = roteiro
        self.chamadas: list[dict] = []

    def request(self, metodo, url, headers=None, json=None, stream=False, timeout=None):
        self.chamadas.append({"metodo": metodo, "url": url, "headers": dict(headers or {}), "json": json, "stream": stream,
                              "timeout": timeout})
        r = self.roteiro(metodo, url, json)
        if isinstance(r, Exception):
            raise r
        return r

    def close(self):
        pass


class ErroDeConexao(Exception):
    """Nome semelhante ao do requests (ConnectionError)."""


class ReadTimeout(Exception):
    pass
