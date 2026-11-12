"""
반도체 리포트 — 산업분석 중 반도체 · 삼성전자 · SK하이닉스 리포트를 한 화면에.

2026-11-12 요청: "산업리포트란 반도체 부분 요약해주는 탭 신설, 삼성전자
하이닉스 보고서도 그렇게 해줄 것".

**이 화면의 '요약' 이 무엇인가.** 이 서버에는 글을 읽고 요약하는 AI 가
없습니다. 그래서 요약을 두 겹으로 만듭니다:

  1. 묶음 요약 (코드가 셉니다)  기간 · 건수 · 증권사 수 · **자주 나온 말**.
     증권사들이 지금 무엇을 이야기하는지 한눈에 보는 용도입니다. 글을
     옮기지 않고 낱말이 몇 건의 리포트에 나오는지만 셉니다.
  2. 리포트별 미리보기  본문 **앞부분만** (네이버 목록이 주는 미리보기와
     같은 길이). 전문은 싣지 않고 원문·PDF 로 보냅니다 — 본문은 증권사의
     저작물입니다.

더 깊은 요약(리포트끼리 엇갈리는 주장, 근거 숫자)은 화면의 'Claude 에 요약
요청' 이 제목과 PDF 주소를 채워 넘깁니다.

**증권사 의견·목표주가.** 종목 리포트에는 증권사가 낸 투자의견과 목표주가가
붙어 옵니다. 그대로 적되 **증권사의 숫자**라고 표시하고, 평균을 내어
하나의 숫자로 만들지 않습니다 (이 대시보드는 목표주가를 제시하지 않습니다).
"""
from __future__ import annotations

import re
import statistics

#: 산업분석에서 '반도체' 로 볼 업종 이름.
CATEGORIES: tuple[str, ...] = ("반도체",)
#: 업종 칸이 비었을 때 제목으로 가리는 낱말.
TITLE_WORDS: tuple[str, ...] = ("반도체", "메모리", "HBM", "DRAM", "D램", "NAND",
                                "낸드", "파운드리", "삼성전자", "하이닉스")
#: 종목 리포트를 받을 종목.
STOCKS: tuple[tuple[str, str], ...] = (("005930", "삼성전자"), ("000660", "SK하이닉스"))

#: 자주 나온 말을 셀 낱말 — (화면 표기, 찾을 모양들). 대소문자를 가리지 않습니다.
TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("HBM", ("hbm",)),
    ("DRAM", ("dram", "d램", "디램")),
    ("NAND", ("nand", "낸드")),
    ("메모리 가격", ("가격", "asp", "판가")),
    ("AI · 데이터센터", ("ai", "데이터센터", "서버")),
    ("설비투자(CapEx)", ("capex", "설비투자", "증설", "투자 지연")),
    ("재고", ("재고",)),
    ("공급", ("공급",)),
    ("수요", ("수요",)),
    ("파운드리", ("파운드리", "foundry")),
    ("실적", ("실적", "영업이익", "어닝")),
    ("사이클", ("사이클", "업사이클", "다운사이클")),
    ("밸류에이션", ("밸류에이션", "p/b", "pbr", "per", "p/e")),
    ("환율", ("환율",)),
    ("관세 · 규제", ("관세", "규제", "수출 통제")),
    ("중국", ("중국", "cxmt", "ymtc")),
)

_WORD_AI = re.compile(r"(?<![a-z])ai(?![a-z])")


def is_semi(report) -> bool:
    """산업분석 리포트가 반도체 것인가 (업종 칸 우선, 없으면 제목)."""
    cat = (getattr(report, "category", "") or "").strip()
    if cat:
        return cat in CATEGORIES
    title = (getattr(report, "title", "") or "")
    low = title.lower()
    return any(w.lower() in low for w in TITLE_WORDS)


def _haystack(report) -> str:
    return f"{getattr(report, 'title', '')} {getattr(report, 'preview', '')}".lower()


def _mentions(text: str, needle: str) -> bool:
    if needle == "ai":                      # 'main' · 'rain' 에 걸리지 않게
        return bool(_WORD_AI.search(text))
    return needle in text


def keyword_counts(reports, top: int = 8) -> list[tuple[str, int]]:
    """[(말, 그 말이 나온 **리포트 수**)] — 많은 순. 한 리포트에서 여러 번 나와도 1."""
    counts: list[tuple[str, int]] = []
    texts = [_haystack(r) for r in reports]
    for label, needles in TERMS:
        n = sum(1 for t in texts if any(_mentions(t, nd) for nd in needles))
        if n:
            counts.append((label, n))
    counts.sort(key=lambda kv: -kv[1])
    return counts[:top]


def span(reports) -> tuple[str, str]:
    dates = sorted(r.date for r in reports if getattr(r, "date", ""))
    return (dates[0], dates[-1]) if dates else ("", "")


def brokers(reports) -> list[str]:
    seen: dict[str, int] = {}
    for r in reports:
        b = getattr(r, "broker", "")
        if b:
            seen[b] = seen.get(b, 0) + 1
    return [b for b, _n in sorted(seen.items(), key=lambda kv: -kv[1])]


def goal_change(report) -> str:
    """목표주가가 직전 대비 어떻게 바뀌었나 — '상향' · '하향' · '유지' · ''."""
    now, prev = getattr(report, "goal_price", None), getattr(report, "prev_goal_price", None)
    if not now or not prev:
        return ""
    # 커버리지를 새로 시작한 리포트는 '직전 목표가' 칸에 그날 주가가 들어
    # 옵니다 (2026-11-12 실제 응답: 직전 219,500 = 작성일 주가 219,500).
    # 그걸 상향으로 읽으면 안 됩니다.
    then = getattr(report, "price_then", None)
    if then and abs(prev - then) < 0.5:
        return ""
    if now > prev * 1.001:
        return "상향"
    if now < prev * 0.999:
        return "하향"
    return "유지"


def opinion_summary(reports) -> dict:
    """증권사 의견·목표주가를 **세기만** 합니다 (평균을 내지 않습니다).

    {with_goal, low, high, opinions: [(의견, 건수)], up, down, keep}
    """
    goals = [r.goal_price for r in reports if getattr(r, "goal_price", None)]
    ops: dict[str, int] = {}
    for r in reports:
        op = (getattr(r, "opinion", "") or "").strip()
        if op:
            key = _normalize_opinion(op)
            ops[key] = ops.get(key, 0) + 1
    moves = [goal_change(r) for r in reports]
    return {
        "with_goal": len(goals),
        "low": min(goals) if goals else None,
        "high": max(goals) if goals else None,
        "opinions": sorted(ops.items(), key=lambda kv: -kv[1]),
        "up": moves.count("상향"), "down": moves.count("하향"),
        "keep": moves.count("유지"),
    }


def _normalize_opinion(text: str) -> str:
    low = text.strip().lower()
    if low in ("buy", "매수", "strong buy", "적극매수", "trading buy", "outperform",
               "비중확대", "overweight"):
        return "매수 계열"
    if low in ("hold", "중립", "neutral", "보유", "marketperform", "market perform",
               "시장수익률"):
        return "중립 계열"
    if low in ("sell", "매도", "underperform", "비중축소", "underweight", "reduce"):
        return "매도 계열"
    return text.strip()


def digest(reports, what: str) -> list[str]:
    """묶음 요약 문장들 (글자 그대로 화면에 찍습니다 — HTML 아님)."""
    if not reports:
        return []
    lo, hi = span(reports)
    names = brokers(reports)
    lines = [
        f"{what} 리포트 {len(reports)}건 · 증권사 {len(names)}곳"
        + (f" · {lo[5:]} ~ {hi[5:]}" if lo else ""),
    ]
    words = keyword_counts(reports)
    if words:
        lines.append("자주 나온 말: " + " · ".join(f"{w} {n}건" for w, n in words))
    if names:
        lines.append("많이 낸 곳: " + " · ".join(names[:5]))
    return lines


def median_gap_days(reports) -> float | None:
    """리포트가 며칠에 한 건꼴로 나오나 (참고)."""
    import datetime as _dt

    days = sorted({r.date for r in reports if getattr(r, "date", "")})
    if len(days) < 3:
        return None
    ds = [_dt.date.fromisoformat(d) for d in days]
    gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
    return float(statistics.median(gaps)) if gaps else None
