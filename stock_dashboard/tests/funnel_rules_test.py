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
check("한국 찾기 = 후보 · 근거 · 차트·거래 3칸 (11/13 단순화)",
      dict(config.MARKET_TABS["kr"])["찾기"] == ("picks", "basis", "timing")
      and [config.SPECIAL_TAB_LABELS[k] for k in ("picks", "basis", "timing")]
      == ["후보", "근거", "차트·거래"])
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
      dict(config.MARKET_TABS["us"])["찾기"] == ("picks", "basis", "timing")
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

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
