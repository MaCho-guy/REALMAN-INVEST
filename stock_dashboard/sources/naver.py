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


# ──────────────────────────────────────────────────────────────────────────────
# 일봉 · 투자지표 — 국내 스크리너용
# ──────────────────────────────────────────────────────────────────────────────
#
# 2026-11-11 "한국 종목발굴이 0 건". 국내 스크리너는 야후 일봉(.KS/.KQ 두
# 심볼씩 최대 80회)과 야후 .info(종목당 1~2회)에 기대고 있었습니다. 야후는
# 클라우드 서버에서 요청이 몰리면 '너무 많은 요청' 으로 막는 일이 잦고,
# 국내 종목은 코스피/코스닥 접미사를 코드만 봐서는 알 수 없어 요청이
# 두 배가 됩니다. 네이버는 6자리 코드 그대로 받고, 국내 시세의 원래
# 출처라 거래량도 정확합니다. **네이버를 먼저, 실패한 종목만 야후로.**
#
# 두 엔드포인트 모두 공식 문서가 없습니다. 형식이 바뀌면 빈 값과 이유를
# 돌려주고, 호출하는 쪽이 야후로 넘어갑니다.

CHART_URL = ("https://fchart.stock.naver.com/sise.nhn"
             "?symbol={code}&timeframe=day&count={count}&requestType=0")
INTEGRATION_URL = "https://m.stock.naver.com/api/stock/{code}/integration"


def parse_chart_xml(text: str) -> tuple[list[float], list[float], str]:
    """fchart 응답 → (종가, 거래량, 이름).

    항목 형식: <item data="20251110|시가|고가|저가|종가|거래량" />
    """
    import re

    closes: list[float] = []
    vols: list[float] = []
    for raw in re.findall(r'data="([^"]+)"', text or ""):
        parts = raw.split("|")
        if len(parts) < 6:
            continue
        close, vol = _num(parts[4]), _num(parts[5])
        if close is None or close <= 0:
            continue
        closes.append(close)
        vols.append(vol or 0.0)
    m = re.search(r'name="([^"]*)"', text or "")
    return closes, vols, (m.group(1) if m else "")


def last_bar_date(text: str) -> str:
    """fchart 응답의 **마지막 봉 날짜** ('YYYY-MM-DD', 없으면 '').

    2026-11-12 실제 화면에서 섹터 온도의 '1일' 이 +0.8% 인데 같은 시각
    코스피는 +3.7% 였습니다 — 받은 일봉이 어제까지였던 것입니다. 종가만
    보면 마지막 봉이 오늘인지 어제인지 알 수 없어, 날짜를 따로 꺼냅니다.
    """
    import re

    found = re.findall(r'data="(\d{8})\|', text or "")
    if not found:
        return ""
    d = found[-1]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def fetch_daily(code: str, count: int = 300, dates: dict | None = None
                ) -> tuple[list[float], list[float], str]:
    """6자리 코드 → (종가 목록, 거래량 목록, 오류). 오래된 것부터.

    dates 에 dict 를 넘기면 {코드: 마지막 봉 날짜} 를 채워 줍니다.
    """
    try:
        resp = requests.get(CHART_URL.format(code=code, count=count),
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        # 이 엔드포인트는 EUC-KR 로 옵니다. 숫자만 쓰므로 깨져도 무방하지만
        # 이름까지 쓰려면 인코딩을 맞춥니다.
        resp.encoding = resp.encoding or "euc-kr"
        closes, vols, _name = parse_chart_xml(resp.text)
        if dates is not None and closes:
            dates[code] = last_bar_date(resp.text)
    except requests.RequestException as exc:
        return [], [], f"네이버 일봉 요청 실패: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001
        return [], [], f"네이버 일봉 파싱 실패: {type(exc).__name__}"
    if not closes:
        return [], [], "네이버 일봉이 비어 있습니다 (형식이 바뀌었을 수 있음)"
    return closes, vols, ""


def fetch_daily_many(codes: list[str], count: int = 300,
                     dates: dict | None = None,
                     ) -> tuple[dict[str, list[float]], dict[str, list[float]],
                                dict[str, str]]:
    """여러 종목 동시에. ({코드: 종가}, {코드: 거래량}, {코드: 오류}).

    dates 에 dict 를 넘기면 {코드: 마지막 봉 날짜} 를 채워 줍니다.
    """
    closes: dict[str, list[float]] = {}
    vols: dict[str, list[float]] = {}
    errs: dict[str, str] = {}
    unique = list(dict.fromkeys(c for c in codes if c))
    if not unique:
        return closes, vols, errs
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        for code, (c, v, e) in zip(unique, pool.map(
                lambda x: fetch_daily(x, count, dates), unique)):
            if c:
                closes[code], vols[code] = c, v
            if e:
                errs[code] = e
    return closes, vols, errs


def _pick_info(infos: list, *labels: str) -> float | None:
    """totalInfos 에서 key/code 가 정확히 맞는 값. '추정PER' 은 PER 이 아닙니다."""
    want = {lab.lower() for lab in labels}
    for row in infos or []:
        if not isinstance(row, dict):
            continue
        keys = {str(row.get("code", "")).lower(), str(row.get("key", "")).lower()}
        if keys & want:
            return _num(str(row.get("value", "")).replace("배", "")
                        .replace("%", "").replace("원", ""))
    return None


def parse_integration(payload: object) -> dict:
    """integration 응답 → {per, pbr, div_yield, name}. 못 찾은 값은 None."""
    if not isinstance(payload, dict):
        return {"per": None, "pbr": None, "div_yield": None, "name": ""}
    infos = payload.get("totalInfos") or []
    return {
        "per": _pick_info(infos, "per", "PER"),
        "pbr": _pick_info(infos, "pbr", "PBR"),
        "div_yield": _pick_info(infos, "dividendYieldRatio", "배당수익률"),
        "name": str(payload.get("stockName") or ""),
    }


def fetch_valuation(code: str) -> dict:
    """PER · PBR · 배당수익률(%). 실패하면 error 키에 이유."""
    try:
        resp = requests.get(INTEGRATION_URL.format(code=code),
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        out = parse_integration(resp.json())
    except requests.RequestException as exc:
        return {"error": f"네이버 지표 요청 실패: {type(exc).__name__}"}
    except ValueError:
        return {"error": "네이버 지표 응답이 JSON 이 아닙니다"}
    if out["per"] is None and out["pbr"] is None and out["div_yield"] is None:
        out["error"] = "네이버 지표에서 PER·PBR·배당을 찾지 못했습니다"
    else:
        out["error"] = ""
    return out


def fetch_valuation_many(codes: list[str]) -> dict[str, dict]:
    unique = list(dict.fromkeys(c for c in codes if c))
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        return dict(zip(unique, pool.map(fetch_valuation, unique)))


# ──────────────────────────────────────────────────────────────────────────────
# 고가·저가 포함 일봉 — 차트 조건(일목·CCI·DMI)용
# ──────────────────────────────────────────────────────────────────────────────

def parse_chart_ohlc(text: str) -> dict[str, list[float]]:
    """fchart 응답 → {"high","low","close","volume"} (오래된 것부터).

    항목 형식: <item data="20251110|시가|고가|저가|종가|거래량" />
    고가·저가가 비거나 0 인 봉은 종가로 메웁니다 — 거래정지일에 그렇게 옵니다.
    """
    import re

    out: dict[str, list[float]] = {"high": [], "low": [], "close": [], "volume": []}
    for raw in re.findall(r'data="([^"]+)"', text or ""):
        parts = raw.split("|")
        if len(parts) < 6:
            continue
        close = _num(parts[4])
        if close is None or close <= 0:
            continue
        high, low = _num(parts[2]), _num(parts[3])
        high = high if high and high > 0 else close
        low = low if low and low > 0 else close
        out["high"].append(max(high, close))
        out["low"].append(min(low, close))
        out["close"].append(close)
        out["volume"].append(_num(parts[5]) or 0.0)
    if out["close"]:
        out["last_date"] = last_bar_date(text)     # 문자열 — 마지막 봉이 언제 것인가
    return out


def fetch_ohlc(code: str, count: int = 300) -> tuple[dict[str, list[float]], str]:
    try:
        resp = requests.get(CHART_URL.format(code=code, count=count),
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = parse_chart_ohlc(resp.text)
    except requests.RequestException as exc:
        return {}, f"네이버 일봉 요청 실패: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001
        return {}, f"네이버 일봉 파싱 실패: {type(exc).__name__}"
    if not data["close"]:
        return {}, "네이버 일봉이 비어 있습니다 (형식이 바뀌었을 수 있음)"
    return data, ""


def fetch_ohlc_many(codes: list[str], count: int = 300
                    ) -> tuple[dict[str, dict], dict[str, str]]:
    """({코드: {"high","low","close","volume"}}, {코드: 오류})."""
    unique = list(dict.fromkeys(c for c in codes if c))
    out: dict[str, dict] = {}
    errs: dict[str, str] = {}
    if not unique:
        return out, errs
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        for code, (data, err) in zip(unique, pool.map(
                lambda x: fetch_ohlc(x, count), unique)):
            if data:
                out[code] = data
            if err:
                errs[code] = err
    return out, errs
