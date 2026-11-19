"""
AMT 역DCF 계산 — 현재 주가가 요구하는 FCF 성장률 역산. (생성 2026-11-19)

모델: 10년간 성장률 g + 이후 영구성장 2.5%. 이분법으로 g 를 찾는다.
    EV = Σ(t=1..10) FCF×(1+g)^t / (1+W)^t + [FCF×(1+g)^10×(1+tg) / (W−tg)] / (1+W)^10
    EV = 시가총액 + 순부채
입력값 출처는 price.html 의 '⑥ 계산 과정' 표와 같다. 단위: 백만 달러 · 백만 주.
"""
PRICE = 191.64            # 2026-11-13 종가
DILUTED_SHARES = 466.2    # 2026년 가중평균 희석 주식수 전망 (3분기 실적 발표)
TOTAL_DEBT = 37_579       # 2026-09-30
CASH = 1_872              # 2026-09-30
TERMINAL_GROWTH = 0.025
OCF = {2021: 4820, 2022: 3696, 2023: 4722, 2024: 5291, 2025: 5464}
CAPEX = {2021: 1377, 2022: 1874, 2023: 1798, 2024: 1590, 2025: 1680}
FCF = {y: OCF[y] - CAPEX[y] for y in OCF}
AFFO_2025 = 5_042         # 리츠 지표 (참고 계산용)
BASE_WACC = 0.09
WACCS = (0.08, 0.09, 0.10, 0.12)
BASES = {"FCF 2025": FCF[2025], "AFFO 2025": AFFO_2025, "FCF 3년 평균": sum(FCF[y] for y in (2023, 2024, 2025)) / 3}
PAST = {"FCF 2021→2025": (FCF[2021], FCF[2025], 4), "매출 2021→2025": (9357, 10645, 4), "주당 AFFO 2023→2025": (9.87, 10.76, 2)}


def enterprise_value(fcf, g, wacc, tg=TERMINAL_GROWTH, years=10):
    pv = sum(fcf * (1 + g) ** t / (1 + wacc) ** t for t in range(1, years + 1))
    tv = fcf * (1 + g) ** years * (1 + tg) / (wacc - tg) / (1 + wacc) ** years
    return pv + tv


def implied_growth(ev, fcf, wacc):
    lo, hi = -0.5, 1.5
    for _ in range(200):
        mid = (lo + hi) / 2
        if enterprise_value(fcf, mid, wacc) > ev:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def cagr(a, b, n):
    return (b / a) ** (1 / n) - 1


if __name__ == "__main__":
    market_cap = PRICE * DILUTED_SHARES
    net_debt = TOTAL_DEBT - CASH
    ev = market_cap + net_debt
    print(f"시가총액 {market_cap:,.0f} · 순부채 {net_debt:,.0f} · EV {ev:,.0f}")
    print("FCF:", {y: round(v, 1) for y, v in FCF.items()})
    for name, base in BASES.items():
        row = " · ".join(f"WACC {w:.0%}: {implied_growth(ev, base, w):.1%}" for w in WACCS)
        print(f"요구 성장률 — {name} {base:,.0f} → {row}")
    for name, (a, b, n) in PAST.items():
        print(f"과거 — {name}: 연 {cagr(a, b, n):.1%}")
