"""
판단 재료 요약 — 추천 대신 지도를 줍니다.

**추천하지 않는 이유는 규칙 때문만이 아닙니다.**
"삼성전자 사세요" 는 왜 그런지 설명이 안 되면 따라갈 수 없고, 설명이 되면
추천이 필요 없습니다. 그래서 두 축을 교차해 **지금 어디에 서 있는지**만
보여주고, 결론은 비워둡니다.

    가로축: 사업의 질     — 버핏식 숫자 기준 몇 개를 통과했나
    세로축: 가격의 기대   — 현재 가격이 요구하는 성장률 vs 과거 실제

                        요구 < 과거 실제        요구 > 과거 실제
    기준 많이 통과   ① 둘 다 설명됨           ② 사업은 통과, 가격에 기대
    기준 적게 통과   ③ 가격은 낮지만 사업 의문  ④ 둘 다 확인 필요

①~④ 는 **좋고 나쁨의 순서가 아닙니다.** ①이 항상 좋은 것도 아닙니다 —
시장이 알고 있는 위험을 가격에 반영했을 수 있습니다. 네 칸은 "다음에 무엇을
확인해야 하는가" 가 다를 뿐입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config
import funnel
import reverse_dcf as rdcf


@dataclass
class Verdict:
    """한 종목의 판단 재료. 결론 필드가 없는 것이 의도입니다."""

    ticker: str
    name: str = ""

    #: 사업의 질 — (통과 수, 전체, 판정 불가 수)
    passed: int = 0
    total: int = 0
    unknown: int = 0

    #: 가격의 기대
    implied_growth: float | None = None
    historical_growth: float | None = None
    historical_span: int | None = None
    growth_band: str = ""

    #: ① ~ ④, 또는 판정 불가면 0
    quadrant: int = 0
    #: 가격 축의 판정 — 'light' 낮음 · 'edge' 경계 · 'heavy' 높음 · 'na' 판정 안 함.
    #: 종목 발굴 깔때기와 **같은 규칙**(funnel.price_state)입니다.
    price_state: str = "na"
    #: 2026-11-12 이전 규칙(할인율 10% 하나 · 과거 성장률은 시작 · 끝 두 해 · 주식보상비용
    #: 미차감)이었다면의 사분면. -1 = 계산하지 않음. 규칙을 바꾼 영향을 화면에 보이려고 둡니다.
    prev_quadrant: int = -1
    #: 예전 규칙의 숫자 (요구 성장률 · 과거 성장률) — 왜 위치가 바뀌었는지 보이려고
    prev_implied: float | None = None
    prev_hist: float | None = None
    #: 할인율 12% 일 때의 요구 성장률 (경계 판정의 근거)
    band_hi: float | None = None

    @property
    def price_word(self) -> str:
        return {"light": "낮음", "edge": "경계", "heavy": "높음"}.get(self.price_state, "판정 안 함")

    @property
    def price_reason(self) -> str:
        """가격 판정의 근거 한 줄 — 카드 맨 위에 적습니다 (2026-11-12 "카드를 열어도
        경계 · 상한이 안 나온다": 주의 문구는 해당할 때만 붙어서, 근거가 늘 보이지 않았습니다)."""
        if self.price_state == "na":
            return (self.dcf_error.split("\n")[0][:60] if self.dcf_error
                    else "과거 성장률을 계산할 수 없습니다")
        cap = config.FUNNEL_HIST_GROWTH_CAP
        text = f"요구 연 {self.implied_growth * 100:,.1f}%"
        if self.band_hi is not None:
            text += f" (할인율 12%면 {self.band_hi * 100:,.1f}%)"
        text += f" · 과거 연 {self.historical_growth * 100:,.1f}%"
        if self.historical_growth > cap:
            text += f" → {cap * 100:g}%까지만 인정"
        return text

    @property
    def moved_reason(self) -> str:
        """규칙을 바꿔 위치가 달라졌으면 예전 규칙의 숫자 한 줄, 아니면 ''."""
        if self.prev_quadrant < 0 or self.prev_quadrant == self.quadrant:
            return ""
        mark = {0: "판정 안 함", 1: "①", 2: "②", 3: "③", 4: "④"}
        text = f"예전 규칙에서는 {mark[self.prev_quadrant]}"
        if self.prev_implied is not None and self.prev_hist is not None:
            text += (f" — 요구 연 {self.prev_implied * 100:,.1f}% · 과거 연 "
                     f"{self.prev_hist * 100:,.1f}% (할인율 10%만 · 시작 해와 끝 해)")
        return text

    #: 통과·탈락한 기준 이름
    passed_names: list[str] = field(default_factory=list)
    failed_names: list[str] = field(default_factory=list)
    unknown_names: list[str] = field(default_factory=list)

    #: 다음에 확인할 것 — 사분면에 따라 달라집니다
    next_checks: list[str] = field(default_factory=list)
    #: 이 요약을 그대로 믿기 어려운 이유
    caveats: list[str] = field(default_factory=list)

    dcf_error: str = ""

    @property
    def gap(self) -> float | None:
        if self.implied_growth is None or self.historical_growth is None:
            return None
        return self.implied_growth - self.historical_growth

    @property
    def quality_label(self) -> str:
        base = f"{self.passed}/{self.total} 통과"
        return base + (f" · 판정 불가 {self.unknown}" if self.unknown else "")

    @property
    def price_label(self) -> str:
        if self.implied_growth is None:
            return "역DCF 적용 불가"
        text = f"요구 연 {self.implied_growth * 100:,.1f}%"
        if self.historical_growth is not None:
            text += f" vs 과거 {self.historical_growth * 100:,.1f}%"
        return text


QUADRANT_TITLE = {
    1: "① 사업 기준 통과 · 가격이 과거 성장 범위 안",
    2: "② 사업 기준 통과 · 가격에 과거보다 높은 기대",
    3: "③ 가격 기대는 낮음 · 사업 기준은 미달",
    4: "④ 사업 기준 미달 · 가격에도 높은 기대",
    0: "사분면 판정 불가",
}

QUADRANT_MEANING = {
    1: "숫자상으로는 사업도 기준을 넘고, 가격도 과거 실적으로 설명되는 "
       "범위에 있습니다. **그래도 좋은 투자라는 뜻은 아닙니다** — 시장이 "
       "알고 있는 위험을 가격에 반영했을 가능성을 먼저 배제해야 합니다.",
    2: "사업의 과거 실적은 기준을 넘지만, 현재 가격은 과거보다 빠른 성장을 "
       "전제합니다. **그 전제가 공시로 뒷받침되는지**가 판단의 핵심입니다.",
    3: "가격에 들어간 기대는 과거보다 낮지만, 사업 기준에서 걸린 항목이 "
       "있습니다. **걸린 항목이 업종 구조인지 기업 고유 문제인지**를 "
       "구분해야 합니다 — 업종 구조면 기준이 부적절한 것입니다.",
    4: "사업 기준도 미달이고 가격에도 높은 기대가 들어있습니다. "
       "**둘 중 하나는 제 기준이나 모델이 이 기업에 맞지 않는다는 신호**일 "
       "수 있으니, 결론을 내리기 전에 왜 그런지부터 봐야 합니다.",
    0: "역DCF 를 적용할 수 없어 가격 축을 세울 수 없습니다. "
       "사업 기준 결과만으로 판단해야 합니다.",
}

NEXT_CHECKS = {
    1: [
        "시장이 이미 아는 위험이 있는지 — 최근 10-K 의 Risk Factors 에서 "
        "새로 추가되거나 표현이 강해진 항목",
        "경제적 해자가 실제로 있는지 — 가격을 올려도 고객이 떠나지 않을 이유",
        "경영진이 유보이익을 어디에 썼고 그 결정이 결과로 정당화됐는지",
    ],
    2: [
        "가격이 전제한 성장의 근거가 공시에 있는지 — 신제품·구조적 수요 변화·"
        "마진 개선 중 무엇이고, 경영진이 그걸 가이던스로 제시했는지",
        "과거 가이던스를 실제로 달성해온 이력이 있는지 (스토리 분석)",
        "그 성장이 멈추면 가격이 어디까지 설명되는지 — 요구 성장률을 "
        "과거 실적 수준으로 낮췄을 때의 가치",
    ],
    3: [
        "탈락한 기준이 업종 구조 때문인지 — 같은 업종 경쟁사도 같은 기준에서 "
        "걸리는지 비교",
        "숫자가 나쁜 구간이 일회성인지 구조적인지 — 해당 연도의 공시 설명",
        "가격 기대가 낮은 이유가 시장의 합리적 우려인지 과도한 비관인지",
    ],
    4: [
        "제 기준이 이 업종에 맞는지부터 — 기준별 통과율에서 이 기준이 "
        "거의 모두를 떨어뜨리고 있다면 기준 문제입니다",
        "역DCF 의 FCF 기준값이 타당한지 — 사이클 업종이면 평균 처리가 "
        "결과를 왜곡했을 수 있습니다",
        "이 기업을 아예 후보에서 빼도 되는지, 아니면 다른 틀로 봐야 하는지",
    ],
    0: [
        "역DCF 가 안 되는 이유 — 적자, 사이클 왜곡, 순현금 과다 중 무엇인지",
        "현금흐름이 불규칙한 업종이면 지표체계(레이어 1~4)로 국면을 먼저 판정",
        "사업 기준에서 통과한 항목만으로 읽을 가치가 있는지",
    ],
}


def legacy_quadrant(passed: int, threshold: int, dcf) -> int:
    """예전 규칙의 사분면 — 할인율 10% 에서 요구 성장률 ≤ 과거(시작 · 끝 두 해)면 낮음."""
    gap = dcf.gap if dcf is not None and dcf.ok else None
    if gap is None:
        return 0
    if passed >= threshold:
        return 1 if gap <= 0 else 2
    return 3 if gap <= 0 else 4


def build(screen, dcf: rdcf.Result | None, *,
          quality_threshold: int | None = None, financial: bool = False,
          legacy_dcf: rdcf.Result | None = None) -> Verdict:
    """스크리닝 결과 + 역DCF 를 하나의 판단 재료로 묶습니다.

    quality_threshold: 사업 축의 기준선. 기본은 전체의 3분의 2.
    """
    total = len(screen.checks)
    threshold = (quality_threshold if quality_threshold is not None
                 else max(1, round(total * 2 / 3)))

    v = Verdict(
        ticker=screen.ticker,
        name=screen.name,
        passed=screen.passed_count,
        total=total,
        unknown=screen.unknown_count,
        passed_names=[c.criterion.name for c in screen.checks if c.passed],
        failed_names=[c.criterion.name for c in screen.checks
                      if c.verdict == "fail"],
        unknown_names=[c.criterion.name for c in screen.checks if not c.known],
    )

    # 가격 축 — 2026-11-12 부터 종목 발굴 깔때기와 같은 규칙(funnel.py)으로 봅니다.
    # 전에는 할인율 10% 하나 · 과거 성장률은 시작 해와 끝 해 두 점이었습니다.
    band_hi = None
    if financial:
        v.dcf_error = "금융업 — FCF 기반 역DCF 를 적용하지 않습니다."
    elif dcf is not None and dcf.ok:
        v.implied_growth = dcf.implied_growth
        v.growth_band = dcf.band_label
        trend, tspan = funnel.trend_growth(dcf.inputs.fcf_history)
        span = dcf.gap_span
        if tspan is not None:                # 6년치 이상 — 앞 3년 평균 → 뒤 3년 평균
            v.historical_growth, v.historical_span = trend, tspan
        elif span is not None:
            v.historical_growth = dcf.historical_cagr[span]
            v.historical_span = span
        band = [x for x in dcf.sensitivity.values() if x is not None]
        band_hi = max(band) if len(band) >= 2 else None
        v.band_hi = band_hi
    elif dcf is not None:
        v.dcf_error = dcf.error
    v.price_state = funnel.price_state(
        {"g": v.implied_growth, "h": v.historical_growth, "hi": band_hi})

    # 사분면 — '낮음' 은 할인율 8~12% 전 구간에서 요구 ≤ 과거(상한까지)일 때만
    quality_ok = v.passed >= threshold
    if v.price_state == "na":
        v.quadrant = 0
    elif quality_ok and v.price_state == "light":
        v.quadrant = 1
    elif quality_ok:
        v.quadrant = 2
    elif v.price_state == "light":
        v.quadrant = 3
    else:
        v.quadrant = 4

    if legacy_dcf is not None:
        v.prev_quadrant = legacy_quadrant(v.passed, threshold, legacy_dcf)
        if legacy_dcf.ok and legacy_dcf.gap_span is not None:
            v.prev_implied = legacy_dcf.implied_growth
            v.prev_hist = legacy_dcf.historical_cagr[legacy_dcf.gap_span]

    v.next_checks = list(NEXT_CHECKS[v.quadrant])
    if v.failed_names and v.quadrant in (1, 2):
        v.next_checks.append(
            f"통과했지만 걸린 항목({', '.join(v.failed_names)})이 "
            "이 업종에서 구조적인지"
        )

    # 이 요약을 그대로 믿기 어려운 이유들
    cap = config.FUNNEL_HIST_GROWTH_CAP
    if v.price_state == "edge" and band_hi is not None:
        v.caveats.append(
            f"**가격은 '경계' 입니다.** 할인율 10% 에서는 요구 성장률이 과거 성장률 이하지만, "
            f"12% 로 보면 연 {band_hi * 100:,.1f}% 가 되어 넘습니다 — '부담 낮음' 으로 세지 않았습니다."
        )
    if v.historical_growth is not None and v.historical_growth > cap:
        v.caveats.append(
            f"과거 FCF 성장률 연 {v.historical_growth * 100:,.1f}% 는 **연 {cap * 100:g}% 까지만** "
            "인정했습니다 — 과거의 고성장이 그대로 이어진다고 보지 않습니다."
        )
    if v.unknown:
        v.caveats.append(
            f"기준 {v.unknown}개는 **판정 불가**입니다 "
            f"({', '.join(v.unknown_names)}) — 공시에 해당 계정이 없습니다. "
            "통과도 탈락도 아니므로 점수를 그대로 비교하면 안 됩니다."
        )
    if dcf is not None and getattr(dcf, "severe_distortion", False):
        v.caveats.append(
            "**가격 축을 신뢰할 수 없습니다.** 역DCF 의 FCF 기준값이 최근 "
            "실적의 절반 미만으로 깎였습니다(사이클 왜곡) — 요구 성장률이 "
            "실제보다 크게 높게 나옵니다. 이 종목의 사분면 위치는 "
            "참고만 하십시오."
        )
    elif dcf is not None and dcf.normalized:
        v.caveats.append(
            "역DCF 의 FCF 기준값을 **3년 평균으로 바꿨습니다** — 최근 실적이 "
            "구조적으로 개선된 경우라면 요구 성장률이 과대평가됩니다."
        )
    if dcf is not None and dcf.ok and dcf.inputs.net_debt is None:
        v.caveats.append(
            "순부채를 계산하지 못해 시가총액을 기업가치로 대신 썼습니다 — "
            "현금이 많은 기업은 요구 성장률이 과대평가됩니다."
        )
    if v.historical_growth is None and v.implied_growth is not None:
        v.caveats.append(
            "과거 FCF 성장률이 계산되지 않아(적자 연도 포함) 격차를 "
            "낼 수 없었습니다."
        )
    return v


def summary_lines(v: Verdict) -> list[str]:
    """화면과 프롬프트에 함께 쓰는 요약. 결론 문장은 없습니다."""
    lines = [
        f"**사업의 질** — {v.quality_label}.",
    ]
    if v.passed_names:
        lines.append(f"통과: {', '.join(v.passed_names)}.")
    if v.failed_names:
        lines.append(f"걸린 항목: {', '.join(v.failed_names)}.")

    if v.implied_growth is not None:
        text = (f"**가격의 기대** — 현재 가격은 향후 10년 FCF "
                f"연 {v.implied_growth * 100:,.1f}% 성장을 요구합니다")
        if v.growth_band and v.growth_band != "—":
            text += f" (할인율 8~12% 구간에서 {v.growth_band})"
        lines.append(text + ".")
        if v.historical_growth is not None:
            lines.append(
                f"과거 {v.historical_span}년 실제는 연 "
                f"{v.historical_growth * 100:,.1f}% 였고, 격차는 "
                f"**{v.gap * 100:+,.1f}%p** 입니다."
            )
    else:
        lines.append(f"**가격의 기대** — {v.dcf_error or '역DCF 적용 불가'}")

    lines.append(f"**위치** — {QUADRANT_TITLE[v.quadrant]}")
    lines.append(QUADRANT_MEANING[v.quadrant])
    return lines


def prompt_for(v: Verdict, screen) -> str:
    """Claude 에 붙여넣을 질문. 숫자는 여기 다 넣고, 판단은 요청하지 않습니다."""
    lines = [
        f"{v.ticker} ({v.name}) 의 숫자를 정리했습니다. "
        "공시를 근거로 확인해 주십시오.",
        "",
        "[숫자]",
    ]
    lines += [f"- {ln.replace('**', '')}" for ln in summary_lines(v)]

    if v.caveats:
        lines += ["", "[이 숫자의 한계]"]
        lines += [f"- {c.replace('**', '')}" for c in v.caveats]

    lines += ["", "[확인하고 싶은 것]"]
    for i, item in enumerate(v.next_checks, 1):
        lines.append(f"{i}. {item}")

    lines += [
        "",
        "공시(10-K·10-Q·사업보고서·어닝콜)에 있는 내용만으로 답해 주시고, "
        "자료에서 확인할 수 없는 것은 그렇다고 말해 주십시오.",
        "매수/매도 추천, 목표주가, 단기 주가 방향은 필요 없습니다 — "
        "판단 재료만 정리해 주십시오.",
    ]
    return "\n".join(lines)
