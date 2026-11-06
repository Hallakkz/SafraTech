"""Execução completa do main.py (Streamlit simulado): navegação, português, módulos agrícolas, Pecuária, PDFs e falhas."""
import ast
import datetime as dt
import io
import re
from pathlib import Path

import pdfplumber
import pytest

from conftest import MAIN, RAIZ
from database import connections
from database.connections import BancoIndisponivel
from stub_streamlit import AppSimulado

SEM_DADOS = "Não há dados de referência disponíveis no banco para esta combinação."
# Só o código do app: os pacotes dos bancos (agrícola e de pecuária) ficam fora da verificação
ARQS_APP = [p for p in RAIZ.rglob("*.py") if "tests" not in p.parts
            and not any(x.lower().replace("_", " ").startswith("banco de dados") for x in p.parts)]


def _texto_pdf(dados: bytes) -> str:
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages).replace("\n", " ")


def _menus():
    arv = ast.parse(Path(MAIN).read_text(encoding="utf-8"))
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.walk(arv)
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("MENU_AGRICULTURA", "MENU_PECUARIA")}


def agricultura(pagina: int = 0, valores=None) -> AppSimulado:
    app = AppSimulado(valores=valores).executar(MAIN)
    if pagina:
        app.interagir(MAIN, "nav_agricultura", pagina)
    return app


def pecuaria(pagina: int = 0) -> AppSimulado:
    app = AppSimulado().executar(MAIN)
    app.interagir(MAIN, "nav_agricultura", 3)
    if pagina:
        app.interagir(MAIN, "nav_pecuaria", pagina)
    return app


# =====================================================================================================
# Navegação
# =====================================================================================================
def test_menus_na_ordem_pedida():
    m = _menus()
    assert m["MENU_AGRICULTURA"] == ["🧪 Diagnóstico do Solo", "🍃 Diagnóstico Nutricional", "🗓️ Simulação de Plantio", "🐂 Pecuária",
                                     "🎓 EduAgro AI"]
    assert m["MENU_PECUARIA"] == ["💵 Análise de Viabilidade de Compra", "📈 Diagnóstico de Desempenho do Rebanho",
                                  "📊 Simulador de Rentabilidade", "🌱 Agricultura"]


@pytest.mark.parametrize("idx,cabecalho", [(0, "Diagnóstico do Solo"), (1, "Diagnóstico Nutricional"), (2, "Simulação de Plantio")])
def test_paginas_agricolas_iniciam_sem_erro(bancos, idx, cabecalho):
    app = agricultura(idx)
    assert not app.textos("error")
    assert app.contem(cabecalho, "header")
    menu = [w for w in app.widgets if w[2] == "nav_agricultura"][0]
    assert menu[3] == [0, 1, 2, 3, 4]


def test_clicar_em_pecuaria_troca_a_navegacao(bancos):
    app = agricultura(1)
    app.interagir(MAIN, "nav_agricultura", 3)
    assert app.session_state["area"] == "pecuaria"
    assert not [w for w in app.widgets if w[2] == "nav_agricultura"]
    assert [w for w in app.widgets if w[2] == "nav_pecuaria"][0][3] == [0, 1, 2, 3]
    assert app.contem("Análise de Viabilidade de Compra", "header") and not app.textos("error")


@pytest.mark.parametrize("idx,cabecalho", [(0, "Análise de Viabilidade de Compra"), (1, "Diagnóstico de Desempenho do Rebanho"),
                                           (2, "Simulador de Rentabilidade")])
def test_paginas_de_pecuaria_iniciam_sem_erro(bancos, idx, cabecalho):
    app = pecuaria(idx)
    assert not app.textos("error")
    assert app.contem(cabecalho, "header")


def test_voltar_para_agricultura_mantem_a_ultima_pagina(bancos):
    app = agricultura(2)                                   # Simulação de Plantio
    app.interagir(MAIN, "nav_agricultura", 3)              # Pecuária
    app.interagir(MAIN, "nav_pecuaria", 1)                 # Desempenho
    app.interagir(MAIN, "nav_pecuaria", 3)                 # 🌱 Agricultura
    assert app.session_state["area"] == "agricultura"
    assert app.contem("Simulação de Plantio", "header")
    app.interagir(MAIN, "nav_agricultura", 3)              # de volta à Pecuária: lembra o Desempenho
    assert app.contem("Diagnóstico de Desempenho do Rebanho", "header")


def test_pecuaria_nao_esta_em_paginas_independentes_do_menu_principal():
    m = _menus()
    for nome in ("Análise de Viabilidade de Compra", "Diagnóstico de Desempenho", "Simulador de Rentabilidade"):
        assert not any(nome in x for x in m["MENU_AGRICULTURA"])


# =====================================================================================================
# Remoções: Recomendação, inglês, Pecuária antiga
# =====================================================================================================
def test_recomendacao_removida():
    for p in ARQS_APP:
        t = p.read_text(encoding="utf-8")
        assert "Recomendação" not in t and "Recommendation" not in t, p
        assert "Safratech_crop_recommendation.csv" not in t and "data_core.csv" not in t, p
        assert "Área (Acres)" not in t and "Cultura Alvo" not in t, p


def test_pecuaria_antiga_removida():
    for p in ARQS_APP:
        t = p.read_text(encoding="utf-8")
        assert "safratech ia pecuaria.csv" not in t, p
        assert "load_pecuaria" not in t and "Analisar Animal" not in t and "Escore corporal" not in t, p


def test_sem_seletor_de_idioma_nem_ingles(bancos):
    assert not (RAIZ / "utils" / "i18n.py").exists()
    for p in ARQS_APP:
        t = p.read_text(encoding="utf-8")
        assert '"English"' not in t and "🌐" not in t and 'lang ==' not in t, p
    app = agricultura()
    assert not any("Language" in str(w[1]) or "Idioma" in str(w[1]) for w in app.widgets)
    assert "lang" not in app.session_state


INGLES = re.compile(r"\b(Soil|Livestock|Recommendation|Language|Settings|Breed|Weight|Analyze|Download|Report|Crop|Planting|"
                    r"Nutritional|Diagnosis|Herd|Purchase|Profitability|Scenario|Sources|Generate|Inputs|Results|Unit|Value)\b")


@pytest.mark.parametrize("area,idx", [("agricultura", 0), ("agricultura", 1), ("agricultura", 2),
                                      ("pecuaria", 0), ("pecuaria", 1), ("pecuaria", 2)])
def test_interface_somente_em_portugues(bancos, area, idx):
    app = agricultura(idx) if area == "agricultura" else pecuaria(idx)
    rotulos = [str(w[1]) for w in app.widgets] + [t for t in app.textos() if not t.lstrip().startswith("<style")]
    achados = sorted({m.group(0) for t in rotulos for m in [INGLES.search(t)] if m})
    assert not achados, achados


# =====================================================================================================
# Conexões e status dos bancos
# =====================================================================================================
def test_painel_de_status_lista_os_seis_bancos(bancos):
    app = agricultura()
    for nome in ("solo_database", "nutricao_database", "plantio_database", "pecuaria_compra_database",
                 "pecuaria_desempenho_database", "pecuaria_rentabilidade_database"):
        assert any(nome in t and "conectado" in t for t in app.textos("markdown")), nome


def test_status_individual_quando_um_banco_pecuario_cai(bancos):
    import psql_executor

    def executor(chave, sql, params):
        if chave == "pecuaria_desempenho":
            raise BancoIndisponivel("conexão recusada")
        return psql_executor.executar(chave, sql, params)
    connections.definir_executor_externo(executor)
    app = agricultura()
    linhas = app.textos("markdown")
    assert any("pecuaria_desempenho_database" in t and "indisponível" in t for t in linhas)
    assert any("pecuaria_compra_database" in t and "conectado" in t for t in linhas)
    assert any("solo_database" in t and "conectado" in t for t in linhas)


@pytest.mark.parametrize("banco_off", ["pecuaria_compra", "pecuaria_desempenho", "pecuaria_rentabilidade"])
def test_banco_pecuario_indisponivel_nao_derruba_os_outros(bancos, banco_off):
    import psql_executor

    def executor(chave, sql, params):
        if chave == banco_off:
            raise BancoIndisponivel("servidor fora do ar")
        return psql_executor.executar(chave, sql, params)
    connections.definir_executor_externo(executor)
    paginas = {"pecuaria_compra": 0, "pecuaria_desempenho": 1, "pecuaria_rentabilidade": 2}
    for nome, idx in paginas.items():
        app = pecuaria(idx)
        if nome == banco_off:
            assert app.contem(f"{nome}_database", "error") and app.contem("não está disponível", "error")
            assert app.contem(f"{connections.BANCOS[nome]['env']}", "caption")
        else:
            assert not app.textos("error"), nome
    app = agricultura(0)
    assert not app.textos("error") and app.contem("Diagnóstico do Solo", "header")


def test_falha_de_banco_agricola_nao_afeta_pecuaria(bancos):
    import psql_executor

    def executor(chave, sql, params):
        if chave == "solo":
            raise BancoIndisponivel("conexão recusada")
        return psql_executor.executar(chave, sql, params)
    connections.definir_executor_externo(executor)
    app = agricultura(0)
    assert app.contem("solo_database", "error")
    app.interagir(MAIN, "nav_agricultura", 1)
    assert not app.textos("error") and app.contem("Diagnóstico Nutricional", "header")
    app.interagir(MAIN, "nav_agricultura", 3)
    assert not app.textos("error") and app.contem("Análise de Viabilidade de Compra", "header")


def test_app_inicia_sem_nenhum_banco_configurado(monkeypatch):
    connections.definir_executor_externo(None)
    connections.descartar_engines()
    for cfg in connections.BANCOS.values():
        monkeypatch.setenv(cfg["env"], "")   # vazio (e não ausente): o main.py recarrega o .env, que não sobrescreve variáveis existentes
    monkeypatch.setattr(connections, "_segredos", {})
    for idx in range(3):
        app = agricultura(idx)
        assert app.contem("não está disponível", "error")
    for idx in range(3):
        app = pecuaria(idx)
        assert app.contem("não está disponível", "error")
        assert not app.downloads


# =====================================================================================================
# Módulos agrícolas preservados
# =====================================================================================================
def test_solo_fluxo_completo_e_pdf(bancos):
    v = {"solo_cultura": "Soja", "solo_textura": "Textura argilosa", "solo_argila": 40.0,
         "solo_bioma": "sim", "solo_sistema": "sequeiro", "solo_m_ph": "ph_agua", "solo_m_p": "p_mehlich", "solo_m_k": "k_mehlich",
         "solo_v_ph": 5.8, "solo_v_p": 3.0, "solo_v_k": 0.1536, "solo_u_k": "cmolc/dm³", "solo_v_ca": 30.0, "solo_u_ca": "mmolc/dm³",
         "solo_v_n": 10.0}
    app = AppSimulado(valores=v).executar(MAIN, botoes={"Gerar diagnóstico"})
    assert not app.textos("error")
    assert app.contem("não emite recomendação de calagem", "info")
    pdf = app.downloads["relatorio_solo.pdf"]
    assert pdf.startswith(b"%PDF")
    texto = _texto_pdf(pdf)
    for trecho in ("Diagnóstico do Solo", "Dados informados", "Faixa de", "Abaixo da referência", "Dados insuficientes",
                   "EMB_CERRADO_2004", "Fontes consultadas", "Divergências"):
        assert trecho in texto, trecho
    app.executar(MAIN)
    assert "relatorio_solo.pdf" in app.downloads


def test_solo_sem_valores_avisa(bancos):
    app = AppSimulado().executar(MAIN, botoes={"Gerar diagnóstico"})
    assert app.contem("Informe ao menos um valor", "warning")


def test_solo_valor_impossivel_bloqueado(bancos):
    app = AppSimulado(valores={"solo_v_v": 130.0}).executar(MAIN, botoes={"Gerar diagnóstico"})
    assert app.contem("Valor inválido", "error")


@pytest.mark.parametrize("cultura", ["Soja", "Milho", "Algodão", "Gergelim"])
def test_nutricional_quatro_culturas_e_pdf(bancos, cultura):
    app = agricultura(1)
    v = {"nut_cultura": cultura, "nut_tipo": "ambos", "nut_v_N": 30.0, "nut_v_K": 1.8, "nut_u_K": "%",
         "nut_sintomas": ["amarelecimento", "clorose_internerval"]}
    app.executar(MAIN, valores=v, botoes={"Gerar diagnóstico"})
    assert not app.textos("error")
    assert app.contem("Sintomas visuais são indícios", "warning")
    texto = _texto_pdf(app.downloads["relatorio_nutricional.pdf"])
    assert "Diagnóstico Nutricional" in texto and cultura in texto
    if cultura == "Gergelim":
        assert app.contem(SEM_DADOS, "warning")
        assert SEM_DADOS in texto
    else:
        assert "1,8 %" in texto


def test_nutricional_estagio_fora_do_protocolo(bancos):
    app = agricultura(1)
    v = {"nut_cultura": "Soja", "nut_tipo": "foliar", "nut_estagio_Soja": "__outro__", "nut_v_K": 20.0}
    app.executar(MAIN, valores=v, botoes={"Gerar diagnóstico"})
    assert app.contem(SEM_DADOS, "warning")


def _indice_municipio(uf, nome):
    from database import plantio_queries as pq
    df = pq.municipios(uf)
    return int(df.index[df["municipio"] == nome][0])


def test_plantio_fluxo_completo_e_pdf(bancos):
    app = agricultura(2)
    v = {"pla_uf": "GO", "pla_mun_GO": _indice_municipio("GO", "Rio Verde"),
         "pla_ini": 35, "pla_fim": 3, "pla_tar": 24.0, "pla_chuva": 600.0, "pla_umid": "baixa", "pla_notas": "talhão 3"}
    app.executar(MAIN, valores=v)
    app.executar(MAIN, botoes={"Consultar ZARC e simular"})
    assert not app.textos("error")
    assert app.contem("Isso não significa risco zero", "info")
    assert app.contem("NÃO possui indicação", "warning")
    assert any(x[0] == "plotly_chart" for x in app.saida)
    texto = _texto_pdf(app.downloads["relatorio_plantio.pdf"])
    for trecho in ("Simulação de Plantio", "Rio Verde/GO", "Portaria", "SEM INDICAÇÃO", "não é previsão do tempo",
                   "Informação do usuário", "Referência técnica", "MAPA_ZARC_2026"):
        assert trecho in texto, trecho


# =====================================================================================================
# Pecuária — Módulo 1: viabilidade de compra
# =====================================================================================================
COMPRA = {"pc_raca": "NELORADO", "pc_sexo": "macho_inteiro", "pc_qtd": 100, "pc_peso_compra": 300.0, "pc_dias": 180,
          "pc_preco_cab": 2800.0, "pc_peso_venda": 480.0, "pc_preco_arroba": 300.0, "pc_c_transporte": 5000.0,
          "pc_c_alimentacao": 4.5, "pc_c_manejo": 60.0, "pc_margem_min": 10.0}
BOTAO_COMPRA = {"📊 Analisar viabilidade"}


def test_compra_viavel_com_referencia_identificada_e_pdf(bancos):
    app = pecuaria(0)
    app.executar(MAIN, valores=COMPRA, botoes=BOTAO_COMPRA)
    assert not app.textos("error")
    assert app.contem("Investimento potencialmente viável")
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Investimento inicial"] == "R$ 280.000,00"
    assert metricas["Custos adicionais"] == "R$ 92.000,00"
    assert metricas["Arrobas estimadas"] == "1.696,0 @"          # rendimento 53% (PAR-F06-0094, nelorado macho)
    assert metricas["Receita bruta projetada"] == "R$ 508.800,00"
    assert metricas["Lucro / prejuízo"] == "R$ 136.800,00"
    assert metricas["Preço de equilíbrio"] == "R$ 219,34/@"
    texto = _texto_pdf(app.downloads["relatorio_pecuaria_compra.pdf"])
    for trecho in ("Análise de Viabilidade de Compra", "Dados do lote", "Dados de compra", "Peso, rendimento de carcaça e arrobas",
                   "1.696,0 @ no lote", "53,0% — referência PAR-F06-0094", "Custos", "Receita bruta projetada",
                   "R$ 136.800,00", "Margem de lucro", "Conclusão da análise", "Investimento potencialmente viável",
                   "Fontes técnicas utilizadas", "F06_COT93_MS", "Embrapa Gado de Corte", "2005", "p. 4",
                   "Premissas utilizadas", "15 kg de carcaça", "DIV-07"):
        assert trecho in texto, trecho
    app.executar(MAIN)                                   # o resultado persiste no rerun
    assert "relatorio_pecuaria_compra.pdf" in app.downloads


@pytest.mark.parametrize("arroba,esperado", [(200.0, "Investimento potencialmente inviável"),
                                             (235.0, "Investimento que exige atenção")])
def test_compra_conclusao_segue_os_calculos(bancos, arroba, esperado):
    app = pecuaria(0)
    app.executar(MAIN, valores={**COMPRA, "pc_preco_arroba": arroba}, botoes=BOTAO_COMPRA)
    assert app.contem(esperado)
    assert esperado in _texto_pdf(app.downloads["relatorio_pecuaria_compra.pdf"])


def test_compra_preco_por_cabeca_ou_lote_um_campo_por_vez(bancos):
    app = pecuaria(0)
    app.executar(MAIN, valores=COMPRA)
    rot = [w[1] for w in app.widgets]
    assert "Preço de compra por cabeça (R$/cab)" in rot and "Preço total do lote (R$)" not in rot
    v = {**COMPRA, "pc_modo_preco": "lote", "pc_preco_lote": 280000.0}
    app.executar(MAIN, valores=v, botoes=BOTAO_COMPRA)
    rot = [w[1] for w in app.widgets]
    assert "Preço total do lote (R$)" in rot and "Preço de compra por cabeça (R$/cab)" not in rot
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Investimento inicial"] == "R$ 280.000,00"     # 2.800 x 100 não é somado ao total


def test_compra_rendimento_informado_pelo_usuario(bancos):
    app = pecuaria(0)
    v = {**COMPRA, "pc_rend_modo_NELORADO_macho_inteiro": "usuario", "pc_rend_valor": 55.0}
    app.executar(MAIN, valores=v, botoes=BOTAO_COMPRA)
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Arrobas estimadas"] == "1.760,0 @"           # 100 x 480 x 55% / 15
    assert "informado pelo usuário" in _texto_pdf(app.downloads["relatorio_pecuaria_compra.pdf"])


def test_compra_sem_preco_da_arroba_pede_ao_usuario(bancos):
    app = pecuaria(0)
    app.executar(MAIN, valores={**COMPRA, "pc_preco_arroba": None}, botoes=BOTAO_COMPRA)
    assert app.contem("Informe o valor da arroba de venda", "error")
    assert not app.downloads
    assert app.contem("não contém cotação atual de mercado", "warning")


def test_compra_resultado_desatualizado_apos_alterar_dados(bancos):
    app = pecuaria(0)
    app.executar(MAIN, valores=COMPRA, botoes=BOTAO_COMPRA)
    app.executar(MAIN, valores={**COMPRA, "pc_qtd": 101})
    assert app.contem("Os dados de entrada foram alterados", "info")
    assert not app.contem("Investimento potencialmente viável")


def test_compra_nao_oferece_rendimento_de_outra_raca(bancos):
    app = pecuaria(0)
    app.executar(MAIN, valores={**COMPRA, "pc_raca": "F1_PARDO_SUICO_X_NELORE"})
    ops = [w[3] for w in app.widgets if str(w[2]).startswith("pc_rend_ref_")][0]
    assert not any(o.startswith("PAR-F06") for o in ops)          # PAR-F06 = nelorado: não serve para F1


# =====================================================================================================
# Pecuária — Módulo 2: desempenho
# =====================================================================================================
DESEMP = {"pd_ident": "Lote 3", "pd_raca": "F1_PARDO_SUICO_X_NELORE", "pd_sexo": "macho_castrado", "pd_sistema": "PASTO_E_CONFINAMENTO",
          "pd_fase": "recria", "pd_idade": 18.0, "pd_peso_atual": 350.0, "pd_data_atual": dt.date(2026, 10, 1),
          "pd_peso_ant": 290.0, "pd_data_ant": dt.date(2026, 6, 1)}
BOTAO_DESEMP = {"📈 Diagnosticar desempenho"}


def test_desempenho_com_referencias_compativeis_e_pdf(bancos):
    app = pecuaria(1)
    app.executar(MAIN, valores=DESEMP, botoes=BOTAO_DESEMP)
    assert not app.textos("error")
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Ganho médio diário (GMD)"] == "0,492 kg/dia"
    assert metricas["Evolução do peso"] == "60,0 kg em 122 dias"
    assert metricas["Peso de referência"] == "366–378 kg"          # 'Peso aos 18 meses', F1 castrados (F09)
    dfs = [x[1] for x in app.saida if x[0] == "dataframe"]
    assert any("PAR-F09-0022" in df.to_string() for df in dfs)
    comparacoes = [df for df in dfs if "por que é comparável" in df.columns]
    usados = {r for df in comparacoes for r in df["registro"]}
    assert "PAR-F09-0037" in usados                       # GMD do nascimento aos 18 meses: período compatível
    assert "PAR-F09-0042" not in usados                   # GMD dos 18 aos 20 meses: fora do período entre as pesagens
    nao_usadas = [df for df in dfs if "motivo da não utilização" in df.columns][0]
    assert "período de idade diferente" in nao_usadas.set_index("registro").loc["PAR-F09-0042", "motivo da não utilização"]
    texto = _texto_pdf(app.downloads["relatorio_pecuaria_desempenho.pdf"])
    for trecho in ("Identificação do animal ou lote", "Lote 3", "F1 Pardo Suíço Corte x Nelore", "Macho castrado", "18 meses",
                   "Pesagens", "0,492 kg/dia", "Comparações técnicas", "Indicadores de desempenho", "Pontos de atenção",
                   "Fontes técnicas utilizadas", "F09_BP12", "Boletim de Pesquisa", "2000", "p. 12", "Experimento: 104"):
        assert trecho in texto, trecho


def test_desempenho_sem_referencia_compativel_nao_inventa_peso(bancos):
    app = pecuaria(1)
    v = {**DESEMP, "pd_raca": "PANTANEIRO", "pd_sexo": "femea", "pd_sistema": "EXTENSIVO", "pd_idade": 30.0}
    app.executar(MAIN, valores=v, botoes=BOTAO_DESEMP)
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Peso de referência"] == "dados insuficientes"
    assert app.contem("Dados insuficientes", "info")
    assert "Dados insuficientes" in _texto_pdf(app.downloads["relatorio_pecuaria_desempenho.pdf"])


def test_desempenho_nelore_po_nao_usa_referencia_de_cruzados(bancos):
    app = pecuaria(1)
    app.executar(MAIN, valores={**DESEMP, "pd_raca": "NELORE_PO", "pd_sistema": "PASTO_E_CONFINAMENTO"}, botoes=BOTAO_DESEMP)
    dfs = [x[1] for x in app.saida if x[0] == "dataframe"]
    assert not any("PAR-F09" in df.to_string() and "por que é comparável" in df.columns for df in dfs)


def test_desempenho_sem_pesagem_anterior_avalia_so_o_peso(bancos):
    app = pecuaria(1)
    app.executar(MAIN, valores={**DESEMP, "pd_peso_ant": None, "pd_data_ant": None}, botoes=BOTAO_DESEMP)
    assert not app.textos("error")
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Ganho médio diário (GMD)"] == "informe a pesagem anterior"


def test_desempenho_datas_invertidas_bloqueadas(bancos):
    app = pecuaria(1)
    app.executar(MAIN, valores={**DESEMP, "pd_data_ant": dt.date(2026, 11, 1)}, botoes=BOTAO_DESEMP)
    assert app.contem("posterior", "error")


# =====================================================================================================
# Pecuária — Módulo 3: rentabilidade
# =====================================================================================================
RENT = {"pr_raca": "NELORE_COMERCIAL", "pr_sexo": "macho_inteiro", "pr_qtd": 200, "pr_peso": 420.0, "pr_dias": 90,
        "pr_preco": 310.0, "pr_c_alimentacao": 9.0, "pr_c_suplementacao": 2.0, "pr_c_manejo": 0.5, "pr_c_outros": 0.3,
        "pr_gmd_ref_NELORE_COMERCIAL_macho_inteiro": "PAR-F08-0232", "pr_rend_ref_NELORE_COMERCIAL_macho_inteiro": "PAR-F08-0227",
        "pr_conservador_preco": 290.0, "pr_conservador_gmd": 0.9, "pr_otimista_preco": 330.0, "pr_otimista_gmd": 1.3}
BOTAO_RENT = {"📊 Simular cenários"}


def test_rentabilidade_tres_cenarios_e_pdf(bancos):
    app = pecuaria(2)
    app.executar(MAIN, valores=RENT, botoes=BOTAO_RENT)
    assert not app.textos("error")
    metricas = dict(x[1:3] for x in app.saida if x[0] == "metric")
    assert metricas["Peso atual do rebanho"] == "84.000 kg"
    assert metricas["Arrobas hoje"] == "3.192,0 @"                  # 420 x 57% / 15 x 200
    assert metricas["Esperar — Conservador"].startswith("−R$")
    assert metricas["Esperar — Otimista"] == "R$ 144.876,00"
    assert app.contem("depende das premissas")
    comparativo = [x[1] for x in app.saida if x[0] == "dataframe" and "Indicador" in x[1].columns][0]
    assert list(comparativo.columns) == ["Indicador", "Vender agora", "Esperar — Conservador", "Esperar — Intermediário",
                                         "Esperar — Otimista"]
    assert sum(x[0] == "plotly_chart" for x in app.saida) >= 2
    texto = _texto_pdf(app.downloads["relatorio_pecuaria_rentabilidade.pdf"])
    for trecho in ("Dados do rebanho", "Premissas utilizadas", "Cenário conservador", "Cenário intermediário", "Cenário otimista",
                   "Comparativo financeiro", "Gráficos", "Custos e receitas", "Conclusão", "Fontes técnicas utilizadas",
                   "−R$ 97.716,00", "R$ 144.876,00", "PAR-F08-0232", "F08_DOC95_SEMIINTENSIVO", "não faz previsões de preço",
                   "igual ao valor atual (sem previsão de mercado)"):
        assert trecho in texto, trecho


def test_rentabilidade_cenarios_identicos_avisam(bancos):
    app = pecuaria(2)
    v = {k: val for k, val in RENT.items() if not k.startswith(("pr_conservador", "pr_otimista"))}
    app.executar(MAIN, valores=v, botoes=BOTAO_RENT)
    assert app.contem("premissas idênticas", "warning")


def test_rentabilidade_sem_preco_atual_pede_ao_usuario(bancos):
    app = pecuaria(2)
    app.executar(MAIN, valores={**RENT, "pr_preco": None}, botoes=BOTAO_RENT)
    assert app.contem("Informe o valor atual da arroba", "error")


def test_rentabilidade_gmd_proprio(bancos):
    app = pecuaria(2)
    v = {**RENT, "pr_gmd_modo_NELORE_COMERCIAL_macho_inteiro": "usuario", "pr_gmd_valor": 1.0}
    app.executar(MAIN, valores=v, botoes=BOTAO_RENT)
    assert not app.textos("error")
    assert "informado pelo usuário" in _texto_pdf(app.downloads["relatorio_pecuaria_rentabilidade.pdf"])


# =====================================================================================================
# Dados históricos e ausência de valores fictícios
# =====================================================================================================
def test_precos_historicos_identificados_como_historicos(bancos):
    app = pecuaria(0)
    dfs = [x[1] for x in app.saida if x[0] == "dataframe" and "data de referência" in x[1].columns]
    assert dfs and set(dfs[0]["natureza"]) == {"histórico de publicação"}
    assert all("NÃO usar como cotação atual" in u for u in dfs[0]["uso permitido"])


def test_nenhum_valor_economico_pre_preenchido(bancos):
    """Preço da arroba, preço de compra, pesos e quantidade começam vazios: nada de valores de demonstração."""
    for idx, chaves in ((0, ["pc_qtd", "pc_peso_compra", "pc_preco_cab", "pc_peso_venda", "pc_preco_arroba", "pc_margem_min"]),
                        (1, ["pd_idade", "pd_peso_atual", "pd_peso_ant"]),
                        (2, ["pr_qtd", "pr_peso", "pr_dias", "pr_preco"])):
        app = pecuaria(idx)
        for k in chaves:
            assert app.session_state.get(k) is None, k


@pytest.mark.parametrize("pagina,valores,botao", [(0, COMPRA, BOTAO_COMPRA), (1, DESEMP, BOTAO_DESEMP), (2, RENT, BOTAO_RENT)])
def test_telas_de_resultado_e_pdfs_em_portugues(bancos, pagina, valores, botao):
    app = pecuaria(pagina)
    app.executar(MAIN, valores=valores, botoes=botao)
    textos = [t for t in app.textos() if not t.lstrip().startswith("<style")]
    textos += [x[1].to_string() for x in app.saida if x[0] == "dataframe"]
    textos += [_texto_pdf(pdf) for pdf in app.downloads.values()]
    achados = sorted({m.group(0) for t in textos for m in INGLES.finditer(t)})
    assert not achados, achados
