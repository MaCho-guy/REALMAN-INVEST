"""
색상 토큰과 CSS. **데이 모드 한 가지입니다.**

2026-11-11 에 나이트 모드를 없앴습니다. 두 벌을 유지하면 한쪽에서만
깨지는 버그가 계속 생기고(실제로 각주 태그·링크 색·차트 대비가 전부
한쪽에서만 틀렸습니다), 둘 다 어중간해집니다. 하나를 제대로 만드는 게
낫습니다.

**디자인 방향 — '리서치 노트'**

이 화면은 종이 위의 리서치 노트처럼 읽혀야 합니다. 숫자가 주인공이고
나머지는 구조입니다. 그래서:

  바탕은 차가운 회색(#eceef1), 카드는 **진짜 흰색**.
    크림색(#f4f1ea 계열)을 피했습니다. 따뜻한 종이색은 숫자를 읽는
    화면에 어울리지 않고, 카드와 바탕이 둘 다 크림이면 경계가 안
    보입니다. 흰 카드가 회색 바탕에서 뜨면 그림자 없이도 구분됩니다.

  **색은 등락에만 씁니다.** 구조(선·제목·링크)는 전부 무채색이나
    남색 하나입니다. 색이 두 가지 뜻을 가지면 숫자를 잘못 읽습니다 —
    돈이 걸린 화면에서 제일 비싼 실수입니다.

  숫자는 **tabular-nums** 로 자릿수를 맞춥니다. 표에서 자리가 흔들리면
    위아래 비교가 안 됩니다.

모든 글자색은 가장 밝은 배경(#eceef1) 기준 **명암비 5.0 이상**입니다
(WCAG AA 는 4.5). 색각이상 대비: 상승 적색 #c02a29 / 하락 청색 #1d63b8.
색만으로 뜻을 전하지 않도록 ▲ / ▼ 와 부호를 항상 같이 적습니다.
"""

from __future__ import annotations

from typing import Literal

#: 남아 있는 호출부 호환용. 값은 "light" 하나뿐입니다.
Mode = Literal["light"]

PALETTE: dict[Mode, dict[str, str]] = {
    "light": {
        # 바탕과 면
        "page": "#eceef1",            # 차가운 회색 — 카드가 뜨는 바탕
        "surface": "#ffffff",         # 카드
        "surface_raised": "#f1f3f6",  # 카드 **안쪽** 블록 (흰색보다 어둡게)
        # 글자
        "ink": "#15181c",
        "ink_secondary": "#4a5158",
        "ink_muted": "#5f666e",
        # 구조
        "border": "rgba(21,24,28,0.16)",
        "divider": "#dce0e6",
        "accent": "#1f3a5f",          # 깊은 남색 — 구조 전용, 등락 아님
        # 등락 (한국 관행: 상승 적색 / 미국 관행: 상승 녹색)
        "up_kr": "#c02a29",
        "down_kr": "#1d63b8",
        "up_us": "#13693a",
        "down_us": "#c02a29",
        "flat": "#5f666e",
        # 상태 배지
        "badge_live": "#13693a",
        "badge_pre": "#835f00",
        "badge_post": "#5b4bc4",
        "badge_closed": "#5f666e",
        "badge_error": "#bf2b2b",
    },
}

#: 섹션 묶음(내비의 '오늘 · 찾기 · 한국/미국 시장 · 공통')마다의 옅은 색 (2026-11-13
#: 사용자: "섹션 별로 구분 잘 가게 · 옅은 파스텔 · 섹션 별로 다른 색깔").
#: 묶음 순서대로 씁니다. (키, 옅은 바탕, 고른 항목 바탕, 선). 글자는 늘 --dash-ink
#: (세 바탕 모두 명암비 9 이상). 등락색(적 · 청 · 녹)과 헷갈리지 않게 채도를 낮춘
#: 채도를 낮춘 하늘 · 세이지 · 샌드 · 웜 그레이입니다 — 색은 '어느 묶음인가' 만 뜻합니다.
GROUP_TONES: tuple[tuple[str, str, str, str], ...] = (
    ("today", "#e9f1f7", "#d3e3ef", "#6f9dbd"),     # 흐린 하늘
    ("find", "#eaf2ec", "#d5e5d9", "#78a587"),      # 세이지
    ("market", "#f7eee3", "#eedcc6", "#c49a6c"),    # 샌드
    ("common", "#efefec", "#e0dfda", "#96948d"),    # 웜 그레이
)
# 09:40 "보라색은 맘에 안 듦" · 09:46 "파스텔톤은 좋은데 색조합이 이상함" —
# 하늘 · 민트 · 복숭아 · 버터는 채도가 제각각이라 따로 놀았습니다. 채도를 한 단계
# 낮추고 밝기를 맞춘 한 벌(흐린 하늘 · 세이지 · 샌드 · 웜 그레이)로 바꿨습니다.
# '공통' 은 일부러 무채색입니다 — 어느 시장에도 속하지 않는 묶음.


def group_tone(index: int) -> tuple[str, str, str, str]:
    return GROUP_TONES[index % len(GROUP_TONES)]


def nav_group_css(market: str, groups) -> str:
    """내비 버튼에 묶음 색을 입히는 규칙. groups = config.tab_groups(market).

    스트림릿은 key 가 있는 위젯에 `st-key-<key>` 클래스를 붙입니다 (1.39+). 그
    클래스가 없는 버전이면 이 규칙만 안 먹고 내비는 예전 모양으로 돕니다.
    """
    col = 'div[data-testid="stColumn"]:has(.dash-navmark)'
    out = []
    for gi, (_name, items) in enumerate(groups):
        _k, tint, mid, line = group_tone(gi)
        for key, _label in items:
            b = f"{col} .st-key-navbtn_{market}_{key} button"
            out.append(
                f'{b}[kind="secondary"]{{background:{tint} !important;'
                f"border:1px solid transparent !important;}}"
                f'{b}[kind="secondary"]:hover{{background:{mid} !important;'
                f"border-color:{line} !important;}}"
                f'{b}[kind="primary"]{{background:{mid} !important;'
                f"border:1.5px solid {line} !important;color:var(--dash-ink) !important;}}"
                f'{b}[kind="primary"] p{{color:var(--dash-ink) !important;}}')
    return "".join(out)


def group_vars_css(index: int) -> str:
    """지금 보는 묶음의 색을 본문에 넘기는 변수 (구역 제목 띠가 씁니다)."""
    _k, tint, mid, line = group_tone(index)
    return f":root{{--grp-tint:{tint};--grp-mid:{mid};--grp-line:{line};}}"


FONT_STACK = 'system-ui, -apple-system, "Segoe UI", "Apple SD Gothic Neo", sans-serif'


def delta_colors(convention: str, mode: Mode = "light") -> tuple[str, str, str]:
    """(상승색, 하락색, 보합색) 을 반환합니다."""
    p = PALETTE[mode]
    if convention == "us":
        return p["up_us"], p["down_us"], p["flat"]
    return p["up_kr"], p["down_kr"], p["flat"]


def build_vars(convention: str, scope: str = ":root") -> str:
    """색상 변수만 담은 CSS 블록."""
    p = PALETTE["light"]
    up, down, flat = delta_colors(convention)

    return f"""
  {scope} {{
    --dash-page: {p["page"]};
    --dash-surface: {p["surface"]};
    --dash-raised: {p["surface_raised"]};
    --dash-ink: {p["ink"]};
    --dash-ink-2: {p["ink_secondary"]};
    --dash-ink-muted: {p["ink_muted"]};
    --dash-border: {p["border"]};
    --dash-accent: {p["accent"]};
    --dash-divider: {p["divider"]};
    --dash-up: {up};
    --dash-down: {down};
    --dash-flat: {flat};
    --dash-badge-live: {p["badge_live"]};
    --dash-badge-pre: {p["badge_pre"]};
    --dash-badge-post: {p["badge_post"]};
    --dash-badge-closed: {p["badge_closed"]};
    --dash-badge-error: {p["badge_error"]};

    /* 타입 스케일 — 9단. 고치기 전에는 38종이 쓰였고 0.58·0.60·0.61·0.62·
       0.63·0.64rem 이 전부 1px 안에 몰려 있었습니다. 눈에는 안 보이면서
       정렬만 미묘하게 어긋나고, 고칠 때마다 어느 값을 쓸지 헷갈립니다.
       아래 칸 사이는 좁고(UI 글자) 위로 갈수록 넓습니다(수치 강조).
       2026-11-11: 아래 여섯 칸을 한 단계씩 올렸습니다. 10·11px 짜리 보조
       글자가 대비까지 낮아 야간 모드에서 읽히지 않는다는 지적을 받았습니다.
       큰 수치 쪽(7~9)은 이미 충분해서 건드리지 않았습니다. */
    --fs-1: 0.72rem;   /* 11.5px — 출처 태그, 작은 칩 */
    --fs-2: 0.78rem;   /* 12.5px — 캡션, 세부 설명 */
    --fs-3: 0.84rem;   /* 13.5px — 표 본문, 판정 줄 */
    --fs-4: 0.90rem;   /* 14.5px — 본문, 카드 라벨 */
    --fs-5: 0.98rem;   /* 16px — 카드 제목 */
    --fs-6: 1.10rem;   /* 18px — 섹션 제목 */
    --fs-7: 1.30rem;   /* 21px — 중간 수치 */
    --fs-8: 1.60rem;   /* 26px — 큰 수치 */
    --fs-9: 2.00rem;   /* 32px — 최대 수치 */

    /* 모서리 — 4단. 전에는 8종(3·4·6·7·8·9·10·999px)이 섞여 있었는데
       위계가 아니라 잡음이었습니다. 이제 칩 < 내부 요소 < 카드 < 알약
       순서로 의미가 있습니다. */
    --r-chip: 3px;
    --r-inner: 6px;
    --r-card: 10px;
    --r-pill: 999px;

    /* 세로 리듬 — 섹션 사이 간격이 8·10·14·20px 로 제각각이면 어디서
       끊기는지 눈이 못 잡습니다. 4의 배수 한 줄로 둡니다. */
    --sp-1: 4px;
    --sp-2: 8px;
    --sp-3: 12px;
    --sp-4: 20px;
    --sp-5: 32px;
  }}
  /* 휴대폰 — 글자를 한 단계씩 키웁니다 (2026-11-11 "접으면 글자가 안 보인다").
     화면이 좁다고 글자를 줄이면 안 됩니다. 눈과의 거리는 같고 화면만
     작으니, 한 줄에 덜 담고 글자는 오히려 키워야 읽힙니다. 줄어든 폭은
     표를 카드로 세워서 감당합니다 (아래 .dash-stk). */
  @media (max-width: 640px) {{
    {scope} {{
      --fs-1: 0.82rem;   /* 13px */
      --fs-2: 0.88rem;   /* 14px */
      --fs-3: 0.95rem;   /* 15px */
      --fs-4: 1.00rem;   /* 16px */
      --fs-5: 1.07rem;   /* 17px */
      --fs-6: 1.16rem;   /* 18.5px */
    }}
  }}
"""


def build_css(convention: str, stack: bool = True) -> str:
    """앱 전체에 주입할 CSS (변수 + 규칙).

    stack=True 면 좁은 화면에서 표를 카드로 세웁니다 (기본). False 면 표를
    그대로 두고 옆으로 밀어 봅니다.
    """
    import config  # noqa: PLC0415

    compact = getattr(config, "DENSITY", "compact") == "compact"
    return ("<style>" + build_vars(convention) + build_rules()
            + build_native_rules()
            + (build_density_rules() if compact else "")
            # 표 → 카드 규칙은 맨 뒤여야 합니다 (표마다 준 폭·여백을 덮습니다)
            + (build_stack_rules() if stack else "") + "</style>")


def build_density_rules() -> str:
    """촘촘한 배치 — 글자 크기는 그대로 두고 **사이 간격만** 줄입니다.

    2026-11-12 "여백을 크게 써서 내용이 덜 들어간 느낌". 실제 화면을 재 보니
    빈 곳의 대부분은 부품 안쪽이 아니라 **부품 사이**였습니다:
      · 스트림릿이 블록마다 넣는 세로 간격 1rem (한 화면에 블록이 20개면 320px)
      · 섹션 제목 위 32px, 설명 글 아래 20px
      · 넓은 화면의 좌우 여백 5rem
    글자를 줄이면 휴대폰에서 읽기 어려워지므로(2026-11-11 에 키운 값) 건드리지
    않습니다. config.DENSITY = "roomy" 로 두면 이 묶음 전체가 빠집니다.
    공통 규칙 뒤 · 표→카드 규칙 앞에 붙어서 앞의 규칙을 덮습니다.
    """
    return f"""
  :root {{ --sp-4: 13px; --sp-5: 20px; }}

  /* 스트림릿 블록 사이 */
  [data-testid="stMain"] div[data-testid="stVerticalBlock"] {{ gap: 0.5rem; }}
  [data-testid="stMain"] div[data-testid="stHorizontalBlock"] {{ gap: 0.6rem; }}
  /* 2026-11-12 실제 앱에서 잰 값: 위 여백이 96px(6rem)였습니다. 스트림릿
     머리띠(60px, 오른쪽에 Fork·메뉴)만 피하면 됩니다. 이 스트림릿에서
     stMain 은 <section> 이 아니라 <main> 이라 꼬리표 이름 없이 집습니다. */
  [data-testid="stMain"] .block-container,
  div[data-testid="stMainBlockContainer"] {{
    padding-top: 3.9rem !important;
    padding-bottom: 2.5rem !important; max-width: 1560px;
  }}
  /* <style> 만 든 칸은 높이가 0 이어도 블록 간격을 한 번씩 먹습니다 (2칸) */
  div[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {{
    display: none !important;
  }}
  @media (min-width: 900px) {{
    [data-testid="stMain"] .block-container,
    div[data-testid="stMainBlockContainer"] {{
      padding-left: 1.6rem !important; padding-right: 1.6rem !important;
    }}
  }}

  /* 접는 카드 — 제목 줄을 낮추고 안쪽 여백을 줄입니다 */
  [data-testid="stExpander"] summary {{
    padding-top: 5px !important; padding-bottom: 5px !important; min-height: 0 !important;
  }}
  [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    padding: 6px 12px 10px !important;
  }}
  /* 위젯 이름과 위젯 사이 */
  [data-testid="stWidgetLabel"] {{ margin-bottom: 0 !important; min-height: 0 !important; }}
  [data-testid="stSlider"] {{ padding-bottom: 0 !important; }}
  [data-testid="stCaptionContainer"] {{ margin-bottom: -4px; }}
  hr {{ margin: 0.6rem 0 !important; }}

  /* 우리 부품 — 사이 간격 */
  .dash-section-head {{ margin: var(--sp-4) 0 var(--sp-2); padding-bottom: 5px; }}
  .dash-footnote {{ line-height: 1.5; margin: 2px 0 var(--sp-2); }}
  .dash-scr-head {{ margin: var(--sp-4) 0 6px; padding-bottom: 5px; }}
  .dash-grid {{ gap: 8px; margin: 4px 0 10px; }}
  .dash-card {{ padding: 10px 12px 10px 12px; }}
  .dash-screen {{ padding: 10px 12px 8px; margin-bottom: 6px; }}
  .dash-signal {{ padding: 10px 13px; margin-bottom: 7px; }}
  .dash-exp {{ padding: 9px 12px; margin: 3px 0 7px; }}
  .dash-cycle {{ padding: 12px 14px 10px; margin-bottom: 10px; }}
  .dash-macro-group {{ margin-top: 14px; }}
  .dash-rp {{ gap: 6px; }}
  .dash-rp .rp-card {{ padding: 8px 11px; }}
  .dash-times {{ margin-bottom: 6px; }}
  table.dash-table th, table.dash-table td {{ padding: 5px 9px; }}
  .dash-kv th, .dash-kv td {{ padding-top: 4px; padding-bottom: 4px; }}

  /* 시장 전환 버튼 — 다른 위젯보다 크되, 줄 하나를 다 먹지는 않게 */
  div[data-testid="stElementContainer"]:has(.dash-marketmark)
    + div[data-testid="stElementContainer"] button {{
    padding: 4px 18px !important; min-height: 34px;
  }}
  div[data-testid="stElementContainer"]:has(.dash-marketmark)
    + div[data-testid="stElementContainer"] {{ margin-bottom: 0; }}
  /* 표식만 든 빈 칸은 자리를 차지하지 않게 */
  div[data-testid="stElementContainer"]:has(.dash-marketmark):not(:has(button)) {{
    display: none !important;
  }}

  @media (max-width: 640px) {{
    [data-testid="stMain"] div[data-testid="stVerticalBlock"] {{ gap: 0.45rem; }}
    .dash-section-head {{ margin-top: 14px; }}
    .dash-footnote {{ line-height: 1.45; }}
    .dash-card {{ padding: 9px 11px; }}
  }}
"""


def build_rules() -> str:
    """테마와 무관한 CSS 규칙. 색은 전부 변수로 참조합니다."""
    return f"""
  .stApp {{ background: var(--dash-page); }}

  /* 숫자는 어디에 있든 자릿수를 맞춥니다. 표에서 자리가 흔들리면 위아래
     비교가 안 됩니다 — 이 화면에서 제일 많이 하는 동작입니다. */
  .dash-card, .dash-signal, .dash-exp, .dash-skills, .dash-sector,
  table.dash-table, .dash-kv, .dash-hit-row, .dash-macro-card {{
    font-variant-numeric: tabular-nums;
  }}

  /* 섹션 헤더 */
  /* 섹션 제목 — 아래 실선 하나로만 구분했더니 어디서 끊기는지 눈이 못
     잡았습니다. 제목 왼쪽에 남색 굵은 선을 세워 **구역의 시작**을
     표시합니다. 색은 여기서만 쓰고 숫자에는 쓰지 않습니다. */
  /* 2026-11-13: 실선 + 남색 막대 → 묶음 색의 옅은 띠. 구역이 어디서 시작하는지가
     띠로 보이고, 띠 색으로 지금 어느 묶음(오늘 · 찾기 · 시장 · 공통)인지 압니다.
     변수가 없으면(미리보기 등) 예전 남색 막대로 돌아갑니다. */
  .dash-section-head {{
    display: flex; align-items: baseline; gap: var(--sp-3);
    margin: var(--sp-5) 0 var(--sp-3);
    padding: 9px 12px 9px 12px;
    background: var(--grp-tint, transparent);
    border-left: 4px solid var(--grp-line, var(--dash-accent));
    border-radius: var(--r-inner);
    font-family: {FONT_STACK};
  }}
  /* 첫 섹션은 위 여백을 줄입니다 — 탭 바로 아래가 비어 보입니다 */
  .dash-section-head:first-child {{ margin-top: var(--sp-2); }}
  .dash-section-title {{
    font-size: var(--fs-6); font-weight: 750; color: var(--dash-ink);
    letter-spacing: -0.015em;
    /* 좁은 폭에서 flex 가 제목을 압축해 '요/약' 처럼 글자 단위로
       쪼갰습니다. 제목은 줄이지 않습니다. */
    flex: 0 0 auto; white-space: nowrap;
  }}
  .dash-section-sub {{
    font-size: var(--fs-4); color: var(--dash-ink-muted);
    flex: 1 1 auto; min-width: 0;
  }}
  .dash-section-count {{
    margin-left: auto; font-size: var(--fs-3); color: var(--dash-ink-muted);
    border: 1px solid var(--dash-border); border-radius: var(--r-pill);
    padding: 2px 9px; white-space: nowrap;
  }}
  /* 설명 문구. 글자만 작게 하면 '작은 본문' 으로 읽혀 데이터와 섞입니다.
     왼쪽에 세로선을 둬서 **주석**임을 구조로 표시합니다 — 그러면 눈이
     숫자를 찾을 때 이 블록을 건너뜁니다. */
  .dash-footnote {{
    font-size: var(--fs-2); color: var(--dash-ink-muted);
    line-height: 1.65; margin: var(--sp-1) 0 var(--sp-4);
    padding: 1px 0 1px var(--sp-3);
    border-left: 2px solid var(--dash-divider);
    font-family: {FONT_STACK};
    max-width: 78ch;              /* 긴 줄은 눈이 되돌아올 곳을 잃습니다 */
  }}
  /* 표시 패널에서 설명을 끄면 데이터만 남습니다 */
  .dash-nonotes .dash-footnote,
  .dash-nonotes .dash-check-detail {{ display: none; }}

  /* 종목 카드 */
  /* 카드 — 흰 면이 회색 바탕 위에 놓입니다. 그림자를 깔지 않습니다:
     카드가 20개 넘는 화면에서 그림자는 전부 같은 회색 번짐이 되어
     오히려 구분을 지웁니다. 테두리 한 줄이면 충분합니다. */
  .dash-card {{
    background: var(--dash-surface);
    border: 1px solid var(--dash-border);
    border-radius: var(--r-card);
    padding: 13px 15px 14px 15px;
    font-family: {FONT_STACK};
    height: 100%;
    display: flex; flex-direction: column; gap: 2px;
  }}
  .dash-card-name {{
    font-size: var(--fs-5); font-weight: 600; color: var(--dash-ink);
    line-height: 1.3; letter-spacing: -0.01em;
  }}
  .dash-card-meta {{
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    font-size: var(--fs-2); color: var(--dash-ink-muted);
    margin-bottom: 9px;
  }}
  .dash-badge {{
    font-size: var(--fs-1); font-weight: 600; letter-spacing: 0.02em;
    padding: 1px 6px; border-radius: var(--r-inner);
    border: 1px solid currentColor;
  }}
  .dash-badge.live   {{ color: var(--dash-badge-live); }}
  .dash-badge.pre    {{ color: var(--dash-badge-pre); }}
  .dash-badge.post   {{ color: var(--dash-badge-post); }}
  .dash-badge.closed {{ color: var(--dash-badge-closed); }}
  .dash-badge.error  {{ color: var(--dash-badge-error); }}

  .dash-price {{
    font-size: var(--fs-8); font-weight: 600; color: var(--dash-ink);
    line-height: 1.12; letter-spacing: -0.02em;
  }}
  .dash-price-sub {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); margin-top: 1px;
  }}
  .dash-delta {{
    font-size: var(--fs-4); font-weight: 600; margin-top: 5px;
    font-variant-numeric: tabular-nums;
  }}
  .dash-delta.up   {{ color: var(--dash-up); }}
  .dash-delta.down {{ color: var(--dash-down); }}
  .dash-delta.flat {{ color: var(--dash-flat); }}

  .dash-extras {{
    margin-top: auto; padding-top: 10px;
    border-top: 1px solid var(--dash-divider);
    display: flex; flex-direction: column; gap: 4px;
  }}
  .dash-extra-row {{
    display: flex; justify-content: space-between; gap: 10px;
    font-size: var(--fs-3);
  }}
  .dash-extra-label {{ color: var(--dash-ink-muted); }}
  .dash-extra-value {{
    color: var(--dash-ink-2); font-weight: 600;
    font-variant-numeric: tabular-nums;
  }}
  .dash-extra-value.up   {{ color: var(--dash-up); }}
  .dash-extra-value.down {{ color: var(--dash-down); }}

  .dash-note {{
    margin-top: 9px; font-size: var(--fs-2); line-height: 1.45;
    color: var(--dash-ink-muted);
  }}
  .dash-error {{
    margin-top: 6px; font-size: var(--fs-2); line-height: 1.45;
    color: var(--dash-badge-error);
  }}
  .dash-unverified {{
    display: inline-block; margin-top: 7px;
    font-size: var(--fs-1); font-weight: 600;
    color: var(--dash-badge-pre);
    border: 1px dashed currentColor; border-radius: var(--r-inner);
    padding: 1px 6px;
  }}

  /* 상단 바 */
  .dash-topbar {{
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 2px 0 16px 0; font-family: {FONT_STACK};
  }}
  .dash-logo {{
    font-size: var(--fs-7); font-weight: 700; color: var(--dash-ink);
    letter-spacing: -0.02em;
  }}
  .dash-logo-sub {{
    font-size: var(--fs-3); color: var(--dash-ink-muted);
  }}
  .dash-clock {{
    margin-left: auto; font-size: var(--fs-3); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums;
  }}

  /* 카드 제목 링크 */
  a.dash-card-link {{
    color: var(--dash-ink); text-decoration: none;
    display: inline-flex; align-items: baseline; gap: 3px;
  }}
  a.dash-card-link:hover {{ text-decoration: underline; }}
  .dash-link-arrow {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); flex: none;
  }}
  /* 링크는 **색이 아니라 밑줄**로 표시합니다.
     전에는 var(--dash-down) 을 썼는데, 그건 '하락' 색입니다 — 등락 표기를
     한국식(하락=파랑)에서 미국식(하락=빨강)으로 바꾸면 링크 색까지 같이
     바뀌었고, 금융 화면에서 빨간 글자는 '떨어졌다' 로 읽힙니다.
     word-break:break-all 도 뺐습니다 — 한글 제목이 아무 데서나 잘렸습니다. */
  a.dash-inline-link {{
    color: var(--dash-ink-2);
    text-decoration: underline;
    text-decoration-color: var(--dash-ink-muted);
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
    overflow-wrap: break-word;
  }}
  a.dash-inline-link:hover {{
    color: var(--dash-ink); text-decoration-color: currentColor;
  }}
  a.dash-inline-link:focus-visible {{
    outline: 2px solid var(--dash-ink-muted); outline-offset: 2px;
    border-radius: var(--r-chip);
  }}

  /* 재고 지표 */
  .dash-cycle {{
    background:var(--dash-surface); border:1px solid var(--dash-border);
    border-radius: var(--r-card); padding:16px 18px 14px; margin-bottom:16px;
    font-family:{FONT_STACK};
  }}
  .dash-cycle-head {{
    display:flex; align-items:baseline; gap:9px; flex-wrap:wrap;
    font-size: var(--fs-6); font-weight:650; color:var(--dash-ink); margin-bottom:4px;
  }}
  .dash-cycle-sym {{ font-size: var(--fs-3); color:var(--dash-ink-muted); font-weight:500; }}
  .dash-cycle-basis {{
    margin-left:auto; font-size: var(--fs-3); color:var(--dash-ink-muted); font-weight:500;
  }}
  .dash-cycle-sub {{
    font-size: var(--fs-4); font-weight:650; color:var(--dash-ink-2);
    margin:18px 0 2px; padding-top:12px; border-top:1px solid var(--dash-divider);
  }}
  .dash-cycle .kpi {{ display:flex; gap:22px; flex-wrap:wrap; margin:10px 0 4px; }}
  .dash-cycle .kpi > div {{ min-width:118px; }}
  .dash-cycle .kpi .lbl {{ font-size: var(--fs-2); color:var(--dash-ink-muted); }}
  .dash-cycle .kpi .val {{
    font-size: var(--fs-7); font-weight:700; color:var(--dash-ink);
    letter-spacing:-.02em; font-variant-numeric:tabular-nums;
  }}

  .dash-cycle-warn {{
    border:1px solid var(--dash-badge-error); border-radius: var(--r-card);
    padding:11px 14px; margin-top:12px;
    font-size: var(--fs-3); line-height:1.6; color:var(--dash-ink-2);
  }}
  .dash-cycle-warn b {{ color:var(--dash-badge-error); }}

  /* 변화 감지 */
  .dash-sig-summary {{
    display:flex; gap:7px; flex-wrap:wrap; margin:0 0 14px 0;
    font-family:{FONT_STACK};
  }}
  .dash-sig-chip {{
    font-size: var(--fs-3); font-weight:650; padding:4px 11px; border-radius: var(--r-pill);
    border:1px solid currentColor;
  }}
  .dash-sig-chip.now  {{ color:var(--dash-up); }}
  .dash-sig-chip.week {{ color:var(--dash-badge-pre); }}
  .dash-sig-chip.fyi  {{ color:var(--dash-ink-muted); }}

  /* 시장 공시 — 묶음별 색. 상승·하락 색(빨강·파랑)과 겹치지 않게
     경고만 진한 적색, 나머지는 채도를 낮춘 서로 다른 색상(hue)으로. */
  .dash-fk {{
    display:inline-block; font-size: var(--fs-2); font-weight:650;
    padding:2px 8px; border-radius: var(--r-pill); white-space:nowrap;
    color:var(--fk-ink); background:var(--fk-bg); font-family:{FONT_STACK};
  }}
  .dash-fk-sub {{
    display:block; margin-top:3px; font-size: var(--fs-2);
    color:var(--dash-ink-2); white-space:nowrap;
  }}
  .dash-fk-risk, .dash-fc-risk       {{ --fk-ink:#a3221a; --fk-bg:#fbe9e7; }}
  .dash-fk-earn, .dash-fc-earn       {{ --fk-ink:#1f3a5f; --fk-bg:#e6ecf4; }}
  .dash-fk-dilute, .dash-fc-dilute   {{ --fk-ink:#93520a; --fk-bg:#fbf0de; }}
  .dash-fk-return, .dash-fc-return   {{ --fk-ink:#1b6b45; --fk-bg:#e3f2ea; }}
  .dash-fk-owner, .dash-fc-owner     {{ --fk-ink:#5d3a91; --fk-bg:#efe9f7; }}
  .dash-fk-biz, .dash-fc-biz         {{ --fk-ink:#0e6470; --fk-bg:#e2f1f3; }}
  .dash-fk-neutral, .dash-fc-neutral {{ --fk-ink:#535b66; --fk-bg:#edeff2; }}

  .dash-fc-grid {{
    display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr));
    gap:8px; margin:0 0 12px 0; font-family:{FONT_STACK};
  }}
  .dash-fc {{
    background:var(--dash-surface); border:1px solid var(--dash-border);
    border-left:4px solid var(--fk-ink); border-radius: var(--r-card);
    padding:8px 10px;
  }}
  .dash-fc.dim {{ opacity:.45; }}
  .dash-fc-head {{
    display:flex; justify-content:space-between; align-items:baseline;
    font-size: var(--fs-3); color:var(--fk-ink); font-weight:650;
  }}
  .dash-fc-head b {{ font-size: var(--fs-5); font-variant-numeric: tabular-nums; }}
  .dash-fc-sub {{
    margin-top:3px; font-size: var(--fs-2); color:var(--dash-ink-2);
    line-height:1.45;
  }}
  table.dash-table.dash-fl td, table.dash-table.dash-fl th {{
    vertical-align: top; text-align:left; }}
  table.dash-table.dash-fl td:last-child {{ white-space: normal; min-width: 240px; }}
  .dash-fl .dash-fl-type {{ white-space:nowrap; }}
  .dash-fl-mkt {{ font-size: var(--fs-2); color:var(--dash-ink-muted); margin-top:2px; }}
  .dash-fl-star {{ color:#b7791f; }}
  .dash-fl-flag {{
    display:inline-block; margin-left:6px; font-size: var(--fs-1, 11px);
    padding:0 6px; border:1px solid var(--dash-border); border-radius: var(--r-pill);
    color:var(--dash-ink-2); vertical-align:1px;
  }}
  .dash-fl-filer {{ font-size: var(--fs-2); color:var(--dash-ink-muted); margin-top:2px; }}
  .dash-fg-wrap {{ display:grid; gap:12px; font-family:{FONT_STACK}; }}

  /* 수급 · 배당 · 실적 표 — 숫자 칸 아래 작은 보조 줄 */
  table.dash-flowt td .sub, table.dash-divt td .sub, table.dash-est td .sub {{
    display:block; font-size: var(--fs-2); color:var(--dash-ink-muted);
    font-weight:500; margin-top:2px;
  }}
  table.dash-flowt td.up b, table.dash-flowt span.up, table.dash-est span.up,
  table.dash-flowt .sub.up {{ color:var(--dash-up); }}
  table.dash-flowt td.down b, table.dash-flowt span.down, table.dash-est span.down,
  table.dash-flowt .sub.down {{ color:var(--dash-down); }}
  table.dash-est .sub.up {{ color:var(--dash-up); }}
  table.dash-est .sub.down {{ color:var(--dash-down); }}
  table.dash-flowt td, table.dash-divt td, table.dash-est td {{ vertical-align:top; }}
  .dash-spark {{ display:block; }}
  .dash-spark line {{ stroke: var(--dash-divider); stroke-width:1; }}
  .dash-spark rect.up {{ fill: var(--dash-up); }}
  .dash-spark rect.down {{ fill: var(--dash-down); }}
  table.dash-divt tr.dv-other td {{ opacity:.55; }}
  table.dash-divt td.note {{ white-space:normal; min-width:160px; text-align:left;
                             color:var(--dash-ink-2); font-size: var(--fs-2); }}
  .dv-b {{ display:inline-block; font-size: var(--fs-1); padding:0 6px;
           border-radius: var(--r-pill); margin-left:4px; vertical-align:1px; }}
  .dv-b.ann {{ background:#e3f2ea; color:#1b6b45; }}
  .dv-b.est {{ background:#fbf0de; color:#93520a; }}
  table.dash-est td.es-cell {{ white-space:normal; text-align:left; }}
  .es-q {{ display:inline-flex; flex-direction:column; align-items:flex-start;
           gap:1px; margin:0 6px 4px 0; padding:4px 8px; min-width:74px;
           border:1px solid var(--dash-border); border-radius: var(--r-inner);
           font-size: var(--fs-2); background:var(--dash-surface); }}
  .es-q b {{ font-size: var(--fs-1); color:var(--dash-ink-muted); font-weight:600; }}
  .es-q span {{ font-size: var(--fs-3); font-weight:700; }}
  .es-q i {{ font-style:normal; color:var(--dash-ink-muted); font-size: var(--fs-1); }}
  .es-q.up {{ border-color: color-mix(in srgb, var(--dash-up) 45%, transparent); }}
  .es-q.down {{ border-color: color-mix(in srgb, var(--dash-down) 45%, transparent); }}
  table.dash-est a.dash-inline-link {{ display:block; font-size: var(--fs-2); margin-top:3px; }}
  .cal-k.dividend {{ color:#1b6b45; font-weight:650; }}
  .dash-fg ul {{ margin:6px 0 0 0; padding-left:18px; }}
  .dash-fg li {{ font-size: var(--fs-3); color:var(--dash-ink-2); line-height:1.55;
                 margin:2px 0; }}
  .dash-fg li b {{ color:var(--dash-ink); }}
  @media (max-width: 640px) {{
    .dash-fc-grid {{ grid-template-columns:repeat(2, 1fr); }}
    .dash-fl .dash-fl-type {{ white-space:normal; }}
  }}

  .dash-sig-empty {{
    border:1px solid var(--dash-border); border-radius: var(--r-card);
    padding:22px 20px; text-align:center;
    font-size: var(--fs-4); color:var(--dash-ink-muted);
    font-family:{FONT_STACK};
  }}

  .dash-signal {{
    background:var(--dash-surface);
    border:1px solid var(--dash-border);
    border-left:3px solid var(--dash-ink-muted);
    border-radius: var(--r-card); padding:13px 16px; margin-bottom:10px;
    font-family:{FONT_STACK};
  }}
  .dash-signal.now  {{ border-left-color:var(--dash-up); }}
  .dash-signal.week {{ border-left-color:var(--dash-badge-pre); }}
  .dash-signal.fyi  {{ border-left-color:var(--dash-ink-muted); }}

  .dash-sig-top {{
    display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:5px;
  }}
  .dash-sig-icon {{ font-size: var(--fs-5); }}
  .dash-sig-name {{ font-size: var(--fs-5); font-weight:650; color:var(--dash-ink); }}
  .dash-sig-sym  {{ font-size: var(--fs-2); color:var(--dash-ink-muted); }}
  .dash-sig-sev  {{
    margin-left:auto; font-size: var(--fs-2); font-weight:700;
    padding:1px 7px; border-radius: var(--r-inner); border:1px solid currentColor;
  }}
  .dash-sig-sev.now  {{ color:var(--dash-up); }}
  .dash-sig-sev.week {{ color:var(--dash-badge-pre); }}
  .dash-sig-sev.fyi  {{ color:var(--dash-ink-muted); }}

  .dash-sig-title  {{ font-size: var(--fs-5); font-weight:600; color:var(--dash-ink); }}
  .dash-sig-detail {{ font-size: var(--fs-3); color:var(--dash-ink-2); margin-top:3px; }}
  .dash-sig-tags   {{ display:flex; gap:4px; flex-wrap:wrap; margin-top:7px; }}
  .dash-sigtag {{
    font-size: var(--fs-1); color:var(--dash-ink-muted);
    border:1px solid var(--dash-divider); border-radius: var(--r-chip); padding:1px 6px;
  }}

  /* 헤드라인 — 신호 카드 **안쪽** 블록입니다. 상자로 그리면 카드 안에
     카드가 들어간 꼴이라 선 하나로만 구분합니다. */
  .dash-news {{
    margin: var(--sp-3) 0 0; padding: var(--sp-3) 0 0;
    border-top: 1px solid var(--dash-border);
  }}
  .dash-news-head {{
    font-size: var(--fs-1); font-weight:650; color:var(--dash-ink-muted);
    letter-spacing:.02em; margin-bottom:var(--sp-2);
  }}
  .dash-news ul {{ margin:0; padding-left:16px; }}
  .dash-news li {{
    font-size: var(--fs-3); margin-bottom:5px; line-height:1.55;
    color: var(--dash-ink-2);
  }}
  .dash-news li::marker {{ color: var(--dash-ink-muted); }}
  .dash-news-meta {{
    font-size: var(--fs-1); color:var(--dash-ink-muted); white-space:nowrap;
  }}

  /* 공시 분석 탭 */
  .dash-chiprow {{
    display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 16px 0;
    font-family: {FONT_STACK};
  }}
  .dash-chip {{
    display: flex; align-items: center; gap: 7px;
    background: var(--dash-surface);
    border: 1px solid var(--dash-border);
    border-radius: var(--r-pill); padding: 4px 11px;
  }}
  .dash-chip-name {{ font-size: var(--fs-3); color: var(--dash-ink); font-weight: 600; }}
  .dash-chip-marks {{ display: flex; gap: 3px; }}
  .dash-kindmark {{
    font-size: var(--fs-1); font-weight: 700; letter-spacing: 0.02em;
    padding: 1px 4px; border-radius: var(--r-chip); line-height: 1.5;
  }}
  .dash-kindmark.on  {{ color: #ffffff; background: var(--dash-badge-live); }}
  .dash-kindmark.off {{ color: var(--dash-ink-muted); background: var(--dash-divider); }}
  .dash-kindmark.stale {{ color: #0b0b0b; background: var(--dash-badge-pre); }}

  .dash-analysis-head {{
    background: var(--dash-surface);
    border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 13px 16px; margin-bottom: 14px;
    font-family: {FONT_STACK};
  }}
  .dash-analysis-name {{
    font-size: var(--fs-6); font-weight: 650; color: var(--dash-ink);
    margin-right: 10px;
  }}
  .dash-analysis-meta {{ font-size: var(--fs-3); color: var(--dash-ink-muted); }}

  .dash-analysis-body {{
    background: #ffffff; color: #0b0b0b;
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    padding: 18px 20px; overflow-x: auto;
    font-family: {FONT_STACK};
  }}
  .dash-analysis-body table {{ border-collapse: collapse; }}
  .dash-analysis-body img, .dash-analysis-body svg {{ max-width: 100%; height: auto; }}
  .dash-analysis-body a {{ color: #1c5cab; }}

  .dash-missing {{
    border: 1px dashed var(--dash-border); border-radius: var(--r-card);
    padding: 18px 20px; font-family: {FONT_STACK};
  }}
  .dash-missing-title {{
    font-size: var(--fs-5); font-weight: 650; color: var(--dash-ink); margin-bottom: 8px;
  }}
  .dash-missing-body {{
    font-size: var(--fs-4); line-height: 1.6; color: var(--dash-ink-2);
    margin: 10px 0 6px 0;
  }}
  .dash-missing-cmd {{
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: var(--fs-3); color: var(--dash-ink);
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-inner); padding: 8px 11px; margin-bottom: 4px;
    user-select: all; word-break: break-all;
  }}
  .dash-srclist {{ margin: 6px 0 0 0; padding-left: 18px; }}
  .dash-srclist li {{ margin-bottom: 3px; }}

  /* 테이블 */
  /* 표는 **자기 안에서** 위아래로 스크롤합니다. 30행짜리 표가 페이지를
     통째로 늘리면, 아래에 있는 카드까지 가려면 한참 내려야 합니다.
     머리글은 붙여 둬서 스크롤 중에도 어느 열인지 보입니다. */
  .dash-table-wrap {{
    overflow-x: auto; overflow-y: auto;
    max-height: 62vh;
    border: 1px solid var(--dash-border); border-radius: var(--r-inner);
    background: var(--dash-surface);
    /* 가로로 잘렸다는 걸 보이게 — 오른쪽 끝에 옅은 그라데이션을 붙여
       둡니다. 열이 9개면 1280px 에서도 잘리는데, 아무 표시가 없으면
       '그게 전부' 라고 읽습니다. 끝까지 스크롤하면 사라집니다. */
    background-image:
      linear-gradient(to right, var(--dash-surface) 30%,
                      rgba(255,255,255,0)),
      linear-gradient(to left, var(--dash-surface) 30%,
                      rgba(255,255,255,0)),
      linear-gradient(to right, rgba(21,24,28,.13), rgba(255,255,255,0) 14px),
      linear-gradient(to left, rgba(21,24,28,.13), rgba(255,255,255,0) 14px);
    background-position: left center, right center, left center, right center;
    background-repeat: no-repeat;
    background-size: 36px 100%, 36px 100%, 14px 100%, 14px 100%;
    background-attachment: local, local, scroll, scroll;
  }}
  .dash-table-wrap table.dash-table thead th {{
    position: sticky; top: 0; z-index: 2;
    background: var(--dash-raised);
    /* sticky 요소에는 테두리가 같이 붙지 않아 그림자로 선을 만듭니다 */
    box-shadow: inset 0 -1px 0 var(--dash-divider);
  }}
  /* 행이 적으면 max-height 에 닿지 않아 스크롤바가 생기지 않습니다 —
     별도 클래스가 필요 없습니다. */
  .dash-th-sym {{
    font-size: var(--fs-1); font-weight: 500; color: var(--dash-ink-muted);
  }}
  table.dash-table {{
    width: 100%; border-collapse: collapse;
    font-family: {FONT_STACK}; font-size: var(--fs-4);
    font-variant-numeric: tabular-nums;
  }}
  table.dash-table th, table.dash-table td {{
    padding: 8px 11px; text-align: right; white-space: nowrap;
    border-bottom: 1px solid var(--dash-divider);
  }}
  table.dash-table th {{
    color: var(--dash-ink-2); font-weight: 700;
    font-size: var(--fs-3); text-align: right;
    background: var(--dash-raised);
    border-bottom: 2px solid var(--dash-border);
  }}
  /* 첫 열은 가로 스크롤 중에도 붙어 있어야 '어느 종목 줄' 인지 압니다.
     sticky 요소는 배경이 투명하면 뒤 칸이 비쳐서 글자가 겹칩니다 —
     그래서 배경을 깔되, 줄무늬와 어긋나지 않게 **줄의 배경을 물려받습니다**
     (전에는 --dash-page 를 깔아 그 칸만 회색으로 떠 보였습니다). */
  table.dash-table th:first-child,
  table.dash-table td:first-child {{
    text-align: left; color: var(--dash-ink); font-weight: 650;
    position: sticky; left: 0;
    background: var(--dash-surface);
  }}
  table.dash-table tbody tr:nth-child(even) td:first-child {{
    background: var(--dash-raised);
  }}
  table.dash-table tbody tr:hover td:first-child {{ background: #e7ebf1; }}
  table.dash-table thead th:first-child {{ background: var(--dash-raised); left: 0; z-index: 3; }}
  table.dash-table td {{ color: var(--dash-ink); }}
  /* 줄이 길면 눈이 옆줄로 샙니다. 홀짝을 아주 옅게 깔아 줄을 잡아줍니다 —
     테두리를 더 긋는 것보다 조용합니다. */
  table.dash-table tbody tr:nth-child(even) {{
    background: var(--dash-raised);
  }}
  table.dash-table tbody tr:hover {{ background: #e7ebf1; }}
  table.dash-table td.na {{ color: var(--dash-ink-muted); }}

  /* 매크로 지표 — 방향에 가격의 적색/청색을 쓰지 않습니다.
     실업률 상승과 반도체 생산 상승은 의미가 반대이므로, 색으로 좋고 나쁨을
     암시하면 틀린 신호를 줍니다. 색은 '임계값을 건드렸다' 에만 씁니다. */
  .dash-macro-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
    gap: 10px; margin: 6px 0 18px;
  }}
  .dash-macro {{
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 12px 14px 10px;
    font-family: {FONT_STACK};
  }}
  .dash-macro.hit {{ border-color: var(--dash-up); }}
  .dash-macro-name {{
    font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink);
    display: flex; align-items: baseline; gap: 6px;
  }}
  .dash-macro-id {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); font-weight: 500;
    margin-left: auto; letter-spacing: .02em;
  }}
  .dash-macro-value {{
    font-size: var(--fs-8); font-weight: 600; color: var(--dash-ink);
    font-variant-numeric: tabular-nums; margin: 6px 0 1px;
    display: flex; align-items: baseline; gap: 8px;
  }}
  .dash-macro-dir {{
    font-size: var(--fs-3); font-weight: 600; color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums;
  }}
  .dash-macro-meta {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); margin-top: 3px;
    font-variant-numeric: tabular-nums;
  }}
  .dash-macro-meta .late {{ color: var(--dash-up); font-weight: 600; }}
  .dash-macro-why {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.5;
    margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--dash-divider);
  }}
  .dash-macro-spark {{ display: block; margin: 7px 0 2px; }}
  .dash-macro-err {{ font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.5; }}
  /* 데모 배지 — 가짜 숫자를 가짜라고 말해주는 장치.
     데모 데이터가 그럴듯해서 실제 값과 구분이 안 되는 문제가 있었습니다. */
  .dash-demo-banner {{
    background: var(--dash-raised);
    border: 1px solid var(--dash-up); border-left-width: 3px;
    border-radius: var(--r-card); padding: 11px 14px; margin: 0 0 14px;
    font-family: {FONT_STACK};
  }}
  .dash-demo-banner .db-title {{
    font-size: var(--fs-4); font-weight: 700; color: var(--dash-up);
  }}
  .dash-demo-banner .db-body {{
    font-size: var(--fs-3); color: var(--dash-ink-2); line-height: 1.6;
    margin-top: 4px;
  }}
  .dash-demo-tag {{
    display: inline-block; font-size: var(--fs-1); font-weight: 700;
    letter-spacing: .04em; padding: 1px 5px; border-radius: var(--r-chip);
    border: 1px solid var(--dash-up); color: var(--dash-up);
    vertical-align: 2px; margin-left: 6px;
  }}

  /* 요약 — 휴대폰 10초 화면 */
  .dash-verdict-band {{
    background: var(--dash-raised); border: 1px solid var(--dash-border);
    border-left: 3px solid var(--dash-ink-muted);
    border-radius: var(--r-card); padding: 13px 15px; margin: 2px 0 14px;
    font-family: {FONT_STACK};
  }}
  .dash-verdict-band.attention {{ border-left-color: var(--dash-up); }}
  .dash-verdict-band .vb-main {{
    font-size: var(--fs-6); font-weight: 650; color: var(--dash-ink);
    line-height: 1.45;
  }}
  .dash-verdict-band .vb-sub {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); margin-top: 4px;
  }}
  .dash-srow {{
    display: grid; grid-template-columns: 62px 1fr; gap: 10px;
    align-items: start; padding: 11px 13px; margin-bottom: 8px;
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); font-family: {FONT_STACK};
  }}
  .dash-srow.alert {{ border-color: var(--dash-up); }}
  .dash-srow-chip {{
    font-size: var(--fs-1); font-weight: 650; text-align: center;
    padding: 3px 0; border-radius: var(--r-inner); white-space: nowrap;
    border: 1px solid var(--dash-border); color: var(--dash-ink-muted);
  }}
  .dash-srow.alert .dash-srow-chip {{
    border-color: var(--dash-up); color: var(--dash-up);
  }}
  .dash-srow.watch .dash-srow-chip {{ color: var(--dash-ink); }}
  .dash-srow-title {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); display: block;
  }}
  .dash-srow-head {{
    font-size: var(--fs-5); font-weight: 600; color: var(--dash-ink);
    line-height: 1.45;
  }}
  .dash-srow-detail {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.55;
    margin-top: 3px;
  }}
  .dash-srow-goto {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); margin-top: 4px;
  }}
  @media (max-width: 640px) {{
    .dash-srow {{ grid-template-columns: 54px 1fr; gap: 8px; }}
    .dash-verdict-band .vb-main {{ font-size: var(--fs-5); }}
  }}

  /* 카드 그리드 — app.py 가 class="dash-grid cols-4" 를 쓰는데 규칙이
     theme.py 에 없었습니다. tools/preview.py 에만 있어서, 프리뷰는 정상인데
     **실제 앱에서는 카드가 그리드로 배치되지 않았습니다.** 프리뷰만 확인한
     탓에 놓친 버그입니다. */
  .dash-grid {{
    display: grid; gap: 10px; margin: 6px 0 18px;
    grid-template-columns: repeat(var(--cols, 4), minmax(0, 1fr));
  }}
  .dash-grid.cols-4 {{ --cols: 4; }}
  .dash-grid.cols-3 {{ --cols: 3; }}
  .dash-grid.cols-2 {{ --cols: 2; }}

  /* 휴대폰 — 세로 화면에서 4열은 글자가 안 읽힙니다 */
  @media (max-width: 1100px) {{
    .dash-grid {{ --cols: 2 !important; }}
  }}
  @media (max-width: 640px) {{
    /* 좁은 폭에서는 제목 / 부제 / 개수를 줄바꿈해 흐르게 둡니다.
       한 줄에 밀어넣으면 제목이 압축돼 글자 단위로 쪼개집니다. */
    .dash-section-head {{ flex-wrap: wrap; gap: var(--sp-2); }}
    .dash-section-count {{ margin-left: 0; order: 3; }}
    .dash-section-sub {{ flex-basis: 100%; order: 2; }}
    .dash-grid {{ --cols: 2 !important; gap: 7px; }}
    /* 표는 가로 스크롤로 — 9개 컬럼을 390px 에 밀어넣으면 못 읽습니다 */
    .dash-table-wrap {{
      overflow-x: auto; overflow-y: auto; max-height: 52vh;
      -webkit-overflow-scrolling: touch;
    }}
    table.dash-table {{ font-size: var(--fs-3); }}
    table.dash-table th, table.dash-table td {{
      padding: 5px 7px; white-space: nowrap;
    }}
    /* 큰 숫자는 조금 줄입니다 */
    .dash-fg-score {{ font-size: var(--fs-8); }}
    .dash-vix-spot {{ font-size: var(--fs-8); }}
    .dash-card-price {{ font-size: var(--fs-6); }}
    /* 사슬·세부지표는 한 줄에 둘씩 */
    .dash-chain {{ grid-template-columns: repeat(auto-fit, minmax(76px, 1fr)); }}
    .dash-fg-comps {{ grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); }}
    .dash-macro-grid {{ grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}

    /* SVG 는 viewBox 가 축소되면서 글자도 같이 줄어듭니다. 390px 화면에서
       9px 라벨은 4~5px 로 렌더링돼 읽을 수 없으므로 키웁니다. */
    svg.dash-dio text {{ font-size: 13px; }}
    svg.dash-vix-curve text {{ font-size: 13px; }}
    svg.dash-fg-gauge text {{ font-size: 11px; }}
    .dash-macro-spark {{ height: 34px; }}
  }}

  /* VIX 기간구조 */
  .dash-vix {{
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 13px 15px 11px; margin: 4px 0 16px;
    font-family: {FONT_STACK};
  }}
  .dash-vix.inverted {{ border-color: var(--dash-up); }}
  .dash-vix-top {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
  .dash-vix-spot {{
    font-size: var(--fs-9); font-weight: 650; color: var(--dash-ink);
    font-variant-numeric: tabular-nums; line-height: 1;
  }}
  .dash-vix-struct {{ font-size: var(--fs-5); font-weight: 650; color: var(--dash-ink); }}
  .dash-vix-struct.inverted {{ color: var(--dash-up); }}
  .dash-vix-pct {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); margin-left: auto;
    font-variant-numeric: tabular-nums; text-align: right;
  }}
  .dash-vix-curve {{ display: block; width: 100%; height: auto; max-width: 520px; }}
  .dash-vix-lines {{
    font-size: var(--fs-3); color: var(--dash-ink-2); line-height: 1.6; margin-top: 8px;
  }}
  .dash-vix-lines b {{ color: var(--dash-ink); }}

  /* 공포탐욕지수 */
  .dash-fg {{
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 13px 15px 11px; margin: 4px 0 16px;
    font-family: {FONT_STACK};
  }}
  .dash-fg-top {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
  .dash-fg-score {{
    font-size: var(--fs-9); font-weight: 650; color: var(--dash-ink);
    font-variant-numeric: tabular-nums; line-height: 1;
  }}
  .dash-fg-band {{ font-size: var(--fs-5); font-weight: 600; color: var(--dash-ink); }}
  .dash-fg-delta {{
    font-size: var(--fs-2); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums; margin-left: auto; text-align: right;
  }}
  .dash-fg-gauge {{ display: block; width: 100%; height: auto; margin: 10px 0 4px; }}
  .dash-fg-comps {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 7px; margin-top: 10px;
  }}
  .dash-fg-comp {{
    border: 1px solid var(--dash-border); border-radius: var(--r-inner); padding: 7px 9px;
  }}
  .dash-fg-comp.extreme {{ border-color: var(--dash-ink-muted); }}
  .dash-fg-comp .nm {{
    font-size: var(--fs-2); color: var(--dash-ink); font-weight: 600; display: block;
  }}
  .dash-fg-comp .sc {{
    font-size: var(--fs-4); font-weight: 600; color: var(--dash-ink-2);
    font-variant-numeric: tabular-nums;
  }}
  .dash-fg-comp .bd {{ font-size: var(--fs-1); color: var(--dash-ink-muted); }}
  .dash-fg-comp .ds {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); line-height: 1.45;
    display: block; margin-top: 3px;
  }}

  /* DIO 차트 — 폭에 맞춰 늘어나되 세로비를 유지합니다 */
  svg.dash-dio {{
    display: block; width: 100%; height: auto; max-width: 1000px;
    margin: var(--sp-1) 0 2px;
  }}

  /* 괴리율 사슬 */
  .dash-chain {{
    display: grid; gap: 7px;
    grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
    align-items: stretch; margin: 2px 0 0;
  }}
  .dash-chain-step {{
    border: 1px solid var(--dash-border); border-radius: var(--r-inner);
    padding: 7px 9px; background: var(--dash-surface);
    position: relative;
  }}
  .dash-chain-step.op {{
    border: none; background: none; display: flex;
    align-items: center; justify-content: center; padding: 0;
    color: var(--dash-ink-muted); font-size: var(--fs-6); font-weight: 600;
    min-width: 18px;
  }}
  .dash-chain-step.out {{ border-color: var(--dash-ink-muted); }}
  .dash-chain-step .lb {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); display: block;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .dash-chain-step .vl {{
    font-size: var(--fs-5); font-weight: 600; color: var(--dash-ink);
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .dash-chain-step .sub {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); display: block;
    white-space: nowrap;
  }}
  .dash-pair {{
    background: var(--dash-raised); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 12px 14px; margin-bottom: 10px;
    font-family: {FONT_STACK};
  }}
  .dash-pair-top {{
    display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap;
    margin-bottom: 9px;
  }}
  .dash-pair-name {{
    font-size: var(--fs-5); font-weight: 650; color: var(--dash-ink);
  }}
  .dash-pair-tag {{
    font-size: var(--fs-1); color: var(--dash-ink-muted);
    border: 1px solid var(--dash-border); border-radius: var(--r-chip); padding: 1px 5px;
  }}
  .dash-pair-prem {{
    margin-left: auto; font-size: var(--fs-6); font-weight: 650;
    font-variant-numeric: tabular-nums;
  }}
  .dash-pair-note {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.55;
    margin-top: 8px; padding-top: 7px;
    border-top: 1px solid var(--dash-divider);
  }}
  .dash-live {{
    display: inline-flex; align-items: center; gap: 5px;
    font-size: var(--fs-2); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums;
  }}
  .dash-live .dot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--dash-ink-muted); display: inline-block;
  }}
  .dash-live.on .dot {{ background: var(--dash-up); }}
  .dash-live.frozen .dot {{ background: var(--dash-down); }}

  /* 판단 재료 (사분면) */
  .dash-verdict {{
    background: var(--dash-raised); border: 1px solid var(--dash-border);
    border-left: 3px solid var(--dash-ink-muted);
    border-radius: var(--r-card); padding: 11px 14px; margin: 9px 0 0;
    font-family: {FONT_STACK};
  }}
  .dash-verdict.q1 {{ border-left-color: var(--dash-ink); }}
  .dash-verdict.q2 {{ border-left-color: var(--dash-up); }}
  .dash-verdict.q3 {{ border-left-color: var(--dash-down); }}
  .dash-verdict-pos {{
    font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink);
    margin-bottom: 5px;
  }}
  .dash-verdict-line {{
    font-size: var(--fs-3); color: var(--dash-ink-2); line-height: 1.6;
  }}
  .dash-verdict-line b {{ color: var(--dash-ink); }}
  .dash-verdict-cav {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.55;
    margin-top: 6px; padding-top: 6px;
    border-top: 1px solid var(--dash-divider);
  }}
  .dash-verdict-next {{
    font-size: var(--fs-2); color: var(--dash-ink-2); line-height: 1.6;
    margin-top: 6px; padding-left: 15px;
  }}
  .dash-dcf-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px; margin: 8px 0 2px;
  }}
  .dash-dcf-cell {{
    border: 1px solid var(--dash-border); border-radius: var(--r-inner);
    padding: 7px 10px; background: var(--dash-surface);
  }}
  .dash-dcf-cell .lb {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); display: block;
  }}
  .dash-dcf-cell .vl {{
    font-size: var(--fs-5); font-weight: 600; color: var(--dash-ink);
    font-variant-numeric: tabular-nums;
  }}

  /* 버핏 스크리너 */
  .dash-screen {{
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 13px 15px 11px; margin-bottom: 10px;
    font-family: {FONT_STACK};
  }}
  .dash-screen-top {{
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  }}
  .dash-screen-tkr {{
    font-size: var(--fs-5); font-weight: 700; color: var(--dash-ink);
    letter-spacing: .01em;
  }}
  .dash-screen-name {{ font-size: var(--fs-3); color: var(--dash-ink-muted); }}
  .dash-screen-score {{
    margin-left: auto; font-size: var(--fs-4); font-weight: 650;
    font-variant-numeric: tabular-nums; color: var(--dash-ink-2);
  }}
  .dash-screen-score .unk {{
    font-size: var(--fs-2); font-weight: 500; color: var(--dash-ink-muted);
  }}
  .dash-screen-checks {{ margin-top: 9px; display: grid; gap: 5px; }}
  .dash-check {{
    display: grid; grid-template-columns: 17px 1fr auto;
    gap: 8px; align-items: baseline; font-size: var(--fs-3);
  }}
  .dash-check .mk {{ font-weight: 700; text-align: center; }}
  .dash-check.pass .mk {{ color: var(--dash-up); }}
  .dash-check.fail .mk {{ color: var(--dash-down); }}
  .dash-check.unknown .mk {{ color: var(--dash-ink-muted); }}
  .dash-check .nm {{ color: var(--dash-ink); font-weight: 600; }}
  .dash-check .vl {{
    color: var(--dash-ink-2); font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }}
  .dash-check-detail {{
    grid-column: 2 / -1; font-size: var(--fs-2); color: var(--dash-ink-muted);
    line-height: 1.5; margin-top: -2px;
  }}
  .dash-check-warn {{
    grid-column: 2 / -1; font-size: var(--fs-2); color: var(--dash-up);
    line-height: 1.5; margin-top: 1px;
  }}
  .dash-prov {{
    display: inline-block; font-size: var(--fs-1); font-weight: 600;
    padding: 1px 5px; border-radius: var(--r-chip); margin-left: 5px;
    border: 1px solid var(--dash-border); color: var(--dash-ink-muted);
    vertical-align: 1px;
  }}
  .dash-prov.verbatim {{ color: var(--dash-ink); border-color: var(--dash-ink-muted); }}
  .dash-screen-err {{
    font-size: var(--fs-3); color: var(--dash-ink-muted); line-height: 1.5;
    margin-top: 6px;
  }}

  /* ── 브리핑 (생성) ────────────────────────────────────────────────── */
  .dash-brief {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); padding: var(--sp-3) 16px var(--sp-2);
    margin: var(--sp-1) 0 var(--sp-4);
  }}
  .dash-brief-top {{
    display: flex; align-items: baseline; gap: var(--sp-3);
    flex-wrap: wrap; padding-bottom: var(--sp-2);
    border-bottom: 1px solid var(--dash-divider); margin-bottom: var(--sp-2);
  }}
  .dash-brief-head {{
    font-size: var(--fs-5); font-weight: 700; color: var(--dash-ink);
  }}
  .dash-brief-asof {{
    margin-left: auto; font-size: var(--fs-1); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .dash-brief-line {{
    display: grid; grid-template-columns: 56px 1fr; gap: var(--sp-3);
    align-items: baseline; padding: 5px 0;
  }}
  .dash-brief-topic {{
    font-size: var(--fs-1); font-weight: 650; color: var(--dash-ink-muted);
    text-align: right;
  }}
  .dash-brief-text {{
    font-size: var(--fs-4); line-height: 1.6; color: var(--dash-ink-2);
  }}
  .dash-brief-line.warm .dash-brief-text {{ color: var(--dash-ink); }}
  .dash-brief-line.hot .dash-brief-topic {{ color: var(--dash-up); }}
  .dash-brief-line.hot .dash-brief-text {{
    color: var(--dash-ink); font-weight: 550;
  }}
  @media (max-width: 640px) {{
    .dash-brief-line {{ grid-template-columns: 1fr; gap: 1px; }}
    .dash-brief-topic {{ text-align: left; }}
    .dash-brief-asof {{ margin-left: 0; }}
  }}

  /* ── 증시 브리핑 ──────────────────────────────────────────────────── */
  .dash-bf {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); padding: 12px 14px; margin: 4px 0 10px;
  }}
  .dash-bf-top {{
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  }}
  .dash-bf-title {{
    font-size: var(--fs-5); font-weight: 700; color: var(--dash-ink);
    line-height: 1.4;
  }}
  .dash-bf-date {{
    margin-left: auto; font-size: var(--fs-3); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .dash-bf-stale {{
    display: block; margin-top: 7px; font-size: var(--fs-2); line-height: 1.5;
    color: var(--dash-down);
  }}
  .dash-bf-src {{
    margin-top: 7px; font-size: var(--fs-2); color: var(--dash-ink-muted);
    line-height: 1.6;
  }}
  /* 요약 탭 한 줄 */
  .dash-bf-line {{
    display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap;
    border: 1px solid var(--dash-border); border-radius: var(--r-inner);
    background: var(--dash-surface); padding: 8px 12px; margin: 2px 0 10px;
  }}
  .dash-bf-line-tag {{
    font-size: var(--fs-1); font-weight: 700; letter-spacing: .04em;
    color: var(--dash-ink-muted); border: 1px solid var(--dash-border);
    border-radius: var(--r-chip); padding: 1px 5px; white-space: nowrap;
  }}
  .dash-bf-line-title {{
    font-size: var(--fs-4); font-weight: 600; color: var(--dash-ink);
    line-height: 1.4;
  }}
  .dash-bf-line-date {{
    margin-left: auto; font-size: var(--fs-2); color: var(--dash-ink-muted);
    white-space: nowrap;
  }}

  /* ── 잠정실적 레이더 ──────────────────────────────────────────────── */
  .dash-prelim {{ display: grid; gap: 5px; margin: 4px 0 8px; }}
  .dash-prelim-row {{
    display: grid; grid-template-columns: 84px 86px 1fr auto auto;
    gap: 9px; align-items: baseline; font-size: var(--fs-3);
    padding: 6px 0; border-bottom: 1px solid var(--dash-divider);
  }}
  .dash-prelim-date {{
    color: var(--dash-ink-muted); font-variant-numeric: tabular-nums;
  }}
  .dash-prelim-corp {{ color: var(--dash-ink); font-weight: 650; }}
  .dash-prelim-nm {{ color: var(--dash-ink-2); line-height: 1.4; }}
  .dash-prelim-age {{
    color: var(--dash-ink-muted); font-size: var(--fs-2); white-space: nowrap;
  }}
  .dash-prelim-link {{ font-size: var(--fs-2); white-space: nowrap; }}
  .dash-prelim-empty {{
    font-size: var(--fs-3); color: var(--dash-ink-muted); line-height: 1.6;
  }}

  /* ── 파일 버전 경고 ───────────────────────────────────────────────── */
  .dash-build-warn, .dash-build-note {{
    border-radius: var(--r-card); padding: var(--sp-3) 15px;
    margin: 0 0 var(--sp-4); font-size: var(--fs-3); line-height: 1.6;
  }}
  .dash-build-warn {{
    border: 1px solid var(--dash-badge-error);
    color: var(--dash-ink);
  }}
  .dash-build-note {{
    border: 1px dashed var(--dash-border); color: var(--dash-ink-muted);
  }}
  .dash-build-files {{
    margin: var(--sp-2) 0 0; padding-left: 1.2em;
  }}
  .dash-build-files li {{ margin: var(--sp-1) 0; }}

  /* ── 사이드바 숨김 ────────────────────────────────────────────────── */
  /* 설정은 controls() 가 페이지 안에 그립니다. 사이드바를 비워 두면
     Streamlit 이 왼쪽에 펼침 화살표만 남기는데, 눌러도 빈 패널이 나와
     고장난 것처럼 보입니다. 통째로 없앱니다. */
  section[data-testid="stSidebar"] {{ display: none !important; }}
  button[data-testid="stSidebarCollapsedControl"],
  div[data-testid="stSidebarCollapsedControl"],
  button[data-testid="baseButton-headerNoPadding"] {{
    display: none !important;
  }}
  /* 사이드바가 빠진 만큼 본문이 왼쪽 끝에 붙지 않게 여백을 둡니다 */
  section[data-testid="stMain"] .block-container {{
    padding-top: var(--sp-4);
  }}

  /* ── 시장 전환 — 최상위 축 ────────────────────────────────────────── */
  /* 제목 옆 배지 — 지금 어느 시장인지 항상 보이게 */
  .dash-market-badge {{
    display: inline-block; margin-left: 10px;
    font-size: var(--fs-4); font-weight: 750;
    color: #ffffff; background: var(--dash-accent);
    padding: 3px 11px; border-radius: var(--r-pill);
    vertical-align: middle; letter-spacing: -0.01em;
  }}
  /* 전환 버튼 — 다른 위젯보다 크게. 표식 바로 다음 위젯만 집습니다. */
  div[data-testid="stElementContainer"]:has(.dash-marketmark)
    + div[data-testid="stElementContainer"] button {{
    font-size: var(--fs-5) !important; font-weight: 700 !important;
    padding: 8px 22px !important; min-height: 42px;
  }}
  div[data-testid="stElementContainer"]:has(.dash-marketmark)
    + div[data-testid="stElementContainer"] {{
    margin-bottom: var(--sp-2);
  }}

  /* ── 세로 섹션 내비 ───────────────────────────────────────────────── */
  /*
     2026-11-11: "왼쪽 버튼이 잘 안 보인다". 원인이 둘이었습니다.
     (1) hover 배경이 **존재하지 않는 변수**(--dash-surface-raised)를
         가리켜서 아무 일도 안 일어났습니다.
     (2) 선택된 항목에 아무 표시를 안 줬습니다. 프리뷰에서는 남색 막대가
         보였는데 그건 .pv-tab 전용이었고, 실제 앱의 라디오에는 적용되지
         않았습니다 — 프리뷰만 보고 다 됐다고 여긴 제 실수입니다.

     이제 내비 전체를 **흰 패널 한 장**으로 두고, 선택된 항목에 남색
     막대와 굵은 글씨를 줍니다. 회색 바탕 위의 흰 패널이라 어디까지가
     내비인지 경계가 보입니다.
  */
  /* 내비가 들어 있는 **칸 자체**를 흰 패널로 만듭니다. 스트림릿 위젯을
     HTML div 로 감쌀 수 없어서, 표식을 하나 넣고 :has() 로 그 칸을
     집습니다. :has() 가 없으면 배경만 안 깔리고 목록은 그대로 돕니다. */
  div[data-testid="stColumn"]:has(.dash-navmark),
  div[data-testid="column"]:has(.dash-navmark) {{
    background: var(--dash-surface);
    border: 1px solid var(--dash-border);
    border-radius: var(--r-card);
    padding: var(--sp-3) var(--sp-2) var(--sp-3);
    align-self: flex-start;
  }}
  .dash-navhead {{
    font-size: var(--fs-2); font-weight: 750; letter-spacing: .04em;
    color: var(--dash-ink-2);
    margin: var(--sp-3) 0 var(--sp-2); padding-left: 6px;
    display: flex; align-items: center; gap: 6px;
  }}
  /* 묶음 색 점 — 버튼 색과 같은 색 */
  .dash-navhead i {{
    width: 9px; height: 9px; border-radius: var(--r-pill); flex: 0 0 auto;
    background: var(--dot, var(--dash-accent));
  }}
  /* 본문 맨 위 — 지금 어디인지 (묶음 › 섹션), 묶음 색 알약 */
  .dash-crumb {{
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--grp-mid, var(--dash-raised)); color: var(--dash-ink);
    border-radius: var(--r-pill); padding: 3px 12px;
    font-size: var(--fs-3); font-weight: 650; margin: 0 0 var(--sp-2);
  }}
  .dash-crumb span {{ font-weight: 500; color: var(--dash-ink-2); }}
  .dash-navhead:first-child {{ margin-top: 0; }}

  /* 섹션 버튼 — 스트림릿 버튼을 그대로 쓰고 **모양만** 다듬습니다.
     전에는 라디오를 목록처럼 꾸몄는데 (1) 동그라미를 숨기니 선택 안 된
     항목은 그냥 글자였고 (2) 이 규칙이 **화면의 모든 라디오**에 걸려
     '대상'·'색 규칙' 라디오의 동그라미까지 지웠습니다. 이제 내비 칸
     안의 버튼에만 겁니다. 아래 규칙이 안 먹어도 버튼은 테마가 그린
     테두리·남색 채움으로 보입니다. */
  div[data-testid="stColumn"]:has(.dash-navmark) div[data-testid="stButton"],
  div[data-testid="column"]:has(.dash-navmark) div[data-testid="stButton"] {{
    margin-bottom: -6px;
  }}
  div[data-testid="stColumn"]:has(.dash-navmark) button,
  div[data-testid="column"]:has(.dash-navmark) button {{
    justify-content: flex-start !important;
    text-align: left; min-height: 40px;
    padding: 6px 12px !important;
    border-radius: var(--r-inner) !important;
    font-size: var(--fs-4) !important;
  }}
  div[data-testid="stColumn"]:has(.dash-navmark) button[kind="secondary"],
  div[data-testid="column"]:has(.dash-navmark) button[kind="secondary"] {{
    background: var(--dash-surface) !important;
    border: 1px solid color-mix(in srgb, var(--dash-ink) 26%, var(--dash-surface)) !important;
    color: var(--dash-ink) !important;
  }}
  div[data-testid="stColumn"]:has(.dash-navmark) button[kind="secondary"]:hover,
  div[data-testid="column"]:has(.dash-navmark) button[kind="secondary"]:hover {{
    background: var(--dash-raised) !important;
    border-color: var(--dash-accent) !important;
  }}
  div[data-testid="stColumn"]:has(.dash-navmark) button[kind="primary"],
  div[data-testid="column"]:has(.dash-navmark) button[kind="primary"] {{
    font-weight: 750 !important;
  }}
  div[data-testid="stColumn"]:has(.dash-navmark) button p,
  div[data-testid="column"]:has(.dash-navmark) button p {{
    font-size: var(--fs-4) !important; text-align: left;
  }}

  /* 휴대폰: 칸이 위아래로 쌓이면 버튼 8개가 세로로 늘어서 본문이 한참
     아래로 밀립니다. 좁은 화면에서는 버튼을 가로로 흘려 담습니다. 이
     규칙이 안 먹으면 세로 목록으로 남을 뿐입니다. */
  @media (max-width: 640px) {{
    div[data-testid="stColumn"]:has(.dash-navmark) div[data-testid="stVerticalBlock"] {{
      flex-direction: row !important; flex-wrap: wrap !important;
      gap: 6px !important;
    }}
    div[data-testid="stColumn"]:has(.dash-navmark) div[data-testid="stElementContainer"] {{
      width: auto !important; flex: 0 0 auto !important;
    }}
    div[data-testid="stColumn"]:has(.dash-navmark)
      div[data-testid="stElementContainer"]:has(.dash-navhead),
    div[data-testid="stColumn"]:has(.dash-navmark)
      div[data-testid="stElementContainer"]:has(.dash-navmark) {{
      flex-basis: 100% !important; width: 100% !important;
    }}
    div[data-testid="stColumn"]:has(.dash-navmark) button {{
      width: auto !important; min-height: 36px;
    }}
    div[data-testid="stColumn"]:has(.dash-navmark) div[data-testid="stButton"] {{
      margin-bottom: 0;
    }}
  }}

  .dash-empty-reason {{
    border: 1px solid var(--dash-border); border-left: 3px solid var(--dash-badge-error);
    background: var(--dash-surface); border-radius: var(--r-inner);
    padding: var(--sp-3) var(--sp-3); font-size: var(--fs-3); color: var(--dash-ink);
    margin: var(--sp-2) 0;
  }}
  .dash-empty-reason ul {{ margin: var(--sp-2) 0 0; padding-left: 1.2em; }}
  .dash-empty-reason li {{ margin: 3px 0; word-break: break-word; color: var(--dash-ink-2); }}

  /* ── 시장 띠 ──────────────────────────────────────────────────────── */
  /* 카드가 아니라 한 장의 띠. 칸 사이 세로선, 큰 숫자, 작은 이름. */
  /* 2026-11-13 폰: "지수 수치 맨 위 표시가 너무 밋밋" (09:40) → "다시" (09:46).
     칸마다 흰 카드. 오른쪽 위 모서리에서 등락색이 옅게 번지고(방향이 한눈에),
     숫자는 크게, 그 아래 '▲ 전일 대비 값 · 등락률' 을 등락색으로 적습니다.
     색의 뜻은 그대로(상승 적 · 하락 청), ▲▼ 와 부호를 같이 적습니다. */
  .dash-mstrip {{
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px; margin: 0 0 var(--sp-4);
  }}
  .ms-cell {{
    position: relative; overflow: hidden;
    padding: 10px 12px 10px; min-width: 0;
    background: var(--dash-surface); border-radius: var(--r-card);
    border: 1px solid var(--dash-divider);
    display: flex; flex-direction: column; align-items: flex-start; gap: 1px;
  }}
  .ms-cell::before {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(120% 90% at 100% 0%,
      color-mix(in srgb, var(--ms-tone, transparent) 16%, transparent) 0%,
      transparent 62%);
  }}
  .ms-cell.up {{ --ms-tone: var(--dash-up); }}
  .ms-cell.down {{ --ms-tone: var(--dash-down); }}
  .ms-cell > * {{ position: relative; }}
  .ms-label {{ font-size: var(--fs-2); font-weight: 650; color: var(--dash-ink-2);
              max-width: 100%;
              white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .ms-val {{ font-size: var(--fs-7); font-weight: 800; color: var(--dash-ink);
            font-variant-numeric: tabular-nums; letter-spacing: -0.025em;
            line-height: 1.2; white-space: nowrap; }}
  .ms-chg {{ font-size: var(--fs-2); font-weight: 700;
            font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .ms-chg small {{ font-size: inherit; font-weight: 600; opacity: .85; }}
  .ms-chg.up {{ color: var(--dash-up); }}
  .ms-chg.down {{ color: var(--dash-down); }}
  .ms-chg.flat {{ color: var(--dash-ink-muted); }}
  @media (max-width: 760px) {{
    .dash-mstrip {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }}
    .ms-cell {{ padding: 8px 9px 8px; }}
    .ms-val {{ font-size: var(--fs-5); }}
    .ms-chg small {{ display: none; }}      /* 좁으면 등락률만 */
  }}

  /* ── 섹터 온도 — 순위 막대 · 온도 격자 (2026-11-13) ─────────────────── */
  .dash-sbar2, .dash-hgrid {{
    background: var(--dash-surface); border: 1px solid var(--dash-divider);
    border-radius: var(--r-card); padding: 12px 12px 10px; margin: 0 0 var(--sp-3);
  }}
  .sb-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px;
             margin-bottom: 8px; }}
  .sb-head b {{ font-size: var(--fs-4); color: var(--dash-ink); }}
  .sb-head span {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .sb-row {{ display: grid; grid-template-columns: 5.6em minmax(0, 1fr) 3.4em;
            align-items: center; gap: 8px; padding: 3px 0; }}
  .sb-name {{ font-size: var(--fs-3); font-weight: 600; color: var(--dash-ink);
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .sb-track {{ position: relative; height: 14px; border-radius: var(--r-chip);
              background: var(--dash-raised); }}
  .sb-track::after {{ content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px;
                     width: 1px; background: var(--dash-ink-muted); opacity: .55; }}
  .sb-track i {{ position: absolute; top: 0; bottom: 0; border-radius: var(--r-chip); }}
  .sb-track i.up {{ background: color-mix(in srgb, var(--dash-up) 62%, var(--dash-surface)); }}
  .sb-track i.down {{ background: color-mix(in srgb, var(--dash-down) 62%, var(--dash-surface)); }}
  .sb-val {{ font-size: var(--fs-3); font-weight: 700; text-align: right;
            font-variant-numeric: tabular-nums; }}
  .sb-val.up {{ color: var(--dash-up); }}
  .sb-val.down {{ color: var(--dash-down); }}
  .sb-val.flat {{ color: var(--dash-ink-muted); }}
  .hg-row {{ display: grid; grid-template-columns: 5.6em repeat(4, minmax(0, 1fr));
            gap: 3px; margin-bottom: 3px; align-items: stretch; }}
  .hg-head span {{ font-size: var(--fs-1); color: var(--dash-ink-muted); text-align: center; }}
  .hg-name {{ font-size: var(--fs-3); font-weight: 600; color: var(--dash-ink);
             align-self: center;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .hg-cell {{ font-size: var(--fs-2); font-weight: 600; text-align: center;
             color: var(--dash-ink); padding: 6px 0; border-radius: var(--r-chip);
             font-variant-numeric: tabular-nums; }}
  .hg-cell.strong {{ font-weight: 750; }}
  .hg-cell.na {{ color: var(--dash-ink-muted); background: var(--dash-raised); }}
  .hg-bench {{ padding-bottom: 5px; margin-bottom: 6px;
              border-bottom: 1px dashed var(--dash-divider); }}

  /* ── 아침 브리핑 — 읽기 화면 (2026-11-13) ─────────────────────────────
     폰: 한 줄에 한 구역, 글자 16px 안팎, 줄 간격 넉넉히. 넓은 화면: 숫자 구역이
     나란히, 글 구역은 한 줄 길이를 46em 안으로 (길면 눈이 줄을 놓칩니다). */
  .dash-brf {{ max-width: 980px; margin: 0 0 var(--sp-4); font-family: {FONT_STACK};
              color: var(--dash-ink); }}
  .bf-hero {{ background: var(--grp-tint, var(--dash-raised));
             border-left: 4px solid var(--grp-line, var(--dash-accent));
             border-radius: var(--r-card); padding: 16px 18px 14px; margin-bottom: 10px; }}
  .bf-meta {{ font-size: var(--fs-2); color: var(--dash-ink-2); margin-bottom: 4px; }}
  .bf-hero h2 {{ font-size: var(--fs-7); font-weight: 780; letter-spacing: -0.02em;
                line-height: 1.3; margin: 0 0 8px; padding: 0; color: var(--dash-ink); }}
  .bf-lead {{ font-size: var(--fs-5); line-height: 1.65; margin: 0; max-width: 46em;
             word-break: keep-all; overflow-wrap: anywhere; }}
  .bf-stale {{ margin-top: 8px; font-size: var(--fs-3); font-weight: 650;
              color: var(--dash-badge-error); }}
  .bf-grid {{ display: grid; gap: 10px; margin-bottom: 10px;
             grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
  .bf-sec {{ background: var(--dash-surface); border: 1px solid var(--dash-divider);
            border-radius: var(--r-card); padding: 14px 16px 12px; min-width: 0; }}
  .bf-sec.bf-wide {{ grid-column: 1 / -1; }}
  .bf-sec h3 {{ font-size: var(--fs-3); font-weight: 750; letter-spacing: .02em;
               color: var(--dash-ink-2); margin: 0 0 8px; padding: 0 0 7px;
               border-bottom: 2px solid var(--grp-mid, var(--dash-divider)); }}
  .bf-kv {{ display: flex; flex-wrap: wrap; align-items: baseline;
           justify-content: space-between; gap: 2px 12px; padding: 7px 0;
           border-bottom: 1px solid var(--dash-divider); font-size: var(--fs-4); }}
  .bf-kv:last-child {{ border-bottom: none; }}
  .bf-kv > b {{ font-weight: 700; }}
  .bf-vals {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 2px 12px;
             font-variant-numeric: tabular-nums; text-align: right; }}
  .bf-note {{ flex-basis: 100%; font-size: var(--fs-3); color: var(--dash-ink-2);
             line-height: 1.5; }}
  .bf-kv-text {{ display: block; color: var(--dash-ink-2); font-size: var(--fs-3);
                line-height: 1.55; }}
  .bf-mv {{ font-weight: 700; white-space: nowrap; }}
  .bf-mv.up {{ color: var(--dash-up); }}
  .bf-mv.down {{ color: var(--dash-down); }}
  .bf-list {{ list-style: none; margin: 0; padding: 0; }}
  .bf-list li {{ position: relative; padding: 8px 0 8px 16px; font-size: var(--fs-4);
                line-height: 1.65; max-width: 46em; word-break: keep-all;
                overflow-wrap: anywhere; border-bottom: 1px solid var(--dash-divider); }}
  .bf-list li:last-child {{ border-bottom: none; }}
  .bf-list li::before {{ content: ""; position: absolute; left: 2px; top: 1.05em;
                        width: 6px; height: 6px; border-radius: var(--r-pill);
                        background: var(--grp-line, var(--dash-accent)); }}
  .bf-when {{ display: inline-block; font-weight: 750; font-variant-numeric: tabular-nums;
             background: var(--grp-tint, var(--dash-raised)); border-radius: var(--r-chip);
             padding: 0 7px; margin-right: 8px; }}
  .bf-more h4 {{ font-size: var(--fs-4); font-weight: 750; margin: 14px 0 6px; padding: 0;
                color: var(--dash-ink); }}
  .bf-more h4:first-child {{ margin-top: 0; }}
  .bf-more p, .bf-more li {{ font-size: var(--fs-4); line-height: 1.65; max-width: 46em;
                            word-break: keep-all; overflow-wrap: anywhere; }}
  .bf-more p {{ margin: 0 0 8px; color: var(--dash-ink); }}
  .bf-more ul, .bf-more ol {{ margin: 0 0 8px; padding-left: 1.3em; }}
  .bf-more li {{ margin: 0 0 7px; }}
  .bf-src {{ margin: 10px 0 0; font-size: var(--fs-3); color: var(--dash-ink-2); }}
  .bf-src summary {{ cursor: pointer; font-weight: 650; padding: 6px 0; }}
  .bf-src ol {{ margin: 4px 0 0; padding-left: 1.6em; columns: 2 220px; }}
  .bf-src li {{ margin: 0 0 4px; break-inside: avoid; }}
  .bf-foot {{ margin-top: 10px; font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  @media (max-width: 640px) {{
    .bf-hero {{ padding: 14px 14px 12px; }}
    .bf-sec {{ padding: 12px 13px 10px; }}
    .bf-grid {{ grid-template-columns: 1fr; }}
  }}
  /* ── 섹터 온도 — 흐름 판독 · 4칸 지도 (2026-11-13) ─────────────────────
     폰: 1열(주도 → 회복 → 둔화 → 침체). 넓은 화면: 2×2 를 RRG 배치로
     (위 = 이번 주 강, 오른쪽 = 3개월 강). 보라 계열 금지 — 등락색만 옅게. */
  .dash-sflow {{
    background: var(--dash-surface); border: 1px solid var(--dash-divider);
    border-radius: var(--r-card); padding: 12px 12px 10px; margin: 0 0 var(--sp-3);
  }}
  .sf-read {{ margin: 0 0 10px; padding-left: 1.1em; }}
  .sf-read li {{ font-size: var(--fs-3); line-height: 1.55; color: var(--dash-ink);
                margin-bottom: 4px; }}
  .sf-map {{ display: grid; grid-template-columns: 1fr; gap: 6px; }}
  .sf-q {{ border-radius: var(--r-chip); padding: 7px 9px 8px;
          border-left: 3px solid var(--dash-divider); background: var(--dash-raised); }}
  .sf-lead {{ border-left-color: var(--dash-up);
             background: color-mix(in srgb, var(--dash-up) 9%, var(--dash-surface)); }}
  .sf-recover {{ border-left-color: color-mix(in srgb, var(--dash-up) 45%, var(--dash-surface));
                background: color-mix(in srgb, var(--dash-up) 4%, var(--dash-surface)); }}
  .sf-fade {{ border-left-color: color-mix(in srgb, var(--dash-down) 45%, var(--dash-surface));
             background: color-mix(in srgb, var(--dash-down) 4%, var(--dash-surface)); }}
  .sf-lag {{ border-left-color: var(--dash-down);
            background: color-mix(in srgb, var(--dash-down) 9%, var(--dash-surface)); }}
  .sf-qh {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 5px; }}
  .sf-qh b {{ font-size: var(--fs-4); color: var(--dash-ink); }}
  .sf-qh span {{ font-size: var(--fs-1); color: var(--dash-ink-muted); flex: 1; }}
  .sf-qh small {{ font-size: var(--fs-2); font-weight: 700; color: var(--dash-ink-2); }}
  .sf-chips {{ display: flex; flex-wrap: wrap; gap: 5px; }}
  .sf-chip {{ display: inline-flex; align-items: baseline; gap: 5px;
             background: var(--dash-surface); border: 1px solid var(--dash-divider);
             border-radius: var(--r-chip); padding: 3px 7px; font-size: var(--fs-2); }}
  .sf-chip b {{ color: var(--dash-ink); font-weight: 700; }}
  .sf-chip em {{ font-style: normal; color: var(--dash-ink-2);
                font-variant-numeric: tabular-nums; }}
  .sf-chip i {{ font-style: normal; font-size: var(--fs-1); color: var(--dash-accent);
               font-weight: 650; }}
  .sf-none {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .sf-flat {{ margin-top: 7px; font-size: var(--fs-2); color: var(--dash-ink-muted);
             display: flex; flex-wrap: wrap; align-items: baseline; gap: 5px; }}
  .sf-flat b {{ color: var(--dash-ink-2); }}
  .sf-foot, .sf-unk {{ margin-top: 7px; font-size: var(--fs-1); color: var(--dash-ink-muted);
                      line-height: 1.5; }}
  .sf-foot i {{ font-style: normal; color: var(--dash-accent); font-weight: 650; }}
  @media (min-width: 761px) {{
    .sf-map {{ grid-template-columns: 1fr 1fr;
              grid-template-areas: "recover lead" "lag fade"; }}
    .sf-lead {{ grid-area: lead; }} .sf-recover {{ grid-area: recover; }}
    .sf-fade {{ grid-area: fade; }} .sf-lag {{ grid-area: lag; }}
  }}

  /* ── 요약 상태판 ──────────────────────────────────────────────────── */
  .dash-sgrid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 8px; margin-bottom: var(--sp-3); }}
  .dash-sgrid .dash-srow {{ margin-bottom: 0; }}
  .dash-sgrid .dash-srow.quiet, .dash-sgrid .dash-srow.unknown {{ background: transparent; }}
  .dash-sgrid .dash-srow.quiet .dash-srow-head {{ color: var(--dash-ink-2);
                                               font-weight: 550; }}
  .dash-sgrid .dash-srow.alert {{ border-left: 3px solid var(--dash-up); }}
  .dash-sgrid .dash-srow.watch {{ border-left: 3px solid var(--dash-accent); }}
  @media (max-width: 760px) {{
    .dash-sgrid {{ grid-template-columns: 1fr; }}
  }}

  /* ── 섹터 막대 ────────────────────────────────────────────────────── */
  .dash-sbars {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
                border-radius: var(--r-card); padding: 12px 14px; margin: 0 0 var(--sp-3); }}
  .dash-sbars .sb-head {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
             margin-bottom: var(--sp-2); }}
  .dash-sbars .sb-row {{ display: grid; grid-template-columns: 92px 1fr 64px; gap: 10px;
            align-items: center; padding: 3px 0; }}
  .dash-sbars .sb-name {{ font-size: var(--fs-3); color: var(--dash-ink); white-space: nowrap;
             overflow: hidden; text-overflow: ellipsis; }}
  .dash-sbars .sb-track {{ position: relative; height: 12px; }}
  .dash-sbars .sb-zero {{ position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px;
             background: var(--dash-border); }}
  .dash-sbars .sb-bar {{ position: absolute; top: 2px; bottom: 2px; border-radius: var(--r-chip); }}
  .dash-sbars .sb-bar.up {{ background: var(--dash-up); }}
  .dash-sbars .sb-bar.down {{ background: var(--dash-down); }}
  .dash-sbars .sb-bar.flat {{ background: var(--dash-ink-muted); }}
  .dash-sbars .sb-val {{ font-size: var(--fs-3); font-weight: 650; text-align: right;
            font-variant-numeric: tabular-nums; }}
  .dash-sbars .sb-val.up {{ color: var(--dash-up); }}
  .dash-sbars .sb-val.down {{ color: var(--dash-down); }}

  /* ── 통과 종목 비교표 ───────────────────────────────────────────── */
  .dash-htable-wrap {{ overflow-x: auto; margin: 0 0 var(--sp-3);
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); }}
  .dash-htable {{ width: 100%; border-collapse: collapse; font-size: var(--fs-3);
                 font-variant-numeric: tabular-nums; }}
  .dash-htable th {{ text-align: right; font-weight: 600; font-size: var(--fs-2);
    color: var(--dash-ink-muted); padding: 8px 12px; white-space: nowrap;
    border-bottom: 1px solid var(--dash-border); background: var(--dash-raised); }}
  .dash-htable td {{ text-align: right; padding: 8px 12px; white-space: nowrap;
    border-bottom: 1px solid var(--dash-divider); color: var(--dash-ink); }}
  .dash-htable tr:last-child td {{ border-bottom: none; }}
  .dash-htable th:nth-child(2), .dash-htable td.ht-name {{ text-align: left; }}
  .dash-htable td.ht-name span {{ color: var(--dash-ink-muted); margin-left: 6px;
                                  font-size: var(--fs-2); }}
  .dash-htable .ht-rank {{ text-align: center; color: var(--dash-ink-muted); width: 32px; }}

  /* ── 보유 종목 표 ─────────────────────────────────────────────────── */
  .dash-hold td.hd-name {{ text-align: left; font-weight: 650; }}
  .dash-hold td.hd-name a {{ color: var(--dash-ink); text-decoration: none; }}
  .dash-hold td.hd-name a:hover {{ text-decoration: underline; }}
  .dash-hold td.hd-name span {{ color: var(--dash-ink-muted); font-weight: 400;
                               margin-left: 6px; font-size: var(--fs-2); }}
  .dash-hold th:first-child {{ text-align: left; }}
  .dash-hold th:nth-child(2) {{ text-align: right; }}
  .dash-hold td.hd-num {{ font-size: var(--fs-4); }}
  .dash-hold td.up, .dash-hold .hd-ext .up {{ color: var(--dash-up); }}
  .dash-hold td.down, .dash-hold .hd-ext .down {{ color: var(--dash-down); }}
  .dash-hold .hd-ext {{ display: block; font-size: var(--fs-1); color: var(--dash-ink-muted); }}
  .dash-hold td.hd-sigs {{ text-align: right; }}
  .hd-sig {{ display: inline-block; font-size: var(--fs-1); font-weight: 650;
            padding: 2px 8px; border-radius: var(--r-pill); margin-left: 4px;
            border: 1px solid var(--dash-border); color: var(--dash-ink-muted); }}
  .hd-sig.now {{ border-color: var(--dash-up); color: var(--dash-up); }}
  .hd-sig.soon {{ border-color: var(--dash-accent); color: var(--dash-accent); }}

  .dash-table th.mk, .dash-table td.mk {{ text-align: center !important;
    min-width: 64px; white-space: normal; }}
  .dash-table th.mk {{ font-size: var(--fs-1); line-height: 1.3; vertical-align: bottom; }}

  /* ── 차트 조건 ────────────────────────────────────────────────────── */
  .dash-cc {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
             gap: 8px; margin: var(--sp-2) 0 var(--sp-2); }}
  .cc-cell {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
             border-radius: var(--r-inner); padding: 10px 12px; min-width: 0; }}
  .cc-name {{ font-size: var(--fs-3); font-weight: 700; color: var(--dash-ink); }}
  .cc-n {{ font-size: var(--fs-7); font-weight: 750; color: var(--dash-ink);
          font-variant-numeric: tabular-nums; line-height: 1.2; }}
  .cc-n span {{ font-size: var(--fs-2); font-weight: 500; color: var(--dash-ink-muted);
               margin-left: 4px; }}
  .cc-bar {{ height: 4px; background: var(--dash-raised); border-radius: var(--r-chip);
            margin: 4px 0 6px; overflow: hidden; }}
  .cc-bar i {{ display: block; height: 100%; background: var(--dash-accent); }}
  .cc-rule {{ font-size: var(--fs-1); color: var(--dash-ink-muted); line-height: 1.4; }}
  .cc-miss {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
             margin: 0 0 var(--sp-2); }}
  @media (max-width: 760px) {{
    .dash-cc {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
  .dash-ctable td {{ text-align: left; }}
  /* 조건이 일곱이라 칸 여백을 줄입니다 — 넓은 화면에서 가로 스크롤 없이 */
  .dash-ctable th, .dash-ctable td {{ padding-left: 8px; padding-right: 8px; }}
  .dash-ctable .ht-rank {{ width: 24px; }}
  /* 값은 한 줄, 상태 이름(아랫줄)만 필요하면 줄바꿈 */
  .dash-ctable td.ct-yes span, .dash-ctable td.ct-no span, .dash-ctable td.ct-na span {{
    white-space: normal; max-width: 96px; line-height: 1.3; }}
  .dash-ctable th {{ white-space: normal; line-height: 1.3; }}
  .dash-ctable th {{ text-align: left; }}
  .dash-ctable td span {{ display: block; font-size: var(--fs-1);
                         color: var(--dash-ink-muted); }}
  .dash-ctable td.ht-name span {{ display: inline; }}
  .dash-ctable td.ht-name span.ct-semi {{ font-weight: 600; color: var(--dash-ink); font-size: 0.85em; }}
  .dash-ctable td.ht-name span.ct-new {{ text-decoration: underline; }}
  /* 오늘 볼 종목 — 카드 (2026-11-13 12:05 "글자만 나오는데 개선") */
  .dash-picks {{ display: grid; gap: 10px; margin: 6px 0 4px;
                grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); }}
  .pk-card {{ background: var(--dash-surface); border: 1px solid var(--dash-divider);
             border-top: 3px solid var(--grp-line, var(--dash-accent));
             border-radius: var(--r-card); padding: 12px 14px 12px; min-width: 0; }}
  .pk-top {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }}
  .pk-top b {{ font-size: var(--fs-5); font-weight: 780; letter-spacing: -0.01em; }}
  .pk-n {{ color: var(--dash-ink-muted); font-size: var(--fs-2); font-weight: 700; }}
  .pk-code {{ color: var(--dash-ink-muted); font-size: var(--fs-2); }}
  .pk-tag {{ font-size: var(--fs-1); font-weight: 700; color: var(--dash-ink);
            background: var(--grp-mid, var(--dash-raised)); border-radius: var(--r-pill);
            padding: 1px 8px; }}
  .pk-price {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px;
              margin: 6px 0 8px; }}
  .pk-px {{ font-size: var(--fs-6); font-weight: 750; font-variant-numeric: tabular-nums;
           letter-spacing: -0.02em; }}
  .pk-gap {{ font-size: var(--fs-3); font-weight: 650; font-variant-numeric: tabular-nums; }}
  .pk-gap.up {{ color: var(--dash-up); }} .pk-gap.down {{ color: var(--dash-down); }}
  .pk-gap.flat {{ color: var(--dash-ink-muted); }}
  .pk-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
  .pk-chart {{ position: relative; margin: 0 0 8px; }}
  .pk-chart svg {{ display: block; width: 100%; height: 44px; }}
  .pk-chart span {{ position: absolute; right: 2px; top: -2px; font-size: var(--fs-1);
                   color: var(--dash-ink-muted); background: var(--dash-surface); padding: 0 3px; }}
  .pk-chip {{ font-size: var(--fs-2); font-weight: 650; border-radius: var(--r-pill);
             padding: 3px 10px; white-space: nowrap; color: var(--dash-ink);
             background: var(--dash-raised); }}
  .pk-chip small {{ font-weight: 500; opacity: .8; font-size: inherit; }}
  .pk-chip.good {{ background: var(--grp-mid, var(--dash-raised)); }}
  .pk-chip.mid {{ background: var(--grp-tint, var(--dash-raised)); }}
  .pk-chip.plain {{ background: transparent; border: 1px solid var(--dash-divider);
                   color: var(--dash-ink-2); }}
  .pk-chip.eps.up {{ color: var(--dash-up);
                    background: color-mix(in srgb, var(--dash-up) 10%, var(--dash-surface)); }}
  .pk-chip.eps.down {{ color: var(--dash-down);
                      background: color-mix(in srgb, var(--dash-down) 10%, var(--dash-surface)); }}
  .pk-g {{ display: grid; grid-template-columns: 6.6em minmax(0, 1fr) 2.6em;
          align-items: center; gap: 8px; padding: 3px 0; }}
  .pk-gl {{ font-size: var(--fs-2); color: var(--dash-ink-2); white-space: nowrap; }}
  .pk-g.on .pk-gl {{ color: var(--dash-ink); font-weight: 700; }}
  .pk-gl em, .pk-legend em {{ font-style: normal; font-size: var(--fs-1); font-weight: 700;
            margin-left: 5px; padding: 0 5px; border-radius: var(--r-chip);
            color: var(--dash-surface); background: var(--dash-down); }}
  .pk-legend em {{ margin-left: 0; }}
  .pk-gt {{ position: relative; height: 8px; border-radius: var(--r-pill);
           background: var(--dash-raised); }}
  .pk-gt .zone {{ position: absolute; left: 0; top: 0; bottom: 0;
                 border-radius: var(--r-pill) 0 0 var(--r-pill);
                 background: color-mix(in srgb, var(--dash-down) 26%, var(--dash-surface)); }}
  .pk-gt .dot {{ position: absolute; top: 50%; width: 12px; height: 12px;
                margin: -6px 0 0 -6px; border-radius: var(--r-pill);
                background: var(--dash-ink); border: 2px solid var(--dash-surface); }}
  .pk-gv {{ font-size: var(--fs-2); font-weight: 650; text-align: right;
           font-variant-numeric: tabular-nums; }}
  .pk-legend {{ font-size: var(--fs-2); color: var(--dash-ink-muted); margin: 2px 0 var(--sp-2); }}
  .dash-ctable .ct-mark {{ display: inline-block; width: 1.1em;
                          color: var(--dash-ink-muted); font-weight: 400; }}
  .dash-ctable td.ct-yes {{
    background: color-mix(in srgb, var(--dash-accent) 9%, var(--dash-surface));
    font-weight: 650; }}
  .dash-ctable td.ct-yes .ct-mark {{ color: var(--dash-accent); }}
  .dash-ctable td.ct-no {{ color: var(--dash-ink-2); }}
  .dash-ctable td.ct-na {{ color: var(--dash-ink-muted); }}
  .dash-ctable td.ct-met {{ font-weight: 700; white-space: nowrap; }}
  .ct-star {{ font-style: normal; color: var(--dash-accent); margin-right: 4px; }}
  .ct-dots {{ display: inline-flex !important; gap: 3px; margin-right: 7px;
             vertical-align: middle; }}
  .ct-dots i {{ width: 7px; height: 7px; border-radius: 50%;
               border: 1px solid var(--dash-ink-muted); display: block; }}
  .ct-dots i.on {{ background: var(--dash-accent); border-color: var(--dash-accent); }}

  .dash-cdetail {{ padding: 2px 0 4px; }}
  .dash-cloud {{ width: 100%; height: 170px; display: block;
                background: var(--dash-surface); border: 1px solid var(--dash-divider);
                border-radius: var(--r-inner); }}
  .dash-cloud .cl-bull {{ fill: color-mix(in srgb, var(--dash-up) 22%, transparent); }}
  .dash-cloud .cl-bear {{ fill: color-mix(in srgb, var(--dash-down) 22%, transparent); }}
  .dash-cloud .cl-price {{ fill: none; stroke: var(--dash-ink); stroke-width: 1.6;
                          vector-effect: non-scaling-stroke; }}
  .dash-cloud .cl-today {{ stroke: var(--dash-ink-muted); stroke-width: 1;
    stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }}
  .dash-cloud-wrap {{ position: relative; }}
  .dash-cloud-wrap .cl-lab {{ position: absolute; right: 6px;
    transform: translateY(-50%); font-size: var(--fs-1); color: var(--dash-ink);
    font-weight: 650; font-variant-numeric: tabular-nums;
    background: var(--dash-surface); padding: 0 3px; }}
  .cd-legend {{ display: flex; gap: 14px; flex-wrap: wrap; font-size: var(--fs-1);
               color: var(--dash-ink-muted); margin: 5px 0 var(--sp-2); }}
  .cd-legend span::before {{ content: ""; display: inline-block; width: 10px;
    height: 10px; margin-right: 5px; vertical-align: -1px; border-radius: var(--r-chip); }}
  .cd-legend .lg-price::before {{ height: 2px; vertical-align: 3px; background: var(--dash-ink); }}
  .cd-legend .lg-bull::before {{ background: color-mix(in srgb, var(--dash-up) 35%, transparent); }}
  .cd-legend .lg-bear::before {{ background: color-mix(in srgb, var(--dash-down) 35%, transparent); }}
  .cd-legend span:last-child::before {{ display: none; }}
  .cd-row {{ display: grid; grid-template-columns: 96px 150px 1fr; gap: 4px 10px;
            padding: 7px 0; border-top: 1px solid var(--dash-divider);
            font-size: var(--fs-3); align-items: baseline; }}
  .cd-name {{ font-weight: 700; color: var(--dash-ink); }}
  .cd-verdict {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .cd-yes .cd-verdict {{ color: var(--dash-accent); font-weight: 700; }}
  .cd-val {{ color: var(--dash-ink); font-variant-numeric: tabular-nums; }}
  .cd-rule {{ grid-column: 3; font-size: var(--fs-1); color: var(--dash-ink-muted); }}
  @media (max-width: 640px) {{
    .cd-row {{ grid-template-columns: 84px 1fr; }}
    .cd-val, .cd-rule {{ grid-column: 1 / -1; }}
  }}

  /* ── 매크로: 시세 표 · 임계값 목록 · 지표 표 ───────────────────────── */
  .dash-qt td.qt-err {{ text-align: right; color: var(--dash-ink-muted);
                       font-size: var(--fs-2); white-space: normal; }}
  .dash-qt td.flat {{ color: var(--dash-ink-muted); }}

  .dash-tlist {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
                border-radius: var(--r-card); margin: 0 0 var(--sp-2); overflow: hidden; }}
  .tl-row {{ display: grid; grid-template-columns: 70px 1fr auto; gap: 12px;
            align-items: start; padding: 10px 14px;
            border-top: 1px solid var(--dash-divider);
            border-left: 3px solid transparent; }}
  .tl-row:first-child {{ border-top: none; }}
  .tl-row.now {{ border-left-color: var(--dash-up); }}
  .tl-row .dash-sig-chip {{ justify-self: start; white-space: nowrap; }}
  .tl-title {{ font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink);
              line-height: 1.4; }}
  .tl-detail {{ font-size: var(--fs-2); color: var(--dash-ink-2); margin-top: 1px; }}
  .tl-tag {{ font-size: var(--fs-1); color: var(--dash-ink-muted); white-space: nowrap;
            padding-top: 3px; }}
  @media (max-width: 640px) {{
    .tl-row {{ grid-template-columns: 66px 1fr; gap: 8px; }}
    .tl-tag {{ grid-column: 2; padding-top: 0; }}
  }}

  .dash-mt th, .dash-mt td {{ text-align: left; }}
  .dash-mt th:nth-child(2), .dash-mt td.mt-val,
  .dash-mt th:nth-child(5), .dash-mt td.mt-obs {{ text-align: right; }}
  .dash-mt tr.mt-group td {{ background: var(--dash-raised);
    padding: 7px 12px; border-bottom: 1px solid var(--dash-border);
    font-size: var(--fs-3); color: var(--dash-ink); white-space: normal; }}
  .dash-mt tr.mt-group td span {{ color: var(--dash-ink-muted); font-size: var(--fs-2);
                                 margin-left: 8px; }}
  .dash-mt td.mt-name b {{ font-weight: 650; }}
  .dash-mt td.mt-name span {{ display: block; font-size: var(--fs-1);
                             color: var(--dash-ink-muted); }}
  .dash-mt td.mt-val {{ font-size: var(--fs-5); font-weight: 700; }}
  .dash-mt td.mt-delta {{ color: var(--dash-ink-2); }}
  .dash-mt td.mt-spark svg {{ display: block; }}
  .dash-mt td.mt-obs {{ color: var(--dash-ink-2); font-size: var(--fs-2); }}
  .dash-mt td.mt-obs span {{ display: block; color: var(--dash-ink-muted);
                            font-size: var(--fs-1); }}
  .dash-mt td.mt-obs span.late {{ color: var(--dash-badge-error); font-weight: 650; }}
  /* 반도체 리포트 — 묶음 요약 + 리포트 카드 */
  .dash-digest {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-left: 3px solid var(--dash-accent); border-radius: var(--r-card);
    padding: 11px 14px; margin: 4px 0 10px; }}
  .dash-digest .dg-head {{ font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink); }}
  .dash-digest .dg-line {{ font-size: var(--fs-3); color: var(--dash-ink-2); margin-top: 5px; }}
  .dash-digest .dg-words {{ display: flex; flex-wrap: wrap; gap: 5px 6px;
    align-items: center; margin-top: 8px; }}
  .dash-digest .dg-cap {{ font-size: var(--fs-2); color: var(--dash-ink-muted); margin-right: 2px; }}
  .dash-digest .dg-chip {{ font-size: var(--fs-2); color: var(--dash-ink);
    background: var(--dash-raised); border-radius: var(--r-pill); padding: 2px 9px;
    white-space: nowrap; }}
  .dash-digest .dg-chip b {{ color: var(--dash-accent); font-weight: 700; }}
  /* 캔들 차트 + 지표 패널 — SVG 는 가로로 늘어나고 글자는 HTML 로 얹습니다 */
  .dash-kchart {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 6px 4px 6px 8px; margin: 4px 0 10px;
    font-variant-numeric: tabular-nums; }}
  .dash-kchart .kc-panel {{ border-bottom: 1px solid var(--dash-divider); padding-top: 3px; }}
  .dash-kchart .kc-row {{ display: flex; }}
  .dash-kchart .kc-plot {{ position: relative; flex: 1 1 auto; min-width: 0; overflow: hidden; }}
  .dash-kchart .kc-plot svg {{ position: absolute; inset: 0; width: 100%; height: 100%;
    display: block; }}
  .dash-kchart .kc-axis {{ position: relative; flex: 0 0 54px; }}
  .dash-kchart .kc-axis span {{ position: absolute; left: 4px; transform: translateY(-50%);
    font-size: var(--fs-1); color: var(--dash-ink-muted); white-space: nowrap; }}
  .dash-kchart .kc-title {{ padding: 0 4px;
    display: flex; flex-wrap: wrap; gap: 1px 10px; align-items: baseline;
    font-size: var(--fs-1); color: var(--dash-ink-2); line-height: 1.4; }}
  .dash-kchart .kc-title span {{ white-space: nowrap; }}
  .dash-kchart .kc-title b {{ color: var(--dash-ink); font-weight: 700; }}
  .dash-kchart .kc-title i {{ display: inline-block; width: 12px; height: 0;
    border-top: 2px solid var(--dash-ink); vertical-align: middle; margin-right: 3px; }}
  .dash-kchart .kc-title em {{ font-style: normal; font-weight: 700; color: var(--dash-ink);
    border: 1px solid var(--dash-ink-2); border-radius: var(--r-chip); padding: 0 5px;
    background: var(--dash-surface); white-space: nowrap; }}
  .dash-kchart svg line, .dash-kchart svg polyline, .dash-kchart svg rect {{
    vector-effect: non-scaling-stroke; }}
  .dash-kchart svg polyline {{ fill: none; stroke-linejoin: round; }}
  .dash-kchart .kc-up line {{ stroke: var(--dash-up); stroke-width: 1; }}
  .dash-kchart .kc-up rect, .dash-kchart rect.kc-up {{ fill: var(--dash-up); }}
  .dash-kchart .kc-dn line {{ stroke: var(--dash-down); stroke-width: 1; }}
  .dash-kchart .kc-dn rect, .dash-kchart rect.kc-dn {{ fill: var(--dash-down); }}
  .dash-kchart rect.kc-vol {{ opacity: .55; }}
  .dash-kchart .kc-bull {{ fill: color-mix(in srgb, var(--dash-up) 14%, transparent); }}
  .dash-kchart .kc-bear {{ fill: color-mix(in srgb, var(--dash-down) 14%, transparent); }}
  .dash-kchart .kc-sa {{ stroke: color-mix(in srgb, var(--dash-up) 55%, transparent); stroke-width: 1; }}
  .dash-kchart .kc-sb {{ stroke: color-mix(in srgb, var(--dash-down) 55%, transparent); stroke-width: 1; }}
  .dash-kchart polyline.kc-m1 {{ stroke: #b7791f; stroke-width: 1.5; }}
  .dash-kchart polyline.kc-m2 {{ stroke: #2f855a; stroke-width: 1.5; }}
  .dash-kchart polyline.kc-m3 {{ stroke: #6b46c1; stroke-width: 1.5; }}
  .dash-kchart polyline.kc-bb {{ stroke: var(--dash-ink-muted); stroke-width: 1;
    stroke-dasharray: 3 3; }}
  .dash-kchart polyline.kc-l1 {{ stroke: var(--dash-ink); stroke-width: 1.6; }}
  .dash-kchart polyline.kc-l2 {{ stroke: #b7791f; stroke-width: 1.2; }}
  .dash-kchart polyline.kc-l3 {{ stroke: var(--dash-ink-muted); stroke-width: 1.2;
    stroke-dasharray: 4 3; }}
  .dash-kchart line.kc-ref {{ stroke: var(--dash-ink-2); stroke-width: 1; stroke-dasharray: 5 4;
    opacity: .7; }}
  .dash-kchart line.kc-zero {{ stroke: var(--dash-divider); stroke-width: 1; }}
  .dash-kchart line.kc-today {{ stroke: var(--dash-ink-muted); stroke-width: 1;
    stroke-dasharray: 2 3; }}
  .dash-kchart rect.kc-fwd {{ fill: var(--dash-raised); opacity: .55; }}
  .dash-kchart rect.kc-hist.pos {{ fill: var(--dash-ink-2); opacity: .55; }}
  .dash-kchart rect.kc-hist.neg {{ fill: var(--dash-ink-muted); opacity: .45; }}
  .dash-kchart .kc-title i.kc-m1 {{ border-color: #b7791f; }}
  .dash-kchart .kc-title i.kc-m2 {{ border-color: #2f855a; }}
  .dash-kchart .kc-title i.kc-m3 {{ border-color: #6b46c1; }}
  .dash-kchart .kc-title i.kc-l2 {{ border-color: #b7791f; }}
  .dash-kchart .kc-title i.kc-l3, .dash-kchart .kc-title i.kc-bb {{
    border-top-style: dashed; border-color: var(--dash-ink-muted); }}
  .dash-kchart .kc-title i.kc-cloud {{ height: 8px; border: 0; vertical-align: -1px;
    background: linear-gradient(90deg, color-mix(in srgb, var(--dash-up) 30%, transparent) 50%,
      color-mix(in srgb, var(--dash-down) 30%, transparent) 50%); }}
  .dash-kchart .kc-dates {{ display: flex; height: 18px; padding-right: 54px; }}
  .dash-kchart .kc-dates span {{ position: absolute; top: 2px; transform: translateX(-50%);
    font-size: var(--fs-1); color: var(--dash-ink-muted); white-space: nowrap; }}
  .dash-kchart .kc-dates span.now {{ color: var(--dash-ink); font-weight: 700; }}
  .dash-kchart .kc-foot {{ font-size: var(--fs-1); color: var(--dash-ink-muted);
    padding: 3px 4px 0; line-height: 1.4; }}
  @media (max-width: 640px) {{
    .dash-kchart {{ padding-left: 4px; }}
    .dash-kchart .kc-axis {{ flex-basis: 46px; }}
    .dash-kchart .kc-dates {{ padding-right: 46px; }}
    .dash-kchart .kc-title {{ gap: 0 7px; }}
  }}
  /* 종목 발굴 — 한눈표의 종목 이름 · 업종, 업종별 통과 칩 */
  table.dash-sctable .sc-name {{ display: block; font-size: var(--fs-1); font-weight: 400;
    color: var(--dash-ink-muted); max-width: 14em; overflow: hidden; text-overflow: ellipsis; }}
  table.dash-sctable .sc-sub {{ display: block; font-size: var(--fs-1); font-weight: 400;
    color: var(--dash-ink-muted); white-space: nowrap; }}
  table.dash-sctable .sc-rk {{ font-style: normal; font-weight: 500; color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums; margin-right: 6px; }}
  table.dash-sctable td.sc-x {{ text-align: left; white-space: nowrap;
    font-variant-numeric: tabular-nums; }}
  /* 누를 수 있는 단계 칸 · 사분면의 종목 이름 */
  .dash-funnel a.fn-link {{ text-decoration: none !important; color: inherit !important;
    cursor: pointer; border-color: var(--dash-accent) !important; }}
  .dash-funnel a.fn-link .fn-l {{ text-decoration: underline; text-underline-offset: 3px; }}
  .dash-funnel a.fn-link.fn-on {{ background: var(--dash-raised) !important;
    box-shadow: inset 0 -3px 0 var(--dash-accent); }}
  .dash-qmap a.qk {{ color: var(--dash-accent) !important; font-weight: 600;
    text-decoration: underline; text-underline-offset: 3px; padding: 2px 0; display: inline-block; }}
  /* 사분면 지도 — 2×2 칸 (폰에서도 두 칸씩) */
  .dash-qmap {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 4px 0 8px; }}
  .dash-qmap .qc {{ border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); padding: 8px 10px; min-width: 0; }}
  .dash-qmap .qc.wide {{ grid-column: 1 / -1; }}
  .dash-qmap .qc.q1 {{ border-color: var(--dash-accent); }}
  .dash-qmap .qt {{ display: block; font-size: var(--fs-2); color: var(--dash-ink-muted);
    line-height: 1.35; }}
  .dash-qmap .qn {{ display: block; font-size: var(--fs-5); font-weight: 700;
    color: var(--dash-ink); font-variant-numeric: tabular-nums; }}
  .dash-qmap .qv {{ display: block; font-size: var(--fs-3); color: var(--dash-ink-2);
    line-height: 1.45; overflow-wrap: anywhere; }}
  /* 긴 설명 — 두 줄만 보이고 누르면 펼쳐집니다 (components.clamp) */
  details.dash-clamp > summary {{ list-style: none; cursor: pointer; }}
  details.dash-clamp > summary::-webkit-details-marker {{ display: none; }}
  details.dash-clamp:not([open]) > summary .t {{ display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }}
  details.dash-clamp.one:not([open]) > summary .t {{ -webkit-line-clamp: 1; }}
  details.dash-clamp > summary::after {{ content: "더 보기"; font-size: var(--fs-1);
    font-weight: 600; color: var(--dash-accent); }}
  details.dash-clamp[open] > summary::after {{ content: "접기"; }}
  details.dash-clamp.one > summary::after {{ content: "▾"; }}
  details.dash-clamp.one[open] > summary::after {{ content: "▴"; }}
  /* '자세히' 로 접어 두는 칸 */
  details.dash-more {{ border-top: 1px solid var(--dash-divider); margin-top: 6px; }}
  details.dash-more > summary {{ cursor: pointer; padding: 8px 0 6px; font-size: var(--fs-3);
    font-weight: 600; color: var(--dash-ink-2); }}
  details.dash-more[open] > summary {{ color: var(--dash-ink); }}
  .dash-more-body {{ padding: 2px 0 6px; }}
  .dash-verdict-tkr {{ font-size: var(--fs-5); font-weight: 700; color: var(--dash-ink);
    margin-bottom: 2px; }}
  .dash-verdict-tkr span {{ font-size: var(--fs-2); font-weight: 500;
    color: var(--dash-ink-muted); margin-left: 7px; }}
  /* 판단 카드 맨 위 — 품질 · 가격 판정과 근거 */
  .dash-vhead {{ display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: baseline;
    margin: 4px 0 6px; }}
  .dash-vhead .vc {{ border: 1px solid var(--dash-border); border-radius: var(--r-pill);
    padding: 0 9px; font-size: var(--fs-2); font-weight: 600; color: var(--dash-ink);
    background: var(--dash-surface); white-space: nowrap; }}
  .dash-vhead .vc.p-light {{ border-color: var(--dash-accent); color: var(--dash-accent); }}
  .dash-vhead .vc.p-na {{ color: var(--dash-ink-muted); font-weight: 500; }}
  .dash-vhead .vc.ve.e-up {{ border-color: var(--dash-up); color: var(--dash-up); }}
  .dash-vhead .vc.ve.e-down {{ border-color: var(--dash-down); color: var(--dash-down); }}
  .dash-vhead .vr {{ flex-basis: 100%; font-size: var(--fs-3); color: var(--dash-ink);
    font-variant-numeric: tabular-nums; line-height: 1.45; }}
  .dash-vhead .vr.vm {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  /* '걸린 기준' 한 줄은 좁은 화면 전용 — 넓은 화면은 기준 9칸을 그대로 봅니다 */
  table.dash-sctable .sc-miss {{ display: none; }}
  table.dash-sctable td.sc-sect {{ text-align: left; font-size: var(--fs-2);
    color: var(--dash-ink-2); }}
  table.dash-sctable .ct-star {{ font-style: normal; color: var(--dash-accent); margin-right: 3px; }}
  .dash-sectpass {{ display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: baseline;
    font-size: var(--fs-2); color: var(--dash-ink-2); margin: 2px 0 8px; }}
  .dash-sectpass em {{ font-style: normal; font-weight: 700; color: var(--dash-ink);
    margin-right: 2px; }}
  .dash-sectpass span {{ border: 1px solid var(--dash-border); border-radius: var(--r-pill);
    background: var(--dash-surface); padding: 0 8px; white-space: nowrap;
    font-variant-numeric: tabular-nums; }}
  .dash-sectpass b {{ font-weight: 600; color: var(--dash-ink); }}
  /* 기호 풀이 · 분류 건수 — 설명 문구를 꺼도 남는 한 줄 */
  .dash-legend {{ font-size: var(--fs-2); color: var(--dash-ink-2); line-height: 1.5;
    margin: 2px 0 6px; }}
  .dash-legend b {{ color: var(--dash-ink); }}
  /* 차트 조건 — 종목의 쪽 (과매도 / 과매수 / 엇갈림) */
  .dash-ctable td.ct-side {{ text-align: center; white-space: nowrap; }}
  .dash-ctable .ct-sd {{ display: inline-block; font-size: var(--fs-2); font-weight: 700;
    color: var(--dash-ink); border: 1.5px solid var(--dash-ink-2);
    border-radius: var(--r-chip); padding: 0 6px; line-height: 1.5; }}
  .dash-ctable .ct-sd.ob {{ background: var(--dash-ink); color: var(--dash-surface);
    border-color: var(--dash-ink); }}
  .dash-ctable .ct-sd.mixed {{ border-style: dashed; font-weight: 600;
    color: var(--dash-ink-2); }}
  .dash-ctable .ct-sd.none {{ border: 0; color: var(--dash-ink-muted); font-weight: 400; }}
  .dash-ctable .ct-sd i {{ font-style: normal; font-weight: 500; margin-left: 4px;
    font-size: var(--fs-1); opacity: .8; }}
  /* 기준표 — 이름 · 통과 조건(숫자) · 출처 */
  .dash-criteria {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 10px 13px; margin: 4px 0 10px; }}
  .dash-criteria .cr-title {{ font-size: var(--fs-4); font-weight: 700; color: var(--dash-ink); }}
  .dash-criteria .cr-intro {{ font-size: var(--fs-3); color: var(--dash-ink-2);
    line-height: 1.5; margin: 3px 0 7px; max-width: 92ch; }}
  .dash-criteria table.cr-table {{ width: 100%; border-collapse: collapse;
    font-size: var(--fs-3); font-variant-numeric: tabular-nums; }}
  .dash-criteria .cr-table th {{ text-align: left; font-size: var(--fs-1); font-weight: 650;
    color: var(--dash-ink-muted); padding: 2px 8px 3px 0;
    border-bottom: 1px solid var(--dash-border); }}
  .dash-criteria .cr-table td {{ padding: 4px 8px 4px 0; vertical-align: top;
    border-bottom: 1px solid var(--dash-divider); line-height: 1.45; }}
  .dash-criteria .cr-table tr:last-child td {{ border-bottom: 0; }}
  .dash-criteria .cr-n {{ color: var(--dash-ink-muted); width: 1.4em; }}
  .dash-criteria .cr-name {{ white-space: nowrap; color: var(--dash-ink); width: 1%; }}
  .dash-criteria .cr-rule {{ color: var(--dash-ink); }}
  .dash-criteria .cr-src {{ display: inline-block; margin-left: 6px; font-size: var(--fs-1);
    color: var(--dash-ink-muted); border: 1px solid var(--dash-border);
    border-radius: var(--r-chip); padding: 0 5px; white-space: nowrap; }}
  .dash-criteria .cr-foot {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
    line-height: 1.5; margin-top: 7px; max-width: 100ch; }}
  /* 좁은 화면 — 이름 칸이 조건 칸을 밀어내지 않게 위아래로 쌓습니다 */
  @media (max-width: 640px) {{
    .dash-criteria table.cr-table thead {{ display: none; }}
    .dash-criteria .cr-table tr {{ display: block; padding: 5px 0;
      border-bottom: 1px solid var(--dash-divider); }}
    .dash-criteria .cr-table tr:last-child {{ border-bottom: 0; }}
    .dash-criteria .cr-table td {{ display: block; border: 0 !important; padding: 0;
      width: auto; }}
    .dash-criteria .cr-table td.cr-n {{ display: none; }}
    .dash-criteria .cr-name {{ white-space: normal; }}
    .dash-terms b {{ display: block; min-width: 0; }}
  }}
  .dash-terms {{ font-size: var(--fs-2); color: var(--dash-ink-2); line-height: 1.5;
    display: grid; gap: 2px; margin: 2px 0 6px; }}
  .dash-terms b {{ display: inline-block; min-width: 7.5em; color: var(--dash-ink); }}
  .dash-rp {{ display: grid; gap: 8px; margin: 4px 0 12px; }}
  .dash-rp .rp-card {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 10px 13px; }}
  .dash-rp .rp-who {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums; }}
  .dash-rp .rp-pdf {{ margin-left: 6px; font-size: var(--fs-1); font-weight: 650;
    color: var(--dash-accent); text-decoration: none;
    border: 1px solid var(--dash-accent); border-radius: var(--r-chip); padding: 0 5px; }}
  .dash-rp .rp-title {{ font-size: var(--fs-4); font-weight: 650; line-height: 1.4;
    margin-top: 3px; }}
  .dash-rp .rp-body {{ font-size: var(--fs-3); color: var(--dash-ink-2); line-height: 1.55;
    margin-top: 5px; }}
  .dash-rp .rp-ai {{ margin-top: 7px; padding: 8px 10px; border-radius: var(--r-chip);
    background: var(--dash-raised); font-size: var(--fs-3); line-height: 1.55;
    color: var(--dash-ink); }}
  .dash-rp .rp-ai .ai-tag {{ display: inline-block; font-size: var(--fs-1); font-weight: 700;
    color: var(--dash-accent); border: 1px solid var(--dash-accent);
    border-radius: var(--r-chip); padding: 0 5px; margin-bottom: 2px; }}
  .dash-rp .rp-ai .ai-h {{ font-weight: 700; font-size: var(--fs-2);
    color: var(--dash-ink-2); margin-top: 6px; }}
  .dash-rp .rp-ai ul {{ margin: 2px 0 0; padding-left: 17px; }}
  .dash-rp .rp-ai li {{ margin: 1px 0; }}
  .dash-rp .rp-meta {{ font-size: var(--fs-2); color: var(--dash-ink-2); margin-top: 7px;
    padding-top: 6px; border-top: 1px dashed var(--dash-divider); }}
  .dash-rp .rp-src {{ font-size: var(--fs-1); color: var(--dash-ink-muted);
    border: 1px solid var(--dash-border); border-radius: var(--r-chip);
    padding: 0 5px; margin-right: 6px; }}
  /* 받은 시각 — 화면마다 맨 위 한 줄 (좁으면 여러 줄로 넘어갑니다) */
  .dash-times {{ display: flex; flex-wrap: wrap; align-items: baseline;
    gap: 3px 12px; margin: 0 0 10px; font-size: var(--fs-1);
    color: var(--dash-ink-muted); font-variant-numeric: tabular-nums; }}
  .dash-times b {{ color: var(--dash-ink-2); font-weight: 650; }}
  .dash-times span {{ white-space: nowrap; }}
  .dash-times span.old {{ color: var(--dash-ink-2); font-weight: 600; }}
  .dash-times span.old i {{ font-style: normal; font-weight: 400; }}
  .dash-mt td.mt-val i.mt-live {{ display: block; font-style: normal;
    font-size: var(--fs-2); font-weight: 600; color: var(--dash-accent); }}
  .dash-mt tr.mt-hit td:first-child {{ box-shadow: inset 3px 0 0 var(--dash-accent); }}
  .mt-flag, .mt-unv {{ font-style: normal; font-size: var(--fs-1); font-weight: 650;
    margin-left: 7px; padding: 1px 7px; border-radius: var(--r-pill);
    border: 1px solid var(--dash-accent); color: var(--dash-accent); }}
  .mt-unv {{ border-color: var(--dash-border); color: var(--dash-ink-muted); }}
  .dash-mt tr.mt-err td {{ color: var(--dash-ink-muted); white-space: normal; }}
  .dash-mt tr.mt-why td {{ white-space: normal; font-size: var(--fs-2);
    color: var(--dash-ink-2); line-height: 1.55; padding-top: 0;
    border-bottom: 1px solid var(--dash-divider); }}

  /* 심리 두 칸 (프리뷰용 — 앱은 st.columns 가 같은 일을 합니다) */
  .dash-two {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 16px; align-items: start; }}
  @media (max-width: 900px) {{ .dash-two {{ grid-template-columns: 1fr; }} }}

  /* ── 전일 장 브리핑 ───────────────────────────────────────────────── */
  .dash-db {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
             border-radius: var(--r-card); padding: 12px 14px; margin: 0 0 var(--sp-3); }}
  .db-head {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
             margin-bottom: var(--sp-2); }}
  .db-head b {{ font-size: var(--fs-5); color: var(--dash-ink); }}
  .db-head span {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .db-head .db-live {{ color: var(--dash-accent); font-weight: 650; }}
  .db-cells {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
              gap: 0; border: 1px solid var(--dash-divider); border-radius: var(--r-inner);
              margin-bottom: var(--sp-2); overflow: hidden; }}
  .db-cell {{ padding: 8px 12px; border-left: 1px solid var(--dash-divider); }}
  .db-cell:first-child {{ border-left: none; }}
  .db-l {{ font-size: var(--fs-1); color: var(--dash-ink-muted); }}
  .db-v {{ font-size: var(--fs-5); font-weight: 750; color: var(--dash-ink);
          font-variant-numeric: tabular-nums; }}
  .db-c {{ font-size: var(--fs-3); font-weight: 650; font-variant-numeric: tabular-nums; }}
  .db-c.up {{ color: var(--dash-up); }} .db-c.down {{ color: var(--dash-down); }}
  .db-c.flat {{ color: var(--dash-ink-muted); }}
  .db-line {{ display: grid; grid-template-columns: 78px 1fr; gap: 10px;
             padding: 5px 0; font-size: var(--fs-3); color: var(--dash-ink);
             line-height: 1.55; border-top: 1px solid var(--dash-divider); }}
  .db-line span {{ color: var(--dash-ink-muted); font-size: var(--fs-2); }}
  .db-miss, .db-err {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
                      margin-top: var(--sp-1); }}
  .db-rep {{ border-top: 1px solid var(--dash-divider); margin-top: var(--sp-2);
            padding-top: var(--sp-2); }}
  .db-rep-h {{ font-size: var(--fs-2); font-weight: 700; color: var(--dash-ink-2); }}
  .db-rep ul {{ margin: 4px 0 0; padding-left: 1.2em; font-size: var(--fs-3); }}
  .db-rep li {{ margin: 3px 0; }}
  .db-rep li span {{ font-size: var(--fs-1); color: var(--dash-ink-muted); }}

  /* ── 산업 리포트 ──────────────────────────────────────────────────── */
  .dash-rc {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
             border-radius: var(--r-card); padding: 10px 14px; margin: 0 0 var(--sp-3); }}
  .rc-row {{ display: grid; grid-template-columns: 110px 1fr 34px; gap: 10px;
            align-items: center; padding: 3px 0; }}
  .rc-name {{ font-size: var(--fs-3); color: var(--dash-ink); white-space: nowrap;
             overflow: hidden; text-overflow: ellipsis; }}
  .rc-track {{ height: 10px; background: var(--dash-raised); border-radius: var(--r-chip);
              overflow: hidden; }}
  .rc-track i {{ display: block; height: 100%; background: var(--dash-accent); }}
  .rc-n {{ font-size: var(--fs-3); font-weight: 700; text-align: right;
          font-variant-numeric: tabular-nums; }}
  .dash-rt th, .dash-rt td {{ text-align: left; }}
  .dash-rt td.rt-title {{ white-space: normal; min-width: 220px; line-height: 1.45; }}
  .dash-rt td.rt-date, .dash-rt td.rt-broker, .dash-rt td.rt-cat {{
    color: var(--dash-ink-2); font-size: var(--fs-2); }}
  .rt-pdf {{ font-size: var(--fs-1); color: var(--dash-ink-muted);
            border: 1px solid var(--dash-border); border-radius: var(--r-chip);
            padding: 0 4px; margin-left: 4px; }}

  /* ── 보유 평가 ────────────────────────────────────────────────────── */
  .dash-pf {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
             gap: 8px; margin: 0 0 var(--sp-2); }}
  .pf-kpi {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
            border-radius: var(--r-inner); padding: 10px 14px; }}
  .pf-l {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .pf-v {{ font-size: var(--fs-7); font-weight: 750; color: var(--dash-ink);
          font-variant-numeric: tabular-nums; }}
  .pf-s {{ font-size: var(--fs-2); color: var(--dash-ink-2); font-variant-numeric: tabular-nums; }}
  .pf-v.up, .pf-s.up, .pf-sub.up {{ color: var(--dash-up); }}
  .pf-v.down, .pf-s.down, .pf-sub.down {{ color: var(--dash-down); }}
  .pf-sub {{ display: block; font-size: var(--fs-1); }}
  .dash-pft td.pf-w {{ min-width: 110px; position: relative; text-align: right; }}
  .dash-pft td.pf-w i {{ position: absolute; left: 12px; top: 50%; height: 8px;
    margin-top: -4px; max-width: calc(100% - 64px); background: var(--dash-accent);
    border-radius: var(--r-chip); opacity: .75; }}
  .dash-pft td.pf-w span {{ font-variant-numeric: tabular-nums; }}
  .dash-hold td.hd-chart {{ font-size: var(--fs-2); color: var(--dash-ink-2);
    white-space: normal; min-width: 160px; line-height: 1.45; text-align: left; }}

  /* ── 주요 일정 ────────────────────────────────────────────────────── */
  .dash-cal {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
              border-radius: var(--r-card); margin: 0 0 var(--sp-3); overflow: hidden; }}
  .cal-day {{ display: grid; grid-template-columns: 78px 1fr; gap: 10px;
             padding: 9px 14px; border-top: 1px solid var(--dash-divider); }}
  .cal-day:first-child {{ border-top: none; }}
  .cal-date b {{ font-size: var(--fs-5); color: var(--dash-ink); margin-right: 4px; }}
  .cal-date span {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .cal-date em {{ display: block; font-style: normal; font-size: var(--fs-1);
                 color: var(--dash-ink-muted); }}
  .cal-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px;
             padding: 2px 0; font-size: var(--fs-3); }}
  .cal-row.cal-other {{ opacity: .55; }}
  .cal-row.cal-imp .cal-t, .cal-c.cal-imp .cal-t {{ font-weight: 750; }}
  .cal-t {{ color: var(--dash-ink); }}
  .cal-t i {{ font-style: normal; font-size: var(--fs-1); color: var(--dash-ink-muted);
             border: 1px solid var(--dash-border); border-radius: var(--r-chip);
             padding: 0 4px; }}
  .cal-n {{ font-size: var(--fs-2); color: var(--dash-ink-muted); }}
  .cal-mk {{ font-size: var(--fs-1); font-weight: 700; padding: 1px 6px;
            border-radius: var(--r-pill); border: 1px solid var(--dash-border);
            color: var(--dash-ink-2); white-space: nowrap; }}
  .cal-k {{ font-size: var(--fs-1); color: var(--dash-ink-muted); white-space: nowrap;
           min-width: 44px; }}
  .cal-k.policy {{ color: var(--dash-accent); font-weight: 700; }}
  .dash-calc {{ background: var(--dash-surface); border: 1px solid var(--dash-border);
               border-radius: var(--r-card); padding: 6px 14px; margin: 0 0 var(--sp-3); }}
  .cal-c {{ display: grid; grid-template-columns: 52px 44px 1fr auto; gap: 8px;
           align-items: baseline; padding: 5px 0; font-size: var(--fs-3);
           border-top: 1px solid var(--dash-divider); }}
  .cal-c:first-child {{ border-top: none; }}
  .cal-d {{ font-weight: 750; color: var(--dash-accent); font-variant-numeric: tabular-nums; }}
  @media (max-width: 640px) {{
    .cal-c {{ grid-template-columns: 48px 40px 1fr; }}
    .cal-c .cal-n {{ grid-column: 3; }}
    .cal-day {{ grid-template-columns: 58px 1fr; }}
  }}

  /* ── 걸러진 단계 ──────────────────────────────────────────────────── */
  .dash-funnel {{ margin: var(--sp-2) 0 var(--sp-4); }}
  .fn-title {{ font-size: var(--fs-2); color: var(--dash-ink-muted);
              margin-bottom: var(--sp-1); }}
  .fn-row {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 4px; }}
  .fn-step {{
    flex: 1 1 88px; min-width: 84px;
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-inner); padding: 8px 10px;
  }}
  .fn-n {{ font-size: var(--fs-7); font-weight: 750; line-height: 1.1;
          font-variant-numeric: tabular-nums; color: var(--dash-ink); }}
  .fn-l {{ font-size: var(--fs-2); color: var(--dash-ink-2); margin-top: 2px; }}
  .fn-note {{ font-size: var(--fs-1); color: var(--dash-ink-muted); margin-top: 4px; }}
  .fn-arrow {{ align-self: center; color: var(--dash-ink-muted);
              font-size: var(--fs-6); padding: 0 1px; }}
  .fn-worst {{ border-color: var(--dash-accent);
              box-shadow: inset 0 -3px 0 var(--dash-accent); }}
  .fn-zero .fn-n {{ color: var(--dash-ink-muted); }}
  .fn-errs {{ margin-top: var(--sp-2); font-size: var(--fs-2);
             color: var(--dash-ink-2); }}
  .fn-errs summary {{ cursor: pointer; }}
  .fn-errs ul {{ margin: var(--sp-1) 0 0; padding-left: 1.2em; }}
  .fn-errs li {{ margin: 2px 0; word-break: break-all; }}

  /* ── 국내 스크리너 ────────────────────────────────────────────────── */
  .dash-scr-head {{
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
    border-bottom: 1px solid var(--dash-divider);
    padding-bottom: var(--sp-2); margin: var(--sp-5) 0 var(--sp-2);
  }}
  .dash-scr-title {{
    font-size: var(--fs-6); font-weight: 750; color: var(--dash-ink);
    flex: 0 0 auto; white-space: nowrap;
  }}
  .dash-scr-rule {{
    font-size: var(--fs-3); color: var(--dash-ink-2); flex: 1 1 240px;
  }}
  .dash-scr-caveat {{
    font-size: var(--fs-2); color: var(--dash-ink-muted);
    border-left: 2px solid var(--dash-border);
    padding: 2px 0 2px 10px; margin: 0 0 var(--sp-3);
  }}

  /* 통과 종목의 지표 — 가로 한 줄. 세로 목록으로 쌓으면 종목 간 비교가
     안 됩니다. 좁아지면 줄바꿈되게 둡니다. */
  .dash-hit-row {{
    display: flex; flex-wrap: wrap; gap: var(--sp-3) 22px;
    padding: var(--sp-3) 0;
    border-bottom: 1px solid var(--dash-divider);
  }}
  .dash-hit-cell {{ min-width: 92px; }}
  .dash-hit-label {{
    font-size: var(--fs-1); color: var(--dash-ink-muted);
    margin-bottom: 2px; white-space: nowrap;
  }}
  .dash-hit-value {{
    font-size: var(--fs-5); font-weight: 650; color: var(--dash-ink);
    font-variant-numeric: tabular-nums;
  }}
  .dash-hit-why {{ padding: var(--sp-3) 0 0; }}
  .dash-hit-why ul {{ margin: 0; padding-left: 17px; }}
  .dash-hit-why li {{
    font-size: var(--fs-3); color: var(--dash-ink-2); margin-bottom: 4px;
    line-height: 1.55;
  }}
  .dash-hit-links {{
    font-size: var(--fs-3); padding: var(--sp-2) 0 0;
  }}

  /* 키-값 표 (기업개황) */
  .dash-kv {{
    width: 100%; border-collapse: collapse; margin: var(--sp-2) 0;
  }}
  .dash-kv th, .dash-kv td {{
    text-align: left; padding: 6px 10px 6px 0; vertical-align: top;
    border-bottom: 1px solid var(--dash-divider);
    font-size: var(--fs-3); line-height: 1.5;
  }}
  .dash-kv th {{
    color: var(--dash-ink-muted); font-weight: 600;
    width: 130px; white-space: nowrap;
  }}
  .dash-kv td {{ color: var(--dash-ink); }}

  /* ── 분석 스킬 딥링크 ─────────────────────────────────────────────── */
  .dash-skills {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); margin: var(--sp-2) 0;
    overflow: hidden;
  }}
  .dash-skill-row {{
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--sp-3); flex-wrap: wrap;
    padding: var(--sp-3) 14px;
    border-bottom: 1px solid var(--dash-divider);
  }}
  .dash-skill-row:last-child {{ border-bottom: none; }}
  .dash-skill-name {{
    font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink);
    display: flex; flex-direction: column; gap: 2px; min-width: 150px;
  }}
  .dash-skill-desc {{
    font-size: var(--fs-2); font-weight: 400; color: var(--dash-ink-muted);
  }}
  .dash-skill-links {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .dash-skill-btn {{
    display: inline-block; text-decoration: none;
    font-size: var(--fs-2); font-weight: 600;
    padding: 6px 11px; border-radius: var(--r-inner);
    border: 1px solid var(--dash-border);
    background: var(--dash-raised); color: var(--dash-ink);
    white-space: nowrap;
  }}
  .dash-skill-btn:hover {{ border-color: var(--dash-ink-muted); }}
  .dash-skill-btn.ghost {{
    background: transparent; color: var(--dash-ink-2);
  }}
  @media (max-width: 620px) {{
    .dash-skill-row {{ flex-direction: column; align-items: stretch; }}
    .dash-skill-links {{ display: grid; grid-template-columns: 1fr 1fr; }}
    .dash-skill-btn {{ text-align: center; }}
    .dash-skill-btn.ghost {{ grid-column: 1 / -1; }}
  }}

  /* ── 섹터별 뉴스 ──────────────────────────────────────────────────── */
  .dash-sectors {{
    display: grid; gap: var(--sp-3);
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    margin: var(--sp-2) 0;
  }}
  .dash-sector {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); padding: 11px 13px;
  }}
  .dash-sector-name {{
    font-size: var(--fs-4); font-weight: 700; color: var(--dash-ink);
    display: flex; flex-direction: column; gap: 2px;
    margin-bottom: var(--sp-2);
    padding-bottom: var(--sp-2);
    border-bottom: 1px solid var(--dash-divider);
  }}
  .dash-sector-q {{
    font-size: var(--fs-1); font-weight: 400; color: var(--dash-ink-muted);
  }}
  .dash-sector ul {{ margin: 0; padding-left: 16px; }}
  .dash-sector li {{
    font-size: var(--fs-3); color: var(--dash-ink-2);
    margin-bottom: 5px; line-height: 1.5;
  }}
  .dash-sector li::marker {{ color: var(--dash-ink-muted); }}
  .dash-sector-empty {{
    font-size: var(--fs-2); color: var(--dash-ink-muted);
  }}
  .dash-exp-value {{
    font-size: var(--fs-8); font-weight: 700; color: var(--dash-ink);
    font-variant-numeric: tabular-nums; margin: 6px 0 2px;
  }}
  /* 변화량은 본값보다 작게 — 같은 크기면 뭐가 현재값인지 안 보입니다 */
  .dash-exp-value .dash-exp-delta {{
    font-size: var(--fs-4); font-weight: 650; margin-left: 8px;
    color: var(--dash-ink-2);
  }}

  /* ── 섹터 온도 ────────────────────────────────────────────────────── */
  table.dash-heat td.heat {{
    color: var(--dash-ink); white-space: nowrap;
    border-left: 1px solid var(--dash-surface);
  }}
  table.dash-heat .heat-arrow {{
    font-size: .72em; margin-right: 3px; opacity: .8;
  }}
  /* 줄무늬가 온도색을 덮으면 안 됩니다 — 히트맵에서는 끕니다 */
  table.dash-heat tbody tr:nth-child(even) {{ background: transparent; }}
  table.dash-heat tbody tr:nth-child(even) td:first-child {{
    background: var(--dash-surface);
  }}
  table.dash-heat .heat-name {{
    font-weight: 700; color: var(--dash-ink); display: block;
  }}
  table.dash-heat .heat-code {{
    font-size: var(--fs-1); color: var(--dash-ink-muted); font-weight: 500;
  }}
  table.dash-heat .heat-bad {{
    display: inline-block; margin-left: 4px;
    font-size: var(--fs-1); font-weight: 700;
    color: var(--dash-badge-error);
    border: 1px solid var(--dash-badge-error);
    border-radius: var(--r-chip); padding: 0 4px;
  }}
  table.dash-heat tr.heat-bench td {{
    border-bottom: 2px solid var(--dash-border);
  }}
  table.dash-heat tr.heat-bench .heat-name::after {{
    content: " 기준"; font-size: var(--fs-1); font-weight: 600;
    color: var(--dash-accent);
  }}
  table.dash-heat tr.heat-fail td {{ color: var(--dash-ink-muted); }}
  /* 52주 위치 — 막대 위의 눈금 */
  .heat-band {{
    position: relative; display: inline-block; vertical-align: middle;
    width: 54px; height: 6px; border-radius: var(--r-chip);
    background: var(--dash-raised); border: 1px solid var(--dash-divider);
    margin-right: 6px;
  }}
  .heat-band i {{
    position: absolute; top: -3px; width: 4px; height: 10px;
    margin-left: -2px; border-radius: var(--r-chip); background: var(--dash-ink);
  }}
  .heat-band-num {{
    font-size: var(--fs-2); color: var(--dash-ink-2);
    display: inline-block; min-width: 36px; text-align: right;
  }}
  .heat-spark {{ display: block; }}
  .heat-sum {{
    background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 12px 14px; margin: 0 0 12px;
    display: flex; flex-direction: column; gap: 8px;
  }}
  .heat-sum-row {{
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }}
  .heat-sum-lab {{
    font-size: var(--fs-2); font-weight: 700; color: var(--dash-ink-muted);
    width: 34px; flex: none;
  }}
  .heat-chip {{
    font-size: var(--fs-3); padding: 4px 10px;
    border-radius: var(--r-pill); color: var(--dash-ink);
  }}
  .heat-chip b {{ font-variant-numeric: tabular-nums; margin-left: 2px; }}
  .heat-chip.up {{
    background: color-mix(in srgb, var(--dash-up) 16%, var(--dash-surface));
  }}
  .heat-chip.up b {{ color: var(--dash-up); }}
  .heat-chip.down {{
    background: color-mix(in srgb, var(--dash-down) 16%, var(--dash-surface));
  }}
  .heat-chip.down b {{ color: var(--dash-down); }}
  .heat-sum-note {{ font-size: var(--fs-1); color: var(--dash-ink-muted); }}

  /* ── 한국 반도체 수출 ─────────────────────────────────────────────── */
  .dash-exp {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-surface); padding: 11px 14px; margin: 4px 0 10px;
  }}
  .dash-exp-top {{
    display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap;
  }}
  .dash-exp-label {{
    font-size: var(--fs-4); font-weight: 700; color: var(--dash-ink);
  }}
  .dash-exp-period {{
    font-size: var(--fs-3); color: var(--dash-ink-muted);
    font-variant-numeric: tabular-nums;
  }}
  .dash-exp-link {{ margin-left: auto; font-size: var(--fs-2); }}
  .dash-exp-nums {{
    display: flex; align-items: baseline; gap: 18px; margin-top: 7px;
    flex-wrap: wrap;
  }}
  .dash-exp-amt {{
    font-size: var(--fs-7); font-weight: 700; color: var(--dash-ink);
    font-variant-numeric: tabular-nums;
  }}
  .dash-exp-yoy {{
    font-size: var(--fs-5); font-weight: 650; color: var(--dash-ink-2);
    font-variant-numeric: tabular-nums;
  }}
  .dash-exp-yoy.up {{ color: var(--dash-up); }}
  .dash-exp-yoy.down {{ color: var(--dash-down); }}
  .dash-exp-why {{
    display: block; margin-top: 6px; font-size: var(--fs-2); line-height: 1.55;
    color: var(--dash-ink-muted);
  }}
  .dash-exp-fail {{ border-style: dashed; }}
  @media (max-width: 640px) {{
    .dash-exp-link {{ margin-left: 0; }}
  }}

  /* ── 외부 대시보드 링크 ───────────────────────────────────────────── */
  .dash-ext {{
    display: grid; gap: 6px; margin: 6px 0 12px;
    border: 1px solid var(--dash-border); border-radius: var(--r-inner);
    background: var(--dash-surface); padding: 10px 13px;
  }}
  .dash-ext-row {{
    display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap;
  }}
  .dash-ext-link {{ font-size: var(--fs-4); font-weight: 650; white-space: nowrap; }}
  .dash-ext-note {{
    font-size: var(--fs-2); color: var(--dash-ink-muted); line-height: 1.5;
  }}
  @media (max-width: 640px) {{
    .dash-prelim-row {{
      grid-template-columns: 1fr auto; row-gap: 3px;
    }}
    .dash-prelim-nm {{ grid-column: 1 / -1; }}
    .dash-prelim-link {{ grid-column: 1 / -1; }}
  }}

  /* ── 가격 조건 ────────────────────────────────────────────────────── */
  /* 2026-11-11: 이 상자가 .dash-price 라는 이름을 시세 카드의 가격 숫자와
     같이 써서, **모든 시세 카드의 숫자에 회색 상자가 씌워졌습니다.**
     카드가 투박해 보이던 원인 중 하나입니다. 이름을 나눴습니다. */
  .dash-pricecond {{
    border: 1px solid var(--dash-border); border-radius: var(--r-card);
    background: var(--dash-raised); padding: 11px 13px; margin-top: 8px;
  }}
  .dash-price-top {{
    display: flex; align-items: baseline; gap: 9px; flex-wrap: wrap;
  }}
  .dash-price-label {{
    font-size: var(--fs-4); font-weight: 700; color: var(--dash-ink);
  }}
  .dash-price-basis {{
    flex-basis: 100%; font-size: var(--fs-2); color: var(--dash-ink-muted);
    margin-top: 2px;
  }}
  .dash-price-metrics {{
    margin-top: 10px; padding-top: 9px;
    border-top: 1px solid var(--dash-divider);
    display: flex; gap: 20px; flex-wrap: wrap;
  }}
  .dash-price-metrics-head {{
    flex-basis: 100%; font-size: var(--fs-2); color: var(--dash-ink-muted);
    letter-spacing: .02em;
  }}
  .dash-price-metric {{ display: flex; align-items: baseline; gap: 6px; }}
  .dash-price-metric-label {{
    font-size: var(--fs-2); color: var(--dash-ink-muted);
  }}
  .dash-price-metric-val {{
    font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink-2);
    font-variant-numeric: tabular-nums;
  }}
  @media (max-width: 640px) {{
    .dash-bf-date, .dash-bf-line-date {{ margin-left: 0; }}
    .dash-price-metrics {{ gap: 12px; }}
  }}

  .dash-macro-group {{
    font-size: var(--fs-4); font-weight: 650; color: var(--dash-ink);
    margin: 22px 0 1px; display: flex; align-items: baseline; gap: 9px;
  }}
  .dash-macro-group .sub {{
    font-size: var(--fs-2); font-weight: 500; color: var(--dash-ink-muted);
  }}

  /* ══ 휴대폰 공통 ═══════════════════════════════════════════════════════ */
  @media (max-width: 640px) {{
    /* 본문 여백 — 스트림릿 기본 좌우 여백이 좁은 화면의 1/8 을 가져갑니다 */
    section[data-testid="stMain"] .block-container,
    div[data-testid="stMainBlockContainer"] {{
      padding-left: 0.7rem !important; padding-right: 0.7rem !important;
    }}
    /* 표를 그대로 둘 때(카드로 세우지 않을 때)는 **옆으로 밀 수 있어야**
       합니다. 감싼 칸이 화면보다 넓어지면 밀리지 않고 잘리기만 하므로
       폭을 화면에 묶습니다. 종목 이름 칸은 밀어도 붙어 있습니다. */
    .dash-table-wrap, .dash-htable-wrap {{
      max-width: calc(100vw - 1.4rem); overflow-x: auto;
      -webkit-overflow-scrolling: touch; overscroll-behavior-x: contain;
    }}
    .dash-htable td.ht-name, .dash-htable td.hd-name {{
      position: sticky; left: 0; z-index: 1; background: var(--dash-surface);
      box-shadow: 1px 0 0 var(--dash-divider);
    }}
    /* 건수 카드 묶음은 **옆으로 미는 한 줄**로 — 일곱 장을 두 줄씩 세우면
       목록이 나오기 전에 화면 두 장을 씁니다. 다음 카드가 반쯤 걸쳐 보여서
       밀 수 있다는 걸 알립니다. */
    .dash-cc, .dash-fc-grid {{
      display: flex !important; overflow-x: auto; gap: 8px;
      scroll-snap-type: x proximity; -webkit-overflow-scrolling: touch;
      padding-bottom: 6px; max-width: calc(100vw - 1.4rem);
    }}
    .dash-cc > *, .dash-fc-grid > * {{
      flex: 0 0 43%; min-width: 132px; scroll-snap-align: start;
    }}
    .dash-pf {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .dash-sectors {{ grid-template-columns: minmax(0, 1fr); }}
    .dash-kv {{ display: block; max-width: calc(100vw - 1.4rem); overflow-x: auto; }}
    .dash-kv th, .dash-kv td {{ white-space: normal !important; }}
    .dash-check {{ grid-template-columns: 17px minmax(0, 1fr) auto; }}
    .dash-check > * {{ min-width: 0; overflow-wrap: anywhere; }}
    .dash-scr-title {{ white-space: normal; flex: 1 1 auto; }}
  }}
"""


def build_stack_rules() -> str:
    """좁은 화면에서 표를 카드로 세우는 규칙. build_css(stack=False) 면 뺍니다
    (그때는 표를 그대로 두고 옆으로 밀어 봅니다)."""
    return f"""
  /* ══ 좁은 화면 — 표를 줄 단위 카드로 ═══════════════════════════════════
     components.stack_tables 가 칸마다 data-l="머리글" 을 넣어 둡니다.
     640px 아래에서는 한 줄(tr)을 카드 한 장으로 세우고, 머리글을 칸 왼쪽에
     띄웁니다(float). 값 쪽은 여러 줄이어도 오른쪽에 그대로 흐릅니다.
     이 묶음은 **파일 맨 끝**에 있어야 합니다 — 표마다 따로 준 폭·정렬·
     고정 열 규칙을 여기서 덮기 때문입니다. */
  @media (max-width: 640px) {{
    .dash-stkw {{
      overflow: visible !important; max-height: none !important;
      border: none !important; background: none !important;
      border-radius: 0 !important;
    }}
    table.dash-stk, table.dash-stk tbody {{ display: block; width: 100%; }}
    table.dash-stk thead {{ display: none; }}
    table.dash-stk tr {{
      display: block; margin: 0 0 8px; padding: 10px 12px 8px;
      background: var(--dash-surface) !important;
      border: 1px solid var(--dash-border); border-radius: var(--r-card);
    }}
    table.dash-stk td {{
      display: flow-root; text-align: right !important;
      padding: 4px 0 !important; border: none !important;
      white-space: normal !important; position: static !important;
      background: none !important; width: auto !important;
      min-width: 0 !important; max-width: none !important;
      font-size: var(--fs-3); line-height: 1.45; opacity: 1;
      overflow-wrap: anywhere;
    }}
    table.dash-table.dash-stk td.mk {{ text-align: right !important; }}
    table.dash-stk td + td {{ border-top: 1px solid var(--dash-divider) !important; }}
    table.dash-stk td::before {{
      content: attr(data-l); float: left; max-width: 44%;
      margin-right: 12px; text-align: left;
      color: var(--dash-ink-muted); font-size: var(--fs-2); font-weight: 500;
      white-space: normal; line-height: 1.45;
    }}
    /* 카드 제목 — 첫 칸(순위 칸이 있으면 그다음 칸) */
    table.dash-stk td:first-child:not(.ht-rank),
    table.dash-stk td.ht-rank + td {{
      text-align: left !important; font-size: var(--fs-5); font-weight: 700;
      padding: 0 0 7px !important; border-top: none !important;
    }}
    table.dash-stk td.ht-name, table.dash-stk td.hd-name {{ box-shadow: none; }}
    table.dash-stk td:first-child:not(.ht-rank)::before,
    table.dash-stk td.ht-rank + td::before {{ content: none; }}
    table.dash-stk td.ht-rank {{ display: none; }}
    /* 값 아래 보조 줄은 같은 줄로 올립니다 — 카드 높이가 절반이 됩니다 */
    table.dash-stk td .sub {{
      display: inline !important; font-size: var(--fs-2); margin: 0 0 0 7px; }}
    table.dash-stk td .sub + .sub::before {{ content: "· "; }}
    table.dash-stk td:first-child .sub, table.dash-stk td.ht-rank + td .sub {{
      display: inline; margin-left: 6px; font-weight: 500;
    }}
    /* 비교용 막대·흐림은 카드에서 빼냅니다 */
    table.dash-stk tr.dv-other td {{ opacity: 1; }}
    table.dash-stk tr.dv-other {{ opacity: .6; }}
    .dash-pft.dash-stk td.pf-w i {{ display: none; }}

    /* 품질 한눈표 — 기준 9칸 대신 '걸린 기준' 한 줄 (종목당 12줄 → 4줄) */
    table.dash-stk.dash-sctable td.mk {{ display: none !important; }}
    table.dash-stk.dash-sctable td.sc-miss {{ display: flow-root !important; }}
    table.dash-stk.dash-sctable .sc-name {{ display: inline; margin-left: 6px;
      font-size: var(--fs-2); font-weight: 500; }}
    table.dash-stk.dash-sctable .sc-sub {{ display: inline; margin-left: 7px;
      font-size: var(--fs-2); }}

    /* 차트 조건 — 해당하는 조건만 남깁니다 (7칸을 다 세우면 종목당 9줄) */
    table.dash-ctable.dash-stk td.ct-no,
    table.dash-ctable.dash-stk td.ct-na {{ display: none; }}
    table.dash-ctable.dash-stk td span {{ max-width: none !important; }}
    table.dash-ctable.dash-stk td.ct-yes span {{
      display: inline !important; margin-left: 6px; color: var(--dash-ink-2);
      font-size: var(--fs-2); }}

    /* 시장 공시 — 회사 / 유형·날짜 / 보고서 */
    table.dash-fl.dash-stk tr {{
      display: grid; grid-template-columns: 1fr auto; gap: 4px 10px;
      align-items: start;
    }}
    table.dash-fl.dash-stk td {{ display: block; padding: 0 !important;
                                 border: none !important; }}
    table.dash-fl.dash-stk td::before {{ content: none !important; }}
    table.dash-fl.dash-stk td:nth-child(3) {{
      grid-column: 1 / -1; grid-row: 1; text-align: left !important;
      font-size: var(--fs-5); font-weight: 700;
    }}
    table.dash-fl.dash-stk td:nth-child(2) {{
      grid-column: 1; grid-row: 2; text-align: left !important;
      font-size: var(--fs-3); font-weight: 400; white-space: normal;
    }}
    table.dash-fl.dash-stk td:nth-child(2) .dash-fk-sub {{
      display: inline; margin-left: 6px; white-space: normal; }}
    table.dash-fl.dash-stk td:nth-child(1) {{
      grid-column: 2; grid-row: 2; text-align: right !important;
      font-size: var(--fs-2) !important; font-weight: 500 !important;
      color: var(--dash-ink-muted); padding: 2px 0 0 !important;
    }}
    table.dash-fl.dash-stk td:nth-child(1) .dash-fl-mkt {{
      display: inline; margin-left: 6px; }}
    table.dash-fl.dash-stk td:nth-child(4) {{
      grid-column: 1 / -1; grid-row: 3; text-align: left !important;
      min-width: 0 !important; padding-top: 3px !important;
    }}

    /* 실적(미국) — 분기 칩은 머리글 아래 한 줄로 */
    table.dash-est.dash-stk td.es-cell {{ text-align: left !important; }}
    table.dash-est.dash-stk td.es-cell::before {{ float: none; display: block;
      max-width: none; margin: 0 0 5px; }}
    .es-q {{ min-width: 66px; }}


    /* 긴 목록은 **칸 안에서** 위아래로 밉니다 — 43종목을 그대로 세우면
       그 아래 내용까지 가려면 화면을 스무 번 넘겨야 합니다. 끝까지 밀면
       바깥 화면이 이어서 움직입니다. */
    .dash-stkw.dash-stk-long {{
      max-height: 74vh !important; overflow-y: auto !important;
      -webkit-overflow-scrolling: touch;
      border-top: 1px solid var(--dash-border) !important;
      border-bottom: 1px solid var(--dash-border) !important;
      padding: 0 1px 6px;
    }}
    .dash-stkw.dash-stk-long::before {{
      content: attr(data-n) "개 · 이 칸 안에서 위아래로 밀어 보기";
      position: sticky; top: 0; z-index: 3; display: block;
      padding: 6px 2px; margin-bottom: 4px;
      background: var(--dash-page); color: var(--dash-ink-muted);
      font-size: var(--fs-2); font-family: {FONT_STACK};
      border-bottom: 1px solid var(--dash-divider);
    }}
  }}
"""


def build_native_rules() -> str:
    """스트림릿 **기본 부품**(버튼·접는 카드·칩·토글·선택 상자)의 색을 고정합니다.

    2026-11-12 실제 앱에서 확인한 문제: 테마 설정 파일(.streamlit/config.toml)
    이 적용되지 않고 있었습니다 (마지막 줄이 잘려 문법 오류). 그러면
    스트림릿은 **보는 기기의 다크/라이트 설정**을 따라갑니다. 다크 모드
    휴대폰에서는 기본 부품이 검은 바탕·흰 글자로 그려지는데, 대시보드는
    밝은 바탕을 깔고 있어서 — 버튼은 검은 덩어리가 되고, 바탕 없이 글자만
    있는 부품(접는 카드 제목·토글 이름·칩 이름)은 흰 글자가 밝은 바탕에
    묻혀 **아예 안 보였습니다.**

    설정 파일에 기대지 않도록, 기본 부품의 색을 여기서 대시보드 변수로
    직접 정합니다. 선택자는 실제 앱의 구조에서 읽은 것입니다
    (stBaseButton-secondary · stPopoverButton · stButtonGroup 안의
    role=radio 버튼 · stExpander …). 스트림릿이 구조를 바꾸면 그 부품만
    기본 모양으로 돌아갑니다.
    """
    return f"""
  /* ══ 스트림릿 기본 부품 — 기기의 다크 모드와 무관하게 ══════════════════ */
  :root {{ color-scheme: light; }}
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    color: var(--dash-ink);
  }}
  header[data-testid="stHeader"] {{
    background: var(--dash-page) !important; color: var(--dash-ink) !important;
  }}
  header[data-testid="stHeader"] * {{ color: var(--dash-ink) !important; }}

  /* 글자 — 바탕 없이 글자만 있는 부품들 */
  [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
  [data-testid="stWidgetLabel"] p, [data-testid="stCheckbox"] label,
  [data-testid="stRadio"] label, [data-testid="stRadio"] label p,
  [data-testid="stCheckbox"] label p, [data-testid="stExpanderDetails"],
  [data-testid="stSpinner"], [data-testid="stText"] {{
    color: var(--dash-ink);
  }}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
  [data-testid="stTooltipIcon"] svg {{
    color: var(--dash-ink-muted) !important;
  }}

  /* 버튼 — 기본(흰 바탕·테두리), 강조(남색) */
  button[kind="secondary"], [data-testid="stBaseButton-secondary"],
  [data-testid="stPopoverButton"], [data-testid="stBaseButton-headerNoPadding"] {{
    background: var(--dash-surface) !important; color: var(--dash-ink) !important;
    border: 1px solid var(--dash-border) !important;
    border-radius: var(--r-inner) !important;
  }}
  button[kind="secondary"]:hover, [data-testid="stPopoverButton"]:hover {{
    border-color: var(--dash-accent) !important; color: var(--dash-accent) !important;
    background: var(--dash-surface) !important;
  }}
  button[kind="secondary"]:active, button[kind="secondary"]:focus:not(:active),
  [data-testid="stPopoverButton"]:focus:not(:active) {{
    background: var(--dash-surface) !important; color: var(--dash-ink) !important;
    border-color: var(--dash-accent) !important;
  }}
  button[kind="primary"], [data-testid="stBaseButton-primary"] {{
    background: var(--dash-accent) !important; color: #fff !important;
    border: 1px solid var(--dash-accent) !important;
    border-radius: var(--r-inner) !important;
  }}
  button [data-testid="stMarkdownContainer"],
  button [data-testid="stMarkdownContainer"] p,
  button [data-testid="stIconMaterial"] {{ color: inherit !important; }}

  /* 고르는 칩 (시장 · 스크리너 · 조건) — 줄이 넘치면 잘리지 않고 다음 줄로 */
  [data-testid="stButtonGroup"] [role="radiogroup"],
  [data-testid="stButtonGroup"] > div:last-child {{
    flex-wrap: wrap !important; gap: 6px !important; overflow: visible !important;
  }}
  [data-testid="stButtonGroup"] button {{
    background: var(--dash-surface) !important; color: var(--dash-ink-2) !important;
    border: 1px solid var(--dash-border) !important;
    border-radius: var(--r-pill) !important; min-height: 36px;
    max-width: 100%;
  }}
  [data-testid="stButtonGroup"] button * {{ color: inherit !important; }}
  [data-testid="stButtonGroup"] button p {{
    white-space: normal !important; text-align: left; line-height: 1.3;
  }}
  [data-testid="stButtonGroup"] button[aria-checked="true"],
  [data-testid="stButtonGroup"] button[aria-pressed="true"],
  [data-testid="stButtonGroup"] button[aria-selected="true"],
  [data-testid="stButtonGroup"] button[kind$="Active"] {{
    background: color-mix(in srgb, var(--dash-accent) 12%, var(--dash-surface)) !important;
    color: var(--dash-accent) !important; border-color: var(--dash-accent) !important;
    font-weight: 700 !important;
  }}

  /* 접는 카드 — 접혀 있어도 제목이 보여야 합니다 */
  [data-testid="stExpander"] details {{
    background: var(--dash-surface) !important;
    border: 1px solid var(--dash-border) !important;
    border-radius: var(--r-card) !important;
  }}
  [data-testid="stExpander"] summary {{
    color: var(--dash-ink) !important; background: transparent !important;
    border-radius: var(--r-card) !important;
  }}
  [data-testid="stExpander"] summary:hover,
  [data-testid="stExpander"] summary:focus,
  [data-testid="stExpander"] summary:active {{
    color: var(--dash-accent) !important; background: var(--dash-raised) !important;
  }}
  [data-testid="stExpander"] summary *,
  [data-testid="stExpander"] summary svg {{ color: inherit !important; fill: currentColor; }}
  [data-testid="stExpander"] summary p {{ font-weight: 600; }}

  /* 떠오르는 패널 · 선택 상자 · 입력란 */
  [data-testid="stPopoverBody"], [data-baseweb="popover"] > div > div {{
    background: var(--dash-surface) !important; color: var(--dash-ink) !important;
    border-color: var(--dash-border) !important;
  }}
  [data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"],
  [data-baseweb="input"] input, [data-testid="stNumberInput"] input,
  [data-testid="stTextInput"] input, textarea {{
    background: var(--dash-surface) !important; color: var(--dash-ink) !important;
    border-color: var(--dash-border) !important;
    -webkit-text-fill-color: var(--dash-ink);
  }}
  [data-baseweb="select"] * {{ color: var(--dash-ink) !important; }}
  [role="listbox"], [data-baseweb="menu"], [data-baseweb="menu"] ul {{
    background: var(--dash-surface) !important;
  }}
  [role="option"], [data-baseweb="menu"] li {{
    color: var(--dash-ink) !important; background: var(--dash-surface) !important;
  }}
  [role="option"]:hover, [role="option"][aria-selected="true"] {{
    background: var(--dash-raised) !important;
  }}
  [data-testid="stNumberInput"] button {{
    background: var(--dash-raised) !important; color: var(--dash-ink) !important;
  }}
  /* 탭 (설정 패널 안) */
  [data-baseweb="tab"] {{ color: var(--dash-ink-2) !important; background: transparent !important; }}
  [data-baseweb="tab"][aria-selected="true"] {{ color: var(--dash-accent) !important; }}
  [data-baseweb="tab-highlight"] {{ background: var(--dash-accent) !important; }}
  [data-baseweb="tab-border"] {{ background: var(--dash-divider) !important; }}

  /* 알림 상자 (st.info · st.warning) — 흰 글자가 밝은 바탕에 묻히지 않게 */
  [data-testid="stAlert"] *, [data-testid="stAlertContainer"] * {{
    color: var(--dash-ink) !important;
  }}

  /* ── 위쪽 조작 줄 — 휴대폰에서도 **한 줄** ─────────────────────────────
     스트림릿은 좁은 화면에서 칸을 위아래로 쌓습니다. 설정 버튼 셋과
     갱신 버튼이 화면 한 장을 다 쓰던 이유입니다. 이 줄만은 쌓지 않습니다. */
  /* 2026-11-13: 폭을 나눠 쓰지 않고 글자만큼만 — 작은 버튼 둘을 오른쪽에 붙입니다 */
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) {{
    flex-wrap: nowrap !important; gap: 6px !important; align-items: center;
    justify-content: flex-end !important; margin-bottom: -8px;
  }}
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) > div[data-testid="stColumn"] {{
    min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
  }}
  /* 버튼과 그 감싸는 칸만 글자 폭으로 (패널 안쪽 위젯의 폭은 건드리지 않습니다) */
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) div[data-testid="stPopover"],
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) div[data-testid="stButton"],
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) div[data-testid="stElementContainer"],
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) div[data-testid="stVerticalBlock"],
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) button {{
    width: auto !important;
  }}
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) button {{
    min-height: 30px !important; padding: 2px 12px !important;
    border-radius: var(--r-pill) !important;
  }}
  div[data-testid="stHorizontalBlock"]:has(.dash-ctrlmark) button p {{
    font-size: var(--fs-3) !important; white-space: nowrap;
  }}
  div[data-testid="stElementContainer"]:has(> div > .dash-ctrlmark),
  div[data-testid="stElementContainer"]:has(.dash-ctrlmark):not(:has(button)) {{
    display: none !important;
  }}
"""
