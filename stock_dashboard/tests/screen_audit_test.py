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
# 2026-11-12 FRED 에서 직접 확인한 실제 값으로
ip = macro.kr_macro_row("한국 산업생산 (전년동월비)", "pct",
                        monthly(2025, 8, [1.9] + [0.5] * 11 + [-0.851788756388283]), "", TODAY)
check("이미 전년비로 오는 계열은 그대로", ip[1] == "전년동월비 -0.9%" and "8월분" in ip[2] and "1년 전 +1.9%" in ip[2],
      f"{ip[1]} | {ip[2]}")
cli = macro.kr_macro_row("한국 OECD 경기선행지수", "level",
                         monthly(2025, 9, [100.9] + [101.5] * 11 + [102.5310190176960]), "", TODAY)
check("선행지수는 레벨 그대로 + 1년 전 대비", cli[1] == "102.5  (1년 전보다 +1.6)" and "100 이 장기 추세" in cli[2],
      f"{cli[1]} | {cli[2]}")
bsi = macro.kr_macro_row("한국 제조업 기업심리", "balance",
                         monthly(2025, 9, [-12.0] + [-9.0] * 11 + [-7.666666666666670]), "", TODAY)
check("기업심리는 부호를 붙여", bsi[1] == "-7.7  (1년 전보다 +4.3)" and "0 이 중립" in bsi[2], f"{bsi[1]} | {bsi[2]}")
y10 = macro.kr_macro_row("한국 10년 국채금리", "rate",
                         monthly(2025, 9, [2.9] + [3.5] * 11 + [4.454]), "", TODAY)
check("10년 국채금리", y10[1] == "4.45%  (1년 전보다 +1.55%p)", y10[1])
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
      "@swr.cached(3_600, version=3)" in src and "@swr.cached(21_600, version=2)" in src)

print("\n=== 국내 스크리너 — 하락장에서도 비지 않는 기준 ===")
import kr_screen as ks  # noqa: E402


def bars(start, moves):
    out, px = [], float(start)
    for m in moves:
        px *= 1 + m
        out.append(px)
    return out


VOL = [300_000.0] * 300
# 전 종목이 고점에서 20% 넘게 빠진 장 — ①②는 0종목이어야 정상
market = {}
for i in range(10):
    tail = -0.0040 + i * 0.0003                 # 종목마다 빠지는 속도가 다름 (전부 하락)
    market[f"S{i}"] = bars(50_000, [0.004] * 170 + [tail] * 130)
profs = [ks.profile(k, k, v, VOL) for k, v in market.items()]
check("하락장: 52주 고가 90% 이상이 하나도 없다 (①② 0종목은 버그가 아님)",
      ks.near_high_hits(profs) == [] and ks.contraction_hits(profs) == [])
rs = ks.relative_strength_hits(profs)
check("④ 그래도 덜 빠진 종목이 올라온다", len(rs) == 2 and {h.ticker for h in rs} == {"S9", "S8"},
      str([h.ticker for h in rs]))
check("④ 가장 덜 빠진 종목이 맨 위", rs[0].ticker == "S9")
check("④ 이유에 실제 수익률과 후보 중앙값을 적는다 ('강하다' ≠ '올랐다')",
      "3개월 수익률" in rs[0].reasons[0] and "후보 중앙값" in rs[0].reasons[0], rs[0].reasons[0])
check("④ 비교할 종목이 5개 미만이면 순위를 내지 않는다", ks.relative_strength_hits(profs[:4]) == [])
thin = [ks.profile(k, k, v, [100.0] * 300) for k, v in market.items()]
check("④ 거래대금 바닥 밑은 뺀다", ks.relative_strength_hits(thin) == [])

deep = bars(100_000, [0.002] * 150 + [-0.006] * 120 + [0.012] * 12)      # 급락 뒤 반등
falling = bars(100_000, [0.002] * 150 + [-0.006] * 132)                  # 계속 하락
flat_hi = bars(100_000, [0.001] * 282)                                   # 고점 근처
rb = ks.rebound_hits([ks.profile("D", "되돌림", deep, VOL), ks.profile("F", "하락중", falling, VOL),
                      ks.profile("H", "고점", flat_hi, VOL)])
check("⑤ 많이 빠졌다가 저점에서 올라온 종목만", [h.ticker for h in rb] == ["D"], str([h.ticker for h in rb]))
check("⑤ 이유에 낙폭 · 저점 대비 · 20일선", "빠진 상태" in rb[0].reasons[0] and "20일 저점" in rb[0].reasons[1]
      and "20일선 위" in rb[0].reasons[2])

quiet = bars(50_000, [0.0] * 300)
surge_vol = [300_000.0] * 295 + [1_500_000.0] * 5
sg = ks.turnover_surge_hits([ks.profile("V", "거래급증", quiet, surge_vol),
                             ks.profile("Q", "평소대로", quiet, VOL)])
check("⑥ 5일 거래대금이 60일 평균의 2배 이상", [h.ticker for h in sg] == ["V"]
      and sg[0].metrics[0][1].endswith("배"), str(sg[0].metrics[0] if sg else None))
check("⑥ 그 사이 주가 방향을 같이 적는다", "주가" in sg[0].reasons[1])
check("⑥ 거래량을 못 받았으면 올리지 않는다", ks.turnover_surge_hits([ks.profile("N", "n", quiet, None)]) == [])

for key in ks.VOL_SCREENS:
    steps = ks.funnel(key, len(profs), profs)
    check(f"단계표 [{key}] — 후보에서 시작해 줄어든다",
          steps[0].label == "후보" and steps[0].count == len(profs)
          and all(a.count >= b.count for a, b in zip(steps[2:], steps[3:])),
          str([(x.label, x.count) for x in steps]))
check("단계표 마지막 칸 = 통과 종목 수",
      ks.funnel("rs", len(profs), profs)[-1].count == len(rs))
keys = [k for k, *_ in ks.KR_SCREENS]
check("스크리너 6개 — 기존 셋은 그대로, 셋 추가",
      keys == ["contraction", "near_high", "value_trad", "rs", "rebound", "surge"])
check("앱이 여섯 개를 모두 계산한다",
      all(f'"{k}": kr_screen.' in src for k in ("rs", "rebound", "surge")))
check("0종목일 때 다른 스크리너를 안내한다", "④ 시장 대비 강한" in src)

print("\n=== 반도체 리포트 — 실제 응답 모양 (2026-11-12 진단 패널로 확인) ===")
import semi_research as sr  # noqa: E402
from sources import research as rs  # noqa: E402

IND_LIST = [
    {"researchCategory": "산업분석", "category": "반도체", "researchId": "46967",
     "title": "이미 많은 것이 반영된 주가", "brokerName": "유진투자증권",
     "writeDate": "2026-11-12", "readCount": "92",
     "endUrl": "https://m.stock.naver.com/research/industry/46967"},
    {"researchCategory": "산업분석", "category": "은행", "researchId": "46962",
     "title": "10 월 여수신 동향", "brokerName": "SK증권", "writeDate": "2026-11-12",
     "readCount": "5", "endUrl": "https://m.stock.naver.com/research/industry/46962"},
    {"researchCategory": "산업분석", "category": "기타", "researchId": "46960",
     "title": "[Daily] 인터넷/게임", "brokerName": "IBK투자증권", "writeDate": "2026-11-12",
     "readCount": "1", "endUrl": "https://m.stock.naver.com/research/industry/46960"},
]
ind = rs.reports_from_json(IND_LIST, "industry")
check("업종은 category 칸에서 (researchCategory 의 '산업분석' 이 아님)",
      [r.category for r in ind] == ["반도체", "은행", "기타"], str([r.category for r in ind]))
check("리서치 번호를 같이 든다", ind[0].research_id == "46967")
check("반도체만 고른다", [r.title for r in ind if sr.is_semi(r)] == ["이미 많은 것이 반영된 주가"])
check("업종 칸이 비면 제목으로 가린다",
      sr.is_semi(rs.Report(kind="industry", title="HBM 공급 점검"))
      and not sr.is_semi(rs.Report(kind="industry", title="조선 수주 동향")))
check("업종 칸이 있으면 제목의 낱말에 끌려가지 않는다",
      not sr.is_semi(rs.Report(kind="industry", title="삼성전자 납품 화장품", category="화장품")))

STOCK_LIST = [
    {"researchCategory": "종목분석", "category": "종목분석", "itemCode": "005930",
     "itemName": "삼성전자", "researchId": "97570", "title": "STRESS TEST",
     "brokerName": "iM증권", "writeDate": "2026-11-04", "readCount": "42678",
     "previewContent": "목표주가 37만원, ‘28년 기준으로는 56만원까지 열림투자의견 Buy, 목표주가 37만원으로 "
                       "커버리지를 개시한다. ‘27년 BPS에 목표 P/B 2.3배를 적용했다. 이는 과거 고점 배수를 "
                       "넘는 수준이나 HBM 과 DRAM 가격 강세가 이어지는 구간이라는 점을 반영했다. 그 뒤로 이어지는 "
                       "문단은 화면에 싣지 않는다. 재고는 낮다."},
    {"researchCategory": "종목분석", "category": "종목분석", "itemCode": "005930",
     "itemName": "삼성전자", "researchId": "97400", "title": "환율 부담에도 분기 영업이익 100조원 돌파",
     "brokerName": "B증권", "writeDate": "2026-10-30", "readCount": "100",
     "previewContent": "3Q26Review 메모리 업사이클 지속&nbsp;삼성전자의 3Q26 연결기준 매출액은 195.4조원"},
    {"title": "", "researchId": "1"}, "쓰레기",
]
DETAIL = {"researchContent": {
    "itemCode": "005930", "itemName": "삼성전자", "researchId": "97570", "title": "STRESS TEST",
    "brokerName": "iM증권", "writeDate": "2026-11-04", "readCount": "42689",
    "attachUrl": "https://stock.pstatic.net/stock-research/company/61/20261104_company_507672000.pdf",
    "content": "<p><strong>목표주가 37만원</strong></p><p><br>투자의견 Buy&nbsp;…</p>",
    "opinion": "Buy", "goalPrice": "370000", "prevGoalPrice": "219500",
    "priceAtWriteDate": "219500"}, "researchSummaries": []}
DETAIL2 = {"researchContent": {**DETAIL["researchContent"], "researchId": "97400", "opinion": "매수",
                               "goalPrice": "400000", "prevGoalPrice": "350000",
                               "priceAtWriteDate": "230000", "attachUrl": ""}}
urls = []


def fake_get(url):
    urls.append(url)
    if "/company/97570" in url:
        return DETAIL
    if "/company/97400" in url:
        return DETAIL2
    if "/stock/005930" in url and "page=1" in url:
        return STOCK_LIST
    return []


reps, err = rs.fetch_stock("005930", pages=2, get=fake_get)
check("종목 리포트 목록 (빈 줄·쓰레기는 건너뜀)", len(reps) == 2 and err == "" and reps[0].item_name == "삼성전자",
      f"{len(reps)} · {err}")
check("상세 페이지 주소를 만든다", reps[0].url == "https://m.stock.naver.com/research/company/97570")
check("다음 쪽이 비면 멈춘다", sum("/stock/005930" in u for u in urls) == 2)
check("미리보기는 앞부분만 (160자 안, 낱말 중간에서 안 자름)",
      len(reps[0].preview) <= rs.PREVIEW_CHARS + 1 and reps[0].preview.endswith("…")
      and "재고는 낮다" not in reps[0].preview, f"{len(reps[0].preview)}자")
check("&nbsp; 같은 찌꺼기를 지운다", "&nbsp;" not in reps[1].preview and "지속 삼성전자" in reps[1].preview,
      reps[1].preview)
filled = rs.enrich(reps, limit=5, get=fake_get)
check("상세에서 의견 · 목표주가 · PDF 를 채운다",
      filled == 2 and reps[0].opinion == "Buy" and reps[0].goal_price == 370000.0
      and reps[0].pdf.endswith(".pdf") and reps[1].pdf == "")
check("목록의 미리보기를 상세 본문으로 덮지 않는다", reps[0].preview.startswith("목표주가 37만원, ‘28년"))
check("커버리지 개시는 '상향' 이 아니다 (직전 목표가 칸 = 그날 주가)", sr.goal_change(reps[0]) == "")
check("직전보다 올렸으면 상향", sr.goal_change(reps[1]) == "상향")
ops = sr.opinion_summary(reps)
check("의견은 계열로 묶어 세고, 목표주가는 범위만 (평균 없음)",
      ops["opinions"] == [("매수 계열", 2)] and ops["low"] == 370000.0 and ops["high"] == 400000.0
      and ops["up"] == 1 and "mean" not in ops and "avg" not in ops, str(ops))
broken = rs.fetch_stock("000660", get=lambda u: (_ for _ in ()).throw(RuntimeError("막힘")))
check("못 받으면 빈 목록과 사유", broken[0] == [] and "실패" in broken[1])
check("상세가 실패해도 목록은 남는다",
      rs.enrich([rs.Report(kind="company", title="x", research_id="1")],
                get=lambda u: (_ for _ in ()).throw(RuntimeError("x"))) == 0)

words = sr.keyword_counts(reps)
check("자주 나온 말 — 낱말이 나온 리포트 수", dict(words).get("HBM") == 1 and dict(words).get("실적") == 1
      and dict(words).get("밸류에이션") == 1, str(words))
check("'ai' 는 낱말로만 센다 (main · rain 에 안 걸림)",
      sr.keyword_counts([rs.Report(kind="industry", title="Maintain rain gain")]) == []
      and dict(sr.keyword_counts([rs.Report(kind="industry", title="AI 서버 투자")])).get("AI · 데이터센터") == 1)
dg = sr.digest(reps, "삼성전자")
check("묶음 요약 첫 줄", dg[0] == "삼성전자 리포트 2건 · 증권사 2곳 · 10-30 ~ 11-04", dg[0])
check("리포트가 없으면 요약도 없다", sr.digest([], "x") == [])

cards = ui.render_report_cards(reps, show_stock=True)
check("카드: 제목은 원문 링크, PDF 는 따로",
      'href="https://m.stock.naver.com/research/company/97570"' in cards and cards.count("rp-pdf") == 1)
check("카드: 증권사가 낸 숫자라고 표시", cards.count("증권사 제시") == 2 and "목표주가 370,000원" in cards)
check("카드: 커버리지 개시는 '직전' 을 적지 않고, 바꾼 경우만 적는다",
      "직전 219,500원" not in cards and "목표주가 400,000원 (직전 350,000원)" in cards)
check("카드: 의견을 끄면 숫자가 안 나온다",
      "목표주가 370,000원" not in ui.render_report_cards(reps, show_opinion=False))
evil = rs.Report(kind="company", title="<script>alert(1)</script>", broker="x", date="2026-11-01",
                 url="javascript:alert(1)", preview="<img src=x onerror=1>")
safe_cards = ui.render_report_cards([evil])
check("카드: 제목·미리보기의 태그를 그대로 찍지 않고, 이상한 주소는 링크로 만들지 않는다",
      "<script>" not in safe_cards and "<img" not in safe_cards and "javascript:" not in safe_cards)
demo = demo_mod.demo_semi_research()
check("데모 — 세 묶음 모두 값이 있다",
      len(demo["industry"]) >= 5 and all(len(demo["stocks"][c]) >= 5 for c, _n in sr.STOCKS))
check("탭이 한국 쪽에만 있다", "semi_research" in config.market_tab_keys("kr")
      and "semi_research" not in config.market_tab_keys("us"))
check("탭 이름 · 디스패치 · 미리 받기 · 받은 시각 이름표",
      dict(config.tab_labels()).get("semi_research") == "반도체 리포트"
      and 'active == "semi_research"' in src and 'jobs["반도체 리포트"]' in src
      and '"load_semi_research": "반도체 리포트"' in src)
check("화면이 전문을 싣지 않는다고 적는다", "전문은 증권사의 저작물이라 싣지 않고" in src)
check("목표주가의 평균을 내지 않는다고 적는다", "평균을 내어 하나의 숫자로 만들지 않습니다" in src)

print("\n=== 새로 받기가 실패해도 좋은 값을 덮지 않는다 (2026-11-12 시장 공시) ===")
import time as _time  # noqa: E402

mode = {"v": "good", "n": 0}


def _filings():
    mode["n"] += 1
    if mode["v"] == "good":
        return ([{"corp": "삼성전자"}, {"corp": "SK하이닉스"}], "")
    return ([], "DartError: DART 요청 실패 (list.json): 연결 시간 초과")


filings_fn = swr.cached(0.05, stale=30, disk=False)(_filings)
check("처음에는 받은 값", filings_fn()[1] == "")
got_at = filings_fn.age()
mode["v"] = "timeout"
_time.sleep(0.08)
filings_fn()                                   # 묵은 값을 주고 뒤에서 새로 받음 → 실패
_dl = _time.time() + 2
while swr.busy() and _time.time() < _dl:
    _time.sleep(0.01)
val = filings_fn()
check("뒤에서 받기가 실패해도 직전 값이 남는다", val[1] == "" and len(val[0]) == 2, str(val))
check("받은 시각은 바뀌지 않는다 (실패한 시도를 '받았다' 고 적지 않음)",
      filings_fn.age() >= 0.08, f"{filings_fn.age():.2f}초")
entry = swr._store[filings_fn.key((), {})]
check("왜 유지했는지 적어 둔다", "직전 값을 유지" in entry.error and "연결 시간 초과" in entry.error, entry.error)
n_before = mode["n"]
filings_fn(), filings_fn()
_time.sleep(0.05)
check("실패한 뒤에는 쉬었다가 다시 받는다 (부를 때마다 두드리지 않음)", mode["n"] == n_before, f"{mode['n']} vs {n_before}")

first_fail = swr.cached(600, stale=3_600, disk=False)(lambda: ([], "요청 실패"))
first_fail.name = "t_first_fail"
first_fail()
e2 = swr._store[first_fail.key((), {})]
check("처음부터 실패한 값은 받아 두되 금방 다시 받는다 (ttl 10분 → 2분 30초)",
      e2.failed and first_fail._ttl_of(e2) == 150.0, f"{e2.failed} · {first_fail._ttl_of(e2)}")
ok_val = swr.cached(600, disk=False)(lambda: {"a": [1, 2]})
ok_val.name = "t_ok_val"
ok_val()
check("멀쩡한 값은 원래 ttl", not swr._store[ok_val.key((), {})].failed)
plain = swr.cached(600, disk=False)(lambda: "글자 하나")
plain.name = "t_plain"
plain()
check("글자·숫자 하나짜리 값은 실패로 보지 않는다", not swr._store[plain.key((), {})].failed)

mode2 = {"v": "good"}
old_keep = swr.KEEP_GOOD_MAX
aged = swr.cached(0.05, stale=30, disk=False)(lambda: ({"a": [1]}, "") if mode2["v"] == "good" else ({}, "실패"))
aged.name = "t_aged"
aged()
mode2["v"] = "bad"
swr.KEEP_GOOD_MAX = 0.01                       # 직전 값이 너무 오래된 경우
_time.sleep(0.08)
aged()
_dl = _time.time() + 2
while swr.busy() and _time.time() < _dl:
    _time.sleep(0.01)
check("직전 값이 너무 오래됐으면 그만 붙들고 실패를 보여준다", aged()[1] == "실패", str(aged()))
swr.KEEP_GOOD_MAX = old_keep

import health as _health  # noqa: E402

check("'errors' 묶음은 값으로 세지 않는다 (전부 실패한 반도체 리포트)",
      _health.looks_failed({"industry": [], "stocks": {"005930": [], "000660": []},
                            "errors": {"산업분석": "요청 실패"}, "scanned": 0}))
check("일부만 실패했으면 쓸 만한 값",
      not _health.looks_failed(demo_mod.demo_semi_research() | {"errors": {"SK하이닉스": "요청 실패"}}))
sys.path.insert(0, "tools")
check("수집기와 저장소가 같은 규칙을 쓴다",
      __import__("collect").looks_failed is _health.looks_failed)

print("\n=== 일목 양운·음운 — 앞 구름으로 판정 (2026-11-12 사용자 정정) ===")
cs = chart_signals


def _ohlc(closes):
    return [c * 1.01 for c in closes], [c * 0.99 for c in closes], closes


# 오래 내리다가 최근 20봉 급반등 — 오늘 자리 구름(25봉 전 계산)은 아직 음운, 앞 구름은 양운
down_up = [100_000 * (0.997 ** i) for i in range(200)]
down_up += [down_up[-1] * (1.012 ** i) for i in range(1, 21)]
hh, ll, cc_ = _ohlc(down_up)
ic = cs.ichimoku(hh, ll)
mid = lambda n: (max(hh[-n:]) + min(ll[-n:])) / 2          # noqa: E731
check("앞 구름의 선행스팬1 = (전환선 + 기준선) ÷ 2 — 오늘 봉으로 계산",
      abs(ic.lead_a - (mid(9) + mid(26)) / 2) < 1e-6, f"{ic.lead_a}")
check("앞 구름의 선행스팬2 = 52봉 고저 중간 — 오늘 봉으로 계산", abs(ic.lead_b - mid(52)) < 1e-6)
check("오늘 자리 구름은 25봉 전에 계산된 값 (그대로)",
      abs(ic.span_b - (max(hh[-77:-25]) + min(ll[-77:-25])) / 2) < 1e-6)
check("급반등: 오늘 자리는 음운인데 앞 구름은 양운 → 양운으로 판정",
      ic.here_bullish is False and ic.bullish_cloud is True, f"{ic.here_bullish} / {ic.bullish_cloud}")
check("그 사이에 구름이 바뀌었다고 적는다", ic.twist == "음운 → 양운 전환", ic.twist)
up_down = [50_000 * (1.003 ** i) for i in range(200)]
up_down += [up_down[-1] * (0.988 ** i) for i in range(1, 21)]
h2, l2, _c2 = _ohlc(up_down)
ic2 = cs.ichimoku(h2, l2)
check("급락: 오늘 자리는 양운인데 앞 구름은 음운 → 음운으로 판정",
      ic2.here_bullish is True and ic2.bullish_cloud is False and ic2.twist == "양운 → 음운 전환")
row = cs.build_row("T", "반등주", hh, ll, cc_, [1_000.0] * len(cc_))
check("조건표의 '일목 양운' 이 앞 구름을 따른다", row.flags()["cloud"] is True)
check("가격 위치(구름 위·안·아래)는 오늘 자리 구름 기준 그대로",
      row.cloud_position == ic.position(cc_[-1]) and row.cloud_position in ("구름 위", "구름 안", "구름 아래"))
check("차트의 구름은 오늘을 지나 앞 25봉까지",
      len(row.spark_a) == len(row.spark) + cs.DISPLACEMENT
      and abs(row.spark_a[-1] - ic.lead_a) < 1e-6 and abs(row.spark_b[-1] - ic.lead_b) < 1e-6
      and abs(row.spark_a[len(row.spark) - 1] - ic.span_a) < 1e-6)
chart_html = ui.render_cloud_chart(row)
check("차트에 '오늘' 세로선이 있고 그 오른쪽에 구름이 이어진다",
      "cl-today" in chart_html and "cl-bull" in chart_html and "cl-bear" in chart_html)
det = ui.render_chart_detail(row, cs.CONDITIONS)
check("상세에 앞 구름 값과 전환을 적는다", "앞 구름 선행스팬1" in det and "음운 → 양운 전환" in det
      and "오늘 자리" in det)
check("조건 설명이 '앞 구름' 이다", "앞 구름" in dict((k, r) for k, _n, r in cs.CONDITIONS)["cloud"])
short = cs.ichimoku(hh[:40], ll[:40])
check("봉이 모자라면 판정하지 않는다 (52봉 미만)", short.bullish_cloud is None)

print("\n=== 분석 실행 안내 ===")
check("화면 3분의 1 을 차지하던 노란 경고가 없다", "분석 실행 불가" not in src)
check("한 줄 안내 + 접어 둔 설치 방법",
      "이 서버에서는 분석을 새로 실행할 수 없습니다" in src and "PC 에서 직접 실행하려면" in src)

print("\n=== 기준 정의 · 촘촘한 배치 (2026-11-12 요청) ===")
import buffett_kr  # noqa: E402
import kr_screen  # noqa: E402
import theme  # noqa: E402

us_rules = buffett.criteria_rules(config.screen_thresholds())
check("기준마다 통과 조건이 있음", len(us_rules) == len(buffett.CRITERIA)
      and all(r["rule"] and r["short"] and r["label"] for r in us_rules))
th = config.screen_thresholds()
by = {r["key"]: r["rule"] for r in us_rules}
check("통과선이 판정에 쓰는 값과 같음 (ROE · 부채 · ROIC)",
      f"{th.roe_min:g}%" in by["roe"] and f"{th.roe_years_required}해" in by["roe"]
      and f"{th.debt_to_equity_max:g}" in by["low_debt"] and f"{th.debt_years_max:g}년" in by["low_debt"]
      and f"{th.roic_min:g}%" in by["roic"] and f"{th.fcf_conversion_min:g}%" in by["fcf_conversion"])
kr_by = {r["key"]: r["rule"] for r in buffett.criteria_rules(buffett_kr.kr_thresholds())}
check("한국은 한국 기준선으로 적힘", "10%" in kr_by["roe"] and "15%" not in kr_by["roe"]
      and "0.6" in kr_by["low_debt"])
moved = buffett.Thresholds(roe_min=20.0, roe_years_required=9)
check("기준선을 바꾸면 표도 바뀜", "20%" in buffett.criteria_rules(moved)[0]["rule"]
      and "9해" in buffett.criteria_rules(moved)[0]["rule"])
check("모든 판정 함수에 기준 설명이 있음",
      {c.key for c in buffett.CRITERIA} == set(by) == set(buffett.SHORT_NAMES))
check("출처 개수의 합이 기준 수", sum(buffett.provenance_counts().values()) == len(buffett.CRITERIA))
html = ui.render_criteria_table(us_rules, title="버핏식 품질 기준", intro=buffett.DEFINITION, foot="끝")
check("기준표 — 이름 · 조건 · 출처 칩", html.count("<tr>") == len(us_rules) + 1
      and "cr-src" in html and "ROE(순이익 ÷ 자본) ≥ 15%" in html and "<b>또는</b>" in html)
check("기준표가 비면 아무것도 그리지 않음", ui.render_criteria_table([]) == "")
evil = ui.render_criteria_table([{"short": "<script>x</script>", "rule": "a"}])
check("이름은 HTML 로 해석하지 않음", "<script>" not in evil)
check("정의 문장 — 가격은 보지 않는다고 적음", "가격은 보지 않습니다" in buffett.DEFINITION)
check("발굴(미국) — 정의 · 기준표 · 한눈표",
      "_criteria_block(config.screen_thresholds(), market=\"us\"" in src
      and "ui.render_screen_table(top, buffett.CRITERIA, held=held" in src)
check("밸류에이션 — '사업의 질' 기준표를 펼쳐 볼 수 있음",
      "'사업의 질' 은 무엇으로 재나" in src and "buffett_kr.kr_thresholds() if kr_only" in src)
check("발굴(한국) — 여섯 스크리너 기준표와 말뜻",
      "여섯 스크리너의 기준 — 숫자와 말뜻" in src and "kr_screen.KR_TERMS" in src
      and len(kr_screen.KR_TERMS) >= 4)
terms = ui.render_terms(kr_screen.KR_TERMS)
check("말뜻 — 변동성 · 거래대금 창이 숫자로",
      f"{kr_screen.SHORT_WINDOW}거래일" in terms and f"{kr_screen.LONG_WINDOW}거래일" in terms
      and f"{kr_screen.TURNOVER_WINDOW}거래일" in terms)
tbl = ui.render_screen_table([], buffett.CRITERIA)
check("한눈표 머리는 짧은 이름", tbl == "" and all(len(v) <= 6 for v in buffett.SHORT_NAMES.values()))

css = theme.build_css("kr")
check("촘촘한 배치가 기본", config.DENSITY == "compact"
      and 'div[data-testid="stVerticalBlock"] { gap: 0.5rem; }' in css)
check("글자 크기는 건드리지 않음", "--fs-" not in theme.build_density_rules())
check("stMain 을 꼬리표 이름으로 집지 않음 (실제 앱에서는 <main>)",
      'section[data-testid="stMain"]' not in theme.build_density_rules()
      and '[data-testid="stMain"] div[data-testid="stVerticalBlock"]' in theme.build_density_rules())
check("위 여백을 머리띠 높이만큼만", "padding-top: 3.9rem !important" in theme.build_density_rules())
check("<style> 만 든 칸은 간격을 먹지 않게", "> style:only-child" in theme.build_density_rules())
check("기준표 스타일", ".dash-criteria" in css and ".dash-terms" in css)
check("좁은 화면에서는 기준 이름과 조건을 위아래로",
      ".dash-criteria .cr-table td { display: block;" in css
      and css.index(".dash-criteria table.cr-table thead { display: none; }")
      > css.index(".dash-criteria .cr-name { white-space: nowrap;"))
old_density = config.DENSITY
config.DENSITY = "roomy"
roomy = theme.build_css("kr")
config.DENSITY = old_density
check("roomy 로 두면 간격 묶음이 빠짐", len(roomy) < len(css) and "gap: 0.5rem" not in roomy
      and ".dash-criteria" in roomy)
check("중괄호 짝이 맞음", css.count("{") == css.count("}"))
check("요약 범위 20건 · 상세도 20건", config.SUMMARY_PER_LIST == 20 and config.SEMI_DETAIL_LIMIT >= 20)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
