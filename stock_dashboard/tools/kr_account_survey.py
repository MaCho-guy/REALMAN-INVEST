"""
국내 재무 계정 조사 — '판정 불가' 가 왜 나는지 **전 종목의 실제 DART 응답**으로 셉니다.

    python stock_dashboard/tools/kr_account_survey.py            # 코스피200 + 코스닥150
    python stock_dashboard/tools/kr_account_survey.py --limit 40

2026-11-12 첫 한국 전수 심사: 판정의 30.5% 가 '판정 불가', 그중 주주이익 · 설비투자
기준은 331개 회사 중 265개에서 판정 불가였습니다. 미국에서 한 것(tools/tag_survey.py)과
같은 방식으로, 최근 사업보고서 한 건씩만 받아:
  1) 규칙(buffett_kr.KR_RULES)으로 못 찾은 계정을 세고,
  2) 그 회사의 같은 재무제표에서 같은 뜻으로 보이는 계정 이름을 모아 셉니다.
화면 · 데이터 파일은 건드리지 않고 표만 찍습니다. DART 요청은 종목당 1~2건입니다.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buffett_kr  # noqa: E402
import config  # noqa: E402
import universe  # noqa: E402
from sources import dart, universe_src  # noqa: E402

#: 계정마다 '같은 뜻으로 보이는 이름' 을 찾는 정규식 (넓게 잡고 사람이 고릅니다).
PATTERNS = {
    "dep_amort": r"상각",
    "capex": r"유형자산|설비",
    "long_term_debt": r"차입|사채",
    "short_term_debt": r"차입|유동성",
    "cost_of_revenue": r"원가",
    "gross_profit": r"매출총",
    "revenue": r"매출|수익",
    "operating_income": r"영업이익|영업손익",
    "interest_expense": r"이자|금융비용|금융원가",
    "tax_expense": r"법인세",
    "pretax_income": r"법인세.*차감|세전",
    "operating_cash_flow": r"영업활동",
    "net_income": r"순이익|순손익",
    "equity": r"자본",
    "cash": r"현금",
}


def survey_one(accounts) -> dict:
    """한 회사의 최근 사업보고서 — {key: [(재무제표, 계정명, 계정ID), …]} (못 찾은 계정만)."""
    out = {}
    for rule in buffett_kr.KR_RULES:
        hit = buffett_kr.find_account(accounts, rule)
        if hit is not None and hit.thstrm_amount is not None:
            continue
        pat = re.compile(PATTERNS.get(rule.key, re.escape(rule.label)))
        out[rule.key] = [(a.sj_div, a.account_nm.strip(), a.account_id) for a in accounts
                         if (not rule.sj or a.sj_div in rule.sj) and pat.search(a.account_nm)
                         and a.thstrm_amount is not None]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    members, rules = universe_src.fetch_kr_members()
    cands = [(m["code"], m["name"]) for m in universe.merge_members(members)]
    if args.limit:
        cands = cands[:args.limit]
    corp_map = dart.fetch_corp_codes()
    year = dart.latest_available_quarter()[0] - 1
    print(f"조사 대상 {len(cands)}종목 · 사업보고서 {year}년 · 규칙 {rules}")

    def one(item):
        code, name = item
        corp = dart.resolve_corp_code(code, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if not corp:
            return code, name, None, "고유번호 없음", ""
        last = ""
        for fs in ("CFS", "OFS"):                 # 연결이 없으면 별도
            for y in (year, year - 1):
                try:
                    return code, name, dart.fetch_financials(corp, y, "FY", fs_div=fs), "", f"{fs} {y}"
                except dart.DartError as exc:
                    last = re.sub(r"\d{6,}", "N", str(exc))[:70]
        return code, name, None, last, ""

    miss = collections.Counter()
    none_at_all = collections.Counter()
    found = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    fails = collections.Counter()
    fail_names = []
    got_how = collections.Counter()
    sj_seen = collections.Counter()
    n_ok = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for code, name, accounts, err, how in pool.map(one, cands):
            if accounts is None:
                fails[err] += 1
                if len(fail_names) < 25:
                    fail_names.append(name)
                continue
            n_ok += 1
            got_how[how] += 1
            for sj in {a.sj_div for a in accounts}:
                sj_seen[sj] += 1
            for key, cs in survey_one(accounts).items():
                miss[key] += 1
                if not cs:
                    none_at_all[key] += 1
                    if len(examples[key]) < 8:
                        examples[key].append(name)
                for sj, nm, aid in cs:
                    found[key][f"{sj} | {nm} | {aid[:60]}"] += 1

    print(f"\n받은 회사 {n_ok} · 못 받은 회사 {sum(fails.values())}")
    print("  받은 방식:", dict(got_how))
    print("  재무제표 종류별 회사 수:", dict(sj_seen))
    for err, n in fails.most_common(6):
        print(f"  못 받음 {n}: {err}")
    print("  못 받은 회사 예:", ", ".join(fail_names))
    print("\n계정별 — 규칙으로 못 찾은 회사 수 / 비슷한 이름도 없는 회사 수")
    for key, n in miss.most_common():
        print(f"\n[{key}] 못 찾음 {n} · 비슷한 이름 없음 {none_at_all[key]}"
              f" (예: {', '.join(examples[key])})")
        for line, c in found[key].most_common(16):
            print(f"    {c:4d}  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
