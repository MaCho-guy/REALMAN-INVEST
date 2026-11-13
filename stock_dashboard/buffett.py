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
        # 2026-11-12 전 종목 조사: 은행 · 유틸리티가 쓰는 매출 태그
        "RevenuesNetOfInterestExpense",
        "RegulatedAndUnregulatedOperatingRevenue",
    ),
    "gross_profit": ("GrossProfit",),
    "cost_of_revenue": (
        "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfSales",
        "CostOfGoodsSold",
        # 감가상각을 뺀 매출원가 — 마진이 조금 높게 나오지만 이 기준이 보는 것은
        # 마진의 '흔들림' 이라 쓸 수 있습니다 (조사에서 20개 회사)
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
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
        # 아래는 2026-11-12 전 종목 조사에서 '장기부채가 빈 회사' 가 실제로 쓰던
        # 태그입니다. 유동성 장기부채가 섞인 것도 있어 부채가 조금 크게 잡힙니다
        # (기준에는 보수적인 쪽). 순수 비유동 태그가 있으면 그쪽이 먼저 쓰입니다.
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "DebtAndCapitalLeaseObligations",
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermNotesPayable", "SeniorNotes", "ConvertibleNotesPayableNoncurrent",
        "ConvertibleDebtNoncurrent", "OtherLongTermDebtNoncurrent",
        "UnsecuredDebt", "SecuredDebt", "LongTermLineOfCredit",
        "NotesPayable", "ConvertibleNotesPayable", "DebtInstrumentCarryingAmount",
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
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        "PaymentsToAcquireOilAndGasPropertyAndEquipment",
        "PaymentsToAcquireMachineryAndEquipment",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireOtherProductiveAssets",
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
    # ── ROIC · 이자보상배율용 ───────────────────────────────────────────────
    # **아직 실제 응답으로 검증하지 않았습니다.** 회사마다 쓰는 태그가 달라
    # 후보를 여러 개 두고 먼저 맞는 것을 씁니다. 못 찾으면 그 기준만
    # '판정 불가' 가 되고 나머지 기준은 그대로 동작합니다.
    "operating_income": (
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "interest_expense": (
        "InterestExpense",
        "InterestExpenseNonoperating",     # 조사: 최근 연도에 184개 회사가 이 태그
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestExpenseOperating",
        "InterestExpenseBorrowings",
        "InterestExpenseLongTermDebt",
    ),
    # 실제 낸 이자(현금흐름표 보충 공시). 이자비용을 손익계산서에 따로 적지 않는
    # 회사가 많아(조사: 265개 회사가 이 태그만 있음) 이자보상배율의 **대체값**으로
    # 씁니다 — 쓸 때는 화면에 그렇게 적습니다.
    "interest_paid": ("InterestPaidNet", "InterestPaid"),
    # 이자수익 − 이자비용 (순액). 이자비용 자체로는 쓰지 않고, **마이너스면 빚이
    # 있다는 증거**로만 씁니다 (무차입 추정을 막는 용도).
    "interest_net": ("InterestIncomeExpenseNonoperatingNet", "InterestIncomeExpenseNet"),
    "tax_expense": ("IncomeTaxExpenseBenefit",),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    # 주식보상비용 — 현금흐름표에서 순이익에 되더해지는 비현금 비용. 영업현금흐름에
    # 그대로 들어 있어 FCF 를 부풀립니다 (직원에게 주식으로 준 급여는 주주의 비용).
    # 품질 기준에는 쓰지 않고, 가격 단계(역DCF)의 FCF 에서만 뺍니다 (funnel.py).
    "sbc": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    # 세전이익을 국내 · 해외로만 나눠 적는 회사 — 둘을 더해 세전이익으로 씁니다
    "pretax_domestic": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",),
    "pretax_foreign": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",),
}

#: companyfacts 에서 보관할 태그 전체 (응답이 커서 추려냅니다)
KEEP_TAGS: set[str] = {tag for cands in TAGS.values() for tag in cands}

#: 화면에 적을 계정 이름. 2026-11-12 실제 화면에 '공시에서 못 찾은 계정:
#: long_term_investments' 처럼 내부 이름이 그대로 나왔습니다 (국내는 한국어).
TAG_LABELS: dict[str, str] = {
    "net_income": "순이익", "revenue": "매출", "gross_profit": "매출총이익",
    "cost_of_revenue": "매출원가", "operating_income": "영업이익",
    "interest_expense": "이자비용", "depreciation": "감가상각비",
    "capex": "설비투자(CapEx)", "operating_cash_flow": "영업현금흐름",
    "dividends_paid": "배당금 지급", "buybacks": "자사주 매입",
    "equity": "자기자본", "total_assets": "총자산", "total_liabilities": "총부채",
    "long_term_debt": "장기차입금", "short_term_debt": "단기차입금",
    "cash": "현금성자산", "long_term_investments": "장기투자자산",
    "short_term_investments": "단기투자자산", "shares": "발행주식수",
    "eps": "주당순이익(EPS)", "income_tax": "법인세", "pretax_income": "세전이익",
    "inventory": "재고자산", "receivables": "매출채권", "goodwill": "영업권",
    "intangibles": "무형자산", "retained_earnings": "이익잉여금",
    "current_assets": "유동자산", "current_liabilities": "유동부채",
    "sga": "판매관리비", "rnd": "연구개발비",
    "assets": "총자산", "liabilities": "총부채",
    "dep_amort": "감가상각비", "tax_expense": "법인세비용",
    "interest_paid": "실제 낸 이자", "interest_net": "순이자(이자수익 − 이자비용)",
    "pretax_domestic": "세전이익(국내)", "pretax_foreign": "세전이익(해외)",
    "sbc": "주식보상비용",
}


def tag_label(key: str) -> str:
    """내부 계정 이름 → 화면 표기. 모르는 이름은 밑줄만 띄어 그대로."""
    return TAG_LABELS.get(key) or key.replace("_", " ")


FLOW_KEYS = ("net_income", "revenue", "gross_profit", "cost_of_revenue",
             "dep_amort", "capex", "operating_cash_flow",
             "operating_income", "interest_expense", "tax_expense",
             "pretax_income", "interest_paid", "pretax_domestic", "pretax_foreign",
             "interest_net", "sbc")
#: 다른 계정을 채우는 데만 쓰는 보조 계정 — 없어도 '못 찾은 계정' 에 올리지 않습니다
AUX_KEYS = ("interest_paid", "pretax_domestic", "pretax_foreign", "interest_net", "sbc")
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

    operating_income: float | None = None
    interest_expense: float | None = None
    tax_expense: float | None = None
    pretax_income: float | None = None
    #: 보조 — 이자비용이 없을 때의 대체값 · 세전이익을 나눠 적는 회사
    interest_paid: float | None = None
    pretax_domestic: float | None = None
    pretax_foreign: float | None = None
    interest_net: float | None = None
    sbc: float | None = None

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
    def effective_tax_rate(self) -> float | None:
        """실효세율. 법정세율(21%)을 쓰지 않는 이유: 회사마다 실제로 내는
        세율이 크게 다릅니다. 적자 해에는 음수가 나오므로 0~50% 밖은
        버립니다 — 이상한 세율로 ROIC 를 왜곡시키느니 판정을 포기합니다.
        """
        if self.tax_expense is None or not self.pretax_income:
            return None
        if self.pretax_income <= 0:
            return None
        rate = self.tax_expense / self.pretax_income
        return rate if 0.0 <= rate <= 0.5 else None

    @property
    def invested_capital(self) -> float | None:
        """투하자본 = 차입금 + 자본 − 현금·투자자산.

        현금을 빼는 이유: 쌓아둔 현금은 사업에 투입된 자본이 아닙니다.
        현금이 많은 회사의 ROIC 를 낮게 계산하면 '자본 효율이 나쁘다' 고
        잘못 읽습니다.
        """
        debt = self.total_debt or 0.0
        eq = self.equity
        if eq is None:
            return None
        cash = self.cash_and_investments or 0.0
        ic = debt + eq - cash
        return ic if ic > 0 else None

    @property
    def roic(self) -> float | None:
        """투하자본이익률(%) = 영업이익 × (1 − 실효세율) ÷ 투하자본.

        ROE 와 무엇이 다른가: ROE 는 분모가 **자본**이라 빚을 많이 쓰거나
        자사주를 많이 사면 자동으로 올라갑니다. 사업이 좋아진 게 아닌데
        숫자가 좋아집니다. ROIC 는 분모에 **빚까지** 넣으므로 그 길이
        막힙니다.
        """
        ebit = self.operating_income
        ic = self.invested_capital
        if ebit is None or ic is None:
            return None
        rate = self.effective_tax_rate
        nopat = ebit * (1.0 - rate) if rate is not None else ebit
        return nopat / ic * 100.0

    @property
    def interest_coverage(self) -> float | None:
        """이자보상배율 = 영업이익 ÷ 이자비용.

        D/E 와 무엇이 다른가: D/E 는 **얼마나 빌렸나**를 보고 이것은
        **갚을 수 있나**를 봅니다. 리츠·유틸리티는 구조적으로 빚이 많아
        D/E 로는 전부 탈락하지만, 현금흐름이 안정적이면 이자는 충분히
        냅니다. 업종 차이를 덜 타는 기준입니다.
        """
        ebit = self.operating_income
        exp = self.interest_cost
        if ebit is None or exp is None:
            return None
        return ebit / exp

    @property
    def interest_cost(self) -> float | None:
        """이자보상배율의 분모 — 이자비용, 없으면 실제 낸 이자. 0 이하면 None.

        이자비용이 0 이면 배수가 무한대라 숫자로 적지 않습니다 ('무차입' 은
        no_debt_disclosed 로 따로 봅니다).
        """
        for v in (self.interest_expense, self.interest_paid):
            if v is not None and abs(v) > 0:
                return abs(v)
        return None

    @property
    def interest_basis(self) -> str:
        """'expense' · 'paid'(대체값) · ''(없음) — 화면에 무엇으로 셌는지 적으려고."""
        if self.interest_expense is not None and abs(self.interest_expense) > 0:
            return "expense"
        if self.interest_paid is not None and abs(self.interest_paid) > 0:
            return "paid"
        return ""

    @property
    def no_debt_disclosed(self) -> bool:
        """차입금 · 이자 관련 계정이 **하나도** 없거나 전부 0 인가.

        장기부채 후보 17개 · 단기차입 3개 · 이자비용 7개 · 낸 이자 2개 태그를 다
        봤는데도 없다는 뜻입니다. 미국 전수 심사에서 이 경우를 '무차입' 으로
        봅니다 (ANET · CPRT · DECK 처럼 실제로 빚이 없는 회사가 부채 기준에서
        '판정 불가' 가 되던 것 — 2026-11-12 조사에서 38개 회사).
        """
        if self.interest_net is not None and self.interest_net < 0:
            return False                 # 순이자가 마이너스 — 어딘가 빚이 있습니다
        return all(v is None or abs(v) == 0 for v in (
            self.long_term_debt, self.short_term_debt,
            self.interest_expense, self.interest_paid))

    @property
    def fcf_conversion(self) -> float | None:
        """FCF 전환율(%) = 자유현금흐름 ÷ 순이익.

        이익이 **현금이 되는가**를 봅니다. 장부 이익은 늘어나는데 현금이
        따라오지 않으면 매출채권·재고가 쌓이고 있다는 뜻일 수 있습니다.
        순이익이 0 이하면 비율이 의미를 잃어 None 입니다.
        """
        fcf = self.free_cash_flow
        if fcf is None or not self.net_income or self.net_income <= 0:
            return None
        return fcf / self.net_income * 100.0

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

#: 기존 6개 기준이 **스스로 인정한 한계**를 메우는 기준들입니다.
#: 각 기준의 caveat 에 적힌 문제를 그대로 가져와 대응시켰습니다.
EXTRA_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "roic", "투하자본이익률(ROIC)이 높은가", "mine",
        "버핏이 ROIC 라는 지표명을 쓴 적은 없습니다. 다만 '자본을 얼마나 "
        "잘 굴리는가' 는 주주서한에서 반복되는 주제이고, ROE 의 레버리지 "
        "왜곡을 피하려면 분모를 바꿔야 합니다. 기준선 12% 는 제 재량입니다.",
        "영업이익 × (1 − 실효세율) ÷ (차입금 + 자본 − 현금·투자자산). "
        "실효세율은 법정세율이 아니라 **실제 낸 세금**으로 계산합니다. "
        "현금을 투하자본에서 빼는 이유는, 쌓아둔 현금이 사업에 투입된 "
        "자본이 아니기 때문입니다.",
        "<b>ROE 기준의 한계를 메우려는 것입니다.</b> ROE 는 빚을 많이 쓰거나 "
        "자사주를 사면 사업이 그대로여도 올라갑니다. ROIC 는 그 길이 "
        "막힙니다. 다만 영업이익·법인세 태그를 새로 읽어야 해서 **아직 "
        "실제 응답으로 검증되지 않았습니다** — 못 읽으면 판정 불가가 됩니다. "
        "금융업은 '투하자본' 개념이 달라 이 기준이 맞지 않습니다.",
    ),
    Criterion(
        "interest_cover", "이자를 충분히 내고 있는가", "practice",
        "이자보상배율은 신용 분석에서 널리 쓰는 지표입니다. 버핏의 특정 "
        "발언에 대응하지는 않고, 기준선 5배도 제 재량입니다.",
        "영업이익 ÷ 이자비용. 이자비용이 0 이면 배수가 무한대라 판정하지 "
        "않습니다 — 무차입은 부채 기준이 이미 잡아냅니다.",
        "<b>부채 기준의 한계를 메우려는 것입니다.</b> D/E 는 '얼마나 "
        "빌렸나' 를 보는데, 리츠·유틸리티는 구조적으로 빚이 많아 전부 "
        "탈락합니다. 이자보상배율은 '갚을 수 있나' 를 보므로 업종 차이를 "
        "덜 탑니다. 다만 이자비용 태그가 **미검증**이고, 회사가 이자수익과 "
        "상계해 순액으로 공시하면 배수가 과장될 수 있습니다.",
    ),
    Criterion(
        "fcf_conversion", "이익이 현금으로 들어오는가", "mine",
        "제 기준입니다. 버핏이 '현금이 중요하다' 고 한 것과 방향은 같지만 "
        "전환율이라는 숫자 기준을 제시한 적은 없습니다. 기준선 70% 도 "
        "제 재량입니다.",
        "자유현금흐름 ÷ 순이익. 10년 중 몇 해가 기준을 넘는지 셉니다. "
        "순이익이 0 이하인 해는 비율이 의미를 잃어 제외합니다.",
        "장부 이익은 느는데 현금이 안 따라오면 매출채권·재고가 쌓이고 "
        "있다는 뜻일 수 있습니다. 다만 <b>성장 투자가 큰 기업은 설비투자 "
        "때문에 낮게 나옵니다</b> — 주주이익 기준과 같은 한계이고, 낮다고 "
        "나쁜 기업이라는 뜻은 아닙니다.",
    ),
)

CRITERIA = CRITERIA + EXTRA_CRITERIA

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


#: 무차입으로 '추정' 했을 때 붙이는 경고 — 추정임을 숨기지 않습니다.
NO_DEBT_WARNING = ("차입금 · 이자 관련 계정을 하나도 찾지 못해 무차입으로 추정했습니다. "
                   "드문 계정 이름을 쓰는 회사라면 틀릴 수 있습니다 — 공시에서 확인하십시오.")


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

    # ── 보강 기준 (전부 제 재량입니다) ──────────────────────────────────────
    roic_min: float = 12.0           # %
    roic_years_required: int = 6     # 10년 중 몇 해
    interest_cover_min: float = 5.0  # 배
    fcf_conversion_min: float = 70.0     # %
    fcf_conversion_years_required: int = 6


@dataclass
class Screen:
    """한 기업의 스크리닝 결과."""

    ticker: str
    name: str = ""
    years: list[YearRow] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    error: str = ""
    missing_tags: list[str] = field(default_factory=list)
    #: 차입금 · 이자 계정이 하나도 없을 때 '무차입' 으로 볼지. 태그 후보를 넓게
    #: 확인한 미국(SEC) 심사에서만 켭니다 — 국내(DART)는 계정 이름 체계가 달라
    #: '못 읽음' 과 '없음' 을 구분할 근거가 없습니다.
    infer_no_debt: bool = False

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
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.known and not c.passed)

    @property
    def judged_ratio(self) -> float | None:
        """판정된 기준 가운데 통과한 비율 (판정 불가는 분모에서 뺌). 판정된 게 없으면 None."""
        known = self.known_count
        return self.passed_count / known if known else None

    @property
    def judged_label(self) -> str:
        """'판정 8 중 8' — 순위가 무엇으로 매겨졌는지 표에 같이 적는 글."""
        return f"판정 {self.known_count} 중 {self.passed_count}"

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
    if latest is None:
        return Check(crit, "unknown", detail="장기부채 또는 자본 미공시")
    if latest.debt_to_equity is None:
        if (screen.infer_no_debt and latest.long_term_debt is None
                and latest.no_debt_disclosed and latest.equity and latest.equity > 0):
            return Check(crit, "pass", value=0.0, value_label="무차입",
                         detail="차입금 · 이자 관련 공시가 없음 — 무차입으로 봄",
                         warning=NO_DEBT_WARNING)
        years = latest.debt_years
        if (latest.long_term_debt is not None and latest.equity is not None
                and latest.equity <= 0 and years is not None):
            # 자본이 마이너스(자사주 매입 · 누적 적자)면 부채/자본은 못 쓰지만,
            # '순이익 몇 년치로 갚나' 로는 판정할 수 있습니다.
            return Check(crit, "pass" if years <= th.debt_years_max else "fail",
                         value=years, value_label=f"{years:,.1f}년",
                         detail=f"자본이 마이너스라 부채/자본은 못 씀 — 장기부채가 순이익 "
                                f"{years:,.1f}년치 (기준 {th.debt_years_max:g}년 이하)",
                         warning="자본이 마이너스입니다 (자사주 매입 또는 누적 적자). "
                                 "부채/자본 대신 순이익 대비로만 봤습니다.")
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
        if not series and len(screen.years) >= th.min_years:
            # 못 읽은 것이 아니라 그 회사가 매출원가를 따로 적지 않는 경우
            return Check(crit, "unknown",
                         detail="매출원가를 따로 공시하지 않는 회사 (금융 · 리츠 · 일부 "
                                "서비스업) — 이 기준은 해당 없음")
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


def check_roic(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["roic"]
    series = screen.series("roic")
    if len(series) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"ROIC 산출 가능 연도 {len(series)}개 "
                            "(영업이익·법인세 태그를 못 읽었을 수 있습니다)")
    hits = sum(1 for _y, v in series if v >= th.roic_min)
    med = statistics.median(v for _y, v in series)
    return Check(
        crit, "pass" if hits >= th.roic_years_required else "fail",
        value=med, value_label=f"{med:,.1f}%",
        detail=f"{len(series)}년 중 {hits}해가 {th.roic_min:g}% 이상 "
               f"(기준 {th.roic_years_required}해) · 중간값 {med:,.1f}%",
    )


def check_interest_cover(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["interest_cover"]
    latest = screen.latest
    cover = latest.interest_coverage if latest is not None else None
    if cover is None:
        if (screen.infer_no_debt and latest is not None and latest.no_debt_disclosed
                and latest.operating_income is not None):
            return Check(crit, "pass", value_label="무차입",
                         detail="차입금 · 이자 관련 공시가 없음 — 낼 이자가 없는 것으로 봄",
                         warning=NO_DEBT_WARNING)
        return Check(crit, "unknown",
                     detail="영업이익 또는 이자비용 미공시 (무차입이면 "
                            "부채 기준에서 이미 통과합니다)")
    paid = latest.interest_basis == "paid"
    return Check(
        crit, "pass" if cover >= th.interest_cover_min else "fail",
        value=cover, value_label=f"{cover:,.1f}배",
        detail=(f"영업이익이 {'실제 낸 이자' if paid else '이자비용'}의 {cover:,.1f}배 "
                f"(기준 {th.interest_cover_min:g}배 이상)"
                + (" · 이자비용을 따로 공시하지 않아 현금흐름표의 '낸 이자' 로 계산" if paid else "")),
    )


def check_fcf_conversion(screen: Screen, th: Thresholds) -> Check:
    crit = CRITERIA_BY_KEY["fcf_conversion"]
    series = screen.series("fcf_conversion")
    if len(series) < th.min_years:
        return Check(crit, "unknown",
                     detail=f"전환율 산출 가능 연도 {len(series)}개")
    hits = sum(1 for _y, v in series if v >= th.fcf_conversion_min)
    med = statistics.median(v for _y, v in series)
    return Check(
        crit, "pass" if hits >= th.fcf_conversion_years_required else "fail",
        value=med, value_label=f"{med:,.0f}%",
        detail=f"{len(series)}년 중 {hits}해가 {th.fcf_conversion_min:g}% 이상 "
               f"(기준 {th.fcf_conversion_years_required}해) · 중간값 {med:,.0f}%",
    )


#: 표 머리에 쓸 짧은 이름 (기준 이름은 질문 꼴이라 깁니다).
SHORT_NAMES = {
    "roe": "ROE", "owner_earnings": "주주이익", "capex_light": "설비투자",
    "low_debt": "부채", "stable_margin": "마진 안정", "earnings_consistency": "이익 꾸준",
    "roic": "ROIC", "interest_cover": "이자보상", "fcf_conversion": "현금 전환",
}

DEFINITION = (
    "워런 버핏의 주주서한에 반복해 나오는 원칙 — <b>자본을 잘 굴리고, 빚이 "
    "적고, 이익이 꾸준하고, 그 이익이 실제 현금으로 들어오는 사업</b> — 을 "
    "최근 10개 회계연도의 공시 숫자로 옮긴 질문 묶음입니다. 질문마다 통과 / "
    "미달 / 판정 불가(숫자가 5년치 미만)로 가르고, 통과한 개수를 셉니다. "
    "<b>사업의 질만 보고 가격은 보지 않습니다</b> (가격은 밸류에이션 탭)."
)


def criteria_rules(th: Thresholds | None = None) -> list[dict]:
    """기준마다 **통과 조건을 숫자로** — 화면의 기준표에 씁니다.

    2026-11-12 "버핏식 품질 기준이 뭔지 정의돼 있지 않다". 기준 이름(질문)만
    있고 몇 %·몇 해가 통과선인지는 종목을 펼쳐야 보였습니다. 판정 함수
    (check_*)가 쓰는 Thresholds 를 그대로 읽어 적으므로, 기준선을 바꾸면
    표도 같이 바뀝니다. [{key, short, name, rule, provenance, label}]
    """
    th = th or Thresholds()
    rules = {
        "roe": f"ROE(순이익 ÷ 자본) ≥ {th.roe_min:g}% 인 해가 10년 중 "
               f"{th.roe_years_required}해 이상",
        "owner_earnings": "주주이익(순이익 + 감가상각 − 설비투자) > 0 인 해가 "
                          f"{th.owner_earnings_years_required}해 이상",
        "capex_light": "설비투자가 감가상각보다 큰 해가 "
                       f"{th.capex_heavy_years_allowed}해 이하",
        "low_debt": f"최근 연도 장기부채 ÷ 자본 ≤ {th.debt_to_equity_max:g} "
                    f"<b>또는</b> 장기부채 ÷ 순이익 ≤ {th.debt_years_max:g}년",
        "stable_margin": f"매출총이익률의 10년 표준편차 ≤ {th.margin_stdev_max:g}%p",
        "earnings_consistency": f"적자이거나 순이익이 전년보다 {th.earnings_drop_pct:g}% "
                                f"이상 준 해가 {th.bad_years_allowed}회 이하",
        "roic": f"ROIC(세후 영업이익 ÷ 투하자본) ≥ {th.roic_min:g}% 인 해가 "
                f"{th.roic_years_required}해 이상",
        "interest_cover": f"최근 연도 영업이익 ÷ 이자비용 ≥ {th.interest_cover_min:g}배",
        "fcf_conversion": f"FCF(영업현금흐름 − 설비투자) ÷ 순이익 ≥ {th.fcf_conversion_min:g}% 인 해가 "
                          f"{th.fcf_conversion_years_required}해 이상",
    }
    return [{"key": c.key, "short": SHORT_NAMES.get(c.key, c.name), "name": c.name,
             "rule": rules.get(c.key, c.description), "provenance": c.provenance,
             "label": PROVENANCE_LABEL.get(c.provenance, "")}
            for c in CRITERIA]


def provenance_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for c in CRITERIA:
        out[c.provenance] = out.get(c.provenance, 0) + 1
    return out


CHECKS = (check_roe, check_owner_earnings, check_capex_light,
          check_low_debt, check_stable_margin, check_earnings_consistency,
          check_roic, check_interest_cover, check_fcf_conversion)


def run_checks(screen: Screen, th: Thresholds | None = None) -> Screen:
    th = th or Thresholds()
    screen.checks = [fn(screen, th) for fn in CHECKS]
    return screen


# ──────────────────────────────────────────────────────────────────────────────
# companyfacts → 연도별 숫자
# ──────────────────────────────────────────────────────────────────────────────

#: 재무를 읽는 방식이 바뀔 때마다 올립니다. 전수 심사 파일에 같이 적어 두고,
#: 숫자가 다르면 수집기가 '아직 새 파일' 이어도 다시 심사합니다.
#:   2 (2026-11-12): 후보 태그를 연도별로 합침 · 회계연도 말만 축으로 · 낸 이자 대체 ·
#:                   무차입 추정 · 자본 마이너스 부채 판정 · 조사에서 나온 태그 추가
#:   3 (2026-11-12): 품질 통과 종목에 역DCF 입력(FCF 이력 · 순부채)을 같이 남김 (funnel.py)
#:   4 (2026-11-12): 역DCF 입력의 FCF 에서 주식보상비용을 뺌
SCREEN_REV = 4

#: 연간 보고서 양식 — 이 양식으로 낸 12개월 구간의 끝이 회계연도 말입니다
ANNUAL_FORMS = ("10-K", "20-F", "40-F")


def fiscal_year_ends(annual: list) -> set[str] | None:
    """12개월 구간들 가운데 **회계연도 말**로 끝나는 종료일의 집합.

    연간 보고서(10-K 등)로 낸 구간의 끝을 회계연도 말로 봅니다. 가장 최근
    회계연도 말과 달력상 ±15일 안에 끝나는 구간도 받습니다 (52 · 53주 회계연도는
    해마다 며칠씩 움직이고, 과거 연도를 8-K 로 다시 낸 경우 양식이 10-K 가
    아닙니다). 연간 보고서 양식이 하나도 없으면 가를 근거가 없어 None(전부 허용).
    """
    k_ends = {f.end for f in annual
              if str(getattr(f, "form", "") or "").upper().startswith(ANNUAL_FORMS)}
    if not k_ends:
        return None

    def doy(end: str) -> int | None:
        try:
            return dt.date.fromisoformat(end).timetuple().tm_yday
        except ValueError:
            return None

    anchor = doy(max(k_ends))
    out = set(k_ends)
    if anchor is not None:
        for f in annual:
            d = doy(f.end)
            if d is None:
                continue
            gap = abs(d - anchor)
            if min(gap, 366 - gap) <= 15:
                out.add(f.end)
    return out


def _annual(facts, tags) -> list:
    """후보 태그를 연도별로 합친 연간 값 (합치는 메서드가 없는 옛 객체면 첫 태그 하나)."""
    fn = getattr(facts, "annual_merged", None)
    return fn(tags) if fn else facts.annual(tags)[1]


def _instants(facts, tags) -> list:
    fn = getattr(facts, "instants_merged", None)
    return fn(tags) if fn else facts.instants(tags)[1]


def build_years(facts, *, years: int = 10,
                today: dt.date | None = None) -> tuple[list[YearRow], list[str]]:
    """companyfacts 에서 최근 years 개 회계연도를 뽑습니다.

    흐름 계정(순이익·매출·설비투자)은 **연간 구간**에서, 저량 계정(자본·부채)은
    같은 연도말 **시점값**에서 가져옵니다. 둘을 섞으면 ROE 분모가 어긋납니다.
    """
    missing: list[str] = []

    # 1) 흐름 계정의 연간 구간을 모아 연도 축을 만듭니다
    flows: dict[str, dict[str, float]] = {}
    flow_facts: dict[str, list] = {}
    for key in FLOW_KEYS:
        annual = _annual(facts, TAGS[key])
        if not annual:
            if key not in AUX_KEYS:
                missing.append(key)
            continue
        flows[key] = {f.end: f.val for f in annual}
        flow_facts[key] = annual

    # 순이익 또는 매출의 연도말 날짜를 축으로 씁니다
    axis_key = "net_income" if flows.get("net_income") else "revenue"
    axis_source = flows.get(axis_key) or {}
    if not axis_source:
        return [], missing or ["net_income", "revenue"]

    # 12개월 길이라고 다 회계연도가 아닙니다. 분기보고서에 '최근 12개월' 을 같이
    # 적는 회사(아마존 · 유틸리티 다수)는 3 · 6 · 9월 말로 끝나는 12개월 구간이
    # 섞여 들어와, 최근 10개 '연도' 가 실제로는 2~3년치 분기 말이 되고 다른 계정은
    # 그 날짜에 값이 없어 줄줄이 '판정 불가' 가 됐습니다 (2026-11-12 조사).
    fye = fiscal_year_ends(flow_facts.get(axis_key) or [])
    ends = sorted(e for e in axis_source if fye is None or e in fye)[-years:]
    if not ends:
        return [], missing or ["net_income", "revenue"]

    # 2) 저량 계정의 시점값 — 연도말과 가장 가까운 것 (±7일)
    stocks: dict[str, list] = {}
    for key in STOCK_KEYS:
        instants = _instants(facts, TAGS[key])
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
        # 세전이익을 국내 · 해외로만 나눠 적는 회사 — 둘을 더합니다
        if (row.pretax_income is None and row.pretax_domestic is not None
                and row.pretax_foreign is not None):
            row.pretax_income = row.pretax_domestic + row.pretax_foreign
        # 영업이익을 따로 적지 않는 회사 — 세전이익으로 대신합니다 (TAGS 의
        # operating_income 둘째 후보와 같은 대체. 이자를 뺀 뒤의 숫자라 보수적입니다)
        if row.operating_income is None and row.pretax_income is not None:
            row.operating_income = row.pretax_income
        rows.append(row)

    return rows, sorted(set(missing))


def screen_company(ticker: str, facts, *, years: int = 10,
                   th: Thresholds | None = None) -> Screen:
    """한 기업을 스크리닝합니다."""
    rows, missing = build_years(facts, years=years)
    screen = Screen(ticker=ticker, name=getattr(facts, "entity_name", "") or ticker,
                    years=rows, missing_tags=missing, infer_no_debt=True)
    if not rows:
        screen.error = (
            "연간 재무 데이터를 찾지 못했습니다 "
            f"(못 찾은 계정: {', '.join(missing) if missing else '없음'})."
        )
        return screen
    return run_checks(screen, th)


@dataclass
class ScreenSummary(Screen):
    """파일에서 되살린 심사 결과 — 연도별 숫자 없이 판정만 들고 있습니다.

    전수 심사(universe.py)는 500개 기업의 10년치 숫자를 파일에 싣지 않습니다.
    화면이 쓰는 것(판정 · 값 · 설명 · 연도 수)만 남깁니다.
    """

    years_n: int = 0
    sector: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and self.years_n > 0

    @property
    def year_count(self) -> int:
        return self.years_n


def to_summary(screen: Screen, **extra) -> dict:
    """심사 결과 → 파일에 실을 사전. c: [기준, 판정, 값, 설명, 경고]"""
    return {
        "t": screen.ticker, "n": screen.name, "y": screen.year_count,
        **({"e": screen.error} if screen.error else {}),
        **({"m": list(screen.missing_tags)} if screen.missing_tags else {}),
        "c": [[c.criterion.key, c.verdict, c.value_label, c.detail, c.warning]
              for c in screen.checks],
        **{k: v for k, v in extra.items() if v},
    }


def from_summary(row: dict) -> ScreenSummary | None:
    """사전 → ScreenSummary. 모르는 기준은 건너뜁니다 (파일이 다른 버전일 때)."""
    if not isinstance(row, dict) or not row.get("t"):
        return None
    checks = []
    for item in row.get("c") or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        crit = CRITERIA_BY_KEY.get(item[0])
        if crit is None or item[1] not in ("pass", "fail", "unknown"):
            continue
        checks.append(Check(crit, item[1], value_label=str(item[2] if len(item) > 2 else "—"),
                            detail=str(item[3] if len(item) > 3 else ""),
                            warning=str(item[4] if len(item) > 4 else "")))
    return ScreenSummary(
        ticker=str(row["t"]), name=str(row.get("n") or row["t"]), checks=checks,
        error=str(row.get("e") or ""), missing_tags=list(row.get("m") or []),
        years_n=int(row.get("y") or 0), sector=str(row.get("s") or ""))


def rank(screens: list[Screen]) -> list[Screen]:
    """통과 수 내림차순, 같으면 판정 불가가 적은 순, 그다음 티커순.

    **점수가 높다고 좋은 투자가 아닙니다.** 읽는 순서를 정하는 용도입니다.
    """
    return sorted(
        [s for s in screens if s.ok],
        key=lambda s: (-s.passed_count, s.unknown_count, s.ticker),
    ) + [s for s in screens if not s.ok]


def passes(screen: Screen, min_pass: int, *, by_ratio: bool = False,
           min_known: int = 6) -> bool:
    """품질 통과인가.

    기본은 **통과 수** min_pass 이상. by_ratio 면 **판정된 기준 중 통과 비율**이
    min_pass ÷ 전체 기준 수 이상이고, 판정된 기준이 min_known 개 이상일 때입니다.

    국내는 by_ratio 로 봅니다 — DART 재무제표 본문에는 감가상각비가 거의 없어
    (2026-11-12 조사: 348개 회사 중 267개) 주주이익 · 설비투자 두 기준이 대부분
    판정 불가입니다. 통과 수로 재면 9개 중 7개가 '판정된 7개 전부' 가 되어, 미국과
    같은 선이 한국에서는 훨씬 높은 선이 됩니다.
    """
    if not screen.ok:
        return False
    if not by_ratio:
        return screen.passed_count >= min_pass
    known = screen.known_count
    return known >= min_known and screen.passed_count / known >= min_pass / len(CRITERIA)


def rank_by_ratio(screens: list[Screen]) -> list[Screen]:
    """판정된 기준 중 통과 비율 내림차순 → 통과 수 내림차순 → 티커순.

    판정 불가가 많은 종목이 통과 수만으로는 불리하게 밀리던 것을 고칩니다
    (2026-11-12 전수 심사: 판정의 33% 가 '판정 불가'). 9개 중 8개 통과 · 1개
    판정 불가(8/8)는 9개 중 8개 통과 · 1개 미달(8/9)보다 앞에 옵니다 —
    **미달이 없는 쪽이 먼저**입니다.

    비율만 보면 '판정 2 중 2' 가 맨 위로 오므로, 이 함수는 **통과 수 기준을
    이미 넘긴 목록**(또는 보류 목록)에만 씁니다. 점수가 높다고 좋은 투자가
    아닙니다 — 읽는 순서를 정하는 용도입니다.
    """
    return sorted(
        [s for s in screens if s.ok],
        key=lambda s: (-(s.judged_ratio or 0.0), -s.passed_count, s.ticker))


# ── 국내 품질 통과 — '허용 미달 수' 규칙 (2026-11-13) ─────────────────────────
#
# 예전 규칙(판정된 기준 중 7/9 비율)은 판정 수에 따라 허용 미달이 2 · 1 · 1 · 1 로
# 들쭉날쭉했습니다 (판정 9 → 미달 2개 허용, 판정 8 · 7 · 6 → 1개). 국내는 감가상각비가
# 본문에 없어 거의 모든 회사가 '판정 7개' 라서, 실제로는 미국(9개 중 미달 2개 허용)보다
# 한 칸 엄격한 '7개 중 미달 1개' 로 걸렸습니다.
# 새 규칙: **확인된 미달이 2개 이하** (미국 7/9 와 같은 허용 폭 — 9개 다 판정되면 미국과
# 똑같은 선) 이고 **판정된 기준이 7개 이상** (적어도 7개는 숫자로 확인).
# 2026-11-13 데이터(funnel_kr.json): 예전 23종목 → 새 규칙 33종목. 판정 6개 이하로
# 통과하던 10종목은 '증거 부족 보류' 로 옮겨 따로 보입니다.

def passes_kr(screen: Screen, max_fail: int | None = None,
              min_known: int | None = None) -> bool:
    """국내 품질 통과 — 확인된 미달 ≤ max_fail 이고 판정된 기준 ≥ min_known."""
    import config  # noqa: PLC0415 - config 가 buffett 을 읽으므로 안에서

    if not screen.ok:
        return False
    mf = config.KR_QUALITY_MAX_FAIL if max_fail is None else max_fail
    mk = config.KR_QUALITY_MIN_KNOWN if min_known is None else min_known
    return screen.known_count >= mk and screen.failed_count <= mf


def held_back_kr(screen: Screen, max_fail: int | None = None,
                 min_known: int | None = None, floor: int = 5) -> bool:
    """국내 '증거 부족 보류' — 미달은 허용 안쪽인데 판정된 기준이 모자람 (floor 이상)."""
    import config  # noqa: PLC0415

    if not screen.ok:
        return False
    mf = config.KR_QUALITY_MAX_FAIL if max_fail is None else max_fail
    mk = config.KR_QUALITY_MIN_KNOWN if min_known is None else min_known
    return floor <= screen.known_count < mk and screen.failed_count <= mf


def quality_pass(screen: Screen, market: str, us_min: int | None = None) -> bool:
    """화면 · 오늘 볼 종목이 같이 쓰는 '품질 통과' — 미국은 통과 수, 국내는 허용 미달 수."""
    import config  # noqa: PLC0415

    if market == "kr":
        return passes_kr(screen)
    return screen.ok and screen.passed_count >= (config.DISCOVER_QUALITY_MIN
                                                 if us_min is None else us_min)


def rank_with_eps(screens: list[Screen], eps: dict | None = None) -> list[Screen]:
    """rank_by_ratio 와 같은 순서에, 비율 · 통과 수가 같으면 **선행 EPS 90일 변화** 큰 순.

    eps = {티커: 변화율(소수) 또는 None}. 추정이 없는 종목은 같은 동점 묶음의 맨 뒤.
    (2026-11-13: 대시보드 원칙의 첫째가 Forward EPS 인데 순위에 쓰이지 않던 것)
    """
    eps = eps or {}

    def key(s):
        c = eps.get(s.ticker)
        return (-(s.judged_ratio or 0.0), -s.passed_count,
                c is None, -(c or 0.0), s.ticker)

    return sorted([s for s in screens if s.ok], key=key)


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
