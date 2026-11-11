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
    head("FRED 매크로 계열 — 인증키 불필요")

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
        print(f"  {spec.series_id:<13}{was:<6}{len(series.observations):>7}"
              f"{series.missing_count:>6}{latest.date.isoformat():>12}"
              f"{str(lag) + '일':>7}  {spec.name}")

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
        if norm(real) == norm(name):
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
