"""
================================================================================
가격 조건식 — "좋은 회사" 다음에 "싼가" 를 숫자로 묻습니다.
================================================================================

왜 buffett.py 와 분리했는가:

  buffett.py 의 6개 기준은 **공시만** 있으면 판정됩니다. 그래서 95개 기업을
  시세 없이 돌릴 수 있고, 종목 발굴 탭이 빠릅니다.

  가격 조건은 **시가총액**이 필요합니다. 95개 기업 시가총액을 매번 받으면
  발굴 탭이 야후 호출 95건을 더 짊어집니다. 그래서 질 조건을 통과한
  후보에만 가격 조건을 붙입니다 — 밸류에이션 탭이 하는 일입니다.

새로 받아오는 태그가 **하나도 없습니다.** 전부 이미 쓰는 값으로 계산합니다:

  FCF        = 영업활동현금흐름 − 유형자산 취득지출   (YearRow.free_cash_flow)
  순부채     = (유동+비유동 차입금) − (현금+투자자산)  (YearRow.net_debt)
  자본       = StockholdersEquity                      (YearRow.equity)
  내재성장률 = 역DCF 역산값                            (reverse_dcf.Result)

미검증 식별자를 늘리지 않으려는 의도입니다. 영업이익·이자비용·법인세 태그를
새로 넣으면 조건은 늘어나지만, 실제 응답에서 안 맞을 위험도 같이 늘어납니다.

────────────────────────────────────────────────────────────────────────────────
기준선의 출처에 대해

버핏은 **숫자로 된 밸류에이션 기준을 공표한 적이 없습니다.** "적정 가격에 좋은
기업" 이라고 했을 뿐 적정의 선을 그은 적이 없습니다. 그래서 여기 세 조건은
전부 provenance="mine" 입니다 — 제가 정한 구현 기준이고, 버핏 발언에
대응하지 않습니다.

그중 FCF 수익률만은 근거를 댈 수 있습니다. 주식의 현금 수익률이 무위험
수익률보다 낮으면, 국채보다 비싼 값에 주식 위험을 사는 것입니다. 이 비교는
판단의 출발점이 되므로 기준선을 FRED 10년물(DGS10)에 연동시킬 수 있게
했습니다. 나머지 두 개(3년, 중위수 비교)는 솔직히 제 재량입니다.
================================================================================
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from buffett import Check, Criterion

# ──────────────────────────────────────────────────────────────────────────────
# 조건 정의
# ──────────────────────────────────────────────────────────────────────────────

CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "fcf_yield", "FCF 수익률이 무위험 수익률보다 높은가", "mine",
        "버핏은 숫자 기준을 공표한 적이 없습니다. 다만 주식의 현금 수익률이 "
        "국채 수익률보다 낮으면 국채보다 비싼 값에 주식 위험을 사는 것이라는 "
        "비교는 성립합니다. 기준선을 FRED 10년물(DGS10)에 연동할 수 있게 "
        "했고, 연동이 안 되면 기본 5.0% 를 씁니다.",
        "기준 FCF ÷ 시가총액. 역DCF 와 **같은 기준 FCF** 를 씁니다 — 두 화면이 "
        "다른 숫자를 보여주면 신뢰를 잃습니다. 사이클 정규화가 적용된 값입니다.",
        "분모가 시가총액이라 **부채를 무시합니다.** 차입으로 자산을 산 회사는 "
        "시가총액이 작아 수익률이 높아 보입니다 — 아래 순부채 조건과 같이 "
        "보셔야 합니다. 또 FCF 는 성장 투자를 비용으로 처리하므로 투자기 "
        "기업은 낮게 나옵니다.",
    ),
    Criterion(
        "net_debt_years", "순부채를 FCF 로 몇 년에 갚는가", "mine",
        "제가 정한 기준입니다(기본 3년). 버핏의 부채 회피 원칙을 상환 기간으로 "
        "옮긴 것이고 특정 발언에 대응하지 않습니다.",
        "순부채 ÷ 기준 FCF. 순현금(순부채가 음수)이면 통과로 봅니다. "
        "D/E 와 달리 **갚을 현금이 있는지**를 봅니다 — 부채가 많아도 현금을 "
        "많이 벌면 위험이 다릅니다.",
        "리츠·유틸리티는 구조적으로 부채가 많아 이 조건에서도 불리합니다. "
        "D/E 조건보다는 덜하지만 완전히 해결되지 않습니다. 또 FCF 가 음수면 "
        "'몇 년' 이 계산되지 않아 판정 불가가 됩니다.",
    ),
    Criterion(
        "expectation_gap", "주가가 요구하는 성장률이 과거 실적보다 낮은가", "mine",
        "역DCF 로 역산한 내재 성장률을 과거 실제 FCF 성장률과 비교하는 기법은 "
        "제 구현 기준입니다. 버핏 발언에 대응하지 않습니다.",
        "역DCF 내재 성장률 ≤ 과거 FCF 연평균 성장률(여러 기간의 **중위수**). "
        "시장이 과거보다 낮은 성장을 요구하고 있다면 기대가 보수적으로 "
        "**해석할 여지**가 있습니다.",
        "과거 성장률이 미래를 보장하지 않습니다. 사이클 업종은 시작·끝 연도에 "
        "따라 CAGR 이 크게 달라져 여러 기간의 중위수를 쓰지만 그래도 흔들립니다. "
        "또 과거 성장률 자체가 음수면 '더 낮은 기대' 가 좋은 뜻이 아닙니다 — "
        "그 경우는 판정 불가로 둡니다.",
    ),
)

CRITERIA_BY_KEY = {c.key: c for c in CRITERIA}

#: 점수에 넣지 않고 **표시만** 하는 지표.
#: 넣지 않는 이유는 각 항목의 note 에 적었습니다. 점수는 서로 다른 축을
#: 재는 조건들로만 구성해야 합니다 — 비슷한 걸 두 번 세면 그 축에
#: 가중치가 두 배로 붙습니다.
METRICS: tuple[tuple[str, str, str], ...] = (
    ("ev_fcf", "EV / FCF",
     "기업가치(시가총액 + 순부채) ÷ 기준 FCF. FCF 수익률과 순부채 조건을 "
     "한 숫자로 합친 것이라, 점수에 넣으면 그 둘과 겹쳐 중복 계산됩니다."),
    ("pbr", "PBR",
     "시가총액 ÷ 자본총계. 점수에서 뺀 이유는 **이 스크리닝과 방향이 "
     "반대**라서입니다 — PBR 은 자산이 많은 기업을 싸게 보는데, 질 조건은 "
     "자본이 덜 드는 기업을 높게 봅니다. 둘을 한 점수에 넣으면 서로 "
     "상쇄됩니다. MSFT 같은 무형자산 중심 기업은 PBR 이 구조적으로 높습니다."),
)


@dataclass
class Thresholds:
    """가격 조건 기준선."""

    #: FCF 수익률 하한(%). None 이면 risk_free_pct + premium_pct 로 계산합니다.
    fcf_yield_min: float | None = None
    #: 무위험 수익률(%). app 에서 FRED DGS10 최신값을 넣습니다.
    risk_free_pct: float | None = None
    #: 무위험 수익률에 얹는 가산(%p). 제 재량입니다.
    premium_pct: float = 1.0
    #: 연동이 안 될 때의 기본 하한(%)
    fcf_yield_fallback: float = 5.0

    net_debt_years_max: float = 3.0

    def yield_floor(self) -> tuple[float, str]:
        """하한값과 그 근거 문구를 함께 돌려줍니다.

        화면에 '왜 이 숫자인지' 를 같이 적어야 합니다 — 근거 없는 기준선은
        통과/탈락만 보여주고 판단 재료가 되지 않습니다.
        """
        if self.fcf_yield_min is not None:
            return self.fcf_yield_min, "직접 지정"
        if self.risk_free_pct is not None:
            return (self.risk_free_pct + self.premium_pct,
                    f"10년물 {self.risk_free_pct:.2f}% + 가산 {self.premium_pct:.1f}%p")
        return self.fcf_yield_fallback, "10년물 미연동 — 기본값"


# ──────────────────────────────────────────────────────────────────────────────
# 판정
# ──────────────────────────────────────────────────────────────────────────────

def _fail(key: str, label: str, detail: str, value: float | None = None) -> Check:
    return Check(CRITERIA_BY_KEY[key], "fail", value, label, detail)


def _unknown(key: str, detail: str) -> Check:
    return Check(CRITERIA_BY_KEY[key], "unknown", None, "—", detail)


def _pass(key: str, label: str, detail: str, value: float | None = None,
          warning: str = "") -> Check:
    return Check(CRITERIA_BY_KEY[key], "pass", value, label, detail, warning)


def check_fcf_yield(fcf_base: float | None, market_cap: float | None,
                    th: Thresholds, *, distorted: bool = False) -> Check:
    floor, basis = th.yield_floor()
    if fcf_base is None or not market_cap or market_cap <= 0:
        return _unknown("fcf_yield", "기준 FCF 또는 시가총액이 없습니다.")

    pct = fcf_base / market_cap * 100.0
    label = f"{pct:.2f}%"
    detail = f"기준선 {floor:.2f}% ({basis})"
    if pct < floor:
        return _fail("fcf_yield", label, detail, pct)

    warn = ""
    if distorted:
        warn = ("사이클 정규화가 기준 FCF 를 절반 이상 깎았습니다. "
                "이 수익률은 최근 실적이 아니라 평균치 기준입니다.")
    return _pass("fcf_yield", label, detail, pct, warn)


def check_net_debt_years(net_debt: float | None, fcf_base: float | None,
                         th: Thresholds) -> Check:
    if net_debt is None:
        return _unknown("net_debt_years", "순부채를 계산할 수 없습니다.")
    if net_debt <= 0:
        # 순현금입니다. '몇 년' 이 음수로 나오면 오해를 사므로 따로 적습니다.
        return _pass("net_debt_years", "순현금", "차입금보다 현금·투자자산이 많습니다.", 0.0)
    if fcf_base is None or fcf_base <= 0:
        return _unknown("net_debt_years",
                        "기준 FCF 가 0 이하라 상환 기간이 계산되지 않습니다.")

    years = net_debt / fcf_base
    label = f"{years:.1f}년"
    detail = f"기준선 {th.net_debt_years_max:.1f}년 이내"
    if years > th.net_debt_years_max:
        return _fail("net_debt_years", label, detail, years)
    return _pass("net_debt_years", label, detail, years)


def historical_median(cagr: dict[int, float | None]) -> float | None:
    """여러 기간 CAGR 의 중위수.

    사이클 업종은 시작·끝 연도에 따라 CAGR 이 크게 달라집니다. 10년 CAGR
    하나만 쓰면 10년 전이 불황이었는지 호황이었는지에 결과가 끌려갑니다.
    중위수는 그 영향을 줄입니다 — 없애지는 못합니다.
    """
    vals = [v for v in cagr.values() if v is not None]
    if not vals:
        return None
    return statistics.median(vals)


def check_expectation_gap(implied: float | None,
                          cagr: dict[int, float | None]) -> Check:
    if implied is None:
        return _unknown("expectation_gap", "역DCF 내재 성장률이 없습니다.")
    past = historical_median(cagr)
    if past is None:
        return _unknown("expectation_gap", "과거 FCF 성장률을 계산할 수 없습니다.")
    if past <= 0:
        # 과거가 역성장이면 '기대가 더 낮다' 가 좋은 신호가 아닙니다.
        return _unknown(
            "expectation_gap",
            f"과거 성장률 중위수가 {past*100:.1f}% 로 역성장입니다. "
            "이 비교는 의미가 없어 판정하지 않습니다.")

    gap = past - implied
    label = f"요구 {implied*100:.1f}% vs 과거 {past*100:.1f}%"
    detail = f"차이 {gap*100:+.1f}%p ({len([v for v in cagr.values() if v is not None])}개 기간 중위수)"
    if implied > past:
        return _fail("expectation_gap", label, detail, gap)
    return _pass("expectation_gap", label, detail, gap)


# ──────────────────────────────────────────────────────────────────────────────
# 표시 전용 지표
# ──────────────────────────────────────────────────────────────────────────────

def ev_over_fcf(market_cap: float | None, net_debt: float | None,
                fcf_base: float | None) -> float | None:
    if not market_cap or fcf_base is None or fcf_base <= 0:
        return None
    ev = market_cap + (net_debt or 0.0)
    return ev / fcf_base


def pbr(market_cap: float | None, equity: float | None) -> float | None:
    if not market_cap or not equity or equity <= 0:
        return None
    return market_cap / equity


# ──────────────────────────────────────────────────────────────────────────────
# 묶음
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PriceScreen:
    """한 기업의 가격 조건 판정."""

    ticker: str
    checks: list[Check] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    yield_basis: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def unknown_count(self) -> int:
        return sum(1 for c in self.checks if not c.known)

    @property
    def score_label(self) -> str:
        return f"{self.passed_count} / {len(self.checks)}"


def build(screen, result, market_cap: float | None,
          th: Thresholds | None = None) -> PriceScreen:
    """질 스크리닝 결과 + 역DCF 결과 + 시가총액 → 가격 조건 판정.

    screen 과 result 를 **둘 다** 받는 이유: 기준 FCF 는 역DCF 가 정규화한
    값을 써야 두 화면의 숫자가 일치하고, 자본총계는 역DCF 가 안 들고 있어
    screen 에서 가져와야 합니다.
    """
    th = th or Thresholds()
    out = PriceScreen(ticker=getattr(screen, "ticker", ""))

    if result is None or not getattr(result, "ok", False):
        out.error = getattr(result, "error", "") or "역DCF 결과가 없습니다."
        return out

    fcf_base = result.fcf_base
    latest = getattr(screen, "latest", None)
    net_debt = latest.net_debt if latest else None
    equity = latest.equity if latest else None

    out.checks = [
        check_fcf_yield(fcf_base, market_cap, th,
                        distorted=result.severe_distortion),
        check_net_debt_years(net_debt, fcf_base, th),
        check_expectation_gap(result.implied_growth, result.historical_cagr),
    ]
    out.yield_basis = th.yield_floor()[1]
    out.metrics = {
        "ev_fcf": ev_over_fcf(market_cap, net_debt, fcf_base),
        "pbr": pbr(market_cap, equity),
    }
    return out


def combined_label(quality_passed: int, quality_total: int,
                   price: PriceScreen | None) -> str:
    """'질 5/6 · 가격 2/3' 형태. 두 점수를 **합치지 않습니다.**

    합쳐서 8/9 로 적으면 질과 가격의 가중치가 섞여, 질이 나쁜데 싼 종목과
    질이 좋은데 비싼 종목이 같은 점수로 보입니다. 다른 축이므로 따로 적습니다.
    """
    left = f"질 {quality_passed}/{quality_total}"
    if price is None or not price.ok:
        return f"{left} · 가격 판정 불가"
    # score_label 은 buffett.Screen 과 서식을 맞춰 '2 / 3' 이지만, 여기서는
    # 왼쪽의 '질 5/6' 과 나란히 놓이므로 공백 없이 적습니다.
    return f"{left} · 가격 {price.passed_count}/{len(price.checks)}"
