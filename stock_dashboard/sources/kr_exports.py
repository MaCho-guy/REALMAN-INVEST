"""
================================================================================
한국 반도체 수출 — 산업통상부 보도자료에서 읽어옵니다.
================================================================================

왜 이 소스인가 (다른 걸 다 검토한 뒤의 결론):

  관세청 OpenAPI    data.go.kr 인증키 필요. 순별(10일) 단위가 키 없이
                    열려 있는지 확인되지 않았습니다.
  FRED (OECD)       XTEXVA01KRM667S 등. 키는 필요 없지만 **총수출만**
                    이고 2~3개월 지연됩니다. 반도체 구분이 없어
                    메모리 사이클 읽기에는 약합니다.
  한국무역협회 K-stat  품목별(MTI4 메모리반도체)이 있지만 조회에
                    세션이 필요해 보입니다.
  산업통상부 보도자료   **반도체 수출액과 전년동월비를 월초에 발표**합니다.
                    키가 필요 없고 품목이 구분됩니다. 대신 HTML 을
                    긁어야 합니다.

그래서 이걸 씁니다. 다만 솔직하게 적어 둡니다:

  ★ **가져오기(fetch)는 검증되지 않았습니다.** 이 모듈을 만든 환경에서
    motir.go.kr 요청이 막혀 한 번도 실제로 받아보지 못했습니다. 배포한
    앱에서도 같은 벽에 막힐 수 있습니다. 화면 위쪽 진단 패널로 확인한 뒤
    실패하면 쓰지 마십시오.

  ○ **파싱(parse)은 검증했습니다.** 보도자료 실제 문장으로 테스트를
    작성했습니다 (tests/kr_exports_test.py). 형식이 바뀌지 않는 한
    본문에서 숫자를 뽑는 부분은 동작합니다.

────────────────────────────────────────────────────────────────────────────────
본문 형식 (실제 보도자료에서 확인한 것)

  "반도체 수출(603.0억 달러, +262.8)은 메모리 수요 증가세가 지속되며…"
  "반도체 수출(466.5억 달러, +209.0%)은 구글·아마존 등 하이퍼스케일러…"
  "반도체 수출(205.4억 달러, +102.7%)은 AI서버향 높은 수요로…"

**% 기호가 붙을 때와 안 붙을 때가 섞여 있습니다.** 그리고 감소는 마이너스
기호가 아니라 △ 를 씁니다. 둘 다 받습니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

BOARD_URL = "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c"
TIMEOUT = 15

#: 보도자료 제목에 이 말이 들어간 글을 찾습니다. 공백은 무시합니다.
TITLE_HINTS: tuple[str, ...] = ("수출입동향", "수출입 동향")

#: 억 달러 단위 금액과 전년동월비. % 기호는 있을 때와 없을 때가 섞입니다.
#: △ 는 감소를 뜻하는 한국 공문서 관례입니다 (마이너스 기호가 아닙니다).
SEMI_RE = re.compile(
    r"반도체\s*수출\s*\(\s*([\d,]+(?:\.\d+)?)\s*억\s*달러\s*,\s*"
    r"([+\-△▲]?)\s*([\d,]+(?:\.\d+)?)\s*%?\s*\)"
)

#: 금액 없이 증감률만 적는 형태도 있습니다.
#:   "반도체 수출은 263%, 반도체 외 품목 수출은 23% 증가했다"
SEMI_PCT_ONLY_RE = re.compile(
    r"반도체\s*수출은\s*([+\-△▲]?)\s*([\d,]+(?:\.\d+)?)\s*%"
)

#: 제목·본문에서 기준 연월을 찾습니다. "2026년 10월 수출입 동향"
MONTH_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
#: "‘26.9월" 처럼 줄여 쓰는 경우
MONTH_SHORT_RE = re.compile(r"[‘'](\d{2})\s*\.\s*(\d{1,2})\s*월")


class ExportsError(RuntimeError):
    """수출 데이터 수집 실패."""


@dataclass
class SemiExports:
    """한 달치 반도체 수출."""

    year: int = 0
    month: int = 0
    #: 억 달러
    value_100m_usd: float | None = None
    #: 전년 동월비 (%)
    yoy_pct: float | None = None
    source_url: str = ""
    title: str = ""
    #: 어떤 패턴으로 읽었는가 — 진단에 씁니다
    matched: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.yoy_pct is not None or self.value_100m_usd is not None

    @property
    def period(self) -> str:
        if not self.year or not self.month:
            return ""
        return f"{self.year}-{self.month:02d}"

    @property
    def value_usd_bn(self) -> float | None:
        """억 달러 → 10억 달러. 화면에서 'B' 단위로 쓰고 싶을 때."""
        if self.value_100m_usd is None:
            return None
        return self.value_100m_usd / 10.0

    @property
    def age_months(self) -> int | None:
        if not self.year or not self.month:
            return None
        today = dt.date.today()
        return (today.year - self.year) * 12 + (today.month - self.month)


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _signed(sign: str, magnitude: str) -> float | None:
    """부호 기호와 숫자를 합칩니다.

    △ 와 ▲ 는 한국 공문서에서 **감소**를 뜻합니다. 마이너스 기호로 바꾸지
    않고 그대로 두면 증가로 잘못 읽습니다.
    """
    val = _num(magnitude)
    if val is None:
        return None
    return -val if sign in ("-", "△", "▲") else val


def parse_period(text: str) -> tuple[int, int]:
    """본문·제목에서 기준 연월을 찾습니다. 못 찾으면 (0, 0)."""
    m = MONTH_RE.search(text or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = MONTH_SHORT_RE.search(text or "")
    if m:
        # 두 자리 연도 — 2000년대로 봅니다
        return 2000 + int(m.group(1)), int(m.group(2))
    return 0, 0


def parse_semi_exports(text: str, *, title: str = "",
                       url: str = "") -> SemiExports:
    """보도자료 본문에서 반도체 수출액과 전년동월비를 뽑습니다.

    네트워크와 분리해 테스트하려고 공개 함수로 둡니다 — 이 프로젝트의
    다른 파서(fred.parse_csv, edgar_facts.parse_facts)와 같은 방식입니다.
    """
    out = SemiExports(source_url=url, title=title)
    body = text or ""

    year, month = parse_period(title or "")
    if not year:
        year, month = parse_period(body)
    out.year, out.month = year, month
    if not year:
        out.warnings.append("기준 연월을 찾지 못했습니다.")

    m = SEMI_RE.search(body)
    if m:
        out.value_100m_usd = _num(m.group(1))
        out.yoy_pct = _signed(m.group(2), m.group(3))
        out.matched = "금액+증감률"
        return out

    m = SEMI_PCT_ONLY_RE.search(body)
    if m:
        out.yoy_pct = _signed(m.group(1), m.group(2))
        out.matched = "증감률만"
        out.warnings.append("금액은 찾지 못하고 증감률만 읽었습니다.")
        return out

    out.warnings.append(
        "본문에서 '반도체 수출(…억 달러, …%)' 형식을 찾지 못했습니다. "
        "보도자료 서식이 바뀌었을 수 있습니다.")
    return out


def find_article_links(html: str) -> list[tuple[str, str]]:
    """목록 페이지 HTML 에서 (제목, 상대경로) 쌍을 찾습니다.

    제목에 '수출입동향' 이 들어간 것만 돌려줍니다. HTML 구조에 의존하지
    않으려고 **링크 태그를 정규식으로 훑습니다** — 목록 레이아웃이 바뀌어도
    a 태그의 href 와 글자는 남습니다.
    """
    out: list[tuple[str, str]] = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         html or "", re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        label = " ".join(label.split())
        squashed = label.replace(" ", "")
        if any(h.replace(" ", "") in squashed for h in TITLE_HINTS):
            out.append((label, href))
    return out


def fetch_latest(*, session=None) -> SemiExports:
    """목록 → 최신 글 → 본문 파싱. **검증되지 않은 경로입니다.**

    두 번 요청합니다. 목록 페이지에서 '수출입동향' 글을 찾고, 그중 첫
    번째(최신)를 받아 본문을 파싱합니다.
    """
    import requests

    get = (session or requests).get
    headers = {
        # 사이트가 자동 요청을 막을 수 있습니다. 평범한 브라우저 문자열을
        # 씁니다 — 연락처(이메일)는 넣지 않습니다.
        "User-Agent": "Mozilla/5.0 (compatible; stock-dashboard/1.0)",
        "Accept-Language": "ko,en;q=0.8",
    }
    try:
        res = get(BOARD_URL, headers=headers, timeout=TIMEOUT)
        res.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ExportsError(
            f"목록 페이지를 받지 못했습니다: {type(exc).__name__}: {exc}") from exc

    links = find_article_links(res.text)
    if not links:
        raise ExportsError(
            "목록에서 '수출입동향' 글을 찾지 못했습니다. "
            "페이지 구조가 바뀌었거나 차단되었을 수 있습니다.")

    title, href = links[0]
    url = href if href.startswith("http") else (
        "https://www.motir.go.kr" + (href if href.startswith("/") else "/" + href))
    try:
        res2 = get(url, headers=headers, timeout=TIMEOUT)
        res2.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ExportsError(
            f"기사 페이지를 받지 못했습니다: {type(exc).__name__}: {exc}") from exc

    plain = re.sub(r"<[^>]+>", " ", res2.text)
    return parse_semi_exports(plain, title=title, url=url)
