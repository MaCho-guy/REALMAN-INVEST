"""깔때기 · 오늘 볼 종목 점검 — data 브랜치 파일로 화면과 같은 규칙을 다시 셉니다.

    python tools/check_funnel.py              # git 의 data 브랜치에서 읽음 (git fetch origin data:data 먼저)
    python tools/check_funnel.py --dir 경로    # 받아 둔 JSON 폴더에서 읽음

나오는 것 (시장마다): 후보 → 품질 통과(화면 규칙) → 가격 내역 → 오늘 볼 종목.
'틀림' 줄이 하나라도 나오면 종료 코드 1 — 아래 검사:
  · 오늘 볼 종목의 모든 종목이 품질 통과 집합 안에 있다
  · 오늘 볼 종목의 모든 종목에 가격 판정이 붙어 있다 (가격 높음도 빠지지 않는다)
  · 국내 품질 통과 종목은 전부 깔때기 파일에 가격 · 차트 줄이 있다 (미리 계산 범위 안)
  · 순위에서 같은 비율 · 같은 통과 수끼리는 선행 EPS 90일이 큰 순
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import buffett  # noqa: E402
import chart_signals  # noqa: E402
import funnel  # noqa: E402

FILES = ("universe_us", "funnel_us", "funnel_kr", "chart_us", "chart_kr")


def load(name: str, folder: str | None) -> dict:
    if folder:
        with open(os.path.join(folder, f"{name}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    out = subprocess.run(["git", "show", f"data:{name}.json"], cwd=HERE,
                         capture_output=True, check=True)
    return json.loads(out.stdout)


def check_market(market: str, d: dict) -> list[str]:
    bad: list[str] = []
    screens = (d["universe_us"] if market == "us" else d["funnel_kr"]).get("screens") or []
    frows = {r["t"].replace(".", "-"): r for r in d[f"funnel_{market}"].get("rows") or []}
    quality = funnel.quality_tickers(screens, market)
    scs = [x for x in (buffett.from_summary(s) for s in screens) if x and x.ok]
    print(f"\n[{market.upper()}] 심사 {len(screens)} · 재무 받음 {len(scs)} · "
          f"품질 통과(화면 규칙) {len(quality)} · 깔때기 파일 줄 {len(frows)}")
    if market == "kr":
        old = sum(1 for x in scs if buffett.passes(x, 7, by_ratio=True))
        held = sum(1 for x in scs if buffett.held_back_kr(x))
        print(f"  예전 규칙(판정 중 7/9) {old} · 증거 부족 보류 {held}")
    missing = sorted(quality - set(frows))
    if missing:
        bad.append(f"{market}: 품질 통과인데 깔때기 줄이 없음 {missing[:10]}")
    b = funnel.breakdown([frows.get(t) for t in quality])
    print("  " + funnel.breakdown_text(b, len(quality)).replace("<b>", "").replace("</b>", ""))

    # 순위 — 동점끼리 EPS 순
    eps = {t: ((r.get("f") or {}).get("c90")) for t, r in frows.items()}
    ranked = buffett.rank_with_eps([x for x in scs if x.ticker.replace(".", "-") in quality],
                                   {k.replace("-", "."): v for k, v in eps.items()} | eps)
    for a, c in zip(ranked, ranked[1:]):
        if (a.judged_ratio, a.passed_count) == (c.judged_ratio, c.passed_count):
            ea, ec = eps.get(a.ticker.replace(".", "-")), eps.get(c.ticker.replace(".", "-"))
            if ea is None and ec is not None or (ea is not None and ec is not None and ea < ec):
                bad.append(f"{market}: 동점 정렬 어긋남 {a.ticker}({ea}) 앞 {c.ticker}({ec})")

    # 오늘 볼 종목
    items = d[f"chart_{market}"].get("rows") or []
    rows = [r for r in (chart_signals.row_from_dict(x) for x in items) if r is not None]
    new = {str(x.get("ticker")) for x in items if x.get("new")}
    semis = {str(x.get("ticker")) for x in items if x.get("s")}
    picks = chart_signals.today_picks(rows, quality, set(), semis, new)
    loose = chart_signals.today_picks(rows, set(frows), set(), semis, new)
    print(f"  오늘 볼 종목 {len(picks)} (예전처럼 깔때기 줄 전부를 쓰면 {len(loose)})")
    for r in picks[:10]:
        fr = frows.get(r.ticker) or {}
        state = funnel.price_state(fr.get("p"))
        gap = funnel.gap_text(fr.get("p"))
        warn = " · EPS 하향 경고" if funnel.eps_down(fr.get("f")) else ""
        print(f"    {r.ticker:8} {r.name[:14]:14} 가격 {state:5} {gap}"
              f" · {funnel.eps_chip(fr.get('f')) or '선행 EPS 추정 없음'}{warn}")
        if r.ticker not in quality:
            bad.append(f"{market}: 오늘 볼 종목 {r.ticker} 가 품질 통과가 아님")
        if r.ticker not in frows:
            bad.append(f"{market}: 오늘 볼 종목 {r.ticker} 에 가격 판정 줄이 없음")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    a = ap.parse_args()
    d = {n: load(n, a.dir) for n in FILES}
    bad = check_market("us", d) + check_market("kr", d)
    print()
    for b in bad:
        print("틀림:", b)
    print("통과" if not bad else f"틀림 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
