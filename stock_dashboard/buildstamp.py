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
#:
#: 2026-11-11: **tools/ 를 다시 넣었습니다.** 앱이 돌 때 app.py 가
#: `from tools import diagnose` 를 합니다 — 개발용 폴더가 아니라
#: 런타임 의존입니다. 빼 두었더니 tools/diagnose.py 만 옛날 파일인
#: 상태가 검사를 **통과**했고, 진단 패널에서 AttributeError 로 죽었습니다.
#: 검사에서 빠진 파일은 검사를 통과하는 게 아니라 안 보이는 것입니다.
#: tests/ 는 앱이 임포트하지 않으므로 그대로 둡니다.
SKIP_DIRS = ("__pycache__", ".git", ".streamlit", "briefings", "analysis",
             ".jobs", "tests")
SKIP_FILES = ("BUILD.json",)


def _strip_toml_comment(line: str) -> str:
    """따옴표 밖의 # 부터 끝까지 지웁니다 ("#1f3a5f" 같은 색은 남김)."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


def normalize_toml(text: str) -> str:
    """설정 파일의 '값' 만 남깁니다 — 주석·빈 줄·공백·줄바꿈 차이는 무시.

    2026-11-11: 채팅에 주석을 뺀 짧은 내용을 붙여 넣으라고 안내했는데,
    검사는 주석까지 포함한 바이트를 비교해서 '내용이 다릅니다' 가
    떴습니다. 설정 파일에서 의미가 있는 건 키와 값뿐입니다.
    """
    out = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _strip_toml_comment(raw).strip()
        if not line:
            continue
        if "=" in line and not line.startswith("["):
            k, v = line.split("=", 1)
            line = f"{k.strip()}={v.strip()}"
        out.append(line)
    return "\n".join(out)


def file_hash(path: str) -> str:
    """파일 내용의 sha256 앞 12자리.

    줄바꿈 때문에 틀리지 않도록 **바이트 그대로** 읽습니다 — GitHub 웹
    편집기가 줄바꿈을 바꿔도 내용이 같으면 같은 해시여야 하는데, 그건
    포기합니다. 줄바꿈이 바뀌었다는 것도 '다른 파일' 이 맞습니다.
    """
    if path.endswith(".toml"):
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
        return hashlib.sha256(
            normalize_toml(text).encode("utf-8")).hexdigest()[:12]
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


#: .py 가 아니어도 **앱 동작을 바꾸는** 파일. .streamlit/config.toml 이
#: 없으면 Streamlit 은 보는 기기의 다크/라이트 설정을 따라가서, 다크 모드
#: 휴대폰에서는 위젯 글자가 밝은 패널 위에 밝게 찍혀 안 보입니다.
#: .py 만 보면 이 파일이 빠져도 검사를 통과합니다.
#: secrets.toml 은 사용자마다 다르므로 넣지 않습니다.
THEME_FILE = ".streamlit/config.toml"
EXTRA_TRACKED = (THEME_FILE, "requirements.txt")

#: Streamlit Community Cloud 는 **저장소 루트**에서 streamlit run 을
#: 실행하고, 설정 파일도 루트의 .streamlit/config.toml 을 읽습니다 (앱
#: 폴더 옆에 둔 파일은 최신 버전에서만 덮어쓰기용으로 읽힙니다). 그래서
#: 이 파일은 앱 폴더·작업 폴더·상위 폴더 어디에 있어도 '있음' 으로 봅니다.
_ROOT_LEVEL = (THEME_FILE,)


#: 테마 설정이 가져야 할 값. theme.py PALETTE["light"] 와 같아야 하며,
#: 테스트가 셋(.streamlit/config.toml · 이 표 · PALETTE)이 일치하는지 봅니다.
#: 설정 파일은 바이트가 아니라 **이 값들**로 검사합니다 — 2026-11-11 에
#: 주석·위치 차이로 '다릅니다' 가 두 번 잘못 떴습니다.
EXPECTED_THEME = {
    "base": "light",
    "primaryColor": "#1f3a5f",
    "backgroundColor": "#eceef1",
    "secondaryBackgroundColor": "#ffffff",
    "textColor": "#15181c",
}
_CURLY = "\u201c\u201d\u2018\u2019"   # 휴대폰 자동 고침이 만드는 둥근 따옴표


def _parse_theme(text: str) -> dict:
    """[theme] 구역의 key = "value" 만 읽습니다 (tomllib 없이도 동작)."""
    section, out = "", {}
    for raw in text.replace("\r", "\n").split("\n"):
        line = _strip_toml_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section == "theme" and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def _toml_error(text: str) -> str:
    """TOML 문법 오류를 사람 말로 (없으면 빈 문자열). 파이썬 3.11 미만은 건너뜀."""
    try:
        import tomllib  # noqa: PLC0415
    except ImportError:
        return ""
    try:
        tomllib.loads(text)
        return ""
    except tomllib.TOMLDecodeError as exc:
        import re as _re  # noqa: PLC0415
        m = _re.search(r"line (\d+)", str(exc))
        where, shown = "", ""
        if m:
            n = int(m.group(1))
            lines = text.splitlines()
            where = f" {n}번째 줄"
            if 0 < n <= len(lines):
                shown = f" — `{lines[n - 1].strip()[:60]}`"
        hint = ""
        if _re.search(r"=\s*(fals|fal|tru|tr)\s*$", text, _re.M):
            hint = " (true / false 가 중간에 잘렸습니다)"
        return (f"문법 오류{where}{shown}{hint}. 한 줄이라도 틀리면 Streamlit 이 "
                "이 파일 **전체**를 읽지 못해 테마가 적용되지 않습니다")
    except Exception:  # noqa: BLE001
        return ""


def theme_problems(path: str) -> list[str]:
    """설정 파일 하나의 문제 목록 (비어 있으면 정상)."""
    try:
        with open(path, "rb") as fh:
            # utf-8-sig: 윈도 메모장이 붙이는 BOM 을 떼고 읽습니다
            text = fh.read().decode("utf-8-sig", "replace")
    except OSError as exc:
        return [f"읽지 못함 ({type(exc).__name__})"]
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    probs = []
    if any(c in text for c in _CURLY):
        probs.append("따옴표가 둥근 따옴표(“ ”)로 바뀌어 있습니다 — 휴대폰 "
                     "자동 고침 때문입니다. 이러면 Streamlit 이 파일을 못 읽습니다. "
                     "곧은 따옴표(\")로 바꾸십시오")
        text = text.translate({ord(c): '"' for c in _CURLY})
    # **파일 전체가 문법에 맞는지** 봅니다. 2026-11-12: 저장소의 파일이
    # 마지막 줄에서 잘려 있었습니다 (`gatherUsageStats = fals`). [theme] 값은
    # 전부 맞아서 아래 검사는 통과했지만, 한 줄이라도 틀리면 Streamlit 은
    # 파일 **전체**를 못 읽습니다 — 테마가 통째로 적용되지 않습니다.
    syntax = _toml_error(text)
    if syntax:
        probs.append(syntax)
    got = _parse_theme(text)
    if not got:
        probs.append("[theme] 구역을 찾지 못했습니다 — 첫 줄이 [theme] 인지 "
                     "확인하십시오")
        return probs
    for k, want in EXPECTED_THEME.items():
        have = got.get(k)
        if have is None:
            probs.append(f"{k} 줄이 없습니다 (기대 {want})")
        elif have.lower() != want.lower():
            probs.append(f"{k} = {have} (기대 {want})")
    return probs


def _theme_locations(root: str) -> list[tuple[str, str]]:
    """(설명, 경로) — 실제로 존재하는 설정 파일들. 앱 폴더가 먼저(우선)."""
    out = []
    app = os.path.join(root, THEME_FILE)
    if os.path.exists(app):
        out.append((f"앱 폴더({os.path.basename(os.path.abspath(root))}/"
                    f"{THEME_FILE})", app))
    for alt in _alt_roots(root):
        full = os.path.join(alt, THEME_FILE)
        if os.path.exists(full) and all(
                os.path.abspath(full) != os.path.abspath(p) for _, p in out):
            out.append((f"저장소 맨 위({THEME_FILE})", full))
    return out


def _alt_roots(root: str) -> list[str]:
    out = []
    for cand in (os.getcwd(), os.path.dirname(os.path.abspath(root))):
        if cand and os.path.abspath(cand) != os.path.abspath(root) \
                and cand not in out:
            out.append(cand)
    return out


def _find_misplaced(root: str, rel: str, want_hash: str) -> str:
    """같은 이름·같은 내용의 파일이 다른 경로에 있으면 그 경로."""
    base = os.path.basename(rel)
    tops = [root] + _alt_roots(root)
    seen = set()
    for top in tops:
        for dirpath, dirnames, filenames in os.walk(top):
            depth = os.path.relpath(dirpath, top).count(os.sep)
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", "__pycache__", "node_modules")
                           and depth < 3]
            if base not in filenames:
                continue
            full = os.path.abspath(os.path.join(dirpath, base))
            if full in seen:
                continue
            seen.add(full)
            if full == os.path.abspath(os.path.join(root, rel)):
                continue
            try:
                if file_hash(full) == want_hash:
                    return os.path.relpath(full, root).replace(os.sep, "/")
            except OSError:
                continue
    return ""


def _tracked(root: str) -> list[str]:
    """검사 대상 파일의 상대경로 목록 (.py + EXTRA_TRACKED)."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py") or name in SKIP_FILES:
                continue
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    for rel in EXTRA_TRACKED:
        if os.path.exists(os.path.join(root, rel)):
            out.append(rel)
    return sorted(set(out))


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
    #: 문제 파일 → 실제로 발견된 엉뚱한 위치 (내용은 최신과 같음)
    misplaced: dict = field(default_factory=dict)
    #: .streamlit/config.toml 을 어디서 찾았는가 (앱 폴더 / 저장소 루트)
    found_at: dict = field(default_factory=dict)
    #: 설정 파일 위치별 문제 [(설명, [문제...])]
    theme_issues: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.checked and not (self.stale or self.missing)

    @property
    def problem_files(self) -> list[str]:
        return sorted(set(self.stale) | set(self.missing))

    def hints(self) -> list[str]:
        """파일마다 '무엇을 하면 되는지' 한 줄씩."""
        out = []
        for rel in self.problem_files:
            where = self.misplaced.get(rel)
            if where:
                out.append(f"{rel} — 최신 파일이 엉뚱한 위치({where})에 올라가 "
                           f"있습니다. 앱 폴더 기준 {rel} 로 옮기십시오.")
            elif rel == THEME_FILE and rel in self.stale:
                for label, probs in self.theme_issues:
                    if probs:
                        out.append(f"{label} — " + "; ".join(probs) + ".")
                if len(self.theme_issues) > 1:
                    out.append("설정 파일이 두 곳에 있습니다. 앱 폴더 쪽이 "
                               "우선하므로, 앱 폴더의 파일을 지우고 저장소 맨 "
                               "위 하나만 남기는 것이 가장 간단합니다.")
            elif rel == THEME_FILE:
                out.append(
                    f"{rel} — 이름이 점(.)으로 시작하는 폴더는 Mac Finder 와 "
                    "일부 업로드 창에서 숨겨져 같이 안 올라갑니다. GitHub 에서 "
                    "'Add file → Create new file' 로 저장소 맨 위에 "
                    ".streamlit/config.toml 을 직접 만들고 내용을 붙여 넣으십시오. "
                    "이 파일이 없으면 휴대폰이 다크 모드일 때 버튼 글자가 "
                    "배경에 묻힙니다.")
            elif rel in self.missing:
                out.append(f"{rel} — 파일이 없습니다. 이 경로 그대로 올리십시오.")
            else:
                out.append(f"{rel} — 예전 버전입니다. 폴더 경로까지 같은 자리에 "
                           "덮어썼는지 확인하십시오.")
        return out

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


_VERIFY_MEMO: dict = {}


def verify_cached(root: str) -> Report:
    """verify() 와 같지만, 파일이 안 바뀌었으면 지난 결과를 그대로 줍니다.

    화면을 그릴 때마다(버튼 한 번마다) 60여 개 파일을 다시 읽어 해시할
    이유가 없습니다. 파일의 수정 시각·크기가 그대로면 내용도 그대로로 봅니다.
    """
    sig = []
    try:
        with open(os.path.join(root, MANIFEST), "rb") as fh:
            raw = fh.read()
        names = list(json.loads(raw.decode("utf-8")))
    except Exception:  # noqa: BLE001
        return verify(root)
    sig.append(hash(raw))
    for rel in names:
        try:
            st_ = os.stat(os.path.join(root, rel))
            sig.append((rel, st_.st_mtime_ns, st_.st_size))
        except OSError:
            sig.append((rel, 0, -1))
    key = (root, tuple(sig))
    if _VERIFY_MEMO.get("key") != key:
        _VERIFY_MEMO["key"] = key
        _VERIFY_MEMO["report"] = verify(root)
    return _VERIFY_MEMO["report"]


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
        if rel == THEME_FILE:
            locs = _theme_locations(root)
            if not locs:
                rep.missing.append(rel)
                continue
            rep.theme_issues = [(label, theme_problems(path))
                                for label, path in locs]
            rep.found_at[rel] = ", ".join(label for label, _ in locs)
            if any(probs for _, probs in rep.theme_issues):
                rep.stale.append(rel)
            continue
        full = os.path.join(root, rel)
        if not os.path.exists(full) and rel in _ROOT_LEVEL:
            for alt in _alt_roots(root):
                if os.path.exists(os.path.join(alt, rel)):
                    full = os.path.join(alt, rel)
                    break
        if not os.path.exists(full):
            rep.missing.append(rel)
            continue
        if rel in _ROOT_LEVEL:
            rep.found_at[rel] = os.path.relpath(
                full, root).replace(os.sep, "/")
        try:
            have[rel] = file_hash(full)
        except OSError:
            rep.missing.append(rel)
    for rel, want_hash in want.items():
        if rel in have and have[rel] != want_hash:
            rep.stale.append(rel)

    for rel in rep.stale + rep.missing:
        if rel == THEME_FILE:
            continue
        try:
            where = _find_misplaced(root, rel, want[rel])
        except Exception:  # noqa: BLE001
            where = ""
        if where:
            rep.misplaced[rel] = where

    actual = set(_tracked(root))
    rep.extra = sorted(actual - set(want))
    rep.stale.sort()
    rep.missing.sort()
    return rep
