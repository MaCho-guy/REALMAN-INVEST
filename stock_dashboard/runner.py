"""
분석 실행 엔진 — Claude Code 헤드리스 모드로 스킬을 직접 돌립니다.

================================================================================
어떻게 동작하나
================================================================================
Claude Code 는 `-p`(`--print`) 플래그를 주면 대화형 UI 없이 같은 에이전트 루프를
한 번 돌리고 결과를 출력한 뒤 종료합니다. `--output-format json` 을 쓰면
result / session_id / total_cost_usd / num_turns / is_error 가 담긴 JSON 이 나옵니다.

커스텀 스킬은 파일시스템 기반(~/.claude/skills/ 또는 .claude/skills/)이라
API 업로드가 필요 없습니다. 따라서 이미 설치된 스킬을 그대로 쓸 수 있습니다.

    claude -p "/company-decoder-korean Micron ... analysis/MU/decoder.html 에 저장"
          --output-format json
          --max-turns 40
          --permission-mode dontAsk
          --allowedTools "Read,Write,Edit,Bash,WebSearch,WebFetch,Glob,Grep"

================================================================================
왜 스레드가 아니라 분리된 프로세스 + 상태 파일인가
================================================================================
Streamlit 은 위젯을 건드릴 때마다 스크립트 전체를 다시 실행합니다. 스레드나
session_state 에 작업을 담으면 재실행 때 참조가 끊기거나 중복 실행됩니다.

그래서 이 모듈은:
  1) 서브프로세스를 **분리(detached)** 로 띄우고 stdout/stderr 을 로그 파일로 보냅니다
  2) 작업 상태를 `analysis/<키>/.jobs/<종류>.json` 에 기록합니다
  3) UI 는 그 파일만 읽습니다

결과적으로 Streamlit 이 몇 번 재실행되든, 브라우저를 닫든 작업은 계속 돌아가고
상태는 파일에 남습니다.

================================================================================
비용 주의
================================================================================
한 번 실행할 때마다 토큰을 씁니다. 기업 해독기 한 건이 웹검색 10회 이상 +
계산 + HTML 생성이라 적지 않습니다. 완료된 작업의 `cost_usd` 를 UI 에 그대로
표시하니 실제 비용을 보고 판단하십시오. `--max-turns` 로 상한을 둡니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field, asdict

import analysis_store

JOBS_DIRNAME = ".jobs"

#: 스킬이 쓸 수 있는 도구. 필요한 최소로 제한합니다.
#: 웹검색·페이지읽기(자료 수집), 파일 쓰기(결과 저장), Bash(계산 스크립트 실행).
DEFAULT_ALLOWED_TOOLS = "Read,Write,Edit,Bash,WebSearch,WebFetch,Glob,Grep"

#: 무인 실행 권한 모드. 허용 목록(allowedTools)과 함께 쓰는 것이 권장 조합입니다.
DEFAULT_PERMISSION_MODE = "dontAsk"

#: 에이전트 루프 상한. 비용 폭주 방지용.
DEFAULT_MAX_TURNS = 40

#: 프로세스를 강제 종료할 시간(초). 기업 해독기 한 건에 10~20분 걸릴 수 있습니다.
DEFAULT_TIMEOUT_SEC = 2400

#: 스킬 슬래시 명령. 플러그인으로 설치했다면 접두어가 붙을 수 있으므로
#: config 에서 덮어쓸 수 있게 둡니다. 정확한 이름은 `claude` 를 띄워 `/` 를
#: 입력하면 목록으로 확인됩니다.
SKILL_COMMANDS = {
    "decoder": "/company-decoder-korean",
    "story": "/company-story-korean",
    "price": "/price-decoder-korean",
}


# ──────────────────────────────────────────────────────────────────────────────
# CLI 환경 점검
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CliInfo:
    available: bool
    path: str = ""
    version: str = ""
    error: str = ""

    @property
    def summary(self) -> str:
        if self.available:
            return f"claude {self.version}".strip()
        return self.error or "claude CLI 를 찾을 수 없습니다."


def cli_info() -> CliInfo:
    """`claude` 실행 파일이 있는지, 버전이 뭔지 확인합니다."""
    path = shutil.which("claude")
    if not path:
        return CliInfo(
            available=False,
            error=(
                "claude CLI 를 PATH 에서 찾을 수 없습니다. "
                "`npm install -g @anthropic-ai/claude-code` 로 설치하고, "
                "한 번 `claude` 를 실행해 로그인을 마치십시오."
            ),
        )
    try:
        proc = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
        version = (proc.stdout or proc.stderr or "").strip().splitlines()[:1]
        return CliInfo(available=True, path=path, version=version[0] if version else "")
    except (OSError, subprocess.SubprocessError) as exc:
        return CliInfo(available=False, path=path, error=f"버전 확인 실패: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# 작업 상태
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Job:
    """한 번의 분석 실행."""

    key: str                      # 종목 분석 키 (예: MU)
    kind: str                     # decoder | story | price
    status: str = "idle"          # idle | running | done | failed | cancelled | timeout
    pid: int | None = None
    started_at: str = ""
    finished_at: str = ""
    cost_usd: float | None = None
    num_turns: int | None = None
    session_id: str = ""
    error: str = ""
    command: list[str] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def elapsed_sec(self) -> int | None:
        if not self.started_at:
            return None
        try:
            started = dt.datetime.fromisoformat(self.started_at)
        except ValueError:
            return None
        end = dt.datetime.now(dt.timezone.utc)
        if self.finished_at:
            try:
                end = dt.datetime.fromisoformat(self.finished_at)
            except ValueError:
                pass
        return max(0, int((end - started).total_seconds()))


def _jobs_dir(base_dir: str, key: str) -> str:
    safe = analysis_store._safe_key(key)  # noqa: SLF001 - 같은 패키지의 경로 정제 로직 재사용
    return os.path.join(base_dir, safe, JOBS_DIRNAME)


def _job_path(base_dir: str, key: str, kind: str) -> str:
    return os.path.join(_jobs_dir(base_dir, key), f"{kind}.json")


def _log_path(base_dir: str, key: str, kind: str) -> str:
    return os.path.join(_jobs_dir(base_dir, key), f"{kind}.log")


def _write_job(base_dir: str, job: Job) -> None:
    folder = _jobs_dir(base_dir, job.key)
    os.makedirs(folder, exist_ok=True)
    tmp = _job_path(base_dir, job.key, job.kind) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(job), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _job_path(base_dir, job.key, job.kind))   # 원자적 교체


def read_job(base_dir: str, key: str, kind: str) -> Job:
    """작업 상태를 읽습니다. 파일이 없으면 idle 상태의 Job 을 돌려줍니다."""
    path = _job_path(base_dir, key, kind)
    if not os.path.isfile(path):
        return Job(key=key, kind=kind)
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            return Job(key=key, kind=kind, status="failed", error="작업 파일 형식 오류")
        allowed = {f for f in Job.__dataclass_fields__}
        return Job(**{k: v for k, v in raw.items() if k in allowed})
    except (OSError, ValueError, TypeError) as exc:
        return Job(key=key, kind=kind, status="failed", error=f"작업 파일 읽기 실패: {exc}")


def read_log(base_dir: str, key: str, kind: str, tail_bytes: int = 4000) -> str:
    """로그 파일의 끝부분을 읽습니다."""
    path = _log_path(base_dir, key, kind)
    if not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > tail_bytes:
                fh.seek(size - tail_bytes)
            data = fh.read()
        return data.decode("utf-8", errors="replace")
    except OSError as exc:
        return f"(로그 읽기 실패: {exc})"


def _proc_state(pid: int) -> str | None:
    """리눅스 /proc 에서 프로세스 상태 문자를 읽습니다. 없으면 None."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return None
    # 실행 파일명에 공백·괄호가 들어갈 수 있으므로 마지막 ')' 뒤부터 파싱합니다
    close = data.rfind(")")
    if close < 0:
        return None
    rest = data[close + 2 :].split()
    return rest[0] if rest else None


def _pid_alive(pid: int | None) -> bool:
    """프로세스가 아직 돌고 있는지 확인합니다.

    주의 — 좀비 처리:
      서브프로세스를 띄운 뒤 Popen 객체를 버리면 (Streamlit 재실행 때문에
      객체를 들고 있을 수 없습니다) 자식이 종료해도 수거(reap)되지 않아
      **좀비 상태로 남습니다.** 좀비에게 os.kill(pid, 0) 은 성공하므로,
      이것만으로 판단하면 끝난 작업이 영원히 '실행 중'으로 보입니다.

      그래서 먼저 waitpid(WNOHANG) 로 수거를 시도하고, 그래도 안 되면
      /proc 상태가 'Z'(좀비)인지 확인합니다.
    """
    if not pid:
        return False

    # 1) 우리 자식이면 수거를 시도합니다
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False          # 방금 수거됨 = 종료
    except ChildProcessError:
        pass                      # 우리 자식이 아님 (앱 재시작 후 등)
    except OSError:
        pass

    # 2) 리눅스면 좀비 여부를 직접 확인합니다
    state = _proc_state(pid)
    if state is not None:
        return state not in ("Z", "X", "x")

    # 3) /proc 이 없는 환경(macOS 등) — 신호로 확인
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True               # 살아 있으나 신호를 보낼 권한이 없음
    except OSError:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 프롬프트
# ──────────────────────────────────────────────────────────────────────────────

def build_prompt(key: str, name: str, kind: str, rel_out: str,
                 skill_commands: dict[str, str] | None = None) -> str:
    """헤드리스 실행에 넘길 프롬프트.

    헤드리스 모드에는 아티팩트 도구가 없으므로, 스킬이 만든 HTML 을
    지정 경로에 파일로 저장하도록 명시합니다.
    """
    commands = skill_commands or SKILL_COMMANDS
    cmd = commands.get(kind, "")
    label = analysis_store.kind_label(kind)

    return (
        f"{cmd} {name} ({key})\n\n"
        f"[출력 요구사항 — 반드시 지켜주세요]\n"
        f"1. 위 스킬의 지침을 그대로 따라 '{label}' 분석을 수행하세요.\n"
        f"2. 이 환경에는 아티팩트 도구가 없습니다. 결과 HTML 을 "
        f"`{rel_out}` 경로에 **파일로 저장**하세요.\n"
        f"3. HTML 은 `<div>` 로 시작하는 본문 조각이 아니라 "
        f"`<!DOCTYPE html>` 로 시작하는 완결된 문서로 저장하세요. "
        f"스타일은 문서 안에 `<style>` 로 포함하고, 외부 CDN 을 참조하지 마세요.\n"
        f"4. 흰 배경·검정 텍스트·파랑 강조의 미니멀 스타일로, 인쇄해도 읽히게 만드세요.\n"
        f"5. 수치 계산은 반드시 코드 실행으로 하고, 출처 없는 숫자는 쓰지 마세요. "
        f"확인이 안 되는 값은 '확인 필요'로 남기세요.\n"
        f"6. 저장을 마치면 마지막 줄에 `SAVED: {rel_out}` 만 출력하세요.\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────────────────────

def start_job(
    base_dir: str,
    project_root: str,
    key: str,
    name: str,
    kind: str,
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
    skill_commands: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
) -> Job:
    """분석을 백그라운드로 시작합니다.

    base_dir      analysis/ 절대 경로
    project_root  claude 를 실행할 작업 디렉터리 (프로젝트 루트)
    """
    info = cli_info()
    if not info.available:
        job = Job(key=key, kind=kind, status="failed", error=info.summary)
        _write_job(base_dir, job)
        return job

    existing = read_job(base_dir, key, kind)
    if existing.is_running and _pid_alive(existing.pid):
        return existing          # 이미 돌고 있으면 중복 실행하지 않습니다

    safe = analysis_store._safe_key(key)  # noqa: SLF001
    if not safe:
        job = Job(key=key, kind=kind, status="failed", error=f"잘못된 분석 키: {key}")
        _write_job(base_dir, job)
        return job

    out_dir = os.path.join(base_dir, safe)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(_jobs_dir(base_dir, key), exist_ok=True)

    # claude 는 project_root 에서 실행되므로 상대 경로로 넘깁니다
    rel_out = os.path.relpath(os.path.join(out_dir, f"{kind}.html"), project_root)
    rel_out = rel_out.replace(os.sep, "/")

    prompt = build_prompt(safe, name, kind, rel_out, skill_commands)

    cmd = [
        info.path, "-p", prompt,
        "--output-format", "json",
        "--max-turns", str(max_turns),
        "--permission-mode", permission_mode,
        "--allowedTools", allowed_tools,
    ]
    if extra_args:
        cmd.extend(extra_args)

    log_file = _log_path(base_dir, key, kind)
    job = Job(
        key=safe, kind=kind, status="running",
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        command=cmd[:1] + ["-p", f"<{len(prompt)}자 프롬프트>"] + cmd[3:],
    )

    try:
        log_fh = open(log_file, "wb")
    except OSError as exc:
        job.status, job.error = "failed", f"로그 파일 생성 실패: {exc}"
        _write_job(base_dir, job)
        return job

    try:
        # start_new_session=True : 부모(Streamlit)가 죽어도 살아남습니다
        proc = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except (OSError, ValueError) as exc:
        log_fh.close()
        job.status, job.error = "failed", f"프로세스 실행 실패: {exc}"
        _write_job(base_dir, job)
        return job
    finally:
        try:
            log_fh.close()
        except OSError:
            pass

    job.pid = proc.pid
    _write_job(base_dir, job)
    return job


def poll_job(base_dir: str, key: str, kind: str,
             timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> Job:
    """running 상태의 작업이 끝났는지 확인하고 상태를 갱신합니다.

    UI 가 화면을 그릴 때마다 호출하면 됩니다. 멱등합니다.
    """
    job = read_job(base_dir, key, kind)
    if not job.is_running:
        return job

    if _pid_alive(job.pid):
        # 타임아웃 초과 시 종료
        elapsed = job.elapsed_sec or 0
        if elapsed > timeout_sec:
            _terminate(job.pid)
            job.status = "timeout"
            job.error = f"{timeout_sec}초를 넘겨 중단했습니다."
            job.finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            _write_job(base_dir, job)
        return job

    # 프로세스가 끝났다 → 로그에서 JSON 결과를 읽는다
    job.finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    raw = read_log(base_dir, key, kind, tail_bytes=2_000_000)
    parsed = _parse_result(raw)

    out_html = os.path.join(base_dir, analysis_store._safe_key(key), f"{kind}.html")  # noqa: SLF001
    produced = os.path.isfile(out_html) and os.path.getsize(out_html) > 400

    job.cost_usd = parsed.get("cost_usd")
    job.num_turns = parsed.get("num_turns")
    job.session_id = parsed.get("session_id") or ""

    if parsed.get("is_error"):
        job.status = "failed"
        job.error = _explain_failure(parsed)
    elif not parsed:
        job.status = "failed"
        job.error = (
            "claude 의 JSON 결과를 찾지 못했습니다. 실행이 비정상 종료했거나 "
            "CLI 버전이 --output-format json 을 지원하지 않을 수 있습니다. "
            "아래 로그를 확인하십시오."
        )
    elif not produced:
        job.status = "failed"
        job.error = (
            f"실행은 정상 종료했지만 {kind}.html 이 생성되지 않았습니다. "
            f"스킬 슬래시 명령 이름이 맞는지 확인하십시오 — 터미널에서 `claude` 실행 후 "
            f"`/` 를 입력하면 목록이 보입니다. 플러그인으로 설치했다면 "
            f"'/anthropic-skills:...' 처럼 접두어가 붙습니다. "
            f"사이드바 '분석 실행 설정'에서 고칠 수 있습니다."
        )
    else:
        job.status = "done"
        _touch_meta(base_dir, key, parsed)

    _write_job(base_dir, job)
    return job


def _parse_result(raw: str) -> dict:
    """로그에서 `--output-format json` 결과를 찾아 파싱합니다.

    로그에는 진행 메시지가 섞일 수 있으므로, JSON 객체로 보이는 줄을
    뒤에서부터 찾습니다.
    """
    out: dict = {}
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for line in reversed(lines):
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if {"result", "session_id", "total_cost_usd"} & set(obj):
            out["cost_usd"] = obj.get("total_cost_usd")
            out["num_turns"] = obj.get("num_turns")
            out["session_id"] = obj.get("session_id")
            out["is_error"] = bool(obj.get("is_error"))
            out["terminal_reason"] = obj.get("terminal_reason") or ""
            denials = obj.get("permission_denials")
            if isinstance(denials, list) and denials:
                names = []
                for d in denials:
                    if isinstance(d, dict):
                        names.append(str(d.get("tool_name") or d.get("tool") or d))
                    else:
                        names.append(str(d))
                out["denied_tools"] = sorted(set(names))
            if obj.get("is_error"):
                res = obj.get("result")
                out["error"] = str(res)[:400] if res else ""
            return out
    return out


def _explain_failure(parsed: dict) -> str:
    """실패 사유를 사용자가 바로 조치할 수 있는 문장으로 바꿉니다."""
    raw = (parsed.get("error") or "").strip()
    reason = (parsed.get("terminal_reason") or "").strip()
    denied = parsed.get("denied_tools") or []

    low = raw.lower()

    if "authentication" in low or "unauthorized" in low or "401" in low:
        return (
            "Claude Code 인증 실패입니다. 터미널에서 `claude` 를 한 번 실행해 "
            "로그인을 마치거나, ANTHROPIC_API_KEY 환경변수를 설정한 뒤 "
            "이 앱을 재시작하십시오."
        )

    if denied:
        return (
            f"도구 사용이 거부됐습니다: {', '.join(denied)}. "
            f"현재 허용 목록은 '{DEFAULT_ALLOWED_TOOLS}' 입니다. "
            f"스킬이 다른 도구를 필요로 하면 runner.py 의 DEFAULT_ALLOWED_TOOLS 에 "
            f"추가하십시오."
        )

    if "max turns" in low or reason == "max_turns":
        return (
            "최대 턴 수에 걸려 중단됐습니다. 사이드바 '분석 실행 설정'에서 "
            "턴 수를 올리고 다시 실행하십시오. 비용도 함께 올라갑니다."
        )

    if "rate limit" in low or "429" in low:
        return "요청 한도에 걸렸습니다. 잠시 후 다시 실행하십시오."

    if reason == "api_error" and raw:
        return f"API 오류: {raw}"

    if raw:
        return raw

    return "claude 가 오류로 종료했습니다. 아래 로그를 확인하십시오."


def _touch_meta(base_dir: str, key: str, parsed: dict) -> None:
    """생성 성공 시 meta.json 의 생성일·모드를 갱신합니다. 기존 값은 보존합니다."""
    safe = analysis_store._safe_key(key)  # noqa: SLF001
    path = os.path.join(base_dir, safe, "meta.json")
    meta: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, ValueError):
            meta = {}

    meta["generated"] = dt.date.today().isoformat()
    meta.setdefault("name", safe)
    meta.setdefault("mode", "web")
    meta.setdefault("sources", [])
    note = meta.get("note") or ""
    stamp = f"Claude Code 헤드리스 실행으로 생성"
    if parsed.get("cost_usd") is not None:
        stamp += f" (비용 ${parsed['cost_usd']:.2f})"
    meta["note"] = stamp if not note else note

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError:
        pass


def _terminate(pid: int | None) -> None:
    if not pid:
        return
    try:
        # 프로세스 그룹 전체에 보냅니다 (start_new_session=True 로 띄웠으므로)
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def cancel_job(base_dir: str, key: str, kind: str) -> Job:
    """돌고 있는 작업을 중단합니다."""
    job = read_job(base_dir, key, kind)
    if job.is_running and _pid_alive(job.pid):
        _terminate(job.pid)
        job.status = "cancelled"
        job.error = "사용자가 중단했습니다."
        job.finished_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        _write_job(base_dir, job)
    return job


def poll_all(base_dir: str, keys: list[str]) -> dict[tuple[str, str], Job]:
    """여러 종목의 모든 작업 상태를 갱신해서 돌려줍니다."""
    out: dict[tuple[str, str], Job] = {}
    for key in keys:
        for kind in analysis_store.KIND_KEYS:
            out[(key, kind)] = poll_job(base_dir, key, kind)
    return out


def running_count(jobs: dict[tuple[str, str], Job]) -> int:
    return sum(1 for j in jobs.values() if j.is_running)


if __name__ == "__main__":
    info = cli_info()
    print(f"claude CLI: {'사용 가능' if info.available else '사용 불가'}")
    print(f"  경로   {info.path or '—'}")
    print(f"  버전   {info.version or '—'}")
    if not info.available:
        print(f"  사유   {info.error}")
        sys.exit(1)
