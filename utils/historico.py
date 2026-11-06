"""Histórico opcional de análises. Fica na sessão do Streamlit e, se o usuário marcar, em historico/analises.jsonl.
Nunca grava nos bancos de dados."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping

ARQUIVO = Path(os.environ.get("SAFRATECH_HISTORICO", Path(__file__).resolve().parent.parent / "historico" / "analises.jsonl"))
CHAVE = "safratech_historico"


def registrar(estado: MutableMapping, modulo: str, entradas: dict, resumo: dict, salvar_arquivo: bool = False) -> dict:
    item = {"data_hora": datetime.now().isoformat(timespec="seconds"), "modulo": modulo,
            "entradas": _serializavel(entradas), "resumo": _serializavel(resumo)}
    estado.setdefault(CHAVE, [])
    estado[CHAVE].insert(0, item)
    del estado[CHAVE][30:]
    if salvar_arquivo:
        try:
            ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
            with open(ARQUIVO, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return item


def listar(estado: MutableMapping) -> list[dict]:
    return list(estado.get(CHAVE, []))


def _serializavel(x: Any):
    if isinstance(x, dict):
        return {str(k): _serializavel(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_serializavel(v) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)
