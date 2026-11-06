@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
python tests\validar_deepseek.py > dados_eduagro\saida_validar_deepseek.txt 2>&1
