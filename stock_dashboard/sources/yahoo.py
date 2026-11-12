"""
야후 파이낸스 시세 (yfinance 경유).

여러 심볼을 스레드 풀로 병렬 조회합니다. 심볼 하나가 실패해도
해당 Quote 에만 error 가 담기고 나머지는 정상 반환됩니다.

프리장/애프터장:
  yfinance 의 `Ticker.info` 에 marketState, preMarketPrice, postMarketPrice 가
  있을 때만 채웁니다. 선물·FX 처럼 해당 개념이 없는 상품은 비어 있습니다.

주의:
  야후 파이낸스는 공식 API 가 아니며 필드 구성이 예고 없이 바뀝니다.
  이 모듈은 모든 필드 접근을 방어적으로 처리합니다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .model import MarketStatus, Quote

#: 42종목을 8개씩 나누면 6묶음입니다. ticker.info 는 호출당 여러
#: 엔드포인트를 긁어 1~3초씩 걸려서, 묶음 수가 그대로 대기 시간이 됩니다.
#: 야후는 공식 제한을 밝히지 않지만 12는 흔히 쓰이는 수준입니다.
MAX_WORKERS = 12

#: 야후 marketState -> 화면 배지
_STATE_MAP = {
    "REGULAR": MarketStatus.REGULAR,
    "PRE": MarketStatus.PRE,
    "PREPRE": MarketStatus.CLOSED,
    "POST": MarketStatus.POST,
    "POSTPOST": MarketStatus.CLOSED,
    "CLOSED": MarketStatus.CLOSED,
}


def _import_yfinance():
    try:
        import yfinance  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "yfinance 가 설치되지 않았습니다. `pip install -r requirements.txt` 를 실행하십시오."
        ) from exc
    return yfinance


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    # 야후는 결측을 0 이 아니라 누락으로 주지만, NaN 이 섞여 오는 경우가 있습니다.
    if out != out:  # NaN
        return None
    return out


def _market_of(symbol: str) -> str:
    """심볼이 어느 시장의 휴장일을 따르나 — 'kr' · 'us' · '' (모름: 평일은 다 거래일)."""
    sym = (symbol or "").upper()
    if sym.endswith((".KS", ".KQ")) or sym in ("^KS11", "^KQ11", "^KS200"):
        return "kr"
    if sym.endswith(("=F", "=X")) or "-USD" in sym:
        return ""
    if sym.startswith("^") or sym.isalpha():
        return "us"
    return ""


def bars_adjacent(prev_day, last_day, market: str = "") -> bool:
    """두 봉 사이에 **빠진 거래일이 없는가**.

    사이에 낀 날이 전부 주말이거나 그 시장의 휴장일이면 True. 평일이 하나라도
    끼어 있으면 봉이 하나 빠진 것입니다.
    """
    import datetime as _dt  # noqa: PLC0415

    try:
        import calendar_events as _ce  # noqa: PLC0415
        holidays = {"kr": _ce.KRX_HOLIDAYS, "us": _ce.NYSE_HOLIDAYS}.get(market, {})
    except Exception:  # noqa: BLE001
        holidays = {}
    day = prev_day + _dt.timedelta(days=1)
    while day < last_day:
        if day.weekday() < 5 and day.isoformat() not in holidays:
            return False
        day += _dt.timedelta(days=1)
    return True


def pick_price_prev(rows: list, market: str = "") -> tuple[float | None, float | None, bool]:
    """[(날짜, 종가)] → (가격, 전일 종가, 전일 종가를 믿을 수 있나).

    2026-11-12 실제 화면: 같은 코스피 5,430 근처에서 등락률이 6분 사이에
    +3.69% → +0.97% 로 바뀌었습니다. 야후가 일봉 5일치에서 **어제 봉을
    빠뜨린 채** 돌려준 적이 있고, '끝에서 두 번째 종가' 를 전일 종가로
    쓰던 코드는 그걸 그제 종가와 비교해 이틀치 등락을 하루치처럼 보였습니다.
    이제 두 봉의 **날짜**를 보고, 사이에 거래일이 빠졌으면 믿지 않습니다.
    """
    clean = [(d, float(c)) for d, c in rows if c is not None and c == c and c > 0]
    if not clean:
        return None, None, False
    last_day, price = clean[-1]
    if len(clean) == 1:
        return price, None, False
    prev_day, prev = clean[-2]
    try:
        ok = bars_adjacent(prev_day, last_day, market)
    except Exception:  # noqa: BLE001 - 날짜를 못 읽으면 예전처럼
        ok = True
    return price, prev, ok


def _from_history(ticker, symbol: str = "") -> tuple[float | None, float | None]:
    """최근 5영업일 일봉으로 가격/전일 종가를 구합니다.

    전일 종가는 봉 날짜가 이어질 때만 일봉에서 가져옵니다. 봉이 빠졌으면
    야후가 따로 주는 전일 종가(fast_info)를 쓰고, 그것도 없으면 **비워
    둡니다** — 틀린 등락률보다 '—' 가 낫습니다.
    """
    try:
        hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
    except Exception:  # noqa: BLE001 - 야후는 다양한 예외를 던집니다
        return None, None
    if hist is None or hist.empty or "Close" not in hist:
        return None, None
    rows = []
    for stamp, close in zip(list(hist.index), hist["Close"].tolist()):
        try:
            day = stamp.date() if hasattr(stamp, "date") else stamp
        except Exception:  # noqa: BLE001
            day = None
        rows.append((day, close))
    if any(d is None for d, _c in rows):
        closes = [c for _d, c in rows if c == c]
        if not closes:
            return None, None
        return closes[-1], (closes[-2] if len(closes) > 1 else None)
    price, prev, trusted = pick_price_prev(rows, _market_of(symbol))
    if price is None or trusted:
        return price, prev
    try:
        fast = ticker.fast_info
        alt = _num(fast.get("previousClose")) or _num(fast.get("regularMarketPreviousClose"))
    except Exception:  # noqa: BLE001
        alt = None
    return price, alt


def _fetch_one(symbol: str) -> Quote:
    yf = _import_yfinance()
    ticker = yf.Ticker(symbol)

    info: dict = {}
    try:
        raw = ticker.info
        if isinstance(raw, dict):
            info = raw
    except Exception:  # noqa: BLE001
        info = {}

    price = _num(info.get("regularMarketPrice"))
    prev = _num(info.get("regularMarketPreviousClose")) or _num(info.get("previousClose"))
    currency = info.get("currency") or ""
    if isinstance(currency, str):
        currency = currency.upper()
    else:
        currency = ""

    # fast_info 로 보강
    if price is None or prev is None:
        try:
            fast = ticker.fast_info
            price = price or _num(fast.get("lastPrice"))
            prev = prev or _num(fast.get("previousClose"))
            currency = currency or str(fast.get("currency") or "").upper()
        except Exception:  # noqa: BLE001
            pass

    # 그래도 없으면 히스토리
    if price is None:
        h_price, h_prev = _from_history(ticker, symbol)
        price = price or h_price
        prev = prev or h_prev

    if price is None:
        return Quote.failed(
            symbol,
            f"'{symbol}' 시세를 가져올 수 없습니다. 티커가 존재하지 않거나 "
            f"야후 파이낸스가 해당 상품을 제공하지 않습니다.",
        )

    state_raw = info.get("marketState")
    status = _STATE_MAP.get(state_raw, MarketStatus.UNKNOWN) if isinstance(state_raw, str) else MarketStatus.UNKNOWN

    extended_price: float | None = None
    extended_label = ""
    if status is MarketStatus.PRE:
        extended_price = _num(info.get("preMarketPrice"))
        extended_label = "프리장"
    elif status is MarketStatus.POST:
        extended_price = _num(info.get("postMarketPrice"))
        extended_label = "애프터장"
    else:
        # 장 마감 상태에서도 마지막 애프터장 가격이 남아 있는 경우가 있습니다.
        post = _num(info.get("postMarketPrice"))
        pre = _num(info.get("preMarketPrice"))
        if pre is not None:
            extended_price, extended_label = pre, "프리장"
        elif post is not None:
            extended_price, extended_label = post, "애프터장"

    extra: dict = {}
    for key, label in (
        ("trailingPE", "per"),
        ("forwardPE", "forward_per"),
        ("marketCap", "market_cap"),
        ("fiftyTwoWeekHigh", "high_52w"),
        ("fiftyTwoWeekLow", "low_52w"),
    ):
        val = _num(info.get(key))
        if val is not None:
            extra[label] = val

    # 실적 발표 예정일 — 변화 감지에서 D-day 로 씁니다.
    # 야후는 버전·종목에 따라 여러 필드에 담아 주므로 순서대로 시도합니다.
    earnings = _num(info.get("earningsTimestampStart")) or _num(info.get("earningsTimestamp"))
    if earnings:
        extra["earnings_date"] = earnings          # epoch 초 (signals 가 날짜로 변환)
    else:
        raw_dates = info.get("earningsDate")
        if isinstance(raw_dates, list) and raw_dates:
            first = _num(raw_dates[0])
            if first:
                extra["earnings_date"] = first

    return Quote(
        symbol=symbol,
        price=price,
        prev_close=prev,
        currency=currency,
        status=status,
        extended_price=extended_price,
        extended_label=extended_label,
        extra=extra,
    )


def _fetch_light(symbol: str) -> Quote:
    """가격과 전일 종가만 — 일봉 5일 한 번.

    .info 는 종목 하나에 상세정보 수십 항목(요청 여러 번)을 받아 오는
    무거운 호출입니다. 지수·환율·금리·선물은 가격과 전일 종가면 충분해서
    일봉 요청 하나로 줄입니다. 실패하면 원래 방식(_fetch_one)으로 받습니다.
    프리·애프터장 가격과 장 상태는 이 경로에서 나오지 않습니다.
    """
    yf = _import_yfinance()
    price, prev = _from_history(yf.Ticker(symbol), symbol)
    if price is None:
        return _fetch_one(symbol)
    return Quote(symbol=symbol, price=price, prev_close=prev,
                 status=MarketStatus.UNKNOWN, extra={"light": True})


def fetch_quotes(symbols: list[str], *, light: tuple[str, ...] | set = ()
                 ) -> dict[str, Quote]:
    """심볼 목록을 병렬 조회합니다.

    light 에 든 심볼은 가격만 가볍게 받습니다 (_fetch_light). 관심종목처럼
    프리장 가격 · 52주 고저 · 실적 발표일이 필요한 것은 넣지 마십시오.
    """
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return {}
    light = set(light or ())

    def safe(sym: str) -> Quote:
        try:
            return _fetch_light(sym) if sym in light else _fetch_one(sym)
        except Exception as exc:  # noqa: BLE001
            return Quote.failed(sym, f"조회 중 예외: {exc}")

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        results = list(pool.map(safe, unique))

    return dict(zip(unique, results))


def fetch_fundamentals(symbols: list[str], fields: tuple[tuple[str, str, str], ...]) -> dict[str, dict]:
    """밸류에이션 표용 펀더멘털 지표를 가져옵니다.

    반환: {symbol: {yahoo_field: value|None, "_error": str|None}}
    """
    yf = _import_yfinance()
    unique = list(dict.fromkeys(s for s in symbols if s))
    wanted = [f[0] for f in fields]

    def one(sym: str) -> dict:
        try:
            info = yf.Ticker(sym).info
            if not isinstance(info, dict):
                return {"_error": "info 응답이 dict 가 아닙니다."}
            row: dict = {"_error": None, "_name": info.get("shortName") or sym}
            for key in wanted:
                row[key] = _num(info.get(key))
            return row
        except Exception as exc:  # noqa: BLE001
            return {"_error": f"{exc}"}

    if not unique:
        return {}

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        rows = list(pool.map(one, unique))

    return dict(zip(unique, rows))


def fetch_market_cap(symbol: str) -> float | None:
    """시가총액 하나. 역DCF 의 외부 입력값입니다.

    `.info` 는 느리고 자주 깨지므로 `fast_info` 를 먼저 봅니다.
    한국 종목은 `005930.KS` 형태로 바꿔서 조회합니다 — 숫자 6자리면
    코스피로 가정하고, 실패하면 코스닥(`.KQ`)을 시도합니다.
    """
    candidates = [symbol]
    if symbol.isdigit() and len(symbol) == 6:
        candidates = [f"{symbol}.KS", f"{symbol}.KQ"]

    for candidate in candidates:
        try:
            ticker = _import_yfinance().Ticker(candidate)
        except Exception:  # noqa: BLE001
            continue

        for getter in (
            lambda t: getattr(t.fast_info, "market_cap", None),
            lambda t: (t.info or {}).get("marketCap"),
        ):
            try:
                value = getter(ticker)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 일봉 — 국내 변동성 스크리너용
# ──────────────────────────────────────────────────────────────────────────────

def _last_index_date(hist) -> str:
    """일봉 표의 마지막 줄 날짜 ('YYYY-MM-DD', 못 읽으면 '')."""
    try:
        last = hist.index[-1]
        return str(last.date() if hasattr(last, "date") else last)[:10]
    except Exception:  # noqa: BLE001
        return ""


def fetch_closes(symbols: list[str], *, period: str = "1y",
                 volumes: dict[str, list[float]] | None = None,
                 dates: dict[str, str] | None = None,
                 ) -> tuple[dict[str, list[float]], dict[str, str]]:
    """심볼마다 일봉 종가 목록을 가져옵니다.

    반환: ({심볼: [종가…]}, {심볼: 오류})
    volumes 에 dict 를 넘기면 {심볼: [거래량…]} 로 채워 줍니다 —
    거래대금(종가×거래량) 으로 유동성 바닥을 거르는 데 씁니다.

    **한 종목에 심볼 후보가 여럿일 수 있습니다.** 국내 코드는 코스피(.KS)
    인지 코스닥(.KQ)인지 코드만 봐서는 모르므로, 호출하는 쪽이 후보를
    순서대로 넣고 먼저 값이 오는 것을 씁니다 — 여기서는 심볼 하나를
    심볼 하나로만 다루고, 그 선택은 kr_screen 쪽에서 합니다.

    실패를 예외로 올리지 않는 이유: 30종목 중 한둘이 비는 건 정상이고,
    그 때문에 화면 전체가 멈추면 안 됩니다.
    """
    yf = _import_yfinance()
    unique = list(dict.fromkeys(s for s in symbols if s))
    out: dict[str, list[float]] = {}
    errors: dict[str, str] = {}
    # 거래량은 호출하는 쪽이 dict 를 넘기면 채워 줍니다. 반환값을 늘리면
    # 기존 호출부가 전부 깨지므로 선택 인자로 둡니다.
    if volumes is None:
        volumes = {}

    def one(sym: str) -> tuple[str, list[float], list[float], str]:
        try:
            hist = yf.Ticker(sym).history(period=period, interval="1d",
                                          auto_adjust=True)
            if hist is None or hist.empty or "Close" not in hist:
                return sym, [], [], "일봉이 비어 있습니다."
            if dates is not None:
                dates[sym] = _last_index_date(hist)
            rows = list(zip(hist["Close"].tolist(),
                            (hist["Volume"].tolist()
                             if "Volume" in hist
                             else [0] * len(hist))))
            closes, vols = [], []
            for close, vol in rows:
                if close is None or (isinstance(close, float)
                                     and close != close):
                    continue
                closes.append(float(close))
                try:
                    vols.append(float(vol or 0.0))
                except (TypeError, ValueError):
                    vols.append(0.0)
            return (sym, closes, vols,
                    "" if closes else "유효한 종가가 없습니다.")
        except Exception as exc:  # noqa: BLE001
            return sym, [], [], f"{type(exc).__name__}: {exc}"

    if not unique:
        return out, errors
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        for sym, closes, vols, err in pool.map(one, unique):
            if closes:
                out[sym] = closes
                volumes[sym] = vols
            if err:
                errors[sym] = err
    return out, errors


def fetch_ohlc(symbols: list[str], *, period: str = "1y"
               ) -> tuple[dict[str, dict[str, list[float]]], dict[str, str]]:
    """심볼마다 일봉 고가·저가·종가. 차트 조건(일목·CCI·DMI)용.

    반환: ({심볼: {"high","low","close","volume"}}, {심볼: 오류})

    **수정주가를 쓰지 않습니다** (auto_adjust=False). 수정주가는 종가만이
    아니라 고가·저가도 배당만큼 깎는데, 차트 지표는 HTS 에 보이는 가격
    으로 계산하는 것이 관행이라 화면의 숫자가 HTS 와 맞아야 합니다.
    액면분할은 야후가 이 설정에서도 반영합니다.
    """
    yf = _import_yfinance()
    unique = list(dict.fromkeys(s for s in symbols if s))
    out: dict[str, dict[str, list[float]]] = {}
    errors: dict[str, str] = {}

    def one(sym: str):
        try:
            hist = yf.Ticker(sym).history(period=period, interval="1d",
                                          auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist:
                return sym, None, "일봉이 비어 있습니다."
            d: dict[str, list[float]] = {"high": [], "low": [], "close": [],
                                         "volume": []}
            vols = (hist["Volume"].tolist() if "Volume" in hist
                    else [0.0] * len(hist))
            for hi, lo, cl, vo in zip(hist["High"].tolist(), hist["Low"].tolist(),
                                      hist["Close"].tolist(), vols):
                if cl is None or cl != cl or cl <= 0:
                    continue
                hi = cl if (hi is None or hi != hi or hi <= 0) else hi
                lo = cl if (lo is None or lo != lo or lo <= 0) else lo
                d["high"].append(max(float(hi), float(cl)))
                d["low"].append(min(float(lo), float(cl)))
                d["close"].append(float(cl))
                d["volume"].append(0.0 if (vo is None or vo != vo) else float(vo))
            if d["close"]:
                d["last_date"] = _last_index_date(hist)   # 문자열
            return sym, (d if d["close"] else None), (
                "" if d["close"] else "유효한 종가가 없습니다.")
        except Exception as exc:  # noqa: BLE001
            return sym, None, f"{type(exc).__name__}: {exc}"

    if not unique:
        return out, errors
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        for sym, d, err in pool.map(one, unique):
            if d:
                out[sym] = d
            if err:
                errors[sym] = err
    return out, errors


def fetch_daily_bars(symbols: list[str], *, period: str = "1mo"
                     ) -> tuple[dict[str, list[tuple[str, float]]], dict[str, str]]:
    """심볼마다 (거래일, 종가) 목록 — 전일 장 브리핑용.

    날짜는 **거래소 현지 날짜**입니다 (야후가 봉마다 거래소 시간대로 줍니다).
    '마지막으로 끝난 거래일' 을 가리려면 날짜가 꼭 있어야 해서,
    종가만 주는 fetch_closes 와 따로 둡니다.
    """
    yf = _import_yfinance()
    unique = list(dict.fromkeys(s for s in symbols if s))
    out: dict[str, list[tuple[str, float]]] = {}
    errors: dict[str, str] = {}

    def one(sym: str):
        try:
            hist = yf.Ticker(sym).history(period=period, interval="1d",
                                          auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist:
                return sym, [], "일봉이 비어 있습니다."
            bars = []
            for ts, cl in zip(hist.index, hist["Close"].tolist()):
                if cl is None or cl != cl or cl <= 0:
                    continue
                day = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
                bars.append((day, float(cl)))
            return sym, bars, "" if bars else "유효한 종가가 없습니다."
        except Exception as exc:  # noqa: BLE001
            return sym, [], f"{type(exc).__name__}: {exc}"

    if not unique:
        return out, errors
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        for sym, bars, err in pool.map(one, unique):
            if bars:
                out[sym] = bars
            if err:
                errors[sym] = err
    return out, errors
