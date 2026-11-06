import sys
from pathlib import Path

import streamlit as st

# Raiz do projeto no sys.path (permite `streamlit run main.py` de qualquer pasta)
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

try:  # .env opcional (as senhas ficam fora do código)
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:
    pass

from database import connections
from modules import diagnostico_nutricional, diagnostico_solo, simulacao_plantio
from modules.pecuaria import compra, desempenho, rentabilidade
from modules._comum import CSS_EXTRA
from modules.eduagro_ai.estilo import CSS_MENU_DESTAQUE
from utils.textos import tr

st.set_page_config(page_title="SafraTech IA", page_icon="🌱", layout="wide")

# -------------------------
# ESTILO VISUAL
# -------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap');

/* Base */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Fundo geral */
.stApp {
    background: linear-gradient(135deg, #0a1a0f 0%, #0d2218 50%, #0a1a0f 100%);
    color: #e8f5e9;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #071510 0%, #0d2218 100%) !important;
    border-right: 1px solid #1a4a2a;
}
[data-testid="stSidebar"] * {
    color: #c8e6c9 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stNumberInput label {
    color: #81c784 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 500;
}

/* Título principal */
h1 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important;
    font-size: 2.4rem !important;
    background: linear-gradient(90deg, #69f0ae, #b9f6ca);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
    padding-bottom: 0.5rem;
}

/* Headers */
h2, h3 {
    font-family: 'Syne', sans-serif !important;
    color: #a5d6a7 !important;
    font-weight: 700 !important;
}

/* Cards de métrica */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #0d2a1a, #133d26);
    border: 1px solid #1e5c35;
    border-radius: 16px;
    padding: 1.2rem 1.4rem !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(105,240,174,0.08);
    transition: transform 0.2s, box-shadow 0.2s;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(105,240,174,0.12);
}
[data-testid="stMetricLabel"] {
    color: #81c784 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Syne', sans-serif !important;
    color: #69f0ae !important;
    font-size: 1.9rem !important;
    font-weight: 700 !important;
}

/* Botões */
.stButton > button {
    background: linear-gradient(135deg, #1b5e20, #2e7d32) !important;
    color: #b9f6ca !important;
    border: 1px solid #388e3c !important;
    border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em;
    padding: 0.6rem 2rem !important;
    transition: all 0.2s !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2e7d32, #388e3c) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 20px rgba(56,142,60,0.4) !important;
}

/* Selectbox e inputs */
.stSelectbox > div > div,
.stNumberInput > div > div > input {
    background: #0d2218 !important;
    border: 1px solid #1e5c35 !important;
    border-radius: 10px !important;
    color: #c8e6c9 !important;
}

/* Alertas */
.stSuccess {
    background: rgba(27, 94, 32, 0.3) !important;
    border: 1px solid #2e7d32 !important;
    border-radius: 10px !important;
    color: #c8e6c9 !important;
}
.stError {
    background: rgba(183, 28, 28, 0.25) !important;
    border: 1px solid #c62828 !important;
    border-radius: 10px !important;
}
.stWarning {
    background: rgba(230, 81, 0, 0.2) !important;
    border: 1px solid #bf360c !important;
    border-radius: 10px !important;
}

/* Divider */
hr {
    border-color: #1a4a2a !important;
    margin: 1.5rem 0 !important;
}

/* Caption / footer */
.stCaption {
    color: #4caf50 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.05em;
}

/* Radio buttons na sidebar */
[data-testid="stSidebar"] .stRadio > div {
    gap: 0.3rem;
}
[data-testid="stSidebar"] .stRadio label {
    background: rgba(255,255,255,0.03);
    border: 1px solid #1a4a2a;
    border-radius: 8px;
    padding: 0.4rem 0.8rem !important;
    transition: all 0.15s;
    text-transform: none !important;
    letter-spacing: normal !important;
    font-size: 0.85rem !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    border-color: #388e3c;
    background: rgba(56,142,60,0.1);
}

/* Header badge */
.header-badge {
    display: inline-block;
    background: linear-gradient(135deg, #1b5e20, #2e7d32);
    color: #b9f6ca;
    font-family: 'Syne', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    border: 1px solid #388e3c;
    margin-bottom: 0.5rem;
}

/* Botões de formulário e download no mesmo estilo dos botões */
.stFormSubmitButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg, #1b5e20, #2e7d32) !important;
    color: #b9f6ca !important;
    border: 1px solid #388e3c !important;
    border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
}
[data-testid="stExpander"] {
    border: 1px solid #1e5c35 !important;
    border-radius: 12px !important;
    background: rgba(13,42,26,0.35);
}
</style>
""", unsafe_allow_html=True)
st.markdown(CSS_EXTRA, unsafe_allow_html=True)
st.markdown(CSS_MENU_DESTAQUE, unsafe_allow_html=True)

# -------------------------
# CONEXÕES COM OS BANCOS (URLs em variáveis de ambiente ou st.secrets — nunca no código)
# -------------------------
try:
    connections.configurar_segredos(dict(st.secrets))
except Exception:
    pass


@st.cache_data(ttl=60, show_spinner=False)
def status_bancos():
    return [connections.verificar(chave) for chave in connections.BANCOS]


# -------------------------
# NAVEGAÇÃO
# Menu principal (área Agricultura): Solo, Nutricional, Plantio, o acesso à Pecuária e o EduAgro AI.
# Área Pecuária: Compra, Desempenho, Rentabilidade e o retorno à Agricultura.
# -------------------------
MENU_AGRICULTURA = ["🧪 Diagnóstico do Solo", "🍃 Diagnóstico Nutricional", "🗓️ Simulação de Plantio", "🐂 Pecuária",
                    "🎓 EduAgro AI"]
MENU_PECUARIA = ["💵 Análise de Viabilidade de Compra", "📈 Diagnóstico de Desempenho do Rebanho",
                 "📊 Simulador de Rentabilidade", "🌱 Agricultura"]
IDX_IR_PECUARIA = MENU_AGRICULTURA.index("🐂 Pecuária")
IDX_EDUAGRO = MENU_AGRICULTURA.index("🎓 EduAgro AI")
IDX_IR_AGRICULTURA = MENU_PECUARIA.index("🌱 Agricultura")


def _ao_mudar_agricultura():
    escolha = st.session_state["nav_agricultura"]
    if escolha == IDX_IR_PECUARIA:
        st.session_state["area"] = "pecuaria"
        st.session_state["nav_agricultura"] = st.session_state.get("_ultima_agricultura", 0)
        st.session_state["nav_pecuaria"] = st.session_state.get("_ultima_pecuaria", 0)
    else:
        st.session_state["_ultima_agricultura"] = escolha


def _ao_mudar_pecuaria():
    escolha = st.session_state["nav_pecuaria"]
    if escolha == IDX_IR_AGRICULTURA:
        st.session_state["area"] = "agricultura"
        st.session_state["nav_pecuaria"] = st.session_state.get("_ultima_pecuaria", 0)
        st.session_state["nav_agricultura"] = st.session_state.get("_ultima_agricultura", 0)
    else:
        st.session_state["_ultima_pecuaria"] = escolha


# -------------------------
# INTERFACE
# -------------------------
try:
    st.sidebar.image("safratech_ia.png", width="stretch")
except TypeError:
    try:
        st.sidebar.image("safratech_ia.png", use_container_width=True)
    except Exception:
        pass
except Exception:
    pass

st.title("🌱 SafraTech — Sistema Simples de Plantio")
area = st.session_state.setdefault("area", "agricultura")

if area == "pecuaria":
    st.sidebar.header("🐂 Pecuária de Corte")
    pagina = st.sidebar.radio("Navegação:", list(range(len(MENU_PECUARIA))), format_func=lambda i: MENU_PECUARIA[i],
                              key="nav_pecuaria", on_change=_ao_mudar_pecuaria)
else:
    st.sidebar.header("🌱 Agricultura")
    pagina = st.sidebar.radio("Navegação:", list(range(len(MENU_AGRICULTURA))), format_func=lambda i: MENU_AGRICULTURA[i],
                              key="nav_agricultura", on_change=_ao_mudar_agricultura)

# Situação de cada banco (verificada individualmente)
with st.sidebar.expander(f"🗄️ {tr('db_status')}", expanded=False):
    for titulo_area, chave_area in (("Agricultura", "agricultura"), ("Pecuária", "pecuaria")):
        st.markdown(f"**{titulo_area}**")
        for s in status_bancos():
            if connections.BANCOS[s.chave].get("area") != chave_area:
                continue
            icone = "🟢" if s.disponivel else "🔴"
            st.markdown(f"{icone} {connections.BANCOS[s.chave]['nome']} — {tr('db_ok') if s.disponivel else tr('db_fail')}")
            if not s.disponivel:
                st.caption(s.mensagem)

if area == "pecuaria":
    # ---------- PECUÁRIA DE CORTE (pecuaria_compra / desempenho / rentabilidade) ----------
    if pagina == 0:
        compra.render()          # pecuaria_compra_database
    elif pagina == 1:
        desempenho.render()      # pecuaria_desempenho_database
    elif pagina == 2:
        rentabilidade.render()   # pecuaria_rentabilidade_database
    else:  # pragma: no cover - o retorno à Agricultura é tratado no callback da navegação
        st.info("Selecione um módulo de Pecuária ou volte para Agricultura.")
else:
    # ---------- AGRICULTURA ----------
    if pagina == 0:
        diagnostico_solo.render()          # solo_database
    elif pagina == 1:
        diagnostico_nutricional.render()   # nutricao_database
    elif pagina == 2:
        simulacao_plantio.render()         # plantio_database / ZARC
    elif pagina == IDX_EDUAGRO:
        # EduAgro AI: importado só quando aberto, para que uma falha nele nunca afete os demais módulos
        try:
            from modules.eduagro_ai import interface as eduagro
        except Exception as erro:  # pragma: no cover
            st.error(f"Não foi possível carregar o EduAgro AI: {type(erro).__name__}: {erro}")
        else:
            eduagro.render()
    else:  # pragma: no cover - a entrada na Pecuária é tratada no callback da navegação
        st.info("Abrindo a área de Pecuária…")

st.caption("A SafraTech IA não é humana. Pode cometer erros.")
