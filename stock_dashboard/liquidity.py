"""
글로벌 유동성 — 연준 순유동성(net liquidity)과 주요국 중앙은행 자산.

**개념.** 연준이 푼 돈이 전부 시장에 머무는 게 아닙니다. 두 군데로
빨려 들어갑니다:

  역레포 (RRP)   머니마켓펀드가 연준에 하룻밤 맡겨둔 돈
  재무부 일반계정 (TGA)  정부가 연준에 넣어둔 세금·국채 대금

둘 다 연준 대차대조표 안에 있지만 **시장에 없는 돈**입니다. 그래서:

    순유동성 = 연준 총자산 − 역레포 − 재무부 계정

이 값이 늘면 시장에 도는 돈이 는 것이고, 줄면 준 것입니다. 2022~2023년에
연준이 자산을 줄이는데도 주가가 버틴 구간이 있었는데, 역레포가 더 빨리
줄어서 순유동성은 오히려 늘었기 때문입니다. 총자산만 보면 놓칩니다.

**이건 인과가 아니라 배경입니다.** 순유동성이 늘었다고 주가가 오르는 게
아니고, 상관도 구간마다 달라집니다. 왜 시장이 이렇게 움직이나를 설명할
때 보는 재료이지, 매매 신호가 아닙니다.

────────────────────────────────────────────────────────────────────────
**단위 함정 — 이 모듈이 조심하는 것**

FRED 는 계열마다 단위가 다릅니다. WALCL 은 백만 달러, RRPONTSYD 와
WTREGEN 은 십억 달러입니다. 그냥 빼면 **1000배 틀린 숫자**가 나오는데,
화면에는 그럴듯한 숫자로 보입니다. 조용히 틀리는 게 제일 나쁩니다.

그래서 이 모듈은 config 에 적힌 단위를 그대로 믿지 않고, **받은 값의
크기로 다시 확인합니다.** 연준 총자산은 어떤 단위로 적든 수조 달러
규모여야 하고, 역레포·TGA 는 그보다 한참 작아야 합니다. 그 관계가
깨지면 **숫자를 내놓지 않고 왜 못 내놓는지 적습니다.**
"""

from __future__ import annotations

from dataclasses import dataclass

#: 단위 배수 — 원 계열값에 곱하면 '십억 달러' 가 됩니다.
SCALE = {
    "billions": 1.0,
    "millions": 0.001,
    "thousands": 0.000_001,
    "units": 0.000_000_001,
    "hundred_millions": 0.1,      # 1억 단위 (일본은행 자료)
}

#: 상식 범위 (십억 달러). 2026년 기준으로 연준 총자산은 수조 달러,
#: 역레포·TGA 는 수백억~수천억 달러입니다. 이 범위를 크게 벗어나면
#: 단위를 잘못 읽은 것입니다.
SANE = {
    "fed_assets": (2_000.0, 20_000.0),      # 2조 ~ 20조
    "rrp": (0.0, 3_000.0),                  # 0 ~ 3조
    "tga": (0.0, 2_000.0),                  # 0 ~ 2조
}


@dataclass
class Component:
    """유동성 구성요소 하나."""

    key: str
    label: str
    raw: float | None = None          # 원 계열값
    unit: str = "billions"
    period: str = ""
    prev: float | None = None         # 4주 전 (추세용)
    error: str = ""

    @property
    def billions(self) -> float | None:
        if self.raw is None:
            return None
        return self.raw * SCALE.get(self.unit, 1.0)

    @property
    def prev_billions(self) -> float | None:
        if self.prev is None:
            return None
        return self.prev * SCALE.get(self.unit, 1.0)

    @property
    def change(self) -> float | None:
        """4주 변화 (십억 달러)."""
        a, b = self.billions, self.prev_billions
        return None if (a is None or b is None) else a - b

    #: 이 구성요소의 정상 범위 (현지통화 십억 단위). 비우면 SANE 을 봅니다.
    sane_range: tuple[float, float] | None = None
    currency: str = "달러"

    def _range(self) -> tuple[float, float] | None:
        return self.sane_range or SANE.get(self.key)

    def suggest_unit(self) -> str:
        """지금 값이 어느 단위면 정상 범위에 들어가는지 **계산해서**
        알려줍니다.

        "단위가 틀린 것 같습니다" 까지만 말하면 어느 단위로 고쳐야 할지는
        다시 찾아봐야 합니다. 배수가 1000 단위로 떨어지는 문제라 기계가
        맞혀 줄 수 있습니다 — 실제로 TGA 를 billions 로 적어 95경 달러가
        나왔을 때, millions 로 읽으면 맞는다는 걸 바로 알 수 있었습니다.
        """
        rng = self._range()
        if self.raw is None or rng is None:
            return ""
        lo, hi = rng
        fits = [name for name, mul in SCALE.items()
                if lo <= self.raw * mul <= hi]
        if not fits or self.unit in fits:
            return ""
        best = fits[0]
        return (f"'{best}' 로 읽으면 "
                f"{self.raw * SCALE[best]:,.0f}십억 이 되어 범위에 "
                f"들어갑니다 — config 의 단위를 '{best}' 로 고치십시오.")

    def sanity(self) -> str:
        """단위가 말이 되는지. 문제 없으면 빈 문자열."""
        v = self.billions
        if v is None:
            return ""
        rng = self._range()
        if rng is None:
            return ""
        lo, hi = rng
        if not (lo <= v <= hi):
            tip = self.suggest_unit()
            return (f"{self.label} 이 {v:,.0f}십억 {self.currency}로 "
                    f"계산됐습니다 — 정상 범위({lo:,.0f}~{hi:,.0f})를 "
                    f"벗어납니다. FRED 계열 단위('{self.unit}')가 "
                    "틀렸습니다."
                    + (f" {tip}" if tip else ""))
        return ""


@dataclass
class NetLiquidity:
    """순유동성 = 연준 총자산 − 역레포 − 재무부 계정."""

    value: float | None = None        # 십억 달러
    prev: float | None = None
    period: str = ""
    parts: list[Component] | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and self.value is not None

    @property
    def change(self) -> float | None:
        if self.value is None or self.prev is None:
            return None
        return self.value - self.prev

    @property
    def direction(self) -> str:
        c = self.change
        if c is None:
            return "알 수 없음"
        if c > 50:
            return "늘고 있음"
        if c < -50:
            return "줄고 있음"
        return "거의 그대로"


def net_liquidity(fed: Component, rrp: Component,
                  tga: Component) -> NetLiquidity:
    """세 구성요소 → 순유동성. **단위 검사를 통과해야 계산합니다.**"""
    parts = [fed, rrp, tga]
    problems = [p.error for p in parts if p.error]
    problems += [msg for msg in (p.sanity() for p in parts) if msg]
    if problems:
        return NetLiquidity(parts=parts, error=" / ".join(problems[:2]))

    vals = [p.billions for p in parts]
    if any(v is None for v in vals):
        missing = [p.label for p in parts if p.billions is None]
        return NetLiquidity(
            parts=parts,
            error=f"{', '.join(missing)} 을(를) 받지 못해 계산할 수 "
                  "없습니다. 부분값만으로 '순유동성' 이라고 적으면 "
                  "틀린 숫자가 됩니다.")

    prevs = [p.prev_billions for p in parts]
    prev_total = (vals[0] - vals[1] - vals[2]
                  if any(x is None for x in prevs)
                  else prevs[0] - prevs[1] - prevs[2])
    return NetLiquidity(
        value=vals[0] - vals[1] - vals[2],
        prev=None if any(x is None for x in prevs) else prev_total,
        period=fed.period, parts=parts,
    )


def summary_line(nl: NetLiquidity) -> str:
    if not nl.ok:
        return nl.error or "순유동성을 계산하지 못했습니다."
    bits = [f"연준 순유동성 {nl.value / 1000:,.2f}조 달러"]
    c = nl.change
    if c is not None:
        bits.append(f"4주 {c:+,.0f}십억 ({nl.direction})")
    return " · ".join(bits)
