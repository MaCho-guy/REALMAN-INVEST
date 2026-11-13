"""
뉴스 헤드라인 — 보조 용도.

**의도적으로 좁게 만들었습니다.** 장기투자자에게 헤드라인 20개는 노이즈입니다.
이 모듈은 변화 감지에서 신호가 잡힌 종목에 대해서만, 종목당 3건 정도만
가져오도록 설계됐습니다. 호출하는 쪽(signals/app)이 그 판단을 합니다.

소스:
  미국 종목  yfinance 의 Ticker.news (키 불필요)
  한국 종목  구글 뉴스 RSS (키 불필요)

저작권: 제목과 링크만 가져옵니다. 본문은 가져오지도, 저장하지도 않습니다.
사용자는 링크로 원문을 읽습니다.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import urllib.parse
from dataclasses import dataclass

import requests

TIMEOUT = 10
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


@dataclass
class Headline:
    title: str
    url: str
    source: str = ""
    published: str = ""        # YYYY-MM-DD, 알 수 없으면 빈 문자열

    @property
    def days_ago(self) -> int | None:
        if not self.published:
            return None
        try:
            d = dt.date.fromisoformat(self.published[:10])
        except ValueError:
            return None
        return (dt.date.today() - d).days


def _clean(text: object) -> str:
    if not isinstance(text, str):
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


# ──────────────────────────────────────────────────────────────────────────────
# 미국 종목 — yfinance
# ──────────────────────────────────────────────────────────────────────────────

def _from_yfinance(symbol: str, limit: int) -> list[Headline]:
    try:
        import yfinance as yf  # noqa: PLC0415
    except ImportError:
        return []

    try:
        raw = yf.Ticker(symbol).news
    except Exception:  # noqa: BLE001 - yfinance 는 다양한 예외를 던집니다
        return []
    if not isinstance(raw, list):
        return []

    out: list[Headline] = []
    for item in raw[: limit * 3]:
        if not isinstance(item, dict):
            continue
        # yfinance 는 버전에 따라 평평한 구조와 {"content": {...}} 구조를 둘 다 씁니다
        content = item.get("content") if isinstance(item.get("content"), dict) else item

        title = _clean(content.get("title"))
        if not title:
            continue

        url = ""
        for key in ("canonicalUrl", "clickThroughUrl", "link"):
            val = content.get(key)
            if isinstance(val, dict):
                val = val.get("url")
            if isinstance(val, str) and val.startswith("http"):
                url = val
                break

        provider = content.get("provider")
        source = ""
        if isinstance(provider, dict):
            source = _clean(provider.get("displayName"))
        elif isinstance(content.get("publisher"), str):
            source = _clean(content.get("publisher"))

        published = ""
        pub = content.get("pubDate") or content.get("displayTime")
        if isinstance(pub, str) and len(pub) >= 10:
            published = pub[:10]
        elif isinstance(item.get("providerPublishTime"), (int, float)):
            try:
                published = dt.datetime.fromtimestamp(
                    item["providerPublishTime"], dt.timezone.utc
                ).date().isoformat()
            except (OSError, ValueError, OverflowError):
                published = ""

        out.append(Headline(title=title, url=url, source=source, published=published))
        if len(out) >= limit:
            break

    return out


# ──────────────────────────────────────────────────────────────────────────────
# 한국 종목 — 구글 뉴스 RSS
# ──────────────────────────────────────────────────────────────────────────────

#: 구글 뉴스에서 받을 기사의 최대 나이(일). 2026-11-13 사용자: "섹터별 뉴스에
#: 엄청 오래된 것들이 뜬다". 원인 — RSS 검색 결과는 **관련도 순**인데 위에서부터
#: 몇 건만 잘라 썼습니다. 그래서 몇 달 된 기사가 맨 위에 오면 그대로 나왔습니다.
#: 이제는 검색어에 기간을 걸고(when:Nd), 받은 기사 **전부**를 날짜순으로 줄 세운 뒤
#: 기간 밖 기사는 버립니다. 부르는 쪽이 성격에 맞게 정합니다 (마감 기사는 2일).
NEWS_MAX_DAYS = 14
_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _pub_time(pub: str) -> dt.datetime | None:
    """'Tue, 04 Nov 2026 02:13:00 GMT' → UTC datetime (모르면 None)."""
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", pub or "")
    if not m or m.group(2) not in _MONTHS:
        return None
    try:
        return dt.datetime(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)),
                           int(m.group(4) or 0), int(m.group(5) or 0),
                           tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def parse_google_rss(body: str, limit: int, max_days: int | None = NEWS_MAX_DAYS,
                     now: dt.datetime | None = None) -> list[Headline]:
    """RSS 글 → 최근 기사부터 limit 건. max_days 보다 오래된 기사와 날짜 모르는
    기사는 버립니다 (max_days=None 이면 나이로 거르지 않음 — 그래도 날짜순)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    got: list[tuple[dt.datetime | None, Headline]] = []
    seen: set[str] = set()
    for block in re.findall(r"<item>(.*?)</item>", body or "", re.S):
        def grab(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _clean(m.group(1)) if m else ""

        title = grab("title")
        if not title or title in seen:
            continue
        when = _pub_time(grab("pubDate"))
        if max_days is not None and (when is None or now - when > dt.timedelta(days=max_days)):
            continue
        seen.add(title)
        got.append((when, Headline(title=title, url=grab("link"), source=grab("source"),
                                   published=when.date().isoformat() if when else "")))
    got.sort(key=lambda x: x[0] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
             reverse=True)
    return [h for _w, h in got[:limit]]


def _from_google_rss(query: str, limit: int, max_days: int | None = NEWS_MAX_DAYS
                     ) -> list[Headline]:
    q = f"{query} when:{max_days}d" if max_days else query
    url = GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(q))
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "stock-dashboard/1.0 (personal dashboard)"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.text
    except requests.RequestException:
        return []
    return parse_google_rss(body, limit, max_days)


# ──────────────────────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────────────────────

def fetch_headlines(
    name: str,
    symbol: str,
    source: str,
    *,
    limit: int = 3,
) -> list[Headline]:
    """한 종목의 헤드라인을 가져옵니다.

    source  "yahoo" 면 yfinance, "naver"(한국 종목)면 구글 뉴스 RSS.
    실패하면 빈 리스트 — 뉴스는 보조이므로 없어도 화면이 깨지지 않습니다.
    """
    try:
        # 2026-11-11: 미국 종목도 **한국어 헤드라인**을 먼저 찾습니다.
        # 전에는 yfinance 를 먼저 써서 요약 화면의 제목이 전부 영어로
        # 나왔습니다. 구글 뉴스 RSS 는 hl=ko&gl=KR 로 호출하므로 같은
        # 기업이라도 한국 매체 기사가 돌아옵니다. 한국어 기사가 없을
        # 때만 yfinance(영어)로 내려갑니다 — 비는 것보다는 낫습니다.
        ko = _from_google_rss(_ko_query(name, symbol), limit)
        if ko or source == "naver":
            return ko
        return _from_yfinance(symbol, limit)
    except Exception:  # noqa: BLE001
        return []


def _ko_query(name: str, symbol: str) -> str:
    """구글 뉴스 한국어 검색어.

    한국 매체는 'Microsoft' 가 아니라 '마이크로소프트' 라고 씁니다. 아는
    종목은 한국어 이름으로 찾고, 모르는 종목은 영문 이름을 그대로 씁니다 —
    없는 이름을 지어내면 엉뚱한 기사가 붙습니다.
    """
    try:
        import config  # noqa: PLC0415 - 순환 참조를 피해 지연 임포트
        known = config.NEWS_NAME_KO.get(symbol, "")
    except Exception:  # noqa: BLE001
        known = ""
    base = (known or name or symbol).strip()
    if len(base) < 3 and base.lower() != symbol.lower():
        base = f"{base} {symbol}".strip()
    elif len(base) < 3:
        base = symbol
    return f"{base} 주가"


def fetch_for_many(
    targets: list[tuple[str, str, str]],
    *,
    limit: int = 3,
) -> dict[str, list[Headline]]:
    """targets = [(키, 표시이름, 심볼, 소스)] 형태가 아니라 (키, 이름, 소스) 로 받고
    심볼은 키와 같다고 봅니다. 신호가 잡힌 소수 종목에만 호출하십시오.
    """
    out: dict[str, list[Headline]] = {}
    for key, name, source in targets:
        items = fetch_headlines(name, key, source, limit=limit)
        if items:
            out[key] = items
    return out


def fetch_sector_news(sectors, *, limit: int = 3, max_days: int = 7
                      ) -> tuple[dict[str, list[Headline]], dict[str, str]]:
    """섹터별 헤드라인. sectors = [(키, 표시이름, 검색어), …].

    섹터는 9개 안팎이고 RSS 는 가벼워서 순차로 받습니다. 하나가 실패해도
    나머지는 보여줘야 하므로 오류를 따로 모읍니다 — 조용히 비우면
    '오늘 뉴스가 없네' 로 오해합니다.
    """
    out: dict[str, list[Headline]] = {}
    errors: dict[str, str] = {}
    for key, _label, query in sectors:
        try:
            items = _from_google_rss(query, limit, max_days)
        except Exception as exc:  # noqa: BLE001
            errors[key] = f"{type(exc).__name__}: {exc}"
            continue
        if items:
            out[key] = items
        else:
            errors[key] = f"최근 {max_days}일 기사가 없습니다."
    return out, errors
