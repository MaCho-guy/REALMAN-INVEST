"""
종목 발굴 — 52주 위치와 품질을 교차합니다.

**먼저 분명히 해둘 것:** 52주 신고가는 **모멘텀 지표**입니다. "좋은 주식" 이
아니라 "최근 많이 오른 주식" 입니다. 신고가 종목이 비싼 경우가 많고, 그게
신고가인 이유일 수도 있습니다.

그래서 단독으로 쓰지 않고 **버핏식 품질 기준과 교차**합니다:

                        52주 고가권            52주 저가권
    품질 기준 통과   ① 좋은 사업 + 오름세     ③ 좋은 사업 + 눌림  ← 역발상 후보
    품질 기준 미달   ② 모멘텀만              ④ 양쪽 다 미달

③ 이 가치투자가 전통적으로 찾는 자리이고, ① 은 "이미 시장이 알아본" 자리입니다.
어느 쪽이 맞는지는 이 숫자로 답할 수 없습니다 — 위치만 보여줍니다.

52주 고가·저가는 시세 조회(yfinance)의 `extra` 에서 옵니다. 공시가 아니라
시장 데이터라 즉시 갱신됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 고가권·저가권 판정은 **구간 위치**(저가~고가에서 몇 %)로 합니다.
#: 처음엔 '저가 대비 +N% 이내' 로 했는데, 그러면 52주 변동폭이 좁은 종목이
#: 구간 중간에 있어도 저가권으로 잡힙니다 — 변동폭 20% 인 종목은 구간 50%
#: 지점이 '저가 대비 +10%' 라서 저가권 조건을 통과합니다. 구간 위치는 변동폭이
#: 좁은 종목과 넓은 종목을 같은 자에 올립니다.
NEAR_HIGH_BAND = 80.0
NEAR_LOW_BAND = 20.0
#: 신고가 '돌파' 로 볼 기준 (고가의 99.5% 이상)
BREAKOUT_PCT = 99.5


@dataclass
class Position:
    """한 종목의 52주 구간 내 위치."""

    ticker: str
    name: str = ""
    price: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    currency: str = ""
    change_pct: float | None = None

    #: 버핏식 품질 — 교차할 스크리닝 결과가 있을 때만
    quality_passed: int | None = None
    quality_total: int | None = None
    quality_unknown: int | None = None

    error: str = ""

    @property
    def ok(self) -> bool:
        return (self.error == "" and self.price is not None
                and self.high_52w is not None and self.low_52w is not None
                and self.high_52w > self.low_52w)

    @property
    def pct_of_high(self) -> float | None:
        """현재가 ÷ 52주 고가 (%). 100 이면 신고가입니다."""
        if self.price is None or not self.high_52w:
            return None
        return self.price / self.high_52w * 100.0

    @property
    def band_position(self) -> float | None:
        """52주 저가~고가 구간에서의 위치 (0~100%).

        고가 대비 비율(`pct_of_high`)보다 이쪽이 정보가 많습니다 — 변동폭이
        좁은 종목과 넓은 종목을 같은 자에 올립니다.
        """
        if not self.ok:
            return None
        span = self.high_52w - self.low_52w
        return (self.price - self.low_52w) / span * 100.0

    @property
    def drawdown_pct(self) -> float | None:
        """52주 고가 대비 낙폭 (%). 음수입니다."""
        pct = self.pct_of_high
        return None if pct is None else pct - 100.0

    @property
    def upside_from_low_pct(self) -> float | None:
        """52주 저가 대비 상승률 (%)."""
        if self.price is None or not self.low_52w:
            return None
        return (self.price / self.low_52w - 1.0) * 100.0

    @property
    def is_breakout(self) -> bool:
        pct = self.pct_of_high
        return pct is not None and pct >= BREAKOUT_PCT

    @property
    def is_new_low(self) -> bool:
        """52주 저가를 깬 상태. 구간 위치가 0 이하입니다."""
        band = self.band_position
        return band is not None and band <= 0.0

    @property
    def is_near_high(self) -> bool:
        band = self.band_position
        return band is not None and band >= NEAR_HIGH_BAND

    @property
    def is_near_low(self) -> bool:
        band = self.band_position
        return band is not None and band <= NEAR_LOW_BAND

    @property
    def quality_label(self) -> str:
        if self.quality_passed is None:
            return "—"
        base = f"{self.quality_passed}/{self.quality_total}"
        return base + (f" (불가 {self.quality_unknown})"
                       if self.quality_unknown else "")

    @property
    def has_quality(self) -> bool:
        return self.quality_passed is not None

    def quadrant(self, quality_threshold: int) -> int:
        """① 고가권+통과 ② 고가권+미달 ③ 저가권+통과 ④ 저가권+미달, 0 = 분류 불가."""
        if not self.ok or not self.has_quality:
            return 0
        good = self.quality_passed >= quality_threshold
        if self.is_near_high:
            return 1 if good else 2
        if self.is_near_low:
            return 3 if good else 4
        return 0


QUADRANT_TITLE = {
    1: "① 52주 고가권 · 품질 기준 통과",
    2: "② 52주 고가권 · 품질 기준 미달",
    3: "③ 52주 저가권 · 품질 기준 통과",
    4: "④ 52주 저가권 · 품질 기준 미달",
    0: "중간 구간 또는 품질 판정 없음",
}

QUADRANT_MEANING = {
    1: "사업 기준도 넘고 가격도 오름세입니다. **시장이 이미 알아본 자리**일 "
       "가능성이 큽니다 — 밸류에이션 탭에서 가격에 얼마나 기대가 들어갔는지 "
       "먼저 보십시오.",
    2: "가격만 오르고 사업 기준은 못 넘었습니다. **모멘텀만 있는 자리**입니다. "
       "기준에서 걸린 항목이 업종 구조인지 기업 문제인지 보지 않으면 "
       "판단할 수 없습니다.",
    3: "사업 기준은 넘는데 가격은 눌려 있습니다. **가치투자가 전통적으로 찾는 "
       "자리**이지만, 시장이 아는 악재가 있어서 눌린 것일 수도 있습니다. "
       "최근 공시의 Risk Factors 변화를 먼저 확인해야 합니다.",
    4: "사업 기준도 미달이고 가격도 저가권입니다. 둘 다 이유가 있을 수 있으니, "
       "**제 기준이 이 업종에 맞는지**부터 보는 게 순서입니다.",
    0: "52주 구간의 중간이거나 품질 스크리닝 결과가 없습니다.",
}


def build_positions(instruments, quotes: dict, *,
                    screens: dict | None = None) -> list[Position]:
    """시세 + (선택) 스크리닝 결과를 교차해 위치 목록을 만듭니다.

    instruments: config.Instrument 목록
    quotes: {source: {symbol: Quote}}
    screens: {ticker: buffett.Screen} — 있으면 품질 축이 생깁니다
    """
    out: list[Position] = []
    for inst in instruments:
        quote = (quotes.get(inst.source) or {}).get(inst.symbol)
        pos = Position(ticker=inst.symbol, name=inst.name,
                       currency=inst.currency)

        if quote is None:
            pos.error = "시세를 받지 못했습니다."
        elif not quote.ok:
            pos.error = quote.error or "시세 조회 실패"
        else:
            pos.price = quote.price
            pos.currency = quote.currency or inst.currency
            pos.change_pct = quote.change_pct
            pos.high_52w = quote.extra.get("high_52w")
            pos.low_52w = quote.extra.get("low_52w")
            if pos.high_52w is None or pos.low_52w is None:
                pos.error = "52주 고가·저가를 받지 못했습니다."

        screen = (screens or {}).get(inst.symbol)
        if screen is not None and screen.ok:
            pos.quality_passed = screen.passed_count
            pos.quality_total = len(screen.checks)
            pos.quality_unknown = screen.unknown_count

        out.append(pos)
    return out


def rank_by_high(positions: list[Position]) -> list[Position]:
    """고가 대비 비율 내림차순. 신고가가 맨 위로 옵니다."""
    usable = [p for p in positions if p.ok]
    usable.sort(key=lambda p: (-(p.pct_of_high or 0.0), p.ticker))
    return usable + [p for p in positions if not p.ok]


def rank_by_low(positions: list[Position]) -> list[Position]:
    """저가 대비 상승률 오름차순. 저가권이 맨 위로 옵니다."""
    usable = [p for p in positions if p.ok]
    usable.sort(key=lambda p: ((p.upside_from_low_pct or 1e9), p.ticker))
    return usable + [p for p in positions if not p.ok]


def group_by_quadrant(positions: list[Position], quality_threshold: int,
                      ) -> dict[int, list[Position]]:
    groups: dict[int, list[Position]] = {0: [], 1: [], 2: [], 3: [], 4: []}
    for pos in positions:
        if pos.ok:
            groups[pos.quadrant(quality_threshold)].append(pos)
    for key in groups:
        groups[key].sort(key=lambda p: -(p.pct_of_high or 0.0))
    return groups


def summary_counts(positions: list[Position]) -> dict[str, int]:
    usable = [p for p in positions if p.ok]
    return {
        "전체": len(usable),
        "신고가 돌파": sum(1 for p in usable if p.is_breakout),
        "고가권(구간 80%+)": sum(1 for p in usable if p.is_near_high),
        "저가권(구간 20%-)": sum(1 for p in usable if p.is_near_low),
        "신저가": sum(1 for p in usable if p.is_new_low),
        "조회 실패": sum(1 for p in positions if not p.ok),
    }


def prompt_for(pos: Position, quality_threshold: int) -> str:
    """Claude 에 붙여넣을 질문. 모멘텀 숫자만으로는 판단이 안 되므로
    공시에서 무엇을 봐야 하는지 묻습니다."""
    quad = pos.quadrant(quality_threshold)
    lines = [
        f"{pos.ticker} ({pos.name}) 의 52주 위치를 봤습니다.",
        "",
        "[숫자]",
        f"- 현재가가 52주 고가의 {pos.pct_of_high:,.1f}% "
        f"(저가~고가 구간에서 {pos.band_position:,.0f}% 위치)",
        f"- 52주 저가 대비 {pos.upside_from_low_pct:+,.1f}%, "
        f"고가 대비 {pos.drawdown_pct:+,.1f}%",
    ]
    if pos.has_quality:
        lines.append(f"- 버핏식 숫자 기준 {pos.quality_label} 통과")
    lines += [
        "",
        f"[위치] {QUADRANT_TITLE[quad]}",
        "",
        "[확인하고 싶은 것]",
    ]
    if quad == 1:
        lines += [
            "1. 최근 1년 주가가 오른 **이유가 공시에 있는지** — 실적·가이던스·"
            "신규 사업 중 무엇인지.",
            "2. 그 이유가 **일회성인지 구조적인지**.",
            "3. 지금 가격이 그 개선을 이미 반영했는지 넘어섰는지.",
        ]
    elif quad == 2:
        lines += [
            "1. 주가가 오른 이유가 **실적인지 기대인지** — 공시 숫자로 확인.",
            "2. 버핏식 기준에서 걸린 항목이 **업종 구조인지 기업 문제인지**.",
            "3. 이 종목을 후보에서 빼도 되는지, 다른 틀로 봐야 하는지.",
        ]
    elif quad == 3:
        lines += [
            "1. **주가가 눌린 이유가 공시에 있는지** — 최근 10-K·분기보고서의 "
            "Risk Factors 에서 새로 추가되거나 표현이 강해진 항목.",
            "2. 그 악재가 **일시적인지 구조적인지**, 경영진이 어떻게 설명했는지.",
            "3. 사업 기준은 과거 실적이고 주가는 미래를 봅니다 — **시장이 먼저 "
            "본 것이 있는지**.",
        ]
    elif quad == 4:
        lines += [
            "1. 사업 기준에서 걸린 항목이 업종 전체에 해당하는지 (경쟁사 비교).",
            "2. 주가 하락과 실적 악화의 **시점이 맞는지**.",
            "3. 이 종목을 계속 볼 이유가 있는지.",
        ]
    else:
        lines += [
            "1. 52주 구간 중간이라 모멘텀 신호가 없습니다 — 사업 기준만으로 "
            "읽을 가치가 있는지.",
            "2. 최근 공시에서 방향을 바꿀 만한 내용이 있는지.",
            "3. 더 볼 필요가 없으면 그렇다고 말해 주십시오.",
        ]
    lines += [
        "",
        "**52주 신고가는 모멘텀 지표입니다** — '좋은 주식' 이 아니라 '최근 많이 "
        "오른 주식' 입니다. 그 전제로 답해 주십시오.",
        "공시에 있는 내용만으로 답하고, 자료에서 확인할 수 없는 것은 그렇다고 "
        "말해 주십시오. 매수/매도 추천, 목표주가, 단기 주가 방향은 필요 없습니다.",
    ]
    return "\n".join(lines)
