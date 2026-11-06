"""
Página do módulo EduAgro AI (5º módulo do menu principal do SafraTech).

Áreas: 1. Tutor Agro Inteligente · 2. Cursos e Trilhas · 3. Biblioteca · 4. Exercícios e Avaliações · 5. Meu Aprendizado.
A navegação interna usa a chave `edu_secao` (0 a 2).
"""
from __future__ import annotations

import streamlit as st

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import deepseek_client as ds
from modules.eduagro_ai import prompts
from modules.eduagro_ai import web_search as ws
from modules.eduagro_ai.estilo import CSS_EDUAGRO
from modules.eduagro_ai.paginas import avaliacoes_ui, progresso_ui, tutor_ui

SECOES = ["🤖 Tutor Agro", "📝 Exercícios e Avaliações", "📈 Meu Aprendizado"]
RENDER = [tutor_ui.render, avaliacoes_ui.render, progresso_ui.render]


def _testar_ia():
    st.session_state["edu_status_ia"] = ds.obter_cliente().testar_conexao(com_chat=True).__dict__


def _perfil() -> dict:
    """Perfil de estudante (o SafraTech não possui login; o perfil apenas separa o progresso de cada pessoa)."""
    perfis = {u["nome"] for u in arm.listar_usuarios()} | {arm.PERFIL_PADRAO}
    atual = st.session_state.get("edu_perfil_atual", arm.PERFIL_PADRAO)
    novo = st.session_state.pop("edu_perfil_criado", None)
    if novo:   # perfil recém-criado passa a ser o selecionado
        atual = novo
        st.session_state.pop("edu_perfil", None)
    opcoes = sorted(perfis | {atual})
    nome = st.sidebar.selectbox("Perfil de estudante", opcoes, index=opcoes.index(atual), key="edu_perfil",
                                help="O SafraTech não exige login: o perfil só separa o progresso de quem usa este computador.")
    st.session_state["edu_perfil_atual"] = nome
    with st.sidebar.expander("➕ Novo perfil", expanded=False):
        novo_nome = st.text_input("Nome do estudante", key="edu_novo_perfil")
        if st.button("Criar perfil", key="edu_criar_perfil") and novo_nome.strip():
            u = arm.obter_ou_criar_usuario(novo_nome)
            st.session_state["edu_perfil_criado"] = u["nome"]
            st.rerun()
    return arm.obter_ou_criar_usuario(nome)


def _testar_busca():
    try:
        paginas = ws.obter_cliente().buscar("Embrapa soja manejo")
        st.session_state["edu_status_busca"] = {"ok": True, "msg": f"Busca na internet funcionando ({len(paginas)} páginas)."}
    except ws.ErroBusca as e:
        st.session_state["edu_status_busca"] = {"ok": False, "msg": e.mensagem_usuario, "detalhe": e.detalhe}


def _status_busca() -> None:
    cfg = ws.carregar_config()
    with st.sidebar.expander("🔗 Busca na internet (Tavily)", expanded=False):
        st.markdown("🟢 Configurada" if cfg.disponivel else "⚪ Desativada")
        st.caption("O tutor procura primeiro nos bancos do SafraTech e na Biblioteca; a internet só é consultada quando "
                   "nada é encontrado neles (ou quando você pede).")
        st.caption(cfg.descricao())
        if cfg.disponivel:
            mes = arm.agora()[:7]
            n = (arm.um("SELECT count(*) AS n FROM evento WHERE tipo = 'busca_internet' AND substr(criado_em, 1, 7) = ?",
                        (mes,)) or {"n": 0})["n"]
            st.caption(f"Buscas feitas pelo EduAgro neste mês: {n} (cada busca usa 1 crédito do plano Tavily).")
            st.button("Testar busca", key="edu_testar_busca", on_click=_testar_busca)
        s = st.session_state.get("edu_status_busca")
        if s:
            (st.success if s["ok"] else st.error)(s["msg"])


def _status_ia() -> None:
    cfg = ds.carregar_config()
    with st.sidebar.expander("🤖 Inteligência artificial (DeepSeek)", expanded=not cfg.configurada):
        if not cfg.configurada:
            st.markdown("🔴 Não configurada")
            st.caption(ds.IANaoConfigurada.mensagem_padrao)
        else:
            st.markdown(f"🟢 Chave carregada · modelo `{cfg.modelo}`")
        st.caption(cfg.descricao())
        st.button("Testar conexão", key="edu_testar_ia", on_click=_testar_ia)
        s = st.session_state.get("edu_status_ia")
        if s:
            (st.success if s["disponivel"] else st.error)(s["mensagem"])
            if s.get("saldo"):
                st.caption(f"Saldo da conta: {s['saldo']}")
            det = s.get("detalhes") or {}
            if det.get("duracao_s"):
                st.caption(f"Resposta de teste em {det['duracao_s']} s ({det.get('modelo_resposta', '')}).")
            elif det.get("detalhe"):
                st.caption(det["detalhe"])


def render() -> None:
    try:  # chaves vindas de st.secrets (opcional); variáveis de ambiente/.env têm prioridade
        ds.configurar_segredos(dict(st.secrets))
        ws.configurar_segredos(dict(st.secrets))
    except Exception:
        pass
    st.markdown(CSS_EDUAGRO, unsafe_allow_html=True)
    from utils import mascote
    try:
        c_foto, c_titulo = st.columns([1, 5], vertical_alignment="center")
    except TypeError:  # versões antigas do Streamlit
        c_foto, c_titulo = st.columns([1, 5])
    with c_foto:
        mascote.mostrar(tamanho=110)
    c_titulo.header("EduAgro AI — o tutor inteligente")
    st.markdown('<div class="edu-hero"><span class="edu-selo">Plataforma de ensino · SafraTech</span>'
                '<h2>Aprenda agronegócio com o conhecimento técnico do SafraTech</h2>'
                '<p>Tutor inteligente, exercícios com correção e acompanhamento '
                'do seu progresso — sempre diferenciando o que vem dos bancos do SafraTech, o que é explicação da IA e o que '
                'é exemplo hipotético.</p></div>', unsafe_allow_html=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**🎓 EduAgro AI**")
    usuario = _perfil()
    nivel = st.sidebar.radio("Seu nível de conhecimento", list(prompts.NIVEIS), key="edu_nivel",
                             index=list(prompts.NIVEIS).index(usuario.get("nivel", "Iniciante"))
                             if usuario.get("nivel") in prompts.NIVEIS else 0)
    if nivel != usuario.get("nivel"):
        arm.definir_nivel(usuario["id"], nivel)
        usuario["nivel"] = nivel
    _status_ia()
    _status_busca()

    secao = st.radio("Área do EduAgro", list(range(len(SECOES))), format_func=lambda i: SECOES[i], horizontal=True,
                     key="edu_secao", label_visibility="collapsed")
    st.divider()
    RENDER[secao](usuario, nivel)
