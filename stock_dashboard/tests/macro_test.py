"""
매크로 지표 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/macro_test.py

검증 범위: FRED CSV 파싱(결측 `.`, 헤더명 변형, 위치 기반 읽기),
           전년대비 계산과 기준연도 무관성, 최신값 제외 평균,
           0 을 통과하는 부호 전환, 임계값 6종, 뉴스 대상 선별, 표시 라벨.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import macro  # noqa: E402
from config import MacroSeries  # noqa: E402
from sources import fred  # noqa: E402
from sources.fred import FredError, Observation, Series, parse_csv  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def near(a, b, tol=0.05) -> bool:
    return a is not None and b is not None and abs(a - b) < tol


def series_of(series_id: str, pairs: list[tuple[str, float]]) -> Series:
    return Series(series_id=series_id, observations=[
        Observation(date=dt.date.fromisoformat(d), value=v) for d, v in pairs
    ])


def monthly(series_id: str, start: str, values: list[float]) -> Series:
    y, m = int(start[:4]), int(start[5:7])
    obs = []
    for v in values:
        obs.append(Observation(date=dt.date(y, m, 1), value=v))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return Series(series_id=series_id, observations=obs)


def spec(**kw) -> MacroSeries:
    base = dict(key="t", name="테스트지표", series_id="TEST", group="rates")
    base.update(kw)
    return MacroSeries(**base)


# ──────────────────────────────────────────────────────────────────────────────
print("=== FRED CSV 파싱 ===")
# 결측은 빈 칸이 아니라 점 한 글자로 옵니다
csv_text = (
    "observation_date,DGS10\n"
    "2026-10-01,4.12\n"
    "2026-10-02,.\n"
    "2026-10-03,4.15\n"
    "2026-10-04,\n"
    "2026-10-05,4.18\n"
)
s = parse_csv(csv_text, "DGS10")
check("점(.) 결측 제외", len(s.observations) == 3, f"{len(s.observations)}건")
check("결측 건수 집계", s.missing_count == 2, str(s.missing_count))
check("최신값", near(s.latest.value, 4.18))
check("오름차순 정렬",
      [o.date.isoformat() for o in s.observations]
      == ["2026-10-01", "2026-10-03", "2026-10-05"])

# 헤더의 두 번째 컬럼명이 계열 ID 와 다를 수 있습니다 — 이름이 아니라 위치로 읽습니다
odd_header = parse_csv(
    "DATE,DGS10_20260101_20261101\n2026-10-01,4.12\n2026-10-02,4.15\n", "DGS10")
check("헤더명이 달라도 파싱", len(odd_header.observations) == 2,
      f"{len(odd_header.observations)}건")

# 전부 결측이면 조용히 빈 계열을 돌려주면 안 됩니다 — 명시적으로 실패해야 합니다
raised = False
try:
    parse_csv("observation_date,X\n2026-10-01,.\n2026-10-02,.\n", "X")
except FredError as exc:
    raised, msg = True, str(exc)
check("전부 결측이면 FredError", raised)
check("실패 메시지에 결측 수", raised and "2건" in msg, msg if raised else "")

raised = False
try:
    parse_csv("<html><body>Not Found</body></html>", "BAD")
except FredError as exc:
    raised, msg = True, str(exc)
check("HTML 응답이면 FredError", raised, msg[:50] if raised else "")

raised = False
try:
    parse_csv("", "EMPTY")
except FredError:
    raised = True
check("빈 응답이면 FredError", raised)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 전년대비 — 기준연도와 무관해야 합니다 ===")
# 지수 계열은 기준연도가 바뀌어도(2017=100 → 2022=100) 변화율은 같아야 합니다
base_2017 = monthly("IDX", "2025-01", [100.0 + i for i in range(14)])
base_2022 = monthly("IDX", "2025-01", [(100.0 + i) * 1.732 for i in range(14)])
check("같은 모양이면 전년대비 동일",
      near(base_2017.yoy_pct(), base_2022.yoy_pct(), 0.001),
      f"{base_2017.yoy_pct():.4f}% vs {base_2022.yoy_pct():.4f}%")
# 2026-02 (113) vs 2025-02 (101) = +11.88%
check("전년대비 값", near(base_2017.yoy_pct(), 11.881, 0.01),
      f"{base_2017.yoy_pct():.3f}%")

short = monthly("IDX", "2026-01", [100.0, 101.0, 102.0])
check("1년치가 없으면 None", short.yoy_pct() is None)

# 전년 동월이 정확히 없으면 **그 이전**의 가장 최신 관측치를 씁니다.
# 전년 동월보다 뒤인 관측치를 기준으로 쓰면 11개월 비교를 전년대비라고
# 부르는 셈이라, 그런 경우는 거부해야 맞습니다.
only_later = series_of("G", [("2025-03-01", 100.0), ("2026-02-01", 110.0)])
check("전년 동월 이후 관측치만 있으면 거부", only_later.yoy_pct() is None,
      str(only_later.yoy_pct()))

gappy = series_of("G", [("2025-01-01", 100.0), ("2025-03-01", 105.0),
                        ("2026-02-01", 110.0)])
check("전년 동월 없으면 그 이전 관측치로", near(gappy.yoy_pct(), 10.0),
      f"{gappy.yoy_pct()}")

check("전년대비 시계열 길이", len(base_2017.yoy_series(24)) == 2,
      str(len(base_2017.yoy_series(24))))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 최신값 제외 평균 ===")
# '4주 평균 대비 급증' 에서 최신값이 자기 기준선에 들어가면 급증이 희석됩니다
spike = series_of("ICSA", [
    ("2026-10-01", 240_000.0), ("2026-10-08", 244_000.0),
    ("2026-10-15", 248_000.0), ("2026-10-22", 252_000.0),
    ("2026-10-29", 310_000.0),
])
check("mean 은 최신값 포함", near(spike.mean(4), 263_500.0, 1),
      f"{spike.mean(4):,.0f}")
check("mean_prior 는 최신값 제외", near(spike.mean_prior(4), 246_000.0, 1),
      f"{spike.mean_prior(4):,.0f}")
incl = (310_000 / spike.mean(4) - 1) * 100
excl = (310_000 / spike.mean_prior(4) - 1) * 100
check("제외 쪽이 변화를 더 크게 잡음", excl > incl + 7,
      f"포함 {incl:+.1f}% vs 제외 {excl:+.1f}%")
check("관측치 부족하면 None", spike.mean_prior(10) is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 변화·지연 ===")
rates = series_of("DGS10", [(f"2026-10-{d:02d}", 3.60 + d * 0.03)
                            for d in range(1, 21)])
check("직전 대비 변화", near(rates.change(1), 0.03, 0.001))
check("19개 관측 전 대비", near(rates.change(19), 0.57, 0.001),
      f"{rates.change(19):.3f}")
check("구간 부족하면 None", rates.change(50) is None)
check("변화율", near(rates.pct_change(1), 0.03 / 4.17 * 100, 0.01))

lagged = series_of("X", [((dt.date.today() - dt.timedelta(days=40)).isoformat(), 1.0)])
check("지연일수", lagged.lag_days == 40, str(lagged.lag_days))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 부호 전환 — 0.00 을 통과해도 잡아야 합니다 ===")
# T10Y2Y 는 소수 둘째 자리까지라 0.00 이 자주 나옵니다. 직전 관측치만 보면
# 0.00 을 만나는 순간 비교가 무효가 되어 역전 해소를 통째로 놓칩니다.
through_zero = macro.build_reading(
    spec(key="curve", name="스프레드", sign_flip=True, decimals=2),
    series_of("T10Y2Y", [("2026-10-01", -0.05), ("2026-10-02", -0.02),
                         ("2026-10-03", 0.00), ("2026-10-04", 0.01)]))
trigs = macro.evaluate(through_zero)
check("0.00 을 지나는 전환도 감지", any(t.rule == "sign_flip" for t in trigs),
      f"{[t.rule for t in trigs]}")
flip = [t for t in trigs if t.rule == "sign_flip"][0]
check("역전 해소로 표현", "역전 해소" in flip.title, flip.title)
check("심각도 3 (지금)", flip.severity == 3, str(flip.severity))
check("직전 비영 값을 보여줌", "-0.02" in flip.detail, flip.detail)

# 현재가 정확히 0 이면 부호가 없으므로 판정하지 않습니다
at_zero = macro.build_reading(
    spec(sign_flip=True),
    series_of("Z", [("2026-10-01", -0.05), ("2026-10-02", 0.00)]))
check("현재 0 이면 전환 아님",
      not any(t.rule == "sign_flip" for t in macro.evaluate(at_zero)))

# 같은 부호를 유지하면 신호가 없어야 합니다
same = macro.build_reading(
    spec(sign_flip=True),
    series_of("S", [("2026-10-01", 0.05), ("2026-10-02", 0.00),
                    ("2026-10-03", 0.08)]))
check("같은 부호 유지면 전환 아님",
      not any(t.rule == "sign_flip" for t in macro.evaluate(same)))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 전년대비 부호 전환 (사이클 전환) ===")
# 감소세에서 증가세로 — 반도체 생산 사이클의 전환 신호
recover = monthly("IPG3344S", "2025-01", [
    180.0, 178.0, 176.0, 174.0, 172.0, 170.0, 168.0, 166.0, 165.0,
    164.0, 164.0, 165.0,
    # 2026년 — 2026-01 은 전년 대비 -4.4%(172 vs 180),
    #          2026-02 는 +3.9%(185 vs 178) → 여기서 부호가 바뀝니다
    172.0, 185.0,
])
r = macro.build_reading(
    spec(key="semi_ip", name="반도체 생산", group="semi", mode="yoy",
         yoy_flip=True, decimals=1),
    recover)
trigs = macro.evaluate(r)
check("전년대비 전환 감지", any(t.rule == "yoy_flip" for t in trigs),
      f"표시값 {r.value_label}, 규칙 {[t.rule for t in trigs]}")
if any(t.rule == "yoy_flip" for t in trigs):
    t = [x for x in trigs if x.rule == "yoy_flip"][0]
    check("증가세 회복으로 표현", "증가세 회복" in t.title, t.title)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 임계값 6종 ===")
above = macro.build_reading(
    spec(name="코어 PCE", mode="yoy", level_above=2.5, decimals=1),
    monthly("PCE", "2025-01", [100.0] * 12 + [103.8]))
check("level_above", any(t.rule == "level_above" for t in macro.evaluate(above)),
      above.value_label)

below = macro.build_reading(
    spec(name="고용", mode="diff", level_below=0.0, decimals=0),
    series_of("PAYEMS", [("2026-09-01", 160_000.0), ("2026-10-01", 159_980.0)]))
check("level_below", any(t.rule == "level_below" for t in macro.evaluate(below)),
      below.value_label)

changed = macro.build_reading(
    spec(name="10년물", change_abs=0.50, change_periods=19, decimals=2, unit="%"),
    rates)
ct = [t for t in macro.evaluate(changed) if t.rule == "change"]
check("change_abs", bool(ct), changed.value_label)
check("변화 단위가 %p", bool(ct) and "%p" in ct[0].title, ct[0].title if ct else "")

vs_mean = macro.build_reading(
    spec(name="청구건수", pct_vs_mean=15.0, mean_periods=4, decimals=0, unit="건"),
    spike)
vt = [t for t in macro.evaluate(vs_mean) if t.rule == "vs_mean"]
check("pct_vs_mean", bool(vt), vt[0].title if vt else "")
check("기준선이 최신값 제외 평균",
      bool(vt) and "246,000" in vt[0].detail, vt[0].detail if vt else "")

quiet = macro.build_reading(spec(name="조용", level_above=99.0), rates)
check("임계값 미달이면 신호 없음", macro.evaluate(quiet) == [])

no_rule = macro.build_reading(spec(name="표시만"), rates)
check("임계값이 없으면 표시만", macro.evaluate(no_rule) == [])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 실패 처리 ===")
err = macro.build_reading(spec(), None, "404 없는 계열")
check("수집 실패는 error 로", not err.ok and "404" in err.error)
check("실패는 신호를 내지 않음", macro.evaluate(err) == [])
check("실패 표시값은 대시", err.value_label == "—")

no_yoy = macro.build_reading(spec(mode="yoy"), short)
check("전년대비 불가도 error",
      not no_yoy.ok and "전년 동기" in no_yoy.error, no_yoy.error)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 표시 라벨 ===")
lvl = macro.build_reading(spec(unit="%", decimals=2, period_days=1), rates)
check("레벨 라벨", lvl.value_label == "4.20%", lvl.value_label)
check("변화 라벨에 부호", lvl.delta_label.startswith("+"), lvl.delta_label)

yoy = macro.build_reading(spec(mode="yoy", decimals=1), base_2017)
check("전년대비 라벨에 부호와 %", yoy.value_label == "+11.9%", yoy.value_label)

dif = macro.build_reading(spec(mode="diff", unit="천명", decimals=0),
                          series_of("P", [("2026-09-01", 100.0),
                                          ("2026-10-01", 85.0)]))
check("증감 라벨", dif.value_label == "-15천명", dif.value_label)

monthly_r = macro.build_reading(spec(period_days=30, mode="level"),
                                monthly("M", "2026-01", [1.0, 2.0]))
check("월간은 연-월 표기", monthly_r.observed_label == "2026-02",
      monthly_r.observed_label)
check("일간은 전체 날짜", lvl.observed_label == "2026-10-20", lvl.observed_label)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 발표 지연 ===")
late = macro.build_reading(
    spec(period_days=7),
    series_of("ICSA", [((dt.date.today() - dt.timedelta(days=30)).isoformat(),
                        1.0)]))
check("통상 주기의 2.5배 초과면 지연", late.stale, f"{late.lag_days}일")
fresh = macro.build_reading(
    spec(period_days=30),
    series_of("CPI", [((dt.date.today() - dt.timedelta(days=30)).isoformat(),
                       1.0)]))
check("주기 내면 지연 아님", not fresh.stale, f"{fresh.lag_days}일")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 뉴스 대상 선별 — 범람 방지 ===")
readings = [
    macro.build_reading(
        spec(key=f"k{i}", name=f"지표{i}", level_above=0.0,
             news_query=f"질의{i}"),
        series_of("X", [("2026-10-01", 1.0), ("2026-10-02", 5.0)]))
    for i in range(6)
]
trigs = macro.evaluate_all(readings)
check("6개 지표 전부 신호", len(trigs) == 6, f"{len(trigs)}건")
targets = macro.news_queries(trigs, limit=3)
check("뉴스는 상한까지만", len(targets) == 3, f"{len(targets)}개")
check("질의 문자열을 넘김", targets[0][1] == "질의0", str(targets[0]))

no_query = macro.build_reading(
    spec(key="nq", level_above=0.0, news_query=""),
    series_of("X", [("2026-10-01", 1.0), ("2026-10-02", 5.0)]))
check("질의가 없으면 뉴스 제외",
      macro.news_queries(macro.evaluate(no_query)) == [])

check("신호가 없으면 뉴스도 없음", macro.news_queries([]) == [])

# 심각도 높은 순으로 정렬돼야 합니다 — 역전 해소(3)가 금리 급변(2)보다 위
mixed = macro.evaluate_all([through_zero, changed])
check("심각도 내림차순", [t.severity for t in mixed] == sorted(
    [t.severity for t in mixed], reverse=True), str([t.severity for t in mixed]))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 프롬프트 ===")
p = macro.prompt_for(flip)
check("계열 ID 포함", "T10Y2Y" in p or flip.reading.spec.series_id in p)
check("관측 시점·지연 포함", "일 전 데이터" in p)
check("추천 금지 문구 포함", "매수/매도 추천" in p)

semi_trig = [t for t in macro.evaluate(r) if t.rule == "yoy_flip"]
if semi_trig:
    sp = macro.prompt_for(semi_trig[0])
    check("반도체는 지표체계 교차검증을 요구", "레이어" in sp)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 설정 정합성 ===")
specs = config.macro_series()
check("계열 목록 비어 있지 않음", len(specs) > 0, f"{len(specs)}개")
check("key 중복 없음", len({s.key for s in specs}) == len(specs))
check("series_id 중복 없음", len({s.series_id for s in specs}) == len(specs))
check("mode 는 세 가지뿐",
      all(s.mode in ("level", "yoy", "diff") for s in specs),
      str({s.mode for s in specs}))
groups = {g[0] for g in config.MACRO_GROUPS}
check("모든 계열이 정의된 그룹에 속함",
      all(s.group in groups for s in specs),
      str({s.group for s in specs} - groups))
check("모든 계열에 why 가 있음", all(s.why for s in specs),
      str([s.key for s in specs if not s.why]))
check("지수 계열은 전년대비로 표시",
      all(s.mode == "yoy" for s in specs if s.group == "semi"),
      str([(s.key, s.mode) for s in specs if s.group == "semi"]))
check("macro_series_ids 길이 일치",
      len(config.macro_series_ids()) == len(specs))
check("그룹 필터 동작",
      len(config.macro_series("semi")) == 2,
      str(len(config.macro_series("semi"))))
check("key 로 조회", config.macro_series_by_key("ust10") is not None)
check("없는 key 는 None", config.macro_series_by_key("없음") is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 렌더링 ===")
import components as ui  # noqa: E402

html_out = ui.render_macro_card(lvl, hit=True)
check("카드에 값", "4.20%" in html_out)
check("임계값 도달 표시", 'class="dash-macro hit"' in html_out)
check("계열 ID 표시", "TEST" in html_out)

err_html = ui.render_macro_card(err)
check("실패 카드도 렌더링", "dash-macro-err" in err_html and "404" in err_html)

spark = ui.render_macro_spark(yoy.history)
check("포인트 부족하면 빈 문자열", ui.render_macro_spark([("a", 1.0)]) == "")
spark2 = ui.render_macro_spark([("d", -2.0), ("d", -1.0), ("d", 0.5),
                                ("d", 1.5)])
check("0 선을 그림", "stroke-dasharray" in spark2)
check("SVG 좌표 생성", "polyline" in spark2 and "points=" in spark2)

trig_html = ui.render_macro_trigger(flip, macro.prompt_for(flip))
check("신호 카드 렌더링", "dash-signal" in trig_html and "역전 해소" in trig_html)
check("프롬프트 접힘", "<details>" in trig_html)

xss = macro.build_reading(
    spec(name='<img src=x onerror="alert(1)">', unit="%"), rates)
xh = ui.render_macro_card(xss)
check("HTML 이스케이프", "&lt;img" in xh and "<img src=x" not in xh)

grp = ui.render_macro_group("금리", "설명", [lvl], {"t"})
check("그룹 렌더링", "dash-macro-grid" in grp and "금리" in grp)
check("빈 그룹은 빈 문자열", ui.render_macro_group("x", "y", [], set()) == "")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 데모 데이터 ===")
import demo  # noqa: E402

dseries, derrors = demo.demo_macro_series()
check("모든 계열에 데모 데이터",
      all(s.series_id in dseries for s in specs),
      str([s.series_id for s in specs if s.series_id not in dseries]))
dreadings = macro.build_readings(specs, dseries, derrors)
check("데모에서 전부 산출됨", all(r.ok for r in dreadings),
      str([(r.spec.key, r.error[:30]) for r in dreadings if not r.ok]))
dtrigs = macro.evaluate_all(dreadings)
check("데모에서 신호가 남", len(dtrigs) >= 3, f"{len(dtrigs)}건")
check("데모에 심각도 3 신호 포함", any(t.severity == 3 for t in dtrigs),
      str([t.severity for t in dtrigs]))
check("데모 뉴스 대상 상한 준수",
      len(macro.news_queries(dtrigs, limit=config.MACRO_MAX_NEWS_TARGETS))
      <= config.MACRO_MAX_NEWS_TARGETS)




# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 공포탐욕지수 파싱 ===")
import re as _re  # noqa: E402

from sources import feargreed as fgm  # noqa: E402

_payload = {
    "fear_and_greed": {
        "score": 63.4, "rating": "greed",
        "timestamp": 1_793_000_000_000,
        "previous_close": 61.0, "previous_1_week": 55.0,
        "previous_1_month": 48.0, "previous_1_year": 39.0,
    },
    "market_momentum_sp500": {"score": 78.0, "rating": "extreme greed"},
    "safe_haven_demand": {"score": 22.0, "rating": "extreme fear"},
    "put_call_options": {"score": 46.0, "rating": "neutral"},
    "fear_and_greed_historical": {"data": [
        {"x": 1_792_000_000_000, "y": 50.0},
        {"x": 1_792_500_000_000, "y": 58.0},
        {"x": 1_793_000_000_000, "y": 63.4},
    ]},
}
_fg = fgm.parse(_payload)
check("점수 파싱", near(_fg.score, 63.4, 0.01), str(_fg.score))
check("관측일 파싱 (밀리초 타임스탬프)", _fg.observed_at is not None,
      str(_fg.observed_at))
check("세부 지표 3개", len(_fg.components) == 3, str(len(_fg.components)))
check("이력 파싱", len(_fg.history) == 3, str(len(_fg.history)))
check("1주 대비", near(_fg.change_1w, 8.4, 0.01), str(_fg.change_1w))
check("1개월 대비", near(_fg.change_1m, 15.4, 0.01), str(_fg.change_1m))

# 응답에 없는 세부 지표는 빼야 합니다 — 0 으로 채우면 '극단적 공포' 로 오독됩니다
check("없는 세부 지표는 제외",
      {c.key for c in _fg.components}
      == {"market_momentum_sp500", "safe_haven_demand", "put_call_options"},
      str([c.key for c in _fg.components]))

print("\n=== 구간 판정 ===")
for _score, _want in ((0.0, "극단적 공포"), (24.9, "극단적 공포"),
                      (25.0, "공포"), (44.9, "공포"),
                      (45.0, "중립"), (54.9, "중립"),
                      (55.0, "탐욕"), (74.9, "탐욕"),
                      (75.0, "극단적 탐욕"), (100.0, "극단적 탐욕")):
    check(f"{_score:g} → {_want}", fgm.band_label(_score) == _want,
          fgm.band_label(_score))
check("None 은 대시", fgm.band_label(None) == "—")

print("\n=== 극단 지표 추출 ===")
# 지수 한 숫자만 보면 왜 그런지 알 수 없으므로 극단에 있는 세부 지표를 뽑습니다
_ext = {c.key for c in _fg.extremes}
check("극단 지표만", _ext == {"market_momentum_sp500", "safe_haven_demand"},
      str(_ext))
check("중립은 제외", "put_call_options" not in _ext)

print("\n=== 실패 처리 ===")
_raised = False
try:
    fgm.parse({"nope": 1})
except fgm.FearGreedError as exc:
    _raised, _msg = True, str(exc)
check("구조가 바뀌면 FearGreedError", _raised)
check("내부 엔드포인트임을 알림",
      _raised and "내부 엔드포인트" in _msg, _msg[:50] if _raised else "")

_raised = False
try:
    fgm.parse({"fear_and_greed": {"rating": "greed"}})
except fgm.FearGreedError as exc:
    _raised = True
check("score 가 없으면 실패", _raised)

_bad = fgm.FearGreed(error="막혔습니다")
check("실패 객체는 ok=False", not _bad.ok)
check("실패 시 점수 라벨은 대시", _bad.score_label == "—")
check("실패 시 구간도 대시", _bad.band == "—")

print("\n=== 공포탐욕 렌더링 ===")
_fg_demo = demo.demo_feargreed()
_html = ui.render_feargreed(_fg_demo)
check("점수 표시", "dash-fg-score" in _html and "63" in _html)
check("게이지", "dash-fg-gauge" in _html)
# 컨테이너 class="dash-fg-comps" 가 같은 접두사라 정확히 세어야 합니다
_comp_cells = len(_re.findall(r'class="dash-fg-comp(?: extreme)?"', _html))
check("세부 지표 7개", _comp_cells == 7, str(_comp_cells))
check("컨테이너는 하나", _html.count('class="dash-fg-comps"') == 1)
check("극단 지표 강조", 'class="dash-fg-comp extreme"' in _html)
check("세부 지표 설명 포함", "125일 이동평균" in _html)
check("하드코딩 색 없음 (나이트 모드)",
      not _re.findall(r"#[0-9a-fA-F]{6}", _html),
      str(_re.findall(r"#[0-9a-fA-F]{6}", _html)))
check("실패도 렌더링", "막혔습니다" in ui.render_feargreed(_bad))
check("점수 없으면 게이지 없음", ui.render_feargreed_gauge(_bad) == "")
check("게이지에 구간 경계", "25" in ui.render_feargreed_gauge(_fg_demo))

_xss = fgm.FearGreed(error='<img src=x onerror="y">')
check("실패 메시지 이스케이프", "&lt;img" in ui.render_feargreed(_xss))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== VIX 백분위 ===")
from sources import vix as vxm  # noqa: E402
from sources.model import Quote  # noqa: E402

_hist = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 25.0, 30.0, 35.0, 40.0]
check("중간값의 백분위", near(vxm.percentile_of(18.0, _hist), 50.0, 0.1),
      str(vxm.percentile_of(18.0, _hist)))
check("최저값", near(vxm.percentile_of(10.0, _hist), 10.0, 0.1))
check("최고값", near(vxm.percentile_of(40.0, _hist), 100.0, 0.1))
check("범위 밖(위)", near(vxm.percentile_of(99.0, _hist), 100.0, 0.1))
check("범위 밖(아래)", near(vxm.percentile_of(1.0, _hist), 0.0, 0.1))
check("이력 없으면 None", vxm.percentile_of(18.0, []) is None)


def _vix_quotes(**levels):
    from sources.model import MarketStatus

    return {sym: Quote(symbol=sym, price=val, prev_close=val,
                       currency="USD", status=MarketStatus.REGULAR)
            for sym, val in levels.items()}


print("\n=== 기간구조 판정 ===")
# 강한 콘탱고: VIX÷VIX3M < 0.90
_calm = vxm.build_state(_vix_quotes(**{"^VIX": 14.0, "^VIX3M": 18.0}))
check("강한 콘탱고", _calm.structure == "강한 콘탱고", _calm.structure)
check("IVTS", near(_calm.ivts, 14.0 / 18.0, 1e-6), f"{_calm.ivts:.4f}")
check("역전 아님", not _calm.is_inverted)

# 평평한 콘탱고: 0.90 ~ 1.00
_flat = vxm.build_state(_vix_quotes(**{"^VIX": 17.5, "^VIX3M": 18.0}))
check("콘탱고(평평)", _flat.structure == "콘탱고", _flat.structure)
check("평평하면 역전 주시 문구", "주시" in _flat.structure_detail,
      _flat.structure_detail[:40])

# 백워데이션: >= 1.00
_stress = vxm.build_state(_vix_quotes(**{"^VIX": 28.0, "^VIX3M": 24.0}))
check("백워데이션", _stress.is_inverted, _stress.structure)
check("드물다는 기준값 포함", "7.7" in _stress.structure_detail,
      _stress.structure_detail[-40:])

# 정확히 1.0 은 역전으로 봅니다 (경계 포함)
_edge = vxm.build_state(_vix_quotes(**{"^VIX": 18.0, "^VIX3M": 18.0}))
check("비율 1.0 은 역전", _edge.is_inverted, f"{_edge.ivts}")

print("\n=== 초단기 역전 (이벤트) ===")
_front = vxm.build_state(_vix_quotes(**{"^VIX9D": 20.0, "^VIX": 18.0,
                                        "^VIX3M": 19.0}))
check("VIX9D÷VIX", near(_front.front_ratio, 20.0 / 18.0, 1e-6))
_lines = vxm.reading_lines(_front)
check("이벤트 문구", any("FOMC" in ln for ln in _lines),
      str(_lines)[:60])
check("구조적 스트레스와 구분하라고 적음",
      any("구조적 스트레스" in ln for ln in _lines))

_noevent = vxm.reading_lines(_calm)
check("초단기 역전 없으면 그 문구 없음",
      not any("FOMC" in ln for ln in _noevent))

print("\n=== 누락 처리 ===")
_only_spot = vxm.build_state(_vix_quotes(**{"^VIX": 18.0}))
check("VIX 만 있어도 동작", _only_spot.ok)
check("VIX3M 없으면 기간구조 판정 불가",
      _only_spot.structure == "판정 불가", _only_spot.structure)
check("IVTS 는 None", _only_spot.ivts is None)
check("누락을 경고", any("VIX3M" in w for w in _only_spot.warnings),
      str(_only_spot.warnings)[:70])

_empty = vxm.build_state({})
check("VIX 없으면 error", not _empty.ok and "VIX 시세" in _empty.error)
check("error 면 판단 재료도 그것만",
      vxm.reading_lines(_empty) == [_empty.error])

# 백분위 없이도 현재값은 말해야 하고, 모른다는 것도 말해야 합니다
_nofred = vxm.reading_lines(_calm)
check("FRED 없으면 위치 못 낸다고 적음",
      any("위치를 낼 수 없습니다" in ln for ln in _nofred),
      str(_nofred)[:60])
check("FRED 없으면 경고", any("VIXCLS" in w for w in _calm.warnings))

print("\n=== 표본이 짧으면 경고 ===")
import datetime as _dt3  # noqa: E402

from sources.fred import Observation as _Obs, Series as _Ser  # noqa: E402

_short = _Ser(series_id="VIXCLS", observations=[
    _Obs(date=_dt3.date.today() - _dt3.timedelta(days=i), value=15.0 + i % 9)
    for i in range(100)
])
_thin = vxm.build_state(_vix_quotes(**{"^VIX": 18.0, "^VIX3M": 20.0}), _short)
check("표본 100일이면 경고", any("표본이 짧" in w for w in _thin.warnings),
      str(_thin.warnings)[:70])
check("그래도 백분위는 계산", _thin.pct_5y is not None, str(_thin.pct_5y))

print("\n=== VIX 렌더링 ===")
_demo_vix = demo.demo_vix()
_vh = ui.render_vix(_demo_vix)
check("현재값 표시", "dash-vix-spot" in _vh and "16.40" in _vh)
check("곡선 SVG", 'class="dash-vix-curve"' in _vh)
check("만기 라벨 4개",
      all(lb in _vh for lb in ("VIX9D", "VIX3M", "VIX6M")), "")
check("미검증 표시", "미검증" in _vh)
check("하드코딩 색 없음",
      not _re.findall(r"#[0-9a-fA-F]{6}", _vh),
      str(_re.findall(r"#[0-9a-fA-F]{6}", _vh)))
check("타이밍 도구 아님을 명시", "타이밍 도구가 아닙니다" in _vh)

_inv_html = ui.render_vix(demo.demo_vix(inverted=True))
check("역전은 강조 클래스", 'class="dash-vix inverted"' in _inv_html)
check("역전 라벨", "백워데이션" in _inv_html)
check("정상은 강조 안 함", 'class="dash-vix inverted"' not in _vh)

check("실패도 렌더링", "VIX 시세" in ui.render_vix(_empty))
check("점이 2개 미만이면 곡선 없음", ui.render_vix_curve(_empty) == "")
check("한 점만 있으면 곡선 없음", ui.render_vix_curve(_only_spot) == "")

_xss_state = vxm.VixState()
_xss_state.error = '<img src=x onerror="y">'
check("오류 메시지 이스케이프", "&lt;img" in ui.render_vix(_xss_state))

print("\n=== VIX 설정 정합성 ===")
check("계열 4개", len(vxm.FAMILY) == 4, str(len(vxm.FAMILY)))
check("만기가 오름차순",
      [d for _s, _l, d, _v in vxm.FAMILY] == sorted(
          d for _s, _l, d, _v in vxm.FAMILY))
check("VIX 만 검증됨",
      [l for _s, l, _d, v in vxm.FAMILY if v] == ["VIX"],
      str([l for _s, l, _d, v in vxm.FAMILY if v]))
check("경계값 순서", vxm.STRONG_CONTANGO < vxm.BACKWARDATION)
check("FRED 계열 ID", vxm.FRED_SERIES == "VIXCLS")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 공탐 파싱 방어 (응답 구조를 확인할 수 없으므로) ===")
import datetime as _dt4  # noqa: E402

_now_ms = int(_dt4.datetime.now(_dt4.timezone.utc).timestamp() * 1000)
_now_s = int(_now_ms / 1000)

# 타임스탬프 형식을 단정하지 않습니다 — CNN 문서가 없어 바뀔 수 있습니다
# 자정 무렵에는 서버 날짜와 UTC 날짜가 하루 다릅니다 — 둘 다 받아들입니다
_ok_days = {_dt4.date.today(), _dt4.datetime.now(_dt4.timezone.utc).date()}
check("밀리초 타임스탬프", fgm._date_from(_now_ms) in _ok_days,
      str(fgm._date_from(_now_ms)))
check("초 타임스탬프도 처리", fgm._date_from(_now_s) in _ok_days,
      str(fgm._date_from(_now_s)))
check("ISO 날짜 문자열", fgm._date_from("2026-11-07") == _dt4.date(2026, 11, 7))
check("ISO 일시 문자열",
      fgm._date_from("2026-11-07T12:00:00Z") == _dt4.date(2026, 11, 7))
# 상식 범위를 벗어나면 틀린 날짜를 보여주는 대신 비웁니다
check("1970년대로 나오면 거부", fgm._date_from(1000) is None,
      str(fgm._date_from(1000)))
check("먼 미래도 거부", fgm._date_from(99_999_999_999_999) is None)
check("문자열 쓰레기는 None", fgm._date_from("abc") is None)
check("None 은 None", fgm._date_from(None) is None)

# 키 이름이 바뀔 수 있으니 후보를 봅니다
_alt = fgm.parse({
    "fear_and_greed": {
        "value": 58.0, "label": "greed",
        "date": "2026-11-07",
        "previousClose": 57.0, "previous_week": 50.0,
    },
})
check("score 대신 value", near(_alt.score, 58.0), str(_alt.score))
check("rating 대신 label", _alt.rating == "greed", _alt.rating)
check("timestamp 대신 date", _alt.observed_at == _dt4.date(2026, 11, 7),
      str(_alt.observed_at))
check("previousClose 변형", near(_alt.previous_close, 57.0))
check("previous_week 변형", near(_alt.previous_week, 50.0))

# 구조를 알려주는 키 목록 — 진단에서 "CNN 이 무엇을 보냈나" 를 보여줍니다
check("최상위 키 기록", _alt.raw_keys == ["fear_and_greed"], str(_alt.raw_keys))
check("내부 키 기록", "value" in _alt.root_keys and "label" in _alt.root_keys,
      str(_alt.root_keys))

# 비교값을 못 읽어도 점수는 살아야 합니다
_bare = fgm.parse({"fear_and_greed": {"score": 42.0}})
check("비교값 없어도 ok", _bare.ok and near(_bare.score, 42.0))
check("비교값은 None", _bare.previous_week is None)
check("1주 대비도 None", _bare.change_1w is None)
check("관측일 없으면 None", _bare.observed_at is None)
check("관측일 없으면 지연도 None", _bare.lag_days is None)

print("\n=== 데모 표시 ===")
_banner = ui.render_demo_banner()
check("가짜임을 명시", "전부 가짜입니다" in _banner)
check("무엇이 가짜인지 열거",
      "공포탐욕지수" in _banner and "VIX" in _banner, "")
check("끄는 방법 안내", "데모 모드를 끄" in _banner)
_pv = ui.render_demo_banner(preview=True)
check("프리뷰용 문구", "streamlit run app.py" in _pv)
check("데모 태그", ui.demo_tag(True) != "" and ui.demo_tag(False) == "")
check("CNN 대조 링크 상수", fgm.CNN_PAGE.startswith("https://"))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 평균 대비 신호의 단위와 자리수 ===")
# '주' 로 못박아 둬서 일간 계열(하이일드 스프레드)이 "20주 평균" 으로
# 나왔고, ,.0f 때문에 3.2 -> 4.05 가 "3 -> 4" 로 보여 변화가 사라졌습니다.

check("일간 계열은 '일'", macro._period_label(1, 20) == "20일",
      macro._period_label(1, 20))
check("주간 계열은 '주'", macro._period_label(7, 4) == "4주",
      macro._period_label(7, 4))
check("월간 계열은 '개월'", macro._period_label(30, 6) == "6개월",
      macro._period_label(30, 6))
check("분기 이상은 '기'", macro._period_label(120, 2) == "2기",
      macro._period_label(120, 2))

import demo as _dm  # noqa: E402

_series, _errs = _dm.demo_macro_series()
_readings = macro.build_readings(config.macro_series(), _series, _errs)
_vs = {}
for _r in _readings:
    for _t in macro.evaluate(_r):
        if _t.rule == "vs_mean":
            _vs[_r.spec.key] = _t

check("하이일드 평균 대비 신호가 난다", "hy_spread" in _vs, str(list(_vs)))
if "hy_spread" in _vs:
    _t = _vs["hy_spread"]
    check("일간 계열에 '일' 단위", "20일 평균" in _t.title, _t.title)
    check("'주' 로 쓰지 않는다", "20주" not in _t.title, _t.title)
    check("소수점 2자리가 보존된다",
          "3.20" in _t.detail and "4.05" in _t.detail, _t.detail)
    check("단위가 붙는다", "%p" in _t.detail, _t.detail)

check("실업수당은 여전히 '주' 단위",
      "4주 평균" in _vs["claims"].title if "claims" in _vs else False,
      _vs.get("claims").title if "claims" in _vs else "신호 없음")
check("정수 계열은 소수점을 붙이지 않는다",
      "245,000" in _vs["claims"].detail if "claims" in _vs else False,
      _vs.get("claims").detail if "claims" in _vs else "")

print("\n=== 크레딧 임계값 설계 ===")
_hy_spec = [s for s in config.MACRO_SERIES if s.key == "hy_spread"][0]
check("절대 %p 변화 기준을 쓰지 않는다", _hy_spec.change_abs is None,
      "스프레드가 3%p 일 때와 8%p 일 때 의미가 달라집니다")
check("자기 평균 대비 상대 기준을 쓴다",
      _hy_spec.pct_vs_mean is not None and _hy_spec.mean_periods >= 20,
      f"{_hy_spec.pct_vs_mean}% / {_hy_spec.mean_periods}기간")
check("레벨 기준이 위기 표시로 남아 있다", _hy_spec.level_above == 5.0)
check("임계값 근거가 화면 문구에 적혀 있다", "임계값 근거" in _hy_spec.why)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== FRED 막힌 호스트 대응 ===")
# 2026-11-11 배포 환경 실측: fred.stlouisfed.org 는 30초 ReadTimeout,
# api.stlouisfed.org 는 0.1초에 응답(HTTP 400). 즉 **호스트가 갈립니다.**
import threading as _th7  # noqa: E402
import time as _tm7  # noqa: E402

import sources.fred as _fr7  # noqa: E402

check("CSV 타임아웃을 짧게 둔다", _fr7.TIMEOUT <= 10,
      f"{_fr7.TIMEOUT}초 — 30초면 14계열에 3분 넘게 멈춥니다")
check("API 타임아웃은 넉넉히", _fr7.API_TIMEOUT >= _fr7.TIMEOUT,
      f"{_fr7.API_TIMEOUT}초 — 여기는 응답이 오는 경로입니다")
check("연속 실패 시 포기 기준이 있다", _fr7.TIMEOUT_GIVE_UP >= 2,
      str(_fr7.TIMEOUT_GIVE_UP))

# 차단기 — 전부 타임아웃이면 전부 시도하지 않아야 합니다
_tried = []
_orig_fetch = _fr7.fetch_series


def _always_timeout(sid, *, start=None):
    _tried.append(sid)
    raise _fr7.FredError(f"{sid}: FRED 응답 없음 (8초 초과). …")


_fr7.fetch_series = _always_timeout
try:
    _ids = [f"S{i:02d}" for i in range(14)]
    _out, _errs = _fr7.fetch_many(_ids)
    check("막힌 호스트에 전부 물어보지 않는다", len(_tried) < len(_ids),
          f"{len(_tried)}/{len(_ids)} 시도")
    check("건너뛴 계열도 사유를 남긴다",
          all(_errs.get(i) for i in _ids),
          "빈칸으로 두면 왜 없는지 알 수 없습니다")
    _skip = [k for k, v in _errs.items() if "건너뜀" in v]
    check("건너뜀을 따로 표시한다", bool(_skip), f"{len(_skip)}개")
    check("계열 ID 문제가 아님을 적는다",
          any("계열 ID 문제가 아닙니다" in v for v in _errs.values()))
finally:
    _fr7.fetch_series = _orig_fetch

# 하나라도 성공하면 연속 기록이 지워져야 합니다
_seq = []


def _flaky(sid, *, start=None):
    _seq.append(sid)
    if len(_seq) % 2 == 0:
        raise _fr7.FredError(f"{sid}: FRED 응답 없음 (8초 초과). …")
    return _fr7.Series(series_id=sid, observations=[
        _fr7.Observation(__import__("datetime").date(2026, 1, 1), 1.0)])


_fr7.fetch_series = _flaky
try:
    _out2, _errs2 = _fr7.fetch_many([f"T{i:02d}" for i in range(10)])
    check("간헐적 실패로는 포기하지 않는다",
          not any("건너뜀" in v for v in _errs2.values()),
          "성공이 섞이면 연속 기록이 지워져야 합니다")
    check("성공한 계열은 돌려준다", len(_out2) >= 4, str(len(_out2)))
finally:
    _fr7.fetch_series = _orig_fetch

print("\n=== FRED 키 형식 검사 ===")
_saved_key = os.environ.pop("FRED_API_KEY", None)
check("키가 없으면 그 사실을 말한다", "설정되지 않았" in _fr7.key_problem())
os.environ["FRED_API_KEY"] = "abc"
check("짧은 키를 잡는다", "모자랍니다" in _fr7.key_problem(), _fr7.key_problem())
check("짧은 건 따옴표 탓이 아니라고 말한다",
      "잘렸다" in _fr7.key_problem(),
      "따옴표가 섞이면 오히려 길어집니다 — 엉뚱한 데를 보게 하면 안 됩니다")
os.environ["FRED_API_KEY"] = '"' + "a" * 32 + '"'
check("긴 키는 따옴표를 지목한다", "깁니다" in _fr7.key_problem(),
      _fr7.key_problem())
check("섞인 문자를 보여준다", "'\"'" in _fr7.key_problem(),
      _fr7.key_problem())
os.environ["FRED_API_KEY"] = "A" * 32
check("대문자를 잡는다", "대문자" in _fr7.key_problem(), _fr7.key_problem())
os.environ["FRED_API_KEY"] = '"' + "a" * 30 + '"'
check("따옴표가 섞인 키를 잡는다", bool(_fr7.key_problem()))
_diag_src = pathlib.Path("tools/diagnose.py").read_text(encoding="utf-8")
check("진단이 키 모양을 가려서 보여준다", "모양:" in _diag_src,
      "길이만으로는 어디가 잘렸는지 감이 안 옵니다")
check("발급 페이지를 알려준다",
      "fredaccount.stlouisfed.org/apikeys" in _diag_src)
os.environ["FRED_API_KEY"] = "a1" * 16
check("정상 키는 통과", _fr7.key_problem() == "", _fr7.key_problem())
if _saved_key is None:
    os.environ.pop("FRED_API_KEY", None)
else:
    os.environ["FRED_API_KEY"] = _saved_key


print("\n=== 언제 것인가 · 다음에 언제 나오나 (2026-11-12 '72일 전') ===")
import calendar_events as _ce  # noqa: E402
import components as _ui  # noqa: E402

_today = dt.date(2026, 11, 12)
_cpi_spec = spec(key="cpi", name="CPI", series_id="CPIAUCSL", mode="yoy",
                 period_days=30, release_id=10)
_cpi = macro.build_reading(
    _cpi_spec,
    monthly("CPIAUCSL", "2024-09-01", [100 + i * 0.3 for i in range(25)]),   # 마지막 = 2026-09
    "", _today)
check("FRED 는 9월 통계를 9월 1일자로 적는다 → 72일 전", _cpi.lag_days == 72, str(_cpi.lag_days))
check("화면에는 '9월분' 이라고 적는다", _cpi.period_label == "9월분", _cpi.period_label)
check("다음 발표일을 모르면 주기를 적는다", _cpi.cadence_label == "월 1회 발표")
_payload = {"release_dates": [
    {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-10-14"},
    {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-12-10"},
    {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-11-13"},
    {"release_id": 50, "release_name": "Employment Situation", "date": "2026-11-12"},
    {"release_id": "x", "date": "2026-11-20"}, {"release_id": 46, "date": "없음"}, "쓰레기",
]}
_next = _ce.next_release_dates(_payload, _today)
check("오늘 이후 가장 가까운 발표일을 고른다",
      _next == {10: dt.date(2026, 11, 13), 50: dt.date(2026, 11, 12)}, str(_next))
check("응답이 이상하면 빈 묶음", _ce.next_release_dates(None) == {} and _ce.next_release_dates([]) == {})
macro.attach_context([_cpi], next_releases=_next)
check("다음 발표일을 붙이면 그 날짜", _cpi.cadence_label == "다음 발표 11/13", _cpi.cadence_label)
_jobs = macro.build_reading(
    spec(key="unrate", name="실업률", series_id="UNRATE", period_days=30, release_id=50),
    monthly("UNRATE", "2025-09-01", [4.0 + i * 0.01 for i in range(13)]), "", _today)
macro.attach_context([_jobs], next_releases=_next)
check("발표일이 오늘이면 '오늘 발표'", _jobs.cadence_label == "오늘 발표", _jobs.cadence_label)
_wk = macro.build_reading(
    spec(key="claims", name="실업수당", series_id="ICSA", period_days=7),
    series_of("ICSA", [("2026-10-24", 220), ("2026-10-31", 225), ("2026-11-07", 230)]), "", _today)
check("주간 통계", _wk.period_label == "11/07 주간" and _wk.cadence_label == "주 1회 발표",
      f"{_wk.period_label} · {_wk.cadence_label}")
_d10_spec = spec(key="ust10", name="미국 10년 국채 금리", series_id="DGS10", unit="%",
                 period_days=1, live_symbol="^TNX", change_abs=0.5, change_periods=2)
_d10 = macro.build_reading(
    _d10_spec, series_of("DGS10", [("2026-11-05", 4.10), ("2026-11-06", 4.12), ("2026-11-09", 4.15)]),
    "", _today)
check("일별 금리 — 휴일이 끼면 3일 전이 최신", _d10.lag_days == 3
      and _d10.period_label == "11/09 종가" and _d10.cadence_label == "다음 영업일 공개",
      f"{_d10.period_label} · {_d10.cadence_label}")
check("지금 시세가 없으면 적지 않는다", _d10.live_label == "")
_before = [(t.reading.spec.key, t.rule) for t in macro.evaluate_all([_d10])]
macro.attach_context([_d10], live_quotes={"^TNX": (4.95, 0.80), "^IRX": (4.0, None)})
check("지금 시세를 붙인다", _d10.live_label == "지금 4.95%", _d10.live_label)
check("임계값 판정은 FRED 값 그대로 (장중 시세로 신호를 바꾸지 않음)",
      _d10.value == 4.15
      and [(t.reading.spec.key, t.rule) for t in macro.evaluate_all([_d10])] == _before)
macro.attach_context([_d10], live_quotes={"^TNX": None})
check("시세가 비면 직전 값을 지우지 않고 넘어간다", _d10.live_value == 4.95)
_old = macro.build_reading(
    _cpi_spec, monthly("CPIAUCSL", "2023-12-01", [100 + i * 0.3 for i in range(25)]), "",
    dt.date(2026, 1, 20))
check("해가 다르면 연도를 적는다", _old.period_label == "2025년 12월분", _old.period_label)
_html = _ui.render_macro_table(
    [("g", "묶음", "부제")], {"g": [_cpi, _d10, _wk]}, set())
check("표에 'N일 전' 이 없다", "일 전" not in _html)
check("표에 몇 월분 · 다음 발표 · 지금 시세가 있다",
      "9월분" in _html and "다음 발표 11/13" in _html and "지금 4.95%" in _html)
_stale = macro.build_reading(
    _cpi_spec, monthly("CPIAUCSL", "2024-03-01", [100 + i * 0.3 for i in range(25)]), "", _today)
check("정말 늦은 것은 '발표 지연' 으로 따로 적는다",
      _stale.stale and "발표 지연" in _ui.render_macro_table([("g", "묶음", "")], {"g": [_stale]}, set()))
_card = _ui.render_macro_card(_d10)
check("카드에도", "지금 4.95%" in _card and "11/09 종가" in _card and "일 전" not in _card)
check("실제 설정 — 10년물에 지금 시세, CPI·고용·PCE 에 발표 번호",
      config.macro_series_by_key("ust10").live_symbol == "^TNX"
      and config.macro_series_by_key("cpi").release_id == 10
      and config.macro_series_by_key("payrolls").release_id == 50
      and config.macro_series_by_key("core_pce").release_id == 54)
_valid = {rid for rid, *_ in _ce.FRED_RELEASES}
check("발표 번호는 일정표가 아는 번호만",
      all(s.release_id in _valid for s in config.MACRO_SERIES if s.release_id is not None))

print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
