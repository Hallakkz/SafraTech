"""
Conversões de unidade. Os fatores K e MO são lidos dos registros 'conversao_unidade' do solo_database
(SOL-000220 e SOL-000221); as demais são equivalências exatas do Sistema Internacional
(1 cmolc/dm³ = 10 mmolc/dm³; 1 % = 10 g/kg = 1 dag/kg; 1 mg/dm³ = 1 ppm em base volumétrica).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# fatores padrão usados apenas se o banco estiver indisponível (mesmos valores dos registros da fonte)
FATOR_K_PADRAO = 0.00256     # K (cmolc/dm3) = K (mg/dm3) × 0,00256
FATOR_MO_PADRAO = 1.724      # MO (%) = C (%) × 1,724


@dataclass
class Fatores:
    k_mg_para_cmolc: float = FATOR_K_PADRAO
    c_para_mo: float = FATOR_MO_PADRAO
    origem_k: str = "padrão (banco indisponível)"
    origem_mo: str = "padrão (banco indisponível)"


def fatores_do_banco(conv: Optional[pd.DataFrame]) -> Fatores:
    f = Fatores()
    if conv is None or conv.empty:
        return f
    for r in conv.to_dict("records"):
        texto = str(r.get("texto") or "")
        m = re.search(r"×\s*([\d.,]+)", texto)
        if not m:
            continue
        valor = float(m.group(1).replace(",", "."))
        ref = f"{r.get('registro_id')} ({r.get('fonte_id')}, {r.get('secao')})"
        if str(r.get("parametro", "")).startswith("Potássio"):
            f.k_mg_para_cmolc, f.origem_k = valor, ref
        elif str(r.get("parametro", "")).startswith("Matéria orgânica"):
            f.c_para_mo, f.origem_mo = valor, ref
    return f


# unidades aceitas na interface, por parâmetro do solo
UNIDADES_SOLO = {
    "ph": ["—"],
    "p": ["mg/dm³"],
    "k": ["mg/dm³", "cmolc/dm³", "mmolc/dm³", "mg/kg"],
    "ca": ["cmolc/dm³", "mmolc/dm³"],
    "mg": ["cmolc/dm³", "mmolc/dm³"],
    "s": ["mg/dm³"],
    "mo": ["%", "g/kg", "dag/kg", "C orgânico (%)"],
    "ctc": ["cmolc/dm³", "mmolc/dm³"],
    "v": ["%"],
    "m": ["%"],
    "n": ["mg/dm³", "%", "g/kg"],
    "b": ["mg/dm³"], "cu": ["mg/dm³"], "fe": ["mg/dm³"], "mn": ["mg/dm³"], "zn": ["mg/dm³"],
}


@dataclass
class Convertido:
    valor: Optional[float]
    unidade_base: Optional[str]     # unidade_base do banco usada na comparação
    nota: str = ""                  # descrição da conversão aplicada (vazio se nenhuma)
    k_cmolc: Optional[float] = None


def converter_solo(chave: str, valor: Optional[float], unidade: str, f: Fatores) -> Convertido:
    if valor is None:
        return Convertido(None, None)
    if chave == "ph":
        return Convertido(valor, "adimensional")
    if chave in ("ca", "mg", "ctc"):
        if unidade == "mmolc/dm³":
            return Convertido(valor / 10, "cmolc/dm3", f"{valor:g} mmolc/dm³ ÷ 10 = {valor / 10:g} cmolc/dm³")
        return Convertido(valor, "cmolc/dm3")
    if chave == "k":
        if unidade == "mg/kg":
            # referência específica em mg/kg (Cap. 7, Tabela 5); não é convertida para volume
            return Convertido(valor, "mg/kg", "", None)
        if unidade == "cmolc/dm³":
            mg = valor / f.k_mg_para_cmolc
            return Convertido(mg, "mg/dm3", f"{valor:g} cmolc/dm³ ÷ {f.k_mg_para_cmolc:g} = {mg:.1f} mg/dm³ (fator {f.origem_k})", valor)
        if unidade == "mmolc/dm³":
            cm = valor / 10
            mg = cm / f.k_mg_para_cmolc
            return Convertido(mg, "mg/dm3", f"{valor:g} mmolc/dm³ = {cm:g} cmolc/dm³ ÷ {f.k_mg_para_cmolc:g} = {mg:.1f} mg/dm³ (fator {f.origem_k})", cm)
        return Convertido(valor, "mg/dm3", "", valor * f.k_mg_para_cmolc)
    if chave == "mo":
        if unidade == "g/kg":
            return Convertido(valor / 10, "%", f"{valor:g} g/kg ÷ 10 = {valor / 10:g} %")
        if unidade == "C orgânico (%)":
            mo = valor * f.c_para_mo
            return Convertido(mo, "%", f"C {valor:g} % × {f.c_para_mo:g} = MO {mo:.2f} % (fator {f.origem_mo})")
        return Convertido(valor, "%")
    if chave in ("v", "m"):
        return Convertido(valor, "%")
    if chave == "n":
        return Convertido(valor, None)
    return Convertido(valor, "mg/dm3")


# ---------------- foliar ----------------
MACROS_FOLIAR = {"N", "P", "K", "Ca", "Mg", "S"}
UNIDADES_FOLIAR_MACRO = ["g/kg", "%", "dag/kg"]
UNIDADES_FOLIAR_MICRO = ["mg/kg", "ppm", "g/kg"]


def converter_foliar(nutriente: str, valor: Optional[float], unidade: str) -> tuple[Optional[float], str, str]:
    """Converte para a unidade_base do banco (g/kg para macros, mg/kg para micros)."""
    if valor is None:
        return None, "", ""
    if nutriente in MACROS_FOLIAR:
        if unidade in ("%", "dag/kg"):
            return valor * 10, "g/kg", f"{valor:g} {unidade} × 10 = {valor * 10:g} g/kg"
        return valor, "g/kg", ""
    if unidade == "g/kg":
        return valor * 1000, "mg/kg", f"{valor:g} g/kg × 1000 = {valor * 1000:g} mg/kg"
    if unidade == "ppm":
        return valor, "mg/kg", "ppm = mg/kg"
    return valor, "mg/kg", ""
