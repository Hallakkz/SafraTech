@echo off
cd /d "%~dp0\.."
python dados_eduagro\checar_tamanho.py > dados_eduagro\checar_erro.txt 2>&1
