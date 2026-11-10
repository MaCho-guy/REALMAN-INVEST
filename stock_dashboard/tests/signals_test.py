"""
변화 감지 로직 테스트 (네트워크 불필요).

실행:
    cd stock_dashboard
    python tests/signals_test.py

검증 범위: 각 신호 유형의 발생 조건과 미발생 조건, 심각도 정렬,
           프롬프트 내용, 뉴스 대상 선별, EDGAR 컬럼→행 변환·폼 분류.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signals as sig_mod  # noqa: E402
from analysis_store import AnalysisDoc  # noqa: E402
from config import Instrument  # noqa: E402
from sources.edgar import Filing, _rows_from_recent  # noqa: E402
from sources.model import Quote  # noqa: E402

FAILURES: list[str] = []
TODAY = dt.date.today()


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def ago(n: int) -> str:
    return (TODAY - dt.timedelta(days=n)).isoformat()


def ahead(n: int) -> str:
    return (TODAY + dt.timedelta(days=n)).isoformat()


MU = Instrument("Micron", "MU", "yahoo", "NASDAQ", "USD",
                verified=True, analysis_key="MU")
AAPL = Instrument("Apple", "AAPL", "yahoo", "NASDAQ", "USD",
                  verified=True, analysis_key="AAPL")

TH = sig_mod.Thresholds()


def quote(price=100.0, prev=100.0, **extra) -> Quote:
    return Quote(symbol="MU", price=price, prev_close=prev,
                 currency="USD", extra=extra)


def doc(generated: str = "", kinds: tuple[str, ...] = ()) -> AnalysisDoc:
    d = AnalysisDoc(key="MU", generated=generated)
    d.html = {k: "<div>x</div>" for k in kinds}
    return d


def kinds_of(found) -> list[str]:
    return [s.kind for s in found]


print("=== 신규 공시 감지 ===")
f_new = [Filing("10-Q", ago(3), ago(10), "acc-1", "mu.htm", cik=723125)]
found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc(ago(40), ("decoder",))},
                       {"MU": f_new}, thresholds=TH)
filing_sigs = [s for s in found if s.kind == "new_filing"]
check("분석보다 새 공시면 감지", len(filing_sigs) == 1)
check("30일 이내는 심각도 3", filing_sigs[0].severity == 3, str(filing_sigs[0].severity))
check("공시 링크 포함", "sec.gov" in filing_sigs[0].url, filing_sigs[0].url)
check("프롬프트에 폼·날짜", "10-Q" in filing_sigs[0].prompt and ago(3) in filing_sigs[0].prompt)
check("프롬프트에 기존 분석 생성일", ago(40) in filing_sigs[0].prompt)
check("뉴스 대상으로 표시", filing_sigs[0].wants_news)

found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc(ago(1), ("decoder",))},
                       {"MU": f_new}, thresholds=TH)
check("분석이 공시보다 최신이면 미감지",
      not [s for s in found if s.kind == "new_filing"])

f_old = [Filing("10-Q", ago(200), "", "acc-2", "x.htm", cik=1)]
found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc(ago(10), ("decoder",))},
                       {"MU": f_old}, thresholds=TH)
check("오래된 공시는 미감지", not [s for s in found if s.kind == "new_filing"])

f_minor = [Filing("4", ago(2), "", "acc-3", "x.htm", cik=1)]
found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc(ago(40), ("decoder",))},
                       {"MU": f_minor}, thresholds=TH)
check("중요도 1 폼(내부자 거래)은 신호 아님",
      not [s for s in found if s.kind == "new_filing"])

found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc()},
                       {"MU": f_new}, thresholds=TH)
check("분석이 아예 없으면 공시 전부가 '최신'",
      len([s for s in found if s.kind == "new_filing"]) == 1)

print("\n=== 실적 발표 임박 ===")
found = sig_mod.detect([MU], {"MU": quote(earnings_date=ahead(3))},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
es = [s for s in found if s.kind == "earnings_soon"]
check("D-3 감지", len(es) == 1 and "D-3" in es[0].title, es[0].title if es else "")
check("5일 이내는 심각도 3", es and es[0].severity == 3)

found = sig_mod.detect([MU], {"MU": quote(earnings_date=ahead(10))},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
es = [s for s in found if s.kind == "earnings_soon"]
check("6~14일은 심각도 2", es and es[0].severity == 2)

for days, label in ((30, "임계값 밖"), (-5, "이미 지난 발표")):
    found = sig_mod.detect([MU], {"MU": quote(earnings_date=ahead(days))},
                           {"MU": doc(ago(10), ("decoder", "story", "price"))},
                           {}, thresholds=TH)
    check(f"{label}({days}일) 미감지",
          not [s for s in found if s.kind == "earnings_soon"])

print("\n=== 분석 노후화 / 미생성 ===")
found = sig_mod.detect([MU], {"MU": quote()}, {"MU": doc()}, {}, thresholds=TH)
check("분석 없음 감지", "never" in kinds_of(found))
check("미생성 프롬프트에 해독기 명령",
      "/company-decoder-korean" in [s for s in found if s.kind == "never"][0].prompt)

found = sig_mod.detect([MU], {"MU": quote()},
                       {"MU": doc(ago(120), ("decoder", "story", "price"))}, {}, thresholds=TH)
st_sigs = [s for s in found if s.kind == "stale"]
check("90일 초과 노후화 감지", len(st_sigs) == 1 and "120일" in st_sigs[0].title,
      st_sigs[0].title if st_sigs else "")

found = sig_mod.detect([MU], {"MU": quote()},
                       {"MU": doc(ago(30), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("최근 생성 + 3종 완비면 신호 없음", not found, str(kinds_of(found)))

found = sig_mod.detect([MU], {"MU": quote()},
                       {"MU": doc(ago(30), ("decoder",))}, {}, thresholds=TH)
part = [s for s in found if s.kind == "partial"]
check("일부 미생성 감지", len(part) == 1, str(kinds_of(found)))
check("미생성 종류 표기", part and "기업 스토리" in part[0].title
      and "가격 판독" in part[0].title, part[0].title if part else "")
check("'분석 없음' 과 다른 kind 로 분리",
      not [s for s in found if s.kind == "never"])

print("\n=== 급등락 ===")
found = sig_mod.detect([MU], {"MU": quote(price=93.0, prev=100.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
mv = [s for s in found if s.kind == "move"]
check("-7% 감지", len(mv) == 1 and "-7.0%" in mv[0].title, mv[0].title if mv else "")
check("뉴스 대상으로 표시", mv and mv[0].wants_news)
check("프롬프트가 원인을 묻는다", mv and "원인" in mv[0].prompt)

found = sig_mod.detect([MU], {"MU": quote(price=97.0, prev=100.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("-3% 는 임계값 미달", not [s for s in found if s.kind == "move"])

found = sig_mod.detect([MU], {"MU": quote(price=90.0, prev=100.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
mv = [s for s in found if s.kind == "move"]
check("-10% 는 심각도 3", mv and mv[0].severity == 3)

print("\n=== 52주 위치 ===")
cases = [
    ("고점 대비 -40%", {"high_52w": 100.0, "low_52w": 30.0}, 60.0, "낙폭"),
    ("52주 최고가 근처", {"high_52w": 101.0, "low_52w": 50.0}, 100.0, "신고가"),
    ("52주 최저가 근처", {"high_52w": 200.0, "low_52w": 99.0}, 100.0, "신저가"),
]
for label, extra, price, tag in cases:
    found = sig_mod.detect([MU], {"MU": quote(price=price, prev=price, **extra)},
                           {"MU": doc(ago(10), ("decoder", "story", "price"))},
                           {}, thresholds=TH)
    ex = [s for s in found if s.kind == "extreme" and tag in s.tags]
    check(f"{label} → '{tag}' 신호", len(ex) >= 1,
          str([s.title for s in found if s.kind == "extreme"]))

found = sig_mod.detect([MU], {"MU": quote(price=70.0, prev=70.0,
                                          high_52w=100.0, low_52w=50.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("고점 -30% 는 낙폭 신호 (심각도 2 미만)",
      any(s.kind == "extreme" and s.severity <= 2 for s in found))

found = sig_mod.detect([MU], {"MU": quote(price=80.0, prev=80.0,
                                          high_52w=100.0, low_52w=50.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("고점 -20% 는 신호 없음", not found, str([s.title for s in found]))

print("\n=== 결측 입력 ===")
found = sig_mod.detect([MU], {}, {"MU": doc(ago(10), ("decoder", "story", "price"))},
                       {}, thresholds=TH)
check("시세 없어도 예외 없음", isinstance(found, list))
found = sig_mod.detect([MU], {"MU": Quote.failed("MU", "x")},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("실패한 시세는 가격 신호 미발생",
      not [s for s in found if s.kind in ("move", "extreme", "earnings_soon")])
found = sig_mod.detect([MU], {"MU": quote(price=100.0, prev=0.0)},
                       {"MU": doc(ago(10), ("decoder", "story", "price"))}, {}, thresholds=TH)
check("전일종가 0 이면 등락 신호 없음", not [s for s in found if s.kind == "move"])
check("빈 종목 목록", sig_mod.detect([], {}, {}, {}, thresholds=TH) == [])

print("\n=== 정렬과 집계 ===")
many = sig_mod.detect(
    [MU, AAPL],
    {"MU": quote(price=90.0, prev=100.0, high_52w=200.0, low_52w=50.0,
                 earnings_date=ahead(2)),
     "AAPL": Quote(symbol="AAPL", price=100.0, prev_close=100.0, currency="USD",
                   extra={"high_52w": 101.0, "low_52w": 50.0})},
    {"MU": doc(ago(200), ("decoder",)), "AAPL": doc()},
    {"MU": [Filing("10-K", ago(2), "", "a", "x.htm", cik=1)]},
    thresholds=TH,
)
sevs = [s.severity for s in many]
check("심각도 내림차순 정렬", sevs == sorted(sevs, reverse=True), str(sevs))
counts = sig_mod.summarize(many)
check("집계 합계 일치", sum(counts.values()) == len(many),
      f"{counts} vs {len(many)}")

print("\n=== 뉴스 대상 선별 ===")
targets = sig_mod.news_targets(many, limit=4)
check("공시·급등락 종목만", all(t[0] in ("MU", "AAPL") for t in targets), str(targets))
check("종목당 1회만", len({t[0] for t in targets}) == len(targets))
check("MU 포함 (공시+급락)", any(t[0] == "MU" for t in targets))
only_stale = sig_mod.detect([AAPL], {}, {"AAPL": doc(ago(200), ("decoder",))},
                            {}, thresholds=TH)
check("노후화만 있으면 뉴스 안 붙임", sig_mod.news_targets(only_stale) == [],
      str(sig_mod.news_targets(only_stale)))
check("상한 적용", len(sig_mod.news_targets(many, limit=1)) <= 1)

print("\n=== 묶기 (받은편지함 범람 방지) ===")


def never_sig(name: str) -> sig_mod.Signal:
    inst = Instrument(name, name, "yahoo", analysis_key=name)
    return sig_mod.Signal(kind="never", severity=1, inst=inst,
                          title="분석 없음", prompt="x", tags=["미생성"])


for n, expect_agg in ((1, False), (2, False), (3, True), (9, True)):
    group = [never_sig(f"T{i}") for i in range(n)]
    merged = sig_mod.collapse(group)
    aggs = [s for s in merged if s.aggregate]
    if expect_agg:
        check(f"{n}건 → 묶음 1건", len(merged) == 1 and len(aggs) == 1, str(len(merged)))
        check(f"{n}건 묶음 제목에 개수", f"{n}종목" in aggs[0].title, aggs[0].title)
        check(f"{n}건 묶음에 종목 목록", len(aggs[0].members) == n)
        check(f"{n}건 묶음 count 속성", aggs[0].count == n)
    else:
        check(f"{n}건 이하는 묶지 않음", len(merged) == n and not aggs, str(len(merged)))

high = sig_mod.Signal(kind="never", severity=3, inst=never_sig("X").inst, title="t")
mixed = sig_mod.collapse([never_sig(f"T{i}") for i in range(5)] + [high])
check("심각도 2 이상은 묶이지 않음",
      any(s.severity == 3 and not s.aggregate for s in mixed))
check("묶음과 개별이 공존", len(mixed) == 2, str(len(mixed)))

diff_kinds = sig_mod.collapse(
    [never_sig(f"A{i}") for i in range(3)]
    + [sig_mod.Signal(kind="partial", severity=1, inst=never_sig(f"B{i}").inst,
                      title="일부", tags=["미생성"]) for i in range(3)]
)
check("종류가 다르면 따로 묶임", len(diff_kinds) == 2, str([s.kind for s in diff_kinds]))

bulk_prompt = [s for s in sig_mod.collapse([never_sig(f"T{i}") for i in range(4)])][0].prompt
check("묶음 프롬프트가 우선순위를 묻는다", "우선순위" in bulk_prompt)
check("묶음 프롬프트에 종목 전부", all(f"T{i}" in bulk_prompt for i in range(4)))

print("\n=== 긴급도 분리 ===")
pool = [
    sig_mod.Signal(kind="move", severity=3, inst=MU, title="a"),
    sig_mod.Signal(kind="stale", severity=2, inst=MU, title="b"),
    sig_mod.Signal(kind="never", severity=1, inst=MU, title="c"),
    sig_mod.Signal(kind="extreme", severity=1, inst=MU, title="d"),
]
urgent, fyi = sig_mod.split_by_urgency(pool)
check("긴급 = 심각도 2 이상", len(urgent) == 2 and all(s.severity >= 2 for s in urgent))
check("참고 = 심각도 1", len(fyi) == 2 and all(s.severity < 2 for s in fyi))
check("합이 원본과 같음", len(urgent) + len(fyi) == len(pool))
check("빈 입력", sig_mod.split_by_urgency([]) == ([], []))

print("\n=== 실제 구성에서 노이즈 억제 확인 ===")
import config as cfg  # noqa: E402

many_insts = list(cfg.SECTION_WATCHLIST.instruments)
no_analysis = {i.analysis_key: AnalysisDoc(key=i.analysis_key)
               for i in many_insts if i.analysis_key}
flood = sig_mod.detect(many_insts, {}, no_analysis, {}, thresholds=TH)
check(f"9종목 전부 분석 없음 → 카드 1건 ({len(flood)}건)", len(flood) == 1, str(len(flood)))
check("그 1건이 묶음", flood and flood[0].aggregate)

print("\n=== EDGAR 컬럼→행 변환 ===")
recent = {
    "form": ["10-Q", "8-K", "4"],
    "filingDate": ["2026-11-02", "2026-10-28", "2026-10-20"],
    "reportDate": ["2026-09-30", "2026-10-28", ""],
    "accessionNumber": ["a-1", "a-2", "a-3"],
    "primaryDocument": ["q.htm", "k.htm", "f.htm"],
    "items": ["", "2.02,9.01", ""],
}
rows = _rows_from_recent(recent)
check("행 개수", len(rows) == 3, str(len(rows)))
check("첫 행 매핑", rows[0]["form"] == "10-Q" and rows[0]["accessionNumber"] == "a-1")
check("빈 dict 처리", _rows_from_recent({}) == [])
check("길이 불일치는 짧은 쪽 기준",
      len(_rows_from_recent({"form": ["a", "b"], "filingDate": ["x"]})) == 1)

print("\n=== Filing 속성 ===")
f = Filing("8-K", ago(5), ago(5), "0000723125-26-000029", "mu-8k.htm",
           items="2.02,9.01", cik=723125)
check("한국어 라벨", f.label == "수시보고 (주요 사건)", f.label)
check("중요도 2", f.importance == 2)
check("URL 에 accession 하이픈 제거", "000072312526000029" in f.url, f.url)
check("경과일 계산", f.days_ago == 5, str(f.days_ago))
check("primary_doc 없으면 인덱스 페이지",
      "-index.htm" in Filing("8-K", ago(1), "", "a-b-c", "", cik=1).url)
check("모르는 폼은 중요도 1", Filing("XYZ", ago(1), "", "a", "x", cik=1).importance == 1)

print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
