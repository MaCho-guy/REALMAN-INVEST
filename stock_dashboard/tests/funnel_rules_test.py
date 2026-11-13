"""깔때기 규칙 (2026-11-13) — 국내 허용 미달 규칙 · 오늘 볼 종목 품질 집합 · EPS 동점 정렬 ·
가격 격차 · 내역 줄. 통신 없음.

    python tests/funnel_rules_test.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import buffett  # noqa: E402
import chart_signals  # noqa: E402
import components as ui  # noqa: E402
import config  # noqa: E402
import funnel  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


P, F, U = "pass", "fail", "unknown"


def summ(ticker, verdicts):
    return {"t": ticker, "n": ticker, "y": 10,
            "c": [[c.key, v, "", "", ""] for c, v in zip(buffett.CRITERIA, verdicts)]}


def mk(ticker, verdicts):
    return buffett.from_summary(summ(ticker, verdicts))


print("=== 국내 통과 — 확인된 미달 2개 이하 · 판정 7개 이상 ===")
k9_7 = mk("A", [P] * 7 + [F, F])            # 9개 다 판정 · 7 통과 — 미국 7/9 와 같은 선
k9_6 = mk("B", [P] * 6 + [F] * 3)           # 미달 3
k8_6 = mk("C", [P] * 6 + [F, F] + [U])      # 예전 규칙에선 탈락 (6/8 = 75%)
k7_5 = mk("D", [P] * 5 + [F, F] + [U, U])   # 국내 전형(판정 7) · 미달 2 — 예전엔 탈락
k7_4 = mk("E", [P] * 4 + [F] * 3 + [U, U])  # 미달 3
k6_6 = mk("G", [P] * 6 + [U] * 3)           # 판정 6 — 증거 부족 보류
k4_4 = mk("H", [P] * 4 + [U] * 5)           # 판정 4 — 보류도 아님 (floor 5)
check("9개 판정 · 7 통과는 통과 (미국과 같은 선)", buffett.passes_kr(k9_7))
check("미달 3개는 탈락", not buffett.passes_kr(k9_6) and not buffett.passes_kr(k7_4))
check("판정 8 · 미달 2 는 통과 (예전 비율 규칙은 탈락)",
      buffett.passes_kr(k8_6) and not buffett.passes(k8_6, 7, by_ratio=True))
check("판정 7 · 미달 2 는 통과 (예전 비율 규칙은 탈락)",
      buffett.passes_kr(k7_5) and not buffett.passes(k7_5, 7, by_ratio=True))
check("판정 6 은 통과가 아니고 보류", not buffett.passes_kr(k6_6) and buffett.held_back_kr(k6_6))
check("판정 4 는 보류도 아님", not buffett.held_back_kr(k4_4))
check("통과 종목은 보류에 겹치지 않음",
      not any(buffett.passes_kr(x) and buffett.held_back_kr(x) for x in (k9_7, k8_6, k7_5, k6_6)))
check("예전 함수는 그대로 남아 있음 (기존 기능 유지)",
      buffett.passes(k9_7, 7, by_ratio=True) and buffett.passes(k9_7, 7))
check("새 통과는 미리 계산 범위(판정 중 6/9 비율) 안 — 가격 · 차트 줄이 빠지지 않음",
      all(buffett.passes(x, config.FUNNEL_MIN_PASS, by_ratio=True)
          for x in (k9_7, k8_6, k7_5)))
check("미국 품질 통과는 통과 수 7 그대로",
      buffett.quality_pass(k9_7, "us") and not buffett.quality_pass(k8_6, "us"))

print("\n=== 오늘 볼 종목 — 깔때기 화면과 같은 품질 집합 ===")
screens = [summ("BRK.B", [P] * 7 + [F, F]), summ("XX", [P] * 6 + [F] * 3)]
qs = funnel.quality_tickers(screens, "us")
check("미국 — 6개 통과는 빠지고 티커는 야후 표기", qs == {"BRK-B"}, str(qs))
kscreens = [summ("000001", [P] * 5 + [F, F] + [U, U]), summ("000002", [P] * 6 + [U] * 3)]
check("한국 — 판정 6개 보류 종목은 오늘 볼 종목 후보가 아님",
      funnel.quality_tickers(kscreens, "kr") == {"000001"})
app_src = pathlib.Path("app.py").read_text(encoding="utf-8")
check("화면이 quality_tickers 로 줄인다", "funnel.quality_tickers(src, market)" in app_src)

print("\n=== 순위 — 동점이면 선행 EPS 90일 ===")
a = mk("A1", [P] * 8 + [F])
b = mk("B1", [P] * 8 + [F])
c = mk("C1", [P] * 8 + [F])
d = mk("D1", [P] * 9)
order = [x.ticker for x in buffett.rank_with_eps([a, b, c, d], {"A1": 0.01, "B1": None, "C1": 0.05})]
check("비율 먼저, 동점은 EPS 큰 순, 추정 없음은 맨 뒤", order == ["D1", "C1", "A1", "B1"], str(order))

print("\n=== 가격 격차 · 내역 ===")
heavy = {"g": 0.20, "h": 0.30, "hi": 0.22, "sp": 7}     # 과거 30% → 상한 15% 로 비교
light = {"g": 0.05, "h": 0.10, "hi": 0.07, "sp": 7}
check("격차는 상한을 적용한 과거 성장률과 견줌",
      abs(funnel.price_gap(heavy) - 0.05) < 1e-9 and funnel.price_state(heavy) == "heavy")
check("높음 칸에 '요구가 과거보다 +5.0%p'", "+5.0%p" in funnel.price_cells(heavy)[1])
check("판정 안 함이면 격차 없음", funnel.price_gap({"na": "금융업"}) is None
      and funnel.gap_text(None) == "")
rows = [{"p": heavy, "f": {"c90": -0.08}}, {"p": light, "f": {"c90": 0.02}}, {"p": None, "f": None}]
b_ = funnel.breakdown(rows)
check("내역 — 가격 · EPS 칸 수", (b_["heavy"], b_["light"], b_["na"], b_["eps_down"],
                             b_["eps_warn"], b_["eps_up"], b_["eps_none"]) == (1, 1, 1, 1, 1, 1, 1),
      str(b_))
check("내역 줄 글", "높음 1" in funnel.breakdown_text(b_, 3) and "−5% 이하 1" in funnel.breakdown_text(b_, 3))
check("EPS −5% 경계", funnel.eps_down({"c90": -0.05}) and not funnel.eps_down({"c90": -0.049})
      and not funnel.eps_down(None))

print("\n=== 카드 — 가격 높음 · EPS 하향은 눈에 띄게 ===")
html = ui.render_pick_cards([{"name": "가", "ticker": "1", "price_state": "heavy",
                              "price_word": "가격 부담 높음 +5.0%p", "eps_c90": -0.08,
                              "eps_warn": True}])
check("가격 높음 칩에 warn", 'pk-chip warn">가격 부담 높음 +5.0%p' in html, html[:200])
check("EPS 하향 칩에 warn", "pk-chip eps down warn" in html)
check("빈 데이터에도 깨지지 않음", ui.render_pick_cards([{"name": "나"}]) != "")
check("today_picks 는 품질 집합이 비면 빈 목록",
      chart_signals.today_picks([], set()) == [])

print("\n=== 밸류에이션 탭 — 깔때기와 같은 품질 · 가격 규칙 ===")
from types import SimpleNamespace as _NS  # noqa: E402
import verdict as vd  # noqa: E402


def _dcf(g, sev=False):
    hist = [(2015 + i, 100.0 * 1.08 ** i) for i in range(10)]   # 과거 연 8%
    return _NS(ok=True, implied_growth=g, band_label="", gap_span=9,
               historical_cagr={9: 0.08}, sensitivity={0.08: g - 0.01, 0.1: g, 0.12: g + 0.01},
               severe_distortion=sev, normalized=False, error="",
               inputs=_NS(fcf_history=hist, net_debt=0.0))


k_scr = mk("K", [P] * 5 + [F, F] + [U, U])      # 국내 새 규칙 통과 · 통과 수는 5
v_kr = vd.build(k_scr, _dcf(0.03), market="kr")
v_old = vd.build(k_scr, _dcf(0.03))
check("국내 — 사분면 사업 축이 깔때기 규칙(①)", v_kr.quadrant == 1 and v_old.quadrant == 3,
      f"{v_kr.quadrant} / 예전 기본 {v_old.quadrant}")
u_scr = mk("U", [P] * 6 + [F] * 3)
check("미국 — 6개 통과는 사업 축 미달(③), 깔때기와 같음",
      vd.build(u_scr, _dcf(0.03), market="us").quadrant == 3)
v_sev = vd.build(mk("S", [P] * 9), _dcf(0.03, sev=True), market="us")
check("사이클 왜곡은 판정 안 함 (깔때기와 같음)",
      v_sev.price_state == "na" and v_sev.quadrant == 0 and "왜곡" in v_sev.price_reason)
v_h = vd.build(mk("H2", [P] * 9), _dcf(0.12), market="us")
check("가격 높음 근거에 격차 %p", v_h.price_state == "heavy" and "+4.0%p" in v_h.price_reason,
      v_h.price_reason)
check("quality_threshold 를 주면 예전처럼 통과 수", vd.build(u_scr, _dcf(0.03),
                                                     quality_threshold=6).quadrant == 1)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
