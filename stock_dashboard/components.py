"""
카드 / 테이블 HTML 렌더링.

Streamlit 기본 위젯으로는 jusikbot 같은 밀도 높은 카드 그리드를 만들기
어려우므로, 카드는 HTML 문자열로 직접 조립해서 st.markdown 으로 넣습니다.
사용자 입력이 섞이지 않는 경로지만, 외부 API 가 돌려준 문자열(종목명 등)이
들어오므로 모든 텍스트는 html.escape 로 이스케이프합니다.
"""

from __future__ import annotations

import datetime as dt
import html
import re

from compute import FxRates, Premium
from config import Instrument
from sources.model import MarketStatus, Quote

# ──────────────────────────────────────────────────────────────────────────────
# 숫자 포맷
# ──────────────────────────────────────────────────────────────────────────────

_BADGE_CLASS = {
    MarketStatus.LIVE: "live",
    MarketStatus.REGULAR: "live",
    MarketStatus.PRE: "pre",
    MarketStatus.POST: "post",
    MarketStatus.CLOSED: "closed",
    MarketStatus.UNKNOWN: "closed",
}


def auto_decimals(value: float) -> int:
    """가격 크기에 따라 소수점 자리수를 정합니다."""
    magnitude = abs(value)
    if magnitude >= 10_000:
        return 0
    if magnitude >= 100:
        return 2
    if magnitude >= 1:
        return 3
    return 5


def fmt_num(value: float | None, decimals: int | None = None) -> str:
    """천단위 구분 기호를 넣어 포맷합니다. None 이면 em dash."""
    if value is None:
        return "—"
    dec = decimals if decimals is not None else auto_decimals(value)
    return f"{value:,.{dec}f}"


def fmt_signed(value: float | None, decimals: int | None = None) -> str:
    """부호를 항상 붙입니다 (색상에만 의존하지 않도록)."""
    if value is None:
        return "—"
    dec = decimals if decimals is not None else auto_decimals(value)
    return f"{value:+,.{dec}f}"


def fmt_pct(value: float | None, decimals: int = 2, signed: bool = True) -> str:
    if value is None:
        return "—"
    sign = "+" if signed else ""
    return f"{value:{sign},.{decimals}f}%"


def fmt_krw_compact(value: float | None) -> str:
    """원화를 읽기 쉬운 단위로 표기합니다.

    압축은 정보를 잃지 않는 구간에서만 합니다.
      1억 이상        -> '2.50억원'
      1,000만 ~ 1억   -> '1,500만원'
      그 미만         -> '66,240원'  (만원 단위로 줄이면 반올림 오차가 커집니다)

    예) 66,240원을 '6.6만원'으로 줄이면 1원 단위가 사라지므로 그대로 둡니다.
    """
    if value is None:
        return "—"
    abs_v = abs(value)
    if abs_v >= 1_0000_0000:          # 1억
        return f"{value / 1_0000_0000:,.2f}억원"
    if abs_v >= 1000_0000:            # 1,000만
        return f"{value / 1_0000:,.0f}만원"
    return f"{value:,.0f}원"


def fmt_big_usd(value: float | None) -> str:
    """시가총액 등 큰 USD 금액을 B/M 단위로 표기합니다."""
    if value is None:
        return "—"
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"${value / 1e12:,.2f}T"
    if abs_v >= 1e9:
        return f"${value / 1e9:,.1f}B"
    if abs_v >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value:,.0f}"


def direction_class(value: float | None) -> str:
    if value is None:
        return "flat"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def direction_glyph(value: float | None) -> str:
    """색상 외 2차 채널. 색각이상·흑백 인쇄에서도 방향이 읽히도록 합니다."""
    if value is None:
        return ""
    if value > 0:
        return "▲ "
    if value < 0:
        return "▼ "
    return "— "


# ──────────────────────────────────────────────────────────────────────────────
# 카드
# ──────────────────────────────────────────────────────────────────────────────

def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def render_news_block(headlines, *, limit: int = 3,
                      title: str = "관련 헤드라인") -> str:
    """헤드라인 목록. 신호 카드와 매크로 탭이 같은 함수를 씁니다.

    뉴스는 보조이므로 비면 빈 문자열을 돌려줍니다 — 화면에 '뉴스 없음' 같은
    빈 칸을 남기지 않습니다.

    항상 카드 **안쪽**에 들어갑니다 — 테두리 없이 위쪽 실선 한 줄로만
    구분합니다. 전에는 카드 밖에 상자로 그렸는데, 스트림릿이 그 사이에
    컨테이너 여백을 끼워 넣어 정체불명의 박스가 하나 더 떠 있는 것처럼
    보였습니다.
    """
    if not headlines:
        return ""
    items = "".join(
        "<li>"
        + (
            f'<a class="dash-inline-link" href="{_esc(h.url)}" target="_blank" '
            f'rel="noopener noreferrer">{_esc(h.title)}</a>'
            if h.url else _esc(h.title)
        )
        + (
            f' <span class="dash-news-meta">{_esc(h.source)}'
            + (f" · {h.days_ago}일 전" if h.days_ago is not None else "")
            + "</span>"
            if (h.source or h.days_ago is not None) else ""
        )
        + "</li>"
        for h in headlines[:limit]
    )
    return (
        '<div class="dash-news">'
        f'<div class="dash-news-head">{_esc(title)}</div>'
        f"<ul>{items}</ul>"
        "</div>"
    )


def _extra_row(label: str, value_html: str) -> str:
    return (
        '<div class="dash-extra-row">'
        f'<span class="dash-extra-label">{_esc(label)}</span>'
        f"{value_html}"
        "</div>"
    )


def _value_span(text: str, cls: str = "") -> str:
    klass = f"dash-extra-value {cls}".strip()
    return f'<span class="{klass}">{_esc(text)}</span>'


def _name_html(inst: Instrument) -> str:
    """카드 제목. 연결할 주소가 있으면 링크로 만듭니다."""
    name = _esc(inst.name)
    url = inst.resolved_link()
    if not url:
        return f'<div class="dash-card-name">{name}</div>'
    # target="_blank" + rel: 아티팩트/샌드박스 환경에서도 새 탭으로 열립니다.
    return (
        '<div class="dash-card-name">'
        f'<a class="dash-card-link" href="{_esc(url)}" target="_blank" '
        f'rel="noopener noreferrer">{name}<span class="dash-link-arrow">↗</span></a>'
        "</div>"
    )


def render_card(
    inst: Instrument,
    quote: Quote | None,
    fx: FxRates,
    premium: Premium | None = None,
) -> str:
    """종목 카드 하나의 HTML 을 반환합니다."""
    name_html = _name_html(inst)
    meta_bits = [b for b in (_esc(inst.symbol), _esc(inst.exchange)) if b]

    # ── 조회 실패 ────────────────────────────────────────────────────────────
    if quote is None or not quote.ok:
        reason = (quote.error if quote is not None else "데이터 소스가 응답하지 않았습니다.") or "원인 불명"
        url = inst.resolved_link()
        manual = (
            f'<div class="dash-note">직접 확인: '
            f'<a class="dash-inline-link" href="{_esc(url)}" target="_blank" '
            f'rel="noopener noreferrer">{_esc(url)}</a></div>'
            if url
            else ""
        )
        return (
            '<div class="dash-card">'
            f"{name_html}"
            f'<div class="dash-card-meta">{" · ".join(meta_bits)}'
            '<span class="dash-badge error">데이터 없음</span></div>'
            '<div class="dash-price" style="color:var(--dash-ink-muted)">—</div>'
            f'<div class="dash-error">{_esc(reason)}</div>'
            f"{manual}"
            "</div>"
        )

    scale = inst.scale or 1.0
    price = quote.price * scale if quote.price is not None else None
    change = quote.change * scale if quote.change is not None else None
    pct = quote.change_pct  # 비율은 scale 에 영향받지 않습니다

    badge_cls = _BADGE_CLASS.get(quote.status, "closed")
    badge_html = (
        f'<span class="dash-badge {badge_cls}">{_esc(quote.status.value)}</span>'
        if quote.status is not MarketStatus.UNKNOWN
        else ""
    )

    # 통화/단위 표기
    unit = inst.suffix or ""
    cur = (quote.currency or inst.currency or "").upper()
    price_text = fmt_num(price, inst.decimals) + unit

    # 원화 환산 (USD/EUR 표시 종목에만)
    sub_bits: list[str] = []
    if cur and cur != "KRW" and not unit:
        krw = fx.to_krw(price, cur) if price is not None else None
        if krw is not None:
            sub_bits.append(f"{cur} · 약 {fmt_krw_compact(krw)}")
        else:
            sub_bits.append(cur)
    elif cur == "KRW":
        sub_bits.append("KRW")

    sub_html = f'<div class="dash-price-sub">{_esc(" · ".join(sub_bits))}</div>' if sub_bits else ""

    delta_cls = direction_class(change if change is not None else pct)
    delta_text = f"{direction_glyph(change if change is not None else pct)}{fmt_signed(change, inst.decimals)} ({fmt_pct(pct)})"

    # ── 추가 지표 ────────────────────────────────────────────────────────────
    extras: list[str] = []

    if quote.extended_price is not None and quote.extended_label:
        ext_pct = quote.extended_change_pct
        ext_text = f"{fmt_num(quote.extended_price * scale, inst.decimals)} ({fmt_pct(ext_pct)})"
        extras.append(
            _extra_row(quote.extended_label, _value_span(ext_text, direction_class(ext_pct)))
        )

    if premium is not None:
        extras.append(
            _extra_row(
                "본주 대비 괴리율",
                _value_span(
                    f"{direction_glyph(premium.premium_pct)}{fmt_pct(premium.premium_pct)}",
                    direction_class(premium.premium_pct),
                ),
            )
        )
        extras.append(_extra_row("본주 환산가", _value_span(f"{fmt_num(premium.implied_krw, 0)}원")))
        extras.append(_extra_row("국내 본주", _value_span(f"{fmt_num(premium.local_krw, 0)}원")))

    funding = quote.extra.get("funding_8h")
    if funding is not None:
        extras.append(
            _extra_row(
                "펀딩률 (8h)",
                _value_span(fmt_pct(funding * 100, 4), direction_class(funding)),
            )
        )

    perp_premium = quote.extra.get("perp_premium")
    if perp_premium is not None:
        extras.append(
            _extra_row(
                "오라클 대비 프리미엄",
                _value_span(fmt_pct(perp_premium * 100, 3), direction_class(perp_premium)),
            )
        )

    oi = quote.extra.get("open_interest")
    if oi is not None:
        extras.append(_extra_row("미결제약정", _value_span(fmt_num(oi, 0))))

    vol = quote.extra.get("day_volume_usd")
    if vol is not None:
        extras.append(_extra_row("24h 거래대금", _value_span(fmt_big_usd(vol))))

    if quote.extra.get("fallback"):
        extras.append(_extra_row("데이터 출처", _value_span(str(quote.extra["fallback"]))))

    extras_html = f'<div class="dash-extras">{"".join(extras)}</div>' if extras else ""

    note_html = f'<div class="dash-note">{_esc(inst.note)}</div>' if inst.note else ""
    unverified_html = (
        '<div><span class="dash-unverified">티커 미검증</span></div>' if not inst.verified else ""
    )

    return (
        '<div class="dash-card">'
        f"{name_html}"
        f'<div class="dash-card-meta">{" · ".join(meta_bits)}{badge_html}</div>'
        f'<div class="dash-price">{_esc(price_text)}</div>'
        f"{sub_html}"
        f'<div class="dash-delta {delta_cls}">{_esc(delta_text)}</div>'
        f"{extras_html}"
        f"{note_html}"
        f"{unverified_html}"
        "</div>"
    )


def render_section_head(title: str, subtitle: str,
                        count: int | None = None) -> str:
    """구역 제목. count=None 이면 개수 배지를 그리지 않습니다.

    탭 맨 위의 소개용 제목에 0 을 넘기면 '0개 항목' 이라고 찍혀서 아래에
    내용이 있는데도 비어 있는 것처럼 보입니다. 셀 것이 없는 자리는
    None 을 넘기십시오.
    """
    sub = f'<span class="dash-section-sub">{_esc(subtitle)}</span>' if subtitle else ""
    badge = ("" if count is None
             else f'<span class="dash-section-count">{count}개 항목</span>')
    return (
        '<div class="dash-section-head">'
        f'<span class="dash-section-title">{_esc(title)}</span>'
        f"{sub}{badge}"
        "</div>"
    )


#: 설명 문구에서 되살릴 태그. **전부 이스케이프한 뒤 이것만 되돌립니다** —
#: 허용 목록 방식이라 새 태그가 섞여 들어와도 글자로 보일 뿐 실행되지 않습니다.
_SAFE_TAGS = ("b", "br", "code", "em", "strong", "small")

_SAFE_RE = re.compile(
    r"&lt;(/?)(" + "|".join(_SAFE_TAGS) + r")\s*/?&gt;", re.I)

#: 링크는 http(s) 만. class·target·rel 은 우리가 다시 붙입니다 —
#: 원문의 속성을 그대로 살리면 onclick 같은 게 끼어들 수 있습니다.
#: 속성 안에는 &quot; 가 들어가므로 [^&] 로는 못 넘습니다.
#: 태그 경계인 &gt; 를 만나기 전까지만 훑습니다.
_ATTR = r"(?:(?!&gt;).)*?"
_SAFE_A_RE = re.compile(
    r"&lt;a\s+" + _ATTR + r"href=&quot;(https?://[^&\s]+)&quot;" + _ATTR
    + r"&gt;(.*?)&lt;/a&gt;", re.I | re.S)


def _safe_inline(text: str) -> str:
    """이스케이프한 뒤 안전한 태그만 되살립니다.

    왜 필요한가: 설명 문구 60여 곳이 <b>·<br>·<code> 를 쓰는데
    _esc 만 거치면 **태그가 글자 그대로 화면에 나옵니다.** 스크린샷으로
    확인하기 전까지 그렇게 돌아가고 있었습니다.
    """
    out = _esc(text)
    out = _SAFE_A_RE.sub(
        lambda m: (f'<a class="dash-inline-link" href="{m.group(1)}" '
                   f'target="_blank" rel="noopener noreferrer">'
                   f'{m.group(2)}</a>'),
        out)
    out = _SAFE_RE.sub(lambda m: f"<{m.group(1)}{m.group(2).lower()}>", out)
    # 설명 문구를 쓰면서 습관적으로 **강조** 를 쓰는데, 지금까지는 별표가
    # 글자 그대로 화면에 찍혔습니다. 태그로 바꿔 줍니다. 이스케이프를 이미
    # 끝낸 뒤라 안쪽 내용은 안전합니다.
    return _MD_BOLD_RE.sub(r"<b>\1</b>", out)


# 줄바꿈을 건너뛰지 않게 한 줄 안에서만, 그리고 비어 있지 않은 것만
_MD_BOLD_RE = re.compile(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*")


def render_footnote(text: str) -> str:
    return (f'<div class="dash-footnote">{_safe_inline(text)}</div>'
            if text else "")


def render_topbar(title: str, subtitle: str, clock: str,
                  market_label: str = "") -> str:
    """맨 위 제목줄. market_label 을 주면 제목 옆에 **지금 보는 시장**을
    크게 적습니다 — 시장마다 섹션이 다르므로 어느 쪽인지가 항상 보여야
    합니다."""
    badge = (f'<span class="dash-market-badge">{_esc(market_label)}</span>'
             if market_label else "")
    return (
        '<div class="dash-topbar">'
        f'<span class="dash-logo">{_esc(title)}</span>{badge}'
        f'<span class="dash-logo-sub">{_esc(subtitle)}</span>'
        f'<span class="dash-clock">{_esc(clock)}</span>'
        "</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 밸류에이션 테이블
# ──────────────────────────────────────────────────────────────────────────────

_SIGNAL_ICON = {
    "new_filing": "📄",
    "earnings_soon": "📅",
    "stale": "🕒",
    "never": "○",
    "partial": "◐",
    "move": "⚡",
    "extreme": "📉",
    "inventory": "📦",
}


def render_dio_chart(trend) -> str:
    """DIO 시계열 막대 그래프 — 좌표를 계산해서 SVG 로 그립니다.

    고친 것 세 가지 (전 버전이 나이트 모드에서 깨졌습니다):

    1. **색상을 CSS 변수로.** 전에는 `#898781`·`#2a78d6` 을 하드코딩해서
       나이트 모드에서 배경과 대비가 안 났습니다. 대시보드의 다른 차트는
       전부 변수를 쓰는데 이것만 빠져 있었습니다.
    2. **밴드 라벨을 왼쪽으로.** 밴드 최대값은 보통 가장 높은 막대와 같아서,
       오른쪽에 쓰면 막대 값 라벨과 **같은 자리에 겹쳤습니다.**
    3. **가까운 밴드선은 합칩니다.** 최대·중간·최소가 몇 일 차이면 선 세 개와
       라벨 세 개가 뭉쳐서 읽을 수 없게 됩니다.
    """
    series = trend.dio_series
    if len(series) < 2:
        return ""

    values = [v for _l, v in series]
    low, high = min(values), max(values)
    span = max(high - low, 1.0)
    y_min, y_max = low - span * 0.35, high + span * 0.28

    # 가로를 넓게 잡습니다. 700x220 이면 카드(약 1230px)에서 왼쪽 절반만
    # 쓰고 오른쪽이 비었습니다 — max-width 로 700 에서 멈췄기 때문입니다.
    # 1000x210 은 같은 폭에서 높이가 246px 정도로 들어옵니다.
    width, height = 1000, 210
    pad_l, pad_r, pad_t, pad_b = 78, 20, 20, 42
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b

    def y_of(v: float) -> float:
        return pad_t + ph * (y_max - v) / (y_max - y_min)

    # 막대 폭 상한을 올립니다 — 폭이 넓어진 만큼 46px 로 두면 가느다란
    # 막대에 간격만 벌어져 허전합니다.
    bar_w = min(pw / len(series) * 0.52, 68.0)
    parts = [
        f'<svg class="dash-dio" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{_esc(trend.corp_name)} 재고자산회전일수 추이">'
    ]

    # ── 밴드 기준선 — 왼쪽에 라벨, 가까운 것은 합칩니다 ──────────────────────
    band = trend.dio_band
    if band is not None:
        lo, mid, hi = band
        # 라벨이 읽히려면 최소 14px 는 떨어져야 합니다
        candidates = [(hi, "최대"), (mid, "중간"), (lo, "최소")]
        drawn: list[tuple[float, str, float]] = []
        for value, label in candidates:
            yy = y_of(value)
            clash = next((d for d in drawn if abs(d[2] - yy) < 14.0), None)
            if clash is not None:
                # 겹치면 기존 라벨에 합쳐 적습니다 (선은 한 번만)
                drawn[drawn.index(clash)] = (
                    clash[0], f"{clash[1]}·{label}", clash[2])
                continue
            drawn.append((value, label, yy))

        for value, label, yy in drawn:
            parts.append(
                f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" '
                f'y2="{yy:.1f}" stroke="var(--dash-border)" stroke-width="1" '
                'stroke-dasharray="4 3"/>'
            )
            parts.append(
                f'<text x="{pad_l - 8}" y="{yy + 3.5:.1f}" text-anchor="end" '
                'font-size="9.5" fill="var(--dash-ink-muted)">'
                f'{_esc(label)} {value:.0f}</text>'
            )

    # ── 기준선(바닥) ────────────────────────────────────────────────────────
    base_y = height - pad_b
    parts.append(
        f'<line x1="{pad_l}" y1="{base_y}" x2="{width - pad_r}" y2="{base_y}" '
        'stroke="var(--dash-border)" stroke-width="1"/>'
    )

    # ── 막대 ────────────────────────────────────────────────────────────────
    for i, (label, value) in enumerate(series):
        cx = pad_l + pw * (i + 0.5) / len(series)
        top = y_of(value)
        is_last = i == len(series) - 1
        fill = "var(--dash-ink)" if is_last else "var(--dash-ink-muted)"
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{top:.1f}" '
            f'width="{bar_w:.1f}" height="{max(base_y - top, 2.0):.1f}" '
            f'fill="{fill}" rx="3"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{top - 6:.1f}" text-anchor="middle" '
            f'font-size="11" font-weight="650" fill="{fill}">{value:.0f}</text>'
        )
        # 분기 라벨은 두 줄로 — '2026 1분기' 가 한 줄이면 옆 라벨과 붙습니다
        head, _, rest = _esc(label).partition(" ")
        parts.append(
            f'<text x="{cx:.1f}" y="{base_y + 14:.1f}" text-anchor="middle" '
            f'font-size="9" fill="var(--dash-ink-muted)">{head}</text>'
        )
        if rest:
            parts.append(
                f'<text x="{cx:.1f}" y="{base_y + 25:.1f}" text-anchor="middle" '
                f'font-size="9" fill="var(--dash-ink-muted)">{rest}</text>'
            )

    parts.append(
        f'<text x="{pad_l - 8}" y="{pad_t - 7:.1f}" text-anchor="end" '
        'font-size="9" fill="var(--dash-ink-muted)">DIO(일)</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_inventory_panel(trend, checks: list) -> str:
    """한 기업의 재고 지표 블록."""
    latest = trend.latest
    if latest is None:
        return (
            '<div class="dash-missing">'
            f'<div class="dash-missing-title">{_esc(trend.corp_name)} — 재고 지표 없음</div>'
            '<div class="dash-missing-body">'
            + ("<br>".join(_esc(e) for e in trend.errors) if trend.errors
               else "수집된 분기가 없습니다.")
            + "</div></div>"
        )

    def fmt_won(value: float | None) -> str:
        if value is None:
            return "—"
        if abs(value) >= 1_0000_0000_0000:
            return f"{value / 1_0000_0000_0000:,.1f}조원"
        if abs(value) >= 1_0000_0000:
            return f"{value / 1_0000_0000:,.0f}억원"
        return f"{value:,.0f}원"

    kpis = [
        ("DIO (재고자산회전일수)",
         f"{latest.dio:.0f}일" if latest.dio is not None else "—"),
        ("직전 분기 대비",
         f"{trend.dio_qoq_change:+.1f}일" if trend.dio_qoq_change is not None else "—"),
        ("연속 상승",
         f"{trend.dio_rising_quarters}분기"),
        ("재고-매출 갭",
         f"{trend.inventory_revenue_gap:+.1f}%p"
         if trend.inventory_revenue_gap is not None else "—"),
    ]
    kpi_html = "".join(
        f'<div><div class="lbl">{_esc(k)}</div><div class="val">{_esc(v)}</div></div>'
        for k, v in kpis
    )

    is_xbrl = latest.fs_div == "XBRL"

    def fmt_money(value: float | None) -> str:
        """XBRL 경로는 달러, DART 경로는 원화."""
        if value is None:
            return "—"
        if not is_xbrl:
            return fmt_won(value)
        if abs(value) >= 1e9:
            return f"${value / 1e9:,.1f}B"
        if abs(value) >= 1e6:
            return f"${value / 1e6:,.0f}M"
        return f"${value:,.0f}"

    rows = "".join(
        "<tr>"
        f"<td>{_esc(q.label)}</td>"
        f"<td>{_esc(fmt_money(q.inventory))}</td>"
        f"<td>{_esc(fmt_money(q.cost_of_sales))}</td>"
        f"<td>{_esc(fmt_money(q.revenue))}</td>"
        f"<td>{_esc(f'{q.period_days:.0f}일')}</td>"
        f"<td>{(f'{q.dio:.0f}일' if q.dio is not None else '—')}</td>"
        "</tr>"
        for q in reversed(trend.quarters)
    )

    check_rows = "".join(
        "<tr>"
        f'<td>{"🔴" if c.lit else ("—" if c.lit is None else "⚪")}</td>'
        f"<td>{_esc(c.label)}</td>"
        f'<td class="{"na" if c.lit is None else ""}">{_esc(c.detail)}</td>'
        "</tr>"
        for c in checks
    )

    missing = trend.all_missing
    missing_html = (
        f'<div class="dash-footnote">찾지 못한 계정: {_esc(", ".join(missing))} — '
        f'계정명이 다르거나 주석 항목일 수 있습니다. 숫자를 추정하지 않고 비워 뒀습니다.</div>'
        if missing else ""
    )
    dio_warn = trend.dio_warnings
    warn_html = (
        '<div class="box warn dash-cycle-warn">'
        '<b>기간 불일치로 제외한 분기가 있습니다</b><br>'
        + "<br>".join(_esc(w) for w in dio_warn)
        + "</div>"
        if dio_warn else ""
    )

    # XBRL 경로(미국 기업)는 회사가 직접 공시한 DIO 와 값이 다를 수 있습니다.
    # 이걸 말해주지 않으면 사용자가 공시값과 비교하고 버그로 오해합니다.
    convention_html = (
        '<div class="dash-footnote">'
        "이 DIO 는 <b>기말 재고 ÷ 기간 매출원가 × 구간 실제 일수</b> 로 계산한 값입니다. "
        "회사가 실적발표에서 직접 공시하는 DIO 와는 다를 수 있습니다 — 기업은 보통 "
        "평균 재고를 쓰거나 분기를 91일로 고정하는 관행을 따릅니다. "
        "여기 값은 한국 2사와 <b>같은 방식으로 맞춘 비교용</b>이고, 단일 기업의 절대 "
        "수준을 볼 때는 회사 공시값이 더 적절합니다."
        "</div>"
        if latest.fs_div == "XBRL" else ""
    )
    errors_html = (
        f'<div class="dash-footnote">수집 경고: {_esc(" / ".join(trend.errors[:3]))}</div>'
        if trend.errors else ""
    )

    return (
        '<div class="dash-cycle">'
        f'<div class="dash-cycle-head">{_esc(trend.corp_name)} '
        f'<span class="dash-cycle-sym">{_esc(trend.stock_code)}</span>'
        f'<span class="dash-cycle-basis">기준 {_esc(latest.label)} 보고서 · '
        f'{_esc(latest.fs_div)}</span></div>'
        f'<div class="kpi">{kpi_html}</div>'
        + render_dio_chart(trend)
        + '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th>보고서</th><th>재고자산</th><th>매출원가</th>"
        "<th>매출액</th><th>기간</th><th>DIO</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        '<div class="dash-cycle-sub">②→③ 전환 체크리스트 (재고 항목만 자동 판정)</div>'
        '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th></th><th>항목</th><th>근거</th></tr></thead>"
        f"<tbody>{check_rows}</tbody></table></div>"
        + warn_html
        + convention_html
        + missing_html
        + errors_html
        + "</div>"
    )


def render_signal_card(sig, headlines: list | None = None) -> str:
    """변화 감지 신호 하나를 카드로 그립니다."""
    icon = _SIGNAL_ICON.get(sig.kind, "•")
    sev_cls = {3: "now", 2: "week", 1: "fyi"}.get(sig.severity, "fyi")

    tags_html = "".join(
        f'<span class="dash-sigtag">{_esc(t)}</span>' for t in sig.tags[:5]
    )

    link_html = ""
    if sig.url:
        link_html = (
            f' <a class="dash-inline-link" href="{_esc(sig.url)}" target="_blank" '
            f'rel="noopener noreferrer">공시 원문 ↗</a>'
        )

    news_html = render_news_block(headlines)

    # 묶인 신호는 종목명 대신 "N종목" 을 제목에 쓰고, 목록은 detail 에 들어갑니다
    if sig.aggregate:
        head = (
            f'<span class="dash-sig-icon">{icon}</span>'
            f'<span class="dash-sig-name">{sig.count}종목</span>'
            f'<span class="dash-sig-sym">묶음</span>'
        )
    else:
        head = (
            f'<span class="dash-sig-icon">{icon}</span>'
            f'<span class="dash-sig-name">{_esc(sig.inst.name)}</span>'
            f'<span class="dash-sig-sym">{_esc(sig.inst.symbol)}</span>'
        )

    return (
        f'<div class="dash-signal {sev_cls}">'
        '<div class="dash-sig-top">'
        f"{head}"
        f'<span class="dash-sig-sev {sev_cls}">{_esc(sig.severity_label)}</span>'
        "</div>"
        f'<div class="dash-sig-title">{_esc(sig.title)}</div>'
        + (f'<div class="dash-sig-detail">{_esc(sig.detail)}{link_html}</div>'
           if sig.detail or link_html else "")
        + (f'<div class="dash-sig-tags">{tags_html}</div>' if tags_html else "")
        + news_html
        + "</div>"
    )


def render_signal_summary(counts: dict, total: int) -> str:
    """심각도별 개수 요약 줄."""
    if not total:
        return (
            '<div class="dash-sig-empty">'
            "감지된 변화가 없습니다. 새 공시도, 임박한 실적도, 비정상 등락도 없습니다."
            "</div>"
        )
    bits = []
    for sev, label, cls in ((3, "지금", "now"), (2, "이번 주", "week"), (1, "참고", "fyi")):
        n = counts.get(str(sev), 0)
        if n:
            bits.append(f'<span class="dash-sig-chip {cls}">{label} {n}</span>')
    return f'<div class="dash-sig-summary">{"".join(bits)}</div>'


def render_analysis_index(instruments: list, docs: dict) -> str:
    """어떤 종목이 어떤 분석을 갖고 있는지 한 줄 요약 그리드."""
    from analysis_store import KINDS

    chips: list[str] = []
    for inst in instruments:
        doc = docs.get(inst.analysis_key)
        marks: list[str] = []
        for kind, label, _desc in KINDS:
            has = doc is not None and kind in doc.html
            cls = "on" if has else "off"
            marks.append(f'<span class="dash-kindmark {cls}" title="{_esc(label)}">'
                         f'{_esc(label[:2])}</span>')
        stale = ' <span class="dash-kindmark stale" title="오래됨">!</span>' if (
            doc is not None and doc.is_stale
        ) else ""
        chips.append(
            '<div class="dash-chip">'
            f'<span class="dash-chip-name">{_esc(inst.name)}</span>'
            f'<span class="dash-chip-marks">{"".join(marks)}{stale}</span>'
            "</div>"
        )
    return f'<div class="dash-chiprow">{"".join(chips)}</div>'


def render_analysis_header(inst, doc) -> str:
    """선택한 종목의 분석 메타 정보."""
    url = inst.resolved_link()
    name = _esc(doc.name or inst.name)

    bits: list[str] = []
    if doc.generated:
        age = doc.age_days
        age_text = f" ({age}일 전)" if age is not None else ""
        bits.append(f"생성 {_esc(doc.generated)}{age_text}")
    if doc.mode:
        label = {"web": "웹검색 기반", "filing": "공시 원문 기반"}.get(doc.mode, doc.mode)
        bits.append(_esc(label))
    if not doc.html:
        bits.append("분석 미생성")

    meta = " · ".join(bits) if bits else "분석 미생성"
    link_html = (
        f' <a class="dash-inline-link" href="{_esc(url)}" target="_blank" '
        f'rel="noopener noreferrer">시세 페이지 ↗</a>'
        if url
        else ""
    )
    note = f'<div class="dash-note">{_esc(doc.note)}</div>' if doc.note else ""

    return (
        '<div class="dash-analysis-head">'
        f'<span class="dash-analysis-name">{name}</span>'
        f'<span class="dash-analysis-meta">{meta}{link_html}</span>'
        f"{note}"
        "</div>"
    )


def render_analysis_body(body_html: str) -> str:
    """스킬이 만든 HTML 을 감싸서 넣습니다.

    body_html 은 Claude 스킬이 생성한 신뢰 가능한 로컬 파일 내용이므로
    이스케이프하지 않고 넣습니다. 대신 스타일 격리를 위해 래퍼로 감쌉니다.
    외부에서 받은 HTML 을 여기 넣지 마십시오.
    """
    return f'<div class="dash-analysis-body">{body_html}</div>'


def render_analysis_missing(label: str, command: str, key: str, kind: str) -> str:
    """분석이 없을 때의 안내.

    위의 '분석 실행' 버튼이 1순위 경로이고, 이 안내는 claude CLI 를 쓸 수 없을 때의
    수동 대안입니다.
    """
    return (
        '<div class="dash-missing">'
        f'<div class="dash-missing-title">{_esc(label)} 미생성</div>'
        '<div class="dash-missing-body">'
        "위의 <b>분석 실행</b> 버튼을 누르면 Claude Code 가 백그라운드에서 스킬을 "
        "돌려 이 자리를 채웁니다.<br>"
        "claude CLI 를 쓸 수 없는 환경이라면, Claude 대화창에 아래를 입력하고 "
        "받은 HTML 을 지정 경로에 직접 저장해도 됩니다."
        "</div>"
        f'<div class="dash-missing-cmd">{_esc(command)}</div>'
        '<div class="dash-missing-body">저장 경로</div>'
        f'<div class="dash-missing-cmd">analysis/{_esc(key)}/{_esc(kind)}.html</div>'
        "</div>"
    )


def render_analysis_sources(sources: list[str]) -> str:
    items = "".join(
        f'<li><a class="dash-inline-link" href="{_esc(s)}" target="_blank" '
        f'rel="noopener noreferrer">{_esc(s)}</a></li>'
        for s in sources
    )
    return f'<div class="dash-footnote">참고 소스<ul class="dash-srclist">{items}</ul></div>'


_FORMATTERS = {
    "num2": lambda v: fmt_num(v, 2),
    "pct": lambda v: fmt_pct(v * 100 if v is not None else None, 2, signed=False),
    "bigusd": fmt_big_usd,
}


def render_valuation_table(
    columns: tuple[tuple[str, str], ...],
    fields: tuple[tuple[str, str, str], ...],
    rows: dict[str, dict],
) -> str:
    """지표를 행, 종목을 열로 놓은 표를 만듭니다.

    columns 는 (표시이름, 야후심볼) 쌍입니다. 지표 수가 종목 수보다 많으므로
    전치(transpose)해서 세로로 길게 놓는 쪽이 읽기 쉽습니다.
    """
    header = "".join(
        f'<th title="{_esc(sym)}">{_esc(label)}<br>'
        f'<span class="dash-th-sym">{_esc(sym)}</span></th>'
        for label, sym in columns
    )
    body_rows: list[str] = []

    for yahoo_key, label, kind in fields:
        formatter = _FORMATTERS.get(kind, lambda v: fmt_num(v))
        cells: list[str] = []
        for _label, sym in columns:
            row = rows.get(sym) or {}
            value = row.get(yahoo_key)
            if value is None:
                cells.append('<td class="na">—</td>')
            else:
                cells.append(f"<td>{_esc(formatter(value))}</td>")
        body_rows.append(f"<tr><td>{_esc(label)}</td>{''.join(cells)}</tr>")

    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        f"<thead><tr><th>지표</th>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 매크로 지표
# ──────────────────────────────────────────────────────────────────────────────

def render_macro_spark(history: list[tuple[str, float]], *,
                       width: int = 208, height: int = 30) -> str:
    """스파크라인 — 좌표를 계산해서 SVG 로 그립니다.

    0 선을 함께 그립니다. 전년대비 증감률 계열에서는 0 을 지나는 지점이
    사이클 전환이므로, 0 선 없이는 그래프가 의미를 잃습니다.
    """
    values = [v for _d, v in history]
    if len(values) < 3:
        return ""

    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - 1.0, hi + 1.0
    # 0 이 범위 안에 들어오면 함께 보이게 넓힙니다
    if lo > 0:
        lo = 0.0
    elif hi < 0:
        hi = 0.0
    span = hi - lo

    pad = 2.0
    inner_h = height - pad * 2
    step = width / (len(values) - 1)

    def y_of(value: float) -> float:
        return pad + inner_h * (1.0 - (value - lo) / span)

    points = " ".join(
        f"{i * step:.1f},{y_of(v):.1f}" for i, v in enumerate(values))
    last_x, last_y = (len(values) - 1) * step, y_of(values[-1])

    zero_line = ""
    if lo <= 0.0 <= hi:
        zy = y_of(0.0)
        zero_line = (
            f'<line x1="0" y1="{zy:.1f}" x2="{width}" y2="{zy:.1f}" '
            'stroke="var(--dash-border)" stroke-width="1" '
            'stroke-dasharray="2 2"/>'
        )

    return (
        f'<svg class="dash-macro-spark" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="최근 {len(values)}개 관측치 추이">'
        f"{zero_line}"
        f'<polyline points="{points}" fill="none" '
        'stroke="var(--dash-ink-2)" stroke-width="1.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.4" '
        'fill="var(--dash-ink)"/>'
        "</svg>"
    )


def _tag_label(key: str) -> str:
    """재무 계정의 내부 이름을 화면 표기로 (국내 쪽은 이미 한국어라 그대로)."""
    try:
        import buffett  # noqa: PLC0415
        return buffett.tag_label(key)
    except Exception:  # noqa: BLE001
        return key


def render_macro_card(reading, *, hit: bool = False, show_why: bool = True) -> str:
    """지표 한 칸. hit=True 면 임계값을 건드린 상태입니다."""
    spec = reading.spec

    head = (
        '<div class="dash-macro-name">'
        f"<span>{_esc(spec.name)}</span>"
        f'<span class="dash-macro-id">{_esc(spec.series_id)}</span>'
        "</div>"
    )

    if not reading.ok:
        return (
            f'<div class="dash-macro">{head}'
            f'<div class="dash-macro-err">{_esc(reading.error)}</div>'
            "</div>"
        )

    # 방향은 기호로만 — 색으로 좋고 나쁨을 암시하지 않습니다
    arrow = ""
    if reading.delta is not None and reading.delta != 0:
        arrow = f"{'▲' if reading.delta > 0 else '▼'} {_esc(reading.delta_label)}"

    meta = [_esc(reading.period_label)]
    if reading.stale:
        meta.append('<span class="late">발표 지연</span>')
    else:
        meta.append(_esc(reading.cadence_label))
    if reading.live_label:
        meta.insert(0, f"<b>{_esc(reading.live_label)}</b>")
    if not spec.verified:
        meta.append("계열 미검증")

    why = ""
    if show_why and spec.why:
        why = f'<div class="dash-macro-why">{_safe_inline(spec.why)}</div>'

    warn = ""
    if reading.warning:
        warn = f'<div class="dash-macro-why">{_safe_inline(reading.warning)}</div>'

    return (
        f'<div class="dash-macro{" hit" if hit else ""}">{head}'
        f'<div class="dash-macro-value">{_esc(reading.value_label)}'
        f'<span class="dash-macro-dir">{arrow}</span></div>'
        f'<div class="dash-macro-meta">{" · ".join(meta)}</div>'
        f"{render_macro_spark(reading.history)}"
        f"{why}{warn}</div>"
    )


def render_macro_group(title: str, subtitle: str, readings: list,
                       hit_keys: set[str], *, show_why: bool = True) -> str:
    """한 그룹의 지표들."""
    if not readings:
        return ""
    cards = "".join(
        render_macro_card(r, hit=r.spec.key in hit_keys, show_why=show_why)
        for r in readings
    )
    return (
        f'<div class="dash-macro-group">{_esc(title)}'
        f'<span class="sub">{_esc(subtitle)}</span></div>'
        f'<div class="dash-macro-grid">{cards}</div>'
    )


def render_macro_trigger(trigger, prompt: str = "", headlines=()) -> str:
    """임계값을 건드린 지표 한 건 — 변화 감지 탭의 신호 카드와 같은 모양.

    헤드라인은 **카드 안에** 넣습니다. 전에는 app.py 가 카드와 헤드라인을
    따로 st.markdown 으로 그렸고, 스트림릿이 그 둘 사이에 자기 컨테이너
    여백을 끼워 넣어서 카드 아래에 정체불명의 박스가 하나 더 떠 있는
    것처럼 보였습니다. CSS 음수 마진으로 끌어올리는 건 스트림릿 버전에
    따라 어긋나므로, 애초에 한 덩어리로 그립니다.
    """
    r = trigger.reading
    spec = r.spec
    sev_class = {3: "now", 2: "soon", 1: "fyi"}.get(trigger.severity, "fyi")
    sev_label = {3: "지금", 2: "이번 주", 1: "참고"}.get(trigger.severity, "")

    chips = "".join(
        f'<span class="dash-sigtag">{_esc(t)}</span>'
        for t in (spec.series_id, _MACRO_RULE_LABEL.get(trigger.rule, trigger.rule))
    )

    prompt_block = ""
    if prompt:
        prompt_block = (
            '<details><summary class="dash-sig-detail" style="cursor:pointer">'
            "Claude 에 붙여넣을 질문</summary>"
            f'<div class="dash-missing-cmd">{_esc(prompt)}</div></details>'
        )

    return (
        '<div class="dash-signal">'
        '<div class="dash-sig-top">'
        f'<span class="dash-sig-chip {sev_class}">{_esc(sev_label)}</span>'
        f'<span class="dash-sig-title">{_esc(trigger.title)}</span>'
        "</div>"
        f'<div class="dash-sig-detail">{_esc(trigger.detail)}</div>'
        f'<div class="dash-sig-tags">{chips}</div>'
        f"{prompt_block}"
        f"{render_news_block(headlines)}"
        "</div>"
    )


_MACRO_RULE_LABEL = {
    "level_above": "기준 상회",
    "level_below": "기준 하회",
    "change": "급변",
    "sign_flip": "부호 전환",
    "yoy_flip": "증감률 전환",
    "vs_mean": "평균 대비 이탈",
}


# ──────────────────────────────────────────────────────────────────────────────
# 버핏식 스크리너
# ──────────────────────────────────────────────────────────────────────────────

_MARK = {"pass": "○", "fail": "✗", "unknown": "?"}


def render_check(check, *, show_source: bool = False) -> str:
    """기준 하나의 판정."""
    crit = check.criterion
    prov = crit.provenance
    label = {"verbatim": "버핏 원문", "practice": "인용 관행",
             "mine": "제 기준"}.get(prov, prov)
    badge = (f'<span class="dash-prov {_esc(prov)}">{_esc(label)}</span>'
             if prov == "verbatim" or show_source else "")

    detail = f'<div class="dash-check-detail">{_safe_inline(check.detail)}</div>'
    warn = (f'<div class="dash-check-warn">⚠ {_safe_inline(check.warning)}</div>'
            if check.warning else "")
    source = ""
    if show_source:
        source = (
            f'<div class="dash-check-detail"><b>출처</b> — {_safe_inline(crit.source)}'
            + (f'<br><b>한계</b> — {_safe_inline(crit.caveat)}' if crit.caveat else "")
            + "</div>"
        )

    return (
        f'<div class="dash-check {_esc(check.verdict)}">'
        f'<span class="mk">{_MARK.get(check.verdict, "?")}</span>'
        f'<span class="nm">{_esc(crit.name)}{badge}</span>'
        f'<span class="vl">{_esc(check.value_label)}</span>'
        f"{detail}{warn}{source}</div>"
    )


def render_screen(screen, *, show_source: bool = False,
                  prompt: str = "") -> str:
    """한 기업의 스크리닝 결과."""
    head = (
        '<div class="dash-screen-top">'
        f'<span class="dash-screen-tkr">{_esc(screen.ticker)}</span>'
        f'<span class="dash-screen-name">{_esc(screen.name)}</span>'
    )

    if not screen.ok:
        return (
            f'<div class="dash-screen">{head}</div>'
            f'<div class="dash-screen-err">{_safe_inline(screen.error)}</div></div>'
        )

    unk = (f'<span class="unk"> · 판정 불가 {screen.unknown_count}</span>'
           if screen.unknown_count else "")
    head += (
        f'<span class="dash-screen-score">{_esc(screen.score_label)}'
        f'<span class="unk"> 통과 · {screen.year_count}년치</span>{unk}</span>'
        "</div>"
    )

    checks = "".join(render_check(c, show_source=show_source)
                     for c in screen.checks)

    missing = ""
    if screen.missing_tags:
        missing = (
            '<div class="dash-screen-err">공시에서 못 찾은 계정: '
            + _esc(", ".join(_tag_label(t) for t in screen.missing_tags))
            + "</div>"
        )

    prompt_block = ""
    if prompt:
        prompt_block = (
            '<details><summary class="dash-check-detail" '
            'style="cursor:pointer;margin-top:8px">'
            "숫자로 안 걸러지는 것 — Claude 에 붙여넣을 질문</summary>"
            f'<div class="dash-missing-cmd">{_esc(prompt)}</div></details>'
        )

    return (
        f'<div class="dash-screen">{head}'
        f'<div class="dash-screen-checks">{checks}</div>'
        f"{missing}{prompt_block}</div>"
    )


def render_criteria_table(rows, *, title: str = "", intro: str = "",
                          foot: str = "") -> str:
    """기준표 — 이름 · 통과 조건(숫자) · 출처. rows: [{short|title, name, rule, label}]

    기준이 화면에 숫자로 적혀 있지 않으면 '통과' 가 무슨 뜻인지 알 수
    없습니다. 조건은 판정 코드가 쓰는 값에서 만들어 넘깁니다.
    """
    if not rows:
        return ""
    body = []
    for i, r in enumerate(rows, 1):
        label = r.get("label") or ""
        chip = f'<span class="cr-src">{_esc(label)}</span>' if label else ""
        name = r.get("name") or ""
        tip = f' title="{_esc(name)}"' if name else ""
        body.append(
            f'<tr><td class="cr-n">{i}</td>'
            f'<td class="cr-name"{tip}><b>{_esc(r.get("short") or r.get("title") or "")}</b></td>'
            f'<td class="cr-rule">{_safe_inline(r.get("rule") or "")}{chip}</td></tr>')
    head = (f'<div class="cr-title">{_esc(title)}</div>' if title else "")
    intro_html = f'<div class="cr-intro">{_safe_inline(intro)}</div>' if intro else ""
    foot_html = f'<div class="cr-foot">{_safe_inline(foot)}</div>' if foot else ""
    return (f'<div class="dash-criteria">{head}{intro_html}'
            '<table class="cr-table"><thead><tr><th></th><th>기준</th>'
            "<th>통과 조건</th></tr></thead><tbody>"
            + "".join(body) + f"</tbody></table>{foot_html}</div>")


#: 이 글자 수(태그 제외)를 넘는 설명은 두 줄만 보이고 누르면 펼쳐집니다.
CLAMP_CHARS = 64
_TAG_RE = re.compile(r"<[^>]+>")


def clamp(inner_html: str, *, limit: int = CLAMP_CHARS, one: bool = False) -> str:
    """긴 설명을 두 줄(one 이면 한 줄)만 보이게 — 누르면 전부 펼쳐집니다.

    2026-11-12 사용자: "폰에서 글자가 너무 많아 보기가 힘들다 — 접을 수 있게".
    글은 지우지 않습니다. 접힌 상태에서도 앞 두 줄은 그대로 읽히므로, 출처와
    기준 시각은 **글의 맨 앞**에 두면 접어도 보입니다. 짧은 글은 그대로 둡니다.
    inner_html 은 이미 안전하게 만든 HTML 입니다.
    """
    if len(_TAG_RE.sub("", inner_html)) <= limit:
        return inner_html
    return (f'<details class="dash-clamp{" one" if one else ""}">'
            f'<summary><span class="t">{inner_html}</span></summary></details>')


def render_legend(html: str) -> str:
    """표·차트를 읽는 데 꼭 필요한 한 줄 (기호 풀이 · 분류 건수).

    render_footnote 는 '설명 문구 표시' 가 꺼져 있으면(기본) 숨겨집니다.
    기호의 뜻이나 분류 결과처럼 **없으면 표를 못 읽는 글**은 이쪽으로 냅니다.
    길면 두 줄만 보이고 누르면 펼쳐집니다 (clamp).
    """
    return f'<div class="dash-legend">{clamp(_safe_inline(html))}</div>' if html else ""


def render_terms(terms) -> str:
    """낱말 풀이 한 묶음 — [(낱말, 뜻)]."""
    if not terms:
        return ""
    return ('<div class="dash-terms">' + "".join(
        f'<div><b>{_esc(k)}</b>{_esc(v)}</div>' for k, v in terms) + "</div>")


def render_screen_table(screens, criteria, *, held=(), sectors: dict | None = None,
                        rank_from: int | None = None, extra_heads: tuple = (),
                        extra: dict | None = None) -> str:
    """전체 요약 표 — 어느 기업이 어느 기준에서 걸렸나 한눈에.

    held 에 든 티커는 ★, sectors({티커: 업종})를 주면 업종 칸을 더합니다.
    rank_from 을 주면 종목 이름 앞에 그 숫자부터 순위를 달고, 통과 칸에 순위의
    근거('판정 8 중 8')를 작게 적습니다 — 접어 둔 나머지 표는 이어지는 숫자로.

    extra_heads 와 extra({티커: [(값, 보조 줄), …]})를 주면 통과 칸 뒤에 칸을
    더합니다 — 깔때기의 '요구 성장률' · '차트' (funnel.py).

    좁은 화면에서는 한 줄이 카드 한 장이 되는데, 기준 9칸을 다 세우면 종목당
    12줄이라 20종목만 돼도 끝없이 내려야 했습니다. 그래서 **걸린 기준만**
    한 줄로 적은 칸('걸린 기준')을 따로 두고, 좁은 화면에서는 9칸 대신 그 한
    줄을 보입니다 (theme.build_stack_rules). 넓은 화면에서는 그 칸을 숨깁니다.
    """
    if not screens:
        return ""
    import buffett as _bf  # noqa: PLC0415

    # 기준 이름이 길어서 열마다 폭이 들쭉날쭉했고, 표시(○·×)가 제목과
    # 어긋나 보였습니다. 제목과 표시를 모두 가운데로 맞춥니다.
    header = "".join(
        f"<th class='mk' title='{_esc(c.name)}'>{_esc(_bf.SHORT_NAMES.get(c.key, c.name))}</th>"
        for c in criteria)
    rows = []
    n = (rank_from or 1) - 1
    for s in screens:
        if not s.ok:
            continue
        n += 1
        cells = []
        for check in s.checks:
            cls = {"pass": "mk", "fail": "mk na", "unknown": "mk na"}[check.verdict]
            cells.append(f'<td class="{cls}">{_MARK[check.verdict]}</td>')
        nm = getattr(s, "name", "") or ""
        star = '<i class="ct-star" title="내 관심종목">★</i>' if s.ticker in held else ""
        sect = (f'<td class="sc-sect">{_esc((sectors or {}).get(s.ticker, ""))}</td>'
                if sectors else "")
        rk = f'<i class="sc-rk">{n}</i>' if rank_from else ""
        sub = (f"<span class='sc-sub'>{_esc(s.judged_label)}</span>" if rank_from else "")
        miss = " · ".join(
            f"{_MARK[c.verdict]} {_esc(_bf.SHORT_NAMES.get(c.criterion.key, c.criterion.name))}"
            for c in s.checks if c.verdict != "pass") or "전부 통과"
        # 국내 종목은 6자리 코드라 이름이 앞(크게), 코드가 뒤(작게) — 2026-11-13 폰:
        # "기업명 대신 기업번호가 더 크게 뜸". 미국은 티커가 이름 구실을 해서 그대로.
        if s.ticker.isdigit() and nm:
            first, second = nm[:22], s.ticker
        else:
            first, second = s.ticker, nm[:22]
        rows.append(
            f"<tr><td title='{_esc(nm)}'>{rk}{star}{_esc(first)}"
            f"<span class='sc-name'>{_esc(second)}</span></td>{sect}"
            f'<td class="">{_esc(s.score_label)}{sub}</td>'
            + "".join(
                f'<td class="sc-x">{_esc(v)}'
                + (f"<span class='sc-sub'>{_esc(note)}</span>" if note else "") + "</td>"
                for v, note in ((extra or {}).get(s.ticker)
                                or [("—", "")] * len(extra_heads))[:len(extra_heads)])
            + f'<td class="sc-miss">{miss}</td>'
            + "".join(cells) + "</tr>"
        )
    if not rows:
        return ""
    sect_h = "<th>업종</th>" if sectors else ""
    return (
        '<div class="dash-table-wrap"><table class="dash-table dash-sctable">'
        f"<thead><tr><th>종목</th>{sect_h}<th>통과</th>"
        + "".join(f"<th>{_esc(h)}</th>" for h in extra_heads)
        + f"<th class='sc-miss'>걸린 기준</th>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_sector_pass(usable, passed, sectors: dict, label=lambda x: x) -> str:
    """업종별로 몇 종목 중 몇 종목이 통과했나 — 통과율 순의 칩 한 줄.

    어느 업종이 구조적으로 잘 통과하고(필수소비재) 어느 업종이 거의 못
    통과하는지(유틸리티 · 부동산) 보여 줍니다. 기준이 업종을 가린다는 사실을
    숨기지 않으려는 것입니다.
    """
    total: dict[str, int] = {}
    ok: dict[str, int] = {}
    for s in usable:
        k = sectors.get(s.ticker) or ""
        total[k] = total.get(k, 0) + 1
    for s in passed:
        k = sectors.get(s.ticker) or ""
        ok[k] = ok.get(k, 0) + 1
    if not total:
        return ""
    order = sorted(total, key=lambda k: (-(ok.get(k, 0) / total[k]), k))
    chips = "".join(
        f'<span><b>{_esc(label(k) if k else "분류 없음")}</b> {ok.get(k, 0)}/{total[k]}</span>'
        for k in order)
    return f'<div class="dash-sectpass"><em>업종별 통과</em>{chips}</div>'


# ──────────────────────────────────────────────────────────────────────────────
# 가격 판독 + 판단 재료
# ──────────────────────────────────────────────────────────────────────────────

def render_dcf_cells(result) -> str:
    """역DCF 숫자 칸들."""
    if not result.ok:
        return (f'<div class="dash-screen-err">{_safe_inline(result.error)}</div>'
                if result.error else "")

    cells = [
        ("요구 성장률 (할인율 10%)", result.growth_label),
        ("할인율 8~12% 구간", result.band_label),
    ]
    # 과거 성장률 — 판단 요약(verdict) · 종목 발굴 깔때기와 같은 값을 보입니다:
    # 6년치 이상이면 앞 3년 평균 → 뒤 3년 평균, 아니면 시작 해 · 끝 해 두 점.
    import funnel as _fn  # noqa: PLC0415

    hist, span = _fn.trend_growth(result.inputs.fcf_history)
    label = "실제 (앞·뒤 3년 평균)"
    if span is None:
        span, label = result.gap_span, "실제"
        hist = result.historical_cagr[span] if span is not None else None
    if hist is not None:
        cells.append((f"과거 {span}년 {label}", f"연 {hist * 100:,.1f}%"))
        if result.implied_growth is not None:
            cells.append(("격차", f"{(result.implied_growth - hist) * 100:+,.1f}%p"))
    if result.fcf_base is not None:
        label = "기준 FCF" + (" (3년 평균)" if result.normalized else "")
        cells.append((label, f"{result.fcf_base / 1e9:,.1f}B"))

    inner = "".join(
        f'<div class="dash-dcf-cell"><span class="lb">{_esc(lb)}</span>'
        f'<span class="vl">{_esc(vl)}</span></div>'
        for lb, vl in cells
    )
    return f'<div class="dash-dcf-grid">{inner}</div>'


def render_more(summary: str, inner_html: str, *, cls: str = "") -> str:
    """'자세히' 로 접어 두는 칸 — 눌러야 펼쳐집니다. 내용은 지우지 않고 접기만 합니다.

    2026-11-12 폰 확인 "밸류에이션 탭이 너무 복잡하다": 종목 하나가 폰 두 화면을
    넘었습니다. 판정과 근거만 먼저 보이고 나머지는 이 칸 안에 둡니다.
    inner_html 은 이미 만들어진 HTML 입니다 (여기서 다시 바꾸지 않습니다).
    """
    if not inner_html:
        return ""
    return (f'<details class="dash-more {cls}"><summary>{_esc(summary)}</summary>'
            f'<div class="dash-more-body">{inner_html}</div></details>')


def render_verdict(v, *, prompt: str = "", show_next: bool = True,
                   show_name: bool = False) -> str:
    """판단 재료 — 사분면 위치와 다음에 확인할 것. 결론은 쓰지 않습니다.

    먼저 보이는 것은 위치 · 판정 줄 · 근거 · 주의 문구뿐이고, 긴 글(판단 요약 ·
    다음에 확인할 것 · Claude 질문)은 '자세히' 안에 접혀 있습니다.
    show_name 이면 맨 위에 종목 이름을 적습니다 (접는 제목이 따로 없는 화면용).
    """
    from verdict import QUADRANT_MEANING, QUADRANT_TITLE, summary_lines

    cls = f"q{v.quadrant}" if v.quadrant in (1, 2, 3) else ""
    lines = summary_lines(v)
    # summary_lines 의 마지막 두 줄은 위치·의미이므로 머리에 따로 씁니다
    body = lines[:-2]

    body_html = "".join(
        f'<div class="dash-verdict-line">{_md_bold(ln)}</div>' for ln in body)

    cav = ""
    if v.caveats:
        cav = ('<div class="dash-verdict-cav">'
               + "".join(f"<div>⚠ {_md_bold(c)}</div>" for c in v.caveats)
               + "</div>")

    nxt = ""
    if show_next and v.next_checks:
        items = "".join(f"<li>{_esc(c)}</li>" for c in v.next_checks)
        nxt = (f'<div class="dash-verdict-next"><b>다음에 확인할 것</b>'
               f"<ol>{items}</ol></div>")

    prompt_block = ""
    if prompt:
        prompt_block = (
            '<details><summary class="dash-verdict-line" '
            'style="cursor:pointer;margin-top:7px">'
            "<b>Claude 에 붙여넣을 질문</b> — 숫자와 한계를 모두 담았습니다"
            "</summary>"
            f'<div class="dash-missing-cmd">{_esc(prompt)}</div></details>'
        )

    name = ""
    if show_name:
        nm = getattr(v, "name", "") or ""
        name = (f'<div class="dash-verdict-tkr">{_esc(v.ticker)}'
                + (f"<span>{_esc(nm[:30])}</span>" if nm and nm != v.ticker else "") + "</div>")
    more = render_more(
        "자세히 — 판단 요약 · 다음에 확인할 것 · Claude 질문",
        f'<div class="dash-verdict-line">{_md_bold(QUADRANT_MEANING[v.quadrant])}</div>'
        f"{body_html}{nxt}{prompt_block}")
    return (
        f'<div class="dash-verdict {cls}">{name}'
        f'<div class="dash-verdict-pos">{_esc(QUADRANT_TITLE[v.quadrant])}</div>'
        f"{_verdict_head(v)}{cav}{more}</div>"
    )


def _eps_chip_html(v) -> str:
    """선행 EPS 상승세 — 판정 줄의 **맨 앞** (사용자 지정 2026-11-12). 없으면 그리지 않습니다."""
    import funnel as _fn  # noqa: PLC0415

    f = getattr(v, "eps", None)
    text = _fn.eps_chip(f)
    if not text:
        return ""
    c = f["c90"]
    cls = "e-up" if c >= _fn.EPS_FLAT else ("e-down" if c <= -_fn.EPS_FLAT else "")
    return f'<span class="vc ve {cls}" title="향후 12개월 EPS 추정 · 야후">{_esc(text)}</span>'


def _verdict_head(v) -> str:
    """카드 맨 위 — 품질 · 가격 판정과 그 근거 한 줄 (늘 보입니다)."""
    state = getattr(v, "price_state", "na")
    moved = getattr(v, "moved_reason", "")
    return (
        '<div class="dash-vhead">'
        + _eps_chip_html(v)
        + f'<span class="vc">품질 {_esc(v.passed)}/{_esc(v.total)}</span>'
        f'<span class="vc p-{_esc(state)}">가격 {_esc(v.price_word)}</span>'
        f'<span class="vr">{_esc(v.price_reason)}</span>'
        + (f'<span class="vr vm">{_esc(moved)}</span>' if moved else "")
        + "</div>")


def _md_bold(text: str) -> str:
    """**굵게** 만 허용하는 최소 마크다운. 나머지는 전부 이스케이프합니다."""
    parts = _esc(text).split("**")
    out = []
    for i, part in enumerate(parts):
        out.append(f"<b>{part}</b>" if i % 2 == 1 else part)
    return "".join(out)


def render_quadrant_map(verdicts, *, href_fn=None) -> str:
    """사분면 지도 — 어느 종목이 어디 있나.

    href_fn(티커) → 주소를 주면 종목 이름이 그 종목 칸으로 가는 링크가 됩니다.
    """
    if not verdicts:
        return ""
    buckets: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: [], 0: []}
    href_by = {}
    for v in verdicts:
        label = verdict_name(v)
        buckets[v.quadrant].append(label)
        href_by[label] = v.ticker

    # 표가 아니라 2×2 칸입니다. 2026-11-12 폰 화면: 표는 좁은 화면에서 줄마다 카드로
    # 세워져 '지도' 가 아니게 되고, 합친 칸('판정 안 함')에는 엉뚱한 머리글
    # ('가격 부담 낮음')이 붙었습니다. 칸마다 제목을 직접 적습니다.
    def cell(q: int, title: str, cls: str = "") -> str:
        names = buckets.get(q) or []

        def one(n: str) -> str:
            if href_fn is None:
                return _esc(n)
            return (f'<a class="qk" href="{_esc(href_fn(href_by.get(n, n)))}" '
                    f'target="_self">{_esc(n)}</a>')

        body = ", ".join(one(n) for n in names) if names else "—"
        return (f'<div class="qc {cls}"><span class="qt">{title}</span>'
                f'<span class="qn">{len(names)}</span><span class="qv">{body}</span></div>')

    return (
        '<div class="dash-qmap">'
        + cell(1, "① 품질 통과 · 가격 부담 낮음", "q1")
        + cell(2, "② 품질 통과 · 가격 경계 · 높음")
        + cell(3, "③ 품질 미달 · 가격 부담 낮음")
        + cell(4, "④ 품질 미달 · 가격 경계 · 높음")
        + cell(0, "가격 판정 안 함 (역DCF 불가 · 금융업)", "wide")
        + "</div>"
        + render_rule_change(verdicts)
    )


_QUAD_MARK = {0: "판정 안 함", 1: "①", 2: "②", 3: "③", 4: "④"}
#: 누르는 칸의 짧은 표시 (판정 안 함은 '–')
QUAD_SHORT = {0: "–", 1: "①", 2: "②", 3: "③", 4: "④"}


def verdict_name(v) -> str:
    """화면에 적을 종목 이름 — 국내 종목(6자리 코드)은 **회사 이름**, 나머지는 티커.

    2026-11-13 폰 확인: 사분면 지도에 국내 종목이 '005930' 같은 번호로 나왔습니다.
    """
    ticker = str(getattr(v, "ticker", "") or "")
    name = str(getattr(v, "name", "") or "")
    if ticker.isdigit() and name and name != ticker:
        return name
    return ticker


def render_rule_change(verdicts, *, limit: int = 15) -> str:
    """가격 규칙을 바꾼 뒤(2026-11-12) 사분면이 달라진 종목 한 줄.

    예전 규칙의 위치를 계산해 둔 종목(prev_quadrant ≥ 0)만 봅니다. 하나도
    계산돼 있지 않으면 아무것도 그리지 않습니다.
    """
    known = [v for v in verdicts if getattr(v, "prev_quadrant", -1) >= 0]
    if not known:
        return ""
    moved = [v for v in known if v.prev_quadrant != v.quadrant]
    if not moved:
        body = "위치가 바뀐 종목이 없습니다"
    else:
        body = " · ".join(
            f"<b>{_esc(verdict_name(v))}</b> {_QUAD_MARK[v.prev_quadrant]} → {_QUAD_MARK[v.quadrant]}"
            for v in moved[:limit])
        if len(moved) > limit:
            body += f" 외 {len(moved) - limit}종목"
    return render_legend(
        f"<b>가격 규칙 변경(11/12)의 영향</b> — {len(known)}종목 중 {len(moved)}종목: {body}. "
        "바뀐 규칙: 할인율 8~12% 전 구간 · 과거 성장률은 앞 · 뒤 3년 평균(연 15% 까지) · "
        "주식보상비용 차감 · 금융업 판정 안 함")


# ──────────────────────────────────────────────────────────────────────────────
# 괴리율 — 계산 사슬을 한 화면에
# ──────────────────────────────────────────────────────────────────────────────

def _chain_step(label: str, value: str, sub: str = "",
                cls: str = "") -> str:
    sub_html = f'<span class="sub">{_esc(sub)}</span>' if sub else ""
    return (
        f'<div class="dash-chain-step {cls}">'
        f'<span class="lb">{_esc(label)}</span>'
        f'<span class="vl">{_esc(value)}</span>{sub_html}</div>'
    )


def _chain_op(symbol: str) -> str:
    return f'<div class="dash-chain-step op">{_esc(symbol)}</div>'


def render_premium_pair(row, *, fx=None) -> str:
    """해외 종목 한 줄 — 계산 사슬 전체.

        해외가 × 환율 ÷ 환산주수 = 본주환산가  vs  실제 본주가  →  괴리율

    두 탭으로 나뉘어 있을 때는 이 사슬이 안 보였습니다. 숫자 하나가 비면
    어디서 끊겼는지도 바로 보입니다.
    """
    inst = row.foreign
    fq = row.foreign_quote

    tags = [inst.symbol]
    if inst.exchange:
        tags.append(inst.exchange)
    if row.uses_extended and fq is not None and fq.extended_label:
        tags.append(fq.extended_label)
    tag_html = "".join(f'<span class="dash-pair-tag">{_esc(t)}</span>'
                       for t in tags)

    prem_html = ""
    if row.ok:
        pct = row.premium.premium_pct
        prem_html = (
            f'<span class="dash-pair-prem {direction_class(pct)}">'
            f"{direction_glyph(pct)}{fmt_pct(pct)}</span>"
        )

    head = (
        '<div class="dash-pair-top">'
        f'<span class="dash-pair-name">{_esc(inst.name)}</span>'
        f"{tag_html}{prem_html}</div>"
    )

    # ── 사슬 ────────────────────────────────────────────────────────────────
    fp = row.foreign_price
    cur = (fq.currency if fq and fq.ok and fq.currency else inst.currency) or ""
    steps = [
        _chain_step(
            "해외가" + (" (시간외)" if row.uses_extended else ""),
            fmt_num(fp, inst.decimals) if fp is not None else "—",
            cur,
        ),
        _chain_op("×"),
        _chain_step(
            f"{cur}/KRW",
            fmt_num(row.fx_rate, 2) if row.fx_rate else "—",
        ),
        _chain_op("÷"),
        _chain_step(
            "환산주수",
            (f"{row.shares_per_unit:g}" if row.shares_per_unit else "—"),
            "1단위당 본주",
        ),
        _chain_op("="),
        _chain_step(
            "본주환산가",
            (f"{fmt_num(row.premium.implied_krw, 0)}원" if row.ok else "—"),
            cls="out",
        ),
    ]

    if row.local is not None:
        lq = row.local_quote
        local_price = lq.price if lq and lq.ok and lq.price else None
        local_pct = lq.change_pct if lq and lq.ok else None
        steps += [
            _chain_op("vs"),
            _chain_step(
                f"{row.local.name} ({row.local.symbol})",
                (f"{fmt_num(local_price, 0)}원" if local_price else "—"),
                (f"{direction_glyph(local_pct)}{fmt_pct(local_pct)}"
                 if local_pct is not None else ""),
                cls="out",
            ),
        ]

    chain = f'<div class="dash-chain">{"".join(steps)}</div>'

    notes: list[str] = []
    if row.blocked:
        notes.append(f"<b>괴리율 계산 불가</b> — {_esc(row.blocked)}")
    if inst.note:
        notes.append(_esc(inst.note))
    note_html = (f'<div class="dash-pair-note">{" · ".join(notes)}</div>'
                 if notes else "")

    link = ""
    if inst.resolved_link():
        link = (
            f'<div class="dash-pair-note">'
            f'<a class="dash-inline-link" href="{_esc(inst.resolved_link())}" '
            f'target="_blank" rel="noopener noreferrer">{_esc(inst.symbol)} 시세 보기</a>'
            "</div>"
        )

    return f'<div class="dash-pair">{head}{chain}{note_html}{link}</div>'


def render_live_badge(label: str, state: str = "", detail: str = "") -> str:
    """실시간 상태 표시. state: on(갱신 중) / frozen(고정) / 빈값(미정)."""
    cls = f"dash-live {state}".strip()
    text = label + (f" · {detail}" if detail else "")
    return f'<span class="{cls}"><span class="dot"></span>{_esc(text)}</span>'


# ──────────────────────────────────────────────────────────────────────────────
# 종목 발굴 — 52주 위치
# ──────────────────────────────────────────────────────────────────────────────

def render_discover_map(groups: dict) -> str:
    """52주 위치 × 품질 사분면 지도."""
    def cell(q: int) -> str:
        names = [p.ticker for p in groups.get(q) or []]
        if not names:
            return "<td>—</td>"
        shown = ", ".join(_esc(n) for n in names[:12])
        if len(names) > 12:
            shown += f" <span class=\"dash-news-meta\">외 {len(names) - 12}</span>"
        return f"<td>{shown}</td>"

    mid = groups.get(0) or []
    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th></th><th>52주 고가권</th><th>52주 저가권</th></tr></thead>"
        "<tbody>"
        f"<tr><td>품질 기준 통과</td>{cell(1)}{cell(3)}</tr>"
        f"<tr><td>품질 기준 미달</td>{cell(2)}{cell(4)}</tr>"
        f'<tr><td>중간 구간 · 판정 없음</td><td colspan="2">'
        f'{", ".join(_esc(p.ticker) for p in mid[:16]) or "—"}'
        f'{f" 외 {len(mid) - 16}" if len(mid) > 16 else ""}</td></tr>'
        "</tbody></table></div>"
    )


def render_discover_table(positions: list, quality_threshold: int) -> str:
    """52주 위치 표."""
    if not positions:
        return ""
    rows = []
    for pos in positions:
        quality = "—"
        if pos.has_quality:
            mark = "○" if pos.quality_passed >= quality_threshold else "✗"
            if pos.quality_unknown and pos.quality_passed == 0:
                mark = "?"
            quality = f"{mark} {pos.quality_label}"
        band = pos.band_position
        rows.append(
            "<tr>"
            f"<td>{_esc(pos.ticker)}</td>"
            f"<td>{_esc(pos.name[:18])}</td>"
            f"<td>{fmt_num(pos.price, 0 if pos.currency == 'KRW' else 2)}</td>"
            f"<td>{pos.pct_of_high:,.1f}%</td>"
            f"<td>{band:,.0f}%</td>"
            f"<td>{pos.upside_from_low_pct:+,.1f}%</td>"
            f'<td class="{"" if pos.has_quality else "na"}">{_esc(quality)}</td>'
            "</tr>"
        )
    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th>티커</th><th>종목</th><th>현재가</th>"
        "<th>고가 대비</th><th>구간 위치</th><th>저가 대비</th>"
        "<th>품질</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_discover_card(pos, quality_threshold: int, *,
                         prompt: str = "") -> str:
    """주목 구간 종목 하나."""
    from discover import QUADRANT_MEANING, QUADRANT_TITLE

    quad = pos.quadrant(quality_threshold)
    cls = f"q{quad}" if quad in (1, 2, 3) else ""

    tags = []
    if pos.is_breakout:
        tags.append("52주 신고가")
    elif pos.is_near_high:
        tags.append("고가권")
    if pos.is_new_low:
        tags.append("52주 신저가")
    elif pos.is_near_low:
        tags.append("저가권")
    if pos.has_quality:
        tags.append(f"품질 {pos.quality_label}")
    tag_html = "".join(f'<span class="dash-pair-tag">{_esc(t)}</span>'
                       for t in tags)

    cells = [
        ("현재가", fmt_num(pos.price, 0 if pos.currency == "KRW" else 2)),
        ("52주 고가 대비", f"{pos.pct_of_high:,.1f}%"),
        ("구간 위치", f"{pos.band_position:,.0f}%"),
        ("저가 대비", f"{pos.upside_from_low_pct:+,.1f}%"),
    ]
    grid = "".join(
        f'<div class="dash-dcf-cell"><span class="lb">{_esc(lb)}</span>'
        f'<span class="vl">{_esc(vl)}</span></div>'
        for lb, vl in cells
    )

    prompt_block = ""
    if prompt:
        prompt_block = (
            '<details><summary class="dash-verdict-line" '
            'style="cursor:pointer;margin-top:7px">'
            "<b>Claude 에 붙여넣을 질문</b></summary>"
            f'<div class="dash-missing-cmd">{_esc(prompt)}</div></details>'
        )

    return (
        f'<div class="dash-verdict {cls}">'
        '<div class="dash-pair-top">'
        f'<span class="dash-pair-name">{_esc(pos.ticker)}</span>'
        f'<span class="dash-screen-name">{_esc(pos.name)}</span>{tag_html}</div>'
        f'<div class="dash-verdict-pos">{_esc(QUADRANT_TITLE[quad])}</div>'
        f'<div class="dash-verdict-line">{_md_bold(QUADRANT_MEANING[quad])}</div>'
        f'<div class="dash-dcf-grid">{grid}</div>'
        f"{prompt_block}</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 공포탐욕지수
# ──────────────────────────────────────────────────────────────────────────────

def render_feargreed_gauge(fg, *, width: int = 420, height: int = 46) -> str:
    """0~100 눈금 + 현재 위치. 구간 경계를 함께 그립니다.

    숫자만 보면 70 이 높은지 알 수 없으므로, CNN 의 구간 경계(25·45·55·75)를
    눈금으로 찍어 위치를 보이게 합니다.
    """
    if fg.score is None:
        return ""

    from sources.feargreed import BANDS

    pad = 10
    track_y = 20
    inner = width - pad * 2

    parts = [
        f'<svg class="dash-fg-gauge" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="공포탐욕지수 {fg.score:.0f} ({fg.band})">',
        f'<line x1="{pad}" y1="{track_y}" x2="{width - pad}" y2="{track_y}" '
        'stroke="var(--dash-border)" stroke-width="5" stroke-linecap="round"/>',
    ]

    for limit, _label in BANDS[:-1]:
        x = pad + inner * limit / 100.0
        parts.append(
            f'<line x1="{x:.1f}" y1="{track_y - 7}" x2="{x:.1f}" '
            f'y2="{track_y + 7}" stroke="var(--dash-border)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{track_y + 19}" text-anchor="middle" '
            f'font-size="8" fill="var(--dash-ink-muted)">{limit:.0f}</text>'
        )

    cx = pad + inner * min(max(fg.score, 0.0), 100.0) / 100.0
    parts.append(
        f'<circle cx="{cx:.1f}" cy="{track_y}" r="6.5" '
        'fill="var(--dash-ink)" stroke="var(--dash-surface)" stroke-width="2"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_feargreed(fg, *, show_components: bool = True) -> str:
    """공포탐욕지수 블록."""
    if not fg.ok:
        return (
            '<div class="dash-fg">'
            '<div class="dash-fg-top"><span class="dash-fg-band">'
            "공포탐욕지수</span></div>"
            f'<div class="dash-macro-err">{_esc(fg.error)}</div></div>'
        )

    deltas = []
    if fg.change_1w is not None:
        deltas.append(f"1주 전 대비 {fg.change_1w:+.0f}")
    if fg.change_1m is not None:
        deltas.append(f"1개월 전 대비 {fg.change_1m:+.0f}")
    if fg.previous_year is not None:
        deltas.append(f"1년 전 {fg.previous_year:.0f}")
    meta = []
    if fg.observed_at is not None:
        meta.append(fg.observed_at.isoformat())
    if fg.lag_days:
        meta.append(f"{fg.lag_days}일 전")

    head = (
        '<div class="dash-fg-top">'
        f'<span class="dash-fg-score">{_esc(fg.score_label)}</span>'
        f'<span class="dash-fg-band">{_esc(fg.band)}</span>'
        f'<span class="dash-fg-delta">{_esc(" · ".join(deltas))}'
        + (f'<br>{_esc(" · ".join(meta))}' if meta else "")
        + "</span></div>"
    )

    comps = ""
    if show_components and fg.components:
        cells = []
        for comp in fg.components:
            extreme = (comp.score is not None
                       and (comp.score < 25.0 or comp.score >= 75.0))
            cells.append(
                f'<div class="dash-fg-comp{" extreme" if extreme else ""}">'
                f'<span class="nm">{_esc(comp.label)}</span>'
                f'<span class="sc">{"—" if comp.score is None else f"{comp.score:,.0f}"}</span> '
                f'<span class="bd">{_esc(comp.band)}</span>'
                f'<span class="ds">{_esc(comp.desc)}</span></div>'
            )
        comps = f'<div class="dash-fg-comps">{"".join(cells)}</div>'

    return (
        f'<div class="dash-fg">{head}'
        f"{render_feargreed_gauge(fg)}{comps}</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# VIX 기간구조
# ──────────────────────────────────────────────────────────────────────────────

def render_vix_curve(state, *, width: int = 520, height: int = 128) -> str:
    """만기별 변동성 곡선. 모양이 콘탱고인지 역전인지 한눈에 보이게 그립니다.

    숫자 네 개를 표로 보면 모양이 안 보입니다. 곡선의 **기울기**가 신호이므로
    선으로 잇고, 수평 점선(현재 VIX)을 깔아 뒤가 위/아래인지 바로 읽히게
    했습니다.
    """
    pts = [p for p in state.points if p.ok]
    if len(pts) < 2:
        return ""

    values = [p.value for p in pts]
    low, high = min(values), max(values)
    span = max(high - low, 1.0)
    y_min, y_max = low - span * 0.45, high + span * 0.35

    pad_l, pad_r, pad_t, pad_b = 14, 14, 20, 30
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b

    def y_of(v: float) -> float:
        return pad_t + ph * (y_max - v) / (y_max - y_min)

    xs = [pad_l + pw * i / max(len(pts) - 1, 1) for i in range(len(pts))]
    stroke = "var(--dash-up)" if state.is_inverted else "var(--dash-ink)"

    parts = [
        f'<svg class="dash-vix-curve" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="VIX 기간구조 {_esc(state.structure)}">'
    ]

    spot = state.spot
    if spot is not None:
        sy = y_of(spot)
        parts.append(
            f'<line x1="{pad_l}" y1="{sy:.1f}" x2="{width - pad_r}" '
            f'y2="{sy:.1f}" stroke="var(--dash-border)" stroke-width="1" '
            'stroke-dasharray="4 3"/>'
        )

    poly = " ".join(f"{x:.1f},{y_of(p.value):.1f}" for x, p in zip(xs, pts))
    parts.append(
        f'<polyline points="{poly}" fill="none" stroke="{stroke}" '
        'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    for x, p in zip(xs, pts):
        yy = y_of(p.value)
        is_spot = p.label == "VIX"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="{4.5 if is_spot else 3.2}" '
            f'fill="{stroke}"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{yy - 9:.1f}" text-anchor="middle" '
            f'font-size="10.5" font-weight="{650 if is_spot else 500}" '
            f'fill="{stroke}">{p.value:,.1f}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - pad_b + 14:.1f}" '
            'text-anchor="middle" font-size="9" '
            f'fill="var(--dash-ink-muted)">{_esc(p.label)}</text>'
        )
        if not p.verified:
            parts.append(
                f'<text x="{x:.1f}" y="{height - pad_b + 24:.1f}" '
                'text-anchor="middle" font-size="7.5" '
                'fill="var(--dash-ink-muted)">미검증</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def render_vix(state) -> str:
    """VIX 기간구조 + 백분위 블록."""
    if not state.ok:
        return (
            '<div class="dash-vix"><div class="dash-vix-top">'
            '<span class="dash-vix-struct">VIX 기간구조</span></div>'
            f'<div class="dash-macro-err">{_esc(state.error)}</div></div>'
        )

    inv = " inverted" if state.is_inverted else ""
    ivts = state.ivts
    pct_bits = []
    if state.pct_5y is not None:
        pct_bits.append(f"5년 중 {state.pct_5y:,.0f}% 지점")
    if state.pct_1y is not None:
        pct_bits.append(f"1년 중 {state.pct_1y:,.0f}%")
    if ivts is not None:
        pct_bits.append(f"VIX÷VIX3M {ivts:.3f}")

    head = (
        '<div class="dash-vix-top">'
        f'<span class="dash-vix-spot">{state.spot:,.2f}</span>'
        f'<span class="dash-vix-struct{inv}">{_esc(state.structure)}</span>'
        f'<span class="dash-vix-pct">{_esc(" · ".join(pct_bits))}</span>'
        "</div>"
    )

    from sources.vix import reading_lines

    lines = "".join(f"<div>{_md_bold(ln)}</div>" for ln in reading_lines(state))
    warn = ""
    if state.warnings:
        warn = ('<div class="dash-macro-why">'
                + "".join(f"<div>⚠ {_esc(w)}</div>" for w in state.warnings)
                + "</div>")

    return (
        f'<div class="dash-vix{inv}">{head}'
        f"{render_vix_curve(state)}"
        f'<div class="dash-vix-lines">{lines}</div>{warn}</div>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# 요약 — 휴대폰 10초 화면
# ──────────────────────────────────────────────────────────────────────────────

def render_summary_band(summary) -> str:
    """맨 위 한 줄. 이것만 보고 앱을 닫을 수 있어야 합니다."""
    attention = summary.attention_count
    cls = " attention" if attention else ""
    sub = (f"확인할 항목 {attention}건" if attention
           else "네 가지를 다 봤고 올라온 것이 없습니다")
    return (
        f'<div class="dash-verdict-band{cls}">'
        f'<div class="vb-main">{_esc(summary.verdict)}</div>'
        f'<div class="vb-sub">{_esc(sub)}</div></div>'
    )


def render_summary_row(row) -> str:
    """요약 한 줄."""
    from summary import LEVEL_LABEL

    goto = (f'<div class="dash-srow-goto">→ {_esc(row.goto)} 탭</div>'
            if row.goto else "")
    detail = (f'<div class="dash-srow-detail">{clamp(_esc(row.detail))}</div>'
              if row.detail else "")
    return (
        f'<div class="dash-srow {_esc(row.level)}">'
        f'<span class="dash-srow-chip">'
        f'{_esc(LEVEL_LABEL.get(row.level, row.level))}</span>'
        "<div>"
        f'<span class="dash-srow-title">{_esc(row.title)}</span>'
        f'<div class="dash-srow-head">{_esc(row.headline)}</div>'
        f"{detail}{goto}</div></div>"
    )


def render_summary(summary) -> str:
    """판정 한 줄 + **두 칸 상태판**. 전에는 같은 모양 카드가 세로로 네 장
    쌓여 있어서 무엇이 급한지가 위치로 드러나지 않았습니다. 이제 확인할
    것(alert·watch)이 앞에 오고, 조용한 칸은 흐리게 둡니다."""
    order = {"alert": 0, "watch": 1}
    rows = sorted(summary.rows, key=lambda r: order.get(r.level, 2))
    return (
        render_summary_band(summary)
        + '<div class="dash-sgrid">'
        + "".join(render_summary_row(r) for r in rows)
        + "</div>"
    )


def render_sector_bars(rows, n: int = 4) -> str:
    """섹터 온도 요약 — 기준선 대비 1개월, 강한 n개 · 약한 n개를 막대로.

    0 을 가운데 둔 **양방향 막대**입니다. 숫자 열만 있으면 크기 비교가
    눈에 안 들어옵니다. 막대 길이는 이 묶음의 최댓값 기준이라 다른 날과
    길이를 비교하면 안 됩니다 — 그래서 숫자를 막대 끝에 같이 적습니다.
    """
    usable = [r for r in rows or [] if getattr(r, "ok", False)
              and not getattr(r, "benchmark", False) and r.rel_1m is not None]
    if not usable:
        return ""
    usable.sort(key=lambda r: -r.rel_1m)
    pick = usable[:n] + [r for r in usable[-n:] if r not in usable[:n]]
    top = max(abs(r.rel_1m) for r in pick) or 1.0
    lines = []
    for r in pick:
        w = abs(r.rel_1m) / top * 50.0
        cls = direction_class(r.rel_1m)
        side = (f'left:50%;width:{w:.1f}%' if r.rel_1m >= 0
                else f'left:{50 - w:.1f}%;width:{w:.1f}%')
        lines.append(
            f'<div class="sb-row"><div class="sb-name">{_esc(r.label)}</div>'
            f'<div class="sb-track"><div class="sb-zero"></div>'
            f'<div class="sb-bar {cls}" style="{side}"></div></div>'
            f'<div class="sb-val {cls}">{r.rel_1m:+.1f}%p</div></div>')
    return ('<div class="dash-sbars"><div class="sb-head">섹터 온도 · 1개월, '
            'KODEX 200 대비</div>' + "".join(lines) + "</div>")


# ──────────────────────────────────────────────────────────────────────────────
# 데모 표시 — 가짜 숫자를 가짜라고 말해주는 장치
# ──────────────────────────────────────────────────────────────────────────────

def render_demo_banner(*, preview: bool = False) -> str:
    """데모 데이터임을 화면 맨 위에 알립니다.

    **왜 필요한가:** 데모 숫자를 그럴듯하게 만들어서(공포탐욕 63, VIX 16.4,
    삼성전자 DIO) 실제 값과 구분할 방법이 없었습니다. 숫자가 안 맞는다고
    느끼는 게 정상인데, 그게 데모인지 버그인지 알 수 없는 상태였습니다.
    """
    where = "이 프리뷰는" if preview else "데모 모드입니다 —"
    extra = (
        "실제 데이터로 보시려면 압축을 풀고 <code>streamlit run app.py</code> "
        "를 실행한 뒤 화면 위쪽 <b>표시</b> 패널에서 데모 모드를 끄십시오."
        if preview else
        "화면 위쪽 표시 패널에서 데모 모드를 끄면 실제 데이터를 받아옵니다."
    )
    return (
        '<div class="dash-demo-banner">'
        '<div class="db-title">⚠ 지금 보이는 숫자는 전부 가짜입니다</div>'
        f'<div class="db-body">{where} <b>오프라인 데모 데이터</b>로 만들어졌습니다. '
        "공포탐욕지수·VIX·주가·재고·재무 — <b>어느 것도 실제 값이 아니고</b>, "
        "레이아웃과 계산 경로를 확인하기 위한 고정값입니다. "
        f"{extra}</div></div>"
    )


def demo_tag(use_demo: bool) -> str:
    """섹션 제목 옆에 붙이는 작은 표시."""
    return '<span class="dash-demo-tag">데모</span>' if use_demo else ""


# ──────────────────────────────────────────────────────────────────────────────
# 증시 브리핑
# ──────────────────────────────────────────────────────────────────────────────

def render_briefing_head(bf) -> str:
    """브리핑 제목·날짜·오래됨 경고. 본문은 st.markdown 이 따로 그립니다.

    본문을 여기서 그리지 않는 이유: 마크다운은 st.markdown 이 렌더해야 하고,
    여기서 HTML 로 만들면 마크다운이 글자 그대로 나옵니다.
    """
    stale = ""
    if bf.is_stale:
        stale = (
            '<span class="dash-bf-stale">'
            f'{_esc(bf.age_label)} 글입니다 — 지금 시장을 설명하지 못할 수 있습니다'
            "</span>"
        )
    src = ""
    if bf.sources:
        links = " · ".join(
            f'<a class="dash-inline-link" href="{_esc(u)}" target="_blank" '
            f'rel="noopener noreferrer">출처 {i}</a>'
            for i, u in enumerate(bf.sources[:6], start=1)
        )
        src = f'<div class="dash-bf-src">{links}</div>'

    warn = ""
    if bf.warnings:
        warn = (f'<div class="dash-screen-err">'
                f'{_esc(" · ".join(bf.warnings))}</div>')

    return (
        '<div class="dash-bf">'
        f'<div class="dash-bf-top">'
        f'<span class="dash-bf-title">{_esc(bf.title or "제목 없음")}</span>'
        f'<span class="dash-bf-date">{_esc(bf.date)} · {_esc(bf.age_label)}</span>'
        f"</div>{stale}{src}{warn}</div>"
    )


def render_briefing_line(bf) -> str:
    """요약 탭 한 줄. 제목과 날짜만 — 요약은 임계값을 건드린 것만 올리는
    화면이라, 매일 있는 브리핑을 길게 넣으면 항상 차 있게 됩니다."""
    if bf is None:
        return ""
    tag = "오래됨" if bf.is_stale else bf.age_label
    return (
        '<div class="dash-bf-line">'
        '<span class="dash-bf-line-tag">아침 브리핑</span>'
        f'<span class="dash-bf-line-title">{_esc(bf.short_title)}</span>'
        f'<span class="dash-bf-line-date">{_esc(tag)}</span>'
        "</div>"
    )


def render_briefing_empty(template: str) -> str:
    """브리핑이 아직 없을 때. 넣는 방법을 그 자리에서 알려줍니다."""
    return (
        '<div class="dash-bf">'
        '<div class="dash-bf-top"><span class="dash-bf-title">'
        "증시 브리핑이 없습니다</span></div>"
        '<div class="dash-bf-src">다른 대화에서 쓴 브리핑을 아래 형식으로 '
        "저장하면 이 자리에 올라옵니다.</div>"
        f'<div class="dash-missing-cmd">{_esc(template)}</div>'
        "</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 가격 조건
# ──────────────────────────────────────────────────────────────────────────────

def render_price_block(price, *, show_source: bool = False,
                       metrics_meta=()) -> str:
    """가격 조건 판정 + 표시 전용 지표.

    질 조건(render_screen)과 **점수를 합치지 않습니다.** 다른 축이라 합치면
    질이 나쁜데 싼 종목과 질이 좋은데 비싼 종목이 같은 점수가 됩니다.
    """
    if price is None or not price.ok:
        msg = getattr(price, "error", "") or "가격 조건을 판정할 수 없습니다."
        return f'<div class="dash-screen-err">{_safe_inline(msg)}</div>'

    unk = (f'<span class="unk"> · 판정 불가 {price.unknown_count}</span>'
           if price.unknown_count else "")
    head = (
        '<div class="dash-price-top">'
        '<span class="dash-price-label">가격 조건</span>'
        f'<span class="dash-screen-score">{_esc(price.score_label)}'
        f'<span class="unk"> 통과</span>{unk}</span>'
        f'<span class="dash-price-basis">기준선 근거: {_esc(price.yield_basis)}</span>'
        "</div>"
    )

    checks = "".join(render_check(c, show_source=show_source)
                     for c in price.checks)

    cells = ""
    for key, label, note in metrics_meta:
        val = price.metrics.get(key)
        shown = "—" if val is None else f"{val:.2f}"
        tip = (f'<div class="dash-check-detail">{_safe_inline(note)}</div>'
               if show_source else "")
        cells += (
            '<div class="dash-price-metric">'
            f'<span class="dash-price-metric-label">{_esc(label)}</span>'
            f'<span class="dash-price-metric-val">{shown}</span>{tip}'
            "</div>"
        )
    metrics_block = ""
    if cells:
        metrics_block = (
            '<div class="dash-price-metrics">'
            '<span class="dash-price-metrics-head">점수에 넣지 않는 참고 지표</span>'
            f"{cells}</div>"
        )

    return (f'<div class="dash-pricecond">{head}'
            f'<div class="dash-screen-checks">{checks}</div>'
            f"{metrics_block}</div>")


# ──────────────────────────────────────────────────────────────────────────────
# 잠정실적 레이더
# ──────────────────────────────────────────────────────────────────────────────

def render_prelim_radar(filings, *, errors=None) -> str:
    """잠정실적 공시 목록. 숫자는 담지 않고 '떴다' 와 링크만 줍니다.

    공정공시 본문 표는 회사·분기마다 형식이 달라서, 파싱해 조용히 틀린
    숫자를 보여주는 것보다 열어보게 하는 쪽이 안전합니다.
    """
    err_block = ""
    if errors:
        err_block = (
            '<div class="dash-screen-err">'
            + _esc(" · ".join(f"{k}: {v[:70]}" for k, v in errors.items()))
            + "</div>"
        )

    if not filings:
        return (
            '<div class="dash-prelim">'
            '<div class="dash-prelim-empty">최근 잠정실적 공시가 없습니다. '
            '분기 종료 후 2~4주 사이에 올라옵니다.</div>'
            f"{err_block}</div>"
        )

    rows = ""
    for f in filings:
        fresh = "" if f.is_fresh else ' <span class="unk">(지난 분기)</span>'
        link = (
            f'<a class="dash-inline-link" href="{_esc(f.url)}" target="_blank" '
            'rel="noopener noreferrer">DART 에서 열기</a>'
        ) if f.url.startswith(("http://", "https://")) else ""
        rows += (
            '<div class="dash-prelim-row">'
            f'<span class="dash-prelim-date">{_esc(f.date_iso)}</span>'
            f'<span class="dash-prelim-corp">{_esc(f.corp_name)}</span>'
            f'<span class="dash-prelim-nm">{_esc(f.report_nm)}{fresh}</span>'
            f'<span class="dash-prelim-age">{_esc(f.age_label)}</span>'
            f'<span class="dash-prelim-link">{link}</span>'
            "</div>"
        )
    return f'<div class="dash-prelim">{rows}{err_block}</div>'

def render_kr_exports(res, *, error: str = "") -> str:
    """한국 반도체 수출 — 메모리 사이클의 선행 지표.

    실패를 숨기지 않습니다. 이 경로는 검증되지 않았으므로 **막혔다는 사실
    자체가 정보**입니다 — 빈 칸으로 두면 수출이 0인 줄 압니다.
    """
    if res is None or not getattr(res, "ok", False):
        why = error or " · ".join(getattr(res, "warnings", []) or []) \
            or "데이터를 받지 못했습니다."
        return (
            '<div class="dash-exp dash-exp-fail">'
            '<span class="dash-exp-label">한국 반도체 수출</span>'
            f'<span class="dash-exp-why">받아오지 못했습니다 — {_esc(why[:160])}</span>'
            '<span class="dash-exp-why">화면 위쪽 <b>진단</b> 패널의 '
            '<b>반도체 수출 확인</b> 버튼으로 원인을 볼 수 있습니다. '
            '이 경로는 아직 검증되지 않았습니다.</span>'
            "</div>"
        )

    yoy = res.yoy_pct
    arrow = "" if yoy is None else ("▲" if yoy > 0 else ("▼" if yoy < 0 else "—"))
    cls = "" if yoy is None else ("up" if yoy > 0 else ("down" if yoy < 0 else ""))
    amount = ("—" if res.value_100m_usd is None
              else f"{res.value_100m_usd:,.1f}억 $")
    yoy_txt = "—" if yoy is None else f"{arrow} {abs(yoy):,.1f}%"

    stale = ""
    age = res.age_months
    if age is not None and age >= 2:
        stale = (f'<span class="dash-exp-why">{age}개월 전 자료입니다 — '
                 "새 보도자료가 아직 안 올라왔거나 긁기가 실패했을 수 있습니다."
                 "</span>")

    link = ""
    if str(res.source_url).startswith(("http://", "https://")):
        link = (f'<a class="dash-inline-link" href="{_esc(res.source_url)}" '
                'target="_blank" rel="noopener noreferrer">보도자료</a>')

    warn = ""
    if res.warnings:
        warn = (f'<span class="dash-exp-why">{_esc(" · ".join(res.warnings))}'
                "</span>")

    return (
        '<div class="dash-exp">'
        '<div class="dash-exp-top">'
        '<span class="dash-exp-label">한국 반도체 수출</span>'
        f'<span class="dash-exp-period">{_esc(res.period)}</span>'
        f'<span class="dash-exp-link">{link}</span>'
        "</div>"
        '<div class="dash-exp-nums">'
        f'<span class="dash-exp-amt">{_esc(amount)}</span>'
        f'<span class="dash-exp-yoy {cls}">{_esc(yoy_txt)}'
        '<span class="unk"> 전년동월비</span></span>'
        "</div>"
        f"{stale}{warn}</div>"
    )


def render_brief(lines, headline_text: str, as_of_text: str) -> str:
    """증시 브리핑. 카드가 아니라 **읽는 글**로 보이게 합니다.

    외부 사이트로 보내는 링크가 아니라, 이 대시보드가 가진 숫자를 문장으로
    엮은 것입니다. 카드는 조회용이고 이건 통독용입니다.
    """
    if not lines:
        body = ('<div class="dash-brief-line">'
                f'<span class="dash-brief-text">{_esc(headline_text)}</span>'
                "</div>")
    else:
        body = ""
        for ln in lines:
            cls = ("hot" if ln.severity >= 3
                   else ("warm" if ln.severity >= 2 else ""))
            body += (
                f'<div class="dash-brief-line {cls}">'
                f'<span class="dash-brief-topic">{_esc(ln.topic)}</span>'
                f'<span class="dash-brief-text">{_safe_inline(ln.text)}</span>'
                "</div>"
            )
    return (
        '<div class="dash-brief">'
        '<div class="dash-brief-top">'
        f'<span class="dash-brief-head">{_esc(headline_text)}</span>'
        f'<span class="dash-brief-asof">{_esc(as_of_text)}</span>'
        "</div>"
        f"{body}</div>"
    )



def render_build_warning(rep) -> str:
    """파일 버전 불일치 경고. 앱 맨 위에 띄웁니다.

    Streamlit Cloud 는 오류 본문을 가려서("redacted to prevent data leaks")
    AttributeError 만 보이고 어느 파일이 문제인지 알 수 없습니다. 그래서
    **죽기 전에** 파일 이름을 말해 주는 것이 이 블록의 목적입니다.
    """
    if rep is None or rep.ok:
        return ""
    msg = rep.message()
    if not msg:
        return ""
    cls = "dash-build-warn" if rep.checked else "dash-build-note"
    files = ""
    hints = rep.hints() if hasattr(rep, "hints") else list(rep.problem_files)
    if hints:
        # 파일마다 한 줄 — 예전엔 <code> 를 붙여 써서 복사하면
        # '.streamlit/config.tomlsources/fred.py' 처럼 이어졌습니다.
        files = ('<ul class="dash-build-files">'
                 + "".join(f"<li>{_esc(h)}</li>" for h in hints)
                 + "</ul>")
    return (f'<div class="{cls}">{_md_bold(_esc(msg))}{files}</div>')


# ──────────────────────────────────────────────────────────────────────────────
# 국내 스크리너
# ──────────────────────────────────────────────────────────────────────────────

def render_screener_head(title: str, rule: str, count: int,
                         caveat: str = "") -> str:
    """스크리너 한 묶음의 머리 — **기준을 제목 옆에 적습니다.**

    기준이 화면에 없으면 몇 주 뒤에 "이게 왜 걸렸지" 를 되묻게 됩니다.
    """
    cav = (f'<div class="dash-scr-caveat">{clamp(_safe_inline(caveat))}</div>'
           if caveat else "")
    return (
        '<div class="dash-scr-head">'
        f'<span class="dash-scr-title">{_esc(title)}</span>'
        f'<span class="dash-scr-rule">{_safe_inline(rule)}</span>'
        f'<span class="dash-section-count">{count}종목</span>'
        "</div>" + cav
    )


def render_hit_metrics(hit) -> str:
    """통과 종목의 지표를 가로 표 한 줄로."""
    if not hit.metrics:
        return ""
    cells = "".join(
        f'<div class="dash-hit-cell">'
        f'<div class="dash-hit-label">{_esc(label)}</div>'
        f'<div class="dash-hit-value">{_esc(value)}</div></div>'
        for label, value in hit.metrics
    )
    return f'<div class="dash-hit-row">{cells}</div>'


def render_hit_reasons(hit) -> str:
    """왜 걸렸는지. 기준과 실제값을 같이 적습니다."""
    if not hit.reasons:
        return ""
    items = "".join(f"<li>{_safe_inline(r)}</li>" for r in hit.reasons)
    return ('<div class="dash-hit-why"><div class="dash-news-head">'
            f"걸린 이유</div><ul>{items}</ul></div>")


def render_company_overview(profile, *, search_name: str = "") -> str:
    """기업개황 표. DART 가 주는 것만 적습니다."""
    if profile is None:
        return render_footnote("기업개황을 불러오지 않았습니다.")
    if getattr(profile, "error", ""):
        return render_footnote(
            f"<b>기업개황을 받지 못했습니다.</b> {_esc(profile.error)}")

    rows = [
        ("대표자", profile.ceo),
        ("설립일", profile.established_ko),
        ("결산월", profile.fiscal_ko),
        ("표준산업분류 코드", profile.industry_code),
        ("본사", profile.address),
    ]
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v) if v else '—'}</td></tr>"
        for k, v in rows
    )
    # DART 공시검색은 종목코드가 아니라 **회사명**으로 찾습니다
    # (textCrpNm). 코드를 넣으면 결과가 비어서 링크가 고장난 것처럼
    # 보입니다.
    link = ""
    if search_name:
        import urllib.parse as _up  # noqa: PLC0415
        q = _up.quote(search_name)
        link = (f'<a class="dash-inline-link" target="_blank" '
                f'rel="noopener noreferrer" '
                f'href="https://dart.fss.or.kr/dsab007/main.do?'
                f'option=corp&textCrpNm={q}">DART 공시 전체 ↗</a>')
    home = ""
    if profile.homepage and profile.homepage.startswith(("http://", "https://")):
        home = (f' · <a class="dash-inline-link" target="_blank" '
                f'rel="noopener noreferrer" href="{_esc(profile.homepage)}">'
                "회사 홈페이지 ↗</a>")
    return (
        '<table class="dash-kv"><tbody>' + body + "</tbody></table>"
        + (f'<div class="dash-hit-links">{link}{home}</div>'
           if (link or home) else "")
        + render_footnote(
            "DART 기업개황(company.json) 그대로입니다. "
            "<b>업종명은 적지 않습니다</b> — DART 는 표준산업분류 "
            "<b>코드</b>만 주고 코드→이름 표는 이 API 에 없습니다. "
            "제가 이름을 붙이면 틀릴 수 있습니다.")
    )


# ──────────────────────────────────────────────────────────────────────────────
# 분석 스킬 딥링크
# ──────────────────────────────────────────────────────────────────────────────
#
# 스트림릿 클라우드에서는 `claude -p` 가 돌지 않습니다. 대신 Claude 앱·웹을
# **프롬프트가 채워진 채로** 여는 공식 딥링크를 씁니다:
#
#   claude://claude.ai/new?q=…   앱(데스크톱·모바일). 설치돼 있으면 앱이 열림
#   https://claude.ai/new?q=…    웹. 앱이 없어도 열림 (휴대폰 브라우저 포함)
#   claude://code/new?q=…        PC 의 Claude Code
#
# 값은 전부 URL 인코딩해야 합니다. q 는 1만 4천 자 근처에서 잘리는데,
# 우리 프롬프트는 100자 미만이라 여유가 많습니다.

APP_LINK = "claude://claude.ai/new?q={q}"
WEB_LINK = "https://claude.ai/new?q={q}"
CODE_LINK = "claude://code/new?q={q}"


def render_skill_links(code: str, name: str) -> str:
    """종목 하나에 대한 3대 분석 딥링크 묶음."""
    import urllib.parse as _up  # noqa: PLC0415

    import analysis_store as _store  # noqa: PLC0415

    rows = []
    for kind, label, desc in _store.KINDS:
        cmd = _store.skill_command(kind, code, name)
        if not cmd:
            continue
        q = _up.quote(cmd, safe="")
        rows.append(
            '<div class="dash-skill-row">'
            f'<div class="dash-skill-name">{_esc(label)}'
            f'<span class="dash-skill-desc">{_esc(desc)}</span></div>'
            '<div class="dash-skill-links">'
            f'<a class="dash-skill-btn" href="{APP_LINK.format(q=q)}">'
            "앱에서 열기</a>"
            f'<a class="dash-skill-btn" target="_blank" '
            f'rel="noopener noreferrer" href="{WEB_LINK.format(q=q)}">'
            "웹에서 열기</a>"
            f'<a class="dash-skill-btn ghost" href="{CODE_LINK.format(q=q)}">'
            "Claude Code</a>"
            "</div></div>"
        )
    if not rows:
        return ""
    return (
        '<div class="dash-skills">' + "".join(rows) + "</div>"
        + render_footnote(
            "<b>앱에서 열기</b>는 휴대폰·PC 모두에서 Claude 앱을 프롬프트가 "
            "채워진 채로 엽니다. 앱이 없으면 <b>웹에서 열기</b>를 쓰십시오. "
            "<b>Claude Code</b>는 PC 에 Claude Code 가 설치돼 있을 때만 "
            "열립니다. 셋 다 <b>보내기 전에 내용을 확인</b>할 수 있습니다.")
    )


# ──────────────────────────────────────────────────────────────────────────────
# 뉴스 · 공시 · 지표
# ──────────────────────────────────────────────────────────────────────────────

_DIR_CLASS = {"재가속": "now", "둔화": "fyi", "비슷": "soon"}


def render_inflation_table(readings: list) -> str:
    """물가 — 지수가 아니라 **속도 세 가지**를 나란히."""
    usable = [r for r in readings if r.ok]
    if not usable:
        return render_footnote(
            "<b>물가 계열을 하나도 받지 못했습니다.</b> FRED 키가 설정돼 "
            "있는지 확인하십시오.")

    def cell(v, suffix="%"):
        return "—" if v is None else f"{v:+.2f}{suffix}"

    rows = "".join(
        "<tr>"
        f"<td class='name'>{_esc(r.label)}</td>"
        f"<td class='num'>{cell(r.mom)}</td>"
        f"<td class='num'>{cell(r.yoy)}</td>"
        f"<td class='num'>{cell(r.saar3)}</td>"
        f"<td><span class='dash-sig-chip "
        f"{_DIR_CLASS.get(r.direction, 'fyi')}'>{_esc(r.direction)}</span></td>"
        f"<td class='meta'>{_esc(r.period)}</td>"
        "</tr>"
        for r in usable
    )
    missing = [r for r in readings if not r.ok]
    note = ""
    if missing:
        note = render_footnote(
            f"<b>못 받은 계열 {len(missing)}개:</b> "
            + " · ".join(f"{_esc(r.label)} ({_esc(r.error[:40])})"
                         for r in missing[:4]))
    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th>지표</th><th class='num'>전월비</th>"
        "<th class='num'>전년동월비</th><th class='num'>3개월 연율</th>"
        "<th>방향</th><th>기준</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>" + note
    )


def fmt_usd_bn(billions: float | None, *, signed: bool = False) -> str:
    """십억 달러 → 한국식 단위.

    '30십억' 은 한국어가 아닙니다. 1십억 달러 = 10억 달러이므로
    조·억으로 바꿔 적습니다.
    """
    if billions is None:
        return "—"
    eok = billions * 10.0                      # 십억 달러 → 억 달러
    sign = "+" if (signed and eok > 0) else ("-" if signed and eok < 0 else "")
    a = abs(eok)
    if a >= 10_000:
        return f"{sign}{a / 10_000:,.2f}조 달러"
    return f"{sign}{a:,.0f}억 달러"


def render_liquidity(nl, extra: list | None = None) -> str:
    """순유동성 + 구성요소."""
    if not nl.ok:
        return render_footnote(
            f"<b>순유동성을 계산하지 않았습니다.</b> {_safe_inline(nl.error)}<br>"
            "부분값으로 '순유동성' 이라고 적으면 틀린 숫자가 됩니다.")

    arrow = "▲" if (nl.change or 0) > 0 else ("▼" if (nl.change or 0) < 0 else "–")
    parts = "".join(
        f'<div class="dash-hit-cell"><div class="dash-hit-label">'
        f'{_esc(p.label)}</div><div class="dash-hit-value">'
        f'{fmt_usd_bn(p.billions)}</div></div>'
        for p in (nl.parts or []) if p.billions is not None
    )
    chg = ("" if nl.change is None
           else f'<span class="dash-exp-delta">{arrow} '
                f'{fmt_usd_bn(abs(nl.change))} (4주)</span>')
    return (
        '<div class="dash-exp">'
        '<div class="dash-exp-top">'
        '<span class="dash-exp-label">연준 순유동성</span>'
        f'<span class="dash-exp-period">{_esc(nl.period)}</span></div>'
        f'<div class="dash-exp-value">{fmt_usd_bn(nl.value)} {chg}</div>'
        f'<div class="dash-hit-row">{parts}</div>'
        "</div>"
        + render_footnote(
            "<b>순유동성 = 연준 총자산 − 역레포 − 재무부 계정.</b> "
            "뒤 둘은 연준 장부에 있지만 <b>시장에 없는 돈</b>이라 뺍니다. "
            "총자산만 보면 2022~23년처럼 자산이 주는데 순유동성은 느는 "
            "구간을 놓칩니다.<br><b>인과가 아니라 배경입니다</b> — 늘었다고 "
            "주가가 오르는 게 아니고, 상관도 구간마다 다릅니다.")
        + (render_simple_rows(extra) if extra else "")
    )


def render_simple_rows(rows: list) -> str:
    """(라벨, 값문자열, 메모) 목록을 간단한 표로."""
    items = [r for r in rows if r]
    if not items:
        return ""
    body = "".join(
        f"<tr><th>{_esc(a)}</th><td>{_esc(b)}</td>"
        f"<td class='meta'>{_esc(c)}</td></tr>"
        for a, b, c in items
    )
    return f'<table class="dash-kv"><tbody>{body}</tbody></table>'


def _news_meta(h) -> str:
    """'매체 · 11/12 · 관련 5곳' — 기사 날짜를 늘 같이 보입니다 (2026-11-13
    '오래된 기사' 점검). '관련 N곳' 은 같은 사건으로 묶인 다른 매체 수 —
    섹터 뉴스 순위에서만 채워집니다 (옛 캐시 객체엔 없을 수 있어 getattr)."""
    pub = getattr(h, "published", "") or ""
    day = f"{pub[5:7]}/{pub[8:10]}" if len(pub) >= 10 else ""
    more = getattr(h, "more", 0) or 0
    extra = f"관련 {more}곳" if more > 0 else ""
    return " · ".join(x for x in (getattr(h, "source", "") or "", day, extra) if x)


def _query_hint(query: str) -> str:
    """'(반도체 OR HBM) (업황 OR 가격)' → '반도체·HBM + 업황·가격' — 폰에서 읽히게."""
    parts: list[str] = []
    bare: list[str] = []           # 괄호 밖 낱말은 띄어 쓴 그대로 한 덩어리
    for grp, word in re.findall(r"\(([^)]*)\)|(\S+)", query or ""):
        if grp:
            if bare:
                parts.append(" ".join(bare))
                bare = []
            parts.append("·".join(w.strip() for w in grp.split(" OR ") if w.strip()))
        elif word and word != "OR":
            bare.append(word)
    if bare:
        parts.append(" ".join(bare))
    return " + ".join(parts)


def render_sector_news(sectors, headlines: dict, errors: dict) -> str:
    """섹터별 뉴스 — 섹터당 몇 줄씩, 한 화면에."""
    blocks = []
    for key, label, query in sectors:
        items = headlines.get(key) or []
        if not items:
            blocks.append(
                '<div class="dash-sector">'
                f'<div class="dash-sector-name">{_esc(label)}</div>'
                '<div class="dash-sector-empty">'
                f'{_esc(errors.get(key) or "헤드라인 없음")}</div></div>')
            continue
        lis = "".join(
            "<li>"
            + (f'<a class="dash-inline-link" href="{_esc(h.url)}" '
               f'target="_blank" rel="noopener noreferrer">{_esc(h.title)}</a>'
               if h.url else _esc(h.title))
            + (f' <span class="dash-news-meta">{_esc(_news_meta(h))}</span>'
               if _news_meta(h) else "")
            + "</li>"
            for h in items
        )
        blocks.append(
            '<div class="dash-sector">'
            f'<div class="dash-sector-name">{_esc(label)}'
            f'<span class="dash-sector-q">{_esc(_query_hint(query))}</span></div>'
            f"<ul>{lis}</ul></div>")
    return f'<div class="dash-sectors">{"".join(blocks)}</div>'


def _filing_type_cell(f) -> str:
    tone = getattr(f, "tone", "neutral") or "neutral"
    sub = getattr(f, "sub", "") or ""
    return (f"<span class='dash-fk dash-fk-{_esc(tone)}'>{_esc(f.kind)}</span>"
            + (f"<span class='dash-fk-sub'>{_esc(sub)}</span>"
               if sub and sub != f.kind else ""))


def render_filing_counts(counts, active=()) -> str:
    """묶음별 건수 + 세부 유형 분해. counts 는 dart.count_filings() 결과."""
    if not counts:
        return ""
    active = set(active or ())
    cells = []
    for group, n, subs in counts:
        tone = _FILING_TONE.get(group, "neutral")
        detail = " · ".join(f"{_esc(s)} {c}" for s, c in subs[:5])
        if len(subs) > 5:
            detail += f" · 외 {sum(c for _s, c in subs[5:])}"
        dim = " dim" if active and group not in active else ""
        cells.append(
            f"<div class='dash-fc dash-fc-{tone}{dim}'>"
            f"<div class='dash-fc-head'><span>{_esc(group)}</span>"
            f"<b>{n}</b></div>"
            f"<div class='dash-fc-sub'>{detail}</div></div>")
    return f"<div class='dash-fc-grid'>{''.join(cells)}</div>"


#: dart.GROUP_TONE 과 같은 값 — components 가 sources 를 import 하지 않게 복사.
_FILING_TONE = {
    "경고": "risk", "실적": "earn", "희석·물량": "dilute",
    "주주환원": "return", "지분·M&A": "owner", "사업·계약": "biz",
    "주식수 변동": "neutral", "일정·IR": "neutral",
}


def render_market_filings(filings: list, error: str = "", *,
                          held=None, scan=None, limit: int = 120) -> str:
    """시장 전체 주요 공시 — 세부 유형·시장·꼬리표까지."""
    if error:
        return render_footnote(f"<b>공시를 받지 못했습니다.</b> {_esc(error)}")
    held = set(held or ())
    gaps = list(getattr(scan, "gaps", None) or [])
    if not filings:
        return render_footnote(
            "<b>조건에 맞는 공시가 없습니다.</b> 전체 공시가 없다는 뜻이 "
            "아니라, 추려내는 유형(실적·증자·자사주·최대주주변경 등)이나 "
            "고른 필터에 해당하는 것이 없다는 뜻입니다."
            + (" " + _esc(" / ".join(gaps)) if gaps else ""))
    shown = filings[:limit]
    rows = []
    for f in shown:
        star = (" <span class='dash-fl-star' title='보유·관심 종목'>★</span>"
                if f.stock_code and f.stock_code in held else "")
        flags = "".join(f"<span class='dash-fl-flag'>{_esc(x)}</span>"
                        for x in getattr(f, "flags", ()) or ())
        filer = getattr(f, "filer", "") or ""
        who = (f"<div class='dash-fl-filer'>제출 {_esc(filer)}</div>"
               if filer and filer != f.corp_name else "")
        title = (f'<a class="dash-inline-link" href="{_esc(f.url)}" '
                 f'target="_blank" rel="noopener noreferrer">{_esc(f.title)}</a>'
                 if f.url else _esc(f.title))
        market = getattr(f, "market", "") or ""
        rows.append(
            "<tr>"
            f"<td class='meta'>{_esc(f.date[5:] if len(f.date) == 10 else f.date)}"
            + (f"<div class='dash-fl-mkt'>{_esc(market)}</div>" if market else "")
            + "</td>"
            f"<td class='dash-fl-type'>{_filing_type_cell(f)}</td>"
            f"<td class='name'>{_esc(f.corp_name)}{star}</td>"
            f"<td>{title}{flags}{who}</td></tr>")
    more = (f"<b>앞의 {limit}건만 보입니다</b> (전체 {len(filings)}건) — "
            "필터로 좁히십시오. " if len(filings) > limit else "")
    gap_txt = ("<b>훑은 범위:</b> " + _esc(" / ".join(gaps)) + ". "
               if gaps else "")
    fb = ("<b>공시 유형 필터가 응답하지 않아 시장별 전체 목록을 몇 쪽만 "
          "봤습니다.</b> " if getattr(scan, "fallback", False) else "")
    return (
        '<div class="dash-table-wrap"><table class="dash-table dash-fl">'
        "<thead><tr><th>날짜</th><th>유형</th><th>회사</th>"
        "<th>보고서</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        + render_footnote(
            more + fb + gap_txt +
            "<b>제목으로 추렸습니다.</b> 주요사항보고·거래소공시·지분공시를 "
            "받아 정해 둔 세부 유형에 맞는 것만 남깁니다. 정기보고서, "
            "임원·주요주주 소유보고(하루 수백 건), 투자주의 지정은 뺐습니다. "
            "<b>놓치는 쪽을 택했으니 빠진 게 있을 수 있습니다</b> — 전체는 "
            "DART 에서 보십시오. '정정' 은 앞서 낸 공시를 고친 것이라 원래 "
            "공시와 함께 봐야 합니다.")
    )


def render_filing_guide(types, groups) -> str:
    """유형별로 '이 공시가 뜨면 무엇을 보나'. types 는 dart.DISCLOSURE_TYPES."""
    blocks = []
    for g in groups:
        items = [t for t in types if t.group == g]
        if not items:
            continue
        tone = _FILING_TONE.get(g, "neutral")
        lis = "".join(
            f"<li><b>{_esc(t.label)}</b> — {_esc(t.why)}</li>" for t in items)
        blocks.append(
            f"<div class='dash-fg'><span class='dash-fk dash-fk-{tone}'>"
            f"{_esc(g)}</span><ul>{lis}</ul></div>")
    return (f"<div class='dash-fg-wrap'>{''.join(blocks)}</div>"
            + render_footnote(
                "좋다·나쁘다를 판정하지 않고 <b>보고서에서 어느 숫자를 "
                "보면 되는지</b>만 적었습니다. 같은 유형이라도 규모와 조건에 "
                "따라 의미가 달라집니다."))


def render_nav_groups(groups) -> str:
    """세로 내비의 묶음 이름을 CSS 로 끼워 넣습니다.

    스트림릿 라디오 안에는 머리말을 넣을 수 없습니다. 그룹마다 라디오를
    따로 두면 선택이 갈려서 '지금 어느 탭인가' 가 흔들립니다. 그래서
    라디오는 하나로 두고, 각 그룹 첫 항목 **앞에** ::before 로 이름을
    붙입니다.

    **범위를 좁히는 게 중요합니다.** 그냥 div[role="radiogroup"] 에 걸면
    아래 '시장' 라디오(3개)에도 '오늘'·'찾기' 가 붙어 버립니다. 바로 앞에
    표식 div 를 하나 두고 :has() 로 **그 다음 위젯만** 집습니다.

    스트림릿이 DOM 을 바꾸거나 :has() 가 없는 브라우저면 **묶음 이름만**
    사라지고 내비는 그대로 돕니다.
    """
    sel = ('div[data-testid="stElementContainer"]:has(.dash-navmark)'
           ' + div[data-testid="stElementContainer"]'
           ' div[role="radiogroup"] > label')
    rules = []
    idx = 1
    for name, items in groups:
        if not items:
            continue
        rules.append(
            f"{sel}:nth-of-type({idx})::before {{"
            f'content: "{_esc(name)}";'
            "display: block; font-size: var(--fs-1); font-weight: 700;"
            "letter-spacing: .06em; color: var(--dash-ink-muted);"
            "margin: 11px 0 3px; padding-left: 2px;"
            "}"
        )
        idx += len(items)
    # 첫 묶음은 위 여백을 줄입니다 — '섹션' 글자 바로 아래라 비어 보입니다
    rules.append(f"{sel}:nth-of-type(1)::before {{ margin-top: 0; }}")
    return ('<div class="dash-navmark"></div><style>'
            + "".join(rules) + "</style>")


# ──────────────────────────────────────────────────────────────────────────────
# 섹터 온도
# ──────────────────────────────────────────────────────────────────────────────

def _heat_cell(value: float | None, scale: float) -> str:
    """수익률 칸. 배경 진하기 = 크기, 색 = 방향.

    color-mix 로 등락 변수에 흰색을 섞습니다. 등락 색 관행(한국/미국)을
    바꾸면 온도 색도 같이 바뀝니다 — 색을 여기서 따로 정하면 두 군데가
    어긋납니다.
    """
    if value is None:
        return '<td class="num heat na">—</td>'
    strength = min(1.0, abs(value) / scale) if scale else 0.0
    pct = round(8 + strength * 50)          # 8%~58% 진하기
    var = "--dash-up" if value > 0 else ("--dash-down" if value < 0
                                         else "--dash-flat")
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "")
    style = (f"background: color-mix(in srgb, var({var}) {pct}%, "
             "var(--dash-surface));")
    # 진한 칸은 글자를 진하게 — 연한 칸에서 굵은 글씨는 소음입니다
    weight = "700" if strength > 0.6 else "600"
    return (f'<td class="num heat" style="{style} font-weight:{weight}">'
            f'<span class="heat-arrow">{arrow}</span>{value:+.1f}%</td>')


def _sparkline(values: list[float], width: int = 96, height: int = 26) -> str:
    """3개월 추이 — 축 없는 작은 선. 시작점 대비 위면 상승색."""
    pts = [v for v in values if v and v > 0]
    if len(pts) < 5:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts) - 1
    coords = " ".join(
        f"{i / n * (width - 2) + 1:.1f},"
        f"{height - 2 - (v - lo) / span * (height - 4):.1f}"
        for i, v in enumerate(pts))
    color = ("var(--dash-up)" if pts[-1] > pts[0]
             else "var(--dash-down)" if pts[-1] < pts[0]
             else "var(--dash-flat)")
    base_y = height - 2 - (pts[0] - lo) / span * (height - 4)
    return (
        f'<svg class="heat-spark" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" aria-hidden="true">'
        f'<line x1="1" x2="{width - 1}" y1="{base_y:.1f}" y2="{base_y:.1f}" '
        'stroke="var(--dash-divider)" stroke-width="1" '
        'stroke-dasharray="2 2"/>'
        f'<polyline points="{coords}" fill="none" stroke="{color}" '
        'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
        "</svg>"
    )


def render_sector_heat(rows: list) -> str:
    """섹터 온도 표. 줄 = 업종, 칸 = 기간별 수익률 + 상대강도 + 추이."""
    import sector_heat as _sh  # noqa: PLC0415

    if not rows:
        return render_footnote("업종 ETF 목록이 비어 있습니다.")
    usable = [r for r in rows if r.ok]
    if not usable:
        return render_footnote(
            "<b>업종 ETF 를 하나도 받지 못했습니다.</b> 야후 파이낸스 연결을 "
            "확인하십시오 — 이 표는 키가 필요 없습니다.")

    head = (
        "<tr><th>업종</th>"
        + "".join(f'<th class="num">{_esc(lab)}</th>'
                  for _k, lab, _n in _sh.PERIODS)
        + '<th class="num" title="KODEX 200 대비 1개월 초과수익">'
          "200 대비</th>"
        + '<th class="num">52주 위치</th>'
        + "<th>3개월 추이</th></tr>"
    )
    body = []
    for r in rows:
        name_flag = ""
        if r.name_ok is False:
            name_flag = (f' <span class="heat-bad" title="야후 이름: '
                         f'{_esc(r.yahoo_name)}">✗ 코드 확인</span>')
        label = (f'<span class="heat-name">{_esc(r.label)}</span>'
                 f'<span class="heat-code">{_esc(r.code)}</span>{name_flag}')
        if not r.ok:
            body.append(
                f'<tr class="heat-fail"><td>{label}</td>'
                f'<td colspan="{len(_sh.PERIODS) + 3}" class="na">'
                f"{_esc(r.error[:80])}</td></tr>")
            continue
        cells = "".join(
            _heat_cell(r.returns.get(k), _sh.COLOR_SCALE[k])
            for k, _lab, _n in _sh.PERIODS)
        rel = ('<td class="num na">기준</td>' if r.benchmark
               else _heat_cell(r.rel_1m, _sh.COLOR_SCALE["m1"]))
        band = ("—" if r.band_52w is None
                else f'<span class="heat-band"><i style="left:'
                     f'{r.band_52w:.0f}%"></i></span>'
                     f'<span class="heat-band-num">{r.band_52w:.0f}%</span>')
        cls = ' class="heat-bench"' if r.benchmark else ""
        body.append(
            f"<tr{cls}><td>{label}</td>{cells}{rel}"
            f'<td class="num">{band}</td>'
            f"<td>{_sparkline(r.spark)}</td></tr>")

    bad = _sh.mismatched(rows)
    warn = ""
    if bad:
        warn = render_footnote(
            f"<b>✗ 종목코드를 확인하십시오 ({len(bad)}건).</b> 야후가 돌려준 "
            "이름이 업종과 맞지 않습니다 — 다른 ETF 의 수익률일 수 있습니다: "
            + " · ".join(f"{_esc(r.label)}({_esc(r.code)}) → "
                         f"'{_esc(r.yahoo_name)}'" for r in bad)
            + ". config.KR_SECTOR_ETFS 에서 코드를 고치십시오.")

    return (
        '<div class="dash-table-wrap"><table class="dash-table dash-heat">'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
        + warn
    )


def render_sector_bars(rows: list) -> str:
    """업종 순위 막대 — KODEX 200 대비 1개월 초과수익, 가운데 선에서 좌(약세) · 우(강세).

    2026-11-13 폰: "섹터 온도란 너무 허접하고 비어 보임". 폰에서는 표가 종목별 카드로
    풀려 색이 사라지고 숫자만 세로로 늘어섰습니다. 한 화면에 순위가 보이게 막대로.
    """
    ranked = [r for r in rows if r.ok and not r.benchmark and r.rel_1m is not None]
    if not ranked:
        return ""
    ranked.sort(key=lambda r: r.rel_1m, reverse=True)
    top = max(abs(r.rel_1m) for r in ranked) or 1.0
    out = []
    for r in ranked:
        w = abs(r.rel_1m) / top * 50.0
        cls = "up" if r.rel_1m > 0 else ("down" if r.rel_1m < 0 else "flat")
        side = f"left:50%;width:{w:.1f}%" if r.rel_1m >= 0 else f"right:50%;width:{w:.1f}%"
        out.append(
            f'<div class="sb-row"><span class="sb-name">{_esc(r.label)}</span>'
            f'<span class="sb-track"><i class="{cls}" style="{side}"></i></span>'
            f'<span class="sb-val {cls}">{r.rel_1m:+.1f}</span></div>')
    return ('<div class="dash-sbar2"><div class="sb-head"><b>시장 대비 강약</b>'
            "<span>1개월 · KODEX 200 대비 %p · ← 약세 | 강세 →</span></div>"
            + "".join(out) + "</div>")


def render_sector_heatgrid(rows: list) -> str:
    """기간별 온도 격자 — 업종 × (1일 · 1주 · 1개월 · 3개월). 색 = 방향, 진하기 = 크기.

    표(table)가 아니라 격자(div)라서 폰에서도 풀리지 않고 한 화면에 들어옵니다.
    순서는 막대와 같습니다 (기준선이 맨 위, 그다음 시장 대비 강한 순).
    """
    import sector_heat as _sh  # noqa: PLC0415

    ok = [r for r in rows if r.ok]
    if not ok:
        return ""
    bench = [r for r in ok if r.benchmark]
    rest = sorted([r for r in ok if not r.benchmark],
                  key=lambda r: (r.rel_1m is None, -(r.rel_1m or 0.0)))
    head = ('<div class="hg-row hg-head"><span></span>'
            + "".join(f"<span>{_esc(lab)}</span>" for _k, lab, _n in _sh.PERIODS) + "</div>")
    body = []
    for r in bench + rest:
        cells = []
        for k, _lab, _n in _sh.PERIODS:
            v = r.returns.get(k)
            if v is None:
                cells.append('<span class="hg-cell na">—</span>')
                continue
            strength = min(1.0, abs(v) / _sh.COLOR_SCALE[k]) if _sh.COLOR_SCALE.get(k) else 0.0
            pct = round(10 + strength * 55)
            var = "--dash-up" if v > 0 else ("--dash-down" if v < 0 else "--dash-flat")
            cells.append(
                f'<span class="hg-cell{" strong" if strength > 0.6 else ""}" style="background:'
                f'color-mix(in srgb, var({var}) {pct}%, var(--dash-surface))">{v:+.1f}</span>')
        body.append(
            f'<div class="hg-row{" hg-bench" if r.benchmark else ""}">'
            f'<span class="hg-name">{_esc(r.label)}</span>{"".join(cells)}</div>')
    return ('<div class="dash-hgrid"><div class="sb-head"><b>기간별 수익률</b>'
            "<span>% · 붉을수록 상승 · 푸를수록 하락</span></div>"
            + head + "".join(body) + "</div>")


def _flow_chip(f, show_prev: bool = True) -> str:
    """흐름 칩 — 이름 · 3개월 | 1주 (시장 대비 %p) · 1주 전 칸."""
    import sector_heat as _sh  # noqa: PLC0415

    prev = ""
    if show_prev and f.moved:
        prev = f'<i>← {_esc(_sh.PHASE_NAME.get(f.prev_phase, ""))}</i>'
    return (f'<span class="sf-chip"><b>{_esc(f.label)}</b>'
            f'<em>{_sh.pp(f.level)} | {_sh.pp(f.direction)}</em>{prev}</span>')


def render_sector_flow(rows: list, base: str = "k200") -> str:
    """섹터 온도 맨 위 — 판독 문장 + 흐름 지도(주도 · 회복 · 둔화 · 침체).

    2026-11-13 사용자: "섹터 온도의 변화 흐름이 무엇을 이야기하는지" 가 안 보임.
    아래의 칩 · 막대 · 격자는 그대로 두고, 그 숫자들이 **무슨 이야기인지**를
    먼저 적습니다. 판정 규칙은 sector_heat.flow · flow_read 에 있습니다.
    기준선을 못 받았거나 판정한 업종이 없으면 아무것도 그리지 않습니다
    (아래 칸들은 그대로 나옵니다).
    """
    import sector_heat as _sh  # noqa: PLC0415

    rows = rows or []
    bench, fallback = None, ""
    if base == "ew":
        # 2026-11-13 사용자 승인: 업종 평균(동일가중) 기준으로도 보기
        bench = _sh.equal_weight_bench(rows)
        if bench is None:
            fallback = (f'<div class="sf-unk">업종 평균을 만들 업종이 '
                        f"{_sh.EW_MIN_MEMBERS}개보다 적어 KODEX 200 기준으로 "
                        "보여 줍니다.</div>")
    flows = _sh.flow(rows, bench)
    read = _sh.flow_read(rows, flows, bench)
    if read is None:
        return ""
    ew = read.bench_code == _sh.EW_CODE
    day = _sh.as_of(rows)
    when = f" · {int(day[5:7])}/{day[8:10]} 봉 기준" if len(day) >= 10 else ""
    lines = "".join(f"<li>{_esc(t)}</li>" for t in _sh.flow_sentences(read))

    known = [f for f in flows if f.phase is not None]
    boxes = []
    for key, name, meaning in _sh.PHASES:
        items = sorted((f for f in known if f.phase == key),
                       key=lambda f: -f.direction)
        chips = ("".join(_flow_chip(f) for f in items)
                 or '<span class="sf-none">없음</span>')
        if ew:
            meaning = meaning.replace("시장", _sh.EW_LABEL)
        boxes.append(
            f'<div class="sf-q sf-{key}"><div class="sf-qh"><b>{_esc(name)}</b>'
            f"<span>{_esc(meaning)}</span><small>{len(items)}</small></div>"
            f'<div class="sf-chips">{chips}</div></div>')

    flat = sorted((f for f in known if f.phase == "flat"), key=lambda f: -f.level)
    flat_html = ""
    if flat:
        flat_html = (f'<div class="sf-flat"><b>방향 없음</b> (1주 ±{_sh.FLOW_FLAT:g}%p 안) '
                     + "".join(_flow_chip(f, show_prev=False) for f in flat) + "</div>")
    unk_html = ""
    if read.unknown:
        unk_html = ('<div class="sf-unk">판정 못 함: '
                    + " · ".join(f"{_esc(f.label)}({_esc(f.why_none)})"
                                 for f in read.unknown) + "</div>")
    moved = (f" · 1주 전과 칸이 바뀐 업종 {read.moved}/{read.n}개"
             + (" — 1주 기준이라 칸이 자주 바뀝니다" if read.moved * 2 >= read.n else "")
             if read.moved else "")
    ew_note = ""
    if ew and bench is not None:
        ew_note = (f'<div class="sf-foot"><b>{_esc(_sh.EW_LABEL)}</b> = 업종 ETF '
                   f"{len(bench.members)}개를 같은 비중으로 매일 평균한 선 "
                   "(코스닥150 은 시장 지수라 뺌) · 이번 주 "
                   f"{_sh.pp(read.bench_dir)}% · 3개월 "
                   + (f"{_sh.pp(bench.returns.get('m3'))}%" if bench.returns.get("m3") is not None
                      else "—") + "</div>")
    return (
        '<div class="dash-sflow">'
        f'<div class="sb-head"><b>흐름이 말하는 것</b><span>기준 {_esc(read.bench_label)} · '
        f"KODEX 업종 ETF · 네이버 일봉{_esc(when)}</span></div>{fallback}"
        f'<ul class="sf-read">{lines}</ul>'
        f'<div class="sf-map">{"".join(boxes)}</div>{flat_html}'
        f'<div class="sf-foot">숫자 = <b>3개월 | 1주</b>, {_esc(read.bench_label)} 대비 %p · '
        f"<i>← 칸</i> = 1주 전에 있던 칸{_esc(moved)}</div>{ew_note}{unk_html}"
        "</div>")


def render_sector_heat_summary(rows: list) -> str:
    """표 위의 한 줄 — 강세·약세 업종. 표를 다 읽기 전에 결론부터."""
    import sector_heat as _sh  # noqa: PLC0415

    hot, cold = _sh.hot_and_cold(rows, n=3)
    if not hot and not cold:
        return ""

    def chips(items, cls):
        return "".join(
            f'<span class="heat-chip {cls}">{_esc(r.label)} '
            f'<b>{r.rel_1m:+.1f}%p</b></span>' for r in items)

    parts = []
    if hot:
        parts.append('<div class="heat-sum-row"><span class="heat-sum-lab">'
                     f'강세</span>{chips(hot, "up")}</div>')
    if cold:
        parts.append('<div class="heat-sum-row"><span class="heat-sum-lab">'
                     f'약세</span>{chips(cold, "down")}</div>')
    return ('<div class="heat-sum">' + "".join(parts)
            + '<div class="heat-sum-note">1개월 · KODEX 200 대비</div></div>')


# ──────────────────────────────────────────────────────────────────────────────
# 걸러진 단계 (스크리너 깔때기)
# ──────────────────────────────────────────────────────────────────────────────

def render_funnel(steps, errors: dict | None = None, *, title: str = "") -> str:
    """단계마다 남은 종목 수를 가로로. 가장 많이 빠진 단계를 강조합니다.

    0 건일 때 '데이터를 못 받은 것' 과 '기준에서 걸러진 것' 을 한눈에
    구분하려는 표입니다. 오류는 접어서 전문을 보여 줍니다 — 60자에서 자른
    'HTTPSConnectionPool(h' 로는 원인을 알 수 없었습니다.
    """
    if not steps:
        return ""
    drops = [(steps[i - 1].count - steps[i].count, i) for i in range(1, len(steps))]
    worst = max(drops)[1] if drops and max(drops)[0] > 0 else -1
    cells = []
    for i, stp in enumerate(steps):
        cls = "fn-step"
        if i == worst:
            cls += " fn-worst"
        if stp.count == 0:
            cls += " fn-zero"
        note = (f'<div class="fn-note">{_esc(stp.note)}</div>'
                if stp.note else "")
        arrow = '<div class="fn-arrow" aria-hidden="true">›</div>' if i else ""
        inner = (f'<div class="fn-n">{stp.count}</div>'
                 f'<div class="fn-l">{_esc(stp.label)}</div>{note}')
        href = getattr(stp, "href", "")
        if href:
            # 누르면 그 단계의 목록으로 — 같은 창에서 엽니다
            on = " fn-on" if getattr(stp, "on", False) else ""
            cells.append(f'{arrow}<a class="{cls} fn-link{on}" href="{_esc(href)}" '
                         f'target="_self">{inner}</a>')
        else:
            cells.append(f'{arrow}<div class="{cls}">{inner}</div>')
    head = (f'<div class="fn-title">{_esc(title)}</div>' if title else "")
    err_html = ""
    if errors:
        items = "".join(
            f"<li><code>{_esc(k)}</code> {_esc(str(v))}</li>"
            for k, v in list(errors.items())[:40])
        err_html = (f'<details class="fn-errs"><summary>빠진 종목 '
                    f'{len(errors)}개 — 이유 보기</summary><ul>{items}</ul>'
                    "</details>")
    return (f'<div class="dash-funnel">{head}<div class="fn-row">'
            + "".join(cells) + f"</div>{err_html}</div>")


def render_empty_reason(n_total: int, errors: dict, *, scope_hint: bool,
                        source: str) -> str:
    """'대상 종목 없음' 을 **원인별로** 말합니다.

    2026-11-11: 국내 3종목이 전부 DART 고유번호 실패였는데 화면은 "'전체'
    로 바꿔 보십시오" 를 먼저 말했습니다. 데이터를 못 받은 상황에서
    범위를 넓혀도 결과는 같습니다. 오류가 있으면 오류가 먼저입니다.
    """
    if errors:
        # 같은 원인이 여러 종목에 반복되면 한 번만 적습니다
        causes: dict[str, list[str]] = {}
        for tk, msg in errors.items():
            core = str(msg).split(":", 1)[-1].strip() if ":" in str(msg) else str(msg)
            causes.setdefault(core, []).append(tk)
        lines = "".join(
            f"<li><b>{_esc(', '.join(tks[:6]))}{' 외' if len(tks) > 6 else ''}</b>"
            f" — {_esc(cause)}</li>" for cause, tks in causes.items())
        lead = (f"<b>{source} 재무를 받지 못해 판단할 종목이 없습니다.</b> "
                f"후보 {n_total}종목 중 {len(errors)}종목이 실패했습니다. "
                "범위를 바꿔도 같은 결과입니다 — 연결 문제가 먼저입니다.")
        hint = ("" if source != "DART" else
                '<div class="dash-footnote dash-notice">해결 순서: 설정 → 진단의 '
                "<b>국내 데이터 출처 확인</b>을 누르면 DART 에 닿는지, 막혔다면 "
                "연결 단계인지 내려받기 단계인지 나옵니다.</div>")
        return (f'<div class="dash-empty-reason">{lead}<ul>{lines}</ul></div>'
                + hint)
    if scope_hint:
        return render_footnote(
            "<b>대상 종목이 없습니다.</b> 위 '대상' 에서 <b>전체</b>를 고르면 "
            "보유·발굴 통과가 아닌 종목까지 봅니다.")
    return render_footnote("<b>대상 종목이 없습니다.</b> 후보 목록이 비어 있습니다.")


def render_notice(text: str) -> str:
    """'설명 문구 표시' 를 꺼도 **남는** 안내 — 0 건·실패·통과 수처럼
    화면을 읽는 데 꼭 필요한 문장. 설명(footnote)과 모양은 같고 숨지 않습니다."""
    return f'<div class="dash-footnote dash-notice">{text}</div>'


# ──────────────────────────────────────────────────────────────────────────────
# 시장 띠
# ──────────────────────────────────────────────────────────────────────────────

def render_market_strip(items) -> str:
    """맨 위 숫자 6개. items: [(이름, Instrument, Quote|None)].

    **카드가 아니라 띠**입니다 — 칸 사이에 세로선만 두고 한 줄로 붙입니다.
    아래 섹션들이 카드라서, 첫 줄까지 카드면 화면 전체가 같은 모양이
    됩니다. 값을 못 받은 칸은 '—' 로 두고 자리를 지킵니다 (칸이 빠지면
    매번 위치가 바뀌어 눈이 못 따라갑니다).
    """
    cells = []
    for label, inst, q in items:
        price = q.price if (q is not None and q.ok) else None
        pct = q.change_pct if (q is not None and q.ok) else None
        scale = getattr(inst, "scale", 1.0) or 1.0
        unit = getattr(inst, "suffix", "") or ""
        dec = inst.decimals if inst.decimals is not None else 2
        if price is not None and price >= 1000:
            dec = min(dec, 2)
        val = "—" if price is None else fmt_num(price * scale, dec) + unit
        cls = direction_class(pct) if pct is not None else "flat"
        prev = getattr(q, "prev_close", None) if q is not None else None
        diff = ((price - prev) * scale if (price is not None and prev) else None)
        diff_txt = ("" if diff is None else
                    f"<small>{fmt_num(abs(diff), dec)} · </small>")
        chg = ("" if pct is None else
               f'<span class="ms-chg {cls}">{direction_glyph(pct)}{diff_txt}'
               f"{fmt_pct(pct)}</span>")
        cells.append(
            f'<div class="ms-cell {cls}"><div class="ms-label">{_esc(label)}</div>'
            f'<div class="ms-val">{_esc(val)}</div>{chg}</div>')
    return '<div class="dash-mstrip">' + "".join(cells) + "</div>"


def render_hit_table(hits, limit: int = 12) -> str:
    """통과 종목 비교표 — 펼치기 전에 숫자가 보이게.

    전에는 종목 이름만 적힌 접힌 줄이 세로로 늘어서 있어서, 무엇이 왜
    걸렸는지 보려면 하나씩 열어야 했습니다. 순위·이름·지표를 한 표에
    두면 종목끼리 비교가 됩니다. 열은 첫 종목의 지표 이름을 따릅니다
    (같은 스크리너의 종목은 지표가 같습니다).
    """
    hits = list(hits or [])[:limit]
    if not hits:
        return ""
    cols = [lab for lab, _v in hits[0].metrics][:8]   # 품질 · 선행 EPS 두 칸이 앞에 붙음 (11/13)
    head = ("<tr><th class='ht-rank'>#</th><th>종목</th>"
            + "".join(f"<th>{_esc(c)}</th>" for c in cols) + "</tr>")
    body = []
    for i, h in enumerate(hits, 1):
        vals = dict(h.metrics)
        cells = "".join(f"<td>{_esc(str(vals.get(c, '—')))}</td>" for c in cols)
        body.append(
            f"<tr><td class='ht-rank'>{i}</td>"
            f"<td class='ht-name'><b>{_esc(h.name)}</b>"
            f"<span>{_esc(h.ticker)}</span></td>{cells}</tr>")
    return ('<div class="dash-htable-wrap"><table class="dash-htable">'
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>")


# ──────────────────────────────────────────────────────────────────────────────
# 보유 종목 표
# ──────────────────────────────────────────────────────────────────────────────

_CHART_SHORT = {"cloud": "일목", "ma": "이평", "cci": "CCI", "macd": "MACD",
                "stoch": "스토캐스틱", "bb": "볼린저", "dmi": "−DI"}


def chart_badges(row, limit: int = 3) -> str:
    """차트 조건 한 줄 요약 — 상태가 있는 지표만, 최대 limit 개."""
    if row is None or not getattr(row, "ok", False):
        return ""
    nt = row.notes()
    bits = []
    if row.ichi.bullish_cloud is not None:
        bits.append("양운" if row.ichi.bullish_cloud else "음운")
    for k in ("ma", "cci", "stoch", "macd", "bb", "dmi"):
        txt = (nt.get(k) or "").split(" · 거래량")[0]
        if txt:
            bits.append(f"{_CHART_SHORT[k]} {txt}")
        if len(bits) >= limit + 1:
            break
    return " · ".join(bits[:limit + 1])


def render_holdings_table(rows, chart_rows: dict | None = None) -> str:
    """보유·관심 종목을 한 표로. rows: [(Instrument, Quote|None, 신호목록)].

    전에는 종목마다 큰 카드(이름·거래소·상태 배지·회색 상자 안 가격·등락)
    가 네 칸 격자로 놓였습니다. 7종목이면 화면 두 장이고 종목끼리 등락을
    비교하려면 눈이 지그재그로 움직였습니다. 표 한 장이면 위아래로 바로
    비교됩니다. 신호(지금/이번 주)는 맨 오른쪽 칸에 개수로 둡니다 — 내용은
    아래 '변화 감지' 에 있습니다.
    """
    if not rows:
        return ""
    body = []
    for inst, q, sigs in rows:
        ok = q is not None and q.ok
        scale = getattr(inst, "scale", 1.0) or 1.0
        unit = getattr(inst, "suffix", "") or ""
        price = fmt_num(q.price * scale, inst.decimals) + unit if ok else "—"
        pct = q.change_pct if ok else None
        cls = direction_class(pct) if pct is not None else "flat"
        chg = (f"{direction_glyph(pct)}{fmt_pct(pct)}" if pct is not None else "—")
        ext = ""
        if ok and q.extended_price is not None and q.extended_label:
            ep = q.extended_change_pct
            ext = (f'<span class="hd-ext">{_esc(q.extended_label)} '
                   f'<span class="{direction_class(ep)}">{fmt_pct(ep)}</span></span>')
        sigs = sigs if sigs is not None else []
        now = sum(1 for s in sigs if s.severity >= 3)
        soon = sum(1 for s in sigs if s.severity == 2)
        badges = ""
        if now:
            badges += f'<span class="hd-sig now">지금 {now}</span>'
        if soon:
            badges += f'<span class="hd-sig soon">이번 주 {soon}</span>'
        if not badges:
            badges = '<span class="hd-sig quiet">조용</span>'
        link = inst.resolved_link() if hasattr(inst, "resolved_link") else ""
        name = (f'<a href="{_esc(link)}" target="_blank" rel="noopener">{_esc(inst.name)}</a>'
                if link else _esc(inst.name))
        chart = ""
        if chart_rows is not None:
            cb = chart_badges(chart_rows.get(inst.symbol))
            chart = f"<td class='hd-chart'>{_esc(cb) or '—'}</td>"
        body.append(
            f"<tr><td class='hd-name'>{name}<span>{_esc(inst.symbol)}</span></td>"
            f"<td class='hd-num'>{_esc(price)}</td>"
            f"<td class='hd-num {cls}'>{chg}{ext}</td>"
            f"{chart}<td class='hd-sigs'>{badges}</td></tr>")
    chart_th = "<th>차트 상태</th>" if chart_rows is not None else ""
    return ('<div class="dash-htable-wrap"><table class="dash-htable dash-hold">'
            f"<thead><tr><th>종목</th><th>현재가</th><th>등락</th>{chart_th}<th>신호</th></tr>"
            f"</thead><tbody>{''.join(body)}</tbody></table></div>")


# ──────────────────────────────────────────────────────────────────────────────
# 보유 평가
# ──────────────────────────────────────────────────────────────────────────────

def _won(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e8:
        s = f"{a / 1e8:,.2f}억"
    elif a >= 1e4:
        s = f"{a / 1e4:,.0f}만"
    else:
        s = f"{a:,.0f}"
    sign = ("+" if v > 0 else "−" if v < 0 else "") if signed else ("−" if v < 0 else "")
    return f"{sign}{s}원"


def render_portfolio(summary, *, source: str = "", bad=(), total=None) -> str:
    """보유 평가 — 숫자 네 칸 + 종목 표 (비중 막대).

    total 을 주면(두 시장 합계) 맨 위에 '계좌 전체' 한 줄을 붙입니다.
    """
    rows = summary.rows
    if not rows:
        return ""
    pnl_cls = direction_class(summary.pnl_krw)
    td_cls = direction_class(summary.today_krw)
    kpis = (
        f'<div class="pf-kpi"><div class="pf-l">평가금액</div>'
        f'<div class="pf-v">{_won(summary.value_krw)}</div>'
        f'<div class="pf-s">{summary.priced}/{len(rows)}종목 시세 반영</div></div>'
        f'<div class="pf-kpi"><div class="pf-l">평가손익 (원화 환산)</div>'
        f'<div class="pf-v {pnl_cls}">{_won(summary.pnl_krw, True)}</div>'
        f'<div class="pf-s {pnl_cls}">{fmt_pct(summary.pnl_pct)}</div></div>'
        f'<div class="pf-kpi"><div class="pf-l">오늘 움직임</div>'
        f'<div class="pf-v {td_cls}">{_won(summary.today_krw, True)}</div>'
        f'<div class="pf-s {td_cls}">{fmt_pct(summary.today_pct)}</div></div>'
    )
    if total is not None and total.value_krw and total.value_krw != summary.value_krw:
        share = summary.value_krw / total.value_krw * 100.0
        kpis += (f'<div class="pf-kpi"><div class="pf-l">계좌 전체 중 이 시장</div>'
                 f'<div class="pf-v">{share:.0f}%</div>'
                 f'<div class="pf-s">전체 {_won(total.value_krw)} · 손익 '
                 f'{_won(total.pnl_krw, True)}</div></div>')
    body = []
    for r in rows:
        if not r.ok:
            body.append(
                f"<tr><td class='hd-name'><b>{_esc(r.name)}</b><span>{_esc(r.pos.symbol)}</span></td>"
                f"<td class='hd-num'>{r.pos.qty:,.4g}</td>"
                f"<td colspan='6' class='qt-err'>{_esc(r.error[:80])}</td></tr>")
            continue
        dec = 0 if r.currency == "KRW" else 2
        w = summary.weight(r) or 0.0
        pc = direction_class(r.pnl_pct)
        tc = direction_class(r.today_krw)
        body.append(
            f"<tr><td class='hd-name'><b>{_esc(r.name)}</b><span>{_esc(r.pos.symbol)}</span></td>"
            f"<td class='hd-num'>{r.pos.qty:,.4g}</td>"
            f"<td class='hd-num'>{fmt_num(r.pos.avg, dec)}</td>"
            f"<td class='hd-num'>{fmt_num(r.price, dec)}</td>"
            f"<td class='hd-num {pc}'>{fmt_pct(r.pnl_pct)}</td>"
            f"<td class='hd-num'>{_won(r.value_krw)}<span class='pf-sub {pc}'>"
            f"{_won(r.pnl_krw, True)}</span></td>"
            f"<td class='hd-num {tc}'>{_won(r.today_krw, True)}</td>"
            f"<td class='pf-w'><i style='width:{w:.0f}%'></i><span>{w:.1f}%</span></td></tr>")
    head = ("<tr><th>종목</th><th>수량</th><th>평균단가</th><th>현재가</th>"
            "<th>손익률</th><th>평가금액 · 손익</th><th>오늘</th><th>비중</th></tr>")
    notes = []
    if source:
        notes.append(f"보유 출처: {_esc(source)}")
    notes.append("원화 손익은 지금 환율로 환산 — 매수 당시 환율을 몰라 환차손익을 나누지 "
                 "못합니다. 손익률은 종목 통화 기준")
    if bad:
        notes.append("읽지 못한 항목: " + _esc(", ".join(list(bad)[:5])))
    return (f'<div class="dash-pf">{kpis}</div>'
            '<div class="dash-htable-wrap"><table class="dash-htable dash-hold dash-pft">'
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
            f'<div class="dash-footnote dash-notice">{" · ".join(notes)}</div>')


def render_portfolio_setup() -> str:
    """PORTFOLIO 가 없을 때 — 무엇을 어디에 적는지."""
    return ('<div class="dash-footnote dash-notice"><b>보유 수량을 넣으면 평가금액·손익·'
            "비중이 여기 나옵니다.</b> Streamlit Cloud → 앱 설정 → Secrets 맨 위에 한 줄: "
            '<code>PORTFOLIO = "MSFT:10@410.5, 005930:30@71000"</code> (종목:수량@평균단가, '
            "미국은 달러·한국은 원). 저장소에는 올라가지 않습니다.</div>")


# ──────────────────────────────────────────────────────────────────────────────
# 주요 일정
# ──────────────────────────────────────────────────────────────────────────────

def render_calendar(events, today, *, market: str = "", limit: int = 60,
                    compact: bool = False) -> str:
    """날짜별 목록. 고른 시장의 사건은 진하게, 다른 시장은 흐리게.

    compact=True 면 요약 화면용 — 다음 몇 건만 한 줄씩.
    """
    import calendar_events as ce

    events = list(events or [])[:limit]
    if not events:
        return ""
    if compact:
        items = "".join(
            f'<div class="cal-c {"cal-imp" if e.importance >= 3 else ""}">'
            f'<span class="cal-d">{_esc(ce.d_day(e, today))}</span>'
            f'<span class="cal-mk {e.market}">{_esc(ce.MARKET_LABEL[e.market])}</span>'
            f'<span class="cal-t">{_esc(e.title)}</span>'
            f'<span class="cal-n">{_esc(e.date[5:].replace("-", "/"))}'
            f'{" · " + _esc(e.note) if e.note and e.kind != "data" else ""}</span></div>'
            for e in events)
        return f'<div class="dash-calc">{items}</div>'
    days: dict[str, list] = {}
    for e in events:
        days.setdefault(e.date, []).append(e)
    blocks = []
    for d, evs in days.items():
        day = evs[0].day
        wd = "월화수목금토일"[day.weekday()]
        rows = "".join(
            f'<div class="cal-row {"cal-other" if market and e.market != market else ""} '
            f'{"cal-imp" if e.importance >= 3 else ""}">'
            f'<span class="cal-mk {e.market}">{_esc(ce.MARKET_LABEL[e.market])}</span>'
            f'<span class="cal-k {e.kind}">{_esc(ce.KIND_LABEL.get(e.kind, e.kind))}</span>'
            f'<span class="cal-t">{_esc(e.title)}'
            f'{" <i>잠정</i>" if e.tentative else ""}</span>'
            f'<span class="cal-n">{_esc(e.note)}</span></div>'
            for e in evs)
        blocks.append(
            f'<div class="cal-day"><div class="cal-date"><b>{day.month}/{day.day}</b>'
            f'<span>{wd}</span><em>{_esc(ce.d_day(evs[0], today))}</em></div>'
            f'<div class="cal-list">{rows}</div></div>')
    return f'<div class="dash-cal">{"".join(blocks)}</div>'



# ──────────────────────────────────────────────────────────────────────────────
# 차트 조건 (일목 양운 · CCI · MACD · DMI)
# ──────────────────────────────────────────────────────────────────────────────

def render_chart_counts(counts: dict, n_ok: int, n_total: int,
                        conditions) -> str:
    """조건별로 몇 종목이 충족하는지 — 네 칸. 깔때기가 아닙니다 (조건이
    서로 독립이라 순서가 없습니다). 계산된 종목 수를 분모로 같이 적습니다."""
    cells = []
    for key, name, rule in conditions:
        n = counts.get(key, 0)
        share = (n / n_ok * 100.0) if n_ok else 0.0
        cells.append(
            f'<div class="cc-cell"><div class="cc-name">{_esc(name)}</div>'
            f'<div class="cc-n">{n}<span>/ {n_ok}</span></div>'
            f'<div class="cc-bar"><i style="width:{share:.0f}%"></i></div>'
            f'<div class="cc-rule">{clamp(_esc(rule), limit=24, one=True)}</div></div>')
    miss = n_total - n_ok
    tail = (f'<div class="cc-miss">후보 {n_total}종목 중 {miss}종목은 일봉이 '
            "없거나 모자라 계산하지 못했습니다.</div>" if miss else "")
    return f'<div class="dash-cc">{"".join(cells)}</div>{tail}'


def _cc_cell(met, main: str, note: str = "") -> str:
    cls = "ct-yes" if met else ("ct-na" if met is None else "ct-no")
    mark = "●" if met else ("?" if met is None else "·")
    sub = f"<span>{_esc(note)}</span>" if note else ""
    return (f'<td class="{cls}"><b class="ct-mark">{mark}</b>'
            f'{_esc(main)}{sub}</td>')


def _side_chip(row) -> str:
    """종목의 쪽 — 과매도 / 과매수 / 엇갈림, 그리고 몇 개 지표가 그쪽인지.

    색으로 칠하지 않습니다 (좋고 나쁨이 아니라 상태). 글자와 테두리 모양으로
    가릅니다.
    """
    import chart_signals as _cs  # noqa: PLC0415

    side = getattr(row, "side", "")
    if not side:
        return '<span class="ct-sd none">—</span>'
    n_os, n_ob = row.side_votes
    count = {"os": f"{n_os}/3", "ob": f"{n_ob}/3", "mixed": f"{n_os}:{n_ob}"}[side]
    return (f'<span class="ct-sd {side}">{_cs.SIDE_NAMES[side]}'
            f'<i>{count}</i></span>')


def render_chart_table(rows, limit: int = 30, held=(), semi=(), new=()) -> str:
    """종목 × 조건. 칸마다 **상태 이름**과 값을 적습니다. held 에 든 종목
    (보유·관심)은 이름 앞에 ★ 를 붙입니다.

    해당하는 칸은 채워진 점과 옅은 바탕으로 표시합니다. 과매도·과매수를
    오름·내림 색으로 칠하지 않습니다 — 좋고 나쁨이 아니라 상태입니다.
    쪽은 글자로 구분합니다 — '쪽' 칸에 종목의 쪽과, 세 지표(CCI · 스토캐스틱 ·
    볼린저) 가운데 몇 개가 그쪽인지 적습니다.
    """
    rows = list(rows or [])[:limit]
    if not rows:
        return ""
    body = []
    for i, r in enumerate(rows, 1):
        f, nt = r.flags(), r.notes()
        dots = "".join(
            f'<i class="{"on" if f.get(k) else ""}"></i>' for k in f)
        cloud = "—" if f["cloud"] is None else ("양운" if f["cloud"] else "음운")
        cci = "—" if r.cci is None else f"{r.cci:+.0f}"
        macd = "—" if r.macd_hist is None else ("위" if r.macd_hist > 0 else "아래")
        stoch = ("—" if r.stoch_k is None else
                 f"{r.stoch_k:.0f}" + ("" if r.stoch_d is None
                                       else f" / {r.stoch_d:.0f}"))
        di = "—" if r.minus_di is None else f"{r.minus_di:.0f}"
        ma = "—" if r.disparity is None else f"이격 {r.disparity:.1f}"
        bb = "—" if r.bb_pctb is None else f"{r.bb_pctb:.2f}"
        star = '<i class="ct-star" title="내 종목">★</i>' if r.ticker in held else ""
        tag = (("<span class='ct-semi ct-new'>새로</span>" if r.ticker in new else "")
               + ("<span class='ct-semi'>반도체</span>" if r.ticker in semi else ""))
        body.append(
            f"<tr><td class='ht-rank'>{i}</td>"
            f"<td class='ht-name'>{star}<b>{_esc(r.name)}</b><span>{_esc(r.ticker)}</span>{tag}</td>"
            f"<td class='ct-met'><span class='ct-dots'>{dots}</span>{r.met}/{len(f)}</td>"
            f"<td class='ct-side'>{_side_chip(r)}</td>"
            + _cc_cell(f["cloud"], cloud, nt["cloud"])
            + _cc_cell(f["ma"], ma, nt["ma"])
            + _cc_cell(f["cci"], cci, nt["cci"])
            + _cc_cell(f["macd"], macd, nt["macd"] if f["macd"] else "")
            + _cc_cell(f["stoch"], stoch, nt["stoch"])
            + _cc_cell(f["bb"], bb, nt["bb"])
            + _cc_cell(f["dmi"], di, nt["dmi"])
            + "</tr>")
    return ('<div class="dash-htable-wrap"><table class="dash-htable dash-ctable">'
            "<thead><tr><th class='ht-rank'>#</th><th>종목</th><th>해당</th>"
            "<th title='CCI · 스토캐스틱 · 볼린저 %B 로 가른 쪽'>쪽</th>"
            "<th>일목</th><th>이동평균</th><th>CCI(13)</th><th>MACD<br>시그널 대비</th>"
            "<th>스토캐스틱<br>%K / %D</th><th>볼린저<br>%B</th><th>−DI</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def _cloud_runs(a: list, b: list) -> list[tuple[bool, int, int]]:
    """구름을 '양운 구간 / 음운 구간' 으로 자릅니다. (양운?, 시작, 끝) 목록."""
    runs: list[tuple[bool, int, int]] = []
    start, cur = None, None
    for i in range(len(a)):
        if a[i] is None or b[i] is None:
            if start is not None:
                runs.append((cur, start, i - 1))
                start = None
            continue
        bull = a[i] > b[i]
        if start is None:
            start, cur = i, bull
        elif bull != cur:
            runs.append((cur, start, i))     # 교차 지점을 양쪽이 공유
            start, cur = i, bull
    if start is not None:
        runs.append((cur, start, len(a) - 1))
    return runs


def render_cloud_chart(row, width: int = 640, height: int = 170) -> str:
    """최근 120봉 종가 + 일목 구름. 양운·음운은 등락 색 규칙을 따릅니다
    (국내 HTS 와 같이 양운 = 오름 색). 축 눈금 대신 양 끝 가격만 적습니다."""
    px = [p for p in (row.spark or []) if p is not None]
    if len(px) < 2:
        return ""
    a, b = list(row.spark_a), list(row.spark_b)
    vals = px + [v for v in a if v is not None] + [v for v in b if v is not None]
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return ""
    pad_l, pad_r, pad_t, pad_b = 6, 62, 8, 8
    n = len(px)
    # 구름은 오늘을 지나 앞쪽(선행 25봉)까지 이어집니다 — 가로 눈금은 구름 길이 기준
    span_n = max(n, len(a), len(b))

    def X(i: int) -> float:
        return pad_l + (width - pad_l - pad_r) * i / (span_n - 1)

    def Y(v: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    polys = []
    for bull, s, e in _cloud_runs(a, b):
        if e <= s:
            continue
        top = " ".join(f"{X(i):.1f},{Y(a[i]):.1f}" for i in range(s, e + 1))
        bot = " ".join(f"{X(i):.1f},{Y(b[i]):.1f}" for i in range(e, s - 1, -1))
        polys.append(f'<polygon class="{"cl-bull" if bull else "cl-bear"}" '
                     f'points="{top} {bot}"/>')
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(px))
    last = px[-1]
    dec = 0 if last >= 1000 else 2
    top_pct = Y(last) / height * 100.0
    # '오늘' 세로선 — 그 오른쪽이 앞 구름입니다
    today_x = X(n - 1)
    today_line = (f'<line class="cl-today" x1="{today_x:.1f}" y1="{pad_t}" '
                  f'x2="{today_x:.1f}" y2="{height - pad_b}"/>' if span_n > n else "")
    # 가격 글자는 SVG 밖에 둡니다 — SVG 를 칸 너비에 맞춰 늘리면
    # (preserveAspectRatio=none) 안의 글자도 같이 찌그러집니다.
    return ('<div class="dash-cloud-wrap">'
            f'<svg class="dash-cloud" viewBox="0 0 {width} {height}" '
            'preserveAspectRatio="none" role="img" '
            f'aria-label="{_esc(row.name)} 최근 {n}일 종가와 일목 구름">'
            + "".join(polys) + today_line
            + f'<polyline class="cl-price" points="{line}"/></svg>'
            + f'<span class="cl-lab" style="top:{top_pct:.1f}%">'
              f'{fmt_num(last, dec)}</span></div>')


# ── 캔들 차트 + 지표 패널 (2026-11-12 "차트 연동") ───────────────────────────
#
# 서버에서 SVG 로 그립니다. 그래프 라이브러리를 싣지 않아서 빠르고, 표의
# 판정과 **같은 숫자**로 그려집니다. SVG 는 칸 너비에 맞춰 가로로 늘리므로
# (preserveAspectRatio=none) 글자는 전부 SVG 밖 HTML 로 둡니다 — 안에 두면
# 같이 찌그러집니다. 선 굵기는 vector-effect 로 고정합니다.

_KC_W = 1000.0          # 가로 눈금 (늘어나므로 값 자체는 의미 없음)


def _kc_x(i: float, total: int) -> float:
    return _KC_W * (i + 0.5) / total


def _kc_segments(vals, total: int, Y, cls: str) -> str:
    """None 에서 끊기는 꺾은선."""
    out, cur = [], []
    for i, v in enumerate(vals):
        if v is None:
            if len(cur) > 1:
                out.append(cur)
            cur = []
            continue
        cur.append(f"{_kc_x(i, total):.1f},{Y(v):.1f}")
    if len(cur) > 1:
        out.append(cur)
    return "".join(f'<polyline class="{cls}" points="{" ".join(seg)}"/>' for seg in out)


def _kc_scale(lo: float, hi: float, height: float, pad: float = 6.0):
    if hi <= lo:
        hi, lo = lo + 1.0, lo - 1.0

    def Y(v: float) -> float:
        return pad + (height - 2 * pad) * (1 - (v - lo) / (hi - lo))
    return Y


def _kc_ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    """보기 좋은 눈금 값 (1·2·5 × 10ⁿ 간격)."""
    import math

    if hi <= lo:
        return [lo]
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 5, 10) if m * mag >= raw), 10 * mag)
    first = math.ceil(lo / step) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def _kc_num(v: float | None, ref: float | None = None) -> str:
    if v is None:
        return "—"
    ref = abs(v) if ref is None else abs(ref)
    return fmt_num(v, 0 if ref >= 1000 else (1 if ref >= 100 else 2))


def _kc_panel(height: int, svg: str, title: str, ticks: list[tuple[float, str]],
              Y, cls: str = "") -> str:
    """패널 한 장 — SVG + 왼쪽 위 제목 + 오른쪽 눈금 글자."""
    labs = "".join(
        f'<span style="top:{Y(v) / height * 100:.1f}%">{_esc(t)}</span>' for v, t in ticks)
    # 제목은 그림 **위 줄**에 둡니다 — 그림에 겹치면 좁은 화면에서 두 줄로
    # 넘어가며 선을 가립니다.
    return (f'<div class="kc-panel {cls}"><div class="kc-title">{title}</div>'
            f'<div class="kc-row" style="height:{height}px">'
            f'<div class="kc-plot"><svg viewBox="0 0 {_KC_W:.0f} {height}" '
            f'preserveAspectRatio="none" aria-hidden="true">{svg}</svg></div>'
            f'<div class="kc-axis">{labs}</div></div></div>')


def render_kchart(series, *, link: str = "", link_label: str = "") -> str:
    """캔들 + 이동평균 · 일목 구름 · 볼린저, 아래에 거래량 · CCI · MACD ·
    스토캐스틱 · DMI. series: chart_signals.ChartSeries.

    기준선(CCI ±100, 스토캐스틱 30/80, −DI 30/10)을 같이 그어, 표의 상태
    이름이 어디서 나왔는지 눈으로 맞춰 볼 수 있게 합니다.
    """
    import chart_signals as _cs  # noqa: PLC0415

    if series is None or not series.ok:
        why = getattr(series, "error", "") or "일봉을 받지 못했습니다."
        return f'<div class="dash-screen-err">{_esc(why)}</div>'
    n, fwd = series.n, series.fwd
    total = n + fwd
    slot = _KC_W / total
    row = series.row
    st = (row.states if row is not None else {}) or {}

    def X(i):
        return _kc_x(i, total)

    today_x = X(n - 1) + slot / 2
    # 오늘 뒤(앞 구름 자리)는 옅게 — 어디까지가 실제 봉인지 보이게
    guide = (f'<rect class="kc-fwd" x="{today_x:.1f}" y="0" width="{_KC_W - today_x:.1f}" '
             'height="100%"/>'
             f'<line class="kc-today" x1="{today_x:.1f}" y1="0" x2="{today_x:.1f}" y2="100%"/>')

    def tag(text: str) -> str:
        return f'<em>{_esc(text)}</em>' if text else ""

    def sw(cls: str, label: str, value: str) -> str:
        return f'<span><i class="{cls}"></i>{_esc(label)} <b>{_esc(value)}</b></span>'

    # ── 1. 가격 ────────────────────────────────────────────────────────────
    H1 = 280
    vals = [v for v in series.high + series.low if v is not None]
    for extra in (series.ma20, series.ma60, series.ma120, series.bb_up, series.bb_lo,
                  series.span_a, series.span_b):
        vals += [v for v in extra if v is not None]
    lo, hi = min(vals), max(vals)
    padv = (hi - lo) * 0.03 or 1.0
    lo, hi = lo - padv, hi + padv
    Y1 = _kc_scale(lo, hi, H1, 4)
    parts = [guide]
    a, b = list(series.span_a), list(series.span_b)
    for bull, s0, e0 in _cloud_runs(a, b):
        if e0 <= s0:
            continue
        top = " ".join(f"{X(i):.1f},{Y1(a[i]):.1f}" for i in range(s0, e0 + 1))
        bot = " ".join(f"{X(i):.1f},{Y1(b[i]):.1f}" for i in range(e0, s0 - 1, -1))
        parts.append(f'<polygon class="{"kc-bull" if bull else "kc-bear"}" points="{top} {bot}"/>')
    parts.append(_kc_segments(a, total, Y1, "kc-sa"))
    parts.append(_kc_segments(b, total, Y1, "kc-sb"))
    parts.append(_kc_segments(series.bb_up, total, Y1, "kc-bb"))
    parts.append(_kc_segments(series.bb_lo, total, Y1, "kc-bb"))
    bw = slot * 0.66
    ref = series.close[-1]
    for i in range(n):
        o, h, l, c = series.open[i], series.high[i], series.low[i], series.close[i]
        cls = "kc-up" if c >= o else "kc-dn"
        y0, y1 = Y1(max(o, c)), Y1(min(o, c))
        x = X(i)
        tip = (f"{series.dates[i]} 시 {_kc_num(o, ref)} 고 {_kc_num(h, ref)} "
               f"저 {_kc_num(l, ref)} 종 {_kc_num(c, ref)}")
        parts.append(
            f'<g class="{cls}"><title>{_esc(tip)}</title>'
            f'<line x1="{x:.1f}" y1="{Y1(h):.1f}" x2="{x:.1f}" y2="{Y1(l):.1f}"/>'
            f'<rect x="{x - bw / 2:.1f}" y="{y0:.1f}" width="{bw:.1f}" '
            f'height="{max(y1 - y0, 0.8):.1f}"/></g>')
    parts.append(_kc_segments(series.ma120, total, Y1, "kc-m3"))
    parts.append(_kc_segments(series.ma60, total, Y1, "kc-m2"))
    parts.append(_kc_segments(series.ma20, total, Y1, "kc-m1"))
    cloud = ("" if row is None or row.ichi.bullish_cloud is None else
             ("양운" if row.ichi.bullish_cloud else "음운"))
    title1 = (f'<span><b>{_esc(series.name)}</b> 종가 <b>{_kc_num(ref)}</b></span>'
              + sw("kc-m1", f"{_cs.MA_SHORT}일", _kc_num(series.ma20[-1], ref))
              + sw("kc-m2", f"{_cs.MA_MID}일", _kc_num(series.ma60[-1], ref))
              + sw("kc-m3", f"{_cs.MA_LONG}일", _kc_num(series.ma120[-1], ref))
              + '<span><i class="kc-bb"></i>볼린저</span>'
              + f'<span><i class="kc-cloud"></i>일목 구름</span>{tag(cloud)}{tag(st.get("ma", ""))}'
              + tag(st.get("bb", "")))
    panels = [_kc_panel(H1, "".join(parts), title1,
                        [(v, _kc_num(v, ref)) for v in _kc_ticks(lo, hi, 5)], Y1, "kc-price")]

    # ── 2. 거래량 ──────────────────────────────────────────────────────────
    if any(v for v in series.volume):
        H2 = 46
        vmax = max(series.volume) or 1.0
        Y2 = _kc_scale(0.0, vmax, H2, 3)
        bars = [guide]
        for i in range(n):
            v = series.volume[i] or 0.0
            cls = "kc-up" if series.close[i] >= series.open[i] else "kc-dn"
            bars.append(f'<rect class="kc-vol {cls}" x="{X(i) - bw / 2:.1f}" y="{Y2(v):.1f}" '
                        f'width="{bw:.1f}" height="{max(Y2(0) - Y2(v), 0.5):.1f}"/>')
        ratio = "" if row is None or row.vol_ratio is None else f"20일 평균의 {row.vol_ratio:.1f}배"
        panels.append(_kc_panel(H2, "".join(bars),
                                f'<span>거래량 <b>{_esc(ratio)}</b></span>', [], Y2))

    def refline(Y, v, cls="kc-ref"):
        return f'<line class="{cls}" x1="0" y1="{Y(v):.1f}" x2="{_KC_W:.0f}" y2="{Y(v):.1f}"/>'

    HI = 76
    # ── 3. CCI ─────────────────────────────────────────────────────────────
    cv = [v for v in series.cci + series.cci_sig if v is not None]
    if cv:
        clo, chi = min(min(cv), -160.0), max(max(cv), 160.0)
        Yc = _kc_scale(clo, chi, HI)
        svg = (guide + refline(Yc, _cs.CCI_OVERBOUGHT) + refline(Yc, _cs.CCI_OVERSOLD)
               + refline(Yc, _cs.CCI_MID, "kc-zero")
               + _kc_segments(series.cci_sig, total, Yc, "kc-l2")
               + _kc_segments(series.cci, total, Yc, "kc-l1"))
        t = (sw("kc-l1", f"CCI({_cs.CCI_WINDOW})", "—" if series.cci[-1] is None else f"{series.cci[-1]:+.0f}")
             + sw("kc-l2", f"시그널 {_cs.CCI_SIGNAL}",
                  "—" if series.cci_sig[-1] is None else f"{series.cci_sig[-1]:+.0f}")
             + tag(st.get("cci", "")))
        panels.append(_kc_panel(HI, svg, t, [(_cs.CCI_OVERBOUGHT, "+100"), (_cs.CCI_MID, "0"),
                                             (_cs.CCI_OVERSOLD, "−100")], Yc))
    # ── 4. MACD ────────────────────────────────────────────────────────────
    mv = [v for v in series.macd + series.macd_sig + series.macd_hist if v is not None]
    if mv:
        m = max(abs(min(mv)), abs(max(mv))) or 1.0
        Ym = _kc_scale(-m, m, HI)
        svg = [guide, refline(Ym, 0.0, "kc-zero")]
        for i, h in enumerate(series.macd_hist):
            if h is None:
                continue
            y0, y1 = sorted((Ym(h), Ym(0.0)))
            svg.append(f'<rect class="kc-hist {"pos" if h > 0 else "neg"}" x="{X(i) - bw / 2:.1f}" '
                       f'y="{y0:.1f}" width="{bw:.1f}" height="{max(y1 - y0, 0.4):.1f}"/>')
        svg.append(_kc_segments(series.macd_sig, total, Ym, "kc-l2"))
        svg.append(_kc_segments(series.macd, total, Ym, "kc-l1"))
        mref = m
        t = (sw("kc-l1", f"MACD({_cs.MACD_FAST},{_cs.MACD_SLOW})", _kc_num(series.macd[-1], mref))
             + sw("kc-l2", f"시그널 {_cs.MACD_SIGNAL}", _kc_num(series.macd_sig[-1], mref))
             + f'<span>막대 = 둘의 차이 <b>{_esc(_kc_num(series.macd_hist[-1], mref))}</b></span>'
             + tag(st.get("macd", "")))
        panels.append(_kc_panel(HI, "".join(svg), t, [(0.0, "0")], Ym))
    # ── 5. 스토캐스틱 ──────────────────────────────────────────────────────
    if any(v is not None for v in series.stoch_k):
        Ys = _kc_scale(0.0, 100.0, HI)
        svg = (guide + refline(Ys, _cs.STOCH_OVERBOUGHT) + refline(Ys, _cs.STOCH_OVERSOLD)
               + refline(Ys, _cs.STOCH_MID, "kc-zero")
               + _kc_segments(series.stoch_d, total, Ys, "kc-l2")
               + _kc_segments(series.stoch_k, total, Ys, "kc-l1"))
        k, d = series.stoch_k[-1], series.stoch_d[-1]
        t = (sw("kc-l1", f"스토캐스틱 슬로우({_cs.STOCH_N},{_cs.STOCH_K},{_cs.STOCH_D}) %K",
                "—" if k is None else f"{k:.0f}")
             + sw("kc-l2", "%D", "—" if d is None else f"{d:.0f}") + tag(st.get("stoch", "")))
        panels.append(_kc_panel(HI, svg, t, [(_cs.STOCH_OVERBOUGHT, f"{_cs.STOCH_OVERBOUGHT:g}"),
                                             (_cs.STOCH_MID, f"{_cs.STOCH_MID:g}"),
                                             (_cs.STOCH_OVERSOLD, f"{_cs.STOCH_OVERSOLD:g}")], Ys))
    # ── 6. DMI ─────────────────────────────────────────────────────────────
    dv = [v for v in series.pdi + series.mdi + series.adx if v is not None]
    if dv:
        dhi = max(max(dv), 45.0)
        Yd = _kc_scale(0.0, dhi, HI)
        svg = (guide + "".join(refline(Yd, lv) for lv in _cs.MDI_LEVELS)
               + _kc_segments(series.adx, total, Yd, "kc-l3")
               + _kc_segments(series.pdi, total, Yd, "kc-l2")
               + _kc_segments(series.mdi, total, Yd, "kc-l1"))

        def n0(v):
            return "—" if v is None else f"{v:.0f}"
        t = (sw("kc-l1", f"−DI({_cs.DMI_WINDOW})", n0(series.mdi[-1]))
             + sw("kc-l2", "+DI", n0(series.pdi[-1])) + sw("kc-l3", "ADX", n0(series.adx[-1]))
             + tag(st.get("dmi", "")))
        panels.append(_kc_panel(HI, svg, t, [(lv, f"{lv:g}") for lv in _cs.MDI_LEVELS], Yd))

    # ── 날짜 눈금 — 달이 바뀌는 자리 ───────────────────────────────────────
    marks, prev = [], ""
    for i, day in enumerate(series.dates):
        ym = day[:7]
        # 왼쪽 끝과 '오늘' 글자 바로 옆의 달 표시는 겹치므로 뺍니다
        if ym and ym != prev and 3 <= i <= n - 1 - max(6, n // 14):
            marks.append(f'<span style="left:{X(i) / _KC_W * 100:.2f}%">{int(day[5:7])}월</span>')
        prev = ym or prev
    marks.append(f'<span class="now" style="left:{today_x / _KC_W * 100:.2f}%">'
                 f'{_esc(series.dates[-1][5:].replace("-", "/")) or "오늘"}</span>')
    more = (f'<a class="dash-inline-link" target="_blank" rel="noopener noreferrer" '
            f'href="{_esc(link)}">{_esc(link_label or "원본 차트")} ↗</a>'
            if link.startswith("https://") else "")
    foot = (f'<div class="kc-foot">최근 {n}봉 · 세로 점선 오른쪽은 일목 구름이 그려지는 '
            f'앞 {fwd}봉 자리 · 봉에 마우스를 올리면 시·고·저·종 {more}</div>')
    return ('<div class="dash-kchart" role="img" '
            f'aria-label="{_esc(series.name)} 일봉 차트와 지표">'
            + "".join(panels)
            + f'<div class="kc-dates"><div class="kc-plot">{"".join(marks)}</div></div>'
            + foot + "</div>")


def render_chart_detail(row, conditions) -> str:
    """종목 하나 — 구름 차트 + 조건별 상태와 값."""
    f, nt = row.flags(), row.notes()
    ic = row.ichi

    def n0(v):
        return fmt_num(v, 0 if v >= 1000 else 2)

    vol = ("" if row.vol_ratio is None else
           f" · 거래량 20일 평균의 {row.vol_ratio:.1f}배")
    vals = {
        "cloud": ("—" if ic.lead_a is None or ic.lead_b is None else
                  f"앞 구름 선행스팬1 {n0(ic.lead_a)} · 선행스팬2 {n0(ic.lead_b)}"
                  + (f" · {ic.twist}" if ic.twist else "")
                  + ("" if ic.span_a is None or ic.span_b is None else
                     f" · 오늘 자리 {n0(ic.span_a)} / {n0(ic.span_b)}")),
        "ma": ("—" if row.ma20 is None else
               f"20일 {n0(row.ma20)}"
               + ("" if row.ma60 is None else f" · 60일 {n0(row.ma60)}")
               + ("" if row.ma120 is None else f" · 120일 {n0(row.ma120)}")
               + ("" if row.disparity is None else f" · 이격도 {row.disparity:.1f}")),
        "bb": ("—" if row.bb_pctb is None else
               f"%B {row.bb_pctb:.2f}"
               + ("" if row.bb_width_rank is None else
                  f" · 밴드폭이 최근 120일 중 좁은 쪽 {row.bb_width_rank:.0f}% 자리")),
        "cci": ("—" if row.cci is None else
                f"CCI {row.cci:+.1f}" + ("" if row.cci_signal is None
                                         else f" · 시그널 {row.cci_signal:+.1f}")),
        "macd": ("—" if row.macd is None else
                 f"MACD {row.macd:+.2f} · 시그널 {row.macd_signal:+.2f}"),
        "stoch": ("—" if row.stoch_k is None else
                  f"%K {row.stoch_k:.1f}" + ("" if row.stoch_d is None
                                             else f" · %D {row.stoch_d:.1f}")),
        "dmi": ("—" if row.minus_di is None else
                f"−DI {row.minus_di:.1f} · +DI {row.plus_di:.1f}"
                + ("" if row.adx is None else f" · ADX {row.adx:.1f}") + vol),
    }
    lines = []
    for key, name, rule in conditions:
        met = f.get(key)
        cls = "cd-yes" if met else ("cd-na" if met is None else "cd-no")
        if met is None:
            verdict = "판정 불가"
        elif key == "cloud":
            verdict = ("양운" if met else "음운") + (f" · {nt[key]}" if nt[key] else "")
        elif key == "dmi":
            verdict = nt[key].split(" · ")[0] if met else "해당 없음"
        else:
            verdict = nt[key] if met else "해당 없음"
        lines.append(
            f'<div class="cd-row {cls}"><span class="cd-name">{_esc(name)}</span>'
            f'<span class="cd-verdict">{_esc(verdict)}</span>'
            f'<span class="cd-val">{_esc(vals[key])}</span>'
            f'<span class="cd-rule">{clamp(_esc(rule), limit=24, one=True)}</span></div>')
    legend = ('<div class="cd-legend"><span class="lg-price">종가</span>'
              '<span class="lg-bull">양운</span><span class="lg-bear">음운</span>'
              f"<span>최근 {len(row.spark)}거래일 · 세로선 오른쪽이 앞 구름</span></div>"
              if row.spark else
              # 수집기 파일(chart_kr.json)에서 온 줄은 작은 차트용 봉이 없습니다
              '<div class="cd-legend"><span>작은 차트 없음 — 위 \'차트\' 칸에서 종목을 '
              '고르면 봉 차트를 그립니다</span></div>')
    return ('<div class="dash-cdetail">' + render_cloud_chart(row) + legend
            + "".join(lines) + "</div>")


# ──────────────────────────────────────────────────────────────────────────────
# 매크로 화면 — 표로 줄인 구성 (2026-11-11 개편)
# ──────────────────────────────────────────────────────────────────────────────
#
# 매크로 화면은 세로 5,000px 가 넘었습니다: 시세 카드 7장, 임계값 카드
# 6장(각각 헤드라인 포함), 지표 카드 14장. 같은 모양의 큰 카드가 이어져
# 무엇이 중요한지 위치로 드러나지 않았습니다. 시세와 지표는 **표**로,
# 임계값은 **한 줄 목록**으로 줄이고 자세한 내용은 접어 둡니다.

def render_quote_table(rows) -> str:
    """시세 표. rows: [(Instrument, Quote|None)]. 카드 격자를 대신합니다."""
    if not rows:
        return ""
    body = []
    for inst, q in rows:
        ok = q is not None and q.ok
        scale = getattr(inst, "scale", 1.0) or 1.0
        unit = getattr(inst, "suffix", "") or ""
        link = inst.resolved_link() if hasattr(inst, "resolved_link") else ""
        name = (f'<a href="{_esc(link)}" target="_blank" rel="noopener">'
                f"{_esc(inst.name)}</a>" if link else _esc(inst.name))
        if not ok:
            why = (getattr(q, "error", None) or "데이터 없음") if q is not None \
                else "데이터 없음"
            body.append(
                f"<tr><td class='hd-name'>{name}<span>{_esc(inst.symbol)}</span></td>"
                f"<td class='hd-num'>—</td>"
                f"<td class='qt-err' colspan='2'>{_esc(str(why)[:80])}</td></tr>")
            continue
        pct, chg = q.change_pct, q.change
        cls = direction_class(pct) if pct is not None else "flat"
        # 금리처럼 단위가 % 인 값의 변화는 %p 입니다 (4.09% → 4.21% 는 +0.12%p)
        chg_unit = "%p" if unit == "%" else unit
        chg_txt = ("—" if chg is None
                   else fmt_signed(chg * scale, inst.decimals) + chg_unit)
        pct_txt = "—" if pct is None else f"{direction_glyph(pct)}{fmt_pct(pct)}"
        body.append(
            f"<tr><td class='hd-name'>{name}<span>{_esc(inst.symbol)}</span></td>"
            f"<td class='hd-num'>{_esc(fmt_num(q.price * scale, inst.decimals) + unit)}</td>"
            f"<td class='hd-num {cls}'>{_esc(chg_txt)}</td>"
            f"<td class='hd-num {cls}'>{pct_txt}</td></tr>")
    return ('<div class="dash-htable-wrap"><table class="dash-htable dash-hold dash-qt">'
            "<thead><tr><th>지표</th><th>현재</th><th>전일 대비</th><th>등락률</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


def render_trigger_list(triggers) -> str:
    """임계값에 닿은 지표 — 한 줄씩. 헤드라인·질문은 접힌 상세에 둡니다."""
    if not triggers:
        return ""
    rows = []
    for t in triggers:
        spec = t.reading.spec
        sev_class = {3: "now", 2: "soon", 1: "fyi"}.get(t.severity, "fyi")
        sev_label = {3: "지금", 2: "이번 주", 1: "참고"}.get(t.severity, "")
        rule = _MACRO_RULE_LABEL.get(t.rule, t.rule)
        rows.append(
            f'<div class="tl-row {sev_class}">'
            f'<span class="dash-sig-chip {sev_class}">{_esc(sev_label)}</span>'
            f'<div class="tl-main"><div class="tl-title">{_esc(t.title)}</div>'
            f'<div class="tl-detail">{_esc(t.detail)}</div></div>'
            f'<span class="tl-tag">{_esc(spec.series_id)} · {_esc(rule)}</span>'
            "</div>")
    return '<div class="dash-tlist">' + "".join(rows) + "</div>"


def render_macro_table(groups, by_group: dict, hit_keys: set,
                       *, show_why: bool = False) -> str:
    """경제지표 전체 — 묶음별 표. groups: [(키, 제목, 부제)].

    카드 14장 대신 표 한 장입니다. 줄마다 현재값 · 직전 대비 · 최근 흐름 ·
    관측 시점. 임계값에 닿은 줄은 왼쪽 막대와 '임계값' 표시로 구분합니다.
    방향은 기호로만 적고 색으로 좋고 나쁨을 암시하지 않습니다 (금리가
    오른 것이 좋은지는 보는 사람의 포지션에 달렸습니다).
    """
    body = []
    for key, title, subtitle in groups:
        readings = by_group.get(key) or []
        if not readings:
            continue
        body.append(
            f"<tr class='mt-group'><td colspan='5'><b>{_esc(title)}</b>"
            f"<span>{_esc(subtitle)}</span></td></tr>")
        for r in readings:
            spec = r.spec
            hit = spec.key in hit_keys
            flag = '<i class="mt-flag">임계값</i>' if hit else ""
            unv = "" if spec.verified else '<i class="mt-unv">미검증</i>'
            name = (f"<td class='mt-name'><b>{_esc(spec.name)}</b>{flag}{unv}"
                    f"<span>{_esc(spec.series_id)}</span></td>")
            if not r.ok:
                body.append(f"<tr class='mt-err'>{name}"
                            f"<td colspan='4'>{_esc(r.error)}</td></tr>")
                continue
            arrow = "—"
            if r.delta is not None and r.delta != 0:
                arrow = f"{'▲' if r.delta > 0 else '▼'} {_esc(r.delta_label)}"
            # 'N일 전' 대신 **언제 것인지**와 **다음에 언제 나오는지** 를 적습니다
            lag = (f"<span class='late'>발표 지연 · {r.lag_days}일째</span>"
                   if r.stale and r.lag_days is not None
                   else f"<span>{_esc(r.cadence_label)}</span>")
            live = (f"<i class='mt-live'>{_esc(r.live_label)}</i>"
                    if r.live_label else "")
            body.append(
                f"<tr class='{'mt-hit' if hit else ''}'>{name}"
                f"<td class='mt-val'>{_esc(r.value_label)}{live}</td>"
                f"<td class='mt-delta'>{arrow}</td>"
                f"<td class='mt-spark'>{render_macro_spark(r.history, width=120, height=24)}</td>"
                f"<td class='mt-obs'>{_esc(r.period_label)}{lag}</td></tr>")
            extra = []
            if show_why and spec.why:
                extra.append(_safe_inline(spec.why))
            if r.warning:
                extra.append(_safe_inline(r.warning))
            if extra:
                body.append("<tr class='mt-why'><td colspan='5'>"
                            + "<br>".join(extra) + "</td></tr>")
    if not body:
        return ""
    return ('<div class="dash-htable-wrap"><table class="dash-htable dash-mt">'
            "<thead><tr><th>지표</th><th>현재값</th><th>직전 대비</th>"
            "<th>최근 흐름</th><th>관측 시점</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


# ──────────────────────────────────────────────────────────────────────────────
# 전일 장 브리핑
# ──────────────────────────────────────────────────────────────────────────────

def render_daily_brief(brief, headlines=(), reports=()) -> str:
    """한 시장의 마지막 거래일 — 지수 칸 + 문장 몇 줄 + 마감 기사 제목.

    '왜' 는 적지 않습니다 (daily_brief.py 머리말). 이유는 기사·리포트 링크로.
    """
    if brief is None:
        return ""
    if not brief.ok:
        return ('<div class="dash-db"><div class="db-head"><b>'
                f'{_esc(brief.title)}</b></div><div class="db-err">브리핑을 만들지 '
                f'못했습니다 — {_esc(brief.error)}</div></div>')
    cells = []
    for m in brief.indices:
        cls = direction_class(m.pct) if m.ok else "flat"
        val = "—" if not m.ok else (f"{m.close:,.2f}" if m.close < 10_000
                                    else f"{m.close:,.0f}")
        chg = (f'{direction_glyph(m.pct)}{_esc(m.change_label)}' if m.ok else "")
        cells.append(f'<div class="db-cell"><div class="db-l">{_esc(m.label)}</div>'
                     f'<div class="db-v">{val}</div>'
                     f'<div class="db-c {cls}">{chg}</div></div>')
    live = ('<span class="db-live">오늘 장은 아직 끝나지 않아 뺐습니다</span>'
            if brief.in_progress else "")
    lines = "".join(
        f'<div class="db-line"><span>{_esc(tag)}</span><div>{_esc(text)}</div></div>'
        for tag, text in brief.lines if tag != "지수")
    miss = (f'<div class="db-miss">값을 못 받은 항목: '
            f'{_esc(", ".join(brief.missing[:8]))}</div>' if brief.missing else "")
    news = render_news_block(list(headlines or ()), limit=3, title="마감 기사")
    rep = ""
    if reports:
        items = "".join(
            f'<li><a class="dash-inline-link" target="_blank" rel="noopener noreferrer" '
            f'href="{_esc(r.link)}">{_esc(r.title)}</a> '
            f'<span>{_esc(r.broker)} · {_esc(r.date)}</span></li>'
            for r in list(reports)[:4] if r.link.startswith(("https://", "http://")))
        rep = ('<div class="db-rep"><div class="db-rep-h">증권사 시황 리포트</div>'
               f"<ul>{items}</ul></div>")
    return (f'<div class="dash-db"><div class="db-head"><b>{_esc(brief.title)}</b>'
            f'<span>{_esc(brief.session_label)} 마감 기준</span>{live}</div>'
            f'<div class="db-cells">{"".join(cells)}</div>{lines}{miss}{news}{rep}</div>')


# ──────────────────────────────────────────────────────────────────────────────
# 산업 리포트
# ──────────────────────────────────────────────────────────────────────────────

def render_research_counts(groups, top: int = 12) -> str:
    """업종별 보고서 수 — 가로 막대. 어느 업종에 리포트가 몰리는지."""
    groups = list(groups or [])[:top]
    if not groups:
        return ""
    peak = max(len(rs) for _c, rs in groups) or 1
    rows = "".join(
        f'<div class="rc-row"><div class="rc-name">{_esc(cat)}</div>'
        f'<div class="rc-track"><i style="width:{len(rs) / peak * 100:.0f}%"></i></div>'
        f'<div class="rc-n">{len(rs)}</div></div>'
        for cat, rs in groups)
    return f'<div class="dash-rc">{rows}</div>'


def render_research_table(reports, limit: int = 40, *, show_category: bool = True) -> str:
    """리포트 목록 — 제목은 원문(PDF 또는 상세 페이지)으로 가는 링크."""
    reports = list(reports or [])[:limit]
    if not reports:
        return ""
    body = []
    for r in reports:
        cat = f"<td class='rt-cat'>{_esc(r.category or '—')}</td>" if show_category else ""
        link = (f'<a class="dash-inline-link" target="_blank" rel="noopener noreferrer" '
                f'href="{_esc(r.link)}">{_esc(r.title)}</a>'
                if r.link.startswith(("https://", "http://")) else _esc(r.title))
        pdf = ' <span class="rt-pdf">PDF</span>' if r.pdf else ""
        body.append(f"<tr><td class='rt-date'>{_esc(r.date[5:] if r.date else '—')}</td>"
                    f"{cat}<td class='rt-title'>{link}{pdf}</td>"
                    f"<td class='rt-broker'>{_esc(r.broker)}</td></tr>")
    head_cat = "<th>업종</th>" if show_category else ""
    return ('<div class="dash-htable-wrap"><table class="dash-htable dash-rt">'
            f"<thead><tr><th>날짜</th>{head_cat}<th>제목</th><th>증권사</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def render_digest(lines, words=None) -> str:
    """묶음 요약 — 첫 줄은 굵게, '자주 나온 말' 은 칩으로."""
    lines = [ln for ln in (lines or []) if ln and not ln.startswith("자주 나온 말")]
    if not lines and not words:
        return ""
    head = f'<div class="dg-head">{_esc(lines[0])}</div>' if lines else ""
    rest = "".join(f'<div class="dg-line">{_esc(ln)}</div>' for ln in lines[1:])
    chips = ""
    if words:
        chips = ('<div class="dg-words"><span class="dg-cap">자주 나온 말</span>'
                 + "".join(f'<span class="dg-chip">{_esc(w)} <b>{n}</b></span>'
                           for w, n in words)
                 + "</div>")
    return f'<div class="dash-digest">{head}{chips}{rest}</div>'


def _goal_won(value) -> str:
    return "" if not value else f"{value:,.0f}원"


def render_ai_summary(item: dict) -> str:
    """AI 요약 한 건 (HTML). item: report_summary.entry 가 만든 묶음."""
    import report_summary  # noqa: PLC0415

    parts = []
    for head, lines in report_summary.blocks(item.get("summary") or ""):
        if head:
            parts.append(f'<div class="ai-h">{_esc(head)}</div>')
        if lines:
            parts.append("<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in lines) + "</ul>")
    if not parts:
        return ""
    model = str(item.get("model") or "").strip()
    tag = "AI 요약" + (f" · {_esc(model)}" if model else "")
    try:
        total, sent = int(item.get("pages_total") or 0), int(item.get("pages_sent") or 0)
    except (TypeError, ValueError):
        total = sent = 0
    if total and sent and sent < total:
        tag += f" · 앞 {sent}쪽만 읽음 (전체 {total}쪽)"
    return (f'<div class="rp-ai"><span class="ai-tag">{tag}</span>'
            + "".join(parts) + "</div>")


def render_report_cards(reports, limit: int = 12, *, show_stock: bool = False,
                        show_opinion: bool = True, summaries: dict | None = None) -> str:
    """리포트 한 건 = 카드 한 장. 제목(원문 링크) · 미리보기 · 증권사 의견.

    휴대폰에서 표보다 읽기 쉽게 세로로 쌓습니다. 미리보기는 본문 앞부분만
    이고, 의견·목표주가는 **증권사가 낸 것**임을 줄마다 적습니다.
    summaries({이름: 항목})에 요약이 있는 리포트는 미리보기 대신 AI 요약을
    보여 줍니다 — 누가 쓴 글인지 헷갈리지 않게 'AI 요약' 표시를 붙입니다.
    """
    import report_summary  # noqa: PLC0415

    summaries = summaries or {}
    reports = list(reports or [])[:limit]
    if not reports:
        return ""
    cards = []
    for r in reports:
        link = getattr(r, "link", "") or ""
        page = getattr(r, "url", "") or ""
        title = (f'<a class="dash-inline-link" target="_blank" rel="noopener noreferrer" '
                 f'href="{_esc(page or link)}">{_esc(r.title)}</a>'
                 if (page or link).startswith(("https://", "http://")) else _esc(r.title))
        who = " · ".join(x for x in (
            (r.date[5:] if r.date else ""), r.broker,
            (getattr(r, "item_name", "") if show_stock else "")) if x)
        pdf = getattr(r, "pdf", "") or ""
        pdf_link = (f' <a class="rp-pdf" target="_blank" rel="noopener noreferrer" '
                    f'href="{_esc(pdf)}">PDF</a>'
                    if pdf.startswith(("https://", "http://")) else "")
        preview = getattr(r, "preview", "") or ""
        body = f'<div class="rp-body">{_esc(preview)}</div>' if preview else ""
        item = summaries.get(report_summary.key_of(r))
        if isinstance(item, dict):
            body = render_ai_summary(item) or body
        meta = ""
        if show_opinion:
            bits = []
            op = getattr(r, "opinion", "") or ""
            if op:
                bits.append(f"의견 {_esc(op)}")
            goal = getattr(r, "goal_price", None)
            if goal:
                prev = getattr(r, "prev_goal_price", None)
                then = getattr(r, "price_then", None)
                moved = ""
                if prev and not (then and abs(prev - then) < 0.5) and abs(prev - goal) > 0.5:
                    moved = f" (직전 {_goal_won(prev)})"
                bits.append(f"목표주가 {_goal_won(goal)}{moved}")
            if bits:
                meta = ('<div class="rp-meta"><span class="rp-src">증권사 제시</span>'
                        + " · ".join(bits) + "</div>")
        cards.append(
            f'<div class="rp-card"><div class="rp-who">{_esc(who)}{pdf_link}</div>'
            f'<div class="rp-title">{title}</div>{body}{meta}</div>')
    return '<div class="dash-rp">' + "".join(cards) + "</div>"


def render_prompt_links(prompt: str, label: str = "Claude 에 요약 요청") -> str:
    """프롬프트가 채워진 채로 Claude 를 여는 링크 (앱 · 웹)."""
    import urllib.parse as _up

    q = _up.quote(prompt, safe="")
    return ('<div class="dash-skill-row">'
            f'<a class="dash-skill-btn" href="{APP_LINK.format(q=q)}">{_esc(label)} (앱)</a>'
            f'<a class="dash-skill-btn ghost" target="_blank" rel="noopener noreferrer" '
            f'href="{WEB_LINK.format(q=q)}">웹에서 열기</a></div>')


# ──────────────────────────────────────────────────────────────────────────────
# 수급 · 배당 · 실적 서프라이즈
# ──────────────────────────────────────────────────────────────────────────────

def _updown(v: float | None) -> str:
    if v is None or v == 0:
        return ""
    return "up" if v > 0 else "down"


def _eok(amount_won: float | None) -> str:
    """원 → '+123억' / '−4,560만' (부호 포함)."""
    if amount_won is None:
        return "—"
    a = abs(amount_won)
    sign = "+" if amount_won > 0 else "−" if amount_won < 0 else ""
    if a >= 1e12:
        return f"{sign}{a / 1e12:,.2f}조"
    if a >= 1e8:
        return f"{sign}{a / 1e8:,.0f}억"
    if a >= 1e4:
        return f"{sign}{a / 1e4:,.0f}만"
    return f"{sign}{a:,.0f}"


def _shares(q: float | None) -> str:
    if q is None:
        return ""
    a = abs(q)
    sign = "+" if q > 0 else "−" if q < 0 else ""
    if a >= 1e4:
        return f"{sign}{a / 1e4:,.1f}만주"
    return f"{sign}{a:,.0f}주"


def render_spark_bars(values, width: int = 84, height: int = 22) -> str:
    """일별 순매매 막대 (오래된 → 최신). 0 선 위는 순매수, 아래는 순매도."""
    vals = [v or 0.0 for v in (values or [])]
    if not vals or not any(vals):
        return ""
    peak = max(abs(v) for v in vals) or 1.0
    n = len(vals)
    bw = width / n
    mid = height / 2
    bars = []
    for i, v in enumerate(vals):
        h = abs(v) / peak * (mid - 1)
        y = mid - h if v > 0 else mid
        cls = "up" if v > 0 else "down"
        bars.append(f'<rect class="{cls}" x="{i * bw + 0.5:.1f}" y="{y:.1f}" '
                    f'width="{max(bw - 1, 1):.1f}" height="{max(h, 0.6):.1f}"/>')
    return (f'<svg class="dash-spark" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" '
            f'aria-label="최근 {n}일 외국인 순매매">'
            f'<line x1="0" y1="{mid}" x2="{width}" y2="{mid}"/>{"".join(bars)}</svg>')


def _flow_cell(s, who: str, n: int) -> str:
    amt = (s.amount.get(who) or {}).get(n)
    qty = (s.net.get(who) or {}).get(n)
    if amt is None and qty is None:
        return "<td class='na'>—</td>"
    return (f"<td class='{_updown(amt if amt is not None else qty)}'>"
            f"<b>{_eok(amt)}</b><span class='sub'>{_shares(qty)}</span></td>")


def _streak_txt(n: int | None) -> str:
    if not n:
        return "—"
    return f"<span class='{_updown(n)}'>{'+' if n > 0 else '−'}{abs(n)}일</span>"


def render_flow_table(sums) -> str:
    """종목별 외국인·기관 순매매 표."""
    if not sums:
        return render_footnote("<b>볼 종목이 없습니다.</b> 관심종목이나 보유에 "
                               "국내 종목을 넣으십시오.")
    ok = [s for s in sums if not s.error and s.days]
    bad = [s for s in sums if s.error or not s.days]
    rows = []
    for s in ok:
        star = "<i class='ct-star' title='보유'>★</i>" if s.held else ""
        ratio = "—" if s.ratio is None else f"{s.ratio:.2f}%"
        chg = ("" if s.ratio_change is None else
               f"<span class='sub {_updown(s.ratio_change)}'>"
               f"{s.ratio_change:+.2f}%p · 20일</span>")
        share = ("" if s.vol_share20 is None else
                 f"<span class='sub'>거래량의 {s.vol_share20:+.1f}%</span>")
        rows.append(
            "<tr>"
            f"<td>{star}<b>{_esc(s.name)}</b><span class='sub'>{_esc(s.code)}</span></td>"
            + _flow_cell(s, "foreign", 5) + _flow_cell(s, "foreign", 20)
            + _flow_cell(s, "inst", 5) + _flow_cell(s, "inst", 20)
            + f"<td>외 {_streak_txt(s.streak.get('foreign'))}"
              f"<span class='sub'>기 {_streak_txt(s.streak.get('inst'))}</span></td>"
            + f"<td>{ratio}{chg}</td>"
            + f"<td class='spark'>{render_spark_bars(s.spark)}{share}</td>"
            "</tr>")
    table = ""
    if rows:
        table = (
            '<div class="dash-table-wrap"><table class="dash-table dash-flowt">'
            "<thead><tr><th>종목</th><th>외국인 5일</th><th>외국인 20일</th>"
            "<th>기관 5일</th><th>기관 20일</th><th>연속</th>"
            "<th>외국인 보유율</th><th>외국인 20일 흐름</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")
    miss = ""
    if bad:
        miss = render_notice(
            "<b>받지 못한 종목:</b> " + " · ".join(
                f"{_esc(s.name)}({_esc(s.error or '데이터 없음')})" for s in bad[:8])
            + (f" 외 {len(bad) - 8}" if len(bad) > 8 else ""))
    return table + miss


def render_dividend_table(views, today, market: str = "kr") -> str:
    """배당 일정 표 — 고른 시장 먼저, 그 안에서 다음 배당락이 가까운 순."""
    has = [v for v in views if v.count]
    none = [v for v in views if not v.count]

    def key(v):
        d = v.days_to_next(today)
        return (0 if v.market == market else 1, d if d is not None else 9999,
                v.name)

    rows = []
    for v in sorted(has, key=key):
        d = v.days_to_next(today)
        dd = ("" if d is None else "오늘" if d == 0 else f"D-{d}")
        basis = (f"<span class='dv-b {'ann' if v.next_basis == '발표' else 'est'}'>"
                 f"{_esc(v.next_basis)}</span>" if v.next_basis else "")
        money = (lambda x: "—" if x is None else
                 (f"{x:,.0f}원" if v.market == "kr" else f"${x:,.2f}"))
        star = "<i class='ct-star' title='보유'>★</i>" if v.held else ""
        dim = "" if v.market == market else " class='dv-other'"
        rows.append(
            f"<tr{dim}>"
            f"<td>{star}<b>{_esc(v.name)}</b><span class='sub'>{_esc(v.symbol)}</span></td>"
            f"<td>{_esc(v.freq or '—')}</td>"
            f"<td>{_esc(v.next_ex[5:] if v.next_ex else '—')} {basis}"
            f"<span class='sub'>{dd}</span></td>"
            f"<td>{money(v.last_amount)}<span class='sub'>"
            f"{_esc(v.last_ex[2:] if v.last_ex else '')}</span></td>"
            f"<td>{money(v.ttm)}</td>"
            f"<td>{'—' if v.yield_pct is None else f'{v.yield_pct:.2f}%'}</td>"
            f"<td class='note'>{_esc(v.note or v.error)}</td>"
            "</tr>")
    table = ""
    if rows:
        table = (
            '<div class="dash-table-wrap"><table class="dash-table dash-divt">'
            "<thead><tr><th>종목</th><th>주기</th><th>다음 배당락</th>"
            "<th>직전 배당</th><th>12개월 합</th><th>시가배당률</th>"
            "<th>메모</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")
    tail = ""
    if none:
        tail = render_notice("<b>배당 이력이 없는 종목:</b> " + " · ".join(
            f"{_esc(v.name)}" + (f"({_esc(v.error[:40])})" if v.error else "")
            for v in none))
    return table + tail + render_footnote(
        "<b>배당락일</b>은 그날 사면 이번 배당을 못 받는 첫날입니다 — 받으려면 "
        "그 전 거래일까지 사야 합니다. <b>발표</b>는 야후에 회사 발표일이 있는 "
        "경우, <b>추정</b>은 직전 배당 간격을 더한 날짜라 일정이 아닙니다. "
        "한국은 2023년 제도 개선 뒤 배당기준일을 주주총회 뒤로 옮기는 회사가 "
        "있어 작년 날짜로 추정하면 크게 틀릴 수 있습니다 — 배당 결정 공시로 "
        "확인하십시오. 시가배당률은 최근 12개월 합 ÷ 현재가 (특별배당이 끼면 "
        "부풀려 보입니다).")


def _pct_txt(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"<span class='{_updown(v)}'>{v:+.{digits}f}%</span>"


def render_us_earnings(views, today) -> str:
    """미국 — 최근 4분기 EPS 서프라이즈 + 다음 발표."""
    ok = [v for v in views if v.reported or v.next_date]
    none = [v for v in views if not (v.reported or v.next_date)]
    rows = []
    for v in sorted(ok, key=lambda x: (0 if x.held else 1, x.next_date or "9")):
        chips = "".join(
            f"<span class='es-q {_updown(q.surprise)}' title='추정 "
            f"{'—' if q.estimate is None else f'{q.estimate:.2f}'} → 실제 "
            f"{'—' if q.reported is None else f'{q.reported:.2f}'}'>"
            f"<b>{_esc(q.date[2:7].replace('-', '.'))}</b>"
            f"{_pct_txt(q.surprise)}"
            f"<i>{'—' if q.reported is None else f'{q.reported:.2f}'} / "
            f"{'—' if q.estimate is None else f'{q.estimate:.2f}'}</i></span>"
            for q in v.reported)
        n = len(v.reported)
        hit = f"{v.beats}/{n}" if n else "—"
        nxt = "—"
        if v.next_date:
            days = (dt.date.fromisoformat(v.next_date) - today).days
            nxt = (f"{_esc(v.next_date[5:])}<span class='sub'>D-{days} · 추정 "
                   f"{'—' if v.next_estimate is None else f'{v.next_estimate:.2f}'}"
                   "</span>")
        star = "<i class='ct-star' title='보유'>★</i>" if v.held else ""
        rows.append(
            f"<tr><td>{star}<b>{_esc(v.name)}</b><span class='sub'>{_esc(v.symbol)}</span></td>"
            f"<td class='es-cell'>{chips or '—'}</td><td>{hit}</td><td>{nxt}</td></tr>")
    table = ""
    if rows:
        table = (
            '<div class="dash-table-wrap"><table class="dash-table dash-est">'
            "<thead><tr><th>종목</th><th>최근 4분기 (서프라이즈 · 실제 / 추정 EPS)</th>"
            "<th>상회</th><th>다음 발표</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")
    tail = ""
    if none:
        tail = render_notice("<b>실적 데이터 없음:</b> " + " · ".join(
            _esc(v.name) for v in none) + " — ETF 는 실적 발표가 없습니다.")
    return table + tail + render_footnote(
        "<b>서프라이즈 = (실제 − 추정) ÷ |추정|.</b> 추정치는 발표 직전 애널리스트 "
        "평균(야후)이고 EPS 는 대개 조정(non-GAAP) 기준이라 손익계산서 EPS 와 "
        "다를 수 있습니다. 추정을 넘었는지는 '시장이 무엇을 기대했나' 를 보여줄 "
        "뿐 주가 반응을 말해주지 않습니다 — 가이던스와 매출이 더 크게 움직이는 "
        "경우가 많습니다.")


def _eok_val(v: float | None) -> str:
    """억원 단위 값 → '1.23조' / '4,560억'."""
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v / 10000:,.2f}조"
    return f"{v:,.0f}억"


def render_kr_earnings(views) -> str:
    """한국 — 최근 분기 실적, 전년 동기·직전 분기 대비, 컨센서스."""
    ok = [v for v in views if v.latest is not None]
    none = [v for v in views if v.latest is None]
    rows = []
    any_surprise = False
    for v in sorted(ok, key=lambda x: (0 if x.held else 1, x.name)):
        cells = []
        for m in ("매출액", "영업이익", "순이익"):
            now = v.latest.values.get(m)
            turn = v.turns.get(m)
            tone = {"흑자 전환": "up", "적자 전환": "down"}.get(turn, "")
            yoy = (f"<span class='sub {tone}'>{_esc(turn)}</span>" if turn else
                   f"<span class='sub'>YoY {_pct_txt(v.yoy.get(m))}</span>"
                   f"<span class='sub'>QoQ {_pct_txt(v.qoq.get(m))}</span>")
            cells.append(f"<td>{_eok_val(now)}{yoy}</td>")
        sur = v.surprise.get("영업이익") if v.surprise else None
        if v.surprise:
            any_surprise = True
            sur_html = (f"영업이익 {_pct_txt(sur)}<span class='sub'>매출 "
                        f"{_pct_txt(v.surprise.get('매출액'))}</span>"
                        f"<span class='sub'>{_esc(v.surprise_seen[5:])} 기록 대비</span>")
        else:
            sur_html = "<span class='sub'>발표 전 기록 없음</span>"
        nxt = "—"
        if v.nxt is not None:
            nxt = (f"<b>{_esc(v.nxt.label)}</b><span class='sub'>매출 "
                   f"{_eok_val(v.nxt.values.get('매출액'))}</span><span class='sub'>"
                   f"영업이익 {_eok_val(v.nxt.values.get('영업이익'))}</span>")
        fil = ""
        if v.filing is not None and getattr(v.filing, "url", ""):
            fil = (f"<a class='dash-inline-link' href='{_esc(v.filing.url)}' "
                   f"target='_blank' rel='noopener noreferrer'>잠정실적 "
                   f"{_esc(v.filing.date[5:])}</a>")
        star = "<i class='ct-star' title='보유'>★</i>" if v.held else ""
        rows.append(
            f"<tr><td>{star}<b>{_esc(v.name)}</b><span class='sub'>{_esc(v.code)} · "
            f"{_esc(v.latest.label)}</span>{fil}</td>" + "".join(cells)
            + f"<td>{sur_html}</td><td>{nxt}</td></tr>")
    table = ""
    if rows:
        table = (
            '<div class="dash-table-wrap"><table class="dash-table dash-est">'
            "<thead><tr><th>종목 · 최근 분기</th><th>매출액</th><th>영업이익</th>"
            "<th>순이익</th><th>서프라이즈</th><th>다음 분기 컨센서스</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")
    tail = ""
    if none:
        tail = render_notice("<b>실적을 받지 못한 종목:</b> " + " · ".join(
            f"{_esc(v.name)}({_esc(v.error or '데이터 없음')})" for v in none))
    note = ("" if any_surprise else
            "<b>서프라이즈 칸이 비어 있는 게 지금은 정상입니다.</b> ")
    return table + tail + render_footnote(
        note + "네이버 실적표는 실적이 나오면 그 분기의 컨센서스(E) 를 실제값으로 "
        "<b>덮어씁니다</b>. 그래서 이 서버가 (E) 를 볼 때마다 기록해 두고, 같은 "
        "분기가 실제값으로 바뀌면 기록과 비교합니다. 서버가 재시작되면 기록이 "
        "지워져 다음 발표부터 다시 쌓입니다. 금액 단위 억원, 연결 기준이 기본 "
        "(네이버 표기). YoY 는 전년 같은 분기, QoQ 는 직전 분기 대비이며 부호가 "
        "바뀌면 %를 쓰지 않고 '흑자 전환' 처럼 적습니다.")



# ──────────────────────────────────────────────────────────────────────────────
# 좁은 화면 — 표를 줄 단위 카드로 (2026-11-11 "접으면 글자가 안 보인다")
# ──────────────────────────────────────────────────────────────────────────────
#
# 표는 가로로 넓습니다. 휴대폰(특히 접은 화면 344px)에서는 앞의 두세 칸만
# 보이고 나머지는 옆으로 밀어야 나옵니다 — 정작 숫자가 그쪽에 있습니다.
# 그래서 좁은 화면에서는 **한 줄을 카드 한 장**으로 세우고, 칸마다 머리글을
# 왼쪽에 붙입니다 ("외국인 5일   +418억").
#
# 머리글은 CSS 로 붙입니다: 칸에 data-l="머리글" 을 넣어 두면 좁은 화면에서
# td::before { content: attr(data-l) } 가 그걸 꺼냅니다. 넓은 화면에서는
# 속성만 있을 뿐 아무 일도 안 일어납니다. 표를 그리는 함수가 스물셋이라
# 하나씩 고치지 않고, 모든 render_* 의 결과를 여기로 한 번 통과시킵니다.

_STK_TABLE = re.compile(
    r'(?P<wrap><div class="dash-h?table-wrap)(?P<wrapc>[^"]*)">(?P<gap>\s*)'
    r'(?P<open><table\b[^>]*>)(?P<body>.*?)</table>', re.S)
_STK_THEAD = re.compile(r"<thead\b[^>]*>(.*?)</thead>", re.S)
_STK_TH = re.compile(r"<th\b([^>]*)>(.*?)</th>", re.S)
_STK_TR = re.compile(r"(<tr\b[^>]*>)(.*?)(</tr>)", re.S)
_STK_TD = re.compile(r"<td\b([^>]*)>")
_STK_TAG = re.compile(r"<[^>]+>")
_STK_SPAN = re.compile(r"colspan=[\"']?(\d+)")


#: 이 줄 수를 넘으면 좁은 화면에서 목록을 스크롤 칸에 넣습니다.
STACK_LONG = 6


def _stk_label(th_html: str) -> str:
    text = _STK_TAG.sub(" ", th_html.replace("<br>", " ").replace("<br/>", " "))
    return " ".join(text.split()).replace('"', "&quot;")


def stack_tables(markup: str) -> str:
    """표 칸에 머리글(data-l)을 붙이고 표·감싼 칸에 표식 클래스를 답니다.

    이미 처리한 표, 머리글 줄이 없는 표, 'dash-nostack' 표는 건드리지 않습니다.
    """
    if "<table" not in markup or "<thead" not in markup:
        return markup

    def one(m: re.Match) -> str:
        open_tag, body = m.group("open"), m.group("body")
        if "dash-stk" in open_tag or "dash-nostack" in open_tag:
            return m.group(0)
        head = _STK_THEAD.search(body)
        if head is None:
            return m.group(0)
        labels: list[str] = []
        for attrs, inner in _STK_TH.findall(head.group(1)):
            span = _STK_SPAN.search(attrs)
            labels += [_stk_label(inner)] * (int(span.group(1)) if span else 1)
        if len(labels) < 2:
            return m.group(0)

        def row(rm: re.Match) -> str:
            idx = 0

            def cell(cm: re.Match) -> str:
                nonlocal idx
                attrs = cm.group(1)
                label = labels[idx] if idx < len(labels) else ""
                span = _STK_SPAN.search(attrs)
                idx += int(span.group(1)) if span else 1
                return f'<td{attrs} data-l="{label}">'

            return rm.group(1) + _STK_TD.sub(cell, rm.group(2)) + rm.group(3)

        cut = head.end()
        n_rows = len(_STK_TR.findall(body[cut:]))
        body = body[:cut] + _STK_TR.sub(row, body[cut:])
        if 'class="' in open_tag:
            open_tag = open_tag.replace('class="', 'class="dash-stk ', 1)
        elif "class='" in open_tag:
            open_tag = open_tag.replace("class='", "class='dash-stk ", 1)
        else:
            open_tag = open_tag.replace("<table", '<table class="dash-stk"', 1)
        # 줄이 많으면 좁은 화면에서 '칸 안에서 밀어 보기' 로 높이를 묶습니다
        long = f' dash-stk-long" data-n="{n_rows}' if n_rows > STACK_LONG else ""
        return (f'{m.group("wrap")}{m.group("wrapc")} dash-stkw{long}">'
                f'{m.group("gap")}{open_tag}{body}</table>')

    return _STK_TABLE.sub(one, markup)


def _stacking(fn):
    import functools  # noqa: PLC0415

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        out = fn(*args, **kwargs)
        return stack_tables(out) if isinstance(out, str) else out
    return inner


for _name, _fn in list(globals().items()):
    if _name.startswith("render_") and callable(_fn):
        globals()[_name] = _stacking(_fn)
del _name, _fn


# ──────────────────────────────────────────────────────────────────────────────
# 차트 조건 — 오늘 볼 종목 (2026-11-13)
# ──────────────────────────────────────────────────────────────────────────────
#
# 사용자(폰): "첫 화면 표는 어떤 걸 의미하는지 모르겠네 · 표가 너무 길어".
# 지표 상태 칸이 든 넓은 표 대신 **종목당 두 줄**: 이름(+새로·반도체) /
# 왜 여기 있는지(과매도 진입한 지표 · 가격 판정 · 선행 EPS).

def render_pick_list(items: list[dict]) -> str:
    """items: [{name, ticker, tags[str], facts[str]}] → 두 줄짜리 목록."""
    out = []
    for i, it in enumerate(items, 1):
        tags = "".join(f'<span class="pk-tag">{_esc(t)}</span>' for t in it.get("tags") or [])
        facts = " · ".join(_esc(f) for f in it.get("facts") or [] if f)
        out.append(
            f'<li><div class="pk-top"><span class="pk-n">{i}</span>'
            f'<b>{_esc(it.get("name", ""))}</b><span class="pk-code">{_esc(it.get("ticker", ""))}'
            f'</span>{tags}</div><div class="pk-why">{facts}</div></li>')
    return f'<ol class="dash-picks">{"".join(out)}</ol>' if out else ""


# ──────────────────────────────────────────────────────────────────────────────
# 아침 브리핑 — 읽기 화면 (2026-11-13)
# ──────────────────────────────────────────────────────────────────────────────
#
# 사용자(폰): "가독성이 너무 떨어지고 그냥 맨바탕에 글씨만 있어서 이상하다 — 브라우저나
# 폰 둘 다에서 읽기 좋게". 고정폭 글 덩어리를 briefing_store.parse_block 이 구역 · 줄로
# 풀고, 여기서 카드로 그립니다: 맨 위 제목과 '한 줄', 숫자 구역은 이름-값 줄,
# 연결 · 일정 구역은 목록. 넓은 화면에서는 숫자 구역이 나란히 놓입니다.
# 글은 전부 이스케이프하고, 링크는 http(s) 만 만듭니다.

import re as _re_bf

_BF_MOVE = _re_bf.compile(r"([▲▼])\s?([0-9][0-9.,]*\s?(?:%p|%|bp|p)?)")
_BF_WHEN = _re_bf.compile(
    r"^(\d{1,2}/\d{1,2}(?:~\d{1,2})?(?:\s\d{1,2}:\d{2})?|\d{1,2}:\d{2})\s+(.*)$")
_BF_BOLD = _re_bf.compile(r"\*\*(.+?)\*\*")
_BF_LINK = _re_bf.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BF_OL = _re_bf.compile(r"^(\d+)[.)]\s+(.*)$")


def _bf_inline(text: str) -> str:
    """한 줄 글 → HTML. 이스케이프 → ▲▼ 등락색 → **굵게** → [글](http 주소)."""
    out = _esc(text)
    out = _BF_MOVE.sub(
        lambda m: f'<span class="bf-mv {"up" if m.group(1) == "▲" else "down"}">'
                  f"{m.group(1)}{m.group(2).strip()}</span>", out)
    out = _BF_BOLD.sub(r"<b>\1</b>", out)
    out = _BF_LINK.sub(
        r'<a class="dash-inline-link" href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        out)
    return out


def _bf_markdown(md: str) -> str:
    """브리핑 뒷부분(리스크 · 질문 등)의 간단한 마크다운 → HTML.

    제목(#), 목록(- · 1.), 문단, 굵게, 링크만 압니다. 나머지는 글자 그대로 보입니다.
    """
    parts: list[str] = []
    kind = ""               # "" | ul | ol | p
    buf: list[str] = []

    def flush() -> None:
        nonlocal kind, buf
        if kind in ("ul", "ol") and buf:
            parts.append(f"<{kind}>" + "".join(f"<li>{x}</li>" for x in buf) + f"</{kind}>")
        elif kind == "p" and buf:
            parts.append("<p>" + " ".join(buf) + "</p>")
        kind, buf = "", []

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("```"):
            flush()
            continue
        if s.startswith("#"):
            flush()
            parts.append(f'<h4>{_bf_inline(s.lstrip("#").strip())}</h4>')
            continue
        m_ol = _BF_OL.match(s)
        if s[:2] in ("- ", "* ") or m_ol:
            want = "ol" if m_ol else "ul"
            if kind != want:
                flush()
                kind = want
            buf.append(_bf_inline(m_ol.group(2) if m_ol else s[2:].strip()))
            continue
        if line[:1].isspace() and kind in ("ul", "ol") and buf:
            buf[-1] += " " + _bf_inline(s)          # 목록의 이어 쓰기
            continue
        if kind != "p":
            flush()
            kind = "p"
        buf.append(_bf_inline(s))
    flush()
    return "".join(parts)


def _bf_split_headings(md: str) -> list[tuple[str, str]]:
    """마크다운을 제목(#) 단위로 — [(제목, 본문)]. 첫 제목 앞 글은 ('참고', 글).

    ``` 블록 안의 # 는 제목으로 보지 않습니다.
    """
    out: list[tuple[str, list[str]]] = [("참고", [])]
    fence = False
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("```"):
            fence = not fence
        if not fence and s.startswith("#") and s.lstrip("#").strip():
            out.append((s.lstrip("#").strip(), []))
            continue
        out[-1][1].append(line)
    return [(t, "\n".join(b).strip()) for t, b in out if "\n".join(b).strip()]


def _bf_section(sec: dict) -> str:
    rows = sec.get("rows") or []
    n_kv = sum(1 for r in rows if r["kind"] == "kv")
    tabular = n_kv >= max(2, len(rows) // 2)
    body: list[str] = []
    listing: list[str] = []

    def close_list() -> None:
        if listing:
            body.append('<ul class="bf-list">' + "".join(listing) + "</ul>")
            listing.clear()

    for r in rows:
        if r["kind"] == "kv":
            close_list()
            cells = "".join(f"<span>{_bf_inline(c)}</span>" for c in r["cells"])
            note = (f'<div class="bf-note">{_bf_inline(r["note"])}</div>'
                    if r.get("note") else "")
            body.append(f'<div class="bf-kv"><b>{_esc(r["label"])}</b>'
                        f'<span class="bf-vals">{cells}</span>{note}</div>')
            continue
        text = r["text"]
        when = _BF_WHEN.match(text) if r["kind"] == "text" else None
        if when:
            listing.append(f'<li><span class="bf-when">{_esc(when.group(1))}</span>'
                           f"{_bf_inline(when.group(2))}</li>")
        elif tabular and r["kind"] == "text":
            close_list()
            body.append(f'<div class="bf-kv bf-kv-text">{_bf_inline(text)}</div>')
        else:
            listing.append(f"<li>{_bf_inline(text)}</li>")
    close_list()
    return (f'<section class="bf-sec {"bf-num" if tabular else "bf-wide"}">'
            f'<h3>{_esc(sec.get("title", ""))}</h3>{"".join(body)}</section>')


def render_briefing_view(bf, parsed: dict | None, rest_md: str = "") -> str:
    """아침 브리핑 한 편 — 제목 · 한 줄 · 구역 카드 · 덧붙인 글 · 출처."""
    stale = (f'<div class="bf-stale">{_esc(bf.age_label)} 글입니다 — 지금 시장을 설명하지 '
             "못할 수 있습니다</div>" if bf.is_stale else "")
    warn = (f'<div class="bf-stale">{_esc(" · ".join(bf.warnings))}</div>'
            if bf.warnings else "")
    lead, secs = "", []
    for sec in (parsed or {}).get("sections", []):
        if sec.get("lead") and not sec.get("rows"):
            lead += f'<p class="bf-lead">{_bf_inline(sec["lead"])}</p>'
        else:
            secs.append(_bf_section(sec))
    hero = ('<header class="bf-hero">'
            f'<div class="bf-meta">{_esc(bf.date)} · {_esc(bf.age_label)} · 아침 예약 작업이 쓴 글</div>'
            f'<h2>{_esc(bf.title or "제목 없음")}</h2>{lead}{stale}{warn}</header>')
    grid = f'<div class="bf-grid">{"".join(secs)}</div>' if secs else ""
    # 덧붙인 글 — 제목(#)마다 카드 한 장, 제목 앞 글은 '참고' 카드 (12:52 "문단마다 카드로")
    cards: list[str] = []
    for title, md in _bf_split_headings(rest_md):
        inner = _bf_markdown(md)
        if not inner:
            continue
        cards.append(f'<section class="bf-sec bf-wide bf-more"><h3>{_esc(title)}</h3>{inner}</section>')
    more = f'<div class="bf-grid bf-grid-more">{"".join(cards)}</div>' if cards else ""
    src = ""
    if bf.sources:
        items = "".join(
            f'<li><a class="dash-inline-link" href="{_esc(u)}" target="_blank" '
            f'rel="noopener noreferrer">{_esc(u.split("//", 1)[-1].split("/", 1)[0])}</a></li>'
            for u in bf.sources[:30])
        src = (f'<details class="bf-src"><summary>출처 {len(bf.sources)}곳</summary>'
               f"<ol>{items}</ol></details>")
    foot = ('<div class="bf-foot">웹에서 모은 자료를 AI 가 정리한 글입니다. 숫자는 출처에서 '
            "다시 확인하십시오. 매수 · 매도 의견이 아닙니다.</div>")
    return f'<article class="dash-brf">{hero}{grid}{more}{src}{foot}</article>'


# ── 차트 조건 — 오늘 볼 종목 카드 (2026-11-13 12:05 폰: "글자만 나오는데 개선") ──
#
# 종목당 카드 한 장: 이름 · 꼬리표 · 종가와 20일선 대비 / 펀더멘털 칩(가격 부담 · 선행 EPS)
# / CCI · 스토캐스틱 눈금(과매도 구역에 색, 지금 값에 점). 넓은 화면에서는 나란히.

_PK_PRICE_CLS = {"light": "good", "edge": "mid", "heavy": "warn", "na": "plain"}


def _pk_gauge(label: str, value, lo: float, hi: float, zone_hi: float,
              entered: bool, fmt: str = "{:+.0f}") -> str:
    if value is None:
        return ""
    span = (hi - lo) or 1.0
    pos = min(1.0, max(0.0, (value - lo) / span)) * 100
    zone = min(1.0, max(0.0, (zone_hi - lo) / span)) * 100
    badge = '<em>진입</em>' if entered else ""
    return (f'<div class="pk-g{" on" if entered else ""}"><span class="pk-gl">{_esc(label)}{badge}'
            f'</span><span class="pk-gt"><i class="zone" style="width:{zone:.1f}%"></i>'
            f'<i class="dot" style="left:{pos:.1f}%"></i></span>'
            f'<span class="pk-gv">{_esc(fmt.format(value))}</span></div>')


def _pk_spark(values, width: int = 300, height: int = 44) -> str:
    """3개월 종가 선 — 선 + 옅은 면 + 마지막 점. 칸 폭에 맞춰 늘어납니다 (12:08 '글자만')."""
    pts = [float(v) for v in (values or []) if isinstance(v, (int, float)) and v > 0]
    if len(pts) < 5:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts) - 1

    def xy(i, v):
        return (i / n * (width - 6) + 3, height - 4 - (v - lo) / span * (height - 10))

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(pts)))
    lx, ly = xy(n, pts[-1])
    tone = ("var(--dash-up)" if pts[-1] > pts[0] else
            "var(--dash-down)" if pts[-1] < pts[0] else "var(--dash-flat)")
    chg = pts[-1] / pts[0] - 1
    return (f'<div class="pk-chart"><svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
            f'aria-hidden="true"><polygon points="3,{height - 1} {line} {width - 3},{height - 1}" '
            f'fill="{tone}" opacity=".10"/><polyline points="{line}" fill="none" stroke="{tone}" '
            'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" '
            f'vector-effect="non-scaling-stroke"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" '
            f'fill="{tone}"/></svg><span>최근 {len(pts)}거래일 {direction_glyph(chg)}'
            f"{abs(chg) * 100:.1f}%</span></div>")


def render_pick_cards(items: list[dict]) -> str:
    """items: [{name, ticker, tags, price_txt, gap20, price_state, price_word, eps_c90,
    cci, stoch_k, entered(set), vol_ratio, cci_lo, stoch_lo, spark?}] → 카드 묶음."""
    cards = []
    for i, it in enumerate(items, 1):
        tags = "".join(f'<span class="pk-tag">{_esc(t)}</span>' for t in it.get("tags") or [])
        gap = it.get("gap20")
        gap_html = ""
        if gap is not None:
            cls = "up" if gap > 0 else ("down" if gap < 0 else "flat")
            gap_html = (f'<span class="pk-gap {cls}">20일선 대비 '
                        f"{direction_glyph(gap)}{abs(gap):.1f}%</span>")
        chips = []
        word = it.get("price_word") or ""
        if word:
            chips.append(f'<span class="pk-chip {_PK_PRICE_CLS.get(it.get("price_state"), "plain")}">'
                         f"{_esc(word)}</span>")
        c90 = it.get("eps_c90")
        if c90 is not None:
            cls = "up" if c90 > 0.005 else ("down" if c90 < -0.005 else "flat")
            arrow = "▲" if cls == "up" else ("▼" if cls == "down" else "→")
            warn = " warn" if it.get("eps_warn") else ""
            chips.append(f'<span class="pk-chip eps {cls}{warn}">선행 EPS {arrow} {c90 * 100:+.1f}%'
                         "<small> 90일</small></span>")
        else:
            chips.append('<span class="pk-chip plain">선행 EPS 추정 없음</span>')
        vr = it.get("vol_ratio")
        if vr is not None and vr >= 1.5:
            chips.append(f'<span class="pk-chip plain">거래량 {vr:.1f}배</span>')
        entered = it.get("entered") or set()
        gauges = (_pk_gauge("CCI", it.get("cci"), -300.0, 300.0, it.get("cci_lo", -100.0),
                            "cci" in entered)
                  + _pk_gauge("스토캐스틱", it.get("stoch_k"), 0.0, 100.0,
                              it.get("stoch_lo", 30.0), "stoch" in entered, "{:.0f}"))
        cards.append(
            f'<div class="pk-card"><div class="pk-top"><span class="pk-n">{i}</span>'
            f'<b>{_esc(it.get("name", ""))}</b><span class="pk-code">{_esc(it.get("ticker", ""))}'
            f"</span>{tags}</div>"
            f'<div class="pk-price"><span class="pk-px">{_esc(it.get("price_txt", ""))}</span>'
            f"{gap_html}</div>"
            + _pk_spark(it.get("spark"))
            + f'<div class="pk-chips">{"".join(chips)}</div>'
            f'<div class="pk-gs">{gauges}</div></div>')
    if not cards:
        return ""
    legend = ('<div class="pk-legend">눈금의 색칠한 구역 = 과매도 · 점 = 지금 값 · '
              "<em>진입</em> = 최근 3거래일 안에 그 구역으로 들어감</div>")
    return f'<div class="dash-picks">{"".join(cards)}</div>{legend}'


# ── 후보 (한국) — 등 세 개 (2026-11-13, 같은 날 네 개 → 세 개로 단순화) ──────────
#
# 종목당 카드 한 장: 순위 · 이름 · '근거 n/3' · 타이밍 꼬리표 / 등 세 개(품질 · 가격 ·
# 선행 EPS)와 근거 한 줄씩. 폰에서는 한 줄에 한 장.

_LAMP_ORDER = (("quality", "품질"), ("price", "가격"), ("eps", "선행 EPS"))
#: 성장형(11/13) — 성장 품질 7개 · PEG · 추정 흐름(30 · 90일 상향 지속)
_LAMP_ORDER_GROWTH = (("growth", "성장 품질"), ("price", "가격 PEG"), ("eps", "추정 흐름"))
_LAMP_WORD = {"g": "충족", "y": "보통", "r": "주의", "-": "없음"}


def render_candidate_cards(cands: list, limit: int = 10, *, compact: bool = False) -> str:
    """cands: integrate.Candidate 목록. compact=True 면 근거 줄 없이 등만 (요약 탭용)."""
    cards = []
    for i, c in enumerate(list(cands or [])[:limit], 1):
        tags = (('<span class="pk-tag ic-timing" title="차트가 최근 3거래일 안에 과매도로 들어감">타이밍</span>'
                 if getattr(c, "timing", False) else "")
                + ('<span class="pk-tag">반도체</span>' if getattr(c, "semi", False) else "")
                + (f'<span class="pk-tag">{"안정형" if getattr(c, "track", "") == "growth" else "성장형"}'
                   "에도</span>" if getattr(c, "also", False) else ""))
        order = _LAMP_ORDER_GROWTH if getattr(c, "track", "") == "growth" else _LAMP_ORDER
        lamps = []
        for key, label in order:
            col = (c.lamps or {}).get(key, "-")
            note = "" if compact else (
                f'<span class="ic-note">{_esc((c.notes or {}).get(key, ""))}</span>')
            lamps.append(f'<div class="ic-lamp {col}"><i aria-hidden="true"></i>'
                         f'<span class="ic-l">{label}</span>'
                         f'<span class="ic-w">{_LAMP_WORD.get(col, "")}</span>{note}</div>')
        n = len(order)
        cards.append(
            f'<div class="pk-card ic-card"><div class="pk-top"><span class="pk-n">{i}</span>'
            f'<b>{_esc(c.name)}</b><span class="pk-code">{_esc(c.ticker)}</span>{tags}'
            f'<span class="ic-score">근거 {c.greens}/{n}</span></div>'
            f'<div class="ic-lamps{" compact" if compact else ""}">{"".join(lamps)}</div></div>')
    if not cards:
        return ""
    return f'<div class="dash-picks ic-picks">{"".join(cards)}</div>'


def render_candidate_excluded(cands: list, limit: int = 30) -> str:
    """관문에 걸려 빠진 종목 — '이름 · 이유' 한 줄씩."""
    rows = [f"<li><b>{_esc(c.name)}</b> <span>{_esc(c.ticker)}</span> — {_esc(c.excluded)}</li>"
            for c in list(cands or [])[:limit]]
    return f'<ul class="ic-out">{"".join(rows)}</ul>' if rows else ""


_CHK = {"pass": ("✓", "g"), "fail": ("✗", "r"), "unknown": ("?", "u")}


def render_rule_box(title: str, lines: list) -> str:
    """규칙 설명 상자 (11/13) — 줄마다 구분선, 잘리지 않게(legend 는 두 줄에서 접힘)."""
    items = "".join(f'<li class="ck"><div class="ck-t rb">{_safe_inline(x)}</div></li>'
                    for x in lines if x)
    return (f'<div class="dash-cklist dash-rulebox"><div class="ck-h">{_esc(title)}</div>'
            f'<ul>{items}</ul></div>') if items else ""


def render_checklist(items: list, title: str = "추가 확인", sub: str = "") -> str:
    """근거 탭 확인 목록 (11/13) — [(상태, 항목, 근거 글)]. 줄마다 구분선 · 항목 아래 근거.

    11/13 폰 피드백 — 3칸 표(기호 · 항목 · 근거)는 좁은 폭에서 칸 경계가 안 보여 읽기 힘들었다.
    한 줄 = 기호 + 항목(굵게) / 그 아래 근거(작게) 두 줄로 세우고 줄 사이에 선을 둡니다.
    """
    rows = []
    for state, label, text in items or []:
        mark, cls = _CHK.get(state, ("?", "u"))
        word = {"g": "좋음", "r": "주의", "u": "자료 부족"}[cls]
        rows.append(f'<li class="ck {cls}"><div class="ck-top"><b class="ck-m" aria-label="{word}">'
                    f'{mark}</b><span class="ck-l">{_esc(label)}</span><span class="ck-w">{word}'
                    f'</span></div><div class="ck-t">{_esc(text)}</div></li>')
    if not rows:
        return ""
    sub_html = f'<div class="ck-s">{_esc(sub)}</div>' if sub else ""
    return (f'<div class="dash-cklist"><div class="ck-h">{_esc(title)}</div>{sub_html}'
            f'<ul>{"".join(rows)}</ul></div>')


def render_holding_checks(items: list) -> str:
    """내 종목 기준 점검 (11/13) — integrate.assess 결과 목록. 한 줄에 종목 · 등 3개 · 점검."""
    rows = []
    for c in items or []:
        dots = "".join(
            f'<span class="hc-d {(c.lamps or {}).get(k, "-")}" title="{_esc((c.notes or {}).get(k, ""))}">'
            f'<i aria-hidden="true"></i>{lab}<em>{_LAMP_WORD.get((c.lamps or {}).get(k, "-"), "")}</em></span>'
            for k, lab in _LAMP_ORDER)
        flag = (c.notes or {}).get("flags") or ""
        tags = ('<span class="pk-tag">성장형 통과</span>' if getattr(c, "also", False) else "") + (
            '<span class="pk-tag ic-timing">타이밍</span>' if getattr(c, "timing", False) else "")
        rows.append(
            f'<div class="hc-row{" warn" if flag else ""}"><div class="hc-n"><b>{_esc(c.name)}</b>'
            f'<span class="pk-code">{_esc(c.ticker)}</span>{tags}</div>'
            f'<div class="hc-dots">{dots}</div>'
            + (f'<div class="hc-f">점검 필요 — {_esc(flag)}</div>' if flag else "")
            + "</div>")
    return f'<div class="dash-hchecks">{"".join(rows)}</div>' if rows else ""


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:+.1f}%"


def render_paper(pf: dict, market: str) -> str:
    """모의 매수 실험 (11/13, paper.py) — 묶음(안정형 · 성장형)마다 요약 줄 + 종목 표 + 최근 변경점."""
    import paper  # noqa: PLC0415

    out = []
    cur = "원" if market == "kr" else "$"
    for track, label in (("stable", "안정형"), ("growth", "성장형")):
        allp = [p for p in pf.get("pos", []) if p["m"] == market and p["track"] == track]
        ps = [p for p in allp if p.get("state") != "void"]
        voided = len(allp) - len(ps)
        if not ps:
            continue
        sm = paper.summary(pf, market, track)
        exc = (sm["avg"] - sm["bench"]) if sm["avg"] is not None and sm["bench"] is not None else None
        head = (f'<div class="pp-h"><b>{label}</b> · {sm["n"]}종목 (보유 {sm["hold"]} · 매도 '
                f'{sm["sold"]}) · 평균 <b>{_pct(sm["avg"])}</b> · 같은 기간 시장 {_pct(sm["bench"])}'
                + (f' · 차이 <b>{_pct(exc)}</b>' if exc is not None else "") + "</div>")
        rows = []
        fmt = (lambda v: f"{v:,.0f}{cur}") if market == "kr" else (lambda v: f"{cur}{v:,.2f}")
        for p in ps:
            sold = p["state"] == "sold"
            end = p.get("p1") if sold else p.get("p")
            r = paper.ret(p)
            cls = "up" if r > 0.0005 else ("down" if r < -0.0005 else "flat")
            state = (f'매도 {_esc(str(p.get("d1", ""))[5:10])} — {_esc(p.get("why", ""))}' if sold
                     else ("보유 · 판정 불가" if p.get("na") else "보유"))
            rows.append(
                f'<div class="pp-row{" sold" if sold else ""}"><div class="pp-top"><b>{_esc(p["n"])}</b>'
                f'<span class="pk-code">{_esc(p["t"])}</span><span class="pp-r {cls}">{_pct(r)}</span></div>'
                f'<div class="pp-sub">{_esc(str(p["d0"])[5:10])} {fmt(p["p0"])} → '
                f'{fmt(end) if end else "—"} · 시장 {_pct(paper.bench_ret(p))}</div>'
                f'<div class="pp-st">{state}</div></div>')
        void_note = (f'<div class="pp-st">이전 규칙 묶음 {voided}종목은 규칙 변경으로 실험에서 뺌 — '
                     '아래 기록에 남김</div>' if voided else "")
        out.append(head + void_note + f'<div class="pp-list">{"".join(rows)}</div>')
    ev = [e for e in pf.get("events", []) if e[1] == market and e[4] != "buy"][-10:]
    if ev:
        names = {p["t"]: p["n"] for p in pf.get("pos", [])}
        kind = {"change": "변경", "sell": "매도", "na": "판정 불가", "reset": "규칙 변경"}
        items = "".join(
            f'<li><span>{_esc(str(e[0])[5:16])}</span> <b>{_esc(names.get(e[3], e[3]))}</b> '
            f'({"안정형" if e[2] == "stable" else "성장형"}) · {kind.get(e[4], e[4])} — {_esc(e[5])}</li>'
            for e in reversed(ev))
        out.append(f'<div class="pp-ev"><div class="pp-h"><b>논거 변경점 · 매도 기록</b> (최근 '
                   f'{len(ev)})</div><ul>{items}</ul></div>')
    return f'<div class="dash-paper">{"".join(out)}</div>' if out else ""


def render_backtest(res: dict, market: str, recent: str = "A") -> str:
    """차트 전략 백테스트 (11/13, techtest.py) — 변형마다 요약 카드 + 오늘 신호 + 최근 거래."""
    import techtest  # noqa: PLC0415

    var = res.get("variants") or {}
    if not var:
        return ""
    cur = "원" if market == "kr" else "$"
    fmt = (lambda v: f"{v:,.0f}{cur}") if market == "kr" else (lambda v: f"{cur}{v:,.2f}")
    out, rows = [], []
    for k in techtest.VARIANTS:
        v = var.get(k)
        if not v:
            continue
        if not v["trades"]:
            rows.append(f'<div class="pp-row"><div class="pp-top"><b>{_esc(techtest.LABELS[k])}</b>'
                        f'</div><div class="pp-sub">끝난 거래 없음 (보유 중 {v["open"]})</div></div>')
            continue
        r = v["avg"]
        cls = "up" if r > 0.0005 else ("down" if r < -0.0005 else "flat")
        why = " · ".join(f"{_esc(w)} {n}" for w, n in sorted(v["why"].items(), key=lambda x: -x[1]))
        rows.append(
            f'<div class="pp-row"><div class="pp-top"><b>{_esc(techtest.LABELS[k])}</b>'
            f'<span class="pp-r {cls}">평균 {_pct(r)}</span></div>'
            f'<div class="pp-sub">거래 {v["trades"]}번 (보유 중 {v["open"]}) · 이긴 비율 '
            f'{v["win"] * 100:.0f}% · 가운데 {_pct(v["med"])} · 최고 {_pct(v["best"])} · 최저 '
            f'{_pct(v["worst"])}</div>'
            f'<div class="pp-sub">같은 기간 후보 전체 대비 <b>{_pct(v["excess"])}</b> · 평균 보유 '
            f'{v["hold"]}일</div><div class="pp-st">끝난 이유 — {why}</div></div>')
    out.append(f'<div class="pp-list">{"".join(rows)}</div>')
    for k, label in (("A", "A 기본"), ("S", "S 스토캐스틱 확인"), ("C", "C 펀더멘털 통과만")):
        sig = (res.get("signals") or {}).get(k)
        if sig is None:
            continue
        body = (" · ".join(f'<b>{_esc(s["n"])}</b> <span class="pk-code">{_esc(s["s"])}</span>'
                           for s in sig[:12]) if sig else "없음")
        out.append(f'<div class="pp-h">오늘 매수 신호 · {label} ({len(sig)}) — {body}</div>')
    rec = list(reversed((var.get(recent) or {}).get("recent") or []))
    if rec:
        items = "".join(
            f'<li><span>{_esc(str(x["d0"])[5:10])}→{_esc(str(x["d1"])[5:10])}</span> '
            f'<b>{_esc(x["n"])}</b> {fmt(x["p0"])}→{fmt(x["p1"])} <b>{_pct(x["r"])}</b>'
            f' · {_esc(x["why"])}</li>' for x in rec)
        out.append(f'<div class="pp-ev"><div class="pp-h"><b>최근 거래 · '
                   f'{_esc(techtest.LABELS[recent])}</b> ({len(rec)})</div><ul>{items}</ul></div>')
    return f'<div class="dash-paper">{"".join(out)}</div>'
