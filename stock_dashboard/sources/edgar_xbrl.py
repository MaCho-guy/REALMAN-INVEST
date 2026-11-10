"""
SEC EDGAR XBRL — 미국 기업의 계정 시계열. 키 불필요.

================================================================================
왜 이게 필요한가
================================================================================
한국 2사(삼성전자·SK하이닉스)의 재고 지표는 DART 에서 계산합니다. 그런데
비교 대상인 Micron 은 미국 기업이라 DART 에 없습니다. 메모리 3사를 같은
화면에서 비교하려면 MU 의 재고·매출원가도 같은 방식으로 뽑아야 합니다.

EDGAR 의 XBRL API 가 그걸 해줍니다 — **키가 필요 없고**, 한 계정의 전체
보고 이력을 한 번에 돌려줍니다.

    GET data.sec.gov/api/xbrl/companyconcept/CIK{10자리}/{taxonomy}/{tag}.json

응답: {cik, taxonomy, tag, label, entityName,
       units: {"USD": [{start?, end, val, accn, fy, fp, form, filed}, ...]}}

taxonomy 는 us-gaap / ifrs-full / dei / srt 가 가능합니다. 미국 기업은 us-gaap,
ASML 처럼 20-F 를 내는 외국 기업은 ifrs-full 입니다.

================================================================================
두 가지 함정
================================================================================
1. **중복 보고.** 같은 기간이 여러 공시에 다시 실립니다 (10-Q 로 처음 나오고,
   이후 10-K 와 다음 해 10-Q 의 비교란에 또 실림). 그래서 (start, end) 가 같은
   항목이 여러 개 옵니다. **filed 가 가장 늦은 것만** 남겨야 합니다 —
   정정본이 있으면 그게 최신입니다.

2. **기간 구분.** 재무상태표 항목(재고)은 시점값이라 start 가 없고 end 만
   있습니다. 손익계산서 항목(매출원가·매출)은 start~end 구간값입니다.
   분기(약 90일)와 연간(약 365일)을 섞으면 DIO 가 망가지므로 일수로 분류합니다.
   마이크론은 53주 회계연도가 있어 분기가 84~98일로 흔들립니다.

SEC 규칙: 연락처가 담긴 User-Agent 를 보내고, 초당 10건을 넘기지 않습니다.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import requests

CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json"
TIMEOUT = 20
MIN_INTERVAL = 0.15

#: 기간 분류 기준(일). 마이크론의 53주 회계연도를 감안해 넉넉히 둡니다.
QUARTER_MIN_DAYS, QUARTER_MAX_DAYS = 60, 120
ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS = 300, 400

_last_request_at = 0.0


class XbrlError(RuntimeError):
    pass


class XbrlNotFound(XbrlError):
    """해당 계정을 그 기업이 보고하지 않음 (404). 다음 태그 후보로 넘어가면 됩니다."""


@dataclass
class Fact:
    """XBRL 보고 한 건."""

    start: str | None       # YYYY-MM-DD, 시점값이면 None
    end: str                # YYYY-MM-DD
    val: float
    form: str               # 10-K / 10-Q / 20-F …
    fy: int | None          # 회계연도
    fp: str                 # Q1 / Q2 / Q3 / FY
    filed: str              # 공시 제출일
    accn: str = ""
    tag: str = ""

    @property
    def duration_days(self) -> int | None:
        if not self.start:
            return None
        try:
            s = dt.date.fromisoformat(self.start)
            e = dt.date.fromisoformat(self.end)
        except ValueError:
            return None
        return (e - s).days

    @property
    def is_instant(self) -> bool:
        return self.start is None

    @property
    def is_quarterly(self) -> bool:
        d = self.duration_days
        return d is not None and QUARTER_MIN_DAYS <= d <= QUARTER_MAX_DAYS

    @property
    def is_annual(self) -> bool:
        d = self.duration_days
        return d is not None and ANNUAL_MIN_DAYS <= d <= ANNUAL_MAX_DAYS

    @property
    def period_label(self) -> str:
        """'FY2026 Q3' 형태. fy/fp 가 없으면 종료일로 대체합니다."""
        if self.fy and self.fp:
            return f"FY{self.fy} {self.fp}"
        return self.end


def _throttle() -> None:
    global _last_request_at
    gap = time.monotonic() - _last_request_at
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_request_at = time.monotonic()


def fetch_concept(cik: int, tag: str, user_agent: str,
                  *, taxonomy: str = "us-gaap", unit: str = "USD") -> list[Fact]:
    """한 계정의 전체 보고 이력. 중복 보고는 제거합니다."""
    _throttle()
    url = CONCEPT_URL.format(cik=cik, taxonomy=taxonomy, tag=tag)
    try:
        resp = requests.get(
            url, timeout=TIMEOUT,
            headers={"User-Agent": user_agent, "Accept": "application/json",
                     "Accept-Encoding": "gzip, deflate"},
        )
        if resp.status_code == 404:
            raise XbrlNotFound(f"'{tag}' 을 보고하지 않습니다 (taxonomy={taxonomy}).")
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status == 403:
            raise XbrlError(
                "SEC 가 403 으로 거부했습니다. User-Agent 에 연락처를 넣어야 합니다 "
                "(config.py 의 EDGAR_USER_AGENT)."
            ) from exc
        raise XbrlError(f"XBRL 요청 실패 (HTTP {status}): {tag}") from exc
    except requests.RequestException as exc:
        raise XbrlError(f"XBRL 요청 실패: {exc}") from exc
    except ValueError as exc:
        raise XbrlError(f"XBRL 응답 파싱 실패: {exc}") from exc

    if not isinstance(payload, dict):
        raise XbrlError("XBRL 응답 형식이 예상과 다릅니다.")

    rows = (payload.get("units") or {}).get(unit)
    if not isinstance(rows, list):
        raise XbrlNotFound(f"'{tag}' 에 {unit} 단위 값이 없습니다.")

    facts: list[Fact] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        end = row.get("end")
        val = row.get("val")
        if not isinstance(end, str) or not isinstance(val, (int, float)):
            continue
        start = row.get("start")
        facts.append(Fact(
            start=start if isinstance(start, str) else None,
            end=end,
            val=float(val),
            form=str(row.get("form") or ""),
            fy=row.get("fy") if isinstance(row.get("fy"), int) else None,
            fp=str(row.get("fp") or ""),
            filed=str(row.get("filed") or ""),
            accn=str(row.get("accn") or ""),
            tag=tag,
        ))

    return dedupe(facts)


def dedupe(facts: list[Fact]) -> list[Fact]:
    """같은 기간의 중복 보고를 제거합니다 — filed 가 가장 늦은 것만 남깁니다.

    같은 기간이 10-Q, 10-K, 다음 해 비교란에 반복 실립니다. 값이 정정되는
    경우도 있어, 제출일이 가장 늦은 것이 최신입니다.
    """
    best: dict[tuple[str | None, str], Fact] = {}
    for fact in facts:
        key = (fact.start, fact.end)
        prev = best.get(key)
        if prev is None or fact.filed > prev.filed:
            best[key] = fact
    out = list(best.values())
    out.sort(key=lambda f: (f.end, f.start or ""))
    return out


def fetch_first_available(cik: int, tags: tuple[str, ...], user_agent: str,
                          *, taxonomy: str = "us-gaap",
                          unit: str = "USD") -> tuple[str, list[Fact]]:
    """태그 후보를 순서대로 시도해 첫 성공을 돌려줍니다.

    기업마다 쓰는 태그가 달라서(CostOfRevenue vs CostOfGoodsAndServicesSold)
    후보 목록이 필요합니다. 전부 실패하면 XbrlNotFound.
    """
    errors: list[str] = []
    for tag in tags:
        try:
            facts = fetch_concept(cik, tag, user_agent, taxonomy=taxonomy, unit=unit)
        except XbrlNotFound as exc:
            errors.append(f"{tag}: {exc}")
            continue
        if facts:
            return tag, facts
        errors.append(f"{tag}: 값이 비어 있습니다.")
    raise XbrlNotFound(
        f"후보 태그 {len(tags)}개 모두 실패 — " + " / ".join(errors[:3])
    )


# ──────────────────────────────────────────────────────────────────────────────
# 기간 정렬 — 시점값(재고)을 구간값(매출원가)에 붙이기
# ──────────────────────────────────────────────────────────────────────────────

def align_instant_to_duration(
    instants: list[Fact], durations: list[Fact], *, tolerance_days: int = 7
) -> list[tuple[Fact, Fact]]:
    """구간값의 종료일과 같은(또는 tolerance 안의) 시점값을 짝지어 줍니다.

    DIO = 기말 재고 ÷ 기간 매출원가 이므로, 매출원가 구간의 **종료일 시점**
    재고를 써야 합니다. 보고일이 하루이틀 어긋나는 경우가 있어 허용치를 둡니다.
    """
    by_end: dict[str, Fact] = {f.end: f for f in instants}
    pairs: list[tuple[Fact, Fact]] = []

    for dur in durations:
        inst = by_end.get(dur.end)
        if inst is None:
            # 종료일이 정확히 안 맞으면 가장 가까운 시점값을 찾습니다
            try:
                target = dt.date.fromisoformat(dur.end)
            except ValueError:
                continue
            best: Fact | None = None
            best_gap = tolerance_days + 1
            for cand in instants:
                try:
                    gap = abs((dt.date.fromisoformat(cand.end) - target).days)
                except ValueError:
                    continue
                if gap < best_gap:
                    best, best_gap = cand, gap
            inst = best
        if inst is not None:
            pairs.append((inst, dur))

    return pairs
