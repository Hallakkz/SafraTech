"""Interface da Biblioteca de Conhecimento Agro."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from modules._comum import tabela
from modules.eduagro_ai import biblioteca as bib
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai.paginas.componentes import esc, escapar_moeda, referencia_html, tag

STATUS = {"indexado": "🟢 indexado", "sem_texto": "🟠 sem texto extraível", "erro": "🔴 erro", "processando": "⏳ processando",
          "pendente": "⏳ pendente"}


def render(usuario: dict, nivel: str) -> None:
    docs = bib.listar_documentos()
    c1, c2, c3 = st.columns(3)
    c1.metric("Documentos", len(docs))
    c2.metric("Disponíveis para o tutor", sum(1 for d in docs if d["status"] == "indexado"))
    c3.metric("Trechos indexados", sum(int(d["trechos"] or 0) for d in docs))
    st.caption("Os documentos indexados são consultados pelo Tutor Agro por trechos (RAG), sempre com a identificação do "
               "documento e da página. Os arquivos ficam somente neste computador (pasta dados_eduagro/).")
    t1, t2, t3, t4 = st.tabs(["📚 Acervo", "⬆️ Adicionar material", "🔎 Buscar nos documentos", "📦 Materiais do SafraTech"])
    with t1:
        _acervo()
    with t2:
        _adicionar()
    with t3:
        _buscar()
    with t4:
        _materiais_safratech()


def _acervo() -> None:
    a, b = st.columns([1, 2])
    cat = a.selectbox("Categoria", ["Todas", *bib.CATEGORIAS], key="edu_bib_cat")
    termo = b.text_input("Filtrar por título, autor ou instituição", key="edu_bib_termo")
    docs = bib.listar_documentos(None if cat == "Todas" else cat, termo)
    if not docs:
        st.info("Nenhum material cadastrado ainda. Adicione PDFs, apostilas, manuais ou guias em **⬆️ Adicionar material**, "
                "ou importe as publicações já usadas nos bancos em **📦 Materiais do SafraTech**.")
        return
    tabela(pd.DataFrame([{"Título": d["titulo"], "Tipo": d["tipo_material"], "Categoria": d["categoria"],
                          "Instituição/autores": d["instituicao"] or d["autores"], "Ano": d["ano"], "Páginas": d["paginas"],
                          "Trechos": d["trechos"], "Situação": STATUS.get(d["status"], d["status"])} for d in docs]))
    for d in docs:
        with st.expander(f"{d['titulo']} — {STATUS.get(d['status'], d['status'])}"):
            st.markdown(tag(d["tipo_material"], "banco") + tag(d["categoria"]) +
                        (tag("Publicação-fonte do SafraTech", "banco") if d["origem"] == "safratech" else ""),
                        unsafe_allow_html=True)
            for rot, campo in (("Autores", "autores"), ("Instituição", "instituicao"), ("Ano", "ano"), ("Referência", "referencia"),
                               ("Arquivo original", "nome_original"), ("Observações", "observacoes")):
                if d.get(campo):
                    st.markdown(f"**{rot}:** {esc(d[campo])}")
            amostra = bib.trechos_do_documento(d["id"], 2)
            for t in amostra:
                st.caption(escapar_moeda(f"p. {t['pagina']} — {t['texto'][:400]}…"))
            st.button("Excluir da biblioteca", key=f"edu_bib_del_{d['id']}", on_click=bib.excluir_documento, args=(d["id"],))


def _adicionar() -> None:
    with st.form("edu_bib_form", clear_on_submit=False):
        arquivo = st.file_uploader("Arquivo (PDF, TXT ou MD)", type=["pdf", "txt", "md"], key="edu_bib_arquivo")
        titulo = st.text_input("Título", key="edu_bib_titulo")
        a, b = st.columns(2)
        tipo = a.selectbox("Tipo de material", list(bib.TIPOS_MATERIAL), key="edu_bib_tipo")
        categoria = b.selectbox("Categoria", list(bib.CATEGORIAS), key="edu_bib_categoria")
        c, d, e = st.columns([2, 2, 1])
        autores = c.text_input("Autores", key="edu_bib_autores")
        instituicao = d.text_input("Instituição", key="edu_bib_inst")
        ano = e.text_input("Ano", key="edu_bib_ano")
        referencia = st.text_input("Referência bibliográfica (opcional)", key="edu_bib_ref")
        enviar = st.form_submit_button("Adicionar à biblioteca")
    if enviar:
        if arquivo is None:
            st.warning("Selecione um arquivo.")
            return
        barra = st.progress(0.0, text="Extraindo texto…")
        try:
            res = bib.cadastrar_documento(arquivo.name, arquivo.getvalue(), titulo or arquivo.name, tipo, categoria, autores,
                                          instituicao, ano, referencia,
                                          progresso=lambda f: barra.progress(min(1.0, f), text=f"Extraindo texto… {f:.0%}"))
        except ValueError as e:
            st.error(str(e))
            return
        barra.progress(1.0, text="Concluído")
        (st.success if res.status == "indexado" else st.warning)(res.mensagem)


def _buscar() -> None:
    termo = st.text_input("O que você procura nos documentos?", key="edu_bib_busca",
                          placeholder="ex.: suplementação na seca")
    if not termo.strip():
        return
    res = kr.buscar(termo, usar_bancos=False, usar_biblioteca=True, k_biblioteca=8, cobertura=0.3)
    if res.vazio:
        st.info("Nenhum trecho encontrado nos documentos indexados.")
        return
    for r in res.referencias:
        st.markdown(referencia_html(r.para_dict()), unsafe_allow_html=True)
        st.caption(escapar_moeda(r.texto[:700] + ("…" if len(r.texto) > 700 else "")))


def _materiais_safratech() -> None:
    st.caption("Publicações técnicas (Embrapa) que deram origem aos bancos de pecuária do SafraTech e que já estão na pasta "
               "do projeto. Importe para que o tutor possa citar trechos e páginas desses documentos.")
    itens = bib.materiais_do_safratech()
    if not itens:
        st.info("Nenhuma publicação-fonte foi encontrada na pasta do projeto.")
        return
    for i, it in enumerate(itens):
        a, b = st.columns([5, 1.3])
        a.markdown(f"**{esc(it['titulo'])}** — {esc(it['instituicao'] or '')} {esc(it['ano'] or '')} · {it['tamanho_mb']} MB"
                   f" · `{esc(it['codigo'])}`")
        if it["importado"]:
            b.markdown("✅ importado")
        elif b.button("Importar", key=f"edu_imp_{i}"):
            barra = st.progress(0.0, text="Extraindo texto…")
            res = bib.importar_material_safratech(it, lambda f: barra.progress(min(1.0, f), text=f"Extraindo texto… {f:.0%}"))
            (st.success if res.status == "indexado" else st.warning)(res.mensagem)
