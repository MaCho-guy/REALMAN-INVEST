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
    현재 주가가 요구하는 FCF 성장률 ≤ 과거 실제 FCF 성장률 (가장 긴 기간)
밸류에이션 탭의 가격 축(verdict.py — gap ≤ 0)과 **같은 규칙**입니다. FCF 기준값이
사이클로 크게 왜곡된 종목은 숫자가 나와도 '낮음' 으로 세지 않습니다.

'차트 조건' 은 차트 조건 탭의 **과매도 쪽**(CCI · 스토캐스틱 · 볼린저 %B)입니다.

이 목록은 '살 종목' 이 아니라 '공시를 읽어볼 순서' 입니다.
"""
from __future__ import annotations

import reverse_dcf as rdcf


def dcf_inputs(screen) -> dict | None:
    """심사 직후(10년 숫자가 메모리에 있을 때) 역DCF 입력만 추려 둡니다.

    {"f": [[연도, FCF], …], "nd": 순부채(없으면 None), "end": 재무 기준일}.
    FCF 를 한 해도 못 만들면 None — 가격 단계에서 '판정 불가' 가 됩니다.
    """
    hist = [[row.year, round(row.free_cash_flow)] for row in screen.years
            if row.free_cash_flow is not None]
    latest = screen.latest
    if not hist or latest is None:
        return None
    nd = latest.net_debt
    return {"f": hist, "nd": round(nd) if nd is not None else None, "end": latest.end}


def price_part(ticker: str, d: dict, cap: float | None) -> dict:
    """역DCF 한 종목 — 요구 성장률 · 과거 성장률 · 격차.

    g: 요구 성장률(소수) · h: 과거 FCF 연평균 성장률 · sp: 그 기간(년) ·
    gap: g − h · lo/hi: 할인율 8~12% 일 때의 요구 성장률 범위 ·
    norm: FCF 기준값을 3년 평균으로 바꿨는가 · sev: 기준값이 크게 왜곡됐는가 ·
    e: 계산하지 못한 이유.
    """
    res = rdcf.run(rdcf.Inputs(
        ticker=ticker, market_cap=float(cap or 0.0), net_debt=d.get("nd"),
        fcf_history=[(int(y), float(v)) for y, v in (d.get("f") or [])]))
    span = res.gap_span
    band = [v for v in res.sensitivity.values() if v is not None]
    out = {
        "cap": cap, "g": res.implied_growth,
        "h": res.historical_cagr.get(span) if span is not None else None,
        "sp": span, "gap": res.gap,
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


def is_light(p: dict | None) -> bool:
    """가격 부담 낮음 — 요구 성장률 ≤ 과거 실제 성장률 (왜곡이 큰 종목 제외)."""
    return bool(p) and p.get("gap") is not None and p["gap"] <= 0 and not p.get("sev")


def price_known(p: dict | None) -> bool:
    return bool(p) and p.get("gap") is not None and not p.get("sev")


def is_oversold(c: dict | None) -> bool:
    """차트 조건 — 과매도 쪽."""
    return bool(c) and c.get("side") == "os"


def pct(v) -> str:
    return "—" if v is None else f"연 {v * 100:,.1f}%"


def price_cells(p: dict | None) -> tuple[str, str]:
    """(값, 보조 줄) — 표의 '요구 성장률' 칸."""
    if not p:
        return "—", ""
    if p.get("g") is None:
        return "—", "역DCF 적용 불가" if p.get("e") else ""
    note = (f"과거 {pct(p.get('h'))} · {p.get('sp')}년" if p.get("h") is not None
            else "과거 성장률 계산 불가")
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
