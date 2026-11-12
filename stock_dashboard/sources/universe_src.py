"""
종목 발굴 후보 목록을 받아 옵니다 (통신만 — 해석은 universe.py).

    미국   위키백과 'List of S&P 500 companies' 의 구성 종목 표
    한국   네이버 증권 — 지수 구성 종목(enrollStocks) · 시가총액 순위(marketValue)

주소와 응답 모양은 2026-11-12 실제 응답으로 확인했습니다 (설정 → 진단 →
'발굴 후보 출처 확인'). 시가총액 순위는 한 쪽에 100개까지이고 ETF 가 섞여
옵니다 — 주식만 N 개가 찰 때까지 쪽을 넘깁니다.
"""
from __future__ import annotations

import requests

import universe

from . import naver

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
#: 나스닥100 구성 종목 표는 2026-11 현재 지수 문서가 아니라 **목록 문서**에 있습니다
#: (지수 문서에는 표가 없습니다 — 2026-11-12 진단으로 확인). 옮겨질 때를 대비해
#: 둘 다 차례로 봅니다.
NDX_URLS = ("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
            "https://en.wikipedia.org/wiki/Nasdaq-100")
#: 나스닥100 표의 업종은 ICB 분류라 이름이 조금 다릅니다 — S&P 500 의 GICS 이름으로 맞춥니다
#: (업종 필터에 '정보기술' 이 두 번 나오지 않게). 분류 체계가 달라 완전히 같지는 않습니다.
ICB_TO_GICS = {"Technology": "Information Technology",
               "Telecommunications": "Communication Services",
               "Basic Materials": "Materials"}
INDEX_URL = "https://m.stock.naver.com/api/index/{code}/enrollStocks?page={page}&pageSize={size}"
CAP_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize={size}"
PAGE_SIZE = 100
TIMEOUT = 15
UA = {"User-Agent": "stock-dashboard/1.0 (personal dashboard)"}


class UniverseError(RuntimeError):
    """후보 목록을 받지 못함."""


def _get_json(url: str, get=None):
    resp = (get or requests.get)(url, headers={**naver.HEADERS, "Accept": "application/json"},
                                 timeout=TIMEOUT)
    resp.raise_for_status()
    if not resp.content:
        return []
    return resp.json()


def fetch_index_table(url: str, floor: int, label: str, get=None) -> list[dict]:
    """위키백과 구성 종목 표 [{ticker, name, sector, cik}]. 너무 적게 오면 예외."""
    resp = (get or requests.get)(url, headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    members = universe.parse_index_table(resp.text)
    if len(members) < floor:
        raise UniverseError(f"{label} 표에서 {len(members)}종목만 읽었습니다 "
                            "(페이지 구조가 바뀌었을 수 있습니다).")
    return members


def fetch_sp500(get=None) -> list[dict]:
    return fetch_index_table(SP500_URL, universe.MIN_SP500, "S&P 500", get)


def fetch_us_members(get=None) -> tuple[list[dict], dict]:
    """미국 후보 — (종목 목록, 규칙). S&P 500 은 꼭 있어야 하고, 나스닥100 은
    못 받으면 빼고 갑니다 (규칙에 그렇게 적힙니다)."""
    sp = fetch_sp500(get)
    for m in sp:
        m["index"] = True
    rules = {"S&P 500 구성 종목": {"n": len(sp), "how": "index"}}
    have = {m["ticker"] for m in sp}
    ndx: list[dict] = []
    why = ""
    for url in NDX_URLS:
        try:
            ndx = fetch_index_table(url, universe.MIN_NDX, "나스닥100", get)
            break
        except Exception as exc:  # noqa: BLE001
            why = f"{type(exc).__name__}: {str(exc)[:90]}"
    if not ndx:
        rules["나스닥100 (목록을 못 받아 제외)"] = {"n": 0, "how": f"실패: {why}"}
        return sp, rules
    added = [dict(m, index=True, sector=ICB_TO_GICS.get(m.get("sector", ""), m.get("sector", "")))
             for m in ndx if m["ticker"] not in have]
    rules["나스닥100 에만 있는 종목"] = {"n": len(added), "how": "index",
                                  "total": len(ndx)}
    return sp + added, rules


def fetch_index_members(code: str, expect: int, get=None,
                        sizes: tuple[int, ...] = (100, 50, 20)) -> list[dict]:
    """지수 구성 종목 [{code, name, cap}]. 빈 응답이면 빈 목록 (그 지수 코드가 없는 것).

    쪽 크기를 줄여 가며 받아 봅니다 — 2026-11-12 첫 실행에서 100개씩은 받지
    못했습니다 (3개씩은 왔습니다). 가장 많이 받은 결과를 돌려줍니다.
    """
    best: list[dict] = []
    for size in sizes:
        out: list[dict] = []
        seen: set[str] = set()
        try:
            for page in range(1, expect // size + 3):
                rows = universe.parse_naver_stocks(
                    _get_json(INDEX_URL.format(code=code, page=page, size=size), get))
                fresh = [r for r in rows if r["code"] not in seen]
                if not fresh:
                    break
                seen.update(r["code"] for r in fresh)
                out.extend(fresh)
                if len(out) >= expect or len(rows) < size:
                    break
        except Exception:  # noqa: BLE001 - 이 쪽 크기는 안 받는 것 — 더 작게
            pass
        if len(out) > len(best):
            best = out
        if len(best) >= expect:
            break
    return best


def fetch_cap_top(market: str, n: int, get=None, max_pages: int = 8) -> list[dict]:
    """시가총액 상위 보통주 n 개 [{code, name, cap}]. market: KOSPI / KOSDAQ."""
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        rows = universe.parse_naver_stocks(
            _get_json(CAP_URL.format(market=market, page=page, size=PAGE_SIZE), get))
        if not rows:
            break
        for r in rows:
            if r["code"] in seen or not universe.is_common_stock(r["code"], r["name"]):
                continue
            seen.add(r["code"])
            out.append(r)
            if len(out) >= n:
                return out
    return out


def fetch_kr_members(get=None) -> tuple[list[dict], dict]:
    """한국 후보 — (종목 목록, 규칙). 규칙: {이름: {n, how}}.

    구성 종목 목록을 먼저 받고, 못 받으면(코드가 없거나 너무 적으면) 시가총액
    상위로 대신합니다. 어느 쪽을 썼는지 규칙에 적어 화면에 그대로 냅니다.
    """
    members: list[dict] = []
    rules: dict = {}
    plan = (
        ("KOSPI", ("KPI200",), universe.KOSPI_N, universe.MIN_KOSPI, "코스피200 구성 종목"),
        ("KOSDAQ", ("KQ150", "KOSDAQ150", "KSQ150"), universe.KOSDAQ_N, universe.MIN_KOSDAQ,
         "코스닥150 구성 종목"),
    )
    for market, codes, n, floor, label in plan:
        rows: list[dict] = []
        how = ""
        for code in codes:
            try:
                rows = fetch_index_members(code, n, get)
            except Exception:  # noqa: BLE001 - 다음 코드 · 시가총액 순위로 넘어갑니다
                rows = []
            if len(rows) >= floor:
                how = "index"
                break
        if how != "index":
            rows = fetch_cap_top(market, n, get)
            label, how = f"{'코스피' if market == 'KOSPI' else '코스닥'} 시가총액 상위 {n}", "cap"
        if not rows:
            raise UniverseError(f"{market} 후보를 받지 못했습니다.")
        for r in rows:
            r["market"], r["index"] = market, True
        members.extend(rows)
        rules[label] = {"n": len(rows), "how": how}
    return members, rules


# ── 업종 (반도체) ────────────────────────────────────────────────────────────
#
# 2026-11-12 사용자 승인: 차트 조건 탭 한국 350종목에서 반도체 종목을 맨 위에,
# 분류는 네이버 업종. 응답 모양은 2026-11-13 survey(market=industry)로 확인:
#   업종 목록  {"groups": [{"no": 278, "name": "반도체와반도체장비", "totalCount": 174, …}]}
#   업종 종목  {"stocks": [{itemCode, stockName, stockEndType, marketValue, …}]}
# PC 업종 페이지(finance.naver.com/sise/sise_group*)는 스크립트로 그리는 페이지라
# HTML 에 종목이 없습니다 — 쓰지 않습니다. 모바일 API 는 Accept 가 JSON 이어야
# 받습니다 (text/html 이면 406). 결과에 SK하이닉스 · 삼성전자가 하나도 없으면
# 분류가 틀린 것으로 보고 버립니다.

GROUPS_API_URL = "https://m.stock.naver.com/api/stocks/industry?page={page}&pageSize={size}"
GROUP_API_URL = "https://m.stock.naver.com/api/stocks/industry/{no}?page={page}&pageSize={size}"
#: 분류가 맞는지 보는 표지 종목 — 둘 중 하나는 반도체 업종에 있어야 합니다.
SEMI_MARKERS = ("000660", "005930")


def parse_groups(payload) -> list[dict]:
    """업종 목록 응답 → [{no, name, n}]."""
    items = payload.get("groups") if isinstance(payload, dict) else payload
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("no") in (None, ""):
            continue
        out.append({"no": str(it["no"]), "name": str(it.get("name") or "").strip(),
                    "n": int(_to_int(it.get("totalCount")))})
    return out


def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def fetch_group_codes(no: str, expect: int, get=None,
                      sizes: tuple[int, ...] = (100, 50, 20)) -> list[str]:
    """업종 하나의 종목 코드. 쪽 크기를 줄여 가며 가장 많이 받은 결과."""
    best: list[str] = []
    for size in sizes:
        got: list[str] = []
        try:
            for page in range(1, max(expect, size) // size + 3):
                rows = universe.parse_naver_stocks(
                    _get_json(GROUP_API_URL.format(no=no, page=page, size=size), get))
                fresh = [r["code"] for r in rows if r["code"] not in got]
                if not fresh:
                    break
                got.extend(fresh)
                if len(rows) < size or (expect and len(got) >= expect):
                    break
        except Exception:  # noqa: BLE001 - 이 쪽 크기는 안 받는 것 — 더 작게
            pass
        if len(got) > len(best):
            best = got
        if expect and len(best) >= expect:
            break
    return best


def fetch_kr_industry(keyword: str = "반도체", get=None) -> tuple[set[str], dict]:
    """이름에 keyword 가 든 네이버 업종의 종목 코드 — (코드 묶음, 정보).

    정보: {name, no, n, total}. 실패하면 예외 (UniverseError) — 부르는 쪽이
    지난 분류로 돌아갑니다.
    """
    groups: list[dict] = []
    for page in range(1, 4):
        got = parse_groups(_get_json(GROUPS_API_URL.format(page=page, size=PAGE_SIZE), get))
        groups.extend(g for g in got if g["no"] not in {x["no"] for x in groups})
        if len(got) < PAGE_SIZE:
            break
    picked = [g for g in groups if keyword in g["name"]]
    if not picked:
        raise UniverseError(f"업종 {len(groups)}개 중 '{keyword}' 가 든 업종이 없습니다 "
                            "(응답 모양이 바뀌었을 수 있습니다).")
    codes: set[str] = set()
    for g in picked:
        codes.update(fetch_group_codes(g["no"], g["n"], get))
    total = sum(g["n"] for g in picked)
    if keyword == "반도체" and not any(m in codes for m in SEMI_MARKERS):
        raise UniverseError(f"'{keyword}' 업종 {len(codes)}/{total}종목에 SK하이닉스 · "
                            "삼성전자가 없습니다 (분류를 믿을 수 없음).")
    return codes, {"name": " · ".join(g["name"] for g in picked),
                   "no": ",".join(g["no"] for g in picked), "n": len(codes), "total": total}
