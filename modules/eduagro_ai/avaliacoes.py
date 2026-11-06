"""
Exercícios e avaliações — lógica (sem interface).

Origens das questões (sempre identificadas na interface):
- 'calculo_banco': exercícios numéricos com fórmulas dos bancos; resposta calculada pelo aplicativo (exercicios_calculo.py);
- 'ia': questões geradas pela DeepSeek a partir das referências recuperadas — rotuladas como "geradas por IA para estudo",
  nunca como questões oficiais de instituições;
- 'cadastrada': questões escritas pelo responsável pelo conteúdo do curso.

Correção: múltipla escolha, verdadeiro/falso e práticas numéricas são corrigidas pelo aplicativo; respostas abertas
(estudo de caso / prática discursiva) são corrigidas pela DeepSeek — se a IA estiver indisponível, a correção não é
simulada: o estudante é avisado e pode ver a resposta esperada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import cursos as cur
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai import prompts
from modules.eduagro_ai.deepseek_client import ClienteDeepSeek
from modules.eduagro_ai.exercicios_calculo import confere, ler_numero

TIPOS = {"multipla_escolha": "Múltipla escolha", "verdadeiro_falso": "Verdadeiro ou falso", "pratica": "Questão prática",
         "estudo_de_caso": "Estudo de caso"}
ORIGENS = {"ia": "🤖 Gerada por IA para estudo (não é questão oficial de nenhuma instituição)",
           "calculo_banco": "🧮 Cálculo com fórmula dos bancos do SafraTech (valores hipotéticos)",
           "cadastrada": "📝 Questão cadastrada no curso"}
LETRAS = "ABCDE"
PALAVRAS_OFICIAIS = re.compile(r"\b(quest[aã]o oficial|prova oficial|concurso|vestibular|enem|exame da ordem)\b", re.IGNORECASE)


# =====================================================================================================
# Validação das questões geradas pela IA
# =====================================================================================================
def _lista(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def validar_questao(q: dict, rotulos: dict[str, kr.Referencia], nivel: str, tema: str, categoria: str) -> Optional[dict]:
    """Normaliza a questão da IA; devolve None se estiver incompleta ou incoerente."""
    if not isinstance(q, dict):
        return None
    tipo = str(q.get("tipo") or "").strip().lower().replace(" ", "_")
    tipo = {"multipla": "multipla_escolha", "vf": "verdadeiro_falso", "estudo_caso": "estudo_de_caso"}.get(tipo, tipo)
    enun = str(q.get("enunciado") or "").strip()
    if tipo not in TIPOS or len(enun) < 15:
        return None
    if PALAVRAS_OFICIAIS.search(enun):
        enun = PALAVRAS_OFICIAIS.sub("exercício", enun)
    refs_citadas = [str(r).strip("[] ") for r in _lista(q.get("referencias"))]
    refs = [rotulos[r].para_dict() for r in refs_citadas if r in rotulos]
    if not refs:
        return None   # toda questão precisa estar fundamentada em um trecho real do contexto
    out = {"tipo": tipo, "enunciado": enun, "alternativas": [], "resposta": str(q.get("resposta_correta") or "").strip(),
           "resposta_numerica": None, "tolerancia": None, "tolerancia_abs": None,
           "explicacao": str(q.get("explicacao") or "").strip(), "justificativa": str(q.get("justificativa_tecnica") or "").strip(),
           "referencias": refs, "assuntos": [str(a) for a in _lista(q.get("assuntos"))][:4] or [tema], "nivel": nivel,
           "origem": "ia", "tema": tema, "categoria": categoria}
    if tipo == "multipla_escolha":
        alts = [re.sub(r"^\s*[A-Ea-e][\)\.\-:]\s*", "", str(a)).strip() for a in _lista(q.get("alternativas"))]
        alts = [a for a in alts if a]
        if not 3 <= len(alts) <= 5 or len(set(alts)) != len(alts):
            return None
        letra = out["resposta"][:1].upper()
        if letra not in LETRAS[:len(alts)]:
            try:
                letra = LETRAS[alts.index(out["resposta"])]
            except ValueError:
                return None
        out.update(alternativas=alts, resposta=letra)
    elif tipo == "verdadeiro_falso":
        r = out["resposta"].lower()
        if r.startswith("v"):
            out["resposta"] = "Verdadeiro"
        elif r.startswith("f"):
            out["resposta"] = "Falso"
        else:
            return None
    else:
        if not out["resposta"]:
            return None
        num = q.get("resposta_numerica")
        if tipo == "pratica" and num not in (None, ""):
            v = ler_numero(num)
            if v is not None:
                tol = ler_numero(q.get("tolerancia"))
                out.update(resposta_numerica=v, tolerancia=min(max(tol if tol is not None else 0.03, 0.005), 0.1))
    if not out["explicacao"]:
        return None
    return out


@dataclass
class Geracao:
    questoes: list[dict]
    descartadas: int
    busca: kr.ResultadoBusca
    aulas_usadas: int = 0


def contexto_aulas(curso_id: int, limite: int = 6) -> tuple[str, int]:
    aulas = [a for a in cur.listar_aulas(curso_id) if a["revisada"]][:limite]
    blocos = [f"[A{i}] Aula do curso — {a['titulo']}\n{a['conteudo'][:1800]}\nResumo: {a.get('resumo') or ''}"
              for i, a in enumerate(aulas, 1)]
    return "\n\n".join(blocos), len(aulas)


def gerar_questoes_ia(cliente: ClienteDeepSeek, tema: str, nivel: str, quantidade: int = 5, tipos: Optional[list[str]] = None,
                      area: str = "todas", categoria: str = "", curso_id: Optional[int] = None,
                      usar_biblioteca: bool = True) -> Geracao:
    tipos = [t for t in (tipos or list(TIPOS)) if t in TIPOS] or ["multipla_escolha"]
    quantidade = max(1, min(int(quantidade), 10))
    busca = kr.buscar(tema, area=area, k_bancos=8, k_biblioteca=4, usar_biblioteca=usar_biblioteca, cobertura=0.3)
    ctx_aulas, n_aulas = contexto_aulas(curso_id) if curso_id else ("", 0)
    if busca.vazio and not n_aulas:
        raise ValueError("Não encontrei conteúdo sobre este tema nos bancos do SafraTech, na Biblioteca ou nas aulas do curso. "
                         "Sem uma base cadastrada, os exercícios não são gerados.")
    contexto = "\n\n".join(x for x in (kr.formatar_contexto(busca) if not busca.vazio else "", ctx_aulas) if x)
    msgs = [{"role": "system", "content": prompts.SISTEMA_EXERCICIOS.format(nivel=nivel)},
            {"role": "user", "content": prompts.pedido_exercicios(tema, contexto, quantidade, [TIPOS[t] + f" ({t})" for t in tipos])}]
    dados = cliente.conversar_json(msgs, temperatura=0.4, max_tokens=4000)
    rotulos = {r.rotulo: r for r in busca.referencias}
    if n_aulas:
        for i in range(1, n_aulas + 1):   # aulas também podem fundamentar a questão
            rotulos[f"A{i}"] = kr.Referencia(chave=f"aula:{curso_id}:{i}", origem="curso", area="curso", bancos=["curso"],
                                             tipo="Aula do curso", titulo=f"Aula {i}", texto="", fonte="Aulas do curso")
    brutas = _lista(dados.get("questoes"))
    validas = [v for v in (validar_questao(q, rotulos, nivel, tema, categoria) for q in brutas) if v and v["tipo"] in tipos]
    return Geracao(validas[:quantidade], len(brutas) - len(validas), busca, n_aulas)


# =====================================================================================================
# Persistência das questões
# =====================================================================================================
def salvar_questao(q: dict, curso_id: Optional[int] = None, avaliacao_final: bool = False) -> int:
    return arm.executar(
        "INSERT INTO questao (curso_id, tema, categoria, tipo, enunciado, alternativas_json, resposta, resposta_numerica, "
        "tolerancia, tolerancia_abs, explicacao, justificativa, referencias_json, assuntos, nivel, origem, avaliacao_final, "
        "criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (curso_id, q.get("tema"), q.get("categoria"), q["tipo"], q["enunciado"], arm.jdump(q.get("alternativas") or []),
         q.get("resposta"), q.get("resposta_numerica"), q.get("tolerancia"), q.get("tolerancia_abs"), q.get("explicacao"),
         q.get("justificativa"), arm.jdump(q.get("referencias") or []), "; ".join(q.get("assuntos") or []), q.get("nivel"),
         q.get("origem", "cadastrada"), int(avaliacao_final), arm.agora()))


def _de_linha(r: dict) -> dict:
    r = dict(r)
    r["alternativas"] = arm.jload(r.pop("alternativas_json", None), [])
    r["referencias"] = arm.jload(r.pop("referencias_json", None), [])
    r["assuntos"] = [a.strip() for a in (r.get("assuntos") or "").split(";") if a.strip()]
    return r


def listar_questoes(curso_id: Optional[int] = None, final: Optional[bool] = None) -> list[dict]:
    sql = ("SELECT id, curso_id, tema, categoria, tipo, enunciado, alternativas_json, resposta, resposta_numerica, tolerancia, "
           "tolerancia_abs, explicacao, justificativa, referencias_json, assuntos, nivel, origem, avaliacao_final FROM questao")
    cond, params = [], []
    if curso_id is not None:
        cond.append("curso_id = ?")
        params.append(curso_id)
    if final is not None:
        cond.append("avaliacao_final = ?")
        params.append(int(final))
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return [_de_linha(r) for r in arm.consultar(sql + " ORDER BY id", params)]


def excluir_questao(qid: int) -> None:
    arm.executar("DELETE FROM questao WHERE id = ?", (qid,))


# =====================================================================================================
# Correção
# =====================================================================================================
@dataclass
class Correcao:
    correta: bool
    pontuacao: float
    resposta_usuario: str
    resposta_correta: str
    feedback: str = ""
    revisar: list[str] = field(default_factory=list)
    corrigida_por: str = "aplicativo"


def resposta_formatada(q: dict) -> str:
    if q["tipo"] == "multipla_escolha" and q.get("alternativas"):
        i = LETRAS.index(q["resposta"]) if q["resposta"] in LETRAS else -1
        return f"{q['resposta']}) {q['alternativas'][i]}" if 0 <= i < len(q["alternativas"]) else q["resposta"]
    return str(q.get("resposta") or "")


def corrigir(q: dict, resposta_usuario, cliente: Optional[ClienteDeepSeek] = None) -> Correcao:
    """Levanta ErroIA (deepseek_client) se a questão exigir correção pela IA e ela estiver indisponível."""
    tipo = q["tipo"]
    ru = "" if resposta_usuario is None else str(resposta_usuario).strip()
    esperado = resposta_formatada(q)
    if tipo == "multipla_escolha":
        ok = ru[:1].upper() == q["resposta"]
        return Correcao(ok, 1.0 if ok else 0.0, ru, esperado, revisar=[] if ok else q.get("assuntos", []))
    if tipo == "verdadeiro_falso":
        ok = ru.lower()[:1] == q["resposta"].lower()[:1] and bool(ru)
        return Correcao(ok, 1.0 if ok else 0.0, ru, esperado, revisar=[] if ok else q.get("assuntos", []))
    if tipo == "pratica" and q.get("resposta_numerica") is not None:
        v = ler_numero(ru)
        ok = confere(v, float(q["resposta_numerica"]), float(q.get("tolerancia") or 0.02), float(q.get("tolerancia_abs") or 0))
        fb = "" if v is not None else "Não reconheci um número na sua resposta (use, por exemplo, 0,85)."
        return Correcao(ok, 1.0 if ok else 0.0, ru, esperado, feedback=fb, revisar=[] if ok else q.get("assuntos", []))
    # resposta aberta → correção pela IA
    if not ru:
        return Correcao(False, 0.0, ru, esperado, "Resposta em branco.", q.get("assuntos", []))
    if cliente is None:
        from modules.eduagro_ai.deepseek_client import obter_cliente
        cliente = obter_cliente()
    dados = cliente.conversar_json([{"role": "system", "content": prompts.SISTEMA_CORRECAO},
                                    {"role": "user", "content": prompts.pedido_correcao(q["enunciado"], esperado,
                                                                                       q.get("justificativa") or "", ru)}],
                                   temperatura=0.1, max_tokens=900)
    p = ler_numero(dados.get("pontuacao"))
    p = 0.0 if p is None else max(0.0, min(1.0, p if p <= 1 else p / 100))
    return Correcao(p >= 0.7, p, ru, esperado, str(dados.get("feedback") or ""),
                    [str(x) for x in _lista(dados.get("assuntos_para_revisar"))][:4] or ([] if p >= 0.7 else q.get("assuntos", [])),
                    corrigida_por="IA (DeepSeek)")


# =====================================================================================================
# Registro do resultado
# =====================================================================================================
def registrar_avaliacao(usuario_id: int, titulo: str, itens: list[tuple[dict, Correcao]], curso_id: Optional[int] = None,
                        categoria: Optional[str] = None, final: bool = False) -> dict:
    if not itens:
        raise ValueError("Nenhuma questão respondida.")
    total = len(itens)
    acertos = sum(c.pontuacao for _, c in itens)
    nota = round(100 * acertos / total, 1)
    categoria = categoria or (itens[0][0].get("categoria") or None)
    av_id = arm.executar("INSERT INTO avaliacao (usuario_id, curso_id, titulo, categoria, final, total, acertos, nota, criado_em) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (usuario_id, curso_id, titulo[:150], categoria, int(final), total, acertos, nota, arm.agora()))
    arm.executar_varios(
        "INSERT INTO tentativa (usuario_id, questao_id, avaliacao_id, resposta_usuario, correta, pontuacao, feedback, categoria, "
        "tema, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(usuario_id, q.get("id"), av_id, c.resposta_usuario, int(c.correta), c.pontuacao, c.feedback,
          q.get("categoria") or categoria, q.get("tema"), arm.agora()) for q, c in itens])
    arm.registrar_evento(usuario_id, "avaliacao_final" if final else "exercicios",
                         f"{'Avaliação final' if final else 'Exercícios'}: {titulo} — nota {nota:g}%", categoria)
    if curso_id:
        cur.matricular(usuario_id, curso_id)
        cur.atualizar_status_curso(usuario_id, curso_id)
    revisar = sorted({a for _, c in itens if not c.correta for a in (c.revisar or [])})
    return {"avaliacao_id": av_id, "nota": nota, "acertos": acertos, "total": total, "revisar": revisar}
