"""주요 일정 — 앞으로 몇 주 동안 시장에 있는 날짜들.

2026-11-11 추가. 무엇이 언제 있는지를 한곳에 모읍니다:

  통화정책  FOMC · 한국은행 금통위 (통화정책방향 결정회의)  — 공식 발표 일정 (아래 표)
  지표 발표  미국 CPI · PPI · 고용 · PCE · GDP                — FRED 발표 일정 (API)
  만기      한국 옵션 매월 둘째 목요일 · 3·6·9·12월 동시만기
            미국 옵션 매월 셋째 금요일 · 3·6·9·12월 쿼드러플 위칭  — 규칙으로 계산
  휴장      KRX · NYSE                                          — 거래소 공지 (아래 표)
  실적      내 종목의 실적 발표 예정일                          — 야후 시세에 딸려 옴

**표의 출처** (2026-11-11 확인):
  FOMC   federalreserve.gov/monetarypolicy/fomccalendars.htm (2027 은 '잠정')
  금통위 한국은행 2027년 금통위 정기회의 개최 예정일 의결(2026-10-29) 보도,
         2026년 일정은 같은 해 발표분
  휴장일 KRX · NYSE 공지를 정리한 자료 (etfshopping.com/guide/market-hours)
날짜가 바뀌면 이 표를 고칩니다. 표에 없는 해는 '일정 없음' 으로 비웁니다 —
규칙으로 짐작해 채우지 않습니다 (연준·한은은 해마다 날짜를 따로 정합니다).

순수 파이썬 — 스트림릿·네트워크 없음. FRED 응답 해석도 여기 있고, 받기는
sources/fred.py 가 합니다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# ── 공식 일정 표 ──────────────────────────────────────────────────────────────

#: FOMC — (결정일, 경제전망(SEP) 포함). 결정은 회의 둘째 날 미 동부 14:00.
FOMC = (
    ("2026-01-28", False), ("2026-03-18", True), ("2026-04-29", False),
    ("2026-06-17", True), ("2026-07-29", False), ("2026-09-16", True),
    ("2026-10-28", False), ("2026-12-09", True),
    ("2027-01-27", False), ("2027-03-17", True), ("2027-04-28", False),
    ("2027-06-09", True), ("2027-07-28", False), ("2027-09-15", True),
    ("2027-10-27", False), ("2027-12-08", True),
)
FOMC_TENTATIVE_FROM = "2027-01-01"

#: 한국은행 통화정책방향 결정회의 (기준금리 결정일).
BOK = (
    "2026-01-15", "2026-02-26", "2026-04-10", "2026-05-28",
    "2026-07-16", "2026-08-27", "2026-10-22", "2026-11-26",
    "2027-01-14", "2027-02-25", "2027-04-09", "2027-05-27",
    "2027-07-15", "2027-08-26", "2027-10-15", "2027-11-25",
)

#: 평일 휴장일 (주말에 걸친 공휴일은 적지 않습니다).
KRX_HOLIDAYS = {
    "2026-01-01": "신정", "2026-02-16": "설날", "2026-02-17": "설날",
    "2026-02-18": "설날", "2026-03-02": "삼일절 대체휴일", "2026-05-01": "노동절",
    "2026-05-05": "어린이날", "2026-05-25": "부처님오신날 대체휴일",
    "2026-06-03": "전국동시지방선거", "2026-07-17": "제헌절",
    "2026-08-17": "광복절 대체휴일", "2026-09-24": "추석", "2026-09-25": "추석",
    "2026-10-05": "개천절 대체휴일", "2026-10-09": "한글날", "2026-12-25": "성탄절",
    "2026-12-31": "연말 휴장",
    "2027-01-01": "신정", "2027-02-08": "설날", "2027-02-09": "설날 대체휴일",
    "2027-03-01": "삼일절", "2027-05-03": "노동절 대체휴일", "2027-05-05": "어린이날",
    "2027-05-13": "부처님오신날", "2027-07-19": "제헌절 대체휴일",
    "2027-08-16": "광복절 대체휴일", "2027-09-14": "추석", "2027-09-15": "추석",
    "2027-09-16": "추석", "2027-10-04": "개천절 대체휴일",
    "2027-10-11": "한글날 대체휴일", "2027-12-27": "성탄절 대체휴일",
    "2027-12-31": "연말 휴장",
}
NYSE_HOLIDAYS = {
    "2026-01-01": "New Year's Day", "2026-01-19": "MLK Day",
    "2026-02-16": "Presidents' Day", "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day", "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (대체)", "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving", "2026-12-25": "Christmas",
    "2027-01-01": "New Year's Day", "2027-01-18": "MLK Day",
    "2027-02-15": "Presidents' Day", "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day", "2027-06-18": "Juneteenth (대체)",
    "2027-07-05": "Independence Day (대체)", "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving", "2027-12-24": "Christmas (대체)",
}
NYSE_EARLY_CLOSE = {
    "2026-11-27": "추수감사절 다음 날 (뉴욕 13:00 마감)",
    "2026-12-24": "크리스마스 이브 (뉴욕 13:00 마감)",
    "2027-11-26": "추수감사절 다음 날 (뉴욕 13:00 마감)",
}
#: 표가 덮는 마지막 날. 이 뒤로는 휴장일을 모르므로 만기일을 계산하지 않습니다.
TABLE_END = "2027-12-31"

#: FRED 발표 — (release_id, 화면 이름, 이름 확인용 낱말, 중요도).
#: release_id 는 FRED 의 발표 묶음 번호. 응답의 release_name 에 낱말이 없으면
#: '이름 불일치' 로 표시해 번호가 틀렸는지 드러나게 합니다.
FRED_RELEASES = (
    (10, "미국 CPI", "consumer price", 3),
    (50, "미국 고용 (비농업)", "employment situation", 3),
    (46, "미국 PPI", "producer price", 2),
    (54, "미국 PCE (개인소득·지출)", "personal income", 3),
    (53, "미국 GDP", "gross domestic product", 2),
)

KIND_LABEL = {"policy": "통화정책", "data": "지표", "expiry": "만기",
              "holiday": "휴장", "earnings": "실적", "early": "조기 마감"}
MARKET_LABEL = {"kr": "한국", "us": "미국"}


@dataclass
class Event:
    date: str                 # YYYY-MM-DD (그 나라 날짜)
    market: str               # kr | us
    kind: str                 # policy | data | expiry | holiday | earnings | early
    title: str
    note: str = ""
    importance: int = 2       # 3 = 굵게
    source: str = ""
    tentative: bool = False

    @property
    def day(self) -> dt.date:
        return dt.date.fromisoformat(self.date)


# ── 계산 ─────────────────────────────────────────────────────────────────────

def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """그 달의 n번째 요일 (weekday: 월=0 … 일=6)."""
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def previous_trading_day(d: dt.date, holidays: dict) -> dt.date:
    """d 가 주말·휴장이면 그 앞 거래일."""
    while d.weekday() >= 5 or d.isoformat() in holidays:
        d -= dt.timedelta(days=1)
    return d


def expiry_events(start: dt.date, end: dt.date) -> list[Event]:
    """옵션 만기일. 휴장일과 겹치면 앞 거래일로 당깁니다.

    한국: KOSPI200 옵션 매월 둘째 목요일, 3·6·9·12월은 선물도 같이 끝나는 동시만기.
    미국: 월물 옵션 매월 셋째 금요일, 3·6·9·12월은 지수 선물·옵션이 함께 끝나는
          쿼드러플 위칭.
    휴장일 표가 없는 해(TABLE_END 이후)는 계산하지 않습니다.
    """
    out: list[Event] = []
    last = min(end, dt.date.fromisoformat(TABLE_END))
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= last:
        quarter = m in (3, 6, 9, 12)
        kr = previous_trading_day(nth_weekday(y, m, 3, 2), KRX_HOLIDAYS)
        us = previous_trading_day(nth_weekday(y, m, 4, 3), NYSE_HOLIDAYS)
        for d, mk, title, note in (
            (kr, "kr", "동시만기 (선물·옵션)" if quarter else "옵션 만기",
             "KOSPI200 — 매월 둘째 목요일"),
            (us, "us", "쿼드러플 위칭" if quarter else "옵션 만기",
             "월물 옵션 — 매월 셋째 금요일"),
        ):
            if start <= d <= last:
                out.append(Event(d.isoformat(), mk, "expiry", title, note,
                                 3 if quarter else 1, "규칙으로 계산"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def table_events(start: dt.date, end: dt.date) -> list[Event]:
    """공식 일정 표 → 기간 안의 사건."""
    s, e = start.isoformat(), end.isoformat()
    out: list[Event] = []
    for d, sep in FOMC:
        if s <= d <= e:
            out.append(Event(d, "us", "policy", "FOMC 금리 결정",
                             "경제전망(SEP)·점도표 포함" if sep else "",
                             3, "연준", tentative=d >= FOMC_TENTATIVE_FROM))
    for d in BOK:
        if s <= d <= e:
            out.append(Event(d, "kr", "policy", "금통위 기준금리 결정", "",
                             3, "한국은행"))
    for table, mk in ((KRX_HOLIDAYS, "kr"), (NYSE_HOLIDAYS, "us")):
        for d, name in table.items():
            if s <= d <= e:
                out.append(Event(d, mk, "holiday", "휴장", name, 2, "거래소"))
    for d, name in NYSE_EARLY_CLOSE.items():
        if s <= d <= e:
            out.append(Event(d, "us", "early", "조기 마감", name, 1, "거래소"))
    return out


def parse_fred_dates(payload: object, start: dt.date, end: dt.date
                     ) -> tuple[list[Event], list[str]]:
    """FRED releases/dates 응답 → (사건, 경고).

    응답 모양: {"release_dates": [{"release_id": 10, "release_name": "...",
               "date": "2026-12-10"}, ...]}
    """
    warns: list[str] = []
    if not isinstance(payload, dict):
        return [], ["FRED 발표 일정 응답 형식이 예상과 다릅니다."]
    rows = payload.get("release_dates") or []
    want = {rid: (name, key, imp) for rid, name, key, imp in FRED_RELEASES}
    seen: set[tuple[int, str]] = set()
    out: list[Event] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            rid = int(row.get("release_id"))
        except (TypeError, ValueError):
            continue
        if rid not in want:
            continue
        d = str(row.get("date") or "")
        try:
            day = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if not (start <= day <= end) or (rid, d) in seen:
            continue
        seen.add((rid, d))
        name, key, imp = want[rid]
        rname = str(row.get("release_name") or "")
        if rname and key not in rname.lower():
            warns.append(f"FRED 발표 번호 {rid} 의 이름이 '{rname}' 입니다 "
                         f"({name} 이 아닐 수 있음)")
        out.append(Event(d, "us", "data", name, rname, imp, "FRED"))
    return out, sorted(set(warns))


def _as_date(value) -> dt.date | None:
    """epoch 초(야후 실제 응답) 또는 'YYYY-MM-DD'(데모·다른 경로) → 날짜."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                return None
    try:
        return dt.datetime.fromtimestamp(float(value), dt.timezone.utc).date()
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def earnings_events(quotes: dict, instruments, start: dt.date, end: dt.date
                    ) -> list[Event]:
    """내 종목 실적 발표 예정일 — 야후 시세의 extra['earnings_date'] (epoch 초)."""
    out: list[Event] = []
    for inst in instruments:
        q = quotes.get(inst.symbol)
        ts = (getattr(q, "extra", None) or {}).get("earnings_date") if q else None
        day = _as_date(ts)
        if day is None:
            continue
        if start <= day <= end:
            out.append(Event(day.isoformat(), "us" if inst.source == "yahoo" else "kr",
                             "earnings", f"{inst.name} 실적 발표", "예정일 (야후)",
                             3, "야후"))
    return out


def build(today: dt.date, days: int = 45, *, fred_payload=None, quotes=None,
          instruments=()) -> tuple[list[Event], list[str]]:
    """오늘부터 days 일 동안의 사건 (날짜 · 중요도 순)과 경고."""
    end = today + dt.timedelta(days=days)
    events = table_events(today, end) + expiry_events(today, end)
    warns: list[str] = []
    if fred_payload is not None:
        ev, warns = parse_fred_dates(fred_payload, today, end)
        events += ev
    if quotes:
        events += earnings_events(quotes, instruments, today, end)
    if end.isoformat() > TABLE_END:
        warns.append(f"{TABLE_END[:4]}년 뒤의 휴장일·통화정책 일정은 아직 표에 없습니다.")
    events.sort(key=lambda e: (e.date, -e.importance, e.market))
    return events, warns


def d_day(event: Event, today: dt.date) -> str:
    n = (event.day - today).days
    return "오늘" if n == 0 else (f"D-{n}" if n > 0 else f"D+{-n}")
