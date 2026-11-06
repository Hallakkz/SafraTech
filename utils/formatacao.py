"""Formatação de números, status e unidades para exibição."""
from __future__ import annotations

from typing import Any, Optional

from core.classificacao import num
from utils.textos import tr

CORES_STATUS = {
    "adequado": "#2e7d32", "atencao": "#f9a825", "abaixo": "#c62828", "acima": "#ef6c00",
    "insuficiente": "#607d8b", "divergente": "#8e24aa", "classe_fonte": "#1e88e5",
}

CORES_RISCO = {0: "#37474f", 20: "#2e7d32", 30: "#f9a825", 40: "#ef6c00"}


def numero(v: Any, casas: int = 2) -> str:
    x = num(v)
    if x is None:
        return "—"
    s = f"{x:,.{casas}f}".rstrip("0").rstrip(".") if casas else f"{x:,.0f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")   # padrão brasileiro: 1.234,5


def status(st_key: str) -> str:
    return tr(f"st_{st_key}")


def chip(st_key: str) -> str:
    cor = CORES_STATUS.get(st_key, "#607d8b")
    return (f'<span class="st-chip" style="border-color:{cor};background:{cor}33">'
            f'{status(st_key)}</span>')


def unidade_html(u: Optional[str]) -> str:
    return (u or "").replace("dm3", "dm³").replace("cmolc", "cmolc")


def para_pdf(texto: Any) -> str:
    """Remove caracteres não suportados por fontes básicas do PDF (emojis)."""
    s = "" if texto is None else str(texto)
    return "".join(ch for ch in s if ord(ch) < 0x2190 or ch in "≤≥–—→•…−")
