"""
실행 엔진 테스트 (claude CLI 없이 돌아갑니다).

실행:
    cd stock_dashboard
    python tests/runner_test.py

검증 범위: CLI 부재 처리, 작업 상태 파일 왕복, 프롬프트 생성, 경로 정제,
           중복 실행 방지, 프로세스 종료 감지, 결과 JSON 파싱, meta.json 갱신.
가짜 `claude` 실행 파일을 임시로 만들어 전체 경로를 끝까지 통과시킵니다.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis_store  # noqa: E402
import runner  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def make_fake_claude(tmp: str, *, script: str) -> str:
    """가짜 claude 실행 파일을 만들어 PATH 앞에 끼웁니다."""
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "claude")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    return path


print("=== 프롬프트 생성 ===")
p = runner.build_prompt("MU", "Micron", "decoder", "analysis/MU/decoder.html")
check("슬래시 명령 포함", "/company-decoder-korean" in p)
check("종목명·키 포함", "Micron" in p and "(MU)" in p)
check("출력 경로 명시", "analysis/MU/decoder.html" in p)
check("완결 HTML 요구", "<!DOCTYPE html>" in p)
check("SAVED 마커 요구", "SAVED: analysis/MU/decoder.html" in p)
check("출처 규칙 포함", "출처 없는 숫자" in p)

p2 = runner.build_prompt("MU", "Micron", "price", "x.html",
                         skill_commands={"price": "/anthropic-skills:price-decoder-korean"})
check("스킬 명령 덮어쓰기", "/anthropic-skills:price-decoder-korean" in p2)

print("\n=== 결과 JSON 파싱 ===")
ok_log = (
    "진행 메시지 한 줄\n"
    '{"type":"system","subtype":"init"}\n'
    '{"result":"끝","session_id":"abc-123","total_cost_usd":0.4213,'
    '"num_turns":17,"is_error":false}\n'
)
r = runner._parse_result(ok_log)
check("비용 파싱", abs((r.get("cost_usd") or 0) - 0.4213) < 1e-9, str(r.get("cost_usd")))
check("턴 수 파싱", r.get("num_turns") == 17)
check("세션 ID 파싱", r.get("session_id") == "abc-123")
check("오류 아님", r.get("is_error") is False)

err_log = '{"result":"turn limit","session_id":"z","total_cost_usd":0.1,"is_error":true}\n'
r2 = runner._parse_result(err_log)
check("오류 플래그 파싱", r2.get("is_error") is True)
check("오류 메시지 추출", "turn limit" in (r2.get("error") or ""))

check("JSON 없는 로그는 빈 dict", runner._parse_result("그냥 텍스트\n에러\n") == {})
check("깨진 JSON 무시", runner._parse_result('{"result":\n') == {})

print("\n=== claude CLI 부재 처리 ===")
saved_path = os.environ["PATH"]
try:
    os.environ["PATH"] = "/nonexistent-dir-for-test"
    info = runner.cli_info()
    check("CLI 없음 감지", not info.available)
    check("설치 안내 포함", "npm install" in info.error)

    with tempfile.TemporaryDirectory() as tmp:
        job = runner.start_job(tmp, tmp, "MU", "Micron", "decoder")
        check("CLI 없으면 failed 로 기록", job.status == "failed")
        check("사유가 담김", "claude" in job.error)
        reread = runner.read_job(tmp, "MU", "decoder")
        check("실패 상태가 파일에 남음", reread.status == "failed")
finally:
    os.environ["PATH"] = saved_path

print("\n=== 경로 정제 ===")
with tempfile.TemporaryDirectory() as tmp:
    for hostile in ("../../etc", "..", "MU/../AAPL", "/abs/path"):
        d = runner._jobs_dir(tmp, hostile)
        inside = os.path.commonpath([os.path.abspath(tmp), os.path.abspath(d)]) \
                 == os.path.abspath(tmp)
        check(f"{hostile!r} 가 analysis 밖으로 못 나감", inside and ".." not in d, d)

print("\n=== 성공 경로 (가짜 claude) ===")
with tempfile.TemporaryDirectory() as tmp:
    analysis = os.path.join(tmp, "analysis")
    os.makedirs(os.path.join(analysis, "MU"), exist_ok=True)

    # 가짜 claude: HTML 을 쓰고 결과 JSON 을 출력
    script = f"""#!/bin/sh
if [ "$1" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi
mkdir -p "{analysis}/MU"
cat > "{analysis}/MU/decoder.html" <<'EOF'
<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title></head>
<body><div>가짜 분석 본문입니다. 길이를 400바이트 넘기기 위한 패딩 텍스트를 넣습니다.
{'패딩 ' * 60}</div></body></html>
EOF
echo '{{"result":"done","session_id":"s-1","total_cost_usd":0.77,"num_turns":9,"is_error":false}}'
exit 0
"""
    make_fake_claude(tmp, script=script)

    info = runner.cli_info()
    check("가짜 CLI 인식", info.available, info.version)

    job = runner.start_job(analysis, tmp, "MU", "Micron", "decoder")
    check("running 으로 시작", job.status == "running", f"pid={job.pid}")
    check("pid 기록", job.pid is not None)

    # 중복 실행 방지 (프로세스가 아직 살아 있을 수 있음)
    again = runner.start_job(analysis, tmp, "MU", "Micron", "decoder")
    check("중복 실행 시 기존 작업 유지",
          again.pid == job.pid or again.status in ("running", "done"))

    for _ in range(100):
        polled = runner.poll_job(analysis, "MU", "decoder")
        if not polled.is_running:
            break
        time.sleep(0.1)

    check("완료 감지", polled.status == "done", polled.error)
    check("비용 기록", polled.cost_usd == 0.77, str(polled.cost_usd))
    check("턴 수 기록", polled.num_turns == 9)
    check("종료 시각 기록", bool(polled.finished_at))
    check("경과 시간 계산", polled.elapsed_sec is not None)

    html_path = os.path.join(analysis, "MU", "decoder.html")
    check("HTML 파일 생성", os.path.isfile(html_path))

    doc = analysis_store.load(analysis, "MU")
    check("뷰어가 읽음", "decoder" in doc.html)
    check("meta.json 생성일 갱신", bool(doc.generated), doc.generated)
    check("meta note 에 실행 기록", "헤드리스" in (doc.note or ""), doc.note or "")

    check("poll 멱등 (재호출해도 done)",
          runner.poll_job(analysis, "MU", "decoder").status == "done")

    log = runner.read_log(analysis, "MU", "decoder")
    check("로그 저장됨", "total_cost_usd" in log)

print("\n=== HTML 미생성 실패 경로 ===")
with tempfile.TemporaryDirectory() as tmp:
    analysis = os.path.join(tmp, "analysis")
    os.makedirs(analysis, exist_ok=True)
    # HTML 을 안 쓰고 성공 JSON 만 내는 가짜 claude
    make_fake_claude(tmp, script="""#!/bin/sh
if [ "$1" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi
echo '{"result":"ok","session_id":"s","total_cost_usd":0.01,"num_turns":1,"is_error":false}'
exit 0
""")
    runner.start_job(analysis, tmp, "AAPL", "Apple", "story")
    for _ in range(100):
        j = runner.poll_job(analysis, "AAPL", "story")
        if not j.is_running:
            break
        time.sleep(0.1)
    check("HTML 없으면 failed", j.status == "failed", j.status)
    check("슬래시 명령 확인 안내", "슬래시 명령" in j.error)

print("\n=== 오류 종료 경로 ===")
with tempfile.TemporaryDirectory() as tmp:
    analysis = os.path.join(tmp, "analysis")
    os.makedirs(analysis, exist_ok=True)
    make_fake_claude(tmp, script="""#!/bin/sh
if [ "$1" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi
echo '{"result":"max turns reached","session_id":"s","total_cost_usd":1.5,"is_error":true}'
exit 1
""")
    runner.start_job(analysis, tmp, "MSFT", "Microsoft", "price")
    for _ in range(100):
        j = runner.poll_job(analysis, "MSFT", "price")
        if not j.is_running:
            break
        time.sleep(0.1)
    check("is_error 면 failed", j.status == "failed", j.status)
    check("턴 초과를 조치 가능한 문장으로 번역", "턴 수" in j.error, j.error)
    check("실패해도 비용은 기록", j.cost_usd == 1.5, str(j.cost_usd))

print("\n=== 실패 사유 번역 ===")
for label, parsed, expect in (
    ("인증", {"error": "Authentication error · network", "is_error": True}, "인증 실패"),
    ("도구 거부", {"error": "x", "is_error": True, "denied_tools": ["WebSearch"]}, "WebSearch"),
    ("턴 초과", {"error": "max turns", "is_error": True, "terminal_reason": "max_turns"}, "턴 수"),
    ("요청 한도", {"error": "rate limit (429)", "is_error": True}, "한도"),
    ("사유 없음", {"is_error": True}, "로그를 확인"),
):
    msg = runner._explain_failure(parsed)
    check(f"{label} → 조치 안내", expect in msg, msg[:70])

print("\n=== 중단 ===")
with tempfile.TemporaryDirectory() as tmp:
    analysis = os.path.join(tmp, "analysis")
    os.makedirs(analysis, exist_ok=True)
    make_fake_claude(tmp, script="""#!/bin/sh
if [ "$1" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi
sleep 30
""")
    runner.start_job(analysis, tmp, "UNH", "UnitedHealth", "decoder")
    time.sleep(0.3)
    running = runner.read_job(analysis, "UNH", "decoder")
    check("장시간 작업이 running", running.is_running, running.status)
    cancelled = runner.cancel_job(analysis, "UNH", "decoder")
    check("중단 처리", cancelled.status == "cancelled", cancelled.status)
    time.sleep(0.3)
    check("프로세스 실제 종료", not runner._pid_alive(cancelled.pid))

print("\n=== 작업 상태 집계 ===")
with tempfile.TemporaryDirectory() as tmp:
    analysis = os.path.join(tmp, "analysis")
    os.makedirs(analysis, exist_ok=True)
    jobs = runner.poll_all(analysis, ["MU", "AAPL"])
    check("종목×종류 전부 조회", len(jobs) == 2 * len(analysis_store.KIND_KEYS), str(len(jobs)))
    check("기록 없으면 전부 idle", all(j.status == "idle" for j in jobs.values()))
    check("실행 중 집계 0", runner.running_count(jobs) == 0)

print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
