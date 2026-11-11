"""
배당 캘린더 — 배당 이력으로 주기·최근 배당·다음 배당락일을 정리합니다.

다음 배당락일은 두 종류입니다:
  발표   야후 calendar 에 회사가 발표한 날짜가 있을 때 (미국 종목 위주)
  추정   없으면 최근 배당 간격의 중앙값을 마지막 배당락일에 더한 날짜.
         **추정은 일정이 아닙니다.** 미국 분기배당처럼 규칙적인 곳은 대개
         며칠 차이 안에서 맞지만, 한국은 2023년 제도 개선으로 배당기준일을
         주주총회 뒤로 옮길 수 있게 되어 작년 날짜로 추정하면 크게 틀릴 수
         있습니다 — 한국 추정치에는 그 경고를 붙입니다.

배당락일(ex-date) 은 '이날 사면 이번 배당을 못 받는 첫날' 입니다. 받으려면
그 **전 거래일까지** 사야 합니다.

시가배당률은 최근 12개월 배당 합 ÷ 현재가 입니다 (특별배당이 끼면 부풀려
보입니다).
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass


@dataclass
class DividendView:
    symbol: str
    name: str
    market: str                       # kr | us
    currency: str = ""
    freq: str = ""                    # 월 · 분기 · 반기 · 연 · 불규칙
    last_ex: str = ""
    last_amount: float | None = None
    ttm: float | None = None
    yield_pct: float | None = None
    next_ex: str = ""
    next_basis: str = ""              # 발표 | 추정
    pay_date: str = ""
    count: int = 0
    note: str = ""
    error: str = ""
    held: bool = False

    def days_to_next(self, today: dt.date) -> int | None:
        if not self.next_ex:
            return None
        return (dt.date.fromisoformat(self.next_ex) - today).days


def _freq_label(n_last_year: int, gap_days: float | None) -> str:
    if n_last_year >= 10:
        return "월"
    if n_last_year >= 3:
        return "분기"
    if n_last_year == 2:
        return "반기"
    if n_last_year == 1:
        return "연"
    if gap_days is not None and gap_days > 400:
        return "불규칙"
    return ""


def analyze(symbol: str, name: str, market: str, history, today: dt.date, *,
            announced_ex: str = "", pay_date: str = "", price: float | None = None,
            currency: str = "", error: str = "", held: bool = False) -> DividendView:
    """history 는 [(YYYY-MM-DD, 금액)] — 순서는 상관없습니다."""
    view = DividendView(symbol=symbol, name=name, market=market,
                        currency=currency, error=error, held=held,
                        pay_date=pay_date or "")
    hist = sorted((d, a) for d, a in (history or []) if d and a)
    view.count = len(hist)
    if not hist:
        if not error:
            view.note = "배당 이력 없음"
        return view
    dates = [dt.date.fromisoformat(d) for d, _a in hist]
    view.last_ex, view.last_amount = hist[-1]
    year_ago = today - dt.timedelta(days=365)
    recent = [a for (d, a), day in zip(hist, dates) if day > year_ago]
    view.ttm = sum(recent) if recent else None
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])][-4:]
    gap = statistics.median(gaps) if gaps else None
    view.freq = _freq_label(len(recent), gap)
    if price and view.ttm:
        view.yield_pct = view.ttm / price * 100

    if announced_ex and announced_ex >= today.isoformat():
        view.next_ex, view.next_basis = announced_ex, "발표"
    elif gap and 20 <= gap <= 400 and recent:
        guess = dates[-1] + dt.timedelta(days=round(gap))
        loops = 0
        while guess < today and loops < 4:
            guess += dt.timedelta(days=round(gap))
            loops += 1
        if guess >= today:
            view.next_ex, view.next_basis = guess.isoformat(), "추정"
    if view.next_basis == "추정" and market == "kr":
        view.note = "작년 날짜로 추정 — 기준일을 옮긴 회사는 크게 다를 수 있음"
    elif not recent:
        view.note = "최근 12개월 배당 없음"
    return view


def calendar_events(views, today: dt.date, end: dt.date) -> list:
    """일정 탭에 넣을 배당락 사건 (calendar_events.Event)."""
    import calendar_events as ce  # noqa: PLC0415

    out = []
    for v in views:
        if not v.next_ex:
            continue
        day = dt.date.fromisoformat(v.next_ex)
        if not (today <= day <= end):
            continue
        amt = (f" · 직전 {v.last_amount:,.{0 if v.market == 'kr' else 2}f}"
               f"{'원' if v.market == 'kr' else ' ' + (v.currency or 'USD')}"
               if v.last_amount else "")
        out.append(ce.Event(
            v.next_ex, v.market, "dividend", f"{v.name} 배당락",
            ("발표일 (야후)" if v.next_basis == "발표"
             else "추정 — 직전 간격으로 계산") + amt,
            3 if v.held else 2, "야후"))
    return out
