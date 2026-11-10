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

def _from_google_rss(query: str, limit: int) -> list[Headline]:
    url = GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(query))
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

    out: list[Headline] = []
    for block in re.findall(r"<item>(.*?)</item>", body, re.S)[: limit * 2]:
        def grab(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
            return _clean(m.group(1)) if m else ""

        title = grab("title")
        if not title:
            continue
        link = grab("link")
        source = grab("source")

        published = ""
        pub = grab("pubDate")
        if pub:
            # 예: "Tue, 04 Nov 2026 02:13:00 GMT"
            m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pub)
            if m:
                months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
                month = months.get(m.group(2))
                if month:
                    try:
                        published = dt.date(
                            int(m.group(3)), month, int(m.group(1))
                        ).isoformat()
                    except ValueError:
                        published = ""

        out.append(Headline(title=title, url=link, source=source, published=published))
        if len(out) >= limit:
            break

    return out


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
        if source == "naver":
            return _from_google_rss(f"{name} 주가", limit)

        found = _from_yfinance(symbol, limit)
        if found:
            return found
        # yfinance 가 비면 구글 뉴스로 한 번 더
        return _from_google_rss(f"{symbol} stock", limit)
    except Exception:  # noqa: BLE001
        return []


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
