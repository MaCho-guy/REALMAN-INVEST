"""잠금 — '내 종목' 탭 · 보유 평가(PORTFOLIO) · 진단 패널을 비밀번호 뒤에 둡니다.

2026-11-13 추가 (사용자 요청 "내 종목 탭 비밀번호로 잠그고 개인정보 안 새게").

**왜 필요한가.** 보유 수량 · 평균단가는 Streamlit Secrets 에 있어 저장소로는
새지 않습니다. 하지만 앱이 그 값을 읽어 화면에 그리므로, 앱 주소를 아는
사람은 누구나 볼 수 있었습니다. Secrets 는 "코드에서 안 보이게" 일 뿐
"화면에서 안 보이게" 가 아닙니다. 진단 패널도 누구나 눌러 내 DART · FRED
키로 호출을 보내거나 캐시를 비울 수 있었습니다.

**어떻게 막나.**
  - Secrets 맨 위에 ``DASH_PASSWORD = "8자 이상"`` 한 줄.
  - 맞는 비밀번호를 넣은 **그 브라우저 세션만** 풀립니다(스트림릿 세션 상태).
    서버 전체 변수에 두면 한 사람이 풀 때 모두에게 풀리므로 절대 그렇게 하지 않습니다.
  - 비밀번호가 Secrets 에 없거나 8자 미만이면 **늘 잠김**(실수로 열리지 않게).
  - 같은 세션에서 5번 틀리면 60초 동안 입력을 받지 않습니다. 새 세션을 열면
    다시 시도할 수 있으므로 완전한 방어는 아닙니다 — 긴 비밀번호가 진짜 방어입니다.
  - 비교는 hmac.compare_digest(글자 수가 같아도 걸린 시간으로 추측 못 하게).

순수 파이썬 — 스트림릿 없음. 세션 상태는 dict 처럼 넘겨받습니다(테스트 가능).
"""
from __future__ import annotations

import hmac
import os
import time

PASSWORD_ENV = "DASH_PASSWORD"
MIN_LEN = 8
MAX_TRIES = 5
LOCK_SEC = 60

_OK = "_dash_unlocked"
_TRIES = "_dash_tries"
_UNTIL = "_dash_locked_until"


def _secret() -> str:
    return (os.environ.get(PASSWORD_ENV) or "").strip()


def configured() -> bool:
    """비밀번호가 Secrets 에 쓸 만한 길이로 들어 있나."""
    return len(_secret()) >= MIN_LEN


def unlocked(state) -> bool:
    """이 세션이 풀렸나. 비밀번호가 없거나 바뀌면 다시 잠깁니다."""
    if not configured():
        return False
    try:
        mark = state.get(_OK)
    except Exception:  # noqa: BLE001
        return False
    # 풀린 표시로 비밀번호 자체가 아니라 '지문'을 둡니다 — 비밀번호를 바꾸면 풀린 세션도 잠김
    return isinstance(mark, str) and hmac.compare_digest(mark, _fingerprint(_secret()))


def _fingerprint(secret: str) -> str:
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(("dash-lock:" + secret).encode("utf-8")).hexdigest()[:16]


def try_unlock(state, typed: str, now: float | None = None) -> tuple[bool, str]:
    """입력한 비밀번호로 풀어 봅니다 → (풀렸나, 안내 문구)."""
    now = time.time() if now is None else now
    if not configured():
        return False, (f"Secrets 에 {PASSWORD_ENV} 가 없거나 {MIN_LEN}자 미만이라 "
                       "잠금을 풀 수 없습니다.")
    until = float(state.get(_UNTIL) or 0)
    if now < until:
        return False, f"너무 많이 틀렸습니다. {int(until - now) + 1}초 뒤에 다시 하십시오."
    typed = (typed or "").strip()
    if typed and hmac.compare_digest(typed.encode("utf-8"), _secret().encode("utf-8")):
        state[_OK] = _fingerprint(_secret())
        state[_TRIES] = 0
        state[_UNTIL] = 0
        return True, ""
    tries = int(state.get(_TRIES) or 0) + 1
    state[_TRIES] = tries
    if tries >= MAX_TRIES:
        state[_TRIES] = 0
        state[_UNTIL] = now + LOCK_SEC
        return False, f"{MAX_TRIES}번 틀려 {LOCK_SEC}초 동안 입력을 받지 않습니다."
    return False, f"비밀번호가 맞지 않습니다 ({tries}/{MAX_TRIES})."


def lock(state) -> None:
    """다시 잠그기."""
    try:
        state.pop(_OK, None)
    except Exception:  # noqa: BLE001
        pass
