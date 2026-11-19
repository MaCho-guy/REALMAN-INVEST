"""스트림릿 없이 app.py 의 화면 함수를 끝까지 돌리는 받아쓰기 모듈 (2026-11-19).

왜 필요한가
    1. 테스트는 app.py 를 글자로만 검사했습니다 (스트림릿이 없는 곳에서도 돌아야 해서).
       그래서 화면 함수 안의 오타 · 없는 속성은 배포해야 드러났습니다 — 11/19 에
       `cli.label`(없는 속성)이 그렇게 숨어 있었습니다.
    2. 프리뷰(tools/preview.py)는 화면을 **따로** 조립해서 앱과 어긋났습니다
       (README '반응형 CSS — 없던 걸 넣었습니다'). 이 모듈로 앱 코드를 그대로 돌려
       받아 적으면 프리뷰와 앱이 같은 코드에서 나옵니다 (tools/app_preview.py).

무엇을 하나
    `install()` 이 `streamlit` 자리에 가짜 모듈을 넣습니다. `st.markdown` 은 글을
    받아 적고, 위젯은 **기본값을 돌려주며** 정적인 HTML 한 줄로 받아 적습니다.
    접는 칸(expander)은 <details> 로, 칸 나누기(columns)는 <div> 로 감쌉니다.

무엇이 아닌가
    스트림릿을 흉내 내는 것이 아닙니다 — 화면이 '끝까지 그려지는가' 와 '무엇이
    찍히는가' 만 봅니다. 위젯을 눌렀을 때의 동작, 스트림릿이 만드는 DOM
    (data-testid …)에 기대는 CSS 는 실제 앱에서 확인해야 합니다.
"""
from __future__ import annotations

import html as _html
import sys
import types

#: 받아 적은 조각들 (순서대로)
OUT: list[str] = []
#: 만난 위젯 — (종류, 라벨, key, 그 밖)
WIDGETS: list[tuple] = []
#: 내비 · 시장 전환처럼 프리뷰가 직접 그리는 위젯 — 받아 적지 않습니다
SKIP_KEY_PREFIXES = ("navbtn_", "market", "mnav")


def reset() -> None:
    OUT.clear()
    WIDGETS.clear()


def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


class _State(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as exc:
            raise AttributeError(k) from exc

    def __setattr__(self, k, v):
        self[k] = v


class _Ctx:
    """with 로 여닫는 칸 — 열 때 · 닫을 때 받아 적을 글을 가질 수 있습니다."""

    def __init__(self, open_html: str = "", close_html: str = "", mute: bool = False):
        self._open, self._close, self._mute = open_html, close_html, mute
        self._mark = 0

    def __enter__(self):
        self._mark = len(OUT)
        if self._open and not self._mute:
            OUT.append(self._open)
        return self

    def __exit__(self, *exc):
        if self._mute:
            del OUT[self._mark:]            # 이 칸 안에서 찍힌 것은 버립니다
        elif self._close:
            OUT.append(self._close)
        return False

    def __getattr__(self, name):
        return getattr(sys.modules["streamlit"], name)

    def __call__(self, *a, **k):
        return self


class _Slot:
    """st.empty() — 자리를 잡아 두고 나중에 채웁니다."""

    def __init__(self):
        self._at = len(OUT)
        OUT.append("")

    def _put(self, body="", *a, **k):
        if 0 <= self._at < len(OUT):
            OUT[self._at] = str(body)

    markdown = write = info = warning = error = success = caption = _put

    def empty(self):
        self._put("")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return getattr(sys.modules["streamlit"], name)


def install() -> types.ModuleType:
    """sys.modules 에 가짜 streamlit 을 넣고 돌려줍니다. 여러 번 불러도 됩니다."""
    st = types.ModuleType("streamlit")
    st.session_state = _State()
    st.query_params = _State()
    st.secrets = _State()
    st.context = types.SimpleNamespace(headers={})
    st.__version__ = "0.0-fakest"

    def _skip(key) -> bool:
        return isinstance(key, str) and key.startswith(SKIP_KEY_PREFIXES)

    def markdown(body="", *a, **k):
        OUT.append(str(body))

    for name in ("markdown", "write", "html"):
        setattr(st, name, markdown)

    def _boxed(cls):
        def f(body="", *a, **k):
            OUT.append(f'<div class="fs-box fs-{cls}">{_esc(body)}</div>')
        return f

    for name in ("info", "warning", "error", "success", "caption", "text",
                 "subheader", "header", "title"):
        setattr(st, name, _boxed(name))
    st.code = lambda body="", *a, **k: OUT.append(f'<pre class="fs-code">{_esc(body)}</pre>')

    def _val(key, default):
        if key is not None and key in st.session_state:
            return st.session_state[key]
        if key is not None:
            st.session_state[key] = default
        return default

    def button(label="", key=None, on_click=None, args=(), kwargs=None, **k):
        WIDGETS.append(("button", label, key, k.get("type")))
        if not _skip(key):
            kind = " fs-primary" if k.get("type") == "primary" else ""
            OUT.append(f'<span class="fs-btn{kind}">{_esc(label)}</span>')
        return False

    st.button = st.download_button = st.link_button = st.form_submit_button = button

    def toggle(label="", value=False, key=None, **k):
        WIDGETS.append(("toggle", label, key, None))
        val = _val(key, value)
        OUT.append(f'<div class="fs-toggle{" on" if val else ""}"><i></i>{_esc(label)}</div>')
        return val

    st.toggle = st.checkbox = toggle

    def _pick(kind):
        def f(label="", options=(), index=0, key=None, default=None,
              format_func=None, **k):
            options = list(options)
            WIDGETS.append((kind, label, key, tuple(options)))
            if kind in ("segmented_control", "pills"):
                d = default
            elif kind == "multiselect":
                d = list(default or [])
            else:
                d = options[index] if options and index is not None else None
            val = _val(key, d)
            if _skip(key):
                return val
            fmt = format_func or (lambda x: x)
            if kind == "selectbox":
                OUT.append(f'<div class="fs-select">{_esc(fmt(val)) if val in options else ""}'
                           " ▾</div>")
            else:
                chosen = val if isinstance(val, list) else [val]
                cells = "".join(
                    f'<span class="fs-seg-i{" on" if o in chosen else ""}" '
                    f'data-key="{_esc(key or "")}" data-val="{_esc(o)}">{_esc(fmt(o))}</span>'
                    for o in options)
                OUT.append(f'<div class="fs-seg" data-key="{_esc(key or "")}">{cells}</div>')
            return val
        return f

    for kind in ("radio", "selectbox", "segmented_control", "pills", "multiselect"):
        setattr(st, kind, _pick(kind))

    def _input(label="", value=None, key=None, **k):
        WIDGETS.append(("input", label, key, None))
        return _val(key, value if value is not None else "")

    st.text_input = st.text_area = _input
    st.number_input = (lambda label="", min_value=None, max_value=None, value=0, key=None,
                       **k: _val(key, value))
    st.slider = (lambda label="", min_value=0, max_value=100, value=None, key=None,
                 **k: _val(key, value if value is not None else min_value))

    def columns(spec=1, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx('<div class="fs-col">', "</div>") for _ in range(n)]

    st.columns = columns
    st.tabs = lambda labels, **k: [_Ctx(f'<div class="fs-tab"><b>{_esc(lb)}</b>', "</div>")
                                   for lb in labels]

    def expander(label="", expanded=False, **k):
        return _Ctx(f'<details class="fs-exp"{" open" if expanded else ""}>'
                    f"<summary>{_esc(label)}</summary>", "</details>")

    st.expander = expander
    # 떠오르는 칸(popover)은 평소 닫혀 있습니다 — 안의 것은 받아 적지 않습니다
    st.popover = lambda *a, **k: _Ctx(mute=True)
    for name in ("container", "form", "spinner", "status", "chat_message", "dialog"):
        setattr(st, name, lambda *a, **k: _Ctx())
    st.empty = lambda *a, **k: _Slot()
    st.sidebar = _Ctx(mute=True)

    def _cache(*a, **k):
        if a and callable(a[0]) and not k:
            a[0].clear = lambda *x, **y: None
            return a[0]

        def deco(fn):
            fn.clear = lambda *x, **y: None
            return fn
        return deco

    st.cache_data = _cache
    st.cache_resource = _cache
    st.cache_data.clear = lambda *a, **k: None
    st.cache_resource.clear = lambda *a, **k: None

    def fragment(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda fn: fn

    st.fragment = fragment
    for name in ("rerun", "stop", "set_page_config", "toast", "divider", "image",
                 "dataframe", "table", "json", "metric", "balloons"):
        setattr(st, name, lambda *a, **k: None)
    st.progress = lambda *a, **k: _Ctx()

    comp = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")
    v1.html = lambda body="", **k: OUT.append(str(body))
    comp.v1 = v1
    st.components = comp
    cfg = types.ModuleType("streamlit.config")
    cfg.get_option = lambda name: None
    cfg.set_option = lambda *a, **k: None
    st.config = cfg
    sys.modules.update({"streamlit": st, "streamlit.components": comp,
                        "streamlit.components.v1": v1, "streamlit.config": cfg})
    return st


def render_screen(app, st, market: str, key: str, *, demo: bool = True,
                  state: dict | None = None, query: dict | None = None) -> str:
    """app.render_body 를 한 화면만 돌려 받아 적은 글을 돌려줍니다."""
    reset()
    st.session_state.clear()
    st.query_params.clear()
    st.session_state["market"] = market
    st.session_state[f"nav_{market}"] = key
    st.query_params["m"] = market
    st.query_params["s"] = key
    for k, v in (state or {}).items():
        st.session_state[k] = v
    for k, v in (query or {}).items():
        st.query_params[k] = v
    app.render_body({"demo": demo, "fx_override": None, "phone": False, "auto": False,
                     "convention": "kr", "interval": 60, "notes": True, "stack": True,
                     "market": market})
    return "\n".join(OUT)
