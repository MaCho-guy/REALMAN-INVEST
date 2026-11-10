"""
가격 판독 (역DCF) — 현재 주가가 요구하는 성장률을 역산합니다.

**적정주가를 계산하지 않습니다.** 그건 할인율·성장률 가정을 바꾸면 원하는
숫자가 나오는 계산이라 판단 재료가 못 됩니다. 대신 방향을 뒤집습니다:

    적정주가 계산: 성장률을 가정 → 주가를 구함  (가정이 답을 결정)
    역DCF:        주가를 입력   → 성장률을 구함  (시장의 기대를 드러냄)

나온 숫자를 **과거 실제 성장률과 비교**하면 판단이 섭니다:

    현재 가격이 요구하는 성장률  연 14%
    과거 10년 실제              연 6%
    → 시장은 과거보다 2배 이상 빠른 성장을 가격에 넣어두었습니다.
      그게 가능한 이유가 있는지는 공시를 읽어야 압니다.

모델:
    EV = Σ(t=1..10) FCF×(1+g)^t / (1+W)^t
         + [FCF×(1+g)^10×(1+tg) / (W−tg)] / (1+W)^10

    EV = 시가총액 + 순부채          (순부채가 음수면 순현금 → EV < 시가총액)
    g  = 이분법으로 역산
    tg = 영구성장률 (기본 2.5%)
    W  = 가중평균자본비용. **가정입니다** — 8/10/12% 세 경우를 함께 보여줍니다.

가정이 세 개(10년 구간, 영구성장률, 할인율) 들어가므로 결과는 점이 아니라
**구간**입니다. 그래서 단일 숫자로 표시하지 않습니다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# 가정값 — 전부 바꿀 수 있습니다
# ──────────────────────────────────────────────────────────────────────────────

TERMINAL_GROWTH = 0.025        # 영구성장률 2.5% (장기 명목성장률 수준)
PROJECTION_YEARS = 10
WACC_SCENARIOS = (0.08, 0.10, 0.12)
WACC_BASE = 0.10

#: 최근 FCF 가 3년 평균에서 이 비율 이상 벗어나면 평균을 씁니다.
#: 사이클 업종은 단일 연도 FCF 가 피크/트로프일 수 있어 그대로 쓰면
#: 요구 성장률이 말이 안 되게 나옵니다.
FCF_NORMALIZE_THRESHOLD = 0.40
FCF_AVERAGE_YEARS = 3

#: 역산 결과가 이 범위를 벗어나면 숫자를 내지 않고 '모델 범위 밖' 으로 둡니다.
#: 연 60% 성장을 10년 지속한다는 건 모델이 깨진 것이지 전망이 아닙니다.
GROWTH_MIN, GROWTH_MAX = -0.50, 0.60


@dataclass
class Inputs:
    """역DCF 입력값. 전부 출처가 있어야 합니다 — 추정값은 넣지 않습니다."""

    ticker: str
    market_cap: float                      # 시가총액 (통화 단위 무관, 일관되면 됨)
    net_debt: float | None = None          # 순부채. 음수면 순현금
    fcf_history: list[tuple[int, float]] = field(default_factory=list)
    currency: str = "USD"

    #: 각 입력값의 출처
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def enterprise_value(self) -> float:
        return self.market_cap + (self.net_debt or 0.0)


@dataclass
class Result:
    """역산 결과."""

    inputs: Inputs

    #: 기준 FCF (정규화 적용 후)
    fcf_base: float | None = None
    fcf_latest: float | None = None
    fcf_average: float | None = None
    normalized: bool = False

    #: 기준 WACC 에서 역산한 요구 성장률 (소수. 0.14 = 14%)
    implied_growth: float | None = None
    #: WACC 별 요구 성장률
    sensitivity: dict[float, float | None] = field(default_factory=dict)

    #: 과거 실제 FCF 연평균 성장률 — 기간별
    historical_cagr: dict[int, float | None] = field(default_factory=dict)

    #: 과거 CAGR 을 낼 수 있는 최대 기간(년). 연도 수 − 1 입니다.
    max_span: int = 0

    #: 사이클 정규화가 기준값을 절반 이상 깎았는가. True 면 역산이
    #: 성공했어도 결과를 신뢰할 수 없습니다.
    severe_distortion: bool = False

    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error == "" and self.implied_growth is not None

    @property
    def gap_span(self) -> int | None:
        """격차 비교에 쓴 과거 기간. 가장 긴 것을 씁니다."""
        usable = [sp for sp, v in self.historical_cagr.items() if v is not None]
        return max(usable) if usable else None

    @property
    def gap(self) -> float | None:
        """요구 성장률 − 과거 실제(가장 긴 기간). 플러스면 시장이 과거보다 높게 기대."""
        span = self.gap_span
        if self.implied_growth is None or span is None:
            return None
        return self.implied_growth - self.historical_cagr[span]

    @property
    def growth_label(self) -> str:
        if self.implied_growth is None:
            return "—"
        return f"연 {self.implied_growth * 100:,.1f}%"

    @property
    def band_label(self) -> str:
        """WACC 8~12% 구간의 요구 성장률 범위."""
        values = [v for v in self.sensitivity.values() if v is not None]
        if len(values) < 2:
            return "—"
        return f"연 {min(values) * 100:,.1f}% ~ {max(values) * 100:,.1f}%"


# ──────────────────────────────────────────────────────────────────────────────
# 계산
# ──────────────────────────────────────────────────────────────────────────────

def present_value(fcf0: float, g: float, wacc: float, *,
                  years: int = PROJECTION_YEARS,
                  terminal_growth: float = TERMINAL_GROWTH) -> float:
    """성장률 g 로 years 년, 이후 영구성장했을 때의 현재가치."""
    if wacc <= terminal_growth:
        raise ValueError("할인율이 영구성장률보다 커야 합니다.")

    total = 0.0
    fcf = fcf0
    for _ in range(years):
        fcf *= 1.0 + g
        total += fcf / (1.0 + wacc) ** _ / (1.0 + wacc)

    terminal = fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
    total += terminal / (1.0 + wacc) ** years
    return total


def solve_growth(target_ev: float, fcf0: float, wacc: float, *,
                 years: int = PROJECTION_YEARS,
                 terminal_growth: float = TERMINAL_GROWTH,
                 lo: float = GROWTH_MIN, hi: float = GROWTH_MAX,
                 tolerance: float = 1e-7) -> float | None:
    """이분법으로 g 를 찾습니다. 범위 밖이면 None."""
    if fcf0 <= 0:
        return None

    pv_lo = present_value(fcf0, lo, wacc, years=years,
                          terminal_growth=terminal_growth)
    pv_hi = present_value(fcf0, hi, wacc, years=years,
                          terminal_growth=terminal_growth)
    if not (pv_lo <= target_ev <= pv_hi):
        return None

    for _ in range(200):
        mid = (lo + hi) / 2.0
        pv = present_value(fcf0, mid, wacc, years=years,
                           terminal_growth=terminal_growth)
        if abs(pv - target_ev) < abs(target_ev) * tolerance:
            return mid
        if pv < target_ev:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def cagr(start: float, end: float, years: int) -> float | None:
    """연평균 성장률. 시작이나 끝이 0 이하면 계산이 불가능합니다 —
    적자에서 흑자로의 '성장률' 은 수학적으로 정의되지 않습니다."""
    if years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def normalize_fcf(history: list[tuple[int, float]],
                  ) -> tuple[float | None, float | None, float | None, bool, str]:
    """기준 FCF 를 정합니다.

    반환: (기준값, 최근값, 3년평균, 정규화했는지, 설명)

    사이클 업종은 단일 연도 FCF 가 피크나 트로프일 수 있습니다. 피크를 기준으로
    역산하면 요구 성장률이 비현실적으로 낮게, 트로프 기준이면 비현실적으로
    높게 나옵니다. 그래서 최근값이 3년 평균에서 40% 이상 벗어나면 평균을 씁니다.
    """
    if not history:
        return None, None, None, False, "FCF 이력이 없습니다."

    values = [v for _y, v in history]
    latest = values[-1]
    window = values[-FCF_AVERAGE_YEARS:]
    average = statistics.fmean(window) if len(window) >= 2 else None

    if average is None or average == 0:
        return latest, latest, average, False, "3년 평균을 낼 수 없어 최근값을 씁니다."

    deviation = abs(latest / average - 1.0) if average > 0 else None
    if deviation is not None and deviation >= FCF_NORMALIZE_THRESHOLD:
        return (average, latest, average, True,
                f"최근 FCF 가 3년 평균에서 {deviation * 100:,.0f}% 벗어나 "
                f"**3년 평균을 기준값으로 씁니다** (사이클 왜곡 방지).")
    return latest, latest, average, False, "최근 FCF 를 기준값으로 씁니다."


def run(inputs: Inputs, *, wacc_base: float = WACC_BASE,
        wacc_scenarios: tuple[float, ...] = WACC_SCENARIOS,
        terminal_growth: float = TERMINAL_GROWTH,
        years: int = PROJECTION_YEARS) -> Result:
    """역DCF 를 돌립니다."""
    result = Result(inputs=inputs)

    base, latest, average, normalized, note = normalize_fcf(inputs.fcf_history)
    result.fcf_base = base
    result.fcf_latest = latest
    result.fcf_average = average
    result.normalized = normalized
    if note:
        result.warnings.append(note)

    if base is None:
        result.error = "FCF 를 계산할 수 없습니다 (영업현금흐름 또는 설비투자 미공시)."
        return result

    if base <= 0:
        result.error = (
            f"기준 FCF 가 {base:,.0f} (0 이하) 입니다. "
            "역DCF 는 양의 현금흐름을 전제하므로 이 기업에는 적용할 수 없습니다. "
            "적자·현금소진 기업은 다른 방법으로 봐야 합니다."
        )
        return result

    if inputs.market_cap <= 0:
        result.error = "시가총액을 받아오지 못했습니다."
        return result

    if inputs.net_debt is None:
        result.warnings.append(
            "순부채를 계산할 수 없어 **시가총액을 EV 로 대신 씁니다.** "
            "현금이 많은 기업은 요구 성장률이 과대평가됩니다."
        )

    target_ev = inputs.enterprise_value
    if target_ev <= 0:
        result.error = (
            f"기업가치(EV)가 {target_ev:,.0f} 입니다 — 순현금이 시가총액보다 "
            "큽니다. 이 경우 역DCF 가 성립하지 않습니다."
        )
        return result

    # WACC 별 역산
    for wacc in wacc_scenarios:
        result.sensitivity[wacc] = solve_growth(
            target_ev, base, wacc, years=years, terminal_growth=terminal_growth)
    result.implied_growth = result.sensitivity.get(wacc_base)
    if result.implied_growth is None:
        result.implied_growth = solve_growth(
            target_ev, base, wacc_base, years=years,
            terminal_growth=terminal_growth)

    if result.implied_growth is None:
        hits = [v for v in result.sensitivity.values() if v is not None]
        if hits:
            result.warnings.append(
                f"기준 할인율({wacc_base * 100:g}%)에서는 역산이 모델 범위 "
                f"({GROWTH_MIN * 100:g}~{GROWTH_MAX * 100:g}%) 를 벗어났습니다."
            )
        else:
            # 사이클 정규화가 기준값을 크게 깎은 경우가 가장 흔한 원인입니다.
            # 그냥 '범위 밖' 이라고만 하면 왜 그런지 알 수 없습니다.
            if (normalized and latest and base and latest > 0
                    and base < latest * 0.5):
                result.error = (
                    f"역DCF 를 적용할 수 없습니다. 3년 평균 FCF "
                    f"({base:,.0f})가 최근 FCF ({latest:,.0f})의 "
                    f"{base / latest * 100:,.0f}% 수준입니다 — 과거에 적자나 "
                    "급락이 섞인 **사이클 업종**이라 평균이 기준값으로 쓸 수 "
                    "없을 만큼 낮아졌습니다.\n"
                    "이 기업은 '현금흐름이 꾸준히 성장한다' 는 모델의 전제가 "
                    "맞지 않습니다. 사이클 업종은 레이어 1~4 지표체계로 "
                    "**국면을 먼저 판정**하는 쪽이 맞습니다."
                )
            else:
                result.error = (
                    "요구 성장률이 모델 범위를 벗어났습니다 "
                    f"({GROWTH_MIN * 100:g}~{GROWTH_MAX * 100:g}%). "
                    f"기준 FCF {base:,.0f} 로 EV {target_ev:,.0f} 를 "
                    "설명하려면 모델 밖의 성장률이 필요합니다 — 현재 가격이 "
                    "현금흐름만으로 설명되지 않는다는 뜻입니다."
                )
            return result

    # 과거 실제 성장률.
    # N 개 연도로는 **N−1 년** CAGR 이 최대입니다 (시작점과 끝점이 필요).
    # 10년치를 받아도 10년 CAGR 은 못 냅니다 — 그래서 최대 가능 기간을
    # 따로 계산해 함께 보여줍니다.
    values = inputs.fcf_history
    max_span = len(values) - 1
    spans = sorted({3, 5, max_span} - {0})
    for span in spans:
        if span <= max_span and span > 0:
            result.historical_cagr[span] = cagr(
                values[-(span + 1)][1], values[-1][1], span)
    result.max_span = max_span

    # 과거 FCF 에 적자가 섞여 있으면 CAGR 이 의미를 잃습니다
    negatives = [y for y, v in values if v <= 0]
    if negatives:
        result.warnings.append(
            f"과거 FCF 에 0 이하인 해가 있습니다 ({', '.join(str(y) for y in negatives)}). "
            "그 구간을 포함한 연평균 성장률은 계산되지 않거나 의미가 없습니다."
        )

    if normalized:
        result.warnings.append(
            "기준값을 평균으로 바꿨으므로, 최근 실적이 구조적으로 개선된 "
            "경우라면 요구 성장률이 **과대평가**됩니다. 반대로 최근이 "
            "일시적 피크였다면 이 조정이 맞습니다. 어느 쪽인지는 공시를 "
            "읽어야 압니다."
        )

    # 정규화가 기준값을 절반 이상 깎았으면, 역산이 **성공해도** 결과를 믿을 수
    # 없습니다. 이 경우가 '모델 범위 밖' 보다 위험합니다 — 에러 없이 그럴듯한
    # 숫자가 나와서 그냥 읽히기 때문입니다. 그래서 따로 경고합니다.
    if (normalized and latest and base and latest > 0
            and base < latest * 0.5):
        result.severe_distortion = True
        result.warnings.insert(0, (
            f"**이 숫자를 그대로 쓰지 마십시오.** 기준 FCF({base:,.0f})가 "
            f"최근({latest:,.0f})의 {base / latest * 100:,.0f}% 수준입니다 — "
            "과거에 적자나 급락이 섞인 사이클 업종이라 3년 평균이 크게 "
            "낮아졌습니다. 그래서 요구 성장률이 실제보다 **크게 높게** "
            "나옵니다. 사이클 업종은 레이어 1~4 지표체계로 국면을 먼저 "
            "판정하는 쪽이 맞습니다."
        ))

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 스크리너 연결
# ──────────────────────────────────────────────────────────────────────────────

def inputs_from_screen(screen, market_cap: float | None, *,
                       currency: str = "USD",
                       market_cap_source: str = "") -> Inputs:
    """스크리닝 결과(10년치 재무)에서 역DCF 입력값을 만듭니다.

    FCF 와 순부채는 공시에서 나오고, 시가총액만 외부(시세)에서 옵니다.
    """
    history: list[tuple[int, float]] = []
    for row in screen.years:
        fcf = row.free_cash_flow
        if fcf is not None:
            history.append((row.year, fcf))

    latest = screen.latest
    net_debt = latest.net_debt if latest else None

    sources = {
        "FCF": "SEC EDGAR companyfacts — 영업활동현금흐름 − 유형자산 취득지출",
        "순부채": "SEC EDGAR companyfacts — (유동+비유동 차입금) − (현금+투자자산)",
    }
    if market_cap_source:
        sources["시가총액"] = market_cap_source
    if latest:
        sources["재무 기준일"] = latest.end

    return Inputs(
        ticker=screen.ticker,
        market_cap=market_cap or 0.0,
        net_debt=net_debt,
        fcf_history=history,
        currency=currency,
        sources=sources,
    )


def verdict_lines(result: Result) -> list[str]:
    """판단 재료 — 결론은 쓰지 않습니다.

    "비싸다/싸다" 를 말하지 않습니다. 요구 성장률과 과거 실적의 **격차**를
    숫자로 놓고, 그 격차를 어떻게 읽을지는 수빈님이 판단하도록 둡니다.
    """
    if not result.ok:
        return [result.error] if result.error else []

    lines = [
        f"현재 가격은 향후 {PROJECTION_YEARS}년간 "
        f"**FCF {result.growth_label} 성장**을 요구합니다 "
        f"(할인율 {WACC_BASE * 100:g}% 기준, 8~12% 구간에서 {result.band_label}).",
    ]

    hist_parts = []
    for span in sorted(result.historical_cagr):
        value = result.historical_cagr.get(span)
        if value is not None:
            hist_parts.append(f"{span}년 연 {value * 100:,.1f}%")
    if hist_parts:
        lines.append("과거 실제 FCF 성장: " + " · ".join(hist_parts) + ".")
    else:
        lines.append(
            "과거 FCF 성장률은 계산되지 않습니다 — 적자 연도가 섞여 있어 "
            "연평균 성장률이 수학적으로 정의되지 않습니다."
        )

    gap = result.gap
    if gap is not None:
        if gap > 0:
            lines.append(
                f"격차 **{gap * 100:+,.1f}%p** (과거 {result.gap_span}년 기준) "
                "— 시장은 과거보다 빠른 성장을 "
                "가격에 넣어두었습니다. 그게 가능한 이유(신제품·구조적 수요 변화·"
                "마진 개선)가 공시에서 확인되는지 봐야 합니다."
            )
        else:
            lines.append(
                f"격차 **{gap * 100:+,.1f}%p** (과거 {result.gap_span}년 기준) "
                "— 시장은 과거보다 느린 성장을 "
                "가격에 넣어두었습니다. 성장 둔화 요인이 공시에 있는지, "
                "아니면 시장이 과소평가하는지 봐야 합니다."
            )
    return lines
