"""Interface do Tutor Agro Inteligente (chat)."""
from __future__ import annotations

from collections import Counter

import streamlit as st

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import tutor
from modules.eduagro_ai.deepseek_client import ErroIA, IANaoConfigurada, obter_cliente
from modules.eduagro_ai.paginas.componentes import aviso_erro_ia, esc, legenda_origens, md, mostrar_referencias

AVATAR_USUARIO = "🧑‍🌾"
AVATAR_TUTOR = "🎓"
TEXTO_MODO = {"mais_simples": "🙂 Explique de forma mais simples.", "aprofundar": "🔬 Aprofunde este assunto.",
              "internet": "🔗 Procure também na internet sobre este assunto."}


# ------------------------------------------------------------------ callbacks
def _nova_conversa():
    st.session_state["edu_conversa_id"] = None
    st.session_state.pop("edu_pendente", None)


def _abrir_conversa(cid: int):
    st.session_state["edu_conversa_id"] = cid
    st.session_state.pop("edu_pendente", None)


def _excluir_conversa(cid: int, uid: int):
    tutor.excluir_conversa(cid, uid)
    st.session_state["edu_conversa_id"] = None


def _pendente(texto: str, modo: str = "pergunta"):
    st.session_state["edu_pendente"] = {"texto": texto, "modo": modo}


def _ir_para_exercicios(tema: str):
    st.session_state["edu_tema_exercicio"] = tema
    st.session_state["edu_secao"] = 1


# ------------------------------------------------------------------ interface
def _categoria(refs: list[dict]) -> str | None:
    areas = Counter(r.get("area") for r in refs if r.get("area") in ("agricultura", "pecuaria"))
    if not areas:
        return None
    return {"agricultura": "Agricultura", "pecuaria": "Pecuária"}[areas.most_common(1)[0][0]]


def _mostrar_mensagem(m: dict) -> None:
    if m["papel"] == "user":
        with st.chat_message("user", avatar=AVATAR_USUARIO):
            md(m["conteudo"])
        return
    meta = m.get("meta") or {}
    with st.chat_message("assistant", avatar=AVATAR_TUTOR):
        md(m["conteudo"])
        cit = meta.get("citacoes") or {}
        if cit.get("invalidas"):
            st.warning("⚠️ A resposta citou rótulos que não estavam nas referências entregues à IA: "
                       + ", ".join(cit["invalidas"]) + ". Desconsidere essas citações.")
        for aviso in meta.get("avisos") or []:
            st.caption("⚠️ " + aviso)
        if meta.get("truncada"):
            st.caption("A resposta atingiu o limite de tamanho; peça “continue” para o restante.")
        mostrar_referencias(m.get("referencias") or [])
        st.caption(f"Nível: {meta.get('nivel', '—')} · modelo: {meta.get('modelo', '—')}"
                   + (f" · {meta.get('tokens_saida')} tokens" if meta.get("tokens_saida") else ""))


def render(usuario: dict, nivel: str) -> None:
    uid = usuario["id"]
    if st.session_state.get("edu_conversa_usuario") != uid:
        st.session_state["edu_conversa_id"] = None
        st.session_state["edu_conversa_usuario"] = uid
    atual = st.session_state.get("edu_conversa_id")

    col_hist, col_chat = st.columns([1, 3], gap="large")
    with col_hist:
        st.button("➕ Nova conversa", key="edu_nova_conversa", on_click=_nova_conversa)
        st.markdown("**🕘 Histórico de conversas**")
        conversas = tutor.listar_conversas(uid, 20)
        if not conversas:
            st.caption("Suas conversas aparecerão aqui.")
        for c in conversas:
            marcador = "▶ " if c["id"] == atual else ""
            st.button(f"{marcador}{c['titulo'][:42]}", key=f"edu_conv_{c['id']}", on_click=_abrir_conversa, args=(c["id"],),
                      help=f"{c['mensagens']} mensagens · {c['atualizado_em'].replace('T', ' ')}")
        if atual:
            st.button("🗑️ Excluir conversa atual", key="edu_excluir_conversa", on_click=_excluir_conversa, args=(atual, uid))
        st.markdown("**⚙️ Onde o tutor consulta**")
        fontes = list(tutor.FONTES_TUTOR)
        fonte = st.radio("Fonte das respostas", fontes, format_func=tutor.FONTES_TUTOR.get, key="edu_tutor_fonte",
                         index=fontes.index(tutor.fonte_padrao()))
        area, usar_bib = "todas", False
        if fonte == "bancos":
            area = st.selectbox("Bancos do SafraTech", list(tutor.AREAS_TUTOR), format_func=tutor.AREAS_TUTOR.get,
                                key="edu_tutor_area")
        else:
            from modules.eduagro_ai import web_search as ws
            if not ws.carregar_config().disponivel:
                st.warning("A busca na internet não está configurada (TAVILY_API_KEY no .env).")

    with col_chat:
        legenda_origens()
        msgs = tutor.mensagens(atual) if atual else []
        area_msgs = st.container()
        with area_msgs:
            if not msgs and not st.session_state.get("edu_pendente"):
                st.markdown(
                    '<div class="edu-card" style="min-height:0"><h4>👋 Olá! Eu sou o Tutor Agro.</h4>'
                    f'<div class="desc">Pergunte sobre solo, nutrição de plantas, plantio, pecuária de corte ou gestão rural. '
                    f'Vou consultar os bancos técnicos do SafraTech, explicar no nível <b>{esc(nivel)}</b>, mostrar exemplos e '
                    f'cálculos passo a passo e fazer perguntas para você verificar o que aprendeu.</div></div>',
                    unsafe_allow_html=True)
                st.markdown("**💡 Sugestões de perguntas**")
                cols = st.columns(2)
                for i, sug in enumerate(tutor.SUGESTOES):
                    cols[i % 2].button(sug, key=f"edu_sug_{i}", on_click=_pendente, args=(sug,))
            for m in msgs:
                _mostrar_mensagem(m)
            ultima_consulta = next((m.get("meta", {}).get("consulta") for m in reversed(msgs)
                                    if m["papel"] == "user" and m.get("meta", {}).get("consulta")), "")
            if msgs and msgs[-1]["papel"] == "assistant":
                from modules.eduagro_ai import web_search as ws
                web_ok = ws.carregar_config().disponivel
                usou_web = any(r.get("origem") == "internet" for r in (msgs[-1].get("referencias") or []))
                b1, b2, b3 = st.columns(3)
                b1.button("🙂 Explicar de forma mais simples", key="edu_mais_simples", on_click=_pendente,
                          args=(TEXTO_MODO["mais_simples"], "mais_simples"))
                b2.button("🔬 Explicação mais aprofundada", key="edu_aprofundar", on_click=_pendente,
                          args=(TEXTO_MODO["aprofundar"], "aprofundar"))
                b3.button("📝 Gerar exercícios sobre este assunto", key="edu_exercicios_assunto",
                          on_click=_ir_para_exercicios, args=(ultima_consulta,))
                if web_ok and not usou_web and fonte == "bancos":
                    st.button("🔗 Procurar também na internet", key="edu_buscar_internet", on_click=_pendente,
                              args=(TEXTO_MODO["internet"], "internet"),
                              help="Os bancos do SafraTech já foram consultados primeiro. Use se a resposta não foi suficiente.")

        digitado = st.chat_input("Pergunte ao Tutor Agro… (ex.: Como calcular a saturação por bases?)", key="edu_chat_input")
        pendente = {"texto": digitado, "modo": "pergunta"} if digitado else st.session_state.pop("edu_pendente", None)
        if pendente and str(pendente.get("texto") or "").strip():
            _processar(pendente, uid, nivel, area, usar_bib, msgs, ultima_consulta, area_msgs, fonte)


def _processar(pendente: dict, uid: int, nivel: str, area: str, usar_bib: bool, msgs: list[dict], ultima_consulta: str,
               area_msgs, fonte: str = "bancos") -> None:
    texto, modo = pendente["texto"].strip()[:4000], pendente.get("modo", "pergunta")
    cliente = obter_cliente()
    with area_msgs:
        with st.chat_message("user", avatar=AVATAR_USUARIO):
            md(texto)
        with st.chat_message("assistant", avatar=AVATAR_TUTOR):
            if not cliente.configurado:
                aviso_erro_ia(IANaoConfigurada(), "responder")
                return
            espera = "🔗 Pesquisando na internet…" if fonte == "internet" else "🔎 Consultando os bancos do SafraTech…"
            with st.spinner(espera):
                prep = tutor.preparar(texto, nivel, msgs, area=area, usar_bancos=True, usar_biblioteca=usar_bib, modo=modo,
                                      consulta_anterior=ultima_consulta, fonte=fonte)
            for aviso in prep.avisos:
                st.caption("⚠️ " + aviso)
            if fonte == "internet":
                st.caption(f"🔗 {len(prep.busca.da_internet)} página(s) da internet enviadas ao tutor · ✍️ escrevendo a resposta…")
            else:
                web = f" e {len(prep.busca.da_internet)} página(s) da internet" if prep.busca.da_internet else ""
                st.caption(f"🔎 {len(prep.busca.do_banco)} registro(s) dos bancos{web} enviados ao tutor · ✍️ escrevendo a resposta…")
            try:
                resposta = st.write_stream(tutor.responder_stream(cliente, prep))
            except ErroIA as e:
                aviso_erro_ia(e, "responder agora")
                st.caption("Sua pergunta não foi registrada. Tente novamente quando a IA estiver disponível.")
                return
    resposta = tutor.normalizar_latex(resposta if isinstance(resposta, str) else "".join(map(str, resposta)))
    info = cliente.ultima_resposta
    cit = tutor.verificar_citacoes(resposta, prep.busca)
    cid = st.session_state.get("edu_conversa_id")
    if not cid:
        cid = tutor.criar_conversa(uid, prep.consulta if modo == "pergunta" else texto, nivel)
        st.session_state["edu_conversa_id"] = cid
    tutor.adicionar_mensagem(cid, "user", texto, meta={"modo": modo, "consulta": prep.consulta})
    refs = [r.para_dict() for r in prep.busca.referencias]
    tutor.adicionar_mensagem(cid, "assistant", resposta, referencias=refs, meta={
        "nivel": nivel, "modo": modo, "consulta": prep.consulta, "citacoes": cit, "avisos": prep.avisos,
        "modelo": getattr(info, "modelo", ""), "tokens_saida": getattr(info, "tokens_saida", 0),
        "truncada": bool(getattr(info, "truncada", False)), "bancos_consultados": prep.busca.bancos_consultados,
        "internet": bool(prep.busca.da_internet), "fonte": fonte})
    arm.registrar_evento(uid, "tutor", f"Pergunta ao tutor: {prep.consulta[:140]}", _categoria(refs))
    if prep.busca.internet_consultada and prep.busca.da_internet:
        arm.registrar_evento(uid, "busca_internet", f"Busca na internet: {prep.consulta[:140]}", None)
    st.rerun()
