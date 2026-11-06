"""
Substituto mínimo do Streamlit para testes automatizados sem servidor.

Executa o main.py de verdade (todas as linhas), registra o que seria exibido e permite controlar os widgets:
    app = AppSimulado(valores={"solo_cultura": "Soja"}, botoes={"Gerar diagnóstico"})
    app.executar("main.py")
    app.interagir("main.py", "nav_agricultura", 3)   # clique do usuário: dispara o on_change e reexecuta
Os valores podem ser indexados pela `key` do widget ou pelo rótulo.
"""
from __future__ import annotations

import runpy
import sys
import types
from contextlib import contextmanager
from typing import Any


class _Estado(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class _Rerun(Exception):
    """Equivalente a st.rerun(): interrompe a execução e recomeça o script."""


class _Bloco:
    """Objeto com a mesma API de st / st.sidebar / colunas / expander / form."""

    def __init__(self, app: "AppSimulado", nome: str):
        self._app, self._nome = app, nome

    # ---- contexto ----
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # ---- saída ----
    def _log(self, tipo, *conteudo):
        self._app.saida.append((tipo, *conteudo))
        return self

    def markdown(self, texto, unsafe_allow_html=False, **kw):
        return self._log("markdown", str(texto))

    def write(self, *a, **kw):
        return self._log("write", " ".join(map(str, a)))

    def title(self, t, **kw):
        return self._log("title", t)

    def header(self, t, **kw):
        return self._log("header", t)

    def subheader(self, t, **kw):
        return self._log("subheader", t)

    def caption(self, t, **kw):
        return self._log("caption", str(t))

    def info(self, t, **kw):
        return self._log("info", str(t))

    def warning(self, t, **kw):
        return self._log("warning", str(t))

    def error(self, t, **kw):
        return self._log("error", str(t))

    def success(self, t, **kw):
        return self._log("success", str(t))

    def divider(self):
        return self._log("divider")

    def metric(self, label, value, delta=None, help=None, **kw):
        return self._log("metric", str(label), str(value))

    def image(self, img, **kw):
        if "use_container_width" in kw:
            raise TypeError("use_container_width obsoleto")  # força o caminho moderno
        return self._log("image", img)

    def dataframe(self, df, hide_index=None, width=None, use_container_width=None, **kw):
        return self._log("dataframe", df)

    def table(self, df, **kw):
        return self._log("table", df)

    def plotly_chart(self, fig, width=None, use_container_width=None, config=None, **kw):
        return self._log("plotly_chart", fig)

    def download_button(self, label, data, file_name=None, mime=None, key=None, **kw):
        self._app.downloads[file_name] = data
        return self._log("download_button", label, file_name)

    def spinner(self, *a, **kw):
        return self

    # ---- layout ----
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Bloco(self._app, f"{self._nome}.col{i}") for i in range(n)]

    def tabs(self, nomes):
        return [_Bloco(self._app, f"{self._nome}.tab:{n}") for n in nomes]

    def expander(self, rotulo, expanded=False, **kw):
        self._log("expander", rotulo)
        return _Bloco(self._app, f"{self._nome}.exp")

    def container(self, **kw):
        return _Bloco(self._app, f"{self._nome}.cont")

    def form(self, chave, **kw):
        return _Bloco(self._app, f"form:{chave}")

    # ---- widgets ----
    def _valor(self, key, rotulo, padrao):
        for k in (key, rotulo):
            if k is not None and k in self._app.valores:
                return self._app.valores[k]
        if key is not None and key in self._app.session_state:
            return self._app.session_state[key]
        return padrao

    def _registrar(self, key, valor, on_change=None):
        if key is not None:
            self._app.session_state[key] = valor
            if on_change is not None:
                self._app.callbacks[key] = on_change
        return valor

    def selectbox(self, rotulo, opcoes, index=0, format_func=str, key=None, on_change=None, **kw):
        opcoes = list(opcoes)
        for o in opcoes:
            format_func(o)          # garante que o format_func funciona para todas as opções
        self._app.widgets.append(("selectbox", rotulo, key, opcoes))
        padrao = opcoes[index] if opcoes and index is not None else None
        v = self._valor(key, rotulo, padrao)
        if opcoes and v not in opcoes:
            v = padrao
        return self._registrar(key, v, on_change)

    def radio(self, rotulo, opcoes, index=0, format_func=str, key=None, on_change=None, **kw):
        return self.selectbox(rotulo, opcoes, index=index, format_func=format_func, key=key, on_change=on_change)

    def multiselect(self, rotulo, opcoes, default=None, format_func=str, key=None, **kw):
        opcoes = list(opcoes)
        for o in opcoes:
            format_func(o)
        v = self._valor(key, rotulo, list(default or []))
        assert all(x in opcoes for x in v), f"opção inválida em {rotulo}: {v}"
        return self._registrar(key, v)

    def number_input(self, rotulo, min_value=None, max_value=None, value="min", step=None, format=None, key=None, **kw):
        padrao = (min_value if min_value is not None else 0.0) if value == "min" else value
        self._app.widgets.append(("number_input", rotulo, key, None))
        v = self._valor(key, rotulo, padrao)
        if v is not None:
            if min_value is not None and v < min_value:
                raise ValueError(f"{rotulo}: {v} < min {min_value}")
            if max_value is not None and v > max_value:
                raise ValueError(f"{rotulo}: {v} > max {max_value}")
        return self._registrar(key, v)

    def date_input(self, rotulo, value="today", key=None, **kw):
        import datetime as _dt
        padrao = _dt.date.today() if value == "today" else value
        self._app.widgets.append(("date_input", rotulo, key, None))
        return self._registrar(key, self._valor(key, rotulo, padrao))

    def text_input(self, rotulo, value="", key=None, **kw):
        return self._registrar(key, self._valor(key, rotulo, value))

    def text_area(self, rotulo, value="", key=None, **kw):
        return self._registrar(key, self._valor(key, rotulo, value))

    def checkbox(self, rotulo, value=False, key=None, **kw):
        return self._registrar(key, self._valor(key, rotulo, value))

    def button(self, rotulo, key=None, on_click=None, args=None, kwargs=None, **kw):
        self._app.widgets.append(("button", rotulo, key, None))
        clicado = rotulo in self._app.botoes or (key is not None and key in self._app.botoes)
        if clicado and on_click is not None:   # como no Streamlit: o callback roda antes do código que lê o botão
            on_click(*(args or ()), **(kwargs or {}))
        return clicado

    def form_submit_button(self, rotulo, on_click=None, args=None, kwargs=None, **kw):
        return self.button(rotulo, on_click=on_click, args=args, kwargs=kwargs)

    # ---- widgets e elementos usados pelo EduAgro AI ----
    def toggle(self, rotulo, value=False, key=None, **kw):
        return self.checkbox(rotulo, value=value, key=key)

    def file_uploader(self, rotulo, type=None, key=None, **kw):
        self._app.widgets.append(("file_uploader", rotulo, key, type))
        return self._registrar(key, self._valor(key, rotulo, None))

    def chat_input(self, placeholder="", key=None, **kw):
        """Como no Streamlit, o valor enviado é devolvido uma única vez."""
        self._app.widgets.append(("chat_input", placeholder, key, None))
        for k in (key, placeholder):
            if k is not None and k in self._app.valores:
                return self._app.valores.pop(k)
        return None

    def chat_message(self, nome, avatar=None, **kw):
        self._log("chat_message", nome)
        return _Bloco(self._app, f"{self._nome}.chat:{nome}")

    def write_stream(self, gerador, **kw):
        texto = "".join(str(x) for x in gerador)
        self._log("write_stream", texto)
        return texto

    def progress(self, valor=0, text=None, **kw):
        self._log("progress", str(text or valor))
        return self

    def empty(self):
        return _Bloco(self._app, f"{self._nome}.empty")

    def status(self, rotulo, **kw):
        self._log("status", rotulo)
        return self

    def update(self, **kw):
        return self

    def latex(self, t, **kw):
        return self._log("latex", t)

    def code(self, t, **kw):
        return self._log("code", t)


class AppSimulado:
    def __init__(self, valores: dict | None = None, botoes: set | None = None):
        self.valores = dict(valores or {})
        self.botoes = set(botoes or [])
        self.session_state = _Estado()
        self.saida: list = []
        self.widgets: list = []
        self.downloads: dict = {}
        self.callbacks: dict = {}
        self.modulo = self._montar_modulo()

    def _montar_modulo(self):
        st = types.ModuleType("streamlit")
        raiz = _Bloco(self, "main")
        for nome in dir(_Bloco):
            if not nome.startswith("_") or nome in ("__enter__", "__exit__"):
                if not nome.startswith("__"):
                    setattr(st, nome, getattr(raiz, nome))
        st.sidebar = _Bloco(self, "sidebar")
        st.session_state = self.session_state
        st.set_page_config = lambda **kw: None

        def rerun(**kw):
            raise _Rerun()
        st.rerun = rerun

        class _Secrets(dict):
            def __iter__(self):
                raise FileNotFoundError("No secrets file")

            def keys(self):
                raise FileNotFoundError("No secrets file")

        st.secrets = _Secrets()

        def cache_data(func=None, **kw):
            def deco(f):
                f.clear = lambda: None
                return f
            return deco(func) if callable(func) else deco

        st.cache_data = cache_data
        st.cache_resource = cache_data
        return st

    def executar(self, caminho: str, valores: dict | None = None, botoes: set | None = None):
        """Uma execução completa do script (equivale a um rerun do Streamlit)."""
        if valores is not None:
            self.valores.update(valores)
        self.botoes = set(botoes or [])
        self.saida, self.widgets = [], []
        anterior = sys.modules.get("streamlit")
        sys.modules["streamlit"] = self.modulo
        # módulos que importam streamlit precisam enxergar o stub desta execução
        for m in [m for m in sys.modules if m.startswith(("modules", "main"))]:
            del sys.modules[m]
        try:
            for _ in range(5):
                try:
                    self.saida, self.widgets = [], []
                    runpy.run_path(caminho, run_name="__main__")
                    break
                except _Rerun:
                    for m in [m for m in sys.modules if m.startswith(("modules", "main"))]:
                        del sys.modules[m]
        finally:
            if anterior is not None:
                sys.modules["streamlit"] = anterior
        return self

    def interagir(self, caminho: str, chave: str, valor, botoes: set | None = None):
        """Simula o usuário alterando um widget: grava o novo valor, chama o on_change (como o Streamlit faz antes
        de reexecutar) e reexecuta o script."""
        self.valores.pop(chave, None)
        self.session_state[chave] = valor
        cb = self.callbacks.get(chave)
        if cb is not None:
            cb()
        return self.executar(caminho, botoes=botoes)

    # ---- consultas sobre a saída ----
    def textos(self, tipo: str | None = None) -> list[str]:
        return [str(x[1]) for x in self.saida if (tipo is None or x[0] == tipo) and len(x) > 1]

    def contem(self, trecho: str, tipo: str | None = None) -> bool:
        return any(trecho in t for t in self.textos(tipo))


def instalar_plotly_stub():
    """Plotly mínimo para exercitar o código dos gráficos quando a biblioteca não está instalada."""
    try:
        import plotly.graph_objects  # noqa: F401
        return False
    except ImportError:
        pass

    class _Obj:
        def __init__(self, *a, **kw):
            self.kw, self.data, self.shapes = kw, list(a), []

        def __getattr__(self, nome):
            def metodo(*a, **kw):
                if nome in ("add_shape", "add_vrect"):
                    self.shapes.append(kw)
                if nome == "add_trace":
                    self.data.extend(a)
                return self
            return metodo

    go = types.ModuleType("plotly.graph_objects")
    go.Figure = _Obj
    go.Scatter = _Obj
    go.Heatmap = _Obj
    go.Bar = _Obj
    plotly = types.ModuleType("plotly")
    plotly.graph_objects = go
    sys.modules["plotly"] = plotly
    sys.modules["plotly.graph_objects"] = go
    return True
