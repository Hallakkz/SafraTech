"""
Cálculos da Pecuária de Corte do SafraTech (funções puras, sem Streamlit e sem acesso a banco).

As expressões reproduzem exatamente as views dos bancos de pecuária (02_criar_views.sql) e as fórmulas
registradas em `formula_calculo`:

* ARROBAS_CARCACA_DE_PESO_VIVO (F05, p.21):  arrobas = peso_vivo_kg × (rendimento_pct / 100) / 15
* RENDIMENTO_CARCACA (F07, p.4):             rendimento_pct = peso_carcaca_kg / peso_vivo_kg × 100
* PESO_VIVO_DE_ARROBAS_CARCACA (F01, p.231): peso_vivo_kg = arrobas × 15 / (rendimento_pct / 100)
* GMD (F08):                                 gmd = (peso_final − peso_inicial) / dias
* PESO_PROJETADO:                            peso_projetado = peso_atual + gmd × dias
* LUCRO / MARGEM_OPERACIONAL (F05, p.26):    receita − custo
* vw_lote_compra_resumo / vw_lote_compra_viabilidade  → analisar_compra()
* vw_gmd_lote                                          → gmd()
* vw_projecao_cenario / vw_comparativo_cenarios        → projetar_cenario()

Regras: 1 arroba comercial = 15 kg de CARCAÇA. Peso vivo só vira arroba com um rendimento de carcaça
informado pelo usuário ou vindo de uma referência identificada — nunca há rendimento fixo.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Sequence

KG_POR_ARROBA = 15.0          # arroba comercial de carcaça (F01, F04, F05, F06; ver DIV-09)
DIAS_POR_MES = 30.4375        # 365,25 / 12 — usado só para converter idades citadas em dias (ex.: PC205)


class DadosInvalidos(ValueError):
    """Entrada incompleta ou fora dos limites físicos/econômicos aceitáveis."""


# =====================================================================================================
# Conversões básicas
# =====================================================================================================
def _positivo(nome: str, v: Optional[float], permitir_zero: bool = False) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        raise DadosInvalidos(f"Informe {nome}.")
    v = float(v)
    if v < 0 or (v == 0 and not permitir_zero):
        raise DadosInvalidos(f"{nome[0].upper() + nome[1:]} deve ser maior que zero.")
    return v


def validar_rendimento(rendimento_pct: Optional[float]) -> float:
    r = _positivo("o rendimento de carcaça (%)", rendimento_pct)
    if not 0 < r < 100:
        raise DadosInvalidos("O rendimento de carcaça deve estar entre 0% e 100% do peso vivo.")
    return r


def peso_carcaca_kg(peso_vivo_kg: float, rendimento_pct: float) -> float:
    """Peso de carcaça = peso vivo × rendimento."""
    return _positivo("o peso vivo", peso_vivo_kg) * validar_rendimento(rendimento_pct) / 100.0


def arrobas_de_peso_vivo(peso_vivo_kg: float, rendimento_pct: float) -> float:
    """ARROBAS_CARCACA_DE_PESO_VIVO: arrobas de carcaça = peso vivo × (rendimento/100) / 15."""
    return peso_carcaca_kg(peso_vivo_kg, rendimento_pct) / KG_POR_ARROBA


def peso_vivo_de_arrobas(arrobas: float, rendimento_pct: float) -> float:
    """PESO_VIVO_DE_ARROBAS_CARCACA: peso vivo = arrobas × 15 / (rendimento/100)."""
    return _positivo("as arrobas", arrobas) * KG_POR_ARROBA / (validar_rendimento(rendimento_pct) / 100.0)


def rendimento_carcaca_pct(peso_carcaca: float, peso_vivo: float) -> float:
    """RENDIMENTO_CARCACA: peso de carcaça / peso vivo × 100."""
    return _positivo("o peso de carcaça", peso_carcaca) / _positivo("o peso vivo", peso_vivo) * 100.0


def margem_pct(resultado: float, receita: float) -> Optional[float]:
    return resultado / receita * 100.0 if receita else None


# =====================================================================================================
# Módulo 1 — Viabilidade de compra (vw_lote_compra_resumo + vw_lote_compra_viabilidade)
# =====================================================================================================
BASES_CUSTO = {
    "brl_total": "R$ por lote",
    "brl_cab": "R$ por cabeça",
    "brl_cab_dia": "R$ por cabeça por dia",
}


@dataclass
class CustoAdicional:
    tipo: str
    valor: float
    base: str  # brl_total | brl_cab | brl_cab_dia (mesmos códigos de lote_compra_custo_adicional.base_valor)
    descricao: str = ""

    def total(self, quantidade: int, dias: Optional[int]) -> float:
        if self.base == "brl_total":
            return float(self.valor)
        if self.base == "brl_cab":
            return float(self.valor) * quantidade
        if self.base == "brl_cab_dia":
            return float(self.valor) * quantidade * float(dias or 0)   # COALESCE(c.dias, 0) na view
        raise DadosInvalidos(f"Base de custo desconhecida: {self.base}")


@dataclass
class EntradaCompra:
    quantidade_animais: int
    peso_medio_compra_kg: float
    modo_preco: str                      # "cabeca" | "lote"
    preco_compra: float                  # R$/cab ou R$ do lote, conforme modo_preco
    peso_venda_kg: float                 # peso vivo médio previsto na venda
    rendimento_venda_pct: float          # informado ou de referência identificada
    preco_venda_arroba: float            # R$/@ de carcaça informado pelo produtor
    dias_permanencia: Optional[int] = None
    custos: list[CustoAdicional] = field(default_factory=list)
    margem_minima_pct: Optional[float] = None


@dataclass
class ResultadoCompra:
    entrada: EntradaCompra
    peso_total_compra_kg: float
    peso_total_venda_kg: float
    custo_aquisicao_lote: float          # investimento inicial
    custo_aquisicao_cab: float
    custo_adicional_total: float
    custos_detalhados: list[tuple[str, float]]
    custo_total_lote: float
    peso_carcaca_cab_kg: float
    peso_carcaca_lote_kg: float
    arrobas_carcaca_cab: float
    arrobas_carcaca_lote: float
    receita_bruta: float
    receita_liquida: float               # receita bruta − custos adicionais
    lucro: float                         # receita bruta − custo total (= receita líquida − aquisição)
    margem_lucro_pct: Optional[float]
    retorno_sobre_custo_pct: Optional[float]
    preco_equilibrio_arroba: Optional[float]
    rendimento_equilibrio_pct: Optional[float]
    peso_venda_equilibrio_kg: Optional[float]
    margem_seguranca_preco_pct: Optional[float]
    ganho_peso_cab_kg: float
    gmd_implicito_kg_dia: Optional[float]
    custo_por_arroba_vendida: Optional[float]
    classificacao: str                   # viavel | atencao | inviavel
    sensibilidade: list[dict]


def analisar_compra(e: EntradaCompra) -> ResultadoCompra:
    q = int(_positivo("a quantidade de animais", e.quantidade_animais))
    peso_compra = _positivo("o peso médio na compra", e.peso_medio_compra_kg)
    peso_venda = _positivo("o peso médio previsto na venda", e.peso_venda_kg)
    rend = validar_rendimento(e.rendimento_venda_pct)
    preco_arroba = _positivo("o valor da arroba de venda", e.preco_venda_arroba)
    if e.modo_preco not in ("cabeca", "lote"):
        raise DadosInvalidos("Escolha se o preço de compra é por cabeça ou do lote inteiro.")
    preco = _positivo("o preço de compra", e.preco_compra)
    dias = int(e.dias_permanencia) if e.dias_permanencia else None
    if any(c.base == "brl_cab_dia" and c.valor for c in e.custos) and not dias:
        raise DadosInvalidos("Informe os dias de permanência para calcular custos por cabeça por dia.")

    # vw_lote_compra_resumo: custo de aquisição (só uma forma de preço é contabilizada)
    custo_aquisicao = preco * q if e.modo_preco == "cabeca" else preco
    detalhes = [(c.descricao or c.tipo, c.total(q, dias)) for c in e.custos if c.valor]
    if any(v < 0 for _, v in detalhes):
        raise DadosInvalidos("Custos adicionais não podem ser negativos.")
    adicional = sum(v for _, v in detalhes)
    custo_total = custo_aquisicao + adicional

    # vw_lote_compra_viabilidade
    arrobas_cab = peso_venda * rend / 100.0 / KG_POR_ARROBA
    arrobas_lote = arrobas_cab * q
    receita = arrobas_lote * preco_arroba
    lucro = receita - custo_total
    margem = lucro / receita * 100.0 if preco_arroba > 0 and receita else None
    retorno = lucro / custo_total * 100.0 if custo_total else None
    preco_eq = custo_total / arrobas_lote if arrobas_lote else None
    rend_eq = custo_total / (peso_venda * q * preco_arroba / KG_POR_ARROBA) * 100.0
    peso_eq = custo_total / (q * rend / 100.0 / KG_POR_ARROBA * preco_arroba)
    seg = (preco_arroba - preco_eq) / preco_arroba * 100.0 if preco_eq is not None else None

    ganho = peso_venda - peso_compra
    gmd = ganho / dias if dias else None

    if lucro <= 0:
        classe = "inviavel"
    elif e.margem_minima_pct is not None and margem is not None and margem < float(e.margem_minima_pct):
        classe = "atencao"
    else:
        classe = "viavel"

    # Sensibilidade: efeito de uma variação desfavorável de 1% em cada premissa (relação linear)
    sens = [
        {"fator": "Valor da arroba de venda", "impacto_lucro": -0.01 * receita},
        {"fator": "Rendimento de carcaça", "impacto_lucro": -0.01 * receita},
        {"fator": "Peso de venda", "impacto_lucro": -0.01 * receita},
        {"fator": "Preço de compra do lote", "impacto_lucro": -0.01 * custo_aquisicao},
        {"fator": "Custos adicionais", "impacto_lucro": -0.01 * adicional},
    ]
    sens.sort(key=lambda d: d["impacto_lucro"])

    return ResultadoCompra(
        entrada=e, peso_total_compra_kg=peso_compra * q, peso_total_venda_kg=peso_venda * q,
        custo_aquisicao_lote=custo_aquisicao, custo_aquisicao_cab=custo_aquisicao / q,
        custo_adicional_total=adicional, custos_detalhados=detalhes, custo_total_lote=custo_total,
        peso_carcaca_cab_kg=peso_venda * rend / 100.0, peso_carcaca_lote_kg=peso_venda * rend / 100.0 * q,
        arrobas_carcaca_cab=arrobas_cab, arrobas_carcaca_lote=arrobas_lote, receita_bruta=receita,
        receita_liquida=receita - adicional, lucro=lucro, margem_lucro_pct=margem, retorno_sobre_custo_pct=retorno,
        preco_equilibrio_arroba=preco_eq, rendimento_equilibrio_pct=rend_eq, peso_venda_equilibrio_kg=peso_eq,
        margem_seguranca_preco_pct=seg, ganho_peso_cab_kg=ganho, gmd_implicito_kg_dia=gmd,
        custo_por_arroba_vendida=custo_total / arrobas_lote if arrobas_lote else None,
        classificacao=classe, sensibilidade=sens,
    )


def fatores_compra(r: ResultadoCompra) -> list[str]:
    """Explicação, em texto, dos fatores que mais influenciaram o resultado (derivada dos próprios cálculos)."""
    f = []
    part_aq = r.custo_aquisicao_lote / r.custo_total_lote * 100 if r.custo_total_lote else 0
    f.append(f"A aquisição dos animais representa {_br(part_aq, 1)}% do custo total do lote"
             + (f"; os custos adicionais, {_br(100 - part_aq, 1)}%." if r.custo_adicional_total else "; não foram informados custos adicionais."))
    if r.preco_equilibrio_arroba is not None:
        rel = "acima" if r.entrada.preco_venda_arroba >= r.preco_equilibrio_arroba else "abaixo"
        f.append(f"Para cobrir todos os custos, a arroba precisaria valer R$ {_br(r.preco_equilibrio_arroba)}; o valor "
                 f"informado (R$ {_br(r.entrada.preco_venda_arroba)}) está {rel} desse ponto de equilíbrio "
                 f"({_br(abs(r.margem_seguranca_preco_pct or 0), 1)}% de {'folga' if rel == 'acima' else 'déficit'}).")
    if r.rendimento_equilibrio_pct is not None:
        f.append(f"Com os demais dados mantidos, o rendimento de carcaça de equilíbrio é {_br(r.rendimento_equilibrio_pct, 1)}% "
                 f"(premissa usada: {_br(r.entrada.rendimento_venda_pct, 1)}%).")
    if r.peso_venda_equilibrio_kg is not None:
        f.append(f"O peso de venda mínimo para não ter prejuízo é {_br(r.peso_venda_equilibrio_kg, 0)} kg por cabeça "
                 f"(premissa usada: {_br(r.entrada.peso_venda_kg, 0)} kg; ganho previsto de {_br(r.ganho_peso_cab_kg, 0)} kg/cab).")
    imp = {s["fator"]: abs(s["impacto_lucro"]) for s in r.sensibilidade}
    receita_1 = imp["Valor da arroba de venda"]
    principal = ("às premissas de venda (arroba, rendimento e peso)" if receita_1 >= imp["Preço de compra do lote"]
                 else "ao preço de compra do lote")
    f.append(f"Sensibilidade: cada 1% desfavorável no valor da arroba, no rendimento de carcaça ou no peso de venda reduz o "
             f"lucro em R$ {_br(receita_1)}; 1% a mais no preço de compra, em R$ {_br(imp['Preço de compra do lote'])}"
             + (f"; 1% a mais nos custos adicionais, em R$ {_br(imp['Custos adicionais'])}" if r.custo_adicional_total else "")
             + f". O resultado é mais sensível a {principal}.")
    return f


# =====================================================================================================
# Módulo 2 — Desempenho do rebanho (vw_gmd_lote + vw_gmd_lote_x_referencia)
# =====================================================================================================
SEXOS_USUARIO = {"macho_inteiro": "Macho inteiro", "macho_castrado": "Macho castrado", "femea": "Fêmea"}
# Códigos de sexo das referências considerados compatíveis com o sexo informado.
# 'macho' = fonte não informa a condição sexual (inteiro/castrado) — compatível, mas sinalizado.
SEXO_COMPATIVEL = {
    "macho_inteiro": {"macho_inteiro": "mesmo sexo e condição sexual", "macho": "macho (a fonte não informa se inteiro ou castrado)",
                      "touro": "touro (macho inteiro)"},
    "macho_castrado": {"macho_castrado": "mesmo sexo e condição sexual", "macho": "macho (a fonte não informa se inteiro ou castrado)"},
    "femea": {"femea": "mesmo sexo"},
}
FASES_USUARIO = {"": "Não informada", "pre_desmama": "Cria (pré-desmama)", "recria": "Recria",
                 "terminacao": "Terminação/engorda", "recria_terminacao": "Recria e terminação"}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def gmd(peso_inicial: float, peso_final: float, data_inicial: date, data_final: date) -> tuple[float, int]:
    """GMD = (peso_final − peso_inicial) / dias, como em vw_gmd_lote. Retorna (gmd_kg_dia, dias)."""
    p0 = _positivo("o peso anterior", peso_inicial)
    p1 = _positivo("o peso atual", peso_final)
    if data_inicial is None or data_final is None:
        raise DadosInvalidos("Informe as datas das duas pesagens.")
    dias = (data_final - data_inicial).days
    if dias <= 0:
        raise DadosInvalidos("A data da pesagem atual deve ser posterior à da pesagem anterior.")
    return (p1 - p0) / dias, dias


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def idade_referencia_meses(parametro: str) -> Optional[tuple[float, float]]:
    """Idade (meses) explícita no texto do parâmetro da fonte, como intervalo (mín, máx).

    Só usa o texto do parâmetro (ex.: 'Peso aos 12 meses', 'Peso corrigido para 205 dias', 'Machos 1-2 anos',
    'Peso ao nascimento'). Não usa idade_fase, que pode descrever tratamentos (ex.: idade de castração).
    Retorna None quando a fonte não informa a idade."""
    t = _sem_acento(parametro)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[-–a]\s*(\d+(?:[.,]\d+)?)\s*anos", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 12, float(m.group(2).replace(",", ".")) * 12
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*meses", t)
    if m:
        return float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    m = re.search(r"\baos?\s+(\d+(?:[.,]\d+)?)\s*meses", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        return v, v
    m = re.search(r"\baos?\s+(\d+(?:[.,]\d+)?)\s*anos", t)
    if m:
        v = float(m.group(1).replace(",", ".")) * 12
        return v, v
    m = re.search(r"\b(?:para|aos?)\s+(\d+)\s*dias", t)
    if m:
        v = round(float(m.group(1)) / DIAS_POR_MES, 1)
        return v, v
    if re.search(r"\bao nascimento\b", t):
        return 0.0, 0.0
    return None


def janela_gmd_meses(parametro: str) -> Optional[tuple[float, float]]:
    """Período de idade a que um GMD se refere, quando explícito ('dos 18 aos 20 meses', 'do nascimento aos 18 meses').
    'nascimento ao abate' devolve None (média da vida inteira, comparável só em fase de ciclo completo)."""
    t = _sem_acento(parametro)
    m = re.search(r"dos?\s+(\d+)\s+aos?\s+(\d+)\s*meses", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"do nascimento aos?\s+(\d+)\s*meses", t)
    if m:
        return 0.0, float(m.group(1))
    return None


def mes_referencia(parametro: str) -> Optional[int]:
    t = _sem_acento(parametro)
    for i, nome in enumerate(MESES, start=1):
        if re.search(rf"\b{_sem_acento(nome)}\b", t):
            return i
    return None


def meses_do_periodo(d0: date, d1: date) -> set[int]:
    meses, a, m = set(), d0.year, d0.month
    while (a, m) <= (d1.year, d1.month):
        meses.add(m)
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return meses


def _num(v) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


@dataclass
class Comparacao:
    id_registro: str
    parametro: str
    valor_ref: Optional[float]
    ref_min: Optional[float]
    ref_max: Optional[float]
    observado: float
    diferenca: Optional[float]
    diferenca_pct: Optional[float]
    status: str                  # abaixo | adequado | acima
    justificativa: str           # por que a referência é compatível
    registro: dict


@dataclass
class NaoUsada:
    id_registro: str
    parametro: str
    motivo: str
    registro: dict


def _status_valor(obs: float, ref: Optional[float], rmin: Optional[float], rmax: Optional[float], tol_pct: float):
    if rmin is not None or rmax is not None:
        lo = rmin if rmin is not None else -math.inf
        hi = rmax if rmax is not None else math.inf
        if obs < lo:
            return "abaixo", obs - lo, (obs - lo) / lo * 100 if lo not in (0, -math.inf) else None
        if obs > hi:
            return "acima", obs - hi, (obs - hi) / hi * 100 if hi not in (0, math.inf) else None
        return "adequado", 0.0, 0.0
    dif = obs - ref
    pct = dif / abs(ref) * 100 if ref else None
    if pct is None:   # referência zero: compara pelo sinal
        return ("abaixo" if dif < 0 else "acima" if dif > 0 else "adequado"), dif, None
    if pct < -tol_pct:
        return "abaixo", dif, pct
    if pct > tol_pct:
        return "acima", dif, pct
    return "adequado", dif, pct


def _compat_base(r: dict, raca: str, sexo: str, sistema: str) -> tuple[Optional[str], list[str]]:
    """Regras comuns: mesma raça/genótipo (sem misturar Nelore puro, comercial, nelorado e cruzados),
    sexo compatível e mesmo sistema de criação. Retorna (motivo_de_exclusão | None, justificativas)."""
    just = []
    if r.get("raca_codigo") != raca:
        return f"raça/genótipo diferente ({r.get('raca')})", just
    just.append(f"mesma raça/genótipo ({r.get('raca')})")
    sx = SEXO_COMPATIVEL.get(sexo, {})
    if r.get("sexo") not in sx:
        return f"sexo/categoria diferente ou não especificado pela fonte ({r.get('sexo')})", just
    just.append(sx[r.get("sexo")])
    if r.get("sistema_codigo") != sistema:
        return f"sistema de criação diferente ({r.get('sistema')})", just
    just.append(f"mesmo sistema ({r.get('sistema')})")
    return None, just


def comparar_peso(referencias: Iterable[dict], raca: str, sexo: str, sistema: str, idade_meses: float, peso_kg: float,
                  tolerancia_idade_meses: float = 1.0, tolerancia_pct: float = 10.0
                  ) -> tuple[list[Comparacao], list[NaoUsada]]:
    usadas, nao = [], []
    for r in referencias:
        motivo, just = _compat_base(r, raca, sexo, sistema)
        if motivo is None:
            faixa = idade_referencia_meses(r.get("parametro", ""))
            if faixa is None:
                motivo = "a fonte não informa a idade dos animais"
            elif not (faixa[0] - tolerancia_idade_meses <= idade_meses <= faixa[1] + tolerancia_idade_meses):
                motivo = f"idade diferente (referência: {_faixa_txt(faixa)})"
            else:
                just.append(f"idade compatível (referência: {_faixa_txt(faixa)}; tolerância ±{_br(tolerancia_idade_meses, 1)} mês)")
        ref, rmin, rmax = _num(r.get("valor_numerico")), _num(r.get("valor_min")), _num(r.get("valor_max"))
        if motivo is None and ref is None and rmin is None and rmax is None:
            motivo = "sem valor numérico"
        if motivo:
            nao.append(NaoUsada(r.get("id_registro"), r.get("parametro"), motivo, r))
            continue
        stt, dif, pct = _status_valor(peso_kg, ref, rmin, rmax, tolerancia_pct)
        usadas.append(Comparacao(r.get("id_registro"), r.get("parametro"), ref, rmin, rmax, peso_kg, dif, pct, stt,
                                 "; ".join(just), r))
    return usadas, nao


def comparar_gmd(referencias: Iterable[dict], raca: str, sexo: str, sistema: str, fase: str, idade_meses: float,
                 gmd_obs: float, d0: date, d1: date, tolerancia_idade_meses: float = 1.0, tolerancia_pct: float = 10.0
                 ) -> tuple[list[Comparacao], list[NaoUsada]]:
    """Compatibilidade como em vw_gmd_lote_x_referencia (mesma raça; flags mesmo_sexo, mesmo_sistema, mesma_fase),
    exigindo as três condições, mais: o período entre as pesagens precisa estar dentro do período de idade da
    referência (quando a fonte o define) e incluir o mês da referência (quando o GMD é mensal)."""
    meses = meses_do_periodo(d0, d1)
    idade_inicio = idade_meses - (d1 - d0).days / DIAS_POR_MES     # idade na pesagem anterior
    usadas, nao = [], []
    for r in referencias:
        motivo, just = _compat_base(r, raca, sexo, sistema)
        if motivo is None:
            if not fase:
                motivo = "fase produtiva não informada (o GMD varia muito entre cria, recria e terminação)"
            elif r.get("fase") != fase:
                motivo = f"fase produtiva diferente ({r.get('fase')})"
            else:
                just.append(f"mesma fase ({FASES_USUARIO.get(fase, fase)})")
        if motivo is None:
            jan = janela_gmd_meses(r.get("parametro", ""))
            if jan and not (jan[0] - tolerancia_idade_meses <= idade_inicio and idade_meses <= jan[1] + tolerancia_idade_meses):
                motivo = (f"período de idade diferente (referência: {_faixa_txt(jan)}; pesagens: "
                          f"{_faixa_txt((round(idade_inicio, 1), round(idade_meses, 1)))})")
            elif jan:
                just.append(f"período entre as pesagens dentro do período de idade da referência ({_faixa_txt(jan)})")
        if motivo is None:
            mes = mes_referencia(r.get("parametro", ""))
            if mes and mes not in meses:
                motivo = f"referência do mês de {MESES[mes - 1]}, fora do período entre as pesagens"
            elif mes:
                just.append(f"mês de {MESES[mes - 1]} dentro do período entre as pesagens")
        ref = _num(r.get("gmd_kg_dia"))
        rmin, rmax = _num(r.get("gmd_min_kg_dia")), _num(r.get("gmd_max_kg_dia"))
        if motivo is None and ref is None and rmin is None and rmax is None:
            motivo = "sem valor numérico"
        if motivo:
            nao.append(NaoUsada(r.get("id_registro"), r.get("parametro"), motivo, r))
            continue
        stt, dif, pct = _status_valor(gmd_obs, ref, rmin, rmax, tolerancia_pct)
        usadas.append(Comparacao(r.get("id_registro"), r.get("parametro"), ref, rmin, rmax, gmd_obs, dif, pct, stt,
                                 "; ".join(just), r))
    return usadas, nao


def resumo_status(comparacoes: Sequence[Comparacao]) -> str:
    """insuficiente (nenhuma referência compatível) | abaixo | adequado | acima | divergente (referências discordam)."""
    if not comparacoes:
        return "insuficiente"
    st = {c.status for c in comparacoes}
    return st.pop() if len(st) == 1 else "divergente"


def pontos_de_atencao(peso_cmp: Sequence[Comparacao], gmd_cmp: Sequence[Comparacao], gmd_obs: Optional[float],
                      ganho_kg: Optional[float]) -> list[str]:
    p = []
    if gmd_obs is not None and gmd_obs < 0:
        p.append(f"O animal/lote PERDEU peso entre as pesagens ({_br(ganho_kg, 1)} kg; GMD {_br(gmd_obs, 3)} kg/dia).")
    for c in peso_cmp:
        if c.status == "abaixo":
            p.append(f"Peso abaixo da referência '{c.parametro}' ({c.id_registro}): {_br(c.diferenca, 1)} kg "
                     f"({_br(c.diferenca_pct, 1)}%).")
    for c in gmd_cmp:
        if c.status == "abaixo":
            p.append(f"GMD abaixo da referência '{c.parametro}' ({c.id_registro}): {_br(c.diferenca, 3)} kg/dia.")
    if not peso_cmp:
        p.append("Não há referência de peso compatível (raça, sexo, sistema e idade) no banco: dados insuficientes para "
                 "avaliar o peso — nenhum peso esperado foi estimado.")
    if gmd_obs is not None and not gmd_cmp:
        p.append("Não há referência de GMD compatível (raça, sexo, sistema e fase) no banco: dados insuficientes para "
                 "avaliar o ganho diário.")
    return p


# =====================================================================================================
# Módulo 3 — Rentabilidade: vender agora x esperar (vw_projecao_cenario + vw_comparativo_cenarios)
# =====================================================================================================
TIPOS_CENARIO = {"conservador": "Conservador", "intermediario": "Intermediário", "otimista": "Otimista"}
TIPOS_CUSTO = {"alimentacao": "Alimentação", "suplementacao": "Suplementação", "manejo": "Manejo", "outros": "Outros"}


@dataclass
class Cenario:
    tipo: str                       # conservador | intermediario | otimista
    preco_arroba_futuro: float      # R$/@ na venda após o período (premissa do usuário)
    gmd_kg_dia: float
    rendimento_futuro_pct: float
    custos_cab_dia: dict            # {alimentacao, suplementacao, manejo, outros}: R$/cab/dia


@dataclass
class EntradaRentabilidade:
    quantidade_animais: int
    peso_atual_kg: float
    preco_arroba_atual: float
    rendimento_atual_pct: float
    dias: int
    custo_acumulado_brl: float = 0.0


@dataclass
class ResultadoCenario:
    cenario: Cenario
    peso_atual_rebanho_kg: float
    peso_projetado_cab_kg: float
    peso_projetado_rebanho_kg: float
    ganho_cab_kg: float
    ganho_rebanho_kg: float
    arrobas_atual_cab: float
    arrobas_futuro_cab: float
    arrobas_atual_lote: float
    arrobas_futuro_lote: float
    arrobas_produzidas: float
    receita_vender_agora: float
    receita_vender_depois: float
    custo_diario_cab: float
    custo_adicional_espera: float
    custo_acumulado_total_depois: float
    receita_liquida_depois: float
    margem_operacional_agora: float
    margem_operacional_depois: float
    margem_operacional_agora_pct: Optional[float]
    margem_operacional_depois_pct: Optional[float]
    resultado_incremental: float
    custo_por_arroba_produzida: Optional[float]
    preco_equilibrio_futuro: Optional[float]
    indicacao: str                 # esperar | vender agora | indiferente


def projetar_cenario(e: EntradaRentabilidade, c: Cenario) -> ResultadoCenario:
    q = int(_positivo("a quantidade de animais", e.quantidade_animais))
    p0 = _positivo("o peso médio atual", e.peso_atual_kg)
    pa = _positivo("o valor atual da arroba", e.preco_arroba_atual)
    ra = validar_rendimento(e.rendimento_atual_pct)
    dias = int(_positivo("o período de simulação (dias)", e.dias))
    acum = _positivo("o custo já acumulado", e.custo_acumulado_brl or 0.0, permitir_zero=True)
    pf = _positivo(f"o valor futuro da arroba no cenário {TIPOS_CENARIO.get(c.tipo, c.tipo)}", c.preco_arroba_futuro)
    rf = validar_rendimento(c.rendimento_futuro_pct)
    if c.gmd_kg_dia is None or not -2 < float(c.gmd_kg_dia) < 3:   # mesma restrição de cenario_venda
        raise DadosInvalidos("O GMD de cada cenário deve estar entre −2 e 3 kg/dia.")
    g = float(c.gmd_kg_dia)
    custos = {k: float(v or 0) for k, v in (c.custos_cab_dia or {}).items()}
    if any(v < 0 for v in custos.values()):
        raise DadosInvalidos("Custos diários não podem ser negativos.")
    cd = sum(custos.values())

    peso_proj = p0 + g * dias
    if peso_proj <= 0:
        raise DadosInvalidos("Com esse GMD o peso projetado fica menor ou igual a zero.")
    arr_a = p0 * ra / 100.0 / KG_POR_ARROBA
    arr_f = peso_proj * rf / 100.0 / KG_POR_ARROBA
    rec_a = arr_a * q * pa
    rec_d = arr_f * q * pf
    custo_esp = cd * dias * q
    custo_tot = acum + custo_esp
    inc = (rec_d - custo_esp) - rec_a
    produzidas = (arr_f - arr_a) * q
    return ResultadoCenario(
        cenario=c, peso_atual_rebanho_kg=p0 * q, peso_projetado_cab_kg=peso_proj, peso_projetado_rebanho_kg=peso_proj * q,
        ganho_cab_kg=g * dias, ganho_rebanho_kg=g * dias * q, arrobas_atual_cab=arr_a, arrobas_futuro_cab=arr_f,
        arrobas_atual_lote=arr_a * q, arrobas_futuro_lote=arr_f * q, arrobas_produzidas=produzidas,
        receita_vender_agora=rec_a, receita_vender_depois=rec_d, custo_diario_cab=cd, custo_adicional_espera=custo_esp,
        custo_acumulado_total_depois=custo_tot, receita_liquida_depois=rec_d - custo_esp,
        margem_operacional_agora=rec_a - acum, margem_operacional_depois=rec_d - custo_tot,
        margem_operacional_agora_pct=margem_pct(rec_a - acum, rec_a), margem_operacional_depois_pct=margem_pct(rec_d - custo_tot, rec_d),
        resultado_incremental=inc,
        custo_por_arroba_produzida=custo_esp / produzidas if produzidas else None,
        preco_equilibrio_futuro=(rec_a + custo_esp) / (arr_f * q) if arr_f else None,
        indicacao="esperar" if inc > 0 else ("vender agora" if inc < 0 else "indiferente"),
    )


def comparar_cenarios(e: EntradaRentabilidade, cenarios: Sequence[Cenario]) -> list[ResultadoCenario]:
    return [projetar_cenario(e, c) for c in cenarios]


def conclusao_rentabilidade(res: Sequence[ResultadoCenario], dias: int) -> str:
    esperar = [r for r in res if r.indicacao == "esperar"]
    if not res:
        return ""
    if len(esperar) == len(res):
        return (f"Nas três premissas, esperar {dias} dias resulta em ganho incremental em relação a vender agora "
                f"(de R$ {_br(min(r.resultado_incremental for r in res))} a R$ {_br(max(r.resultado_incremental for r in res))}).")
    if not esperar:
        return (f"Nas três premissas, vender agora é financeiramente melhor que esperar {dias} dias "
                f"(perda incremental de R$ {_br(abs(max(r.resultado_incremental for r in res)))} a "
                f"R$ {_br(abs(min(r.resultado_incremental for r in res)))} ao esperar).")
    nomes = ", ".join(TIPOS_CENARIO[r.cenario.tipo].lower() for r in esperar)
    return (f"O resultado depende das premissas: esperar {dias} dias compensa apenas no(s) cenário(s) {nomes}. "
            "Compare o valor futuro da arroba de cada cenário com o preço de equilíbrio indicado.")


# =====================================================================================================
# utilidades de texto
# =====================================================================================================
def _br(v: Optional[float], casas: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _faixa_txt(f: tuple[float, float]) -> str:
    a, b = f
    return f"{_br(a, 1).removesuffix(',0')} meses" if a == b else f"{_br(a, 1).removesuffix(',0')}–{_br(b, 1).removesuffix(',0')} meses"
