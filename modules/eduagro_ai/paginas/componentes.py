"""Componentes de interface compartilhados pelas áreas do EduAgro AI."""
from __future__ import annotations

import html
import re
from typing import Optional

import streamlit as st

from modules.eduagro_ai import avaliacoes as av
from modules.eduagro_ai.deepseek_client import ErroIA, IALimiteRequisicoes, IASemSaldo, IANaoConfigurada

ROTULO_AREA_BANCO = {"agricultura": "Agricultura", "pecuaria": "Pecuária", "biblioteca": "Biblioteca", "curso": "Curso"}


def escapar_moeda(t: str) -> str:
    """'R$ 10' seria lido como início de fórmula LaTeX pelo Streamlit; escapa o cifrão de valores em reais."""
    return re.sub(r"(?<!\\)R\$", r"R\\$", str(t or ""))


def md(t: str) -> None:
    st.markdown(escapar_moeda(t))


def esc(t) -> str:
    return html.escape(str(t or ""))


def tag(texto: str, classe: str = "") -> str:
    return f'<span class="edu-tag {classe}">{esc(texto)}</span>'


def aviso_erro_ia(e: ErroIA, contexto: str = "") -> None:
    """Mensagem clara quando a IA está indisponível (nunca simula uma resposta)."""
    icone = "💳" if isinstance(e, IASemSaldo) else "⏳" if isinstance(e, IALimiteRequisicoes) else "🔌"
    st.error(f"{icone} **A inteligência artificial está indisponível{(' para ' + contexto) if contexto else ''}.** "
             f"{e.mensagem_usuario}")
    if isinstance(e, IANaoConfigurada):
        st.caption("Variáveis esperadas no arquivo .env: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL e DEEPSEEK_MODEL.")
    elif e.detalhe:
        st.caption(f"Detalhe técnico: {e.detalhe}")
    st.caption("Os demais recursos do EduAgro (cursos, biblioteca, exercícios de cálculo e progresso) continuam funcionando.")


def referencia_html(r: dict) -> str:
    if r.get("origem") == "internet":
        url = str(r.get("localizacao") or "")
        link = f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(r.get("fonte") or url)}</a>' \
            if url.startswith(("http://", "https://")) else esc(r.get("fonte"))
        return (f'<div class="edu-ref"><b>[{esc(r.get("rotulo"))}] {esc(r.get("titulo"))}</b> '
                f'{tag("🔗 Internet", "alerta")}<br>'
                f'<span class="fonte">🔗 {link}</span></div>')
    bancos = ", ".join(r.get("bancos") or [])
    regs = ", ".join((r.get("registros") or [])[:5])
    fonte = esc(r.get("fonte") or "fonte não informada")
    meta = ", ".join(x for x in (r.get("instituicao"), str(r.get("ano") or "")) if x)
    loc = " — ".join(x for x in (r.get("localizacao"), f"p. {r['pagina']}" if r.get("pagina") else "") if x)
    classe = "banco" if r.get("origem") == "banco" else ""
    return (f'<div class="edu-ref"><b>[{esc(r.get("rotulo"))}] {esc(r.get("titulo"))}</b> '
            f'{tag(r.get("tipo") or "", classe)}<br>'
            f'<span class="fonte">📚 {fonte}{(" (" + esc(meta) + ")") if meta else ""}{(" — " + esc(loc)) if loc else ""}'
            f'<br>🗄️ {esc(bancos)}{(" · registro(s): " + esc(regs)) if regs else ""}</span></div>')


def mostrar_referencias(refs: list[dict], titulo: str = "📚 Referências consultadas", expandido: bool = False,
                        mostrar_trecho: bool = True) -> None:
    with st.expander(f"{titulo} ({len(refs)})", expanded=expandido):
        if not refs:
            st.caption("Nenhuma referência dos bancos do SafraTech ou da Biblioteca foi encontrada para este assunto.")
            return
        st.caption("Registros reais recuperados dos bancos do SafraTech (S) e da Biblioteca (D) — e, quando os bancos não "
                   "tinham a informação, páginas da internet (W) — entregues à IA. Use-os para conferir as citações da resposta.")
        for r in refs:
            st.markdown(referencia_html(r), unsafe_allow_html=True)
            if mostrar_trecho and r.get("trecho"):
                st.caption(escapar_moeda(r["trecho"][:600] + ("…" if len(r["trecho"]) > 600 else "")))


def legenda_origens() -> None:
    st.markdown(f'<div class="edu-legenda">{tag("📚 Bancos do SafraTech", "banco")} informação encontrada nos bancos, com citação '
                f'[S#] · {tag("🧠 Explicação do tutor (IA)", "ia")} produzida pela inteligência artificial · '
                f'{tag("🧮 Exemplo hipotético", "hipotetico")} números fictícios, só para ensinar · '
                f'{tag("🔗 Internet", "alerta")} só quando os bancos não têm a informação [W#]</div>',
                unsafe_allow_html=True)


# =====================================================================================================
# Questionário (usado em exercícios, questões dos cursos e avaliação final)
# =====================================================================================================
def questionario(questoes: list[dict], chave: str, usuario_id: int, titulo: str, curso_id: Optional[int] = None,
                 categoria: Optional[str] = None, final: bool = False) -> None:
    from modules.eduagro_ai.exercicios_calculo import AVISO_HIPOTETICO  # noqa: F401  (rótulo usado nos enunciados)
    chave_res = f"{chave}_resultado"
    if not questoes:
        st.info("Nenhuma questão disponível.")
        return
    with st.form(f"{chave}_form"):
        respostas = []
        for i, q in enumerate(questoes):
            st.markdown(f"**Questão {i + 1}** · {av.TIPOS.get(q['tipo'], q['tipo'])} "
                        f"{tag(av.ORIGENS.get(q.get('origem'), ''), 'ia' if q.get('origem') == 'ia' else 'banco')}",
                        unsafe_allow_html=True)
            md(q["enunciado"])
            k = f"{chave}_r{i}"
            if q["tipo"] == "multipla_escolha":
                alts = q.get("alternativas") or []
                letras = list(av.LETRAS[:len(alts)])
                respostas.append(st.radio("Sua resposta", letras, index=None, key=k,
                                          format_func=lambda l, alts=alts: f"{l}) {alts[av.LETRAS.index(l)]}"))
            elif q["tipo"] == "verdadeiro_falso":
                respostas.append(st.radio("Sua resposta", ["Verdadeiro", "Falso"], index=None, key=k, horizontal=True))
            elif q["tipo"] == "pratica" and q.get("resposta_numerica") is not None:
                respostas.append(st.text_input(f"Sua resposta (número{', em ' + q['unidade'] if q.get('unidade') else ''})",
                                               key=k, placeholder="ex.: 0,85"))
            else:
                respostas.append(st.text_area("Sua resposta", key=k, height=120))
            st.divider()
        enviado = st.form_submit_button("✅ Enviar respostas")
    if enviado:
        if any(r in (None, "") for r in respostas):
            st.warning("Responda todas as questões antes de enviar.")
        else:
            itens = []
            try:
                with st.spinner("Corrigindo…"):
                    for q, r in zip(questoes, respostas):
                        itens.append((q, av.corrigir(q, r)))
            except ErroIA as e:
                aviso_erro_ia(e, "corrigir as respostas abertas")
                st.info("As respostas abertas não foram corrigidas e nada foi registrado no seu progresso. "
                        "Veja abaixo as respostas esperadas para autoestudo.")
                for i, q in enumerate(questoes):
                    if q["tipo"] in ("estudo_de_caso", "pratica") and q.get("resposta_numerica") is None:
                        with st.expander(f"Resposta esperada — questão {i + 1}"):
                            st.markdown(q.get("resposta") or "")
                            st.markdown(q.get("explicacao") or "")
                itens = []
            if itens:
                res = av.registrar_avaliacao(usuario_id, titulo, itens, curso_id=curso_id, categoria=categoria, final=final)
                st.session_state[chave_res] = {"resumo": res, "itens": [(q, c.__dict__) for q, c in itens]}
    if chave_res in st.session_state:
        mostrar_resultado(st.session_state[chave_res], chave)


def mostrar_resultado(resultado: dict, chave: str) -> None:
    res = resultado["resumo"]
    st.subheader("📊 Resultado")
    c1, c2, c3 = st.columns(3)
    c1.metric("Nota", f"{res['nota']:g}%")
    c2.metric("Acertos", f"{res['acertos']:g} de {res['total']}")
    c3.metric("Situação", "Bom resultado" if res["nota"] >= 70 else "Revisar conteúdo")
    for i, (q, c) in enumerate(resultado["itens"], start=1):
        icone = "✅" if c["correta"] else "❌"
        situacao = "correta" if c["correta"] else "incorreta"
        parcial = "" if c["pontuacao"] in (0, 1) else " (pontuação {:.0%})".format(c["pontuacao"])
        with st.expander(f"{icone} Questão {i} — {situacao}{parcial}", expanded=not c["correta"]):
            md(f"**Sua resposta:** {c['resposta_usuario'] or '—'}")
            md(f"**Resposta correta:** {c['resposta_correta']}")
            if c.get("feedback"):
                md(f"**Comentário da correção ({c.get('corrigida_por')}):** {c['feedback']}")
            if q.get("explicacao"):
                st.markdown("**Explicação da resposta**")
                md(q["explicacao"])
            if q.get("justificativa"):
                st.markdown("**Justificativa técnica**")
                md(q["justificativa"])
            if q.get("referencias"):
                for r in q["referencias"]:
                    if r.get("origem") == "banco" or r.get("origem") == "biblioteca":
                        st.markdown(referencia_html(r), unsafe_allow_html=True)
            st.caption(av.ORIGENS.get(q.get("origem"), ""))
    if res.get("revisar"):
        st.warning("📌 **Assuntos para estudar novamente:** " + "; ".join(res["revisar"]))
        st.button("🤖 Revisar esses assuntos com o Tutor Agro", key=f"{chave}_revisar",
                  on_click=enviar_ao_tutor, args=(f"Me ajude a revisar: {', '.join(res['revisar'])}. Explique os pontos principais "
                                                 f"e onde costumam acontecer os erros.",))
    else:
        st.success("Parabéns! Nenhum assunto pendente de revisão neste conjunto.")


def enviar_ao_tutor(pergunta: str) -> None:
    """Callback: abre o Tutor com uma pergunta pronta (processada na próxima execução)."""
    st.session_state["edu_secao"] = 0
    st.session_state["edu_pendente"] = {"texto": pergunta, "modo": "pergunta"}
