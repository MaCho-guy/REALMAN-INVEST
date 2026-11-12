"""장중 갱신 · 시세 3초 · 아침 스냅샷 · 인증키 지우기 · 기본 위젯 색 검증.

    python tests/live_seed_test.py
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys
import threading
import time
from zoneinfo import ZoneInfo

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
sys.path.insert(0, "tools")

DART_KEY = "k" * 8 + "0123456789abcdef0123456789abcdef"
FRED_KEY = "f" * 8 + "fedcba9876543210fedcba98"
os.environ["DART_API_KEY"] = DART_KEY
os.environ["FRED_API_KEY"] = FRED_KEY

import buildstamp  # noqa: E402
import calendar_events as cal  # noqa: E402
import swr  # noqa: E402
import theme  # noqa: E402
from sources import dart, fred, safe  # noqa: E402

swr.DISK = False
FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


print("\n=== 인증키 지우기 ===")
leak = (f"Max retries exceeded with url: /api/list.json?crtfc_key={DART_KEY}&page_no=1 "
        f"and /fred/series/observations?series_id=DGS10&api_key={FRED_KEY}&file_type=json")
clean = safe.scrub(leak)
check("값이 사라진다", DART_KEY not in clean and FRED_KEY not in clean, clean)
check("자리는 남는다 (무엇을 불렀는지는 보임)",
      "crtfc_key=***&page_no=1" in clean and "api_key=***&file_type=json" in clean, clean)
check("모르는 키도 '…_key=값' 모양이면 지운다",
      safe.scrub("x?crtfc_key=zzzz9999&y=1") == "x?crtfc_key=***&y=1")
check("상관없는 글은 그대로", safe.scrub("PER 12.3 · key 지표 = 좋음") == "PER 12.3 · key 지표 = 좋음")
check("문자열이 아니면 그대로", safe.scrub(None) is None and safe.scrub(3) == 3)
check("DartError 는 만들어질 때 지운다", DART_KEY not in str(dart.DartError(leak)))
check("FredError 도", FRED_KEY not in str(fred.FredError(leak)))
check("하위 오류도", DART_KEY not in str(dart.DartKeyMissing(leak)))


class _Boom(Exception):
    pass


check("dart._describe 도 지운다", DART_KEY not in dart._describe(_Boom(leak)))


def _raises():
    raise RuntimeError(leak)


bad = swr.cached(60, disk=False)(_raises)
try:
    bad()
except RuntimeError:
    pass
check("swr 가 적어 두는 오류에도 없다",
      all(DART_KEY not in (e.error or "") for e in swr._store.values()))


class _FakeSt:
    def __init__(self):
        self.seen = []

    def markdown(self, body, unsafe_allow_html=False):
        self.seen.append(body)

    def code(self, body, language=None):
        self.seen.append(body)

    def error(self, body):
        self.seen.append(body)


fake = _FakeSt()
n1 = safe.guard_streamlit(fake)
n2 = safe.guard_streamlit(fake)
fake.markdown(leak, unsafe_allow_html=True)
fake.code(body=leak)
fake.error(leak)
check("화면 출력 함수를 감싼다 (두 번 불러도 한 번만)", n1 == 3 and n2 == 0, f"{n1},{n2}")
check("화면에 찍히는 글에 키가 없다",
      len(fake.seen) == 3 and all(DART_KEY not in s and FRED_KEY not in s for s in fake.seen))
src = pathlib.Path("app.py").read_text(encoding="utf-8")
check("앱이 시작할 때 지우개를 단다", "safe.guard_streamlit(st)" in src)
check("진단 결과도 지운 뒤 보여준다", "safe.scrub(output)" in src)

print("\n=== 때에 따라 달라지는 유효 시간 ===")
state = {"ttl": 0.05, "n": 0}


def _count(tag):
    state["n"] += 1
    return f"{tag}{state['n']}"


live = swr.cached(lambda tag: state["ttl"], stale=10, disk=False)(_count)
check("처음에는 받는다", live("a") == "a1")
state["ttl"] = 100
check("유효 시간 안이면 그대로", live("a") == "a1" and state["n"] == 1)
state["ttl"] = 0.01
time.sleep(0.03)
first = live("a")
deadline = time.time() + 2
while swr.busy() and time.time() < deadline:
    time.sleep(0.01)
state["ttl"] = 100
# 뒤에서 받기가 아주 빠르면 첫 호출이 벌써 새 값을 볼 수도 있습니다
check("짧아지면 기다리지 않고 뒤에서 새로 받는다", first in ("a1", "a2") and live("a") == "a2",
      f"{first} → {live('a')}")
check("ttl_for 가 인자를 받는다", live.ttl_for(("a",)) == 100)

print("\n=== 새 값을 잠깐 기다리기 (wait_fresh) ===")
delay = {"sec": 0.0, "n": 0}


def _quote():
    delay["n"] += 1
    time.sleep(delay["sec"])
    return delay["n"]


quote = swr.cached(0.05, stale=30, disk=False, wait_fresh=0.4)(_quote)
check("처음", quote() == 1)
time.sleep(0.08)
delay["sec"] = 0.1
t0 = time.perf_counter()
got = quote()
took = time.perf_counter() - t0
check("빨리 오면 새 값을 준다 (옛 값을 보여주지 않음)", got == 2 and took < 0.35,
      f"{got} · {took:.2f}초")
time.sleep(0.08)
delay["sec"] = 1.0
t0 = time.perf_counter()
got = quote()
took = time.perf_counter() - t0
check("늦으면 기다린 만큼만 기다리고 옛 값", got == 2 and 0.3 < took < 0.7,
      f"{got} · {took:.2f}초")
t0 = time.perf_counter()
again = quote()
check("같은 새로 받기를 두 번 기다리지 않는다",
      again == 2 and time.perf_counter() - t0 < 0.15, f"{time.perf_counter() - t0:.2f}초")
deadline = time.time() + 3
while swr.busy() and time.time() < deadline:
    time.sleep(0.02)
check("뒤에서 끝나면 새 값", quote() == 3)
plain = swr.cached(0.05, stale=30, disk=False)(_quote)
plain()
time.sleep(0.08)
t0 = time.perf_counter()
plain()
check("기다리지 않는 것이 기본", time.perf_counter() - t0 < 0.1)
deadline = time.time() + 3
while swr.busy() and time.time() < deadline:
    time.sleep(0.02)
check("시세에 3초를 건다", "wait_fresh=config.QUOTE_WAIT_FRESH_SEC" in src)

print("\n=== 키에 쓰는 모듈 이름 ===")


def _fn():
    return 1


_fn.__module__ = "__main__"
check("__main__ 은 파일 이름으로", swr._module_name(_fn) == "live_seed_test", swr._module_name(_fn))
_fn.__module__ = "app"
check("다른 모듈은 그대로", swr._module_name(_fn) == "app")

print("\n=== 스냅샷 내보내기 · 읽기 ===")
swr.clear_all()
with swr._store_lock:
    swr._store.clear()
calls = {"n": 0}


def _data(market):
    calls["n"] += 1
    return {"market": market, "rows": [1, 2, 3]}


def _leaky():
    return {"msg": f"url?crtfc_key={DART_KEY}"}


def _failed():
    return {}, "받지 못했습니다"


data = swr.cached(3_600, disk=False)(_data)
leaky = swr.cached(3_600, disk=False)(_leaky)
failed = swr.cached(3_600, disk=False)(_failed)
data("kr"), data("us"), leaky(), failed()
import collect  # noqa: E402

blob, rep = swr.export_seed((DART_KEY, FRED_KEY), skip=collect.looks_failed)
check("쓸 만한 값만 담는다", rep["kept"] == 2, str(rep))
check("인증키가 든 값은 뺀다", any("_leaky" in k for k in rep["dropped_secret"]), str(rep))
check("실패한 결과는 뺀다", any("_failed" in k for k in rep["dropped_failed"]), str(rep))
import gzip  # noqa: E402

check("파일 어디에도 키가 없다", DART_KEY.encode() not in gzip.decompress(blob))

with swr._store_lock:
    swr._store.clear()
before = calls["n"]
got = swr.import_seed(blob)
check("읽으면 채워진다", got["loaded"] == 2, str(got))
check("채운 값은 다시 받지 않고 쓴다",
      data("kr") == {"market": "kr", "rows": [1, 2, 3]} and calls["n"] == before)
check("받은 시각이 그대로다 (지금으로 바뀌지 않음)", got["made"] <= time.time())
again = swr.import_seed(blob)
check("이미 있는 값은 덮지 않는다", again["loaded"] == 0 and again["skipped_have"] == 2, str(again))
with swr._store_lock:
    swr._store.clear()
old = swr.import_seed(blob, max_age=-1)
check("너무 오래된 스냅샷은 버린다", old["loaded"] == 0 and old["skipped_old"] == 2, str(old))
check("깨진 파일은 조용히 넘긴다", swr.import_seed(b"not a seed")["loaded"] == 0)
swr._seed_state.update(tried=False, report=None)
r1 = swr.load_seed_from("http://127.0.0.1:9/none.gz", timeout=0.5)
r2 = swr.load_seed_from("http://127.0.0.1:9/none.gz", timeout=0.5)
check("못 받아도 멈추지 않고, 한 번만 시도한다",
      r1 is r2 and r1["loaded"] == 0 and "error" in r1, str(r1))
check("주소가 없으면 아무것도 안 한다", swr.load_seed_from("") is None)
check("앱이 첫 화면에서 스냅샷을 읽는다", "swr.load_seed_from" in src and "config.SEED_URL" in src)

print("\n=== 수집기 ===")
check("빈 값 + 오류 문구 = 실패", collect.looks_failed(({}, "요청 실패")))
check("빈 값 + 오류 묶음 = 실패", collect.looks_failed(({}, {"A": "x", "B": "y"})))


class _Row:
    def __init__(self, error=""):
        self.error = error


check("전부 오류인 줄 = 실패", collect.looks_failed([_Row("x"), _Row("y")]))
check("대부분 받았으면 넣는다", not collect.looks_failed([_Row(), _Row(), _Row("x")]))
check("값 + 빈 오류 = 정상", not collect.looks_failed(({"A": [1, 2]}, {})))
check("값 + 일부 오류 = 정상", not collect.looks_failed(({"A": _Row(), "B": _Row()}, {"C": "x"})))
check("비어 있으면 넣지 않는다", collect.looks_failed({}) and collect.looks_failed(None))
# 2026-11-12 첫 실제 실행: 글자만 든 줄을 '쓸 것 없음' 으로 세어 멀쩡한 값을 뺐다
ok_rows = [("한국 소비자물가", "118.2", "2026-09 · 전년비 +2.1%"), ("한국 기준금리", "2.50%", "")]
bad_rows = [("한국 소비자물가", "—", "KORCPIALLMINMEI: FRED API 실패 — ProxyError")] * 2
check("(이름, 값, 메모) 줄은 정상", not collect.looks_failed(ok_rows), str(collect.health(ok_rows)))
check("값이 '—' 인 줄은 실패", collect.looks_failed(bad_rows))
check("(None, 사유) 는 실패", collect.looks_failed((None, "ExportsError: 목록 페이지를 받지 못했습니다"))
      and "ExportsError" in collect.first_error((None, "ExportsError: 목록")))


class _Net:
    error = ""


check("유동성 (값, 글자 줄들) 은 정상", not collect.looks_failed((_Net(), ok_rows)))
check("{rows, error} 묶음 — 값이 있으면 정상",
      not collect.looks_failed({"AAPL": {"history": [1, 2], "ex_date": None, "error": ""}}))
check("{rows, error} 묶음 — 오류면 실패",
      collect.looks_failed({"AAPL": {"history": [], "error": "야후 요청 실패"},
                            "MSFT": {"history": [], "error": "야후 요청 실패"}}))
check("왜 뺐는지 한 줄로 꺼낸다",
      collect.first_error(({}, "요청 실패: ProxyError")) == "요청 실패: ProxyError"
      and "FRED API 실패" in collect.first_error(bad_rows)
      and collect.first_error({"A": {"history": [], "error": "야후 요청 실패"}}) == "야후 요청 실패"
      and collect.first_error(ok_rows) == "")
check("보유 종목은 수집 대상이 아니다",
      "PORTFOLIO" in collect.SECRET_ENVS
      and "PORTFOLIO" not in pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8"))
wf = pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8")
check("정해진 시각 + 손으로 돌리기", wf.count("cron:") == 2 and "workflow_dispatch" in wf)
check("data 브랜치에만 쓴다", "contents: write" in wf and wf.rstrip().endswith("data"))
check("키는 Secrets 에서만", "secrets.DART_API_KEY" in wf and "secrets.FRED_API_KEY" in wf
      and DART_KEY not in wf)

print("\n=== 장이 열려 있나 ===")
KST, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
check("한국 목요일 10시", cal.is_open("kr", dt.datetime(2026, 11, 12, 10, 0, tzinfo=KST)))
check("한국 8시 59분은 닫힘", not cal.is_open("kr", dt.datetime(2026, 11, 12, 8, 59, tzinfo=KST)))
check("한국 15시 30분에 닫힘", not cal.is_open("kr", dt.datetime(2026, 11, 12, 15, 30, tzinfo=KST)))
check("토요일", not cal.is_open("kr", dt.datetime(2026, 11, 14, 10, 0, tzinfo=KST)))
check("미국 목요일 10시 (뉴욕)", cal.is_open("us", dt.datetime(2026, 11, 12, 10, 0, tzinfo=NY)))
check("미국 9시 29분은 닫힘", not cal.is_open("us", dt.datetime(2026, 11, 12, 9, 29, tzinfo=NY)))
check("같은 순간 한국은 한밤", not cal.is_open("kr", dt.datetime(2026, 11, 12, 10, 0, tzinfo=NY)))
hol = next((d for d in sorted(cal.NYSE_HOLIDAYS) if d.startswith("2026-11")), None)
if hol:
    y, m, d = map(int, hol.split("-"))
    check(f"미국 휴장일 ({hol})", not cal.is_open("us", dt.datetime(y, m, d, 11, 0, tzinfo=NY)))
early = next((d for d in sorted(cal.NYSE_EARLY_CLOSE) if d >= "2026-11"), None)
if early:
    y, m, d = map(int, early.split("-"))
    check(f"조기 마감일 ({early}) 13시 이후 닫힘",
          cal.is_open("us", dt.datetime(y, m, d, 12, 0, tzinfo=NY))
          and not cal.is_open("us", dt.datetime(y, m, d, 13, 30, tzinfo=NY)))
check("차트는 장중 5분", "CHART_TTL_OPEN_SEC = 300" in pathlib.Path("config.py").read_text(encoding="utf-8")
      and "@swr.cached(_chart_ttl" in src)
check("장중에는 '잠정' 이라고 적는다", "잠정" in src and "calendar_events.is_open" in src)

print("\n=== 기본 위젯 색 (어두운 기기에서도 보이게) ===")
native = theme.build_native_rules()
css = theme.build_css("kr")
check("전체 스타일에 들어간다", native.strip()[:80] in css)
for needle, why in (
    ("color-scheme: light", "밝은 화면으로 고정"),
    ('[data-testid="stExpander"]', "접는 칸 제목"),
    ('[data-testid="stWidgetLabel"]', "입력 이름"),
    ('[data-testid="stButtonGroup"]', "고르기 단추"),
    ('aria-checked="true"', "고른 단추 표시"),
    ('[data-testid="stPopover', "설정 단추"),
    (".dash-ctrlmark", "위쪽 단추 한 줄"),
):
    check(why, needle in native, needle)
check("접는 칸 글자에 색을 직접 준다 (기기 설정을 따르지 않게)",
      "summary" in native and "var(--dash-ink" in native)
check("위쪽 단추 줄은 줄바꿈하지 않는다", "flex-wrap: nowrap" in native.replace("flex-wrap:nowrap", "flex-wrap: nowrap"))
check("위쪽 단추 4개가 한 줄", "dash-ctrlmark" in src and "st.columns([2, 2, 2, 2])" in src)
check("앱이 밝은 테마를 직접 건다", "_force_light_theme()" in src)

print("\n=== 설정 파일 문법 ===")
broken = '[theme]\nbase = "light"\n\n[browser]\ngatherUsageStats = fals\n'
msg = buildstamp._toml_error(broken)
check("잘린 false 를 짚어 준다", "5번째 줄" in msg and "fals" in msg and "잘렸" in msg, msg)
check("멀쩡하면 조용하다", buildstamp._toml_error(broken.replace("fals\n", "false\n")) == "")

print("\n=== 새 파일을 올린 뒤 옛 모듈이 남는 사고 (2026-11-12) ===")
import ast  # noqa: E402
import types  # noqa: E402

tree = ast.parse(src)
want = {"_build_id", "_drop_stale_modules"}
body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
ns = {"os": os, "sys": sys, "__file__": os.path.abspath("app.py")}
exec(compile(ast.Module(body=body, type_ignores=[]), "app.py", "exec"), ns)  # noqa: S102
drop, build_id = ns["_drop_stale_modules"], ns["_build_id"]

stale = types.ModuleType("config")          # 옛 config — 새 값이 없습니다
stale.__file__ = os.path.abspath("config.py")
stale.CACHE_TTL_SEC = 60
sub = types.ModuleType("sources.dart")
sub.__file__ = os.path.abspath("sources/dart.py")
outside = types.ModuleType("requests")
outside.__file__ = "/usr/lib/python3/site-packages/requests/__init__.py"
builtin = types.ModuleType("time")           # __file__ 없음
main_mod = types.ModuleType("__main__")
main_mod.__file__ = os.path.abspath("app.py")
mods = {"config": stale, "sources.dart": sub, "requests": outside,
        "time": builtin, "__main__": main_mod}

saved = getattr(sys, "_dash_build", None)
sys._dash_build = "예전 묶음"
out = drop(mods, build="새 묶음")
check("묶음이 바뀌면 이 폴더의 모듈을 내보낸다", out == ["config", "sources.dart"], str(out))
check("남의 모듈 · 본문은 그대로", set(mods) == {"requests", "time", "__main__"}, str(set(mods)))
sys._dash_build = "새 묶음"
mods2 = {"config": stale}
check("묶음이 같으면 건드리지 않는다", drop(mods2, build="새 묶음") == [] and "config" in mods2)
del sys._dash_build
mods3 = {"config": stale}
check("이 코드가 처음 올라간 프로세스에서도 내보낸다 (기록이 없을 때)",
      drop(mods3, build="새 묶음") == ["config"])
check("새로 켜진 프로세스에서는 내보낼 것이 없다", drop({"requests": outside}, build="x") == [])

# 사고 재현: 옛 config 가 메모리에 있으면 새 값이 없고, 내보낸 뒤 다시 불러오면 있다
real = sys.modules.pop("config", None)
sys.modules["config"] = stale
check("재현 — 옛 모듈에는 새 값이 없다", not hasattr(sys.modules["config"], "QUOTE_WAIT_FRESH_SEC"))
drop(build="새 묶음")
import config as _fresh  # noqa: E402

check("내보낸 뒤 다시 불러오면 새 값이 있다",
      getattr(_fresh, "QUOTE_WAIT_FRESH_SEC", None) == 3.0)
if saved is not None:
    sys._dash_build = saved
check("지문은 BUILD.json 내용에서", len(build_id()) == 16)
check("import 보다 먼저 확인한다",
      src.index("_drop_stale_modules() if __name__") < src.index("import swr  # noqa: E402"))
check("정상 시작한 뒤에 묶음을 적는다", "sys._dash_build = _build_id()" in src)

print("\n=== 받은 시각 표기 (2026-11-12 \"모든 지표 언제 받았는지\") ===")
import re  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

with swr._store_lock:
    swr._store.clear()
swr._tl.__dict__.pop("served", None)
t_a = swr.cached(3_600, disk=False)(lambda tag: tag)
t_a.name = "load_alpha"
t_b = swr.cached(3_600, disk=False)(lambda: "b")
t_b.name = "load_beta"
t_a("x")
check("기록을 시작하기 전에는 적지 않는다", swr.served_times() == {})
swr.reset_stale_served()
t0_ = time.time()
t_a("x"), t_a("y"), t_b.peek()        # peek 는 값이 없으면 None — 기록도 없음
got_times = swr.served_times()
check("이번 화면에서 쓴 것만, 받은 시각과 함께",
      set(got_times) == {"load_alpha"} and got_times["load_alpha"][0] <= got_times["load_alpha"][1] <= time.time(),
      str(got_times))
x_at = swr._store[t_a.key(("x",), {})].at
check("같은 출처를 여러 번 받았으면 가장 오래된 시각이 앞", got_times["load_alpha"][0] == x_at)
t_b()
check("peek 로 읽은 값도 적는다", t_b.peek() == "b" and "load_beta" in swr.served_times())
with ThreadPoolExecutor(1) as ex:
    other = ex.submit(lambda: (t_a("z"), swr.served_times())[1]).result()
check("뒤에서 도는 스레드의 받기는 섞이지 않는다",
      other == {} and len(swr._tl.served["load_alpha"]) == 2, str(other))
swr.reset_stale_served()
check("화면을 새로 그리면 비운다", swr.served_times() == {})

want = {"FETCH_LABELS", "FETCH_OLD_SEC"}
body = [n for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in ("_fetched_line", "_age_text"))
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in want)]
ns2 = {"dt": dt, "time": time, "KST": ZoneInfo("Asia/Seoul")}
exec(compile(ast.Module(body=body, type_ignores=[]), "app.py", "exec"), ns2)  # noqa: S102
line_fn, labels = ns2["_fetched_line"], ns2["FETCH_LABELS"]
now_ = dt.datetime(2026, 11, 12, 11, 5, tzinfo=ZoneInfo("Asia/Seoul")).timestamp()
html_ = line_fn({"load_all": (now_ - 40, now_ - 40),
                 "load_macro": (now_ - 7 * 60, now_ - 60),
                 "load_kr_screens": (now_ - 4.5 * 3_600, now_ - 4.5 * 3_600),
                 "load_dividends": (now_ - 30 * 3_600, now_),
                 "모르는_함수": (now_, now_)}, now_)
check("시:분으로 적는다", "시세 11:04" in html_ and "경제지표(FRED) 10:58" in html_, html_)
check("오래된 것은 몇 시간 전인지 함께, 눈에 띄게",
      '<span class="old">국내 재무 심사 06:35 <i>4시간 전</i></span>' in html_
      or '<span class="old">국내 재무 심사 06:35 <i>5시간 전</i></span>' in html_, html_)
check("오늘 것이 아니면 날짜도", "배당 11/11 05:05" in html_, html_)
check("이름표가 없는 것은 적지 않는다", "모르는_함수" not in html_)
check("쓴 것이 없으면 줄 자체가 없다", line_fn({}, now_) == "")
check("시세가 맨 앞", html_.index("시세 ") < html_.index("경제지표"))
loaders = set(re.findall(r"^@swr\.cached\([^\n]*\n(?:[^\n]*\n)??def (\w+)\(", src, re.M))
loaders |= set(re.findall(r"wait_fresh=config\.QUOTE_WAIT_FRESH_SEC\)\ndef (\w+)\(", src))
check("받기 함수를 전부 찾았다", len(loaders) >= 30 and "load_all" in loaders, str(len(loaders)))
check("모든 받기 함수에 이름표가 있다", not (loaders - set(labels)), str(sorted(loaders - set(labels))))
check("없는 함수의 이름표가 없다", not (set(labels) - loaders), str(sorted(set(labels) - loaders)))
check("화면마다 자리를 잡고 다 그린 뒤 채운다",
      src.index("times_slot = st.empty()") < src.index("times_slot.markdown(")
      and "swr.served_times()" in src)
check("스타일이 있다", ".dash-times" in theme.build_css("kr"))

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
