"""모의 매수 실험 (2026-11-13) — 후보 몇 개를 '샀다고 치고', 매수 근거가 깨지면 '판다'.

사용자: "후보로 올린 것 중 몇 개 선별해서 현재부터 가짜로 매수했다는 설정을 하고, 매수
근거가 깨진다면 매도한다는 설정으로 그 흐름을 판별해서 수익률 및 매수 논거 변경점을 정리".

규칙 (재량 없음 — 코드가 정함):
  매수   첫 수집 회차에 시장마다 안정형 상위 STABLE_N · 성장형 상위 GROWTH_N 종목을 같은
         비중으로. 그 회차의 종가(차트 파일의 마지막 봉). 이후 새로 사지 않음(고정 묶음).
  빈자리 (11/17 저녁 추가) 판 자리는 그다음 회차(판 회차 포함) 후보 순서에서 지금 들고 있지
         않은 상위 종목으로 채움 — 판 돈(현금) 전부를 새로 산 종목에 똑같이 나눔(refill).
         전에는 판 돈을 현금으로 두어 묶음이 점점 현금이 됐음(11/17 한국 안정형 약 60%).
  매도   매수 근거(후보 관문)가 깨진 회차의 종가.
           안정형: 품질 통과 상실 · 가격 부담 높음 · 선행 EPS 90일 −5% 이하 · 실적 추세 악화
           성장형: 성장 품질 미통과 · PEG 2.5 초과 · 선행 EPS 90일 −5% 이하
         같은 회차에 판정할 데이터가 없으면(파일에 없음) 팔지 않고 '판정 불가' 로 적음.
  변경점 등(色)이 바뀐 순간을 모두 적음 — 매도는 아니지만 논거가 약해지거나 강해진 기록.
  비교   같은 기간 시장(한국 KODEX 200 · 미국 SPY) 수익률.

과거로 돌려 보는 백테스트는 하지 않습니다 — 과거 시점의 재무 · 추정 스냅숏이 없어서
'그때의 후보' 를 다시 만들 수 없습니다. 오늘부터 앞으로만 따라갑니다.

파일: data 브랜치 `paper_portfolio.json`
    {"version":1, "start": "YYYY-MM-DD",
     "bench": {"kr": {"sym","p0","p"}, "us": {...}},
     "pos": [{"m","track","t","n","d0","p0","l0"(매수 때 등),"p","l"(지금 등),
              "state":"hold"/"sold","d1"?,"p1"?,"why"?, "r"?(빈자리 채움으로 산 종목이면 1)}],
     "events": [[날짜, 시장, 트랙, 티커, 'buy'/'change'/'sell'/'na', 글], …],
     "curve": {"kr": {"stable": {"start": "YYYY-MM-DD", "pts": [[종가 날짜, 가치, 시장 가치], …]},
                      "growth": {…}}, "us": {…}}}          # 11/16 — 아래 '누적수익률 곡선'

누적수익률 곡선 (2026-11-16 사용자 승인 — "누적수익률 기록 가능한가?" → "그렇게 진행해줘")
  묶음(시장 × 트랙)마다 계좌 가치를 100 에서 시작해 이어 붙입니다.
    · 묶음을 살 때 그때 현금을 종목 수로 똑같이 나눠 주수(가치 ÷ 매수가)를 정함
      (처음엔 100, 규칙 변경으로 다시 살 때는 그때까지 쌓인 현금 전부)
    · 판 종목(sold) · 실험에서 뺀 종목(void)은 판 가격 × 주수 만큼 현금이 되고 이후 0%
    · 가치 = 현금 + Σ 보유 주수 × 지금 가격 — nav() 가 pos 만으로 매번 처음부터 다시 셈
      (주수를 따로 저장하지 않아 예전 파일도 그대로 됨)
    · 시장 가치 = 100 × 지금 지수 ÷ 묶음 시작 때 지수
  한 번에 같이 산 종목만 있으면 가치 − 100 = 예전 '평균'(ret 동일 비중 평균)과 같습니다.
  다른 점은 다시 산 경우 — 평균은 새 묶음만 보지만 가치는 앞 묶음의 손익까지 이어 갑니다.
  점은 수집 회차마다 차트 파일의 마지막 봉 날짜(종가 날짜)로 하나 — 같은 날짜면 바꿉니다
  (주말 · 장 시작 전 수집이 같은 점을 반복해 찍지 않게).
  11/16 오후: 수집기가 받은 1년 일봉으로 묶음 시작부터 **거래일마다** 다시 채웁니다
  (backfill_curve — 수집이 빠진 날도 점이 생김). 그날까지 산 · 판 것만 반영하고(매수 · 매도
  시각의 종가 날짜 = close_date), 보유 종목은 그날 종가로 셈. 일봉이 없는 종목은 그날 이전
  마지막으로 아는 가격(없으면 매수가).
"""
from __future__ import annotations

import datetime as _dt

import buffett
import funnel
import growth
import integrate

STABLE_N = 5
GROWTH_N = 3
BENCH = {"kr": "069500.KS", "us": "SPY"}
KEEP_EVENTS = 400
LAMP_WORD = {"g": "충족", "y": "보통", "r": "주의", "-": "없음"}
LAMP_NAME = {"quality": "품질", "price": "가격", "eps": "선행 EPS",
             "growth": "성장 품질", "timing": "타이밍"}


def _px(row):
    p = getattr(row, "price", None) if row is not None else None
    return None if p is None else float(p)


def judge(track: str, summary: dict | None, frow: dict | None, row, market: str
          ) -> tuple[dict | None, list[str]]:
    """(등 {키: 색}, 깨진 근거 목록). 판정할 데이터가 없으면 (None, [])."""
    if not summary:
        return None, []
    fr = frow or {}
    f = fr.get("f")
    gr = summary.get("gr") or {}
    broken: list[str] = []
    if track == "stable":
        sc = buffett.from_summary(summary)
        if sc is None or not sc.ok:
            return None, []
        q, _ = integrate._quality(sc, market)
        p, _ = integrate._price(fr) if fr else ("-", "")
        e, _ = integrate._eps(f) if fr else ("-", "")
        lamps = {"quality": q, "price": p, "eps": e}
        if not buffett.quality_pass(sc, market):
            broken.append("품질 기준 통과 상실")
        if fr and funnel.price_state(fr.get("p")) == "heavy":
            broken.append("가격 부담 높음")
    else:
        g, _ = integrate._growth_lamp(gr, market)
        p, _, pg = integrate._peg_lamp(f, _px(row))
        e, _ = integrate._trend_lamp(f)
        lamps = {"growth": g, "price": p, "eps": e}
        if gr and not growth.passes(gr, market):
            broken.append("성장 품질 기준 미통과")
        if pg is not None and pg > growth.PEG_OK:
            broken.append(f"PEG {pg:.2f} (> {growth.PEG_OK})")
    if funnel.eps_down(f):
        broken.append(f"선행 EPS 90일 {f['c90'] * 100:+.1f}%")
    if track == "stable" and gr.get("td"):
        broken.append("실적 추세 악화 (매출 · 영업이익 3년 연속 감소)")
    lamps["timing"] = "g" if integrate._chart(row)[0] == integrate.GREEN else "-"
    return lamps, broken


def start(day: str, picks: dict, prices: dict, bench: dict) -> dict:
    """첫 회차 — picks = {(시장, 트랙): [(티커, 이름, 등), …]} · prices = {(시장, 티커): 종가}."""
    pf = {"version": 1, "start": day, "bench": {}, "pos": [], "events": []}
    for (m, track), lst in picks.items():
        add_sleeve(pf, day, m, track, lst, prices, bench)
    return pf


def add_sleeve(pf: dict, day: str, m: str, track: str, lst: list, prices: dict,
               bench: dict) -> int:
    """한 묶음(시장 × 트랙)을 이 회차에 사서 넣음 — 첫 회차에 데이터가 없던 묶음(예: 성장
    지표가 다음 수집부터 생김)은 데이터가 생긴 회차에 시작합니다. 넣은 종목 수."""
    b = (bench or {}).get(m)
    if b is not None:
        pf.setdefault("bench", {}).setdefault(m, {"sym": BENCH[m], "p0": b, "p": b})["p"] = b
    n = 0
    for t, name, lamps in lst:
        p0 = prices.get((m, t))
        if p0 is None:
            continue
        pf["pos"].append({"m": m, "track": track, "t": t, "n": name, "d0": day, "p0": p0,
                          "l0": lamps, "p": p0, "l": lamps, "state": "hold", "b0": b, "b": b})
        pf["events"].append([day, m, track, t, "buy", f"매수 {p0:,.2f} — 등 " + _lamp_text(lamps)])
        n += 1
    return n


def refill(pf: dict, day: str, m: str, track: str, ranked: list, n: int, prices: dict,
           bench: dict) -> list:
    """빈자리 채우기 (11/17 사용자 승인 "제안대로 해줘") — 판 자리를 그 회차 후보로 다시 채움.

    묶음(시장 × 트랙)에 들고 있는 종목(hold — 판정 불가 포함)이 n 개보다 적고 판 돈(현금)이
    있으면, ranked(그 회차 후보 순서 [(티커, 이름, 등), …]) 에서 **지금 들고 있지 않은**
    종목을 위에서부터 빈자리 수만큼 그 회차 종가에 삽니다. 예전에 팔았던 종목도 다시
    후보면 살 수 있습니다. 돈은 ledger 규칙 그대로 — 같은 회차에 산 종목끼리 그때까지
    쌓인 현금을 똑같이 나눔. 가격이 없는 종목은 건너뜀. 돌려줌: 산 티커 목록.
    void 만 남은 묶음(규칙 변경)은 add_sleeve 가 다시 시작하므로 여기서는 건너뜀.
    """
    if not has_sleeve(pf, m, track):
        return []
    held = {p["t"] for p in pf.get("pos", [])
            if p["m"] == m and p["track"] == track and p.get("state") == "hold"}
    slots = n - len(held)
    lg = ledger(pf, m, track)
    if slots <= 0 or not lg or lg[0] <= 1e-9:
        return []
    b = (bench or {}).get(m)
    bought = []
    for t, name, lamps in ranked:
        if len(bought) >= slots:
            break
        if t in held or t in bought:
            continue
        p0 = prices.get((m, t))
        if p0 is None:
            continue
        pf["pos"].append({"m": m, "track": track, "t": t, "n": name, "d0": day, "p0": p0,
                          "l0": lamps, "p": p0, "l": lamps, "state": "hold", "b0": b, "b": b,
                          "r": 1})
        pf.setdefault("events", []).append([day, m, track, t, "buy",
                             f"빈자리 채움 매수 {p0:,.2f} — 판 돈으로 · 등 " + _lamp_text(lamps)])
        bought.append(t)
    return bought


def has_sleeve(pf: dict, m: str, track: str) -> bool:
    return any(p["m"] == m and p["track"] == track and p.get("state") != "void"
               for p in pf.get("pos", []))


def reset_track(pf: dict, day: str, track: str, why: str, prices: dict | None = None) -> int:
    """규칙이 바뀐 트랙(11/13 성장형 문턱 5 → 6)을 실험에서 뺌 — 지우지 않고 state 'void' 로
    남겨 기록은 보이게 하고, 요약 · 묶음 판정에서는 뺍니다. 그 회차에 새 규칙으로 다시 삽니다."""
    n = 0
    for ps in pf.get("pos", []):
        if ps.get("track") != track or ps.get("state") != "hold":
            continue
        px = (prices or {}).get((ps["m"], ps["t"]), ps.get("p"))
        ps.update(state="void", d1=day, p1=px, why=why)
        pf["events"].append([day, ps["m"], track, ps["t"], "reset",
                             f"실험에서 뺌 ({ret(ps) * 100:+.1f}%) — {why}"])
        n += 1
    return n


def _lamp_text(lamps: dict) -> str:
    return " · ".join(f"{LAMP_NAME.get(k, k)} {LAMP_WORD.get(v, v)}" for k, v in lamps.items()
                      if k != "timing") + (" · 타이밍" if lamps.get("timing") == "g" else "")


def step(pf: dict, day: str, judged: dict, prices: dict, bench: dict) -> dict:
    """다음 회차 — judged = {(시장, 트랙, 티커): (등 또는 None, 깨진 근거)}."""
    for m, b in (bench or {}).items():
        if b is not None and m in pf.get("bench", {}):
            pf["bench"][m]["p"] = b
    for ps in pf.get("pos", []):
        if ps.get("state") != "hold":
            continue
        key = (ps["m"], ps["track"], ps["t"])
        px = prices.get((ps["m"], ps["t"]))
        if px is not None:
            ps["p"] = px
        if (bench or {}).get(ps["m"]) is not None:
            ps["b"] = bench[ps["m"]]                 # 시장 지수 — 매도하면 그 회차에서 멈춤
        lamps, broken = judged.get(key, (None, []))
        if lamps is None:
            if not ps.get("na"):
                pf["events"].append([day, ps["m"], ps["track"], ps["t"], "na",
                                     "판정할 데이터 없음 — 팔지 않고 둠"])
            ps["na"] = 1
            continue
        ps.pop("na", None)
        changes = [f"{LAMP_NAME.get(k, k)} {LAMP_WORD.get(ps['l'].get(k), '?')}→{LAMP_WORD.get(v, v)}"
                   for k, v in lamps.items() if k != "timing" and ps["l"].get(k) != v]
        if lamps.get("timing") != ps["l"].get("timing"):
            changes.append("타이밍 " + ("켜짐" if lamps.get("timing") == "g" else "꺼짐"))
        if changes:
            pf["events"].append([day, ps["m"], ps["track"], ps["t"], "change", " · ".join(changes)])
        ps["l"] = lamps
        if broken and px is not None:
            ps.update(state="sold", d1=day, p1=px, why=" · ".join(broken))
            pf["events"].append([day, ps["m"], ps["track"], ps["t"], "sell",
                                 f"매도 {px:,.2f} ({ret(ps) * 100:+.1f}%) — 근거 깨짐: "
                                 + " · ".join(broken)])
    pf["events"] = pf["events"][-KEEP_EVENTS:]
    pf["last"] = day
    return pf


def ret(ps: dict) -> float:
    end = ps.get("p1") if ps.get("state") in ("sold", "void") else ps.get("p")
    return (end / ps["p0"] - 1.0) if end and ps.get("p0") else 0.0


def bench_ret(ps: dict) -> float | None:
    """같은 기간(매수 회차 → 매도 회차 또는 지금) 시장 수익률."""
    b0, b = ps.get("b0"), ps.get("b")
    return (b / b0 - 1.0) if b0 and b else None


def summary(pf: dict, market: str, track: str) -> dict:
    """{n, hold, sold, avg(동일 비중 평균 수익률), bench(같은 기간 시장 평균)}."""
    ps = [p for p in pf.get("pos", []) if p["m"] == market and p["track"] == track
          and p.get("state") != "void"]
    bs = [bench_ret(p) for p in ps if bench_ret(p) is not None]
    bench = sum(bs) / len(bs) if bs else None
    rs = [ret(p) for p in ps]
    return {"n": len(ps), "hold": sum(1 for p in ps if p["state"] == "hold"),
            "sold": sum(1 for p in ps if p["state"] == "sold"),
            "avg": sum(rs) / len(rs) if rs else None, "bench": bench}


# ── 누적수익률 곡선 (11/16) ─────────────────────────────────────────────────

#: 곡선 점을 몇 개까지 둘지 (하루 1점 — 약 4년)
KEEP_POINTS = 1000


def _sleeve(pf: dict, m: str, track: str) -> list:
    return [(i, p) for i, p in enumerate(pf.get("pos") or [])
            if p.get("m") == m and p.get("track") == track and p.get("p0")]


def ledger(pf: dict, m: str, track: str) -> tuple[float, dict] | None:
    """묶음 장부 — (지금 현금, {pf["pos"] 번호: 주수}). 처음 100 기준 (11/17 nav 에서 떼어 냄).

    주수 = 산 때 현금 ÷ 종목 수 ÷ 매수가 (소수 주). 화면은 이 값에 실험 금액 ÷ 100 을
    곱해 '몇 주 · 얼마' 로 보입니다(CAPITAL) — 계좌 가치(nav)와 같은 계산이라 어긋나지 않음.
    """
    ps = _sleeve(pf, m, track)
    if not ps:
        return None
    by_i = dict(ps)
    exits = sorted((p["d1"], i) for i, p in ps
                   if p.get("state") in ("sold", "void") and p.get("d1"))
    cash, units, k = 100.0, {}, 0

    def take(upto):
        nonlocal cash, k
        while k < len(exits) and (upto is None or exits[k][0] <= upto):
            q = by_i[exits[k][1]]
            cash += units.get(exits[k][1], 0.0) * float(q.get("p1") or q.get("p") or 0.0)
            k += 1

    for d0 in sorted({p["d0"] for _i, p in ps}):
        take(d0)                                   # 같은 시각에 판 것(규칙 변경)은 먼저 현금으로
        grp = [i for i, p in ps if p["d0"] == d0]
        if cash <= 0:
            continue
        each = cash / len(grp)
        for i in grp:
            units[i] = each / float(by_i[i]["p0"])
        cash = 0.0
    take(None)
    return cash, units


def nav(pf: dict, m: str, track: str) -> float | None:
    """묶음의 지금 계좌 가치 (처음 100) — 머리말 '누적수익률 곡선' 규칙대로 pos 를 다시 돌려 셈."""
    lg = ledger(pf, m, track)
    if lg is None:
        return None
    cash, units = lg
    pos = pf.get("pos") or []
    held = sum(units.get(i, 0.0) * float(pos[i].get("p") or pos[i]["p0"])
               for i, _p in _sleeve(pf, m, track) if pos[i].get("state") == "hold")
    return cash + held


#: 화면에 보이는 실험 금액 — 묶음(시장 × 트랙)마다 (11/17 사용자 "몇 주 사서 얼마에 팔았다,
#: 얼마로 실험한다"). 계산은 처음 100 기준 그대로이고 화면만 이 금액으로 바꿔 보입니다.
CAPITAL = {"kr": 10_000_000, "us": 10_000}


def shares(pf: dict, m: str, track: str) -> dict:
    """{pf["pos"] 번호: 실험 금액 기준 주수(소수)} — 화면용."""
    lg = ledger(pf, m, track)
    if lg is None:
        return {}
    k = CAPITAL.get(m, 100) / 100.0
    return {i: u * k for i, u in lg[1].items()}


def close_date(stamp: str, market: str) -> str:
    """수집 시각(KST "YYYY-MM-DD HH:MM") 에 그 시장의 마지막 종가 날짜(휴장일은 모름 — 주말만 뺌).
    한국 = 15:30 지났으면 그날, 아니면 전 평일 / 미국 = 06:00 KST(뉴욕 16:00, 겨울 기준) 전이면
    그 전 평일의 미국 날짜. 예전 묶음의 시작 점 날짜에만 씁니다(나머지는 차트 파일의 봉 날짜)."""
    t = _dt.datetime.strptime(str(stamp)[:16], "%Y-%m-%d %H:%M")
    if market == "kr":
        d = t.date() if (t.hour, t.minute) >= (15, 30) else t.date() - _dt.timedelta(days=1)
    else:
        d = (t - _dt.timedelta(hours=6)).date() - _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d.isoformat()


def update_curve(pf: dict, m: str, track: str, bar_date: str | None,
                 bench_now: float | None) -> list | None:
    """이번 회차 점을 넣음(같은 날짜면 바꿈). 돌려줌: 넣은 점 [날짜, 가치, 시장 가치]."""
    ps = _sleeve(pf, m, track)
    v = nav(pf, m, track)
    if not ps or v is None or not bar_date:
        return None
    cv = pf.setdefault("curve", {}).setdefault(m, {}).setdefault(track, {})
    first = min(p["d0"] for _i, p in ps)
    cv.setdefault("start", close_date(first, m))
    b0 = next((p.get("b0") for _i, p in sorted(ps, key=lambda x: x[1]["d0"]) if p.get("b0")), None)
    bv = round(100.0 * bench_now / b0, 3) if bench_now and b0 else None
    pt = [str(bar_date)[:10], round(v, 3), bv]
    pts = [x for x in cv.get("pts") or [] if x and x[0] != pt[0]]
    pts.append(pt)
    pts.sort(key=lambda x: x[0])
    cv["pts"] = pts[-KEEP_POINTS:]
    return pt


def curve(pf: dict, m: str, track: str) -> list:
    """그릴 점 — 시작 점(100, 100)을 앞에 붙임. [[날짜, 가치, 시장 가치], …]"""
    cv = ((pf.get("curve") or {}).get(m) or {}).get(track) or {}
    pts = [x for x in cv.get("pts") or [] if isinstance(x, list) and len(x) >= 3]
    if not cv.get("start"):
        return pts
    # 시작 날짜와 같은 날짜의 점도 둠 — 같은 종가 날짜에 산 뒤 가격이 다르게 잡힌 경우(11/13
    # 16:44 매수가 ≠ 이후 회차의 11/13 종가)가 있어, 빼면 100 만 보이고 실제 손익이 숨음
    return [[cv["start"], 100.0, 100.0]] + [x for x in pts if x[0] >= cv["start"]]


def fill_bench(pf: dict, m: str, dates: list, closes: list) -> int:
    """시장 지수를 못 받은 회차에 산 종목(b0 없음)의 b0 를 일봉에서 채움 (11/16).

    매수 시각의 종가 날짜(close_date) 이하 마지막 종가. 판 종목의 b(매도 때 지수)도 없으면
    매도 날짜로 채움. 시장 상태 묶음(pf["bench"])의 p0 도 없으면 채움. 채운 수."""
    pairs = [(str(d)[:10], c) for d, c in zip(dates or [], closes or []) if d and c]
    if not pairs:
        return 0

    def on(stamp):
        cd = close_date(stamp, m)
        got = [c for d, c in pairs if d <= cd]
        return float(got[-1]) if got else None

    n = 0
    for ps in pf.get("pos") or []:
        if ps.get("m") != m:
            continue
        if not ps.get("b0") and ps.get("d0"):
            v = on(ps["d0"])
            if v:
                ps["b0"] = v
                n += 1
        if ps.get("state") in ("sold", "void") and not ps.get("b") and ps.get("d1"):
            v = on(ps["d1"])
            if v:
                ps["b"] = v
        elif ps.get("state") == "hold" and not ps.get("b"):
            ps["b"] = float(pairs[-1][1])
    bm = (pf.get("bench") or {}).get(m)
    if bm is not None and not bm.get("p0"):
        bm["p0"] = (pf.get("pos") and on(min(p["d0"] for p in pf["pos"] if p.get("m") == m))) or None
    return n


def _on_or_before(hist, day):
    """(날짜 목록, 종가 목록) 에서 day 이하 마지막 종가 — 없으면 None."""
    import bisect  # noqa: PLC0415

    dates, closes = hist
    i = bisect.bisect_right(dates, day) - 1
    while i >= 0:
        if closes[i]:
            return float(closes[i])
        i -= 1
    return None


def nav_on(pf: dict, m: str, track: str, day: str, px_hist: dict) -> float | None:
    """그 종가 날짜(day)의 계좌 가치 — nav() 와 같은 규칙, 그날까지 산 · 판 것만. 보유는 그날 종가."""
    ps = [(i, p) for i, p in _sleeve(pf, m, track) if close_date(p["d0"], m) <= day]
    if not ps:
        return None
    by_i = dict(ps)
    exits = sorted((p["d1"], i) for i, p in ps
                   if p.get("state") in ("sold", "void") and p.get("d1")
                   and close_date(p["d1"], m) <= day)
    gone = {i for _d, i in exits}
    cash, units, k = 100.0, {}, 0

    def take(upto):
        nonlocal cash, k
        while k < len(exits) and (upto is None or exits[k][0] <= upto):
            q = by_i[exits[k][1]]
            cash += units.get(exits[k][1], 0.0) * float(q.get("p1") or q.get("p") or 0.0)
            k += 1

    for d0 in sorted({p["d0"] for _i, p in ps}):
        take(d0)
        grp = [i for i, p in ps if p["d0"] == d0]
        if cash <= 0:
            continue
        each = cash / len(grp)
        for i in grp:
            units[i] = each / float(by_i[i]["p0"])
        cash = 0.0
    take(None)
    held = 0.0
    for i, p in ps:
        if i in gone or i not in units:
            continue
        h = px_hist.get(p["t"])
        px = _on_or_before(h, day) if h else None
        held += units[i] * (px or float(p.get("p") or p["p0"]))
    return cash + held


def backfill_curve(pf: dict, m: str, track: str, px_hist: dict, bench_hist,
                   upto: str | None = None) -> int:
    """일봉으로 묶음 시작부터 거래일마다 점을 다시 채움 — 넣거나 바꾼 점 수.

    px_hist = {티커: (날짜 목록, 종가 목록)} · bench_hist = (날짜, 종가) 또는 None.
    거래일 = 지수 일봉 날짜(없으면 종목 일봉 날짜 모음) 중 묶음 시작 이후 · upto 이하.
    """
    ps = _sleeve(pf, m, track)
    if not ps:
        return 0
    start = close_date(min(p["d0"] for _i, p in ps), m)
    days = set(bench_hist[0]) if bench_hist and bench_hist[0] else set()
    if not days:
        for i, p in ps:
            days.update((px_hist.get(p["t"]) or ([], []))[0])
    days = sorted(d for d in days if d and d >= start and (upto is None or d <= upto))
    if not days:
        return 0
    b0 = next((p.get("b0") for _i, p in sorted(ps, key=lambda x: x[1]["d0"]) if p.get("b0")), None)
    cv = pf.setdefault("curve", {}).setdefault(m, {}).setdefault(track, {})
    cv.setdefault("start", start)
    pts = {x[0]: x for x in cv.get("pts") or [] if x}
    n = 0
    for d in days:
        v = nav_on(pf, m, track, d, px_hist)
        if v is None:
            continue
        bnow = _on_or_before(bench_hist, d) if bench_hist else None
        bv = round(100.0 * bnow / b0, 3) if bnow and b0 else (pts.get(d) or [None, None, None])[2]
        pts[d] = [d, round(v, 3), bv]
        n += 1
    cv["pts"] = sorted(pts.values(), key=lambda x: x[0])[-KEEP_POINTS:]
    return n
