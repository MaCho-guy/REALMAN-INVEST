"""전일 장 브리핑 — 한국장 · 미국장의 **마지막으로 끝난 거래일**을 숫자로.

2026-11-11 요청: "한국 및 미국장 전날 브리핑 관련 내용도 추가".

**무엇을 하는가.** 지수 · 업종 ETF · 보유 종목의 일봉에서 '마지막으로
마감한 날' 을 찾아, 그날 무엇이 얼마나 움직였는지를 문장 몇 줄로 엮습니다.

**무엇을 하지 않는가.** '왜' 움직였는지는 적지 않습니다. 숫자만으로는
이유를 알 수 없고, 그럴듯한 이유를 지어내면 틀린 설명이 사실처럼
보입니다. 이유는 아래에 붙는 마감 기사 제목과 증권사 시황 리포트(링크)
에서 읽습니다.

**'전일' 을 어떻게 정하나.** 장중에는 오늘 봉이 아직 움직이는 중이라
'끝난 날' 이 아닙니다. 그 시장의 현지 시각이 마감 뒤(여유 10분)가 아니면
오늘 봉을 버리고 그 앞 봉을 씁니다. 휴장일은 봉 자체가 없으므로 저절로
건너뜁니다.

순수 파이썬 — 스트림릿·네트워크 없음. 테스트가 시각을 바꿔 가며 돌립니다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

WEEKDAYS = "월화수목금토일"


@dataclass
class Move:
    label: str
    symbol: str
    close: float | None = None
    pct: float | None = None          # 전 거래일 대비 %
    delta: float | None = None        # 전 거래일 대비 값 (금리는 %p)
    kind: str = "pct"                 # pct | rate | level
    date: str = ""                    # 이 값의 거래일 (YYYY-MM-DD)

    @property
    def ok(self) -> bool:
        return self.close is not None and self.pct is not None

    @property
    def change_label(self) -> str:
        if not self.ok:
            return "—"
        if self.kind == "rate":
            return f"{self.delta:+.2f}%p"
        return f"{self.pct:+.1f}%"


@dataclass
class SessionBrief:
    market: str                       # kr | us
    title: str = ""                   # "한국장" / "미국장"
    session: str = ""                 # 거래일 YYYY-MM-DD
    in_progress: bool = False         # 지금 그 시장이 열려 있어 오늘 봉을 버렸는가
    indices: list[Move] = field(default_factory=list)
    extras: list[Move] = field(default_factory=list)
    sectors: list[Move] = field(default_factory=list)
    holdings: list[Move] = field(default_factory=list)
    lines: list[tuple[str, str]] = field(default_factory=list)   # (머리말, 문장)
    missing: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.session)

    @property
    def session_label(self) -> str:
        """'11월 10일(월)'."""
        try:
            d = dt.date.fromisoformat(self.session)
        except ValueError:
            return ""
        return f"{d.month}월 {d.day}일({WEEKDAYS[d.weekday()]})"


def completed(bars: list[tuple[str, float]], today: str, market_closed: bool
              ) -> list[tuple[str, float]]:
    """끝난 봉만. 오늘 봉은 장이 마감했을 때만 남깁니다. 미래 날짜는 버립니다."""
    out = [(d, c) for d, c in bars if c is not None and c > 0 and d <= today]
    if out and out[-1][0] == today and not market_closed:
        out = out[:-1]
    return out


def move_on(label: str, symbol: str, bars: list[tuple[str, float]],
            session: str, *, kind: str = "pct", exact: bool = True) -> Move:
    """session 날의 움직임. exact=False 면 그날 봉이 없을 때 그 전 마지막 봉."""
    upto = [(d, c) for d, c in bars if d <= session]
    if len(upto) < 2 or (exact and upto[-1][0] != session):
        return Move(label, symbol, kind=kind)
    (_pd, prev), (d, close) = upto[-2], upto[-1]
    return Move(label, symbol, close=close, pct=(close / prev - 1.0) * 100.0,
                delta=close - prev, kind=kind, date=d)


def _fmt_close(v: float) -> str:
    return f"{v:,.2f}" if v < 10_000 else f"{v:,.0f}"


def _join(moves: list[Move], *, with_close: bool = False) -> str:
    bits = []
    for m in moves:
        head = f"{m.label} {_fmt_close(m.close)}" if with_close else m.label
        bits.append(f"{head} ({m.change_label})" if with_close
                    else f"{head} {m.change_label}")
    return " · ".join(bits)


def compose_lines(b: SessionBrief) -> list[tuple[str, str]]:
    """숫자를 문장으로. 값이 없는 줄은 통째로 건너뜁니다."""
    lines: list[tuple[str, str]] = []
    idx = [m for m in b.indices if m.ok]
    if idx:
        lines.append(("지수", _join(idx, with_close=True)))
    sec = sorted([m for m in b.sectors if m.ok], key=lambda m: -m.pct)
    if sec:
        up = sum(1 for m in sec if m.pct > 0)
        k = min(3, len(sec) // 2) or 1
        text = f"업종 ETF {len(sec)}개 중 {up}개 상승"
        strong = [m for m in sec[:k] if m.pct > 0]
        weak = [m for m in sec[-k:][::-1] if m.pct < 0]
        if strong:
            text += f" · 강한 쪽 {_join(strong)}"
        if weak:
            text += f" · 약한 쪽 {_join(weak)}"
        lines.append(("업종", text))
    hold = sorted([m for m in b.holdings if m.ok], key=lambda m: -abs(m.pct))
    if hold:
        lines.append(("내 종목", _join(hold[:5])
                      + (f" 외 {len(hold) - 5}종목" if len(hold) > 5 else "")))
    ext = [m for m in b.extras if m.ok]
    if ext:
        lines.append(("환율 · 금리", " · ".join(
            f"{m.label} {_fmt_close(m.close)}{'%' if m.kind == 'rate' else ''}"
            f" ({m.change_label})" for m in ext)))
    return lines


def build(market: str, spec: dict, bars: dict[str, list[tuple[str, float]]],
          now: dt.datetime, errors: dict[str, str] | None = None) -> SessionBrief:
    """spec: {"title","tz","cutoff":(시,분),"indices":[(심볼,이름)],
              "extras":[(심볼,이름,kind)],"sectors":[(심볼,이름)],
              "holdings":[(심볼,이름)]}.  now 는 시간대가 있는 시각."""
    errors = errors or {}
    brief = SessionBrief(market=market, title=spec.get("title", ""))
    local = now.astimezone(ZoneInfo(spec["tz"]))
    today = local.date().isoformat()
    h, m = spec["cutoff"]
    closed = (local.hour, local.minute) >= (h, m) or local.weekday() >= 5

    done: dict[str, list] = {s: completed(b, today, closed) for s, b in bars.items()}
    idx_dates = [done[s][-1][0] for s, _l in spec["indices"]
                 if done.get(s) and len(done[s]) >= 2]
    if not idx_dates:
        why = "; ".join(f"{s}: {errors[s]}" for s, _l in spec["indices"]
                        if errors.get(s)) or "지수 일봉을 받지 못했습니다"
        brief.error = why
        return brief
    brief.session = max(idx_dates)
    raw_last = [bars[s][-1][0] for s, _l in spec["indices"] if bars.get(s)]
    brief.in_progress = bool(raw_last) and max(raw_last) == today and not closed

    def collect(pairs, *, exact=True, kinds=None):
        out = []
        for i, (sym, label) in enumerate(pairs):
            mv = move_on(label, sym, done.get(sym) or [], brief.session,
                         kind=(kinds[i] if kinds else "pct"), exact=exact)
            out.append(mv)
            if not mv.ok:
                brief.missing.append(label)
        return out

    brief.indices = collect(spec["indices"])
    brief.sectors = collect(spec.get("sectors", ()))
    brief.holdings = collect(spec.get("holdings", ()))
    ex = spec.get("extras", ())
    # 환율·금리는 주식시장과 휴장일이 달라 '그날 봉' 을 고집하지 않습니다
    brief.extras = collect([(s, l) for s, l, _k in ex], exact=False,
                           kinds=[k for _s, _l, k in ex])
    brief.lines = compose_lines(brief)
    return brief
