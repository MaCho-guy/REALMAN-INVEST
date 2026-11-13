"""테스트 전부 돌리기 — tests/*_test.py 를 하나씩 따로 실행해 결과를 모읍니다 (11/13).

    python -m tools.run_tests          # 전부
    python -m tools.run_tests funnel   # 이름에 'funnel' 이 든 것만

GitHub Actions(.github/workflows/test.yml)와 tools/push_main.py 가 이걸 부릅니다.
실패가 하나라도 있으면 종료 코드 1.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(pattern: str = "") -> int:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    files = sorted(f for f in glob.glob(os.path.join(HERE, "tests", "*_test.py"))
                   if pattern in os.path.basename(f))
    bad = []
    for f in files:
        t0 = time.time()
        p = subprocess.run([sys.executable, f], cwd=HERE, env=env, capture_output=True,
                           text=True, timeout=600)
        out = (p.stdout or "") + (p.stderr or "")
        fails = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("FAIL")]
        name = os.path.basename(f)
        ok = p.returncode == 0
        print(f"{'OK  ' if ok else 'FAIL'} {name:32} {time.time() - t0:5.1f}s"
              + ("" if ok else f" — {fails[:3] or out.strip().splitlines()[-1:]}"))
        if not ok:
            bad.append(name)
    print(f"\n테스트 {len(files)}개 · 실패 {len(bad)}개" + (f": {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else ""))
