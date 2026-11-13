"""차트 전략 백테스트 (2026-11-13) — 가격 · 거래량만 쓰므로 과거 1년 일봉으로 바로 돌려 봅니다.

사용자 아이디어(11/13 15:17): "거래량이 점차 커지는 종목인데 CCI 과매도 구간 탈출 시도 및
−DMI 30 아래로 진입 → 그쯤 매수해서 CCI 과매수 구간 및 −DMI 10 이하로 갈 때까지 보유 →
매도는 CCI 과매수 꺼지고 −DMI 다시 상승하려고 할 때". 거래량은 OBV 로(15:25).

규칙 (지표 정의는 chart_signals 와 같음 — CCI(13), DMI(14)):
  매수  ① CCI '과매도 탈출 시도'(−100 아래에서 전일보다 오름) 또는 '과매도 탈출'(최근 3봉
        안에 −100 위로, 아직 0 아래)  ② −DI 가 최근 3봉 안에 30 을 아래로 지남
        ③ 거래량: OBV 가 10일 평균 위 · 5일 전보다 높음 (변형 A_vol 은 5일 ÷ 20일 거래량
        ≥ 1.2배 · 5일 평균 3일 연속 증가)  — 셋 다 맞는 날 종가
  대기  보유 중 CCI ≥ +100 그리고 −DI ≤ ARM(10)
  매도  대기 뒤 CCI 가 +100 아래로 · −DI 가 전일보다 오름 — 그날 종가
  안전  손절 −8%(종가) · 매수 후 20봉 안에 대기 못 가면 정리 · 최대 40봉
  비용  왕복 0.25% 차감
변형:
  A      위 규칙 (OBV)
  A_vol  거래량을 OBV 대신 거래량 배수로 (비교용)
  A15    대기 조건 −DI ≤ 15 (10 은 드물 수 있어 비교)
  A5     대기 조건을 '같은 날' 대신 '최근 5봉 안에 CCI ≥ +100 · −DI ≤ 10 이 각각 한 번씩'으로
  B      A + ADX 꺾임(최근 3봉 전보다 낮음 — 하락 추세의 힘이 빠지는 중)
  C      B + 펀더멘털 필터(품질 통과 · 보류, 선행 EPS 90일 −5% 초과) — **오늘의 재무로
         과거 신호를 거르므로 미리 보기 편향이 있음** (참고용)
비교  '시장' = 같은 날짜들의 후보 전체 동일 비중 평균(일별 수익률 평균을 누적) — 지수
      대신 후보 전체를 씀(같은 종목군 안에서 신호가 나은지 보려고).
한계  1년치 일봉(앞 30봉은 지표 준비) → 실제 검증 약 10개월 · 한 장세에 쏠릴 수 있음.
"""
from __future__ import annotations

import chart_signals as cs

COST = 0.0025
STOP = 0.08
ARM_WAIT = 20
MAX_HOLD = 40
WARMUP = 30
VARIANTS = ("A", "A_vol", "A15", "A5", "B", "C")
LABELS = {"A": "A · OBV (기본)", "A_vol": "A · 거래량 배수", "A15": "A · 대기 −DI 15", "A5": "A · 대기 5봉 창",
          "B": "B · A + ADX 꺾임", "C": "C · B + 펀더멘털(참고)"}


def _obv(close, vol):
    out = [0.0]
    for i in range(1, len(close)):
        v = vol[i] or 0.0
        out.append(out[-1] + (v if close[i] > close[i - 1] else -v if close[i] < close[i - 1] else 0.0))
    return out


def indicators(bars: dict) -> dict | None:
    h, l, c = bars.get("high") or [], bars.get("low") or [], bars.get("close") or []
    v = bars.get("volume") or []
    n = len(c)
    if n < WARMUP + 10 or len(h) != n or len(l) != n:
        return None
    if any(x is None for x in c[-n:]) or any(x is None for x in h) or any(x is None for x in l):
        return None
    v = (list(v) + [0.0] * n)[:n]
    pdi, mdi, adx = cs.dmi(h, l, c)
    return {"c": c, "cci": cs.cci_series(h, l, c), "pdi": pdi, "mdi": mdi, "adx": adx,
            "obv": _obv(c, v), "vol": [x or 0.0 for x in v],
            "date": (bars.get("date") or [""] * n)[:n], "n": n}


def _ok(*xs):
    return all(x is not None for x in xs)


def _cci_escape(cci, i):
    cur, prev = cci[i], cci[i - 1]
    if not _ok(cur, prev):
        return False
    if cur <= cs.CCI_OVERSOLD and cur > prev:
        return True                                   # 과매도 탈출 시도
    if cs.CCI_OVERSOLD < cur < 0:                     # 과매도 탈출 (최근 3봉 안에 −100 위로)
        for j in range(max(1, i - 2), i + 1):
            if _ok(cci[j], cci[j - 1]) and cci[j - 1] <= cs.CCI_OVERSOLD < cci[j]:
                return True
    return False


def _mdi_cross30(mdi, i):
    for j in range(max(1, i - 2), i + 1):
        if _ok(mdi[j], mdi[j - 1]) and mdi[j - 1] >= 30.0 > mdi[j]:
            return True
    return False


def _obv_up(ind, i):
    o = ind["obv"]
    if i < 10:
        return False
    return o[i] > sum(o[i - 9:i + 1]) / 10.0 and o[i] > o[i - 5]


def _vol_up(ind, i):
    v = ind["vol"]
    if i < 22:
        return False
    a5 = [sum(v[k - 4:k + 1]) / 5.0 for k in (i - 2, i - 1, i)]
    a20 = sum(v[i - 19:i + 1]) / 20.0
    return a20 > 0 and a5[-1] / a20 >= 1.2 and a5[0] < a5[1] < a5[2]


def entry(ind: dict, i: int, variant: str) -> bool:
    if not (_cci_escape(ind["cci"], i) and _mdi_cross30(ind["mdi"], i)):
        return False
    if not (_vol_up(ind, i) if variant == "A_vol" else _obv_up(ind, i)):
        return False
    if variant in ("B", "C"):
        a = ind["adx"]
        if not (i >= 3 and _ok(a[i], a[i - 3]) and a[i] < a[i - 3]):
            return False
    return True


def _armed(cci, mdi, k, lvl, win):
    """대기 — 최근 win 봉 안에 CCI ≥ +100 한 번 · −DI ≤ lvl 한 번 (win=1 이면 같은 날)."""
    lo = max(0, k - win + 1)
    return (any(x is not None and x >= cs.CCI_OVERBOUGHT for x in cci[lo:k + 1])
            and any(x is not None and x <= lvl for x in mdi[lo:k + 1]))


def trades(ind: dict, variant: str) -> list[dict]:
    """한 종목의 거래 목록 — {i0, i1, p0, p1, why, open}."""
    arm_lvl = 15.0 if variant == "A15" else 10.0
    c, cci, mdi, n = ind["c"], ind["cci"], ind["mdi"], ind["n"]
    out, i = [], WARMUP
    while i < n:
        if not entry(ind, i, variant):
            i += 1
            continue
        p0, armed, k, why = c[i], False, i + 1, ""
        while k < n:
            if c[k] <= p0 * (1 - STOP):
                why = "손절 −8%"
                break
            if not armed and _armed(cci, mdi, k, arm_lvl, 5 if variant == "A5" else 1):
                armed = True
            elif armed and _ok(cci[k], mdi[k], mdi[k - 1]) and cci[k] < cs.CCI_OVERBOUGHT \
                    and mdi[k] > mdi[k - 1]:
                why = "매도 신호"
                break
            if not armed and k - i >= ARM_WAIT:
                why = "대기 못 감 (20봉)"
                break
            if k - i >= MAX_HOLD:
                why = "기간 만료 (40봉)"
                break
            k += 1
        if k >= n:
            out.append({"i0": i, "i1": n - 1, "p0": p0, "p1": c[-1], "why": "보유 중", "open": True})
            break
        out.append({"i0": i, "i1": k, "p0": p0, "p1": c[k], "why": why, "open": False})
        i = k + 1
    return out


def _ew_index(inds: dict) -> dict:
    """{날짜: 누적 지수} — 후보 전체 일별 수익률 평균을 누적 (동일 비중 시장)."""
    by_day: dict[str, list[float]] = {}
    for ind in inds.values():
        c, d = ind["c"], ind["date"]
        for i in range(1, ind["n"]):
            if d[i] and c[i - 1]:
                by_day.setdefault(d[i], []).append(c[i] / c[i - 1] - 1.0)
    idx, lvl = {}, 1.0
    for day in sorted(by_day):
        r = by_day[day]
        lvl *= 1.0 + sum(r) / len(r)
        idx[day] = lvl
    return idx


def run(bars_by_sym: dict, names: dict | None = None, allowed: set | None = None) -> dict:
    """시장 하나 — {variants: {이름: 요약}, signals: {A: [...], C: [...]}, window}."""
    names = names or {}
    inds = {s: x for s, x in ((s, indicators(b)) for s, b in bars_by_sym.items()) if x}
    idx = _ew_index(inds)
    out = {"n_syms": len(inds), "variants": {}, "signals": {}}
    days = sorted(idx)
    if days:
        out["window"] = {"from": days[min(WARMUP, len(days) - 1)], "to": days[-1]}
    for var in VARIANTS:
        rows = []
        for s, ind in inds.items():
            if var == "C" and (allowed is None or s not in allowed):
                continue
            for t in trades(ind, var):
                d0, d1 = ind["date"][t["i0"]], ind["date"][t["i1"]]
                r = t["p1"] / t["p0"] - 1.0 - (0.0 if t["open"] else COST)
                b = (idx[d1] / idx[d0] - 1.0) if d0 in idx and d1 in idx else None
                rows.append({"s": s, "n": names.get(s, s), "d0": d0, "d1": d1,
                             "p0": round(t["p0"], 4), "p1": round(t["p1"], 4), "r": round(r, 4),
                             "b": None if b is None else round(b, 4), "hold": t["i1"] - t["i0"],
                             "why": t["why"], "open": int(t["open"])})
        closed = [x for x in rows if not x["open"]]
        rs = sorted(x["r"] for x in closed)
        ex = [x["r"] - x["b"] for x in closed if x["b"] is not None]
        whys: dict[str, int] = {}
        for x in closed:
            whys[x["why"]] = whys.get(x["why"], 0) + 1
        out["variants"][var] = {
            "trades": len(closed), "open": len(rows) - len(closed),
            "win": round(sum(1 for r in rs if r > 0) / len(rs), 3) if rs else None,
            "avg": round(sum(rs) / len(rs), 4) if rs else None,
            "med": rs[len(rs) // 2] if rs else None,
            "best": rs[-1] if rs else None, "worst": rs[0] if rs else None,
            "excess": round(sum(ex) / len(ex), 4) if ex else None,
            "hold": round(sum(x["hold"] for x in closed) / len(closed), 1) if closed else None,
            "why": whys,
            "recent": sorted(rows, key=lambda x: x["d0"])[-15:],
        }
        if var in ("A", "C"):
            sig = []
            for s, ind in inds.items():
                if var == "C" and (allowed is None or s not in allowed):
                    continue
                if entry(ind, ind["n"] - 1, var):
                    sig.append({"s": s, "n": names.get(s, s), "p": ind["c"][-1],
                                "d": ind["date"][-1]})
            out["signals"][var] = sig
    return out
