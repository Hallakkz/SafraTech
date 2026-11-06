"""Camada de comunicação com a DeepSeek: configuração pelo .env, segurança da chave, erros, novas tentativas, limites e
streaming. (Usa uma sessão HTTP falsa só para provocar cada situação de erro; o teste real da API está em
tests/validar_deepseek.py.)"""
import re
from pathlib import Path

import pytest

from conftest import RAIZ
from fake_deepseek import ErroDeConexao, ReadTimeout, RespostaFalsa, SessaoFalsa, erro, resposta_chat, resposta_stream
from modules.eduagro_ai import deepseek_client as ds

CHAVE_TESTE = "sk-teste-0123456789abcdef0123456789"
ARQS_APP = [p for p in RAIZ.rglob("*.py") if "tests" not in p.parts
            and not any(x.lower().replace("_", " ").startswith("banco de dados") for x in p.parts)]


@pytest.fixture
def cfg():
    return ds.ConfigDeepSeek(api_key=CHAVE_TESTE, base_url="https://api.deepseek.com", modelo="deepseek-chat",
                             timeout_s=30, max_req_min=50)


def cliente(cfg, roteiro, **kw):
    sessao = SessaoFalsa(roteiro)
    return ds.ClienteDeepSeek(cfg, sessao=sessao, dormir=lambda s: None, **kw), sessao


# ---------------------------------------------------------------- configuração e segurança
def test_configuracao_vem_das_variaveis_de_ambiente(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", CHAVE_TESTE)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    c = ds.carregar_config()
    assert c.api_key == CHAVE_TESTE and c.base_url == "https://api.deepseek.com" and c.modelo == "deepseek-chat"
    assert CHAVE_TESTE not in repr(c) and CHAVE_TESTE not in c.descricao()


def test_sem_chave_ia_nao_configurada(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(ds, "_segredos", {})
    c = ds.ClienteDeepSeek(ds.carregar_config(), sessao=SessaoFalsa(lambda *a: pytest.fail("não deveria chamar a API")))
    assert not c.configurado
    with pytest.raises(ds.IANaoConfigurada):
        c.conversar([{"role": "user", "content": "oi"}])
    st = c.testar_conexao()
    assert not st.disponivel and st.codigo == "nao_configurada"


def test_nenhuma_chave_no_codigo_nem_no_env_example():
    padrao = re.compile(r"sk-[A-Za-z0-9]{20,}")
    for p in ARQS_APP + [RAIZ / ".env.example", RAIZ / "README.md"]:
        assert not padrao.search(p.read_text(encoding="utf-8")), p
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^DEEPSEEK_API_KEY=\s*$", exemplo, re.M)
    assert "DEEPSEEK_BASE_URL=https://api.deepseek.com" in exemplo and "DEEPSEEK_MODEL=deepseek-chat" in exemplo
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()


def test_chave_so_no_cabecalho_e_nunca_nas_mensagens_de_erro(cfg):
    c, s = cliente(cfg, lambda m, u, j: erro(401, f"Authentication Fails, key {CHAVE_TESTE} invalid"))
    with pytest.raises(ds.IAChaveInvalida) as e:
        c.conversar([{"role": "user", "content": "oi"}])
    assert s.chamadas[0]["headers"]["Authorization"] == f"Bearer {CHAVE_TESTE}"
    assert CHAVE_TESTE not in str(e.value) and CHAVE_TESTE not in e.value.detalhe and "***" in e.value.detalhe
    assert s.chamadas[0]["url"] == "https://api.deepseek.com/chat/completions"


def test_chamada_vai_pelo_backend_com_modelo_do_env(cfg):
    c, s = cliente(cfg, lambda m, u, j: resposta_chat("Olá!"))
    r = c.conversar([{"role": "user", "content": "oi"}], temperatura=0.2, max_tokens=50)
    assert r.texto == "Olá!" and r.tokens_saida == 20
    corpo = s.chamadas[0]["json"]
    assert corpo["model"] == "deepseek-chat" and corpo["max_tokens"] == 50 and corpo["stream"] is False


# ---------------------------------------------------------------- erros da API
@pytest.mark.parametrize("status,classe", [(401, ds.IAChaveInvalida), (402, ds.IASemSaldo), (400, ds.IARequisicaoInvalida),
                                          (422, ds.IARequisicaoInvalida)])
def test_erros_definitivos_nao_repetem(cfg, status, classe):
    c, s = cliente(cfg, lambda m, u, j: erro(status))
    with pytest.raises(classe) as e:
        c.conversar([{"role": "user", "content": "oi"}])
    assert len(s.chamadas) == 1
    assert e.value.mensagem_usuario and e.value.status_http == status


def test_sem_saldo_tem_mensagem_clara(cfg):
    c, _ = cliente(cfg, lambda m, u, j: erro(402, "Insufficient Balance"))
    with pytest.raises(ds.IASemSaldo) as e:
        c.conversar([{"role": "user", "content": "oi"}])
    assert "sem saldo" in e.value.mensagem_usuario.lower()


def test_servidor_sobrecarregado_repete_e_recupera(cfg):
    respostas = iter([erro(503, "Server Overloaded"), erro(500), resposta_chat("ok")])
    c, s = cliente(cfg, lambda m, u, j: next(respostas))
    assert c.conversar([{"role": "user", "content": "oi"}]).texto == "ok"
    assert len(s.chamadas) == 3


def test_servidor_indisponivel_apos_tentativas(cfg):
    c, s = cliente(cfg, lambda m, u, j: erro(503))
    with pytest.raises(ds.IAIndisponivel):
        c.conversar([{"role": "user", "content": "oi"}])
    assert len(s.chamadas) == ds.ClienteDeepSeek.TENTATIVAS


def test_limite_da_api_429_respeita_retry_after(cfg):
    esperas = []
    respostas = iter([erro(429, "Rate Limit Reached", {"Retry-After": "3"}), resposta_chat("ok")])
    c = ds.ClienteDeepSeek(cfg, sessao=SessaoFalsa(lambda m, u, j: next(respostas)), dormir=esperas.append)
    assert c.conversar([{"role": "user", "content": "oi"}]).texto == "ok"
    assert esperas == [3.0]


def test_tempo_esgotado_e_sem_conexao(cfg):
    c, _ = cliente(cfg, lambda m, u, j: ReadTimeout("read timed out"))
    with pytest.raises(ds.IATempoEsgotado):
        c.conversar([{"role": "user", "content": "oi"}])
    c, _ = cliente(cfg, lambda m, u, j: ErroDeConexao("Name or service not known"))
    with pytest.raises(ds.IASemConexao):
        c.conversar([{"role": "user", "content": "oi"}])


def test_resposta_vazia_ou_malformada(cfg):
    c, _ = cliente(cfg, lambda m, u, j: RespostaFalsa(200, {"inesperado": True}))
    with pytest.raises(ds.IARespostaInvalida):
        c.conversar([{"role": "user", "content": "oi"}])
    c, _ = cliente(cfg, lambda m, u, j: resposta_chat("   "))
    with pytest.raises(ds.IARespostaInvalida):
        c.conversar([{"role": "user", "content": "oi"}])


def test_limite_local_de_requisicoes_por_minuto(cfg):
    relogio = [0.0]
    lim = ds.LimitadorRequisicoes(2, relogio=lambda: relogio[0])
    c, s = cliente(cfg, lambda m, u, j: resposta_chat("ok"), limitador=lim)
    c.conversar([{"role": "user", "content": "1"}])
    c.conversar([{"role": "user", "content": "2"}])
    with pytest.raises(ds.IALimiteRequisicoes) as e:
        c.conversar([{"role": "user", "content": "3"}])
    assert len(s.chamadas) == 2 and "Aguarde" in e.value.mensagem_usuario
    relogio[0] = 61
    assert c.conversar([{"role": "user", "content": "4"}]).texto == "ok"


# ---------------------------------------------------------------- streaming, JSON e diagnóstico
def test_streaming_monta_o_texto_e_registra_uso(cfg):
    c, s = cliente(cfg, lambda m, u, j: resposta_stream(["Olá, ", "produtor", "!"]))
    partes = list(c.conversar_stream([{"role": "user", "content": "oi"}]))
    assert "".join(partes) == "Olá, produtor!" and s.chamadas[0]["json"]["stream"] is True
    assert c.ultima_resposta.motivo_fim == "stop" and c.ultima_resposta.tokens_saida == 3


def test_streaming_interrompido_vira_erro_claro(cfg):
    class Quebrada(RespostaFalsa):
        def iter_lines(self, decode_unicode=False):
            yield 'data: {"choices":[{"delta":{"content":"parte"}}]}'
            raise ErroDeConexao("Connection broken")
    c, _ = cliente(cfg, lambda m, u, j: Quebrada(200))
    with pytest.raises(ds.IASemConexao):
        list(c.conversar_stream([{"role": "user", "content": "oi"}]))


def test_modo_json(cfg):
    c, s = cliente(cfg, lambda m, u, j: resposta_chat('{"questoes": []}'))
    assert c.conversar_json([{"role": "user", "content": "json"}]) == {"questoes": []}
    assert s.chamadas[0]["json"]["response_format"] == {"type": "json_object"}
    c, _ = cliente(cfg, lambda m, u, j: resposta_chat("não é json"))
    with pytest.raises(ds.IARespostaInvalida):
        c.conversar_json([{"role": "user", "content": "json"}])


def test_testar_conexao_detecta_saldo_e_indisponibilidade(cfg):
    c, _ = cliente(cfg, lambda m, u, j: RespostaFalsa(200, {"is_available": False, "balance_infos": [
        {"currency": "USD", "total_balance": "0.00"}]}))
    st = c.testar_conexao()
    assert not st.disponivel and st.codigo == "sem_saldo" and st.saldo == "0.00 USD"

    def roteiro(m, u, j):
        if u.endswith("/user/balance"):
            return RespostaFalsa(200, {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "5.00"}]})
        return resposta_chat("OK")
    c, s = cliente(cfg, roteiro)
    st = c.testar_conexao(com_chat=True)
    assert st.disponivel and st.detalhes["resposta_teste"] == "OK" and [x["metodo"] for x in s.chamadas] == ["GET", "POST"]
    c, _ = cliente(cfg, lambda m, u, j: erro(401))
    st = c.testar_conexao()
    assert not st.disponivel and st.codigo == "chave_invalida"


def test_script_de_validacao_real_existe_e_nao_simula():
    t = (RAIZ / "tests" / "validar_deepseek.py").read_text(encoding="utf-8")
    assert "obter_cliente" in t and "SessaoFalsa" not in t and "fake_deepseek" not in t
