"""
================================================================================
파일 버전 검사 — "어느 파일이 안 올라갔는지" 를 앱이 직접 말합니다.
================================================================================

왜 필요한가:

  GitHub 웹에서 파일을 손으로 올리다 보면 일부만 올라갑니다. 지금까지
  네 번 그랬습니다:

    ModuleNotFoundError  sources/ 폴더가 통째로 빠짐
    ValueError           app.py 는 새것, 함수 반환 개수는 옛것
    AttributeError       app.py 는 새것, signals.py 는 옛것
    AttributeError       app.py 는 새것, components.py 는 옛것

  네 번 다 **배포한 뒤에야** 알았고, Streamlit Cloud 는 오류 본문을 가려서
  ("redacted to prevent data leaks") 로그를 따로 열어야 보입니다.

  이 모듈은 그걸 **앱이 뜨자마자** 사람이 읽는 문장으로 바꿉니다:
  "components.py 가 오래된 버전입니다" 라고요.

어떻게 하는가:

  패키징할 때 tools/stamp.py 가 모든 .py 의 해시를 BUILD.json 에 적습니다.
  앱이 시작할 때 실제 파일 해시와 비교합니다. 다르면 그 파일 이름을
  화면에 띄웁니다.

  BUILD.json 자체가 안 올라갔을 수도 있습니다. 그 경우는 '검사할 수 없음'
  이지 '정상' 이 아니므로 구분해서 알립니다.
================================================================================
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

MANIFEST = "BUILD.json"

#: 검사하지 않는 경로. 사용자가 직접 넣는 것들이라 달라서 정상입니다.
SKIP_DIRS = ("__pycache__", ".git", ".streamlit", "briefings", "analysis",
             ".jobs", "tests", "tools")
SKIP_FILES = ("BUILD.json",)


def file_hash(path: str) -> str:
    """파일 내용의 sha256 앞 12자리.

    줄바꿈 때문에 틀리지 않도록 **바이트 그대로** 읽습니다 — GitHub 웹
    편집기가 줄바꿈을 바꿔도 내용이 같으면 같은 해시여야 하는데, 그건
    포기합니다. 줄바꿈이 바뀌었다는 것도 '다른 파일' 이 맞습니다.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _tracked(root: str) -> list[str]:
    """검사 대상 .py 파일의 상대경로 목록."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py") or name in SKIP_FILES:
                continue
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def build_manifest(root: str) -> dict:
    """현재 파일들의 해시 목록. 패키징할 때 호출합니다."""
    return {rel: file_hash(os.path.join(root, rel)) for rel in _tracked(root)}


def write_manifest(root: str) -> dict:
    data = build_manifest(root)
    with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return data


@dataclass
class Report:
    """검사 결과."""

    checked: bool = False          # BUILD.json 을 읽었는가
    stale: list[str] = field(default_factory=list)    # 내용이 다른 파일
    missing: list[str] = field(default_factory=list)  # 목록에 있는데 없는 파일
    extra: list[str] = field(default_factory=list)    # 목록에 없는 파일
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.checked and not (self.stale or self.missing)

    @property
    def problem_files(self) -> list[str]:
        return sorted(set(self.stale) | set(self.missing))

    def message(self) -> str:
        """사람이 읽는 한 문단. 화면에 그대로 띄웁니다."""
        if not self.checked:
            return (f"파일 버전을 검사하지 못했습니다 — {self.note} "
                    "일부 파일만 올라갔는지 확인할 수 없습니다.")
        if self.ok:
            return ""
        bits = []
        if self.stale:
            bits.append("내용이 다릅니다: " + ", ".join(self.stale))
        if self.missing:
            bits.append("아예 없습니다: " + ", ".join(self.missing))
        return (
            "**일부 파일이 최신이 아닙니다.** "
            + " · ".join(bits)
            + ". 압축을 다시 풀어 이 파일들을 덮어쓰십시오 — "
            "파일이 섞이면 AttributeError 처럼 원인을 알기 어려운 오류가 납니다."
        )


def verify(root: str) -> Report:
    """BUILD.json 과 실제 파일을 비교합니다.

    검사 자체가 앱을 멈추게 하면 안 됩니다 — 어떤 예외든 '검사 못 함' 으로
    돌려주고 앱은 계속 돌아갑니다.
    """
    rep = Report()
    path = os.path.join(root, MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            want = json.load(fh)
    except FileNotFoundError:
        rep.note = f"{MANIFEST} 이 없습니다."
        return rep
    except Exception as exc:  # noqa: BLE001
        rep.note = f"{MANIFEST} 을 읽지 못했습니다 ({type(exc).__name__})."
        return rep

    if not isinstance(want, dict) or not want:
        rep.note = f"{MANIFEST} 내용이 비어 있습니다."
        return rep

    rep.checked = True
    have = {}
    for rel in want:
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            rep.missing.append(rel)
            continue
        try:
            have[rel] = file_hash(full)
        except OSError:
            rep.missing.append(rel)
    for rel, want_hash in want.items():
        if rel in have and have[rel] != want_hash:
            rep.stale.append(rel)

    actual = set(_tracked(root))
    rep.extra = sorted(actual - set(want))
    rep.stale.sort()
    rep.missing.sort()
    return rep
