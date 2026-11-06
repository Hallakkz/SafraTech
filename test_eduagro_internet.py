"""Busca na internet do Tutor Agro: só é usada quando os bancos do SafraTech e a Biblioteca não têm a informação
(ou quando o estudante pede). A API do Tavily é substituída por uma sessão HTTP falsa apenas nestes testes; o teste real
está em tests/validar_deepseek.py."""
import json

import pytest
import requests

from conftest import MAIN
from fake_deepseek import ErroDeConexao, RespostaFalsa, SessaoFalsa, erro, resposta_chat
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai import tutor
from modules.eduagro_ai import web_search as ws
from stub_streamlit import AppSimulado

CHAVE = "tvly-teste-0123456789abcdef0123456789"
PAGINAS = {"results": [
    {"title": "Bitcoin hoje", "url": "https://www.exemplo-financas.com/btc", "content": "A cotação do bitcoin hoje é X.", "score": 0.9},
    {"title": "Sem link válido", "url": "javascript:alert(1)", "content": "ignorar", "score": 0.5},
    {"title": "Embrapa — notícia", "url": "https://www.embrapa.br/noticia", "content": "Conteúdo técnico da Embrapa.", "score": 0.8}]}


def cliente(roteiro, **kw):
    sessao = SessaoFalsa(roteiro)
    cfg = ws.ConfigBusca(api_key=CHAVE, max_resultados=5, max_req_min=50, **kw)
    return ws.ClienteBusca(cfg, sessao=sessao, dormir=lambda s: None), sessao


# ---------------------------------------------------------------- cliente Tavily
def test_configuracao_pelo_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", CHAVE)
    monkeypatch.delenv("EDUAGRO_BUSCA_INTERNET", raising=False)
    c = ws.carregar_config()
    assert c.disponivel and CHAVE not in repr(c) and CHAVE not in c.descricao()
    monkeypatch.setenv("EDUAGRO_BUSCA_INTERNET", "0")
    assert not ws.carregar_config().disponivel
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setattr(ws, "_segredos", {})
    assert not ws.carregar_config().disponivel


def test_busca_retorna_paginas_com_link(monkeypatch):
    c, s = cliente(lambda m, u, j: RespostaFalsa(200, PAGINAS))
    r = c.buscar("  cotação   do bitcoin  ")
    assert [p.url for p in r] == ["https://www.exemplo-financas.com/btc", "https://www.embrapa.br/noticia"]
    assert r[1].site == "embrapa.br"
    ch = s.chamadas[0]
    assert ch["url"] == ws.URL_BUSCA and ch["json"]["query"] == "cotação do bitcoin" and ch["json"]["search_depth"] == "basic"
    assert ch["headers"]["Authorization"] == f"Bearer {CHAVE}"


@pytest.mark.parametrize("status,classe", [(401, ws.BuscaChaveInvalida), (432, ws.BuscaCotaEsgotada),
                                          (433, ws.BuscaCotaEsgotada), (400, ws.ErroBusca)])
def test_erros_da_api(status, classe):
    c, s = cliente(lambda m, u, j: erro(status, f"falha {CHAVE}"))
    with pytest.raises(classe) as e:
        c.buscar("teste")
    assert CHAVE not in str(e.value) and CHAVE not in e.value.detalhe and len(s.chamadas) == 1


def test_erros_temporarios_repetem_uma_vez():
    respostas = iter([erro(500), RespostaFalsa(200, PAGINAS)])
    c, s = cliente(lambda m, u, j: next(respostas))
    assert len(c.buscar("x")) == 2 and len(s.chamadas) == 2
    c, s = cliente(lambda m, u, j: ErroDeConexao("sem rede"))
    with pytest.raises(ws.BuscaIndisponivel):
        c.buscar("x")
    c, s = cliente(lambda m, u, j: erro(429))
    with pytest.raises(ws.BuscaLimite):
        c.buscar("x")


def test_sem_chave_nao_chama_a_api():
    c = ws.ClienteBusca(ws.ConfigBusca(api_key=""), sessao=SessaoFalsa(lambda *a: pytest.fail("chamou a API")))
    with pytest.raises(ws.BuscaNaoConfigurada):
        c.buscar("x")


# ---------------------------------------------------------------- ordem das fontes no tutor
@pytest.fixture
def base(bancos):
    kr.invalidar_bancos()
    yield
    kr.invalidar_bancos()


def test_achou_nos_bancos_nao_pesquisa_na_internet(base, edu_dados):
    c, s = cliente(lambda *a: pytest.fail("não deveria pesquisar na internet"))
    p = tutor.preparar("Como calcular o ganho médio diário de um bovino?", "Iniciante", [], cliente_busca=c)
    assert p.busca.do_banco and not p.busca.da_internet and not s.chamadas
    assert "[W1]" not in p.mensagens[-1]["content"]


def test_nao_achou_nos_bancos_pesquisa_na_internet(base, edu_dados):
    c, s = cliente(lambda m, u, j: RespostaFalsa(200, PAGINAS))
    p = tutor.preparar("Qual a cotação do bitcoin hoje?", "Iniciante", [], cliente_busca=c)
    assert len(s.chamadas) == 1 and [r.rotulo for r in p.busca.da_internet] == ["W1", "W2"]
    ctx = p.mensagens[-1]["content"]
    assert "ATENÇÃO: nada foi encontrado nos bancos do SafraTech" in ctx and "Endereço: https://www.embrapa.br/noticia" in ctx
    assert any("Nada encontrado nos bancos do SafraTech" in a and "🔗 2 página(s)" in a for a in p.avisos)
    cit = tutor.verificar_citacoes("Segundo embrapa.br [W2] e [W7].", p.busca)
    assert cit["citadas"] == ["W2"] and cit["invalidas"] == ["W7"]
    assert "🔗 O que a internet informa" in p.mensagens[0]["content"]


def test_pedido_explicito_de_internet_complementa_os_bancos(base, edu_dados):
    c, s = cliente(lambda m, u, j: RespostaFalsa(200, PAGINAS))
    p = tutor.preparar("", "Iniciante", [], modo="internet", consulta_anterior="Como funciona o rendimento de carcaça?",
                       cliente_busca=c)
    assert p.busca.do_banco and p.busca.da_internet and len(s.chamadas) == 1
    assert s.chamadas[0]["json"]["query"] == "Como funciona o rendimento de carcaça?"
    assert "ATENÇÃO" not in p.mensagens[-1]["content"], "os bancos foram encontrados: a internet só complementa"


def test_falha_da_internet_nao_derruba_o_tutor(base, edu_dados):
    c, _ = cliente(lambda m, u, j: erro(432, "Plan limit"))
    p = tutor.preparar("Qual a cotação do bitcoin hoje?", "Iniciante", [], cliente_busca=c)
    assert not p.busca.referencias and any("cota de buscas do Tavily acabou" in a for a in p.avisos)
    assert "NENHUMA referência" in p.mensagens[-1]["content"]
    sem = ws.ClienteBusca(ws.ConfigBusca(api_key=""), sessao=SessaoFalsa(lambda *a: pytest.fail("chamou")))
    p = tutor.preparar("Qual a cotação do bitcoin hoje?", "Iniciante", [], cliente_busca=sem)
    assert any("busca na internet não está configurada" in a for a in p.avisos)


# ---------------------------------------------------------------- no aplicativo
@pytest.fixture
def api_web(monkeypatch, edu_dados):
    chamadas = []

    def roteiro(m, u, j):
        chamadas.append(u)
        if "tavily" in u:
            return RespostaFalsa(200, PAGINAS)
        if j and j.get("stream"):
            from fake_deepseek import resposta_stream
            return resposta_stream(["### 🔗 O que a internet informa\nSegundo embrapa.br [W2]..."])
        return resposta_chat("OK")
    sessao = SessaoFalsa(roteiro)
    monkeypatch.setattr(requests, "Session", lambda: sessao)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-teste-ui-0000000000000000000000")
    monkeypatch.setenv("TAVILY_API_KEY", CHAVE)
    monkeypatch.delenv("EDUAGRO_BUSCA_INTERNET", raising=False)
    monkeypatch.setenv("EDUAGRO_FONTE_TUTOR", "bancos")
    return sessao


def _tutor():
    app = AppSimulado().executar(MAIN)
    app.interagir(MAIN, "nav_agricultura", 4)
    return app


def test_app_usa_internet_so_quando_os_bancos_nao_tem(bancos, api_web):
    app = _tutor()
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o ganho médio diário de um bovino?"})
    assert not [c for c in api_web.chamadas if "tavily" in c["url"]]
    assert any(w[2] == "edu_buscar_internet" for w in app.widgets), "botão para pedir a internet aparece"
    app.executar(MAIN, valores={"edu_chat_input": "Qual a cotação do bitcoin hoje?"})
    web = [c for c in api_web.chamadas if "tavily" in c["url"]]
    assert len(web) == 1 and CHAVE not in json.dumps([c["json"] for c in api_web.chamadas if "deepseek" in c["url"]])
    assert any('href="https://www.embrapa.br/noticia"' in t for t in app.textos("markdown"))
    assert any("Nada encontrado nos bancos do SafraTech" in t for t in app.textos("caption"))
    assert not any(w[2] == "edu_buscar_internet" for w in app.widgets), "já usou a internet: sem botão"
    from modules.eduagro_ai import armazenamento as arm
    assert arm.consultar("SELECT count(*) AS n FROM evento WHERE tipo = 'busca_internet'")[0]["n"] == 1


def test_app_botao_procurar_na_internet(bancos, api_web):
    app = _tutor()
    app.executar(MAIN, valores={"edu_chat_input": "Como funciona o rendimento de carcaça?"})
    app.executar(MAIN, botoes={"edu_buscar_internet"})
    web = [c for c in api_web.chamadas if "tavily" in c["url"]]
    assert len(web) == 1 and web[0]["json"]["query"] == "Como funciona o rendimento de carcaça?"
    ultima = [c for c in api_web.chamadas if c["json"] and c["json"].get("stream")][-1]["json"]["messages"][-1]["content"]
    assert "[S1]" in ultima and "[W1]" in ultima


def test_status_da_busca_na_barra_lateral(bancos, api_web):
    app = _tutor()
    assert app.contem("🟢 Configurada", "markdown")
    app.executar(MAIN, botoes={"edu_testar_busca"})
    assert app.contem("Busca na internet funcionando (2 páginas)", "success")


def test_nenhuma_chave_do_tavily_no_codigo():
    import re
    from conftest import RAIZ
    arqs = [p for p in RAIZ.rglob("*.py") if "tests" not in p.parts
            and not any(x.lower().replace("_", " ").startswith("banco de dados") for x in p.parts)]
    for p in arqs + [RAIZ / ".env.example", RAIZ / "README.md"]:
        assert not re.search(r"tvly-[A-Za-z0-9]{10,}", p.read_text(encoding="utf-8")), p
    assert re.search(r"^TAVILY_API_KEY=\s*$", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M)



# ---------------------------------------------------------------- modo "somente internet" (padrão)
def test_fonte_padrao_e_internet(monkeypatch):
    monkeypatch.delenv("EDUAGRO_FONTE_TUTOR", raising=False)
    assert tutor.fonte_padrao() == "internet"
    monkeypatch.setenv("EDUAGRO_FONTE_TUTOR", "bancos")
    assert tutor.fonte_padrao() == "bancos"
    monkeypatch.setenv("EDUAGRO_FONTE_TUTOR", "qualquer")
    assert tutor.fonte_padrao() == "internet"


def test_somente_internet_nao_consulta_os_bancos(base, edu_dados, monkeypatch):
    monkeypatch.setattr(kr, "buscar", lambda *a, **k: pytest.fail("não deveria consultar os bancos"))
    c, s = cliente(lambda m, u, j: RespostaFalsa(200, PAGINAS))
    p = tutor.preparar("Como calcular o ganho médio diário de um bovino?", "Iniciante", [], cliente_busca=c, fonte="internet")
    assert len(s.chamadas) == 1 and not p.busca.do_banco and [r.rotulo for r in p.busca.da_internet] == ["W1", "W2"]
    ctx = p.mensagens[-1]["content"]
    assert "MODO SOMENTE INTERNET" in ctx and "[W1]" in ctx and "[S1]" not in ctx and "ATENÇÃO: nada foi encontrado" not in ctx
    assert not any("internet" in a for a in p.avisos)


def test_somente_internet_sem_chave_avisa(base, edu_dados):
    sem = ws.ClienteBusca(ws.ConfigBusca(api_key=""), sessao=SessaoFalsa(lambda *a: pytest.fail("chamou")))
    p = tutor.preparar("Como calcular o GMD?", "Iniciante", [], cliente_busca=sem, fonte="internet")
    assert not p.busca.referencias and any("não está configurada" in a for a in p.avisos)
    assert "NENHUMA referência" in p.mensagens[-1]["content"]


def test_app_padrao_responde_so_com_a_internet(bancos, api_web, monkeypatch):
    monkeypatch.delenv("EDUAGRO_FONTE_TUTOR", raising=False)
    app = _tutor()
    radio = [w for w in app.widgets if w[2] == "edu_tutor_fonte"][0]
    assert app.session_state["edu_tutor_fonte"] == "internet" and radio[3] == ["internet", "bancos"]
    assert not any(w[2] == "edu_tutor_area" for w in app.widgets)
    app.executar(MAIN, valores={"edu_chat_input": "Como calcular o ganho médio diário de um bovino?"})
    web = [c for c in api_web.chamadas if "tavily" in c["url"]]
    assert len(web) == 1 and web[0]["json"]["query"] == "Como calcular o ganho médio diário de um bovino?"
    ultima = [c for c in api_web.chamadas if c["json"] and c["json"].get("stream")][-1]["json"]["messages"][-1]["content"]
    assert "MODO SOMENTE INTERNET" in ultima and "[W1]" in ultima and "[S1]" not in ultima
    assert any('href="https://www.embrapa.br/noticia"' in t for t in app.textos("markdown"))
    assert not any(w[2] == "edu_buscar_internet" for w in app.widgets)
    # o estudante pode voltar a usar os bancos do SafraTech
    app.interagir(MAIN, "edu_tutor_fonte", "bancos")
    assert any(w[2] == "edu_tutor_area" for w in app.widgets)
