"""
Consultas (somente leitura, parametrizadas) aos três bancos de pecuária de corte do SafraTech.

Bancos (chaves de database.connections.BANCOS):
    pecuaria_compra          -> pecuaria_compra_database
    pecuaria_desempenho      -> pecuaria_desempenho_database
    pecuaria_rentabilidade   -> pecuaria_rentabilidade_database

Todas as tabelas e views ficam no esquema public e foram criadas pelos scripts em
BANCO_DE_DADOS_SAFRATECH_PECUARIA/<banco>/estrutura/. As views usadas aqui (definições conferidas em
02_criar_views.sql) são:
    vw_referencias_rendimento_carcaca, vw_referencias_gmd, vw_referencias_peso,
    vw_custos_referencia, vw_precos_arroba_historicos, vw_perguntas_por_tema.
As views de cálculo (vw_lote_compra_viabilidade, vw_gmd_lote, vw_gmd_lote_x_referencia, vw_projecao_cenario,
vw_comparativo_cenarios) trabalham sobre as tabelas de entrada do banco (lote_compra, lote_rebanho,
cenario_venda...). Como o app abre sessões somente leitura e não grava dados do produtor, as mesmas fórmulas
são aplicadas em modules/pecuaria/calculos.py; a equivalência é verificada em tests/test_pecuaria_views.py.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from database.connections import consultar

COMPRA = "pecuaria_compra"
DESEMPENHO = "pecuaria_desempenho"
RENTABILIDADE = "pecuaria_rentabilidade"
BANCOS_PECUARIA = (COMPRA, DESEMPENHO, RENTABILIDADE)

# Códigos que não identificam um genótipo de animal (usados só em registros gerais)
RACAS_NAO_SELECIONAVEIS = ("NAO_APLICAVEL",)
SISTEMAS_NAO_SELECIONAVEIS = ("NAO_ESPECIFICADO", "NAO_APLICAVEL")

_COLS_FONTE = """f.titulo AS fonte_titulo, f.autores AS fonte_autores, f.instituicao AS fonte_instituicao,
       f.ano_publicacao AS fonte_ano, f.referencia_abnt"""


def _lista(valores: Iterable) -> list[str]:
    return sorted({str(v) for v in valores if v is not None and str(v) != ""})


# ---------------------------------------------------------------- catálogos
def racas(banco: str) -> pd.DataFrame:
    return consultar(banco, """
        SELECT raca_codigo, nome, grupo_genetico, descricao
        FROM raca_genotipo
        WHERE raca_codigo <> ALL(:excluir)
        ORDER BY CASE WHEN raca_codigo = 'NAO_ESPECIFICADA' THEN 1 ELSE 0 END, nome
    """, {"excluir": list(RACAS_NAO_SELECIONAVEIS)})


def sistemas(banco: str) -> pd.DataFrame:
    return consultar(banco, """
        SELECT sistema_codigo, nome, descricao
        FROM sistema_criacao
        WHERE sistema_codigo <> ALL(:excluir)
        ORDER BY nome
    """, {"excluir": list(SISTEMAS_NAO_SELECIONAVEIS)})


def metadados(banco: str) -> pd.DataFrame:
    return consultar(banco, "SELECT chave, valor FROM metadados_banco ORDER BY chave")


# ---------------------------------------------------------------- fontes e transparência
def fontes(banco: str, codigos: Iterable[str]) -> pd.DataFrame:
    return consultar(banco, """
        SELECT fonte_codigo, titulo, autores, instituicao, colecao_serie, numero_serie, ano_publicacao,
               tipo_documento, abrangencia_regional, referencia_abnt, observacoes
        FROM fonte
        WHERE fonte_codigo = ANY(:codigos)
        ORDER BY fonte_codigo
    """, {"codigos": _lista(codigos)})


def formulas(banco: str, codigos: Iterable[str]) -> pd.DataFrame:
    return consultar(banco, f"""
        SELECT fc.formula_codigo, fc.nome, fc.expressao, fc.variaveis, fc.unidade_resultado, fc.fonte_codigo,
               fc.pagina_pdf, fc.observacoes, {_COLS_FONTE}
        FROM formula_calculo fc
        JOIN fonte f USING (fonte_codigo)
        WHERE fc.formula_codigo = ANY(:codigos)
        ORDER BY fc.formula_codigo
    """, {"codigos": _lista(codigos)})


def divergencias(banco: str, ids_registro: Iterable[str]) -> pd.DataFrame:
    return consultar(banco, """
        SELECT d.divergencia_codigo, d.descricao, d.tratamento, dr.tabela_origem, dr.id_registro
        FROM divergencia_registro dr
        JOIN divergencia d USING (divergencia_codigo)
        WHERE dr.id_registro = ANY(:ids)
        ORDER BY d.divergencia_codigo, dr.id_registro
    """, {"ids": _lista(ids_registro)})


def perguntas_relacionadas(banco: str, termo: str, temas: Iterable[str], limite: int = 5) -> pd.DataFrame:
    """Perguntas e respostas das fontes (busca textual em português) dentro dos temas indicados."""
    if not termo:
        return pd.DataFrame(columns=["id_pergunta", "fonte_codigo", "numero_pergunta", "capitulo_titulo", "pergunta",
                                     "resposta", "pagina_pdf_inicio", "pagina_impressa_inicio", "localizacao",
                                     "possui_conteudo_nao_transcrito", "fonte_titulo", "fonte_ano"])
    return consultar(banco, """
        SELECT q.id_pergunta, q.fonte_codigo, q.numero_pergunta, q.capitulo_titulo, q.pergunta, q.resposta,
               q.pagina_pdf_inicio, q.pagina_impressa_inicio, q.localizacao, q.possui_conteudo_nao_transcrito,
               f.titulo AS fonte_titulo, f.ano_publicacao AS fonte_ano
        FROM pergunta_resposta q
        JOIN fonte f USING (fonte_codigo)
        WHERE to_tsvector('portuguese', q.pergunta || ' ' || q.resposta) @@ plainto_tsquery('portuguese', :termo)
          AND EXISTS (SELECT 1 FROM vw_perguntas_por_tema t WHERE t.id_pergunta = q.id_pergunta AND t.tema = ANY(:temas))
        ORDER BY q.fonte_codigo, q.numero_pergunta
        LIMIT :limite
    """, {"termo": termo, "temas": _lista(temas), "limite": int(limite)})


# ---------------------------------------------------------------- referências técnicas
def referencias_rendimento(banco: str) -> pd.DataFrame:
    """vw_referencias_rendimento_carcaca + códigos de raça/sistema e dados da fonte."""
    return consultar(banco, f"""
        SELECT v.id_registro, v.parametro, v.raca, v.grupo_genetico, v.sexo, v.idade_fase, v.sistema, v.regiao,
               v.macro_regiao, v.valor_numerico, v.valor_min, v.valor_max, v.condicoes_aplicacao, v.tipo_dado,
               v.periodo_referencia, v.fonte_codigo, v.pagina_pdf, v.localizacao, v.status_validacao, v.observacoes,
               p.raca_codigo, p.sistema_codigo, p.pagina_impressa, {_COLS_FONTE}
        FROM vw_referencias_rendimento_carcaca v
        JOIN parametro_tecnico p USING (id_registro)
        JOIN fonte f ON f.fonte_codigo = v.fonte_codigo
        ORDER BY v.raca, v.sexo, v.id_registro
    """)


def referencias_gmd(banco: str) -> pd.DataFrame:
    """vw_referencias_gmd (GMD em kg/dia, já padronizado) + códigos e dados da fonte."""
    return consultar(banco, f"""
        SELECT v.id_registro, v.parametro, v.raca, v.grupo_genetico, v.sexo, v.idade_fase, v.fase, v.sistema, v.regiao,
               v.macro_regiao, v.gmd_kg_dia, v.gmd_min_kg_dia, v.gmd_max_kg_dia, v.condicoes_aplicacao, v.tipo_dado,
               v.periodo_referencia, v.fonte_codigo, v.pagina_pdf, v.localizacao, v.status_validacao,
               p.raca_codigo, p.sistema_codigo, p.pagina_impressa, {_COLS_FONTE}
        FROM vw_referencias_gmd v
        JOIN parametro_tecnico p USING (id_registro)
        JOIN fonte f ON f.fonte_codigo = v.fonte_codigo
        ORDER BY v.raca, v.sexo, v.fase, v.id_registro
    """)


def referencias_peso(banco: str = DESEMPENHO) -> pd.DataFrame:
    """vw_referencias_peso restrita a peso vivo (kg PV) — peso de carcaça não é comparável ao peso vivo informado."""
    return consultar(banco, f"""
        SELECT v.id_registro, v.parametro, v.raca, v.grupo_genetico, v.sexo, v.idade_fase, v.fase, v.sistema, v.regiao,
               v.macro_regiao, v.valor_numerico, v.valor_min, v.valor_max, v.unidade, v.condicoes_aplicacao, v.tipo_dado,
               v.periodo_referencia, v.fonte_codigo, v.pagina_pdf, v.localizacao, v.status_validacao,
               p.raca_codigo, p.sistema_codigo, p.pagina_impressa, p.unidade_padrao, {_COLS_FONTE}
        FROM vw_referencias_peso v
        JOIN parametro_tecnico p USING (id_registro)
        JOIN fonte f ON f.fonte_codigo = v.fonte_codigo
        WHERE p.unidade_padrao = 'kg_pv'
        ORDER BY v.raca, v.sexo, v.fase, v.id_registro
    """)


# ---------------------------------------------------------------- dados econômicos (históricos)
def precos_arroba_historicos(banco: str) -> pd.DataFrame:
    """vw_precos_arroba_historicos: cotações registradas nas publicações (natureza e uso permitido incluídos)."""
    return consultar(banco, """
        SELECT v.id_preco, v.data_referencia, v.estado, v.municipio_praca, v.categoria_animal, v.preco, v.unidade_codigo,
               v.moeda, v.fonte_codigo, v.tipo_cotacao, v.natureza, v.uso_permitido, v.pagina_pdf,
               f.titulo AS fonte_titulo, f.ano_publicacao AS fonte_ano
        FROM vw_precos_arroba_historicos v
        JOIN fonte f ON f.fonte_codigo = v.fonte_codigo
        ORDER BY v.data_referencia, v.id_preco
    """)


def precos_insumo_historicos(banco: str = RENTABILIDADE) -> pd.DataFrame:
    return consultar(banco, """
        SELECT pi.id_preco_insumo, pi.insumo, pi.data_referencia, pi.estado, pi.municipio_praca, pi.preco, pi.unidade_codigo,
               pi.fonte_codigo, pi.tipo_cotacao, pi.pagina_pdf, pi.localizacao, f.titulo AS fonte_titulo,
               f.ano_publicacao AS fonte_ano
        FROM preco_insumo pi
        JOIN fonte f USING (fonte_codigo)
        ORDER BY pi.insumo, pi.id_preco_insumo
    """)


def custos_referencia(banco: str) -> pd.DataFrame:
    """vw_custos_referencia: estruturas de custo de fazendas modelo/típicas registradas nas publicações."""
    return consultar(banco, """
        SELECT v.id_custo, v.fonte_codigo, v.regiao, v.macro_regiao, v.escopo, v.periodo_referencia, v.localizacao,
               v.grupo, v.nivel, v.item, v.valor_brl, v.valor_usd, v.participacao_pct, v.base_participacao,
               v.status_validacao, f.titulo AS fonte_titulo, f.ano_publicacao AS fonte_ano
        FROM vw_custos_referencia v
        JOIN fonte f ON f.fonte_codigo = v.fonte_codigo
    """)


def receitas_referencia(banco: str) -> pd.DataFrame:
    return consultar(banco, """
        SELECT r.id_receita, r.fonte_codigo, g.nome AS regiao, r.raca_codigo, r.periodo_referencia, r.ano_referencia,
               r.localizacao, r.categoria_animal, r.sexo, r.quantidade_cab, r.peso_vivo_kg, r.peso_carcaca_arroba_cab,
               r.preco_unitario, r.unidade_preco, r.valor_total_brl, r.participacao_pct, r.moeda_referencia, r.pagina_pdf,
               f.titulo AS fonte_titulo, f.ano_publicacao AS fonte_ano
        FROM receita_venda_referencia r
        JOIN regiao g USING (regiao_codigo)
        JOIN fonte f ON f.fonte_codigo = r.fonte_codigo
        ORDER BY r.fonte_codigo, r.localizacao, r.id_receita
    """)
