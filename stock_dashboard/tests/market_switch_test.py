"""
시장 전환 로직 테스트 — **실제 app.py 의 함수를 실행합니다.**

샌드박스에 스트림릿이 없어 app.py 를 통째로 돌릴 수 없습니다. 대신
_market_switch / _peek_market 두 함수를 AST 로 떼어내 가짜 st 위에서
돌립니다. 프리뷰(HTML)는 다른 코드라 이 버그를 못 잡습니다.

2026-11-11 에 실제로 잡은 것: 이미 고른 시장 칸을 다시 누르면
segmented_control 이 None 을 돌려주는데, 그걸 '위젯 없음' 으로 읽고
라디오로 내려갔다가 keys.index(None) 으로 앱이 죽었습니다.
"""

from __future__ import annotations

import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ast
import pathlib
import sys

sys.path.insert(0, ".")
import config  # noqa: E402

src = pathlib.Path("app.py").read_text()
tree = ast.parse(src)
fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name in ("_market_switch", "_peek_market")]
mod = ast.Module(body=fns, type_ignores=[])

class QP(dict):
    def get(self, k, d=None): return dict.get(self, k, d)

class FakeSt:
    """스트림릿 대역 — 위젯 호출을 기록하고, 정해 둔 '사용자 선택' 을 돌려줍니다."""
    def __init__(self, session, query, seg_returns, has_seg=True):
        self.session_state = session
        self.query_params = QP(query)
        self._seg = seg_returns
        self.calls = []
        if not has_seg:
            self.segmented_control = None
    def markdown(self, *a, **k): self.calls.append("md")
    def segmented_control(self, label, opts, key=None, **k):
        self.calls.append(("seg", tuple(opts), key))
        # 사용자가 아무것도 안 눌렀으면 세션에 있던 값, 눌렀으면 그 값
        val = self._seg if self._seg != "__keep__" else self.session_state.get(key)
        self.session_state[key] = val
        return val
    def radio(self, label, opts, key=None, index=0, **k):
        self.calls.append(("radio", tuple(opts), key, index))
        return opts[index]

def run(session, query, seg, has_seg=True):
    st = FakeSt(dict(session), query, seg, has_seg)
    if not has_seg:
        st.segmented_control = None
    ns = {"st": st, "config": config}
    exec(compile(mod, "app.py", "exec"), ns)
    peek = ns["_peek_market"]()
    got = ns["_market_switch"]()
    return peek, got, st

cases = [
    ("처음 열기 (주소 없음)",          {}, {}, "__keep__"),
    ("처음 열기 (?m=us)",             {}, {"m": "us"}, "__keep__"),
    ("처음 열기 (?m=이상한값)",        {}, {"m": "xx"}, "__keep__"),
    ("한국 보다가 미국 누름",          {"market": "us", "_market_last": "kr"}, {"m": "kr"}, "__keep__"),
    ("같은 칸 다시 눌러 선택 해제",    {"market": None, "_market_last": "us"}, {"m": "us"}, None),
    ("구버전 (segmented 없음)",        {}, {"m": "us"}, "__keep__", False),
]
ok = True
for c in cases:
    name, sess, q, seg = c[:4]
    has_seg = c[4] if len(c) > 4 else True
    peek, got, st = run(sess, q, seg, has_seg)
    url = st.query_params.get("m")
    line = f"  {name:22s} 제목줄={peek:3s} 화면={got:3s} 주소=?m={url}"
    print(line)
    # 불변식: 결과는 항상 유효한 시장, 주소는 결과와 같음
    if got not in config.MARKETS or url != got:
        ok = False; print("    ✗ 불변식 위반")

# 제목줄과 화면이 어긋나는 경우가 있는지 — '처음 열기' 류는 같아야 합니다
p, g, _ = run({}, {"m": "us"}, "__keep__")
if p != g: ok = False; print("  ✗ 처음 열 때 제목줄과 화면이 다릅니다", p, g)
p, g, _ = run({"market": "us"}, {"m": "kr"}, "__keep__")
if p != g: ok = False; print("  ✗ 전환 직후 제목줄과 화면이 다릅니다", p, g)
print("\n" + "=" * 54)
if not ok:
    print("실패 있음")
    sys.exit(1)
print("전부 통과")
