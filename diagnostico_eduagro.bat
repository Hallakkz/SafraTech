@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist dados_eduagro mkdir dados_eduagro
set OUT=dados_eduagro\diagnostico_windows.txt
(
echo === PYTHON ===
where python
where py
where streamlit
python --version
python -c "import sys;print(sys.executable)"
python -c "import streamlit,requests;print('streamlit',streamlit.__version__,'requests',requests.__version__)"
python -c "import pypdf;print('pypdf',pypdf.__version__)"
python -c "import pytest,pdfplumber;print('pytest',pytest.__version__)"
python -c "import sqlalchemy,psycopg,dotenv,plotly,reportlab;print('demais dependencias ok')"
echo === PSQL ===
where psql
dir /b "C:\Program Files\PostgreSQL"
echo === FIM ===
) > %OUT% 2>&1
