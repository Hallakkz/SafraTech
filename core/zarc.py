"""
Leitura das indicações oficiais do ZARC (plantio.zarc_indicacao) já filtradas no PostgreSQL.

- 20, 30, 40 = nível de risco climático (%) do decêndio;
- 0 = SEM INDICAÇÃO de semeadura no decêndio (não é "risco zero");
- decêndios são identificados apenas pelo número (1 a 36): o banco não define as datas correspondentes,
  portanto o aplicativo não converte decêndios em datas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.classificacao import num, txt

NIVEIS = (20, 30, 40)
SEM_INDICACAO = 0

INDICADO_TODO = "indicado_todo"
INDICADO_PARCIAL = "indicado_parcial"
SEM_INDICACAO_PERIODO = "sem_indicacao_periodo"
SEM_LINHA = "sem_linha"


def riscos_da_linha(linha: dict) -> list[int]:
    out = []
    for i in range(1, 37):
        v = num(linha.get(f"dec{i}"))
        out.append(int(v) if v is not None else SEM_INDICACAO)
    return out


def periodo(inicio: int, fim: int) -> list[int]:
    """Decêndios de início a fim (inclusive), com passagem do 36 para o 1."""
    inicio, fim = int(inicio), int(fim)
    if not (1 <= inicio <= 36 and 1 <= fim <= 36):
        raise ValueError("decêndios devem estar entre 1 e 36")
    if inicio <= fim:
        return list(range(inicio, fim + 1))
    return list(range(inicio, 37)) + list(range(1, fim + 1))


def janelas(riscos: list[int]) -> list[dict]:
    """Sequências contínuas de decêndios com mesmo nível de risco (considerando a virada 36→1)."""
    blocos, atual = [], None
    for d, r in enumerate(riscos, start=1):
        if r == SEM_INDICACAO:
            atual = None
            continue
        if atual and atual["risco"] == r and atual["fim"] == d - 1:
            atual["fim"] = d
        else:
            atual = {"inicio": d, "fim": d, "risco": r}
            blocos.append(atual)
    if len(blocos) > 1 and blocos[0]["inicio"] == 1 and blocos[-1]["fim"] == 36 and blocos[0]["risco"] == blocos[-1]["risco"]:
        ultimo = blocos.pop()
        blocos[0] = {"inicio": ultimo["inicio"], "fim": blocos[0]["fim"], "risco": ultimo["risco"]}
    for b in blocos:
        b["decendios"] = periodo(b["inicio"], b["fim"])
    return sorted(blocos, key=lambda b: (b["risco"], b["inicio"]))


@dataclass
class AvaliacaoPeriodo:
    situacao: str
    decendios: list
    riscos_no_periodo: dict = field(default_factory=dict)  # decêndio -> risco (0 = sem indicação)
    melhor_risco: Optional[int] = None
    pior_risco: Optional[int] = None


def avaliar_periodo(riscos: list[int], decs: list[int]) -> AvaliacaoPeriodo:
    r = {d: riscos[d - 1] for d in decs}
    indicados = [v for v in r.values() if v in NIVEIS]
    if not indicados:
        sit = SEM_INDICACAO_PERIODO
    elif len(indicados) == len(decs):
        sit = INDICADO_TODO
    else:
        sit = INDICADO_PARCIAL
    return AvaliacaoPeriodo(sit, decs, r, min(indicados) if indicados else None, max(indicados) if indicados else None)


def tabela_longa(ind: pd.DataFrame) -> pd.DataFrame:
    """Transforma as linhas filtradas (poucas) em formato longo para gráficos: uma linha por decêndio."""
    linhas = []
    for row in ind.to_dict("records"):
        rotulo = f"NM {txt(row.get('cod_nm'))}" if txt(row.get("cod_nm")) not in ("", "0") else "—"
        rot = f"{txt(row.get('manejo'))} · {rotulo}"
        for d, r in enumerate(riscos_da_linha(row), start=1):
            linhas.append({"indicacao_id": row.get("indicacao_id"), "linha": rot, "decendio": d, "risco": r,
                           "rotulo": f"{r}%" if r in NIVEIS else "sem indicação"})
    return pd.DataFrame(linhas)


def resumo_linha(row: dict) -> dict:
    riscos = riscos_da_linha(row)
    cont = {n: sum(1 for r in riscos if r == n) for n in NIVEIS}
    return {"n_indicados": sum(cont.values()), "n_sem_indicacao": riscos.count(SEM_INDICACAO), **{f"n_{n}": c for n, c in cont.items()},
            "janelas": janelas(riscos)}
