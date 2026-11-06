"""Módulo 3 — Simulação de Plantio (ZARC oficial + simulação complementar por referências técnicas)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import simulacao, zarc
from core.classificacao import txt
from database import plantio_queries as pq
from database.connections import BancoIndisponivel
from modules._comum import _ufs, aviso_banco, botao_pdf, go, grafico, layout_escuro, painel_historico, seletor_municipio, tabela
from utils import historico
from utils.formatacao import CORES_RISCO, numero
from utils.textos import tr
from utils.referencias import resumo_divergencias
from utils.relatorio_pdf import Relatorio
from utils.validacoes import validar_periodo

RES = "pla_resultado"


@st.cache_data(ttl=3600, show_spinner=False)
def _culturas(geo: str) -> pd.DataFrame:
    return pq.culturas_do_municipio(geo)


@st.cache_data(ttl=3600, show_spinner=False)
def _opcoes(geo: str, cod: str) -> pd.DataFrame:
    return pq.opcoes_indicacao(geo, cod)


@st.cache_data(ttl=900, show_spinner=False)
def _indicacoes(geo, cod, safra, solo, ciclo, manejo) -> pd.DataFrame:
    return pq.indicacoes(geo, cod, safra, solo, ciclo, manejo)


@st.cache_data(ttl=3600, show_spinner=False)
def _exigencias(cultura_base: str) -> pd.DataFrame:
    return pq.exigencias(cultura_base)


@st.cache_data(ttl=3600, show_spinner=False)
def _municipio(geo: str) -> pd.DataFrame:
    return pq.municipio(geo)


@st.cache_data(ttl=3600, show_spinner=False)
def _divergencias(ids: tuple) -> pd.DataFrame:
    return pq.divergencias(list(ids))


@st.cache_data(ttl=3600, show_spinner=False)
def _fontes(ids: tuple) -> pd.DataFrame:
    return pq.fontes(list(ids))


def _sel(col, rotulo, df: pd.DataFrame, cod: str, rot: str, key: str):
    pares = df[[cod, rot]].drop_duplicates().sort_values(cod)
    cods = pares[cod].astype(str).tolist()
    nomes = dict(zip(cods, pares[rot].fillna("").astype(str)))
    return col.selectbox(rotulo, cods, format_func=lambda c: f"{nomes.get(c) or c} ({c})", key=key)


def render():
    st.markdown(f'<div class="header-badge">{tr("pla_badge")}</div>', unsafe_allow_html=True)
    st.header(tr("pla_header"))
    st.caption(tr("pla_intro"))
    try:
        _render()
    except BancoIndisponivel as e:
        aviso_banco("plantio", e)


def _render():
    _ufs()  # o ZARC depende do plantio_database: se indisponível, BancoIndisponivel é tratado em render()
    uf, municipio, geo = seletor_municipio("pla", obrigatorio=True)
    if not geo:
        return
    culturas = _culturas(geo)
    if culturas.empty:
        st.warning(tr("pla_no_mun_crop"))
        return
    st.caption(tr("pla_gergelim"))
    cods = culturas["cod_cultura"].astype(str).tolist()
    nomes = dict(zip(cods, culturas["nome_cultura"]))
    padrao = cods.index("12016720000011") if "12016720000011" in cods else 0
    cod = st.selectbox(tr("pla_crop_zarc"), cods, index=padrao, format_func=nomes.get, key=f"pla_cult_{geo}")
    op = _opcoes(geo, cod)
    if op.empty:
        st.warning(tr("pla_no_mun_crop"))
        return
    c1, c2, c3, c4 = st.columns(4)
    safras = sorted(op["safra_ini"].astype(int).unique().tolist())
    safra = c1.selectbox(tr("pla_safra"), safras, format_func=lambda s: f"{s}/{s + 1}", key=f"pla_safra_{geo}_{cod}")
    op_s = op[op["safra_ini"].astype(int) == safra]
    solo = _sel(c2, tr("pla_soil"), op_s, "cod_solo", "grupo_solo", f"pla_solo_{geo}_{cod}")
    op_so = op_s[op_s["cod_solo"].astype(str) == solo]
    ciclo = _sel(c3, tr("pla_cycle"), op_so, "cod_ciclo", "grupo_cultivar", f"pla_ciclo_{geo}_{cod}")
    op_c = op_so[op_so["cod_ciclo"].astype(str) == ciclo]
    manejo = _sel(c4, tr("pla_manejo"), op_c, "cod_outros_manejos", "manejo", f"pla_manejo_{geo}_{cod}")

    st.markdown(f"**{tr('pla_period')}**")
    st.caption(tr("pla_period_note"))
    d1, d2 = st.columns(2)
    ini = d1.number_input(tr("pla_dec_start"), min_value=1, max_value=36, value=28, step=1, key="pla_ini")
    fim = d2.number_input(tr("pla_dec_end"), min_value=1, max_value=36, value=33, step=1, key="pla_fim")

    with st.expander(tr("pla_optional"), expanded=False):
        o1, o2, o3 = st.columns(3)
        t_ar = o1.number_input(tr("pla_temp_air"), value=None, step=0.5, key="pla_tar", placeholder=tr("not_informed"))
        t_solo = o2.number_input(tr("pla_temp_soil"), value=None, step=0.5, key="pla_tsolo", placeholder=tr("not_informed"))
        chuva = o3.number_input(tr("pla_rain"), value=None, min_value=0.0, step=10.0, key="pla_chuva", placeholder=tr("not_informed"))
        umids = tr("pla_moistures")
        umid = st.selectbox(tr("pla_moisture"), list(umids), format_func=umids.get, key="pla_umid")
        notas = st.text_area(tr("pla_notes"), key="pla_notas", max_chars=1000)
    salvar = st.checkbox(tr("history_save"), key="pla_salvar")

    if st.button(tr("pla_run"), key="pla_btn"):
        if (msg := validar_periodo(ini, fim)):
            st.error(msg)
            return
        ind = _indicacoes(geo, cod, int(safra), solo, ciclo, manejo)
        decs = zarc.periodo(ini, fim)
        cultura_base = txt(culturas.loc[culturas["cod_cultura"].astype(str) == cod, "cultura_base"].iloc[0])
        exig = _exigencias(cultura_base)
        sim = simulacao.simular(exig, t_ar, t_solo, chuva)
        mun = _municipio(geo)
        ids_tec = [txt(i.registro.get("registro_id")) for i in sim["itens"]] + [txt(r.get("registro_id")) for r in sim["umidade_textos"]]
        div = _divergencias(tuple(sorted(set(i for i in ids_tec if i))))
        fontes_ids = sorted({"MAPA_ZARC_2026", "MAPA_DIC_TABUA_2026"} | {txt(i.registro.get("fonte_id")) for i in sim["itens"]}
                            | {txt(r.get("fonte_id")) for r in sim["umidade_textos"]})
        fontes = _fontes(tuple(f for f in fontes_ids if f))
        st.session_state[RES] = {
            "uf": uf, "municipio": municipio, "geo": geo, "cod": cod, "cultura": nomes[cod], "cultura_base": cultura_base,
            "safra": safra, "solo": solo, "ciclo": ciclo, "manejo": manejo, "ini": int(ini), "fim": int(fim), "decs": decs,
            "ind": ind, "sim": sim, "exig": exig, "t_ar": t_ar, "t_solo": t_solo, "chuva": chuva, "umid": umid, "notas": notas,
            "mun": mun, "div": div, "fontes": fontes,
        }
        aval = [zarc.avaliar_periodo(zarc.riscos_da_linha(r), decs).situacao for r in ind.to_dict("records")]
        historico.registrar(st.session_state, "plantio",
                            {"geocodigo": geo, "cod_cultura": cod, "safra": safra, "cod_solo": solo, "cod_ciclo": ciclo,
                             "manejo": manejo, "decendios": [int(ini), int(fim)]},
                            {"municipio": f"{municipio}/{uf}", "cultura": nomes[cod], "linhas_zarc": len(ind),
                             "situacao": ", ".join(sorted(set(aval))) or "sem_linha"}, salvar_arquivo=salvar)

    res = st.session_state.get(RES)
    if res and res["geo"] == geo and res["cod"] == cod:
        _mostrar(res)
    painel_historico("plantio")


def _heatmap(ind: pd.DataFrame, decs: list[int]):
    longo = zarc.tabela_longa(ind)
    linhas = list(dict.fromkeys(longo["linha"]))
    if go is None:
        tabela(longo.pivot(index="linha", columns="decendio", values="rotulo").reset_index())
        return
    z, texto = [], []
    for l in linhas:
        sub = longo[longo["linha"] == l].sort_values("decendio")
        z.append(sub["risco"].tolist())
        texto.append(["—" if r == 0 else f"{r}" for r in sub["risco"]])
    escala = [[0, CORES_RISCO[0]], [0.25, CORES_RISCO[0]], [0.25, CORES_RISCO[20]], [0.625, CORES_RISCO[20]],
              [0.625, CORES_RISCO[30]], [0.875, CORES_RISCO[30]], [0.875, CORES_RISCO[40]], [1, CORES_RISCO[40]]]
    fig = go.Figure(go.Heatmap(z=z, x=list(range(1, 37)), y=linhas, zmin=0, zmax=40, colorscale=escala, showscale=False,
                               text=texto, texttemplate="%{text}", xgap=2, ygap=2,
                               hovertemplate=f"{tr('pla_dec')} %{{x}}<br>%{{y}}<br>%{{text}}<extra></extra>"))
    blocos, atual = [], None
    for d in decs:
        if atual and d == atual[1] + 1:
            atual[1] = d
        else:
            atual = [d, d]
            blocos.append(atual)
    for a, b in blocos:
        fig.add_shape(type="rect", x0=a - 0.5, x1=b + 0.5, y0=-0.5, y1=len(linhas) - 0.5, line=dict(color="#e8f5e9", width=2, dash="dot"))
    fig.update_xaxes(dtick=1, title=tr("pla_dec"))
    fig.update_layout(title=dict(text=f"ZARC — {tr('pla_risk')} (%) · — = {tr('pla_no_ind')}", font=dict(size=13)))
    grafico(layout_escuro(fig, altura=max(230, 46 * len(linhas) + 120)))


def _mostrar(res: dict):
    st.divider()
    ind = res["ind"]
    st.subheader(f"📊 {res['cultura']} — {res['municipio']}/{res['uf']} — {res['safra']}/{res['safra'] + 1}")
    st.markdown(f'<span class="st-origem">{tr("pla_official")}</span>', unsafe_allow_html=True)
    if not res["mun"].empty and txt(res["mun"].iloc[0].get("observacao")):
        st.caption(f"{tr('pla_mun_obs')}: {txt(res['mun'].iloc[0].get('observacao'))}")
    if ind.empty:
        st.warning(tr("pla_no_combo"))
    else:
        st.info(tr("pla_no_ind_note"))
        if len(ind) > 1:
            st.caption(tr("pla_lines_note"))
        _heatmap(ind, res["decs"])
        cols = st.columns(min(4, len(ind)))
        for i, row in enumerate(ind.to_dict("records")):
            av = zarc.avaliar_periodo(zarc.riscos_da_linha(row), res["decs"])
            nm = txt(row.get("cod_nm"))
            titulo = f"{txt(row.get('manejo'))}" + (f" · NM{nm}" if nm not in ("", "0") else "")
            with cols[i % len(cols)]:
                st.metric(titulo, f"{av.melhor_risco}%" if av.melhor_risco is not None else tr("pla_no_ind"),
                          help=f"{tr('pla_risk')}: {av.melhor_risco}–{av.pior_risco}%" if av.melhor_risco is not None else None)
            msg = tr(f"pla_sit_{av.situacao}")
            (st.success if av.situacao == zarc.INDICADO_TODO else st.warning if av.situacao == zarc.INDICADO_PARCIAL else st.error)(f"{titulo}: {msg}")
        janelas = []
        for row in ind.to_dict("records"):
            nm = txt(row.get("cod_nm"))
            for j in zarc.resumo_linha(row)["janelas"]:
                janelas.append({tr("pla_line"): txt(row.get("manejo")) + (f" · NM{nm}" if nm not in ("", "0") else ""),
                                tr("pla_dec"): f"{j['inicio']}–{j['fim']}" if j["inicio"] != j["fim"] else str(j["inicio"]),
                                tr("pla_risk"): f"{j['risco']}%", "n": len(j["decendios"])})
        st.markdown(f"**{tr('pla_windows')}**")
        tabela(pd.DataFrame(janelas))
        r0 = ind.iloc[0]
        st.caption(f"{tr('pla_ordinance')}: {txt(r0.get('portaria_numero'))} ({txt(r0.get('portaria'))}) — {tr('pla_published')} "
                   f"{txt(r0.get('portaria_data'))} · MAPA — Zoneamento Agrícola de Risco Climático · "
                   f"{tr('pla_soil')}: {txt(r0.get('grupo_solo'))} · {tr('pla_cycle')}: {txt(r0.get('grupo_cultivar'))} · "
                   f"clima: {txt(r0.get('clima'))} · indicacao_id: {', '.join(map(str, ind['indicacao_id']))}")

    st.markdown(f"### {tr('pla_sim_header')}")
    st.warning(tr("pla_disclaimer"))
    sim = res["sim"]
    informados = [(tr("pla_temp_air"), res["t_ar"]), (tr("pla_temp_soil"), res["t_solo"]), (tr("pla_rain"), res["chuva"])]
    if any(v is not None for _, v in informados) or res["umid"] or res["notas"]:
        st.markdown(f'<span class="st-origem">{tr("pla_user")}</span>', unsafe_allow_html=True)
        for rot, v in informados:
            if v is not None:
                st.markdown(f"- {rot}: **{numero(v)}**")
        if res["umid"]:
            st.markdown(f"- {tr('pla_moisture')}: **{tr('pla_moistures')[res['umid']]}**")
        if res["notas"]:
            st.markdown(f"- {tr('pla_notes')}: {res['notas']}")
    else:
        st.caption(tr("pla_sim_none"))
    for item in sim["itens"]:
        r = item.registro
        icone = {"favoravel": "✅", "desfavoravel": "⚠️", "neutra": "➖", "descritiva": "ℹ️"}[item.leitura]
        st.markdown(f'<div class="st-card"><span class="st-origem">{tr("pla_sim")}</span>'
                    f'<span class="st-origem">{tr("pla_technical")}</span>'
                    f'<div style="margin-top:0.4rem">{icone} {item.texto}</div>'
                    f'<div class="meta">{txt(r.get("estagio"))} · {txt(r.get("fonte_id"))} — {txt(r.get("secao"))}, p. {txt(r.get("pagina_impressa"))} · {txt(r.get("registro_id"))}</div></div>',
                    unsafe_allow_html=True)
    if sim["sem_referencia"]:
        st.caption(tr("pla_sim_noref", itens=", ".join(sim["sem_referencia"])))
    if res["umid"] and sim["umidade_textos"]:
        for r in sim["umidade_textos"]:
            st.markdown(f'<div class="st-card"><span class="st-origem">{tr("pla_technical")}</span>'
                        f'<h4>{txt(r.get("parametro"))}</h4><div>{txt(r.get("texto"))}</div>'
                        f'<div class="meta">{txt(r.get("fonte_id"))} — {txt(r.get("secao"))}</div></div>', unsafe_allow_html=True)
    with st.expander(tr("pla_req")):
        exig = res["exig"]
        if exig.empty:
            st.caption("—")
        else:
            tabela(exig[["categoria", "parametro", "estagio", "operador_min", "valor_min", "operador_max", "valor_max", "valor", "unidade",
                         "fonte_id", "secao", "registro_id"]])
    with st.expander(tr("sources")):
        tabela(res["fontes"])
    div = resumo_divergencias(res["div"])
    with st.expander(tr("divergences"), expanded=not div.empty):
        if div.empty:
            st.caption(tr("no_divergence"))
        else:
            tabela(div)
    botao_pdf(_pdf(res, div), f"{tr('pdf_name')}_plantio", "pdf_pla")


def _pdf(res: dict, div: pd.DataFrame) -> bytes:
    ind = res["ind"]
    rel = Relatorio(f"SafraTech IA — {tr('pla_header')[2:].strip()}",
                    f"{res['cultura']} — {res['municipio']}/{res['uf']} — {res['safra']}/{res['safra'] + 1}",
                    "SafraTech IA — ZARC oficial (MAPA) + simulação complementar. Não é previsão do tempo nem garantia de produtividade.")
    rel.secao(tr("inputs"))
    r0 = ind.iloc[0].to_dict() if not ind.empty else {}
    rel.pares([(tr("municipio"), f"{res['municipio']}/{res['uf']} (IBGE {res['geo']})"), (tr("pla_crop_zarc"), res["cultura"]),
               (tr("pla_safra"), f"{res['safra']}/{res['safra'] + 1}"),
               (tr("pla_soil"), f"{txt(r0.get('grupo_solo')) or ''} ({res['solo']})"),
               (tr("pla_cycle"), f"{txt(r0.get('grupo_cultivar')) or ''} ({res['ciclo']})"),
               (tr("pla_manejo"), f"{txt(r0.get('manejo')) or ''} ({res['manejo']})"),
               (tr("pla_period"), f"{res['ini']}–{res['fim']}")])
    rel.secao(tr("pla_official"))
    if ind.empty:
        rel.paragrafo(tr("pla_no_combo"), aviso=True)
    else:
        rel.paragrafo(tr("pla_no_ind_note"), aviso=True)
        cab = [tr("pla_line")] + [str(d) for d in range(1, 37)]
        linhas = []
        for row in ind.to_dict("records"):
            nm = txt(row.get("cod_nm"))
            linhas.append([txt(row.get("manejo")) + (f" NM{nm}" if nm not in ("", "0") else "")]
                          + ["—" if r == 0 else str(r) for r in zarc.riscos_da_linha(row)])
        from reportlab.lib.units import cm
        rel.tabela(cab, linhas, larguras=[2.6 * cm] + [0.42 * cm] * 36, compacta=True)
        for row in ind.to_dict("records"):
            av = zarc.avaliar_periodo(zarc.riscos_da_linha(row), res["decs"])
            nm = txt(row.get("cod_nm"))
            per = ", ".join(f"{d}: {'sem indicação' if r == 0 else str(r) + '%'}" for d, r in av.riscos_no_periodo.items())
            rel.paragrafo(f"{txt(row.get('manejo'))}{' NM' + nm if nm not in ('', '0') else ''}: {tr('pla_sit_' + av.situacao)} ({per})")
        rel.paragrafo(f"{tr('pla_ordinance')}: {txt(r0.get('portaria_numero'))} ({txt(r0.get('portaria'))}), "
                      f"{tr('pla_published')} {txt(r0.get('portaria_data'))}. MAPA — ZARC. indicacao_id: {', '.join(map(str, ind['indicacao_id']))}.")
    rel.secao(tr("pla_sim_header"))
    rel.paragrafo(tr("pla_disclaimer"), aviso=True)
    usr = [(tr("pla_temp_air"), res["t_ar"]), (tr("pla_temp_soil"), res["t_solo"]), (tr("pla_rain"), res["chuva"])]
    pares = [(f"[{tr('pla_user')[2:].strip()}] {k}", numero(v)) for k, v in usr if v is not None]
    if res["umid"]:
        pares.append((f"[{tr('pla_user')[2:].strip()}] {tr('pla_moisture')}", tr("pla_moistures")[res["umid"]]))
    if res["notas"]:
        pares.append((f"[{tr('pla_user')[2:].strip()}] {tr('pla_notes')}", res["notas"]))
    if pares:
        rel.pares(pares)
    for item in res["sim"]["itens"]:
        r = item.registro
        rel.paragrafo(f"[{tr('pla_sim')[2:].strip()} / {tr('pla_technical')[2:].strip()}] {item.texto} "
                      f"({txt(r.get('fonte_id'))} {txt(r.get('secao'))}, {txt(r.get('registro_id'))})")
    rel.secao(tr("divergences"))
    if div is None or div.empty:
        rel.paragrafo(tr("no_divergence"))
    else:
        rel.tabela(list(div.columns), div.astype(str).values.tolist())
    rel.secao(tr("sources"))
    f = res["fontes"]
    if not f.empty:
        rel.tabela(["fonte_id", "referência"], f[["fonte_id", "referencia_abnt"]].astype(str).values.tolist())
    return rel.gerar()
