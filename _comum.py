"""Componentes de interface compartilhados pelos módulos."""
from __future__ import annotations

import re
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from core.classificacao import num, txt
from database import connections
from database.connections import BancoIndisponivel
from utils import historico
from utils.formatacao import CORES_STATUS, chip
from utils.textos import tr
from utils.referencias import resumo_divergencias, tabela_fontes

try:  # Plotly é opcional: sem ele os gráficos viram tabelas
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None

_FAVORAVEL = re.compile(r"adequad|preferid|boa fertilidade|alvo|sem problemas|altas produtividades|^normal$|suficiência|intervalo adequado|ótim",
                        re.IGNORECASE)

CSS_EXTRA = """
<style>
.st-chip {display:inline-block;padding:0.15rem 0.6rem;border:1px solid;border-radius:14px;font-size:0.78rem;
          font-family:'Inter',sans-serif;color:#e8f5e9;white-space:nowrap}
.st-card {background:linear-gradient(135deg,#0d2a1a,#133d26);border:1px solid #1e5c35;border-radius:16px;
          padding:0.9rem 1.1rem;margin-bottom:0.6rem;box-shadow:0 4px 24px rgba(0,0,0,0.35)}
.st-card h4 {font-family:'Syne',sans-serif;color:#a5d6a7;margin:0 0 0.3rem 0;font-size:1rem}
.st-card .valor {font-family:'Syne',sans-serif;color:#69f0ae;font-size:1.35rem;font-weight:700}
.st-card .meta {color:#81c784;font-size:0.78rem}
.st-origem {display:inline-block;font-size:0.72rem;letter-spacing:0.05em;padding:0.1rem 0.5rem;border-radius:10px;
            border:1px solid #388e3c;color:#b9f6ca;margin-right:0.3rem}
</style>
"""


# ---------------- tabelas e gráficos (compatível com versões novas e antigas do Streamlit) ----------------
def tabela(df: pd.DataFrame, **kw):
    try:
        st.dataframe(df, hide_index=True, width="stretch", **kw)
    except Exception:  # versões antigas do Streamlit não aceitam width="stretch"
        st.dataframe(df, hide_index=True, use_container_width=True, **kw)


def grafico(fig):
    try:
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    except Exception:  # versões antigas do Streamlit
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def layout_escuro(fig, altura: int = 360):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,34,24,0.6)", font=dict(color="#c8e6c9", family="Inter"),
                      height=altura, margin=dict(l=10, r=10, t=40, b=10))
    fig.update_xaxes(gridcolor="#1a4a2a", zerolinecolor="#1a4a2a")
    fig.update_yaxes(gridcolor="#1a4a2a", zerolinecolor="#1a4a2a")
    return fig


def grafico_posicao(itens: list[dict], titulo: str):
    """itens: {rotulo, valor, vmin, vmax, status}. Mostra a posição normalizada do valor na faixa adequada da fonte."""
    pts = [i for i in itens if i.get("vmin") is not None and i.get("vmax") is not None and i["vmax"] > i["vmin"]]
    if not pts:
        return
    if go is None:
        tabela(pd.DataFrame(pts))
        return
    pos = [(p["valor"] - p["vmin"]) / (p["vmax"] - p["vmin"]) for p in pts]
    pos_plot = [max(-0.6, min(1.6, x)) for x in pos]
    fig = go.Figure()
    fig.add_vrect(x0=0, x1=1, fillcolor="#2e7d32", opacity=0.18, line_width=0)
    fig.add_trace(go.Scatter(
        x=pos_plot, y=[p["rotulo"] for p in pts], mode="markers",
        marker=dict(size=14, color=[CORES_STATUS.get(p["status"], "#607d8b") for p in pts], line=dict(color="#e8f5e9", width=1)),
        customdata=[[p["valor"], p["vmin"], p["vmax"], p.get("unidade", "")] for p in pts],
        hovertemplate="%{y}<br>%{customdata[0]:.3g} %{customdata[3]}<br>[%{customdata[1]:.3g} – %{customdata[2]:.3g}]<extra></extra>"))
    fig.update_xaxes(range=[-0.7, 1.7], tickvals=[0, 1], ticktext=[tr("lower"), tr("upper")])
    fig.update_layout(title=dict(text=titulo, font=dict(size=13)), showlegend=False)
    grafico(layout_escuro(fig, altura=max(220, 34 * len(pts) + 90)))
    st.caption(tr("chart_position"))


def faixa_favoravel(registros: list[dict]) -> tuple[Optional[float], Optional[float]]:
    for r in registros:
        if _FAVORAVEL.search(txt(r.get("classificacao"))) and num(r.get("valor_min")) is not None and num(r.get("valor_max")) is not None:
            return num(r.get("valor_min")), num(r.get("valor_max"))
    return None, None


# ---------------- bancos ----------------
def aviso_banco(chave: str, erro: Exception):
    st.error(tr("db_unavailable", banco=connections.BANCOS[chave]["nome"]))
    st.caption(f"{erro}")
    st.caption(tr("db_hint", env=connections.BANCOS[chave]["env"]))


def protegido(chave: str, func: Callable, *args, **kw):
    """Executa a função do módulo; se o banco estiver indisponível mostra o aviso sem derrubar o app."""
    try:
        return func(*args, **kw)
    except BancoIndisponivel as e:
        aviso_banco(chave, e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _ufs() -> list[str]:
    from database import plantio_queries as pq
    return pq.ufs()


@st.cache_data(ttl=3600, show_spinner=False)
def _municipios(uf: str) -> pd.DataFrame:
    from database import plantio_queries as pq
    return pq.municipios(uf)


def seletor_municipio(chave: str, obrigatorio: bool = False) -> tuple[str, str, Optional[str]]:
    """UF e município a partir do plantio_database; se indisponível, campos de texto. Retorna (uf, municipio, geocodigo)."""
    c1, c2 = st.columns([1, 3])
    try:
        ufs = _ufs()
    except BancoIndisponivel:
        uf = c1.text_input(tr("uf"), key=f"{chave}_uf_txt")
        mun = c2.text_input(tr("municipio"), key=f"{chave}_mun_txt")
        return uf, mun, None
    opcoes_uf = ufs if obrigatorio else [""] + ufs
    uf = c1.selectbox(tr("uf"), opcoes_uf, key=f"{chave}_uf",
                      index=opcoes_uf.index("GO") if obrigatorio and "GO" in opcoes_uf else 0)
    if not uf:
        c2.selectbox(tr("municipio"), [""], key=f"{chave}_mun_vazio", disabled=True)
        return "", "", None
    df = _municipios(uf)
    nomes = df["municipio"].tolist()
    geos = df["geocodigo"].astype(str).tolist()
    opcoes = list(range(len(nomes))) if obrigatorio else [-1] + list(range(len(nomes)))
    idx = c2.selectbox(tr("municipio"), opcoes, key=f"{chave}_mun_{uf}",
                       format_func=lambda i: "" if i == -1 else nomes[i])
    if idx is None or idx == -1:
        return uf, "", None
    return uf, nomes[idx], geos[idx]


# ---------------- transparência ----------------
def mostrar_fontes(registros: list[dict]):
    df = tabela_fontes(registros)
    with st.expander(tr("sources"), expanded=False):
        if df.empty:
            st.caption("—")
        else:
            tabela(df)
    return df


def mostrar_divergencias(df_div: Optional[pd.DataFrame]):
    res = resumo_divergencias(df_div)
    with st.expander(tr("divergences"), expanded=not res.empty):
        if res.empty:
            st.caption(tr("no_divergence"))
        else:
            tabela(res)
    return res


def card(titulo: str, valor_html: str, status_key: Optional[str], meta: str = ""):
    st.markdown(f'<div class="st-card"><h4>{titulo}</h4><span class="valor">{valor_html}</span> '
                f'{chip(status_key) if status_key else ""}'
                f'{"<div class=meta>" + meta + "</div>" if meta else ""}</div>', unsafe_allow_html=True)


def botao_pdf(pdf: bytes, nome: str, chave: str):
    st.download_button(tr("pdf_btn"), data=pdf, file_name=f"{nome}.pdf", mime="application/pdf", key=chave)


def painel_historico(modulo: str):
    itens = [i for i in historico.listar(st.session_state) if i["modulo"] == modulo]
    with st.expander(tr("history"), expanded=False):
        if not itens:
            st.caption(tr("history_empty"))
            return
        tabela(pd.DataFrame([{"data/hora": i["data_hora"], **{k: v for k, v in i["resumo"].items() if not isinstance(v, (dict, list))}}
                             for i in itens]))
