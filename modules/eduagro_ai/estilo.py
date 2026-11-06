"""Estilo visual do EduAgro AI — segue a identidade do SafraTech (verde-escuro, Syne nos títulos, Inter nos textos,
cartões arredondados) com um destaque próprio em verde-limão/dourado para o módulo de ensino."""

CSS_EDUAGRO = """
<style>
.edu-hero {background:radial-gradient(120% 140% at 0% 0%, rgba(105,240,174,0.16) 0%, rgba(13,42,26,0.0) 55%),
           linear-gradient(135deg,#0d2a1a 0%,#123a24 60%,#16452b 100%);
           border:1px solid #2e7d32;border-radius:20px;padding:1.2rem 1.4rem;margin:0.2rem 0 1rem 0;
           box-shadow:0 6px 28px rgba(0,0,0,0.45), inset 0 1px 0 rgba(185,246,202,0.10)}
.edu-hero h2 {font-family:'Syne',sans-serif !important;margin:0 0 0.2rem 0 !important;font-size:1.55rem !important;
              background:linear-gradient(90deg,#b9f6ca,#e6ee9c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.edu-hero p {color:#a5d6a7;margin:0;font-size:0.92rem}
.edu-selo {display:inline-block;font-family:'Syne',sans-serif;font-size:0.68rem;font-weight:700;letter-spacing:0.14em;
           text-transform:uppercase;padding:0.2rem 0.7rem;border-radius:20px;margin-bottom:0.45rem;
           color:#0a1a0f;background:linear-gradient(90deg,#69f0ae,#e6ee9c)}
.edu-card {background:linear-gradient(135deg,#0d2a1a,#133d26);border:1px solid #1e5c35;border-radius:16px;
           padding:0.9rem 1.05rem;margin-bottom:0.7rem;min-height:9.5rem;box-shadow:0 4px 20px rgba(0,0,0,0.35)}
.edu-card h4 {font-family:'Syne',sans-serif;color:#b9f6ca;margin:0 0 0.25rem 0;font-size:1.0rem}
.edu-card .meta {color:#81c784;font-size:0.76rem;letter-spacing:0.03em}
.edu-card .desc {color:#c8e6c9;font-size:0.85rem;margin-top:0.35rem}
.edu-tag {display:inline-block;font-size:0.7rem;padding:0.08rem 0.5rem;border-radius:10px;border:1px solid #388e3c;
          color:#b9f6ca;margin:0 0.25rem 0.25rem 0;font-family:'Inter',sans-serif}
.edu-tag.banco {border-color:#69f0ae;background:rgba(105,240,174,0.10)}
.edu-tag.ia {border-color:#e6ee9c;color:#f0f4c3;background:rgba(230,238,156,0.08)}
.edu-tag.hipotetico {border-color:#ffb74d;color:#ffe0b2;background:rgba(255,183,77,0.08)}
.edu-tag.alerta {border-color:#ef9a9a;color:#ffcdd2;background:rgba(239,154,154,0.08)}
.edu-ref {border-left:3px solid #2e7d32;padding:0.35rem 0.7rem;margin:0.35rem 0;background:rgba(13,42,26,0.45);
          border-radius:0 10px 10px 0;font-size:0.84rem;color:#c8e6c9}
.edu-ref b {color:#b9f6ca}
.edu-ref .fonte {color:#81c784;font-size:0.76rem}
.edu-legenda {font-size:0.78rem;color:#81c784}
[data-testid="stChatMessage"] {background:rgba(13,42,26,0.55);border:1px solid #1a4a2a;border-radius:16px;padding:0.6rem 0.9rem}
[data-testid="stChatMessage"] h3 {font-size:1.02rem !important;margin-top:0.6rem !important}
[data-testid="stChatInput"] textarea {font-family:'Inter',sans-serif !important}
div[data-testid="stTabs"] button[role="tab"] p {font-family:'Syne',sans-serif;font-weight:600}
/* rótulos e textos dos campos na área principal (contraste sobre o fundo verde-escuro) */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stCheckbox"] label p,
[data-testid="stMain"] div[role="radiogroup"] label p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li {color:#dcedc8}
[data-testid="stMain"] [data-testid="stCaptionContainer"] {color:#a5d6a7 !important}
.st-key-edu_secao div[role="radiogroup"] label {border:1px solid #1e5c35;border-radius:12px;padding:0.3rem 0.8rem;
          background:rgba(13,42,26,0.6);margin-right:0.35rem}
.st-key-edu_secao div[role="radiogroup"] label p {font-family:'Syne',sans-serif;font-weight:600;color:#c8e6c9 !important}
.st-key-edu_secao div[role="radiogroup"] label:has(input:checked) {border-color:#9ccc65;
          background:linear-gradient(90deg, rgba(105,240,174,0.18), rgba(230,238,156,0.10))}
.st-key-edu_secao div[role="radiogroup"] label:has(input:checked) p {color:#e6ee9c !important}
[data-testid="stExpander"] summary p {color:#c8e6c9}
</style>
"""

# Destaque do item "EduAgro AI" no menu principal da barra lateral (5º item do menu).
CSS_MENU_DESTAQUE = """
<style>
[data-testid="stSidebar"] .st-key-nav_agricultura div[role="radiogroup"] > label:nth-of-type(5) {
    margin-top: 0.55rem;
    border: 1px solid #9ccc65 !important;
    background: linear-gradient(90deg, rgba(105,240,174,0.16), rgba(230,238,156,0.10)) !important;
    box-shadow: 0 0 14px rgba(105,240,174,0.18);
}
[data-testid="stSidebar"] .st-key-nav_agricultura div[role="radiogroup"] > label:nth-of-type(5) p {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    color: #e6ee9c !important;
}
</style>
"""
