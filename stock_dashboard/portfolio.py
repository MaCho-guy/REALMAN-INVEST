"""보유 평가 — 수량 · 평균단가 → 평가금액 · 손익 · 비중 (원화 기준).

2026-11-11 추가. 지금까지 '내 종목' 은 관심종목 시세만 보여줬고, 얼마나
들고 있는지는 몰랐습니다. 수량과 평균단가를 알면 '오늘 계좌가 얼마
움직였나', '어느 종목에 쏠려 있나' 를 숫자로 볼 수 있습니다.

**어디에 적나 — 저장소가 아니라 Secrets.** 보유 수량은 개인 정보라
GitHub 에 올리면 안 됩니다. Streamlit Cloud 의 Secrets 맨 위에 한 줄:

    PORTFOLIO = "MSFT:10@410.5, AAPL:5@190, 005930:30@71000"

  - 종목:수량@평균단가 를 쉼표나 줄바꿈으로 나열
  - 미국은 티커, 한국은 6자리 코드. 평균단가는 그 종목의 통화(달러/원)
  - 같은 종목을 두 번 적으면 수량을 더하고 평균단가를 가중평균합니다

**계산의 한계 (화면에도 적습니다).**
  - 원화 손익은 **지금 환율**로 환산합니다. 매수 당시 환율을 모르므로
    미국 종목의 손익에는 환율 변화가 섞여 있고, 그걸 나눠 보이지 못합니다.
    그래서 손익률은 종목 통화 기준(달러 → 달러)으로 따로 적습니다.
  - 세금 · 수수료 · 배당은 넣지 않습니다.

순수 파이썬 — 스트림릿·네트워크 없음.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

ENV_KEY = "PORTFOLIO"

#: 데모 모드용 — 숫자는 지어낸 것입니다.
DEMO = "MSFT:12@380, AAPL:20@190, MU:30@95, QQQ:8@420, 005930:50@68000, 000660:10@180000"

#: 숫자 — 천 단위 쉼표(71,000)를 허용하되 항목 구분 쉼표와 헷갈리지 않게
#: '쉼표 + 정확히 세 자리' 만 숫자의 일부로 봅니다.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_ITEM = re.compile(r"([A-Za-z0-9.\-=^]+)\s*:\s*(" + _NUM + r")\s*@\s*(" + _NUM + r")")


@dataclass
class Position:
    symbol: str
    qty: float
    avg: float               # 종목 통화 기준 평균단가

    @property
    def market(self) -> str:
        return "kr" if self.symbol.isdigit() and len(self.symbol) == 6 else "us"

    @property
    def source(self) -> str:
        return "naver" if self.market == "kr" else "yahoo"


def parse(text: str) -> tuple[list[Position], list[str]]:
    """'MSFT:10@410.5, 005930:30@71000' → (보유 목록, 읽지 못한 조각)."""
    merged: dict[str, Position] = {}
    bad: list[str] = []
    text = text or ""
    pos = 0
    leftovers: list[str] = []
    for m in _ITEM.finditer(text):
        leftovers.append(text[pos:m.start()])
        pos = m.end()
        sym = m.group(1).upper()
        qty = float(m.group(2).replace(",", ""))
        avg = float(m.group(3).replace(",", ""))
        if qty <= 0 or avg <= 0:
            bad.append(m.group(0).strip())
            continue
        if sym in merged:
            p = merged[sym]
            total = p.qty + qty
            merged[sym] = Position(sym, total, (p.qty * p.avg + qty * avg) / total)
        else:
            merged[sym] = Position(sym, qty, avg)
    leftovers.append(text[pos:])
    # 항목 사이에 남은 글자 중 구분자가 아닌 것 = 읽지 못한 조각
    for chunk in leftovers:
        for piece in re.split(r"[,;\n]", chunk):
            if piece.strip():
                bad.append(piece.strip())
    return list(merged.values()), bad


def load(use_demo: bool = False) -> tuple[list[Position], list[str], str]:
    """(보유 목록, 읽지 못한 조각, 출처 설명). 비어 있으면 빈 목록."""
    if use_demo:
        pos, bad = parse(DEMO)
        return pos, bad, "데모 (지어낸 보유)"
    raw = os.environ.get(ENV_KEY, "")
    if not raw.strip():
        return [], [], ""
    pos, bad = parse(raw)
    return pos, bad, "Secrets 의 PORTFOLIO"


def symbols(positions: list[Position], source: str) -> list[str]:
    return [p.symbol for p in positions if p.source == source]


@dataclass
class Row:
    pos: Position
    name: str = ""
    currency: str = ""
    price: float | None = None
    prev: float | None = None
    fx: float = 1.0                       # 종목 통화 → 원
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.price is not None and not self.error

    @property
    def value_krw(self) -> float | None:
        return None if not self.ok else self.pos.qty * self.price * self.fx

    @property
    def cost_krw(self) -> float:
        """원가 — **지금 환율**로 환산 (매수 당시 환율을 모릅니다)."""
        return self.pos.qty * self.pos.avg * self.fx

    @property
    def pnl_krw(self) -> float | None:
        v = self.value_krw
        return None if v is None else v - self.cost_krw

    @property
    def pnl_pct(self) -> float | None:
        """종목 통화 기준 손익률 — 환율 변화가 섞이지 않습니다."""
        return None if not self.ok else (self.price / self.pos.avg - 1.0) * 100.0

    @property
    def today_krw(self) -> float | None:
        if not self.ok or self.prev is None:
            return None
        return self.pos.qty * (self.price - self.prev) * self.fx


@dataclass
class Summary:
    rows: list[Row]
    value_krw: float = 0.0
    cost_krw: float = 0.0
    today_krw: float = 0.0
    priced: int = 0

    @property
    def pnl_krw(self) -> float:
        return self.value_krw - self.cost_krw

    @property
    def pnl_pct(self) -> float | None:
        return None if not self.cost_krw else self.pnl_krw / self.cost_krw * 100.0

    @property
    def today_pct(self) -> float | None:
        base = self.value_krw - self.today_krw
        return None if not base else self.today_krw / base * 100.0

    def weight(self, row: Row) -> float | None:
        v = row.value_krw
        return None if v is None or not self.value_krw else v / self.value_krw * 100.0


def valuate(positions: list[Position], quote_of, usdkrw: float | None,
            names: dict | None = None) -> Summary:
    """quote_of(Position) → Quote|None. usdkrw 가 없으면 미국 종목은 값 없음."""
    names = names or {}
    rows: list[Row] = []
    for p in positions:
        q = quote_of(p)
        r = Row(pos=p, name=names.get(p.symbol, p.symbol))
        if q is None or not getattr(q, "ok", False):
            r.error = (getattr(q, "error", None) or "시세 없음") if q is not None \
                else "시세 없음"
            rows.append(r)
            continue
        cur = (getattr(q, "currency", "") or ("KRW" if p.market == "kr" else "USD")).upper()
        if cur == "KRW":
            fx = 1.0
        elif usdkrw:
            fx = float(usdkrw)
        else:
            r.error = "환율을 받지 못해 원화로 바꿀 수 없음"
            rows.append(r)
            continue
        r.currency, r.price, r.prev, r.fx = cur, q.price, q.prev_close, fx
        rows.append(r)
    s = Summary(rows=rows)
    for r in rows:
        if r.ok:
            s.value_krw += r.value_krw
            s.cost_krw += r.cost_krw
            s.today_krw += r.today_krw or 0.0
            s.priced += 1
    rows.sort(key=lambda r: -(r.value_krw or 0.0))
    return s
