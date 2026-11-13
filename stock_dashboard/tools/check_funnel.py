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
import integrate  # noqa: E402
import kr_screen  # noqa: E402
import universe  # noqa: E402

FILES = ("universe_us", "funnel_us", "funnel_kr", "chart_us", "chart_kr", "universe_kr")


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


def check_kr_extra(d: dict) -> list[str]:
    """거래 스크리너(순위 기준) 종목 수 · 통합 후보."""
    bad: list[str] = []
    u = d["universe_kr"]
    profiles = universe.restore(kr_screen.VolProfile, u.get("profiles"))
    values = universe.restore(kr_screen.ValueRow, u.get("values"))
    th = kr_screen.adaptive_thresholds(profiles, values)
    hits = kr_screen.adaptive_hits(profiles, values, th)
    fk = d["funnel_kr"]
    scr = {s["t"]: buffett.from_summary(s) for s in fk.get("screens") or []}
    print("\n[KR 거래 스크리너 — 순위 기준]")
    for k, lst in hits.items():
        qn = sum(1 for h in lst if scr.get(h.ticker) is not None
                 and (buffett.passes_kr(scr[h.ticker]) or buffett.held_back_kr(scr[h.ticker])))
        print(f"  {k:12} {len(lst):3}종목 · 품질 통과·보류 {qn}")
        if not 5 <= len(lst) <= 25:
            print(f"    (참고) 목표 5~25 밖")
    frows = {r["t"]: r for r in fk.get("rows") or []}
    items = d["chart_kr"].get("rows") or []
    rows = {r.ticker: r for r in (chart_signals.row_from_dict(x) for x in items) if r}
    cands = integrate.build(fk.get("screens") or [], frows, rows, hits,
                            {x["ticker"] for x in items if x.get("s")},
                            {x["ticker"] for x in items if x.get("new")})
    picks, out = integrate.split(cands)
    print(f"\n[KR 통합 후보] 품질 통과 {len(cands)} → 후보 {len(picks)} · 빠짐 {len(out)}")
    lamp = {"g": "●", "y": "◐", "r": "✕", "-": "○"}
    for i, c in enumerate(picks[:integrate.MAX_PICKS], 1):
        ls = " ".join(f"{n}{lamp[c.lamps[k]]}" for k, n in
                      (("quality", "품질"), ("price", "가격"), ("eps", "EPS")))
        print(f"  {i:2}. {c.name[:12]:12} {c.ticker} 근거 {c.greens}/3 · {ls}"
              f"{' · 타이밍' if c.timing else ''}")
        print(f"      가격: {c.notes['price']} | EPS: {c.notes['eps']} | 차트: {c.notes['chart']}")
        if c.excluded or c.lamps["quality"] != "g":
            bad.append(f"통합 후보 {c.ticker} 가 관문을 통과하지 않았는데 후보에 있음")
    for c in out:
        print(f"  빠짐: {c.name[:12]:12} {c.ticker} — {c.excluded}")
        if c.lamps["price"] != "r" and not funnel.eps_down(frows.get(c.ticker, {}).get("f")):
            bad.append(f"{c.ticker} 가 이유 없이 빠짐")
    keys = [c.sort_key() for c in picks]
    if keys != sorted(keys):
        bad.append("통합 후보 순서가 규칙과 다름")
    return bad


def check_growth(d: dict) -> list[str]:
    """성장형 (11/13) — 심사 묶음에 gr 이 있으면 시장마다 후보 수 · 앞 5종목."""
    import growth  # noqa: PLC0415
    bad: list[str] = []
    for market, uni, fun, ch in (("us", "universe_us", "funnel_us", "chart_us"),
                                 ("kr", "funnel_kr", "funnel_kr", "chart_kr")):
        screens = d[uni].get("screens") or []
        have = sum(1 for x in screens if x.get("gr"))
        print(f"\n[{market.upper()} 성장형] 성장 지표 있는 종목 {have}/{len(screens)}")
        if not have:
            print("  (수집기가 새 기준으로 다시 심사하기 전 — 건너뜀)")
            continue
        fix = (lambda t: t) if market == "kr" else (lambda t: str(t).replace("-", "."))
        rows = {fix(r.ticker): r for r in (chart_signals.row_from_dict(x)
                                            for x in d[ch].get("rows") or []) if r}
        frows = {r["t"]: r for r in d[fun].get("rows") or []}
        gpass = [x for x in screens if growth.passes(x.get("gr"), market)]
        nof = [x["t"] for x in gpass if x["t"] not in frows]
        cands = integrate.build_growth(screens, frows, rows, market=market)
        p, o = integrate.split(cands)
        print(f"  성장 품질 통과 {len(gpass)} → 후보 {len(p)} · 빠짐 {len(o)}"
              f" · 가격 · EPS 줄 없음 {len(nof)}")
        if nof:
            bad.append(f"{market}: 성장 품질 통과인데 깔때기 줄 없음 {nof[:8]}")
        for i, c in enumerate(p[:5], 1):
            print(f"   {i}. {c.name[:16]:16} {c.ticker} {c.greens}/3 · {c.notes['price'][:40]}"
                  f" | {c.notes['eps']}")
        td = sum(1 for x in screens if (x.get("gr") or {}).get("td"))
        print(f"  실적 추세 악화(td) {td}종목")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    a = ap.parse_args()
    d = {n: load(n, a.dir) for n in FILES}
    bad = (check_market("us", d) + check_market("kr", d) + check_kr_extra(d)
           + check_growth(d))
    print()
    for b in bad:
        print("틀림:", b)
    print("통과" if not bad else f"틀림 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
