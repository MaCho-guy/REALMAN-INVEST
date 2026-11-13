"""모의 매수 실험 (2026-11-13) — 후보 몇 개를 '샀다고 치고', 매수 근거가 깨지면 '판다'.

사용자: "후보로 올린 것 중 몇 개 선별해서 현재부터 가짜로 매수했다는 설정을 하고, 매수
근거가 깨진다면 매도한다는 설정으로 그 흐름을 판별해서 수익률 및 매수 논거 변경점을 정리".

규칙 (재량 없음 — 코드가 정함):
  매수   첫 수집 회차에 시장마다 안정형 상위 STABLE_N · 성장형 상위 GROWTH_N 종목을 같은
         비중으로. 그 회차의 종가(차트 파일의 마지막 봉). 이후 새로 사지 않음(고정 묶음).
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
              "state":"hold"/"sold","d1"?,"p1"?,"why"?}],
     "events": [[날짜, 시장, 트랙, 티커, 'buy'/'change'/'sell'/'na', 글], …]}
"""
from __future__ import annotations

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


def has_sleeve(pf: dict, m: str, track: str) -> bool:
    return any(p["m"] == m and p["track"] == track for p in pf.get("pos", []))


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
    end = ps.get("p1") if ps.get("state") == "sold" else ps.get("p")
    return (end / ps["p0"] - 1.0) if end and ps.get("p0") else 0.0


def bench_ret(ps: dict) -> float | None:
    """같은 기간(매수 회차 → 매도 회차 또는 지금) 시장 수익률."""
    b0, b = ps.get("b0"), ps.get("b")
    return (b / b0 - 1.0) if b0 and b else None


def summary(pf: dict, market: str, track: str) -> dict:
    """{n, hold, sold, avg(동일 비중 평균 수익률), bench(같은 기간 시장 평균)}."""
    ps = [p for p in pf.get("pos", []) if p["m"] == market and p["track"] == track]
    bs = [bench_ret(p) for p in ps if bench_ret(p) is not None]
    bench = sum(bs) / len(bs) if bs else None
    rs = [ret(p) for p in ps]
    return {"n": len(ps), "hold": sum(1 for p in ps if p["state"] == "hold"),
            "sold": sum(1 for p in ps if p["state"] == "sold"),
            "avg": sum(rs) / len(rs) if rs else None, "bench": bench}
