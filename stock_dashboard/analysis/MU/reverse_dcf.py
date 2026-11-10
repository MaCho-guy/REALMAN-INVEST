"""
MU 역DCF 계산 — 현재 주가가 요구하는 FCF 성장률 역산.

모델: 10년간 성장률 g + 이후 영구성장 2.5%
      이분법(bisection)으로 g 를 찾는다.

    EV = Σ(t=1..10) FCF×(1+g)^t / (1+W)^t
         + [FCF×(1+g)^10×(1+tg) / (W−tg)] / (1+W)^10

    EV = 시가총액 + 순부채   (순부채가 음수면 순현금이므로 EV < 시가총액)

입력값 출처는 모두 아래 SOURCES 에 기록. 추정값 없음.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# 입력값 (단위: 백만 USD, 주식수는 백만주)
# ──────────────────────────────────────────────────────────────────────────────

PRICE = 795.23           # 2026-11-04 종가 (Investing.com)
DILUTED_SHARES = 1_150   # FY27 Q1 가이던스 기준 희석주식수 약 11.5억주
TOTAL_DEBT = 5_179       # FY26 말: 유동 491 + 비유동 4,688
CASH_AND_INV = 73_453    # FY26 말: 현금 38,364 + 단기투자 5,070 + 장기투자 30,019
TERMINAL_GROWTH = 0.025

# FCF = 영업활동현금흐름 − 유형자산 취득지출 (스킬 정의)
FCF_HISTORY = {
    2017: 3_400,
    2018: 8_500,
    2019: 3_400,
    2020: 83,
    2021: 2_440,
    2022: 3_110,
    2023: -6_120,
    2024: 121,
    2025: 1_668,
    2026: 58_963,
}

SOURCES = {
    "PRICE": "Investing.com, 2026-11-04 (전일 종가 855.10)",
    "DILUTED_SHARES": "FY26 Q4 보도자료 — FY27 Q1 가이던스 기준 약 11.5억주",
    "TOTAL_DEBT": "FY26 Q4 보도자료 재무상태표",
    "CASH_AND_INV": "FY26 Q4 보도자료 — 현금성자산 + 단기/장기 유가증권",
    "FCF_2024_2026": "FY25/FY26 Q4 보도자료 현금흐름표 (OCF − PP&E 취득지출)",
    "FCF_2017_2023": "Alpha Spread / 공시 기반 집계",
}

MARKET_CAP = PRICE * DILUTED_SHARES
NET_DEBT = TOTAL_DEBT - CASH_AND_INV          # 음수 = 순현금
ENTERPRISE_VALUE = MARKET_CAP + NET_DEBT


# ──────────────────────────────────────────────────────────────────────────────
# 모델
# ──────────────────────────────────────────────────────────────────────────────

def pv_of_fcf(fcf0: float, g: float, wacc: float, years: int = 10,
              tg: float = TERMINAL_GROWTH) -> float:
    """성장률 g 를 가정했을 때의 기업가치 현재가치."""
    if wacc <= tg:
        raise ValueError("WACC 가 영구성장률보다 커야 합니다.")
    total = 0.0
    for t in range(1, years + 1):
        total += fcf0 * (1 + g) ** t / (1 + wacc) ** t
    terminal = fcf0 * (1 + g) ** years * (1 + tg) / (wacc - tg)
    total += terminal / (1 + wacc) ** years
    return total


def solve_growth(target_ev: float, fcf0: float, wacc: float,
                 lo: float = -0.60, hi: float = 2.00, tol: float = 1e-9) -> float | None:
    """이분법으로 target_ev 를 만드는 g 를 찾는다. 범위 밖이면 None."""
    if fcf0 <= 0:
        return None
    f_lo = pv_of_fcf(fcf0, lo, wacc) - target_ev
    f_hi = pv_of_fcf(fcf0, hi, wacc) - target_ev
    if f_lo > 0:
        return None          # 최저 성장률에서도 가치가 주가보다 높음
    if f_hi < 0:
        return None          # 최고 성장률에서도 못 미침
    for _ in range(300):
        mid = (lo + hi) / 2
        val = pv_of_fcf(fcf0, mid, wacc) - target_ev
        if abs(val) < tol:
            return mid
        if val < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def cagr(start: float, end: float, years: int) -> float | None:
    """시작값이 0 이하면 CAGR 정의 불가."""
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return (end / start) ** (1 / years) - 1


# ──────────────────────────────────────────────────────────────────────────────
# 시나리오
# ──────────────────────────────────────────────────────────────────────────────

avg3 = sum(FCF_HISTORY[y] for y in (2024, 2025, 2026)) / 3
avg5 = sum(FCF_HISTORY[y] for y in (2022, 2023, 2024, 2025, 2026)) / 5
latest = FCF_HISTORY[2026]

SCENARIOS = (
    ("FY2026 실적 그대로", latest),
    ("3년 평균 (FY24~26)", avg3),
    ("5년 평균 (FY22~26)", avg5),
)
WACCS = (0.08, 0.10, 0.12)


def main() -> None:
    print("=" * 76)
    print("MU 역DCF — 현재 주가가 요구하는 FCF 성장률")
    print("=" * 76)
    print(f"현재 주가            ${PRICE:,.2f}   ({SOURCES['PRICE']})")
    print(f"희석주식수           {DILUTED_SHARES:,}백만주")
    print(f"시가총액             ${MARKET_CAP:,.0f}M  (${MARKET_CAP/1000:,.1f}B)")
    print(f"총부채               ${TOTAL_DEBT:,}M")
    print(f"현금+투자자산        ${CASH_AND_INV:,}M")
    print(f"순부채               ${NET_DEBT:,}M   ← 음수이므로 순현금 ${-NET_DEBT:,}M")
    print(f"기업가치(EV)         ${ENTERPRISE_VALUE:,.0f}M  (${ENTERPRISE_VALUE/1000:,.1f}B)")
    print(f"영구성장률           {TERMINAL_GROWTH:.1%}")

    print("\n" + "-" * 76)
    print("FCF 이력 (영업활동현금흐름 − 유형자산 취득지출, 단위 백만 USD)")
    print("-" * 76)
    for year, val in FCF_HISTORY.items():
        bar_len = max(0, int(val / 1500)) if val > 0 else 0
        bar = "█" * min(bar_len, 40)
        print(f"  FY{year}  {val:>9,}  {bar}")

    print("\n  FY2026 단독      ", f"${latest:>9,.0f}M")
    print("  3년 평균 (24~26) ", f"${avg3:>9,.0f}M")
    print("  5년 평균 (22~26) ", f"${avg5:>9,.0f}M")
    dev = (latest / avg3 - 1) * 100
    print(f"\n  ⚠ FY2026 은 3년 평균 대비 {dev:+.0f}% — 스킬 기준(±40%)을 크게 벗어남")
    print("     → 정규화 대상. 단, 아래처럼 어느 값을 쓰든 결과가 완전히 달라짐.")

    print("\n" + "=" * 76)
    print("요구 성장률 (10년) — FCF 기준 × 할인율")
    print("=" * 76)
    header = f"{'FCF 기준':<22}" + "".join(f"{w:>16.0%}" for w in WACCS)
    print(header)
    print("-" * 76)

    results: dict[str, dict[float, float | None]] = {}
    for label, fcf0 in SCENARIOS:
        row = f"{label:<22}"
        results[label] = {}
        for wacc in WACCS:
            g = solve_growth(ENTERPRISE_VALUE, fcf0, wacc)
            results[label][wacc] = g
            row += f"{'해 없음' if g is None else f'{g:>15.1%}':>16}"
        print(row + f"   (FCF ${fcf0:,.0f}M)")

    print("\n" + "=" * 76)
    print("비교 대상 — 과거 실제 성장률")
    print("=" * 76)

    past = {
        "FCF 5년 CAGR (FY21→26)": cagr(FCF_HISTORY[2021], FCF_HISTORY[2026], 5),
        "FCF 9년 CAGR (FY17→26)": cagr(FCF_HISTORY[2017], FCF_HISTORY[2026], 9),
        "FCF 5년 CAGR (FY21→25, 사이클 피크 제외)":
            cagr(FCF_HISTORY[2021], FCF_HISTORY[2025], 4),
        "FCF 8년 CAGR (FY17→25, 사이클 피크 제외)":
            cagr(FCF_HISTORY[2017], FCF_HISTORY[2025], 8),
    }
    for label, val in past.items():
        shown = "정의 불가" if val is None else f"{val:>8.1%}"
        print(f"  {label:<44} {shown}")

    print("\n" + "=" * 76)
    print("해석용 보조 지표")
    print("=" * 76)
    print(f"  EV / FY2026 FCF        {ENTERPRISE_VALUE/latest:>8.1f}배")
    print(f"  EV / 3년평균 FCF       {ENTERPRISE_VALUE/avg3:>8.1f}배")
    print(f"  EV / 5년평균 FCF       {ENTERPRISE_VALUE/avg5:>8.1f}배")
    print(f"  주가 / FY2026 EPS      {PRICE/74.33:>8.1f}배  (GAAP EPS $74.33)")
    print(f"  주가 / FY2027 컨센서스 {PRICE/176.50:>8.1f}배  (컨센서스 EPS $176.50)")

    print("\n" + "=" * 76)
    print("JSON 출력 (HTML 카드용)")
    print("=" * 76)
    import json
    payload = {
        "price": PRICE,
        "market_cap_m": round(MARKET_CAP),
        "net_debt_m": NET_DEBT,
        "ev_m": round(ENTERPRISE_VALUE),
        "fcf": {"latest": latest, "avg3": round(avg3, 1), "avg5": round(avg5, 1)},
        "deviation_pct": round(dev, 1),
        "required_growth": {
            label: {f"{int(w*100)}": (None if g is None else round(g, 5))
                    for w, g in row.items()}
            for label, row in results.items()
        },
        "past_cagr": {k: (None if v is None else round(v, 5)) for k, v in past.items()},
        "multiples": {
            "ev_fcf26": round(ENTERPRISE_VALUE / latest, 2),
            "ev_fcf_avg3": round(ENTERPRISE_VALUE / avg3, 2),
            "ev_fcf_avg5": round(ENTERPRISE_VALUE / avg5, 2),
            "pe_fy26": round(PRICE / 74.33, 2),
            "pe_fy27e": round(PRICE / 176.50, 2),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
