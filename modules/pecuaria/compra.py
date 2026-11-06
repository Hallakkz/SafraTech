"""Módulo 1 — Análise de Viabilidade de Compra (pecuaria_compra_database).

Pergunta central: vale a pena comprar determinado lote de gado de corte?
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import pecuaria_queries as pq
from modules._comum import tabela
from modules.pecuaria import calculos as calc
from modules.pecuaria import componentes as ui
from modules.pecuaria import relatorios
from utils import historico

BANCO = pq.COMPRA
CHAVE_RES = "pc_resultado"
VEREDITO = {
    "viavel": ("✅ Investimento potencialmente viável", "O lucro projetado é positivo e a margem atinge a margem mínima desejada."),
    "atencao": ("⚠️ Investimento que exige atenção", "O lucro projetado é positivo, mas a margem fica abaixo da margem mínima desejada."),
    "inviavel": ("⛔ Investimento potencialmente inviável", "Com as premissas informadas a receita projetada não cobre o custo total."),
}
FORMULAS = ["ARROBAS_CARCACA_DE_PESO_VIVO", "RENDIMENTO_CARCACA", "LUCRO"]


def render():
    ui.cabecalho("💵 Pecuária · Compra", "💵 Análise de Viabilidade de Compra",
                 "Vale a pena comprar determinado lote de gado de corte?", BANCO)
    dados = ui.dados_ou_aviso(BANCO, ["racas", "referencias_rendimento", "precos_arroba_historicos", "custos_referencia"])
    if dados is None:
        return

    # ------------------------------------------------------------------ dados do lote
    st.subheader("🐂 Dados do lote")
    c1, c2 = st.columns(2)
    with c1:
        raca, raca_reg = ui.selecionar_raca(dados["racas"], "pc_raca")
    sexo = c2.selectbox("Sexo / categoria", list(calc.SEXOS_USUARIO), key="pc_sexo", format_func=calc.SEXOS_USUARIO.get,
                        help="Usado para selecionar referências de rendimento de carcaça compatíveis.")
    c1, c2, c3 = st.columns(3)
    qtd = c1.number_input("Quantidade de animais", min_value=1, max_value=100000, value=None, step=1, key="pc_qtd",
                          placeholder="nº de cabeças")
    peso_compra = c2.number_input("Peso médio por animal na compra (kg de peso vivo)", min_value=30.0, max_value=1200.0,
                                  value=None, step=1.0, key="pc_peso_compra", placeholder="kg PV")
    dias = c3.number_input("Dias de permanência até a venda", min_value=0, max_value=1500, value=None, step=1, key="pc_dias",
                           placeholder="opcional", help="Necessário para custos por cabeça por dia e para o GMD implícito.")

    # ------------------------------------------------------------------ compra
    st.subheader("💰 Dados de compra")
    c1, c2 = st.columns([1, 2])
    modo = c1.radio("Forma de informar o preço de compra", ["cabeca", "lote"], key="pc_modo_preco",
                    format_func={"cabeca": "Preço por cabeça", "lote": "Preço total do lote"}.get,
                    help="Apenas uma forma é considerada no cálculo — nunca as duas ao mesmo tempo.")
    if modo == "cabeca":
        preco = c2.number_input("Preço de compra por cabeça (R$/cab)", min_value=0.0, value=None, step=50.0, key="pc_preco_cab",
                                placeholder="R$ por cabeça")
    else:
        preco = c2.number_input("Preço total do lote (R$)", min_value=0.0, value=None, step=1000.0, key="pc_preco_lote",
                                placeholder="R$ do lote inteiro")

    # ------------------------------------------------------------------ venda prevista
    st.subheader("🏷️ Venda prevista")
    c1, c2 = st.columns(2)
    peso_venda = c1.number_input("Peso médio previsto na venda (kg de peso vivo)", min_value=30.0, max_value=1500.0, value=None,
                                 step=1.0, key="pc_peso_venda", placeholder="kg PV por cabeça")
    preco_arroba = c2.number_input("Valor da arroba de venda considerado (R$/@ de carcaça)", min_value=0.0, value=None, step=1.0,
                                   key="pc_preco_arroba", placeholder="cotação atual na sua região",
                                   help="1 arroba = 15 kg de CARCAÇA. O banco só contém preços históricos de publicações; "
                                        "informe o valor praticado hoje.")
    ui.precos_historicos(dados["precos_arroba_historicos"])
    rend, ref_rend, origem_rend = ui.escolher_rendimento(dados["referencias_rendimento"], raca, sexo, "pc_rend",
                                                         "Rendimento de carcaça na venda")

    # ------------------------------------------------------------------ custos
    st.subheader("🧾 Custos adicionais")
    c1, c2, c3, c4 = st.columns(4)
    transporte = c1.number_input("Transporte (R$ por lote)", min_value=0.0, value=0.0, step=100.0, key="pc_c_transporte")
    alimentacao = c2.number_input("Alimentação (R$/cab/dia)", min_value=0.0, value=0.0, step=0.5, key="pc_c_alimentacao")
    manejo = c3.number_input("Manejo e sanidade (R$/cab)", min_value=0.0, value=0.0, step=5.0, key="pc_c_manejo")
    outros = c4.number_input("Outros (R$ por lote)", min_value=0.0, value=0.0, step=100.0, key="pc_c_outros",
                             help="Ex.: comissão, impostos, taxas de comercialização.")
    with st.expander("📊 Estruturas de custo de referência (fazendas típicas das publicações — valores históricos)"):
        _custos_referencia(dados["custos_referencia"])
    margem_min = st.number_input("Margem de lucro mínima desejada (% da receita bruta)", min_value=0.0, max_value=100.0, value=None,
                                 step=1.0, key="pc_margem_min", placeholder="sua meta de margem",
                                 help="Premissa sua. Define o limite entre 'viável' e 'exige atenção' quando há lucro.")

    custos = [calc.CustoAdicional("transporte", transporte, "brl_total", "Transporte"),
              calc.CustoAdicional("alimentacao", alimentacao, "brl_cab_dia", "Alimentação"),
              calc.CustoAdicional("manejo", manejo, "brl_cab", "Manejo e sanidade"),
              calc.CustoAdicional("outros", outros, "brl_total", "Outros")]
    entrada = calc.EntradaCompra(quantidade_animais=qtd, peso_medio_compra_kg=peso_compra, modo_preco=modo, preco_compra=preco,
                                 peso_venda_kg=peso_venda, rendimento_venda_pct=rend, preco_venda_arroba=preco_arroba,
                                 dias_permanencia=dias, custos=custos, margem_minima_pct=margem_min)
    assin = ui.assinatura(raca, sexo, entrada.__dict__ | {"custos": [c.__dict__ for c in custos]}, origem_rend)

    if st.button("📊 Analisar viabilidade", key="pc_analisar"):
        try:
            if margem_min is None:
                raise calc.DadosInvalidos("Informe a margem de lucro mínima desejada.")
            res = calc.analisar_compra(entrada)
        except calc.DadosInvalidos as e:
            st.error(f"Dados incompletos ou inválidos: {e}")
            st.session_state.pop(CHAVE_RES, None)
        else:
            st.session_state[CHAVE_RES] = {"assin": assin, "res": res, "raca": raca_reg, "sexo": sexo,
                                           "ref_rend": ref_rend, "origem_rend": origem_rend}
            historico.registrar(st.session_state, "pecuaria_compra", {"raca": raca, "quantidade": qtd},
                                {"lucro": round(res.lucro, 2), "classificacao": res.classificacao})

    salvo = st.session_state.get(CHAVE_RES)
    if salvo:
        if salvo["assin"] != assin:
            ui.aviso_resultado_desatualizado()
        else:
            _mostrar(salvo)


def _custos_referencia(df: pd.DataFrame):
    if df is None or df.empty:
        st.caption("Sem registros.")
        return
    st.caption("Composição de custos de fazendas modelo/típicas descritas nas fontes, em BRL nominal da época indicada. "
               "Servem para conferir se algum item de custo foi esquecido — não substituem os custos do seu lote.")
    resumo = (df.groupby(["fonte_codigo", "escopo", "periodo_referencia", "localizacao"], dropna=False)
              .agg(itens=("id_custo", "count")).reset_index())
    tabela(resumo.rename(columns={"fonte_codigo": "fonte", "periodo_referencia": "período", "localizacao": "localização"}))


def _mostrar(salvo: dict):
    res: calc.ResultadoCompra = salvo["res"]
    e = res.entrada
    st.divider()
    st.subheader("📊 Resultado da análise")
    titulo, explicacao = VEREDITO[res.classificacao]
    ui.card_veredito(res.classificacao, titulo,
                     f"{explicacao}<br>Lucro projetado: <b>{ui.moeda(res.lucro)}</b> · margem "
                     f"<b>{ui.num(res.margem_lucro_pct, 1, '%')}</b> (mínima desejada: {ui.num(e.margem_minima_pct, 1, '%')}).")
    ui.metricas([
        ("Investimento inicial", ui.moeda(res.custo_aquisicao_lote)),
        ("Custos adicionais", ui.moeda(res.custo_adicional_total)),
        ("Custo total do lote", ui.moeda(res.custo_total_lote)),
        ("Receita bruta projetada", ui.moeda(res.receita_bruta)),
        ("Receita líquida estimada", ui.moeda(res.receita_liquida)),
        ("Lucro / prejuízo", ui.moeda(res.lucro)),
        ("Margem de lucro", ui.num(res.margem_lucro_pct, 1, "%")),
        ("Retorno sobre o custo", ui.num(res.retorno_sobre_custo_pct, 1, "%")),
    ], ajuda={"Receita líquida estimada": "Receita bruta − custos adicionais (antes de descontar a aquisição).",
              "Investimento inicial": "Custo de aquisição dos animais."})
    st.markdown("**Peso e arrobas**")
    ui.metricas([
        ("Peso total na compra", ui.num(res.peso_total_compra_kg, 0, " kg")),
        ("Peso total na venda", ui.num(res.peso_total_venda_kg, 0, " kg")),
        ("Peso de carcaça estimado", ui.num(res.peso_carcaca_lote_kg, 0, " kg")),
        ("Arrobas estimadas", ui.num(res.arrobas_carcaca_lote, 1, " @")),
    ])
    st.markdown("**Indicadores de viabilidade**")
    ui.metricas([
        ("Preço de equilíbrio", ui.moeda(res.preco_equilibrio_arroba) + "/@"),
        ("Margem de segurança no preço", ui.num(res.margem_seguranca_preco_pct, 1, "%")),
        ("Rendimento de equilíbrio", ui.num(res.rendimento_equilibrio_pct, 1, "%")),
        ("Peso de venda de equilíbrio", ui.num(res.peso_venda_equilibrio_kg, 0, " kg/cab")),
    ], ajuda={"Preço de equilíbrio": "Valor da arroba que zera o lucro.",
              "Margem de segurança no preço": "Quanto o preço da arroba pode cair (em %) antes de haver prejuízo."})

    ui.grafico_barras(["Receita bruta", "Aquisição", "Custos adicionais", "Lucro / prejuízo"],
                      {"R$": [res.receita_bruta, res.custo_aquisicao_lote, res.custo_adicional_total, res.lucro]},
                      "Receita, custos e resultado do lote", "R$")

    st.markdown("**Fatores que mais influenciaram o resultado**")
    for f in calc.fatores_compra(res):
        st.markdown(f"- {f}")
    with st.expander("🔍 Sensibilidade (efeito de 1% desfavorável em cada premissa)"):
        tabela(pd.DataFrame([{"premissa": s["fator"], "efeito no lucro": ui.moeda(s["impacto_lucro"])} for s in res.sensibilidade]))
    if res.custos_detalhados:
        with st.expander("🧾 Custos adicionais detalhados"):
            tabela(pd.DataFrame([{"item": a, "total no período": ui.moeda(b)} for a, b in res.custos_detalhados]))

    premissas = premissas_compra(salvo)
    with st.expander("📋 Premissas utilizadas", expanded=False):
        ui.tabela_premissas(premissas)
        st.caption("1 arroba = 15 kg de carcaça. Arrobas = peso vivo de venda × rendimento ÷ 15. Nenhum preço atual foi "
                   "retirado do banco: o valor da arroba é o informado por você.")
    refs = [salvo["ref_rend"]] if salvo.get("ref_rend") else []
    fontes = ui.bloco_fontes(BANCO, refs, FORMULAS)
    pdf = relatorios.pdf_compra(salvo, premissas, fontes)
    st.download_button("📄 Baixar relatório em PDF", data=pdf, file_name="relatorio_pecuaria_compra.pdf",
                       mime="application/pdf", key="pc_pdf")


def premissas_compra(salvo: dict) -> list[tuple[str, str, str]]:
    res: calc.ResultadoCompra = salvo["res"]
    e = res.entrada
    preco = (f"{ui.moeda(e.preco_compra)} por cabeça" if e.modo_preco == "cabeca" else f"{ui.moeda(e.preco_compra)} pelo lote")
    return [
        ("Raça / composição genética", f"{salvo['raca']['nome']} ({salvo['raca']['grupo_genetico']})", "usuário (lista do banco)"),
        ("Sexo / categoria", calc.SEXOS_USUARIO.get(salvo["sexo"], salvo["sexo"]), "usuário"),
        ("Quantidade de animais", f"{e.quantidade_animais}", "usuário"),
        ("Peso médio na compra", ui.num(e.peso_medio_compra_kg, 0, " kg PV"), "usuário"),
        ("Preço de compra", preco, "usuário"),
        ("Peso médio previsto na venda", ui.num(e.peso_venda_kg, 0, " kg PV"), "usuário"),
        ("Dias de permanência", f"{e.dias_permanencia}" if e.dias_permanencia else "não informado", "usuário"),
        ("Rendimento de carcaça na venda", ui.num(e.rendimento_venda_pct, 1, "%"), salvo["origem_rend"]),
        ("Valor da arroba de venda", ui.moeda(e.preco_venda_arroba) + "/@ de carcaça", "usuário"),
        ("Margem mínima desejada", ui.num(e.margem_minima_pct, 1, "%"), "usuário"),
    ] + [(f"Custo: {c.descricao}", f"{ui.moeda(c.valor)} ({calc.BASES_CUSTO[c.base]})", "usuário") for c in e.custos if c.valor]
