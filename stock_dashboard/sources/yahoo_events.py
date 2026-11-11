"""
야후 — 배당 이력·다음 배당 일정, 실적 발표(EPS 추정 vs 실제).

yfinance 의 세 가지를 씁니다:
  Ticker.dividends            배당락일(ex-date) 로 색인된 주당 배당금
  Ticker.calendar             다음 배당락일 'Ex-Dividend Date', 지급일
                              'Dividend Date' (미국 종목 위주, 없을 수 있음)
  Ticker.get_earnings_dates   'EPS Estimate' · 'Reported EPS' · 'Surprise(%)'
                              (열 이름이 버전마다 조금씩 달라 부분 일치로 찾음)

한국 종목(005930.KS)도 dividends 는 대체로 오지만 calendar 와 실적
추정치는 비는 경우가 많습니다 — 한국 실적은 네이버 쪽을 씁니다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .yahoo import _import_yfinance, _num


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
        if value is None:
            return ""
    text = str(value)
    return text[:10] if len(text) >= 10 and text[4] == "-" else ""


def fetch_dividends(symbol: str) -> dict:
    """{"history": [(ex_date, 금액)…] 오래된 순, "ex_date", "pay_date", "error"}"""
    yf = _import_yfinance()
    out = {"history": [], "ex_date": "", "pay_date": "", "error": ""}
    try:
        t = yf.Ticker(symbol)
        series = t.dividends
        hist = []
        for idx, val in getattr(series, "items", lambda: [])():
            amt = _num(val)
            day = _iso(getattr(idx, "date", lambda: idx)())
            if amt and day:
                hist.append((day, amt))
        out["history"] = hist[-30:]
        try:
            cal = t.calendar
            if hasattr(cal, "to_dict") and not isinstance(cal, dict):
                cal = {k: v for k, v in cal.to_dict().items()}
            if isinstance(cal, dict):
                out["ex_date"] = _iso(cal.get("Ex-Dividend Date"))
                out["pay_date"] = _iso(cal.get("Dividend Date"))
        except Exception:  # noqa: BLE001 — 일정이 없어도 이력은 씁니다
            pass
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _col(columns, *parts: str):
    for c in columns:
        low = str(c).lower().replace(" ", "")
        if all(p in low for p in parts):
            return c
    return None


def fetch_earnings(symbol: str, limit: int = 12) -> dict:
    """{"rows": [{"date", "estimate", "reported", "surprise"}…] 최신순, "error"}"""
    yf = _import_yfinance()
    try:
        t = yf.Ticker(symbol)
        getter = getattr(t, "get_earnings_dates", None)
        df = getter(limit=limit) if getter else t.earnings_dates
        if df is None or getattr(df, "empty", True):
            return {"rows": [], "error": "야후에 실적 일정이 없습니다"}
        cols = list(df.columns)
        est, rep, sur = (_col(cols, "estimate"), _col(cols, "reported"),
                         _col(cols, "surprise"))
        rows = []
        for idx, rec in df.iterrows():
            day = _iso(getattr(idx, "date", lambda: idx)())
            if not day:
                continue
            rows.append({
                "date": day,
                "estimate": _num(rec.get(est)) if est else None,
                "reported": _num(rec.get(rep)) if rep else None,
                "surprise": _num(rec.get(sur)) if sur else None,
            })
        rows.sort(key=lambda r: r["date"], reverse=True)
        return {"rows": rows, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "error": f"{type(exc).__name__}: {exc}"}


def fetch_many(fn, symbols: list[str], workers: int = 4) -> dict[str, dict]:
    symbols = [s for s in dict.fromkeys(symbols) if s]
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as pool:
        return dict(zip(symbols, pool.map(fn, symbols)))
