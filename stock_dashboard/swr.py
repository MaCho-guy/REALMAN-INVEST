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
import sys
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


#: keep 을 정하지 않은 받기에 공통 규칙(실패가 좋은 값을 덮지 않음)을 쓸지.
AUTO_KEEP = True
#: 직전 값을 이 나이까지만 붙듭니다. 넘으면 실패를 그대로 보여줍니다.
KEEP_GOOD_MAX = 2 * 86_400.0
#: 실패 모양의 값은 이 시간만 '새것' 으로 칩니다 (그 뒤엔 다시 받음).
FAILED_TTL = 120.0


def _looks_failed(value) -> bool:
    # 글자·숫자 하나짜리 값은 모양으로 판단할 수 없습니다 — 실패로 보지 않습니다
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return False
    try:
        import health  # noqa: PLC0415
        return bool(health.looks_failed(value))
    except Exception:  # noqa: BLE001 - 판단을 못 하면 실패로 보지 않습니다
        return False


def _first_error(value) -> str:
    try:
        import health  # noqa: PLC0415
        return str(health.first_error(value) or "")
    except Exception:  # noqa: BLE001
        return ""


def _scrub(text: str) -> str:
    """오류 문구에서 인증키를 지웁니다 (sources.safe 가 없으면 그대로)."""
    try:
        from sources import safe  # noqa: PLC0415
        return safe.scrub(text)
    except Exception:  # noqa: BLE001
        return text


@dataclass
class _Entry:
    value: object = None
    at: float = 0.0               # 받은 시각 (time.time)
    ok: bool = False              # 값이 있는가
    refreshing: bool = False
    error: str = ""               # 마지막 새로 받기 실패
    failed: bool = False          # 지금 든 값이 실패 모양인가 (금방 다시 받음)
    retry_at: float = 0.0         # 실패 뒤 이 시각 전에는 다시 안 받음
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: 뒤에서 받기가 끝나면 켜집니다 (wait_fresh 가 이걸 기다립니다)
    done: threading.Event = field(default_factory=threading.Event)
    #: 새 값을 기다려 줄 마지막 시각 — 한 번의 새로 받기에 한 번만 기다립니다
    wait_until: float = 0.0


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

#: 이번 화면을 그리면서 **쓴 값들의 받은 시각** — 화면에 '언제 받은 값인지'
#: 적는 데 씁니다. 화면을 그리는 스레드에만 기록합니다 (스레드별 저장):
#: 뒤에서 도는 미리 받기가 섞이면 이 화면에 없는 것까지 적히기 때문입니다.
_tl = threading.local()


def _note_served(name: str, at: float) -> None:
    served = getattr(_tl, "served", None)
    if served is not None and at:
        served.setdefault(name, []).append(at)


def served_times() -> dict[str, tuple[float, float]]:
    """{함수 이름: (가장 오래된 받은 시각, 가장 최근 받은 시각)} — 이번 화면에서 쓴 것만.

    reset_stale_served() 를 부른 스레드에서만 값이 있습니다.
    """
    served = getattr(_tl, "served", None) or {}
    return {name: (min(ats), max(ats)) for name, ats in served.items() if ats}



def _entry(key: str) -> _Entry:
    with _store_lock:
        e = _store.get(key)
        if e is None:
            e = _store[key] = _Entry()
        return e


def _disk_path(key: str) -> str:
    h = hashlib.sha256(f"v2|{key}".encode("utf-8")).hexdigest()[:24]
    return os.path.join(DISK_DIR, f"{h}.pkl")


# ── 파일 사본이 '지금 코드' 와 맞는지 ────────────────────────────────────────
#
# 예전에는 코드 판본(BUILD.json 해시)을 파일 이름에 넣어서, **파일 하나만
# 고쳐도 모든 사본을 버렸습니다.** 새 판을 올릴 때마다 10년치 재무(12초)까지
# 처음부터 다시 받은 이유입니다. 이제는 사본마다 '이 값 안의 객체를 정의한
# 파일들' 의 해시를 같이 적어 두고, 읽을 때 그 파일들이 그대로인지만 봅니다.
# 차트 지표 코드를 고쳐도 재무 심사 사본은 살아남습니다.

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_file_hash_memo: dict[str, tuple[float, str]] = {}


def _module_hash(name: str) -> str | None:
    """모듈 파일의 해시. 앱 폴더 밖(표준·외부 라이브러리)이면 None."""
    if name in ("__main__", "__mp_main__"):
        return "main:" + CODE_VERSION          # 본문 스크립트 — 보수적으로
    mod = sys.modules.get(name)
    path = getattr(mod, "__file__", None)
    if not path:
        return None
    path = os.path.abspath(path)
    if not path.startswith(_APP_DIR + os.sep):
        return None
    try:
        mtime = os.path.getmtime(path)
        memo = _file_hash_memo.get(path)
        if memo and memo[0] == mtime:
            return memo[1]
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()[:16]
        _file_hash_memo[path] = (mtime, digest)
        return digest
    except OSError:
        return "missing"


_PLAIN = (str, bytes, int, float, bool, type(None))


def _class_modules(value, limit: int = 400_000) -> set[str]:
    """값 안에 든 객체들의 클래스가 정의된 모듈 이름 (앱 폴더 것만 의미 있음)."""
    found: set[str] = set()
    stack = [value]
    seen: set[int] = set()
    count = 0
    while stack:
        v = stack.pop()
        if isinstance(v, _PLAIN):
            continue
        count += 1
        if count > limit:
            found.add("__main__")              # 너무 큼 — 보수적으로 판본에 묶음
            break
        if id(v) in seen:
            continue
        seen.add(id(v))
        if isinstance(v, dict):
            stack.extend(v.keys())
            stack.extend(v.values())
        elif isinstance(v, (list, tuple, set, frozenset)):
            stack.extend(v)
        else:
            found.add(type(v).__module__)
            inner = getattr(v, "__dict__", None)
            if isinstance(inner, dict):
                stack.extend(inner.values())
            slots = getattr(type(v), "__slots__", ())
            for name in (slots if isinstance(slots, (list, tuple)) else (slots,)):
                if isinstance(name, str) and hasattr(v, name):
                    stack.append(getattr(v, name))
    return found


def _deps_of(value) -> dict[str, str]:
    out = {}
    for name in _class_modules(value):
        digest = _module_hash(name)
        if digest is not None:
            out[name] = digest
    return out


def _disk_load(key: str, max_age: float) -> tuple[object, float] | None:
    if not DISK:
        return None
    path = _disk_path(key)
    try:
        if time.time() - os.path.getmtime(path) > max_age:
            return None
        with open(path, "rb") as fh:
            saved_key, at, deps = pickle.load(fh)        # 머리말 먼저
            if saved_key != key:
                return None
            # 값 안의 객체를 정의한 파일이 하나라도 바뀌었으면 버립니다 —
            # 칸이 늘어난 클래스에 옛 객체를 넣으면 화면이 없는 칸을 찾습니다.
            for name, digest in deps.items():
                if name not in sys.modules:
                    try:
                        __import__(name)
                    except Exception:  # noqa: BLE001
                        return None
                if _module_hash(name) != digest:
                    return None
            value = pickle.load(fh)
        return value, at
    except Exception:  # noqa: BLE001 - 파일 사본은 있으면 좋은 것
        return None


def _disk_save(key: str, at: float, value: object) -> None:
    if not DISK:
        return
    try:
        os.makedirs(DISK_DIR, exist_ok=True)
        tmp = _disk_path(key) + f".{threading.get_ident()}.tmp"
        with open(tmp, "wb") as fh:
            pickle.dump((key, at, _deps_of(value)), fh,
                        protocol=pickle.HIGHEST_PROTOCOL)
            pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, _disk_path(key))
    except Exception:  # noqa: BLE001 - 저장 못 해도 메모리 값은 씁니다
        pass


def stale_served() -> list[str]:
    """reset 이후 '직전 값으로 답한' 함수 이름들 (중복 제거, 화면 아래 표시용)."""
    with _stale_lock:
        return list(dict.fromkeys(_stale_names))


def reset_stale_served() -> None:
    _tl.served = {}
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


def _module_name(fn: Callable) -> str:
    """키에 쓸 모듈 이름. 본문 스크립트(__main__)는 **파일 이름**으로 적습니다.

    스트림릿은 app.py 를 __main__ 으로 돌리고, 아침 수집기는 같은 파일을
    'app' 이라는 모듈로 불러옵니다. 이름이 다르면 수집해 둔 값을 앱이 못
    찾으므로, 둘 다 'app' 이 되게 합니다.
    """
    mod = getattr(fn, "__module__", "") or ""
    if mod in ("__main__", "__mp_main__"):
        try:
            return os.path.splitext(os.path.basename(fn.__code__.co_filename))[0]
        except AttributeError:
            return mod
    return mod


class Cached:
    """@cached(...) 로 감싼 함수. 부르면 값, .clear() 로 비우기."""

    def __init__(self, fn: Callable, ttl, stale: float,
                 keep: Callable[[object], bool] | None, disk: bool,
                 wait_fresh: float = 0.0, version: int = 0):
        self.fn = fn
        #: ttl 은 숫자이거나 **함수**(인자를 받아 초를 돌려줌)입니다. 장중에는
        #: 5분, 장이 닫히면 1시간처럼 때에 따라 달라지는 것에 씁니다.
        self._ttl_fn = ttl if callable(ttl) else None
        self.ttl = 0.0 if callable(ttl) else float(ttl)
        self.stale = float(stale) if self._ttl_fn else float(max(stale, ttl))
        self.keep = keep
        self.disk = disk
        #: 묵은 값을 주기 전에 새 값을 이만큼(초) 기다려 봅니다. 시세처럼
        #: '옛 값이 잠깐이라도 보이면 곤란한' 것에 씁니다. 0 이면 안 기다림.
        self.wait_fresh = float(wait_fresh)
        #: 돌려주는 값의 **모양이나 계산이 바뀌면** 올리는 번호. 키에 들어가므로
        #: 올리면 메모리·임시 폴더·스냅샷에 남은 옛 값을 쓰지 않습니다.
        #: (우리 자료형이 든 값은 코드 해시로 저절로 걸러지지만, 글자·숫자만
        #: 든 값은 걸러 낼 근거가 없어 이 번호가 필요합니다.)
        self.version = int(version)
        self.name = fn.__name__
        self.module = _module_name(fn)
        functools.update_wrapper(self, fn)
        _registry[self.name] = self

    def ttl_for(self, args: tuple = ()) -> float:
        if self._ttl_fn is None:
            return self.ttl
        try:
            return float(self._ttl_fn(*args))
        except Exception:  # noqa: BLE001
            return 3_600.0

    def _ttl_of(self, e: "_Entry", args: tuple = ()) -> float:
        """이 항목에 적용할 ttl — 실패 모양의 값이면 짧게."""
        ttl = self.ttl_for(args)
        if getattr(e, "failed", False):
            return min(ttl, max(FAILED_TTL, ttl * 0.25))
        return ttl

    # ── 키 ────────────────────────────────────────────────────────────────
    def key(self, args: tuple, kwargs: dict) -> str:
        return f"{self._prefix()}{args!r}|{sorted(kwargs.items())!r}"

    def _prefix(self) -> str:
        tag = f"#v{self.version}" if self.version else ""
        return f"{self.module}.{self.name}{tag}|"

    # ── 받기 ──────────────────────────────────────────────────────────────
    def _fetch(self, key: str, args, kwargs, e: _Entry) -> None:
        """새로 받아 넣습니다. 잠금은 부르는 쪽이 잡고 있습니다."""
        try:
            value = self.fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            e.error = _scrub(f"{type(exc).__name__}: {exc}")
            if not e.ok:
                raise
            return
        # 새 값이 '빈 값' 이면 좋은 직전 값을 덮지 않습니다
        if e.ok and self.keep is not None:
            try:
                if not self.keep(value):
                    e.error = "새로 받은 값이 비어 직전 값을 유지"
                    e.at = time.time() - self.ttl_for(args) * 0.75   # 곧 다시 시도
                    return
            except Exception:  # noqa: BLE001
                pass
        # keep 을 따로 정하지 않은 받기에는 **공통 규칙**을 씁니다: 새로 받은
        # 값이 실패 모양이고 직전 값은 멀쩡하면, 직전 값을 그대로 둡니다.
        # 받은 시각(e.at)은 건드리지 않습니다 — 화면의 '받은 시각' 이 거짓말을
        # 하면 안 됩니다. 다시 받는 간격은 retry_at 이 맡습니다.
        # 직전 값이 KEEP_GOOD_MAX 보다 오래됐으면 그만 붙들고 실패를 보여줍니다.
        failed = False
        if self.keep is None and AUTO_KEEP:
            failed = _looks_failed(value)
            if (failed and e.ok and time.time() - e.at < KEEP_GOOD_MAX
                    and not _looks_failed(e.value)):
                e.error = _scrub("새로 받기 실패 — 직전 값을 유지: "
                                 + (_first_error(value) or "받은 것이 비어 있음"))[:300]
                e.retry_at = time.time() + self._backoff(args)
                return
        e.value, e.at, e.ok, e.error = value, time.time(), True, ""
        # 실패 모양의 값은 받아 두되 **금방 다시** 받습니다 (ttl 을 다 채우지 않음)
        e.failed = failed
        if self.disk and not failed:
            _disk_save(key, e.at, value)

    def _backoff(self, args: tuple = ()) -> float:
        """실패한 뒤 다시 받기까지 쉬는 시간 — ttl 의 4분의 1, 1~15분 사이."""
        return max(RETRY_AFTER, min(self.ttl_for(args) * 0.25, 900.0))

    def _window(self) -> float:
        """이 나이까지는 저장된 값을 (묵었어도) 바로 줍니다."""
        return max(self.stale, HARD_STALE)

    def _background(self, key: str, args, kwargs, e: _Entry) -> None:
        ttl = self._ttl_of(e, args)

        def run():
            try:
                with e.lock:
                    if time.time() - e.at >= ttl:          # 그사이 누가 받았으면 건너뜀
                        before = e.at
                        self._fetch(key, args, kwargs, e)
                        if e.at == before:                 # 못 받았음 — 잠시 쉼
                            e.retry_at = max(e.retry_at, time.time() + RETRY_AFTER)
            except Exception:  # noqa: BLE001
                e.retry_at = time.time() + RETRY_AFTER
            finally:
                e.refreshing = False
                e.done.set()
        e.refreshing = True
        e.done.clear()
        e.wait_until = time.time() + self.wait_fresh
        try:
            _pool.submit(run)
        except RuntimeError:            # 인터프리터 종료 중
            e.refreshing = False
            e.done.set()

    def __call__(self, *args, **kwargs):
        return self._get(args, kwargs, self.wait_fresh)

    def quick(self, *args, **kwargs):
        """__call__ 과 같되 묵은 값이면 새 값을 **기다리지 않고** 바로 줌 (뒤에서 새로 받음).

        11/13 17:56 "탭을 눌렀을 때 한 번에 안 넘어감" — 시세가 60초를 넘기면 탭을 누를
        때마다 새 시세를 최대 3초 기다려서, 그동안 화면이 안 바뀐 것처럼 보였습니다.
        처음 열 때만 기다리고(옛 시세가 안 보이게), 탭을 옮길 때는 이쪽을 씁니다."""
        return self._get(args, kwargs, 0.0)

    def _get(self, args, kwargs, wait_fresh: float):
        key = self.key(args, kwargs)
        e = _entry(key)
        window = self._window()
        if not e.ok and self.disk:
            got = _disk_load(key, window)
            if got is not None:
                with e.lock:
                    if not e.ok:
                        e.value, e.at, e.ok = got[0], got[1], True
                        e.failed = _looks_failed(got[0])   # 옛 실패 사본은 금방 다시 받음
        ttl = self._ttl_of(e, args)
        if e.ok:
            age = time.time() - e.at
            if age < ttl:
                _note_served(self.name, e.at)
                return e.value
            if age < window:
                if not e.refreshing and time.time() >= e.retry_at:
                    self._background(key, args, kwargs, e)
                # 새 값을 잠깐 기다려 봅니다 (wait_fresh). 그 안에 오면 새 값을,
                # 안 오면 묵은 값을 줍니다. 한 번의 새로 받기에는 정해진
                # 시각(wait_until)까지만 — 여러 곳에서 불러도 합쳐서 그만큼.
                if wait_fresh and e.refreshing:
                    left = e.wait_until - time.time()
                    if left > 0:
                        e.done.wait(left)
                    if time.time() - e.at < ttl:
                        _note_served(self.name, e.at)
                        return e.value
                _note_stale(self.name, time.time() - e.at)
                _note_served(self.name, e.at)
                return e.value
        # 값이 없거나 너무 오래됨 — 기다려서 받습니다 (같은 키는 한 번만)
        with e.lock:
            if not e.ok or time.time() - e.at >= window:
                self._fetch(key, args, kwargs, e)
            _note_served(self.name, e.at)
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
                        e.failed = _looks_failed(got[0])   # 옛 실패 사본은 금방 다시 받음
        if e.ok and time.time() - e.at < window:
            age = time.time() - e.at
            if age >= self._ttl_of(e, args):
                if not e.refreshing and time.time() >= e.retry_at:
                    self._background(key, args, kwargs, e)
                _note_stale(self.name, age)
            _note_served(self.name, e.at)
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
        prefix = self._prefix()
        with _store_lock:
            for k in [k for k in _store if k.startswith(prefix)]:
                if DISK:
                    try:
                        os.remove(_disk_path(k))
                    except OSError:
                        pass
                del _store[k]


def cached(ttl, *, stale: float | None = None,
           keep: Callable[[object], bool] | None = None,
           disk: bool = True, wait_fresh: float = 0.0,
           version: int = 0) -> Callable[[Callable], Cached]:
    """데코레이터.

    ttl    이 시간 안이면 저장된 값을 그대로 (초)
    stale  이 시간 안이면 저장된 값을 바로 주고 뒤에서 새로 받음.
           기본은 ttl 의 6배 (시세 60초 → 6분, 일봉 1시간 → 6시간)
    keep   새 값을 받아들일지. False 면 직전 값을 유지 (빈 결과가
           좋은 값을 덮지 않게)
    disk   임시 폴더에 사본을 남길지
    version 값의 모양·계산이 바뀌면 올립니다 — 옛 저장값을 쓰지 않게
    """
    def deco(fn: Callable) -> Cached:
        if stale is not None:
            window = stale
        else:
            window = 6 * 3_600 if callable(ttl) else ttl * 6
        return Cached(fn, ttl, window, keep, disk, wait_fresh, version)
    return deco


# ── 스냅샷 — 아침 수집기가 만들고 앱이 읽습니다 ─────────────────────────────
#
# 화면을 여는 순간에 받으면 느립니다. 그래서 정해진 시각에 수집기
# (tools/collect.py, GitHub Actions)가 모든 화면의 데이터를 미리 받아
# 한 파일로 묶어 두고, 앱은 값이 하나도 없을 때(서버가 막 깨어났을 때)
# 그 파일을 읽어 채웁니다. 읽은 값은 '받은 시각' 이 그대로라 묵은 값으로
# 취급되어, 바로 보여주고 뒤에서 새로 받는 흐름을 탑니다.

SEED_FORMAT = 1


def export_seed(secrets: tuple[str, ...] = (), skip=None) -> tuple[bytes, dict]:
    """지금 메모리에 있는 값들을 한 덩어리로. (gzip 바이트, 보고서)

    secrets 에 든 글자가 **하나라도** 들어 있는 항목은 뺍니다. 실패 메시지에
    요청 주소(인증키 포함)가 섞여 들어갈 수 있고, 이 파일은 공개 저장소에
    올라가기 때문입니다.

    skip(값) 이 참이면 그 항목도 뺍니다 — 수집기는 '받기에 실패한 결과' 를
    여기서 걸러, 앱이 실패를 물려받지 않고 직접 받게 합니다.
    """
    import gzip  # noqa: PLC0415

    needles = [x.encode("utf-8") for x in secrets if x and len(x) >= 6]
    items: dict[str, bytes] = {}
    report = {"kept": 0, "dropped_secret": [], "dropped_error": [],
              "dropped_failed": [], "bytes": 0}
    with _store_lock:
        snapshot = [(k, e.at, e.value) for k, e in _store.items() if e.ok]
    for key, at, value in snapshot:
        try:
            if skip is not None and skip(value):
                report["dropped_failed"].append(key.split("|")[0])
                continue
        except Exception:  # noqa: BLE001 - 판단을 못 하면 넣지 않습니다
            report["dropped_failed"].append(key.split("|")[0])
            continue
        try:
            blob = pickle.dumps((key, at, _deps_of(value), value),
                                protocol=4)        # 4 = 파이썬 3.4 이상 어디서나
        except Exception as exc:  # noqa: BLE001
            report["dropped_error"].append(f"{key[:60]} — {type(exc).__name__}")
            continue
        if any(n in blob for n in needles) or any(n in key.encode("utf-8")
                                                  for n in needles):
            report["dropped_secret"].append(key.split("|")[0])
            continue
        items[key] = blob
        report["kept"] += 1
    raw = pickle.dumps({"format": SEED_FORMAT, "made": time.time(),
                        "items": items}, protocol=4)
    out = gzip.compress(raw, compresslevel=6)
    report["bytes"] = len(out)
    return out, report


def import_seed(blob: bytes, max_age: float = 3 * 86_400) -> dict:
    """스냅샷을 메모리에 채웁니다. 이미 값이 있는 키는 건드리지 않습니다.

    항목마다 '그 값을 만든 코드 파일' 이 지금과 같은지 확인하고, 다르면
    그 항목만 버립니다 (파일 사본과 같은 규칙).
    """
    import gzip  # noqa: PLC0415

    report = {"loaded": 0, "skipped_old": 0, "skipped_code": 0,
              "skipped_have": 0, "made": 0.0}
    try:
        pack = pickle.loads(gzip.decompress(blob))
        if pack.get("format") != SEED_FORMAT:
            return report
    except Exception:  # noqa: BLE001
        return report
    report["made"] = float(pack.get("made") or 0.0)
    now = time.time()
    for key, item in (pack.get("items") or {}).items():
        try:
            saved_key, at, deps, value = pickle.loads(item)
        except Exception:  # noqa: BLE001 - 클래스가 사라졌거나 모양이 다름
            report["skipped_code"] += 1
            continue
        if saved_key != key or now - at > max_age:
            report["skipped_old"] += 1
            continue
        if any(_module_hash(name) != digest for name, digest in deps.items()):
            report["skipped_code"] += 1
            continue
        e = _entry(key)
        with e.lock:
            if e.ok:
                report["skipped_have"] += 1
                continue
            e.value, e.at, e.ok = value, at, True
        report["loaded"] += 1
    return report


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


#: 스냅샷 읽기 — 프로세스마다 한 번만 시도합니다.
_seed_lock = threading.Lock()
_seed_state: dict = {"tried": False, "report": None}


def load_seed_from(url: str, timeout: float = 4.0) -> dict | None:
    """url 의 스냅샷을 받아 채웁니다. 이미 시도했으면 지난 결과를 돌려줍니다.

    서버가 막 깨어난 첫 화면에서 한 번 부릅니다. 실패해도 조용히 넘어갑니다
    (스냅샷은 있으면 좋은 것이고, 없으면 예전처럼 직접 받습니다).
    """
    if not url:
        return None
    with _seed_lock:
        if _seed_state["tried"]:
            return _seed_state["report"]
        _seed_state["tried"] = True
        t0 = time.time()
        try:
            import urllib.request  # noqa: PLC0415
            req = urllib.request.Request(url, headers={"User-Agent": "dash-seed/1"})
            try:
                import config as _cfg  # noqa: PLC0415 - 비공개 저장소(11/13)
                _cfg.add_github_auth(req)
            except Exception:  # noqa: BLE001
                pass
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                blob = resp.read()
            report = import_seed(blob)
            report["bytes"] = len(blob)
        except Exception as exc:  # noqa: BLE001
            report = {"loaded": 0, "error": f"{type(exc).__name__}: {exc}"[:160]}
        report["sec"] = round(time.time() - t0, 2)
        _seed_state["report"] = report
        return report

