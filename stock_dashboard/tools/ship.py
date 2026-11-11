"""
보낼 파일 목록을 **기계가** 정합니다.

왜 필요한가: 2026-11-11 에 두 번 연속으로 "변경된 파일만" 을 손으로
골랐다가 빠뜨렸습니다. 한 번은 tools/diagnose.py, 다음은
sources/kr_exports.py 와 sources/yahoo.py 였습니다. 기억으로 고르면
반드시 틀립니다 — 기억이 좋고 나쁘고의 문제가 아니라, 편집한 파일과
보낼 파일이 **다른 목록**이기 때문입니다 (의존 파일, 앞 턴에서 고쳤는데
아직 안 보낸 파일 등).

그래서 마지막으로 **실제로 보낸** 매니페스트를 `.shipped.json` 에
남겨 두고, 지금 상태와 해시로 비교합니다. 사람이 판단할 자리가 없습니다.

    python -m tools.ship --diff     달라진 파일만 출력 (한 줄에 하나)
    python -m tools.ship --mark     지금 상태를 '보냈음' 으로 기록
    python -m tools.ship --restore  실수로 --mark 했을 때 되돌리기

**--mark 는 실제로 보낸 직후에만** 돌립니다. 보내기 전에 돌리면 기준점이
사라져서 다음에 전체를 보내야 합니다 (실제로 한 번 그랬습니다).
    python -m tools.ship            요약

BUILD.json 과 .shipped.json 의 차이:
  BUILD.json    앱이 켜질 때 자기 파일을 검사하는 기준 (저장소에 올라감)
  .shipped.json 내가 마지막으로 보낸 상태의 기록 (저장소에 안 올라감)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buildstamp  # noqa: E402

SHIPPED = ".shipped.json"


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_shipped(root: str) -> dict[str, str]:
    path = os.path.join(root, SHIPPED)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data.get("files", data) if isinstance(data, dict) else {}


def changed(root: str) -> tuple[list[str], list[str], list[str]]:
    """(바뀐 것, 새로 생긴 것, 지워진 것)."""
    now = buildstamp.build_manifest(root)
    before = load_shipped(root)
    modified = sorted(k for k, v in now.items()
                      if k in before and before[k] != v)
    added = sorted(k for k in now if k not in before)
    removed = sorted(k for k in before if k not in now)
    return modified, added, removed


def mark(root: str) -> int:
    """지금 상태를 '보냈음' 으로 기록합니다.

    **직전 기록을 .shipped.prev.json 으로 남깁니다.** 보내지도 않고
    실수로 --mark 를 돌리면 '무엇이 바뀌었는지' 기준점이 사라지는데,
    그러면 다시 전체를 보내는 수밖에 없습니다. 실제로 한 번 그랬습니다.
    """
    path = os.path.join(root, SHIPPED)
    if os.path.exists(path):
        prev = os.path.join(root, SHIPPED.replace(".json", ".prev.json"))
        try:
            with open(path, encoding="utf-8") as src, \
                    open(prev, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        except OSError:
            pass
    now = buildstamp.build_manifest(root)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"files": now}, fh, ensure_ascii=False, indent=1,
                  sort_keys=True)
    return len(now)


def restore(root: str) -> bool:
    """실수로 --mark 한 것을 되돌립니다."""
    prev = os.path.join(root, SHIPPED.replace(".json", ".prev.json"))
    if not os.path.exists(prev):
        return False
    with open(prev, encoding="utf-8") as src, \
            open(os.path.join(root, SHIPPED), "w", encoding="utf-8") as dst:
        dst.write(src.read())
    return True


def main(argv: list[str]) -> int:
    root = _root()
    modified, added, removed = changed(root)

    if "--restore" in argv:
        ok = restore(root)
        print("직전 기록으로 되돌렸습니다." if ok
              else "되돌릴 기록이 없습니다.")
        return 0 if ok else 1

    if "--mark" in argv:
        n = mark(root)
        print(f"{SHIPPED} 기록 — {n}개 파일을 '보냈음' 으로 표시했습니다.")
        return 0

    # 보낼 목록에는 BUILD.json 을 **항상** 넣습니다. 받는 쪽 앱이 자기
    # 파일을 검사하는 기준이라, 이게 빠지면 검사가 옛 기준으로 돕니다.
    send = modified + added
    if send:
        send = send + ["BUILD.json"]

    if "--diff" in argv:
        for path in send:
            print(path)
        return 0

    if not load_shipped(root):
        print(f"{SHIPPED} 가 없습니다 — 비교 기준이 없으므로 "
              "**전체를 보내야 합니다.**")
        print("보낸 뒤 `python -m tools.ship --mark` 를 돌리십시오.")
        return 1

    print(f"바뀐 파일 {len(modified)} · 새 파일 {len(added)} · "
          f"지운 파일 {len(removed)}")
    for path in modified:
        print(f"  ~ {path}")
    for path in added:
        print(f"  + {path}")
    for path in removed:
        print(f"  - {path}  (받는 쪽에서 지워야 합니다)")
    if send:
        print("\n보낼 목록:")
        print("  " + " ".join(send))
    else:
        print("\n보낼 것이 없습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
