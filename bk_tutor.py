"""
Tutor Agro Inteligente — lógica (sem interface): recuperação de contexto, montagem das mensagens para a DeepSeek,
pós-processamento das respostas e persistência das conversas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Optional

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai import prompts
from modules.eduagro_ai.deepseek_client import ClienteDeepSeek

SUGESTOES = [
    "Como interpretar uma análise de solo?",
    "Qual a diferença entre deficiência e toxicidade nutricional?",
    "Como funciona a adubação de cobertura na soja?",
    "Como calcular o ganho médio diário de um bovino?",
    "Como funciona o rendimento de carcaça?",
    "Como avaliar a rentabilidade de um lote de gado?",
    "O que é o Zoneamento Agrícola de Risco Climático?",
    "Como escolher uma cultivar?",
]

FONTES_TUTOR = {"internet": "🔗 Somente internet", "bancos": "📚 Bancos do SafraTech (internet só se não achar)"}


def fonte_padrao() -> str:
    """Fonte inicial das respostas do tutor (EDUAGRO_FONTE_TUTOR no .env: 'internet' ou 'bancos'). Padrão: internet."""
    import os
    v = (os.environ.get("EDUAGRO_FONTE_TUTOR") or "internet").strip().lower()
    return v if v in FONTES_TUTOR else "internet"


AREAS_TUTOR = {"todas": "Todas as áreas", "agricultura": "Agricultura (solo, nutrição, plantio)",
               "pecuaria": "Pecuária de corte e gestão"}

MAX_HISTORICO = 6          # mensagens anteriores enviadas à IA (3 trocas)
MAX_CARACTERES_HISTORICO = 3500


@dataclass
class Preparacao:
    mensagens: list[dict]
    busca: kr.ResultadoBusca
    consulta: str
    modo: str = "pergunta"
    avisos: list[str] = field(default_factory=list)


def _resumir(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + " […]"


def preparar(pergunta: str, nivel: str, historico: list[dict], area: str = "todas", usar_bancos: bool = True,
             usar_biblioteca: bool = True, modo: str = "pergunta", consulta_anterior: str = "",
             usar_internet: bool = True, cliente_busca=None, fonte: str = "bancos") -> Preparacao:
    """Monta as mensagens da DeepSeek. `modo`: 'pergunta' | 'mais_simples' | 'aprofundar' | 'internet'.
    Nos modos de reformulação, a busca reutiliza a consulta anterior (o assunto não muda).

    `fonte`:
      - 'internet': a resposta usa SOMENTE páginas da internet (os bancos do SafraTech não são consultados);
      - 'bancos': 1º bancos do SafraTech e Biblioteca; 2º internet, SOMENTE se nada for encontrado neles
        (ou se o estudante pedir explicitamente, modo 'internet')."""
    if modo == "mais_simples":
        texto_usuario, consulta = prompts.INSTRUCAO_MAIS_SIMPLES, consulta_anterior or pergunta
    elif modo == "aprofundar":
        texto_usuario, consulta = prompts.INSTRUCAO_APROFUNDAR, consulta_anterior or pergunta
    elif modo == "internet":
        texto_usuario, consulta = prompts.INSTRUCAO_INTERNET, consulta_anterior or pergunta
    else:
        texto_usuario, consulta = pergunta.strip(), pergunta.strip()
    avisos = []
    if fonte == "internet":
        if modo == "internet":
            texto_usuario = pergunta.strip() or consulta
        busca = kr.ResultadoBusca(consulta, [], [], {}, False, 0)
        avisos += _complementar_com_internet(busca, consulta, cliente_busca, pedido_explicito=True, somente_internet=True)
    else:
        busca = kr.buscar(consulta, area=area, usar_bancos=usar_bancos, usar_biblioteca=usar_biblioteca)
        if busca.bancos_indisponiveis:
            avisos.append("Bancos indisponíveis nesta consulta: " + ", ".join(busca.bancos_indisponiveis) + ".")
        if usar_internet and (modo == "internet" or busca.sem_fontes_safratech):
            avisos += _complementar_com_internet(busca, consulta, cliente_busca, pedido_explicito=(modo == "internet"))
    if fonte == "internet":
        texto_usuario = prompts.INSTRUCAO_SOMENTE_INTERNET + "\n\n" + texto_usuario
    msgs = [{"role": "system", "content": prompts.sistema_tutor(nivel)}]
    for m in historico[-MAX_HISTORICO:]:
        if m.get("papel") in ("user", "assistant") and m.get("conteudo"):
            msgs.append({"role": m["papel"], "content": _resumir(m["conteudo"], MAX_CARACTERES_HISTORICO)})
    msgs.append({"role": "user", "content": prompts.mensagem_com_contexto(texto_usuario, kr.formatar_contexto(busca))})
    return Preparacao(msgs, busca, consulta, modo, avisos)


def _complementar_com_internet(busca: kr.ResultadoBusca, consulta: str, cliente_busca, pedido_explicito: bool,
                               somente_internet: bool = False) -> list[str]:
    from modules.eduagro_ai import web_search as ws
    cli = cliente_busca or ws.obter_cliente()
    if not cli.disponivel:
        busca.erro_internet = cli.config.descricao()
        if pedido_explicito:
            return ["A busca na internet não está configurada (TAVILY_API_KEY no .env)."]
        return ["Nada encontrado nos bancos do SafraTech; a busca na internet não está configurada."]
    try:
        paginas = cli.buscar(consulta)
    except Exception as e:  # qualquer falha da internet nunca derruba o tutor: ele responde com o que tiver
        msg = getattr(e, "mensagem_usuario", None) or f"{type(e).__name__}: {e}"
        busca.internet_consultada, busca.erro_internet = True, msg
        return ["Busca na internet indisponível: " + msg]
    kr.anexar_internet(busca, paginas)
    if not paginas:
        return ["A busca na internet não encontrou páginas para esta pergunta."]
    if somente_internet:
        return [f"🔗 Resposta baseada em {len(paginas)} página(s) da internet (fontes externas, não verificadas pelo SafraTech)."]
    origem = "Nada encontrado nos bancos do SafraTech — " if busca.sem_fontes_safratech else ""
    return [f"{origem}🔗 {len(paginas)} página(s) da internet consultada(s) (fontes externas, não verificadas pelo SafraTech)."]


def responder_stream(cliente: ClienteDeepSeek, prep: Preparacao, temperatura: float = 0.3) -> Iterator[str]:
    yield from cliente.conversar_stream(prep.mensagens, temperatura=temperatura)


# =====================================================================================================
# Pós-processamento
# =====================================================================================================
def normalizar_latex(texto: str) -> str:
    """Converte \\( \\) e \\[ \\] (comuns nas respostas) para $ e $$, que o Streamlit renderiza."""
    t = re.sub(r"\\\[(.+?)\\\]", lambda m: f"\n$$\n{m.group(1).strip()}\n$$\n", texto, flags=re.S)
    t = re.sub(r"\\\((.+?)\\\)", lambda m: f"${m.group(1).strip()}$", t, flags=re.S)
    return t


def verificar_citacoes(texto: str, busca: kr.ResultadoBusca) -> dict:
    """Confere se cada [S#]/[D#] citado pela IA existe no contexto entregue a ela."""
    citadas = sorted(set(re.findall(r"\[([SDW]\d+)\]", texto)), key=lambda x: (x[0], int(x[1:])))
    validos = {r.rotulo for r in busca.referencias}
    return {"citadas": [c for c in citadas if c in validos], "invalidas": [c for c in citadas if c not in validos],
            "nao_citadas": sorted(validos - set(citadas))}


# =====================================================================================================
# Conversas (SQLite)
# =====================================================================================================
def criar_conversa(usuario_id: int, primeira_pergunta: str, nivel: str) -> int:
    titulo = " ".join(primeira_pergunta.split())[:70] or "Nova conversa"
    agora = arm.agora()
    return arm.executar("INSERT INTO conversa (usuario_id, titulo, nivel, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?)",
                        (usuario_id, titulo, nivel, agora, agora))


def adicionar_mensagem(conversa_id: int, papel: str, conteudo: str, referencias: Optional[list] = None,
                       meta: Optional[dict] = None) -> int:
    agora = arm.agora()
    mid = arm.executar("INSERT INTO mensagem (conversa_id, papel, conteudo, referencias_json, meta_json, criado_em) "
                       "VALUES (?, ?, ?, ?, ?, ?)",
                       (conversa_id, papel, conteudo, arm.jdump(referencias or []), arm.jdump(meta or {}), agora))
    arm.executar("UPDATE conversa SET atualizado_em = ? WHERE id = ?", (agora, conversa_id))
    return mid


def listar_conversas(usuario_id: int, limite: int = 30) -> list[dict]:
    return arm.consultar("""SELECT c.id, c.titulo, c.nivel, c.atualizado_em, count(m.id) AS mensagens
                            FROM conversa c LEFT JOIN mensagem m ON m.conversa_id = c.id
                            WHERE c.usuario_id = ? GROUP BY c.id ORDER BY c.atualizado_em DESC, c.id DESC LIMIT ?""",
                         (usuario_id, limite))


def mensagens(conversa_id: int) -> list[dict]:
    linhas = arm.consultar("SELECT id, papel, conteudo, referencias_json, meta_json, criado_em FROM mensagem "
                           "WHERE conversa_id = ? ORDER BY id", (conversa_id,))
    for l in linhas:
        l["referencias"] = arm.jload(l.pop("referencias_json"), [])
        l["meta"] = arm.jload(l.pop("meta_json"), {})
    return linhas


def excluir_conversa(conversa_id: int, usuario_id: int) -> None:
    arm.executar("DELETE FROM conversa WHERE id = ? AND usuario_id = ?", (conversa_id, usuario_id))
