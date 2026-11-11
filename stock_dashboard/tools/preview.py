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
from theme import build_rules, build_vars

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

  /* 섹션 내비 — 앱과 같이 세로입니다 */
  .pv-shell { display: flex; gap: 26px; align-items: flex-start; }
  .pv-side { flex: 0 0 150px; position: sticky; top: 14px; }
  .pv-main { flex: 1 1 auto; min-width: 0; }
  .pv-tabs { display: flex; flex-direction: column; gap: 1px; }
  .pv-tab {
    appearance: none; background: none; cursor: pointer; text-align: left;
    border: none; border-left: 2px solid transparent;
    color: var(--dash-ink-muted);
    font: inherit; font-size: var(--fs-4); font-weight: 600;
    padding: 7px 11px; border-radius: 0 var(--r-inner) var(--r-inner) 0;
    transition: color 0.12s ease, border-color 0.12s ease,
                background 0.12s ease;
  }
  .pv-tab:hover {
    color: var(--dash-ink-2); background: var(--dash-surface-raised);
  }
  .pv-tab[aria-selected="true"] {
    color: var(--dash-ink); border-left-color: var(--dash-accent);
    background: var(--dash-surface); font-weight: 700;
  }
  .pv-navgroup {
    font-size: var(--fs-1); font-weight: 700; letter-spacing: .06em;
    color: var(--dash-ink-muted); margin: 11px 0 3px; padding-left: 11px;
  }
  .pv-navgroup:first-child { margin-top: 0; }
  @media (max-width: 760px) {
    .pv-shell { display: block; }
    .pv-side { position: static; margin-bottom: 14px; }
    .pv-tabs { flex-direction: row; flex-wrap: wrap; align-items: center; }
    .pv-navgroup { width: 100%; margin: 8px 0 2px; padding-left: 0; }
    .pv-tab {
      border-left: none; border-bottom: 2px solid transparent;
      border-radius: var(--r-inner) var(--r-inner) 0 0;
    }
    .pv-tab[aria-selected="true"] {
      border-left-color: transparent;
      border-bottom-color: var(--dash-accent);
    }
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
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.pv-tab'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.pv-panel'));

  function show(key) {
    tabs.forEach(function (t) {
      t.setAttribute('aria-selected', String(t.dataset.key === key));
    });
    panels.forEach(function (p) {
      if (p.dataset.key === key) { p.removeAttribute('hidden'); }
      else { p.setAttribute('hidden', ''); }
    });
    if (location.hash.slice(1) !== key) {
      history.replaceState(null, '', '#' + key);
    }
  }

  tabs.forEach(function (t) {
    t.addEventListener('click', function () { show(t.dataset.key); });
  });
  window.addEventListener('hashchange', function () {
    var key = location.hash.slice(1);
    if (tabs.some(function (t) { return t.dataset.key === key; })) { show(key); }
  });

  var start = location.hash.slice(1);
  show(tabs.some(function (t) { return t.dataset.key === start; })
       ? start : tabs[0].dataset.key);

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


def _signals_panel(data, use_demo: bool) -> str:
    """변화 감지 탭. 정적 프리뷰에서는 프롬프트를 <details> 로 접어 넣습니다."""
    import os

    import analysis_store as astore
    import signals as sig_mod
    from compute import pick_quote

    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config.ANALYSIS_DIR
    )
    instruments = list(config.SECTION_WATCHLIST.instruments)
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


def _summary_panel(data, fx, use_demo: bool) -> str:
    """0. 요약 — 휴대폰 10초 화면."""
    import config as cfg
    import macro as macro_mod
    import summary as sm

    if use_demo:
        fg = demo_mod.demo_feargreed()
        vix_state = demo_mod.demo_vix()
        trends = demo_mod.demo_inventory_trends()
        series, errs = demo_mod.demo_macro_series()
    else:
        fg = vix_state = None
        trends, series, errs = {}, {}, {}
    readings = macro_mod.build_readings(cfg.macro_series(), series, errs)

    summary = sm.build(
        urgent=[], soon=[],
        holdings_total=len(cfg.SECTION_WATCHLIST.instruments),
        fg=fg, vix_state=vix_state, trends=trends, macro_readings=readings)

    parts = [
        ui.render_section_head(
            "요약", "휴대폰에서 10초 — 지금 알아야 할 것만", 4),
        ui.render_summary(summary),
        ui.render_briefing_line(demo_mod.demo_briefing()),
    ]
    if summary.all_quiet:
        parts.append(ui.render_footnote(
            "<b>조용한 게 정상입니다.</b> 이 화면은 뉴스 피드가 아니라 "
            "<b>임계값을 건드린 것만</b> 올립니다 — 올라온 게 없으면 앱을 "
            "닫아도 됩니다."))
    parts.append(ui.render_footnote(
        "<b>왜 탭이 하나 더 늘었나:</b> 아래 5개는 \"무엇을 하려는 화면인가\" 로 "
        "묶었고, 이 요약은 <b>\"휴대폰에서 10초\"</b> 입니다 — 축이 다릅니다. "
        "간간히 확인하는 용도라면 탭 5개를 돌 게 아니라 한 화면에서 끝나야 "
        "합니다.<br><b>발굴·밸류에이션은 일부러 뺐습니다</b> — 68종목의 10년 "
        "재무를 받아오는 작업이라 휴대폰 글랜스에 맞지 않습니다."))
    return "".join(parts)


def _holdings_panel(data, fx, use_demo: bool) -> str:
    """1. 내 종목 — 변화 감지 + 시세 + 공시 분석."""
    parts = [_signals_panel(data, use_demo)]
    watchlist = config.SECTION_WATCHLIST
    parts.append(ui.render_section_head(
        "보유 · 관심 종목", watchlist.subtitle, len(watchlist.instruments)))
    cards = "".join(
        ui.render_card(inst, (data.get(inst.source) or {}).get(inst.symbol), fx)
        for inst in watchlist.instruments)
    parts.append(f'<div class="dash-grid cols-4">{cards}</div>')
    # 공시 분석은 앱에서 **접혀 있습니다** — 프리뷰에도 접힌 상태로 보여줍니다
    parts.append(
        '<details class="pv-fold"><summary>'
        "공시 분석 — 앱에서는 접혀 있습니다 (눌러서 펼치기)"
        "</summary>" + _analysis_panel() + "</details>"
    )
    return "".join(parts)


def _flows_panel(use_demo: bool) -> str:
    """뉴스 · 공시 · 지표 — 앱에서는 왼쪽 시장 선택을 따릅니다."""
    import inflation
    import liquidity  # noqa: F401 - 데모가 반환하는 타입

    parts = [
        ui.render_footnote(
            "<b>앱에서는 왼쪽 시장 선택을 따릅니다</b> — '한국' 을 고르면 "
            "섹터 뉴스·공시·한국 지표만, '미국' 을 고르면 물가·유동성만 "
            "나옵니다. 프리뷰는 둘 다 보여줍니다."),
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

    filings = demo_mod.demo_market_filings() if use_demo else []
    parts.append(ui.render_section_head(
        "한국 — 주요 공시", "최근 3일 · 전체 시장에서 추렸습니다", len(filings)))
    parts.append(ui.render_market_filings(filings))

    kr_rows = (demo_mod.demo_kr_macro(config.KR_MACRO_SERIES)
               if use_demo else [])
    parts.append(ui.render_section_head(
        "한국 — 경제지표", "FRED 경유 · 전년동월비 병기", len(kr_rows)))
    parts.append(ui.render_simple_rows(kr_rows))
    parts.append(ui.render_footnote(
        "<b>한국 계열 ID 는 전부 미검증입니다.</b> FRED 의 한국 통계는 "
        "OECD 경유라 ID 체계가 미국 계열과 다르고 중단된 것도 많습니다. "
        "'—' 로 나오면 그 계열이 없는 것입니다."))

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


def _discover_panel(use_demo: bool) -> str:
    """2. 종목 발굴 — 미국은 품질 기준만, 국내는 변동성·밸류 스크리너."""
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
    }
    companies = demo_mod.demo_kr_companies(
        tuple(c for c, _n in cands)) if use_demo else {}
    news_demo = demo_mod.demo_news([c for c, _n in cands]) if use_demo else {}

    for key, title, rule, caveat in kr_screen.KR_SCREENS:
        picked = hits.get(key, [])
        parts.append(ui.render_screener_head(title, rule, len(picked), caveat))
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


def _valuation_tab_panel(data, fx, use_demo: bool) -> str:
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
            "앱에서는 <b>미국/국내</b>와 <b>보유+발굴 통과 / 전체</b>를 "
            "전환할 수 있습니다."),
    ]
    if not use_demo:
        parts.append(ui.render_footnote("실데이터 프리뷰는 앱에서 확인하십시오."))
        return "".join(parts)

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
    if section is not None:
        parts.append(_section_panel(section, data, fx))

    triggers = macro_mod.evaluate_all(readings)
    hit_keys = {t.reading.spec.key for t in triggers}

    # 공포탐욕지수 — 가격도 통계도 아닌 제3의 성격이라 둘 사이에 둡니다
    fg = demo_mod.demo_feargreed() if use_demo else None
    if fg is not None:
        parts.append(ui.render_section_head(
            "공포탐욕지수 (CNN Fear & Greed)",
            "시장 심리 0~100 · 세부 지표 7개로 '왜 그 값인가' 를 함께",
            7 if fg.ok else 0))
        parts.append(ui.render_feargreed(fg))
        parts.append(ui.render_footnote(
            "숫자가 안 맞는다고 느끼시면 "
            '<a class="dash-inline-link" '
            'href="https://edition.cnn.com/markets/fear-and-greed" '
            'target="_blank" rel="noopener noreferrer">CNN 공식 페이지</a>'
            " 와 직접 대조해 보십시오. "
            "<b>이 프리뷰는 데모 데이터라 당연히 다릅니다</b> — 실제 앱에서 "
            "다르면 화면 위쪽 진단 패널 → 경제지표 확인을 돌려 출력을 "
            "알려주십시오."))
        if fg.ok and fg.extremes:
            parts.append(ui.render_footnote(
                "<b>지금 지수를 끌고 있는 것:</b> "
                + " · ".join(f"{c.label} {c.score:,.0f}({c.band})"
                             for c in fg.extremes)
                + ". 지수 한 숫자만 보면 같은 '탐욕 70' 이 주가 모멘텀 때문인지 "
                "채권 수요 때문인지 알 수 없어서, 극단에 있는 세부 지표를 "
                "따로 적었습니다."))
        parts.append(ui.render_footnote(
            "<b>출처 주의 —</b> CNN 이 자기 페이지에서 쓰는 "
            "<b>문서화되지 않은 내부 엔드포인트</b>입니다. 공개 API 가 아니라 "
            "예고 없이 바뀌거나 막힐 수 있어, 실패해도 다른 지표에 영향이 "
            "가지 않게 격리했습니다. 이 지수는 <b>심리 지표이고 가치 판단이 "
            "아닙니다</b> — 탐욕 구간이라고 비싸다는 뜻이 아닙니다."))

    # VIX 기간구조 — 공탐지수와 같은 심리·위험 묶음
    if use_demo:
        import sources.vix as vix_mod

        vs = demo_mod.demo_vix()
        parts.append(ui.render_section_head(
            "VIX 기간구조", "숫자 하나가 아니라 곡선의 모양 · 과거 대비 위치",
            sum(1 for p in vs.points if p.ok)))
        parts.append(ui.render_vix(vs))
        parts.append(ui.render_footnote(
            "<b>VIX 숫자 하나는 쓸모가 적습니다.</b> 18 이 높은지 낮은지는 맥락 "
            "없이 답할 수 없어서, 위 카드의 VIX 값에 두 가지를 붙였습니다 — "
            "<b>과거 대비 백분위</b>(FRED VIXCLS 5년)와 <b>기간구조</b>"
            "(VIX9D→VIX→VIX3M→VIX6M 곡선의 모양).<br>"
            "평소에는 뒤 만기가 더 높습니다(<b>콘탱고</b>). 위기에는 앞이 치솟아 "
            "뒤보다 높아집니다(<b>백워데이션</b>) — 2010년 이후 전체 거래일의 "
            f"<b>{vix_mod.BACKWARDATION_BASE_RATE:g}%</b> 에만 나타났으니, "
            "드물기 때문에 신호가 됩니다."))

    if triggers:
        parts.append(ui.render_section_head(
            "임계값 도달", "이 지표만 확인하십시오", len(triggers)))
        targets = macro_mod.news_queries(
            triggers, limit=config.MACRO_MAX_NEWS_TARGETS)
        headlines = (demo_mod.demo_news([t[0] for t in targets])
                     if use_demo else {})
        for trig in triggers:
            parts.append(ui.render_macro_trigger(
                trig, macro_mod.prompt_for(trig),
                headlines.get(trig.reading.spec.key) or ()))
    else:
        parts.append(ui.render_footnote(
            "<b>임계값에 닿은 지표가 없습니다.</b> 조용한 게 정상입니다 — "
            "이 탭은 뉴스 피드가 아니라, 지표가 실제로 움직였을 때만 "
            "올라오게 만들었습니다."
        ))

    parts.append(ui.render_section_head(
        "경제지표 (FRED)",
        "발표 지연이 있는 통계 — 위 가격 카드와 성격이 다릅니다",
        len(readings),
    ))
    parts.append(ui.render_footnote(
        "위 카드는 <b>시장가격</b>(실시간), 아래는 <b>통계</b>입니다. "
        "통계는 발표가 2~6주 늦으므로 각 칸에 <b>관측 시점과 지연일수</b>를 "
        "함께 적었습니다. 지수 계열(산업생산·PPI)은 기준연도가 바뀌어 레벨 비교가 "
        "불가능하므로 <b>전년 동기 대비</b>만 표시합니다. "
        "FRED 는 인증키가 필요 없습니다."
    ))

    by_group: dict[str, list] = {}
    for reading in readings:
        by_group.setdefault(reading.spec.group, []).append(reading)
    for key, title, subtitle in config.MACRO_GROUPS:
        parts.append(ui.render_macro_group(
            title, subtitle, by_group.get(key, []), hit_keys, show_why=True))

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
    pairs = config.tab_labels()

    # 탭 버튼
    # 묶음 이름을 붙입니다 — 앱의 세로 내비와 같은 구조입니다.
    tab_buttons = "".join(
        f'<div class="pv-navgroup">{gname}</div>'
        + "".join(
            f'<button class="pv-tab" role="tab" data-key="{key}" '
            f'aria-selected="false">{label}</button>'
            for key, label in items)
        for gname, items in config.tab_groups()
    )
    theme_toggle = ""

    # 탭 패널
    panels: list[str] = []
    for key, _label in pairs:
        if key == "signals":
            body = _signals_panel(data, use_demo)
        elif key == "cycle":
            body = _cycle_panel(use_demo)
        elif key == "summary":
            body = _summary_panel(data, fx, use_demo)
        elif key == "holdings":
            body = _holdings_panel(data, fx, use_demo)
        elif key == "discover":
            body = _discover_panel(use_demo)
        elif key == "flows":
            body = _flows_panel(use_demo)
        elif key == "valuation":
            body = _valuation_tab_panel(data, fx, use_demo)
        elif key == "macro":
            body = _macro_panel(config.SECTION_BY_KEY.get("macro"),
                                data, fx, use_demo)
        else:
            section = config.SECTION_BY_KEY.get(key)
            body = _section_panel(section, data, fx) if section is not None else ""
        # 데모 배너를 모든 패널 맨 위에 — 데모 숫자가 그럴듯해서 실제 값과
        # 구분이 안 되는 문제가 있었습니다. 어느 탭을 열어도 보여야 합니다.
        banner = ui.render_demo_banner(preview=True) if use_demo else ""
        panels.append(
            f'<div class="pv-panel" data-key="{key}" hidden>{banner}{body}</div>')

    css = (
        "<style>"
        + build_vars(convention, ":root")
        + build_rules()
        + EXTRA_CSS
        + "</style>"
    )

    banner = (
        '<div class="demo-banner"><b>레이아웃 프리뷰 (데모 데이터)</b><br>'
        "숫자는 레이아웃 확인용 가짜 값이며 실제 시세가 아닙니다. "
        "왼쪽 목록에서 섹션을 고르십시오. "
        "카드 제목을 누르면 해당 종목 페이지로 이동합니다. "
        "실제 시세는 <code>streamlit run app.py</code> 로 확인하십시오.</div>"
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
        '<span class="dash-logo-sub">야간 대체시세 · 시장 지표 · 관심종목</span>'
        f"{theme_toggle}</div>",
        banner,
        '<div class="pv-shell">',
        '<div class="pv-side">'
        f'<div class="pv-tabs" role="tablist">{tab_buttons}</div>'
        '<div class="dash-navhead">보는 시장</div>'
        '<div class="pv-tabs">'
        '<button class="pv-tab" aria-selected="true" type="button">전체</button>'
        '<button class="pv-tab" type="button">미국</button>'
        '<button class="pv-tab" type="button">한국</button>'
        "</div>"
        '<div class="dash-footnote" style="margin-top:10px">'
        "프리뷰에서는 시장 선택이 표시만 됩니다 — 실제 앱에서 목록이 "
        "걸러집니다.</div>"
        "</div>",
        f'<div class="pv-main">{"".join(panels)}</div>',
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
