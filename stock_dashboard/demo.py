"""
오프라인 데모 데이터.

네트워크가 막힌 환경에서도 레이아웃을 확인할 수 있게, 설정에 정의된
모든 심볼에 대해 결정론적인(seed 고정) 가짜 시세를 만듭니다.

데모 값은 **실제 시세가 아닙니다.** 앱 화면에도 경고 배너를 띄웁니다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import random

import config
from sources.model import MarketStatus, Quote

#: 데모에서 사용할 기준 가격. 심볼 해시로 결정되므로 실행마다 동일합니다.
_BASE_HINTS: dict[str, float] = {
    "^KS11": 2650.0, "^KQ11": 760.0, "^GSPC": 6050.0, "^IXIC": 20100.0,
    "^DJI": 44200.0, "^SOX": 5150.0,
    "KRW=X": 1380.0,
    "EURUSD=X": 1.08,
    "^TNX": 4.21,
    "^IRX": 4.05,
    "^VIX": 15.4,
    "CL=F": 71.3,
    "GC=F": 2650.0,
    "NQ=F": 20450.0,
    "ES=F": 5880.0,
    "YM=F": 43200.0,
    "005930": 71500.0,
    "005935": 59800.0,
    "000660": 196000.0,
    "005380": 215000.0,
    # 괴리율이 현실적인 범위(±1~3%)로 나오도록 환산주수를 반영한 값입니다.
    # 1 ADR = 본주 0.1주이므로 196,000원 × 0.1 ÷ 1,380 ≈ $14.2 가 평형 가격입니다.
    "SKHY": 14.50,
    "SMSN.IL": 1_278.45,   # 1 GDR = 본주 25주 → 괴리 약 −1.3%
    "SMSD.IL": 1_092.00,   # 우선주 GDS → 괴리 약 +0.8%
    "DRAM": 47.98,
}


def _seeded_unit(key: str) -> float:
    """심볼로부터 0..1 사이의 결정론적 값을 만듭니다."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


#: 변화 감지 탭을 보여주려고 일부러 극단값을 심어둔 종목.
#: (일일 등락률 %, 52주 고점 배수, 52주 저점 배수, 실적 D-day 또는 None)
_SIGNAL_SCENARIOS: dict[str, tuple[float, float, float, int | None]] = {
    "MU":   (-7.4, 1.58, 0.24, 12),    # 급락 + 고점 대비 큰 낙폭 + 실적 임박
    "MSFT": (0.8, 1.04, 0.72, 3),      # 실적 임박만
    "AAPL": (1.2, 1.01, 0.68, None),   # 52주 최고가 근처
    "UNH":  (-2.1, 1.44, 1.01, None),  # 52주 최저가 근처 + 낙폭
    "O":    (0.3, 1.12, 0.88, None),   # 신호 없음 (조용한 종목도 있어야 현실적)
}


def _fake(symbol: str, currency: str, status: MarketStatus, base: float | None = None) -> Quote:
    unit = _seeded_unit(symbol)
    price = base if base is not None else _BASE_HINTS.get(symbol, 20.0 + unit * 480.0)

    scenario = _SIGNAL_SCENARIOS.get(symbol)
    if scenario is not None:
        pct = scenario[0]
    else:
        # -3% ~ +3% 사이의 결정론적 등락
        pct = (_seeded_unit(symbol + "|chg") - 0.5) * 6.0
    prev = price / (1.0 + pct / 100.0)

    extra: dict = {}
    if scenario is not None:
        _p, high_mult, low_mult, edays = scenario
        extra["high_52w"] = price * high_mult
        extra["low_52w"] = price * low_mult
        if edays is not None:
            extra["earnings_date"] = (
                dt.date.today() + dt.timedelta(days=edays)
            ).isoformat()
    else:
        extra["high_52w"] = price * (1.1 + unit * 0.5)
        extra["low_52w"] = price * (0.55 + unit * 0.3)

    extended = None
    label = ""
    if status in (MarketStatus.PRE, MarketStatus.POST):
        extended = price * (1.0 + (_seeded_unit(symbol + "|ext") - 0.5) * 0.02)
        label = "프리장" if status is MarketStatus.PRE else "애프터장"

    return Quote(
        symbol=symbol,
        price=price,
        prev_close=prev,
        currency=currency,
        status=status,
        extended_price=extended,
        extended_label=label,
        extra=extra,
    )


def demo_payload() -> dict[str, dict[str, Quote]]:
    """app.py 의 load_all() 과 같은 형태의 딕셔너리를 반환합니다."""
    yahoo_quotes: dict[str, Quote] = {}
    for section in config.SECTIONS:
        for inst in section.instruments:
            if inst.source != "yahoo":
                continue
            status = (
                MarketStatus.PRE
                if section.key in ("watchlist", "etf_proxy", "adr")
                else MarketStatus.REGULAR
            )
            # 1순위 심볼만 채웁니다. 대체 심볼을 비워 둬서 폴백 경로도 데모에서 확인됩니다.
            yahoo_quotes[inst.symbol] = _fake(inst.symbol, inst.currency or "USD", status)

    for inst in config.STRIP_EXTRA:
        yahoo_quotes[inst.symbol] = _fake(inst.symbol, inst.currency, MarketStatus.REGULAR)
    yahoo_quotes["KRW=X"] = _fake("KRW=X", "KRW", MarketStatus.REGULAR)
    yahoo_quotes["EURUSD=X"] = _fake("EURUSD=X", "USD", MarketStatus.REGULAR)

    naver_quotes: dict[str, Quote] = {
        code: _fake(code, "KRW", MarketStatus.CLOSED) for code in config.all_naver_codes()
    }

    hl_quotes: dict[str, Quote] = {}
    for sym in config.all_hyperliquid_symbols():
        q = _fake(sym, "USD", MarketStatus.LIVE)
        funding_1h = (_seeded_unit(sym + "|fund") - 0.5) * 0.0002
        q.extra = {
            "funding_1h": funding_1h,
            "funding_8h": funding_1h * 8,
            "perp_premium": (_seeded_unit(sym + "|prem") - 0.5) * 0.004,
            "open_interest": 10_000 + _seeded_unit(sym + "|oi") * 90_000,
            "day_volume_usd": 1e6 + _seeded_unit(sym + "|vol") * 5e7,
        }
        hl_quotes[sym] = q

    return {"yahoo": yahoo_quotes, "naver": naver_quotes, "hyperliquid": hl_quotes}


def demo_filings() -> dict[str, list]:
    """데모용 EDGAR 공시. 변화 감지 탭의 각 신호 유형이 한 번씩 나오게 구성했습니다."""
    from sources.edgar import Filing

    today = dt.date.today()

    def days(n: int) -> str:
        return (today - dt.timedelta(days=n)).isoformat()

    return {
        "MU": [
            Filing("10-Q", days(3), days(10), "0000723125-26-000031",
                   "mu-20261203.htm", items="", cik=723125),
            Filing("8-K", days(9), days(9), "0000723125-26-000029",
                   "mu-8k.htm", items="2.02,9.01", cik=723125),
        ],
        "AAPL": [
            Filing("10-K", days(21), days(35), "0000320193-26-000079",
                   "aapl-20260926.htm", cik=320193),
        ],
        "MSFT": [
            Filing("8-K", days(140), days(140), "0000789019-26-000045",
                   "msft-8k.htm", items="5.02", cik=789019),
        ],
        "UNH": [
            Filing("SC 13G", days(6), "", "0000731766-26-000012",
                   "unh-sc13g.htm", cik=731766),
        ],
        "O": [],
    }


def demo_dart_disclosures() -> dict[str, list]:
    """데모용 DART 공시."""
    from sources.dart import Disclosure

    today = dt.date.today()

    def ymd(n: int) -> str:
        return (today - dt.timedelta(days=n)).strftime("%Y%m%d")

    # 잠정실적 공시를 섞어 둡니다 — 잠정실적 레이더가 비어 보이면
    # 기능이 들어간 건지 데모 데이터가 없는 건지 구분이 안 됩니다.
    # 분기보고서보다 **먼저** 접수된 날짜를 줘야 "2주 빠르다" 가 보입니다.
    return {
        "005930": [
            Disclosure("삼성전자", "분기보고서 (2026.09)", "20261114000" + "123",
                       ymd(4), flr_nm="삼성전자", stock_code="005930"),
            Disclosure("삼성전자", "연결재무제표기준영업(잠정)실적(공정공시)",
                       "20261008000" + "111",
                       ymd(18), flr_nm="삼성전자", stock_code="005930"),
            Disclosure("삼성전자", "현금·현물배당결정", "20261030000" + "456",
                       ymd(19), flr_nm="삼성전자", stock_code="005930"),
        ],
        "000660": [
            Disclosure("SK하이닉스", "분기보고서 (2026.09)", "20261113000" + "789",
                       ymd(5), flr_nm="SK하이닉스", stock_code="000660"),
            Disclosure("SK하이닉스", "영업(잠정)실적(공정공시)",
                       "20261009000" + "222",
                       ymd(17), flr_nm="SK하이닉스", stock_code="000660"),
        ],
    }


def demo_inventory_trends() -> dict[str, object]:
    """데모용 재고 지표 추세.

    지표체계 문서의 2026-11-05 스냅샷 분위기를 따라, 삼성전자는 재고 증가율이
    매출 증가율을 밑도는(아직 ② 확장기) 모습, SK하이닉스는 DIO 가 꺾여 올라오는
    모습으로 구성했습니다. **숫자는 전부 가짜입니다.**
    """
    import cycle as cycle_mod
    from sources.dart import Account

    def rows(inv: float, cos: float, rev: float) -> list[Account]:
        def a(sj, aid, nm, amt):
            return Account(sj_div=sj, sj_nm="x", account_id=aid, account_nm=nm,
                           thstrm_amount=amt, thstrm_add_amount=None,
                           frmtrm_amount=None, bfefrmtrm_amount=None)
        return [
            a("BS", "ifrs-full_Inventories", "재고자산", inv),
            a("IS", "ifrs-full_CostOfSales", "매출원가", cos),
            a("IS", "ifrs-full_Revenue", "수익(매출액)", rev),
        ]

    조 = 1_0000_0000_0000.0

    # 사업보고서(FY)는 연간 금액이므로 분기의 약 4배로 둬야 DIO 가 맞게 나옵니다.
    # 이걸 틀리면 DIO 가 400일을 넘고, cycle 모듈이 기간 불일치로 걸러냅니다.
    samsung = cycle_mod.build_trend("삼성전자", "005930", [
        (2025, "3Q", "CFS", rows(60.1 * 조, 44.0 * 조, 79.0 * 조)),
        (2025, "FY", "CFS", rows(63.4 * 조, 185.2 * 조, 331.0 * 조)),
        (2026, "1Q", "CFS", rows(66.8 * 조, 52.1 * 조, 95.4 * 조)),
        (2026, "2Q", "CFS", rows(71.4 * 조, 58.3 * 조, 112.7 * 조)),
    ])

    hynix = cycle_mod.build_trend("SK하이닉스", "000660", [
        (2025, "3Q", "CFS", rows(14.2 * 조, 11.1 * 조, 17.6 * 조)),
        (2025, "FY", "CFS", rows(15.0 * 조, 46.8 * 조, 79.4 * 조)),
        (2026, "1Q", "CFS", rows(16.9 * 조, 13.0 * 조, 24.8 * 조)),
        (2026, "2Q", "CFS", rows(19.8 * 조, 13.4 * 조, 26.1 * 조)),
    ])

    return {"005930": samsung, "000660": hynix}


def demo_us_inventory_trends() -> dict[str, object]:
    """데모용 미국 기업 재고 지표 (EDGAR XBRL 경로).

    지표체계 문서의 'MU FQ4-26: DIO 129일(+9 QoQ), 10년 중간값 ~125~128일' 을
    참고해 비슷한 모양으로 구성했습니다. **숫자는 가짜입니다.**
    """
    import cycle as cycle_mod
    from sources.edgar_xbrl import Fact

    B = 1_000_000_000.0

    def inst(end: str, val: float, fy: int, fp: str) -> Fact:
        return Fact(start=None, end=end, val=val, form="10-Q",
                    fy=fy, fp=fp, filed=end, tag="InventoryNet")

    def dur(start: str, end: str, val: float, fy: int, fp: str) -> Fact:
        return Fact(start=start, end=end, val=val, form="10-Q",
                    fy=fy, fp=fp, filed=end, tag="CostOfGoodsAndServicesSold")

    # (종료일, 시작일, 재고, 매출원가, 매출, 회계연도, 분기)
    rows = [
        ("2025-11-27", "2025-08-29", 9.1 * B, 6.9 * B, 13.6 * B, 2026, "Q1"),
        ("2026-02-26", "2025-11-28", 10.4 * B, 8.1 * B, 23.9 * B, 2026, "Q2"),
        ("2026-05-28", "2026-02-27", 12.2 * B, 9.4 * B, 41.5 * B, 2026, "Q3"),
        ("2026-09-03", "2026-05-29", 15.6 * B, 11.0 * B, 54.2 * B, 2026, "Q4"),
    ]

    inventory = [inst(e, iv, fy, fp) for e, _s, iv, _c, _r, fy, fp in rows]
    cost = [dur(s, e, c, fy, fp) for e, s, _iv, c, _r, fy, fp in rows]
    revenue = [
        Fact(start=s, end=e, val=r, form="10-Q", fy=fy, fp=fp, filed=e,
             tag="RevenueFromContractWithCustomerExcludingAssessedTax")
        for e, s, _iv, _c, r, fy, fp in rows
    ]

    return {
        "MU": cycle_mod.build_trend_from_xbrl(
            "Micron", "MU", inventory, cost, revenue, quarters=6),
    }


def demo_news(keys: list[str]) -> dict[str, list]:
    """데모용 헤드라인. 제목만 있고 링크는 없습니다 — 가짜이므로."""
    from sources.news import Headline

    today = dt.date.today()

    def ago(n: int) -> str:
        return (today - dt.timedelta(days=n)).isoformat()

    pool = {
        "MU": [
            Headline("(데모) 메모리 3사 2027년 공급 계약 마무리 국면", "", "데모 와이어", ago(1)),
            Headline("(데모) HBM4 가격 협상 결과에 시장 주목", "", "데모 경제", ago(2)),
            Headline("(데모) 반도체 ETF 자금 유출 지속", "", "데모 마켓", ago(3)),
        ],
        "AAPL": [
            Headline("(데모) 연간보고서 제출, 서비스 부문 성장률 공개", "", "데모 와이어", ago(1)),
            Headline("(데모) 공급망 다변화 계획 업데이트", "", "데모 테크", ago(4)),
        ],
    }
    generic = [
        Headline("(데모) 해당 종목 관련 헤드라인 1", "", "데모 와이어", ago(1)),
        Headline("(데모) 해당 종목 관련 헤드라인 2", "", "데모 경제", ago(2)),
    ]
    return {k: pool.get(k, generic) for k in keys}


def demo_fundamentals(symbols: list[str], fields: tuple[tuple[str, str, str], ...]) -> dict[str, dict]:
    """밸류에이션 표용 데모 값."""
    out: dict[str, dict] = {}
    for sym in symbols:
        row: dict = {"_error": None, "_name": sym}
        for key, _label, kind in fields:
            unit = _seeded_unit(sym + "|" + key)
            if kind == "pct":
                row[key] = 0.02 + unit * 0.45
            elif kind == "bigusd":
                row[key] = 5e10 + unit * 3e12
            else:
                row[key] = 5.0 + unit * 60.0
        out[sym] = row
    return out


def demo_macro_series() -> tuple[dict, dict]:
    """오프라인 매크로 데이터.

    일부러 **여러 임계값이 걸리게** 만들어 두었습니다 — 반도체 생산 전년대비
    마이너스→플러스 전환, 금리 급변, 실업수당 청구 급증. 신호 경로 전체를
    눈으로 확인하려면 신호가 실제로 나야 합니다.
    """
    import datetime as dt

    from sources.fred import Observation, Series

    today = dt.date.today()

    def monthly(series_id: str, values: list[float], *,
                lag_days: int = 20) -> Series:
        """최신 관측이 lag_days 전인 월간 계열. 전년대비를 쓰려면 13개 이상 필요."""
        end = today - dt.timedelta(days=lag_days)
        anchor = end.replace(day=1)
        obs = []
        for i, v in enumerate(reversed(values)):
            month = anchor.month - i
            year = anchor.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            obs.append(Observation(date=dt.date(year, month, 1), value=v))
        obs.reverse()
        return Series(series_id=series_id, observations=obs)

    def daily(series_id: str, values: list[float]) -> Series:
        obs = [
            Observation(date=today - dt.timedelta(days=len(values) - 1 - i),
                        value=v)
            for i, v in enumerate(values)
        ]
        return Series(series_id=series_id, observations=obs)

    def weekly(series_id: str, values: list[float]) -> Series:
        obs = [
            Observation(date=today - dt.timedelta(weeks=len(values) - 1 - i),
                        value=v)
            for i, v in enumerate(values)
        ]
        return Series(series_id=series_id, observations=obs)

    # 10년물 — 최근 20영업일에 0.58%p 상승 (임계값 0.50 초과)
    ust10 = daily("DGS10", [
        3.62, 3.64, 3.61, 3.66, 3.70, 3.68, 3.72, 3.75, 3.79, 3.82,
        3.86, 3.91, 3.95, 3.98, 4.02, 4.05, 4.09, 4.12, 4.16, 4.18, 4.20,
    ])
    ust2 = daily("DGS2", [
        3.95, 3.96, 3.94, 3.97, 3.99, 3.98, 4.01, 4.02, 4.04, 4.05,
        4.07, 4.09, 4.10, 4.12, 4.13, 4.14, 4.16, 4.17, 4.18, 4.19, 4.20,
    ])
    # 10-2 스프레드 — 마이너스에서 플러스로 전환 (부호 전환 신호)
    curve = daily("T10Y2Y", [
        -0.33, -0.31, -0.33, -0.31, -0.29, -0.30, -0.29, -0.27, -0.25,
        -0.23, -0.21, -0.18, -0.15, -0.14, -0.11, -0.09, -0.07, -0.05,
        -0.02, -0.01, 0.00, 0.01,
    ])
    ig = daily("BAMLC0A0CM", [
        0.88, 0.87, 0.89, 0.88, 0.87, 0.89, 0.90, 0.89, 0.91, 0.92,
        0.91, 0.93, 0.94, 0.93, 0.95, 0.96, 0.95, 0.97, 0.98, 0.97, 0.99,
    ])
    # 마지막 값을 급등시켜 둡니다 — '자기 20일 평균 대비 +20%' 신호 경로를
    # 미리보기에서 눈으로 확인하려면 신호가 실제로 나야 합니다.
    # 20일 평균 3.2 -> 마지막 4.05 는 +26%.
    hy = daily("BAMLH0A0HYM2", [
        3.12, 3.10, 3.14, 3.11, 3.09, 3.13, 3.16, 3.14, 3.18, 3.20,
        3.17, 3.21, 3.24, 3.22, 3.26, 3.29, 3.27, 3.31, 3.34, 3.32, 4.05,
    ])

    # CPI — 지수 레벨 25개월 (전년대비 산출 가능)
    cpi_levels = [
        308.0, 308.6, 309.3, 310.0, 310.6, 311.3, 312.0, 312.7, 313.3,
        314.0, 314.7, 315.4, 316.0, 316.6, 317.3, 318.0, 318.6, 319.3,
        320.1, 320.9, 321.6, 322.4, 323.2, 324.0, 324.9,
    ]
    cpi = monthly("CPIAUCSL", cpi_levels)
    core_cpi = monthly("CPILFESL", [v * 0.97 for v in cpi_levels])
    core_pce = monthly("PCEPILFE", [
        125.0, 125.3, 125.6, 125.9, 126.2, 126.5, 126.8, 127.1, 127.4,
        127.7, 128.0, 128.3, 128.6, 128.9, 129.2, 129.6, 129.9, 130.3,
        130.7, 131.1, 131.5, 131.9, 132.4, 132.8, 133.3,
    ], lag_days=35)
    breakeven = daily("T5YIFR", [
        2.28, 2.29, 2.27, 2.30, 2.31, 2.30, 2.32, 2.33, 2.34, 2.33,
        2.35, 2.36, 2.38, 2.37, 2.39, 2.41, 2.40, 2.42, 2.43, 2.44, 2.45,
    ])

    # 주간 실업수당 청구 — 4주 평균 대비 +19% (임계값 15% 초과)
    claims = weekly("ICSA", [
        218_000, 221_000, 215_000, 224_000, 219_000, 226_000, 222_000,
        231_000, 228_000, 235_000, 232_000, 229_000, 238_000, 241_000,
        236_000, 244_000, 239_000, 247_000, 243_000, 251_000, 298_000,
    ])
    unrate = monthly("UNRATE", [
        3.9, 3.9, 4.0, 4.0, 4.0, 4.1, 4.1, 4.1, 4.2, 4.2, 4.1, 4.2,
        4.2, 4.3, 4.2, 4.3, 4.3, 4.4, 4.3, 4.4, 4.4, 4.5, 4.5, 4.6, 4.7,
    ])
    payems = monthly("PAYEMS", [
        158_000, 158_180, 158_340, 158_520, 158_690, 158_830, 158_990,
        159_140, 159_270, 159_410, 159_540, 159_660, 159_770, 159_880,
        159_970, 160_060, 160_140, 160_210, 160_270, 160_320, 160_360,
        160_390, 160_410, 160_420, 160_405,
    ])

    # 반도체 산업생산 — 전년대비 마이너스에서 플러스로 전환 (사이클 전환 신호)
    semi_ip = monthly("IPG3344S", [
        172.0, 171.2, 170.5, 169.8, 169.1, 168.6, 168.0, 167.5, 167.0,
        166.6, 166.2, 165.9, 165.6, 165.4, 165.3, 165.5, 165.9, 166.6,
        167.6, 168.9, 170.4, 172.2, 174.3, 176.1, 178.4,
    ])
    # 반도체 PPI — 전년대비 마이너스 지속 (전환 아직 아님)
    semi_ppi = monthly("PCU334413334413", [
        33.8, 33.6, 33.4, 33.1, 32.9, 32.7, 32.4, 32.2, 32.0, 31.8,
        31.6, 31.4, 31.2, 31.0, 30.9, 30.7, 30.6, 30.4, 30.3, 30.2,
        30.1, 30.0, 29.9, 29.9, 29.8,
    ])

    series = {
        "DGS10": ust10, "DGS2": ust2, "T10Y2Y": curve,
        "BAMLH0A0HYM2": hy, "BAMLC0A0CM": ig,
        "CPIAUCSL": cpi, "CPILFESL": core_cpi, "PCEPILFE": core_pce,
        "T5YIFR": breakeven,
        "ICSA": claims, "UNRATE": unrate, "PAYEMS": payems,
        "IPG3344S": semi_ip, "PCU334413334413": semi_ppi,
    }
    return series, {}


def demo_screens() -> tuple[dict, dict]:
    """오프라인 버핏 스크리닝 데이터.

    네 가지 성격을 일부러 섞었습니다:
      KO   — 대부분 통과 (안정 소비재)
      MSFT — 전부 통과 (고ROE·자본경량)
      MU   — 대부분 탈락 (사이클·자본집약) ← 기준의 한계를 보여주는 사례
      O    — 부채 기준 탈락 (리츠는 구조적으로 부채가 많음)
      ZZZZ — 데이터 부족 (판정 불가 처리 확인용)
    """
    import buffett

    def rows(spec: list[dict], start_year: int = 2016) -> list[buffett.YearRow]:
        """영업현금흐름·현금·단기차입금은 주어진 값에서 파생시킵니다 —
        역DCF 경로(FCF·순부채)를 데모에서도 돌려보려면 있어야 합니다."""
        out = []
        for i, d in enumerate(spec):
            year = start_year + i
            d = dict(d)
            ni = d.get("net_income") or 0.0
            da = d.get("dep_amort") or 0.0
            d.setdefault("operating_cash_flow", ni + da * 1.15)
            d.setdefault("cash", abs(ni) * 1.4)
            d.setdefault("short_term_investments", abs(ni) * 0.5)
            d.setdefault("short_term_debt", (d.get("long_term_debt") or 0.0) * 0.08)
            # ROIC·이자보상배율 경로도 데모에서 돌아가야 합니다. 안 넣으면
            # 미리보기에 '판정 불가' 두 줄이 고정으로 떠서, 기능이 안 들어간
            # 것처럼 보입니다. 실효세율 22%, 영업이익률은 순이익의 1.3배
            # 수준으로 잡습니다(세금·이자를 더한 대략의 모양).
            d.setdefault("pretax_income", ni * 1.28)
            d.setdefault("tax_expense", ni * 1.28 * 0.22)
            ltd = d.get("long_term_debt") or 0.0
            d.setdefault("interest_expense", ltd * 0.045)
            d.setdefault("operating_income", ni * 1.28 + ltd * 0.045)
            out.append(buffett.YearRow(
                year=year, end=f"{year}-12-31", **d))
        return out

    M = 1_000_000.0

    # KO 형태 — 높고 안정적인 ROE, 자본경량, 부채는 좀 있음
    ko = rows([
        dict(net_income=6_527 * M, revenue=41_863 * M, gross_profit=25_398 * M,
             dep_amort=1_787 * M, capex=2_262 * M, equity=23_220 * M,
             long_term_debt=29_684 * M),
        dict(net_income=1_248 * M, revenue=35_410 * M, gross_profit=22_154 * M,
             dep_amort=1_260 * M, capex=1_675 * M, equity=17_072 * M,
             long_term_debt=31_182 * M),
        dict(net_income=6_434 * M, revenue=34_300 * M, gross_profit=21_233 * M,
             dep_amort=1_086 * M, capex=1_548 * M, equity=16_981 * M,
             long_term_debt=25_364 * M),
        dict(net_income=8_920 * M, revenue=37_266 * M, gross_profit=22_647 * M,
             dep_amort=1_365 * M, capex=2_054 * M, equity=18_981 * M,
             long_term_debt=27_516 * M),
        dict(net_income=7_747 * M, revenue=33_014 * M, gross_profit=19_581 * M,
             dep_amort=1_536 * M, capex=1_177 * M, equity=19_299 * M,
             long_term_debt=40_125 * M),
        dict(net_income=9_771 * M, revenue=38_655 * M, gross_profit=23_298 * M,
             dep_amort=1_452 * M, capex=1_367 * M, equity=22_999 * M,
             long_term_debt=38_116 * M),
        dict(net_income=9_542 * M, revenue=43_004 * M, gross_profit=25_004 * M,
             dep_amort=1_260 * M, capex=1_484 * M, equity=24_105 * M,
             long_term_debt=36_377 * M),
        dict(net_income=10_714 * M, revenue=45_754 * M, gross_profit=27_234 * M,
             dep_amort=1_128 * M, capex=1_852 * M, equity=25_941 * M,
             long_term_debt=35_547 * M),
        dict(net_income=10_631 * M, revenue=47_061 * M, gross_profit=28_728 * M,
             dep_amort=1_117 * M, capex=2_064 * M, equity=24_856 * M,
             long_term_debt=42_134 * M),
        dict(net_income=11_420 * M, revenue=49_312 * M, gross_profit=30_412 * M,
             dep_amort=1_184 * M, capex=2_210 * M, equity=26_480 * M,
             long_term_debt=41_280 * M),
    ])

    # MSFT 형태 — 전부 통과
    msft = rows([
        dict(net_income=20_539 * M, revenue=91_154 * M, gross_profit=58_374 * M,
             dep_amort=6_622 * M, capex=8_343 * M, equity=71_997 * M,
             long_term_debt=40_557 * M),
        dict(net_income=21_204 * M, revenue=96_571 * M, gross_profit=62_310 * M,
             dep_amort=7_800 * M, capex=8_129 * M, equity=72_394 * M,
             long_term_debt=76_073 * M),
        dict(net_income=16_571 * M, revenue=110_360 * M, gross_profit=72_007 * M,
             dep_amort=9_900 * M, capex=11_632 * M, equity=82_718 * M,
             long_term_debt=72_242 * M),
        dict(net_income=39_240 * M, revenue=125_843 * M, gross_profit=82_933 * M,
             dep_amort=11_682 * M, capex=13_925 * M, equity=102_330 * M,
             long_term_debt=66_662 * M),
        dict(net_income=44_281 * M, revenue=143_015 * M, gross_profit=96_937 * M,
             dep_amort=12_796 * M, capex=15_441 * M, equity=118_304 * M,
             long_term_debt=59_578 * M),
        dict(net_income=61_271 * M, revenue=168_088 * M, gross_profit=115_856 * M,
             dep_amort=11_686 * M, capex=20_622 * M, equity=141_988 * M,
             long_term_debt=50_074 * M),
        dict(net_income=72_738 * M, revenue=198_270 * M, gross_profit=135_620 * M,
             dep_amort=14_460 * M, capex=23_886 * M, equity=166_542 * M,
             long_term_debt=47_032 * M),
        dict(net_income=72_361 * M, revenue=211_915 * M, gross_profit=146_052 * M,
             dep_amort=13_861 * M, capex=28_107 * M, equity=206_223 * M,
             long_term_debt=41_990 * M),
        dict(net_income=88_136 * M, revenue=245_122 * M, gross_profit=171_008 * M,
             dep_amort=22_287 * M, capex=44_477 * M, equity=268_477 * M,
             long_term_debt=42_688 * M),
        dict(net_income=96_640 * M, revenue=281_724 * M, gross_profit=197_210 * M,
             dep_amort=28_400 * M, capex=58_900 * M, equity=312_400 * M,
             long_term_debt=45_200 * M),
    ])

    # MU 형태 — 사이클·자본집약. 적자 연도와 큰 감익이 섞입니다
    mu = rows([
        dict(net_income=-276 * M, revenue=12_399 * M, gross_profit=1_518 * M,
             dep_amort=2_975 * M, capex=5_817 * M, equity=12_080 * M,
             long_term_debt=9_872 * M),
        dict(net_income=5_089 * M, revenue=20_322 * M, gross_profit=8_436 * M,
             dep_amort=4_183 * M, capex=8_879 * M, equity=19_350 * M,
             long_term_debt=9_872 * M),
        dict(net_income=14_135 * M, revenue=30_391 * M, gross_profit=17_891 * M,
             dep_amort=4_803 * M, capex=8_879 * M, equity=32_294 * M,
             long_term_debt=3_780 * M),
        dict(net_income=6_313 * M, revenue=23_406 * M, gross_profit=10_702 * M,
             dep_amort=4_751 * M, capex=9_780 * M, equity=35_881 * M,
             long_term_debt=4_541 * M),
        dict(net_income=2_687 * M, revenue=21_435 * M, gross_profit=6_552 * M,
             dep_amort=5_433 * M, capex=8_223 * M, equity=39_491 * M,
             long_term_debt=6_373 * M),
        dict(net_income=5_861 * M, revenue=27_705 * M, gross_profit=10_379 * M,
             dep_amort=6_214 * M, capex=10_030 * M, equity=43_566 * M,
             long_term_debt=6_670 * M),
        dict(net_income=8_687 * M, revenue=30_758 * M, gross_profit=13_919 * M,
             dep_amort=7_000 * M, capex=12_067 * M, equity=49_907 * M,
             long_term_debt=6_803 * M),
        dict(net_income=-5_833 * M, revenue=15_540 * M, gross_profit=-1_209 * M,
             dep_amort=7_422 * M, capex=7_676 * M, equity=44_120 * M,
             long_term_debt=13_052 * M),
        dict(net_income=778 * M, revenue=25_111 * M, gross_profit=5_613 * M,
             dep_amort=7_714 * M, capex=8_386 * M, equity=45_131 * M,
             long_term_debt=13_056 * M),
        dict(net_income=8_539 * M, revenue=37_380 * M, gross_profit=14_120 * M,
             dep_amort=8_200 * M, capex=13_800 * M, equity=54_600 * M,
             long_term_debt=12_900 * M),
    ])

    # O 형태 — 리츠. 부채가 구조적으로 많고 ROE 가 낮습니다
    o = rows([
        dict(net_income=288 * M, revenue=1_103 * M, gross_profit=1_103 * M,
             dep_amort=421 * M, capex=22 * M, equity=5_457 * M,
             long_term_debt=4_320 * M),
        dict(net_income=301 * M, revenue=1_216 * M, gross_profit=1_216 * M,
             dep_amort=461 * M, capex=25 * M, equity=6_018 * M,
             long_term_debt=5_200 * M),
        dict(net_income=363 * M, revenue=1_328 * M, gross_profit=1_328 * M,
             dep_amort=508 * M, capex=28 * M, equity=6_417 * M,
             long_term_debt=5_800 * M),
        dict(net_income=436 * M, revenue=1_492 * M, gross_profit=1_492 * M,
             dep_amort=593 * M, capex=30 * M, equity=9_040 * M,
             long_term_debt=7_200 * M),
        dict(net_income=395 * M, revenue=1_652 * M, gross_profit=1_652 * M,
             dep_amort=699 * M, capex=32 * M, equity=10_518 * M,
             long_term_debt=8_600 * M),
        dict(net_income=359 * M, revenue=2_080 * M, gross_profit=2_080 * M,
             dep_amort=917 * M, capex=35 * M, equity=14_995 * M,
             long_term_debt=11_200 * M),
        dict(net_income=869 * M, revenue=3_344 * M, gross_profit=3_344 * M,
             dep_amort=1_502 * M, capex=40 * M, equity=28_156 * M,
             long_term_debt=16_400 * M),
        dict(net_income=872 * M, revenue=4_079 * M, gross_profit=4_079 * M,
             dep_amort=1_741 * M, capex=45 * M, equity=28_785 * M,
             long_term_debt=19_200 * M),
        dict(net_income=860 * M, revenue=5_271 * M, gross_profit=5_271 * M,
             dep_amort=2_305 * M, capex=50 * M, equity=37_124 * M,
             long_term_debt=25_600 * M),
        dict(net_income=920 * M, revenue=5_600 * M, gross_profit=5_600 * M,
             dep_amort=2_480 * M, capex=55 * M, equity=37_800 * M,
             long_term_debt=26_400 * M),
    ])

    specs = {"KO": ko, "MSFT": msft, "MU": mu, "O": o}
    names = {"KO": "COCA COLA CO", "MSFT": "MICROSOFT CORP",
             "MU": "MICRON TECHNOLOGY INC", "O": "REALTY INCOME CORP"}

    th = None
    try:
        import config
        th = config.screen_thresholds()
    except Exception:  # noqa: BLE001
        pass

    screens: dict[str, object] = {}
    for ticker, year_rows in specs.items():
        screen = buffett.Screen(ticker=ticker, name=names[ticker],
                                years=year_rows)
        screens[ticker] = buffett.run_checks(screen, th)

    # 데이터 부족 사례 — 판정 불가 처리를 확인하려면 하나는 있어야 합니다
    thin = buffett.Screen(
        ticker="ZZZZ", name="THIN DATA CORP",
        years=rows([
            dict(net_income=10 * M, revenue=100 * M, equity=80 * M),
            dict(net_income=12 * M, revenue=110 * M, equity=85 * M),
        ], start_year=2024),
        missing_tags=["capex", "dep_amort", "long_term_debt"],
    )
    screens["ZZZZ"] = buffett.run_checks(thin, th)

    return screens, {"FAKE": "데모 모드에서는 실제 조회를 하지 않습니다."}


def demo_market_caps() -> dict[str, float]:
    """오프라인 시가총액 (단위: 달러). 역DCF 입력값입니다.

    실제로는 yfinance 에서 실시간으로 받습니다.
    """
    M = 1_000_000.0
    return {
        "KO": 310_000 * M,
        "MSFT": 3_700_000 * M,
        "MU": 240_000 * M,
        "O": 52_000 * M,
    }


def demo_kr_screens() -> tuple[dict, dict]:
    """오프라인 국내 스크리닝 데이터 (DART 형태).

    삼성전자·SK하이닉스·KT&G 세 가지 성격:
      005930 — 대형 제조업, ROE 중간대, 자본집약
      000660 — 사이클 극단 (적자 연도 포함)
      033780 — 안정 소비재 (한국에서 버핏식 기준에 가장 가까운 성격)
    """
    import buffett
    import buffett_kr

    B = 100_000_000.0        # 억원

    def kr_rows(spec: list[dict], start_year: int = 2016):
        out = []
        for i, d in enumerate(spec):
            year = start_year + i
            d = dict(d)
            ni = d.get("net_income") or 0.0
            da = d.get("dep_amort") or 0.0
            d.setdefault("operating_cash_flow", ni + da * 1.1)
            d.setdefault("cash", abs(ni) * 1.2)
            d.setdefault("short_term_investments", abs(ni) * 0.8)
            d.setdefault("short_term_debt", (d.get("long_term_debt") or 0.0) * 0.5)
            out.append(buffett.YearRow(year=year, end=f"{year}-12-31", **d))
        return out

    # 삼성전자 형태 (단위: 억원)
    samsung = kr_rows([
        dict(net_income=227_000 * B / B * B, revenue=2_018_000 * B,
             gross_profit=810_000 * B, dep_amort=210_000 * B,
             capex=241_000 * B, equity=1_929_000 * B, long_term_debt=13_000 * B),
        dict(net_income=421_000 * B, revenue=2_396_000 * B,
             gross_profit=1_108_000 * B, dep_amort=228_000 * B,
             capex=427_000 * B, equity=2_144_000 * B, long_term_debt=12_000 * B),
        dict(net_income=443_000 * B, revenue=2_437_000 * B,
             gross_profit=1_136_000 * B, dep_amort=267_000 * B,
             capex=295_000 * B, equity=2_478_000 * B, long_term_debt=11_000 * B),
        dict(net_income=217_000 * B, revenue=2_304_000 * B,
             gross_profit=818_000 * B, dep_amort=289_000 * B,
             capex=253_000 * B, equity=2_628_000 * B, long_term_debt=9_000 * B),
        dict(net_income=264_000 * B, revenue=2_368_000 * B,
             gross_profit=890_000 * B, dep_amort=306_000 * B,
             capex=375_000 * B, equity=2_759_000 * B, long_term_debt=10_000 * B),
        dict(net_income=399_000 * B, revenue=2_796_000 * B,
             gross_profit=1_157_000 * B, dep_amort=320_000 * B,
             capex=471_000 * B, equity=3_046_000 * B, long_term_debt=11_000 * B),
        dict(net_income=556_000 * B, revenue=3_022_000 * B,
             gross_profit=1_138_000 * B, dep_amort=361_000 * B,
             capex=494_000 * B, equity=3_457_000 * B, long_term_debt=10_000 * B),
        dict(net_income=154_000 * B, revenue=2_589_000 * B,
             gross_profit=895_000 * B, dep_amort=398_000 * B,
             capex=531_000 * B, equity=3_632_000 * B, long_term_debt=9_000 * B),
        dict(net_income=341_000 * B, revenue=3_008_000 * B,
             gross_profit=1_095_000 * B, dep_amort=412_000 * B,
             capex=490_000 * B, equity=3_880_000 * B, long_term_debt=8_000 * B),
        dict(net_income=398_000 * B, revenue=3_240_000 * B,
             gross_profit=1_210_000 * B, dep_amort=430_000 * B,
             capex=510_000 * B, equity=4_120_000 * B, long_term_debt=8_000 * B),
    ])

    # SK하이닉스 형태 — 사이클 극단
    hynix = kr_rows([
        dict(net_income=29_600 * B, revenue=171_000 * B,
             gross_profit=50_000 * B, dep_amort=44_000 * B,
             capex=60_000 * B, equity=238_000 * B, long_term_debt=25_000 * B),
        dict(net_income=106_000 * B, revenue=301_000 * B,
             gross_profit=158_000 * B, dep_amort=51_000 * B,
             capex=104_000 * B, equity=346_000 * B, long_term_debt=23_000 * B),
        dict(net_income=155_000 * B, revenue=404_000 * B,
             gross_profit=217_000 * B, dep_amort=59_000 * B,
             capex=170_000 * B, equity=494_000 * B, long_term_debt=19_000 * B),
        dict(net_income=20_100 * B, revenue=270_000 * B,
             gross_profit=72_000 * B, dep_amort=78_000 * B,
             capex=129_000 * B, equity=519_000 * B, long_term_debt=36_000 * B),
        dict(net_income=47_600 * B, revenue=319_000 * B,
             gross_profit=106_000 * B, dep_amort=89_000 * B,
             capex=99_000 * B, equity=566_000 * B, long_term_debt=50_000 * B),
        dict(net_income=96_200 * B, revenue=430_000 * B,
             gross_profit=172_000 * B, dep_amort=97_000 * B,
             capex=135_000 * B, equity=649_000 * B, long_term_debt=58_000 * B),
        dict(net_income=22_400 * B, revenue=446_000 * B,
             gross_profit=137_000 * B, dep_amort=110_000 * B,
             capex=190_000 * B, equity=652_000 * B, long_term_debt=80_000 * B),
        dict(net_income=-91_400 * B, revenue=327_000 * B,
             gross_profit=-13_000 * B, dep_amort=125_000 * B,
             capex=72_000 * B, equity=552_000 * B, long_term_debt=131_000 * B),
        dict(net_income=197_000 * B, revenue=662_000 * B,
             gross_profit=289_000 * B, dep_amort=128_000 * B,
             capex=140_000 * B, equity=750_000 * B, long_term_debt=120_000 * B),
        dict(net_income=240_000 * B, revenue=780_000 * B,
             gross_profit=350_000 * B, dep_amort=135_000 * B,
             capex=190_000 * B, equity=980_000 * B, long_term_debt=110_000 * B),
    ])

    # KT&G 형태 — 안정 소비재
    ktng = kr_rows([
        dict(net_income=11_700 * B, revenue=45_000 * B,
             gross_profit=26_000 * B, dep_amort=1_800 * B,
             capex=2_400 * B, equity=72_000 * B, long_term_debt=1_000 * B),
        dict(net_income=11_500 * B, revenue=46_700 * B,
             gross_profit=26_900 * B, dep_amort=1_900 * B,
             capex=2_600 * B, equity=77_000 * B, long_term_debt=1_200 * B),
        dict(net_income=9_400 * B, revenue=44_700 * B,
             gross_profit=25_100 * B, dep_amort=2_000 * B,
             capex=3_100 * B, equity=80_000 * B, long_term_debt=1_100 * B),
        dict(net_income=10_400 * B, revenue=49_700 * B,
             gross_profit=27_600 * B, dep_amort=2_300 * B,
             capex=3_400 * B, equity=85_000 * B, long_term_debt=1_000 * B),
        dict(net_income=11_600 * B, revenue=53_000 * B,
             gross_profit=29_400 * B, dep_amort=2_500 * B,
             capex=2_900 * B, equity=90_000 * B, long_term_debt=900 * B),
        dict(net_income=9_700 * B, revenue=52_300 * B,
             gross_profit=28_800 * B, dep_amort=2_600 * B,
             capex=2_700 * B, equity=93_000 * B, long_term_debt=800 * B),
        dict(net_income=10_200 * B, revenue=58_600 * B,
             gross_profit=31_000 * B, dep_amort=2_700 * B,
             capex=2_800 * B, equity=96_000 * B, long_term_debt=800 * B),
        dict(net_income=11_800 * B, revenue=59_700 * B,
             gross_profit=32_200 * B, dep_amort=2_800 * B,
             capex=3_000 * B, equity=99_000 * B, long_term_debt=700 * B),
        dict(net_income=12_400 * B, revenue=61_500 * B,
             gross_profit=33_400 * B, dep_amort=2_900 * B,
             capex=3_100 * B, equity=102_000 * B, long_term_debt=700 * B),
        dict(net_income=13_100 * B, revenue=64_000 * B,
             gross_profit=35_000 * B, dep_amort=3_000 * B,
             capex=3_200 * B, equity=105_000 * B, long_term_debt=700 * B),
    ])

    th = buffett_kr.kr_thresholds()
    specs = {"005930": ("삼성전자", samsung),
             "000660": ("SK하이닉스", hynix),
             "033780": ("KT&G", ktng)}

    screens: dict[str, object] = {}
    for code, (name, year_rows) in specs.items():
        screen = buffett.Screen(ticker=code, name=name, years=year_rows)
        screens[code] = buffett.run_checks(screen, th)
    return screens, {}


def demo_kr_market_caps() -> dict[str, float]:
    """오프라인 국내 시가총액 (원)."""
    B = 100_000_000.0
    return {
        "005930": 5_400_000 * B,
        "000660": 3_600_000 * B,
        "033780": 150_000 * B,
    }


def demo_discovery_quotes() -> dict[str, dict[str, Quote]]:
    """발굴 탭용 오프라인 시세 — 스크리닝 대상 전체에 52주 고가·저가를 넣습니다.

    demo_payload() 는 관심종목만 덮으므로 발굴 탭(68+30종목)에서는 대부분이
    '조회 실패' 로 보입니다. 화면이 망가져 보이면 데모의 쓸모가 없어서,
    후보 전체에 결정적(deterministic) 값을 깔아둡니다 — 티커 해시로 만들므로
    같은 종목은 항상 같은 위치에 옵니다.
    """
    import config
    from sources.model import MarketStatus

    out: dict[str, dict[str, Quote]] = {"yahoo": {}, "naver": {}}
    base = demo_payload()
    out["yahoo"].update(base.get("yahoo") or {})
    out["naver"].update(base.get("naver") or {})

    def spread(symbol: str) -> tuple[float, float, float]:
        """티커에서 (현재가, 52주 고가, 52주 저가) 를 결정적으로 만듭니다."""
        h = sum(ord(c) * (i + 3) for i, c in enumerate(symbol))
        price = 20.0 + (h % 760)
        # 구간 위치를 0~100% 에 고르게 흩뿌립니다 (고가권·저가권·중간이 섞이게)
        band = (h % 101) / 100.0
        span = price * (0.18 + (h % 7) * 0.06)
        low = price - span * band
        high = low + span
        return price, high, low

    for ticker in config.screen_tickers():
        if ticker in out["yahoo"]:
            continue
        price, high, low = spread(ticker)
        out["yahoo"][ticker] = Quote(
            symbol=ticker, price=price, prev_close=price * 0.994,
            currency="USD", status=MarketStatus.REGULAR,
            extra={"high_52w": high, "low_52w": low},
        )

    for code, _name in config.screen_kr_candidates():
        if code in out["naver"]:
            continue
        price, high, low = spread(code)
        price, high, low = price * 1_000, high * 1_000, low * 1_000
        out["naver"][code] = Quote(
            symbol=code, price=price, prev_close=price * 1.003,
            currency="KRW", status=MarketStatus.CLOSED,
            extra={"high_52w": high, "low_52w": low},
        )
    return out


def demo_feargreed():
    """오프라인 공포탐욕지수. 세부 지표 중 둘을 극단에 둬서 강조 경로를 확인합니다."""
    import datetime as dt

    from sources.feargreed import COMPONENTS, Component, FearGreed

    today = dt.date.today()
    scores = {
        "market_momentum_sp500": 78.0,
        "stock_price_strength": 81.0,
        "stock_price_breadth": 58.0,
        "put_call_options": 46.0,
        "market_volatility_vix": 62.0,
        "safe_haven_demand": 22.0,
        "junk_bond_demand": 64.0,
    }
    from sources.feargreed import band_label

    fg = FearGreed(
        score=63.0, rating="greed", observed_at=today,
        previous_close=61.0, previous_week=55.0,
        previous_month=48.0, previous_year=39.0,
        components=[Component(key=k, score=scores[k], rating=band_label(scores[k]))
                    for k, _l, _d in COMPONENTS],
    )
    base = today - dt.timedelta(days=59)
    for i in range(60):
        value = 40.0 + 23.0 * (i / 59.0) + (3.0 if i % 7 == 0 else 0.0)
        fg.history.append(((base + dt.timedelta(days=i)).isoformat(), value))
    return fg


def demo_vix(inverted: bool = False):
    """오프라인 VIX 상태. inverted=True 로 백워데이션 경로도 확인합니다."""
    import datetime as dt

    from sources.fred import Observation, Series
    from sources.model import MarketStatus
    from sources.vix import build_state

    if inverted:
        levels = {"^VIX9D": 31.4, "^VIX": 28.6, "^VIX3M": 26.2, "^VIX6M": 25.1}
    else:
        levels = {"^VIX9D": 14.8, "^VIX": 16.4, "^VIX3M": 18.9, "^VIX6M": 20.1}

    quotes = {
        sym: Quote(symbol=sym, price=value, prev_close=value * 0.97,
                   currency="USD", status=MarketStatus.REGULAR)
        for sym, value in levels.items()
    }

    # FRED VIXCLS 5년 이력 — 백분위가 의미를 갖도록 분포를 흩뿌립니다
    today = dt.date.today()
    obs = []
    for i in range(1_260):                      # 약 5년 거래일
        day = today - dt.timedelta(days=1_260 - i)
        base = 15.0 + 7.0 * ((i * 37) % 100) / 100.0
        if (i * 53) % 101 > 94:                 # 간헐적 급등 구간
            base += 18.0
        obs.append(Observation(date=day, value=base))
    series = Series(series_id="VIXCLS", observations=obs)
    return build_state(quotes, series)


def demo_briefing():
    """미리보기용 증시 브리핑 한 편.

    실제 파일을 만들지 않고 객체만 돌려줍니다 — 미리보기 때문에
    briefings/ 에 가짜 파일이 생기면 실제 브리핑과 섞입니다.
    """
    import datetime as _dt

    import briefing_store as _bs

    return _bs.Briefing(
        date=_dt.date.today().isoformat(),
        title="(데모) 금리와 메모리 가격이 같은 방향을 보기 시작한 주",
        body="",
        fmt="md",
        sources=["https://www.federalreserve.gov/", "https://fred.stlouisfed.org/"],
        path="briefings/데모.md",
    )


def demo_kr_exports():
    """미리보기용 한국 반도체 수출.

    실제 보도자료 수치를 씁니다(2026년 9월) — 지어낸 숫자를 쓰면
    자리수 감각이 틀립니다.
    """
    from sources.kr_exports import SemiExports

    return SemiExports(
        year=2026, month=9,
        value_100m_usd=603.0,
        yoy_pct=262.8,
        source_url="https://www.motir.go.kr/",
        title="(데모) 2026년 9월 수출입 동향",
        matched="금액+증감률",
    )


# ──────────────────────────────────────────────────────────────────────────────
# 국내 스크리너 데모
# ──────────────────────────────────────────────────────────────────────────────

def demo_kr_vol_profiles(candidates):
    """국내 변동성 프로파일 — 고정 난수로 만든 가짜 일봉.

    seed 를 고정해 매번 같은 화면이 나오게 합니다. 레이아웃 확인용이라
    매번 달라지면 '바뀐 게 내 코드 때문인가' 를 판단할 수 없습니다.
    """
    import kr_screen  # noqa: PLC0415 - 순환 참조를 피해 지연 임포트

    profiles, errors = [], {}
    for idx, (code, name) in enumerate(candidates):
        rnd = random.Random(f"vol-{code}")
        # 앞 240일은 시끄럽게, 뒤 60일은 종목마다 다른 강도로 잦아들게
        calm = 0.004 + (idx % 5) * 0.004
        trend = 0.0012 if idx % 3 == 0 else (-0.0008 if idx % 3 == 1 else 0.0)
        price, closes = 50_000.0, []
        for day in range(300):
            sd = 0.022 if day < 240 else calm
            price *= math.exp(rnd.gauss(trend, sd))
            closes.append(price)
        if idx % 11 == 7:          # 몇 종목은 일부러 데이터 부족
            closes = closes[:60]
        # 거래대금 — 몇 종목은 일부러 바닥 밑으로 둡니다. 필터가 실제로
        # 걸러내는지 프리뷰에서 눈으로 보여야 합니다.
        thin = idx % 4 == 3
        base_vol = 3_000.0 if thin else rnd.uniform(40_000, 400_000)
        vols = [base_vol * rnd.uniform(0.6, 1.5) for _ in closes]
        p = kr_screen.profile(code, name, closes, vols)
        profiles.append(p)
        if p.error:
            errors[code] = p.error
    return profiles, errors


def demo_kr_value_rows(candidates):
    """국내 전통 밸류 지표 — 고정 가짜값."""
    import kr_screen  # noqa: PLC0415

    rows = []
    for code, name in candidates:
        rnd = random.Random(f"val-{code}")
        rows.append(kr_screen.ValueRow(
            ticker=code, name=name,
            pbr=round(rnd.uniform(0.3, 2.4), 2),
            per=round(rnd.uniform(4.0, 28.0), 1),
            div_yield=round(rnd.uniform(0.0, 6.0), 2),
        ))
    return rows


def demo_kr_companies(codes):
    """국내 기업개황 데모."""
    import sources.dart as _dart  # noqa: PLC0415

    names = dict(config.screen_kr_candidates())
    out = {}
    for idx, code in enumerate(codes):
        rnd = random.Random(f"co-{code}")
        out[code] = _dart.CompanyProfile(
            stock_code=code,
            corp_name=names.get(code, code),
            ceo=f"(데모) 대표이사 {rnd.choice('김이박최정')}OO",
            industry_code=str(rnd.randint(10, 99)) + str(rnd.randint(10, 99)),
            established=f"{1950 + idx % 50}{rnd.randint(1, 12):02d}"
                        f"{rnd.randint(1, 28):02d}",
            fiscal_month="12",
            homepage="(데모) 홈페이지 주소",
            address="(데모) 본사 주소",
        )
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 뉴스 · 공시 · 지표 데모
# ──────────────────────────────────────────────────────────────────────────────

def demo_inflation(specs):
    """물가 — 계열마다 다른 속도를 주어 '재가속/둔화' 가 둘 다 보이게."""
    import inflation  # noqa: PLC0415

    out = []
    for idx, (sid, label, sa) in enumerate(specs):
        base, recent = 0.0016, (0.0030 if idx % 3 == 0 else
                                0.0008 if idx % 3 == 1 else 0.0016)
        vals, p = [], 100.0
        for m in range(26):
            p *= (1 + (recent if m >= 23 else base))
            vals.append((f"2024-{(m % 12) + 1:02d}-01", p))
        vals = [(f"{2024 + i // 12}-{(i % 12) + 1:02d}-01", v)
                for i, (_d, v) in enumerate(vals)]
        out.append(inflation.build(sid, label, vals, seasonally_adjusted=sa))
    return out


def demo_liquidity():
    import liquidity  # noqa: PLC0415

    parts = [
        liquidity.Component("fed_assets", "연준 총자산", raw=6_580_000,
                            unit="millions", prev=6_612_000,
                            period="2026-11-05"),
        liquidity.Component("rrp", "역레포 (ON RRP)", raw=96.4,
                            unit="billions", prev=141.2),
        liquidity.Component("tga", "재무부 일반계정 (TGA)", raw=812.0,
                            unit="billions", prev=769.5),
    ]
    nl = liquidity.net_liquidity(*parts)
    extra = [
        ("미국 M2 통화량", "22.15조 달러", "2026-09-01"),
        ("ECB 총자산", "6.04조 유로", "2026-10-31"),
        ("일본은행 총자산", "742.00조 엔", "2026-10-31"),
    ]
    return nl, extra


def _cfg_kr_kind(sid: str) -> str:
    import config as _config  # noqa: PLC0415
    return _config.KR_MACRO_KIND.get(sid, "index")


def demo_kr_macro(specs):
    rows = []
    for idx, (sid, label) in enumerate(specs):
        rnd = random.Random(f"krm-{sid}")
        val = rnd.uniform(90, 130)
        yoy = rnd.uniform(-4, 9)
        kind = _cfg_kr_kind(sid)
        if kind == "rate":
            text = f"{rnd.uniform(2.4, 3.6):,.2f}%  (1년 전보다 {rnd.uniform(-0.6, 0.6):+.2f}%p)"
            note = "9월분"
        elif kind == "usd":
            text = f"{rnd.uniform(550, 1100):,.1f}억 달러  (전년동월비 {yoy * 4:+.1f}%)"
            note = "9월분"
        elif kind == "pct":
            text, note = f"전년동월비 {yoy / 2:+.1f}%", f"8월분 · 1년 전 {yoy / 3:+.1f}%"
        elif kind == "level":
            lv = rnd.uniform(99, 103)
            text = f"{lv:,.1f}  (1년 전보다 {rnd.uniform(-1.5, 2.0):+.1f})"
            note = "9월분 · 100 이 장기 추세"
        elif kind == "balance":
            text = f"{rnd.uniform(-12, 4):+.1f}  (1년 전보다 {rnd.uniform(-5, 5):+.1f})"
            note = "9월분 · 0 이 중립 · 긍정−부정 응답"
        else:
            text, note = f"전년동월비 {yoy:+.1f}%", f"9월분 · 지수 {val:,.1f}"
        rows.append((label, text, note))
    return rows


def demo_sector_news(sectors):
    from sources.news import Headline  # noqa: PLC0415

    out, errors = {}, {}
    for idx, (key, label, _q) in enumerate(sectors):
        if idx == len(sectors) - 1:
            errors[key] = "(데모) 헤드라인이 비었습니다."
            continue
        out[key] = [
            Headline(title=f"(데모) {label} 관련 헤드라인 {n}",
                     url="https://example.com",
                     source=f"데모 {['경제', '일보', '뉴스'][n % 3]}",
                     published="2026-11-11")
            for n in range(1, 4)
        ]
    return out, errors


def demo_market_filings():
    """시장 공시 데모 — 묶음·시장·꼬리표가 고루 나오게. 회사·제목은 실제
    양식을 흉내 냈을 뿐 실제 공시가 아닙니다 (접수번호도 지어낸 것)."""
    import sources.dart as _dart  # noqa: PLC0415

    rows = [
        # (날짜, 회사, 코드, 제목, 시장, rm, 제출인)
        ("2026-11-11", "삼성전자", "005930", "연결재무제표기준영업(잠정)실적(공정공시)", "Y", "유", ""),
        ("2026-11-11", "에코프로비엠", "247540", "단일판매ㆍ공급계약체결", "K", "코", ""),
        ("2026-11-11", "(데모) 바이오A", "222222", "기술이전계약체결", "K", "코", ""),
        ("2026-11-11", "(데모) 코스닥B", "333333", "[기재정정]전환사채권발행결정", "K", "", ""),
        ("2026-11-11", "(데모) 코스닥C", "444444", "전환가액의조정", "K", "", ""),
        ("2026-11-11", "(데모) 코스닥D", "555555", "기타시장안내(조회공시요구)", "K", "코", "코스닥시장본부"),
        ("2026-11-10", "SK하이닉스", "000660", "주요사항보고서(자기주식취득결정)", "Y", "", ""),
        ("2026-11-10", "알테오젠", "196170", "주식등의대량보유상황보고서(일반)", "K", "", "(데모) 어떤자산운용"),
        ("2026-11-10", "현대차", "005380", "현금ㆍ현물배당결정", "Y", "유", ""),
        ("2026-11-10", "(데모) 코스피E", "666666", "주요사항보고서(유상증자결정)", "Y", "", ""),
        ("2026-11-10", "(데모) 코스피F", "777777", "단일판매ㆍ공급계약체결(자회사의주요경영사항)", "Y", "유", ""),
        ("2026-11-09", "(데모) 어떤기업", "000000", "최대주주변경을수반하는주식양수도계약체결", "K", "코", ""),
        ("2026-11-09", "(데모) 다른기업", "111111", "불성실공시법인지정", "K", "코", "코스닥시장본부"),
        ("2026-11-09", "(데모) 코스피G", "888888", "자기주식취득신탁계약체결결정", "Y", "유", ""),
        ("2026-11-09", "(데모) 코스닥H", "999999", "무상증자결정", "K", "코", ""),
        ("2026-11-08", "(데모) 코스피I", "121212", "회사분할결정", "Y", "유", ""),
        ("2026-11-08", "(데모) 코스닥J", "131313", "매출액또는손익구조30%(대규모법인은15%)이상변경", "K", "코", ""),
        ("2026-11-08", "(데모) 코스닥K", "141414", "전환청구권행사", "K", "코", ""),
    ]
    out = []
    for i, (d, n, c, t, cls, rm, filer) in enumerate(rows):
        kind = _dart.classify_detail(t)
        out.append(_dart.MarketFiling(
            date=d, corp_name=n, stock_code=c, title=t,
            kind=kind.group if kind else "", rcept_no=f"2026111{i:07d}",
            sub=kind.label if kind else "", market=_dart._MARKET_OF[cls],
            flags=_dart.title_flags(t, rm), filer=filer))
    _dart._sort_filings(out)
    return out


def demo_filing_scan():
    import sources.dart as _dart  # noqa: PLC0415

    filings = demo_market_filings()
    return _dart.FilingScan(
        filings=filings, scanned=1240, begin="2026-11-06",
        gaps=["거래소공시는 11-08 이후만 훑었습니다 (6쪽 한도)"])


def demo_sector_heat(specs):
    """섹터 온도 데모 — 업종마다 다른 추세를 줘서 색이 고루 나오게."""
    import sector_heat  # noqa: PLC0415

    closes, names = {}, {}
    for idx, spec in enumerate(specs):
        code, label = spec[0], spec[1]
        rnd = random.Random(f"heat-{code}")
        drift = (0.0004 if idx == 0 else
                 [0.0022, 0.0015, -0.0012, 0.0006, -0.0006, 0.0011,
                  -0.0018, 0.0002, 0.0018, -0.0003, 0.0009, -0.0009,
                  0.0004][(idx - 1) % 13])
        p, out = 10_000.0, []
        for _ in range(300):
            p *= math.exp(rnd.gauss(drift, 0.013))
            out.append(p)
        closes[code] = out
        names[code] = f"(데모) KODEX {label}"
    # 하나는 일부러 이름을 틀리게 — 화면이 잡아내는지 보이려고
    if len(specs) > 6:
        names[specs[6][0]] = "(데모) TIGER 화장품"
    return sector_heat.build(specs, closes, names)


def demo_chart_ohlc(candidates):
    """차트 조건용 가짜 일봉 (고·저·종). ({코드: {...}}, {코드: 오류})

    종목마다 모양을 다르게 줍니다 — 꾸준한 상승, 상승 뒤 눌림, 하락, 횡보.
    '상승 뒤 눌림' 이 있어야 양운 + CCI 과매도 조합이 화면에 실제로 잡힙니다.
    """
    out, errors = {}, {}
    for idx, (code, _name) in enumerate(candidates):
        rnd = random.Random(f"chart-{code}")
        shape = idx % 5
        price = 40_000.0 + rnd.uniform(0, 60_000)
        hs, ls, cs, vs = [], [], [], []
        base_vol = rnd.uniform(50_000, 500_000)
        n = 280
        for day in range(n):
            if shape == 0:                       # 꾸준한 상승
                drift = 0.0020
            elif shape == 1:                     # 상승 뒤 최근 눌림
                drift = 0.0030 if day < n - 9 else -0.016
            elif shape == 2:                     # 하락
                drift = -0.0018
            elif shape == 3:                     # 하락하다 최근 반등
                drift = -0.0020 if day < n - 14 else 0.012
            else:                                # 횡보
                drift = 0.0
            price *= math.exp(rnd.gauss(drift, 0.014))
            hi = price * (1 + abs(rnd.gauss(0, 0.007)))
            lo = price * (1 - abs(rnd.gauss(0, 0.007)))
            hs.append(hi), ls.append(lo), cs.append(price)
            # 최근 며칠은 몇 종목만 거래량이 늘게 — '거래량 동반' 이 화면에 보이도록
            surge = 2.2 if (idx % 3 == 0 and day >= n - 2) else 1.0
            vs.append(base_vol * rnd.uniform(0.7, 1.3) * surge)
        if idx % 13 == 9:                        # 몇 종목은 일부러 실패
            errors[code] = "(데모) 네이버 일봉 요청 실패: ReadTimeout → 야후도 비었음"
            continue
        if idx % 17 == 11:                       # 신규 상장
            hs, ls, cs, vs = hs[-70:], ls[-70:], cs[-70:], vs[-70:]
        # 시가 = 전일 종가 근처 (고저 안으로), 날짜 = 오늘까지의 평일
        ops = [min(max(cs[i - 1] if i else cs[0], ls[i]), hs[i]) for i in range(len(cs))]
        out[code] = {"high": hs, "low": ls, "close": cs, "volume": vs,
                     "open": ops, "date": _weekdays_back(len(cs))}
    return out, errors


def _weekdays_back(n: int) -> list[str]:
    """오늘까지의 평일 n 개 ('YYYY-MM-DD', 오래된 것부터)."""
    import datetime as _dt

    out, day = [], _dt.date.today()
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= _dt.timedelta(days=1)
    return out[::-1]


def demo_daily_bars(market: str, today: str | None = None):
    """전일 브리핑용 가짜 일봉 — {심볼: [(날짜, 종가)]}. 평일 22개, 오늘까지."""
    import datetime as _dt

    end = _dt.date.fromisoformat(today) if today else _dt.date.today()
    days: list[str] = []
    d = end
    while len(days) < 22:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= _dt.timedelta(days=1)
    days.reverse()
    out = {}
    for sym in config.daily_brief_symbols(market):
        rnd = random.Random(f"brief-{sym}")
        price = _BASE_HINTS.get(sym, 50.0 + rnd.uniform(0, 400))
        bars = []
        for day in days:
            price *= math.exp(rnd.gauss(0.0004, 0.012))
            bars.append((day, price))
        out[sym] = bars
    return out, {}


def demo_research():
    """리포트 목록 가짜 데이터 — (산업분석, 시황정보). 제목은 전부 지어낸 것."""
    from sources.research import Report  # noqa: PLC0415

    cats = ["반도체", "반도체", "반도체", "자동차", "자동차", "은행", "조선",
            "조선", "제약", "2차전지", "유틸리티", "반도체", "건설", "게임"]
    brokers = ["(데모)A증권", "(데모)B투자증권", "(데모)C증권"]
    ind = [Report(kind="industry", category=c,
                  title=f"(데모) {c} 산업 점검 {i + 1}",
                  broker=brokers[i % 3],
                  date=f"2026-11-{11 - i // 4:02d}",
                  url="https://example.com/read", pdf="https://example.com/r.pdf")
           for i, c in enumerate(cats)]
    mk = [Report(kind="market", title=f"(데모) 모닝 브리프 {i + 1}",
                 broker=brokers[i % 3], date=f"2026-11-{11 - i // 2:02d}",
                 url="https://example.com/read", pdf="https://example.com/m.pdf")
          for i in range(5)]
    return ind, mk


def demo_report_summaries() -> dict:
    """AI 요약의 가짜 데이터 — 데모 리포트 앞의 몇 건에만 붙입니다 (전부 지어낸 글)."""
    import report_summary  # noqa: PLC0415

    data = demo_semi_research()
    lists = [data["industry"]] + list(data["stocks"].values())
    text = ("핵심 주장\n- (데모) 메모리 가격 반등이 이어진다고 본다\n"
            "- (데모) 수요는 서버가 끌고 있다고 적었다\n"
            "근거 숫자\n- (데모) DRAM 계약가 +12% (3쪽)\n- (데모) 재고 일수 9주 → 6주 (5쪽)\n"
            "가정 · 위험\n- (데모) 데이터센터 투자가 줄면 결론이 달라진다고 밝혔다")
    out = {}
    for reports in lists:
        for r in reports[:2]:
            key = report_summary.key_of(r)
            if key:
                out[key] = {"summary": text, "title": r.title, "broker": r.broker,
                            "date": r.date, "model": "(데모)", "at": 0,
                            "input_tokens": 0, "output_tokens": 0}
    return out


def demo_semi_research():
    """반도체 리포트 화면의 가짜 데이터 — 제목·미리보기·숫자 전부 지어낸 것."""
    from sources.research import Report  # noqa: PLC0415

    brokers = ["(데모)A증권", "(데모)B투자증권", "(데모)C증권", "(데모)D증권"]
    themes = [
        ("메모리 가격 점검", "(데모) DRAM 고정거래가격이 석 달째 오르는 가운데 서버 수요가 재고를 줄이고 있다는 내용. HBM 비중과 내년 CapEx 전망을 다룬다."),
        ("HBM 공급 계획 비교", "(데모) 3사의 HBM 증설 일정과 공급 부족 지속 여부를 비교. 수요 쪽 가정이 바뀌면 결론이 달라진다고 적었다."),
        ("AI 서버 투자와 사이클", "(데모) 데이터센터 설비투자가 둔화될 때 메모리 사이클이 어떻게 꺾였는지 과거 사례를 대입."),
        ("NAND 감산 효과", "(데모) 낸드 감산 이후 재고 일수와 가격 반등 폭. 중국 업체의 증설이 변수."),
        ("파운드리 가동률", "(데모) 선단 공정 가동률과 고객사 수주 현황. 환율 영향을 따로 계산."),
    ]
    industry = [
        Report(kind="industry", category="반도체", title=f"(데모) {themes[i % 5][0]} {i + 1}",
               broker=brokers[i % 4], date=f"2026-11-{12 - i // 2:02d}",
               url="https://example.com/industry", pdf="https://example.com/i.pdf",
               research_id=str(46900 + i), preview=themes[i % 5][1])
        for i in range(9)]
    stocks = {}
    for code, name, base in (("005930", "삼성전자", 250_000), ("000660", "SK하이닉스", 2_400_000)):
        rows = []
        for i in range(8):
            goal = base * (1.0 + 0.04 * (i % 4))
            rows.append(Report(
                kind="company", title=f"(데모) {name} — {themes[i % 5][0]}",
                broker=brokers[i % 4], date=f"2026-11-{11 - i:02d}",
                url="https://example.com/company", pdf="https://example.com/c.pdf",
                research_id=str(97000 + i), item_code=code, item_name=name,
                preview=themes[(i + 2) % 5][1],
                opinion="Buy" if i % 5 else "Hold", goal_price=goal,
                prev_goal_price=goal * (0.92 if i % 3 == 0 else 1.0),
                price_then=base * 0.8))
        stocks[code] = rows
    return {"industry": industry, "stocks": stocks, "errors": {}, "scanned": 180}


def demo_fred_release_dates(today=None):
    """FRED releases/dates 모양의 가짜 응답 — 날짜는 지어낸 것입니다."""
    import datetime as _dt

    import calendar_events as ce  # noqa: PLC0415

    base = today or _dt.date.today()
    rows = []
    for i, (rid, name, key, _imp) in enumerate(ce.FRED_RELEASES):
        for k in range(2):
            d = base + _dt.timedelta(days=3 + i * 4 + k * 30)
            while d.weekday() >= 5:          # 발표는 평일
                d += _dt.timedelta(days=1)
            rows.append({"release_id": rid, "release_name": f"(데모) {key.title()}",
                         "date": d.isoformat()})
    return {"release_dates": rows}


# ──────────────────────────────────────────────────────────────────────────────
# 수급 · 배당 · 실적 데모 (지어낸 숫자 — 모양 확인용)
# ──────────────────────────────────────────────────────────────────────────────

def _demo_weekdays(n: int, end=None) -> list:
    import datetime as _dt  # noqa: PLC0415
    day = end or _dt.date(2026, 11, 11)
    out = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= _dt.timedelta(days=1)
    return out


def demo_kr_flows(codes) -> dict:
    from sources.naver_extra import FlowDay  # noqa: PLC0415

    out = {}
    for idx, code in enumerate(codes):
        rnd = random.Random(f"flow-{code}")
        if idx == len(codes) - 1 and len(codes) > 3:
            out[code] = ([], "", "(데모) HTTP 403")
            continue
        base = rnd.uniform(20_000, 400_000)
        bias_f = rnd.uniform(-0.6, 0.6)
        bias_i = rnd.uniform(-0.5, 0.5)
        ratio = rnd.uniform(8, 55)
        price = rnd.uniform(15_000, 300_000)
        rows = []
        for i, day in enumerate(_demo_weekdays(40)):
            f = base * (bias_f + rnd.gauss(0, 0.8))
            ins = base * (bias_i + rnd.gauss(0, 0.6))
            rows.append(FlowDay(
                date=day.isoformat(), close=round(price * (1 - i * 0.002), -1),
                volume=base * rnd.uniform(4, 9), inst=round(ins), foreign=round(f),
                foreign_ratio=round(ratio - i * bias_f * 0.02, 2)))
        out[code] = (rows, "(데모)", "")
    return out


def demo_dividends(symbols) -> dict:
    import datetime as _dt  # noqa: PLC0415

    today = _dt.date(2026, 11, 11)
    plans = {  # (간격 일, 금액, 발표일 여부)
        "MSFT": (91, 0.83, True), "AAPL": (91, 0.26, True), "MU": (91, 0.115, False),
        "O": (30, 0.2685, True), "QQQ": (91, 0.70, False), "SCHD": (91, 0.26, False),
        "UNH": (91, 2.21, True),
    }
    out = {}
    for sym in symbols:
        rnd = random.Random(f"div-{sym}")
        if sym.endswith((".KS", ".KQ")):
            gap, amt, ann = ((91, 361.0, False) if sym.startswith("005930")
                             else (365, rnd.choice([1200.0, 400.0, 3000.0]), False))
        else:
            gap, amt, ann = plans.get(sym, (91, 0.5, False))
        last = today - _dt.timedelta(days=rnd.randint(5, gap - 3))
        hist = []
        day = last
        for k in range(max(4, 900 // gap)):
            hist.append((day.isoformat(), amt * (1 - 0.03 * (k // 4))))
            day -= _dt.timedelta(days=gap + rnd.randint(-3, 3))
        ex = (last + _dt.timedelta(days=gap)).isoformat() if ann else ""
        out[sym] = {"history": sorted(hist), "ex_date": ex,
                    "pay_date": "", "error": ""}
    return out


def demo_us_earnings(symbols) -> dict:
    import datetime as _dt  # noqa: PLC0415

    today = _dt.date(2026, 11, 11)
    out = {}
    for sym in symbols:
        if sym in ("QQQ", "SCHD"):
            out[sym] = {"rows": [], "error": "야후에 실적 일정이 없습니다"}
            continue
        rnd = random.Random(f"eps-{sym}")
        eps = rnd.uniform(0.8, 6.0)
        rows = []
        first = today - _dt.timedelta(days=rnd.randint(10, 60))
        nxt = first + _dt.timedelta(days=91)
        rows.append({"date": nxt.isoformat(), "estimate": round(eps * 1.04, 2),
                     "reported": None, "surprise": None})
        for k in range(4):
            day = first - _dt.timedelta(days=91 * k)
            est = round(eps * (1 - 0.03 * k), 2)
            rep = round(est * (1 + rnd.gauss(0.03, 0.05)), 2)
            rows.append({"date": day.isoformat(), "estimate": est, "reported": rep,
                         "surprise": round((rep - est) / abs(est) * 100, 2)})
        out[sym] = {"rows": rows, "error": ""}
    return out


def demo_kr_quarters(codes) -> dict:
    from sources.naver_extra import Period  # noqa: PLC0415

    keys = ["202509", "202512", "202603", "202606", "202609", "202612"]
    out = {}
    for code in codes:
        rnd = random.Random(f"q-{code}")
        sales = rnd.uniform(3_000, 800_000)
        margin = rnd.uniform(-0.05, 0.25)
        periods = []
        for i, k in enumerate(keys):
            s = sales * (1 + 0.03 * i + rnd.gauss(0, 0.04))
            op = s * (margin + rnd.gauss(0, 0.03))
            periods.append(Period(k, f"{k[:4]}.{k[4:]}.", consensus=(i == len(keys) - 1),
                                  values={"매출액": round(s), "영업이익": round(op),
                                          "순이익": round(op * 0.8)}))
        out[code] = (periods, "")
    return out


def demo_fill_kr_surprise(views) -> None:
    """데모에서는 '기록이 쌓인 뒤' 모습을 보여주려고 서프라이즈를 채웁니다."""
    for v in views[:3]:
        if v.latest is None:
            continue
        rnd = random.Random(f"sur-{v.code}")
        v.surprise = {"매출액": round(rnd.gauss(1, 3), 1),
                      "영업이익": round(rnd.gauss(2, 9), 1), "순이익": None}
        v.surprise_seen = "2026-10-28"
