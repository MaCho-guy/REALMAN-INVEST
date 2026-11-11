"""증권사 리포트 목록 — 네이버 증권 리서치 (산업분석 · 시황정보).

2026-11-11 요청: "한경컨센서스에서 보고서 긁어올 수 있잖아. 산업분석
요약 같은 것 정리해서 볼 수 있게 (꼭 거기가 아니어도 됨)".

**왜 한경컨센서스가 아닌가.** 한경컨센서스는 리포트 파일을 열려면
로그인이 필요합니다. 서버에 계정 비밀번호를 넣어야 하는데, 그건 이
대시보드가 감당할 위험이 아닙니다. 네이버 증권 리서치는 로그인 없이
목록과 PDF 를 열 수 있고, 산업분석 목록에 **업종 분류**가 붙어 있어
'업종별로 정리' 하기에 더 맞습니다.

**무엇을 가져오고 무엇을 안 가져오나.**
  가져옴: 업종 · 제목 · 증권사 · 날짜 · 원문(PDF)·상세 페이지 링크
  안 가져옴: 리포트 본문과 요약문. 본문은 증권사의 저작물이라 이
  화면에 옮겨 싣지 않고, 원문 링크로 보냅니다. 요약이 필요하면 화면의
  'Claude 에 요약 요청' 링크가 제목·PDF 주소를 채운 채로 Claude 를 엽니다.

엔드포인트 (공식 문서 없음 — 형식이 바뀌면 빈 목록과 이유를 돌려줍니다):
  https://finance.naver.com/research/industry_list.naver?page=N     산업분석
  https://finance.naver.com/research/market_info_list.naver?page=N  시황정보

**이 파서는 실제 응답으로 검증하지 못했습니다** (작업 환경에서 접속
불가). 그래서 열 위치를 고정하지 않고, 줄마다 '상세 링크 · PDF 링크 ·
날짜 모양' 을 찾아 읽습니다. 진단 패널의 '리서치 목록 확인' 으로 실제
응답을 한 번 확인해야 합니다.
"""
from __future__ import annotations

import html as _html
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

BASE = "https://finance.naver.com/research/"
LISTS = {
    "industry": "industry_list.naver",       # 산업분석
    "market": "market_info_list.naver",      # 시황정보
}
TIMEOUT = 8
HEADERS = {
    "User-Agent": "stock-dashboard/1.0 (personal dashboard)",
    "Referer": "https://finance.naver.com/research/",
}


@dataclass
class Report:
    kind: str                 # industry | market
    title: str
    broker: str = ""
    category: str = ""        # 업종 (산업분석만)
    date: str = ""            # YYYY-MM-DD
    url: str = ""             # 상세 페이지
    pdf: str = ""             # 원문 PDF

    @property
    def link(self) -> str:
        return self.pdf or self.url


_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_A = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_DATE = re.compile(r"^(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$")


def _text(fragment: str) -> str:
    return " ".join(_html.unescape(_TAG.sub(" ", fragment)).split())


def _iso(text: str) -> str:
    m = _DATE.match(text.strip())
    if not m:
        return ""
    y, mo, d = m.groups()
    y = f"20{y}" if len(y) == 2 else y
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _abs(href: str) -> str:
    href = _html.unescape(href.strip())
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://finance.naver.com" + href
    return BASE + href


def parse_list(page: str, kind: str) -> list[Report]:
    """목록 페이지 HTML → 리포트 목록.

    한 줄(<tr>)에서:
      제목  = '…_read.naver' 로 가는 링크의 글자
      PDF   = '.pdf' 로 끝나는 링크
      날짜  = 날짜 모양(25.11.10)의 칸
      업종  = 제목 칸보다 **앞에** 있는 글자 칸 (산업분석만)
      증권사 = 제목 칸 **바로 뒤**의 글자 칸
    제목 링크가 없는 줄(머리줄·구분선)은 건너뜁니다.
    """
    out: list[Report] = []
    for row in _TR.findall(page or ""):
        cells = _TD.findall(row)
        if len(cells) < 3:
            continue
        title, url, pdf, date, t_idx = "", "", "", "", -1
        for i, cell in enumerate(cells):
            for href, inner in _A.findall(cell):
                if "_read.naver" in href and not title:
                    title, url, t_idx = _text(inner), _abs(href), i
                elif href.lower().split("?")[0].endswith(".pdf") and not pdf:
                    pdf = _abs(href)
            iso = _iso(_text(cell))
            if iso and not date:
                date = iso
        if not title or t_idx < 0:
            continue
        category = ""
        if kind == "industry":
            for cell in cells[:t_idx]:
                txt = _text(cell)
                if txt:
                    category = txt
        broker = _text(cells[t_idx + 1]) if t_idx + 1 < len(cells) else ""
        if _iso(broker):        # 열이 밀려 날짜가 잡혔으면 비웁니다
            broker = ""
        out.append(Report(kind=kind, title=title, broker=broker,
                          category=category, date=date, url=url, pdf=pdf))
    return out


def fetch_page(kind: str, page: int = 1) -> tuple[list[Report], str]:
    try:
        resp = requests.get(BASE + LISTS[kind], params={"page": page},
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        # 이 페이지는 EUC-KR 입니다. 헤더에 없으면 requests 가 ISO-8859-1 로
        # 읽어 한글이 깨지므로 직접 정합니다.
        enc = (resp.encoding or "").lower()
        if enc in ("", "iso-8859-1"):
            resp.encoding = resp.apparent_encoding or "euc-kr"
        items = parse_list(resp.text, kind)
    except requests.RequestException as exc:
        return [], f"요청 실패: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001
        return [], f"해석 실패: {type(exc).__name__}"
    if not items:
        return [], "목록이 비었습니다 (페이지 형식이 바뀌었을 수 있음)"
    return items, ""


def fetch(kind: str, pages: int = 3) -> tuple[list[Report], str]:
    """여러 쪽을 동시에. (리포트 목록 — 최신순·중복 제거, 오류)."""
    nums = list(range(1, max(1, pages) + 1))
    with ThreadPoolExecutor(max_workers=min(4, len(nums))) as pool:
        results = list(pool.map(lambda n: fetch_page(kind, n), nums))
    seen: set[str] = set()
    out: list[Report] = []
    errs = []
    for items, err in results:
        if err:
            errs.append(err)
        for r in items:
            key = r.url or (r.title + r.date)
            if key not in seen:
                seen.add(key)
                out.append(r)
    out.sort(key=lambda r: r.date, reverse=True)
    return out, ("" if out else (errs[0] if errs else "목록이 비었습니다"))


# ── 정리 ─────────────────────────────────────────────────────────────────────

def by_category(reports: list[Report]) -> list[tuple[str, list[Report]]]:
    """업종별 묶음 — 보고서 많은 업종부터. 업종이 비면 '기타'."""
    groups: dict[str, list[Report]] = {}
    for r in reports:
        groups.setdefault(r.category or "기타", []).append(r)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def date_range(reports: list[Report]) -> tuple[str, str]:
    dates = sorted(r.date for r in reports if r.date)
    return (dates[0], dates[-1]) if dates else ("", "")


def summary_prompt(category: str, reports: list[Report], limit: int = 8) -> str:
    """Claude 에 붙여넣을 요약 요청 — 제목과 원문 주소만 담습니다."""
    lines = [f"아래는 최근 증권사 '{category}' 산업분석 리포트 목록이야. "
             "각 PDF 를 열어 읽고 정리해 줘.",
             "1) 리포트별 핵심 주장 2~3줄 (출처: 증권사·날짜·쪽수)",
             "2) 증권사들이 공통으로 말하는 것과 엇갈리는 것",
             "3) 주장의 근거가 된 숫자와, 근거 없이 전망만 있는 부분 구분",
             "매수·매도 추천이나 목표주가는 옮기지 말고, 열지 못한 PDF 는 "
             "열지 못했다고 적어 줘.", ""]
    for r in reports[:limit]:
        lines.append(f"- {r.date} {r.broker} 「{r.title}」 {r.link}")
    return "\n".join(lines)
