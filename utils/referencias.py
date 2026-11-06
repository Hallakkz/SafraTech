"""Montagem das tabelas de fontes e divergências a partir dos registros usados."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.classificacao import txt


def tabela_fontes(registros: Iterable[dict]) -> pd.DataFrame:
    """Uma linha por (fonte, seção, página) a partir de registros vindos de v_registro_com_fonte."""
    linhas, vistos = [], set()
    for r in registros:
        k = (txt(r.get("fonte_id")), txt(r.get("secao")), txt(r.get("pagina_impressa")))
        if not k[0] or k in vistos:
            continue
        vistos.add(k)
        linhas.append({
            "fonte_id": k[0],
            "título": txt(r.get("fonte_titulo")),
            "autores": txt(r.get("fonte_autores")),
            "instituição": txt(r.get("fonte_instituicao")),
            "ano": txt(r.get("fonte_ano")),
            "seção": k[1],
            "página": k[2],
            "referência": txt(r.get("referencia_abnt")),
        })
    return pd.DataFrame(linhas)


def ids_registros(registros: Iterable[dict]) -> list[str]:
    return sorted({txt(r.get("registro_id")) for r in registros if txt(r.get("registro_id"))})


def resumo_divergencias(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [c for c in ["divergencia_id", "parametro", "descricao", "fontes", "tratamento"] if c in df.columns]
    agg = df.groupby(cols, dropna=False)["registro_id"].apply(lambda s: ", ".join(sorted(set(map(str, s))))).reset_index()
    return agg.rename(columns={"registro_id": "registros"})
