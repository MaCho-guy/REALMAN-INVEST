"""
가격 판독(역DCF) · 판단 재료 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/dcf_test.py

검증 범위: 현재가치 계산과 역산의 왕복 일치, FCF 정규화, 적용 불가 조건,
           민감도, 과거 CAGR 기간 한계, 사분면 판정, 한국 기준선 분리.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buffett  # noqa: E402
import buffett_kr  # noqa: E402
import reverse_dcf as rd  # noqa: E402
import verdict as vd  # noqa: E402
from buffett import Screen, YearRow  # noqa: E402

FAILURES: list[str] = []
M = 1_000_000.0


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def near(a, b, tol=1e-5) -> bool:
    return a is not None and b is not None and abs(a - b) < tol


# ──────────────────────────────────────────────────────────────────────────────
print("=== 현재가치 ↔ 역산 왕복 ===")
# 성장률로 PV 를 구하고 그 PV 로 성장률을 역산하면 원래 값이 나와야 합니다.
# 이게 안 맞으면 이분법이나 할인식이 틀린 것입니다.
for g_true in (-0.20, -0.05, 0.0, 0.03, 0.08, 0.15, 0.25, 0.45):
    for wacc in (0.08, 0.10, 0.12):
        pv = rd.present_value(1_000.0, g_true, wacc)
        back = rd.solve_growth(pv, 1_000.0, wacc)
        check(f"g={g_true:+.0%} wacc={wacc:.0%}", near(back, g_true),
              f"역산 {back:+.5%}" if back is not None else "역산 실패")

def _try(fn) -> bool:
    """ValueError 를 던지는지 확인합니다. 다른 예외는 통과로 보지 않습니다."""
    try:
        fn()
    except ValueError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


check("할인율 ≤ 영구성장률은 ValueError",
      _try(lambda: rd.present_value(100.0, 0.05, 0.02)))
check("FCF 0 이하면 역산 None", rd.solve_growth(1000.0, 0.0, 0.10) is None)
check("FCF 음수면 역산 None", rd.solve_growth(1000.0, -50.0, 0.10) is None)

# 성장률이 높으면 PV 도 커야 합니다 (단조성)
pvs = [rd.present_value(100.0, g, 0.10) for g in (0.0, 0.05, 0.10, 0.20)]
check("성장률과 현재가치는 단조 증가", pvs == sorted(pvs), str([round(p) for p in pvs]))
# 할인율이 높으면 PV 는 작아야 합니다
pvw = [rd.present_value(100.0, 0.05, w) for w in (0.08, 0.10, 0.12)]
check("할인율과 현재가치는 단조 감소", pvw == sorted(pvw, reverse=True),
      str([round(p) for p in pvw]))

# 범위 밖은 None
tiny = rd.present_value(100.0, rd.GROWTH_MIN, 0.10)
check("범위 아래는 None", rd.solve_growth(tiny * 0.5, 100.0, 0.10) is None)
huge = rd.present_value(100.0, rd.GROWTH_MAX, 0.10)
check("범위 위는 None", rd.solve_growth(huge * 2, 100.0, 0.10) is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== CAGR ===")
check("2배 10년", near(rd.cagr(100.0, 200.0, 10), 0.0717735, 1e-5),
      f"{rd.cagr(100.0, 200.0, 10):.5f}")
check("감소도 계산", rd.cagr(200.0, 100.0, 10) < 0)
check("시작이 0 이하면 None", rd.cagr(0.0, 100.0, 5) is None)
check("끝이 0 이하면 None", rd.cagr(100.0, -5.0, 5) is None)
check("기간 0 이면 None", rd.cagr(100.0, 200.0, 0) is None)
# 적자→흑자 '성장률' 은 수학적으로 정의되지 않습니다
check("적자에서 흑자는 None", rd.cagr(-50.0, 100.0, 3) is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== FCF 정규화 ===")
steady = [(2020, 100.0), (2021, 105.0), (2022, 110.0)]
base, latest, avg, normalized, note = rd.normalize_fcf(steady)
check("안정적이면 최근값 사용", near(base, 110.0) and not normalized, str(base))

# 최근값이 3년 평균에서 40% 이상 벗어나면 평균을 씁니다
spike = [(2020, 100.0), (2021, 105.0), (2022, 400.0)]
base, latest, avg, normalized, note = rd.normalize_fcf(spike)
check("급등이면 평균 사용", normalized, f"기준 {base:,.1f}")
check("평균값이 기준", near(base, (100 + 105 + 400) / 3, 0.01), str(base))
check("정규화 사유를 설명", "3년 평균" in note, note[:50])

trough = [(2020, 400.0), (2021, 380.0), (2022, 50.0)]
base, _l, _a, normalized, _n = rd.normalize_fcf(trough)
check("급락도 평균 사용", normalized, f"기준 {base:,.1f}")

check("이력 없으면 None", rd.normalize_fcf([])[0] is None)
one = rd.normalize_fcf([(2022, 100.0)])
check("1년치면 그 값", near(one[0], 100.0) and not one[3])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 적용 불가 조건 ===")
def inputs_of(cap, net_debt, history, ticker="T"):
    return rd.Inputs(ticker=ticker, market_cap=cap, net_debt=net_debt,
                     fcf_history=history)


good_hist = [(2016 + i, 1_000.0 * (1.08 ** i)) for i in range(10)]

neg = rd.run(inputs_of(50_000.0, 0.0, [(y, -100.0) for y, _v in good_hist]))
check("FCF 가 음수면 적용 불가", not neg.ok and "0 이하" in neg.error,
      neg.error[:60])

no_cap = rd.run(inputs_of(0.0, 0.0, good_hist))
check("시가총액 0 이면 적용 불가", not no_cap.ok and "시가총액" in no_cap.error)

no_hist = rd.run(inputs_of(50_000.0, 0.0, []))
check("FCF 이력 없으면 적용 불가", not no_hist.ok and "FCF" in no_hist.error)

# 순현금이 시가총액보다 크면 EV 가 음수 → 모델이 성립하지 않습니다
cash_rich = rd.run(inputs_of(1_000.0, -5_000.0, good_hist))
check("EV 가 음수면 적용 불가", not cash_rich.ok and "순현금" in cash_rich.error,
      cash_rich.error[:60])

# 사이클 왜곡으로 기준값이 뭉개진 경우는 사유를 따로 설명해야 합니다
cyclical = [(2020, 5_000.0), (2021, -4_000.0), (2022, 100.0), (2023, 6_000.0)]

# (a) 역산이 아예 안 되는 경우 — 전용 오류 메시지
cyc_fail = rd.run(inputs_of(50_000_000.0, 0.0, cyclical))
check("사이클 왜곡은 전용 메시지",
      not cyc_fail.ok and "사이클 업종" in cyc_fail.error, cyc_fail.error[:70])
check("지표체계로 되돌려보냄", "레이어" in cyc_fail.error)

# (b) 역산이 '성공' 하는 경우 — 이게 더 위험합니다. 에러 없이 그럴듯한 숫자가
#     나오므로 그냥 읽힙니다. 반드시 경고가 붙어야 합니다.
cyc_ok = rd.run(inputs_of(500_000.0, 0.0, cyclical))
check("사이클 왜곡이면 역산 성공해도 플래그",
      cyc_ok.severe_distortion, f"ok={cyc_ok.ok}")
check("경고가 맨 앞에",
      cyc_ok.warnings and "그대로 쓰지 마십시오" in cyc_ok.warnings[0],
      cyc_ok.warnings[0][:50] if cyc_ok.warnings else "경고 없음")
check("왜곡된 결과는 판단 재료에서도 경고",
      any("신뢰할 수 없습니다" in c
          for c in vd.build(hi_q_placeholder, cyc_ok).caveats)
      if (hi_q_placeholder := Screen(ticker="X", name="X", years=[])) else False)

# 정상 범위 정규화는 플래그가 없어야 합니다
mild = rd.run(inputs_of(30_000.0, 0.0,
                        [(2020, 900.0), (2021, 1_000.0), (2022, 1_500.0)]))
check("완만한 정규화는 플래그 없음", not mild.severe_distortion)

no_debt = rd.run(inputs_of(50_000.0, None, good_hist))
check("순부채 없으면 경고하고 진행",
      no_debt.ok and any("시가총액을" in w for w in no_debt.warnings))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 정상 경로 ===")
res = rd.run(inputs_of(30_000.0, -2_000.0, good_hist))
check("역산 성공", res.ok, res.error[:60] if not res.ok else res.growth_label)
check("EV = 시총 + 순부채", near(res.inputs.enterprise_value, 28_000.0, 0.01))
check("민감도 3개", len(res.sensitivity) == 3, str(len(res.sensitivity)))
vals = [v for v in res.sensitivity.values() if v is not None]
check("할인율이 높으면 요구 성장률도 높음",
      vals == sorted(vals), str([f"{v:.3f}" for v in vals]))
check("구간 라벨", "~" in res.band_label, res.band_label)

# 10년치 데이터로는 9년 CAGR 이 최대입니다
check("최대 기간은 연도수 − 1", res.max_span == 9, str(res.max_span))
check("9년 CAGR 산출", res.historical_cagr.get(9) is not None)
check("과거 성장률이 8%", near(res.historical_cagr[9], 0.08, 1e-6),
      f"{res.historical_cagr[9]:.5f}")
check("3·5년도 산출",
      res.historical_cagr.get(3) is not None
      and res.historical_cagr.get(5) is not None)
check("격차 = 요구 − 과거", near(res.gap, res.implied_growth - 0.08, 1e-6))
check("격차 기준 기간은 최장", res.gap_span == 9, str(res.gap_span))

lines = rd.verdict_lines(res)
check("판단 재료 문장 생성", len(lines) >= 3, f"{len(lines)}줄")
check("요구 성장률 언급", any("요구" in ln or "성장" in ln for ln in lines))
check("결론 문장 없음",
      not any(w in " ".join(lines) for w in ("사십시오", "매수", "추천", "비싸", "싸다")),
      " ".join(lines)[:60])

# 적자 연도가 섞이면 경고
mixed = [(2016, 1_000.0), (2017, -500.0)] + [(2018 + i, 1_000.0 * (1.05 ** i))
                                             for i in range(8)]
res_mixed = rd.run(inputs_of(30_000.0, 0.0, mixed))
check("적자 연도 경고",
      any("0 이하" in w for w in res_mixed.warnings),
      str(res_mixed.warnings)[:70])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 스크리너 연결 ===")
def screen_with(ocf, capex, **over) -> Screen:
    years = []
    for i in range(10):
        years.append(YearRow(
            year=2016 + i, end=f"{2016 + i}-12-31",
            net_income=200 * M, revenue=1_000 * M, gross_profit=600 * M,
            dep_amort=100 * M, capex=capex, operating_cash_flow=ocf,
            equity=800 * M, long_term_debt=200 * M,
            cash=over.get("cash", 300 * M),
            short_term_debt=over.get("short_term_debt", 50 * M),
        ))
    s = Screen(ticker="TST", name="TST", years=years)
    return buffett.run_checks(s)


sc = screen_with(400 * M, 150 * M)
ins = rd.inputs_from_screen(sc, 20_000 * M, market_cap_source="테스트")
check("FCF = OCF − capex", near(ins.fcf_history[0][1] / M, 250.0, 0.01),
      f"{ins.fcf_history[0][1] / M}")
check("FCF 이력 10년", len(ins.fcf_history) == 10)
# 순부채 = (50 + 200) − 300 = -50
check("순부채 = 차입금 − 현금", near(ins.net_debt / M, -50.0, 0.01),
      f"{ins.net_debt / M}")
check("출처 기록", "FCF" in ins.sources and "순부채" in ins.sources)
check("시가총액 출처", ins.sources.get("시가총액") == "테스트")
check("재무 기준일 기록", "재무 기준일" in ins.sources)

no_ocf = rd.inputs_from_screen(screen_with(None, 150 * M), 20_000 * M)
check("영업현금흐름 없으면 FCF 이력 없음", no_ocf.fcf_history == [])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 사분면 ===")
hi_q = screen_with(400 * M, 60 * M)                      # 기준 많이 통과
check("고품질 스크린은 5개 이상 통과", hi_q.passed_count >= 5,
      hi_q.score_label)

# ① 기준 통과 + 요구 ≤ 과거
flat_hist = [(2016 + i, 1_000.0 * (1.20 ** i)) for i in range(10)]
q1 = vd.build(hi_q, rd.run(inputs_of(8_000.0, 0.0, flat_hist)))
check("① 통과 + 요구 낮음", q1.quadrant == 1,
      f"사분면 {q1.quadrant}, 격차 {q1.gap}")

# ② 기준 통과 + 요구 > 과거
slow_hist = [(2016 + i, 1_000.0 * (1.01 ** i)) for i in range(10)]
q2 = vd.build(hi_q, rd.run(inputs_of(40_000.0, 0.0, slow_hist)))
check("② 통과 + 요구 높음", q2.quadrant == 2, f"사분면 {q2.quadrant}")

lo_q = Screen(ticker="LOW", name="LOW", years=[
    YearRow(year=2016 + i, end=f"{2016 + i}-12-31", net_income=10 * M,
            revenue=1_000 * M, gross_profit=100 * M, dep_amort=10 * M,
            capex=300 * M, operating_cash_flow=50 * M, equity=900 * M,
            long_term_debt=900 * M)
    for i in range(10)
])
buffett.run_checks(lo_q)
check("저품질 스크린은 적게 통과", lo_q.passed_count <= 2, lo_q.score_label)

q3 = vd.build(lo_q, rd.run(inputs_of(8_000.0, 0.0, flat_hist)))
check("③ 미달 + 요구 낮음", q3.quadrant == 3, f"사분면 {q3.quadrant}")
q4 = vd.build(lo_q, rd.run(inputs_of(40_000.0, 0.0, slow_hist)))
check("④ 미달 + 요구 높음", q4.quadrant == 4, f"사분면 {q4.quadrant}")

q0 = vd.build(hi_q, rd.run(inputs_of(50_000.0, 0.0, [(2022, -100.0)])))
check("역DCF 불가면 사분면 0", q0.quadrant == 0, f"사분면 {q0.quadrant}")
check("사분면 0 도 사업 점수는 있음", q0.passed > 0, str(q0.passed))
check("역DCF 오류를 보관", q0.dcf_error != "")

check("dcf 가 None 이어도 동작", vd.build(hi_q, None).quadrant == 0)

# 사분면마다 다음 확인 항목이 달라야 합니다 — 같으면 지도가 무의미합니다
checks_by_q = {q.quadrant: tuple(q.next_checks[:3])
               for q in (q1, q2, q3, q4, q0)}
check("사분면별 다음 확인이 서로 다름",
      len(set(checks_by_q.values())) == len(checks_by_q),
      f"{len(set(checks_by_q.values()))}/{len(checks_by_q)} 종류")
check("② 는 성장 근거를 묻는다",
      any("근거" in c for c in q2.next_checks), str(q2.next_checks[:1]))
check("③ 은 업종 구조를 묻는다",
      any("업종 구조" in c for c in q3.next_checks))
check("④ 는 기준 자체를 의심한다",
      any("기준" in c for c in q4.next_checks))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 판단 재료 — 결론을 쓰지 않는다 ===")
lines = vd.summary_lines(q2)
text = " ".join(lines)
check("요약 생성", len(lines) >= 4, f"{len(lines)}줄")
check("사업 점수 포함", "통과" in text)
check("가격 기대 포함", "요구" in text)
check("위치 포함", any("①" in ln or "②" in ln or "③" in ln or "④" in ln
                      for ln in lines))
for banned in ("매수", "매도", "추천", "목표주가", "사십시오", "파십시오",
               "저평가", "고평가", "비싸", "싸다"):
    check(f"'{banned}' 없음", banned not in text, text[:60])

prompt = vd.prompt_for(q2, hi_q)
check("프롬프트에 숫자", "요구" in prompt)
check("프롬프트에 한계 구분", "[" in prompt)
check("공시 근거만 요구", "공시" in prompt)
check("추천 금지 명시", "매수/매도 추천" in prompt and "목표주가" in prompt)

q_unk = vd.build(lo_q, rd.run(inputs_of(8_000.0, 0.0, flat_hist)))
check("판정 불가 있으면 한계에 적음",
      q_unk.unknown == 0 or any("판정 불가" in c for c in q_unk.caveats))

norm_res = rd.run(inputs_of(30_000.0, 0.0, spike + good_hist[:7]))
q_norm = vd.build(hi_q, norm_res)
check("정규화했으면 한계에 적음",
      not norm_res.normalized
      or any("3년 평균" in c for c in q_norm.caveats),
      str(q_norm.caveats)[:70])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 한국 기준선 분리 ===")
import config  # noqa: E402

us_th = config.screen_thresholds()
kr_th = buffett_kr.kr_thresholds()
check("한국 ROE 기준이 더 낮다", kr_th.roe_min < us_th.roe_min,
      f"KR {kr_th.roe_min} vs US {us_th.roe_min}")
check("한국 요구 연수가 더 적다",
      kr_th.roe_years_required < us_th.roe_years_required)
check("한국 부채 허용이 더 크다",
      kr_th.debt_to_equity_max > us_th.debt_to_equity_max)
check("한국 마진 변동 허용이 더 크다",
      kr_th.margin_stdev_max > us_th.margin_stdev_max)
check("한국 나쁜해 허용이 더 많다",
      kr_th.bad_years_allowed > us_th.bad_years_allowed)
check("오버라이드 적용", buffett_kr.kr_thresholds({"roe_min": 20.0}).roe_min == 20.0)
check("정수 필드 유지", isinstance(kr_th.roe_years_required, int))

# 같은 기업이 미국 기준에선 탈락, 한국 기준에선 통과할 수 있어야 합니다
mid = Screen(ticker="MID", name="MID", years=[
    YearRow(year=2016 + i, end=f"{2016 + i}-12-31", net_income=96 * M,
            revenue=1_000 * M, gross_profit=600 * M, dep_amort=100 * M,
            capex=60 * M, operating_cash_flow=300 * M, equity=800 * M,
            long_term_debt=200 * M)
    for i in range(10)
])
import copy  # noqa: E402
us_result = buffett.run_checks(copy.deepcopy(mid), us_th)
kr_result = buffett.run_checks(copy.deepcopy(mid), kr_th)
us_roe = [c for c in us_result.checks if c.criterion.key == "roe"][0]
kr_roe = [c for c in kr_result.checks if c.criterion.key == "roe"][0]
check("ROE 12% — 미국 기준 탈락", us_roe.verdict == "fail", us_roe.detail[:50])
check("ROE 12% — 한국 기준 통과", kr_roe.verdict == "pass", kr_roe.detail[:50])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== K-IFRS 계정 매칭 ===")
class FakeAccount:
    def __init__(self, sj_div, account_id, account_nm,
                 thstrm=None, frmtrm=None, bfefrmtrm=None):
        self.sj_div = sj_div
        self.sj_nm = ""
        self.account_id = account_id
        self.account_nm = account_nm
        self.thstrm_amount = thstrm
        self.thstrm_add_amount = None
        self.frmtrm_amount = frmtrm
        self.bfefrmtrm_amount = bfefrmtrm


accounts = [
    FakeAccount("IS", "ifrs-full_Revenue", "매출액", 1_000.0, 900.0, 800.0),
    FakeAccount("IS", "-표준계정코드 미사용-", "매출액증가율", 11.0),
    FakeAccount("IS", "ifrs-full_CostOfSales", "매출원가", 600.0, 560.0, 500.0),
    FakeAccount("CIS", "ifrs-full_ProfitLoss", "당기순이익", 200.0, 180.0, 150.0),
    FakeAccount("BS", "ifrs-full_Equity", "자본총계", 2_000.0, 1_900.0, 1_800.0),
    FakeAccount("BS", "-표준계정코드 미사용-", "재고자산평가손실누계액", 5.0),
    FakeAccount("CF", "-표준계정코드 미사용-", "영업활동현금흐름",
                300.0, 280.0, 250.0),
]

rev = buffett_kr.find_account(accounts, buffett_kr.KR_RULES_BY_KEY["revenue"])
check("표준ID 로 매출액", rev is not None and rev.account_nm == "매출액",
      rev.account_nm if rev else "없음")
check("매출액증가율을 집지 않음", rev.account_id == "ifrs-full_Revenue")

ocf = buffett_kr.find_account(
    accounts, buffett_kr.KR_RULES_BY_KEY["operating_cash_flow"])
check("계정명 폴백으로 영업활동현금흐름",
      ocf is not None and near(ocf.thstrm_amount, 300.0))

ni = buffett_kr.find_account(accounts, buffett_kr.KR_RULES_BY_KEY["net_income"])
check("CIS 구분에서 당기순이익", ni is not None and near(ni.thstrm_amount, 200.0))

missing = buffett_kr.find_account(accounts, buffett_kr.KR_RULES_BY_KEY["capex"])
check("없는 계정은 None", missing is None)

# sj_div 가 다르면 집지 않습니다 — 현금흐름표의 '재고자산의 변동' 을
# 재무상태표의 재고자산으로 잘못 집는 사고를 막는 장치입니다
wrong_sj = [FakeAccount("CF", "ifrs-full_Equity", "자본총계", 999.0)]
check("재무제표 구분이 다르면 제외",
      buffett_kr.find_account(wrong_sj,
                              buffett_kr.KR_RULES_BY_KEY["equity"]) is None)


print("\n=== 보고서 1회 → 3년 ===")
rows = buffett_kr.years_from_report(accounts, 2025)
check("3개 연도 생성", len(rows) == 3, f"{len(rows)}개")
check("당기·전기·전전기",
      [r.year for r in rows] == [2025, 2024, 2023],
      str([r.year for r in rows]))
check("당기 매출", near(rows[0].revenue, 1_000.0))
check("전기 매출", near(rows[1].revenue, 900.0))
check("전전기 매출", near(rows[2].revenue, 800.0))
check("전기 순이익", near(rows[1].net_income, 180.0))
check("파생 지표 동작", near(rows[0].roe, 10.0), str(rows[0].roe))

print("\n=== 보고서 합치기 — 최신 우선 ===")
old_accounts = [
    FakeAccount("IS", "ifrs-full_Revenue", "매출액", 700.0, 600.0, 500.0),
    FakeAccount("CIS", "ifrs-full_ProfitLoss", "당기순이익", 100.0, 90.0, 80.0),
]
merged = buffett_kr.merge_years([
    buffett_kr.years_from_report(old_accounts, 2022),
    buffett_kr.years_from_report(accounts, 2025),
])
check("연도 중복 제거", len(merged) == 6, f"{len(merged)}개")
check("연속된 연도", [r.year for r in merged] == list(range(2020, 2026)),
      str([r.year for r in merged]))
check("오름차순", [r.year for r in merged] == sorted(r.year for r in merged))

# 같은 연도가 두 보고서에 있으면 최신 보고서 값을 씁니다 (재작성 반영)
restated = [FakeAccount("IS", "ifrs-full_Revenue", "매출액", 1_111.0)]
merged2 = buffett_kr.merge_years([
    buffett_kr.years_from_report(accounts, 2025),
    buffett_kr.years_from_report(restated, 2025),
])
y2025 = [r for r in merged2 if r.year == 2025][0]
check("최신 보고서 값으로 덮음", near(y2025.revenue, 1_111.0),
      str(y2025.revenue))
check("최신에 없는 항목은 유지", near(y2025.net_income, 200.0),
      str(y2025.net_income))


print("\n=== 국내 스크리닝 전체 ===")
kr_screen = buffett_kr.screen_company(
    "005930", "삼성전자",
    [(2022, old_accounts), (2025, accounts)], years=10)
check("스크린 생성", kr_screen.year_count == 6, f"{kr_screen.year_count}년")
check("종목명 유지", kr_screen.name == "삼성전자")
check("기준 6개 판정", len(kr_screen.checks) == 6)
check("못 찾은 계정 보고", "유형자산의 취득" in kr_screen.missing_tags,
      str(kr_screen.missing_tags))

empty = buffett_kr.screen_company("000000", "없음", [(2025, [])], years=10)
check("계정이 없으면 error", not empty.ok and "찾지 못했습니다" in empty.error)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 데모 데이터 ===")
import demo  # noqa: E402

us_screens, _ = demo.demo_screens()
us_caps = demo.demo_market_caps()
quadrants = {}
for ticker, screen in us_screens.items():
    if not screen.ok:
        continue
    result = rd.run(rd.inputs_from_screen(screen, us_caps.get(ticker)))
    quadrants[ticker] = vd.build(screen, result).quadrant
check("미국 데모에서 사분면이 갈림", len(set(quadrants.values())) >= 3,
      str(quadrants))
check("MU 는 역DCF 불가 (사이클)", quadrants.get("MU") == 0, str(quadrants))

kr_screens, _ = demo.demo_kr_screens()
kr_caps = demo.demo_kr_market_caps()
kr_quadrants = {}
for code, screen in kr_screens.items():
    result = rd.run(rd.inputs_from_screen(screen, kr_caps.get(code),
                                          currency="KRW"))
    kr_quadrants[screen.name] = vd.build(screen, result).quadrant
check("국내 데모 3종목", len(kr_quadrants) == 3, str(kr_quadrants))
check("국내 데모에서 사분면이 갈림", len(set(kr_quadrants.values())) >= 2,
      str(kr_quadrants))
check("KT&G 가 가장 많이 통과",
      kr_screens["033780"].passed_count >= kr_screens["000660"].passed_count,
      f"KT&G {kr_screens['033780'].score_label} vs "
      f"하이닉스 {kr_screens['000660'].score_label}")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 렌더링 ===")
import components as ui  # noqa: E402

cells = ui.render_dcf_cells(res)
check("DCF 칸 렌더링", "dash-dcf-grid" in cells and "요구 성장률" in cells)
check("적용 불가면 사유 표시", "0 이하" in ui.render_dcf_cells(neg))

vhtml = ui.render_verdict(q2, prompt=vd.prompt_for(q2, hi_q))
check("판단 카드 렌더링", "dash-verdict q2" in vhtml)
check("위치 표시", "②" in vhtml)
check("다음 확인 목록", "다음에 확인할 것" in vhtml and "<ol>" in vhtml)
check("프롬프트 접힘", "<details>" in vhtml)
check("굵게만 허용", "<b>" in vhtml)

check("사분면 지도", "dash-table" in ui.render_quadrant_map([q1, q2, q3, q4]))
check("빈 지도는 빈 문자열", ui.render_quadrant_map([]) == "")

check("마크다운 이스케이프",
      ui._md_bold('<img src=x onerror="y">') .startswith("&lt;img"),
      ui._md_bold('<img x>')[:30])
check("굵게는 태그로", ui._md_bold("a **b** c") == "a <b>b</b> c",
      ui._md_bold("a **b** c"))

q_xss = vd.build(Screen(ticker="<script>", name="x", years=hi_q.years), None)
check("티커 이스케이프", "&lt;script&gt;" in ui.render_quadrant_map([q_xss]))


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
