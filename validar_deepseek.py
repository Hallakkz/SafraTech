"""
VALIDAÇÃO REAL da integração do EduAgro AI com a DeepSeek (não é um teste simulado).

Executa, com a chave do arquivo .env e os bancos reais do SafraTech:
  1. carga da configuração (sem exibir a chave);
  2. diagnóstico da conta (saldo) e uma chamada mínima ao modelo;
  3. perguntas reais ao Tutor Agro, com recuperação de referências nos bancos agrícolas e pecuários;
  4. geração real de exercícios a partir das referências;
  5. correção real de uma resposta aberta;
  6. tratamento de erro real (chave inválida → HTTP 401).

Uso (na pasta do projeto, com o ambiente virtual ativo):
    python tests/validar_deepseek.py
O resultado também é salvo em dados_eduagro/validacao_deepseek.md. Consome poucos créditos (alguns milhares de tokens).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
try:  # console do Windows: garante a saída dos acentos e emojis
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:
    print("Aviso: python-dotenv não instalado; usando apenas as variáveis de ambiente do sistema.")

from modules.eduagro_ai import avaliacoes as av            # noqa: E402
from modules.eduagro_ai import deepseek_client as ds        # noqa: E402
from modules.eduagro_ai import knowledge_retrieval as kr    # noqa: E402
from modules.eduagro_ai import tutor                        # noqa: E402
from modules.eduagro_ai import web_search as ws             # noqa: E402

PERGUNTAS = [
    ("Como interpretar o fósforo na análise de solo?", "solo_database"),
    ("Como calcular o ganho médio diário de um bovino?", "pecuaria_desempenho_database"),
    ("Como avaliar a rentabilidade de um lote de gado?", "pecuaria_"),
    ("O que é o Zoneamento Agrícola de Risco Climático?", "plantio_database"),
]
SECOES = ("O que os bancos do SafraTech informam", "Explicação do tutor", "Verifique seu aprendizado")

linhas: list[str] = []
falhas: list[str] = []


def log(t: str = "") -> None:
    print(t, flush=True)
    linhas.append(t)


def ok(cond: bool, descricao: str) -> bool:
    log(f"   {'✅' if cond else '❌'} {descricao}")
    if not cond:
        falhas.append(descricao)
    return cond


def main() -> int:
    log(f"# Validação real da DeepSeek — EduAgro AI ({datetime.now():%d/%m/%Y %H:%M})")
    cfg = ds.carregar_config()
    log("\n## 1. Configuração (.env)")
    log(f"   {cfg.descricao()}")
    if not ok(cfg.configurada, "DEEPSEEK_API_KEY carregada do .env"):
        return 1
    ok(cfg.api_key.startswith("sk-"), "formato da chave (prefixo sk-)")
    cliente = ds.obter_cliente()

    log("\n## 2. Conexão, saldo e chamada mínima ao modelo")
    st = cliente.testar_conexao(com_chat=True)
    log(f"   status: {st.mensagem} | saldo: {st.saldo} | detalhes: {st.detalhes}")
    if not ok(st.disponivel, "API acessível, conta com saldo e modelo respondendo"):
        log("   → A IA está indisponível: o EduAgro mostrará esta mesma mensagem ao usuário.")
        log("\n## 2b. Confirmação real do erro numa pergunta ao modelo")
        try:
            cliente.conversar([{"role": "user", "content": "Responda apenas: OK"}], max_tokens=5)
            ok(False, "a API respondeu, embora o diagnóstico tenha indicado indisponibilidade")
        except ds.ErroIA as e:
            log(f"   {type(e).__name__} (HTTP {e.status_http}): {e.mensagem_usuario}")
            log(f"   detalhe da API: {e.detalhe}")
            ok(e.codigo == st.codigo or isinstance(e, ds.IASemSaldo), "erro real da API tratado com a mensagem correta")
        _bancos_sem_ia()
        _chave_invalida(cfg)
        log("\n## Resultado: ❌ a integração está pronta, mas a DeepSeek não pode responder até o problema acima ser resolvido "
            "(as etapas 3 a 5 exigem resposta do modelo).")
        return 1

    log("\n## 3. Tutor Agro com os bancos do SafraTech (perguntas reais)")
    base = kr.carregar_base_bancos(forcar=True)
    log(f"   bancos consultáveis: {', '.join(base.disponiveis) or 'nenhum'}")
    if base.indisponiveis:
        log(f"   bancos indisponíveis: {base.indisponiveis}")
    ok(len(base.disponiveis) == 6, "os 6 bancos do SafraTech acessíveis pelo tutor")
    for pergunta, banco_esperado in PERGUNTAS:
        log(f"\n### {pergunta}")
        prep = tutor.preparar(pergunta, "Intermediário", [])
        refs = prep.busca.referencias
        log("   referências recuperadas: " + "; ".join(f"[{r.rotulo}] {r.titulo[:50]} ({r.bancos[0]})" for r in refs[:5]))
        ok(any(any(b.startswith(banco_esperado) for b in r.bancos) for r in refs), f"referência do banco {banco_esperado}*")
        t0 = time.monotonic()
        try:
            texto = "".join(tutor.responder_stream(cliente, prep))
        except ds.ErroIA as e:
            ok(False, f"resposta da DeepSeek ({e.mensagem_usuario} {e.detalhe})")
            continue
        dur = time.monotonic() - t0
        info = cliente.ultima_resposta
        cit = tutor.verificar_citacoes(texto, prep.busca)
        log(f"   resposta: {len(texto)} caracteres em {dur:.1f} s · tokens entrada/saída: {info.tokens_entrada}/{info.tokens_saida}")
        ok(all(s in texto for s in SECOES), "resposta organizada nas seções didáticas (bancos / explicação / verificação)")
        ok(bool(cit["citadas"]), f"cita referências reais do contexto: {cit['citadas']}")
        ok(not cit["invalidas"], f"nenhuma citação inexistente (inválidas: {cit['invalidas']})")
        trecho = texto[:700].replace("\n", "\n   > ")
        log(f"   > {trecho}…")

    _internet(cliente)

    log("\n## 4. Geração real de exercícios a partir dos bancos")
    try:
        g = av.gerar_questoes_ia(cliente, "rendimento de carcaça de bovinos", "Intermediário", 3,
                                 ["multipla_escolha", "verdadeiro_falso", "pratica"], area="pecuaria", categoria="Pecuária")
        ok(len(g.questoes) >= 1, f"{len(g.questoes)} questão(ões) válida(s) com referência real; {g.descartadas} descartada(s)")
        for q in g.questoes:
            log(f"   - [{q['tipo']}] {q['enunciado'][:120]} → resposta: {q['resposta'][:60]} · refs: "
                f"{[r['rotulo'] for r in q['referencias']]}")
    except (ds.ErroIA, ValueError) as e:
        ok(False, f"geração de exercícios: {getattr(e, 'mensagem_usuario', e)}")

    log("\n## 5. Correção real de resposta aberta")
    q = {"tipo": "estudo_de_caso", "enunciado": "Um boi com 500 kg de peso vivo gerou 270 kg de carcaça. Explique como calcular "
         "o rendimento de carcaça e qual o resultado.", "resposta": "Rendimento = 270/500 × 100 = 54%.",
         "justificativa": "Rendimento de carcaça = peso de carcaça ÷ peso vivo × 100.", "explicacao": "", "assuntos": ["Rendimento"]}
    try:
        c = av.corrigir(q, "Divide o peso da carcaça pelo peso vivo e multiplica por 100: 270/500 = 0,54, ou seja 54%.", cliente)
        ok(c.correta and c.pontuacao >= 0.7, f"resposta correta reconhecida (pontuação {c.pontuacao:.2f}) — {c.feedback[:120]}")
    except ds.ErroIA as e:
        ok(False, f"correção: {e.mensagem_usuario}")

    _chave_invalida(cfg)
    log(f"\n## Resultado: {'✅ APROVADO' if not falhas else '❌ ' + str(len(falhas)) + ' falha(s)'}")
    for f in falhas:
        log(f"   - {f}")
    return 0 if not falhas else 1


def _internet(cliente) -> None:
    log("\n## 3c. Busca na internet (Tavily)")
    cfg = ws.carregar_config()
    log(f"   {cfg.descricao()}")
    if not cfg.disponivel:
        log("   (TAVILY_API_KEY ausente: etapa ignorada)")
        return
    pergunta = "Como calcular o ganho médio diário de um bovino?"
    prep = tutor.preparar(pergunta, "Intermediário", [], fonte="internet")
    log(f"   [somente internet] “{pergunta}” → " + "; ".join(f"[{r.rotulo}] {r.fonte}" for r in prep.busca.da_internet))
    if ok(bool(prep.busca.da_internet) and not prep.busca.do_banco, "modo padrão “somente internet”: só páginas da internet"):
        try:
            texto = "".join(tutor.responder_stream(cliente, prep))
            cit = tutor.verificar_citacoes(texto, prep.busca)
            ok(any(c.startswith("W") for c in cit["citadas"]) and not cit["invalidas"]
               and not any(c.startswith("S") for c in cit["citadas"]),
               f"resposta cita só a internet: {cit['citadas']} (inválidas: {cit['invalidas']})")
            trecho = texto[:600].replace("\n", "\n   > ")
            log(f"   > {trecho}…")
        except ds.ErroIA as e:
            ok(False, f"resposta somente internet: {e.mensagem_usuario}")
    prep = tutor.preparar("Como calcular o ganho médio diário de um bovino?", "Intermediário", [])
    ok(not prep.busca.da_internet, "[modo bancos] pergunta coberta pelos bancos NÃO consulta a internet")
    pergunta = "O que é agricultura regenerativa?"
    prep = tutor.preparar(pergunta, "Intermediário", [])
    web = prep.busca.da_internet
    log(f"   “{pergunta}” → bancos: {len(prep.busca.do_banco)} · internet: "
        + "; ".join(f"[{r.rotulo}] {r.fonte}" for r in web))
    for a in prep.avisos:
        log(f"   aviso: {a}")
    if not ok(bool(web), "pergunta fora dos bancos consulta a internet e traz páginas com link"):
        return
    try:
        texto = "".join(tutor.responder_stream(cliente, prep))
    except ds.ErroIA as e:
        ok(False, f"resposta com a internet: {e.mensagem_usuario}")
        return
    cit = tutor.verificar_citacoes(texto, prep.busca)
    ok("O que a internet informa" in texto, "resposta separa a seção “🔗 O que a internet informa”")
    ok(any(c.startswith("W") for c in cit["citadas"]) and not cit["invalidas"],
       f"cita as páginas da internet corretamente: {cit['citadas']} (inválidas: {cit['invalidas']})")
    trecho = texto[:600].replace("\n", "\n   > ")
    log(f"   > {trecho}…")
    invalido = ws.ClienteBusca(ws.ConfigBusca(api_key="tvly-chave-invalida-para-teste-000000"))
    try:
        invalido.buscar("teste")
        ok(False, "o Tavily deveria recusar uma chave inválida")
    except ws.BuscaChaveInvalida as e:
        ok(True, f"chave inválida do Tavily tratada: “{e.mensagem_usuario}”")
    except ws.ErroBusca as e:
        ok(False, f"erro inesperado do Tavily para chave inválida: {type(e).__name__} {e.detalhe}")


def _bancos_sem_ia() -> None:
    log("\n## 3b. Recuperação nos bancos do SafraTech (sem IA)")
    base = kr.carregar_base_bancos(forcar=True)
    log(f"   bancos consultáveis: {', '.join(base.disponiveis) or 'nenhum'} · {len(base.indice)} referências indexadas")
    ok(len(base.disponiveis) == 6, "os 6 bancos do SafraTech acessíveis pelo tutor")
    for pergunta, banco_esperado in PERGUNTAS:
        refs = kr.buscar(pergunta, usar_biblioteca=False).referencias
        ok(any(any(b.startswith(banco_esperado) for b in r.bancos) for r in refs),
           f"“{pergunta}” → {', '.join(f'[{r.rotulo}] {r.titulo[:40]}' for r in refs[:3])}")


def _chave_invalida(cfg) -> None:
    log("\n## 6. Tratamento de erro real (chave inválida)")
    invalido = ds.ClienteDeepSeek(ds.ConfigDeepSeek(api_key="sk-chave-invalida-para-teste-000000", base_url=cfg.base_url,
                                                     modelo=cfg.modelo))
    try:
        invalido.conversar([{"role": "user", "content": "OK"}], max_tokens=5)
        ok(False, "a API deveria recusar uma chave inválida")
    except ds.IAChaveInvalida as e:
        ok(True, f"HTTP {e.status_http} tratado como chave inválida: “{e.mensagem_usuario}”")
    except ds.ErroIA as e:
        ok(False, f"erro inesperado para chave inválida: {type(e).__name__} {e.detalhe}")


if __name__ == "__main__":
    codigo = main()
    try:
        destino = RAIZ / "dados_eduagro" / "validacao_deepseek.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("\n".join(linhas), encoding="utf-8")
        print(f"\nRelatório salvo em {destino}")
    except OSError:
        pass
    sys.exit(codigo)
