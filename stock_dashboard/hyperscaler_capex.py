"""
하이퍼스케일러 4사 설비투자(CapEx) — 레이어 4, HBM 수요의 상류 (2026-11-16).

================================================================================
무엇을 · 어디서
================================================================================
Microsoft · Alphabet · Amazon · Meta 의 현금흐름표 '유형자산 취득' 을 SEC EDGAR
XBRL 에서 받습니다 (키 불필요, 미국 재고 지표와 같은 경로).

  태그 후보:  PaymentsToAcquirePropertyPlantAndEquipment  (MSFT · GOOGL · META)
              PaymentsToAcquireProductiveAssets           (AMZN 이 쓰는 태그)

회사마다 쓰는 태그가 다르고, 한 회사가 과거에 다른 태그를 쓰다 바꾼 경우도
있어 **후보 중 최신 종료일이 가장 늦은 태그**를 고릅니다 (pick_latest_tag).

================================================================================
함정 두 가지
================================================================================
1. 현금흐름표는 10-Q 에 누적(YTD)으로만 실립니다. 분기 값은 누적 차분으로
   만듭니다 — sources.edgar_xbrl.derive_quarters.
2. 회계연도가 다릅니다 (MSFT 6월 결산). 다행히 네 회사 모두 분기 말일이
   달력 분기 말(3·6·9·12월 말)이라 **달력 분기로 맞춰** 합산합니다. 분기 말일이
   달력 분기 말에서 10일 넘게 어긋나는 값은 합산에서 뺍니다.

리스(금융리스로 들여온 서버 등)는 이 숫자에 들어가지 않습니다. 회사가 발표하는
'CapEx' 와 정의가 다를 수 있다는 뜻입니다 — 화면에 적어 둡니다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

COMPANIES: tuple[tuple[str, str], ...] = (
    ("MSFT", "Microsoft"), ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta"))

TAGS: tuple[str, ...] = ("PaymentsToAcquirePropertyPlantAndEquipment",
                         "PaymentsToAcquireProductiveAssets")

#: 분기 말일이 달력 분기 말에서 이만큼(일)까지 어긋나도 같은 분기로 봅니다
ALIGN_TOLERANCE_DAYS = 10
#: 화면에 보여줄 분기 수
SHOW_QUARTERS = 6


def calendar_quarter(end: str) -> str | None:
    """'2026-09-30' → '2026Q3'. 달력 분기 말에서 너무 멀면 None."""
    try:
        d = dt.date.fromisoformat(end)
    except ValueError:
        return None
    best: tuple[int, str] | None = None
    for y in (d.year - 1, d.year, d.year + 1):
        for q, (m, day) in enumerate(((3, 31), (6, 30), (9, 30), (12, 31)), start=1):
            gap = abs((d - dt.date(y, m, day)).days)
            if best is None or gap < best[0]:
                best = (gap, f"{y}Q{q}")
    return best[1] if best and best[0] <= ALIGN_TOLERANCE_DAYS else None


@dataclass
class CompanyCapex:
    symbol: str
    name: str
    tag: str = ""
    by_quarter: dict = field(default_factory=dict)     # '2026Q3' → 백만 달러
    derived: set = field(default_factory=set)          # 누적 차분으로 만든 분기
    error: str = ""


@dataclass
class CapexTable:
    companies: list[CompanyCapex]
    quarters: list[str]                                # 오래된 → 최신

    def total(self, q: str) -> float | None:
        """네 회사가 모두 있을 때만 합계. 하나라도 빠지면 None — 부분합을 합계로 보이지 않게."""
        vals = [c.by_quarter.get(q) for c in self.companies if not c.error]
        if not vals or any(v is None for v in vals) or len(vals) < len(self.companies):
            return None
        return sum(vals)

    def yoy(self, q: str, company: CompanyCapex | None = None) -> float | None:
        prev = _shift(q, -4)
        if company is None:
            a, b = self.total(q), self.total(prev)
        else:
            a, b = company.by_quarter.get(q), company.by_quarter.get(prev)
        if a is None or not b:
            return None
        return (a / b - 1) * 100

    @property
    def latest_full(self) -> str | None:
        """네 회사 합계가 나오는 가장 최근 분기."""
        return next((q for q in reversed(self.quarters) if self.total(q) is not None), None)

    @property
    def ok(self) -> bool:
        return any(not c.error and c.by_quarter for c in self.companies)


def _shift(q: str, n: int) -> str:
    y, k = int(q[:4]), int(q[-1])
    idx = y * 4 + (k - 1) + n
    return f"{idx // 4}Q{idx % 4 + 1}"


def to_quarters(facts: list) -> tuple[dict, set]:
    """XBRL Fact 목록(누적 포함) → ({'2026Q3': 백만 달러}, 차분 분기 집합)."""
    from sources.edgar_xbrl import derive_quarters

    out: dict[str, float] = {}
    derived: set[str] = set()
    for f in derive_quarters(facts):
        q = calendar_quarter(f.end)
        if q is None:
            continue
        out[q] = f.val / 1e6
        if "(차분)" in f.form:
            derived.add(q)
        else:
            derived.discard(q)
    return out, derived


def pick_latest_tag(candidates: dict[str, list]) -> tuple[str, list]:
    """{태그: Fact 목록} 중 최신 종료일이 가장 늦은 태그."""
    best_tag, best_facts, best_end = "", [], ""
    for tag, facts in candidates.items():
        if not facts:
            continue
        end = max(f.end for f in facts)
        if end > best_end:
            best_tag, best_facts, best_end = tag, facts, end
    return best_tag, best_facts


def build(per_company: dict[str, tuple[str, list] | str],
          show: int = SHOW_QUARTERS) -> CapexTable:
    """{티커: (태그, Fact 목록) 또는 오류 문자열} → CapexTable."""
    companies: list[CompanyCapex] = []
    all_q: set[str] = set()
    for sym, name in COMPANIES:
        got = per_company.get(sym)
        if got is None:
            companies.append(CompanyCapex(sym, name, error="수집되지 않음"))
            continue
        if isinstance(got, str):
            companies.append(CompanyCapex(sym, name, error=got))
            continue
        tag, facts = got
        by_q, derived = to_quarters(facts)
        if not by_q:
            companies.append(CompanyCapex(sym, name, tag=tag, error="분기 값을 만들지 못했습니다"))
            continue
        companies.append(CompanyCapex(sym, name, tag=tag, by_quarter=by_q, derived=derived))
        all_q.update(by_q)
    quarters = sorted(all_q)[-show:]
    return CapexTable(companies=companies, quarters=quarters)


def fetch(user_agent: str, ticker_map: dict, overrides: dict | None = None) -> CapexTable:
    """EDGAR 에서 받아 표를 만듭니다. 회사별 실패는 그 회사 칸에 담고 계속합니다."""
    from sources import edgar_xbrl

    overrides = overrides or {}
    per: dict[str, tuple[str, list] | str] = {}
    for sym, _name in COMPANIES:
        cik = overrides.get(sym) or ticker_map.get(sym)
        if cik is None:
            per[sym] = f"'{sym}' CIK 를 찾지 못했습니다"
            continue
        cands: dict[str, list] = {}
        errs: list[str] = []
        for tag in TAGS:
            try:
                cands[tag] = edgar_xbrl.fetch_concept(cik, tag, user_agent)
            except edgar_xbrl.XbrlError as exc:
                errs.append(str(exc))
        tag, facts = pick_latest_tag(cands)
        per[sym] = (tag, facts) if facts else ("; ".join(errs[:2]) or "값 없음")
    return build(per)
