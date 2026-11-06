"""ZARC (plantio_database) e simulação complementar."""
import pytest

from core import simulacao, zarc

RIO_VERDE = "5218805"
SOJA = "12016720000011"


@pytest.fixture
def pq(bancos):
    from database import plantio_queries
    return plantio_queries


def test_municipios_e_culturas(pq):
    mun = pq.municipios("GO")
    assert "Rio Verde" in set(mun["municipio"]) and mun["municipio"].notna().all()
    cult = pq.culturas_do_municipio(RIO_VERDE)
    assert SOJA in set(cult["cod_cultura"])


def test_combinacao_municipio_cultura_safra_solo_ciclo(pq):
    ind = pq.indicacoes(RIO_VERDE, SOJA, 2026, "11", "20", "1")
    assert len(ind) == 1
    row = ind.iloc[0].to_dict()
    assert row["geocodigo"] if "geocodigo" in row else True
    assert row["grupo_solo"] == "AD1" and row["grupo_cultivar"] == "Grupo I" and row["manejo"] == "Sequeiro"
    assert row["portaria_numero"] and row["portaria_data"]
    riscos = zarc.riscos_da_linha(row)
    assert len(riscos) == 36 and set(riscos) <= {0, 20, 30, 40}


def test_unpivot_igual_a_visao_oficial(pq):
    """Os decêndios lidos das colunas dec1..dec36 coincidem com a visão v_zarc_risco do banco."""
    ind = pq.indicacoes(RIO_VERDE, SOJA, 2026, "11", "20", "1")
    row = ind.iloc[0].to_dict()
    from database.connections import consultar
    v = consultar("plantio", "SELECT decendio, nivel_risco_pct FROM plantio.v_zarc_risco WHERE indicacao_id = :i ORDER BY decendio",
                  {"i": int(row["indicacao_id"])})
    nosso = {d: r for d, r in enumerate(zarc.riscos_da_linha(row), start=1) if r}
    assert nosso == dict(zip(v["decendio"].astype(int), v["nivel_risco_pct"].astype(int)))


def test_niveis_de_manejo_mostrados_separadamente(pq):
    ind = pq.indicacoes("4100103", SOJA, 2026, "11", "20", "1")
    assert len(ind) == 4 and sorted(ind["cod_nm"].astype(str)) == ["1", "2", "3", "4"]
    longo = zarc.tabela_longa(ind)
    assert longo["linha"].nunique() == 4 and len(longo) == 4 * 36


def test_combinacao_inexistente_retorna_vazio(pq):
    assert pq.indicacoes(RIO_VERDE, SOJA, 2026, "3", "20", "1").empty      # Argiloso não existe para soja (usa AD)
    assert pq.indicacoes(RIO_VERDE, SOJA, 2030, "11", "20", "1").empty     # safra inexistente
    assert pq.culturas_do_municipio("0000000").empty


def test_zero_e_sem_indicacao_nao_risco_zero():
    riscos = [0] * 36
    riscos[27:33] = [20] * 6
    a = zarc.avaliar_periodo(riscos, zarc.periodo(1, 3))
    assert a.situacao == zarc.SEM_INDICACAO_PERIODO and a.melhor_risco is None
    b = zarc.avaliar_periodo(riscos, zarc.periodo(27, 30))
    assert b.situacao == zarc.INDICADO_PARCIAL and b.riscos_no_periodo[27] == 0
    c = zarc.avaliar_periodo(riscos, zarc.periodo(28, 33))
    assert c.situacao == zarc.INDICADO_TODO and c.melhor_risco == 20


def test_periodo_com_virada_de_ano_e_janelas():
    assert zarc.periodo(35, 2) == [35, 36, 1, 2]
    riscos = [20, 30] + [0] * 31 + [40, 20, 20]
    j = zarc.janelas(riscos)
    assert {"inicio": 35, "fim": 1, "risco": 20, "decendios": [35, 36, 1]} in j
    with pytest.raises(ValueError):
        zarc.periodo(0, 37)


def test_dominio_e_decendio_sem_datas(pq):
    d = pq.decendios()
    assert len(d) == 36 and d["observacao"].str.contains("Datas não convertidas").all()
    dom = pq.dominio("dec1..dec36")
    assert "Sem indicação" in dom.loc[dom["codigo"].astype(str) == "0", "rotulo"].iloc[0]


def test_simulacao_soja_compara_com_referencias(pq):
    exig = pq.exigencias("Soja")
    s = simulacao.simular(exig, temp_ar=18.0, temp_solo=22.0, chuva_ciclo=500.0)
    por_reg = {i.registro["registro_id"]: i for i in s["itens"]}
    assert por_reg["PLA-000074"].leitura == "desfavoravel"     # 20–30 °C adequada para semeadura
    assert por_reg["PLA-000076"].leitura == "neutra"           # solo < 20 °C limitante: não se enquadra
    assert por_reg["PLA-000071"].leitura == "favoravel"        # 450–800 mm/ciclo
    assert all(i.registro["unidade"] != "mm/dia" for i in s["itens"] if i.variavel == "chuva_ciclo")
    s2 = simulacao.simular(exig, temp_ar=25.0)
    assert {i.registro["registro_id"]: i.leitura for i in s2["itens"]}["PLA-000074"] == "favoravel"


def test_simulacao_sem_entradas_e_sem_referencia(pq):
    assert simulacao.simular(pq.exigencias("Soja"))["itens"] == []
    s = simulacao.simular(pq.exigencias("Algodão"), temp_ar=25.0)
    assert "temperatura_ar" in s["sem_referencia"]               # não há limite numérico de semeadura para algodão
