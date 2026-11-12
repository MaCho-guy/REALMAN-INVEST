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
    """모든 기준을 통과하는 한 해.

    보강 기준 3개(ROIC·이자보상·FCF전환)가 들어오면서 영업이익·이자비용·
    법인세도 채웁니다. 안 채우면 '판정 불가' 가 되어 전부 통과하는
    픽스처가 아니게 됩니다.
      ROIC      = 260 x (1-0.22) / (200 + 800 - 280) = 28.2%  > 12%
      이자보상  = 260 / 9 = 28.9배                            > 5배
      FCF 전환  = (영업현금 315 - 설비 60) / 200 = 127%       > 70%
    """
    base = dict(net_income=200 * M, revenue=1_000 * M, gross_profit=600 * M,
                dep_amort=100 * M, capex=60 * M, equity=800 * M,
                long_term_debt=200 * M,
                operating_income=260 * M, interest_expense=9 * M,
                pretax_income=251 * M, tax_expense=55 * M,
                operating_cash_flow=315 * M,
                cash=280 * M, short_term_investments=0.0,
                short_term_debt=0.0, long_term_investments=0.0)
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
print(f"\n=== 기준 {len(buffett.CRITERIA)}종 — 통과 ===")
all_pass = screen_of([good_year()] * 10)
check("전부 통과", all_pass.passed_count == len(buffett.CRITERIA),
      all_pass.score_label)
check("판정 불가 0", all_pass.unknown_count == 0)
_N = len(buffett.CRITERIA)
check("점수 라벨", all_pass.score_label == f"{_N} / {_N}",
      all_pass.score_label)


print(f"\n=== 기준 {len(buffett.CRITERIA)}종 — 탈락 ===")
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
check("연도가 적으면 전부 판정 불가",
      thin.unknown_count == len(buffett.CRITERIA),
      f"불가 {thin.unknown_count} / {len(buffett.CRITERIA)}")
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
# 기준 수를 못박지 않습니다 — 늘릴 때마다 테스트가 깨집니다.
# 중요한 건 **CHECKS 와 개수가 맞는가** 입니다.
check("기준이 하나 이상", len(buffett.CRITERIA) >= 6,
      str(len(buffett.CRITERIA)))
check("CHECKS 와 수가 같다",
      len(buffett.CHECKS) == len(buffett.CRITERIA),
      f"{len(buffett.CHECKS)} vs {len(buffett.CRITERIA)} — 다르면 점수 분모가 어긋납니다")
check("키가 중복되지 않는다",
      len(buffett.CRITERIA_BY_KEY) == len(buffett.CRITERIA))
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
check("점수 포함", f"{len(buffett.CRITERIA)} / {len(buffett.CRITERIA)}" in p)
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
check("카드 렌더링", "dash-screen" in html_out
      and f"{len(buffett.CRITERIA)} / {len(buffett.CRITERIA)}" in html_out)
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
      screens_map["ZZZZ"].unknown_count == len(buffett.CRITERIA),
      f'{screens_map["ZZZZ"].unknown_count} / {len(buffett.CRITERIA)}')
check("데모 전부 10년 또는 2년",
      {s.year_count for s in screens_map.values()} == {10, 2},
      str({s.year_count for s in screens_map.values()}))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 보강 기준 3개 ===")
# 기존 6개 기준이 **스스로 인정한 한계**를 메우려고 넣은 것들입니다.
#   ROE 는 레버리지·자사주로 부풀려진다        -> ROIC
#   D/E 는 리츠·유틸리티를 전부 떨어뜨린다      -> 이자보상배율
#   이익이 현금이 되는지는 아무도 안 본다       -> FCF 전환율

M = 1_000_000.0


def _row(**kw):
    r = buffett.YearRow(year=kw.pop("year", 2025), end="2025-12-31")
    for k, v in kw.items():
        setattr(r, k, v)
    return r


print("\n-- 실효세율 --")
r = _row(tax_expense=200.0, pretax_income=1000.0)
check("실효세율 계산", abs(r.effective_tax_rate - 0.20) < 1e-9,
      str(r.effective_tax_rate))
check("적자면 None", _row(tax_expense=50.0,
                        pretax_income=-100.0).effective_tax_rate is None,
      "적자 해의 세율로 ROIC 를 왜곡시키지 않습니다")
check("0~50% 밖은 버린다",
      _row(tax_expense=900.0, pretax_income=1000.0).effective_tax_rate is None,
      "90% 같은 값은 일회성 항목일 가능성이 큽니다")
check("세금 없으면 None",
      _row(pretax_income=1000.0).effective_tax_rate is None)

print("\n-- 투하자본 --")
r = _row(equity=3000.0, long_term_debt=2000.0, short_term_debt=0.0,
         cash=500.0)
check("차입 + 자본 - 현금", r.invested_capital == 4500.0,
      str(r.invested_capital))
check("현금이 많으면 작아진다",
      _row(equity=3000.0, long_term_debt=0.0, cash=2900.0).invested_capital
      == 100.0,
      "쌓아둔 현금은 사업에 투입된 자본이 아닙니다")
check("0 이하면 None",
      _row(equity=100.0, long_term_debt=0.0, cash=500.0).invested_capital
      is None)
check("자본이 없으면 None", _row(long_term_debt=100.0).invested_capital is None)

print("\n-- ROIC vs ROE --")
# 같은 사업인데 빚만 늘린 회사: ROE 는 오르고 ROIC 는 그대로여야 합니다
base = _row(net_income=700.0, operating_income=1000.0,
            tax_expense=200.0, pretax_income=900.0,
            equity=3000.0, long_term_debt=0.0, cash=0.0)
levered = _row(net_income=700.0, operating_income=1000.0,
               tax_expense=200.0, pretax_income=900.0,
               equity=1000.0, long_term_debt=2000.0, cash=0.0)
check("빚을 늘리면 ROE 가 오른다", levered.roe > base.roe * 2,
      f"{base.roe:.1f}% -> {levered.roe:.1f}%")
check("ROIC 는 그대로", abs(levered.roic - base.roic) < 1e-6,
      f"{base.roic:.2f}% vs {levered.roic:.2f}% — 분모에 빚이 들어가 "
      "레버리지로 부풀릴 수 없습니다")
check("영업이익이 없으면 None", _row(equity=1000.0).roic is None)
check("세율을 못 구하면 세전으로 계산",
      abs(_row(operating_income=1000.0, equity=1000.0,
               long_term_debt=0.0, cash=0.0).roic - 100.0) < 1e-6,
      "세율 불명이라고 판정을 포기하지 않습니다")

print("\n-- 이자보상배율 --")
check("영업이익 / 이자비용",
      _row(operating_income=1000.0, interest_expense=100.0
           ).interest_coverage == 10.0)
check("이자비용이 음수로 와도 절대값",
      _row(operating_income=1000.0, interest_expense=-100.0
           ).interest_coverage == 10.0,
      "현금흐름표에서 음수로 오는 경우가 있습니다")
check("이자비용 0 이면 None",
      _row(operating_income=1000.0, interest_expense=0.0
           ).interest_coverage is None,
      "무한대는 숫자로 못 적습니다 — 무차입은 부채 기준이 잡습니다")
check("영업적자면 음수", _row(operating_income=-500.0,
                          interest_expense=100.0).interest_coverage == -5.0)

print("\n-- FCF 전환율 --")
check("FCF / 순이익",
      _row(net_income=700.0, operating_cash_flow=900.0,
           capex=200.0).fcf_conversion == 100.0)
check("순이익이 0 이하면 None",
      _row(net_income=-100.0, operating_cash_flow=900.0,
           capex=200.0).fcf_conversion is None,
      "적자 해의 비율은 의미가 없습니다")
check("설비투자가 크면 낮아진다",
      _row(net_income=700.0, operating_cash_flow=900.0,
           capex=800.0).fcf_conversion < 20.0,
      "투자기 기업이 낮게 나오는 것은 한계이고 caveat 에 적었습니다")

print("\n-- 기준 정의 --")
_new = {"roic", "interest_cover", "fcf_conversion"}
check("기준이 9개", len(buffett.CRITERIA) == 9, str(len(buffett.CRITERIA)))
check("CHECKS 와 CRITERIA 수가 같다",
      len(buffett.CHECKS) == len(buffett.CRITERIA),
      "다르면 점수의 분모가 어긋납니다")
check("새 기준 키가 전부 있다",
      _new <= set(buffett.CRITERIA_BY_KEY), str(_new - set(buffett.CRITERIA_BY_KEY)))
for _k in sorted(_new):
    _c = buffett.CRITERIA_BY_KEY[_k]
    check(f"{_k}: 근거가 적혀 있다", len(_c.source) > 40)
    check(f"{_k}: 한계가 적혀 있다", len(_c.caveat) > 60)
    check(f"{_k}: 출처 표기가 정직하다",
          _c.provenance in ("mine", "practice"),
          "버핏이 이 숫자 기준을 말한 적은 없습니다")
check("ROIC 한계에 ROE 와의 관계가 적혀 있다",
      "ROE" in buffett.CRITERIA_BY_KEY["roic"].caveat)
check("이자보상 한계에 리츠·유틸리티가 적혀 있다",
      "리츠" in buffett.CRITERIA_BY_KEY["interest_cover"].caveat)
check("미검증 사실이 적혀 있다",
      "검증" in buffett.CRITERIA_BY_KEY["roic"].caveat)

print("\n-- 태그 등록 --")
for _k in ("operating_income", "interest_expense", "tax_expense",
           "pretax_income"):
    check(f"us-gaap 태그 {_k}", _k in buffett.TAGS and bool(buffett.TAGS[_k]))
    check(f"흐름 계정으로 등록 {_k}", _k in buffett.FLOW_KEYS,
          "저량으로 읽으면 연도 축이 어긋납니다")

import buffett_kr as _bkr  # noqa: E402

_kr_keys = {r.key for r in _bkr.KR_RULES}
for _k in ("operating_income", "interest_expense", "tax_expense",
           "pretax_income"):
    check(f"K-IFRS 계정 {_k}", _k in _kr_keys,
          "없으면 국내 종목만 판정 불가가 늘어 불리해집니다")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 판정 불가 줄이기 (2026-11-12 전 종목 조사) ===")
from sources.edgar_xbrl import Fact as _Fact
from sources.edgar_facts import CompanyFacts as _CF


def _fa(tag, year, val, *, form="10-K", start=None, end=None):
    return _Fact(start=start or f"{year}-01-01", end=end or f"{year}-12-31", val=float(val),
                 form=form, fy=year, fp="FY", filed=f"{year + 1}-02-01", accn="a", tag=tag)


def _fi(tag, year, val, end=None):
    return _Fact(start=None, end=end or f"{year}-12-31", val=float(val), form="10-K",
                 fy=year, fp="FY", filed=f"{year + 1}-02-01", accn="a", tag=tag)


def _company(extra=None, drop=()):
    yrs = range(2016, 2026)
    by = {
        "NetIncomeLoss": [_fa("NetIncomeLoss", y, 200) for y in yrs],
        "Revenues": [_fa("Revenues", y, 1000) for y in yrs],
        "GrossProfit": [_fa("GrossProfit", y, 600) for y in yrs],
        "DepreciationDepletionAndAmortization": [_fa("DepreciationDepletionAndAmortization", y, 100) for y in yrs],
        "PaymentsToAcquirePropertyPlantAndEquipment": [_fa("PaymentsToAcquirePropertyPlantAndEquipment", y, 60) for y in yrs],
        "NetCashProvidedByUsedInOperatingActivities": [_fa("NetCashProvidedByUsedInOperatingActivities", y, 315) for y in yrs],
        "OperatingIncomeLoss": [_fa("OperatingIncomeLoss", y, 260) for y in yrs],
        "IncomeTaxExpenseBenefit": [_fa("IncomeTaxExpenseBenefit", y, 55) for y in yrs],
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
            [_fa("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", y, 251) for y in yrs],
        "StockholdersEquity": [_fi("StockholdersEquity", y, 800) for y in yrs],
        "LongTermDebtNoncurrent": [_fi("LongTermDebtNoncurrent", y, 200) for y in yrs],
        "InterestExpense": [_fa("InterestExpense", y, 9) for y in yrs],
        "CashAndCashEquivalentsAtCarryingValue": [_fi("CashAndCashEquivalentsAtCarryingValue", y, 280) for y in yrs],
    }
    for k in drop:
        by.pop(k)
    by.update(extra or {})
    return _CF(cik=1, entity_name="T", by_tag=by, total_tags=len(by))


def _verdict(screen, key):
    return next(c for c in screen.checks if c.criterion.key == key)


base_screen = buffett.screen_company("T", _company())
check("바탕 픽스처는 전부 통과", base_screen.passed_count == len(buffett.CRITERIA),
      base_screen.score_label)

# 1) 회사가 중간에 태그를 바꾼 경우 — 옛 태그에는 옛 연도만 있다
switched = _company(extra={
    "InterestExpense": [_fa("InterestExpense", y, 9) for y in range(2016, 2022)],
    "InterestExpenseNonoperating": [_fa("InterestExpenseNonoperating", y, 9) for y in range(2022, 2026)]})
sw = buffett.screen_company("T", switched)
check("태그를 바꾼 회사 — 최근 연도 이자비용을 읽는다 (전에는 판정 불가)",
      sw.latest.interest_expense == 9 and _verdict(sw, "interest_cover").verdict == "pass",
      _verdict(sw, "interest_cover").detail)
check("합칠 때 앞 후보가 우선 — 같은 해에 둘 다 있으면 첫 태그",
      [f.val for f in _company(extra={
          "InterestExpenseNonoperating": [_fa("InterestExpenseNonoperating", 2025, 99)]})
       .annual_merged(buffett.TAGS["interest_expense"])][-1] == 9)

# 2) '최근 12개월' 구간이 섞인 회사 (아마존 · 유틸리티)
ttm = _company(extra={"NetIncomeLoss": [_fa("NetIncomeLoss", y, 200) for y in range(2016, 2026)] + [
    _fa("NetIncomeLoss", 2025, 210, form="10-Q", start=f"{y}-{m}", end=e)
    for y, m, e in (("2024", "04-01", "2025-03-31"), ("2024", "07-01", "2025-06-30"),
                    ("2024", "10-01", "2025-09-30"), ("2025", "04-01", "2026-03-31"),
                    ("2025", "07-01", "2026-06-30"), ("2025", "10-01", "2026-09-30"))]})
tt = buffett.screen_company("T", ttm)
check("회계연도 말만 연도 축으로 — 12개월짜리 분기 말 구간은 뺀다",
      [r.end for r in tt.years] == [f"{y}-12-31" for y in range(2016, 2026)]
      and tt.passed_count == len(buffett.CRITERIA), str([r.end for r in tt.years][-4:]))
w53 = [_fa("NetIncomeLoss", y, 1, end=e) for y, e in ((2023, "2023-12-30"), (2024, "2024-12-28"))]
w53.append(_fa("NetIncomeLoss", 2025, 1, form="8-K", end="2026-01-03"))
check("52 · 53주 회계연도 · 8-K 로 다시 낸 연도도 받는다",
      buffett.fiscal_year_ends(w53) == {"2023-12-30", "2024-12-28", "2026-01-03"})
check("연간 보고서 양식이 없으면 가르지 않는다 (None)",
      buffett.fiscal_year_ends([_fa("NetIncomeLoss", 2025, 1, form="")]) is None)

# 3) 이자비용을 따로 안 적는 회사 — 현금흐름표의 '낸 이자'
paid = buffett.screen_company("T", _company(
    drop=("InterestExpense",),
    extra={"InterestPaidNet": [_fa("InterestPaidNet", y, 10) for y in range(2016, 2026)]}))
c_paid = _verdict(paid, "interest_cover")
check("낸 이자로 대신 계산하고 그렇게 적는다",
      c_paid.verdict == "pass" and "낸 이자" in c_paid.detail and near(c_paid.value, 26.0),
      c_paid.detail)

# 4) 빚이 없는 회사 — 부채 · 이자 계정이 아예 없다
nodebt_facts = _company(drop=("InterestExpense", "LongTermDebtNoncurrent"))
nd = buffett.screen_company("T", nodebt_facts)
check("무차입 — 부채 · 이자보상 기준을 통과로 보되 추정이라고 경고",
      _verdict(nd, "low_debt").verdict == "pass" and _verdict(nd, "interest_cover").verdict == "pass"
      and "추정" in _verdict(nd, "low_debt").warning and _verdict(nd, "low_debt").value_label == "무차입")
neg = buffett.screen_company("T", _company(
    drop=("InterestExpense", "LongTermDebtNoncurrent"),
    extra={"InterestIncomeExpenseNet": [_fa("InterestIncomeExpenseNet", y, -30) for y in range(2016, 2026)]}))
check("순이자가 마이너스면 무차입으로 보지 않는다 (판정 불가 유지)",
      _verdict(neg, "low_debt").verdict == "unknown" and _verdict(neg, "interest_cover").verdict == "unknown")
kr_like = buffett.Screen(ticker="K", years=nd.years)
buffett.run_checks(kr_like)
check("무차입 추정은 미국(SEC) 심사에서만 — 다른 경로는 판정 불가 그대로",
      _verdict(kr_like, "low_debt").verdict == "unknown")

# 5) 자본이 마이너스인 회사 (자사주 매입)
negeq = buffett.screen_company("T", _company(extra={
    "StockholdersEquity": [_fi("StockholdersEquity", y, -100) for y in range(2016, 2026)]}))
c_neg = _verdict(negeq, "low_debt")
check("자본이 마이너스 — 순이익 몇 년치로 판정 (전에는 판정 불가)",
      c_neg.verdict == "pass" and "마이너스" in c_neg.detail and near(c_neg.value, 1.0), c_neg.detail)
heavy = buffett.screen_company("T", _company(extra={
    "StockholdersEquity": [_fi("StockholdersEquity", y, -100) for y in range(2016, 2026)],
    "LongTermDebtNoncurrent": [_fi("LongTermDebtNoncurrent", y, 2000) for y in range(2016, 2026)]}))
check("자본이 마이너스이고 빚이 순이익 10년치면 미달", _verdict(heavy, "low_debt").verdict == "fail")

# 6) 세전이익을 국내 · 해외로만 적는 회사 / 매출원가가 없는 회사
split = buffett.screen_company("T", _company(
    drop=("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    extra={"IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic":
               [_fa("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic", y, 151) for y in range(2016, 2026)],
           "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign":
               [_fa("IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign", y, 100) for y in range(2016, 2026)]}))
check("세전이익 = 국내 + 해외", split.latest.pretax_income == 251
      and "pretax_domestic" not in split.missing_tags and _verdict(split, "roic").verdict == "pass")
bank = buffett.screen_company("T", _company(drop=("GrossProfit",)))
check("매출원가를 안 적는 회사 — '해당 없음' 이라고 적는다 (통과로 세지 않음)",
      _verdict(bank, "stable_margin").verdict == "unknown"
      and "해당 없음" in _verdict(bank, "stable_margin").detail)
check("조사에서 나온 태그가 후보에 있다",
      "InterestExpenseNonoperating" in buffett.TAGS["interest_expense"]
      and "RevenuesNetOfInterestExpense" in buffett.TAGS["revenue"]
      and "InterestPaidNet" in buffett.KEEP_TAGS
      and "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities" in buffett.TAGS["long_term_debt"])

print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
