"""Cursos, biblioteca, exercícios, avaliações e progresso do EduAgro AI (lógica e persistência)."""
import io
import random
from datetime import date

import pytest

from fake_deepseek import SessaoFalsa, resposta_chat
from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import avaliacoes as av
from modules.eduagro_ai import biblioteca as bib
from modules.eduagro_ai import cursos as cur
from modules.eduagro_ai import deepseek_client as ds
from modules.eduagro_ai import exercicios_calculo as ec
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai import progresso as pg
from modules.pecuaria import calculos as calc


def cliente_falso(texto_json: str):
    cfg = ds.ConfigDeepSeek(api_key="sk-teste-xxxxxxxxxxxxxxxxxxxxxxxx", max_req_min=100)
    return ds.ClienteDeepSeek(cfg, sessao=SessaoFalsa(lambda m, u, j: resposta_chat(texto_json)), dormir=lambda s: None)


# ---------------------------------------------------------------- armazenamento e perfis
def test_banco_local_separado_dos_bancos_do_safratech(edu_dados):
    u = arm.obter_ou_criar_usuario("  Maria   Silva ")
    assert u["nome"] == "Maria Silva" and arm.obter_ou_criar_usuario("Maria Silva")["id"] == u["id"]
    assert arm.caminho_banco().exists() and arm.caminho_banco().parent == edu_dados
    arm.definir_nivel(u["id"], "Avançado")
    assert arm.obter_ou_criar_usuario("Maria Silva")["nivel"] == "Avançado"


# ---------------------------------------------------------------- cursos
def test_catalogo_com_as_categorias_e_cursos_pedidos(edu_dados):
    cursos = cur.listar_cursos()
    nomes = {(c["categoria"], c["nome"]) for c in cursos}
    for nome in ("Fundamentos da agricultura", "Ciência do solo", "Fertilidade e adubação", "Nutrição de plantas",
                 "Culturas agrícolas", "Manejo de lavouras", "Climatologia agrícola", "Planejamento de plantio"):
        assert ("Agricultura", nome) in nomes
    for nome in ("Introdução à pecuária de corte", "Raças bovinas", "Nutrição animal", "Sistemas de criação",
                 "Manejo de bovinos", "Desempenho do rebanho", "Custos de produção", "Comercialização de bovinos",
                 "Gestão econômica da pecuária"):
        assert ("Pecuária", nome) in nomes
    for nome in ("Gestão de propriedades rurais", "Custos de produção", "Planejamento financeiro", "Comercialização agrícola",
                 "Tecnologia no agronegócio"):
        assert ("Gestão Rural", nome) in nomes
    assert len(cursos) == 22
    for c in cursos:
        assert c["descricao"] and c["nivel"] in cur.NIVEIS and c["objetivos"]
        assert c["aulas"] == 0, "o catálogo não traz conteúdo técnico apresentado como oficial"
    cur.garantir_catalogo()
    assert len(cur.listar_cursos()) == 22


def test_aulas_conclusao_e_avaliacao_final(edu_dados):
    u = arm.obter_ou_criar_usuario("Ana")
    curso = cur.listar_cursos("Pecuária")[0]
    with pytest.raises(ValueError):
        cur.salvar_aula(curso["id"], "", "")
    a1 = cur.salvar_aula(curso["id"], "Fases da produção", "Texto próprio", "resumo", "exemplo", "ref", "proprio")
    a2 = cur.salvar_aula(curso["id"], "Rascunho", "Texto da IA", origem="rascunho_ia")
    aulas = cur.listar_aulas(curso["id"])
    assert [a["revisada"] for a in aulas] == [1, 0]
    cur.marcar_revisada(a2)
    cur.concluir_aula(u["id"], a1)
    assert cur.atualizar_status_curso(u["id"], curso["id"]) == "em_andamento"
    cur.concluir_aula(u["id"], a2)
    assert cur.atualizar_status_curso(u["id"], curso["id"]) == "concluido"
    # com avaliação final cadastrada, a conclusão exige nota mínima
    q = {"tipo": "verdadeiro_falso", "enunciado": "Afirmação de teste sobre o curso.", "resposta": "Verdadeiro",
         "explicacao": "x", "referencias": [], "assuntos": ["Fases"], "origem": "cadastrada", "categoria": "Pecuária"}
    q["id"] = av.salvar_questao(q, curso["id"], avaliacao_final=True)
    assert cur.atualizar_status_curso(u["id"], curso["id"]) == "em_andamento"
    av.registrar_avaliacao(u["id"], "Final", [(q, av.corrigir(q, "Falso"))], curso_id=curso["id"], final=True)
    assert cur.atualizar_status_curso(u["id"], curso["id"]) == "em_andamento"
    av.registrar_avaliacao(u["id"], "Final", [(q, av.corrigir(q, "Verdadeiro"))], curso_id=curso["id"], final=True)
    assert cur.atualizar_status_curso(u["id"], curso["id"]) == "concluido"


def test_rascunho_de_aula_usa_so_referencias_recuperadas(bancos, edu_dados):
    curso = next(c for c in cur.listar_cursos() if c["codigo"] == "PEC-06")
    resposta = ('{"titulo": "GMD", "conteudo": "O GMD é calculado assim [S1].", "resumo": "- GMD", '
                '"exemplos": "Exemplo hipotético", "referencias": ["S1", "S99"]}')
    r = cur.gerar_rascunho_aula(cliente_falso(resposta), curso, "ganho médio diário", "Iniciante", "pecuaria")
    assert r["citadas_validas"] == ["S1"] and "[S1]" in r["referencias"] and "pecuaria_" in r["referencias"]
    with pytest.raises(ValueError):
        cur.gerar_rascunho_aula(cliente_falso(resposta), curso, "criptomoedas bitcoin blockchain", "Iniciante", "pecuaria")


# ---------------------------------------------------------------- exercícios de cálculo
def test_exercicios_de_calculo_conferem_com_as_formulas_do_safratech(bancos, edu_dados):
    kr.invalidar_bancos()
    codigos = {g.codigo for g in ec.disponiveis()}
    assert {"GMD", "RENDIMENTO", "ARROBAS", "SOMA_BASES", "CTC", "V", "UA", "PRENHEZ"} <= codigos
    for semente in range(15):
        q = ec.gerar("GMD", semente)
        nums = [int(x) for x in __import__("re").findall(r"\*\*(\d+)", q["enunciado"])]
        pi, pf, dias = nums[0], nums[1], nums[2]
        esperado, _ = calc.gmd(pi, pf, date(2026, 1, 1), date.fromordinal(date(2026, 1, 1).toordinal() + dias))
        assert q["resposta_numerica"] == pytest.approx(esperado, abs=1e-3)
        assert "pecuaria_desempenho_database" in q["justificativa"] and ec.AVISO_HIPOTETICO in q["enunciado"]
    for semente in range(15):
        q = ec.gerar("ARROBAS", semente)
        pv, rend = [int(x) for x in __import__("re").findall(r"\*\*(\d+)", q["enunciado"])][:2]
        assert q["resposta_numerica"] == pytest.approx(calc.arrobas_de_peso_vivo(pv, rend), abs=1e-6)
    q = ec.gerar("V", 3)
    assert "solo_database" in q["justificativa"] and "V (%) = S / CTC × 100" in q["justificativa"]
    assert av.corrigir(q, q["resposta"].split()[0]).correta
    assert not av.corrigir(q, "1").correta
    assert av.corrigir(q, str(q["resposta_numerica"]).replace(".", ",")).correta


def test_leitura_de_numeros_em_portugues():
    assert ec.ler_numero("0,85") == 0.85 and ec.ler_numero("1.234,5") == 1234.5 and ec.ler_numero("12,3 @") == 12.3
    assert ec.ler_numero("85 %") == 85 and ec.ler_numero("abc") is None


# ---------------------------------------------------------------- questões geradas por IA
def _rotulos():
    r = kr.Referencia(chave="x", origem="banco", area="pecuaria", bancos=["pecuaria_desempenho_database"], tipo="Fórmula",
                      titulo="GMD", texto="gmd = ...", fonte="Fonte", rotulo="S1")
    return {"S1": r}


def test_validacao_das_questoes_da_ia():
    rot = _rotulos()
    base = {"enunciado": "Qual é a fórmula do ganho médio diário?", "explicacao": "Porque...", "referencias": ["S1"],
            "assuntos": ["GMD"]}
    mc = av.validar_questao({**base, "tipo": "multipla_escolha", "alternativas": ["A) x", "B) y", "C) z", "D) w"],
                             "resposta_correta": "C"}, rot, "Iniciante", "GMD", "Pecuária")
    assert mc["alternativas"] == ["x", "y", "z", "w"] and mc["resposta"] == "C" and mc["origem"] == "ia"
    assert mc["referencias"][0]["bancos"] == ["pecuaria_desempenho_database"]
    assert av.validar_questao({**base, "tipo": "multipla_escolha", "alternativas": ["x", "y"], "resposta_correta": "A"},
                              rot, "Iniciante", "GMD", "Pecuária") is None
    assert av.validar_questao({**base, "tipo": "verdadeiro_falso", "referencias": ["S7"], "resposta_correta": "V"},
                              rot, "Iniciante", "GMD", "Pecuária") is None, "sem referência real a questão é descartada"
    vf = av.validar_questao({**base, "tipo": "verdadeiro_falso", "resposta_correta": "falso"}, rot, "Iniciante", "GMD", "Pecuária")
    assert vf["resposta"] == "Falso"
    oficial = av.validar_questao({**base, "tipo": "verdadeiro_falso", "resposta_correta": "V",
                                  "enunciado": "Questão oficial do concurso: o GMD é a diferença de peso por dia."},
                                 rot, "Iniciante", "GMD", "Pecuária")
    assert "oficial" not in oficial["enunciado"].lower() and "concurso" not in oficial["enunciado"].lower()
    pr = av.validar_questao({**base, "tipo": "pratica", "resposta_correta": "0,8 kg/dia", "resposta_numerica": "0,8",
                             "tolerancia": 0.05}, rot, "Iniciante", "GMD", "Pecuária")
    assert pr["resposta_numerica"] == 0.8 and av.corrigir(pr, "0,81").correta and not av.corrigir(pr, "0,9").correta


def test_geracao_de_exercicios_pela_ia_com_referencias_reais(bancos, edu_dados):
    resposta = ('{"questoes": ['
                '{"tipo": "multipla_escolha", "enunciado": "Como se calcula o GMD de um bovino?", "alternativas": '
                '["Peso final dividido pelos dias", "(Peso final - peso inicial) / dias", "Peso inicial x dias", "Nenhuma"], '
                '"resposta_correta": "B", "explicacao": "É a diferença de peso no período dividida pelos dias.", '
                '"justificativa_tecnica": "Fórmula do banco [S1].", "referencias": ["S1"], "assuntos": ["GMD"]},'
                '{"tipo": "verdadeiro_falso", "enunciado": "Afirmação inventada sem base nenhuma no contexto.", '
                '"resposta_correta": "Falso", "explicacao": "x", "referencias": [], "assuntos": ["x"]}]}')
    g = av.gerar_questoes_ia(cliente_falso(resposta), "ganho médio diário de bovinos", "Iniciante", 5,
                             ["multipla_escolha", "verdadeiro_falso"], area="pecuaria", categoria="Pecuária")
    assert len(g.questoes) == 1 and g.descartadas == 1
    assert g.questoes[0]["referencias"][0]["titulo"].startswith("Ganho médio diário")
    with pytest.raises(ValueError):
        av.gerar_questoes_ia(cliente_falso(resposta), "bitcoin blockchain criptomoeda", "Iniciante", 3, area="pecuaria")


def test_correcao_aberta_usa_a_ia_e_nao_simula_quando_indisponivel(edu_dados):
    q = {"tipo": "estudo_de_caso", "enunciado": "Caso hipotético...", "resposta": "Pontos esperados", "explicacao": "x",
         "justificativa": "y", "assuntos": ["Custos"]}
    c = av.corrigir(q, "Minha resposta", cliente_falso('{"pontuacao": 0.8, "feedback": "Bom", "assuntos_para_revisar": []}'))
    assert c.correta and c.pontuacao == 0.8 and c.corrigida_por.startswith("IA")
    sem = ds.ClienteDeepSeek(ds.ConfigDeepSeek(api_key=""), sessao=SessaoFalsa(lambda *a: pytest.fail("chamou a API")))
    with pytest.raises(ds.IANaoConfigurada):
        av.corrigir(q, "Minha resposta", sem)


# ---------------------------------------------------------------- biblioteca (RAG por trechos)
def _pdf(paginas: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for texto in paginas:
        y = 800
        for linha in texto.split("\n"):
            c.drawString(50, y, linha)
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


def test_biblioteca_extrai_por_pagina_e_cita_documento_e_pagina(edu_dados):
    pdf = _pdf(["Apostila de pastagens - introducao geral ao manejo de pastagens tropicais.",
                "Capitulo 2. O capim-marandu e uma forrageira tropical usada na recria.\nA altura de entrada recomendada "
                "pelo material e de 30 a 35 cm para o pastejo rotacionado.",
                "Capitulo 3. Suplementacao mineral do rebanho na estacao seca."])
    res = bib.cadastrar_documento("apostila.pdf", pdf, "Apostila de pastagens", "Apostila", "Pecuária", instituicao="Curso X",
                                  ano="2024")
    assert res.status == "indexado" and res.paginas == 3 and res.trechos == 3
    assert (arm.pasta_biblioteca()).exists() and any(arm.pasta_biblioteca().iterdir())
    dup = bib.cadastrar_documento("copia.pdf", pdf, "Outra", "Apostila", "Pecuária")
    assert dup.status == "duplicado"
    busca = kr.buscar("altura de entrada do capim-marandu", usar_bancos=False)
    assert busca.referencias and busca.referencias[0].rotulo == "D1"
    d1 = busca.referencias[0]
    assert d1.titulo == "Apostila de pastagens" and d1.pagina == "2" and "30 a 35 cm" in d1.texto
    assert "Apostila de pastagens" in kr.formatar_contexto(busca) and "p. 2" in kr.formatar_contexto(busca)
    bib.excluir_documento(res.documento_id)
    assert kr.buscar("altura de entrada do capim-marandu", usar_bancos=False).vazio


def test_biblioteca_valida_formato_metadados_e_pdf_sem_texto(edu_dados):
    with pytest.raises(ValueError):
        bib.cadastrar_documento("planilha.xlsx", b"x", "T", "Apostila", "Pecuária")
    with pytest.raises(ValueError):
        bib.cadastrar_documento("a.txt", b"texto", "T", "Tipo inexistente", "Pecuária")
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(10, 10, 100, 100)
    c.showPage()
    c.save()
    res = bib.cadastrar_documento("imagem.pdf", buf.getvalue(), "Digitalizado", "PDF", "Solo")
    assert res.status == "sem_texto" and "digitalizado" in res.mensagem
    txt = bib.cadastrar_documento("guia.md", ("# Guia\n\n" + "Calagem eleva o pH do solo. " * 80).encode(), "Guia de calagem",
                                  "Guia de estudo", "Solo")
    assert txt.status == "indexado" and txt.trechos >= 2


def test_trechos_nao_misturam_paginas():
    trechos = bib.dividir_em_trechos([(1, "a" * 50 + ". " + "b" * 2000), (2, "c" * 100)])
    assert {p for p, _ in trechos} == {1, 2} and all(len(t) <= bib.TAMANHO_TRECHO for _, t in trechos)


# ---------------------------------------------------------------- progresso
def test_indicadores_de_progresso(bancos, edu_dados):
    u = arm.obter_ou_criar_usuario("Pedro")
    assert pg.resumo(u["id"])["exercicios"] == 0 and pg.assuntos_para_revisar(u["id"]) == []
    for sem in range(3):
        q = ec.gerar("GMD", sem)
        av.registrar_avaliacao(u["id"], "Treino GMD", [(q, av.corrigir(q, q["resposta"].split()[0]))], categoria="Pecuária")
    q = ec.gerar("V", 1)
    av.registrar_avaliacao(u["id"], "Treino V%", [(q, av.corrigir(q, "0"))], categoria="Agricultura")
    r = pg.resumo(u["id"])
    assert r["exercicios"] == 4 and r["avaliacoes"] == 4 and r["acertos_pct"] == 75.0
    cat = pg.por_categoria(u["id"]).set_index("Categoria")
    assert cat.loc["Pecuária", "Acertos (%)"] == 100.0 and cat.loc["Agricultura", "Acertos (%)"] == 0.0
    assert pg.assuntos_para_revisar(u["id"]) == ["Saturação por bases (V%)"]
    assert len(pg.historico(u["id"])) == 4 and not pg.notas(u["id"]).empty
    outro = arm.obter_ou_criar_usuario("Outra pessoa")
    assert pg.resumo(outro["id"])["exercicios"] == 0, "o progresso é individual por perfil"
