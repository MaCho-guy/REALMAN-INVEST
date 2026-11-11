"""
실시간 주식 대시보드 — Streamlit 앱.

실행:
    streamlit run app.py

구성:
  상단 탭      섹션 전환 (관심종목 / 밸류에이션 / 공시 분석 / DEX 선물 / …)
  설정 패널   테마(나이트·데이), 등락 색상, 갱신, 환율 — 페이지 상단
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

import brief
import buildstamp
import briefing_store as bfs
import value as vl
import analysis_store
import components as ui
import config
import cycle
import buffett
import buffett_kr
import demo as demo_mod
import discover as disc
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
    naver, news, vix, yahoo,
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

@st.cache_data(ttl=config.CACHE_TTL_SEC, show_spinner=False)
def load_all(use_demo: bool) -> dict[str, dict[str, Quote]]:
    """모든 소스에서 시세를 모읍니다. 소스별 실패는 격리됩니다."""
    if use_demo:
        return demo_mod.demo_payload()

    payload: dict[str, dict[str, Quote]] = {"yahoo": {}, "naver": {}, "hyperliquid": {}}

    for bucket, fetch, symbols in (
        ("yahoo", yahoo.fetch_quotes, config.all_yahoo_symbols()),
        ("naver", naver.fetch_quotes, config.all_naver_codes()),
        ("hyperliquid", hyperliquid.fetch_quotes, config.all_hyperliquid_symbols()),
    ):
        try:
            payload[bucket] = fetch(symbols)
        except Exception as exc:  # noqa: BLE001
            payload[bucket] = {
                s: Quote.failed(s, f"{bucket} 소스 전체 실패: {exc}") for s in symbols
            }

    return payload


@st.cache_data(ttl=600, show_spinner=False)
def load_fundamentals(use_demo: bool) -> dict[str, dict]:
    """밸류에이션 지표는 자주 바뀌지 않으므로 캐시를 10분으로 둡니다."""
    symbols = [sym for _label, sym in config.VALUATION_TICKERS]
    if use_demo:
        return demo_mod.demo_fundamentals(symbols, config.VALUATION_FIELDS)
    try:
        return yahoo.fetch_fundamentals(symbols, config.VALUATION_FIELDS)
    except Exception as exc:  # noqa: BLE001
        return {s: {"_error": str(exc)} for s in symbols}


@st.cache_data(ttl=config.EDGAR_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=config.DART_MAP_CACHE_TTL_SEC, show_spinner=False)
def load_corp_codes() -> tuple[dict, str]:
    """종목코드 → DART 고유번호 매핑. (매핑, 오류메시지)"""
    try:
        return dart.fetch_corp_codes(), ""
    except dart.DartKeyMissing as exc:
        return {}, str(exc)
    except Exception as exc:  # noqa: BLE001
        return {}, f"DART 고유번호 조회 실패: {exc}"


@st.cache_data(ttl=config.DART_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=config.DART_FINANCIALS_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=config.DART_FINANCIALS_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=config.NEWS_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=21_600, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
def load_briefings() -> list:
    """증시 브리핑. 로컬 파일이라 캐시를 짧게 둡니다 — 파일을 새로 넣고
    1분 안에 보이는 편이, 캐시를 길게 잡아 '왜 안 보이지' 하는 것보다 낫습니다.
    """
    return bfs.load_all(BRIEFING_PATH)


@st.cache_data(ttl=config.MACRO_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=config.SCREEN_CACHE_TTL_SEC, show_spinner=False)
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


@st.cache_data(ttl=600, show_spinner=False)
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
            f"{min_pass}개 이상 통과", "각 카드의 질문을 Claude 에 붙여넣으면 정독이 시작됩니다",
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
                       use_demo: bool) -> None:
    """요약. 다른 탭에서 이미 캐시된 것만 씁니다 — 휴대폰에서 느려지면 안 됩니다.

    발굴·밸류에이션은 일부러 빼둡니다. 68종목의 10년 재무를 받아오는 작업이라
    휴대폰 글랜스에 맞지 않습니다 — 어디로 가면 되는지만 적습니다.
    """
    found, instruments, trends, _filings, _errors = _detect_signals(
        data, use_demo)
    # 요약은 "지금 N건" 과 "이번 주 N건" 을 구분해 적어야 해서 세 갈래가
    # 필요합니다. signals.split_by_urgency 는 둘을 합쳐 두 갈래로 주므로
    # **여기서 직접 나눕니다** — 다른 파일을 함께 고쳐야 하는 변경을 피하려는
    # 것입니다. 파일을 손으로 맞추다 보면 한쪽만 올라가 AttributeError 가
    # 납니다. 세 줄짜리 분류라 공유 함수로 뺄 이득이 적습니다.
    collapsed = sig_mod.collapse(found)
    urgent = [s for s in collapsed if s.severity >= 3]
    soon = [s for s in collapsed if s.severity == 2]

    fg = load_feargreed(use_demo)
    vix_state = load_vix(use_demo)
    series_map, errors = load_macro(use_demo, fred.key_fingerprint())
    readings = macro_mod.build_readings(config.macro_series(), series_map, errors)

    summary = sm.build(
        urgent=urgent, soon=soon, holdings_total=len(instruments),
        fg=fg, vix_state=vix_state, trends=trends, macro_readings=readings,
    )

    st.markdown(ui.render_summary(summary), unsafe_allow_html=True)

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

def render_holdings_tab(data: dict[str, dict[str, Quote]], fx,
                        use_demo: bool, phone: bool = False) -> None:
    """내가 가진 종목에 대해 알아야 할 전부를 한 화면에.

    예전에는 '변화 감지' · '관심종목' · '공시 분석' 세 탭이었습니다. 보유 종목을
    볼 때는 늘 세 탭을 다 열어야 했으니 나뉘어 있을 이유가 없었습니다.
    순서가 중요합니다 — **지금 확인할 것이 맨 위**, 그다음 시세, 그다음 분석.
    """
    watchlist = config.SECTION_WATCHLIST
    local = config.SECTION_LOCAL

    render_signals_tab(data, use_demo)

    st.markdown(
        ui.render_section_head("보유 · 관심 종목", watchlist.subtitle,
                               len(watchlist.instruments)),
        unsafe_allow_html=True,
    )
    cards = "".join(
        ui.render_card(inst, (data.get(inst.source) or {}).get(inst.symbol), fx)
        for inst in watchlist.instruments
    )
    st.markdown(f'<div class="dash-grid cols-4">{cards}</div>',
                unsafe_allow_html=True)

    others = [i for i in local.instruments
              if i.symbol not in {w.symbol for w in watchlist.instruments}]
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

@st.cache_data(ttl=300, show_spinner=False)
def load_discovery_quotes(use_demo: bool) -> dict[str, dict[str, Quote]]:
    """발굴 대상 전체의 시세. 52주 고가·저가가 필요합니다."""
    if use_demo:
        return demo_mod.demo_discovery_quotes()
    us = config.screen_tickers()
    kr = [code for code, _n in config.screen_kr_candidates()]
    out: dict[str, dict[str, Quote]] = {"yahoo": {}, "naver": {}}
    try:
        out["yahoo"] = yahoo.fetch_quotes(us)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["naver"] = naver.fetch_quotes(kr)
    except Exception:  # noqa: BLE001
        pass
    return out


def _discovery_instruments() -> tuple[list, list]:
    """발굴 대상을 Instrument 로 만듭니다 (미국, 국내).

    이미 config 에 정의된 종목은 그 정보를 재사용하고, 후보 목록에만 있는
    종목은 최소 정보로 만듭니다.
    """
    from config import Instrument

    known = {i.symbol: i for i in config.all_instruments()}
    us = [known.get(t) or Instrument(name=t, symbol=t, source="yahoo",
                                     currency="USD", verified=False)
          for t in config.screen_tickers()]
    kr = [known.get(c) or Instrument(name=n, symbol=c, source="naver",
                                     currency="KRW", verified=False,
                                     decimals=0, suffix="원")
          for c, n in config.screen_kr_candidates()]
    return us, kr


def render_discover_tab(use_demo: bool) -> None:
    """종목 발굴 — 52주 위치와 품질을 교차합니다."""
    st.markdown(
        ui.render_section_head(
            "종목 발굴", "52주 위치 × 버핏식 품질 기준 — 읽을 목록을 줄입니다", 0),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "<b>52주 신고가는 모멘텀 지표입니다.</b> '좋은 주식' 이 아니라 "
            "'최근 많이 오른 주식' 입니다 — 신고가인 이유가 비싸서일 수도 "
            "있습니다. 그래서 단독으로 쓰지 않고 <b>버핏식 품질 기준과 "
            "교차</b>합니다. ③ 저가권 + 품질 통과가 가치투자가 전통적으로 찾는 "
            "자리이고, ① 고가권 + 품질 통과는 시장이 이미 알아본 자리입니다."
        ),
        unsafe_allow_html=True,
    )

    market = st.radio("시장", ["미국", "국내"], horizontal=True,
                      key="disc_market")
    col1, col2 = st.columns([1, 1])
    with col1:
        # 기준이 6개에서 9개로 늘었습니다. 기본값을 4로 두면 전보다
        # 느슨해지므로, 같은 비율(약 2/3)을 유지합니다.
        quality_min = st.slider("품질 기준 통과 수 (이상이면 '통과')",
                                1, len(buffett.CRITERIA),
                                round(len(buffett.CRITERIA) * 2 / 3),
                                key="disc_q")
    with col2:
        view = st.radio("정렬", ["고가권부터", "저가권부터"], horizontal=True,
                        key="disc_sort")

    quotes = load_discovery_quotes(use_demo)
    us_inst, kr_inst = _discovery_instruments()

    if market == "미국":
        instruments = us_inst
        screens_map, errors = load_screens(use_demo)
    else:
        instruments = kr_inst
        screens_map, errors = load_kr_screens(use_demo, dart.key_fingerprint())

    positions = disc.build_positions(instruments, quotes, screens=screens_map)
    counts = disc.summary_counts(positions)

    st.markdown(
        ui.render_footnote(
            " · ".join(f"<b>{k}</b> {v}" for k, v in counts.items())
            + (f" · 품질 스크리닝 실패 {len(errors)}건" if errors else "")
        ),
        unsafe_allow_html=True,
    )

    groups = disc.group_by_quadrant(positions, quality_min)

    # 품질 축이 없는 종목이 대부분이면 지도가 오해를 부릅니다 — 사분면이
    # 비어 보이는 게 '해당 종목이 없다' 가 아니라 '재무를 못 받았다' 일 수
    # 있으므로 반드시 구분해서 말해야 합니다.
    usable = [p for p in positions if p.ok]
    with_quality = [p for p in usable if p.has_quality]
    if usable and len(with_quality) < len(usable) * 0.5:
        st.markdown(
            ui.render_footnote(
                f"<b>사분면 지도가 비어 보이는 이유:</b> 52주 데이터는 "
                f"{len(usable)}종목에 있는데 <b>품질 스크리닝 결과는 "
                f"{len(with_quality)}종목</b>에만 있습니다. 사분면은 두 축이 "
                "모두 있어야 분류되므로, 나머지는 '중간 구간 · 판정 없음' 으로 "
                "갑니다 — 해당하는 종목이 없다는 뜻이 아닙니다."
                + ("<br>데모 모드에서는 재무 데이터가 몇 종목만 들어 있습니다. "
                   "실제 데이터로 보려면 화면 위쪽 표시 패널에서 데모 모드를 끄십시오."
                   if use_demo else "")
            ),
            unsafe_allow_html=True,
        )
    st.markdown(ui.render_discover_map(groups), unsafe_allow_html=True)

    order = (disc.rank_by_high(positions) if view == "고가권부터"
             else disc.rank_by_low(positions))
    shown = [p for p in order if p.ok][:30]

    st.markdown(
        ui.render_section_head(
            view, "표의 ○ 는 품질 기준 통과, ✗ 는 미달, ? 는 판정 불가",
            len(shown)),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_discover_table(shown, quality_min),
                unsafe_allow_html=True)

    focus = (groups[1] + groups[3])[:8]
    if focus:
        st.markdown(
            ui.render_section_head(
                "주목 구간 (① · ③)", "품질 기준을 넘은 종목만", len(focus)),
            unsafe_allow_html=True,
        )
        for pos in focus:
            st.markdown(
                ui.render_discover_card(
                    pos, quality_min, prompt=disc.prompt_for(pos, quality_min)),
                unsafe_allow_html=True,
            )

    failed = [p for p in positions if not p.ok]
    if failed:
        st.markdown(
            ui.render_footnote(
                f"<b>조회 실패 {len(failed)}건:</b> "
                + " · ".join(f"{p.ticker} ({p.error[:34]})" for p in failed[:6])
            ),
            unsafe_allow_html=True,
        )


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

    checks = (
        # 개수를 적어 두면 계열을 늘릴 때마다 어긋납니다.
        ("fred", "경제지표 계열 확인",
         f"FRED 계열 {len(config.MACRO_SERIES)}개가 실제로 받아지는지. "
         "연결 자체도 먼저 시험합니다. 키 불필요.",
         diag.diagnose_fred),
        ("screen", "미국 스크리너 확인", "companyfacts 에서 계정이 잡히는지 (앞 8개 기업). 키 불필요.",
         diag.diagnose_screen),
        ("xbrl", "재고 지표 확인 (미국)", "MU 의 XBRL 태그와 DIO 계산. 키 불필요.",
         diag.diagnose_xbrl),
        ("dart", "DART 확인 (국내)", "재고 구성 계정과 DIO. **인증키 필요.**",
         diag.diagnose_dart),
        ("krexp", "반도체 수출 확인 (한국)",
         "산업통상부 보도자료 긁기. **한 번도 성공한 적 없는 경로입니다** — "
         "막혀 있으면 쓰지 않는 게 맞습니다. 키 불필요.",
         diag.diagnose_kr_exports),
    )

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
            ui.render_footnote(
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
            ui.render_footnote(
                f"<b>조회 실패 {len(errors)}건:</b> "
                + " · ".join(f"{t} ({m[:50]})" for t, m in list(errors.items())[:5])
            ),
            unsafe_allow_html=True,
        )


@st.cache_data(ttl=config.SCREEN_CACHE_TTL_SEC, show_spinner=False)
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
            ui.render_footnote(
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
            ui.render_footnote(
                f"<b>조회 실패 {len(failed)}건:</b> "
                + " · ".join(f"{t} ({m[:50]})" for t, m in failed[:6])
            ),
            unsafe_allow_html=True,
        )


@st.cache_data(ttl=1800, show_spinner=False)
def load_feargreed(use_demo: bool):
    """CNN 공포탐욕지수. 실패하면 error 가 담긴 객체가 돌아옵니다 —
    문서화되지 않은 내부 엔드포인트라 다른 지표와 격리해 둡니다."""
    if use_demo:
        return demo_mod.demo_feargreed()
    return feargreed.fetch()


@st.cache_data(ttl=300, show_spinner=False)
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


def render_macro_tab(data: dict[str, dict[str, Quote]], fx, use_demo: bool) -> None:
    """매크로 — 시장가격(실시간)과 통계(지연)를 분리해서 보여줍니다."""
    section = config.SECTION_BY_KEY.get("macro")

    # 0) 증시 브리핑 — 사람이 쓴 글이 숫자보다 먼저 옵니다. 숫자를 보기 전에
    #    '지금 무슨 상황인지' 를 읽는 순서가 맞습니다.
    render_briefing_section(use_demo)

    # 1) 시장가격 — 야후, 실시간
    if section is not None:
        render_section(section, data, fx)

    # 2) 공포탐욕지수 — 시장 심리. 가격도 통계도 아닌 제3의 성격이라
    #    둘 사이에 둡니다.
    fg = load_feargreed(use_demo)
    st.markdown(
        ui.render_section_head(
            "공포탐욕지수 (CNN Fear & Greed)",
            "시장 심리 0~100 · 세부 지표 7개로 '왜 그 값인가' 를 함께",
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
                + ". 지수 한 숫자만 보면 같은 '탐욕 70' 이 주가 모멘텀 때문인지 "
                "채권 수요 때문인지 알 수 없어서, 극단에 있는 세부 지표를 "
                "따로 적었습니다."
            ),
            unsafe_allow_html=True,
        )
    st.markdown(
        ui.render_footnote(
            "<b>출처 주의 —</b> CNN 이 자기 페이지에서 쓰는 "
            "<b>문서화되지 않은 내부 엔드포인트</b>입니다. 공개 API 가 아니라 "
            "예고 없이 바뀌거나 막힐 수 있어, 실패해도 다른 지표에 영향이 "
            "가지 않게 격리했습니다. 이 지수는 <b>심리 지표이고 가치 판단이 "
            "아닙니다</b> — 탐욕 구간이라고 비싸다는 뜻이 아닙니다."
        ),
        unsafe_allow_html=True,
    )

    # 3) VIX 기간구조 — 공탐지수와 같은 심리·위험 묶음
    vix_state = load_vix(use_demo)
    st.markdown(
        ui.render_section_head(
            "VIX 기간구조",
            "숫자 하나가 아니라 곡선의 모양 · 과거 대비 위치",
            sum(1 for p in vix_state.points if p.ok),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(ui.render_vix(vix_state), unsafe_allow_html=True)
    st.markdown(
        ui.render_footnote(
            "<b>VIX 숫자 하나는 쓸모가 적습니다.</b> 18 이 높은지 낮은지는 맥락 "
            "없이 답할 수 없어서, 위 카드의 VIX 값에 두 가지를 붙였습니다 — "
            "<b>과거 대비 백분위</b>(FRED VIXCLS 5년)와 <b>기간구조</b>"
            "(VIX9D→VIX→VIX3M→VIX6M 곡선의 모양).<br>"
            "평소에는 뒤 만기가 더 높습니다(<b>콘탱고</b>). 위기에는 앞이 치솟아 "
            "뒤보다 높아집니다(<b>백워데이션</b>) — 2010년 이후 전체 거래일의 "
            f"<b>{vix.BACKWARDATION_BASE_RATE:g}%</b> 에만 나타났으니, 드물기 "
            "때문에 신호가 됩니다."
        ),
        unsafe_allow_html=True,
    )

    # 4) 통계 — FRED, 발표 지연 있음
    series_map, errors = load_macro(use_demo, fred.key_fingerprint())
    readings = macro_mod.build_readings(config.macro_series(), series_map, errors)
    triggers = macro_mod.evaluate_all(readings)
    hit_keys = {t.reading.spec.key for t in triggers}

    # 3) 임계값을 건드린 것만 먼저. 전에는 '경제지표' 헤더와 그 내용
    #    사이에 끼어 있어서, 헤더가 '14개 항목' 이라고 적힌 바로 아래
    #    다른 섹션이 나오고 지표는 한참 뒤에 나왔습니다.
    if triggers:
        st.markdown(
            ui.render_section_head(
                "임계값 도달", "이 지표만 확인하십시오", len(triggers)),
            unsafe_allow_html=True,
        )
        news_targets = tuple(
            macro_mod.news_queries(triggers, limit=config.MACRO_MAX_NEWS_TARGETS))
        headlines = load_news(news_targets, use_demo)
        for trig in triggers:
            st.markdown(
                ui.render_macro_trigger(trig, macro_mod.prompt_for(trig)),
                unsafe_allow_html=True,
            )
            items = headlines.get(trig.reading.spec.key)
            if items:
                st.markdown(ui.render_news_block(items), unsafe_allow_html=True)
    else:
        st.markdown(
            ui.render_footnote(
                "<b>임계값에 닿은 지표가 없습니다.</b> 조용한 게 정상입니다 — "
                "이 탭은 뉴스 피드가 아니라, 지표가 실제로 움직였을 때만 "
                "올라오게 만들었습니다."
            ),
            unsafe_allow_html=True,
        )

    # 4) 전체 지표 — 위의 '임계값 도달' 이 요약이고 여기가 전체 목록입니다
    st.markdown(
        ui.render_section_head(
            "경제지표 (FRED)",
            "발표 지연이 있는 통계 — 위 가격 카드와 성격이 다릅니다",
            len(readings),
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        ui.render_footnote(
            "위 카드는 <b>시장가격</b>(실시간), 아래는 <b>통계</b>입니다. "
            "통계는 발표가 2~6주 늦으므로 각 칸에 <b>관측 시점과 지연일수</b>를 "
            "함께 적었습니다 — 어제 숫자로 착각하면 판단이 틀립니다. "
            "지수 계열(산업생산·PPI)은 기준연도가 바뀌어 레벨 비교가 불가능하므로 "
            "<b>전년 동기 대비</b>만 표시합니다. FRED 는 인증키가 필요 없습니다."
        ),
        unsafe_allow_html=True,
    )

    show_why = st.toggle("각 지표를 보는 이유 표시", value=False,
                         key="macro_why",
                         help="왜 이 지표가 제 포트폴리오와 연결되는지")
    by_group: dict[str, list] = {}
    for reading in readings:
        by_group.setdefault(reading.spec.group, []).append(reading)

    for key, title, subtitle in config.MACRO_GROUPS:
        st.markdown(
            ui.render_macro_group(title, subtitle, by_group.get(key, []),
                                  hit_keys, show_why=show_why),
            unsafe_allow_html=True,
        )

    unverified = [r.spec for r in readings if not r.spec.verified]
    failed = [(sid, msg) for sid, msg in errors.items()]
    if failed:
        st.markdown(
            ui.render_footnote(
                "<b>수집 실패:</b> "
                + " · ".join(f"{sid} ({msg[:60]})" for sid, msg in failed[:5])
            ),
            unsafe_allow_html=True,
        )
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

def render_section(section: Section, data: dict[str, dict[str, Quote]], fx) -> None:
    st.markdown(
        ui.render_section_head(section.title, section.subtitle, len(section.instruments)),
        unsafe_allow_html=True,
    )

    instruments = list(section.instruments)
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
                         use_demo: bool, phone: bool = False) -> None:
    """4. 걸러낸 종목 밸류에이션 — 역DCF 가 중심, 지표표는 보조.

    '걸러낸 종목' 은 두 갈래입니다: **내가 가진 것**(판단이 이미 필요함)과
    **발굴에서 품질 기준을 넘은 것**(판단이 곧 필요함). 둘을 같은 화면에 놓아야
    "가진 것 대신 이걸 볼 이유가 있나" 를 비교할 수 있습니다.
    """
    st.markdown(
        ui.render_section_head(
            "밸류에이션 판단", "현재 가격이 요구하는 성장률 vs 과거 실제", 0),
        unsafe_allow_html=True,
    )
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

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        market = st.radio("시장", ["미국", "국내"], horizontal=True,
                          key="val_market")
    with col2:
        scope = st.radio("대상", ["보유 + 발굴 통과", "전체"], horizontal=True,
                         key="val_scope")
    with col3:
        show_source = st.toggle("기준 출처·한계 표시", value=False,
                                key="val_src")

    if market == "미국":
        screens_map, errors = load_screens(use_demo)
        currency = "USD"
        held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
                if i.source == "yahoo"}
    else:
        screens_map, errors = load_kr_screens(use_demo, dart.key_fingerprint())
        currency = "KRW"
        held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
                if i.source == "naver"}

    screens = buffett.rank(list(screens_map.values()))
    if scope == "보유 + 발굴 통과":
        threshold = max(1, round(len(buffett.CRITERIA) * 2 / 3))
        screens = [s for s in screens
                   if s.ticker in held or s.passed_count >= threshold]

    triples = _attach_dcf(screens, use_demo, currency=currency)
    # **정렬 전에** 부릅니다 — load_market_caps 캐시 키가 티커 순서라
    # 정렬 후에 부르면 캐시를 놓치고 야후를 다시 칩니다.
    prices = _price_screens(triples, use_demo)
    if not triples:
        st.markdown(
            ui.render_footnote(
                "<b>대상 종목이 없습니다.</b> "
                + ("'전체' 로 바꿔 보십시오. "
                   if scope != "전체" else "")
                + (" · ".join(f"{t}: {m[:60]}"
                              for t, m in list(errors.items())[:3])
                   if errors else "")
            ),
            unsafe_allow_html=True,
        )
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

def _detect_signals(data: dict[str, dict[str, Quote]], use_demo: bool):
    """변화 감지 한 번. 요약 탭과 변화 감지 탭이 **같은 경로**를 씁니다.

    두 화면이 다른 결과를 보여주면 신뢰를 잃으므로 함수 하나로 모았습니다.
    반환: (신호 목록, 종목 목록, 추세, 공시, 오류 모음)
    오류 모음은 {"edgar": {...}, "dart": {...}, "trend": {...}} 입니다 —
    화면에 "무엇을 못 받았는지" 를 적어야 하므로 버리지 않고 넘깁니다.
    """
    instruments = list(config.SECTION_WATCHLIST.instruments)

    docs = analysis_store.load_all(
        ANALYSIS_PATH, [i.analysis_key for i in instruments if i.analysis_key]
    )

    # EDGAR(미국) + DART(한국) 공시를 하나로 — 두 Filing 이 같은 속성을
    # 제공하므로 signals 는 구분하지 않습니다.
    filings, filing_errors = load_filings(use_demo)
    dart_filings, dart_errors = load_dart_disclosures(use_demo, dart.key_fingerprint())
    merged_filings = {**filings, **dart_filings}

    kr_trends, trend_errors = load_inventory_trends(use_demo, dart.key_fingerprint())
    us_trends, us_trend_errors = load_us_inventory_trends(use_demo)
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


def render_signals_tab(data: dict[str, dict[str, Quote]], use_demo: bool) -> None:
    """변화 감지 — 뭘 봐야 하는지 알려주는 화면."""
    instruments = list(config.SECTION_WATCHLIST.instruments)

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
    found, _inst, _trends, _filings, errs = _detect_signals(data, use_demo)
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

    st.markdown(
        ui.render_footnote(
            "공시는 SEC EDGAR 공개 API(키 불필요)에서 실시간으로 받아옵니다. "
            "한국 종목(삼성전자·SK하이닉스)은 EDGAR 에 없어 공시 감지가 되지 않습니다 — "
            "DART 오픈API 를 붙이려면 무료 키 발급이 필요합니다. "
            "헤드라인은 제목과 링크만 가져오며, 공시나 급등락이 감지된 종목에만 붙습니다."
        ),
        unsafe_allow_html=True,
    )


def render_cycle_tab(use_demo: bool) -> None:
    """재고 지표 — 반도체 사이클 레이어 2. 메모리 3사를 한 화면에서 비교."""
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

    kr_trends, kr_errors = load_inventory_trends(use_demo, dart.key_fingerprint())
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
# 사이드바
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


def controls() -> dict:
    """설정을 **페이지 안**에 둡니다.

    전에는 전부 사이드바에 있었는데, 왼쪽을 접었다 폈다 해야 해서 번거롭고
    휴대폰에서는 화면을 가립니다. 한 줄에 묶고, 자주 안 쓰는 것은 버튼을
    눌러 펼치는 패널에 넣습니다. 매일 쓰는 건 '지금 갱신' 하나뿐입니다.
    """
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

    with c1:
        seg = getattr(st, "segmented_control", None)
        opts_theme = ["🌙 나이트", "☀️ 데이"]
        default = opts_theme[0 if config.DEFAULT_THEME == "dark" else 1]
        if seg is not None:
            try:
                theme_label = seg("테마", opts_theme, default=default,
                                  key="ui_theme", label_visibility="collapsed")
            except Exception:  # noqa: BLE001
                theme_label = st.radio("테마", opts_theme, horizontal=True,
                                       key="ui_theme_r",
                                       label_visibility="collapsed")
        else:
            theme_label = st.radio("테마", opts_theme, horizontal=True,
                                   key="ui_theme_r",
                                   label_visibility="collapsed")
        mode = "dark" if (theme_label or opts_theme[0]).startswith("🌙") \
            else "light"

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
                "휴대폰 모드", value=False,
                help="무거운 것을 아예 싣지 않습니다 — 공시 분석 본문(수십 KB)과 "
                     "넓은 지표표를 생략합니다. 요약·시세·매크로는 그대로입니다.",
            )
            show_notes = st.toggle(
                "설명 문구 표시", value=True,
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
            auto = st.toggle("자동 갱신", value=config.AUTO_REFRESH_SEC > 0)
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
            render_diag_panel()
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
        "mode": mode,
        "convention": convention,
        "phone": phone,
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
    "valuation": "밸류에이션 — 스크리닝 결과로 역DCF 를 계산합니다 (처음 1~3분)",
    "cycle": "메모리 사이클 — 재고 추이를 받아옵니다 (처음 20~60초)",
}


def render_body(opts: dict) -> None:
    data = load_all(opts["demo"])
    fx = resolve_fx(data.get("yahoo", {}), opts["fx_override"])

    now_kst = dt.datetime.now(KST)
    now_et = now_kst.astimezone(ET)
    clock = (
        f"KST {now_kst:%Y-%m-%d %H:%M:%S}　·　ET {now_et:%H:%M}　·　"
        f"USD/KRW {ui.fmt_num(fx.usdkrw, 2)}"
    )

    st.markdown(
        ui.render_topbar("주식 대시보드", "야간 대체시세 · 시장 지표 · 관심종목", clock),
        unsafe_allow_html=True,
    )

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

    pairs = config.tab_labels()
    keys = [k for k, _l in pairs]
    labels = dict(pairs)

    # st.tabs 는 **보이지 않는 탭의 본문까지 전부 실행합니다.** 탭 전환이
    # 브라우저에서 즉시 되는 이유가 그것입니다 — 이미 다 그려둔 것을
    # 보여주기만 합니다. 그래서 요약만 보려 해도 스크리닝 95종목(SEC 65 +
    # DART 30×4)과 재고 추이까지 돌아 요청이 250건 가까이 나갔습니다.
    # 선택한 섹션 하나만 실행하도록 바꿉니다. 탭 전환 때 서버를 한 번
    # 왕복하는 대신, 첫 로딩에서 안 볼 섹션 값을 치르지 않습니다.
    picker = getattr(st, "segmented_control", None)
    try:
        if picker is not None:
            active = picker(
                "섹션", keys, default=keys[0], key="nav",
                format_func=lambda k: labels.get(k, k),
                label_visibility="collapsed",
            )
        else:
            active = st.radio(
                "섹션", keys, horizontal=True, key="nav",
                format_func=lambda k: labels.get(k, k),
                label_visibility="collapsed",
            )
    except Exception:  # noqa: BLE001 - 위젯 인자는 버전마다 다릅니다
        active = st.radio("섹션", keys, horizontal=True, key="nav_fallback",
                          format_func=lambda k: labels.get(k, k))

    # segmented_control 은 같은 칸을 다시 눌러 선택 해제가 됩니다.
    # 그 상태로 두면 화면이 빈 채로 남으니 요약으로 되돌립니다.
    if active not in labels:
        active = keys[0]

    if opts["demo"]:
        st.markdown(ui.render_demo_banner(), unsafe_allow_html=True)

    with st.spinner(SECTION_LOADING.get(active, "불러오는 중…")):
        if active == "summary":
            render_summary_tab(data, fx, opts["demo"])
        elif active == "holdings":
            render_holdings_tab(data, fx, opts["demo"], opts["phone"])
        elif active == "discover":
            render_discover_tab(opts["demo"])
        elif active == "macro":
            render_macro_tab(data, fx, opts["demo"])
        elif active == "valuation":
            render_valuation_tab(data, fx, opts["demo"], opts["phone"])
        elif active == "cycle":
            render_cycle_tab(opts["demo"])
        else:
            section = config.SECTION_BY_KEY.get(active)
            if section is not None:
                render_section(section, data, fx)

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
        _build = buildstamp.verify(BASE_DIR)
    except Exception:  # noqa: BLE001 - 검사가 앱을 막으면 안 됩니다
        _build = None
    if _build is not None and not _build.ok:
        st.markdown(ui.render_build_warning(_build), unsafe_allow_html=True)

    opts = controls()
    st.markdown(build_css(opts["mode"], opts["convention"]), unsafe_allow_html=True)
    if not opts.get("notes", True):
        # Streamlit 의 본문 컨테이너에 클래스를 걸 수 없어서, 설명 문구를
        # 숨기는 규칙을 전역으로 한 번 더 주입합니다. build_css 의 서명을
        # 바꾸지 않으려는 것입니다 — 테스트와 미리보기가 그걸 씁니다.
        st.markdown(
            "<style>.dash-footnote,.dash-check-detail{display:none}</style>",
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
