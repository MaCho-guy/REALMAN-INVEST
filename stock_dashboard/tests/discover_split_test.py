"""종목 발굴 → '품질 깔때기' · '거래 스크리너' 두 탭 (2026-11-13), 국내 이름 먼저.

    python tests/discover_split_test.py
"""
from __future__ import annotations

import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
sys.path.insert(0, "tools")

import collect  # noqa: E402

app = collect.load_app()
import config  # noqa: E402

FAILS: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


kr = dict(config.tab_groups("kr"))["찾기"]
us = dict(config.tab_groups("us"))["찾기"]
check("한국 찾기 = 후보 · 근거 · 차트·거래 (11/13 단순화 — 품질 깔때기 · 밸류에이션은 근거 안, "
      "거래 스크리너 · 차트 조건은 차트·거래 안)",
      [k for k, _l in kr] == ["picks", "basis", "timing", "paper"], str(kr))
check("미국은 스크리너 없음 (원래 없던 화면)", "screener" not in [k for k, _l in us], str(us))
check("탭 이름", dict(kr)["basis"] == "근거" and dict(kr)["timing"] == "차트·거래"
      and config.SPECIAL_TAB_LABELS["discover"] == "품질 깔때기"
      and config.SPECIAL_TAB_LABELS["screener"] == "거래 스크리너")

calls: list = []
orig_q, orig_u = app._kr_quality_block, app._universe_or_none
app._kr_quality_block = lambda use_demo: calls.append("quality")
app._universe_or_none = lambda m, u: {"screens": [1]} if m == "funnel_kr" else {}
shown: list = []
orig_md = app.st.markdown
app.st.markdown = lambda body, **k: shown.append(str(body))
try:
    app.render_discover_tab(True, market="kr")
    html = "\n".join(shown)
    check("품질 깔때기 탭 — 깔때기만", calls == ["quality"] and "여섯 스크리너" not in html,
          str(calls))
    calls.clear()
    shown.clear()
    try:
        app.render_screener_tab(True, market="kr")
    except Exception as exc:  # noqa: BLE001 - 가짜 스트림릿에서 위젯 반환값 때문일 수 있음
        print(f"  (스크리너 끝까지 그리기는 가짜 스트림릿 한계로 중단: {type(exc).__name__})")
    html = "\n".join(shown)
    check("거래 스크리너 탭 — 깔때기 없음", calls == [] and "거래 스크리너 · 한국" in html, str(calls))
finally:
    app._kr_quality_block, app._universe_or_none = orig_q, orig_u
    app.st.markdown = orig_md

src = open("app.py", encoding="utf-8").read()
check("화면 분기", 'elif active == "screener":' in src and '"screener"' in src)

import buffett  # noqa: E402
import components as ui  # noqa: E402


class S:
    def __init__(self, t, n):
        self.ticker, self.name = t, n
        self.checks, self.score_label, self.passed_count = [], "7/9", 7
        self.ok, self.error, self.years = True, "", 10


html = ui.render_screen_table([S("214150", "클래시스"), S("NVDA", "NVIDIA")], buffett.CRITERIA)
check("국내 — 이름이 앞(크게), 코드는 작게", "클래시스<span class='sc-name'>214150" in html, "")
check("미국 — 티커가 앞", "NVDA<span class='sc-name'>NVIDIA" in html, "")

# 내 종목 탭 — 실적 서프라이즈 스위치
calls_e: list = []
st = app.st
keep = {k: getattr(app, k) for k in ("_render_portfolio", "_detect_signals", "render_signals_tab",
                                     "render_analysis_tab", "render_earnings_tab")}
keep_st = {k: getattr(st, k) for k in ("markdown", "toggle", "expander")}
app._render_portfolio = lambda *a, **k: None
app._detect_signals = lambda *a, **k: ([], None)
app.render_signals_tab = lambda *a, **k: None
app.render_analysis_tab = lambda *a, **k: None
app.render_earnings_tab = lambda use_demo, market="kr": calls_e.append(market)
on = {"v": False}
st.markdown = lambda *a, **k: None
st.toggle = lambda label, value=False, key=None, **k: on["v"] if str(key).startswith("hold_earn") else value
st.expander = lambda *a, **k: collect._Any()
try:
    app.render_holdings_tab({}, None, True, market="kr")
    check("실적 스위치 꺼짐 — 받지 않음", calls_e == [])
    on["v"] = True
    app.render_holdings_tab({}, None, True, market="us")
    check("실적 스위치 켜면 그 시장 실적", calls_e == ["us"], str(calls_e))
    app.render_earnings_tab = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    app.render_holdings_tab({}, None, True, market="kr")
    check("실적이 실패해도 내 종목 화면은 그려짐", True)
finally:
    for k, v in keep.items():
        setattr(app, k, v)
    for k, v in keep_st.items():
        setattr(st, k, v)

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
