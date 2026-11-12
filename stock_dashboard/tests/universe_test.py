"""종목 발굴 후보를 규칙으로 — 목록 해석 · 전수 심사 파일 · 수집기 단계 · 화면.

    python tests/universe_test.py

통신은 하지 않습니다. 표·응답 모양은 2026-11-12 실제 응답(설정 → 진단 →
'발굴 후보 출처 확인')에서 가져왔습니다.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
sys.path.insert(0, "tools")

import buffett  # noqa: E402
import components as ui  # noqa: E402
import config  # noqa: E402
import demo as demo_mod  # noqa: E402
import kr_screen  # noqa: E402
import universe  # noqa: E402
from sources import universe_src  # noqa: E402

FAILURES: list[str] = []
app_src = pathlib.Path("app.py").read_text(encoding="utf-8")


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


print("\n=== S&P 500 · 나스닥100 표 (위키백과) ===")
# 실제 응답의 줄 모양 그대로 (속성이 많이 붙어 옵니다)
SP = ('<table class="wikitable sortable" id="constituents"><tbody><tr>'
      '<th id="mwJA"><a rel="mw:WikiLink" href="x" title="Ticker symbol">Symbol</a></th> '
      '<th id="mwJg">Security</th><th id="mwJw"><a href="x">GICS</a> Sector</th>'
      '<th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date added</th>'
      '<th><a href="x">CIK</a></th><th>Founded</th></tr>'
      '<tr><td id="mwMA"><a rel="mw:ExtLink nofollow" href="https://www.nyse.com/quote/XNYS:MMM" '
      'data-mw=\'{"parts":[{"template":{"target":{"wt":"NyseSymbol"},"params":{"1":{"wt":"MMM"}}}}]}\'>'
      'MMM</a></td> <td><a href="x" title="3M">3M</a></td> <td>Industrials</td> '
      '<td>Industrial Conglomerates</td> <td><a href="x">Saint Paul, Minnesota</a></td> '
      '<td>1957-03-04</td> <td>0000066740</td> <td>1902</td></tr>'
      '<tr><td><a href="x">BRK.B</a></td><td><a>Berkshire Hathaway</a></td><td>Financials</td>'
      '<td>Multi-Sector Holdings</td><td>Omaha, Nebraska</td><td>2010-02-16</td>'
      '<td>0001067983</td><td>1839</td></tr>'
      '<tr><td><a href="x">MMM</a></td><td>중복</td><td>x</td><td>x</td><td>x</td><td>x</td>'
      '<td>1</td><td>x</td></tr>'
      '</tbody></table><table id="changes"><tr><td>ZZZ</td></tr></table>')
rows = universe.parse_index_table(SP)
check("티커 · 이름 · 업종 · CIK", rows[0] == {"ticker": "MMM", "name": "3M",
                                         "sector": "Industrials", "cik": 66740}, str(rows[:1]))
check("점이 든 티커 · 같은 티커는 한 번 · 다른 표는 안 읽음",
      [r["ticker"] for r in rows] == ["MMM", "BRK.B"] and rows[1]["cik"] == 1067983)
NDX = ('<table class="wikitable sortable" id="constituents"><tr><th>Ticker</th><th>Company</th>'
       '<th>ICB Industry</th><th>ICB Subsector</th></tr>'
       '<tr><td>ADBE</td><td><a>Adobe Inc.</a></td><td>Technology</td><td>Software</td></tr>'
       '<tr><td>ASML</td><td><a>ASML Holding</a></td><td>Technology</td><td>Semis</td></tr></table>')
nd = universe.parse_index_table(NDX)
check("칸 순서가 달라도 머리글로 찾는다 (CIK 칸이 없으면 None)",
      [r["ticker"] for r in nd] == ["ADBE", "ASML"] and nd[0]["cik"] is None
      and nd[0]["name"] == "Adobe Inc." and nd[0]["sector"] == "Technology")
NOID = ('<table class="wikitable"><tr><th>Year</th><th>Change</th></tr><tr><td>2025</td><td>x</td></tr></table>'
        '<table class="wikitable sortable"><tr><th>Company</th><th>Ticker</th><th>GICS Sector</th></tr>'
        + "".join(f"<tr><td><a>회사{i}</a></td><td>N{i}</td><td>Tech</td></tr>" for i in range(60))
        + '</table><table><tr><th>Ticker</th></tr><tr><td>ZZ</td></tr></table>')
no = universe.parse_index_table(NOID)
check("id 가 없어도 티커 칸이 있는 가장 큰 표를 읽는다 (칸 순서도 달라도)",
      len(no) == 60 and no[0] == {"ticker": "N0", "name": "회사0", "sector": "Tech", "cik": None},
      str(no[:1]))
check("표가 없으면 빈 목록", universe.parse_index_table("<html>없음</html>") == []
      and universe.parse_index_table("") == [])
check("업종 우리말 이름", universe.sector_label("Consumer Staples") == "필수소비재"
      and universe.sector_label("") == "분류 없음" and universe.sector_label("X") == "X")


class Resp:
    def __init__(self, text="", payload=None, status=200):
        self.text, self._p, self.status_code = text, payload, status
        self.content = (text or json.dumps(payload or "")).encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._p


def big_table(n, prefix="T"):
    body = "".join(f"<tr><td>{prefix}{i}</td><td>회사{i}</td><td>Industrials</td><td>x</td>"
                   f"<td>x</td><td>x</td><td>{1000 + i}</td><td>x</td></tr>" for i in range(n))
    return ('<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>'
            "<th>GICS Sub-Industry</th><th>HQ</th><th>Date added</th><th>CIK</th><th>Founded</th></tr>"
            + body + "</table>")


def us_get(ndx_ok=True, sp_n=500):
    def get(url, headers=None, timeout=None):
        if "S%26P_500" in url:
            return Resp(big_table(sp_n))
        if not ndx_ok:
            return Resp("", status=500)
        if url.endswith("/Nasdaq-100"):
            # 지수 문서에는 구성 종목 표가 없다 (2026-11-12 실제) — 연도별 표뿐
            return Resp('<table class="wikitable"><tr><th>Year</th><th>Closing level</th></tr>'
                        "<tr><td>2025</td><td>1</td></tr></table>")
        # 목록 문서 — 실제 칸 순서: Ticker · Company · ISIN · ICB Industry · ICB Subsector
        return Resp('<table class="wikitable sortable"><tr><th>Ticker</th><th>Company</th>'
                    "<th>ISIN</th><th>ICB Industry</th><th>ICB Subsector</th></tr>"
                    + "".join(f"<tr><td>{t}</td><td>n</td><td>US0</td><td>Technology</td><td>x</td></tr>"
                              for t in [f"T{i}" for i in range(90)] + ["NQ1", "NQ2"]) + "</table>")
    return get


members, rules = universe_src.fetch_us_members(us_get())
check("S&P 500 + 나스닥100 에만 있는 종목", len(members) == 502
      and rules["S&P 500 구성 종목"]["n"] == 500
      and rules["나스닥100 에만 있는 종목"]["n"] == 2 and all(m["index"] for m in members))
check("나스닥100 은 목록 문서에서 읽고, 업종 이름을 S&P 500 쪽에 맞춘다",
      [m["sector"] for m in members if m["ticker"] in ("NQ1", "NQ2")] == ["Information Technology"] * 2
      and universe_src.NDX_URLS[0].endswith("List_of_NASDAQ-100_companies"))
members, rules = universe_src.fetch_us_members(us_get(ndx_ok=False))
check("나스닥100 을 못 받으면 빼고 가되 그렇게 적는다", len(members) == 500
      and any("못 받아 제외" in k for k in rules))
try:
    universe_src.fetch_us_members(us_get(sp_n=40))
    check("S&P 500 이 너무 적게 오면 실패", False)
except universe_src.UniverseError:
    check("S&P 500 이 너무 적게 오면 실패 (조용히 40종목으로 가지 않음)", True)

print("\n=== 네이버 종목 목록 (지수 구성 종목 · 시가총액 순위) ===")


def item(code, name, kind="stock", cap="1,234"):
    return {"stockType": "domestic", "stockEndType": kind, "itemCode": code,
            "stockName": name, "marketValue": cap, "closePrice": "1,000"}


got = universe.parse_naver_stocks({"stocks": [item("005930", "삼성전자", cap="12,131,028"),
                                              item("069500", "KODEX 200", "etf")],
                                   "totalCount": "2496"})
check("시가총액 순위 — ETF 제외 · 억 원", got == [{"code": "005930", "name": "삼성전자",
                                           "cap": 12131028.0}], str(got))
check("지수 구성 종목은 목록으로 온다", universe.parse_naver_stocks([item("000660", "SK하이닉스")])[0]["code"] == "000660")
check("빈 응답 · 이상한 모양", universe.parse_naver_stocks([]) == [] and universe.parse_naver_stocks(None) == []
      and universe.parse_naver_stocks("x") == [])
check("보통주만 — 우선주 · 스팩 제외",
      universe.is_common_stock("005930", "삼성전자") and not universe.is_common_stock("005935", "삼성전자우")
      and not universe.is_common_stock("123450", "어느제1호스팩") and not universe.is_common_stock("00593K", "x"))


def kr_get(kospi_index=True, kosdaq_index=False):
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        page = int(url.split("page=")[1].split("&")[0])
        if "/index/KPI200/" in url:
            if not kospi_index:
                return Resp("")
            base = (page - 1) * 100
            return Resp(payload=[item(f"{base + i:05d}0", f"코스피{base + i}") for i in range(100)]
                        if page <= 2 else [])
        if "/index/" in url:
            return Resp("") if not kosdaq_index else Resp(
                payload=[item(f"9{(page - 1) * 100 + i:04d}0", f"코닥{i}") for i in range(100)]
                if page <= 2 else [])
        market = "KOSPI" if "/KOSPI?" in url else "KOSDAQ"
        base = (page - 1) * 100
        rows = []
        for i in range(100):
            n = base + i
            kind = "etf" if i % 4 == 3 else "stock"
            code = f"{'1' if market == 'KOSPI' else '2'}{n:04d}{'5' if i % 10 == 1 else '0'}"
            rows.append(item(code, f"{market}{n}", kind))
        return Resp(payload={"stocks": rows, "totalCount": "2496"})
    get.calls = calls
    return get


g = kr_get()
members, rules = universe_src.fetch_kr_members(g)
check("코스피는 구성 종목 200 · 코스닥은 시가총액 상위 150 (구성 종목이 안 올 때)",
      rules.get("코스피200 구성 종목", {}).get("n") == 200
      and rules.get("코스닥 시가총액 상위 150", {}).get("n") == 150 and len(members) == 350,
      str(rules))
check("규칙에 어떤 방식인지 적는다", rules["코스피200 구성 종목"]["how"] == "index"
      and rules["코스닥 시가총액 상위 150"]["how"] == "cap")
kq = [m for m in members if m["market"] == "KOSDAQ"]
check("시가총액 순위에서는 ETF · 우선주를 건너뛰고 채운다",
      len(kq) == 150 and all(m["code"].endswith("0") for m in kq))
members, rules = universe_src.fetch_kr_members(kr_get(kospi_index=False))
check("코스피 구성 종목도 못 받으면 시가총액 상위 200", "코스피 시가총액 상위 200" in rules
      and len([m for m in members if m["market"] == "KOSPI"]) == 200)
members, rules = universe_src.fetch_kr_members(kr_get(kosdaq_index=True))
check("코스닥 구성 종목이 오면 그것을 쓴다", "코스닥150 구성 종목" in rules)

print("\n=== 합치기 · 규칙 문장 · 저장 ===")
merged = universe.merge_members(
    [{"ticker": "AAA", "name": "에이", "sector": "Energy", "cik": 1}, {"ticker": "MSFT", "name": "Microsoft", "cik": 2}],
    extra=[{"ticker": "MSFT", "name": ""}, {"ticker": "CRCL", "name": ""}])
by = {m["ticker"]: m for m in merged}
check("관심종목이 지수에도 있으면 지수 종목으로 (이름 · CIK 를 채움)",
      by["MSFT"]["index"] is True and by["MSFT"]["name"] == "Microsoft" and by["MSFT"]["cik"] == 2)
check("지수에 없는 관심종목은 index=False", by["CRCL"]["index"] is False and len(merged) == 3)
check("파일에 '관심종목' 표시를 따로 싣지 않는다", all("held" not in m for m in merged))
pay = {"rules": {"S&P 500 구성 종목": {"n": 2}, "나스닥100 에만 있는 종목": {"n": 0}},
       "members": merged}
check("규칙 문장 — 더하면 전체", universe.rule_text("us", pay)
      == "S&P 500 구성 종목 2 + 나스닥100 에만 있는 종목 0 + 관심종목 1 = 3종목", universe.rule_text("us", pay))
text = universe.dump({"rules": {}, "members": [], "screens": []})
back = universe.parse(text)
check("저장했다 읽으면 버전 · 만든 시각", back["version"] == universe.VERSION
      and abs(back["made"] - time.time()) < 5)
check("깨진 파일 · 다른 버전은 빈 묶음", universe.parse("{x") == {} and universe.parse('{"version":99}') == {}
      and universe.parse("[]") == {})
check("나이(시간)", abs(universe.age_hours({"made": time.time() - 7200}) - 2.0) < 0.01
      and universe.age_hours({}) is None)

print("\n=== 심사 결과를 파일로 — 판정만 남기고 되살린다 ===")
demo_screens, _e = demo_mod.demo_screens()
src0 = next(s for s in demo_screens.values() if s.ok)
row = json.loads(json.dumps(buffett.to_summary(src0, s="Industrials"), ensure_ascii=False))
back = buffett.from_summary(row)
check("통과 수 · 연도 수 · 업종", back.ok and back.passed_count == src0.passed_count
      and back.year_count == src0.year_count and back.sector == "Industrials")
check("화면에 그리면 원본과 같다", ui.render_screen(back) == ui.render_screen(src0))
check("연도별 숫자는 싣지 않는다 (파일 크기)", len(json.dumps(row, ensure_ascii=False)) < 1500
      and "years" not in row)
bad = next((s for s in demo_screens.values() if not s.ok), None)
if bad is not None:
    b2 = buffett.from_summary(buffett.to_summary(bad))
    check("실패한 심사는 실패로 되살아난다", not b2.ok and b2.error == bad.error)
check("이상한 줄은 건너뛴다", buffett.from_summary({}) is None and buffett.from_summary("x") is None
      and buffett.from_summary({"t": "X", "c": [["없는기준", "pass"], ["roe", "이상"]]}).checks == [])
prof = kr_screen.VolProfile("005930", "삼성전자", bars=250, price=207500.0, vol_long=41.23456789,
                            ret_3m=-12.5)
d = universe.profile_to_dict(prof)
check("프로파일 — 빈 칸은 빼고 소수는 줄임", "high_52w" not in d and d["vol_long"] == 41.2346)
back_p = universe.restore(kr_screen.VolProfile, [d, {"ticker": "X", "모르는칸": 1}, "x", {}])
check("되살리기 — 모르는 칸은 버리고 이상한 줄은 건너뜀",
      len(back_p) == 2 and back_p[0].price == 207500.0 and back_p[0].ret_3m == -12.5
      and back_p[1].ticker == "X")

print("\n=== 수집기 — 미국 전수 심사 ===")
import collect  # noqa: E402

real_screen_company = buffett.screen_company


def fake_screen_company(ticker, facts, *, years=10, th=None):
    s = copy.copy(src0)
    s.ticker, s.name = ticker, f"이름 {ticker}"
    return s


def members_fn():
    ms = [{"ticker": f"T{i}", "name": f"회사{i}", "sector": "Energy", "cik": 100 + i, "index": True}
          for i in range(95)]
    ms += [{"ticker": "GOOGL", "name": "Alphabet A", "sector": "Communication Services",
            "cik": 7, "index": True},
           {"ticker": "GOOG", "name": "Alphabet C", "sector": "Communication Services",
            "cik": 7, "index": True},
           {"ticker": "ASML", "name": "ASML", "sector": "Technology", "cik": None, "index": True}]
    return ms, {"S&P 500 구성 종목": {"n": 97}, "나스닥100 에만 있는 종목": {"n": 1}}


batches = []


def facts_fn(ciks):
    batches.append(len(ciks))
    out = {t: object() for t in ciks if t != "T3"}
    return out, ({"T3": "HTTP 404"} if "T3" in ciks else {})


buffett.screen_company = fake_screen_company
try:
    with tempfile.TemporaryDirectory() as out:
        r = collect.build_universe_us(None, out, members_fn=members_fn,
                                      ticker_map_fn=lambda ua: {"MSFT": 789019, "CRCL": 5},
                                      facts_fn=facts_fn)
        data = universe.parse(pathlib.Path(out, "universe_us.json").read_text(encoding="utf-8"))
        tick = [s["t"] for s in data["screens"]]
        watch = set(config.watchlist_us_tickers())
        check("지수 종목 + 관심종목을 심사", r["n"] == len(tick) and "T0" in tick and "MSFT" in tick, str(r))
        check("묶음으로 나눠 받는다 (원본을 다 들고 있지 않게)",
              len(batches) >= 3 and max(batches) <= config.UNIVERSE_US_BATCH, str(batches))
        check("같은 회사의 다른 주식은 한 번만 (GOOG / GOOGL)",
              ("GOOG" in tick) + ("GOOGL" in tick) == 1
              and sum(1 for m in data["members"] if m["ticker"] in ("GOOG", "GOOGL")) == 1)
        check("CIK 가 없는 종목 · 못 받은 종목은 이유와 함께", "ASML" in data["errors"]
              and data["errors"]["T3"] == "HTTP 404" and "T3" not in tick)
        check("업종과 이름이 따라온다", next(s for s in data["screens"] if s["t"] == "T0")["s"] == "Energy"
              and next(s for s in data["screens"] if s["t"] == "T0")["n"] == "회사0")
        check("파일에 '관심종목' 표시가 없다 — index 만",
              all(set(m) <= {"ticker", "name", "sector", "index"} for m in data["members"])
              and any(not m["index"] for m in data["members"]) == bool(
                  watch - {"GOOGL"} - {f"T{i}" for i in range(95)}))
        before = len(batches)
        r2 = collect.build_universe_us(None, out, members_fn=members_fn, facts_fn=facts_fn,
                                       ticker_map_fn=lambda ua: {}, min_keep=10)
        r2b = collect.build_universe_us(None, out, members_fn=members_fn, facts_fn=facts_fn,
                                        ticker_map_fn=lambda ua: {})
        check("지난 파일이 너무 작으면(반쪽짜리) 새것이어도 다시 한다", not r2b.get("kept"))
        before = len(batches)
        check("방금 만든 파일이 있으면 다시 묻지 않는다 (하루 한 번)",
              r2.get("kept") and r2.get("n", 0) > 50, str(r2))
        r3 = collect.build_universe_us(None, out, members_fn=members_fn, facts_fn=facts_fn,
                                       ticker_map_fn=lambda ua: {}, force=True)
        check("강제로는 다시 한다", not r3.get("kept") and len(batches) > before)
        bad = json.loads(pathlib.Path(out, "universe_us.json").read_text(encoding="utf-8"))
        bad["rules"]["나스닥100 (목록을 못 받아 제외)"] = {"n": 0, "how": "실패: UniverseError"}
        pathlib.Path(out, "universe_us.json").write_text(json.dumps(bad), encoding="utf-8")
        before = len(batches)
        r3b = collect.build_universe_us(None, out, members_fn=members_fn, facts_fn=facts_fn,
                                        ticker_map_fn=lambda ua: {}, min_keep=10)
        check("지난번에 목록 하나를 못 받았으면 새 파일이어도 다시 한다",
              not r3b.get("kept") and len(batches) > before)

        def boom():
            raise universe_src.UniverseError("표에서 40종목만")

        old = json.loads(pathlib.Path(out, "universe_us.json").read_text(encoding="utf-8"))
        old["made"] = int(time.time() - 40 * 3600)
        pathlib.Path(out, "universe_us.json").write_text(json.dumps(old), encoding="utf-8")
        r4 = collect.build_universe_us(None, out, members_fn=boom, facts_fn=facts_fn)
        kept = universe.parse(pathlib.Path(out, "universe_us.json").read_text(encoding="utf-8"))
        check("목록을 못 받으면 지난 파일을 그대로 둔다 (손으로 고른 목록으로 바꾸지 않음)",
              r4.get("skipped") and r4.get("kept") and len(kept["screens"]) == len(old["screens"]))
    with tempfile.TemporaryDirectory() as out:
        r5 = collect.build_universe_us(None, out, members_fn=boom, facts_fn=facts_fn)
        check("지난 파일도 없으면 파일을 만들지 않는다",
              r5.get("skipped") and not os.path.exists(os.path.join(out, "universe_us.json")))
finally:
    buffett.screen_company = real_screen_company

print("\n=== 수집기 — 한국 전수 심사 ===")
kr_members = ([{"code": f"{i:05d}0", "name": f"코스피{i}", "cap": 1000.0 - i, "market": "KOSPI",
                "index": True} for i in range(20)]
              + [{"code": "005930", "name": "삼성전자", "cap": 12131028.0, "market": "KOSPI",
                  "index": True}])


class KrApp:
    def __init__(self, drop=0):
        self.drop, self.seen = drop, {}

    def kr_vol_profiles_for(self, cands):
        self.seen["vol"] = list(cands)
        use = cands[self.drop:]
        profs, _errs = demo_mod.demo_kr_vol_profiles(use)
        return profs, {c: "네이버 실패" for c, _n in cands[:self.drop]}

    def kr_value_rows_for(self, cands, *, yahoo_fallback=True):
        self.seen["fallback"] = yahoo_fallback
        return demo_mod.demo_kr_value_rows(cands)


with tempfile.TemporaryDirectory() as out:
    kapp = KrApp()
    r = collect.build_universe_kr(kapp, out, members_fn=lambda: (
        kr_members, {"코스피200 구성 종목": {"n": 21, "how": "index"}}))
    data = universe.parse(pathlib.Path(out, "universe_kr.json").read_text(encoding="utf-8"))
    codes = [m["code"] for m in data["members"]]
    watch_kr = [c for c, _n in config.watchlist_kr()]
    check("지수 종목 + 관심종목", set(watch_kr) <= set(codes) and "000000" in codes
          and len(codes) == len(set(codes)), str(r))
    check("일봉 프로파일 · 투자지표가 종목 수만큼", len(data["profiles"]) == len(codes)
          and len(data["values"]) == len(codes))
    check("전수 심사에서는 야후로 다시 묻지 않는다 (종목당 1~2초)", kapp.seen["fallback"] is False)
    profs = universe.restore(kr_screen.VolProfile, data["profiles"])
    vals = universe.restore(kr_screen.ValueRow, data["values"])
    same, _se = demo_mod.demo_kr_vol_profiles([(m["code"], m["name"]) for m in data["members"]])
    check("되살린 프로파일로 스크리너를 돌리면 원본과 같은 종목",
          [h.ticker for h in kr_screen.relative_strength_hits(profs)]
          == [h.ticker for h in kr_screen.relative_strength_hits(same)]
          and [h.ticker for h in kr_screen.value_hits(vals)]
          == [h.ticker for h in kr_screen.value_hits(
              demo_mod.demo_kr_value_rows([(m["code"], m["name"]) for m in data["members"]]))])
    check("규칙 문장", "코스피200 구성 종목 21" in universe.rule_text("kr", data)
          and universe.rule_text("kr", data).endswith(f"= {len(codes)}종목"),
          universe.rule_text("kr", data))
    kapp2 = KrApp(drop=len(codes))
    r2 = collect.build_universe_kr(kapp2, out, members_fn=lambda: (kr_members, {"x": {"n": 21}}))
    kept = universe.parse(pathlib.Path(out, "universe_kr.json").read_text(encoding="utf-8"))
    check("일봉을 절반도 못 받으면 지난 파일을 둔다", r2.get("skipped") and r2.get("kept")
          and len(kept["profiles"]) == len(codes))

src = pathlib.Path("tools/collect.py").read_text(encoding="utf-8")
wf = pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8")
check("수집기가 전수 심사를 돈다 (실패해도 스냅샷은 올라감)",
      "build_universe(app, args.out" in src and "전수 심사 단계 실패" in src)
check("워크플로 — 지난 전수 심사 파일을 꺼내 둔다",
      "universe_us.json universe_kr.json" in wf and 'git show "FETCH_HEAD:$f"' in wf
      and wf.index('git show "FETCH_HEAD:$f"') < wf.index("tools/collect.py --out"))
check("워크플로 — 시간 한도를 늘림", "timeout-minutes: 45" in wf)

print("\n=== 화면 — 전수 심사 결과로 그린다 ===")
_names = ("_discover_us", "_discover_kr", "_universe_or_none", "_universe_line",
          "_fallback_note", "_criteria_block")
_fns = [n for n in ast.parse(app_src).body
        if isinstance(n, ast.FunctionDef) and n.name in _names]


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSt:
    def __init__(self, sector="", q=None, choice=None):
        self.md, self.exp, self._sector, self._q, self.choice = [], [], sector, q, choice
        self.sector_opts = None

    def markdown(self, html, **k):
        self.md.append(html)

    def columns(self, spec):
        return [_Ctx() for _ in spec]

    def slider(self, label, lo, hi, value, key=None):
        return self._q or value

    def selectbox(self, label, opts, key=None, format_func=None, index=0):
        self.sector_opts = [format_func(o) for o in opts]
        return self._sector

    def toggle(self, label, value=False, key=None):
        return value

    def expander(self, label, expanded=False):
        self.exp.append(label)
        return _Ctx()

    def segmented_control(self, label, keys, default=None, key=None, format_func=None,
                          label_visibility=None):
        [format_func(k) for k in keys]
        return self.choice or default


def us_payload(n=120):
    screens = []
    base = [s for s in demo_screens.values() if s.ok]
    sect = ["Consumer Staples", "Utilities", "Information Technology"]
    for i in range(n):
        s = copy.copy(base[i % len(base)])
        s.ticker, s.name = (f"U{i}" if i else "MSFT"), f"Company {i}"
        screens.append(buffett.to_summary(s, s=sect[i % 3]))
    members = ([{"ticker": s["t"], "name": s["n"], "sector": s["s"], "index": True} for s in screens]
               + [{"ticker": "ASML", "name": "ASML", "index": True},
                  {"ticker": "CRCL", "name": "", "index": False}])
    return json.loads(universe.dump({
        "rules": {"S&P 500 구성 종목": {"n": n}, "나스닥100 에만 있는 종목": {"n": 1}},
        "members": members, "screens": screens,
        "errors": {"ASML": "CIK 를 찾지 못했습니다", "CRCL": "HTTP 404"}}))


def run(market, payload, **kw):
    st = FakeSt(**kw)
    calls = {"fallback": 0}

    def load_universe(m, use_demo):
        if isinstance(payload, Exception):
            raise payload
        return payload

    def soft_main(loader, use_demo, *rest, what="", secs=""):
        calls["fallback"] += 1
        return demo_mod.demo_screens()

    def kr_vol(use_demo):
        calls["fallback"] += 1
        c = list(config.screen_kr_candidates())
        return demo_mod.demo_kr_vol_profiles(c)

    import html as _h
    ns = {"st": st, "ui": ui, "config": config, "buffett": buffett, "kr_screen": kr_screen,
          "universe": universe, "dt": dt, "KST": ZoneInfo("Asia/Seoul"),
          "_esc_plain": lambda t: _h.escape(str(t), quote=True),
          "load_universe": load_universe, "_soft_main": soft_main, "load_screens": None,
          "load_kr_vol_profiles": kr_vol,
          "load_kr_value_rows": lambda use_demo: demo_mod.demo_kr_value_rows(
              list(config.screen_kr_candidates())),
          "load_kr_companies": lambda *a: {}, "load_news": lambda *a: {},
          "dart": type("D", (), {"key_fingerprint": staticmethod(lambda: "")}),
          "runner": type("R", (), {"cli_info": staticmethod(lambda: None)}),
          "_render_skill_buttons": lambda *a: None}
    exec(compile(ast.Module(body=_fns, type_ignores=[]), "app.py", "exec"), ns)
    ns["_discover_us" if market == "us" else "_discover_kr"](False)
    return st, "".join(st.md), calls


st_, html, calls = run("us", us_payload())
check("파일이 있으면 그 결과로 — 직접 받지 않는다", calls["fallback"] == 0 and "dash-sctable" in html)
check("후보를 어떻게 정했는지 화면에 (꺼도 보이는 줄)",
      'class="dash-legend"' in html and "S&amp;P 500 구성 종목 120 + 나스닥100 에만 있는 종목 1 + 관심종목 1 = 122종목" in html
      and "&amp;amp;" not in html
      and "심사 " in html and "위키백과" in html, "")
check("단계별로 남은 종목 — 후보 → 재무 받음 → 통과", "단계별로 남은 종목" in html
      and ">122<" in html and ">120<" in html and "빠진 종목 2개" in html)
check("업종별 통과 수", "dash-sectpass" in html and "필수소비재" in html and "유틸리티" in html)
check("업종을 고를 수 있다 (종목 수와 함께)", st_.sector_opts[0] == "전체 (120)"
      and any(o.startswith("필수소비재 (40)") for o in st_.sector_opts), str(st_.sector_opts))
tables = [t.split("</table>")[0] for t in html.split('dash-sctable">')[1:]]
n_pass = sum(1 for x in us_payload()["screens"] if sum(1 for c in x["c"] if c[1] == "pass") >= 6)
check("첫 표는 40줄까지 · 나머지는 접어 둠",
      tables and tables[0].count("</tr>") - 1 == min(n_pass, config.DISCOVER_TABLE_ROWS)
      and (n_pass <= config.DISCOVER_TABLE_ROWS
           or any(e.startswith("나머지 통과 종목") for e in st_.exp)),
      f"통과 {n_pass} · 표 {[t.count('</tr>') - 1 for t in tables]}")
check("내 관심종목에 ★", "ct-star" in html)
st2, html2, _c = run("us", us_payload(), sector="Utilities")
check("업종으로 좁히면 그 업종만", "유틸리티" in html2 and "dash-sectpass" not in html2
      and all("필수소비재" not in t.split("</table>")[0] for t in
              html2.split('dash-sctable">')[1:]))
st3, html3, _c = run("us", us_payload(), q=9)
n9 = sum(1 for s in us_payload()["screens"]
         if sum(1 for c in s["c"] if c[1] == "pass") >= 9)
check("통과 수 기준을 올리면 줄어든다", f">{n9}<" in html3 or "통과한 종목이 없습니다" in html3)
st4, html4, calls4 = run("us", {})
check("파일이 없으면 예전 후보로 — 그렇다고 화면에 적는다",
      calls4["fallback"] == 1 and "전수 심사 결과를 아직 받지 못했습니다" in html4
      and "손으로 고른 후보" in html4 and "dash-sctable" in html4)
st5, html5, calls5 = run("us", RuntimeError("timeout"))
check("파일을 받다 실패해도 화면이 죽지 않는다", calls5["fallback"] == 1 and "dash-sctable" in html5)

cands = [(f"{i:05d}0", f"종목{i}") for i in range(160)]
kr_pay = json.loads(universe.dump({
    "rules": {"코스피200 구성 종목": {"n": 100, "how": "index"},
              "코스닥 시가총액 상위 150": {"n": 60, "how": "cap"}},
    "members": [{"code": c, "name": n, "market": "KOSPI", "index": True} for c, n in cands],
    "profiles": [universe.profile_to_dict(p) for p in demo_mod.demo_kr_vol_profiles(cands)[0]],
    "values": [universe.profile_to_dict(v) for v in demo_mod.demo_kr_value_rows(cands)],
    "errors": {}}))
st6, html6, calls6 = run("kr", kr_pay, choice="rs")
check("한국도 파일로 — 직접 받지 않는다", calls6["fallback"] == 0
      and "코스피200 구성 종목 100 + 코스닥 시가총액 상위 150 60 = 160종목" in html6)
check("후보 수가 단계표에 반영된다", ">160<" in html6)
n_rs = len(kr_screen.relative_strength_hits(universe.restore(kr_screen.VolProfile, kr_pay["profiles"])))
check("통과가 많으면 표는 위 40종목만 싣고 그렇게 적는다",
      n_rs <= config.DISCOVER_TABLE_ROWS or f"통과 {n_rs}종목 중 위 {config.DISCOVER_TABLE_ROWS}종목" in html6,
      str(n_rs))
st7, html7, calls7 = run("kr", {})
check("한국도 파일이 없으면 예전 후보로 · 화면에 적는다",
      calls7["fallback"] == 1 and "전수 심사 결과를 아직 받지 못했습니다" in html7)

check("데모의 국내 프로파일을 한 번 더 싸지 않는다 (화면이 죽던 것)",
      "return demo_mod.demo_kr_vol_profiles(cands)\n" in app_src
      and "demo_mod.demo_kr_vol_profiles(cands), {}" not in app_src)
check("앱은 전수 심사를 직접 하지 않는다 (파일만 읽음)",
      "universe_src" not in app_src and "def load_universe(" in app_src
      and '"load_universe": "전수 심사"' in app_src)
check("파일 주소는 data 브랜치", config.UNIVERSE_URLS["us"].endswith("/data/universe_us.json")
      and config.UNIVERSE_URLS["kr"].endswith("/data/universe_kr.json"))
tbl = ui.render_screen_table([buffett.from_summary(us_payload()["screens"][0])], buffett.CRITERIA,
                             held={"MSFT"}, sectors={"MSFT": "필수소비재"})
check("한눈표 — 종목 이름 · 업종 · ★", "sc-name" in tbl and "필수소비재" in tbl and "ct-star" in tbl
      and "<th>업종</th>" in tbl)
check("업종 칩 — 통과/전체", "1/2" in ui.render_sector_pass(
    [buffett.from_summary(s) for s in us_payload(2)["screens"]],
    [buffett.from_summary(us_payload(2)["screens"][0])],
    {"MSFT": "A", "U1": "A"}))

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
