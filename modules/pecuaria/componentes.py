"""Componentes de interface compartilhados pelos três submódulos de Pecuária (mesma identidade visual do SafraTech)."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Optional, Sequence

import pandas as pd
import streamlit as st

from database import pecuaria_queries as pq
from database.connections import BancoIndisponivel
from modules._comum import aviso_banco, grafico, layout_escuro, tabela
from utils.formatacao import CORES_STATUS

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None

CORES_VEREDITO = {"viavel": "#2e7d32", "atencao": "#f9a825", "inviavel": "#c62828",
                  "adequado": "#2e7d32", "abaixo": "#c62828", "acima": "#ef6c00", "insuficiente": "#607d8b",
                  "divergente": "#8e24aa", "esperar": "#2e7d32", "vender agora": "#ef6c00", "indiferente": "#607d8b"}

ROTULO_STATUS = {"abaixo": "🔻 Abaixo da referência", "adequado": "✅ Próximo da referência / dentro da faixa",
                 "acima": "🔺 Acima da referência", "insuficiente": "❔ Dados insuficientes",
                 "divergente": "⚖️ Referências divergentes"}

TIPO_DADO = {
    "experimental": "resultado experimental", "modelo_fisico": "modelo físico (unidade de pesquisa)",
    "meta_ou_premissa": "meta ou premissa da fonte", "citacao_secundaria": "citação de outro trabalho",
    "recomendacao_tecnica": "recomendação técnica", "exemplo_ilustrativo": "exemplo ilustrativo",
    "levantamento_painel": "levantamento por painel (fazenda típica)", "norma_ou_definicao": "norma ou definição",
}

SEXO_REF = {"macho": "macho", "macho_inteiro": "macho inteiro", "macho_castrado": "macho castrado", "femea": "fêmea",
            "touro": "touro", "touruno": "touruno", "misto": "misto", "nao_especificado": "não especificado",
            "nao_aplicavel": "não se aplica"}

TERMO_BUSCA_RACA = {
    "NELORE_PO": "nelore", "NELORE_COMERCIAL": "nelore", "NELORADO": "nelore", "F1_PARDO_SUICO_X_NELORE": "pardo suíço",
    "ANGUS_X_NELORE": "angus", "PANTANEIRO": "pantaneiro", "BRITANICAS": "britânicas", "CONTINENTAIS_EUROPEIAS": "continentais",
    "ZEBUINOS_GERAL": "zebuínos", "TAURINOS_GERAL": "taurinos",
}


# ------------------------------------------------------------------ formatação
def moeda(v: Optional[float], casas: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    s = f"{abs(v):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"−R$ {s}" if v < 0 else f"R$ {s}"


def num(v: Optional[float], casas: int = 2, sufixo: str = "") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s}{sufixo}"


def texto(v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def ano_fonte(v: Any) -> str:
    return texto(v) or "ano não identificado na fonte"


def assinatura(*partes) -> str:
    """Hash das entradas: usado para saber se o resultado exibido ainda corresponde aos dados da tela."""
    return hashlib.sha1(json.dumps(partes, default=str, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------ carregamento com cache
@st.cache_data(ttl=3600, show_spinner=False)
def carregar(consulta: str, banco: str) -> pd.DataFrame:
    """Executa uma consulta de database.pecuaria_queries (sem parâmetros além do banco) com cache."""
    return getattr(pq, consulta)(banco)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_fontes(banco: str, codigos: tuple) -> pd.DataFrame:
    return pq.fontes(banco, codigos)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_formulas(banco: str, codigos: tuple) -> pd.DataFrame:
    return pq.formulas(banco, codigos)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_divergencias(banco: str, ids: tuple) -> pd.DataFrame:
    return pq.divergencias(banco, ids)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_perguntas(banco: str, termo: str, temas: tuple) -> pd.DataFrame:
    return pq.perguntas_relacionadas(banco, termo, temas)


def dados_ou_aviso(banco: str, consultas: Sequence[str]) -> Optional[dict]:
    """Carrega as consultas; se o banco estiver indisponível mostra o aviso e devolve None (os outros módulos seguem)."""
    try:
        return {c: carregar(c, banco) for c in consultas}
    except BancoIndisponivel as e:
        aviso_banco(banco, e)
        return None


# ------------------------------------------------------------------ cabeçalho e cards
def cabecalho(badge: str, titulo: str, pergunta: str, banco: str):
    st.markdown(f'<div class="header-badge">{badge}</div>', unsafe_allow_html=True)
    st.header(titulo)
    st.caption(f"**Pergunta central:** {pergunta}  ·  Banco: `{pq_nome(banco)}`")


def pq_nome(banco: str) -> str:
    from database.connections import BANCOS
    return BANCOS[banco]["nome"]


def card_veredito(chave: str, titulo: str, texto_html: str):
    cor = CORES_VEREDITO.get(chave, "#607d8b")
    st.markdown(f'<div class="st-card" style="border-left:6px solid {cor}"><h4>{titulo}</h4>'
                f'<div style="color:#e8f5e9;font-size:0.95rem">{texto_html}</div></div>', unsafe_allow_html=True)


def chip_status(chave: str) -> str:
    cor = CORES_STATUS.get(chave, CORES_VEREDITO.get(chave, "#607d8b"))
    return (f'<span class="st-chip" style="border-color:{cor};background:{cor}33">'
            f'{ROTULO_STATUS.get(chave, chave)}</span>')


def metricas(itens: Sequence[tuple[str, str]], colunas: int = 4, ajuda: Optional[dict] = None):
    for i in range(0, len(itens), colunas):
        cols = st.columns(colunas)
        for c, (rot, val) in zip(cols, itens[i:i + colunas]):
            c.metric(rot, val, help=(ajuda or {}).get(rot))


def tabela_premissas(pares: Sequence[tuple[str, str, str]]):
    """pares: (premissa, valor, origem)."""
    tabela(pd.DataFrame([{"Premissa": a, "Valor": b, "Origem": c} for a, b, c in pares]))


def aviso_resultado_desatualizado():
    st.info("Os dados de entrada foram alterados depois da última análise. Clique no botão para recalcular.")


# ------------------------------------------------------------------ referências técnicas
def rotulo_referencia(r: dict, valor: str) -> str:
    partes = [valor, texto(r.get("parametro"))]
    det = " · ".join(x for x in [texto(r.get("raca")), SEXO_REF.get(texto(r.get("sexo")), texto(r.get("sexo"))),
                                 texto(r.get("sistema")), texto(r.get("regiao"))] if x)
    pag = f"p. {texto(r.get('pagina_pdf'))}" if texto(r.get("pagina_pdf")) else "página não indicada"
    return f"{partes[0]} — {partes[1]} ({det}) · {texto(r.get('fonte_codigo'))}, {pag}"


def valor_rendimento_txt(r: dict) -> str:
    v, a, b = r.get("valor_numerico"), r.get("valor_min"), r.get("valor_max")
    if v is not None and not (isinstance(v, float) and math.isnan(v)):
        return f"{num(float(v), 1)}%"
    return f"{num(float(a), 1)}–{num(float(b), 1)}%"


def detalhes_referencia(r: dict):
    linhas = [
        f"**Registro:** {texto(r.get('id_registro'))} · **Tipo de dado:** {TIPO_DADO.get(texto(r.get('tipo_dado')), texto(r.get('tipo_dado')))}",
        f"**Fonte:** {texto(r.get('fonte_titulo'))} — {texto(r.get('fonte_instituicao'))} ({ano_fonte(r.get('fonte_ano'))}), "
        f"p. {texto(r.get('pagina_pdf')) or '—'} do PDF"
        + (f" / p. {texto(r.get('pagina_impressa'))} impressa" if texto(r.get("pagina_impressa")) else "")
        + (f" · {texto(r.get('localizacao'))}" if texto(r.get("localizacao")) else ""),
    ]
    if texto(r.get("condicoes_aplicacao")):
        linhas.append(f"**Condições de aplicação:** {texto(r.get('condicoes_aplicacao'))}")
    if texto(r.get("periodo_referencia")):
        linhas.append(f"**Período de referência:** {texto(r.get('periodo_referencia'))}")
    st.caption("  \n".join(linhas))


def tabela_referencias(regs: Iterable[dict], extra: Optional[dict] = None) -> pd.DataFrame:
    """Tabela padronizada das referências técnicas usadas (fonte, instituição, ano, página, condições)."""
    linhas = []
    for r in regs:
        d = {
            "registro": texto(r.get("id_registro")),
            "parâmetro": texto(r.get("parametro")),
            "raça/genótipo": texto(r.get("raca")),
            "sexo": SEXO_REF.get(texto(r.get("sexo")), texto(r.get("sexo"))),
            "sistema": texto(r.get("sistema")),
            "tipo de dado": TIPO_DADO.get(texto(r.get("tipo_dado")), texto(r.get("tipo_dado"))),
            "fonte": texto(r.get("fonte_codigo")),
            "instituição": texto(r.get("fonte_instituicao")),
            "ano": ano_fonte(r.get("fonte_ano")),
            "página (PDF)": texto(r.get("pagina_pdf")),
            "condições de aplicação": texto(r.get("condicoes_aplicacao")),
        }
        if extra:
            d.update({k: f(r) for k, f in extra.items()})
        linhas.append(d)
    return pd.DataFrame(linhas)


def bloco_fontes(banco: str, referencias: Sequence[dict], formulas: Sequence[str], titulo: str = "📚 Fontes e referências técnicas"
                 ) -> dict:
    """Expander com referências usadas, documentos (título, autores, instituição, ano, ABNT), fórmulas e divergências.
    Devolve os DataFrames para o PDF."""
    refs_df = tabela_referencias(referencias)
    codigos = {texto(r.get("fonte_codigo")) for r in referencias}
    try:
        form_df = carregar_formulas(banco, tuple(sorted(formulas)))
        codigos |= set(form_df["fonte_codigo"].astype(str)) if not form_df.empty else set()
        fontes_df = carregar_fontes(banco, tuple(sorted(c for c in codigos if c)))
        div_df = carregar_divergencias(banco, tuple(sorted(texto(r.get("id_registro")) for r in referencias)))
    except BancoIndisponivel as e:
        aviso_banco(banco, e)
        return {"referencias": refs_df, "fontes": pd.DataFrame(), "formulas": pd.DataFrame(), "divergencias": pd.DataFrame()}
    with st.expander(titulo, expanded=False):
        if not refs_df.empty:
            st.markdown("**Referências técnicas utilizadas**")
            tabela(refs_df)
        if not fontes_df.empty:
            st.markdown("**Documentos de origem**")
            tabela(pd.DataFrame([{
                "fonte": texto(f.get("fonte_codigo")), "título": texto(f.get("titulo")), "autores": texto(f.get("autores")),
                "instituição": texto(f.get("instituicao")), "ano": ano_fonte(f.get("ano_publicacao")),
                "referência (ABNT)": texto(f.get("referencia_abnt")),
            } for f in fontes_df.to_dict("records")]))
        if not form_df.empty:
            st.markdown("**Fórmulas aplicadas (tabela formula_calculo)**")
            tabela(pd.DataFrame([{
                "fórmula": texto(f.get("nome")), "expressão": texto(f.get("expressao")),
                "fonte": f"{texto(f.get('fonte_codigo'))}, p. {texto(f.get('pagina_pdf')) or '—'}",
                "observações": texto(f.get("observacoes")),
            } for f in form_df.to_dict("records")]))
        if not div_df.empty:
            st.markdown("**Divergências entre fontes registradas para as referências usadas**")
            tabela(div_df.drop_duplicates("divergencia_codigo")[["divergencia_codigo", "descricao", "tratamento"]])
        if refs_df.empty and form_df.empty:
            st.caption("Nenhuma referência do banco foi usada: o resultado depende apenas das premissas informadas.")
    return {"referencias": refs_df, "fontes": fontes_df, "formulas": form_df, "divergencias": div_df}


def precos_historicos(dfp: pd.DataFrame):
    """Mostra as cotações registradas no banco, deixando claro que são históricas (não atuais)."""
    with st.expander("🗓️ Cotações da arroba registradas no banco (históricas — não são preços atuais)", expanded=False):
        if dfp is None or dfp.empty:
            st.caption("Nenhuma cotação registrada.")
            return
        atuais = dfp[dfp["natureza"].astype(str) == "cotacao_mercado"]
        if atuais.empty:
            st.warning("O banco não contém cotação atual de mercado. Os valores abaixo vêm de publicações técnicas e "
                       "valem apenas como registro histórico (BRL nominal da data indicada). Informe o valor da arroba "
                       "praticado hoje na sua região.")
        tabela(pd.DataFrame([{
            "data de referência": texto(r.get("data_referencia")), "praça": f"{texto(r.get('municipio_praca'))} {texto(r.get('estado'))}".strip(),
            "categoria": texto(r.get("categoria_animal")), "preço (R$/@)": num(r.get("preco")),
            "natureza": "histórico de publicação" if r.get("natureza") == "historico_publicacao" else texto(r.get("natureza")),
            "tipo de cotação": texto(r.get("tipo_cotacao")), "fonte": f"{texto(r.get('fonte_codigo'))} ({ano_fonte(r.get('fonte_ano'))}), p. {texto(r.get('pagina_pdf'))}",
            "uso permitido": texto(r.get("uso_permitido")),
        } for r in dfp.to_dict("records")]))


def selecionar_raca(df_racas: pd.DataFrame, chave: str, rotulo: str = "Raça ou composição genética") -> tuple[str, dict]:
    regs = {r["raca_codigo"]: r for r in df_racas.to_dict("records")}
    codigos = list(regs)
    cod = st.selectbox(rotulo, codigos, key=chave, format_func=lambda c: f"{regs[c]['nome']} — {regs[c]['grupo_genetico']}",
                       help="Lista do banco (raca_genotipo). Nelore PO, Nelore comercial, nelorado e cruzados são genótipos "
                            "distintos e nunca são misturados nas comparações.")
    return cod, regs[cod]


def referencias_compativeis_rendimento(df: pd.DataFrame, raca: str, sexo: str) -> tuple[list[dict], list[dict]]:
    """(compatíveis, gerais). Compatíveis: mesma raça e sexo compatível. Gerais: fonte sem raça definida
    (Não especificada / Não se aplica). Referências de OUTRA raça específica não são oferecidas."""
    from modules.pecuaria.calculos import SEXO_COMPATIVEL
    sx_ok = set(SEXO_COMPATIVEL.get(sexo, {})) | {"nao_aplicavel", "nao_especificado"}
    comp, gerais = [], []
    for r in df.to_dict("records"):
        if r.get("sexo") not in sx_ok:
            continue
        if r.get("raca_codigo") == raca:
            comp.append(r)
        elif r.get("raca_codigo") in ("NAO_ESPECIFICADA", "NAO_APLICAVEL"):
            gerais.append(r)
    return comp, gerais


def escolher_rendimento(df_ref: pd.DataFrame, raca: str, sexo: str, chave: str, rotulo: str = "Rendimento de carcaça"
                        ) -> tuple[Optional[float], Optional[dict], str]:
    """Rendimento informado pelo usuário ou referência identificada do banco. Retorna (valor, registro, origem)."""
    comp, gerais = referencias_compativeis_rendimento(df_ref, raca, sexo)
    opcoes_ref = comp + gerais
    modos = ["ref", "usuario"] if opcoes_ref else ["usuario"]
    modo = st.radio(f"{rotulo}: origem do valor", modos, key=f"{chave}_modo_{raca}_{sexo}", horizontal=True,
                    format_func={"ref": "Referência técnica do banco", "usuario": "Informar valor próprio"}.get)
    if modo == "usuario":
        if not opcoes_ref:
            st.caption("Não há referência de rendimento para esta raça/sexo no banco (nem referência geral compatível).")
        v = st.number_input(f"{rotulo} (% do peso vivo)", min_value=30.0, max_value=75.0, value=None, step=0.5,
                            key=f"{chave}_valor", placeholder="ex.: informe o rendimento do frigorífico",
                            help="Peso de carcaça ÷ peso vivo × 100. Use o valor praticado nos seus abates, se houver.")
        return v, None, "informado pelo usuário"
    ids = [r["id_registro"] for r in opcoes_ref]
    regs = {r["id_registro"]: r for r in opcoes_ref}
    marca = {r["id_registro"]: ("" if r in comp else "[geral] ") for r in opcoes_ref}
    rid = st.selectbox(f"{rotulo}: referência", ids, key=f"{chave}_ref_{raca}_{sexo}",
                       format_func=lambda i: marca[i] + rotulo_referencia(regs[i], valor_rendimento_txt(regs[i])),
                       help="Somente referências da mesma raça/genótipo e sexo compatível, ou referências gerais "
                            "(fonte sem raça definida, marcadas como [geral]).")
    r = regs[rid]
    detalhes_referencia(r)
    if r in gerais:
        st.caption("⚠️ Referência geral: a fonte não define a raça dos animais. Confira as condições antes de usar.")
    v = r.get("valor_numerico")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        a, b = float(r["valor_min"]), float(r["valor_max"])
        v = st.number_input(f"Valor dentro da faixa da referência ({num(a, 1)}–{num(b, 1)}%)", min_value=a, max_value=b,
                            value=a, step=0.1, key=f"{chave}_faixa_{rid}",
                            help="A referência é uma faixa; escolha o valor a usar (o padrão é o limite inferior).")
        return float(v), r, f"referência {rid} (faixa {num(a, 1)}–{num(b, 1)}%; valor escolhido pelo usuário)"
    return float(v), r, f"referência {rid}"


def perguntas_tecnicas(banco: str, raca: str, temas: Sequence[str], titulo: str):
    termo = TERMO_BUSCA_RACA.get(raca, "")
    if not termo:
        return pd.DataFrame()
    try:
        df = carregar_perguntas(banco, termo, tuple(temas))
    except BancoIndisponivel:
        return pd.DataFrame()
    if df.empty:
        return df
    with st.expander(titulo, expanded=False):
        for r in df.to_dict("records"):
            st.markdown(f"**{texto(r.get('pergunta'))}**")
            st.write(texto(r.get("resposta")))
            st.caption(f"{texto(r.get('fonte_titulo'))} ({ano_fonte(r.get('fonte_ano'))}) — pergunta {texto(r.get('numero_pergunta'))}, "
                       f"{texto(r.get('capitulo_titulo'))}, p. {texto(r.get('pagina_pdf_inicio')) or '—'} do PDF"
                       + (" · contém ilustração não transcrita" if r.get("possui_conteudo_nao_transcrito") else ""))
    return df


# ------------------------------------------------------------------ gráficos
def grafico_barras(categorias: Sequence[str], series: dict, titulo: str, eixo_y: str, altura: int = 360):
    if go is None:
        tabela(pd.DataFrame({"categoria": categorias, **series}))
        return
    cores = ["#69f0ae", "#ef6c00", "#81c784", "#4fc3f7", "#c62828"]
    fig = go.Figure()
    for i, (nome, valores) in enumerate(series.items()):
        fig.add_trace(go.Bar(name=nome, x=list(categorias), y=list(valores), marker_color=cores[i % len(cores)]))
    fig.update_layout(title=dict(text=titulo, font=dict(size=13)), barmode="group", yaxis_title=eixo_y,
                      legend=dict(orientation="h", y=-0.2))
    grafico(layout_escuro(fig, altura))
