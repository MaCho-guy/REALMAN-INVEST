"""구글 뉴스 — 오래된 기사 거르기 (2026-11-13 '섹터별 뉴스에 엄청 오래된 것들').

    python tests/news_age_test.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

from sources import news  # noqa: E402

FAILS: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


NOW = dt.datetime(2026, 11, 13, 0, 0, tzinfo=dt.timezone.utc)


def item(title, day, mon="Nov", year=2026, hh="02:13"):
    return (f"<item><title>{title}</title><link>https://x/{title}</link>"
            f"<pubDate>Tue, {day:02d} {mon} {year} {hh}:00 GMT</pubDate>"
            f'<source url="https://m">매체</source></item>')


# 관련도 순 — 맨 위가 가장 오래된 기사 (실제로 본 모양)
body = "".join([item("옛기사", 2, "Mar"), item("작년", 20, "Dec", 2025), item("어제", 12),
                item("일주일전", 6), item("오늘새벽", 12, hh="23:50"), item("날짜없음", 99)])
got = news.parse_google_rss(body, 3, 7, now=NOW)
check("최근 기사부터 3건", [h.title for h in got] == ["오늘새벽", "어제", "일주일전"],
      str([h.title for h in got]))
check("기간 밖 · 날짜 모르는 기사는 버림",
      not {"옛기사", "작년", "날짜없음"} & {h.title for h in news.parse_google_rss(body, 9, 7, now=NOW)})
check("마감 기사(2일) — 하루 전까지만",
      [h.title for h in news.parse_google_rss(body, 3, 2, now=NOW)] == ["오늘새벽", "어제"])
check("매체 · 날짜 표시",
      got[0].source == "매체" and got[0].published == "2026-11-12", f"{got[0]}")
check("같은 제목은 한 번만", len(news.parse_google_rss(body + item("어제", 12), 9, 7, now=NOW)) == 3)

import components as ui  # noqa: E402

html = ui.render_sector_news([("semi", "반도체", "q")], {"semi": got}, {})
check("화면에 날짜", "11/12" in html, html[:200])
html = ui.render_sector_news([("semi", "반도체", "q")], {}, {"semi": "최근 7일 기사가 없습니다."})
check("비면 이유", "최근 7일" in html)

src = open("sources/news.py", encoding="utf-8").read()
check("검색어에 기간 (when:Nd)", 'when:{max_days}d' in src)
app_src = open("app.py", encoding="utf-8").read()
check("마감 기사는 2일", "max_days=2" in app_src)

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
