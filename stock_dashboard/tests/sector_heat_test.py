"""
섹터 온도 + 스트림릿 테마 동기화 테스트.

섹터 온도는 산술(기간 수익률·상대강도·구간 위치)이라 이론값과 맞춰 볼 수
있습니다. 종목코드 검증(야후 이름 대조)은 **틀렸을 때 조용히 지나가지
않는지**를 봅니다 — 이 화면에서 제일 비싼 실수는 다른 ETF 의 수익률이
'반도체' 이름표를 달고 나오는 것입니다.

스트림릿 테마는 .streamlit/config.toml 에 따로 적혀 있어서 theme.py 를
고쳐도 같이 안 바뀝니다. 2026-11-11 에 실제로 config.toml 이 다크로 남아
위젯 글자가 흰 패널 위에서 안 보였습니다.
"""

from __future__ import annotations

import math
import os
import pathlib
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
import config  # noqa: E402
import demo as demo_mod  # noqa: E402
import sector_heat as sh  # noqa: E402
import summary as sm  # noqa: E402
import theme  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}"
          f"{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def walk(n, drift, sd, seed, start=10_000.0):
    r = random.Random(seed)
    p, out = start, []
    for _ in range(n):
        p *= math.exp(r.gauss(drift, sd))
        out.append(p)
    return out


print("=== 기간 수익률 ===")
up = [100 * 1.01 ** i for i in range(300)]
check("1일", abs(sh.period_return(up, 1) - 1.0) < 1e-9)
check("1주(5일)", abs(sh.period_return(up, 5) - (1.01 ** 5 - 1) * 100) < 1e-9)
check("1개월(21일)",
      abs(sh.period_return(up, 21) - (1.01 ** 21 - 1) * 100) < 1e-9)
check("표본이 모자라면 None", sh.period_return([100.0] * 5, 21) is None)
check("0·음수 가격을 걸러낸다",
      sh.period_return([0.0, -1.0, 100.0, 101.0], 1) is not None)
check("기간 정의가 4개", [k for k, _l, _n in sh.PERIODS]
      == ["d1", "w1", "m1", "m3"])
check("기간마다 색 눈금이 있다",
      all(k in sh.COLOR_SCALE for k, _l, _n in sh.PERIODS))
check("긴 기간일수록 눈금이 넓다",
      sh.COLOR_SCALE["d1"] < sh.COLOR_SCALE["w1"]
      < sh.COLOR_SCALE["m1"] < sh.COLOR_SCALE["m3"],
      "하나로 두면 1일은 늘 연하고 3개월은 늘 진합니다")

print("\n=== 52주 위치 ===")
check("신고가는 100", sh.band_position(up) == 100.0)
down = [200 - i * 0.5 for i in range(300)]
check("신저가는 0", sh.band_position(down) == 0.0)
check("평평하면 None", sh.band_position([100.0] * 300) is None)
check("짧으면 None", sh.band_position([100.0, 101.0]) is None)

print("\n=== 기준선 대비 ===")
specs = [
    ("069500", "KODEX 200", ("200",), True),
    ("A", "강한 업종", ("강",)),
    ("B", "약한 업종", ("약",)),
    ("C", "실패", ("x",)),
]
# 기준선 1개월 정확히 +2%, A 는 +10%, B 는 -5% 가 되게 만듭니다
def ladder(ret_1m):
    base = [100.0] * 280
    step = (1 + ret_1m / 100) ** (1 / 21)
    return base + [100.0 * step ** (i + 1) for i in range(21)]

rows = sh.build(specs, {"069500": ladder(2.0), "A": ladder(10.0),
                        "B": ladder(-5.0)})
by = {r.code: r for r in rows}
check("기준선 1개월 +2%", abs(by["069500"].returns["m1"] - 2.0) < 1e-6,
      f"{by['069500'].returns['m1']:.6f}")
check("상대강도 = 업종 − 기준선", abs(by["A"].rel_1m - 8.0) < 1e-6,
      f"{by['A'].rel_1m:.6f}")
check("음의 상대강도", abs(by["B"].rel_1m - (-7.0)) < 1e-6)
check("기준선에는 상대강도가 없다", by["069500"].rel_1m is None)
check("기준선이 맨 위", rows[0].benchmark)
check("강한 업종이 그다음", rows[1].code == "A")
check("실패한 줄은 맨 아래", rows[-1].code == "C" and not rows[-1].ok)
check("실패 사유를 남긴다", rows[-1].error != "")
hot, cold = sh.hot_and_cold(rows)
check("강세를 고른다", [r.code for r in hot] == ["A"])
check("약세를 고른다", [r.code for r in cold] == ["B"])
check("요약 한 줄에 둘 다", "강한 업종" in sh.summary_line(rows)
      and "약한 업종" in sh.summary_line(rows))
check("요약에 기준을 밝힌다", "KODEX 200 대비" in sh.summary_line(rows))
no_bench = sh.build(specs[1:3], {"A": ladder(10.0), "B": ladder(-5.0)})
check("기준선이 없으면 상대강도를 지어내지 않는다",
      all(r.rel_1m is None for r in no_bench))

print("\n=== 종목코드 검증 (야후 이름 대조) ===")
r_ok = sh.SectorRow(code="091160", label="반도체",
                    keywords=("반도체", "semicon"), yahoo_name="KODEX Semicon")
r_bad = sh.SectorRow(code="091170", label="은행",
                     keywords=("은행", "bank"), yahoo_name="KODEX Insurance")
r_none = sh.SectorRow(code="x", label="모름", keywords=("y",))
check("맞는 이름은 통과", r_ok.name_ok is True)
check("틀린 이름을 잡는다", r_bad.name_ok is False)
check("이름을 못 받으면 판단 보류", r_none.name_ok is None,
      "못 받은 걸 '틀렸다' 고 하면 경고가 소음이 됩니다")
check("대소문자·공백 무시",
      sh.SectorRow(code="a", label="a", keywords=("kosdaq 150",),
                   yahoo_name="KODEX KOSDAQ150").name_ok is True)
check("불일치 목록", sh.mismatched([r_ok, r_bad, r_none]) == [r_bad])

print("\n=== 설정 ===")
etfs = config.KR_SECTOR_ETFS
codes = [e[0] for e in etfs]
check("코드가 6자리 숫자", all(len(c) == 6 and c.isdigit() for c in codes))
check("중복 없음", len(codes) == len(set(codes)))
check("기준선이 정확히 하나",
      sum(1 for e in etfs if len(e) > 3 and e[3]) == 1)
check("모든 줄에 검증 키워드", all(e[2] for e in etfs),
      "키워드가 없으면 틀린 코드를 못 잡습니다")
check("한글·영어 키워드를 같이 적었다",
      sum(1 for e in etfs if any(k.isascii() for k in e[2])) >= len(etfs) - 1,
      "야후는 국내 ETF 이름을 영어로 줄 때가 많습니다")

print("\n=== 화면 ===")
demo_rows = demo_mod.demo_sector_heat(etfs)
html = ui.render_sector_heat(demo_rows)
check("업종마다 한 줄", html.count("<tr") - 1 == len(etfs))
check("스파크라인", html.count("<svg") == len(etfs))
check("기준선 표시", "heat-bench" in html)
check("코드 확인 배지", "✗ 코드 확인" in html)
check("배지에 야후 이름을 넣는다", "TIGER 화장품" in html)
check("표 아래 경고에 고칠 곳", "config.KR_SECTOR_ETFS" in html)
check("등락 변수로 색칠", "var(--dash-up)" in html
      and "var(--dash-down)" in html,
      "색을 여기서 정하면 한국/미국 색 관행 전환과 어긋납니다")
check("방향 기호를 같이 쓴다", "▲" in html and "▼" in html)
check("받은 게 없으면 그렇게 말한다",
      "하나도 받지 못했습니다" in ui.render_sector_heat(
          [sh.SectorRow(code="a", label="a", error="x")]))
chips = ui.render_sector_heat_summary(demo_rows)
check("표 위에 강세·약세 칩", "강세" in chips and "약세" in chips)

xss = sh.SectorRow(code="<b>", label="<script>", keywords=("x",),
                   yahoo_name="<img src=x onerror=1>", error="")
xss.closes = [100.0] * 300
xss.returns = {k: 0.0 for k, _l, _n in sh.PERIODS}
check("야후 이름을 이스케이프한다",
      "<img" not in ui.render_sector_heat([xss])
      and "&lt;script&gt;" in ui.render_sector_heat([xss]))

print("\n=== 요약에 섹터 온도 ===")
k = sm.build(market="kr", sector_rows=demo_rows, holdings_total=2)
u = sm.build(market="us", holdings_total=7)
check("한국 요약 둘째 줄은 섹터 온도", k.rows[1].key == "sector")
check("미국 요약 둘째 줄은 시장 심리", u.rows[1].key == "sentiment"
      or u.rows[1].title == "시장 분위기", u.rows[1].title)
check("코드 불일치를 요약에도 띄운다", "종목코드 확인" in k.rows[1].detail,
      k.rows[1].detail)
check("못 받으면 '데이터 없음'",
      sm.build(market="kr", sector_rows=[]).rows[1].level == "unknown")
check("발굴 안내가 시장마다 다르다",
      k.rows[3].detail != u.rows[3].detail)

_app = pathlib.Path("app.py").read_text(encoding="utf-8")
check("한국 요약은 공포탐욕을 안 받는다",
      'if market == "kr":\n        sector_rows = load_sector_heat(use_demo)'
      in _app, "안 쓰는 걸 받아오면 요약이 느려집니다")

print("\n=== 흐름 — 4칸 판정 (2026-11-13) ===")
check("주도 = 3개월 + · 1주 +", sh.phase_of(5.0, 3.0) == "lead")
check("둔화 = 3개월 + · 1주 −", sh.phase_of(5.0, -3.0) == "fade")
check("회복 = 3개월 − · 1주 +", sh.phase_of(-5.0, 3.0) == "recover")
check("침체 = 3개월 − · 1주 −", sh.phase_of(-5.0, -3.0) == "lag")
check("1주가 ±1%p 안이면 방향 없음", sh.phase_of(5.0, 0.9) == "flat"
      and sh.phase_of(-5.0, -0.9) == "flat")
check("값이 없으면 None", sh.phase_of(None, 3.0) is None)
check("기간이 3개월 · 1주", sh.FLOW_LEVEL == ("m3", 63) and sh.FLOW_DIR == ("w1", 5))


def series(daily_by_day):
    """하루 수익률 목록 → 종가."""
    p, out = 100.0, [100.0]
    for g in daily_by_day:
        p *= 1 + g
        out.append(p)
    return out


# 기준선은 평평. A: 3개월 꾸준히 오르다 마지막 주 빠짐 → 지난주 주도, 이번 주 둔화
# B: 3개월 빠지다 마지막 주 급등 → 지난주 침체, 이번 주 회복
flat = series([0.0] * 120)
a = series([0.004] * 115 + [-0.01] * 5)
b = series([-0.004] * 115 + [0.02] * 5)
specs_f = [("069500", "KODEX 200", ("200",), True),
           ("A", "꺾인 업종", ()), ("B", "돌아선 업종", ()), ("C", "빈 업종", ())]
rows_f = sh.build(specs_f, {"069500": flat, "A": a, "B": b, "C": []},
                  dates_by_code={"069500": "2026-11-13", "A": "2026-11-13",
                                 "B": "2026-11-13"})
fl = {f.label: f for f in sh.flow(rows_f)}
check("기준선은 흐름 줄에 없다", "KODEX 200" not in fl)
fa, fb = fl["꺾인 업종"], fl["돌아선 업종"]
check("A: 이번 주 둔화 · 1주 전 주도", (fa.phase, fa.prev_phase) == ("fade", "lead"),
      f"{fa.phase} / {fa.prev_phase}")
check("B: 이번 주 회복 · 1주 전 침체", (fb.phase, fb.prev_phase) == ("recover", "lag"),
      f"{fb.phase} / {fb.prev_phase}")
check("1주 값 = 업종 1주 − 기준선 1주 (격자로 검산 가능)",
      abs(fb.direction - (sh.period_return(b, 5) - sh.period_return(flat, 5))) < 1e-9)
check("A 는 꺾임, B 는 돌아섬", fa.turned_down and not fa.turned_up
      and fb.turned_up and not fb.turned_down)
check("일봉 없는 줄은 판정 못 함 + 이유", fl["빈 업종"].phase is None
      and fl["빈 업종"].why_none != "")
rows_d = sh.build(specs_f[:2], {"069500": flat, "A": a},
                  dates_by_code={"069500": "2026-11-13", "A": "2026-11-12"})
fd = sh.flow(rows_d)[0]
check("마지막 봉 날짜가 기준선과 다르면 판정 안 함", fd.phase is None
      and "날짜" in fd.why_none, fd.why_none)

rd = sh.flow_read(rows_f)
check("판독: 판정한 업종 2개 · 앞선 업종 1개", rd is not None and rd.n == 2
      and rd.beat == 1, f"{rd and (rd.n, rd.beat)}")
lines = sh.flow_sentences(rd)
check("판독 문장 1~3줄", 1 <= len(lines) <= 3, str(len(lines)))
check("돌아선 쪽에 '침체→회복' 이 적힌다", any("돌아선 업종(침체→회복)" in t for t in lines),
      " / ".join(lines))
check("매수 · 매도 · 전망 말이 없다",
      not any(w in " ".join(lines) for w in ("매수", "매도", "목표", "전망", "추천")))
check("기준선이 없으면 판독 없음",
      sh.flow_read([r for r in rows_f if not r.benchmark]) is None
      and ui.render_sector_flow([r for r in rows_f if not r.benchmark]) == "")
check("빈 목록이어도 깨지지 않음", ui.render_sector_flow([]) == ""
      and sh.flow_sentences(None) == [])
check("기준선 일봉 실패여도 깨지지 않음",
      ui.render_sector_flow(sh.build(specs_f, {"A": a, "B": b})) == "")
html_f = ui.render_sector_flow(rows_f)
check("지도에 네 칸이 모두 있다 (빈 칸은 '없음')",
      all(f"sf-{k}" in html_f for k in ("lead", "recover", "fade", "lag"))
      and "없음" in html_f)
check("1주 전 칸 표시", "← 주도" in html_f and "← 침체" in html_f)
check("출처 · 기준일 표시", "네이버 일봉" in html_f and "11/13 봉 기준" in html_f)
check("판정 못 한 업종을 숨기지 않는다", "판정 못 함" in html_f and "빈 업종" in html_f)

print("\n=== 흐름 — 시소 (큰 업종이 시장을 끌 때) ===")
heavy = series([0.0] * 115 + [0.03] * 5)
bench_h = series([0.0] * 115 + [0.012] * 5)           # 반도체가 끌어올린 시장
others = {f"S{i}": series([0.0] * 115 + [0.004] * 5) for i in range(4)}
specs_h = ([("069500", "KODEX 200", ("200",), True), ("091160", "반도체", ())]
           + [(c, f"업종{c}", ()) for c in others])
rh = sh.flow_read(sh.build(specs_h, {"069500": bench_h, "091160": heavy, **others}))
check("반도체가 크게 앞서고 나머지가 반대면 시소 문장", rh is not None and rh.heavy is not None
      and any("착시" in t for t in sh.flow_sentences(rh)))
check("좁은 움직임으로 판정 (1/5 만 시장을 앞섬)", rh.breadth == "narrow"
      and rh.beat == 1, f"{rh.breadth} {rh.beat}")
check("조사: '반도체가'", any(t.startswith("반도체가 ") for t in sh.flow_sentences(rh)))
same = {f"S{i}": series([0.0] * 115 + [0.02] * 5) for i in range(4)}
rn = sh.flow_read(sh.build(specs_h, {"069500": bench_h, "091160": heavy, **same}))
check("다른 업종도 같이 앞서면 시소 아님", rn.heavy is None and rn.breadth == "broad")

print("\n=== 흐름 — 업종 평균(동일가중) 기준선 (2026-11-13) ===")
# 업종 두 개가 매일 +1% · −1% 면 동일가중 평균은 매일 0% → 평평
u = series([0.01] * 120)
d = series([-0.01] * 120)
k = series([0.0] * 120)
spec_ew = ([("069500", "KODEX 200", ("200",), True), ("229200", "코스닥150", ())]
           + [(f"U{i}", f"상승{i}", ()) for i in range(3)]
           + [(f"D{i}", f"하락{i}", ()) for i in range(3)])
data_ew = {"069500": k, "229200": series([0.05] * 120),
           **{f"U{i}": u for i in range(3)}, **{f"D{i}": d for i in range(3)}}
rows_ew = sh.build(spec_ew, data_ew)
ew_b = sh.equal_weight_bench(rows_ew)
check("업종 평균 = 매일 같은 비중 평균 (±1% 짝 → 0%)", ew_b is not None
      and abs(ew_b.returns["w1"]) < 1e-9 and abs(ew_b.returns["m3"]) < 1e-9,
      str(ew_b and ew_b.returns))
check("코스닥150 은 평균에서 뺀다", ew_b is not None and "코스닥150" not in ew_b.members
      and len(ew_b.members) == 6, str(ew_b and ew_b.members))
check("업종이 모자라면 None",
      sh.equal_weight_bench(sh.build(spec_ew[:4], data_ew)) is None)
rows_late = sh.build(spec_ew, data_ew, dates_by_code={
    "069500": "2026-11-13", **{f"U{i}": "2026-11-13" for i in range(3)},
    "D0": "2026-11-12", "D1": "2026-11-13", "D2": "2026-11-13"})
ew_late = sh.equal_weight_bench(rows_late)
check("마지막 봉 날짜가 다른 업종은 평균에 안 넣는다",
      ew_late is not None and "하락0" not in ew_late.members)
fl_ew = sh.flow(rows_ew, ew_b)
check("업종 평균 기준 흐름: 상승 업종 = 주도, 하락 업종 = 침체",
      {f.phase for f in fl_ew if f.label.startswith("상승")} == {"lead"}
      and {f.phase for f in fl_ew if f.label.startswith("하락")} == {"lag"})
rd_ew = sh.flow_read(rows_ew, fl_ew, ew_b)
check("업종 평균 기준 문장은 '업종 평균보다' 라고 쓴다",
      rd_ew is not None and "업종 평균보다 더 오른" in sh.flow_sentences(rd_ew)[0],
      sh.flow_sentences(rd_ew)[0] if rd_ew else "")
# 시소 데이터(위)를 업종 평균 기준으로 — 시소 문장이 나오면 안 됨
rows_h = sh.build(specs_h, {"069500": bench_h, "091160": heavy, **others})
rh_ew = sh.flow_read(rows_h, bench=sh.equal_weight_bench(rows_h))
check("업종 평균 기준에서는 시소 문장을 안 쓴다 (KODEX 200 비중 얘기라 틀린 말)",
      rh_ew is None or rh_ew.heavy is None)
check("KODEX 200 기준 시소 문장은 업종 평균으로 바꿔 보라고 안내",
      any("업종 평균' 으로 바꾸면" in t for t in sh.flow_sentences(rh)))
html_ew = ui.render_sector_flow(rows_ew, "ew")
check("화면: 업종 평균 기준 표시 + 구성 설명", "기준 업종 평균" in html_ew
      and "6개를 같은 비중" in html_ew and "업종 평균보다 강하고" in html_ew)
html_fb = ui.render_sector_flow(sh.build(spec_ew[:4], data_ew), "ew")
check("업종 평균을 못 만들면 KODEX 200 으로 돌아가고 그렇다고 적는다",
      "KODEX 200 기준으로 보여 줍니다" in html_fb and "기준 KODEX 200" in html_fb)
check("기본은 KODEX 200", "기준 KODEX 200" in ui.render_sector_flow(rows_ew))

check("-0.0 이 안 나온다", sh.pp(-0.04) == "0.0" and sh.pp(0.04) == "0.0"
      and sh.pp(-0.06) == "-0.1" and sh.pp(1.0) == "+1.0")

print("\n=== 요약 탭 한 줄 — 흐름 기준 (2026-11-13) ===")
rs = sm.row_sector(rows_f)
check("요약 한 줄이 흐름 기준", "1주" in rs.detail and "3개월" in rs.detail
      and ("주도" in rs.headline or "회복" in rs.headline), f"{rs.headline} / {rs.detail}")
check("새로 들어온 업종에 (새로)", "돌아선 업종(새로)" in rs.headline, rs.headline)
check("꺾임 개수", "꺾임 1개" in rs.headline, rs.headline)
rs_nb = sm.row_sector([r for r in rows_f if not r.benchmark])
check("기준선이 없으면 1개월 한 줄로 돌아간다",
      "1개월" in rs_nb.detail or rs_nb.level == "unknown", f"{rs_nb.headline} / {rs_nb.detail}")
check("업종을 하나도 못 받으면 unknown", sm.row_sector([]).level == "unknown")
check("탭에 기준 고르기(KODEX 200 / 업종 평균)",
      'key="sector_flow_base"' in _app and "ui.render_sector_flow(rows, base)" in _app)

print("\n=== 흐름 — 데모 · 화면 연결 ===")
_demo = demo_mod.demo_sector_heat(config.KR_SECTOR_ETFS)
check("데모로 흐름 지도가 그려진다", "dash-sflow" in ui.render_sector_flow(_demo)
      and "dash-sflow" in ui.render_sector_flow(_demo, "ew"))
check("탭이 흐름을 칩 · 막대보다 먼저 그린다",
      _app.index("ui.render_sector_flow(rows, base)")
      < _app.index("ui.render_sector_heat_summary(rows)")
      < _app.index("ui.render_sector_bars(rows)"))
check("기존 칩 · 막대 · 격자 · 표가 그대로 있다",
      all(x in _app for x in ("ui.render_sector_heat_summary(rows)",
                               "ui.render_sector_bars(rows)",
                               "ui.render_sector_heatgrid(rows)",
                               "ui.render_sector_heat(rows)")))
_css = theme.build_rules()
check("흐름 CSS 가 있다", ".dash-sflow" in _css and "sf-map" in _css)
check("예전 막대 CSS 가 새 막대를 덮지 않는다 (범위를 좁힘)",
      ".dash-sbars .sb-row" in _css and "\n  .sb-row { display: grid; grid-template-columns: 92px"
      not in _css)

print("\n=== 스트림릿 테마가 theme.py 와 같은가 ===")
# 주석을 '#' 로 잘라내면 '#1f3a5f' 같은 색값까지 잘립니다 — 진짜 TOML
# 파서로 읽습니다.
import tomllib  # noqa: E402

with open(".streamlit/config.toml", "rb") as _fh:
    _theme_cfg = tomllib.load(_fh).get("theme", {})


def _val(key: str) -> str:
    return str(_theme_cfg.get(key, "")).lower()


pal = theme.PALETTE["light"]
check("base 가 light", _val("base") == "light",
      f"'{_val('base')}' — dark 면 위젯 글자가 흰 패널 위에서 안 보입니다")
check("primaryColor = 강조색", _val("primaryColor") == pal["accent"].lower(),
      f"{_val('primaryColor')} vs {pal['accent']}")
check("backgroundColor = 바탕", _val("backgroundColor") == pal["page"].lower())
check("secondaryBackgroundColor = 카드",
      _val("secondaryBackgroundColor") == pal["surface"].lower())
check("textColor = 본문 글자", _val("textColor") == pal["ink"].lower())

import buildstamp  # noqa: E402

_man = buildstamp.build_manifest(".")
check("config.toml 이 버전 검사 대상", ".streamlit/config.toml" in _man,
      ".py 만 보면 이 파일이 낡아도 검사를 통과합니다")
check("secrets.toml 은 대상이 아니다",
      not any("secrets" in k for k in _man))

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
