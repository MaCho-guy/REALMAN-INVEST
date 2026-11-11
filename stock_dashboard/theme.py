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
"""


def build_css(convention: str) -> str:
    """앱 전체에 주입할 CSS (변수 + 규칙)."""
    return "<style>" + build_vars(convention) + build_rules() + "</style>"


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
  .dash-section-head {{
    display: flex; align-items: baseline; gap: var(--sp-3);
    margin: var(--sp-5) 0 var(--sp-3);
    padding: 0 0 var(--sp-2) 11px;
    border-bottom: 1px solid var(--dash-divider);
    border-left: 3px solid var(--dash-accent);
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
  table.dash-table thead th:first-child {{ background: var(--dash-raised); }}
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
    margin-top: var(--sp-2); display: flex; gap: var(--sp-2); flex-wrap: wrap;
  }}
  .dash-build-files code {{
    font-size: var(--fs-2); padding: 2px 7px;
    border: 1px solid var(--dash-border); border-radius: var(--r-chip);
    background: var(--dash-raised);
  }}

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
    font-size: var(--fs-1); font-weight: 700; letter-spacing: .06em;
    color: var(--dash-ink-muted);
    margin: var(--sp-3) 0 var(--sp-2); padding-left: 10px;
  }}
  .dash-navhead:first-child {{ margin-top: 0; }}

  /* 라디오를 목록처럼. 점은 지우고 **막대와 굵기**로 선택을 표시합니다 —
     점은 작아서 멀리서 안 보입니다. */
  div[data-testid="stVerticalBlock"] div[role="radiogroup"] {{
    gap: 2px;
  }}
  div[role="radiogroup"] > label {{
    display: flex; align-items: center;
    padding: 8px 10px;
    border-left: 3px solid transparent;
    border-radius: 0 var(--r-inner) var(--r-inner) 0;
    font-size: var(--fs-4); color: var(--dash-ink-2);
    cursor: pointer;
    transition: background .12s ease, border-color .12s ease;
  }}
  div[role="radiogroup"] > label:hover {{
    background: var(--dash-raised); color: var(--dash-ink);
  }}
  /* 선택된 항목 — :has() 가 없는 브라우저에서는 이 규칙만 빠지고
     목록은 그대로 돕니다. */
  div[role="radiogroup"] > label:has(input:checked) {{
    background: var(--dash-raised);
    border-left-color: var(--dash-accent);
    color: var(--dash-ink); font-weight: 750;
  }}
  /* 라디오 동그라미는 숨깁니다. 막대가 같은 일을 더 크게 합니다. */
  div[role="radiogroup"] > label > div:first-child {{
    display: none !important;
  }}

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
  .dash-price {{
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
"""
