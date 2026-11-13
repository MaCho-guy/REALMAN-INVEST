"""화면 부품끼리 CSS 클래스가 겹치지 않는지 (2026-11-13 사고 뒤 추가).

11/13 15:37 근거 탭 카드가 통째로 깨졌습니다 — 새로 만든 체크리스트(render_checklist)가
'품질 9개 기준' 줄(render_screen)의 클래스 `dash-check` 를 그대로 써서, 두 부품의 모양
규칙이 서로 섞였습니다. 테스트는 다 통과했고 폰에서야 보였습니다.

이 검사는 '래칫'입니다: 지금 여러 함수가 같이 쓰는 dash-* 클래스 목록을
tests/css_shared_classes.json 에 적어 두고, **새 함수가 기존 클래스를 같이 쓰기 시작하면**
실패합니다. 일부러 같이 쓰는 것(공통 부품 · 링크 등)이면 목록을 갱신하십시오:

    python tests/css_class_test.py --update
"""
from __future__ import annotations

import ast
import collections
import json
import os
import re
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "tests/css_shared_classes.json"


def shared_map() -> dict[str, list[str]]:
    src = open("components.py", encoding="utf-8").read()
    used: dict[str, set] = collections.defaultdict(set)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(src, node) or ""
            for cls in re.findall(r"class=\\?[\"']([^\"'{}]+)", seg):
                for c in cls.split():
                    if c.startswith("dash-"):
                        used[c].add(node.name)
    return {k: sorted(v) for k, v in sorted(used.items()) if len(v) > 1}


if __name__ == "__main__":
    now = shared_map()
    if "--update" in sys.argv:
        with open(BASE, "w", encoding="utf-8") as fh:
            json.dump(now, fh, ensure_ascii=False, indent=1)
        print(f"갱신: 같이 쓰는 클래스 {len(now)}개")
        sys.exit(0)
    base = json.load(open(BASE, encoding="utf-8"))
    bad = []
    for cls, fns in now.items():
        new = sorted(set(fns) - set(base.get(cls, [])))
        if new and (cls in base or len(fns) > 1):
            bad.append(f"{cls}: {', '.join(new)} 가 새로 같이 씀 (전: {', '.join(base.get(cls, [])) or '한 함수만'})")
    for b in bad:
        print("  FAIL", b)
    print(f"  OK   dash-* 클래스 {len(now)}개 같이 쓰기 확인" if not bad else "")
    print("전부 통과" if not bad else f"실패 {len(bad)}건 — 일부러면 --update")
    sys.exit(1 if bad else 0)
