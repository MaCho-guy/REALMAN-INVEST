"""
데모 데이터로 대시보드를 정적 HTML 한 장으로 렌더링합니다.

Streamlit 을 설치하지 않고도 실제 앱과 같은 섹션 전환을
눈으로 확인할 용도입니다. 카드·테이블은 앱과 동일한 components.py / theme.py
를 쓰므로 여기서 보이는 모양이 앱에서도 그대로 나옵니다.

실행:
    cd stock_dashboard
    python -m tools.preview          # preview.html (데모 데이터)
    python -m tools.preview --live   # 실제 시세로 렌더링 (네트워크 필요)

주의: 데모 모드의 숫자는 가짜입니다.
"""

from __future__ import annotations

import sys

import analysis_store
import components as ui
import config
import demo as demo_mod
from compute import compute_premium, pick_quote, resolve_fx
from theme import build_rules, build_stack_rules, build_vars

EXTRA_CSS = """
  body {
    margin: 0; padding: 0;
    background: var(--dash-page);
    font-family: system-ui, -apple-system, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
    transition: background 0.15s ease;
  }
  .dash-wrap { max-width: 1480px; margin: 0 auto; padding: 24px 28px 56px 28px; }
  .dash-grid {
    display: grid; gap: 12px; margin-bottom: 6px;
    grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
  }
  @media (max-width: 1100px) { .dash-grid { --cols: 2 !important; } }
  @media (max-width: 680px)  { .dash-grid { --cols: 1 !important; } }

  /* 시장 전환 — 최상위 축 */
  .pv-market {
    display: inline-flex; gap: 4px; padding: 4px; margin: 0 0 16px;
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card);
  }
  .pv-mkt {
    appearance: none; border: none; cursor: pointer; font: inherit;
    font-size: var(--fs-5); font-weight: 700; color: var(--dash-ink-2);
    background: transparent; padding: 9px 24px;
    border-radius: var(--r-inner); min-height: 42px;
  }
  .pv-mkt:hover { background: var(--dash-raised); color: var(--dash-ink); }
  .pv-mkt[aria-pressed="true"] {
    background: var(--dash-accent); color: #ffffff;
  }
  .pv-nav[hidden] { display: none !important; }

  /* 섹션 내비 — 앱과 같이 세로입니다 */
  /* 앱 기본값과 같이: 설명 문단은 숨기고, 꼭 필요한 안내(notice)만 */
  .dash-footnote:not(.dash-notice) { display: none; }
  body.pv-notes .dash-footnote { display: block; }
  /* 앱의 설정 줄과 같은 모양 — 표시 · 데이터 · 진단 · 갱신 이 한 줄 */
  .pv-ctrl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
             gap: 8px; margin: 0 0 12px; }
  .pv-ctrl span { display: block; text-align: center; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    font-size: var(--fs-3); color: var(--dash-ink);
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-inner); padding: 8px 6px; }
  .pv-topctl { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
               margin-bottom: 12px; }
  .pv-topctl .pv-market { margin-bottom: 0; }
  .pv-notes-btn { appearance: none; cursor: pointer; font: inherit;
    font-size: var(--fs-3); color: var(--dash-ink-2); background: none;
    border: 1px solid var(--dash-border); border-radius: var(--r-pill);
    padding: 5px 12px; }
  .pv-notes-btn[aria-pressed="true"] { color: var(--dash-ink); border-color: var(--dash-accent); }
  .pv-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
              font-size: var(--fs-2); color: var(--dash-ink-muted); margin: 6px 0 8px; }
  .pv-chip { border: 1px solid var(--dash-border); border-radius: var(--r-pill);
             padding: 4px 11px; color: var(--dash-ink); font-size: var(--fs-3);
             background: var(--dash-surface); }
  .pv-chips em { font-style: normal; }
  .pv-shell { display: flex; gap: 26px; align-items: flex-start; }
  .pv-side {
    flex: 0 0 176px; position: sticky; top: 14px;
    background: var(--dash-surface);
    border: 1px solid var(--dash-border);
    border-radius: var(--r-card);
    padding: 12px 8px;
    align-self: flex-start;
  }
  .pv-main { flex: 1 1 auto; min-width: 0; }
  /* 앱과 같은 모양: 스트림릿 버튼 — 흰 바탕 테두리, 지금 섹션은 남색 채움 */
  .pv-tabs { display: flex; flex-direction: column; gap: 6px; }
  .pv-tab {
    appearance: none; cursor: pointer; text-align: left;
    background: var(--dash-surface);
    border: 1px solid color-mix(in srgb, var(--dash-ink) 26%, var(--dash-surface));
    color: var(--dash-ink);
    font: inherit; font-size: var(--fs-4); font-weight: 600;
    min-height: 40px; padding: 6px 12px; border-radius: var(--r-inner);
    transition: background 0.12s ease, border-color 0.12s ease;
  }
  .pv-tab:hover { background: var(--dash-raised); border-color: var(--dash-accent); }
  .pv-tab[aria-selected="true"] {
    background: var(--dash-accent); border-color: var(--dash-accent);
    color: #fff; font-weight: 750;
  }
  .pv-navgroup {
    font-size: var(--fs-1); font-weight: 700; letter-spacing: .06em;
    color: var(--dash-ink-muted); margin: 12px 0 2px; padding-left: 2px;
  }
  .pv-navgroup:first-child { margin-top: 0; }
  @media (max-width: 760px) {
    .pv-shell { display: block; }
    .pv-side { position: static; margin-bottom: 14px; flex: none; }
    .pv-tabs { flex-direction: row; flex-wrap: wrap; align-items: center; }
    .pv-navgroup { width: 100%; margin: 8px 0 0; }
    .pv-tab { min-height: 36px; }
  }
  .pv-fold > summary {
    cursor: pointer; font-size: .8rem; font-weight: 600;
    color: var(--dash-ink-2); padding: 10px 13px; margin: 6px 0 2px;
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: 9px; list-style: none;
  }
  .pv-fold > summary::marker, .pv-fold > summary::-webkit-details-marker { display: none; }
  .pv-fold > summary::before { content: "▸ "; color: var(--dash-ink-muted); }
  .pv-fold[open] > summary::before { content: "▾ "; }
  .pv-panel[hidden] { display: none; }
  .pv-fold-body { padding: 2px 0 10px; }

  .demo-banner {
    border: 1px solid var(--dash-badge-pre); color: var(--dash-badge-pre);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 18px;
    font-size: 0.78rem; line-height: 1.55;
  }
  .pv-note {
    font-size: 0.75rem; color: var(--dash-ink-muted); line-height: 1.6;
    border: 1px solid var(--dash-border); border-radius: 8px;
    padding: 14px 16px; margin-bottom: 16px;
  }
  .pv-note code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.72rem; background: var(--dash-surface);
    border: 1px solid var(--dash-border); border-radius: 4px; padding: 1px 5px;
  }
  details.pv-prompt { margin: -4px 0 14px 0; }
  details.pv-prompt summary {
    cursor: pointer; font-size: 0.74rem; font-weight: 600;
    color: var(--dash-ink-muted); padding: 5px 0 5px 3px;
  }
  details.pv-prompt summary:hover { color: var(--dash-ink-2); }
  details.pv-fyi { margin: 10px 0 6px; }
  details.pv-fyi > summary {
    cursor: pointer; font-size: 0.8rem; font-weight: 650;
    color: var(--dash-ink-2); padding: 9px 13px;
    border: 1px solid var(--dash-border); border-radius: 8px;
    background: var(--dash-surface);
  }
  details.pv-fyi[open] > summary { margin-bottom: 10px; }
  details.pv-prompt pre {
    margin: 4px 0 0; padding: 12px 14px; overflow-x: auto;
    background: var(--dash-surface); color: var(--dash-ink-2);
    border: 1px solid var(--dash-border); border-radius: 7px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.73rem; line-height: 1.6; white-space: pre-wrap;
  }
"""

TAB_SCRIPT = """
(function () {
  // 앱과 같은 구조: 시장을 먼저 고르면 그 시장의 섹션 목록이 나옵니다.
  var markets = Array.prototype.slice.call(document.querySelectorAll('.pv-mkt'));
  var navs = Array.prototype.slice.call(document.querySelectorAll('.pv-nav'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.pv-panel'));
  var badge = document.getElementById('pv-badge');
  var strips = Array.prototype.slice.call(document.querySelectorAll('.pv-strip'));
  var current = 'kr';

  function navOf(m) {
    return navs.filter(function (n) { return n.dataset.market === m; })[0];
  }
  function tabsOf(m) {
    var n = navOf(m);
    return n ? Array.prototype.slice.call(n.querySelectorAll('.pv-tab')) : [];
  }

  function show(key) {
    tabsOf(current).forEach(function (t) {
      t.setAttribute('aria-selected', String(t.dataset.key === key));
    });
    panels.forEach(function (p) {
      if (p.dataset.key === key) { p.removeAttribute('hidden'); }
      else { p.setAttribute('hidden', ''); }
    });
    var h = current + '/' + key.replace(current + ':', '');
    if (location.hash.slice(1) !== h) { history.replaceState(null, '', '#' + h); }
  }

  function setMarket(m, key) {
    current = m;
    markets.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.market === m));
    });
    navs.forEach(function (n) {
      if (n.dataset.market === m) { n.removeAttribute('hidden'); }
      else { n.setAttribute('hidden', ''); }
    });
    if (badge) {
      var btn = markets.filter(function (b) { return b.dataset.market === m; })[0];
      badge.textContent = btn ? btn.textContent : '';
    }
    strips.forEach(function (s) {
      if (s.dataset.market === m) { s.removeAttribute('hidden'); }
      else { s.setAttribute('hidden', ''); }
    });
    var tabs = tabsOf(m);
    // 주소의 섹션은 'holdings' 일 수도, 'kr:holdings' 일 수도 있습니다
    var want = '';
    tabs.forEach(function (t) {
      if (t.dataset.key === key || t.dataset.key === m + ':' + key) { want = t.dataset.key; }
    });
    show(want || (tabs[0] ? tabs[0].dataset.key : ''));
  }
  var notesBtn = document.getElementById('pv-notes');
  if (notesBtn) {
    notesBtn.addEventListener('click', function () {
      var on = document.body.classList.toggle('pv-notes');
      notesBtn.setAttribute('aria-pressed', String(on));
      notesBtn.textContent = on ? '설명 숨기기' : '설명 보기';
    });
  }

  markets.forEach(function (b) {
    b.addEventListener('click', function () { setMarket(b.dataset.market); });
  });
  navs.forEach(function (n) {
    Array.prototype.slice.call(n.querySelectorAll('.pv-tab')).forEach(function (t) {
      t.addEventListener('click', function () { show(t.dataset.key); });
    });
  });

  var parts = location.hash.slice(1).split('/');
  var startM = (parts[0] === 'us' || parts[0] === 'kr') ? parts[0] : 'kr';
  setMarket(startM, parts[1] || '');
})();
"""


def _section_panel(section, data, fx) -> str:
    parts = [
        ui.render_section_head(section.title, section.subtitle, len(section.instruments)),
        f'<div class="dash-grid" style="--cols:{section.columns}">',
    ]
    for inst in section.instruments:
        quote = pick_quote(inst, data)
        premium = None
        if inst.local_peer and inst.common_shares_per_unit is not None and quote is not None:
            local = data.get("naver", {}).get(inst.local_peer)
            premium = compute_premium(inst, quote, local, fx)
        parts.append(ui.render_card(inst, quote, fx, premium))
    parts.append("</div>")
    parts.append(ui.render_footnote(section.footnote))
    return "".join(parts)


_LAST_FOUND: list = []    # 내 종목 표가 신호 개수를 쓰려고 받아 둡니다


def _signals_panel(data, use_demo: bool, market: str = "") -> str:
    """변화 감지 탭. 정적 프리뷰에서는 프롬프트를 <details> 로 접어 넣습니다."""
    import os

    import analysis_store as astore
    import signals as sig_mod
    from compute import pick_quote

    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config.ANALYSIS_DIR
    )
    instruments = list(config.SECTION_WATCHLIST.instruments)
    if market:
        # 앱과 같이 고른 시장의 종목만 — 전엔 한국 화면에 Apple 이 떴습니다
        instruments = config.filter_instruments(instruments, market)
    docs = astore.load_all(base, [i.analysis_key for i in instruments if i.analysis_key])

    quotes = {}
    for inst in instruments:
        q = pick_quote(inst, data)
        if q is not None:
            quotes[inst.symbol] = q

    if use_demo:
        filings = {**demo_mod.demo_filings(), **demo_mod.demo_dart_disclosures()}
        trends = demo_mod.demo_inventory_trends()
    else:
        from sources import edgar
        filings, _errs = edgar.fetch_for_tickers(
            config.edgar_tickers(), config.EDGAR_USER_AGENT,
            cik_overrides=config.EDGAR_CIK_OVERRIDES,
            limit=config.EDGAR_FILING_LIMIT,
        )
        trends = {}

    th = sig_mod.Thresholds(
        move_pct=config.SIGNAL_MOVE_PCT,
        drawdown_pct=config.SIGNAL_DRAWDOWN_PCT,
        extreme_pct=config.SIGNAL_EXTREME_PCT,
        earnings_days=config.SIGNAL_EARNINGS_DAYS,
        stale_days=config.SIGNAL_STALE_DAYS,
    )
    found = sig_mod.detect(instruments, quotes, docs, filings,
                           thresholds=th, trends=trends)
    _LAST_FOUND[:] = found

    targets = sig_mod.news_targets(found, limit=config.NEWS_MAX_TICKERS)
    headlines = (demo_mod.demo_news([t[0] for t in targets]) if use_demo else {})

    import html as _h

    urgent, fyi = sig_mod.split_by_urgency(found)

    parts = [
        ui.render_section_head(
            "변화 감지",
            "새 공시 · 실적 임박 · 분석 노후화 · 비정상 등락 · 52주 위치",
            len(instruments),
        ),
        ui.render_signal_summary(sig_mod.summarize(found), len(found)),
    ]

    def card(s) -> str:
        out = ui.render_signal_card(s, headlines.get(s.inst.symbol))
        if s.prompt:
            out += ('<details class="pv-prompt"><summary>Claude 에 물어볼 질문</summary>'
                    f'<pre>{_h.escape(s.prompt)}</pre></details>')
        return out

    parts.extend(card(s) for s in urgent)

    if fyi:
        parts.append(
            f'<details class="pv-fyi"{"" if urgent else " open"}>'
            f'<summary>참고 {len(fyi)}건</summary>'
            + "".join(card(s) for s in fyi)
            + "</details>"
        )
    parts.append(ui.render_footnote(
        "공시는 SEC EDGAR 공개 API(키 불필요)에서 받아옵니다. 한국 종목은 EDGAR 에 없어 "
        "공시 감지가 되지 않습니다 — DART 오픈API 는 무료 키 발급이 필요합니다. "
        "헤드라인은 제목·링크만 가져오며 공시·급등락이 감지된 종목에만 붙습니다."
    ))
    return "".join(parts)


def _prelim_block(use_demo: bool) -> str:
    """잠정실적 레이더 — 데모 공시에서 골라냅니다."""
    import cycle as cyc

    # 변수명을 disc 로 두면 모듈 별칭 disc(discover) 를 가립니다.
    by_code = demo_mod.demo_dart_disclosures() if use_demo else {}
    found = []
    for rows in by_code.values():
        found.extend(cyc.preliminary_radar(rows))
    # 미국 — MU 의 8-K Item 2.02 를 같은 목록에.
    # 변수명을 edgar 로 두면 모듈 별칭 sources.edgar 를 가립니다.
    by_ticker = demo_mod.demo_filings() if use_demo else {}
    for tkr in config.CYCLE_US_TICKERS:
        found.extend(cyc.prelim_from_filings(
            by_ticker.get(tkr, []), tkr, name={"MU": "Micron"}.get(tkr, tkr)))
    found.sort(key=lambda f: f.rcept_dt, reverse=True)
    return "".join([
        ui.render_section_head(
            "잠정실적 레이더",
            "영업(잠정)실적 + 8-K Item 2.02 — 정식 보고서보다 먼저 나오는 숫자",
            len(found)),
        ui.render_prelim_radar(found[:8]),
        ui.render_footnote(
            "<b>공시 안의 숫자를 읽어오지 않습니다.</b> 공정공시 본문 표는 "
            "회사·분기마다 형식이 달라서, 파싱해 조용히 틀린 숫자를 "
            "보여주는 것보다 링크로 열어보는 쪽이 안전합니다. 미국(8-K)은 "
            "SEC 가 항목 번호를 주므로 제목을 대조하지 않고 <b>Item 2.02</b> 로 "
            "정확히 걸러냅니다."),
        ui.render_kr_exports(
            demo_mod.demo_kr_exports() if use_demo else None),
        ui.render_footnote(
            "한국 반도체 수출은 <b>월초에 전월치</b>가 나옵니다 — 분기 실적을 "
            "기다리지 않고 메모리 수요를 읽을 수 있는 유일한 월간 지표입니다. "
            "<b>다만 이 긁어오기 경로는 검증되지 않았습니다</b> — 화면 위쪽 "
            "진단으로 실제로 되는지 먼저 확인하십시오."),
    ])


def _cycle_panel(use_demo: bool) -> str:
    """재고 지표 탭."""
    import cycle as cycle_mod

    instruments = config.cycle_instruments()
    us_tickers = list(config.CYCLE_US_TICKERS)

    # 미국 경로 — EDGAR XBRL, 인증키 불필요
    if use_demo:
        us_trends = demo_mod.demo_us_inventory_trends()
        us_errors: dict[str, str] = {}
    else:
        from sources import edgar as edgar_mod, edgar_xbrl as xbrl_mod
        us_trends, us_errors = {}, {}
        try:
            ticker_map = edgar_mod.fetch_ticker_map(config.EDGAR_USER_AGENT)
        except Exception as exc:  # noqa: BLE001
            ticker_map, us_errors = {}, {t: str(exc) for t in us_tickers}
        for ticker in us_tickers:
            cik = (config.EDGAR_CIK_OVERRIDES.get(ticker)
                   or ticker_map.get(ticker.upper()))
            if cik is None:
                us_errors.setdefault(ticker, "CIK 를 찾지 못했습니다.")
                continue
            collected, warns = {}, []
            for key, tags in cycle_mod.XBRL_TAGS.items():
                try:
                    _tag, facts = xbrl_mod.fetch_first_available(
                        cik, tags, config.EDGAR_USER_AGENT)
                    collected[key] = facts
                except xbrl_mod.XbrlError as exc:
                    collected[key] = []
                    warns.append(f"{key}: {exc}")
            if collected.get("inventory") and collected.get("cost_of_sales"):
                us_trends[ticker] = cycle_mod.build_trend_from_xbrl(
                    ticker, ticker, collected["inventory"],
                    collected["cost_of_sales"], collected.get("revenue") or [],
                    quarters=config.CYCLE_XBRL_QUARTERS, errors=warns,
                )
            else:
                us_errors[ticker] = "; ".join(warns) or "재고·매출원가를 찾지 못했습니다."

    # 한국 경로 — DART, 인증키 필요
    if use_demo:
        trends = demo_mod.demo_inventory_trends()
        errors: dict[str, str] = {}
    else:
        from sources import dart as dart_mod
        trends, errors = {}, {}
        try:
            corp_map = dart_mod.fetch_corp_codes()
        except dart_mod.DartError as exc:
            corp_map, errors = {}, {"DART": str(exc)}
        for inst in instruments:
            corp = dart_mod.resolve_corp_code(
                inst.symbol, corp_map, config.DART_CORP_CODE_OVERRIDES)
            if not corp:
                continue
            collected, warns = [], []
            year, quarter = dart_mod.latest_available_quarter()
            for _ in range(config.CYCLE_QUARTERS_BACK):
                try:
                    accts = dart_mod.fetch_financials(
                        corp, year, quarter, fs_div=config.CYCLE_FS_DIV)
                    if accts:
                        collected.append((year, quarter, config.CYCLE_FS_DIV, accts))
                except dart_mod.DartError as exc:
                    if "조회된 데이터가 없습니다" not in str(exc):
                        warns.append(str(exc))
                year, quarter = dart_mod.previous_quarter(year, quarter)
            if collected:
                trends[inst.symbol] = cycle_mod.build_trend(
                    inst.name, inst.symbol, collected, warns)

    parts = [
        # 잠정실적이 정식 보고서보다 먼저 나오므로 재고 지표 위에 둡니다
        _prelim_block(use_demo),
        ui.render_section_head(
            "재고 지표 (레이어 2)",
            "DART 분기보고서 + EDGAR XBRL 에서 DIO · 재고-매출 갭을 직접 계산",
            len(instruments) + len(us_tickers),
        ),
        ui.render_footnote(
            "DIO 절대값은 의미가 없습니다 — <b>자사 역사적 밴드 내 위치</b>가 신호입니다. "
            "그래서 수집한 분기들의 최소·중간값·최대를 기준선으로 함께 표시합니다. "
            "한국 2사는 분기보고서가 분기말 후 45일에 공시되므로 기준 분기가 헤드라인 "
            "실적보다 한 분기 뒤처집니다. 마이크론은 10-Q 가 더 빨라 더 최신입니다 — "
            "<b>3사의 기준 분기가 다를 수 있으니 비교할 때 각 패널의 '기준' 표기를 "
            "확인하십시오.</b>"
        ),
    ]

    # 미국(키 불필요) 먼저 — 키가 없어도 뭔가는 보여야 합니다
    for ticker in us_tickers:
        trend = us_trends.get(ticker)
        if trend is None:
            parts.append(ui.render_analysis_missing(
                f"{ticker} 재고 지표",
                us_errors.get(ticker, "수집되지 않았습니다."),
                ticker, "inventory",
            ))
            continue
        parts.append(ui.render_inventory_panel(trend, cycle_mod.checklist(trend)))

    for inst in instruments:
        trend = trends.get(inst.symbol)
        if trend is None:
            parts.append(ui.render_analysis_missing(
                f"{inst.name} 재고 지표",
                errors.get(inst.symbol, "DART 인증키가 필요합니다 (환경변수 DART_API_KEY)."),
                inst.symbol, "inventory",
            ))
            continue
        parts.append(ui.render_inventory_panel(trend, cycle_mod.checklist(trend)))

    parts.append(ui.render_footnote(
        "계정은 XBRL 표준계정ID(ifrs-full_Inventories 등)를 1순위로 맞추고, 표준ID 가 "
        "없을 때만 계정명으로 폴백합니다. 기업마다 계정명이 달라(매출액 / 수익(매출액) / "
        "영업수익) 계정명만으로 필터링하면 절반이 빠집니다. 재고 구성(원재료·재공품·완제품)은 "
        "주석 항목이라 전체 재무제표 API 에 없는 경우가 많아 '판정 불가' 로 둡니다."
    ))
    return "".join(parts)


def _screen_body(triples, criteria, min_pass: int, caps=None) -> str:
    """미국·국내 공통 — 통과율 · 사분면 지도 · 종목 카드.

    caps 를 주면 가격 조건 블록까지 그립니다. 기본값을 None 으로 둔 것은
    기존 호출 3곳을 한꺼번에 고치지 않아도 되게 하려는 것입니다.
    """
    import value as vl
    import verdict as vd

    caps = caps or {}
    # 데모에서는 10년물을 4.2% 로 가정합니다. 실제 앱은 FRED DGS10 을 씁니다.
    th = vl.Thresholds(risk_free_pct=4.20)

    screens = [t[0] for t in triples]
    verdicts = [t[2] for t in triples]
    parts = [
        ui.render_footnote(
            "<b>기준별 통과율</b> — 0% 나 100% 에 가까운 기준은 구분을 못 하고 "
            "있다는 뜻이니 기준선을 조정할 후보입니다: "
            + " · ".join(
                f"{c.name.replace(' 꾸준히', '')} "
                f"{sum(1 for s in screens if s.checks[i].passed)}/{len(screens)}"
                for i, c in enumerate(criteria))),
        ui.render_screen_table(screens, criteria),
        ui.render_section_head(
            "사분면 지도", "사업의 질(가로) × 가격의 기대(세로)", len(verdicts)),
        ui.render_quadrant_map(verdicts),
        ui.render_footnote(
            "①~④ 는 <b>좋고 나쁨의 순서가 아닙니다.</b> ① 이 항상 좋은 것도 "
            "아닙니다 — 시장이 알고 있는 위험을 가격에 반영했을 수 있습니다. "
            "네 칸은 <b>다음에 무엇을 확인해야 하는가</b>가 다를 뿐입니다."),
    ]
    shortlist = [t for t in triples if t[0].passed_count >= min_pass]
    parts.append(ui.render_section_head(
        ("전체 종목" if min_pass <= 0 else f"{min_pass}개 이상 통과"),
        "각 카드의 질문을 Claude 에 붙여넣으면 정독이 시작됩니다",
        len(shortlist)))
    # 종목마다 접습니다 — **실제 앱이 st.expander 로 그리는 모양**과 맞춰야
    # 합니다. 전에는 미리보기만 평평하게 펼쳐 놔서, 앱은 접이식인데
    # 미리보기를 보고 '너무 길다' 고 판단하게 됐습니다.
    import html as _html

    for idx, (screen, result, verdict_obj) in enumerate(shortlist):
        price = vl.build(screen, result, caps.get(screen.ticker), th)
        label = _html.escape(_valuation_label(screen, result, price))
        inner = "".join([
            ui.render_screen(screen, show_source=True),
            ui.render_dcf_cells(result),
            ui.render_price_block(price, show_source=True,
                                  metrics_meta=vl.METRICS),
            ui.render_verdict(verdict_obj,
                              prompt=vd.prompt_for(verdict_obj, screen)),
        ])
        # 첫 종목만 펼쳐 둡니다 — 전부 접혀 있으면 빈 화면처럼 보이고,
        # 전부 펼치면 접는 의미가 없습니다.
        open_attr = " open" if idx == 0 else ""
        parts.append(
            f'<details class="pv-fold"{open_attr}>'
            f'<summary>{label}</summary>'
            f'<div class="pv-fold-body">{inner}</div>'
            "</details>"
        )
    return "".join(parts)


def _valuation_label(screen, result, price) -> str:
    """접힌 카드 제목. app._valuation_label 과 같은 형식으로 적습니다 —
    두 화면이 다르면 미리보기를 믿을 수 없게 됩니다."""
    import buffett as bf_mod

    parts = [f"질 {screen.passed_count}/{len(bf_mod.CRITERIA)}"]
    if price is not None and price.ok:
        parts.append(f"가격 {price.passed_count}/{len(price.checks)}")
    else:
        parts.append("가격 판정 불가")
    if result is not None and getattr(result, "ok", False) \
            and result.implied_growth is not None:
        parts.append(f"요구 성장률 연 {result.implied_growth * 100:.1f}%")
    name = (screen.name or "").strip()
    head = f"{screen.ticker} {name}" if name else screen.ticker
    return f"{head}  ·  " + "  ·  ".join(parts)


def _attach(screens, caps, currency: str):
    import reverse_dcf as rdcf
    import verdict as vd

    out = []
    for screen in screens:
        if not screen.ok:
            continue
        result = rdcf.run(rdcf.inputs_from_screen(
            screen, caps.get(screen.ticker), currency=currency,
            market_cap_source="데모 데이터"))
        out.append((screen, result, vd.build(screen, result)))
    return out


def _screen_kr_panel(use_demo: bool) -> str:
    """국내 발굴 — DART 기반."""
    import buffett

    parts = [
        ui.render_section_head(
            "국내주식 발굴 (버핏식 숫자 기준)",
            "DART 사업보고서 10년치 — 보고서 1회당 3년이 나옵니다",
            len(config.screen_kr_candidates())),
        ui.render_footnote(
            "<b>기준선이 미국과 다릅니다.</b> 미국 기준(ROE 15% 이상 10년 중 8년)을 "
            "한국 종목에 그대로 적용하면 거의 전부 탈락합니다 — 기업이 나빠서가 "
            "아니라 한국 상장사의 ROE 분포가 구조적으로 낮기 때문입니다. "
            "그러면 \"한국 주식은 다 안 좋다\" 는 결론이 나오는데 그건 "
            "<b>기준이 틀린 것</b>입니다. 그래서 ROE 10%·D/E 0.6·마진 ±7%p 로 "
            "낮췄습니다 — <b>버핏의 숫자가 아니라 제가 분포를 보고 정한 값</b>입니다. "
            "DART 인증키가 필요합니다 (미국 탭은 키 없이 동작)."),
    ]
    if use_demo:
        screens_map, _errors = demo_mod.demo_kr_screens()
        caps = demo_mod.demo_kr_market_caps()
    else:
        parts.append(ui.render_footnote(
            "실데이터 프리뷰는 DART 인증키가 필요합니다 — 앱에서 확인하십시오."))
        return "".join(parts)

    triples = _attach(buffett.rank(list(screens_map.values())), caps, "KRW")
    if not triples:
        parts.append(ui.render_footnote("<b>스크리닝 결과가 없습니다.</b>"))
        return "".join(parts)
    parts.append(_screen_body(triples, buffett.CRITERIA, 3, caps))
    return "".join(parts)


def _premium_panel(data, fx) -> str:
    """괴리율 · 국내 본주 — 합친 화면."""
    import compute as compute_mod

    foreign = list(config.SECTION_ADR.instruments)
    local = list(config.SECTION_LOCAL.instruments)
    rows, unpaired = compute_mod.build_premium_rows(foreign, local, data, fx)

    parts = [
        ui.render_section_head(
            "괴리율 · 국내 본주",
            "해외 상장 한국 종목과 국내 본주를 한 화면에서 — 계산 사슬 전체",
            len(rows) + len(unpaired)),
        '<div style="margin:-4px 0 10px">'
        + ui.render_live_badge("실시간", "on", "30초마다 갱신")
        + "  "
        + ui.render_live_badge("코스피", "frozen", "마감 후 · 본주가 종가로 고정")
        + "</div>",
        ui.render_footnote(
            "<b>지금 괴리율은 실제 가격차가 아닙니다.</b> 국내 장이 닫혀 본주가가 "
            "종가로 고정돼 있으므로, 이 수치는 <b>마감 이후 해외에서 벌어진 "
            "움직임</b>을 본주 기준으로 환산한 값입니다."),
    ]
    for row in rows:
        parts.append(ui.render_premium_pair(row, fx=fx))

    if unpaired:
        parts.append(ui.render_section_head(
            "짝이 없는 국내 종목", "해외 상장이 없어 괴리율을 낼 수 없습니다",
            len(unpaired)))
        cards = "".join(
            ui.render_card(inst, (data.get(inst.source) or {}).get(inst.symbol), fx)
            for inst in unpaired)
        parts.append(f'<div class="dash-grid cols-4">{cards}</div>')

    parts.append(ui.render_footnote(
        "괴리율 = (해외가격 × 환율 ÷ 환산주수) ÷ 국내 본주가 − 1. "
        "해외 종목에 프리/애프터장 가격이 있으면 <b>그것을 우선</b> 씁니다.<br>"
        "<b>괴리율이 크다는 사실만으로 차익거래 기회가 아닙니다.</b> "
        "SK하이닉스 ADR 은 본주→ADR 전환이 발행주식수의 2.5% 로 제한되어 "
        "괴리가 좁혀지기 어렵습니다. 세금·수수료·환전 비용도 반영되지 "
        "않았습니다."))
    return "".join(parts)


def _summary_panel(data, fx, use_demo: bool, market: str = "kr") -> str:
    """요약 — 시장마다 둘째 줄이 다릅니다 (미국 심리 / 한국 섹터 온도)."""
    import config as cfg
    import macro as macro_mod
    import summary as sm

    fg = vix_state = sector_rows = None
    if use_demo:
        if market == "kr":
            sector_rows = demo_mod.demo_sector_heat(cfg.KR_SECTOR_ETFS)
        else:
            fg = demo_mod.demo_feargreed()
            vix_state = demo_mod.demo_vix()
        trends = demo_mod.demo_inventory_trends()
        series, errs = demo_mod.demo_macro_series()
    else:
        trends, series, errs = {}, {}, {}
    readings = macro_mod.build_readings(cfg.macro_series(), series, errs)
    held = cfg.filter_instruments(cfg.SECTION_WATCHLIST.instruments, market)

    summary = sm.build(
        urgent=[], soon=[], holdings_total=len(held),
        fg=fg, vix_state=vix_state, trends=trends, macro_readings=readings,
        market=market, sector_rows=sector_rows)

    parts = [
        ui.render_section_head(
            "요약", "휴대폰에서 10초 — 지금 알아야 할 것만", 4),
        ui.render_summary(summary),
        ui.render_sector_bars(sector_rows) if sector_rows else "",
        _upcoming(data, use_demo, market),
        _daily_briefs(use_demo, market),
        ui.render_briefing_line(demo_mod.demo_briefing()),
    ]
    if summary.all_quiet:
        parts.append(ui.render_footnote(
            "<b>조용한 게 정상입니다.</b> 이 화면은 뉴스 피드가 아니라 "
            "<b>임계값을 건드린 것만</b> 올립니다 — 올라온 게 없으면 앱을 "
            "닫아도 됩니다."))
    parts.append(ui.render_footnote(
        "<b>시장마다 둘째 줄이 다릅니다.</b> 미국은 시장 심리(공포탐욕·VIX), "
        "한국은 섹터 온도입니다. 공포탐욕과 VIX 는 미국 지표라 한국 화면에 "
        "둘 이유가 약하고, 한국에서 매일 보는 건 '어느 업종으로 돈이 "
        "가나' 입니다."))
    return "".join(parts)


def _holdings_panel(data, fx, use_demo: bool, market: str = "kr") -> str:
    """내 종목 — 고른 시장의 종목만."""
    watchlist = config.SECTION_WATCHLIST
    shown = config.filter_instruments(watchlist.instruments, market)
    import chart_signals as cs

    signals_html = _signals_panel(data, use_demo, market)
    found = list(_LAST_FOUND)
    cands = config.chart_candidates(market)
    crow = ({r.ticker: r for r in cs.build_rows(cands, *demo_mod.demo_chart_ohlc(cands))}
            if use_demo else None)
    parts = [_portfolio_html(data, fx, use_demo, market),
             ui.render_section_head("보유 · 관심 종목", watchlist.subtitle, len(shown))]
    parts.append(ui.render_holdings_table(
        [(inst, pick_quote(inst, data),
          [s for s in found if s.inst.symbol == inst.symbol]) for inst in shown],
        chart_rows=crow))
    parts.append(signals_html)
    # 공시 분석은 앱에서 **접혀 있습니다** — 프리뷰에도 접힌 상태로 보여줍니다
    parts.append(
        '<details class="pv-fold"><summary>'
        "공시 분석 — 앱에서는 접혀 있습니다 (눌러서 펼치기)"
        "</summary>" + _analysis_panel() + "</details>"
    )
    return "".join(parts)


def _sector_heat_panel(use_demo: bool) -> str:
    """섹터 온도 — 업종 ETF 히트맵. 앱의 render_sector_heat_tab 과 같은 순서."""
    rows = (demo_mod.demo_sector_heat(config.KR_SECTOR_ETFS)
            if use_demo else [])
    return "".join([
        ui.render_section_head(
            "섹터 온도", "KODEX 업종 ETF · KODEX 200 대비 1개월 순",
            len([r for r in rows if not r.benchmark])),
        ui.render_footnote(
            "<b>왜 'KODEX 200 대비' 로 줄을 세우나.</b> 업종 하나가 5% "
            "올랐어도 시장 전체가 6% 올랐다면 그 업종은 <b>덜 오른</b> "
            "것입니다. 업종 순환(어디로 돈이 옮겨가나)을 보려면 절대 "
            "수익률이 아니라 시장 대비 수익률을 봐야 합니다.<br>"
            "업종지수를 직접 받을 공개 경로가 없어 <b>ETF 를 대용</b>으로 "
            "씁니다. 운용보수·추적오차 때문에 실제 업종지수와 조금 다를 수 "
            "있습니다."),
        ui.render_sector_heat_summary(rows),
        ui.render_sector_heat(rows),
        ui.render_footnote(
            "색 진하기는 크기입니다 — 기간마다 눈금이 다릅니다(1일 ±3% · "
            "1주 ±6% · 1개월 ±12% · 3개월 ±25% 에서 가장 진함).<br>"
            "52주 위치는 지난 1년 저가(왼쪽)~고가(오른쪽) 사이 어디인지입니다. "
            "3개월 추이의 점선은 시작점입니다.<br>"
            "<b>데모에서는 '은행' 줄에 일부러 틀린 이름을 넣었습니다</b> — "
            "코드가 틀렸을 때 화면이 어떻게 알려주는지 보이려고."),
    ])


def _kr_flows_panel(use_demo: bool) -> str:
    """한국 — 섹터 뉴스 · 주요 공시 · 경제지표."""
    import inflation
    import liquidity  # noqa: F401 - 데모가 반환하는 타입

    parts = [
        ui.render_section_head(
            "한국 — 섹터별 뉴스", "업종 바람이 먼저 불고 종목이 따라갑니다",
            len(config.KR_SECTORS)),
        ui.render_footnote(
            "종목 뉴스와 다릅니다. 종목 뉴스는 '내 종목에 무슨 일이' 고, "
            "이건 '내 종목이 속한 업종에 무슨 바람이' 입니다. "
            "구글 뉴스를 한국어로 부르며 <b>제목과 링크만</b> 가져옵니다."),
    ]
    sn, se = (demo_mod.demo_sector_news(config.KR_SECTORS)
              if use_demo else ({}, {}))
    parts.append(ui.render_sector_news(config.KR_SECTORS, sn, se))

    import sources.dart as _dart  # noqa: PLC0415
    scan = demo_mod.demo_filing_scan() if use_demo else _dart.FilingScan([])
    filings = scan.filings
    parts.append(ui.render_section_head(
        "한국 — 주요 공시", "11-06 이후 · 코스피·코스닥 · 세부 유형별",
        len(filings)))
    parts.append(ui.render_filing_counts(_dart.count_filings(filings)))
    parts.append(ui.render_notice(
        "<i>(앱에서는 여기에 분류 칩 · 세부 유형 칩 · 시장 · '내 종목만' "
        f"필터가 붙습니다)</i> <b>{len(filings)}건</b> / 읽은 공시 "
        f"{scan.scanned:,}건 · <b>내 종목 3건</b>"))
    parts.append(ui.render_market_filings(
        filings, held={"005930", "000660", "005380"}, scan=scan))
    parts.append("<details class='dash-pv-details'><summary>유형별로 무엇을 "
                 "보면 되나</summary>"
                 + ui.render_filing_guide(_dart.DISCLOSURE_TYPES,
                                          _dart.DISCLOSURE_GROUPS)
                 + "</details>")

    kr_rows = (demo_mod.demo_kr_macro(config.KR_MACRO_SERIES)
               if use_demo else [])
    parts.append(ui.render_section_head(
        "한국 — 경제지표", "FRED 경유 · 전년동월비 병기", len(kr_rows)))
    parts.append(ui.render_simple_rows(kr_rows))
    parts.append(ui.render_footnote(
        "<b>한국 계열 ID 는 전부 미검증입니다.</b> FRED 의 한국 통계는 "
        "OECD 경유라 ID 체계가 미국 계열과 다르고 중단된 것도 많습니다. "
        "'—' 로 나오면 그 계열이 없는 것입니다."))
    return "".join(parts)


def _us_flows_panel(use_demo: bool) -> str:
    """미국 — 물가 속도 · 글로벌 유동성."""
    import inflation
    import liquidity  # noqa: F401 - 데모가 반환하는 타입

    parts: list[str] = []
    readings = (demo_mod.demo_inflation(config.INFLATION_SERIES)
                if use_demo else [])
    parts.append(ui.render_section_head(
        "미국 — 물가 속도", "지수가 아니라 속도로",
        len([r for r in readings if r.ok])))
    parts.append(ui.render_footnote(
        "<b>전년동월비 하나만 보면 늦습니다</b> — 12개월 전 숫자를 아직 "
        "끌고 다니기 때문입니다. <b>3개월 연율</b>은 최근 3개월 변화를 "
        "1년치로 환산한 것이라 가장 빠릅니다. 3개월 연율이 전년동월비보다 "
        "높으면 물가가 다시 붙는 중이고, 낮으면 식는 중입니다 — "
        "이건 해석이 아니라 산술입니다.<br>"
        "비계절조정 계열(PPI 전체상품)은 전월비·연율을 내지 않습니다."))
    parts.append(ui.render_inflation_table(readings))
    if readings:
        parts.append(ui.render_footnote(inflation.summary_line(readings)))

    parts.append(ui.render_section_head(
        "글로벌 — 유동성", "연준 순유동성 + 주요국 중앙은행"))
    if use_demo:
        nl, extra = demo_mod.demo_liquidity()
        parts.append(ui.render_liquidity(nl, extra))
    else:
        parts.append(ui.render_footnote("실데이터 프리뷰는 앱에서 확인하십시오."))
    return "".join(parts)


def _discover_panel(use_demo: bool, market: str = "us") -> str:
    """종목 발굴 — 미국은 품질 기준만, 국내는 변동성·밸류 스크리너.

    앱과 같게 **고른 시장 하나만** 보여줍니다.
    """
    import buffett
    import kr_screen

    parts = [
        ui.render_section_head(
            "종목 발굴 · 미국",
            f"버핏식 품질 기준 {len(buffett.CRITERIA)}개 — 읽을 목록을 줄입니다"),
        ui.render_footnote(
            "<b>52주 위치 축을 뺐습니다.</b> 신고가는 '최근 많이 오른 주식' "
            "이지 '좋은 주식' 이 아닙니다 — 품질 기준을 통과한 목록을 주가 "
            "흐름으로 한 번 더 자를 근거가 장기 보유 판단에는 없습니다. "
            "가격은 <b>밸류에이션 탭</b>에서 공시 숫자(FCF·순부채)와 "
            "견줍니다.<br>앱에서는 <b>품질 기준선 슬라이더</b>로 조절합니다."),
    ]
    screens_map, _errs = (demo_mod.demo_screens() if use_demo else ({}, {}))
    screens = buffett.rank(list(screens_map.values()))
    threshold = round(len(buffett.CRITERIA) * 2 / 3)
    passed = [s for s in screens if s.passed_count >= threshold]
    parts.append(ui.render_footnote(
        f"<b>후보 {len(screens)}종목</b> 중 <b>{len(passed)}종목</b>이 "
        f"{threshold}개 이상 통과"))
    parts.append(ui.render_section_head(
        "통과 종목", "통과 수 많은 순", len(passed)))
    for screen in passed[:6]:
        parts.append(
            '<details class="pv-fold"><summary>'
            f"{screen.ticker} · {screen.passed_count}"
            f"/{len(buffett.CRITERIA)} 통과</summary>"
            f'<div class="pv-fold-body">{ui.render_screen(screen)}</div>'
            "</details>")

    if market != "kr":
        return "".join(parts)
    parts = []

    # ── 국내 ────────────────────────────────────────────────────────────
    parts.append(ui.render_section_head(
        "종목 발굴 · 한국",
        "변동성 × 신고가 × 전통 밸류 — 국내는 재무만으로 안 걸러집니다"))
    parts.append(ui.render_footnote(
        f"<b>왜 미국과 기준이 다른가.</b> 국내 후보 "
        f"{len(config.screen_kr_candidates())}종목(코스피 + 코스닥)은 재무 "
        "기준만으로는 거의 걸러지지 않습니다. 대신 주가 변동성이 미국보다 "
        "큽니다 — 52주 신고가를 단독으로 쓰면 급등 후 되돌림 구간이 대거 "
        "섞입니다. 그래서 <b>변동성이 잦아든 상태</b>와 <b>거래대금 "
        "바닥</b>을 같이 봅니다.<br>"
        "앱에서는 아래 세 묶음을 <b>버튼으로 전환</b>하고, 종목마다 카드를 "
        "펼쳐 기업 개요·최근 뉴스·3대 분석 버튼을 봅니다."))

    cands = list(config.screen_kr_candidates())
    if use_demo:
        profiles, vol_errors = demo_mod.demo_kr_vol_profiles(cands)
        value_rows = demo_mod.demo_kr_value_rows(cands)
    else:
        profiles, vol_errors, value_rows = [], {}, []
    hits = {
        "contraction": kr_screen.contraction_hits(profiles),
        "near_high": kr_screen.near_high_hits(profiles),
        "value_trad": kr_screen.value_hits(value_rows),
        "rs": kr_screen.relative_strength_hits(profiles),
        "rebound": kr_screen.rebound_hits(profiles),
        "surge": kr_screen.turnover_surge_hits(profiles),
    }
    companies = demo_mod.demo_kr_companies(
        tuple(c for c, _n in cands)) if use_demo else {}
    news_demo = demo_mod.demo_news([c for c, _n in cands]) if use_demo else {}

    n_cands = len(cands)
    for key, title, rule, caveat in kr_screen.KR_SCREENS:
        picked = hits.get(key, [])
        parts.append(ui.render_screener_head(title, rule, len(picked), caveat))
        if key in kr_screen.VOL_SCREENS:
            steps = kr_screen.funnel(key, n_cands, profiles)
            parts.append(ui.render_funnel(steps, vol_errors, title="단계별로 남은 종목"))
        else:
            parts.append(ui.render_funnel(
                kr_screen.value_funnel(value_rows),
                {r.ticker: r.error for r in value_rows if r.error},
                title="단계별로 남은 종목"))
        parts.append(ui.render_hit_table(picked))
        if not picked:
            parts.append(ui.render_footnote(
                "<b>이 기준을 통과한 종목이 없습니다.</b> 기준을 느슨하게 "
                "하지 않고 그대로 둡니다."))
            continue
        for hit in picked[:3]:
            inner = (
                ui.render_hit_metrics(hit)
                + ui.render_hit_reasons(hit)
                + ui.render_section_head("기업 개요", "DART 기업개황")
                + ui.render_company_overview(companies.get(hit.ticker),
                                             search_name=hit.name)
                + ui.render_section_head("최근 뉴스", "구글 뉴스 · 제목과 링크만",
                                         len(news_demo.get(hit.ticker) or []))
                + (ui.render_news_block(news_demo.get(hit.ticker) or [], limit=5)
                   or ui.render_footnote("최근 헤드라인을 찾지 못했습니다."))
                + ui.render_section_head("3대 분석", "어디서 돌릴지 고르십시오", 3)
                + ui.render_footnote(
                    "로컬에서 <code>streamlit run app.py</code> 로 띄우면 "
                    "여기에 <b>바로 실행</b> 버튼이 붙습니다. 클라우드에는 "
                    "<code>claude</code> 실행 파일이 없어 아래 링크로 "
                    "대신합니다.")
                + ui.render_skill_links(hit.ticker, hit.name)
            )
            parts.append(
                '<details class="pv-fold"><summary>'
                f"{hit.name} · {hit.ticker}</summary>"
                f'<div class="pv-fold-body">{inner}</div></details>')
    if vol_errors:
        parts.append(ui.render_footnote(
            f"<b>일봉을 못 받은 종목 {len(vol_errors)}건</b> — 신규 상장이나 "
            "거래정지 구간이 있으면 변동성을 신뢰할 수 없어 뺍니다."))
    return "".join(parts)


def _calendar_data(data, use_demo: bool, days: int = 45):
    import datetime as _dt
    from zoneinfo import ZoneInfo

    import calendar_events as ce

    today = _dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    payload = demo_mod.demo_fred_release_dates(today) if use_demo else None
    watch = [i for i in config.SECTION_WATCHLIST.instruments if i.source == "yahoo"]
    events, warns = ce.build(today, days, fred_payload=payload,
                             quotes=(data or {}).get("yahoo", {}), instruments=watch)
    return events, warns, today


def _upcoming(data, use_demo: bool, market: str) -> str:
    events, _w, today = _calendar_data(data, use_demo, 7)
    top = [e for e in events if e.importance >= 2
           or (e.market == market and (e.day - today).days <= 2)][:6]
    if not top:
        return ""
    return (ui.render_section_head("다가오는 일정", "앞으로 7일 — 전체는 '주요 일정'", len(top))
            + ui.render_calendar(top, today, market=market, compact=True))


def _demo_dividend_views(data, use_demo: bool, today) -> list:
    import dividends

    held = {"MSFT", "AAPL", "MU", "QQQ", "005930.KS", "000660.KS"}
    targets = []
    for inst in config.SECTION_WATCHLIST.instruments:
        if inst.source == "yahoo":
            targets.append((inst.symbol, inst.name, "us"))
        elif inst.source == "naver":
            targets.append((inst.fundamental_symbol or inst.symbol + ".KS", inst.name, "kr"))
    raw = demo_mod.demo_dividends([t[0] for t in targets]) if use_demo else {}
    prices = {"MSFT": 420, "AAPL": 230, "MU": 110, "O": 58, "QQQ": 500, "SCHD": 28,
              "UNH": 520, "005930.KS": 60000, "000660.KS": 190000}
    return [dividends.analyze(sym, name, mkt, (raw.get(sym) or {}).get("history", []),
                              today, announced_ex=(raw.get(sym) or {}).get("ex_date", ""),
                              price=prices.get(sym), held=sym in held)
            for sym, name, mkt in targets]


def _calendar_panel(data, use_demo: bool, market: str) -> str:
    import datetime as _dt
    import dividends

    events, warns, today = _calendar_data(data, use_demo)
    views = _demo_dividend_views(data, use_demo, today)
    events = sorted(events + dividends.calendar_events(
        views, today, today + _dt.timedelta(days=45)),
        key=lambda e: (e.date, -e.importance, e.market))
    return (ui.render_section_head("주요 일정", "앞으로 45일 · 고르지 않은 시장은 흐리게",
                                   len(events))
            + ui.render_calendar(events, today, market=market)
            + "".join(ui.render_notice(w) for w in warns)
            + ui.render_footnote(
                "<b>출처:</b> FOMC 연준 공식 일정 · 금통위 한국은행 의결 일정 · 휴장일 "
                "거래소 공지 · 미국 지표 발표일 FRED (프리뷰는 데모 날짜) · 만기일은 "
                "규칙으로 계산 · 배당락일은 야후 발표 또는 추정")
            + ui.render_section_head("배당 일정",
                                     "관심·보유 종목 — 다음 배당락일 · 최근 12개월 배당",
                                     sum(1 for v in views if v.count))
            + ui.render_dividend_table(views, today, market=market))


def _supply_panel(use_demo: bool) -> str:
    import flows

    names = dict(config.chart_candidates("kr"))
    for sec in (config.SECTION_WATCHLIST, config.SECTION_LOCAL):
        for inst in sec.instruments:
            if inst.source == "naver":
                names[inst.symbol] = inst.name
    codes = ["005930", "000660", "005935", "005380", "035420", "068270", "051910"]
    raw = demo_mod.demo_kr_flows(codes) if use_demo else {}
    sums = [flows.summarize(c, (raw.get(c) or ([], "", ""))[0], name=names.get(c, c),
                            source=(raw.get(c) or ([], "", ""))[1],
                            error=(raw.get(c) or ([], "", "데이터 없음"))[2],
                            held=c in ("005930", "000660"))
            for c in codes]
    sums.sort(key=flows.rank_key)
    return (ui.render_section_head("수급 — 외국인 · 기관",
                                   "2026-11-11 까지 · 5일 · 20일 누적, 금액은 근사",
                                   sum(1 for x in sums if not x.error))
            + "<div class='pv-chips'><span class='pv-chip'>차트 조건 후보 전체 "
              "(약 50종목)</span><em>앱에서는 켜면 후보 전체를 봅니다</em></div>"
            + ui.render_flow_table(sums)
            + ui.render_footnote(
                "<b>숫자만 셉니다.</b> 순매수는 원인이기도 하고 결과이기도 해서 방향을 "
                "말해주지 않습니다. 금액은 순매수 주식 수 × 그날 종가의 합(근사)."))


def _earnings_panel(use_demo: bool, market: str) -> str:
    import datetime as _dt
    import earnings

    today = _dt.date(2026, 11, 11)
    if market == "us":
        syms = [(i.symbol, i.name) for i in config.SECTION_WATCHLIST.instruments
                if i.source == "yahoo"]
        raw = demo_mod.demo_us_earnings([s for s, _n in syms]) if use_demo else {}
        views = [earnings.us_view(s, n, (raw.get(s) or {}).get("rows"), today,
                                  error=(raw.get(s) or {}).get("error", ""),
                                  held=s in ("MSFT", "AAPL", "MU"))
                 for s, n in syms]
        return (ui.render_section_head("실적 서프라이즈 · 미국",
                                       "EPS 추정치 vs 발표치 — 최근 4분기",
                                       sum(1 for v in views if v.reported))
                + ui.render_us_earnings(views, today))
    codes = [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005935", "삼성전자우"),
             ("005380", "현대차")]
    raw = demo_mod.demo_kr_quarters([c for c, _n in codes]) if use_demo else {}
    views = [earnings.kr_view(c, n, (raw.get(c) or ([], ""))[0], today=today,
                              held=c in ("005930", "000660"))
             for c, n in codes]
    demo_mod.demo_fill_kr_surprise(views)
    filings = {f.stock_code: f for f in demo_mod.demo_market_filings() if f.kind == "실적"}
    for v in views:
        v.filing = filings.get(v.code)
    return (ui.render_section_head("실적 서프라이즈 · 한국",
                                   "최근 분기 실적 · 전년 동기 대비 · 다음 분기 컨센서스",
                                   sum(1 for v in views if v.latest))
            + ui.render_kr_earnings(views))


def _portfolio_html(data, fx, use_demo: bool, market: str) -> str:
    import portfolio as pf

    positions, bad, source = pf.load(use_demo)
    if not positions:
        return ui.render_portfolio_setup()
    by_sym = {i.symbol: i for i in (*config.SECTION_WATCHLIST.instruments,
                                    *config.SECTION_LOCAL.instruments)}
    names = {p.symbol: by_sym[p.symbol].name for p in positions if p.symbol in by_sym}
    quote_of = (lambda p: pick_quote(by_sym[p.symbol], data) if p.symbol in by_sym else None)
    total = pf.valuate(positions, quote_of, fx.usdkrw, names)
    mine = [p for p in positions if p.market == market]
    summ = pf.valuate(mine, quote_of, fx.usdkrw, names)
    return (ui.render_section_head("보유 평가", "수량·평균단가 기준 · 원화 환산", len(mine))
            + ui.render_portfolio(summ, source=source, bad=bad, total=total))


def _daily_briefs(use_demo: bool, market: str) -> str:
    """전일 장 브리핑 — 앱의 _render_daily_briefs 와 같은 순서."""
    import datetime as _dt
    from zoneinfo import ZoneInfo

    import daily_brief as dbm

    if not use_demo:
        return ""
    now = _dt.datetime.now(ZoneInfo("Asia/Seoul"))
    heads = demo_mod.demo_sector_news(
        tuple(config.DAILY_BRIEF[m]["news"] for m in config.DAILY_BRIEF)
        + (("_", "_", "_"),))[0]
    reports = demo_mod.demo_research()[1]
    order = [market] + [m for m in config.DAILY_BRIEF if m != market]
    parts = [ui.render_section_head(
        "전일 장 브리핑", "마지막으로 마감한 거래일 — 숫자만, 해석 없이", len(order))]
    for m in order:
        spec = config.daily_brief_spec(m)
        today = now.astimezone(ZoneInfo(spec["tz"])).date().isoformat()
        brief = dbm.build(m, spec, demo_mod.demo_daily_bars(m, today)[0], now)
        parts.append(ui.render_daily_brief(
            brief, heads.get(config.DAILY_BRIEF[m]["news"][0]) or (),
            reports if m == "kr" else ()))
    parts.append(ui.render_footnote(
        "<b>'왜' 는 적지 않습니다.</b> 숫자만으로는 이유를 알 수 없어서, "
        "움직임만 적고 이유는 마감 기사와 증권사 시황 리포트 링크로 넘깁니다."))
    return "".join(parts)


def _semi_research_panel(use_demo: bool) -> str:
    """반도체 리포트 — 앱의 render_semi_research_tab 과 같은 순서 (세 묶음을 이어서)."""
    import semi_research as sr  # noqa: PLC0415

    if not use_demo:
        return ui.render_notice("프리뷰의 반도체 리포트는 데모 값으로만 그립니다.")
    data = demo_mod.demo_semi_research()
    names = dict(sr.STOCKS)
    total = len(data["industry"]) + sum(len(v) for v in data["stocks"].values())
    parts = [
        ui.render_section_head("반도체 리포트",
                               "증권사 산업분석(반도체) · 삼성전자 · SK하이닉스", total),
        ui.render_footnote(
            "<b>요약은 두 가지입니다.</b> 맨 위 상자는 코드가 센 <b>묶음 요약</b>"
            "이고, 카드의 글은 리포트 <b>본문 앞부분</b>입니다. 전문은 싣지 않고 "
            "원문·PDF 로 보냅니다."),
    ]
    groups = [("반도체 산업", data["industry"])] + [
        (names[c], data["stocks"].get(c) or []) for c, _n in sr.STOCKS]
    for what, picked in groups:
        parts.append(ui.render_section_head(what, "최근 리포트", len(picked)))
        parts.append(ui.render_digest(sr.digest(picked, what), sr.keyword_counts(picked)))
        parts.append(ui.render_report_cards(picked, limit=3, summaries=demo_mod.demo_report_summaries()))
    return "".join(parts)


def _research_panel(use_demo: bool) -> str:
    """산업 리포트 — 앱의 render_research_tab 과 같은 순서."""
    from sources import research as rs

    reports = demo_mod.demo_research()[0] if use_demo else []
    groups = rs.by_category(reports)
    lo, hi = rs.date_range(reports)
    parts = [
        ui.render_section_head(
            "산업 리포트",
            f"증권사 산업분석 · 네이버 증권 리서치 · {lo[5:]} ~ {hi[5:]}", len(reports)),
        ui.render_footnote(
            "<b>제목과 링크만 싣습니다.</b> 리포트 본문은 증권사의 저작물이라 "
            "옮기지 않고 원문으로 보냅니다."),
        ui.render_section_head("업종별 보고서 수",
                               "어느 업종에 리포트가 몰리는가", len(groups)),
        ui.render_research_counts(groups),
        ui.render_section_head("리포트 목록", "제목을 누르면 원문이 열립니다 · "
                               "앱에서는 업종을 골라 좁힙니다", len(reports)),
        ui.render_research_table(reports),
    ]
    if groups:
        cat, rs_ = groups[0]
        parts.append(ui.render_section_head(
            f"{cat} 리포트", "업종을 고르면 요약 요청 링크가 붙습니다", len(rs_)))
        parts.append(ui.render_research_table(rs_, show_category=False))
        parts.append(ui.render_prompt_links(rs.summary_prompt(cat, rs_)))
    return "".join(parts)


def _chart_panel(use_demo: bool, market: str = "kr") -> str:
    """차트 조건 — 앱의 render_chart_tab 과 같은 순서.

    앱에서는 '모두 해당해야 하는 조건' 과 '쪽' 을 눌러 표를 거릅니다. 정적
    프리뷰에는 그 버튼이 없어서, 조건 없이 한 번, 그리고 'CCI + 스토캐스틱 ·
    과매도 쪽' 으로 거른 예를 한 번 보여줍니다.
    """
    import chart_signals as cs

    conds = cs.CONDITIONS
    cands = config.chart_candidates(market)
    ohlc, errs = demo_mod.demo_chart_ohlc(cands) if use_demo else ({}, {})
    rows = cs.build_rows(cands, ohlc, errs)
    ok_rows = [r for r in rows if r.ok]
    names = {k: n for k, n, _r in conds}
    parts = [
        ui.render_section_head(
            f"차트 조건 · {config.MARKETS.get(market, '')}",
            "일봉 기준 — 일목 · 이동평균 · CCI · MACD · 스토캐스틱 · 볼린저 · −DI",
            len(ok_rows)),
        ui.render_footnote(
            "<b>읽어볼 목록이지 매매 신호가 아닙니다.</b> 지표는 지난 가격을 "
            "다시 정리한 값이고 방향을 말해주지 않습니다."),
        # 장이 열려 있을 때만 나오는 안내 (프리뷰에서는 항상 보여 줍니다)
        ui.render_notice(
            "<b>장중 잠정</b> · 10:35 기준 — 오늘 봉을 지금 가격으로 넣어 "
            f"계산했습니다. {config.CHART_TTL_OPEN_SEC // 60}분마다 다시 계산하며, "
            "조건은 <b>종가에 달라질 수 있습니다.</b>"),
        ui.render_chart_counts(cs.counts(rows), len(ok_rows), len(rows), conds),
    ]
    chips = "".join(f'<span class="pv-chip">{n}</span>' for n in names.values())
    sides = "".join(f'<span class="pv-chip">{n}</span>' for _k, n in cs.SIDES)
    parts.append(f'<div class="pv-chips"><span>모두 해당해야 하는 조건</span>{chips}'
                 f"<span>쪽</span>{sides}<span class=\"pv-chip\">내 종목만</span>"
                 "<em>앱에서는 눌러서 고릅니다</em></div>")
    chosen = cs.select(rows)
    parts.append(ui.render_notice(
        f"<b>{len(chosen)}종목</b> · 조건을 고르지 않음 — 해당 수 많은 순"))
    held = {i.symbol for i in config.SECTION_WATCHLIST.instruments
            if config.in_market(i, market)}
    parts.append(ui.render_chart_table(chosen, limit=12, held=held))
    for i, row in enumerate(chosen[:3]):
        parts.append(
            f'<details class="pv-fold"{" open" if i == 0 else ""}><summary>'
            f"{row.name} · {row.ticker} · {row.met}/{len(conds)}</summary>"
            f'<div class="pv-fold-body">{ui.render_chart_detail(row, conds)}</div>'
            "</details>")
    req = ("cci", "stoch")
    ex = cs.select(rows, req, "os")
    parts.append(ui.render_section_head(
        "거른 예", " + ".join(names[k] for k in req) + " · 과매도 쪽", len(ex)))
    parts.append(ui.render_chart_table(ex, limit=8)
                 or ui.render_notice("<b>이 조합에 해당하는 종목이 없습니다.</b>"))
    return "".join(parts)


def _valuation_tab_panel(data, fx, use_demo: bool, market: str = "us") -> str:
    """4. 밸류에이션 판단 — 역DCF + 사분면.

    아래쪽의 _valuation_panel(fundamentals) 은 야후 집계 지표표이고 다른
    함수입니다. 앱에서는 이 탭의 접힌 영역에 그 표가 들어갑니다.
    """
    import buffett

    parts = [
        ui.render_footnote(
            "<b>적정주가를 계산하지 않습니다.</b> 할인율·성장률 가정을 조금만 "
            "바꿔도 원하는 숫자가 나와서 판단 재료가 못 됩니다. 대신 방향을 "
            "뒤집어 <b>현재 가격이 요구하는 성장률</b>을 역산하고, 그걸 "
            "<b>과거 실제 성장률</b>과 비교합니다. FCF 와 순부채는 공시에서 "
            "자동으로 나오고, 외부에서 오는 건 시가총액 하나뿐입니다.<br>"
            "통화가 섞이면 비교가 안 되므로 <b>맨 위에서 고른 시장 하나만</b> "
            "봅니다."),
    ]
    if not use_demo:
        parts.append(ui.render_footnote("실데이터 프리뷰는 앱에서 확인하십시오."))
        return "".join(parts)

    if market == "kr":
        screens_map, _errors = demo_mod.demo_kr_screens()
        caps = demo_mod.demo_kr_market_caps()
        triples = _attach(buffett.rank(list(screens_map.values())), caps, "KRW")
    else:
        screens_map, _errors = demo_mod.demo_screens()
        caps = demo_mod.demo_market_caps()
        triples = _attach(buffett.rank(list(screens_map.values())), caps, "USD")
    parts.insert(0, ui.render_section_head(
        "밸류에이션 판단", "현재 가격이 요구하는 성장률 vs 과거 실제",
        len(triples)))
    if not triples:
        parts.append(ui.render_footnote("<b>대상 종목이 없습니다.</b>"))
        return "".join(parts)
    parts.append(_screen_body(triples, buffett.CRITERIA, 0, caps))
    # 야후 집계 지표표 — 앱에서는 접힌 영역에 들어갑니다
    symbols = [sym for sym, _name in config.VALUATION_TICKERS]
    parts.append(_valuation_panel(
        demo_mod.demo_fundamentals(symbols, config.VALUATION_FIELDS)
        if use_demo else {}))
    return "".join(parts)


def _diag_panel() -> str:
    """진단 — 실제 앱에서는 버튼입니다."""
    return "".join([
        ui.render_section_head(
            "진단", "제가 확인하지 못한 것들을 실제 응답으로 확인합니다", 4),
        ui.render_footnote(
            "이 대시보드의 일부는 <b>실제 API 응답을 받아본 적이 없습니다</b> — "
            "개발 환경에서 DART·SEC·FRED 가 모두 차단되어 있었습니다. "
            "앱에서는 여기에 <b>버튼 4개</b>가 있고, 누르면 실제 응답을 받아 "
            "결과를 보여줍니다. <b>그 출력을 복사해 Claude 에 붙여넣으면</b> "
            "틀린 부분을 고칠 수 있습니다. 터미널을 쓸 필요가 없습니다."),
        ui.render_footnote(
            "확인 항목: <b>경제지표 계열</b>(FRED 13개 · 키 불필요) · "
            "<b>미국 스크리너</b>(companyfacts 계정 · 키 불필요) · "
            "<b>재고 지표</b>(MU XBRL · 키 불필요) · "
            "<b>DART</b>(재고 구성 계정 · 키 필요)."),
        ui.render_footnote(
            "터미널에서 같은 것을 돌리려면: "
            "<code>python -m tools.diagnose --fred</code> "
            "(또는 <code>--screen</code>, <code>--xbrl</code>, "
            "<code>--dart</code>, 전부는 인자 없이)."),
    ])


def _screen_panel(use_demo: bool) -> str:
    """종목 발굴 — 버핏식 숫자 기준."""
    import buffett

    if use_demo:
        screens_map, errors = demo_mod.demo_screens()
    else:
        from sources import edgar as edgar_mod, edgar_facts as facts_mod
        tickers = config.screen_tickers()
        th = config.screen_thresholds()
        screens_map, errors = {}, {}
        try:
            ticker_map = edgar_mod.fetch_ticker_map(config.EDGAR_USER_AGENT)
        except Exception as exc:  # noqa: BLE001
            ticker_map = {}
            errors = {t: f"티커 매핑 실패: {exc}" for t in tickers}
        ciks = {}
        for ticker in tickers:
            cik = (config.EDGAR_CIK_OVERRIDES.get(ticker)
                   or ticker_map.get(ticker.upper())
                   or ticker_map.get(ticker.upper().replace(".", "-")))
            if cik is None:
                errors.setdefault(ticker, "CIK 를 찾지 못했습니다.")
                continue
            ciks[ticker] = cik
        if ciks:
            facts_map, fetch_errors = facts_mod.fetch_many(
                ciks, config.EDGAR_USER_AGENT, keep=buffett.KEEP_TAGS)
            errors.update(fetch_errors)
            for ticker, facts in facts_map.items():
                screens_map[ticker] = buffett.screen_company(
                    ticker, facts, years=config.SCREEN_YEARS, th=th)

    screens = buffett.rank(list(screens_map.values()))
    usable = [s for s in screens if s.ok]

    parts = [
        ui.render_section_head(
            "종목 발굴 (버핏식 숫자 기준)",
            "10년치 공시로 후보를 줄입니다 — 매수 목록이 아닙니다",
            len(config.screen_tickers()),
        ),
        ui.render_footnote(
            "<b>이 화면이 하는 일:</b> 10년치 공시 숫자로 <b>읽어볼 만한 후보</b>를 "
            "줄입니다. <b>하지 않는 일:</b> 무엇을 살지 판단하지 않습니다.<br>"
            "버핏 기준의 핵심인 <b>경제적 해자·경영진의 질·내가 이해하는 사업인가</b>는 "
            "숫자로 걸러지지 않습니다. 그래서 각 카드에 <b>그 다음에 물어볼 질문</b>을 "
            "붙였습니다. <b>점수가 높다고 좋은 투자가 아닙니다</b> — 읽는 순서를 "
            "정하는 용도입니다."
        ),
    ]
    if not usable:
        parts.append(ui.render_footnote(
            "<b>스크리닝 결과가 없습니다.</b> "
            + (" · ".join(f"{t}: {m[:70]}" for t, m in list(errors.items())[:4])
               if errors else "데이터를 받아오지 못했습니다.")))
        return "".join(parts)

    caps = (demo_mod.demo_market_caps() if use_demo
            else _live_caps([s.ticker for s in usable]))
    triples = _attach(usable, caps, "USD")
    parts.append(_screen_body(triples, buffett.CRITERIA, 4, caps))

    if errors:
        parts.append(ui.render_footnote(
            f"<b>조회 실패 {len(errors)}건:</b> "
            + " · ".join(f"{t} ({m[:50]})" for t, m in list(errors.items())[:6])))
    return "".join(parts)


def _macro_panel(section, data, fx, use_demo: bool) -> str:
    """매크로 — 시장가격(실시간) + 경제지표(지연)."""
    import macro as macro_mod

    import brief as brief_mod

    # 브리핑은 매크로 판정이 있어야 쓸 수 있으므로 지표를 **먼저 한 번만**
    # 읽습니다. 아래에서 다시 읽지 않습니다 — 두 번 읽으면 브리핑과 카드가
    # 서로 다른 시점의 숫자를 보여줄 수 있습니다.
    if use_demo:
        series_map, errors = demo_mod.demo_macro_series()
    else:
        from sources import fred as fred_mod
        try:
            series_map, errors = fred_mod.fetch_many(
                config.macro_series_ids(), years=config.MACRO_SERIES_YEARS)
        except Exception as exc:  # noqa: BLE001
            series_map = {}
            errors = {sid: str(exc) for sid in config.macro_series_ids()}

    readings = macro_mod.build_readings(config.macro_series(), series_map, errors)
    # 앱과 같이: 다음 발표일(데모 일정)과 10년물 지금 시세를 붙입니다
    import calendar_events as _ce  # noqa: PLC0415
    readings = macro_mod.attach_context(
        readings,
        next_releases=_ce.next_release_dates(demo_mod.demo_fred_release_dates()),
        live_quotes={"^TNX": (4.21, 0.03)})          # 데모 값
    triggers = macro_mod.evaluate_all(readings)
    brief_lines = brief_mod.compose(
        readings=readings, triggers=triggers,
        fg=demo_mod.demo_feargreed() if use_demo else None,
        vix_state=demo_mod.demo_vix() if use_demo else None,
        exports=demo_mod.demo_kr_exports() if use_demo else None,
        trends=demo_mod.demo_inventory_trends() if use_demo else None,
    )

    parts = [
        ui.render_section_head(
            "증시 브리핑", "지금 화면의 숫자를 문장으로 — 오늘 달라진 것",
            len(brief_lines)),
        ui.render_brief(brief_lines, brief_mod.headline(brief_lines),
                        brief_mod.as_of()),
        ui.render_footnote(
            "<b>새로 받아오는 데이터가 없습니다.</b> 아래 카드에 이미 있는 "
            "값을 문장으로 엮은 것이라, 브리핑 때문에 느려지지 않습니다. "
            "받지 못한 값은 그 줄을 통째로 건너뜁니다 — 빈칸을 '보합' 같은 "
            "말로 메우지 않습니다."),
        ui.render_section_head(
            "직접 쓴 브리핑", "briefings/ 폴더의 글을 날짜별로 읽어옵니다", 1),
        ui.render_briefing_head(demo_mod.demo_briefing()),
        # 정적 미리보기라 본문은 st.markdown 대신 안내로 대체합니다.
        ui.render_footnote(
            "실제 앱에서는 이 자리에 <b>브리핑 본문</b>이 마크다운으로 "
            "렌더됩니다. <code>briefings/2026-11-10.md</code> 같은 "
            "날짜 파일명으로 저장하면 읽어옵니다."),
    ]
    hit_keys = {t.reading.spec.key for t in triggers}

    # 2) 임계값 도달 — 한 줄씩. 헤드라인·질문은 접어 둡니다.
    if triggers:
        parts.append(ui.render_section_head(
            "임계값 도달", "이 지표만 확인하십시오", len(triggers)))
        parts.append(ui.render_trigger_list(triggers))
        targets = macro_mod.news_queries(
            triggers, limit=config.MACRO_MAX_NEWS_TARGETS)
        headlines = (demo_mod.demo_news([t[0] for t in targets])
                     if use_demo else {})
        cards = "".join(
            ui.render_macro_trigger(trig, macro_mod.prompt_for(trig),
                                    headlines.get(trig.reading.spec.key) or ())
            for trig in triggers)
        parts.append('<details class="pv-fold"><summary>관련 헤드라인 · Claude 에 '
                     f'붙여넣을 질문</summary><div class="pv-fold-body">{cards}'
                     "</div></details>")
    else:
        parts.append(ui.render_notice(
            "<b>임계값에 닿은 지표가 없습니다.</b> 조용한 게 정상입니다."))

    # 3) 시장가격 — 표 한 장
    if section is not None:
        parts.append(ui.render_section_head(
            section.title, section.subtitle, len(section.instruments)))
        parts.append(ui.render_quote_table(
            [(inst, pick_quote(inst, data)) for inst in section.instruments]))
        parts.append(ui.render_footnote(section.footnote))

    # 4) 심리 — 공포탐욕 | VIX 좌우
    fg = demo_mod.demo_feargreed() if use_demo else None
    vs = demo_mod.demo_vix() if use_demo else None
    if fg is not None and vs is not None:
        left = (ui.render_section_head(
                    "공포탐욕지수 (CNN)", "시장 심리 0~100 · 세부 지표 7개",
                    7 if fg.ok else 0)
                + ui.render_feargreed(fg)
                + ui.render_footnote(
                    "<b>출처 주의 —</b> CNN 의 문서화되지 않은 내부 "
                    "엔드포인트입니다. 이 지수는 <b>심리 지표이고 가치 판단이 "
                    "아닙니다</b>. 이 프리뷰는 데모 값입니다."))
        right = (ui.render_section_head(
                     "VIX 기간구조", "곡선의 모양 · 과거 대비 위치",
                     sum(1 for p in vs.points if p.ok))
                 + ui.render_vix(vs)
                 + ui.render_footnote(
                     "<b>VIX 숫자 하나는 쓸모가 적습니다.</b> 과거 대비 "
                     "백분위와 기간구조(VIX9D→VIX→VIX3M→VIX6M)를 같이 봅니다."))
        parts.append(f'<div class="dash-two"><div>{left}</div><div>{right}</div></div>')

    # 5) 경제지표 — 묶음별 표 한 장
    parts.append(ui.render_section_head(
        "경제지표 (FRED)",
        "발표 지연이 있는 통계 — 위 시세 표와 성격이 다릅니다",
        len(readings),
    ))
    parts.append(ui.render_footnote(
        "위 표는 <b>시장가격</b>(실시간), 아래는 <b>통계</b>입니다. "
        "통계는 발표가 2~6주 늦으므로 줄마다 <b>관측 시점과 지연일수</b>를 "
        "함께 적었습니다. 앱에서는 '각 지표를 보는 이유 표시' 를 켜면 줄마다 "
        "설명이 붙습니다."
    ))
    by_group: dict[str, list] = {}
    for reading in readings:
        by_group.setdefault(reading.spec.group, []).append(reading)
    parts.append(ui.render_macro_table(config.MACRO_GROUPS, by_group, hit_keys))

    unverified = [r.spec for r in readings if not r.spec.verified]
    if unverified:
        parts.append(ui.render_footnote(
            "<b>계열 ID 미검증:</b> "
            + ", ".join(s.series_id for s in unverified)
            + ". <code>python -m tools.diagnose --fred</code> 로 검증하십시오."
        ))
    return "".join(parts)


def _valuation_panel(fundamentals) -> str:
    return "".join((
        ui.render_section_head(
            "밸류에이션 지표", "관심종목 기준 · 야후 파이낸스 집계값",
            len(config.VALUATION_TICKERS),
        ),
        ui.render_valuation_table(
            config.VALUATION_TICKERS, config.VALUATION_FIELDS, fundamentals
        ),
        ui.render_footnote(
            "야후 집계값이며 공시 원문이 아닙니다. Forward PER 은 컨센서스 기반 추정치이고, "
            "ETF 는 개별 기업 지표가 비어 있는 항목이 많습니다."
        ),
    ))


def _analysis_panel() -> str:
    """'공시 분석' 탭 — 실제 analysis/ 폴더를 읽어 생성 현황을 보여줍니다."""
    import os

    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config.ANALYSIS_DIR
    )
    instruments = config.analysis_instruments()
    docs = analysis_store.load_all(base, [i.analysis_key for i in instruments])

    parts = [
        ui.render_section_head(
            "공시 분석", "Claude 스킬 산출물 뷰어 · analysis/ 폴더를 읽습니다",
            len(instruments),
        ),
        ui.render_analysis_index(instruments, docs),
        '<div class="pv-note">'
        "이 탭은 <code>/company-decoder-korean</code>, <code>/company-story-korean</code>, "
        "<code>/price-decoder-korean</code> 스킬이 만든 HTML 을 읽어 표시합니다.<br>"
        "스킬은 Claude 세션에서 돌아가므로 앱이 직접 호출할 수 없습니다. "
        "Claude 에게 분석을 요청해 받은 HTML 을 "
        "<code>analysis/&lt;티커&gt;/decoder.html</code> 같은 경로에 저장하면 "
        "여기에 나타납니다. 위 칩의 초록 표시가 생성 완료된 분석입니다."
        "</div>",
    ]

    # 생성된 분석이 있으면 그걸 보여주고, 없으면 미생성 안내를 보여줍니다
    ready = [i for i in instruments if not docs[i.analysis_key].is_empty]
    sample = ready[0] if ready else (instruments[0] if instruments else None)

    if sample is not None:
        doc = docs[sample.analysis_key]
        parts.append(ui.render_analysis_header(sample, doc))
        for kind, label, desc in analysis_store.KINDS:
            parts.append(f'<div class="dash-footnote">{desc}</div>')
            body = doc.html.get(kind)
            if body:
                parts.append(ui.render_analysis_body(body))
            else:
                cmd = analysis_store.skill_command(kind, sample.analysis_key, sample.name)
                parts.append(ui.render_analysis_missing(label, cmd, sample.analysis_key, kind))
            parts.append('<div style="height:14px"></div>')
        if doc.sources:
            parts.append(ui.render_analysis_sources(doc.sources))

    return "".join(parts)


def build_html(convention: str, use_demo: bool) -> str:
    val_symbols = [sym for _label, sym in config.VALUATION_TICKERS]

    if use_demo:
        data = demo_mod.demo_payload()
        fundamentals = demo_mod.demo_fundamentals(val_symbols, config.VALUATION_FIELDS)
    else:
        from sources import hyperliquid, naver, yahoo

        data = {
            "yahoo": yahoo.fetch_quotes(config.all_yahoo_symbols()),
            "naver": naver.fetch_quotes(config.all_naver_codes()),
            "hyperliquid": hyperliquid.fetch_quotes(config.all_hyperliquid_symbols()),
        }
        fundamentals = yahoo.fetch_fundamentals(val_symbols, config.VALUATION_FIELDS)

    fx = resolve_fx(data.get("yahoo", {}), config.FX_OVERRIDE)

    # ── 시장이 최상위 축 — 앱과 같은 구조 ─────────────────────────────
    # 시장마다 내용이 다른 탭은 패널을 따로 만듭니다 (kr:summary, us:summary).
    # 한쪽에만 있거나 공통인 탭은 하나만 만듭니다.
    PER_MARKET = {"summary", "holdings", "discover", "screener", "valuation", "chart", "earnings"}

    def panel_key(market: str, key: str) -> str:
        return f"{market}:{key}" if key in PER_MARKET else key

    def render_panel(market: str, key: str) -> str:
        if key == "summary":
            return _summary_panel(data, fx, use_demo, market)
        if key == "holdings":
            return _holdings_panel(data, fx, use_demo, market)
        if key in ("discover", "screener"):
            return _discover_panel(use_demo, market)
        if key == "valuation":
            return _valuation_tab_panel(data, fx, use_demo, market)
        if key == "research":
            return _research_panel(use_demo)
        if key == "semi_research":
            return _semi_research_panel(use_demo)
        if key == "supply":
            return _supply_panel(use_demo)
        if key == "earnings":
            return _earnings_panel(use_demo, market)
        if key == "calendar":
            return _calendar_panel(data, use_demo, market)
        if key == "chart":
            return _chart_panel(use_demo, market)
        if key == "sector_heat":
            return _sector_heat_panel(use_demo)
        if key == "kr_flows":
            return _kr_flows_panel(use_demo)
        if key == "us_flows":
            return _us_flows_panel(use_demo)
        if key == "cycle":
            return _cycle_panel(use_demo)
        if key == "macro":
            note = ""
            if market == "kr":
                note = ui.render_footnote(
                    "<b>한국 화면에서도 매크로는 '공통' 입니다.</b> 미국 금리·"
                    "원달러·유가·VIX 는 국내 종목만 보는 날에도 같은 배경이라, "
                    "두 시장이 같이 씁니다.")
            return _macro_panel(config.SECTION_BY_KEY.get("macro"),
                                data, fx, use_demo) + note
        section = config.SECTION_BY_KEY.get(key)
        return _section_panel(section, data, fx) if section is not None else ""

    navs: list[str] = []
    panels: list[str] = []
    made: set[str] = set()
    # 패널마다 큰 데모 경고를 반복하지 않습니다 — 맨 위 한 줄로 충분합니다.
    demo_top = ""
    for market in config.MARKETS:
        groups = config.tab_groups(market)
        buttons = "".join(
            f'<div class="pv-navgroup">{gname}</div>'
            + "".join(
                f'<button class="pv-tab" role="tab" '
                f'data-key="{panel_key(market, key)}" '
                f'aria-selected="false">{label}</button>'
                for key, label in items)
            for gname, items in groups)
        navs.append(f'<div class="pv-tabs pv-nav" data-market="{market}" '
                    f'role="tablist" hidden>{buttons}</div>')
        for _g, items in groups:
            for key, _label in items:
                pk = panel_key(market, key)
                if pk in made:
                    continue
                made.add(pk)
                # 공통 탭(매크로)은 한국에서 열 때만 설명 각주가 붙으므로
                # 한국 쪽에서 먼저 만들어집니다 — 미국에서도 같은 패널을
                # 쓰지만 각주 한 줄이 남는 건 감수합니다.
                body = render_panel(market, key)
                panels.append(f'<div class="pv-panel" data-key="{pk}" '
                              f'hidden>{demo_top}{body}</div>')

    market_switch = (
        '<div class="pv-topctl"><div class="pv-market" role="tablist">'
        + "".join(
            f'<button class="pv-mkt" type="button" data-market="{m}" '
            f'aria-pressed="false">{label} 시장</button>'
            for m, label in config.MARKETS.items())
        + '</div><button class="pv-notes-btn" id="pv-notes" type="button" '
          'aria-pressed="false">설명 보기</button></div>'
        + "".join(
            f'<div class="pv-strip" data-market="{m}" hidden>'
            + ui.render_market_strip(
                [(label, inst, pick_quote(inst, data))
                 for inst, label in config.strip_instruments(m)])
            + "</div>"
            for m in config.MARKETS))

    css = (
        "<style>"
        + build_vars(convention, ":root")
        + build_rules() + build_stack_rules()
        + EXTRA_CSS
        + "</style>"
    )

    banner = (
        '<div class="demo-banner"><b>프리뷰 · 숫자는 전부 데모 값</b> — '
        "레이아웃 확인용이며 실제 시세가 아닙니다.</div>"
        if use_demo
        else ""
    )

    return "\n".join((
        "<!DOCTYPE html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>주식 대시보드 — 레이아웃 프리뷰</title>",
        css,
        '</head><body><div class="dash-wrap">',
        '<div class="dash-topbar">'
        '<span class="dash-logo">주식 대시보드</span>'
        '<span class="dash-market-badge" id="pv-badge">한국 시장</span>'
        '<span class="dash-logo-sub">야간 대체시세 · 시장 지표 · 관심종목</span>'
        "</div>",
        banner,
        '<div class="pv-ctrl" aria-hidden="true"><span>표시</span>'
        '<span>데이터</span><span>진단</span><span>갱신</span></div>',
        market_switch,
        '<div class="pv-shell">',
        '<div class="pv-side">' + "".join(navs) + "</div>",
        '<div class="pv-main">'
        # 앱은 화면마다 그 화면에서 쓴 값의 받은 시각을 적습니다 (여기는 예시)
        '<div class="dash-times"><b>받은 시각</b><span>시세 11:04</span>'
        '<span>경제지표(FRED) 10:58</span><span>공포탐욕 11:01</span>'
        '<span class="old">국내 재무 심사 06:35 <i>4시간 전</i></span></div>'
        f'{"".join(panels)}</div>',
        "</div>",
        ui.render_footnote(
            "정보 제공 목적이며 투자 판단의 근거가 아닙니다. 시세는 지연될 수 있고, "
            "사용하는 데이터 소스는 어느 것도 공식 API 가 아닙니다."
        ),
        "</div>",
        f"<script>{TAB_SCRIPT}</script>",
        "</body></html>",
    ))


def main(argv: list[str]) -> int:
    convention = "us" if "--us-colors" in argv else "kr"
    use_demo = "--live" not in argv

    html_text = build_html(convention, use_demo)
    with open("preview.html", "w", encoding="utf-8") as fh:
        fh.write(html_text)

    print(f"preview.html 생성 완료 ({len(html_text):,} bytes, demo={use_demo})")
    print("섹션 전환 · 카드 링크가 모두 동작합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def _live_caps(tickers: list[str]) -> dict[str, float]:
    """실데이터 프리뷰용 시가총액. 실패는 조용히 건너뜁니다."""
    from sources import yahoo as yahoo_mod

    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            value = yahoo_mod.fetch_market_cap(ticker)
        except Exception:  # noqa: BLE001
            continue
        if value:
            out[ticker] = value
    return out
