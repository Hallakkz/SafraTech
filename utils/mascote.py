"""Mascote do EduAgro no cabeçalho do EduAgro AI (com easter egg: 3 cliques rápidos mostram o alien do MST)."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

PASTA = Path(__file__).resolve().parent.parent / "assets"
IMAGEM_EDUAGRO = PASTA / "eduagro_avatar.png"
IMAGEM_SECRETA = PASTA / "eduagro_mst.png"
TAMANHO_PX = 150


@lru_cache(maxsize=4)
def _b64(caminho: str) -> str:
    try:
        return base64.b64encode(Path(caminho).read_bytes()).decode()
    except OSError:
        return ""


def _html(edu: str, mst: str, tam: int = TAMANHO_PX) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:transparent;overflow:hidden}}
.wrap{{display:flex;align-items:center;justify-content:flex-start;height:{tam + 16}px;padding-left:4px}}
img{{width:{tam}px;height:{tam}px;border-radius:50%;cursor:pointer;user-select:none;
     -webkit-user-drag:none;border:3px solid #6ee7a8;box-shadow:0 0 18px rgba(110,231,168,.35);
     transition:transform .15s ease, border-color .3s, box-shadow .3s}}
img:active{{transform:scale(.95)}}
img.mst{{border-color:#ef4444;box-shadow:0 0 22px rgba(239,68,68,.55)}}
img.gira{{animation:gira .6s ease}}
@keyframes gira{{0%{{transform:rotateY(0) scale(1)}}50%{{transform:rotateY(90deg) scale(1.08)}}100%{{transform:rotateY(0) scale(1)}}}}
</style></head><body><div class="wrap">
<img id="m" src="data:image/png;base64,{edu}" alt="EduAgro" title="EduAgro">
</div><script>
const EDU="data:image/png;base64,{edu}", MST="data:image/png;base64,{mst}";
const img=document.getElementById("m"); let cliques=0, timer=null, secreto=false;
img.addEventListener("click",()=>{{
  cliques++; clearTimeout(timer); timer=setTimeout(()=>cliques=0,700);
  if(cliques<3) return;
  cliques=0; secreto=!secreto;
  img.classList.remove("gira"); void img.offsetWidth; img.classList.add("gira");
  setTimeout(()=>{{img.src=secreto?MST:EDU; img.classList.toggle("mst",secreto);
                   img.title=secreto?"MST":"EduAgro";}},300);
}});
</script></body></html>"""


def mostrar(tamanho: int = TAMANHO_PX) -> None:
    """Mostra o mascote em um círculo. Se o componente HTML não estiver disponível, mostra só a imagem."""
    edu, mst = _b64(str(IMAGEM_EDUAGRO)), _b64(str(IMAGEM_SECRETA))
    if not edu:
        return
    try:
        from streamlit.components.v1 import html as componente_html
    except Exception:  # pragma: no cover - ambiente sem componentes
        componente_html = None
    if componente_html is not None and mst:
        componente_html(_html(edu, mst, tamanho), height=tamanho + 16)
    else:
        st.markdown(f'<img src="data:image/png;base64,{edu}" alt="EduAgro" '
                    f'style="width:{tamanho}px;height:{tamanho}px;border-radius:50%">', unsafe_allow_html=True)
