"""
사이클 보강 테스트 (2026-11-16) — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/cycle_extras_test.py

검증 범위:
  · 누적(YTD) → 분기 차분 (sources.edgar_xbrl.derive_quarters) — 4분기 · 현금흐름
  · 미국 재고 추세가 4분기를 포함하게 됐는가 (build_trend_from_xbrl)
  · 백테스트 — 번들 MU 이력에서 사이클 4번, 규칙별 점수가 손계산과 일치
  · 하이퍼스케일러 CapEx — 달력 분기 정렬, 누적 차분, 합계는 4사 다 있을 때만
  · 체크리스트 근거일 · 강도 검증, 판정 이력 일치 검사, 화면 문구
  · 트랙별 재고 요약
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
import cycle  # noqa: E402
import cycle_backtest as bt  # noqa: E402
import cycle_phase as cp  # noqa: E402
import hyperscaler_capex as hx  # noqa: E402
from sources.edgar_xbrl import Fact, derive_quarters  # noqa: E402

FAILURES: list[str] = []
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def F(start, end, val, fp="Q1", form="10-Q", fy=2026, filed="2026-01-01"):
    return Fact(start, end, float(val), form, fy, fp, filed)


# ──────────────────────────────────────────────────────────────────────────────
print("── 누적 → 분기 차분")
ytd = [F("2025-07-01", "2025-09-30", 10), F("2025-07-01", "2025-12-31", 25, "Q2"),
       F("2025-07-01", "2026-03-31", 45, "Q3"), F("2025-07-01", "2026-06-30", 70, "FY", "10-K")]
q = derive_quarters(ytd)
check("4개 분기", len(q) == 4, str([x.val for x in q]))
check("값 = 10, 15, 20, 25", [x.val for x in q] == [10, 15, 20, 25])
check("4분기는 fp=Q4 · '(차분)' 표시", q[-1].fp == "Q4" and "(차분)" in q[-1].form)
check("차분 분기 시작일 = 앞 누적 종료일 다음 날", q[1].start == "2025-10-01")
direct = ytd + [F("2025-10-01", "2025-12-31", 16, "Q2")]
q2 = derive_quarters(direct)
check("같은 종료일 직접 분기가 있으면 그걸 씀", next(x for x in q2 if x.end == "2025-12-31").val == 16)
odd = [F("2025-01-01", "2025-03-31", 5), F("2025-01-01", "2025-12-31", 50, "FY", "10-K")]
check("간격이 분기가 아니면(3개월 → 12개월) 차분하지 않음",
      [x.end for x in derive_quarters(odd)] == ["2025-03-31"])

print("── 미국 재고 추세에 4분기 포함")
inv = [Fact(None, e, v, "10-Q", 2026, "Q", "2026-01-01")
       for e, v in (("2025-11-27", 100), ("2026-02-26", 110), ("2026-05-28", 120), ("2026-09-03", 150))]
cos = [F("2025-08-29", "2025-11-27", 90, "Q1"), F("2025-11-28", "2026-02-26", 90, "Q2"),
       F("2026-02-27", "2026-05-28", 90, "Q3"),
       F("2025-08-29", "2026-02-26", 180, "Q2"), F("2025-08-29", "2026-05-28", 270, "Q3"),
       F("2025-08-29", "2026-09-03", 370, "FY", "10-K")]
rev = [F(f.start, f.end, f.val * 2, f.fp, f.form) for f in cos]
tr = cycle.build_trend_from_xbrl("Micron", "MU", inv, cos, rev, quarters=6)
ends = [x.period_end for x in tr.quarters]
check("4분기(2026-09-03)가 시계열에 있음", "2026-09-03" in ends, str(ends))
q4 = next(x for x in tr.quarters if x.period_end == "2026-09-03")
check("4분기 매출원가 = 연간 370 − 3분기 누적 270 = 100", q4.cost_of_sales == 100)
check("4분기 매출도 차분으로 붙음", q4.revenue == 200)

# ──────────────────────────────────────────────────────────────────────────────
print("── 백테스트 (번들 MU 이력)")
res = bt.run_file()
check("읽기 성공", res.ok, res.error)
check("분기 66개 · 2009-02 ~ 2025-05", len(res.quarters) == 66 and res.span == "2009-02 ~ 2025-05")
check("사이클 4번 — 피크 2010-08 · 2014-11 · 2018-08 · 2022-05",
      [c.peak[:7] for c in res.cycles] == ["2010-08", "2014-11", "2018-08", "2022-05"],
      str([c.peak for c in res.cycles]))
q18 = next(x for x in res.quarters if x.end == "2018-08-31")
check("2018-08 DIO = 3,595 ÷ 3,289 × 91.25 ≈ 99.7일", abs(q18.dio - 3595 / 3289 * 91.25) < 1e-9
      and round(q18.dio, 1) == 99.7)
check("2018-08 매출총이익률 61.0%", round(q18.gross_margin, 1) == 61.0)
s_any, s_both, s3 = res.score("any"), res.score("both"), res.score("i3")
check("옛 정의 ③ 또는 ④ 점등 32/66", (s_any.lit_quarters, s_any.total) == (32, 66))
check("옛 정의 ③ 또는 ④ 확장기 오경보 6/23", (s_any.early_alarms, s_any.expansion_quarters) == (6, 23))
check("'③ 그리고 ④' 점등 10/66 · 오경보 0", s_both.lit_quarters == 10 and s_both.early_alarms == 0)
check("'③ 그리고 ④' 피크 대비 [-1, -2, +2, -1]", s_both.first_vs_peak == [-1, -2, 2, -1])
check("2018 피크에서는 ③이 2분기 지연", s3.first_vs_peak[2] == 2)
check("중앙값 선행 −1분기 (③)", s3.median_lead == -1.0)
html = ui.render_cycle_backtest(res)
check("화면: 규칙 6줄 · 한계 문구", html.count('<td class="bt-r">') == 6 and "과거 자료가 없어" in html)
check("화면: 피크 대비 부호 표기 (+2 지연 · −1 선행)", '<span class="lag">+2</span>' in html
      and '<span class="lead">-1</span>' in html and "1분기 먼저" in html)
short = bt.run(res.quarters[:8])
check("분기가 부족하면 오류로 담음", not short.ok and "12개" in short.error)
check("파일이 없으면 오류로 담음", not bt.run_file("nope.csv").ok)
check("화면: 달러 단위 · 피크 개수", "$8,440M" in html and "피크 4번뿐" in html)
kr_res = bt.run(res.quarters, company="SK하이닉스", unit="KRW")
check("원화 결과는 조원으로", kr_res.money(13_811_001_000_000) == "13.8조원")

# ──────────────────────────────────────────────────────────────────────────────
print("── 하이퍼스케일러 CapEx")
check("달력 분기 — 2026-09-30 → 2026Q3", hx.calendar_quarter("2026-09-30") == "2026Q3")
check("달력 분기 — 2025-12-28(주 단위 결산) → 2025Q4", hx.calendar_quarter("2025-12-28") == "2025Q4")
check("달력 분기 — 말일에서 멀면 None", hx.calendar_quarter("2026-08-15") is None)


def ytd_facts(fy_start, ends_vals, tag="PaymentsToAcquirePropertyPlantAndEquipment"):
    out = []
    for i, (e, v) in enumerate(ends_vals):
        out.append(Fact(fy_start, e, v * 1e6, "10-K" if i == 3 else "10-Q", 2026,
                        "FY" if i == 3 else f"Q{i + 1}", "2026-10-30", tag=tag))
    return out


msft = ytd_facts("2025-07-01", [("2025-09-30", 19000), ("2025-12-31", 40000),
                                ("2026-03-31", 62000), ("2026-06-30", 87000)])
cal = ytd_facts("2026-01-01", [("2026-03-31", 20000), ("2026-06-30", 42000), ("2026-09-30", 66000)])
cal_prev = ytd_facts("2025-01-01", [("2025-03-31", 15000), ("2025-06-30", 31000), ("2025-09-30", 48000),
                                   ("2025-12-31", 66000)])
per = {"MSFT": ("PaymentsToAcquirePropertyPlantAndEquipment", msft),
       "GOOGL": ("PaymentsToAcquirePropertyPlantAndEquipment", cal + cal_prev),
       "AMZN": ("PaymentsToAcquireProductiveAssets", cal + cal_prev),
       "META": "SEC 403"}
tb = hx.build(per)
m = next(c for c in tb.companies if c.symbol == "MSFT")
check("MSFT 6월 결산 — 4분기(2026Q2) = 87,000 − 62,000", m.by_quarter.get("2026Q2") == 25000)
check("MSFT 2025Q4 = 40,000 − 19,000 · 차분 표시", m.by_quarter.get("2025Q4") == 21000 and "2025Q4" in m.derived)
check("한 회사라도 없으면 합계 없음 (META 오류)", tb.total("2026Q2") is None)
g = next(c for c in tb.companies if c.symbol == "GOOGL")
check("GOOGL 2026Q3 = 66,000 − 42,000", g.by_quarter.get("2026Q3") == 24000)
check("회사 전년비 = 24,000 / 17,000 − 1", abs(tb.yoy("2026Q3", g) - (24000 / 17000 - 1) * 100) < 1e-9)
full = hx.build({**per, "META": ("PaymentsToAcquirePropertyPlantAndEquipment", cal + cal_prev)})
check("4사 다 있으면 합계 (2026Q1: MSFT 22,000 + 20,000×3)", full.total("2026Q1") == 22000 + 60000)
check("최근 합계 분기 = 2026Q2 (MSFT 가 2026Q3 없음)", full.latest_full == "2026Q2")
tag, facts = hx.pick_latest_tag({"A": [F("2010-01-01", "2010-12-31", 1)], "B": cal})
check("태그 후보 중 최신 종료일이 늦은 쪽", tag == "B")
ch = ui.render_capex(full)
check("화면: 4사 합계 · 차분 표시 · 리스 주의", "4사 합계" in ch and "*" in ch and "금융리스" in ch)
check("화면: 오류면 사유", "403" in ui.render_capex(None, "SEC 403"))

# ──────────────────────────────────────────────────────────────────────────────
print("── 근거일 · 강도 · 이력")
real = json.load(open(cp.PHASE_FILE, encoding="utf-8"))
ph = cp.parse(real)
check("실제 기록 — 점등 항목은 전부 강도 1~3", all(c.strength in (1, 2, 3) for c in ph.checklist if c.state == "lit"))
check("실제 기록 — 모든 항목에 근거일", all(c.evidence_date for c in ph.checklist))
check("실제 기록 — 이력 마지막이 현재와 일치", ph.history_gap() == "", ph.history_gap())
check("실제 기록 — 이력은 날짜순", [h.as_of for h in ph.history] == sorted(h.as_of for h in ph.history))

bad = copy.deepcopy(real)
next(c for c in bad["checklist"] if c["state"] == "lit")["strength"] = 0

def _try(d):
    try:
        cp.parse(d)
        return ""
    except ValueError as exc:
        return str(exc)


check("점등인데 강도 0 → 형식 오류", "strength" in _try(bad))
bad2 = copy.deepcopy(real)
next(c for c in bad2["checklist"] if c["state"] == "unlit")["strength"] = 2
check("미점등인데 강도 2 → 형식 오류", "0 이어야" in _try(bad2))
bad3 = copy.deepcopy(real)
bad3["history"][0]["phases"]["zzz"] = "②"
check("이력에 없는 트랙 → 형식 오류", "없는 트랙" in _try(bad3))

day = ph.as_of + dt.timedelta(days=3)
check("3일 뒤 — 오래된 근거 없음", ph.stale_evidence(day) == [])
far = max(c.evidence_date for c in ph.checklist) + dt.timedelta(days=cp.EVIDENCE_STALE_DAYS + 1)
check("31일 지나면 전 항목 재확인", len(ph.stale_evidence(far)) == len(ph.checklist))

moved = copy.deepcopy(real)
moved["as_of"] = "2026-11-20"
pm = cp.parse(moved)
check("판정일만 바꾸고 이력 안 적으면 경고", "다릅니다" in pm.history_gap())
board = ui.render_phase_board(pm, pm.as_of, {})
check("보드에 이력 경고", "판정 이력" in board)
changed = copy.deepcopy(real)
changed["history"].append({"as_of": "2026-11-20", "phases": {**real["history"][-1]["phases"], "dram": "③진입"},
                           "lit": 4, "status": "전환 감시"})
pc = cp.parse(changed)
check("이력 변화 감지 — 마지막 줄에서 dram 바뀜", pc.changes_at(len(pc.history) - 1) == {"dram"})

b = ui.render_phase_board(ph, day, {})
check("보드: 점등 강도 요약 (강 1 · 중 3)", "강 1 · 중 3" in b, b[b.find("ph-lit"):b.find("ph-lit") + 80])
cl = ui.render_phase_checklist(ph, day, {})
check("체크리스트: 근거 날짜 · 강도 점", "근거 11/12" in cl and "●●●" in cl and "확인 11/16" in cl)
check("체크리스트: 강도 정의 문구", "여러 출처" in cl)
cl_old = ui.render_phase_checklist(ph, far, {})
check("오래되면 '재확인'", "재확인" in cl_old and "cl-ev old" in cl_old)
hh = ui.render_phase_history(pc)
check("이력 표: 최신이 위 · 바뀐 칸 굵게", hh.find("11/20") < hh.find("11/13") and 'class="chg"' in hh)

# ──────────────────────────────────────────────────────────────────────────────
print("── 트랙별 재고")


def mk_trend(name, dios, revs):
    t = cycle.InventoryTrend(corp_name=name, stock_code=name)
    for i, (dio, rv) in enumerate(zip(dios, revs)):
        qm = cycle.QuarterMetrics(year=2026, quarter=f"Q{i + 1}", fs_div="XBRL",
                                  inventory=dio * 100 / 91.25, cost_of_sales=100.0, revenue=rv)
        qm.explicit_period_days = 91.25
        qm.period_end = f"2026-0{i + 1}-28"
        t.quarters.append(qm)
    return t


up = mk_trend("Texas Instruments", [180, 190, 200], [100, 100, 100])     # DIO 2분기↑, 재고 > 매출
flat = mk_trend("Analog Devices", [150, 140, 145], [100, 100, 120])
ti = cp.track_inventory({"legacy": {"TXN": up, "ADI": flat, "MCHP": None}},
                        {"MCHP": "CIK 를 찾지 못했습니다"})["legacy"]
check("TXN DIO 2분기 연속 상승 점등", ti.rows[0].i3 is True and ti.rows[0].rising == 2)
check("ADI 미점등", ti.rows[1].i3 is False)
check("MCHP 오류 행", ti.rows[2].error.startswith("CIK"))
check("요약: DIO 2분기↑ 1/2", ti.summary.startswith("DIO 2분기↑ 1/2"), ti.summary)
check("③④ 동시 1/2", ti.both == (1, 2))
b2 = ui.render_phase_board(ph, day, {}, {"legacy": ti})
check("보드 레거시 카드에 재고 한 줄 · 동시 점등이면 강조", "ph-inv hot" in b2 and "TXN·ADI·MCHP" in b2)
tt = ui.render_track_inventory({"legacy": ti}, ph)
check("트랙 재고 표: 트랙 이름 · 참고 문구", "레거시" in tt and "참고 표" in tt)
empty = cp.track_inventory({"nand": {"SNDK": None}}, {})["nand"]
check("전부 실패면 '재고 공시 대기'", empty.summary == "재고 공시 대기")

print("── 국내(DART) 연간 → 4분기 · 백테스트 입력")
from sources.dart import Account  # noqa: E402


def acc(sj, aid, cur, cum=None):
    return Account(sj_div=sj, sj_nm="", account_id=aid, account_nm="", thstrm_amount=cur,
                   thstrm_add_amount=cum, frmtrm_amount=None, bfefrmtrm_amount=None)


def accounts(inv, cos, rev, cos_cum=None, rev_cum=None):
    return [acc("BS", "ifrs-full_Inventories", inv), acc("IS", "ifrs-full_CostOfSales", cos, cos_cum),
            acc("IS", "ifrs-full_Revenue", rev, rev_cum)]


col = [(2025, "1Q", "CFS", accounts(50, 40, 70)), (2025, "2Q", "CFS", accounts(52, 42, 75)),
       (2025, "3Q", "CFS", accounts(55, 45, 80, cos_cum=127, rev_cum=225)),
       (2025, "FY", "CFS", accounts(60, 175, 310)), (2026, "1Q", "CFS", accounts(62, 50, 90))]
kt = cycle.build_trend("SK하이닉스", "000660", col)
q4 = next(x for x in kt.quarters if x.year == 2025 and x.quarter == "4Q")
check("연간 → 4분기: 매출원가 175 − 127 = 48", q4.cost_of_sales == 48)
check("연간 → 4분기: 매출 310 − 225 = 85", q4.revenue == 85)
check("4분기 DIO 는 91.25일 기준", abs(q4.dio - 60 / 48 * 91.25) < 1e-9)
check("순서: 3분기 → 4분기 → 다음 해 1분기", [x.quarter for x in kt.quarters][-3:] == ["3Q", "4Q", "1Q"])
gap = kt.inventory_revenue_gap
check("1분기 갭 = 재고 +3.3% − 매출 +5.9% (연간과 비교하지 않음)",
      abs(gap - ((62 / 60 - 1) * 100 - (90 / 85 - 1) * 100)) < 1e-9, f"{gap:.2f}")
no3q = cycle.build_trend("x", "x", [(2024, "FY", "CFS", accounts(60, 175, 310))])
check("3분기 누적이 없으면 연간 그대로", no3q.quarters[0].quarter == "FY")
bq = bt.from_trend(kt)
check("백테스트 입력: 5분기 · 4분기 말일 12-31", len(bq) == 5 and bq[3].end == "2025-12-31")
check("연간 그대로 남은 분기는 백테스트에서 뺌", bt.from_trend(no3q) == [])

print()
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
