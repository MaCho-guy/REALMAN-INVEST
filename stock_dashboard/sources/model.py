"""모든 데이터 소스가 공통으로 반환하는 시세 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MarketStatus(str, Enum):
    """카드에 표시할 거래 상태 배지."""

    LIVE = "실시간"          # 24시간 거래 (DEX 등)
    REGULAR = "정규장"
    PRE = "프리장"
    POST = "애프터장"
    CLOSED = "장마감"
    UNKNOWN = "—"


@dataclass
class Quote:
    """단일 종목의 시세 스냅샷.

    실패한 조회도 Quote 로 반환합니다 (error 필드가 채워짐).
    이렇게 하면 한 종목이 실패해도 섹션 전체가 비지 않습니다.
    """

    symbol: str
    price: float | None = None
    prev_close: float | None = None
    currency: str = ""
    status: MarketStatus = MarketStatus.UNKNOWN

    #: 프리장/애프터장 가격 (있을 때만)
    extended_price: float | None = None
    extended_label: str = ""

    #: 소스별 추가 지표. 예) {"funding_8h": 0.0012, "open_interest": 12345}
    extra: dict = field(default_factory=dict)

    #: 조회 실패 사유. None 이면 정상.
    error: str | None = None

    # ── 파생값 ────────────────────────────────────────────────────────────────

    @property
    def ok(self) -> bool:
        return self.error is None and self.price is not None

    @property
    def change(self) -> float | None:
        """전일 대비 등락액."""
        if self.price is None or self.prev_close is None:
            return None
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float | None:
        """전일 대비 등락률(%). prev_close 가 0 이면 None."""
        if self.price is None or not self.prev_close:
            return None
        return (self.price / self.prev_close - 1.0) * 100.0

    @property
    def extended_change_pct(self) -> float | None:
        """정규장 종가 대비 프리/애프터 등락률(%)."""
        if self.extended_price is None or not self.price:
            return None
        return (self.extended_price / self.price - 1.0) * 100.0

    @classmethod
    def failed(cls, symbol: str, reason: str) -> "Quote":
        return cls(symbol=symbol, error=reason)
