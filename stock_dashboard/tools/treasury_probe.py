"""
재무부 일별 수익률 곡선 — 배포 · 수집 환경에서 실제로 받아지는지 **재 보는** 도구.

    python stock_dashboard/tools/treasury_probe.py

화면 · 데이터 파일은 건드리지 않고 로그만 찍습니다 (survey 워크플로 market=treasury).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from sources import treasury  # noqa: E402


def main() -> int:
    today = dt.date.today()
    ym = f"{today.year:04d}{today.month:02d}"
    url = treasury.CSV_MONTH.format(ym=ym)
    t0 = time.time()
    resp = requests.get(url, headers=treasury.HEADERS, timeout=treasury.TIMEOUT)
    print(f"GET {url}\n  HTTP {resp.status_code} · {len(resp.content)} B · {time.time() - t0:.1f}초"
          f" · {resp.headers.get('content-type')}")
    print("  앞부분:", repr(resp.text[:400]))
    t0 = time.time()
    curves = treasury.fetch_recent(today)
    print(f"\nfetch_recent: {len(curves)}일 · {time.time() - t0:.1f}초")
    for c in curves[-4:]:
        print(" ", c.date, {k: c.rates.get(k) for k in ("2yr", "10yr", "3mo", "30yr")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
