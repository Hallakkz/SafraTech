"""
Diagnóstico nutricional (análise foliar e sintomas visuais) — lógica determinística sobre os registros do nutricao_database.

Regras:
- só usa faixas da cultura escolhida (a consulta já filtra por cultura);
- só usa faixas cujo protocolo de amostragem (estádio) é compatível com o informado;
- os limites e operadores vêm do banco; nada é estimado;
- sintomas são indícios, nunca diagnóstico definitivo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.classificacao import (ABAIXO, ACIMA, ADEQUADO, DIVERGENTE, INSUFICIENTE, atende, faixa_texto, num, txt)

SEM_DADOS = "Não há dados de referência disponíveis no banco para esta combinação."

NUTRIENTES_FOLIARES = ["N", "P", "K", "Ca", "Mg", "S", "B", "Zn", "Fe", "Mn", "Cu", "Mo"]
ESTAGIO_REMETIDO = "Conforme Cap. 10"        # Cap. 8, Tab. 9 remete o protocolo de amostragem ao Cap. 10
ESTAGIO_NAO_ESPECIFICADO = "Não especificado"
OUTRO_ESTAGIO = "__outro__"


def estagios_protocolo(faixas: pd.DataFrame) -> list[str]:
    """Estádios de amostragem explicitamente definidos nas faixas da cultura."""
    if faixas is None or faixas.empty:
        return []
    est = [txt(e) for e in faixas["estagio"].dropna().unique()]
    return sorted(e for e in est if e and not e.startswith(ESTAGIO_REMETIDO) and not e.startswith(ESTAGIO_NAO_ESPECIFICADO))


def faixas_compativeis(faixas: pd.DataFrame, estagio: str) -> tuple[list[dict], list[str]]:
    """Seleciona as faixas compatíveis com o estádio informado. Retorna (registros, avisos)."""
    if faixas is None or faixas.empty or not estagio or estagio == OUTRO_ESTAGIO:
        return [], []
    protocolos = estagios_protocolo(faixas)
    regs, avisos = [], set()
    for r in faixas.to_dict("records"):
        e = txt(r.get("estagio"))
        if e == estagio:
            regs.append(r)
        elif e.startswith(ESTAGIO_REMETIDO) and estagio in protocolos and "EMB_CERRADO_2004" == txt(r.get("fonte_id")):
            regs.append(r)
            avisos.add("Faixas de micronutrientes do Cap. 8 (Tabela 9) usam o procedimento de amostragem do Cap. 10 da mesma fonte.")
        elif e.startswith(ESTAGIO_NAO_ESPECIFICADO):
            regs.append({**r, "_aviso_estagio": True})
            avisos.add(f"Há referência cuja fonte não especifica o estádio de amostragem ({r.get('fonte_id')}); "
                       "use-a com cautela.")
    return regs, sorted(avisos)


@dataclass
class ResultadoNutriente:
    nutriente: str
    valor: Optional[float]
    unidade_base: str
    status: str
    avaliacoes: list = field(default_factory=list)   # [{registro, status, faixa}]
    mensagem: str = ""
    conversao: str = ""


def _classificar(valor: float, r: dict) -> str:
    if atende(valor, r.get("valor_min"), r.get("operador_min"), r.get("valor_max"), r.get("operador_max")):
        return ADEQUADO
    vmin = num(r.get("valor_min"))
    return ABAIXO if (vmin is not None and valor < vmin) else ACIMA


def avaliar_foliar(valores: dict, unidades_base: dict, compat: list[dict], conversoes: dict | None = None) -> list[ResultadoNutriente]:
    """valores: {nutriente: valor já convertido para a unidade_base}; compat: faixas compatíveis."""
    conversoes = conversoes or {}
    saida = []
    for nut in NUTRIENTES_FOLIARES:
        v = valores.get(nut)
        if v is None:
            continue
        ub = unidades_base.get(nut, "")
        regs = [r for r in compat if txt(r.get("nutriente_codigo")) == nut and txt(r.get("unidade_base")) == ub]
        if not regs:
            saida.append(ResultadoNutriente(nut, v, ub, INSUFICIENTE, [], SEM_DADOS, conversoes.get(nut, "")))
            continue
        aval = [{"registro": r, "status": _classificar(v, r), "faixa": faixa_texto(r)} for r in regs]
        sts = {a["status"] for a in aval}
        status = sts.pop() if len(sts) == 1 else DIVERGENTE
        msg = "" if status != DIVERGENTE else "As fontes cadastradas apresentam faixas diferentes e o valor se enquadra de forma distinta em cada uma."
        saida.append(ResultadoNutriente(nut, v, ub, status, aval, msg, conversoes.get(nut, "")))
    return saida


def ausencias_registradas(complementares: pd.DataFrame, cobertura: pd.DataFrame) -> list[dict]:
    """Ausências documentadas no banco (registros 'ausencia_dado' e cobertura com disponivel = 'nao')."""
    out = []
    if complementares is not None and not complementares.empty:
        for r in complementares.to_dict("records"):
            if txt(r.get("categoria")) == "ausencia_dado":
                out.append({"tipo": "registro", "nutriente": txt(r.get("nutriente_codigo")), "texto": txt(r.get("texto")),
                            "fonte": txt(r.get("referencia_abnt")), "registro_id": r.get("registro_id"), "secao": txt(r.get("secao"))})
    if cobertura is not None and not cobertura.empty:
        # agrupa por tipo de informação e nota (evita uma linha por nutriente com o mesmo texto)
        grupos: dict = {}
        for r in cobertura.to_dict("records"):
            if txt(r.get("disponivel")) == "nao":
                k = (txt(r.get("tipo_informacao")), txt(r.get("descricao")), txt(r.get("nota")))
                grupos.setdefault(k, []).append(txt(r.get("nutriente_codigo")))
        for (tipo, desc, nota), nuts in grupos.items():
            out.append({"tipo": "cobertura", "nutriente": ", ".join(sorted(set(nuts))),
                        "texto": f"{tipo}: {desc or 'não disponível'}" + (f" — {nota}" if nota else ""),
                        "fonte": "nutricao.cobertura_cultura_nutriente", "registro_id": "", "secao": tipo})
    return out


# ---------------- sintomas visuais ----------------
SINTOMAS = {
    "amarelecimento": r"amarel|clorose uniforme|clorose do ponteiro|verde-clar|verde-lim",
    "manchas": r"mancha",
    "bordas_queimadas": r"margens|bordas|pontas.{0,30}queimad|queimad",
    "arroxeadas": r"p[úu]rpur|arroxead|avermelhad|vermelh",
    "crescimento_reduzido": r"crescimento|nanismo|raqu[íi]tic|\banãs?\b|intern[óo]dios curtos|paralisa",
    "deformacoes": r"deform|enrugad|encarquilh|torcid|distor[çc]|enrolad|encurvad|tortas|gancho",
    "clorose_internerval": r"internerval|interverval|entre (as )?nervuras|nervuras (permanecem )?verdes|reticulad",
    "necrose": r"necro|necre|morte|tecido morto|secam|morrem",
}


def associar_sintomas(sintomas_df: pd.DataFrame, escolhidos: list[str], cultura: str) -> list[dict]:
    """Relaciona sintomas observados aos textos cadastrados (busca por termos). Retorna registros ordenados por
    número de sintomas coincidentes, priorizando os específicos da cultura."""
    if sintomas_df is None or sintomas_df.empty or not escolhidos:
        return []
    saida = []
    for r in sintomas_df.to_dict("records"):
        texto = f"{txt(r.get('texto'))} {txt(r.get('parte_planta'))}"
        hits = [s for s in escolhidos if re.search(SINTOMAS[s], texto, re.IGNORECASE)]
        if hits:
            saida.append({**r, "coincidencias": hits, "especifico": txt(r.get("cultura")) == cultura})
    saida.sort(key=lambda x: (not x["especifico"], -len(x["coincidencias"]), txt(x.get("nutriente_codigo"))))
    return saida
