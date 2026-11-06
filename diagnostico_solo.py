"""Módulo 1 — Diagnóstico do Solo."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import solo_engine as se
from core.classificacao import INSUFICIENTE, faixa_texto, txt
from core.unidades import UNIDADES_SOLO, fatores_do_banco
from database import solo_queries as sq
from database.connections import BancoIndisponivel
from modules._comum import (aviso_banco, botao_pdf, faixa_favoravel, grafico_posicao, mostrar_divergencias, mostrar_fontes,
                            painel_historico, seletor_municipio, tabela)
from utils import historico
from utils.formatacao import chip, numero, status
from utils.textos import tr
from utils.relatorio_pdf import Relatorio
from utils.validacoes import validar

CULTURAS = ["Soja", "Milho", "Algodão", "Gergelim"]
CAMPOS_MACRO = [("ph", "pH"), ("p", "P"), ("k", "K"), ("ca", "Ca"), ("mg", "Mg"), ("s", "S (0–20 cm)"), ("mo", "MO"),
                ("ctc", "CTC pH 7"), ("v", "V%"), ("m", "m% (Al)"), ("n", "N")]
CAMPOS_MICRO = [("b", "B"), ("cu", "Cu"), ("fe", "Fe"), ("mn", "Mn"), ("zn", "Zn")]
METODOS_UI = {
    "ph": ["", "ph_agua", "ph_cacl2"],
    "p": ["", "p_mehlich", "p_prem", "p_resina"],
    "k": ["", "k_mehlich"],
    "micro": ["", "micro_mehlich", "micro_dtpa"],
    "b": ["", "b_agua_quente"],
}
RES = "solo_resultado"


# ---------------- consultas com cache (filtradas no PostgreSQL) ----------------
@st.cache_data(ttl=3600, show_spinner=False)
def _culturas_banco() -> list[str]:
    return sq.culturas_disponiveis()["cultura"].tolist()


@st.cache_data(ttl=3600, show_spinner=False)
def _texturas() -> list[str]:
    return sq.texturas_disponiveis()


@st.cache_data(ttl=3600, show_spinner=False)
def _conversoes() -> pd.DataFrame:
    return sq.conversoes_unidade()


@st.cache_data(ttl=3600, show_spinner=False)
def _referencias(parametros: tuple, culturas: tuple) -> pd.DataFrame:
    return sq.faixas_interpretacao(list(parametros), list(culturas))


@st.cache_data(ttl=3600, show_spinner=False)
def _divergencias(ids: tuple) -> pd.DataFrame:
    return sq.divergencias(list(ids))


def _campo(col, chave: str, rotulo: str):
    unidades = UNIDADES_SOLO[chave]
    a, b = col.columns([3, 2])
    v = a.number_input(rotulo, value=None, min_value=0.0, step=0.1, format="%.3f", key=f"solo_v_{chave}",
                       placeholder=tr("not_informed"))
    if len(unidades) > 1:
        u = b.selectbox(tr("unit"), unidades, key=f"solo_u_{chave}")
    else:
        u = unidades[0]
        b.markdown(f"<div style='padding-top:2.1rem;color:#81c784;font-size:0.85rem'>{u}</div>", unsafe_allow_html=True)
    return v, u


def render():
    st.markdown(f'<div class="header-badge">{tr("solo_badge")}</div>', unsafe_allow_html=True)
    st.header(tr("solo_header"))
    st.caption(tr("solo_intro"))

    try:
        texturas = _texturas()
    except BancoIndisponivel as e:
        aviso_banco("solo", e)
        return

    st.subheader(tr("solo_context"))
    cultura = st.selectbox(tr("crop"), CULTURAS, key="solo_cultura")
    uf, municipio, _ = seletor_municipio("solo")   # fora do formulário: a lista de municípios acompanha a UF
    with st.form("form_solo"):
        c1, c2, c3 = st.columns(3)
        textura = c1.selectbox(tr("solo_texture"), [""] + texturas, key="solo_textura",
                               format_func=lambda x: x or tr("solo_texture_none"))
        argila = c2.number_input(tr("solo_clay"), value=None, min_value=0.0, max_value=100.0, key="solo_argila",
                                 placeholder=tr("not_informed"))
        prem = c3.number_input(tr("solo_prem"), value=None, min_value=0.0, key="solo_prem", placeholder=tr("not_informed"))
        c4, c5, c6 = st.columns(3)
        camadas = tr("solo_layers")
        camada = c4.selectbox(tr("solo_layer"), list(camadas), format_func=camadas.get, key="solo_camada")
        sistemas = tr("solo_systems")
        sistema = c5.selectbox(tr("solo_system"), list(sistemas), format_func=sistemas.get, key="solo_sistema")
        biomas = tr("solo_biomes")
        bioma = c6.radio(tr("solo_biome"), list(biomas), index=2, format_func=biomas.get, horizontal=True, key="solo_bioma")

        st.subheader(tr("solo_methods"))
        nomes_m = tr("metodos")
        m = st.columns(5)
        met = {
            "ph": m[0].selectbox(tr("solo_m_ph"), METODOS_UI["ph"], format_func=nomes_m.get, key="solo_m_ph"),
            "p": m[1].selectbox(tr("solo_m_p"), METODOS_UI["p"], format_func=nomes_m.get, key="solo_m_p"),
            "k": m[2].selectbox(tr("solo_m_k"), METODOS_UI["k"], format_func=nomes_m.get, key="solo_m_k"),
            "micro": m[3].selectbox(tr("solo_m_micro"), METODOS_UI["micro"], format_func=nomes_m.get, key="solo_m_micro"),
            "b": m[4].selectbox(tr("solo_m_b"), METODOS_UI["b"], format_func=nomes_m.get, key="solo_m_b"),
        }

        st.subheader(tr("solo_values"))
        st.markdown(f"**{tr('solo_macros')}**")
        valores = {}
        cols = st.columns(3)
        for i, (k, rot) in enumerate(CAMPOS_MACRO):
            valores[k] = _campo(cols[i % 3], k, rot)
        s2040 = cols[len(CAMPOS_MACRO) % 3].number_input(tr("solo_s2040"), value=None, min_value=0.0, key="solo_s2040",
                                                          placeholder=tr("optional"))
        st.caption(tr("solo_n_note"))
        st.markdown(f"**{tr('solo_micros')}**")
        cols = st.columns(3)
        for i, (k, rot) in enumerate(CAMPOS_MICRO):
            valores[k] = _campo(cols[i % 3], k, rot)
        salvar = st.checkbox(tr("history_save"), key="solo_salvar")
        enviado = st.form_submit_button(tr("run"))

    if enviado:
        informados = {k: (v, u) for k, (v, u) in valores.items() if v is not None}
        erros = [f"{k}: {msg}" for k, (v, u) in informados.items() if (msg := validar(k, v, u))]
        if (msg := validar("argila", argila)):
            erros.append(f"argila: {msg}")
        if erros:
            st.error(f"{tr('invalid')}: " + "; ".join(erros))
            return
        if not informados:
            st.warning(tr("nothing_entered"))
            return
        metodos = {"ph": met["ph"], "p": met["p"], "k": met["k"], "b": met["b"],
                   "cu": met["micro"], "fe": met["micro"], "mn": met["micro"], "zn": met["micro"]}
        entrada = se.EntradaSolo(cultura=cultura, uf=uf, municipio=municipio, textura=textura or None, bioma_cerrado=bioma,
                                 sistema=sistema or None, argila=argila, prem=prem, camada=camada,
                                 metodos={k: v for k, v in metodos.items() if v}, valores=informados, s_20_40=s2040)
        try:
            culturas = se.culturas_aplicaveis(cultura, _culturas_banco())
            refs = _referencias(tuple(se.parametros_consulta()), tuple(culturas))
            fatores = fatores_do_banco(_conversoes())
            linhas = se.executar(entrada, refs, fatores, culturas)
            ids = se.registros_usados(linhas)
            div = _divergencias(tuple(ids))
        except BancoIndisponivel as e:
            aviso_banco("solo", e)
            return
        st.session_state[RES] = {"entrada": entrada, "linhas": linhas, "div": div, "fatores": fatores}
        historico.registrar(st.session_state, "solo",
                            {"cultura": cultura, "uf": uf, "municipio": municipio, "valores": informados},
                            {"cultura": cultura, "municipio": f"{municipio}/{uf}" if municipio else "",
                             **{l.rotulo: l.resultado.status for l in linhas}}, salvar_arquivo=salvar)

    res = st.session_state.get(RES)
    if res:
        _mostrar(res)
    painel_historico("solo")


def _linhas_resumo(linhas):
    out = []
    for l in linhas:
        g = next((g for g in l.resultado.grupos if g.status != INSUFICIENTE), None)
        out.append({
            "parâmetro": l.rotulo,
            tr("value"): numero(l.valor_comparado, 3),
            tr("unit"): l.unidade_comparada,
            tr("reference_range"): " | ".join(dict.fromkeys(g.faixa for g in l.resultado.grupos if g.faixa)) or "—",
            tr("source_class"): " | ".join(dict.fromkeys(g.classe for g in l.resultado.grupos if g.classe)) or "—",
            tr("status"): status(l.resultado.status),
        })
    return pd.DataFrame(out)


def _mostrar(res: dict):
    e, linhas, div = res["entrada"], res["linhas"], res["div"]
    st.divider()
    st.subheader(f"📊 {tr('results')} — {e.cultura}" + (f" — {e.municipio}/{e.uf}" if e.municipio else ""))
    st.info(tr("solo_no_reco"))
    if e.bioma_cerrado == "nao_sei":
        st.warning(tr("solo_biome_warn"))

    contagem = pd.Series([l.resultado.status for l in linhas]).value_counts()
    cols = st.columns(4)
    for i, sk in enumerate(["adequado", "atencao", "abaixo", "acima"]):
        cols[i].metric(status(sk), int(contagem.get(sk, 0)))
    cols = st.columns(3)
    for i, sk in enumerate(["divergente", "classe_fonte", "insuficiente"]):
        cols[i].metric(status(sk), int(contagem.get(sk, 0)))

    tabela(_linhas_resumo(linhas))

    pontos = []
    for l in linhas:
        for g in l.resultado.grupos:
            vmin, vmax = faixa_favoravel(g.registros)
            if vmin is not None and l.valor_comparado is not None:
                pontos.append({"rotulo": f"{l.rotulo} · {g.chave[0]} {txt(g.chave[1])[:22]}", "valor": l.valor_comparado,
                               "vmin": vmin, "vmax": vmax, "status": g.status, "unidade": l.unidade_comparada})
    grafico_posicao(pontos, tr("chart_position"))

    usados = []
    for l in linhas:
        with st.expander(f"{l.rotulo} — {numero(l.valor_comparado, 3)} {l.unidade_comparada} — {status(l.resultado.status)}",
                         expanded=False):
            st.markdown(chip(l.resultado.status), unsafe_allow_html=True)
            if l.conversao:
                st.caption(f"{tr('conversion')}: {l.conversao}")
            if l.calculado:
                st.caption(f"🧮 {tr('calc')}")
            if l.resultado.grupos:
                det = []
                for g in l.resultado.grupos:
                    r = g.registro_casado or g.registros[0]
                    usados.extend(g.registros)
                    det.append({
                        tr("status"): status(g.status),
                        tr("source_class"): g.classe or "—",
                        tr("reference_range"): g.faixa or "—",
                        tr("unit"): txt(r.get("unidade")),
                        "condição": " · ".join(x for x in [txt(r.get("metodo")), txt(r.get("tipo_solo")),
                                                                                                    txt(r.get("camada")), txt(r.get("regiao"))] if x),
                        tr("explanation"): g.motivo,
                        tr("source"): f"{txt(r.get('fonte_id'))} — {txt(r.get('secao'))}, p. {txt(r.get('pagina_impressa'))}",
                        "registro": txt(r.get("registro_id")),
                    })
                    escala = [f"{txt(x.get('classificacao'))}: {faixa_texto(x)}" for x in g.registros]
                    if len(escala) > 1:
                        det[-1]["escala da fonte"] = " | ".join(escala)
                tabela(pd.DataFrame(det))
            if l.resultado.limitacoes:
                st.markdown(f"**{tr('limitations')}:**")
                for lim in l.resultado.limitacoes:
                    st.markdown(f"- {lim}")
            if l.resultado.informativos:
                st.markdown(f"**{tr('solo_informative')}:**")
                tabela(pd.DataFrame([{tr("source_class"): txt(r.get("classificacao")), tr("reference_range"): faixa_texto(r),
                                      "método": txt(r.get("metodo")), tr("solo_reason"): r.get("motivo_nao_uso"),
                                      tr("source"): f"{txt(r.get('fonte_id'))} — {txt(r.get('secao'))}"} for r in l.resultado.informativos]))

    st.caption(tr("deterministic"))
    fontes = mostrar_fontes(usados)
    div_res = mostrar_divergencias(div)
    botao_pdf(_pdf(res, fontes, div_res), f"{tr('pdf_name')}_solo", "pdf_solo")


def _pdf(res: dict, fontes: pd.DataFrame, div_res: pd.DataFrame) -> bytes:
    e, linhas = res["entrada"], res["linhas"]
    rel = Relatorio(f"SafraTech IA — {tr('solo_header')[2:].strip()}", f"{e.cultura} {('— ' + e.municipio + '/' + e.uf) if e.municipio else ''}",
                    "SafraTech IA — relatório gerado a partir dos bancos agronômicos; não substitui responsável técnico.")
    rel.secao(tr("inputs"))
    nm = tr("metodos")
    rel.pares([(tr("crop"), e.cultura), (tr("municipio"), f"{e.municipio}/{e.uf}" if e.municipio else "—"),
               (tr("solo_texture"), e.textura or "—"), (tr("solo_clay"), numero(e.argila)),
               (tr("solo_prem"), numero(e.prem)), (tr("solo_layer"), tr("solo_layers").get(e.camada, e.camada)),
               (tr("solo_system"), tr("solo_systems").get(e.sistema or "", "—")),
               (tr("solo_biome"), tr("solo_biomes").get(e.bioma_cerrado)),
               (tr("solo_methods"), "; ".join(f"{se.ROTULOS.get(k, k)}: {nm.get(v, v)}" for k, v in e.metodos.items()) or "—")]
              + [(se.ROTULOS.get(k, k), f"{numero(v, 3)} {u}") for k, (v, u) in e.valores.items()]
              + ([(tr("solo_s2040"), numero(e.s_20_40))] if e.s_20_40 is not None else []))
    rel.secao(tr("results"))
    rel.paragrafo(tr("solo_no_reco"), aviso=True)
    df = _linhas_resumo(linhas)
    rel.tabela(list(df.columns), df.values.tolist())
    rel.secao(tr("explanation"))
    for l in linhas:
        partes = [f"{l.rotulo}: {status(l.resultado.status)}."]
        for g in l.resultado.grupos:
            r = g.registro_casado or g.registros[0]
            partes.append(f"[{txt(r.get('fonte_id'))} {txt(r.get('secao'))}] {g.classe or '—'} ({g.faixa or '—'}) — {g.motivo}.")
        if l.conversao:
            partes.append(f"{tr('conversion')}: {l.conversao}.")
        if l.resultado.limitacoes:
            partes.append(f"{tr('limitations')}: " + "; ".join(l.resultado.limitacoes) + ".")
        rel.paragrafo(" ".join(partes))
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
