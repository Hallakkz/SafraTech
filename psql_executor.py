"""
Executor de testes que usa o cliente `psql` no lugar do SQLAlchemy/psycopg.

Serve apenas para validar as consultas reais contra os bancos em ambientes onde o driver Python
não está instalado. Os parâmetros nomeados (:nome) são convertidos em literais SQL escapados.
O aplicativo em produção usa database.connections (SQLAlchemy + psycopg) — este módulo não é importado por ele.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import pandas as pd

BANCOS = {"solo": "solo_database", "nutricao": "nutricao_database", "plantio": "plantio_database",
          "pecuaria_compra": "pecuaria_compra_database", "pecuaria_desempenho": "pecuaria_desempenho_database",
          "pecuaria_rentabilidade": "pecuaria_rentabilidade_database"}
_RX = re.compile(r"(?<!:):([A-Za-z_]\w*)")


def _literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        if not v:
            return "ARRAY[]::text[]"
        return "ARRAY[" + ", ".join(_literal(x) for x in v) + "]"
    return "'" + str(v).replace("'", "''") + "'"


def ligar(sql: str, params: dict | None) -> str:
    params = params or {}

    def sub(m):
        nome = m.group(1)
        if nome not in params:
            return m.group(0)
        return _literal(params[nome])

    return _RX.sub(sub, sql)


def executar(chave: str, sql: str, params: dict | None = None) -> pd.DataFrame:
    banco = BANCOS[chave]
    sql_final = ligar(sql, params).strip().rstrip(";")
    embrulhado = f"SELECT row_to_json(t) FROM ({sql_final}) t;"
    # SQL enviado pela entrada padrão em UTF-8 (e não como argumento -c): no Windows os argumentos chegam ao psql na
    # página de código ANSI, o que corrompia acentos e símbolos (≥, −, →) das consultas e dos dados.
    env = {**os.environ, "PGOPTIONS": "-c default_transaction_read_only=on", "PGCLIENTENCODING": "UTF8"}
    proc = subprocess.run(["psql", "-h", os.environ.get("PGHOST", "localhost"), "-U", os.environ.get("PGUSER", "postgres"),
                           "-d", banco, "-At", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                          input=embrulhado, capture_output=True, text=True, encoding="utf-8", env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    linhas = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    if linhas:
        return pd.DataFrame(linhas)
    # sem linhas: obtém os nomes das colunas (como o SQLAlchemy faria)
    cab = subprocess.run(["psql", "-h", os.environ.get("PGHOST", "localhost"), "-U", os.environ.get("PGUSER", "postgres"),
                          "-d", banco, "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                         input=f"SELECT * FROM ({sql_final}) t LIMIT 0;", capture_output=True, text=True, encoding="utf-8",
                         env=env)
    colunas = cab.stdout.strip().split(",") if cab.returncode == 0 and cab.stdout.strip() else []
    return pd.DataFrame(columns=colunas)


def disponivel() -> bool:
    try:
        return subprocess.run(["psql", "-h", "localhost", "-U", "postgres", "-d", "solo_database", "-Atc", "SELECT 1"],
                              capture_output=True, text=True, timeout=10).returncode == 0
    except Exception:
        return False
