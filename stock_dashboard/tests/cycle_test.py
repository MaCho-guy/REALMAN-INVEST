"""
사이클 레이어 2 (재고 지표) 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/cycle_test.py

검증 범위: XBRL 표준ID 우선 매칭, 계정명 폴백, 금액 파싱(음수·괄호·쉼표),
           DIO 계산과 기간일수, 밴드·연속상승·재고매출갭, 체크리스트 판정,
           DART 상태코드·corp_code 해석·분기 추정.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cycle  # noqa: E402
from cycle import RULES, AccountRule, find_account, metrics_from_accounts  # noqa: E402
from sources import dart  # noqa: E402
from sources.dart import Account, Disclosure, _amount  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def near(a, b, tol=0.01) -> bool:
    return a is not None and b is not None and abs(a - b) < tol


def acc(sj, aid, name, th, add=None, frm=None) -> Account:
    return Account(sj_div=sj, sj_nm="x", account_id=aid, account_nm=name,
                   thstrm_amount=th, thstrm_add_amount=add,
                   frmtrm_amount=frm, bfefrmtrm_amount=None)


print("=== 금액 파싱 ===")
for raw, want in (("1,234,567", 1234567.0), ("-5,000", -5000.0),
                  ("(3,200)", -3200.0), ("", None), ("-", None),
                  (None, None), ("abc", None), ("0", 0.0)):
    got = _amount(raw)
    check(f"{raw!r} → {want!r}", got == want, repr(got))

print("\n=== 계정 매칭: XBRL 표준ID 1순위 ===")
pool = [
    acc("BS", "ifrs-full_Inventories", "재고자산", 72_000_000),
    acc("BS", cycle.NOT_STANDARD, "재고자산평가손실누계액", -1_000_000),
    acc("IS", "ifrs-full_CostOfSales", "매출원가", 40_000_000, add=118_000_000),
    acc("IS", "ifrs-full_Revenue", "수익(매출액)", 90_000_000, add=260_000_000),
]
inv = find_account(pool, RULES["inventory"])
check("재고자산 — 표준ID 로 찾음", inv is not None and inv.thstrm_amount == 72_000_000)
check("평가손실 계정을 집지 않음", inv is not None and "평가손실" not in inv.account_nm,
      inv.account_nm if inv else "")
rev = find_account(pool, RULES["revenue"])
check("매출액 — 계정명이 '수익(매출액)' 이어도 표준ID 로 찾음",
      rev is not None and rev.thstrm_amount == 90_000_000)

print("\n=== 계정 매칭: 표준ID 없을 때 계정명 폴백 ===")
nonstd = [
    acc("BS", cycle.NOT_STANDARD, "재고자산", 50.0),
    acc("IS", cycle.NOT_STANDARD, "영업수익", 300.0),
    acc("IS", cycle.NOT_STANDARD, "매출원가", 200.0),
]
check("재고자산 — 계정명 폴백",
      (find_account(nonstd, RULES["inventory"]) or acc("", "", "", 0)).thstrm_amount == 50.0)
check("영업수익 → 매출액 후보에 포함",
      (find_account(nonstd, RULES["revenue"]) or acc("", "", "", 0)).thstrm_amount == 300.0)

spaced = [acc("IS", cycle.NOT_STANDARD, "수익 (매출액)", 123.0)]
check("공백·괄호 차이를 무시하고 매칭",
      (find_account(spaced, RULES["revenue"]) or acc("", "", "", 0)).thstrm_amount == 123.0)

print("\n=== 계정 매칭: 재무제표 구분 필터 ===")
wrong_sj = [acc("CF", "ifrs-full_Inventories", "재고자산의 변동", 9.0)]
check("현금흐름표의 동명 계정은 재고자산으로 집지 않음",
      find_account(wrong_sj, RULES["inventory"]) is None)

print("\n=== 계정 매칭: 부분일치는 가장 짧은 계정명 ===")
partial = [
    acc("BS", cycle.NOT_STANDARD, "재고자산충당금", 1.0),
    acc("BS", cycle.NOT_STANDARD, "재고자산", 2.0),
    acc("BS", cycle.NOT_STANDARD, "재고자산평가손실", 3.0),
]
found = find_account(partial, RULES["inventory"])
check("정확 일치가 있으면 그것", found is not None and found.thstrm_amount == 2.0,
      found.account_nm if found else "")

only_partial = [acc("BS", cycle.NOT_STANDARD, "기타재고자산및선급금", 7.0)]
check("정확 일치 없으면 부분일치 허용",
      (find_account(only_partial, RULES["inventory"]) or acc("", "", "", 0)).thstrm_amount == 7.0)

check("아무것도 없으면 None",
      find_account([], RULES["inventory"]) is None)

print("\n=== pick_amount: BS 는 시점, IS 는 기간 ===")
bs = acc("BS", "x", "재고자산", 100.0, add=999.0)
check("BS 는 period 무관하게 thstrm_amount",
      cycle.pick_amount(bs, period="cumulative") == 100.0)
is_acc = acc("IS", "x", "매출원가", 40.0, add=118.0)
check("IS quarter → 3개월 금액", cycle.pick_amount(is_acc, period="quarter") == 40.0)
check("IS cumulative → 누적 금액", cycle.pick_amount(is_acc, period="cumulative") == 118.0)
check("누적이 없으면 3개월로 폴백",
      cycle.pick_amount(acc("IS", "x", "매출원가", 40.0), period="cumulative") == 40.0)
check("None 계정은 None", cycle.pick_amount(None, period="quarter") is None)

print("\n=== DIO 계산과 기간일수 ===")
m_q = metrics_from_accounts(pool, 2026, "3Q", "CFS")
# 재고 72,000,000 ÷ 매출원가 40,000,000 × 91.25일 = 164.25일
check("분기 DIO = 재고÷매출원가×91.25", near(m_q.dio, 72_000_000 / 40_000_000 * 91.25),
      f"{m_q.dio:.2f}" if m_q.dio else "None")
check("분기 기간일수 91.25", m_q.period_days == 91.25)

m_fy = metrics_from_accounts(pool, 2026, "FY", "CFS")
check("연간 기간일수 365", m_fy.period_days == 365.0)
# 이 pool 은 분기 규모 금액이라 FY 로 계산하면 657일 — 가드가 걸러냅니다.
check("연간 환산식 자체는 맞음 (raw)",
      near(m_fy.dio_raw, 72_000_000 / 40_000_000 * 365))
check("다만 657일이라 가드가 제외", m_fy.dio is None,
      f"raw={m_fy.dio_raw:.0f}")

check("매출원가 0 이면 DIO None",
      metrics_from_accounts(
          [acc("BS", "ifrs-full_Inventories", "재고자산", 10.0),
           acc("IS", "ifrs-full_CostOfSales", "매출원가", 0.0)],
          2026, "3Q", "CFS").dio is None)
check("재고 없으면 DIO None",
      metrics_from_accounts(
          [acc("IS", "ifrs-full_CostOfSales", "매출원가", 10.0)],
          2026, "3Q", "CFS").dio is None)

print("\n=== DIO 타당성 가드 (기간 불일치 탐지) ===")
# 분기 보고서에 연간 금액이 오면 DIO 가 폭발합니다 — 버리고 경고를 남겨야 합니다
mismatch = metrics_from_accounts(
    [acc("BS", "ifrs-full_Inventories", "재고자산", 100.0),
     acc("IS", "ifrs-full_CostOfSales", "매출원가", 50.0)],
    2026, "FY", "CFS")
check("730일은 타당 범위 밖 → dio None", mismatch.dio is None,
      f"raw={mismatch.dio_raw:.0f}")
check("raw 값은 남겨둠", near(mismatch.dio_raw, 730.0))
check("경고 문구에 계산값", "730일" in mismatch.dio_warning, mismatch.dio_warning[:50])
check("경고 문구에 원인 설명", "기간" in mismatch.dio_warning)

normal = metrics_from_accounts(
    [acc("BS", "ifrs-full_Inventories", "재고자산", 100.0),
     acc("IS", "ifrs-full_CostOfSales", "매출원가", 50.0)],
    2026, "1Q", "CFS")
check("182.5일은 정상 → dio 유효", near(normal.dio, 182.5))
check("정상이면 경고 없음", normal.dio_warning == "")

tiny = metrics_from_accounts(
    [acc("BS", "ifrs-full_Inventories", "재고자산", 1.0),
     acc("IS", "ifrs-full_CostOfSales", "매출원가", 100.0)],
    2026, "1Q", "CFS")
check("0.9일도 타당 범위 밖 (하한)", tiny.dio is None, f"raw={tiny.dio_raw:.2f}")

guarded = cycle.build_trend("x", "y", [
    (2026, "1Q", "CFS", [acc("BS", "ifrs-full_Inventories", "재고자산", 100.0),
                         acc("IS", "ifrs-full_CostOfSales", "매출원가", 50.0),
                         acc("IS", "ifrs-full_Revenue", "매출액", 90.0)]),
    (2026, "FY", "CFS", [acc("BS", "ifrs-full_Inventories", "재고자산", 100.0),
                         acc("IS", "ifrs-full_CostOfSales", "매출원가", 50.0),
                         acc("IS", "ifrs-full_Revenue", "매출액", 90.0)]),
])
check("이상값은 시계열에서 제외", len(guarded.dio_series) == 1, str(guarded.dio_series))
check("추세에 경고 수집", len(guarded.dio_warnings) == 1)
check("유효 분기 1개면 밴드 None (오염 방지)", guarded.dio_band is None)

print("\n=== 못 찾은 계정 기록 ===")
m_missing = metrics_from_accounts([acc("BS", "ifrs-full_Inventories", "재고자산", 1.0)],
                                  2026, "3Q", "CFS")
check("매출원가·매출액을 missing 에 기록",
      "매출원가" in m_missing.missing and "매출액" in m_missing.missing,
      str(m_missing.missing))
check("찾은 계정은 missing 에 없음", "재고자산" not in m_missing.missing)
check("숫자를 추정하지 않음", m_missing.cost_of_sales is None)

print("\n=== 재고 구성 비중 ===")
with_mix = pool + [
    acc("BS", "ifrs-full_CurrentRawMaterialsAndCurrentProductionSupplies", "원재료", 20.0),
    acc("BS", "ifrs-full_CurrentWorkInProgress", "재공품", 30.0),
    acc("BS", "ifrs-full_CurrentFinishedGoods", "제품", 50.0),
]
mix = metrics_from_accounts(with_mix, 2026, "3Q", "CFS").inventory_mix
check("구성 비중 합 100%", mix is not None and near(sum(mix.values()), 100.0))
check("완제품 50%", mix is not None and near(mix["완제품"], 50.0), str(mix))
check("한 항목이라도 없으면 None",
      metrics_from_accounts(pool, 2026, "3Q", "CFS").inventory_mix is None)

print("\n=== 추세: 밴드·연속상승·재고매출갭 ===")


def q(year, quarter, inv, cos, rev) -> tuple:
    rows = [
        acc("BS", "ifrs-full_Inventories", "재고자산", inv),
        acc("IS", "ifrs-full_CostOfSales", "매출원가", cos),
        acc("IS", "ifrs-full_Revenue", "매출액", rev),
    ]
    return (year, quarter, "CFS", rows)


trend = cycle.build_trend("삼성전자", "005930", [
    q(2025, "3Q", 50.0, 50.0, 100.0),    # DIO 91.25
    q(2026, "1Q", 60.0, 50.0, 100.0),    # DIO 109.5
    q(2026, "2Q", 70.0, 50.0, 100.0),    # DIO 127.75
    q(2026, "3Q", 80.0, 50.0, 105.0),    # DIO 146.0
])
check("분기 4개 수집", len(trend.quarters) == 4)
check("시간순 정렬", [x.label for x in trend.quarters][0] == "2025 3분기",
      str([x.label for x in trend.quarters]))
band = trend.dio_band
check("밴드 (최소·중간·최대)", band is not None and near(band[0], 91.25) and near(band[2], 146.0),
      str(band))
check("최신이 밴드 최상단 → 위치 100%", near(trend.dio_position, 100.0),
      f"{trend.dio_position:.1f}" if trend.dio_position else "None")
check("DIO 3분기 연속 상승", trend.dio_rising_quarters == 3, str(trend.dio_rising_quarters))
check("직전 분기 대비 +18.25일", near(trend.dio_qoq_change, 18.25),
      f"{trend.dio_qoq_change:.2f}" if trend.dio_qoq_change else "None")

# 재고 70→80 (+14.29%), 매출 100→105 (+5%) → 갭 +9.29%p
check("재고-매출 갭 플러스", near(trend.inventory_revenue_gap, (80/70-1)*100 - 5.0, 0.1),
      f"{trend.inventory_revenue_gap:+.2f}" if trend.inventory_revenue_gap else "None")

falling = cycle.build_trend("x", "y", [
    q(2026, "1Q", 80.0, 50.0, 100.0),
    q(2026, "2Q", 70.0, 50.0, 100.0),
    q(2026, "3Q", 60.0, 50.0, 100.0),
])
check("하락 추세면 연속상승 0", falling.dio_rising_quarters == 0)
check("최신이 밴드 최하단 → 위치 0%", near(falling.dio_position, 0.0),
      f"{falling.dio_position:.1f}" if falling.dio_position is not None else "None")

one = cycle.build_trend("x", "y", [q(2026, "3Q", 50.0, 50.0, 100.0)])
check("1분기만 있으면 밴드 None", one.dio_band is None)
check("1분기만 있으면 갭 None", one.inventory_revenue_gap is None)
check("1분기만 있어도 DIO 는 계산됨", one.latest is not None and one.latest.dio is not None)

empty = cycle.build_trend("x", "y", [])
check("빈 추세 — latest None", empty.latest is None)
check("빈 추세 — 예외 없음", empty.dio_band is None and empty.dio_position is None)

print("\n=== 체크리스트 판정 ===")
items = cycle.checklist(trend)
by_label = {i.label: i for i in items}
check("DIO 2분기 연속 상승 점등", by_label["자사 DIO 2분기 연속 상승"].lit is True,
      by_label["자사 DIO 2분기 연속 상승"].detail)
check("재고-매출 갭 점등", by_label["재고-매출 증가율 갭 플러스 전환"].lit is True)
check("완제품 비중은 판정 불가 (주석 항목)",
      by_label["완제품 재고 비중 급증"].lit is None,
      by_label["완제품 재고 비중 급증"].detail[:40])

items_f = {i.label: i for i in cycle.checklist(falling)}
check("하락 추세면 DIO 항목 미점등",
      items_f["자사 DIO 2분기 연속 상승"].lit is False)
check("하락 추세면 갭 미점등",
      items_f["재고-매출 증가율 갭 플러스 전환"].lit is False)

items_e = {i.label: i for i in cycle.checklist(empty)}
check("빈 추세는 전부 판정 불가",
      all(i.lit is None for i in items_e.values()))

print("\n=== DART: 상태코드 처리 ===")
for code, keyword in (("010", "등록되지 않은"), ("013", "조회된 데이터가 없습니다"),
                      ("020", "요청 제한"), ("901", "인증키")):
    check(f"{code} 메시지 존재", keyword in dart.STATUS_MESSAGES[code],
          dart.STATUS_MESSAGES[code][:30])

try:
    dart._check_status({"status": "013", "message": "no data"}, "test")
    check("013 은 예외", False)
except dart.DartError as exc:
    check("013 은 DartError", "조회된 데이터가 없습니다" in str(exc))

dart._check_status({"status": "000"}, "test")
check("000 은 통과", True)
dart._check_status({}, "test")
check("status 없으면 통과", True)

print("\n=== DART: 인증키 ===")
saved = os.environ.pop("DART_API_KEY", None)
try:
    ok, msg = dart.key_status()
    check("키 없으면 사용 불가", not ok)
    check("발급 안내 포함", "opendart.fss.or.kr" in msg)
    try:
        dart.api_key()
        check("키 없으면 예외", False)
    except dart.DartKeyMissing:
        check("DartKeyMissing 발생", True)

    os.environ["DART_API_KEY"] = "short"
    try:
        dart.api_key()
        check("40자리 아니면 예외", False)
    except dart.DartKeyMissing as exc:
        check("길이 검증", "40자리가 아닙니다" in str(exc))

    os.environ["DART_API_KEY"] = "a" * 40
    ok, msg = dart.key_status()
    check("40자리면 사용 가능", ok, msg)
    check("키 전체를 노출하지 않음", "a" * 40 not in msg, msg)
finally:
    os.environ.pop("DART_API_KEY", None)
    if saved is not None:
        os.environ["DART_API_KEY"] = saved

print("\n=== DART: corp_code 해석 ===")
corp_map = {"005930": {"corp_code": "00126380", "corp_name": "삼성전자"},
            "000660": {"corp_code": "00164779", "corp_name": "SK하이닉스"}}
check("종목코드 → corp_code",
      dart.resolve_corp_code("005930", corp_map) == "00126380")
check("우선주(005935) → 보통주 법인으로 폴백",
      dart.resolve_corp_code("005935", corp_map) == "00126380")
check("없는 종목은 None", dart.resolve_corp_code("999999", corp_map) is None)
check("override 가 우선",
      dart.resolve_corp_code("005930", corp_map, {"005930": "99999999"}) == "99999999")

print("\n=== DART: 공시 객체 ===")
d = Disclosure("삼성전자", "분기보고서 (2026.09)", "20261114000123", "20261114",
               flr_nm="삼성전자", stock_code="005930")
check("날짜 ISO 변환", d.date_iso == "2026-11-14", d.date_iso)
check("중요도 2 (분기보고서)", d.importance == 2)
check("DART 링크", "rcpNo=20261114000123" in d.url, d.url)
check("기타 공시는 중요도 1",
      Disclosure("x", "임원ㆍ주요주주특정증권등소유상황보고서", "1", "20261101").importance == 1)
check("주요사항보고서는 중요도 2",
      Disclosure("x", "주요사항보고서(유형자산양수도)", "1", "20261101").importance == 2)

print("\n=== DART: 분기 추정 ===")
cases = [
    # 분기보고서는 분기말 후 45일 제출. 11/5 에는 3Q 보고서가 아직 없습니다
    # (잠정실적은 발표됐어도 재고자산 주석이 담긴 분기보고서는 11월 중순).
    (dt.date(2026, 11, 5), (2026, "2Q"), "3Q 보고서 미제출 시점"),
    (dt.date(2026, 11, 20), (2026, "3Q"), "3Q 보고서 제출 후"),
    (dt.date(2026, 5, 25), (2026, "1Q"), "1Q 보고서 제출 후"),
    (dt.date(2026, 8, 25), (2026, "2Q"), "반기보고서 제출 후"),
    # 사업보고서는 90일이므로 2/25 에는 전년 FY 가 아직 없음 → 전년 3Q
    (dt.date(2026, 2, 25), (2025, "3Q"), "전년 사업보고서 미제출 시점"),
    (dt.date(2026, 4, 5), (2025, "FY"), "전년 사업보고서 제출 후"),
]
for today, want, why in cases:
    got = dart.latest_available_quarter(today)
    check(f"{today} → {want} ({why})", got == want, str(got))

check("한 분기 뒤로: 3Q → 2Q", dart.previous_quarter(2026, "3Q") == (2026, "2Q"))
check("한 분기 뒤로: 1Q → 전년 FY", dart.previous_quarter(2026, "1Q") == (2025, "FY"))
check("한 분기 뒤로: FY → 3Q", dart.previous_quarter(2026, "FY") == (2026, "3Q"))

print("\n=== DART: 보고서 코드 ===")
check("코드 매핑", dart.REPORT_CODES == {"1Q": "11013", "2Q": "11012",
                                        "3Q": "11014", "FY": "11011"})
check("라벨 매핑", dart.REPORT_LABELS["11014"] == "3분기보고서")




# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 잠정실적 레이더 ===")
# 삼성전자·SK하이닉스의 영업(잠정)실적은 정식 분기보고서보다 2주 정도 빠릅니다.
# 재고 지표는 정식 보고서가 있어야 계산되므로, 그 사이 기간에는 이게
# 메모리 사이클에 대한 가장 이른 확정 숫자입니다.


class _Disc:
    """sources.dart.Disclosure 대역."""

    def __init__(self, report_nm, rcept_dt, corp_name="삼성전자",
                 stock_code="005930"):
        self.report_nm = report_nm
        self.rcept_dt = rcept_dt
        self.corp_name = corp_name
        self.stock_code = stock_code
        self.url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_dt}"


# 제목 판별 — DART 제목은 회사·분기마다 조금씩 다릅니다
for _name, _want in (
    ("연결재무제표기준영업(잠정)실적(공정공시)", True),
    ("영업(잠정)실적(공정공시)", True),
    ("영업 (잠정) 실적", True),            # 공백이 끼어도 잡아야 합니다
    ("매출액또는손익구조30%(대규모법인은15%)이상변동", True),
    ("분기보고서", False),
    ("사업보고서", False),
    ("주요사항보고서", False),
    ("현금ㆍ현물배당결정", False),
    ("단일판매ㆍ공급계약체결", False),
):
    check(f"제목 판별: {_name[:22]}",
          cycle.is_preliminary(_name) is _want,
          f"기대 {_want}")

# 정렬과 선별
_rows = [
    _Disc("분기보고서", "20261101"),
    _Disc("영업(잠정)실적(공정공시)", "20261008"),
    _Disc("매출액또는손익구조30%이상변동", "20260715"),
    _Disc("현금ㆍ현물배당결정", "20260901"),
    _Disc("영업(잠정)실적(공정공시)", "20260708", "SK하이닉스", "000660"),
]
_radar = cycle.preliminary_radar(_rows)
check("잠정실적만 골라낸다", len(_radar) == 3, str(len(_radar)))
check("접수일 역순", [f.rcept_dt for f in _radar]
      == ["20261008", "20260715", "20260708"],
      str([f.rcept_dt for f in _radar]))
check("회사명이 보존된다",
      {f.corp_name for f in _radar} == {"삼성전자", "SK하이닉스"},
      str({f.corp_name for f in _radar}))
check("DART 링크가 담긴다",
      all(f.url.startswith("https://dart.fss.or.kr/") for f in _radar))
check("limit 이 적용된다", len(cycle.preliminary_radar(_rows, limit=1)) == 1)
check("빈 입력도 처리", cycle.preliminary_radar([]) == []
      and cycle.preliminary_radar(None) == [])

# 날짜 변환과 신선도
_f = _radar[0]
check("YYYYMMDD 를 ISO 로", _f.date_iso == "2026-10-08", _f.date_iso)
_bad = cycle.PrelimFiling("x", "y", "엉뚱한값", "")
check("날짜가 깨져도 죽지 않는다",
      _bad.age_days is None and _bad.age_label == "" and not _bad.is_fresh,
      _bad.date_iso)

import datetime as _dt2  # noqa: E402

_today = _dt2.date.today().strftime("%Y%m%d")
_old = (_dt2.date.today() - _dt2.timedelta(days=200)).strftime("%Y%m%d")
_fresh = cycle.preliminary_radar([_Disc("영업(잠정)실적", _today)])[0]
_stale = cycle.preliminary_radar([_Disc("영업(잠정)실적", _old)])[0]
check("오늘 공시는 최신", _fresh.is_fresh and _fresh.age_label == "오늘")
check("200일 전 공시는 최신 아님", not _stale.is_fresh, _stale.age_label)
check("신선도 기준이 한 분기보다 길다", cycle.PRELIM_FRESH_DAYS > 90,
      f"{cycle.PRELIM_FRESH_DAYS}일 — 다음 분기 공시가 나올 시점까지입니다")

# 숫자를 파싱하지 않는다는 설계를 고정합니다
check("잠정 공시 본문 숫자를 파싱하지 않는다",
      not any(hasattr(_f, a) for a in ("revenue", "operating_income", "amount")),
      "표 형식이 분기마다 달라 조용히 틀린 숫자를 보여줄 위험이 큽니다")


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 미국 실적 8-K 레이더 ===")
# 한국은 제목을 대조해야 하지만 미국은 SEC 가 항목 번호를 줍니다.
# Item 2.02 = Results of Operations and Financial Condition.


class _Fil:
    def __init__(self, form, items, filing_date):
        self.form = form
        self.items = items
        self.filing_date = filing_date
        self.url = f"https://www.sec.gov/Archives/x/{filing_date}"


_fils = [
    _Fil("10-Q", "", "2026-11-07"),
    _Fil("8-K", "2.02,9.01", "2026-11-01"),
    _Fil("8-K", "5.02", "2026-08-15"),          # 임원 변경 — 실적 아님
    _Fil("8-K", "7.01,8.01", "2026-07-20"),     # Reg FD — 실적 아님
    _Fil("8-K/A", "2.02", "2026-06-30"),        # 정정도 실적
    _Fil("10-K", "", "2026-10-10"),
]
_us = cycle.prelim_from_filings(_fils, "MU", name="Micron")
check("Item 2.02 만 골라낸다", len(_us) == 2, str(len(_us)))
check("임원 변경(5.02) 제외",
      not any("5.02" in f.report_nm for f in _us))
check("Reg FD(7.01) 제외", all("2.02" in f.report_nm for f in _us))
check("8-K/A(정정)도 포함", any("8-K/A" in f.report_nm for f in _us),
      str([f.report_nm for f in _us]))
check("10-Q·10-K 는 제외", not any("10-" in f.report_nm for f in _us))
check("접수일 역순", [f.rcept_dt for f in _us] == ["20261101", "20260630"],
      str([f.rcept_dt for f in _us]))
check("회사명이 들어간다", all(f.corp_name == "Micron" for f in _us))
check("SEC 링크가 담긴다",
      all(f.url.startswith("https://www.sec.gov/") for f in _us))
check("항목 번호를 화면 문구에 적는다",
      all("Item 2.02" in f.report_nm for f in _us),
      str([f.report_nm for f in _us]))
check("빈 입력도 처리",
      cycle.prelim_from_filings([], "MU") == []
      and cycle.prelim_from_filings(None, "MU") == [])
check("name 을 안 주면 티커를 쓴다",
      cycle.prelim_from_filings(_fils, "MU")[0].corp_name == "MU")
check("limit 적용", len(cycle.prelim_from_filings(_fils, "MU", limit=1)) == 1)

# 한국·미국이 같은 타입으로 나와 한 목록에 섞일 수 있어야 합니다
_mixed = cycle.preliminary_radar(_rows) + _us
_mixed.sort(key=lambda f: f.rcept_dt, reverse=True)
check("한국·미국을 한 목록에 섞을 수 있다",
      len(_mixed) == 5 and all(hasattr(f, "date_iso") for f in _mixed),
      f"{len(_mixed)}건")
check("메모리 3사가 함께 보인다",
      {"삼성전자", "SK하이닉스", "Micron"} <= {f.corp_name for f in _mixed},
      str({f.corp_name for f in _mixed}))


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
