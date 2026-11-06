"""
Executa, no computador do usuário, a validação completa do SafraTech + EduAgro AI e grava os resultados em
dados_eduagro/:  validacao_deepseek.md (API real)  e  resultado_pytest.txt (testes automatizados).

- Lê o .env; para os testes de integração, o cliente psql usa o usuário/senha de SOLO_DATABASE_URL
  (somente no processo dos testes) e a pasta bin do PostgreSQL é adicionada ao PATH, se existir.
Uso:  python tests/executar_validacao_windows.py      (ou duplo clique em validar_eduagro.bat)
"""
from __future__ import annotations

import glob
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "dados_eduagro"
SAIDA.mkdir(exist_ok=True)
try:
    from dotenv import dotenv_values
    env_arquivo = dotenv_values(RAIZ / ".env")
except ImportError:
    env_arquivo = {}

amb = {**os.environ, "PYTHONIOENCODING": "utf-8"}
amb.pop("PGCLIENTENCODING", None)   # tests/psql_executor.py define UTF8 e envia o SQL pela entrada padrão
url = env_arquivo.get("SOLO_DATABASE_URL") or os.environ.get("SOLO_DATABASE_URL") or ""
if url:
    u = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    amb.update(PGHOST=u.hostname or "localhost", PGUSER=u.username or "postgres", PGPASSWORD=u.password or "",
               PGPORT=str(u.port or 5432))
for pasta in sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin"), reverse=True):
    amb["PATH"] = pasta + os.pathsep + amb.get("PATH", "")
    break

resumo = [f"Python: {sys.executable} ({sys.version.split()[0]})"]
for mod in ("streamlit", "requests", "pypdf", "plotly", "sqlalchemy", "psycopg", "reportlab", "dotenv", "pytest", "pdfplumber"):
    resumo.append(f"  {mod}: {'ok' if importlib.util.find_spec(mod) else 'NÃO INSTALADO'}")

r = subprocess.run([sys.executable, str(RAIZ / "tests" / "validar_deepseek.py")], cwd=RAIZ, env=amb,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
resumo.append(f"validar_deepseek.py: código de saída {r.returncode}")
(SAIDA / "saida_validar_deepseek.txt").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")

if importlib.util.find_spec("pytest"):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", "tests", "-p", "no:cacheprovider"], cwd=RAIZ, env=amb,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    (SAIDA / "resultado_pytest.txt").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
    resumo.append(f"pytest: código de saída {r.returncode} — " + (r.stdout.strip().splitlines() or ["?"])[-1])
else:
    resumo.append("pytest: não instalado (pip install -r requirements-dev.txt)")
(SAIDA / "resumo_validacao.txt").write_text("\n".join(resumo), encoding="utf-8")
print("\n".join(resumo))
