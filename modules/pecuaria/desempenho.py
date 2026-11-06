"""Módulo 2 — Diagnóstico de Desempenho do Rebanho (pecuaria_desempenho_database).

Pergunta central: os animais estão apresentando desempenho adequado considerando raça, idade, sexo e sistema de criação?
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database import pecuaria_queries as pq
from modules._comum import tabela
from modules.pecuaria import calculos as calc
from modules.pecuaria import componentes as ui
from modules.pecuaria import relatorios
from utils import historico

BANCO = pq.DESEMPENHO
CHAVE_RES = "pd_resultado"


def render():
    ui.cabecalho("📈 Pecuária · Desempenho", "📈 Diagnóstico de Desempenho do Rebanho",
                 "Os animais estão apresentando desempenho adequado considerando raça, idade, sexo e sistema de criação?", BANCO)
    dados = ui.dados_ou_aviso(BANCO, ["racas", "sistemas", "referencias_peso", "referencias_gmd"])
    if dados is None:
        return

    st.subheader("🐂 Identificação")
    ident = st.text_input("Identificação do animal ou lote (opcional)", key="pd_ident", placeholder="ex.: lote 3 — pasto da represa")
    c1, c2 = st.columns(2)
    with c1:
        raca, raca_reg = ui.selecionar_raca(dados["racas"], "pd_raca")
    sexo = c2.selectbox("Sexo / condição sexual", list(calc.SEXOS_USUARIO), key="pd_sexo", format_func=calc.SEXOS_USUARIO.get)
    sist = {r["sistema_codigo"]: r for r in dados["sistemas"].to_dict("records")}
    c1, c2, c3 = st.columns(3)
    sistema = c1.selectbox("Sistema de criação", list(sist), key="pd_sistema", format_func=lambda s: sist[s]["nome"],
                           help="Lista do banco (sistema_criacao).")
    fase = c2.selectbox("Fase produtiva", list(calc.FASES_USUARIO), key="pd_fase", format_func=calc.FASES_USUARIO.get,
                        help="Necessária para comparar o GMD: o ganho esperado muda muito entre cria, recria e terminação.")
    idade = c3.number_input("Idade (meses)", min_value=0.0, max_value=240.0, value=None, step=1.0, key="pd_idade",
                            placeholder="idade na pesagem atual")

    st.subheader("⚖️ Pesagens")
    c1, c2 = st.columns(2)
    peso_atual = c1.number_input("Peso atual (kg de peso vivo)", min_value=1.0, max_value=1499.0, value=None, step=1.0,
                                 key="pd_peso_atual", placeholder="kg PV")
    data_atual = c2.date_input("Data da pesagem atual", value=date.today(), key="pd_data_atual", format="DD/MM/YYYY")
    c1, c2 = st.columns(2)
    peso_ant = c1.number_input("Peso anterior (kg de peso vivo) — opcional", min_value=1.0, max_value=1499.0, value=None,
                               step=1.0, key="pd_peso_ant", placeholder="para calcular o GMD")
    data_ant = c2.date_input("Data da pesagem anterior — opcional", value=None, key="pd_data_ant", format="DD/MM/YYYY")
    with st.expander("⚙️ Critérios de comparação (ajustáveis)"):
        st.caption("Critérios do SafraTech para decidir se uma referência é comparável e como classificar a diferença. "
                   "Não são dados das fontes.")
        c1, c2 = st.columns(2)
        tol_idade = c1.number_input("Tolerância de idade (± meses)", min_value=0.0, max_value=6.0, value=1.0, step=0.5,
                                    key="pd_tol_idade")
        tol_pct = c2.number_input("Faixa considerada próxima da referência (± %)", min_value=0.0, max_value=50.0, value=10.0,
                                  step=1.0, key="pd_tol_pct",
                                  help="Para referências de valor único (médias). Referências com faixa usam os limites da fonte.")

    assin = ui.assinatura(ident, raca, sexo, sistema, fase, idade, peso_atual, data_atual, peso_ant, data_ant, tol_idade, tol_pct)
    if st.button("📈 Diagnosticar desempenho", key="pd_analisar"):
        try:
            res = diagnosticar(dados, raca, sexo, sistema, fase, idade, peso_atual, data_atual, peso_ant, data_ant, tol_idade, tol_pct)
        except calc.DadosInvalidos as e:
            st.error(f"Dados incompletos ou inválidos: {e}")
            st.session_state.pop(CHAVE_RES, None)
        else:
            res.update({"assin": assin, "ident": ident, "raca": raca_reg, "sistema_reg": sist[sistema]})
            st.session_state[CHAVE_RES] = res
            historico.registrar(st.session_state, "pecuaria_desempenho", {"raca": raca, "sexo": sexo, "idade": idade},
                                {"peso": res["status_peso"], "gmd": res["status_gmd"]})

    salvo = st.session_state.get(CHAVE_RES)
    if salvo:
        if salvo["assin"] != assin:
            ui.aviso_resultado_desatualizado()
        else:
            _mostrar(salvo)


def diagnosticar(dados, raca, sexo, sistema, fase, idade, peso_atual, data_atual, peso_ant, data_ant, tol_idade, tol_pct) -> dict:
    if idade is None:
        raise calc.DadosInvalidos("Informe a idade (meses).")
    if peso_atual is None:
        raise calc.DadosInvalidos("Informe o peso atual.")
    g = dias = ganho = None
    if peso_ant is not None or data_ant is not None:
        if peso_ant is None or data_ant is None:
            raise calc.DadosInvalidos("Para calcular o GMD informe o peso E a data da pesagem anterior.")
        g, dias = calc.gmd(peso_ant, peso_atual, data_ant, data_atual)
        ganho = peso_atual - peso_ant
    refs_peso = dados["referencias_peso"].to_dict("records")
    cmp_peso, nao_peso = calc.comparar_peso(refs_peso, raca, sexo, sistema, idade, peso_atual, tol_idade, tol_pct)
    cmp_gmd, nao_gmd = [], []
    if g is not None:
        cmp_gmd, nao_gmd = calc.comparar_gmd(dados["referencias_gmd"].to_dict("records"), raca, sexo, sistema, fase, idade, g,
                                             data_ant, data_atual, tol_idade, tol_pct)
    return {"raca_cod": raca, "sexo": sexo, "sistema": sistema, "fase": fase, "idade": idade, "peso_atual": peso_atual,
            "data_atual": data_atual, "peso_ant": peso_ant, "data_ant": data_ant, "gmd": g, "dias": dias, "ganho": ganho,
            "tol_idade": tol_idade, "tol_pct": tol_pct, "cmp_peso": cmp_peso, "nao_peso": nao_peso, "cmp_gmd": cmp_gmd,
            "nao_gmd": nao_gmd, "status_peso": calc.resumo_status(cmp_peso),
            "status_gmd": calc.resumo_status(cmp_gmd) if g is not None else "sem_gmd",
            "atencao": calc.pontos_de_atencao(cmp_peso, cmp_gmd, g, ganho)}


def _linhas(cmps, unidade: str, casas: int) -> pd.DataFrame:
    return pd.DataFrame([{
        "referência": c.parametro,
        "valor de referência": (ui.num(c.valor_ref, casas) if c.valor_ref is not None
                                else f"{ui.num(c.ref_min, casas)}–{ui.num(c.ref_max, casas)}") + f" {unidade}",
        "observado": f"{ui.num(c.observado, casas)} {unidade}",
        "diferença": (f"{ui.num(c.diferenca, casas)} {unidade}" + (f" ({ui.num(c.diferenca_pct, 1)}%)" if c.diferenca_pct is not None else "")),
        "situação": ui.ROTULO_STATUS[c.status],
        "tipo de dado": ui.TIPO_DADO.get(c.registro.get("tipo_dado"), c.registro.get("tipo_dado")),
        "por que é comparável": c.justificativa,
        "fonte": f"{c.registro.get('fonte_codigo')}, p. {ui.texto(c.registro.get('pagina_pdf')) or '—'}",
        "registro": c.id_registro,
    } for c in cmps])


def _nao_usadas(nao) -> pd.DataFrame:
    return pd.DataFrame([{"registro": n.id_registro, "parâmetro": n.parametro, "raça": n.registro.get("raca"),
                          "sexo": ui.SEXO_REF.get(n.registro.get("sexo"), n.registro.get("sexo")),
                          "sistema": n.registro.get("sistema"), "motivo da não utilização": n.motivo} for n in nao])


def _mostrar(r: dict):
    st.divider()
    nome = r["ident"] or "Animal/lote"
    st.subheader(f"📊 Diagnóstico — {nome}")
    st.caption(f"{r['raca']['nome']} · {calc.SEXOS_USUARIO[r['sexo']]} · {ui.num(r['idade'], 0)} meses · "
               f"{r['sistema_reg']['nome']} · fase: {calc.FASES_USUARIO[r['fase']]}")

    st_peso, st_gmd = r["status_peso"], r["status_gmd"]
    txt = f"<b>Peso:</b> {ui.chip_status(st_peso)}"
    if st_gmd != "sem_gmd":
        txt += f" &nbsp; <b>GMD:</b> {ui.chip_status(st_gmd)}"
    ui.card_veredito(st_peso if st_gmd in ("sem_gmd", st_peso) else ("abaixo" if "abaixo" in (st_peso, st_gmd) else st_peso),
                     "Situação em relação às referências técnicas compatíveis", txt)

    itens = [("Peso atual", ui.num(r["peso_atual"], 1, " kg"))]
    if r["cmp_peso"]:
        vals = [c.valor_ref for c in r["cmp_peso"] if c.valor_ref is not None]
        if vals:
            itens.append(("Peso de referência", (ui.num(min(vals), 0) + "–" + ui.num(max(vals), 0) if min(vals) != max(vals)
                                                else ui.num(vals[0], 0)) + " kg"))
    else:
        itens.append(("Peso de referência", "dados insuficientes"))
    if r["gmd"] is not None:
        itens += [("Ganho médio diário (GMD)", ui.num(r["gmd"], 3, " kg/dia")),
                  ("Evolução do peso", f"{ui.num(r['ganho'], 1, ' kg')} em {r['dias']} dias")]
    else:
        itens += [("Ganho médio diário (GMD)", "informe a pesagem anterior"), ("Evolução do peso", "—")]
    ui.metricas(itens)
    if r["gmd"] is not None:
        ui.metricas([("Peso anterior", ui.num(r["peso_ant"], 1, " kg")),
                     ("Ganho relativo", ui.num(r["ganho"] / r["peso_ant"] * 100, 1, "%")),
                     ("Em unidades animais (UA)", ui.num(r["peso_atual"] / 450, 2, " UA")),
                     ("Referências compatíveis", f"{len(r['cmp_peso'])} peso · {len(r['cmp_gmd'])} GMD")],
                    ajuda={"Em unidades animais (UA)": "UA = peso vivo ÷ 450 (formula_calculo UNIDADE_ANIMAL, F01 p.232)."})

    if r["atencao"]:
        st.markdown("**⚠️ Pontos de atenção**")
        for p in r["atencao"]:
            st.warning(p)

    st.markdown("**Comparação do peso com referências de animais de características compatíveis**")
    if r["cmp_peso"]:
        tabela(_linhas(r["cmp_peso"], "kg", 1))
        _grafico_peso(r)
    else:
        st.info("Dados insuficientes: não há no banco referência de peso vivo para a mesma raça/genótipo, sexo compatível, "
                "mesmo sistema de criação e idade compatível. O SafraTech não estima um peso esperado nesses casos.")
    if r["gmd"] is not None:
        st.markdown("**Comparação do GMD**")
        if r["cmp_gmd"]:
            tabela(_linhas(r["cmp_gmd"], "kg/dia", 3))
        else:
            st.info("Dados insuficientes: não há no banco referência de GMD para a mesma raça/genótipo, sexo compatível, "
                    "mesmo sistema e mesma fase (e, quando a fonte define, mesmo período de idade ou mês).")
    with st.expander(f"🗂️ Referências do banco não utilizadas e o motivo ({len(r['nao_peso']) + len(r['nao_gmd'])})"):
        st.caption("Regras: mesma raça/genótipo (Nelore PO, Nelore comercial, nelorado e cruzados nunca se misturam), sexo "
                   "compatível, mesmo sistema; para peso, idade explícita na fonte; para GMD, mesma fase.")
        mesmas = [n for n in r["nao_peso"] + r["nao_gmd"] if n.registro.get("raca_codigo") == r["raca_cod"]]
        if mesmas:
            tabela(_nao_usadas(mesmas))
        outras = len(r["nao_peso"]) + len(r["nao_gmd"]) - len(mesmas)
        st.caption(f"Outras {outras} referências são de raça/genótipo diferente e não foram consideradas.")

    with st.expander("🧬 Informações técnicas da raça e do sistema de criação"):
        st.markdown(f"**{r['raca']['nome']}** — {r['raca']['grupo_genetico']}: {r['raca']['descricao']}")
        st.markdown(f"**{r['sistema_reg']['nome']}**: {r['sistema_reg']['descricao']}")
    ui.perguntas_tecnicas(BANCO, r["raca_cod"], ["ganho_peso", "recria", "terminacao_confinamento", "raca_genetica"],
                          "❓ Perguntas e respostas das fontes relacionadas à raça")

    refs = [c.registro for c in r["cmp_peso"] + r["cmp_gmd"]]
    formulas = ["UNIDADE_ANIMAL"] + (["GMD"] if r["gmd"] is not None else [])
    if any("205 dias" in str(x.get("parametro")) for x in refs):
        formulas.append("PESO_CORRIGIDO_205_DIAS")
    fontes = ui.bloco_fontes(BANCO, refs, formulas)
    pdf = relatorios.pdf_desempenho(r, fontes)
    st.download_button("📄 Baixar relatório em PDF", data=pdf, file_name="relatorio_pecuaria_desempenho.pdf",
                       mime="application/pdf", key="pd_pdf")


def _grafico_peso(r: dict):
    cats = [f"{c.id_registro}" for c in r["cmp_peso"]]
    refs = [c.valor_ref if c.valor_ref is not None else (c.ref_min or 0) for c in r["cmp_peso"]]
    ui.grafico_barras(cats, {"Referência (kg)": refs, "Peso atual (kg)": [r["peso_atual"]] * len(cats)},
                      "Peso atual x referências compatíveis", "kg de peso vivo", altura=320)
