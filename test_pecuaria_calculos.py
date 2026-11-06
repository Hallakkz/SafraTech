"""Cálculos da Pecuária: peso vivo x carcaça, rendimento, arrobas, custos, margens, GMD e cenários (sem banco)."""
from datetime import date

import pytest

from modules.pecuaria import calculos as c


# ------------------------------------------------------------------ conversões básicas
def test_arroba_e_de_15_kg_de_carcaca():
    assert c.KG_POR_ARROBA == 15.0
    # 480 kg PV x 53% = 254,4 kg de carcaça = 16,96 @
    assert c.peso_carcaca_kg(480, 53) == pytest.approx(254.4)
    assert c.arrobas_de_peso_vivo(480, 53) == pytest.approx(16.96)


def test_peso_vivo_nao_vira_arroba_sem_rendimento():
    # dividir peso vivo por 15 (arroba de peso vivo) daria 32 @ — o cálculo correto usa o rendimento
    assert c.arrobas_de_peso_vivo(480, 53) != pytest.approx(480 / 15)
    with pytest.raises(c.DadosInvalidos):
        c.arrobas_de_peso_vivo(480, None)


def test_rendimento_nao_e_fixo():
    assert c.arrobas_de_peso_vivo(480, 50) < c.arrobas_de_peso_vivo(480, 53) < c.arrobas_de_peso_vivo(480, 57.5)


def test_exemplo_da_fonte_f01_pergunta_454():
    # "18 @ e rendimento de 53% = 509 kg de peso vivo" (F01, p.231 — formula PESO_VIVO_DE_ARROBAS_CARCACA)
    assert c.peso_vivo_de_arrobas(18, 53) == pytest.approx(509.43, abs=0.01)


def test_exemplo_da_fonte_f01_rendimento():
    # 480 kg PV e carcaça de 264 kg -> 55% (PAR-F01-0001)
    assert c.rendimento_carcaca_pct(264, 480) == pytest.approx(55.0)


@pytest.mark.parametrize("rend", [0, 100, 120, -5])
def test_rendimento_fora_dos_limites(rend):
    with pytest.raises(c.DadosInvalidos):
        c.validar_rendimento(rend)


# ------------------------------------------------------------------ módulo 1: compra
def _entrada(**kw):
    base = dict(quantidade_animais=100, peso_medio_compra_kg=300, modo_preco="cabeca", preco_compra=2800, peso_venda_kg=480,
                rendimento_venda_pct=53, preco_venda_arroba=300, dias_permanencia=180, margem_minima_pct=10,
                custos=[c.CustoAdicional("transporte", 5000, "brl_total"), c.CustoAdicional("alimentacao", 4.5, "brl_cab_dia"),
                        c.CustoAdicional("manejo", 60, "brl_cab")])
    base.update(kw)
    return c.EntradaCompra(**base)


def test_compra_calculo_completo():
    r = c.analisar_compra(_entrada())
    assert r.custo_aquisicao_lote == pytest.approx(280_000)
    assert r.custo_adicional_total == pytest.approx(5_000 + 4.5 * 100 * 180 + 60 * 100)   # 92.000
    assert r.custo_total_lote == pytest.approx(372_000)
    assert r.peso_total_compra_kg == 30_000 and r.peso_total_venda_kg == 48_000
    assert r.peso_carcaca_lote_kg == pytest.approx(25_440)
    assert r.arrobas_carcaca_lote == pytest.approx(1_696)
    assert r.receita_bruta == pytest.approx(508_800)
    assert r.receita_liquida == pytest.approx(508_800 - 92_000)
    assert r.lucro == pytest.approx(136_800)
    assert r.margem_lucro_pct == pytest.approx(136_800 / 508_800 * 100)
    assert r.retorno_sobre_custo_pct == pytest.approx(136_800 / 372_000 * 100)
    assert r.preco_equilibrio_arroba == pytest.approx(372_000 / 1_696)
    assert r.gmd_implicito_kg_dia == pytest.approx(1.0)
    assert r.classificacao == "viavel"


def test_compra_pontos_de_equilibrio_zeram_o_lucro():
    r = c.analisar_compra(_entrada())
    for campo, valor in (("preco_venda_arroba", r.preco_equilibrio_arroba), ("rendimento_venda_pct", r.rendimento_equilibrio_pct),
                         ("peso_venda_kg", r.peso_venda_equilibrio_kg)):
        assert c.analisar_compra(_entrada(**{campo: valor})).lucro == pytest.approx(0, abs=1e-6), campo


def test_preco_por_cabeca_ou_total_nunca_somados():
    por_cab = c.analisar_compra(_entrada(modo_preco="cabeca", preco_compra=2800))
    total = c.analisar_compra(_entrada(modo_preco="lote", preco_compra=280_000))
    assert por_cab.custo_aquisicao_lote == total.custo_aquisicao_lote == pytest.approx(280_000)
    assert por_cab.lucro == pytest.approx(total.lucro)


def test_classificacao_determinada_pelos_calculos():
    assert c.analisar_compra(_entrada(preco_venda_arroba=200)).classificacao == "inviavel"     # receita < custo
    r = c.analisar_compra(_entrada(preco_venda_arroba=230))
    assert r.lucro > 0 and r.margem_lucro_pct < 10 and r.classificacao == "atencao"
    assert c.analisar_compra(_entrada(preco_venda_arroba=230, margem_minima_pct=1)).classificacao == "viavel"


def test_custo_por_dia_exige_dias():
    with pytest.raises(c.DadosInvalidos):
        c.analisar_compra(_entrada(dias_permanencia=None))


@pytest.mark.parametrize("campo", ["quantidade_animais", "peso_venda_kg", "preco_venda_arroba", "preco_compra", "rendimento_venda_pct"])
def test_compra_campos_obrigatorios(campo):
    with pytest.raises(c.DadosInvalidos):
        c.analisar_compra(_entrada(**{campo: None}))


def test_fatores_explicam_o_resultado():
    r = c.analisar_compra(_entrada())
    f = " ".join(c.fatores_compra(r))
    assert "219,34" in f and "75,3%" in f and "Sensibilidade" in f


# ------------------------------------------------------------------ módulo 2: desempenho
def test_gmd_e_dias():
    g, dias = c.gmd(290, 350, date(2026, 6, 1), date(2026, 10, 1))
    assert dias == 122 and g == pytest.approx(60 / 122)


def test_gmd_datas_invalidas():
    with pytest.raises(c.DadosInvalidos):
        c.gmd(290, 350, date(2026, 10, 1), date(2026, 10, 1))
    with pytest.raises(c.DadosInvalidos):
        c.gmd(290, 350, date(2026, 10, 2), date(2026, 10, 1))


@pytest.mark.parametrize("texto,esperado", [
    ("Peso aos 12 meses", (12, 12)), ("Peso aos 18 meses", (18, 18)), ("Peso corrigido para 205 dias - machos", (6.7, 6.7)),
    ("Machos 1-2 anos comercializados - peso vivo médio", (12, 24)), ("Peso ao nascimento", (0, 0)),
    ("Peso potencial à desmama natural aos 10 meses (bezerros nelore, Nhecolândia)", (10, 10)),
    ("Peso aos 42 meses de touros transferidos aos 12 meses e recriados em campo nativo", (42, 42)),
    ("Peso à desmama", None), ("Peso das vacas adultas - desmama", None), ("Peso de abate após jejum - 1998", None),
    ("Ganho de peso esperado em ~90 dias de suplementação na seca", None),
])
def test_idade_da_referencia_vem_so_do_texto_da_fonte(texto, esperado):
    assert c.idade_referencia_meses(texto) == esperado


def _ref_peso(**kw):
    base = dict(id_registro="R1", parametro="Peso aos 12 meses", raca_codigo="F1_PARDO_SUICO_X_NELORE", raca="F1",
                sexo="macho_castrado", sistema_codigo="PASTO_E_CONFINAMENTO", sistema="Pasto + confinamento",
                valor_numerico=284.0, valor_min=None, valor_max=None)
    base.update(kw)
    return base


def test_peso_comparado_somente_com_referencia_compativel():
    refs = [_ref_peso(), _ref_peso(id_registro="NELORE", raca_codigo="NELORE_PO"), _ref_peso(id_registro="FEMEA", sexo="femea"),
            _ref_peso(id_registro="SIST", sistema_codigo="EXTENSIVO"), _ref_peso(id_registro="IDADE", parametro="Peso aos 18 meses"),
            _ref_peso(id_registro="SEMIDADE", parametro="Peso à desmama")]
    usadas, nao = c.comparar_peso(refs, "F1_PARDO_SUICO_X_NELORE", "macho_castrado", "PASTO_E_CONFINAMENTO", 12, 260)
    assert [u.id_registro for u in usadas] == ["R1"]
    motivos = {n.id_registro: n.motivo for n in nao}
    assert "raça" in motivos["NELORE"] and "sexo" in motivos["FEMEA"] and "sistema" in motivos["SIST"]
    assert "idade" in motivos["IDADE"] and "não informa a idade" in motivos["SEMIDADE"]
    assert usadas[0].status == "adequado" and usadas[0].diferenca == pytest.approx(-24)


def test_nelore_puro_e_cruzado_nunca_se_misturam():
    refs = [_ref_peso(raca_codigo="NELORE_PO"), _ref_peso(raca_codigo="NELORE_COMERCIAL"), _ref_peso(raca_codigo="NELORADO")]
    usadas, _ = c.comparar_peso(refs, "F1_PARDO_SUICO_X_NELORE", "macho_castrado", "PASTO_E_CONFINAMENTO", 12, 260)
    assert usadas == []
    usadas, _ = c.comparar_peso([_ref_peso(raca_codigo="F1_PARDO_SUICO_X_NELORE")], "NELORE_PO", "macho_castrado",
                                "PASTO_E_CONFINAMENTO", 12, 260)
    assert usadas == []


def test_sem_referencia_compativel_dados_insuficientes_sem_inventar_peso():
    usadas, _ = c.comparar_peso([_ref_peso()], "PANTANEIRO", "femea", "EXTENSIVO", 30, 300)
    assert usadas == [] and c.resumo_status(usadas) == "insuficiente"
    pontos = c.pontos_de_atencao(usadas, [], None, None)
    assert any("dados insuficientes" in p and "nenhum peso esperado foi estimado" in p for p in pontos)


def test_status_com_tolerancia_e_faixa():
    u, _ = c.comparar_peso([_ref_peso()], "F1_PARDO_SUICO_X_NELORE", "macho_castrado", "PASTO_E_CONFINAMENTO", 12, 240, tolerancia_pct=10)
    assert u[0].status == "abaixo"
    u, _ = c.comparar_peso([_ref_peso()], "F1_PARDO_SUICO_X_NELORE", "macho_castrado", "PASTO_E_CONFINAMENTO", 12, 330, tolerancia_pct=10)
    assert u[0].status == "acima"
    faixa = _ref_peso(valor_numerico=None, valor_min=250.0, valor_max=300.0)
    u, _ = c.comparar_peso([faixa], "F1_PARDO_SUICO_X_NELORE", "macho_castrado", "PASTO_E_CONFINAMENTO", 12, 299)
    assert u[0].status == "adequado"


def _ref_gmd(**kw):
    base = dict(id_registro="G1", parametro="Ganho médio diário (GMD)", raca_codigo="NELORE_COMERCIAL", raca="Nelore comercial",
                sexo="macho", sistema_codigo="SEMI_INTENSIVO", sistema="Semi-intensivo", fase="recria", gmd_kg_dia=0.5,
                gmd_min_kg_dia=None, gmd_max_kg_dia=None)
    base.update(kw)
    return base


def test_gmd_exige_mesma_fase_e_respeita_periodo_e_mes():
    d0, d1 = date(2026, 6, 1), date(2026, 10, 1)       # junho a outubro; idade 18 meses na pesagem atual (~14 a 18)
    refs = [_ref_gmd(), _ref_gmd(id_registro="FASE", fase="terminacao"),
            _ref_gmd(id_registro="JANELA_OK", parametro="GMD do nascimento aos 18 meses"),
            _ref_gmd(id_registro="JANELA_FORA", parametro="GMD dos 18 aos 20 meses"),
            _ref_gmd(id_registro="MES_OK", parametro="GMD esperado em pastagens - agosto"),
            _ref_gmd(id_registro="MES_FORA", parametro="GMD esperado em pastagens - janeiro")]
    usadas, nao = c.comparar_gmd(refs, "NELORE_COMERCIAL", "macho_inteiro", "SEMI_INTENSIVO", "recria", 18, 0.45, d0, d1)
    assert {u.id_registro for u in usadas} == {"G1", "JANELA_OK", "MES_OK"}
    assert {n.id_registro for n in nao} == {"FASE", "JANELA_FORA", "MES_FORA"}
    usadas, nao = c.comparar_gmd(refs, "NELORE_COMERCIAL", "macho_inteiro", "SEMI_INTENSIVO", "", 18, 0.45, d0, d1)
    assert usadas == [] and all("fase" in n.motivo or "raça" in n.motivo for n in nao)


def test_perda_de_peso_e_ponto_de_atencao():
    pontos = c.pontos_de_atencao([], [], -0.1, -12)
    assert any("PERDEU peso" in p for p in pontos)


# ------------------------------------------------------------------ módulo 3: rentabilidade
def _ent():
    return c.EntradaRentabilidade(quantidade_animais=200, peso_atual_kg=420, preco_arroba_atual=310, rendimento_atual_pct=57,
                                  dias=90, custo_acumulado_brl=50_000)


def _cen(tipo="intermediario", preco=310, gmd=1.0, rend=57, custos=None):
    return c.Cenario(tipo, preco, gmd, rend, custos or {"alimentacao": 9, "suplementacao": 2, "manejo": 0.5, "outros": 0.5})


def test_projecao_igual_a_view():
    r = c.projetar_cenario(_ent(), _cen())
    assert r.peso_atual_rebanho_kg == 84_000
    assert r.peso_projetado_cab_kg == pytest.approx(510)
    assert r.ganho_cab_kg == pytest.approx(90) and r.ganho_rebanho_kg == pytest.approx(18_000)
    assert r.arrobas_atual_cab == pytest.approx(420 * 0.57 / 15)
    assert r.arrobas_futuro_cab == pytest.approx(510 * 0.57 / 15)
    assert r.receita_vender_agora == pytest.approx(420 * 0.57 / 15 * 200 * 310)
    assert r.receita_vender_depois == pytest.approx(510 * 0.57 / 15 * 200 * 310)
    assert r.custo_adicional_espera == pytest.approx(12 * 90 * 200)
    assert r.custo_acumulado_total_depois == pytest.approx(50_000 + 216_000)
    assert r.margem_operacional_agora == pytest.approx(r.receita_vender_agora - 50_000)
    assert r.margem_operacional_depois == pytest.approx(r.receita_vender_depois - 266_000)
    inc = (r.receita_vender_depois - 216_000) - r.receita_vender_agora
    assert r.resultado_incremental == pytest.approx(inc)
    assert r.indicacao == ("esperar" if inc > 0 else "vender agora")
    assert r.custo_por_arroba_produzida == pytest.approx(216_000 / r.arrobas_produzidas)


def test_preco_de_equilibrio_futuro_zera_a_diferenca():
    r = c.projetar_cenario(_ent(), _cen())
    r2 = c.projetar_cenario(_ent(), _cen(preco=r.preco_equilibrio_futuro))
    assert r2.resultado_incremental == pytest.approx(0, abs=1e-6) and r2.indicacao in ("indiferente", "esperar", "vender agora")


def test_tres_cenarios_e_conclusao():
    res = c.comparar_cenarios(_ent(), [_cen("conservador", 280, 0.7), _cen("intermediario", 310, 1.0), _cen("otimista", 340, 1.3)])
    assert [r.cenario.tipo for r in res] == ["conservador", "intermediario", "otimista"]
    assert res[0].resultado_incremental < res[1].resultado_incremental < res[2].resultado_incremental
    texto = c.conclusao_rentabilidade(res, 90)
    assert "depende das premissas" in texto or "Nas três premissas" in texto


def test_custo_acumulado_nao_altera_a_decisao():
    e1, e2 = _ent(), _ent()
    e2.custo_acumulado_brl = 0
    assert c.projetar_cenario(e1, _cen()).resultado_incremental == pytest.approx(c.projetar_cenario(e2, _cen()).resultado_incremental)


@pytest.mark.parametrize("gmd", [-2.5, 3.5, None])
def test_gmd_fora_da_restricao_do_banco(gmd):
    with pytest.raises(c.DadosInvalidos):
        c.projetar_cenario(_ent(), _cen(gmd=gmd))


def test_rendimento_futuro_obrigatorio():
    with pytest.raises(c.DadosInvalidos):
        c.projetar_cenario(_ent(), _cen(rend=None))
