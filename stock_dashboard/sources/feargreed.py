"""
CNN 공포탐욕지수 (Fear & Greed Index) — **인증키 불필요**.

CNN 이 자기 페이지에서 호출하는 엔드포인트를 그대로 씁니다:

    https://production.dataviz.cnn.io/index/fearandgreed/graphdata

**솔직히 말해둘 것:** 이건 **공개 API 가 아니라 CNN 내부 엔드포인트**입니다.
문서가 없고, CNN 이 예고 없이 바꾸거나 막을 수 있습니다. 그래서 실패를 정상
경로로 취급하고(화면에서 조용히 비움), 다른 매크로 지표의 동작에 영향을 주지
않게 격리했습니다. User-Agent 를 안 보내면 거부됩니다.

지수 자체는 0~100 한 숫자지만, **7개 세부 지표**가 함께 옵니다. 한 숫자만 보면
왜 그런지 알 수 없어서, 세부 지표를 같이 보여줍니다 — 같은 "탐욕 70" 이
주가 모멘텀 때문인지 채권 수요 때문인지는 전혀 다른 이야기입니다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import requests

GRAPH_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
#: 대조용 공식 페이지. 화면에 링크로 띄워 숫자를 직접 비교할 수 있게 합니다.
CNN_PAGE = "https://edition.cnn.com/markets/fear-and-greed"
TIMEOUT = 15

#: 0~100 구간 구분. CNN 이 쓰는 경계입니다.
BANDS: tuple[tuple[float, str], ...] = (
    (25.0, "극단적 공포"),
    (45.0, "공포"),
    (55.0, "중립"),
    (75.0, "탐욕"),
    (100.1, "극단적 탐욕"),
)

#: 세부 지표 — 응답 키 → (한국어 이름, 무엇을 보는가)
COMPONENTS: tuple[tuple[str, str, str], ...] = (
    ("market_momentum_sp500", "주가 모멘텀",
     "S&P 500 이 125일 이동평균 위/아래 어디에 있나"),
    ("stock_price_strength", "주가 강도",
     "52주 신고가 종목 수 vs 신저가 종목 수"),
    ("stock_price_breadth", "거래량 폭",
     "상승 종목 거래량 vs 하락 종목 거래량"),
    ("put_call_options", "풋/콜 비율",
     "하락 베팅(풋)이 상승 베팅(콜)보다 많은가"),
    ("market_volatility_vix", "변동성(VIX)",
     "VIX 가 50일 이동평균 대비 어디에 있나"),
    ("safe_haven_demand", "안전자산 수요",
     "주식 수익률 vs 국채 수익률 — 돈이 어디로 가나"),
    ("junk_bond_demand", "하이일드 수요",
     "정크본드와 국채의 수익률 격차 — 위험 선호도"),
)

COMPONENT_LABEL = {key: label for key, label, _d in COMPONENTS}
COMPONENT_DESC = {key: desc for key, _l, desc in COMPONENTS}


class FearGreedError(RuntimeError):
    """공포탐욕지수 조회 실패."""


def band_label(score: float | None) -> str:
    if score is None:
        return "—"
    for limit, label in BANDS:
        if score < limit:
            return label
    return BANDS[-1][1]


@dataclass
class Component:
    """세부 지표 하나."""

    key: str
    score: float | None = None
    rating: str = ""

    @property
    def label(self) -> str:
        return COMPONENT_LABEL.get(self.key, self.key)

    @property
    def desc(self) -> str:
        return COMPONENT_DESC.get(self.key, "")

    @property
    def band(self) -> str:
        return band_label(self.score)


@dataclass
class FearGreed:
    """공포탐욕지수 스냅샷."""

    score: float | None = None
    rating: str = ""
    observed_at: dt.date | None = None

    #: 과거 비교값 (CNN 이 함께 돌려줍니다)
    previous_close: float | None = None
    previous_week: float | None = None
    previous_month: float | None = None
    previous_year: float | None = None

    components: list[Component] = field(default_factory=list)
    history: list[tuple[str, float]] = field(default_factory=list)

    error: str = ""

    #: 응답 구조 확인용 — 진단에서 "CNN 이 무엇을 보냈나" 를 보여줍니다
    raw_keys: list[str] = field(default_factory=list)
    root_keys: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error == "" and self.score is not None

    @property
    def band(self) -> str:
        return band_label(self.score)

    @property
    def score_label(self) -> str:
        return "—" if self.score is None else f"{self.score:,.0f}"

    @property
    def change_1w(self) -> float | None:
        if self.score is None or self.previous_week is None:
            return None
        return self.score - self.previous_week

    @property
    def change_1m(self) -> float | None:
        if self.score is None or self.previous_month is None:
            return None
        return self.score - self.previous_month

    @property
    def lag_days(self) -> int | None:
        if self.observed_at is None:
            return None
        return (dt.date.today() - self.observed_at).days

    @property
    def extremes(self) -> list[Component]:
        """극단에 있는 세부 지표만. 지수가 왜 그 값인지 설명하는 항목들입니다."""
        return [c for c in self.components
                if c.score is not None and (c.score < 25.0 or c.score >= 75.0)]


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _date_from(value) -> dt.date | None:
    """타임스탬프를 날짜로. **형식을 단정하지 않습니다.**

    CNN 이 밀리초를 쓰는 것으로 보이지만 문서가 없어 확인할 수 없습니다.
    초 단위로 바뀌면 날짜가 1970년대로 나오고, ISO 문자열로 바뀌면 통째로
    실패합니다. 그래서 세 형식을 다 받고, **결과가 상식적인 범위(2000년
    이후 ~ 내일)에 들어오는지 검사**합니다. 범위를 벗어나면 None 입니다 —
    틀린 날짜를 보여주는 것보다 비우는 게 낫습니다.
    """
    lo = dt.date(2000, 1, 1)
    hi = dt.date.today() + dt.timedelta(days=1)

    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        for parse in (dt.date.fromisoformat, lambda t: dt.datetime.fromisoformat(t).date()):
            try:
                found = parse(text)
            except ValueError:
                continue
            if lo <= found <= hi:
                return found
        return None

    if not isinstance(value, (int, float)):
        return None

    for divisor in (1000.0, 1.0):          # 밀리초 → 초
        try:
            found = dt.datetime.fromtimestamp(
                value / divisor, dt.timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            continue
        if lo <= found <= hi:
            return found
    return None


def parse(payload: dict, *, history_points: int = 60) -> FearGreed:
    """응답을 파싱합니다. 네트워크와 분리해 테스트합니다."""
    if not isinstance(payload, dict):
        raise FearGreedError("응답 형식이 예상과 다릅니다.")

    root = payload.get("fear_and_greed")
    if not isinstance(root, dict):
        raise FearGreedError(
            "응답에 fear_and_greed 가 없습니다 — CNN 이 구조를 바꿨을 수 "
            "있습니다 (문서화되지 않은 내부 엔드포인트입니다)."
        )

    def pick(*keys):
        """키 이름이 바뀔 수 있으니 후보를 순서대로 봅니다."""
        for key in keys:
            value = _num(root.get(key))
            if value is not None:
                return value
        return None

    out = FearGreed(
        score=pick("score", "value"),
        rating=str(root.get("rating") or root.get("label") or ""),
        observed_at=_date_from(
            root.get("timestamp") or root.get("x") or root.get("date")),
        previous_close=pick("previous_close", "previousClose"),
        previous_week=pick("previous_1_week", "previous_week", "previous1Week"),
        previous_month=pick("previous_1_month", "previous_month",
                            "previous1Month"),
        previous_year=pick("previous_1_year", "previous_year", "previous1Year"),
    )
    #: 응답의 최상위 키 — 구조가 바뀌었는지 진단에서 보여주기 위해 남깁니다
    out.raw_keys = sorted(k for k in payload if isinstance(k, str))
    out.root_keys = sorted(k for k in root if isinstance(k, str))
    if out.score is None:
        raise FearGreedError("score 를 읽지 못했습니다.")

    for key, _label, _desc in COMPONENTS:
        body = payload.get(key)
        if not isinstance(body, dict):
            continue
        out.components.append(Component(
            key=key,
            score=_num(body.get("score")),
            rating=str(body.get("rating") or ""),
        ))

    rows = payload.get("fear_and_greed_historical")
    data = rows.get("data") if isinstance(rows, dict) else None
    if isinstance(data, list):
        for row in data[-history_points:]:
            if not isinstance(row, dict):
                continue
            date = _date_from(row.get("x"))
            value = _num(row.get("y"))
            if date is not None and value is not None:
                out.history.append((date.isoformat(), value))
    return out


def fetch(*, user_agent: str = "stock-dashboard/1.0 (personal research)",
          days: int = 90) -> FearGreed:
    """현재 지수 + 세부 지표 + 최근 이력.

    실패하면 예외 대신 **error 가 채워진 객체**를 돌려줍니다. 매크로 탭의
    다른 지표가 이것 때문에 비지 않게 하려는 것입니다.
    """
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        resp = requests.get(
            f"{GRAPH_URL}/{start}",
            timeout=TIMEOUT,
            headers={"User-Agent": user_agent,
                     "Accept": "application/json",
                     "Referer": "https://edition.cnn.com/markets/fear-and-greed"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        return FearGreed(error=(
            f"CNN 이 HTTP {status} 로 거부했습니다. 문서화되지 않은 내부 "
            "엔드포인트라 예고 없이 막힐 수 있습니다."
        ))
    except requests.RequestException as exc:
        return FearGreed(error=f"요청 실패 — {exc}")
    except ValueError as exc:
        return FearGreed(error=f"JSON 파싱 실패 — {exc}")

    try:
        return parse(payload)
    except FearGreedError as exc:
        return FearGreed(error=str(exc))
