"""차트 조건 — 한국 350종목 전수 (chart_kr.json) 2026-11-13.

    python tests/chart_kr_test.py

통신은 하지 않습니다. 네이버 업종 응답은 **실제로 확인하지 못한 모양**을
가정한 가짜이므로, 여기서 확인하는 것은 '형식이 맞을 때 맞게 읽는가' 와
'형식이 틀리면 버리고 지난 분류로 돌아가는가' 입니다.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
sys.path.insert(0, "tools")

import collect  # noqa: E402

app = collect.load_app()
import chart_signals  # noqa: E402
import components as ui  # noqa: E402
import universe  # noqa: E402
from sources import universe_src  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def bars(seed: int, n: int = 260, drift: float = 0.0) -> dict:
    rnd = random.Random(seed)
    px, cl = 10_000.0, []
    for _ in range(n):
        px *= 1 + rnd.gauss(drift, 0.02)
        cl.append(round(px))
    return {"high": [c * 1.01 for c in cl], "low": [c * 0.99 for c in cl], "close": cl,
            "volume": [1000.0] * n, "last_date": "2026-11-12"}


class Resp:
    def __init__(self, body, status=200):
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status

    @property
    def text(self):
        return self.content.decode("utf-8")

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.status)

    def json(self):
        return json.loads(self.content)


GROUPS = {"stockListSortType": "INDUSTRY", "groups": [
    {"no": 285, "name": "방송과엔터테인먼트", "totalCount": 58},
    {"no": 278, "name": "반도체와반도체장비", "totalCount": 174}]}   # 2026-11-13 실제 응답 모양


def semi_stocks(n_total=174, markers=True):
    rows = [{"stockType": "domestic", "stockEndType": "stock", "itemCode": f"{900000 + i}",
             "stockName": f"반도체{i}"} for i in range(n_total)]
    if markers:
        rows[0]["itemCode"], rows[1]["itemCode"] = "000660", "005930"
    rows.append({"stockEndType": "etf", "itemCode": "091160", "stockName": "KODEX 반도체"})
    return rows


def fake_get(markers=True, big_ok=True, seen=None):
    data = semi_stocks(markers=markers)

    def get(url, headers=None, timeout=None):
        if seen is not None:
            seen.append((url, (headers or {}).get("Accept")))
        if "/industry?" in url:
            return Resp(GROUPS)
        if "/industry/278?" in url:
            q = dict(x.split("=") for x in url.split("?")[1].split("&"))
            page, size = int(q["page"]), int(q["pageSize"])
            if size == 100 and not big_ok:
                return Resp({}, 500)
            return Resp({"stocks": data[(page - 1) * size:page * size]})
        return Resp({}, 404)
    return get


print("1. 네이버 업종 읽기")
seen: list = []
codes, info = universe_src.fetch_kr_industry(get=fake_get(seen=seen))
check("반도체 업종 174종목 (ETF 제외)", len(codes) == 174 and "091160" not in codes
      and info["name"] == "반도체와반도체장비" and info["no"] == "278", str(info))
check("JSON 으로 요청 (text/html 이면 406)", all(acc == "application/json" for _u, acc in seen))
codes, info = universe_src.fetch_kr_industry(get=fake_get(big_ok=False))
check("100개씩 실패 → 50개씩으로", len(codes) == 174, str(info))
# 실제 응답처럼 첫 쪽 100개 안에 ETF 가 섞여 있어도 끝까지 넘겨야 합니다
mixed = semi_stocks()
for i in (10, 20, 30, 40):
    mixed[i] = {**mixed[i], "stockEndType": "etf"}


def get_mixed(url, headers=None, timeout=None):
    if "/industry?" in url:
        return Resp(GROUPS)
    q = dict(x.split("=") for x in url.split("?")[1].split("&"))
    page, size = int(q["page"]), int(q["pageSize"])
    return Resp({"stocks": mixed[(page - 1) * size:page * size]})


codes, info = universe_src.fetch_kr_industry(get=get_mixed)
check("첫 쪽에 ETF 가 섞여도 둘째 쪽까지", len(codes) == 170 and "000660" in codes, str(info))
try:
    universe_src.fetch_kr_industry(get=fake_get(markers=False))
    check("표지 종목이 없으면 예외", False)
except universe_src.UniverseError as exc:
    check("표지 종목이 없으면 예외", "000660" in str(exc), str(exc))
try:
    universe_src.fetch_kr_industry(get=lambda *a, **k: Resp({"groups": []}))
    check("업종이 없으면 예외", False)
except universe_src.UniverseError as exc:
    check("업종이 없으면 예외", "업종 0개" in str(exc), str(exc))

print("2. 줄 ↔ 파일")
b3 = bars(3)
r = chart_signals.build_row("005930", "삼성전자", b3["high"], b3["low"], b3["close"], b3["volume"])
d = chart_signals.row_to_dict(r)
r2 = chart_signals.row_from_dict(json.loads(json.dumps(d)))
check("되살린 줄의 판정이 같음",
      r2 is not None and r2.flags() == r.flags() and r2.side == r.side
      and r2.notes() == r.notes(), "")
check("작은 차트 봉은 싣지 않음", "spark" not in d and not r2.spark)
check("깨진 줄은 None", chart_signals.row_from_dict({"ticker": "X", "bars": "a" * 3,
                                                     "ichi": {"lead_a": 1}}) is not None
      and chart_signals.row_from_dict({"nope": 1}) is None)
check("한 줄 크기 1KB 안쪽", len(json.dumps(d, ensure_ascii=False)) < 1024,
      f"{len(json.dumps(d, ensure_ascii=False))} B")

print("3. 수집기 build_chart_kr")
N = 350
members = [{"code": f"{i:06d}", "name": f"종목{i}", "market": "KOSPI" if i < 200 else "KOSDAQ"}
           for i in range(1, N + 1)]
members[0]["code"], members[1]["code"] = "000660", "005930"
tmp = tempfile.mkdtemp()
with open(os.path.join(tmp, "universe_kr.json"), "w", encoding="utf-8") as fh:
    fh.write(universe.dump({"members": members}))
all_bars = {m["code"]: bars(i, drift=-0.004 if i % 5 == 0 else 0.0)
            for i, m in enumerate(members) if i % 50 != 7}       # 7개는 못 받음


def ohlc_fn(codes):
    return ({c: all_bars[c] for c in codes if c in all_bars},
            {c: "네이버 실패 → 야후도 비었음" for c in codes if c not in all_bars})


keep: dict = {}
t = time.time()
res = collect.build_chart_kr(app, tmp, ohlc_fn=ohlc_fn, keep=keep,
                             semi_fn=lambda: ({"000660", "005930", "777777"},
                                              {"name": "반도체와반도체장비", "no": "278",
                                               "how": "api", "n": 3}))
sec = time.time() - t
check("350종목 계산", res.get("n") == N and res.get("bars") == N - 7, str(res))
check("계산 시간(통신 제외) 5초 이내", sec < 5, f"{sec:.2f}초")
check("받은 봉을 깔때기용으로 남김", len(keep) == N - 7)
check("후보에 있는 반도체만 셈", res.get("semi") == 2, str(res.get("semi")))
payload = universe.parse(open(os.path.join(tmp, "chart_kr.json"), encoding="utf-8").read())
rows = payload.get("rows") or []
check("파일 줄 수 = 후보 수", len(rows) == N)
check("못 받은 종목은 이유와 함께", sum(1 for x in rows if x.get("error")) == 7
      and all("야후" in x["error"] for x in rows if x.get("error")))
check("반도체 표시", {x["ticker"] for x in rows if x.get("s")} == {"000660", "005930"})
size = os.path.getsize(os.path.join(tmp, "chart_kr.json"))
check("파일 크기 400KB 이내", size < 400 * 1024, f"{size / 1024:.0f} KB")

res2 = collect.build_chart_kr(app, tmp, ohlc_fn=ohlc_fn,
                              semi_fn=lambda: (_ for _ in ()).throw(RuntimeError("형식 바뀜")))
p2 = universe.parse(open(os.path.join(tmp, "chart_kr.json"), encoding="utf-8").read())
check("업종 실패 → 지난 분류 재사용", res2.get("semi_src") == "prev" and res2.get("semi") == 2
      and "형식 바뀜" in (p2.get("semi") or {}).get("e", ""), str(res2))

res3 = collect.build_chart_kr(app, tmp, ohlc_fn=lambda c: ({}, {x: "실패" for x in c}))
check("일봉을 절반도 못 받으면 지난 파일 유지",
      res3.get("kept") and universe.parse(open(os.path.join(tmp, "chart_kr.json"),
                                               encoding="utf-8").read()).get("rows"), str(res3))

print("4. 화면 — 합치기 · 반도체 먼저 · 파일 없음")
live = chart_signals.build_rows([("005930", "삼성전자"), ("123456", "라이브")],
                                {"005930": bars(1), "123456": bars(2)})
orig_load = app.load_universe
app.load_universe = lambda key, use_demo: p2 if key == "chart_kr" else {}
merged, semis, from_file, note = app._merge_chart_file(live, False)
check("지금 목록 + 파일 나머지", len(merged) == 2 + N - 1, str(len(merged)))
check("지금 목록 종목은 화면 값", "005930" not in from_file and "000660" in from_file)
check("안내에 기준 시각 · 출처", "수집기 기준" in note and "네이버" in note, note[:80])
app.load_universe = lambda key, use_demo: {}
m2, s2, _f, note2 = app._merge_chart_file(live, False)
check("파일 없으면 지금 목록만", len(m2) == 2 and not s2 and "아직 없어" in note2)


def boom(*_a, **_k):
    raise OSError("네트워크")


app.load_universe = boom
m3, _s, _f, note3 = app._merge_chart_file(live, False)
check("파일 읽기 실패해도 깨지지 않음", len(m3) == 2 and "읽지 못해" in note3)

# 탭 전체를 가짜 스트림릿으로 그려 봅니다
app.load_universe = lambda key, use_demo: p2 if key == "chart_kr" else {}
shown: list[str] = []
st = app.st
answers = {"chart_semi_kr": False}
orig = {k: getattr(st, k, None) for k in ("markdown", "toggle", "radio", "pills",
                                          "multiselect", "selectbox", "columns", "expander")}
st.markdown = lambda body, **_k: shown.append(str(body))
st.toggle = lambda label, value=False, key=None, **_k: answers.get(key, value)
st.radio = lambda label, options, **_k: options[0] if options else ""
st.pills = lambda *a, **k: []
st.multiselect = lambda *a, **k: []
st.columns = lambda spec, **k: [collect._Any() for _ in (spec if isinstance(spec, list) else range(spec))]
st.selectbox = lambda label, options, index=0, **k: options[index] if options else None
orig_rows = app.load_chart_rows
app.load_chart_rows = type("F", (), {"__call__": lambda self, m, u: live,
                                     "age": lambda self, *a: 0})()
orig_bars = app.load_chart_bars
app.load_chart_bars = lambda m, t, u: ({}, "테스트")
try:
    t = time.time()
    app.render_chart_tab(False, market="kr")
    sec = time.time() - t
    html = "\n".join(shown)
    check("탭 그리기 에러 없음 · 1초 이내", sec < 1.0, f"{sec:.2f}초")
    table = next((h for h in shown if "dash-ctable" in h), "")
    first = table.split("<tbody>")[1].split("</tr>")[0] if "<tbody>" in table else ""
    check("표 첫 줄이 반도체", "ct-semi" in first, first[:120])
    check("표는 30종목까지", table.count("<tr>") <= 31)
    check("못 받은 이유 칸 · 수집 안내", "수집기 기준" in html)
    answers["chart_semi_kr"] = True
    shown.clear()
    app.render_chart_tab(False, market="kr")
    table = next((h for h in shown if "dash-ctable" in h), "")
    check("반도체만 → 반도체 2종목", table.count("ct-semi") == 2, str(table.count("ct-semi")))
    answers["chart_semi_kr"] = False
    app.load_universe = lambda key, use_demo: {}
    shown.clear()
    app.render_chart_tab(False, market="kr")
    html = "\n".join(shown)
    check("파일 없을 때도 그려짐 (지금 목록)", "아직 없어" in html and "ct-semi" not in html)
finally:
    for k, v in orig.items():
        if v is not None:
            setattr(st, k, v)
    app.load_chart_rows, app.load_chart_bars, app.load_universe = orig_rows, orig_bars, orig_load

print("5. 같은 일봉을 두 번 받지 않음 (수집기 메모)")
from sources import naver  # noqa: E402

calls = []
XML = "".join(f'<item data="2026{m:02d}{d:02d}|100|110|90|105|1000" />'
              for m in range(1, 11) for d in range(1, 29))


class _R:
    status_code, encoding = 200, None
    text = XML

    def raise_for_status(self):
        pass


orig_get = naver.requests.get
naver.requests.get = lambda url, **k: calls.append(url) or _R()
try:
    naver.CHART_MEMO = {}
    cl, _v, _e = naver.fetch_daily_many(["000660", "005930"])
    oh, _oe = naver.fetch_ohlc_many(["000660", "005930"])
    check("메모 켜짐: 종가 · 고저종이 요청 2번", len(calls) == 2 and len(oh) == 2
          and oh["000660"]["close"] == cl["000660"], str(len(calls)))
    naver.CHART_MEMO = None
    calls.clear()
    naver.fetch_ohlc_many(["000660"])
    naver.fetch_ohlc_many(["000660"])
    check("메모 꺼짐(화면): 매번 받음", len(calls) == 2)
finally:
    naver.requests.get = orig_get
    naver.CHART_MEMO = None
src = open("tools/collect.py", encoding="utf-8").read()
check("수집기는 전수 단계 동안만 메모", "naver.CHART_MEMO = {}" in src
      and "finally:\n        naver.CHART_MEMO = None" in src)

print("6. 미국 — 위키백과 세부 업종 · chart_us.json")


def wiki_table(rows):
    body = "".join(f"<tr><td>{t}</td><td>{n}</td><td>{sec}</td><td>{sub}</td><td>{i}</td></tr>"
                   for i, (t, n, sec, sub) in enumerate(rows, 1))
    return ('<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>'
            f'<th>GICS Sub-Industry</th><th>CIK</th></tr>{body}</table>')


SP_ROWS = [("NVDA", "Nvidia", "Information Technology", "Semiconductors"),
           ("AMD", "Advanced Micro Devices", "Information Technology", "Semiconductors"),
           ("AMAT", "Applied Materials", "Information Technology",
            "Semiconductor Materials & Equipment"),
           ("BRK.B", "Berkshire", "Financials", "Multi-Sector Holdings")]
SP_ROWS += [(f"T{i}", f"Co{i}", "Industrials", "Machinery") for i in range(600)]


def wiki_get(rows):
    def get(url, headers=None, timeout=None):
        if "S%26P" in url:
            return Resp(wiki_table(rows).encode())
        return Resp(b"<html></html>")
    return get


us_codes, us_info = universe_src.fetch_us_semis(get=wiki_get(SP_ROWS))
check("미국 반도체 = 세부 업종에 Semiconductor", us_codes == {"NVDA", "AMD", "AMAT"}, str(us_info))
try:
    universe_src.fetch_us_semis(get=wiki_get([r for r in SP_ROWS if r[0] != "AMD"]))
    check("미국 표지 종목(AMD) 없으면 예외", False)
except universe_src.UniverseError as exc:
    check("미국 표지 종목(AMD) 없으면 예외", "AMD" in str(exc), str(exc))

us_members = [{"ticker": t, "name": n, "sector": sec, "index": True}
              for t, n, sec, _s in SP_ROWS[:516]]
with open(os.path.join(tmp, "universe_us.json"), "w", encoding="utf-8") as fh:
    fh.write(universe.dump({"members": us_members}))
us_bars = {m["ticker"].replace(".", "-"): bars(i) for i, m in enumerate(us_members) if i != 9}
asked: list = []


def us_ohlc(symbols):
    asked.extend(symbols)
    return ({x: us_bars[x] for x in symbols if x in us_bars},
            {x: "일봉이 비어 있습니다." for x in symbols if x not in us_bars})


keep_us: dict = {}
t = time.time()
ru = collect.build_chart_us(app, tmp, ohlc_fn=us_ohlc, keep=keep_us,
                            semi_fn=lambda: (us_codes, us_info))
sec = time.time() - t
check("미국 516종목 계산", ru.get("n") == 516 and ru.get("ok") == 515, str(ru))
check("미국 계산 시간(통신 제외) 5초 이내", sec < 5, f"{sec:.2f}초")
check("야후 표기로 요청 (BRK.B → BRK-B)", "BRK-B" in asked and "BRK.B" not in asked)
pu = universe.parse(open(os.path.join(tmp, "chart_us.json"), encoding="utf-8").read())
check("미국 반도체 표시", {x["ticker"] for x in pu["rows"] if x.get("s")} == {"NVDA", "AMD", "AMAT"})
size = os.path.getsize(os.path.join(tmp, "chart_us.json"))
check("미국 파일 크기 600KB 이내", size < 600 * 1024, f"{size / 1024:.0f} KB")
check("미국 일봉을 깔때기용으로 남김", len(keep_us) == 515)

live_us = chart_signals.build_rows([("NVDA", "NVIDIA"), ("QQQ", "QQQ")],
                                   {"NVDA": bars(5), "QQQ": bars(6)})
app.load_universe = lambda key, use_demo: pu if key == "chart_us" else {}
mu, su, fu, nu = app._merge_chart_file(live_us, False, "us")
check("미국 합치기 (ETF 는 지금 목록에만)", len(mu) == 2 + 515 and "NVDA" not in fu, str(len(mu)))
check("미국 안내 — 야후 · 위키백과", "야후 일봉" in nu and "위키백과" in nu, nu[:90])
app.load_universe = orig_load

src = open("tools/collect.py", encoding="utf-8").read()
check("미국 깔때기도 같은 일봉을 다시 씀", "ohlc_fn=us_ohlc_reuse if us_bars else None" in src)
check("상세 칸 — 작은 차트 없을 때 안내", "작은 차트 없음" in ui.render_chart_detail(
    r2, chart_signals.CONDITIONS))

print()
if FAILURES:
    print(f"실패 {len(FAILURES)}개: {FAILURES}")
    sys.exit(1)
print("모두 통과")
