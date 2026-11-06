"""EduAgro AI no aplicativo (Streamlit simulado executando o main.py de verdade): menu, áreas, tutor, exercícios,
biblioteca, progresso, erros da IA e preservação dos demais módulos.

A API da DeepSeek é substituída por uma sessão HTTP falsa SOMENTE nestes testes de interface (para não gastar créditos
e para provocar erros). A validação real da integração é feita por tests/validar_deepseek.py."""
import ast
import io
import json
import re
from pathlib import Path

import pytest
import requests

from conftest import MAIN, RAIZ
from fake_deepseek import RespostaFalsa, SessaoFalsa, erro, resposta_chat, resposta_stream
from stub_streamlit import AppSimulado

RESPOSTA_TUTOR = ("### 📚 O que os bancos do SafraTech informam\nA fórmula do GMD é (peso final − peso inicial) ÷ dias [S1].\n\n"
                  "### 🧠 Explicação do tutor (IA)\nO GMD mostra quanto o animal ganha por dia. A fórmula: \\( GMD = \\frac{PF - PI}{d} \\)\n\n"
                  "### 🧮 Exemplo hipotético (somente para ensinar)\n1. Ganho = 300 − 240 = 60 kg\n2. GMD = 60 ÷ 100 = 0,6 kg/dia\n\n"
                  "### ✅ Verifique seu aprendizado\n1. O que acontece com o GMD se o período dobrar? [S9]")


class Roteiro:
    """Respostas da API falsa, por tipo de chamada."""

    def __init__(self):
        self.stream = lambda corpo: resposta_stream([RESPOSTA_TUTOR[i:i + 40] for i in range(0, len(RESPOSTA_TUTOR), 40)])
        self.json = lambda corpo: resposta_chat('{"questoes": []}')
        self.saldo = lambda: RespostaFalsa(200, {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "9.99"}]})
        self.web = lambda corpo: RespostaFalsa(200, {"results": []})

    def __call__(self, metodo, url, corpo):
        if "tavily" in url:
            return self.web(corpo)
        if url.endswith("/user/balance"):
            return self.saldo()
        if corpo.get("stream"):
            return self.stream(corpo)
        if corpo.get("response_format"):
            return self.json(corpo)
        return resposta_chat("OK")


@pytest.fixture
def api(monkeypatch, edu_dados):
    roteiro = Roteiro()
    sessao = SessaoFalsa(roteiro)
    monkeypatch.setattr(requests, "Session", lambda: sessao)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-teste-ui-0000000000000000000000")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("TAVILY_API_KEY", "")   # vazio: o .env real não é usado; os testes da internet ligam explicitamente
    monkeypatch.setenv("EDUAGRO_FONTE_TUTOR", "bancos")   # estes testes cobrem o modo com os bancos do SafraTech
    sessao.roteiro_obj = roteiro
    return sessao


def eduagro(secao: int = 0, valores=None) -> AppSimulado:
    app = AppSimulado(valores=valores).executar(MAIN)
    app.interagir(MAIN, "nav_agricultura", 4)
    if secao:
        app.interagir(MAIN, "edu_secao", secao)
    return app


def _menus():
    arv = ast.parse(Path(MAIN).read_text(encoding="utf-8"))
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.walk(arv)
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("MENU_AGRICULTURA", "MENU_PECUARIA")}


# ---------------------------------------------------------------- menu e estrutura
def test_menu_principal_com_cinco_modulos():
    m = _menus()
    assert m["MENU_AGRICULTURA"] == ["🧪 Diagnóstico do Solo", "🍃 Diagnóstico Nutricional", "🗓️ Simulação de Plantio",
                                     "🐂 Pecuária", "🎓 EduAgro AI"]
    assert "🌱 Agricultura" in m["MENU_PECUARIA"] and len(m["MENU_PECUARIA"]) == 4
    assert not any("Recomenda" in x or "Idioma" in x for x in m["MENU_AGRICULTURA"])


def test_destaque_visual_e_estrutura_modular():
    texto = Path(MAIN).read_text(encoding="utf-8")
    assert "CSS_MENU_DESTAQUE" in texto and "eduagro.render()" in texto
    pasta = RAIZ / "modules" / "eduagro_ai"
    for nome in ("__init__.py", "interface.py", "tutor.py", "cursos.py", "biblioteca.py", "avaliacoes.py", "progresso.py",
                 "deepseek_client.py", "knowledge_retrieval.py", "prompts.py"):
        assert (pasta / nome).exists(), nome
    assert "requests" not in texto and "deepseek" not in texto.lower().replace("eduagro", "")


def test_eduagro_abre_com_as_cinco_areas(bancos, api):
    app = eduagro()
    assert app.contem("EduAgro AI — o tutor inteligente", "header") and not app.textos("error")
    nav = [w for w in app.widgets if w[2] == "edu_secao"][0]
    assert nav[3] == [0, 1, 2]
    menu = [w for w in app.widgets if w[2] == "nav_agricultura"][0]
    assert menu[3] == [0, 1, 2, 3, 4]
    for secao in range(3):
        app.interagir(MAIN, "edu_secao", secao)
        assert not app.textos("error"), (secao, app.textos("error"))


INGLES = re.compile(r"\b(Soil|Livestock|Language|Settings|Analyze|Download|Report|Upload|Library|Course|Courses|Lesson|"
                    r"Exercise|Quiz|Progress|Score|Submit|Send|Chat|New|Delete|Search|Sources|Results|Generate|Value)\b")


def test_interface_do_eduagro_em_portugues(bancos, api):
    for secao in range(3):
        app = eduagro(secao)
        rotulos = [str(w[1]) for w in app.widgets] + [t for t in app.textos() if not t.lstrip().startswith("<style")]
        achados = sorted({m.group(0) for t in rotulos for m in [INGLES.search(t)] if m})
        assert not achados, (secao, achados)


def test_outros_modulos_continuam_funcionando_depois_do_eduagro(bancos, api):
    app = eduagro(1)
    app.interagir(MAIN, "nav_agricultura", 0)
    assert app.contem("Diagnóstico do Solo", "header") and not app.textos("error")
    app.interagir(MAIN, "nav_agricultura", 3)
    assert app.session_state["area"] == "pecuaria" and app.contem("Análise de Viabilidade de Compra", "header")
    app.interagir(MAIN, "nav_pecuaria", 3)
    assert app.session_state["area"] == "agricultura"


# ---------------------------------------------------------------- tutor
def test_tutor_responde_com_bancos_e_salva_a_conversa(bancos, api):
    app = eduagro(0)
    assert sum(1 for w in app.widgets if w[0] == "button" and str(w[2]).startswith("edu_sug_")) == 8
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o ganho médio diário de um bovino?"})
    assert not app.textos("error"), app.textos("error")
    chamada = [c for c in api.chamadas if c["json"] and c["json"].get("stream")][0]
    msgs = chamada["json"]["messages"]
    assert msgs[0]["role"] == "system" and "Tutor Agro" in msgs[0]["content"] and "INICIANTE" in msgs[0]["content"]
    assert "[S1] Fórmula de cálculo — Ganho médio diário (GMD)" in msgs[-1]["content"]
    assert "pecuaria_desempenho_database" in msgs[-1]["content"]
    assert chamada["headers"]["Authorization"].startswith("Bearer sk-teste-ui")
    # depois do rerun: a conversa aparece do histórico, com fórmulas normalizadas, referências e alerta de citação inválida
    textos = app.textos("markdown")
    assert any("$GMD = \\frac{PF - PI}{d}$" in t for t in textos)
    assert app.contem("rótulos que não estavam nas referências entregues à IA: S9", "warning") and app.contem("📚 Referências consultadas", "expander")
    assert any("Sistema semi-intensivo de produção de carne" in t for t in textos)
    assert any(w[2] == "edu_mais_simples" for w in app.widgets) and any(w[2] == "edu_conv_1" for w in app.widgets)
    from modules.eduagro_ai import armazenamento as arm
    msgs_db = arm.consultar("SELECT papel, conteudo, referencias_json, meta_json FROM mensagem ORDER BY id")
    assert [m["papel"] for m in msgs_db] == ["user", "assistant"]
    meta = json.loads(msgs_db[1]["meta_json"])
    assert meta["citacoes"]["citadas"] == ["S1"] and meta["citacoes"]["invalidas"] == ["S9"] and meta["nivel"] == "Iniciante"
    refs = json.loads(msgs_db[1]["referencias_json"])
    assert refs[0]["bancos"] and refs[0]["fonte"] and refs[0]["rotulo"] == "S1"


def test_tutor_adapta_o_nivel_e_explica_mais_simples(bancos, api):
    app = eduagro(0, valores={"edu_nivel": "Avançado"})
    app.executar(MAIN, valores={"edu_chat_input": "Como funciona o rendimento de carcaça?"})
    primeira = [c for c in api.chamadas if c["json"] and c["json"].get("stream")][-1]["json"]["messages"]
    assert "AVANÇADO" in primeira[0]["content"]
    app.executar(MAIN, botoes={"edu_mais_simples"})
    ultima = [c for c in api.chamadas if c["json"] and c["json"].get("stream")][-1]["json"]["messages"]
    assert "MAIS SIMPLES" in ultima[-1]["content"] and ultima[1]["role"] == "user" and ultima[2]["role"] == "assistant"
    assert "RENDIMENTO_CARCACA" in ultima[-1]["content"], "a reformulação mantém o mesmo assunto na busca"


@pytest.mark.parametrize("status,trecho", [(402, "sem saldo"), (401, "chave"), (503, "indisponível"), (429, "Aguarde")])
def test_tutor_informa_ia_indisponivel_sem_simular(bancos, api, status, trecho):
    api.roteiro_obj.stream = lambda corpo: erro(status)
    app = eduagro(0)
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o GMD?"})
    erros = " ".join(app.textos("error"))
    assert "indisponível" in erros and trecho.lower() in erros.lower()
    from modules.eduagro_ai import armazenamento as arm
    assert arm.consultar("SELECT count(*) AS n FROM mensagem")[0]["n"] == 0, "nada é registrado como se a IA tivesse respondido"


def test_tutor_sem_chave_configurada(bancos, api, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    app = eduagro(0)
    assert app.contem("🔴 Não configurada", "markdown")
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o GMD?"})
    assert app.contem("DEEPSEEK_API_KEY", "error") and not api.chamadas


def test_teste_de_conexao_na_barra_lateral(bancos, api):
    app = eduagro(0)
    app.executar(MAIN, botoes={"edu_testar_ia"})
    assert app.contem("DeepSeek conectada e com saldo disponível", "success") and app.contem("9.99 USD", "caption")
    api.roteiro_obj.saldo = lambda: erro(402, "Insufficient Balance")
    app.executar(MAIN, botoes={"edu_testar_ia"})
    assert app.contem("sem saldo", "error")


# ---------------------------------------------------------------- exercícios e progresso
def test_treino_de_calculo_corrige_e_registra_progresso(bancos, api):
    app = eduagro(1)
    q = app.session_state["edu_calc_atual"]
    assert q["origem"] == "calculo_banco" and "pecuaria_desempenho_database" in q["justificativa"]
    chave = f"edu_calc_{app.session_state['edu_calc_seq']}"
    app.executar(MAIN, valores={f"{chave}_r0": q["resposta"].split()[0]}, botoes={"✅ Enviar respostas"})
    assert app.contem("Nota", "metric") or any(x[0] == "metric" and "100" in x[2] for x in app.saida)
    assert app.contem("Parabéns", "success")
    app.interagir(MAIN, "edu_secao", 2)
    assert any(x[0] == "metric" and x[1] == "Exercícios realizados" and x[2] == "1" for x in app.saida)


def test_exercicios_gerados_por_ia_com_correcao_e_revisao(bancos, api):
    api.roteiro_obj.json = lambda corpo: resposta_chat(json.dumps({"questoes": [
        {"tipo": "multipla_escolha", "enunciado": "Qual expressão calcula o GMD de um bovino?",
         "alternativas": ["Peso final / dias", "(Peso final − peso inicial) / dias", "Peso inicial × dias", "Dias / peso"],
         "resposta_correta": "B", "explicacao": "Diferença de peso dividida pelo período.",
         "justificativa_tecnica": "Fórmula GMD do banco [S1].", "referencias": ["S1"], "assuntos": ["Ganho médio diário"]},
        {"tipo": "verdadeiro_falso", "enunciado": "O GMD é expresso em kg por dia (kg/dia).", "resposta_correta": "Verdadeiro",
         "explicacao": "A unidade do resultado é kg/dia.", "justificativa_tecnica": "[S1]", "referencias": ["S1"],
         "assuntos": ["Unidades"]}]}, ensure_ascii=False))
    app = eduagro(1, valores={"edu_ia_tema": "ganho médio diário de bovinos", "edu_ia_cat": "Pecuária"})
    app.executar(MAIN, botoes={"🤖 Gerar exercícios"})
    assert not app.textos("error") and app.session_state["edu_ia_questoes"]["questoes"]
    pedido = [c for c in api.chamadas if c["json"] and c["json"].get("response_format")][-1]["json"]["messages"]
    assert "NUNCA diga ou sugira que são questões oficiais" in pedido[0]["content"]
    seq = app.session_state["edu_ia_seq"]
    app.executar(MAIN, valores={f"edu_ia_{seq}_r0": "A", f"edu_ia_{seq}_r1": "Verdadeiro"}, botoes={"✅ Enviar respostas"})
    res = app.session_state[f"edu_ia_{seq}_resultado"]["resumo"]
    assert res["nota"] == 50.0 and res["revisar"] == ["Ganho médio diário"]
    assert app.contem("Assuntos para estudar novamente", "warning") and app.contem("Resposta correta:** B)", "markdown")
    assert any("Gerada por IA para estudo" in t for t in app.textos())
    # o botão de revisão leva ao tutor com a pergunta pronta
    app.executar(MAIN, botoes={f"edu_ia_{seq}_revisar"})
    assert app.session_state["edu_secao"] == 0
    app.executar(MAIN)   # no Streamlit, o clique dispara uma nova execução já na área do Tutor
    assert any(c["json"] and c["json"].get("stream") and "Ganho médio diário" in c["json"]["messages"][-1]["content"]
               for c in api.chamadas)


def test_tutor_leva_o_assunto_para_os_exercicios(bancos, api):
    app = eduagro(0)
    app.executar(MAIN, valores={"edu_chat_input": "Como funciona o rendimento de carcaça?"})
    app.executar(MAIN, botoes={"edu_exercicios_assunto"})
    app.executar(MAIN)
    assert app.session_state["edu_secao"] == 1 and app.session_state["edu_ia_tema"] == "Como funciona o rendimento de carcaça?"


def test_eduagro_funciona_sem_bancos(api, monkeypatch):
    from database import connections
    connections.definir_executor_externo(None)
    connections.descartar_engines()
    for cfg in connections.BANCOS.values():
        monkeypatch.setenv(cfg["env"], "")
    monkeypatch.setattr(connections, "_segredos", {})
    app = eduagro(1)
    assert app.contem("bancos do SafraTech estão inacessíveis", "warning")
    app.interagir(MAIN, "edu_secao", 2)
    assert not [e for e in app.textos("error") if "EduAgro" in e]
    app.interagir(MAIN, "edu_secao", 0)
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o GMD?"})
    assert app.contem("Bancos indisponíveis nesta consulta", "caption")
    assert "NENHUMA referência" in [c for c in api.chamadas if c["json"] and c["json"].get("stream")][-1]["json"]["messages"][-1]["content"]
