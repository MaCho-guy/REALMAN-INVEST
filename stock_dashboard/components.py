"""
카드 / 테이블 HTML 렌더링.

Streamlit 기본 위젯으로는 jusikbot 같은 밀도 높은 카드 그리드를 만들기
어려우므로, 카드는 HTML 문자열로 직접 조립해서 st.markdown 으로 넣습니다.
사용자 입력이 섞이지 않는 경로지만, 외부 API 가 돌려준 문자열(종목명 등)이
들어오므로 모든 텍스트는 html.escape 로 이스케이프합니다.
"""

from __future__ import annotations

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


def render_section_head(title: str, subtitle: str, count: int) -> str:
    sub = f'<span class="dash-section-sub">{_esc(subtitle)}</span>' if subtitle else ""
    return (
        '<div class="dash-section-head">'
        f'<span class="dash-section-title">{_esc(title)}</span>'
        f"{sub}"
        f'<span class="dash-section-count">{count}개 항목</span>'
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
    return _SAFE_RE.sub(lambda m: f"<{m.group(1)}{m.group(2).lower()}>", out)


def render_footnote(text: str) -> str:
    return (f'<div class="dash-footnote">{_safe_inline(text)}</div>'
            if text else "")


def render_topbar(title: str, subtitle: str, clock: str) -> str:
    return (
        '<div class="dash-topbar">'
        f'<span class="dash-logo">{_esc(title)}</span>'
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

    meta = [f"관측 {_esc(reading.observed_label)}"]
    if reading.lag_days is not None:
        late = ' class="late"' if reading.stale else ""
        meta.append(f"<span{late}>{reading.lag_days}일 전</span>")
    if not spec.verified:
        meta.append("계열 미검증")

    why = ""
    if show_why and spec.why:
        why = f'<div class="dash-macro-why">{spec.why}</div>'

    warn = ""
    if reading.warning:
        warn = f'<div class="dash-macro-why">{_esc(reading.warning)}</div>'

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


def render_macro_trigger(trigger, prompt: str = "") -> str:
    """임계값을 건드린 지표 한 건 — 변화 감지 탭의 신호 카드와 같은 모양."""
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

    detail = f'<div class="dash-check-detail">{_esc(check.detail)}</div>'
    warn = (f'<div class="dash-check-warn">⚠ {_esc(check.warning)}</div>'
            if check.warning else "")
    source = ""
    if show_source:
        source = (
            f'<div class="dash-check-detail"><b>출처</b> — {_esc(crit.source)}'
            + (f'<br><b>한계</b> — {_esc(crit.caveat)}' if crit.caveat else "")
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
            f'<div class="dash-screen-err">{_esc(screen.error)}</div></div>'
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
            + _esc(", ".join(screen.missing_tags))
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


def render_screen_table(screens, criteria) -> str:
    """전체 요약 표 — 어느 기업이 어느 기준에서 걸렸나 한눈에."""
    if not screens:
        return ""
    header = "".join(f"<th>{_esc(c.name.replace(' 꾸준히', '').replace('가', ''))}</th>"
                     for c in criteria)
    rows = []
    for s in screens:
        if not s.ok:
            continue
        cells = []
        for check in s.checks:
            cls = {"pass": "", "fail": "na", "unknown": "na"}[check.verdict]
            cells.append(f'<td class="{cls}">{_MARK[check.verdict]}</td>')
        rows.append(
            f"<tr><td>{_esc(s.ticker)}</td>"
            f'<td class="">{_esc(s.score_label)}</td>'
            + "".join(cells) + "</tr>"
        )
    if not rows:
        return ""
    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        f"<thead><tr><th>티커</th><th>통과</th>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 가격 판독 + 판단 재료
# ──────────────────────────────────────────────────────────────────────────────

def render_dcf_cells(result) -> str:
    """역DCF 숫자 칸들."""
    if not result.ok:
        return (f'<div class="dash-screen-err">{_esc(result.error)}</div>'
                if result.error else "")

    cells = [
        ("요구 성장률 (할인율 10%)", result.growth_label),
        ("할인율 8~12% 구간", result.band_label),
    ]
    span = result.gap_span
    if span is not None:
        hist = result.historical_cagr[span]
        cells.append((f"과거 {span}년 실제", f"연 {hist * 100:,.1f}%"))
    gap = result.gap
    if gap is not None:
        cells.append(("격차", f"{gap * 100:+,.1f}%p"))
    if result.fcf_base is not None:
        label = "기준 FCF" + (" (3년 평균)" if result.normalized else "")
        cells.append((label, f"{result.fcf_base / 1e9:,.1f}B"))

    inner = "".join(
        f'<div class="dash-dcf-cell"><span class="lb">{_esc(lb)}</span>'
        f'<span class="vl">{_esc(vl)}</span></div>'
        for lb, vl in cells
    )
    return f'<div class="dash-dcf-grid">{inner}</div>'


def render_verdict(v, *, prompt: str = "", show_next: bool = True) -> str:
    """판단 재료 — 사분면 위치와 다음에 확인할 것. 결론은 쓰지 않습니다."""
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

    return (
        f'<div class="dash-verdict {cls}">'
        f'<div class="dash-verdict-pos">{_esc(QUADRANT_TITLE[v.quadrant])}</div>'
        f'<div class="dash-verdict-line">{_md_bold(QUADRANT_MEANING[v.quadrant])}</div>'
        f"{body_html}{cav}{nxt}{prompt_block}</div>"
    )


def _md_bold(text: str) -> str:
    """**굵게** 만 허용하는 최소 마크다운. 나머지는 전부 이스케이프합니다."""
    parts = _esc(text).split("**")
    out = []
    for i, part in enumerate(parts):
        out.append(f"<b>{part}</b>" if i % 2 == 1 else part)
    return "".join(out)


def render_quadrant_map(verdicts) -> str:
    """사분면 지도 — 어느 종목이 어디 있나."""
    if not verdicts:
        return ""
    buckets: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: [], 0: []}
    for v in verdicts:
        buckets[v.quadrant].append(v.ticker)

    def cell(q: int) -> str:
        names = buckets.get(q) or []
        body = ", ".join(_esc(n) for n in names) if names else "—"
        return f'<td>{body}</td>'

    return (
        '<div class="dash-table-wrap"><table class="dash-table">'
        "<thead><tr><th></th>"
        "<th>요구 ≤ 과거 실제</th><th>요구 &gt; 과거 실제</th></tr></thead>"
        "<tbody>"
        f"<tr><td>기준 많이 통과</td>{cell(1)}{cell(2)}</tr>"
        f"<tr><td>기준 적게 통과</td>{cell(3)}{cell(4)}</tr>"
        f'<tr><td>역DCF 불가</td><td colspan="2">'
        f'{", ".join(_esc(n) for n in buckets[0]) or "—"}</td></tr>'
        "</tbody></table></div>"
    )


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
    detail = (f'<div class="dash-srow-detail">{_esc(row.detail)}</div>'
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
    return (
        render_summary_band(summary)
        + "".join(render_summary_row(r) for r in summary.rows)
    )


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
        "를 실행한 뒤 사이드바에서 데모 모드를 끄십시오."
        if preview else
        "사이드바에서 데모 모드를 끄면 실제 데이터를 받아옵니다."
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
        '<span class="dash-bf-line-tag">증시 브리핑</span>'
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
        return f'<div class="dash-screen-err">{_esc(msg)}</div>'

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
        tip = (f'<div class="dash-check-detail">{_esc(note)}</div>'
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

    return (f'<div class="dash-price">{head}'
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


def render_external_dashboard(links) -> str:
    """다른 곳에서 이미 잘 돌고 있는 대시보드로 보냅니다.

    뉴스·일정·섹터 온도·수출 레이더를 여기서 다시 만들면 중복입니다.
    links: ((라벨, URL, 설명), ...)
    """
    items = ""
    for label, url, note in links:
        if not str(url).startswith(("http://", "https://")):
            continue
        items += (
            '<div class="dash-ext-row">'
            f'<a class="dash-inline-link dash-ext-link" href="{_esc(url)}" '
            f'target="_blank" rel="noopener noreferrer">{_esc(label)}</a>'
            f'<span class="dash-ext-note">{_esc(note)}</span>'
            "</div>"
        )
    if not items:
        return ""
    return f'<div class="dash-ext">{items}</div>'


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
            '<span class="dash-exp-why">사이드바 진단의 '
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
