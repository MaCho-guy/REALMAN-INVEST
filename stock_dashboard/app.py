"""
실시간 주식 대시보드 — Streamlit 앱.

실행:
    streamlit run app.py

구성:
  상단 탭      섹션 전환 (관심종목 / 밸류에이션 / 공시 분석 / DEX 선물 / …)
  설정 패널   등락 색상, 갱신, 환율 — 페이지 상단
  카드 제목    클릭하면 야후·네이버·Hyperliquid 해당 종목 페이지로 이동

jusikbot.com 의 정보 구조를 참고했으나 UI·코드는 전부 직접 작성한 것입니다.
이 앱은 정보 제공용이며 투자 판단의 근거가 아닙니다.
"""

from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

from concurrent.futures import ThreadPoolExecutor

import streamlit as st


def _missing_files() -> list[str]:
    """BUILD.json 에 있는데 서버에 없는 .py 파일.

    모듈 하나가 빠지면 아래 import 에서 바로 죽고, 스트림릿 클라우드는 오류
    내용을 가립니다('redacted'). 그래서 import **전에** 파일 목록부터 대조해
    무엇이 빠졌는지 화면에 적고 멈춥니다. BUILD.json 이 없으면 검사를
    건너뜁니다 (그때는 원래 오류가 그대로 납니다).
    """
    import json  # noqa: PLC0415

    base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "BUILD.json"), encoding="utf-8") as fh:
            names = list(json.load(fh))
    except Exception:  # noqa: BLE001
        return []
    return sorted(n for n in names if n.endswith(".py")
                  and not os.path.exists(os.path.join(base, n)))


_MISSING = _missing_files()
if _MISSING:
    st.error(
        "**올라가지 않은 파일이 있어 앱을 시작할 수 없습니다.**\n\n"
        + "\n".join(f"- `{n}`" for n in _MISSING)
        + "\n\n받은 **전체 패키지 zip** 을 `stock_dashboard/` 에 풀어 "
          "통째로 덮어쓰십시오. 파일 하나만 빠져도 그 파일을 쓰는 모든 "
          "화면이 멈춥니다.")
    st.stop()

import swr  # noqa: E402

# 저장된 값이 있으면 **묵었어도 먼저** 그리고 뒤에서 새로 받습니다 (이틀까지).
# 휴대폰으로 가끔 열면 값이 매번 stale 을 넘겨 있어서 열 때마다 처음처럼
# 기다렸습니다. 묵은 값을 보여줄 때는 화면 위에 '몇 분 전 값' 이라고 적고,
# 새 값이 오면 화면을 한 번 자동으로 다시 그립니다 (_refresh_watch).
swr.HARD_STALE = 2 * 86_400

import brief
import buildstamp
import briefing_store as bfs
import inflation
import kr_screen
import sector_heat
import chart_signals
import daily_brief
import calendar_events
import portfolio
import flows
import dividends
import earnings
import perf
import threading
import time
import liquidity
import value as vl
import analysis_store
import components as ui
import config
import cycle
import buffett
import buffett_kr
import demo as demo_mod
import macro as macro_mod
import reverse_dcf as rdcf
import runner
import summary as sm
import verdict as vd
import signals as sig_mod
import compute
from compute import compute_premium, pick_quote, resolve_fx
from config import Section
from sources import (
    dart, edgar, edgar_facts, edgar_xbrl, feargreed, fred, hyperliquid,
    naver, news, research, vix, yahoo,
)
from sources.model import Quote
from theme import build_css

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_PATH = os.path.join(BASE_DIR, config.ANALYSIS_DIR)
BRIEFING_PATH = os.path.join(BASE_DIR, config.BRIEFING_DIR)


# ──────────────────────────────────────────────────────────────────────────────
# 데이터 로딩
# ──────────────────────────────────────────────────────────────────────────────

def _any_quote_ok(payload) -> bool:
    """시세를 하나라도 받았는가. 전부 실패한 결과가 좋은 직전 값을 덮지 않게."""
    try:
        return any(q.ok for bucket in payload.values() for q in bucket.values())
    except Exception:  # noqa: BLE001
        return False


# ──────────────────────────────────────────────────────────────────────────────
# 저장 방식 — swr.py (2026-11-11)
#
# 아래 로더는 전부 st.cache_data 대신 swr.cached 를 씁니다. 저장 시간이
# 지나도 **직전 값을 바로 보여주고 뒤에서 새로 받습니다** — 1분 지난 시세
# 때문에 화면이 멈추지 않습니다. 받은 값은 임시 폴더에도 남겨, 앱이 다시
# 켜져도 처음부터 받지 않습니다. 로더 안에서 st 를 부르지 않으므로 작업
# 스레드에서 미리 받아 둘 수 있습니다 (_warm_market).
# ──────────────────────────────────────────────────────────────────────────────

@swr.cached(config.CACHE_TTL_SEC, stale=1_800, keep=_any_quote_ok)
def load_all(use_demo: bool) -> dict[str, dict[str, Quote]]:
    """모든 소스에서 시세를 모읍니다. 소스별 실패는 격리됩니다."""
    if use_demo:
        return demo_mod.demo_payload()

    payload: dict[str, dict[str, Quote]] = {"yahoo": {}, "naver": {}, "hyperliquid": {}}
    jobs = (
        ("yahoo", yahoo.fetch_quotes, config.live_symbols("yahoo")),
        ("naver", naver.fetch_quotes, config.live_symbols("naver")),
        ("hyperliquid", hyperliquid.fetch_quotes, config.live_symbols("hyperliquid")),
    )

    light = set(config.light_yahoo_symbols())

    def one(job):
        bucket, fetch, symbols = job
        try:
            if bucket == "yahoo":
                return bucket, fetch(symbols, light=light)
            return bucket, fetch(symbols)
        except Exception as exc:  # noqa: BLE001
            return bucket, {
                s: Quote.failed(s, f"{bucket} 소스 전체 실패: {exc}") for s in symbols
            }

    # 세 소스는 서로 기다릴 이유가 없습니다 — 전에는 야후 → 네이버 →
    # 하이퍼리퀴드를 차례로 기다렸습니다.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for bucket, got in pool.map(one, jobs):
            payload[bucket] = got
    return payload


@swr.cached(600)
def load_fundamentals(use_demo: bool) -> dict[str, dict]:
    """밸류에이션 지표는 자주 바뀌지 않으므로 캐시를 10분으로 둡니다."""
    symbols = [sym for _label, sym in config.VALUATION_TICKERS]
    if use_demo:
        return demo_mod.demo_fundamentals(symbols, config.VALUATION_FIELDS)
    try:
        return yahoo.fetch_fundamentals(symbols, config.VALUATION_FIELDS)
    except Exception as exc:  # noqa: BLE001
        return {s: {"_error": str(exc)} for s in symbols}


@swr.cached(config.EDGAR_CACHE_TTL_SEC)
def load_filings(use_demo: bool) -> tuple[dict[str, list], dict[str, str]]:
    """EDGAR 공시. 캐시가 길어 화면을 그릴 때마다 요청하지 않습니다."""
    if use_demo:
        return demo_mod.demo_filings(), {}
    tickers = config.edgar_tickers()
    if not tickers:
        return {}, {}
    try:
        return edgar.fetch_for_tickers(
            tickers,
            config.EDGAR_USER_AGENT,
            cik_overrides=config.EDGAR_CIK_OVERRIDES,
            limit=config.EDGAR_FILING_LIMIT,
        )
    except Exception as exc:  # noqa: BLE001
        return {}, {t: f"EDGAR 조회 실패: {exc}" for t in tickers}


@swr.cached(config.DART_MAP_CACHE_TTL_SEC)
def load_corp_codes() -> tuple[dict, str]:
    """종목코드 → DART 고유번호 매핑. (매핑, 오류메시지)"""
    try:
        return dart.fetch_corp_codes(), ""
    except dart.DartKeyMissing as exc:
        return {}, str(exc)
    except Exception as exc:  # noqa: BLE001
        return {}, f"DART 고유번호 조회 실패: {exc}"


@swr.cached(config.DART_CACHE_TTL_SEC)
def load_dart_disclosures(use_demo: bool,
                          key_fp: str = "") -> tuple[dict[str, list], dict[str, str]]:
    """국내 공시 목록.

    key_fp 는 **쓰지 않습니다.** 캐시 키를 바꾸려고만 받습니다 —
    Secrets 에 DART 키를 넣는 순간 지문이 달라져 캐시가 자동으로
    무효화됩니다. 없으면 키 없이 실패한 결과가 TTL 동안 그대로
    남아서, 키를 넣어도 바뀌지 않습니다.
    """
    """한국 종목 공시. 키가 없으면 빈 결과 + 안내 메시지."""
    codes = config.dart_stock_codes()
    if use_demo:
        return demo_mod.demo_dart_disclosures(), {}
    if not codes:
        return {}, {}

    corp_map, map_err = load_corp_codes()
    if map_err:
        return {}, {"DART": map_err}

    out: dict[str, list] = {}
    errors: dict[str, str] = {}
    for code in codes:
        corp = dart.resolve_corp_code(code, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if corp is None:
            errors[code] = f"'{code}' 의 DART 고유번호를 찾지 못했습니다."
            continue
        try:
            out[code] = dart.fetch_disclosures(
                corp,
                since_days=config.DART_DISCLOSURE_DAYS,
                limit=config.DART_DISCLOSURE_LIMIT,
            )
        except dart.DartError as exc:
            errors[code] = str(exc)
    return out, errors


@swr.cached(config.DART_FINANCIALS_CACHE_TTL_SEC)
def load_us_inventory_trends(use_demo: bool) -> tuple[dict[str, object], dict[str, str]]:
    """미국 기업 재고 지표 — EDGAR XBRL. 키가 필요 없습니다."""
    if use_demo:
        return demo_mod.demo_us_inventory_trends(), {}

    tickers = list(config.CYCLE_US_TICKERS)
    if not tickers:
        return {}, {}

    trends: dict[str, object] = {}
    errors: dict[str, str] = {}

    try:
        ticker_map = edgar.fetch_ticker_map(config.EDGAR_USER_AGENT)
    except Exception as exc:  # noqa: BLE001
        return {}, {t: f"CIK 매핑 실패: {exc}" for t in tickers}

    for ticker in tickers:
        cik = config.EDGAR_CIK_OVERRIDES.get(ticker) or ticker_map.get(ticker.upper())
        if cik is None:
            errors[ticker] = f"'{ticker}' 의 CIK 를 찾지 못했습니다."
            continue

        collected: dict[str, list] = {}
        warnings: list[str] = []
        for key in ("inventory", "cost_of_sales", "revenue"):
            try:
                tag, facts = edgar_xbrl.fetch_first_available(
                    cik, cycle.XBRL_TAGS[key], config.EDGAR_USER_AGENT)
                collected[key] = facts
            except edgar_xbrl.XbrlError as exc:
                collected[key] = []
                warnings.append(f"{key}: {exc}")

        if not collected.get("inventory") or not collected.get("cost_of_sales"):
            errors[ticker] = (
                f"{ticker} 재고·매출원가를 가져오지 못했습니다."
                + (f" ({warnings[0]})" if warnings else "")
            )
            continue

        name = next((i.name for i in config.SECTION_WATCHLIST.instruments
                     if i.symbol == ticker), ticker)
        trends[ticker] = cycle.build_trend_from_xbrl(
            name, ticker,
            collected["inventory"], collected["cost_of_sales"],
            collected.get("revenue") or [],
            quarters=config.CYCLE_XBRL_QUARTERS,
            errors=warnings,
        )

    return trends, errors


@swr.cached(config.DART_FINANCIALS_CACHE_TTL_SEC)
def load_inventory_trends(use_demo: bool, key_fp: str = "") -> tuple[dict[str, object], dict[str, str]]:
    """재고 지표(레이어 2). 분기별 재무제표를 모아 추세로 만듭니다."""
    if use_demo:
        return demo_mod.demo_inventory_trends(), {}

    instruments = config.cycle_instruments()
    if not instruments:
        return {}, {}

    corp_map, map_err = load_corp_codes()
    if map_err:
        return {}, {"DART": map_err}

    trends: dict[str, object] = {}
    errors: dict[str, str] = {}

    for inst in instruments:
        corp = dart.resolve_corp_code(
            inst.symbol, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if corp is None:
            errors[inst.symbol] = f"'{inst.symbol}' 의 DART 고유번호를 찾지 못했습니다."
            continue

        collected: list[tuple[int, str, str, list]] = []
        warnings: list[str] = []
        year, quarter = dart.latest_available_quarter()

        for _ in range(config.CYCLE_QUARTERS_BACK):
            try:
                accounts = dart.fetch_financials(
                    corp, year, quarter, fs_div=config.CYCLE_FS_DIV)
                if accounts:
                    collected.append((year, quarter, config.CYCLE_FS_DIV, accounts))
            except dart.DartError as exc:
                # 013(데이터 없음)은 정상 — 아직 공시 안 된 분기입니다
                if "조회된 데이터가 없습니다" not in str(exc):
                    warnings.append(f"{year} {quarter}: {exc}")
            year, quarter = dart.previous_quarter(year, quarter)

        if not collected:
            errors[inst.symbol] = (
                f"{inst.name} 의 재무제표를 가져오지 못했습니다."
                + (f" ({warnings[0]})" if warnings else "")
            )
            continue

        trends[inst.symbol] = cycle.build_trend(
            inst.name, inst.symbol, collected, warnings)

    return trends, errors


@swr.cached(config.NEWS_CACHE_TTL_SEC)
def load_news(targets: tuple[tuple[str, str, str], ...], use_demo: bool) -> dict[str, list]:
    """신호가 잡힌 종목에만 헤드라인을 붙입니다."""
    if not targets:
        return {}
    if use_demo:
        return demo_mod.demo_news([t[0] for t in targets])
    try:
        return news.fetch_for_many(list(targets), limit=config.NEWS_PER_TICKER)
    except Exception:  # noqa: BLE001 - 뉴스는 보조이므로 조용히 비웁니다
        return {}


@swr.cached(3_600)
def load_chart_rows(market: str, use_demo: bool):
    """차트 조건 — 후보의 1년 일봉(고·저·종) → 종목별 지표 한 줄.

    한국은 네이버 먼저, 못 받은 종목만 야후(.KS/.KQ). 미국은 야후.
    일봉은 하루 한 번 바뀌므로 1시간 저장합니다. 장중에는 오늘 봉이
    아직 완성되지 않은 값이라, 지표도 장 마감 뒤에 확정됩니다.
    """
    cands = config.chart_candidates(market)
    if use_demo:
        ohlc, errs = demo_mod.demo_chart_ohlc(cands)
        return chart_signals.build_rows(cands, ohlc, errs)
    ohlc: dict = {}
    errs: dict[str, str] = {}
    if market == "kr":
        codes = [c for c, _n in cands]
        ohlc, nerr = naver.fetch_ohlc_many(codes)
        missing = [c for c in codes if c not in ohlc]
        yahoo_note = "야후도 비었음"
        if missing:
            try:
                got, _ye = yahoo.fetch_ohlc(
                    kr_screen.all_symbols([(c, "") for c in missing]))
            except Exception as exc:  # noqa: BLE001
                got, yahoo_note = {}, f"야후도 실패: {type(exc).__name__}"
            for code in missing:
                for sym in kr_screen.yahoo_symbols(code):
                    if got.get(sym):
                        ohlc[code] = got[sym]
                        break
        errs = {c: f"{nerr.get(c, '네이버 실패')} → {yahoo_note}"
                for c in codes if c not in ohlc}
    else:
        try:
            ohlc, errs = yahoo.fetch_ohlc([t for t, _n in cands])
        except Exception as exc:  # noqa: BLE001
            errs = {t: f"야후 일봉 실패: {exc}" for t, _n in cands}
    return chart_signals.build_rows(cands, ohlc, errs)


@swr.cached(900)
def load_daily_brief(market: str, use_demo: bool):
    """전일 장 브리핑 — 지수·업종 ETF·보유 종목의 최근 한 달 일봉.

    15분 저장. '끝난 거래일' 판정이 현재 시각에 달려 있어서(장 마감 전후로
    결과가 바뀝니다) 길게 저장하면 마감 뒤에도 그 전날을 보여줍니다.
    """
    spec = config.daily_brief_spec(market)
    now = dt.datetime.now(KST)
    if use_demo:
        today = now.astimezone(ZoneInfo(spec["tz"])).date().isoformat()
        bars, errs = demo_mod.demo_daily_bars(market, today)
    else:
        try:
            bars, errs = yahoo.fetch_daily_bars(config.daily_brief_symbols(market))
        except Exception as exc:  # noqa: BLE001
            bars, errs = {}, {s_: f"{type(exc).__name__}: {exc}"
                              for s_, _l in spec["indices"]}
    return daily_brief.build(market, spec, bars, now, errs)


@swr.cached(1_800)
def load_close_headlines(use_demo: bool):
    """한국장·미국장 마감 기사 제목 (구글 뉴스). {키: [Headline]}."""
    specs = tuple(config.DAILY_BRIEF[m]["news"] for m in config.DAILY_BRIEF)
    if use_demo:
        return demo_mod.demo_sector_news(specs + (("_", "_", "_"),))[0]
    try:
        return news.fetch_sector_news(specs, limit=3)[0]
    except Exception:  # noqa: BLE001 - 기사는 보조입니다
        return {}


@swr.cached(1_800)
def load_research(kind: str, use_demo: bool):
    """증권사 리포트 목록 (산업분석 / 시황정보). (목록, 오류)."""
    if use_demo:
        ind, mk = demo_mod.demo_research()
        return (ind if kind == "industry" else mk), ""
    try:
        return research.fetch(
            kind, pages=config.RESEARCH_PAGES if kind == "industry" else 1)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"


@swr.cached(21_600)
def load_release_dates(use_demo: bool, key_fp: str = ""):
    """FRED 발표 일정 (앞으로 60일). (응답, 오류). 하루에 몇 번 바뀌지 않습니다."""
    if use_demo:
        return demo_mod.demo_fred_release_dates(), ""
    try:
        return fred.fetch_release_dates(60), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


@swr.cached(86_400)
def load_sector_names(pairs: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """ETF 이름 — 코드 검증용. 이름은 바뀌지 않으므로 하루 동안 저장합니다.

    전에는 30분마다 일봉과 함께 14번 더 불렀습니다. 야후의 .info 는
    종목당 1초 안팎이라 섹터 온도를 여는 시간의 큰 몫이었습니다.
    """
    names: dict[str, str] = {}
    try:
        info = yahoo.fetch_fundamentals([sym for _c, sym in pairs], ())
        for code, sym in pairs:
            names[code] = str((info.get(sym) or {}).get("_name") or "")
            if names[code] == sym:      # 이름을 못 받으면 심볼을 돌려줍니다
                names[code] = ""
    except Exception:  # noqa: BLE001 - 이름은 검증용이라 없어도 됩니다
        pass
    return names


@swr.cached(1_800)
def load_sector_heat(use_demo: bool):
    """KODEX 업종 ETF 14개 → 섹터 온도.

    일봉은 장중에도 1일 수익률이 바뀌므로 캐시를 30분으로 둡니다.
    이름(야후 shortName)은 코드 검증용이라 같이 받습니다 — 한 번 더
    호출하는 비용(14회)이 들지만, 틀린 코드를 조용히 쓰는 것보다 낫습니다.
    """
    specs = config.KR_SECTOR_ETFS
    if use_demo:
        return demo_mod.demo_sector_heat(specs)
    syms = {s[0]: f"{s[0]}.KS" for s in specs}
    try:
        closes_by_sym, errs = yahoo.fetch_closes(list(syms.values()))
    except Exception as exc:  # noqa: BLE001
        return [sector_heat.SectorRow(code=s[0], label=s[1],
                                      error=f"일봉 실패: {exc}")
                for s in specs]
    names = load_sector_names(tuple(syms.items()))
    closes = {code: closes_by_sym.get(sym) or [] for code, sym in syms.items()}
    errors = {code: errs.get(sym, "") for code, sym in syms.items()}
    return sector_heat.build(specs, closes, names, errors)


@swr.cached(3_600)
def load_kr_vol_profiles(use_demo: bool):
    """국내 후보(코스피 + 코스닥)의 1년 일봉 → 변동성 프로파일.

    **네이버 먼저, 실패한 종목만 야후.** 전에는 야후만 썼는데 코스피/
    코스닥 접미사를 몰라 종목마다 두 번씩(최대 80회) 불렀고, 클라우드에서
    야후가 막히면 전부 비어 '0건' 이 됐습니다. 오류 사전에는 출처를 같이
    적어 화면의 '걸러진 단계' 표가 원인을 말할 수 있게 합니다.
    """
    cands = list(config.screen_kr_candidates())
    if use_demo:
        return demo_mod.demo_kr_vol_profiles(cands), {}
    codes = [c for c, _n in cands]
    closes, vols, nerr = naver.fetch_daily_many(codes)
    missing = [c for c in codes if c not in closes]
    yerr: dict[str, str] = {}
    if missing:
        yvols: dict[str, list[float]] = {}
        try:
            ycl, _ye = yahoo.fetch_closes(
                kr_screen.all_symbols([(c, "") for c in missing]), volumes=yvols)
        except Exception as exc:  # noqa: BLE001
            ycl, yerr = {}, {c: f"야후도 실패: {exc}" for c in missing}
        for code in missing:
            for sym in kr_screen.yahoo_symbols(code):
                if ycl.get(sym):
                    closes[code], vols[code] = ycl[sym], yvols.get(sym) or []
                    break
    profiles, errors = [], {}
    for code, name in cands:
        if code not in closes:
            errors[code] = (f"{nerr.get(code, '네이버 실패')} → "
                            f"{yerr.get(code, '야후도 비었음')}")
            continue
        prof = kr_screen.profile(code, name, closes[code], vols.get(code))
        profiles.append(prof)
        if prof.error:
            errors[code] = prof.error
    return profiles, errors


@swr.cached(3_600)
def load_kr_value_rows(use_demo: bool):
    """국내 후보의 PBR · PER · 배당수익률.

    **네이버 투자지표 먼저, 빈 종목만 야후.** 야후 .info 는 국내 종목의
    PER·PBR 을 자주 비워 두고, 종목당 1~2초라 50종목이면 느립니다.
    두 출처 모두 '집계값' 이라 기준 시점이 다를 수 있습니다 — 화면에
    그렇게 적습니다.
    """
    cands = list(config.screen_kr_candidates())
    if use_demo:
        return demo_mod.demo_kr_value_rows(cands)
    nav = naver.fetch_valuation_many([c for c, _n in cands])
    rows: list = []
    need_yahoo = []
    for code, name in cands:
        got = nav.get(code) or {}
        if got.get("error") == "" :
            rows.append(kr_screen.ValueRow(
                ticker=code, name=name, pbr=got.get("pbr"), per=got.get("per"),
                div_yield=got.get("div_yield")))
        else:
            need_yahoo.append((code, name, got.get("error") or "네이버 실패"))
    if not need_yahoo:
        return rows
    cands = [(c, n) for c, n, _e in need_yahoo]
    nerr = {c: e for c, _n, e in need_yahoo}
    fields = (("priceToBook", "PBR", "num2"),
              ("trailingPE", "PER", "num2"),
              ("dividendYield", "배당수익률", "pct"))
    syms: list[str] = []
    for code, _n in cands:
        syms.extend(kr_screen.yahoo_symbols(code))
    try:
        raw = yahoo.fetch_fundamentals(syms, fields)
    except Exception as exc:  # noqa: BLE001
        return rows + [kr_screen.ValueRow(c, n, error=f"{nerr[c]} → 야후 실패: {exc}")
                       for c, n in cands]
    for code, name in cands:
        got = {}
        for sym in kr_screen.yahoo_symbols(code):
            cell = raw.get(sym) or {}
            if cell.get("_error") is None and any(
                    cell.get(k) is not None for k in
                    ("priceToBook", "trailingPE", "dividendYield")):
                got = cell
                break
        dy = got.get("dividendYield")
        # 야후는 배당수익률을 0.025(비율) 로 줄 때와 2.5(%) 로 줄 때가
        # 둘 다 있습니다. 1 미만이면 비율로 보고 100 을 곱합니다.
        if dy is not None and dy < 1.0:
            dy *= 100.0
        rows.append(kr_screen.ValueRow(
            ticker=code, name=name,
            pbr=got.get("priceToBook"), per=got.get("trailingPE"),
            div_yield=dy,
            error="" if got else f"{nerr[code]} → 야후도 비었음",
        ))
    return rows


@swr.cached(3_600)
def load_inflation(use_demo: bool, key_fp: str = ""):
    """물가 계열 → 속도 분석. 월 1회 발표라 캐시를 1시간으로 둡니다."""
    specs = config.INFLATION_SERIES
    if use_demo:
        return demo_mod.demo_inflation(specs), {}
    series, errors = fred.fetch_many([sid for sid, _l, _sa in specs], years=3)
    out = []
    for sid, label, sa in specs:
        ser = series.get(sid)
        if ser is None:
            out.append(inflation.Reading(
                key=sid, label=label, seasonally_adjusted=sa,
                error=errors.get(sid, "계열을 받지 못했습니다.")))
            continue
        pts = [(o.date.isoformat(), o.value) for o in ser.observations]
        out.append(inflation.build(sid, label, pts, seasonally_adjusted=sa))
    return out, errors


@swr.cached(3_600)
def load_liquidity(use_demo: bool, key_fp: str = ""):
    """순유동성 + 참고 계열."""
    if use_demo:
        return demo_mod.demo_liquidity()
    ids = [sid for _k, sid, _l, _u in config.LIQUIDITY_SERIES]
    ids += [row[0] for row in config.LIQUIDITY_EXTRA]
    series, errors = fred.fetch_many(ids, years=2)

    def comp(key, sid, label, unit):
        ser = series.get(sid)
        if ser is None or not ser.observations:
            return liquidity.Component(
                key=key, label=label, unit=unit,
                error=errors.get(sid, f"{sid} 를 받지 못했습니다."))
        obs = ser.observations
        # 4주 전 — 주간 계열이면 4개 전, 일간이면 20개 전쯤입니다.
        back = 4 if len(obs) < 200 else 20
        prev = obs[-back].value if len(obs) > back else None
        return liquidity.Component(
            key=key, label=label, unit=unit, raw=obs[-1].value,
            period=obs[-1].date.isoformat(), prev=prev)

    parts = [comp(k, sid, lab, u)
             for k, sid, lab, u in config.LIQUIDITY_SERIES]
    nl = liquidity.net_liquidity(*parts)

    # 참고 계열도 **단위를 검사합니다.** 전에는 검사 없이 그대로 찍어서,
    # 단위가 틀리면 조용히 이상한 숫자가 나갔습니다 (TGA 가 그랬습니다).
    extra = []
    for sid, label, unit, currency, lo, hi in config.LIQUIDITY_EXTRA:
        ser = series.get(sid)
        if ser is None or not ser.observations:
            extra.append((label, "—", (errors.get(sid) or "받지 못함")[:44]))
            continue
        obs = ser.observations[-1]
        c = liquidity.Component(key=sid, label=label, unit=unit,
                                raw=obs.value, currency=currency,
                                sane_range=(lo, hi))
        problem = c.sanity()
        if problem:
            extra.append((label, "— (단위 확인 필요)", problem[:120]))
            continue
        extra.append((label, f"{c.billions / 1000:,.2f}조 {currency}",
                      obs.date.isoformat()))
    return nl, extra


@swr.cached(3_600)
def load_kr_macro(use_demo: bool, key_fp: str = ""):
    """한국 경제지표 (FRED 경유). 계열 ID 는 전부 미검증입니다."""
    if use_demo:
        return demo_mod.demo_kr_macro(config.KR_MACRO_SERIES)
    series, errors = fred.fetch_many(
        [sid for sid, _l in config.KR_MACRO_SERIES], years=3)
    rows = []
    for sid, label in config.KR_MACRO_SERIES:
        ser = series.get(sid)
        if ser is None or len(ser.observations) < 13:
            rows.append((label, "—",
                         (errors.get(sid) or "관측치 부족")[:46]))
            continue
        obs = ser.observations
        last, year_ago = obs[-1].value, obs[-13].value
        yoy = ((last / year_ago - 1.0) * 100.0) if year_ago else None
        rows.append((
            label,
            f"{last:,.2f}" + (f"  ({yoy:+.1f}% YoY)" if yoy is not None else ""),
            obs[-1].date.isoformat()))
    return rows


@swr.cached(1_800)
def load_sector_news(use_demo: bool):
    """섹터별 헤드라인. 30분 캐시 — 뉴스는 보조입니다."""
    if use_demo:
        return demo_mod.demo_sector_news(config.KR_SECTORS)
    try:
        return news.fetch_sector_news(config.KR_SECTORS,
                                      limit=config.SECTOR_NEWS_PER)
    except Exception as exc:  # noqa: BLE001
        return {}, {"_": f"{type(exc).__name__}: {exc}"}


def _filings_ok(value) -> bool:
    scan = value[0] if isinstance(value, tuple) and value else None
    return bool(getattr(scan, "filings", None))


@swr.cached(1_800, stale=6 * 3_600, keep=_filings_ok)
def load_market_filings(use_demo: bool, key_fp: str = ""):
    """시장 전체 주요 공시 → (FilingScan, 오류).

    주말을 넘겨도 비지 않게 5일을 봅니다. 30분 캐시 + 6시간 묵은 값 허용 —
    공시는 장중에도 계속 올라오지만 30분 늦는다고 판단이 바뀌는 종류는
    아닙니다 (급한 건 HTS 알림이 먼저입니다)."""
    if use_demo:
        return demo_mod.demo_filing_scan(), ""
    try:
        return dart.scan_market_filings(days=5, limit=300), ""
    except Exception as exc:  # noqa: BLE001
        return dart.FilingScan(filings=[]), f"{type(exc).__name__}: {exc}"


@swr.cached(86_400)
def load_kr_companies(codes: tuple[str, ...], use_demo: bool,
                      key_fp: str = "") -> dict:
    """국내 기업개황. 회사 정보는 거의 안 바뀌므로 캐시를 하루로 둡니다.

    key_fp 는 DART 키 지문입니다 — 키를 바꿨는데 실패한 결과가 캐시에
    남아 있으면 넣어도 안 바뀝니다. 캐시 키에 넣어 자동 무효화합니다.
    """
    if not codes:
        return {}
    if use_demo:
        return demo_mod.demo_kr_companies(codes)
    out: dict = {}
    try:
        corp_map = dart.fetch_corp_codes()
    except Exception as exc:  # noqa: BLE001
        return {c: dart.CompanyProfile(stock_code=c, error=str(exc))
                for c in codes}
    for code in codes:
        try:
            corp = dart.resolve_corp_code(code, corp_map)
            if not corp:
                out[code] = dart.CompanyProfile(
                    stock_code=code, error="DART 고유번호를 찾지 못했습니다.")
                continue
            out[code] = dart.fetch_company(corp, code)
        except Exception as exc:  # noqa: BLE001
            out[code] = dart.CompanyProfile(stock_code=code, error=str(exc))
    return out


@swr.cached(21_600)
def load_kr_exports(use_demo: bool):
    """한국 반도체 수출. 월 1회 발표라 캐시를 6시간으로 둡니다.

    실패를 예외로 올리지 않습니다 — 이 경로는 검증되지 않았고, 막혔다고
    메모리 사이클 탭 전체가 비면 안 됩니다. 실패 사유를 함께 돌려줍니다.
    """
    if use_demo:
        return demo_mod.demo_kr_exports(), ""
    try:
        from sources import kr_exports as kx
        return kx.fetch_latest(), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


@swr.cached(60, disk=False)
def load_briefings() -> list:
    """증시 브리핑. 로컬 파일이라 캐시를 짧게 둡니다 — 파일을 새로 넣고
    1분 안에 보이는 편이, 캐시를 길게 잡아 '왜 안 보이지' 하는 것보다 낫습니다.
    """
    return bfs.load_all(BRIEFING_PATH)


@swr.cached(config.MACRO_CACHE_TTL_SEC)
def load_macro(use_demo: bool, key_fp: str = "") -> tuple[dict, dict]:
    """FRED 매크로 계열. 키가 필요 없어 설정 없이 바로 동작합니다.

    캐시가 깁니다 — 월간 통계는 하루에 몇 번 조회해도 같은 값입니다.
    """
    if use_demo:
        return demo_mod.demo_macro_series()
    try:
        return fred.fetch_many(config.macro_series_ids(),
                               years=config.MACRO_SERIES_YEARS)
    except Exception as exc:  # noqa: BLE001
        return {}, {sid: str(exc) for sid in config.macro_series_ids()}


@swr.cached(config.SCREEN_CACHE_TTL_SEC)
def load_screens(use_demo: bool) -> tuple[dict, dict]:
    """버핏식 스크리닝. 기업당 companyfacts 1회 요청.

    캐시가 24시간입니다 — 연간 재무제표는 1년에 한 번 바뀝니다.
    """
    if use_demo:
        return demo_mod.demo_screens()

    tickers = config.screen_tickers()
    th = config.screen_thresholds()
    try:
        ticker_map = edgar.fetch_ticker_map(config.EDGAR_USER_AGENT)
    except Exception as exc:  # noqa: BLE001
        return {}, {t: f"티커 매핑 실패: {exc}" for t in tickers}

    ciks: dict[str, int] = {}
    errors: dict[str, str] = {}
    for ticker in tickers:
        cik = (config.EDGAR_CIK_OVERRIDES.get(ticker)
               or ticker_map.get(ticker.upper())
               # BRK-B 처럼 EDGAR 가 하이픈을 쓰는 경우
               or ticker_map.get(ticker.upper().replace(".", "-")))
        if cik is None:
            errors[ticker] = "CIK 를 찾지 못했습니다 (SEC 신고 기업이 아닐 수 있습니다)."
            continue
        ciks[ticker] = cik

    facts_map, fetch_errors = edgar_facts.fetch_many(
        ciks, config.EDGAR_USER_AGENT, keep=buffett.KEEP_TAGS)
    errors.update(fetch_errors)

    screens: dict[str, object] = {}
    for ticker, facts in facts_map.items():
        screens[ticker] = buffett.screen_company(
            ticker, facts, years=config.SCREEN_YEARS, th=th)
    return screens, errors


@swr.cached(600)
def load_market_caps(tickers: tuple[str, ...], use_demo: bool) -> dict[str, float]:
    """시가총액 — 역DCF 의 유일한 외부 입력값입니다.

    FCF 와 순부채는 공시에서 나오지만 시가총액은 시세라서 야후에서 받습니다.
    """
    if use_demo:
        caps = dict(demo_mod.demo_market_caps())
        caps.update(demo_mod.demo_kr_market_caps())
        return {t: caps[t] for t in tickers if t in caps}
    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            value = yahoo.fetch_market_cap(ticker)
            if value:
                out[ticker] = value
        except Exception:  # noqa: BLE001
            continue
    return out


def _attach_dcf(screens: list, use_demo: bool, *, currency: str = "USD",
                cap_source: str = "") -> list:
    """스크리닝 결과에 역DCF 와 판단 재료를 붙입니다."""
    usable = [s for s in screens if s.ok]
    caps = load_market_caps(tuple(s.ticker for s in usable), use_demo)
    out = []
    for screen in usable:
        inputs = rdcf.inputs_from_screen(
            screen, caps.get(screen.ticker), currency=currency,
            market_cap_source=cap_source or ("데모 데이터" if use_demo else "yfinance"))
        result = rdcf.run(inputs)
        out.append((screen, result, vd.build(screen, result)))
    return out


def _risk_free_pct(use_demo: bool) -> float | None:
    """FRED 10년물(DGS10) 최신값. 가격 조건의 기준선에 씁니다.

    받아오지 못하면 None 을 돌려주고, value.Thresholds 가 기본값으로
    넘어갑니다 — 금리를 못 받았다고 가격 조건 전체를 못 쓰게 만들 이유가
    없습니다. 화면에는 '미연동' 이라고 적힙니다.
    """
    try:
        series_map, _errors = load_macro(use_demo, fred.key_fingerprint())
    except Exception:  # noqa: BLE001
        return None
    series = series_map.get("DGS10")
    obs = getattr(series, "latest", None) if series is not None else None
    return obs.value if obs is not None else None


def _price_screens(triples: list, use_demo: bool) -> dict:
    """가격 조건 판정을 티커별로 돌려줍니다.

    **_attach_dcf 의 반환 튜플을 건드리지 않습니다.** 3개를 4개로 늘리면
    풀어 쓰는 자리를 한 곳이라도 놓쳤을 때 배포 후 ValueError 로 죽습니다
    (실제로 한 번 겪었습니다). 별도 dict 로 두면 기존 자리는 그대로입니다.

    시가총액은 load_market_caps 가 캐시하므로, _attach_dcf 가 이미 같은
    인자로 불렀다면 추가 호출이 없습니다 — **정렬 전에** 부르십시오.
    """
    if not triples:
        return {}
    th = vl.Thresholds(risk_free_pct=_risk_free_pct(use_demo))
    caps = load_market_caps(tuple(t[0].ticker for t in triples), use_demo)
    return {t[0].ticker: vl.build(t[0], t[1], caps.get(t[0].ticker), th)
            for t in triples}


def _render_screen_body(triples: list, *, min_pass: int, show_source: bool,
                        criteria) -> None:
    """미국·국내 공통 렌더링."""
    screens = [t[0] for t in triples]
    verdicts = [t[2] for t in triples]

    st.markdown(
        ui.render_footnote(
            "<b>기준별 통과율</b> — 0% 나 100% 에 가까운 기준은 구분을 못 하고 "
            "있다는 뜻이니 기준선을 조정할 후보입니다: "
            + " · ".join(
                f"{c.name.replace(' 꾸준히', '')} "
                f"{sum(1 for s in screens if s.checks[i].passed)}/{len(screens)}"
                for i, c in enumerate(criteria))
        ),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_screen_table(screens, criteria), unsafe_allow_html=True)

    st.markdown(
        ui.render_section_head(
            "사분면 지도", "사업의 질(가로) × 가격의 기대(세로)", len(verdicts)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_quadrant_map(verdicts), unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "①~④ 는 <b>좋고 나쁨의 순서가 아닙니다.</b> ① 이 항상 좋은 것도 "
            "아닙니다 — 시장이 알고 있는 위험을 가격에 반영했을 수 있습니다. "
            "네 칸은 <b>다음에 무엇을 확인해야 하는가</b>가 다를 뿐입니다."
        ),
        unsafe_allow_html=True,
    )

    shortlist = [t for t in triples if t[0].passed_count >= min_pass]
    st.markdown(
        ui.render_section_head(
            ("전체 종목" if min_pass <= 0 else f"{min_pass}개 이상 통과"),
            "각 카드의 질문을 Claude 에 붙여넣으면 정독이 시작됩니다",
            len(shortlist)),
        unsafe_allow_html=True,
    )
    for screen, result, verdict_obj in shortlist:
        st.markdown(
            ui.render_screen(screen, show_source=show_source),
            unsafe_allow_html=True,
        )
        st.markdown(ui.render_dcf_cells(result), unsafe_allow_html=True)
        st.markdown(
            ui.render_verdict(verdict_obj, prompt=vd.prompt_for(verdict_obj, screen)),
            unsafe_allow_html=True,
        )
    if not shortlist:
        st.markdown(
            ui.render_footnote(
                "기준을 낮추거나 <code>config.py</code> 의 기준선을 조정하십시오. "
                "통과 기업이 0개인 것도 정보입니다."
            ),
            unsafe_allow_html=True,
        )


def render_premium_tab(data: dict[str, dict[str, Quote]], fx,
                       interval: int | None) -> None:
    """괴리율 · 국내 본주 — 하나의 화면. 계산 사슬이 그대로 보입니다."""
    import datetime as _dt

    foreign = list(config.SECTION_ADR.instruments)
    local = list(config.SECTION_LOCAL.instruments)
    rows, unpaired = compute.build_premium_rows(foreign, local, data, fx)

    state, state_detail = compute.kospi_state()
    now_kst = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    live_detail = (f"{now_kst:%H:%M:%S} KST"
                   + (f" · {interval}초마다 갱신" if interval else " · 수동 갱신"))

    st.markdown(
        ui.render_section_head(
            "괴리율 · 국내 본주",
            "해외 상장 한국 종목과 국내 본주를 한 화면에서 — 계산 사슬 전체",
            len(rows) + len(unpaired),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="margin:-4px 0 10px">'
        + ui.render_live_badge("실시간", "on" if interval else "", live_detail)
        + "  "
        + ui.render_live_badge("코스피", state, state_detail)
        + "</div>",
        unsafe_allow_html=True,
    )

    if state == "frozen":
        st.markdown(
            ui.render_footnote(
                "<b>지금 괴리율은 실제 가격차가 아닙니다.</b> 국내 장이 닫혀 "
                "본주가가 종가로 고정돼 있으므로, 이 수치는 <b>마감 이후 해외에서 "
                "벌어진 움직임</b>을 본주 기준으로 환산한 값입니다. "
                "코스피가 열리면 본주가가 움직이면서 괴리가 좁혀지는 것이 "
                "보통입니다."
            ),
            unsafe_allow_html=True,
        )

    for row in rows:
        st.markdown(ui.render_premium_pair(row, fx=fx), unsafe_allow_html=True)

    if unpaired:
        st.markdown(
            ui.render_section_head(
                "짝이 없는 국내 종목", "해외 상장이 없어 괴리율을 낼 수 없습니다",
                len(unpaired)),
            unsafe_allow_html=True,
        )
        cards = "".join(
            ui.render_card(inst, (data.get(inst.source) or {}).get(inst.symbol), fx)
            for inst in unpaired
        )
        st.markdown(f'<div class="dash-grid cols-4">{cards}</div>',
                    unsafe_allow_html=True)

    st.markdown(
        ui.render_footnote(
            "괴리율 = (해외가격 × 환율 ÷ 환산주수) ÷ 국내 본주가 − 1. "
            "해외 종목에 프리/애프터장 가격이 있으면 <b>그것을 우선</b> 씁니다 — "
            "야간 괴리율이 이 화면의 주 용도입니다.<br>"
            "<b>괴리율이 크다는 사실만으로 차익거래 기회가 아닙니다.</b> "
            "SK하이닉스 ADR 은 본주→ADR 전환이 발행주식수의 2.5% 로 제한되어 "
            "차익거래로 괴리가 좁혀지기 어렵습니다. 세금·수수료·환전 비용도 "
            "이 수치에 반영되어 있지 않습니다."
        ),
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 0. 요약 — 휴대폰 10초 화면
# ──────────────────────────────────────────────────────────────────────────────

def render_summary_tab(data: dict[str, dict[str, Quote]], fx,
                       use_demo: bool, *, market: str = "all") -> None:
    """요약. 다른 탭에서 이미 캐시된 것만 씁니다 — 휴대폰에서 느려지면 안 됩니다.

    발굴·밸류에이션은 일부러 빼둡니다. 68종목의 10년 재무를 받아오는 작업이라
    휴대폰 글랜스에 맞지 않습니다 — 어디로 가면 되는지만 적습니다.
    """
    found, instruments, trends, _filings, _errors = _detect_signals(
        data, use_demo, market=market, soft=True)
    # 요약은 "지금 N건" 과 "이번 주 N건" 을 구분해 적어야 해서 세 갈래가
    # 필요합니다. signals.split_by_urgency 는 둘을 합쳐 두 갈래로 주므로
    # **여기서 직접 나눕니다** — 다른 파일을 함께 고쳐야 하는 변경을 피하려는
    # 것입니다. 파일을 손으로 맞추다 보면 한쪽만 올라가 AttributeError 가
    # 납니다. 세 줄짜리 분류라 공유 함수로 뺄 이득이 적습니다.
    collapsed = sig_mod.collapse(found)
    urgent = [s for s in collapsed if s.severity >= 3]
    soon = [s for s in collapsed if s.severity == 2]

    # 시장마다 둘째 줄이 다릅니다 — 미국은 심리(공포탐욕·VIX), 한국은
    # 섹터 온도. 안 쓰는 쪽은 **받아오지 않습니다**.
    fg = vix_state = None
    sector_rows = None
    if market == "kr":
        sector_rows = load_sector_heat(use_demo)
    else:
        fg = load_feargreed(use_demo)
        vix_state = load_vix(use_demo)
    series_map, errors = load_macro(use_demo, fred.key_fingerprint())
    readings = macro_mod.build_readings(config.macro_series(), series_map, errors)

    summary = sm.build(
        urgent=urgent, soon=soon, holdings_total=len(instruments),
        fg=fg, vix_state=vix_state, trends=trends, macro_readings=readings,
        market=market, sector_rows=sector_rows,
    )

    st.markdown(ui.render_summary(summary), unsafe_allow_html=True)
    if sector_rows:
        st.markdown(ui.render_sector_bars(sector_rows), unsafe_allow_html=True)

    _render_upcoming(data, use_demo, market)
    _render_daily_briefs(use_demo, market)

    # 브리핑은 한 줄만. 요약은 임계값을 건드린 것만 올리는 화면인데 브리핑은
    # 매일 있으므로, 전문을 넣으면 요약이 항상 차 있게 됩니다.
    briefings = load_briefings()
    if briefings:
        st.markdown(ui.render_briefing_line(briefings[0]),
                    unsafe_allow_html=True)

    if summary.all_quiet:
        st.markdown(
            ui.render_footnote(
                "<b>조용한 게 정상입니다.</b> 이 화면은 뉴스 피드가 아니라 "
                "<b>임계값을 건드린 것만</b> 올립니다 — 올라온 게 없으면 "
                "앱을 닫아도 됩니다."
            ),
            unsafe_allow_html=True,
        )

    # 긴급 신호는 요약에서 바로 펼쳐 봅니다 (탭 이동 없이)
    if urgent:
        st.markdown(
            ui.render_section_head("지금 확인할 것", "내 종목", len(urgent)),
            unsafe_allow_html=True,
        )
        news_targets = tuple(sig_mod.news_targets(
            urgent, limit=config.NEWS_MAX_TICKERS))
        headlines = load_news(news_targets, use_demo)
        for sig in urgent[:6]:
            st.markdown(
                ui.render_signal_card(sig, headlines.get(sig.inst.symbol)),
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# 1. 내 종목 — 변화 감지 + 시세 + 공시 분석
# ──────────────────────────────────────────────────────────────────────────────

def _portfolio_quote(p, data):
    """보유 종목의 시세 — 관심종목 정의가 있으면 그걸로, 없으면 즉석 정의."""
    for inst in (*config.SECTION_WATCHLIST.instruments, *config.SECTION_LOCAL.instruments):
        if inst.symbol == p.symbol:
            return pick_quote(inst, data), inst.name
    inst = config.Instrument(p.symbol, p.symbol, p.source,
                             currency="KRW" if p.market == "kr" else "USD")
    q = pick_quote(inst, data)
    name = (getattr(q, "extra", None) or {}).get("name") if q is not None else None
    return q, (name or p.symbol)


def _render_portfolio(data, fx, use_demo: bool, market: str) -> None:
    """보유 평가 — Secrets 의 PORTFOLIO 가 있을 때만. 없으면 넣는 법 한 줄."""
    positions, bad, source = portfolio.load(use_demo)
    if not positions:
        st.markdown(ui.render_portfolio_setup(), unsafe_allow_html=True)
        return
    names: dict = {}
    quotes: dict = {}
    for p in positions:
        quotes[p.symbol], names[p.symbol] = _portfolio_quote(p, data)
    usd = getattr(fx, "usdkrw", None)
    total = portfolio.valuate(positions, lambda p: quotes.get(p.symbol), usd, names)
    mine = [p for p in positions if p.market == market]
    if not mine:
        st.markdown(ui.render_notice(
            f"<b>{config.MARKETS.get(market, '')} 종목 보유가 없습니다.</b> 계좌 전체 "
            f"평가금액 {ui._won(total.value_krw)} · 손익 {ui._won(total.pnl_krw, True)}"),
            unsafe_allow_html=True)
        return
    summ = portfolio.valuate(mine, lambda p: quotes.get(p.symbol), usd, names)
    st.markdown(ui.render_section_head(
        "보유 평가", "수량·평균단가 기준 · 원화 환산", len(mine)),
        unsafe_allow_html=True)
    st.markdown(ui.render_portfolio(summ, source=source, bad=bad, total=total),
                unsafe_allow_html=True)


def render_holdings_tab(data: dict[str, dict[str, Quote]], fx,
                        use_demo: bool, phone: bool = False,
                        *, market: str = "all") -> None:
    """내가 가진 종목에 대해 알아야 할 전부를 한 화면에.

    예전에는 '변화 감지' · '관심종목' · '공시 분석' 세 탭이었습니다. 보유 종목을
    볼 때는 늘 세 탭을 다 열어야 했으니 나뉘어 있을 이유가 없었습니다.
    순서가 중요합니다 — **지금 확인할 것이 맨 위**, 그다음 시세, 그다음 분석.
    """
    watchlist = config.SECTION_WATCHLIST
    local = config.SECTION_LOCAL

    # 표가 먼저 — 가진 종목의 숫자와 신호 개수를 한눈에. 자세한 신호는
    # 그 아래 '변화 감지' 가 그립니다.
    shown = config.filter_instruments(watchlist.instruments, market)
    try:
        found = _detect_signals(data, use_demo, market=market, soft=True)[0]
    except Exception:  # noqa: BLE001 - 신호를 못 구해도 표는 그립니다
        found = []
    _render_portfolio(data, fx, use_demo, market)

    # 차트 상태 칸 — 이미 받아 둔 일봉이 있을 때만. 없으면 이번엔 빼고
    # 뒤에서 받기 시작합니다 (내 종목 화면이 50종목 일봉을 기다리지 않게).
    chart_rows = None
    try:
        got = load_chart_rows.peek(market, use_demo)
        if got is not None:
            chart_rows = {r.ticker: r for r in got}
    except Exception:  # noqa: BLE001
        chart_rows = None
    st.markdown(
        ui.render_section_head("보유 · 관심 종목", watchlist.subtitle,
                               len(shown)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_holdings_table(
        [(inst, pick_quote(inst, data),
          [s for s in found if getattr(s.inst, "symbol", None) == inst.symbol])
         for inst in shown], chart_rows=chart_rows), unsafe_allow_html=True)
    if chart_rows is None:
        st.markdown(ui.render_footnote(
            "차트 상태는 일봉을 받는 중이라 이번 화면에서는 뺐습니다 — 다시 "
            "열면 붙습니다."), unsafe_allow_html=True)

    render_signals_tab(data, use_demo, market=market)

    # 국내 본주 목록은 한국 쪽입니다 — 미국만 볼 때는 보일 이유가 없습니다
    others = [i for i in local.instruments
              if i.symbol not in {w.symbol for w in watchlist.instruments}
              and config.in_market(i, market)]
    if others:
        with st.expander(f"국내 본주 {len(others)}종목 더 보기", expanded=False):
            more = "".join(
                ui.render_card(inst,
                               (data.get(inst.source) or {}).get(inst.symbol), fx)
                for inst in others
            )
            st.markdown(f'<div class="dash-grid cols-4">{more}</div>',
                        unsafe_allow_html=True)

    # ── 공시 분석 — 섹션 전체를 접습니다 ────────────────────────────────────
    # 분석 본문만 접어도 위젯이 20개 넘게 남아 화면이 길어집니다. '내 종목' 은
    # 시세와 변화 감지를 보러 오는 화면이니, 분석은 **통째로 접고** 요약 한 줄만
    # 밖에 둡니다 — 어느 종목에 분석이 있는지는 접힌 채로도 보여야 합니다.
    summary = _analysis_summary()
    with st.expander(f"공시 분석 — {summary}", expanded=False):
        render_analysis_tab(embed=True, phone=phone)


def _analysis_summary() -> str:
    """접힌 상태에서도 보이는 한 줄 요약."""
    instruments = config.analysis_instruments()
    docs = analysis_store.load_all(
        ANALYSIS_PATH, [i.analysis_key for i in instruments])
    ready = [i for i in instruments if not docs[i.analysis_key].is_empty]
    stale = [i for i in ready if docs[i.analysis_key].is_stale]

    if not ready:
        return f"생성된 분석 없음 (대상 {len(instruments)}종목)"
    names = ", ".join(i.analysis_key for i in ready[:4])
    if len(ready) > 4:
        names += f" 외 {len(ready) - 4}"
    text = f"{names} ({len(ready)}/{len(instruments)}종목)"
    if stale:
        text += f" · {len(stale)}건 오래됨"
    return text


# ──────────────────────────────────────────────────────────────────────────────
# 2. 종목 발굴 — 52주 위치 × 버핏식 품질
# ──────────────────────────────────────────────────────────────────────────────

# load_discovery_quotes / _discovery_instruments 는 2026-11-11 에 지웠습니다.
# 52주 위치 축을 발굴에서 뺐고(미국), 국내는 야후 일봉에서 직접 고·저를
# 계산하므로(kr_screen) 시세 스냅샷이 더 필요하지 않습니다. 빈 함수로
# 남겨두면 다음에 "이건 왜 안 쓰지" 를 다시 따져야 합니다.


def render_discover_tab(use_demo: bool, *, market: str = "all") -> None:
    """종목 발굴 — 시장마다 **다른 도구**를 씁니다.

    전에는 한·미 모두 '52주 위치 × 버핏식 품질' 사분면이었습니다. 미국에는
    맞지만 국내에는 맞지 않았습니다:

    - 미국은 후보가 68종목이고 재무가 안정적이라 **품질 기준만으로도**
      목록이 줄어듭니다. 52주 위치는 거기에 모멘텀을 섞는 축이라, 장기
      보유 판단에는 오히려 잡음이었습니다. 그래서 뺐습니다.
    - 국내는 후보가 50종목 남짓이라 재무 기준으로 거의 안 걸러지고, 대신
      **주가 변동성이 훨씬 큽니다.** 그래서 변동성을 축으로 씁니다.
    """
    if market == "kr":
        _discover_kr(use_demo)
    else:
        _discover_us(use_demo)


# ── 미국 — 버핏식 품질 기준만 ────────────────────────────────────────────

def _discover_us(use_demo: bool) -> None:
    """미국 발굴 — 52주 위치를 뺐습니다.

    **왜 뺐는가.** 52주 신고가는 '최근 많이 오른 주식' 이지 '좋은 주식' 이
    아닙니다. 품질 기준과 교차하면 그럴듯해 보이지만, 실제로 하는 일은
    품질을 통과한 목록을 **주가 흐름으로 한 번 더 자르는 것**입니다.
    장기 보유 판단에서 그 자르기는 근거가 없습니다. 시세는 밸류에이션
    탭의 가격 조건(FCF 수익률·기대 괴리)이 다룹니다 — 거기는 가격을
    **공시 숫자와 견주는** 자리라 성격이 다릅니다.
    """
    st.markdown(
        ui.render_section_head(
            "종목 발굴 · 미국",
            f"버핏식 품질 기준 {len(buffett.CRITERIA)}개 — 읽을 목록을 줄입니다"),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>52주 위치 축을 뺐습니다.</b> 신고가는 '최근 많이 오른 주식' "
            "이지 '좋은 주식' 이 아닙니다 — 품질 기준을 통과한 목록을 주가 "
            "흐름으로 한 번 더 자를 근거가 장기 보유 판단에는 없습니다. "
            "가격은 <b>밸류에이션 탭</b>에서 공시 숫자(FCF·순부채)와 "
            "견줍니다."),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        quality_min = st.slider(
            "품질 기준 통과 수 (이상이면 '통과')",
            1, len(buffett.CRITERIA),
            round(len(buffett.CRITERIA) * 2 / 3), key="disc_q")
    with col2:
        show_source = st.toggle("기준 출처·한계 표시", value=False,
                                key="disc_src")

    screens_map, errors = load_screens(use_demo)
    screens = buffett.rank(list(screens_map.values()))
    passed = [s for s in screens if s.passed_count >= quality_min]

    st.markdown(
        ui.render_notice(
            f"<b>후보 {len(screens)}종목</b> 중 "
            f"<b>{len(passed)}종목</b>이 {quality_min}개 이상 통과"
            + (f" · 재무를 못 받은 종목 {len(errors)}건" if errors else "")),
        unsafe_allow_html=True,
    )

    if not passed:
        st.markdown(
            ui.render_notice(
                "<b>통과한 종목이 없습니다.</b> 기준을 한두 칸 낮춰 보십시오 — "
                f"{len(buffett.CRITERIA)}개를 전부 넘는 기업은 드뭅니다."),
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        ui.render_section_head("통과 종목", "통과 수 많은 순", len(passed)),
        unsafe_allow_html=True,
    )
    for idx, screen in enumerate(passed[:30]):
        label = (f"{screen.ticker} · {screen.passed_count}"
                 f"/{len(buffett.CRITERIA)} 통과")
        with st.expander(label, expanded=(idx == 0)):
            st.markdown(ui.render_screen(screen, show_source=show_source),
                        unsafe_allow_html=True)

    if errors:
        st.markdown(
            ui.render_notice(
                f"<b>재무를 못 받은 종목 {len(errors)}건:</b> "
                + " · ".join(f"{t} ({e[:34]})"
                             for t, e in list(errors.items())[:6])),
            unsafe_allow_html=True,
        )


# ── 국내 — 변동성 + 밸류 ────────────────────────────────────────────────

def _discover_kr(use_demo: bool) -> None:
    """국내 발굴 — 스크리너 → 종목 카드(개요·뉴스·스킬) 순서."""
    st.markdown(
        ui.render_section_head(
            "종목 발굴 · 한국",
            "변동성 × 신고가 × 전통 밸류 — 국내는 재무만으로 안 걸러집니다"),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            f"<b>왜 미국과 기준이 다른가.</b> 국내 후보 "
            f"{len(config.screen_kr_candidates())}종목(코스피 + 코스닥)은 "
            "재무 기준만으로는 거의 걸러지지 않습니다. 대신 주가 "
            "변동성이 미국보다 큽니다 — 52주 신고가를 단독으로 쓰면 "
            "급등 후 되돌림 구간이 대거 섞입니다. 그래서 <b>변동성이 "
            "잦아든 상태</b>와 <b>거래대금 바닥</b>을 같이 봅니다. "
            "코스닥에는 '거래가 없어서 안 움직인' 종목이 흔한데, "
            "변동성 수축만으로는 그걸 구분하지 못합니다."),
        unsafe_allow_html=True,
    )

    profiles, vol_errors = load_kr_vol_profiles(use_demo)
    value_rows = load_kr_value_rows(use_demo)

    hits = {
        "contraction": kr_screen.contraction_hits(profiles),
        "near_high": kr_screen.near_high_hits(profiles),
        "value_trad": kr_screen.value_hits(value_rows),
    }

    picker = getattr(st, "segmented_control", None)
    labels = {k: t for k, t, _r, _c in kr_screen.KR_SCREENS}
    keys = [k for k, _t, _r, _c in kr_screen.KR_SCREENS]
    choice = None
    if picker is not None:
        try:
            choice = picker(
                "스크리너", keys, default=keys[0], key="kr_scr",
                format_func=lambda k: f"{labels[k]} ({len(hits[k])})",
                label_visibility="collapsed")
        except Exception:  # noqa: BLE001
            choice = None
    if choice is None:
        choice = st.radio(
            "스크리너", keys, horizontal=True, key="kr_scr_r",
            format_func=lambda k: f"{labels[k]} ({len(hits[k])})",
            label_visibility="collapsed")
    if choice not in labels:
        choice = keys[0]

    _key, title, rule, caveat = next(
        x for x in kr_screen.KR_SCREENS if x[0] == choice)
    picked = hits[choice]
    st.markdown(ui.render_screener_head(title, rule, len(picked), caveat),
                unsafe_allow_html=True)

    # 단계별로 몇 종목이 남는지 — 0 건이 '데이터 실패' 인지 '기준 탈락'
    # 인지 바로 보이게 합니다.
    n_cands = len(config.screen_kr_candidates())
    if choice in ("contraction", "near_high"):
        steps = kr_screen.vol_funnel(n_cands, profiles)
        if choice == "near_high":
            steps = steps[:-1]      # 신고가만 보는 스크리너엔 수축 단계가 없음
        st.markdown(ui.render_funnel(steps, vol_errors,
                                     title="단계별로 남은 종목"),
                    unsafe_allow_html=True)
    else:
        v_err = {r.ticker: r.error for r in value_rows if r.error}
        st.markdown(ui.render_funnel(kr_screen.value_funnel(value_rows), v_err,
                                     title="단계별로 남은 종목"),
                    unsafe_allow_html=True)

    if not picked:
        st.markdown(
            ui.render_notice(
                "<b>이 기준을 통과한 종목이 없습니다.</b> 위 단계표에서 "
                "숫자가 크게 줄어든 칸이 원인입니다 — '일봉 받음' 이나 "
                "'지표 받음' 에서 줄었다면 데이터 문제이고, 그 뒤에서 "
                "줄었다면 지금 시장에 그런 종목이 없는 것입니다. 기준은 "
                "느슨하게 하지 않습니다."),
            unsafe_allow_html=True,
        )
        return

    st.markdown(ui.render_hit_table(picked), unsafe_allow_html=True)

    companies = load_kr_companies(
        tuple(h.ticker for h in picked[:12]), use_demo, dart.key_fingerprint())
    headlines = load_news(
        tuple((h.ticker, h.name, "naver") for h in picked[:12]), use_demo)
    cli = runner.cli_info()

    for idx, hit in enumerate(picked[:12]):
        with st.expander(f"{hit.name} · {hit.ticker}", expanded=(idx == 0)):
            st.markdown(ui.render_hit_metrics(hit), unsafe_allow_html=True)
            st.markdown(ui.render_hit_reasons(hit), unsafe_allow_html=True)

            st.markdown(ui.render_section_head("기업 개요", "DART 기업개황"),
                        unsafe_allow_html=True)
            st.markdown(
                ui.render_company_overview(companies.get(hit.ticker),
                                           search_name=hit.name),
                unsafe_allow_html=True,
            )

            items = headlines.get(hit.ticker) or []
            st.markdown(
                ui.render_section_head("최근 뉴스", "구글 뉴스 · 제목과 링크만",
                                       len(items)),
                unsafe_allow_html=True,
            )
            st.markdown(
                ui.render_news_block(items, limit=5)
                or ui.render_footnote("최근 헤드라인을 찾지 못했습니다."),
                unsafe_allow_html=True,
            )

            _render_skill_buttons(hit.ticker, hit.name, cli)


def _render_skill_buttons(code: str, name: str, cli) -> None:
    """3대 분석 스킬 — 어디서든 돌릴 수 있게.

    **스트림릿 클라우드에서는 `claude -p` 가 돌지 않습니다.** 컨테이너에
    실행 파일도 로그인 세션도 없습니다. '느려서' 가 아니라 '없어서' 안
    됩니다. 그래서 실행 경로를 셋으로 나눴습니다:

      1. 로컬에서 `streamlit run app.py` — 버튼이 그대로 돕니다
      2. 휴대폰·PC 어디서든 — Claude 앱/웹을 **프롬프트가 채워진 채로**
         열어주는 링크 (`claude://claude.ai/new?q=` / `claude.ai/new?q=`).
         공식 딥링크라 앱이 깔려 있으면 앱이 열리고, 없으면 웹이 열립니다.
      3. PC 에서 Claude Code 로 — `claude://code/new?q=…&folder=…`

    2번이 휴대폰에서 쓰는 길입니다. 누르면 프롬프트가 입력창에 채워진
    채로 열리므로, 읽어보고 보내기만 하면 됩니다.
    """
    st.markdown(
        ui.render_section_head("3대 분석", "어디서 돌릴지 고르십시오",
                               len(analysis_store.KINDS)),
        unsafe_allow_html=True,
    )

    if cli.available:
        cols = st.columns(len(analysis_store.KINDS))
        for col, (kind, label, desc) in zip(cols, analysis_store.KINDS):
            with col:
                if st.button(f"▶ {label}", key=f"kr_run_{code}_{kind}",
                             help=f"{desc} — 이 컴퓨터에서 바로 실행",
                             use_container_width=True):
                    runner.start_job(
                        ANALYSIS_PATH, BASE_DIR, code, name, kind,
                        max_turns=st.session_state.get(
                            "max_turns", runner.DEFAULT_MAX_TURNS),
                        permission_mode=st.session_state.get(
                            "permission_mode", runner.DEFAULT_PERMISSION_MODE),
                        skill_commands=st.session_state.get("skill_commands"),
                    )
                    st.rerun()
        st.caption(f"이 컴퓨터에서 바로 실행합니다 ({cli.label}). "
                   "결과는 `analysis/` 폴더에 쌓이고 '공시 분석' 탭에서 읽힙니다.")
    else:
        st.caption(
            "**이 환경에는 `claude` 실행 파일이 없습니다** — 느린 게 아니라 "
            "아예 없습니다. 대신 아래 링크를 누르면 Claude 앱(또는 웹)이 "
            "**프롬프트가 채워진 채로** 열립니다. 휴대폰에서도 됩니다."
        )

    st.markdown(ui.render_skill_links(code, name), unsafe_allow_html=True)

    with st.expander("직접 붙여넣을 명령", expanded=False):
        st.code("\n".join(analysis_store.skill_command(k, code, name)
                          for k, _l, _d in analysis_store.KINDS),
                language="text")
        st.caption(
            "Claude 앱·웹 어디든 붙여넣으면 됩니다. 이 프로젝트에 스킬이 "
            "등록돼 있어야 슬래시 명령이 동작합니다."
        )


# ──────────────────────────────────────────────────────────────────────────────
# 뉴스 · 공시 · 지표
# ──────────────────────────────────────────────────────────────────────────────

def render_chart_tab(use_demo: bool, *, market: str = "kr") -> None:
    """차트 조건 — 일목 양운 · CCI · MACD · 스토캐스틱 슬로우 · −DI (일봉).

    지표마다 **지금 상태**(과매도 진입 · 구간 · 탈출 시도 · 탈출, 과매수
    근접 …)를 이름으로 보여주고, 한 점수로 합치지 않습니다. 사용자가
    '모두 해당해야 하는 조건' 과 '쪽'(과매도 / 과매수)을 고릅니다.
    """
    conds = chart_signals.CONDITIONS
    rows = load_chart_rows(market, use_demo)
    ok_rows = [r for r in rows if r.ok]
    st.markdown(
        ui.render_section_head(
            f"차트 조건 · {config.MARKETS.get(market, '')}",
            "일봉 기준 — 일목 · 이동평균 · CCI · MACD · 스토캐스틱 · 볼린저 · −DI",
            len(ok_rows)),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>읽어볼 목록이지 매매 신호가 아닙니다.</b> 지표는 지난 가격을 "
            "다시 정리한 값이고 방향을 말해주지 않습니다. 장중에는 오늘 "
            "봉이 완성되지 않아 값과 거래량 배수가 마감 때와 다릅니다."),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_chart_counts(
        chart_signals.counts(rows), len(ok_rows), len(rows), conds),
        unsafe_allow_html=True)

    names = {k: n for k, n, _r in conds}
    keys = list(names)
    picked: list = []
    pills = getattr(st, "pills", None)
    if pills is not None:
        try:
            picked = pills("모두 해당해야 하는 조건", keys,
                           selection_mode="multi", key=f"chart_req_{market}",
                           format_func=lambda k: names[k]) or []
        except Exception:  # noqa: BLE001
            pills = None
    if pills is None:
        picked = st.multiselect("모두 해당해야 하는 조건", keys,
                                key=f"chart_req_m_{market}",
                                format_func=lambda k: names[k])
    required = tuple(k for k in keys if k in picked)

    side_names = dict(chart_signals.SIDES)
    side = st.radio("쪽", list(side_names), horizontal=True,
                    key=f"chart_side_{market}",
                    format_func=lambda k: side_names[k],
                    help="CCI · MACD · 스토캐스틱을 과매도 쪽 상태만 / "
                         "과매수 쪽 상태만 보도록 좁힙니다.")
    if side not in side_names:
        side = ""

    # 내 종목(보유·관심)은 표에 ★ 로 표시하고, 그것만 보는 스위치를 둡니다.
    held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
            if config.in_market(i, market)}
    only_held = st.toggle("내 종목만", value=False, key=f"chart_held_{market}")

    chosen = chart_signals.select(rows, required, side)
    if only_held:
        chosen = [r for r in chosen if r.ticker in held]
    label = (" + ".join(names[k] for k in required)
             if required else "조건을 고르지 않음 — 해당 수 많은 순")
    if side:
        label += f" · {side_names[side]}"
    if only_held:
        label += " · 내 종목만"
    st.markdown(ui.render_notice(
        f"<b>{len(chosen)}종목</b> · {label}"), unsafe_allow_html=True)

    if not chosen:
        st.markdown(ui.render_notice(
            "<b>이 조합에 모두 해당하는 종목이 없습니다.</b> 조건을 하나 "
            "빼거나 '쪽' 을 전체로 바꿔 보십시오. 위 칸의 숫자가 조건별 "
            "해당 종목 수입니다."
            if ok_rows else
            "<b>일봉을 받은 종목이 없습니다.</b> 설정 → 진단의 "
            "'국내 데이터 출처 확인' 으로 연결을 확인하십시오."),
            unsafe_allow_html=True)
    else:
        st.markdown(ui.render_chart_table(chosen, held=held),
                    unsafe_allow_html=True)
        for idx, row in enumerate(chosen[:12]):
            with st.expander(f"{row.name} · {row.ticker} · {row.met}/{len(keys)}",
                             expanded=(idx == 0)):
                st.markdown(ui.render_chart_detail(row, conds),
                            unsafe_allow_html=True)

    failed = {r.ticker: r.error for r in rows if r.error}
    if failed:
        with st.expander(f"계산하지 못한 종목 {len(failed)}개 — 이유"):
            st.markdown(ui.render_notice("<br>".join(
                f"<code>{t}</code> {e}" for t, e in list(failed.items())[:60])),
                unsafe_allow_html=True)


def _calendar_events(data, use_demo: bool, days: int = 45, soft: bool = False):
    """(사건 목록, 경고, 오늘). 요약과 일정 탭이 같이 씁니다.

    soft=True (요약): 미국 지표 발표일을 기다리지 않습니다 — 표로 가진 일정
    (통화정책·만기·휴장)은 바로 나오고 발표일은 받는 대로 붙습니다."""
    today = dt.datetime.now(KST).date()
    if soft and not use_demo:
        payload, err = _soft(load_release_dates, use_demo, fred.key_fingerprint(),
                             default=(None, ""))
    else:
        payload, err = load_release_dates(use_demo, fred.key_fingerprint())
    watch = [i for i in config.SECTION_WATCHLIST.instruments if i.source == "yahoo"]
    events, warns = calendar_events.build(
        today, days, fred_payload=payload, quotes=(data or {}).get("yahoo", {}),
        instruments=watch)
    if err:
        warns = [f"미국 지표 발표일을 받지 못했습니다 — {err}"] + warns
    return events, warns, today


def _render_upcoming(data, use_demo: bool, market: str) -> None:
    """요약 — 앞으로 7일의 중요한 일정 (실패해도 요약은 계속)."""
    try:
        events, _w, today = _calendar_events(data, use_demo, days=7, soft=True)
        # 중요한 것 + 고른 시장의 이틀 안 일정(월물 만기처럼 평소엔 작은 것도)
        top = [e for e in events if e.importance >= 2
               or (e.market == market and (e.day - today).days <= 2)][:6]
        if not top:
            return
        st.markdown(ui.render_section_head(
            "다가오는 일정", "앞으로 7일 — 전체는 '주요 일정'", len(top)),
            unsafe_allow_html=True)
        st.markdown(ui.render_calendar(top, today, market=market, compact=True),
                    unsafe_allow_html=True)
    except Exception:  # noqa: BLE001
        pass


def render_calendar_tab(data, use_demo: bool, *, market: str = "kr") -> None:
    """주요 일정 — 통화정책 · 지표 발표 · 만기 · 휴장 · 실적, 앞으로 45일.

    두 시장을 함께 보여주고, 고르지 않은 시장의 일정은 흐리게 둡니다.
    미국 일정이 한국 시장을 움직이고 그 반대도 있어서, 빼면 놓칩니다.
    """
    events, warns, today = _calendar_events(data, use_demo)
    # 배당락일(발표·추정)을 같은 달력에 넣습니다. 실패해도 나머지 일정은 그립니다.
    try:
        div_views = _dividend_views(data, use_demo, today)
    except Exception as exc:  # noqa: BLE001
        div_views = []
        warns = warns + [f"배당 정보를 받지 못했습니다 — {type(exc).__name__}"]
    if div_views:
        events = sorted(
            events + dividends.calendar_events(
                div_views, today, today + dt.timedelta(days=45)),
            key=lambda e: (e.date, -e.importance, e.market))
    st.markdown(
        ui.render_section_head(
            "주요 일정", "앞으로 45일 · 고르지 않은 시장은 흐리게", len(events)),
        unsafe_allow_html=True,
    )
    only = st.toggle(f"{config.MARKETS.get(market, '')} 시장만", value=False,
                     key=f"cal_only_{market}")
    shown = [e for e in events if e.market == market] if only else events
    st.markdown(ui.render_calendar(shown, today, market=market),
                unsafe_allow_html=True)
    for w in warns:
        st.markdown(ui.render_notice(w), unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "<b>출처:</b> FOMC 연준 공식 일정 (2027년은 잠정) · 금통위 한국은행 의결 "
            "일정 · 휴장일 거래소 공지 · 미국 지표 발표일 FRED · 만기일은 규칙"
            "(한국 매월 둘째 목요일, 미국 셋째 금요일)으로 계산하고 휴장이면 앞 "
            "거래일로 당깁니다 · 실적일은 야후 예정일이라 바뀔 수 있습니다 · "
            "배당락일은 야후 발표일이 있으면 그것, 없으면 직전 배당 간격으로 "
            "<b>추정</b>합니다. 한국 경제지표 발표일과 국내 종목 실적일은 "
            "아직 없습니다."),
        unsafe_allow_html=True,
    )
    if div_views:
        st.markdown(ui.render_section_head(
            "배당 일정", "관심·보유 종목 — 다음 배당락일 · 최근 12개월 배당",
            sum(1 for v in div_views if v.count)), unsafe_allow_html=True)
        st.markdown(ui.render_dividend_table(div_views, today, market=market),
                    unsafe_allow_html=True)


def _render_daily_briefs(use_demo: bool, market: str) -> None:
    """전일 장 브리핑 — 고른 시장이 먼저, 다른 시장이 그다음.

    두 시장을 다 보여주는 이유: 한국 종목을 보는 날에도 간밤 미국장은
    배경이고, 미국 종목을 보는 날에도 한국장(반도체)은 같은 업종의 다른
    시간대입니다. 실패해도 요약의 나머지는 그려야 하므로 통째로 감쌉니다.
    """
    try:
        order = [market] + [m for m in config.DAILY_BRIEF if m != market]
        if use_demo:
            heads = load_close_headlines(use_demo)
            reports = load_research("market", use_demo)[0]
            briefs = {m: load_daily_brief(m, use_demo) for m in order}
        else:
            # 기다리지 않습니다 — 기사·리포트는 없으면 빈 채로, 브리핑은
            # 아직 못 받은 시장만 '받는 중' 으로 둡니다.
            heads = _soft(load_close_headlines, use_demo, default={})
            reports = _soft(load_research, "market", use_demo, default=([], ""))[0]
            briefs = {m: _soft(load_daily_brief, m, use_demo, default=None)
                      for m in order}
        st.markdown(
            ui.render_section_head(
                "전일 장 브리핑", "마지막으로 마감한 거래일 — 숫자만, 해석 없이",
                len(order)),
            unsafe_allow_html=True,
        )
        for m in order:
            brief = briefs.get(m)
            if brief is None:
                st.markdown(ui.render_notice(
                    f"<b>{config.MARKETS.get(m, m)} 전일 브리핑을 받는 중입니다.</b> "
                    "받으면 자동으로 채워집니다."), unsafe_allow_html=True)
                continue
            key = config.DAILY_BRIEF[m]["news"][0]
            st.markdown(
                ui.render_daily_brief(
                    brief, heads.get(key) or (),
                    reports if m == "kr" else ()),
                unsafe_allow_html=True,
            )
        st.markdown(
            ui.render_footnote(
                "<b>'왜' 는 적지 않습니다.</b> 숫자만으로는 이유를 알 수 없어서, "
                "움직임만 적고 이유는 마감 기사와 증권사 시황 리포트 링크로 "
                "넘깁니다. 장중에는 오늘 봉을 빼고 그 전 거래일을 보여줍니다."),
            unsafe_allow_html=True,
        )
    except Exception as exc:  # noqa: BLE001
        st.markdown(ui.render_notice(
            f"<b>전일 장 브리핑을 그리지 못했습니다.</b> {type(exc).__name__}"),
            unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# 수급 · 배당 · 실적 서프라이즈 (2026-11-11)
# ──────────────────────────────────────────────────────────────────────────────

def _kr_held_codes(use_demo: bool) -> set[str]:
    """실제 보유(PORTFOLIO) 국내 종목만."""
    try:
        positions, _bad, _src = portfolio.load(use_demo)
    except Exception:  # noqa: BLE001
        return set()
    return {p.symbol for p in positions if p.market == "kr"}


def _us_held_symbols(use_demo: bool) -> set[str]:
    try:
        positions, _bad, _src = portfolio.load(use_demo)
    except Exception:  # noqa: BLE001
        return set()
    return {p.symbol for p in positions if p.market == "us"}


def _kr_name_map() -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        for code, name in config.chart_candidates("kr"):
            names.setdefault(code, name)
    except Exception:  # noqa: BLE001
        pass
    for section in config.SECTIONS:
        for inst in section.instruments:
            if inst.source == "naver" and inst.symbol.isdigit():
                names[inst.symbol] = inst.name
    return names


def _kr_watch_codes(use_demo: bool) -> list[str]:
    """보유 → 관심 → 국내 본주 순서, 중복 없이."""
    out = list(sorted(_kr_held_codes(use_demo)))
    for section in (config.SECTION_WATCHLIST, config.SECTION_LOCAL):
        for inst in section.instruments:
            if inst.source == "naver" and inst.symbol.isdigit():
                out.append(inst.symbol)
    return list(dict.fromkeys(out))


def _pool_map(fn, items, workers: int = 4) -> list:
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        return list(pool.map(fn, items))


@swr.cached(1_800, stale=6 * 3_600)
def load_kr_flows(codes: tuple[str, ...], use_demo: bool) -> dict:
    """{코드: (일별 수급 최신순, 출처, 실패 사유)}. 30분 캐시.

    네이버 수급은 장 마감 뒤 확정치가 올라옵니다. 장중 숫자는 잠정입니다.
    """
    if use_demo:
        return demo_mod.demo_kr_flows(codes)
    from sources import naver_extra  # noqa: PLC0415
    got = _pool_map(lambda c: naver_extra.fetch_flows(c, 40), codes)
    return dict(zip(codes, got))


@swr.cached(43_200, stale=3 * 86_400)
def load_dividends(symbols: tuple[str, ...], use_demo: bool) -> dict:
    """{야후 심볼: {history, ex_date, pay_date, error}}. 12시간 캐시."""
    if use_demo:
        return demo_mod.demo_dividends(symbols)
    from sources import yahoo_events  # noqa: PLC0415
    return yahoo_events.fetch_many(yahoo_events.fetch_dividends, list(symbols))


@swr.cached(21_600, stale=2 * 86_400)
def load_us_earnings(symbols: tuple[str, ...], use_demo: bool) -> dict:
    """{티커: {rows, error}}. 6시간 캐시."""
    if use_demo:
        return demo_mod.demo_us_earnings(symbols)
    from sources import yahoo_events  # noqa: PLC0415
    return yahoo_events.fetch_many(yahoo_events.fetch_earnings, list(symbols))


@swr.cached(21_600, stale=2 * 86_400)
def load_kr_quarters(codes: tuple[str, ...], use_demo: bool) -> dict:
    """{코드: (분기 목록, 실패 사유)}. 6시간 캐시."""
    if use_demo:
        return demo_mod.demo_kr_quarters(codes)
    from sources import naver_extra  # noqa: PLC0415
    return dict(zip(codes, _pool_map(naver_extra.fetch_quarter, codes)))


def render_supply_tab(use_demo: bool) -> None:
    """한국 — 종목별 외국인·기관 수급 (5일 · 20일)."""
    held = _kr_held_codes(use_demo)
    names = _kr_name_map()
    mine = _kr_watch_codes(use_demo)
    wide = st.toggle("차트 조건 후보 전체 (약 50종목 — 처음 30~60초)",
                     value=False, key="supply_wide")
    codes = list(mine)
    if wide:
        codes += [c for c, _n in config.chart_candidates("kr") if c not in codes]
    raw = load_kr_flows(tuple(codes), use_demo)
    sums = []
    for code in codes:
        rows, src, err = raw.get(code, ([], "", "받지 못함"))
        sums.append(flows.summarize(code, rows, name=names.get(code, code),
                                    source=src, error=err, held=code in held))
    sums.sort(key=flows.rank_key)
    ok = [s for s in sums if not s.error]
    last = max((s.last_date for s in ok), default="")
    st.markdown(
        ui.render_section_head(
            "수급 — 외국인 · 기관",
            (f"{last} 까지 · " if last else "") + "5일 · 20일 누적, 금액은 근사",
            len(ok)),
        unsafe_allow_html=True)
    st.markdown(ui.render_flow_table(sums), unsafe_allow_html=True)
    srcs = sorted({s.source for s in ok if s.source})
    st.markdown(ui.render_footnote(
        "<b>숫자만 셉니다.</b> 순매수는 원인이기도 하고 결과이기도 해서(오르니까 "
        "사는 것일 수도) 방향을 말해주지 않습니다. 금액은 '그날 순매수 주식 수 × "
        "그날 종가' 의 합이라 실제 체결 금액과 다릅니다. 장중에는 잠정치이고 장 "
        "마감 뒤 확정됩니다. 연속 일수는 최근부터 같은 방향이 이어진 날 수 "
        "(+ 순매수 / − 순매도). 출처: " + (_esc_plain(", ".join(srcs)) if srcs else "—")
        + ". <b>공매도·신용잔고는 아직 없습니다</b> — 이 서버에서 닿는 출처를 "
        "확인한 뒤 붙입니다 (설정 → 진단 → '국내 수급·실적 확인')."),
        unsafe_allow_html=True)


def _dividend_targets(use_demo: bool) -> list[tuple[str, str, str, bool]]:
    """(야후 심볼, 이름, 시장, 보유) — 관심·본주 + 보유."""
    us_held = _us_held_symbols(use_demo)
    kr_held = _kr_held_codes(use_demo)
    out: dict[str, tuple[str, str, str, bool]] = {}
    for section in (config.SECTION_WATCHLIST, config.SECTION_LOCAL):
        for inst in section.instruments:
            if inst.source == "yahoo":
                out[inst.symbol] = (inst.symbol, inst.name, "us",
                                    inst.symbol in us_held)
            elif inst.source == "naver" and inst.symbol.isdigit():
                ysym = inst.fundamental_symbol or f"{inst.symbol}.KS"
                out[ysym] = (ysym, inst.name, "kr", inst.symbol in kr_held)
    names = _kr_name_map()
    for code in kr_held:
        if not any(k.startswith(code + ".") for k in out):
            out[f"{code}.KS"] = (f"{code}.KS", names.get(code, code), "kr", True)
    for sym in us_held:
        out.setdefault(sym, (sym, sym, "us", True))
    return list(out.values())


def _price_for(data, ysym: str) -> float | None:
    code = ysym.split(".")[0]
    for bucket, key in (("yahoo", ysym), ("naver", code)):
        q = ((data or {}).get(bucket) or {}).get(key)
        if q is not None and getattr(q, "price", None):
            return q.price
    return None


def _dividend_views(data, use_demo: bool, today) -> list:
    targets = _dividend_targets(use_demo)
    raw = load_dividends(tuple(t[0] for t in targets), use_demo)
    views = []
    for ysym, name, market, held in targets:
        d = raw.get(ysym) or {}
        views.append(dividends.analyze(
            ysym, name, market, d.get("history") or [], today,
            announced_ex=d.get("ex_date") or "", pay_date=d.get("pay_date") or "",
            price=_price_for(data, ysym), currency="KRW" if market == "kr" else "USD",
            error=d.get("error") or "", held=held))
    return views


def _latest_kr_earnings_filings(use_demo: bool) -> dict:
    """시장 공시 캐시에서 잠정실적 공시만 (기다리지 않음 — 있으면 씀)."""
    try:
        value = load_market_filings.peek(use_demo, dart.key_fingerprint())
    except Exception:  # noqa: BLE001
        value = None
    scan = value[0] if isinstance(value, tuple) and value else None
    out: dict = {}
    for f in getattr(scan, "filings", None) or []:
        if f.kind == "실적" and f.stock_code and f.stock_code not in out:
            out[f.stock_code] = f
    return out


def render_earnings_tab(use_demo: bool, *, market: str = "kr") -> None:
    """실적 서프라이즈 — 발표 실적 vs 발표 전 추정치."""
    today = dt.datetime.now(KST).date()
    if market == "us":
        us_held = _us_held_symbols(use_demo)
        targets = [(i.symbol, i.name) for i in config.SECTION_WATCHLIST.instruments
                   if i.source == "yahoo"]
        targets += [(s, s) for s in sorted(us_held)
                    if s not in {t for t, _n in targets}]
        raw = load_us_earnings(tuple(t for t, _n in targets), use_demo)
        views = [earnings.us_view(sym, name, (raw.get(sym) or {}).get("rows"),
                                  today, error=(raw.get(sym) or {}).get("error", ""),
                                  held=sym in us_held)
                 for sym, name in targets]
        st.markdown(ui.render_section_head(
            "실적 서프라이즈 · 미국", "EPS 추정치 vs 발표치 — 최근 4분기",
            sum(1 for v in views if v.reported)), unsafe_allow_html=True)
        st.markdown(ui.render_us_earnings(views, today), unsafe_allow_html=True)
        return

    held = _kr_held_codes(use_demo)
    names = _kr_name_map()
    codes = _kr_watch_codes(use_demo)
    raw = load_kr_quarters(tuple(codes), use_demo)
    store = earnings.ConsensusStore(os.path.join(swr.DISK_DIR, "consensus.json"))
    filings = _latest_kr_earnings_filings(use_demo)
    views = []
    for code in codes:
        periods, err = raw.get(code, ([], "받지 못함"))
        views.append(earnings.kr_view(
            code, names.get(code, code), periods,
            store=None if use_demo else store, today=today, error=err,
            held=code in held, filing=filings.get(code)))
    if use_demo:
        demo_mod.demo_fill_kr_surprise(views)
    st.markdown(ui.render_section_head(
        "실적 서프라이즈 · 한국", "최근 분기 실적 · 전년 동기 대비 · 다음 분기 컨센서스",
        sum(1 for v in views if v.latest)), unsafe_allow_html=True)
    st.markdown(ui.render_kr_earnings(views), unsafe_allow_html=True)


def render_research_tab(use_demo: bool) -> None:
    """산업 리포트 — 증권사 산업분석 리포트를 업종별로 정리 (제목·링크).

    본문과 요약문은 싣지 않습니다 (증권사 저작물). 제목·증권사·날짜와
    원문 링크만 두고, 요약은 'Claude 에 요약 요청' 링크로 넘깁니다 —
    이 서버에는 문서를 읽고 요약할 AI 가 없습니다.
    """
    reports, err = load_research("industry", use_demo)
    lo, hi = research.date_range(reports)
    span = f"{lo[5:]} ~ {hi[5:]}" if lo else "기간 알 수 없음"
    st.markdown(
        ui.render_section_head(
            "산업 리포트", f"증권사 산업분석 · 네이버 증권 리서치 · {span}",
            len(reports)),
        unsafe_allow_html=True,
    )
    if not reports:
        st.markdown(ui.render_notice(
            "<b>리포트 목록을 받지 못했습니다.</b> "
            f"{err or '사유 없음'} — 설정 → 진단의 '리서치 목록 확인' 을 "
            "누르면 실제 응답이 어떻게 왔는지 나옵니다."),
            unsafe_allow_html=True)
        return
    st.markdown(
        ui.render_footnote(
            "<b>제목과 링크만 싣습니다.</b> 리포트 본문은 증권사의 저작물이라 "
            "옮기지 않고 원문으로 보냅니다. 증권사 리포트는 매수 의견 비중이 "
            "매우 높습니다 — 결론보다 근거가 된 숫자를 보십시오."),
        unsafe_allow_html=True,
    )
    groups = research.by_category(reports)
    st.markdown(
        ui.render_section_head("업종별 보고서 수",
                               "어느 업종에 리포트가 몰리는가", len(groups)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_research_counts(groups), unsafe_allow_html=True)

    cats = ["전체"] + [c for c, _rs in groups]
    counts = {c: len(rs) for c, rs in groups}
    pick = st.selectbox(
        "업종", cats, key="research_cat",
        format_func=lambda c: c if c == "전체" else f"{c} ({counts.get(c, 0)})")
    if pick not in cats:
        pick = "전체"
    shown = reports if pick == "전체" else dict(groups).get(pick, [])
    st.markdown(
        ui.render_section_head(
            "리포트 목록" if pick == "전체" else f"{pick} 리포트",
            "제목을 누르면 원문이 열립니다", len(shown)),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_research_table(shown, show_category=(pick == "전체")),
        unsafe_allow_html=True,
    )
    if pick != "전체" and shown:
        st.markdown(
            ui.render_prompt_links(research.summary_prompt(pick, shown)),
            unsafe_allow_html=True,
        )
        st.markdown(
            ui.render_footnote(
                "링크를 누르면 이 업종 리포트의 제목과 PDF 주소가 채워진 채로 "
                "Claude 가 열립니다. Claude 가 PDF 를 열지 못하면 파일을 내려받아 "
                "첨부하십시오."),
            unsafe_allow_html=True,
        )


def render_sector_heat_tab(use_demo: bool) -> None:
    """섹터 온도 — 업종별로 어디가 뜨겁고 어디가 식었나."""
    rows = load_sector_heat(use_demo)
    st.markdown(
        ui.render_section_head(
            "섹터 온도", "KODEX 업종 ETF · KODEX 200 대비 1개월 순",
            len([r for r in rows if not r.benchmark])),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>왜 'KODEX 200 대비' 로 줄을 세우나.</b> 업종 하나가 5% 올랐어도 "
            "시장 전체가 6% 올랐다면 그 업종은 <b>덜 오른</b> 것입니다. "
            "업종 순환(어디로 돈이 옮겨가나)을 보려면 절대 수익률이 아니라 "
            "시장 대비 수익률을 봐야 합니다.<br>"
            "업종지수를 직접 받을 공개 경로가 없어 <b>ETF 를 대용</b>으로 "
            "씁니다. 운용보수·추적오차 때문에 실제 업종지수와 조금 다를 수 "
            "있습니다."),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_sector_heat_summary(rows), unsafe_allow_html=True)
    st.markdown(ui.render_sector_heat(rows), unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "색 진하기는 크기입니다 — 기간마다 눈금이 다릅니다(1일 ±3% · "
            "1주 ±6% · 1개월 ±12% · 3개월 ±25% 에서 가장 진함). 하나로 두면 "
            "1일은 늘 연하고 3개월은 늘 진해서 색이 정보를 못 줍니다.<br>"
            "52주 위치는 지난 1년 저가(왼쪽)~고가(오른쪽) 사이 어디인지입니다. "
            "3개월 추이의 점선은 시작점입니다."),
        unsafe_allow_html=True,
    )


def _kr_my_codes(use_demo: bool) -> set[str]:
    """보유(PORTFOLIO) + 관심(워치리스트) 국내 종목 코드."""
    codes = {i.symbol for i in config.SECTION_WATCHLIST.instruments
             if i.source == "naver" and i.symbol.isdigit()}
    try:
        positions, _bad, _src = portfolio.load(use_demo)
        codes |= {p.symbol for p in positions if p.market == "kr"}
    except Exception:  # noqa: BLE001 — 보유 파싱 실패가 공시 화면을 막으면 안 됨
        pass
    return codes


def _multi_pick(label: str, options: list[str], key: str,
                fmt=None, help_text: str = "") -> list[str]:
    """여러 개 고르기 — st.pills 가 있으면 칩, 없으면 multiselect."""
    fmt = fmt or (lambda x: x)
    # 새로고침으로 선택지가 바뀌면(그 유형 공시가 사라짐) 세션에 남은 옛 값이
    # 위젯 오류를 냅니다. 그리기 전에 지금 있는 선택지만 남깁니다.
    for k in (key, key + "_m"):
        old = st.session_state.get(k)
        if isinstance(old, (list, tuple)):
            keep = [x for x in old if x in options]
            if len(keep) != len(old):
                st.session_state[k] = keep
    pills = getattr(st, "pills", None)
    if pills is not None:
        try:
            picked = pills(label, options, selection_mode="multi",
                           format_func=fmt, key=key, help=help_text or None)
            return list(picked or [])
        except TypeError:
            pass
    return list(st.multiselect(label, options, format_func=fmt,
                               key=key + "_m", help=help_text or None))


def _render_market_filings(use_demo: bool) -> None:
    """시장 공시 — 묶음별 건수 → 필터(묶음·세부·시장·내 종목) → 표 → 설명."""
    scan, f_err = load_market_filings(use_demo, dart.key_fingerprint())
    filings = list(getattr(scan, "filings", []) or [])
    begin = getattr(scan, "begin", "") or ""
    st.markdown(
        ui.render_section_head(
            "한국 — 주요 공시",
            (f"{begin[5:]} 이후 · " if begin else "최근 5일 · ")
            + "코스피·코스닥 · 세부 유형별",
            len(filings)),
        unsafe_allow_html=True,
    )
    if f_err or not filings:
        st.markdown(ui.render_market_filings(filings, error=f_err, scan=scan),
                    unsafe_allow_html=True)
        return

    counts = dart.count_filings(filings)
    present = [g for g, _n, _s in counts]
    n_of = {g: n for g, n, _s in counts}
    groups = _multi_pick("분류", present, "filing_groups",
                         fmt=lambda g: f"{g} {n_of.get(g, 0)}",
                         help_text="아무것도 안 고르면 전부입니다.")
    st.markdown(ui.render_filing_counts(counts, active=groups),
                unsafe_allow_html=True)

    subs: list[str] = []
    if len(groups) == 1:
        sub_counts = next((sc for g, _n, sc in counts if g == groups[0]), [])
        sub_n = dict(sub_counts)
        subs = _multi_pick(f"{groups[0]} 세부", [s for s, _c in sub_counts],
                           f"filing_subs_{groups[0]}",
                           fmt=lambda x: f"{x} {sub_n.get(x, 0)}")

    my_codes = _kr_my_codes(use_demo)
    c1, c2 = st.columns([3, 2])
    with c1:
        picker = getattr(st, "segmented_control", None)
        opts = ["전체", "코스피", "코스닥"]
        market = None
        if picker is not None:
            try:
                market = picker("시장", opts, default="전체",
                                key="filing_market")
            except TypeError:
                market = None
        if market is None:
            market = st.radio("시장", opts, horizontal=True,
                              key="filing_market_r")
    with c2:
        only_mine = st.toggle(
            f"내 종목만 ({len(my_codes)})", value=False, key="filing_mine",
            disabled=not my_codes,
            help="보유(Secrets 의 PORTFOLIO)와 워치리스트의 국내 종목.")

    chosen = dart.filter_filings(
        filings, groups=groups, subs=subs,
        market="" if market in (None, "전체") else market,
        codes=my_codes if only_mine else None)
    mine_hits = sum(1 for f in filings if f.stock_code in my_codes)
    st.markdown(ui.render_notice(
        f"<b>{len(chosen)}건</b> / 추린 공시 {len(filings)}건"
        + (f" · 읽은 공시 {scan.scanned:,}건" if getattr(scan, "scanned", 0) else "")
        + (f" · <b>내 종목 {mine_hits}건</b>" if mine_hits else "")),
        unsafe_allow_html=True)
    st.markdown(ui.render_market_filings(chosen, held=my_codes, scan=scan),
                unsafe_allow_html=True)
    with st.expander("유형별로 무엇을 보면 되나"):
        st.markdown(ui.render_filing_guide(dart.DISCLOSURE_TYPES,
                                           dart.DISCLOSURE_GROUPS),
                    unsafe_allow_html=True)


def _flows_korea(use_demo: bool) -> None:
    st.markdown(
        ui.render_section_head(
            "한국 — 섹터별 뉴스", "업종 바람이 먼저 불고 종목이 따라갑니다",
            len(config.KR_SECTORS)),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "종목 뉴스와 다릅니다. 종목 뉴스는 '내 종목에 무슨 일이' 고, "
            "이건 '내 종목이 속한 업종에 무슨 바람이' 입니다. "
            "구글 뉴스를 한국어로 부르며 <b>제목과 링크만</b> 가져옵니다."),
        unsafe_allow_html=True,
    )
    sector_news, sector_errors = load_sector_news(use_demo)
    st.markdown(
        ui.render_sector_news(config.KR_SECTORS, sector_news, sector_errors),
        unsafe_allow_html=True,
    )

    _render_market_filings(use_demo)

    kr_rows = load_kr_macro(use_demo, fred.key_fingerprint())
    st.markdown(
        ui.render_section_head("한국 — 경제지표", "FRED 경유 · 전년동월비 병기",
                               len(kr_rows)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_simple_rows(kr_rows), unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "<b>한국 계열 ID 는 전부 미검증입니다.</b> FRED 의 한국 통계는 "
            "OECD 경유라 ID 체계가 미국 계열과 다르고 중단된 것도 많습니다. "
            "'—' 로 나오면 그 계열이 없는 것이니 진단 패널에서 확인하고 "
            "config 에서 지우십시오. 원자료는 한국은행 ECOS 가 정확하지만 "
            "별도 키가 필요합니다."),
        unsafe_allow_html=True,
    )


def _flows_us(use_demo: bool) -> None:
    readings, _errs = load_inflation(use_demo, fred.key_fingerprint())
    st.markdown(
        ui.render_section_head("미국 — 물가 속도", "지수가 아니라 속도로",
                               len([r for r in readings if r.ok])),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>전년동월비 하나만 보면 늦습니다</b> — 12개월 전 숫자를 아직 "
            "끌고 다니기 때문입니다. <b>3개월 연율</b>은 최근 3개월 변화를 "
            "1년치로 환산한 것이라 가장 빠릅니다. 3개월 연율이 전년동월비보다 "
            "높으면 물가가 다시 붙는 중이고, 낮으면 식는 중입니다 — "
            "이건 해석이 아니라 산술입니다.<br>"
            "비계절조정 계열(PPI 전체상품)은 전월비·연율을 내지 않습니다. "
            "계절 패턴이 물가 상승으로 보이기 때문입니다."),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_inflation_table(readings), unsafe_allow_html=True)
    st.caption(inflation.summary_line(readings))

    nl, extra = load_liquidity(use_demo, fred.key_fingerprint())
    st.markdown(
        ui.render_section_head("글로벌 — 유동성", "연준 순유동성 + 주요국 중앙은행"),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_liquidity(nl, extra), unsafe_allow_html=True)


def render_diag_panel() -> None:
    """진단 — 터미널 없이 버튼으로. 페이지 상단 패널에 들어갑니다.

    이 대시보드의 일부는 실제 API 응답을 받아본 적이 없습니다(개발 환경에서
    DART·SEC·FRED 가 차단). 버튼을 누르면 실제로 되는지 확인해 주고, 출력을
    복사해 Claude 에 붙이면 틀린 부분을 고칠 수 있습니다.
    """
    st.caption(
        "일부 데이터는 실제 응답으로 확인되지 않았습니다. 버튼을 누르면 "
        "실제로 되는지 확인합니다. 출력을 복사해 Claude 에 붙여넣으십시오. "
        "인증키는 출력에 들어가지 않습니다 (끝 4자리만)."
    )

    # 캐시 비우기 — 국내 재무는 24시간, 공시는 30분 캐시됩니다. DART 키를
    # 새로 넣으면 지문이 바뀌어 자동으로 무효화되지만, 그 밖의 이유로
    # 오래된 값을 치우고 싶을 때가 있습니다.
    if st.button("캐시 비우고 다시 불러오기", width="stretch"):
        st.cache_data.clear()
        swr.clear_all()
        st.success("캐시를 비웠습니다. 다음 화면부터 새로 받아옵니다.")
        st.rerun()
    st.caption(
        "국내 재무 24시간 · 공시 30분 · 시세 수십 초 단위로 캐시합니다. "
        "DART 키를 Secrets 에 **새로 넣은 경우에는 누를 필요가 없습니다** — "
        "키 지문이 바뀌면 캐시가 저절로 무효화됩니다."
    )

    import io
    from contextlib import redirect_stdout

    from tools import diagnose as diag

    # 키를 Secrets 에 넣기 전에 **되는지 먼저** 보고 싶을 때가 있습니다.
    # 여기에 넣은 값은 이 세션에서만 쓰이고 저장하지 않습니다.
    _fred_src = fred.key_source()
    st.caption(f"FRED 키 출처: **{_fred_src}**")
    if _fred_src != "Secrets (환경변수)":
        _typed = st.text_input(
            "FRED 키 임시 입력 (저장하지 않습니다)", value="",
            type="password", key="fred_tmp_key",
            help="Secrets 에 넣기 전에 되는지 확인용입니다. 새로고침하면 "
                 "사라집니다. 확인되면 Secrets 에 최상위 레벨로 "
                 'FRED_API_KEY = "…" 를 넣으십시오.',
        )
        if _typed and _typed.strip() != fred.api_key():
            fred.set_session_key(_typed)
            st.cache_data.clear()
            swr.clear_all()
            st.rerun()

    # 함수를 **이름으로** 찾습니다. 직접 참조하면 tools/diagnose.py 가
    # 옛날 파일일 때 이 목록을 만드는 순간 AttributeError 로 앱 전체가
    # 죽습니다 — 2026-11-11 에 실제로 그렇게 죽었습니다. 진단 하나가
    # 없는 것과 앱이 안 켜지는 것은 심각도가 다릅니다.
    specs = (
        ("fredkey", "FRED 키 확인 (한 계열만)", "diagnose_fred_key",
         "키 형식 → 연결 → 실제 호출을 순서대로 봅니다. 계열 14개를 다 "
         "돌리지 않아 **빠르고**, 실패하면 응답 본문에서 사유를 그대로 "
         "보여줍니다. 물가·유동성이 전부 비면 여기부터 누르십시오."),
        ("fred", "경제지표 계열 확인", "diagnose_fred",
         f"FRED 계열 {len(config.MACRO_SERIES)}개가 실제로 받아지는지. "
         "연결 자체도 먼저 시험합니다. 키 불필요."),
        ("fredx", "FRED 추가 계열 확인", "diagnose_fred_extra",
         "물가 6 · 유동성 6 · 한국 6 계열. 매크로 14개와 **다른 계열**이라 "
         "따로 봐야 합니다. 유동성은 받은 값의 크기까지 찍어서 단위가 "
         "맞는지 확인합니다 — 틀리면 1000배 어긋납니다. **인증키 필요.**"),
        ("screen", "미국 스크리너 확인", "diagnose_screen",
         "companyfacts 에서 계정이 잡히는지 (앞 8개 기업). 키 불필요."),
        ("xbrl", "재고 지표 확인 (미국)", "diagnose_xbrl",
         "MU 의 XBRL 태그와 DIO 계산. 키 불필요."),
        ("dart", "DART 확인 (국내)", "diagnose_dart",
         "재고 구성 계정과 DIO. **인증키 필요.**"),
        ("krexp", "반도체 수출 확인 (한국)", "diagnose_kr_exports",
         "산업통상부 보도자료 긁기. **한 번도 성공한 적 없는 경로입니다** — "
         "막혀 있으면 쓰지 않는 게 맞습니다. 키 불필요."),
        ("krsrc", "국내 데이터 출처 확인", "diagnose_kr_sources",
         "네이버 일봉·투자지표, DART 작은 요청·고유번호 ZIP 이 이 서버에서 "
         "닿는지와 걸린 시간. 한국 종목발굴이 0 건이거나 'DART 요청 실패' "
         "가 보이면 여기부터 누르십시오."),
        ("filings", "시장 공시 확인 (국내)", "diagnose_filings",
         "공시 유형(주요사항·거래소·지분)별로 실제로 몇 건이 오는지, "
         "어느 세부 유형으로 분류됐는지, **분류에서 빠진 제목**이 무엇인지. "
         "빠진 것 중 봐야 할 유형이 있으면 알려 주시면 넣습니다. "
         "**인증키 필요.**"),
        ("krsupply", "국내 수급·실적 확인", "diagnose_kr_supply",
         "네이버 수급 두 경로(모바일 JSON · PC 표)와 분기 실적표(컨센서스 "
         "포함)가 받아지는지, 필드가 제대로 읽히는지. 공매도·신용잔고 단서도 "
         "찾아 찍습니다. **세 경로 모두 실제 응답으로 검증하지 못했습니다.**"),
        ("yahooev", "야후 배당·실적 확인", "diagnose_yahoo_events",
         "배당 이력·다음 배당락일·EPS 추정 vs 실제가 오는지 (MSFT · O · 삼성전자)."),
        ("research", "리서치 목록 확인", "diagnose_research",
         "네이버 증권 리서치의 산업분석·시황 목록이 받아지는지, 줄마다 업종·"
         "제목·증권사·날짜·PDF 가 제대로 읽히는지. **이 해석기는 실제 응답으로 "
         "검증하지 못했으므로** 산업 리포트가 비거나 이상하면 눌러 보십시오."),
        ("krcode", "국내 종목코드 대조", "diagnose_kr_codes",
         "config 의 6자리 코드가 실제로 그 회사인지 DART corpCode.xml 로 "
         "맞춰봅니다. 코드가 틀리면 **다른 회사 재무를 조용히 가져옵니다.** "
         "코스닥을 추가한 뒤 한 번은 돌려야 합니다. **인증키 필요.**"),
    )
    checks = [(k, t, d, getattr(diag, fname, None))
              for k, t, fname, d in specs]
    stale = [t for _k, t, _d, fn in checks if fn is None]
    if stale:
        st.warning(
            "**tools/diagnose.py 가 이 버전과 맞지 않습니다.** "
            f"없는 진단: {', '.join(stale)}. 그 파일을 다시 올리십시오 — "
            "나머지 진단은 그대로 씁니다.",
            icon="⚠️",
        )
    checks = [c for c in checks if c[3] is not None]

    for key, title, desc, fn in checks:
        if st.button(title, key=f"diag_{key}", help=desc,
                     use_container_width=True):
            with st.spinner(f"{title} — 실제 응답을 받아오는 중…"):
                buffer = io.StringIO()
                try:
                    with redirect_stdout(buffer):
                        fn()
                    output = buffer.getvalue()
                except Exception as exc:  # noqa: BLE001
                    output = (buffer.getvalue()
                              + f"\n\n예외: {type(exc).__name__}: {exc}")
            st.session_state[f"diag_out_{key}"] = output

        output = st.session_state.get(f"diag_out_{key}")
        if output:
            st.code(output, language="text")
            st.caption("전체 복사해서 Claude 에 붙여넣으십시오.")

    st.caption(
        "터미널에서도 됩니다: `python -m tools.diagnose --fred` "
        "(또는 `--screen`, `--xbrl`, `--dart`, 전부는 인자 없이)."
    )


def render_screen_kr_tab(use_demo: bool) -> None:
    """국내주식 발굴 — DART 사업보고서 기반. 인증키가 필요합니다."""
    candidates = config.screen_kr_candidates()
    st.markdown(
        ui.render_section_head(
            "국내주식 발굴 (버핏식 숫자 기준)",
            "DART 사업보고서 10년치 — 보고서 1회당 3년이 나옵니다",
            len(candidates),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>기준선이 미국과 다릅니다.</b> 미국 기준(ROE 15% 이상 10년 중 8년)을 "
            "한국 종목에 그대로 적용하면 거의 전부 탈락합니다 — 기업이 나빠서가 "
            "아니라 한국 상장사의 ROE 분포가 구조적으로 낮기 때문입니다. "
            "그러면 \"한국 주식은 다 안 좋다\" 는 결론이 나오는데 그건 "
            "<b>기준이 틀린 것</b>입니다. 그래서 ROE 10%·D/E 0.6·마진 ±7%p 로 "
            "낮췄습니다 — <b>버핏의 숫자가 아니라 제가 분포를 보고 정한 값</b>이니 "
            "<code>buffett_kr.KR_THRESHOLDS</code> 에서 바꾸십시오."
        ),
        unsafe_allow_html=True,
    )

    ok, msg = dart.key_status()
    if not ok and not use_demo:
        st.markdown(
            ui.render_footnote(
                f"<b>DART 인증키가 필요합니다.</b> {_esc_plain(msg)} "
                "환경변수 <code>DART_API_KEY</code> 에 넣으십시오 "
                "(opendart.fss.or.kr 에서 무료 발급). "
                "미국 발굴 탭은 키 없이 동작합니다."
            ),
            unsafe_allow_html=True,
        )
        return

    col1, col2 = st.columns([1, 1])
    with col1:
        min_pass = st.slider("최소 통과 기준 수", 0, len(buffett.CRITERIA),
                             round(len(buffett.CRITERIA) / 2),
                             key="screen_kr_min")
    with col2:
        show_source = st.toggle("각 기준의 출처와 한계 표시", value=False,
                                key="screen_kr_src")

    screens_map, errors = load_kr_screens(use_demo, dart.key_fingerprint())
    screens = buffett.rank(list(screens_map.values()))
    triples = _attach_dcf(screens, use_demo, currency="KRW")

    if not triples:
        st.markdown(
            ui.render_notice(
                "<b>스크리닝 결과가 없습니다.</b> "
                + (" · ".join(f"{t}: {m[:70]}" for t, m in list(errors.items())[:4])
                   if errors else "데이터를 받아오지 못했습니다.")
            ),
            unsafe_allow_html=True,
        )
        return

    _render_screen_body(triples, min_pass=min_pass, show_source=show_source,
                        criteria=buffett.CRITERIA)

    if errors:
        st.markdown(
            ui.render_notice(
                f"<b>조회 실패 {len(errors)}건:</b> "
                + " · ".join(f"{t} ({m[:50]})" for t, m in list(errors.items())[:5])
            ),
            unsafe_allow_html=True,
        )


@swr.cached(config.SCREEN_CACHE_TTL_SEC)
def load_kr_screens(use_demo: bool, key_fp: str = "") -> tuple[dict, dict]:
    """국내 스크리닝. 종목당 사업보고서 4회 요청(각 3년)."""
    if use_demo:
        return demo_mod.demo_kr_screens()

    candidates = config.screen_kr_candidates()
    th = buffett_kr.kr_thresholds()
    try:
        corp_map = dart.fetch_corp_codes()
    except dart.DartError as exc:
        return {}, {code: f"고유번호 조회 실패: {exc}" for code, _n in candidates}

    latest_year, _q = dart.latest_available_quarter()
    screens: dict[str, object] = {}
    errors: dict[str, str] = {}

    jobs: list[tuple[str, str, str]] = []
    for code, name in candidates:
        corp = dart.resolve_corp_code(code, corp_map,
                                      config.DART_CORP_CODE_OVERRIDES)
        if not corp:
            errors[code] = "고유번호를 찾지 못했습니다."
            continue
        jobs.append((code, corp, name))

    def one(job: tuple[str, str, str]):
        code, corp, name = job
        try:
            return code, buffett_kr.fetch_and_screen(
                code, corp, name, latest_year=latest_year - 1,
                reports=config.SCREEN_KR_REPORTS,
                years=config.SCREEN_YEARS, th=th), None
        except Exception as exc:  # noqa: BLE001 - 한 종목 실패가 전체를 막으면 안 됩니다
            return code, None, f"{type(exc).__name__}: {exc}"

    # 종목당 사업보고서 4회씩 순차로 돌리면 30종목 = 120회 왕복입니다.
    # dart._throttle 이 시작 간격을 지키므로 겹쳐도 한도는 유지됩니다.
    if jobs:
        with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
            for code, screen, err in pool.map(one, jobs):
                if err is not None:
                    errors[code] = err
                elif screen is not None and screen.ok:
                    screens[code] = screen
                elif screen is not None:
                    errors[code] = screen.error
    return screens, errors


def _esc_plain(text: object) -> str:
    import html as _html
    return _html.escape(str(text), quote=True)


def render_screen_tab(use_demo: bool) -> None:
    """종목 발굴 — 버핏식 숫자 기준으로 '읽을 목록' 을 줄입니다."""
    st.markdown(
        ui.render_section_head(
            "종목 발굴 (버핏식 숫자 기준)",
            "10년치 공시로 후보를 줄입니다 — 매수 목록이 아닙니다",
            len(config.screen_tickers()),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>이 화면이 하는 일:</b> 10년치 공시 숫자로 <b>읽어볼 만한 후보</b>를 "
            "줄입니다. <b>하지 않는 일:</b> 무엇을 살지 판단하지 않습니다.<br>"
            "버핏 기준의 핵심인 <b>경제적 해자·경영진의 질·내가 이해하는 사업인가</b>는 "
            "숫자로 걸러지지 않습니다. 숫자가 좋은데 해자가 없는 회사가 많고, 그 구분은 "
            "10-K 와 어닝콜을 읽어야 압니다. 그래서 각 카드에 "
            "<b>그 다음에 물어볼 질문</b>을 붙였습니다.<br>"
            "<b>점수가 높다고 좋은 투자가 아닙니다</b> — 읽는 순서를 정하는 용도입니다."
        ),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        min_pass = st.slider(
            "최소 통과 기준 수", 0, len(buffett.CRITERIA),
            round(len(buffett.CRITERIA) * 2 / 3), key="screen_min",
            help="이 수 이상 통과한 기업만 카드로 봅니다. 표에는 전부 나옵니다.")
    with col2:
        show_source = st.toggle(
            "각 기준의 출처와 한계 표시", value=False, key="screen_src",
            help="버핏 원문인지, 인용 관행인지, 제가 정한 기준인지")

    screens_map, errors = load_screens(use_demo)
    screens = buffett.rank(list(screens_map.values()))
    triples = _attach_dcf(screens, use_demo, currency="USD")
    usable = [t[0] for t in triples]

    if not usable:
        st.markdown(
            ui.render_notice(
                "<b>스크리닝 결과가 없습니다.</b> "
                + (" · ".join(f"{t}: {m[:70]}" for t, m in list(errors.items())[:4])
                   if errors else "데이터를 받아오지 못했습니다.")
            ),
            unsafe_allow_html=True,
        )
        return

    _render_screen_body(triples, min_pass=min_pass, show_source=show_source,
                        criteria=buffett.CRITERIA)

    failed = [(t, m) for t, m in errors.items()]
    if failed:
        st.markdown(
            ui.render_notice(
                f"<b>조회 실패 {len(failed)}건:</b> "
                + " · ".join(f"{t} ({m[:50]})" for t, m in failed[:6])
            ),
            unsafe_allow_html=True,
        )


@swr.cached(1800)
def load_feargreed(use_demo: bool):
    """CNN 공포탐욕지수. 실패하면 error 가 담긴 객체가 돌아옵니다 —
    문서화되지 않은 내부 엔드포인트라 다른 지표와 격리해 둡니다."""
    if use_demo:
        return demo_mod.demo_feargreed()
    return feargreed.fetch()


@swr.cached(300)
def load_vix(use_demo: bool):
    """VIX 기간구조 + 백분위.

    시세(야후)와 과거 이력(FRED VIXCLS)을 합칩니다. 둘 다 키가 필요 없습니다.
    """
    if use_demo:
        return demo_mod.demo_vix()

    symbols = [sym for sym, _l, _d, _v in vix.FAMILY]
    try:
        quotes = yahoo.fetch_quotes(symbols)
    except Exception as exc:  # noqa: BLE001
        state = vix.VixState()
        state.error = f"VIX 시세 조회 실패 — {exc}"
        return state

    series = None
    try:
        series = fred.fetch_series(
            vix.FRED_SERIES,
            start=dt.date.today() - dt.timedelta(days=365 * 5 + 10))
    except Exception:  # noqa: BLE001
        series = None
    return vix.build_state(quotes, series)


def _render_briefing_body(bf) -> None:
    """브리핑 본문. 마크다운은 st.markdown 이 렌더해야 합니다 —
    HTML 문자열로 만들면 '# 제목' 이 글자 그대로 보입니다.

    HTML 브리핑은 unsafe_allow_html 로 넣습니다. 내용이 **사용자 자신의
    저장소 파일**이라 외부 입력이 아닙니다.
    """
    if not bf.body.strip():
        return
    st.markdown(bf.body, unsafe_allow_html=bf.is_html)


def render_briefing_section(use_demo: bool, *, readings=None,
                            triggers=None, fg=None, vix_state=None) -> None:
    """매크로 탭 맨 위.

    **대시보드가 가진 숫자로 직접 씁니다.** 전에는 외부 대시보드로 보내는
    링크였는데, 다른 화면으로 나가야 하면 이 대시보드를 여는 의미가
    없습니다. 카드는 조회용이고 브리핑은 통독용입니다.
    """
    exports, _exp_err = load_kr_exports(use_demo)
    trends, _tr_err = load_inventory_trends(use_demo, dart.key_fingerprint())

    lines = brief.compose(
        readings=readings, triggers=triggers, fg=fg, vix_state=vix_state,
        exports=exports, trends=trends,
    )
    st.markdown(
        ui.render_section_head(
            "증시 브리핑", "지금 화면의 숫자를 문장으로 — 오늘 달라진 것",
            len(lines)),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_brief(lines, brief.headline(lines), brief.as_of()),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>새로 받아오는 데이터가 없습니다.</b> 아래 카드에 이미 있는 "
            "값을 문장으로 엮은 것이라, 브리핑 때문에 느려지지 않습니다. "
            "받지 못한 값은 그 줄을 통째로 건너뜁니다 — 빈칸을 '보합' 같은 "
            "말로 메우지 않습니다."
        ),
        unsafe_allow_html=True,
    )

    briefings = load_briefings()
    if briefings:
        st.markdown(
            ui.render_section_head(
                "직접 쓴 브리핑", "briefings/ 폴더의 글을 날짜별로 읽어옵니다",
                len(briefings)),
            unsafe_allow_html=True,
        )
    if not briefings:
        with st.expander("직접 쓴 브리핑을 넣는 방법", expanded=False):
            st.markdown(ui.render_briefing_empty(bfs.example_file()),
                        unsafe_allow_html=True)
        return

    latest_bf = briefings[0]
    st.markdown(ui.render_briefing_head(latest_bf), unsafe_allow_html=True)
    _render_briefing_body(latest_bf)

    # 지난 글은 접어 둡니다 — 펼치면 매크로 지표가 한참 아래로 밀립니다
    rest = briefings[1:]
    if rest:
        with st.expander(f"지난 브리핑 {len(rest)}편", expanded=False):
            for bf in rest:
                st.markdown(ui.render_briefing_head(bf), unsafe_allow_html=True)
                _render_briefing_body(bf)


def render_macro_tab(data: dict[str, dict[str, Quote]], fx, use_demo: bool,
                     *, market: str = "all") -> None:
    """매크로 — 확인할 것 → 시세 → 심리 → 통계 순서.

    2026-11-11 개편. 전에는 시세 카드 7장 · 공포탐욕 · VIX · 임계값 카드 ·
    지표 카드 14장이 차례로 쌓여 세로 5,000px 가 넘었고, **확인해야 할
    임계값 도달**이 화면 세 장 아래에 있었습니다. 이제:

      1. 브리핑          — 사람이 읽는 문장
      2. 임계값 도달      — 한 줄씩. 헤드라인·질문은 접어 둠
      3. 시장가격         — 표 한 장 (카드 7장 대신)
      4. 심리            — 공포탐욕 | VIX 를 좌우로
      5. 경제지표 (FRED)  — 묶음별 표 한 장 (카드 14장 대신)
    """
    section = config.SECTION_BY_KEY.get("macro")

    # 1) 증시 브리핑 — 사람이 쓴 글이 숫자보다 먼저 옵니다.
    render_briefing_section(use_demo)

    # 통계는 2)와 5)가 같이 쓰므로 먼저 한 번 읽습니다 (캐시됨).
    series_map, errors = load_macro(use_demo, fred.key_fingerprint())
    readings = macro_mod.build_readings(config.macro_series(), series_map, errors)
    triggers = macro_mod.evaluate_all(readings)
    hit_keys = {t.reading.spec.key for t in triggers}

    # 2) 임계값을 건드린 것 — 이 화면에서 가장 먼저 봐야 하는 것
    if triggers:
        st.markdown(
            ui.render_section_head(
                "임계값 도달", "이 지표만 확인하십시오", len(triggers)),
            unsafe_allow_html=True,
        )
        st.markdown(ui.render_trigger_list(triggers), unsafe_allow_html=True)
        with st.expander("관련 헤드라인 · Claude 에 붙여넣을 질문", expanded=False):
            news_targets = tuple(
                macro_mod.news_queries(triggers, limit=config.MACRO_MAX_NEWS_TARGETS))
            headlines = load_news(news_targets, use_demo)
            for trig in triggers:
                st.markdown(
                    ui.render_macro_trigger(
                        trig,
                        macro_mod.prompt_for(trig),
                        headlines.get(trig.reading.spec.key) or (),
                    ),
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            ui.render_notice(
                "<b>임계값에 닿은 지표가 없습니다.</b> 조용한 게 정상입니다 — "
                "이 탭은 뉴스 피드가 아니라, 지표가 실제로 움직였을 때만 "
                "올라오게 만들었습니다."
            ),
            unsafe_allow_html=True,
        )

    # 3) 시장가격 — 야후, 실시간. 표 한 장.
    #
    # 매크로는 **일부러 시장별로 나누지 않습니다.** 미국 10년 국채 금리와
    # 달러인덱스는 국내 종목만 보는 날에도 봐야 하는 숫자입니다. 나누면
    # 한국을 고른 날 금리가 사라져서, 분리가 아니라 누락이 됩니다.
    if section is not None:
        st.markdown(
            ui.render_section_head(section.title, section.subtitle,
                                   len(section.instruments)),
            unsafe_allow_html=True,
        )
        st.markdown(
            ui.render_quote_table(
                [(inst, pick_quote(inst, data)) for inst in section.instruments]),
            unsafe_allow_html=True,
        )
        if section.footnote:
            st.markdown(ui.render_footnote(section.footnote),
                        unsafe_allow_html=True)
    if market == "kr":
        st.markdown(
            ui.render_footnote(
                "<b>한국 화면에서도 매크로는 '공통' 입니다.</b> 미국 금리·"
                "원달러·유가·VIX 는 국내 종목만 보는 날에도 같은 배경이라, "
                "한국 쪽으로 옮겨 놓지 않고 두 시장이 같이 씁니다."),
            unsafe_allow_html=True,
        )

    # 4) 심리 — 공포탐욕과 VIX 는 같은 묶음이라 좌우로 둡니다. 좁은
    #    화면에서는 스트림릿이 알아서 위아래로 쌓습니다.
    fg = load_feargreed(use_demo)
    vix_state = load_vix(use_demo)
    col_fg, col_vix = st.columns(2, gap="medium")
    with col_fg:
        st.markdown(
            ui.render_section_head(
                "공포탐욕지수 (CNN)", "시장 심리 0~100 · 세부 지표 7개",
                7 if fg.ok else 0,
            ),
            unsafe_allow_html=True,
        )
        st.markdown(ui.render_feargreed(fg), unsafe_allow_html=True)
        st.markdown(
            ui.render_footnote(
                "숫자가 안 맞는다고 느끼시면 "
                f'<a class="dash-inline-link" href="{feargreed.CNN_PAGE}" '
                'target="_blank" rel="noopener noreferrer">CNN 공식 페이지</a>'
                " 와 직접 대조해 보십시오. "
                + ("<b>지금은 데모 모드라 가짜 숫자입니다.</b>" if use_demo else
                   "다르면 화면 위쪽 진단 패널 → 경제지표 확인을 돌려 출력을 "
                   "알려주십시오 — 응답 구조가 바뀌었을 수 있습니다.")
            ),
            unsafe_allow_html=True,
        )
        if fg.ok and fg.extremes:
            st.markdown(
                ui.render_footnote(
                    "<b>지금 지수를 끌고 있는 것:</b> "
                    + " · ".join(f"{c.label} {c.score:,.0f}({c.band})"
                                 for c in fg.extremes)
                    + ". 지수 한 숫자만 보면 같은 '탐욕 70' 이 주가 모멘텀 "
                    "때문인지 채권 수요 때문인지 알 수 없어서, 극단에 있는 "
                    "세부 지표를 따로 적었습니다."
                ),
                unsafe_allow_html=True,
            )
        st.markdown(
            ui.render_footnote(
                "<b>출처 주의 —</b> CNN 이 자기 페이지에서 쓰는 "
                "<b>문서화되지 않은 내부 엔드포인트</b>입니다. 공개 API 가 "
                "아니라 예고 없이 바뀌거나 막힐 수 있어, 실패해도 다른 지표에 "
                "영향이 가지 않게 격리했습니다. 이 지수는 <b>심리 지표이고 "
                "가치 판단이 아닙니다</b> — 탐욕 구간이라고 비싸다는 뜻이 "
                "아닙니다."
            ),
            unsafe_allow_html=True,
        )
    with col_vix:
        st.markdown(
            ui.render_section_head(
                "VIX 기간구조",
                "곡선의 모양 · 과거 대비 위치",
                sum(1 for p in vix_state.points if p.ok),
            ),
            unsafe_allow_html=True,
        )
        st.markdown(ui.render_vix(vix_state), unsafe_allow_html=True)
        st.markdown(
            ui.render_footnote(
                "<b>VIX 숫자 하나는 쓸모가 적습니다.</b> 18 이 높은지 낮은지는 "
                "맥락 없이 답할 수 없어서, VIX 값에 두 가지를 붙였습니다 — "
                "<b>과거 대비 백분위</b>(FRED VIXCLS 5년)와 <b>기간구조</b>"
                "(VIX9D→VIX→VIX3M→VIX6M 곡선의 모양).<br>"
                "평소에는 뒤 만기가 더 높습니다(<b>콘탱고</b>). 위기에는 앞이 "
                "치솟아 뒤보다 높아집니다(<b>백워데이션</b>) — 2010년 이후 "
                f"전체 거래일의 <b>{vix.BACKWARDATION_BASE_RATE:g}%</b> 에만 "
                "나타났으니, 드물기 때문에 신호가 됩니다."
            ),
            unsafe_allow_html=True,
        )

    # 전 계열이 실패하면 카드 14장이 전부 오류로 뜹니다. 그보다 **왜**
    # 와 **무엇을 하면 되는지** 를 한 번 적는 쪽이 낫습니다.
    if readings and all(getattr(r, "error", None) for r in readings):
        _blocked = sum(1 for r in readings
                       if "응답 없음" in (r.error or "")
                       or "건너뜀" in (r.error or ""))
        if _blocked:
            _kp = fred.key_problem()
            _hint = (f"<br>지금 설정된 키에 문제가 있습니다 — {_kp}" if
                     (fred.api_key() and _kp) else
                     "<br>무료 키 발급(즉시): "
                     '<a class="dash-inline-link" target="_blank" '
                     'rel="noopener noreferrer" '
                     'href="https://fred.stlouisfed.org/docs/api/api_key.html">'
                     "fred.stlouisfed.org/docs/api/api_key.html</a>")
            st.markdown(
                ui.render_footnote(
                    "<b>FRED 지표를 하나도 받지 못했습니다.</b> "
                    f"{_blocked}개 계열이 응답 없음으로 끝났습니다 — 계열 ID "
                    "문제가 아니라 이 서버에서 <code>fred.stlouisfed.org</code> "
                    "로 나가는 길이 막힌 것으로 보입니다. "
                    "<b>FRED_API_KEY</b> 를 Secrets 에 넣으면 다른 호스트"
                    "(<code>api.stlouisfed.org</code>)로 받아옵니다."
                    + _hint),
                unsafe_allow_html=True,
            )

    # 5) 전체 지표 — 위의 '임계값 도달' 이 요약이고 여기가 전체 목록입니다
    st.markdown(
        ui.render_section_head(
            "경제지표 (FRED)",
            "발표 지연이 있는 통계 — 위 시세 표와 성격이 다릅니다",
            len(readings),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "위 표는 <b>시장가격</b>(실시간), 아래는 <b>통계</b>입니다. "
            "통계는 발표가 2~6주 늦으므로 줄마다 <b>관측 시점과 지연일수</b>를 "
            "함께 적었습니다 — 어제 숫자로 착각하면 판단이 틀립니다. "
            "지수 계열(산업생산·PPI)은 기준연도가 바뀌어 레벨 비교가 불가능하므로 "
            "<b>전년 동기 대비</b>만 표시합니다."
        ),
        unsafe_allow_html=True,
    )

    show_why = st.toggle("각 지표를 보는 이유 표시", value=False,
                         key="macro_why",
                         help="왜 이 지표가 제 포트폴리오와 연결되는지")
    by_group: dict[str, list] = {}
    for reading in readings:
        by_group.setdefault(reading.spec.group, []).append(reading)
    st.markdown(
        ui.render_macro_table(config.MACRO_GROUPS, by_group, hit_keys,
                              show_why=show_why),
        unsafe_allow_html=True,
    )

    unverified = [r.spec for r in readings if not r.spec.verified]
    if unverified:
        st.markdown(
            ui.render_footnote(
                "<b>계열 ID 미검증:</b> "
                + ", ".join(s.series_id for s in unverified)
                + ". 이 ID 들은 제가 직접 응답으로 확인하지 못했습니다 — "
                "<code>python -m tools.diagnose --fred</code> 로 검증하십시오. "
                "틀린 ID 는 404 로 조용히 비어 보입니다."
            ),
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 렌더링
# ──────────────────────────────────────────────────────────────────────────────

def render_section(section: Section, data: dict[str, dict[str, Quote]], fx,
                   *, market: str = "all") -> None:
    instruments = config.filter_instruments(section.instruments, market)
    st.markdown(
        ui.render_section_head(section.title, section.subtitle, len(instruments)),
        unsafe_allow_html=True,
    )
    if not instruments:
        st.markdown(
            ui.render_footnote(
                f"<b>{config.MARKETS.get(market, market)} 종목이 이 구역에 "
                "없습니다.</b> 맨 위에서 다른 시장을 고르십시오."),
            unsafe_allow_html=True,
        )
        return

    cols_per_row = max(1, section.columns)

    for start in range(0, len(instruments), cols_per_row):
        chunk = instruments[start : start + cols_per_row]
        columns = st.columns(cols_per_row, gap="small")
        for col, inst in zip(columns, chunk):
            quote = pick_quote(inst, data)

            premium = None
            if inst.local_peer and inst.common_shares_per_unit is not None and quote is not None:
                local = data.get("naver", {}).get(inst.local_peer)
                premium = compute_premium(inst, quote, local, fx)

            with col:
                st.markdown(ui.render_card(inst, quote, fx, premium), unsafe_allow_html=True)

    if section.footnote:
        st.markdown(ui.render_footnote(section.footnote), unsafe_allow_html=True)


def _valuation_label(screen, result, price, *, held: bool) -> str:
    """접힌 카드 제목. 펼치지 않고도 비교되도록 숫자를 다 적습니다.

    st.expander 의 제목은 **평문만** 들어갑니다(HTML 이 안 먹습니다).
    그래서 기호로 구분합니다.
    """
    parts = [f"{screen.ticker}"]
    if held:
        parts.append("보유")
    parts.append(f"질 {screen.passed_count}/{len(buffett.CRITERIA)}")
    if price is not None and price.ok:
        parts.append(f"가격 {price.passed_count}/{len(price.checks)}")
    else:
        parts.append("가격 판정 불가")
    if result is not None and getattr(result, "ok", False) \
            and result.implied_growth is not None:
        parts.append(f"요구 성장률 연 {result.implied_growth * 100:.1f}%")
    name = (screen.name or "").strip()
    head = f"{parts[0]} {name}" if name else parts[0]
    return f"{head}  ·  " + "  ·  ".join(parts[1:])


def render_valuation_tab(data: dict[str, dict[str, Quote]], fx,
                         use_demo: bool, phone: bool = False,
                         *, market: str = "all") -> None:
    """4. 걸러낸 종목 밸류에이션 — 역DCF 가 중심, 지표표는 보조.

    '걸러낸 종목' 은 두 갈래입니다: **내가 가진 것**(판단이 이미 필요함)과
    **발굴에서 품질 기준을 넘은 것**(판단이 곧 필요함). 둘을 같은 화면에 놓아야
    "가진 것 대신 이걸 볼 이유가 있나" 를 비교할 수 있습니다.
    """
    # 종목 수는 아래에서 _attach_dcf 를 돌려야 나옵니다. 헤더는 맨 위에
    # 있어야 하므로 자리만 잡아두고 개수가 나온 뒤에 채웁니다.
    head_slot = st.empty()
    st.markdown(
        ui.render_footnote(
            "<b>적정주가를 계산하지 않습니다.</b> 할인율·성장률 가정을 조금만 "
            "바꿔도 원하는 숫자가 나와서 판단 재료가 못 됩니다. 대신 방향을 "
            "뒤집어 <b>현재 가격이 요구하는 성장률</b>을 역산하고, 그걸 "
            "<b>과거 실제 성장률</b>과 비교합니다. FCF 와 순부채는 공시에서 "
            "자동으로 나오고, 외부에서 오는 건 시가총액 하나뿐입니다."
        ),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        scope = st.radio("대상", ["보유 + 발굴 통과", "전체"], horizontal=True,
                         key="val_scope")
    with col2:
        show_source = st.toggle("기준 출처·한계 표시", value=False,
                                key="val_src")

    # 시장은 왼쪽 내비에서 고릅니다. 역DCF 는 통화가 섞이면 비교가 안 되고
    # (달러 FCF 와 원화 FCF 를 같은 표에 둘 수 없습니다) 재무 출처도
    # SEC/DART 로 갈리므로, '전체' 는 미국으로 봅니다.
    kr_only = market == "kr"
    if kr_only:
        screens_map, errors = load_kr_screens(use_demo, dart.key_fingerprint())
        currency = "KRW"
        held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
                if i.source == "naver"}
    else:
        screens_map, errors = load_screens(use_demo)
        currency = "USD"
        held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
                if i.source == "yahoo"}

    screens = buffett.rank(list(screens_map.values()))
    if scope == "보유 + 발굴 통과":
        threshold = max(1, round(len(buffett.CRITERIA) * 2 / 3))
        screens = [s for s in screens
                   if s.ticker in held or s.passed_count >= threshold]

    triples = _attach_dcf(screens, use_demo, currency=currency)
    head_slot.markdown(
        ui.render_section_head(
            "밸류에이션 판단", "현재 가격이 요구하는 성장률 vs 과거 실제",
            len(triples)),
        unsafe_allow_html=True,
    )
    # **정렬 전에** 부릅니다 — load_market_caps 캐시 키가 티커 순서라
    # 정렬 후에 부르면 캐시를 놓치고 야후를 다시 칩니다.
    prices = _price_screens(triples, use_demo)
    if not triples:
        st.markdown(ui.render_empty_reason(
            n_total=len(screens_map), errors=errors,
            scope_hint=(scope != "전체" and not errors),
            source="DART" if kr_only else "SEC"), unsafe_allow_html=True)
        return

    # 보유 종목을 먼저 — 판단이 이미 필요한 것들입니다
    triples.sort(key=lambda t: (t[0].ticker not in held, -t[0].passed_count))

    verdicts = [t[2] for t in triples]
    st.markdown(
        ui.render_section_head(
            "사분면 지도", "사업의 질(가로) × 가격의 기대(세로)", len(verdicts)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_quadrant_map(verdicts), unsafe_allow_html=True)

    # 종목마다 접습니다. 펼친 상태로 5종목이면 페이지가 8,000px 가 넘어
    # 가격 조건이 어디 있는지 찾지 못합니다. 접힌 제목에 **질·가격 점수와
    # 판정을 그대로 적어서**, 펼치지 않고도 줄 세워 비교할 수 있게 합니다.
    for idx, (screen, result, verdict_obj) in enumerate(triples):
        price = prices.get(screen.ticker)
        label = _valuation_label(screen, result, price,
                                 held=screen.ticker in held)
        # 첫 종목만 펼쳐 둡니다 — 전부 접혀 있으면 빈 화면처럼 보이고,
        # 전부 펼치면 접는 의미가 없습니다.
        with st.expander(label, expanded=(idx == 0)):
            st.markdown(
                ui.render_screen(screen, show_source=show_source),
                unsafe_allow_html=True,
            )
            st.markdown(ui.render_dcf_cells(result), unsafe_allow_html=True)
            st.markdown(
                ui.render_price_block(price, show_source=show_source,
                                      metrics_meta=vl.METRICS),
                unsafe_allow_html=True,
            )
            st.markdown(
                ui.render_verdict(verdict_obj,
                                  prompt=vd.prompt_for(verdict_obj, screen)),
                unsafe_allow_html=True,
            )

    if phone:
        st.caption(
            "야후 집계 지표(PER · PBR 등)는 9컬럼 표라서 휴대폰 모드에서는 "
            "생략합니다. 화면 위쪽 표시 패널에서 끄시면 나옵니다."
        )
    else:
        with st.expander(
            "야후 파이낸스 집계 지표 (PER · PBR 등) — 표가 넓어 가로 스크롤이 "
            "필요합니다", expanded=False,
        ):
            render_valuation(use_demo)


def render_valuation(use_demo: bool) -> None:
    st.markdown(
        ui.render_section_head(
            "밸류에이션 지표",
            "관심종목 기준 · 야후 파이낸스 집계값",
            len(config.VALUATION_TICKERS),
        ),
        unsafe_allow_html=True,
    )

    rows = load_fundamentals(use_demo)
    st.markdown(
        ui.render_valuation_table(config.VALUATION_TICKERS, config.VALUATION_FIELDS, rows),
        unsafe_allow_html=True,
    )

    errors = [f"{sym}: {row['_error']}" for sym, row in rows.items() if row.get("_error")]
    if errors:
        st.markdown(ui.render_footnote("조회 실패 — " + " / ".join(errors[:4])),
                    unsafe_allow_html=True)

    st.markdown(
        ui.render_footnote(
            "이 표의 수치는 야후 파이낸스 집계값이며 공시 원문(10-K/10-Q, 사업보고서)이 아닙니다. "
            "Forward PER 은 애널리스트 컨센서스 기반 추정치입니다. "
            "ETF(QQQ·SCHD·DRAM)는 개별 기업 지표가 비어 있는 항목이 많습니다. "
            "한국 종목은 야후의 한국물 집계가 부정확한 경우가 있으므로 DART 원문과 대조하십시오. "
            "공시 원문 기반 분석은 '공시 분석' 탭을 보십시오."
        ),
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 공시 분석 탭
# ──────────────────────────────────────────────────────────────────────────────

#: 받는 중 안내에 쓸 이름 (함수 이름 → 화면 표기)
SOFT_LABELS = {
    "load_filings": "미국 공시", "load_dart_disclosures": "국내 공시",
    "load_inventory_trends": "국내 재고 추세",
    "load_us_inventory_trends": "미국 재고 추세",
    "load_close_headlines": "마감 기사", "load_research": "시황 리포트",
    "load_daily_brief": "전일 브리핑", "load_release_dates": "발표 일정",
}


def _soft(loader, *args, default):
    """**기다리지 않는** 받기. 저장된 값이 있으면 그것, 없으면 default.

    없을 때는 뒤에서 받기 시작하고, swr 이 '받는 중' 으로 적어 둡니다 —
    화면 위 안내와 자동 다시 그리기가 그 기록을 씁니다. 요약처럼 '먼저
    보여야 하는 화면' 의 곁가지에만 씁니다: 느린 재무 하나가 첫 화면
    전체를 붙잡지 않게 하려는 것입니다.
    """
    peek = getattr(loader, "peek", None)
    if peek is None:                      # 테스트용 가짜 등 — 그냥 부릅니다
        return loader(*args)
    got = peek(*args)
    return default if got is None else got


def _detect_signals(data: dict[str, dict[str, Quote]], use_demo: bool,
                    *, market: str = "all", soft: bool = False):
    """변화 감지 한 번. 요약 탭과 변화 감지 탭이 **같은 경로**를 씁니다.

    두 화면이 다른 결과를 보여주면 신뢰를 잃으므로 함수 하나로 모았습니다.
    반환: (신호 목록, 종목 목록, 추세, 공시, 오류 모음)
    오류 모음은 {"edgar": {...}, "dart": {...}, "trend": {...}} 입니다 —
    화면에 "무엇을 못 받았는지" 를 적어야 하므로 버리지 않고 넘깁니다.
    """
    instruments = config.filter_instruments(
        config.SECTION_WATCHLIST.instruments, market)

    docs = analysis_store.load_all(
        ANALYSIS_PATH, [i.analysis_key for i in instruments if i.analysis_key]
    )

    # EDGAR(미국) + DART(한국) 공시를 하나로 — 두 Filing 이 같은 속성을
    # 제공하므로 signals 는 구분하지 않습니다.
    # soft=True (요약·내 종목): 공시와 재고 추세를 **기다리지 않습니다.**
    # 아직 없으면 빈 값으로 그리고, 받는 대로 화면이 한 번 다시 그려집니다.
    # 데모에서는 기다릴 게 없으니 그대로 부릅니다.
    dfp = dart.key_fingerprint()
    if soft and not use_demo:
        filings, filing_errors = _soft(load_filings, use_demo, default=({}, {}))
        dart_filings, dart_errors = _soft(load_dart_disclosures, use_demo, dfp,
                                          default=({}, {}))
        kr_trends, trend_errors = _soft(load_inventory_trends, use_demo, dfp,
                                        default=({}, {}))
        us_trends, us_trend_errors = _soft(load_us_inventory_trends, use_demo,
                                           default=({}, {}))
    else:
        filings, filing_errors = load_filings(use_demo)
        dart_filings, dart_errors = load_dart_disclosures(use_demo, dfp)
        kr_trends, trend_errors = load_inventory_trends(use_demo, dfp)
        us_trends, us_trend_errors = load_us_inventory_trends(use_demo)
    merged_filings = {**filings, **dart_filings}
    trends = {**kr_trends, **us_trends}
    errors = {
        "edgar": filing_errors,
        "dart": dart_errors,
        "trend": {**trend_errors, **us_trend_errors},
    }

    quotes: dict[str, Quote] = {}
    for inst in instruments:
        q = pick_quote(inst, data)
        if q is not None:
            quotes[inst.symbol] = q

    thresholds = sig_mod.Thresholds(
        move_pct=config.SIGNAL_MOVE_PCT,
        drawdown_pct=config.SIGNAL_DRAWDOWN_PCT,
        extreme_pct=config.SIGNAL_EXTREME_PCT,
        earnings_days=config.SIGNAL_EARNINGS_DAYS,
        stale_days=config.SIGNAL_STALE_DAYS,
    )
    found = sig_mod.detect(instruments, quotes, docs, merged_filings,
                           thresholds=thresholds, trends=trends)
    return found, instruments, trends, merged_filings, errors


def render_signals_tab(data: dict[str, dict[str, Quote]], use_demo: bool,
                       *, market: str = "all") -> None:
    """변화 감지 — 뭘 봐야 하는지 알려주는 화면."""
    instruments = config.filter_instruments(
        config.SECTION_WATCHLIST.instruments, market)

    st.markdown(
        ui.render_section_head(
            "변화 감지",
            "새 공시 · 실적 임박 · 분석 노후화 · 비정상 등락 · 52주 위치",
            len(instruments),
        ),
        unsafe_allow_html=True,
    )

    # 요약 탭과 **같은 경로**를 씁니다 (_detect_signals). 두 화면이 다른 결과를
    # 보여주면 신뢰를 잃습니다.
    found, _inst, _trends, _filings, errs = _detect_signals(
        data, use_demo, market=market, soft=True)
    filing_errors = errs["edgar"]
    dart_errors, trend_errors = errs["dart"], errs["trend"]

    # 뉴스는 공시·급등락 신호가 잡힌 종목에만
    targets = tuple(sig_mod.news_targets(found, limit=config.NEWS_MAX_TICKERS))
    headlines = load_news(targets, use_demo)

    counts = sig_mod.summarize(found)
    st.markdown(ui.render_signal_summary(counts, len(found)), unsafe_allow_html=True)

    if filing_errors:
        with st.expander(f"EDGAR 조회 실패 {len(filing_errors)}건"):
            for ticker, err in filing_errors.items():
                st.markdown(f"**{ticker}** — {err}")
            st.caption(
                "SEC 는 API 키 대신 연락처가 담긴 User-Agent 를 요구합니다. "
                "config.py 의 EDGAR_USER_AGENT 에 본인 이메일을 넣으십시오."
            )

    all_dart_errors = {**dart_errors, **trend_errors}
    if all_dart_errors:
        key_ok, key_msg = dart.key_status()
        with st.expander(
            ("DART 인증키 미설정 — 한국 종목 공시·재고 지표 비활성"
             if not key_ok else f"DART 조회 실패 {len(all_dart_errors)}건")
        ):
            if not key_ok:
                st.markdown(
                    "**한국 종목(삼성전자·SK하이닉스) 공시 감지와 재고 지표에는 "
                    "DART 인증키가 필요합니다.** 무료입니다.\n\n"
                    "1. https://opendart.fss.or.kr 회원가입 (이메일 인증)\n"
                    "2. '인증키 신청/관리' → 신청\n"
                    "3. '오픈API 이용현황' 에서 40자리 키 확인\n"
                    "4. 환경변수로 설정한 뒤 앱 재시작\n"
                )
                st.code('export DART_API_KEY="40자리키"      # macOS/Linux\n'
                        'setx DART_API_KEY "40자리키"        # Windows',
                        language="bash")
                st.caption(
                    "키는 환경변수로만 받습니다 — config.py 에 적으면 압축 파일이나 "
                    "저장소에 섞여 나갑니다."
                )
            else:
                for code, err in all_dart_errors.items():
                    st.markdown(f"**{code}** — {err}")

    # ── 신호 목록 ────────────────────────────────────────────────────────────
    # 지금·이번 주는 펼쳐서, 참고는 접어서 — 화면이 할 일 목록으로 범람하지 않게
    urgent, fyi = sig_mod.split_by_urgency(found)
    cli = runner.cli_info()

    def draw(sig, slot) -> None:
        slot.markdown(
            ui.render_signal_card(sig, headlines.get(sig.inst.symbol)),
            unsafe_allow_html=True,
        )
        if not sig.prompt:
            return
        with slot.expander("Claude 에 물어볼 질문"):
            st.code(sig.prompt, language="text")
            st.caption("박스 우측 상단 복사 버튼으로 복사해 Claude 대화창에 붙여넣으십시오.")
            if (cli.available and not sig.aggregate
                    and sig.kind in ("new_filing", "stale", "never", "partial")
                    and sig.inst.analysis_key):
                st.caption(f"또는 '공시 분석' 탭에서 {sig.inst.name} 를 바로 실행할 수 있습니다.")

    for sig in urgent:
        draw(sig, st)

    if fyi:
        if urgent:
            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        with st.expander(f"참고 {len(fyi)}건", expanded=not urgent):
            for sig in fyi:
                draw(sig, st)

    if not found:
        st.caption(
            "임계값은 config.py 에서 조절합니다 — "
            f"등락 ±{config.SIGNAL_MOVE_PCT:.0f}%, "
            f"낙폭 {config.SIGNAL_DRAWDOWN_PCT:.0f}%, "
            f"실적 D-{config.SIGNAL_EARNINGS_DAYS}, "
            f"노후화 {config.SIGNAL_STALE_DAYS}일."
        )

    # 한국 종목 안내는 DART 키가 실제로 있는지에 따라 달라집니다. 전에는
    # 키를 넣은 뒤에도 '키 발급이 필요합니다' 라고 계속 적혀 있었습니다.
    _kr_note = (
        "한국 종목(삼성전자·SK하이닉스)은 EDGAR 에 없어 <b>DART 오픈API</b> 로 "
        "따로 받아옵니다. "
        if dart.api_key() else
        "한국 종목(삼성전자·SK하이닉스)은 EDGAR 에 없어 공시 감지가 되지 "
        "않습니다 — <b>DART_API_KEY</b> 를 Secrets 에 넣으면 받아옵니다. "
    )
    st.markdown(
        ui.render_footnote(
            "공시는 SEC EDGAR 공개 API(키 불필요)에서 실시간으로 받아옵니다. "
            + _kr_note
            + "헤드라인은 제목과 링크만 가져오며, 공시나 급등락이 감지된 "
            "종목에만 붙습니다."
        ),
        unsafe_allow_html=True,
    )


def render_cycle_tab(use_demo: bool, *, market: str = "all") -> None:
    """재고 지표 — 반도체 사이클 레이어 2. 메모리 3사를 한 화면에서 비교."""
    # 이 화면만은 **시장 선택을 따르지 않습니다.** 메모리 재고 사이클은
    # 삼성전자·SK하이닉스·마이크론 셋을 나란히 놓아야 읽히는 지표입니다.
    # 한쪽을 숨기면 "하이닉스 재고가 늘었다" 가 업황인지 회사 사정인지
    # 구분이 안 됩니다. 분리가 목적이 아니라 비교가 목적인 화면입니다.
    kr_instruments = config.cycle_instruments()
    us_tickers = list(config.CYCLE_US_TICKERS)

    st.markdown(
        ui.render_section_head(
            "재고 지표 (레이어 2)",
            "DART 분기보고서 + EDGAR XBRL 에서 DIO · 재고-매출 갭을 직접 계산",
            len(kr_instruments) + len(us_tickers),
        ),
        unsafe_allow_html=True,
    )
    if True:  # 메모리 사이클은 어느 시장에서 열어도 같은 화면입니다
        st.markdown(
            ui.render_footnote(
                "<b>이 화면은 시장과 무관하게 한·미를 함께 보여줍니다.</b> "
                "삼성전자·SK하이닉스·마이크론의 재고를 나란히 놓아야 "
                "업황인지 회사 사정인지 구분이 됩니다."),
            unsafe_allow_html=True,
        )

    kr_trends, kr_errors = load_inventory_trends(
        use_demo, dart.key_fingerprint())
    us_trends, us_errors = load_us_inventory_trends(use_demo)

    # 잠정실적 레이더 — 재고 지표는 정식 분기보고서가 있어야 계산되는데,
    # 영업(잠정)실적은 그보다 2주쯤 먼저 나옵니다. 그 사이 기간에 메모리
    # 사이클에 대한 가장 이른 확정 숫자라 재고 지표 **위에** 둡니다.
    # 이미 받아둔 공시 목록을 쓰므로 추가 네트워크 호출이 없습니다.
    _disc, _disc_err = load_dart_disclosures(use_demo, dart.key_fingerprint())
    _prelim = []
    for _rows in _disc.values():
        _prelim.extend(cycle.preliminary_radar(_rows))

    # 미국 쪽 — MU 는 8-K Item 2.02(Results of Operations)로 실적을 먼저
    # 냅니다. 한국의 영업(잠정)실적과 같은 성격이라 **같은 목록에** 둡니다 —
    # 메모리 3사를 한 화면에서 비교하는 게 이 탭의 목적입니다.
    _edgar, _edgar_err = load_filings(use_demo)
    _us_names = {"MU": "Micron"}
    for _tkr in config.CYCLE_US_TICKERS:
        _prelim.extend(cycle.prelim_from_filings(
            _edgar.get(_tkr, []), _tkr, name=_us_names.get(_tkr, _tkr)))

    _prelim.sort(key=lambda f: f.rcept_dt, reverse=True)
    _radar_err = {**_disc_err, **{k: v for k, v in _edgar_err.items()
                                  if k in config.CYCLE_US_TICKERS}}
    st.markdown(
        ui.render_section_head(
            "잠정실적 레이더",
            "영업(잠정)실적 + 8-K Item 2.02 — 정식 보고서보다 먼저 나오는 숫자",
            len(_prelim)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_prelim_radar(_prelim[:8], errors=_radar_err),
                unsafe_allow_html=True)

    # 한국 반도체 수출 — 공시보다도 빠릅니다. 월초에 전월치가 나오므로
    # 분기 실적을 기다리지 않고 수요를 읽는 유일한 월간 지표입니다.
    # 미국만 볼 때도 의미가 있지만(마이크론 수요의 선행 지표), 출처가
    # 산업통상자원부라 '한국' 쪽에 둡니다.
    if True:  # 사이클 탭은 공통 — 한국 수출도 같이 봅니다
        _exp, _exp_err = load_kr_exports(use_demo)
        st.markdown(ui.render_kr_exports(_exp, error=_exp_err),
                    unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "<b>공시 안의 숫자를 읽어오지 않습니다.</b> 공정공시 본문 표는 "
            "회사·분기마다 형식이 달라서, 파싱해 조용히 틀린 숫자를 보여주는 "
            "것보다 링크로 열어보는 쪽이 안전합니다. 미국(8-K)은 SEC 가 "
            "항목 번호를 주므로 제목을 대조하지 않고 <b>Item 2.02</b> 로 "
            "정확히 걸러냅니다. 재고 지표(아래)는 정식 분기보고서·10-Q 가 "
            "올라온 뒤에야 갱신됩니다."),
        unsafe_allow_html=True,
    )

    key_ok, key_msg = dart.key_status()
    if not key_ok and not use_demo:
        st.info(
            f"**한국 2사는 DART 인증키가 필요합니다.** {key_msg}\n\n"
            "무료 발급: https://opendart.fss.or.kr → 인증키 신청/관리 → "
            "오픈API 이용현황에서 40자리 키 확인 → 환경변수 `DART_API_KEY` 설정 후 재시작.\n\n"
            "**마이크론(MU)은 키 없이 EDGAR XBRL 로 바로 나옵니다** — 아래에서 확인하십시오.",
            icon="🔑",
        )

    st.markdown(
        ui.render_footnote(
            "DIO 절대값은 의미가 없습니다 — <b>자사 역사적 밴드 내 위치</b>가 신호입니다. "
            "그래서 수집한 분기들의 최소·중간값·최대를 기준선으로 함께 표시합니다. "
            "한국 2사는 분기보고서가 분기말 후 45일에 공시되므로 기준 분기가 헤드라인 "
            "실적보다 한 분기 뒤처집니다. 마이크론은 10-Q 가 더 빨라 더 최신입니다 — "
            "<b>3사의 기준 분기가 다를 수 있으니 비교할 때 각 패널의 '기준' 표기를 "
            "확인하십시오.</b>"
        ),
        unsafe_allow_html=True,
    )

    # 미국(키 불필요) 먼저 — 키가 없어도 뭔가는 보여야 합니다
    for ticker in us_tickers:
        trend = us_trends.get(ticker)
        if trend is None:
            st.markdown(
                ui.render_analysis_missing(
                    f"{ticker} 재고 지표",
                    us_errors.get(ticker, "수집되지 않았습니다."),
                    ticker, "inventory",
                ),
                unsafe_allow_html=True,
            )
            continue
        st.markdown(ui.render_inventory_panel(trend, cycle.checklist(trend)),
                    unsafe_allow_html=True)

    for inst in kr_instruments:
        trend = kr_trends.get(inst.symbol)
        if trend is None:
            st.markdown(
                ui.render_analysis_missing(
                    f"{inst.name} 재고 지표",
                    kr_errors.get(inst.symbol,
                                  "DART 인증키가 필요합니다 (환경변수 DART_API_KEY)."),
                    inst.symbol, "inventory",
                ),
                unsafe_allow_html=True,
            )
            continue
        st.markdown(ui.render_inventory_panel(trend, cycle.checklist(trend)),
                    unsafe_allow_html=True)

    all_errors = {**us_errors, **kr_errors}
    if all_errors:
        with st.expander(f"수집 실패 {len(all_errors)}건"):
            for code, err in all_errors.items():
                st.markdown(f"**{code}** — {err}")

    st.markdown(
        ui.render_footnote(
            "<b>한국 2사(DART)</b> — 계정은 XBRL 표준계정ID(ifrs-full_Inventories 등)를 "
            "1순위로 맞추고, 표준ID 가 없을 때만 계정명으로 폴백합니다. 기업마다 계정명이 "
            "달라(매출액 / 수익(매출액) / 영업수익) 계정명만으로 필터링하면 절반이 빠집니다. "
            "연결(CFS) 기준이며 재무정보 API 는 2015년 이후만 제공합니다.<br>"
            "<b>마이크론(EDGAR XBRL)</b> — us-gaap 태그 후보를 순서대로 시도하고, 같은 기간이 "
            "여러 공시에 반복 실리므로 제출일이 가장 늦은 보고만 남깁니다. 구간의 실제 "
            "일수를 쓰기 때문에 53주 회계연도(14주 분기)도 정확히 반영됩니다.<br>"
            "<b>재고 구성(원재료·재공품·완제품)은 이 경로로 받을 수 없습니다.</b> "
            "2026년 11월 삼성전자·SK하이닉스 실제 응답을 확인한 결과, 재고 관련 "
            "계정은 <code>ifrs-full_Inventories</code> 한 줄뿐이었습니다. 구성은 "
            "사업보고서 <b>주석</b>에 있고 DART 의 전체 재무제표 API 는 본표만 "
            "줍니다. 고장이 아니라 데이터가 없는 것이고, 추정하지 않습니다. "
            "DIO 는 정상 산출됩니다."
        ),
        unsafe_allow_html=True,
    )


_STATUS_STYLE = {
    "running":   ("🔄", "실행 중"),
    "done":      ("✅", "완료"),
    "failed":    ("❌", "실패"),
    "timeout":   ("⏱️", "시간 초과"),
    "cancelled": ("⛔", "중단됨"),
    "idle":      ("", ""),
}


def _render_job_panel(inst, kind: str, label: str, job: runner.Job, cli: runner.CliInfo) -> None:
    """한 종류 분석의 실행 버튼 + 상태를 그립니다."""
    icon, status_text = _STATUS_STYLE.get(job.status, ("", job.status))

    cols = st.columns([1.4, 1, 1, 2.6])

    with cols[0]:
        if job.is_running:
            st.button("중단", key=f"cancel_{inst.analysis_key}_{kind}",
                      use_container_width=True,
                      on_click=runner.cancel_job,
                      args=(ANALYSIS_PATH, inst.analysis_key, kind))
        else:
            disabled = not cli.available
            btn_label = "다시 실행" if job.status == "done" else "분석 실행"
            if st.button(btn_label, key=f"run_{inst.analysis_key}_{kind}",
                         type="primary" if not disabled else "secondary",
                         disabled=disabled, use_container_width=True):
                runner.start_job(
                    ANALYSIS_PATH, BASE_DIR,
                    inst.analysis_key, inst.name, kind,
                    max_turns=st.session_state.get("max_turns", runner.DEFAULT_MAX_TURNS),
                    permission_mode=st.session_state.get(
                        "permission_mode", runner.DEFAULT_PERMISSION_MODE),
                    skill_commands=st.session_state.get("skill_commands"),
                )
                st.rerun()

    with cols[1]:
        if status_text:
            st.markdown(f"<div style='padding-top:7px'>{icon} {status_text}</div>",
                        unsafe_allow_html=True)

    with cols[2]:
        elapsed = job.elapsed_sec
        if elapsed is not None and job.status != "idle":
            mins, secs = divmod(elapsed, 60)
            st.markdown(f"<div style='padding-top:7px;color:#898781'>{mins}분 {secs}초</div>",
                        unsafe_allow_html=True)

    with cols[3]:
        bits = []
        if job.cost_usd is not None:
            bits.append(f"비용 ${job.cost_usd:.2f}")
        if job.num_turns is not None:
            bits.append(f"{job.num_turns}턴")
        if bits:
            st.markdown(
                f"<div style='padding-top:7px;color:#898781'>{' · '.join(bits)}</div>",
                unsafe_allow_html=True)

    if job.is_running:
        st.caption("Claude Code 가 백그라운드에서 돌고 있습니다. "
                   "이 창을 닫아도 작업은 계속되고, 다시 열면 상태가 보입니다.")
        log = runner.read_log(ANALYSIS_PATH, inst.analysis_key, kind, tail_bytes=1500)
        if log:
            with st.expander("실행 로그 (마지막 부분)"):
                st.code(log, language="text")

    if job.status in ("failed", "timeout", "cancelled") and job.error:
        st.error(job.error, icon="⚠️")
        log = runner.read_log(ANALYSIS_PATH, inst.analysis_key, kind, tail_bytes=3000)
        if log:
            with st.expander("실행 로그 (마지막 부분)"):
                st.code(log, language="text")


def render_analysis_tab(*, embed: bool = False,
                        phone: bool = False) -> None:
    """공시 분석.

    phone=True 면 본문을 **DOM 에 아예 넣지 않습니다.** 접기만 해도 스크롤은
    짧아지지만 수십 KB 가 전송되고, 휴대폰에서 읽을 분량이 아닙니다.

    embed=True 는 '내 종목' 탭에 들어갈 때입니다. 분석 본문(종목당 50KB 넘는
    HTML 3개)을 그대로 펼치면 보유 종목 화면이 스크롤 수십 번 길이가 됩니다.
    그래서 **목록과 실행 버튼만 펼치고 본문은 접습니다** — 읽을 때 열면 됩니다.
    """
    instruments = config.analysis_instruments()
    cli = runner.cli_info()

    st.markdown(
        ui.render_section_head(
            "공시 분석",
            "Claude Code 헤드리스 실행 + 결과 뷰어",
            len(instruments),
        ),
        unsafe_allow_html=True,
    )

    # ── 실행 환경 상태 ────────────────────────────────────────────────────────
    if not cli.available:
        st.warning(
            f"**분석 실행 불가** — {cli.summary}\n\n"
            "설치 후에도 버튼이 비활성이면, 터미널에서 `claude` 를 한 번 실행해 "
            "로그인을 마치고 이 앱을 재시작하십시오. "
            "이미 생성된 분석은 아래에서 그대로 볼 수 있습니다.",
            icon="🔌",
        )
    else:
        st.caption(f"🔌 {cli.summary} · {cli.path}")

    docs = analysis_store.load_all(ANALYSIS_PATH, [i.analysis_key for i in instruments])
    jobs = runner.poll_all(ANALYSIS_PATH, [i.analysis_key for i in instruments])
    n_running = runner.running_count(jobs)

    if n_running:
        st.info(f"{n_running}건이 실행 중입니다. 완료되면 자동으로 아래에 반영됩니다.",
                icon="🔄")

    st.markdown(ui.render_analysis_index(instruments, docs), unsafe_allow_html=True)

    ready = [i for i in instruments if not docs[i.analysis_key].is_empty]
    if not ready and cli.available:
        st.info("아직 생성된 분석이 없습니다. 종목을 고르고 '분석 실행'을 누르십시오.",
                icon="📄")

    labels = [f"{i.name} ({i.analysis_key})" for i in instruments]
    chosen_label = st.selectbox("종목 선택", labels, index=0)
    inst = instruments[labels.index(chosen_label)]
    doc = docs[inst.analysis_key]

    # ── 일괄 실행 ─────────────────────────────────────────────────────────────
    if cli.available:
        run_all, _spacer = st.columns([1.6, 5])
        with run_all:
            if st.button("3종 모두 실행", key=f"runall_{inst.analysis_key}",
                         use_container_width=True):
                for kind in analysis_store.KIND_KEYS:
                    runner.start_job(
                        ANALYSIS_PATH, BASE_DIR,
                        inst.analysis_key, inst.name, kind,
                        max_turns=st.session_state.get("max_turns", runner.DEFAULT_MAX_TURNS),
                        permission_mode=st.session_state.get(
                            "permission_mode", runner.DEFAULT_PERMISSION_MODE),
                        skill_commands=st.session_state.get("skill_commands"),
                    )
                st.rerun()

    st.markdown(ui.render_analysis_header(inst, doc), unsafe_allow_html=True)

    for warn in doc.warnings:
        st.warning(warn, icon="⚠️")

    if doc.is_stale:
        st.warning(
            f"이 분석은 {doc.age_days}일 전({doc.generated})에 생성됐습니다. "
            f"그 사이 실적 발표가 있었다면 다시 실행하십시오.",
            icon="🕒",
        )

    kind_tabs = st.tabs([analysis_store.kind_label(k) for k, _l, _d in analysis_store.KINDS])
    for tab, (kind, label, desc) in zip(kind_tabs, analysis_store.KINDS):
        with tab:
            st.caption(desc)
            _render_job_panel(inst, kind, label, jobs[(inst.analysis_key, kind)], cli)

            body = doc.html.get(kind)
            if body:
                size_kb = len(body) / 1024
                if phone:
                    # DOM 에 넣지 않습니다 — 전송량을 아끼는 게 목적입니다
                    st.caption(
                        f"{label} 전문 {size_kb:,.0f}KB — 휴대폰 모드에서는 "
                        "싣지 않습니다. 화면 위쪽 표시 패널에서 끄시거나 컴퓨터에서 "
                        "보십시오."
                    )
                elif embed:
                    # 내 종목 탭에서는 접어둡니다. 분량을 먼저 알려줘
                    # 열지 말지 판단할 수 있게 합니다.
                    with st.expander(f"{label} 전문 보기 ({size_kb:,.0f}KB)",
                                     expanded=False):
                        st.markdown(ui.render_analysis_body(body),
                                    unsafe_allow_html=True)
                else:
                    st.divider()
                    st.markdown(ui.render_analysis_body(body),
                                unsafe_allow_html=True)
            elif not jobs[(inst.analysis_key, kind)].is_running:
                cmd = analysis_store.skill_command(kind, inst.analysis_key, inst.name)
                st.markdown(
                    ui.render_analysis_missing(label, cmd, inst.analysis_key, kind),
                    unsafe_allow_html=True,
                )

    # 출처 목록은 본문을 읽을 때 쓰는 것이라, 내 종목 탭에서는 생략합니다
    if doc.sources and not embed:
        st.markdown(ui.render_analysis_sources(doc.sources), unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# 설정 패널 (페이지 상단)
# ──────────────────────────────────────────────────────────────────────────────

def _pane(label: str, help_text: str = ""):
    """설정 묶음 하나. st.popover 가 있으면 그걸, 없으면 expander 를 씁니다.

    popover 는 버튼을 누르면 떠오르는 작은 패널이라 페이지를 밀어내지
    않습니다. Streamlit 버전에 따라 없을 수 있어 대체 경로를 둡니다.
    """
    pop = getattr(st, "popover", None)
    if pop is not None:
        try:
            return pop(label, help=help_text, use_container_width=True)
        except TypeError:
            return pop(label)
    return st.expander(label)


def _is_phone() -> bool:
    """브라우저가 휴대폰인가 — 요청 머리글의 User-Agent 로 봅니다.

    스트림릿은 화면 폭을 서버에 알려주지 않습니다. 그래서 폭이 아니라
    기기 종류로 판단합니다: 접는 휴대폰은 펼쳐도 'Mobile' 이라 휴대폰으로
    잡힙니다 (그쪽이 가벼워서 손해가 없습니다). 못 읽으면 False.
    """
    try:
        ua = str(st.context.headers.get("User-Agent", ""))
    except Exception:  # noqa: BLE001 - st.context 는 1.37 이상
        return False
    return any(k in ua for k in ("Mobile", "Android", "iPhone"))


def controls() -> dict:
    """설정을 **페이지 안**에 둡니다.

    전에는 전부 사이드바에 있었는데, 왼쪽을 접었다 폈다 해야 해서 번거롭고
    휴대폰에서는 화면을 가립니다. 한 줄에 묶고, 자주 안 쓰는 것은 버튼을
    눌러 펼치는 패널에 넣습니다. 매일 쓰는 건 '지금 갱신' 하나뿐입니다.
    """
    # 테마 전환을 없앴습니다 (2026-11-11). 두 벌을 유지하면 한쪽에서만
    # 깨지는 버그가 계속 생기고 둘 다 어중간해집니다 — 실제로 각주 태그,
    # 링크 색, 차트 대비가 전부 한쪽에서만 틀렸습니다. 하나를 제대로
    # 만드는 쪽을 골랐습니다.
    c2, c3, c4 = st.columns([2, 2, 2])

    with c2:
        with _pane("표시 설정", "색상 · 휴대폰 · 설명 문구"):
            convention_label = st.radio(
                "등락 색상",
                ["상승 적색 (한국)", "상승 녹색 (미국)"],
                index=0 if config.COLOR_CONVENTION == "kr" else 1,
                help="한국·일본 증시는 상승을 적색으로, 미국 증시는 녹색으로 "
                     "표시합니다.",
            )
            convention = "kr" if convention_label.startswith("상승 적색") else "us"
            phone = st.toggle(
                "휴대폰 모드", value=_is_phone(),
                help="무거운 것을 아예 싣지 않습니다 — 공시 분석 본문(수십 KB)과 "
                     "넓은 지표표를 생략합니다. 요약·시세·매크로는 그대로입니다. "
                     "휴대폰 브라우저로 열면 처음부터 켜져 있습니다.",
            )
            stack = st.toggle(
                "좁은 화면에서 표를 카드로", value=True,
                help="휴대폰처럼 좁은 화면에서 표의 한 줄을 카드 한 장으로 "
                     "세웁니다 (옆으로 밀 필요 없음). 끄면 표를 그대로 두고 "
                     "옆으로 밀어서 봅니다. 넓은 화면에는 영향이 없습니다.",
            )
            # 기본은 끕니다. 화면마다 '왜 이렇게 계산하는가' 문단이 먼저
            # 나와서 숫자가 한참 아래로 밀렸습니다 (2026-11-11 "허접하고
            # 획일적"). 0 건·실패처럼 꼭 읽어야 하는 문장은 꺼도 남습니다.
            show_notes = st.toggle(
                "설명 문구 표시", value=False,
                help="각 지표를 '왜 그렇게 보는가' 하는 설명을 숨깁니다. "
                     "익숙해지면 끄십시오 — 숫자만 남아 훨씬 빨리 읽힙니다.",
            )

    with c3:
        with _pane("데이터", "갱신 · 환율 · 데모"):
            use_demo = st.toggle(
                "데모 모드 (오프라인)", value=False,
                help="네트워크 없이 레이아웃만 확인합니다. 표시되는 숫자는 "
                     "실제 시세가 아닙니다.",
            )
            # 기본은 꺼 둡니다. 켜 두면 주기마다 화면 전체를 다시 그려서
            # (스피너·깜빡임) 보는 중에 답답합니다. 시세를 지켜볼 때만 켭니다.
            auto = st.toggle("자동 갱신", value=config.AUTO_REFRESH_DEFAULT)
            interval = config.AUTO_REFRESH_SEC
            if auto:
                interval = st.slider("갱신 주기 (초)", 10, 300,
                                     config.AUTO_REFRESH_SEC, step=10)
            fx_manual = st.number_input(
                "환율 수동 지정 (USD/KRW)", min_value=0.0,
                value=float(config.FX_OVERRIDE or 0.0), step=1.0,
                help="0 이면 실시간 환율(KRW=X)을 사용합니다.",
            )

    with c4:
        with _pane("진단 · 실행", "데이터가 맞는지 확인 · 분석 실행 설정"):
            # 진단 패널 하나 때문에 앱 전체가 안 켜지면 안 됩니다.
            # 2026-11-11 에 tools/diagnose.py 가 낡았다는 이유로 여기서
            # AttributeError 가 났고, controls() 안이라 화면이 통째로
            # 비었습니다. 파일이 섞였을 때 **고칠 방법을 보여줄 화면**
            # 자체가 사라지는 게 제일 나쁩니다.
            try:
                render_diag_panel()
            except Exception as exc:  # noqa: BLE001
                st.error(
                    f"**진단 패널을 그리지 못했습니다** ({type(exc).__name__}). "
                    "`tools/` 안의 파일이 이 버전과 맞지 않을 수 있습니다. "
                    "화면 맨 위 경고에 적힌 파일을 다시 올리십시오. "
                    "나머지 화면은 그대로 씁니다.",
                    icon="⚠️",
                )
            st.divider()
            st.caption(
                "공시 분석 탭의 '분석 실행' 은 Claude Code 를 "
                "헤드리스(`claude -p`)로 띄워 실제 스킬을 돌립니다. "
                "실행마다 토큰 비용이 발생합니다."
            )
            st.session_state["max_turns"] = st.slider(
                "최대 턴 수", 10, 80, runner.DEFAULT_MAX_TURNS, step=5,
                help="에이전트 루프 상한. 낮추면 비용이 줄지만 분석이 중간에 "
                     "끊길 수 있습니다.",
            )
            st.session_state["permission_mode"] = st.selectbox(
                "권한 모드",
                ["dontAsk", "acceptEdits", "bypassPermissions"],
                index=0,
                help=(
                    "무인 실행이므로 승인 대기 없이 돌아야 합니다. "
                    "allowedTools 로 도구를 "
                    f"({runner.DEFAULT_ALLOWED_TOOLS}) 로 제한해 두었습니다. "
                    "bypassPermissions 는 가장 넓은 권한이므로 권장하지 "
                    "않습니다."
                ),
            )
            st.caption("**스킬 슬래시 명령** — 플러그인으로 설치했다면 접두어가 "
                       "붙습니다. 터미널에서 `claude` 실행 후 `/` 를 입력하면 "
                       "정확한 이름이 보입니다.")
            cmds: dict[str, str] = {}
            for kind, label, _desc in analysis_store.KINDS:
                cmds[kind] = st.text_input(
                    label, value=runner.SKILL_COMMANDS[kind],
                    key=f"skillcmd_{kind}",
                )
            st.session_state["skill_commands"] = cmds

    if st.button("지금 갱신", use_container_width=False):
        load_all.clear()
        load_fundamentals.clear()
        st.rerun()

    return {
        "convention": convention,
        "phone": phone,
        "stack": stack,
        "notes": show_notes,
        "demo": use_demo,
        "auto": auto,
        "interval": interval,
        "fx_override": fx_manual or None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 본문
# ──────────────────────────────────────────────────────────────────────────────

#: 섹션별 로딩 안내. 모든 load_* 가 show_spinner=False 라 아무것도
#: 안 띄우면 멈춘 것처럼 보입니다. 첫 로딩(캐시 없음) 기준 체감 시간을
#: 적습니다 — 과소 표기하면 "고장났나" 싶어 새로고침하게 됩니다.
SECTION_LOADING = {
    "summary": "요약 — 시세·공포탐욕·VIX·FRED 를 불러옵니다 (처음 10~30초)",
    "holdings": "내 종목 — 시세와 공시를 불러옵니다 (처음 10~30초)",
    "discover": "종목 발굴 — 95개 기업 재무제표를 받아옵니다 (처음 1~3분)",
    "macro": "매크로 — FRED 13종·VIX·공포탐욕 (처음 10~20초)",
    "chart": "차트 조건 — 후보 종목의 1년 일봉 (처음 10~30초)",
    "research": "산업 리포트 — 증권사 리포트 목록 (처음 5~10초)",
    "calendar": "주요 일정 — FRED 발표일 · 배당 이력 (처음 5~15초)",
    "supply": "수급 — 종목별 외국인·기관 순매매 (처음 5~15초)",
    "earnings": "실적 — 분기 실적과 추정치 (처음 5~15초)",
    "sector_heat": "섹터 온도 — 업종 ETF 14개 일봉 (처음 10~20초)",
    "kr_flows": "뉴스·공시·지표 — 섹터 뉴스·DART 공시·한국 지표 (처음 20~40초)",
    "us_flows": "물가·유동성 — FRED 물가 6 · 유동성 6 (처음 10~20초)",
    "valuation": "밸류에이션 — 스크리닝 결과로 역DCF 를 계산합니다 (처음 1~3분)",
    "cycle": "메모리 사이클 — 재고 추이를 받아옵니다 (처음 20~60초)",
}


# ──────────────────────────────────────────────────────────────────────────────
# 속도 — 동시에 받아 두기 · 측정
# ──────────────────────────────────────────────────────────────────────────────

def _ctx_initializer():
    """작업 스레드에 스트림릿 실행 문맥을 붙이는 함수. 못 구하면 None.

    문맥이 없어도 캐시 함수는 돌지만 로그에 경고가 찍힙니다. 스트림릿
    내부 경로라 버전에 따라 없을 수 있어 실패는 조용히 넘깁니다.
    """
    try:
        from streamlit.runtime.scriptrunner import (
            add_script_run_ctx, get_script_run_ctx)
        ctx = get_script_run_ctx()
    except Exception:  # noqa: BLE001
        return None
    if ctx is None:
        return None

    def init() -> None:
        try:
            add_script_run_ctx(threading.current_thread(), ctx)
        except Exception:  # noqa: BLE001
            pass
    return init


def _section_jobs(section: str, market: str, use_demo: bool) -> dict:
    """화면별로 **서로 기다릴 필요 없는** 데이터 받기. 이름 → 함수.

    지문(key_fingerprint)은 여기서, 즉 주 스레드에서 미리 계산합니다 —
    세션에 넣은 임시 키가 스레드에서 안 보일 수 있습니다.
    """
    dfp, ffp = dart.key_fingerprint(), fred.key_fingerprint()
    jobs: dict = {"시세": lambda: load_all(use_demo)}
    if section == "summary":
        jobs.update({
            "미국 공시": lambda: load_filings(use_demo),
            "국내 공시": lambda: load_dart_disclosures(use_demo, dfp),
            "국내 재고 추세": lambda: load_inventory_trends(use_demo, dfp),
            "미국 재고 추세": lambda: load_us_inventory_trends(use_demo),
            "매크로": lambda: load_macro(use_demo, ffp),
        })
        if market == "kr":
            jobs["섹터 온도"] = lambda: load_sector_heat(use_demo)
        else:
            jobs["공포탐욕"] = lambda: load_feargreed(use_demo)
            jobs["VIX"] = lambda: load_vix(use_demo)
        jobs.update({
            "전일 브리핑 (한국)": lambda: load_daily_brief("kr", use_demo),
            "전일 브리핑 (미국)": lambda: load_daily_brief("us", use_demo),
            "마감 기사": lambda: load_close_headlines(use_demo),
            "시황 리포트": lambda: load_research("market", use_demo),
            "발표 일정": lambda: load_release_dates(use_demo, ffp),
        })
    elif section == "kr_flows":
        jobs.update({
            "섹터 뉴스": lambda: load_sector_news(use_demo),
            "주요 공시": lambda: load_market_filings(use_demo, dfp),
            "국내 지표": lambda: load_kr_macro(use_demo, ffp),
        })
    elif section == "us_flows":
        jobs.update({
            "물가": lambda: load_inflation(use_demo, ffp),
            "유동성": lambda: load_liquidity(use_demo, ffp),
        })
    elif section == "cycle":
        jobs.update({
            "미국 공시": lambda: load_filings(use_demo),
            "국내 공시": lambda: load_dart_disclosures(use_demo, dfp),
            "국내 재고 추세": lambda: load_inventory_trends(use_demo, dfp),
            "미국 재고 추세": lambda: load_us_inventory_trends(use_demo),
            "수출": lambda: load_kr_exports(use_demo),
        })
    elif section == "macro":
        jobs.update({
            "매크로": lambda: load_macro(use_demo, ffp),
            "공포탐욕": lambda: load_feargreed(use_demo),
            "VIX": lambda: load_vix(use_demo),
        })
    elif section == "valuation":
        jobs.update({
            "미국 재무 심사": lambda: load_screens(use_demo),
            "국내 재무 심사": lambda: load_kr_screens(use_demo, dfp),
        })
    elif section == "sector_heat":
        jobs["섹터 온도"] = lambda: load_sector_heat(use_demo)
    elif section == "research":
        jobs["산업 리포트"] = lambda: load_research("industry", use_demo)
    elif section == "calendar":
        jobs["발표 일정"] = lambda: load_release_dates(use_demo, ffp)
        # 대상 목록은 함수 안에서 만듭니다 — 여기서는 '무엇을 받을지' 만 정하고
        # 실제 계산은 받는 순간에 (테스트도 이 함수를 따로 떼어 부릅니다).
        jobs["배당"] = lambda: load_dividends(
            tuple(t[0] for t in _dividend_targets(use_demo)), use_demo)
    elif section == "supply":
        jobs["수급"] = lambda: load_kr_flows(
            tuple(_kr_watch_codes(use_demo)), use_demo)
    elif section == "earnings" and market == "kr":
        jobs["분기 실적"] = lambda: load_kr_quarters(
            tuple(_kr_watch_codes(use_demo)), use_demo)
        jobs["주요 공시"] = lambda: load_market_filings(use_demo, dfp)
    elif section == "earnings":
        jobs["실적 (야후)"] = lambda: load_us_earnings(
            tuple(i.symbol for i in config.SECTION_WATCHLIST.instruments
                  if i.source == "yahoo"), use_demo)
    elif section == "holdings":
        jobs["일봉 (차트 조건)"] = lambda: load_chart_rows(market, use_demo)
    elif section == "chart":
        jobs["일봉 (차트 조건)"] = lambda: load_chart_rows(market, use_demo)
    elif section == "discover" and market == "kr":
        jobs.update({
            "국내 일봉": lambda: load_kr_vol_profiles(use_demo),
            "국내 지표": lambda: load_kr_value_rows(use_demo),
        })
    elif section == "discover":
        jobs["미국 재무 심사"] = lambda: load_screens(use_demo)
    return jobs


def _warm_market(market: str, use_demo: bool) -> bool:
    """이 시장의 **다른 섹션** 데이터를 뒤에서 미리 받아 둡니다.

    지금 화면을 다 그린 뒤에 부릅니다 — 화면을 기다리게 하지 않습니다.
    한 시장에 10분에 한 번만 돌고, 이미 저장된 값이 있으면 실제로 받지
    않습니다 (swr 이 저장 시간을 봅니다). 그래서 처음 한 번만 무겁고,
    그 뒤로 섹션 버튼을 누르면 저장된 값이 바로 나옵니다.

    데모 모드에서는 하지 않습니다 — 가짜 값을 미리 만들 이유가 없습니다.
    """
    if use_demo:
        return False
    jobs: dict = {}
    for sec in config.market_tab_keys(market):
        for name, fn in _section_jobs(sec, market, use_demo).items():
            jobs.setdefault(name, fn)
    # 다른 시장의 요약도 — 시장 버튼을 누르면 바로 나오게
    other = next((m for m in config.MARKETS if m != market), None)
    if other:
        for name, fn in _section_jobs("summary", other, use_demo).items():
            jobs.setdefault(f"{other}:{name}", fn)
    return swr.warm(f"market:{market}", jobs, every=600)


def _prefetch(section: str, market: str, use_demo: bool, log) -> None:
    """이 화면이 쓸 데이터를 **동시에** 받아 캐시에 넣어 둡니다.

    아래의 원래 코드는 바꾸지 않습니다 — 같은 함수를 다시 부르면 캐시에서
    바로 나옵니다. 여기서 실패한 것은 원래 경로에서 평소처럼 오류로
    보입니다. 그래서 이 함수가 통째로 실패해도 화면은 예전처럼(느리게)
    그려질 뿐입니다.
    """
    if use_demo:
        return
    try:
        # 요약·내 종목은 **3초만** 기다립니다. 그 안에 못 끝낸 것(재무·공시)은
        # 뒤에서 계속 받고, 화면은 있는 것으로 먼저 그립니다. 이 두 화면의
        # 곁가지는 기다리지 않는 받기(_soft)를 쓰므로 빈 채로 그려졌다가
        # 받는 대로 채워집니다. 다른 화면은 그 데이터가 본문이라 기다립니다.
        budget = PREFETCH_BUDGET if section in SOFT_SECTIONS else None
        perf.run_parallel(_section_jobs(section, market, use_demo), log,
                          initializer=_ctx_initializer(), budget=budget)
    except Exception:  # noqa: BLE001
        pass


#: 먼저 그리고 나중에 채우는 화면과, 그 화면이 처음에 기다려 주는 시간(초)
SOFT_SECTIONS = ("summary", "holdings")
PREFETCH_BUDGET = 3.0
#: 이보다 묵은 값을 보여줬으면 화면 위에 알리고, 새 값이 오면 다시 그립니다
STALE_NOTICE_SEC = 300.0
#: 자동 다시 그리기 연속 한도 — 받기가 계속 실패해도 돌고 돌지 않게
AUTO_RERUN_MAX = 3


def _age_text(seconds: float) -> str:
    if seconds < 3_600:
        return f"{max(1, round(seconds / 60))}분"
    if seconds < 86_400:
        return f"{seconds / 3_600:.0f}시간"
    return f"{seconds / 86_400:.0f}일"


def _stale_notice(oldest: float, pending: list[str]) -> str:
    """화면 위 안내 한 줄 (없으면 빈 문자열)."""
    parts = []
    if oldest >= STALE_NOTICE_SEC:
        parts.append(f"<b>저장해 둔 값을 먼저 보여드립니다</b> (가장 오래된 것 "
                     f"{_age_text(oldest)} 전)")
    if pending:
        names = list(dict.fromkeys(SOFT_LABELS.get(n, n) for n in pending))
        parts.append("<b>받는 중:</b> " + " · ".join(names))
    if not parts:
        return ""
    return " — ".join(parts) + ". 새 값이 오면 화면이 한 번 자동으로 바뀝니다."


def _refresh_watch(waiting: bool, auto_on: bool) -> None:
    """묵은 값·빈 값으로 먼저 그렸으면, 새 값이 왔을 때 **한 번** 다시 그립니다.

    2초마다 '뒤에서 받던 것이 끝났나' 만 보는 작은 조각입니다. 끝났으면 화면
    전체를 다시 돌립니다. 받기가 계속 실패하면 끝없이 돌 수 있어 연속
    AUTO_RERUN_MAX 번까지만 합니다 (기다릴 게 없는 화면이 한 번 그려지면
    횟수는 0 으로 돌아갑니다). 자동 갱신을 켠 상태에서는 그쪽이 주기적으로
    다시 그리므로 따로 하지 않습니다.
    """
    if not waiting:
        st.session_state["_auto_reruns"] = 0
        return
    if auto_on or not hasattr(st, "fragment"):
        return
    count = int(st.session_state.get("_auto_reruns", 0))
    if count >= AUTO_RERUN_MAX:
        return
    armed = time.time()

    @st.fragment(run_every=2)
    def _watch() -> None:
        # 그리는 중에 한 번 바로 실행됩니다 — 그때는 넘어갑니다
        if time.time() - armed < 1.5 or swr.busy() > 0:
            return
        st.session_state["_auto_reruns"] = count + 1
        st.rerun()

    try:
        _watch()
    except Exception:  # noqa: BLE001 - 자동 다시 그리기는 있으면 좋은 것
        pass


def _peek_section(market: str) -> str:
    """지금 그릴 섹션 — 내비보다 먼저 데이터를 받으려고 미리 읽습니다."""
    ordered = config.market_tab_keys(market)
    cand = st.session_state.get(f"nav_{market}")
    if cand not in ordered:
        try:
            cand = st.query_params.get("s", "")
        except Exception:  # noqa: BLE001
            cand = ""
    return cand if cand in ordered else ordered[0]


def _nav_button(label: str, key: str, active: bool, on_click, args) -> None:
    kw = dict(key=key, type="primary" if active else "secondary",
              on_click=on_click, args=args)
    try:
        st.button(label, width="stretch", **kw)
    except TypeError:   # width 가 없는 예전 스트림릿
        st.button(label, use_container_width=True, **kw)


def _section_nav(market: str, labels: dict) -> str:
    """왼쪽 섹션 목록 — **진짜 버튼**으로 그립니다. 고른 섹션 키를 돌려줍니다.

    2026-11-11: 라디오를 CSS 로 목록처럼 꾸몄는데 실제 앱에서는 버튼
    모양이 안 보였습니다. 동그라미를 숨기고 나니 선택 안 된 항목은 그냥
    글자였고, 선택 표시는 스트림릿 내부 구조(:has(input:checked))에
    기대고 있어 보장이 없었습니다. 스트림릿 버튼은 테마가 직접 그리므로
    테두리가 항상 보이고, 지금 섹션은 남색으로 채워집니다.
    """
    key = f"nav_{market}"
    groups = config.tab_groups(market)
    ordered = [k for _g, items in groups for k, _l in items]
    cur = _peek_section(market)
    st.session_state[key] = cur

    def pick(k: str) -> None:
        st.session_state[key] = k

    st.markdown('<div class="dash-navmark"></div>', unsafe_allow_html=True)
    for gname, items in groups:
        if not items:
            continue
        st.markdown(f'<div class="dash-navhead">{gname}</div>',
                    unsafe_allow_html=True)
        for k, _lbl in items:
            _nav_button(labels.get(k, k), f"navbtn_{market}_{k}",
                        k == cur, pick, (k,))
    try:
        if st.query_params.get("s") != cur:
            st.query_params["s"] = cur
    except Exception:  # noqa: BLE001
        pass
    return cur if cur in ordered else ordered[0]


def _peek_market() -> str:
    """제목줄에 적을 시장. 전환 위젯보다 **먼저** 그려지므로 세션·주소에서
    미리 읽습니다. 위젯을 누르면 스트림릿이 새 값을 세션에 넣고 처음부터
    다시 돌리므로 여기서 읽는 값이 곧 화면의 값입니다."""
    keys = list(config.MARKETS)
    for cand in (st.session_state.get("market"),
                 st.session_state.get("_market_last")):
        if cand in keys:
            return cand
    try:
        m = st.query_params.get("m", "")
    except Exception:  # noqa: BLE001
        m = ""
    return m if m in keys else config.DEFAULT_MARKET


def _market_switch() -> str:
    """한국 / 미국 — 화면 맨 위의 큰 전환. 고른 값을 돌려줍니다.

    **주소창에 남깁니다** (?m=kr). 새로고침해도, 휴대폰 홈 화면에 즐겨찾기를
    걸어도 마지막에 본 시장으로 열립니다. 세션 상태만 쓰면 새로고침할
    때마다 기본값으로 돌아갑니다.
    """
    keys = list(config.MARKETS)
    if "market" not in st.session_state:
        try:
            from_url = st.query_params.get("m", "")
        except Exception:  # noqa: BLE001 - 구버전 스트림릿
            from_url = ""
        st.session_state["market"] = (from_url if from_url in keys
                                      else config.DEFAULT_MARKET)

    st.markdown('<div class="dash-marketmark"></div>', unsafe_allow_html=True)
    last = st.session_state.get("_market_last")
    if last not in keys:
        last = st.session_state.get("market")
    if last not in keys:
        last = config.DEFAULT_MARKET

    # **'위젯이 없다' 와 '위젯이 None 을 돌려줬다' 를 구분합니다.**
    # segmented_control 은 이미 고른 칸을 다시 누르면 선택이 풀려 None 을
    # 돌려줍니다. 전에는 그걸 '위젯이 없다' 로 읽고 라디오로 내려갔다가,
    # 세션의 None 으로 index 를 찾다 ValueError 로 앱이 죽었습니다.
    # 휴대폰에서 '한국 시장' 을 두 번 누르면 그렇게 됩니다.
    picker = getattr(st, "segmented_control", None)
    used_picker = False
    choice = None
    if picker is not None:
        try:
            choice = picker(
                "시장", keys, key="market",
                format_func=lambda k: f"{config.MARKETS[k]} 시장",
                label_visibility="collapsed",
            )
            used_picker = True
        except Exception:  # noqa: BLE001 - 위젯 인자는 버전마다 다릅니다
            used_picker = False
    if not used_picker:
        choice = st.radio("시장", keys, horizontal=True, key="market_r",
                          index=keys.index(last),
                          format_func=lambda k: f"{config.MARKETS[k]} 시장",
                          label_visibility="collapsed")
    # 선택이 풀렸으면 직전 시장을 유지합니다 — 빈 화면을 만들지 않습니다.
    if choice not in keys:
        choice = last
    st.session_state["_market_last"] = choice
    try:
        if st.query_params.get("m") != choice:
            st.query_params["m"] = choice
    except Exception:  # noqa: BLE001
        pass
    return choice


def render_body(opts: dict) -> None:
    log = perf.RunLog()
    swr.reset_stale_served()
    # 시세와 이 화면의 데이터를 **동시에** 받기 시작합니다. 전에는 시세 →
    # 공시 → 재고 → 섹터 → 매크로를 한 줄로 기다렸습니다.
    _m = _peek_market()
    _prefetch(_peek_section(_m), _m, opts["demo"], log)
    data = log.measure("시세", load_all, opts["demo"]) if not log.items \
        else load_all(opts["demo"])
    fx = resolve_fx(data.get("yahoo", {}), opts["fx_override"])

    now_kst = dt.datetime.now(KST)
    now_et = now_kst.astimezone(ET)
    clock = (
        f"KST {now_kst:%Y-%m-%d %H:%M:%S}　·　ET {now_et:%H:%M}　·　"
        f"USD/KRW {ui.fmt_num(fx.usdkrw, 2)}"
    )

    st.markdown(
        ui.render_topbar(
            "주식 대시보드", "야간 대체시세 · 시장 지표 · 관심종목", clock,
            market_label=f"{config.MARKETS.get(_peek_market(), '')} 시장"),
        unsafe_allow_html=True,
    )
    # 묵은 값·받는 중 안내가 들어갈 자리. 무엇을 묵은 값으로 그렸는지는 화면을
    # 다 그려야 알 수 있어서, 자리만 잡아 두고 끝에서 채웁니다.
    stale_slot = st.empty()

    if opts["demo"]:
        st.warning(
            "**데모 모드입니다.** 화면의 모든 숫자는 레이아웃 확인용 가짜 값이며 "
            "실제 시세가 아닙니다. 화면 위쪽 표시 패널에서 데모 모드를 끄십시오.",
            icon="⚠️",
        )

    if fx.usdkrw is None and not opts["demo"]:
        st.info(
            "USD/KRW 환율을 가져오지 못해 원화 환산과 괴리율이 표시되지 않습니다. "
            "화면 위쪽 표시 패널에서 환율을 수동 지정할 수 있습니다.",
            icon="ℹ️",
        )

    labels = dict(config.tab_labels())

    # ── 시장 — 최상위 축 ───────────────────────────────────────────────
    # 전에는 내비 맨 아래 작은 라디오였고 기본값이 '전체' 라 아무것도
    # 갈리지 않았습니다. 이제는 **가장 먼저** 고르고, 고른 시장에 따라
    # 왼쪽 섹션 목록 자체가 바뀝니다.
    market = _market_switch()
    opts["market"] = market

    # 시장 띠 — 어느 섹션을 보든 맨 위에 지수·환율·선물 숫자 6개.
    try:
        st.markdown(ui.render_market_strip(
            [(label, inst, pick_quote(inst, data))
             for inst, label in config.strip_instruments(market)]),
            unsafe_allow_html=True)
    except Exception:  # noqa: BLE001 - 띠가 실패해도 본문은 그립니다
        pass

    # st.tabs 는 보이지 않는 탭의 본문까지 전부 실행합니다 — 그래서
    # 선택한 섹션 하나만 실행하는 세로 내비를 씁니다.
    nav_col, body_col = st.columns([1, 5], gap="medium")

    with nav_col:
        active = _section_nav(market, labels)

    with body_col:
        if opts["demo"]:
            st.markdown(ui.render_demo_banner(), unsafe_allow_html=True)

        with st.spinner(SECTION_LOADING.get(active, "불러오는 중…")):
            if active == "summary":
                render_summary_tab(data, fx, opts["demo"], market=market)
            elif active == "holdings":
                render_holdings_tab(data, fx, opts["demo"], opts["phone"],
                                    market=market)
            elif active == "discover":
                render_discover_tab(opts["demo"], market=market)
            elif active == "valuation":
                render_valuation_tab(data, fx, opts["demo"], opts["phone"],
                                     market=market)
            elif active == "chart":
                render_chart_tab(opts["demo"], market=market)
            elif active == "calendar":
                render_calendar_tab(data, opts["demo"], market=market)
            elif active == "research":
                render_research_tab(opts["demo"])
            elif active == "supply":
                render_supply_tab(opts["demo"])
            elif active == "earnings":
                render_earnings_tab(opts["demo"], market=market)
            elif active == "sector_heat":
                render_sector_heat_tab(opts["demo"])
            elif active == "kr_flows":
                _flows_korea(opts["demo"])
            elif active == "us_flows":
                _flows_us(opts["demo"])
            elif active == "macro":
                render_macro_tab(data, fx, opts["demo"], market=market)
            elif active == "cycle":
                render_cycle_tab(opts["demo"], market=market)
            else:
                section = config.SECTION_BY_KEY.get(active)
                if section is not None:
                    render_section(section, data, fx, market=market)

    # 무엇이 느린지 **숫자로** 남깁니다. "느리다" 를 고치려면 어디가
    # 느린지부터 알아야 합니다.
    stale = swr.stale_served()
    oldest, pending = swr.stale_report()
    line = log.summary_line()
    if stale:
        line += (f" · 직전 값으로 먼저 보여준 것 {len(stale)}건 "
                 "(뒤에서 새로 받는 중)")
    st.markdown(ui.render_notice(line), unsafe_allow_html=True)
    notice = _stale_notice(oldest, pending)
    if notice:
        stale_slot.markdown(ui.render_notice(notice), unsafe_allow_html=True)
    _refresh_watch(bool(notice), bool(opts.get("auto")))

    # 다른 섹션 미리 받기 — 화면을 다 그린 **뒤**에 시작합니다
    try:
        _warm_market(market, opts["demo"])
    except Exception:  # noqa: BLE001 - 미리 받기 실패가 화면을 막으면 안 됩니다
        pass

    # 고지 문구 — 전에는 사이드바 맨 아래 있었는데 사이드바를 없앴습니다.
    # 본문 끝이 제자리입니다: 읽고 난 뒤에 보여야 합니다.
    st.markdown(
        ui.render_footnote(
            "정보 제공 목적이며 투자 판단의 근거가 아닙니다. 시세는 지연될 수 "
            "있고, 사용하는 데이터 소스는 어느 것도 공식 API 가 아닙니다."
        ),
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="주식 대시보드",
        page_icon="📈",
        layout="wide",
        # 사이드바를 더 쓰지 않습니다 — 설정은 controls() 가 페이지 안에
        # 그립니다. 접었다 폈다 하는 동작이 번거롭고 휴대폰에서는 화면을
        # 가렸습니다.
        initial_sidebar_state="collapsed",
    )

    # 파일 버전 검사를 **가장 먼저** 합니다. 일부만 올라간 상태면 아래
    # 코드가 AttributeError 로 죽는데, Streamlit Cloud 는 오류 본문을 가려서
    # 어느 파일인지 알 수 없습니다. 죽기 전에 파일 이름을 말해 줍니다.
    try:
        _check = getattr(buildstamp, "verify_cached", buildstamp.verify)
        _build = _check(BASE_DIR)
    except Exception:  # noqa: BLE001 - 검사가 앱을 막으면 안 됩니다
        _build = None
    if _build is not None and not _build.ok:
        st.markdown(ui.render_build_warning(_build), unsafe_allow_html=True)

    opts = controls()
    st.markdown(build_css(opts["convention"], stack=opts.get("stack", True)),
                unsafe_allow_html=True)
    if not opts.get("notes", True):
        # Streamlit 의 본문 컨테이너에 클래스를 걸 수 없어서, 설명 문구를
        # 숨기는 규칙을 전역으로 한 번 더 주입합니다. build_css 의 서명을
        # 바꾸지 않으려는 것입니다 — 테스트와 미리보기가 그걸 씁니다.
        st.markdown(
            "<style>.dash-footnote:not(.dash-notice),.dash-check-detail"
            "{display:none}</style>",
            unsafe_allow_html=True,
        )

    if opts["auto"] and hasattr(st, "fragment"):
        # Streamlit 1.37+ : 지정 주기마다 이 조각만 다시 실행합니다.
        @st.fragment(run_every=opts["interval"])
        def _auto() -> None:
            render_body(opts)

        _auto()
    else:
        render_body(opts)
        if opts["auto"]:
            st.caption(
                "자동 갱신에는 Streamlit 1.37 이상이 필요합니다. "
                "`pip install -U streamlit` 후 다시 실행하거나 '지금 갱신'을 누르십시오."
            )


if __name__ == "__main__":
    main()
