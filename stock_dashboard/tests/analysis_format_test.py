"""
공시 분석 HTML 을 읽을 때 빈 줄 · 들여쓰기를 걸러 주는지 검사합니다.

실행:
    cd stock_dashboard
    python tests/analysis_format_test.py

배경 (2026-11-25): analysis/MU/*.html 에 빈 줄이 있어 스트림릿 마크다운이 <style> 을
첫 빈 줄에서 끊었고, 표 폭 · 2단 배치 · 상자 테두리가 빠진 채 보였습니다. 파일은
고쳤지만, PC 의 '분석 실행' 이 새로 만든 파일에 빈 줄이 있으면 같은 일이 다시 납니다.
그래서 읽는 쪽(analysis_store.clean_html)에서 걸러 줍니다.
"""

from __future__ import annotations

import glob
import html
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import analysis_store  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def blank_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if not ln.strip())


def indented_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln[:1] in (" ", "\t"))


def visible(text: str) -> str:
    """태그 · <style> 을 뺀 글자 (공백 무시)."""
    text = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", text)))


def css(text: str) -> str:
    m = re.search(r"<style>(.*?)</style>", text, re.S)
    return re.sub(r"\s+", "", m.group(1)) if m else ""


BROKEN = """<!DOCTYPE html>
<html lang="ko"><head><title>x</title>
<style>
  .mu { color:#111; }
  .mu * { box-sizing:border-box; }

  .mu table { width:100%; }
  .mu .kpi > div { min-width:130px; }

  .mu .grid2 { display:grid; }
</style>
</head><body>
<div class="mu">

  <h1>제목</h1>

      <p>빈 줄 뒤에 4칸 넘게 들여쓴 줄 — 그대로 두면 코드 블록이 됩니다.</p>
  <table><tr><td>1,331.9억$</td></tr></table>
  <pre style="x"><code>EV = A
     + B

   = 846,240
\t탭 줄</code></pre>

  <p>끝</p>
</div>
</body></html>
"""

print("\n=== 1. 빈 줄 · 들여쓰기 제거 ===")
fixed = analysis_store.clean_html(BROKEN)
check("고치기 전 견본에는 빈 줄 · 들여쓴 줄이 있다", blank_lines(BROKEN) > 0 and indented_lines(BROKEN) > 0)
check("빈 줄 0", blank_lines(fixed) == 0, str(blank_lines(fixed)))
check("줄 앞 공백 0", indented_lines(fixed) == 0, str(indented_lines(fixed)))
check("글자는 그대로", visible(BROKEN) == visible(fixed))
check("모양 규칙(CSS)은 그대로", css(BROKEN) == css(fixed) and ".mu.grid2{display:grid;}" in css(fixed))
check("태그 수 그대로", len(re.findall(r"<[^>]+>", BROKEN)) == len(re.findall(r"<[^>]+>", fixed)))
check("두 번 걸러도 같다", analysis_store.clean_html(fixed) == fixed)

print("\n=== 2. <pre> 안 줄 맞춤 ===")
pre = lambda t: html.unescape(re.search(r"<pre[^>]*>(.*?)</pre>", t, re.S).group(1))  # noqa: E731
before = [ln.rstrip() for ln in pre(BROKEN).split("\n")]
after = [ln.rstrip() for ln in pre(fixed).split("\n")]
check("브라우저가 보는 <pre> 글자가 줄 단위로 같다", before == after, f"{before} / {after}")
check("들여쓴 줄 '     + B' 유지", "     + B" in pre(fixed))
check("탭 줄 유지", "\t탭 줄" in pre(fixed))
check("<pre> 뒤 줄은 다시 보통 규칙", fixed.rstrip().endswith("</body></html>") and "\n<p>끝</p>\n" in fixed)
one = analysis_store.clean_html("<div>\n  <pre>한 줄</pre>\n\n    <p>뒤</p>\n</div>\n")
check("한 줄짜리 <pre> 뒤도 보통 규칙", one == "<div>\n<pre>한 줄</pre>\n<p>뒤</p>\n</div>\n", repr(one))

print("\n=== 3. 건드리지 않는 것 ===")
md = "# 제목\n\n    코드\n\n본문\n"
check("HTML 이 아닌 글은 그대로", analysis_store.clean_html(md) == md)
paths = sorted(glob.glob(os.path.join(ROOT, "analysis", "*", "*.html")))
check("저장소에 분석 HTML 이 있다", len(paths) >= 15, str(len(paths)))
changed = []
for p in paths:
    with open(p, encoding="utf-8") as fh:
        body = fh.read()
    if analysis_store.clean_html(body) != body:
        changed.append(os.path.relpath(p, ROOT))
check("이미 올린 분석은 한 글자도 안 바뀐다", not changed, ", ".join(changed))

print("\n=== 4. load() 가 걸러서 준다 ===")
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "MU"))
    with open(os.path.join(tmp, "MU", "decoder.html"), "w", encoding="utf-8") as fh:
        fh.write(BROKEN)
    doc = analysis_store.load(tmp, "MU")
    got = doc.html.get("decoder", "")
    check("load: 본문 있음", bool(got))
    check("load: 빈 줄 0 · 줄 앞 공백 0", blank_lines(got) == 0 and indented_lines(got) == 0)
    with open(os.path.join(tmp, "MU", "decoder.html"), encoding="utf-8") as fh:
        check("load: 원본 파일은 건드리지 않는다", fh.read() == BROKEN)

print("\n=== 5. 서버 안내 문구 ===")
with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
    src = fh.read()
check("새 분석을 얻는 길을 적는다", "Claude 대화에서 요청하면 여기에 올라옵니다" in src)
check("설치 안내 위에 '오류가 아님' 을 먼저 적는다",
      src.index("오류가 \"\n                \"아닙니다") < src.index('f"{cli.summary}\\n\\n"')
      if "오류가 \"\n                \"아닙니다" in src else False)

print()
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {FAILURES}")
    sys.exit(1)
print("모두 통과")
