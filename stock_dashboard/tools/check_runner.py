"""
분석 실행 환경을 점검합니다.

실행:
    cd stock_dashboard
    python -m tools.check_runner              # 환경만 점검
    python -m tools.check_runner --dry-run    # 실제로 넘길 명령까지 출력
    python -m tools.check_runner --jobs       # 저장된 작업 상태 전체 조회

'분석 실행' 버튼이 동작하지 않을 때 여기서 원인을 찾습니다.
"""

from __future__ import annotations

import os
import sys

import analysis_store
import config
import runner

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(BASE, config.ANALYSIS_DIR)

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def check_env() -> bool:
    print("=" * 72)
    print("1. claude CLI")
    print("=" * 72)
    info = runner.cli_info()
    if info.available:
        print(f"  {GREEN}OK{RESET}   경로 {info.path}")
        print(f"       버전 {info.version or '(확인 못 함)'}")
    else:
        print(f"  {RED}FAIL{RESET} {info.error}")
        print()
        print("  설치:")
        print("    npm install -g @anthropic-ai/claude-code")
        print("  설치 후 한 번 대화형으로 띄워 로그인을 마치십시오:")
        print("    claude")
        return False

    print()
    print("=" * 72)
    print("2. 스킬 설치 위치")
    print("=" * 72)
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".claude", "skills"),
        os.path.join(BASE, ".claude", "skills"),
        os.path.join(home, ".claude", "skills", "synced"),
    ]
    found_any = False
    wanted = {"company-decoder-korean", "company-story-korean", "price-decoder-korean"}
    for folder in candidates:
        if not os.path.isdir(folder):
            print(f"  {DIM}없음  {folder}{RESET}")
            continue
        found_any = True
        entries = sorted(os.listdir(folder))
        hits = [e for e in entries if e in wanted]
        print(f"  {GREEN}존재{RESET}  {folder}  ({len(entries)}개 항목)")
        if hits:
            for h in hits:
                print(f"         {GREEN}✓{RESET} {h}")
        # 하위 폴더(플러그인·synced)도 한 겹 들여다봅니다
        for e in entries:
            sub = os.path.join(folder, e)
            if not os.path.isdir(sub):
                continue
            subhits = [s for s in os.listdir(sub) if s in wanted]
            for s in subhits:
                print(f"         {GREEN}✓{RESET} {e}/{s}")

    if not found_any:
        print(f"  {YELLOW}주의{RESET} 스킬 폴더를 찾지 못했습니다. 플러그인으로 설치된 경우")
        print("         다른 위치에 있을 수 있습니다. 아래 3번으로 확인하십시오.")

    print()
    print("=" * 72)
    print("3. 슬래시 명령 이름 — 직접 확인이 필요합니다")
    print("=" * 72)
    print("  이 도구가 자동으로 알 수 없는 유일한 부분입니다.")
    print("  터미널에서 `claude` 를 실행하고 `/` 를 입력하면 사용 가능한 명령이 뜹니다.")
    print()
    print("  현재 config 기본값:")
    for kind, label, _d in analysis_store.KINDS:
        print(f"    {label:<12} {runner.SKILL_COMMANDS[kind]}")
    print()
    print(f"  {YELLOW}플러그인으로 설치했다면 접두어가 붙습니다{RESET}")
    print("    예) /anthropic-skills:company-decoder-korean")
    print("  다르면 앱 사이드바의 '분석 실행 설정' 에서 고칠 수 있습니다.")

    return True


def dry_run() -> None:
    print()
    print("=" * 72)
    print("4. 실제로 실행될 명령 (dry-run)")
    print("=" * 72)
    info = runner.cli_info()
    exe = info.path or "claude"

    inst = next((i for i in config.analysis_instruments() if i.analysis_key == "MU"), None)
    if inst is None:
        inst = config.analysis_instruments()[0]

    rel_out = f"{config.ANALYSIS_DIR}/{inst.analysis_key}/decoder.html"
    prompt = runner.build_prompt(inst.analysis_key, inst.name, "decoder", rel_out)

    print(f"  작업 디렉터리  {BASE}")
    print(f"  출력 경로      {rel_out}")
    print()
    print("  명령:")
    print(f"    {exe} -p '<프롬프트>' \\")
    print(f"      --output-format json \\")
    print(f"      --max-turns {runner.DEFAULT_MAX_TURNS} \\")
    print(f"      --permission-mode {runner.DEFAULT_PERMISSION_MODE} \\")
    print(f"      --allowedTools \"{runner.DEFAULT_ALLOWED_TOOLS}\"")
    print()
    print(f"  프롬프트 ({len(prompt)}자):")
    print(f"{DIM}" + "\n".join("    " + ln for ln in prompt.splitlines()) + f"{RESET}")


def show_jobs() -> None:
    print()
    print("=" * 72)
    print("저장된 작업 상태")
    print("=" * 72)
    keys = [i.analysis_key for i in config.analysis_instruments()]
    any_job = False
    for key in keys:
        rows = []
        for kind, label, _d in analysis_store.KINDS:
            job = runner.read_job(ANALYSIS, key, kind)
            if job.status == "idle":
                continue
            any_job = True
            cost = f"${job.cost_usd:.2f}" if job.cost_usd is not None else "—"
            turns = str(job.num_turns) if job.num_turns is not None else "—"
            el = job.elapsed_sec
            elapsed = f"{el // 60}분 {el % 60}초" if el is not None else "—"
            rows.append((label, job.status, elapsed, cost, turns, job.error[:50]))
        if rows:
            print(f"\n  [{key}]")
            for label, status, elapsed, cost, turns, err in rows:
                mark = {"done": GREEN, "running": YELLOW}.get(status, RED)
                print(f"    {mark}{status:<10}{RESET} {label:<12} "
                      f"{elapsed:<12} {cost:<8} {turns}턴")
                if err:
                    print(f"      {DIM}{err}{RESET}")
    if not any_job:
        print("  실행 기록이 없습니다.")


def main(argv: list[str]) -> int:
    ok = check_env()
    if "--dry-run" in argv:
        dry_run()
    if "--jobs" in argv:
        show_jobs()
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
