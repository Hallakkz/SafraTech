"""
Exercícios práticos de cálculo gerados a partir das FÓRMULAS cadastradas nos bancos do SafraTech.

Diferente das questões criadas pela IA, aqui a resposta correta é calculada pelo próprio aplicativo (Python) com a
expressão registrada no banco, e a fórmula é exibida com fonte e página. Os números do enunciado são HIPOTÉTICOS
(sorteados apenas para treino) e isso é dito no enunciado. Se o banco da fórmula estiver indisponível, o exercício
correspondente não é oferecido.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, Optional

from modules.eduagro_ai import knowledge_retrieval as kr

AVISO_HIPOTETICO = "Valores hipotéticos, criados apenas para treino — não são dados de referência."


def br(x: float, casas: int = 2) -> str:
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ler_numero(texto) -> Optional[float]:
    """Aceita '0,85', '0.85', '1.234,5', '85 %', '12,3 @'."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = re.sub(r"[^\d,.\-]", "", str(texto).strip())
    if not t or t in "-.,":
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def confere(resposta: Optional[float], correta: float, tolerancia_rel: float = 0.02, tolerancia_abs: float = 0.0) -> bool:
    if resposta is None:
        return False
    return abs(resposta - correta) <= max(abs(correta) * tolerancia_rel, tolerancia_abs)


@dataclass(frozen=True)
class Gerador:
    codigo: str
    nome: str
    categoria: str               # Agricultura | Pecuária | Gestão Rural
    chave_referencia: str        # chave da Referencia na base dos bancos
    criar: Callable[[random.Random, kr.Referencia], dict]


def _q(enunciado: str, resposta: float, unidade: str, passos: list[str], ref: kr.Referencia, assuntos: list[str],
       casas: int = 2, tol: float = 0.02, tol_abs: float = 0.0) -> dict:
    return {
        "tipo": "pratica", "enunciado": f"{enunciado}\n\n*{AVISO_HIPOTETICO}*",
        "resposta": br(resposta, casas) + (f" {unidade}" if unidade else ""), "resposta_numerica": round(resposta, 6),
        "tolerancia": tol, "tolerancia_abs": tol_abs, "unidade": unidade,
        "explicacao": "**Resolução passo a passo**\n\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(passos, 1)),
        "justificativa": f"Fórmula registrada no banco ({', '.join(ref.bancos)}): **{ref.titulo}**.\n\n{ref.texto}\n\n"
                         f"Fonte: {ref.citacao()}",
        "referencias": [ref.para_dict()], "assuntos": assuntos, "origem": "calculo_banco",
    }


# ------------------------------------------------------------------ pecuária
def _gmd(rng, ref):
    pi = rng.randint(18, 32) * 10
    dias = rng.choice([60, 75, 90, 105, 120, 150])
    gmd = rng.randint(30, 110) / 100
    pf = round(pi + gmd * dias)
    r = (pf - pi) / dias
    return _q(f"Um novilho pesava **{pi} kg** na primeira pesagem e **{pf} kg** na segunda, **{dias} dias** depois. "
              f"Qual foi o ganho médio diário (GMD), em kg/dia?", r, "kg/dia",
              [f"Ganho de peso no período: {pf} − {pi} = {pf - pi} kg",
               f"GMD = ganho ÷ dias = {pf - pi} ÷ {dias} = **{br(r, 3)} kg/dia**"], ref, ["Ganho médio diário (GMD)"], casas=3)


def _rendimento(rng, ref):
    pv = rng.randint(420, 560)
    car = round(pv * rng.randint(500, 560) / 1000, 1)
    r = car / pv * 100
    return _q(f"Um boi foi pesado com **{pv} kg** de peso vivo (após jejum) e gerou **{br(car, 1)} kg** de carcaça "
              f"(soma das meias-carcaças). Qual o rendimento de carcaça, em %?", r, "%",
              [f"Rendimento = peso de carcaça ÷ peso vivo × 100", f"= {br(car, 1)} ÷ {pv} × 100 = **{br(r, 2)} %**"],
              ref, ["Rendimento de carcaça"], tol=0.01)


def _arrobas(rng, ref):
    pv = rng.randint(40, 56) * 10
    rend = rng.choice([50, 51, 52, 53, 54, 55])
    r = pv * rend / 100 / 15
    return _q(f"Um lote será vendido com peso vivo médio de **{pv} kg** por animal. Considere um rendimento de carcaça "
              f"de **{rend} %** para este exercício. Quantas arrobas de carcaça cada animal produz?", r, "@",
              [f"Peso de carcaça = {pv} × {rend}/100 = {br(pv * rend / 100, 1)} kg",
               f"Arrobas = peso de carcaça ÷ 15 kg = {br(pv * rend / 100, 1)} ÷ 15 = **{br(r, 2)} @**",
               "Atenção: arroba de carcaça (15 kg) não é o mesmo que 15 kg de peso vivo."], ref, ["Arroba de carcaça"])


def _peso_projetado(rng, ref):
    pa = rng.randint(28, 42) * 10
    gmd = rng.randint(40, 100) / 100
    dias = rng.choice([60, 90, 120])
    r = pa + gmd * dias
    return _q(f"Um animal pesa **{pa} kg** hoje. Se mantiver um GMD de **{br(gmd, 2)} kg/dia** (premissa do exercício) "
              f"por **{dias} dias**, qual será o peso projetado?", r, "kg",
              [f"Ganho no período = {br(gmd, 2)} × {dias} = {br(gmd * dias, 1)} kg",
               f"Peso projetado = {pa} + {br(gmd * dias, 1)} = **{br(r, 1)} kg**"], ref, ["Projeção de peso"], casas=1)


def _ua(rng, ref):
    n = rng.randint(2, 12) * 10
    pv = rng.randint(25, 45) * 10
    r = n * pv / 450
    return _q(f"Uma pastagem recebe **{n} novilhos** com peso vivo médio de **{pv} kg**. Quantas unidades animais (UA) "
              f"esse lote representa?", r, "UA",
              [f"UA por animal = {pv} ÷ 450 = {br(pv / 450, 3)}", f"UA do lote = {n} × {br(pv / 450, 3)} = **{br(r, 1)} UA**"],
              ref, ["Unidade animal"], casas=1)


def _prenhez(rng, ref):
    exp = rng.randint(8, 30) * 10
    pren = round(exp * rng.randint(55, 92) / 100)
    r = pren / exp * 100
    return _q(f"Na estação de monta, **{exp} vacas** foram expostas ao touro e **{pren}** foram diagnosticadas prenhes. "
              f"Qual a taxa de prenhez?", r, "%", [f"Taxa de prenhez = prenhes ÷ expostas × 100 = {pren} ÷ {exp} × 100 = **{br(r, 1)} %**"],
              ref, ["Taxa de prenhez"], casas=1, tol=0.01)


def _mortalidade(rng, ref):
    tot = rng.randint(10, 60) * 10
    mortos = rng.randint(2, max(3, tot // 25))
    r = mortos / tot * 100
    return _q(f"Um rebanho com **{tot} animais** teve **{mortos} mortes** no ano. Qual a taxa de mortalidade?", r, "%",
              [f"Taxa de mortalidade = mortos ÷ total × 100 = {mortos} ÷ {tot} × 100 = **{br(r, 2)} %**"], ref,
              ["Taxa de mortalidade"], tol=0.01)


def _margem_bruta(rng, ref):
    receita = rng.randint(30, 120) * 10000
    desemb = round(receita * rng.randint(45, 95) / 100, -2)
    r = receita - desemb
    return _q(f"No ano, uma fazenda de recria teve receita total de **R$ {br(receita, 0)}** e desembolsos (custo operacional "
              f"efetivo) de **R$ {br(desemb, 0)}**. Qual foi a margem bruta?", r, "R$",
              [f"Margem bruta = receita − desembolsos = {br(receita, 0)} − {br(desemb, 0)} = **R$ {br(r, 0)}**"], ref,
              ["Margem bruta"], casas=0, tol=0.0, tol_abs=1)


# ------------------------------------------------------------------ solo
def _soma_bases(rng, ref):
    ca, mg, k = rng.randint(10, 50) / 10, rng.randint(3, 15) / 10, rng.randint(5, 40) / 100
    r = ca + mg + k
    return _q(f"Um laudo de análise de solo apresentou Ca = **{br(ca, 1)}**, Mg = **{br(mg, 1)}** e K = **{br(k, 2)} cmolc/dm³**. "
              f"Calcule a soma de bases (S).", r, "cmolc/dm³", [f"S = Ca + Mg + K = {br(ca, 1)} + {br(mg, 1)} + {br(k, 2)} = **{br(r, 2)} cmolc/dm³**"],
              ref, ["Soma de bases"], tol=0.01)


def _ctc(rng, ref):
    s, hal = rng.randint(15, 60) / 10, rng.randint(15, 70) / 10
    r = s + hal
    return _q(f"Um solo tem soma de bases S = **{br(s, 1)} cmolc/dm³** e acidez potencial H+Al = **{br(hal, 1)} cmolc/dm³**. "
              f"Qual a CTC a pH 7?", r, "cmolc/dm³", [f"CTC = S + (H + Al) = {br(s, 1)} + {br(hal, 1)} = **{br(r, 1)} cmolc/dm³**"],
              ref, ["CTC a pH 7"], casas=1, tol=0.01)


def _v(rng, ref):
    ca, mg, k = rng.randint(10, 45) / 10, rng.randint(3, 12) / 10, rng.randint(8, 35) / 100
    hal = rng.randint(20, 60) / 10
    s = ca + mg + k
    ctc = s + hal
    r = s / ctc * 100
    return _q(f"Laudo de solo: Ca = **{br(ca, 1)}**, Mg = **{br(mg, 1)}**, K = **{br(k, 2)}** e H+Al = **{br(hal, 1)} cmolc/dm³**. "
              f"Calcule a saturação por bases (V%).", r, "%",
              [f"S = Ca + Mg + K = {br(s, 2)} cmolc/dm³", f"CTC (T) = S + H+Al = {br(s, 2)} + {br(hal, 1)} = {br(ctc, 2)} cmolc/dm³",
               f"V% = S ÷ CTC × 100 = {br(s, 2)} ÷ {br(ctc, 2)} × 100 = **{br(r, 1)} %**"], ref, ["Saturação por bases"],
              casas=1, tol=0.015)


def _gesso(rng, ref):
    arg = rng.randint(15, 65)
    r = 50 * arg
    return _q(f"Para uma área de culturas anuais em que o critério de indicação de gesso foi atendido, o teor de argila é "
              f"**{arg} %**. Pela equação do banco, qual a dose de gesso?", r, "kg/ha",
              [f"D.G. = 50 × argila (%) = 50 × {arg} = **{br(r, 0)} kg/ha**"], ref, ["Gessagem"], casas=0, tol=0.0, tol_abs=1)


GERADORES: tuple[Gerador, ...] = (
    Gerador("GMD", "Ganho médio diário (GMD)", "Pecuária", "pec:formula:GMD", _gmd),
    Gerador("RENDIMENTO", "Rendimento de carcaça", "Pecuária", "pec:formula:RENDIMENTO_CARCACA", _rendimento),
    Gerador("ARROBAS", "Arrobas de carcaça a partir do peso vivo", "Pecuária", "pec:formula:ARROBAS_CARCACA_DE_PESO_VIVO", _arrobas),
    Gerador("PESO_PROJ", "Peso projetado", "Pecuária", "pec:formula:PESO_PROJETADO", _peso_projetado),
    Gerador("UA", "Unidade animal (UA)", "Pecuária", "pec:formula:UNIDADE_ANIMAL", _ua),
    Gerador("PRENHEZ", "Taxa de prenhez", "Pecuária", "pec:formula:TAXA_PRENHEZ", _prenhez),
    Gerador("MORTALIDADE", "Taxa de mortalidade", "Pecuária", "pec:formula:TAXA_MORTALIDADE", _mortalidade),
    Gerador("MARGEM_BRUTA", "Margem bruta", "Gestão Rural", "pec:formula:MARGEM_BRUTA", _margem_bruta),
    Gerador("SOMA_BASES", "Soma de bases (S)", "Agricultura", "solo_database:SOL-000215", _soma_bases),
    Gerador("CTC", "CTC a pH 7", "Agricultura", "solo_database:SOL-000216", _ctc),
    Gerador("V", "Saturação por bases (V%)", "Agricultura", "solo_database:SOL-000217", _v),
    Gerador("GESSO", "Dose de gesso (culturas anuais)", "Agricultura", "solo_database:SOL-000318", _gesso),
)


def referencia(chave: str) -> Optional[kr.Referencia]:
    base = kr.carregar_base_bancos()
    return next((r for r in base.indice.itens if r.chave == chave), None)


def disponiveis() -> list[Gerador]:
    """Somente geradores cuja fórmula foi encontrada nos bancos acessíveis."""
    base = kr.carregar_base_bancos()
    chaves = {r.chave for r in base.indice.itens}
    return [g for g in GERADORES if g.chave_referencia in chaves]


def gerar(codigo: str, semente: Optional[int] = None) -> dict:
    g = next((x for x in GERADORES if x.codigo == codigo), None)
    if g is None:
        raise KeyError(codigo)
    ref = referencia(g.chave_referencia)
    if ref is None:
        raise LookupError(f"A fórmula de “{g.nome}” não está disponível (banco de origem inacessível).")
    rng = random.Random(semente)
    q = g.criar(rng, ref)
    q.update(tema=g.nome, categoria=g.categoria, gerador=g.codigo)
    return q
