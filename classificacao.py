"""
Classificação determinística a partir dos registros dos bancos.

Nenhum limite é criado aqui: os valores de corte e os operadores (>, >=, <, <=, =) vêm sempre dos registros.
A única lógica própria é a leitura da posição da classe encontrada em relação à classe que a própria
fonte rotula como adequada/favorável (ex.: 'Adequado', 'Faixa preferida', 'Faixa alvo').
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional

# ---------------- status exibidos ----------------
ADEQUADO = "adequado"
ATENCAO = "atencao"
ABAIXO = "abaixo"
ACIMA = "acima"
INSUFICIENTE = "insuficiente"
DIVERGENTE = "divergente"
CLASSE_FONTE = "classe_fonte"          # a fonte classifica, mas não define uma classe "adequada" para comparar

ORDEM_STATUS = [DIVERGENTE, ABAIXO, ACIMA, ATENCAO, CLASSE_FONTE, ADEQUADO, INSUFICIENTE]

_FAVORAVEL = re.compile(r"adequad|preferid|boa fertilidade|alvo|sem problemas|altas produtividades|^normal$|suficiência|intervalo adequado",
                        re.IGNORECASE)
_MEDIO = re.compile(r"^m[ée]di[oa]$", re.IGNORECASE)
_DESFAVORAVEL = re.compile(r"prejudicial|elevada|compromete|limitante|desfavor|letal|t[óo]xic", re.IGNORECASE)


def num(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def txt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x)


def atende(valor: float, vmin: Any, opmin: Any, vmax: Any, opmax: Any) -> bool:
    """Testa o valor contra os limites e operadores registrados."""
    vmin, vmax = num(vmin), num(vmax)
    opmin, opmax = txt(opmin) or ">=", txt(opmax) or "<="
    if vmin is not None:
        if opmin == ">" and not valor > vmin:
            return False
        if opmin == ">=" and not valor >= vmin:
            return False
        if opmin == "=" and not valor == vmin:
            return False
    if vmax is not None:
        if opmax == "<" and not valor < vmax:
            return False
        if opmax == "<=" and not valor <= vmax:
            return False
        if opmax == "=" and not valor == vmax:
            return False
    return vmin is not None or vmax is not None


def fmt_num(v: Any) -> str:
    v = num(v)
    if v is None:
        return ""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def faixa_texto(r: dict) -> str:
    """Representação legível da faixa registrada, preservando operadores."""
    vmin, vmax, v = num(r.get("valor_min")), num(r.get("valor_max")), num(r.get("valor"))
    omin, omax = txt(r.get("operador_min")) or ">=", txt(r.get("operador_max")) or "<="
    if vmin is not None and vmax is not None:
        if vmin == vmax:
            return f"= {fmt_num(vmin)}"
        a = "" if omin == ">=" else "> "
        b = "" if omax == "<=" else " (exclusivo)"
        return f"{a}{fmt_num(vmin)} a {fmt_num(vmax)}{b}"
    if vmin is not None:
        return f"{'≥' if omin == '>=' else '>'} {fmt_num(vmin)}"
    if vmax is not None:
        return f"{'≤' if omax == '<=' else '<'} {fmt_num(vmax)}"
    if v is not None:
        return f"{fmt_num(v)}"
    return ""


# ---------------- condições textuais das faixas (coluna tipo_solo) ----------------
_RX_FAIXA = re.compile(r"^(Argila|P-rem|CTC a pH 7(?:,0)?)\s*(.*?)\s*(%|cmolc/dm3)?$")


def _parse_limites(s: str):
    s = s.strip().replace("≤", "<=").replace("≥", ">=")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    m = re.fullmatch(r"(<=|>=|<|>)\s*([\d.]+)", s)
    if m:
        op, v = m.group(1), float(m.group(2))
        return (None, None, v, op) if op.startswith("<") else (v, op, None, None)
    m = re.fullmatch(r"([\d.]+)\s*a\s*([\d.]+)", s)
    if m:
        return float(m.group(1)), ">=", float(m.group(2)), "<="
    return None


def condicao_do_registro(tipo_solo: Any) -> Optional[dict]:
    """Interpreta a condição de aplicação registrada em tipo_solo.
    Retorna {'variavel': 'argila'|'prem'|'ctc'|'textura', ...} ou None se não houver condição."""
    t = txt(tipo_solo).strip()
    if not t:
        return None
    if t.startswith("Textura "):
        return {"variavel": "textura", "valor": t}
    m = _RX_FAIXA.match(t)
    if m:
        var = {"Argila": "argila", "P-rem": "prem"}.get(m.group(1), "ctc")
        lim = _parse_limites(m.group(2))
        if lim:
            return {"variavel": var, "vmin": lim[0], "opmin": lim[1], "vmax": lim[2], "opmax": lim[3], "texto": t}
    return {"variavel": "outra", "texto": t}


# ---------------- avaliação ----------------
@dataclass
class ResultadoGrupo:
    chave: tuple
    registros: list
    status: str
    classe: str = ""
    faixa: str = ""
    registro_casado: Optional[dict] = None
    motivo: str = ""


@dataclass
class ResultadoParametro:
    status: str
    grupos: list = field(default_factory=list)
    limitacoes: list = field(default_factory=list)
    informativos: list = field(default_factory=list)   # referências não usadas (método não especificado etc.)


def _ordenar(regs: list) -> list:
    def k(r):
        a, b = num(r.get("valor_min")), num(r.get("valor_max"))
        return (a if a is not None else -1e18, b if b is not None else 1e18)
    return sorted(regs, key=k)


def classificar_grupo(valor: float, regs: list) -> ResultadoGrupo:
    """Classifica o valor dentro de um conjunto de classes da mesma tabela/fonte."""
    chave = tuple(regs[0].get(k) for k in ("fonte_id", "secao", "parametro", "metodo", "tipo_solo", "condicoes", "cultura", "camada"))
    # nível crítico (valor único = mínimo adequado segundo a fonte)
    if all(txt(r.get("categoria")) == "nivel_critico" for r in regs):
        r = regs[0]
        nc = num(r.get("valor"))
        st = ADEQUADO if valor >= nc else ABAIXO
        return ResultadoGrupo(chave, regs, st, txt(r.get("classificacao")), f"nível crítico {fmt_num(nc)}", r,
                              "valor ≥ nível crítico" if st == ADEQUADO else "valor abaixo do nível crítico")
    ordenados = _ordenar(regs)
    casados = [r for r in ordenados if atende(valor, r.get("valor_min"), r.get("operador_min"), r.get("valor_max"), r.get("operador_max"))]
    fav = [i for i, r in enumerate(ordenados) if _FAVORAVEL.search(txt(r.get("classificacao")))]

    if len(ordenados) == 1:
        r = ordenados[0]
        rotulo = txt(r.get("classificacao"))
        if _FAVORAVEL.search(rotulo):
            if casados:
                return ResultadoGrupo(chave, regs, ADEQUADO, rotulo, faixa_texto(r), r, "dentro da faixa de referência")
            vmin = num(r.get("valor_min"))
            st = ABAIXO if (vmin is not None and valor < vmin) else ACIMA
            return ResultadoGrupo(chave, regs, st, f"fora de: {rotulo}", faixa_texto(r), r,
                                  "abaixo da faixa de referência" if st == ABAIXO else "acima da faixa de referência")
        if casados:
            st = ATENCAO if _DESFAVORAVEL.search(rotulo) else CLASSE_FONTE
            return ResultadoGrupo(chave, regs, st, rotulo, faixa_texto(r), r, "valor enquadra-se na condição descrita pela fonte")
        return ResultadoGrupo(chave, regs, CLASSE_FONTE, f"fora da condição: {rotulo}", faixa_texto(r), r,
                              "valor não se enquadra na condição descrita; a fonte não define outra classe")

    if not casados:
        return ResultadoGrupo(chave, regs, INSUFICIENTE, "", "", None,
                              "valor entre limites de classes da fonte (lacuna da tabela) — sem classe correspondente")
    status = []
    for r in casados:
        i = ordenados.index(r)
        rot = txt(r.get("classificacao"))
        if not fav:
            status.append(CLASSE_FONTE)
        elif i in fav:
            status.append(ADEQUADO)
        elif i < min(fav):
            status.append(ATENCAO if (i == min(fav) - 1 and _MEDIO.search(rot)) else ABAIXO)
        else:
            status.append(ACIMA)
    r = casados[0]
    if len(set(status)) > 1:
        return ResultadoGrupo(chave, regs, DIVERGENTE, " / ".join(txt(c.get("classificacao")) for c in casados),
                              " | ".join(faixa_texto(c) for c in casados), r,
                              "valor no limite compartilhado por duas classes da própria fonte")
    return ResultadoGrupo(chave, regs, status[0], txt(r.get("classificacao")), faixa_texto(r), r,
                          "classe da fonte" if status[0] == CLASSE_FONTE else "posição em relação à classe adequada da fonte")


def agrupar(regs: Iterable[dict]) -> list:
    grupos: dict = {}
    for r in regs:
        k = tuple(r.get(c) for c in ("fonte_id", "secao", "parametro", "metodo", "tipo_solo", "condicoes", "cultura", "camada", "unidade_base"))
        grupos.setdefault(k, []).append(r)
    return list(grupos.values())


def status_final(grupos: list) -> str:
    sts = [g.status for g in grupos if g.status != INSUFICIENTE]
    if not sts:
        return INSUFICIENTE
    fortes = {s for s in sts if s != CLASSE_FONTE}
    if not fortes:
        return CLASSE_FONTE
    if len(fortes) > 1:
        return DIVERGENTE
    return fortes.pop()
