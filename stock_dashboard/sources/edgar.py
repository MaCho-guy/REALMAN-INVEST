"""
SEC EDGAR 공시 조회.

무료 공개 API 이고 키가 필요 없습니다. 대신 두 가지 규칙이 있습니다:
  1. 연락처가 담긴 User-Agent 헤더를 반드시 보낼 것
  2. 초당 10건을 넘기지 말 것

엔드포인트:
  티커→CIK 매핑   https://www.sec.gov/files/company_tickers.json
  제출 이력       https://data.sec.gov/submissions/CIK{10자리 0패딩}.json

제출 이력의 `filings.recent` 는 **컬럼 지향** 구조입니다. 즉 필드별로 리스트가
하나씩 있고 인덱스가 같은 것끼리 한 건을 이룹니다:

    {"form": ["10-Q","8-K",...], "filingDate": ["2026-10-09",...], ...}

그래서 zip 으로 행 단위로 돌려놓고 씁니다.

한국 종목(005930 등)은 EDGAR 에 없습니다. DART 오픈API 를 써야 하고 그쪽은
무료지만 **키 발급이 필요**합니다. 이 모듈은 한국 종목을 조용히 건너뜁니다.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import requests

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
TIMEOUT = 15

#: 요청 사이 최소 간격(초). SEC 한도는 초당 10건이므로 여유를 둡니다.
MIN_INTERVAL = 0.15

#: 관심 있는 폼과 한국어 설명·중요도.
#: 중요도 2 = 분석을 다시 돌릴 만한 사건, 1 = 참고.
FORM_INFO: dict[str, tuple[str, int]] = {
    "10-K":     ("연간보고서", 2),
    "10-K/A":   ("연간보고서 정정", 2),
    "10-Q":     ("분기보고서", 2),
    "10-Q/A":   ("분기보고서 정정", 2),
    "8-K":      ("수시보고 (주요 사건)", 2),
    "8-K/A":    ("수시보고 정정", 1),
    "DEF 14A":  ("주주총회 소집통지", 1),
    "DEFA14A":  ("주주총회 추가자료", 1),
    "S-1":      ("증권신고서", 2),
    "S-3":      ("증권신고서 (약식)", 1),
    "424B5":    ("발행조건 확정 신고서", 1),
    "SC 13D":   ("5% 이상 지분 취득 (경영참여)", 2),
    "SC 13G":   ("5% 이상 지분 취득 (단순투자)", 1),
    "4":        ("내부자 거래", 1),
    "3":        ("내부자 지분 최초보고", 1),
    "11-K":     ("종업원 지주제 보고", 1),
    "20-F":     ("외국기업 연간보고서", 2),
    "6-K":      ("외국기업 수시보고", 1),
}

#: 기본 수집 대상 (중요도 2 중심 + 지분공시)
DEFAULT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "DEF 14A",
                 "S-1", "SC 13D", "SC 13G", "20-F")

_last_request_at = 0.0


@dataclass
class Filing:
    """제출 한 건."""

    form: str
    filing_date: str          # YYYY-MM-DD (SEC 접수일)
    report_date: str          # YYYY-MM-DD (보고 기준일, 없을 수 있음)
    accession: str
    primary_doc: str
    items: str = ""           # 8-K 항목 번호 (예: "2.02,9.01")
    cik: int = 0

    @property
    def label(self) -> str:
        return FORM_INFO.get(self.form, (self.form, 1))[0]

    @property
    def importance(self) -> int:
        return FORM_INFO.get(self.form, (self.form, 1))[1]

    @property
    def url(self) -> str:
        """공시 문서 직접 링크. 없으면 인덱스 페이지."""
        acc_nodash = self.accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{acc_nodash}"
        if self.primary_doc:
            return f"{base}/{self.primary_doc}"
        return f"{base}/{self.accession}-index.htm"

    @property
    def days_ago(self) -> int | None:
        try:
            filed = dt.date.fromisoformat(self.filing_date)
        except ValueError:
            return None
        return (dt.date.today() - filed).days


class EdgarError(RuntimeError):
    pass


def _headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }


def _throttle() -> None:
    """요청 간격을 벌려 SEC 한도를 지킵니다."""
    global _last_request_at
    gap = time.monotonic() - _last_request_at
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_request_at = time.monotonic()


def _get_json(url: str, user_agent: str) -> object:
    _throttle()
    try:
        resp = requests.get(url, headers=_headers(user_agent), timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status == 403:
            raise EdgarError(
                "SEC 가 403 으로 거부했습니다. User-Agent 에 연락처를 넣어야 합니다 "
                "(config.py 의 EDGAR_USER_AGENT)."
            ) from exc
        if status == 429:
            raise EdgarError("SEC 요청 한도(초당 10건)를 넘었습니다. 잠시 후 다시 시도하십시오.") from exc
        raise EdgarError(f"SEC 요청 실패 (HTTP {status}): {url}") from exc
    except requests.RequestException as exc:
        raise EdgarError(f"SEC 요청 실패: {exc}") from exc
    except ValueError as exc:
        raise EdgarError(f"SEC 응답 파싱 실패: {exc}") from exc


def fetch_ticker_map(user_agent: str) -> dict[str, int]:
    """티커(대문자) -> CIK(int) 매핑.

    company_tickers.json 은 {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    형태입니다. 약 1MB 이므로 호출하는 쪽에서 길게 캐시하십시오.
    """
    data = _get_json(TICKER_MAP_URL, user_agent)
    if not isinstance(data, dict):
        raise EdgarError("company_tickers.json 형식이 예상과 다릅니다.")

    out: dict[str, int] = {}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        cik = entry.get("cik_str")
        if isinstance(ticker, str) and isinstance(cik, int):
            out[ticker.upper()] = cik
    if not out:
        raise EdgarError("company_tickers.json 에서 티커를 찾지 못했습니다.")
    return out


def _rows_from_recent(recent: dict) -> list[dict]:
    """컬럼 지향 구조를 행 단위로 바꿉니다."""
    if not isinstance(recent, dict) or not recent:
        return []
    # 모든 필드의 길이가 같아야 하지만, 방어적으로 가장 짧은 길이를 씁니다
    lists = {k: v for k, v in recent.items() if isinstance(v, list)}
    if not lists:
        return []
    n = min(len(v) for v in lists.values())
    return [{k: v[i] for k, v in lists.items()} for i in range(n)]


def fetch_filings(
    cik: int,
    user_agent: str,
    *,
    forms: tuple[str, ...] = DEFAULT_FORMS,
    limit: int = 12,
    since_days: int = 400,
) -> list[Filing]:
    """한 기업의 최근 공시를 가져옵니다.

    forms 에 해당하고, since_days 안에 접수된 것만, 최신순 limit 건까지.
    """
    data = _get_json(SUBMISSIONS_URL.format(cik=cik), user_agent)
    if not isinstance(data, dict):
        raise EdgarError("submissions 응답 형식이 예상과 다릅니다.")

    recent = (data.get("filings") or {}).get("recent")
    rows = _rows_from_recent(recent if isinstance(recent, dict) else {})

    cutoff = dt.date.today() - dt.timedelta(days=since_days)
    wanted = set(forms)
    out: list[Filing] = []

    for row in rows:
        form = str(row.get("form") or "")
        if wanted and form not in wanted:
            continue
        filing_date = str(row.get("filingDate") or "")
        try:
            if dt.date.fromisoformat(filing_date) < cutoff:
                continue
        except ValueError:
            continue

        out.append(Filing(
            form=form,
            filing_date=filing_date,
            report_date=str(row.get("reportDate") or ""),
            accession=str(row.get("accessionNumber") or ""),
            primary_doc=str(row.get("primaryDocument") or ""),
            items=str(row.get("items") or ""),
            cik=cik,
        ))
        if len(out) >= limit:
            break

    # SEC 는 보통 최신순으로 주지만 보장하지 않으므로 직접 정렬합니다
    out.sort(key=lambda f: f.filing_date, reverse=True)
    return out


def fetch_for_tickers(
    tickers: list[str],
    user_agent: str,
    *,
    cik_overrides: dict[str, int] | None = None,
    forms: tuple[str, ...] = DEFAULT_FORMS,
    limit: int = 12,
) -> tuple[dict[str, list[Filing]], dict[str, str]]:
    """여러 티커의 공시를 한 번에.

    반환: ({티커: [Filing...]}, {티커: 오류메시지})
    오류는 티커별로 격리됩니다 — 하나가 실패해도 나머지는 정상 반환합니다.
    """
    overrides = {k.upper(): v for k, v in (cik_overrides or {}).items()}
    results: dict[str, list[Filing]] = {}
    errors: dict[str, str] = {}

    # CIK 매핑은 한 번만 — override 로 전부 해결되면 아예 받지 않습니다
    need_map = [t for t in tickers if t.upper() not in overrides]
    ticker_map: dict[str, int] = {}
    if need_map:
        try:
            ticker_map = fetch_ticker_map(user_agent)
        except EdgarError as exc:
            for t in need_map:
                errors[t] = str(exc)

    for ticker in tickers:
        up = ticker.upper()
        cik = overrides.get(up) or ticker_map.get(up)
        if cik is None:
            if ticker not in errors:
                errors[ticker] = (
                    f"'{ticker}' 의 CIK 를 찾지 못했습니다. 미국 상장 종목이 아니거나 "
                    f"티커 표기가 다를 수 있습니다. config.py 의 EDGAR_CIK_OVERRIDES 에 "
                    f"직접 넣을 수 있습니다."
                )
            continue
        try:
            results[ticker] = fetch_filings(cik, user_agent, forms=forms, limit=limit)
        except EdgarError as exc:
            errors[ticker] = str(exc)
        except Exception as exc:  # noqa: BLE001
            errors[ticker] = f"조회 중 예외: {exc}"

    return results, errors
