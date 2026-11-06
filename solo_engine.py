"""Orquestra o Diagnóstico do Solo: consulta as faixas no PostgreSQL (filtradas por parâmetro e cultura),
converte unidades, aplica as regras de aplicabilidade e consolida divergências e fontes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.classificacao import ResultadoParametro, status_final, txt
from core.solo_regras import PARAMETROS, Contexto, avaliar, derivados
from core.unidades import Fatores, converter_solo

GENERICAS = ["Culturas anuais", "Não específico de cultura"]

ROTULOS = {
    "ph": "pH", "p": "Fósforo (P)", "k": "Potássio (K)", "ca": "Cálcio (Ca)", "mg": "Magnésio (Mg)", "s": "Enxofre (S)",
    "mo": "Matéria orgânica (MO)", "ctc": "CTC a pH 7", "v": "Saturação por bases (V%)", "m": "Saturação por alumínio (m%)",
    "n": "Nitrogênio (N)", "b": "Boro (B)", "cu": "Cobre (Cu)", "fe": "Ferro (Fe)", "mn": "Manganês (Mn)", "zn": "Zinco (Zn)",
    "ca_mg": "Relação Ca/Mg (calculada)", "camg_k": "Relação (Ca+Mg)/K (calculada)", "ca_k": "Relação Ca/K (calculada)",
    "mg_k": "Relação Mg/K (calculada)", "k_ctc": "Saturação por K na CTC (calculada)",
}
UNIDADE_EXIBICAO = {"adimensional": "—", "mg/dm3": "mg/dm³", "cmolc/dm3": "cmolc/dm³", "%": "%", "mg/kg": "mg/kg", "relação": "relação"}


def culturas_aplicaveis(cultura: str, disponiveis: list[str]) -> list[str]:
    """Cultura escolhida + referências gerais + registros que listam explicitamente a cultura (ex.: 'Soja ou feijão')."""
    out = [cultura] + GENERICAS
    for c in disponiveis:
        partes = [p.strip().split(" (")[0] for p in c.replace(" ou ", ";").split(";")]
        if cultura in partes and c not in out:
            out.append(c)
    return out


@dataclass
class EntradaSolo:
    cultura: str
    uf: str = ""
    municipio: str = ""
    textura: Optional[str] = None
    bioma_cerrado: str = "nao_sei"
    sistema: Optional[str] = None
    argila: Optional[float] = None
    prem: Optional[float] = None
    camada: str = "0-20"
    metodos: dict = field(default_factory=dict)
    valores: dict = field(default_factory=dict)     # chave -> (valor, unidade)
    s_20_40: Optional[float] = None                  # S na camada 20-40 cm (mg/dm³), opcional


@dataclass
class LinhaSolo:
    chave: str
    rotulo: str
    valor_informado: Optional[float]
    unidade_informada: str
    valor_comparado: Optional[float]
    unidade_comparada: str
    conversao: str
    calculado: bool
    resultado: ResultadoParametro


def executar(e: EntradaSolo, referencias: pd.DataFrame, fatores: Fatores, culturas: list[str]) -> list[LinhaSolo]:
    """`referencias` deve ter sido consultada com parametros_consulta() e a mesma lista `culturas`."""
    conv = {k: converter_solo(k, v, u, fatores) for k, (v, u) in e.valores.items()}
    ctc_cmol = conv["ctc"].valor if "ctc" in conv else None
    ctx = Contexto(culturas=list(culturas), bioma_cerrado=e.bioma_cerrado, sistema=e.sistema, argila=e.argila, prem=e.prem, ctc=ctc_cmol,
                   textura=e.textura, camada=e.camada, metodos=e.metodos)
    linhas: list[LinhaSolo] = []
    for chave in ["ph", "p", "k", "ca", "mg", "s", "mo", "ctc", "v", "m", "n", "b", "cu", "fe", "mn", "zn"]:
        if chave not in e.valores:
            continue
        v, u = e.valores[chave]
        c = conv[chave]
        if chave == "s" and e.s_20_40 is not None and c.valor is not None:
            res = _avaliar_enxofre(c.valor, e.s_20_40, referencias, ctx)
            nota = f"média 0-20/20-40 cm = ({c.valor:g} + {e.s_20_40:g}) / 2 = {(c.valor + e.s_20_40) / 2:g} mg/dm³"
        else:
            res = avaliar(chave, c.valor, referencias, ctx, c.unidade_base)
            nota = c.nota
        linhas.append(LinhaSolo(chave, ROTULOS[chave], v, u, c.valor, UNIDADE_EXIBICAO.get(c.unidade_base or "", u),
                                nota, False, res))
    base = {"ca": conv["ca"].valor if "ca" in conv else None, "mg": conv["mg"].valor if "mg" in conv else None,
            "k_cmolc": conv["k"].k_cmolc if "k" in conv else None, "ctc": ctc_cmol}
    for chave, val in derivados(base).items():
        res = avaliar(chave, val, referencias, ctx)
        ub = PARAMETROS[chave][1]
        linhas.append(LinhaSolo(chave, ROTULOS[chave], None, "", val, UNIDADE_EXIBICAO.get(ub, ub), "calculado a partir dos valores informados",
                                True, res))
    return linhas


def _avaliar_enxofre(s_0_20: float, s_20_40: float, refs: pd.DataFrame, ctx: Contexto) -> ResultadoParametro:
    """S: a Tabela 11 usa a média de 0-20 e 20-40 cm; o nível crítico do Cap. 9 usa 0-20 cm."""
    from dataclasses import replace
    r_media = avaliar("s", (s_0_20 + s_20_40) / 2, refs, replace(ctx, camada="media_0_40"))
    r_sup = avaliar("s", s_0_20, refs, replace(ctx, camada="0-20"))
    grupos = r_media.grupos + r_sup.grupos
    return ResultadoParametro(status_final(grupos), grupos, sorted(set(r_media.limitacoes + r_sup.limitacoes)),
                              r_media.informativos + r_sup.informativos)


def parametros_consulta() -> list[str]:
    return sorted({n for v in PARAMETROS.values() for n in v[0]})


def registros_usados(linhas: list[LinhaSolo]) -> list[str]:
    ids = []
    for l in linhas:
        for g in l.resultado.grupos:
            ids.extend(txt(r.get("registro_id")) for r in g.registros)
    return sorted(set(i for i in ids if i))


def fontes_usadas(linhas: list[LinhaSolo]) -> list[dict]:
    vistos, out = set(), []
    for l in linhas:
        for g in l.resultado.grupos:
            r = g.registros[0]
            k = (txt(r.get("fonte_id")), txt(r.get("secao")))
            if k in vistos:
                continue
            vistos.add(k)
            out.append({"fonte_id": k[0], "secao": k[1], "titulo": txt(r.get("fonte_titulo")), "autores": txt(r.get("fonte_autores")),
                        "instituicao": txt(r.get("fonte_instituicao")), "ano": txt(r.get("fonte_ano")),
                        "pagina": txt(r.get("pagina_impressa")), "referencia": txt(r.get("referencia_abnt"))})
    return out
