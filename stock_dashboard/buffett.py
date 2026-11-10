"""
버핏식 스크리닝 — 숫자로 걸러지는 것만, 출처를 밝혀서.

**이것이 하는 일:** 10년치 공시 숫자로 "읽어볼 만한 후보" 목록을 줄입니다.
**이것이 하지 않는 일:** 무엇을 살지 판단하지 않습니다.

버핏 기준의 핵심인 **경제적 해자, 경영진의 질, 내가 이해하는 사업인가**는
숫자로 걸러지지 않습니다. 숫자가 좋은데 해자가 없는 회사가 많고, 그 구분은
10-K 와 어닝콜을 읽어야 압니다. 그래서 이 모듈의 출력은 최종 답이 아니라
**정독할 목록**입니다.

출처 표기 규칙 — 세 가지를 구분합니다:

  verbatim : 버핏이 직접 쓴 정의·규칙 (주주서한 원문)
  practice : 그의 투자 사례·발언에서 널리 인용되는 수치. 원문 표현은 아님
  mine     : 제(Claude)가 자동화를 위해 정한 구현 기준

`mine` 과 `practice` 는 수빈님 판단으로 바꾸십시오. `verbatim` 은 정의 자체라
바꾸면 다른 지표가 됩니다.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# 필요한 XBRL 태그 — 기업마다 쓰는 태그가 달라 후보를 둡니다
# ──────────────────────────────────────────────────────────────────────────────

TAGS: dict[str, tuple[str, ...]] = {
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ),
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "cost_of_revenue": (
        "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfSales",
    ),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "long_term_debt": (
        "LongTermDebtNoncurrent", "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ),
    "dep_amort": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "retained_earnings": (
        "RetainedEarningsAccumulatedDeficit",
    ),
    # ── 역DCF 용 — 순부채 계산 ──────────────────────────────────────────────
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "short_term_investments": (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ),
    "long_term_investments": (
        "LongTermInvestments",
        "MarketableSecuritiesNoncurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
    ),
    "short_term_debt": (
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
    ),
}

#: companyfacts 에서 보관할 태그 전체 (응답이 커서 추려냅니다)
KEEP_TAGS: set[str] = {tag for cands in TAGS.values() for tag in cands}

FLOW_KEYS = ("net_income", "revenue", "gross_profit", "cost_of_revenue",
             "dep_amort", "capex", "operating_cash_flow")
STOCK_KEYS = ("equity", "assets", "liabilities", "long_term_debt",
              "retained_earnings", "cash", "short_term_investments",
              "long_term_investments", "short_term_debt")


# ──────────────────────────────────────────────────────────────────────────────
# 연도별 숫자
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class YearRow:
    """한 회계연도의 숫자. 없는 항목은 None 으로 둡니다 — 추정하지 않습니다."""

    year: int
    end: str

    net_income: float | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    cost_of_revenue: float | None = None
    dep_amort: float | None = None
    capex: float | None = None
    operating_cash_flow: float | None = None

    equity: float | None = None
    assets: float | None = None
    liabilities: float | None = None
    long_term_debt: float | None = None
    retained_earnings: float | None = None
    cash: float | None = None
    short_term_investments: float | None = None
    long_term_investments: float | None = None
    short_term_debt: float | None = None

    # ── 파생 지표 ────────────────────────────────────────────────────────────
    @property
    def roe(self) -> float | None:
        """자기자본이익률(%). 자본이 음수면 의미가 없어 None 입니다."""
        if self.net_income is None or not self.equity or self.equity <= 0:
            return None
        return self.net_income / self.equity * 100.0

    @property
    def gross_margin(self) -> float | None:
        """매출총이익률(%). GrossProfit 이 없으면 매출−매출원가로 만듭니다.

        **매출총이익이 매출과 같으면 None 을 돌려줍니다.** 리츠·금융처럼
        매출원가를 따로 쓰지 않는 업종은 이 값이 100% 로 고정되고, 그러면
        표준편차가 0 이 되어 '마진이 완벽하게 안정적' 이라는 **거짓 통과**가
        나옵니다. 데이터가 없는 것을 통과로 세면 안 됩니다.
        """
        if not self.revenue or self.revenue <= 0:
            return None
        gp = self.gross_profit
        if gp is None and self.cost_of_revenue is not None:
            gp = self.revenue - self.cost_of_revenue
        if gp is None:
            return None
        if abs(gp - self.revenue) < self.revenue * 1e-6:
            return None
        return gp / self.revenue * 100.0

    @property
    def net_margin(self) -> float | None:
        if self.net_income is None or not self.revenue or self.revenue <= 0:
            return None
        return self.net_income / self.revenue * 100.0

    @property
    def owner_earnings(self) -> float | None:
        """주주이익 = 순이익 + 감가상각 등 − 설비투자.

        **버핏의 1986년 주주서한 부록 정의입니다.** 단 (c)는 원문에서
        "사업이 장기 경쟁력과 판매량을 온전히 유지하기 위해 필요한 연평균
        설비투자액" 이고, 그건 **공시되지 않는 숫자**입니다. 버핏 본인이
        "(c)는 추정이어야 하고 때로는 매우 어려운 추정" 이라고 적었습니다.

        여기서는 **총 설비투자**를 대입합니다. 성장 투자가 섞여 있으므로
        성장 기업의 주주이익은 **과소평가**됩니다. 이 한계는 화면에 표시합니다.
        """
        if self.net_income is None or self.dep_amort is None or self.capex is None:
            return None
        return self.net_income + self.dep_amort - abs(self.capex)

    @property
    def capex_exceeds_depreciation(self) -> bool | None:
        """설비투자 > 감가상각 인가.

        버핏 원문: "(c)가 (b)를 넘을 때 GAAP 이익은 주주이익을 과대계상한다.
        그런 과대계상은 흔히 상당하다." 자본집약적 사업을 걸러내는 직접 기준입니다.
        """
        if self.dep_amort is None or self.capex is None:
            return None
        return abs(self.capex) > self.dep_amort

    @property
    def free_cash_flow(self) -> float | None:
        """자유현금흐름 = 영업활동현금흐름 − 유형자산 취득지출.

        가격 판독(역DCF)의 입력값입니다. 주주이익과 비슷하지만 다릅니다 —
        주주이익은 순이익에서 출발하고 FCF 는 영업현금흐름에서 출발합니다.
        """
        if self.operating_cash_flow is None or self.capex is None:
            return None
        return self.operating_cash_flow - abs(self.capex)

    @property
    def total_debt(self) -> float | None:
        """총차입금 = 유동 + 비유동. 한쪽만 있으면 그것만 씁니다."""
        parts = [v for v in (self.short_term_debt, self.long_term_debt)
                 if v is not None]
        return sum(parts) if parts else None

    @property
    def cash_and_investments(self) -> float | None:
        """현금성자산 + 단기·장기 투자자산."""
        parts = [v for v in (self.cash, self.short_term_investments,
                             self.long_term_investments) if v is not None]
        return sum(parts) if parts else None

    @property
    def net_debt(self) -> float | None:
        """순부채. **음수면 순현금**이고, 그러면 EV 가 시가총액보다 작습니다."""
        debt = self.total_debt
        cash = self.cash_and_investments
        if debt is None and cash is None:
            return None
        return (debt or 0.0) - (cash or 0.0)

    @property
    def debt_to_equity(self) -> float | None:
        if self.long_term_debt is None or not self.equity or self.equity <= 0:
            return None
        return self.long_term_debt / self.equity

    @property
    def debt_years(self) -> float | None:
        """장기부채를 순이익 몇 년치로 갚을 수 있나."""
        if self.long_term_debt is None or not self.net_income:
            return None
        if self.net_income <= 0:
            return None
        return self.long_term_debt / self.net_income


# ──────────────────────────────────────────────────────────────────────────────
# 기준 정의
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Criterion:
    """스크리닝 기준 하나 + 출처."""

    key: str
    name: str
    #: verbatim(버핏 원문) / practice(인용 관행) / mine(제 구현 기준)
    provenance: str
    source: str                 # 구체적 출처 또는 근거
    description: str            # 무엇을 어떻게 보는가
    caveat: str = ""            # 이 기준의 한계


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "roe", "ROE 꾸준히 높은가", "practice",
        "자기자본이익률을 중시한다는 점은 주주서한에서 반복되지만, "
        "'15% 이상' 이라는 구체적 수치는 그의 투자 사례를 두고 널리 인용되는 "
        "관행적 기준이고 원문 표현은 아닙니다.",
        "10년 중 몇 해나 기준선(기본 15%)을 넘었는가. 단일 연도가 아니라 "
        "**연속성**을 봅니다 — 한 해 잘한 것과 10년 잘한 것은 다릅니다.",
        "자본이 작으면 ROE 가 과장됩니다. 자사주 매입을 많이 한 기업은 자본이 "
        "줄어 ROE 가 올라갑니다 — 사업이 좋아진 게 아닐 수 있습니다.",
    ),
    Criterion(
        "owner_earnings", "주주이익이 플러스인가", "verbatim",
        "1986년 버크셔 주주서한 부록: 주주이익 = (a) 보고 순이익 + "
        "(b) 감가상각·감모·무형자산상각 등 비현금 비용 − (c) 사업이 장기 경쟁력과 "
        "판매량을 온전히 유지하기 위해 필요한 연평균 설비투자액.",
        "10년 중 몇 해나 주주이익이 플러스였는가, 그리고 순이익 대비 비율.",
        "**(c)는 공시되지 않습니다.** 버핏 본인이 '(c)는 추정이어야 하고 때로는 "
        "매우 어려운 추정' 이라고 적었습니다. 여기서는 총 설비투자를 대입하므로 "
        "성장 투자가 많은 기업은 주주이익이 **과소평가**됩니다.",
    ),
    Criterion(
        "capex_light", "설비투자가 감가상각을 넘지 않는가", "verbatim",
        "1986년 주주서한: '(c)가 (b)를 넘을 때 GAAP 이익은 주주이익을 "
        "과대계상한다. 그런 과대계상은 흔히 상당하다.'",
        "10년 중 설비투자가 감가상각을 넘은 해가 몇 번인가. 적을수록 "
        "자본이 덜 드는 사업입니다.",
        "성장기 기업은 당연히 넘습니다. 성장 투자와 유지 투자가 구분되지 않는 "
        "것이 이 기준의 근본 한계입니다 — 떨어뜨렸다고 나쁜 기업은 아닙니다.",
    ),
    Criterion(
        "low_debt", "부채가 적은가", "practice",
        "부채 의존을 피한다는 원칙은 주주서한에 반복되지만 'D/E 0.5 이하' 같은 "
        "구체적 선은 인용 관행입니다.",
        "장기부채 ÷ 자본, 그리고 장기부채를 순이익 몇 년치로 갚을 수 있는가.",
        "업종에 따라 적정 부채가 크게 다릅니다. 유틸리티·리츠(O)는 구조적으로 "
        "부채가 많아 이 기준으로 보면 전부 탈락합니다.",
    ),
    Criterion(
        "stable_margin", "마진이 안 흔들리는가", "practice",
        "가격 결정력(pricing power)이 있는 사업을 선호한다는 취지에서 파생된 "
        "기준입니다. 버핏이 표준편차를 쓴다고 말한 적은 없습니다.",
        "매출총이익률의 10년 표준편차. 작을수록 가격 결정력이 유지된 것으로 "
        "**해석할 여지**가 있습니다.",
        "원가 구조가 안정적인 업종은 해자 없이도 마진이 안정적입니다. "
        "반도체처럼 사이클이 큰 업종은 해자가 있어도 흔들립니다 — "
        "MU·삼성전자가 이 기준에서 낮게 나오는 건 당연합니다.",
    ),
    Criterion(
        "earnings_consistency", "이익이 꾸준한가", "mine",
        "제가 정한 구현 기준입니다. '예측 가능한 사업' 선호를 숫자로 옮긴 것이고, "
        "버핏의 특정 발언에 대응하지 않습니다.",
        "10년 중 순이익이 적자였거나 전년 대비 30% 이상 감소한 해가 몇 번인가.",
        "사이클 업종은 구조적으로 불리합니다. 또 10년은 경기 침체를 한 번만 "
        "포함할 수 있어 표본이 짧습니다.",
    ),
)

CRITERIA_BY_KEY = {c.key: c for c in CRITERIA}

PROVENANCE_LABEL = {
    "verbatim": "버핏 원문",
    "practice": "인용 관행",
    "mine": "제 기준",
}


# ──────────────────────────────────────────────────────────────────────────────
# 판정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    """기준 하나의 판정 결과."""

    criterion: Criterion
    #: pass / fail / unknown — unknown 은 데이터가 없는 것이고 탈락이 아닙니다
    verdict: str
    value: float | None = None
    value_label: str = "—"
    detail: str = ""
    #: 통과했지만 숫자를 그대로 믿기 어려운 경우의 경고
    warning: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def known(self) -> bool:
        return self.verdict in ("pass", "fail")


@dataclass
class Thresholds:
    """기준선. 전부 config 에서 바꿀 수 있습니다."""

    roe_min: float = 15.0            # %
    roe_years_required: int = 8      # 10년 중 몇 해
    owner_earnings_years_required: int = 8
    capex_heavy_years_allowed: int = 3
    debt_to_equity_max: float = 0.5
    debt_years_max: float = 4.0
    margin_stdev_max: float = 5.0    # %포인트
    bad_years_allowed: int = 1
    earnings_drop_pct: float = 30.0
    min_years: int = 5               # 이보다 적으면 판정하지 않습니다


@dataclass
class Screen:
    """한 기업의 스크리닝 결과."""

    ticker: str
    name: str = ""
    years: list[YearRow] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    error: str = ""
    missing_tags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error == "" and len(self.years) > 0

    @property
    def year_count(self) -> int:
        return len(self.years)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def known_count(self) -> int:
        return sum(1 for c in self.checks if c.known)

    @property
    def unknown_count(self) -> int:
        return sum(1 for c in self.checks if not c.known)

    @property
    def score_label(self) -> str:
        """'4 / 6' 형태. 판정 불가는 분모에서 빼지 않고 따로 표시합니다 —
        데이터가 없는 것을 통과로도 탈락으로도 세면 안 됩니다."""
        return f"{self.passed_count} / {len(self.checks)}"

    @property
    def latest(self) -> YearRow | None:
        return self.years[-1] if self.years else None

    def series(self, attr: str) -> list[tuple[int, float]]:
        out = []
        for row in self.years:
            value = getattr(row, attr, None)
            if value is not None:
                out.append((row.year, value))
        return out


def _label_pct(value: float | None, decimals: int = 1) -> str:
    return "—" if value is None else f"{value:,.{decimals}f}%"


def check_roe(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["roe"]
    series = screen.series("roe")
    if len(series) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"ROE 산출 가능 연도 {len(series)}개 "
                            f"(최소 {th.min_years}개 필요)")
    hits = [v for _y, v in series if v >= th.roe_min]
    required = min(th.roe_years_required, len(series))
    median = statistics.median(v for _y, v in series)
    return Check(
        crit, "pass" if len(hits) >= required else "fail",
        value=median, value_label=_label_pct(median),
        detail=f"{len(series)}년 중 {len(hits)}년이 {th.roe_min:g}% 이상 "
               f"(기준 {required}년) · 중간값 {median:,.1f}%",
    )


def check_owner_earnings(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["owner_earnings"]
    series = screen.series("owner_earnings")
    if len(series) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"주주이익 산출 가능 연도 {len(series)}개 "
                            f"(감가상각·설비투자 공시 필요)")
    positive = [v for _y, v in series if v > 0]
    required = min(th.owner_earnings_years_required, len(series))

    # 순이익 대비 비율 — 100% 미만이면 설비투자가 감가상각을 넘은 것입니다
    ratio = None
    ni = {y: v for y, v in screen.series("net_income")}
    pairs = [(oe, ni[y]) for y, oe in series if y in ni and ni[y] > 0]
    if pairs:
        ratio = statistics.median(oe / n * 100.0 for oe, n in pairs)

    detail = (f"{len(series)}년 중 {len(positive)}년 플러스 (기준 {required}년)")
    if ratio is not None:
        detail += f" · 순이익 대비 중간값 {ratio:,.0f}%"

    warning = ""
    if ratio is not None and ratio > 150.0:
        warning = (
            f"주주이익이 순이익의 {ratio:,.0f}% 입니다. 감가상각이 매우 크고 "
            "설비투자가 작다는 뜻인데, 부동산·인프라 업종은 자산 취득이 "
            "PaymentsToAcquirePropertyPlantAndEquipment 에 잡히지 않아 "
            "**재투자가 과소계상**됩니다. 이 통과는 그대로 믿기 어렵습니다."
        )
    return Check(
        crit, "pass" if len(positive) >= required else "fail",
        value=ratio, value_label="—" if ratio is None else f"{ratio:,.0f}%",
        detail=detail, warning=warning,
    )


def check_capex_light(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["capex_light"]
    flags = [row.capex_exceeds_depreciation for row in screen.years
             if row.capex_exceeds_depreciation is not None]
    if len(flags) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"비교 가능 연도 {len(flags)}개")
    heavy = sum(1 for f in flags if f)

    # 배수도 함께 — 횟수만으로는 '성장 투자' 와 '자본집약' 이 구분되지 않습니다.
    # 1.1배와 2.5배는 같은 '초과' 지만 의미가 전혀 다릅니다.
    ratios = [abs(r.capex) / r.dep_amort for r in screen.years
              if r.capex is not None and r.dep_amort]
    median_ratio = statistics.median(ratios) if ratios else None

    detail = (f"{len(flags)}년 중 {heavy}년 설비투자 > 감가상각 "
              f"(허용 {th.capex_heavy_years_allowed}년)")
    if median_ratio is not None:
        detail += f" · 설비투자/감가상각 중간값 {median_ratio:,.2f}배"
    return Check(
        crit, "pass" if heavy <= th.capex_heavy_years_allowed else "fail",
        value=median_ratio, value_label=f"{heavy}/{len(flags)}년",
        detail=detail,
    )


def check_low_debt(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["low_debt"]
    latest = screen.latest
    if latest is None or latest.debt_to_equity is None:
        return Check(crit, "unknown", detail="장기부채 또는 자본 미공시")
    de = latest.debt_to_equity
    years = latest.debt_years
    ok = de <= th.debt_to_equity_max or (years is not None
                                        and years <= th.debt_years_max)
    detail = f"장기부채/자본 {de:,.2f} (기준 {th.debt_to_equity_max:g} 이하)"
    if years is not None:
        detail += f" · 순이익 {years:,.1f}년치 (기준 {th.debt_years_max:g}년 이하)"
    return Check(crit, "pass" if ok else "fail", value=de,
                 value_label=f"{de:,.2f}", detail=detail)


def check_stable_margin(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["stable_margin"]
    series = screen.series("gross_margin")
    if len(series) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"매출총이익률 산출 가능 연도 {len(series)}개")
    values = [v for _y, v in series]
    sd = statistics.pstdev(values)
    mean = statistics.fmean(values)
    return Check(
        crit, "pass" if sd <= th.margin_stdev_max else "fail",
        value=sd, value_label=f"±{sd:,.1f}%p",
        detail=f"{len(series)}년 평균 {mean:,.1f}% · 표준편차 ±{sd:,.1f}%p "
               f"(기준 ±{th.margin_stdev_max:g}%p 이하)",
    )


def check_earnings_consistency(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["earnings_consistency"]
    series = screen.series("net_income")
    if len(series) < th.min_years:
        return Check(crit, "unknown", detail=f"순이익 연도 {len(series)}개")
    bad: list[int] = []
    for i, (year, value) in enumerate(series):
        if value <= 0:
            bad.append(year)
            continue
        if i > 0:
            prev = series[i - 1][1]
            if prev > 0 and (value / prev - 1.0) * 100.0 <= -th.earnings_drop_pct:
                bad.append(year)
    return Check(
        crit, "pass" if len(bad) <= th.bad_years_allowed else "fail",
        value=float(len(bad)), value_label=f"{len(bad)}회",
        detail=f"{len(series)}년 중 적자 또는 {th.earnings_drop_pct:g}% 이상 "
               f"감익 {len(bad)}회 (허용 {th.bad_years_allowed}회)"
               + (f" — {', '.join(str(y) for y in bad)}" if bad else ""),
    )


CHECKS = (check_roe, check_owner_earnings, check_capex_light,
          check_low_debt, check_stable_margin, check_earnings_consistency)


def run_checks(screen: Screen, th: Thresholds | None = None) -> Screen:
    th = th or Thresholds()
    screen.checks = [fn(screen, th) for fn in CHECKS]
    return screen


# ──────────────────────────────────────────────────────────────────────────────
# companyfacts → 연도별 숫자
# ──────────────────────────────────────────────────────────────────────────────

def build_years(facts, *, years: int = 10,
                today: dt.date | None = None) -> tuple[list[YearRow], list[str]]:
    """companyfacts 에서 최근 years 개 회계연도를 뽑습니다.

    흐름 계정(순이익·매출·설비투자)은 **연간 구간**에서, 저량 계정(자본·부채)은
    같은 연도말 **시점값**에서 가져옵니다. 둘을 섞으면 ROE 분모가 어긋납니다.
    """
    missing: list[str] = []

    # 1) 흐름 계정의 연간 구간을 모아 연도 축을 만듭니다
    flows: dict[str, dict[str, float]] = {}
    for key in FLOW_KEYS:
        tag, annual = facts.annual(TAGS[key])
        if not annual:
            missing.append(key)
            continue
        flows[key] = {f.end: f.val for f in annual}

    # 순이익 또는 매출의 연도말 날짜를 축으로 씁니다
    axis_source = flows.get("net_income") or flows.get("revenue") or {}
    if not axis_source:
        return [], missing or ["net_income", "revenue"]

    ends = sorted(axis_source.keys())[-years:]

    # 2) 저량 계정의 시점값 — 연도말과 가장 가까운 것 (±7일)
    stocks: dict[str, list] = {}
    for key in STOCK_KEYS:
        tag, instants = facts.instants(TAGS[key])
        if not instants:
            missing.append(key)
            continue
        stocks[key] = instants

    def instant_at(key: str, end: str) -> float | None:
        items = stocks.get(key)
        if not items:
            return None
        exact = [f for f in items if f.end == end]
        if exact:
            return exact[0].val
        try:
            target = dt.date.fromisoformat(end)
        except ValueError:
            return None
        best, best_gap = None, 8
        for f in items:
            try:
                gap = abs((dt.date.fromisoformat(f.end) - target).days)
            except ValueError:
                continue
            if gap < best_gap:
                best, best_gap = f.val, gap
        return best

    rows: list[YearRow] = []
    for end in ends:
        row = YearRow(year=int(end[:4]), end=end)
        for key in FLOW_KEYS:
            if key in flows and end in flows[key]:
                setattr(row, key, flows[key][end])
        for key in STOCK_KEYS:
            value = instant_at(key, end)
            if value is not None:
                setattr(row, key, value)
        rows.append(row)

    return rows, sorted(set(missing))


def screen_company(ticker: str, facts, *, years: int = 10,
                   th: Thresholds | None = None) -> Screen:
    """한 기업을 스크리닝합니다."""
    rows, missing = build_years(facts, years=years)
    screen = Screen(ticker=ticker, name=getattr(facts, "entity_name", "") or ticker,
                    years=rows, missing_tags=missing)
    if not rows:
        screen.error = (
            "연간 재무 데이터를 찾지 못했습니다 "
            f"(못 찾은 계정: {', '.join(missing) if missing else '없음'})."
        )
        return screen
    return run_checks(screen, th)


def rank(screens: list[Screen]) -> list[Screen]:
    """통과 수 내림차순, 같으면 판정 불가가 적은 순, 그다음 티커순.

    **점수가 높다고 좋은 투자가 아닙니다.** 읽는 순서를 정하는 용도입니다.
    """
    return sorted(
        [s for s in screens if s.ok],
        key=lambda s: (-s.passed_count, s.unknown_count, s.ticker),
    ) + [s for s in screens if not s.ok]


def prompt_for(screen: Screen) -> str:
    """통과한 기업에 대해 Claude 에 붙여넣을 질문.

    스크리닝은 숫자만 봅니다. 숫자로 안 걸러지는 것을 묻는 게 다음 단계입니다.
    """
    passed = [c.criterion.name for c in screen.checks if c.passed]
    failed = [c.criterion.name for c in screen.checks if c.verdict == "fail"]
    unknown = [c.criterion.name for c in screen.checks if not c.known]

    lines = [
        f"{screen.ticker} ({screen.name}) 가 버핏식 숫자 기준 "
        f"{screen.score_label} 을 통과했습니다. {screen.year_count}년치 공시 기준입니다.",
        "",
        f"통과: {', '.join(passed) if passed else '없음'}",
        f"탈락: {', '.join(failed) if failed else '없음'}",
    ]
    if unknown:
        lines.append(f"판정 불가(데이터 없음): {', '.join(unknown)}")
    lines += [
        "",
        "숫자로는 걸러지지 않는 것들을 확인하고 싶습니다:",
        "1. **경제적 해자가 실제로 있습니까?** 10-K 의 경쟁 서술과 "
        "Risk Factors 를 근거로, 이 회사가 가격을 올려도 고객이 떠나지 않을 "
        "이유가 있는지 봐주십시오.",
        "2. **높은 ROE 가 사업의 힘입니까, 자본 구조입니까?** 자사주 매입이나 "
        "부채로 자본이 줄어 ROE 가 올라간 것이 아닌지 확인해 주십시오.",
        "3. **경영진이 자본을 어디에 썼습니까?** 유보이익이 재투자·인수·자사주 "
        "매입 중 어디로 갔고, 그 결정이 결과로 정당화됐는지.",
        "4. **제가 이해할 수 있는 사업입니까?** 수익이 어디서 나오는지 "
        "세 문장으로 설명되지 않으면 그렇다고 말해 주십시오.",
    ]
    if failed:
        lines.append(
            f"5. **탈락한 기준({', '.join(failed)})이 이 업종에서 "
            "구조적인 것입니까?** 업종 특성이면 기준이 부적절한 것이고, "
            "기업 고유 문제면 탈락이 맞습니다."
        )
    lines += [
        "",
        "매수/매도 추천이나 목표주가는 필요 없습니다. 판단 재료만 정리해 주십시오.",
    ]
    return "\n".join(lines)
