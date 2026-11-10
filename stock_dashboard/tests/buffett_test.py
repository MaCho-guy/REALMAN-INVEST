"""
버핏식 스크리닝 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/buffett_test.py

검증 범위: companyfacts 파싱, 흐름/저량 계정 분리, 파생 지표(ROE·마진·주주이익),
           기준 6종의 통과·탈락·판정불가, **거짓 통과 가드**, 순위, 설정 정합성.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buffett  # noqa: E402
import config  # noqa: E402
from buffett import Screen, Thresholds, YearRow  # noqa: E402
from sources import edgar_facts  # noqa: E402

FAILURES: list[str] = []
M = 1_000_000.0


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def near(a, b, tol=0.05) -> bool:
    return a is not None and b is not None and abs(a - b) < tol


def rows(spec: list[dict], start: int = 2016) -> list[YearRow]:
    return [YearRow(year=start + i, end=f"{start + i}-12-31", **d)
            for i, d in enumerate(spec)]


def screen_of(spec: list[dict], ticker: str = "TEST",
              th: Thresholds | None = None, start: int = 2016) -> Screen:
    s = Screen(ticker=ticker, name=ticker, years=rows(spec, start))
    return buffett.run_checks(s, th or Thresholds())


def verdict(screen: Screen, key: str) -> str:
    for c in screen.checks:
        if c.criterion.key == key:
            return c.verdict
    return "missing"


def check_of(screen: Screen, key: str):
    for c in screen.checks:
        if c.criterion.key == key:
            return c
    return None


def good_year(**over) -> dict:
    """모든 기준을 통과하는 한 해."""
    base = dict(net_income=200 * M, revenue=1_000 * M, gross_profit=600 * M,
                dep_amort=100 * M, capex=60 * M, equity=800 * M,
                long_term_debt=200 * M)
    base.update(over)
    return base


# ──────────────────────────────────────────────────────────────────────────────
print("=== companyfacts 파싱 ===")
payload = {
    "entityName": "TEST CORP",
    "facts": {
        "us-gaap": {
            "NetIncomeLoss": {"units": {"USD": [
                {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0,
                 "form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-02-01"},
                {"start": "2025-01-01", "end": "2025-12-31", "val": 105.0,
                 "form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-03-01"},
                {"start": "2025-10-01", "end": "2025-12-31", "val": 30.0,
                 "form": "10-Q", "fy": 2025, "fp": "Q4", "filed": "2026-02-01"},
            ]}},
            "StockholdersEquity": {"units": {"USD": [
                {"end": "2025-12-31", "val": 500.0, "form": "10-K",
                 "fy": 2025, "fp": "FY", "filed": "2026-02-01"},
            ]}},
            "SomeTagWeDoNotWant": {"units": {"USD": [
                {"end": "2025-12-31", "val": 1.0, "form": "10-K",
                 "fy": 2025, "fp": "FY", "filed": "2026-02-01"},
            ]}},
        },
    },
}
facts = edgar_facts.parse_facts(payload, 123, keep=buffett.KEEP_TAGS)
check("기업명 파싱", facts.entity_name == "TEST CORP", facts.entity_name)
check("keep 밖 태그는 버림", "SomeTagWeDoNotWant" not in facts.by_tag,
      str(list(facts.by_tag)))
check("전체 태그 수는 집계", facts.total_tags == 3, str(facts.total_tags))

tag, annual = facts.annual(buffett.TAGS["net_income"])
check("연간 구간만 추림", len(annual) == 1, f"{len(annual)}건")
check("중복은 filed 최신", near(annual[0].val, 105.0), str(annual[0].val))
check("태그 이름 반환", tag == "NetIncomeLoss", tag)

tag_eq, instants = facts.instants(buffett.TAGS["equity"])
check("시점값 추림", len(instants) == 1 and near(instants[0].val, 500.0))

tag_miss, empty = facts.get(("NopeTag",))
check("없는 태그는 빈 목록", tag_miss == "" and empty == [])

raised = False
try:
    edgar_facts.parse_facts({"facts": {}}, 1)
except edgar_facts.FactsNotFound:
    raised = True
check("facts 가 비면 FactsNotFound", raised)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 흐름/저량 계정 분리 ===")
# ROE 분모는 같은 연도말 자본이어야 합니다. 연간 구간과 시점값을 섞으면 어긋납니다.
multi = {
    "entityName": "MULTI",
    "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": float(y - 2000),
             "form": "10-K", "fy": y, "fp": "FY", "filed": f"{y + 1}-02-01"}
            for y in range(2020, 2026)
        ]}},
        "StockholdersEquity": {"units": {"USD": [
            {"end": f"{y}-12-31", "val": float((y - 2000) * 10),
             "form": "10-K", "fy": y, "fp": "FY", "filed": f"{y + 1}-02-01"}
            for y in range(2020, 2026)
        ]}},
    }},
}
mf = edgar_facts.parse_facts(multi, 1, keep=buffett.KEEP_TAGS)
year_rows, missing = buffett.build_years(mf, years=10)
check("6개 연도 생성", len(year_rows) == 6, f"{len(year_rows)}개")
check("연도 오름차순", [r.year for r in year_rows] == list(range(2020, 2026)))
check("순이익·자본이 같은 연도로 묶임",
      all(near(r.net_income * 10, r.equity) for r in year_rows))
check("ROE 10%", all(near(r.roe, 10.0) for r in year_rows),
      str([round(r.roe, 1) for r in year_rows]))
check("못 찾은 계정 보고", "capex" in missing and "revenue" in missing,
      str(missing))

trimmed, _ = buffett.build_years(mf, years=3)
check("years 한도 적용", len(trimmed) == 3, f"{len(trimmed)}개")
check("최근 것만 남김", [r.year for r in trimmed] == [2023, 2024, 2025])

# 결산일이 며칠 어긋나도 ±7일 안이면 붙입니다
off = {
    "entityName": "OFF",
    "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0,
             "form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-02-01"}]}},
        "StockholdersEquity": {"units": {"USD": [
            {"end": "2025-12-28", "val": 500.0, "form": "10-K",
             "fy": 2025, "fp": "FY", "filed": "2026-02-01"}]}},
    }},
}
off_rows, _ = buffett.build_years(
    edgar_facts.parse_facts(off, 1, keep=buffett.KEEP_TAGS))
check("결산일 3일 차이는 매칭", near(off_rows[0].equity, 500.0),
      str(off_rows[0].equity))

far = {
    "entityName": "FAR",
    "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0,
             "form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-02-01"}]}},
        "StockholdersEquity": {"units": {"USD": [
            {"end": "2025-09-30", "val": 500.0, "form": "10-K",
             "fy": 2025, "fp": "FY", "filed": "2026-02-01"}]}},
    }},
}
far_rows, _ = buffett.build_years(
    edgar_facts.parse_facts(far, 1, keep=buffett.KEEP_TAGS))
check("92일 차이는 매칭 안 함", far_rows[0].equity is None,
      str(far_rows[0].equity))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 파생 지표 ===")
r = YearRow(year=2025, end="2025-12-31", net_income=200 * M, revenue=1_000 * M,
            gross_profit=600 * M, dep_amort=100 * M, capex=60 * M,
            equity=800 * M, long_term_debt=400 * M)
check("ROE", near(r.roe, 25.0), f"{r.roe}")
check("매출총이익률", near(r.gross_margin, 60.0), f"{r.gross_margin}")
check("순이익률", near(r.net_margin, 20.0), f"{r.net_margin}")
# 주주이익 = 200 + 100 − 60 = 240
check("주주이익 (버핏 1986 정의)", near(r.owner_earnings / M, 240.0),
      f"{r.owner_earnings / M}")
check("설비투자 < 감가상각", r.capex_exceeds_depreciation is False)
check("부채/자본", near(r.debt_to_equity, 0.5))
check("부채 상환 연수", near(r.debt_years, 2.0))

# 설비투자는 음수로 공시되는 경우가 있어 절댓값을 씁니다
neg = YearRow(year=2025, end="x", net_income=200 * M, dep_amort=100 * M,
              capex=-60 * M)
check("음수 설비투자도 같은 결과", near(neg.owner_earnings / M, 240.0),
      f"{neg.owner_earnings / M}")

# 매출원가만 있으면 매출총이익을 만듭니다
imputed = YearRow(year=2025, end="x", revenue=1_000 * M,
                  cost_of_revenue=400 * M)
check("매출원가로 마진 산출", near(imputed.gross_margin, 60.0))

check("자본이 음수면 ROE None",
      YearRow(year=1, end="x", net_income=1.0, equity=-5.0).roe is None)
check("자본이 0이면 ROE None",
      YearRow(year=1, end="x", net_income=1.0, equity=0.0).roe is None)
check("적자면 부채 연수 None",
      YearRow(year=1, end="x", net_income=-1.0,
              long_term_debt=5.0).debt_years is None)
check("감가상각 없으면 주주이익 None",
      YearRow(year=1, end="x", net_income=1.0, capex=1.0).owner_earnings is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 거짓 통과 가드 ===")
# 리츠·금융은 매출원가를 따로 쓰지 않아 매출총이익 = 매출 입니다.
# 그러면 마진 100% 고정 → 표준편차 0 → '완벽하게 안정적' 이라는 거짓 통과.
reit_row = YearRow(year=2025, end="x", revenue=1_000 * M,
                   gross_profit=1_000 * M)
check("매출총이익 = 매출이면 마진 None", reit_row.gross_margin is None,
      str(reit_row.gross_margin))

reit = screen_of([
    dict(net_income=90 * M, revenue=1_000 * M, gross_profit=1_000 * M,
         dep_amort=400 * M, capex=10 * M, equity=3_000 * M,
         long_term_debt=2_500 * M)
] * 10)
check("리츠 형태는 마진 판정 불가", verdict(reit, "stable_margin") == "unknown",
      verdict(reit, "stable_margin"))

# 감가상각이 지배하면 주주이익이 순이익을 크게 넘습니다 — 통과시키되 경고
oe_check = check_of(reit, "owner_earnings")
check("주주이익 과대 시 경고", oe_check.warning != "", oe_check.warning[:60])
check("경고가 있어도 통과는 통과", oe_check.verdict == "pass", oe_check.verdict)

normal = screen_of([good_year()] * 10)
check("정상 기업엔 경고 없음",
      check_of(normal, "owner_earnings").warning == "")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 기준 6종 — 통과 ===")
all_pass = screen_of([good_year()] * 10)
check("6개 전부 통과", all_pass.passed_count == 6, all_pass.score_label)
check("판정 불가 0", all_pass.unknown_count == 0)
check("점수 라벨", all_pass.score_label == "6 / 6", all_pass.score_label)


print("\n=== 기준 6종 — 탈락 ===")
low_roe = screen_of([good_year(net_income=40 * M)] * 10)
check("ROE 낮으면 탈락", verdict(low_roe, "roe") == "fail")

neg_oe = screen_of([good_year(capex=500 * M)] * 10)
check("설비투자가 크면 주주이익 탈락",
      verdict(neg_oe, "owner_earnings") == "fail")
check("동시에 자본집약 탈락", verdict(neg_oe, "capex_light") == "fail")

heavy = screen_of([good_year(capex=150 * M)] * 10)
check("설비투자 > 감가상각 10년이면 탈락",
      verdict(heavy, "capex_light") == "fail")
cl = check_of(heavy, "capex_light")
check("배수를 함께 보여줌", "1.50배" in cl.detail, cl.detail)

indebted = screen_of([good_year(long_term_debt=2_000 * M)] * 10)
check("부채 많으면 탈락", verdict(indebted, "low_debt") == "fail")

# 부채/자본은 높지만 순이익으로 빨리 갚을 수 있으면 통과 (둘 중 하나)
fast_repay = screen_of([good_year(long_term_debt=600 * M,
                                  net_income=400 * M)] * 10)
check("상환 연수가 짧으면 통과", verdict(fast_repay, "low_debt") == "pass",
      check_of(fast_repay, "low_debt").detail)

swingy = screen_of([
    good_year(gross_profit=gp * M)
    for gp in (300, 700, 250, 800, 400, 750, 200, 850, 350, 700)
])
check("마진이 흔들리면 탈락", verdict(swingy, "stable_margin") == "fail",
      check_of(swingy, "stable_margin").detail)

erratic = screen_of([
    good_year(net_income=ni * M)
    for ni in (200, -50, 300, 100, 280, -30, 320, 150, 400, 420)
])
check("적자·급감이 많으면 탈락",
      verdict(erratic, "earnings_consistency") == "fail",
      check_of(erratic, "earnings_consistency").detail)
check("탈락 연도를 적어줌",
      "2017" in check_of(erratic, "earnings_consistency").detail)


print("\n=== 기준 6종 — 판정 불가 ===")
thin = screen_of([dict(net_income=100 * M, revenue=500 * M, equity=400 * M)] * 2)
check("연도가 적으면 전부 판정 불가", thin.unknown_count == 6,
      f"불가 {thin.unknown_count}")
check("판정 불가는 통과가 아님", thin.passed_count == 0)
check("판정 불가는 탈락도 아님",
      all(not c.known for c in thin.checks))

no_capex = screen_of([dict(net_income=200 * M, revenue=1_000 * M,
                           gross_profit=600 * M, equity=800 * M,
                           long_term_debt=200 * M)] * 10)
check("설비투자 없으면 주주이익 판정 불가",
      verdict(no_capex, "owner_earnings") == "unknown")
check("설비투자 없으면 자본경량도 판정 불가",
      verdict(no_capex, "capex_light") == "unknown")
check("나머지는 정상 판정", verdict(no_capex, "roe") == "pass")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 임계값이 실제로 적용되나 ===")
strict = screen_of([good_year()] * 10, th=Thresholds(roe_min=50.0))
check("기준선을 올리면 탈락", verdict(strict, "roe") == "fail")
loose = screen_of([good_year(net_income=40 * M)] * 10,
                  th=Thresholds(roe_min=4.0))
check("기준선을 내리면 통과", verdict(loose, "roe") == "pass")

# 10년 중 8년 요구 — 2년만 미달이면 통과, 3년이면 탈락
mostly = screen_of([good_year(net_income=ni * M)
                    for ni in (40, 40, 200, 200, 200, 200, 200, 200, 200, 200)])
check("2년 미달은 통과", verdict(mostly, "roe") == "pass",
      check_of(mostly, "roe").detail)
barely = screen_of([good_year(net_income=ni * M)
                    for ni in (40, 40, 40, 200, 200, 200, 200, 200, 200, 200)])
check("3년 미달은 탈락", verdict(barely, "roe") == "fail",
      check_of(barely, "roe").detail)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 순위 ===")
a = screen_of([good_year()] * 10, ticker="AAA")
b = screen_of([good_year(net_income=40 * M)] * 10, ticker="BBB")
c = screen_of([dict(net_income=1 * M)] * 2, ticker="CCC")
broken = Screen(ticker="DDD", error="조회 실패")
ranked = buffett.rank([b, broken, c, a])
check("통과 많은 순", [s.ticker for s in ranked[:2]] == ["AAA", "BBB"],
      str([s.ticker for s in ranked]))
check("실패는 맨 뒤", ranked[-1].ticker == "DDD")
check("실패는 ok=False", not broken.ok)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 출처 표기 ===")
check("기준 6개", len(buffett.CRITERIA) == 6, str(len(buffett.CRITERIA)))
check("출처 종류는 세 가지",
      {c.provenance for c in buffett.CRITERIA} <= {"verbatim", "practice", "mine"},
      str({c.provenance for c in buffett.CRITERIA}))
verbatim = [c for c in buffett.CRITERIA if c.provenance == "verbatim"]
check("버핏 원문 기준이 2개", len(verbatim) == 2,
      str([c.key for c in verbatim]))
check("주주이익은 원문", buffett.CRITERIA_BY_KEY["owner_earnings"].provenance
      == "verbatim")
check("설비투자 규칙도 원문",
      buffett.CRITERIA_BY_KEY["capex_light"].provenance == "verbatim")
check("1986년 서한을 명시",
      "1986" in buffett.CRITERIA_BY_KEY["owner_earnings"].source)
check("(c)가 추정임을 한계로 적음",
      "추정" in buffett.CRITERIA_BY_KEY["owner_earnings"].caveat)
check("ROE 15%는 원문이 아님을 밝힘",
      buffett.CRITERIA_BY_KEY["roe"].provenance == "practice"
      and "원문 표현은 아닙니다" in buffett.CRITERIA_BY_KEY["roe"].source)
check("모든 기준에 한계가 적혀 있음",
      all(c.caveat for c in buffett.CRITERIA),
      str([c.key for c in buffett.CRITERIA if not c.caveat]))
check("반도체 사이클 한계를 명시",
      "반도체" in buffett.CRITERIA_BY_KEY["stable_margin"].caveat)
check("리츠 한계를 명시",
      "리츠" in buffett.CRITERIA_BY_KEY["low_debt"].caveat)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 프롬프트 ===")
p = buffett.prompt_for(all_pass)
check("점수 포함", "6 / 6" in p)
check("해자를 묻는다", "해자" in p)
check("ROE 가 자본구조 때문인지 묻는다", "자사주" in p)
check("이해 가능한 사업인지 묻는다", "이해할 수 있는" in p)
check("추천 금지 문구", "매수/매도 추천" in p)
check("목표주가 금지 문구", "목표주가" in p)

p_fail = buffett.prompt_for(erratic)
check("탈락 기준이 업종 특성인지 묻는다", "구조적인 것입니까" in p_fail)
check("탈락 항목을 나열", "이익이 꾸준한가" in p_fail)

p_unk = buffett.prompt_for(no_capex)
check("판정 불가도 알려준다", "판정 불가" in p_unk)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 설정 정합성 ===")
tickers = config.screen_tickers()
check("대상이 비어 있지 않음", len(tickers) > 0, f"{len(tickers)}개")
check("중복 없음", len(set(tickers)) == len(tickers))
check("ETF 제외", not ({"QQQ", "SCHD"} & set(tickers)),
      str({"QQQ", "SCHD"} & set(tickers)))
check("한국 종목 제외", not any("." in t for t in tickers),
      str([t for t in tickers if "." in t]))
check("관심종목 미국 개별주 포함",
      {"MSFT", "AAPL", "MU", "O", "UNH"} <= set(tickers),
      str({"MSFT", "AAPL", "MU", "O", "UNH"} - set(tickers)))
th = config.screen_thresholds()
check("임계값이 Thresholds 로 변환됨", isinstance(th, Thresholds))
check("정수 필드는 정수",
      isinstance(th.roe_years_required, int)
      and isinstance(th.bad_years_allowed, int),
      f"{type(th.roe_years_required).__name__}")
check("KEEP_TAGS 가 TAGS 를 모두 덮음",
      all(t in buffett.KEEP_TAGS for cands in buffett.TAGS.values()
          for t in cands))
check("흐름/저량 키가 YearRow 필드와 일치",
      all(hasattr(YearRow(year=1, end="x"), k)
          for k in buffett.FLOW_KEYS + buffett.STOCK_KEYS))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 렌더링 ===")
import components as ui  # noqa: E402

html_out = ui.render_screen(all_pass, show_source=True,
                            prompt=buffett.prompt_for(all_pass))
check("카드 렌더링", "dash-screen" in html_out and "6 / 6" in html_out)
check("통과 표시", 'class="dash-check pass"' in html_out)
check("출처 표시", "출처" in html_out and "한계" in html_out)
check("프롬프트 접힘", "<details>" in html_out)

no_src = ui.render_screen(all_pass)
check("출처 숨기면 안 나옴", "<b>출처</b>" not in no_src)
check("버핏 원문 배지는 항상", "dash-prov verbatim" in no_src)

fail_html = ui.render_screen(erratic)
check("탈락 표시", 'class="dash-check fail"' in fail_html)

unk_html = ui.render_screen(thin)
check("판정 불가 표시", 'class="dash-check unknown"' in unk_html)

err_html = ui.render_screen(broken)
check("실패 카드", "조회 실패" in err_html)

warn_html = ui.render_screen(reit)
check("경고 표시", "dash-check-warn" in warn_html)

table = ui.render_screen_table([a, b], buffett.CRITERIA)
check("요약 표", "dash-table" in table and "AAA" in table and "BBB" in table)
check("빈 목록은 빈 문자열", ui.render_screen_table([], buffett.CRITERIA) == "")
check("실패만 있으면 빈 문자열",
      ui.render_screen_table([broken], buffett.CRITERIA) == "")

xss = Screen(ticker='<img src=x onerror="alert(1)">', name="x",
             years=rows([good_year()] * 10))
buffett.run_checks(xss)
xh = ui.render_screen(xss)
check("HTML 이스케이프", "&lt;img" in xh and "<img src=x" not in xh)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 데모 데이터 ===")
import demo  # noqa: E402

screens_map, _errors = demo.demo_screens()
check("데모 기업 5개", len(screens_map) == 5, str(len(screens_map)))
ranked_demo = buffett.rank(list(screens_map.values()))
check("MSFT·KO 가 상위",
      {s.ticker for s in ranked_demo[:2]} == {"MSFT", "KO"},
      str([s.ticker for s in ranked_demo]))
check("MU 는 하위 (사이클 업종)",
      ranked_demo.index(screens_map["MU"]) >= 3,
      str([s.ticker for s in ranked_demo]))
check("MU 는 마진에서 탈락",
      verdict(screens_map["MU"], "stable_margin") == "fail")
check("MU 는 이익 일관성에서 탈락",
      verdict(screens_map["MU"], "earnings_consistency") == "fail")
check("O 는 부채에서 탈락", verdict(screens_map["O"], "low_debt") == "fail")
check("O 는 마진 판정 불가 (거짓 통과 아님)",
      verdict(screens_map["O"], "stable_margin") == "unknown")
check("ZZZZ 는 전부 판정 불가",
      screens_map["ZZZZ"].unknown_count == 6)
check("데모 전부 10년 또는 2년",
      {s.year_count for s in screens_map.values()} == {10, 2},
      str({s.year_count for s in screens_map.values()}))


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
