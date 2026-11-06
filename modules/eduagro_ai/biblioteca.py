"""
Biblioteca de Conhecimento Agro — lógica (sem interface).

- Cadastro de materiais (PDF, TXT, MD) com metadados: tipo de material, categoria, autores, instituição, ano, referência.
- O arquivo é copiado para dados_eduagro/biblioteca/ e o texto é extraído POR PÁGINA (pypdf) e dividido em trechos
  com sobreposição, guardados na tabela `trecho` (documento + página + ordem).
- A busca por trechos (RAG) é feita por knowledge_retrieval.py; as respostas do tutor citam documento e página.
- PDFs digitalizados sem camada de texto (imagem) não têm texto extraível: o documento fica com status
  "sem_texto" e é informado na interface (OCR não faz parte desta versão).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from modules.eduagro_ai import armazenamento as arm

TIPOS_MATERIAL = ("PDF", "Apostila", "Manual técnico", "Publicação científica", "Material da Embrapa", "Guia de estudo",
                  "Documento próprio")
CATEGORIAS = ("Agricultura", "Pecuária", "Solo", "Nutrição vegetal", "Clima", "Gestão rural", "Economia agropecuária")
EXTENSOES = (".pdf", ".txt", ".md")
TAMANHO_TRECHO = 1200
SOBREPOSICAO = 200
LIMITE_MB = 80


@dataclass
class ResultadoImportacao:
    documento_id: Optional[int]
    paginas: int
    trechos: int
    status: str
    mensagem: str


def _limpar(texto: str) -> str:
    t = texto.replace("­", "").replace("\x00", " ")
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)          # palavras hifenizadas na quebra de linha
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extrair_paginas(nome: str, dados: bytes, progresso: Optional[Callable[[float], None]] = None) -> list[tuple[int, str]]:
    """Retorna [(página, texto)]. TXT/MD viram páginas lógicas de ~3000 caracteres."""
    ext = Path(nome).suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("A biblioteca 'pypdf' não está instalada (pip install -r requirements.txt).") from e
        leitor = PdfReader(io.BytesIO(dados))
        if leitor.is_encrypted:
            try:
                leitor.decrypt("")
            except Exception as e:
                raise RuntimeError("O PDF está protegido por senha.") from e
        total = len(leitor.pages)
        paginas = []
        for i, pg in enumerate(leitor.pages, start=1):
            try:
                txt = pg.extract_text() or ""
            except Exception:
                txt = ""
            paginas.append((i, _limpar(txt)))
            if progresso and (i % 5 == 0 or i == total):
                progresso(i / max(total, 1))
        return paginas
    if ext in (".txt", ".md"):
        texto = None
        for cod in ("utf-8", "latin-1"):
            try:
                texto = dados.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        texto = _limpar(texto or "")
        blocos, atual = [], ""
        for par in texto.split("\n\n"):
            if len(atual) + len(par) > 3000 and atual:
                blocos.append(atual)
                atual = ""
            atual += par + "\n\n"
        if atual.strip():
            blocos.append(atual)
        return [(i, b.strip()) for i, b in enumerate(blocos, start=1)]
    raise ValueError(f"Formato não suportado: {ext or 'sem extensão'}. Use PDF, TXT ou MD.")


def dividir_em_trechos(paginas: list[tuple[int, str]], tamanho: int = TAMANHO_TRECHO, sobreposicao: int = SOBREPOSICAO) -> list[tuple[int, str]]:
    """Divide cada página em trechos (sem misturar páginas, para preservar a citação da página)."""
    trechos = []
    for pagina, texto in paginas:
        texto = texto.strip()
        if len(texto) < 40:
            continue
        inicio = 0
        while inicio < len(texto):
            fim = min(len(texto), inicio + tamanho)
            if fim < len(texto):
                corte = max(texto.rfind(". ", inicio, fim), texto.rfind("\n", inicio, fim))
                if corte > inicio + tamanho // 2:
                    fim = corte + 1
            trechos.append((pagina, texto[inicio:fim].strip()))
            if fim >= len(texto):
                break
            novo = max(fim - sobreposicao, inicio + 1)
            espaco = texto.find(" ", novo, fim)        # recomeça no início de uma palavra
            inicio = espaco + 1 if 0 <= espaco < fim - 1 else novo
    return trechos


def _nome_seguro(nome: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(nome).name)[:80]
    return base or "documento"


def cadastrar_documento(nome_arquivo: str, dados: bytes, titulo: str, tipo_material: str, categoria: str, autores: str = "",
                        instituicao: str = "", ano: str = "", referencia: str = "", observacoes: str = "",
                        origem: str = "upload", progresso: Optional[Callable[[float], None]] = None) -> ResultadoImportacao:
    """Guarda o arquivo, extrai o texto por página e indexa os trechos. Documentos repetidos (mesmo SHA-256) são recusados."""
    if not titulo.strip():
        raise ValueError("Informe o título do material.")
    if tipo_material not in TIPOS_MATERIAL or categoria not in CATEGORIAS:
        raise ValueError("Tipo de material ou categoria inválidos.")
    if Path(nome_arquivo).suffix.lower() not in EXTENSOES:
        raise ValueError("Formato não suportado. Use PDF, TXT ou MD.")
    if len(dados) > LIMITE_MB * 1024 * 1024:
        raise ValueError(f"Arquivo maior que {LIMITE_MB} MB.")
    sha = hashlib.sha256(dados).hexdigest()
    existente = arm.um("SELECT id, titulo FROM documento WHERE sha256 = ?", (sha,))
    if existente:
        return ResultadoImportacao(existente["id"], 0, 0, "duplicado",
                                   f"Este arquivo já está na biblioteca: “{existente['titulo']}”.")
    destino = arm.pasta_biblioteca() / f"{sha[:12]}_{_nome_seguro(nome_arquivo)}"
    destino.write_bytes(dados)
    doc_id = arm.executar(
        "INSERT INTO documento (titulo, tipo_material, categoria, autores, instituicao, ano, referencia, arquivo, nome_original, "
        "sha256, status, observacoes, origem, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processando', ?, ?, ?)",
        (titulo.strip(), tipo_material, categoria, autores.strip(), instituicao.strip(), str(ano).strip(), referencia.strip(),
         destino.name, Path(nome_arquivo).name, sha, observacoes.strip(), origem, arm.agora()))
    try:
        paginas = extrair_paginas(nome_arquivo, dados, progresso)
    except Exception as e:
        arm.executar("UPDATE documento SET status = 'erro', observacoes = ? WHERE id = ?", (f"Falha na extração: {e}", doc_id))
        return ResultadoImportacao(doc_id, 0, 0, "erro", f"Não foi possível extrair o texto: {e}")
    trechos = dividir_em_trechos(paginas)
    if trechos:
        arm.executar_varios("INSERT INTO trecho (documento_id, pagina, ordem, texto) VALUES (?, ?, ?, ?)",
                            [(doc_id, p, i, t) for i, (p, t) in enumerate(trechos, start=1)])
    status = "indexado" if trechos else "sem_texto"
    arm.executar("UPDATE documento SET paginas = ?, trechos = ?, status = ? WHERE id = ?", (len(paginas), len(trechos), status, doc_id))
    if status == "sem_texto":
        msg = ("Documento guardado, mas nenhuma página tem texto extraível (provavelmente um PDF digitalizado como imagem). "
               "Ele não poderá ser consultado pelo tutor até que uma versão com texto seja cadastrada.")
    else:
        msg = f"Documento indexado: {len(paginas)} página(s), {len(trechos)} trecho(s) disponíveis para consulta."
    return ResultadoImportacao(doc_id, len(paginas), len(trechos), status, msg)


def listar_documentos(categoria: Optional[str] = None, termo: str = "") -> list[dict]:
    sql = ("SELECT id, titulo, tipo_material, categoria, autores, instituicao, ano, referencia, nome_original, paginas, trechos, "
           "status, observacoes, origem, criado_em FROM documento")
    cond, params = [], []
    if categoria:
        cond.append("categoria = ?")
        params.append(categoria)
    if termo.strip():
        cond.append("(titulo LIKE ? OR autores LIKE ? OR instituicao LIKE ?)")
        params += [f"%{termo.strip()}%"] * 3
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return arm.consultar(sql + " ORDER BY criado_em DESC, id DESC", params)


def excluir_documento(doc_id: int) -> None:
    d = arm.um("SELECT arquivo FROM documento WHERE id = ?", (doc_id,))
    arm.executar("DELETE FROM documento WHERE id = ?", (doc_id,))
    if d and d.get("arquivo"):
        try:
            (arm.pasta_biblioteca() / d["arquivo"]).unlink(missing_ok=True)
        except OSError:
            pass


def trechos_do_documento(doc_id: int, limite: int = 5) -> list[dict]:
    return arm.consultar("SELECT pagina, ordem, texto FROM trecho WHERE documento_id = ? ORDER BY ordem LIMIT ?", (doc_id, limite))


# =====================================================================================================
# Materiais de referência já presentes no projeto SafraTech (PDFs das publicações usadas nos bancos de pecuária)
# =====================================================================================================
def materiais_do_safratech() -> list[dict]:
    """Localiza as publicações-fonte guardadas no pacote dos bancos de pecuária (arquivos *.referencia.json + PDFs)."""
    raiz = arm.RAIZ
    encontrados: dict[str, dict] = {}
    fontes_csv: dict[str, dict] = {}
    for pacote in sorted(raiz.glob("BANCO_DE_DADOS_SAFRATECH_PECUARIA*")):
        for csv in pacote.rglob("pecuaria_*_database/dados/csv/fonte.csv"):
            try:
                import pandas as pd
                for r in pd.read_csv(csv).to_dict("records"):
                    fontes_csv.setdefault(str(r.get("fonte_codigo")), r)
            except Exception:
                pass
        for ref in pacote.rglob("*.referencia.json"):
            try:
                info = json.loads(ref.read_text(encoding="utf-8"))
            except Exception:
                continue
            rel = str(info.get("arquivo_fisico") or "").replace("\\", "/")
            base = next((p for p in ref.parents if (p / rel).exists()), None) if rel else None
            if base is None or not rel.lower().endswith(".pdf"):
                continue
            caminho = base / rel
            codigo = str(info.get("fonte_codigo") or caminho.stem)
            f = fontes_csv.get(codigo, {})
            encontrados.setdefault(str(caminho), {
                "codigo": codigo, "caminho": caminho, "titulo": str(info.get("titulo") or f.get("titulo") or caminho.stem),
                "instituicao": str(f.get("instituicao") or ""), "autores": str(f.get("autores") or ""),
                "ano": "" if str(f.get("ano_publicacao") or "nan") == "nan" else str(f.get("ano_publicacao")).replace(".0", ""),
                "referencia": "" if str(f.get("referencia_abnt") or "nan") == "nan" else str(f.get("referencia_abnt")),
                "tamanho_mb": round(caminho.stat().st_size / 1024 / 1024, 1)})
    ja = {d["nome_original"] for d in arm.consultar("SELECT nome_original FROM documento")}
    lista = sorted(encontrados.values(), key=lambda x: x["codigo"])
    for item in lista:
        item["importado"] = item["caminho"].name in ja
    return lista


def importar_material_safratech(item: dict, progresso: Optional[Callable[[float], None]] = None) -> ResultadoImportacao:
    caminho: Path = item["caminho"]
    return cadastrar_documento(caminho.name, caminho.read_bytes(), item["titulo"], "Material da Embrapa", "Pecuária",
                               autores=item.get("autores", ""), instituicao=item.get("instituicao", ""), ano=item.get("ano", ""),
                               referencia=item.get("referencia", ""),
                               observacoes=f"Publicação-fonte dos bancos de pecuária do SafraTech ({item['codigo']}).",
                               origem="safratech", progresso=progresso)
