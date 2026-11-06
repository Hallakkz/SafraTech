"""Diagnóstico do Solo contra o solo_database real."""
import pytest

from core import solo_engine as se
from core.classificacao import ABAIXO, ADEQUADO, DIVERGENTE, INSUFICIENTE, atende
from core.solo_regras import Contexto, avaliar
from core.unidades import converter_solo, fatores_do_banco


@pytest.fixture
def ambiente(bancos):
    from database import solo_queries as sq
    cache = {}

    def preparar(cultura):
        if cultura not in cache:
            culturas = se.culturas_aplicaveis(cultura, sq.culturas_disponiveis()["cultura"].tolist())
            refs = sq.faixas_interpretacao(se.parametros_consulta(), culturas)
            cache[cultura] = (culturas, refs)
        return cache[cultura]

    return sq, preparar, fatores_do_banco(sq.conversoes_unidade())


def _rodar(ambiente, cultura="Soja", **kw):
    sq, preparar, fatores = ambiente
    culturas, refs = preparar(cultura)
    e = se.EntradaSolo(cultura=cultura, **kw)
    return {l.chave: l for l in se.executar(e, refs, fatores, culturas)}, refs


def test_consulta_filtrada_por_parametro_e_cultura(ambiente):
    sq, preparar, _ = ambiente
    culturas, refs = preparar("Soja")
    assert set(refs["cultura"]) <= set(culturas)
    assert set(refs["categoria"]) <= {"faixa_interpretacao", "nivel_critico"}
    assert "Milho" not in set(refs["cultura"]) and "Algodão" not in set(refs["cultura"])
    assert len(refs) < 400  # nunca a tabela inteira


def test_culturas_aplicaveis_inclui_registros_compostos(ambiente):
    sq, _, _ = ambiente
    disp = sq.culturas_disponiveis()["cultura"].tolist()
    assert "Soja ou feijão" in se.culturas_aplicaveis("Soja", disp)
    assert "Soja ou feijão" not in se.culturas_aplicaveis("Milho", disp)
    assert "Soja; Milho; Trigo; Feijão (sequeiro)" in se.culturas_aplicaveis("Milho", disp)
    assert "Soja" not in se.culturas_aplicaveis("Gergelim", disp)


def test_ph_agua_adequado_com_limites_do_banco(ambiente):
    r, refs = _rodar(ambiente, bioma_cerrado="sim", metodos={"ph": "ph_agua"}, valores={"ph": (5.8, "—")})
    res = r["ph"].resultado
    assert res.status == ADEQUADO
    for g in res.grupos:
        reg = g.registro_casado
        assert reg["registro_id"] in set(refs["registro_id"])            # limite vem do banco
        assert atende(5.8, reg["valor_min"], reg["operador_min"], reg["valor_max"], reg["operador_max"])
        assert "água" in reg["metodo"].lower()                            # nunca outro método


def test_ph_sem_metodo_dados_insuficientes(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", valores={"ph": (5.8, "—")})
    assert r["ph"].resultado.status == INSUFICIENTE
    assert any("método" in l for l in r["ph"].resultado.limitacoes)


def test_ph_cacl2_nao_usa_faixa_de_agua(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"ph": "ph_cacl2"}, valores={"ph": (5.0, "—")})
    for g in r["ph"].resultado.grupos:
        assert "cacl2" in g.registro_casado["metodo"].lower()


def test_fosforo_respeita_argila_e_sistema(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", sistema="sequeiro", argila=40, textura="Textura argilosa",
                  metodos={"p": "p_mehlich"}, valores={"p": (3.0, "mg/dm³")})
    res = r["p"].resultado
    assert res.status == ABAIXO
    for g in res.grupos:
        reg = g.registros[0]
        assert "irrigad" not in (reg.get("condicoes") or "").lower() or "sequeiro" in (reg.get("condicoes") or "").lower()
        assert reg["tipo_solo"] in ("Argila 36 a 60 %", "Textura argilosa")


def test_fosforo_sem_argila_informa_limitacao(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", sistema="sequeiro", metodos={"p": "p_mehlich"}, valores={"p": (3.0, "mg/dm³")})
    res = r["p"].resultado
    assert res.status == INSUFICIENTE
    assert any("argila" in l or "textural" in l for l in res.limitacoes)


def test_nitrogenio_sempre_dados_insuficientes(ambiente):
    r, _ = _rodar(ambiente, valores={"n": (20.0, "mg/dm³")})
    assert r["n"].resultado.status == INSUFICIENTE
    assert "não há faixa" in r["n"].resultado.limitacoes[0]


def test_unidades_equivalentes_dao_mesmo_resultado(ambiente):
    a, _ = _rodar(ambiente, bioma_cerrado="sim", textura="Textura argilosa",
                  valores={"ca": (3.0, "cmolc/dm³"), "mg": (1.0, "cmolc/dm³"), "mo": (3.0, "%"), "ctc": (8.0, "cmolc/dm³")})
    b, _ = _rodar(ambiente, bioma_cerrado="sim", textura="Textura argilosa",
                  valores={"ca": (30.0, "mmolc/dm³"), "mg": (10.0, "mmolc/dm³"), "mo": (30.0, "g/kg"), "ctc": (80.0, "mmolc/dm³")})
    for k in ("ca", "mg", "mo", "ctc"):
        assert a[k].resultado.status == b[k].resultado.status
        assert a[k].valor_comparado == pytest.approx(b[k].valor_comparado)
    assert "÷ 10" in b["ca"].conversao


def test_conversao_k_e_mo_usa_fatores_cadastrados(ambiente):
    _, _, f = ambiente
    assert f.k_mg_para_cmolc == pytest.approx(0.00256) and "SOL-000220" in f.origem_k
    assert f.c_para_mo == pytest.approx(1.724) and "SOL-000221" in f.origem_mo
    c = converter_solo("k", 0.1536, "cmolc/dm³", f)
    assert c.valor == pytest.approx(60.0) and c.unidade_base == "mg/dm3"
    c = converter_solo("mo", 2.0, "C orgânico (%)", f)
    assert c.valor == pytest.approx(3.448)


def test_k_em_mg_kg_usa_somente_referencia_em_mg_kg(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"k": "k_mehlich"}, valores={"k": (60.0, "mg/kg")}, argila=40)
    for g in r["k"].resultado.grupos:
        assert g.registros[0]["unidade_base"] == "mg/kg"


def test_relacoes_calculadas_sao_rotuladas(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"k": "k_mehlich"},
                  valores={"ca": (3.0, "cmolc/dm³"), "mg": (1.0, "cmolc/dm³"), "k": (60.0, "mg/dm³"), "ctc": (8.0, "cmolc/dm³")})
    assert r["ca_mg"].calculado and r["ca_mg"].valor_comparado == pytest.approx(3.0)
    assert r["k_ctc"].valor_comparado == pytest.approx(100 * 60 * 0.00256 / 8)


def test_fora_do_cerrado_exclui_referencias_regionais(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="nao", valores={"ca": (3.0, "cmolc/dm³")})
    for g in r["ca"].resultado.grupos:
        assert g.registros[0]["regiao"] != "Cerrado"
    assert any(i.get("regiao") == "Cerrado" for i in r["ca"].resultado.informativos)


def test_micronutriente_dtpa_nao_usa_mehlich(ambiente):
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"zn": "micro_dtpa"}, valores={"zn": (1.2, "mg/dm³")})
    for g in r["zn"].resultado.grupos:
        assert g.registros[0]["metodo"].startswith("DTPA")
    assert any("Estado de São Paulo" in l for l in r["zn"].resultado.limitacoes)


def test_divergencia_entre_referencias_sinalizada(ambiente):
    # pH em CaCl2 5,0: Anexo 6 (Adequado 4,9–5,5) x outra referência com faixa 5,5–6,5
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"ph": "ph_cacl2"}, valores={"ph": (5.0, "—")})
    assert r["ph"].resultado.status == DIVERGENTE
    assert len({g.status for g in r["ph"].resultado.grupos}) > 1


def test_divergencias_do_banco_consultadas(ambiente):
    sq, _, _ = ambiente
    r, _ = _rodar(ambiente, bioma_cerrado="sim", metodos={"ph": "ph_agua", "p": "p_mehlich"}, sistema="sequeiro", argila=40,
                  valores={"ph": (5.8, "—"), "p": (8.0, "mg/dm³"), "ca": (3.0, "cmolc/dm³"), "mg": (1.0, "cmolc/dm³")})
    ids = se.registros_usados(list(r.values()))
    div = sq.divergencias(ids)
    assert set(div.columns) >= {"divergencia_id", "registro_id", "descricao"}
    assert set(div["registro_id"]) <= set(ids)
    assert "DIV-SOL-CAMG" in set(div["divergencia_id"])      # relação Ca/Mg calculada usa registros com divergência
    vazio = sq.divergencias(["SOL-INEXISTENTE"])
    assert vazio.empty and "divergencia_id" in vazio.columns


def test_avaliar_valor_nao_informado():
    import pandas as pd
    assert avaliar("ph", None, pd.DataFrame(), Contexto(culturas=["Soja"])).status == INSUFICIENTE
