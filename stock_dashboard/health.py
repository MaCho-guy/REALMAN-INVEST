"""
받아온 값이 '쓸 만한가' 를 **모양만 보고** 판단합니다.

받는 함수들은 실패해도 예외를 올리지 않고 '빈 값 + 오류 문구' 를 돌려줍니다
(화면이 한 줄 실패로 멈추지 않게). 그래서 값만 봐서는 성공인지 실패인지
모릅니다. 두 곳에서 이 판단이 필요합니다:

  · 아침 수집기 (tools/collect.py) — 실패한 결과를 스냅샷에 넣으면 앱이
    **실패를 물려받습니다.**
  · 저장소 (swr.py) — 새로 받기가 실패했을 때 그 결과로 **멀쩡한 직전
    값을 덮으면 안 됩니다.** 2026-11-12 실제 화면: 아침 스냅샷으로 잘
    보이던 시장 공시가, 서버에서 DART 연결이 한 번 시간 초과되자 '공시를
    받지 못했습니다' 로 바뀌었습니다.
"""
from __future__ import annotations


def health(value, _depth: int = 0) -> tuple[int, int]:
    """(쓸 만한 것, 실패한 것) 을 셉니다 — 값의 모양만 보고 판단합니다.

    받는 함수들은 실패해도 예외를 올리지 않고 '빈 값 + 오류 문구' 를
    돌려줍니다 (화면이 한 줄 실패로 멈추지 않게). 그대로 스냅샷에 넣으면
    앱이 **실패를 물려받아** 직접 받으면 됐을 것까지 비어 보입니다.
    """
    if value is None or _depth > 6:
        return 0, 0
    if isinstance(value, (str, bytes, int, float, bool)):
        return 0, 0
    if isinstance(value, tuple) and value and all(
            isinstance(v, (str, bytes, int, float, bool, type(None))) for v in value):
        # 글자·숫자만 든 한 줄 — 예: (이름, 값, 메모). 2026-11-12 첫 실행에서
        # 이런 줄을 전부 '쓸 것 없음' 으로 세어 멀쩡한 국내 지표·유동성을
        # 스냅샷에서 뺐습니다. 값 자리가 '—' 이거나 '실패' 가 적혀 있을 때만
        # 실패로 봅니다 (이 앱이 못 받은 칸을 적는 방식).
        texts = [v for v in value if isinstance(v, str)]
        if value[0] is None:                 # (None, "왜 못 받았는지") 모양
            return (0, 1) if any(texts) else (0, 0)
        if any(t.strip() == "—" or "실패" in t for t in texts):
            return 0, 1
        return (1, 0) if any(v not in (None, "", 0) for v in value) else (0, 0)
    if isinstance(value, tuple):
        tail = value[-1] if value else None
        tail_is_error = isinstance(tail, str) or (
            isinstance(tail, dict) and tail
            and all(isinstance(v, str) for v in tail.values()))
        body = value[:-1] if (tail_is_error and len(value) >= 2) else value
        good = bad = 0
        for item in body:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        if tail_is_error and tail:
            bad += len(tail) if isinstance(tail, dict) else 1
        return good, bad
    if isinstance(value, dict):
        if not value:
            return 0, 0
        if "error" in value or "_error" in value:
            # {rows, error} 처럼 결과와 실패 사유를 함께 담는 묶음
            if value.get("error") or value.get("_error"):
                return 0, 1
            rest = [v for k, v in value.items() if k not in ("error", "_error")]
            return (1, 0) if any(bool(v) for v in rest) else (0, 0)
        vals = list(value.values())[:400]
        if all(isinstance(v, (str, bytes, int, float, bool, type(None))) for v in vals):
            return 1, 0
        good = bad = 0
        for item in vals:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        return good, bad
    if isinstance(value, (list, set, frozenset)):
        vals = list(value)[:400]
        if not vals:
            return 0, 0
        if all(isinstance(v, (str, bytes, int, float, bool, type(None))) for v in vals):
            return 1, 0
        good = bad = 0
        for item in vals:
            g, b = health(item, _depth + 1)
            good, bad = good + g, bad + b
        return good, bad
    # 우리 자료형 — error 가 차 있으면 실패, 아니면 쓸 만한 값
    if getattr(value, "error", None):
        return 0, 1
    return 1, 0


def first_error(value, _depth: int = 0) -> str:
    """값 안에서 처음 만나는 실패 문구 — 로그에 '왜 뺐는지' 적는 데 씁니다."""
    if value is None or _depth > 6:
        return ""
    if isinstance(value, str):
        return ""
    err = getattr(value, "error", None)
    if isinstance(err, str) and err:
        return err
    if isinstance(value, dict):
        for key in ("error", "_error"):
            if isinstance(value.get(key), str) and value.get(key):
                return value[key]
        for v in list(value.values())[:50]:
            if isinstance(v, str) and _depth > 0 and v:
                return v
            got = first_error(v, _depth + 1)
            if got:
                return got
        return ""
    if isinstance(value, tuple):
        if value and all(isinstance(v, (str, int, float, bool, type(None))) for v in value):
            texts = [v for v in value if isinstance(v, str) and v]
            if texts and (value[0] is None
                          or any(t.strip() == "—" or "실패" in t for t in texts)):
                return texts[-1]
            return ""
        tail = value[-1] if value else None
        if isinstance(tail, str) and tail:
            return tail
        for v in reversed(value):
            got = first_error(v, _depth + 1)
            if got:
                return got
        return ""
    if isinstance(value, (list, set, frozenset)):
        for v in list(value)[:50]:
            got = first_error(v, _depth + 1)
            if got:
                return got
    return ""


def looks_failed(value) -> bool:
    """쓸 만한 것이 없거나, 실패가 더 많으면 스냅샷에 넣지 않습니다."""
    good, bad = health(value)
    return good == 0 or bad >= good
