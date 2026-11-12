"""
인증키가 화면·기록·스냅샷에 새어 나가지 않게 지웁니다.

2026-11-12 에 찾은 문제. requests 의 연결 실패 메시지는 **요청 주소 전체**를
담습니다:

    Max retries exceeded with url: /api/list.json?crtfc_key=<키>&page_no=1

DART 와 FRED 는 키를 주소에 넣으므로, 연결이 실패하면 키가 오류 문구에
그대로 들어갑니다. 그 문구는 화면의 오류 안내와 진단 패널에 찍히고,
이 앱은 주소만 알면 누구나 볼 수 있습니다. 그래서 세 군데서 지웁니다:

  1. 오류를 만들 때 (DartError · FredError 가 문구를 받는 순간)
  2. 화면에 내보낼 때 (app 이 스트림릿 출력 함수를 감쌉니다)
  3. 스냅샷을 쓸 때 (swr.export_seed 가 키가 든 항목을 통째로 뺍니다)
"""
from __future__ import annotations

import os
import re

#: 이 환경변수의 **값**은 어디에도 찍히면 안 됩니다.
SECRET_ENVS = ("DART_API_KEY", "FRED_API_KEY", "GITHUB_TOKEN")

_QUERY = re.compile(r"(?i)\b(crtfc_key|api_key|apikey|access_token|token)=([^&\s'\"<>)]+)")


def secret_values() -> tuple[str, ...]:
    vals = []
    for name in SECRET_ENVS:
        v = (os.environ.get(name) or "").strip()
        if len(v) >= 8:
            vals.append(v)
    try:
        from . import fred  # noqa: PLC0415 - 화면에서 넣은 세션 키
        v = (fred.api_key() or "").strip()
        if len(v) >= 8:
            vals.append(v)
    except Exception:  # noqa: BLE001
        pass
    return tuple(dict.fromkeys(vals))


def scrub(text):
    """문자열에서 키 값과 '…_key=값' 을 가립니다. 문자열이 아니면 그대로."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for v in secret_values():
        if v in out:
            out = out.replace(v, "***")
    if "key=" in out.lower() or "token=" in out.lower():
        out = _QUERY.sub(lambda m: f"{m.group(1)}=***", out)
    return out


def wrap(fn):
    """화면 출력 함수를 감싸, 첫 인자(문구)를 지운 뒤 넘깁니다."""
    import functools  # noqa: PLC0415

    if getattr(fn, "_scrubbed", False):
        return fn

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if args and isinstance(args[0], str):
            args = (scrub(args[0]),) + args[1:]
        if isinstance(kwargs.get("body"), str):
            kwargs["body"] = scrub(kwargs["body"])
        return fn(*args, **kwargs)

    inner._scrubbed = True
    return inner


#: 문구를 그대로 화면에 찍는 스트림릿 함수들.
ST_OUTPUTS = ("markdown", "error", "warning", "info", "success", "caption",
              "code", "text", "write", "html", "exception")


def guard_streamlit(st) -> int:
    """스트림릿 출력 함수에 지우개를 답니다. 여러 번 불러도 한 번만 감쌉니다."""
    n = 0
    for name in ST_OUTPUTS:
        fn = getattr(st, name, None)
        if fn is None or getattr(fn, "_scrubbed", False):
            continue
        try:
            setattr(st, name, wrap(fn))
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n
