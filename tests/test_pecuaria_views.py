"""Equivalência entre os cálculos do app (modules/pecuaria/calculos.py) e as views de cálculo dos bancos.

O app abre sessões somente leitura e não grava os dados do produtor. Para provar que as fórmulas são as mesmas das
views, cada teste insere um caso dentro de uma transação, lê a view e faz ROLLBACK — o banco não é alterado
(a fixture bancos_inalterados do conftest confere isso ao final da sessão).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date

import pytest

from conftest import BANCOS_OK
from modules.pecuaria import calculos as c

pytestmark = pytest.mark.skipif(not BANCOS_OK, reason="PostgreSQL com os bancos SafraTech não acessível")


def _transacao(banco: str, inserts: str, select: str) -> list[dict]:
    sql = f"BEGIN;\n{inserts}\nSELECT row_to_json(t) FROM ({select}) t;\nROLLBACK;"
    p = subprocess.run(["psql", "-h", os.environ.get("PGHOST", "localhost"), "-U", os.environ.get("PGUSER", "postgres"), "-d", banco,
                        "-At", "-q", "-v", "ON_ERROR_STOP=1"], input=sql, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]


CASOS_COMPRA = [
    dict(q=100, peso=300, preco_cab=2800, peso_venda=480, rend=53, arroba=300, dias=180, transp=5000, alim=4.5, manejo=60),
    dict(q=37, peso=210.5, preco_cab=1950, peso_venda=455, rend=54.5, arroba=285.4, dias=240, transp=0, alim=0, manejo=0),
    dict(q=12, peso=400, preco_cab=4100, peso_venda=420, rend=50, arroba=250, dias=30, transp=1200, alim=12, manejo=15),
]


@pytest.mark.parametrize("k", CASOS_COMPRA)
def test_compra_igual_a_vw_lote_compra_viabilidade(k):
    ins = f"""
    INSERT INTO lote_compra (id_lote, descricao, data_avaliacao, raca_codigo, sexo, quantidade_animais, peso_medio_kg_pv,
                             preco_aquisicao_valor, preco_aquisicao_unidade)
    VALUES (990001, 'teste', '2026-11-03', 'NELORADO', 'macho', {k['q']}, {k['peso']}, {k['preco_cab']}, 'brl_cab');
    INSERT INTO lote_compra_custo_adicional (id_custo_adicional, id_lote, tipo, valor, base_valor, dias) VALUES
        (990001, 990001, 'transporte', {k['transp']}, 'brl_total', NULL),
        (990002, 990001, 'alimentacao', {k['alim']}, 'brl_cab_dia', {k['dias']}),
        (990003, 990001, 'manejo', {k['manejo']}, 'brl_cab', NULL);
    INSERT INTO lote_compra_cenario_venda (id_cenario, id_lote, nome_cenario, peso_venda_kg_pv, rendimento_carcaca_pct, preco_venda_brl_arroba,
                                           dias_permanencia, origem_premissas)
    VALUES (990001, 990001, 'teste', {k['peso_venda']}, {k['rend']}, {k['arroba']}, {k['dias']}, 'usuario');"""
    view = _transacao("pecuaria_compra_database", ins,
                      "SELECT custo_aquisicao_lote, custo_adicional_total, custo_total_lote, arrobas_carcaca_cab, arrobas_carcaca_lote, "
                      "receita_bruta_estimada, lucro_projetado, margem_lucro_pct, preco_equilibrio_brl_arroba, retorno_sobre_custo_pct "
                      "FROM vw_lote_compra_viabilidade WHERE id_lote = 990001")[0]
    r = c.analisar_compra(c.EntradaCompra(
        quantidade_animais=k["q"], peso_medio_compra_kg=k["peso"], modo_preco="cabeca", preco_compra=k["preco_cab"],
        peso_venda_kg=k["peso_venda"], rendimento_venda_pct=k["rend"], preco_venda_arroba=k["arroba"], dias_permanencia=k["dias"],
        custos=[c.CustoAdicional("transporte", k["transp"], "brl_total"), c.CustoAdicional("alimentacao", k["alim"], "brl_cab_dia"),
                c.CustoAdicional("manejo", k["manejo"], "brl_cab")]))
    pares = {"custo_aquisicao_lote": r.custo_aquisicao_lote, "custo_adicional_total": r.custo_adicional_total,
             "custo_total_lote": r.custo_total_lote, "arrobas_carcaca_cab": r.arrobas_carcaca_cab,
             "arrobas_carcaca_lote": r.arrobas_carcaca_lote, "receita_bruta_estimada": r.receita_bruta,
             "lucro_projetado": r.lucro, "margem_lucro_pct": r.margem_lucro_pct,
             "preco_equilibrio_brl_arroba": r.preco_equilibrio_arroba, "retorno_sobre_custo_pct": r.retorno_sobre_custo_pct}
    for campo, py in pares.items():
        assert float(view[campo]) == pytest.approx(py, rel=1e-9, abs=1e-6), campo


def test_preco_total_do_lote_equivale_a_preco_por_cabeca_na_view():
    k = CASOS_COMPRA[0]
    total = c.analisar_compra(c.EntradaCompra(quantidade_animais=k["q"], peso_medio_compra_kg=k["peso"], modo_preco="lote",
                                              preco_compra=k["preco_cab"] * k["q"], peso_venda_kg=k["peso_venda"],
                                              rendimento_venda_pct=k["rend"], preco_venda_arroba=k["arroba"]))
    assert total.custo_aquisicao_lote == pytest.approx(k["preco_cab"] * k["q"])


CASOS_CENARIO = [
    dict(q=200, peso=420, gmd=1.179, dias=90, ra=57, rf=57, pa=310, pf=330, cd=11.8, extra=1.2, acum=50000),
    dict(q=55, peso=380.5, gmd=0.45, dias=120, ra=52, rf=53.5, pa=295.5, pf=280, cd=2.3, extra=0, acum=0),
    dict(q=10, peso=500, gmd=-0.1, dias=30, ra=55, rf=55, pa=300, pf=300, cd=5, extra=0.5, acum=1000),
]


@pytest.mark.parametrize("k", CASOS_CENARIO)
def test_rentabilidade_igual_a_vw_projecao_cenario(k):
    ins = f"""
    INSERT INTO cenario_venda (id_cenario, descricao, tipo_cenario, data_base, quantidade_animais, peso_atual_kg_pv, gmd_kg_dia,
                               dias_espera, rendimento_carcaca_atual_pct, rendimento_carcaca_futuro_pct, preco_arroba_atual_brl,
                               preco_arroba_futuro_brl, custo_diario_cab_brl, custo_acumulado_brl, origem_premissas)
    VALUES (990001, 'teste', 'intermediario', '2026-11-03', {k['q']}, {k['peso']}, {k['gmd']}, {k['dias']}, {k['ra']}, {k['rf']},
            {k['pa']}, {k['pf']}, {k['cd']}, {k['acum']}, 'usuario');
    INSERT INTO cenario_custo_item (id_item, id_cenario, tipo, valor_brl_cab_dia) VALUES (990001, 990001, 'suplementacao', {k['extra']});"""
    view = _transacao("pecuaria_rentabilidade_database", ins,
                      "SELECT p.*, c.indicacao_pelas_premissas FROM vw_projecao_cenario p "
                      "JOIN vw_comparativo_cenarios c USING (descricao, tipo_cenario) WHERE p.id_cenario = 990001")[0]
    e = c.EntradaRentabilidade(quantidade_animais=k["q"], peso_atual_kg=k["peso"], preco_arroba_atual=k["pa"],
                               rendimento_atual_pct=k["ra"], dias=k["dias"], custo_acumulado_brl=k["acum"])
    r = c.projetar_cenario(e, c.Cenario("intermediario", k["pf"], k["gmd"], k["rf"],
                                        {"alimentacao": k["cd"], "suplementacao": k["extra"]}))
    pares = {"peso_projetado_kg_pv": r.peso_projetado_cab_kg, "arrobas_atual_cab": r.arrobas_atual_cab,
             "arrobas_futuro_cab": r.arrobas_futuro_cab, "arrobas_produzidas_espera": r.arrobas_produzidas,
             "receita_bruta_vender_agora": r.receita_vender_agora, "receita_bruta_vender_depois": r.receita_vender_depois,
             "custo_adicional_espera": r.custo_adicional_espera, "custo_acumulado_total_depois": r.custo_acumulado_total_depois,
             "margem_operacional_vender_agora": r.margem_operacional_agora,
             "margem_operacional_vender_depois": r.margem_operacional_depois,
             "resultado_incremental_esperar": r.resultado_incremental}
    for campo, py in pares.items():
        assert float(view[campo]) == pytest.approx(py, rel=1e-9, abs=1e-6), campo
    if view["custo_por_arroba_produzida"] is not None:
        assert float(view["custo_por_arroba_produzida"]) == pytest.approx(r.custo_por_arroba_produzida, rel=1e-9)
    assert view["indicacao_pelas_premissas"] == r.indicacao


def test_gmd_igual_a_vw_gmd_lote_e_flags_de_vw_gmd_lote_x_referencia():
    ins = """
    INSERT INTO lote_rebanho (id_lote, descricao, raca_codigo, sexo, fase, sistema_codigo)
    VALUES (990001, 'teste', 'NELORE_COMERCIAL', 'macho', 'recria', 'SEMI_INTENSIVO');
    INSERT INTO pesagem_rebanho (id_pesagem, id_lote, data_pesagem, peso_kg_pv) VALUES
        (990001, 990001, '2026-06-01', 288), (990002, 990001, '2026-06-01', 292), (990003, 990001, '2026-10-01', 351),
        (990004, 990001, '2026-10-01', 349);"""
    g = _transacao("pecuaria_desempenho_database", ins, "SELECT dias, gmd_kg_dia FROM vw_gmd_lote WHERE id_lote = 990001")[0]
    gmd_py, dias = c.gmd(290, 350, date(2026, 6, 1), date(2026, 10, 1))
    assert g["dias"] == dias and float(g["gmd_kg_dia"]) == pytest.approx(gmd_py)
    # As referências que o app considera compatíveis são exatamente as que a view marca com mesmo sexo, sistema e fase
    xr = _transacao("pecuaria_desempenho_database", ins,
                    "SELECT id_referencia FROM vw_gmd_lote_x_referencia WHERE id_lote = 990001 AND mesmo_sexo AND mesmo_sistema "
                    "AND mesma_fase")
    ids_view = {x["id_referencia"] for x in xr}
    import psql_executor
    from database import connections, pecuaria_queries as pq
    connections.definir_executor_externo(psql_executor.executar)
    try:
        refs = pq.referencias_gmd(pq.DESEMPENHO).to_dict("records")
    finally:
        connections.definir_executor_externo(None)
    # sexo 'macho' do lote: no app, o produtor informa macho inteiro/castrado; referências 'macho' são compatíveis com ambos
    refs_macho = [r for r in refs if r["sexo"] == "macho"]
    usadas, nao = c.comparar_gmd(refs_macho, "NELORE_COMERCIAL", "macho_inteiro", "SEMI_INTENSIVO", "recria", 18, gmd_py,
                                 date(2026, 6, 1), date(2026, 10, 1))
    ids_app = {u.id_registro for u in usadas} | {n.id_registro for n in nao if "mês" in n.motivo or "período" in n.motivo}
    assert ids_app == ids_view
