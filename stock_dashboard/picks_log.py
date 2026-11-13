"""후보 기록 (2026-11-13) — 규칙이 맞는지 나중에 데이터로 보려고 날마다 후보를 쌓습니다.

사용자: "또 뭘 고치면 좋을까" → 제안 1순위(승인). 오늘 하루에만 품질 문턱 · 등 개수 ·
성장형 기준을 여러 번 바꿨는데 근거는 '논리적으로 맞아 보인다' 였습니다. 후보에 오른
종목이 이후 4주 · 12주 동안 시장 대비 어땠는지를 보려면 그날의 목록과 가격이 남아 있어야
합니다.

파일: data 브랜치 `picks_history.json` — 수집기가 지난 파일을 이어받아 붙입니다.
    {"version": 1, "made": …, "days": [
        {"d": "2026-11-13", "t": 수집 시각(epoch),
         "us": {"s": [[티커, 충족 수, 타이밍 1/0, 종가], …],     # 안정형 후보 (순서대로)
                "g": [[티커, 충족 수, 타이밍, 종가, PEG], …]},   # 성장형 후보
         "kr": {…}}, …]}
같은 날 여러 번 수집하면 마지막 것으로 바꿉니다. 최근 KEEP_DAYS 일만 둡니다.
"""
from __future__ import annotations

import integrate

KEEP_DAYS = 500


def _px(row):
    p = getattr(row, "price", None) if row is not None else None
    return None if p is None else round(float(p), 4)


def snapshot(screens: list, frows: dict, chart_rows: dict, market: str,
             semis: set = (), new: set = ()) -> dict:
    """한 시장의 그날 후보 — {"s": 안정형, "g": 성장형}. 화면과 같은 integrate 규칙."""
    stable = integrate.split(integrate.build(screens, frows, chart_rows, {}, semis, new,
                                             market=market))[0]
    growth_c = integrate.split(integrate.build_growth(screens, frows, chart_rows, semis, new,
                                                      market, {c.ticker for c in stable}))[0]
    return {
        "s": [[c.ticker, c.greens, int(c.timing), _px(chart_rows.get(c.ticker))] for c in stable],
        "g": [[c.ticker, c.greens, int(c.timing), _px(chart_rows.get(c.ticker)),
               None if c.price_gap is None else round(c.price_gap, 3)] for c in growth_c],
    }


def append(history: dict | None, day: str, made: float, snaps: dict,
           keep: int = KEEP_DAYS) -> dict:
    """지난 기록에 오늘 줄을 붙임 (같은 날이면 바꿈). snaps = {"us": {...}, "kr": {...}}."""
    days = [d for d in ((history or {}).get("days") or [])
            if isinstance(d, dict) and d.get("d") != day]
    # 오늘 한 시장만 수집했으면 다른 시장은 같은 날 지난 줄에서 이어받음
    prev_today = next((d for d in ((history or {}).get("days") or [])
                       if isinstance(d, dict) and d.get("d") == day), {})
    row = {"d": day, "t": int(made)}
    for m in ("us", "kr"):
        if snaps.get(m) is not None:
            row[m] = snaps[m]
        elif prev_today.get(m) is not None:
            row[m] = prev_today[m]
    days.append(row)
    days.sort(key=lambda d: d["d"])
    return {"version": 1, "made": int(made), "days": days[-keep:]}


def summary(history: dict | None, market: str) -> tuple[int, str]:
    """(기록된 날 수, 첫 날짜) — 화면 한 줄용."""
    days = [d for d in ((history or {}).get("days") or []) if isinstance(d, dict) and d.get(market)]
    return len(days), (days[0]["d"] if days else "")
