"""
CRCL 역DCF 계산 — 현재 주가가 요구하는 FCF 성장률 역산. (생성 2026-11-19)

모델: 10년간 성장률 g + 이후 영구성장 2.5%. 이분법으로 g 를 찾는다.
    EV = Σ(t=1..10) FCF×(1+g)^t / (1+W)^t + [FCF×(1+g)^10×(1+tg) / (W−tg)] / (1+W)^10
    EV = 시가총액 + 순부채 (순현금이면 EV < 시가총액)
입력값 출처는 price.html 의 '⑥ 계산 과정' 표와 같다. 단위: 백만 달러 · 백만 주.
FCF = 영업현금흐름 − 유형자산 취득 − 소프트웨어 개발비 자본화. 주식보상비는 빼지 않는다(주의).
"""
PRICE = 57.65             # 2026-11-16 종가 (11/13 종가는 62.20)
DILUTED_SHARES = 267.8    # 2026년 3분기 가중평균 희석
TOTAL_DEBT = 0            # 2026-09-30 (전환사채 0)
CASH = 1_700              # 회사 몫 현금 — 고객 준비금 · 회사 보유 스테이블코인용 현금은 제외
TERMINAL_GROWTH = 0.025
OCF = {2021: -92.33, 2022: -72.69, 2023: 139.57, 2024: 344.58, 2025: 542.13}
CAPEX = {2021: 1.06 + 6.81, 2022: 3.05 + 18.32, 2023: 0.65 + 32.86, 2024: 18.13 + 39.10, 2025: 12.43 + 56.20}
FCF = {y: OCF[y] - CAPEX[y] for y in OCF}
BASE_WACC = 0.12
WACCS = (0.10, 0.12, 0.14)
# 2025년 FCF 가 3년 평균보다 64% 높아(±40% 초과) 3년 평균을 기본으로 쓴다
BASES = {"FCF 3년 평균": sum(FCF[y] for y in (2023, 2024, 2025)) / 3, "FCF 2025": FCF[2025], "FCF 최근 12개월(2026.6)": 776.92 - 15.40 - 67.11}
PAST = {"매출 2023→2025": (1450, 2747, 2), "매출 2022→2025": (772.05, 2747, 3), "FCF 2023→2025": (FCF[2023], FCF[2025], 2)}


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
