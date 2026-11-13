"""
반도체 사이클 레이어 2 — 재고 지표를 공시에서 직접 계산.

================================================================================
무엇을 계산하나 (지표체계 v2 레이어 2)
================================================================================
    DIO            = 기말 재고 ÷ 매출원가 × 기간일수
    재고-매출 갭    = 재고 증가율 − 매출 증가율   (플러스로 벌어지면 경고)
    재고 구성      = 원재료 / 재공품 / 완제품 비중  (완제품 급증이 최악)

문서의 지침 그대로입니다 — **DIO 절대값은 무의미하고, 자사 역사적 밴드 내
위치가 신호**입니다. 그래서 이 모듈은 단일 분기가 아니라 여러 분기를 모아
밴드(최소·중간값·최대)와 현재 위치를 함께 돌려줍니다.

================================================================================
계정 매칭 — 여기가 가장 깨지기 쉬운 지점입니다
================================================================================
`account_nm == "매출액"` 으로 필터링하면 절반이 빈 값으로 빠집니다. 기업마다
계정명을 다르게 씁니다 (매출액 / 수익(매출액) / 영업수익 …).

그래서 **XBRL 표준계정ID(account_id)를 1순위**로 맞추고, 표준ID가 없을 때만
계정명 후보 목록으로 폴백합니다. 둘 다 실패하면 숫자를 추정하지 않고
None 을 돌려주고 어느 계정을 못 찾았는지 기록합니다.

================================================================================
기간 주의
================================================================================
분기 손익계산서의 thstrm_amount 는 **3개월 금액**, thstrm_add_amount 가 누적입니다.
DIO 는 분모가 기간 매출원가라 기간일수를 맞춰야 합니다:
    분기 보고서 → 3개월 매출원가 × 91.25일
    사업보고서  → 연간 매출원가 × 365일
이 모듈은 분기면 3개월 금액을 쓰고 기간일수를 91.25 로 둡니다.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

from sources.dart import Account

# ──────────────────────────────────────────────────────────────────────────────
# 계정 매칭 규칙 — (XBRL 표준ID 후보, 계정명 후보, 재무제표 구분)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AccountRule:
    label: str
    ids: tuple[str, ...]
    names: tuple[str, ...]
    sj: tuple[str, ...]          # 찾을 재무제표 구분 (BS/IS/CIS)


RULES: dict[str, AccountRule] = {
    "inventory": AccountRule(
        "재고자산",
        ids=("ifrs-full_Inventories", "ifrs_Inventories"),
        names=("재고자산",),
        sj=("BS",),
    ),
    "cost_of_sales": AccountRule(
        "매출원가",
        ids=("ifrs-full_CostOfSales", "ifrs_CostOfSales"),
        names=("매출원가",),
        sj=("IS", "CIS"),
    ),
    "revenue": AccountRule(
        "매출액",
        ids=("ifrs-full_Revenue", "ifrs_Revenue",
             "ifrs-full_RevenueFromContractsWithCustomers"),
        names=("매출액", "수익(매출액)", "영업수익", "매출"),
        sj=("IS", "CIS"),
    ),
    # 재고 구성 — **실제 응답으로 확인했습니다(2026-11): 없습니다.**
    # 삼성전자·SK하이닉스 2026 2Q 응답에서 재고 관련 계정은
    # ifrs-full_Inventories(재고자산) 한 줄뿐이었습니다. 구성(원재료·
    # 재공품·완제품)은 사업보고서 **주석**에 있고, fnlttSinglAcntAll 은
    # 본표만 주므로 이 경로로는 받을 수 없습니다.
    #
    # 그래도 규칙을 남겨 두는 이유: 회사·분기에 따라 본표에 싣는 경우가
    # 있고, 있으면 쓰는 게 맞기 때문입니다. 없다고 추정하지 않습니다.
    "raw_materials": AccountRule(
        "원재료",
        ids=("ifrs-full_CurrentRawMaterialsAndCurrentProductionSupplies",
             "ifrs-full_RawMaterials"),
        names=("원재료", "원재료및부재료"),
        sj=("BS",),
    ),
    "work_in_progress": AccountRule(
        "재공품",
        ids=("ifrs-full_CurrentWorkInProgress", "ifrs-full_WorkInProgress"),
        names=("재공품", "반제품및재공품"),
        sj=("BS",),
    ),
    "finished_goods": AccountRule(
        "완제품",
        ids=("ifrs-full_CurrentFinishedGoods", "ifrs-full_FinishedGoods"),
        names=("제품", "완제품", "제품및상품"),
        sj=("BS",),
    ),
}

NOT_STANDARD = "-표준계정코드 미사용-"

#: DIO 타당 범위(일). 이 밖의 값은 기간 불일치로 보고 버립니다.
#: 반도체 제조사의 DIO 는 역사적으로 대략 60~200일 구간이고, 최악의 적체에서도
#: 300일을 넘기는 일은 드뭅니다. 400일을 넘으면 거의 확실히 계산 오류입니다.
DIO_MIN_DAYS = 5.0
DIO_MAX_DAYS = 400.0


def _norm(text: str) -> str:
    return "".join(text.split()).replace("(", "").replace(")", "")


def find_account(accounts: list[Account], rule: AccountRule) -> Account | None:
    """표준ID 우선, 계정명 폴백으로 계정 한 줄을 찾습니다."""
    pool = [a for a in accounts if not rule.sj or a.sj_div in rule.sj]

    # 1순위 — XBRL 표준계정ID 정확 일치
    for want in rule.ids:
        for acc in pool:
            if acc.account_id == want:
                return acc

    # 2순위 — 계정명 정확 일치 (공백·괄호 제거 후)
    wanted_names = {_norm(n) for n in rule.names}
    for acc in pool:
        if _norm(acc.account_nm) in wanted_names:
            return acc

    # 3순위 — 계정명 포함 (가장 짧은 것을 고름: '재고자산' vs '재고자산평가손실')
    candidates = [
        acc for acc in pool
        if any(_norm(n) in _norm(acc.account_nm) for n in rule.names)
    ]
    if candidates:
        return min(candidates, key=lambda a: len(a.account_nm))
    return None


def pick_amount(acc: Account | None, *, period: str) -> float | None:
    """계정에서 해당 기간 금액을 꺼냅니다.

    period "quarter" 면 3개월 금액(thstrm_amount), "cumulative" 면 누적.
    재무상태표(BS)는 시점 값이라 period 와 무관하게 thstrm_amount 입니다.
    """
    if acc is None:
        return None
    if acc.sj_div == "BS":
        return acc.thstrm_amount
    if period == "cumulative" and acc.thstrm_add_amount is not None:
        return acc.thstrm_add_amount
    return acc.thstrm_amount


# ──────────────────────────────────────────────────────────────────────────────
# 분기 스냅샷
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class QuarterMetrics:
    """한 분기의 재고 지표."""

    year: int
    quarter: str                 # 1Q / 2Q / 3Q / FY
    fs_div: str                  # CFS / OFS

    inventory: float | None = None
    cost_of_sales: float | None = None
    revenue: float | None = None
    raw_materials: float | None = None
    work_in_progress: float | None = None
    finished_goods: float | None = None

    #: 찾지 못한 계정 라벨
    missing: list[str] = field(default_factory=list)

    #: 실제 구간 일수를 아는 경우(XBRL)에 설정합니다. DART 는 보고서 종류로만
    #: 추정할 수 있어 None 입니다.
    explicit_period_days: float | None = None

    #: 구간 종료일(YYYY-MM-DD). XBRL 경로에서만 채워집니다. 시계열 정렬에
    #: 씁니다 — fy/fp 는 비어 있거나 회계연도 표기가 어긋날 수 있는데 종료일은
    #: 항상 있고 항상 단조증가합니다.
    period_end: str | None = None

    @property
    def period_days(self) -> float:
        """DIO 분모의 기간일수.

        XBRL 은 구간의 시작·종료일을 알려주므로 실제 일수를 씁니다 — 마이크론의
        53주 회계연도(14주 분기)까지 정확히 반영됩니다.
        DART 는 보고서 종류만 알 수 있어 사업보고서 365일 / 분기 91.25일로 둡니다.
        """
        if self.explicit_period_days:
            return self.explicit_period_days
        return 365.0 if self.quarter == "FY" else 91.25

    @property
    def label(self) -> str:
        q = {"1Q": "1분기", "2Q": "반기", "3Q": "3분기", "FY": "연간",
             "Q1": "1분기", "Q2": "2분기", "Q3": "3분기", "Q4": "4분기"}.get(
            self.quarter, self.quarter)
        return f"{self.year} {q}"

    @property
    def dio_raw(self) -> float | None:
        """기간일수를 적용한 DIO. 타당성 검사 전 값."""
        if not self.inventory or not self.cost_of_sales:
            return None
        if self.cost_of_sales <= 0:
            return None
        return self.inventory / self.cost_of_sales * self.period_days

    @property
    def dio(self) -> float | None:
        """재고자산회전일수. 타당 범위를 벗어나면 None (쓰지 않습니다).

        DIO 가 비정상이면 거의 항상 **기간 불일치**입니다 — 분기 손익계산서에서
        3개월 금액이 와야 할 자리에 누적 금액이 오거나, 사업보고서 금액에
        91.25일을 적용한 경우입니다. 그런 값으로 밴드를 만들면 전부 왜곡되므로,
        계산해서 보여주는 대신 버리고 경고를 남깁니다.
        """
        value = self.dio_raw
        if value is None:
            return None
        return value if DIO_MIN_DAYS <= value <= DIO_MAX_DAYS else None

    @property
    def dio_warning(self) -> str:
        """DIO 가 버려진 이유. 정상이면 빈 문자열."""
        value = self.dio_raw
        if value is None or DIO_MIN_DAYS <= value <= DIO_MAX_DAYS:
            return ""
        return (
            f"{self.label} DIO 계산값이 {value:.0f}일로 타당 범위"
            f"({DIO_MIN_DAYS:.0f}~{DIO_MAX_DAYS:.0f}일)를 벗어나 제외했습니다. "
            f"보고서의 매출원가가 기간({self.period_days:.2f}일)과 맞지 않을 수 있습니다 "
            f"— 분기 보고서인데 누적 금액이 왔거나 그 반대입니다."
        )

    @property
    def inventory_mix(self) -> dict[str, float] | None:
        """재고 구성 비중(%). 세 항목 중 하나라도 없으면 None."""
        parts = {
            "원재료": self.raw_materials,
            "재공품": self.work_in_progress,
            "완제품": self.finished_goods,
        }
        if any(v is None for v in parts.values()):
            return None
        total = sum(v for v in parts.values() if v is not None)
        if total <= 0:
            return None
        return {k: (v or 0.0) / total * 100.0 for k, v in parts.items()}


def metrics_from_accounts(accounts: list[Account], year: int, quarter: str,
                          fs_div: str) -> QuarterMetrics:
    """재무제표 계정 목록에서 한 분기 지표를 뽑아냅니다."""
    out = QuarterMetrics(year=year, quarter=quarter, fs_div=fs_div)
    period = "quarter"

    for key, rule in RULES.items():
        acc = find_account(accounts, rule)
        value = pick_amount(acc, period=period)
        if value is None:
            out.missing.append(rule.label)
        setattr(out, key, value)

    return out


# ──────────────────────────────────────────────────────────────────────────────
# 시계열 — 밴드 내 위치가 신호
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class InventoryTrend:
    """여러 분기를 모은 재고 추세. 오래된 것 → 최신 순서로 담습니다."""

    corp_name: str
    stock_code: str
    quarters: list[QuarterMetrics] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def latest(self) -> QuarterMetrics | None:
        return self.quarters[-1] if self.quarters else None

    @property
    def dio_series(self) -> list[tuple[str, float]]:
        return [(q.label, q.dio) for q in self.quarters if q.dio is not None]

    @property
    def dio_band(self) -> tuple[float, float, float] | None:
        """(최소, 중간값, 최대). 2개 미만이면 None — 밴드라고 부를 수 없습니다."""
        values = [v for _l, v in self.dio_series]
        if len(values) < 2:
            return None
        return min(values), statistics.median(values), max(values)

    @property
    def dio_position(self) -> float | None:
        """밴드 내 위치(0~100%). 최소=0, 최대=100."""
        band = self.dio_band
        latest = self.latest
        if band is None or latest is None or latest.dio is None:
            return None
        low, _mid, high = band
        if high - low <= 0:
            return None
        return (latest.dio - low) / (high - low) * 100.0

    @property
    def dio_qoq_change(self) -> float | None:
        """직전 분기 대비 DIO 변화(일)."""
        vals = [v for _l, v in self.dio_series]
        if len(vals) < 2:
            return None
        return vals[-1] - vals[-2]

    @property
    def dio_rising_quarters(self) -> int:
        """DIO 가 연속 상승한 분기 수. 체크리스트의 '2분기 연속 상승' 판정용."""
        vals = [v for _l, v in self.dio_series]
        count = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] > vals[i - 1]:
                count += 1
            else:
                break
        return count

    @property
    def inventory_revenue_gap(self) -> float | None:
        """재고 증가율 − 매출 증가율 (%포인트). 플러스면 경고.

        직전 분기 대비(QoQ)로 계산합니다. 전년동기 데이터는 같은 보고서에
        frmtrm_amount 로 들어오지만 재고 구성까지 일관되게 맞추기 어려워,
        수집한 분기 시계열로 QoQ 를 씁니다.
        """
        if len(self.quarters) < 2:
            return None
        prev, cur = self.quarters[-2], self.quarters[-1]
        if not (prev.inventory and cur.inventory and prev.revenue and cur.revenue):
            return None
        if prev.inventory <= 0 or prev.revenue <= 0:
            return None
        inv_growth = (cur.inventory / prev.inventory - 1) * 100
        rev_growth = (cur.revenue / prev.revenue - 1) * 100
        return inv_growth - rev_growth

    @property
    def all_missing(self) -> list[str]:
        """어느 계정을 못 찾았는지 (중복 제거)."""
        seen: list[str] = []
        for q in self.quarters:
            for m in q.missing:
                if m not in seen:
                    seen.append(m)
        return seen

    @property
    def dio_warnings(self) -> list[str]:
        """기간 불일치로 버린 분기들의 경고 문구."""
        return [w for w in (q.dio_warning for q in self.quarters) if w]


# ──────────────────────────────────────────────────────────────────────────────
# 미국 기업 — EDGAR XBRL 에서 같은 추세를 만듭니다
# ──────────────────────────────────────────────────────────────────────────────

#: us-gaap 태그 후보. 기업마다 쓰는 태그가 달라 순서대로 시도합니다.
XBRL_TAGS = {
    "inventory": ("InventoryNet", "InventoryGross",
                  "InventoryFinishedGoodsNetOfReserves"),
    "cost_of_sales": ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfSales"),
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    "finished_goods": ("InventoryFinishedGoods", "InventoryFinishedGoodsNetOfReserves"),
    "work_in_progress": ("InventoryWorkInProcess",
                         "InventoryWorkInProcessNetOfReserves"),
    "raw_materials": ("InventoryRawMaterials",
                      "InventoryRawMaterialsNetOfReserves"),
}


def build_trend_from_xbrl(
    corp_name: str, ticker: str,
    inventory: list, cost_of_sales: list, revenue: list,
    *, quarters: int = 6, errors: list[str] | None = None,
) -> InventoryTrend:
    """EDGAR XBRL Fact 목록에서 재고 추세를 만듭니다.

    DART 경로와 **같은 InventoryTrend 를 돌려주므로** 화면·체크리스트·신호 코드가
    한국 기업과 미국 기업을 구분하지 않습니다.

    분기 구간만 씁니다 — 연간 구간을 섞으면 DIO 기간이 어긋납니다.
    """
    from sources.edgar_xbrl import align_instant_to_duration

    trend = InventoryTrend(corp_name=corp_name, stock_code=ticker,
                           errors=list(errors or []))

    cos_quarters = [f for f in cost_of_sales if f.is_quarterly]
    if not cos_quarters:
        trend.errors.append(
            "분기 구간의 매출원가를 찾지 못했습니다 "
            f"(수집 {len(cost_of_sales)}건, 분기 0건)."
        )
        return trend

    rev_by_period = {(f.start, f.end): f for f in revenue if f.is_quarterly}
    pairs = align_instant_to_duration(
        [f for f in inventory if f.is_instant], cos_quarters)

    # 최근 분기부터 quarters 개
    pairs.sort(key=lambda p: p[1].end, reverse=True)
    pairs = pairs[:quarters]

    for inv_fact, cos_fact in pairs:
        rev_fact = rev_by_period.get((cos_fact.start, cos_fact.end))
        days = cos_fact.duration_days or 91

        metrics = QuarterMetrics(
            year=cos_fact.fy or int(cos_fact.end[:4]),
            quarter=cos_fact.fp or "Q?",
            fs_div="XBRL",
            inventory=inv_fact.val,
            cost_of_sales=cos_fact.val,
            revenue=rev_fact.val if rev_fact else None,
        )
        # XBRL 은 실제 구간 일수를 알려주므로 그대로 씁니다 (53주 회계연도 대응)
        metrics.explicit_period_days = float(days)
        metrics.period_end = cos_fact.end
        if rev_fact is None:
            metrics.missing.append("매출액")
        trend.quarters.append(metrics)

    # 종료일로 정렬합니다. 회계연도·분기 표기(fy/fp)로 정렬하면 세 가지가 깨집니다:
    #   · fp 가 비면 분기 순위를 못 정해 해당 연도 맨 앞으로 밀림
    #   · "FY" 와 "Q4" 가 같은 순위라 10-K 구간과 4분기 구간이 뒤섞임
    #   · fy 가 없으면 종료일 연도로 대체되는데 회계연도와 어긋남
    #     (마이크론 FY2026 Q1 은 2025-12 종료 → 2025 로 잡힘)
    # 종료일은 항상 있고 항상 단조증가하므로 이쪽이 안전합니다.
    trend.quarters.sort(key=lambda q: q.period_end or "")
    return trend


def build_trend(corp_name: str, stock_code: str,
                collected: list[tuple[int, str, str, list[Account]]],
                errors: list[str] | None = None) -> InventoryTrend:
    """수집한 (연도, 분기, fs_div, 계정목록) 들을 추세로 묶습니다."""
    trend = InventoryTrend(corp_name=corp_name, stock_code=stock_code,
                           errors=list(errors or []))
    for year, quarter, fs_div, accounts in collected:
        trend.quarters.append(metrics_from_accounts(accounts, year, quarter, fs_div))

    order = {"1Q": 1, "2Q": 2, "3Q": 3, "FY": 4}
    trend.quarters.sort(key=lambda q: (q.year, order.get(q.quarter, 0)))
    return trend


# ──────────────────────────────────────────────────────────────────────────────
# 체크리스트 판정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckItem:
    label: str
    lit: bool | None        # True 점등, False 미점등, None 판정 불가
    detail: str = ""


#: 체크리스트 기준선 — 화면의 '판단 근거' 카드가 이 값을 그대로 읽어 적습니다.
DIO_RISING_MIN = 2          # DIO 가 이만큼 연속 상승하면 점등 (분기)
FINISHED_JUMP_PP = 3.0      # 완제품 비중이 직전 분기보다 이만큼 늘면 점등 (%포인트)


def judgement_rules() -> list[dict]:
    """이 화면이 사이클을 어떻게 읽는지 — 지표 · 계산식 · 점등 조건 (2026-11-13
    사용자: "어떻게 판단하는지 그 판단 근거를 접을 수 있는 카드로")."""
    return [
        {"short": "DIO (재고일수)",
         "rule": "기말 재고 ÷ 매출원가 × 기간일수 (분기 91.25일 · 연간 365일). 재고를 다 "
                 "파는 데 걸리는 날 수. 절대값은 회사마다 달라 비교하지 않고 아래 '밴드 내 "
                 f"위치' 로 읽음. {DIO_MIN_DAYS:g}일 미만 · {DIO_MAX_DAYS:g}일 초과는 기간이 "
                 "안 맞는 값으로 보고 버림"},
        {"short": "밴드 내 위치",
         "rule": "수집한 분기들의 DIO 최소 = 0% · 최대 = 100% 로 놓고 최신 분기가 어디인지. "
                 "100% 에 가까울수록 그 회사 기준으로 재고가 많이 쌓인 상태. 분기가 2개 "
                 "미만이면 계산하지 않음"},
        {"short": "① DIO 연속 상승",
         "rule": f"DIO 가 {DIO_RISING_MIN}분기 연속 직전 분기보다 높으면 점등. 재고가 "
                 "팔리는 속도보다 빨리 쌓이기 시작했다는 뜻"},
        {"short": "② 재고-매출 갭",
         "rule": "재고 증가율 − 매출 증가율 (직전 분기 대비, %포인트)이 0 보다 크면 점등. "
                 "매출보다 재고가 빨리 늘면 수요가 생산을 못 따라가는 것"},
        {"short": "③ 완제품 비중 급증",
         "rule": f"재고 중 완제품 비중이 직전 분기보다 {FINISHED_JUMP_PP:g}%포인트 이상 "
                 "늘면 점등. 원재료 · 재공품이 아니라 '만들어 놓고 못 판 것' 이 늘어난 "
                 "경우. 재고 구성은 주석 항목이라 없으면 '판정 불가'"},
        {"short": "읽는 법",
         "rule": "점등이 많을수록 재고 쪽에서 본 하강 신호. 세 회사가 같이 켜지면 업황, "
                 "한 회사만 켜지면 그 회사 사정일 가능성. 한 점수로 합치지 않고 항목별로 봄"},
        {"short": "보지 않는 것",
         "rule": "메모리 가격(DRAM · NAND 현물 · 고정가) · CapEx · 수요는 공시 재무제표에서 "
                 "계산할 수 없어 여기서 판정하지 않음. 잠정실적 레이더는 공시가 떴는지만 "
                 "알리고 숫자는 읽지 않음"},
    ]


def checklist(trend: InventoryTrend) -> list[CheckItem]:
    """지표체계 v2 §5 중 재고 관련 항목만 자동 판정합니다.

    가격·CapEx·수요 항목은 공시에서 계산할 수 없어 여기서 다루지 않습니다.
    """
    items: list[CheckItem] = []

    rising = trend.dio_rising_quarters
    if not trend.dio_series:
        items.append(CheckItem("자사 DIO 2분기 연속 상승", None, "DIO 계산 불가"))
    else:
        items.append(CheckItem(
            "자사 DIO 2분기 연속 상승",
            rising >= DIO_RISING_MIN,
            f"연속 상승 {rising}분기"
            + (f" · 직전 분기 대비 {trend.dio_qoq_change:+.1f}일"
               if trend.dio_qoq_change is not None else ""),
        ))

    gap = trend.inventory_revenue_gap
    if gap is None:
        items.append(CheckItem("재고-매출 증가율 갭 플러스 전환", None, "계산 불가"))
    else:
        items.append(CheckItem(
            "재고-매출 증가율 갭 플러스 전환",
            gap > 0,
            f"{gap:+.1f}%포인트 (재고 증가율 − 매출 증가율, 직전 분기 대비)",
        ))

    latest = trend.latest
    mix = latest.inventory_mix if latest else None
    if mix is None:
        items.append(CheckItem(
            "완제품 재고 비중 급증", None,
            "재고 구성은 주석 항목이라 전체 재무제표 API 에 없을 수 있습니다 — 보고서 원문 확인 필요",
        ))
    else:
        prev_mix = (trend.quarters[-2].inventory_mix
                    if len(trend.quarters) >= 2 else None)
        if prev_mix is None:
            items.append(CheckItem(
                "완제품 재고 비중 급증", None,
                f"현재 완제품 {mix['완제품']:.1f}% · 비교할 직전 분기 구성 없음",
            ))
        else:
            delta = mix["완제품"] - prev_mix["완제품"]
            items.append(CheckItem(
                "완제품 재고 비중 급증",
                delta >= FINISHED_JUMP_PP,
                f"완제품 {prev_mix['완제품']:.1f}% → {mix['완제품']:.1f}% ({delta:+.1f}%p)",
            ))

    return items


# ──────────────────────────────────────────────────────────────────────────────
# 잠정실적 레이더 — 정식 보고서보다 먼저 나오는 숫자
# ──────────────────────────────────────────────────────────────────────────────
#
# 왜 보는가:
#
#   삼성전자·SK하이닉스는 분기 종료 후 **영업(잠정)실적**을 공정공시로 먼저
#   냅니다. 매출과 영업이익만 담긴 짧은 공시인데, 정식 분기보고서보다
#   2주 정도 빠릅니다. 재고 지표(레이어 2)는 정식 보고서의 재무상태표가
#   있어야 계산되므로, 그 사이 기간에는 잠정실적이 메모리 사이클에 대한
#   **가장 이른 확정 숫자**입니다.
#
#   이 레이더는 "그 공시가 떴는지" 만 알려줍니다. 안에 든 숫자를 파싱하지
#   않습니다 — 공정공시 본문은 표 형식이 회사·분기마다 달라서, 파싱해
#   조용히 틀린 숫자를 보여주는 것보다 "떴으니 열어보라" 가 낫습니다.

#: 공시 제목에 이 중 하나가 들어가면 잠정실적으로 봅니다.
#: DART 공시 제목은 회사마다 조금씩 달라서 부분 문자열로 맞춥니다.
PRELIM_PATTERNS: tuple[str, ...] = (
    "영업(잠정)실적",
    "잠정실적",
    "매출액또는손익구조",
    "손익구조30%",
    "손익구조15%",
)

#: 이 일수가 지난 잠정공시는 '지난 분기' 로 봅니다. 분기가 3개월이므로
#: 100일이면 다음 분기 공시가 나올 시점입니다.
PRELIM_FRESH_DAYS = 100


@dataclass
class PrelimFiling:
    """잠정실적 공시 하나."""

    corp_name: str
    report_nm: str
    rcept_dt: str               # YYYYMMDD
    url: str
    stock_code: str = ""

    @property
    def date_iso(self) -> str:
        d = self.rcept_dt
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return d

    @property
    def age_days(self) -> int | None:
        try:
            made = dt.date.fromisoformat(self.date_iso)
        except ValueError:
            return None
        return (dt.date.today() - made).days

    @property
    def is_fresh(self) -> bool:
        age = self.age_days
        return age is not None and age <= PRELIM_FRESH_DAYS

    @property
    def age_label(self) -> str:
        age = self.age_days
        if age is None:
            return ""
        if age == 0:
            return "오늘"
        return f"{age}일 전"


def is_preliminary(report_nm: str) -> bool:
    """공시 제목이 잠정실적인가. 공백을 지우고 비교합니다 —
    DART 제목에는 공백이 들쭉날쭉 들어갑니다."""
    squashed = "".join(report_nm.split())
    return any(p in squashed for p in PRELIM_PATTERNS)


#: 8-K 항목 2.02 = Results of Operations and Financial Condition.
#: 미국은 제목을 대조할 필요가 없습니다 — SEC 가 항목 번호를 직접 줍니다.
#: 제목 문자열보다 정확하고, 회사가 표현을 바꿔도 깨지지 않습니다.
EARNINGS_8K_ITEM = "2.02"


def prelim_from_filings(filings, ticker: str, *, name: str = "",
                        limit: int = 8) -> list[PrelimFiling]:
    """EDGAR 제출 목록에서 **실적 발표 8-K** 만 골라냅니다.

    한국의 영업(잠정)실적과 같은 성격입니다 — 10-Q 보다 먼저 나오는 숫자.
    MU 는 분기 마감 후 3~4주에 8-K(2.02)로 실적을 내고, 10-Q 는 그보다
    며칠에서 몇 주 뒤에 올라옵니다. 재고 지표는 10-Q 가 있어야 계산되니
    그 사이를 메우는 것이 이 레이더의 목적입니다.
    """
    out: list[PrelimFiling] = []
    for f in filings or ():
        form = (getattr(f, "form", "") or "").upper()
        if not form.startswith("8-K"):
            continue
        items = getattr(f, "items", "") or ""
        if EARNINGS_8K_ITEM not in items:
            continue
        filed = (getattr(f, "filing_date", "") or "").replace("-", "")
        out.append(PrelimFiling(
            corp_name=name or ticker,
            report_nm=f"{form} 실적 발표 (Item {EARNINGS_8K_ITEM})",
            rcept_dt=filed,
            url=getattr(f, "url", "") or "",
            stock_code=ticker,
        ))
    out.sort(key=lambda f: f.rcept_dt, reverse=True)
    return out[:limit]


def preliminary_radar(disclosures, *, limit: int = 8) -> list[PrelimFiling]:
    """공시 목록에서 잠정실적만 골라 **접수일 역순**으로 돌려줍니다.

    disclosures 는 sources.dart.Disclosure 목록입니다. 타입을 명시하지 않은
    것은 데모 데이터와 테스트 대역도 같은 속성만 있으면 받게 하려는 것입니다.
    """
    out: list[PrelimFiling] = []
    for d in disclosures or ():
        name = getattr(d, "report_nm", "") or ""
        if not is_preliminary(name):
            continue
        out.append(PrelimFiling(
            corp_name=getattr(d, "corp_name", "") or "",
            report_nm=name,
            rcept_dt=getattr(d, "rcept_dt", "") or "",
            url=getattr(d, "url", "") or "",
            stock_code=getattr(d, "stock_code", "") or "",
        ))
    out.sort(key=lambda f: f.rcept_dt, reverse=True)
    return out[:limit]
