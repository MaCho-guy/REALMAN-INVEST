"""요약 — 휴대폰에서 10초 안에 보는 한 화면.

**이 화면에는 카드만 있습니다** (2026-11-19 구조 점검 → 사용자 승인). 전에는 섹터 막대 ·
후보 3 · 뉴스 5 · 일정 · 전일 장 · 신호 상세가 이 화면에 쌓여 휴대폰 6화면 길이였습니다.
이제 그것들은 각자 화면에만 있고, 여기에는 **한 줄씩**만 남깁니다 — 카드를 누르면
그 화면으로 갑니다.

    1. 내 종목        — 최근 7일 새 공시 · 실적 임박 · 급변
    2. 시장           — 한국: 섹터 온도 / 미국: 공포탐욕 + VIX 기간구조
    3. 메모리 사이클  — 국면 판정 기록 + DIO 방향
    4. 후보           — 몇 종목, 앞 셋
    5. 꼭 읽을 뉴스   — 몇 건, 내 종목이 걸렸나 (그 시장의 뉴스)
    6. 전일 장        — 마지막으로 마감한 날의 지수
    7. 다가오는 일정  — 가장 가까운 것

각 줄은 **지금 볼 필요가 있나 없나**를 먼저 말합니다. "조용합니다" 가 정상 상태이고,
맨 윗줄만 보고 앱을 닫을 수 있어야 합니다.

`Row.goto` 는 화면 이름이 아니라 **화면 key** 입니다 — 이름과 주소는 그리는 쪽이
config 에서 만듭니다 (메뉴를 옮겨도 안내가 낡지 않게).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 요약에 올릴 신호 최대 개수. 휴대폰 한 화면을 넘기지 않기 위한 상한입니다.
MAX_SIGNALS = 4


@dataclass
class Row:
    """요약 한 줄."""

    key: str
    title: str
    #: quiet(조용함) / watch(볼 것 있음) / alert(지금 확인) / unknown(데이터 없음)
    level: str = "quiet"
    headline: str = ""
    detail: str = ""
    #: 누르면 갈 화면의 key (config.TAB_ORDER 의 값). 이름 · 주소는 그리는 쪽이 만듭니다
    goto: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.level in ("watch", "alert")


LEVEL_LABEL = {
    "alert": "지금 확인",
    "watch": "볼 것 있음",
    "quiet": "조용함",
    "unknown": "데이터 없음",
}


@dataclass
class Summary:
    rows: list[Row] = field(default_factory=list)

    @property
    def attention_count(self) -> int:
        return sum(1 for r in self.rows if r.needs_attention)

    @property
    def all_quiet(self) -> bool:
        return self.attention_count == 0

    @property
    def attention_titles(self) -> list[str]:
        """볼 것이 있는 줄의 이름 — 급한 것(alert)이 앞."""
        order = {"alert": 0, "watch": 1}
        rows = sorted((r for r in self.rows if r.needs_attention),
                      key=lambda r: order.get(r.level, 2))
        return [r.title for r in rows]

    @property
    def verdict(self) -> str:
        """맨 위에 한 줄. 이것만 보고 닫을 수 있어야 합니다."""
        n = self.attention_count
        if n == 0:
            unknown = sum(1 for r in self.rows if r.level == "unknown")
            if unknown == len(self.rows):
                return "데이터를 받지 못했습니다 — 화면 위쪽 진단 패널에서 확인하십시오."
            return "지금 확인할 것이 없습니다."
        alerts = [r for r in self.rows if r.level == "alert"]
        if alerts:
            return f"{alerts[0].title} — {alerts[0].headline}"
        watch = [r for r in self.rows if r.level == "watch"]
        return f"{watch[0].title} — {watch[0].headline}"


# ──────────────────────────────────────────────────────────────────────────────
# 줄 만들기
# ──────────────────────────────────────────────────────────────────────────────

def _sig_text(sig) -> str:
    """'SK하이닉스 새 공시 4건' — 종목 이름 + 신호 제목의 앞부분.

    11/19 점검: 제목만 이어 붙여 "새 공시 4건 — … · 새 공시 4건 — …" 처럼 어느 종목인지
    없는 줄이 됐습니다."""
    title = str(getattr(sig, "title", "")).split(" — ")[0]
    if getattr(sig, "aggregate", False):
        return title
    name = getattr(getattr(sig, "inst", None), "name", "") or ""
    return f"{name} {title}".strip()


def row_holdings(urgent: list, soon: list, total: int) -> Row:
    """1. 내 종목에 생긴 일."""
    row = Row(key="holdings", title="내 종목", goto="holdings")

    if urgent:
        row.level = "alert"
        row.headline = f"지금 확인 {len(urgent)}건"
        row.detail = " · ".join(_sig_text(s) for s in urgent[:MAX_SIGNALS])
        if len(urgent) > MAX_SIGNALS:
            row.detail += f" 외 {len(urgent) - MAX_SIGNALS}건"
    elif soon:
        row.level = "watch"
        row.headline = f"이번 주 {len(soon)}건"
        row.detail = " · ".join(_sig_text(s) for s in soon[:MAX_SIGNALS])
        if len(soon) > MAX_SIGNALS:
            row.detail += f" 외 {len(soon) - MAX_SIGNALS}건"
    else:
        row.level = "quiet"
        row.headline = f"{total}종목 모두 조용함"
        row.detail = "최근 7일 새 공시 · 실적 임박 · 급변 없음"
    return row


def row_sentiment(fg, vix_state) -> Row:
    """2. 시장 분위기 — 공포탐욕 + VIX 기간구조."""
    row = Row(key="sentiment", title="시장 분위기", goto="macro")

    parts: list[str] = []
    level = "quiet"

    if fg is not None and fg.ok:
        parts.append(f"공포탐욕 {fg.score:,.0f} ({fg.band})")
        if fg.score < 25.0 or fg.score >= 75.0:
            level = "watch"
        if fg.extremes:
            names = ", ".join(c.label for c in fg.extremes[:2])
            row.detail = f"극단 지표: {names}"
    if vix_state is not None and vix_state.ok:
        parts.append(f"VIX {vix_state.spot:,.1f}")
        if vix_state.pct_5y is not None:
            parts.append(f"5년 중 {vix_state.pct_5y:,.0f}%")
        if vix_state.is_inverted:
            level = "alert"
            row.detail = (
                "VIX 기간구조가 역전됐습니다 — 2010년 이후 거래일의 7.7% 에만 "
                "나타난 상태입니다."
            )

    if not parts:
        row.level = "unknown"
        row.headline = "공포탐욕·VIX 를 받지 못했습니다"
        return row

    row.level = level
    row.headline = " · ".join(parts)
    if not row.detail:
        row.detail = (
            f"기간구조 {vix_state.structure}"
            if vix_state is not None and vix_state.ok else "세부 지표 7개는 매크로 화면"
        )
    return row


def _phase_bits(phase, trends: dict, today) -> tuple[str, str, list[str]]:
    """(국면 머리말, 올릴 수준, 세부 문구). phase 가 없거나 깨졌으면 ('', 'quiet', []).

    '전환 감시' 자체로는 수준을 올리지 않습니다 — 몇 주씩 이어지는 상태라
    올려 두면 요약 줄이 늘 '볼 것 있음' 이 되어 조용함의 뜻이 사라집니다.
    올리는 건 셋뿐입니다: 재판정 필요 · 공시가 기록과 달라짐 · 판정이 오래됨.
    """
    if phase is None or not getattr(phase, "ok", False):
        return "", "quiet", []
    import datetime as _dt

    import cycle_phase  # 요약이 다른 탭의 무거운 모듈을 먼저 부르지 않게 여기서

    today = today or _dt.date.today()
    main = phase.main_track
    status = phase.status
    head = f"{main.abbr} {main.short}" if main else ""
    if status != cycle_phase.STATUS_HOLD:
        head += f" ({status})"
    level = "quiet"
    details: list[str] = []
    if status == cycle_phase.STATUS_REJUDGE:
        level = "watch"
        details.append("체크리스트 재판정 대상 (재고 ③·④ 동시 점등 또는 ⑤)")
    diff = cycle_phase.disagreements(cycle_phase.cross_check(phase, trends or {}))
    if diff:
        level = "watch"
        details.append("공시가 판정 기록과 달라짐: " + ", ".join(f"{n}번" for n in diff))
    if phase.is_stale(today):
        level = "watch"
        details.append(f"국면 판정이 {phase.age_days(today)}일 전 기준 — 점검 필요")
    others = [t for t in phase.tracks if t.key != phase.checklist_track and t.phase >= 3]
    if others:
        details.append(" · ".join(f"{t.abbr} {t.short}" for t in others) + " 먼저 둔화")
    return head, level, details


def row_cycle(trends: dict, macro_readings: list, phase=None, today=None,
              *, phase_check: bool = True) -> Row:
    """3. 메모리 사이클 — 국면 판정 기록 + DIO 방향 + 반도체 생산·가격."""
    row = Row(key="cycle", title="메모리 사이클", goto="cycle")

    bits: list[str] = []
    level = "quiet"
    details: list[str] = []
    phase_head, phase_level, phase_details = _phase_bits(
        phase, trends if phase_check else {}, today)

    rising = []
    for trend in (trends or {}).values():
        if not getattr(trend, "quarters", None):
            continue
        if trend.dio_rising_quarters >= 2:
            rising.append(trend.corp_name)
        if trend.dio_qoq_change is not None and trend.latest is not None:
            bits.append(f"{trend.corp_name} DIO {trend.dio_qoq_change:+.0f}일")
    if rising:
        level = "watch"
        details.append(f"DIO 2분기 연속 상승: {', '.join(rising)}")

    for reading in macro_readings or []:
        if reading.spec.group != "semi" or not reading.ok:
            continue
        bits.append(f"{reading.spec.name.split(' (')[0]} {reading.value_label}")

    if phase_level == "watch":
        level = "watch"
    details = phase_details + details

    if not bits and not phase_head:
        row.level = "unknown"
        row.headline = "재고·반도체 지표를 받지 못했습니다"
        row.detail = "DART 인증키가 필요하거나 조회가 실패했습니다"
        return row

    row.level = level
    # 국면이 맨 앞 — 휴대폰에서 첫 단어만 보고도 어느 국면인지 알게
    row.headline = " · ".join(([phase_head] if phase_head else [])
                              + bits[:2 if phase_head else 3])
    if not bits:
        details.append("재고·반도체 지표는 받지 못했습니다")
    row.detail = (" · ".join(details) if details
                  else "레이어 2(재고)와 레이어 1·4(생산·가격)를 교차해야 판정됩니다")
    return row


def row_picks(picks=None, when: str = "", market: str = "kr") -> Row:
    """4. 후보 — 몇 종목이고 앞 셋이 누구인가. 목록은 후보 화면에만 있습니다.

    picks = 관문을 넘은 후보(순서대로). None 이면 아직 못 읽은 것(파일 없음)."""
    row = Row(key="picks", title="후보", goto="picks")
    if picks is None:
        row.level = "unknown"
        row.headline = "후보 파일을 아직 못 읽었습니다"
        row.detail = "다음 수집(06:43 · 15:43) 뒤에 나옵니다"
        return row
    names = [str(getattr(c, "name", "") or getattr(c, "ticker", "")) for c in picks[:3]]
    if not picks:
        row.headline = "관문을 넘은 종목이 없습니다"
    else:
        row.headline = f"{len(picks)}종목 · 앞 셋 " + " · ".join(n for n in names if n)
    row.detail = "품질 · 가격 · 선행 EPS" + (f" · {when} 수집" if when else "")
    return row


def row_news(must=None, worth=None, market: str = "kr") -> Row:
    """5. 꼭 읽을 뉴스 — 몇 건이고 내 종목이 걸렸나. **그 시장의 뉴스**입니다
    (한국: 섹터 뉴스 / 미국: 주제별 뉴스 — 11/19 "미국장은 미국 걸로").

    must · worth = news.triage 의 결과(Picked 목록). None 이면 아직 받는 중."""
    row = Row(key="news", title="꼭 읽을 뉴스",
              goto="us_news" if market == "us" else "kr_flows")
    if must is None:
        row.level = "unknown"
        row.headline = "받는 중"
        return row
    mine = [p for p in must if any(str(t).startswith("내 종목") for t in getattr(p, "tags", ()))]
    if not must:
        row.headline = "오늘 꼭 읽을 것은 없습니다"
        row.detail = f"볼 만함 {len(worth or [])}건"
        return row
    row.headline = f"{len(must)}건" + (f" · 내 종목 {len(mine)}건" if mine else "")
    lead = (mine or must)[0]
    title = str(getattr(getattr(lead, "head", None), "title", ""))
    row.detail = title if len(title) <= 46 else title[:45] + "…"
    row.level = "watch" if mine else "quiet"
    return row


def row_sessions(briefs=None, market: str = "kr") -> Row:
    """6. 전일 장 — 마지막으로 마감한 거래일의 지수 등락. 숫자만, 해석 없이.

    briefs = {시장: daily_brief.SessionBrief 또는 None}. 고른 시장이 머리, 다른 시장이 세부."""
    row = Row(key="sessions", title="전일 장", goto="briefing")
    briefs = briefs or {}

    def line(b, n: int) -> str:
        moves = [m for m in getattr(b, "indices", []) if getattr(m, "ok", False)][:n]
        return " · ".join(f"{m.label} {m.pct:+.1f}%" for m in moves)

    main = briefs.get(market)
    if main is None or not getattr(main, "ok", False) or not line(main, 1):
        row.level = "unknown"
        row.headline = "전일 장 숫자를 받지 못했습니다" if main is not None else "받는 중"
        return row
    row.headline = line(main, 3)
    bits = [f"{main.session_label} 마감"]
    for m, b in briefs.items():
        if m != market and b is not None and getattr(b, "ok", False) and line(b, 2):
            bits.append(f"{b.title} {line(b, 2)}")
    row.detail = " · ".join(bits)
    return row


def row_calendar(events=None, today=None, market: str = "kr") -> Row:
    """7. 다가오는 일정 — 앞으로 7일 중 가장 가까운 것. 전체는 주요 일정 화면.

    events = calendar_events.Event 목록(날짜순). 이틀 안에 큰 일정이 있으면 '볼 것 있음'."""
    row = Row(key="calendar", title="다가오는 일정", goto="calendar")
    if events is None:
        row.level = "unknown"
        row.headline = "받는 중"
        return row
    if not events:
        row.headline = "앞으로 7일, 큰 일정 없음"
        return row
    import datetime as _dt

    today = today or _dt.date.today()

    def tag(e) -> str:
        d = (e.day - today).days
        return ("오늘" if d == 0 else f"D-{d}") + f" {e.title}"

    row.headline = tag(events[0])
    rest = events[1:3]
    row.detail = (" · ".join(tag(e) for e in rest)
                  + (f" 외 {len(events) - 3}건" if len(events) > 3 else "")) if rest else ""
    near = [e for e in events if (e.day - today).days <= 2 and e.importance >= 3]
    row.level = "watch" if near else "quiet"
    return row


def row_sector(sector_rows) -> Row:
    """한국 — 섹터 온도. 업종 순환이 보이면 '볼 것 있음'."""
    import sector_heat as _sh  # noqa: PLC0415

    row = Row(key="sector", title="섹터 온도", goto="sector_heat")
    usable = [r for r in (sector_rows or []) if r.ok and not r.benchmark]
    if not usable:
        row.level = "unknown"
        row.headline = "업종 ETF 를 받지 못했습니다"
        return row
    # 2026-11-13 사용자 승인: 한 줄을 흐름 기준(3개월 위치 × 1주 방향)으로 —
    # 1개월 기준이던 때는 섹터 온도 탭의 판독과 결론이 달랐습니다.
    flows = _sh.flow(sector_rows)
    line = _sh.flow_summary_line(_sh.flow_read(sector_rows, flows), flows)
    row.headline = line or _sh.summary_line(sector_rows)
    basis = ("3개월 위치 × 1주 방향, KODEX 200 대비" if line
             else "1개월, KODEX 200 대비")
    # 시장보다 10%p 넘게 벌어진 업종이 있으면 볼 만한 순환입니다 (1개월 — 그대로).
    spread = [abs(r.rel_1m) for r in usable if r.rel_1m is not None]
    row.level = "watch" if spread and max(spread) >= 10 else "quiet"
    bad = _sh.mismatched(sector_rows)
    if bad:
        row.detail = (f"✗ 종목코드 확인 필요 {len(bad)}건 — "
                      + ", ".join(r.label for r in bad))
    else:
        row.detail = f"업종 ETF {len(usable)}개 · {basis}"
    return row


def build(*, urgent=None, soon=None, holdings_total: int = 0,
          fg=None, vix_state=None, trends=None,
          macro_readings=None, market: str = "us",
          sector_rows=None, phase=None, today=None,
          phase_check: bool = True,
          picks=None, picks_when: str = "", news=None,
          sessions=None, events=None, extras: bool = True) -> Summary:
    """요약을 만듭니다. 없는 입력은 '데이터 없음' 으로 표시합니다.

    **시장마다 둘째 줄이 다릅니다.** 미국은 시장 심리(공포탐욕·VIX),
    한국은 섹터 온도입니다. 공포탐욕과 VIX 는 미국 지표라 한국 화면의
    둘째 줄에 둘 이유가 약하고, 한국에서 매일 보는 건 '어느 업종으로
    돈이 가나' 입니다.

    news = (꼭 읽기, 볼 만함) 또는 None — **그 시장의 뉴스**를 넘깁니다 (11/19 점검:
    미국 요약에 한국 섹터 뉴스가 나왔습니다 → 미국은 미국 주제 뉴스). extras=False 면
    뒤의 네 줄(후보 · 뉴스 · 전일 장 · 일정)을 만들지 않습니다.
    """
    second = (row_sector(sector_rows) if market == "kr"
              else row_sentiment(fg, vix_state))
    rows = [
        row_holdings(urgent or [], soon or [], holdings_total),
        second,
        row_cycle(trends or {}, macro_readings or [], phase, today,
                  phase_check=phase_check),
    ]
    if extras:
        rows.append(row_picks(picks, picks_when, market))
        must, worth = news if news is not None else (None, None)
        rows.append(row_news(must, worth, market))
        rows.append(row_sessions(sessions, market))
        rows.append(row_calendar(events, today, market))
    return Summary(rows=rows)
