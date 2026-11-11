"""배포 폴더 배치에 따른 파일 버전 검사.

Streamlit Community Cloud 는 저장소 루트에서 streamlit run 을 실행하고,
테마 설정은 루트의 .streamlit/config.toml 을 읽습니다 (앱 폴더 옆의
파일이 있으면 그쪽 값이 우선). 설정 파일은 바이트가 아니라 **테마 값**
으로 검사합니다. 최신 .py 가 엉뚱한 경로에 올라가면 그 위치를 짚습니다.

    python tests/buildstamp_layout_test.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import buildstamp as b  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


GOOD = ('[theme]\nbase = "light"\nprimaryColor = "#1f3a5f"\n'
        'backgroundColor = "#eceef1"\nsecondaryBackgroundColor = "#ffffff"\n'
        'textColor = "#15181c"\n\n[server]\nmaxUploadSize = 5\n')


def write(path: str, text: str, newline: str | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


print("=== 세 곳의 테마 값이 일치 ===")
import theme  # noqa: E402

_pal = theme.PALETTE["light"]
check("EXPECTED_THEME 이 PALETTE 와 같다",
      b.EXPECTED_THEME["backgroundColor"] == _pal["page"]
      and b.EXPECTED_THEME["secondaryBackgroundColor"] == _pal["surface"]
      and b.EXPECTED_THEME["textColor"] == _pal["ink"]
      and b.EXPECTED_THEME["primaryColor"] == _pal["accent"])
check("배포용 config.toml 이 문제 없음",
      b.theme_problems(os.path.join(ROOT, ".streamlit", "config.toml")) == [],
      str(b.theme_problems(os.path.join(ROOT, ".streamlit", "config.toml"))))

tmp = tempfile.mkdtemp()
repo = os.path.join(tmp, "repo")
app = os.path.join(repo, "app")
APP_CFG = os.path.join(app, ".streamlit", "config.toml")
ROOT_CFG = os.path.join(repo, ".streamlit", "config.toml")
write(os.path.join(app, "a.py"), "x = 1\n")
write(os.path.join(app, "sources", "fred.py"), "y = 2\n")
write(APP_CFG, GOOD)
b.write_manifest(app)
old_cwd = os.getcwd()
os.chdir(repo)  # Cloud 의 작업 폴더 = 저장소 루트

try:
    print("\n=== 설정 파일 위치 ===")
    r = b.verify(app)
    check("전부 제자리면 통과", r.ok, r.message())

    write(ROOT_CFG, GOOD)
    os.remove(APP_CFG)
    r = b.verify(app)
    check("저장소 맨 위에만 있어도 통과", r.ok, r.message())
    check("위치 설명이 '저장소 맨 위'", "저장소 맨 위" in r.found_at.get(b.THEME_FILE, ""))

    os.remove(ROOT_CFG)
    r = b.verify(app)
    check("어디에도 없으면 '없음'", b.THEME_FILE in r.missing)
    hint = " ".join(r.hints())
    check("'없음' 은 GitHub 에서 직접 만드는 법을 안내",
          "Create new file" in hint and "점(.)" in hint)

    print("\n=== 설정 파일은 값으로 비교 ===")
    write(ROOT_CFG, "# 주석\r\n[theme]\r\nbase='light'  # 밝게\r\n"
          "primaryColor =  \"#1F3A5F\"\r\nbackgroundColor=\"#eceef1\"\r\n"
          "secondaryBackgroundColor = \"#ffffff\"\r\ntextColor = \"#15181c\"\r\n",
          newline="")
    r = b.verify(app)
    check("주석·공백·줄바꿈·대소문자·따옴표 종류만 다르면 통과", r.ok, str(r.hints()))
    check("색상의 # 은 주석으로 지우지 않는다",
          "#1f3a5f" in b.normalize_toml('a = "#1f3a5f" # x'))

    write(ROOT_CFG, GOOD.replace('"light"', '"dark"'))
    r = b.verify(app)
    check("값이 다르면 '다름'", b.THEME_FILE in r.stale)
    hint = " ".join(r.hints())
    check("어느 키가 무엇으로 되어 있는지 말한다", "base = dark (기대 light)" in hint, hint)

    write(ROOT_CFG, GOOD.replace('"light"', "“light”"))
    r = b.verify(app)
    hint = " ".join(r.hints())
    check("휴대폰 둥근 따옴표를 짚는다", "둥근 따옴표" in hint, hint[:60])

    write(ROOT_CFG, GOOD)
    write(APP_CFG, "base = \"light\"\n")  # [theme] 줄 빠짐
    r = b.verify(app)
    hint = " ".join(r.hints())
    check("두 곳에 있으면 문제 있는 쪽(앱 폴더)을 짚는다",
          "앱 폴더(app/.streamlit/config.toml)" in hint and "[theme]" in hint, hint)
    check("두 곳이면 하나만 남기라고 안내", "하나만 남기" in hint)
    os.remove(APP_CFG)

    print("\n=== 엉뚱한 위치의 .py ===")
    shutil.copy(os.path.join(app, "sources", "fred.py"), os.path.join(app, "fred.py"))
    write(os.path.join(app, "sources", "fred.py"), "y = 1  # 예전\n")
    r = b.verify(app)
    check("엉뚱한 위치의 최신 파일을 찾는다",
          r.misplaced.get("sources/fred.py") == "fred.py", str(r.misplaced))
    check("옮길 경로를 말해 준다",
          any("sources/fred.py 로 옮기" in h for h in r.hints()))

    print("\n=== 경고 화면 ===")
    import components as ui  # noqa: E402
    html = ui.render_build_warning(r)
    check("파일마다 줄을 나눈다 (복사해도 이어 붙지 않음)",
          html.count("<li>") == len(r.hints()), html[-120:])
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
