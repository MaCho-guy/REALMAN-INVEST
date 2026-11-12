"""
진단 리포트 — 실제 데이터로 열린 질문에 답합니다.

제가(Claude) 이 샌드박스에서 확인할 수 없는 것들이 있습니다. DART·EDGAR 가
모두 차단되어 있어서, 아래 질문은 수빈님 컴퓨터에서만 답이 나옵니다:

  1. 재고 구성(원재료·재공품·완제품) 계정이 실제로 응답에 있나?
  2. DIO 가 타당 범위(5~400일)에 들어오나? 기간 처리가 맞나?
  3. XBRL 태그 후보 중 어느 게 실제로 쓰이나?
  4. MU 가 공시한 DIO 와 계산값이 얼마나 다른가?
  5. 제가 확인하지 못한 FRED 계열 ID 가 실제로 존재하나?
     (공포탐욕지수 엔드포인트가 아직 열려 있는지도 함께 확인합니다)
  6. 스크리닝 대상 기업의 CIK 와 계정이 실제로 잡히나?

실행:
    cd stock_dashboard
    python -m tools.diagnose              # 전체
    python -m tools.diagnose --dart       # DART(한국 2사)만
    python -m tools.diagnose --xbrl       # EDGAR XBRL(MU)만
    python -m tools.diagnose --fred       # FRED 계열 ID 검증만 (키 불필요)
    python -m tools.diagnose --codes      # 국내 종목코드 대조 (인증키 필요)
    python -m tools.diagnose --screen     # 스크리닝 대상 검증 (키 불필요, 느림)
    python -m tools.diagnose > report.txt # 파일로 저장

**출력을 그대로 복사해 Claude 에 붙여넣으면** 결과에 맞춰 코드를 고칠 수 있습니다.
인증키는 출력에 포함되지 않습니다 (끝 4자리만 표시).
"""

from __future__ import annotations

import sys
import textwrap

import config
import cycle
import buffett
import macro as macro_mod
from sources import (
    dart, edgar, edgar_facts, edgar_xbrl, feargreed, fred,
)

LINE = "=" * 74


def head(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


# ──────────────────────────────────────────────────────────────────────────────
# DART
# ──────────────────────────────────────────────────────────────────────────────

def diagnose_dart() -> None:
    head("DART — 한국 2사")

    ok, msg = dart.key_status()
    print(f"인증키: {msg}")
    if not ok:
        print("\n키가 없어 DART 진단을 건너뜁니다.")
        print("발급: https://opendart.fss.or.kr → 인증키 신청/관리")
        return

    try:
        corp_map = dart.fetch_corp_codes()
        print(f"고유번호 매핑: 상장사 {len(corp_map):,}개")
    except dart.DartError as exc:
        print(f"고유번호 조회 실패: {exc}")
        return

    for inst in config.cycle_instruments():
        corp = dart.resolve_corp_code(
            inst.symbol, corp_map, config.DART_CORP_CODE_OVERRIDES)
        print(f"\n{'-' * 74}")
        print(f"{inst.name} ({inst.symbol}) → corp_code {corp}")
        if not corp:
            print("  고유번호를 찾지 못했습니다.")
            continue

        year, quarter = dart.latest_available_quarter()
        print(f"조회 시도: {year} {quarter} ({dart.REPORT_CODES[quarter]}), "
              f"fs_div={config.CYCLE_FS_DIV}")

        try:
            accounts = dart.fetch_financials(
                corp, year, quarter, fs_div=config.CYCLE_FS_DIV)
        except dart.DartError as exc:
            print(f"  실패: {exc}")
            year, quarter = dart.previous_quarter(year, quarter)
            print(f"  한 분기 물러서서 재시도: {year} {quarter}")
            try:
                accounts = dart.fetch_financials(
                    corp, year, quarter, fs_div=config.CYCLE_FS_DIV)
            except dart.DartError as exc2:
                print(f"  재시도도 실패: {exc2}")
                continue

        print(f"  응답 계정 수: {len(accounts)}")
        by_sj: dict[str, int] = {}
        for a in accounts:
            by_sj[a.sj_div] = by_sj.get(a.sj_div, 0) + 1
        print(f"  재무제표 구분별: {by_sj}")

        # ── 질문 1·3: 각 규칙이 어느 계정을 집었나 ─────────────────────────
        print(f"\n  [계정 매칭 결과]")
        for key, rule in cycle.RULES.items():
            acc = cycle.find_account(accounts, rule)
            if acc is None:
                print(f"    ✗ {rule.label:<10} 찾지 못함 "
                      f"(후보ID {rule.ids[0]}, 후보명 {rule.names})")
            else:
                std = "표준ID" if acc.account_id not in ("", cycle.NOT_STANDARD) else "계정명"
                val = cycle.pick_amount(acc, period="quarter")
                shown = f"{val:,.0f}" if val is not None else "값 없음"
                print(f"    ✓ {rule.label:<10} [{std}] {acc.account_nm} "
                      f"({acc.sj_div}) = {shown}")

        # ── 재고 관련 계정 전체 덤프 (구성 항목이 있는지 확인용) ───────────
        inv_like = [a for a in accounts
                    if "재고" in a.account_nm or "제품" in a.account_nm
                    or "원재료" in a.account_nm or "재공" in a.account_nm]
        print(f"\n  [재고 관련 계정 전체 {len(inv_like)}건] "
              f"← 질문: 재고 구성이 응답에 있나?")
        for a in inv_like[:20]:
            val = a.thstrm_amount
            shown = f"{val:,.0f}" if val is not None else "—"
            print(f"    {a.sj_div}  {a.account_nm[:34]:<34} {shown:>22}  "
                  f"{a.account_id[:40]}")
        if len(inv_like) > 20:
            print(f"    … {len(inv_like) - 20}건 더")

        # ── 질문 2: DIO ───────────────────────────────────────────────────
        m = cycle.metrics_from_accounts(accounts, year, quarter, config.CYCLE_FS_DIV)
        print(f"\n  [DIO 계산] ← 질문: 타당 범위에 들어오나?")
        print(f"    기간일수 {m.period_days}")
        if m.dio_raw is None:
            print(f"    계산 불가 (재고={m.inventory}, 매출원가={m.cost_of_sales})")
        else:
            verdict = "정상" if m.dio is not None else "범위 밖 → 제외됨"
            print(f"    raw {m.dio_raw:.1f}일  →  {verdict}")
            if m.dio_warning:
                print(f"    경고: {m.dio_warning}")
        mix = m.inventory_mix
        if mix:
            print(f"    재고 구성: {mix}")
        else:
            print("    재고 구성: 이 응답에 없습니다 — 고장이 아닙니다.")
            print("              구성(원재료·재공품·완제품)은 사업보고서 "
                  "**주석**에 있고,")
            print("              fnlttSinglAcntAll 은 본표만 줍니다. "
                  "DIO 는 위에서 정상 산출됩니다.")


# ──────────────────────────────────────────────────────────────────────────────
# EDGAR XBRL
# ──────────────────────────────────────────────────────────────────────────────

def diagnose_xbrl() -> None:
    head("EDGAR XBRL — 미국 기업 (키 불필요)")

    ua = config.EDGAR_USER_AGENT
    print(f"User-Agent: {ua}")
    if "your-email" in ua or "example.com" in ua:
        print("  ⚠ config.py 의 EDGAR_USER_AGENT 에 본인 연락처를 넣으십시오.")
        print("    SEC 는 없으면 403 으로 거부합니다.")

    try:
        ticker_map = edgar.fetch_ticker_map(ua)
        print(f"티커 매핑: {len(ticker_map):,}개")
    except Exception as exc:  # noqa: BLE001
        print(f"티커 매핑 실패: {exc}")
        return

    for ticker in config.CYCLE_US_TICKERS:
        cik = config.EDGAR_CIK_OVERRIDES.get(ticker) or ticker_map.get(ticker.upper())
        print(f"\n{'-' * 74}")
        print(f"{ticker} → CIK {cik}")
        if cik is None:
            print("  CIK 를 찾지 못했습니다.")
            continue

        collected: dict[str, list] = {}
        print(f"\n  [태그 후보 시도] ← 질문: 어느 태그가 실제로 쓰이나?")
        for key, tags in cycle.XBRL_TAGS.items():
            try:
                tag, facts = edgar_xbrl.fetch_first_available(cik, tags, ua)
                collected[key] = facts
                kinds = {
                    "시점": sum(1 for f in facts if f.is_instant),
                    "분기": sum(1 for f in facts if f.is_quarterly),
                    "연간": sum(1 for f in facts if f.is_annual),
                }
                print(f"    ✓ {key:<16} {tag:<52} {len(facts)}건 {kinds}")
            except edgar_xbrl.XbrlError as exc:
                collected[key] = []
                print(f"    ✗ {key:<16} 전부 실패 — {str(exc)[:80]}")

        if not collected.get("inventory") or not collected.get("cost_of_sales"):
            print("\n  재고·매출원가가 없어 DIO 를 계산할 수 없습니다.")
            continue

        trend = cycle.build_trend_from_xbrl(
            ticker, ticker,
            collected["inventory"], collected["cost_of_sales"],
            collected.get("revenue") or [],
            quarters=config.CYCLE_XBRL_QUARTERS,
        )
        print(f"\n  [DIO 계산] ← 질문: 기간 처리가 맞나? / 공시값과 얼마나 다른가?")
        print(f"    {'보고서':<14}{'재고($M)':>12}{'매출원가($M)':>14}"
              f"{'기간':>7}{'DIO':>9}{'91일가정':>10}")
        for q in trend.quarters:
            dio = f"{q.dio:.0f}일" if q.dio is not None else (
                f"{q.dio_raw:.0f}✗" if q.dio_raw else "—")
            alt = (f"{q.inventory / q.cost_of_sales * 91:.0f}일"
                   if q.inventory and q.cost_of_sales else "—")
            print(f"    {q.label:<14}{(q.inventory or 0) / 1e6:>12,.0f}"
                  f"{(q.cost_of_sales or 0) / 1e6:>14,.0f}"
                  f"{q.period_days:>7.0f}{dio:>9}{alt:>10}")

        band = trend.dio_band
        if band:
            print(f"\n    밴드 {band[0]:.0f}~{band[2]:.0f}일 (중간 {band[1]:.0f}) · "
                  f"위치 {trend.dio_position:.0f}%")
        print(f"    연속 상승 {trend.dio_rising_quarters}분기", end="")
        if trend.dio_qoq_change is not None:
            print(f" · QoQ {trend.dio_qoq_change:+.1f}일", end="")
        if trend.inventory_revenue_gap is not None:
            print(f" · 재고-매출 갭 {trend.inventory_revenue_gap:+.1f}%p", end="")
        print()
        for w in trend.dio_warnings:
            print(f"    경고: {w}")
        if trend.all_missing:
            print(f"    못 찾은 계정: {', '.join(trend.all_missing)}")

        # 재고 구성 시도
        print(f"\n  [재고 구성] ← 질문: 원재료·재공품·완제품이 있나?")
        for key in ("raw_materials", "work_in_progress", "finished_goods"):
            facts = collected.get(key) or []
            if facts:
                latest = max(facts, key=lambda f: f.end)
                print(f"    ✓ {key:<18} {latest.end} = ${latest.val / 1e6:,.0f}M "
                      f"({latest.tag})")
            else:
                print(f"    ✗ {key:<18} 보고하지 않음")


# ──────────────────────────────────────────────────────────────────────────────
# FRED
# ──────────────────────────────────────────────────────────────────────────────

def diagnose_fred() -> None:
    head("FRED 매크로 계열 — 키가 있으면 공식 API, 없으면 CSV")

    specs = config.macro_series()
    unverified = [s for s in specs if not s.verified]
    print(f"계열 {len(specs)}개 · 이 중 제가 확인하지 못한 것 {len(unverified)}개")
    if unverified:
        print("미검증: " + ", ".join(s.series_id for s in unverified))
    print("\n틀린 계열 ID 는 404 로 조용히 비어 보입니다. 그래서 하나씩 확인합니다.\n")

    # ── 연결 자체를 먼저 시험합니다 ────────────────────────────────────────
    # 계열 14개가 전부 같은 오류로 실패하면 계열 ID 문제가 아니라 **연결**
    # 문제입니다. 그때 ID 목록을 14줄 찍는 건 아무 도움이 안 됩니다.
    import time as _t

    import requests as _rq

    print("  [연결 시험] fred.stlouisfed.org 에 닿는가")
    probe_ok = False
    _fred_key = fred.api_key()
    _probes = [
        ("CSV (키 불필요)", fred.CSV_URL, {"id": "DGS10"}),
        ("일반 페이지", "https://fred.stlouisfed.org/series/DGS10", None),
    ]
    if _fred_key:
        _probes.append((
            "공식 API (키 사용)", fred.API_URL,
            {"series_id": "DGS10", "api_key": _fred_key, "file_type": "json",
             "limit": "1"}))
    else:
        print("    · FRED_API_KEY 가 없습니다. CSV 경로가 막혀 있다면 "
              "무료 키를 발급해 Secrets 에 넣으면 다른 호스트로 받아옵니다:")
        print("      https://fred.stlouisfed.org/docs/api/api_key.html")

    # 키 형식을 **보내기 전에** 확인합니다. 형식이 틀리면 서버가 400 을
    # 주는데, 상태코드만 보고는 왜인지 알 수 없습니다.
    _kp = fred.key_problem()
    if _fred_key and _kp:
        print(f"    ⚠ {_kp}")
        print("      Secrets 에 따옴표 안쪽만 키여야 합니다: "
              'FRED_API_KEY = "abcd…32자"')

    for label, url, params in _probes:
        t0 = _t.monotonic()
        try:
            r = _rq.get(url, params=params, timeout=fred.TIMEOUT,
                        headers={"User-Agent": "stock-dashboard/1.0"})
            el = _t.monotonic() - t0
            print(f"    {'✓' if r.status_code == 200 else '✗'} {label}: "
                  f"HTTP {r.status_code} · {el:.1f}초 · {len(r.content):,} bytes")
            # 주소에 api_key 가 들어가므로 URL 은 찍지 않습니다.
            if r.status_code != 200:
                # **본문을 찍습니다.** 전에 상태코드만 보여줘서 400 의 사유가
                # 응답 안에 있는데도 보이지 않았습니다. FRED API 는 400 과
                # 함께 error_message 를 돌려줍니다.
                body = r.text.strip()
                if _fred_key:
                    body = body.replace(_fred_key, "…키가려짐…")
                for chunk in textwrap.wrap(body, 92)[:6]:
                    print(f"        {chunk}")
            if r.status_code == 200:
                probe_ok = True
                if params:
                    print(f"        첫 줄: {r.text.splitlines()[0][:70]}")
        except Exception as exc:  # noqa: BLE001
            el = _t.monotonic() - t0
            print(f"    ✗ {label}: {el:.1f}초 만에 실패")
            msg = f"{type(exc).__name__}: {exc}"
            if _fred_key:
                msg = msg.replace(_fred_key, "…키가려짐…")
            for chunk in textwrap.wrap(msg, 92):
                print(f"        {chunk}")

    if not probe_ok:
        print()
        print("    둘 다 실패했다면 이 서버에서 FRED 로 나가는 길이 막힌 것입니다.")
        print("    계열 ID 는 문제가 아니니 아래 목록은 참고만 하십시오.")
    print(f"    (타임아웃 {fred.TIMEOUT}초 · 실패 시 {fred.RETRIES}회 재시도)")
    print()

    # 공포탐욕지수 — CNN 내부 엔드포인트라 따로 확인합니다
    print("\n  [공포탐욕지수] ← CNN 내부 엔드포인트가 아직 열려 있나?")
    fg = feargreed.fetch()
    if fg.ok:
        print(f"    ✓ {fg.score:.0f} ({fg.band}) · 관측 {fg.observed_at} · "
              f"세부 지표 {len(fg.components)}개 · 이력 {len(fg.history)}일")
        print(f"      CNN 공식 페이지와 대조: {feargreed.CNN_PAGE}")
        for comp in fg.components:
            value = "없음" if comp.score is None else f"{comp.score:5.0f}"
            print(f"        {comp.label:<14}{value}  {comp.band}")
        # 구조가 바뀌었는지 알려면 실제 키를 봐야 합니다
        print(f"      응답 최상위 키: {', '.join(fg.raw_keys)}")
        print(f"      fear_and_greed 키: {', '.join(fg.root_keys)}")
        missing = [n for n, v in (
            ("previous_close", fg.previous_close),
            ("previous_1_week", fg.previous_week),
            ("previous_1_month", fg.previous_month),
            ("previous_1_year", fg.previous_year),
        ) if v is None]
        if missing:
            print(f"      ⚠ 못 읽은 비교값: {', '.join(missing)} "
                  "— 키 이름이 바뀌었을 수 있습니다")
        if fg.observed_at is None:
            print("      ⚠ 관측일을 못 읽었습니다 — timestamp 형식이 "
                  "바뀌었을 수 있습니다")
        elif fg.lag_days and fg.lag_days > 5:
            print(f"      ⚠ 관측일이 {fg.lag_days}일 전입니다 — "
                  "타임스탬프 해석이 틀렸을 수 있습니다")
    else:
        print(f"    ✗ {fg.error[:90]}")
        print("      (공개 API 가 아니라 막힐 수 있습니다. 다른 지표에는 영향 없습니다.)")
        print(f"      대조용 공식 페이지: {feargreed.CNN_PAGE}")

    series_map, errors = fred.fetch_many(
        config.macro_series_ids(), years=config.MACRO_SERIES_YEARS)

    print(f"  {'계열':<13}{'확인':<6}{'관측수':>7}{'결측':>6}"
          f"{'최신 관측':>12}{'지연':>7}  지표명")
    print("  " + "-" * 86)
    for spec in specs:
        series = series_map.get(spec.series_id)
        if series is None:
            mark = "✗"
            print(f"  {spec.series_id:<13}{mark:<6}{'—':>7}{'—':>6}{'—':>12}{'—':>7}  "
                  f"{spec.name}")
            # **자르지 않습니다.** 전에 78자에서 잘라서
            # "HTTPSConnectionPool(host='fred.stlouisfed.org', port=443):"
            # 까지만 보이고 진짜 사유(타임아웃인지 차단인지 SSL 인지)가
            # 잘려 나갔습니다. 진단의 존재 이유가 사라집니다.
            _why = errors.get(spec.series_id, "사유 불명")
            for _i, _chunk in enumerate(textwrap.wrap(_why, 96) or [_why]):
                print(f"      {'→' if _i == 0 else ' '} {_chunk}")
            continue
        was = "기존✓" if spec.verified else "신규✓"
        latest = series.latest
        lag = series.lag_days
        print(f"  {spec.series_id:<15} {was:<6}{len(series.observations):>7}"
              f"{series.missing_count:>6}{latest.date.isoformat():>12}"
              f"{str(lag) + '일':>7}  {spec.name}")
        _gaps = series.gap_months()
        if _gaps:
            print(f"      ↳ 중간에 빠진 달: {', '.join(_gaps)} — 이 달이 기준이 "
                  "되는 전년대비는 계산하지 않습니다")

    # 표시값·신호까지 한 번 돌려봅니다
    readings = macro_mod.build_readings(specs, series_map, errors)
    print(f"\n  [표시값] ← mode 가 맞는지, 전년대비가 산출되는지")
    for r in readings:
        if r.ok:
            extra = ""
            if r.spec.mode == "yoy":
                extra = f"  (전년대비 {len(r.history)}포인트)"
            print(f"    {r.spec.name[:26]:<28}{r.value_label:>12}"
                  f"  관측 {r.observed_label}{extra}")
            if r.warning:
                print(f"        ⚠ {r.warning}")
        else:
            print(f"    {r.spec.name[:26]:<28}{'ERROR':>12}  {r.error[:46]}")

    triggers = macro_mod.evaluate_all(readings)
    print(f"\n  [임계값 판정] {len(triggers)}건 ← 0건이면 조용한 게 정상입니다")
    for t in triggers:
        print(f"    [{t.severity}] {t.title}")
        print(f"          {t.detail}")

    stale = [r for r in readings if r.stale]
    if stale:
        print(f"\n  [발표 지연 경고] {len(stale)}건")
        for r in stale:
            print(f"    {r.spec.name} — {r.lag_days}일 전 관측 "
                  f"(통상 주기 {r.spec.period_days}일)")

    print("\n  ※ '신규✓' 로 나온 계열은 config.py 의 MacroSeries 에서")
    print("     verified=True 로 바꿔 두시면 화면의 '미검증' 표시가 사라집니다.")


# ──────────────────────────────────────────────────────────────────────────────
# 스크리너
# ──────────────────────────────────────────────────────────────────────────────

def diagnose_screen(limit: int = 8) -> None:
    head(f"버핏식 스크리너 — companyfacts (키 불필요, 앞 {limit}개만)")

    ua = config.EDGAR_USER_AGENT
    if "your-email" in ua or "example.com" in ua:
        print("  ⚠ config.py 의 EDGAR_USER_AGENT 에 본인 연락처를 넣으십시오.")

    tickers = config.screen_tickers()[:limit]
    print(f"전체 대상 {len(config.screen_tickers())}개 중 {len(tickers)}개만 확인합니다")
    print("(전체를 돌리려면 앱의 종목 발굴 탭을 쓰십시오 — 결과가 캐시됩니다)\n")

    try:
        ticker_map = edgar.fetch_ticker_map(ua)
    except Exception as exc:  # noqa: BLE001
        print(f"티커 매핑 실패: {exc}")
        return

    ciks = {}
    for ticker in tickers:
        cik = (config.EDGAR_CIK_OVERRIDES.get(ticker)
               or ticker_map.get(ticker.upper())
               or ticker_map.get(ticker.upper().replace(".", "-")))
        if cik is None:
            print(f"  ✗ {ticker:<8} CIK 를 찾지 못했습니다")
            continue
        ciks[ticker] = cik

    facts_map, errors = edgar_facts.fetch_many(
        ciks, ua, keep=buffett.KEEP_TAGS)
    th = config.screen_thresholds()

    print(f"  {'티커':<8}{'연도':>5}{'통과':>7}{'불가':>5}  못 찾은 계정")
    print("  " + "-" * 74)
    for ticker in tickers:
        facts = facts_map.get(ticker)
        if facts is None:
            print(f"  {ticker:<8}  ✗  {errors.get(ticker, '사유 불명')[:58]}")
            continue
        screen = buffett.screen_company(
            ticker, facts, years=config.SCREEN_YEARS, th=th)
        if not screen.ok:
            print(f"  {ticker:<8}  ✗  {screen.error[:58]}")
            continue
        miss = ", ".join(screen.missing_tags) if screen.missing_tags else "—"
        print(f"  {ticker:<8}{screen.year_count:>5}{screen.score_label:>7}"
              f"{screen.unknown_count:>5}  {miss[:40]}")
        for c in screen.checks:
            mark = {"pass": "○", "fail": "✗", "unknown": "?"}[c.verdict]
            print(f"      {mark} {c.criterion.name[:24]:<26}{c.value_label:>11}"
                  f"  {c.detail[:46]}")
            if c.warning:
                print(f"          ⚠ {c.warning[:70]}")

    print("\n  ※ '못 찾은 계정' 이 많으면 buffett.TAGS 의 태그 후보를 늘려야 합니다.")
    print("     '판정 불가' 는 탈락이 아닙니다 — 데이터가 없는 것입니다.")


def main(argv: list[str]) -> int:
    only_dart = "--dart" in argv
    only_xbrl = "--xbrl" in argv
    only_fred = "--fred" in argv
    only_screen = "--screen" in argv
    only_codes = "--codes" in argv
    picked = (only_dart or only_xbrl or only_fred or only_screen
              or only_codes)

    print(LINE)
    print("주식 대시보드 진단 리포트")
    print("이 출력을 그대로 복사해 Claude 에 붙여넣으면 결과에 맞춰 고칠 수 있습니다.")
    print("인증키는 포함되지 않습니다 (끝 4자리만).")
    print(LINE)

    if only_dart or not picked:
        try:
            diagnose_dart()
        except Exception as exc:  # noqa: BLE001
            print(f"\nDART 진단 중 예외: {type(exc).__name__}: {exc}")

    if only_xbrl or not picked:
        try:
            diagnose_xbrl()
        except Exception as exc:  # noqa: BLE001
            print(f"\nXBRL 진단 중 예외: {type(exc).__name__}: {exc}")

    if only_fred or not picked:
        try:
            diagnose_fred()
        except Exception as exc:  # noqa: BLE001
            print(f"\nFRED 진단 중 예외: {type(exc).__name__}: {exc}")

    if only_screen or not picked:
        try:
            diagnose_screen()
        except Exception as exc:  # noqa: BLE001
            print(f"\n스크리너 진단 중 예외: {type(exc).__name__}: {exc}")

    if only_fred or not picked:
        try:
            diagnose_fred_extra()
        except Exception as exc:  # noqa: BLE001
            print(f"\n추가 계열 진단 중 예외: {type(exc).__name__}: {exc}")

    if only_codes or not picked:
        try:
            diagnose_kr_codes()
        except Exception as exc:  # noqa: BLE001
            print(f"\n종목코드 대조 중 예외: {type(exc).__name__}: {exc}")

    head("진단 완료")
    print("확인해야 할 것:")
    print("  1. 재고 구성 계정이 있나 → 있으면 체크리스트 3번째 항목이 살아납니다")
    print("  2. DIO 가 5~400일 범위인가 → 벗어나면 기간 처리를 고쳐야 합니다")
    print("  3. 어느 태그/계정명이 실제로 쓰이나 → 후보 목록 순서를 조정합니다")
    print("  4. MU 계산 DIO vs 91일 가정 → 공시값과 어느 쪽이 가까운지")
    print("  5. FRED '신규✓' 계열 → config.py 에서 verified=True 로 바꾸십시오")
    print("     '✗' 계열 → ID 가 틀렸습니다. fred.stlouisfed.org 에서 찾아 고치십시오")
    print("  6. 스크리너 '못 찾은 계정' → buffett.TAGS 의 태그 후보를 늘려야 합니다")
    print("  7. 종목코드 '✗ 불일치' → config.py 의 그 줄이 다른 회사를 가리킵니다")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def diagnose_kr_exports() -> None:
    """한국 반도체 수출 — 산업통상부 보도자료 긁기가 실제로 되는지.

    이 경로는 **한 번도 실제로 성공한 적이 없습니다.** 개발 환경에서
    motir.go.kr 요청이 막혀 확인할 수 없었습니다. 배포한 앱에서도 막히면
    쓰지 마십시오 — 출력을 보고 판단하시면 됩니다.
    """
    from sources import kr_exports as kx

    print("한국 반도체 수출 (산업통상부 보도자료)")
    print(f"목록 주소: {kx.BOARD_URL}")
    print("-" * 56)
    try:
        res = kx.fetch_latest()
    except kx.ExportsError as exc:
        print(f"실패: {exc}")
        print()
        print("이 경로가 막혀 있다면 쓰지 않는 게 맞습니다.")
        print("대안: 관세청 OpenAPI(data.go.kr 인증키 필요) 또는")
        print("      다른 대시보드의 수출입 레이더를 보십시오.")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"예상치 못한 오류: {type(exc).__name__}: {exc}")
        return

    print(f"제목   : {res.title}")
    print(f"주소   : {res.source_url}")
    print(f"기준월 : {res.period or '못 찾음'}")
    print(f"금액   : {res.value_100m_usd} 억 달러"
          if res.value_100m_usd is not None else "금액   : 못 찾음")
    print(f"전년비 : {res.yoy_pct}%" if res.yoy_pct is not None
          else "전년비 : 못 찾음")
    print(f"패턴   : {res.matched or '없음'}")
    for w in res.warnings:
        print(f"경고   : {w}")
    print()
    print("성공했다면 이 출력을 Claude 에 붙여넣어 주십시오 —")
    print("실제 응답을 보고 파서를 맞출 수 있습니다.")


def diagnose_kr_codes() -> None:
    """국내 종목코드가 실제로 그 회사인지 DART 로 대조합니다.

    **왜 필요한가.** config.py 의 6자리 코드는 사람이 손으로 적은
    것입니다. 한 자리만 틀려도 *존재하는 다른 회사*의 재무를 가져오는데,
    화면에는 아무 이상이 없어 보입니다. 조용히 틀린 숫자가 제일 나쁩니다.
    DART 의 corpCode.xml 에 실제 회사명이 들어 있으니 기계가 맞춰봅니다.
    """
    import config
    from sources import dart

    print("[국내 종목코드 대조]")
    ok, why = dart.key_status()
    if not ok:
        print(f"  건너뜀 — {why}")
        return
    try:
        corp_map = dart.fetch_corp_codes()
    except Exception as exc:  # noqa: BLE001
        print(f"  corpCode.xml 을 받지 못했습니다: {type(exc).__name__}: {exc}")
        return
    print(f"  DART 매핑 {len(corp_map):,}건 수신")

    #: 같은 회사인데 화면에서는 줄여 부르는 이름 → DART 의 법인 등기명.
    #: 2026-11-11 진단에서 나온 4건 — 코드는 맞고 이름 표기만 다릅니다.
    aliases = {"현대차": "현대자동차", "한국전력": "한국전력공사",
               "kt": "케이티", "kt&g": "케이티앤지"}

    def norm(text: str) -> str:
        """비교용 정규화 — 공백·점·㈜ 같은 장식을 뺍니다."""
        out = (text or "").strip().lower()
        for junk in (" ", ".", "(주)", "㈜", "주식회사", "㈐", "-"):
            out = out.replace(junk, "")
        return out

    rows = list(config.screen_kr_candidates())
    kq = config.kosdaq_codes()
    bad, missing, good = [], [], 0
    for code, name in rows:
        entry = corp_map.get(code)
        if not entry:
            missing.append((code, name))
            continue
        real = entry.get("corp_name", "")
        if norm(real) == norm(name) or norm(real) == norm(aliases.get(norm(name), "")):
            good += 1
        else:
            bad.append((code, name, real, "코스닥" if code in kq else "코스피"))

    print(f"  일치 {good} · 불일치 {len(bad)} · DART 에 없음 {len(missing)}"
          f"  (전체 {len(rows)})")
    for code, name, real, mkt in bad:
        print(f"  ✗ {code} [{mkt}] config='{name}'  ←→  DART='{real}'")
    for code, name in missing:
        print(f"  ? {code} config='{name}' — DART 매핑에 없습니다 "
              "(상장폐지·코드 오타·비상장)")
    if bad:
        print("  → config.py 의 SCREEN_KR_CANDIDATES / SCREEN_KQ_CANDIDATES "
              "에서 해당 줄을 DART 쪽 이름·코드로 고치십시오.")
    elif not missing:
        print("  → 전부 일치합니다. 코드 목록을 신뢰해도 됩니다.")


def diagnose_fred_key() -> None:
    """FRED 키 하나만 집중해서 봅니다 — 형식 → 연결 → 실제 호출.

    `diagnose_fred` 는 계열 14개를 전부 돌려 길고, 키가 문제일 때는
    같은 실패가 14번 반복됩니다. 여기서는 **한 계열(DGS10)만** 불러서
    키가 되는지 아닌지 한 줄로 답합니다.
    """
    import requests

    from sources import fred

    print("[FRED 키 확인]")
    key = fred.api_key()
    print(f"  출처: {fred.key_source()}")
    if not key:
        print("  키가 없습니다. 무료 발급(즉시): "
              "https://fred.stlouisfed.org/docs/api/api_key.html")
        print("  발급 후 Streamlit Secrets 에 **최상위 레벨**로 넣으십시오:")
        print('    FRED_API_KEY = "여기에32자"')
        print("  [section] 아래에 넣으면 환경변수가 되지 않습니다.")
        return
    print(f"  길이 {len(key)}자 · 끝 4자리 …{key[-4:]}")
    problem = fred.key_problem()
    if problem:
        print("  ✗ 형식 문제:")
        for line in textwrap.wrap(problem, width=72):
            print(f"      {line}")
        # 무엇이 들어 있는지 **가린 채로** 모양만 보여줍니다. 길이만으로는
        # 어디가 잘렸는지 감이 안 옵니다.
        shape = "".join("9" if c.isdigit() else
                        ("a" if c.islower() else
                         ("A" if c.isupper() else "·")) for c in key)
        print(f"      모양: {shape}  (a=소문자 9=숫자 A=대문자 ·=기타)")
        print("      정상: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (32칸, "
              "소문자·숫자만)")
        print("  → 발급 페이지: https://fredaccount.stlouisfed.org/apikeys")
        return
    print("  ✓ 형식은 정상입니다 (소문자 영숫자 32자)")

    print("\n  공식 API 로 DGS10 한 계열만 받아봅니다…")
    try:
        resp = requests.get(
            fred.API_URL,
            params={"series_id": "DGS10", "api_key": key,
                    "file_type": "json", "limit": "3",
                    "sort_order": "desc"},
            timeout=fred.API_TIMEOUT,
            headers={"User-Agent": "stock-dashboard/1.0"},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 연결 실패: {type(exc).__name__}: {exc}")
        print("  → api.stlouisfed.org 로 나가는 길이 막혀 있습니다. "
              "키 문제가 아닙니다.")
        return

    print(f"  HTTP {resp.status_code} · {len(resp.content)} bytes")
    if resp.status_code != 200:
        body = resp.text.replace(key, "…" + key[-4:])
        print("  ✗ 응답 본문:")
        for line in textwrap.wrap(body[:600], width=76):
            print(f"      {line}")
        print("  → 위 문장이 사유입니다. 'Bad Request. The value for "
              "variable api_key is not registered' 면 키가 아직 "
              "활성화되지 않았거나 오타입니다.")
        return

    try:
        obs = resp.json().get("observations", [])
    except ValueError:
        print("  ✗ JSON 으로 읽을 수 없습니다.")
        return
    print(f"  ✓ 관측치 {len(obs)}건 수신")
    for row in obs[:3]:
        print(f"      {row.get('date')}  {row.get('value')}")
    print("  → 키가 정상 동작합니다. 매크로·물가·유동성이 모두 "
          "채워져야 합니다. 그래도 비면 화면 위쪽 '캐시 비우고 다시 "
          "불러오기' 를 누르십시오.")


def diagnose_fred_extra() -> None:
    """매크로 14계열 **밖의** FRED 계열 — 물가·유동성·한국.

    `diagnose_fred` 는 MACRO_SERIES 만 봅니다. 2026-11-11 에 물가 6 ·
    유동성 6 · 한국 6 계열을 새로 넣었는데 그쪽은 확인할 길이 없었습니다.

    **유동성은 단위까지 봅니다.** FRED 는 WALCL 을 백만 달러로,
    역레포·TGA 를 십억 달러로 줍니다. 그냥 빼면 1000배 틀린 숫자가
    나오는데 화면에는 그럴듯해 보입니다. 받은 값의 크기를 찍어서
    config 에 적은 단위가 맞는지 눈으로 확인하게 합니다.
    """
    import config
    from sources import fred

    print("[FRED 추가 계열 — 물가 · 유동성 · 한국]")
    if not fred.api_key():
        print("  건너뜀 — FRED_API_KEY 가 없습니다.")
        return

    groups = [
        ("물가", [(sid, label) for sid, label, _sa
                 in config.INFLATION_SERIES]),
        ("유동성(순유동성 계산에 쓰임)",
         [(sid, label) for _k, sid, label, _u in config.LIQUIDITY_SERIES]),
        ("유동성(참고)",
         [(row[0], row[1]) for row in config.LIQUIDITY_EXTRA]),
        ("한국", list(config.KR_MACRO_SERIES)),
    ]
    units = {sid: u for _k, sid, _l, u in config.LIQUIDITY_SERIES}
    units.update({row[0]: row[2] for row in config.LIQUIDITY_EXTRA})
    ranges = {k: None for k, _s, _l, _u in config.LIQUIDITY_SERIES}
    ranges.update({row[0]: (row[4], row[5]) for row in config.LIQUIDITY_EXTRA})

    ok_ids, bad_ids = [], []
    for title, items in groups:
        print(f"\n  ── {title} ──")
        ids = [sid for sid, _l in items]
        series, errors = fred.fetch_many(ids, years=3)
        for sid, label in items:
            ser = series.get(sid)
            if ser is None or not ser.observations:
                why = (errors.get(sid) or "관측치 없음")
                bad_ids.append(sid)
                print(f"  ✗ {sid:18s} {label}")
                for line in textwrap.wrap(why, width=66):
                    print(f"       {line}")
                continue
            ok_ids.append(sid)
            last = ser.observations[-1]
            extra = ""
            if sid in units:
                scaled = _to_billions(last.value, units[sid])
                extra = (f"  →  {scaled:,.0f}십억 "
                         f"(config 단위 '{units[sid]}')")
                rng = ranges.get(sid)
                if rng and not (rng[0] <= scaled <= rng[1]):
                    fits = [n for n, m in
                            (("billions", 1.0), ("millions", 1e-3),
                             ("hundred_millions", 0.1),
                             ("thousands", 1e-6), ("units", 1e-9))
                            if rng[0] <= last.value * m <= rng[1]]
                    extra += ("  ✗ 범위 "
                              f"{rng[0]:,.0f}~{rng[1]:,.0f} 밖")
                    if fits:
                        extra += f" → '{fits[0]}' 이 맞습니다"
            print(f"  ✓ {sid:18s} {len(ser.observations):4d}개 · "
                  f"최신 {last.date} = {last.value:,.4g}{extra}")

    print("\n  [단위 점검] ← 숫자 크기가 말이 되는지 **눈으로** 보십시오")
    print("    연준 총자산(WALCL)  6,000~7,000십억 달러 근처여야 합니다")
    print("    역레포(RRPONTSYD)   0~1,000십억 달러")
    print("    재무부 계정(WTREGEN) 300~1,000십억 달러")
    print("    벗어나면 config.LIQUIDITY_SERIES 의 단위가 틀린 것입니다 —")
    print("    화면은 숫자를 내지 않고 '단위가 이상합니다' 라고 적습니다.")

    print(f"\n  정상 {len(ok_ids)} · 실패 {len(bad_ids)}")
    if bad_ids:
        print(f"  실패한 ID: {', '.join(bad_ids)}")
        print("  → config.py 에서 해당 줄을 지우거나 올바른 ID 로 "
              "고치십시오. 한국 계열은 OECD 경유라 중단된 것이 많습니다.")


def _to_billions(value: float, unit: str) -> float:
    return value * {"billions": 1.0, "millions": 0.001,
                    "thousands": 1e-6, "units": 1e-9}.get(unit, 1.0)


def diagnose_kr_sources() -> None:
    """국내 스크리너·밸류에이션의 데이터 출처가 이 서버에서 닿는지.

    2026-11-11: 한국 종목발굴 0건 + DART 고유번호 실패. 출처 셋을 한 번에
    봅니다 — 네이버 일봉, 네이버 투자지표, DART(작은 요청 → 큰 ZIP 순서).
    작은 요청은 되는데 ZIP 만 안 되면 '내려받기 시간' 문제, 둘 다 안
    되면 '연결 자체' 문제입니다.
    """
    import time as _t
    import requests as _rq
    from sources import naver as _nv

    head("국내 데이터 출처")
    code = "005930"

    t0 = _t.perf_counter()
    closes, vols, err = _nv.fetch_daily(code, 300)
    dt_ = _t.perf_counter() - t0
    if closes:
        print(f"네이버 일봉   ✓ {len(closes)}개 · 마지막 종가 {closes[-1]:,.0f} · "
              f"거래량 {vols[-1]:,.0f} · {dt_:.1f}초")
    else:
        print(f"네이버 일봉   ✗ {err} · {dt_:.1f}초")

    t0 = _t.perf_counter()
    val = _nv.fetch_valuation(code)
    dt_ = _t.perf_counter() - t0
    if not val.get("error"):
        print(f"네이버 지표   ✓ PER {val.get('per')} · PBR {val.get('pbr')} · "
              f"배당 {val.get('div_yield')}% · {dt_:.1f}초")
    else:
        print(f"네이버 지표   ✗ {val.get('error')} · {dt_:.1f}초")

    ok, msg = dart.key_status()
    print(f"\nDART 인증키: {msg}")
    if not ok:
        return
    # 작은 요청 — 공시 목록 1건
    t0 = _t.perf_counter()
    try:
        r = _rq.get(f"{dart.BASE}/list.json",
                    params={"crtfc_key": dart.api_key(), "page_count": 1},
                    timeout=(10, 20))
        print(f"DART 작은 요청 (list.json) ✓ HTTP {r.status_code} · "
              f"{_t.perf_counter() - t0:.1f}초")
    except Exception as exc:  # noqa: BLE001
        print(f"DART 작은 요청 (list.json) ✗ {dart._describe(exc)} · "
              f"{_t.perf_counter() - t0:.1f}초")
    # 큰 ZIP
    t0 = _t.perf_counter()
    try:
        m = dart._fetch_corp_codes_remote()
        print(f"DART 고유번호 ZIP          ✓ 상장사 {len(m):,}개 · "
              f"{_t.perf_counter() - t0:.1f}초")
        dart._write_corp_cache(m)
        print("  → 서버 임시 폴더에 저장했습니다 (7일 동안 다시 받지 않음)")
    except Exception as exc:  # noqa: BLE001
        print(f"DART 고유번호 ZIP          ✗ {exc} · "
              f"{_t.perf_counter() - t0:.1f}초")
        print("\n읽는 법: 작은 요청 ✓ + ZIP ✗ → 내려받기가 느린 것 (재시도·"
              "저장으로 완화). 둘 다 ✗ 이고 '연결 시간 초과' → 이 서버(미국)"
              "에서 DART 에 닿지 않는 것. 그 경우 국내 재무는 DART 대신 다른 "
              "출처가 필요합니다.")


def diagnose_filings() -> None:
    """시장 공시 — 유형 필터가 먹는지, 무엇이 분류되고 무엇이 빠지는지."""
    import collections as _co
    import datetime as _dt
    from sources import dart as _d

    head("시장 공시 (DART list.json · 유형별)")
    ok, why = _d.key_status()
    if not ok:
        print(f"  키 없음 — {why}")
        return
    today = _dt.date.today()
    begin = (today - _dt.timedelta(days=2)).strftime("%Y%m%d")
    for ty, name, _pages in _d.SCAN_PAGES:
        try:
            payload = _d._get("list.json", {
                "bgn_de": begin, "end_de": today.strftime("%Y%m%d"),
                "pblntf_ty": ty, "page_no": "1", "page_count": "100",
                "sort": "date", "sort_mth": "desc"})
        except Exception as exc:  # noqa: BLE001
            print(f"\n{name}({ty}): 실패 — {type(exc).__name__}: {exc}")
            continue
        rows = [r for r in (payload.get("list") or []) if isinstance(r, dict)]
        cls = _co.Counter(str(r.get("corp_cls") or "?") for r in rows)
        hit = _co.Counter()
        miss = _co.Counter()
        for r in rows:
            if str(r.get("corp_cls") or "") not in ("Y", "K"):
                continue
            t = str(r.get("report_nm") or "")
            k = _d.classify_detail(t)
            if k:
                hit[f"{k.group}/{k.label}"] += 1
            else:
                miss[t.split("(")[0].strip()[:30]] += 1
        print(f"\n{name}({ty}): 1쪽 {len(rows)}건 · 전체 "
              f"{payload.get('total_count', '?')}건 / {payload.get('total_page', '?')}쪽"
              f" · 시장 {dict(cls)}")
        print("  분류됨: " + (", ".join(f"{k} {n}" for k, n in hit.most_common(12))
                            or "없음"))
        print("  빠진 제목 상위 (이 중 봐야 할 게 있으면 알려 주십시오):")
        for t, n in miss.most_common(12):
            print(f"    {n:>3}  {t}")


def diagnose_kr_supply() -> None:
    """국내 수급(네이버 두 경로) · 분기 실적표 · 공매도/신용 단서."""
    import requests as _rq
    from sources import naver as _nv
    from sources import naver_extra as _nx

    head("국내 수급 · 분기 실적 (네이버)")
    code = "005930"
    try:
        r = _rq.get(_nx.TREND_URL.format(code=code), params={"pageSize": "5"},
                    headers=_nv.HEADERS, timeout=_nv.TIMEOUT)
        print(f"\n모바일 수급 JSON: HTTP {r.status_code} · {len(r.content):,} bytes")
        try:
            payload = r.json()
            rows = _nx._find_rows(payload)
            print(f"  수급 줄 {len(rows)}개 · 해석 {len(_nx.parse_trend_json(payload))}개")
            if rows:
                print("  첫 줄 키: " + ", ".join(
                    f"{k}={str(v)[:18]!r}" for k, v in list(rows[0].items())[:16]))
            else:
                print("  앞부분: " + repr(r.text[:400]))
        except ValueError:
            print("  JSON 아님 — 앞부분: " + repr(r.text[:300]))
    except Exception as exc:  # noqa: BLE001
        print(f"\n모바일 수급 JSON: 실패 — {type(exc).__name__}: {exc}")
    try:
        r = _rq.get(_nx.FRGN_URL, params={"code": code, "page": 1},
                    headers=_nx._HTML_HEADERS, timeout=_nv.TIMEOUT)
        if (r.encoding or "").lower() in ("", "iso-8859-1"):
            r.encoding = "euc-kr"
        got = _nx.parse_frgn_html(r.text)
        print(f"\nPC 수급 표: HTTP {r.status_code} · {len(r.content):,} bytes · "
              f"<tr> {r.text.count('<tr')}개 · 해석 {len(got)}줄")
        for g in got[:3]:
            print(f"  {g.date} 종가 {g.close} 거래량 {g.volume} 기관 {g.inst} "
                  f"외국인 {g.foreign} 보유율 {g.foreign_ratio}")
    except Exception as exc:  # noqa: BLE001
        print(f"\nPC 수급 표: 실패 — {type(exc).__name__}: {exc}")
    rows, src, err = _nx.fetch_flows(code, 25)
    print(f"\n최종: {len(rows)}일 · 출처 {src or '-'} · {err or '정상'}")

    periods, err = _nx.fetch_quarter(code)
    print(f"\n분기 실적표: {len(periods)}개 기간 · {err or '정상'}")
    for p in periods:
        vals = " · ".join(f"{k} {v}" for k, v in p.values.items())
        print(f"  {p.label:10s} {vals}")

    try:
        r = _rq.get(_nv.INTEGRATION_URL.format(code=code), headers=_nv.HEADERS,
                    timeout=_nv.TIMEOUT)
        text = r.text
        print(f"\n공매도·신용 단서 (integration): HTTP {r.status_code}")
        for word in ("credit", "Credit", "short", "Short", "신용", "공매도", "대차",
                     "foreignRate"):
            k = text.find(word)
            if k >= 0:
                print(f"  '{word}' 주변: {text[max(0, k - 80):k + 120]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n공매도·신용 단서: 실패 — {type(exc).__name__}: {exc}")


def diagnose_yahoo_events() -> None:
    """야후 배당 이력·배당 일정·실적(EPS 추정 vs 실제)."""
    from sources import yahoo_events as _ye

    head("야후 배당 · 실적")
    for sym in ("MSFT", "O", "005930.KS"):
        d = _ye.fetch_dividends(sym)
        hist = d["history"]
        print(f"\n{sym} 배당: {len(hist)}건 · 최근 {hist[-3:] if hist else '-'} · "
              f"다음 배당락 {d['ex_date'] or '-'} · 지급 {d['pay_date'] or '-'}"
              + (f" · 오류 {d['error']}" if d["error"] else ""))
    for sym in ("MSFT", "005930.KS"):
        e = _ye.fetch_earnings(sym)
        print(f"\n{sym} 실적: {len(e['rows'])}줄" + (f" · {e['error']}" if e["error"] else ""))
        for row in e["rows"][:5]:
            print(f"  {row}")


def diagnose_research_detail() -> None:
    """리서치 — 종목 리포트 목록과 상세(요약·목표가)가 어떤 모양으로 오는지.

    반도체 리포트 화면을 만들기 전에 **실제 응답**을 보려고 만든 것입니다.
    주소는 전부 추측입니다 — 되는 것과 그 모양을 찍습니다. 본문은 앞
    160자만 찍습니다 (구조 확인용).
    """
    import json as _json

    import requests as _rq
    from sources import research as _rs

    head("리서치 — 종목 리포트 · 상세")
    hdr = {**_rs.HEADERS, "Accept": "application/json"}
    base = "https://m.stock.naver.com"

    def show(value, limit=70):
        text = str(value).replace("\n", " ")
        return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"

    def call(url):
        try:
            r = _rq.get(url, headers=hdr, timeout=10)
        except Exception as exc:  # noqa: BLE001
            print(f"  {url}\n    → 실패 {type(exc).__name__}")
            return None
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            print(f"  {url}\n    → HTTP {r.status_code} · {len(r.content):,}B · JSON 아님: "
                  f"{r.text[:60]!r}")
            return None
        print(f"  {url}\n    → HTTP {r.status_code} · {len(r.content):,}B")
        return data

    def rows_of(data):
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            for key in ("result", "list", "data", "items", "researches", "contents"):
                got = rows_of(data.get(key))
                if got:
                    return got
            for val in data.values():
                got = rows_of(val) if isinstance(val, (list, dict)) else []
                if got:
                    return got
        return []

    first_ids: dict[str, str] = {}
    print("\n[목록]")
    lists = [
        ("industry", "/api/research/industry?pageSize=30&page=1"),
        ("industry", "/api/research/industry?pageSize=30&page=1&category=반도체"),
        ("industry", "/api/research/industry?pageSize=30&page=1&keyword=반도체"),
        ("company", "/api/research/company?pageSize=30&page=1"),
        ("company", "/api/research/company?pageSize=30&page=1&itemCode=005930"),
        ("company", "/api/research/company?pageSize=30&page=1&code=005930"),
        ("company", "/api/research/company?pageSize=30&page=1&stockCode=005930"),
        ("company", "/api/research/company?pageSize=30&page=1&keyword=삼성전자"),
        ("company", "/front-api/research/list?category=company&pageSize=30&page=1&itemCode=005930"),
        ("company", "/api/stock/005930/research?pageSize=20&page=1"),
        ("stock", "/api/research/stock/005930?pageSize=20&page=1"),
        ("stock", "/api/research/stock/000660?pageSize=20&page=2"),
        ("industry", "/api/research/industry?pageSize=30&page=4"),
    ]
    for kind, path in lists:
        data = call(base + path)
        rows = rows_of(data)
        if not rows:
            if isinstance(data, dict):
                print(f"    키 {list(data)[:8]} · 줄 없음")
            continue
        cats: dict[str, int] = {}
        for row in rows:
            tag = str(row.get("category") or row.get("stockName") or row.get("itemName")
                      or row.get("itemCode") or "?")
            cats[tag] = cats.get(tag, 0) + 1
        top = sorted(cats.items(), key=lambda kv: -kv[1])[:6]
        print(f"    {len(rows)}줄 · 분포 {top}")
        print("    첫 줄: " + ", ".join(f"{k}={show(v, 40)!r}" for k, v in rows[0].items()))
        if kind == "stock":
            print(f"    날짜 범위 {rows[-1].get('writeDate')} ~ {rows[0].get('writeDate')}")
            for row in rows[:3]:
                print("    미리보기: " + show(row.get("previewContent"), 220))
        first_ids.setdefault(kind, str(rows[0].get("researchId") or rows[0].get("id")
                                       or rows[0].get("nid") or ""))

    print("\n[상세]")
    first_ids.setdefault("company", first_ids.get("stock", ""))
    if first_ids.get("stock"):
        first_ids["company"] = first_ids["stock"]      # 삼성전자 리포트의 상세를 봅니다
    for kind in ("industry", "company"):
        rid = first_ids.get(kind)
        if not rid:
            print(f"  {kind}: 목록에서 번호를 얻지 못해 건너뜁니다")
            continue
        for path in (f"/api/research/{kind}/{rid}",):
            data = call(base + path)
            if data is None:
                continue
            node = data
            if isinstance(node, dict) and isinstance(node.get("result"), dict):
                node = node["result"]
            if not isinstance(node, dict):
                print(f"    모양: {type(node).__name__}")
                continue
            for key, val in node.items():
                if isinstance(val, dict):
                    # 한 단계 더 — 칸 이름을 전부 봐야 해석기를 쓸 수 있습니다
                    print(f"    {key}: dict[{len(val)}]")
                    for k2, v2 in val.items():
                        size = f" (글자 {len(v2):,})" if isinstance(v2, str) and len(v2) > 90 else ""
                        print(f"      · {k2}{size}: {show(v2, 90)!r}")
                elif isinstance(val, list):
                    print(f"    {key}: list[{len(val)}] "
                          f"{show(_json.dumps(val[:1], ensure_ascii=False), 200)}")
                else:
                    print(f"    {key}: {show(val, 160)!r}")


def diagnose_universe_sources() -> None:
    """종목 발굴 후보의 출처 — S&P 500 목록과 네이버 시가총액 순위가 어떤 모양으로 오는지.

    2026-11-12 "근본 해결안" (손으로 고른 후보 → 규칙으로 정한 후보) 을 만들기
    전에 실제 응답을 보려고 만든 것입니다. 주소 일부는 추측입니다.
    """
    import json as _json
    import re as _re

    import requests as _rq
    from sources import naver as _nv

    head("후보 출처 — S&P 500 · 시가총액 순위")
    ua = {"User-Agent": "stock-dashboard/1.0 (personal dashboard)"}
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        r = _rq.get(url, headers=ua, timeout=15)
        text = r.text
        print(f"위키백과: HTTP {r.status_code} · {len(text):,}자 · constituents 표 "
              f"{'있음' if 'id=\"constituents\"' in text else '없음'}")
        i = text.find('id="constituents"')
        if i >= 0:
            body = text[i:text.find("</table>", i)]
            rows = _re.findall(r"<tr[^>]*>(.*?)</tr>", body, _re.S)
            print(f"  줄 {len(rows)}개")
            for row in rows[:3]:
                print("  줄:", _re.sub(r"\s+", " ", row)[:900])
    except Exception as exc:  # noqa: BLE001
        print(f"위키백과 실패: {type(exc).__name__}: {exc}")

    hdr = {**_nv.HEADERS, "Accept": "application/json"}

    def show(value, limit=90):
        t = str(value).replace("\n", " ")
        return t if len(t) <= limit else t[:limit] + "…"

    for u in (
        "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=3",
        "https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page=1&pageSize=3",
        "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=2&pageSize=100",
        "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=200",
        "https://m.stock.naver.com/api/index/KPI200/enrollStocks?page=1&pageSize=3",
        "https://m.stock.naver.com/api/index/KOSDAQ150/enrollStocks?page=1&pageSize=3",
        "https://m.stock.naver.com/api/stocks/marketValue/all?page=1&pageSize=3",
    ):
        try:
            r = _rq.get(u, headers=hdr, timeout=10)
        except Exception as exc:  # noqa: BLE001
            print(f"\n{u}\n  실패 {type(exc).__name__}")
            continue
        print(f"\n{u}\n  HTTP {r.status_code} · {len(r.content):,}B")
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            print(f"  JSON 아님: {r.text[:120]!r}")
            continue
        if isinstance(data, dict):
            print("  맨 위 칸:", {k: (f"list[{len(v)}]" if isinstance(v, list) else show(v, 40))
                               for k, v in data.items()})
            items = next((v for v in data.values() if isinstance(v, list) and v), [])
        else:
            items = data if isinstance(data, list) else []
            print(f"  list[{len(items)}]")
        for it in items[:2]:
            print("  항목:", show(_json.dumps(it, ensure_ascii=False), 1200))
        if len(items) > 3:
            kinds: dict = {}
            for it in items:
                k = (it.get("stockEndType"), it.get("stockType")) if isinstance(it, dict) else "?"
                kinds[k] = kinds.get(k, 0) + 1
            print("  종류별:", kinds, "· 마지막:", show(_json.dumps(items[-1], ensure_ascii=False), 200))


def ichimoku_trace(dates, highs, lows, closes, offsets=(25, 26)) -> list[str]:
    """일목 구름 계산을 줄글로 풉니다 — HTS 와 한 칸씩 맞춰 볼 수 있게.

    dates/highs/lows/closes: 오래된 것부터. 돌려주는 것은 찍을 줄들.
    '오늘 자리 구름' 은 offset 봉 전에 계산한 값입니다. 그 봉의 날짜와, 9·26·52봉
    구간의 최고가·최저가(와 그 날짜)를 적습니다.
    """
    n = len(closes)
    lines: list[str] = []

    def window(end: int, size: int):
        lo = end - size + 1
        if lo < 0 or end >= n:
            return None
        hh = max(range(lo, end + 1), key=lambda i: highs[i])
        ll = min(range(lo, end + 1), key=lambda i: lows[i])
        return hh, ll, (highs[hh] + lows[ll]) / 2.0

    def at(src: int):
        t, k, b = window(src, 9), window(src, 26), window(src, 52)
        if not (t and k and b):
            return None
        return t, k, b, (t[2] + k[2]) / 2.0, b[2]

    def name(a: float, b: float) -> str:
        return "양운" if a > b else ("음운" if a < b else "같음")

    lines.append(f"  봉 {n}개 · 마지막 봉 {dates[-1]} 고 {highs[-1]:,.0f} 저 {lows[-1]:,.0f} "
                 f"종 {closes[-1]:,.0f}")
    for off in offsets:
        src = n - 1 - off
        got = at(src)
        lines.append(f"  ── 오늘 자리 구름 (이동 {off}봉 → {dates[src] if src >= 0 else '?'} 봉에서 계산)")
        if not got:
            lines.append("     봉이 모자랍니다")
            continue
        t, k, b, sa, sb = got
        for label, w in (("전환선  9봉", t), ("기준선 26봉", k), ("선행2  52봉", b)):
            lines.append(f"     {label}: 최고 {highs[w[0]]:,.0f} ({dates[w[0]]}) · "
                         f"최저 {lows[w[1]]:,.0f} ({dates[w[1]]}) → 중간 {w[2]:,.0f}")
        lines.append(f"     선행스팬1 {sa:,.0f} · 선행스팬2 {sb:,.0f} → {name(sa, sb)}")
    got = at(n - 1)
    if got:
        t, k, b, sa, sb = got
        lines.append(f"  ── 앞 구름 끝 (오늘 {dates[-1]} 봉으로 계산)")
        for label, w in (("전환선  9봉", t), ("기준선 26봉", k), ("선행2  52봉", b)):
            lines.append(f"     {label}: 최고 {highs[w[0]]:,.0f} ({dates[w[0]]}) · "
                         f"최저 {lows[w[1]]:,.0f} ({dates[w[1]]}) → 중간 {w[2]:,.0f}")
        lines.append(f"     선행스팬1 {sa:,.0f} · 선행스팬2 {sb:,.0f} → {name(sa, sb)}")
    # 계산한 날짜별 구름 색 — 어디서 바뀌는지 (최근 60봉)
    lines.append("  ── 계산한 봉별 구름 (그 봉에서 계산한 값은 25~26봉 뒤 자리에 그려집니다)")
    prev, run_start = None, None
    for src in range(max(51, n - 60), n):
        got = at(src)
        if not got:
            continue
        cur = name(got[3], got[4])
        if cur != prev:
            if prev is not None:
                lines.append(f"     {dates[run_start]} ~ {dates[src - 1]} 계산분: {prev}")
            prev, run_start = cur, src
    if prev is not None:
        lines.append(f"     {dates[run_start]} ~ {dates[n - 1]} 계산분: {prev}")
    return lines


def diagnose_ichimoku() -> None:
    """일목 구름 — 삼성전자·SK하이닉스의 실제 일봉과 계산 과정을 찍습니다.

    HTS 와 양운/음운이 다르게 보일 때 어느 칸이 다른지 찾는 용도입니다.
    (HTS 에서 같은 날짜의 고가·저가, 선행스팬 값을 맞춰 보십시오.)
    """
    import re as _re

    import requests as _rq
    from sources import naver as _nv

    head("일목 구름 계산 확인")
    for code, label in (("005930", "삼성전자"), ("000660", "SK하이닉스")):
        print(f"\n{label} ({code})")
        try:
            resp = _rq.get(_nv.CHART_URL.format(code=code, count=300),
                           headers=_nv.HEADERS, timeout=_nv.TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"  네이버 일봉 실패: {type(exc).__name__}")
            continue
        dates, highs, lows, closes = [], [], [], []
        for raw in _re.findall(r'data="([^"]+)"', resp.text or ""):
            parts = raw.split("|")
            if len(parts) < 6:
                continue
            try:
                h, l, c = float(parts[2]), float(parts[3]), float(parts[4])
            except ValueError:
                continue
            if c <= 0:
                continue
            dates.append(f"{parts[0][4:6]}/{parts[0][6:8]}")
            highs.append(max(h if h > 0 else c, c))
            lows.append(min(l if l > 0 else c, c))
            closes.append(c)
        if len(closes) < 80:
            print(f"  봉이 {len(closes)}개뿐입니다")
            continue
        for line in ichimoku_trace(dates, highs, lows, closes):
            print(line)
        print("  ── 최근 80봉 (날짜 고가 저가 종가)")
        rows = [f"{d} {h:,.0f} {l:,.0f} {c:,.0f}"
                for d, h, l, c in zip(dates[-80:], highs[-80:], lows[-80:], closes[-80:])]
        for i in range(0, len(rows), 2):
            print("     " + "   |   ".join(rows[i:i + 2]))


def diagnose_research() -> None:
    """네이버 증권 리서치 목록 — 받아지는지, 줄이 제대로 읽히는지."""
    import requests as _rq
    from sources import research as _rs

    head("리서치 목록 (네이버 증권)")
    for kind, name in (("industry", "산업분석"), ("market", "시황정보")):
        url = _rs.BASE + _rs.LISTS[kind]
        try:
            r = _rq.get(url, params={"page": 1}, headers=_rs.HEADERS,
                        timeout=_rs.TIMEOUT)
            print(f"\n{name}: HTTP {r.status_code} · {len(r.content):,} bytes · "
                  f"encoding {r.encoding} / {r.apparent_encoding}")
            enc = (r.encoding or "").lower()
            if enc in ("", "iso-8859-1"):
                r.encoding = r.apparent_encoding or "euc-kr"
            items = _rs.parse_list(r.text, kind)
            print(f"  읽은 줄: {len(items)}건 · <tr> {r.text.count('<tr')}개 · "
                  f"'_read.naver' {r.text.count('_read.naver')}회 · "
                  f"'.pdf' {r.text.count('.pdf')}회")
            for it in items[:4]:
                print(f"  {it.date or '날짜?'} | {it.category or '-'} | "
                      f"{it.title[:36]} | {it.broker or '증권사?'} | "
                      f"{'PDF' if it.pdf else 'PDF 없음'}")
            if not items:
                nxt = _rs.parse_next(r.text, kind)
                text = _rs.next_text(r.text)
                print(f"  Next.js 조각: __NEXT_DATA__ "
                      f"{'있음' if '__NEXT_DATA__' in r.text else '없음'} · "
                      f"__next_f {r.text.count('__next_f.push')}개 · 풀어낸 글자 "
                      f"{len(text):,} · 리포트처럼 생긴 객체 {len(nxt)}건")
                for it in nxt[:4]:
                    print(f"  {it.date or '날짜?'} | {it.category or '-'} | "
                          f"{it.title[:36]} | {it.broker or '증권사?'} | "
                          f"{'PDF' if it.pdf else 'PDF 없음'}")
                # 첫 후보 객체의 키 — 필드 이름을 정확히 맞추는 데 씁니다
                shown = 0
                for obj in _rs._objects(text, limit=1500):
                    for dd in _rs._walk_dicts(obj):
                        if _rs.report_like(dd) and shown < 2:
                            shown += 1
                            print("  [후보 객체] " + ", ".join(
                                f"{k}={str(v)[:40]!r}" for k, v in list(dd.items())[:14]))
                if not nxt:
                    print("  → 페이지 안에 목록이 없습니다 (브라우저가 따로 받아 옴). "
                          "데이터 주소를 찾습니다.")
                    urls = _rs.script_urls(r.text)
                    print(f"  자바스크립트 묶음 {len(urls)}개")
                    try:
                        found = _rs.discover(r.text)
                    except Exception as exc:  # noqa: BLE001
                        found = []
                        print(f"  묶음 받기 실패 — {type(exc).__name__}: {exc}")
                    lits = list(dict.fromkeys(lit for lit, _f in found))
                    print(f"  'research' 가 든 주소 모양 글자 {len(lits)}개:")
                    for lit in lits[:40]:
                        src = next(f for li, f in found if li == lit)
                        print(f"    {lit[:150]}    ← {src[:40]}")
                    print("  추측한 주소를 하나씩 불러 봅니다:")
                    import requests as _rq2
                    for alias in _rs.KIND_ALIASES.get(kind, (kind,)):
                        for tpl in _rs.API_CANDIDATES:
                            url = tpl.replace("{kind}", alias).replace("{page}", "1")
                            try:
                                rr = _rq2.get(url, headers={**_rs.HEADERS,
                                              "Accept": "application/json"},
                                              timeout=_rs.TIMEOUT)
                                line = f"HTTP {rr.status_code} · {len(rr.content):,}B"
                                if rr.ok:
                                    try:
                                        js = rr.json()
                                        got = _rs.reports_from_json(js, kind)
                                        top = (list(js)[:8] if isinstance(js, dict)
                                               else f"list[{len(js)}]")
                                        line += f" · JSON 키 {top} · 리포트 {len(got)}건"
                                        first = next((dd for dd in _rs._walk_dicts(js)
                                                      if _rs.report_like(dd)), None)
                                        if first:
                                            line += "\n        첫 객체: " + ", ".join(
                                                f"{k}={str(v)[:28]!r}"
                                                for k, v in list(first.items())[:14])
                                    except ValueError:
                                        line += " · JSON 아님: " + repr(rr.text[:80])
                            except Exception as exc:  # noqa: BLE001
                                line = f"실패 — {type(exc).__name__}"
                            print(f"    {url[:92]}\n      → {line}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n{name}: 요청 실패 — {type(exc).__name__}: {exc}")
