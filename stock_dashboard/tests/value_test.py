"""
가격 조건식 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/value_test.py

검증 범위: FCF 수익률 기준선(10년물 연동 포함), 순부채 상환 기간,
           기대 격차(역성장 예외), 중위수의 끝점 완화 효과,
           표시 전용 지표의 경계값, 두 점수를 합치지 않는지.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import value as vl  # noqa: E402
from buffett import Screen, YearRow  # noqa: E402

FAILURES: list[str] = []
M = 1_000_000.0


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


# ──────────────────────────────────────────────────────────────────────────────
print("=== 기준선: 10년물 연동 ===")

th_default = vl.Thresholds()
floor, basis = th_default.yield_floor()
check("미연동이면 기본 5.0%", floor == 5.0, f"{floor} ({basis})")
check("미연동 사실을 문구에 적는다", "미연동" in basis, basis)

th_linked = vl.Thresholds(risk_free_pct=4.20)
floor, basis = th_linked.yield_floor()
check("10년물 4.20% + 가산 1.0%p = 5.20%", abs(floor - 5.20) < 1e-9, f"{floor}")
check("근거에 10년물 값이 보인다", "4.20" in basis, basis)

th_manual = vl.Thresholds(fcf_yield_min=8.0, risk_free_pct=4.20)
floor, basis = th_manual.yield_floor()
check("직접 지정이 10년물보다 우선", floor == 8.0, f"{floor} ({basis})")

# 10년물이 높아지면 기준선도 같이 올라가야 합니다 — 금리가 오르면
# 같은 FCF 수익률이 상대적으로 덜 매력적인 게 맞습니다.
hi = vl.Thresholds(risk_free_pct=6.0).yield_floor()[0]
lo = vl.Thresholds(risk_free_pct=2.0).yield_floor()[0]
check("금리가 오르면 기준선도 오른다", hi > lo, f"{lo}% → {hi}%")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== FCF 수익률 ===")

th = vl.Thresholds(risk_free_pct=4.0)          # 기준선 5.0%
c = vl.check_fcf_yield(60 * M, 1000 * M, th)   # 6.0%
check("기준선 위면 통과", c.passed, c.value_label)
check("값이 표시된다", c.value_label == "6.00%", c.value_label)
check("근거 문구가 붙는다", "10년물" in c.detail, c.detail)

c = vl.check_fcf_yield(40 * M, 1000 * M, th)   # 4.0%
check("기준선 아래면 탈락", c.verdict == "fail", c.value_label)

c = vl.check_fcf_yield(-10 * M, 1000 * M, th)
check("FCF 적자면 탈락", c.verdict == "fail", c.value_label)

check("시가총액 없으면 판정 불가",
      not vl.check_fcf_yield(60 * M, None, th).known)
check("시가총액 0 이면 판정 불가",
      not vl.check_fcf_yield(60 * M, 0, th).known)
check("FCF 없으면 판정 불가",
      not vl.check_fcf_yield(None, 1000 * M, th).known)

# 정규화로 기준값이 반토막난 경우 — 통과시키되 경고를 남겨야 합니다.
c = vl.check_fcf_yield(60 * M, 1000 * M, th, distorted=True)
check("정규화 왜곡 시 통과하되 경고", c.passed and bool(c.warning), c.warning[:30])
c = vl.check_fcf_yield(60 * M, 1000 * M, th, distorted=False)
check("왜곡 없으면 경고 없음", c.passed and not c.warning)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 순부채 상환 기간 ===")

th = vl.Thresholds(net_debt_years_max=3.0)
c = vl.check_net_debt_years(200 * M, 100 * M, th)      # 2.0년
check("기준 이내면 통과", c.passed, c.value_label)
check("연수가 표시된다", c.value_label == "2.0년", c.value_label)

c = vl.check_net_debt_years(400 * M, 100 * M, th)      # 4.0년
check("기준 초과면 탈락", c.verdict == "fail", c.value_label)

c = vl.check_net_debt_years(-500 * M, 100 * M, th)
check("순현금이면 통과", c.passed, c.value_label)
check("순현금은 음수 연수로 적지 않는다", c.value_label == "순현금", c.value_label)

c = vl.check_net_debt_years(200 * M, -50 * M, th)
check("FCF 적자면 판정 불가", not c.known, c.detail[:30])
check("순부채 없으면 판정 불가",
      not vl.check_net_debt_years(None, 100 * M, th).known)

# 경계값 — 정확히 기준선이면 통과여야 합니다(이내로 썼으므로)
c = vl.check_net_debt_years(300 * M, 100 * M, th)
check("정확히 기준선이면 통과", c.passed, c.value_label)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 중위수가 끝점 민감도를 줄이는가 ===")

# 10년 CAGR 하나만 쓰면 10년 전 값에 끌려갑니다. 사이클 업종을 모사해
# 기간별 CAGR 이 크게 흩어진 경우를 봅니다.
spread = {3: 0.45, 5: 0.08, 7: 0.10, 10: 0.09}
med = vl.historical_median(spread)
check("중위수가 극단값(45%)에 끌려가지 않는다",
      med is not None and 0.08 <= med <= 0.11, f"{med:.3f}")
check("단일 기간만 있으면 그 값", vl.historical_median({10: 0.07}) == 0.07)
check("전부 없으면 None", vl.historical_median({3: None, 5: None}) is None)
check("빈 입력도 None", vl.historical_median({}) is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 기대 격차 ===")

cagr = {3: 0.12, 5: 0.10, 10: 0.11}            # 중위수 11%
c = vl.check_expectation_gap(0.06, cagr)
check("요구 < 과거면 통과", c.passed, c.value_label)
check("차이를 %p 로 적는다", "+" in c.detail, c.detail)

c = vl.check_expectation_gap(0.20, cagr)
check("요구 > 과거면 탈락", c.verdict == "fail", c.value_label)

c = vl.check_expectation_gap(0.11, cagr)
check("같으면 통과(이하 기준)", c.passed, c.value_label)

# 과거가 역성장이면 '기대가 더 낮다' 는 좋은 신호가 아닙니다.
c = vl.check_expectation_gap(-0.30, {5: -0.15, 10: -0.10})
check("과거 역성장이면 판정 불가", not c.known, c.detail[:40])
check("역성장 사실을 설명한다", "역성장" in c.detail)

check("내재 성장률 없으면 판정 불가",
      not vl.check_expectation_gap(None, cagr).known)
check("과거 CAGR 없으면 판정 불가",
      not vl.check_expectation_gap(0.05, {}).known)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 표시 전용 지표 ===")

check("EV/FCF — 순부채가 더해진다",
      vl.ev_over_fcf(1000 * M, 200 * M, 100 * M) == 12.0,
      str(vl.ev_over_fcf(1000 * M, 200 * M, 100 * M)))
check("EV/FCF — 순현금이면 작아진다",
      vl.ev_over_fcf(1000 * M, -200 * M, 100 * M) == 8.0)
check("EV/FCF — FCF 0 이하면 None",
      vl.ev_over_fcf(1000 * M, 0, 0) is None
      and vl.ev_over_fcf(1000 * M, 0, -5 * M) is None)
check("EV/FCF — 순부채 None 은 0 으로",
      vl.ev_over_fcf(1000 * M, None, 100 * M) == 10.0)

check("PBR 계산", vl.pbr(1000 * M, 250 * M) == 4.0)
check("PBR — 자본 0 이하면 None",
      vl.pbr(1000 * M, 0) is None and vl.pbr(1000 * M, -10 * M) is None)
check("PBR — 시가총액 없으면 None", vl.pbr(None, 250 * M) is None)

check("표시 전용은 점수 조건이 아니다",
      {k for k, _l, _n in vl.METRICS}.isdisjoint(vl.CRITERIA_BY_KEY),
      "겹치면 같은 축을 두 번 셉니다")
check("표시 전용 지표마다 제외 이유가 적혀 있다",
      all(len(n) > 30 for _k, _l, n in vl.METRICS))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 출처 표기 ===")

check("가격 조건은 전부 '제 기준'",
      all(c.provenance == "mine" for c in vl.CRITERIA),
      "버핏은 숫자 밸류에이션 기준을 공표한 적이 없습니다")
check("조건마다 한계를 적는다",
      all(len(c.caveat) > 40 for c in vl.CRITERIA))
check("조건마다 근거를 적는다",
      all(len(c.source) > 30 for c in vl.CRITERIA))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== build() 통합 ===")


class _Res:
    """역DCF 결과 대역."""

    def __init__(self, **kw):
        self.ok = kw.get("ok", True)
        self.fcf_base = kw.get("fcf_base", 60 * M)
        self.implied_growth = kw.get("implied_growth", 0.05)
        self.historical_cagr = kw.get("historical_cagr", {5: 0.10, 10: 0.11})
        self.severe_distortion = kw.get("severe_distortion", False)
        self.error = kw.get("error", "")


def _screen(net_debt=200 * M, equity=250 * M):
    row = YearRow(year=2025, end="2025-12-31")
    row.long_term_debt = net_debt + 100 * M
    row.short_term_debt = 0.0
    row.cash = 100 * M
    row.short_term_investments = 0.0
    row.long_term_investments = 0.0
    row.equity = equity
    s = Screen(ticker="TEST", name="테스트")
    s.years = [row]
    return s, row


# 순부채 150M ÷ 기준 FCF 60M = 2.5년 → 3년 기준 안쪽.
# 200M 으로 두면 3.3년이라 정상적으로 탈락합니다(그 경우는 아래에서 봅니다).
s, row = _screen(net_debt=150 * M)
check("대역 순부채가 의도한 값", row.net_debt == 150 * M, str(row.net_debt))

ps = vl.build(s, _Res(), 1000 * M, vl.Thresholds(risk_free_pct=4.0))
check("조건 3개가 판정된다", len(ps.checks) == 3, str(len(ps.checks)))
check("세 개 모두 통과", ps.passed_count == 3, ps.score_label)
check("기준선 근거가 담긴다", "10년물" in ps.yield_basis, ps.yield_basis)
# EV/FCF = (시가총액 1000M + 순부채 150M) / 기준 FCF 60M = 19.17
check("표시 지표도 함께 계산",
      abs(ps.metrics["ev_fcf"] - 19.1667) < 1e-3
      and ps.metrics["pbr"] == 4.0, str(ps.metrics))

ps = vl.build(s, _Res(ok=False, error="시가총액 없음"), 1000 * M)
check("역DCF 실패면 오류를 그대로 전달",
      not ps.ok and "시가총액" in ps.error, ps.error)
check("실패 시 조건을 만들지 않는다", not ps.checks)

ps = vl.build(s, None, 1000 * M)
check("결과가 None 이어도 죽지 않는다", not ps.ok and bool(ps.error), ps.error)

# 시가총액이 커지면 수익률이 떨어져 탈락해야 합니다
ps_expensive = vl.build(s, _Res(), 5000 * M, vl.Thresholds(risk_free_pct=4.0))
check("시가총액이 5배면 수익률 조건 탈락",
      ps_expensive.passed_count < 3, ps_expensive.score_label)

# 순부채가 많으면 상환 기간 조건에서 떨어져야 합니다
s_heavy, row_heavy = _screen(net_debt=200 * M)
ps_heavy = vl.build(s_heavy, _Res(), 1000 * M, vl.Thresholds(risk_free_pct=4.0))
_nd = [c for c in ps_heavy.checks if c.criterion.key == "net_debt_years"][0]
check("순부채 3.3년이면 상환 조건 탈락",
      _nd.verdict == "fail", _nd.value_label)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 두 점수를 합치지 않는가 ===")

ps_good = vl.build(s, _Res(), 1000 * M, vl.Thresholds(risk_free_pct=4.0))
label = vl.combined_label(5, 6, ps_good)
check("질과 가격을 따로 적는다", "질 5/6" in label and "가격 3/3" in label, label)
# 합계를 적으면 질과 가격의 가중치가 섞입니다. 5/6 + 3/3 = 8/9 가
# 라벨에 나타나면 안 됩니다.
check("합계 숫자를 만들지 않는다", "8/9" not in label and "8 / 9" not in label,
      label)
check("가격 판정 불가도 표기", "판정 불가" in vl.combined_label(5, 6, None))

# 질이 나쁜데 싼 종목과 질이 좋은데 비싼 종목이 구분되어야 합니다
cheap_bad = vl.combined_label(1, 6, ps_good)
good_pricey = vl.combined_label(6, 6, vl.build(
    s, _Res(), 5000 * M, vl.Thresholds(risk_free_pct=4.0)))
check("싼 저품질과 비싼 우량주가 다르게 보인다",
      cheap_bad != good_pricey, f"{cheap_bad} / {good_pricey}")


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
