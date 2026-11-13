"""후보 (한국) — 세 질문: 좋은 회사인가 · 싼가 · 이익 전망이 깎이고 있지 않은가.

2026-11-13 사용자: "4대를 토대로 통합하여 매수를 노려볼만한 종목 제안까지" → 같은 날
"찾기안들 기준이 너무 복잡하다" 로 단순화. 처음에는 등 네 개(품질 · 가격 · 차트 · 거래)
였는데, 차트(많이 내림)와 거래(많이 오름)는 방향이 반대인 신호라 '충족 개수' 로 더하면
뜻이 없어지고, 실제 순위를 가르는 것도 품질 · 가격 · 선행 EPS 셋이었습니다.

    등 ① 품질      초록 = 통과 (미달 2개 이하 · 판정 7개 이상) — 후보는 전부 초록
    등 ② 가격      초록 = 가격 부담 낮음 · 노랑 = 경계 / 판정 안 함 · 빨강 = 높음(관문)
    등 ③ 선행 EPS  초록 = 90일 상향(+0.5% 이상) · 노랑 = 보합 · 소폭 하향 · 빈칸 = 추정 없음
                   · 빨강 = −5% 이하(관문)
    꼬리표 '타이밍'  차트가 과매도 진입(최근 3봉)이면 — 순서에만 씁니다

관문 (하나라도 걸리면 후보가 아니고 '빠진 이유' 에 적습니다):
    품질 통과가 아님 · 가격 부담 높음 · 선행 EPS 90일 −5% 이하 (실적 추정이 깎이는 중)

순서: 초록 수 → 타이밍 꼬리표 → 선행 EPS 90일 변화 큰 순(추정 없음은 뒤) → 가격 여유.
거래 스크리너 신호는 근거(notes["trade"])에만 남기고 등으로 세지 않습니다.

**한 점수로 합치지 않습니다** — 초록 수는 순서를 정하는 데만 쓰고, 화면에는 등 네 개와
근거 글을 그대로 보입니다. 이 목록은 규칙으로 고른 '먼저 공시를 읽어볼 종목' 이지
매수 권유가 아닙니다. 목표가 · 단기 전망은 내지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import buffett
import chart_signals
import config
import funnel

GREEN, YELLOW, RED, GRAY = "g", "y", "r", "-"

#: ④ 거래 등 — 초록으로 치는 스크리너 (추세 · 반등)
TRADE_GREEN = ("contraction", "near_high", "rs", "rebound")
TRADE_NAMES = {"contraction": "변동성 수축", "near_high": "신고가 근처",
               "value_trad": "전통 밸류", "rs": "시장 대비 강함",
               "rebound": "낙폭 과대 반등", "surge": "거래대금 급증"}

#: 화면에 싣는 최대 후보 수
MAX_PICKS = 10


@dataclass
class Candidate:
    ticker: str
    name: str
    lamps: dict = field(default_factory=dict)      # {"quality","price","eps": 색}
    notes: dict = field(default_factory=dict)      # 등마다 근거 한 줄
    eps_c90: float | None = None
    price_gap: float | None = None
    excluded: str = ""                             # 관문에 걸린 이유 ('' = 후보)
    semi: bool = False
    new_entry: bool = False
    timing: bool = False                           # 차트 과매도 진입 (꼬리표)

    @property
    def greens(self) -> int:
        return sum(1 for v in self.lamps.values() if v == GREEN)

    def sort_key(self):
        c = self.eps_c90
        return (-self.greens, not self.timing, c is None, -(c or 0.0),
                self.price_gap if self.price_gap is not None else 1.0, self.ticker)


def _quality(sc) -> tuple[str, str]:
    if sc is None or not sc.ok:
        return GRAY, "재무를 받지 못함"
    txt = f"판정 {sc.known_count} 중 통과 {sc.passed_count} · 미달 {sc.failed_count}"
    if buffett.passes_kr(sc):
        return GREEN, txt
    if buffett.held_back_kr(sc):
        return YELLOW, txt + " (증거 부족 보류)"
    return RED, txt


def _price(frow: dict | None) -> tuple[str, str]:
    p = (frow or {}).get("p")
    state = funnel.price_state(p)
    if state == "light":
        return GREEN, "가격 부담 낮음 · " + funnel.gap_text(p)
    if state == "edge":
        return YELLOW, "경계 — 할인율 12%면 요구가 과거를 넘음"
    if state == "heavy":
        return RED, "가격 부담 높음 · " + funnel.gap_text(p)
    if not p:
        return YELLOW, "가격 계산 없음"
    if p.get("na"):
        why = p["na"]
    elif p.get("sev"):
        why = "FCF 기준값이 사이클로 크게 왜곡됨"
    elif p.get("g") is None:
        why = "역DCF 계산 불가 (FCF 적자 등)"
    elif p.get("h") is None:
        why = "과거 FCF 성장률 계산 불가 (적자 연도 · 이력 6년 미만)"
    else:
        why = "판정 근거 부족"
    return YELLOW, "판정 안 함 — " + why


def _chart(row) -> tuple[str, str]:
    if row is None or not row.ok:
        return GRAY, "일봉 없음"
    if chart_signals.is_os_entry(row):
        names = [n for k, n in (("cci", "CCI"), ("stoch", "스토캐스틱"))
                 if row.states.get(k) == chart_signals.ENTRY]
        return GREEN, " · ".join(names) + " 과매도 진입 (최근 3봉)"
    if row.side == "os":
        return YELLOW, "과매도 쪽"
    if row.side == "ob":
        return RED, "과매수 쪽 — 최근 많이 오름"
    return GRAY, "중립"


def _eps(f: dict | None) -> tuple[str, str]:
    c = (f or {}).get("c90")
    if c is None:
        return GRAY, "추정 없음 (야후)"
    txt = f"90일 {funnel.eps_arrow(c)} {c * 100:+.1f}%"
    if funnel.eps_down(f):
        return RED, txt + " — 추정이 깎이는 중"
    if c >= funnel.EPS_FLAT:
        return GREEN, txt + " 상향"
    return YELLOW, txt + (" 보합" if c > -funnel.EPS_FLAT else " 소폭 하향")


def _trade(keys: list[str]) -> tuple[str, str]:
    green = [k for k in keys if k in TRADE_GREEN]
    if green:
        return GREEN, " · ".join(TRADE_NAMES[k] for k in keys)
    if keys:
        return YELLOW, " · ".join(TRADE_NAMES[k] for k in keys) + " (방향 신호 아님)"
    return GRAY, "걸린 스크리너 없음"


def build(screens: list, frows: dict, chart_rows: dict, hits: dict,
          semis: set = (), new: set = ()) -> list[Candidate]:
    """품질 통과 종목마다 Candidate — 관문 통과(후보)가 앞, 빠진 종목이 뒤.

    screens: funnel_kr.json 의 screens (dict 또는 Screen) · frows: {코드: 깔때기 줄} ·
    chart_rows: {코드: ChartRow} · hits: {스크리너 키: [Hit]} (kr_screen.adaptive_hits).
    """
    by_hit: dict[str, list[str]] = {}
    for key, lst in (hits or {}).items():
        for h in lst or []:
            by_hit.setdefault(h.ticker, []).append(key)
    out: list[Candidate] = []
    for s in screens or []:
        sc = buffett.from_summary(s) if isinstance(s, dict) else s
        if sc is None or not buffett.passes_kr(sc):
            continue                                   # 관문 ① — 품질 통과만 살핌
        t = sc.ticker
        fr = frows.get(t)
        c = Candidate(ticker=t, name=sc.name, semi=t in semis, new_entry=t in new)
        for key, (col, note) in (("quality", _quality(sc)), ("price", _price(fr)),
                                 ("eps", _eps((fr or {}).get("f")))):
            c.lamps[key], c.notes[key] = col, note
        chart_col, c.notes["chart"] = _chart(chart_rows.get(t))
        c.timing = chart_col == GREEN
        c.notes["trade"] = _trade(by_hit.get(t, []))[1]
        c.eps_c90 = ((fr or {}).get("f") or {}).get("c90")
        c.price_gap = funnel.price_gap((fr or {}).get("p"))
        if c.lamps["price"] == RED:
            c.excluded = "가격 부담 높음"
        elif funnel.eps_down((fr or {}).get("f")):
            c.excluded = (f"선행 EPS 90일 {c.eps_c90 * 100:+.1f}% "
                          f"(−{abs(config.EPS_DOWN_WARN) * 100:g}% 이하)")
        out.append(c)
    picks = sorted([c for c in out if not c.excluded], key=Candidate.sort_key)
    rest = sorted([c for c in out if c.excluded], key=Candidate.sort_key)
    return picks + rest


def split(cands: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
    return [c for c in cands if not c.excluded], [c for c in cands if c.excluded]


def eps_text(c90) -> str:
    if c90 is None:
        return "선행 EPS 추정 없음"
    return f"선행 EPS 90일 {funnel.eps_arrow(c90)} {c90 * 100:+.1f}%"
