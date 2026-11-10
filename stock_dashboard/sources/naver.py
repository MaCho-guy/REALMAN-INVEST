"""
국내 종목 실시간 시세 (네이버 금융 폴링 API).

엔드포인트:
  https://polling.finance.naver.com/api/realtime/domestic/stock/{code}

이 API 는 공식 문서가 없는 비공개 엔드포인트입니다. 응답 구조가 바뀔 수
있으므로 파싱을 방어적으로 처리하고, 실패하면 야후 파이낸스
({code}.KS) 로 폴백합니다.

필드 의미 (확인된 범위):
  nv = 현재가, sv = 전일 종가, cv = 전일 대비 변동폭, cr = 변동률(%)
  rf = 등락 구분 코드 ("1" 상한, "2" 상승, "3" 보합, "4" 하한, "5" 하락)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import requests

from .model import MarketStatus, Quote

BASE_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
TIMEOUT = 8

#: 네이버는 브라우저가 아닌 요청을 막는 경우가 있어 referer 를 같이 보냅니다.
HEADERS = {
    "User-Agent": "stock-dashboard/1.0 (personal dashboard)",
    "Referer": "https://finance.naver.com/",
    "Accept": "application/json",
}


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def _walk_for_datas(node: object) -> list[dict]:
    """응답 구조가 바뀌어도 'nv' 를 가진 dict 들을 찾아냅니다."""
    found: list[dict] = []

    def visit(obj: object) -> None:
        if isinstance(obj, dict):
            if "nv" in obj or "cd" in obj:
                found.append(obj)
            for val in obj.values():
                visit(val)
        elif isinstance(obj, list):
            for val in obj:
                visit(val)

    visit(node)
    return found


def _fetch_one(code: str) -> Quote:
    url = BASE_URL.format(code=code)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        return _yahoo_fallback(code, f"네이버 요청 실패: {exc}")
    except ValueError as exc:
        return _yahoo_fallback(code, f"네이버 응답 파싱 실패: {exc}")

    candidates = _walk_for_datas(payload)
    row = None
    for cand in candidates:
        if str(cand.get("cd", "")).lstrip("A") == code:
            row = cand
            break
    if row is None and candidates:
        row = candidates[0]

    if row is None:
        return _yahoo_fallback(code, "네이버 응답에서 시세 데이터를 찾지 못했습니다.")

    price = _num(row.get("nv"))
    prev = _num(row.get("sv"))

    if price is None:
        return _yahoo_fallback(code, "네이버 응답에 현재가(nv)가 없습니다.")

    # 전일종가가 없으면 변동폭으로 역산
    if prev is None:
        cv = _num(row.get("cv"))
        rf = str(row.get("rf", ""))
        if cv is not None:
            # rf 가 하락(4,5)이면 cv 는 양수로 오므로 부호를 반전합니다.
            signed = -cv if rf in {"4", "5"} else cv
            prev = price - signed

    name = row.get("nm")

    return Quote(
        symbol=code,
        price=price,
        prev_close=prev,
        currency="KRW",
        status=MarketStatus.UNKNOWN,  # 네이버 응답에 장 상태 플래그가 없습니다
        extra={"name": name} if isinstance(name, str) else {},
    )


def _yahoo_fallback(code: str, reason: str) -> Quote:
    """네이버가 실패하면 야후({code}.KS)로 재시도합니다."""
    from . import yahoo  # 순환 임포트 방지를 위해 지역 임포트

    for suffix in (".KS", ".KQ"):
        quote = yahoo.fetch_quotes([f"{code}{suffix}"]).get(f"{code}{suffix}")
        if quote is not None and quote.ok:
            quote.symbol = code
            quote.currency = "KRW"
            quote.extra = dict(quote.extra, fallback=f"야후 {code}{suffix}")
            return quote

    return Quote.failed(code, f"{reason} (야후 폴백도 실패)")


def fetch_quotes(codes: list[str]) -> dict[str, Quote]:
    """국내 종목코드 목록을 병렬 조회합니다."""
    unique = list(dict.fromkeys(c for c in codes if c))
    if not unique:
        return {}

    def safe(code: str) -> Quote:
        try:
            return _fetch_one(code)
        except Exception as exc:  # noqa: BLE001
            return Quote.failed(code, f"조회 중 예외: {exc}")

    with ThreadPoolExecutor(max_workers=min(6, len(unique))) as pool:
        results = list(pool.map(safe, unique))

    return dict(zip(unique, results))
