"""Meu Aprendizado — indicadores de progresso do estudante (lógica, sem interface)."""
from __future__ import annotations

import pandas as pd

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import cursos as cur

CATEGORIAS = cur.CATEGORIAS


def _n(sql: str, params=()) -> float:
    r = arm.um(sql, params)
    return float(list(r.values())[0] or 0) if r else 0.0


def resumo(usuario_id: int) -> dict:
    cur.garantir_catalogo()
    return {
        "cursos_iniciados": int(_n("SELECT count(*) FROM matricula WHERE usuario_id = ?", (usuario_id,))),
        "cursos_concluidos": int(_n("SELECT count(*) FROM matricula WHERE usuario_id = ? AND status = 'concluido'", (usuario_id,))),
        "aulas_concluidas": int(_n("SELECT count(*) FROM aula_concluida WHERE usuario_id = ?", (usuario_id,))),
        "exercicios": int(_n("SELECT count(*) FROM tentativa WHERE usuario_id = ?", (usuario_id,))),
        "acertos_pct": round(100 * _n("SELECT avg(pontuacao) FROM tentativa WHERE usuario_id = ?", (usuario_id,)), 1),
        "avaliacoes": int(_n("SELECT count(*) FROM avaliacao WHERE usuario_id = ?", (usuario_id,))),
        "media_notas": round(_n("SELECT avg(nota) FROM avaliacao WHERE usuario_id = ?", (usuario_id,)), 1),
        "perguntas_tutor": int(_n("SELECT count(*) FROM mensagem m JOIN conversa c ON c.id = m.conversa_id "
                                  "WHERE c.usuario_id = ? AND m.papel = 'user'", (usuario_id,))),
    }


def por_categoria(usuario_id: int) -> pd.DataFrame:
    linhas = []
    for cat in CATEGORIAS:
        total_cursos = _n("SELECT count(*) FROM curso WHERE categoria = ?", (cat,))
        iniciados = _n("SELECT count(*) FROM matricula m JOIN curso c ON c.id = m.curso_id WHERE m.usuario_id = ? AND c.categoria = ?",
                       (usuario_id, cat))
        concluidos = _n("SELECT count(*) FROM matricula m JOIN curso c ON c.id = m.curso_id WHERE m.usuario_id = ? AND "
                        "c.categoria = ? AND m.status = 'concluido'", (usuario_id, cat))
        aulas_total = _n("SELECT count(*) FROM aula a JOIN curso c ON c.id = a.curso_id WHERE c.categoria = ?", (cat,))
        aulas_feitas = _n("SELECT count(*) FROM aula_concluida ac JOIN aula a ON a.id = ac.aula_id JOIN curso c ON c.id = a.curso_id "
                          "WHERE ac.usuario_id = ? AND c.categoria = ?", (usuario_id, cat))
        exerc = _n("SELECT count(*) FROM tentativa WHERE usuario_id = ? AND categoria = ?", (usuario_id, cat))
        acerto = _n("SELECT avg(pontuacao) FROM tentativa WHERE usuario_id = ? AND categoria = ?", (usuario_id, cat))
        linhas.append({"Categoria": cat, "Cursos no catálogo": int(total_cursos), "Cursos iniciados": int(iniciados),
                       "Cursos concluídos": int(concluidos), "Aulas concluídas": int(aulas_feitas),
                       "Aulas cadastradas": int(aulas_total),
                       "Progresso nas aulas (%)": round(100 * aulas_feitas / aulas_total, 1) if aulas_total else 0.0,
                       "Exercícios": int(exerc), "Acertos (%)": round(100 * acerto, 1) if exerc else None})
    return pd.DataFrame(linhas)


def cursos_do_usuario(usuario_id: int) -> pd.DataFrame:
    linhas = arm.consultar("""
        SELECT c.nome AS curso, c.categoria, m.status, m.iniciado_em, m.concluido_em,
               (SELECT count(*) FROM aula a WHERE a.curso_id = c.id) AS aulas,
               (SELECT count(*) FROM aula_concluida ac JOIN aula a ON a.id = ac.aula_id
                 WHERE a.curso_id = c.id AND ac.usuario_id = m.usuario_id) AS concluidas,
               (SELECT max(nota) FROM avaliacao v WHERE v.curso_id = c.id AND v.usuario_id = m.usuario_id AND v.final = 1) AS nota_final
        FROM matricula m JOIN curso c ON c.id = m.curso_id WHERE m.usuario_id = ? ORDER BY m.iniciado_em DESC""", (usuario_id,))
    df = pd.DataFrame(linhas)
    if not df.empty:
        df["status"] = df["status"].map({"concluido": "✅ Concluído", "em_andamento": "📘 Em andamento"}).fillna(df["status"])
    return df


def notas(usuario_id: int) -> pd.DataFrame:
    return pd.DataFrame(arm.consultar("SELECT criado_em, titulo, categoria, final, total, acertos, nota FROM avaliacao "
                                      "WHERE usuario_id = ? ORDER BY criado_em, id", (usuario_id,)))


def desempenho_por_tema(usuario_id: int) -> pd.DataFrame:
    df = pd.DataFrame(arm.consultar("SELECT coalesce(tema, 'Sem tema') AS tema, categoria, count(*) AS questoes, "
                                    "round(100 * avg(pontuacao), 1) AS acertos_pct FROM tentativa WHERE usuario_id = ? "
                                    "GROUP BY 1, 2 ORDER BY acertos_pct, questoes DESC", (usuario_id,)))
    return df


def assuntos_para_revisar(usuario_id: int, limite_pct: float = 70.0) -> list[str]:
    df = desempenho_por_tema(usuario_id)
    if df.empty:
        return []
    return df[df["acertos_pct"] < limite_pct]["tema"].tolist()


def historico(usuario_id: int, limite: int = 50) -> pd.DataFrame:
    return pd.DataFrame(arm.consultar("SELECT criado_em, tipo, descricao, categoria FROM evento WHERE usuario_id = ? "
                                      "ORDER BY id DESC LIMIT ?", (usuario_id, limite)))


def atividade_diaria(usuario_id: int) -> pd.DataFrame:
    return pd.DataFrame(arm.consultar("SELECT substr(criado_em, 1, 10) AS dia, count(*) AS atividades FROM evento "
                                      "WHERE usuario_id = ? GROUP BY 1 ORDER BY 1", (usuario_id,)))
