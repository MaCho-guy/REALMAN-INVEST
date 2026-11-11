"""
요약 — 휴대폰에서 10초 안에 보는 한 화면.

**다른 5개 탭과 축이 다릅니다.** 5개는 "무엇을 하려는 화면인가" 로 묶었고,
이건 "지금 알아야 할 것만" 입니다. 휴대폰으로 간간히 확인하는 용도라면
탭 5개를 돌아다니는 게 아니라 **한 화면에서 끝나야** 합니다.

담는 것은 네 줄입니다:

    1. 내 종목에 생긴 일   — 신규 공시 · 실적 임박 · 급변 (긴급한 것만)
    2. 시장 분위기        — 공포탐욕지수 + VIX 기간구조
    3. 메모리 사이클      — DIO 방향 + 반도체 생산·가격 전년대비
    4. 발굴 신규          — 어디를 봐야 하는지 (수치는 그 탭에서)

**담지 않는 것:** 68종목 스크리닝과 역DCF 는 책상 작업입니다. 휴대폰으로
68개 기업의 10년 재무를 받아오면 느리고, 작은 화면에서 9컬럼 표를 읽을 수도
없습니다. 그 탭으로 가라고만 적습니다.

각 줄은 **지금 볼 필요가 있나 없나**를 먼저 말합니다. "조용합니다" 가
정상 상태이고, 그게 보이면 앱을 닫아도 됩니다.
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
    #: 어느 탭으로 가야 하나
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

def row_holdings(urgent: list, soon: list, total: int) -> Row:
    """1. 내 종목에 생긴 일."""
    row = Row(key="holdings", title="내 종목", goto="내 종목")

    if urgent:
        row.level = "alert"
        row.headline = f"{len(urgent)}건 확인 필요"
        row.detail = " · ".join(s.title for s in urgent[:MAX_SIGNALS])
        if len(urgent) > MAX_SIGNALS:
            row.detail += f" 외 {len(urgent) - MAX_SIGNALS}건"
    elif soon:
        row.level = "watch"
        row.headline = f"이번 주 {len(soon)}건"
        row.detail = " · ".join(s.title for s in soon[:MAX_SIGNALS])
        if len(soon) > MAX_SIGNALS:
            row.detail += f" 외 {len(soon) - MAX_SIGNALS}건"
    else:
        row.level = "quiet"
        row.headline = f"{total}종목 모두 조용함"
        row.detail = "신규 공시·실적 임박·급변 없음"
    return row


def row_sentiment(fg, vix_state) -> Row:
    """2. 시장 분위기 — 공포탐욕 + VIX 기간구조."""
    row = Row(key="sentiment", title="시장 분위기", goto="매크로")

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
            if vix_state is not None and vix_state.ok else "세부는 매크로 탭"
        )
    return row


def row_cycle(trends: dict, macro_readings: list) -> Row:
    """3. 메모리 사이클 — DIO 방향 + 반도체 생산·가격."""
    row = Row(key="cycle", title="메모리 사이클", goto="메모리 사이클")

    bits: list[str] = []
    level = "quiet"
    details: list[str] = []

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

    if not bits:
        row.level = "unknown"
        row.headline = "재고·반도체 지표를 받지 못했습니다"
        row.detail = "DART 인증키가 필요하거나 조회가 실패했습니다"
        return row

    row.level = level
    row.headline = " · ".join(bits[:3])
    row.detail = (" · ".join(details) if details
                  else "레이어 2(재고)와 레이어 1·4(생산·가격)를 교차해야 판정됩니다")
    return row


def row_discover(note: str = "") -> Row:
    """4. 발굴 — 휴대폰에서는 수치를 돌리지 않습니다."""
    return Row(
        key="discover", title="종목 발굴", level="quiet",
        headline="책상에서 볼 것",
        detail=note or (
            "68종목 스크리닝과 역DCF 는 10년 재무를 받아와야 해서 휴대폰에서는 "
            "느립니다. 발굴·밸류에이션 탭에서 확인하십시오."
        ),
        goto="종목 발굴",
    )


def row_sector(sector_rows) -> Row:
    """한국 — 섹터 온도. 업종 순환이 보이면 '볼 것 있음'."""
    import sector_heat as _sh  # noqa: PLC0415

    row = Row(key="sector", title="섹터 온도", goto="섹터 온도")
    usable = [r for r in (sector_rows or []) if r.ok and not r.benchmark]
    if not usable:
        row.level = "unknown"
        row.headline = "업종 ETF 를 받지 못했습니다"
        return row
    hot, cold = _sh.hot_and_cold(sector_rows, n=2)
    row.headline = _sh.summary_line(sector_rows)
    # 시장보다 10%p 넘게 벌어진 업종이 있으면 볼 만한 순환입니다.
    spread = [abs(r.rel_1m) for r in usable if r.rel_1m is not None]
    row.level = "watch" if spread and max(spread) >= 10 else "quiet"
    bad = _sh.mismatched(sector_rows)
    if bad:
        row.detail = (f"✗ 종목코드 확인 필요 {len(bad)}건 — "
                      + ", ".join(r.label for r in bad))
    else:
        row.detail = f"업종 ETF {len(usable)}개 · KODEX 200 대비"
    return row


def build(*, urgent=None, soon=None, holdings_total: int = 0,
          fg=None, vix_state=None, trends=None,
          macro_readings=None, market: str = "us",
          sector_rows=None) -> Summary:
    """요약을 만듭니다. 없는 입력은 '데이터 없음' 으로 표시합니다.

    **시장마다 둘째 줄이 다릅니다.** 미국은 시장 심리(공포탐욕·VIX),
    한국은 섹터 온도입니다. 공포탐욕과 VIX 는 미국 지표라 한국 화면의
    둘째 줄에 둘 이유가 약하고, 한국에서 매일 보는 건 '어느 업종으로
    돈이 가나' 입니다.
    """
    second = (row_sector(sector_rows) if market == "kr"
              else row_sentiment(fg, vix_state))
    discover_note = (
        "국내 50종목 변동성 수축·신고가·전통 밸류 스크리닝. 일봉 1년치를 "
        "받아와야 해서 휴대폰에서는 느립니다." if market == "kr" else
        "미국 68종목 버핏식 품질 스크리닝과 역DCF 는 10년 재무를 받아와야 "
        "해서 휴대폰에서는 느립니다.")
    return Summary(rows=[
        row_holdings(urgent or [], soon or [], holdings_total),
        second,
        row_cycle(trends or {}, macro_readings or []),
        row_discover(discover_note + " 발굴·밸류에이션 탭에서 확인하십시오."),
    ])
