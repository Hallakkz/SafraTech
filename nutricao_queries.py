"""Consultas ao nutricao_database (somente leitura, parametrizadas)."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from database.connections import consultar

BANCO = "nutricao"
CULTURAS = ["Soja", "Milho", "Algodão", "Gergelim"]
GERAL = "Geral (não específico de cultura)"


def faixas_suficiencia(cultura: str) -> pd.DataFrame:
    """Faixas foliares SOMENTE da cultura informada (nunca de outra cultura)."""
    return consultar(BANCO, """SELECT registro_id, cultura, nutriente_codigo, valor_min, valor_max, operador_min, operador_max,
                                      unidade, unidade_base, classificacao, estagio, parte_planta, metodo, regiao, condicoes,
                                      observacoes, divergencia_ids, fonte_id, secao, pagina_pdf, pagina_impressa, tipo_dado,
                                      fonte_titulo, fonte_autores, fonte_instituicao, fonte_ano, referencia_abnt
                               FROM nutricao.v_registro_com_fonte
                               WHERE categoria = 'faixa_suficiencia' AND cultura = :cultura
                               ORDER BY nutriente_codigo, fonte_id, secao""", {"cultura": cultura})


def registros_complementares(cultura: str) -> pd.DataFrame:
    """Teores de referência aproximados, relações (N:S) e ausências registradas para a cultura."""
    return consultar(BANCO, """SELECT registro_id, categoria, nutriente, nutriente_codigo, valor, valor_min, valor_max, unidade,
                                      classificacao, estagio, parte_planta, texto, condicoes, fonte_id, secao, pagina_impressa,
                                      referencia_abnt
                               FROM nutricao.v_registro_com_fonte
                               WHERE cultura = :cultura AND categoria IN ('teor_foliar_referencia', 'relacao_nutrientes', 'ausencia_dado', 'teor_otimo')
                               ORDER BY categoria, nutriente_codigo""", {"cultura": cultura})


def cobertura(cultura: str) -> pd.DataFrame:
    return consultar(BANCO, """SELECT cultura, nutriente_codigo, tipo_informacao, descricao, disponivel, n_registros, nota
                               FROM nutricao.cobertura_cultura_nutriente WHERE cultura = :cultura
                               ORDER BY tipo_informacao, nutriente_codigo""", {"cultura": cultura})


def amostragem_foliar(cultura: str) -> pd.DataFrame:
    return consultar(BANCO, """SELECT registro_id, cultura, estagio, parte_planta, valor, unidade, texto, divergencia_ids,
                                      fonte_id, secao, pagina_impressa, referencia_abnt
                               FROM nutricao.v_registro_com_fonte
                               WHERE categoria = 'amostragem_foliar' AND cultura = :cultura
                               ORDER BY fonte_id, secao""", {"cultura": cultura})


def sintomas(cultura: str) -> pd.DataFrame:
    """Sintomas da cultura + sintomas gerais (rotulados como não específicos da cultura)."""
    return consultar(BANCO, """SELECT registro_id, cultura, nutriente, nutriente_codigo, classificacao, parte_planta, texto, causas,
                                      condicoes, fonte_id, secao, pagina_impressa, referencia_abnt, fonte_titulo, fonte_ano
                               FROM nutricao.v_registro_com_fonte
                               WHERE categoria = 'sintoma' AND cultura = ANY(:culturas)
                               ORDER BY (cultura = :cultura) DESC, nutriente""", {"culturas": [cultura, GERAL], "cultura": cultura})


def divergencias(registro_ids: Iterable[str]) -> pd.DataFrame:
    ids = list(registro_ids)
    if not ids:
        return pd.DataFrame(columns=["divergencia_id", "registro_id", "parametro", "descricao", "fontes", "tratamento", "tipo"])
    return consultar(BANCO, """SELECT d.divergencia_id, rd.registro_id, d.parametro, d.descricao, d.fontes, d.tratamento, d.tipo
                               FROM nutricao.registro_divergencia rd JOIN meta.divergencia d USING (divergencia_id)
                               WHERE rd.registro_id = ANY(:ids) ORDER BY d.divergencia_id""", {"ids": ids})


def nutrientes() -> pd.DataFrame:
    return consultar(BANCO, "SELECT nutriente_codigo, nome, classe FROM nutricao.nutriente ORDER BY classe, nutriente_codigo")
