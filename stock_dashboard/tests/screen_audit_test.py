"""2026-11-12 실제 화면 전수 점검에서 나온 것들.

    python tests/screen_audit_test.py

23개 화면(한국 13 · 미국 10)을 휴대폰 폭 · 다크 모드로 돌며 찾은 문제와
그 수정을 고정합니다.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import buffett  # noqa: E402
import calendar_events as cal  # noqa: E402
import chart_signals  # noqa: E402
import components as ui  # noqa: E402
import config  # noqa: E402
import demo as demo_mod  # noqa: E402
import macro  # noqa: E402
import sector_heat  # noqa: E402
from sources import kr_exports as kx  # noqa: E402
from sources import naver  # noqa: E402
from sources.fred import Observation, Series  # noqa: E402

FAILURES: list[str] = []
src = pathlib.Path("app.py").read_text(encoding="utf-8")


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


print("\n=== 수출 통계 — 목록 첫 쪽에서 밀려난 글 ===")
# 실제 검색 결과(2026-11-12)의 줄 모양 그대로
SEARCH_HTML = """
<a href="/kor/article/ATCL064d77701">반부패·청렴 관련 자료 공개 안내 페이지</a>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172360/view?mno=&amp;pageIndex=1"
   onclick="article.view('172360'); return false;">2026년 10월 수출입 동향</a></td><td>2026-11-01</td></tr>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172308/view?mno=&amp;pageIndex=1">(참고자료)베트남 현지 진출기업
   최대 애로 ‘내국수출입 부가가치세 환급지연’ 해결</a></td></tr>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172289/view?mno=&amp;pageIndex=1">2026년 9월 정보통신산업(ICT) 수출입 동향</a></td></tr>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172254/view?mno=&amp;pageIndex=1">2026년 9월 수출입 동향</a></td></tr>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172145/view?mno=&amp;pageIndex=1">2026년 8월 수출입동향</a></td></tr>
<tr><td><a href="/kor/article/ATCL3f49a5a8c/172143/view?mno=&amp;pageIndex=1">「전략물자 수출입고시」 개정안 시행</a></td></tr>
"""
FIRST_PAGE_HTML = """
<a href="/kor/article/ATCL3f49a5a8c/172399/view?mno=&amp;pageIndex=1">K-온디바이스 AI반도체, ‘상생’으로 속도낸다</a>
<a href="/kor/article/ATCL3f49a5a8c/172398/view?mno=&amp;pageIndex=1">유럽연합 탄소국경조정제도(CBAM) 국내 첫 검증기관 인정</a>
"""
ARTICLE_HTML = ("<div>10 월 수출은 93.7% 증가한 1,153 억 달러 … 반도체 수출 (564.4 억 달러 , +259.4%) 은 "
                "메모리 수요 증가세가 지속되며 …</div>")
links = kx.find_article_links(SEARCH_HTML)
check("월간 수출입 동향만 고른다 (ICT · 고시 · 참고자료 제외)",
      [t for t, _h in links] == ["2026년 10월 수출입 동향", "2026년 9월 수출입 동향",
                                  "2026년 8월 수출입동향"], str([t for t, _h in links]))
check("주소의 &amp; 를 풀어 준다", links[0][1].endswith("/172360/view?mno=&pageIndex=1"), links[0][1])
check("목록 첫 쪽에는 그 글이 없다 (원인)", kx.find_article_links(FIRST_PAGE_HTML) == [])


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, search_html):
        self.calls, self.search_html = [], search_html

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if "/view" in url:
            return _Resp(ARTICLE_HTML)
        return _Resp(self.search_html if params else FIRST_PAGE_HTML)


sess = _Session(SEARCH_HTML)
got = kx.fetch_latest(session=sess)
check("제목 검색으로 먼저 찾는다",
      sess.calls[0][1].get("searchKeyword") == "수출입" and sess.calls[0][1].get("searchCondition") == "1",
      str(sess.calls[0]))
check("가장 최근 글(10월)을 받는다", "/172360/view" in sess.calls[-1][0], sess.calls[-1][0])
check("본문에서 금액과 전년비를 읽는다 (실제 띄어쓰기)",
      abs((got.value_100m_usd or 0) - 564.4) < 0.01 and abs((got.yoy_pct or 0) - 259.4) < 0.01,
      f"{got.value_100m_usd} · {getattr(got, 'yoy_pct', None)}")
sess2 = _Session("<html>검색 결과가 없습니다</html>")
try:
    kx.fetch_latest(session=sess2)
    raised = ""
except kx.ExportsError as exc:
    raised = str(exc)
check("검색이 비면 목록 첫 쪽도 본 뒤에 실패를 말한다",
      len(sess2.calls) == 2 and sess2.calls[1][1] == {} and "찾지" in raised, raised)

print("\n=== 못 찾은 계정 이름 ===")
check("내부 이름을 한국어로", buffett.tag_label("long_term_investments") == "장기투자자산"
      and buffett.tag_label("gross_profit") == "매출총이익")
check("모르는 이름은 밑줄만 띄운다", buffett.tag_label("some_new_tag") == "some new tag")
check("재무 심사에 쓰는 계정은 전부 이름이 있다",
      not [k for k in set(buffett.FLOW_KEYS) | set(buffett.STOCK_KEYS) if k not in buffett.TAG_LABELS])
screens, _errs = demo_mod.demo_screens()
one = next(iter(screens.values()))
one.missing_tags = ["gross_profit", "long_term_investments"]
html = ui.render_screen(one)
check("화면에 영어 내부 이름이 안 나온다",
      "매출총이익, 장기투자자산" in html and "long_term_investments" not in html)

print("\n=== 한국 지표 — 값의 모양 ===")
TODAY = dt.date(2026, 11, 12)


def monthly(start_y, start_m, values):
    y, m, out = start_y, start_m, []
    for v in values:
        out.append(Observation(date=dt.date(y, m, 1), value=v))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return Series(series_id="X", observations=out)


exp = macro.kr_macro_row("한국 수출액", "usd",
                         monthly(2025, 8, [59_840_000_000.0] + [70e9] * 11 + [100_418_800_000.0]),
                         "", TODAY)
check("달러 원단위를 억 달러로", exp[1].startswith("1,004.2억 달러") and "100,418,800,000" not in exp[1], exp[1])
check("전년동월비를 같이", "(전년동월비 +67.8%)" in exp[1], exp[1])
check("몇 월분인지", exp[2] == "8월분", exp[2])
rate = macro.kr_macro_row("한국 3개월 시장금리", "rate",
                          monthly(2025, 9, [2.56] + [2.8] * 11 + [3.17]), "", TODAY)
check("금리는 % 로, 변화는 %p 로 (금리의 전년비 % 는 뜻이 없음)",
      rate[1] == "3.17%  (1년 전보다 +0.61%p)", rate[1])
idx = macro.kr_macro_row("한국 소비자물가 (지수)", "index",
                         monthly(2025, 9, [100.0] + [101.0] * 11 + [102.5]), "", TODAY)
check("지수는 전년동월비가 앞, 레벨은 메모로", idx[1] == "전년동월비 +2.5%" and "지수 102.5" in idx[2],
      f"{idx[1]} | {idx[2]}")
dead = macro.kr_macro_row("한국 OECD 경기선행지수", "index",
                          monthly(2023, 11, [99.1, 99.3, 99.6]), "", TODAY)
check("갱신이 멈춘 계열은 마지막 값과 함께 그렇게 적는다",
      dead[1] == "지수 99.6" and "2024년 1월분" in dead[2] and "멈춘" in dead[2] and "전년비 생략" in dead[2],
      f"{dead[1]} | {dead[2]}")
none = macro.kr_macro_row("없는 계열", "index", None, "", TODAY)
check("관측치가 하나도 없으면 이유를 적는다", none[1] == "—" and "중단" in none[2], none[2])
gap = monthly(2025, 9, [100.0] * 13)
gap.observations.pop(0)                       # 1년 전 같은 달이 빠진 경우
gap_row = macro.kr_macro_row("빠진 달", "index", gap, "", TODAY)
check("1년 전 같은 달이 없으면 13번째 앞 값과 비교하지 않는다", "전년동월비" not in gap_row[1], gap_row[1])
check("모든 한국 계열에 종류가 있다",
      all(sid in config.KR_MACRO_KIND for sid, _l in config.KR_MACRO_SERIES))
check("앱이 이 함수로 줄을 만든다", "macro_mod.kr_macro_row(" in src and "% YoY" not in src)

print("\n=== 마지막 봉이 오늘 것인가 ===")
XML = ('<item data="20261110|100|102|99|101|1000" />'
       '<item data="20261111|101|103|100|102|1200" />')
check("네이버 일봉의 마지막 날짜", naver.last_bar_date(XML) == "2026-11-11")
check("없으면 빈 문자열", naver.last_bar_date("") == "" and naver.last_bar_date("<x/>") == "")
ohlc = naver.parse_chart_ohlc(XML)
check("고·저·종과 함께 날짜를 든다", ohlc["last_date"] == "2026-11-11" and ohlc["close"] == [101.0, 102.0])
KST, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
open_kr = dt.datetime(2026, 11, 12, 11, 30, tzinfo=KST)
kind, text = cal.bar_note("2026-11-11", "kr", open_kr)
check("장중인데 어제 봉까지면 '미반영' 이라고 말한다 (섹터 온도 +0.8% vs 코스피 +3.7%)",
      kind == "behind" and "11/11 종가까지만" in text and "시세 띠" in text, text)
kind, text = cal.bar_note("2026-11-12", "kr", open_kr)
check("장중이고 오늘 봉이 있으면 '장중 잠정'", kind == "live" and "장중 잠정" in text, text)
kind, text = cal.bar_note("2026-11-12", "kr", dt.datetime(2026, 11, 12, 18, 0, tzinfo=KST))
check("장이 닫히면 종가 기준", kind == "closed" and text == "11/12 종가 기준입니다.", text)
check("날짜를 모르면 아무 말도 안 한다", cal.bar_note("", "kr", open_kr) == ("", "")
      and cal.bar_note("엉뚱", "kr", open_kr) == ("", ""))
kind, _t = cal.bar_note("2026-11-11", "us", dt.datetime(2026, 11, 11, 10, 0, tzinfo=NY))
check("미국은 뉴욕 날짜로 본다 (한국 시각으로는 이미 다음 날)", kind == "live")
check("시장의 오늘", cal.market_today("us", open_kr) == dt.date(2026, 11, 11)
      and cal.market_today("kr", open_kr) == dt.date(2026, 11, 12))

cands = [("A", "가"), ("B", "나"), ("C", "다")]
demo_ohlc, _e = demo_mod.demo_chart_ohlc(cands)
demo_ohlc["A"]["last_date"] = "2026-11-12"
demo_ohlc["B"]["last_date"] = "2026-11-12"
demo_ohlc["C"]["last_date"] = "2026-11-11"
rows = chart_signals.build_rows(cands, demo_ohlc, {})
check("차트 줄이 마지막 봉 날짜를 든다", [r.last_bar for r in rows] == ["2026-11-12", "2026-11-12", "2026-11-11"])
check("가장 흔한 날짜를 대표로", chart_signals.last_bar(rows) == "2026-11-12")
check("날짜가 없어도 줄은 만들어진다",
      chart_signals.build_rows(cands[:1], {"A": {k: v for k, v in demo_ohlc["A"].items() if k != "last_date"}}, {})[0].last_bar == "")
specs = config.KR_SECTOR_ETFS[:3]
closes = {s[0]: [100 + i for i in range(260)] for s in specs}
srows = sector_heat.build(specs, closes, {}, {}, {s[0]: "2026-11-12" for s in specs})
check("섹터 줄이 날짜를 든다", sector_heat.as_of(srows) == "2026-11-12")
check("날짜 없이 불러도 된다 (예전 호출)", sector_heat.as_of(sector_heat.build(specs, closes)) == "")
i_heat = src.index("def load_sector_heat(")
seg = src[i_heat: src.index("\n@swr.cached", i_heat)]
check("섹터 온도는 네이버 일봉을 먼저 받는다 (차트 조건과 같은 출처)",
      "naver.fetch_daily_many(codes, dates=dates)" in seg
      and seg.index("naver.fetch_daily_many") < seg.index("yahoo.fetch_closes"))
check("섹터 온도 · 차트 조건 화면이 '언제까지 반영됐나' 를 적는다",
      src.count("calendar_events.bar_note(") == 2)
check("차트의 '장중 잠정' 은 날짜를 확인한 뒤에만", 'if kind == "live":' in src)

print("\n=== 등락률 — 전일 종가를 날짜로 확인 ===")
from sources import yahoo  # noqa: E402

D = dt.date
# 2026-11-12 실제로 본 것: 가격은 5,430 근처로 같은데 등락률이 +3.69% ↔ +0.97%
full = [(D(2026, 11, 9), 5300.0), (D(2026, 11, 10), 5239.0), (D(2026, 11, 11), 5375.0),
        (D(2026, 11, 12), 5427.41)]
price, prev, ok = yahoo.pick_price_prev(full, "kr")
check("봉이 이어지면 어제 종가와 비교 (+0.97%)",
      ok and prev == 5375.0 and abs((price / prev - 1) * 100 - 0.975) < 0.01, f"{price} / {prev}")
holed = [r for r in full if r[0] != D(2026, 11, 11)]          # 야후가 어제 봉을 빠뜨림
price, prev, ok = yahoo.pick_price_prev(holed, "kr")
check("어제 봉이 빠지면 그제 종가를 전일 종가로 믿지 않는다 (+3.59% 가 될 뻔)",
      not ok and prev == 5239.0 and abs((price / prev - 1) * 100 - 3.6) < 0.05, f"{price} / {prev} · {ok}")
nan = float("nan")
price, prev, ok = yahoo.pick_price_prev(
    [(D(2026, 11, 10), 5239.0), (D(2026, 11, 11), nan), (D(2026, 11, 12), 5427.41)], "kr")
check("어제 종가가 비어(NaN) 와도 같다", not ok and price == 5427.41)
check("주말을 사이에 둔 금 → 월은 이어진 것",
      yahoo.bars_adjacent(D(2026, 11, 6), D(2026, 11, 9), "kr"))
hol = next(d for d in sorted(cal.NYSE_HOLIDAYS) if d.startswith("2026-11"))
hy, hm, hd = map(int, hol.split("-"))
before, after = D(hy, hm, hd) - dt.timedelta(days=1), D(hy, hm, hd) + dt.timedelta(days=1)
check(f"휴장일({hol})을 사이에 둔 봉도 이어진 것 — 그 시장에서만",
      yahoo.bars_adjacent(before, after, "us") and not yahoo.bars_adjacent(before, after, "kr"))
check("어느 시장인지 모르면 평일은 전부 거래일로", not yahoo.bars_adjacent(before, after, ""))
check("심볼로 시장을 가린다",
      yahoo._market_of("^KS11") == "kr" and yahoo._market_of("069500.KS") == "kr"
      and yahoo._market_of("^GSPC") == "us" and yahoo._market_of("NQ=F") == ""
      and yahoo._market_of("KRW=X") == "")
check("봉이 하나뿐이면 전일 종가 없음", yahoo.pick_price_prev([(D(2026, 11, 12), 100.0)], "kr") == (100.0, None, False))
check("빈 값", yahoo.pick_price_prev([], "kr") == (None, None, False))


class _Idx:
    def __init__(self, day):
        self._d = day

    def date(self):
        return self._d


class _Col(list):
    def tolist(self):
        return list(self)


class _Hist:
    empty = False

    def __init__(self, rows):
        self.index = [_Idx(d) for d, _c in rows]
        self._close = _Col(c for _d, c in rows)

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        return self._close


class _Ticker:
    def __init__(self, rows, fast=None):
        self._rows, self._fast = rows, fast

    def history(self, **_kw):
        return _Hist(self._rows)

    @property
    def fast_info(self):
        if self._fast is None:
            raise RuntimeError("fast_info 없음")
        return self._fast


check("이어지면 일봉의 전일 종가", yahoo._from_history(_Ticker(full), "^KS11") == (5427.41, 5375.0))
check("빠졌으면 야후가 따로 주는 전일 종가를 쓴다",
      yahoo._from_history(_Ticker(holed, {"previousClose": 5375.0}), "^KS11") == (5427.41, 5375.0))
check("그것도 없으면 비워 둔다 (틀린 등락률보다 '—')",
      yahoo._from_history(_Ticker(holed), "^KS11") == (5427.41, None))

print("\n=== 값의 모양이 바뀐 받기 — 옛 저장값을 쓰지 않는다 ===")
import swr  # noqa: E402

swr.DISK = False
old_fn = swr.cached(3_600, disk=False)(lambda: "옛 모양")
old_fn.name = "load_shape"
new_fn = swr.cached(3_600, disk=False, version=2)(lambda: "새 모양")
new_fn.name = "load_shape"
check("번호가 키에 들어간다", old_fn.key((), {}) != new_fn.key((), {}) and "#v2|" in new_fn.key((), {}))
old_fn()
check("옛 값이 남아 있어도 새로 받는다", new_fn() == "새 모양")
new_fn.clear()
check("비우기도 번호를 따른다", new_fn.age() is None and old_fn.age() is not None)
check("한국 지표 · 수출 통계에 번호를 올렸다",
      "@swr.cached(3_600, version=2)" in src and "@swr.cached(21_600, version=2)" in src)

print("\n=== 분석 실행 안내 ===")
check("화면 3분의 1 을 차지하던 노란 경고가 없다", "분석 실행 불가" not in src)
check("한 줄 안내 + 접어 둔 설치 방법",
      "이 서버에서는 분석을 새로 실행할 수 없습니다" in src and "PC 에서 직접 실행하려면" in src)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
