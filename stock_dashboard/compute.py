"""
파생 지표 계산 — 환율 환산, ADR/GDR 괴리율.

계산식은 모두 모듈 상단 주석에 명시합니다. 숫자를 추정하거나
임의로 반올림하지 않으며, 입력이 하나라도 없으면 None 을 반환합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import Instrument
from sources.model import Quote


@dataclass
class FxRates:
    """환율 묶음. 값이 없으면 None 입니다."""

    usdkrw: float | None = None
    eurusd: float | None = None

    def to_usd(self, amount: float, currency: str) -> float | None:
        """임의 통화 금액을 USD 로 변환합니다."""
        cur = (currency or "USD").upper()
        if cur == "USD":
            return amount
        if cur == "EUR":
            return amount * self.eurusd if self.eurusd else None
        if cur == "KRW":
            return amount / self.usdkrw if self.usdkrw else None
        return None

    def to_krw(self, amount: float, currency: str) -> float | None:
        """임의 통화 금액을 KRW 로 변환합니다."""
        cur = (currency or "USD").upper()
        if cur == "KRW":
            return amount
        usd = self.to_usd(amount, cur)
        if usd is None or not self.usdkrw:
            return None
        return usd * self.usdkrw

    def rate(self, currency: str) -> float | None:
        """1 단위 통화당 원화. 화면에 환율 자체를 보여주려면 필요합니다."""
        return self.to_krw(1.0, currency)


def resolve_fx(quotes: dict[str, Quote], override: float | None) -> FxRates:
    """시세 묶음에서 환율을 추출합니다. override 가 있으면 USD/KRW 를 덮어씁니다."""
    usdkrw = override
    if usdkrw is None:
        q = quotes.get("KRW=X")
        if q is not None and q.ok:
            usdkrw = q.price

    eurusd = None
    q = quotes.get("EURUSD=X")
    if q is not None and q.ok:
        eurusd = q.price

    return FxRates(usdkrw=usdkrw, eurusd=eurusd)


def pick_quote(inst: Instrument, data: dict[str, dict[str, Quote]]) -> Quote | None:
    """Instrument 에 맞는 Quote 를 꺼냅니다.

    1순위 심볼이 실패하면 alt_symbols 를 순서대로 시도합니다. 야후는 같은 종목을
    거래소별로 다르게 표기해서(SMSN.IL / SMSN.L) 폴백이 필요합니다.
    전부 실패하면 1순위 Quote(실패 사유 포함)를 그대로 돌려줍니다.
    """
    bucket = data.get(inst.source, {})

    primary = bucket.get(inst.symbol)
    if primary is not None and primary.ok:
        return primary

    for alt in inst.alt_symbols:
        candidate = bucket.get(alt)
        if candidate is not None and candidate.ok:
            candidate.extra = dict(candidate.extra, fallback=f"대체 심볼 {alt}")
            return candidate

    return primary


@dataclass
class Premium:
    """해외 상장 종목의 국내 본주 대비 괴리율."""

    #: 해외 가격을 본주 1주 기준 원화로 환산한 값
    implied_krw: float
    #: 비교 대상 국내 본주 가격 (KRW)
    local_krw: float
    #: 괴리율 (%). 양수면 해외가 비쌈.
    premium_pct: float


@dataclass
class PremiumRow:
    """괴리율 한 줄 — 계산 사슬 전체를 담습니다.

    화면에서 왼쪽→오른쪽으로 읽으면 계산이 그대로 보입니다:
        해외가 × 환율 ÷ 환산주수 = 본주환산가  vs  실제 본주가  →  괴리율
    두 탭(괴리율·국내 본주)으로 나뉘어 있을 때는 이 사슬이 보이지 않았습니다.
    """

    foreign: Instrument
    foreign_quote: Quote | None = None
    local: Instrument | None = None
    local_quote: Quote | None = None
    fx_rate: float | None = None
    premium: "Premium | None" = None

    #: 괴리율을 못 낸 이유. 빈 문자열이면 정상입니다.
    blocked: str = ""

    @property
    def foreign_price(self) -> float | None:
        q = self.foreign_quote
        if q is None or not q.ok:
            return None
        return q.extended_price if q.extended_price is not None else q.price

    @property
    def uses_extended(self) -> bool:
        """프리/애프터장 가격을 썼는가. 야간 괴리율의 핵심입니다."""
        q = self.foreign_quote
        return bool(q and q.ok and q.extended_price is not None)

    @property
    def shares_per_unit(self) -> float | None:
        return self.foreign.common_shares_per_unit

    @property
    def ok(self) -> bool:
        return self.premium is not None


def build_premium_rows(
    foreign_instruments,
    local_instruments,
    quotes: dict,
    fx: FxRates,
) -> tuple[list[PremiumRow], list]:
    """괴리율 줄들과 '짝이 없는 국내 종목' 을 함께 돌려줍니다.

    quotes: {source: {symbol: Quote}} 형태
    """
    by_code = {inst.symbol: inst for inst in local_instruments}
    paired: set[str] = set()
    rows: list[PremiumRow] = []

    for inst in foreign_instruments:
        fq = (quotes.get(inst.source) or {}).get(inst.symbol)
        peer_code = inst.local_peer
        peer = by_code.get(peer_code) if peer_code else None
        lq = None
        if peer is not None:
            paired.add(peer.symbol)
            lq = (quotes.get(peer.source) or {}).get(peer.symbol)

        rate = None
        currency = (fq.currency if fq and fq.ok and fq.currency
                    else inst.currency)
        if currency and currency != "KRW":
            rate = fx.rate(currency)

        row = PremiumRow(foreign=inst, foreign_quote=fq, local=peer,
                         local_quote=lq, fx_rate=rate)
        row.premium = compute_premium(inst, fq, lq, fx) if fq else None

        if row.premium is None:
            if fq is None or not fq.ok:
                row.blocked = "해외 시세를 받지 못했습니다."
            elif peer is None:
                row.blocked = f"비교할 국내 본주가 지정되지 않았습니다 ({peer_code})."
            elif lq is None or not lq.ok or not lq.price:
                row.blocked = "국내 본주 시세를 받지 못했습니다."
            elif rate is None:
                row.blocked = f"{currency}/KRW 환율을 받지 못했습니다."
            elif not inst.common_shares_per_unit:
                row.blocked = "1단위당 본주 주수가 설정되지 않았습니다."
            else:
                row.blocked = "계산에 필요한 값이 하나 이상 비었습니다."
        rows.append(row)

    unpaired = [inst for inst in local_instruments
                if inst.symbol not in paired]
    return rows, unpaired


def compute_premium(
    inst: Instrument,
    foreign: Quote,
    local: Quote | None,
    fx: FxRates,
) -> Premium | None:
    """ADR/GDR 괴리율을 계산합니다.

    계산식:
        본주환산가(KRW) = 해외가격 × 환율 ÷ (1단위당 본주 주수)
        괴리율(%)       = (본주환산가 ÷ 국내본주가 − 1) × 100

    예) 삼성전자 런던 GDR 이 1,200 USD, 환율 1,380 원, 1 GDR = 보통주 25주,
        국내 본주 70,000 원인 경우
          본주환산가 = 1,200 × 1,380 ÷ 25 = 66,240 원
          괴리율     = (66,240 ÷ 70,000 − 1) × 100 = −5.37%

    입력이 하나라도 없거나 0 이면 None 을 반환합니다.
    """
    if inst.common_shares_per_unit is None or not inst.common_shares_per_unit:
        return None
    if not foreign.ok or foreign.price is None:
        return None
    if local is None or not local.ok or not local.price:
        return None

    # 프리/애프터장 가격이 있으면 그걸 우선 사용합니다 (야간 괴리율이 핵심 용도).
    foreign_price = foreign.extended_price if foreign.extended_price is not None else foreign.price

    implied_krw = fx.to_krw(foreign_price, foreign.currency or inst.currency)
    if implied_krw is None:
        return None
    implied_krw /= inst.common_shares_per_unit

    premium_pct = (implied_krw / local.price - 1.0) * 100.0
    return Premium(implied_krw=implied_krw, local_krw=local.price, premium_pct=premium_pct)


def kospi_state(now=None) -> tuple[str, str]:
    """코스피 장 상태. 괴리율의 의미가 여기서 갈립니다.

    장이 닫혀 있으면 국내 본주가는 **종가로 고정**되므로, 괴리율은 실제
    가격차가 아니라 '마감 이후 해외에서 벌어진 움직임' 입니다.
    야간에 보는 사람에게는 이 구분이 수치 자체보다 중요합니다.
    """
    import datetime as _dt

    now = now or _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    if now.weekday() >= 5:
        return "frozen", "주말 · 본주가 금요일 종가로 고정"
    minutes = now.hour * 60 + now.minute
    if 9 * 60 <= minutes < 15 * 60 + 30:
        return "on", "코스피 장중 · 양쪽 모두 실시간"
    if minutes < 9 * 60:
        return "frozen", "개장 전 · 본주가 전일 종가로 고정"
    return "frozen", "마감 후 · 본주가 당일 종가로 고정"


