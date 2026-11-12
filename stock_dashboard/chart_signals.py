"""차트 조건 — 일봉 기준 일곱 가지: 일목 양운 · 이동평균 · CCI · MACD ·
스토캐스틱 슬로우 · 볼린저 밴드 · −DI.

2026-11-11 요청으로 만들었고, 같은 날 사용자가 조건을 이렇게 정했습니다:

  1. DMI −DI      : −DI 가 30 아래로 가거나 10 아래로 갈 때 (거래량이 느는 자리)
  2. CCI(13, 시그널 9) : 과매도 진입 · 과매도 구간 · 과매도에서 벗어나려는 중,
                    또는 과매수 근처로 갈 때
  3. MACD         : 같은 방식
  4. 스토캐스틱 슬로우 : 같은 방식
  (일목 양운은 처음 요청 그대로)

**'상태' 로 봅니다.** 처음에는 지표마다 참/거짓 하나였는데, 요청은
'들어가는 중 · 안에 있음 · 나오려는 중' 을 구분하는 것이었습니다. 그래서
지표마다 지금 상태를 이름으로 돌려주고(없으면 빈 문자열), 과매도 쪽인지
과매수 쪽인지를 같이 적습니다.

**이 파일이 정한 것 (요청에 숫자가 없던 부분).**
  - '최근' = 3봉 이내 (돌파가 오늘 하루에만 잡히면 하루 차이로 놓칩니다)
  - CCI: 과매도 −100, 과매수 +100, '과매수 근처' = +80 이상에서 오르는 중.
    시그널은 CCI 의 9일 단순이동평균
  - 스토캐스틱 슬로우 (12, 5, 5 — 사용자 지정): 과매도 20, 과매수 80,
    근처 = 70 이상 상승 중 → 같은 날 과매도 30 · 과매수 80 으로 지정받음
  - MACD (12, 26, 9) 에는 과매도 기준선이 없어 **시그널선 교차**에 같은 틀을
    씌웠습니다: 하향 돌파(진입) · 시그널 아래(구간) · 아래에서 좁혀짐(벗어나려는
    중) · 상향 돌파(벗어남) · 위에서 좁혀짐(과매수 쪽 — 상승 둔화)
  - −DI(14): 30 또는 10 을 **위에서 아래로** 지난 것. 거래량은 조건에 넣지
    않고 옆에 배수(오늘 ÷ 직전 20일 평균)로 적습니다 — 1.3배 이상이면 '동반'
  - '벗어나려는 중' = 구간 안에서 값이 전일보다 올랐거나 시그널 위에 있음

**나중에 더한 두 가지 (2026-11-11 "기술적 지표 추가").** 이미 있던 것은
추세(일목·MACD) · 모멘텀(CCI·스토캐스틱) · 방향(−DI)이었고, 빠진 종류가
둘이었습니다:
  - 이동평균 배열 — 가격이 20·60·120일선 어디에 있는가 (추세의 '위치')
  - 볼린저 밴드 — 밴드 안 위치(%B)와 밴드폭 수축 (변동성)
RSI 는 넣지 않았습니다. CCI·스토캐스틱과 같은 것(최근 가격의 상대 위치)을
재서 세 번째 모멘텀 지표는 같은 말을 한 번 더 할 뿐입니다.

**무엇을 주장하지 않는가.** 지표는 과거 가격을 다시 정리한 것이고 방향을
예측하지 않습니다. 이 목록은 '읽어볼 종목' 이지 매수·매도 신호가 아닙니다.

순수 파이썬입니다 (pandas 없음). 계산은 tests/chart_signals_test.py 가
pandas 로 만든 독립 구현과 숫자를 대조합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── 기준값 ───────────────────────────────────────────────────────────────────
TENKAN, KIJUN, SENKOU_B = 9, 26, 52
#: 선행 이동. 당일 포함 26일 = 25봉 앞. (트레이딩뷰·국내 HTS 와 같은 자리)
DISPLACEMENT = 25
CCI_WINDOW, CCI_SIGNAL = 13, 9
CCI_OVERSOLD, CCI_OVERBOUGHT, CCI_NEAR = -100.0, 100.0, 80.0
#: 2026-11-12 추가 — '탈출' 은 가운데 선을 넘기 전까지만, '근접' 은 양쪽 모두.
CCI_MID, CCI_NEAR_LOW = 0.0, -80.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
#: 사용자 지정 (2026-11-11): 스토캐스틱 슬로우 12, 5, 5
STOCH_N, STOCH_K, STOCH_D = 12, 5, 5
#: 사용자 지정 (2026-11-11): 과매수 80 · 과매도 30
STOCH_OVERSOLD, STOCH_OVERBOUGHT, STOCH_NEAR = 30.0, 80.0, 70.0
STOCH_MID, STOCH_NEAR_LOW = 50.0, 40.0
#: 이동평균 (단순). 정배열 = 종가 > 20 > 60 > 120
MA_SHORT, MA_MID, MA_LONG = 20, 60, 120
#: 볼린저 밴드 (20, 2σ). '근접' = %B 0.1 이하 / 0.9 이상.
#: '수축' = 밴드폭이 최근 120일 중 좁은 쪽 20% 안
BB_WINDOW, BB_K, BB_NEAR = 20, 2.0, 0.1
BB_SQUEEZE_LOOKBACK, BB_SQUEEZE_PCT = 120, 20.0
DMI_WINDOW = 14
MDI_LEVELS = (30.0, 10.0)
#: '최근' 의 범위 (봉). 돌파·진입을 이 안에서 찾습니다.
RECENT = 3
#: 거래량 '동반' 기준 — 오늘 거래량 ÷ 직전 20일 평균.
VOL_WINDOW, VOL_UP = 20, 1.3
#: 지표를 모두 계산하는 데 필요한 최소 일봉 수.
MIN_BARS = 120

#: (키, 짧은 이름, 기준 설명)
CONDITIONS = (
    ("cloud", "일목 양운", f"앞 구름(오늘 계산 · {DISPLACEMENT}봉 앞): 선행스팬1 > 선행스팬2"),
    ("ma", "이동평균", f"{MA_SHORT}·{MA_MID}·{MA_LONG}일 — 정배열 · 역배열 · "
                    f"{MA_SHORT}일선 돌파 (최근 {RECENT}봉)"),
    ("cci", "CCI", f"CCI({CCI_WINDOW}) · 시그널 {CCI_SIGNAL} — 과매도 {CCI_OVERSOLD:g} 이하 · "
                   f"과매수 +{CCI_OVERBOUGHT:g} 이상 (근접 · 진입 · 구간 · 탈출 시도 · 탈출)"),
    ("macd", "MACD", "시그널 교차 — 하향 돌파 · 아래 · 좁혀짐 · 상향 돌파 "
                     "(과매도·과매수를 가르는 데는 쓰지 않음)"),
    ("stoch", "스토캐스틱", f"슬로우({STOCH_N},{STOCH_K},{STOCH_D}) — 과매도 {STOCH_OVERSOLD:g} 이하 · "
                        f"과매수 {STOCH_OVERBOUGHT:g} 이상 (근접 · 진입 · 구간 · 탈출 시도 · 탈출)"),
    ("bb", "볼린저", f"밴드({BB_WINDOW}, {BB_K:g}σ) — 하단 이탈·근접, 상단 돌파·근접, 밴드 수축"),
    ("dmi", "−DI 하향", f"−DI({DMI_WINDOW}) 가 30 또는 10 을 아래로 (최근 {RECENT}봉)"),
)
CONDITION_KEYS = tuple(k for k, _n, _r in CONDITIONS)
#: 과매도 쪽 / 과매수 쪽을 가르는 지표 — **수준(값의 높낮이)으로 재는 것만**.
#: 2026-11-12 "과매도 과매수가 제대로 분류 안 된다": MACD 의 '시그널 위·아래' 를
#: 쪽으로 세는 바람에, CCI −126 · 스토캐스틱 17 인 종목이 MACD 하나 때문에
#: '과매수 쪽' 목록에 올라왔습니다. MACD 는 방향을 재는 지표라 과매도·과매수의
#: 기준선이 없습니다 — 상태 이름은 그대로 두되 쪽에서는 뺍니다.
SIDED = ("cci", "stoch", "bb")
SIDE_NAMES = {"os": "과매도", "ob": "과매수", "mixed": "엇갈림", "": ""}
#: 기준선을 이미 나온 뒤의 상태 — 쪽의 근거로는 약합니다 (ChartRow.side 참고).
EXITED = ("과매도 탈출", "과매수 이탈")
SIDES = (("", "전체"), ("os", "과매도 쪽"), ("ob", "과매수 쪽"))


# ── 기본 도구 ────────────────────────────────────────────────────────────────

def ema(values: list[float], span: int) -> list[float]:
    """지수이동평균. 첫 값으로 시작합니다 (pandas ewm(adjust=False) 와 같음)."""
    if not values:
        return []
    k = 2.0 / (span + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def sma_series(values: list, window: int) -> list:
    """단순이동평균. 창 안에 None 이 있으면 그 자리는 None.

    누적합으로 한 번에 계산합니다 — 창마다 다시 더하면 종목 70개 × 지표
    여럿에서 이 함수 하나가 계산 시간의 70% 를 썼습니다.
    """
    out: list = [None] * len(values)
    acc = 0.0
    run = 0                      # 연속으로 None 이 아닌 값의 개수
    for i, v in enumerate(values):
        if v is None:
            acc, run = 0.0, 0
            continue
        acc += v
        run += 1
        if run > window:
            acc -= values[i - window]
        if run >= window:
            out[i] = acc / window
    return out


def crossed_down(series: list, level: float, within: int = RECENT) -> bool:
    """최근 within 봉 안에 level 을 위에서 아래로 지났고, 지금도 그 아래인가."""
    if len(series) < 2 or series[-1] is None or series[-1] > level:
        return False
    for back in range(within):
        i = len(series) - 1 - back
        if i < 1 or series[i] is None or series[i - 1] is None:
            break
        if series[i - 1] > level >= series[i]:
            return True
    return False


def crossed_up(series: list, level: float, within: int = RECENT) -> bool:
    """최근 within 봉 안에 level 을 아래에서 위로 지났고, 지금도 그 위인가."""
    if len(series) < 2 or series[-1] is None or series[-1] <= level:
        return False
    for back in range(within):
        i = len(series) - 1 - back
        if i < 1 or series[i] is None or series[i - 1] is None:
            break
        if series[i - 1] <= level < series[i]:
            return True
    return False


def zone_state(vals: list, sig: list, low: float, high: float,
               near: float, mid: float | None = None,
               near_low: float | None = None) -> tuple[str, str]:
    """진동 지표의 지금 상태 → (이름, 쪽). 쪽은 'os'(과매도) / 'ob'(과매수) / ''.

    양쪽이 같은 틀입니다 (low·high 는 기준선, mid 는 가운데 선):

      과매도 쪽                              과매수 쪽
      근접     near_low 이하에서 내리는 중     near 이상에서 오르는 중
      진입     최근 3봉 안에 low 아래로        최근 3봉 안에 high 위로
      구간     low 아래에서 머무름             high 위에서 머무름
      탈출 시도  low 아래에서 전일보다 오름     high 위에서 전일보다 내림
      탈출     최근 3봉 안에 low 위로 나왔고    최근 3봉 안에 high 아래로 나왔고
              아직 mid 아래                   아직 mid 위

    2026-11-12 고친 것 (실제 화면에서 본 오분류):
      · '탈출' 에 끝이 없었습니다. 3봉 전에 −100 을 넘었으면 지금 CCI 가 +64 여도
        '과매도 탈출' 이었습니다. 가운데 선을 넘으면 더는 그쪽 상태가 아닙니다.
      · '탈출 시도' 를 '전일보다 올랐거나 **시그널 위**' 로 봤습니다. 시그널은
        늦게 따라오므로, 계속 내리는 중에도 시그널 위일 수 있습니다. 값이
        실제로 돌아섰을 때(전일 대비)만 셉니다.
      · 과매수 쪽에는 근접·진입·구간만 있었습니다. 같은 틀로 맞췄습니다.
    sig 는 화면 표시용으로만 받습니다 (판정에는 쓰지 않음).
    """
    if len(vals) < 2 or vals[-1] is None or vals[-2] is None:
        return "", ""
    cur, prev = vals[-1], vals[-2]
    mid = (low + high) / 2.0 if mid is None else mid
    if cur <= low:
        if cur > prev:
            return "과매도 탈출 시도", "os"
        if crossed_down(vals, low):
            return "과매도 진입", "os"
        return "과매도 구간", "os"
    if cur >= high:
        if cur < prev:
            return "과매수 이탈 시도", "ob"
        if crossed_up(vals, high - 1e-12):
            return "과매수 진입", "ob"
        return "과매수 구간", "ob"
    if cur < mid and crossed_up(vals, low):
        return "과매도 탈출", "os"
    if cur > mid and crossed_down(vals, high - 1e-12):
        return "과매수 이탈", "ob"
    if cur >= near and cur > prev:
        return "과매수 근접", "ob"
    if near_low is not None and cur <= near_low and cur < prev:
        return "과매도 근접", "os"
    return "", ""


def macd_state(hist: list[float]) -> tuple[str, str]:
    """MACD 의 지금 상태 — 시그널선 교차 (히스토그램의 부호). 쪽은 늘 ''.

    MACD 에는 과매도·과매수 기준선이 없습니다. '시그널 아래' 는 방향이지
    수준이 아니라서 쪽(os/ob)으로 세지 않습니다 (SIDED 주석 참고).
    """
    if len(hist) < 2:
        return "", ""
    h, hp = hist[-1], hist[-2]
    if h == 0 and hp == 0:      # 가격이 안 움직인 종목 (거래정지) — 상태 없음
        return "", ""
    if h <= 0:
        if h > hp:
            return "시그널 아래 · 좁혀짐", ""
        if crossed_down(hist, 0.0):
            return "시그널 하향 돌파", ""
        return "시그널 아래", ""
    if crossed_up(hist, 0.0):
        return "시그널 상향 돌파", ""
    if h < hp:
        return "시그널 위 · 좁혀짐", ""
    return "", ""


def stoch_slow(highs: list[float], lows: list[float], closes: list[float],
               n: int = STOCH_N, k: int = STOCH_K, d: int = STOCH_D
               ) -> tuple[list, list]:
    """스토캐스틱 슬로우 (%K, %D).

    패스트 %K = (종가 − n일 최저) ÷ (n일 최고 − n일 최저) × 100
    슬로우 %K = 패스트 %K 의 k일 단순평균,  슬로우 %D = 슬로우 %K 의 d일 단순평균
    """
    fast: list = []
    for i in range(len(closes)):
        if i + 1 < n:
            fast.append(None)
            continue
        hh, ll = max(highs[i + 1 - n:i + 1]), min(lows[i + 1 - n:i + 1])
        fast.append(None if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0)
    slow_k = sma_series(fast, k)
    return slow_k, sma_series(slow_k, d)


def ma_state(closes: list[float]) -> tuple[str, tuple]:
    """이동평균 배열 → (상태, (20일선, 60일선, 120일선)).

    돌파가 먼저입니다 — 최근에 20일선을 지났으면 배열보다 그 사실이 새
    정보입니다. 그다음 정배열(종가 > 20 > 60 > 120) / 역배열.
    """
    ms, mm, ml = (sma_series(closes, w) for w in (MA_SHORT, MA_MID, MA_LONG))
    last = (ms[-1], mm[-1], ml[-1])
    if ms[-1] is None:
        return "", last
    gap = [None if m is None else c - m for c, m in zip(closes, ms)]
    if crossed_up(gap, 0.0):
        return f"{MA_SHORT}일선 상향 돌파", last
    if crossed_down(gap, -1e-12):
        return f"{MA_SHORT}일선 하향 돌파", last
    if None not in last:
        c = closes[-1]
        if c > last[0] > last[1] > last[2]:
            return "정배열", last
        if c < last[0] < last[1] < last[2]:
            return "역배열", last
    return "", last


def bollinger(closes: list[float]) -> tuple[float | None, float | None, str, str]:
    """볼린저 밴드 → (%B, 밴드폭 순위 %, 상태, 쪽).

    %B = (종가 − 하단) ÷ (상단 − 하단). 0 이 하단, 1 이 상단.
    밴드폭 = (상단 − 하단) ÷ 중심선. 순위는 최근 120일 밴드폭 중 지금보다
    좁았던 날의 비율(%) — 낮을수록 수축. 표준편차는 모집단 기준(÷N)입니다.
    """
    n = len(closes)
    if n < BB_WINDOW:
        return None, None, "", ""
    widths: list[float] = []
    pctb = None
    start = max(BB_WINDOW - 1, n - BB_SQUEEZE_LOOKBACK)
    for i in range(start, n):
        win = closes[i + 1 - BB_WINDOW:i + 1]
        mid = sum(win) / BB_WINDOW
        sd = (sum((x - mid) ** 2 for x in win) / BB_WINDOW) ** 0.5
        widths.append((2 * BB_K * sd / mid) if mid else 0.0)
        if i == n - 1:
            lo, hi = mid - BB_K * sd, mid + BB_K * sd
            pctb = None if hi == lo else (closes[i] - lo) / (hi - lo)
    if pctb is None:
        return None, None, "", ""
    rank = None
    if len(widths) >= 60:
        rank = sum(1 for w in widths[:-1] if w < widths[-1]) / (len(widths) - 1) * 100.0
    if pctb < 0:
        return pctb, rank, "하단 이탈", "os"
    if pctb > 1:
        return pctb, rank, "상단 돌파", "ob"
    if pctb <= BB_NEAR:
        return pctb, rank, "하단 근접", "os"
    if pctb >= 1 - BB_NEAR:
        return pctb, rank, "상단 근접", "ob"
    if rank is not None and rank <= BB_SQUEEZE_PCT:
        return pctb, rank, "밴드 수축", ""
    return pctb, rank, "", ""


def mdi_state(mdi: list) -> str:
    """−DI 가 10 또는 30 을 아래로 지났는가 (낮은 선 먼저)."""
    for level in sorted(MDI_LEVELS):
        if crossed_down(mdi, level):
            return f"{level:.0f} 하향 돌파"
    return ""


def volume_ratio(volumes: list | None) -> float | None:
    """오늘 거래량 ÷ 직전 20일 평균. 장중이면 오늘 값이 아직 작습니다."""
    if not volumes or len(volumes) < VOL_WINDOW + 1:
        return None
    base = [v for v in volumes[-VOL_WINDOW - 1:-1] if v is not None]
    if len(base) < VOL_WINDOW or sum(base) <= 0 or volumes[-1] is None:
        return None
    return volumes[-1] / (sum(base) / len(base))


def _midpoint(highs: list[float], lows: list[float], end: int, window: int) -> float | None:
    """end 봉까지(포함) window 개 봉의 (최고가 + 최저가) / 2."""
    start = end - window + 1
    if start < 0:
        return None
    return (max(highs[start:end + 1]) + min(lows[start:end + 1])) / 2.0


# ── 1. 일목균형표 ────────────────────────────────────────────────────────────

@dataclass
class Ichimoku:
    tenkan: float | None = None       # 전환선 (오늘)
    kijun: float | None = None        # 기준선 (오늘)
    span_a: float | None = None       # 오늘 자리의 선행스팬1
    span_b: float | None = None       # 오늘 자리의 선행스팬2
    #: **앞 구름** — 오늘 봉으로 계산해 25봉 앞에 그려지는 선행스팬 (구름의 맨 앞 끝).
    lead_a: float | None = None
    lead_b: float | None = None

    @property
    def bullish_cloud(self) -> bool | None:
        """양운인가 — **앞 구름**에서 선행스팬1 이 위면 양운, 아니면 음운.

        2026-11-12 사용자 정정: "앞자리 구름을 보는 거야. 선행스팬1 이 위에
        있으면 양운, 반대면 음운." 전에는 오늘 자리의 구름(25봉 전에 계산된
        값)으로 판정해서 HTS 에서 보는 것과 달랐습니다. 오늘 자리 구름은
        '가격이 구름 위/안/아래' 를 볼 때만 씁니다.
        """
        if self.lead_a is None or self.lead_b is None:
            return None
        return self.lead_a > self.lead_b

    @property
    def here_bullish(self) -> bool | None:
        """오늘 자리 구름의 색 (참고용 — 판정에는 쓰지 않습니다)."""
        if self.span_a is None or self.span_b is None:
            return None
        return self.span_a > self.span_b

    @property
    def twist(self) -> str:
        """오늘 자리와 앞 구름의 색이 다르면 그 사이에 구름이 꼬인 것입니다."""
        here, lead = self.here_bullish, self.bullish_cloud
        if here is None or lead is None or here == lead:
            return ""
        return "음운 → 양운 전환" if lead else "양운 → 음운 전환"

    def position(self, price: float | None) -> str:
        """가격이 구름 위 / 안 / 아래."""
        if price is None or self.span_a is None or self.span_b is None:
            return ""
        top, bot = max(self.span_a, self.span_b), min(self.span_a, self.span_b)
        if price > top:
            return "구름 위"
        if price < bot:
            return "구름 아래"
        return "구름 안"


def spans_at(highs: list[float], lows: list[float], idx: int) -> tuple[float | None, float | None]:
    """idx 봉 **자리에 그려지는** 선행스팬 (1, 2). idx − 25 봉에서 계산된 값."""
    src = idx - DISPLACEMENT
    if src < 0:
        return None, None
    t = _midpoint(highs, lows, src, TENKAN)
    k = _midpoint(highs, lows, src, KIJUN)
    b = _midpoint(highs, lows, src, SENKOU_B)
    a = (t + k) / 2.0 if t is not None and k is not None else None
    return a, b


def ichimoku(highs: list[float], lows: list[float]) -> Ichimoku:
    n = len(highs)
    if n == 0 or n != len(lows):
        return Ichimoku()
    last = n - 1
    a, b = spans_at(highs, lows, last)
    # 앞 구름의 맨 앞 끝 = 오늘 봉으로 계산한 선행스팬 (last + 25 자리에 그려짐)
    lead_a, lead_b = spans_at(highs, lows, last + DISPLACEMENT)
    return Ichimoku(tenkan=_midpoint(highs, lows, last, TENKAN),
                    kijun=_midpoint(highs, lows, last, KIJUN),
                    span_a=a, span_b=b, lead_a=lead_a, lead_b=lead_b)


# ── 2. CCI ───────────────────────────────────────────────────────────────────

def cci_series(highs: list[float], lows: list[float], closes: list[float],
               window: int = CCI_WINDOW) -> list[float | None]:
    """CCI = (TP − TP의 이동평균) ÷ (0.015 × 평균편차). TP = (고+저+종)/3."""
    tp = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
    out: list[float | None] = []
    for i in range(len(tp)):
        if i + 1 < window:
            out.append(None)
            continue
        win = tp[i + 1 - window:i + 1]
        mean = sum(win) / window
        md = sum(abs(x - mean) for x in win) / window
        out.append(None if md == 0 else (tp[i] - mean) / (0.015 * md))
    return out


# ── 3. MACD ──────────────────────────────────────────────────────────────────

def macd_series(closes: list[float]) -> tuple[list[float], list[float], list[float]]:
    """(MACD선, 시그널선, 히스토그램)."""
    fast, slow = ema(closes, MACD_FAST), ema(closes, MACD_SLOW)
    line = [f - s for f, s in zip(fast, slow)]
    signal = ema(line, MACD_SIGNAL)
    return line, signal, [m - s for m, s in zip(line, signal)]


def bars_since_cross(hist: list[float]) -> int | None:
    """히스토그램 부호가 지금 부호로 바뀐 지 몇 봉째인가 (오늘 바뀌었으면 0)."""
    if not hist:
        return None
    sign = hist[-1] > 0
    for back in range(1, len(hist)):
        if (hist[-1 - back] > 0) != sign:
            return back - 1
    return None


# ── 4. DMI ───────────────────────────────────────────────────────────────────

def dmi(highs: list[float], lows: list[float], closes: list[float],
        window: int = DMI_WINDOW) -> tuple[list[float | None], list[float | None],
                                           list[float | None]]:
    """(+DI, −DI, ADX) — 와일더 평활.

    와일더 평활: 처음 window 개는 합, 그 뒤는 직전값 − 직전값/window + 새 값.
    """
    n = len(closes)
    plus_dm, minus_dm, tr = [0.0], [0.0], [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                      abs(lows[i] - closes[i - 1])))

    def wilder(xs: list[float]) -> list[float | None]:
        out: list[float | None] = [None] * n
        if n <= window:
            return out
        acc = sum(xs[1:window + 1])
        out[window] = acc
        for i in range(window + 1, n):
            acc = acc - acc / window + xs[i]
            out[i] = acc
        return out

    s_tr, s_p, s_m = wilder(tr), wilder(plus_dm), wilder(minus_dm)
    pdi: list[float | None] = [None] * n
    mdi: list[float | None] = [None] * n
    dx: list[float | None] = [None] * n
    for i in range(n):
        if s_tr[i] is None or not s_tr[i]:
            continue
        pdi[i] = 100.0 * s_p[i] / s_tr[i]
        mdi[i] = 100.0 * s_m[i] / s_tr[i]
        tot = pdi[i] + mdi[i]
        dx[i] = 100.0 * abs(pdi[i] - mdi[i]) / tot if tot else 0.0
    adx: list[float | None] = [None] * n
    first = 2 * window - 1
    if n > first:
        seed = [d for d in dx[window:first + 1] if d is not None]
        if len(seed) == window:
            adx[first] = sum(seed) / window
            for i in range(first + 1, n):
                adx[i] = (adx[i - 1] * (window - 1) + dx[i]) / window
    return pdi, mdi, adx


# ── 종목 한 줄 ───────────────────────────────────────────────────────────────

@dataclass
class ChartRow:
    ticker: str
    name: str = ""
    bars: int = 0
    price: float | None = None
    #: 마지막 봉 날짜 'YYYY-MM-DD' ('' = 모름). 장중에 오늘 봉이 들어왔는지 가립니다.
    last_bar: str = ""
    ichi: Ichimoku = field(default_factory=Ichimoku)
    cci: float | None = None
    cci_signal: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    adx: float | None = None
    vol_ratio: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    bb_pctb: float | None = None
    bb_width_rank: float | None = None        # 낮을수록 밴드가 좁음 (%)
    #: 지표별 상태 이름 ("" = 해당 없음) 과 쪽 ("os" / "ob" / "")
    states: dict = field(default_factory=dict)
    sides: dict = field(default_factory=dict)
    error: str = ""
    #: 작은 차트용 (최근 N봉): 종가 · 그 자리의 선행스팬1 · 선행스팬2
    spark: list[float] = field(default_factory=list)
    spark_a: list[float | None] = field(default_factory=list)
    spark_b: list[float | None] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and self.bars >= MIN_BARS

    @property
    def disparity(self) -> float | None:
        """20일 이격도 = 종가 ÷ 20일선 × 100."""
        if self.price is None or not self.ma20:
            return None
        return self.price / self.ma20 * 100.0

    @property
    def side(self) -> str:
        """종목의 쪽 — 'os' 과매도 / 'ob' 과매수 / 'mixed' 엇갈림 / '' 어느 쪽도 아님.

        수준으로 재는 세 지표(CCI · 스토캐스틱 · 볼린저 %B)만 봅니다. 하나라도
        과매도 쪽 상태이고 과매수 쪽 상태가 없으면 과매도, 그 반대면 과매수,
        둘 다 있으면 엇갈림입니다.
        """
        votes = {k: self.sides.get(k) for k in SIDED if self.sides.get(k)}
        got = set(votes.values())
        if not got:
            return ""
        if len(got) > 1:
            return "mixed"
        side = got.pop()
        # 근거가 전부 '기준선을 나온 뒤'(탈출·이탈) 상태뿐이면, 다른 진동 지표가
        # 이미 가운데 선을 넘었는지 봅니다. 넘었으면 그쪽이 아닙니다 —
        # 스토캐스틱 45('과매도 탈출')인데 CCI 가 +59 인 종목이 과매도 목록에
        # 남던 것을 막습니다 (2026-11-12 실제 화면).
        if all(self.states.get(k) in EXITED for k in votes):
            for val, mid in ((self.cci, CCI_MID), (self.stoch_k, STOCH_MID)):
                if val is None:
                    continue
                if (side == "os" and val > mid) or (side == "ob" and val < mid):
                    return ""
        return side

    @property
    def side_votes(self) -> tuple[int, int]:
        """(과매도 쪽 지표 수, 과매수 쪽 지표 수) — 세 지표 가운데."""
        vals = [self.sides.get(k) for k in SIDED]
        return vals.count("os"), vals.count("ob")

    @property
    def vol_up(self) -> bool:
        return self.vol_ratio is not None and self.vol_ratio >= VOL_UP

    def flags(self) -> dict[str, bool | None]:
        """조건별 해당 여부. 계산 못 하면 None — False 와 구분합니다."""
        if not self.ok:
            return {k: None for k in CONDITION_KEYS}
        out: dict[str, bool | None] = {"cloud": self.ichi.bullish_cloud}
        have = {"cci": self.cci, "macd": self.macd_hist, "stoch": self.stoch_k,
                "dmi": self.minus_di, "ma": self.ma120, "bb": self.bb_pctb}
        for k in ("ma", "cci", "macd", "stoch", "bb", "dmi"):
            out[k] = None if have[k] is None else bool(self.states.get(k))
        return {k: out[k] for k in CONDITION_KEYS}

    @property
    def met(self) -> int:
        return sum(1 for v in self.flags().values() if v)

    @property
    def cloud_position(self) -> str:
        return self.ichi.position(self.price)

    def notes(self) -> dict[str, str]:
        """조건 옆에 붙일 한마디 — 상태 이름과 값."""
        out = {k: "" for k in CONDITION_KEYS}
        if not self.ok:
            return out
        out["cloud"] = self.cloud_position
        for k in ("ma", "cci", "macd", "stoch", "bb"):
            out[k] = self.states.get(k, "")
        st = self.states.get("dmi", "")
        if st:
            vol = ("" if self.vol_ratio is None else
                   f" · 거래량 {self.vol_ratio:.1f}배"
                   + (" 동반" if self.vol_up else ""))
            out["dmi"] = st + vol
        return out


SPARK_BARS = 120


def build_row(ticker: str, name: str, highs: list[float], lows: list[float],
              closes: list[float], volumes: list[float] | None = None) -> ChartRow:
    """일봉(고·저·종[·거래량], 오래된 것부터) → 한 줄."""
    n = min(len(highs), len(lows), len(closes))
    if n == 0:
        return ChartRow(ticker, name, error="일봉을 받지 못했습니다.")
    highs, lows, closes = highs[-n:], lows[-n:], closes[-n:]
    if any(h < l for h, l in zip(highs, lows)):
        return ChartRow(ticker, name, bars=n,
                        error="고가가 저가보다 낮은 봉이 있습니다 (데이터 이상).")
    if n < MIN_BARS:
        return ChartRow(ticker, name, bars=n, price=closes[-1],
                        error=f"일봉이 {n}개뿐입니다 (최소 {MIN_BARS}개).")
    cc = cci_series(highs, lows, closes)
    cc_sig = sma_series(cc, CCI_SIGNAL)
    line, sig, hist = macd_series(closes)
    sk, sd = stoch_slow(highs, lows, closes)
    pdi, mdi, adx = dmi(highs, lows, closes)
    m = min(SPARK_BARS, n)
    # 구름은 오늘을 지나 **앞 25봉**까지 그립니다 — 양운·음운을 가리는 것이
    # 그 앞 구름이라, 차트에서 눈으로 대조할 수 있어야 합니다.
    spans = [spans_at(highs, lows, i) for i in range(n - m, n + DISPLACEMENT)]

    states: dict[str, str] = {}
    sides: dict[str, str] = {}
    states["cci"], sides["cci"] = zone_state(
        cc, cc_sig, CCI_OVERSOLD, CCI_OVERBOUGHT, CCI_NEAR, CCI_MID, CCI_NEAR_LOW)
    states["macd"], sides["macd"] = macd_state(hist)
    states["stoch"], sides["stoch"] = zone_state(
        sk, sd, STOCH_OVERSOLD, STOCH_OVERBOUGHT, STOCH_NEAR, STOCH_MID, STOCH_NEAR_LOW)
    states["dmi"], sides["dmi"] = mdi_state(mdi), ""
    states["ma"], (m20, m60, m120) = ma_state(closes)
    sides["ma"] = ""
    pctb, bw_rank, states["bb"], sides["bb"] = bollinger(closes)
    return ChartRow(
        ticker=ticker, name=name, bars=n, price=closes[-1],
        ichi=ichimoku(highs, lows),
        cci=cc[-1], cci_signal=cc_sig[-1],
        macd=line[-1], macd_signal=sig[-1], macd_hist=hist[-1],
        stoch_k=sk[-1], stoch_d=sd[-1],
        plus_di=pdi[-1], minus_di=mdi[-1], adx=adx[-1],
        vol_ratio=volume_ratio(volumes[-n:] if volumes else None),
        ma20=m20, ma60=m60, ma120=m120, bb_pctb=pctb, bb_width_rank=bw_rank,
        states=states, sides=sides,
        spark=closes[-m:], spark_a=[a for a, _b in spans],
        spark_b=[b for _a, b in spans],
    )


def bollinger_series(closes: list[float]) -> tuple[list, list]:
    """볼린저 밴드 (상단, 하단) — 날마다. 판정(bollinger)과 같은 식 (20, 2σ, ÷N)."""
    up: list = [None] * len(closes)
    lo: list = [None] * len(closes)
    for i in range(BB_WINDOW - 1, len(closes)):
        win = closes[i + 1 - BB_WINDOW:i + 1]
        mid = sum(win) / BB_WINDOW
        sd = (sum((x - mid) ** 2 for x in win) / BB_WINDOW) ** 0.5
        up[i], lo[i] = mid + BB_K * sd, mid - BB_K * sd
    return up, lo


#: 차트에서 고를 수 있는 봉 수.
CHART_BARS = (60, 120, 250)


@dataclass
class ChartSeries:
    """종목 하나의 차트에 그릴 계열 — 전부 같은 길이(n), 구름만 n + 앞 25봉.

    판정(build_row)과 **같은 함수**로 계산합니다. 표에서 '과매도 탈출' 로
    나온 종목을 차트에서 열면 CCI 선이 −100 을 넘는 자리가 그대로 보여야
    합니다 — 차트를 따로 계산하면 그 대조가 깨집니다.
    """

    ticker: str = ""
    name: str = ""
    n: int = 0
    fwd: int = DISPLACEMENT
    dates: list = field(default_factory=list)
    open: list = field(default_factory=list)
    high: list = field(default_factory=list)
    low: list = field(default_factory=list)
    close: list = field(default_factory=list)
    volume: list = field(default_factory=list)
    ma20: list = field(default_factory=list)
    ma60: list = field(default_factory=list)
    ma120: list = field(default_factory=list)
    bb_up: list = field(default_factory=list)
    bb_lo: list = field(default_factory=list)
    span_a: list = field(default_factory=list)      # 길이 n + fwd
    span_b: list = field(default_factory=list)
    cci: list = field(default_factory=list)
    cci_sig: list = field(default_factory=list)
    macd: list = field(default_factory=list)
    macd_sig: list = field(default_factory=list)
    macd_hist: list = field(default_factory=list)
    stoch_k: list = field(default_factory=list)
    stoch_d: list = field(default_factory=list)
    pdi: list = field(default_factory=list)
    mdi: list = field(default_factory=list)
    adx: list = field(default_factory=list)
    #: 같은 봉으로 낸 판정 한 줄 (표와 같은 상태 이름)
    row: ChartRow | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.n >= 2


def chart_series(ticker: str, name: str, ohlc: dict, bars: int = 120) -> ChartSeries:
    """일봉 묶음({high, low, close[, open, volume, date]}) → 차트 계열 (최근 bars 봉)."""
    highs = list(ohlc.get("high") or [])
    lows = list(ohlc.get("low") or [])
    closes = list(ohlc.get("close") or [])
    total = min(len(highs), len(lows), len(closes))
    if total < 2:
        return ChartSeries(ticker, name, error="일봉을 받지 못했습니다.")
    highs, lows, closes = highs[-total:], lows[-total:], closes[-total:]

    def tail(key: str, default):
        vals = list(ohlc.get(key) or [])
        return vals[-total:] if len(vals) >= total else default

    opens = tail("open", [closes[i - 1] if i else closes[0] for i in range(total)])
    opens = [min(max(o, l), h) for o, l, h in zip(opens, lows, highs)]
    vols = tail("volume", [0.0] * total)
    dates = tail("date", [""] * total)

    cc = cci_series(highs, lows, closes)
    cc_sig = sma_series(cc, CCI_SIGNAL)
    line, sig, hist = macd_series(closes)
    sk, sd = stoch_slow(highs, lows, closes)
    pdi, mdi, adx = dmi(highs, lows, closes)
    m20, m60, m120 = (sma_series(closes, w) for w in (MA_SHORT, MA_MID, MA_LONG))
    bu, bl = bollinger_series(closes)
    n = max(2, min(int(bars), total))
    spans = [spans_at(highs, lows, i) for i in range(total - n, total + DISPLACEMENT)]

    def cut(vals):
        return list(vals[-n:])

    return ChartSeries(
        ticker=ticker, name=name, n=n, dates=cut(dates),
        open=cut(opens), high=cut(highs), low=cut(lows), close=cut(closes),
        volume=cut(vols), ma20=cut(m20), ma60=cut(m60), ma120=cut(m120),
        bb_up=cut(bu), bb_lo=cut(bl),
        span_a=[a for a, _b in spans], span_b=[b for _a, b in spans],
        cci=cut(cc), cci_sig=cut(cc_sig), macd=cut(line), macd_sig=cut(sig),
        macd_hist=cut(hist), stoch_k=cut(sk), stoch_d=cut(sd),
        pdi=cut(pdi), mdi=cut(mdi), adx=cut(adx),
        row=build_row(ticker, name, highs, lows, closes, vols),
    )


def build_rows(candidates, ohlc_by_ticker: dict, errors: dict | None = None
               ) -> list[ChartRow]:
    """(코드, 이름) 목록 + {코드: {"high","low","close"[,"volume"]}} → 줄 목록."""
    errors = errors or {}
    rows = []
    for ticker, name in candidates:
        d = ohlc_by_ticker.get(ticker)
        if not d or not d.get("close"):
            rows.append(ChartRow(ticker, name,
                                 error=errors.get(ticker) or "일봉을 받지 못했습니다."))
            continue
        row = build_row(ticker, name, d["high"], d["low"], d["close"],
                        d.get("volume"))
        row.last_bar = str(d.get("last_date") or "")
        rows.append(row)
    return rows


def last_bar(rows: list[ChartRow]) -> str:
    """줄들의 마지막 봉 날짜 중 **가장 흔한 것** ('' = 모름)."""
    seen: dict[str, int] = {}
    for r in rows:
        d = getattr(r, "last_bar", "")
        if d:
            seen[d] = seen.get(d, 0) + 1
    return max(seen, key=seen.get) if seen else ""


def counts(rows: list[ChartRow]) -> dict[str, int]:
    """조건별로 몇 종목이 해당하는가."""
    out = {k: 0 for k in CONDITION_KEYS}
    for r in rows:
        for k, v in r.flags().items():
            if v:
                out[k] += 1
    return out


def select(rows: list[ChartRow], required: tuple[str, ...] = (),
           side: str = "") -> list[ChartRow]:
    """required 조건에 **모두** 해당하는 종목. 비어 있으면 계산된 전 종목.

    side 를 주면('os' / 'ob') 고른 수준 지표(CCI·스토캐스틱·볼린저)가 그 쪽
    상태여야 합니다 — 'CCI 과매도 + 스토캐스틱 과매수' 가 한 줄에 섞이지
    않게. 조건을 안 골랐으면 **종목의 쪽**(ChartRow.side)이 그 쪽인 것만
    남깁니다 — 엇갈린 종목은 빠집니다. MACD 는 쪽을 가르지 않습니다.
    정렬: 쪽을 골랐으면 그 쪽 지표 수 → CCI 깊은 순, 아니면 해당 수 → CCI.
    """
    out = []
    for r in rows:
        if not r.ok:
            continue
        f = r.flags()
        if not all(f.get(k) for k in required):
            continue
        if side:
            picked = [k for k in required if k in SIDED]
            if picked:
                if any(r.sides.get(k) != side for k in picked):
                    continue
            elif r.side != side:
                # 조건을 안 골랐으면 종목의 쪽으로 — 엇갈린 종목은 어느 쪽에도 안 넣습니다
                continue
        out.append(r)
    if side:
        # 쪽을 골랐으면 그 쪽 지표가 많은 순 → CCI 가 더 깊은 순
        sign = -1.0 if side == "ob" else 1.0
        idx = 1 if side == "ob" else 0
        out.sort(key=lambda r: (-r.side_votes[idx],
                                sign * (r.cci if r.cci is not None else 0.0)))
    else:
        out.sort(key=lambda r: (-r.met, r.cci if r.cci is not None else 0.0))
    return out
