"""
국내 전용 스크리너 — 변동성 수축 + 신고가, 그리고 전통 밸류 지표.

**왜 국내만 따로인가.**

미국 발굴은 '버핏식 품질 기준'만으로 충분합니다. 종목 수가 많고 재무가
안정적이라 재무제표만 봐도 목록이 줄어듭니다. 국내는 사정이 다릅니다 —
후보가 50종목 남짓이라 재무 기준만으로는 거의 안 걸러지고, 대신 **주가
변동성이 훨씬 큽니다.** 52주 신고가를 단독으로 쓰면 급등 후 되돌림
구간이 대거 섞여 들어옵니다.

그래서 국내에는 변동성을 같이 봅니다:

  변동성 수축비 = 최근 3개월 변동성 ÷ 최근 1년 변동성

이 값이 1보다 작으면 **움직임이 잦아든 상태**입니다. 신고가 근처인데
변동성이 잦아들었다는 건, 급등 중이 아니라 높은 가격대에서 자리를 잡고
있다는 뜻입니다. 둘을 **곱이 아니라 교집합**으로 씁니다 — 하나로 합친
점수를 만들면 왜 걸렸는지 설명이 안 됩니다.

**무엇을 주장하지 않는가.** 이건 '오를 종목'이 아니라 '읽어볼 목록'
입니다. 변동성 수축은 방향을 말해주지 않습니다 — 위로도 아래로도
터질 수 있습니다. 걸러진 종목은 공시를 읽어야 판단이 됩니다.

데이터: 야후 파이낸스 일봉 1년 (키 불필요). 국내 종목은 `.KS`(코스피) /
`.KQ`(코스닥) 접미사가 필요하고, 어느 쪽인지는 코드만 봐서는 알 수
없어서 `.KS` 를 먼저 시도하고 비면 `.KQ` 로 다시 받습니다.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# 기준값
# ──────────────────────────────────────────────────────────────────────────────

#: 변동성을 재는 창. 거래일 기준입니다 (1년 ≈ 252일, 3개월 ≈ 63일).
LONG_WINDOW = 252
SHORT_WINDOW = 63

#: 변동성이 '잦아들었다'고 보는 기준. 0.80 이면 최근 3개월이 1년 평균보다
#: 20% 이상 조용해진 상태입니다. 0.9 로 두면 거의 전부 통과하고, 0.7 로
#: 두면 1~2 종목만 남습니다 — 50종목 모집단에서 둘 다 쓸모가 없습니다.
CONTRACTION_MAX = 0.80

#: 신고가 '근처'의 범위. 52주 고가 대비 몇 % 이상인가.
#: 100% 정확히 신고가만 보면 하루 차이로 목록이 통째로 바뀝니다.
NEAR_HIGH_PCT = 90.0

#: 유동성 바닥 — 20일 평균 거래대금(원). 모닝 브리프가 쓰는 5억 원을
#: 그대로 가져왔습니다. **왜 필요한가:** 코스닥에는 하루 거래대금이
#: 수천만 원인 종목이 흔합니다. 변동성 수축이 잡혀도 실제로는 '거래가
#: 없어서 안 움직인 것' 이고, 사려고 하면 호가가 비어 있습니다.
#: 걸러내지 않으면 스크리너가 **살 수 없는 종목**을 추천합니다.
MIN_TURNOVER = 500_000_000.0

#: 거래대금을 재는 기간 (거래일).
TURNOVER_WINDOW = 20

#: 계산에 필요한 최소 일봉 수. 이보다 적으면 변동성을 신뢰할 수 없습니다
#: (신규 상장·거래정지). 숫자를 내는 대신 '알 수 없음' 으로 둡니다.
MIN_BARS = 120

#: 전통 밸류 기준. 한국 시장에서 오래 쓰여 온 선입니다.
#: 이 숫자들은 **관행이지 법칙이 아닙니다** — 업종마다 적정선이 다릅니다.
PBR_MAX = 1.0
PER_MAX = 12.0
DIV_MIN = 2.5          # 배당수익률 %


# ──────────────────────────────────────────────────────────────────────────────
# 변동성
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VolProfile:
    """한 종목의 변동성·위치 프로파일."""

    ticker: str
    name: str = ""
    bars: int = 0
    price: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    vol_long: float | None = None      # 연율 변동성 (%), 1년
    vol_short: float | None = None     # 연율 변동성 (%), 3개월
    return_1y: float | None = None     # %
    turnover: float | None = None      # 20일 평균 거래대금 (원)
    # ── 2026-11-12 추가: 상대강도 · 되돌림 · 거래대금 급증 스크리너용 ──────────
    ret_1w: float | None = None        # 5거래일 수익률 (%)
    ret_1m: float | None = None        # 21거래일
    ret_3m: float | None = None        # 63거래일
    ret_6m: float | None = None        # 126거래일
    low_20d: float | None = None       # 최근 20거래일 최저 종가
    ma20: float | None = None
    ma60: float | None = None
    turnover_5d: float | None = None   # 5일 평균 거래대금
    turnover_60d: float | None = None  # 60일 평균 거래대금
    error: str = ""

    @property
    def off_low_pct(self) -> float | None:
        """최근 20일 저점에서 몇 % 올라와 있나."""
        if self.price is None or not self.low_20d:
            return None
        return (self.price / self.low_20d - 1.0) * 100.0

    @property
    def turnover_surge(self) -> float | None:
        """5일 평균 거래대금 ÷ 60일 평균. 2 면 평소의 두 배."""
        if not self.turnover_60d or self.turnover_5d is None:
            return None
        return self.turnover_5d / self.turnover_60d

    @property
    def liquid(self) -> bool:
        """거래대금이 바닥을 넘는가. **모르면 통과시키지 않습니다** —
        거래량을 못 받은 종목을 '유동성 충분' 으로 보면 걸러내는 의미가
        없어집니다."""
        return self.turnover is not None and self.turnover >= MIN_TURNOVER

    @property
    def turnover_label(self) -> str:
        if self.turnover is None:
            return "—"
        if self.turnover >= 100_000_000:
            return f"{self.turnover / 100_000_000:,.1f}억"
        return f"{self.turnover / 10_000:,.0f}만"

    @property
    def ok(self) -> bool:
        return self.error == "" and self.bars >= MIN_BARS

    @property
    def contraction(self) -> float | None:
        """최근 변동성 ÷ 장기 변동성. 1 미만이면 잦아든 것."""
        if not self.ok or not self.vol_long or self.vol_short is None:
            return None
        return self.vol_short / self.vol_long

    @property
    def pct_of_high(self) -> float | None:
        if self.price is None or not self.high_52w:
            return None
        return self.price / self.high_52w * 100.0

    @property
    def band_position(self) -> float | None:
        if (self.price is None or self.high_52w is None
                or self.low_52w is None or self.high_52w <= self.low_52w):
            return None
        return ((self.price - self.low_52w)
                / (self.high_52w - self.low_52w) * 100.0)


def annualized_vol(closes: list[float], window: int) -> float | None:
    """연율 변동성 (%).

    일간 로그수익률의 표준편차에 √252 를 곱합니다. 로그수익률을 쓰는 건
    단순수익률이 상승·하락에 비대칭이기 때문입니다 (+50% 뒤 -50% 는
    원금이 아닙니다).
    """
    tail = [c for c in closes[-(window + 1):] if c and c > 0]
    if len(tail) < 20:
        return None
    rets = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    if len(rets) < 19:
        return None
    try:
        sd = statistics.stdev(rets)
    except statistics.StatisticsError:
        return None
    return sd * math.sqrt(252) * 100.0


def average_turnover(closes: list[float], volumes: list[float],
                     window: int = TURNOVER_WINDOW) -> float | None:
    """최근 window 거래일의 평균 거래대금 (종가 × 거래량).

    정확한 거래대금은 체결가 기준이지만 일봉으로는 알 수 없습니다.
    종가 × 거래량은 **근사치**이고, 유동성 바닥을 가르는 데는 충분합니다
    (5억 원 근처에서 10% 틀려도 판정이 거의 안 바뀝니다).
    """
    pairs = [(c, v) for c, v in zip(closes[-window:], volumes[-window:])
             if c and c > 0 and v is not None and v >= 0]
    if len(pairs) < max(5, window // 4):
        return None
    return sum(c * v for c, v in pairs) / len(pairs)


def profile(ticker: str, name: str, closes: list[float],
            volumes: list[float] | None = None) -> VolProfile:
    """일봉 종가(+거래량) 목록 하나로 프로파일을 만듭니다."""
    clean = [c for c in closes if c and c > 0]
    if not clean:
        return VolProfile(ticker=ticker, name=name,
                          error="일봉을 받지 못했습니다.")
    if len(clean) < MIN_BARS:
        return VolProfile(
            ticker=ticker, name=name, bars=len(clean), price=clean[-1],
            error=f"일봉이 {len(clean)}개뿐입니다 (최소 {MIN_BARS}개). "
                  "신규 상장이거나 거래정지 구간이 있습니다.")
    year = clean[-LONG_WINDOW:]
    ret = None
    if year and year[0] > 0:
        ret = (clean[-1] / year[0] - 1.0) * 100.0

    def back(n: int) -> float | None:
        if len(clean) <= n or clean[-1 - n] <= 0:
            return None
        return (clean[-1] / clean[-1 - n] - 1.0) * 100.0

    def mean(n: int) -> float | None:
        return sum(clean[-n:]) / n if len(clean) >= n else None

    return VolProfile(
        ticker=ticker, name=name, bars=len(clean), price=clean[-1],
        high_52w=max(year), low_52w=min(year),
        vol_long=annualized_vol(clean, LONG_WINDOW),
        vol_short=annualized_vol(clean, SHORT_WINDOW),
        return_1y=ret,
        turnover=(average_turnover(closes, volumes) if volumes else None),
        ret_1w=back(5), ret_1m=back(21), ret_3m=back(63), ret_6m=back(126),
        low_20d=min(clean[-20:]), ma20=mean(20), ma60=mean(60),
        turnover_5d=(average_turnover(closes, volumes, 5) if volumes else None),
        turnover_60d=(average_turnover(closes, volumes, 60) if volumes else None),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 스크리너 1 — 변동성 수축 + 신고가
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Hit:
    """스크리너 하나를 통과한 종목."""

    ticker: str
    name: str
    reasons: list[str] = field(default_factory=list)
    metrics: list[tuple[str, str]] = field(default_factory=list)   # (라벨, 값)
    sort_key: float = 0.0


def contraction_hits(profiles: list[VolProfile], *,
                     contraction_max: float = CONTRACTION_MAX,
                     near_high_pct: float = NEAR_HIGH_PCT,
                     require_liquid: bool = True) -> list[Hit]:
    """변동성이 잦아든 채로 52주 고가 근처에 있는 종목.

    **교집합입니다.** 둘 중 하나만 만족하면 올리지 않습니다 — 변동성만
    낮으면 그냥 안 움직이는 종목이고, 신고가만 보면 급등 중인 종목이
    섞입니다.

    거래대금 바닥도 같이 겁니다. 변동성 수축은 '거래가 없어서 안 움직인
    것' 과 구분이 안 되는데, 코스닥에는 그런 종목이 흔합니다.
    """
    out: list[Hit] = []
    for p in profiles:
        c, hp = p.contraction, p.pct_of_high
        if c is None or hp is None:
            continue
        if c > contraction_max or hp < near_high_pct:
            continue
        if require_liquid and not p.liquid:
            continue
        reasons = [
            f"최근 3개월 변동성이 1년 평균의 {c * 100:.0f}% "
            f"(기준 {contraction_max * 100:.0f}% 이하)",
            f"52주 고가 대비 {hp:.1f}% (기준 {near_high_pct:.0f}% 이상)",
        ]
        # 거래대금은 **실제로 검사했을 때만** 이유에 적습니다. 끄고
        # 돌렸는데 '기준 5억 이상' 이라고 적으면 안 본 조건을 본 것처럼
        # 말하는 셈입니다.
        if require_liquid and p.turnover is not None:
            reasons.append(
                f"20일 평균 거래대금 {p.turnover_label}원 "
                f"(기준 {MIN_TURNOVER / 100_000_000:.0f}억 이상)")
        out.append(Hit(
            ticker=p.ticker, name=p.name,
            reasons=reasons,
            metrics=[
                ("변동성 수축비", f"{c:.2f}"),
                ("연율 변동성 (3개월)", f"{p.vol_short:.1f}%"),
                ("연율 변동성 (1년)", f"{p.vol_long:.1f}%"),
                ("52주 고가 대비", f"{hp:.1f}%"),
                ("1년 수익률",
                 "—" if p.return_1y is None else f"{p.return_1y:+.1f}%"),
                ("20일 평균 거래대금", p.turnover_label),
            ],
            sort_key=c,
        ))
    out.sort(key=lambda h: h.sort_key)      # 많이 잦아든 순
    return out


def near_high_hits(profiles: list[VolProfile], *,
                   near_high_pct: float = NEAR_HIGH_PCT,
                   require_liquid: bool = True) -> list[Hit]:
    """52주 신고가 근처 — 변동성 조건 없이. 비교용으로 따로 둡니다."""
    out: list[Hit] = []
    for p in profiles:
        hp = p.pct_of_high
        if hp is None or hp < near_high_pct:
            continue
        if require_liquid and not p.liquid:
            continue
        out.append(Hit(
            ticker=p.ticker, name=p.name,
            reasons=[f"52주 고가 대비 {hp:.1f}%"],
            metrics=[
                ("52주 고가 대비", f"{hp:.1f}%"),
                ("구간 내 위치",
                 "—" if p.band_position is None
                 else f"{p.band_position:.0f}%"),
                ("연율 변동성 (1년)",
                 "—" if p.vol_long is None else f"{p.vol_long:.1f}%"),
                ("1년 수익률",
                 "—" if p.return_1y is None else f"{p.return_1y:+.1f}%"),
                ("20일 평균 거래대금", p.turnover_label),
            ],
            sort_key=-hp,
        ))
    out.sort(key=lambda h: h.sort_key)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 스크리너 4·5·6 — 하락장에서도 비지 않는 기준 (2026-11-12 추가)
# ──────────────────────────────────────────────────────────────────────────────
#
# ①②는 '52주 고가의 90% 이상' 이라는 **절대** 기준입니다. 시장 전체가
# 10% 넘게 빠지면 (2026-11-12: KODEX 200 1개월 -9.1%, 50종목 전부 90% 아래)
# 둘 다 0종목이 되어 화면이 아무 말도 하지 않습니다. 기준을 느슨하게 하는
# 대신, **다른 질문**을 하는 스크리너를 따로 둡니다:
#   ④ 시장이 빠질 때 누가 덜 빠졌나            (상대)
#   ⑤ 많이 빠진 것 중 누가 돌아서고 있나        (낙폭 + 되돌림)
#   ⑥ 어디에 평소보다 거래가 몰리나             (관심)

#: ④ 후보 가운데 상위 몇 % 를 '강하다' 고 보나.
RS_TOP_PCT = 20.0
#: ⑤ 52주 고가 대비 이 % 이하 (= 25% 이상 하락) 이면서
REBOUND_MAX_OF_HIGH = 75.0
#:    최근 20일 저점에서 이 % 이상 올라와 있고 20일선 위.
REBOUND_OFF_LOW_PCT = 8.0
#: ⑥ 5일 평균 거래대금이 60일 평균의 몇 배 이상인가.
SURGE_RATIO = 2.0


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _pct_rank(value: float, values: list[float]) -> float:
    """value 가 values 안에서 몇 % 위치인가 (100 = 가장 높음)."""
    if not values:
        return 0.0
    below = sum(1 for v in values if v < value)
    same = sum(1 for v in values if v == value)
    return (below + 0.5 * same) / len(values) * 100.0


def _rs_universe(profiles: list[VolProfile], require_liquid: bool) -> list[VolProfile]:
    return [p for p in profiles
            if p.ok and p.ret_3m is not None and p.ret_6m is not None
            and (p.liquid or not require_liquid)]


def relative_strength_hits(profiles: list[VolProfile], *,
                           top_pct: float = RS_TOP_PCT,
                           require_liquid: bool = True) -> list[Hit]:
    """후보 안에서 3개월·6개월 수익률이 상위인 종목 — **시장 대비**.

    절대 수익률이 마이너스여도 올라옵니다 (전부 빠지는 장에서는 덜 빠진
    것이 강한 것입니다). 그래서 이유에 실제 수익률과 후보 중앙값을 같이
    적습니다 — '강하다' 가 '올랐다' 로 읽히지 않게.
    """
    uni = _rs_universe(profiles, require_liquid)
    if len(uni) < 5:
        return []
    r3 = [p.ret_3m for p in uni]
    r6 = [p.ret_6m for p in uni]
    med3, med6 = _median(r3), _median(r6)
    out: list[Hit] = []
    for p in uni:
        score = 0.5 * _pct_rank(p.ret_3m, r3) + 0.5 * _pct_rank(p.ret_6m, r6)
        if score < 100.0 - top_pct:
            continue
        out.append(Hit(
            ticker=p.ticker, name=p.name,
            reasons=[
                f"3개월 수익률 {p.ret_3m:+.1f}% — 후보 중앙값 {med3:+.1f}% 보다 "
                f"{p.ret_3m - med3:+.1f}%p",
                f"6개월 수익률 {p.ret_6m:+.1f}% — 후보 중앙값 {med6:+.1f}% 보다 "
                f"{p.ret_6m - med6:+.1f}%p",
                f"후보 {len(uni)}종목 중 상위 {100.0 - score:.0f}% "
                f"(기준 상위 {top_pct:.0f}%)",
            ],
            metrics=[
                ("상대강도 순위", f"상위 {100.0 - score:.0f}%"),
                ("3개월 수익률", f"{p.ret_3m:+.1f}%"),
                ("6개월 수익률", f"{p.ret_6m:+.1f}%"),
                ("1개월 수익률", "—" if p.ret_1m is None else f"{p.ret_1m:+.1f}%"),
                ("52주 고가 대비",
                 "—" if p.pct_of_high is None else f"{p.pct_of_high:.1f}%"),
                ("20일 평균 거래대금", p.turnover_label),
            ],
            sort_key=-score,
        ))
    out.sort(key=lambda h: h.sort_key)
    return out


def rebound_hits(profiles: list[VolProfile], *,
                 max_of_high: float = REBOUND_MAX_OF_HIGH,
                 off_low_pct: float = REBOUND_OFF_LOW_PCT,
                 require_liquid: bool = True) -> list[Hit]:
    """많이 빠진 뒤 최근 저점에서 올라와 20일선 위에 있는 종목."""
    out: list[Hit] = []
    for p in profiles:
        hp, off = p.pct_of_high, p.off_low_pct
        if not p.ok or hp is None or off is None or p.ma20 is None or p.price is None:
            continue
        if hp > max_of_high or off < off_low_pct or p.price <= p.ma20:
            continue
        if require_liquid and not p.liquid:
            continue
        out.append(Hit(
            ticker=p.ticker, name=p.name,
            reasons=[
                f"52주 고가 대비 {hp:.1f}% — {100.0 - hp:.0f}% 빠진 상태 "
                f"(기준 {100.0 - max_of_high:.0f}% 이상 하락)",
                f"최근 20일 저점에서 {off:+.1f}% (기준 +{off_low_pct:.0f}% 이상)",
                f"종가가 20일선 위 ({(p.price / p.ma20 - 1) * 100:+.1f}%)",
            ],
            metrics=[
                ("52주 고가 대비", f"{hp:.1f}%"),
                ("20일 저점 대비", f"{off:+.1f}%"),
                ("20일선 대비", f"{(p.price / p.ma20 - 1) * 100:+.1f}%"),
                ("1개월 수익률", "—" if p.ret_1m is None else f"{p.ret_1m:+.1f}%"),
                ("3개월 수익률", "—" if p.ret_3m is None else f"{p.ret_3m:+.1f}%"),
                ("20일 평균 거래대금", p.turnover_label),
            ],
            sort_key=-off,
        ))
    out.sort(key=lambda h: h.sort_key)
    return out


def turnover_surge_hits(profiles: list[VolProfile], *,
                        ratio: float = SURGE_RATIO) -> list[Hit]:
    """최근 5일 거래대금이 60일 평균의 ratio 배 이상인 종목."""
    out: list[Hit] = []
    for p in profiles:
        surge = p.turnover_surge
        if not p.ok or surge is None or p.turnover_5d is None:
            continue
        if surge < ratio or p.turnover_5d < MIN_TURNOVER:
            continue
        week = "—" if p.ret_1w is None else f"{p.ret_1w:+.1f}%"
        out.append(Hit(
            ticker=p.ticker, name=p.name,
            reasons=[
                f"5일 평균 거래대금이 60일 평균의 {surge:.1f}배 (기준 {ratio:.1f}배 이상)",
                f"그 5일 동안 주가 {week} — 거래가 몰린 방향을 같이 보십시오",
            ],
            metrics=[
                ("거래대금 배수", f"{surge:.1f}배"),
                ("5일 평균 거래대금", f"{p.turnover_5d / 1e8:,.1f}억"),
                ("60일 평균 거래대금",
                 "—" if not p.turnover_60d else f"{p.turnover_60d / 1e8:,.1f}억"),
                ("1주 수익률", week),
                ("1개월 수익률", "—" if p.ret_1m is None else f"{p.ret_1m:+.1f}%"),
                ("52주 고가 대비",
                 "—" if p.pct_of_high is None else f"{p.pct_of_high:.1f}%"),
            ],
            sort_key=-surge,
        ))
    out.sort(key=lambda h: h.sort_key)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 스크리너 2 — 전통 밸류 (PBR · PER · 배당)
# ──────────────────────────────────────────────────────────────────────────────
#
# 사용자가 '둘 다 따로' 를 골랐습니다. 공시 기반 가격 조건(value.py 의
# FCF 수익률·순부채·기대 괴리)과 **섞지 않습니다.** 성격이 다르기
# 때문입니다: 아래 셋은 야후 집계값이고 업종 편향이 큽니다. PBR 은 자산이
# 많은 업종(은행·중공업)에 구조적으로 유리하고, 그 업종은 버핏식 품질
# 기준에서는 대체로 떨어집니다. 두 점수를 더하면 그 상충이 가려집니다.

@dataclass
class ValueRow:
    ticker: str
    name: str
    pbr: float | None = None
    per: float | None = None
    div_yield: float | None = None     # %
    error: str = ""

    def checks(self) -> list[tuple[str, str, str]]:
        """(라벨, 판정, 설명). 판정은 pass / fail / unknown."""
        out = []
        if self.pbr is None:
            out.append(("PBR", "unknown", "값을 받지 못했습니다"))
        else:
            out.append(("PBR", "pass" if self.pbr <= PBR_MAX else "fail",
                        f"{self.pbr:.2f} (기준 {PBR_MAX:.1f} 이하)"))
        if self.per is None:
            out.append(("PER", "unknown", "값을 받지 못했습니다 "
                                          "(적자면 PER 이 없습니다)"))
        else:
            out.append(("PER", "pass" if self.per <= PER_MAX else "fail",
                        f"{self.per:.1f} (기준 {PER_MAX:.0f} 이하)"))
        if self.div_yield is None:
            out.append(("배당수익률", "unknown", "값을 받지 못했습니다"))
        else:
            out.append(("배당수익률",
                        "pass" if self.div_yield >= DIV_MIN else "fail",
                        f"{self.div_yield:.2f}% (기준 {DIV_MIN:.1f}% 이상)"))
        return out

    @property
    def passed(self) -> int:
        return sum(1 for _l, v, _d in self.checks() if v == "pass")

    @property
    def total(self) -> int:
        return len(self.checks())


def value_hits(rows: list[ValueRow], *, min_pass: int = 2) -> list[Hit]:
    """셋 중 min_pass 개 이상 통과."""
    out: list[Hit] = []
    for r in rows:
        if r.error or r.passed < min_pass:
            continue
        out.append(Hit(
            ticker=r.ticker, name=r.name,
            reasons=[f"{lab} {det}"
                     for lab, verdict, det in r.checks() if verdict == "pass"],
            metrics=[(lab, det) for lab, _v, det in r.checks()],
            sort_key=-float(r.passed),
        ))
    out.sort(key=lambda h: h.sort_key)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 걸러진 단계 — '0건' 일 때 어디서 막혔는지
# ──────────────────────────────────────────────────────────────────────────────
#
# 2026-11-11 "한국 종목발굴이 0". 0 건은 두 가지로 읽힙니다 — 데이터를
# 못 받았거나, 받았는데 기준이 엄격했거나. 화면이 둘을 구분하지 않으면
# 사용자는 고장인지 시장이 조용한 건지 알 수 없습니다. 단계마다 몇
# 종목이 남는지 숫자로 보여 줍니다.

@dataclass
class FunnelStep:
    label: str
    count: int
    note: str = ""        # 이 단계에서 많이 빠졌다면 왜인지


def vol_funnel(n_candidates: int, profiles: list[VolProfile],
               contraction_max: float = CONTRACTION_MAX,
               near_high_pct: float = NEAR_HIGH_PCT) -> list[FunnelStep]:
    got = [p for p in profiles if p.bars > 0]
    usable = [p for p in profiles if p.ok]
    liquid = [p for p in usable if p.liquid]
    no_vol = [p for p in usable if p.turnover is None]
    high = [p for p in liquid if (p.pct_of_high or 0) >= near_high_pct]
    both = [p for p in high
            if p.contraction is not None and p.contraction <= contraction_max]
    steps = [
        FunnelStep("후보", n_candidates),
        FunnelStep("일봉 받음", len(got),
                   "" if len(got) >= n_candidates * 0.8
                   else "데이터 출처 문제 — 아래 오류를 보십시오"),
        FunnelStep(f"{MIN_BARS}일 이상", len(usable)),
        FunnelStep(f"거래대금 {MIN_TURNOVER / 1e8:.0f}억↑", len(liquid),
                   f"거래량을 못 받은 종목 {len(no_vol)}개"
                   if no_vol else ""),
        FunnelStep(f"52주 고가 {near_high_pct:.0f}%↑", len(high)),
        FunnelStep(f"수축비 {contraction_max:.2f}↓", len(both)),
    ]
    return steps


#: 일봉으로 계산하는 스크리너들 (나머지는 지표 기반).
VOL_SCREENS = ("contraction", "near_high", "rs", "rebound", "surge")


def funnel(key: str, n_candidates: int, profiles: list[VolProfile]) -> list[FunnelStep]:
    """스크리너마다 '어느 단계에서 몇 종목이 남았나'. 0건의 원인을 가립니다."""
    if key == "contraction":
        return vol_funnel(n_candidates, profiles)
    if key == "near_high":
        return vol_funnel(n_candidates, profiles)[:-1]
    head = vol_funnel(n_candidates, profiles)[:4]          # 후보 … 거래대금
    usable = [p for p in profiles if p.ok]
    liquid = [p for p in usable if p.liquid]
    if key == "rs":
        uni = _rs_universe(profiles, True)
        return head + [
            FunnelStep("6개월 수익률 있음", len(uni),
                       "" if len(uni) >= 5 else "비교할 종목이 5개 미만이면 순위를 내지 않습니다"),
            FunnelStep(f"상위 {RS_TOP_PCT:.0f}%", len(relative_strength_hits(profiles))),
        ]
    if key == "rebound":
        deep = [p for p in liquid if (p.pct_of_high or 100.0) <= REBOUND_MAX_OF_HIGH]
        off = [p for p in deep if (p.off_low_pct or 0.0) >= REBOUND_OFF_LOW_PCT]
        return head + [
            FunnelStep(f"52주 고가 {REBOUND_MAX_OF_HIGH:.0f}%↓", len(deep)),
            FunnelStep(f"20일 저점 +{REBOUND_OFF_LOW_PCT:.0f}%↑", len(off)),
            FunnelStep("20일선 위", len(rebound_hits(profiles))),
        ]
    if key == "surge":
        have = [p for p in usable if p.turnover_surge is not None]
        return head[:3] + [
            FunnelStep("거래대금 60일치 있음", len(have)),
            FunnelStep(f"5일 ÷ 60일 ≥ {SURGE_RATIO:.1f}배", len(turnover_surge_hits(profiles))),
        ]
    return head


def value_funnel(rows: list[ValueRow], min_pass: int = 2) -> list[FunnelStep]:
    ok = [r for r in rows if not r.error]
    any_val = [r for r in ok if r.total and any(
        v != "unknown" for _l, v, _d in r.checks())]
    one = [r for r in ok if r.passed >= 1]
    hit = [r for r in ok if r.passed >= min_pass]
    return [
        FunnelStep("후보", len(rows)),
        FunnelStep("지표 받음", len(any_val),
                   "" if len(any_val) >= len(rows) * 0.8 or not rows
                   else "데이터 출처 문제 — 아래 오류를 보십시오"),
        FunnelStep("1개 이상 통과", len(one)),
        FunnelStep(f"{min_pass}개 이상 통과", len(hit)),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 야후 심볼
# ──────────────────────────────────────────────────────────────────────────────

def yahoo_symbols(code: str) -> tuple[str, ...]:
    """국내 6자리 코드 → 야후 심볼 후보.

    코스피는 `.KS`, 코스닥은 `.KQ` 인데 코드만 봐서는 구분되지 않습니다.
    (001 로 시작하면 코스피 같은 규칙은 **없습니다** — 예외가 많습니다.)
    그래서 순서대로 시도합니다. 이미 접미사가 붙어 있으면 그대로 씁니다.
    """
    code = (code or "").strip()
    if not code:
        return ()
    if "." in code:
        return (code,)
    if not code.isdigit():
        return (code,)
    # 코스닥으로 알고 있는 종목은 .KQ 를 먼저 시도합니다. 순서만 바뀌고
    # 둘 다 시도하는 건 같습니다 — 목록이 틀렸어도 결과는 나옵니다.
    try:
        import config  # noqa: PLC0415 - 순환 참조를 피해 지연 임포트
        if code in config.kosdaq_codes():
            return (f"{code}.KQ", f"{code}.KS")
    except Exception:  # noqa: BLE001
        pass
    return (f"{code}.KS", f"{code}.KQ")


def build_profiles(candidates, closes_by_symbol: dict[str, list[float]],
                   volumes_by_symbol: dict[str, list[float]] | None = None,
                   ) -> tuple[list[VolProfile], dict[str, str]]:
    """(코드, 이름) 목록 + 받아온 일봉 → 프로파일 목록.

    심볼 후보(.KS / .KQ) 중 **먼저 값이 있는 쪽**을 씁니다. 둘 다 비면
    오류로 남깁니다 — 조용히 빼면 왜 목록에 없는지 알 수 없습니다.
    """
    profiles: list[VolProfile] = []
    errors: dict[str, str] = {}
    volumes_by_symbol = volumes_by_symbol or {}
    for code, name in candidates:
        closes: list[float] = []
        vols: list[float] = []
        for sym in yahoo_symbols(code):
            if closes_by_symbol.get(sym):
                closes = closes_by_symbol[sym]
                vols = volumes_by_symbol.get(sym) or []
                break
        if not closes:
            errors[code] = "일봉을 받지 못했습니다 (.KS · .KQ 둘 다 비었습니다)."
            continue
        p = profile(code, name, closes, vols)
        profiles.append(p)
        if p.error:
            errors[code] = p.error
    return profiles, errors


def all_symbols(candidates) -> list[str]:
    """받아와야 할 야후 심볼 전부 (코드당 최대 2개)."""
    out: list[str] = []
    for code, _name in candidates:
        out.extend(yahoo_symbols(code))
    return list(dict.fromkeys(out))


# ──────────────────────────────────────────────────────────────────────────
# 화면에 쓰는 스크리너 묶음
# ──────────────────────────────────────────────────────────────────────────
#
# app.py 가 아니라 여기 둡니다 — 프리뷰 생성기도 같은 정의를
# 써야 하는데, app.py 를 임포트하면 streamlit 이 딸려옵니다.

#: 국내 스크리너 묶음. (키, 제목, 기준 설명, 주의)
#: 기준표 아래에 붙는 말뜻 — 기준에 나오는 낱말이 정확히 무엇인지.
KR_TERMS = (
    ("변동성", f"일간 수익률의 표준편차. 3개월 = 최근 {SHORT_WINDOW}거래일, "
              f"1년 = 최근 {LONG_WINDOW}거래일"),
    ("52주 고가 대비", "오늘 종가 ÷ 최근 1년 최고가 (100% 면 신고가)"),
    ("거래대금", f"종가 × 거래량의 {TURNOVER_WINDOW}거래일 평균 "
                f"(바닥 {MIN_TURNOVER / 100_000_000:.0f}억 원 — 거래가 없어 안 움직인 종목을 뺍니다)"),
    ("대상", f"코스피 + 코스닥 후보 가운데 일봉이 {MIN_BARS}개 이상인 종목 "
            "(신규 상장 · 거래정지는 계산하지 않습니다)"),
    ("PBR · PER · 배당", "야후 파이낸스 집계값 (공시에서 직접 계산한 값이 아닙니다)"),
)

KR_SCREENS = (
    ("contraction", "① 변동성 수축 + 신고가",
     f"최근 3개월 변동성 ÷ 1년 변동성 ≤ {CONTRACTION_MAX:.2f} "
     f"<b>그리고</b> 52주 고가 대비 ≥ {NEAR_HIGH_PCT:.0f}% "
     f"<b>그리고</b> 20일 평균 거래대금 ≥ "
     f"{MIN_TURNOVER / 100_000_000:.0f}억",
     "<b>방향을 말해주지 않습니다.</b> 변동성이 잦아든 뒤에는 위로도 "
     "아래로도 터집니다. 이 목록은 '오를 종목' 이 아니라 '공시를 읽어볼 "
     "종목' 입니다."),
    ("near_high", "② 52주 신고가 근처",
     f"52주 고가 대비 ≥ {NEAR_HIGH_PCT:.0f}% · 거래대금 ≥ "
     f"{MIN_TURNOVER / 100_000_000:.0f}억 (변동성 조건 없음)",
     "①과 비교하라고 둔 목록입니다. 여기에만 있고 ①에 없으면 "
     "<b>아직 급하게 움직이는 중</b>이라는 뜻입니다."),
    ("value_trad", "③ 전통 밸류 (PBR · PER · 배당)",
     f"PBR ≤ {PBR_MAX:.1f} · PER ≤ {PER_MAX:.0f} · "
     f"배당수익률 ≥ {DIV_MIN:.1f}% 중 2개 이상",
     "야후 집계값입니다. <b>PBR 은 자산이 많은 업종(은행·중공업)에 "
     "구조적으로 유리</b>하고, 그 업종은 대체로 품질 기준에서 떨어집니다. "
     "공시 기반 가격 조건(밸류에이션 탭)과 <b>섞지 않고 따로</b> 둡니다."),
    ("rs", "④ 시장 대비 강한 종목",
     f"3개월·6개월 수익률 순위가 후보 가운데 상위 {RS_TOP_PCT:.0f}% · 거래대금 ≥ "
     f"{MIN_TURNOVER / 100_000_000:.0f}억",
     "<b>'강하다' 는 '올랐다' 가 아닙니다.</b> 전부 빠지는 장에서는 덜 빠진 "
     "종목이 올라옵니다 — 수익률 숫자를 그대로 보십시오. ①②가 0종목인 "
     "하락장에서 '그래도 버티는 곳' 을 보려고 둔 목록입니다."),
    ("rebound", "⑤ 낙폭 과대 + 되돌림",
     f"52주 고가 대비 ≤ {REBOUND_MAX_OF_HIGH:.0f}% <b>그리고</b> 최근 20일 저점에서 "
     f"+{REBOUND_OFF_LOW_PCT:.0f}% 이상 <b>그리고</b> 20일선 위",
     "<b>추세가 바뀌었다는 뜻이 아닙니다.</b> 하락 중의 반등(데드캣)이 "
     "가장 많이 잡히는 조건입니다. 왜 빠졌는지 공시부터 읽으십시오."),
    ("surge", "⑥ 거래대금 급증",
     f"5일 평균 거래대금 ÷ 60일 평균 ≥ {SURGE_RATIO:.1f}배 · 5일 평균 ≥ "
     f"{MIN_TURNOVER / 100_000_000:.0f}억",
     "<b>방향을 말해주지 않습니다.</b> 급락하면서 거래가 터진 종목도 "
     "똑같이 올라옵니다 — 1주 수익률을 같이 적었습니다. 무슨 일이 있었는지 "
     "(공시·실적·수급) 확인할 종목의 목록입니다."),
)
