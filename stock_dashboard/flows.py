"""
종목별 수급 요약 — 외국인·기관이 최근 며칠 동안 얼마나 사고 팔았나.

입력은 일별 순매매(주) 목록(최신순)이고, 여기서는 **더하고 세기만** 합니다.

  5일·20일 누적     순매매 주식 수의 합
  금액(근사)        Σ(그날 순매매 주식 수 × 그날 종가). 실제 체결가는 그날
                    여러 가격이라 정확한 금액이 아닙니다 — 크기 감을 잡는 용도.
  연속 일수         가장 최근 날부터 같은 방향(+/−)이 며칠 이어졌나.
                    0 인 날에서 끊습니다.
  거래량 대비       20일 외국인 순매수 ÷ 20일 거래량. 같은 '100만 주' 라도
                    거래가 적은 종목에서는 무게가 다릅니다.
  보유율 변화       오늘 외국인 보유율 − 20거래일 전 보유율 (%p)

해석(누가 사니 오른다 등)은 하지 않습니다. 수급은 가격의 원인이기도 하고
결과이기도 해서, 숫자만으로 방향을 말할 수 없습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FlowSummary:
    code: str
    name: str = ""
    source: str = ""
    error: str = ""
    days: int = 0
    last_date: str = ""
    net: dict[str, dict[int, float | None]] = field(default_factory=dict)
    amount: dict[str, dict[int, float | None]] = field(default_factory=dict)
    streak: dict[str, int] = field(default_factory=dict)
    ratio: float | None = None
    ratio_change: float | None = None
    vol_share20: float | None = None   # 외국인 20일 순매수 / 20일 거래량 (%)
    spark: list[float] = field(default_factory=list)  # 외국인 일별, 오래된→최신
    held: bool = False


WHO = ("foreign", "inst", "person")
WHO_LABEL = {"foreign": "외국인", "inst": "기관", "person": "개인"}


def _sum(rows, attr: str, n: int) -> float | None:
    vals = [getattr(r, attr) for r in rows[:n]]
    if len(vals) < n or any(v is None for v in vals):
        # 일부라도 비면 '모름' — 0 으로 메우면 조용히 틀린 합계가 됩니다
        return None
    return float(sum(vals))


def _amount(rows, attr: str, n: int) -> float | None:
    if len(rows) < n:
        return None
    total = 0.0
    for r in rows[:n]:
        q = getattr(r, attr)
        if q is None or r.close is None:
            return None
        total += q * r.close
    return total


def streak(values: list[float | None]) -> int:
    """최근부터 같은 부호가 이어진 날 수. 순매수 +n, 순매도 −n."""
    n = 0
    sign = 0
    for v in values:
        if v is None or v == 0:
            break
        s = 1 if v > 0 else -1
        if sign == 0:
            sign = s
        if s != sign:
            break
        n += 1
    return n * sign


def summarize(code: str, rows, *, name: str = "", source: str = "",
              error: str = "", held: bool = False) -> FlowSummary:
    """rows 는 최신순 FlowDay 목록."""
    rows = list(rows or [])
    out = FlowSummary(code=code, name=name, source=source, error=error,
                      days=len(rows), held=held,
                      last_date=rows[0].date if rows else "")
    if not rows:
        return out
    for who in WHO:
        if all(getattr(r, who) is None for r in rows):
            continue
        out.net[who] = {n: _sum(rows, who, n) for n in (1, 5, 20)}
        out.amount[who] = {n: _amount(rows, who, n) for n in (5, 20)}
        out.streak[who] = streak([getattr(r, who) for r in rows])
    out.ratio = rows[0].foreign_ratio
    if len(rows) > 20 and rows[20].foreign_ratio is not None and out.ratio is not None:
        out.ratio_change = out.ratio - rows[20].foreign_ratio
    f20 = out.net.get("foreign", {}).get(20)
    vol20 = _sum(rows, "volume", 20)
    if f20 is not None and vol20:
        out.vol_share20 = f20 / vol20 * 100
    out.spark = [r.foreign or 0.0 for r in reversed(rows[:20])]
    return out


def rank_key(s: FlowSummary) -> tuple:
    """보유 종목 먼저, 그다음 외국인+기관 20일 금액이 큰 순."""
    tot = 0.0
    for who in ("foreign", "inst"):
        tot += abs((s.amount.get(who) or {}).get(20) or 0.0)
    return (0 if s.held else 1, 0 if not s.error else 1, -tot)
