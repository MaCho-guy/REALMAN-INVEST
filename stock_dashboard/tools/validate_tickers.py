"""
config.py 에 정의된 모든 티커가 실제로 응답하는지 확인합니다.

실행:
    cd stock_dashboard
    python -m tools.validate_tickers

대체 심볼(alt_symbols)이 있으면 1순위 실패 시 자동으로 시도하고,
어느 심볼로 성공했는지 표시합니다.

종료 코드: 0 = 전부 통과, 1 = 하나 이상 실패
"""

from __future__ import annotations

import sys

import config
from compute import pick_quote
from sources import hyperliquid, naver, yahoo

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def _fetch_all() -> dict[str, dict]:
    print("조회 중… (심볼 수에 따라 1분 이상 걸릴 수 있습니다)\n")
    out: dict[str, dict] = {}

    yahoo_syms = config.all_yahoo_symbols()
    print(f"  야후 파이낸스  {len(yahoo_syms)}개 (대체 심볼 포함)")
    out["yahoo"] = yahoo.fetch_quotes(yahoo_syms)

    naver_codes = config.all_naver_codes()
    print(f"  네이버 금융    {len(naver_codes)}개")
    out["naver"] = naver.fetch_quotes(naver_codes)

    hl_syms = config.all_hyperliquid_symbols()
    print(f"  Hyperliquid   {len(hl_syms)}개")
    out["hyperliquid"] = hyperliquid.fetch_quotes(hl_syms)

    print()
    return out


def main() -> int:
    data = _fetch_all()
    failures: list[tuple[str, str, str]] = []
    unverified_ok: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for section in config.SECTIONS:
        print(f"{DIM}── {section.title} {'─' * max(0, 46 - len(section.title))}{RESET}")
        for inst in section.instruments:
            if (inst.source, inst.symbol) in seen:
                continue
            seen.add((inst.source, inst.symbol))

            quote = pick_quote(inst, data)
            flag = "" if inst.verified else f" {YELLOW}[미검증]{RESET}"

            if quote is not None and quote.ok:
                price = f"{quote.price:,.4f}".rstrip("0").rstrip(".")
                cur = quote.currency or inst.currency
                via = quote.extra.get("fallback")
                via_text = f" {DIM}via {via}{RESET}" if via else ""
                print(
                    f"  {GREEN}OK  {RESET}{inst.name:<24} {inst.symbol:<14} "
                    f"{price} {cur}{via_text}{flag}"
                )
                if not inst.verified:
                    unverified_ok.append((inst.name, inst.symbol, f"{price} {cur}"))
            else:
                reason = (quote.error if quote is not None else "조회 결과 없음") or "원인 불명"
                print(
                    f"  {RED}FAIL{RESET}{inst.name:<24} {inst.symbol:<14} "
                    f"{DIM}{reason[:66]}{RESET}"
                )
                failures.append((section.title, f"{inst.name} ({inst.symbol})", reason))
        print()

    total = len(seen)
    ok_count = total - len(failures)
    print("=" * 72)
    print(f"결과: {ok_count}/{total} 통과")

    if failures:
        print(f"\n{RED}실패 — config.py 에서 티커를 고치거나 해당 Instrument 를 지우십시오:{RESET}")
        for section_title, label, reason in failures:
            print(f"  · [{section_title}] {label}")
            print(f"      {DIM}{reason}{RESET}")

    if unverified_ok:
        print(
            f"\n{YELLOW}통과했으나 verified=False 인 항목{RESET} — "
            f"가격이 타당한지 눈으로 확인한 뒤 config.py 에서 verified=True 로 바꾸십시오:"
        )
        for name, symbol, price in unverified_ok:
            print(f"  · {name:<24} {symbol:<14} {price}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
