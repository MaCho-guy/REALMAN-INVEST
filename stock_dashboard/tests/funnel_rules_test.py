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

print("\n=== 거래 스크리너 — 후보 안에서의 순위 기준 ===")
import kr_screen as ks  # noqa: E402


def _prof(i, hp, contr, off, above=True):
    price = 100.0
    return ks.VolProfile(ticker=f"{i:06d}", name=f"종목{i}", bars=250, price=price,
                         high_52w=price / (hp / 100.0), low_52w=price * 0.5,
                         vol_long=30.0, vol_short=30.0 * contr, turnover=1e10,
                         ret_3m=float(i % 37), ret_6m=float(i % 41),
                         low_20d=price / (1 + off / 100.0),
                         ma20=price * (0.97 if above else 1.03), ma60=price,
                         turnover_5d=1e10, turnover_60d=1e10)


profs = [_prof(i, 30 + (i * 7) % 70, 0.5 + (i * 3 % 50) / 50, (i * 11) % 40) for i in range(200)]
vals = [ks.ValueRow(ticker=f"{i:06d}", name=f"종목{i}", pbr=0.3 + (i * 13 % 30) / 10,
                    per=3 + (i * 7 % 40), div_yield=(i * 5 % 60) / 10) for i in range(200)]
th = ks.adaptive_thresholds(profs, vals)
hits = ks.adaptive_hits(profs, vals, th)
check("기준값이 분포에서 나온다 (모두 숫자)",
      all(th[k] is not None for k in ("high", "contraction", "deep", "off_low", "pbr", "per", "div")))
check("순위판 ③은 셋 다 만족", all(
    r.pbr <= th["pbr"] and r.per <= th["per"] and r.div_yield >= th["div"]
    for r in vals if r.ticker in {h.ticker for h in hits["value_trad"]}))
check("순위판 결과가 후보 전부가 되지 않음",
      all(len(v) < len(profs) // 2 for v in hits.values()), str({k: len(v) for k, v in hits.items()}))
check("기준 글에 이번 숫자가 들어감", f"{th['contraction']:.2f}" in ks.screen_rules(th)[0][2])
check("빈 후보에도 깨지지 않음", all(v == [] for v in ks.adaptive_hits([], []).values()))
check("고정 기준 함수는 남아 있음", callable(ks.contraction_hits) and ks.CONTRACTION_MAX == 0.80)

print("\n=== 통합 후보 — 네 모델 등 · 관문 · 순서 ===")
import integrate  # noqa: E402

scr = [summ("A", [P] * 7 + [U, U]),             # 통과
       summ("B", [P] * 7 + [U, U]),
       summ("C", [P] * 7 + [U, U]),
       summ("D", [P] * 7 + [U, U]),
       summ("E", [P] * 4 + [F] * 3 + [U, U])]   # 품질 미달 — 아예 안 나옴
light_p = {"g": 0.02, "h": 0.08, "hi": 0.04, "sp": 7}
heavy_p = {"g": 0.20, "h": 0.05, "hi": 0.22, "sp": 7}
fr = {"A": {"p": light_p, "f": {"c90": 0.03}}, "B": {"p": light_p, "f": {"c90": 0.10}},
      "C": {"p": heavy_p, "f": {"c90": 0.10}}, "D": {"p": light_p, "f": {"c90": -0.08}}}
hit = {"rs": [ks.Hit("A", "A")], "surge": [ks.Hit("B", "B")]}
cands = integrate.build(scr, fr, {}, hit)
picks, out = integrate.split(cands)
check("품질 미달은 후보 · 빠짐 어디에도 없음", "E" not in {c.ticker for c in cands})
check("가격 높음 · EPS −5% 이하는 빠짐(이유 포함)",
      {c.ticker: c.excluded[:6] for c in out} == {"C": "가격 부담 높음"[:6], "D": "선행 EPS"[:6]},
      str({c.ticker: c.excluded for c in out}))
check("등은 세 개(품질 · 가격 · 선행 EPS) — 차트 · 거래는 등이 아님",
      set(picks[0].lamps) == {"quality", "price", "eps"})
check("둘 다 3/3 이면 EPS 큰 쪽이 먼저 (B +10% > A +3%)",
      [c.ticker for c in picks] == ["B", "A"] and picks[0].greens == 3 == picks[1].greens,
      str([(c.ticker, c.greens) for c in picks]))
check("거래 스크리너 신호는 근거 글에만", "시장 대비 강함" in picks[1].notes["trade"])
check("일봉이 없으면 타이밍 꼬리표 없음", not picks[0].timing)
html = ui.render_candidate_cards(picks)
check("카드 — 근거 n/3 · 등 낱말 · 선행 EPS 등", "근거 3/3" in html and "충족" in html
      and "선행 EPS" in html)


class _Row:   # 차트 행 흉내 — 과매도 진입
    ok, side = True, "os"
    states = {"cci": "과매도 진입"}


fr2 = dict(fr, A={"p": light_p, "f": {"c90": 0.001}})        # A 는 보합(노랑)
tc = integrate.build(scr, fr2, {"A": _Row()}, {})
tp, _o = integrate.split(tc)
check("타이밍 꼬리표 — 과매도 진입이면 붙고, 같은 초록 수 안에서만 앞으로",
      tp[0].ticker == "B" and tp[1].ticker == "A" and tp[1].timing and tp[1].greens == 2
      and "타이밍" in ui.render_candidate_cards(tp), str([(c.ticker, c.greens, c.timing) for c in tp]))
check("요약용 compact 카드는 근거 줄 없음",
      "ic-note" not in ui.render_candidate_cards(picks, 3, compact=True))
check("빠진 종목 목록", "가격 부담 높음" in ui.render_candidate_excluded(out))
check("빈 입력에도 깨지지 않음", integrate.build([], {}, {}, {}) == []
      and ui.render_candidate_cards([]) == "")
check("한국 찾기 = 후보 · 근거 · 차트·거래 · 모의 매수 (11/13 단순화 · 17:04 모의 매수 탭)",
      dict(config.MARKET_TABS["kr"])["찾기"] == ("picks", "basis", "timing", "paper")
      and [config.SPECIAL_TAB_LABELS[k] for k in ("picks", "basis", "timing", "paper")]
      == ["후보", "근거", "차트·거래", "모의 매수"])
check("아침 브리핑은 공통 묶음 (11/13 17:03)",
      all("briefing" in dict(config.MARKET_TABS[m])["공통"]
          and "briefing" not in dict(config.MARKET_TABS[m])["오늘"] for m in ("kr", "us")))
check("예전 탭은 옮긴 곳으로 (주소 · 세션)",
      config.KR_TAB_MOVED == {"discover": "basis", "valuation": "basis",
                              "screener": "timing", "chart": "timing"}
      and config.TAB_MOVED["kr"] is config.KR_TAB_MOVED)
check("옮긴 화면을 지우지 않고 스위치로 부름",
      '_discover_kr(use_demo, part="funnel")' in app_src.split("def render_basis_tab")[1][:6000]
      and "data, fx, use_demo, phone, market=market)" in app_src
      and "render_chart_tab(use_demo, market=market, today=False)" in app_src
      and "render_screener_tab(use_demo, market=market)" in app_src)
check("미국 찾기도 같은 3칸 · 셋째 칸 이름은 '차트' (11/13)",
      dict(config.MARKET_TABS["us"])["찾기"] == ("picks", "basis", "timing", "paper")
      and config.market_labels("us")["timing"] == "차트"
      and config.market_labels("kr")["timing"] == "차트·거래"
      and dict(config.tab_groups("us"))["찾기"][2] == ("timing", "차트"))
check("미국 예전 주소도 옮긴 탭으로", config.TAB_MOVED["us"]["discover"] == "basis"
      and config.TAB_MOVED["us"]["chart"] == "timing"
      and "config.TAB_MOVED.get(market" in app_src)

print("\n=== 미국 후보 — 품질 9개 중 7개 · 같은 관문 ===")
us_scr = [summ("BRK.B", [P] * 7 + [F, F]),          # 통과
          summ("XX", [P] * 6 + [F] + [U, U])]      # 6개 — 미국은 미달(보류)
us_fr = {"BRK.B": {"p": light_p, "f": {"c90": 0.02}}, "XX": {"p": light_p, "f": {"c90": 0.02}}}
uc = integrate.build(us_scr, us_fr, {"BRK.B": _Row()}, {}, market="us")
check("미국 — 7개 통과만 후보, 차트 표기(BRK-B → BRK.B)를 맞추면 타이밍",
      [c.ticker for c in uc] == ["BRK.B"] and uc[0].timing and uc[0].greens == 3)
check("미국 보류 정의 (미달 1개 이하 · 판정 불가 포함하면 7)",
      integrate.held_back(mk("XX", [P] * 6 + [F] + [U, U]), "us")
      and not integrate.held_back(mk("YY", [P] * 6 + [F] * 3), "us"))
oc = integrate.build([summ("O", [P] * 7 + [F, F])], {"O": {"p": light_p, "f": {"c90": 6.97}}},
                     {}, {}, market="us")
check("EPS 90일 ±100% 넘으면 이상값 — 충족 아님 · 순서는 추정 없음처럼",
      oc[0].lamps["eps"] == "-" and oc[0].eps_c90 is None and "이상값" in oc[0].notes["eps"])
check("화면이 미국 차트 표기를 맞춘다", 'str(t).replace("-", ".")' in app_src)
check("화면이 거래 스크리너 품질 스위치를 기본 켬",
      '"품질 통과 · 보류 종목만", value=True' in app_src)

print("\n=== 성장형 (11/13) — 지표 · 판정 · 후보 · 안정형 불변 ===")
import growth  # noqa: E402


def _yr(y, rev, gp, op, ocf, capex, sbc=None, eq=100.0, ltd=10.0, cash=50.0, ie=1.0):
    return buffett.YearRow(year=y, end=f"{y}-12-31", revenue=rev, gross_profit=gp,
                           operating_income=op, operating_cash_flow=ocf, capex=capex, sbc=sbc,
                           equity=eq, long_term_debt=ltd, cash=cash, interest_expense=ie)


fast = buffett.Screen("GRW", "성장회사", years=[
    _yr(2018 + i, 100 * 1.3 ** i, 70 * 1.3 ** i, 20 * 1.4 ** i, 30 * 1.3 ** i, 5 * 1.3 ** i,
        sbc=5 * 1.3 ** i) for i in range(7)])
gm = growth.metrics(fast)
check("지표 — 매출 3년 30% · 영업이익 40% · Rule of 40 · 순현금",
      abs(gm["rev3"] - 0.30) < 1e-3 and abs(gm["op3"] - 0.40) < 1e-3 and gm["r40"] > 40
      and gm["nc"] == 1 and gm["td"] == 0, str(gm))
gcs = growth.checks(gm, "us")
check("성장 품질 7개 전부 통과", [c[2] for c in gcs] == ["pass"] * 7, str(gcs))
slow = buffett.Screen("DEC", "꺾이는회사", years=[
    _yr(2018 + i, 100 - 10 * i, 40 - 4 * i, 20 - 3 * i, 25, 5) for i in range(7)])
sm = growth.metrics(slow)
check("3년 연속 동반 감소 → td=1 · 성장 미달", sm["td"] == 1 and not growth.passes(sm, "us"))
check("연도가 모자라면 키가 없음(판정 불가)",
      "rev3" not in growth.metrics(buffett.Screen("N", years=fast.years[:2])))
check("이상한 숫자에도 수집이 멈추지 않음", growth.safe_metrics(object()) == {})
check("빈 화면에도 깨지지 않음", growth.metrics(buffett.Screen("E")) == {}
      and growth.checks(None)[0][2] == "unknown")
check("한국은 매출 10% · Rule of 30", growth.checks({"rev3": 0.12}, "kr")[0][2] == "pass"
      and growth.checks({"rev3": 0.12}, "us")[0][2] == "fail")
fpe, g1, pg = growth.peg({"n": 5.0, "g1": 0.20}, 100.0)
check("PEG = 선행 PER ÷ 내년 성장률(%) — 20 ÷ 20 = 1.0", fpe == 20.0 and abs(pg - 1.0) < 1e-9)
check("내년 성장률이 0 이하면 PEG 없음", growth.peg({"n": 5.0, "g1": -0.1}, 100.0)[2] is None)
ep = funnel.eps_part({"e0": 2.0, "e1": 2.5, "p0": 2.0, "p1": 2.4, "fye": None})
check("EPS 파트에 e0 · e1 · g1(+25%)", ep["e0"] == 2.0 and ep["e1"] == 2.5 and ep["g1"] == 0.25)


class _PRow:
    ok, side, price = True, "-", 100.0
    states = {}


gs = [dict(summ("G1", [P] * 5 + [F] * 4), gr=gm), dict(summ("G2", [P] * 5 + [F] * 4), gr=gm),
      dict(summ("G3", [P] * 5 + [F] * 4), gr=gm), dict(summ("SL", [P] * 9), gr=sm)]
gfr = {"G1": {"f": {"n": 5.0, "g1": 0.20, "c90": 0.05, "c30": 0.02}},     # PEG 1.0 · 상향 지속
       "G2": {"f": {"n": 2.0, "g1": 0.10, "c90": 0.05, "c30": 0.02}},     # PEG 5.0 → 빠짐
       "G3": {"f": {"n": 5.0, "g1": 0.20, "c90": -0.08, "c30": -0.02}}}   # EPS 하향 → 빠짐
grows = {t: _PRow() for t in gfr}
gc = integrate.build_growth(gs, gfr, grows, market="us", stable={"G1"})
gp_, go_ = integrate.split(gc)
check("성장형 — 버핏식 품질 미달이어도 성장 품질 통과면 후보", [c.ticker for c in gp_] == ["G1"]
      and gp_[0].greens == 3 and gp_[0].track == "growth" and gp_[0].also)
check("성장형 관문 — PEG 2.5 초과 · EPS 하향은 빠짐",
      {c.ticker: c.excluded[:6] for c in go_} == {"G2": "가격 부담 높음"[:6], "G3": "선행 EPS"[:6]},
      str({c.ticker: c.excluded for c in go_}))
check("성장 미달(SL)은 성장형에 없음", "SL" not in {c.ticker for c in gc})
gh = ui.render_candidate_cards(gp_)
check("성장형 카드 — 등 이름 · '안정형에도'", "성장 품질" in gh and "가격 PEG" in gh
      and "추정 흐름" in gh and "안정형에도" in gh)

# 안정형 불변 — gr(성장 지표)이 붙어도 td 가 아니면 목록 · 순서가 같다
base = integrate.build(scr, fr, {}, hit)
withgr = integrate.build([dict(x, gr=gm) for x in scr], fr, {}, hit)
check("안정형 불변 — 성장 지표가 붙어도 같은 목록 · 순서",
      [(c.ticker, c.excluded) for c in base] == [(c.ticker, c.excluded) for c in withgr])
tdc = integrate.build([dict(x, gr={"td": 1}) if x["t"] == "A" else x for x in scr], fr, {}, hit)
check("추세 악화 관문 — 3년 연속 동반 감소면 안정형에서 빠짐",
      next(c for c in tdc if c.ticker == "A").excluded.startswith("실적 추세 악화"))

ck = integrate.checklist(dict(summ("G1", [P] * 9), gr=gm), gfr["G1"], _PRow(), "us", 25.0)
check("체크리스트 — 6항목 · 선행 PER 20 ≤ 중앙값 25 통과",
      len(ck) == 6 and ck[1][0] == "pass" and ck[0][0] == "pass", str(ck))
check("체크리스트 화면", "✓" in ui.render_checklist(ck) and ui.render_checklist([]) == "")
_th = pathlib.Path("theme.py").read_text(encoding="utf-8")
check("체크리스트는 9개 기준 줄(.dash-check)과 다른 클래스 — 겹치면 둘 다 깨짐 (11/13 폰)",
      'class="dash-cklist"' in ui.render_checklist(ck) and "dash-check\"" not in ui.render_checklist(ck)
      and ".dash-check {{ background" not in _th and ".dash-cklist {{ background" in _th)
check("한국 체크리스트는 주식보상 항목 없음",
      len(integrate.checklist({}, {}, None, "kr", None)) == 5)
check("수집기가 성장 지표를 싣는다",
      'gr = growth.safe_metrics(screen)' in pathlib.Path("tools/collect.py").read_text(encoding="utf-8")
      and buffett.SCREEN_REV >= 5)
import buffett_kr as _bk2  # noqa: E402
check("한국도 다시 심사(KR_REV)", _bk2.KR_REV >= 5)
check("화면 — 후보 탭에 안정형 | 성장형", '"stable": "안정형", "growth": "성장형"' in app_src)

print("\n=== 내 종목 기준 점검 · 후보 기록 (11/13) ===")
hv = integrate.assess(dict(summ("H", [P] * 3 + [F] * 6), gr={"td": 0}),
                      {"p": heavy_p, "f": {"c90": 0.02}}, None, "us", name="사이클주")
check("품질 미달 · 가격 높음은 등 색(주의)만 — 점검 필요 아님",
      hv.lamps["quality"] == "r" and hv.lamps["price"] == "r" and hv.notes["flags"] == "")
hw = integrate.assess(dict(summ("W", [P] * 9), gr={"td": 1}), {"p": light_p, "f": {"c90": -0.07}},
                      None, "us", name="꺾이는주")
check("점검 필요 = 나빠지는 신호 (EPS −5% 이하 · 실적 추세 악화)",
      "선행 EPS 90일 -7.0%" in hw.notes["flags"] and "실적 추세 악화" in hw.notes["flags"])
hn = integrate.assess(None, None, None, "kr", name="ETF", ticker="069500")
check("심사 대상 아니면 등 없음 · 점검 없음", hn.lamps["quality"] == "-" and hn.notes["flags"] == "")
hh = ui.render_holding_checks([hv, hw])
check("점검 화면 — 점검 필요 줄에만 테두리 · 문구", hh.count("hc-row warn") == 1
      and "점검 필요 — 선행 EPS" in hh)
check("내 종목 탭이 점검 칸을 부름", "_render_holding_checks(shown, use_demo, market)" in app_src)

import picks_log  # noqa: E402
snap = {"s": [["A", 3, 0, 10.0]], "g": []}
h1 = picks_log.append(None, "2026-11-12", 1.0, {"us": snap})
h2 = picks_log.append(h1, "2026-11-13", 2.0, {"us": snap, "kr": snap})
h3 = picks_log.append(h2, "2026-11-13", 3.0, {"kr": {"s": [], "g": []}})
check("후보 기록 — 날마다 한 줄 · 같은 날은 바꿈 · 빠진 시장은 같은 날 줄에서 이어받음",
      [d["d"] for d in h3["days"]] == ["2026-11-12", "2026-11-13"]
      and h3["days"][-1]["us"] == snap and h3["days"][-1]["kr"]["s"] == [])
check("오래된 날은 잘림", len(picks_log.append(
    {"days": [{"d": f"2025-01-{i:02d}"} for i in range(1, 29)]}, "2026-01-01", 0, {"us": snap},
    keep=10)["days"]) == 10)
check("요약 — (날 수, 첫 날)", picks_log.summary(h3, "us") == (2, "2026-11-12"))
ps = picks_log.snapshot(scr, fr, {}, "kr")
check("스냅숏 = 화면과 같은 안정형 후보 순서",
      [r[0] for r in ps["s"]] == [c.ticker for c in integrate.split(integrate.build(scr, fr, {}, {}))[0]])
wf = pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8")
real = pathlib.Path("../.github/workflows/collect.yml").read_text(encoding="utf-8")
check("워크플로가 지난 기록을 꺼내 이어 붙임", "picks_history.json" in wf and "picks_history.json" in real)
check("수집기가 기록 단계를 부르고 실패해도 수집은 계속",
      "h = build_picks_history(out_dir, markets)" in
      pathlib.Path("tools/collect.py").read_text(encoding="utf-8"))

print("\n=== 모의 매수 실험 (11/13) ===")
import paper  # noqa: E402

S = dict(summ("A", [P] * 7 + [U, U]))
good_fr = {"p": light_p, "f": {"c90": 0.03, "c30": 0.01}}
l0, b0 = paper.judge("stable", S, good_fr, None, "kr")
check("판정 — 근거 멀쩡하면 깨진 것 없음", b0 == [] and l0["quality"] == "g" and l0["price"] == "g")
pf0 = paper.start("2026-11-13 15:45", {("kr", "stable"): [("A", "가", l0)]},
                  {("kr", "A"): 100.0}, {"kr": 50000.0})
check("매수 — 종가 · 시장 지수 · 등 저장", pf0["pos"][0]["p0"] == 100.0 and pf0["pos"][0]["b0"] == 50000.0
      and pf0["events"][0][4] == "buy")
l1, b1 = paper.judge("stable", S, {"p": light_p, "f": {"c90": 0.001, "c30": 0.0}}, None, "kr")
pf1 = paper.step(pf0, "2026-11-14 15:45", {("kr", "stable", "A"): (l1, b1)},
                 {("kr", "A"): 103.0}, {"kr": 49000.0})
check("변경점 — 선행 EPS 충족→보통 은 기록만, 매도 아님",
      pf1["pos"][0]["state"] == "hold" and pf1["events"][-1][4] == "change"
      and "선행 EPS 충족→보통" in pf1["events"][-1][5])
l2, b2 = paper.judge("stable", S, {"p": heavy_p, "f": {"c90": -0.07}}, None, "kr")
pf2 = paper.step(pf1, "2026-11-15 15:45", {("kr", "stable", "A"): (l2, b2)},
                 {("kr", "A"): 95.0}, {"kr": 48000.0})
pz = pf2["pos"][0]
check("매도 — 근거 깨진 회차 종가 · 이유 · 수익률", pz["state"] == "sold" and pz["p1"] == 95.0
      and "가격 부담 높음" in pz["why"] and "선행 EPS 90일" in pz["why"] and abs(paper.ret(pz) + 0.05) < 1e-9)
check("시장 수익률은 매도 회차에서 멈춤", abs(paper.bench_ret(pz) - (48000 / 50000 - 1)) < 1e-9)
pf3 = paper.step(pf2, "2026-11-16 15:45", {}, {("kr", "A"): 80.0}, {"kr": 40000.0})
check("팔린 종목은 이후 가격 · 지수에 안 움직임", paper.ret(pf3["pos"][0]) == paper.ret(pz)
      and paper.bench_ret(pf3["pos"][0]) == paper.bench_ret(pz))
pfn = paper.start("d", {("kr", "stable"): [("B", "나", l0)]}, {("kr", "B"): 10.0}, {})
pfn = paper.step(pfn, "d2", {("kr", "stable", "B"): (None, [])}, {}, {})
check("데이터 없으면 팔지 않고 '판정 불가'", pfn["pos"][0]["state"] == "hold" and pfn["pos"][0].get("na")
      and pfn["events"][-1][4] == "na")
check("늦게 시작하는 묶음 (성장 지표가 다음 수집부터)",
      paper.add_sleeve(pfn, "d3", "kr", "growth", [("C", "다", {})], {("kr", "C"): 5.0}, {}) == 1
      and paper.has_sleeve(pfn, "kr", "growth"))
sm = paper.summary(pf2, "kr", "stable")
check("요약 — 보유 · 매도 · 평균 · 시장", sm["sold"] == 1 and abs(sm["avg"] + 0.05) < 1e-9
      and abs(sm["bench"] + 0.04) < 1e-9)
ph = ui.render_paper(pf2, "kr")
import theme as _th_  # noqa: E402
_css_all = _th_.build_css("kr")
check("화면 — 카드 · 매도 이유 · 변경점", "pp-row sold" in ph and "근거 깨짐" in ph and "논거 변경점" in ph)
check("빈 실험은 그리지 않음", ui.render_paper({"pos": []}, "kr") == "")
_rb = ui.render_rule_box("규칙", ["<b>매수</b> — 가", "나"])
check("규칙 상자 — 접지 않음(잘림 없음) · 줄마다 구분", "dash-clamp" not in _rb and _rb.count('class="ck"') == 2
      and ui.render_rule_box("규칙", []) == "" and 'ui.render_rule_box("규칙"' in app_src)
check("폰 본문 13px · 내비 버튼 13px 고정 (17:20)", "--fs-3: 0.82rem;   /* 13px — 본문 */" in _css_all
      and "font-size: var(--fs-nav) !important; }   /* 13px 고정" in _css_all
      and "--fs-nav: 0.82rem;" in _css_all)
col = pathlib.Path("tools/collect.py").read_text(encoding="utf-8")
check("수집기가 실험 단계를 부르고 워크플로가 이어받음",
      "pp = build_paper(out_dir, markets)" in col and "paper_portfolio.json" in wf
      and "paper_portfolio.json" in real)
check("모의 매수 탭이 실험을 그림 (17:04 후보 탭에서 뺌)",
      '_render_paper(market, opts["demo"])' in app_src
      and "_render_paper(market, use_demo)" not in app_src)

print("\n== 성장형 문턱 6 · 더 나은 기업 순서 · 모의 매수 규칙 변경 (11/13 17:02)")
import growth as _g  # noqa: E402
import integrate as _ig  # noqa: E402
import paper as _pp  # noqa: E402

check("성장 품질 6개 이상 (사용자 승인)", _g.GROWTH_MIN_PASS == 6)
_a = _ig.Candidate(ticker="A", name="a", track="growth"); _a.lamps = {"x": "g"}; _a.gscore = 6
_b = _ig.Candidate(ticker="B", name="b", track="growth"); _b.lamps = {"x": "g"}; _b.gscore = 7
check("등 수가 같으면 성장 품질 더 많이 통과한 회사 먼저", sorted([_a, _b], key=_ig.Candidate.sort_key)[0].ticker == "B")
_pf = {"pos": [{"m": "kr", "track": "growth", "t": "A", "n": "가", "d0": "d", "p0": 10.0, "l0": {}, "p": 11.0,
                "l": {}, "state": "hold", "b0": 1, "b": 1},
               {"m": "kr", "track": "stable", "t": "B", "n": "나", "d0": "d", "p0": 10.0, "l0": {}, "p": 10.0,
                "l": {}, "state": "hold", "b0": 1, "b": 1}], "events": []}
check("규칙 변경 — 성장형만 실험에서 뺌(지우지 않음) · 새 묶음 시작 가능 · 요약에서 제외",
      _pp.reset_track(_pf, "d2", "growth", "규칙", {("kr", "A"): 12.0}) == 1 and len(_pf["pos"]) == 2
      and _pf["pos"][0]["state"] == "void" and not _pp.has_sleeve(_pf, "kr", "growth")
      and _pp.has_sleeve(_pf, "kr", "stable") and _pp.summary(_pf, "kr", "growth")["n"] == 0
      and _pf["events"][-1][4] == "reset")
check("수집기가 문턱 변경을 알아채고 성장형을 다시 시작", "paper.reset_track(pf, day, \"growth\"" in col
      and '"rules": {"growth_min": growth.GROWTH_MIN_PASS}' in col)

print("\n== 차트 전략 백테스트 (techtest, 11/13)")
import techtest  # noqa: E402

check("OBV — 오르면 더하고 내리면 빼고 같으면 그대로",
      techtest._obv([1, 2, 1, 1], [5, 10, 3, 7]) == [0.0, 10.0, 7.0, 7.0])
ind0 = {"obv": [float(i) for i in range(20)]}
check("OBV 조건 — 10일 평균 위 · 5일 전보다 높음", techtest._obv_up(ind0, 15)
      and not techtest._obv_up({"obv": [float(-i) for i in range(20)]}, 15))
check("−DI 30 하향 — 최근 3봉 안에서만", techtest._mdi_cross30([None, 35, 31, 29, 28], 4)
      and not techtest._mdi_cross30([35, 29, 28, 27, 26, 25], 5))
check("CCI 탈출 시도(−100 아래 · 반등) · 탈출(−100 위로 · 0 아래) · 계속 하락은 아님",
      techtest._cci_escape([None, -150, -120], 2) and techtest._cci_escape([-150, -120, -80], 2)
      and not techtest._cci_escape([-100, -120, -150], 2))
n0 = 60


def fake(cci, mdi, close):
    pad = n0 - len(close)
    return {"c": [100.0] * pad + close, "cci": [0.0] * pad + cci, "mdi": [20.0] * pad + mdi,
            "n": n0, "date": [f"d{i:02d}" for i in range(n0)]}


orig_entry = techtest.entry
try:
    techtest.entry = lambda ind, i, v: i == n0 - 10           # 50번째 봉에서 한 번만 매수
    # 매수 50 → 54 대기(CCI 120 · −DI 8) → 56 CCI 90 · −DI 상승 → 매도
    ind = fake([0, 0, 0, 0, 120, 110, 90, 0, 0, 0], [20, 20, 20, 20, 8, 7, 9, 9, 9, 9],
               [100, 101, 102, 103, 110, 111, 112, 112, 112, 112])
    tr = techtest.trades(ind, "A")
    check("매도 신호 — 대기 뒤 CCI +100 아래 · −DI 상승", len(tr) == 1 and tr[0]["why"] == "매도 신호"
          and tr[0]["p0"] == 100 and tr[0]["p1"] == 112 and tr[0]["i1"] == n0 - 4, str(tr))
    ind = fake([0] * 10, [20] * 10, [100, 100, 100, 100, 95, 91, 90, 90, 90, 90])
    tr = techtest.trades(ind, "A")
    check("손절 −8% (종가)", tr and tr[0]["why"] == "손절 −8%" and tr[0]["p1"] == 91, str(tr))
    techtest.entry = lambda ind, i, v: i == n0 - 30           # 30번째 봉 매수 · 내내 CCI 120 · −DI 13
    ind = fake([120.0] * 30, [13.0] * 30, [100.0] * 30)
    check("대기 −DI 15 변형은 13 에서 대기, 기본(10)은 20봉 뒤 정리",
          techtest.trades(ind, "A")[0]["why"] == "대기 못 감 (20봉)"
          and techtest.trades(ind, "A15")[0]["why"] == "보유 중")
finally:
    techtest.entry = orig_entry

import random  # noqa: E402

rnd = random.Random(3)


def bars(n=200):
    c = [100.0]
    for _ in range(n - 1):
        c.append(c[-1] * (1 + rnd.gauss(0, 0.02)))
    return {"high": [x * 1.01 for x in c], "low": [x * 0.99 for x in c], "close": c,
            "volume": [rnd.randint(1000, 5000) for _ in c], "date": [f"d{i:03d}" for i in range(n)]}


res = techtest.run({f"S{i}": bars() for i in range(20)}, {}, {"S1"})
check("A5 — 5봉 창 안에서 따로 맞아도 대기, 같은 날 규칙은 아님",
      techtest._armed([120, 50, 50], [20, 20, 8], 2, 10.0, 5)
      and not techtest._armed([120, 50, 50], [20, 20, 8], 2, 10.0, 1))
check("묶음 — 변형 9개(스토캐스틱 S · S_vol · SX 포함) · 오늘 신호 A/S/C · 기간",
      set(res["variants"]) == set(techtest.VARIANTS) and len(techtest.VARIANTS) == 9
      and set(res["signals"]) == {"A", "C", "S"} and res["window"]["to"] == "d199")
_si = {"sk": [50, 40, 25, 20, 22, 30, 35], "sd": [50, 45, 35, 25, 21, 24, 28]}
check("슬로우 스토캐스틱 확인 — 30 이하 뒤 %K 가 %D 위로", techtest._stoch_up(_si, 6)
      and not techtest._stoch_up({"sk": [50] * 7, "sd": [40] * 7}, 6))
check("C 는 허용 종목만", all(x["s"] == "S1" for x in res["variants"]["C"]["recent"]))
check("짧은 · 빈 일봉은 건너뜀", techtest.run({"X": {"close": [1, 2]}, "Y": {}})["n_syms"] == 0)
bh = ui.render_backtest(res, "kr")
check("화면 — 변형 카드 · 오늘 신호 · 최근 거래", "A · OBV (기본)" in bh and "오늘 매수 신호" in bh
      and ("최근 거래" in bh or res["variants"]["A"]["trades"] == 0))
check("빈 결과는 그리지 않음", ui.render_backtest({}, "kr") == "")
check("수집기 · 화면 연결", "build_backtest(out_dir" in col and "_render_backtest(market, use_demo)"
      in app_src and "backtest_tech" in config.UNIVERSE_URLS)

print("\n== 폰 글자 크기 · 글꼴 (11/13)")
import theme  # noqa: E402

_css = theme.build_css("kr")
check("글꼴 하나로 — 스트림릿 글 상자 · 캡션도 system-ui",
      '.stApp [data-testid="stMarkdownContainer"],\n  .stApp [data-testid="stCaptionContainer"] p,' in _css
      and '[data-testid="stHeadingWithActionElements"] * { font-family: system-ui' in _css)
check("글자 규칙이 표→카드 규칙보다 뒤 (덮어씀)", _css.index("⓪") > _css.index("table.dash-stk thead"))
check("폰 — 본문 15 · 설명 14 · 리포트 카드 제목 = 리포트 제목",
      ".dash-section-sub, .dash-section-count { font-size: var(--fs-2); }" in _css
      and "td.rt-title {\n      order: -1;" in _css)
ckh = ui.render_checklist([("pass", "가", "근거1"), ("unknown", "나", "근거2")], "추가 확인", "설명")
check("추가 확인 카드 — 항목 / 근거 두 줄 · 상태 글자 · 설명 줄",
      ckh.count('class="ck-top"') == 2 and "좋음" in ckh and "자료 부족" in ckh and 'class="ck-s"' in ckh)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
