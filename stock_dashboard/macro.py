"""
매크로 지표 판정 — FRED 계열을 '표시값 + 신호' 로 바꿉니다.

설계 원칙 두 개:

**1. 뉴스 피드를 만들지 않습니다.**
일반 매크로 뉴스 피드는 받은편지함 범람 문제를 그대로 되풀이합니다. 그래서
티커 쪽과 같은 규율을 씁니다 — **지표가 임계값을 건드렸을 때만** 신호를 내고,
**그 신호에만** 뉴스를 붙입니다. 평소에는 숫자만 조용히 보여줍니다.

**2. 레벨이 아니라 변화를 봅니다.**
지수 계열(산업생산·PPI)은 기준연도가 바뀌어서 레벨이 비교 불가능합니다.
금리도 "4.1%가 높은가"는 맥락 없이는 답할 수 없습니다. 그래서 임계값은
전부 변화·부호전환·평균대비로 정의합니다. 유일한 예외는 연준 목표치(2%)처럼
**외부에 고정 기준이 있는 경우**입니다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from config import MacroSeries

#: 일별 계열을 '발표 지연' 으로 보기 시작하는 날수 (주말 2일 + 휴일 + 공개 1일).
DAILY_STALE_DAYS = 5
from sources.fred import Series


@dataclass
class Reading:
    """한 지표의 현재 상태 — 화면에 그대로 띄울 수 있는 형태."""

    spec: MacroSeries
    value: float | None = None            # mode 에 따른 표시값
    observed_at: dt.date | None = None
    lag_days: int | None = None

    #: 직전 관측치 대비 변화 (표시값 기준)
    delta: float | None = None
    #: 임계값 비교에 쓴 변화 (change_periods 반영)
    window_delta: float | None = None
    #: 최근 mean_periods 평균 (pct_vs_mean 을 쓰는 계열만)
    mean_value: float | None = None
    #: 스파크라인용 최근 시계열
    history: list[tuple[str, float]] = field(default_factory=list)

    #: 발표가 통상 주기보다 늦은가
    stale: bool = False
    #: 데이터 자체의 문제 (결측 과다 등)
    warning: str = ""
    #: 수집 실패 사유
    error: str = ""

    #: 다음 발표일 (FRED 발표 일정에서 — 있을 때만)
    next_release: dt.date | None = None
    #: 같은 것의 **지금 시세** (spec.live_symbol 이 있을 때만) 와 직전 종가 대비
    live_value: float | None = None
    live_change: float | None = None
    #: 화면을 그리는 날 (시점 문구 계산용 — 테스트에서 고정)
    today: dt.date | None = None

    @property
    def ok(self) -> bool:
        return self.error == "" and self.value is not None

    @property
    def value_label(self) -> str:
        if self.value is None:
            return "—"
        spec = self.spec
        text = f"{self.value:,.{spec.decimals}f}"
        if spec.mode == "yoy":
            return f"{'+' if self.value > 0 else ''}{text}%"
        if spec.mode == "diff":
            sign = "+" if self.value > 0 else ""
            return f"{sign}{text}{spec.unit}"
        return f"{text}{spec.unit}" if spec.unit else text

    @property
    def delta_label(self) -> str:
        if self.delta is None:
            return ""
        unit = "%p" if self.spec.mode == "yoy" or self.spec.unit == "%" else ""
        return f"{'+' if self.delta > 0 else ''}{self.delta:,.{self.spec.decimals}f}{unit}"

    @property
    def period_label(self) -> str:
        """이 값이 **언제 것인가** — '9월분' · '11/01 주간' · '11/09 종가'.

        전에는 'N일 전' 이라고 적었습니다. 월간 통계에서 그 숫자는 '우리가
        늦게 받았다' 가 아니라 **통계의 기준 달이 그만큼 전** 이라는 뜻인데
        (FRED 는 9월 CPI 를 9월 1일자로 적습니다 → 11월 12일에 '72일 전'),
        화면에서는 데이터가 묵은 것처럼 읽혔습니다 (2026-11-12).
        """
        d = self.observed_at
        if d is None:
            return "—"
        today = self.today or dt.date.today()
        year = "" if d.year == today.year else f"{d.year}년 "
        if self.spec.period_days >= 28:
            return f"{year}{d.month}월분"
        if self.spec.period_days >= 7:
            return f"{year}{d.month}/{d.day:02d} 주간"
        return f"{year}{d.month}/{d.day:02d} 종가"

    @property
    def cadence_label(self) -> str:
        """얼마나 자주 새 값이 나오는가 — 다음 발표일을 알면 그 날짜."""
        today = self.today or dt.date.today()
        nxt = self.next_release
        if nxt is not None and nxt >= today:
            if nxt == today:
                return "오늘 발표"
            return f"다음 발표 {nxt.month}/{nxt.day:02d}"
        if self.spec.period_days >= 28:
            return "월 1회 발표"
        if self.spec.period_days >= 7:
            return "주 1회 발표"
        return "다음 영업일 공개"

    @property
    def live_label(self) -> str:
        """'지금 4.25%' — 지금 시세가 붙어 있을 때만."""
        if self.live_value is None:
            return ""
        unit = self.spec.unit or ""
        return f"지금 {self.live_value:,.{self.spec.decimals}f}{unit}"

    @property
    def observed_label(self) -> str:
        if self.observed_at is None:
            return "—"
        if self.spec.period_days >= 28:
            return self.observed_at.strftime("%Y-%m")
        return self.observed_at.isoformat()


def _display_value(spec: MacroSeries, series: Series) -> float | None:
    if spec.mode == "yoy":
        return series.yoy_pct()
    if spec.mode == "diff":
        return series.change(1)
    latest = series.latest
    return latest.value if latest else None


def _display_history(spec: MacroSeries, series: Series,
                     points: int = 24) -> list[tuple[str, float]]:
    if spec.mode == "yoy":
        return series.yoy_series(points)
    if spec.mode == "diff":
        out: list[tuple[str, float]] = []
        obs = series.observations[-(points + 1):]
        for prev, cur in zip(obs, obs[1:]):
            out.append((cur.date.isoformat(), cur.value - prev.value))
        return out
    return [(o.date.isoformat(), o.value) for o in series.observations[-points:]]


def _window_delta(spec: MacroSeries, series: Series,
                  history: list[tuple[str, float]]) -> float | None:
    """임계값 비교용 변화. mode 가 yoy/diff 면 표시값 기준으로 계산합니다."""
    periods = spec.change_periods
    if spec.mode == "level":
        return series.change(periods)
    if len(history) <= periods:
        return None
    return history[-1][1] - history[-1 - periods][1]


def build_reading(spec: MacroSeries, series: Series | None,
                  error: str = "", today: dt.date | None = None) -> Reading:
    """계열 하나를 Reading 으로 만듭니다."""
    today = today or dt.date.today()

    if series is None:
        return Reading(spec=spec, error=error or "수집되지 않았습니다.")

    value = _display_value(spec, series)
    gap_note = ""
    if value is None and spec.mode == "yoy" and series.latest is not None:
        # 최신 달의 '1년 전 같은 달' 이 비어 있는 경우 (2025-10 CPI 처럼
        # 발표되지 않은 달). 13개월 전과 비교해 전년대비라고 적지 않고,
        # **계산할 수 있는 가장 최근 달**을 그 달 이름으로 보여줍니다.
        usable = series.yoy_series(24)
        if usable:
            last_day = dt.date.fromisoformat(usable[-1][0])
            cut = [o for o in series.observations if o.date <= last_day]
            latest_day = series.latest.date
            gap_note = (
                f"{latest_day:%Y-%m} 은 1년 전 같은 달({latest_day.year - 1}-"
                f"{latest_day.month:02d}) 값이 발표되지 않아 전년대비를 계산할 수 "
                f"없습니다 — 계산되는 가장 최근 달({last_day:%Y-%m})을 보여줍니다.")
            series = Series(series_id=series.series_id, observations=cut,
                            missing_count=series.missing_count)
            value = usable[-1][1]
    if value is None:
        detail = (
            "전년 동기 관측치가 없어 전년대비를 계산할 수 없습니다"
            if spec.mode == "yoy" else "관측치가 부족합니다"
        )
        return Reading(spec=spec, error=f"{detail} (수집 {len(series.observations)}건).")

    history = _display_history(spec, series)
    latest = series.latest
    observed = latest.date if latest else None
    lag = (today - observed).days if observed else None

    reading = Reading(
        spec=spec,
        value=value,
        observed_at=observed,
        lag_days=lag,
        today=today,
        history=history,
        window_delta=_window_delta(spec, series, history),
    )
    if gap_note:
        reading.warning = gap_note
    if len(history) >= 2:
        reading.delta = history[-1][1] - history[-2][1]
    if spec.pct_vs_mean is not None:
        # 최신값을 제외한 평균 — 급증이 자기 기준선을 끌어올리지 않게
        reading.mean_value = series.mean_prior(spec.mean_periods)

    # 발표 지연 — 통상 주기의 N 배를 넘으면 표시합니다
    from config import MACRO_STALE_MULTIPLIER
    # 일별 계열은 '다음 영업일 공개' 라 주말·휴일이 끼면 3~4일은 정상입니다.
    # 2026-11-12 실제 화면: 11/9 종가(3일 전)에 '발표 지연' 이 붙었습니다 —
    # 주기 1일 × 2.5 = 2.5일을 넘겼다는 이유였습니다. 일별은 5일부터 봅니다.
    limit = spec.period_days * MACRO_STALE_MULTIPLIER
    if spec.period_days < 7:
        limit = max(limit, DAILY_STALE_DAYS)
    if lag is not None and lag > limit:
        reading.stale = True

    if series.missing_count > len(series.observations) and not gap_note:
        reading.warning = (
            f"결측({series.missing_count}건)이 유효 관측치보다 많습니다 — "
            "계열 선택을 다시 보십시오."
        )
    return reading


def build_readings(specs: list[MacroSeries], series_map: dict[str, Series],
                   errors: dict[str, str],
                   today: dt.date | None = None) -> list[Reading]:
    return [
        build_reading(spec, series_map.get(spec.series_id),
                      errors.get(spec.series_id, ""), today)
        for spec in specs
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 임계값 판정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Trigger:
    """임계값을 건드린 사실 하나."""

    reading: Reading
    rule: str                   # level_above / level_below / change / sign_flip / yoy_flip / vs_mean
    severity: int               # 3 지금 / 2 이번 주 / 1 참고
    title: str
    detail: str


def _period_label(period_days: int, count: int) -> str:
    """관측 주기에서 '20일 / 4주 / 6개월' 같은 표현을 만듭니다.

    period_days 는 그 계열의 통상 발표 주기입니다(일간 1, 주간 7, 월간 30).
    """
    if period_days <= 1:
        return f"{count}일"
    if period_days <= 10:
        return f"{count}주"
    if period_days <= 100:
        return f"{count}개월"
    return f"{count}기"


def _sign(value: float) -> int:
    return 0 if value == 0 else (1 if value > 0 else -1)


def _flip(history: list[tuple[str, float]]) -> tuple[int, int] | None:
    """(현재 부호, 직전 비(非)영 부호). 부호가 바뀌지 않았으면 None.

    직전 **관측치**가 아니라 직전 **비영 관측치**와 비교해야 합니다. FRED 의
    스프레드 계열은 소수 둘째 자리까지라 `0.00` 이 자주 나옵니다
    (T10Y2Y 가 -0.01 → 0.00 → 0.01 로 움직이는 식). 직전 관측치만 보면
    0.00 을 만나는 순간 부호 비교가 무효가 되어 **전환을 통째로 놓칩니다.**
    역전 해소는 가장 중요한 신호 중 하나이므로 그걸 놓치면 안 됩니다.
    """
    if not history:
        return None
    now = _sign(history[-1][1])
    if now == 0:
        return None
    for _date, value in reversed(history[:-1]):
        before = _sign(value)
        if before == 0:
            continue
        return (now, before) if now != before else None
    return None


def _last_nonzero(history: list[tuple[str, float]]) -> float:
    for _date, value in reversed(history[:-1]):
        if value != 0:
            return value
    return 0.0


def evaluate(reading: Reading) -> list[Trigger]:
    """한 지표의 임계값을 검사합니다. 여러 규칙이 동시에 걸릴 수 있습니다."""
    if not reading.ok:
        return []

    spec = reading.spec
    value = reading.value
    out: list[Trigger] = []
    name = spec.name

    if spec.level_above is not None and value > spec.level_above:
        out.append(Trigger(
            reading, "level_above", 2,
            f"{name} {reading.value_label} — 기준({spec.level_above:g}) 상회",
            f"기준 {spec.level_above:g} 을 {value - spec.level_above:+.2f} 넘었습니다.",
        ))

    if spec.level_below is not None and value < spec.level_below:
        out.append(Trigger(
            reading, "level_below", 2,
            f"{name} {reading.value_label} — 기준({spec.level_below:g}) 하회",
            f"기준 {spec.level_below:g} 을 {value - spec.level_below:+.2f} 밑돌았습니다.",
        ))

    if spec.change_abs is not None and reading.window_delta is not None:
        if abs(reading.window_delta) >= spec.change_abs:
            unit = "%p" if spec.unit in ("%", "%p") or spec.mode == "yoy" else spec.unit
            periods = spec.change_periods
            out.append(Trigger(
                reading, "change", 2,
                f"{name} {reading.window_delta:+.{spec.decimals}f}{unit} "
                f"({periods}개 관측 구간)",
                f"임계값 ±{spec.change_abs:g}{unit} 을 넘는 변화입니다. "
                f"현재 {reading.value_label}.",
            ))

    if spec.sign_flip:
        flipped = _flip(reading.history)
        if flipped:
            now, _before = flipped
            direction = "플러스로 전환 (역전 해소)" if now > 0 else "마이너스로 전환 (역전 진입)"
            prior = _last_nonzero(reading.history)
            out.append(Trigger(
                reading, "sign_flip", 3,
                f"{name} 부호 전환 — {direction}",
                f"직전 비영 관측 {prior:+.2f} → 현재 {reading.history[-1][1]:+.2f}.",
            ))

    if spec.yoy_flip:
        flipped = _flip(reading.history)
        if flipped:
            now, _before = flipped
            direction = "플러스 전환 (증가세 회복)" if now > 0 else "마이너스 전환 (감소세 진입)"
            prior = _last_nonzero(reading.history)
            out.append(Trigger(
                reading, "yoy_flip", 3,
                f"{name} 전년대비 {direction}",
                f"직전 {prior:+.1f}% → 현재 {reading.history[-1][1]:+.1f}%. "
                "사이클 전환 가능성을 확인해야 합니다.",
            ))

    if (spec.pct_vs_mean is not None and reading.mean_value
            and reading.mean_value != 0):
        gap = (value / reading.mean_value - 1.0) * 100.0
        if abs(gap) >= spec.pct_vs_mean:
            # 단위를 계열 주기에서 가져옵니다. '주' 로 못박아 두면 일간
            # 계열(하이일드 스프레드)에서 "20주 평균" 이라고 틀리게 나옵니다.
            span = _period_label(spec.period_days, spec.mean_periods)
            # 소수점은 계열이 정한 자리수를 씁니다. ,.0f 로 박아 두면
            # 스프레드 3.2 → 4.05 가 "3 → 4" 로 보여 변화가 사라집니다.
            dec = spec.decimals
            out.append(Trigger(
                reading, "vs_mean", 2,
                f"{name} {span} 평균 대비 {gap:+.1f}%",
                f"평균 {reading.mean_value:,.{dec}f} → 현재 {value:,.{dec}f}"
                f"{(' ' + spec.unit) if spec.unit else ''}. "
                f"임계값 ±{spec.pct_vs_mean:g}%.",
            ))

    return out


def evaluate_all(readings: list[Reading]) -> list[Trigger]:
    """심각도 높은 순, 같으면 그룹 순서대로."""
    from config import MACRO_GROUPS

    group_order = {g[0]: i for i, g in enumerate(MACRO_GROUPS)}
    triggers: list[Trigger] = []
    for reading in readings:
        triggers.extend(evaluate(reading))
    triggers.sort(key=lambda t: (-t.severity,
                                 group_order.get(t.reading.spec.group, 99)))
    return triggers


def news_queries(triggers: list[Trigger], *, limit: int = 3,
                 ) -> list[tuple[str, str, str]]:
    """뉴스를 붙일 지표만 — (키, 질의, 소스).

    `news_query` 가 비어 있는 계열은 제외합니다. 모든 지표에 뉴스를 붙이면
    티커 쪽에서 고쳤던 범람 문제가 매크로 탭에서 되살아납니다.
    """
    seen: dict[str, tuple[str, str, str]] = {}
    for trig in triggers:
        spec = trig.reading.spec
        if not spec.news_query or spec.key in seen:
            continue
        seen[spec.key] = (spec.key, spec.news_query, "naver")
        if len(seen) >= limit:
            break
    return list(seen.values())


def prompt_for(trigger: Trigger) -> str:
    """Claude 에 붙여넣을 질문. 티커 신호와 같은 방식입니다."""
    r = trigger.reading
    spec = r.spec
    lines = [
        f"{spec.name}({spec.series_id})이 {r.value_label} 입니다 "
        f"(관측 {r.observed_label}, {r.lag_days}일 전 데이터).",
        f"감지 사유: {trigger.detail}",
        "",
        "확인하고 싶은 것:",
    ]
    if spec.group == "semi":
        lines += [
            "1. 이 전환이 메모리 사이클의 어느 국면과 맞물리는지 — "
            "제 지표체계 레이어 1(가격)·2(재고)·4(수요)와 교차검증해 주십시오.",
            "2. MU·삼성전자·SK하이닉스의 최근 공시·어닝콜 발언과 방향이 일치하는지.",
            "3. 이 계열은 미국 생산 기준이라 한국 2사의 실제 출하와 어긋날 수 있습니다 — "
            "그 한계를 감안하면 어디까지 읽어도 되는지.",
        ]
    elif spec.group == "rates":
        lines += [
            "1. 제 관심 종목 중 금리 민감도가 높은 것(O 리츠, SCHD, QQQ)에 "
            "어떤 경로로 영향이 가는지.",
            "2. 이 변화가 일시적 수급인지 정책 기대의 전환인지 구분할 근거.",
            "3. 과거 비슷한 구간에서 실제로 무엇이 달랐는지.",
        ]
    elif spec.group == "inflation":
        lines += [
            "1. 이 수치가 연준의 정책 경로 기대를 어떻게 바꾸는지.",
            "2. 세부 항목 중 추세를 끌고 있는 항목이 무엇인지 (주거비·서비스 등).",
            "3. 제 관심 종목에 직접 영향이 가는 경로가 있는지, 없으면 없다고 해주십시오.",
        ]
    else:
        lines += [
            "1. 이 지표가 경기 국면에 대해 실제로 말해주는 것과, 과대해석하기 쉬운 부분.",
            "2. 같은 방향을 가리키는 다른 지표가 있는지 (확인), 반대인 지표가 있는지 (경계).",
            "3. 제 관심 종목 중 이 지표와 실제로 연결되는 것이 있는지.",
        ]
    lines += [
        "",
        "매수/매도 추천이나 목표주가는 필요 없습니다. 판단 재료만 정리해 주십시오.",
    ]
    return "\n".join(lines)


def attach_context(readings: list[Reading], *, next_releases: dict | None = None,
                   live_quotes: dict | None = None) -> list[Reading]:
    """다음 발표일과 지금 시세를 붙입니다 (있는 것만). 읽기 자체는 바꾸지 않습니다.

    next_releases: {FRED 발표 번호: 날짜}
    live_quotes:   {야후 심볼: (지금 값, 직전 종가 대비 변화 또는 None)}
    임계값 판정은 여전히 FRED 값(value)으로 합니다 — 장중 시세로 신호가
    켜졌다 꺼졌다 하지 않게.
    """
    next_releases = next_releases or {}
    live_quotes = live_quotes or {}
    for r in readings:
        rid = getattr(r.spec, "release_id", None)
        if rid is not None and rid in next_releases:
            r.next_release = next_releases[rid]
        sym = getattr(r.spec, "live_symbol", "")
        if sym and sym in live_quotes and live_quotes[sym] is not None:
            value, change = live_quotes[sym]
            if value is not None:
                r.live_value, r.live_change = float(value), change
    return readings


#: 이 날수보다 오래된 월간 관측은 '갱신이 멈춘 계열' 로 봅니다.
KR_DEAD_DAYS = 150


def kr_macro_row(label: str, kind: str, series: Series | None, error: str = "",
                 today: dt.date | None = None) -> tuple[str, str, str]:
    """한국 지표 한 줄 → (이름, 값, 메모). 화면은 세 칸을 그대로 찍습니다.

    값의 모양은 kind 가 정합니다 (config.KR_MACRO_KIND). 전년비는 '13번째
    앞 관측' 이 아니라 **1년 전 같은 달**과 비교합니다 — 중간에 빠진 달이
    있으면 13번째 앞이 1년 전이 아닙니다 (미국 CPI 에서 겪은 문제).
    """
    today = today or dt.date.today()
    obs = series.observations if series is not None else []
    if not obs:
        why = (error or "최근 3년 관측치가 없습니다").strip()
        return label, "—", (why[:60] + " — FRED 에서 중단된 계열일 수 있습니다"
                            if "관측" in why else why[:90])
    last = obs[-1]
    base = series.year_ago_base(last.date)
    when = (f"{last.date.month}월분" if last.date.year == today.year
            else f"{last.date.year}년 {last.date.month}월분")
    notes = [when]
    if (today - last.date).days > KR_DEAD_DAYS:
        notes.append("갱신이 멈춘 계열로 보입니다")
    if base is None:
        notes.append("1년 전 값이 없어 전년비 생략")

    if kind == "rate":
        value = f"{last.value:,.2f}%"
        if base is not None:
            value += f"  (1년 전보다 {last.value - base.value:+.2f}%p)"
    elif kind == "usd":
        value = f"{last.value / 1e8:,.1f}억 달러"
        if base is not None and base.value:
            value += f"  (전년동월비 {(last.value / base.value - 1) * 100:+.1f}%)"
    elif kind == "pct":
        value = f"전년동월비 {last.value:+.1f}%"
        notes = [n for n in notes if "전년비 생략" not in n]
        if base is not None:
            notes.append(f"1년 전 {base.value:+.1f}%")
    elif kind == "level":
        value = f"{last.value:,.1f}"
        if base is not None:
            value += f"  (1년 전보다 {last.value - base.value:+.1f})"
        notes.append("100 이 장기 추세")
    elif kind == "balance":
        value = f"{last.value:+.1f}"
        if base is not None:
            value += f"  (1년 전보다 {last.value - base.value:+.1f})"
        notes.append("0 이 중립 · 긍정−부정 응답")
    else:                                    # index
        if base is not None and base.value:
            value = f"전년동월비 {(last.value / base.value - 1) * 100:+.1f}%"
            notes.insert(1, f"지수 {last.value:,.1f}")
        else:
            value = f"지수 {last.value:,.1f}"
    return label, value, " · ".join(notes)
