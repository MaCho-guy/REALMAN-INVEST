"""
섹터 온도 — 업종 ETF 로 본 한국 시장의 업종별 흐름.

**왜 ETF 인가.** 업종 지수(KRX 업종지수)를 직접 받을 공개 경로가 없습니다.
모닝 브리프도 같은 이유로 KODEX 업종 ETF 를 '업종지수 대용' 으로 씁니다.
ETF 는 운용보수와 추적오차가 있어 실제 업종지수와 조금 다를 수 있습니다 —
화면에 그렇게 적습니다.

**무엇을 보는가.** 업종마다 네 기간의 수익률(1일·1주·1개월·3개월)을
나란히 놓고 색으로 칠합니다. 그게 '온도' 입니다. 한 업종만 보면 시장
전체가 오른 건지 그 업종만 오른 건지 구분이 안 되므로, **KODEX 200 대비
1개월 초과수익**을 따로 적고 그 순서로 줄을 세웁니다.

  절대 수익률   — 그 업종이 얼마나 움직였나
  상대 수익률   — 시장보다 더 움직였나 (업종 순환을 볼 때는 이쪽)

**종목코드 검증.** 6자리 코드는 제가 적은 것이라 틀릴 수 있습니다. 틀리면
다른 ETF 의 수익률이 '반도체' 이름표를 달고 나옵니다 — 화면에서는 이상이
안 보입니다. 그래서 야후가 돌려준 **실제 이름**을 받아 기대한 말이 들어
있는지 기계가 대조하고, 안 맞으면 그 줄에 ✗ 를 붙입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 기간 (거래일). 1주 = 5일, 1개월 ≈ 21일, 3개월 ≈ 63일.
PERIODS: tuple[tuple[str, str, int], ...] = (
    ("d1", "1일", 1),
    ("w1", "1주", 5),
    ("m1", "1개월", 21),
    ("m3", "3개월", 63),
)

#: 색을 꽉 채우는 수익률 (%). 이보다 크면 같은 진하기입니다.
#: 기간이 길수록 움직임이 크므로 눈금을 넓힙니다 — 하나로 두면 1일은
#: 늘 연하고 3개월은 늘 진해서 색이 정보를 못 줍니다.
COLOR_SCALE: dict[str, float] = {"d1": 3.0, "w1": 6.0, "m1": 12.0, "m3": 25.0}

#: 스파크라인에 쓸 일봉 수 (3개월)
SPARK_BARS = 63


@dataclass
class SectorRow:
    """업종 하나."""

    code: str                      # 6자리
    label: str                     # 업종 이름 (config 에 적은 것)
    keywords: tuple[str, ...] = ()  # 야후 이름에 있어야 할 말
    benchmark: bool = False        # KODEX 200 같은 기준선
    yahoo_name: str = ""
    closes: list[float] = field(default_factory=list)
    returns: dict[str, float | None] = field(default_factory=dict)
    band_52w: float | None = None  # 52주 구간 내 위치 (0~100)
    rel_1m: float | None = None    # 기준선 대비 1개월 초과수익 (%p)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and bool(self.closes)

    @property
    def name_ok(self) -> bool | None:
        """야후 이름이 기대와 맞는가. 이름을 못 받았으면 None."""
        if not self.yahoo_name:
            return None
        hay = self.yahoo_name.lower().replace(" ", "")
        return any(k.lower().replace(" ", "") in hay for k in self.keywords)

    @property
    def spark(self) -> list[float]:
        return self.closes[-SPARK_BARS:]


def period_return(closes: list[float], bars: int) -> float | None:
    """bars 거래일 전 대비 수익률 (%)."""
    clean = [c for c in closes if c and c > 0]
    if len(clean) <= bars:
        return None
    base = clean[-(bars + 1)]
    return (clean[-1] / base - 1.0) * 100.0 if base else None


def band_position(closes: list[float], window: int = 252) -> float | None:
    """52주 저가~고가 구간에서 지금 위치 (0~100)."""
    year = [c for c in closes[-window:] if c and c > 0]
    if len(year) < 20:
        return None
    lo, hi = min(year), max(year)
    if hi <= lo:
        return None
    return (year[-1] - lo) / (hi - lo) * 100.0


def build(specs, closes_by_code: dict[str, list[float]],
          names_by_code: dict[str, str] | None = None,
          errors: dict[str, str] | None = None) -> list[SectorRow]:
    """설정 + 받아온 일봉 → 업종 줄 목록 (기준선 대비 1개월 순)."""
    names_by_code = names_by_code or {}
    errors = errors or {}
    rows: list[SectorRow] = []
    for spec in specs:
        code, label, keywords = spec[0], spec[1], tuple(spec[2])
        bench = len(spec) > 3 and bool(spec[3])
        closes = closes_by_code.get(code) or []
        row = SectorRow(code=code, label=label, keywords=keywords,
                        benchmark=bench,
                        yahoo_name=names_by_code.get(code, ""),
                        closes=list(closes))
        if not closes:
            row.error = errors.get(code) or "일봉을 받지 못했습니다."
        else:
            row.returns = {k: period_return(closes, n)
                           for k, _lab, n in PERIODS}
            row.band_52w = band_position(closes)
        rows.append(row)

    bench_rows = [r for r in rows if r.benchmark and r.ok]
    bench_1m = bench_rows[0].returns.get("m1") if bench_rows else None
    for r in rows:
        m1 = r.returns.get("m1")
        if r.ok and not r.benchmark and m1 is not None and bench_1m is not None:
            r.rel_1m = m1 - bench_1m

    def key(r: SectorRow):
        # 기준선은 맨 위, 그다음 상대 1개월 순, 실패는 맨 아래
        if r.benchmark:
            return (0, 0.0)
        if not r.ok:
            return (3, 0.0)
        if r.rel_1m is None:
            return (2, 0.0)
        return (1, -r.rel_1m)

    rows.sort(key=key)
    return rows


def hot_and_cold(rows: list[SectorRow], n: int = 2
                 ) -> tuple[list[SectorRow], list[SectorRow]]:
    """기준선 대비 1개월로 가장 뜨거운·차가운 업종 n 개씩."""
    ranked = [r for r in rows if r.ok and not r.benchmark
              and r.rel_1m is not None]
    ranked.sort(key=lambda r: r.rel_1m, reverse=True)
    hot = [r for r in ranked[:n] if r.rel_1m > 0]
    cold = [r for r in ranked[-n:][::-1] if r.rel_1m < 0]
    return hot, cold


def summary_line(rows: list[SectorRow]) -> str:
    """요약 탭에 쓰는 한 줄."""
    hot, cold = hot_and_cold(rows)
    if not hot and not cold:
        usable = [r for r in rows if r.ok and not r.benchmark]
        if not usable:
            return "업종 ETF 를 받지 못했습니다."
        return "업종 간 차이가 크지 않습니다 (KODEX 200 대비 ±0)."
    bits = []
    if hot:
        bits.append("강세 " + " · ".join(
            f"{r.label} {r.rel_1m:+.1f}%p" for r in hot))
    if cold:
        bits.append("약세 " + " · ".join(
            f"{r.label} {r.rel_1m:+.1f}%p" for r in cold))
    return " / ".join(bits) + " (1개월, KODEX 200 대비)"


def mismatched(rows: list[SectorRow]) -> list[SectorRow]:
    """야후 이름이 기대와 다른 줄 — 종목코드가 틀렸을 가능성."""
    return [r for r in rows if r.name_ok is False]
