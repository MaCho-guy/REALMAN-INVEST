"""
실적 서프라이즈 — 발표된 실적이 발표 전 시장 추정치(컨센서스)와 얼마나 달랐나.

미국  야후의 'EPS Estimate' 와 'Reported EPS'. 서프라이즈 % 는 야후 값이
      있으면 그것을, 없으면 (실제 − 추정) ÷ |추정| 으로 직접 계산합니다.
      EPS 는 대개 조정(non-GAAP) 기준이라 손익계산서의 EPS 와 다를 수
      있습니다.

한국  네이버 분기 실적표(억원). 문제는 **발표 전 컨센서스가 사라진다**는
      것입니다 — 실적이 나오면 그 분기 칸의 (E) 가 실제값으로 바뀝니다.
      그래서 이 서버가 (E) 를 볼 때마다 기록해 두고(ConsensusStore), 같은
      분기가 실제값으로 바뀌면 기록과 비교합니다. 서버가 재시작되면 기록이
      지워지므로 **처음에는 서프라이즈가 비어 있는 게 정상**이고, 다음
      발표부터 채워집니다. 그 사이에도 전년 동기 대비(YoY)·직전 분기
      대비(QoQ)와 다음 분기 컨센서스는 보여줍니다.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
from dataclasses import dataclass, field


def surprise_pct(actual: float | None, estimate: float | None) -> float | None:
    if actual is None or estimate is None or estimate == 0:
        return None
    return (actual - estimate) / abs(estimate) * 100


def change_pct(now: float | None, before: float | None) -> float | None:
    """증감률. 적자 전환·흑자 전환은 %가 의미 없어 None (화면에서 말로)."""
    if now is None or before is None or before <= 0:
        # 기준이 0 이하(적자)면 % 가 뜻을 잃습니다 — −1억 → −160억 이
        # '−15,900%' 로 찍힙니다. 그런 칸은 말(적자 지속·흑자 전환)로 적습니다.
        return None
    if now < 0:
        return None
    return (now - before) / abs(before) * 100


def turn_label(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return ""
    if before < 0 <= now:
        return "흑자 전환"
    if before >= 0 > now:
        return "적자 전환"
    if before < 0 and now < 0:
        return "적자 지속"
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# 미국
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class UsQuarter:
    date: str
    estimate: float | None
    reported: float | None
    surprise: float | None


@dataclass
class UsEarnings:
    symbol: str
    name: str
    reported: list[UsQuarter] = field(default_factory=list)   # 최신순 최대 4
    next_date: str = ""
    next_estimate: float | None = None
    error: str = ""
    held: bool = False

    @property
    def beats(self) -> int:
        return sum(1 for q in self.reported if (q.surprise or 0) > 0)

    @property
    def misses(self) -> int:
        return sum(1 for q in self.reported if (q.surprise or 0) < 0)


def us_view(symbol: str, name: str, rows, today: dt.date, *, error: str = "",
            held: bool = False) -> UsEarnings:
    view = UsEarnings(symbol=symbol, name=name, error=error, held=held)
    past, future = [], []
    for r in rows or []:
        day = r.get("date") or ""
        if not day:
            continue
        if r.get("reported") is not None and day <= today.isoformat():
            sur = r.get("surprise")
            if sur is None:
                sur = surprise_pct(r.get("reported"), r.get("estimate"))
            past.append(UsQuarter(day, r.get("estimate"), r.get("reported"), sur))
        elif day >= today.isoformat():
            future.append(r)
    past.sort(key=lambda q: q.date, reverse=True)
    view.reported = past[:4]
    if future:
        nxt = min(future, key=lambda r: r["date"])
        view.next_date, view.next_estimate = nxt["date"], nxt.get("estimate")
    return view


# ──────────────────────────────────────────────────────────────────────────────
# 한국 — 컨센서스 기록
# ──────────────────────────────────────────────────────────────────────────────

class ConsensusStore:
    """(종목, 분기) 의 마지막으로 본 컨센서스. JSON 파일 하나.

    여러 스레드가 동시에 쓸 수 있어 잠금을 겁니다. 파일이 깨져 있으면
    빈 기록으로 시작합니다 (기록은 있으면 좋은 것이지 필수가 아닙니다).
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def record(self, code: str, period: str, values: dict, seen: str) -> None:
        if not any(v is not None for v in values.values()):
            return
        with self._lock:
            data = self._load()
            data.setdefault(code, {})[period] = {"values": values, "seen": seen}
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError:
                pass

    def get(self, code: str, period: str) -> dict | None:
        return self._load().get(code, {}).get(period)


@dataclass
class KrEarnings:
    code: str
    name: str
    latest: object = None             # naver_extra.Period (실제)
    yoy: dict[str, float | None] = field(default_factory=dict)
    qoq: dict[str, float | None] = field(default_factory=dict)
    turns: dict[str, str] = field(default_factory=dict)
    nxt: object = None                # 다음 (E) Period
    surprise: dict[str, float | None] = field(default_factory=dict)
    surprise_seen: str = ""           # 비교한 컨센서스를 본 날
    filing: object = None             # 최근 잠정실적 공시 (MarketFiling)
    error: str = ""
    held: bool = False


METRICS = ("매출액", "영업이익", "순이익")


def kr_view(code: str, name: str, periods, *, store: ConsensusStore | None = None,
            today: dt.date | None = None, error: str = "", held: bool = False,
            filing=None) -> KrEarnings:
    view = KrEarnings(code=code, name=name, error=error, held=held, filing=filing)
    periods = sorted(periods or [], key=lambda p: p.key)
    actual = [p for p in periods if not p.consensus
              and any(v is not None for v in p.values.values())]
    est = [p for p in periods if p.consensus]
    today = today or dt.date.today()
    if store is not None:
        for p in est:
            store.record(code, p.key, dict(p.values), today.isoformat())
    if est:
        view.nxt = est[0]
    if not actual:
        return view
    latest = actual[-1]
    view.latest = latest
    by_key = {p.key: p for p in actual}
    k = latest.key
    prev_year = (f"{int(k[:4]) - 1}{k[4:]}" if len(k) >= 6 and k[:4].isdigit()
                 else "")
    ly = by_key.get(prev_year)
    pq = actual[-2] if len(actual) >= 2 else None
    for m in METRICS:
        now = latest.values.get(m)
        view.yoy[m] = change_pct(now, ly.values.get(m)) if ly else None
        view.qoq[m] = change_pct(now, pq.values.get(m)) if pq else None
        base = ly or pq
        view.turns[m] = turn_label(now, base.values.get(m)) if base else ""
    if store is not None:
        snap = store.get(code, latest.key)
        if snap:
            vals = snap.get("values") or {}
            view.surprise = {m: surprise_pct(latest.values.get(m), vals.get(m))
                             for m in METRICS}
            view.surprise_seen = snap.get("seen", "")
    return view
