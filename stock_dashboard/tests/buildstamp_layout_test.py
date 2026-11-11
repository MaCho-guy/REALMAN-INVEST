"""배포 폴더 배치에 따른 파일 버전 검사.

Streamlit Community Cloud 는 저장소 루트에서 streamlit run 을 실행하고,
테마 설정도 루트의 .streamlit/config.toml 을 읽습니다. 앱은 하위 폴더
(stock_dashboard/) 에 있으므로, 설정 파일이 루트에 있으면 '있음' 이어야
합니다. 또 최신 파일이 엉뚱한 경로에 올라간 경우 그 위치를 짚어야 합니다.

    python tests/buildstamp_layout_test.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import buildstamp as b  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


tmp = tempfile.mkdtemp()
repo = os.path.join(tmp, "repo")
app = os.path.join(repo, "app")
os.makedirs(os.path.join(app, "sources"))
os.makedirs(os.path.join(app, ".streamlit"))
with open(os.path.join(app, "a.py"), "w") as fh:
    fh.write("x = 1\n")
with open(os.path.join(app, "sources", "fred.py"), "w") as fh:
    fh.write("y = 2\n")
with open(os.path.join(app, ".streamlit", "config.toml"), "w") as fh:
    fh.write('[theme]\nbase = "light"\n')
b.write_manifest(app)
old_cwd = os.getcwd()
os.chdir(repo)  # Cloud 의 작업 폴더 = 저장소 루트

try:
    print("=== 배치별 검사 ===")
    r = b.verify(app)
    check("전부 제자리면 통과", r.ok, str(r.message()))

    os.makedirs(os.path.join(repo, ".streamlit"))
    shutil.move(os.path.join(app, ".streamlit", "config.toml"),
                os.path.join(repo, ".streamlit", "config.toml"))
    r = b.verify(app)
    check("설정 파일이 저장소 루트에만 있어도 통과", r.ok, str(r.missing))
    check("어디서 찾았는지 기록", "config.toml" in r.found_at.get(b.THEME_FILE, ""))

    with open(os.path.join(repo, ".streamlit", "config.toml"), "w") as fh:
        fh.write('[theme]\nbase = "dark"\n')
    r = b.verify(app)
    check("루트 설정이 예전 내용이면 '다름'", b.THEME_FILE in r.stale, str(r.stale))

    os.remove(os.path.join(repo, ".streamlit", "config.toml"))
    r = b.verify(app)
    check("설정 파일이 어디에도 없으면 '없음'", b.THEME_FILE in r.missing)
    hint = " ".join(r.hints())
    check("숨김 폴더 원인과 GitHub 에서 직접 만드는 법을 안내",
          "Create new file" in hint and "점(.)" in hint, hint[:60])

    shutil.copy(os.path.join(app, "sources", "fred.py"), os.path.join(app, "fred.py"))
    with open(os.path.join(app, "sources", "fred.py"), "w") as fh:
        fh.write("y = 1  # 예전\n")
    r = b.verify(app)
    check("엉뚱한 위치의 최신 파일을 찾는다",
          r.misplaced.get("sources/fred.py") == "fred.py", str(r.misplaced))
    check("옮길 경로를 말해 준다",
          any("sources/fred.py 로 옮기" in h for h in r.hints()))

    print("\n=== 설정 파일은 값으로 비교 ===")
    # 주석이 잔뜩 든 원본으로 매니페스트를 만들고
    full_cfg = ('[theme]\n# 설명 주석\nbase = "light"  # 밝게\n'
                'primaryColor = "#1f3a5f"\n\n[server]\nmaxUploadSize = 5\n')
    with open(os.path.join(app, ".streamlit", "config.toml"), "w") as fh:
        fh.write(full_cfg)
    os.remove(os.path.join(app, "fred.py"))
    with open(os.path.join(app, "sources", "fred.py"), "w") as fh:
        fh.write("y = 2\n")
    b.write_manifest(app)
    os.remove(os.path.join(app, ".streamlit", "config.toml"))
    # 사용자는 채팅의 짧은 버전(주석 없음, CRLF)을 루트에 붙여 넣음
    with open(os.path.join(repo, ".streamlit", "config.toml"), "w", newline="") as fh:
        fh.write('[theme]\r\nbase="light"\r\nprimaryColor =  "#1f3a5f"\r\n'
                 '[server]\r\nmaxUploadSize=5\r\n')
    r = b.verify(app)
    check("주석·공백·줄바꿈만 다르면 통과", r.ok, r.message())
    check("색상의 # 은 주석으로 지우지 않는다",
          "#1f3a5f" in b.normalize_toml('a = "#1f3a5f" # x'))
    with open(os.path.join(repo, ".streamlit", "config.toml"), "w") as fh:
        fh.write('[theme]\nbase = "dark"\nprimaryColor = "#1f3a5f"\n'
                 '[server]\nmaxUploadSize = 5\n')
    r = b.verify(app)
    check("값이 다르면 '다름'", b.THEME_FILE in r.stale)
    hint = " ".join(r.hints())
    check("'다름' 일 때는 숨김 폴더가 아니라 값 확인을 안내",
          "설정 값이 최신과 다릅니다" in hint and "점(.)" not in hint, hint[:70])

    print("\n=== 경고 화면 ===")
    import components as ui  # noqa: E402
    html = ui.render_build_warning(r)
    check("파일마다 줄을 나눈다 (복사해도 이어 붙지 않음)",
          html.count("<li>") == len(r.problem_files), html[-120:])
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("전부 통과")
