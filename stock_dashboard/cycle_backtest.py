"""
체크리스트 백테스트 — 재고 규칙이 과거 메모리 피크에서 언제 켜졌나 (2026-11-16).

================================================================================
무엇을 검증하나
================================================================================
지표체계 §5 의 문턱(3개 이상 점등 · 레이어 2 필수)은 설계한 값이지 데이터로
맞춘 값이 아닙니다. 과거 현물-고정 스프레드 일별 시계열은 구할 수 없어
**레이어 2(재고) 규칙만** 재현합니다:

  ③ DIO 2분기 연속 상승      cycle.checklist 와 같은 기준 (DIO_RISING_MIN)
  ④ 재고-매출 증가율 갭 > 0   직전 분기 대비 (%p)
  ⑤ 완제품 비중 급증          과거 재고 구성 자료가 없어 재현 불가

그리고 변형 규칙(갭 2분기 연속, 갭 전년동기 대비, ③과 ④ 동시)을 같이 채점해
어느 쪽이 덜 시끄럽고 더 일찍 켜지는지 봅니다.

================================================================================
피크는 어떻게 정하나 — 외부 판정 없이 데이터에서
================================================================================
매출 저점(trough) 다음의 매출 최고 분기를 피크로 둡니다. 저점·피크는
회사 자체 매출에서 찾습니다 (find_cycles). 채점은 두 가지입니다:

  · 피크 대비 첫 점등   피크 −4 ~ +4분기 안에서 처음 켜진 분기 (음수 = 선행)
  · 확장기 오경보       저점 다음 ~ 피크 3분기 전까지 켜진 분기 수 (적을수록 좋음)

표본이 피크 4번뿐입니다. 결과는 '경향' 이지 통계적 결론이 아닙니다.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

DATA_FILE = os.path.join("data", "mu_quarterly_history.csv")

#: 피크 전후 몇 분기까지 '피크 근처' 로 보나
WINDOW = 4
#: 확장기 오경보에서 제외하는 피크 직전 분기 수 (이 안에서 켜지면 '선행' 으로 셈)
PRE_PEAK_EXCLUDE = 2
#: 저점 · 피크를 찾을 때 좌우로 보는 분기 수
EXTREMA_SPAN = 4
#: 피크가 저점보다 이만큼(%) 이상 높아야 사이클로 셈 (잔물결 제외)
MIN_SWING_PCT = 30.0
#: 분기 일수 — 원자료에 구간 일수가 없어 고정합니다 (MU 는 13·14주 분기가 섞임)
QUARTER_DAYS = 91.25


@dataclass
class Q:
    end: str
    inventory: float
    cost_of_sales: float
    revenue: float
    dio: float = 0.0
    rising: int = 0
    gap_qoq: float | None = None
    gap_yoy: float | None = None

    @property
    def gross_margin(self) -> float | None:
        if not self.revenue:
            return None
        return (self.revenue - self.cost_of_sales) / self.revenue * 100.0


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    note: str


RULES: tuple[Rule, ...] = (
    Rule("i3", "③ DIO 2분기 연속 상승", "현행 체크리스트 3번"),
    Rule("i4", "④ 재고-매출 갭 > 0 (직전 분기)", "현행 체크리스트 4번"),
    Rule("i4x2", "④ 갭 2분기 연속 > 0", "변형 — 한 분기 튐을 거름"),
    Rule("i4y", "④ 갭 > 0 (전년동기)", "변형 — 계절성 제거"),
    Rule("any", "③ 또는 ④ — 현행 '레이어 2 점등'", "§5 재판정 조건의 재고 부분"),
    Rule("both", "③ 그리고 ④", "변형 — 두 재고 신호 동시"),
)


@dataclass
class Cycle:
    trough: str
    peak: str
    trough_rev: float
    peak_rev: float


@dataclass
class RuleScore:
    rule: Rule
    lit_quarters: int
    total: int
    first_vs_peak: list[int | None]     # 사이클마다 피크 대비 첫 점등(분기)
    early_alarms: int
    expansion_quarters: int
    lit_ends: list[str] = field(default_factory=list)

    @property
    def lit_share(self) -> float:
        return self.lit_quarters / self.total * 100.0 if self.total else 0.0

    @property
    def median_lead(self) -> float | None:
        vals = sorted(v for v in self.first_vs_peak if v is not None)
        if not vals:
            return None
        m = len(vals) // 2
        return float(vals[m]) if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2


@dataclass
class Result:
    company: str
    source: str
    quarters: list[Q]
    cycles: list[Cycle]
    scores: list[RuleScore]
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.scores)

    @property
    def span(self) -> str:
        return f"{self.quarters[0].end[:7]} ~ {self.quarters[-1].end[:7]}" if self.quarters else ""

    def score(self, key: str) -> RuleScore | None:
        return next((s for s in self.scores if s.rule.key == key), None)


# ──────────────────────────────────────────────────────────────────────────────
# 계산
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(path: str) -> tuple[list[Q], str]:
    """'#' 주석 줄은 출처로 모아 돌려줍니다."""
    notes: list[str] = []
    rows: list[Q] = []
    with open(path, encoding="utf-8") as fh:
        lines = []
        for line in fh:
            if line.startswith("#"):
                notes.append(line.lstrip("# ").strip())
            elif line.strip():
                lines.append(line)
    for r in csv.DictReader(lines):
        rows.append(Q(end=r["period_end"], inventory=float(r["inventory"]),
                      cost_of_sales=float(r["cost_of_sales"]), revenue=float(r["revenue"])))
    rows.sort(key=lambda q: q.end)
    return rows, " ".join(notes)


def enrich(quarters: list[Q], rising_min: int = 2) -> list[Q]:
    for k, q in enumerate(quarters):
        q.dio = q.inventory / q.cost_of_sales * QUARTER_DAYS if q.cost_of_sales > 0 else 0.0
        q.rising = 0
        j = k
        while j > 0 and quarters[j].dio > quarters[j - 1].dio:
            q.rising += 1
            j -= 1
        q.gap_qoq = _gap(q, quarters[k - 1]) if k >= 1 else None
        q.gap_yoy = _gap(q, quarters[k - 4]) if k >= 4 else None
    return quarters


def _gap(cur: Q, prev: Q) -> float | None:
    if prev.inventory <= 0 or prev.revenue <= 0:
        return None
    return (cur.inventory / prev.inventory - 1) * 100 - (cur.revenue / prev.revenue - 1) * 100


def lit(rule_key: str, quarters: list[Q], k: int, rising_min: int = 2) -> bool:
    q = quarters[k]
    i3 = q.rising >= rising_min
    i4 = q.gap_qoq is not None and q.gap_qoq > 0
    if rule_key == "i3":
        return i3
    if rule_key == "i4":
        return i4
    if rule_key == "i4x2":
        return k >= 1 and i4 and (quarters[k - 1].gap_qoq or 0) > 0
    if rule_key == "i4y":
        return q.gap_yoy is not None and q.gap_yoy > 0
    if rule_key == "any":
        return i3 or i4
    if rule_key == "both":
        return i3 and i4
    raise KeyError(rule_key)


def find_cycles(quarters: list[Q], span: int = EXTREMA_SPAN,
                min_swing: float = MIN_SWING_PCT) -> list[Cycle]:
    """매출 저점 → 다음 매출 최고점. 둘 다 좌우 span 분기 안에서 극값이어야 합니다.

    마지막 저점 뒤의 최고점은 아직 진행 중일 수 있어 좌우 span 분기를 다 볼 수
    있을 때만 피크로 인정합니다 (끝에서 span 분기 안이면 제외).
    """
    revs = [q.revenue for q in quarters]
    n = len(revs)

    def is_min(i: int) -> bool:
        lo, hi = max(0, i - span), min(n, i + span + 1)
        return revs[i] == min(revs[lo:hi])

    def is_max(i: int) -> bool:
        if i + span >= n:
            return False
        lo, hi = max(0, i - span), i + span + 1
        return revs[i] == max(revs[lo:hi])

    cycles: list[Cycle] = []
    i = 0
    while i < n:
        if is_min(i):
            j = next((j for j in range(i + 1, n) if is_max(j)), None)
            if j is None:
                break
            if revs[j] >= revs[i] * (1 + min_swing / 100):
                cycles.append(Cycle(quarters[i].end, quarters[j].end, revs[i], revs[j]))
            i = j + 1
        else:
            i += 1
    return cycles


def score(quarters: list[Q], cycles: list[Cycle], rule: Rule,
          rising_min: int = 2) -> RuleScore:
    ends = [q.end for q in quarters]
    lits = [k for k in range(len(quarters)) if lit(rule.key, quarters, k, rising_min)]
    lit_set = set(lits)
    firsts: list[int | None] = []
    early = exp_n = 0
    for c in cycles:
        ti, pi = ends.index(c.trough), ends.index(c.peak)
        first = next((k - pi for k in range(max(0, pi - WINDOW), min(len(ends), pi + WINDOW + 1))
                      if k in lit_set), None)
        firsts.append(first)
        expansion = range(ti + 1, max(ti + 1, pi - PRE_PEAK_EXCLUDE))
        exp_n += len(expansion)
        early += sum(1 for k in expansion if k in lit_set)
    return RuleScore(rule=rule, lit_quarters=len(lits), total=len(quarters),
                     first_vs_peak=firsts, early_alarms=early, expansion_quarters=exp_n,
                     lit_ends=[ends[k] for k in lits])


def run(quarters: list[Q], *, company: str = "Micron", source: str = "",
        rising_min: int = 2) -> Result:
    if len(quarters) < 12:
        return Result(company, source, quarters, [], [],
                      error=f"분기가 {len(quarters)}개뿐이라 사이클을 찾을 수 없습니다 (12개 이상 필요)")
    enrich(quarters, rising_min)
    cycles = find_cycles(quarters)
    if not cycles:
        return Result(company, source, quarters, [], [], error="매출 사이클(저점→피크)을 찾지 못했습니다")
    scores = [score(quarters, cycles, r, rising_min) for r in RULES]
    return Result(company, source, quarters, cycles, scores)


def run_file(path: str = DATA_FILE, *, rising_min: int = 2) -> Result:
    """번들한 MU 이력으로 돌립니다. 파일이 없어도 던지지 않습니다."""
    if not os.path.exists(path):
        return Result("Micron", "", [], [], [], error=f"{path} 가 없습니다")
    try:
        quarters, source = load_csv(path)
    except (OSError, ValueError, KeyError) as exc:
        return Result("Micron", "", [], [], [], error=f"{path} 를 읽지 못했습니다 — {exc}")
    return run(quarters, source=source, rising_min=rising_min)
