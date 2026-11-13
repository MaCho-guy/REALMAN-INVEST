"""
아침 수집기 — 모든 화면의 데이터를 미리 받아 스냅샷 한 파일로 묶습니다.

    python stock_dashboard/tools/collect.py --out /tmp/seed

왜 있나. 대시보드는 화면을 **여는 순간에** 데이터를 받았습니다. 서버가
잠들었다 깨어난 아침에는 값이 하나도 없어 첫 화면이 가장 느렸습니다
(국내 재무 심사만 12.7초 — 2026-11-12 실측). 이 스크립트를 정해진 시각에
돌려(GitHub Actions) 결과를 저장소의 data 브랜치에 올려 두면, 앱은 깨어날
때 그 파일 하나를 읽어 바로 그립니다. 읽은 값은 '받은 시각' 이 그대로라
묵은 값으로 취급되고, 화면에 '몇 시간 전 값' 이라고 적힌 뒤 뒤에서 새로
받아 바뀝니다.

무엇을 받나. 앱이 화면마다 받는 것과 **같은 함수를 같은 인자로** 부릅니다
(app._section_jobs). 따로 목록을 두면 앱과 어긋나기 때문입니다.

안전장치.
  · 인증키가 섞인 항목은 버립니다. 실패 메시지에 요청 주소(키 포함)가
    들어갈 수 있고, 스냅샷은 **공개 저장소**에 올라갑니다.
  · 보유 종목(PORTFOLIO)은 여기에 없습니다 — Actions 에 넣지 않습니다.
  · 스트림릿 없이 돕니다 (가짜 모듈을 끼워 app.py 를 불러옵니다).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)

#: 이 환경변수들의 값이 스냅샷 어디에도 남으면 안 됩니다.
SECRET_ENVS = ("DART_API_KEY", "FRED_API_KEY", "ANTHROPIC_API_KEY", "EDGAR_USER_AGENT",
               "GITHUB_TOKEN", "PORTFOLIO")


class _Any:
    """무엇을 시켜도 조용히 넘어가는 가짜 — 스트림릿 호출 자리에 들어갑니다."""

    def __call__(self, *args, **kwargs):
        # @st.fragment / @st.cache_data 처럼 데코레이터로 쓰인 경우
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return _Any()

    def __getattr__(self, _name):
        return _Any()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def get(self, _key=None, default=None):
        return default


class _State(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value


def install_streamlit_stub() -> types.ModuleType:
    """sys.modules 에 가짜 streamlit 을 끼웁니다 (진짜가 있어도 덮습니다)."""

    class _Stub(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Any()

    stub = _Stub("streamlit")
    stub.session_state = _State()
    stub.query_params = {}
    stub.secrets = {}
    for name in ("streamlit", "streamlit.components", "streamlit.components.v1",
                 "streamlit.runtime", "streamlit.runtime.scriptrunner"):
        mod = stub if name == "streamlit" else _Stub(name)
        sys.modules[name] = mod
    return stub


def load_app():
    """app.py 를 'app' 이라는 모듈로 불러옵니다 (main() 은 돌지 않습니다)."""
    install_streamlit_stub()
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    os.chdir(APP_DIR)
    import importlib  # noqa: PLC0415
    return importlib.import_module("app")


def gather_jobs(app, markets=("kr", "us")) -> dict[str, object]:
    """{이름: 인자 없는 함수} — 시장 × 화면의 모든 받기."""
    import config  # noqa: PLC0415

    jobs: dict[str, object] = {"시세": lambda: app.load_all(False)}
    for market in markets:
        for section in config.market_tab_keys(market):
            try:
                found = app._section_jobs(section, market, False)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {market}/{section}: 목록을 만들지 못함 — "
                      f"{type(exc).__name__}: {exc}")
                continue
            for name, fn in found.items():
                jobs.setdefault(f"{market}/{section}/{name}", fn)
    return jobs


def run_jobs(jobs: dict, workers: int = 6, per_job_note: float = 60.0) -> list[dict]:
    """받기를 동시에 돌리고 결과 요약을 돌려줍니다 (값은 swr 안에 남습니다)."""
    rows: list[dict] = []

    def one(name: str, fn):
        t0 = time.time()
        try:
            fn()
            return {"name": name, "sec": round(time.time() - t0, 1), "error": ""}
        except Exception as exc:  # noqa: BLE001 - 하나가 실패해도 나머지는 받습니다
            return {"name": name, "sec": round(time.time() - t0, 1),
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, n, f) for n, f in jobs.items()]
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            mark = "✗" if row["error"] else ("…" if row["sec"] > per_job_note else "✓")
            print(f"  {mark} {row['name']:<40} {row['sec']:>6.1f}초"
                  + (f"  {row['error']}" if row["error"] else ""), flush=True)
    return sorted(rows, key=lambda r: r["name"])


# 값의 모양으로 성공·실패를 가리는 규칙은 health.py 로 옮겼습니다 (저장소도 씁니다)
sys.path.insert(0, APP_DIR) if APP_DIR not in sys.path else None
from health import first_error, health, looks_failed  # noqa: E402,F401


def secret_values() -> tuple[str, ...]:
    return tuple(v for v in (os.environ.get(k, "") for k in SECRET_ENVS) if v)


def redact(text: str, secrets: tuple[str, ...]) -> str:
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "***")
    return text


def write_seed(out_dir: str, rows: list[dict], secrets: tuple[str, ...]) -> dict:
    """swr 에 쌓인 값을 파일로. (보고서) — seed.pkl.gz 와 seed.json 을 씁니다."""
    import swr  # noqa: PLC0415

    reasons: list[str] = []

    def skip(value) -> bool:
        failed = looks_failed(value)
        if failed:
            good, bad = health(value)
            why = redact(first_error(value), secrets)[:140] or "받은 것이 비어 있음"
            reasons.append(f"쓸 것 {good} · 실패 {bad} — {why}")
        return failed

    blob, report = swr.export_seed(secrets, skip=skip)
    report["failed_why"] = [f"{name}: {why}" for name, why
                            in zip(report["dropped_failed"], reasons)]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "seed.pkl.gz"), "wb") as fh:
        fh.write(blob)
    manifest = {
        "made_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_version": swr.CODE_VERSION,
        "kept": report["kept"], "bytes": report["bytes"],
        "dropped_secret": sorted(set(report["dropped_secret"])),
        "dropped_failed": sorted(set(report["dropped_failed"])),
        "failed_why": report["failed_why"][:40],
        "dropped_error": report["dropped_error"][:20],
        "jobs": [{**r, "error": redact(r["error"], secrets)} for r in rows],
    }
    text = redact(json.dumps(manifest, ensure_ascii=False, indent=1), secrets)
    with open(os.path.join(out_dir, "seed.json"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("이 브랜치는 대시보드가 읽는 **자동 수집 스냅샷**입니다.\n\n"
                 "GitHub Actions(collect)가 정해진 시각마다 덮어씁니다. "
                 "손으로 고치지 마십시오.\n")
    return {**report, "manifest": manifest}


def fetch_bytes(url: str, limit: int = 9 * 1024 * 1024, timeout: float = 30.0) -> bytes:
    """주소의 내용을 받습니다 (limit 를 넘으면 그만 받고 예외)."""
    import requests  # noqa: PLC0415

    resp = requests.get(url, timeout=timeout, stream=True,
                        headers={"User-Agent": "stock-dashboard/1.0 (personal dashboard)"})
    resp.raise_for_status()
    chunks, size = [], 0
    for chunk in resp.iter_content(65_536):
        size += len(chunk)
        if size > limit:
            raise ValueError(f"너무 큽니다 (>{limit / 1e6:.0f} MB)")
        chunks.append(chunk)
    return b"".join(chunks)


def summarize_reports(app, out_dir: str, *, fetch=None, summarize=None,
                      load_existing=None) -> dict:
    """반도체 산업 · 삼성전자 · SK하이닉스 리포트를 Claude API 로 요약해 저장합니다.

    {skipped: 사유, new: 건수, total: 건수, failed: [사유…], cost: 달러(참고)}
    키(ANTHROPIC_API_KEY)가 없으면 아무것도 하지 않습니다. 이미 요약한
    리포트는 다시 보내지 않으려고, 먼저 data 브랜치의 지난 파일을 읽습니다.
    """
    import config  # noqa: PLC0415
    import report_summary as rsum  # noqa: PLC0415
    import semi_research  # noqa: PLC0415
    from sources import claude_api  # noqa: PLC0415

    report = {"skipped": "", "new": 0, "total": 0, "failed": [], "cost": 0.0}
    existing: dict = {}
    # data 브랜치는 돌 때마다 통째로 새로 올라갑니다 — 지난 요약을 먼저 읽어
    # 이어 붙이지 않으면 사라지고, 같은 리포트에 돈을 또 냅니다. 워크플로가
    # git 으로 미리 받아 둔 파일(out_dir/summaries.json)이 있으면 그것을,
    # 없으면 공개 주소에서 읽습니다.
    local = os.path.join(out_dir, "summaries.json")
    try:
        if load_existing:
            text = load_existing()
        elif os.path.exists(local):
            with open(local, encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = fetch_bytes(config.SUMMARY_URL, timeout=15).decode("utf-8")
        existing = rsum.parse(text)
    except Exception as exc:  # noqa: BLE001 - 처음에는 파일이 없습니다 (404)
        print(f"  지난 요약 파일 없음 ({type(exc).__name__}) — 새로 시작합니다")

    def save() -> None:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "summaries.json"), "w", encoding="utf-8") as fh:
            fh.write(redact(rsum.dump(existing), secret_values()))
        report["total"] = len(existing)

    if not claude_api.api_key():
        report["skipped"] = "ANTHROPIC_API_KEY 없음"
        if existing:
            save()                       # 지난 요약은 그대로 넘깁니다
        return report
    try:
        data = app.load_semi_research(False)
    except Exception as exc:  # noqa: BLE001
        report["skipped"] = f"리포트 목록 실패: {type(exc).__name__}"
        if existing:
            save()
        return report
    lists = {"반도체 산업": data.get("industry") or []}
    for code, name in semi_research.STOCKS:
        lists[name] = (data.get("stocks") or {}).get(code) or []
    todo = rsum.targets(lists, existing, config.SUMMARY_PER_LIST, config.SUMMARY_MAX_NEW)
    print(f"  요약할 새 리포트 {len(todo)}건 (이미 있는 요약 {len(existing)}건)")
    # 큰 PDF 도 받습니다 — 보내기 전에 앞쪽만 자르므로 비용은 쪽수가 정합니다
    fetch = fetch or (lambda url: fetch_bytes(url, limit=config.SUMMARY_MAX_DOWNLOAD,
                                              timeout=60.0))
    summarize = summarize or claude_api.summarize_pdf
    spent = 0
    streak = 0          # 연달아 실패한 횟수 — 같은 문제로 돈만 나가는 것을 막습니다
    for r in todo:
        if spent >= config.SUMMARY_MAX_INPUT_TOKENS:
            report["skipped"] = f"입력 토큰 상한 {config.SUMMARY_MAX_INPUT_TOKENS:,} 도달"
            print(f"  → 입력 토큰 상한에 닿았습니다 ({spent:,}). 남은 리포트는 다음 번에.")
            break
        try:
            text, usage = summarize(fetch(r.pdf), rsum.PROMPT, model=config.SUMMARY_MODEL,
                                    max_pages=config.SUMMARY_MAX_PAGES)
        except Exception as exc:  # noqa: BLE001 - 한 건 실패가 나머지를 막지 않게
            why = redact(f"{type(exc).__name__}: {exc}", secret_values())[:160]
            report["failed"].append(f"{r.broker} 「{r.title[:24]}」 — {why}")
            print(f"  ✗ {r.date} {r.broker} — {why}")
            streak += 1
            if streak >= 3:
                # 글 없는 응답도 입력 토큰은 청구됩니다 (2026-11-12: 9건 연속)
                report["skipped"] = "연속 3건 실패로 중단"
                print("  → 연달아 3건 실패했습니다. 남은 리포트는 보내지 않습니다.")
                break
            if any(w in why for w in ("authentication_error", "permission_error",
                                      "credit balance", "billing")):
                # 키가 틀렸거나 잔액이 없으면 남은 건도 똑같이 실패합니다 — 그만.
                report["skipped"] = "키 또는 잔액 문제로 중단"
                print("  → 키 또는 잔액 문제입니다. 남은 리포트는 보내지 않습니다.")
                break
            continue
        existing[rsum.key_of(r)] = rsum.entry(r, text, config.SUMMARY_MODEL, usage)
        report["new"] += 1
        streak = 0
        spent += int(usage.get("input_tokens") or 0)
        pages = (f" · {usage.get('pages_sent')}/{usage.get('pages_total')}쪽"
                 if usage.get("pages_total") else "")
        print(f"  ✓ {r.date} {r.broker} 「{r.title[:30]}」 "
              f"입력 {usage.get('input_tokens', 0):,} · 출력 {usage.get('output_tokens', 0):,} 토큰{pages}")
    if existing:
        save()
    return report


def _read_prev(out_dir: str, name: str) -> dict:
    """워크플로가 git 으로 미리 꺼내 둔 지난 파일 (없으면 빈 묶음)."""
    import universe  # noqa: PLC0415

    path = os.path.join(out_dir, name)
    try:
        with open(path, encoding="utf-8") as fh:
            return universe.parse(fh.read())
    except OSError:
        return {}


def _write_out(out_dir: str, name: str, text: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    text = redact(text, secret_values())
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
        fh.write(text)
    return len(text.encode("utf-8"))


def build_universe_us(app, out_dir: str, *, members_fn=None, ticker_map_fn=None,
                      facts_fn=None, force: bool = False, min_keep: int | None = None) -> dict:
    """미국 전수 심사 — S&P 500 + 나스닥100 + 관심종목을 버핏식 기준으로.

    {kept: 지난 파일을 그대로 둠, n: 심사한 종목, errors: 못 받은 종목, sec: 걸린 초, …}
    연간 재무는 자주 바뀌지 않으므로 지난 파일이 UNIVERSE_US_MAX_AGE_HOURS 보다
    새것이면 다시 하지 않습니다 (SEC 에 500번을 하루 두 번 묻지 않으려고).
    받은 원본 재무는 묶음(UNIVERSE_US_BATCH)마다 판정만 남기고 버립니다.
    """
    import buffett  # noqa: PLC0415
    import config  # noqa: PLC0415
    import funnel  # noqa: PLC0415
    import universe  # noqa: PLC0415
    from sources import edgar, edgar_facts, universe_src  # noqa: PLC0415

    name = "universe_us.json"
    t0 = time.time()
    prev = _read_prev(out_dir, name)
    age = universe.age_hours(prev)
    # 지난번에 목록 하나를 못 받았으면(나스닥100 실패 등) 새 파일이어도 다시 합니다
    failed_rule = any(str((info or {}).get("how", "")).startswith("실패")
                      for info in (prev.get("rules") or {}).values())
    # 재무 읽는 방식이 바뀌었으면(buffett.SCREEN_REV) 새 파일이어도 다시 합니다
    stale_rev = prev.get("screen_rev") != buffett.SCREEN_REV
    if (not force and not failed_rule and not stale_rev and prev and age is not None
            and age < config.UNIVERSE_US_MAX_AGE_HOURS
            and len(prev.get("screens") or []) >= (
                universe.MIN_SP500 // 2 if min_keep is None else min_keep)):
        return {"kept": True, "age": age, "n": len(prev.get("screens") or [])}
    try:
        members, rules = (members_fn or universe_src.fetch_us_members)()
    except Exception as exc:  # noqa: BLE001
        # 목록을 못 받으면 지난 파일을 그대로 둡니다 (있으면). 손으로 고른 목록으로
        # 바꿔 쓰지 않습니다 — 화면이 '규칙으로 정한 후보' 라고 말하고 있기 때문입니다.
        return {"skipped": f"후보 목록 실패: {type(exc).__name__}: {str(exc)[:120]}",
                "kept": bool(prev), "n": len(prev.get("screens") or [])}
    watch = [{"ticker": t.replace("-", "."), "name": ""} for t in config.watchlist_us_tickers()]
    merged = universe.merge_members(members, extra=watch)

    try:
        tmap = (ticker_map_fn or edgar.fetch_ticker_map)(config.EDGAR_USER_AGENT)
    except Exception as exc:  # noqa: BLE001
        tmap = {}
        print(f"  티커 → CIK 표 실패 ({type(exc).__name__}) — 표에 CIK 가 있는 종목만 심사합니다")
    errors: dict[str, str] = {}
    by_cik: dict[int, dict] = {}
    for m in merged:
        t = m["ticker"]
        cik = (m.get("cik") or config.EDGAR_CIK_OVERRIDES.get(t.replace(".", "-"))
               or tmap.get(t) or tmap.get(t.replace(".", "-")))
        if not cik:
            errors[t] = "CIK 를 찾지 못했습니다 (SEC 에 미국 회계기준 재무를 내지 않는 기업일 수 있습니다)."
            continue
        m["cik"] = int(cik)
        by_cik.setdefault(int(cik), m)       # 같은 회사의 다른 주식(GOOG/GOOGL)은 하나만
    todo = list(by_cik.values())
    dup = {m["ticker"] for m in merged if m.get("cik") and by_cik.get(m["cik"]) is not m}
    th = config.screen_thresholds()
    fetch = facts_fn or (lambda ciks: edgar_facts.fetch_many(
        ciks, config.EDGAR_USER_AGENT, keep=buffett.KEEP_TAGS))
    screens: list[dict] = []
    size = max(1, int(config.UNIVERSE_US_BATCH))
    for i in range(0, len(todo), size):
        batch = todo[i:i + size]
        facts_map, errs = fetch({m["ticker"]: m["cik"] for m in batch})
        errors.update({t: str(e)[:160] for t, e in errs.items()})
        for m in batch:
            facts = facts_map.get(m["ticker"])
            old_cik = getattr(config, "EDGAR_CIK_PREVIOUS", {}).get(m["ticker"])
            if old_cik and int(old_cik) != m["cik"]:
                # 등록번호가 바뀐 회사 — 예전 번호의 10년치를 합칩니다
                older, _oerr = fetch({m["ticker"]: int(old_cik)})
                merged_facts = edgar_facts.merge_facts(facts, older.get(m["ticker"]))
                if merged_facts is not None and merged_facts is not facts:
                    facts = merged_facts
                    errors.pop(m["ticker"], None)
                    print(f"  {m['ticker']}: 예전 등록번호 {old_cik} 의 재무를 합쳤습니다")
            if facts is None:
                continue
            try:
                screen = buffett.screen_company(m["ticker"], facts,
                                                years=config.SCREEN_YEARS, th=th)
            except Exception as exc:  # noqa: BLE001 - 한 기업이 나머지를 막지 않게
                errors[m["ticker"]] = f"심사 중 오류: {type(exc).__name__}"
                continue
            if m.get("name"):
                screen.name = m["name"]
            # 품질을 통과한 종목만 역DCF 입력(FCF 이력 · 순부채)을 같이 남깁니다 —
            # 가격 단계가 SEC 에 다시 묻지 않게 (funnel.py)
            d = (funnel.dcf_inputs(screen)
                 if screen.ok and screen.passed_count >= config.FUNNEL_MIN_PASS else None)
            screens.append(buffett.to_summary(screen, s=m.get("sector", ""), d=d))
        del facts_map
        print(f"  미국 {min(i + size, len(todo))}/{len(todo)} · {time.time() - t0:.0f}초 · "
              f"못 받음 {len(errors)}")
    members_out = [{k: v for k, v in m.items() if k in ("ticker", "name", "sector", "index")}
                   for m in merged if m["ticker"] not in dup]
    size_b = _write_out(out_dir, name, universe.dump({
        "rules": rules, "members": members_out, "screens": screens, "errors": errors,
        "screen_rev": buffett.SCREEN_REV}))
    return {"n": len(screens), "members": len(members_out), "errors": len(errors),
            "sec": time.time() - t0, "bytes": size_b, "rules": rules}


def build_universe_kr(app, out_dir: str, *, members_fn=None) -> dict:
    """한국 전수 심사 — 코스피200 + 코스닥150 + 관심종목의 일봉 프로파일 · 투자지표."""
    import config  # noqa: PLC0415
    import universe  # noqa: PLC0415
    from sources import universe_src  # noqa: PLC0415

    name = "universe_kr.json"
    t0 = time.time()
    prev = _read_prev(out_dir, name)
    try:
        members, rules = (members_fn or universe_src.fetch_kr_members)()
    except Exception as exc:  # noqa: BLE001
        return {"skipped": f"후보 목록 실패: {type(exc).__name__}: {str(exc)[:120]}",
                "kept": bool(prev), "n": len(prev.get("profiles") or [])}
    watch = [{"code": c, "name": n} for c, n in config.watchlist_kr()]
    merged = universe.merge_members(members, extra=watch)
    cands = [(m["code"], m["name"]) for m in merged]
    profiles, perr = app.kr_vol_profiles_for(cands)
    print(f"  한국 일봉 {len(profiles)}/{len(cands)} · {time.time() - t0:.0f}초")
    values = app.kr_value_rows_for(cands, yahoo_fallback=False)
    print(f"  한국 투자지표 {sum(1 for v in values if not v.error)}/{len(cands)} · "
          f"{time.time() - t0:.0f}초")
    if len(profiles) < len(cands) // 2 and prev:
        # 절반도 못 받았으면 지난 파일이 낫습니다
        return {"skipped": f"일봉을 {len(profiles)}/{len(cands)}만 받았습니다", "kept": True,
                "n": len(prev.get("profiles") or [])}
    errors = {c: str(e)[:160] for c, e in perr.items()}
    size_b = _write_out(out_dir, name, universe.dump({
        "rules": rules,
        "members": [{k: v for k, v in m.items() if k in ("code", "name", "market", "cap", "index")}
                    for m in merged],
        "profiles": [universe.profile_to_dict(p) for p in profiles],
        "values": [universe.profile_to_dict(v) for v in values],
        "errors": errors}))
    return {"n": len(profiles), "members": len(merged), "errors": len(errors),
            "sec": time.time() - t0, "bytes": size_b, "rules": rules}


def _eps_trends(symbols, eps_fn=None) -> tuple[dict, float]:
    """선행 EPS 추정 추이 (야후) — 실패해도 깔때기의 나머지는 갑니다. (결과, 걸린 초)"""
    from sources import yahoo  # noqa: PLC0415

    t = time.time()
    try:
        got = (eps_fn or yahoo.fetch_eps_trend)(list(symbols))
    except Exception:  # noqa: BLE001
        got = {}
    return got or {}, time.time() - t


def build_funnel_us(app, out_dir: str, *, caps_fn=None, ohlc_fn=None, eps_fn=None) -> dict:
    """미국 깔때기 — 품질 통과 종목에만 가격(역DCF)과 차트 조건을 겁니다.

    전수 심사 파일(universe_us.json — 방금 만들었거나 지난 것)에서 역DCF 입력이
    있는 줄만 골라, 시가총액과 1년 일봉을 받아 계산합니다. 주가는 매일 바뀌므로
    전수 심사를 건너뛴 날에도 **이 단계는 매번** 돕니다.
    """
    import chart_signals  # noqa: PLC0415
    import config  # noqa: PLC0415
    import funnel  # noqa: PLC0415
    import universe  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
    from sources import yahoo  # noqa: PLC0415

    t0 = time.time()
    prev = _read_prev(out_dir, "universe_us.json")
    todo = [r for r in (prev.get("screens") or []) if isinstance(r.get("d"), dict)]
    if not todo:
        return {"skipped": "전수 심사 파일에 역DCF 입력이 없습니다"}
    sym = {r["t"]: r["t"].replace(".", "-") for r in todo}      # 야후 표기 (BRK.B → BRK-B)

    def caps_default(symbols):
        def one(s):
            try:
                return s, yahoo.fetch_market_cap(s)
            except Exception:  # noqa: BLE001
                return s, None
        with ThreadPoolExecutor(max_workers=8) as pool:
            return {s: v for s, v in pool.map(one, symbols) if v}

    caps = (caps_fn or caps_default)(list(sym.values()))
    t_caps = time.time() - t0
    try:
        ohlc, oerr = (ohlc_fn or yahoo.fetch_ohlc)(list(sym.values()))
    except Exception as exc:  # noqa: BLE001
        ohlc, oerr = {}, {s: f"야후 일봉 실패: {type(exc).__name__}" for s in sym.values()}
    charts = {row.ticker: row for row in chart_signals.build_rows(
        [(sym[r["t"]], r.get("n", "")) for r in todo], ohlc, oerr)}
    eps, t_eps = _eps_trends(sym.values(), eps_fn)
    rows = []
    for r in todo:
        s = sym[r["t"]]
        rows.append({"t": r["t"], "f": funnel.eps_part(eps.get(s)),
                     "p": funnel.price_part(r["t"], r["d"], caps.get(s),
                                            financial=r.get("s") == "Financials"),
                     "c": funnel.chart_part(charts[s])})
    size_b = _write_out(out_dir, "funnel_us.json", universe.dump({
        "rows": rows, "min_pass": config.FUNNEL_MIN_PASS,
        "universe_made": prev.get("made")}))
    return {"n": len(rows), "caps": len(caps), "bars": sum(1 for r in rows if not r["c"].get("e")),
            "light": sum(1 for r in rows if funnel.is_light(r["p"])),
            "priced": sum(1 for r in rows if funnel.price_known(r["p"])),
            "os": sum(1 for r in rows if funnel.is_oversold(r["c"])),
            "eps": sum(1 for r in rows if r.get("f") and r["f"].get("c90") is not None),
            "sec_eps": t_eps,
            "sec": time.time() - t0, "sec_caps": t_caps, "bytes": size_b}


def build_funnel_kr(app, out_dir: str, *, screens_fn=None, caps_fn=None, ohlc_fn=None,
                    eps_fn=None, force: bool = False) -> dict:
    """한국 깔때기 — 코스피200 + 코스닥150 을 버핏식 품질 기준으로 거르고(DART),
    통과 종목에만 가격(역DCF)과 차트 조건을 겁니다.

    품질 심사는 연간 재무라 하루 한 번만 합니다 (지난 funnel_kr.json 이
    FUNNEL_KR_MAX_AGE_HOURS 보다 새것이고 읽는 방식의 판이 같으면 그 판정을 다시 씀).
    가격 · 차트는 매번 새로 계산합니다. DART 키가 없으면 건너뜁니다.
    """
    import buffett  # noqa: PLC0415
    import buffett_kr  # noqa: PLC0415
    import chart_signals  # noqa: PLC0415
    import config  # noqa: PLC0415
    import funnel  # noqa: PLC0415
    import universe  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
    from sources import naver, yahoo  # noqa: PLC0415

    t0 = time.time()
    name = "funnel_kr.json"
    uni = _read_prev(out_dir, "universe_kr.json")
    members = [m for m in (uni.get("members") or []) if m.get("code")]
    if not members:
        return {"skipped": "한국 후보 목록(universe_kr.json)이 없습니다"}
    prev = _read_prev(out_dir, name)
    q_made = prev.get("q_made") or 0
    reuse = (not force and prev.get("screens") and prev.get("screen_rev") == buffett_kr.KR_REV
             and (time.time() - q_made) < config.FUNNEL_KR_MAX_AGE_HOURS * 3600
             and len(prev["screens"]) >= len(members) // 2)
    if reuse:
        screens, errors = list(prev["screens"]), dict(prev.get("errors") or {})
    else:
        if screens_fn is None and not os.environ.get("DART_API_KEY"):
            return {"skipped": "DART_API_KEY 가 없습니다 (저장소 Secrets)", "kept": bool(prev)}
        cands = [(m["code"], m.get("name", "")) for m in members]
        got, errs = (screens_fn or (lambda c: app.kr_screens_for(c, keep_failed=True)))(cands)
        if len(got) < len(cands) // 3 and prev.get("screens"):
            # 3분의 1도 못 받았으면(DART 한도 · 장애) 지난 판정이 낫습니다
            return {"skipped": f"품질 심사를 {len(got)}/{len(cands)}만 받았습니다", "kept": True}
        errors = {c: redact(str(e), secret_values())[:160] for c, e in errs.items()}
        screens = []
        for code, _n in cands:
            sc = got.get(code)
            if sc is None:
                continue
            d = (funnel.dcf_inputs(sc)
                 if buffett.passes(sc, config.FUNNEL_MIN_PASS, by_ratio=True) else None)
            screens.append(buffett.to_summary(sc, d=d))
        q_made = int(time.time())
    t_q = time.time() - t0

    todo = [r for r in screens if isinstance(r.get("d"), dict)]
    codes = [r["t"] for r in todo]
    # 시가총액 — 후보 목록에 있으면(네이버, 억 원) 그것을, 없으면 야후
    caps = {m["code"]: float(m["cap"]) * 1e8 for m in members
            if m.get("cap") and m["code"] in set(codes)}
    need = [c for c in codes if c not in caps]

    def caps_default(symbols):
        def one(s):
            try:
                return s, yahoo.fetch_market_cap(s)
            except Exception:  # noqa: BLE001
                return s, None
        with ThreadPoolExecutor(max_workers=8) as pool:
            return {s: v for s, v in pool.map(one, symbols) if v}

    if need:
        caps.update((caps_fn or caps_default)(need))
    try:
        ohlc, oerr = (ohlc_fn or naver.fetch_ohlc_many)(codes) if codes else ({}, {})
    except Exception as exc:  # noqa: BLE001
        ohlc, oerr = {}, {c: f"일봉 실패: {type(exc).__name__}" for c in codes}
    charts = {row.ticker: row for row in chart_signals.build_rows(
        [(r["t"], r.get("n", "")) for r in todo], ohlc, oerr)}
    eps, t_eps = _eps_trends(codes, eps_fn)
    rows = [{"t": r["t"], "f": funnel.eps_part(eps.get(r["t"])),
             "p": funnel.price_part(r["t"], r["d"], caps.get(r["t"])),
             "c": funnel.chart_part(charts[r["t"]])} for r in todo]
    size_b = _write_out(out_dir, name, universe.dump({
        "screens": screens, "errors": errors, "rows": rows, "q_made": q_made,
        "screen_rev": buffett_kr.KR_REV, "min_pass": config.FUNNEL_MIN_PASS,
        "n_members": len(members)}))
    ok = [r for r in screens if r.get("y") and not r.get("e")]
    verdicts = [c[1] for r in ok for c in r.get("c") or []]
    return {"n": len(ok), "members": len(members), "errors": len(errors), "reused": bool(reuse),
            "unknown": verdicts.count("unknown"), "verdicts": len(verdicts),
            "pass7": sum(1 for r in ok if buffett.passes(
                buffett.from_summary(r), config.DISCOVER_QUALITY_MIN, by_ratio=True)),
            "todo": len(rows), "caps": sum(1 for r in rows if r["p"].get("cap")),
            "bars": sum(1 for r in rows if not r["c"].get("e")),
            "priced": sum(1 for r in rows if funnel.price_known(r["p"])),
            "light": sum(1 for r in rows if funnel.is_light(r["p"])),
            "os": sum(1 for r in rows if funnel.is_oversold(r["c"])),
            "eps": sum(1 for r in rows if r.get("f") and r["f"].get("c90") is not None),
            "sec_eps": t_eps,
            "sec": time.time() - t0, "sec_q": t_q, "bytes": size_b}


def build_chart_kr(app, out_dir: str, **kw) -> dict:
    """차트 조건 — 한국 (build_chart 참고)."""
    return build_chart(app, out_dir, "kr", **kw)


def build_chart_us(app, out_dir: str, **kw) -> dict:
    """차트 조건 — 미국 (build_chart 참고)."""
    return build_chart(app, out_dir, "us", **kw)


def _yahoo_sym(ticker: str) -> str:
    return ticker.replace(".", "-")             # 야후 표기 (BRK.B → BRK-B)


def build_chart(app, out_dir: str, market: str, *, ohlc_fn=None, semi_fn=None,
                keep: dict | None = None) -> dict:
    """차트 조건 — 한 시장의 후보 전부에 지표 한 줄씩 → chart_{market}.json.

    한국: universe_kr.json 의 후보 (코스피200 + 코스닥150 + 관심종목) · 네이버 일봉
          (못 받은 종목은 야후) · 반도체 = 네이버 업종.
    미국: universe_us.json 의 후보 (S&P 500 + 나스닥100) · 야후 일봉 · 반도체 =
          위키백과 표의 GICS 세부 업종. 티커는 야후 표기(BRK-B)로 싣습니다.

    2026-11-12 사용자 승인 (한국) · 2026-11-13 "같은 방식으로" (미국). 화면에서
    수백 종목의 일봉을 받으면 느려서 수집기가 계산해 올리고 화면은 읽기만 합니다.
    keep 에 dict 를 넘기면 받은 일봉을 {코드/심볼: 봉} 으로 채워 둡니다 — 바로 뒤의
    깔때기가 같은 봉을 다시 받지 않게 합니다.
    반도체 분류는 실패하면 지난 파일의 분류를 다시 씁니다 (표시: 'prev').
    """
    import chart_signals  # noqa: PLC0415
    import universe  # noqa: PLC0415
    from sources import universe_src, yahoo  # noqa: PLC0415

    t0 = time.time()
    name = f"chart_{market}.json"
    src_file = f"universe_{market}.json"
    uni = _read_prev(out_dir, src_file)
    key = "code" if market == "kr" else "ticker"
    members = [m for m in (uni.get("members") or []) if m.get(key)]
    if not members:
        return {"skipped": f"후보 목록({src_file})이 없습니다"}
    prev = _read_prev(out_dir, name)
    if market == "kr":
        codes = [m["code"] for m in members]
        default_ohlc = app.kr_ohlc_for
        default_semi = universe_src.fetch_kr_industry
    else:
        codes = [_yahoo_sym(m["ticker"]) for m in members]
        default_ohlc = yahoo.fetch_ohlc
        default_semi = universe_src.fetch_us_semis
    try:
        ohlc, oerr = (ohlc_fn or default_ohlc)(codes)
    except Exception as exc:  # noqa: BLE001
        ohlc, oerr = {}, {c: f"일봉 실패: {type(exc).__name__}" for c in codes}
    t_bars = time.time() - t0
    if keep is not None:
        keep.update(ohlc)
    if len(ohlc) < len(codes) // 2 and prev.get("rows"):
        return {"skipped": f"일봉을 {len(ohlc)}/{len(codes)}만 받았습니다", "kept": True}

    t1 = time.time()
    semi_err = ""
    try:
        semi, semi_info = (semi_fn or default_semi)()
        semi = {_yahoo_sym(c) for c in semi} if market == "us" else set(semi)
        semi_info = {**semi_info, "src": "web" if market == "us" else "naver"}
    except Exception as exc:  # noqa: BLE001
        semi_err = redact(f"{type(exc).__name__}: {exc}", secret_values())[:200]
        old = prev.get("semi") if isinstance(prev.get("semi"), dict) else {}
        semi = set(old.get("codes") or [])
        semi_info = {k: old.get(k) for k in ("name", "no", "total") if old.get(k)}
        semi_info["src"] = "prev" if semi else ""
        semi_info["prev_made"] = prev.get("made")
    t_semi = time.time() - t1

    rows = chart_signals.build_rows(
        [(c, m.get("name", "") or c) for c, m in zip(codes, members)], ohlc,
        {c: str(e)[:160] for c, e in oerr.items()})
    mk = {c: m.get("market", "") if market == "kr" else m.get("sector", "")
          for c, m in zip(codes, members)}
    prev_rows = {d.get("ticker"): d for d in (prev.get("rows") or []) if isinstance(d, dict)}
    out_rows = []
    for r in rows:
        d = chart_signals.row_to_dict(r)
        if mk.get(r.ticker):
            d["m"] = mk[r.ticker]
        if r.ticker in semi:
            d["s"] = 1
        # '새로' — 지난 파일이 있을 때만 셉니다 (첫 파일에서는 전부 새로가 되므로)
        if prev_rows and chart_signals.new_flag(r, prev_rows.get(r.ticker)):
            d["new"] = 1
        pb, pe = chart_signals.prev_state(r, prev_rows.get(r.ticker))
        if pe is not None:          # 직전 봉 날짜 · 그때 진입이었는가 (다음 수집이 이어받음)
            d["pb"], d["pe"] = pb, int(pe)
        out_rows.append(d)
    in_list = sorted(c for c in semi if c in set(codes))
    size_b = _write_out(out_dir, name, universe.dump({
        "rows": out_rows, "bar": chart_signals.last_bar(rows), "n_members": len(members),
        "market": market,
        "semi": {**semi_info, "codes": sorted(semi), "in_list": len(in_list), "e": semi_err},
    }))
    return {"n": len(members), "bars": len(ohlc), "ok": sum(1 for r in rows if r.ok),
            "os": sum(1 for r in rows if r.ok and r.side == "os"),
            "entry": sum(1 for r in rows if chart_signals.is_os_entry(r)),
            "new": sum(1 for d in out_rows if d.get("new")), "had_prev": bool(prev_rows),
            "semi": len(in_list), "semi_src": semi_info.get("src", ""), "semi_err": semi_err,
            "semi_name": semi_info.get("name", ""),
            "sec": time.time() - t0, "sec_bars": t_bars, "sec_semi": t_semi, "bytes": size_b}


def build_universe(app, out_dir: str, markets=("us", "kr")) -> dict:
    """전수 심사 두 시장. 한쪽이 실패해도 다른 쪽은 갑니다.

    이 단계 동안만 네이버 일봉 응답을 메모합니다 — 한국 전수 심사(종가)와
    차트 조건 · 깔때기(고·저·종)가 같은 주소를 다시 받지 않게 (2026-11-13).
    """
    from sources import naver  # noqa: PLC0415

    naver.CHART_MEMO = {}
    try:
        return _build_universe(app, out_dir, markets)
    finally:
        naver.CHART_MEMO = None


def _build_universe(app, out_dir: str, markets=("us", "kr")) -> dict:
    out = {}
    for market, fn in (("us", build_universe_us), ("kr", build_universe_kr)):
        if market not in markets:
            continue
        try:
            out[market] = fn(app, out_dir)
        except Exception as exc:  # noqa: BLE001
            out[market] = {"skipped": f"{type(exc).__name__}: "
                                      f"{redact(str(exc), secret_values())[:160]}"}
        r = out[market]
        label = {"us": "미국", "kr": "한국"}[market]
        if r.get("kept") and not r.get("skipped"):
            print(f"  {label}: 지난 파일이 {r.get('age', 0):.1f}시간 전 것이라 그대로 둡니다 "
                  f"({r.get('n', 0)}종목)")
        elif r.get("skipped"):
            print(f"  {label}: 건너뜀 — {r['skipped']}"
                  + (" (지난 파일 유지)" if r.get("kept") else ""))
        else:
            print(f"  {label}: 후보 {r.get('members', 0)} → 심사 {r.get('n', 0)} · "
                  f"못 받음 {r.get('errors', 0)} · {r.get('sec', 0):.0f}초 · "
                  f"{r.get('bytes', 0) / 1024:.0f} KB")
            for name, info in (r.get("rules") or {}).items():
                print(f"    규칙: {name} {info.get('n', 0)} ({info.get('how', '')})")
    def print_chart(label: str, c: dict) -> None:
        if c.get("skipped"):
            print(f"  {label} 차트 조건: 건너뜀 — {c['skipped']}"
                  + (" (지난 파일 유지)" if c.get("kept") else ""))
            return
        src = {"naver": "네이버 업종", "web": "위키백과 GICS 세부 업종",
               "prev": "지난 분류 재사용", "": "분류 없음"}.get(c["semi_src"], c["semi_src"])
        print(f"  {label} 차트 조건: 후보 {c['n']} → 일봉 {c['bars']} · 계산 {c['ok']} · "
              f"과매도 쪽 {c['os']} · 과매도 진입 {c['entry']} (새로 "
              f"{c['new'] if c['had_prev'] else '— 지난 파일 없음'}) · "
              f"반도체 {c['semi']} ({src} '{c['semi_name']}'"
              + (f" · 실패 이유: {c['semi_err']}" if c["semi_err"] else "") + ") · "
              f"{c['sec']:.0f}초 (일봉 {c['sec_bars']:.0f}초 · 업종 {c['sec_semi']:.0f}초) · "
              f"{c['bytes'] / 1024:.0f} KB")

    us_bars: dict = {}
    if "us" in markets:
        try:
            c = build_chart_us(app, out_dir, keep=us_bars)
        except Exception as exc:  # noqa: BLE001
            c = {"skipped": f"{type(exc).__name__}: {redact(str(exc), secret_values())[:160]}"}
        out["chart_us"] = c
        print_chart("미국", c)

    def us_ohlc_reuse(symbols):
        """차트 조건에서 받은 일봉을 다시 씁니다 — 없는 심볼만 새로 받습니다."""
        from sources import yahoo  # noqa: PLC0415

        have = {s_: us_bars[s_] for s_ in symbols if s_ in us_bars}
        need = [s_ for s_ in symbols if s_ not in us_bars]
        got, errs = yahoo.fetch_ohlc(need) if need else ({}, {})
        return {**have, **got}, errs

    if "us" in markets:
        try:
            f = build_funnel_us(app, out_dir, ohlc_fn=us_ohlc_reuse if us_bars else None)
        except Exception as exc:  # noqa: BLE001
            f = {"skipped": f"{type(exc).__name__}: {redact(str(exc), secret_values())[:160]}"}
        out["funnel_us"] = f
        if f.get("skipped"):
            print(f"  미국 깔때기: 건너뜀 — {f['skipped']}")
        else:
            print(f"  미국 깔때기: 품질 통과 {f['n']}종목 → 시가총액 {f['caps']} · 일봉 {f['bars']} · "
                  f"가격 판정 {f['priced']} (부담 낮음 {f['light']}) · 차트 과매도 쪽 {f['os']} · "
                  f"선행 EPS {f['eps']} ({f['sec_eps']:.0f}초) · "
                  f"{f['sec']:.0f}초 (시가총액 {f['sec_caps']:.0f}초) · {f['bytes'] / 1024:.0f} KB")
    kr_bars: dict = {}
    if "kr" in markets:
        try:
            c = build_chart_kr(app, out_dir, keep=kr_bars)
        except Exception as exc:  # noqa: BLE001
            c = {"skipped": f"{type(exc).__name__}: {redact(str(exc), secret_values())[:160]}"}
        out["chart_kr"] = c
        print_chart("한국", c)

    def kr_ohlc_reuse(codes):
        """차트 조건에서 받은 일봉을 다시 씁니다 — 없는 종목만 새로 받습니다."""
        from sources import naver  # noqa: PLC0415

        have = {c: kr_bars[c] for c in codes if c in kr_bars}
        need = [c for c in codes if c not in kr_bars]
        got, errs = naver.fetch_ohlc_many(need) if need else ({}, {})
        return {**have, **got}, errs

    if "kr" in markets:
        try:
            k = build_funnel_kr(app, out_dir, ohlc_fn=kr_ohlc_reuse if kr_bars else None)
        except Exception as exc:  # noqa: BLE001
            k = {"skipped": f"{type(exc).__name__}: {redact(str(exc), secret_values())[:160]}"}
        out["funnel_kr"] = k
        if k.get("skipped"):
            print(f"  한국 깔때기: 건너뜀 — {k['skipped']}")
        else:
            print(f"  한국 깔때기: 후보 {k['members']} → 재무 받음 {k['n']} (못 받음 {k['errors']}"
                  f"{' · 지난 판정 재사용' if k['reused'] else ''}) · 판정 불가 "
                  f"{k['unknown']}/{k['verdicts']} · 품질 통과(판정 중 7/9 이상) {k['pass7']} · "
                  f"가격 판정 {k['priced']}/{k['todo']} (부담 낮음 {k['light']}) · "
                  f"차트 과매도 쪽 {k['os']} · 선행 EPS {k['eps']} ({k['sec_eps']:.0f}초) · "
                  f"{k['sec']:.0f}초 (품질 {k['sec_q']:.0f}초) · "
                  f"{k['bytes'] / 1024:.0f} KB")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default="seed_out")
    ap.add_argument("--markets", default="kr,us")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--list", action="store_true",
                    help="무엇을 받을지 목록만 찍고 끝냅니다")
    args = ap.parse_args(argv)

    missing = [k for k in ("DART_API_KEY", "FRED_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f"※ 환경변수 없음: {', '.join(missing)} — 그 키가 필요한 항목은 "
              "실패로 남고, 앱이 여는 순간에 직접 받습니다.")
    t0 = time.time()
    app = load_app()
    import swr  # noqa: PLC0415
    swr.DISK = False                     # 수집기는 임시 사본을 남길 이유가 없음
    jobs = gather_jobs(app, tuple(m for m in args.markets.split(",") if m))
    print(f"받을 것 {len(jobs)}가지\n")
    if args.list:
        for name in jobs:
            print(f"  {name}")
        return 0
    rows = run_jobs(jobs, workers=args.workers)
    report = write_seed(args.out, rows, secret_values())
    # 종목 발굴 전수 심사 — 규칙으로 정한 후보(지수 구성 종목) 전부. 실패해도
    # 스냅샷은 그대로 올라가고, 화면은 지난 파일(또는 손으로 고른 후보)을 씁니다.
    print("\n종목 발굴 전수 심사")
    try:
        build_universe(app, args.out, tuple(m for m in args.markets.split(",") if m))
    except Exception as exc:  # noqa: BLE001
        print(f"  전수 심사 단계 실패: {type(exc).__name__}: "
              f"{redact(str(exc), secret_values())[:200]}")

    # 리포트 AI 요약 — 키가 있을 때만. 실패해도 스냅샷은 그대로 올라갑니다.
    print("\n리포트 요약 (Claude API)")
    try:
        summ = summarize_reports(app, args.out)
        if summ["skipped"]:
            print(f"  건너뜀 — {summ['skipped']}")
        if not summ["skipped"] or summ["new"]:
            print(f"  새 요약 {summ['new']}건 · 저장된 요약 {summ['total']}건"
                  + (f" · 실패 {len(summ['failed'])}건" if summ["failed"] else ""))
    except Exception as exc:  # noqa: BLE001
        print(f"  요약 단계 실패: {type(exc).__name__}: "
              f"{redact(str(exc), secret_values())[:200]}")
    failed = [r for r in rows if r["error"]]
    print(f"\n스냅샷 {report['kept']}개 항목 · {report['bytes'] / 1024:,.0f} KB · "
          f"{time.time() - t0:.0f}초 · 실패 {len(failed)}/{len(rows)}")
    if report["dropped_failed"]:
        print("받지 못해 뺀 항목 (앱이 직접 받습니다):")
        for line in report["failed_why"]:
            print(f"  - {line}")
    if report["dropped_secret"]:
        print("인증키가 섞여 뺀 항목: "
              + ", ".join(sorted(set(report["dropped_secret"]))))
    return 0 if report["kept"] else 1


if __name__ == "__main__":
    sys.exit(main())
