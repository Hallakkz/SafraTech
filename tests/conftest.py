"""Configuração dos testes.

Os testes de integração usam os bancos reais (solo_database, nutricao_database, plantio_database e os três bancos de
pecuária) por meio do cliente `psql` (tests/psql_executor.py). Se o PostgreSQL não estiver acessível, esses testes são pulados.
Variáveis: PGHOST (padrão localhost), PGUSER (padrão postgres).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import psql_executor  # noqa: E402
from stub_streamlit import instalar_plotly_stub  # noqa: E402

instalar_plotly_stub()
# Os testes nunca usam os dados reais do EduAgro (conversas, progresso, biblioteca): pasta temporária própria.
os.environ["EDUAGRO_DADOS_DIR"] = tempfile.mkdtemp(prefix="eduagro_testes_")
BANCOS_OK = psql_executor.disponivel()
MAIN = str(RAIZ / "main.py")


@pytest.fixture
def bancos():
    if not BANCOS_OK:
        pytest.skip("PostgreSQL com os bancos SafraTech não acessível")
    from database import connections
    connections.definir_executor_externo(psql_executor.executar)
    yield connections
    connections.definir_executor_externo(None)


@pytest.fixture
def edu_dados(tmp_path, monkeypatch):
    """Pasta de dados do EduAgro vazia e exclusiva para o teste."""
    monkeypatch.setenv("EDUAGRO_DADOS_DIR", str(tmp_path / "dados_eduagro"))
    from modules.eduagro_ai import armazenamento, knowledge_retrieval
    armazenamento.reiniciar_cache_de_esquema()
    knowledge_retrieval._cache_bib.update(versao=None, indice=None)
    yield tmp_path / "dados_eduagro"
    armazenamento.reiniciar_cache_de_esquema()


def _assinatura() -> dict:
    """Contagem e hash do conteúdo das tabelas principais (para provar que o app não altera os bancos)."""
    consultas = {
        "solo_database": "SELECT count(*) || ':' || md5(string_agg(hash_conteudo, '' ORDER BY registro_id)) FROM solo.registro",
        "nutricao_database": "SELECT count(*) || ':' || md5(string_agg(hash_conteudo, '' ORDER BY registro_id)) FROM nutricao.registro",
        "plantio_database": "SELECT (SELECT count(*) FROM plantio.zarc_indicacao) || ':' || (SELECT sum(dec1+dec10+dec20+dec30+dec36) FROM plantio.zarc_indicacao)"
                            " || ':' || md5((SELECT string_agg(hash_conteudo, '' ORDER BY registro_id) FROM plantio.registro))",
    }
    for banco in ("pecuaria_compra_database", "pecuaria_desempenho_database", "pecuaria_rentabilidade_database"):
        consultas[banco] = ("SELECT (SELECT count(*) || ':' || md5(string_agg(id_registro || coalesce(valor_numerico::text, ''), '' "
                            "ORDER BY id_registro)) FROM parametro_tecnico) || '|' || (SELECT count(*) FROM fonte) || '|' || "
                            "(SELECT count(*) FROM pergunta_resposta)")
    consultas["pecuaria_compra_database"] += " || '|' || (SELECT count(*) FROM lote_compra) || (SELECT count(*) FROM lote_compra_cenario_venda)"
    consultas["pecuaria_desempenho_database"] += " || '|' || (SELECT count(*) FROM lote_rebanho) || (SELECT count(*) FROM pesagem_rebanho)"
    consultas["pecuaria_rentabilidade_database"] += " || '|' || (SELECT count(*) FROM cenario_venda) || (SELECT count(*) FROM cenario_custo_item)"
    out = {}
    for banco, sql in consultas.items():
        p = subprocess.run(["psql", "-h", "localhost", "-U", "postgres", "-d", banco, "-Atc", sql], capture_output=True, text=True)
        out[banco] = p.stdout.strip()
    return out


@pytest.fixture(scope="session", autouse=True)
def bancos_inalterados():
    """Falha a sessão se qualquer teste (ou o app) alterar o conteúdo dos bancos."""
    if not BANCOS_OK:
        yield
        return
    antes = _assinatura()
    yield
    depois = _assinatura()
    assert antes == depois, f"Conteúdo dos bancos foi alterado durante os testes: {antes} != {depois}"
