"""매크로 탭 증시 브리핑 — 탭의 숫자와 연동 (2026-11-13).

    python tests/brief_link_test.py
"""
from __future__ import annotations

import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import brief  # noqa: E402
import daily_brief  # noqa: E402

FAILS: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


class T:
    def __init__(self, title, sev):
        self.title, self.detail, self.severity = title, "근거", sev


class FG:
    ok, score, band = True, 31.0, "공포"


kr = daily_brief.SessionBrief("kr", title="한국장", session="2026-11-12",
                              lines=[("지수", "코스피 4,100.00 (+0.50%)"), ("업종", "x")])
bad = daily_brief.SessionBrief("us", title="미국장", error="실패")
lines = brief.compose(triggers=[T("미 10년물 4.6% 돌파", 3)], fg=FG(), sessions=[kr, bad, None])
topics = [ln.topic for ln in lines]
check("임계값 · 심리 · 전일 장이 한 브리핑에", {"매크로", "심리", "전일 장"} <= set(topics), str(topics))
check("급한 것(임계값)이 맨 위", topics[0] == "매크로")
sess = next(ln for ln in lines if ln.topic == "전일 장")
check("전일 장 줄 — 시장 · 날짜 · 지수", "한국장" in sess.text and "11월 12일" in sess.text
      and "코스피" in sess.text, sess.text)
check("못 받은 시장은 줄째 빠짐", sum(1 for t in topics if t == "전일 장") == 1)
check("재료가 없어도 죽지 않음", brief.compose() == [])

src = open("app.py", encoding="utf-8").read()
a = src.index("def render_macro_tab")
body = src[a:a + 6000]
check("매크로 탭 — 임계값을 먼저 계산하고 브리핑에 넘김",
      body.index("triggers = macro_mod.evaluate_all(readings)") < body.index("render_briefing_section(")
      and "readings=readings, triggers=triggers" in body and "sessions=" in body)

print("아침 브리핑 — briefings 브랜치에서 끌어오기")
sys.path.insert(0, "tools")
import collect  # noqa: E402
import datetime as dt  # noqa: E402

app = collect.load_app()
MD = """---
title: 11/13(금) 미국장 브리핑
sources:
  - https://example.com/a
  - javascript:alert(1)
---

```
■ 지수
S&P500    6,890.25   ▲0.31%
```

- 리스크: <script>x</script>
"""
asked: list = []


def fake_get(url):
    asked.append(url)
    if url.endswith("2026-11-13.md"):
        return MD
    if url.endswith("2026-11-11.md"):
        return "# 수요일 글\n본문"
    raise OSError("404")


got = app.fetch_remote_briefings(dt.date(2026, 11, 13), get=fake_get)
check("최근 8일을 날짜로 찾음", len(asked) == 8 and all("/briefings/2026-11-" in u for u in asked),
      str(len(asked)))
check("있는 날만 · 최신순", [b.date for b in got] == ["2026-11-13", "2026-11-11"])
check("제목 · 출처(안전한 주소만)", got[0].title.startswith("11/13") and got[0].sources == ["https://example.com/a"])
check("마크다운으로만 그림 (HTML 로 풀지 않음)", got[0].fmt == "md" and not got[0].is_html)
import briefing_store as bfs  # noqa: E402
local = [bfs.Briefing(date="2026-11-13", title="손으로 쓴 글")]
merged = app._merge_briefings(local, got)
check("같은 날짜면 폴더의 글 우선", [b.title for b in merged][0] == "손으로 쓴 글" and len(merged) == 2)
check("전부 실패해도 빈 목록", app.fetch_remote_briefings(dt.date(2026, 11, 13),
                                                  get=lambda u: (_ for _ in ()).throw(OSError())) == [])

import config  # noqa: E402
check("실적 탭 없음 (내 종목 탭 스위치로)", all("earnings" not in [k for _g, items in config.tab_groups(m)
                                                        for k, _l in items] for m in ("kr", "us")))

print("아침 브리핑 — 읽기 화면 (오늘 탭)")
import components as ui  # noqa: E402

BODY = """```
📉 11/13(금) 미국장 브리핑 · 11/12(목) 마감

■ 한 줄
금리가 전부였다. 10년물 5.10%(+10bp)에
대형지수 −0.4%.

■ 지수
S&P500      7,592.40  ▼0.35%
동일가중RSP            ▼0.87%  (시총가중 대비 −0.52%p)
VIX            18.70  ▲6.92%

■ 내 지표체계 연결 ★
→ 레이어4 신규 점등: 41곳 중 40곳에서
  제한안 가결.
→ 체크리스트 9번: 미점등 유지.

■ 오늘 볼 것 (한국시각)
22:30 미 10월 PPI — 컨센 +0.4%
      (9월 실제 +1.3%)
11/14~16 삼성전자 3Q 분기보고서
```

환율: 1,330.70원/USD.

### 리스크 요인

- **금리 레벨** — 10년물 5.10% <script>alert(1)</script>
- [원문](https://example.com/x) · [나쁜 링크](javascript:alert(1))
"""
block, rest = bfs.split_block(BODY)
parsed = bfs.parse_block(block)
secs = {x["title"]: x for x in parsed["sections"]}
check("구역 4개 · '한 줄' 은 문단 하나", len(parsed["sections"]) == 4
      and secs["한 줄"]["lead"].startswith("금리가 전부였다") and "대형지수" in secs["한 줄"]["lead"])
idx = secs["지수"]["rows"]
check("숫자 줄 — 이름 · 값 · 등락", idx[0] == {"kind": "kv", "label": "S&P500",
                                        "cells": ["7,592.40", "▼0.35%"]}, str(idx[0]))
check("긴 괄호 글은 덧붙인 설명으로", idx[1].get("note") == "(시총가중 대비 −0.52%p)", str(idx[1]))
link = secs["내 지표체계 연결 ★"]["rows"]
check("→ 줄은 목록 · 이어 쓴 줄은 합침", len(link) == 2 and link[0]["kind"] == "bullet"
      and link[0]["text"].endswith("제한안 가결."), str(link))
today = secs["오늘 볼 것 (한국시각)"]["rows"]
check("일정 — 이어 쓴 줄 합침", len(today) == 2 and "(9월 실제 +1.3%)" in today[0]["text"])
check("■ 가 없으면 풀지 않음(None)", bfs.parse_block("그냥 글\n둘째 줄") is None
      and bfs.split_block("블록 없음")[0] is None)

bf = bfs.Briefing(date="2026-11-13", title="11/13(금) 미국장 브리핑", body=BODY,
                  sources=["https://example.com/a/b"])
html = ui.render_briefing_view(bf, parsed, rest)
check("등락색 — ▼ 하락 · ▲ 상승", 'bf-mv down">▼0.35%' in html and 'bf-mv up">▲6.92%' in html)
check("일정 시각 칩", '<span class="bf-when">22:30</span>' in html
      and '<span class="bf-when">11/14~16</span>' in html)
check("덧붙인 글 — 제목 · 굵게 · 목록", "<h4>리스크 요인</h4>" in html and "<b>금리 레벨</b>" in html)
check("HTML 은 글자로만 (스크립트 안 돎)", "<script>" not in html and "&lt;script&gt;" in html)
check("링크는 http(s) 만", 'href="https://example.com/x"' in html and "javascript:" not in html.replace(
    "(javascript:alert(1))", ""), "")
check("출처는 접어서 · 도메인만", "<summary>출처 1곳</summary>" in html and ">example.com</a>" in html)
check("고정폭 덩어리(pre)로 그리지 않음", "<pre" not in html and "```" not in html)

tabs = {m: [k for _g, items in config.tab_groups(m) if _g == "오늘" for k, _l in items] for m in ("kr", "us")}
check("오늘 = 요약 · 아침 브리핑 · 내 종목", all(v == ["summary", "briefing", "holdings"] for v in tabs.values()),
      str(tabs))
src = open("app.py", encoding="utf-8").read()
mb = src.split("def render_macro_tab(")[1].split("\ndef ")[0] + src.split("def render_briefing_section(")[1].split("\ndef ")[0]
check("매크로 탭에는 아침 브리핑을 그리지 않음", "render_briefing_view" not in mb and "render_briefing_head" not in mb)

shown: list = []
st = app.st
keep_md, keep_sel = st.markdown, st.selectbox
st.markdown = lambda body, **k: shown.append(str(body))
st.selectbox = lambda label, options, index=0, **k: options[index]
keep_remote, keep_all = app.load_remote_briefings, bfs.load_all
bfs.load_all = lambda *_a, **_k: []
try:
    app.load_remote_briefings = lambda use_demo: [bf, bfs.Briefing(date="2026-11-12", title="어제", body="그냥 글")]
    app.render_briefing_tab(False)
    check("탭 — 최신 글을 카드로", any("dash-brf" in h for h in shown))
    shown.clear()
    app.load_remote_briefings = lambda use_demo: [bfs.Briefing(date="2026-11-12", title="어제", body="그냥 글")]
    app.render_briefing_tab(False)
    check("모양이 다른 글은 예전처럼 그대로", any("그냥 글" in h for h in shown)
          and not any("dash-brf" in h for h in shown))
    shown.clear()
    app.load_remote_briefings = lambda use_demo: (_ for _ in ()).throw(OSError("x"))
    app.load_briefings = lambda: []
    app.render_briefing_tab(False)
    check("글이 없어도 · 받기 실패해도 그려짐", any("아직 없습니다" in h for h in shown))
finally:
    st.markdown, st.selectbox = keep_md, keep_sel
    app.load_remote_briefings, bfs.load_all = keep_remote, keep_all

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
