"""Validações de consistência dos valores digitados (limites físicos, não agronômicos).
Nenhuma destas regras classifica o valor — elas apenas impedem entradas impossíveis."""
from __future__ import annotations

from typing import Optional

LIMITES_FISICOS = {
    "ph": (0.0, 14.0),
    "v": (0.0, 100.0),
    "m": (0.0, 100.0),
    "argila": (0.0, 100.0),
    "mo_%": (0.0, 100.0),
}


def validar(chave: str, valor: Optional[float], unidade: str = "") -> Optional[str]:
    """Retorna mensagem de erro ou None."""
    if valor is None:
        return None
    if valor < 0:
        return "valor negativo"
    k = "mo_%" if chave == "mo" and unidade in ("%", "dag/kg", "C orgânico (%)") else chave
    if k in LIMITES_FISICOS:
        lo, hi = LIMITES_FISICOS[k]
        if not lo <= valor <= hi:
            return f"fora do intervalo físico possível ({lo:g}–{hi:g})"
    return None


def validar_periodo(inicio: int, fim: int) -> Optional[str]:
    if not (1 <= int(inicio) <= 36 and 1 <= int(fim) <= 36):
        return "decêndios devem estar entre 1 e 36"
    return None
