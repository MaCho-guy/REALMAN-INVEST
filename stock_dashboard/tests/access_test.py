"""
잠금 테스트 (11/13) — '내 종목' · 보유 · 진단이 비밀번호 뒤에 있는지.

  1. access.py 규칙: 비밀번호 없음/짧음 = 늘 잠김, 맞으면 그 세션만 풀림,
     5번 틀리면 60초 막힘, 비밀번호를 바꾸면 풀린 세션도 잠김
  2. app.py 구조: 보유를 직접 읽는 곳이 _load_portfolio 하나뿐 · 내 종목 탭과
     진단 패널 호출이 잠금 확인 뒤에 있음
  3. 인증키 지우개가 비밀번호 · 보유 원문도 지움 · .gitignore 에 secrets.toml
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
import access  # noqa: E402
from sources import safe  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


print("=== access 규칙 ===")
os.environ.pop(access.PASSWORD_ENV, None)
s: dict = {}
check("비밀번호 없으면 잠김", not access.unlocked(s))
check("비밀번호 없으면 풀 수 없음", not access.try_unlock(s, "anything")[0])
os.environ[access.PASSWORD_ENV] = "short"
check("8자 미만이면 잠김", not access.configured() and not access.try_unlock(s, "short")[0])

os.environ[access.PASSWORD_ENV] = "correct-horse-9"
s = {}
check("처음엔 잠김", not access.unlocked(s))
ok, msg = access.try_unlock(s, "wrong-pass", now=1000)
check("틀리면 안 풀림", not ok and "1/5" in msg, msg)
ok, _ = access.try_unlock(s, "correct-horse-9", now=1001)
check("맞으면 풀림", ok and access.unlocked(s))
check("세션 상태에 비밀번호 원문이 없다",
      all("correct-horse-9" not in str(v) for v in s.values()), str(s))
other: dict = {}
check("다른 세션은 그대로 잠김", not access.unlocked(other))
os.environ[access.PASSWORD_ENV] = "new-password-77"
check("비밀번호를 바꾸면 풀린 세션도 잠김", not access.unlocked(s))
access.lock(s)
check("잠그기", not access.unlocked(s))

s = {}
for i in range(access.MAX_TRIES):
    ok, msg = access.try_unlock(s, f"bad{i}", now=2000 + i)
check("5번 틀리면 막힘", "60초" in msg, msg)
ok, msg = access.try_unlock(s, "new-password-77", now=2010)
check("막힌 동안은 맞아도 안 풀림", not ok and "뒤에" in msg, msg)
ok, _ = access.try_unlock(s, "new-password-77", now=2005 + access.LOCK_SEC + 1)
check("시간이 지나면 다시 풀 수 있음", ok)

print("\n=== app.py 구조 ===")
src = pathlib.Path("app.py").read_text(encoding="utf-8")
direct = [m.start() for m in re.finditer(r"portfolio\.load\(", src)]
check("보유를 직접 읽는 곳은 _load_portfolio 하나", len(direct) == 1, f"{len(direct)}곳")
lp = src.split("def _load_portfolio(")[1].split("\ndef ")[0]
check("_load_portfolio 가 잠금 먼저 확인", lp.index("access.unlocked") < lp.index("portfolio.load("))
body = src.split("def render_body(")[1].split("\ndef ")[0]
hold = body.split('elif active == "holdings":')[1].split("elif active ==")[0]
check("내 종목 탭은 잠금 확인 뒤", hold.index("access.unlocked") < hold.index("render_holdings_tab("))
check("잠겼을 때 잠금 화면", "_render_lock_gate()" in hold)
ctrl = src.split("def controls()")[1].split("\ndef ")[0]
diag = ctrl.split("render_diag_panel()")[0][-400:]
check("진단 패널은 잠금 확인 뒤", "access.unlocked" in diag)
calls = [m.start() for m in re.finditer(r"render_holdings_tab\(", src)]
check("내 종목 화면을 부르는 곳은 한 곳(정의 제외)", len(calls) == 2, f"{len(calls)}")

print("\n=== 지우개 · .gitignore ===")
os.environ["PORTFOLIO"] = "MSFT:10@410.5, 005930:30@71000"
check("비밀번호 지움", "new-password-77" not in safe.scrub("pw new-password-77 end"))
check("보유 원문 지움", "MSFT:10@410.5" not in safe.scrub(
    "raw=MSFT:10@410.5, 005930:30@71000"))
gi = pathlib.Path(".gitignore").read_text(encoding="utf-8")
check(".gitignore 에 secrets.toml", "secrets.toml" in gi)
check(".gitignore 에 .env", ".env" in gi)

print(f"\n{'통과' if not FAILURES else '실패: ' + ', '.join(FAILURES)}")
sys.exit(1 if FAILURES else 0)
