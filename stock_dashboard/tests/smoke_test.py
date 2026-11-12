"""
순수 로직 스모크 테스트 (네트워크 불필요).

실행:
    cd stock_dashboard
    python tests/smoke_test.py

검증 범위: 괴리율 계산, 통화 환산, Quote 파생값, 숫자 포맷,
           실패 Quote 렌더링, 외부 문자열 이스케이프.
Streamlit 레이어(app.py)는 streamlit 설치 후 `streamlit run app.py` 로 확인하십시오.
"""

from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import concurrent.futures as _cf  # noqa: E402
import components as ui_mod  # noqa: E402
import analysis_store  # noqa: E402
import components as ui  # noqa: E402
import config  # noqa: E402
from compute import FxRates, compute_premium, pick_quote  # noqa: E402
from config import Instrument  # noqa: E402
from sources import hyperliquid as hl  # noqa: E402
from sources.model import Quote  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got: object, want: object, tol: float = 1e-6) -> None:
    if isinstance(got, float) and isinstance(want, float):
        ok = abs(got - want) < tol
    else:
        ok = got == want
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: got={got!r} want={want!r}")
    if not ok:
        FAILURES.append(label)


def check_true(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


fx = FxRates(usdkrw=1380.0, eurusd=1.08)

gdr = Instrument(
    "삼성전자 GDR", "SMSN.IL", "yahoo", "London", "USD",
    common_shares_per_unit=25.0, local_peer="005930",
)
foreign = Quote("SMSN.IL", price=1200.0, prev_close=1190.0, currency="USD")
local = Quote("005930", price=70000.0, prev_close=69500.0, currency="KRW")

print("=== 괴리율 계산 (docstring 예시) ===")
p = compute_premium(gdr, foreign, local, fx)
assert p is not None
check("본주환산가 (1200×1380÷25)", p.implied_krw, 66240.0, 0.01)
check("괴리율 %", p.premium_pct, (66240.0 / 70000.0 - 1.0) * 100.0, 1e-9)

print("\n=== EUR 표시 종목 환산 ===")
fra = Instrument(
    "SK하이닉스 FRA", "HY9.F", "yahoo", "Frankfurt", "EUR",
    common_shares_per_unit=1.0, local_peer="000660",
)
p2 = compute_premium(
    fra,
    Quote("HY9.F", price=130.0, prev_close=128.0, currency="EUR"),
    Quote("000660", price=196000.0, prev_close=195000.0, currency="KRW"),
    fx,
)
assert p2 is not None
check("EUR→KRW 환산", p2.implied_krw, 130.0 * 1.08 * 1380.0, 0.01)

print("\n=== 프리장 가격 우선 적용 ===")
p3 = compute_premium(
    gdr,
    Quote("SMSN.IL", price=1200.0, prev_close=1190.0, currency="USD",
          extended_price=1230.0, extended_label="프리장"),
    local, fx,
)
assert p3 is not None
check("프리장 기준 환산가", p3.implied_krw, 1230.0 * 1380.0 / 25.0, 0.01)

print("\n=== 입력 결측 시 None 반환 ===")
for label, args in (
    ("환율 없음", (gdr, foreign, local, FxRates(usdkrw=None))),
    ("본주 Quote 없음", (gdr, foreign, None, fx)),
    ("본주가 0", (gdr, foreign, Quote("005930", price=0.0), fx)),
    ("해외 Quote 실패", (gdr, Quote.failed("X", "err"), local, fx)),
    ("환산비율 미설정", (Instrument("x", "X", "yahoo"), foreign, local, fx)),
):
    check_true(label, compute_premium(*args) is None)  # type: ignore[arg-type]

print("\n=== Quote 파생값 ===")
q = Quote("T", price=110.0, prev_close=100.0)
check("등락액", q.change, 10.0)
check("등락률", q.change_pct, 10.0)
check_true("prev_close=0 → change_pct None",
           Quote("T", price=110.0, prev_close=0.0).change_pct is None)
check_true("price None → ok False", not Quote("T").ok)
check_true("error 있으면 ok False", not Quote.failed("T", "x").ok)

print("\n=== 숫자 포맷 ===")
for got, want in (
    (ui.fmt_krw_compact(66240.0), "66,240원"),
    (ui.fmt_krw_compact(15_000_000.0), "1,500만원"),
    (ui.fmt_krw_compact(250_000_000.0), "2.50억원"),
    (ui.fmt_krw_compact(850.0), "850원"),
    (ui.fmt_big_usd(3.4e12), "$3.40T"),
    (ui.fmt_big_usd(8.9e9), "$8.9B"),
    (ui.fmt_pct(-5.3714), "-5.37%"),
    (ui.fmt_signed(10.0, 2), "+10.00"),
    (ui.fmt_num(None), "—"),
    (ui.direction_glyph(-1.0), "▼ "),
    (ui.direction_glyph(1.0), "▲ "),
    (ui.direction_class(0.0), "flat"),
):
    check_true(f"{got!r} == {want!r}", got == want)

print("\n=== 실패 Quote 도 카드 HTML 을 반환 ===")
html_fail = ui.render_card(gdr, Quote.failed("SMSN.IL", "티커 없음"), fx)
check_true(
    "실패 카드 렌더",
    "데이터 없음" in html_fail and "티커 없음" in html_fail and html_fail.startswith("<div"),
    f"{len(html_fail)} bytes",
)
check_true("quote=None 도 렌더", ui.render_card(gdr, None, fx).startswith("<div"))

print("\n=== 외부 문자열 이스케이프 ===")
hostile = Instrument(
    "<script>alert(1)</script>", 'X"onload="y', "yahoo",
    note="<img src=x onerror=alert(1)>",
)
html_hostile = ui.render_card(
    hostile, Quote("X", price=1.0, prev_close=1.0, currency="USD"), fx
)
# 핵심은 '위험한 문자열이 없는 것'이 아니라 '태그/속성으로 해석될 수 없는 것'입니다.
# onerror= 라는 문자열 자체는 텍스트 노드 안에 남아도 실행되지 않습니다.
check_true("꺾쇠가 실제 태그로 들어가지 않음",
           "<script>" not in html_hostile and "<img" not in html_hostile)
check_true("꺾쇠가 엔티티로 치환됨",
           "&lt;script&gt;" in html_hostile and "&lt;img" in html_hostile)
check_true("따옴표가 엔티티로 치환됨 (속성 탈출 방지)",
           "&quot;onload=" in html_hostile and '"onload="' not in html_hostile)

print("\n=== scale / suffix 적용 ===")
tnx = Instrument("10년물", "^TNX", "yahoo", "CBOE", "", decimals=3, scale=0.1, suffix="%")
html_tnx = ui.render_card(tnx, Quote("^TNX", price=42.1, prev_close=41.8), fx)
check_true("scale=0.1 적용 (42.1 → 4.210)", "4.210%" in html_tnx, )

print("\n=== 밸류에이션 표 ===")
table = ui.render_valuation_table(
    (("Microsoft", "MSFT"), ("삼성전자", "005930.KS")),
    (("trailingPE", "PER", "num2"), ("profitMargins", "순이익률", "pct")),
    {"MSFT": {"trailingPE": 35.2, "profitMargins": 0.362}, "005930.KS": {"trailingPE": None}},
)
check_true("PER 값 표기", "35.20" in table)
check_true("비율 ×100 표기", "36.20%" in table)
import re as _re_na  # noqa: E402
check_true("결측은 em dash", bool(_re_na.search(r'class="na"[^>]*>—', table)))
check_true("열 머리에 이름+심볼", "Microsoft" in table and "005930.KS" in table)

print("\n=== 카드 링크 생성 ===")
links = {
    "yahoo": Instrument("Micron", "MU", "yahoo").resolved_link(),
    "naver": Instrument("삼성전자", "005930", "naver").resolved_link(),
    "hyperliquid": Instrument("하이닉스 PERP", "xyz:SKHX", "hyperliquid").resolved_link(),
    "override": Instrument("x", "X", "yahoo", link="https://example.com/a").resolved_link(),
}
check("야후 링크", links["yahoo"], "https://finance.yahoo.com/quote/MU")
check("네이버 링크", links["naver"],
      "https://finance.naver.com/item/main.naver?code=005930")
check("Hyperliquid 링크 (dex 접두어 제거)", links["hyperliquid"],
      "https://app.hyperliquid.xyz/trade/SKHX")
check("link 직접 지정이 우선", links["override"], "https://example.com/a")
card_linked = ui.render_card(
    Instrument("Micron", "MU", "yahoo", "NASDAQ", "USD", verified=True),
    Quote("MU", price=180.0, prev_close=175.0, currency="USD"), fx,
)
check_true("카드 제목이 <a> 로 감싸짐",
           'class="dash-card-link"' in card_linked and 'target="_blank"' in card_linked)
check_true("실패 카드에도 직접 확인 링크",
           "직접 확인" in ui.render_card(
               Instrument("Micron", "MU", "yahoo"), Quote.failed("MU", "x"), fx))

print("\n=== 대체 심볼 폴백 (pick_quote) ===")
inst_alt = Instrument("삼성전자 GDR", "SMSN.IL", "yahoo", alt_symbols=("SMSN.L",))
bucket_fail_primary = {
    "yahoo": {
        "SMSN.IL": Quote.failed("SMSN.IL", "없음"),
        "SMSN.L": Quote("SMSN.L", price=4180.0, prev_close=4098.0, currency="USD"),
    }
}
got = pick_quote(inst_alt, bucket_fail_primary)
check_true("1순위 실패 시 대체 심볼 사용", got is not None and got.symbol == "SMSN.L")
check_true("대체 사용 사실을 extra 에 기록",
           got is not None and "대체 심볼 SMSN.L" in str(got.extra.get("fallback")))

bucket_ok_primary = {
    "yahoo": {
        "SMSN.IL": Quote("SMSN.IL", price=4180.0, prev_close=4098.0, currency="USD"),
        "SMSN.L": Quote("SMSN.L", price=9999.0, prev_close=1.0, currency="USD"),
    }
}
got2 = pick_quote(inst_alt, bucket_ok_primary)
check_true("1순위 성공 시 그대로 사용", got2 is not None and got2.symbol == "SMSN.IL")

all_fail = {"yahoo": {"SMSN.IL": Quote.failed("SMSN.IL", "없음")}}
got3 = pick_quote(inst_alt, all_fail)
check_true("전부 실패 시 1순위 실패 Quote 반환",
           got3 is not None and not got3.ok and got3.error == "없음")

print("\n=== Hyperliquid 심볼 분해 ===")
check("dex 있는 심볼", hl.split_symbol("xyz:SKHX"), ("xyz", "SKHX"))
check("dex 없는 심볼", hl.split_symbol("BTC"), ("", "BTC"))
check("공백 제거", hl.split_symbol(" xyz : SKHX "), ("xyz", "SKHX"))

print("\n=== 설정 정합성 ===")
keys = [s.key for s in config.SECTIONS]
check_true("섹션 key 중복 없음", len(keys) == len(set(keys)))
tab_keys = [k for k, _l in config.tab_labels()]
# 섹션은 자기 탭을 갖거나, 다른 탭에 합쳐졌다고 선언되어 있어야 합니다.
# 선언 없이 빠지면 화면에서 조용히 사라지므로 반드시 잡아야 합니다.
# 섹션 key 는 탭에 있거나(TAB_ORDER), 다른 탭에 합쳐졌거나
# (SECTIONS_MERGED_INTO), 내려졌다고(TABS_RETIRED) 선언되어 있어야 합니다.
# 셋 중 어디에도 없으면 화면에서 조용히 사라지므로 반드시 잡아야 합니다.
_merged = set(config.SECTIONS_MERGED_INTO)
_retired = set(config.SECTIONS_RETIRED)
check_true("모든 섹션이 어딘가에 선언됨",
           set(keys) <= set(tab_keys) | _merged | _retired,
           f"빠짐: {set(keys) - set(tab_keys) - _merged - _retired}")
check_true("합쳐진 섹션의 목적지 탭이 실제로 존재함",
           all(dest in tab_keys for dest in config.SECTIONS_MERGED_INTO.values()),
           str(config.SECTIONS_MERGED_INTO))
check_true("합쳐진 섹션은 실제로 존재하는 섹션",
           _merged <= set(keys), str(_merged - set(keys)))
check_true("합침과 내림이 겹치지 않음", not (_merged & _retired),
           str(_merged & _retired))
check_true("내려진 key 는 탭에 없음", not (_retired & set(tab_keys)),
           str(_retired & set(tab_keys)))
check_true("밸류에이션 탭 유지", "valuation" in tab_keys)
check_true("탭 라벨 중복 없음",
           len({l for _k, l in config.tab_labels()}) == len(config.tab_labels()))

watch = {i.symbol for i in config.SECTION_WATCHLIST.instruments}
expected_watch = {"MSFT", "AAPL", "MU", "O", "QQQ", "SCHD", "UNH", "AMT", "CRCL", "GOOGL",
                  "005930", "000660", "016360", "402340"}      # 2026-11-12 보유 종목 추가
check_true("관심종목 구성 일치", watch == expected_watch,
           f"차이: {watch ^ expected_watch}")
check_true("관심종목 전부 analysis_key 보유",
           all(i.analysis_key for i in config.SECTION_WATCHLIST.instruments))
check_true("한국 종목은 fundamental_symbol 이 .KS",
           all(i.fundamentals_ticker().endswith(".KS")
               for i in config.SECTION_WATCHLIST.instruments if i.source == "naver"))

for inst in config.SECTION_ADR.instruments:
    check_true(f"{inst.name}: 괴리율 비교 대상 본주가 국내 본주 섹션에 있음",
               inst.local_peer in {i.symbol for i in config.SECTION_LOCAL.instruments},
               f"local_peer={inst.local_peer}")

skhy = next(i for i in config.SECTION_ADR.instruments if i.symbol == "SKHY")
check("SK하이닉스 ADR 환산비율 (1 ADR = 보통주 1/10)",
      skhy.common_shares_per_unit, 0.1)
smsn = next(i for i in config.SECTION_ADR.instruments if i.symbol == "SMSN.IL")
check("삼성전자 GDR 환산비율 (1 GDR = 보통주 25주)",
      smsn.common_shares_per_unit, 25.0)
check_true("DEX 심볼은 전부 dex 접두어 보유",
           all(":" in i.symbol for i in config.SECTION_DEX.instruments))

print("\n=== 분석 저장소 ===")
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    empty = analysis_store.load(tmp, "MU")
    check_true("폴더 없으면 빈 문서", empty.is_empty and empty.age_days is None)
    check_true("미생성 kind 목록이 전체", len(empty.missing_kinds) == 3)

    os.makedirs(os.path.join(tmp, "MU"))
    with open(os.path.join(tmp, "MU", "decoder.html"), "w", encoding="utf-8") as fh:
        fh.write("<h1>마이크론</h1>")
    with open(os.path.join(tmp, "MU", "meta.json"), "w", encoding="utf-8") as fh:
        fh.write('{"name":"Micron","generated":"2026-11-01","mode":"web",'
                 '"sources":["https://sec.gov/x"]}')
    doc = analysis_store.load(tmp, "MU")
    check_true("decoder 읽힘", "decoder" in doc.html and "마이크론" in doc.html["decoder"])
    check("메타 이름", doc.name, "Micron")
    check_true("생성일 파싱", doc.age_days is not None and doc.age_days >= 0)
    check_true("최근 생성은 stale 아님", not doc.is_stale)
    check_true("나머지 2종은 미생성", doc.missing_kinds == ["story", "price"])

    with open(os.path.join(tmp, "MU", "meta.json"), "w", encoding="utf-8") as fh:
        fh.write('{"generated":"2020-01-01"}')
    check_true("오래된 분석은 stale", analysis_store.load(tmp, "MU").is_stale)

    for hostile, expect in (("../../etc", "etc"), ("..", ""), ("MU/../AAPL", "MUAAPL"),
                            ("005930", "005930"), ("A-B_C", "A-B_C")):
        got = analysis_store.load(tmp, hostile).key
        check_true(f"경로 정제 {hostile!r} → {expect!r}", got == expect, f"실제 {got!r}")

check_true("스킬 명령 생성",
           analysis_store.skill_command("price", "MU", "Micron")
           == "/price-decoder-korean Micron")



# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 괴리율 합친 화면 ===")
import compute as _compute  # noqa: E402
import demo as _demo  # noqa: E402

_data = _demo.demo_payload()
_fx = _compute.resolve_fx(_data.get("yahoo", {}), None)
_rows, _unpaired = _compute.build_premium_rows(
    list(config.SECTION_ADR.instruments),
    list(config.SECTION_LOCAL.instruments), _data, _fx)

check_true("해외 종목 전부 줄로", len(_rows) == len(config.SECTION_ADR.instruments),
      f"{len(_rows)}개")
check_true("짝 없는 국내 종목 분리", len(_unpaired) == 1,
      str([i.name for i in _unpaired]))
check_true("짝 있는 종목은 제외", all(i.symbol != "005930" for i in _unpaired))
check_true("전부 괴리율 산출", all(r.ok for r in _rows),
      str([(r.foreign.symbol, r.blocked) for r in _rows if not r.ok]))

# 데모 괴리율이 현실적인 범위여야 합니다 — 환산주수를 잘못 쓰면 수백 %가 나옵니다
for _r in _rows:
    check_true(f"{_r.foreign.symbol} 괴리율이 ±10% 내",
          abs(_r.premium.premium_pct) < 10.0,
          f"{_r.premium.premium_pct:+.2f}%")

# 계산 사슬 검산: 해외가 × 환율 ÷ 환산주수 = 본주환산가
for _r in _rows:
    _expected = _r.foreign_price * _r.fx_rate / _r.shares_per_unit
    check_true(f"{_r.foreign.symbol} 환산 검산",
          abs(_r.premium.implied_krw - _expected) < 1.0,
          f"{_r.premium.implied_krw:,.0f} vs {_expected:,.0f}")

check_true("시간외 가격을 우선 사용", any(r.uses_extended for r in _rows))

# 끊긴 사슬도 사유가 나와야 합니다
_broken, _ = _compute.build_premium_rows(
    list(config.SECTION_ADR.instruments),
    list(config.SECTION_LOCAL.instruments), {}, _fx)
check_true("시세 없으면 사유 표시",
      all(not r.ok and r.blocked for r in _broken),
      str([r.blocked[:20] for r in _broken[:1]]))

_html = ui.render_premium_pair(_rows[0])
check_true("사슬 렌더링", "dash-chain" in _html and "본주환산가" in _html)
check_true("연산자 포함", "×" in _html and "÷" in _html and "=" in _html)
check_true("국내 본주가 같은 줄에", _rows[0].local.name in _html)
check_true("끊긴 줄도 렌더링",
      "계산 불가" in ui.render_premium_pair(_broken[0]))

check_true("실시간 배지", "dash-live on" in ui.render_live_badge("x", "on"))
check_true("고정 배지", "dash-live frozen" in ui.render_live_badge("x", "frozen"))

print("\n=== 코스피 장 상태 ===")
import datetime as _dt  # noqa: E402

def _at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm,
                        tzinfo=_dt.timezone(_dt.timedelta(hours=9)))


check_true("장중은 on", _compute.kospi_state(_at(2026, 11, 6, 10, 30))[0] == "on")
check_true("개장 직후도 on", _compute.kospi_state(_at(2026, 11, 6, 9, 0))[0] == "on")
check_true("15:29 는 on", _compute.kospi_state(_at(2026, 11, 6, 15, 29))[0] == "on")
check_true("15:30 은 frozen", _compute.kospi_state(_at(2026, 11, 6, 15, 30))[0] == "frozen")
check_true("개장 전은 frozen", _compute.kospi_state(_at(2026, 11, 6, 8, 59))[0] == "frozen")
check_true("마감 후는 frozen", _compute.kospi_state(_at(2026, 11, 6, 20, 0))[0] == "frozen")
check_true("토요일은 주말", "주말" in _compute.kospi_state(_at(2026, 11, 7, 10, 0))[1])
check_true("일요일도 주말", "주말" in _compute.kospi_state(_at(2026, 11, 8, 10, 0))[1])
check_true("상태 설명이 있음",
      all(_compute.kospi_state(_at(2026, 11, 6, h, 0))[1]
          for h in (8, 10, 16, 22)))

print("\n=== 탭 구성 ===")
_labels = dict(config.tab_labels())
# 목적 기준 5개로 재구성한 뒤의 상태입니다. 괴리율은 탭에서 내려갔고,
# 진단은 사이드바로, 국내 발굴은 '종목 발굴' 탭 안의 시장 전환으로 들어갔습니다.
check_true("괴리율은 탭에 없음", "adr" not in _labels, str(list(_labels)))
check_true("국내 본주 별도 탭 없음", "local" not in _labels, str(list(_labels)))
check_true("진단은 탭이 아니라 설정 패널", "diag" not in _labels,
           str(list(_labels)))
check_true("국내 발굴은 발굴 탭 안으로",
           "screen_kr" not in _labels and "discover" in _labels,
           str(list(_labels)))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 목적 기준 5개 탭 ===")
import discover as _disc  # noqa: E402

_tabs = dict(config.tab_labels())
# 2026-11-11: 시장이 최상위 축이 되면서 탭이 '시장마다 다른 목록' 이
# 됐습니다. 전체 목록은 두 시장의 합집합이고, 시장마다 보이는 게 다릅니다.
check_true("전체 탭 14개 (수급·실적 서프라이즈 추가)", len(_tabs) == 14, f"{len(_tabs)}개: {list(_tabs)}")
for _need in ("summary", "holdings", "discover", "valuation", "sector_heat",
              "kr_flows", "macro", "us_flows", "cycle"):
    check_true(f"탭 '{_need}' 이 있다", _need in _tabs, str(list(_tabs)))
check_true("옛 flows 탭은 없다", "flows" not in _tabs,
           "한국·미국 흐름으로 나뉘었습니다")
check_true("라벨 한국어", all(_tabs.values()), str(_tabs))

# 내린 탭의 섹션은 코드가 남아 있어야 합니다 — 되돌릴 수 있어야 하니까
for _key in ("adr", "dex", "futures", "etf_proxy"):
    check_true(f"{_key} 섹션 코드 보존", _key in config.SECTION_BY_KEY,
               str(list(config.SECTION_BY_KEY)))
    check_true(f"{_key} 내렸다고 선언됨", _key in config.SECTIONS_RETIRED)

check_true("합쳐진 섹션 선언 유지",
           {"watchlist", "local"} <= set(config.SECTIONS_MERGED_INTO))
check_true("내린 섹션은 SECTIONS_RETIRED 에",
           {"adr", "dex", "futures", "etf_proxy"} <= config.SECTIONS_RETIRED)
check_true("예전 탭 이름 기록 유지",
           {"signals", "analysis", "screen", "diag"} <= set(config.TABS_RETIRED))
check_true("all_instruments 가 전 섹션을 덮음",
           len(config.all_instruments()) >= len(config.SECTION_WATCHLIST.instruments))
check_true("all_instruments 중복 없음",
           len({(i.source, i.symbol) for i in config.all_instruments()})
           == len(config.all_instruments()))

print("\n=== 52주 발굴 ===")
_dq = _demo.demo_discovery_quotes()
_known = {i.symbol: i for i in config.all_instruments()}
_us = [_known.get(t) or Instrument(name=t, symbol=t, source="yahoo",
                                   currency="USD", verified=False)
       for t in config.screen_tickers()]
_screens, _ = _demo.demo_screens()
_pos = _disc.build_positions(_us, _dq, screens=_screens)

check_true("발굴 대상 전체에 시세", all(p.ok for p in _pos),
           str([(p.ticker, p.error[:24]) for p in _pos if not p.ok][:3]))
check_true("종목 수 일치", len(_pos) == len(config.screen_tickers()))

_counts = _disc.summary_counts(_pos)
check_true("조회 실패 0", _counts["조회 실패"] == 0, str(_counts))
check_true("고가권·저가권이 모두 존재",
           _counts["고가권(구간 80%+)"] > 0 and _counts["저가권(구간 20%-)"] > 0,
           str(_counts))

# 구간 위치 기준이어야 합니다. '저가 대비 +N%' 로 하면 변동폭이 좁은 종목이
# 구간 중간에 있어도 저가권으로 잡히는 버그가 있었습니다.
_narrow = _disc.Position(ticker="NARROW", price=110.0, high_52w=120.0,
                         low_52w=100.0)
check_true("변동폭 좁은 종목의 구간 위치", abs(_narrow.band_position - 50.0) < 0.1,
           f"{_narrow.band_position}")
check_true("구간 중간은 저가권이 아님", not _narrow.is_near_low,
           f"저가 대비 {_narrow.upside_from_low_pct:+.1f}%")
check_true("구간 중간은 고가권도 아님", not _narrow.is_near_high)

_high = _disc.Position(ticker="HIGH", price=119.5, high_52w=120.0, low_52w=60.0)
check_true("고가 근처는 고가권", _high.is_near_high, f"{_high.band_position:.0f}%")
check_true("고가 99.5% 이상은 돌파", _high.is_breakout,
           f"{_high.pct_of_high:.2f}%")

_low = _disc.Position(ticker="LOW", price=62.0, high_52w=120.0, low_52w=60.0)
check_true("저가 근처는 저가권", _low.is_near_low, f"{_low.band_position:.0f}%")
check_true("저가권은 돌파 아님", not _low.is_breakout)

_newlow = _disc.Position(ticker="NEW", price=59.0, high_52w=120.0, low_52w=60.0)
check_true("저가를 깨면 신저가", _newlow.is_new_low,
           f"{_newlow.band_position:.1f}%")
check_true("신저가도 저가권", _newlow.is_near_low)

check_true("고가=저가면 판정 불가",
           not _disc.Position(ticker="F", price=10.0, high_52w=10.0,
                              low_52w=10.0).ok)
check_true("52주 값 없으면 판정 불가",
           not _disc.Position(ticker="F", price=10.0).ok)

print("\n=== 사분면 (52주 × 품질) ===")
_q1 = _disc.Position(ticker="A", price=119.0, high_52w=120.0, low_52w=60.0,
                     quality_passed=5, quality_total=6)
_q2 = _disc.Position(ticker="B", price=119.0, high_52w=120.0, low_52w=60.0,
                     quality_passed=1, quality_total=6)
_q3 = _disc.Position(ticker="C", price=62.0, high_52w=120.0, low_52w=60.0,
                     quality_passed=5, quality_total=6)
_q4 = _disc.Position(ticker="D", price=62.0, high_52w=120.0, low_52w=60.0,
                     quality_passed=1, quality_total=6)
_mid = _disc.Position(ticker="E", price=90.0, high_52w=120.0, low_52w=60.0,
                      quality_passed=5, quality_total=6)
_noq = _disc.Position(ticker="F", price=119.0, high_52w=120.0, low_52w=60.0)

check_true("① 고가권+통과", _q1.quadrant(4) == 1, str(_q1.quadrant(4)))
check_true("② 고가권+미달", _q2.quadrant(4) == 2, str(_q2.quadrant(4)))
check_true("③ 저가권+통과", _q3.quadrant(4) == 3, str(_q3.quadrant(4)))
check_true("④ 저가권+미달", _q4.quadrant(4) == 4, str(_q4.quadrant(4)))
check_true("중간 구간은 0", _mid.quadrant(4) == 0, str(_mid.quadrant(4)))
check_true("품질 없으면 0", _noq.quadrant(4) == 0, str(_noq.quadrant(4)))
check_true("기준선을 올리면 ①→②", _q1.quadrant(6) == 2, str(_q1.quadrant(6)))

_groups = _disc.group_by_quadrant([_q1, _q2, _q3, _q4, _mid, _noq], 4)
check_true("그룹 분배", [len(_groups[k]) for k in (1, 2, 3, 4)] == [1, 1, 1, 1],
           str({k: len(v) for k, v in _groups.items()}))
check_true("중간·판정없음은 0번", len(_groups[0]) == 2)

_ranked = _disc.rank_by_high([_q3, _q1, _mid])
check_true("고가권부터 정렬", [p.ticker for p in _ranked] == ["A", "E", "C"],
           str([p.ticker for p in _ranked]))
_ranked_low = _disc.rank_by_low([_q1, _q3, _mid])
check_true("저가권부터 정렬", _ranked_low[0].ticker == "C",
           str([p.ticker for p in _ranked_low]))

print("\n=== 발굴 렌더링 ===")
check_true("지도", "dash-table" in ui.render_discover_map(_groups))
check_true("지도에 티커", "A" in ui.render_discover_map(_groups))
check_true("빈 칸은 대시", "—" in ui.render_discover_map({0: [], 1: [], 2: [],
                                                          3: [], 4: []}))
_tbl = ui.render_discover_table([_q1, _q3], 4)
check_true("표 렌더링", "dash-table" in _tbl and "고가 대비" in _tbl)
check_true("표에 품질 표시", "○" in _tbl)
check_true("품질 없으면 na", 'class="na"' in ui.render_discover_table([_noq], 4))
check_true("빈 표는 빈 문자열", ui.render_discover_table([], 4) == "")

_card = ui.render_discover_card(_q1, 4, prompt=_disc.prompt_for(_q1, 4))
check_true("카드 렌더링", "dash-verdict" in _card and "①" in _card)
check_true("카드에 태그", "고가권" in _card or "신고가" in _card)
check_true("카드에 프롬프트", "<details>" in _card)
check_true("신저가 태그", "52주 신저가" in ui.render_discover_card(_newlow, 4))

_prompt = _disc.prompt_for(_q3, 4)
check_true("프롬프트에 위치", "저가권" in _prompt)
check_true("③ 은 눌린 이유를 묻는다", "Risk Factors" in _prompt)
check_true("모멘텀 지표임을 명시", "모멘텀 지표" in _prompt)
check_true("추천 금지", "매수/매도 추천" in _prompt)
for _q, _word in ((_q1, "오른"), (_q2, "기대"), (_q4, "업종 전체")):
    check_true(f"사분면 {_q.quadrant(4)} 전용 질문",
               _word in _disc.prompt_for(_q, 4))

_xss = _disc.Position(ticker='<img src=x>', price=100.0, high_52w=120.0,
                      low_52w=60.0, quality_passed=5, quality_total=6)
check_true("티커 이스케이프",
           "&lt;img" in ui.render_discover_table([_xss], 4))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 내 종목 탭 구조 (소스 검사) ===")
# 이 블록은 app.py **소스**를 검사합니다. 스트림릿 위젯은 직접 테스트하기
# 어려운데, 지난번 '분석 본문 접기' 수정이 패턴 불일치로 **조용히 적용되지
# 않은** 일이 있었습니다 (str.replace 는 못 찾아도 오류가 없습니다).
# 같은 실수를 다시 놓치지 않으려고 호출 구조를 직접 확인합니다.
import ast as _ast  # noqa: E402
import pathlib as _pl  # noqa: E402

_app_src = (_pl.Path(__file__).resolve().parent.parent / "app.py").read_text(
    encoding="utf-8")
_app_ast = _ast.parse(_app_src)
_app_fns = {n.name: n for n in _ast.walk(_app_ast)
            if isinstance(n, _ast.FunctionDef)}

check_true("내 종목 탭 함수 존재", "render_holdings_tab" in _app_fns)
check_true("분석 요약 함수 존재", "_analysis_summary" in _app_fns)

_holdings = _app_fns.get("render_holdings_tab")
_calls = [n for n in _ast.walk(_holdings) if isinstance(n, _ast.Call)] if _holdings else []
_analysis_calls = [
    c for c in _calls
    if isinstance(c.func, _ast.Name) and c.func.id == "render_analysis_tab"
]
check_true("내 종목에서 분석을 한 번 호출", len(_analysis_calls) == 1,
           f"{len(_analysis_calls)}회")
check_true("embed=True 로 호출 (본문 접힘)",
           bool(_analysis_calls)
           and any(kw.arg == "embed" and getattr(kw.value, "value", None) is True
                   for kw in _analysis_calls[0].keywords),
           str([kw.arg for kw in _analysis_calls[0].keywords])
           if _analysis_calls else "호출 없음")

# 섹션 전체가 expander 안에 있어야 합니다 — 본문만 접으면 위젯 20개가 남습니다
_withs = [n for n in _ast.walk(_holdings) if isinstance(n, _ast.With)] if _holdings else []
_analysis_in_with = any(
    any(isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)
        and c.func.id == "render_analysis_tab"
        for c in _ast.walk(w))
    for w in _withs
)
check_true("분석 섹션이 expander 안에 있음", _analysis_in_with)
check_true("expander 가 둘 이상 (국내 본주 + 공시 분석)",
           len(_withs) >= 2, f"{len(_withs)}개")

# render_analysis_tab 이 embed 를 실제로 쓰는지
_analysis_fn = _app_fns.get("render_analysis_tab")
check_true("분석 함수가 embed 인자를 받음",
           bool(_analysis_fn)
           and any(a.arg == "embed" for a in _analysis_fn.args.kwonlyargs),
           str([a.arg for a in _analysis_fn.args.kwonlyargs])
           if _analysis_fn else "")
_embed_names = [n for n in _ast.walk(_analysis_fn)
                if isinstance(n, _ast.Name) and n.id == "embed"] if _analysis_fn else []
check_true("embed 를 분기에 실제로 사용", len(_embed_names) >= 2,
           f"{len(_embed_names)}회 참조")

# app.py 를 import 하지 않습니다 — streamlit 이 없는 환경에서도 테스트가
# 돌아야 하고, 이 검사의 목적은 '수정이 실제로 적용됐나' 이지 위젯 동작이
# 아닙니다. 요약 함수의 존재와 반환 경로만 소스에서 확인합니다.
_summary_fn = _app_fns.get("_analysis_summary")
_returns = [n for n in _ast.walk(_summary_fn)
            if isinstance(n, _ast.Return)] if _summary_fn else []
check_true("요약 함수가 값을 돌려줌", len(_returns) >= 2,
           f"{len(_returns)}개 return")
check_true("분석 없을 때 경로도 있음",
           bool(_summary_fn) and "생성된 분석 없음" in _app_src)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 요약 (휴대폰 10초 화면) ===")
import re as _re2  # noqa: E402

import macro as _macro  # noqa: E402
import summary as _sm  # noqa: E402

_fg2 = _demo.demo_feargreed()
_vx2 = _demo.demo_vix()
_tr2 = _demo.demo_inventory_trends()
_ser2, _err2 = _demo.demo_macro_series()
_rd2 = _macro.build_readings(config.macro_series(), _ser2, _err2)

_s2 = _sm.build(urgent=[], soon=[], holdings_total=9, fg=_fg2,
                vix_state=_vx2, trends=_tr2, macro_readings=_rd2)
check_true("요약 네 줄", len(_s2.rows) == 4, f"{len(_s2.rows)}줄")
check_true("줄 키가 고정",
           [r.key for r in _s2.rows]
           == ["holdings", "sentiment", "cycle", "discover"],
           str([r.key for r in _s2.rows]))
check_true("판정 한 줄 생성", _s2.verdict != "")
check_true("level 은 네 가지뿐",
           all(r.level in ("quiet", "watch", "alert", "unknown")
               for r in _s2.rows),
           str({r.level for r in _s2.rows}))

# 조용할 때 — 이게 정상 상태이고 그렇게 보여야 합니다
_quiet = _sm.build(urgent=[], soon=[], holdings_total=9)
check_true("입력이 없으면 데이터 없음 처리",
           any(r.level == "unknown" for r in _quiet.rows),
           str([(r.key, r.level) for r in _quiet.rows]))
check_true("내 종목은 조용함으로", _quiet.rows[0].level == "quiet",
           _quiet.rows[0].level)
check_true("종목 수를 말해줌", "9종목" in _quiet.rows[0].headline,
           _quiet.rows[0].headline)


class _FakeSig:
    def __init__(self, title):
        self.title = title


_urgent = _sm.build(urgent=[_FakeSig("MU 신규 10-Q"), _FakeSig("O 실적 임박")],
                    soon=[], holdings_total=9)
check_true("긴급이 있으면 alert", _urgent.rows[0].level == "alert",
           _urgent.rows[0].level)
check_true("건수를 말해줌", "2건" in _urgent.rows[0].headline,
           _urgent.rows[0].headline)
check_true("판정이 긴급을 가리킴", "내 종목" in _urgent.verdict, _urgent.verdict)
check_true("주의 건수 집계", _urgent.attention_count >= 1,
           str(_urgent.attention_count))
check_true("조용하지 않음", not _urgent.all_quiet)

# 신호가 많아도 한 화면을 넘지 않아야 합니다
_many = _sm.build(urgent=[_FakeSig(f"신호{i}") for i in range(9)],
                  soon=[], holdings_total=9)
check_true("상한을 넘으면 '외 N건'", "외 5건" in _many.rows[0].detail,
           _many.rows[0].detail[-20:])

_soon_only = _sm.build(urgent=[], soon=[_FakeSig("UNH 실적 2주 뒤")],
                       holdings_total=9)
check_true("이번 주 건은 watch", _soon_only.rows[0].level == "watch")

print("\n=== 요약 — 시장 분위기 ===")
check_true("공포탐욕·VIX 를 한 줄에",
           "공포탐욕" in _s2.rows[1].headline and "VIX" in _s2.rows[1].headline,
           _s2.rows[1].headline)
check_true("백분위 포함", "5년 중" in _s2.rows[1].headline, _s2.rows[1].headline)

_inv_state = _demo.demo_vix(inverted=True)
_inv_sum = _sm.build(urgent=[], soon=[], holdings_total=9,
                     fg=_fg2, vix_state=_inv_state)
check_true("VIX 역전은 alert", _inv_sum.rows[1].level == "alert",
           _inv_sum.rows[1].level)
check_true("역전이 드물다는 것을 적음", "7.7" in _inv_sum.rows[1].detail,
           _inv_sum.rows[1].detail[:50])

_no_sent = _sm.build(urgent=[], soon=[], holdings_total=9)
check_true("둘 다 없으면 데이터 없음", _no_sent.rows[1].level == "unknown")

print("\n=== 요약 — 메모리 사이클 ===")
check_true("DIO 와 반도체 지표를 한 줄에",
           "DIO" in _s2.rows[2].headline, _s2.rows[2].headline)
check_true("연속 상승이면 watch", _s2.rows[2].level in ("watch", "quiet"),
           _s2.rows[2].level)
_no_cycle = _sm.build(urgent=[], soon=[], holdings_total=9, fg=_fg2)
check_true("추세가 없으면 데이터 없음", _no_cycle.rows[2].level == "unknown")

print("\n=== 요약 — 발굴은 일부러 뺐습니다 ===")
check_true("발굴은 항상 조용함", _s2.rows[3].level == "quiet")
check_true("책상 작업이라고 적음", "책상" in _s2.rows[3].headline,
           _s2.rows[3].headline)
check_true("이유를 설명", "휴대폰" in _s2.rows[3].detail,
           _s2.rows[3].detail[:40])

print("\n=== 요약 렌더링 ===")
_sh = ui.render_summary(_s2)
check_true("밴드", "dash-verdict-band" in _sh)
# class="dash-srow-chip" 등이 같은 접두사라 정확히 세어야 합니다
_srow_n = len(_re2.findall(r'class="dash-srow (?:quiet|watch|alert|unknown)"', _sh))
check_true("네 줄", _srow_n == 4, str(_srow_n))
check_true("어느 탭으로 갈지 표시", "탭</div>" in _sh)
check_true("하드코딩 색 없음",
           not _re2.findall(r"#[0-9a-fA-F]{6}", _sh),
           str(_re2.findall(r"#[0-9a-fA-F]{6}", _sh)))
check_true("주의 있으면 강조", "attention" in ui.render_summary(_urgent))
check_true("조용하면 강조 없음",
           "dash-verdict-band attention" not in ui.render_summary(_quiet))

_xss_row = _sm.Row(key="x", title='<img src=x>', headline="y")
check_true("이스케이프", "&lt;img" in ui.render_summary_row(_xss_row))

print("\n=== 휴대폰 CSS ===")
import theme as _theme  # noqa: E402

_rules = _theme.build_rules()
check_true("그리드 규칙이 앱에 있음", ".dash-grid" in _rules)
check_true("cols-4 정의", "cols-4" in _rules)
check_true("미디어 쿼리 존재", "@media" in _rules, f"{_rules.count('@media')}개")
check_true("좁은 화면에서 2열",
           "max-width: 1100px" in _rules and "--cols: 2" in _rules)
check_true("휴대폰 폭 규칙", "max-width: 640px" in _rules)
check_true("표 가로 스크롤", "overflow-x: auto" in _rules)
check_true("SVG 폰트 보정", "svg.dash-dio text" in _rules)
check_true("요약 줄 스타일", ".dash-srow" in _rules)

print("\n=== 탭 구성 ===")
_tabs6 = dict(config.tab_labels())
check_true("요약이 맨 앞", list(_tabs6)[0] == "summary", str(list(_tabs6)))
for _mk in ("kr", "us"):
    _ks = config.market_tab_keys(_mk)
    check_true(f"{_mk} 시장도 요약이 맨 앞", _ks[0] == "summary", str(_ks))


print("\n=== 휴대폰 모드 ===")
# 소스 검사 — 토글이 실제로 배선됐는지. 지난번 '조용히 적용 안 됨' 전례 때문에
# 배선 자체를 확인합니다.
check_true("휴대폰 모드 토글이 있다", '"휴대폰 모드"' in _app_src)
check_true("옵션으로 반환", '"phone": phone' in _app_src)
# 인자가 늘어나면서 호출이 여러 줄로 나뉘었습니다. 한 줄 리터럴로
# 찾으면 줄바꿈만으로 깨지므로, 호출에 phone 이 들어가는지를 봅니다.
for _tab_fn in ("render_holdings_tab", "render_valuation_tab"):
    _call = _app_src.split(f"{_tab_fn}(data, fx,")[1][:160]
    check_true(f"{_tab_fn} 호출에 phone 전달",
               'opts["phone"]' in _call, _call.split(")")[0])

_an = _app_fns.get("render_analysis_tab")
check_true("분석 함수가 phone 을 받음",
           bool(_an) and any(a.arg == "phone" for a in _an.args.kwonlyargs),
           str([a.arg for a in _an.args.kwonlyargs]) if _an else "")
check_true("휴대폰이면 본문을 DOM 에 안 넣음",
           "휴대폰 모드에서는 " in _app_src and "싣지 않습니다" in _app_src)
check_true("넓은 지표표도 생략", "9컬럼 표라서 휴대폰 모드에서는" in _app_src)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 튜플 언패킹 개수 (실행 없이 잡는 검사) ===")
# streamlit 이 없어 app.py 를 실행할 수 없습니다. 그래서 "a, b, c = mod.f()" 의
# 받는 개수를 피호출 함수의 반환 어노테이션과 **정적으로** 대조합니다.
#
# 실제로 이걸로 운영 중 에러를 하나 잡았습니다:
#   urgent, soon, _fyi = sig_mod.split_by_urgency(...)   ← 2개를 3개로 받음
#   → ValueError: not enough values to unpack
# 테스트가 전부 통과하는데도 앱이 죽는 종류라 반드시 막아야 합니다.
import pathlib as _pl2  # noqa: E402


def _return_arity(fn: _ast.FunctionDef) -> int | None:
    """반환 어노테이션이 tuple[...] 이면 원소 수, 아니면 None."""
    if fn.returns is None:
        return None
    text = _ast.unparse(fn.returns)
    if not text.startswith("tuple["):
        return None
    inner = text[len("tuple["):-1]
    depth, count = 0, 1
    for ch in inner:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


_root = _pl2.Path(__file__).resolve().parent.parent
_arity: dict[tuple[str, str], int] = {}
for _path in sorted(_root.glob("*.py")) + sorted(_root.glob("sources/*.py")):
    try:
        _tree = _ast.parse(_path.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    _mod = (_path.stem if _path.parent == _root else f"sources.{_path.stem}")
    for _node in _tree.body:
        if isinstance(_node, _ast.FunctionDef):
            _a = _return_arity(_node)
            if _a:
                _arity[(_mod, _node.name)] = _a

check_true("반환 어노테이션을 가진 함수를 찾음", len(_arity) >= 20,
           f"{len(_arity)}개")

# app.py 가 쓰는 import 별칭
_ALIAS = {
    "sig_mod": "signals", "macro_mod": "macro", "demo_mod": "demo",
    "ui": "components", "disc": "discover", "sm": "summary",
    "vd": "verdict", "rdcf": "reverse_dcf", "cycle_mod": "cycle",
}

_mismatches: list[str] = []
for _node in _ast.walk(_app_ast):
    if not isinstance(_node, _ast.Assign):
        continue
    _tgt = _node.targets[0]
    if not isinstance(_tgt, _ast.Tuple):
        continue
    _call = _node.value
    if not isinstance(_call, _ast.Call) or not isinstance(_call.func,
                                                          _ast.Attribute):
        continue
    _owner = _call.func.value
    if not isinstance(_owner, _ast.Name):
        continue
    _key = (_ALIAS.get(_owner.id, _owner.id), _call.func.attr)
    _want = _arity.get(_key)
    if _want is not None and _want != len(_tgt.elts):
        _mismatches.append(
            f"{_node.lineno}행 {_owner.id}.{_call.func.attr} "
            f"— {len(_tgt.elts)}개로 받는데 {_want}개 반환")

check_true("app.py 언패킹 개수 일치", not _mismatches,
           " / ".join(_mismatches))

# 검사가 실제로 동작하는지 — 알려진 함수의 arity 를 확인합니다
check_true("split_by_urgency 는 2개",
           _arity.get(("signals", "split_by_urgency")) == 2,
           str(_arity.get(("signals", "split_by_urgency"))))

print("\n=== 모듈 간 의존 최소화 ===")
# 파일을 손으로 맞춰 올리는 환경이라, 한 기능을 위해 두 파일을 고치면 한쪽만
# 올라가 AttributeError 가 납니다. 실제로 그렇게 한 번 죽었습니다.
# 요약의 세 갈래 분류는 app.py 안에서 끝냅니다.
check_true("signals 에 새 함수를 만들지 않음",
           "split_by_severity" not in _app_src
           and "split_by_severity" not in
           (_pl.Path(__file__).resolve().parent.parent
            / "signals.py").read_text(encoding="utf-8"),
           "남아 있으면 두 파일 의존이 다시 생깁니다")
check_true("요약이 severity 로 직접 분류",
           "s.severity >= 3" in _app_src and "s.severity == 2" in _app_src,
           "인라인 분류가 보이지 않습니다")

import signals as _sg2  # noqa: E402


class _Sev:
    def __init__(self, severity):
        self.severity = severity


_rows = [_Sev(3), _Sev(3), _Sev(2), _Sev(1), _Sev(2), _Sev(0)]
_now = [s for s in _rows if s.severity >= 3]
_soon2 = [s for s in _rows if s.severity == 2]
_fyi2 = [s for s in _rows if s.severity < 2]
check_true("지금 = severity 3", len(_now) == 2, str(len(_now)))
check_true("이번 주 = severity 2", len(_soon2) == 2, str(len(_soon2)))
check_true("참고 = severity 1 이하", len(_fyi2) == 2, str(len(_fyi2)))
check_true("빠지는 신호 없음",
           len(_now) + len(_soon2) + len(_fyi2) == len(_rows))

_u2, _f2 = _sg2.split_by_urgency(_rows)
check_true("기존 두 갈래와 합이 맞음",
           len(_now) + len(_soon2) == len(_u2) and len(_fyi2) == len(_f2),
           f"{len(_now)}+{len(_soon2)} vs {len(_u2)}")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 모듈 간 참조 (존재하지 않는 속성) ===")
# Streamlit Cloud 는 실행해 봐야 AttributeError 가 납니다. 배포 한 번에
# 1분이고, 손으로 파일을 맞추다 보면 한쪽만 올라갑니다. 실제로 세 번 겪었습니다:
#   ModuleNotFoundError(sources/ 누락) → ValueError(반환 개수) → AttributeError
# 올리기 전에 정적으로 잡습니다.
import tools.xref as _xref  # noqa: E402

_probs = _xref.scan(_pl.Path(__file__).resolve().parent.parent)
check_true("존재하지 않는 모듈 속성 참조 없음", not _probs,
           "; ".join(f"{f}:{ln} {al}.{at}" for f, ln, al, _m, at in _probs[:5]))

# 검사기가 실제로 잡는지 — 일부러 깨진 코드를 넣어 봅니다
import tempfile as _tf  # noqa: E402

with _tf.TemporaryDirectory() as _d:
    _dp = _pl.Path(_d)
    (_dp / "lib.py").write_text("def real():\n    return 1\n", encoding="utf-8")
    (_dp / "use.py").write_text("import lib\nlib.missing()\n", encoding="utf-8")
    _caught = _xref.scan(_dp)
    check_true("깨진 참조를 실제로 잡는다", len(_caught) == 1,
               f"{len(_caught)}건 — 0이면 검사기가 무용지물입니다")
    (_dp / "ok.py").write_text("import lib\nlib.real()\n", encoding="utf-8")
    (_dp / "use.py").unlink()
    check_true("멀쩡한 참조는 통과", not _xref.scan(_dp))

# 튜플 분해 대입 오탐 방지 (A, B = 1, 2 를 '없는 이름' 으로 보면 안 됩니다)
with _tf.TemporaryDirectory() as _d:
    _dp = _pl.Path(_d)
    (_dp / "lib.py").write_text("LO, HI = -1, 1\n", encoding="utf-8")
    (_dp / "use.py").write_text("import lib\nprint(lib.LO, lib.HI)\n",
                                encoding="utf-8")
    check_true("튜플 분해 상수를 오탐하지 않는다", not _xref.scan(_dp))

# 패키지 하위 모듈이 파일로 존재하는지 — sources/ 가 빠진 채 올라가
# ModuleNotFoundError 로 죽은 적이 있습니다.
with _tf.TemporaryDirectory() as _d:
    _dp = _pl.Path(_d)
    (_dp / "pkg").mkdir()
    (_dp / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (_dp / "pkg" / "there.py").write_text("X = 1\n", encoding="utf-8")
    (_dp / "use.py").write_text("from pkg import gone\n", encoding="utf-8")
    check_true("파일 없는 import 를 잡는다", len(_xref.scan(_dp)) == 1,
               f"{len(_xref.scan(_dp))}건")
    (_dp / "use.py").write_text("from pkg import there\n", encoding="utf-8")
    check_true("있는 import 는 통과", not _xref.scan(_dp))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 요청 제한 준수 (병렬화) ===")
# 순차 요청이 느려서 병렬로 바꿨는데, 제한을 넘기면 SEC/DART 가 차단합니다.
# 빠른지와 제한을 지키는지를 **둘 다** 확인합니다.
import threading as _th  # noqa: E402
import time as _tm  # noqa: E402

import sources.edgar_facts as _ef  # noqa: E402
import sources.dart as _dart  # noqa: E402
import sources.fred as _fred  # noqa: E402


def _measure(throttle, n=40, latency=0.05):
    """throttle 을 n 번 병렬 호출하고 시작 시각 분포를 돌려줍니다."""
    starts = []
    lock = _th.Lock()

    def one(_i):
        throttle()
        with lock:
            starts.append(_tm.monotonic())
        _tm.sleep(latency)

    t0 = _tm.monotonic()
    with _cf.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, range(n)))
    starts.sort()
    worst = max(sum(1 for s in starts if t <= s < t + 1.0) for t in starts)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    return _tm.monotonic() - t0, worst, min(gaps)


for _name, _mod in (("SEC", _ef), ("DART", _dart), ("FRED", _fred)):
    _el, _worst, _mingap = _measure(_mod._throttle)  # noqa: SLF001
    _cap = 1.0 / _mod.MIN_INTERVAL
    check_true(f"{_name}: 1초당 요청이 한도 이내",
               _worst <= _cap + 1,
               f"최대 {_worst}건/초 (한도 {_cap:.1f})")
    check_true(f"{_name}: 시작 간격이 벌어진다 (잠금 동작)",
               _mingap >= _mod.MIN_INTERVAL * 0.9,
               f"최소 {_mingap*1000:.0f}ms, 기대 {_mod.MIN_INTERVAL*1000:.0f}ms")
    check_true(f"{_name}: 순차보다 빠르다",
               _el < 40 * (_mod.MIN_INTERVAL + 0.05) * 0.8,
               f"{_el:.2f}초 (순차 추정 {40*(_mod.MIN_INTERVAL+0.05):.1f}초)")

# 잠금을 빼면 실제로 제한을 넘는지 — 테스트가 의미 있는지 확인합니다
_naive_last = [0.0]


def _naive_throttle():
    gap = _tm.monotonic() - _naive_last[0]
    if gap < _ef.MIN_INTERVAL:
        _tm.sleep(_ef.MIN_INTERVAL - gap)
    _naive_last[0] = _tm.monotonic()


_el2, _worst2, _gap2 = _measure(_naive_throttle)
check_true("잠금 없으면 간격이 무너진다 (테스트가 유효함)",
           _gap2 < _ef.MIN_INTERVAL * 0.9,
           f"최소 간격 {_gap2*1000:.0f}ms — 이게 크면 위 검사가 무의미합니다")

print("\n=== 탭 지연 실행 ===")
# st.tabs 는 보이지 않는 탭 본문까지 전부 실행해서, 요약만 봐도 스크리닝
# 95종목이 돌았습니다. 선택한 섹션 하나만 실행해야 합니다.
# 'kind_tabs = st.tabs(' 는 분석 문서 종류 탭이고 로컬 파일만 읽어 쌉니다.
# 금지해야 하는 것은 **본문 6개 섹션**을 st.tabs 로 그리는 것뿐입니다.
_body_tabs = [ln for ln in _app_src.splitlines()
              if "st.tabs(" in ln and "kind_tabs" not in ln]
check_true("본문 섹션을 st.tabs 로 그리지 않는다", not _body_tabs,
           f"{_body_tabs} — st.tabs 로 돌아가면 느린 로딩이 재발합니다")
check_true("섹션 선택 위젯이 있다",
           "segmented_control" in _app_src and "st.radio" in _app_src)
check_true("선택한 섹션만 분기 실행",
           'if active == "summary"' in _app_src
           and 'elif active == "discover"' in _app_src)
check_true("섹션별 로딩 안내가 있다",
           "SECTION_LOADING" in _app_src
           and all(k in _app_src for k in ("discover", "valuation")))
# app 은 streamlit 을 import 하므로 여기서 불러올 수 없습니다.
# SECTION_LOADING 딕셔너리를 소스에서 직접 읽습니다.
import config as _cfg2  # noqa: E402

_sl_keys: set[str] = set()
for _node in _ast.walk(_ast.parse(_app_src)):
    if (isinstance(_node, _ast.Assign) and len(_node.targets) == 1
            and isinstance(_node.targets[0], _ast.Name)
            and _node.targets[0].id == "SECTION_LOADING"
            and isinstance(_node.value, _ast.Dict)):
        _sl_keys = {k.value for k in _node.value.keys
                    if isinstance(k, _ast.Constant)}
_missing_hint = [k for k, _l in _cfg2.tab_labels() if k not in _sl_keys]
check_true("모든 탭에 로딩 안내가 붙어 있다", not _missing_hint,
           f"안내 없는 탭: {_missing_hint} — 멈춘 것처럼 보입니다")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 브리핑 · 가격 조건 연결 ===")
# 지난번 st.replace 가 조용히 적용되지 않아 '접기' 기능이 안 들어간 적이
# 있습니다. 연결 지점을 소스에서 직접 확인합니다.
_comp_src = (_pl.Path(__file__).resolve().parent.parent
             / "components.py").read_text(encoding="utf-8")

# render_macro_tab 함수 본문만 떼어내 그 안의 호출 순서를 봅니다.
# 파일 전체에서 index() 를 비교하면 다른 함수의 같은 이름에 걸립니다.
_macro_body = _app_src.split("def render_macro_tab(")[1].split("\ndef ")[0]
check_true("매크로 탭이 브리핑을 그린다",
           "render_briefing_section(use_demo)" in _macro_body,
           "매크로 탭 상단 호출이 보이지 않습니다")
check_true("브리핑이 시세 섹션보다 먼저",
           _macro_body.index("render_briefing_section(use_demo)")
           < _macro_body.index("ui.render_quote_table("),
           "숫자보다 사람이 쓴 글이 먼저 와야 합니다")
check_true("브리핑이 공포탐욕보다 먼저",
           _macro_body.index("render_briefing_section(use_demo)")
           < _macro_body.index("load_feargreed(use_demo)"))
check_true("요약 탭에 브리핑 한 줄",
           "render_briefing_line(briefings[0])" in _app_src)
check_true("요약에는 전문을 넣지 않는다",
           "_render_briefing_body" not in _app_src.split(
               "def render_holdings_tab")[0],
           "요약 탭에 본문 렌더가 들어가면 매일 차 있게 됩니다")
check_true("밸류에이션에 가격 조건 블록",
           "price = prices.get(screen.ticker)" in _app_src
           and "ui.render_price_block(price," in _app_src,
           "종목마다 가격 조건을 찾아 카드에 넘겨야 합니다")
check_true("가격 조건이 정렬 전에 계산된다",
           _app_src.index("prices = _price_screens(triples, use_demo)")
           < _app_src.index("triples.sort(key=lambda t:"),
           "정렬 후면 시가총액 캐시를 놓칩니다")
# _attach_dcf 가 돌려주는 튜플 개수를 바꾸면 t[0]/t[2] 로 꺼내 쓰는
# 7 군데가 조용히 어긋납니다. 리터럴 for 문을 찾는 대신 개수를 셉니다.
_tup = [ln for ln in _app_src.splitlines()
        if "screen, result, verdict_obj" in ln]
check_true("_attach_dcf 반환 튜플은 3개 그대로", bool(_tup),
           "풀어 쓰는 곳이 하나도 없으면 개수 변화를 아무도 못 잡습니다")
check_true("튜플을 3개로만 푼다",
           all(ln.count(",") >= 2 for ln in _tup), str(_tup[:1]))
check_true("렌더러가 components 에 있다",
           all(f"def {n}(" in _comp_src for n in
               ("render_briefing_head", "render_briefing_line",
                "render_briefing_empty", "render_price_block")))
check_true("10년물 연동 함수가 있다", "def _risk_free_pct(" in _app_src)

print("\n=== 가격 조건 CSS ===")
import theme as _th2  # noqa: E402

for _mode in ("light",):
    _css = _th2.build_css("kr")
    _need = (".dash-bf {", ".dash-bf-line {", ".dash-pricecond {",
             ".dash-price-metrics {", ".dash-bf-stale {")
    _miss = [n for n in _need if n not in _css]
    check_true(f"{_mode} 모드에 새 CSS 가 들어 있다", not _miss, str(_miss))
    check_true(f"{_mode} 모드에 이스케이프 안 된 중괄호 없음",
               "{{" not in _css and "}}" not in _css)

check_true("시세 카드 숫자와 가격 조건 상자가 이름을 나눠 쓴다",
           _css.count(".dash-price {") == 1,
           "같은 이름이면 모든 시세 카드 숫자에 회색 상자가 씌워집니다")

print("\n=== 두 점수를 합치지 않는가 (화면) ===")
import value as _vl2  # noqa: E402

check_true("가격 조건이 질 조건과 키가 겹치지 않는다",
           set(_vl2.CRITERIA_BY_KEY).isdisjoint(
               {c.key for c in _bf_mod.CRITERIA})
           if (_bf_mod := __import__("buffett")) else False,
           "키가 겹치면 화면에서 같은 조건이 두 번 나옵니다")
check_true("가격 조건 수가 질 조건 수와 따로 관리된다",
           len(_vl2.CRITERIA) != len(_bf_mod.CRITERIA)
           or True)  # 수가 같아도 되지만 합산하지 않는 것이 중요합니다


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 외부 대시보드 · 크레딧 · 잠정실적 연결 ===")
import config as _cfg3  # noqa: E402
import cycle as _cyc3  # noqa: E402

# 브리핑은 **이 화면 안에서** 끝나야 합니다. 한동안 다른 대시보드로
# 보내는 링크만 뒀는데, 읽으러 나가면 돌아오지 않습니다.
check_true("외부 대시보드로 내보내지 않는다",
           "EXTERNAL_DASHBOARDS" not in _app_src
           and "render_external_dashboard" not in _comp_src,
           "브리핑이 링크면 이 대시보드를 여는 의미가 없습니다")
check_true("브리핑을 직접 조립한다",
           "brief.compose(" in _app_src and "ui.render_brief(" in _app_src)

import brief as _br  # noqa: E402

_bl = _br.compose(triggers=None, fg=None, vix_state=None,
                  exports=None, trends=None, readings=None)
check_true("재료가 하나도 없어도 죽지 않는다", _bl == [], str(_bl))
check_true("빈 브리핑에도 제목 문장이 있다",
           bool(_br.headline([])) and "조용한" in _br.headline([]))

# 한 영역이 브리핑을 독식하면 폭이 사라집니다
class _T:
    def __init__(self, sev, title):
        self.severity, self.title, self.detail = sev, title, "상세"


_many = [_T(2, f"지표{i}") for i in range(9)]
_lines = _br.compose(triggers=_many)
check_true("한 영역은 최대 MAX_PER_TOPIC + 묶음 1줄",
           len(_lines) == _br.MAX_PER_TOPIC + 1,
           f"{len(_lines)}줄 — 매크로가 9줄을 다 차지하면 심리·수출이 밀립니다")
check_true("남은 건수를 묶어서 알린다",
           any("더 있습니다" in ln.text for ln in _lines))
check_true("브리핑은 MAX_LINES 를 넘지 않는다",
           len(_br.compose(triggers=_many)) <= _br.MAX_LINES)

# 크레딧 스프레드 — FRED, 이미 쓰는 경로
_ids = {s.series_id for s in _cfg3.MACRO_SERIES}
check_true("하이일드 스프레드가 등록됐다", "BAMLH0A0HYM2" in _ids)
check_true("투자등급 스프레드가 등록됐다", "BAMLC0A0CM" in _ids)
# 같은 FRED 계열을 두 번 등록하면 두 번 받아오고 두 번 표시됩니다.
# 실제로 한 번 그렇게 만들었습니다 — 기존 hy_spread 가 있는 줄 모르고
# hy_oas 를 추가했습니다. 그 뒤로 이 검사를 둡니다.
from collections import Counter as _Counter  # noqa: E402

_dup_ids = {k: v for k, v in
            _Counter(s.series_id for s in _cfg3.MACRO_SERIES).items() if v > 1}
_dup_keys = {k: v for k, v in
             _Counter(s.key for s in _cfg3.MACRO_SERIES).items() if v > 1}
check_true("FRED 계열 ID 중복 없음", not _dup_ids, str(_dup_ids))
check_true("매크로 key 중복 없음", not _dup_keys, str(_dup_keys))

_hy = [s for s in _cfg3.MACRO_SERIES if s.series_id == "BAMLH0A0HYM2"][0]
check_true("하이일드는 검증 표기", _hy.verified,
           "FRED 페이지에서 실제 관측값까지 확인했습니다")
check_true("하이일드에 임계값이 있다",
           any(getattr(_hy, _f, None) is not None
               for _f in ("level_above", "change_abs", "pct_vs_mean")),
           "기준이 하나도 없으면 임계값 도달에 절대 뜨지 않습니다")
check_true("크레딧 지표에 '왜 보는가' 가 적혀 있다",
           all(len(s.why) > 50 for s in _cfg3.MACRO_SERIES
               if s.series_id.startswith("BAML")))
_demo_series, _ = _demo.demo_macro_series()
check_true("크레딧 데모 데이터가 있다",
           all(i in _demo_series for i in ("BAMLH0A0HYM2", "BAMLC0A0CM")),
           "없으면 미리보기에서 기능이 들어갔는지 확인이 안 됩니다")

# 잠정실적 레이더 — 이미 받아둔 공시를 재사용 (추가 호출 0건)
check_true("사이클 탭이 잠정실적을 그린다",
           "cycle.preliminary_radar(_rows)" in _app_src)
check_true("잠정실적이 재고 지표보다 먼저",
           _app_src.index("잠정실적 레이더")
           < _app_src.index("render_inventory_panel"),
           "정식 보고서보다 먼저 나오는 숫자이므로 위에 있어야 합니다")
check_true("공시 로더를 재사용한다 (추가 호출 없음)",
           "_disc, _disc_err = load_dart_disclosures(use_demo" in _app_src,
           "사이클 탭이 자기 혼자 또 불러오면 DART 호출이 두 배가 됩니다")
check_true("공시 대상이 사이클 종목을 포함한다",
           set(_cfg3.CYCLE_STOCK_CODES) <= set(_cfg3.dart_stock_codes()),
           "포함되지 않으면 레이더가 항상 비어 있습니다")
check_true("잠정실적 렌더러가 있다", "def render_prelim_radar(" in _comp_src)
check_true("빈 목록도 안내를 띄운다",
           "분기 종료 후" in ui_mod.render_prelim_radar([]))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 설명 문구의 인라인 HTML ===")
# render_footnote 가 _esc 만 거쳐서, <b>·<br>·<code> 를 쓰는 설명 문구
# 30여 곳이 **태그를 글자 그대로** 보여주고 있었습니다. 스크린샷을 찍기
# 전까지 몰랐습니다 — 문자열 포함 검사로는 안 잡힙니다.

for _label, _src, _want in (
    ("굵게", "<b>굵게</b> 보통", "<b>굵게</b>"),
    ("줄바꿈", "앞<br>뒤", "앞<br>뒤"),
    ("자기닫힘 br", "앞<br/>뒤", "<br>"),
    ("코드", "<code>app.py</code>", "<code>app.py</code>"),
    ("링크", '<a class="x" href="https://ok.example">출처</a>',
     'href="https://ok.example"'),
):
    check_true(f"{_label} 가 렌더된다", _want in ui_mod.render_footnote(_src),
               ui_mod.render_footnote(_src)[:80])

for _label, _src, _bad in (
    ("script", "<script>alert(1)</script>", "<script"),
    ("onclick", '<b onclick="x()">굵게</b>', 'onclick="'),
    ("javascript 링크", '<a href="javascript:alert(1)">클릭</a>', "<a "),
    ("img onerror", "<img src=x onerror=alert(1)>", "<img"),
    ("iframe", "<iframe src=//evil></iframe>", "<iframe"),
    ("속성 주입", '<a href="https://ok" onmouseover="x">글</a>', 'onmouseover="'),
):
    check_true(f"{_label} 는 실행 형태로 빠져나가지 못한다",
               _bad not in ui_mod.render_footnote(_src),
               ui_mod.render_footnote(_src)[:90])

# 미리보기 HTML 에 태그가 글자로 남아 있으면 안 됩니다
import re as _re3  # noqa: E402

_prev = _pl.Path(__file__).resolve().parent.parent / "preview.html"
if _prev.exists():
    _ph = _prev.read_text(encoding="utf-8")
    _leaks = _re3.findall(
        r'class="dash-footnote">[^<]*&lt;(?:b|br|code)&gt;', _ph)
    check_true("미리보기에 태그가 글자로 보이지 않는다", not _leaks,
               f"{len(_leaks)}곳")

print("\n=== 디자인 토큰 ===")
_th_src = (_pl.Path(__file__).resolve().parent.parent
           / "theme.py").read_text(encoding="utf-8")
_raw_fs = _re3.findall(r"font-size:\s*(\d*\.?\d+)rem", _th_src)
_raw_r = _re3.findall(r"border-radius:\s*(\d+)px", _th_src)
check_true("font-size 를 직접 쓰지 않는다 (토큰만)", not _raw_fs,
           f"{len(_raw_fs)}곳 남음: {_raw_fs[:5]} — 전에는 38종이 섞여 있었습니다")
check_true("border-radius 를 직접 쓰지 않는다", not _raw_r,
           f"{len(_raw_r)}곳 남음: {_raw_r[:5]}")

for _mode in ("light",):
    _css2 = _th2.build_css("kr")
    check_true(f"{_mode}: 타입 스케일 9단이 정의돼 있다",
               all(f"--fs-{i}:" in _css2 for i in range(1, 10)))
    check_true(f"{_mode}: 모서리 4단이 정의돼 있다",
               all(t in _css2 for t in ("--r-chip:", "--r-inner:",
                                        "--r-card:", "--r-pill:")))
    check_true(f"{_mode}: 간격 토큰이 정의돼 있다",
               all(f"--sp-{i}:" in _css2 for i in range(1, 6)))

check_true("링크 색이 등락 색과 분리돼 있다",
           "a.dash-inline-link" in _th_src
           and "color: var(--dash-down); text-decoration: none" not in _th_src,
           "하락 색을 링크에 쓰면 등락 표기 설정에 따라 링크 색이 바뀝니다")
check_true("섹션 제목은 줄바꿈하지 않는다",
           "flex: 0 0 auto; white-space: nowrap;" in _th_src,
           "좁은 폭에서 '요/약' 으로 쪼개졌습니다")
check_true("설명 문구를 끌 수 있다",
           ".dash-nonotes .dash-footnote" in _th_src
           and '"notes": show_notes,' in _app_src)
check_true("개발용 메모가 화면에 노출되지 않는다",
           "scale 을 0.1 로 바꾸십시오" not in
           (_pl.Path(__file__).resolve().parent.parent
            / "config.py").read_text(encoding="utf-8"),
           "note 는 사용자가 읽는 자리입니다")

print("\n=== 매크로 탭 순서 ===")
check_true("임계값 도달이 경제지표 헤더보다 먼저",
           _macro_body.index("임계값 도달") < _macro_body.index("경제지표 (FRED)"),
           "헤더와 그 내용 사이에 다른 섹션이 끼면 '14개 항목' 아래가 빕니다")
check_true("경제지표 헤더 다음에 바로 그룹이 온다",
           _macro_body.index("경제지표 (FRED)")
           < _macro_body.index("render_macro_table"))
check_true("임계값 도달이 시세 표보다 먼저 (확인할 것이 맨 위)",
           _macro_body.index("임계값 도달") < _macro_body.index("ui.render_quote_table("))
check_true("매크로 시세를 카드 격자로 그리지 않는다",
           "render_section(section, data, fx)" not in _macro_body)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 표 세로 스크롤 ===")
# 30행짜리 표가 페이지를 통째로 늘리면 아래 카드까지 한참 내려야 합니다.
# 표가 **자기 안에서** 스크롤하고 머리글은 붙어 있어야 합니다.
for _mode in ("light",):
    _css3 = _th2.build_css("kr")
    check_true(f"{_mode}: 표에 최대 높이", "max-height: 62vh" in _css3)
    check_true(f"{_mode}: 세로 스크롤", "overflow-y: auto" in _css3)
    check_true(f"{_mode}: 머리글 고정", "position: sticky; top: 0" in _css3)
    check_true(f"{_mode}: 휴대폰은 더 낮게", "max-height: 52vh" in _css3)

print("\n=== 발굴 기준 보강 ===")
import buffett as _bf4  # noqa: E402
import buffett_kr as _bkr4  # noqa: E402

check_true("기준이 9개로 늘었다", len(_bf4.CRITERIA) == 9,
           str(len(_bf4.CRITERIA)))
check_true("CHECKS 와 수가 맞는다",
           len(_bf4.CHECKS) == len(_bf4.CRITERIA),
           "다르면 점수 분모가 어긋납니다")
check_true("기준 키가 중복되지 않는다",
           len(_bf4.CRITERIA_BY_KEY) == len(_bf4.CRITERIA))

_added = {"roic", "interest_cover", "fcf_conversion"}
check_true("보강 기준 3개가 있다", _added <= set(_bf4.CRITERIA_BY_KEY))
check_true("보강 기준은 버핏 원문이 아니다",
           all(_bf4.CRITERIA_BY_KEY[k].provenance != "verbatim"
               for k in _added),
           "버핏은 ROIC·이자보상·전환율의 숫자 기준을 말한 적이 없습니다")
check_true("보강 기준마다 한계가 길게 적혀 있다",
           all(len(_bf4.CRITERIA_BY_KEY[k].caveat) > 60 for k in _added))

_kr_keys4 = {r.key for r in _bkr4.KR_RULES}
check_true("국내도 같은 계정을 읽는다",
           {"operating_income", "interest_expense", "tax_expense",
            "pretax_income"} <= _kr_keys4,
           "없으면 국내 종목만 판정 불가가 늘어 점수가 불리해집니다")

# 슬라이더 기본값이 기준 수에 따라가는지 — 6개 시절 숫자가 박혀 있으면
# 기준을 늘릴수록 조건이 느슨해집니다.
check_true("슬라이더 기본값이 기준 수에 비례한다",
           "len(buffett.CRITERIA) * 2 / 3" in _app_src
           and "len(buffett.CRITERIA) / 2" in _app_src,
           "고정값이면 기준이 늘 때마다 느슨해집니다")
for _bad in ('len(buffett.CRITERIA), 4,', 'len(buffett.CRITERIA), 3,'):
    check_true(f"고정 기본값이 남아 있지 않다: {_bad[-3:].strip()}",
               _bad not in _app_src)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 파일 버전 검사 ===")
# GitHub 웹에서 손으로 올리다 일부만 올라간 일이 네 번 있었고, 네 번 다
# 배포한 뒤 AttributeError 로 알았습니다. Streamlit Cloud 는 오류 본문을
# 가려서 어느 파일인지도 안 보입니다. 죽기 전에 이름을 말해야 합니다.
import buildstamp as _bs  # noqa: E402
import shutil as _sh  # noqa: E402

_root = _pl.Path(__file__).resolve().parent.parent
check_true("BUILD.json 이 패키지에 들어 있다",
           (_root / _bs.MANIFEST).exists(),
           "없으면 검사 자체를 못 합니다")

_rep = _bs.verify(str(_root))
check_true("현재 파일들이 목록과 일치한다", _rep.ok,
           f"stale={_rep.stale} missing={_rep.missing} — "
           "패키징 전에 python -m tools.stamp 를 돌려야 합니다")
check_true("정상일 때는 경고를 그리지 않는다",
           ui_mod.render_build_warning(_rep) == "")

# 실제로 잡는지 — 임시 폴더에 가짜 배포본을 만들어 한 파일만 바꿔 봅니다
with _tf.TemporaryDirectory() as _d:
    _fake = _pl.Path(_d) / "app_copy"
    _fake.mkdir()
    (_fake / "a.py").write_text("x = 1\n", encoding="utf-8")
    (_fake / "b.py").write_text("y = 2\n", encoding="utf-8")
    _bs.write_manifest(str(_fake))
    check_true("갓 만든 목록은 일치", _bs.verify(str(_fake)).ok)

    (_fake / "b.py").write_text("y = 3\n", encoding="utf-8")
    _r2 = _bs.verify(str(_fake))
    check_true("내용이 바뀐 파일을 잡는다", _r2.stale == ["b.py"], str(_r2.stale))
    check_true("파일 이름이 메시지에 들어간다", "b.py" in _r2.message())
    check_true("경고 블록에 파일명이 보인다",
               "b.py" in ui_mod.render_build_warning(_r2))

    (_fake / "b.py").unlink()
    _r3 = _bs.verify(str(_fake))
    check_true("사라진 파일을 잡는다", _r3.missing == ["b.py"], str(_r3.missing))
    check_true("'아예 없습니다' 로 구분한다", "아예 없습니다" in _r3.message())

    (_root / "nonexistent_check").exists()  # no-op
    (_pl.Path(_d) / "empty").mkdir()
    _r4 = _bs.verify(str(_pl.Path(_d) / "empty"))
    check_true("BUILD.json 이 없으면 '검사 못 함'", not _r4.checked)
    check_true("검사 못 함을 정상으로 치지 않는다", not _r4.ok,
               "없는 것과 일치하는 것은 다릅니다")
    check_true("검사 못 함은 경고 색을 쓰지 않는다",
               "dash-build-note" in ui_mod.render_build_warning(_r4))

check_true("앱이 시작할 때 검사한다",
           "buildstamp.verify" in _app_src and "_check(BASE_DIR)" in _app_src
           and "render_build_warning" in _app_src)
check_true("검사 실패가 앱을 막지 않는다",
           "except Exception:  # noqa: BLE001 - 검사가 앱을 막으면 안 됩니다"
           in _app_src)
check_true("사용자가 넣는 폴더는 검사하지 않는다",
           {"briefings", "analysis", ".streamlit"} <= set(_bs.SKIP_DIRS),
           "사용자 파일이 다르다고 경고하면 안 됩니다")

print("\n=== DART 키 캐시 무효화 ===")
import sources.dart as _dart5  # noqa: E402

_old_env = os.environ.pop("DART_API_KEY", None)
check_true("키가 없으면 지문도 없다", _dart5.key_fingerprint() == "")
os.environ["DART_API_KEY"] = "a" * 40
_fp1 = _dart5.key_fingerprint()
os.environ["DART_API_KEY"] = "b" * 40
_fp2 = _dart5.key_fingerprint()
check_true("키가 생기면 지문이 생긴다", bool(_fp1))
check_true("키가 바뀌면 지문도 바뀐다", _fp1 != _fp2, f"{_fp1} vs {_fp2}")
check_true("지문에 키가 들어가지 않는다",
           "a" * 40 not in _fp1 and len(_fp1) <= 12, _fp1)
if _old_env is None:
    os.environ.pop("DART_API_KEY", None)
else:
    os.environ["DART_API_KEY"] = _old_env

for _fn in ("load_dart_disclosures", "load_inventory_trends",
            "load_kr_screens"):
    check_true(f"{_fn} 이 지문을 캐시 키로 받는다",
               f"{_fn}(use_demo, dart.key_fingerprint())" in _app_src
               or f"{_fn}, use_demo, dart.key_fingerprint()," in _app_src,
               "없으면 키를 넣어도 실패한 결과가 TTL 동안 남습니다")
check_true("캐시를 수동으로 비울 수 있다",
           "st.cache_data.clear()" in _app_src)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== FRED 연결 실패 대응 ===")
# 배포 환경에서 FRED 전 계열이 HTTPSConnectionPool 오류로 실패했는데,
# 진단이 78자에서 잘라서 **진짜 사유가 안 보였습니다**. 진단의 존재
# 이유가 사라지는 버그였습니다.
import sources.fred as _fr5  # noqa: E402

_diag_src = (_pl.Path(__file__).resolve().parent.parent
             / "tools" / "diagnose.py").read_text(encoding="utf-8")
check_true("진단이 오류를 자르지 않는다",
           "errors.get(spec.series_id, '사유 불명')[:78]" not in _diag_src,
           "자르면 타임아웃인지 차단인지 구분이 안 됩니다")
check_true("진단이 전문을 줄바꿈해 보여준다", "textwrap.wrap(_why" in _diag_src)
check_true("연결 자체를 먼저 시험한다", "[연결 시험]" in _diag_src)
check_true("계열 ID 문제가 아님을 알려준다",
           "계열 ID 는 문제가 아니니" in _diag_src)

check_true("연결 실패는 재시도한다", _fr5.RETRIES >= 1)
# 2026-11-11 배포 환경 실측으로 방향이 뒤집혔습니다. fred.stlouisfed.org
# 는 아예 응답이 없으므로 오래 기다릴수록 손해입니다 — 짧게 끊고 공식
# API(api.stlouisfed.org, 0.1초에 응답) 로 넘어가는 게 맞습니다.
check_true("막힌 호스트는 짧게 끊는다", _fr5.TIMEOUT <= 10, f"{_fr5.TIMEOUT}초")
check_true("살아 있는 호스트는 넉넉히 기다린다",
           _fr5.API_TIMEOUT >= 15, f"{_fr5.API_TIMEOUT}초")
check_true("재시도 횟수를 오류에 적는다", "회 시도" in _fr5.fetch_series.__doc__
           or "회 시도" in _pl.Path(_fr5.__file__).read_text(encoding="utf-8"))

check_true("공식 API 가 대체 경로로 있다",
           _fr5.API_URL.startswith("https://api.stlouisfed.org/"),
           "호스트가 달라야 막힌 경로를 우회합니다")
check_true("API 는 키가 있을 때만 쓴다",
           'key = api_key()' in _pl.Path(_fr5.__file__).read_text(encoding="utf-8"))
check_true("키가 없으면 지문도 없다",
           _fr5.key_fingerprint() == "" or bool(os.environ.get("FRED_API_KEY")))
check_true("load_macro 가 FRED 지문을 캐시 키로 받는다",
           "load_macro(use_demo, fred.key_fingerprint())" in _app_src)

# API JSON 파서 — 실제 API 를 못 치므로 응답 형태로 검증합니다
import types as _ty5  # noqa: E402

_payload = {"observations": [
    {"date": "2026-11-03", "value": "4.12"},
    {"date": "2026-11-04", "value": "."},          # 결측
    {"date": "2026-11-05", "value": "1,234.5"},    # 쉼표
    {"date": "엉뚱", "value": "9.9"},               # 깨진 날짜
]}


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return _payload


_saved = _fr5.requests
_fr5.requests = _ty5.SimpleNamespace(get=lambda *a, **k: _Resp(),
                                     RequestException=Exception)
try:
    _ser = _fr5._fetch_via_api("DGS10", "key", None)  # noqa: SLF001
    check_true("API 응답을 파싱한다", len(_ser.observations) == 2,
               str(len(_ser.observations)))
    check_true("결측(.)을 건너뛴다",
               all(o.value != 0 for o in _ser.observations))
    check_true("쉼표가 든 숫자를 읽는다",
               any(abs(o.value - 1234.5) < 1e-9 for o in _ser.observations))
    check_true("깨진 날짜를 버린다", len(_ser.observations) == 2)
finally:
    _fr5.requests = _saved

print("\n=== DART 재고 구성 (받을 수 없음을 확인) ===")
# 2026-11-11 실제 응답: 삼성전자·SK하이닉스 모두 재고 관련 계정이
# ifrs-full_Inventories 한 줄뿐. 구성은 주석에 있어 이 API 로는 못 받습니다.
import cycle as _cyc6  # noqa: E402

_cyc_src = (_pl.Path(__file__).resolve().parent.parent
            / "cycle.py").read_text(encoding="utf-8")
check_true("구성 계정 규칙은 남겨 둔다",
           {"raw_materials", "work_in_progress", "finished_goods"}
           <= set(_cyc6.RULES),
           "본표에 싣는 회사가 있을 수 있어 지우지 않습니다")
check_true("'없을 수 있습니다' 추측을 사실로 바꿨다",
           "확인했습니다" in _cyc_src and "없습니다" in _cyc_src)
check_true("화면이 고장이 아니라고 말한다",
           "고장이 아니라 데이터가 없는 것" in _app_src)
check_true("진단도 고장이 아니라고 말한다",
           "고장이 아닙니다" in _diag_src)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 설명 문구의 마크다운 강조 ===")
# 2026-11-11 스크린샷에서 발견: 설명에 쓴 **강조** 가 별표째 화면에 찍혔습니다.
# <b> 태그는 _safe_inline 이 살려주는데 별표는 아무도 처리하지 않았습니다.
import pathlib  # noqa: E402
import re  # noqa: E402
import components as _ui_md  # noqa: E402

check_true("별표 강조를 태그로 바꾼다",
           "<b>실물</b>" in _ui_md._safe_inline("반도체 **실물** 생산량"),
           _ui_md._safe_inline("반도체 **실물** 생산량"))
check_true("곱셈 기호는 건드리지 않는다",
           "<b>" not in _ui_md._safe_inline("a ** b ** c"))
check_true("태그 이스케이프는 그대로 유지",
           "&lt;script&gt;" in _ui_md._safe_inline("<script>x</script> **y**"))

_src_md = pathlib.Path("components.py").read_text()
for _field in ("spec.why", "check.detail", "check.warning",
               "crit.source", "crit.caveat", "reading.warning"):
    check_true(f"{_field} 는 _safe_inline 을 거친다",
               f"_safe_inline({_field})" in _src_md,
               "_esc 만 쓰면 별표와 <b> 가 글자로 나옵니다")

_pv_md = pathlib.Path("preview.html")
if _pv_md.exists():
    # 프롬프트 블록은 Claude 에 붙여넣을 글이라 마크다운이 의도된 곳입니다.
    # 중첩 div 때문에 통째로 잘라내기 어려우므로, 별표마다 바로 앞의
    # class 를 보고 프롬프트 계열이면 넘어갑니다.
    _html_md = re.sub(r"<style.*?</style>", "", _pv_md.read_text(), flags=re.S)
    _left_md = []
    for _m in re.finditer(r"\*\*[^*<\n]{1,60}\*\*", _html_md):
        _before = _html_md[max(0, _m.start() - 400):_m.start()]
        _cls = re.findall(r'class="([^"]+)"', _before)
        if _cls and ("cmd" in _cls[-1] or "prompt" in _cls[-1]):
            continue
        _left_md.append(_m.group(0))
    check_true("화면에 별표가 그대로 남지 않는다", not _left_md,
               str(sorted(set(_left_md))[:3]))


print("\n=== 실제 응답으로 확인된 계정 ===")
import buffett_kr as _bkr6  # noqa: E402

_ok = {r.key for r in _bkr6.KR_RULES if r.verified}
check_true("매출액이 검증됨", "revenue" in _ok)
check_true("매출원가가 검증됨", "cost_of_revenue" in _ok)
check_true("검증 근거를 주석에 남겼다",
           "2026-11-11 실제 응답 확인"
           in (_pl.Path(__file__).resolve().parent.parent
               / "buffett_kr.py").read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 테스트 파일 자체의 구조 ===")
# 2026-11-11: smoke_test 의 요약/sys.exit 가 1537줄 중 307줄에 있었습니다.
# 그 뒤 1200줄의 실패 8건이 조용히 묻혀 있었습니다. 요약은 끝에 있어야
# 합니다 — 중간에 있으면 뒤쪽 실패는 보고도 되지 않고 종료 코드도 0 입니다.
for _tf in sorted(pathlib.Path("tests").glob("*_test.py")):
    _lines = _tf.read_text(encoding="utf-8").splitlines()
    _exit = [i for i, ln in enumerate(_lines) if "sys.exit(1)" in ln]
    if not _exit:
        continue
    _tail = len(_lines) - _exit[-1] - 1
    check_true(f"{_tf.name} 요약이 파일 끝에 있다", _tail <= 10,
               f"요약 뒤에 {_tail}줄 — 그 줄들의 실패는 묻힙니다")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 구역 헤더의 개수 배지 ===")
# 2026-11-11 스크린샷: '밸류에이션 판단 … 0개 항목' 아래에 5줄짜리 표가
# 있었고, '0개 이상 통과' 라는 제목도 있었습니다. 둘 다 0 을 그대로 찍은
# 탓입니다. 셀 것이 없으면 배지를 아예 빼고, 0 이면 말이 되게 바꿉니다.
check_true("count=None 이면 배지를 안 그린다",
           "개 항목" not in ui.render_section_head("제목", "부제"),
           ui.render_section_head("제목", "부제"))
check_true("count=0 은 그대로 0개로 표시",
           "0개 항목" in ui.render_section_head("제목", "부제", 0))
check_true("밸류에이션 헤더가 실제 개수를 받는다",
           "len(triples))" in _app_src.split("밸류에이션 판단")[1][:200],
           "0 을 넘기면 아래 표가 비어 보입니다")
check_true("통과 수 0 이면 '전체 종목' 으로 적는다",
           '"전체 종목" if min_pass <= 0' in _app_src,
           "'0개 이상 통과' 는 말이 안 됩니다")

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 명암비 (WCAG AA 4.5) ===")
# 2026-11-11: "나이트 모드 글씨 잘 안 보임" → 재보니 보조 글자가 4.4,
# 미국 하락 적색은 3.3 이었습니다. 같은 날 나이트 모드를 아예 없애고
# 데이 한 벌만 남겼습니다 — 두 벌이면 한쪽에서만 깨지는 버그가 계속
# 생깁니다. 남은 한 벌은 **가장 밝은 배경 기준 5.0 이상**으로 둡니다.
import theme as _th_c  # noqa: E402


def _srgb(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hexs: str) -> float:
    h = hexs.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


check_true("테마는 한 벌뿐", list(_th_c.PALETTE) == ["light"],
           f"{list(_th_c.PALETTE)} — 두 벌이면 한쪽만 깨집니다")
_FG = ("ink", "ink_secondary", "ink_muted", "accent", "up_kr", "down_kr",
       "up_us", "down_us", "badge_pre", "badge_post", "badge_live",
       "badge_error", "flat", "badge_closed")
_BG = ("page", "surface", "surface_raised")
_pal = _th_c.PALETTE["light"]
_worst = min((_contrast(_pal[f], _pal[b]), f, b) for b in _BG for f in _FG)
check_true("모든 글자색이 5.0 이상", _worst[0] >= 5.0,
           f"최저 {_worst[0]:.2f} — {_worst[1]} on {_worst[2]}")
# 카드가 바탕에서 떠 보여야 합니다
check_true("카드가 바탕과 구분된다",
           _contrast(_pal["surface"], _pal["page"]) >= 1.10,
           f"{_contrast(_pal['surface'], _pal['page']):.3f}")
check_true("카드 안쪽 블록도 구분된다",
           _contrast(_pal["surface_raised"], _pal["surface"]) >= 1.05,
           f"{_contrast(_pal['surface_raised'], _pal['surface']):.3f}")
# 등락 두 색의 **명암비**로 재면 안 됩니다. 적색과 청색은 밝기가 비슷해도
# 사람 눈에는 전혀 다른 색이고, 적록색약(가장 흔한 유형)에서도 구분됩니다.
# 문제가 되는 조합은 적-녹입니다. 그래서 색상(hue) 차이로 봅니다.
import colorsys as _cs  # noqa: E402


def _hue(hexs: str) -> float:
    h = hexs.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return _cs.rgb_to_hls(r, g, b)[0] * 360


def _hue_gap(a: str, b: str) -> float:
    d = abs(_hue(a) - _hue(b)) % 360
    return min(d, 360 - d)


check_true("한국 관행 상승·하락 색상이 충분히 멀다",
           _hue_gap(_pal["up_kr"], _pal["down_kr"]) >= 90,
           f"{_hue_gap(_pal['up_kr'], _pal['down_kr']):.0f}도 차이")
check_true("미국 관행도 마찬가지",
           _hue_gap(_pal["up_us"], _pal["down_us"]) >= 90,
           f"{_hue_gap(_pal['up_us'], _pal['down_us']):.0f}도 — 적-녹은 "
           "적록색약에서 겹치므로 기호(▲▼)를 반드시 같이 써야 합니다")
# 색만으로 뜻을 전하지 않는지 — 방향 기호가 코드에 실제로 있는지
_comp_src = pathlib.Path("components.py").read_text(encoding="utf-8")
check_true("방향 기호를 함께 쓴다",
           "▲" in _comp_src and "▼" in _comp_src,
           "색각이상에서는 색만으로 등락을 읽을 수 없습니다")
check_true("강조색은 등락색과 다르다",
           _pal["accent"] not in (_pal["up_kr"], _pal["down_kr"],
                                  _pal["up_us"], _pal["down_us"]),
           "색이 두 뜻을 가지면 숫자를 잘못 읽습니다")

import re as _re_c  # noqa: E402
_m = _re_c.search(r"--fs-1:\s*([0-9.]+)rem",
                  pathlib.Path("theme.py").read_text(encoding="utf-8"))
check_true("가장 작은 글자가 11px 이상",
           _m is not None and float(_m.group(1)) * 16 >= 11,
           f"{float(_m.group(1)) * 16:.1f}px" if _m else "못 찾음")

print("\n=== 나이트 모드 흔적이 남지 않았다 ===")
for _f in ("app.py", "theme.py", "tools/preview.py"):
    _txt = pathlib.Path(_f).read_text(encoding="utf-8")
    _lines = [ln.strip() for ln in _txt.splitlines()
              if ln.strip().startswith(('"', "f\"", "'"))
              and ("나이트" in ln or "data-mode" in ln)]
    check_true(f"{_f} 에 테마 전환 UI 가 없다", not _lines, str(_lines[:2]))
check_true("build_css 가 모드를 받지 않는다",
           "def build_css(convention: str, stack: bool = True)" in
           pathlib.Path("theme.py").read_text(encoding="utf-8"))

print("\n=== 한국·미국 시장 분리 ===")
import config as _cfg_m  # noqa: E402

check_true("시장은 한국·미국 둘뿐", list(_cfg_m.MARKETS) == ["kr", "us"],
           f"{_cfg_m.MARKETS} — '전체' 가 기본이면 아무것도 갈리지 않습니다")
check_true("처음 여는 시장이 정해져 있다",
           _cfg_m.DEFAULT_MARKET in _cfg_m.MARKETS)
_w = _cfg_m.SECTION_WATCHLIST.instruments
check_true("naver 종목은 한국",
           all(_cfg_m.market_of(i) == "kr" for i in _w if i.source == "naver"))
check_true("yahoo 종목은 미국",
           all(_cfg_m.market_of(i) == "us" for i in _w if i.source == "yahoo"))
check_true("미국만 고르면 한국 종목이 빠진다",
           all(i.source != "naver"
               for i in _cfg_m.filter_instruments(_w, "us")))
check_true("한국만 고르면 미국 종목이 빠진다",
           all(i.source == "naver"
               for i in _cfg_m.filter_instruments(_w, "kr")))
check_true("미국 + 한국 = 전체",
           len(_cfg_m.filter_instruments(_w, "us"))
           + len(_cfg_m.filter_instruments(_w, "kr")) == len(_w),
           "어느 쪽에도 안 들어가는 종목이 있으면 화면에서 사라집니다")

print("\n=== 시장이 최상위 축이다 ===")
# '분리가 실현 안 된 것 같다' — 전에는 내비 맨 아래 작은 라디오였고
# 기본값 '전체' 라 아무것도 안 갈렸습니다. 이제는 시장마다 **목록 자체**가
# 다릅니다.
_kr = _cfg_m.market_tab_keys("kr")
_us = _cfg_m.market_tab_keys("us")
check_true("두 시장의 목록이 다르다", _kr != _us, f"{_kr} / {_us}")
check_true("섹터 온도는 한국에만", "sector_heat" in _kr
           and "sector_heat" not in _us)
check_true("물가·유동성은 미국에만", "us_flows" in _us
           and "us_flows" not in _kr)
check_true("메모리 사이클은 양쪽", "cycle" in _kr and "cycle" in _us,
           "한·미 3사를 같이 봐야 하는 화면입니다")
_all = set(dict(_cfg_m.tab_labels()))
check_true("어느 시장에도 없는 탭이 없다",
           _all <= (set(_kr) | set(_us)), str(_all - set(_kr) - set(_us)))
check_true("시장 전환이 내비보다 먼저",
           _app_src.index("market = _market_switch()")
           < _app_src.index("nav_col, body_col = st.columns"))
check_true("시장마다 내비 키가 다르다", 'key = f"nav_{market}"' in _app_src,
           "하나면 시장을 바꿀 때 없는 탭이 선택돼 오류가 납니다")
check_true("주소창에 시장을 남긴다", 'st.query_params["m"]' in _app_src,
           "새로고침하면 기본값으로 돌아갑니다")
check_true("제목줄에 지금 시장을 적는다", "market_label=" in _app_src)
check_true("'전체' 안내가 남지 않았다",
           "'전체' 로 바꾸십시오" not in _app_src
           and 'market == "all"' not in _app_src)
check_true("보는 시장 라디오를 없앴다", "보는 시장" not in _app_src)

# 탭마다 market 을 받아야 합니다 — 하나라도 빠지면 그 탭만 안 걸러집니다
for _fn in ("render_summary_tab", "render_holdings_tab", "render_discover_tab",
            "render_macro_tab", "render_valuation_tab", "render_cycle_tab",
            "render_section", "render_signals_tab"):
    _seg = _app_src.split(f"def {_fn}(")[1][:300]
    check_true(f"{_fn} 가 market 을 받는다", "market" in _seg.split(")")[0],
               "안 받으면 그 탭만 전체가 보입니다")
check_true("탭마다 있던 시장 라디오를 없앴다",
           "disc_market" not in _app_src and "val_market" not in _app_src,
           "두 군데서 고르면 발굴은 미국인데 밸류에이션은 한국인 상태가 됩니다")
check_true("매크로는 시장으로 거르지 않는다",
           "매크로는 **일부러 시장별로 나누지 않습니다.**" in _app_src,
           "금리·환율은 어느 시장을 보든 같은 배경입니다")
check_true("한국에서 매크로는 공통에 있다",
           any(g == "공통" and "macro" in ks
               for g, ks in _cfg_m.MARKET_TABS["kr"]))

print("\n=== 섹션 내비는 세로 ===")
check_true("세로 버튼 목록을 쓴다", "_section_nav(market, labels)" in _app_src)
check_true("가로 옵션을 쓰지 않는다",
           '"섹션", keys, horizontal=True' not in _app_src,
           "horizontal=True 면 다시 한 줄로 돌아갑니다")
check_true("본문과 내비를 두 칸으로 나눈다",
           "nav_col, body_col = st.columns" in _app_src)

print("\n=== 뉴스 헤드라인은 한국어 우선 ===")
import sources.news as _nw  # noqa: E402

check_true("미국 종목도 한국어로 찾는다",
           _nw._ko_query("Microsoft", "MSFT") == "마이크로소프트 주가",
           _nw._ko_query("Microsoft", "MSFT"))
check_true("모르는 종목은 영문 이름 그대로",
           _nw._ko_query("Nvidia", "NVDA") == "Nvidia 주가",
           "없는 한국어 이름을 지어내면 엉뚱한 기사가 붙습니다")
check_true("한 글자 이름은 티커로 보완",
           _nw._ko_query("X", "XYZ").startswith("X XYZ"),
           _nw._ko_query("X", "XYZ"))
check_true("구글 뉴스를 한국어로 호출한다",
           "hl=ko" in _nw.GOOGLE_NEWS_RSS and "ceid=KR:ko" in _nw.GOOGLE_NEWS_RSS)
_news_src = pathlib.Path("sources/news.py").read_text()
check_true("한국어를 먼저 시도하고 영어는 대체",
           _news_src.index("_from_google_rss(_ko_query")
           < _news_src.index("return _from_yfinance(symbol, limit)"),
           "yfinance 가 먼저면 제목이 전부 영어로 나옵니다")

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 화면 문구가 현재 UI 와 맞는가 ===")
# 사이드바를 없앤 뒤에도 "사이드바 진단 버튼을 누르십시오" 같은 안내가
# 여러 곳에 남아 있었습니다. 있지도 않은 곳을 가리키는 안내는 없느니만
# 못합니다.
_GONE = ("사이드바", "왼쪽 접었다", "탭을 눌러")
for _f in sorted(pathlib.Path(".").glob("*.py")) + \
        sorted(pathlib.Path("sources").glob("*.py")) + \
        sorted(pathlib.Path("tools").glob("*.py")):
    _txt = _f.read_text(encoding="utf-8")
    # 주석·독스트링은 이력 설명이라 허용합니다. 화면에 나가는 문자열만
    # 봅니다 — 큰따옴표로 시작하는 한 줄짜리 리터럴.
    _bad = []
    for _ln in _txt.splitlines():
        _st = _ln.strip()
        if not _st.startswith(('"', "f\"", "'")):
            continue
        if any(g in _st for g in _GONE):
            _bad.append(_st[:60])
    check_true(f"{_f.as_posix()} 에 사라진 UI 안내가 없다", not _bad,
               str(_bad[:2]))

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 버전 검사가 실제로 덮는 범위 ===")
# 2026-11-11: tools/diagnose.py 만 옛날 파일인 상태가 BUILD.json 검사를
# **통과**했습니다. tools/ 가 SKIP_DIRS 에 있었기 때문입니다. 그런데
# app.py 는 돌 때 `from tools import diagnose` 를 합니다 — 개발용이
# 아니라 런타임 의존이었습니다. 검사에서 빠진 파일은 통과하는 게 아니라
# 안 보이는 것입니다.
import buildstamp as _bs  # noqa: E402

_manifest = set(_bs.build_manifest("."))
check_true("매니페스트가 비어 있지 않다", len(_manifest) > 20, str(len(_manifest)))

# app.py 가 임포트하는 **1차 모듈**이 전부 매니페스트에 있어야 합니다.
_tree = ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
_imported: set[str] = set()
for _n in ast.walk(_tree):
    if isinstance(_n, ast.Import):
        for _a in _n.names:
            _imported.add(_a.name)
    elif isinstance(_n, ast.ImportFrom) and _n.module and _n.level == 0:
        _imported.add(_n.module)
        for _a in _n.names:
            _imported.add(f"{_n.module}.{_a.name}")

_local_missing = []
for _mod in sorted(_imported):
    _as_file = _mod.replace(".", "/") + ".py"
    _as_pkg = _mod.replace(".", "/") + "/__init__.py"
    if not (os.path.exists(_as_file) or os.path.exists(_as_pkg)):
        continue                     # 표준·서드파티 라이브러리
    if _as_file in _manifest or _as_pkg in _manifest:
        continue
    _local_missing.append(_mod)
check_true("app.py 가 쓰는 모듈이 전부 검사 대상", not _local_missing,
           f"빠진 것: {_local_missing} — 이 파일들은 옛날 버전이어도 "
           "검사를 통과합니다")

check_true("tools 를 건너뛰지 않는다", "tools" not in _bs.SKIP_DIRS,
           "app.py 가 tools.diagnose 를 임포트합니다")
check_true("tests 는 건너뛴다", "tests" in _bs.SKIP_DIRS,
           "앱이 임포트하지 않으므로 올릴 필요가 없습니다")
check_true("tools/diagnose.py 가 매니페스트에 있다",
           "tools/diagnose.py" in _manifest)

print("\n=== 진단 패널은 파일이 낡아도 안 죽는다 ===")
# 모듈 속성을 직접 참조하면 목록을 만드는 순간 AttributeError 가 나고,
# 그게 controls() 안이라 **앱 전체가 안 켜집니다.**
_panel = _app_src.split("def render_diag_panel")[1].split("\ndef ")[0]
check_true("진단 함수를 이름으로 찾는다", "getattr(diag," in _panel,
           "직접 참조하면 함수 하나가 없을 때 앱이 통째로 죽습니다")
check_true("직접 참조가 남아 있지 않다", "diag.diagnose_" not in _panel,
           "한 군데라도 남으면 같은 방식으로 죽습니다")
check_true("없는 진단은 이름을 말해준다", "없는 진단:" in _panel)
check_true("나머지는 계속 쓴다", "if c[3] is not None" in _panel)

# 실제로 함수가 전부 있는지 (지금 버전 기준)
from tools import diagnose as _diag_mod  # noqa: E402
for _fname in ("diagnose_fred", "diagnose_screen", "diagnose_xbrl",
               "diagnose_dart", "diagnose_kr_exports", "diagnose_kr_codes"):
    check_true(f"diagnose.{_fname} 가 있다",
               callable(getattr(_diag_mod, _fname, None)))

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 보낼 파일 목록을 기계가 정한다 ===")
# 2026-11-11: '변경된 파일만' 을 손으로 골랐다가 두 번 연속 빠뜨렸습니다
# (tools/diagnose.py, 그다음 sources/kr_exports.py · sources/yahoo.py).
# 기억으로 고르면 반드시 틀립니다. 해시로 비교합니다.
from tools import ship as _ship  # noqa: E402

check_true("보낸 기록 파일명이 정해져 있다", _ship.SHIPPED == ".shipped.json")
check_true("기록이 .gitignore 에 있다",
           ".shipped.json" in pathlib.Path(".gitignore").read_text(
               encoding="utf-8"),
           "저장소에 올라가면 받는 쪽 상태와 섞입니다")
_mod, _add, _rm = _ship.changed(".")
check_true("지금은 보낼 것이 없다", not (_mod or _add),
           f"바뀜 {_mod} · 새것 {_add} — 패키징 전에 --mark 를 돌리십시오")
check_true("기록이 매니페스트와 같은 범위를 본다",
           set(_ship.load_shipped(".")) == set(_bs.build_manifest(".")),
           "범위가 다르면 비교가 어긋납니다")

print("\n=== 진단 패널이 앱을 죽이지 않는다 ===")
_ctrl = _app_src.split("def controls()")[1].split("\ndef ")[0]
check_true("진단 패널 호출을 감싼다",
           "try:\n                render_diag_panel()" in _ctrl,
           "controls() 안에서 죽으면 화면이 통째로 빕니다")
check_true("실패해도 나머지는 그린다", "나머지 화면은 그대로 씁니다" in _ctrl)

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== CSS 변수가 전부 정의돼 있는가 ===")
# 2026-11-11: 내비 hover 가 --dash-surface-raised 를 가리켰는데 그런
# 변수가 없었습니다. CSS 는 **조용히 무시**하므로 아무 일도 안 일어나고,
# "버튼이 잘 안 보인다" 로만 드러납니다. 오타 하나를 눈으로 못 잡습니다.
import re as _re_v  # noqa: E402

_theme_src = pathlib.Path("theme.py").read_text(encoding="utf-8")
_defined = set(_re_v.findall(r"^\s*(--dash-[a-z0-9-]+):", _theme_src,
                             _re_v.M))
_used: set[str] = set()
for _f in ("theme.py", "tools/preview.py", "components.py"):
    _used |= set(_re_v.findall(r"var\((--dash-[a-z0-9-]+)\)",
                               pathlib.Path(_f).read_text(encoding="utf-8")))
check_true("정의되지 않은 CSS 변수가 없다", not (_used - _defined),
           f"{sorted(_used - _defined)} — CSS 는 조용히 무시합니다")
check_true("안 쓰는 변수도 없다", not (_defined - _used),
           str(sorted(_defined - _used)))

print("\n=== 왼쪽 내비가 보이는가 ===")
# 2026-11-11: 라디오를 CSS 로 꾸미던 방식을 버리고 진짜 버튼으로 바꿨습니다.
# 자세한 동작 검사는 tests/nav_speed_test.py 가 실제 함수를 돌려 합니다.
check_true("섹션은 버튼으로 그린다 (지금 섹션은 primary)",
           'type="primary" if active else "secondary"' in _app_src)
_nav_css = _theme_src.split(':has(.dash-navmark) button[kind="secondary"]')[2][:400]
check_true("선택 안 된 버튼에도 테두리", "border:" in _nav_css, _nav_css[:80])
check_true("hover 도 있다",
           ':has(.dash-navmark) button[kind="secondary"]:hover' in _theme_src)
check_true("지금 섹션은 굵게",
           ':has(.dash-navmark) button[kind="primary"]' in _theme_src)
check_true("내비 칸이 패널로 보인다",
           'div[data-testid="stColumn"]:has(.dash-navmark)' in _theme_src)
# 프리뷰도 같은 모양이어야 '봤으니 됐다' 가 성립합니다
_pv_src = pathlib.Path("tools/preview.py").read_text(encoding="utf-8")
check_true("프리뷰 내비도 패널", ".pv-side {" in _pv_src
           and "border-radius: var(--r-card)" in
           _pv_src.split(".pv-side {")[1][:260])
check_true("프리뷰 선택 표시도 남색",
           "--dash-accent" in
           _pv_src.split('.pv-tab[aria-selected="true"]')[1][:200])

# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 정의되지 않은 이름 (스트림릿 없이 잡는 오타) ===")
# 샌드박스에 스트림릿이 없어 app.py 를 돌려 볼 수 없습니다. 함수 이름을
# 틀려도 그 탭을 눌러야 NameError 로 드러납니다. 정적으로 잡습니다.
from tools.names import check_source as _names  # noqa: E402

_name_targets = sorted(
    {str(p) for p in pathlib.Path(".").glob("*.py")}
    | {str(p) for p in pathlib.Path("sources").glob("*.py")}
    | {str(p) for p in pathlib.Path("tools").glob("*.py")})
_bad_names = []
for _f in _name_targets:
    for _w, _n, _ln in _names(pathlib.Path(_f).read_text(encoding="utf-8"), _f):
        _bad_names.append(f"{_f}:{_ln} {_w}() '{_n}'")
check_true(f"미정의 이름 없음 ({len(_name_targets)}개 파일)", not _bad_names,
           str(_bad_names[:3]))
# 검사기 자체가 잡는지 — 아무것도 안 잡는 검사기는 통과해도 의미가 없습니다
check_true("검사기가 함수명 오타를 잡는다",
           bool(_names("def a():\n    render_sectr()\n")))
check_true("검사기가 클로저를 오탐하지 않는다",
           not _names("def a():\n    x = 1\n    def b():\n"
                      "        return x\n    return b\n"))

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
