"""Geração de relatórios PDF (reportlab). Não acessa os bancos: recebe o conteúdo já calculado."""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Iterable, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from utils.formatacao import para_pdf

_CANDIDATAS = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
_FONTE: Optional[tuple[str, str]] = None


def _fonte() -> tuple[str, str]:
    """Registra uma fonte TrueType com suporte a acentos e ≤ ≥ ³; usa Helvetica se nenhuma existir."""
    global _FONTE
    if _FONTE:
        return _FONTE
    for normal, negrito in _CANDIDATAS:
        if os.path.exists(normal) and os.path.exists(negrito):
            try:
                pdfmetrics.registerFont(TTFont("STNormal", normal))
                pdfmetrics.registerFont(TTFont("STBold", negrito))
                _FONTE = ("STNormal", "STBold")
                return _FONTE
            except Exception:
                continue
    _FONTE = ("Helvetica", "Helvetica-Bold")
    return _FONTE


def _limpar(t) -> str:
    s = para_pdf(t)
    if _fonte()[0] == "Helvetica":       # fonte Type1 sem ≤ ≥ ³ ₂
        s = (s.replace("≤", "<=").replace("≥", ">=").replace("³", "3").replace("₂", "2").replace("→", "->")
             .replace("…", "...").replace("•", "-").replace("−", "-"))
    return escape(s)


class Relatorio:
    """Construtor simples: título, metadados, parágrafos, tabelas."""

    def __init__(self, titulo: str, subtitulo: str = "", rodape: str = ""):
        normal, negrito = _fonte()
        base = getSampleStyleSheet()
        self.st = {
            "titulo": ParagraphStyle("t", parent=base["Title"], fontName=negrito, fontSize=17, textColor=colors.HexColor("#1b5e20"),
                                     alignment=TA_LEFT, spaceAfter=4),
            "sub": ParagraphStyle("s", parent=base["Normal"], fontName=normal, fontSize=9, textColor=colors.HexColor("#555555")),
            "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=negrito, fontSize=12, textColor=colors.HexColor("#2e7d32"),
                                 spaceBefore=10, spaceAfter=4),
            "p": ParagraphStyle("p", parent=base["Normal"], fontName=normal, fontSize=9, leading=12),
            "cel": ParagraphStyle("c", parent=base["Normal"], fontName=normal, fontSize=7.5, leading=9),
            "celb": ParagraphStyle("cb", parent=base["Normal"], fontName=negrito, fontSize=7.5, leading=9, textColor=colors.white),
            "celc": ParagraphStyle("cc", parent=base["Normal"], fontName=normal, fontSize=6, leading=7, alignment=1),
            "celbc": ParagraphStyle("cbc", parent=base["Normal"], fontName=negrito, fontSize=6, leading=7, alignment=1,
                                    textColor=colors.white),
            "aviso": ParagraphStyle("a", parent=base["Normal"], fontName=normal, fontSize=8.5, leading=11,
                                    textColor=colors.HexColor("#8d4f00"), backColor=colors.HexColor("#fff3e0"), borderPadding=4),
        }
        self.rodape = rodape
        self.itens: list = [Paragraph(_limpar(titulo), self.st["titulo"])]
        if subtitulo:
            self.itens.append(Paragraph(_limpar(subtitulo), self.st["sub"]))
        self.itens.append(Paragraph(_limpar(f"{datetime.now():%d/%m/%Y %H:%M}"), self.st["sub"]))
        self.itens.append(Spacer(1, 6))

    def secao(self, titulo: str):
        self.itens.append(Paragraph(_limpar(titulo), self.st["h2"]))

    def paragrafo(self, texto: str, aviso: bool = False):
        self.itens.append(Paragraph(_limpar(texto), self.st["aviso" if aviso else "p"]))
        self.itens.append(Spacer(1, 3))

    def pares(self, pares: Iterable[tuple[str, str]]):
        self.tabela(["", ""], [[k, v] for k, v in pares], larguras=[5.5 * cm, 12.5 * cm], cabecalho_visivel=False)

    def tabela(self, cabecalho: Sequence[str], linhas: Sequence[Sequence], larguras: Optional[Sequence[float]] = None,
               cabecalho_visivel: bool = True, compacta: bool = False):
        mostrar = cabecalho_visivel
        cb, cn = (self.st["celbc"], self.st["celc"]) if compacta else (self.st["celb"], self.st["cel"])
        dados = []
        if mostrar:
            dados.append([Paragraph(_limpar(c), cb) for c in cabecalho])
        for l in linhas:
            dados.append([Paragraph(_limpar(c), cn) for c in l])
        if not dados:
            return
        largura_total = A4[0] - 3 * cm
        if not larguras:
            n = len(cabecalho) or len(linhas[0])
            larguras = [largura_total / n] * n
        t = Table(dados, colWidths=larguras, repeatRows=1 if mostrar else 0)
        estilo = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#a5d6a7")),
                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("ROWBACKGROUNDS", (0, 1 if mostrar else 0), (-1, -1), [colors.white, colors.HexColor("#f1f8e9")])]
        if mostrar:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")))
        if compacta:
            estilo += [("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                       ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
        t.setStyle(TableStyle(estilo))
        self.itens.append(t)
        self.itens.append(Spacer(1, 6))

    def destaque(self, titulo: str, texto: str, cor: str = "#2e7d32"):
        """Caixa colorida para conclusões (ex.: veredito da análise)."""
        _, negrito = _fonte()
        st_t = ParagraphStyle("dt", parent=self.st["p"], fontName=negrito, fontSize=11, textColor=colors.HexColor(cor))
        t = Table([[Paragraph(_limpar(titulo), st_t)], [Paragraph(_limpar(texto), self.st["p"])]],
                  colWidths=[A4[0] - 3 * cm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(cor)),
                               ("LINEBEFORE", (0, 0), (0, -1), 5, colors.HexColor(cor)),
                               ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f8e9")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        self.itens.append(t)
        self.itens.append(Spacer(1, 6))

    def grafico_barras(self, categorias: Sequence[str], series: dict, titulo: str = "", eixo: str = "",
                       altura_cm: float = 7.0):
        """Gráfico de barras agrupadas (reportlab.graphics — sem dependências extras)."""
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.legends import Legend
        from reportlab.graphics.shapes import Drawing, String
        normal, negrito = _fonte()
        largura = A4[0] - 3 * cm
        altura = altura_cm * cm
        d = Drawing(largura, altura)
        if titulo:
            d.add(String(0, altura - 12, _limpar(titulo).replace("&amp;", "&"), fontName=negrito, fontSize=9,
                         fillColor=colors.HexColor("#2e7d32")))
        ch = VerticalBarChart()
        legenda = len(series) > 1
        base_y = 52 if legenda else 30
        ch.x, ch.y, ch.width, ch.height = 55, base_y, largura - 75, altura - base_y - 30
        dados = [[float(v or 0) for v in vals] for vals in series.values()]
        ch.data = dados
        ch.categoryAxis.categoryNames = [_limpar(c).replace("&amp;", "&") for c in categorias]
        ch.categoryAxis.joinAxisMode = "bottom"      # rótulos abaixo do gráfico mesmo com valores negativos
        ch.categoryAxis.labels.fontName = normal
        ch.categoryAxis.labels.fontSize = 7
        ch.valueAxis.labels.fontName = normal
        ch.valueAxis.labels.fontSize = 7
        mn = min(min(x) for x in dados) if dados else 0
        mx = max(max(x) for x in dados) if dados else 1
        ch.valueAxis.valueMin = min(0, mn * 1.1)
        ch.valueAxis.valueMax = max(mx * 1.1, 1)
        ch.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}".replace(",", ".")
        paleta = ["#2e7d32", "#ef6c00", "#81c784", "#1e88e5", "#c62828"]
        for i in range(len(dados)):
            ch.bars[i].fillColor = colors.HexColor(paleta[i % len(paleta)])
            ch.bars[i].strokeColor = None
        ch.barSpacing = 1
        ch.groupSpacing = 8
        d.add(ch)
        if legenda:
            lg = Legend()
            lg.x, lg.y = 55, 4
            lg.fontName, lg.fontSize = normal, 7
            lg.alignment = "right"
            lg.columnMaximum = 1
            lg.dx = lg.dy = 7
            lg.deltax = 150
            nomes = list(series)
            lg.colorNamePairs = [(colors.HexColor(paleta[i % len(paleta)]), _limpar(n).replace("&amp;", "&"))
                                 for i, n in enumerate(nomes)]
            lg.boxAnchor = "sw"
            d.add(lg)
        self.itens.append(d)
        self.itens.append(Spacer(1, 6))

    def gerar(self) -> bytes:
        buf = io.BytesIO()
        normal, _ = _fonte()
        rodape = _limpar(self.rodape)

        def _pagina(canvas, doc):
            canvas.saveState()
            canvas.setFont(normal, 7)
            canvas.setFillColor(colors.HexColor("#777777"))
            canvas.drawString(1.5 * cm, 1 * cm, rodape[:180])
            canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"{doc.page}")
            canvas.restoreState()

        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.6 * cm,
                                title="SafraTech IA", author="SafraTech IA")
        doc.build(self.itens, onFirstPage=_pagina, onLaterPages=_pagina)
        return buf.getvalue()
