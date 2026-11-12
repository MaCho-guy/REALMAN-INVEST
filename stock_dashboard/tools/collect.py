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
