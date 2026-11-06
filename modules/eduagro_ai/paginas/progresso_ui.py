"""Interface de Meu Aprendizado (indicadores e gráficos de progresso)."""
from __future__ import annotations

import streamlit as st

from modules._comum import grafico, layout_escuro, tabela
from modules.eduagro_ai import progresso as pg
from modules.eduagro_ai.paginas.componentes import enviar_ao_tutor

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None

VERDES = ["#69f0ae", "#b9f6ca", "#e6ee9c"]


def render(usuario: dict, nivel: str) -> None:
    uid = usuario["id"]
    r = pg.resumo(uid)
    st.caption(f"Progresso do perfil **{usuario['nome']}** (salvo neste computador).")
    c = st.columns(5)
    c[0].metric("Perguntas ao tutor", r["perguntas_tutor"])
    c[1].metric("Exercícios realizados", r["exercicios"])
    c[2].metric("Acerto médio", f"{r['acertos_pct']:g}%" if r["exercicios"] else "—")
    c[3].metric("Avaliações", r["avaliacoes"])
    c[4].metric("Média das notas", f"{r['media_notas']:g}%" if r["avaliacoes"] else "—")

    cat = pg.por_categoria(uid)
    st.subheader("📈 Progresso por categoria")
    if go is not None:
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Aulas concluídas (%)", x=cat["Categoria"], y=cat["Progresso nas aulas (%)"],
                             marker_color=VERDES[0]))
        fig.add_trace(go.Bar(name="Acertos nos exercícios (%)", x=cat["Categoria"], y=cat["Acertos (%)"].fillna(0),
                             marker_color=VERDES[2]))
        fig.update_layout(barmode="group", title=dict(text="Aulas e exercícios por categoria", font=dict(size=13)),
                          yaxis=dict(range=[0, 100], title="%"), legend=dict(orientation="h"))
        grafico(layout_escuro(fig, 340))
    tabela(cat)

    notas = pg.notas(uid)
    temas = pg.desempenho_por_tema(uid)
    a, b = st.columns(2)
    with a:
        st.subheader("📝 Notas das avaliações")
        if notas.empty:
            st.caption("Nenhuma avaliação realizada ainda.")
        elif go is not None:
            fig = go.Figure(go.Scatter(x=list(range(1, len(notas) + 1)), y=notas["nota"], mode="lines+markers",
                                       text=notas["titulo"], hovertemplate="%{text}<br>%{y}%<extra></extra>",
                                       line=dict(color=VERDES[0])))
            fig.add_hline(y=70, line_dash="dot", line_color="#e6ee9c")
            fig.update_layout(title=dict(text="Evolução das notas (linha pontilhada: 70%)", font=dict(size=13)),
                              xaxis_title="Avaliação nº", yaxis=dict(range=[0, 105], title="%"))
            grafico(layout_escuro(fig, 320))
    with b:
        st.subheader("🎯 Desempenho por tema")
        if temas.empty:
            st.caption("Resolva exercícios para ver seu desempenho por tema.")
        elif go is not None:
            t = temas.head(12)
            fig = go.Figure(go.Bar(x=t["acertos_pct"], y=t["tema"], orientation="h",
                                   marker_color=[VERDES[0] if v >= 70 else "#ffb74d" for v in t["acertos_pct"]]))
            fig.update_layout(title=dict(text="Acertos por tema (%)", font=dict(size=13)), xaxis=dict(range=[0, 100]))
            grafico(layout_escuro(fig, 320))

    revisar = pg.assuntos_para_revisar(uid)
    if revisar:
        st.warning("📌 **Assuntos para revisar** (acerto abaixo de 70%): " + "; ".join(revisar))
        st.button("🤖 Revisar com o Tutor Agro", key="edu_prog_revisar", on_click=enviar_ao_tutor,
                  args=(f"Quero revisar estes assuntos em que errei exercícios: {', '.join(revisar[:5])}. Explique os pontos "
                        f"principais e me dê um exemplo de cada.",))

    st.subheader("🕘 Histórico de aprendizagem")
    hist = pg.historico(uid)
    atv = pg.atividade_diaria(uid)
    if not atv.empty and go is not None and len(atv) > 1:
        fig = go.Figure(go.Bar(x=atv["dia"], y=atv["atividades"], marker_color=VERDES[1]))
        fig.update_layout(title=dict(text="Atividades por dia", font=dict(size=13)))
        grafico(layout_escuro(fig, 240))
    if hist.empty:
        st.caption("Nenhuma atividade registrada ainda.")
    else:
        tabela(hist.rename(columns={"criado_em": "Data/hora", "tipo": "Tipo", "descricao": "Descrição", "categoria": "Categoria"}))
