"""Interface de Exercícios e Avaliações."""
from __future__ import annotations

import random

import streamlit as st

from modules.eduagro_ai import avaliacoes as av
from modules.eduagro_ai import cursos as cur
from modules.eduagro_ai import exercicios_calculo as ec
from modules.eduagro_ai.deepseek_client import ErroIA, obter_cliente
from modules.eduagro_ai.paginas.componentes import aviso_erro_ia, mostrar_referencias, questionario

AREA_POR_CATEGORIA = {"Agricultura": "agricultura", "Pecuária": "pecuaria", "Gestão Rural": "todas"}


def render(usuario: dict, nivel: str) -> None:
    t1, t2 = st.tabs(["🧮 Treino de cálculos (bancos)", "🤖 Exercícios gerados por IA"])
    with t1:
        _calculos(usuario)
    with t2:
        _gerados_ia(usuario, nivel)


# ------------------------------------------------------------------ cálculos com fórmulas dos bancos
def _calculos(usuario: dict) -> None:
    st.caption("Exercícios práticos com as fórmulas cadastradas nos bancos do SafraTech. A resposta correta é calculada pelo "
               "aplicativo; os números do enunciado são hipotéticos.")
    try:
        geradores = ec.disponiveis()
    except Exception as e:  # pragma: no cover - falha inesperada de carga
        st.error(f"Não foi possível carregar as fórmulas dos bancos: {e}")
        return
    if not geradores:
        st.warning("Nenhuma fórmula disponível: os bancos do SafraTech estão inacessíveis.")
        return
    a, b, c = st.columns([2, 1, 1])
    cats = ["Todas", *sorted({g.categoria for g in geradores})]
    cat = b.selectbox("Categoria", cats, key="edu_calc_cat")
    opcoes = [g.codigo for g in geradores if cat == "Todas" or g.categoria == cat]
    nomes = {g.codigo: f"{g.nome} ({g.categoria})" for g in geradores}
    codigo = a.selectbox("Cálculo", opcoes, format_func=nomes.get, key="edu_calc_codigo")
    if c.button("🎲 Novo exercício", key="edu_calc_novo") or st.session_state.get("edu_calc_atual", {}).get("gerador") != codigo:
        q = ec.gerar(codigo, random.randrange(10 ** 9))
        q["id"] = None  # exercício sorteado: não é gravado como questão, apenas a tentativa entra no progresso
        st.session_state["edu_calc_atual"] = q
        st.session_state.pop("edu_calc_resultado", None)
        st.session_state["edu_calc_seq"] = st.session_state.get("edu_calc_seq", 0) + 1
    q = st.session_state["edu_calc_atual"]
    questionario([q], f"edu_calc_{st.session_state.get('edu_calc_seq', 0)}", usuario["id"], f"Treino: {q['tema']}",
                 categoria=q["categoria"])


# ------------------------------------------------------------------ exercícios por IA
def _gerados_ia(usuario: dict, nivel: str) -> None:
    st.caption("A IA cria exercícios **somente** a partir das referências recuperadas dos bancos do SafraTech, da Biblioteca "
               "e das aulas revisadas. Questões sem referência válida são descartadas. São exercícios de estudo gerados por IA "
               "— não são questões oficiais de nenhuma instituição.")
    tema_padrao = st.session_state.pop("edu_tema_exercicio", None)
    if tema_padrao:
        st.session_state["edu_ia_tema"] = tema_padrao
    with st.form("edu_ia_form"):
        tema = st.text_input("Tema", key="edu_ia_tema", placeholder="ex.: interpretação de potássio no solo; GMD na recria")
        a, b, c = st.columns(3)
        categoria = a.selectbox("Categoria", list(cur.CATEGORIAS), key="edu_ia_cat")
        qtd = b.number_input("Quantidade", min_value=1, max_value=10, value=5, step=1, key="edu_ia_qtd")
        nivel_q = c.selectbox("Nível", list(cur.NIVEIS), index=list(cur.NIVEIS).index(nivel) if nivel in cur.NIVEIS else 0,
                              key="edu_ia_nivel")
        tipos = st.multiselect("Tipos de questão", list(av.TIPOS), default=["multipla_escolha", "verdadeiro_falso", "pratica"],
                               format_func=av.TIPOS.get, key="edu_ia_tipos")
        curso_id = None
        gerar = st.form_submit_button("🤖 Gerar exercícios")
    if gerar:
        if not tema.strip():
            st.warning("Informe o tema.")
        elif not tipos:
            st.warning("Escolha ao menos um tipo de questão.")
        else:
            try:
                with st.spinner("Consultando referências e gerando exercícios…"):
                    g = av.gerar_questoes_ia(obter_cliente(), tema, nivel_q, int(qtd), tipos,
                                             area=AREA_POR_CATEGORIA.get(categoria, "todas"), categoria=categoria,
                                             curso_id=curso_id)
                if not g.questoes:
                    st.warning("A IA não produziu questões válidas (todas precisam citar uma referência real). Tente outro tema.")
                else:
                    for q in g.questoes:
                        q["id"] = av.salvar_questao(q, curso_id=curso_id)
                    st.session_state["edu_ia_questoes"] = {"questoes": g.questoes, "tema": tema, "categoria": categoria,
                                                           "curso_id": curso_id, "refs": [r.para_dict() for r in g.busca.referencias],
                                                           "descartadas": g.descartadas}
                    st.session_state["edu_ia_seq"] = st.session_state.get("edu_ia_seq", 0) + 1
            except ValueError as e:
                st.warning(str(e))
            except ErroIA as e:
                aviso_erro_ia(e, "gerar exercícios")
    pacote = st.session_state.get("edu_ia_questoes")
    if pacote:
        st.markdown(f"#### Exercícios: {pacote['tema']}")
        if pacote["descartadas"]:
            st.caption(f"{pacote['descartadas']} questão(ões) descartada(s) por não citarem uma referência válida.")
        mostrar_referencias(pacote["refs"], "📚 Referências usadas na geração")
        questionario(pacote["questoes"], f"edu_ia_{st.session_state.get('edu_ia_seq', 0)}", usuario["id"],
                     f"Exercícios: {pacote['tema']}", curso_id=pacote["curso_id"], categoria=pacote["categoria"])


# ------------------------------------------------------------------ questões cadastradas nos cursos
def _questoes_cursos(usuario: dict) -> None:
    cursos = cur.listar_cursos()
    com_q = [(c, av.listar_questoes(c["id"], final=False)) for c in cursos]
    com_q = [(c, qs) for c, qs in com_q if qs]
    if not com_q:
        st.info("Nenhum curso possui questões de prática cadastradas. Questões geradas por IA com um curso selecionado ficam "
                "disponíveis aqui; a avaliação final de cada curso fica na página do curso.")
        return
    idx = st.selectbox("Curso", list(range(len(com_q))), format_func=lambda i: f"{com_q[i][0]['nome']} ({len(com_q[i][1])} questões)",
                       key="edu_qc_curso")
    curso, questoes = com_q[idx]
    questionario(questoes[-10:], f"edu_qc_{curso['id']}", usuario["id"], f"Prática — {curso['nome']}", curso_id=curso["id"],
                 categoria=curso["categoria"])

