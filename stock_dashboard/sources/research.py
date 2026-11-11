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


# ── 새 페이지 (Next.js) ─────────────────────────────────────────────────────
#
# 2026-11-11 진단: 목록 페이지가 표(<tr>)가 아닌 Next.js 앱으로 바뀌었습니다
# (HTTP 200, 13만 바이트, <tr> 0개). 이런 페이지는 데이터를 HTML 안의
# 스크립트에 JSON 으로 싣습니다 — __NEXT_DATA__ 이거나, 앱 라우터라면
# self.__next_f.push([1,"…"]) 조각들입니다. 필드 이름을 아직 모르므로
# '제목처럼 생긴 키 + (날짜나 증권사나 PDF)' 를 가진 객체를 찾아 읽습니다.
# 진단 패널이 첫 객체의 키를 찍어 주므로, 그걸 보고 정확히 맞춥니다.

_NEXT_DATA = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I)
_NEXT_F = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:\\.|[^"\\])*)"\]\)', re.S)


def next_text(page: str) -> str:
    """페이지에 실린 JSON 조각을 한 문자열로 (없으면 빈 문자열)."""
    import json  # noqa: PLC0415
    m = _NEXT_DATA.search(page or "")
    parts = [m.group(1)] if m else []
    for chunk in _NEXT_F.findall(page or ""):
        try:
            parts.append(json.loads(f'"{chunk}"'))
        except ValueError:
            continue
    return "\n".join(parts)


def _objects(text: str, limit: int = 4000):
    """text 안의 JSON 객체({…})를 하나씩 — 괄호 짝을 맞춰 잘라 json 으로."""
    import json  # noqa: PLC0415
    n = len(text)
    i = 0
    found = 0
    while i < n and found < limit:
        start = text.find("{", i)
        if start < 0:
            break
        depth, j, in_str, esc = 0, start, False, False
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        try:
            obj = json.loads(text[start:j + 1])
            found += 1
            yield obj
            i = j + 1
        except ValueError:
            i = start + 1


def _walk_dicts(node, depth: int = 0):
    if depth > 12:
        return
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_dicts(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_dicts(v, depth + 1)


def _pick(d: dict, *needles: str, avoid: tuple[str, ...] = ()) -> str:
    for k, v in d.items():
        low = str(k).lower()
        if any(a in low for a in avoid):
            continue
        if any(n in low for n in needles) and isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return ""


_ISO_ANY = re.compile(r"(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _iso_any(text: str) -> str:
    m = _ISO_ANY.search(text or "")
    if not m:
        digits = re.sub(r"\D", "", text or "")
        if len(digits) >= 8 and digits[:2] in ("19", "20"):
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
        return ""
    y, mo, d = m.groups()
    y = f"20{y}" if len(y) == 2 else y
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _pick_date(d: dict) -> str:
    """키 이름에 date·dt·time·At 이 든 값 중 **날짜로 읽히는** 첫 값.
    ('category' 에도 'at' 이 들어 있어 이름만으로 고르면 틀립니다.)"""
    for k, v in d.items():
        low = str(k).lower()
        if any(n in low for n in ("date", "dt", "time")) or str(k).endswith("At"):
            iso = _iso_any(str(v))
            if iso:
                return iso
    return ""


def report_like(d: dict) -> bool:
    title = _pick(d, "title", "subject")
    if not title or len(title) < 4:
        return False
    extra = (_pick_date(d)
             or _pick(d, "broker", "office", "securit", "provider", "firm")
             or any(isinstance(v, str) and ".pdf" in v.lower() for v in d.values()))
    return bool(extra)


def parse_next(page: str, kind: str) -> list[Report]:
    text = next_text(page)
    if not text:
        return []
    out: list[Report] = []
    seen: set[str] = set()
    for obj in _objects(text):
        for d in _walk_dicts(obj):
            if not report_like(d):
                continue
            title = _html.unescape(_pick(d, "title", "subject"))
            date = _pick_date(d)
            pdf = next((str(v) for v in d.values()
                        if isinstance(v, str) and ".pdf" in v.lower()), "")
            url = _pick(d, "url", "link", "href", avoid=("pdf", "image", "img", "thumb"))
            key = title + date
            if key in seen:
                continue
            seen.add(key)
            out.append(Report(
                kind=kind, title=title,
                broker=_pick(d, "broker", "office", "securit", "provider", "firm"),
                category=(_pick(d, "category", "industry", "upjong", "sector")
                          if kind == "industry" else ""),
                date=date, url=_abs(url) if url else "",
                pdf=_abs(pdf) if pdf else ""))
    return out


# ── 새 페이지의 데이터 주소 찾기 ────────────────────────────────────────────
#
# 2026-11-12 진단: 페이지 안에 리포트가 **없습니다** (__next_f 조각 40개에
# 제목·메타뿐). 목록은 브라우저가 열린 뒤 따로 받아 옵니다. 그 주소는
# 자바스크립트 묶음 안에 글자로 들어 있으므로, 페이지가 싣는 묶음을 받아
# 'research' 가 든 주소 모양의 글자를 찾습니다. 진단 패널이 이 결과를
# 찍어 주고, 주소가 확인되면 여기 API_CANDIDATES 에 고정합니다.

_SCRIPT_SRC = re.compile(r'(?:src|href)="(https?://[^"]+?/_next/static/chunks/[^"]+?\.js)"')
_F_CHUNK = re.compile(r'static/chunks/[A-Za-z0-9_./\-\[\]]+?\.js')
_STR_LIT = re.compile(r'["\'`]([^"\'`\n]{4,220})["\'`]')

#: 추측한 주소 — **확인되지 않았습니다.** {kind} 는 industry / market(또는 daily),
#: {page} 는 쪽 번호. 진단이 하나씩 불러 보고 어느 것이 살아 있는지 알려줍니다.
API_CANDIDATES: tuple[str, ...] = (
    "https://m.stock.naver.com/front-api/research/list?category={kind}&pageSize=30&page={page}",
    "https://m.stock.naver.com/api/research/{kind}?pageSize=30&page={page}",
    "https://stock.naver.com/api/research/{kind}?pageSize=30&page={page}",
    "https://stock.naver.com/api/domestic/research/{kind}?pageSize=30&page={page}",
    "https://finance.naver.com/research/api/{kind}?pageSize=30&page={page}",
)
#: 우리 이름 → 주소에 넣어 볼 이름들
KIND_ALIASES = {"industry": ("industry",), "market": ("market", "daily", "invest")}

#: 살아 있는 주소를 찾으면 기억합니다 (kind → 주소 틀). 못 찾았으면 "".
_api_memo: dict[str, str] = {}


def script_urls(page: str) -> list[str]:
    """페이지가 싣는 자바스크립트 묶음 주소들."""
    urls = list(dict.fromkeys(_SCRIPT_SRC.findall(page or "")))
    base = ""
    if urls:
        base = urls[0].split("/_next/")[0] + "/_next/"
    for rel in dict.fromkeys(_F_CHUNK.findall(next_text(page) + (page or ""))):
        full = base + rel if base else ""
        if full and full not in urls:
            urls.append(full)
    return urls


def api_strings(js: str) -> list[str]:
    """묶음 안에서 리서치 데이터 주소처럼 생긴 글자들."""
    out = []
    for lit in _STR_LIT.findall(js or ""):
        low = lit.lower()
        if "research" not in low or "/" not in lit:
            continue
        if low.endswith((".js", ".css", ".png", ".svg")) or "static/chunks" in low:
            continue
        out.append(lit)
    return list(dict.fromkeys(out))


def discover(page: str, get=None, limit: int = 80) -> list[tuple[str, str]]:
    """[(주소처럼 생긴 글자, 그 글자가 나온 묶음 파일 이름)]."""
    get = get or (lambda u: requests.get(u, headers=HEADERS, timeout=TIMEOUT).text)
    urls = script_urls(page)[:limit]
    found: list[tuple[str, str]] = []
    if not urls:
        return found

    def one(url: str):
        try:
            return url, api_strings(get(url))
        except Exception:  # noqa: BLE001
            return url, []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, lits in pool.map(one, urls):
            for lit in lits:
                found.append((lit, url.rsplit("/", 1)[-1]))
    return found


def reports_from_json(payload, kind: str) -> list[Report]:
    """JSON 어디에 있든 리포트처럼 생긴 객체를 읽습니다 (parse_next 와 같은 규칙)."""
    out: list[Report] = []
    seen: set[str] = set()
    for d in _walk_dicts(payload):
        if not report_like(d):
            continue
        title = _html.unescape(_pick(d, "title", "subject"))
        date = _pick_date(d)
        pdf = next((str(v) for v in d.values()
                    if isinstance(v, str) and ".pdf" in v.lower()), "")
        url = _pick(d, "url", "link", "href", avoid=("pdf", "image", "img", "thumb"))
        if ".pdf" in url.lower():
            url = ""
        cat = ""
        for needle in ("upjong", "industry", "sector", "category"):
            cat = _pick(d, needle)
            # 'industry' · 'market' 같은 값은 업종이 아니라 목록 종류 이름
            if cat and cat.lower() not in ("industry", "market", "daily",
                                           "invest", "company"):
                break
            cat = ""
        if title + date in seen:
            continue
        seen.add(title + date)
        out.append(Report(
            kind=kind, title=title,
            broker=_pick(d, "broker", "office", "securit", "provider", "firm"),
            category=cat if kind == "industry" else "", date=date,
            url=_abs(url) if url else "", pdf=_abs(pdf) if pdf else ""))
    return out


def fetch_api(kind: str, page: int = 1, get=None) -> tuple[list[Report], str]:
    """추측한 주소들을 차례로 불러 봅니다. (리포트, 쓴 주소 틀)"""
    def default_get(url: str):
        r = requests.get(url, headers={**HEADERS, "Accept": "application/json"},
                         timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    get = get or default_get
    memo = _api_memo.get(kind)
    if memo == "":
        return [], ""
    templates = [memo] if memo else [
        t.replace("{kind}", alias) for alias in KIND_ALIASES.get(kind, (kind,))
        for t in API_CANDIDATES]
    for tpl in templates:
        try:
            items = reports_from_json(get(tpl.replace("{page}", str(page))), kind)
        except Exception:  # noqa: BLE001
            continue
        if len(items) >= 3:
            _api_memo[kind] = tpl
            return items, tpl
    if not memo:
        _api_memo[kind] = ""             # 이번 실행 동안은 다시 두드리지 않음
    return [], ""


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
        items = parse_list(resp.text, kind) or parse_next(resp.text, kind)
        if not items:
            # 페이지에 목록이 없으면(새 페이지) 데이터 주소를 직접 불러 봅니다
            items = fetch_api(kind, page)[0]
    except requests.RequestException as exc:
        return [], f"요청 실패: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001
        return [], f"해석 실패: {type(exc).__name__}"
    if not items:
        return [], ("네이버 리서치가 새 페이지로 바뀌어 목록을 아직 못 읽습니다 "
                    "— 설정 → 진단 → '리서치 목록 확인' 결과가 필요합니다")
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
