"""
analysis/ 폴더 구조를 만들어 둡니다.

실행:
    cd stock_dashboard
    python -m tools.scaffold_analysis

config 의 analysis_key 를 가진 모든 종목에 대해 폴더와 meta.json 틀을 만듭니다.
이미 있는 파일은 건드리지 않습니다 (덮어쓰지 않음).

분석 HTML 자체는 Claude 스킬이 생성합니다. 이 스크립트는 자리만 만듭니다.
"""

from __future__ import annotations

import json
import os
import sys

import config

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(BASE, config.ANALYSIS_DIR)


def main() -> int:
    instruments = config.analysis_instruments()
    os.makedirs(ANALYSIS, exist_ok=True)

    created, skipped = 0, 0

    for inst in instruments:
        folder = os.path.join(ANALYSIS, inst.analysis_key)
        os.makedirs(folder, exist_ok=True)

        meta_path = os.path.join(folder, "meta.json")
        if os.path.exists(meta_path):
            skipped += 1
            continue

        meta = {
            "name": inst.name,
            "generated": "",
            "mode": "",
            "sources": [],
            "note": "분석 미생성 — Claude 스킬로 생성 후 이 파일을 채우십시오.",
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        created += 1

    print(f"analysis/ 준비 완료 — 새로 만든 폴더 {created}개, 기존 유지 {skipped}개")
    print(f"경로: {ANALYSIS}\n")
    print("종목별 생성 명령:")
    for inst in instruments:
        print(f"  {inst.name} ({inst.analysis_key})")
        print(f"    /company-decoder-korean {inst.name}")
        print(f"    /company-story-korean {inst.name}")
        print(f"    /price-decoder-korean {inst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
