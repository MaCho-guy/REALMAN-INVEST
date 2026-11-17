"""
미국 재무부 일별 수익률 곡선 (Daily Treasury Par Yield Curve Rates) — 인증키 불필요.

왜 FRED 와 따로 받는가 (2026-11-17 사용자 승인 "그렇게 해줘"):
FRED 의 DGS2 · DGS10 은 연준 H.15 에서 오는데, H.15 의 국채 금리는 **바로 이
재무부 곡선을 옮겨 적은 값**입니다. 재무부는 그날 저녁(미 동부)에 올리고, H.15 ·
FRED 는 다음 영업일 오후에 올립니다. 그래서 같은 숫자를 하루 먼저 받을 수 있습니다.
(FRED 의 T10Y2Y 가 DGS10 보다 하루 앞서 있는 것도 이 곡선에서 바로 계산하기 때문.)

응답은 CSV 로, 최근 날짜가 맨 위입니다:

    Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr",...
    11/16/2026,4.31,...,4.90,...,5.14,...

**함정:** 칸 이름 · 순서가 해마다 바뀐 적이 있습니다(1.5 Month · 4 Mo 가 나중에 생김).
그래서 위치가 아니라 **이름**으로 읽고, 이름은 공백 · 대소문자를 무시하고 맞춥니다.
날짜는 MM/DD/YYYY. 빈 칸은 결측입니다.

이 모듈은 숫자만 돌려줍니다. 화면에 어떻게 붙일지는 macro.attach_treasury 가 정합니다.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

import requests

BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
#: 달 단위 CSV — 한 달 치(약 22줄)만 받습니다.
CSV_MONTH = (BASE + "/daily-treasury-rates.csv/all/{ym}"
             "?type=daily_treasury_yield_curve&field_tdr_date_value_month={ym}&page&_format=csv")
SOURCE = "미국 재무부 일별 수익률 곡선 (home.treasury.gov)"
TIMEOUT = 15
HEADERS = {"User-Agent": "stock-dashboard/1.0 (personal research)",
           "Accept": "text/csv,*/*;q=0.5"}


class TreasuryError(RuntimeError):
    pass


@dataclass
class Curve:
    """곡선 한 날짜 — {만기 이름: 금리(%)}."""

    date: dt.date
    rates: dict[str, float] = field(default_factory=dict)

    def get(self, name: str) -> float | None:
        return self.rates.get(_norm(name))


def _norm(name: str) -> str:
    """'2 Yr' · '2 yr' · '2Yr' → '2yr'."""
    return "".join(str(name).split()).lower()


def parse_csv(text: str) -> list[Curve]:
    """CSV → 날짜 오름차순 Curve 목록. 형식이 아니면 TreasuryError."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise TreasuryError("빈 응답입니다.")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or _norm(rows[0][0]) != "date" or len(rows[0]) < 3:
        raise TreasuryError(f"CSV 머리글이 다릅니다 (앞 60자: {text[:60]!r})")
    head = [_norm(h) for h in rows[0]]
    out: list[Curve] = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        try:
            day = dt.datetime.strptime(row[0].strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        rates = {}
        for name, cell in zip(head[1:], row[1:]):
            cell = cell.strip()
            if not cell or cell in ("N/A", "."):
                continue
            try:
                rates[name] = float(cell)
            except ValueError:
                continue
        if rates:
            out.append(Curve(day, rates))
    out.sort(key=lambda c: c.date)
    return out


def fetch_month(year: int, month: int, *, get=requests.get) -> list[Curve]:
    ym = f"{year:04d}{month:02d}"
    try:
        resp = get(CSV_MONTH.format(ym=ym), headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise TreasuryError(f"재무부 응답 없음 ({type(exc).__name__})") from exc
    if resp.status_code != 200:
        raise TreasuryError(f"재무부 HTTP {resp.status_code}")
    return parse_csv(resp.text)


def fetch_recent(today: dt.date | None = None, *, get=requests.get) -> list[Curve]:
    """이번 달 + 지난달 — 달 초에도 직전 값이 있게. 날짜 오름차순.

    한 달이 실패해도 다른 달이 있으면 그것을 돌려줍니다. 둘 다 없으면 TreasuryError.
    """
    today = today or dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1))
    curves: dict[dt.date, Curve] = {}
    errors = []
    for y, m in ((prev.year, prev.month), (today.year, today.month)):
        try:
            for c in fetch_month(y, m, get=get):
                curves[c.date] = c
        except TreasuryError as exc:
            errors.append(f"{y}-{m:02d}: {exc}")
    if not curves:
        raise TreasuryError("; ".join(errors) or "재무부 곡선이 비었습니다.")
    return [curves[d] for d in sorted(curves)]
