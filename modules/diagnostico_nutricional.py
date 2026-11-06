"""Módulo 2 — Diagnóstico Nutricional (soja, milho, algodão e gergelim)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import nutricao_engine as ne
from core.classificacao import txt
from core.unidades import MACROS_FOLIAR, UNIDADES_FOLIAR_MACRO, UNIDADES_FOLIAR_MICRO, converter_foliar
from database import nutricao_queries as nq
from database.connections import BancoIndisponivel
from modules._comum import (aviso_banco, botao_pdf, grafico_posicao, mostrar_divergencias, mostrar_fontes, painel_historico,
                            seletor_municipio, tabela)
from utils import historico
from utils.formatacao import chip, numero, status
from utils.textos import tr
from utils.relatorio_pdf import Relatorio

RES = "nut_resultado"


@st.cache_data(ttl=3600, show_spinner=False)
def _faixas(cultura: str) -> pd.DataFrame:
    return nq.faixas_suficiencia(cultura)


@st.cache_data(ttl=3600, show_spinner=False)
def _complementares(cultura: str) -> pd.DataFrame:
    return nq.registros_complementares(cultura)


@st.cache_data(ttl=3600, show_spinner=False)
def _cobertura(cultura: str) -> pd.DataFrame:
    return nq.cobertura(cultura)


@st.cache_data(ttl=3600, show_spinner=False)
def _amostragem(cultura: str) -> pd.DataFrame:
    return nq.amostragem_foliar(cultura)


@st.cache_data(ttl=3600, show_spinner=False)
def _sintomas(cultura: str) -> pd.DataFrame:
    return nq.sintomas(cultura)


@st.cache_data(ttl=3600, show_spinner=False)
def _divergencias(ids: tuple) -> pd.DataFrame:
    return nq.divergencias(list(ids))


def render():
    st.markdown(f'<div class="header-badge">{tr("nut_badge")}</div>', unsafe_allow_html=True)
    st.header(tr("nut_header"))
    st.caption(tr("nut_intro"))

    c1, c2 = st.columns([1, 1])
    cultura = c1.selectbox(tr("crop"), nq.CULTURAS, key="nut_cultura")
    tipos = tr("nut_types")
    tipo = c2.radio(tr("nut_type"), list(tipos), format_func=tipos.get, horizontal=True, key="nut_tipo")
    try:
        faixas = _faixas(cultura)
    except BancoIndisponivel as e:
        aviso_banco("nutricao", e)
        return
    uf, municipio, _ = seletor_municipio("nut")
    estagios = ne.estagios_protocolo(faixas)
    opcoes = estagios + [ne.OUTRO_ESTAGIO]
    estagio = st.selectbox(tr("nut_stage"), opcoes, key=f"nut_estagio_{cultura}",
                           format_func=lambda x: tr("nut_stage_other") if x == ne.OUTRO_ESTAGIO else x)
    if not estagios:
        st.info(tr("nut_no_protocol"))
    else:
        partes = faixas.loc[faixas["estagio"] == estagio, "parte_planta"].dropna().unique().tolist() if estagio != ne.OUTRO_ESTAGIO else []
        if partes:
            st.caption(f"{tr('nut_part')}: {'; '.join(partes)}")

    with st.form("form_nut"):
        valores, unidades = {}, {}
        if tipo in ("foliar", "ambos"):
            st.subheader(tr("nut_tab_foliar"))
            cols = st.columns(4)
            for i, nut in enumerate(ne.NUTRIENTES_FOLIARES):
                col = cols[i % 4]
                a, b = col.columns([3, 2])
                valores[nut] = a.number_input(nut, value=None, min_value=0.0, step=0.1, format="%.3f", key=f"nut_v_{nut}",
                                              placeholder=tr("not_informed"))
                unidades[nut] = b.selectbox(tr("unit"), UNIDADES_FOLIAR_MACRO if nut in MACROS_FOLIAR else UNIDADES_FOLIAR_MICRO,
                                            key=f"nut_u_{nut}")
        sint_sel = []
        if tipo in ("sintomas", "ambos"):
            st.subheader(tr("nut_tab_symptoms"))
            opts = tr("nut_symptom_opts")
            sint_sel = st.multiselect(tr("nut_symptoms"), list(opts), format_func=opts.get, key="nut_sintomas")
        salvar = st.checkbox(tr("history_save"), key="nut_salvar")
        enviado = st.form_submit_button(tr("run"))

    if enviado:
        informados = {k: v for k, v in valores.items() if v is not None}
        if not informados and not sint_sel:
            st.warning(tr("nothing_entered"))
            return
        try:
            conv, ub, notas = {}, {}, {}
            for nut, v in informados.items():
                conv[nut], ub[nut], notas[nut] = converter_foliar(nut, v, unidades[nut])
            compat, avisos = ne.faixas_compativeis(faixas, estagio)
            foliar = ne.avaliar_foliar(conv, ub, compat, notas) if informados else []
            ausencias = ne.ausencias_registradas(_complementares(cultura), _cobertura(cultura))
            sint = ne.associar_sintomas(_sintomas(cultura), sint_sel, cultura) if sint_sel else []
            amostr = _amostragem(cultura)
            ids = [txt(a["registro"].get("registro_id")) for r in foliar for a in r.avaliacoes]
            div = _divergencias(tuple(sorted(set(ids))))
        except BancoIndisponivel as e:
            aviso_banco("nutricao", e)
            return
        st.session_state[RES] = {"cultura": cultura, "uf": uf, "municipio": municipio, "estagio": estagio, "tipo": tipo,
                                 "informados": informados, "unidades": unidades, "foliar": foliar, "avisos": avisos,
                                 "ausencias": ausencias, "sintomas_sel": sint_sel, "sintomas": sint, "div": div, "amostragem": amostr}
        historico.registrar(st.session_state, "nutricao",
                            {"cultura": cultura, "estagio": estagio, "valores": informados, "sintomas": sint_sel},
                            {"cultura": cultura, "estagio": estagio, **{r.nutriente: r.status for r in foliar},
                             "sintomas": len(sint_sel)}, salvar_arquivo=salvar)

    res = st.session_state.get(RES)
    if res and res["cultura"] == cultura:
        _mostrar(res)
    painel_historico("nutricao")


def _tabela_foliar(foliar):
    linhas = []
    for r in foliar:
        if not r.avaliacoes:
            linhas.append({tr("nut_nutrient"): r.nutriente, tr("value"): numero(r.valor, 3), tr("unit"): r.unidade_base,
                           tr("reference_range"): "—", tr("status"): status(r.status), tr("source"): r.mensagem})
            continue
        for a in r.avaliacoes:
            reg = a["registro"]
            linhas.append({tr("nut_nutrient"): r.nutriente, tr("value"): numero(r.valor, 3), tr("unit"): r.unidade_base,
                           tr("reference_range"): a["faixa"], tr("source_class"): txt(reg.get("classificacao")),
                           tr("status"): status(a["status"]) + ("" if r.status == a["status"] else f" ({status(r.status)})"),
                           tr("nut_stage"): txt(reg.get("estagio")), tr("nut_part"): txt(reg.get("parte_planta")),
                           tr("source"): f"{txt(reg.get('fonte_id'))} — {txt(reg.get('secao'))}, p. {txt(reg.get('pagina_impressa'))}",
                           "registro": txt(reg.get("registro_id"))})
    return pd.DataFrame(linhas)


def _mostrar(res: dict):
    st.divider()
    est = tr("nut_stage_other") if res["estagio"] == ne.OUTRO_ESTAGIO else res["estagio"]
    st.subheader(f"📊 {tr('results')} — {res['cultura']} — {est}")
    usados = []
    if res["informados"]:
        st.markdown(f"### {tr('nut_tab_foliar')}")
        if res["estagio"] == ne.OUTRO_ESTAGIO or not any(r.avaliacoes for r in res["foliar"]):
            st.warning(ne.SEM_DADOS)
            if res["estagio"] == ne.OUTRO_ESTAGIO:
                st.caption(tr("nut_stage_warning"))
        for a in res["avisos"]:
            st.caption(f"ℹ️ {a}")
        cols = st.columns(4)
        for i, r in enumerate(res["foliar"]):
            with cols[i % 4]:
                st.markdown(f"**{r.nutriente}** · {numero(r.valor, 3)} {r.unidade_base}<br>{chip(r.status)}", unsafe_allow_html=True)
                if r.conversao:
                    st.caption(r.conversao)
                if r.mensagem == ne.SEM_DADOS:
                    st.caption(ne.SEM_DADOS)
        df = _tabela_foliar(res["foliar"])
        if not df.empty:
            tabela(df)
        pontos = []
        for r in res["foliar"]:
            for a in r.avaliacoes:
                reg = a["registro"]
                usados.append(reg)
                vmin, vmax = reg.get("valor_min"), reg.get("valor_max")
                if vmin is not None and vmax is not None:
                    pontos.append({"rotulo": f"{r.nutriente} · {txt(reg.get('fonte_id'))} {txt(reg.get('secao'))[:18]}", "valor": r.valor,
                                   "vmin": float(vmin), "vmax": float(vmax), "status": a["status"], "unidade": r.unidade_base})
        grafico_posicao(pontos, tr("chart_position"))
        if res["ausencias"]:
            with st.expander(tr("nut_absences"), expanded=not any(r.avaliacoes for r in res["foliar"])):
                tabela(pd.DataFrame(res["ausencias"])[["nutriente", "texto", "secao", "registro_id"]])
        if res["amostragem"] is not None and not res["amostragem"].empty:
            with st.expander("Protocolo de amostragem registrado"):
                tabela(res["amostragem"][["estagio", "parte_planta", "texto", "fonte_id", "secao"]])
                usados.extend(res["amostragem"].to_dict("records"))

    if res["sintomas_sel"]:
        st.markdown(f"### {tr('nut_tab_symptoms')}")
        st.warning(tr("nut_symptom_disclaimer"))
        if not res["sintomas"]:
            st.info(tr("nut_no_match"))
        opts = tr("nut_symptom_opts")
        for s in res["sintomas"]:
            usados.append(s)
            rot = tr("nut_specific") if s["especifico"] else tr("nut_general")
            st.markdown(
                f'<div class="st-card"><h4>{txt(s.get("nutriente")) or "—"} · {txt(s.get("classificacao"))}</h4>'
                f'<span class="st-origem">{rot}</span> <span class="meta">{tr("nut_matches")}: '
                f'{", ".join(opts[c] for c in s["coincidencias"])}</span>'
                f'<div style="margin-top:0.4rem">{txt(s.get("texto"))}</div>'
                f'<div class="meta">{txt(s.get("parte_planta"))} · {txt(s.get("fonte_id"))} — {txt(s.get("secao"))}, p. {txt(s.get("pagina_impressa"))}</div></div>',
                unsafe_allow_html=True)

    st.caption(tr("deterministic"))
    fontes = mostrar_fontes(usados)
    div_res = mostrar_divergencias(res["div"])
    botao_pdf(_pdf(res, fontes, div_res), f"{tr('pdf_name')}_nutricional", "pdf_nut")


def _pdf(res: dict, fontes: pd.DataFrame, div_res: pd.DataFrame) -> bytes:
    est = tr("nut_stage_other") if res["estagio"] == ne.OUTRO_ESTAGIO else res["estagio"]
    rel = Relatorio(f"SafraTech IA — {tr('nut_header')[2:].strip()}", f"{res['cultura']} — {est}",
                    "SafraTech IA — relatório gerado a partir dos bancos agronômicos; não substitui responsável técnico.")
    rel.secao(tr("inputs"))
    opts = tr("nut_symptom_opts")
    rel.pares([(tr("crop"), res["cultura"]), (tr("municipio"), f"{res['municipio']}/{res['uf']}" if res["municipio"] else "—"),
               (tr("nut_stage"), est), (tr("nut_type"), tr("nut_types").get(res["tipo"]))]
              + [(k, f"{numero(v, 3)} {res['unidades'][k]}") for k, v in res["informados"].items()]
              + ([(tr("nut_symptoms"), ", ".join(opts[s] for s in res["sintomas_sel"]))] if res["sintomas_sel"] else []))
    if res["informados"]:
        rel.secao(tr("nut_tab_foliar"))
        if res["estagio"] == ne.OUTRO_ESTAGIO or not any(r.avaliacoes for r in res["foliar"]):
            rel.paragrafo(ne.SEM_DADOS, aviso=True)
        for a in res["avisos"]:
            rel.paragrafo(a)
        df = _tabela_foliar(res["foliar"])
        if not df.empty:
            cols = [c for c in df.columns if c != "registro"]
            from reportlab.lib.units import cm
            larg = [1.4, 1.3, 1.3, 1.9, 2.1, 2.6, 2.4, 2.6, 2.4]
            rel.tabela(cols, df[cols].fillna("").astype(str).values.tolist(),
                       larguras=[w * cm for w in larg] if len(cols) == len(larg) else None)
        if res["ausencias"]:
            rel.secao(tr("nut_absences"))
            rel.tabela(["nutriente", "texto", "seção"], [[a["nutriente"], a["texto"], a["secao"]] for a in res["ausencias"]])
    if res["sintomas_sel"]:
        rel.secao(tr("nut_tab_symptoms"))
        rel.paragrafo(tr("nut_symptom_disclaimer"), aviso=True)
        if not res["sintomas"]:
            rel.paragrafo(tr("nut_no_match"))
        else:
            rel.tabela([tr("nut_nutrient"), "classe", "descrição", tr("nut_matches"), tr("source")],
                       [[txt(s.get("nutriente")), txt(s.get("classificacao")) + (" *" if s["especifico"] else ""), txt(s.get("texto")),
                         ", ".join(opts[c] for c in s["coincidencias"]), f"{txt(s.get('fonte_id'))} {txt(s.get('secao'))}"]
                        for s in res["sintomas"]])
            rel.paragrafo(f"* {tr('nut_specific')}")
    rel.secao(tr("divergences"))
    if div_res is None or div_res.empty:
        rel.paragrafo(tr("no_divergence"))
    else:
        rel.tabela(list(div_res.columns), div_res.astype(str).values.tolist())
    rel.secao(tr("sources"))
    if not fontes.empty:
        rel.tabela(["fonte_id", "seção", "página", "referência"], fontes[["fonte_id", "seção", "página", "referência"]].values.tolist())
    rel.paragrafo(tr("deterministic"))
    return rel.gerar()
