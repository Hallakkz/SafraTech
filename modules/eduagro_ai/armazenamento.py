"""
Persistência do EduAgro AI em SQLite local (biblioteca padrão do Python, sem servidor).

Por que não nos bancos PostgreSQL do SafraTech? Os seis bancos técnicos são abertos SEMPRE em modo somente leitura
(database/connections.py) e nunca são alterados pelo aplicativo. Conversas, progresso, cursos cadastrados e a biblioteca
de documentos são dados do usuário, por isso ficam num arquivo próprio:

    <raiz do projeto>/dados_eduagro/eduagro.db       (pasta configurável por EDUAGRO_DADOS_DIR)

O SafraTech não possui autenticação de usuários; o EduAgro usa um "perfil de estudante" (apenas um nome) para separar
o progresso de quem usa o mesmo computador. Não é um sistema de login.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

RAIZ = Path(__file__).resolve().parent.parent.parent

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    nivel TEXT NOT NULL DEFAULT 'Iniciante',
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    nivel TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensagem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id INTEGER NOT NULL REFERENCES conversa(id) ON DELETE CASCADE,
    papel TEXT NOT NULL CHECK (papel IN ('user', 'assistant')),
    conteudo TEXT NOT NULL,
    referencias_json TEXT,
    meta_json TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS curso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    descricao TEXT,
    categoria TEXT NOT NULL,
    nivel TEXT NOT NULL,
    objetivos TEXT,
    ordem INTEGER DEFAULT 0,
    origem TEXT NOT NULL DEFAULT 'catalogo',
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aula (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curso_id INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL DEFAULT 1,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    resumo TEXT,
    exemplos TEXT,
    referencias TEXT,
    origem TEXT NOT NULL DEFAULT 'proprio',
    revisada INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    tipo_material TEXT NOT NULL,
    categoria TEXT NOT NULL,
    autores TEXT,
    instituicao TEXT,
    ano TEXT,
    referencia TEXT,
    arquivo TEXT,
    nome_original TEXT,
    sha256 TEXT UNIQUE,
    paginas INTEGER DEFAULT 0,
    trechos INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendente',
    observacoes TEXT,
    origem TEXT NOT NULL DEFAULT 'upload',
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trecho (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    pagina INTEGER,
    ordem INTEGER NOT NULL,
    texto TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_trecho_doc ON trecho(documento_id);
CREATE TABLE IF NOT EXISTS questao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curso_id INTEGER REFERENCES curso(id) ON DELETE SET NULL,
    aula_id INTEGER REFERENCES aula(id) ON DELETE SET NULL,
    tema TEXT,
    categoria TEXT,
    tipo TEXT NOT NULL,
    enunciado TEXT NOT NULL,
    alternativas_json TEXT,
    resposta TEXT,
    resposta_numerica REAL,
    tolerancia REAL,
    tolerancia_abs REAL,
    explicacao TEXT,
    justificativa TEXT,
    referencias_json TEXT,
    assuntos TEXT,
    nivel TEXT,
    origem TEXT NOT NULL,
    avaliacao_final INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avaliacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    curso_id INTEGER REFERENCES curso(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL,
    categoria TEXT,
    final INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    acertos REAL NOT NULL,
    nota REAL NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tentativa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    questao_id INTEGER REFERENCES questao(id) ON DELETE SET NULL,
    avaliacao_id INTEGER REFERENCES avaliacao(id) ON DELETE CASCADE,
    resposta_usuario TEXT,
    correta INTEGER NOT NULL,
    pontuacao REAL NOT NULL,
    feedback TEXT,
    categoria TEXT,
    tema TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matricula (
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    curso_id INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'em_andamento',
    iniciado_em TEXT NOT NULL,
    concluido_em TEXT,
    PRIMARY KEY (usuario_id, curso_id)
);
CREATE TABLE IF NOT EXISTS aula_concluida (
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    aula_id INTEGER NOT NULL REFERENCES aula(id) ON DELETE CASCADE,
    concluido_em TEXT NOT NULL,
    PRIMARY KEY (usuario_id, aula_id)
);
CREATE TABLE IF NOT EXISTS evento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT,
    criado_em TEXT NOT NULL
);
"""

_lock = threading.Lock()
_iniciados: set[str] = set()


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def pasta_dados() -> Path:
    return Path(os.environ.get("EDUAGRO_DADOS_DIR") or (RAIZ / "dados_eduagro"))


def caminho_banco() -> Path:
    return pasta_dados() / "eduagro.db"


def pasta_biblioteca() -> Path:
    p = pasta_dados() / "biblioteca"
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def conexao():
    """Abre uma conexão curta (uma por operação: seguro com as várias threads do Streamlit)."""
    caminho = caminho_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        chave = str(caminho)
        if chave not in _iniciados:
            with _lock:
                if chave not in _iniciados:
                    con.execute("PRAGMA journal_mode = WAL")
                    con.executescript(ESQUEMA)
                    _iniciados.add(chave)
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reiniciar_cache_de_esquema() -> None:
    """Usado pelos testes quando EDUAGRO_DADOS_DIR muda."""
    _iniciados.clear()


def consultar(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with conexao() as con:
        return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]


def um(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    linhas = consultar(sql, params)
    return linhas[0] if linhas else None


def executar(sql: str, params: Iterable[Any] = ()) -> int:
    """Executa INSERT/UPDATE/DELETE e devolve o id da última linha inserida."""
    with conexao() as con:
        cur = con.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def executar_varios(sql: str, linhas: Iterable[Iterable[Any]]) -> None:
    with conexao() as con:
        con.executemany(sql, [tuple(x) for x in linhas])


def jdump(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def jload(t: Optional[str], padrao: Any = None) -> Any:
    if not t:
        return padrao
    try:
        return json.loads(t)
    except (TypeError, ValueError):
        return padrao


# =====================================================================================================
# Perfis de estudante
# =====================================================================================================
PERFIL_PADRAO = "Estudante"


def obter_ou_criar_usuario(nome: str) -> dict:
    nome = " ".join((nome or PERFIL_PADRAO).split())[:60] or PERFIL_PADRAO
    u = um("SELECT id, nome, nivel FROM usuario WHERE nome = ?", (nome,))
    if u:
        return u
    executar("INSERT OR IGNORE INTO usuario (nome, criado_em) VALUES (?, ?)", (nome, agora()))
    return um("SELECT id, nome, nivel FROM usuario WHERE nome = ?", (nome,))  # type: ignore[return-value]


def listar_usuarios() -> list[dict]:
    return consultar("SELECT id, nome, nivel FROM usuario ORDER BY nome")


def definir_nivel(usuario_id: int, nivel: str) -> None:
    executar("UPDATE usuario SET nivel = ? WHERE id = ?", (nivel, usuario_id))


def registrar_evento(usuario_id: int, tipo: str, descricao: str, categoria: Optional[str] = None) -> None:
    executar("INSERT INTO evento (usuario_id, tipo, descricao, categoria, criado_em) VALUES (?, ?, ?, ?, ?)",
             (usuario_id, tipo, descricao[:300], categoria, agora()))
