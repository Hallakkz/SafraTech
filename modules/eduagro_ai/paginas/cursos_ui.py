"""Interface de Cursos e Trilhas de Aprendizagem."""
from __future__ import annotations

import streamlit as st

from modules.eduagro_ai import avaliacoes as av
from modules.eduagro_ai import cursos as cur
from modules.eduagro_ai.deepseek_client import ErroIA, obter_cliente
from modules.eduagro_ai.paginas.componentes import aviso_erro_ia, esc, md, mostrar_referencias, questionario, tag

ICONE_CAT = {"Agricultura": "🌱", "Pecuária": "🐂", "Gestão Rural": "📊"}


def _abrir(cid):
    st.session_state["edu_curso_id"] = cid


def _voltar():
    st.session_state["edu_curso_id"] = None


def render(usuario: dict, nivel: str) -> None:
    cur.garantir_catalogo()
    cid = st.session_state.get("edu_curso_id")
    curso = cur.obter_curso(cid) if cid else None
    if curso:
        _detalhe(curso, usuario, nivel)
    else:
        _catalogo(usuario)


# =====================================================================================================
# Catálogo
# =====================================================================================================
def _catalogo(usuario: dict) -> None:
    st.markdown("Trilhas organizadas por tema. O catálogo traz a **estrutura** de cada curso (escopo, nível e objetivos); "
                "as aulas são cadastradas com conteúdo próprio ou materiais técnicos confiáveis — nenhum conteúdo é "
                "apresentado como oficial sem origem identificada.")
    c1, c2 = st.columns([2, 1])
    cat = c1.radio("Categoria", ["Todas", *cur.CATEGORIAS], horizontal=True, key="edu_cursos_cat")
    niv = c2.selectbox("Nível", ["Todos", *cur.NIVEIS], key="edu_cursos_nivel")
    lista = cur.listar_cursos(None if cat == "Todas" else cat, usuario_id=usuario["id"])
    if niv != "Todos":
        lista = [c for c in lista if c["nivel"] == niv]
    if not lista:
        st.info("Nenhum curso para este filtro.")
    for categoria in cur.CATEGORIAS:
        grupo = [c for c in lista if c["categoria"] == categoria]
        if not grupo:
            continue
        st.subheader(f"{ICONE_CAT[categoria]} {categoria}")
        cols = st.columns(3)
        for i, c in enumerate(grupo):
            with cols[i % 3]:
                estado = ("✅ concluído" if c.get("status") == "concluido" else
                          "📘 em andamento" if c.get("status") == "em_andamento" else "")
                aulas = (f"{c['aulas']} aula(s)" + (f" · {c['concluidas']} concluída(s)" if c.get("concluidas") else "")
                         if c["aulas"] else "sem aulas cadastradas")
                st.markdown(f'<div class="edu-card"><h4>{esc(c["nome"])}</h4>'
                            f'<div class="meta">{esc(c["nivel"])} · {esc(aulas)} {esc(estado)}</div>'
                            f'<div class="desc">{esc(c["descricao"])}</div></div>', unsafe_allow_html=True)
                st.button("Abrir curso", key=f"edu_abrir_{c['id']}", on_click=_abrir, args=(c["id"],))
    with st.expander("➕ Criar um novo curso"):
        with st.form("edu_novo_curso"):
            nome = st.text_input("Nome do curso", key="edu_nc_nome")
            a, b = st.columns(2)
            categoria = a.selectbox("Categoria", list(cur.CATEGORIAS), key="edu_nc_cat")
            nivel = b.selectbox("Nível de dificuldade", list(cur.NIVEIS), key="edu_nc_nivel")
            descricao = st.text_area("Descrição", key="edu_nc_desc")
            objetivos = st.text_area("Objetivos de aprendizagem (um por linha)", key="edu_nc_obj")
            if st.form_submit_button("Criar curso"):
                try:
                    novo = cur.criar_curso(nome, categoria, nivel, descricao, objetivos)
                    st.session_state["edu_curso_id"] = novo
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# =====================================================================================================
# Detalhe do curso
# =====================================================================================================
def _detalhe(curso: dict, usuario: dict, nivel: str) -> None:
    uid = usuario["id"]
    st.button("← Voltar ao catálogo", key="edu_voltar_catalogo", on_click=_voltar)
    st.subheader(f"{ICONE_CAT.get(curso['categoria'], '📘')} {curso['nome']}")
    st.markdown(tag(curso["categoria"], "banco") + tag(f"Nível {curso['nivel']}") +
                tag("Curso do catálogo" if curso["origem"] == "catalogo" else "Curso cadastrado"), unsafe_allow_html=True)
    if curso.get("descricao"):
        st.markdown(curso["descricao"])
    if curso.get("objetivos"):
        st.markdown("**🎯 Objetivos de aprendizagem**")
        st.markdown("\n".join(f"- {o}" for o in curso["objetivos"].splitlines() if o.strip()))
    aulas = cur.listar_aulas(curso["id"])
    feitas = cur.aulas_concluidas(uid, curso["id"])
    if aulas:
        st.progress(len(feitas) / len(aulas), text=f"Progresso: {len(feitas)} de {len(aulas)} aula(s) concluída(s)")
    t_aulas, t_refs, t_final, t_gerir = st.tabs(["📖 Aulas", "📚 Referências do SafraTech", "📝 Avaliação final",
                                                  "⚙️ Gerenciar conteúdo"])
    with t_aulas:
        _aulas(aulas, feitas, uid)
    with t_refs:
        st.caption("Registros reais dos bancos do SafraTech (e da Biblioteca) relacionados ao escopo do curso, com fonte e "
                   "página. São material de consulta — não substituem as aulas.")
        with st.spinner("Consultando os bancos…"):
            busca = cur.referencias_do_curso(curso)
        if busca.bancos_indisponiveis:
            st.warning("Bancos indisponíveis: " + ", ".join(busca.bancos_indisponiveis))
        mostrar_referencias([r.para_dict() for r in busca.referencias], "Referências relacionadas", expandido=True)
    with t_final:
        _avaliacao_final(curso, uid)
    with t_gerir:
        _gerenciar(curso, aulas, nivel)


def _aulas(aulas: list[dict], feitas: set, uid: int) -> None:
    if not aulas:
        st.info("Este curso ainda não tem aulas cadastradas. Use a aba **⚙️ Gerenciar conteúdo** para cadastrar aulas com "
                "conteúdo próprio, materiais técnicos ou criar um rascunho com a IA a partir das referências do SafraTech.")
        return
    for a in aulas:
        concluida = a["id"] in feitas
        with st.expander(f"{'✅' if concluida else '📖'} Aula {a['ordem']} — {a['titulo']}", expanded=False):
            st.markdown(tag(cur.ORIGENS_AULA.get(a["origem"], a["origem"]), "ia" if a["origem"] == "rascunho_ia" else "banco"),
                        unsafe_allow_html=True)
            if not a["revisada"]:
                st.warning("Rascunho gerado por IA ainda **não revisado** por um responsável técnico. Use com cautela.")
            md(a["conteudo"])
            if a.get("resumo"):
                st.markdown("**📝 Resumo**")
                md(a["resumo"])
            if a.get("exemplos"):
                st.markdown("**🧮 Exemplos práticos**")
                md(a["exemplos"])
            if a.get("referencias"):
                st.markdown("**📚 Referências da aula**")
                st.markdown(a["referencias"].replace("\n", "  \n"))
            if not concluida:
                st.button("Marcar aula como concluída", key=f"edu_concluir_{a['id']}", on_click=cur.concluir_aula,
                          args=(uid, a["id"]))


def _avaliacao_final(curso: dict, uid: int) -> None:
    questoes = av.listar_questoes(curso["id"], final=True)
    if not questoes:
        st.info("A avaliação final deste curso ainda não foi cadastrada (veja **⚙️ Gerenciar conteúdo**).")
        return
    st.caption(f"{len(questoes)} questão(ões). Critério de conclusão do curso: todas as aulas concluídas e nota mínima de "
               f"{cur.NOTA_APROVACAO:g}% na avaliação final.")
    questionario(questoes, f"edu_final_{curso['id']}", uid, f"Avaliação final — {curso['nome']}", curso_id=curso["id"],
                 categoria=curso["categoria"], final=True)


def _gerenciar(curso: dict, aulas: list[dict], nivel: str) -> None:
    st.markdown("##### ✍️ Cadastrar aula")
    with st.form(f"edu_aula_form_{curso['id']}"):
        titulo = st.text_input("Título da aula", key="edu_aula_titulo")
        origem = st.selectbox("Origem do conteúdo", ["proprio", "material_cadastrado"], format_func=cur.ORIGENS_AULA.get,
                              key="edu_aula_origem")
        conteudo = st.text_area("Conteúdo (Markdown; fórmulas em $...$)", height=220, key="edu_aula_conteudo")
        resumo = st.text_area("Resumo", key="edu_aula_resumo")
        exemplos = st.text_area("Exemplos práticos", key="edu_aula_exemplos")
        referencias = st.text_area("Referências (publicação, instituição, ano, página)", key="edu_aula_refs")
        if st.form_submit_button("Salvar aula"):
            try:
                cur.salvar_aula(curso["id"], titulo, conteudo, resumo, exemplos, referencias, origem)
                st.success("Aula salva.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    st.markdown("##### 🤖 Rascunho de aula com IA")
    st.caption("A IA organiza didaticamente SOMENTE as referências recuperadas dos bancos do SafraTech e da Biblioteca. "
               "O rascunho fica marcado como “não revisado” até ser aprovado.")
    tema = st.text_input("Tema da aula", key=f"edu_rasc_tema_{curso['id']}", placeholder="ex.: Interpretação do fósforo no solo")
    chave_r = f"edu_rascunho_{curso['id']}"
    if st.button("Gerar rascunho", key=f"edu_rasc_btn_{curso['id']}") and tema.strip():
        cat = cur.catalogo_por_codigo(curso["codigo"])
        try:
            with st.spinner("Consultando referências e redigindo o rascunho…"):
                st.session_state[chave_r] = cur.gerar_rascunho_aula(obter_cliente(), curso, tema, nivel,
                                                                    cat.area if cat else "todas")
        except ValueError as e:
            st.warning(str(e))
        except ErroIA as e:
            aviso_erro_ia(e, "gerar o rascunho")
    rasc = st.session_state.get(chave_r)
    if rasc:
        with st.container(border=True):
            st.markdown(f"**Pré-visualização — {rasc['titulo']}** " + tag("Rascunho gerado por IA", "ia"), unsafe_allow_html=True)
            md(rasc["conteudo"])
            st.markdown("**Resumo**")
            md(rasc["resumo"])
            st.markdown("**Exemplos (hipotéticos)**")
            md(rasc["exemplos"])
            st.caption("Referências entregues à IA:\n" + rasc["referencias"])
            a, b = st.columns(2)
            if a.button("Salvar como rascunho no curso", key=f"edu_rasc_salvar_{curso['id']}"):
                cur.salvar_aula(curso["id"], rasc["titulo"], rasc["conteudo"], rasc["resumo"], rasc["exemplos"],
                                rasc["referencias"], origem="rascunho_ia")
                st.session_state.pop(chave_r, None)
                st.rerun()
            if b.button("Descartar", key=f"edu_rasc_desc_{curso['id']}"):
                st.session_state.pop(chave_r, None)
                st.rerun()

    pend = [a for a in aulas if not a["revisada"]]
    if pend or aulas:
        st.markdown("##### 📋 Aulas cadastradas")
        for a in aulas:
            c1, c2, c3 = st.columns([4, 1.4, 1])
            c1.markdown(f"**{a['ordem']}. {a['titulo']}** — {cur.ORIGENS_AULA.get(a['origem'])}"
                        + ("" if a["revisada"] else " · ⚠️ não revisado"))
            if not a["revisada"]:
                c2.button("Marcar como revisada", key=f"edu_rev_{a['id']}", on_click=cur.marcar_revisada, args=(a["id"],))
            c3.button("Excluir", key=f"edu_del_aula_{a['id']}", on_click=cur.excluir_aula, args=(a["id"],))

    st.markdown("##### 📝 Avaliação final com IA")
    st.caption("Questões geradas a partir das aulas revisadas do curso e das referências do SafraTech. São exercícios de estudo, "
               "não questões oficiais de instituições.")
    a, b = st.columns([1, 2])
    qtd = a.number_input("Quantidade", min_value=3, max_value=10, value=5, step=1, key=f"edu_final_qtd_{curso['id']}")
    if b.button("Gerar questões da avaliação final", key=f"edu_final_gerar_{curso['id']}"):
        cat = cur.catalogo_por_codigo(curso["codigo"])
        try:
            with st.spinner("Gerando questões…"):
                g = av.gerar_questoes_ia(obter_cliente(), f"{curso['nome']}: {cat.consulta if cat else curso['descricao']}",
                                         curso["nivel"], int(qtd), ["multipla_escolha", "verdadeiro_falso", "pratica"],
                                         area=cat.area if cat else "todas", categoria=curso["categoria"], curso_id=curso["id"])
            for q in g.questoes:
                av.salvar_questao(q, curso_id=curso["id"], avaliacao_final=True)
            st.success(f"{len(g.questoes)} questão(ões) adicionada(s) à avaliação final"
                       + (f"; {g.descartadas} descartada(s) por não citarem uma referência válida." if g.descartadas else "."))
        except ValueError as e:
            st.warning(str(e))
        except ErroIA as e:
            aviso_erro_ia(e, "gerar as questões")
    finais = av.listar_questoes(curso["id"], final=True)
    if finais:
        with st.expander(f"Questões da avaliação final ({len(finais)})"):
            for q in finais:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"**{av.TIPOS[q['tipo']]}** — {q['enunciado'][:160]}")
                c2.button("Excluir", key=f"edu_del_q_{q['id']}", on_click=av.excluir_questao, args=(q["id"],))
