"""
사이클 국면 기록(cycle_phase) 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/cycle_phase_test.py

검증 범위: 실제 기록 파일 읽기, §5 상태 규칙(유지/전환 감시/재판정), 스프레드
           계산, 신선도 경계, 형식 오류를 던지지 않고 담기, 공시 자동 대조
           (회사 2곳 이상 판정될 때만 결론), 종목 칩, 국면 보드 경고, 요약 줄.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
import cycle  # noqa: E402
import cycle_phase as cp  # noqa: E402
import summary as sm  # noqa: E402

FAILURES: list[str] = []
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(HERE, cp.PHASE_FILE)


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def raw() -> dict:
    with open(REAL, encoding="utf-8") as fh:
        return json.load(fh)


def with_states(states: dict[int, str]) -> cp.Phase:
    data = raw()
    for c in data["checklist"]:
        if c["n"] in states:
            c["state"] = states[c["n"]]
            # 강도는 점등 항목만 1~3 (2026-11-16 형식 검사)
            c["strength"] = (c.get("strength") or 1) if c["state"] == "lit" else 0
    return cp.parse(data)


def trend(name: str, invs, revs=None) -> cycle.InventoryTrend:
    qs = [cycle.QuarterMetrics(year=2026, quarter=f"{i + 1}Q", fs_div="CFS",
                               inventory=v, cost_of_sales=100.0,
                               revenue=(revs[i] if revs else 200.0))
          for i, v in enumerate(invs)]
    return cycle.InventoryTrend(corp_name=name, stock_code=name, quarters=qs)


RISING = [100, 110, 120]     # DIO 2분기 연속 상승 + 재고 증가 > 매출 → ①② 점등
FALLING = [120, 110, 100]    # 둘 다 미점등

print("── 실제 기록 파일")
ph = cp.load(REAL)
check("읽힘", ph.ok, ph.error)
check("4트랙", [t.key for t in ph.tracks] == ["hbm", "dram", "nand", "legacy"])
check("체크리스트 10개 · 번호 1~10", [c.n for c in ph.checklist] == list(range(1, 11)))
check("자동 대조 항목은 재고 3개", [c.n for c in ph.checklist if c.auto] == [3, 4, 5])
check("체크리스트 트랙 = 범용 D램", ph.main_track is not None and ph.main_track.key == "dram")
check("노출 트랙이 전부 있는 트랙", all(ph.tracks_for(s) for s in ph.exposure))
check("관심종목에 없는 종목은 칩 없음", ph.tracks_for("GOOGL") == [])

print("── §5 상태 규칙")
hold = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 2: "lit"})
check("점등 2개 → 유지", hold.status == cp.STATUS_HOLD, str(hold.lit_count))
watch = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 2: "lit", 6: "lit", 8: "lit"})
check("점등 4개 · 레이어 2 없음 → 전환 감시", watch.status == cp.STATUS_WATCH)
rej = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 3: "lit", 4: "lit"})
check("점등 3개 · ③④ 동시 → 재판정 필요", rej.status == cp.STATUS_REJUDGE)
one = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 6: "lit", 3: "lit"})
check("③ 하나만 점등이면 재고 미점등 → 전환 감시 (11/16 규칙)", one.status == cp.STATUS_WATCH)
gap_only = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 6: "lit", 4: "lit"})
check("④ 하나만 점등이어도 전환 감시", gap_only.status == cp.STATUS_WATCH)
fg = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 6: "lit", 5: "lit"})
check("⑤ 완제품 급증은 단독으로 재고 점등 → 재판정", fg.status == cp.STATUS_REJUDGE)
mixed = with_states({n: "unlit" for n in range(1, 11)} | {1: "lit", 6: "lit", 9: "lit"})
check("'2·3' 겸용 항목(어조)은 레이어 2 로 세지 않음", mixed.status == cp.STATUS_WATCH)
check("현재 기록 = 전환 감시, 점등 4", ph.status == cp.STATUS_WATCH and ph.lit_count == 4)

print("── 레이어 1 스프레드")
P = ph.prices
check("DDR4 8Gb 스프레드 = 현물/고정 − 1 (같은 품목)",
      abs(ph.spread - (P.ddr4_8gb_spot / P.ddr4_8gb_contract - 1) * 100) < 1e-9, f"{ph.spread:.2f}%")
check("기준일(11/3) 스프레드 +70.3%", round(ph.ref_spread, 1) == 70.3)
check("11/12 스프레드 +62.6% (§8-1 정정값)", round(ph.spread, 1) == 62.6, f"{ph.spread:.2f}")
check("DDR5 변화 = 현물/기준 − 1",
      abs(ph.ddr5_change_pct - (P.ddr5_16gb_spot / P.ref_ddr5_16gb_spot - 1) * 100) < 1e-9)
nocon = copy.deepcopy(raw())
nocon["prices"]["ddr4_8gb_contract"] = 0
check("고정가 0 이면 스프레드 계산 안 함", cp.parse(nocon).spread is None)

print("── 신선도")
base = ph.as_of
check("판정 14일째는 신선", not ph.is_stale(base + dt.timedelta(days=cp.STALE_PHASE_DAYS)))
check("판정 15일째는 점검 필요", ph.is_stale(base + dt.timedelta(days=cp.STALE_PHASE_DAYS + 1)))
sd = ph.prices.spot_date
check("현물 7일째는 신선", not ph.price_stale(sd + dt.timedelta(days=cp.STALE_PRICE_DAYS)))
check("현물 8일째는 오래됨", ph.price_stale(sd + dt.timedelta(days=cp.STALE_PRICE_DAYS + 1)))
nod = copy.deepcopy(raw())
nod["prices"]["spot_date"] = None
check("현물 날짜가 없으면 오래됨으로", cp.parse(nod).price_stale(base))

print("── 형식 오류는 던지지 않고 담는다")
cases = {
    "as_of 없음": lambda d: d.pop("as_of"),
    "phase 5": lambda d: d["tracks"][0].__setitem__("phase", 5),
    "state 오타": lambda d: d["checklist"][0].__setitem__("state", "on"),
    "auto 오타": lambda d: d["checklist"][2].__setitem__("auto", "dio"),
    "없는 트랙 노출": lambda d: d["exposure"]["MU"].__setitem__("tracks", ["dram", "logic"]),
    "체크리스트 트랙 없음": lambda d: d.__setitem__("checklist_track", "foundry"),
}
with tempfile.TemporaryDirectory() as tmp:
    for label, mutate in cases.items():
        d = raw()
        mutate(d)
        path = os.path.join(tmp, "p.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
        got = cp.load(path)
        check(f"{label} → error 에 사유", not got.ok and "형식 오류" in got.error, got.error)
    bad = os.path.join(tmp, "broken.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    check("깨진 JSON → error", not cp.load(bad).ok and "읽지 못했습니다" in cp.load(bad).error)
    check("파일 없음 → error", "없습니다" in cp.load(os.path.join(tmp, "none.json")).error)

print("── 공시 자동 대조")
three_up = {"MU": trend("Micron", RISING), "005930": trend("삼성전자", RISING),
            "000660": trend("SK하이닉스", FALLING)}
ck = cp.cross_check(ph, three_up)
check("자동 대조는 재고 3항목만", sorted(ck) == [3, 4, 5])
check("3곳 중 2곳 점등 → 점등", ck[3].state == "lit", ck[3].detail)
check("기록(미점등)과 다름 → agrees=False", ck[3].agrees is False)
check("완제품(구성 없음) → 판정 불가 · 대조 안 함", ck[5].state == "unknown" and ck[5].agrees is None)
check("회사별 상태가 세부에 적힘", "Micron 점등" in ck[3].detail and "SK하이닉스 미점등" in ck[3].detail)
check("다른 항목 번호 목록", cp.disagreements(ck) == [3, 4])

one_up = {"MU": trend("Micron", RISING), "005930": trend("삼성전자", FALLING),
          "000660": trend("SK하이닉스", FALLING)}
ck1 = cp.cross_check(ph, one_up)
check("한 곳만 점등 → 미점등 (회사 사정)", ck1[3].state == "unlit" and ck1[3].agrees is True)
only_one = cp.cross_check(ph, {"MU": trend("Micron", RISING)})
check("판정된 회사 1곳뿐 → 판정 불가", only_one[3].state == "unknown" and only_one[3].agrees is None)
check("재고 데이터 없음 → 대조 없음", cp.cross_check(ph, {}) == {})
check("기록이 깨졌으면 대조 없음", cp.cross_check(cp.Phase(error="x"), three_up) == {})

print("── 내 종목 칩")
today = ph.as_of + dt.timedelta(days=3)
html_skh = ui.phase_chips_html(ph, "000660", today)
check("SK하이닉스 — HBM · D램 · 낸드 순", html_skh.index("HBM") < html_skh.index("D램") < html_skh.index("낸드"))
check("낸드 ③ 은 남색 칩(p3)", 'cyc-chip p3">낸드' in html_skh)
check("SK스퀘어 — 경유 표시", "SK하이닉스 경유" in ui.phase_chips_html(ph, "402340", today))
check("신선할 때는 '판정 N일 전' 없음", "cyc-stale" not in html_skh)
late = ui.phase_chips_html(ph, "000660", ph.as_of + dt.timedelta(days=20))
check("15일 넘으면 '판정 20일 전'", "판정 20일 전" in late)
check("노출 없는 종목은 빈 문자열", ui.phase_chips_html(ph, "GOOGL", today) == "")
check("기록이 깨졌으면 빈 문자열", ui.phase_chips_html(cp.Phase(error="x"), "000660", today) == "")


class _Inst:
    def __init__(self, sym, name):
        self.symbol, self.name, self.decimals = sym, name, 0

    def resolved_link(self):
        return ""


rows = [(_Inst("000660", "SK하이닉스"), None, []), (_Inst("GOOGL", "Alphabet"), None, [])]
with_phase = ui.render_holdings_table(rows, phase=ph, today=today)
without = ui.render_holdings_table(rows)
check("표 — 메모리 종목만 칩", with_phase.count("hd-cyc") == 1)
check("표 — phase 를 안 주면 예전과 같음", "hd-cyc" not in without)

print("── 국면 보드")
board = ui.render_phase_board(ph, today, {})
check("상태 칩 '전환 감시'", "ph-status watch" in board)
check("점등 4/10", "점등 4/10" in board)
check("현물이 신선하면 갱신 필요 없음", "갱신 필요" not in board,
      f"현물 {ph.price_age_days(today)}일 전")
stale_day = ph.prices.spot_date + dt.timedelta(days=cp.STALE_PRICE_DAYS + 1)
stale_board = ui.render_phase_board(ph, stale_day, {})
check("현물 8일 지나면 → 갱신 필요 · 회색", "갱신 필요" in stale_board and "ph-price stale" in stale_board)
check("판정 3일 전 → 점검 경고 없음", "점검이 필요합니다" not in board)
old_board = ui.render_phase_board(ph, ph.as_of + dt.timedelta(days=15), {})
check("판정 15일 전 → 점검 경고", "점검이 필요합니다" in old_board)
diff_board = ui.render_phase_board(ph, today, ck)
check("공시가 기록과 다르면 경고", "3번, 4번" in diff_board)
check("깨진 기록 → 사유를 보여줌", "읽지 못했습니다" in ui.render_phase_board(cp.Phase(error="없음"), today))
cl = ui.render_phase_checklist(ph, today, ck)
check("체크리스트 — 다른 행 강조", cl.count('class="diff"') == 2)
check("체크리스트 — 수동 항목 표시", "수동" in cl)
check("체크리스트 — 다음 데이터 목록", "다음 데이터" in cl and "마이크론 FQ1-27" in cl)

print("── 요약 줄")
r = sm.row_cycle({}, [], ph, today)
check("머리말이 국면부터", r.headline.startswith("D램 ②후반 (전환 감시)"), r.headline)
check("전환 감시만으로는 '볼 것 있음' 아님", r.level == "quiet")
check("낸드가 먼저 둔화한 것을 적음", "낸드 ③진입 먼저 둔화" in r.detail)
r_old = sm.row_cycle({}, [], ph, ph.as_of + dt.timedelta(days=15))
check("판정이 오래되면 '볼 것 있음'", r_old.level == "watch" and "점검 필요" in r_old.detail)
r_diff = sm.row_cycle(three_up, [], ph, today)
check("공시가 기록과 다르면 '볼 것 있음'", r_diff.level == "watch" and "달라짐" in r_diff.detail)
r_demo = sm.row_cycle(three_up, [], ph, today, phase_check=False)
check("데모(대조 끔) — 기록과 다름 안 뜸", "달라짐" not in r_demo.detail)
r_rej = sm.row_cycle({}, [], rej, today)
check("재판정 필요 → '볼 것 있음'", r_rej.level == "watch" and "재판정" in r_rej.headline)
r_none = sm.row_cycle({}, [], None, today)
check("기록 없으면 예전 동작(데이터 없음)", r_none.level == "unknown")
r_err = sm.row_cycle({}, [], cp.Phase(error="x"), today)
check("깨진 기록도 예전 동작", r_err.level == "unknown")

print()
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
