"""오늘 꼭 읽을 뉴스 — 사건 종류 · 내 종목 · 섹터 넘어 묶기 (2026-11-16).

    python tests/news_triage_test.py

제목은 11/16 12시 구글 뉴스 실제 응답에서 본 것을 옮겼습니다.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import config  # noqa: E402
from sources import news  # noqa: E402
from sources.news import Headline  # noqa: E402

FAILS: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=KST)          # 월요일
TUE = dt.datetime(2026, 11, 17, 12, 0, tzinfo=KST)


def h(title, sector, score, hours_ago, source="매체", more=0, now=NOW):
    ts = (now - dt.timedelta(hours=hours_ago)).timestamp()
    return Headline(title=title, url="https://x/" + str(abs(hash(title))), source=source,
                    published="2026-11-16", more=more, sector=sector, score=score, ts=ts)


MINE = {"삼성전자": ("삼성전자", "삼전"), "SK하이닉스": ("SK하이닉스", "하이닉스")}


def run(pool, now=NOW, **kw):
    return news.triage(pool, kinds=config.NEWS_EVENT_KINDS, light=config.NEWS_LIGHT_WORDS,
                       target_words=config.NEWS_TARGET_WORDS, mine=kw.pop("mine", MINE),
                       now=now, rules=kw.pop("rules", config.NEWS_TRIAGE_RULES))


# ── 1. 11/16 실제 묶음 (점수는 그날 섹터 순위 점수) ────────────────────────
POOL = {
    "battery": [h("삼성SDI, 수조원대 美 ESS용 배터리 수주", "battery", 3.79, 0.3, "헤럴드경제", 34),
                h("엠플러스, 글로벌 기업서 200억원대 전고체 배터리 조립·전극장비 수주",
                  "battery", 2.78, 2, "머니투데이", 2),
                h("우리 집 배터리·전기차가 AI 전력난을 덜어준다고?", "battery", 1.73, 7, "머니투데이")],
    "semi": [h("“낸드 가격 하락” 삼전 3%·닉스 5% ‘뚝’…코스피도 3% 가까이 약세",
               "semi", 1.79, 1, "서울경제"),
             h("美법원, D램 담합 소송 허용…삼성·SK하이닉스 'HBM 생산' 영향주나",
               "semi", 1.78, 2, "뉴스핌"),
             h("[사설] 수출 1조달러 금자탑, 반도체 편중 그늘도", "semi", 1.72, 8, "머니투데이"),
             h("\"지금 주가 흔들려도 지나고 보면 좋은 가격\"…반도체 장기 투자법",
               "semi", 1.67, 12, "뉴시스")],
    "auto": [h("기아, 국내 전동화차 판매 첫 30만대 돌파", "auto", 3.38, 22, "이투데이", 5),
             h("현대차그룹 공식 웹사이트, 국내외 시상식서 13개 부문 수상", "auto", 1.53, 26, "연합뉴스")],
    "fx": [h("美 반도체주 급락에 환율 상승 경계…외국인 수급 변수", "fx", 1.76, 4, "이데일리"),
           h("iM증권 \"이번주 환율 1320~1360원 전망\"", "fx", 1.77, 3, "비즈니스포스트")],
    "rates": [h("한은 또 올릴까?...올해 마지막 금통위 앞두고 추가 인상 전망", "rates", 1.57, 22,
                "매일경제")],
    "bio": [h("\"리가켐바이오, 3분기 임상 성과는 누적…목표가↓\"-하나", "bio", 2.35, 3, "한국경제"),
            h("한스바이오메드, 셀르디엠 임상 심포지엄 ‘셀렉트’ 개최", "bio", 1.58, 1, "라포르시안")],
}
must, worth = run(POOL)
mt = [p.head.title for p in must]
wt = [p.head.title for p in worth]
check("꼭 읽기 최대 5건", 0 < len(must) <= 5, str(mt))
check("1위 삼성SDI 수주 (34곳 + 수주)", "삼성SDI" in mt[0], str(mt))
check("낸드 하락 — 1곳뿐이어도 꼭 읽기 (내 종목 '삼전' + 가격 급변)",
      any("낸드" in t for t in mt), str(mt))
p_nand = next(p for p in must if "낸드" in p.head.title)
check("꼬리표: 내 종목 삼성전자 · 가격 급변", "내 종목 삼성전자" in p_nand.tags
      and "가격 급변" in p_nand.tags, str(p_nand.tags))
check("D램 담합 소송 — 꼭 읽기 (내 종목 SK하이닉스 + 소송)", any("D램 담합" in t for t in mt))
check("같은 제목 N곳 꼬리표 (more+1)", "같은 제목 35곳" in must[0].tags, str(must[0].tags))
allt = mt + wt
for bad in ("[사설]", "장기 투자법", "시상식", "심포지엄", "덜어준다고?"):
    check(f"가벼운 기사는 어디에도 없음: {bad}", not any(bad in t for t in allt), str(allt))
check("사건 · 내 종목 없는 기사는 꼭 읽기 아님 (환율 전망)",
      not any("1320~1360" in t for t in mt))
check("볼 만함은 꼭 읽기와 겹치지 않음", not set(mt) & set(wt))

# ── 2. 목표가만 말하는 기사는 감점 ─────────────────────────────────────────
a, _ = run({"x": [h("○○전자, 목표가 상향", "x", 2.0, 1)]})
b, w = run({"x": [h("○○전자, 3분기 영업이익 서프라이즈", "x", 2.0, 1)]})
check("사건 있으면 꼭 읽기 · 목표가만이면 아님", not a and len(b) == 1, f"{a} / {b}")

# ── 3. 섹터 넘어 같은 사건은 한 줄 ─────────────────────────────────────────
dup = {"semi": [h("삼성전자, 3분기 영업이익 12조…메모리 회복", "semi", 3.0, 2)],
       "policy": [h("삼성전자 3분기 영업이익 12조, 메모리 회복 뚜렷", "policy", 2.9, 2)]}
m, w = run(dup)
check("다른 섹터의 같은 사건은 하나만", len(m) + len(w) == 1, str([p.head.title for p in m + w]))

# ── 4. 기간 — 월요일은 주말만큼 늘림 ────────────────────────────────────────
old = {"auto": [h("현대차, 10월 美 판매 역대 최대", "auto", 3.0, 60)]}
m_mon, _ = run(old, now=NOW)
old_tue = {"auto": [h("현대차, 10월 美 판매 역대 최대", "auto", 3.0, 60, now=TUE)]}
m_tue, w_tue = run(old_tue, now=TUE)
check("월요일: 60시간 전(금요일) 사건도 꼭 읽기", len(m_mon) == 1)
check("화요일: 60시간 전은 꼭 읽기 아님 → 볼 만함", not m_tue and len(w_tue) == 1)

# ── 5. 비어도 · 옛 객체여도 안 깨짐 ─────────────────────────────────────────
m, w = run({})
check("빈 입력 → 빈 둘", m == [] and w == [])


class _Old:            # ts · score · sector 가 없는 옛 캐시 객체
    title, url, source, published, more = "삼성전자 실적 발표", "", "s", "2026-11-16", 0


m, w = run({"semi": [_Old()]})
check("옛 객체: 시각 모름 → 기간 밖으로 빠짐 (오류 없음)", m == [] and w == [])
m, w = run({"semi": [h("삼성전자 실적", "semi", 3.0, 1)]}, mine={})
check("내 종목이 비어도 사건 종류로만 판정", len(m) == 1)

# ── 6. 환율 중복 A안 — 같은 날 + 숫자 앞자리 ─────────────────────────────────
d1 = dt.datetime(2026, 11, 12, 15, 40, tzinfo=KST)
d2 = dt.datetime(2026, 11, 13, 15, 40, tzinfo=KST)
s1 = news._sig("美 긴축 우려에도 환율 2.9원↓…1330.7원 마감(종합)", d1)
s2 = news._sig("엔화 소폭 강세에 달러 숨 고르기…원·달러 환율 1330원대 마감 [김혜란의 FX]", d1)
s3 = news._sig("엔화 소폭 강세에 달러 숨 고르기…원·달러 환율 1330원대 마감 [김혜란의 FX]", d2)
check("같은 날 1330.7원 마감 = 1330원대 마감", news.same_story(s1, s2))
check("다른 날이면 같은 사건 아님", not news.same_story(s1, s3))
check("날짜 모르면 이 규칙 안 씀", not news.same_story(news._sig(
    "美 긴축 우려에도 환율 2.9원↓…1330.7원 마감(종합)"), news._sig(
    "엔화 소폭 강세에 달러 숨 고르기…원·달러 환율 1330원대 마감 [김혜란의 FX]")))

# ── 7. 순위가 score · ts · sector 를 채움 ───────────────────────────────────
UTC_NOW = NOW.astimezone(dt.timezone.utc)
rows = [(UTC_NOW - dt.timedelta(hours=2), Headline("삼성SDI 美 ESS 배터리 수주", "https://x", "연합뉴스", "2026-11-16"))]
got = news.rank_stories(rows, 3, now=UTC_NOW, tier=config.NEWS_TIER_SOURCES)
check("rank_stories: score · ts 채움", got[0].score > 0 and abs(got[0].ts - rows[0][0].timestamp()) < 1,
      f"{got[0].score} {got[0].ts}")
_orig = news._rss_body
news._rss_body = lambda q, d: ("<item><title>삼성SDI 수주 - 연합뉴스</title><link>https://x</link>"
                               "<pubDate>Mon, 16 Nov 2026 02:00:00 GMT</pubDate>"
                               '<source url="u">연합뉴스</source></item>')
out, _err = news.fetch_sector_news([("battery", "2차전지", "q")], rank=True, max_days=7)
news._rss_body = _orig
check("fetch_sector_news: sector 키를 채움", out["battery"][0].sector == "battery", str(out))


# ── 7-b. 대표 제목 = 가장 많은 매체가 쓴 제목 (11/16 12:30 실화면 — SDI 빠짐) ─────
base = UTC_NOW - dt.timedelta(hours=1)
rows = [(base - dt.timedelta(minutes=i), Headline("삼성SDI, 수조원대 美 ESS용 배터리 수주", f"https://x/{i}",
                                                 src, "2026-11-16"))
        for i, src in enumerate(["헤럴드경제", "매체A", "매체B", "매체C", "매체D"])]
rows.append((UTC_NOW - dt.timedelta(minutes=5),
             Headline("삼성SDI, 美 블랙록 계열사서 '수조원 잭팟'…ESS 날개 달았다", "https://x/bw",
                      "비즈워치", "2026-11-16")))
got = news.rank_stories(rows, 3, now=UTC_NOW, tier=config.NEWS_TIER_SOURCES)
check("한 사건으로 묶임", len(got) == 1, str([g.title for g in got]))
check("대표 = 5곳이 쓴 제목 (주요 매체 · 최신인 1곳짜리가 아님)", "수주" in got[0].title, got[0].title)
check("보도 수 = 그 무리의 다른 매체 4곳", got[0].more == 4, f"more={got[0].more}")
check("링크는 그 무리의 주요 매체", got[0].source == "헤럴드경제", got[0].source)
m, _w = run({"battery": [dataclasses.replace(got[0], sector="battery")]}, now=NOW)
check("→ 꼭 읽기에 들어감", len(m) == 1 and "수주 · 계약" in m[0].tags, str(m))

# ── 8. 화면 ────────────────────────────────────────────────────────────────
import components as ui  # noqa: E402

labels = {k: lbl for k, lbl, _q in config.KR_SECTORS}
must, worth = run(POOL)
html = ui.render_news_triage(must, worth, labels)
check("화면: ① 꼭 읽기 · ② 볼 만함", "① 오늘 꼭 읽기" in html and "② 볼 만함" in html)
check("화면: 매체 · 한국 시각 · 섹터", "헤럴드경제 · 11/16 11:42 · 2차전지" in html, html[:400])
check("화면: 내 종목 꼬리표 강조", 'dash-tri-tag mine' in html)
compact = ui.render_news_triage(must, worth, labels, compact=True)
check("요약용: 볼 만함 안 그림", "② 볼 만함" not in compact and "dash-tri-card" in compact)
check("빈 꼭 읽기 → 이유 한 줄", "아직 없습니다" in ui.render_news_triage([], [], labels))
check("링크는 http 만", "javascript:" not in ui.render_news_triage(
    [news.Picked(Headline("t", "javascript:alert(1)", "s", "2026-11-16"), [], 1.0)], [], labels))

# ── 9. 연결 ────────────────────────────────────────────────────────────────
app_src = open("app.py", encoding="utf-8").read()
check("섹터 뉴스는 후보 8개를 받음", "limit=config.SECTOR_NEWS_POOL" in app_src)
check("섹터 칸 = rest_by_sector(①② 빼고 3개)", "news.rest_by_sector(sector_news or {}, must + worth" in app_src
      and "per=config.SECTOR_NEWS_PER" in app_src)
check("triage 에 일정 · 금액 넘김", "upcoming=_news_upcoming(use_demo)" in app_src
      and "amount_rules=config.NEWS_AMOUNT_RULES" in app_src)
check("뉴스 탭: 꼭 읽기 → 섹터별 전체(접는 칸)", app_src.index("ui.render_news_triage(must, worth, labels)")
      < app_src.index('st.expander(f"섹터별 전체 보기'))
# 11/19: 요약에는 뉴스 목록이 아니라 **한 줄**(몇 건 · 내 종목이 걸렸나)만 — 목록은 뉴스 화면에
check("요약에는 꼭 읽기 한 줄만 (목록은 뉴스 화면)", "_render_news_must" not in app_src
      and "news=news_pair" in app_src and "news_pair = _news_triage(got[0], use_demo)" in app_src)
import summary as _smn  # noqa: E402
_mine = news.Picked(Headline("SK하이닉스 수출 1조달러", "u"), ["내 종목 SK하이닉스"], 4.0)
_etc = news.Picked(Headline("삼성SDI 수조원대 ESS 수주", "u"), ["수주 · 계약"], 3.0)
_r = _smn.row_news([_etc, _mine], [])
check("요약 뉴스 줄 — 건수 · 내 종목 건수 · 내 종목 제목이 앞", _r.headline == "2건 · 내 종목 1건"
      and "SK하이닉스" in _r.detail and _r.level == "watch" and _r.goto == "kr_flows", str(vars(_r)))
check("내 종목이 안 걸리면 조용함", _smn.row_news([_etc], []).level == "quiet")
check("아직 못 받았으면 '받는 중'", _smn.row_news(None, None).level == "unknown")
# 11/19 사용자: "미국장은 왜 한국 뉴스가 뜨지 — 미국 걸로"
check("미국 요약의 뉴스 줄은 미국 뉴스 화면으로, 한국은 한국 뉴스 화면으로",
      _smn.row_news([_etc], [], "us").goto == "us_news"
      and _smn.row_news([_etc], [], "kr").goto == "kr_flows")
check("미국 요약은 미국 뉴스를 받는다 (한국 섹터 뉴스가 아니라)",
      "_soft(load_us_news, use_demo, default=None)" in app_src
      and 'if market == "us":\n            got = (load_us_news(use_demo)' in app_src)
check("미국 주제는 한국 섹터와 키가 겹치지 않는다 (감점 · 가점 낱말을 키로 찾음)",
      not ({k for k, _l, _q in config.US_SECTORS} & {k for k, _l, _q in config.KR_SECTORS})
      and all(k in config.SECTOR_NEWS_MUST for k, _l, _q in config.US_SECTORS))
check("미국 주제마다 검색어가 '주제 + 사건' 꼴 (낱말을 늘어놓으면 AND 라 0건 — 11/13)",
      all("OR" in q for _k, _l, q in config.US_SECTORS))
check("미국 관심종목의 한국어 이름이 다 있다 (ETF 포함) — 내 종목 꼬리표가 붙게",
      all(i.symbol in config.NEWS_NAME_KO for i in config.SECTION_WATCHLIST.instruments
          if i.source == "yahoo"),
      str([i.symbol for i in config.SECTION_WATCHLIST.instruments
           if i.source == "yahoo" and i.symbol not in config.NEWS_NAME_KO]))
check("미국 뉴스 화면이 미국 '읽기' 메뉴에 있다",
      "us_news" in dict(config.MARKET_TABS["us"])["읽기"]
      and "us_news" not in config.market_tab_keys("kr")
      and 'render_us_news_tab(opts["demo"])' in app_src)
check("요약은 기다리지 않음 (_soft)", "_soft(load_sector_news, use_demo, default=None)" in app_src)
check("요약 화면 미리 받기에 섹터 뉴스", '"섹터 뉴스": lambda: load_sector_news(use_demo)' in app_src)
check("캐시 버전 올림 (모양 바뀜)", "@swr.cached(1_800, version=1)\ndef load_sector_news" in app_src)

# ── 10. 금액 가중 (제안 1) ─────────────────────────────────────────────────
for t, want in [("삼성SDI, 수조원대 美 ESS용 배터리 수주", 20_000), ("엠플러스 200억원대 장비 수주", 200),
                ("대한조선, 2,498억 규모 수주", 2_498), ("현대차, 2조 5천억 투자", 25_000),
                ("3천억 규모 계약", 3_000), ("반도체 수출 166억달러", 166 * 1_350),
                ("환율 1,336.7원 마감", None), ("국고채 담합 1.6조 과징금", 16_000)]:
    got = news.amount_eok(t)
    check(f"금액 읽기: {t}", got == want, f"{got} ≠ {want}")
AR = config.NEWS_AMOUNT_RULES
big = h("○○중공업, 1.2조원 규모 LNG선 수주", "ship", 2.0, 2)
mid = h("○○중공업, 2천억원 규모 LNG선 수주", "ship", 2.0, 2)
small = h("○○테크, 120억원 규모 장비 수주", "ship", 2.0, 2)
none_ = h("○○중공업, LNG선 수주", "ship", 2.0, 2)
imps = {}
for x in (big, mid, small, none_):
    m, w = news.triage({"ship": [x]}, kinds=config.NEWS_EVENT_KINDS, mine={}, amount_rules=AR,
                       now=NOW, rules=config.NEWS_TRIAGE_RULES)
    imps[x.title] = (m + w)[0].importance if m + w else None
check("금액 순서: 1조↑ > 1천억↑ > 금액 없음 > 300억 미만",
      imps[big.title] > imps[mid.title] > imps[none_.title] > imps[small.title], str(imps))
m, _ = news.triage({"ship": [big]}, kinds=config.NEWS_EVENT_KINDS, mine={}, amount_rules=AR,
                   now=NOW, rules=config.NEWS_TRIAGE_RULES)
check("꼬리표 '1조원 이상'", "1조원 이상" in m[0].tags, str(m[0].tags))
m, w = news.triage({"x": [h("외국인 8.5조 순매수", "x", 2.0, 2)]}, kinds=config.NEWS_EVENT_KINDS,
                   mine={}, amount_rules=AR, now=NOW, rules=config.NEWS_TRIAGE_RULES)
check("사건 종류 없는 제목엔 금액 가점 없음", all("1조원 이상" not in p.tags for p in m + w))

# ── 11. 일정 가점 (제안 2) ─────────────────────────────────────────────────
UP = [("금통위 D-2", config.NEWS_SCHEDULE_WORDS["금통위"])]
rate = h("한은, 기준금리 인상 여부 주목", "rates", 1.4, 3)
m0, w0 = news.triage({"rates": [rate]}, kinds=config.NEWS_EVENT_KINDS, mine={}, now=NOW,
                     rules=config.NEWS_TRIAGE_RULES)
m1, w1 = news.triage({"rates": [rate]}, kinds=config.NEWS_EVENT_KINDS, mine={}, upcoming=UP,
                     now=NOW, rules=config.NEWS_TRIAGE_RULES)
i0 = (m0 + w0)[0].importance
i1 = (m1 + w1)[0].importance
check("3일 안 일정 주제면 +0.8", abs(i1 - i0 - 0.8) < 1e-6, f"{i0} → {i1}")
check("꼬리표 '금통위 D-2'", "금통위 D-2" in (m1 + w1)[0].tags, str((m1 + w1)[0].tags))
check("일정만 걸려도 꼭 읽기 후보(사건으로 침)", len(m1) == 1 or i1 < config.NEWS_TRIAGE_RULES["must_min"])
check("일정 이름표에 금통위 · FOMC · CPI", {"금통위", "FOMC", "CPI"} <= set(config.NEWS_SCHEDULE_WORDS))
check("일정 기간 3일", config.NEWS_SCHEDULE_DAYS == 3)

# ── 12. 섹터 칸 — ①② 와 가벼운 기사 빼고 다음 순위로 ──────────────────────
pool = {"semi": [h("삼성전자, 3분기 영업이익 12조…메모리 회복", "semi", 3, 1),
                 h("[사설] 반도체 편중 그늘", "semi", 2.9, 1),
                 h("SK하이닉스 HBM4 양산", "semi", 2.8, 1),
                 h("낸드 가격 반등 조짐", "semi", 2.7, 1),
                 h("D램 재고 감소", "semi", 2.6, 1)],
        "fx": [h("삼성전자 3분기 영업이익 12조, 메모리 회복 뚜렷", "fx", 2.0, 1),
               h("환율 1330원 마감", "fx", 1.9, 1)]}
picked = [news.Picked(pool["semi"][0], [], 4.0)]
rest = news.rest_by_sector(pool, picked, light=config.NEWS_LIGHT_WORDS, per=3)
rt = [x.title for x in rest["semi"]]
check("①② 기사 빠짐 · 사설 빠짐 · 다음 순위로 3건",
      rt == ["SK하이닉스 HBM4 양산", "낸드 가격 반등 조짐", "D램 재고 감소"], str(rt))
check("다른 섹터의 같은 사건도 빠짐", [x.title for x in rest["fx"]] == ["환율 1330원 마감"],
      str([x.title for x in rest["fx"]]))
rest2 = news.rest_by_sector({"x": [pool["semi"][0]]}, picked, per=3)
check("다 빠지면 빈 목록", rest2["x"] == [])
check("앱: 빈 섹터엔 '위 ①②에 있습니다'", "위 ① 꼭 읽기 · ② 볼 만함에 있습니다" in app_src)

# ── 13. 섹터 카드 모양 ─────────────────────────────────────────────────────
html = ui.render_sector_news([("fx", "환율", "원달러 환율 (마감 OR 전망)")],
                             {"fx": [Headline("환율 1330원 마감", "https://x", "뉴스1", "2026-11-12", more=2)]}, {})
check("불릿 없는 목록 · 제목 칸 · 메타 줄", 'class="dash-sector-list"' in html
      and 'class="dash-sector-t"' in html and 'class="dash-sector-m">뉴스1 · 11/12 · 관련 2곳' in html, html)
check("밑줄 링크 클래스(dash-inline-link) 안 씀", "dash-inline-link" not in html)
check("머리 한 줄(이름 · 검색어)", "dash-sector-head" in html)
theme_src = open("theme.py", encoding="utf-8").read()
check("밑줄 없앰이 스트림릿 링크 규칙(클래스 + a)보다 구체적",
      ".dash-sector a.dash-sector-t {{ text-decoration: none" in theme_src)
check("제목 최대 2줄", "-webkit-line-clamp: 2" in theme_src[theme_src.index(".dash-sector-t {{"):][:300])

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
