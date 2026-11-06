"""Consultas ao plantio_database. O ZARC (957.490 indicações) é SEMPRE filtrado no PostgreSQL,
usando o índice ix_zarc_mun_cult (geocodigo, cod_cultura). Nenhuma consulta carrega a tabela inteira."""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from database.connections import consultar

BANCO = "plantio"
DECS = [f"dec{i}" for i in range(1, 37)]


def ufs() -> list[str]:
    df = consultar(BANCO, "SELECT DISTINCT uf FROM plantio.municipio ORDER BY uf")
    return df["uf"].tolist()


def municipios(uf: str) -> pd.DataFrame:
    return consultar(BANCO, """SELECT geocodigo, municipio, uf FROM plantio.municipio
                               WHERE uf = :uf AND municipio IS NOT NULL ORDER BY municipio""", {"uf": uf})


def municipio(geocodigo: str) -> pd.DataFrame:
    return consultar(BANCO, """SELECT geocodigo, municipio, uf, cod_munic_sicor, cod_meso, cod_micro, observacao
                               FROM plantio.municipio WHERE geocodigo = :g""", {"g": geocodigo})


def culturas_do_municipio(geocodigo: str) -> pd.DataFrame:
    return consultar(BANCO, """SELECT c.cod_cultura, c.nome_cultura, c.cultura_base
                               FROM plantio.zarc_cultura c
                               WHERE EXISTS (SELECT 1 FROM plantio.zarc_indicacao z
                                             WHERE z.geocodigo = :g AND z.cod_cultura = c.cod_cultura)
                               ORDER BY c.nome_cultura""", {"g": geocodigo})


def opcoes_indicacao(geocodigo: str, cod_cultura: str) -> pd.DataFrame:
    """Combinações de safra, solo, ciclo, manejo, clima e nível de manejo existentes para o município e a cultura."""
    return consultar(BANCO, """SELECT DISTINCT z.safra_ini, z.safra_fin, z.cod_solo, ds.rotulo AS grupo_solo,
                                      z.cod_ciclo, dc.rotulo AS grupo_cultivar, z.cod_outros_manejos, dm.rotulo AS manejo,
                                      z.cod_clima, dcl.rotulo AS clima, z.cod_nm
                               FROM plantio.zarc_indicacao z
                               LEFT JOIN plantio.dominio_codigo ds ON ds.campo = 'Cod_Solo' AND ds.codigo = z.cod_solo
                               LEFT JOIN plantio.dominio_codigo dc ON dc.campo = 'Cod_Ciclo' AND dc.codigo = z.cod_ciclo
                               LEFT JOIN plantio.dominio_codigo dm ON dm.campo = 'Cod_Outros_Manejos' AND dm.codigo = z.cod_outros_manejos
                               LEFT JOIN plantio.dominio_codigo dcl ON dcl.campo = 'Cod_Clima' AND dcl.codigo = z.cod_clima
                               WHERE z.geocodigo = :g AND z.cod_cultura = :c""", {"g": geocodigo, "c": cod_cultura})


def indicacoes(geocodigo: str, cod_cultura: str, safra_ini: int, cod_solo: str, cod_ciclo: str,
               cod_manejo: Optional[str] = None) -> pd.DataFrame:
    """Linhas do ZARC (com os 36 decêndios originais) para a combinação exata."""
    filtro_manejo = "AND z.cod_outros_manejos = :m" if cod_manejo else ""
    params = {"g": geocodigo, "c": cod_cultura, "s": int(safra_ini), "solo": cod_solo, "ciclo": cod_ciclo}
    if cod_manejo:
        params["m"] = cod_manejo
    return consultar(BANCO, f"""SELECT z.indicacao_id, z.cod_cultura, c.nome_cultura, c.cultura_base, z.safra_ini, z.safra_fin,
                                       z.cod_solo, ds.rotulo AS grupo_solo, z.cod_ciclo, dc.rotulo AS grupo_cultivar,
                                       z.cod_outros_manejos, dm.rotulo AS manejo, z.cod_clima, dcl.rotulo AS clima,
                                       z.cod_nm, z.produtividade, z.portaria, p.numero AS portaria_numero,
                                       p.data_publicacao AS portaria_data, {', '.join('z.' + d for d in DECS)}
                                FROM plantio.zarc_indicacao z
                                JOIN plantio.zarc_cultura c USING (cod_cultura)
                                JOIN plantio.portaria p USING (portaria)
                                LEFT JOIN plantio.dominio_codigo ds ON ds.campo = 'Cod_Solo' AND ds.codigo = z.cod_solo
                                LEFT JOIN plantio.dominio_codigo dc ON dc.campo = 'Cod_Ciclo' AND dc.codigo = z.cod_ciclo
                                LEFT JOIN plantio.dominio_codigo dm ON dm.campo = 'Cod_Outros_Manejos' AND dm.codigo = z.cod_outros_manejos
                                LEFT JOIN plantio.dominio_codigo dcl ON dcl.campo = 'Cod_Clima' AND dcl.codigo = z.cod_clima
                                WHERE z.geocodigo = :g AND z.cod_cultura = :c AND z.safra_ini = :s
                                  AND z.cod_solo = :solo AND z.cod_ciclo = :ciclo {filtro_manejo}
                                ORDER BY z.cod_nm NULLS FIRST, z.indicacao_id""", params)


def dominio(campo: Optional[str] = None) -> pd.DataFrame:
    if campo:
        return consultar(BANCO, "SELECT campo, codigo, rotulo, fonte_id, observacao FROM plantio.dominio_codigo WHERE campo = :c ORDER BY codigo",
                         {"c": campo})
    return consultar(BANCO, "SELECT campo, codigo, rotulo, fonte_id, observacao FROM plantio.dominio_codigo ORDER BY campo, codigo")


def decendios() -> pd.DataFrame:
    return consultar(BANCO, "SELECT decendio, campo_origem, observacao FROM plantio.decendio ORDER BY decendio")


def exigencias(cultura_base: str) -> pd.DataFrame:
    """Registros técnicos (não oficiais) de clima, água, fenologia e semeadura da cultura."""
    return consultar(BANCO, """SELECT r.registro_id, r.cultura, r.categoria, r.parametro, r.estagio, r.operador_min, r.valor_min,
                                      r.operador_max, r.valor_max, r.valor, r.unidade, r.unidade_base, r.classificacao, r.regiao,
                                      r.condicoes, r.texto, r.divergencia_ids, r.tipo_dado, r.fonte_id, r.secao, r.pagina_impressa,
                                      f.referencia_abnt
                               FROM plantio.registro r JOIN meta.fonte f USING (fonte_id)
                               WHERE r.cultura = :c ORDER BY r.categoria, r.parametro""", {"c": cultura_base})


def fontes(fonte_ids: Iterable[str]) -> pd.DataFrame:
    return consultar(BANCO, """SELECT fonte_id, titulo, autores, instituicao, ano, referencia_abnt, tipo_dado, observacoes
                               FROM meta.fonte WHERE fonte_id = ANY(:ids) ORDER BY fonte_id""", {"ids": list(fonte_ids)})


def divergencias(registro_ids: Iterable[str]) -> pd.DataFrame:
    ids = list(registro_ids)
    if not ids:
        return pd.DataFrame(columns=["divergencia_id", "registro_id", "parametro", "descricao", "fontes", "tratamento"])
    return consultar(BANCO, """SELECT d.divergencia_id, rd.registro_id, d.parametro, d.descricao, d.fontes, d.tratamento
                               FROM plantio.registro_divergencia rd JOIN meta.divergencia d USING (divergencia_id)
                               WHERE rd.registro_id = ANY(:ids)""", {"ids": ids})
