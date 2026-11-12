"""
재무 태그 조사 — '판정 불가' 가 왜 나는지 **전 종목의 실제 응답**으로 셉니다.

    python stock_dashboard/tools/tag_survey.py            # S&P 500 + 나스닥100 전부
    python stock_dashboard/tools/tag_survey.py --limit 60

하는 일 (화면·데이터 파일은 건드리지 않고 표만 찍습니다):
  1) 지금 방식(buffett.build_years)으로 연도별 숫자를 만들고, **가장 최근 연도**에
     비어 있는 계정을 셉니다.
  2) 비어 있는 계정마다, 그 회사의 companyfacts 안에서 같은 뜻으로 보이는 태그 가운데
     **그 연도말에 값이 있는 것**을 찾아 태그별로 셉니다 — 후보에 무엇을 더할지의 근거.
  3) 이미 후보에 있는 태그를 '첫 번째로 찾은 것 하나' 가 아니라 **연도별로 합쳤다면**
     채워졌을 건수도 셉니다.

2026-11-12: 전수 심사에서 판정의 33% 가 '판정 불가' 였습니다. 태그 후보를 추측으로
늘리지 않으려고 만든 도구입니다 (TAGS 머리말: '아직 실제 응답으로 검증하지 않았습니다').
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buffett  # noqa: E402
import config  # noqa: E402
import universe  # noqa: E402
from sources import edgar, edgar_facts, universe_src  # noqa: E402

#: 계정마다 '같은 뜻으로 보이는 태그' 를 찾는 정규식 (넓게 잡고 사람이 고릅니다).
PATTERNS = {
    "net_income": r"^(NetIncomeLoss|ProfitLoss|IncomeLossFromContinuingOperations$)",
    "revenue": r"Revenue|^Sales",
    "gross_profit": r"^GrossProfit",
    "cost_of_revenue": r"^CostOf|^CostsAndExpenses$|^CostDirect",
    "operating_income": r"^OperatingIncomeLoss|IncomeLossFromContinuingOperationsBefore",
    "interest_expense": r"Interest.*Expense|InterestExpense|InterestPaid|InterestCost",
    "tax_expense": r"^IncomeTaxExpenseBenefit|^IncomeTaxesPaid",
    "pretax_income": r"IncomeLossFromContinuingOperationsBefore|IncomeLossBeforeIncomeTax",
    "dep_amort": r"Depreciation|Amortization",
    "capex": r"^PaymentsToAcquire|^PaymentsFor.*(Property|Capital|Construction)|CapitalExpenditure",
    "operating_cash_flow": r"^NetCashProvidedByUsedInOperatingActivities",
    "equity": r"^StockholdersEquity|^PartnersCapital$|^MembersEquity$",
    "long_term_debt": (r"LongTermDebt|LongTermNotes|^SeniorNotes|^NotesPayable|LongTermBorrowings"
                       r"|DebtAndCapitalLease|DebtLongtermAndShorttermCombinedAmount"
                       r"|^UnsecuredDebt|^SecuredDebt|^DebtInstrumentCarryingAmount|^OtherLongTermDebt"),
    "liabilities": r"^Liabilities",
    "short_term_debt": r"DebtCurrent|ShortTermBorrowings|CommercialPaper|NotesPayableCurrent",
}


def _near(end_a: str, end_b: str, days: int = 7) -> bool:
    try:
        return abs((dt.date.fromisoformat(end_a) - dt.date.fromisoformat(end_b)).days) <= days
    except ValueError:
        return False


def tags_with_value(facts, key: str, end: str) -> list[str]:
    """이 회사가 그 연도말에 값을 낸 태그 가운데 key 와 같은 뜻으로 보이는 것."""
    pat = re.compile(PATTERNS[key])
    flow = key in buffett.FLOW_KEYS
    out = []
    for tag, rows in facts.by_tag.items():
        if not pat.search(tag):
            continue
        if flow:
            hit = any(f.is_annual and f.end == end for f in rows)
        else:
            hit = any(f.is_instant and _near(f.end, end) for f in rows)
        if hit:
            out.append(tag)
    return out


def survey_one(facts) -> dict:
    """한 회사 — {rows: 연도 수, end, missing: {key: [그 연도에 값이 있는 태그]}, merged: [...]}."""
    rows, _missing = buffett.build_years(facts)
    if not rows:
        return {"rows": 0}
    latest = rows[-1]
    out = {"rows": len(rows), "end": latest.end, "missing": {}, "merge": [], "gaps": {}}
    for key in PATTERNS:
        if not hasattr(latest, key):
            continue
        out["gaps"][key] = sum(1 for r in rows if getattr(r, key) is None)
        if getattr(latest, key) is not None:
            continue
        found = tags_with_value(facts, key, latest.end)
        out["missing"][key] = found
        if any(t in buffett.TAGS.get(key, ()) for t in found):
            out["merge"].append(key)
    return out


def describe_empty(facts) -> str:
    """연도 축을 못 만든 회사 — 순이익·매출로 보이는 태그가 무엇을 갖고 있는지."""
    pat = re.compile(PATTERNS["net_income"] + "|" + PATTERNS["revenue"])
    parts = []
    for tag, rows in sorted(facts.by_tag.items()):
        if not pat.search(tag):
            continue
        ann = [f for f in rows if f.is_annual]
        last = max((f.end for f in rows), default="")
        parts.append(f"{tag}: {len(rows)}건 · 연간 {len(ann)}건 · 마지막 {last}")
    return " | ".join(parts[:10]) or f"순이익·매출 태그 없음 (USD 태그 {len(facts.by_tag)}개 · 전체 {facts.total_tags}개)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=24)
    args = ap.parse_args()

    members, rules = universe_src.fetch_us_members()
    tmap = edgar.fetch_ticker_map(config.EDGAR_USER_AGENT)
    by_cik: dict[int, str] = {}
    for m in universe.merge_members(members):
        t = m["ticker"]
        cik = m.get("cik") or tmap.get(t) or tmap.get(t.replace(".", "-"))
        if cik:
            by_cik.setdefault(int(cik), t)
    todo = [(t, c) for c, t in by_cik.items()]
    if args.limit:
        todo = todo[:args.limit]
    print(f"조사 대상 {len(todo)}종목 · 규칙 {rules}")

    n_ok = 0
    miss = collections.Counter()
    none_at_all = collections.Counter()
    merge = collections.Counter()
    found = collections.defaultdict(collections.Counter)
    gaps = collections.Counter()
    year_hist = collections.Counter()
    examples = collections.defaultdict(list)
    empties, errors = [], {}
    for i in range(0, len(todo), args.batch):
        batch = dict(todo[i:i + args.batch])
        got, errs = edgar_facts.fetch_many(batch, config.EDGAR_USER_AGENT, keep=None)
        errors.update(errs)
        for ticker, facts in got.items():
            r = survey_one(facts)
            if not r["rows"]:
                empties.append(f"{ticker}: {describe_empty(facts)}")
                continue
            n_ok += 1
            year_hist[r["rows"]] += 1
            for key, n in r["gaps"].items():
                gaps[key] += n
            for key, tags in r["missing"].items():
                miss[key] += 1
                if not tags:
                    none_at_all[key] += 1
                    if len(examples[key]) < 8:
                        examples[key].append(ticker)
                for tag in tags:
                    found[key][tag] += 1
            for key in r["merge"]:
                merge[key] += 1
        del got
        print(f"  {min(i + args.batch, len(todo))}/{len(todo)}", flush=True)

    print(f"\n연도 축을 만든 회사 {n_ok} · 못 만든 회사 {len(empties)} · 못 받은 회사 {len(errors)}")
    print("연도 수 분포:", sorted(year_hist.items()))
    for line in empties:
        print("  연도 없음 —", line[:600])
    for t, e in list(errors.items())[:10]:
        print("  못 받음 —", t, e[:120])
    print("\n계정별 — 최근 연도에 빈 회사 수 / 후보를 합치기만 해도 채워지는 수 / 비슷한 태그도 없는 수")
    for key, n in miss.most_common():
        print(f"\n[{key}] 최근 연도 빔 {n} · 합치면 채움 {merge[key]} · 비슷한 태그 없음 {none_at_all[key]}"
              f" (예: {', '.join(examples[key])}) · 10년 중 빈 칸 합계 {gaps[key]}")
        for tag, c in found[key].most_common(14):
            mark = "✓후보" if tag in buffett.TAGS.get(key, ()) else "     "
            print(f"    {c:4d} {mark} {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
