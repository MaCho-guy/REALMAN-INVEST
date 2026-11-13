"""main 에 올리기 (배포) — 검사를 통과해야만 올립니다 (11/13 사고 뒤 추가).

11/13 에 있었던 일: ① 작업 브랜치에만 올리고 main(배포)에는 안 올림 ② 파이썬 캐시(.pyc)가
커밋에 섞임 ③ 다른 대화가 main 을 먼저 고쳐 밀어 넣기가 거절됨 ④ 클래스 겹침으로 화면이 깨짐.

하는 일 (하나라도 실패하면 멈춤 · 아무것도 안 올림):
  1. 커밋 안 된 변경 · 올라간 .pyc 가 없는지
  2. origin/main 을 받아 그 위로 다시 얹기(rebase) — 충돌이면 멈춤
  3. BUILD.json 이 지금 파일과 맞는지(tools.stamp --check), 테스트 전부(tools.run_tests)
  4. git push origin HEAD:main → origin/main 커밋 = 로컬 커밋인지 확인

    python -m tools.push_main          (stock_dashboard 폴더에서)
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)


def sh(*args, cwd=ROOT, check=True) -> str:
    p = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"멈춤 — {' '.join(args)}\n{p.stdout}{p.stderr}")
    return (p.stdout or "").strip()


def main() -> int:
    dirty = [ln for ln in sh("git", "status", "--porcelain").splitlines()
             if not ln.startswith("??")]
    if dirty:
        raise SystemExit("멈춤 — 커밋 안 된 변경이 있습니다:\n" + "\n".join(dirty))
    tracked_pyc = [f for f in sh("git", "ls-files").splitlines()
                   if f.endswith(".pyc") or "__pycache__/" in f]
    if tracked_pyc:
        raise SystemExit("멈춤 — 캐시 파일이 저장소에 있습니다: " + ", ".join(tracked_pyc[:5]))
    sh("git", "fetch", "-q", "origin", "main")
    p = subprocess.run(["git", "rebase", "origin/main"], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=ROOT)
        raise SystemExit("멈춤 — origin/main 위로 얹다가 충돌 (다른 대화가 같은 곳을 고침):\n"
                         + p.stdout + p.stderr)
    env_py = [sys.executable]
    if subprocess.run(env_py + ["-m", "tools.stamp", "--check"], cwd=HERE).returncode != 0:
        raise SystemExit("멈춤 — BUILD.json 이 지금 파일과 다릅니다 (python -m tools.stamp 후 커밋)")
    if subprocess.run(env_py + ["-m", "tools.run_tests"], cwd=HERE).returncode != 0:
        raise SystemExit("멈춤 — 테스트 실패. 올리지 않았습니다")
    sh("git", "push", "-q", "origin", "HEAD:main")
    sh("git", "fetch", "-q", "origin", "main")
    local, remote = sh("git", "rev-parse", "--short", "HEAD"), sh("git", "rev-parse", "--short",
                                                                   "origin/main")
    if local != remote:
        raise SystemExit(f"멈춤 — 올렸는데 main({remote}) ≠ 로컬({local})")
    print(f"배포됨 — main = {local}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
