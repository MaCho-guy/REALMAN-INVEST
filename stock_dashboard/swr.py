"""저장해 둔 값 먼저 보여주고, 뒤에서 새로 받기 (stale-while-revalidate).

2026-11-11 "대시보드가 더 빠르게 호출되게". 느린 이유는 계산이 아니라
**기다림**이었습니다 (차트 조건 70종목 계산 0.2초, 나머지는 전부 네트워크):

1. **저장 시간이 끝나는 순간 화면이 멈춥니다.** st.cache_data 는 TTL 이
   지나면 값을 버리고, 그다음 누른 사람이 새로 받는 동안 기다립니다.
   시세는 60초라 1분 넘게 다른 화면을 보다 돌아오면 매번 몇 초씩 멈췄습니다.
2. **안 본 화면은 처음 누를 때 받기 시작합니다.** 섹션 버튼마다 그 화면
   몫을 처음부터 받습니다.
3. **앱이 다시 켜지면 전부 사라집니다.** 코드를 올려 앱이 재시작되면
   메모리 캐시가 비고 처음부터 다시 받습니다.

이 모듈의 처방:

1. TTL 이 지나도 **직전 값을 바로 돌려주고**, 새 값은 뒤에서 받습니다.
   다음에 화면을 그릴 때 새 값이 나옵니다. 너무 오래된 값(stale 한도를
   넘은 값)만 기다려서 받습니다.
2. warm() 으로 **안 본 화면의 데이터를 미리** 받아 둘 수 있습니다.
3. 받은 값을 **임시 폴더에 파일로도** 남깁니다. 프로세스가 다시 켜지면
   파일에서 먼저 읽습니다 (stale 한도 안의 것만).

같은 값을 동시에 두 번 받지 않습니다 (키마다 잠금). 새로 받다 실패하면
직전 값을 그대로 둡니다 — 오류가 좋은 값을 덮지 않습니다.

스트림릿에 의존하지 않습니다. 그래서 작업 스레드에서도 그대로 부를 수
있고 (스트림릿 캐시는 실행 문맥이 없는 스레드에서 경고를 냅니다),
스트림릿 없이 테스트됩니다.

**주의 — 화면에 보이는 값이 '직전 값' 일 수 있습니다.** 그래서 age() 로
몇 초 전 값인지 알 수 있게 하고, 화면 아래 속도 줄에 '뒤에서 새로 받는
중' 을 적습니다.
"""
from __future__ import annotations

import functools
import hashlib
import os
import pickle
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

#: 파일 사본을 둘 곳. 서버마다 다르고, 저장소에는 들어가지 않습니다.
DISK_DIR = os.path.join(tempfile.gettempdir(), "dash_swr")


def _code_version() -> str:
    """코드 판본 — BUILD.json(파일마다 해시) 의 해시.

    파일 사본은 객체를 그대로 저장합니다. 코드를 고쳐 데이터 클래스에
    칸이 늘었는데 옛 사본을 읽으면, 화면이 없는 칸을 찾다 오류가 납니다.
    코드가 바뀌면 판본이 바뀌어 옛 사본을 쓰지 않습니다.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BUILD.json")
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except OSError:
        return "nobuild"


CODE_VERSION = _code_version()
#: 파일 사본을 쓸지. 테스트가 끕니다.
DISK = True
#: **묵은 값이라도 먼저 보여주는 한도(초).** 0 이면 끔 (함수마다 정한 stale 만).
#: 앱이 이 값을 이틀로 올립니다. 휴대폰으로 가끔 여는 대시보드는 열 때마다
#: 저장된 값이 stale 을 넘겨 있어서(시세는 30분) **매번 처음처럼 기다렸습니다.**
#: 이제는 있는 값을 바로 그리고 뒤에서 새로 받은 다음 화면을 한 번 더 그립니다.
#: 화면은 '몇 분 전 값' 인지 적어야 합니다 — stale_report() 가 나이를 줍니다.
HARD_STALE = 0.0
#: 새로 받기가 실패하면 이 시간 동안 다시 시도하지 않습니다. 없으면 화면을
#: 그릴 때마다 실패한 요청을 또 보냅니다.
RETRY_AFTER = 60.0
#: 뒤에서 새로 받기에 쓰는 스레드 수. 야후·네이버를 너무 세게 두드리면
#: 막히므로 적게 둡니다.
BACKGROUND_WORKERS = 8


@dataclass
class _Entry:
    value: object = None
    at: float = 0.0               # 받은 시각 (time.time)
    ok: bool = False              # 값이 있는가
    refreshing: bool = False
    error: str = ""               # 마지막 새로 받기 실패
    retry_at: float = 0.0         # 실패 뒤 이 시각 전에는 다시 안 받음
    lock: threading.Lock = field(default_factory=threading.Lock)


_store: dict[str, _Entry] = {}
_store_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS,
                           thread_name_prefix="swr")
#: 미리 받기는 따로 — 오래 걸리는 재무 받기가 시세 새로 받기를 막지 않게
_warm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="swr-warm")
_registry: dict[str, "Cached"] = {}

#: 마지막 reset 이후 '직전 값으로 답하고 뒤에서 받는 중' 이 된 함수 이름.
#: 미리 받기 스레드에서 불린 것도 잡히도록 스레드별이 아니라 전역입니다
#: (여러 사람이 동시에 보면 섞이지만, 화면 아래 한 줄 표시용이라 감수).
_stale_names: list[str] = []
_stale_ages: dict[str, float] = {}
#: 값이 아직 **하나도 없어** peek 이 None 을 준 함수 이름 (받는 중)
_pending_names: list[str] = []
_stale_lock = threading.Lock()


def _entry(key: str) -> _Entry:
    with _store_lock:
        e = _store.get(key)
        if e is None:
            e = _store[key] = _Entry()
        return e


def _disk_path(key: str) -> str:
    h = hashlib.sha256(f"{CODE_VERSION}|{key}".encode("utf-8")).hexdigest()[:24]
    return os.path.join(DISK_DIR, f"{h}.pkl")


def _disk_load(key: str, max_age: float) -> tuple[object, float] | None:
    if not DISK:
        return None
    path = _disk_path(key)
    try:
        if time.time() - os.path.getmtime(path) > max_age:
            return None
        with open(path, "rb") as fh:
            saved_key, at, value = pickle.load(fh)
        # 해시가 겹치거나 코드가 바뀌어 다른 값이 들어 있을 수 있습니다
        return (value, at) if saved_key == key else None
    except Exception:  # noqa: BLE001 - 파일 사본은 있으면 좋은 것
        return None


def _disk_save(key: str, at: float, value: object) -> None:
    if not DISK:
        return
    try:
        os.makedirs(DISK_DIR, exist_ok=True)
        tmp = _disk_path(key) + f".{threading.get_ident()}.tmp"
        with open(tmp, "wb") as fh:
            pickle.dump((key, at, value), fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, _disk_path(key))
    except Exception:  # noqa: BLE001 - 저장 못 해도 메모리 값은 씁니다
        pass


def stale_served() -> list[str]:
    """reset 이후 '직전 값으로 답한' 함수 이름들 (중복 제거, 화면 아래 표시용)."""
    with _stale_lock:
        return list(dict.fromkeys(_stale_names))


def reset_stale_served() -> None:
    with _stale_lock:
        _stale_names.clear()
        _stale_ages.clear()
        _pending_names.clear()


def stale_report() -> tuple[float, list[str]]:
    """(직전 값으로 답한 것 중 가장 묵은 나이(초), 아직 값이 없어 받는 중인 이름들)."""
    with _stale_lock:
        oldest = max(_stale_ages.values(), default=0.0)
        return oldest, list(dict.fromkeys(_pending_names))


def busy() -> int:
    """지금 뒤에서 새로 받고 있는 항목 수 (미리 받기는 세지 않습니다)."""
    with _store_lock:
        return sum(1 for e in _store.values() if e.refreshing)


def _note_stale(name: str, age: float) -> None:
    with _stale_lock:
        _stale_names.append(name)
        _stale_ages[name] = max(age, _stale_ages.get(name, 0.0))


class Cached:
    """@cached(...) 로 감싼 함수. 부르면 값, .clear() 로 비우기."""

    def __init__(self, fn: Callable, ttl: float, stale: float,
                 keep: Callable[[object], bool] | None, disk: bool):
        self.fn = fn
        self.ttl = float(ttl)
        self.stale = float(max(stale, ttl))
        self.keep = keep
        self.disk = disk
        self.name = fn.__name__
        functools.update_wrapper(self, fn)
        _registry[self.name] = self

    # ── 키 ────────────────────────────────────────────────────────────────
    def key(self, args: tuple, kwargs: dict) -> str:
        return f"{self.fn.__module__}.{self.name}|{args!r}|{sorted(kwargs.items())!r}"

    # ── 받기 ──────────────────────────────────────────────────────────────
    def _fetch(self, key: str, args, kwargs, e: _Entry) -> None:
        """새로 받아 넣습니다. 잠금은 부르는 쪽이 잡고 있습니다."""
        try:
            value = self.fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            e.error = f"{type(exc).__name__}: {exc}"
            if not e.ok:
                raise
            return
        # 새 값이 '빈 값' 이면 좋은 직전 값을 덮지 않습니다
        if e.ok and self.keep is not None:
            try:
                if not self.keep(value):
                    e.error = "새로 받은 값이 비어 직전 값을 유지"
                    e.at = time.time() - self.ttl * 0.75   # 곧 다시 시도
                    return
            except Exception:  # noqa: BLE001
                pass
        e.value, e.at, e.ok, e.error = value, time.time(), True, ""
        if self.disk:
            _disk_save(key, e.at, value)

    def _window(self) -> float:
        """이 나이까지는 저장된 값을 (묵었어도) 바로 줍니다."""
        return max(self.stale, HARD_STALE)

    def _background(self, key: str, args, kwargs, e: _Entry) -> None:
        def run():
            try:
                with e.lock:
                    if time.time() - e.at >= self.ttl:     # 그사이 누가 받았으면 건너뜀
                        before = e.at
                        self._fetch(key, args, kwargs, e)
                        if e.at == before:                 # 못 받았음 — 잠시 쉼
                            e.retry_at = time.time() + RETRY_AFTER
            except Exception:  # noqa: BLE001
                e.retry_at = time.time() + RETRY_AFTER
            finally:
                e.refreshing = False
        e.refreshing = True
        try:
            _pool.submit(run)
        except RuntimeError:            # 인터프리터 종료 중
            e.refreshing = False

    def __call__(self, *args, **kwargs):
        key = self.key(args, kwargs)
        e = _entry(key)
        window = self._window()
        if not e.ok and self.disk:
            got = _disk_load(key, window)
            if got is not None:
                with e.lock:
                    if not e.ok:
                        e.value, e.at, e.ok = got[0], got[1], True
        if e.ok:
            age = time.time() - e.at
            if age < self.ttl:
                return e.value
            if age < window:
                if not e.refreshing and time.time() >= e.retry_at:
                    self._background(key, args, kwargs, e)
                _note_stale(self.name, age)
                return e.value
        # 값이 없거나 너무 오래됨 — 기다려서 받습니다 (같은 키는 한 번만)
        with e.lock:
            if not e.ok or time.time() - e.at >= window:
                self._fetch(key, args, kwargs, e)
            return e.value

    def peek(self, *args, **kwargs):
        """저장된 값이 있으면 (오래됐어도 stale 안이면) 돌려주고, 없으면
        **기다리지 않고** None — 그리고 뒤에서 받기 시작합니다.

        화면의 곁가지(예: 내 종목 표의 '차트 상태' 칸)에 씁니다. 곁가지 때문에
        본문이 기다리면 안 됩니다.
        """
        key = self.key(args, kwargs)
        e = _entry(key)
        window = self._window()
        if not e.ok and self.disk:
            got = _disk_load(key, window)
            if got is not None:
                with e.lock:
                    if not e.ok:
                        e.value, e.at, e.ok = got[0], got[1], True
        if e.ok and time.time() - e.at < window:
            age = time.time() - e.at
            if age >= self.ttl:
                if not e.refreshing and time.time() >= e.retry_at:
                    self._background(key, args, kwargs, e)
                _note_stale(self.name, age)
            return e.value
        with _stale_lock:
            _pending_names.append(self.name)
        if not e.refreshing and time.time() >= e.retry_at:
            def run():
                try:
                    self(*args, **kwargs)
                except Exception:  # noqa: BLE001
                    # 못 받았으면 잠시 쉽니다 — 화면이 다시 그려질 때마다
                    # 실패한 요청을 또 보내지 않게
                    e.retry_at = time.time() + RETRY_AFTER
                finally:
                    e.refreshing = False
            e.refreshing = True
            try:
                _pool.submit(run)
            except RuntimeError:
                e.refreshing = False
        return None

    def age(self, *args, **kwargs) -> float | None:
        e = _store.get(self.key(args, kwargs))
        return None if e is None or not e.ok else time.time() - e.at

    def clear(self) -> None:
        prefix = f"{self.fn.__module__}.{self.name}|"
        with _store_lock:
            for k in [k for k in _store if k.startswith(prefix)]:
                if DISK:
                    try:
                        os.remove(_disk_path(k))
                    except OSError:
                        pass
                del _store[k]


def cached(ttl: float, *, stale: float | None = None,
           keep: Callable[[object], bool] | None = None,
           disk: bool = True) -> Callable[[Callable], Cached]:
    """데코레이터.

    ttl    이 시간 안이면 저장된 값을 그대로 (초)
    stale  이 시간 안이면 저장된 값을 바로 주고 뒤에서 새로 받음.
           기본은 ttl 의 6배 (시세 60초 → 6분, 일봉 1시간 → 6시간)
    keep   새 값을 받아들일지. False 면 직전 값을 유지 (빈 결과가
           좋은 값을 덮지 않게)
    disk   임시 폴더에 사본을 남길지
    """
    def deco(fn: Callable) -> Cached:
        return Cached(fn, ttl, stale if stale is not None else ttl * 6, keep, disk)
    return deco


def clear_all() -> None:
    """메모리와 파일 사본을 모두 비웁니다 ('캐시 비우고 다시 불러오기')."""
    with _store_lock:
        _store.clear()
    if DISK:
        try:
            for name in os.listdir(DISK_DIR):
                if name.endswith(".pkl"):
                    os.remove(os.path.join(DISK_DIR, name))
        except OSError:
            pass


# ── 미리 받기 ─────────────────────────────────────────────────────────────────

_warm_lock = threading.Lock()
_warm_last: dict[str, float] = {}


def warm(tag: str, calls: dict[str, Callable[[], object]], *,
         every: float = 300.0) -> bool:
    """이름 → 인자 없는 함수들을 **뒤에서** 차례로 불러 저장해 둡니다.

    같은 tag 는 every 초에 한 번만. 화면을 기다리게 하지 않습니다 —
    부르고 바로 돌아옵니다. 시작했으면 True.
    """
    now = time.time()
    with _warm_lock:
        if now - _warm_last.get(tag, 0.0) < every:
            return False
        _warm_last[tag] = now

    def run_one(fn):
        try:
            fn()
        except Exception:  # noqa: BLE001 - 미리 받기 실패는 화면에서 다시 드러납니다
            pass

    for fn in calls.values():
        try:
            _warm_pool.submit(run_one, fn)
        except RuntimeError:
            return False
    return True


def registry() -> dict[str, Cached]:
    return dict(_registry)
