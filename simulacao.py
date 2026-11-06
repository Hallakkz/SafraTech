"""
Simulação complementar ao ZARC. Compara as condições informadas pelo usuário com os registros técnicos
(não oficiais) do plantio_database. Não prevê produtividade nem substitui o ZARC.

Cada item de saída carrega a sua origem:
  'zarc_oficial'      — indicação oficial (portaria MAPA)
  'referencia_tecnica'— registro técnico de livro/documento (plantio.registro)
  'usuario'           — valor informado pelo usuário
  'simulacao'         — resultado da comparação feita pelo aplicativo
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.classificacao import atende, faixa_texto, num, txt

ORIGEM_ZARC = "zarc_oficial"
ORIGEM_TECNICA = "referencia_tecnica"
ORIGEM_USUARIO = "usuario"
ORIGEM_SIMULACAO = "simulacao"

_RX_SEMEADURA = re.compile(r"semeadura|emerg|germina", re.IGNORECASE)
_RX_FAVORAVEL = re.compile(r"adequad|ideal|favor[áa]vel|ótim|necessidade|recomendad|indicad|m[íi]nima|para produzir", re.IGNORECASE)
_RX_DESFAVORAVEL = re.compile(r"limitante|reduz|atrasa|paralisa|excessiv|abort|dist[úu]rb|prejud", re.IGNORECASE)
_RX_CICLO = re.compile(r"ciclo", re.IGNORECASE)


@dataclass
class ItemSimulacao:
    variavel: str
    valor_usuario: Optional[float]
    registro: dict
    dentro: bool
    leitura: str          # 'favoravel' | 'desfavoravel' | 'descritiva'
    texto: str


def _tem_limite(r: dict) -> bool:
    return num(r.get("valor_min")) is not None or num(r.get("valor_max")) is not None


def _comparar(variavel: str, valor: float, regs: list[dict]) -> list[ItemSimulacao]:
    out = []
    for r in regs:
        if not _tem_limite(r):
            continue
        dentro = atende(valor, r.get("valor_min"), r.get("operador_min"), r.get("valor_max"), r.get("operador_max"))
        par = txt(r.get("parametro"))
        desf = bool(_RX_DESFAVORAVEL.search(par))
        fav = bool(_RX_FAVORAVEL.search(par)) and not desf
        ref = f"\"{par}\" ({faixa_texto(r)} {txt(r.get('unidade'))})"
        if desf:
            leitura = "desfavoravel" if dentro else "neutra"
            texto = (f"O valor informado se enquadra na condição desfavorável {ref}." if dentro
                     else f"O valor informado não se enquadra na condição desfavorável {ref}.")
        elif fav:
            leitura = "favoravel" if dentro else "desfavoravel"
            texto = (f"O valor informado está dentro de {ref}." if dentro else f"O valor informado está fora de {ref}.")
        else:
            leitura = "descritiva"
            texto = (f"O valor informado se enquadra em {ref}." if dentro else f"O valor informado não se enquadra em {ref}.")
        out.append(ItemSimulacao(variavel, valor, r, dentro, leitura, texto))
    return out


def simular(exig: pd.DataFrame, temp_ar: Optional[float] = None, temp_solo: Optional[float] = None,
            chuva_ciclo: Optional[float] = None) -> dict:
    """Compara as condições informadas com os registros técnicos da cultura."""
    regs = exig.to_dict("records") if exig is not None and not exig.empty else []
    temps = [r for r in regs if txt(r.get("categoria")) == "temperatura"
             and _RX_SEMEADURA.search(f"{txt(r.get('estagio'))} {txt(r.get('parametro'))}")]
    t_solo = [r for r in temps if "solo" in txt(r.get("parametro")).lower()]
    t_ar = [r for r in temps if r not in t_solo]
    agua = [r for r in regs if txt(r.get("categoria")) in ("necessidade_hidrica", "precipitacao")
            and _RX_CICLO.search(txt(r.get("unidade")))]
    umid = [r for r in regs if txt(r.get("categoria")) == "umidade_solo"
            or (txt(r.get("categoria")) == "condicao_ambiental" and "encharc" in txt(r.get("parametro")).lower())]
    res = {"itens": [], "sem_referencia": [], "umidade_textos": umid}
    for nome, valor, alvo in (("temperatura_ar", temp_ar, t_ar), ("temperatura_solo", temp_solo, t_solo),
                              ("chuva_ciclo", chuva_ciclo, agua)):
        if valor is None:
            continue
        itens = _comparar(nome, valor, alvo)
        if itens:
            res["itens"].extend(itens)
        else:
            res["sem_referencia"].append(nome)
    return res
