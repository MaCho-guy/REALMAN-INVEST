"""
SEC EDGAR companyfacts — 기업당 **1회 요청**으로 전 계정 전 기간.

왜 companyconcept 이 아니라 companyfacts 인가:

  companyconcept : 한 기업 × 한 계정   → 10개 계정을 보려면 10회 요청
  companyfacts   : 한 기업 × 전 계정   → 1회 요청

스크리닝은 기업 수가 많고 계정 수도 많아서(ROE·부채·마진·설비투자…) 곱하면
요청이 폭발합니다. 30개 기업 × 10개 계정 = 300회 vs 30회. 초당 10건 제한이
있으니 30초 vs 3초입니다.

대신 **응답이 큽니다** — 신고 이력이 긴 대기업은 수 MB 입니다. 그래서 받은 즉시
필요한 계정만 뽑고 나머지는 버립니다.

반환형은 edgar_xbrl.Fact 를 그대로 씁니다. 기간 분류(is_annual 등)와 중복 제거를
재사용하려는 것이고, 재고 지표 쪽과 같은 타입을 쓰면 코드가 갈라지지 않습니다.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

from sources.edgar_xbrl import Fact, dedupe

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TIMEOUT = 45                 # 응답이 수 MB 라 넉넉히 둡니다
MIN_INTERVAL = 0.12          # SEC 초당 10건 제한 (여유를 둬 8.3건/초)

#: 동시 요청 수. 10 이 아니라 6 인 이유: 응답이 기업당 수 MB 라 많이 띄우면
#: Streamlit Cloud 무료 티어(메모리 1GB)에서 터집니다. 시작 간격을
#: MIN_INTERVAL 로 띄우므로 초당 요청 수는 동시성과 무관하게 지켜집니다.
MAX_WORKERS = 6

_last_request_at = 0.0
_throttle_lock = threading.Lock()


class FactsError(RuntimeError):
    """companyfacts 조회 실패."""


class FactsNotFound(FactsError):
    """해당 CIK 의 XBRL 데이터가 없습니다."""


@dataclass
class CompanyFacts:
    """한 기업의 계정별 사실 목록."""

    cik: int
    entity_name: str
    by_tag: dict[str, list[Fact]]

    #: 응답에 있었던 전체 계정 수 (추려내기 전)
    total_tags: int = 0

    def get(self, tags: tuple[str, ...]) -> tuple[str, list[Fact]]:
        """태그 후보를 순서대로 찾아 첫 성공을 돌려줍니다.

        기업마다 같은 항목에 다른 태그를 씁니다(CostOfRevenue vs
        CostOfGoodsAndServicesSold). 재고 지표 쪽과 같은 폴백 규칙입니다.
        """
        for tag in tags:
            facts = self.by_tag.get(tag)
            if facts:
                return tag, facts
        return "", []

    def annual(self, tags: tuple[str, ...]) -> tuple[str, list[Fact]]:
        """연간 구간(300~400일)만. 손익·현금흐름 계정에 씁니다."""
        tag, facts = self.get(tags)
        return tag, [f for f in facts if f.is_annual]

    def instants(self, tags: tuple[str, ...]) -> tuple[str, list[Fact]]:
        """시점값만. 재무상태표 계정(자본·부채)에 씁니다."""
        tag, facts = self.get(tags)
        return tag, [f for f in facts if f.is_instant]


def _throttle() -> None:
    """요청 **시작 시점**을 MIN_INTERVAL 간격으로 벌립니다.

    잠금이 필요한 이유: 전역 변수만 보고 판단하면 두 스레드가 같은 틈을
    읽고 동시에 나가서 초당 제한을 넘깁니다. SEC 는 넘기면 차단합니다.

    sleep 을 잠금 안에서 하는 것은 의도입니다 — 직렬화되는 것은 '출발
    순서' 뿐이고, 실제 HTTP 왕복은 잠금 밖에서 겹쳐 일어납니다.
    """
    global _last_request_at
    with _throttle_lock:
        gap = time.monotonic() - _last_request_at
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_request_at = time.monotonic()


def parse_facts(payload: dict, cik: int, *, keep: set[str] | None = None,
                taxonomies: tuple[str, ...] = ("us-gaap", "ifrs-full"),
                unit: str = "USD") -> CompanyFacts:
    """companyfacts JSON 을 파싱합니다. 네트워크와 분리해 테스트합니다.

    keep 을 주면 그 태그들만 보관합니다 — 응답이 커서 전부 들고 있으면
    메모리가 낭비됩니다.
    """
    if not isinstance(payload, dict):
        raise FactsError("응답 형식이 예상과 다릅니다.")

    facts_root = payload.get("facts")
    if not isinstance(facts_root, dict) or not facts_root:
        raise FactsNotFound(f"CIK {cik}: XBRL 데이터가 없습니다.")

    by_tag: dict[str, list[Fact]] = {}
    total = 0

    for taxonomy in taxonomies:
        concepts = facts_root.get(taxonomy)
        if not isinstance(concepts, dict):
            continue
        for tag, body in concepts.items():
            total += 1
            if keep is not None and tag not in keep:
                continue
            if not isinstance(body, dict):
                continue
            rows = (body.get("units") or {}).get(unit)
            if not isinstance(rows, list):
                continue

            collected: list[Fact] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                end = row.get("end")
                val = row.get("val")
                if not isinstance(end, str) or not isinstance(val, (int, float)):
                    continue
                start = row.get("start")
                collected.append(Fact(
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
            if collected:
                # 같은 태그가 두 분류체계에 다 있으면 합칩니다
                by_tag[tag] = dedupe(by_tag.get(tag, []) + collected)

    return CompanyFacts(
        cik=cik,
        entity_name=str(payload.get("entityName") or ""),
        by_tag=by_tag,
        total_tags=total,
    )


def fetch_facts(cik: int, user_agent: str, *,
                keep: set[str] | None = None) -> CompanyFacts:
    """한 기업의 전 계정을 1회 요청으로 받아옵니다."""
    _throttle()
    url = FACTS_URL.format(cik=cik)
    try:
        resp = requests.get(
            url, timeout=TIMEOUT,
            headers={"User-Agent": user_agent, "Accept": "application/json",
                     "Accept-Encoding": "gzip, deflate"},
        )
        if resp.status_code == 404:
            raise FactsNotFound(f"CIK {cik}: companyfacts 에 없습니다 (404).")
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status == 403:
            raise FactsError(
                "SEC 가 403 으로 거부했습니다. User-Agent 에 연락처를 넣어야 합니다 "
                "(config.py 의 EDGAR_USER_AGENT)."
            ) from exc
        if status == 429:
            raise FactsError(
                "SEC 가 429(요청 과다)로 거부했습니다. 초당 10건 제한을 넘었습니다."
            ) from exc
        raise FactsError(f"companyfacts 요청 실패 (HTTP {status}): CIK {cik}") from exc
    except requests.RequestException as exc:
        raise FactsError(f"companyfacts 요청 실패: {exc}") from exc
    except ValueError as exc:
        raise FactsError(f"companyfacts 응답 파싱 실패: {exc}") from exc

    return parse_facts(payload, cik, keep=keep)


def fetch_many(ciks: dict[str, int], user_agent: str, *,
               keep: set[str] | None = None,
               ) -> tuple[dict[str, CompanyFacts], dict[str, str]]:
    """여러 기업. 실패는 기업별로 격리됩니다 — 하나가 죽어도 나머지는 삽니다."""
    out: dict[str, CompanyFacts] = {}
    errors: dict[str, str] = {}
    items = list(ciks.items())
    if not items:
        return out, errors

    def one(item: tuple[str, int]) -> tuple[str, CompanyFacts | None, str | None]:
        ticker, cik = item
        try:
            return ticker, fetch_facts(cik, user_agent, keep=keep), None
        except FactsError as exc:
            return ticker, None, str(exc)
        except Exception as exc:  # noqa: BLE001
            return ticker, None, f"예상치 못한 오류: {type(exc).__name__}: {exc}"

    # 순차로 돌리면 65개 기업에 30초~3분이 걸립니다. 각 요청이 수 MB 를
    # 내려받는 동안 그냥 기다리기 때문입니다. 병렬로 겹치면 전체 시간이
    # '초당 제한' 에만 묶입니다 — 65 ÷ 8.3 ≈ 8초 + 파싱.
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(items))) as pool:
        for ticker, facts, err in pool.map(one, items):
            if err is None and facts is not None:
                out[ticker] = facts
            else:
                errors[ticker] = err or "알 수 없는 오류"
    return out, errors
