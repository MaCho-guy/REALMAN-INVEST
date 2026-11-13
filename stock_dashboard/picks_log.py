"""후보 기록 (2026-11-13) — 규칙이 맞는지 나중에 데이터로 보려고 날마다 후보를 쌓습니다.

사용자: "또 뭘 고치면 좋을까" → 제안 1순위(승인). 오늘 하루에만 품질 문턱 · 등 개수 ·
성장형 기준을 여러 번 바꿨는데 근거는 '논리적으로 맞아 보인다' 였습니다. 후보에 오른
종목이 이후 4주 · 12주 동안 시장 대비 어땠는지를 보려면 그날의 목록과 가격이 남아 있어야
합니다.

파일: data 브랜치 `picks_history.json` — 수집기가 지난 파일을 이어받아 붙입니다.
    {"version": 1, "made": …,
     "sec": {"us": {티커: GICS 업종}, "kr": {코드: "반도체"}},     # 날마다 합침 (11/13 저녁)
     "days": [
        {"d": "2026-11-13", "t": 수집 시각(epoch),
         "r": {규칙 값},                                          # 11/13 저녁 — rules() 참고
         "us": {"s": [[티커, 충족 수, 타이밍 1/0, 종가], …],     # 안정형 후보 (순서대로)
                "g": [[티커, 충족 수, 타이밍, 종가, PEG], …],   # 성장형 후보
                ── 아래는 11/13 저녁 추가 (사용자 승인 "스크리너 기준 발전 방향" 1단계) ──
                "sl": ["gy", …],      # s 와 같은 순서 — 등 (가격, 선행 EPS) 색 g/y/r/-
                "gl": ["gg", …],      # g 와 같은 순서 — 등 (PEG, 추정 흐름) 색
                "x":  {"p": [티커…], "e": […], "pe": […]},  # 품질 통과인데 관문에서 빠진 종목
                "gx": {"p": […], "e": […]},                # 성장 품질 통과인데 관문에서 빠진 종목
                "qh": [티커…],        # 품질 보류 (판정이 모자라 보류)
                "gn": [티커…],        # 성장 품질이 문턱보다 하나 모자란 종목 (문턱 −1 이면 통과)
                "qs": [티커…],        # 품질 미달 표본 — 티커 crc32 % QS_MOD == 0 (날마다 같은 종목)
                "n":  {"u": 재무 받음, "q": 품질 통과, "h": 보류, "gp": 성장 품질 통과}},
         "kr": {…}}, …]}

빠진 이유 글자 (x · gx): p = 가격 부담 높음(안정형 역DCF · 성장형 PEG 2.5 초과) ·
e = 선행 EPS 90일 −5% 이하 · t = 실적 추세 악화(안정형만). **걸린 관문을 전부** 적습니다
(화면의 '빠진 이유' 는 첫 번째 하나만) — 관문마다 따로 효과를 보려고.

왜 이것들을 남기나: 후보만 남기면 "후보가 시장보다 나았나" 만 알 수 있고 "관문 · 문턱이
제 몫을 했나" 는 알 수 없습니다. 빠진 종목(x · gx) · 문턱 바로 아래(gn · qh) · 미달
표본(qs) 이 비교 대상입니다. 판정 · 선행 EPS 추정은 지나간 날 값을 다시 받을 수 없어서
기록하지 않은 날은 영영 빕니다.

가격: 새 목록에는 종가를 싣지 않습니다 — 나중에 성과를 셀 때는 수집기가 받는 일봉(분할 ·
배당 조정)을 씁니다. s · g 의 종가는 예전 형식 그대로 둡니다(분할이 있으면 어긋날 수 있음).

같은 날 여러 번 수집하면 마지막 것으로 바꿉니다(r 도 그날 마지막 수집의 규칙). 최근
KEEP_DAYS 일만 둡니다.
"""
from __future__ import annotations

import zlib

import buffett
import config
import funnel
import growth
import integrate

KEEP_DAYS = 500
#: 기록 형식 — 2 = 빠진 종목 · 문턱 아래 · 미달 표본 · 등 · 규칙 (11/13 저녁)
SCHEMA = 2
#: 품질 미달 표본 크기 조절 — 미국 약 380 · 한국 약 290 미달 중 1/QS_MOD (11/13 실측 약 30 · 25)
QS_MOD = 12


def _px(row):
    p = getattr(row, "price", None) if row is not None else None
    return None if p is None else round(float(p), 4)


def in_sample(ticker) -> bool:
    """품질 미달 표본 — 티커로만 정해서 날이 바뀌어도 같은 종목이 계속 들어갑니다."""
    return zlib.crc32(str(ticker).encode("utf-8")) % QS_MOD == 0


def rules() -> dict:
    """그날 판정에 쓴 규칙 값 — 문턱을 바꾼 날을 기록에서 가려내려고."""
    import buffett_kr  # noqa: PLC0415

    return {"v": SCHEMA, "q_us": config.DISCOVER_QUALITY_MIN,
            "q_kr": [config.KR_QUALITY_MAX_FAIL, config.KR_QUALITY_MIN_KNOWN],
            "g": growth.GROWTH_MIN_PASS, "peg": [growth.PEG_GOOD, growth.PEG_OK],
            "eps": config.EPS_DOWN_WARN, "flat": funnel.EPS_FLAT,
            "sr": buffett.SCREEN_REV, "kr": buffett_kr.KR_REV}


def _gates_stable(c, fr: dict, gr: dict) -> str:
    """안정형 관문 — 걸린 것 전부 (integrate.build 와 같은 조건)."""
    return (("p" if c.lamps.get("price") == integrate.RED else "")
            + ("e" if funnel.eps_down((fr or {}).get("f")) else "")
            + ("t" if (gr or {}).get("td") else ""))


def _gates_growth(c) -> str:
    """성장형 관문 — 걸린 것 전부 (integrate.build_growth 와 같은 조건)."""
    return (("p" if c.lamps.get("price") == integrate.RED else "")
            + ("e" if c.lamps.get("eps") == integrate.RED else ""))


def snapshot(screens: list, frows: dict, chart_rows: dict, market: str,
             semis: set = (), new: set = ()) -> dict:
    """한 시장의 그날 기록. s · g 는 화면과 같은 integrate 규칙(예전 형식 그대로)."""
    cands = integrate.build(screens, frows, chart_rows, {}, semis, new, market=market)
    stable, s_out = integrate.split(cands)
    gcands = integrate.build_growth(screens, frows, chart_rows, semis, new, market,
                                    {c.ticker for c in stable})
    growth_c, g_out = integrate.split(gcands)
    by_t = {s.get("t"): s for s in screens or [] if isinstance(s, dict)}
    snap = {
        "s": [[c.ticker, c.greens, int(c.timing), _px(chart_rows.get(c.ticker))] for c in stable],
        "g": [[c.ticker, c.greens, int(c.timing), _px(chart_rows.get(c.ticker)),
               None if c.price_gap is None else round(c.price_gap, 3)] for c in growth_c],
        "sl": [c.lamps.get("price", "-") + c.lamps.get("eps", "-") for c in stable],
        "gl": [c.lamps.get("price", "-") + c.lamps.get("eps", "-") for c in growth_c],
    }
    x: dict[str, list] = {}
    for c in s_out:
        code = _gates_stable(c, frows.get(c.ticker), (by_t.get(c.ticker) or {}).get("gr"))
        x.setdefault(code or "?", []).append(c.ticker)
    gx: dict[str, list] = {}
    for c in g_out:
        gx.setdefault(_gates_growth(c) or "?", []).append(c.ticker)
    qh, qs, gn, n_ok = [], [], [], 0
    near = growth.GROWTH_MIN_PASS - 1
    for s in screens or []:
        if not isinstance(s, dict):
            continue
        gr = s.get("gr") or {}
        if gr and growth.score(gr, market)[0] == near:
            gn.append(s.get("t"))
        sc = buffett.from_summary(s)
        if sc is None or not sc.ok:
            continue
        n_ok += 1
        if buffett.quality_pass(sc, market):
            continue
        if integrate.held_back(sc, market):
            qh.append(sc.ticker)
        elif in_sample(sc.ticker):
            qs.append(sc.ticker)
    snap.update({"x": x, "gx": gx, "qh": sorted(qh), "gn": sorted(t for t in gn if t),
                 "qs": sorted(qs),
                 "n": {"u": n_ok, "q": len(cands), "h": len(qh), "gp": len(gcands)}})
    return snap


def tickers(snap: dict) -> set:
    """기록에 나온 모든 티커 (업종 표를 채울 때)."""
    out = {r[0] for k in ("s", "g") for r in snap.get(k) or [] if r}
    for k in ("x", "gx"):
        for lst in (snap.get(k) or {}).values():
            out.update(lst)
    for k in ("qh", "gn", "qs"):
        out.update(snap.get(k) or [])
    return out


def append(history: dict | None, day: str, made: float, snaps: dict,
           keep: int = KEEP_DAYS, rules_: dict | None = None,
           sec: dict | None = None) -> dict:
    """지난 기록에 오늘 줄을 붙임 (같은 날이면 바꿈). snaps = {"us": {...}, "kr": {...}}.

    rules_ = 그날 규칙 값(rules()) · sec = {"us": {티커: 업종}, …} — 지난 업종 표에 합칩니다.
    """
    days = [d for d in ((history or {}).get("days") or [])
            if isinstance(d, dict) and d.get("d") != day]
    # 오늘 한 시장만 수집했으면 다른 시장은 같은 날 지난 줄에서 이어받음
    prev_today = next((d for d in ((history or {}).get("days") or [])
                       if isinstance(d, dict) and d.get("d") == day), {})
    row = {"d": day, "t": int(made)}
    if rules_ is not None:
        row["r"] = rules_
    elif prev_today.get("r") is not None:
        row["r"] = prev_today["r"]
    for m in ("us", "kr"):
        if snaps.get(m) is not None:
            row[m] = snaps[m]
        elif prev_today.get(m) is not None:
            row[m] = prev_today[m]
    days.append(row)
    days.sort(key=lambda d: d["d"])
    out = {"version": 1, "made": int(made), "days": days[-keep:]}
    old_sec = (history or {}).get("sec")
    if isinstance(old_sec, dict) or sec:
        merged = {m: dict(v) for m, v in (old_sec or {}).items() if isinstance(v, dict)}
        for m, v in (sec or {}).items():
            merged.setdefault(m, {}).update({k: x for k, x in (v or {}).items() if x})
        out["sec"] = merged
    return out


def summary(history: dict | None, market: str) -> tuple[int, str]:
    """(기록된 날 수, 첫 날짜) — 화면 한 줄용."""
    days = [d for d in ((history or {}).get("days") or []) if isinstance(d, dict) and d.get(market)]
    return len(days), (days[0]["d"] if days else "")
