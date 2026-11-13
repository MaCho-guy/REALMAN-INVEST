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

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
