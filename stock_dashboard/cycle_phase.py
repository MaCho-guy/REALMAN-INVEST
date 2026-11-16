"""
사이클 국면 — 4트랙 판정 기록을 화면에 올립니다 (2026-11-16).

================================================================================
왜 '기록' 인가
================================================================================
지표체계 v2 의 판정은 사람이 내립니다. 체크리스트 10개 중 공시에서 숫자로
판정되는 건 재고 쪽 3개(레이어 2)뿐이고, 나머지는 메모리 현물가(유료 데이터),
CapEx 가이던스·경영진 어조(어닝콜), 수요 파괴(시장조사) 입니다. 그래서 이
모듈은 국면을 **계산하지 않습니다.** `cycle_phase.json` 에 적힌 판정을 읽어
보여주고, 다음 세 가지만 기계가 합니다:

  1. 신선도 — 판정이 14일, 현물가가 7일보다 오래되면 화면에 드러냅니다.
     거부권을 가진 가격 층이 묵은 값으로 판정하면 체계 전체가 틀립니다.
  2. 상태 — §5 규칙(3개 이상 점등 → 재판정, 단 레이어 2 없이는 '전환 감시')을
     점등 개수로 그대로 계산합니다. 사람이 세다 틀리는 일을 없앱니다.
  3. 공시 대조 — 재고 3항목은 공시로 자동 판정한 값(cycle.checklist)과 기록을
     나란히 놓습니다. 다르면 "공시가 바뀌었다 — 재점검" 입니다. 자동 값으로
     기록을 **덮어쓰지 않습니다** — 요약·내 종목·사이클 탭이 같은 판정을
     보여야 하기 때문입니다 (두 화면이 다르면 신뢰를 잃습니다).

파일이 없거나 깨져도 예외를 던지지 않습니다. Phase.error 에 사유를 담아
돌려주고, 화면은 그 사유를 보여주거나 해당 칸을 생략합니다.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field

PHASE_FILE = "cycle_phase.json"

#: 판정 기록이 이 일수보다 오래되면 '점검 필요'.
STALE_PHASE_DAYS = 14
#: 현물가 입력이 이 일수보다 오래되면 스프레드를 '오래됨' 으로 표시.
STALE_PRICE_DAYS = 7
#: §5 — 이 개수 이상 점등이면 재판정 대상.
WATCH_MIN_LIT = 3
#: 체크리스트 한 항목의 근거가 이 일수보다 오래되면 '재확인' (2026-11-16).
#: 판정 전체(14일)보다 길게 둡니다 — 분기 공시 항목은 한 달 넘게 안 바뀌는 게 정상.
EVIDENCE_STALE_DAYS = 30

#: 근거 강도 — 점등 항목에만 씁니다. 개수만 세면 11/13 처럼 "4개 그대로인데
#: 근거가 강해졌다" 가 화면에 안 보여서 추가했습니다.
STRENGTH_LABEL = {1: "약", 2: "중", 3: "강"}
STRENGTH_RULE = {1: "간접 · 조짐 (전망, 해석)", 2: "한 출처로 확인 (수치 또는 원문)",
                 3: "여러 출처 · 실적으로 확인"}

PHASE_GLYPH = {1: "①", 2: "②", 3: "③", 4: "④"}
PHASE_NAME = {1: "회복기", 2: "확장기", 3: "피크·둔화", 4: "하강기"}
STATES = ("lit", "unlit", "unknown")
STATE_LABEL = {"lit": "점등", "unlit": "미점등", "unknown": "판정 불가"}

STATUS_HOLD = "유지"
STATUS_WATCH = "전환 감시"
STATUS_REJUDGE = "재판정 필요"

#: 자동 판정 키 → cycle.checklist() 결과에서의 순서
AUTO_INDEX = {"dio_rising": 0, "inv_gap": 1, "finished_jump": 2}


@dataclass(frozen=True)
class Track:
    key: str
    name: str
    abbr: str
    phase: int
    short: str
    label: str
    why: str = ""

    @property
    def glyph(self) -> str:
        return PHASE_GLYPH.get(self.phase, "?")


@dataclass(frozen=True)
class CheckRow:
    n: int
    label: str
    layer: str
    state: str
    detail: str = ""
    auto: str = ""
    next: str = ""
    #: 근거일 — 점등이면 근거 자료의 날짜, 아니면 미점등을 마지막으로 확인한 날
    evidence_date: dt.date | None = None
    #: 근거 강도 1~3 (점등일 때만, 아니면 0)
    strength: int = 0

    def evidence_age(self, today: dt.date) -> int | None:
        return (today - self.evidence_date).days if self.evidence_date else None

    def evidence_stale(self, today: dt.date) -> bool:
        age = self.evidence_age(today)
        return age is None or age > EVIDENCE_STALE_DAYS


@dataclass(frozen=True)
class HistoryEntry:
    """판정 이력 한 줄. 나중에 실제 국면과 대조해 판정 품질을 재려고 쌓습니다."""

    as_of: dt.date
    phases: dict           # 트랙 key → short ("②후반")
    lit: int
    status: str
    note: str = ""


@dataclass(frozen=True)
class Prices:
    spot_date: dt.date | None = None
    ddr5_16gb_spot: float | None = None
    ddr4_8gb_spot: float | None = None
    ddr4_8gb_contract: float | None = None
    contract_month: str = ""
    ref_date: dt.date | None = None
    ref_ddr5_16gb_spot: float | None = None
    ref_ddr4_8gb_spot: float | None = None
    source: str = ""


@dataclass(frozen=True)
class Exposure:
    tracks: tuple[str, ...]
    via: str = ""
    note: str = ""


@dataclass(frozen=True)
class Upcoming:
    date: dt.date
    what: str
    check: str = ""


@dataclass(frozen=True)
class AutoCheck:
    """공시로 자동 판정한 재고 항목 하나."""

    n: int
    state: str              # lit / unlit / unknown
    detail: str             # "Micron 미점등 · 삼성전자 점등 · SK하이닉스 판정 불가"
    agrees: bool | None     # 기록과 같은가 (둘 중 하나라도 판정 불가면 None)


@dataclass
class Phase:
    as_of: dt.date | None = None
    source: str = ""
    overall: str = ""
    checklist_track: str = "dram"
    tracks: list[Track] = field(default_factory=list)
    checklist: list[CheckRow] = field(default_factory=list)
    prices: Prices = field(default_factory=Prices)
    exposure: dict[str, Exposure] = field(default_factory=dict)
    upcoming: list[Upcoming] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    error: str = ""

    # ── 기본 ────────────────────────────────────────────────────────────
    @property
    def ok(self) -> bool:
        return not self.error and self.as_of is not None and bool(self.tracks)

    def track(self, key: str) -> Track | None:
        return next((t for t in self.tracks if t.key == key), None)

    @property
    def main_track(self) -> Track | None:
        """체크리스트가 판정하는 트랙(기본 범용 D램)."""
        return self.track(self.checklist_track)

    # ── 신선도 ──────────────────────────────────────────────────────────
    def age_days(self, today: dt.date) -> int | None:
        return (today - self.as_of).days if self.as_of else None

    def is_stale(self, today: dt.date) -> bool:
        age = self.age_days(today)
        return age is not None and age > STALE_PHASE_DAYS

    def price_age_days(self, today: dt.date) -> int | None:
        d = self.prices.spot_date
        return (today - d).days if d else None

    def price_stale(self, today: dt.date) -> bool:
        age = self.price_age_days(today)
        return age is None or age > STALE_PRICE_DAYS

    # ── 체크리스트 상태 (§5) ──────────────────────────────────────────────
    @property
    def lit_count(self) -> int:
        return sum(1 for c in self.checklist if c.state == "lit")

    @property
    def layer2_lit(self) -> bool:
        """재고(레이어 2)가 '켜졌다' 고 볼 것인가 — ③ DIO 연속 상승과 ④ 재고-매출 갭이
        **둘 다** 점등이거나, ⑤ 완제품 비중 급증이 점등일 때 (2026-11-16 사용자 결정).

        예전 규칙은 셋 중 하나만 켜져도 인정했습니다. 백테스트(MU 2009~2025, 66분기)에서
        그 조건은 전체 분기의 48% 에서 성립해 거름 역할을 못 했고(확장기 오경보 6/23),
        ③·④ 동시는 15% · 오경보 0/23 이었습니다 — claude/사이클-체크리스트-백테스트.md.
        ⑤ 는 과거 자료가 없어 검증하지 못했지만 '만들어 놓고 못 판 재고' 라 단독으로 둡니다.
        항목은 번호가 아니라 auto 키로 찾습니다 (번호가 바뀌어도 규칙이 따라가게).
        """
        by_auto = {c.auto: c.state == "lit" for c in self.checklist if c.auto}
        both = by_auto.get("dio_rising", False) and by_auto.get("inv_gap", False)
        return both or by_auto.get("finished_jump", False)

    @property
    def status(self) -> str:
        """§5 규칙: 3개 이상 점등 → 재판정. 단 재고(레이어 2)가 켜지지 않으면
        '전환 감시' 로 둡니다 — 가격·수요 신호만으로는 국면을 바꾸지 않는다는 규칙입니다.
        '재고가 켜졌다' 의 정의는 layer2_lit (③·④ 동시 또는 ⑤)."""
        if self.lit_count < WATCH_MIN_LIT:
            return STATUS_HOLD
        return STATUS_REJUDGE if self.layer2_lit else STATUS_WATCH

    # ── 가격 (레이어 1) ──────────────────────────────────────────────────
    @staticmethod
    def _spread(spot: float | None, contract: float | None) -> float | None:
        if spot is None or not contract:
            return None
        return (spot / contract - 1.0) * 100.0

    @property
    def spread(self) -> float | None:
        """DDR4 8Gb 현물-고정 스프레드(%). 같은 품목끼리만 계산합니다."""
        p = self.prices
        return self._spread(p.ddr4_8gb_spot, p.ddr4_8gb_contract)

    @property
    def ref_spread(self) -> float | None:
        p = self.prices
        return self._spread(p.ref_ddr4_8gb_spot, p.ddr4_8gb_contract)

    @property
    def ddr5_change_pct(self) -> float | None:
        p = self.prices
        if p.ddr5_16gb_spot is None or not p.ref_ddr5_16gb_spot:
            return None
        return (p.ddr5_16gb_spot / p.ref_ddr5_16gb_spot - 1.0) * 100.0

    # ── 종목 ───────────────────────────────────────────────────────────
    def tracks_for(self, symbol: str) -> list[Track]:
        exp = self.exposure.get(symbol)
        if exp is None:
            return []
        return [t for t in (self.track(k) for k in exp.tracks) if t is not None]

    # ── 근거 · 이력 ────────────────────────────────────────────────────
    def stale_evidence(self, today: dt.date) -> list[int]:
        """근거가 EVIDENCE_STALE_DAYS 보다 오래된 항목 번호."""
        return [c.n for c in self.checklist if c.evidence_stale(today)]

    @property
    def strength_counts(self) -> dict[int, int]:
        out = {1: 0, 2: 0, 3: 0}
        for c in self.checklist:
            if c.state == "lit" and c.strength in out:
                out[c.strength] += 1
        return out

    def history_gap(self) -> str:
        """이력 마지막 줄이 현재 기록과 다르면 사유. 같으면 "".

        기록만 고치고 이력에 안 적으면 나중에 '그때 뭐라고 판정했나' 를 잃습니다.
        """
        if not self.history:
            return "판정 이력이 비어 있습니다"
        last = self.history[-1]
        if last.as_of != self.as_of:
            return f"이력 마지막({_md_plain(last.as_of)})이 판정일({_md_plain(self.as_of)})과 다릅니다"
        now = {t.key: t.short for t in self.tracks}
        diff = [k for k, v in now.items() if last.phases.get(k) != v]
        if diff:
            return f"이력의 국면이 기록과 다릅니다 ({', '.join(diff)})"
        if last.lit != self.lit_count:
            return f"이력 점등 {last.lit} ≠ 기록 점등 {self.lit_count}"
        return ""

    def changes_at(self, i: int) -> set[str]:
        """이력 i 번째 줄에서 직전 줄 대비 국면이 바뀐 트랙 key."""
        if i <= 0 or i >= len(self.history):
            return set()
        a, b = self.history[i - 1].phases, self.history[i].phases
        return {k for k in b if a.get(k) != b.get(k)}

    def upcoming_from(self, today: dt.date) -> list[Upcoming]:
        return sorted((u for u in self.upcoming if u.date >= today), key=lambda u: u.date)


# ──────────────────────────────────────────────────────────────────────────────
# 읽기
# ──────────────────────────────────────────────────────────────────────────────

def _md_plain(d: dt.date | None) -> str:
    return f"{d.month}/{d.day}" if d else "?"


def _date(value) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value)[:10])


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse(data: dict) -> Phase:
    """dict → Phase. 형식이 틀리면 ValueError (어느 칸이 틀렸는지 담아서)."""
    if not isinstance(data, dict):
        raise ValueError("최상위가 객체가 아닙니다")
    as_of = _date(data.get("as_of"))
    if as_of is None:
        raise ValueError("as_of(판정 기준일)가 없습니다")

    tracks: list[Track] = []
    for i, t in enumerate(data.get("tracks") or []):
        try:
            phase = int(t["phase"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"tracks[{i}].phase 가 1~4 숫자가 아닙니다") from None
        if phase not in PHASE_GLYPH:
            raise ValueError(f"tracks[{i}].phase={phase} — 1~4 만 씁니다")
        key = str(t.get("key") or "").strip()
        if not key:
            raise ValueError(f"tracks[{i}].key 가 없습니다")
        tracks.append(Track(
            key=key, name=str(t.get("name") or key), abbr=str(t.get("abbr") or key),
            phase=phase,
            short=str(t.get("short") or PHASE_GLYPH[phase]),
            label=str(t.get("label") or PHASE_NAME[phase]),
            why=str(t.get("why") or "")))
    if not tracks:
        raise ValueError("tracks 가 비어 있습니다")
    keys = {t.key for t in tracks}

    checklist: list[CheckRow] = []
    for i, c in enumerate(data.get("checklist") or []):
        state = str(c.get("state") or "unknown")
        if state not in STATES:
            raise ValueError(f"checklist[{i}].state={state!r} — lit/unlit/unknown 만 씁니다")
        auto = str(c.get("auto") or "")
        if auto and auto not in AUTO_INDEX:
            raise ValueError(f"checklist[{i}].auto={auto!r} — {', '.join(AUTO_INDEX)} 만 씁니다")
        try:
            strength = int(c.get("strength") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"checklist[{i}].strength 가 숫자가 아닙니다") from None
        if state == "lit" and strength not in STRENGTH_LABEL:
            raise ValueError(f"checklist[{i}] 점등인데 strength={strength} — 1~3 을 적습니다")
        if state != "lit" and strength:
            raise ValueError(f"checklist[{i}] 점등이 아닌데 strength={strength} — 0 이어야 합니다")
        checklist.append(CheckRow(
            n=int(c.get("n") or i + 1), label=str(c.get("label") or ""),
            layer=str(c.get("layer") or ""), state=state,
            detail=str(c.get("detail") or ""), auto=auto, next=str(c.get("next") or ""),
            evidence_date=_date(c.get("evidence_date")), strength=strength))

    p = data.get("prices") or {}
    prices = Prices(
        spot_date=_date(p.get("spot_date")),
        ddr5_16gb_spot=_num(p.get("ddr5_16gb_spot")),
        ddr4_8gb_spot=_num(p.get("ddr4_8gb_spot")),
        ddr4_8gb_contract=_num(p.get("ddr4_8gb_contract")),
        contract_month=str(p.get("contract_month") or ""),
        ref_date=_date(p.get("ref_date")),
        ref_ddr5_16gb_spot=_num(p.get("ref_ddr5_16gb_spot")),
        ref_ddr4_8gb_spot=_num(p.get("ref_ddr4_8gb_spot")),
        source=str(p.get("source") or ""))

    exposure: dict[str, Exposure] = {}
    for sym, e in (data.get("exposure") or {}).items():
        tk = tuple(str(k) for k in (e.get("tracks") or []))
        unknown = [k for k in tk if k not in keys]
        if unknown:
            raise ValueError(f"exposure[{sym}] 에 없는 트랙: {', '.join(unknown)}")
        exposure[str(sym)] = Exposure(tracks=tk, via=str(e.get("via") or ""),
                                      note=str(e.get("note") or ""))

    upcoming = [Upcoming(date=_date(u["date"]), what=str(u.get("what") or ""),
                         check=str(u.get("check") or ""))
                for u in (data.get("upcoming") or []) if u.get("date")]

    history: list[HistoryEntry] = []
    for i, h in enumerate(data.get("history") or []):
        hd = _date(h.get("as_of"))
        if hd is None:
            raise ValueError(f"history[{i}].as_of 가 없습니다")
        ph = {str(k): str(v) for k, v in (h.get("phases") or {}).items()}
        unknown = [k for k in ph if k not in keys]
        if unknown:
            raise ValueError(f"history[{i}] 에 없는 트랙: {', '.join(unknown)}")
        history.append(HistoryEntry(as_of=hd, phases=ph, lit=int(h.get("lit") or 0),
                                    status=str(h.get("status") or ""),
                                    note=str(h.get("note") or "")))
    history.sort(key=lambda h: h.as_of)

    track_key = str(data.get("checklist_track") or "dram")
    if track_key not in keys:
        raise ValueError(f"checklist_track={track_key!r} 트랙이 없습니다")

    return Phase(as_of=as_of, source=str(data.get("source") or ""),
                 overall=str(data.get("overall") or ""), checklist_track=track_key,
                 tracks=tracks, checklist=checklist, prices=prices,
                 exposure=exposure, upcoming=upcoming, history=history)


def load(path: str) -> Phase:
    """파일을 읽습니다. 실패해도 던지지 않고 Phase(error=사유) 를 돌려줍니다."""
    if not os.path.exists(path):
        return Phase(error=f"{os.path.basename(path)} 파일이 없습니다")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return Phase(error=f"{os.path.basename(path)} 를 읽지 못했습니다 — {exc}")
    try:
        return parse(data)
    except (ValueError, TypeError, KeyError) as exc:
        return Phase(error=f"{os.path.basename(path)} 형식 오류 — {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 공시 대조 — 재고 3항목
# ──────────────────────────────────────────────────────────────────────────────

def cross_check(phase: Phase, trends: dict) -> dict[int, AutoCheck]:
    """재고 항목(auto 키가 있는 것)을 공시로 판정해 기록과 대조합니다.

    읽는 법은 사이클 탭 '판단 근거' 그대로입니다 — 세 회사가 같이 켜지면 업황,
    한 회사만 켜지면 회사 사정. 그래서 **판정된 회사가 2곳 이상**일 때만
    결론을 내고, 그중 2곳 이상 점등이면 점등입니다. 1곳 이하만 판정되면
    '판정 불가' 로 두고 기록을 그대로 씁니다.
    """
    if not phase.ok or not trends:
        return {}
    import cycle  # 무거운 의존(sources.dart)을 쓸 때만 불러옵니다

    per_company: list[tuple[str, list]] = []
    for trend in trends.values():
        if trend is None or not getattr(trend, "quarters", None):
            continue
        try:
            per_company.append((trend.corp_name, cycle.checklist(trend)))
        except Exception:  # noqa: BLE001 - 한 회사가 이상해도 나머지는 대조합니다
            continue
    if not per_company:
        return {}

    out: dict[int, AutoCheck] = {}
    for row in phase.checklist:
        if not row.auto:
            continue
        idx = AUTO_INDEX[row.auto]
        bits, lits = [], []
        for name, items in per_company:
            lit = items[idx].lit if idx < len(items) else None
            lits.append(lit)
            bits.append(f"{name} {STATE_LABEL['lit' if lit else 'unlit' if lit is False else 'unknown']}")
        decided = [x for x in lits if x is not None]
        if len(decided) < 2:
            state = "unknown"
        else:
            state = "lit" if sum(1 for x in decided if x) >= 2 else "unlit"
        agrees = (None if state == "unknown" or row.state == "unknown"
                  else state == row.state)
        out[row.n] = AutoCheck(n=row.n, state=state, detail=" · ".join(bits), agrees=agrees)
    return out


def disagreements(checks: dict[int, AutoCheck]) -> list[int]:
    """기록과 공시 자동 판정이 다른 항목 번호."""
    return sorted(n for n, c in checks.items() if c.agrees is False)


# ──────────────────────────────────────────────────────────────────────────────
# 트랙별 재고 — 낸드 · 레거시에도 레이어 2 (2026-11-16)
# ──────────────────────────────────────────────────────────────────────────────
#
# 체크리스트 자동 대조는 D램 트랙(메모리 3사)만 합니다. 낸드 ③ · 레거시 ① 판정은
# 그동안 가격 · 뉴스로만 내려졌습니다. 같은 재고 계산(cycle.checklist)을 트랙
# 대표 기업에 돌려 트랙 카드 옆에 붙입니다. **판정을 바꾸지 않고 참고로만 둡니다**
# — 낸드 대표가 SanDisk 한 곳뿐이라 '2곳 이상' 규칙을 못 채우기 때문입니다.

@dataclass(frozen=True)
class CompanyInv:
    symbol: str
    name: str
    period: str             # 기준 분기 종료일
    dio: float | None
    dio_change: float | None
    rising: int
    gap: float | None
    i3: bool | None         # DIO 2분기 연속 상승
    i4: bool | None         # 재고-매출 갭 > 0
    error: str = ""


@dataclass(frozen=True)
class TrackInv:
    track: str
    rows: list

    @property
    def decided(self) -> list:
        return [r for r in self.rows if not r.error and r.i3 is not None]

    def count(self, attr: str) -> tuple[int, int]:
        d = [r for r in self.rows if not r.error and getattr(r, attr) is not None]
        return sum(1 for r in d if getattr(r, attr)), len(d)

    @property
    def both(self) -> tuple[int, int]:
        d = [r for r in self.rows if not r.error and r.i3 is not None and r.i4 is not None]
        return sum(1 for r in d if r.i3 and r.i4), len(d)

    @property
    def summary(self) -> str:
        if not self.decided:
            return "재고 공시 대기"
        a, n = self.count("i3")
        b, m = self.count("i4")
        return f"DIO 2분기↑ {a}/{n} · 재고>매출 {b}/{m}"


def track_inventory(groups: dict, errors: dict | None = None) -> dict[str, TrackInv]:
    """{트랙 key: {티커: InventoryTrend}} → {트랙 key: TrackInv}."""
    import cycle  # 무거운 의존은 쓸 때만

    errors = errors or {}
    out: dict[str, TrackInv] = {}
    for track, trends in groups.items():
        rows = []
        for sym, trend in trends.items():
            if trend is None or not getattr(trend, "quarters", None):
                rows.append(CompanyInv(sym, sym, "", None, None, 0, None, None, None,
                                       error=errors.get(sym, "수집되지 않음")))
                continue
            try:
                items = cycle.checklist(trend)
            except Exception as exc:  # noqa: BLE001
                rows.append(CompanyInv(sym, trend.corp_name, "", None, None, 0, None, None,
                                       None, error=str(exc)))
                continue
            latest = trend.latest
            rows.append(CompanyInv(
                symbol=sym, name=trend.corp_name,
                period=(latest.period_end or latest.label) if latest else "",
                dio=latest.dio if latest else None,
                dio_change=trend.dio_qoq_change, rising=trend.dio_rising_quarters,
                gap=trend.inventory_revenue_gap,
                i3=items[0].lit, i4=items[1].lit))
        out[track] = TrackInv(track=track, rows=rows)
    return out
