"""
종목 발굴의 후보 — 손으로 고른 목록 대신 **규칙으로 정한 목록**.

2026-11-12 "종목 발굴에 있는 주식들은 어떤 근거로 축소된 것인지?" — 그때까지
후보는 제가 config 에 손으로 적어 둔 71개(미국)·52개(한국)였습니다. 기준에
맞을 법한 회사를 미리 골라 놓고 기준을 적용했으니 통과율이 높은 것이
당연했고(순환), 목록에 없는 종목은 심사조차 받지 않았습니다.

이제 후보는 규칙이 정합니다.

    미국   S&P 500 구성 종목 + 나스닥100 구성 종목 (위키백과의 구성 종목 표)
           나스닥100 을 더하는 이유: 나스닥에 상장됐지만 S&P 500 에는 없는
           종목(최근 상장 · 외국 기업)이 빠지기 때문입니다 (2026-11-12 사용자 지적).
           외국 기업은 미국 회계기준 재무가 없어 '재무를 못 받음' 으로 남습니다.
    한국   코스피200 구성 종목 + 코스닥150 구성 종목
           (구성 종목 목록을 못 받으면 시가총액 상위 N 개 — 어느 쪽을 썼는지 파일에 적음)
    공통   내 관심종목은 지수에 없어도 포함

**어디서 계산하나.** 미국 500개는 SEC 에 500번, 한국 350개는 네이버에 700번
요청합니다. 화면을 열 때 받을 수 없는 양이라 아침 수집기(tools/collect.py)가
계산해 결과만 파일로 올리고, 앱은 그 파일을 읽습니다.

    universe_us.json   {version, made, rules, members: [...], screens: [...], errors: {...}}
    universe_kr.json   {version, made, rules, members: [...], profiles: [...], values: [...], errors}

이 모듈은 통신을 하지 않습니다 (해석 · 저장 · 되살리기만). 통신은
sources/universe_src.py 입니다.
"""
from __future__ import annotations

import dataclasses
import html as _html
import json
import re
import time

VERSION = 1

#: 한국 — 구성 종목을 못 받았을 때 시가총액 상위 몇 개로 대신하나.
KOSPI_N, KOSDAQ_N = 200, 150
#: 구성 종목 목록이 이보다 적게 오면 '못 받은 것' 으로 봅니다 (지수 개편 중에도
#: 몇 개 차이만 납니다).
MIN_SP500, MIN_KOSPI, MIN_KOSDAQ = 450, 180, 130
MIN_NDX = 90


# ── 미국: S&P 500 표 ─────────────────────────────────────────────────────────

_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _cell_text(cell: str) -> str:
    return _html.unescape(_TAG.sub("", cell)).replace("\xa0", " ").strip()


_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.I)


_TABLE = re.compile(r"<table[^>]*>.*?</table>", re.S | re.I)


def _parse_one_table(body: str) -> list[dict]:
    """표 하나 → [{ticker, name, sector, cik}]. 티커 칸이 없는 표면 빈 목록."""
    rows = _TR.findall(body)
    heads: list[str] = []
    for row in rows:
        heads = [_cell_text(c).lower() for c in _TH.findall(row)]
        if heads:
            break

    def col(*words, avoid=()) -> int | None:
        for idx, h in enumerate(heads):
            if any(w in h for w in words) and not any(a in h for a in avoid):
                return idx
        return None

    c_tick = col("symbol", "ticker")
    if c_tick is None:
        return []
    c_name = col("security", "company")
    c_sect = col("sector", avoid=("sub",))
    if c_sect is None:
        c_sect = col("industry", avoid=("sub",))
    c_cik = col("cik")
    c_sub = col("sub-industry", "sub industry", "subsector", "sub-sector")
    out, seen = [], set()
    for row in rows:
        if not _TD.findall(row):
            continue                     # 머리글 줄
        # 티커가 <th scope="row"> 로 올 때도 있어 th·td 를 순서대로 같이 읽습니다
        cells = [_cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if len(cells) <= c_tick:
            continue
        ticker = cells[c_tick].upper().strip()
        if not ticker or not re.fullmatch(r"[A-Z0-9.\-]{1,7}", ticker) or ticker in seen:
            continue

        def at(c):
            return cells[c] if c is not None and c < len(cells) else ""
        cik = at(c_cik).lstrip("0")
        seen.add(ticker)
        item = {"ticker": ticker, "name": at(c_name), "sector": at(c_sect),
                "cik": int(cik) if cik.isdigit() else None}
        if at(c_sub):
            item["sub"] = at(c_sub)      # 세부 업종 — 차트 조건의 반도체 분류용 (파일에는 안 씀)
        out.append(item)
    return out


def parse_index_table(page: str) -> list[dict]:
    """위키백과 지수 구성 종목 표 → [{ticker, name, sector, cik}].

    칸 순서를 외워 두지 않고 **머리글로** 찾습니다 — S&P 500 표(Symbol ·
    Security · GICS Sector · … · CIK, 2026-11-12 실제 응답으로 확인)와 나스닥100
    표가 순서가 다르고, 위키백과는 칸을 가끔 바꿉니다.

    표도 id 하나에 기대지 않습니다. id="constituents" 표를 먼저 보고, 거기서
    못 읽으면 페이지의 표 가운데 **티커 칸이 있고 줄이 가장 많은 것**을 씁니다
    (2026-11-12 첫 실행에서 나스닥100 은 그 id 로 읽히지 않았습니다).
    """
    page = page or ""
    best: list[dict] = []
    i = page.find('id="constituents"')
    if i >= 0:
        start = page.rfind("<table", 0, i)
        j = page.find("</table>", i)
        best = _parse_one_table(page[start if start >= 0 else i:j if j > 0 else len(page)])
    if len(best) >= 50:
        return best
    for block in _TABLE.findall(page):
        got = _parse_one_table(block)
        if len(got) > len(best):
            best = got
    return best


def parse_sp500(page: str) -> list[dict]:
    """S&P 500 구성 종목 표 (parse_index_table 과 같음 — 이름만 남김)."""
    return parse_index_table(page)


#: GICS 업종의 우리말 이름 (화면 표시용).
SECTOR_KO = {
    "Information Technology": "정보기술", "Health Care": "헬스케어",
    "Financials": "금융", "Consumer Discretionary": "경기소비재",
    "Communication Services": "커뮤니케이션", "Industrials": "산업재",
    "Consumer Staples": "필수소비재", "Energy": "에너지", "Utilities": "유틸리티",
    "Real Estate": "부동산", "Materials": "소재",
}


def sector_label(sector: str) -> str:
    return SECTOR_KO.get(sector, sector or "분류 없음")


# ── 한국: 네이버 종목 목록 ───────────────────────────────────────────────────

def _to_float(text) -> float | None:
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def is_common_stock(code: str, name: str) -> bool:
    """보통주인가 — 우선주 · 스팩 · 리츠형 펀드를 걸러냅니다.

    국내 종목코드는 보통주가 0 으로 끝나고 우선주는 5·7·9·K·L 등으로 끝납니다.
    시가총액 순위에는 우선주(삼성전자우)가 섞여 있어, 지수 구성 종목을 못
    받았을 때 이걸로 거릅니다.
    """
    code, name = (code or "").strip(), (name or "").strip()
    if len(code) != 6 or not code.isdigit() or not code.endswith("0"):
        return False
    return not ("스팩" in name or name.endswith(("우", "우B", "우C")))


def parse_naver_stocks(payload) -> list[dict]:
    """네이버 종목 목록 응답 → [{code, name, cap}] (cap: 시가총액, 억 원).

    두 모양을 받습니다 (2026-11-12 실제 응답):
      시가총액 순위  {"stocks": [{itemCode, stockName, stockEndType, marketValue, …}], …}
      지수 구성 종목  [{itemCode, stockName, stockEndType, …}]
    ETF 등 주식이 아닌 것(stockEndType != "stock")은 뺍니다.
    """
    items = payload.get("stocks") if isinstance(payload, dict) else payload
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        if str(it.get("stockEndType") or "stock") != "stock":
            continue
        code = str(it.get("itemCode") or "").strip()
        name = str(it.get("stockName") or "").strip()
        if not code or not name:
            continue
        out.append({"code": code, "name": name, "cap": _to_float(it.get("marketValue"))})
    return out


def merge_members(*lists, extra=()) -> list[dict]:
    """목록들을 합칩니다 (중복 제거). extra: 지수에 없어도 넣을 종목(관심종목).

    지수 목록에서 온 것은 index=True, extra 에만 있는 것은 index=False 입니다.
    extra 가 맨 앞에 옵니다. '관심종목인가' 는 파일에 적지 않습니다 — 화면이
    제 설정으로 압니다.
    """
    seen: dict[str, dict] = {}
    for item in extra:
        key = item.get("code") or item.get("ticker")
        if key and key not in seen:
            seen[key] = {**item, "index": False}
    for lst in lists:
        for item in lst:
            key = item.get("code") or item.get("ticker")
            if not key:
                continue
            if key in seen:
                seen[key] = {**seen[key], **{k: v for k, v in item.items() if v not in (None, "")},
                             "index": True}
            else:
                seen[key] = {**item, "index": True}
    return list(seen.values())


# ── 저장 · 읽기 ──────────────────────────────────────────────────────────────

def dump(payload: dict) -> str:
    return json.dumps({"version": VERSION, "made": int(time.time()), **payload},
                      ensure_ascii=False, separators=(",", ":"))


def parse(text: str) -> dict:
    """파일 글 → 묶음. 깨졌거나 버전이 다르면 빈 묶음."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return {}
    return data


def age_hours(payload: dict, now: float | None = None) -> float | None:
    made = payload.get("made") if isinstance(payload, dict) else None
    if not made:
        return None
    return ((time.time() if now is None else now) - float(made)) / 3600.0


def profile_to_dict(profile) -> dict:
    """VolProfile · ValueRow → 사전 (None 인 칸은 빼서 파일을 줄입니다)."""
    return {k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in dataclasses.asdict(profile).items() if v not in (None, "")}


def restore(cls, rows) -> list:
    """사전 목록 → dataclass 목록. 모르는 칸은 버립니다 (파일이 더 새 버전일 때)."""
    names = {f.name for f in dataclasses.fields(cls)}
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("ticker"):
            try:
                out.append(cls(**{k: v for k, v in row.items() if k in names}))
            except TypeError:
                continue
    return out


def rule_text(market: str, payload: dict) -> str:
    """후보를 어떻게 정했는지 한 줄 — 파일에 적힌 대로.

    규칙마다 '그 규칙으로 **새로 들어온** 종목 수' 를 적습니다 (앞 규칙과 겹치는
    것은 빼고) — 더하면 전체가 되게.
    """
    members = payload.get("members") or []
    rules = payload.get("rules") or {}
    extra = sum(1 for m in members if not m.get("index"))
    # 이름이 이미 그 숫자로 끝나면 ('…상위 150') 숫자를 또 붙이지 않습니다
    parts = [name if name.endswith(f" {info.get('n', 0)}") else f"{name} {info.get('n', 0)}"
             for name, info in rules.items()]
    # 한 회사가 주식을 두 종류 상장한 경우(GOOGL · GOOG 등)는 재무가 같아 하나로
    # 셉니다 — 그만큼 합계가 모자라므로 그 사실을 적습니다 (2026-11-12 실제:
    # 503 + 15 + 1 = 519 인데 516종목으로 적혀 셈이 안 맞아 보였습니다).
    total = sum(int(info.get("n", 0) or 0) for info in rules.values()) + extra
    merged = total - len(members)
    return (" + ".join(parts) + (f" + 관심종목 {extra}" if extra else "")
            + (f" − 같은 회사의 다른 주식 {merged}" if merged > 0 else "")
            + f" = {len(members)}종목")
