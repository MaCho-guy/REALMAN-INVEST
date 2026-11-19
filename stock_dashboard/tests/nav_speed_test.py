"""
섹션 버튼 · 동시 받기 테스트 — **실제 app.py 의 함수를 가짜 st 위에서 돌립니다.**

2026-11-11 두 가지 불만:
  (1) "왼쪽 단추 모양이 잘 안 보인다" → 라디오 대신 진짜 버튼
  (2) "너무 느리다" → 서로 기다릴 필요 없는 데이터 받기를 동시에

스트림릿이 없어 app.py 를 통째로 돌릴 수 없으므로 필요한 함수만 AST 로
떼어 실행합니다.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys
import threading
import time

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
import config  # noqa: E402
import perf  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


# ──────────────────────────────────────────────────────────────────────────────
print("=== perf: 동시 실행이 합이 아니라 최댓값 ===")
calls = {f"j{i}": (lambda d=d: (time.sleep(d), d)[1])
         for i, d in enumerate((0.3, 0.3, 0.3, 0.3))}
log = perf.RunLog()
t0 = time.perf_counter()
out = perf.run_parallel(calls, log)
wall = time.perf_counter() - t0
check("결과가 전부 돌아온다", len(out) == 4)
check("1.2초 일을 0.6초 안에", wall < 0.6, f"{wall:.2f}s")
check("항목별 시간이 기록된다", len(log.items) == 4
      and all(t.seconds >= 0.29 for t in log.items))
check("동시 처리 효과를 한 줄로 말한다", "동시에 받아" in log.summary_line(),
      log.summary_line())

boom = {"ok": lambda: 1, "bad": lambda: 1 / 0}
log = perf.RunLog()
out = perf.run_parallel(boom, log)
check("실패한 항목은 결과에서 빠지고 나머지는 남는다", out == {"ok": 1})
check("실패도 기록된다", any(t.error == "ZeroDivisionError" for t in log.items))

seen = []
perf.run_parallel({"a": lambda: seen.append(threading.current_thread().name)},
                  None, initializer=lambda: setattr(
                      threading.current_thread(), "name", "ctx-attached"))
check("initializer 가 작업 스레드에서 실행된다", seen == ["ctx-attached"], str(seen))

bad_init = perf.run_parallel({"a": lambda: 2}, None,
                             initializer=lambda: (_ for _ in ()).throw(RuntimeError()))
check("initializer 가 터져도 일은 그대로 한다", bad_init == {"a": 2}, str(bad_init))

log = perf.RunLog()
log.add("시세", 0.001)
check("전부 캐시면 그렇게 말한다", "바로 나왔습니다" in log.summary_line())

# ──────────────────────────────────────────────────────────────────────────────
src = pathlib.Path("app.py").read_text(encoding="utf-8")
tree = ast.parse(src)
WANT = ("_peek_section", "_nav_button", "_section_nav", "_sub_nav", "_sub_pick", "_section_jobs",
        "_prefetch", "_ctx_initializer", "_peek_market", "_quotes_fn")
fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in WANT]
check("필요한 함수가 app.py 에 있다", len(fns) == len(WANT),
      str(sorted(set(WANT) - {f.name for f in fns})))
mod = ast.Module(body=fns, type_ignores=[])


class QP(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


class FakeSt:
    def __init__(self, session=None, query=None, click=None, old=False):
        self.session_state = dict(session or {})
        self.query_params = QP(query or {})
        self.buttons = []          # (label, key, type)
        self.md = []
        self._click = click        # 이번 실행 직전에 누른 버튼 key
        self._old = old
        self.segs = []             # (key, options, on_change, args) — 안쪽 탭

    def segmented_control(self, label, options, key=None, format_func=None,
                          label_visibility=None, on_change=None, args=()):
        self.segs.append((key, list(options), on_change, args,
                          [format_func(o) for o in options] if format_func else list(options)))
        return self.session_state.get(key)

    def markdown(self, html, **k):
        self.md.append(html)

    def button(self, label, key=None, type="secondary", on_click=None,
               args=(), width=None, use_container_width=None):
        if self._old and width is not None:
            raise TypeError("unexpected keyword argument 'width'")
        self.buttons.append((label, key, type))
        return False


def run_nav(market, session=None, query=None, click_section=None, old=False):
    """click_section: 사용자가 누른 섹션 — 스트림릿처럼 콜백을 먼저 실행한 뒤
    스크립트를 처음부터 다시 돌립니다."""
    st = FakeSt(session, query, old=old)
    ns = {"st": st, "config": config, "threading": threading, "perf": perf}
    exec(compile(mod, "app.py", "exec"), ns)
    labels = dict(config.tab_labels())
    first = ns["_section_nav"](market, labels)
    if click_section is None:
        return first, st
    # 콜백: 세션 값을 바꾸고 다시 실행
    st.session_state[f"nav_{market}"] = click_section
    st.buttons, st.md = [], []
    return ns["_section_nav"](market, labels), st


print("\n=== 섹션 버튼 ===")
got, st = run_nav("kr")
kr_keys = config.market_tab_keys("kr")
check("처음 열면 첫 섹션", got == kr_keys[0], got)
# 11/19 메뉴 7칸 (사용자 승인): 버튼은 화면마다가 아니라 **메뉴(묶음)마다** 하나
kr_groups = [g for g in config.tab_groups("kr") if g[1]]
check("시장의 메뉴마다 버튼 하나 (화면 수가 아니라 메뉴 수)",
      len(st.buttons) == len(kr_groups) == 7 and len(kr_keys) > len(kr_groups),
      f"{len(st.buttons)} vs 메뉴 {len(kr_groups)} · 화면 {len(kr_keys)}")
check("버튼 글자는 메뉴 이름", [b[0] for b in st.buttons] == [g for g, _i in kr_groups],
      str([b[0] for b in st.buttons]))
prim = [b for b in st.buttons if b[2] == "primary"]
check("지금 섹션 하나만 남색(primary)", len(prim) == 1
      and prim[0][1] == f"navbtn_kr_{kr_keys[0]}", str(prim))
check("묶음 머리글 줄은 따로 없다 — 메뉴 이름이 곧 버튼",
      not any('class="dash-navhead"' in h for h in st.md))
check("내비 칸 표식이 있다", any("dash-navmark" in h for h in st.md))
check("주소창에 섹션을 남긴다", st.query_params.get("s") == kr_keys[0])

got, st = run_nav("kr", click_section="sector_heat")
prim = [b for b in st.buttons if b[2] == "primary"]
check("누른 화면이 든 메뉴가 바로 남색으로 (버튼 key = 그 메뉴의 첫 화면)",
      got == "sector_heat" and prim and prim[0][1] == "navbtn_kr_sector_heat"
      and prim[0][0] == "시장", str(prim))
check("주소도 따라간다", st.query_params.get("s") == "sector_heat")
got, st = run_nav("kr", click_section="macro")
prim = [b for b in st.buttons if b[2] == "primary"]
check("메뉴 안의 둘째 화면에 있어도 그 메뉴가 남색", got == "macro"
      and len(prim) == 1 and prim[0][0] == "시장", str(prim))

got, _ = run_nav("kr", query={"s": "kr_flows"})
check("새로고침해도 주소의 섹션으로", got == "kr_flows", got)
got, _ = run_nav("us", query={"s": "sector_heat"})
check("다른 시장의 섹션 주소면 첫 섹션으로 (오류 아님)",
      got == config.market_tab_keys("us")[0], got)
got, _ = run_nav("us", session={"nav_us": "us_flows", "nav_kr": "sector_heat"})
check("시장마다 보던 자리를 따로 기억", got == "us_flows", got)
got, st = run_nav("kr", old=True)
check("width 를 모르는 예전 스트림릿에서도 그려진다", len(st.buttons) == len(kr_groups))
keys = [b[1] for b in run_nav("kr")[1].buttons] + [b[1] for b in run_nav("us")[1].buttons]
check("버튼 key 가 겹치지 않는다 (겹치면 스트림릿이 오류)", len(keys) == len(set(keys)))

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 안쪽 탭 (11/19 메뉴 7칸) ===")


def run_sub(market, active, session=None):
    st = FakeSt(session)
    ns = {"st": st, "config": config, "threading": threading, "perf": perf}
    exec(compile(mod, "app.py", "exec"), ns)
    ns["_sub_nav"](market, active)
    return st, ns


st, ns = run_sub("kr", "macro")
check("메뉴에 화면이 여럿이면 안쪽 탭을 그린다", len(st.segs) == 1
      and st.segs[0][1] == ["sector_heat", "macro", "calendar"], str(st.segs[:1]))
check("안쪽 탭 표식이 있다 (CSS 가 이 표식으로 찾음)", any("dash-submark" in h for h in st.md))
check("지금 화면이 골라진 채로 그려진다", st.session_state.get(st.segs[0][0]) == "macro")
check("안쪽 탭 이름은 화면이 '무엇' 인지로 (메뉴 이름과 안 겹치게)",
      run_sub("kr", "timing")[0].segs[0][4] == ["차트 조건", "거래 스크리너", "실험"]
      and run_sub("kr", "holdings")[0].segs[0][4] == ["전체", "종목 상세", "수급"])
st1, _ = run_sub("kr", "summary")
check("화면이 하나뿐인 메뉴에는 안쪽 탭이 없다", st1.segs == [] and st1.md == [])
# 누르기: 위젯 값이 바뀌고 → 콜백이 내비 상태를 바꾸고 → 다음 실행이 그 화면을 그림
key, _opts, cb, args, _names = st.segs[0]
st.session_state[key] = "calendar"
ns["st"] = st
cb(*args)
check("안쪽 탭을 누르면 내비 상태가 그 화면으로", st.session_state.get("nav_kr") == "calendar")
st.session_state[key] = None            # 고른 칸을 다시 누르면 선택이 풀려 None
cb(*args)
check("고른 칸을 다시 눌러도(None) 화면이 바뀌지 않는다",
      st.session_state.get("nav_kr") == "calendar")
st2, _ = run_sub("kr", "calendar", session=dict(st.session_state))
check("다음 실행에서 풀린 선택을 지금 화면으로 되돌린다",
      st2.session_state.get(st2.segs[0][0]) == "calendar")
check("미국에는 거래 스크리너가 없다 — 안쪽 탭 둘",
      run_sub("us", "timing")[0].segs[0][1] == ["timing", "paper"])
check("주소는 여전히 화면 key (?s=macro) — 예전 즐겨찾기가 그대로 열린다",
      run_nav("kr", query={"s": "semi_research"})[0] == "semi_research")

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 화면별 동시 받기 목록 ===")


class _Src:
    @staticmethod
    def key_fingerprint():
        return "fp"


called = []


def _mk(name):
    def f(*a, **k):
        called.append(name)
        time.sleep(0.2)
        return name
    return f


loaders = ["load_all", "load_filings", "load_dart_disclosures",
           "load_inventory_trends", "load_us_inventory_trends", "load_macro",
           "load_sector_heat", "load_feargreed", "load_vix", "load_sector_news",
           "load_market_filings", "load_kr_macro", "load_inflation",
           "load_liquidity", "load_kr_exports", "load_screens", "load_kr_screens",
           "load_kr_vol_profiles", "load_kr_value_rows", "load_chart_rows",
           "load_daily_brief", "load_close_headlines", "load_research",
           "load_release_dates"]
st = FakeSt()
ns = {"st": st, "config": config, "threading": threading, "perf": perf,
      "dart": _Src, "fred": _Src}
ns.update({n: _mk(n) for n in loaders})
ns.update({"SOFT_SECTIONS": ("summary", "holdings"), "PREFETCH_BUDGET": 3.0})
exec(compile(mod, "app.py", "exec"), ns)

jobs = ns["_section_jobs"]("summary", "kr", False)
check("요약(한국)은 시세+공시+재고+매크로+섹터를 같이",
      {"시세", "미국 공시", "국내 공시", "국내 재고 추세", "미국 재고 추세",
       "매크로", "섹터 온도"} <= set(jobs), str(sorted(jobs)))
check("요약(한국)은 미국 심리를 안 받는다", "공포탐욕" not in jobs)
jobs_us = ns["_section_jobs"]("summary", "us", False)
check("요약(미국)은 섹터 대신 공포탐욕·VIX",
      "섹터 온도" not in jobs_us and {"공포탐욕", "VIX"} <= set(jobs_us))
for sec in config.market_tab_keys("kr") + config.market_tab_keys("us"):
    check(f"{sec}: 어느 화면이든 시세는 같이", "시세" in ns["_section_jobs"](sec, "kr", False))
_most = max(((len(ns["_section_jobs"](sec, m, False)), f"{m}/{sec}")
             for m in ("kr", "us") for sec in config.market_tab_keys(m)))
check("어느 화면의 받기 수도 동시 상한(perf.MAX_WORKERS) 안 — 넘으면 한 바퀴 더 기다림",
      _most[0] <= perf.MAX_WORKERS, f"가장 많은 {_most[1]} {_most[0]}개 / 상한 {perf.MAX_WORKERS}")

log = perf.RunLog()
called.clear()
t0 = time.perf_counter()
ns["_prefetch"]("summary", "kr", False, log)
wall = time.perf_counter() - t0
# 0.6초는 '한 바퀴(0.2초) + CI 여유'. 상한보다 많으면 두 바퀴(0.4초)에 CI 지연이
# 더해져 넘습니다(11/16 CI 0.70~0.74초).
check("요약의 13가지를 동시에 (0.2초×13 → 0.6초 안, 11/16 섹터 뉴스 추가)", wall < 0.6 and len(called) == 13,
      f"{wall:.2f}s, {len(called)}건")
called.clear()
ns["_prefetch"]("summary", "kr", True, perf.RunLog())
check("데모 모드에서는 받지 않는다", called == [])

ns["load_macro"] = lambda *a: 1 / 0
called.clear()
ns["_prefetch"]("summary", "kr", False, perf.RunLog())
check("하나가 터져도 나머지는 받아 둔다", len(called) == 12, str(called))

print("\n=== 느린 하나가 첫 화면을 붙잡지 않는다 ===")
import threading as _th  # noqa: E402
_gate = _th.Event()
_slow_done = []


def _slow():
    _gate.wait(5)
    _slow_done.append(1)
    return "늦은 값"


_log = perf.RunLog()
_t0 = time.perf_counter()
_got = perf.run_parallel({"빠름": lambda: 1, "느림": _slow}, _log, budget=0.3)
_wall = time.perf_counter() - _t0
check("정한 시간만 기다린다", _wall < 1.0, f"{_wall:.2f}s")
check("끝난 것은 돌려준다", _got == {"빠름": 1}, str(_got))
check("못 끝낸 것을 기록한다",
      any(t.name == "느림" and t.error == "뒤에서 계속" for t in _log.items))
check("한 줄 요약에 드러난다", "뒤에서 계속" in _log.summary_line())
_gate.set()
time.sleep(0.2)
check("못 끝낸 것은 뒤에서 끝까지 돈다", _slow_done == [1])
check("시간을 안 주면 전부 기다린다",
      perf.run_parallel({"a": lambda: (time.sleep(0.2), 2)[1]}, None) == {"a": 2})
check("요약·내 종목만 먼저 그린다",
      'budget = PREFETCH_BUDGET if section in SOFT_SECTIONS else None' in src)

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 고정 확인 ===")
check("라디오 내비가 남아 있지 않다", 'st.radio(\n            "섹션"' not in src)
check("화면 맨 아래 속도 한 줄", "log.summary_line()" in src)
check("시세 캐시가 20초가 아니다", config.CACHE_TTL_SEC >= 60)
check("자동 갱신은 기본 꺼짐", config.AUTO_REFRESH_DEFAULT is False)
theme_src = pathlib.Path("theme.py").read_text(encoding="utf-8")
check("라디오 동그라미를 전역으로 숨기지 않는다",
      'div[role="radiogroup"] > label > div:first-child' not in theme_src,
      "다른 라디오(대상·색 규칙)의 선택 표시까지 지웠습니다")
check("버튼 꾸밈은 내비 칸 안에만",
      ':has(.dash-navmark) button[kind="secondary"]' in theme_src)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
