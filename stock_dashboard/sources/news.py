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

import dataclasses
import datetime as dt
import html
import math
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
    #: 같은 사건(또는 아주 가까운 소식)으로 묶인 **다른** 매체 수. 섹터 뉴스
    #: 순위(rank_stories)에서만 채웁니다. 0 이면 표시하지 않습니다.
    more: int = 0

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


_MIN_UTC = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _strip_source(title: str, source: str) -> str:
    """구글 뉴스 제목 끝의 ' - 매체' 를 뗍니다. 매체는 옆에 따로 보이므로
    두 번 나오면 한 줄이 길어지기만 합니다 (2026-11-13 섹터 뉴스 점검)."""
    if source and title.endswith(f" - {source}") and len(title) > len(source) + 3:
        return title[: -(len(source) + 3)].rstrip()
    return title


def _parse_items(body: str, max_days: int | None, now: dt.datetime
                 ) -> list[tuple[dt.datetime | None, Headline]]:
    """RSS 글 → [(발행 시각, Headline)] 최근 것부터. 기간 밖 · 날짜 모름 · 같은 제목은 버림."""
    got: list[tuple[dt.datetime | None, Headline]] = []
    seen: set[str] = set()
    for block in re.findall(r"<item>(.*?)</item>", body or "", re.S):
        def grab(tag: str) -> str:
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _clean(m.group(1)) if m else ""

        source = grab("source")
        title = _strip_source(grab("title"), source)
        if not title or title in seen:
            continue
        when = _pub_time(grab("pubDate"))
        if max_days is not None and (when is None or now - when > dt.timedelta(days=max_days)):
            continue
        seen.add(title)
        got.append((when, Headline(title=title, url=grab("link"), source=source,
                                   published=when.date().isoformat() if when else "")))
    got.sort(key=lambda x: x[0] or _MIN_UTC, reverse=True)
    return got


def parse_google_rss(body: str, limit: int, max_days: int | None = NEWS_MAX_DAYS,
                     now: dt.datetime | None = None) -> list[Headline]:
    """RSS 글 → 최근 기사부터 limit 건. max_days 보다 오래된 기사와 날짜 모르는
    기사는 버립니다 (max_days=None 이면 나이로 거르지 않음 — 그래도 날짜순)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return [h for _w, h in _parse_items(body, max_days, now)[:limit]]


def _rss_body(query: str, max_days: int | None) -> str | None:
    """구글 뉴스 RSS 원문. 받지 못하면 None (빈 결과와 구분하려고)."""
    q = f"{query} when:{max_days}d" if max_days else query
    url = GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(q))
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "stock-dashboard/1.0 (personal dashboard)"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def _from_google_rss(query: str, limit: int, max_days: int | None = NEWS_MAX_DAYS
                     ) -> list[Headline]:
    body = _rss_body(query, max_days)
    if body is None:
        return []
    return parse_google_rss(body, limit, max_days)


# ──────────────────────────────────────────────────────────────────────────────
# 섹터 뉴스 순위 — 같은 사건 묶기 + 매체 + 보도 수 + 나이
# ──────────────────────────────────────────────────────────────────────────────
#
# 2026-11-13 사용자: "섹터별 뉴스 좀 더 읽을만한 정보로". 그날 12시 구글 뉴스
# 실제 응답으로 본 문제 — 최신순 3건만 자르니 환율 칸은 장중 시세 속보 3개,
# 바이오 칸은 같은 기술수출 기사 6개 중 3개, 반도체 칸에 국고채 기사가 섞였습니다.
#
# 그래서 받은 기사 **전부**를 사건별로 묶고, 묶음마다 점수를 매깁니다:
#   보도 매체 수  log2(1+매체 수), 상한 3 (= 7곳). 보도자료가 널리 퍼진 것을
#                 과하게 올리지 않으려고 상한을 둡니다.
#   주요 매체     대표 기사가 주요 매체면 +0.8
#   나이          하루에 −0.25
#   섹터 낱말     대표 제목에 섹터 낱말이 하나도 없으면 −2 (본문에만 걸린 기사)
#   피할 낱말     대표 제목에 있으면 −2 (예: 정책 칸의 대만·홍콩 증시)
# 값은 그날 9개 섹터 실제 응답으로 맞췄습니다. 기사를 버리지는 않습니다 —
# 감점일 뿐이라 섹터 낱말 기사가 없으면 그다음 기사가 나옵니다.

_SIM_JACCARD = 0.35     # 글자 두 개씩 잘라 겹친 비율
_SIM_OVERLAP = 0.6      # 짧은 쪽 기준 겹친 비율 (짧은 속보 제목용)
_SCORE_OUTLET_CAP = 3.0
_SCORE_TIER = 0.8
_SCORE_PER_DAY = 0.25
_SCORE_OFF = 2.0


def _norm_title(t: str) -> str:
    """[속보] · (종합) 같은 꼬리표를 지웁니다."""
    return re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t or "")


def _bigrams(t: str) -> set[str]:
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", _norm_title(t))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _words(t: str) -> list[str]:
    return [w for w in re.split(r"[^가-힣A-Za-z0-9.]+", _norm_title(t)) if len(w) >= 2]


def _numbers(t: str) -> set[str]:
    """제목 속 '구별되는' 숫자 — 1330.7 · 2498 처럼. 연도(20xx)는 뺍니다."""
    s = re.sub(r"(\d),(\d)", r"\1\2", _norm_title(t))
    return {n for n in re.findall(r"\d+\.\d+|\d{3,}", s) if not re.fullmatch(r"20\d\d", n)}


@dataclass
class _Sig:
    bi: set
    words: list
    nums: set


def _sig(title: str) -> _Sig:
    return _Sig(_bigrams(title), _words(title), _numbers(title))


def same_story(a: _Sig, b: _Sig) -> bool:
    """두 제목이 같은 사건인가. 표현만 다른 경우를 잡으려고 네 갈래로 봅니다."""
    n = len(a.bi & b.bi)
    if a.bi and b.bi:
        if n / (len(a.bi) + len(b.bi) - n) >= _SIM_JACCARD:
            return True
        if n / min(len(a.bi), len(b.bi)) >= _SIM_OVERLAP:
            return True
    shared = [w for w in a.words if w in b.words]
    if a.words and b.words and a.words[0] == b.words[0] and len(shared) >= 3:
        return True                      # 같은 주어(회사) + 낱말 셋
    if (a.nums & b.nums) and len(shared) >= 2:
        return True                      # 같은 숫자(1330.7원) + 낱말 둘
    return len(shared) >= 4


def _is_tier(source: str, tier) -> bool:
    return bool(source) and any(t in source for t in tier)


def rank_stories(items: list[tuple[dt.datetime | None, Headline]], limit: int, *,
                 must=(), avoid=(), tier=(), now: dt.datetime | None = None
                 ) -> list[Headline]:
    """[(시각, Headline)] → 사건별로 묶어 점수 높은 순 limit 건.

    돌려주는 Headline 은 묶음의 대표(주요 매체 우선, 그다음 최신)이고
    more = 묶음 안 다른 매체 수입니다. 원래 객체는 바꾸지 않습니다.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = sorted(items, key=lambda x: x[0] or _MIN_UTC, reverse=True)
    clusters: list[list[tuple[dt.datetime | None, Headline, _Sig]]] = []
    for when, h in rows:
        sig = _sig(h.title)
        # 묶음의 앞 3건과만 비교 — 끝없이 이어 붙어 다른 사건까지 삼키는 것을 막습니다
        home = next((c for c in clusters if any(same_story(x[2], sig) for x in c[:3])), None)
        if home is None:
            clusters.append([(when, h, sig)])
        else:
            home.append((when, h, sig))

    scored = []
    for c in clusters:
        outlets = {h.source or h.title for _w, h, _s in c}
        latest = max((w for w, _h, _s in c if w), default=None)
        age = (now - latest).total_seconds() / 86400 if latest else 7.0
        rep_w, rep, _ = sorted(c, key=lambda x: (_is_tier(x[1].source, tier), x[0] or _MIN_UTC),
                               reverse=True)[0]
        score = min(math.log2(1 + len(outlets)), _SCORE_OUTLET_CAP) - max(age, 0) * _SCORE_PER_DAY
        if _is_tier(rep.source, tier):
            score += _SCORE_TIER
        if must and not any(w in rep.title for w in must):
            score -= _SCORE_OFF
        if avoid and any(w in rep.title for w in avoid):
            score -= _SCORE_OFF
        scored.append((score, rep_w or _MIN_UTC, dataclasses.replace(rep, more=len(outlets) - 1)))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [h for _s, _w, h in scored[:limit]]


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


def fetch_sector_news(sectors, *, limit: int = 3, max_days: int = 7, rank: bool = False,
                      must: dict | None = None, avoid: dict | None = None, tier=()
                      ) -> tuple[dict[str, list[Headline]], dict[str, str]]:
    """섹터별 헤드라인. sectors = [(키, 표시이름, 검색어), …].

    섹터는 9개 안팎이고 RSS 는 가벼워서 순차로 받습니다. 하나가 실패해도
    나머지는 보여줘야 하므로 오류를 따로 모읍니다 — 조용히 비우면
    '오늘 뉴스가 없네' 로 오해합니다.

    rank=True 면 받은 기사 전부를 rank_stories 로 사건별 순위를 매깁니다
    (must · avoid = {키: 낱말들}, tier = 주요 매체 이름들). False 면 예전처럼
    최신순 — 장 마감 기사(load_close_headlines)는 이쪽을 씁니다.
    """
    out: dict[str, list[Headline]] = {}
    errors: dict[str, str] = {}
    now = dt.datetime.now(dt.timezone.utc)
    for key, _label, query in sectors:
        try:
            if rank:
                body = _rss_body(query, max_days)
                if body is None:
                    errors[key] = "구글 뉴스 응답을 받지 못했습니다."
                    continue
                items = rank_stories(_parse_items(body, max_days, now), limit,
                                     must=(must or {}).get(key, ()),
                                     avoid=(avoid or {}).get(key, ()), tier=tier, now=now)
            else:
                items = _from_google_rss(query, limit, max_days)
        except Exception as exc:  # noqa: BLE001
            errors[key] = f"{type(exc).__name__}: {exc}"
            continue
        if items:
            out[key] = items
        else:
            errors[key] = f"최근 {max_days}일 기사가 없습니다."
    return out, errors
