"""
Cursos e trilhas de aprendizagem — lógica (sem interface).

O catálogo inicial contém apenas a ESTRUTURA dos cursos (nome, categoria, nível sugerido, escopo e objetivos
pedagógicos). Nenhum conteúdo técnico é apresentado como oficial: as aulas são cadastradas pelo responsável pelo
conteúdo (texto próprio ou material cadastrado) ou criadas como RASCUNHO pela IA a partir das referências dos bancos do
SafraTech e da Biblioteca — o rascunho fica marcado como "não revisado" até alguém revisá-lo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from modules.eduagro_ai import armazenamento as arm
from modules.eduagro_ai import knowledge_retrieval as kr
from modules.eduagro_ai import prompts
from modules.eduagro_ai.deepseek_client import ClienteDeepSeek

CATEGORIAS = ("Agricultura", "Pecuária", "Gestão Rural")
NIVEIS = prompts.NIVEIS
ORIGENS_AULA = {"proprio": "Conteúdo próprio", "material_cadastrado": "Material cadastrado (referência técnica)",
                "rascunho_ia": "Rascunho gerado por IA"}
NOTA_APROVACAO = 70.0  # critério do EduAgro para concluir um curso com avaliação final


@dataclass(frozen=True)
class CursoCatalogo:
    codigo: str
    nome: str
    categoria: str
    nivel: str
    descricao: str
    objetivos: tuple[str, ...]
    consulta: str       # termos usados para buscar referências relacionadas nos bancos
    area: str           # área de busca: agricultura | pecuaria | todas


C = CursoCatalogo
CATALOGO: tuple[CursoCatalogo, ...] = (
    # ---------------------------------------------------------------- Agricultura
    C("AGR-01", "Fundamentos da agricultura", "Agricultura", "Iniciante",
      "Visão geral da produção de grãos: solo, planta, clima e manejo como um sistema.",
      ("Reconhecer os fatores que determinam a produtividade de uma lavoura",
       "Compreender a terminologia básica usada por técnicos e produtores"),
      "ciclo cultura semeadura solo manejo produtividade", "agricultura"),
    C("AGR-02", "Ciência do solo", "Agricultura", "Iniciante",
      "Propriedades do solo, amostragem e leitura de uma análise química de solo.",
      ("Entender o que cada item de um laudo de análise de solo representa",
       "Calcular soma de bases, CTC e saturação por bases", "Saber como amostrar o solo corretamente"),
      "análise de solo amostragem CTC soma de bases saturação textura argila", "agricultura"),
    C("AGR-03", "Fertilidade e adubação", "Agricultura", "Intermediário",
      "Interpretação da fertilidade, calagem, gessagem e critérios de adubação descritos nas referências técnicas.",
      ("Interpretar teores de nutrientes pelas faixas das referências", "Compreender os métodos de cálculo de calagem e gessagem",
       "Diferenciar adubação corretiva e de manutenção"),
      "interpretação fósforo potássio calagem gessagem adubação corretiva manutenção", "agricultura"),
    C("AGR-04", "Nutrição de plantas", "Agricultura", "Intermediário",
      "Exigências nutricionais, diagnose foliar e sintomas de deficiência e toxidez.",
      ("Relacionar nutrientes às suas funções e sintomas", "Usar faixas de suficiência foliar na diagnose",
       "Reconhecer os limites da diagnose visual"),
      "nutriente deficiência sintoma faixa de suficiência foliar exigência", "agricultura"),
    C("AGR-05", "Culturas agrícolas", "Agricultura", "Iniciante",
      "Características das culturas presentes nos bancos do SafraTech: soja, milho, algodão e gergelim.",
      ("Comparar ciclo, exigências e manejo das principais culturas",), "soja milho algodão gergelim ciclo exigência",
      "agricultura"),
    C("AGR-06", "Manejo de lavouras", "Agricultura", "Intermediário",
      "Arranjo de plantas, época de semeadura, manejo do solo e da nutrição ao longo do ciclo.",
      ("Planejar o manejo de uma lavoura ao longo do ciclo", "Entender o efeito do arranjo de plantas"),
      "espaçamento população plantas manejo plantio direto parcelamento", "agricultura"),
    C("AGR-07", "Climatologia agrícola", "Agricultura", "Intermediário",
      "Temperatura, água, fotoperíodo e risco climático na produção agrícola.",
      ("Relacionar exigências climáticas às fases da cultura", "Compreender o conceito de risco climático"),
      "temperatura precipitação necessidade hídrica fotoperíodo soma térmica clima", "agricultura"),
    C("AGR-08", "Planejamento de plantio", "Agricultura", "Intermediário",
      "Uso do Zoneamento Agrícola de Risco Climático (ZARC) e escolha de época e cultivar.",
      ("Ler uma indicação do ZARC (decêndios, grupos de solo e ciclo)", "Planejar a janela de semeadura"),
      "zoneamento ZARC decêndio semeadura grupo de cultivar ciclo risco", "agricultura"),
    # ---------------------------------------------------------------- Pecuária
    C("PEC-01", "Introdução à pecuária de corte", "Pecuária", "Iniciante",
      "Fases da produção (cria, recria e engorda), categorias animais e indicadores básicos.",
      ("Conhecer as fases e as categorias do rebanho de corte", "Entender os principais indicadores zootécnicos"),
      "cria recria engorda terminação categorias rebanho bezerro", "pecuaria"),
    C("PEC-02", "Raças bovinas", "Pecuária", "Iniciante",
      "Raças e grupos genéticos usados na pecuária de corte e cruzamentos.",
      ("Diferenciar grupos genéticos e entender o uso de cruzamentos",), "raça nelore cruzamento genética touro",
      "pecuaria"),
    C("PEC-03", "Nutrição animal", "Pecuária", "Intermediário",
      "Pastagens, suplementação mineral e proteica e confinamento.",
      ("Relacionar a nutrição ao desempenho animal", "Compreender estratégias de suplementação na seca"),
      "suplementação mineral sal proteinado pastagem confinamento seca", "pecuaria"),
    C("PEC-04", "Sistemas de criação", "Pecuária", "Intermediário",
      "Sistemas extensivo, semi-intensivo e intensivo e seus indicadores.",
      ("Comparar sistemas de produção e seus resultados",), "sistema extensivo semi-intensivo intensivo lotação",
      "pecuaria"),
    C("PEC-05", "Manejo de bovinos", "Pecuária", "Iniciante",
      "Manejo reprodutivo, sanitário e de instalações.",
      ("Conhecer as práticas básicas de manejo do rebanho",), "manejo reprodução estação de monta sanidade vacinação",
      "pecuaria"),
    C("PEC-06", "Desempenho do rebanho", "Pecuária", "Intermediário",
      "Ganho médio diário, peso por idade, rendimento de carcaça e indicadores reprodutivos.",
      ("Calcular GMD, PC205, taxa de prenhez e de mortalidade", "Comparar o desempenho com referências compatíveis"),
      "ganho médio diário GMD peso desmama rendimento carcaça prenhez", "pecuaria"),
    C("PEC-07", "Custos de produção", "Pecuária", "Intermediário",
      "Estrutura de custos da pecuária de corte: desembolsos, depreciação, custo operacional e custo total.",
      ("Classificar os itens de custo", "Calcular depreciação e custo total"),
      "custo operacional custo total depreciação desembolso juros", "pecuaria"),
    C("PEC-08", "Comercialização de bovinos", "Pecuária", "Intermediário",
      "Arroba, rendimento de carcaça, formas de venda e leitura de preços históricos.",
      ("Converter peso vivo em arrobas de carcaça", "Entender a formação do preço de venda"),
      "arroba comercialização venda frigorífico preço rendimento", "pecuaria"),
    C("PEC-09", "Gestão econômica da pecuária", "Pecuária", "Avançado",
      "Margem bruta, margem operacional, lucro e análise de viabilidade de lotes.",
      ("Calcular e interpretar margens e lucro", "Avaliar a viabilidade de compra e venda de lotes"),
      "lucro margem bruta margem operacional receita viabilidade", "pecuaria"),
    # ---------------------------------------------------------------- Gestão Rural
    C("GES-01", "Gestão de propriedades rurais", "Gestão Rural", "Iniciante",
      "Organização da propriedade, controles zootécnicos e econômicos e tomada de decisão.",
      ("Identificar os controles essenciais de uma propriedade",), "controles econômicos gestão fazenda registro",
      "todas"),
    C("GES-02", "Custos de produção", "Gestão Rural", "Intermediário",
      "Conceitos gerais de custo aplicáveis à agricultura e à pecuária.",
      ("Diferenciar custo operacional, custo total e custo de oportunidade",), "custo produção depreciação juros oportunidade",
      "todas"),
    C("GES-03", "Planejamento financeiro", "Gestão Rural", "Avançado",
      "Fluxo de caixa, capital de giro, investimentos e indicadores financeiros da atividade.",
      ("Organizar um planejamento financeiro da safra ou do ciclo pecuário",), "capital juros investimento receita fluxo",
      "todas"),
    C("GES-04", "Comercialização agrícola", "Gestão Rural", "Intermediário",
      "Formas de comercialização, preço efetivo de insumos e leitura de cotações.",
      ("Comparar insumos pelo preço efetivo", "Entender a comercialização da produção"),
      "preço efetivo calcário comercialização venda", "todas"),
    C("GES-05", "Tecnologia no agronegócio", "Gestão Rural", "Iniciante",
      "Ferramentas digitais, análise de dados e agricultura e pecuária de precisão.",
      ("Conhecer o papel das ferramentas digitais na gestão rural",), "aplicativo controle tecnologia precisão", "todas"),
)


# =====================================================================================================
# Persistência
# =====================================================================================================
def garantir_catalogo() -> None:
    """Cria no SQLite os cursos do catálogo que ainda não existem (não altera cursos já cadastrados)."""
    agora = arm.agora()
    arm.executar_varios(
        "INSERT OR IGNORE INTO curso (codigo, nome, descricao, categoria, nivel, objetivos, ordem, origem, criado_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'catalogo', ?)",
        [(c.codigo, c.nome, c.descricao, c.categoria, c.nivel, "\n".join(c.objetivos), i, agora) for i, c in enumerate(CATALOGO)])


def catalogo_por_codigo(codigo: str) -> Optional[CursoCatalogo]:
    return next((c for c in CATALOGO if c.codigo == codigo), None)


def listar_cursos(categoria: Optional[str] = None, usuario_id: Optional[int] = None) -> list[dict]:
    garantir_catalogo()
    sql = """SELECT c.id, c.codigo, c.nome, c.descricao, c.categoria, c.nivel, c.objetivos, c.origem,
                    (SELECT count(*) FROM aula a WHERE a.curso_id = c.id) AS aulas,
                    (SELECT count(*) FROM aula a WHERE a.curso_id = c.id AND a.revisada = 0) AS rascunhos,
                    (SELECT count(*) FROM questao q WHERE q.curso_id = c.id AND q.avaliacao_final = 1) AS questoes_finais"""
    params: list = []
    if usuario_id is not None:
        sql += """, (SELECT count(*) FROM aula_concluida ac JOIN aula a ON a.id = ac.aula_id
                    WHERE a.curso_id = c.id AND ac.usuario_id = ?) AS concluidas,
                    (SELECT status FROM matricula m WHERE m.curso_id = c.id AND m.usuario_id = ?) AS status"""
        params += [usuario_id, usuario_id]
    sql += " FROM curso c"
    if categoria:
        sql += " WHERE c.categoria = ?"
        params.append(categoria)
    sql += " ORDER BY CASE c.categoria WHEN 'Agricultura' THEN 0 WHEN 'Pecuária' THEN 1 ELSE 2 END, c.ordem, c.id"
    return arm.consultar(sql, params)


def obter_curso(curso_id: int) -> Optional[dict]:
    return arm.um("SELECT id, codigo, nome, descricao, categoria, nivel, objetivos, origem FROM curso WHERE id = ?", (curso_id,))


def criar_curso(nome: str, categoria: str, nivel: str, descricao: str, objetivos: str) -> int:
    if not nome.strip():
        raise ValueError("Informe o nome do curso.")
    if categoria not in CATEGORIAS or nivel not in NIVEIS:
        raise ValueError("Categoria ou nível inválido.")
    n = (arm.um("SELECT count(*) AS n FROM curso WHERE origem = 'proprio'") or {"n": 0})["n"] + 1
    return arm.executar("INSERT INTO curso (codigo, nome, descricao, categoria, nivel, objetivos, ordem, origem, criado_em) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 'proprio', ?)",
                        (f"PRO-{n:03d}-{arm.agora()[-8:].replace(':', '')}", nome.strip(), descricao.strip(), categoria, nivel,
                         objetivos.strip(), 1000 + n, arm.agora()))


def listar_aulas(curso_id: int) -> list[dict]:
    return arm.consultar("SELECT id, curso_id, ordem, titulo, conteudo, resumo, exemplos, referencias, origem, revisada "
                         "FROM aula WHERE curso_id = ? ORDER BY ordem, id", (curso_id,))


def salvar_aula(curso_id: int, titulo: str, conteudo: str, resumo: str = "", exemplos: str = "", referencias: str = "",
                origem: str = "proprio", aula_id: Optional[int] = None, revisada: Optional[bool] = None) -> int:
    if not titulo.strip() or not conteudo.strip():
        raise ValueError("Título e conteúdo da aula são obrigatórios.")
    if origem not in ORIGENS_AULA:
        raise ValueError("Origem da aula inválida.")
    rev = (origem != "rascunho_ia") if revisada is None else revisada
    agora = arm.agora()
    if aula_id:
        arm.executar("UPDATE aula SET titulo=?, conteudo=?, resumo=?, exemplos=?, referencias=?, origem=?, revisada=?, "
                     "atualizado_em=? WHERE id=?", (titulo, conteudo, resumo, exemplos, referencias, origem, int(rev), agora, aula_id))
        return aula_id
    ordem = (arm.um("SELECT coalesce(max(ordem), 0) + 1 AS o FROM aula WHERE curso_id = ?", (curso_id,)) or {"o": 1})["o"]
    return arm.executar("INSERT INTO aula (curso_id, ordem, titulo, conteudo, resumo, exemplos, referencias, origem, revisada, "
                        "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (curso_id, ordem, titulo.strip(), conteudo, resumo, exemplos, referencias, origem, int(rev), agora, agora))


def marcar_revisada(aula_id: int) -> None:
    arm.executar("UPDATE aula SET revisada = 1, atualizado_em = ? WHERE id = ?", (arm.agora(), aula_id))


def excluir_aula(aula_id: int) -> None:
    arm.executar("DELETE FROM aula WHERE id = ?", (aula_id,))


def referencias_do_curso(curso: dict, k: int = 10) -> kr.ResultadoBusca:
    """Registros dos bancos (e da biblioteca) relacionados ao escopo do curso — material de consulta, com fonte."""
    cat = catalogo_por_codigo(curso.get("codigo", ""))
    consulta = cat.consulta if cat else f"{curso.get('nome', '')} {curso.get('descricao', '')}"
    area = cat.area if cat else ("agricultura" if curso.get("categoria") == "Agricultura" else
                                 "pecuaria" if curso.get("categoria") == "Pecuária" else "todas")
    return kr.buscar(consulta, area=area, k_bancos=k, k_biblioteca=4, cobertura=0.15, relativo=0.2)


def gerar_rascunho_aula(cliente: ClienteDeepSeek, curso: dict, tema_aula: str, nivel: str, area: str = "todas") -> dict:
    """Pede à DeepSeek um rascunho de aula baseado SOMENTE nas referências recuperadas. Não grava nada."""
    busca = kr.buscar(f"{tema_aula} {curso.get('nome', '')}", area=area, k_bancos=8, k_biblioteca=4, cobertura=0.3)
    if busca.vazio:
        raise ValueError("Não há referências nos bancos do SafraTech nem na Biblioteca sobre este tema. "
                         "Cadastre material na Biblioteca ou escreva a aula manualmente.")
    msgs = [{"role": "system", "content": prompts.SISTEMA_RASCUNHO_AULA.replace("{nivel}", nivel)},
            {"role": "user", "content": prompts.pedido_rascunho_aula(curso["nome"], tema_aula, curso.get("objetivos") or "",
                                                                     kr.formatar_contexto(busca))}]
    dados = cliente.conversar_json(msgs, temperatura=0.3, max_tokens=3500)
    rotulos = {r.rotulo: r for r in busca.referencias}
    refs_txt = "\n".join(f"[{r.rotulo}] {r.titulo} — {r.citacao()} ({', '.join(r.bancos)})" for r in busca.referencias)
    return {"titulo": str(dados.get("titulo") or tema_aula)[:150], "conteudo": str(dados.get("conteudo") or ""),
            "resumo": str(dados.get("resumo") or ""), "exemplos": str(dados.get("exemplos") or ""),
            "referencias": refs_txt, "citadas_validas": [x for x in dados.get("referencias") or [] if x in rotulos]}


# =====================================================================================================
# Progresso no curso
# =====================================================================================================
def matricular(usuario_id: int, curso_id: int) -> None:
    arm.executar("INSERT OR IGNORE INTO matricula (usuario_id, curso_id, status, iniciado_em) VALUES (?, ?, 'em_andamento', ?)",
                 (usuario_id, curso_id, arm.agora()))


def concluir_aula(usuario_id: int, aula_id: int) -> None:
    aula = arm.um("SELECT curso_id, titulo FROM aula WHERE id = ?", (aula_id,))
    if not aula:
        return
    matricular(usuario_id, aula["curso_id"])
    arm.executar("INSERT OR IGNORE INTO aula_concluida (usuario_id, aula_id, concluido_em) VALUES (?, ?, ?)",
                 (usuario_id, aula_id, arm.agora()))
    curso = obter_curso(aula["curso_id"]) or {}
    arm.registrar_evento(usuario_id, "aula_concluida", f"Aula concluída: {aula['titulo']}", curso.get("categoria"))
    atualizar_status_curso(usuario_id, aula["curso_id"])


def aulas_concluidas(usuario_id: int, curso_id: int) -> set[int]:
    return {r["aula_id"] for r in arm.consultar(
        "SELECT ac.aula_id FROM aula_concluida ac JOIN aula a ON a.id = ac.aula_id WHERE ac.usuario_id = ? AND a.curso_id = ?",
        (usuario_id, curso_id))}


def atualizar_status_curso(usuario_id: int, curso_id: int) -> str:
    """Concluído quando todas as aulas foram concluídas e, se houver avaliação final cadastrada, nota ≥ 70%."""
    total = (arm.um("SELECT count(*) AS n FROM aula WHERE curso_id = ?", (curso_id,)) or {"n": 0})["n"]
    feitas = len(aulas_concluidas(usuario_id, curso_id))
    tem_final = (arm.um("SELECT count(*) AS n FROM questao WHERE curso_id = ? AND avaliacao_final = 1", (curso_id,)) or {"n": 0})["n"]
    melhor = arm.um("SELECT max(nota) AS nota FROM avaliacao WHERE usuario_id = ? AND curso_id = ? AND final = 1",
                    (usuario_id, curso_id))
    aprovado = (not tem_final) or (melhor and melhor["nota"] is not None and melhor["nota"] >= NOTA_APROVACAO)
    status = "concluido" if total and feitas >= total and aprovado else "em_andamento"
    atual = arm.um("SELECT status FROM matricula WHERE usuario_id = ? AND curso_id = ?", (usuario_id, curso_id))
    if atual and atual["status"] != status:
        arm.executar("UPDATE matricula SET status = ?, concluido_em = ? WHERE usuario_id = ? AND curso_id = ?",
                     (status, arm.agora() if status == "concluido" else None, usuario_id, curso_id))
        if status == "concluido":
            c = obter_curso(curso_id) or {}
            arm.registrar_evento(usuario_id, "curso_concluido", f"Curso concluído: {c.get('nome')}", c.get("categoria"))
    return status
