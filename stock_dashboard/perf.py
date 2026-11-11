"""속도 — 무엇이 느린지 재고, 서로 기다릴 필요 없는 일은 동시에 돌립니다.

2026-11-11 "사이트 불러오는 게 너무 느리다". 요약 화면 하나가 시세 ·
미국 공시 · 국내 공시 · 국내 재고 추세 · 미국 재고 추세 · 섹터 온도 ·
매크로를 **한 줄로 줄 세워** 받고 있었습니다. 각각은 서로를 기다릴
이유가 없습니다. 총 시간이 '합' 이 아니라 '가장 느린 하나' 가 되도록
동시에 시작합니다.

스트림릿 없이 테스트할 수 있게, 스트림릿 의존은 initializer 로만
받습니다 (app.py 가 스크립트 실행 문맥을 스레드에 붙이는 함수를 넘김).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as _wait
from dataclasses import dataclass, field
from typing import Callable

#: 이보다 빠른 항목은 '캐시에서 바로 나옴' 으로 보고 목록에서 뺍니다
CACHE_HIT_SEC = 0.05


@dataclass
class Timing:
    name: str
    seconds: float
    error: str = ""

    @property
    def cached(self) -> bool:
        return self.seconds < CACHE_HIT_SEC and not self.error


@dataclass
class RunLog:
    """한 번의 화면 그리기 동안의 측정 기록."""

    started: float = field(default_factory=time.perf_counter)
    items: list[Timing] = field(default_factory=list)
    parallel_wall: float = 0.0     # 동시에 돌린 묶음의 실제 경과 시간

    def add(self, name: str, seconds: float, error: str = "") -> None:
        self.items.append(Timing(name, seconds, error))

    def measure(self, name: str, fn: Callable, *args, **kwargs):
        """fn 을 실행하고 걸린 시간을 기록합니다. 예외는 그대로 올립니다."""
        t0 = time.perf_counter()
        err = ""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            err = type(exc).__name__
            raise
        finally:
            self.add(name, time.perf_counter() - t0, err)

    def total(self) -> float:
        return time.perf_counter() - self.started

    def slowest(self, n: int = 3) -> list[Timing]:
        real = [t for t in self.items if not t.cached]
        return sorted(real, key=lambda t: -t.seconds)[:n]

    def summary_line(self) -> str:
        """화면 맨 아래 한 줄. 모두 캐시면 그 사실만 적습니다."""
        total = self.total()
        slow = self.slowest()
        if not slow:
            return f"이번 화면 {total:.1f}초 · 모두 저장해 둔 값에서 바로 나왔습니다"
        parts = ", ".join(
            f"{t.name} {t.seconds:.1f}초" + ("+ (뒤에서 계속)" if t.error == "뒤에서 계속" else "")
            for t in slow)
        line = f"이번 화면 {total:.1f}초 · 오래 걸린 것: {parts}"
        if self.parallel_wall and len([t for t in self.items if not t.cached]) > 1:
            serial = sum(t.seconds for t in self.items if not t.cached)
            if serial > self.parallel_wall + 0.5:
                line += (f" (동시에 받아 {serial:.1f}초 → "
                         f"{self.parallel_wall:.1f}초)")
        return line


def run_parallel(calls: dict[str, Callable[[], object]], log: RunLog | None = None,
                 initializer: Callable[[], None] | None = None,
                 max_workers: int = 12,
                 budget: float | None = None) -> dict[str, object]:
    """이름 → 인자 없는 함수. 동시에 실행하고 {이름: 결과} 를 돌려줍니다.

    실패한 항목은 결과에서 빠집니다 — 호출한 쪽이 평소처럼 다시 부르면
    같은 오류를 **원래 경로에서** 보게 됩니다 (화면별 오류 표시가 그대로
    작동). 이 함수는 '미리 데워 두기' 일 뿐, 실패를 삼키거나 바꾸지
    않습니다.
    """
    if not calls:
        return {}
    out: dict[str, object] = {}
    timings: dict[str, Timing] = {}

    def one(name: str, fn: Callable[[], object]):
        t0 = time.perf_counter()
        try:
            val = fn()
            timings[name] = Timing(name, time.perf_counter() - t0)
            return name, val, None
        except Exception as exc:  # noqa: BLE001 - 원래 경로에서 다시 드러납니다
            timings[name] = Timing(name, time.perf_counter() - t0,
                                   type(exc).__name__)
            return name, None, exc

    def safe_init() -> None:
        # initializer 가 예외를 내면 스레드 풀 전체가 BrokenThreadPool 이
        # 됩니다 (테스트로 확인). 문맥 붙이기는 '있으면 좋은 것' 이라 삼킵니다.
        if initializer is None:
            return
        try:
            initializer()
        except Exception:  # noqa: BLE001
            pass

    w0 = time.perf_counter()
    workers = max(1, min(max_workers, len(calls)))
    pool = ThreadPoolExecutor(max_workers=workers, initializer=safe_init)
    futures = {pool.submit(one, n, f): n for n, f in calls.items()}
    # budget 이 있으면 **그만큼만** 기다립니다. 못 끝낸 것은 스레드에서 계속
    # 돌아 캐시에 들어가고, 화면은 먼저 그립니다 (느린 하나가 전체를 붙잡지
    # 않게). 없으면 예전처럼 전부 기다립니다.
    done, late = _wait(futures, timeout=budget)
    for fut in done:
        name, val, exc = fut.result()
        if exc is None:
            out[name] = val
    pool.shutdown(wait=False)
    wall = time.perf_counter() - w0
    if log is not None:
        for name in calls:
            if name in timings:
                log.items.append(timings[name])
        for fut in late:
            log.items.append(Timing(futures[fut], wall, "뒤에서 계속"))
        log.parallel_wall = max(log.parallel_wall, wall)
    return out
