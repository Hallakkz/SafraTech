@echo off
cd /d "%~dp0\.."
python -m streamlit run main.py --server.headless true --server.port 8503
