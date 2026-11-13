"""섹터 뉴스 순위 — 같은 사건 묶기 · 매체 · 섹터 낱말 (2026-11-13 '읽을만한 정보로').

    python tests/sector_news_rank_test.py

제목은 11/13 12시 구글 뉴스 실제 응답에서 본 모양을 줄여 옮겼습니다.
"""
from __future__ import annotations

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


NOW = dt.datetime(2026, 11, 13, 3, 0, tzinfo=dt.timezone.utc)


def at(hours_ago):
    return NOW - dt.timedelta(hours=hours_ago)


def row(title, source, hours_ago=5):
    w = at(hours_ago)
    return (w, Headline(title=title, url=f"https://x/{abs(hash(title))}", source=source,
                        published=w.date().isoformat()))


def sig(t):
    return news._sig(t)


TIER = config.NEWS_TIER_SOURCES

# ── 1. 같은 사건인가 ─────────────────────────────────────────────────────────
same_pairs = [
    ("원·달러 환율, 2.9원 내린 1330.7원 마감", "美 긴축 우려에도 환율 2.9원↓…1330.7원 마감(종합)"),
    ("대한조선, 2498억 규모 원유 운반선 2척 수주",
     "대한조선, 수에즈맥스급 원유운반선 2척 수주…올해 누적 19척"),
    ("대웅제약, ‘장 점막 재생’ 장질환 치료제 임상 1상 진입",
     "대웅제약 “염증성 장질환 신약, 식약처로부터 임상 1상 승인”"),
    ("셀트리온, 비세큐마 호주 품목허가 신청", "셀트리온 “건선 치료 바이오시밀러, 호주 품목허가 신청”"),
    ("반도체 수출 4배로 껑충…‘1조 달러’ 곧 달성 전망", "반도체 수출 4배 폭증…수출 1조달러 눈앞"),
]
for a, b in same_pairs:
    check(f"같은 사건: {a[:16]}…", news.same_story(sig(a), sig(b)))

diff_pairs = [
    ("대한조선, 2498억 규모 원유 운반선 2척 수주", "한화에어로, 육군본부 과장단 초청…방산수출 협력 강조"),
    ("반도체 수출 4배로 껑충…‘1조 달러’ 눈앞", "젠슨 황 사태에 美의회 대중 반도체 수출통제 강화 입법 탄력"),
    ("네이버, 3Q 영업익 4513억원…투자 늘려 전년比 20.9%↓", "넥슨, 신작 공백 뚫고 3Q 어닝서프라이즈"),
]
for a, b in diff_pairs:
    check(f"다른 사건: {a[:12]} / {b[:12]}", not news.same_story(sig(a), sig(b)))

# ── 1-b. 11/13 12:50 실화면 (첫 배포) — 섹터별 3줄 ──────────────────────────
# 같은 사건: 금리 1·2, 정책 1·2 (조사 차이로 못 묶었음). 나머지는 서로 다른 사건.
LIVE = {
    "rates": ["금통위원 과반 \"추가 금리인상 필요\"…AI 증시 충격 '경계'",
              "금통위원들 \"연속 금리 인상 효과 점검해야\"…과반이 추가 긴축에 공감",
              "美 빅스텝 거론에 한은 금리 인상 압력 커지나"],
    "fx": ["엔화 소폭 강세에 달러 숨 고르기…원·달러 환율 1330원대 마감 [김혜란의 FX]",
           "[모닝 리포트] 달러/원 환율, 유가·금리 상승에 1340원 회복 시도",
           "달러·원 3.9원 하락, 1333.6원 마감…외인 양시장 동반 순매수 (종합)'"],
    "semi": ["10월 수출물가지수 반도체 가격 상승에 0.7% 올라, 수입물가는 1.8% 하락",
             "젠슨 황 사태에 美의회 대중 반도체 수출통제 강화 입법 탄력",
             "반도체·AI 인프라 수출 호황…수출물량 증가율 43.9% '역대 최대'"],
    "battery": ["GM, 4세대 전기차에 LMR 각형 배터리 탑재",
                "삼성·현대차, 배터리 공급 넘어 설계까지 맞손…전고체 개발도",
                "LG엔솔 버테크, ESS 운영 SW 고도화…배터리 수명·수익성 관리"],
    "auto": ["영국, 26년 만에 신차 유통 규제 폐지…현대차·기아 대응 모색",
             "현대차·기아 전기차 10월 판매 2배↑…EV5 모델이 성장 견인",
             "기아 PV5, 국내 판매 목표 2달 앞당겨 달성…\"PBV 사업 순항\""],
    "ship": ["대한조선, 2498억 규모 원유 운반선 2척 수주",
             "한화에어로, 육군본부 과장단 초청 행사…K-방산 '원팀' 강조",
             "기품원, 폴란드와 NATO 품질보증 협력 강화 \"K-방산, 유럽 수출 장벽 넘는다\""],
    "bio": ["대웅제약, ‘장 점막 재생’ 장질환 치료제 임상 1상 진입",
            "셀트리온 “건선 치료 바이오시밀러, 호주 품목허가 신청”",
            "일동제약, 바이오 유럽서 비만·위식도역류질환 신약 기술수출 논의"],
    "platform": ["네이버, ‘실행’하는 AI 에이전트로 승부수…AI 팩토리 수익화 속도",
                 "네이버, 3Q 영업익 4513억원…투자 늘려 전년比 20.9%↓",
                 "하나證 \"네이버, 본업 부진에 목표가 34만원 ↓…신사업·두나무 심의 주목\""],
    "policy": ["[증시 현안] \"밸류업 박차\" 금융위, 한국거래소에서 자본시장 현안 간담회 연다",
               "[단독]정부, 13일 거래소서 자본시장 간담회...코스닥 대책 주목",
               "'선제적 조치' 개미 호소에도… 공매도 금지·증안펀드 가동 쉽잖은 이유"],
}
SAME = {("rates", 0, 1), ("policy", 0, 1)}
for k, ts in LIVE.items():
    for i in range(3):
        for j in range(i + 1, 3):
            want = (k, i, j) in SAME
            got_same = news.same_story(sig(ts[i]), sig(ts[j]))
            check(f"실화면 {k} {i + 1}·{j + 1} {'같음' if want else '다름'}", got_same == want,
                  f"{ts[i][:18]} / {ts[j][:18]}")

# ── 2. 순위 — 바이오 칸 (같은 기술수출 6건 + 다른 사건) ─────────────────────
bio = [row(f"일동제약, 바이오 유럽서 파도프라잔 기술수출 논의{s}", src, h)
       for s, src, h in [("", "뉴스핌", 3), ("…상업화 속도", "한국의약통신", 4),
                         (" 추진", "폴리뉴스", 5), ("했다", "비즈월드", 6),
                         ("·비만약", "파이낸셜뉴스", 7), (" 모색", "www.ebn.co.kr", 8)]]
bio += [row("셀트리온, 비세큐마 호주 품목허가 신청", "Chosunbiz", 10),
        row("셀트리온 “건선 치료 바이오시밀러, 호주 품목허가 신청”", "연합뉴스", 11),
        row("HLB제약, 항응고 주사제 개발 중단", "FETV", 1),
        row("국고채 금리 급등…채권시장 긴장", "톱스타뉴스", 0.5)]
got = news.rank_stories(bio, 3, must=config.SECTOR_NEWS_MUST["bio"], tier=TIER, now=NOW)
titles = [h.title for h in got]
check("바이오: 같은 기술수출은 한 줄", sum("일동제약" in t for t in titles) == 1, str(titles))
check("바이오: 6곳 보도가 1위", "일동제약" in titles[0], str(titles))
check("바이오: 관련 N곳 = 다른 매체 수", got[0].more == 5, f"more={got[0].more}")
check("바이오: 대표는 주요 매체", got[0].source in ("뉴스핌", "파이낸셜뉴스"), got[0].source)
check("바이오: 섹터 낱말 없는 국고채 기사는 3위 밖", not any("국고채" in t for t in titles),
      str(titles))
check("원래 객체는 그대로 (more=0)", all(h.more == 0 for _w, h in bio))

# ── 2-b. 숫자는 '거의 같은 제목'만 (11/13 두 번째 배포 '관련 27곳') ──────────
rates = [row("금통위원 과반 \"추가 금리인상 필요\"…AI 증시 충격 '경계'", "뉴스1", 2),
         row("금통위원 과반 \"추가 금리인상 필요\"…AI 증시 충격 경계", "뉴시스", 3),
         row("금통위원들 \"연속 금리 인상 효과 점검해야\"…과반이 추가 긴축에 공감", "아시아경제", 4),
         row("한은 금리 인상 추가로 하나…금통위원 의견 갈려", "데일리팝", 5),
         row("금리 인상 추가 압력…한은 고민", "톱스타뉴스", 6)]
got = news.rank_stories(rates, 3, must=config.SECTOR_NEWS_MUST["rates"], tier=TIER, now=NOW)
check("느슨하게 묶여도 첫 줄은 하나", sum("금통위원" in h.title for h in got) == 1,
      str([h.title for h in got]))
check("관련 N곳은 거의 같은 제목만 (1)", got[0].more <= 1, f"more={got[0].more} {got[0].title}")

auto = [row("코스맥스, 생산능력 확대 속 실적 성장 가속화…목표가 39만원-현대차", "머니투데이", 1),
        row("현대차 中 전략모델 '아이오닉 V', 첫 달 842대 판매", "뉴시스", 5)]
got = news.rank_stories(auto, 1, must=config.SECTOR_NEWS_MUST["auto"],
                        avoid=config.SECTOR_NEWS_AVOID["auto"], tier=TIER, now=NOW)
check("자동차: 현대차증권 리포트 기사는 뒤로", "아이오닉" in got[0].title, got[0].title)

# ── 3. 감점이지 버림이 아님 ─────────────────────────────────────────────────
only_off = [row("국고채 금리 급등…채권시장 긴장", "톱스타뉴스")]
check("섹터 낱말 기사가 없으면 그래도 나옴",
      len(news.rank_stories(only_off, 3, must=("제약",), now=NOW)) == 1)

# ── 4. 정책 칸 — 해외 증시 정책은 뒤로 ─────────────────────────────────────
pol = [row(f"대만, AI株 급락에 공매도 규제 강화{s}", src, 2)
       for s, src in [("", "서울경제"), ("…증시 반등", "뉴스1"), (" 검토", "뉴스웰")]]
pol += [row("[단독]정부, 13일 거래소서 자본시장 간담회...코스닥 대책 주목", "비즈워치", 20)]
got = news.rank_stories(pol, 3, must=config.SECTOR_NEWS_MUST["policy"],
                        avoid=config.SECTOR_NEWS_AVOID["policy"], tier=TIER, now=NOW)
check("정책: 국내 정책이 1위", "자본시장" in got[0].title, str([h.title for h in got]))

# ── 5. 나이 — 오래된 큰 사건보다 어제 사건 ─────────────────────────────────
old_big = [row(f"반도체 업황 회복 신호{n}", f"매체{n}", 24 * 6.5) for n in range(3)]
fresh = [row("SK하이닉스 HBM4 공급 계약", "연합뉴스", 2)]
got = news.rank_stories(old_big + fresh, 1, must=config.SECTOR_NEWS_MUST["semi"], tier=TIER, now=NOW)
check("나이: 6일 넘은 3곳 보도보다 오늘 주요 매체", "HBM4" in got[0].title, got[0].title)

# ── 6. 파싱 — 제목 꼬리 ' - 매체' 제거 ─────────────────────────────────────
body = ("<item><title>환율 1330.7원 마감 - 뉴스1</title><link>https://x/a</link>"
        "<pubDate>Thu, 12 Nov 2026 07:00:00 GMT</pubDate>"
        '<source url="https://m">뉴스1</source></item>')
h = news.parse_google_rss(body, 3, 7, now=NOW)[0]
check("제목 꼬리 ' - 매체' 제거", h.title == "환율 1330.7원 마감", h.title)
check("꼬리가 두 번이어도 제거",
      news._strip_source("수출 호황 - 머니투데이 - 머니투데이", "머니투데이") == "수출 호황")

# ── 7. 화면 ────────────────────────────────────────────────────────────────
import components as ui  # noqa: E402

hs = [Headline("제목", "https://x", "뉴스1", "2026-11-12", more=5)]
html = ui.render_sector_news([("fx", "환율", "원달러 환율 (마감 OR 전망)")], {"fx": hs}, {})
check("화면: 관련 N곳", "관련 5곳" in html, html)
check("화면: 검색어에 OR 기호 없음", " OR " not in html, html)
check("화면: 검색어 풀이", "마감·전망" in html, html)
html0 = ui.render_sector_news([("fx", "환율", "q")], {"fx": [Headline("t", "", "s", "2026-11-12")]}, {})
check("화면: more=0 이면 '관련' 안 씀", "관련" not in html0)
html_err = ui.render_sector_news([("fx", "환율", "q")], {}, {"fx": "구글 뉴스 응답을 받지 못했습니다."})
check("화면: 실패해도 이유 표시", "받지 못했" in html_err)


class _Old:   # 옛 캐시 객체 (more 없음)
    title, url, source, published = "옛", "", "s", "2026-11-12"


check("화면: more 없는 옛 객체도 안 깨짐", "옛" in ui.render_sector_news(
    [("fx", "환율", "q")], {"fx": [_Old()]}, {}))

# ── 8. 설정 ────────────────────────────────────────────────────────────────
keys = [k for k, _l, _q in config.KR_SECTORS]
check("섹터 9개 · 섹터 낱말 모두 있음", len(keys) == 9 and all(k in config.SECTOR_NEWS_MUST for k in keys))
check("정책 칸 이름 '정책'", dict((k, l) for k, l, _q in config.KR_SECTORS)["policy"] == "정책")
app_src = open("app.py", encoding="utf-8").read()
check("섹터 뉴스는 rank=True", "rank=True" in app_src)
check("마감 기사는 그대로(최신순, 2일)", "fetch_sector_news(specs, limit=3, max_days=2)" in app_src)

# ── 9. 네트워크 실패 → 빈 결과와 구분 ──────────────────────────────────────
_orig = news._rss_body
news._rss_body = lambda q, d: None
out, err = news.fetch_sector_news([("fx", "환율", "q")], rank=True)
check("받지 못함 ≠ 기사 없음", not out and "받지 못" in err["fx"], str(err))
news._rss_body = lambda q, d: ""
out, err = news.fetch_sector_news([("fx", "환율", "q")], rank=True)
check("빈 응답은 '기사가 없습니다'", "기사가 없습니다" in err["fx"], str(err))
news._rss_body = _orig

print()
if FAILS:
    print(f"실패 {len(FAILS)}개: {FAILS}")
    sys.exit(1)
print("모두 통과")
