"""
Hyperliquid 에 상장된 무기한선물 심볼을 조회합니다.

주식 무기한선물은 Hyperliquid 본체가 아니라 HIP-3 빌더(trade.xyz 등)가
별도 dex 로 배포합니다. 그래서 dex 를 먼저 찾고, dex 별 universe 를 봅니다.

실행:
    cd stock_dashboard
    python -m tools.discover_hyperliquid                  # dex 목록 + 전체 심볼
    python -m tools.discover_hyperliquid --dex xyz        # 특정 dex 만
    python -m tools.discover_hyperliquid SKH SMSN KR200   # 키워드 필터

config.py 의 심볼은 "dex:COIN" 형태로 적습니다 (예: "xyz:SKHX").
"""

from __future__ import annotations

import sys

from sources import hyperliquid


def _print_grid(names: list[str], indent: str = "  ") -> None:
    if not names:
        return
    width = max(len(n) for n in names) + 3
    per_row = max(1, 100 // width)
    for i in range(0, len(names), per_row):
        print(indent + "".join(n.ljust(width) for n in names[i : i + per_row]))


def main(argv: list[str]) -> int:
    args = argv[1:]

    only_dex: str | None = None
    if "--dex" in args:
        idx = args.index("--dex")
        if idx + 1 >= len(args):
            print("--dex 뒤에 dex 이름을 주십시오.", file=sys.stderr)
            return 2
        only_dex = args[idx + 1]
        args = args[:idx] + args[idx + 2 :]

    keywords = [a.upper() for a in args if not a.startswith("-")]

    # ── dex 목록 ──────────────────────────────────────────────────────────────
    try:
        dexes = hyperliquid.list_dexes()
    except hyperliquid.HyperliquidError as exc:
        print(f"perpDexs 조회 실패: {exc}", file=sys.stderr)
        return 1

    print(f"배포된 perp dex: {len(dexes)}개\n")
    for entry in dexes:
        name = entry.get("name", "")
        full = entry.get("fullName") or ""
        shown = name if name else "(기본)"
        print(f"  {shown:<14} {full}")
    print()

    targets = [d.get("name", "") for d in dexes]
    if only_dex is not None:
        if only_dex not in targets:
            print(
                f"dex '{only_dex}' 를 perpDexs 에서 찾지 못했습니다. "
                f"위 목록에 있는 이름을 쓰십시오.",
                file=sys.stderr,
            )
            return 1
        targets = [only_dex]

    # ── dex 별 universe ──────────────────────────────────────────────────────
    total = 0
    hits: list[str] = []

    for dex in targets:
        try:
            universe = hyperliquid.list_universe(dex)
        except hyperliquid.HyperliquidError as exc:
            print(f"── dex={dex or '(기본)'} : 조회 실패 — {exc}\n")
            continue

        names = [
            e.get("name", "")
            for e in universe
            if isinstance(e, dict) and e.get("name")
        ]
        total += len(names)

        shown = names
        if keywords:
            shown = [n for n in names if any(k in n.upper() for k in keywords)]

        label = dex or "(기본)"
        if keywords:
            print(f"── dex={label} : 전체 {len(names)}개 중 키워드 일치 {len(shown)}개")
        else:
            print(f"── dex={label} : {len(names)}개")

        _print_grid(sorted(shown))
        print()

        prefix = f"{dex}:" if dex else ""
        hits.extend(f"{prefix}{n}" for n in shown)

    print("=" * 72)
    print(f"전체 상장 심볼 {total}개")

    if keywords and hits:
        print(f"\nconfig.py 에 넣을 형태 (키워드 {', '.join(keywords)} 일치):")
        for h in sorted(hits):
            print(f'    Instrument("이름", "{h}", "hyperliquid", "trade.xyz", "USD"),')
    elif keywords:
        print("\n키워드와 일치하는 심볼이 없습니다. 상장 폐지되었거나 표기가 다를 수 있습니다.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
