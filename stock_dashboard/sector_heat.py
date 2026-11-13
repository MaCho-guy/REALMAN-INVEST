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
    as_of: str = ""               # 마지막 봉 날짜 'YYYY-MM-DD' ('' = 모름)
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
          errors: dict[str, str] | None = None,
          dates_by_code: dict[str, str] | None = None) -> list[SectorRow]:
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
                        closes=list(closes),
                        as_of=str((dates_by_code or {}).get(code) or ""))
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


def as_of(rows: list[SectorRow]) -> str:
    """줄들의 마지막 봉 날짜 중 가장 흔한 것 ('' = 모름)."""
    seen: dict[str, int] = {}
    for r in rows:
        if r.as_of:
            seen[r.as_of] = seen.get(r.as_of, 0) + 1
    return max(seen, key=seen.get) if seen else ""


# ──────────────────────────────────────────────────────────────────────────────
# 흐름 — 업종이 지금 어느 단계에 있고, 1주 전과 비교해 어디로 옮겨갔나
# ──────────────────────────────────────────────────────────────────────────────
#
# 2026-11-13 사용자: "섹터 온도의 변화 흐름이 무엇을 이야기하는지" 가 안 보임.
# 위의 판정은 전부 '시장 대비 1개월' 한 숫자라서 방향이 바뀌는 순간을 못
# 잡았습니다 — 같은 날 반도체는 1개월 −7.5%p(약세 쪽)였지만 1주는 +11.2%p 로
# 시장을 가장 크게 앞섰습니다.
#
# **상대 순환 그래프(RRG)를 단순화한 4칸.** 두 축으로 업종을 나눕니다.
#   가로 = 중기 위치 — 3개월 시장 대비 (+ 면 강, − 면 약)
#   세로 = 최근 방향 — 1주 시장 대비 (+ 면 강해짐, − 면 약해짐)
#   주도 = 강 · 강해짐 / 둔화 = 강 · 약해짐 / 침체 = 약 · 약해짐 / 회복 = 약 · 강해짐
# 원래 RRG 는 상대강도를 정규화·평활해서 쓰지만, 여기서는 화면의 기간별 격자
# (1주 · 3개월 칸에서 KODEX 200 칸을 뺀 값)로 **손으로 검산할 수 있게** 단순
# 수익률 차를 씁니다. 1주는 사용자가 고른 기간입니다(2026-11-13) — 전환을 빨리
# 잡는 대신 칸이 자주 바뀝니다.

#: 중기 위치 · 최근 방향에 쓰는 기간 (PERIODS 의 키, 거래일)
FLOW_LEVEL: tuple[str, int] = ("m3", 63)
FLOW_DIR: tuple[str, int] = ("w1", 5)
#: 최근 방향이 이 안(%p)이면 '방향 없음' — 0.3%p 차이로 칸이 갈리지 않게
FLOW_FLAT = 1.0
#: 몇 거래일 전 판정과 비교하나 (1주)
FLOW_LAG = 5
#: 시장 숫자를 크게 흔드는 업종 — KODEX 200 은 시가총액 비중대로 담아서
#: 이 업종이 크게 움직이면 다른 업종의 '시장 대비' 가 반대로 기웁니다.
FLOW_HEAVY_CODE = "091160"      # 반도체
#: 그 업종의 1주 시장 대비가 이만큼(%p) 넘을 때만 시소를 의심합니다
FLOW_HEAVY_MIN = 3.0

#: 단계 — (키, 이름, 뜻). 화면에 이 순서로 놓습니다.
PHASES: tuple[tuple[str, str, str], ...] = (
    ("lead", "주도", "3개월 시장보다 강하고, 이번 주도 강함"),
    ("recover", "회복", "3개월은 약했지만, 이번 주 시장을 앞섬"),
    ("fade", "둔화", "3개월은 강했지만, 이번 주 뒤처짐"),
    ("lag", "침체", "3개월도 약하고, 이번 주도 뒤처짐"),
)
PHASE_NAME: dict[str, str] = {k: n for k, n, _d in PHASES}
_UP_PHASES = ("lead", "recover")      # 이번 주 시장을 앞선 쪽
_DOWN_PHASES = ("fade", "lag")        # 이번 주 시장에 뒤처진 쪽


def phase_of(level: float | None, direction: float | None) -> str | None:
    """두 값 → 단계 키. 방향이 ±FLOW_FLAT 안이면 'flat', 값이 없으면 None."""
    if level is None or direction is None:
        return None
    if abs(direction) < FLOW_FLAT:
        return "flat"
    if level >= 0:
        return "lead" if direction > 0 else "fade"
    return "recover" if direction > 0 else "lag"


def rel_return(closes: list[float], bench: list[float], bars: int,
               lag: int = 0) -> float | None:
    """lag 거래일 전 시점에서 본 bars 거래일 시장 대비 수익률 (%p)."""
    if lag:
        closes, bench = closes[:-lag], bench[:-lag]
    a = period_return(closes, bars)
    b = period_return(bench, bars)
    if a is None or b is None:
        return None
    return a - b


@dataclass
class FlowRow:
    """업종 하나의 흐름."""

    code: str
    label: str
    level: float | None = None        # 3개월 시장 대비 (%p)
    direction: float | None = None    # 1주 시장 대비 (%p)
    phase: str | None = None          # lead · recover · fade · lag · flat
    prev_phase: str | None = None     # 1주 전 판정
    why_none: str = ""               # 판정 못 한 이유

    @property
    def moved(self) -> bool:
        """1주 전과 칸이 바뀌었나 (방향 없음 ↔ 칸 은 셈하지 않음)."""
        known = ("lead", "recover", "fade", "lag")
        return (self.phase in known and self.prev_phase in known
                and self.phase != self.prev_phase)

    @property
    def turned_up(self) -> bool:
        """뒤처지던 쪽(둔화·침체) → 앞서는 쪽(주도·회복)."""
        return self.prev_phase in _DOWN_PHASES and self.phase in _UP_PHASES

    @property
    def turned_down(self) -> bool:
        """앞서던 쪽(주도·회복) → 뒤처지는 쪽(둔화·침체)."""
        return self.prev_phase in _UP_PHASES and self.phase in _DOWN_PHASES


def flow(rows: list[SectorRow]) -> list[FlowRow]:
    """업종 줄 → 흐름 줄 (기준선 제외). 기준선이 없으면 빈 목록."""
    bench = next((r for r in rows if r.benchmark and r.ok), None)
    if bench is None:
        return []
    _lk, lbars = FLOW_LEVEL
    _dk, dbars = FLOW_DIR
    out: list[FlowRow] = []
    for r in rows:
        if r.benchmark:
            continue
        f = FlowRow(code=r.code, label=r.label)
        if not r.ok:
            f.why_none = "일봉 없음"
        elif r.as_of and bench.as_of and r.as_of != bench.as_of:
            # 네이버 실패 → 야후로 메운 줄은 마지막 봉 날짜가 다를 수 있습니다.
            # 날짜가 어긋난 채로 빼면 하루치 등락이 '시장 대비' 로 둔갑합니다.
            f.why_none = f"마지막 봉 날짜가 기준선과 다름 ({r.as_of} vs {bench.as_of})"
        else:
            f.level = rel_return(r.closes, bench.closes, lbars)
            f.direction = rel_return(r.closes, bench.closes, dbars)
            f.phase = phase_of(f.level, f.direction)
            f.prev_phase = phase_of(
                rel_return(r.closes, bench.closes, lbars, FLOW_LAG),
                rel_return(r.closes, bench.closes, dbars, FLOW_LAG))
            if f.phase is None:
                f.why_none = "일봉이 모자람"
        out.append(f)
    return out


@dataclass
class FlowRead:
    """흐름 판독 — 문장을 만들 재료."""

    bench_label: str
    bench_dir: float                  # 기준선 1주 수익률 (%)
    n: int                            # 판정한 업종 수
    beat: int                         # 이번 주 시장보다 더 오른 업종 수
    drivers: list[FlowRow]            # 시장을 가장 크게 앞선 업종 (최대 2)
    turned_up: list[FlowRow]
    turned_down: list[FlowRow]
    stayed_lead: list[FlowRow]        # 1주 전에도 주도
    moved: int                        # 1주 전과 칸이 바뀐 업종 수
    heavy: FlowRow | None             # 시소를 일으켰을 수 있는 업종
    unknown: list[FlowRow]

    @property
    def breadth(self) -> str:
        """'narrow' · 'broad' · 'mixed' — 시장보다 더 오른 업종의 비율."""
        if self.n == 0:
            return "mixed"
        share = self.beat / self.n
        if share <= 1 / 3:
            return "narrow"
        if share >= 2 / 3:
            return "broad"
        return "mixed"


def flow_read(rows: list[SectorRow],
              flows: list[FlowRow] | None = None) -> FlowRead | None:
    """판독 재료. 기준선의 1주 수익률을 모르거나 판정한 업종이 없으면 None."""
    bench = next((r for r in rows if r.benchmark and r.ok), None)
    if bench is None:
        return None
    bdir = bench.returns.get(FLOW_DIR[0])
    if bdir is None:
        return None
    flows = flow(rows) if flows is None else flows
    known = [f for f in flows if f.phase is not None]
    if not known:
        return None
    ahead = sorted((f for f in known if f.direction >= FLOW_FLAT),
                   key=lambda f: -f.direction)
    heavy = next((f for f in known if f.code == FLOW_HEAVY_CODE), None)
    if heavy is not None:
        others = [f for f in known if f is not heavy and abs(f.direction) >= FLOW_FLAT]
        opposite = [f for f in others if (f.direction > 0) != (heavy.direction > 0)]
        if not (abs(heavy.direction) >= FLOW_HEAVY_MIN and others
                and len(opposite) >= len(others) * 2 / 3):
            heavy = None
    return FlowRead(
        bench_label=bench.label, bench_dir=bdir, n=len(known),
        beat=sum(1 for f in known if f.direction > 0),
        drivers=ahead[:2],
        turned_up=sorted((f for f in known if f.turned_up),
                         key=lambda f: -f.direction),
        turned_down=sorted((f for f in known if f.turned_down),
                           key=lambda f: f.direction),
        stayed_lead=[f for f in known if f.phase == "lead" and f.prev_phase == "lead"],
        moved=sum(1 for f in known if f.moved),
        heavy=heavy,
        unknown=[f for f in flows if f.phase is None],
    )


def _josa(word: str, with_final: str, without_final: str) -> str:
    """받침 있으면 '이', 없으면 '가' 처럼. 한글이 아니면 둘 다 적습니다."""
    if not word:
        return word
    ch = word[-1]
    if "가" <= ch <= "힣":
        return word + (with_final if (ord(ch) - 0xAC00) % 28 else without_final)
    return f"{word}{with_final}({without_final})"


def _names(items: list[FlowRow], limit: int = 3) -> str:
    names = [f.label for f in items[:limit]]
    more = f" 등 {len(items)}개" if len(items) > limit else ""
    return "·".join(names) + more


def flow_sentences(read: FlowRead | None) -> list[str]:
    """판독 문장 (최대 3줄, 글자만 — HTML 은 화면 쪽에서 감쌉니다).

    전부 화면의 숫자에서 바로 나오는 사실만 적습니다. 매수·매도나 앞으로의
    방향은 말하지 않습니다.
    """
    if read is None:
        return []
    out: list[str] = []
    word = "올랐고" if read.bench_dir > 0 else ("내렸고" if read.bench_dir < 0 else "제자리였고")
    tone = {"narrow": "몇 업종만 앞선 좁은 움직임",
            "broad": "대부분 업종이 시장을 앞선 고른 움직임",
            "mixed": "업종별로 갈린 움직임"}[read.breadth]
    line = (f"이번 주 {read.bench_label} {read.bench_dir:+.1f}% {word}, 시장보다 더 "
            f"오른 업종은 {read.beat}/{read.n}개 — {tone}.")
    if read.drivers:
        line += " 앞선 쪽: " + " · ".join(
            f"{f.label} {f.direction:+.1f}%p" for f in read.drivers) + "."
    out.append(line)

    if read.turned_up or read.turned_down:
        bits = []
        if read.turned_up:
            bits.append("돌아선 쪽 " + ", ".join(
                f"{f.label}({PHASE_NAME[f.prev_phase]}→{PHASE_NAME[f.phase]})"
                for f in read.turned_up[:3])
                + (f" 외 {len(read.turned_up) - 3}개" if len(read.turned_up) > 3 else ""))
        if read.turned_down:
            bits.append(f"꺾인 쪽 {_names(read.turned_down)} "
                        "(지난주엔 시장을 앞섰으나 이번 주 뒤처짐)")
        out.append("1주 전과 비교: " + " / ".join(bits) + ".")
    elif read.stayed_lead:
        out.append(f"2주 연속 주도: {_names(read.stayed_lead)}.")

    if read.heavy is not None:
        h = read.heavy
        side, mirror = (("앞서", "뒤처져") if h.direction > 0 else ("뒤처져", "앞서"))
        out.append(f"{_josa(h.label, '이', '가')} 시장 대비 {h.direction:+.1f}%p 로 크게 "
                   f"{side} 나머지 업종 대부분이 '시장 대비' 로는 {mirror} 보입니다. "
                   f"{read.bench_label} 안의 {h.label} 비중이 커서 생기는 착시일 수 "
                   "있으니, 업종 자체의 등락은 아래 기간별 수익률로 확인하십시오.")
    return out[:3]
