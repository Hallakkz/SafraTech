"""Pecuária de Corte do SafraTech: três submódulos integrados aos bancos PostgreSQL de pecuária.

- compra.py         → pecuaria_compra_database         (Análise de Viabilidade de Compra)
- desempenho.py     → pecuaria_desempenho_database     (Diagnóstico de Desempenho do Rebanho)
- rentabilidade.py  → pecuaria_rentabilidade_database  (Simulador de Rentabilidade)

calculos.py (fórmulas puras), componentes.py (interface compartilhada) e relatorios.py (PDF) dão suporte aos três;
as consultas SQL ficam em database/pecuaria_queries.py, junto das consultas dos bancos agrícolas.
"""
