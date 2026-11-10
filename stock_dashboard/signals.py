"""
변화 감지 — 대시보드가 실제로 잘할 수 있는 일.

================================================================================
설계 원칙
================================================================================
장기투자자에게 필요한 건 뉴스 피드가 아니라 **"무엇이 달라졌는가"** 입니다.
그래서 이 모듈은 "주가가 얼마다"가 아니라 아래 질문에 답합니다:

  · 내 분석이 쓰인 뒤로 새 공시가 올라왔나?       (분석을 다시 돌릴 시점)
  · 실적 발표가 며칠 남았나?                      (미리 준비할 시점)
  · 마지막으로 들여다본 게 언제인가?              (방치된 종목)
  · 어제 비정상적으로 움직인 종목이 있나?         (원인을 찾아볼 시점)
  · 52주 범위에서 지금 어디인가?                  (사이클 위치)

각 신호는 **붙여넣기용 프롬프트**를 함께 들고 있습니다. 대시보드가 판단을
내리는 대신, 판단이 필요한 순간과 그때 물어볼 질문을 만들어 줍니다.

신호가 없으면 아무것도 표시하지 않습니다 — 없는 신호를 만들어내지 않습니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import analysis_store
from analysis_store import AnalysisDoc
from config import Instrument
from sources.edgar import Filing
from sources.model import Quote

# ──────────────────────────────────────────────────────────────────────────────
# 신호 종류 — (키, 라벨, 기본 심각도)
# 심각도: 3 = 지금 볼 것, 2 = 이번 주에 볼 것, 1 = 참고
# ──────────────────────────────────────────────────────────────────────────────

SEVERITY_LABEL = {3: "지금", 2: "이번 주", 1: "참고"}


@dataclass
class Signal:
    """감지된 변화 한 건."""

    kind: str                  # new_filing | earnings_soon | stale | never | partial | move | extreme
    severity: int              # 3 / 2 / 1
    inst: Instrument
    title: str                 # 한 줄 요약
    detail: str = ""           # 보충 설명
    url: str = ""              # 근거 링크 (공시 등)
    prompt: str = ""           # Claude 에 붙여넣을 질문
    tags: list[str] = field(default_factory=list)

    #: 뉴스를 붙일 가치가 있는 신호인가 (공시·급등락만)
    wants_news: bool = False

    #: 여러 종목을 하나로 묶은 신호인가
    aggregate: bool = False
    members: list[str] = field(default_factory=list)

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABEL.get(self.severity, "")

    @property
    def count(self) -> int:
        return len(self.members) if self.aggregate else 1


# ──────────────────────────────────────────────────────────────────────────────
# 임계값 — config 에서 덮어쓸 수 있습니다
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Thresholds:
    #: 하루 등락률 절댓값이 이 값을 넘으면 '급등락'
    move_pct: float = 5.0
    #: 52주 고점 대비 낙폭이 이 값을 넘으면 알림
    drawdown_pct: float = 25.0
    #: 52주 고/저점에서 이 비율 안에 있으면 '극단'
    extreme_pct: float = 3.0
    #: 실적 발표가 이 일수 안이면 알림
    earnings_days: int = 14
    #: 분석 생성 후 이 일수를 넘으면 노후화
    stale_days: int = 90


# ──────────────────────────────────────────────────────────────────────────────
# 프롬프트 생성
# ──────────────────────────────────────────────────────────────────────────────

def _skill_cmd(kind: str, name: str) -> str:
    return analysis_store.skill_command(kind, name, name)


def _prompt_new_filing(inst: Instrument, filings: list[Filing], doc: AnalysisDoc) -> str:
    listed = ", ".join(f"{f.form}({f.filing_date})" for f in filings[:4])
    base = doc.generated or "없음"
    return (
        f"{inst.name}({inst.analysis_key}) 에 새 공시가 올라왔습니다: {listed}\n"
        f"기존 분석 생성일: {base}\n\n"
        f"이 공시들을 반영해서 기존 분석 대비 **달라진 점 중심으로** 정리해 주세요. "
        f"특히 가이던스 변경, 리스크 요인 추가·삭제, 세그먼트별 추세 변화를 보고 싶습니다. "
        f"변화가 없으면 '변화 없음'이라고 해 주세요.\n\n"
        f"필요하면 {_skill_cmd('story', inst.name)} 를 돌려도 좋습니다."
    )


def _prompt_earnings(inst: Instrument, days: int, date_str: str) -> str:
    return (
        f"{inst.name}({inst.analysis_key}) 실적 발표가 {days}일 뒤({date_str})입니다.\n\n"
        f"이번 분기에 **무엇을 확인해야 하는지** 정리해 주세요. "
        f"직전 분기 가이던스가 무엇이었고, 컨센서스가 어디에 있고, "
        f"어떤 수치가 나오면 투자 논리가 깨지는지 알고 싶습니다."
    )


def _prompt_stale(inst: Instrument, days: int, doc: AnalysisDoc) -> str:
    missing = doc.missing_kinds
    if missing:
        cmds = "\n".join(_skill_cmd(k, inst.name) for k in missing)
        return (
            f"{inst.name}({inst.analysis_key}) 분석이 {days}일 전({doc.generated})에 "
            f"생성됐고, 아래가 아직 없습니다:\n{cmds}\n\n"
            f"그 사이 실적 발표가 있었다면 먼저 갱신이 필요합니다."
        )
    return (
        f"{inst.name}({inst.analysis_key}) 분석 3종이 모두 {days}일 전"
        f"({doc.generated})에 생성됐습니다.\n\n"
        f"그 사이 바뀐 게 있는지 확인하고, 필요하면 다시 돌려 주세요:\n"
        f"{_skill_cmd('story', inst.name)}"
    )


def _prompt_never(inst: Instrument) -> str:
    return (
        f"{inst.name}({inst.analysis_key}) 분석이 아직 없습니다.\n\n"
        f"{_skill_cmd('decoder', inst.name)}\n\n"
        f"10-K 나 사업보고서를 올리면 페이지 출처까지 달아 주세요."
    )


def _prompt_move(inst: Instrument, pct: float) -> str:
    direction = "올랐습니다" if pct > 0 else "빠졌습니다"
    return (
        f"{inst.name}({inst.analysis_key}) 가 하루에 {abs(pct):.1f}% {direction}.\n\n"
        f"공시나 업계 뉴스에 원인이 있는지 확인해 주세요. "
        f"기업 고유 사건인지, 업종 전체 움직임인지 구분해 주시면 좋겠습니다. "
        f"단순 수급이면 그렇다고 말해 주세요."
    )


def _prompt_extreme(inst: Instrument, kind: str, pct: float) -> str:
    if kind == "low":
        return (
            f"{inst.name}({inst.analysis_key}) 가 52주 최저가 근처입니다.\n\n"
            f"시장이 무엇을 걱정하고 있는지 알고 싶습니다. "
            f"공시된 리스크 요인 중 실제로 악화된 게 있는지 확인해 주세요."
        )
    if kind == "drawdown":
        return (
            f"{inst.name}({inst.analysis_key}) 가 52주 고점 대비 {pct:.0f}% 내려와 있습니다.\n\n"
            f"고점 이후 공시·실적에서 실제로 나빠진 게 있는지, 아니면 가격만 움직인 건지 "
            f"구분해 주세요."
        )
    return (
        f"{inst.name}({inst.analysis_key}) 가 52주 최고가 근처입니다.\n\n"
        f"지금 가격이 어떤 기대를 담고 있는지 보고 싶습니다:\n"
        f"{_skill_cmd('price', inst.name)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 감지
# ──────────────────────────────────────────────────────────────────────────────

def _parse_date(value: object) -> dt.date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    if isinstance(value, (int, float)) and value > 0:
        try:
            return dt.datetime.fromtimestamp(value, dt.timezone.utc).date()
        except (OSError, ValueError, OverflowError):
            return None
    return None


def _prompt_dio(inst: Instrument, trend) -> str:
    rising = trend.dio_rising_quarters
    latest = trend.latest
    dio_text = f"{latest.dio:.0f}일" if (latest and latest.dio) else "확인 필요"
    band = trend.dio_band
    band_text = f"{band[0]:.0f}~{band[2]:.0f}일" if band else "밴드 산출 불가"
    gap = trend.inventory_revenue_gap
    gap_text = f"{gap:+.1f}%포인트" if gap is not None else "확인 필요"

    return (
        f"{inst.name}({inst.symbol}) 재고 지표에서 사이클 전환 신호가 잡혔습니다.\n"
        f"· DIO {dio_text} ({rising}분기 연속 상승), 수집 구간 밴드 {band_text}\n"
        f"· 재고-매출 증가율 갭 {gap_text}\n\n"
        f"지표체계 v2 의 ②→③ 전환 체크리스트 관점에서 봐 주세요. "
        f"가격 레이어(현물-고정 스프레드)와 방향이 일치하는지, "
        f"재고 증가가 HBM 선계약 대응 물량인지 범용 재고 적체인지 구분이 필요합니다. "
        f"최근 분기보고서의 재고자산 주석과 어닝콜에서 근거를 찾아 주세요."
    )


def detect(
    instruments: list[Instrument],
    quotes: dict[str, Quote],
    docs: dict[str, AnalysisDoc],
    filings: dict[str, list[Filing]],
    *,
    thresholds: Thresholds | None = None,
    trends: dict[str, object] | None = None,
) -> list[Signal]:
    """모든 신호를 모아 심각도 높은 순으로 반환합니다.

    quotes  는 Instrument.symbol 로 조회 가능한 딕셔너리여야 합니다.
    filings 는 Instrument.analysis_key 기준이고, EDGAR Filing 과 DART Disclosure
            를 섞어 넣을 수 있습니다 (둘이 같은 속성을 제공합니다).
    trends  는 Instrument.symbol 기준의 InventoryTrend — 재고 신호용(선택).
    """
    th = thresholds or Thresholds()
    today = dt.date.today()
    out: list[Signal] = []
    trend_map = trends or {}

    for inst in instruments:
        key = inst.analysis_key or inst.symbol
        doc = docs.get(key) or AnalysisDoc(key=key)
        quote = quotes.get(inst.symbol)
        analysis_date = _parse_date(doc.generated)

        # ── 1) 분석보다 새로운 공시 ──────────────────────────────────────────
        inst_filings = filings.get(key) or []
        if inst_filings:
            if analysis_date is None:
                newer = [f for f in inst_filings if f.importance >= 2][:4]
            else:
                newer = [
                    f for f in inst_filings
                    if f.importance >= 2
                    and (_parse_date(f.filing_date) or today) > analysis_date
                ][:4]

            if newer:
                latest = newer[0]
                ago = latest.days_ago
                ago_text = f"{ago}일 전" if ago is not None else latest.filing_date
                out.append(Signal(
                    kind="new_filing",
                    severity=3 if (ago is not None and ago <= 30) else 2,
                    inst=inst,
                    title=f"새 공시 {len(newer)}건 — 분석보다 최신",
                    detail=(
                        f"가장 최근: {latest.form} ({latest.label}) · {ago_text}"
                        + (f" · 항목 {latest.items}" if latest.items else "")
                        + (f" · 기존 분석 {doc.generated}" if doc.generated else " · 분석 없음")
                    ),
                    url=latest.url,
                    prompt=_prompt_new_filing(inst, newer, doc),
                    tags=[f.form for f in newer],
                    wants_news=True,
                ))

        # ── 2) 실적 발표 임박 ────────────────────────────────────────────────
        if quote is not None and quote.ok:
            edate = _parse_date(quote.extra.get("earnings_date"))
            if edate is not None:
                days = (edate - today).days
                if 0 <= days <= th.earnings_days:
                    out.append(Signal(
                        kind="earnings_soon",
                        severity=3 if days <= 5 else 2,
                        inst=inst,
                        title=f"실적 발표 D-{days}" if days else "실적 발표 당일",
                        detail=f"{edate.isoformat()} 예정",
                        prompt=_prompt_earnings(inst, days, edate.isoformat()),
                        tags=["실적"],
                    ))

        # ── 3) 분석 없음 / 노후화 ────────────────────────────────────────────
        if doc.is_empty:
            out.append(Signal(
                kind="never",
                severity=1,
                inst=inst,
                title="분석 없음",
                detail="아직 한 번도 생성하지 않았습니다",
                prompt=_prompt_never(inst),
                tags=["미생성"],
            ))
        elif analysis_date is not None:
            age = (today - analysis_date).days
            if age > th.stale_days:
                out.append(Signal(
                    kind="stale",
                    severity=2,
                    inst=inst,
                    title=f"분석 노후화 — {age}일 경과",
                    detail=(
                        f"생성 {doc.generated}"
                        + (f" · 미생성 {len(doc.missing_kinds)}종" if doc.missing_kinds else "")
                    ),
                    prompt=_prompt_stale(inst, age, doc),
                    tags=["노후화"],
                ))
            elif doc.missing_kinds:
                missing = ", ".join(analysis_store.kind_label(k) for k in doc.missing_kinds)
                out.append(Signal(
                    kind="partial",
                    severity=1,
                    inst=inst,
                    title=f"분석 일부 미생성 — {missing}",
                    detail=f"생성된 것: "
                           + ", ".join(analysis_store.kind_label(k)
                                       for k in doc.available_kinds),
                    prompt=_prompt_never(inst),
                    tags=["미생성"],
                ))

        # ── 4) 급등락 ───────────────────────────────────────────────────────
        if quote is not None and quote.ok:
            pct = quote.change_pct
            if pct is not None and abs(pct) >= th.move_pct:
                out.append(Signal(
                    kind="move",
                    severity=3 if abs(pct) >= th.move_pct * 1.6 else 2,
                    inst=inst,
                    title=f"하루 {pct:+.1f}% 변동",
                    detail="임계값 "
                           f"±{th.move_pct:.0f}% 초과",
                    prompt=_prompt_move(inst, pct),
                    tags=["급등" if pct > 0 else "급락"],
                    wants_news=True,
                ))

            # ── 5) 52주 위치 ────────────────────────────────────────────────
            high = quote.extra.get("high_52w")
            low = quote.extra.get("low_52w")
            price = quote.price
            if price and isinstance(high, (int, float)) and high > 0:
                off_high = (1 - price / high) * 100
                if off_high >= th.drawdown_pct:
                    out.append(Signal(
                        kind="extreme",
                        severity=2 if off_high >= th.drawdown_pct * 1.5 else 1,
                        inst=inst,
                        title=f"52주 고점 대비 {off_high:.0f}% 하락",
                        detail=f"고점 {high:,.2f} · 현재 {price:,.2f}",
                        prompt=_prompt_extreme(inst, "drawdown", off_high),
                        tags=["낙폭"],
                    ))
                elif off_high <= th.extreme_pct:
                    out.append(Signal(
                        kind="extreme",
                        severity=1,
                        inst=inst,
                        title="52주 최고가 근처",
                        detail=f"고점 {high:,.2f} 대비 {off_high:.1f}%",
                        prompt=_prompt_extreme(inst, "high", off_high),
                        tags=["신고가"],
                    ))
            if price and isinstance(low, (int, float)) and low > 0:
                off_low = (price / low - 1) * 100
                if off_low <= th.extreme_pct:
                    out.append(Signal(
                        kind="extreme",
                        severity=2,
                        inst=inst,
                        title="52주 최저가 근처",
                        detail=f"저점 {low:,.2f} 대비 +{off_low:.1f}%",
                        prompt=_prompt_extreme(inst, "low", off_low),
                        tags=["신저가"],
                    ))

        # ── 6) 재고 지표 (레이어 2) ─────────────────────────────────────────
        trend = trend_map.get(inst.symbol)
        if trend is not None:
            rising = getattr(trend, "dio_rising_quarters", 0)
            gap = getattr(trend, "inventory_revenue_gap", None)
            latest_q = getattr(trend, "latest", None)
            dio = getattr(latest_q, "dio", None) if latest_q else None

            lit = []
            if rising >= 2:
                lit.append(f"DIO {rising}분기 연속 상승")
            if gap is not None and gap > 0:
                lit.append(f"재고-매출 갭 {gap:+.1f}%p")

            if lit:
                pos = getattr(trend, "dio_position", None)
                detail_bits = []
                if dio is not None:
                    detail_bits.append(f"DIO {dio:.0f}일")
                if pos is not None:
                    detail_bits.append(f"수집 밴드 내 {pos:.0f}% 위치")
                if latest_q is not None:
                    detail_bits.append(f"기준 {latest_q.label} 보고서")

                out.append(Signal(
                    kind="inventory",
                    severity=2 if len(lit) >= 2 else 1,
                    inst=inst,
                    title="재고 지표 — " + " · ".join(lit),
                    detail=" · ".join(detail_bits),
                    prompt=_prompt_dio(inst, trend),
                    tags=["재고", "사이클"],
                ))

    out.sort(key=lambda s: (-s.severity, s.inst.name, s.kind))
    return collapse(out)


# ──────────────────────────────────────────────────────────────────────────────
# 묶기 — 받은편지함이 범람하지 않게
# ──────────────────────────────────────────────────────────────────────────────

#: 종목마다 하나씩 뜨면 화면이 터지는 신호들. 심각도 1 일 때만 묶습니다.
#: '분석 없음' 은 9종목이면 9건이 되는데, 그건 알림이 아니라 할 일 목록입니다.
COLLAPSIBLE_KINDS = ("never", "partial", "extreme")

_COLLAPSE_TITLES = {
    "never": "분석 미생성",
    "partial": "분석 일부 미생성",
    "extreme": "52주 범위 특이 위치",
}


def _prompt_bulk(kind: str, group: list[Signal]) -> str:
    names = ", ".join(f"{s.inst.name}({s.inst.analysis_key or s.inst.symbol})"
                      for s in group)
    if kind in ("never", "partial"):
        first = group[0].inst
        return (
            f"아래 종목의 공시 분석이 아직 없거나 일부만 있습니다:\n{names}\n\n"
            f"어느 것부터 보는 게 좋을지 우선순위를 정해 주세요 — "
            f"보유 비중이나 다음 실적 발표 일정을 기준으로요. "
            f"그다음 첫 종목부터 돌리겠습니다:\n"
            f"{_skill_cmd('decoder', first.name)}"
        )
    return (
        f"아래 종목이 52주 범위에서 특이한 위치에 있습니다:\n"
        + "\n".join(f"· {s.inst.name}: {s.title} ({s.detail})" for s in group)
        + "\n\n이 중 가격만 움직인 것과 실제로 펀더멘털이 바뀐 것을 구분해 주세요."
    )


def collapse(signals: list[Signal],
             kinds: tuple[str, ...] = COLLAPSIBLE_KINDS) -> list[Signal]:
    """같은 종류의 심각도 1 신호를 종목 목록 하나로 합칩니다.

    2건 이하면 합치지 않습니다 — 묶는 게 오히려 정보를 가립니다.
    """
    keep: list[Signal] = []
    buckets: dict[str, list[Signal]] = {}

    for sig in signals:
        if sig.kind in kinds and sig.severity <= 1 and not sig.aggregate:
            buckets.setdefault(sig.kind, []).append(sig)
        else:
            keep.append(sig)

    for kind, group in buckets.items():
        if len(group) <= 2:
            keep.extend(group)
            continue
        names = [s.inst.name for s in group]
        keep.append(Signal(
            kind=kind,
            severity=1,
            inst=group[0].inst,
            title=f"{_COLLAPSE_TITLES.get(kind, kind)} {len(group)}종목",
            detail=", ".join(names),
            prompt=_prompt_bulk(kind, group),
            tags=sorted({t for s in group for t in s.tags})[:4],
            aggregate=True,
            members=names,
        ))

    keep.sort(key=lambda s: (-s.severity, not s.aggregate, s.inst.name, s.kind))
    return keep


def split_by_urgency(signals: list[Signal]) -> tuple[list[Signal], list[Signal]]:
    """(지금·이번 주, 참고) 로 나눕니다. 화면에서 참고는 접어 둡니다."""
    urgent = [s for s in signals if s.severity >= 2]
    fyi = [s for s in signals if s.severity < 2]
    return urgent, fyi


def news_targets(signals: list[Signal], *, limit: int = 4) -> list[tuple[str, str, str]]:
    """뉴스를 붙일 종목만 골라냅니다 — (심볼, 이름, 소스).

    공시·급등락 신호가 있는 종목만, 최대 limit 개. 이게 '뉴스는 보조'의 구현입니다.
    """
    seen: dict[str, tuple[str, str, str]] = {}
    for sig in signals:
        if not sig.wants_news:
            continue
        inst = sig.inst
        if inst.symbol in seen:
            continue
        seen[inst.symbol] = (inst.symbol, inst.name, inst.source)
        if len(seen) >= limit:
            break
    return list(seen.values())


def summarize(signals: list[Signal]) -> dict[str, int]:
    """심각도별 개수."""
    out = {"3": 0, "2": 0, "1": 0}
    for sig in signals:
        out[str(sig.severity)] = out.get(str(sig.severity), 0) + 1
    return out
