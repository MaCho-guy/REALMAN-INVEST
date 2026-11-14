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
import growth

GREEN, YELLOW, RED, GRAY = "g", "y", "r", "-"

#: ④ 거래 등 — 초록으로 치는 스크리너 (추세 · 반등)
TRADE_GREEN = ("contraction", "near_high", "rs", "rebound")
TRADE_NAMES = {"contraction": "변동성 수축", "near_high": "신고가 근처",
               "value_trad": "전통 밸류", "rs": "시장 대비 강함",
               "rebound": "낙폭 과대 반등", "surge": "거래대금 급증"}

#: 화면에 싣는 최대 후보 수
MAX_PICKS = 10
#: 선행 EPS 90일 변화가 이 크기(소수)를 넘으면 추정 이상값으로 보고 충족으로 세지 않음.
#: 2026-11-13 실측: Erie Indemnity +697% (야후 추정 이상) 가 미국 후보 4위로 올라옴.
EPS_OUTLIER = 1.0


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
    track: str = "stable"                          # 'stable' 안정형 · 'growth' 성장형 (11/13)
    also: bool = False                             # 다른 트랙 후보에도 있음
    gscore: int = 0                                # 성장 품질 통과 수 (성장형만, 11/13 17:02)

    @property
    def greens(self) -> int:
        return sum(1 for v in self.lamps.values() if v == GREEN)

    def sort_key(self):
        c = self.eps_c90
        # 성장형: 등 수가 같으면 성장 품질을 더 많이 통과한 회사 먼저 ("더 나은 기업", 11/13).
        # 안정형은 gscore = 0 이라 순서 그대로.
        return (-self.greens, -self.gscore, not self.timing, c is None, -(c or 0.0),
                self.price_gap if self.price_gap is not None else 1.0, self.ticker)


def held_back(sc, market: str = "kr") -> bool:
    return buffett.held_back_kr(sc) if market == "kr" else buffett.held_back_us(sc)


def _quality(sc, market: str = "kr") -> tuple[str, str]:
    if sc is None or not sc.ok:
        return GRAY, "재무를 받지 못함"
    txt = f"판정 {sc.known_count} 중 통과 {sc.passed_count} · 미달 {sc.failed_count}"
    if buffett.quality_pass(sc, market):
        return GREEN, txt
    if held_back(sc, market):
        return YELLOW, txt + " (판정 부족 보류)"
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
    old = funnel.eps_old_note(f)        # 지난 수집 값을 이어 쓴 경우 (11/14 — funnel.carry_eps)
    if abs(c) > EPS_OUTLIER:
        return GRAY, txt + " — 추정 이상값, 야후 확인 필요" + old
    if funnel.eps_down(f):
        return RED, txt + " — 추정이 깎이는 중" + old
    if c >= funnel.EPS_FLAT:
        return GREEN, txt + " 상향" + old
    return YELLOW, txt + (" 보합" if c > -funnel.EPS_FLAT else " 소폭 하향") + old


def _trade(keys: list[str]) -> tuple[str, str]:
    green = [k for k in keys if k in TRADE_GREEN]
    if green:
        return GREEN, " · ".join(TRADE_NAMES[k] for k in keys)
    if keys:
        return YELLOW, " · ".join(TRADE_NAMES[k] for k in keys) + " (방향 신호 아님)"
    return GRAY, "걸린 스크리너 없음"


def build(screens: list, frows: dict, chart_rows: dict, hits: dict,
          semis: set = (), new: set = (), market: str = "kr") -> list[Candidate]:
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
        if sc is None or not buffett.quality_pass(sc, market):
            continue                                   # 관문 ① — 품질 통과만 살핌 (미국 7/9)
        t = sc.ticker
        fr = frows.get(t)
        c = Candidate(ticker=t, name=sc.name, semi=t in semis, new_entry=t in new)
        for key, (col, note) in (("quality", _quality(sc, market)), ("price", _price(fr)),
                                 ("eps", _eps((fr or {}).get("f")))):
            c.lamps[key], c.notes[key] = col, note
        chart_col, c.notes["chart"] = _chart(chart_rows.get(t))
        c.timing = chart_col == GREEN
        c.notes["trade"] = _trade(by_hit.get(t, []))[1]
        c.eps_c90 = ((fr or {}).get("f") or {}).get("c90")
        if c.eps_c90 is not None and abs(c.eps_c90) > EPS_OUTLIER:
            c.eps_c90 = None                           # 순서에서는 '추정 없음' 처럼 뒤로
        c.price_gap = funnel.price_gap((fr or {}).get("p"))
        gr = s.get("gr") if isinstance(s, dict) else None
        if c.lamps["price"] == RED:
            c.excluded = "가격 부담 높음"
        elif funnel.eps_down((fr or {}).get("f")):
            c.excluded = (f"선행 EPS 90일 {c.eps_c90 * 100:+.1f}% "
                          f"(−{abs(config.EPS_DOWN_WARN) * 100:g}% 이하)")
        elif (gr or {}).get("td"):
            # 11/13 강화(사용자 승인): 10년 평균이 좋아도 최근 실적이 계속 꺾이면 뺌
            c.excluded = "실적 추세 악화 — 매출 · 영업이익이 3년 연속 함께 감소"
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


# ── 성장형 (11/13) — 안정형과 따로. 안정형 목록 · 순서에는 영향 없음 ──────────────

def _growth_lamp(gr, market) -> tuple[str, str]:
    p, k = growth.score(gr, market)
    if not gr:
        return GRAY, "성장 지표 없음 (다음 수집부터)"
    col = GREEN if growth.passes(gr, market) else RED
    return col, f"7개 중 통과 {p} (판정 {k}) · 기준 {growth.GROWTH_MIN_PASS}개 이상"


def _peg_lamp(f, price) -> tuple[str, str, float | None]:
    fpe, g1, pg = growth.peg(f, price)
    if pg is None:
        why = ("선행 EPS 없음" if fpe is None else
               f"선행 PER {fpe:.1f} · 내년 EPS 성장 " +
               ("없음" if g1 is None else f"{g1 * 100:+.1f}% (플러스여야 PEG 계산)"))
        return YELLOW, "PEG 판정 안 함 — " + why, None
    txt = f"PEG {pg:.2f} (선행 PER {fpe:.1f} ÷ 내년 EPS 성장 {g1 * 100:.1f}%)"
    if pg <= growth.PEG_GOOD:
        return GREEN, txt, pg
    if pg <= growth.PEG_OK:
        return YELLOW, txt, pg
    return RED, txt + f" — {growth.PEG_OK} 초과", pg


def _trend_lamp(f) -> tuple[str, str]:
    """성장형 '추정 흐름' — 30일 · 90일이 둘 다 상향이면 충족."""
    f = f or {}
    c30, c90 = f.get("c30"), f.get("c90")
    if c90 is None or abs(c90) > EPS_OUTLIER:
        return GRAY, "추정 없음 · 이상값"
    old = funnel.eps_old_note(f)        # 지난 수집 값을 이어 쓴 경우 (11/14)
    if funnel.eps_down(f):
        return RED, f"90일 {c90 * 100:+.1f}% — 추정이 깎이는 중" + old
    up90 = c90 >= funnel.EPS_FLAT
    up30 = c30 is not None and c30 >= funnel.EPS_FLAT
    txt = f"90일 {c90 * 100:+.1f}%" + ("" if c30 is None else f" · 30일 {c30 * 100:+.1f}%")
    if up90 and up30:
        return GREEN, txt + " — 상향 지속" + old
    return YELLOW, txt + (" — 최근 30일은 상향 아님" if up90 else " — 상향 아님") + old


def build_growth(screens: list, frows: dict, chart_rows: dict, semis: set = (),
                 new: set = (), market: str = "us", stable: set = ()) -> list[Candidate]:
    """성장형 후보 — 성장 품질 통과 종목만. 관문: PEG 2.5 초과 · 선행 EPS 90일 −5% 이하.

    등: 성장 품질 · 가격(PEG) · 추정 흐름(30 · 90일 상향 지속) + 타이밍 꼬리표.
    stable = 안정형 후보 티커 (겹치면 꼬리표만, 순서에는 쓰지 않음).
    """
    out: list[Candidate] = []
    for s in screens or []:
        if not isinstance(s, dict):
            continue
        gr = s.get("gr") or {}
        if not gr or not growth.passes(gr, market):
            continue
        sc = buffett.from_summary(s)
        if sc is None or not sc.ok:
            continue
        t = sc.ticker
        fr = frows.get(t) or {}
        row = chart_rows.get(t)
        price = getattr(row, "price", None) if row is not None else None
        c = Candidate(ticker=t, name=sc.name, semi=t in semis, new_entry=t in new,
                      track="growth", also=t in stable)
        c.lamps["growth"], c.notes["growth"] = _growth_lamp(gr, market)
        c.gscore = growth.score(gr, market)[0]
        c.lamps["price"], c.notes["price"], pg = _peg_lamp(fr.get("f"), price)
        c.lamps["eps"], c.notes["eps"] = _trend_lamp(fr.get("f"))
        chart_col, c.notes["chart"] = _chart(row)
        c.timing = chart_col == GREEN
        c90 = (fr.get("f") or {}).get("c90")
        c.eps_c90 = None if c90 is None or abs(c90) > EPS_OUTLIER else c90
        c.price_gap = pg                         # 성장형은 '가격 여유' 대신 PEG 낮은 순
        if c.lamps["price"] == RED:
            c.excluded = f"가격 부담 높음 — PEG {pg:.2f}"
        elif c.lamps["eps"] == RED:
            c.excluded = f"선행 EPS 90일 {c90 * 100:+.1f}% (−{abs(config.EPS_DOWN_WARN) * 100:g}% 이하)"
        out.append(c)
    picks = sorted([c for c in out if not c.excluded], key=Candidate.sort_key)
    rest = sorted([c for c in out if c.excluded], key=Candidate.sort_key)
    return picks + rest


# ── 근거 탭 체크리스트 (11/13) ──────────────────────────────────────────────────

def checklist(summary: dict | None, frow: dict | None, row, market: str,
              med_fpe: float | None) -> list[tuple[str, str, str]]:
    """[(상태 'pass'/'fail'/'unknown', 항목, 근거 글)] — 등으로 세지 않는 보조 확인."""
    gr = (summary or {}).get("gr") or {}
    f = (frow or {}).get("f") or {}
    out = []
    c30, c90 = f.get("c30"), f.get("c90")
    if c90 is None or c30 is None:
        out.append(("unknown", "추정 상향 지속", "30일 · 90일 추정 변화가 다 있어야 판정"))
    else:
        same = (c30 >= 0) == (c90 >= 0)
        out.append(("pass" if same and c90 >= 0 else "fail", "추정 상향 지속",
                    f"30일 {c30 * 100:+.1f}% · 90일 {c90 * 100:+.1f}%"
                    + (" — 방향이 엇갈림" if not same else "")))
    price = getattr(row, "price", None) if row is not None else None
    fpe, _g1, _pg = growth.peg(f, price)
    if fpe is None or med_fpe is None:
        out.append(("unknown", "가격 교차 확인 (선행 PER)", "선행 EPS 또는 가격 없음"))
    else:
        out.append(("pass" if fpe <= med_fpe else "fail", "가격 교차 확인 (선행 PER)",
                    f"선행 PER {fpe:.1f} · 품질 통과 종목 중앙값 {med_fpe:.1f}"))
    om3, om10 = gr.get("om3"), gr.get("om10")
    if om3 is None or om10 is None:
        out.append(("unknown", "마진 추세", "영업이익률 연도 부족 (다음 수집부터)"))
    else:
        out.append(("pass" if om3 >= om10 - growth.OM_TOL else "fail", "마진 추세",
                    f"영업이익률 최근 3년 {om3 * 100:.1f}% · 전체 평균 {om10 * 100:.1f}%"))
    td = gr.get("td")
    out.append(("unknown" if td is None else ("fail" if td else "pass"), "실적 추세",
                "연도 부족 (다음 수집부터)" if td is None else
                ("매출 · 영업이익 3년 연속 함께 감소" if td else "3년 연속 동반 감소 아님")))
    if market == "us":
        sbcf = gr.get("sbcf")
        out.append(("unknown" if sbcf is None else
                    ("pass" if sbcf <= growth.SBC_FCF_MAX else "fail"), "주식보상 부담",
                    "계정 없음 · FCF 마이너스" if sbcf is None else
                    f"3년 주식보상비 ÷ FCF {sbcf * 100:.0f}% (기준 {growth.SBC_FCF_MAX * 100:.0f}% 이하)"))
    p, k = growth.score(gr, market)
    out.append(("pass" if gr and growth.passes(gr, market) else ("unknown" if not gr else "fail"),
                "성장형 기준", f"7개 중 통과 {p} (판정 {k}) — 통과면 성장형 후보" if gr
                else "성장 지표 없음 (다음 수집부터)"))
    return out


def median_fpe(frows: dict, chart_rows: dict, tickers) -> float | None:
    vals = []
    for t in tickers:
        row = chart_rows.get(t)
        fpe, _g, _p = growth.peg((frows.get(t) or {}).get("f"),
                                 getattr(row, "price", None) if row is not None else None)
        if fpe is not None and 0 < fpe < 200:
            vals.append(fpe)
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


# ── 내 종목 기준 점검 (11/13) — 찾기와 같은 기준을 보유 · 관심 종목에 ─────────────

def assess(summary: dict | None, frow: dict | None, row, market: str,
           name: str = "", ticker: str = "") -> Candidate:
    """한 종목의 등(품질 · 가격 · 선행 EPS)과 '점검 필요' 이유 (flags → notes['flags']).

    점검 필요 = **나빠지는 신호만** — 선행 EPS 90일 −5% 이하(추정이 깎이는 중) · 실적
    추세 악화(매출 · 영업이익 3년 연속 감소). 품질 미달 · 가격 부담 높음은 원래 그런
    상태(사이클 업종 · 대형 성장주)라 등 색으로만 보입니다 — 11/13 실측: 관심종목 12개
    중 11개가 '점검 필요' 로 떠서 경고가 뜻을 잃었음. 매도 신호가 아니라 공시를 다시
    읽어 볼 이유입니다.
    품질 심사 대상이 아니면(지수 밖 · ETF) 등은 '없음' 이고 점검 항목도 없습니다.
    """
    sc = buffett.from_summary(summary) if summary else None
    t = ticker or (sc.ticker if sc else "")
    c = Candidate(ticker=t, name=name or (sc.name if sc else t))
    if sc is None or not sc.ok:
        for k in ("quality", "price", "eps"):
            c.lamps[k], c.notes[k] = GRAY, "심사 대상 아님 (지수 밖 · ETF · 재무 없음)"
        c.notes["flags"] = ""
        return c
    fr = frow or {}
    c.lamps["quality"], c.notes["quality"] = _quality(sc, market)
    if fr:
        c.lamps["price"], c.notes["price"] = _price(fr)
        c.lamps["eps"], c.notes["eps"] = _eps(fr.get("f"))
    else:
        c.lamps["price"], c.notes["price"] = GRAY, "가격 계산 대상 아님 (품질 6개 기준 미만)"
        c.lamps["eps"], c.notes["eps"] = GRAY, "추정 없음 (계산 대상 아님)"
    chart_col, c.notes["chart"] = _chart(row)
    c.timing = chart_col == GREEN
    gr = (summary or {}).get("gr") or {}
    flags = []
    if funnel.eps_down(fr.get("f")):
        flags.append(f"선행 EPS 90일 {fr['f']['c90'] * 100:+.1f}%")
    if gr.get("td"):
        flags.append("실적 추세 악화 (매출 · 영업이익 3년 연속 감소)")
    c.notes["flags"] = " · ".join(flags)
    c.also = growth.passes(gr, market)            # 성장형 기준 통과 (꼬리표용)
    c.excluded = c.notes["flags"]
    return c
