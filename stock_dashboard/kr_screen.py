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
    error: str = ""

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
    return VolProfile(
        ticker=ticker, name=name, bars=len(clean), price=clean[-1],
        high_52w=max(year), low_52w=min(year),
        vol_long=annualized_vol(clean, LONG_WINDOW),
        vol_short=annualized_vol(clean, SHORT_WINDOW),
        return_1y=ret,
        turnover=(average_turnover(closes, volumes) if volumes else None),
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
)
