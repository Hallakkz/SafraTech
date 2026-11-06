"""
Regras de aplicabilidade das referências de solo (quais registros do banco valem para a análise informada)
e orquestração da classificação por parâmetro. Função pura: recebe os registros já consultados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.classificacao import (INSUFICIENTE, ResultadoParametro, agrupar, atende, classificar_grupo, condicao_do_registro,
                                num, status_final, txt)

# chave interna -> (parâmetros no banco, unidade_base esperada, método relevante?)
PARAMETROS = {
    "ph": (["pH"], "adimensional", True),
    "p": (["Fósforo (P)"], "mg/dm3", True),
    "k": (["Potássio (K)"], None, True),               # mg/dm3 (Anexo 6) ou mg/kg (Cap. 7) — conforme unidade informada
    "ca": (["Cálcio (Ca)"], "cmolc/dm3", False),
    "mg": (["Magnésio (Mg)"], "cmolc/dm3", False),
    "s": (["Enxofre (S)"], "mg/dm3", False),
    "mo": (["Matéria orgânica (MO)"], "%", False),
    "ctc": (["CTC a pH 7"], "cmolc/dm3", False),
    "v": (["Saturação por bases (V%)", "Saturação por bases (V%) da CTC a pH 7", "Saturação por bases desejada (V2)"], "%", False),
    "m": (["Saturação por alumínio (m%)"], "%", False),
    "n": ([], None, False),                              # não há faixa de interpretação de N no solo nos bancos
    "b": (["Boro (B)"], "mg/dm3", True),
    "cu": (["Cobre (Cu)"], "mg/dm3", True),
    "fe": (["Ferro (Fe)"], "mg/dm3", True),
    "mn": (["Manganês (Mn)"], "mg/dm3", True),
    "zn": (["Zinco (Zn)"], "mg/dm3", True),
    # derivados (calculados a partir dos valores informados)
    "ca_mg": (["Relação Ca:Mg", "Relação Ca/Mg no solo"], "relação", False),
    "camg_k": (["Relação (Ca+Mg)/K"], "relação", False),
    "ca_k": (["Relação Ca/K"], "relação", False),
    "mg_k": (["Relação Mg/K"], "relação", False),
    "k_ctc": (["Saturação por K na CTC a pH 7"], "%", False),
}

METODOS = {
    "ph_agua": lambda m: "água" in m.lower() and "quente" not in m.lower(),
    "ph_cacl2": lambda m: "cacl2" in m.lower(),
    "p_mehlich": lambda m: m.startswith("Mehlich-1") and "P-rem" not in m,
    "p_prem": lambda m: "P-rem" in m,
    "p_resina": lambda m: "Resina" in m,
    "k_mehlich": lambda m: m.startswith("Mehlich-1"),
    "micro_mehlich": lambda m: m.startswith("Mehlich-1"),
    "micro_dtpa": lambda m: m.startswith("DTPA"),
    "b_agua_quente": lambda m: m.lower().startswith("água quente"),
}

NAO_ESPECIFICADO = "Não especificado"


@dataclass
class Contexto:
    culturas: list
    bioma_cerrado: str = "nao_sei"            # 'sim' | 'nao' | 'nao_sei'
    sistema: Optional[str] = None              # 'sequeiro' | 'irrigado'
    argila: Optional[float] = None             # %
    prem: Optional[float] = None               # mg/L (Manual) — ver divergência DIV-SOL-PREM-UNIDADE
    ctc: Optional[float] = None                # cmolc/dm3
    textura: Optional[str] = None              # 'Textura argilosa' etc. (valores do banco)
    camada: str = "0-20"                       # '0-20' | 'sub' | 'media_0_40'
    metodos: dict = field(default_factory=dict)   # chave do parâmetro -> chave em METODOS


def _camada_ok(reg_camada: str, camada: str) -> bool:
    c = reg_camada.lower()
    if not c or c.startswith("não especificada"):
        return True
    if "ou camadas mais profundas" in c:
        return camada in ("0-20", "sub")
    if c.startswith("abaixo de 20"):
        return camada == "sub"
    if c.startswith("média de 0-20 e 20-40"):
        return camada == "media_0_40"
    if c.startswith("0-20"):
        return camada == "0-20"
    if c.startswith("0-40"):
        return False
    return True


def aplicabilidade(r: dict, chave: str, ctx: Contexto, unidade_base: Optional[str]) -> tuple[bool, str, bool]:
    """(aplicável?, motivo se não, informativo?) — informativo = referência mostrada mas não usada para classificar."""
    _, ub_padrao, metodo_relevante = PARAMETROS[chave]
    ub = unidade_base or ub_padrao
    if ub and txt(r.get("unidade_base")) and txt(r.get("unidade_base")) != ub:
        return False, f"unidade da referência ({r.get('unidade_base')}) diferente da informada ({ub})", False
    if txt(r.get("cultura")) not in ctx.culturas:
        return False, "referência de outra cultura", False
    metodo = txt(r.get("metodo"))
    if metodo_relevante:
        if metodo.startswith(NAO_ESPECIFICADO):
            return False, "a fonte não especifica o método analítico — não usada para classificar", True
        mk = ctx.metodos.get(chave)
        if not mk:
            return False, "requer informar o método analítico (extrator) usado no laudo", True
        if not METODOS[mk](metodo):
            return False, f"método da referência ({metodo}) diferente do informado", False
    regiao = txt(r.get("regiao"))
    if regiao == "Cerrado" and ctx.bioma_cerrado == "nao":
        return False, "referência regional do Cerrado e a área foi indicada fora do Cerrado", True
    if not _camada_ok(txt(r.get("camada")), ctx.camada):
        return False, f"camada da referência ({r.get('camada')}) diferente da informada", False
    cond = txt(r.get("condicoes")).lower()
    if ctx.sistema:
        tem_seq, tem_irr = "sequeiro" in cond, "irrigad" in cond
        if tem_seq and not tem_irr and ctx.sistema != "sequeiro":
            return False, "referência para sistema de sequeiro", False
        if tem_irr and not tem_seq and ctx.sistema != "irrigado":
            return False, "referência para sistema irrigado", False
    elif ("sequeiro" in cond) != ("irrigad" in cond):
        return False, "requer informar o sistema (sequeiro ou irrigado)", True
    c = condicao_do_registro(r.get("tipo_solo"))
    if c:
        var = c["variavel"]
        if var == "textura":
            if not ctx.textura:
                return False, "requer a classe textural do solo", True
            if ctx.textura != c["valor"]:
                return False, "classe textural diferente", False
        elif var in ("argila", "prem", "ctc"):
            v = {"argila": ctx.argila, "prem": ctx.prem, "ctc": ctx.ctc}[var]
            if v is None:
                return False, {"argila": "requer o teor de argila (%)", "prem": "requer o P remanescente",
                               "ctc": "requer a CTC a pH 7"}[var], True
            if not atende(v, c["vmin"], c["opmin"], c["vmax"], c["opmax"]):
                return False, f"condição '{c['texto']}' não atendida", False
        else:
            return False, f"condição não interpretável: {c.get('texto')}", True
    return True, "", False


def avaliar(chave: str, valor: Optional[float], referencias: pd.DataFrame, ctx: Contexto,
            unidade_base: Optional[str] = None) -> ResultadoParametro:
    """Avalia um parâmetro: filtra referências aplicáveis, classifica por grupo e consolida."""
    if valor is None:
        return ResultadoParametro(INSUFICIENTE, limitacoes=["valor não informado"])
    nomes = PARAMETROS[chave][0]
    if not nomes:
        return ResultadoParametro(INSUFICIENTE, limitacoes=["não há faixa de interpretação deste parâmetro no solo_database"])
    regs = [r for r in referencias.to_dict("records") if r.get("parametro") in nomes] if not referencias.empty else []
    if not regs:
        return ResultadoParametro(INSUFICIENTE, limitacoes=["nenhuma referência cadastrada para este parâmetro"])
    aplicaveis, limit, infos = [], [], []
    for r in regs:
        ok, motivo, informativo = aplicabilidade(r, chave, ctx, unidade_base)
        if ok:
            aplicaveis.append(r)
        else:
            if informativo:
                infos.append({**r, "motivo_nao_uso": motivo})
                limit.append(motivo)
    grupos = [classificar_grupo(valor, g) for g in agrupar(aplicaveis)]
    res = ResultadoParametro(status_final(grupos), grupos, sorted(set(limit)), infos)
    if not grupos:
        res.limitacoes = sorted(set(limit)) or ["nenhuma referência aplicável às condições informadas (método, região, camada, textura ou sistema)"]
    for g in grupos:
        if g.status == INSUFICIENTE:
            res.limitacoes.append(g.motivo)
        reg = txt(g.registros[0].get("regiao"))
        if reg == "Cerrado" and ctx.bioma_cerrado == "nao_sei":
            res.limitacoes.append("referência regional do Cerrado — confirme se a área está no bioma Cerrado")
        elif reg and reg not in ("Cerrado", "Brasil", "Brasil (geral)"):
            res.limitacoes.append(f"referência regional ({reg}) — validade fora dessa região não é garantida pela fonte")
    res.limitacoes = sorted(set(res.limitacoes))
    return res


def derivados(v: dict) -> dict:
    """Relações calculadas a partir dos valores informados (Ca, Mg, K em cmolc/dm3; CTC em cmolc/dm3)."""
    out = {}
    ca, mg, k_cmol, ctc = v.get("ca"), v.get("mg"), v.get("k_cmolc"), v.get("ctc")
    if ca is not None and mg is not None and mg > 0:
        out["ca_mg"] = ca / mg
    if k_cmol is not None and k_cmol > 0:
        if ca is not None and mg is not None:
            out["camg_k"] = (ca + mg) / k_cmol
        if ca is not None:
            out["ca_k"] = ca / k_cmol
        if mg is not None:
            out["mg_k"] = mg / k_cmol
        if ctc is not None and ctc > 0:
            out["k_ctc"] = 100 * k_cmol / ctc
    return out
