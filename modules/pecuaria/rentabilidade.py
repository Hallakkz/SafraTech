"""Módulo 3 — Simulador de Rentabilidade (pecuaria_rentabilidade_database).

Pergunta central: é mais vantajoso vender o gado agora ou esperar para obter melhores resultados financeiros?
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import streamlit as st

from database import pecuaria_queries as pq
from modules._comum import grafico, layout_escuro, tabela
from modules.pecuaria import calculos as calc
from modules.pecuaria import componentes as ui
from modules.pecuaria import relatorios
from utils import historico

BANCO = pq.RENTABILIDADE
CHAVE_RES = "pr_resultado"
FORMULAS = ["ARROBAS_CARCACA_DE_PESO_VIVO", "PESO_PROJETADO", "MARGEM_OPERACIONAL", "RENDIMENTO_CARCACA"]
INDICACAO = {"esperar": "⏳ Esperar", "vender agora": "💰 Vender agora", "indiferente": "➖ Indiferente"}


def render():
    ui.cabecalho("📊 Pecuária · Rentabilidade", "📊 Simulador de Rentabilidade",
                 "É mais vantajoso vender o gado agora ou esperar para obter melhores resultados financeiros?", BANCO)
    dados = ui.dados_ou_aviso(BANCO, ["racas", "referencias_rendimento", "referencias_gmd", "precos_arroba_historicos",
                                      "precos_insumo_historicos", "custos_referencia"])
    if dados is None:
        return

    st.subheader("🐂 Dados do rebanho")
    c1, c2 = st.columns(2)
    with c1:
        raca, raca_reg = ui.selecionar_raca(dados["racas"], "pr_raca")
    sexo = c2.selectbox("Sexo / categoria", list(calc.SEXOS_USUARIO), key="pr_sexo", format_func=calc.SEXOS_USUARIO.get)
    c1, c2, c3 = st.columns(3)
    qtd = c1.number_input("Quantidade de animais", min_value=1, max_value=100000, value=None, step=1, key="pr_qtd",
                          placeholder="nº de cabeças")
    peso = c2.number_input("Peso médio atual (kg de peso vivo)", min_value=30.0, max_value=1499.0, value=None, step=1.0,
                           key="pr_peso", placeholder="kg PV por cabeça")
    dias = c3.number_input("Período de simulação (dias)", min_value=1, max_value=730, value=None, step=1, key="pr_dias",
                           placeholder="dias até a venda futura")

    st.subheader("🏷️ Venda agora")
    c1, c2 = st.columns(2)
    preco_atual = c1.number_input("Valor atual da arroba (R$/@ de carcaça)", min_value=0.0, value=None, step=1.0, key="pr_preco",
                                  placeholder="cotação atual na sua região",
                                  help="1 arroba = 15 kg de carcaça. O banco não tem cotação atual: informe o valor de hoje.")
    acumulado = c2.number_input("Custos já acumulados com o lote (R$) — opcional", min_value=0.0, value=0.0, step=1000.0,
                                key="pr_acumulado", help="Usado apenas na margem operacional (vender agora x depois). "
                                                         "Não altera a diferença entre as alternativas.")
    ui.precos_historicos(dados["precos_arroba_historicos"])
    rend, ref_rend, origem_rend = ui.escolher_rendimento(dados["referencias_rendimento"], raca, sexo, "pr_rend",
                                                         "Rendimento de carcaça")

    st.subheader("📈 Ganho de peso e custos durante a espera")
    gmd, ref_gmd, origem_gmd = _escolher_gmd(dados["referencias_gmd"], raca, sexo)
    c1, c2, c3, c4 = st.columns(4)
    custos_base = {
        "alimentacao": c1.number_input("Alimentação (R$/cab/dia)", min_value=0.0, value=0.0, step=0.1, key="pr_c_alimentacao"),
        "suplementacao": c2.number_input("Suplementação (R$/cab/dia)", min_value=0.0, value=0.0, step=0.1, key="pr_c_suplementacao"),
        "manejo": c3.number_input("Manejo (R$/cab/dia)", min_value=0.0, value=0.0, step=0.1, key="pr_c_manejo"),
        "outros": c4.number_input("Outros custos (R$/cab/dia)", min_value=0.0, value=0.0, step=0.1, key="pr_c_outros"),
    }
    with st.expander("🗂️ Dados econômicos históricos do banco (apenas consulta)"):
        st.caption("Preços de insumos e estruturas de custo publicados nas fontes, em BRL nominal da data indicada. "
                   "Não são preços atuais e não são usados automaticamente.")
        pi = dados["precos_insumo_historicos"]
        if not pi.empty:
            tabela(pd.DataFrame([{"insumo": r["insumo"], "data": r["data_referencia"], "preço": ui.num(r["preco"]),
                                  "unidade": r["unidade_codigo"], "tipo": r["tipo_cotacao"],
                                  "fonte": f"{r['fonte_codigo']} ({ui.ano_fonte(r['fonte_ano'])}), p. {ui.texto(r['pagina_pdf'])}"}
                                 for r in pi.to_dict("records")]))

    # ------------------------------------------------------------------ cenários
    st.subheader("🔮 Cenários")
    st.caption("Defina as premissas de cada cenário. Campos em branco usam a premissa base (preço atual da arroba, GMD, "
               "rendimento e custo diário acima). O SafraTech não faz previsões de mercado: os valores futuros são seus.")
    custo_base_total = sum(v or 0 for v in custos_base.values())
    cols = st.columns(3)
    entradas_cen = {}
    for col, (tipo, nome) in zip(cols, calc.TIPOS_CENARIO.items()):
        with col:
            st.markdown(f"**{nome}**")
            entradas_cen[tipo] = {
                "preco": st.number_input(f"Arroba na venda futura (R$/@) — {nome}", min_value=0.0, value=None, step=1.0,
                                         key=f"pr_{tipo}_preco", placeholder="= valor atual"),
                "gmd": st.number_input(f"GMD (kg/dia) — {nome}", min_value=-1.99, max_value=2.99, value=None, step=0.05,
                                       key=f"pr_{tipo}_gmd", placeholder="= GMD esperado"),
                "rend": st.number_input(f"Rendimento na venda futura (%) — {nome}", min_value=30.0, max_value=75.0, value=None,
                                        step=0.5, key=f"pr_{tipo}_rend", placeholder="= rendimento atual"),
                "custo": st.number_input(f"Custo diário total (R$/cab/dia) — {nome}", min_value=0.0, value=None, step=0.1,
                                         key=f"pr_{tipo}_custo", placeholder="= soma dos custos"),
            }

    entrada = calc.EntradaRentabilidade(quantidade_animais=qtd, peso_atual_kg=peso, preco_arroba_atual=preco_atual,
                                        rendimento_atual_pct=rend, dias=dias, custo_acumulado_brl=acumulado or 0.0)
    assin = ui.assinatura(raca, sexo, entrada.__dict__, gmd, origem_gmd, origem_rend, custos_base, entradas_cen)

    if st.button("📊 Simular cenários", key="pr_simular"):
        try:
            if gmd is None:
                raise calc.DadosInvalidos("Informe o GMD esperado (ou selecione uma referência).")
            cenarios = [_cenario(tipo, v, preco_atual, gmd, rend, custos_base, custo_base_total) for tipo, v in entradas_cen.items()]
            resultados = calc.comparar_cenarios(entrada, cenarios)
        except calc.DadosInvalidos as e:
            st.error(f"Dados incompletos ou inválidos: {e}")
            st.session_state.pop(CHAVE_RES, None)
        else:
            st.session_state[CHAVE_RES] = {
                "assin": assin, "entrada": entrada, "resultados": resultados, "raca": raca_reg, "sexo": sexo,
                "gmd_base": gmd, "origem_gmd": origem_gmd, "ref_gmd": ref_gmd, "origem_rend": origem_rend, "ref_rend": ref_rend,
                "custos_base": custos_base, "entradas_cen": entradas_cen,
            }
            historico.registrar(st.session_state, "pecuaria_rentabilidade", {"raca": raca, "quantidade": qtd, "dias": dias},
                                {r.cenario.tipo: r.indicacao for r in resultados})

    salvo = st.session_state.get(CHAVE_RES)
    if salvo:
        if salvo["assin"] != assin:
            ui.aviso_resultado_desatualizado()
        else:
            _mostrar(salvo)


def _cenario(tipo, v, preco_atual, gmd, rend, custos_base, custo_base_total) -> calc.Cenario:
    total = v["custo"] if v["custo"] is not None else custo_base_total
    if custo_base_total > 0:
        custos = {k: (x or 0) * total / custo_base_total for k, x in custos_base.items()}
    else:
        custos = {"outros": total}
    return calc.Cenario(tipo=tipo, preco_arroba_futuro=v["preco"] if v["preco"] is not None else preco_atual,
                        gmd_kg_dia=v["gmd"] if v["gmd"] is not None else gmd,
                        rendimento_futuro_pct=v["rend"] if v["rend"] is not None else rend, custos_cab_dia=custos)


def _escolher_gmd(df: pd.DataFrame, raca: str, sexo: str) -> tuple[Optional[float], Optional[dict], str]:
    sx_ok = set(calc.SEXO_COMPATIVEL.get(sexo, {}))
    regs = [r for r in df.to_dict("records") if r.get("raca_codigo") == raca and r.get("sexo") in sx_ok]
    regs = [r for r in regs if _v(r.get("gmd_kg_dia")) is not None or _v(r.get("gmd_min_kg_dia")) is not None]
    modos = ["ref", "usuario"] if regs else ["usuario"]
    modo = st.radio("GMD esperado: origem do valor", modos, key=f"pr_gmd_modo_{raca}_{sexo}", horizontal=True,
                    format_func={"ref": "Referência técnica do banco", "usuario": "Informar valor próprio"}.get)
    if modo == "usuario":
        if not regs:
            st.caption("Não há referência de GMD para esta raça/genótipo e sexo no banco de rentabilidade.")
        v = st.number_input("GMD esperado durante a espera (kg/dia)", min_value=-1.99, max_value=2.99, value=None, step=0.05,
                            key="pr_gmd_valor", placeholder="ganho médio diário previsto")
        return v, None, "informado pelo usuário"
    por_id = {r["id_registro"]: r for r in regs}

    def rot(i):
        r = por_id[i]
        val = (f"{ui.num(_v(r['gmd_kg_dia']), 3)} kg/dia" if _v(r.get("gmd_kg_dia")) is not None
               else f"{ui.num(_v(r['gmd_min_kg_dia']), 2)}–{ui.num(_v(r['gmd_max_kg_dia']), 2)} kg/dia")
        return f"{val} — {r['parametro']} (fase: {r['fase']}; {r['sistema']}) · {r['fonte_codigo']}, p. {ui.texto(r['pagina_pdf']) or '—'}"
    rid = st.selectbox("GMD esperado: referência (mesma raça/genótipo e sexo compatível)", list(por_id), key=f"pr_gmd_ref_{raca}_{sexo}",
                       format_func=rot)
    r = por_id[rid]
    ui.detalhes_referencia(r)
    st.caption("Confira se a fase e as condições da referência correspondem ao período que você vai simular.")
    v = _v(r.get("gmd_kg_dia"))
    if v is None:
        a, b = _v(r["gmd_min_kg_dia"]), _v(r["gmd_max_kg_dia"])
        v = st.number_input(f"GMD dentro da faixa da referência ({ui.num(a, 2)}–{ui.num(b, 2)} kg/dia)", min_value=a, max_value=b,
                            value=a, step=0.01, key=f"pr_gmd_faixa_{rid}")
        return float(v), r, f"referência {rid} (faixa; valor escolhido pelo usuário)"
    return v, r, f"referência {rid}"


def _v(x) -> Optional[float]:
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _se_acum(salvo: dict, valor: str) -> str:
    """Lucro e margem operacional só fazem sentido com os custos já acumulados informados (senão a margem seria 100%)."""
    return valor if (salvo["entrada"].custo_acumulado_brl or 0) > 0 else "informe os custos acumulados"


def tabela_comparativa(salvo: dict) -> pd.DataFrame:
    res = salvo["resultados"]
    base = res[0]
    linhas = [
        ("Peso atual do rebanho (kg)", ui.num(base.peso_atual_rebanho_kg, 0), [ui.num(r.peso_projetado_rebanho_kg, 0) for r in res]),
        ("Peso por cabeça (kg)", ui.num(salvo["entrada"].peso_atual_kg, 1), [ui.num(r.peso_projetado_cab_kg, 1) for r in res]),
        ("Ganho de peso estimado (kg/cab)", "—", [ui.num(r.ganho_cab_kg, 1) for r in res]),
        ("Arrobas do lote (@)", ui.num(base.arrobas_atual_lote, 1), [ui.num(r.arrobas_futuro_lote, 1) for r in res]),
        ("Arrobas produzidas na espera (@)", "—", [ui.num(r.arrobas_produzidas, 1) for r in res]),
        ("Valor da arroba (R$/@)", ui.moeda(salvo["entrada"].preco_arroba_atual), [ui.moeda(r.cenario.preco_arroba_futuro) for r in res]),
        ("Receita bruta", ui.moeda(base.receita_vender_agora), [ui.moeda(r.receita_vender_depois) for r in res]),
        ("Custo da espera", "—", [ui.moeda(r.custo_adicional_espera) for r in res]),
        ("Custos acumulados", ui.moeda(salvo["entrada"].custo_acumulado_brl), [ui.moeda(r.custo_acumulado_total_depois) for r in res]),
        ("Receita líquida (receita − custo da espera)", ui.moeda(base.receita_vender_agora), [ui.moeda(r.receita_liquida_depois) for r in res]),
        ("Lucro / prejuízo operacional", _se_acum(salvo, ui.moeda(base.margem_operacional_agora)),
         [_se_acum(salvo, ui.moeda(r.margem_operacional_depois)) for r in res]),
        ("Margem operacional (%)", _se_acum(salvo, ui.num(base.margem_operacional_agora_pct, 1, "%")),
         [_se_acum(salvo, ui.num(r.margem_operacional_depois_pct, 1, "%")) for r in res]),
        ("Diferença: esperar − vender agora", "—", [ui.moeda(r.resultado_incremental) for r in res]),
        ("Custo por arroba produzida", "—", [ui.moeda(r.custo_por_arroba_produzida) for r in res]),
        ("Arroba futura de equilíbrio", "—", [ui.moeda(r.preco_equilibrio_futuro) for r in res]),
        ("Indicação pelas premissas", "—", [INDICACAO[r.indicacao] for r in res]),
    ]
    cols = ["Vender agora"] + [f"Esperar — {calc.TIPOS_CENARIO[r.cenario.tipo]}" for r in res]
    return pd.DataFrame([{"Indicador": a, cols[0]: b, **dict(zip(cols[1:], c))} for a, b, c in linhas])


def _mostrar(salvo: dict):
    res: list[calc.ResultadoCenario] = salvo["resultados"]
    e: calc.EntradaRentabilidade = salvo["entrada"]
    st.divider()
    st.subheader("📊 Resultado da simulação")
    conclusao = calc.conclusao_rentabilidade(res, e.dias)
    n_esp = sum(r.indicacao == "esperar" for r in res)
    chave = "esperar" if n_esp == len(res) else ("vender agora" if n_esp == 0 else "atencao")
    ui.card_veredito(chave, "Vender agora ou esperar?", conclusao)
    if len({(r.cenario.preco_arroba_futuro, r.cenario.gmd_kg_dia, r.cenario.rendimento_futuro_pct, r.custo_diario_cab)
            for r in res}) == 1:
        st.warning("Os três cenários estão com premissas idênticas. Altere o valor futuro da arroba, o GMD, o rendimento ou o "
                   "custo diário de cada cenário para comparar alternativas.")

    ui.metricas([
        ("Peso atual do rebanho", ui.num(res[0].peso_atual_rebanho_kg, 0, " kg")),
        ("Arrobas hoje", ui.num(res[0].arrobas_atual_lote, 1, " @")),
        ("Receita vendendo agora", ui.moeda(res[0].receita_vender_agora)),
        ("Margem operacional agora", _se_acum(salvo, ui.num(res[0].margem_operacional_agora_pct, 1, "%"))),
    ])
    if not (e.custo_acumulado_brl or 0) > 0:
        st.info("Lucro e margem operacional totais exigem os custos já acumulados com o lote (campo opcional acima). "
                "A comparação vender agora x esperar não depende desse valor.")
    cols = st.columns(3)
    for c, r in zip(cols, res):
        c.metric(f"Esperar — {calc.TIPOS_CENARIO[r.cenario.tipo]}", ui.moeda(r.resultado_incremental),
                 delta=INDICACAO[r.indicacao], delta_color="normal" if r.resultado_incremental >= 0 else "inverse",
                 help="Diferença financeira entre esperar o período (receita futura − custo da espera) e vender agora.")
    tabela(tabela_comparativa(salvo))

    nomes = [calc.TIPOS_CENARIO[r.cenario.tipo] for r in res]
    ui.grafico_barras(nomes, {"Vender agora (receita)": [r.receita_vender_agora for r in res],
                              "Esperar (receita − custo da espera)": [r.receita_liquida_depois for r in res],
                              "Diferença": [r.resultado_incremental for r in res]},
                      "Vender agora x esperar, por cenário", "R$")
    _grafico_peso(res, e)

    premissas = premissas_rentabilidade(salvo)
    with st.expander("📋 Premissas utilizadas", expanded=False):
        ui.tabela_premissas(premissas)
        st.caption("Fórmulas (vw_projecao_cenario): peso projetado = peso atual + GMD × dias; arrobas = peso × rendimento ÷ 15; "
                   "diferença = (arrobas futuras × arroba futura − custo diário × dias × cabeças) − arrobas atuais × arroba atual.")
    refs = [x for x in (salvo.get("ref_rend"), salvo.get("ref_gmd")) if x]
    fontes = ui.bloco_fontes(BANCO, refs, FORMULAS + (["GMD"] if salvo.get("ref_gmd") else []))
    pdf = relatorios.pdf_rentabilidade(salvo, premissas, fontes, tabela_comparativa(salvo), conclusao)
    st.download_button("📄 Baixar relatório em PDF", data=pdf, file_name="relatorio_pecuaria_rentabilidade.pdf",
                       mime="application/pdf", key="pr_pdf")


def _grafico_peso(res, e):
    try:
        import plotly.graph_objects as go
    except ImportError:  # pragma: no cover
        return
    fig = go.Figure()
    cores = {"conservador": "#ef6c00", "intermediario": "#81c784", "otimista": "#69f0ae"}
    for r in res:
        fig.add_trace(go.Scatter(x=[0, e.dias], y=[e.peso_atual_kg, r.peso_projetado_cab_kg], mode="lines+markers",
                                 name=calc.TIPOS_CENARIO[r.cenario.tipo], line=dict(color=cores[r.cenario.tipo])))
    fig.update_layout(title=dict(text="Peso projetado por cabeça (kg PV)", font=dict(size=13)), xaxis_title="dias",
                      yaxis_title="kg", legend=dict(orientation="h", y=-0.25))
    grafico(layout_escuro(fig, 320))


def premissas_rentabilidade(salvo: dict) -> list[tuple[str, str, str]]:
    e: calc.EntradaRentabilidade = salvo["entrada"]
    p = [
        ("Raça / composição genética", f"{salvo['raca']['nome']} ({salvo['raca']['grupo_genetico']})", "usuário (lista do banco)"),
        ("Sexo / categoria", calc.SEXOS_USUARIO.get(salvo["sexo"], salvo["sexo"]), "usuário"),
        ("Quantidade de animais", f"{e.quantidade_animais}", "usuário"),
        ("Peso médio atual", ui.num(e.peso_atual_kg, 1, " kg PV"), "usuário"),
        ("Valor atual da arroba", ui.moeda(e.preco_arroba_atual) + "/@ de carcaça", "usuário"),
        ("Rendimento de carcaça atual", ui.num(e.rendimento_atual_pct, 1, "%"), salvo["origem_rend"]),
        ("GMD esperado (base)", ui.num(salvo["gmd_base"], 3, " kg/dia"), salvo["origem_gmd"]),
        ("Período de simulação", f"{e.dias} dias", "usuário"),
        ("Custos já acumulados", ui.moeda(e.custo_acumulado_brl), "usuário"),
    ] + [(f"Custo base — {calc.TIPOS_CUSTO[k]}", ui.moeda(v) + "/cab/dia", "usuário") for k, v in salvo["custos_base"].items()]
    for r in salvo["resultados"]:
        c, v = r.cenario, salvo["entradas_cen"][r.cenario.tipo]
        nome = calc.TIPOS_CENARIO[c.tipo]
        p += [
            (f"{nome}: arroba futura", ui.moeda(c.preco_arroba_futuro) + "/@",
             "usuário" if v["preco"] is not None else "não informada — igual ao valor atual (sem previsão de mercado)"),
            (f"{nome}: GMD", ui.num(c.gmd_kg_dia, 3, " kg/dia"), "usuário" if v["gmd"] is not None else "igual ao GMD base"),
            (f"{nome}: rendimento futuro", ui.num(c.rendimento_futuro_pct, 1, "%"),
             "usuário" if v["rend"] is not None else "igual ao rendimento atual"),
            (f"{nome}: custo diário", ui.moeda(r.custo_diario_cab) + "/cab/dia",
             "usuário" if v["custo"] is not None else "igual à soma dos custos base"),
        ]
    return p
