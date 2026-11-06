"""
Recuperação de conhecimento do EduAgro AI (RAG) — sem dependências externas.

Fontes consultadas:
1. Bancos do SafraTech (somente leitura, via database/eduagro_queries.py):
   - solo_database, nutricao_database, plantio_database: registros curados (faixas de interpretação agrupadas em
     tabelas, equações, critérios, conceitos, sintomas, exigências...);
   - pecuaria_compra/desempenho/rentabilidade_database: parâmetros técnicos, fórmulas de cálculo e perguntas e
     respostas das publicações (registros repetidos entre os três bancos aparecem uma única vez).
2. Biblioteca do EduAgro: trechos de documentos cadastrados (PDF/TXT/MD), com documento e página.

Busca: BM25 sobre texto normalizado (sem acentos, radicais simples do português, expansão de siglas do setor:
P → fósforo, GMD → ganho médio diário, ZARC → zoneamento agrícola de risco climático...). Cada resultado preserva a
identificação de origem: banco, registro, fonte, instituição, ano e página. A IA recebe esses trechos numerados
([S1], [D1]...) e só pode usar valores de referência que estejam neles.

A estrutura `Indice` foi separada para que uma busca vetorial (embeddings) possa ser acrescentada no futuro
(a tabela `trecho` já possui a coluna `embedding`).
"""
from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import pandas as pd

from database import eduagro_queries as eq
from database.connections import BANCOS, BancoIndisponivel

# =====================================================================================================
# Normalização de texto
# =====================================================================================================
STOPWORDS = set("""
a à ao aos as às ate até com como contra da das de dela dele do dos e é ela ele eles elas em entre era essa esse esta
este eu foi for ha há isso isto ja já lhe mais mas me mesmo meu minha muito na nas nao não nem no nos nós num numa o os
ou para pela pelas pelo pelos por pra qual quais quando que quem se sem ser seu sua seus suas so só sobre tambem também
tem têm ter um uma umas uns voce você vocês sao são esta está estao estão pode podem deve devem cada outro outra outros
explique explicar explica funciona funcionam fazer faz significa serve qual quais diferenca diferença entao então
gostaria quero saber sei me favor exemplo exemplos sobre melhor hoje atual atualmente agora
""".split())

# Verbos genéricos: participam da pontuação, mas não contam como "assunto" da pergunta na cobertura mínima
GENERICOS = set("""
interpretar interpreta interpretacao escolher escolha escolhe avaliar avalia calcular calcula calculo funcionar usar
utilizar entender aprender ensinar estudar aplicar aplica obter determinar definir conceito importante principais
principal
""".split())

SIMBOLOS = {"p", "k", "n", "s", "b", "ca", "mg", "zn", "cu", "mn", "fe", "al", "mo", "v", "m", "ua", "pv"}

SINONIMOS = {
    "p": ["fosforo"], "k": ["potassio"], "n": ["nitrogenio"], "s": ["enxofre"], "b": ["boro"], "ca": ["calcio"],
    "mg": ["magnesio"], "zn": ["zinco"], "cu": ["cobre"], "mn": ["manganes"], "fe": ["ferro"], "al": ["aluminio"],
    "gmd": ["ganho", "medio", "diario"], "zarc": ["zoneamento", "agricola", "risco", "climatico"],
    "zoneamento": ["zarc"], "ua": ["unidade", "animal"], "ctc": ["capacidade", "troca", "cationica"],
    "mo": ["materia", "organica"], "pc205": ["peso", "corrigido", "205"], "prnt": ["calcario"],
    "rendimento": ["carcaca"], "arroba": ["arrobas", "carcaca"], "boi": ["bovino", "bovinos"],
    "bovino": ["boi", "gado"], "gado": ["bovino", "bovinos"], "lote": ["lote", "animais"],
    "rentabilidade": ["lucro", "margem", "receita", "custo"], "lucratividade": ["lucro", "margem"],
    "calagem": ["calcario"], "deficiencia": ["deficiencia", "sintoma"], "toxicidade": ["toxidez", "excesso"],
    "toxidez": ["toxicidade", "excesso"], "cultivar": ["cultivar", "cultivares", "ciclo"],
    "semeadura": ["plantio", "semeadura"], "plantio": ["semeadura"],
}

SUFIXOS = ("amentos", "imentos", "amento", "imento", "acoes", "icoes", "acao", "icao", "mente", "idade", "avel", "ivel",
           "adoras", "adores", "adora", "ador", "antes", "ante", "ando", "endo", "indo", "ados", "adas", "idos", "idas",
           "ado", "ada", "ido", "ida", "ar", "er", "ir", "os", "as", "o", "a", "e")

INTENCAO_CALCULO = re.compile(r"calcul|f[óo]rmula|equa[çc]|conta\b|passo a passo|como (se )?obt", re.IGNORECASE)


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def radical(t: str) -> str:
    if t in SIMBOLOS or t.isdigit() or len(t) <= 3:
        return t
    if t.endswith("coes"):
        t = t[:-4] + "cao"
    elif t.endswith("oes") or t.endswith("aes"):
        t = t[:-3] + "ao"
    elif t.endswith("ais"):
        t = t[:-3] + "al"
    elif t.endswith("eis") and len(t) > 5:
        t = t[:-3] + "el"
    elif t.endswith("s") and not t.endswith("ss") and len(t) > 4:
        t = t[:-1]
    for suf in SUFIXOS:
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    return t


def tokens_brutos(texto: str) -> list[str]:
    t = sem_acento(str(texto or "").lower())
    return [x for x in re.findall(r"[a-z0-9]+", t) if (len(x) > 2 or x in SIMBOLOS or x.isdigit()) and x not in STOPWORDS]


def tokenizar(texto: str) -> list[str]:
    return [radical(x) for x in tokens_brutos(texto)]


def tokenizar_consulta(texto: str) -> list[str]:
    brutos = tokens_brutos(texto)
    extra = [s for b in brutos for s in SINONIMOS.get(b, [])]
    return [radical(x) for x in brutos + extra]


# =====================================================================================================
# Estruturas
# =====================================================================================================
@dataclass
class Referencia:
    """Um item recuperável. `chave` é única na base; `rotulo` ([S1], [D2]) é dado no momento da busca."""
    chave: str
    origem: str                 # 'banco' | 'biblioteca'
    area: str                   # 'agricultura' | 'pecuaria' | 'biblioteca'
    bancos: list[str]           # nomes dos bancos (ex.: solo_database) ou ['biblioteca']
    tipo: str                   # rótulo legível (ex.: 'Tabela de interpretação', 'Fórmula de cálculo')
    titulo: str
    texto: str                  # conteúdo enviado à IA
    fonte: str = ""             # título da publicação/documento
    instituicao: str = ""
    ano: str = ""
    pagina: str = ""
    localizacao: str = ""
    registros: list[str] = field(default_factory=list)
    categoria_tecnica: str = ""
    peso: float = 1.0
    rotulo: str = ""
    pontuacao: float = 0.0

    def citacao(self) -> str:
        partes = [self.fonte or "fonte não informada"]
        meta = ", ".join(x for x in (self.instituicao, str(self.ano or "")) if x)
        if meta:
            partes[0] += f" ({meta})"
        if self.localizacao:
            partes.append(self.localizacao)
        if self.pagina:
            partes.append(f"p. {self.pagina}")
        return " — ".join(partes)

    def para_dict(self) -> dict:
        return {"rotulo": self.rotulo, "chave": self.chave, "origem": self.origem, "area": self.area, "bancos": self.bancos,
                "tipo": self.tipo, "titulo": self.titulo, "fonte": self.fonte, "instituicao": self.instituicao,
                "ano": self.ano, "pagina": self.pagina, "localizacao": self.localizacao, "registros": self.registros[:30],
                "trecho": self.texto[:1200], "pontuacao": round(self.pontuacao, 2)}


class Indice:
    """BM25 em memória, com bônus para termos presentes no título e medida de cobertura da consulta."""

    def __init__(self, itens: list[Referencia], k1: float = 1.4, b: float = 0.6, fundo: Optional["Indice"] = None):
        """`fundo`: outro índice cujas estatísticas de frequência são somadas ao cálculo do IDF (usado pela biblioteca,
        que costuma ter poucos documentos — sem isso, termos presentes em todos os trechos teriam peso quase nulo)."""
        self.itens = itens
        self.k1, self.b = k1, b
        self._tf: list[Counter] = []
        self._titulo: list[set] = []
        self._len: list[int] = []
        df: Counter = Counter()
        for it in itens:
            tit = tokenizar(it.titulo)
            corpo = [t for t in tokenizar(f"{it.tipo} {it.texto}") if not t.isdigit()]
            toks = tit + corpo
            c = Counter(toks)
            self._tf.append(c)
            self._titulo.append(set(tit))
            self._len.append(len(toks) or 1)
            df.update(c.keys())
        self.df = df
        self.n = len(itens) or 1
        if fundo is not None:
            n_tot = self.n + fundo.n
            self._idf = {t: math.log(1 + (n_tot - (d + fundo.df.get(t, 0)) + 0.5) / (d + fundo.df.get(t, 0) + 0.5))
                         for t, d in df.items()}
            self.n = n_tot
        else:
            self._idf = {t: math.log(1 + (self.n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._idf_max = math.log(1 + (self.n + 0.5) / 0.5)
        self._media = (sum(self._len) / len(self._len)) if self._len else 1.0

    def __len__(self):
        return len(self.itens)

    def idf(self, t: str) -> float:
        return self._idf.get(t, self._idf_max)

    def pontuar(self, consulta_tokens: list[str], essenciais: Optional[dict[str, set]] = None,
                cobertura_min: float = 0.0) -> list[tuple[float, int]]:
        """Retorna (pontuação, índice). `essenciais` ({termo da pergunta: termo + sinônimos}) definem a cobertura mínima
        ponderada pelo IDF: itens que tocam apenas uma parte pequena do assunto da pergunta são descartados."""
        termos = Counter(consulta_tokens)
        ess = essenciais or {}
        peso_ess = sum(self.idf(t) for t in ess) or 1.0
        res = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            dl = self._len[i]
            for t, qtd in termos.items():
                f = tf.get(t)
                if not f:
                    continue
                idf = self._idf.get(t, 0.0)
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self._media))
                if t in self._titulo[i]:
                    s += 0.8 * idf
            if s <= 0:
                continue
            if ess and cobertura_min > 0:
                cob = sum(self.idf(t) for t, membros in ess.items() if any(m in tf for m in membros)) / peso_ess
                if cob < cobertura_min:
                    continue
            res.append((s * self.itens[i].peso, i))
        res.sort(reverse=True)
        return res


# =====================================================================================================
# Conversão dos registros dos bancos
# =====================================================================================================
ROTULOS_CATEGORIA = {
    "faixa_interpretacao": "Tabela de interpretação", "faixa_suficiencia": "Faixa de suficiência foliar",
    "nivel_critico": "Nível crítico", "equacao": "Equação", "criterio_calagem": "Critério de calagem",
    "criterio_gessagem": "Critério de gessagem", "criterio_adubacao": "Critério de adubação",
    "recomendacao_dose": "Dose indicada na fonte", "conceito": "Conceito", "sintoma": "Sintoma visual",
    "exigencia_nutricional": "Exigência nutricional", "zoneamento": "Zoneamento (ZARC)",
    "temperatura": "Exigência de temperatura", "necessidade_hidrica": "Necessidade hídrica", "fenologia": "Fenologia",
}
AGRUPAVEIS = ("faixa_interpretacao", "faixa_suficiencia", "nivel_critico", "chance_matematica_classe",
              "produtividade_por_classe", "classe_textura", "teor_foliar_referencia")
NOME_BANCO = {k: v["nome"] for k, v in BANCOS.items()}


def _v(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(x, float):
        return f"{x:g}".replace(".", ",")
    return str(x).strip()


def _pagina(*vals) -> str:
    for v in vals:
        s = _v(v)
        if s:
            return s[:-2] if s.endswith(",0") else s
    return ""


def rotulo_categoria(cat: str) -> str:
    return ROTULOS_CATEGORIA.get(cat, (cat or "registro").replace("_", " ").capitalize())


def faixa_texto(op_min, vmin, op_max, vmax, valor=None, unidade="") -> str:
    a, b, v = _v(vmin), _v(vmax), _v(valor)
    u = f" {unidade}" if unidade else ""
    if a and b:
        return f"{_v(op_min) or '≥'} {a} e {_v(op_max) or '≤'} {b}{u}"
    if a:
        return f"{_v(op_min) or '≥'} {a}{u}"
    if b:
        return f"{_v(op_max) or '≤'} {b}{u}"
    if v:
        return f"{v}{u}"
    return ""


def _linha_campos(r: dict, campos: Iterable[tuple[str, str]]) -> str:
    return " | ".join(f"{rot}: {_v(r.get(c))}" for c, rot in campos if _v(r.get(c)))


CAMPOS_CONTEXTO_AGRI = (("cultura", "Cultura"), ("regiao", "Região"), ("camada", "Camada"), ("metodo", "Método"),
                        ("estagio", "Estádio"), ("parte_planta", "Parte da planta"), ("nutriente", "Nutriente"))


def referencias_agricolas(chave: str, df: pd.DataFrame) -> list[Referencia]:
    banco = NOME_BANCO.get(chave, chave)
    out: list[Referencia] = []
    if df is None or df.empty:
        return out
    linhas = df.to_dict("records")
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for r in linhas:
        cat = _v(r.get("categoria"))
        if cat in AGRUPAVEIS:
            k = tuple(_v(r.get(c)) for c in ("categoria", "parametro", "nutriente", "cultura", "regiao", "metodo", "camada",
                                              "estagio", "parte_planta", "condicoes", "fonte_id", "secao"))
            grupos[k].append(r)
        else:
            out.append(_referencia_agricola_simples(banco, r))
    for k, rs in grupos.items():
        r0 = rs[0]
        cat = _v(r0.get("categoria"))
        titulo = _v(r0.get("parametro")) or _v(r0.get("nutriente")) or rotulo_categoria(cat)
        cab = _linha_campos(r0, CAMPOS_CONTEXTO_AGRI)
        corpo = []
        for r in rs:
            faixa = faixa_texto(r.get("operador_min"), r.get("valor_min"), r.get("operador_max"), r.get("valor_max"),
                                r.get("valor"), _v(r.get("unidade")))
            pref = f"{_v(r.get('tipo_solo'))}: " if _v(r.get("tipo_solo")) else ""
            cls = _v(r.get("classificacao"))
            extra = f" ({_v(r.get('texto'))})" if _v(r.get("texto")) and len(rs) <= 6 else ""
            corpo.append(f"- {pref}{faixa} → {cls}{extra}".strip())
        cond = _v(r0.get("condicoes"))
        obs = _v(r0.get("observacoes"))
        texto = "\n".join(x for x in [cab, *corpo, f"Condições de aplicação: {cond}" if cond else "",
                                      f"Observações: {obs}" if obs else ""] if x)
        out.append(Referencia(
            chave=f"{banco}:{cat}:{r0.get('registro_id')}", origem="banco", area="agricultura", bancos=[banco],
            tipo=rotulo_categoria(cat), titulo=titulo, texto=texto, fonte=_v(r0.get("fonte_titulo")),
            instituicao=_v(r0.get("fonte_instituicao")), ano=_v(r0.get("fonte_ano")),
            pagina=_pagina(r0.get("pagina_impressa"), r0.get("pagina_pdf")), localizacao=_v(r0.get("secao")),
            registros=[_v(r.get("registro_id")) for r in rs], categoria_tecnica=cat, peso=1.3))
    return out


def _referencia_agricola_simples(banco: str, r: dict) -> Referencia:
    cat = _v(r.get("categoria"))
    titulo = _v(r.get("parametro")) or (f"{rotulo_categoria(cat)} — {_v(r.get('nutriente'))}" if _v(r.get("nutriente"))
                                        else rotulo_categoria(cat))
    faixa = faixa_texto(r.get("operador_min"), r.get("valor_min"), r.get("operador_max"), r.get("valor_max"),
                        r.get("valor"), _v(r.get("unidade")))
    linhas = [_linha_campos(r, CAMPOS_CONTEXTO_AGRI + (("tipo_solo", "Solo/condição"),))]
    if faixa:
        linhas.append(f"Valor de referência: {faixa}")
    for c, rot in (("classificacao", "Classificação"), ("texto", "Conteúdo"), ("condicoes", "Condições de aplicação"),
                   ("causas", "Causas"), ("observacoes", "Observações")):
        if _v(r.get(c)):
            linhas.append(f"{rot}: {_v(r.get(c))}")
    peso = 1.25 if cat in ("equacao", "conceito") else 1.0
    return Referencia(
        chave=f"{banco}:{r.get('registro_id')}", origem="banco", area="agricultura", bancos=[banco],
        tipo=rotulo_categoria(cat), titulo=titulo, texto="\n".join(x for x in linhas if x), fonte=_v(r.get("fonte_titulo")),
        instituicao=_v(r.get("fonte_instituicao")), ano=_v(r.get("fonte_ano")),
        pagina=_pagina(r.get("pagina_impressa"), r.get("pagina_pdf")), localizacao=_v(r.get("secao")),
        registros=[_v(r.get("registro_id"))], categoria_tecnica=cat, peso=peso)


def referencias_parametros(banco: str, df: pd.DataFrame) -> list[Referencia]:
    out = []
    for r in (df.to_dict("records") if df is not None else []):
        faixa = _v(r.get("valor_texto_original"))
        linhas = [_v(r.get("descricao_tecnica")),
                  _linha_campos(r, (("tema", "Tema"), ("raca", "Raça/genótipo"), ("sexo", "Sexo"), ("idade_fase", "Idade/fase"),
                                    ("fase", "Fase produtiva"), ("sistema", "Sistema"), ("periodo_referencia", "Período"))),
                  f"Valor na fonte: {faixa} ({_v(r.get('unidade_padrao'))})" if faixa else "",
                  f"Condições de aplicação: {_v(r.get('condicoes_aplicacao'))}" if _v(r.get("condicoes_aplicacao")) else "",
                  f"Tipo de dado: {_v(r.get('tipo_dado')).replace('_', ' ')}" if _v(r.get("tipo_dado")) else ""]
        out.append(Referencia(
            chave=f"pec:par:{r.get('id_registro')}", origem="banco", area="pecuaria", bancos=[banco], tipo="Parâmetro técnico",
            titulo=_v(r.get("parametro")), texto="\n".join(x for x in linhas if x), fonte=_v(r.get("fonte_titulo")),
            instituicao=_v(r.get("fonte_instituicao")), ano=_v(r.get("fonte_ano")),
            pagina=_pagina(r.get("pagina_impressa"), r.get("pagina_pdf")), localizacao=_v(r.get("localizacao")),
            registros=[_v(r.get("id_registro"))], categoria_tecnica=_v(r.get("categoria")), peso=0.95))
    return out


def referencias_formulas(banco: str, df: pd.DataFrame) -> list[Referencia]:
    out = []
    for r in (df.to_dict("records") if df is not None else []):
        linhas = [f"Expressão: {_v(r.get('expressao'))}", f"Variáveis: {_v(r.get('variaveis'))}",
                  f"Unidade do resultado: {_v(r.get('unidade_resultado'))}",
                  f"Observações da curadoria: {_v(r.get('observacoes'))}" if _v(r.get("observacoes")) else ""]
        out.append(Referencia(
            chave=f"pec:formula:{r.get('formula_codigo')}", origem="banco", area="pecuaria", bancos=[banco],
            tipo="Fórmula de cálculo", titulo=f"{_v(r.get('nome'))} ({_v(r.get('formula_codigo'))})",
            texto="\n".join(x for x in linhas if x), fonte=_v(r.get("fonte_titulo")), instituicao=_v(r.get("fonte_instituicao")),
            ano=_v(r.get("fonte_ano")), pagina=_pagina(r.get("pagina_pdf")), localizacao="",
            registros=[_v(r.get("formula_codigo"))], categoria_tecnica="formula", peso=1.35))
    return out


def referencias_perguntas(banco: str, df: pd.DataFrame) -> list[Referencia]:
    out = []
    for r in (df.to_dict("records") if df is not None else []):
        resp = _v(r.get("resposta"))
        if r.get("possui_conteudo_nao_transcrito") in (True, "t", "true", 1):
            resp += "\n(Atenção: a resposta original contém tabela ou figura não transcrita.)"
        out.append(Referencia(
            chave=f"pec:qa:{r.get('id_pergunta')}", origem="banco", area="pecuaria", bancos=[banco],
            tipo="Pergunta e resposta da publicação", titulo=_v(r.get("pergunta")), texto=f"Resposta da fonte: {resp}",
            fonte=_v(r.get("fonte_titulo")), instituicao=_v(r.get("fonte_instituicao")), ano=_v(r.get("fonte_ano")),
            pagina=_pagina(r.get("pagina_impressa_inicio"), r.get("pagina_pdf_inicio")),
            localizacao=_v(r.get("localizacao")), registros=[_v(r.get("id_pergunta"))],
            categoria_tecnica=_v(r.get("temas")), peso=1.0))
    return out


def _mesclar(refs: list[Referencia]) -> list[Referencia]:
    """Registros idênticos presentes em mais de um banco de pecuária aparecem uma vez, com a lista de bancos."""
    por_chave: dict[str, Referencia] = {}
    for r in refs:
        if r.chave in por_chave:
            for b in r.bancos:
                if b not in por_chave[r.chave].bancos:
                    por_chave[r.chave].bancos.append(b)
        else:
            por_chave[r.chave] = r
    return list(por_chave.values())


# =====================================================================================================
# Base de conhecimento dos bancos (cache por processo)
# =====================================================================================================
@dataclass
class BaseBancos:
    indice: Indice
    disponiveis: list[str]
    indisponiveis: dict[str, str]
    carregado_em: float
    contagem: dict[str, int]


_cache_bancos: Optional[BaseBancos] = None
_lock = threading.Lock()
TTL_S = 3600


def carregar_base_bancos(forcar: bool = False) -> BaseBancos:
    global _cache_bancos
    with _lock:
        if _cache_bancos is not None and not forcar and time.time() - _cache_bancos.carregado_em < TTL_S \
                and not _cache_bancos.indisponiveis:
            return _cache_bancos
        refs: list[Referencia] = []
        disp, indisp, cont = [], {}, {}
        for chave in eq.BANCOS_AGRICOLAS:
            try:
                novos = referencias_agricolas(chave, eq.registros_agricolas(chave))
                refs += novos
                disp.append(NOME_BANCO[chave])
                cont[NOME_BANCO[chave]] = len(novos)
            except BancoIndisponivel as e:
                indisp[NOME_BANCO[chave]] = str(e)
        pec: list[Referencia] = []
        for chave in eq.BANCOS_PECUARIOS:
            nome = NOME_BANCO[chave]
            try:
                novos = (referencias_parametros(nome, eq.parametros_pecuarios(chave))
                         + referencias_formulas(nome, eq.formulas_pecuarias(chave))
                         + referencias_perguntas(nome, eq.perguntas_pecuarias(chave)))
                pec += novos
                disp.append(nome)
                cont[nome] = len(novos)
            except BancoIndisponivel as e:
                indisp[nome] = str(e)
        refs += _mesclar(pec)
        _cache_bancos = BaseBancos(Indice(refs), disp, indisp, time.time(), cont)
        return _cache_bancos


def invalidar_bancos() -> None:
    global _cache_bancos
    with _lock:
        _cache_bancos = None


# =====================================================================================================
# Biblioteca (trechos de documentos)
# =====================================================================================================
_cache_bib: dict = {"versao": None, "indice": None}


def _versao_biblioteca() -> tuple:
    from modules.eduagro_ai import armazenamento as arm
    r = arm.um("SELECT count(*) AS n, coalesce(max(id), 0) AS m FROM trecho")
    return (str(arm.caminho_banco()), r["n"], r["m"]) if r else (str(arm.caminho_banco()), 0, 0)


def carregar_indice_biblioteca(fundo: Optional[Indice] = None) -> Indice:
    from modules.eduagro_ai import armazenamento as arm
    versao = _versao_biblioteca() + (id(fundo),)
    if _cache_bib["versao"] == versao and _cache_bib["indice"] is not None:
        return _cache_bib["indice"]
    linhas = arm.consultar("""SELECT t.id, t.documento_id, t.pagina, t.ordem, t.texto, d.titulo, d.tipo_material, d.categoria,
                                     d.autores, d.instituicao, d.ano
                              FROM trecho t JOIN documento d ON d.id = t.documento_id
                              WHERE d.status = 'indexado' ORDER BY t.documento_id, t.ordem""")
    refs = [Referencia(chave=f"doc:{r['documento_id']}:{r['id']}", origem="biblioteca", area="biblioteca", bancos=["biblioteca"],
                       tipo=f"Documento da biblioteca ({r['tipo_material']})", titulo=r["titulo"], texto=r["texto"],
                       fonte=r["titulo"], instituicao=r["instituicao"] or r["autores"] or "", ano=r["ano"] or "",
                       pagina=str(r["pagina"] or ""), localizacao=f"categoria {r['categoria']}",
                       registros=[f"documento {r['documento_id']}, trecho {r['ordem']}"], categoria_tecnica=r["categoria"])
            for r in linhas]
    _cache_bib.update(versao=versao, indice=Indice(refs, fundo=fundo))
    return _cache_bib["indice"]


# =====================================================================================================
# Busca
# =====================================================================================================
AREAS = {"todas": None, "agricultura": {"agricultura"}, "pecuaria": {"pecuaria"}}


@dataclass
class ResultadoBusca:
    consulta: str
    referencias: list[Referencia]
    bancos_consultados: list[str]
    bancos_indisponiveis: dict[str, str]
    biblioteca_consultada: bool
    documentos_na_biblioteca: int
    internet_consultada: bool = False
    erro_internet: str = ""

    @property
    def vazio(self) -> bool:
        return not self.referencias

    @property
    def sem_fontes_safratech(self) -> bool:
        """Nada encontrado nos bancos do SafraTech nem na Biblioteca (critério para recorrer à internet)."""
        return not any(r.origem in ("banco", "biblioteca") for r in self.referencias)

    @property
    def da_internet(self) -> list[Referencia]:
        return [r for r in self.referencias if r.origem == "internet"]

    @property
    def do_banco(self) -> list[Referencia]:
        return [r for r in self.referencias if r.origem == "banco"]

    @property
    def da_biblioteca(self) -> list[Referencia]:
        return [r for r in self.referencias if r.origem == "biblioteca"]


def _selecionar(indice: Indice, toks: list[str], essenciais: dict[str, set], k: int, filtro: Callable[[Referencia], bool],
                calculo: bool, minimo_abs: float, relativo: float, max_por_tipo: int, cobertura: float) -> list[Referencia]:
    pont = []
    for s, i in indice.pontuar(toks, essenciais, cobertura):
        it = indice.itens[i]
        if not filtro(it):
            continue
        if calculo and it.categoria_tecnica in ("formula", "equacao"):
            s *= 1.6
        pont.append((s, i))
    pont.sort(reverse=True)
    if not pont or pont[0][0] < minimo_abs:
        return []
    topo = pont[0][0]
    escolhidos, por_tipo = [], Counter()
    for s, i in pont:
        if s < max(minimo_abs, relativo * topo):
            break
        it = indice.itens[i]
        if por_tipo[it.tipo] >= max_por_tipo:
            continue
        por_tipo[it.tipo] += 1
        ref = Referencia(**{**it.__dict__, "bancos": list(it.bancos), "registros": list(it.registros)})
        ref.pontuacao = s
        escolhidos.append(ref)
        if len(escolhidos) >= k:
            break
    return escolhidos


def buscar(consulta: str, area: str = "todas", k_bancos: int = 7, k_biblioteca: int = 4, usar_bancos: bool = True,
           usar_biblioteca: bool = True, minimo_abs: float = 4.0, relativo: float = 0.35,
           cobertura: float = 0.4) -> ResultadoBusca:
    """Busca na base dos bancos e na biblioteca. Nunca levanta exceção por banco indisponível."""
    toks = tokenizar_consulta(consulta)
    essenciais = {radical(b): {radical(b)} | {radical(x) for x in SINONIMOS.get(b, [])}
                  for b in tokens_brutos(consulta) if b not in GENERICOS}
    calculo = bool(INTENCAO_CALCULO.search(consulta or ""))
    areas = AREAS.get(area)
    refs: list[Referencia] = []
    consultados, indisp = [], {}
    base = None
    if usar_bancos and toks:
        base = carregar_base_bancos()
        consultados, indisp = list(base.disponiveis), dict(base.indisponiveis)
        refs += _selecionar(base.indice, toks, essenciais, k_bancos, lambda r: areas is None or r.area in areas, calculo,
                            minimo_abs, relativo, max_por_tipo=4, cobertura=cobertura)
    n_docs = 0
    if usar_biblioteca and toks:
        try:
            if base is None:
                try:
                    base = carregar_base_bancos()
                except Exception:
                    base = None
            ind = carregar_indice_biblioteca(base.indice if base is not None and len(base.indice) else None)
            n_docs = len({r.chave.split(":")[1] for r in ind.itens})
            refs += _selecionar(ind, toks, essenciais, k_biblioteca, lambda r: True, False, minimo_abs * 0.8, relativo,
                                max_por_tipo=k_biblioteca, cobertura=cobertura)
        except Exception:  # biblioteca vazia ou arquivo ainda não criado
            pass
    s = d = 0
    for r in refs:
        if r.origem == "banco":
            s += 1
            r.rotulo = f"S{s}"
        else:
            d += 1
            r.rotulo = f"D{d}"
    return ResultadoBusca(consulta, refs, consultados, indisp, usar_biblioteca, n_docs)


def anexar_internet(resultado: ResultadoBusca, paginas: list) -> ResultadoBusca:
    """Acrescenta páginas da internet (web_search.ResultadoWeb) como referências [W1], [W2]..."""
    for i, p in enumerate(paginas, start=1):
        resultado.referencias.append(Referencia(
            chave=f"web:{p.url}", origem="internet", area="internet", bancos=["internet"],
            tipo="Página da internet", titulo=p.titulo, texto=p.conteudo,
            fonte=p.site or p.url, localizacao=p.url, registros=[p.url], categoria_tecnica="internet",
            rotulo=f"W{i}", pontuacao=p.pontuacao))
    resultado.internet_consultada = True
    return resultado


def formatar_contexto(resultado: ResultadoBusca, limite_por_item: int = 1400) -> str:
    """Bloco de contexto enviado à IA, com os rótulos que ela deve citar."""
    if resultado.vazio:
        aviso = "NENHUMA referência relevante foi encontrada nos bancos do SafraTech nem na biblioteca para esta pergunta."
        if resultado.internet_consultada:
            aviso += " A busca na internet também não trouxe resultados" + (
                f" ({resultado.erro_internet})." if resultado.erro_internet else ".")
        return aviso
    blocos = []
    if resultado.sem_fontes_safratech and resultado.da_internet and resultado.bancos_consultados:
        blocos.append("ATENÇÃO: nada foi encontrado nos bancos do SafraTech nem na biblioteca. Os trechos [W#] abaixo vêm de "
                      "páginas da internet, NÃO verificadas pelo SafraTech.")
    for r in resultado.referencias:
        texto = r.texto if len(r.texto) <= limite_por_item else r.texto[:limite_por_item].rsplit(" ", 1)[0] + " […]"
        origem = ", ".join(r.bancos)
        regs = ", ".join(r.registros[:6]) + (f" (+{len(r.registros) - 6})" if len(r.registros) > 6 else "")
        if r.origem == "internet":
            blocos.append(f"[{r.rotulo}] {r.tipo} — {r.titulo}\nSite: {r.fonte} · Endereço: {r.localizacao}\n{texto}")
            continue
        blocos.append(f"[{r.rotulo}] {r.tipo} — {r.titulo}\nOrigem: {origem} · registro(s): {regs}\n"
                      f"Fonte: {r.citacao()}\n{texto}")
    return "\n\n".join(blocos)
