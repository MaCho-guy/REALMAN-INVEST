"""성장형 지표 · 판정 (2026-11-13) — 안정형(버핏식 9개 · 역DCF)과 **따로** 봅니다.

사용자: "성장주도 고려해야 하는데, 따로 분류해서 — 보수적인 판단에 영향을 미치면 안 되니까".
버핏식 기준은 10년 내내 꾸준한 성숙 기업에 맞춰져 있고, 역DCF 가격 규칙은 과거 FCF
성장률(최대 15%)로 지금 주가를 설명하려 해서, 빠르게 크는 회사는 두 단계 모두에서
떨어집니다(11/13 실측: NVDA 품질 6/9 · MSFT 가격 높음 +14.6%p · NOW 4/9).

수집기가 심사 직후(10년 숫자가 메모리에 있을 때) `metrics()` 로 숫자를 뽑아 심사 묶음에
`gr` 키로 싣고, 화면은 `checks()` · `passes()` 로 판정만 합니다.

성장 품질 7개 (7개 중 GROWTH_MIN_PASS 개 이상이면 통과, 판정 불가는 통과로 세지 않음):
  ① 매출 3년 연평균 ≥ 15% (한국 10%)          성장 자체
  ② 매출총이익률 유지 (최근 3년 ≥ 이전 3년 − 1%p) 가격 결정력
  ③ 영업 레버리지 (영업이익 3년 성장 ≥ 매출 3년 성장) 커질수록 남는 구조
  ④ 영업현금흐름 최근 3년 합계 > 0             적자 성장주 거르기
  ⑤ Rule of 40 (매출 성장률 + FCF 마진 ≥ 40, 한국 30) 성장과 수익의 균형
  ⑥ 주식보상비 ÷ 매출 ≤ 15% (계정이 있는 회사)  주주 희석 대리 지표
  ⑦ 재무 안전 (순현금 또는 부채/자본 ≤ 1, 이자보상 ≥ 5배)

가격은 PEG = 선행 PER ÷ 내년 EPS 예상 성장률(%) — 과거 FCF 가 아니라 예상 성장 대비 가격.
문턱값은 흔히 쓰는 출발점이지 검증된 값이 아닙니다 — 실제 분포를 보고 조정합니다.
"""
from __future__ import annotations

REV_MIN = {"us": 0.15, "kr": 0.10}
RULE40_MIN = {"us": 40.0, "kr": 30.0}
GM_TOL = 0.01                    # 매출총이익률 허용 하락 (1%p)
SBC_REV_MAX = 0.15
DEBT_EQUITY_MAX = 1.0
ICOV_MIN = 5.0
GROWTH_MIN_PASS = 6   # 11/13 17:02 사용자 승인 (5 → 6) — 5개면 미국 83 · 한국 28, 6개면 22 · 9
#: PEG 판정 — 이하면 충족 · 보통, 넘으면 주의(후보에서 뺌)
PEG_GOOD, PEG_OK = 1.5, 2.5
#: 마진 추세 — 최근 3년 영업이익률이 10년 평균보다 이만큼(소수) 넘게 낮으면 '꺾임'
OM_TOL = 0.02
#: 주식보상 부담 — 최근 3년 주식보상비 ÷ FCF 가 이 값 이하면 통과
SBC_FCF_MAX = 0.20

NAMES = {"rev": "매출 3년 성장", "gm": "매출총이익률 유지", "lev": "영업 레버리지",
         "ocf": "영업현금흐름 플러스", "r40": "Rule of 40", "sbc": "주식보상비 부담",
         "safe": "재무 안전"}


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def _cagr(a, b, years):
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return (b / a) ** (1.0 / years) - 1.0


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def metrics(screen) -> dict:
    """심사 결과(Screen)의 연간 숫자 → 성장 지표 사전 (파일에 `gr` 로 실음).

    키: rev3(매출 3년 연평균) · gm3 · gm3p(최근 · 이전 3년 매출총이익률) · op3(영업이익
    3년 연평균) · ocf3(영업현금흐름 3년 합계) · fcfm(FCF 마진 3년 평균) · r40 · sbcr(주식
    보상비 ÷ 매출, 최근 해) · sbcf(3년 주식보상비 ÷ 3년 FCF) · de(장기부채 ÷ 자본) ·
    nc(순현금이면 1, 아니면 0) · icov(이자보상배율) · om3 · om10(영업이익률 최근 3년 ·
    전체 평균) · td(매출 · 영업이익이 둘 다 3년 연속 감소면 1) · n(쓴 연도 수).
    숫자가 모자라면 그 키는 None.
    """
    rows = sorted([y for y in (getattr(screen, "years", None) or [])],
                  key=lambda y: y.year)
    if not rows:
        return {}
    rev = [y.revenue for y in rows]
    op = [y.operating_income for y in rows]

    def gm(y):
        if not y.revenue or y.revenue <= 0:
            return None
        gp = y.gross_profit
        if gp is None and y.cost_of_revenue is not None:
            gp = y.revenue - y.cost_of_revenue
        return None if gp is None else gp / y.revenue

    def om(y):
        if not y.revenue or y.revenue <= 0 or y.operating_income is None:
            return None
        return y.operating_income / y.revenue

    out: dict = {"n": len(rows)}
    if len(rows) >= 4:
        out["rev3"] = _r(_cagr(rev[-4], rev[-1], 3))
        out["op3"] = _r(_cagr(op[-4], op[-1], 3))
        # 둘 다 3년 연속 감소 (4개 점이 다 있어야 판정)
        def down(series):
            s = series[-4:]
            return None if any(v is None for v in s) else all(s[i] > s[i + 1] for i in range(3))
        dr, do = down(rev), down(op)
        out["td"] = None if dr is None or do is None else int(dr and do)
    gms = [gm(y) for y in rows]
    out["gm3"] = _r(_avg(gms[-3:]))
    out["gm3p"] = _r(_avg(gms[-6:-3])) if len(rows) >= 6 else None
    oms = [om(y) for y in rows]
    out["om3"] = _r(_avg(oms[-3:]))
    out["om10"] = _r(_avg(oms))
    last3 = rows[-3:]
    ocf = [y.operating_cash_flow for y in last3]
    out["ocf3"] = None if any(v is None for v in ocf) else _r(sum(ocf), 0)
    fcf = [getattr(y, "free_cash_flow", None) for y in last3]
    rv3 = [y.revenue for y in last3]
    if all(v is not None for v in fcf) and all(v and v > 0 for v in rv3):
        out["fcfm"] = _r(sum(fcf) / sum(rv3))
    if out.get("rev3") is not None and out.get("fcfm") is not None:
        out["r40"] = _r(out["rev3"] * 100 + out["fcfm"] * 100, 1)
    last = rows[-1]
    sbc = getattr(last, "sbc", None)
    if sbc is not None and last.revenue and last.revenue > 0:
        out["sbcr"] = _r(sbc / last.revenue)
    sbcs = [getattr(y, "sbc", None) for y in last3]
    if all(v is not None for v in sbcs) and all(v is not None for v in fcf) and sum(fcf) > 0:
        out["sbcf"] = _r(sum(sbcs) / sum(fcf))
    if last.equity and last.equity > 0 and last.long_term_debt is not None:
        out["de"] = _r(last.long_term_debt / last.equity)
    cash = (last.cash or 0) + (last.short_term_investments or 0)
    debt = (last.long_term_debt or 0) + (last.short_term_debt or 0)
    if last.cash is not None:
        out["nc"] = int(cash > debt)
    ie = last.interest_expense
    if last.operating_income is not None and ie:
        out["icov"] = _r(last.operating_income / abs(ie), 2)
    return {k: v for k, v in out.items() if v is not None}


def safe_metrics(screen) -> dict:
    """수집기용 — 한 회사의 숫자가 이상해도 수집 전체가 멈추지 않게 (실패하면 {})."""
    try:
        return metrics(screen)
    except Exception:  # noqa: BLE001
        return {}


def checks(gr: dict | None, market: str = "us") -> list[tuple[str, str, str, str]]:
    """성장 품질 7개 — [(키, 이름, 'pass'/'fail'/'unknown', 근거 글)]."""
    g = gr or {}
    out = []

    def add(key, state, text):
        out.append((key, NAMES[key], state, text))

    rev3, rmin = g.get("rev3"), REV_MIN.get(market, 0.15)
    add("rev", "unknown" if rev3 is None else ("pass" if rev3 >= rmin else "fail"),
        "매출 4년치 부족" if rev3 is None else f"연 {rev3 * 100:+.1f}% (기준 {rmin * 100:.0f}%↑)")
    gm3, gmp = g.get("gm3"), g.get("gm3p")
    add("gm", "unknown" if gm3 is None or gmp is None else
        ("pass" if gm3 >= gmp - GM_TOL else "fail"),
        "매출총이익 6년치 부족" if gm3 is None or gmp is None else
        f"최근 3년 {gm3 * 100:.1f}% · 이전 3년 {gmp * 100:.1f}%")
    op3 = g.get("op3")
    add("lev", "unknown" if op3 is None or rev3 is None else ("pass" if op3 >= rev3 else "fail"),
        "영업이익 적자 · 부족" if op3 is None or rev3 is None else
        f"영업이익 연 {op3 * 100:+.1f}% · 매출 연 {rev3 * 100:+.1f}%")
    ocf3 = g.get("ocf3")
    add("ocf", "unknown" if ocf3 is None else ("pass" if ocf3 > 0 else "fail"),
        "영업현금흐름 3년치 부족" if ocf3 is None else ("3년 합계 플러스" if ocf3 > 0 else
                                                  "3년 합계 마이너스"))
    r40, r40m = g.get("r40"), RULE40_MIN.get(market, 40.0)
    add("r40", "unknown" if r40 is None else ("pass" if r40 >= r40m else "fail"),
        "FCF 마진 계산 불가" if r40 is None else f"{r40:.0f} (기준 {r40m:.0f}↑)")
    sbcr = g.get("sbcr")
    add("sbc", "unknown" if sbcr is None else ("pass" if sbcr <= SBC_REV_MAX else "fail"),
        "주식보상비 계정 없음" if sbcr is None else
        f"매출의 {sbcr * 100:.1f}% (기준 {SBC_REV_MAX * 100:.0f}% 이하)")
    de, nc, icov = g.get("de"), g.get("nc"), g.get("icov")
    if nc is None and de is None:
        add("safe", "unknown", "부채 · 현금 계정 부족")
    else:
        ok_debt = bool(nc) or (de is not None and de <= DEBT_EQUITY_MAX)
        ok_icov = icov is None or icov >= ICOV_MIN or bool(nc)
        txt = ("순현금" if nc else f"부채/자본 {de:.2f}" if de is not None else "순부채")
        if icov is not None:
            txt += f" · 이자보상 {icov:.1f}배"
        add("safe", "pass" if ok_debt and ok_icov else "fail", txt)
    return out


def passes(gr: dict | None, market: str = "us") -> bool:
    return sum(1 for c in checks(gr, market) if c[2] == "pass") >= GROWTH_MIN_PASS


def score(gr: dict | None, market: str = "us") -> tuple[int, int]:
    """(통과 수, 판정된 수)"""
    cs = checks(gr, market)
    return sum(1 for c in cs if c[2] == "pass"), sum(1 for c in cs if c[2] != "unknown")


def peg(f: dict | None, price: float | None) -> tuple[float | None, float | None, float | None]:
    """(선행 PER, 내년 EPS 예상 성장률(소수), PEG). 못 구하면 None."""
    f = f or {}
    n, g1 = f.get("n"), f.get("g1")
    fpe = price / n if price and n and n > 0 else None
    if fpe is None or g1 is None or g1 <= 0:
        return fpe, g1, None
    return fpe, g1, fpe / (g1 * 100.0)
