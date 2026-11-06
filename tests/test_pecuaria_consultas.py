"""Consultas reais aos três bancos de pecuária: dados técnicos, fontes bibliográficas, preços históricos e regras."""
import pytest

from database import pecuaria_queries as pq


def test_os_tres_bancos_conectam_individualmente(bancos):
    for chave in pq.BANCOS_PECUARIA:
        s = bancos.verificar(chave)
        assert s.disponivel and bancos.BANCOS[chave]["nome"] in s.mensagem


@pytest.mark.parametrize("banco", pq.BANCOS_PECUARIA)
def test_genotipos_nelore_e_cruzados_separados(bancos, banco):
    cods = set(pq.racas(banco)["raca_codigo"])
    assert {"NELORE_PO", "NELORE_COMERCIAL", "NELORADO", "F1_PARDO_SUICO_X_NELORE", "ANGUS_X_NELORE"} <= cods
    assert "NAO_APLICAVEL" not in cods


@pytest.mark.parametrize("banco", pq.BANCOS_PECUARIA)
def test_referencias_de_rendimento_rastreaveis(bancos, banco):
    df = pq.referencias_rendimento(banco)
    assert not df.empty
    for r in df.to_dict("records"):
        assert r["fonte_codigo"] and r["fonte_titulo"] and r["fonte_instituicao"]
        assert (r["pagina_pdf"] == r["pagina_pdf"] and r["pagina_pdf"] is not None) or r["localizacao"]
        v, a, b = r["valor_numerico"], r["valor_min"], r["valor_max"]
        vals = [x for x in (v, a, b) if x is not None and x == x]
        assert vals and all(30 <= float(x) <= 75 for x in vals)       # rendimento em % do peso vivo, nunca fixo


def test_rendimentos_diferentes_entre_racas_e_sexos(bancos):
    df = pq.referencias_rendimento(pq.COMPRA)
    nelorado = df[df["raca_codigo"] == "NELORADO"]
    assert set(nelorado[nelorado["sexo"] == "macho"]["valor_numerico"]) == {53.0}
    assert set(nelorado[nelorado["sexo"] == "femea"]["valor_numerico"]) == {50.0}


def test_referencias_de_gmd_e_peso_com_fonte(bancos):
    gmd = pq.referencias_gmd(pq.DESEMPENHO)
    peso = pq.referencias_peso(pq.DESEMPENHO)
    assert len(gmd) == 65 and set(peso["unidade_padrao"]) == {"kg_pv"}
    for df in (gmd, peso):
        assert df["fonte_codigo"].notna().all() and df["tipo_dado"].notna().all()


@pytest.mark.parametrize("banco", [pq.COMPRA, pq.RENTABILIDADE])
def test_precos_da_arroba_sao_historicos_com_data_e_natureza(bancos, banco):
    df = pq.precos_arroba_historicos(banco)
    assert not df.empty
    assert set(df["natureza"]) == {"historico_publicacao"}
    assert df["data_referencia"].notna().all()
    assert all("NÃO usar como cotação atual" in u for u in df["uso_permitido"])


def test_fontes_bibliograficas_completas(bancos):
    df = pq.fontes(pq.COMPRA, ["F06_COT93_MS", "F07_RENDIMENTO_CARCACA", "F01_500P_GADO_CORTE"])
    assert len(df) == 3
    f06 = df.set_index("fonte_codigo").loc["F06_COT93_MS"]
    assert f06["instituicao"] == "Embrapa Gado de Corte" and int(f06["ano_publicacao"]) == 2005
    assert "Comunicado Técnico" in f06["referencia_abnt"]
    f07 = df.set_index("fonte_codigo").loc["F07_RENDIMENTO_CARCACA"]
    assert f07["ano_publicacao"] != f07["ano_publicacao"] or f07["ano_publicacao"] is None   # ano não identificado: não inventado


def test_formula_de_arrobas_usa_rendimento_e_15_kg(bancos):
    df = pq.formulas(pq.COMPRA, ["ARROBAS_CARCACA_DE_PESO_VIVO"])
    exp = df.iloc[0]["expressao"]
    assert "rendimento_pct" in exp and "/ 15" in exp


def test_divergencia_de_rendimento_registrada(bancos):
    df = pq.divergencias(pq.COMPRA, ["PAR-F06-0094"])
    assert "DIV-07" in set(df["divergencia_codigo"])


def test_perguntas_e_respostas_com_fonte_e_pagina(bancos):
    df = pq.perguntas_relacionadas(pq.DESEMPENHO, "nelore", ["ganho_peso", "raca_genetica"])
    assert not df.empty and df["fonte_titulo"].notna().all() and df["numero_pergunta"].notna().all()


def test_tabelas_de_entrada_vazias_sem_dados_ficticios(bancos):
    assert pq.custos_referencia(pq.COMPRA)["fonte_codigo"].notna().all()
    for banco, tabela in ((pq.COMPRA, "lote_compra"), (pq.DESEMPENHO, "lote_rebanho"), (pq.RENTABILIDADE, "cenario_venda")):
        n = bancos.consultar(banco, f"SELECT count(*) AS n FROM {tabela}").iloc[0]["n"]
        assert int(n) == 0, tabela
