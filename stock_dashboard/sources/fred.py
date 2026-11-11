"""
FRED (세인트루이스 연준 경제데이터) — **인증키 불필요**.

FRED 는 API 키를 요구하지만, 그래프의 CSV 내보내기 경로는 키 없이 열립니다:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10

응답은 두 컬럼 CSV 입니다 (헤더 이름은 계열에 따라 바뀝니다):

    observation_date,DGS10
    2026-10-01,4.12
    2026-10-02,.

**함정 셋:**

1. 결측은 빈 칸이 아니라 **`.`(점 한 글자)** 로 옵니다. float() 에 그대로 넣으면
   터집니다. 특히 PPI 세부 계열은 최근 몇 달이 통째로 `.` 인 경우가 흔합니다.
2. 헤더의 두 번째 컬럼명이 계열 ID 와 다를 수 있습니다(파라미터를 붙이면
   `DGS10_20260101` 처럼 변형됩니다). 그래서 **이름이 아니라 위치**로 읽습니다.
3. 지수 계열(산업생산·PPI)은 **기준연도가 바뀝니다** — 같은 IPG3344S 가
   "2017=100" 으로도 "2022=100" 으로도 나옵니다. 그래서 레벨은 쓰지 않고
   **전년 동기 대비 변화율**만 씁니다. 변화율은 기준연도와 무관합니다.

이 모듈은 숫자만 돌려줍니다. 임계값 판정은 macro.py 가 합니다.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

#: 키 없이 쓰는 경로. 그래프 화면이 쓰는 CSV 로, 요청마다 생성됩니다.
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

#: 공식 API. **호스트가 다릅니다**(api.stlouisfed.org). 무료 키가 필요하지만
#: fredgraph.csv 가 막히거나 느릴 때의 대체 경로입니다 — 실제로 배포 환경에서
#: fredgraph.csv 가 전 계열 실패한 적이 있어 넣었습니다.
#: 키는 fred.stlouisfed.org/docs/api/api_key.html 에서 즉시 발급됩니다.
API_URL = "https://api.stlouisfed.org/fred/series/observations"


def api_key() -> str:
    return (os.environ.get("FRED_API_KEY") or "").strip()


def key_fingerprint() -> str:
    """캐시 무효화용 지문. DART 와 같은 이유입니다 — 키를 넣는 순간
    실패한 캐시가 저절로 버려져야 합니다."""
    import hashlib

    key = api_key()
    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else ""
#: fredgraph.csv 는 요청마다 CSV 를 만들어 내려 주므로 정적 파일보다
#: 느립니다. 15초에서 늘렸습니다 — Streamlit Cloud 에서 전 계열이
#: HTTPSConnectionPool 오류로 실패했고, 타임아웃이 유력한 후보입니다.
TIMEOUT = 30

#: 연결 단계 실패는 한 번 더 시도합니다. HTTP 오류(404 등)는 재시도해도
#: 같은 결과라 재시도하지 않습니다.
RETRIES = 1
RETRY_WAIT = 1.5
#: FRED 는 CSV 엔드포인트의 공식 제한을 밝히지 않습니다. 키가 필요한 공식
#: API 는 분당 120건(= 2건/초)이므로, 그보다 넉넉한 6.7건/초로 둡니다.
#: 0.3초(3.3건/초)였을 때는 13개 계열에 대기만 4초가 들어갔습니다.
MIN_INTERVAL = 0.15
MISSING = "."

#: 동시 요청 수. 응답이 계열당 수십~수백 KB 라 메모리 부담이 적습니다.
MAX_WORKERS = 4

_last_request_at = 0.0
_throttle_lock = threading.Lock()


class FredError(RuntimeError):
    """FRED 조회 실패."""


@dataclass(frozen=True)
class Observation:
    date: dt.date
    value: float


@dataclass
class Series:
    """한 계열의 관측치 — 오래된 것 → 최신 순서."""

    series_id: str
    observations: list[Observation]

    #: 응답에 있었지만 `.` 이라 버린 개수. 데이터 품질 표시용입니다.
    missing_count: int = 0

    @property
    def latest(self) -> Observation | None:
        return self.observations[-1] if self.observations else None

    @property
    def previous(self) -> Observation | None:
        return self.observations[-2] if len(self.observations) >= 2 else None

    def at_or_before(self, target: dt.date) -> Observation | None:
        """target 이전(포함)의 가장 최신 관측치. 월간 계열의 전년 동월 비교용."""
        found = None
        for obs in self.observations:
            if obs.date <= target:
                found = obs
            else:
                break
        return found

    @property
    def lag_days(self) -> int | None:
        """최신 관측일이 며칠 전인가. 발표 지연을 보여주는 데 씁니다.

        매크로 통계는 가격과 달리 2~6주 지연됩니다. 이 숫자를 화면에 띄워야
        '어제 지표' 로 착각하지 않습니다.
        """
        if self.latest is None:
            return None
        return (dt.date.today() - self.latest.date).days

    def change(self, periods: int = 1) -> float | None:
        """periods 관측치 전 대비 절대 변화."""
        if len(self.observations) <= periods:
            return None
        return self.observations[-1].value - self.observations[-1 - periods].value

    def pct_change(self, periods: int = 1) -> float | None:
        """periods 관측치 전 대비 변화율(%)."""
        if len(self.observations) <= periods:
            return None
        base = self.observations[-1 - periods].value
        if base == 0:
            return None
        return (self.observations[-1].value / base - 1.0) * 100.0

    def yoy_pct(self) -> float | None:
        """전년 동기 대비 변화율(%). 지수 계열의 기준연도 문제를 피합니다.

        달력으로 1년 전 날짜를 찾고, 그 이전의 가장 최신 관측치와 비교합니다.
        월간이든 주간이든 일간이든 같은 로직으로 동작합니다.
        """
        if self.latest is None:
            return None
        try:
            a_year_ago = self.latest.date.replace(year=self.latest.date.year - 1)
        except ValueError:                      # 2월 29일
            a_year_ago = self.latest.date.replace(
                year=self.latest.date.year - 1, day=28)
        base = self.at_or_before(a_year_ago)
        if base is None or base.value == 0:
            return None
        return (self.latest.value / base.value - 1.0) * 100.0

    def yoy_series(self, points: int = 24) -> list[tuple[str, float]]:
        """최근 points 개 관측치의 전년 대비 변화율 시계열 — 방향 전환 판정용."""
        out: list[tuple[str, float]] = []
        for obs in self.observations[-points:]:
            try:
                prior_date = obs.date.replace(year=obs.date.year - 1)
            except ValueError:
                prior_date = obs.date.replace(year=obs.date.year - 1, day=28)
            base = self.at_or_before(prior_date)
            if base is None or base.value == 0:
                continue
            out.append((obs.date.isoformat(), (obs.value / base.value - 1.0) * 100.0))
        return out

    def mean(self, periods: int) -> float | None:
        """최근 periods 개 평균."""
        window = self.observations[-periods:]
        if len(window) < periods:
            return None
        return sum(o.value for o in window) / len(window)

    def mean_prior(self, periods: int) -> float | None:
        """최신 관측치를 **제외한** 직전 periods 개 평균.

        '4주 평균 대비 급증' 을 판정할 때 최신값이 자기 기준선에 들어가면
        급증이 스스로 희석됩니다 — 주간 청구건수가 25만→30만으로 튀어도
        평균이 함께 올라가 변화율이 작게 나옵니다. 그래서 기준선은
        최신값을 빼고 만듭니다.
        """
        window = self.observations[-(periods + 1):-1]
        if len(window) < periods:
            return None
        return sum(o.value for o in window) / len(window)


def _throttle() -> None:
    """요청 시작 시점을 MIN_INTERVAL 간격으로 벌립니다 (스레드 안전)."""
    global _last_request_at
    with _throttle_lock:
        gap = time.monotonic() - _last_request_at
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_request_at = time.monotonic()


def parse_csv(text: str, series_id: str) -> Series:
    """FRED CSV 본문을 파싱합니다. 네트워크와 분리해 테스트하기 위해 공개합니다."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise FredError(f"{series_id}: 빈 응답입니다.") from None

    if len(header) < 2:
        raise FredError(
            f"{series_id}: 컬럼이 {len(header)}개뿐입니다 — CSV 가 아닐 수 있습니다 "
            f"(앞 60자: {text[:60]!r})."
        )

    observations: list[Observation] = []
    missing = 0
    for row in reader:
        if len(row) < 2:
            continue
        raw_date, raw_value = row[0].strip(), row[1].strip()
        if raw_value == MISSING or raw_value == "":
            missing += 1
            continue
        try:
            date = dt.date.fromisoformat(raw_date)
            value = float(raw_value)
        except ValueError:
            missing += 1
            continue
        observations.append(Observation(date=date, value=value))

    if not observations:
        raise FredError(
            f"{series_id}: 유효한 관측치가 없습니다 (결측 {missing}건). "
            "계열 ID 가 맞는지 확인하십시오."
        )

    observations.sort(key=lambda o: o.date)
    return Series(series_id=series_id, observations=observations,
                  missing_count=missing)


def fetch_series(series_id: str, *, start: dt.date | None = None) -> Series:
    """한 계열을 받아옵니다. 키가 필요 없습니다."""
    _throttle()
    params = {"id": series_id}
    if start is not None:
        params["cosd"] = start.isoformat()

    headers = {"User-Agent": "stock-dashboard/1.0 (personal research)",
               "Accept": "text/csv"}

    # 키가 있으면 공식 API 를 먼저 씁니다. 호스트가 달라서, fredgraph.csv
    # 가 막힌 환경에서도 열려 있을 수 있습니다.
    key = api_key()
    if key:
        try:
            return _fetch_via_api(series_id, key, start)
        except FredError:
            # API 가 안 되면 키 없는 경로로 내려갑니다 — 둘 다 실패해야
            # 진짜 실패입니다.
            pass

    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(CSV_URL, params=params, timeout=TIMEOUT,
                                headers=headers)
            resp.raise_for_status()
            return parse_csv(resp.text, series_id)
        except requests.HTTPError as exc:
            # HTTP 응답이 왔다는 뜻이므로 재시도해도 같습니다.
            status = exc.response.status_code if exc.response is not None else "?"
            if status == 404:
                raise FredError(
                    f"{series_id}: 그런 계열이 없습니다 (HTTP 404). "
                    "fred.stlouisfed.org 에서 ID 를 확인하십시오."
                ) from exc
            raise FredError(
                f"{series_id}: FRED 요청 실패 (HTTP {status})."
            ) from exc
        except requests.RequestException as exc:
            # 연결·타임아웃 단계 실패. 한 번 더 해 봅니다.
            last = exc
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT)

    raise FredError(
        f"{series_id}: FRED 연결 실패 ({RETRIES + 1}회 시도) — "
        f"{type(last).__name__}: {last}"
    ) from last


def _fetch_via_api(series_id: str, key: str,
                   start: dt.date | None) -> Series:
    """공식 API(JSON)로 받아옵니다. 키가 있을 때만 호출됩니다."""
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
    }
    if start is not None:
        params["observation_start"] = start.isoformat()
    try:
        resp = requests.get(
            API_URL, params=params, timeout=TIMEOUT,
            headers={"User-Agent": "stock-dashboard/1.0 (personal research)"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FredError(
            f"{series_id}: FRED API 실패 — {type(exc).__name__}: {exc}"
        ) from exc

    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise FredError(f"{series_id}: FRED API 응답에 observations 가 없습니다.")

    obs: list[Observation] = []
    for row in rows:
        raw = str(row.get("value", "")).strip()
        if not raw or raw == MISSING:        # 결측은 '.' 입니다 (CSV 와 같음)
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        try:
            when = dt.date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        obs.append(Observation(when, value))

    if not obs:
        raise FredError(f"{series_id}: FRED API 가 관측치를 주지 않았습니다.")
    obs.sort(key=lambda o: o.date)
    return Series(series_id=series_id, observations=obs)


def fetch_many(series_ids: list[str], *, years: int = 4,
               ) -> tuple[dict[str, Series], dict[str, str]]:
    """여러 계열을 받아옵니다. 실패는 계열별로 격리됩니다.

    years 를 제한하는 이유: DGS10 은 1962년부터라 전부 받으면 1MB 가 넘습니다.
    밴드·전년대비만 쓰므로 4년이면 충분합니다.
    """
    start = dt.date.today().replace(year=dt.date.today().year - years)
    out: dict[str, Series] = {}
    errors: dict[str, str] = {}
    ids = list(dict.fromkeys(series_ids))
    if not ids:
        return out, errors

    def one(sid: str) -> tuple[str, "Series | None", str | None]:
        try:
            return sid, fetch_series(sid, start=start), None
        except FredError as exc:
            return sid, None, str(exc)
        except Exception as exc:  # noqa: BLE001
            return sid, None, f"예상치 못한 오류: {type(exc).__name__}: {exc}"

    # 요약 화면이 이 13개 계열을 기다립니다. 순차로는 대기만 2초,
    # 왕복까지 더하면 6~10초였습니다.
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(ids))) as pool:
        for sid, series, err in pool.map(one, ids):
            if err is None and series is not None:
                out[sid] = series
            else:
                errors[sid] = err or "알 수 없는 오류"
    return out, errors
