"""
VIX 기간구조 + 백분위 — **인증키 불필요**.

**VIX 숫자 하나는 쓸모가 적습니다.** `VIX 18` 이 높은지 낮은지는 맥락 없이는
답할 수 없습니다. DIO 에서 "절대값은 의미 없고 자사 밴드 내 위치가 신호" 라고
했던 것과 같은 문제입니다. 그래서 두 가지를 붙입니다:

**1. 백분위** — 과거 대비 지금 어디인가. FRED `VIXCLS` 일별 종가 이력으로
   1년·5년 백분위를 냅니다. "VIX 18 = 5년 중 하위 30%" 가 숫자 18 보다
   정보가 많습니다.

**2. 기간구조** — 곡선의 모양. Cboe 는 만기별로 여러 지수를 냅니다:

       VIX9D  (9일)  →  VIX  (30일)  →  VIX3M  (3개월)  →  VIX6M  (6개월)

   평소에는 뒤로 갈수록 높습니다(**콘탱고** = 평온). 위기에는 앞이 치솟아
   뒤보다 높아집니다(**백워데이션** = 지금 당장이 더 두렵다).

   핵심 비율은 IVTS = VIX ÷ VIX3M 입니다. 1.0 을 넘으면 역전입니다.
   **2010년 이후 역전은 전체 거래일의 7.7% 에 불과합니다** — 드물기 때문에
   신호가 됩니다.

주의: 이건 **국면 지표이고 타이밍 도구가 아닙니다.** 역전이 왔다고 팔 때라는
뜻이 아니고, 콘탱고라고 안전하다는 뜻도 아닙니다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

#: Cboe VIX 계열 — (야후 티커, 이름, 만기 일수, 세션에서 확인했는지)
FAMILY: tuple[tuple[str, str, int, bool], ...] = (
    ("^VIX9D", "VIX9D", 9, False),
    ("^VIX", "VIX", 30, True),
    ("^VIX3M", "VIX3M", 91, False),
    ("^VIX6M", "VIX6M", 182, False),
)

#: FRED 의 VIX 일별 종가 — 백분위 계산용 (키 불필요)
FRED_SERIES = "VIXCLS"

#: IVTS(VIX÷VIX3M) 구간. 관행적 경계이고 법칙이 아닙니다.
STRONG_CONTANGO = 0.90
BACKWARDATION = 1.00

#: 2010년 이후 백워데이션 발생 비율 — 드물다는 것을 화면에 적기 위한 기준값
BACKWARDATION_BASE_RATE = 7.7


@dataclass
class Point:
    """만기 한 지점."""

    symbol: str
    label: str
    days: int
    value: float | None = None
    change_pct: float | None = None
    verified: bool = False

    @property
    def ok(self) -> bool:
        return self.value is not None and self.value > 0


@dataclass
class VixState:
    """VIX 기간구조 + 백분위 스냅샷."""

    points: list[Point] = field(default_factory=list)

    #: FRED VIXCLS 이력에서 낸 백분위 (0~100)
    pct_1y: float | None = None
    pct_5y: float | None = None
    median_1y: float | None = None
    low_5y: float | None = None
    high_5y: float | None = None
    history_days: int = 0

    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def point(self, label: str) -> Point | None:
        for p in self.points:
            if p.label == label and p.ok:
                return p
        return None

    @property
    def spot(self) -> float | None:
        p = self.point("VIX")
        return p.value if p else None

    @property
    def ok(self) -> bool:
        return self.spot is not None

    @property
    def ivts(self) -> float | None:
        """VIX ÷ VIX3M. 1.0 초과면 백워데이션(역전)."""
        near, far = self.point("VIX"), self.point("VIX3M")
        if near is None or far is None:
            return None
        return near.value / far.value

    @property
    def front_ratio(self) -> float | None:
        """VIX9D ÷ VIX. 1.0 초과면 **초단기** 역전 — FOMC·CPI 같은
        이벤트 직전에 흔합니다."""
        front, near = self.point("VIX9D"), self.point("VIX")
        if front is None or near is None:
            return None
        return front.value / near.value

    @property
    def structure(self) -> str:
        r = self.ivts
        if r is None:
            return "판정 불가"
        if r >= BACKWARDATION:
            return "백워데이션 (역전)"
        if r < STRONG_CONTANGO:
            return "강한 콘탱고"
        return "콘탱고"

    @property
    def is_inverted(self) -> bool:
        r = self.ivts
        return r is not None and r >= BACKWARDATION

    @property
    def structure_detail(self) -> str:
        r = self.ivts
        if r is None:
            return "VIX3M 을 받지 못해 기간구조를 판정할 수 없습니다."
        if r >= BACKWARDATION:
            return (
                f"30일 변동성이 3개월보다 높습니다 (비율 {r:.3f}). "
                "시장이 **지금 당장**을 더 두려워하는 상태입니다 — "
                f"2010년 이후 전체 거래일의 {BACKWARDATION_BASE_RATE:g}% 에만 "
                "나타났습니다."
            )
        if r < STRONG_CONTANGO:
            return (
                f"3개월 변동성이 30일보다 뚜렷하게 높습니다 (비율 {r:.3f}). "
                "평온한 구간의 전형적인 모양입니다."
            )
        return (
            f"3개월이 30일보다 높지만 격차가 좁습니다 (비율 {r:.3f}). "
            "콘탱고가 평평해지는 구간이라 역전 쪽을 주시할 값입니다."
        )

    @property
    def percentile_label(self) -> str:
        if self.pct_5y is None:
            return "—"
        return f"5년 중 {self.pct_5y:,.0f}%"


def percentile_of(value: float, history: list[float]) -> float | None:
    """history 중 value 이하인 비율(%). 백분위가 낮으면 지금이 조용한 것입니다."""
    if not history:
        return None
    below = sum(1 for v in history if v <= value)
    return below / len(history) * 100.0


def build_state(quotes: dict, fred_series=None) -> VixState:
    """시세 + FRED 이력을 합쳐 상태를 만듭니다.

    quotes: {symbol: Quote} — 야후에서 받은 VIX 계열
    fred_series: sources.fred.Series — VIXCLS. 없으면 백분위를 비웁니다.
    """
    state = VixState()

    for symbol, label, days, verified in FAMILY:
        quote = quotes.get(symbol)
        point = Point(symbol=symbol, label=label, days=days, verified=verified)
        if quote is not None and quote.ok and quote.price:
            point.value = quote.price
            point.change_pct = quote.change_pct
        state.points.append(point)

    if state.spot is None:
        state.error = "VIX 시세를 받지 못했습니다."
        return state

    missing = [p.label for p in state.points if not p.ok]
    if missing:
        state.warnings.append(
            f"받지 못한 만기: {', '.join(missing)}. "
            "VIX9D·VIX3M·VIX6M 은 야후에서 간헐적으로 비는 경우가 있습니다 — "
            "VIX3M 이 없으면 기간구조를 판정할 수 없습니다."
        )

    if fred_series is not None and fred_series.observations:
        today = dt.date.today()
        cutoff_1y = today - dt.timedelta(days=365)
        cutoff_5y = today - dt.timedelta(days=365 * 5)
        hist_1y = [o.value for o in fred_series.observations if o.date >= cutoff_1y]
        hist_5y = [o.value for o in fred_series.observations if o.date >= cutoff_5y]
        state.history_days = len(hist_5y)

        state.pct_1y = percentile_of(state.spot, hist_1y)
        state.pct_5y = percentile_of(state.spot, hist_5y)
        if hist_1y:
            ordered = sorted(hist_1y)
            state.median_1y = ordered[len(ordered) // 2]
        if hist_5y:
            state.low_5y, state.high_5y = min(hist_5y), max(hist_5y)

        if len(hist_5y) < 250:
            state.warnings.append(
                f"백분위 계산에 쓴 과거 관측치가 {len(hist_5y)}일뿐입니다 — "
                "5년 백분위로 보기엔 표본이 짧습니다."
            )
    else:
        state.warnings.append(
            "FRED VIXCLS 이력을 받지 못해 백분위를 낼 수 없습니다. "
            "현재 숫자만으로는 지금이 높은지 낮은지 알 수 없습니다."
        )

    return state


def reading_lines(state: VixState) -> list[str]:
    """판단 재료. 매수/매도 신호로 읽히지 않게 씁니다."""
    if not state.ok:
        return [state.error] if state.error else []

    lines = []
    if state.pct_5y is not None:
        lines.append(
            f"현재 VIX {state.spot:,.2f} 는 **5년 관측치의 {state.pct_5y:,.0f}% "
            f"지점**입니다"
            + (f" (1년 기준 {state.pct_1y:,.0f}%)" if state.pct_1y is not None else "")
            + "."
        )
        if state.low_5y is not None and state.high_5y is not None:
            lines.append(
                f"5년 범위는 {state.low_5y:,.1f} ~ {state.high_5y:,.1f} 이고, "
                f"1년 중간값은 {state.median_1y:,.1f} 입니다."
                if state.median_1y is not None else
                f"5년 범위는 {state.low_5y:,.1f} ~ {state.high_5y:,.1f} 입니다."
            )
    else:
        lines.append(
            f"현재 VIX {state.spot:,.2f}. **과거 대비 위치를 낼 수 없습니다** — "
            "숫자만으로는 높은지 낮은지 판단할 수 없습니다."
        )

    lines.append(f"기간구조는 **{state.structure}** 입니다. {state.structure_detail}")

    front = state.front_ratio
    if front is not None and front >= 1.0:
        lines.append(
            f"초단기(9일)가 30일보다 높습니다 (비율 {front:.3f}). "
            "FOMC·CPI 같은 예정된 이벤트 직전에 흔한 모양이라, "
            "구조적 스트레스와 구분해서 봐야 합니다."
        )

    lines.append(
        "이건 **국면 지표이고 타이밍 도구가 아닙니다.** 역전이 왔다고 팔 때라는 "
        "뜻이 아니고, 콘탱고라고 안전하다는 뜻도 아닙니다."
    )
    return lines
