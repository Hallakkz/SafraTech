"""
Consultas (somente leitura, parametrizadas) usadas pelo EduAgro AI para montar a base de conhecimento do tutor.

O EduAgro não cria tabelas nem grava nada nos seis bancos do SafraTech: apenas lê os registros técnicos
(com fonte e página) que os módulos de Agricultura e Pecuária já utilizam.

Agricultura (esquemas solo, nutricao, plantio — visão v_registro_com_fonte, idêntica nos três bancos):
    registros curados com parâmetro, cultura, região, faixa/valor, classificação, texto, fonte e página.
Pecuária (esquema public dos três bancos):
    parametro_tecnico, formula_calculo e pergunta_resposta, sempre com a tabela fonte.
"""
from __future__ import annotations

import pandas as pd

from database.connections import consultar

BANCOS_AGRICOLAS = {"solo": "solo", "nutricao": "nutricao", "plantio": "plantio"}
BANCOS_PECUARIOS = ("pecuaria_compra", "pecuaria_desempenho", "pecuaria_rentabilidade")

# Categorias que não ajudam o ensino (marcadores internos de curadoria)
CATEGORIAS_IGNORADAS = ("ilustracao",)


def registros_agricolas(chave: str) -> pd.DataFrame:
    """Registros técnicos de solo_database, nutricao_database ou plantio_database (o esquema tem o nome do banco)."""
    esquema = BANCOS_AGRICOLAS[chave]
    return consultar(chave, f"""
        SELECT registro_id, categoria, parametro, nutriente, cultura, regiao, tipo_solo, camada, estagio, parte_planta,
               metodo, valor, valor_min, valor_max, operador_min, operador_max, unidade, classificacao, texto,
               condicoes, causas, observacoes, fonte_id, secao, pagina_pdf, pagina_impressa, tipo_dado,
               fonte_titulo, fonte_instituicao, fonte_ano
        FROM {esquema}.v_registro_com_fonte
        WHERE categoria <> ALL(:ignoradas)
        ORDER BY registro_id
    """, {"ignoradas": list(CATEGORIAS_IGNORADAS)})


def parametros_pecuarios(chave: str) -> pd.DataFrame:
    return consultar(chave, """
        SELECT p.id_registro, p.categoria, p.tema, p.parametro, r.nome AS raca, p.sexo, p.idade_fase, p.fase,
               s.nome AS sistema, p.valor_texto_original, p.valor_numerico, p.valor_min, p.valor_max, p.unidade_padrao,
               p.condicoes_aplicacao, p.descricao_tecnica, p.tipo_dado, p.periodo_referencia, p.fonte_codigo,
               p.pagina_pdf, p.pagina_impressa, p.localizacao, p.status_validacao,
               f.titulo AS fonte_titulo, f.instituicao AS fonte_instituicao, f.ano_publicacao AS fonte_ano
        FROM parametro_tecnico p
        JOIN fonte f USING (fonte_codigo)
        LEFT JOIN raca_genotipo r ON r.raca_codigo = p.raca_codigo
        LEFT JOIN sistema_criacao s ON s.sistema_codigo = p.sistema_codigo
        ORDER BY p.id_registro
    """)


def formulas_pecuarias(chave: str) -> pd.DataFrame:
    return consultar(chave, """
        SELECT fc.formula_codigo, fc.nome, fc.expressao, fc.variaveis, fc.unidade_resultado, fc.fonte_codigo,
               fc.pagina_pdf, fc.observacoes, f.titulo AS fonte_titulo, f.instituicao AS fonte_instituicao,
               f.ano_publicacao AS fonte_ano
        FROM formula_calculo fc
        JOIN fonte f USING (fonte_codigo)
        ORDER BY fc.formula_codigo
    """)


def perguntas_pecuarias(chave: str) -> pd.DataFrame:
    return consultar(chave, """
        SELECT q.id_pergunta, q.fonte_codigo, q.capitulo_titulo, q.numero_pergunta, q.pergunta, q.resposta,
               q.pagina_pdf_inicio, q.pagina_impressa_inicio, q.localizacao, q.temas, q.possui_conteudo_nao_transcrito,
               f.titulo AS fonte_titulo, f.instituicao AS fonte_instituicao, f.ano_publicacao AS fonte_ano
        FROM pergunta_resposta q
        JOIN fonte f USING (fonte_codigo)
        ORDER BY q.id_pergunta
    """)
