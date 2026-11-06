"""Consultas ao solo_database (somente leitura, parametrizadas). Usa as tabelas/visões reais:
solo.registro, solo.v_registro_com_fonte, solo.registro_divergencia, meta.divergencia, meta.fonte, solo.metodo_analitico."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from database.connections import consultar

BANCO = "solo"

COLUNAS_FAIXA = """registro_id, categoria, parametro, cultura, regiao, tipo_solo, camada, metodo,
    valor, valor_min, valor_max, operador_min, operador_max, unidade, unidade_base, classificacao,
    texto, condicoes, observacoes, divergencia_ids, fonte_id, secao, pagina_pdf, pagina_impressa,
    tipo_dado, fonte_titulo, fonte_autores, fonte_instituicao, fonte_ano, referencia_abnt"""


def faixas_interpretacao(parametros: Iterable[str], culturas: Iterable[str]) -> pd.DataFrame:
    """Faixas de interpretação e níveis críticos dos parâmetros informados, restritas às culturas aplicáveis."""
    sql = f"""SELECT {COLUNAS_FAIXA}
              FROM solo.v_registro_com_fonte
              WHERE categoria IN ('faixa_interpretacao', 'nivel_critico')
                AND parametro = ANY(:parametros)
                AND cultura = ANY(:culturas)
              ORDER BY parametro, fonte_id, secao, tipo_solo, valor_min NULLS FIRST, valor NULLS FIRST"""
    return consultar(BANCO, sql, {"parametros": list(parametros), "culturas": list(culturas)})


def culturas_disponiveis() -> pd.DataFrame:
    return consultar(BANCO, "SELECT cultura, count(*) AS n FROM solo.registro GROUP BY cultura ORDER BY cultura")


def texturas_disponiveis() -> list[str]:
    df = consultar(BANCO, """SELECT DISTINCT tipo_solo FROM solo.registro
                             WHERE categoria = 'faixa_interpretacao' AND tipo_solo LIKE 'Textura %' ORDER BY tipo_solo""")
    return df["tipo_solo"].tolist() if not df.empty else []


def conversoes_unidade() -> pd.DataFrame:
    """Conversões cadastradas na fonte (ex.: K mg/dm3 × 0,00256 = cmolc/dm3; MO = C × 1,724)."""
    return consultar(BANCO, """SELECT registro_id, parametro, texto, fonte_id, secao, pagina_impressa
                               FROM solo.registro WHERE categoria = 'conversao_unidade' ORDER BY parametro""")


def divergencias(registro_ids: Iterable[str]) -> pd.DataFrame:
    ids = list(registro_ids)
    if not ids:
        return pd.DataFrame(columns=["divergencia_id", "registro_id", "parametro", "descricao", "fontes", "tratamento", "tipo"])
    return consultar(BANCO, """SELECT d.divergencia_id, rd.registro_id, d.parametro, d.descricao, d.fontes, d.tratamento, d.tipo
                               FROM solo.registro_divergencia rd JOIN meta.divergencia d USING (divergencia_id)
                               WHERE rd.registro_id = ANY(:ids) ORDER BY d.divergencia_id""", {"ids": ids})


def criterios_relacionados(culturas: Iterable[str], palavras: Iterable[str]) -> pd.DataFrame:
    """Critérios de calagem/gessagem/adubação e equações cadastrados (exibidos como referência, não como recomendação)."""
    padroes = [f"%{p}%" for p in palavras]
    return consultar(BANCO, """SELECT registro_id, categoria, parametro, classificacao, valor, valor_min, valor_max,
                                      operador_min, operador_max, unidade, texto, condicoes, cultura, regiao,
                                      fonte_id, secao, pagina_impressa, referencia_abnt
                               FROM solo.v_registro_com_fonte
                               WHERE categoria IN ('criterio_calagem', 'criterio_gessagem', 'equacao', 'criterio_adubacao')
                                 AND cultura = ANY(:culturas)
                                 AND (parametro ILIKE ANY(:padroes) OR texto ILIKE ANY(:padroes))
                               ORDER BY categoria, parametro""", {"culturas": list(culturas), "padroes": padroes})


def fontes(fonte_ids: Iterable[str]) -> pd.DataFrame:
    return consultar(BANCO, """SELECT fonte_id, titulo, autores, instituicao, ano, referencia_abnt, tipo_dado
                               FROM meta.fonte WHERE fonte_id = ANY(:ids) ORDER BY fonte_id""", {"ids": list(fonte_ids)})


def metodos_analiticos() -> pd.DataFrame:
    return consultar(BANCO, """SELECT codigo, titulo, extrator_ou_meio, relacao_solo_solucao, determinacao, unidade_resultado,
                                      observacoes, pagina_impressa
                               FROM solo.metodo_analitico WHERE status_extracao = 'detalhado' ORDER BY codigo""")
