"""Integração do EduAgro com os bancos do SafraTech (recuperação de conhecimento) e com a Biblioteca."""
import pytest

from database.connections import BancoIndisponivel
from modules.eduagro_ai import knowledge_retrieval as kr


@pytest.fixture
def base(bancos):
    kr.invalidar_bancos()
    yield kr.carregar_base_bancos(forcar=True)
    kr.invalidar_bancos()


def test_base_carrega_os_seis_bancos(base):
    assert set(base.disponiveis) == {"solo_database", "nutricao_database", "plantio_database", "pecuaria_compra_database",
                                     "pecuaria_desempenho_database", "pecuaria_rentabilidade_database"}
    assert not base.indisponiveis and len(base.indice) > 2000
    chaves = [r.chave for r in base.indice.itens]
    assert len(chaves) == len(set(chaves)), "registros duplicados entre os bancos de pecuária"


def _titulos(res):
    return [(r.tipo, r.titulo, ",".join(r.bancos)) for r in res.referencias]


def test_fosforo_na_analise_de_solo_traz_faixas_do_banco_de_solo(base):
    res = kr.buscar("Como interpretar o fósforo na análise de solo?", usar_biblioteca=False)
    tabelas = [r for r in res.referencias if r.tipo == "Tabela de interpretação" and r.titulo == "Fósforo (P)"]
    assert tabelas, _titulos(res)
    t = tabelas[0]
    assert t.bancos == ["solo_database"] and "Muito baixo" in t.texto and "Adequado" in t.texto and "mg/dm3" in t.texto
    assert t.fonte == "Cerrado: correção do solo e adubação" and t.pagina and len(t.registros) >= 5
    assert "Condições de aplicação" in t.texto or "Método" in t.texto


def test_gmd_traz_a_formula_do_banco_de_desempenho(base):
    res = kr.buscar("Como calcular o ganho médio diário de um bovino?", usar_biblioteca=False)
    primeira = res.referencias[0]
    assert primeira.tipo == "Fórmula de cálculo" and "GMD" in primeira.titulo
    assert "pecuaria_desempenho_database" in primeira.bancos
    assert "(peso_final_kg - peso_inicial_kg) / dias" in primeira.texto and primeira.pagina == "23"


def test_rentabilidade_traz_referencias_economicas(base):
    res = kr.buscar("Como calcular a rentabilidade de um lote de gado?", usar_biblioteca=False)
    titulos = " ".join(r.titulo for r in res.referencias)
    assert "Lucro" in titulos and "Margem" in titulos
    assert any(b.startswith("pecuaria_") for r in res.referencias for b in r.bancos)


def test_rendimento_de_carcaca_e_zarc(base):
    res = kr.buscar("Como funciona o rendimento de carcaça?", usar_biblioteca=False)
    assert any("RENDIMENTO_CARCACA" in r.registros for r in res.referencias)
    res = kr.buscar("O que é o Zoneamento Agrícola de Risco Climático?", usar_biblioteca=False)
    assert res.referencias[0].bancos == ["plantio_database"] and "ZARC" in res.referencias[0].titulo


def test_deficiencia_e_toxidez_vem_do_banco_nutricional(base):
    res = kr.buscar("Qual a diferença entre deficiência e toxicidade nutricional?", usar_biblioteca=False)
    assert any(r.bancos == ["nutricao_database"] and r.tipo == "Sintoma visual" for r in res.referencias)


def test_pergunta_fora_do_tema_nao_traz_referencias(base):
    assert kr.buscar("Qual a cotação do bitcoin hoje?", usar_biblioteca=False).vazio
    assert kr.buscar("", usar_biblioteca=False).vazio


def test_filtro_por_area(base):
    res = kr.buscar("rendimento", area="agricultura", usar_biblioteca=False)
    assert all(r.area == "agricultura" for r in res.referencias)
    res = kr.buscar("rendimento de carcaça", area="pecuaria", usar_biblioteca=False)
    assert res.referencias and all(r.area == "pecuaria" for r in res.referencias)


def test_contexto_para_a_ia_tem_rotulos_fonte_e_pagina(base):
    res = kr.buscar("Como calcular o ganho médio diário?", usar_biblioteca=False)
    ctx = kr.formatar_contexto(res)
    assert ctx.startswith("[S1] Fórmula de cálculo") and "Fonte: " in ctx and "p. 23" in ctx and "registro(s): GMD" in ctx
    assert "NENHUMA referência" in kr.formatar_contexto(kr.buscar("bitcoin", usar_biblioteca=False))


def test_banco_indisponivel_e_informado_sem_derrubar_a_busca(bancos):
    import psql_executor

    def executor(chave, sql, params):
        if chave == "solo":
            raise BancoIndisponivel("conexão recusada")
        return psql_executor.executar(chave, sql, params)
    bancos.definir_executor_externo(executor)
    kr.invalidar_bancos()
    res = kr.buscar("Como calcular o ganho médio diário?", usar_biblioteca=False)
    assert "solo_database" in res.bancos_indisponiveis and res.referencias
    assert "solo_database" not in res.bancos_consultados
    kr.invalidar_bancos()


def test_normalizacao_portugues():
    assert kr.tokenizar("Fósforo") == kr.tokenizar("fosforo")
    assert kr.tokenizar("interpretação") == kr.tokenizar("interpretações")
    assert "fosfor" in kr.tokenizar_consulta("teor de P no solo")
    assert {"ganh", "medi", "diari"} <= set(kr.tokenizar_consulta("GMD"))
