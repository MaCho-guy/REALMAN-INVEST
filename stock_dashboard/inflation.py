"""
물가 분석 — CPI · PPI 를 '지수' 에서 '속도' 로 바꿉니다.

**왜 필요한가.** FRED 가 주는 CPIAUCSL 은 지수(index)입니다. 317.6 같은
숫자 자체는 아무 뜻이 없습니다. 뉴스가 말하는 "물가 3.2%" 는 그 지수의
**전년동월비**입니다. 그런데 전년동월비 하나만 보면 늦습니다 — 12개월
전 숫자를 끌고 다니기 때문입니다.

그래서 세 가지를 나란히 봅니다:

  전월비 (MoM)        한 달 변화. 노이즈가 큽니다
  전년동월비 (YoY)    뉴스에 나오는 숫자. 느리지만 안정적입니다
  3개월 연율 (3m SAAR) 최근 3개월 변화를 1년치로 환산. **가장 빠릅니다**

3개월 연율이 전년동월비보다 높으면 **물가가 다시 붙고 있다**는 뜻이고,
낮으면 식고 있다는 뜻입니다. 둘이 교차하는 지점이 방향 전환입니다.
이건 해석이 아니라 산술입니다 — 전년동월비는 과거 9개월을 아직 평균에
담고 있으니까요.

**헤드라인과 근원(core)을 같이 봅니다.** 헤드라인은 유가·식료품이
흔들고, 근원은 그걸 뺀 것입니다. 연준이 보는 건 근원 쪽입니다.

주의: FRED 의 CPI 계열은 **계절조정(SA)** 과 비조정(NSA)이 섞여 있습니다.
전월비·3개월 연율은 계절조정 계열에서만 의미가 있습니다. 비조정 계열에
쓰면 계절 패턴이 그대로 '물가 상승' 으로 보입니다. config 에 어느
쪽인지 적어 두고, 비조정이면 전년동월비만 계산합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 3개월 연율로 바꿀 때 쓰는 지수. (1 + r)^4 - 1 — 분기를 네 번 거듭합니다.
QUARTERS_PER_YEAR = 4

#: 재가속으로 볼 격차 (%p). 3개월 연율이 전년동월비보다 이만큼 높으면
#: '다시 붙는 중' 으로 읽습니다. 0.3 보다 작은 차이는 반올림 노이즈와
#: 구분이 안 됩니다.
REACCEL_GAP = 0.5


@dataclass
class Reading:
    """물가 계열 하나의 현재 속도."""

    key: str
    label: str
    index: float | None = None       # 원 지수값
    period: str = ""                 # 관측 시점 (YYYY-MM-DD)
    mom: float | None = None         # 전월비 %
    yoy: float | None = None         # 전년동월비 %
    saar3: float | None = None       # 3개월 연율 %
    seasonally_adjusted: bool = True
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and self.yoy is not None

    @property
    def gap(self) -> float | None:
        """3개월 연율 − 전년동월비. 양수면 최근이 더 뜨겁습니다."""
        if self.saar3 is None or self.yoy is None:
            return None
        return self.saar3 - self.yoy

    @property
    def direction(self) -> str:
        """재가속 / 둔화 / 비슷 / 알 수 없음."""
        g = self.gap
        if g is None:
            return "알 수 없음"
        if g >= REACCEL_GAP:
            return "재가속"
        if g <= -REACCEL_GAP:
            return "둔화"
        return "비슷"


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return (new / old - 1.0) * 100.0


def annualize(ratio: float, periods: int) -> float:
    """기간 수익률을 연율로. (1+r)^periods - 1."""
    return ((1.0 + ratio) ** periods - 1.0) * 100.0


def build(key: str, label: str, values: list[tuple[str, float]], *,
          seasonally_adjusted: bool = True) -> Reading:
    """(날짜, 지수) 목록 → Reading.

    values 는 **오래된 것부터** 정렬돼 있어야 합니다. 월간 계열을
    가정합니다 — 주간·일간 계열을 넣으면 '전월비' 가 전주비가 됩니다.
    """
    pts = [(d, v) for d, v in values if v is not None]
    if len(pts) < 13:
        return Reading(key=key, label=label,
                       seasonally_adjusted=seasonally_adjusted,
                       error=f"관측치가 {len(pts)}개뿐입니다 "
                             "(전년동월비에 최소 13개 필요).")
    last_date, last = pts[-1]
    prev = pts[-2][1]
    year_ago = pts[-13][1]
    three_ago = pts[-4][1]

    mom = saar3 = None
    if seasonally_adjusted:
        mom = pct_change(last, prev)
        r3 = pct_change(last, three_ago)
        if r3 is not None:
            saar3 = annualize(r3 / 100.0, QUARTERS_PER_YEAR)

    return Reading(
        key=key, label=label, index=last, period=last_date,
        mom=mom, yoy=pct_change(last, year_ago), saar3=saar3,
        seasonally_adjusted=seasonally_adjusted,
    )


def summary_line(readings: list[Reading]) -> str:
    """한 줄 요약. 근원 지표를 우선합니다 — 연준이 보는 쪽입니다."""
    usable = [r for r in readings if r.ok]
    if not usable:
        return "물가 지표를 받지 못했습니다."
    core = next((r for r in usable if "근원" in r.label), usable[0])
    bits = [f"{core.label} 전년동월비 {core.yoy:+.1f}%"]
    if core.saar3 is not None:
        bits.append(f"3개월 연율 {core.saar3:+.1f}%")
    hot = [r for r in usable if r.direction == "재가속"]
    cool = [r for r in usable if r.direction == "둔화"]
    if hot:
        bits.append(f"재가속 {len(hot)}개 ({', '.join(r.label for r in hot)})")
    elif cool:
        bits.append(f"둔화 {len(cool)}개")
    else:
        bits.append("최근 3개월과 1년 속도가 비슷")
    return " · ".join(bits)
