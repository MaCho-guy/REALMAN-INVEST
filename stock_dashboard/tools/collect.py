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
SECRET_ENVS = ("DART_API_KEY", "FRED_API_KEY", "EDGAR_USER_AGENT",
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


def health(value, _depth: int = 0) -> tuple[int, int]:
    """(쓸 만한 것, 실패한 것) 을 셉니다 — 값의 모양만 보고 판단합니다.

    받는 함수들은 실패해도 예외를 올리지 않고 '빈 값 + 오류 문구' 를
    돌려줍니다 (화면이 한 줄 실패로 멈추지 않게). 그대로 스냅샷에 넣으면
    앱이 **실패를 물려받아** 직접 받으면 됐을 것까지 비어 보입니다.
    """
    if value is None or _depth > 6:
        return 0, 0
    if isinstance(value, (str, bytes, int, float, bool)):
        return 0, 0
    if isinstance(value, tuple) and value and all(
            isinstance(v, (str, bytes, int, float, bool, type(None))) for v in value):
        # 글자·숫자만 든 한 줄 — 예: (이름, 값, 메모). 2026-11-12 첫 실행에서
        # 이런 줄을 전부 '쓸 것 없음' 으로 세어 멀쩡한 국내 지표·유동성을
        # 스냅샷에서 뺐습니다. 값 자리가 '—' 이거나 '실패' 가 적혀 있을 때만
        # 실패로 봅니다 (이 앱이 못 받은 칸을 적는 방식).
        texts = [v for v in value if isinstance(v, str)]
        if value[0] is None:                 # (None, "왜 못 받았는지") 모양
            return (0, 1) if any(texts) else (0, 0)
        if any(t.strip() == "—" or "실패" in t for t in texts):
            return 0, 1
        return (1, 0) if any(v not in (None, "", 0) for v in value) else (0, 0)
    if isinstance(value, tuple):
        tail = value[-1] if value else None
        tail_is_error = isinstance(tail, str) or (
            isinstance(tail, dict) and tail
            and all(isinstance(v, str) for v in tail.values()))
        body = value[:-1] if (tail_is_error and len(value) >= 2) else value
        good = bad = 0
        for item in body:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        if tail_is_error and tail:
            bad += len(tail) if isinstance(tail, dict) else 1
        return good, bad
    if isinstance(value, dict):
        if not value:
            return 0, 0
        if "error" in value or "_error" in value:
            # {rows, error} 처럼 결과와 실패 사유를 함께 담는 묶음
            if value.get("error") or value.get("_error"):
                return 0, 1
            rest = [v for k, v in value.items() if k not in ("error", "_error")]
            return (1, 0) if any(bool(v) for v in rest) else (0, 0)
        vals = list(value.values())[:400]
        if all(isinstance(v, (str, bytes, int, float, bool, type(None))) for v in vals):
            return 1, 0
        good = bad = 0
        for item in vals:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        return good, bad
    if isinstance(value, (list, set, frozenset)):
        vals = list(value)[:400]
        if not vals:
            return 0, 0
        if all(isinstance(v, (str, bytes, int, float, bool, type(None))) for v in vals):
            return 1, 0
        good = bad = 0
        for item in vals:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        return good, bad
    # 우리 자료형 — error 가 차 있으면 실패, 아니면 쓸 만한 값
    if getattr(value, "error", None):
        return 0, 1
    return 1, 0


def first_error(value, _depth: int = 0) -> str:
    """값 안에서 처음 만나는 실패 문구 — 로그에 '왜 뺐는지' 적는 데 씁니다."""
    if value is None or _depth > 6:
        return ""
    if isinstance(value, str):
        return ""
    err = getattr(value, "error", None)
    if isinstance(err, str) and err:
        return err
    if isinstance(value, dict):
        for key in ("error", "_error"):
            if isinstance(value.get(key), str) and value.get(key):
                return value[key]
        for v in list(value.values())[:50]:
            if isinstance(v, str) and _depth > 0 and v:
                return v
            got = first_error(v, _depth + 1)
            if got:
                return got
        return ""
    if isinstance(value, tuple):
        if value and all(isinstance(v, (str, int, float, bool, type(None))) for v in value):
            texts = [v for v in value if isinstance(v, str) and v]
            if texts and (value[0] is None
                          or any(t.strip() == "—" or "실패" in t for t in texts)):
                return texts[-1]
            return ""
        tail = value[-1] if value else None
        if isinstance(tail, str) and tail:
            return tail
        for v in reversed(value):
            got = first_error(v, _depth + 1)
            if got:
                return got
        return ""
    if isinstance(value, (list, set, frozenset)):
        for v in list(value)[:50]:
            got = first_error(v, _depth + 1)
            if got:
                return got
    return ""


def looks_failed(value) -> bool:
    """쓸 만한 것이 없거나, 실패가 더 많으면 스냅샷에 넣지 않습니다."""
    good, bad = health(value)
    return good == 0 or bad >= good


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
