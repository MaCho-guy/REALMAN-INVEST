"""
네이버 증권 — 종목별 투자자 수급 · 분기 실적(컨센서스 포함).

**두 경로 모두 실제 응답으로 검증하지 못했습니다.** (2026-11-11)
이 작업 환경에서는 네이버에 닿지 않습니다. 그래서:

  수급   1) m.stock 모바일 JSON  /api/stock/{code}/trend
         2) 실패하면 PC 페이지   finance.naver.com/item/frgn.naver (HTML 표)
         JSON 쪽은 필드 이름을 **추측**하지 않으려고 '이름에 foreigner 와
         purebuy 가 들어간 칸' 처럼 부분 일치로 찾습니다. PC 표는 열 순서가
         오래 그대로였던 페이지입니다(날짜·종가·전일비·등락률·거래량·기관·
         외국인·보유주수·보유율).
  실적   m.stock /api/stock/{code}/finance/quarter
         financeInfo.trTitleList[] (title·key·isConsensus) 와
         financeInfo.rowList[] (title·columns{key:{value}}) 구조, 단위 억원.
         공개 문서(에이전트용 사용법 정리)에 적힌 구조를 따랐습니다.

설정 → 진단의 '국내 수급·실적 확인' 이 실제 응답을 찍어 줍니다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import requests

from .naver import HEADERS, TIMEOUT, _num

TREND_URL = "https://m.stock.naver.com/api/stock/{code}/trend"
FRGN_URL = "https://finance.naver.com/item/frgn.naver"
FINANCE_URL = "https://m.stock.naver.com/api/stock/{code}/finance/{period}"

_HTML_HEADERS = {**HEADERS, "Accept": "text/html,application/xhtml+xml"}


# ──────────────────────────────────────────────────────────────────────────────
# 수급
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FlowDay:
    """하루치 투자자별 순매매 (주 단위, + 순매수 / − 순매도)."""

    date: str                         # YYYY-MM-DD
    close: float | None = None
    volume: float | None = None
    inst: float | None = None         # 기관
    foreign: float | None = None      # 외국인
    person: float | None = None       # 개인 (PC 표에는 없음)
    foreign_ratio: float | None = None  # 외국인 보유율 %


def _iso(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _key_like(d: dict, *parts: str):
    """키 이름에 parts 가 **모두** 들어간 첫 값 (대소문자 무시)."""
    for k, v in d.items():
        low = str(k).lower()
        if all(p in low for p in parts):
            return v
    return None


def _find_rows(node, depth: int = 0) -> list[dict]:
    """응답 어디에 있든 '외국인 순매매가 든 dict 의 목록' 을 찾아냅니다."""
    if depth > 4:
        return []
    if isinstance(node, list):
        dicts = [x for x in node if isinstance(x, dict)]
        if dicts and any(_key_like(x, "foreign") is not None for x in dicts):
            return dicts
        for x in node:
            got = _find_rows(x, depth + 1)
            if got:
                return got
    elif isinstance(node, dict):
        for v in node.values():
            got = _find_rows(v, depth + 1)
            if got:
                return got
    return []


def parse_trend_json(payload) -> list[FlowDay]:
    out: list[FlowDay] = []
    for d in _find_rows(payload):
        date = _iso(str(_key_like(d, "bizdate") or _key_like(d, "date")
                        or _key_like(d, "traded") or ""))
        if not date:
            continue
        out.append(FlowDay(
            date=date,
            close=_num(_key_like(d, "close")),
            volume=_num(_key_like(d, "volume")),
            inst=_num(_key_like(d, "organ", "pure")),
            foreign=_num(_key_like(d, "foreign", "pure")),
            person=_num(_key_like(d, "individual", "pure")),
            foreign_ratio=_num(str(_key_like(d, "foreign", "ratio") or "")
                               .replace("%", "")),
        ))
    out.sort(key=lambda r: r.date, reverse=True)
    return out


_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_DATE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def _cell(html: str) -> str:
    text = _TAG.sub(" ", html).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _signed_num(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("%", "").strip()
    m = re.search(r"[+\-]?\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def parse_frgn_html(text: str) -> list[FlowDay]:
    """PC '외국인·기관 순매매 거래량' 표. 날짜로 시작하고 9칸 이상인 줄만."""
    out: list[FlowDay] = []
    seen: set[str] = set()
    for tr in _TR.findall(text or ""):
        cells = [_cell(c) for c in _TD.findall(tr)]
        if len(cells) < 9 or not _DATE.match(cells[0]):
            continue
        date = _iso(cells[0])
        if date in seen:
            continue
        seen.add(date)
        out.append(FlowDay(
            date=date, close=_signed_num(cells[1]), volume=_signed_num(cells[4]),
            inst=_signed_num(cells[5]), foreign=_signed_num(cells[6]),
            foreign_ratio=_signed_num(cells[8]),
        ))
    out.sort(key=lambda r: r.date, reverse=True)
    return out


def fetch_flows(code: str, days: int = 40) -> tuple[list[FlowDay], str, str]:
    """(일별 수급 최신순, 출처, 실패 사유)."""
    reasons = []
    try:
        r = requests.get(TREND_URL.format(code=code),
                         params={"pageSize": str(days)},
                         headers=HEADERS, timeout=TIMEOUT)
        if r.ok:
            rows = parse_trend_json(r.json())
            if len(rows) >= 5:
                return rows[:days], "네이버 모바일", ""
            reasons.append(f"모바일 JSON 에서 {len(rows)}줄")
        else:
            reasons.append(f"모바일 HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"모바일 {type(exc).__name__}")

    rows: list[FlowDay] = []
    try:
        for page in (1, 2):
            r = requests.get(FRGN_URL, params={"code": code, "page": page},
                             headers=_HTML_HEADERS, timeout=TIMEOUT)
            if not r.ok:
                reasons.append(f"PC HTTP {r.status_code}")
                break
            enc = (r.encoding or "").lower()
            if enc in ("", "iso-8859-1"):
                r.encoding = "euc-kr"
            got = parse_frgn_html(r.text)
            if not got:
                break
            rows += [g for g in got if g.date not in {x.date for x in rows}]
            if len(rows) >= days:
                break
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"PC {type(exc).__name__}")
    rows.sort(key=lambda x: x.date, reverse=True)
    if rows:
        return rows[:days], "네이버 PC", ""
    return [], "", " · ".join(reasons) or "응답 없음"


# ──────────────────────────────────────────────────────────────────────────────
# 분기 실적 (실적 + 컨센서스)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Period:
    key: str                          # 예: 202609
    title: str                        # 예: 2026.09.
    consensus: bool                   # True 면 증권사 추정치(E)
    values: dict[str, float | None] = field(default_factory=dict)  # 억원

    @property
    def label(self) -> str:
        k = re.sub(r"\D", "", self.key or self.title)
        if len(k) >= 6:
            q = {"03": 1, "06": 2, "09": 3, "12": 4}.get(k[4:6])
            base = f"{k[2:4]}.{q}Q" if q else f"{k[:4]}.{k[4:6]}"
        else:
            base = self.title
        return base + ("(E)" if self.consensus else "")


#: 화면에 쓸 행. (이름, 제목에 들어가는 말들 — 앞에 있을수록 우선)
FIN_ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("매출액", ("매출액", "영업수익", "매출")),
    ("영업이익", ("영업이익",)),
    ("순이익", ("지배주주순이익", "당기순이익", "순이익")),
)


def parse_finance(payload) -> list[Period]:
    info = payload.get("financeInfo") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        info = payload if isinstance(payload, dict) else {}
    titles = info.get("trTitleList") or []
    rows = info.get("rowList") or []
    periods: list[Period] = []
    for t in titles:
        if not isinstance(t, dict):
            continue
        periods.append(Period(
            key=str(t.get("key") or ""), title=str(t.get("title") or ""),
            consensus=str(t.get("isConsensus") or "").upper() == "Y"))
    for name, needles in FIN_ROWS:
        row = None
        for needle in needles:
            row = next((r for r in rows if isinstance(r, dict)
                        and needle in str(r.get("title") or "")
                        and "률" not in str(r.get("title") or "")), None)
            if row:
                break
        cols = (row or {}).get("columns") or {}
        for p in periods:
            cell = cols.get(p.key)
            val = cell.get("value") if isinstance(cell, dict) else cell
            p.values[name] = _num(val) if val not in ("", "-", None) else None
    return periods


def fetch_quarter(code: str) -> tuple[list[Period], str]:
    try:
        r = requests.get(FINANCE_URL.format(code=code, period="quarter"),
                         headers=HEADERS, timeout=TIMEOUT)
        if not r.ok:
            return [], f"HTTP {r.status_code}"
        periods = parse_finance(r.json())
        if not periods:
            return [], "기간 머리글(trTitleList)이 비었습니다"
        return periods, ""
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"


def today_kst() -> dt.date:
    return (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()
