"""
저장소 비공개 전환 테스트 (11/13, 사용자 결정 A).

  1. 토큰은 이 저장소 raw 주소에만 붙는다 (다른 호스트 · 비슷한 이름 저장소 X)
  2. 토큰이 없으면 헤더 없음 (공개 저장소일 때와 같은 동작)
  3. urllib 요청에는 '리다이렉트 때 따라가지 않는' 헤더로 붙는다
  4. 저장소 파일을 받는 곳(app 3곳 · swr 스냅샷 · 수집기)이 모두 토큰을 붙인다
  5. 수집 워크플로가 토큰을 넘기고, 사본(tools/collect_workflow.yml)과 같다
  6. 토큰 값은 화면 지우개 · 수집기 지우개 대상
"""
from __future__ import annotations

import os
import pathlib
import sys
import urllib.request

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
import config  # noqa: E402
from sources import safe  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


TOK = "github_pat_TESTTESTTESTTEST1234"
os.environ.pop("GITHUB_TOKEN", None)
print("=== 토큰 없음 ===")
check("헤더 없음", config.github_auth_headers(config.SEED_URL) == {})

os.environ["GITHUB_TOKEN"] = TOK
print("=== 토큰 있음 ===")
for name, url in [("스냅샷", config.SEED_URL), ("요약", config.SUMMARY_URL),
                  ("심사 파일", config.UNIVERSE_URLS["us"]),
                  ("브리핑", config.BRIEFING_REMOTE_URL.format(date="2026-11-14"))]:
    check(f"{name} 주소에 붙음", config.github_auth_headers(url).get("Authorization") == f"token {TOK}", url)
for url in ["https://query1.finance.yahoo.com/v8/finance/chart/MSFT",
            "https://raw.githubusercontent.com/MaCho-guy/REALMAN-INVEST-evil/data/x.json",
            "https://raw.githubusercontent.com/someone/other/main/x",
            "http://raw.githubusercontent.com/MaCho-guy/REALMAN-INVEST/data/x.json",
            "https://evil.example/https://raw.githubusercontent.com/MaCho-guy/REALMAN-INVEST/"]:
    check("다른 주소에는 안 붙음", config.github_auth_headers(url) == {}, url)

req = urllib.request.Request(config.SEED_URL)
config.add_github_auth(req)
check("urllib — 리다이렉트 때 따라가지 않는 헤더",
      req.unredirected_hdrs.get("Authorization") == f"token {TOK}"
      and "Authorization" not in req.headers)
req2 = urllib.request.Request("https://example.com/")
config.add_github_auth(req2)
check("urllib — 다른 주소 요청엔 없음", not req2.unredirected_hdrs and not req2.headers)

print("\n=== 받는 곳 ===")
app = pathlib.Path("app.py").read_text(encoding="utf-8")
check("app — 저장소 파일 받는 3곳", app.count("config.add_github_auth(req)") == 3)
swr_src = pathlib.Path("swr.py").read_text(encoding="utf-8")
check("swr 스냅샷", "add_github_auth(req)" in swr_src)
col = pathlib.Path("tools/collect.py").read_text(encoding="utf-8")
fb = col.split("def fetch_bytes(")[1].split("\ndef ")[0]
check("수집기 fetch_bytes", "github_auth_headers(url)" in fb)

print("\n=== 워크플로 · 지우개 ===")
wf = pathlib.Path("../.github/workflows/collect.yml").read_text(encoding="utf-8")
check("수집 단계가 토큰을 넘김", "GITHUB_TOKEN: ${{ github.token }}" in wf.split("- name: 수집")[1].split("- name:")[0])
check("워크플로 사본과 같음", wf == pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8"))
check("화면 지우개 대상", "GITHUB_TOKEN" in safe.SECRET_ENVS and TOK not in safe.scrub(f"x {TOK} y"))
check("수집기 지우개 대상", '"GITHUB_TOKEN"' in col.split("SECRET_ENVS")[1][:200])

print(f"\n{'통과' if not FAILURES else '실패: ' + ', '.join(FAILURES)}")
sys.exit(1 if FAILURES else 0)
