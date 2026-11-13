"""내 종목 › 실적 서프라이즈에 국내 본주(현대차 등)가 섞이지 않는가 (2026-11-14).

    python tests/my_codes_test.py
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


watch = [i.symbol for i in config.SECTION_WATCHLIST.instruments
         if i.source == "naver" and i.symbol.isdigit()]
local_only = [i.symbol for i in config.SECTION_LOCAL.instruments
              if i.symbol not in watch]

app._kr_held_codes = lambda use_demo: {"123456"}     # 가짜 보유 종목
_my = app._kr_my_codes
app._kr_my_codes = lambda use_demo: _my(use_demo) | {"123456"}
mine = [c for c in app._kr_watch_codes(False) if c in app._kr_my_codes(False)]
check("보유 종목이 들어간다", "123456" in mine, str(mine))
check("관심종목 한국 종목이 들어간다", all(c in mine for c in watch), str(mine))
check("국내 본주에만 있는 종목(현대차 · 삼성전자우)은 빠진다",
      not any(c in mine for c in local_only), f"본주 전용 {local_only} / 결과 {mine}")
check("중복 없음", len(mine) == len(set(mine)))

src = open("app.py", encoding="utf-8").read()
body = src[src.index("def render_earnings_tab"):src.index("def render_research_tab")]
check("실적 서프라이즈(한국)는 _kr_my_codes 를 쓴다",
      "_kr_my_codes(use_demo)" in body
      and "codes = [c for c in _kr_watch_codes(use_demo) if c in _mine]" in body)
check("보유 종목이 맨 앞", mine[0] == "123456", str(mine))

print()
if FAILS:
    print(f"실패 {len(FAILS)}건: {FAILS}")
    sys.exit(1)
print("전부 통과")
