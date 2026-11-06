"""Diagnóstico Nutricional contra o nutricao_database real (4 culturas)."""
import pytest

from core import nutricao_engine as ne
from core.classificacao import ABAIXO, ADEQUADO, DIVERGENTE, INSUFICIENTE
from core.unidades import converter_foliar

CULTURAS = ["Soja", "Milho", "Algodão", "Gergelim"]


@pytest.fixture
def nq(bancos):
    from database import nutricao_queries
    return nutricao_queries


@pytest.mark.parametrize("cultura", CULTURAS)
def test_faixas_somente_da_cultura(nq, cultura):
    f = nq.faixas_suficiencia(cultura)
    assert f.empty or set(f["cultura"]) == {cultura}
    s = nq.sintomas(cultura)
    assert set(s["cultura"]) <= {cultura, nq.GERAL}


@pytest.mark.parametrize("cultura,estagio", [("Soja", "No florescimento"),
                                             ("Milho", "Aparecimento da inflorescência feminina ('cabelo')"),
                                             ("Algodão", "Início do florescimento")])
def test_protocolo_e_faixas_compativeis(nq, cultura, estagio):
    f = nq.faixas_suficiencia(cultura)
    assert ne.estagios_protocolo(f) == [estagio]
    compat, avisos = ne.faixas_compativeis(f, estagio)
    assert compat and all(r["cultura"] == cultura for r in compat)
    assert {r["estagio"] for r in compat} <= {estagio, "Conforme Cap. 10, Tabela 1", "Não especificado"}


def test_gergelim_sem_referencia_mensagem_exata(nq):
    f = nq.faixas_suficiencia("Gergelim")
    assert f.empty and ne.estagios_protocolo(f) == []
    compat, _ = ne.faixas_compativeis(f, ne.OUTRO_ESTAGIO)
    r = ne.avaliar_foliar({"N": 30.0}, {"N": "g/kg"}, compat)
    assert r[0].status == INSUFICIENTE
    assert r[0].mensagem == "Não há dados de referência disponíveis no banco para esta combinação."
    aus = ne.ausencias_registradas(nq.registros_complementares("Gergelim"), nq.cobertura("Gergelim"))
    assert any("faixa_suficiencia" in a["texto"] for a in aus)


def test_estagio_fora_do_protocolo_nao_usa_faixas(nq):
    compat, _ = ne.faixas_compativeis(nq.faixas_suficiencia("Soja"), ne.OUTRO_ESTAGIO)
    assert compat == []
    r = ne.avaliar_foliar({"K": 20.0}, {"K": "g/kg"}, compat)
    assert r[0].mensagem == ne.SEM_DADOS


def test_soja_classificacao_e_divergencia(nq):
    compat, avisos = ne.faixas_compativeis(nq.faixas_suficiencia("Soja"), "No florescimento")
    r = {x.nutriente: x for x in ne.avaliar_foliar({"N": 40.0, "K": 20.0, "P": 2.0}, {"N": "g/kg", "K": "g/kg", "P": "g/kg"}, compat)}
    assert r["K"].status == ADEQUADO
    assert r["P"].status == ABAIXO
    assert r["N"].status == DIVERGENTE        # Cerrado 45–55 x EMB_FOLIAR_2005 31,6–47,2
    assert {a["registro"]["fonte_id"] for a in r["N"].avaliacoes} == {"EMB_CERRADO_2004", "EMB_FOLIAR_2005"}
    assert any("não especifica o estádio" in a for a in avisos)


def test_unidade_percentual_convertida(nq):
    v, ub, nota = converter_foliar("K", 2.0, "%")
    assert (v, ub) == (20.0, "g/kg") and "× 10" in nota
    assert converter_foliar("Zn", 30, "ppm")[:2] == (30, "mg/kg")
    assert converter_foliar("Zn", 0.03, "g/kg")[0] == pytest.approx(30)


def test_algodao_mo_ausencia_e_referencia(nq):
    compat, _ = ne.faixas_compativeis(nq.faixas_suficiencia("Algodão"), "Início do florescimento")
    r = ne.avaliar_foliar({"Mo": 1.5}, {"Mo": "mg/kg"}, compat)[0]
    assert r.status == ADEQUADO and all(a["registro"]["secao"] == "Cap. 8, Tabela 9" for a in r.avaliacoes)
    aus = ne.ausencias_registradas(nq.registros_complementares("Algodão"), nq.cobertura("Algodão"))
    assert any(a["nutriente"] == "Mo" and "'-'" in a["texto"] for a in aus)


@pytest.mark.parametrize("cultura", ["Soja", "Milho", "Algodão"])
def test_milho_algodao_soja_nao_misturam_registros(nq, cultura):
    f = nq.faixas_suficiencia(cultura)
    compat, _ = ne.faixas_compativeis(f, ne.estagios_protocolo(f)[0])
    res = ne.avaliar_foliar({n: 10.0 for n in ne.NUTRIENTES_FOLIARES},
                            {n: "g/kg" if n in {"N", "P", "K", "Ca", "Mg", "S"} else "mg/kg" for n in ne.NUTRIENTES_FOLIARES}, compat)
    for x in res:
        for a in x.avaliacoes:
            assert a["registro"]["cultura"] == cultura


def test_sintomas_priorizam_cultura_e_nao_sao_definitivos(nq):
    s = ne.associar_sintomas(nq.sintomas("Algodão"), ["clorose_internerval"], "Algodão")
    assert s and s[0]["especifico"]
    assert all("clorose_internerval" in x["coincidencias"] for x in s)
    nomes = [x["cultura"] for x in s]
    assert nomes == sorted(nomes, key=lambda c: c != "Algodão")
    assert ne.associar_sintomas(nq.sintomas("Soja"), [], "Soja") == []


def test_divergencias_registradas(nq):
    compat, _ = ne.faixas_compativeis(nq.faixas_suficiencia("Soja"), "No florescimento")
    ids = [r["registro_id"] for r in compat if r.get("divergencia_ids")]
    div = nq.divergencias(ids)
    assert "DIV-NUT-FOLIAR-SOJA-N" in set(div["divergencia_id"])
