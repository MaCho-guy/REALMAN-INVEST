"""패키징 직전에 BUILD.json 을 갱신합니다.

    python -m tools.stamp

앱이 시작할 때 이 목록과 실제 파일을 비교해, 일부만 올라간 경우
'components.py 가 오래된 버전입니다' 라고 알려줍니다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import buildstamp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    data = buildstamp.write_manifest(ROOT)
    print(f"{buildstamp.MANIFEST} 갱신 — 검사 대상 {len(data)}개 파일")
    rep = buildstamp.verify(ROOT)
    print("검사:", "일치" if rep.ok else rep.message())
