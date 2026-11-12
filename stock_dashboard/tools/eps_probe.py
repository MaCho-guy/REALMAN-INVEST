"""
선행 EPS 추정 추이 — 야후가 수집기 환경에서 실제로 무엇을 주는지 **재 보는** 도구.

    python stock_dashboard/tools/eps_probe.py

2026-11-12 사용자 승인: "향후 12개월 선행 EPS 의 90일 변화" 를 판정 줄에 먼저 보인다.
만들기 전에 (1) 어떤 표가 오는지 (2) 한국 종목도 오는지 (3) 종목당 몇 초인지를
확인합니다. 화면 · 데이터 파일은 건드리지 않고 로그만 찍습니다.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOLS = ("MSFT", "AAPL", "NVDA", "KO", "BRK-B", "005930.KS", "000660.KS", "035420.KS")


def main() -> int:
    import yfinance as yf

    print("yfinance", getattr(yf, "__version__", "?"))
    for sym in SYMBOLS:
        t0 = time.time()
        tk = yf.Ticker(sym)
        print(f"\n== {sym}")
        for attr in ("eps_trend", "earnings_estimate", "eps_revisions"):
            try:
                df = getattr(tk, attr)
                if df is None or getattr(df, "empty", True):
                    print(f"  {attr}: 비어 있음")
                    continue
                print(f"  {attr}: 행 {list(df.index)} · 열 {list(df.columns)}")
                for idx in list(df.index):
                    row = df.loc[idx]
                    print("     ", idx, {c: (None if row[c] != row[c] else round(float(row[c]), 4))
                                         for c in df.columns if isinstance(row[c], (int, float))})
            except Exception as exc:  # noqa: BLE001
                print(f"  {attr}: 실패 — {type(exc).__name__}: {str(exc)[:90]}")
        try:
            info = tk.info or {}
            print("  info:", {k: info.get(k) for k in (
                "forwardEps", "trailingEps", "lastFiscalYearEnd", "nextFiscalYearEnd",
                "mostRecentQuarter", "currency", "financialCurrency")})
        except Exception as exc:  # noqa: BLE001
            print(f"  info: 실패 — {type(exc).__name__}: {str(exc)[:90]}")
        print(f"  걸린 시간 {time.time() - t0:.1f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
