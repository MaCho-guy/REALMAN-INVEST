"""
공시 분석 자료 저장소.

================================================================================
왜 이런 구조인가 — 읽어주십시오
================================================================================
`/company-decoder-korean`, `/company-story-korean`, `/price-decoder-korean` 는
**Claude 세션에서 실행되는 스킬**입니다. 웹검색·공시 열람·계산을 수행하고
HTML 카드를 만들어 냅니다. Streamlit 앱은 Claude 세션이 아니므로
**앱 코드가 이 스킬을 직접 호출할 방법이 없습니다.**

그래서 생성과 표시를 분리했습니다.

    [생성]  Claude 에게 "MU 기업 해독기 돌려줘" 라고 요청
              -> 스킬이 분석 수행
              -> 결과 HTML 을 analysis/MU/decoder.html 로 저장

    [표시]  이 모듈이 analysis/ 폴더를 읽어서 대시보드 '공시 분석' 탭에 렌더링

즉 대시보드는 **분석 결과의 뷰어**입니다. 분석 자체는 Claude 가 돌립니다.
자료가 없으면 "미생성" 상태로 표시하고 생성 방법을 안내합니다.

폴더 구조:

    analysis/
    ├── MU/
    │   ├── meta.json          # {"name","generated","mode","sources":[...]}
    │   ├── decoder.html       # company-decoder-korean 산출물
    │   ├── story.html         # company-story-korean 산출물
    │   └── price.html         # price-decoder-korean 산출물
    ├── 005930/
    │   └── ...
    └── ...

meta.json 스키마:
    {
      "name":      "Micron Technology",
      "generated": "2026-11-04",        # 생성일 (ISO)
      "mode":      "web" | "filing",    # 웹검색 기반 / 공시 업로드 기반
      "sources":   ["https://...", ...] # 참고한 1차 소스
      "note":      "선택 — 특이사항"
    }

주의: 분석은 생성 시점의 스냅샷입니다. 실적 발표가 지나면 다시 돌려야 합니다.
      이 모듈은 생성일이 90일을 넘으면 '오래됨' 경고를 띄웁니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field

#: 분석 종류 -> (파일명, 화면 라벨, 한 줄 설명)
KINDS: tuple[tuple[str, str, str], ...] = (
    ("decoder", "기업 해독기", "이 회사가 뭘로 돈을 버는지 한 장으로"),
    ("story", "기업 스토리", "지난 2~3년 공시·어닝콜의 변화와 가이던스 달성 여부"),
    ("price", "가격 판독", "역DCF — 현재 주가가 요구하는 성장률"),
)

KIND_KEYS = tuple(k for k, _l, _d in KINDS)

#: 이 일수를 넘으면 '오래됨' 경고
STALE_DAYS = 90


@dataclass
class AnalysisDoc:
    """한 종목의 분석 묶음."""

    key: str
    name: str = ""
    generated: str = ""
    mode: str = ""
    note: str = ""
    sources: list[str] = field(default_factory=list)

    #: kind -> HTML 본문. 없는 kind 는 키가 아예 없습니다.
    html: dict[str, str] = field(default_factory=dict)

    #: 읽는 중 발생한 문제
    warnings: list[str] = field(default_factory=list)

    @property
    def available_kinds(self) -> list[str]:
        return [k for k in KIND_KEYS if k in self.html]

    @property
    def missing_kinds(self) -> list[str]:
        return [k for k in KIND_KEYS if k not in self.html]

    @property
    def is_empty(self) -> bool:
        return not self.html

    @property
    def age_days(self) -> int | None:
        if not self.generated:
            return None
        try:
            made = dt.date.fromisoformat(self.generated[:10])
        except ValueError:
            return None
        return (dt.date.today() - made).days

    @property
    def is_stale(self) -> bool:
        age = self.age_days
        return age is not None and age > STALE_DAYS


def _safe_key(key: str) -> str:
    """경로 조작을 막습니다.

    분석 키는 티커(MU, AAPL)나 국내 종목코드(005930)라 영숫자·하이픈·밑줄로
    충분합니다. **점은 일부러 제외**했습니다 — 허용하면 "../.." 같은 입력이
    "....", 즉 '..' 를 포함한 문자열로 남아 경로를 읽을 때 혼동을 줍니다.
    """
    return "".join(ch for ch in key if ch.isalnum() or ch in "_-")


def load(base_dir: str, key: str) -> AnalysisDoc:
    """analysis/<key>/ 를 읽습니다. 없으면 빈 AnalysisDoc 을 반환합니다."""
    safe = _safe_key(key)
    doc = AnalysisDoc(key=safe)
    if not safe:
        doc.warnings.append(f"분석 키 '{key}' 를 쓸 수 없습니다.")
        return doc

    folder = os.path.join(base_dir, safe)
    if not os.path.isdir(folder):
        return doc

    # meta.json
    meta_path = os.path.join(folder, "meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
            if isinstance(meta, dict):
                doc.name = str(meta.get("name") or "")
                doc.generated = str(meta.get("generated") or "")
                doc.mode = str(meta.get("mode") or "")
                doc.note = str(meta.get("note") or "")
                src = meta.get("sources")
                if isinstance(src, list):
                    doc.sources = [str(s) for s in src if s]
        except (OSError, ValueError) as exc:
            doc.warnings.append(f"meta.json 읽기 실패: {exc}")

    # 분석 HTML
    for kind in KIND_KEYS:
        path = os.path.join(folder, f"{kind}.html")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            doc.warnings.append(f"{kind}.html 읽기 실패: {exc}")
            continue
        if body.strip():
            doc.html[kind] = body

    return doc


def load_all(base_dir: str, keys: list[str]) -> dict[str, AnalysisDoc]:
    return {k: load(base_dir, k) for k in keys}


def kind_label(kind: str) -> str:
    for k, label, _desc in KINDS:
        if k == kind:
            return label
    return kind


def kind_desc(kind: str) -> str:
    for k, _label, desc in KINDS:
        if k == kind:
            return desc
    return ""


def skill_command(kind: str, key: str, name: str = "") -> str:
    """Claude 에게 붙여넣을 요청문을 만들어 줍니다."""
    target = name or key
    mapping = {
        "decoder": f"/company-decoder-korean {target}",
        "story": f"/company-story-korean {target}",
        "price": f"/price-decoder-korean {target}",
    }
    return mapping.get(kind, "")
