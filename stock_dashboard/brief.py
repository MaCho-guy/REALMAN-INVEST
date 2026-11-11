"""
================================================================================
증시 브리핑 — 화면에 있는 숫자를 **문장으로** 엮습니다.
================================================================================

무엇이 아닌가:

  다른 대시보드로 보내는 링크가 아닙니다. 읽으러 나가야 하면 이 대시보드를
  여는 의미가 없습니다. 카드는 조회용이고 브리핑은 통독용입니다.

무엇인가:

  이미 받아온 값을 사람이 읽는 몇 줄로 바꿉니다. **새로 받아오는 데이터가
  하나도 없습니다** — 매크로 판정, 공포탐욕, VIX, 반도체 수출, 재고 추이가
  전부 다른 섹션에서 이미 계산된 것들입니다. 그래서 브리핑 때문에 화면이
  느려지지 않습니다.

왜 같은 숫자를 다시 쓰는가:

  아래에 다 있습니다. 그런데 **흩어져 있으면 읽지 않습니다.** 브리핑은
  '지금 무슨 상황인가' 를 먼저 말하고 자세한 건 아래에서 보게 하는 자리입니다.

────────────────────────────────────────────────────────────────────────────────
쓰지 않는 것

  판단과 전망은 넣지 않습니다. "위험 구간에 접근" 같은 말은 쓰지 않고
  "하이일드 스프레드가 20일 평균보다 26.6% 높습니다" 라고만 적습니다.
  무엇이 움직였는지는 데이터가 말할 수 있지만 그게 무슨 뜻인지는 아닙니다.

  받지 못한 값은 그 줄을 **통째로 건너뜁니다.** 빈칸을 '보합' 같은 말로
  메우면, 데이터가 없는 것과 변화가 없는 것이 구분되지 않습니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

#: 줄의 무게. 클수록 위에 옵니다.
HOT, WARM, COOL = 3, 2, 1

#: 브리핑 최대 줄 수. 넘으면 읽지 않습니다.
MAX_LINES = 7

#: 한 영역이 차지할 수 있는 최대 줄 수.
#: 이게 없으면 매크로 임계값이 6개 걸린 날 브리핑이 전부 매크로가 되고
#: 심리·수출·재고가 밀려납니다. 브리핑은 깊이가 아니라 **폭**입니다 —
#: 자세한 건 어차피 아래 섹션에 다 있습니다.
MAX_PER_TOPIC = 3


@dataclass
class Line:
    """브리핑 한 줄. topic 은 어느 섹션에서 온 값인지입니다."""

    topic: str
    text: str
    severity: int = COOL

    def __post_init__(self) -> None:
        self.text = " ".join(self.text.split())


def as_of() -> str:
    """브리핑을 만든 시각. 날짜만으로는 장중 갱신인지 알 수 없습니다."""
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M 기준")


# ──────────────────────────────────────────────────────────────────────────────
# 재료별 문장
# ──────────────────────────────────────────────────────────────────────────────

def _from_triggers(triggers) -> list[Line]:
    """임계값을 넘은 매크로 지표.

    Trigger.title 과 detail 은 이미 사람이 읽는 문장입니다. 다시 쓰지 않고
    그대로 씁니다 — 같은 내용을 두 군데서 다르게 표현하면 어느 쪽이 맞는지
    헷갈립니다.

    많이 걸린 날은 심각한 것부터 MAX_PER_TOPIC 개까지만 적고 나머지는
    건수로 묶습니다.
    """
    rows = sorted(triggers or (), key=lambda t: -t.severity)
    out = [
        Line("매크로", f"{t.title}. {t.detail}",
             HOT if t.severity >= 3 else WARM)
        for t in rows[:MAX_PER_TOPIC]
    ]
    rest = len(rows) - MAX_PER_TOPIC
    if rest > 0:
        out.append(Line("매크로", f"임계값에 닿은 지표가 {rest}건 더 있습니다.",
                        COOL))
    return out


def _from_sentiment(fg, vix_state) -> list[Line]:
    """공포탐욕 + VIX 를 한 줄로 묶습니다.

    둘 다 '분위기' 라서 따로 쓰면 두 줄을 차지하면서 같은 말을 합니다.
    """
    bits: list[str] = []
    if fg is not None and getattr(fg, "ok", False):
        # band 가 한국어 라벨('탐욕'), rating 은 영문('greed') 입니다.
        band = getattr(fg, "band", "")
        bits.append(f"공포탐욕 <b>{fg.score:.0f}</b>"
                    + (f" ({band})" if band else ""))
    if vix_state is not None and getattr(vix_state, "ok", False):
        spot = getattr(vix_state, "spot", None)
        piece = f"VIX <b>{spot:.1f}</b>" if spot is not None else "VIX"
        # percentile_label 이 이미 '5년 중 20%' 형태로 완성돼 있습니다.
        # 여기서 다시 만들면 두 화면의 표현이 갈라집니다.
        label = getattr(vix_state, "percentile_label", "")
        if label:
            piece += f" ({label})"
        struct = getattr(vix_state, "structure", "")
        if struct:
            piece += f" · {struct}"
        bits.append(piece)
    if not bits:
        return []
    sev = WARM if (vix_state is not None
                   and getattr(vix_state, "is_inverted", False)) else COOL
    return [Line("심리", " · ".join(bits), sev)]


def _from_exports(exports) -> list[Line]:
    """한국 반도체 수출. 월 1회라, 새로 나온 달에만 눈에 띄게 둡니다."""
    if exports is None or not getattr(exports, "ok", False):
        return []
    parts = [f"한국 반도체 수출 {exports.period}"]
    if exports.value_100m_usd is not None:
        parts.append(f"<b>{exports.value_100m_usd:,.1f}억 달러</b>")
    if exports.yoy_pct is not None:
        parts.append(f"전년동월비 <b>{exports.yoy_pct:+,.1f}%</b>")
    age = exports.age_months
    sev = WARM if (age is not None and age <= 1) else COOL
    return [Line("수출", " · ".join(parts), sev)]


def _from_trends(trends) -> list[Line]:
    """재고 추이(DIO).

    메모리 사이클에서 재고가 쌓이는 방향인지가 신호입니다. 절대값은
    회사마다 달라 비교가 안 되므로 **변화와 연속성**만 적습니다.
    """
    rows: list[tuple[int, str]] = []
    for tr in (trends or {}).values():
        latest = getattr(tr, "latest", None)
        value = getattr(latest, "dio", None) if latest is not None else None
        if value is None:
            continue
        name = getattr(tr, "corp_name", "") or getattr(tr, "stock_code", "")
        piece = f"{name} <b>{value:,.0f}일</b>"
        qoq = getattr(tr, "dio_qoq_change", None)
        if qoq is not None:
            piece += f" ({qoq:+,.1f}일)"
        rising = getattr(tr, "dio_rising_quarters", None) or 0
        if rising >= 2:
            piece += f" · {rising}분기 연속 상승"
        rows.append((rising, piece))
    if not rows:
        return []
    rows.sort(key=lambda r: -r[0])
    text = "재고일수 " + " · ".join(p for _r, p in rows[:MAX_PER_TOPIC])
    return [Line("재고", text, WARM if rows[0][0] >= 2 else COOL)]


def _from_stale(readings) -> list[Line]:
    """오래된 값이 섞여 있으면 한 줄로 알립니다.

    브리핑이 몇 주 전 숫자로 쓰여 있는데 그걸 모르면, 틀린 판단을 자신
    있게 하게 됩니다.
    """
    stale = [r for r in (readings or ()) if getattr(r, "stale", False)]
    if not stale:
        return []
    names = ", ".join(r.spec.name for r in stale[:4])
    more = f" 외 {len(stale) - 4}건" if len(stale) > 4 else ""
    return [Line("자료", f"발표가 늦어 오래된 값: {names}{more}.", COOL)]


# ──────────────────────────────────────────────────────────────────────────────
# 조립
# ──────────────────────────────────────────────────────────────────────────────

def compose(*, readings=None, triggers=None, fg=None, vix_state=None,
            exports=None, trends=None) -> list[Line]:
    """재료를 받아 브리핑 줄을 만듭니다.

    전부 선택 인자입니다. 한 소스가 실패해도 나머지로 브리핑이 나와야
    합니다 — 수출을 못 받았다고 아침 브리핑이 통째로 비면 안 됩니다.
    """
    lines: list[Line] = []
    lines += _from_triggers(triggers)
    lines += _from_trends(trends)
    lines += _from_exports(exports)
    lines += _from_sentiment(fg, vix_state)
    lines += _from_stale(readings)

    # 안정 정렬 — 같은 무게면 넣은 순서를 지킵니다.
    lines.sort(key=lambda ln: -ln.severity)
    return lines[:MAX_LINES]


def headline(lines) -> str:
    """맨 위 한 줄."""
    rows = list(lines or ())
    if not rows:
        return "임계값에 닿은 지표가 없습니다 — 조용한 게 정상입니다"
    hot = sum(1 for ln in rows if ln.severity >= HOT)
    if hot:
        return f"지금 볼 것 {hot}건 · 확인할 항목 {len(rows)}건"
    return f"확인할 항목 {len(rows)}건 — 급한 건 없습니다"
