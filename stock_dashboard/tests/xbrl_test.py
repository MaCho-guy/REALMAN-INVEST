"""
EDGAR XBRL 경로 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/xbrl_test.py

검증 범위: 중복 보고 제거(filed 최신 우선), 구간 분류(시점/분기/연간),
           53주 분기 인식, 시점-구간 정렬과 허용치, 태그 후보 폴백,
           XBRL → InventoryTrend 변환과 DIO 기간일수.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cycle  # noqa: E402
from sources import edgar_xbrl  # noqa: E402
from sources.edgar_xbrl import (  # noqa: E402
    Fact,
    XbrlNotFound,
    align_instant_to_duration,
    dedupe,
)

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def near(a, b, tol=0.05) -> bool:
    return a is not None and b is not None and abs(a - b) < tol


def inst(end: str, val: float, filed: str = "2026-01-01", tag: str = "InventoryNet") -> Fact:
    """시점값(재고 같은 재무상태표 계정) — start 가 없습니다."""
    return Fact(start=None, end=end, val=val, form="10-Q", fy=2026, fp="Q1",
                filed=filed, tag=tag)


def dur(start: str, end: str, val: float, filed: str = "2026-01-01",
        fp: str = "Q1", fy: int = 2026, form: str = "10-Q",
        tag: str = "CostOfRevenue") -> Fact:
    """구간값(매출원가 같은 손익계산서 계정)."""
    return Fact(start=start, end=end, val=val, form=form, fy=fy, fp=fp,
                filed=filed, tag=tag)


# ──────────────────────────────────────────────────────────────────────────────
print("=== 중복 보고 제거 ===")
# 같은 기간이 10-Q, 그 다음 10-K 비교란, 다음 해 10-K 에 반복 실립니다.
# 값이 정정되기도 하므로 제출일(filed)이 가장 늦은 것이 최신입니다.
facts = [
    dur("2025-09-01", "2025-11-30", 100.0, filed="2025-12-20"),
    dur("2025-09-01", "2025-11-30", 105.0, filed="2026-01-05"),   # 정정
    dur("2025-09-01", "2025-11-30", 103.0, filed="2025-12-28"),
    dur("2025-12-01", "2026-02-28", 200.0, filed="2026-03-20"),
]
out = dedupe(facts)
check("같은 기간 3건 → 1건", len(out) == 4 - 2, f"{len(out)}건")
first = [f for f in out if f.end == "2025-11-30"][0]
check("filed 가장 늦은 값이 남음", near(first.val, 105.0), str(first.val))
check("종료일 오름차순 정렬", [f.end for f in out] == ["2025-11-30", "2026-02-28"])

# 시점값과 구간값이 같은 종료일을 가져도 서로 다른 키입니다(start 가 다름).
mixed = dedupe([inst("2026-02-28", 50.0), dur("2025-12-01", "2026-02-28", 200.0)])
check("시점값·구간값은 별개 키", len(mixed) == 2, f"{len(mixed)}건")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 구간 분류 ===")
check("start 없으면 시점값", inst("2026-02-28", 1.0).is_instant)
check("시점값은 분기 아님", not inst("2026-02-28", 1.0).is_quarterly)
check("시점값 duration_days 는 None", inst("2026-02-28", 1.0).duration_days is None)

q13w = dur("2025-12-01", "2026-02-28", 1.0)          # 90일
check("13주 분기(90일) → 분기", q13w.is_quarterly, f"{q13w.duration_days}일")
check("13주 분기는 연간 아님", not q13w.is_annual)

q14w = dur("2025-08-29", "2025-12-04", 1.0)          # 97일, 마이크론 53주 회계연도
check("14주 분기(97일) → 분기", q14w.is_quarterly, f"{q14w.duration_days}일")

fy = dur("2025-09-01", "2026-08-31", 1.0, fp="FY", form="10-K")
check("연간(364일) → 연간", fy.is_annual, f"{fy.duration_days}일")
check("연간은 분기 아님", not fy.is_quarterly)

half = dur("2025-09-01", "2026-02-28", 1.0)          # 180일 — 반기
check("반기(180일)는 분기도 연간도 아님",
      not half.is_quarterly and not half.is_annual, f"{half.duration_days}일")
# ↑ 중요: 반기·누적 구간이 분기로 섞이면 DIO 분모가 두 배가 됩니다.

check("period_label 은 fy/fp 조합", q13w.period_label == "FY2026 Q1")
check("fy 없으면 종료일로 대체",
      Fact(start=None, end="2026-02-28", val=1.0, form="", fy=None, fp="",
           filed="").period_label == "2026-02-28")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 시점-구간 정렬 ===")
instants = [inst("2025-11-30", 90.0), inst("2026-02-28", 95.0),
            inst("2026-05-29", 99.0)]
durations = [dur("2025-09-01", "2025-11-30", 100.0),
             dur("2025-12-01", "2026-02-28", 110.0)]
pairs = align_instant_to_duration(instants, durations)
check("종료일 일치 2쌍", len(pairs) == 2, f"{len(pairs)}쌍")
check("첫 쌍은 11-30 재고 90", near(pairs[0][0].val, 90.0))
check("첫 쌍의 구간은 11-30 종료", pairs[0][1].end == "2025-11-30")

# 재고 보고일이 이틀 어긋난 경우 — 허용치 안이면 붙입니다
off = align_instant_to_duration(
    [inst("2026-03-02", 95.0)],
    [dur("2025-12-01", "2026-02-28", 110.0)],
    tolerance_days=7,
)
check("2일 차이는 허용치 안에서 매칭", len(off) == 1, f"{len(off)}쌍")

far = align_instant_to_duration(
    [inst("2026-04-30", 95.0)],
    [dur("2025-12-01", "2026-02-28", 110.0)],
    tolerance_days=7,
)
check("61일 차이는 매칭 안 됨", len(far) == 0, f"{len(far)}쌍")

# 후보가 여럿이면 가장 가까운 것
nearest = align_instant_to_duration(
    [inst("2026-03-05", 1.0), inst("2026-02-27", 2.0)],
    [dur("2025-12-01", "2026-02-28", 110.0)],
    tolerance_days=10,
)
check("가장 가까운 시점값 선택", len(nearest) == 1 and near(nearest[0][0].val, 2.0),
      str(nearest[0][0].end) if nearest else "없음")

check("정렬 대상 없으면 빈 목록",
      align_instant_to_duration([], durations) == [])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 태그 후보 폴백 ===")
# fetch_concept 을 가로채 네트워크 없이 후보 순회를 검증합니다.
calls: list[str] = []
_real_fetch = edgar_xbrl.fetch_concept


def fake_fetch(cik, tag, user_agent, *, taxonomy="us-gaap", unit="USD"):
    calls.append(tag)
    if tag == "CostOfGoodsAndServicesSold":
        raise XbrlNotFound("보고하지 않습니다")
    if tag == "CostOfSales":
        return []                                     # 응답은 있지만 값이 비었음
    if tag == "CostOfRevenue":
        return [dur("2025-12-01", "2026-02-28", 110.0, tag=tag)]
    raise XbrlNotFound("없음")


edgar_xbrl.fetch_concept = fake_fetch
try:
    tag, facts = edgar_xbrl.fetch_first_available(
        123, ("CostOfGoodsAndServicesSold", "CostOfSales", "CostOfRevenue"), "ua")
    check("세 번째 후보에서 성공", tag == "CostOfRevenue", tag)
    check("후보를 순서대로 시도",
          calls == ["CostOfGoodsAndServicesSold", "CostOfSales", "CostOfRevenue"],
          str(calls))
    check("빈 응답은 실패로 간주해 다음 후보로", len(facts) == 1)

    calls.clear()
    raised = False
    try:
        edgar_xbrl.fetch_first_available(123, ("Nope1", "Nope2"), "ua")
    except XbrlNotFound as exc:
        raised = True
        msg = str(exc)
    check("전부 실패하면 XbrlNotFound", raised)
    check("실패 메시지에 후보 수 포함", raised and "2개" in msg, msg if raised else "")
finally:
    edgar_xbrl.fetch_concept = _real_fetch


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== XBRL → InventoryTrend ===")
# 마이크론 형태: 분기마다 재고·매출원가·매출, 마지막 분기는 14주(97일)
inventory = [
    inst("2025-02-27", 8_900e6), inst("2025-05-29", 9_200e6),
    inst("2025-08-28", 9_600e6), inst("2025-12-04", 11_600e6),
]
cost_of_sales = [
    dur("2024-11-29", "2025-02-27", 6_800e6, fp="Q2", fy=2025),
    dur("2025-02-28", "2025-05-29", 7_250e6, fp="Q3", fy=2025),
    dur("2025-05-30", "2025-08-28", 7_500e6, fp="Q4", fy=2025),
    dur("2025-08-29", "2025-12-04", 8_200e6, fp="Q1", fy=2026),   # 97일
]
revenue = [
    dur("2024-11-29", "2025-02-27", 9_600e6, fp="Q2", fy=2025, tag="Revenues"),
    dur("2025-02-28", "2025-05-29", 10_300e6, fp="Q3", fy=2025, tag="Revenues"),
    dur("2025-05-30", "2025-08-28", 11_000e6, fp="Q4", fy=2025, tag="Revenues"),
    dur("2025-08-29", "2025-12-04", 12_500e6, fp="Q1", fy=2026, tag="Revenues"),
]
trend = cycle.build_trend_from_xbrl("MU", "MU", inventory, cost_of_sales,
                                    revenue, quarters=6)
check("4분기 생성", len(trend.quarters) == 4, f"{len(trend.quarters)}분기")
check("오류 없음", not trend.errors, "; ".join(trend.errors))
check("오래된 것 → 최신 순서",
      [q.period_end for q in trend.quarters]
      == ["2025-02-27", "2025-05-29", "2025-08-28", "2025-12-04"],
      str([q.period_end for q in trend.quarters]))

latest = trend.latest
check("최신 분기 재고 11.6B", near(latest.inventory / 1e9, 11.6, 0.01))
check("최신 분기 기간 97일", near(latest.period_days, 97.0, 0.5),
      f"{latest.period_days}일")
# DIO = 11,600 ÷ 8,200 × 97 = 137.2
check("최신 DIO ≈ 137일", near(latest.dio, 137.2, 0.5), f"{latest.dio:.1f}일")
check("91일 고정 가정과 8일 이상 차이",
      abs(latest.dio - (11_600 / 8_200 * 91)) > 8.0,
      f"실제일수 {latest.dio:.1f} vs 91일가정 {11_600 / 8_200 * 91:.1f}")
# ↑ 이 차이가 explicit_period_days 를 넣은 이유입니다.

check("DIO 시계열 4개", len(trend.dio_series) == 4)
check("밴드 산출됨", trend.dio_band is not None)
check("최신이 밴드 최상단", near(trend.dio_position, 100.0, 0.1),
      f"{trend.dio_position:.0f}%")
check("QoQ 상승", trend.dio_qoq_change is not None and trend.dio_qoq_change > 0,
      f"{trend.dio_qoq_change:+.1f}일" if trend.dio_qoq_change else "없음")
check("가드 경고 없음", not trend.dio_warnings, "; ".join(trend.dio_warnings))

# 연간 구간이 섞여 들어와도 분기만 씁니다
with_annual = cost_of_sales + [
    dur("2024-08-30", "2025-08-28", 29_000e6, fp="FY", form="10-K"),
]
trend2 = cycle.build_trend_from_xbrl("MU", "MU", inventory, with_annual,
                                     revenue, quarters=6)
check("연간 구간은 제외", len(trend2.quarters) == 4, f"{len(trend2.quarters)}분기")

# 분기 구간이 아예 없으면 명시적으로 알려줘야 합니다
only_annual = cycle.build_trend_from_xbrl(
    "MU", "MU", inventory,
    [dur("2024-08-30", "2025-08-28", 29_000e6, fp="FY", form="10-K")],
    revenue, quarters=6)
check("분기 매출원가 없으면 오류 기록",
      not only_annual.quarters and any("분기" in e for e in only_annual.errors),
      "; ".join(only_annual.errors))

# quarters 한도
trimmed = cycle.build_trend_from_xbrl("MU", "MU", inventory, cost_of_sales,
                                      revenue, quarters=2)
check("quarters=2 면 최신 2개만", len(trimmed.quarters) == 2,
      f"{len(trimmed.quarters)}분기")
check("최신 분기가 마지막", trimmed.quarters[-1].label == latest.label,
      trimmed.quarters[-1].label)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 정렬 회귀 (회계연도 표기가 어긋나는 경우) ===")
# 실제 응답에 fp 가 비거나 fy 가 없는 건이 섞입니다. 회계연도·분기로 정렬하면
# 순서가 뒤집히고, 그러면 '연속 상승'과 QoQ 가 전부 거짓이 됩니다.
messy_cos = [
    dur("2025-08-29", "2025-12-04", 8_200e6, fp="", fy=None),      # fp 없음
    dur("2025-05-30", "2025-08-28", 7_500e6, fp="FY", fy=2025),    # FY 표기
    dur("2025-02-28", "2025-05-29", 7_250e6, fp="Q4", fy=2025),    # Q4 와 충돌
]
messy = cycle.build_trend_from_xbrl("MU", "MU", inventory, messy_cos, [],
                                    quarters=6)
check("표기가 어긋나도 종료일 순서 유지",
      [q.period_end for q in messy.quarters]
      == ["2025-05-29", "2025-08-28", "2025-12-04"],
      str([q.period_end for q in messy.quarters]))
check("순서가 맞으면 QoQ 도 최신 기준",
      messy.quarters[-1].period_end == "2025-12-04")
check("매출액 없으면 missing 기록",
      all("매출액" in q.missing for q in messy.quarters))


print("\n=== 재고 없는 분기 ===")
# 매출원가는 있는데 짝지을 재고가 없는 경우 — DIO 는 비고 나머지는 살아야 합니다
sparse = cycle.build_trend_from_xbrl(
    "MU", "MU", [inst("2025-12-04", 11_600e6)], cost_of_sales, revenue,
    quarters=6)
check("재고 1개면 1분기만", len(sparse.quarters) == 1, f"{len(sparse.quarters)}분기")
check("밴드는 2개 미만이면 None", sparse.dio_band is None)


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
