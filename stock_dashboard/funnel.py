"""
발굴 깔때기 — 품질 → 가격(역DCF 요구 성장률) → 차트 조건.

2026-11-12 사용자 요청: "종목이 너무 많은데 효율적으로 볼 방법이 없을까 — 밸류에이션
이랑 차트 조건까지 다 적용하려면 너무 무거울 것 같은데". 세 검사는 바뀌는 주기와
비용이 달라서, **전 종목에 다 돌리지 않고 좁혀 가며** 겁니다.

  ① 품질      연간 재무 — 1년에 한 번 바뀜. 전 종목(약 516). universe_us.json
  ② 가격      주가가 매일 바뀜. **①을 통과한 종목만**. 재무(FCF · 순부채)는 ①에서
              이미 받은 것을 쓰고 시가총액만 새로 받습니다.
  ③ 차트      일봉이 매일 바뀜. **①을 통과한 종목만** 일봉 1건씩.

②③은 수집기가 미리 계산해 funnel_us.json 으로 올리고, 화면은 읽기만 합니다.

'가격 부담 낮음' 의 정의 (사용자 지정: 역DCF 요구 성장률):
    현재 주가가 요구하는 FCF 성장률 ≤ 과거 실제 FCF 성장률

2026-11-12 점검에서 드러난 약점 넷을 고친 규칙입니다 (사용자: "더 낫고 합리적인
방향이면 그렇게 진행"). 밸류에이션 탭(verdict.py)은 아직 예전 규칙입니다.
  · 할인율 — 10% 하나로 판정하면 '낮음' 40종목 중 22종목이 8% · 12% 에서 결론이
    바뀌었습니다. **8~12% 전 구간에서 성립할 때만** '낮음' 이고, 10% 에서만
    성립하면 '경계' 입니다.
  · 금융업 — FCF 기반 역DCF 가 성립하지 않습니다 (예금 · 대출이 영업현금흐름에
    섞임). 판정하지 않고 '해당 없음' 으로 둡니다.
  · 과거 성장률 — 시작 해와 끝 해 두 점이 아니라 **앞 3년 평균 → 뒤 3년 평균**.
    한 해의 일회성 항목에 덜 흔들립니다. 6년치가 안 되면 예전 방식(두 점).
  · 주식보상비용 — FCF 에서 뺍니다 (dcf_inputs). 계정이 없는 회사는 못 뺍니다.
과거 성장률은 상한(config.FUNNEL_HIST_GROWTH_CAP)까지만 인정하고, FCF 기준값이
사이클로 크게 왜곡된 종목은 숫자가 나와도 '낮음' 으로 세지 않습니다.

'차트 조건' 은 차트 조건 탭의 **과매도 쪽**(CCI · 스토캐스틱 · 볼린저 %B)입니다.

이 목록은 '살 종목' 이 아니라 '공시를 읽어볼 순서' 입니다.
"""
from __future__ import annotations

import config
import reverse_dcf as rdcf


def dcf_inputs(screen) -> dict | None:
    """심사 직후(10년 숫자가 메모리에 있을 때) 역DCF 입력만 추려 둡니다.

    {"f": [[연도, FCF], …], "nd": 순부채(없으면 None), "end": 재무 기준일}.
    FCF 를 한 해도 못 만들면 None — 가격 단계에서 '판정 불가' 가 됩니다.
    """
    hist, sbc_years = [], 0
    for row in screen.years:
        fcf = row.free_cash_flow
        if fcf is None:
            continue
        sbc = getattr(row, "sbc", None)
        if sbc is not None and sbc > 0:
            fcf -= sbc                       # 주식으로 준 급여는 주주의 비용
            sbc_years += 1
        hist.append([row.year, round(fcf)])
    latest = screen.latest
    if not hist or latest is None:
        return None
    nd = latest.net_debt
    out = {"f": hist, "nd": round(nd) if nd is not None else None, "end": latest.end}
    if sbc_years:
        out["sbc"] = sbc_years               # 주식보상비용을 뺀 연도 수
    return out


def trend_growth(history) -> tuple[float | None, int | None]:
    """과거 FCF 성장률 — 앞 3년 평균에서 뒤 3년 평균까지의 연평균 (값, 기간).

    두 점(시작 해 · 끝 해)으로 재면 한 해의 일회성 항목이 10년 성장률을 통째로
    바꿉니다. 6년치가 안 되거나 어느 쪽 평균이 0 이하면 (None, 기간).
    """
    vals = [float(v) for _y, v in sorted(history)]
    n = len(vals)
    if n < 6:
        return None, None
    a, b, span = sum(vals[:3]) / 3, sum(vals[-3:]) / 3, n - 3
    if a <= 0 or b <= 0:
        return None, span
    return (b / a) ** (1 / span) - 1, span


def price_part(ticker: str, d: dict, cap: float | None, *, financial: bool = False) -> dict:
    """역DCF 한 종목 — 요구 성장률 · 과거 성장률 · 격차.

    g: 요구 성장률(소수) · h: 과거 FCF 연평균 성장률 · sp: 그 기간(년) ·
    gap: g − h · lo/hi: 할인율 8~12% 일 때의 요구 성장률 범위 ·
    norm: FCF 기준값을 3년 평균으로 바꿨는가 · sev: 기준값이 크게 왜곡됐는가 ·
    e: 계산하지 못한 이유.
    """
    if financial:
        return {"cap": cap, "na": "금융업 — FCF 기반 역DCF 를 적용하지 않습니다"}
    res = rdcf.run(rdcf.Inputs(
        ticker=ticker, market_cap=float(cap or 0.0), net_debt=d.get("nd"),
        fcf_history=[(int(y), float(v)) for y, v in (d.get("f") or [])]))
    span = res.gap_span
    band = [v for v in res.sensitivity.values() if v is not None]
    hist = res.historical_cagr.get(span) if span is not None else None
    how = "ends"
    trend, tspan = trend_growth(d.get("f") or [])
    if tspan is not None:                    # 6년치 이상 — 앞 · 뒤 3년 평균으로
        hist, span, how = trend, tspan, "avg3"
    out = {
        "cap": cap, "g": res.implied_growth,
        "h": hist, "hk": how, "sbc": bool(d.get("sbc")),
        "sp": span, "gap": (res.implied_growth - hist
                            if res.implied_growth is not None and hist is not None else None),
        "lo": min(band) if len(band) >= 2 else None,
        "hi": max(band) if len(band) >= 2 else None,
        "norm": bool(res.normalized), "sev": bool(res.severe_distortion),
        "nd": d.get("nd") is not None,
    }
    if res.error:
        out["e"] = res.error.split("\n")[0][:160]
    return out


def chart_part(row) -> dict:
    """차트 조건 한 종목 — 쪽 · 지표별 상태 · 마지막 봉."""
    if not row.ok:
        return {"e": (row.error or f"일봉이 {row.bars}개뿐입니다")[:120]}
    st = {k: v for k, v in row.states.items() if v}
    cloud = row.ichi.bullish_cloud
    if cloud is not None:
        st["cloud"] = "양운" if cloud else "음운"
    return {"side": row.side, "st": st, "bar": row.last_bar, "p": row.price}


def hist_ref(p: dict | None, cap: float | None = None) -> float | None:
    """비교에 쓰는 과거 성장률 — 실제 값과 상한 가운데 작은 쪽 (없으면 None)."""
    if not p or p.get("h") is None:
        return None
    cap = config.FUNNEL_HIST_GROWTH_CAP if cap is None else cap
    return min(p["h"], cap)


def price_state(p: dict | None, cap: float | None = None) -> str:
    """'light' 낮음 · 'edge' 경계 · 'heavy' 높음 · 'na' 판정하지 않음.

    낮음 = 할인율 8~12% **전 구간**에서 요구 성장률 ≤ 과거 성장률(상한까지).
    경계 = 기준 할인율(10%)에서는 성립하지만 12% 에서는 아님.
    """
    ref = hist_ref(p, cap)
    if not p or p.get("na") or ref is None or p.get("g") is None or p.get("sev"):
        return "na"
    if p["g"] > ref:
        return "heavy"
    hi = p.get("hi")
    return "light" if hi is None or hi <= ref else "edge"


def price_gap(p: dict | None, cap: float | None = None) -> float | None:
    """요구 성장률 − 비교에 쓴 과거 성장률(상한까지) — 소수. 플러스면 주가가 과거보다
    더 빠른 성장을 요구한다는 뜻. 판정하지 않는 종목이면 None. (2026-11-13: '높음' 의
    이유를 숫자로)"""
    ref = hist_ref(p, cap)
    if price_state(p, cap) == "na" or ref is None:
        return None
    return p["g"] - ref


def gap_text(p: dict | None) -> str:
    """'요구가 과거보다 +6.2%p' / '과거보다 −3.1%p 여유' — 판정 안 하면 ''."""
    gp = price_gap(p)
    if gp is None:
        return ""
    if gp > 0:
        return f"요구가 과거보다 +{gp * 100:,.1f}%p"
    return f"과거보다 {gp * 100:,.1f}%p 여유"


def quality_tickers(screens, market: str) -> set:
    """품질 통과 티커 — 깔때기 화면과 '오늘 볼 종목' 이 같은 규칙을 쓰게 (2026-11-13).

    screens: universe.to_summary 묶음(dict) 또는 Screen. 티커는 야후 표기(BRK-B)로.
    예전에는 오늘 볼 종목이 깔때기 파일의 줄 전부(= 미리 계산해 두는 6개 기준 이상)를
    '품질 통과' 로 써서, 화면 깔때기(미국 130 · 한국 23)보다 넓은 목록(189 · 55)에서
    골랐습니다.
    """
    import buffett  # noqa: PLC0415

    out = set()
    for s in screens or []:
        sc = buffett.from_summary(s) if isinstance(s, dict) else s
        if sc is not None and buffett.quality_pass(sc, market):
            out.add(str(sc.ticker).replace(".", "-"))
    return out


def eps_down(f: dict | None) -> bool:
    """선행 EPS 90일 변화가 경고선(config.EPS_DOWN_WARN) 이하."""
    c = (f or {}).get("c90")
    return c is not None and c <= config.EPS_DOWN_WARN


def breakdown(rows: list) -> dict:
    """품질 통과 종목들의 가격 · 선행 EPS 내역 — rows = 깔때기 줄({f, p, c}) 목록.

    {"light","edge","heavy","na", "eps_up","eps_flat","eps_down","eps_warn","eps_none"}.
    """
    out = {k: 0 for k in ("light", "edge", "heavy", "na", "eps_up", "eps_flat",
                          "eps_down", "eps_warn", "eps_none")}
    for r in rows:
        r = r or {}
        out[price_state(r.get("p"))] += 1
        c = (r.get("f") or {}).get("c90")
        if c is None:
            out["eps_none"] += 1
        elif c >= EPS_FLAT:
            out["eps_up"] += 1
        elif c <= -EPS_FLAT:
            out["eps_down"] += 1
        else:
            out["eps_flat"] += 1
        if eps_down(r.get("f")):
            out["eps_warn"] += 1
    return out


def breakdown_text(b: dict, n: int) -> str:
    """내역 한 줄(HTML) — '품질 통과 33 중 가격: 낮음 9 · 경계 4 · 높음 10 · 판정 안 함 10 /
    선행 EPS: 상향 12 · 보합 3 · 하향 9 (−5% 이하 4) · 추정 없음 9'."""
    return (f"<b>품질 통과 {n}종목의 내역</b> — 가격: 낮음 {b['light']} · 경계 {b['edge']} · "
            f"높음 {b['heavy']} · 판정 안 함 {b['na']} / 선행 EPS 90일: 상향 {b['eps_up']} · "
            f"보합 {b['eps_flat']} · 하향 {b['eps_down']}"
            + (f" (−{abs(config.EPS_DOWN_WARN) * 100:g}% 이하 {b['eps_warn']})"
               if b["eps_warn"] else "")
            + f" · 추정 없음 {b['eps_none']}")


def is_light(p: dict | None, cap: float | None = None) -> bool:
    """가격 부담 낮음 (price_state == 'light')."""
    return price_state(p, cap) == "light"


def price_known(p: dict | None) -> bool:
    return price_state(p) != "na"


def is_oversold(c: dict | None) -> bool:
    """차트 조건 — 과매도 쪽."""
    return bool(c) and c.get("side") == "os"


def pct(v) -> str:
    return "—" if v is None else f"연 {v * 100:,.1f}%"


def price_cells(p: dict | None) -> tuple[str, str]:
    """(값, 보조 줄) — 표의 '요구 성장률' 칸."""
    if not p:
        return "—", ""
    if p.get("na"):
        return "해당 없음", "금융업"
    if p.get("g") is None:
        return "—", "역DCF 적용 불가" if p.get("e") else ""
    note = (f"과거 {pct(p.get('h'))} · {p.get('sp')}년" if p.get("h") is not None
            else "과거 성장률 계산 불가")
    state = price_state(p)
    if state == "edge" and p.get("hi") is not None:
        note = f"경계 — 할인율 12% 면 {pct(p['hi'])} · " + note
    elif state == "light":
        note = "낮음 · " + note
    elif state == "heavy":
        note = f"높음 — {gap_text(p)} · " + note
    if p.get("h") is not None and p["h"] > config.FUNNEL_HIST_GROWTH_CAP:
        note += f" → 상한 {pct(config.FUNNEL_HIST_GROWTH_CAP)} 적용"
    if p.get("sev"):
        note += " · 기준값 왜곡 큼"
    elif p.get("norm"):
        note += " · 3년 평균 기준"
    return pct(p["g"]), note


def chart_cell(c: dict | None, names: dict | None = None) -> str:
    """표의 '차트' 칸 — 쪽과 그 근거 상태."""
    if not c or c.get("e"):
        return "—"
    side = {"os": "과매도 쪽", "ob": "과매수 쪽", "mixed": "엇갈림"}.get(c.get("side") or "", "")
    st = c.get("st") or {}
    why = " · ".join(f"{(names or {}).get(k, k)} {v}" for k, v in st.items()
                     if k in ("cci", "stoch", "bb"))
    cloud = st.get("cloud", "")
    parts = [x for x in (side, why, cloud) if x]
    return " · ".join(parts) if parts else "해당 없음"


# ── 선행 EPS 상승세 ──────────────────────────────────────────────────────────
#
# 2026-11-12 사용자: "Forward EPS 상승세를 먼저 보고 싶다 — 향후 12개월 선행 EPS,
# 기준 기간 90일". 애널리스트 평균 추정치가 90일 사이 올랐는지(상향) 내렸는지(하향).
#
# 향후 12개월(NTM) EPS 는 야후가 따로 주지 않아 올해 · 내년 회계연도 추정치를 섞습니다:
#     NTM = w × 올해 + (1 − w) × 내년,   w = 올해 회계연도가 끝날 때까지 남은 달 ÷ 12
# 90일 전 값도 **같은 w** 로 섞습니다 — 날짜가 흘러 내년 비중이 커진 효과를 빼고,
# 추정치 자체가 바뀐 것만 보려는 것입니다.

#: 이 크기(소수) 미만의 변화는 '보합' 으로 적습니다.
EPS_FLAT = 0.005


def eps_part(raw: dict | None, now: float | None = None) -> dict | None:
    """야후 추정 추이 한 종목 → {n: NTM EPS, c90 · c30: 변화율(소수), w, cur}.

    추정치가 0 이하이면 변화율이 뜻을 잃어 c90 · c30 을 None 으로 둡니다.
    """
    import time as _time

    if not raw:
        return None
    now = _time.time() if now is None else now
    fye = raw.get("fye")
    w = 0.5 if not fye else max(0.0, min(1.0, (float(fye) - now) / (365.25 * 86400)))

    def blend(a, b):
        if a is None and b is None:
            return None
        if a is None or b is None:
            return a if b is None else b
        return w * a + (1.0 - w) * b

    n = blend(raw.get("e0"), raw.get("e1"))
    if n is None:
        return None

    def chg(old):
        return (n / old - 1.0) if old is not None and old > 0 and n > 0 else None

    return {"n": n, "c90": chg(blend(raw.get("p0"), raw.get("p1"))),
            "c30": chg(blend(raw.get("m0"), raw.get("m1"))),
            "w": round(w, 3), "cur": raw.get("cur") or ""}


def eps_arrow(c) -> str:
    if c is None:
        return ""
    return "▲" if c >= EPS_FLAT else ("▼" if c <= -EPS_FLAT else "→")


def eps_cells(f: dict | None) -> tuple[str, str]:
    """(값, 보조 줄) — 표의 '선행 EPS 90일' 칸."""
    if not f:
        return "—", ""
    c = f.get("c90")
    if c is None:
        return "—", f"추정 {f['n']:,.2f}" if f.get("n") is not None else ""
    note = f"추정 {f['n']:,.2f}"
    if f.get("c30") is not None:
        note += f" · 30일 {f['c30'] * 100:+,.1f}%"
    return f"{eps_arrow(c)} {c * 100:+,.1f}%", note


def eps_chip(f: dict | None) -> str:
    """판정 줄에 넣는 짧은 글 — '선행 EPS ▲ +3.2% (90일)'. 없으면 ''."""
    if not f or f.get("c90") is None:
        return ""
    return f"선행 EPS {eps_arrow(f['c90'])} {f['c90'] * 100:+,.1f}% (90일)"
