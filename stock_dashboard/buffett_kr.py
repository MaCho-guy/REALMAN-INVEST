"""
국내주식 버핏식 스크리닝 — DART 사업보고서 기반.

미국 쪽(buffett.py)과 **같은 타입**(YearRow·Check·Screen)을 돌려주므로 화면
코드를 공유합니다. 다른 점은 셋입니다:

**1. 계정 체계가 다릅니다.** K-IFRS 는 us-gaap 과 계정 ID 도 이름도 다릅니다.
   그런데 한국 공시는 계정명이 상당히 표준화되어 있어(매출액·매출원가·
   당기순이익·자본총계), **이름 폴백이 미국보다 잘 듣습니다.**

**2. 보고서 1회에 3년이 들어옵니다.** `thstrm`(당기)·`frmtrm`(전기)·
   `bfefrmtrm`(전전기). 그래서 4회 요청으로 12년을 덮습니다. 미국
   companyfacts 가 1회에 전 기간을 주는 것과 다르지만, 여전히 효율적입니다.

**3. 기준선을 따로 둡니다 — 이게 중요합니다.**
   미국 기준(ROE 15% 이상 10년 중 8년)을 한국 종목에 그대로 적용하면
   거의 전부 탈락합니다. 기업이 나빠서가 아니라 한국 상장사의 ROE 분포가
   구조적으로 낮기 때문입니다(지배구조·낮은 배당성향·순환출자 등).
   기준을 그대로 쓰면 "한국 주식은 다 안 좋다" 는 결론이 나오는데,
   그건 기준이 틀린 것입니다. 그래서 `KR_THRESHOLDS` 를 따로 둡니다.

**인증키가 필요합니다** (DART). 미국 스크리너는 키가 없어도 됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass

import buffett
from buffett import Screen, Thresholds, YearRow

# ──────────────────────────────────────────────────────────────────────────────
# K-IFRS 계정 매칭
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KrAccount:
    """계정 하나를 찾는 규칙. XBRL 표준ID 우선, 계정명 폴백."""

    key: str
    label: str
    ids: tuple[str, ...]
    names: tuple[str, ...]
    sj: tuple[str, ...]        # 재무제표 구분 — BS/IS/CIS/CF
    #: 이 계정 ID 를 실제 응답에서 확인했는가. 전부 False 입니다 —
    #: 개발 환경에서 DART 가 차단되어 확인하지 못했습니다.
    verified: bool = False


KR_RULES: tuple[KrAccount, ...] = (
    KrAccount(
        "net_income", "당기순이익",
        ("ifrs-full_ProfitLoss",),
        ("당기순이익", "당기순이익(손실)", "연결당기순이익",
         "당기순이익(지배기업소유주지분)"),
        ("IS", "CIS"),
    ),
    # 2026-11-11 실제 응답 확인: 삼성전자·SK하이닉스 모두 표준ID 로 매칭.
    KrAccount(
        "revenue", "매출액",
        ("ifrs-full_Revenue",),
        ("매출액", "수익(매출액)", "영업수익", "매출"),
        ("IS", "CIS"),
        verified=True,
    ),
    # 2026-11-11 실제 응답 확인: 삼성전자(IS)·SK하이닉스(CIS) 모두 매칭.
    KrAccount(
        "cost_of_revenue", "매출원가",
        ("ifrs-full_CostOfSales",),
        ("매출원가",),
        ("IS", "CIS"),
        verified=True,
    ),
    KrAccount(
        "gross_profit", "매출총이익",
        ("ifrs-full_GrossProfit",),
        ("매출총이익", "매출총이익(손실)"),
        ("IS", "CIS"),
    ),
    KrAccount(
        "equity", "자본총계",
        ("ifrs-full_Equity",),
        ("자본총계", "자본"),
        ("BS",),
    ),
    KrAccount(
        "assets", "자산총계",
        ("ifrs-full_Assets",),
        ("자산총계",),
        ("BS",),
    ),
    KrAccount(
        "liabilities", "부채총계",
        ("ifrs-full_Liabilities",),
        ("부채총계",),
        ("BS",),
    ),
    KrAccount(
        "long_term_debt", "장기차입금",
        # 2026-11-12 전 종목 조사(tools/kr_account_survey.py): 장기차입금을 못 찾은
        # 85개 회사 가운데 일부는 아래 표준ID 로 적습니다. Borrowings 는 장 · 단기를
        # 합친 총차입이라 부채가 크게 잡힙니다 (기준에는 보수적인 쪽).
        ("ifrs-full_LongtermBorrowings", "dart_LongTermBorrowingsGross",
         "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "ifrs-full_Borrowings"),
        ("장기차입금", "사채", "비유동차입금", "장기성차입금", "장기차입부채"),
        ("BS",),
    ),
    KrAccount(
        "short_term_debt", "단기차입금",
        ("ifrs-full_ShorttermBorrowings",
         "ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
         "ifrs-full_CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived"),
        ("단기차입금", "유동성장기부채", "유동차입금"),
        ("BS",),
    ),
    KrAccount(
        "cash", "현금및현금성자산",
        ("ifrs-full_CashAndCashEquivalents", "dart_CashAndDuefromBanks"),
        ("현금및현금성자산", "현금및현금성자산등", "현금및예치금"),
        ("BS",),
    ),
    KrAccount(
        "short_term_investments", "단기금융상품",
        ("dart_ShortTermDepositsNotClassifiedAsCashEquivalents",),
        ("단기금융상품", "단기투자자산", "당기손익-공정가치금융자산"),
        ("BS",),
    ),
    KrAccount(
        "retained_earnings", "이익잉여금",
        ("ifrs-full_RetainedEarnings",),
        ("이익잉여금", "이익잉여금(결손금)"),
        ("BS",),
    ),
    KrAccount(
        "dep_amort", "감가상각비",
        ("ifrs-full_DepreciationAndAmortisationExpense",),
        ("감가상각비", "감가상각비및무형자산상각비", "유형자산감가상각비",
         "감가상각비와 무형자산상각비"),
        ("CF",),
    ),
    KrAccount(
        "capex", "유형자산의 취득",
        ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",),
        ("유형자산의 취득", "유형자산의취득", "유형자산 취득",
         "설비투자", "유형자산의 증가"),
        ("CF",),
    ),
    KrAccount(
        "operating_cash_flow", "영업활동현금흐름",
        ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
        ("영업활동현금흐름", "영업활동으로인한현금흐름",
         "영업활동으로 인한 현금흐름", "영업활동 현금흐름"),
        ("CF",),
    ),
    # ── ROIC · 이자보상배율용 ───────────────────────────────────────────────
    # 이걸 넣지 않으면 **국내 종목만** 새 기준 3개가 전부 '판정 불가' 가 되어
    # 점수가 불리해집니다. 전부 미검증입니다.
    KrAccount(
        "operating_income", "영업이익",
        ("dart_OperatingIncomeLoss",
         "ifrs-full_ProfitLossFromOperatingActivities"),
        ("영업이익", "영업이익(손실)", "영업손익"),
        ("IS", "CIS"),
    ),
    KrAccount(
        "interest_expense", "이자비용",
        ("ifrs-full_FinanceCosts", "ifrs-full_InterestExpense"),
        ("이자비용", "금융원가", "금융비용", "이자비용(금융원가)"),
        ("IS", "CIS"),
    ),
    KrAccount(
        "tax_expense", "법인세비용",
        ("ifrs-full_IncomeTaxExpenseContinuingOperations",),
        ("법인세비용", "법인세비용(수익)", "법인세수익(비용)"),
        ("IS", "CIS"),
    ),
    KrAccount(
        "pretax_income", "법인세비용차감전순이익",
        ("ifrs-full_ProfitLossBeforeTax",),
        ("법인세비용차감전순이익", "법인세차감전순이익",
         "법인세비용차감전순이익(손실)", "법인세차감전계속사업이익"),
        ("IS", "CIS"),
    ),
)

KR_RULES_BY_KEY = {r.key: r for r in KR_RULES}

#: 국내 재무를 읽는 방식이 바뀔 때마다 올립니다 (미국의 buffett.SCREEN_REV 와 따로 —
#: 미국 쪽만 바뀌었을 때 19분짜리 DART 심사를 다시 돌리지 않으려고).
#:   4 (2026-11-12): 연결재무제표가 없는 회사는 별도로 · 차입금 · 현금 표준ID 추가 ·
#:                   통과 판정을 '판정된 기준 중 비율' 로 (감가상각비가 재무제표 본문에
#:                   없어 주주이익 · 설비투자 기준이 대부분 판정 불가이기 때문)
#:   5 (2026-11-13): 성장 지표(growth.metrics → `gr`) — 연간 숫자가 심사 중에만 메모리에 있어
#:                   다시 심사해야 채워짐 (DART 약 19분 한 번)
KR_REV = 5


def find_account(accounts, rule: KrAccount):
    """계정 하나를 찾습니다. 표준ID → 정확한 이름 → 부분일치(가장 짧은 것).

    부분일치에서 **가장 짧은 계정명**을 고르는 이유: '매출액' 을 찾을 때
    '매출액증가율' 을, '재고자산' 을 찾을 때 '재고자산평가손실누계액' 을
    집지 않기 위해서입니다. cycle.py 와 같은 규칙입니다.
    """
    pool = [a for a in accounts if not rule.sj or a.sj_div in rule.sj]

    for wanted in rule.ids:
        for a in pool:
            if a.account_id == wanted:
                return a

    for wanted in rule.names:
        for a in pool:
            if a.account_nm.strip() == wanted:
                return a

    candidates = [
        a for a in pool
        for wanted in rule.names
        if wanted.replace(" ", "") in a.account_nm.replace(" ", "")
    ]
    if candidates:
        return min(candidates, key=lambda a: len(a.account_nm))
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 한국 기준선
# ──────────────────────────────────────────────────────────────────────────────

#: 미국 기준을 그대로 쓰면 한국 종목은 거의 전부 탈락합니다. 기업이 나빠서가
#: 아니라 분포가 다르기 때문입니다. 아래는 **분포를 감안해 제가 낮춘 값**이고,
#: 버핏의 원래 숫자가 아닙니다 — 화면에 '제 기준' 으로 표시됩니다.
KR_THRESHOLDS: dict[str, float] = {
    "roe_min": 10.0,                      # 미국 15% → 한국 10%
    "roe_years_required": 7,              # 10년 중 (미국 8년)
    "owner_earnings_years_required": 7,
    "capex_heavy_years_allowed": 4,       # 제조업 비중이 높아 1년 더 허용
    "debt_to_equity_max": 0.6,            # 미국 0.5
    "debt_years_max": 5.0,                # 미국 4.0
    "margin_stdev_max": 7.0,              # %p — 미국 5.0. 수출 비중이 커 변동이 큽니다
    "bad_years_allowed": 2,               # 미국 1회
    "earnings_drop_pct": 35.0,            # 미국 30%
    "min_years": 5,
}


def kr_thresholds(overrides: dict | None = None) -> Thresholds:
    merged = dict(KR_THRESHOLDS)
    if overrides:
        merged.update(overrides)
    fields = {}
    for key, value in merged.items():
        fields[key] = (int(value)
                       if key.endswith(("_required", "_allowed", "_years"))
                       else value)
    return Thresholds(**fields)


# ──────────────────────────────────────────────────────────────────────────────
# DART 응답 → 연도별 숫자
# ──────────────────────────────────────────────────────────────────────────────

def years_from_report(accounts, report_year: int) -> list[YearRow]:
    """사업보고서 하나에서 **3개 연도**를 뽑습니다.

    DART 는 당기·전기·전전기를 함께 줍니다. 그래서 보고서 1회로 3년이 나오고,
    4회 요청이면 12년을 덮습니다.

    주의: 사업보고서의 손익·현금흐름은 **연간 금액**입니다. 분기보고서와
    달리 누적/3개월 구분 문제가 없습니다.
    """
    slots = (
        (report_year, "thstrm_amount"),
        (report_year - 1, "frmtrm_amount"),
        (report_year - 2, "bfefrmtrm_amount"),
    )

    rows: list[YearRow] = []
    for year, attr in slots:
        row = YearRow(year=year, end=f"{year}-12-31")
        found_any = False
        for rule in KR_RULES:
            account = find_account(accounts, rule)
            if account is None:
                continue
            value = getattr(account, attr, None)
            if value is None:
                continue
            if hasattr(row, rule.key):
                setattr(row, rule.key, value)
                found_any = True
        if found_any:
            rows.append(row)
    return rows


def merge_years(batches: list[list[YearRow]]) -> list[YearRow]:
    """여러 보고서에서 나온 연도들을 합칩니다.

    같은 연도가 여러 보고서에 나옵니다(당기 → 다음 해 전기 → 그다음 해 전전기).
    **최신 보고서의 값을 우선**합니다 — 재작성(restatement)이 반영된 쪽입니다.
    """
    by_year: dict[int, YearRow] = {}
    # 오래된 것부터 넣고 최신으로 덮습니다
    for batch in batches:
        for row in batch:
            existing = by_year.get(row.year)
            if existing is None:
                by_year[row.year] = row
                continue
            # 최신 보고서 값으로 덮되, 최신에 없는 항목은 기존 값을 살립니다
            for key in buffett.FLOW_KEYS + buffett.STOCK_KEYS:
                new_value = getattr(row, key, None)
                if new_value is not None:
                    setattr(existing, key, new_value)
    return [by_year[y] for y in sorted(by_year)]


def screen_company(stock_code: str, name: str,
                   report_batches: list[tuple[int, list]], *,
                   years: int = 10,
                   th: Thresholds | None = None) -> Screen:
    """국내 종목 하나를 스크리닝합니다.

    report_batches: [(보고서 연도, 계정 목록), ...] — 오래된 것부터
    """
    batches = [years_from_report(accounts, year)
               for year, accounts in report_batches]
    rows = merge_years(batches)[-years:]

    missing: list[str] = []
    if rows:
        for rule in KR_RULES:
            if all(getattr(r, rule.key, None) is None for r in rows
                   if hasattr(r, rule.key)):
                missing.append(rule.label)

    screen = Screen(ticker=stock_code, name=name or stock_code,
                    years=rows, missing_tags=missing)
    if not rows:
        screen.error = (
            "연간 재무 데이터를 찾지 못했습니다. 사업보고서 응답에서 계정을 "
            "하나도 매칭하지 못했습니다 — 화면의 진단에서 계정명을 확인하십시오."
        )
        return screen
    return buffett.run_checks(screen, th or kr_thresholds())


def fetch_and_screen(stock_code: str, corp_code: str, name: str, *,
                     latest_year: int, reports: int = 4,
                     years: int = 10, fs_div: str = "CFS",
                     th: Thresholds | None = None) -> Screen:
    """DART 에서 사업보고서 여러 해를 받아 스크리닝합니다.

    reports=4 면 4회 요청으로 약 12년을 덮습니다 (보고서당 3년).
    실패한 보고서는 건너뛰고 나머지로 진행합니다.
    """
    from sources import dart

    batches: list[tuple[int, list]] = []
    errors: list[str] = []
    # 3년 간격으로 거슬러 올라갑니다 — 겹치는 구간이 재작성 반영에 쓰입니다
    for i in range(reports):
        year = latest_year - i * 3
        try:
            accounts = dart.fetch_financials(corp_code, year, "FY",
                                             fs_div=fs_div)
            batches.append((year, accounts))
        except dart.DartError as exc:
            # 종속회사가 없어 연결재무제표를 내지 않는 회사 — 가장 최근 해에서 한 번만
            # 별도(OFS)로 바꿔 봅니다 (2026-11-12 조사: 350개 중 19개 회사).
            if i == 0 and fs_div == "CFS":
                try:
                    accounts = dart.fetch_financials(corp_code, year, "FY", fs_div="OFS")
                    batches.append((year, accounts))
                    fs_div = "OFS"
                    continue
                except dart.DartError:
                    pass
            errors.append(f"{year}: {exc}")

    if not batches:
        screen = Screen(ticker=stock_code, name=name)
        screen.error = ("사업보고서를 받아오지 못했습니다 — "
                        + "; ".join(errors[:3]))
        return screen

    batches.sort(key=lambda b: b[0])        # 오래된 것부터
    screen = screen_company(stock_code, name, batches, years=years, th=th)
    if errors and screen.ok:
        screen.missing_tags.append(
            f"일부 연도 조회 실패 ({len(errors)}건)")
    return screen
