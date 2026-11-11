"""
뉴스 · 공시 · 지표 테스트.

물가와 유동성은 **산술이라 검증이 가능합니다.** 성질을 아는 인공 계열을
넣고 이론값이 나오는지 봅니다. 공시 분류와 단위 검사는 조용히 틀릴 수
있는 자리라 특히 촘촘하게 봅니다 — 단위를 1000배 틀려도 화면에는
그럴듯한 숫자가 뜹니다.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
import config  # noqa: E402
import demo as demo_mod  # noqa: E402
import inflation as inf  # noqa: E402
import liquidity as lq  # noqa: E402
import sources.dart as dart  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}"
          f"{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def steady(monthly: float, n: int = 26, start: float = 100.0):
    out, p = [], start
    for i in range(n):
        p *= (1 + monthly)
        out.append((f"{2024 + i // 12}-{(i % 12) + 1:02d}-01", p))
    return out


print("=== 물가: 지수 → 속도 ===")
# 월 0.2% 꾸준히 → 연 (1.002^12 - 1) = 2.43%, 3개월 연율도 같아야 합니다
r = inf.build("T", "테스트", steady(0.002))
check("전월비가 맞다", r.mom is not None and abs(r.mom - 0.2) < 0.01,
      f"{r.mom:.3f}%")
check("전년동월비가 맞다", abs(r.yoy - 2.431) < 0.02, f"{r.yoy:.3f}% (이론 2.431)")
check("3개월 연율이 맞다", abs(r.saar3 - 2.431) < 0.02,
      f"{r.saar3:.3f}% (같은 속도면 전년동월비와 같아야 합니다)")
check("속도가 같으면 '비슷'", r.direction == "비슷", r.direction)
check("격차가 거의 0", abs(r.gap) < 0.02, f"{r.gap:.3f}%p")

# 최근 3개월만 가속
vals = steady(0.001, n=23)
last = vals[-1][1]
vals += [(f"2026-{m:02d}-01", last * 1.008 ** (m)) for m in (1, 2, 3)]
r2 = inf.build("H", "가속", vals)
check("재가속을 잡는다", r2.direction == "재가속",
      f"YoY {r2.yoy:.2f}% vs 3m {r2.saar3:.2f}%")
check("3개월 연율이 전년동월비보다 크다", r2.saar3 > r2.yoy)

# 최근 3개월만 감속
vals3 = steady(0.004, n=23)
last3 = vals3[-1][1]
vals3 += [(f"2026-{m:02d}-01", last3 * 1.0005 ** m) for m in (1, 2, 3)]
r3 = inf.build("C", "감속", vals3)
check("둔화를 잡는다", r3.direction == "둔화",
      f"YoY {r3.yoy:.2f}% vs 3m {r3.saar3:.2f}%")

print("\n=== 물가: 안 하는 일 ===")
r4 = inf.build("N", "비조정", steady(0.002), seasonally_adjusted=False)
check("비계절조정은 전월비를 안 낸다", r4.mom is None,
      "계절 패턴이 물가 상승으로 보입니다")
check("비계절조정은 연율도 안 낸다", r4.saar3 is None)
check("비계절조정도 전년동월비는 낸다", r4.yoy is not None,
      "12개월 차이라 계절 영향이 상쇄됩니다")
check("방향을 모르면 '알 수 없음'", r4.direction == "알 수 없음")
short = inf.build("S", "짧음", steady(0.002, n=8))
check("관측치가 모자라면 계산 안 함", not short.ok)
check("몇 개인지 적는다", "8개" in short.error, short.error[:40])
check("빈 입력도 안 죽는다", not inf.build("E", "빈", []).ok)
check("0 으로 안 나눈다", inf.pct_change(1.0, 0.0) is None)

print("\n=== 물가: 요약 ===")
line = inf.summary_line([r, r2, r3])
check("근원이 없으면 첫 항목을 쓴다", "테스트" in line, line[:60])
core = inf.build("K", "CPI 근원", steady(0.002))
line2 = inf.summary_line([r2, core])
check("근원을 우선한다", line2.startswith("CPI 근원"), line2[:40])
check("못 받으면 그렇게 말한다",
      "받지 못했습니다" in inf.summary_line([short]))

print("\n=== 유동성: 단위 ===")
check("백만 → 십억", abs(lq.SCALE["millions"] * 6_600_000 - 6600) < 1)
fed = lq.Component("fed_assets", "연준 총자산", raw=6_600_000,
                   unit="millions", prev=6_650_000, period="2026-11-05")
rrp = lq.Component("rrp", "역레포", raw=120.0, unit="billions", prev=160.0)
tga = lq.Component("tga", "재무부 계정", raw=800.0, unit="billions", prev=760.0)
check("연준 총자산이 6.6조", abs(fed.billions - 6600) < 1, f"{fed.billions:,.0f}")
nl = lq.net_liquidity(fed, rrp, tga)
check("순유동성 = 총자산 − 역레포 − TGA",
      abs(nl.value - (6600 - 120 - 800)) < 1, f"{nl.value:,.0f}")
check("4주 변화도 같은 식으로",
      abs(nl.change - ((6600 - 120 - 800) - (6650 - 160 - 760))) < 1,
      f"{nl.change:+,.0f}")

print("\n=== 유동성: 조용히 틀리지 않기 ===")
# 단위를 틀리면 1000배 틀린 숫자가 나옵니다 — 그걸 화면에 내보내면 안 됩니다
wrong = lq.Component("fed_assets", "연준 총자산", raw=6_600_000,
                     unit="billions")
bad = lq.net_liquidity(wrong, rrp, tga)
check("단위가 틀리면 계산을 거부한다", not bad.ok)
check("왜 거부했는지 적는다", "단위" in bad.error, bad.error[:70])
check("정상 범위를 말해준다", "정상 범위" in bad.error, bad.error[:80])
tiny = lq.Component("fed_assets", "연준 총자산", raw=6.6, unit="billions")
check("너무 작아도 잡는다", not lq.net_liquidity(tiny, rrp, tga).ok)
check("정상 범위는 통과", fed.sanity() == "", fed.sanity())
check("역레포 3조 초과면 이상",
      lq.Component("rrp", "역레포", raw=5000.0).sanity() != "")

missing = lq.net_liquidity(fed, lq.Component("rrp", "역레포"), tga)
check("하나라도 없으면 부분합을 내지 않는다", not missing.ok)
check("부분값 경고를 적는다", "부분값" in missing.error, missing.error[:60])
errored = lq.net_liquidity(
    fed, lq.Component("rrp", "역레포", error="FRED 응답 없음"), tga)
check("구성요소 오류를 그대로 올린다",
      "FRED 응답 없음" in errored.error, errored.error[:50])

print("\n=== 유동성: 방향 ===")
check("50십억 넘게 늘면 '늘고 있음'",
      lq.NetLiquidity(value=5000, prev=4900).direction == "늘고 있음")
check("50십억 넘게 줄면 '줄고 있음'",
      lq.NetLiquidity(value=4900, prev=5000).direction == "줄고 있음")
check("작은 변화는 '거의 그대로'",
      lq.NetLiquidity(value=5000, prev=4990).direction == "거의 그대로")
check("이전값이 없으면 '알 수 없음'",
      lq.NetLiquidity(value=5000).direction == "알 수 없음")

print("\n=== 금액 표기 ===")
check("십억을 조로", ui.fmt_usd_bn(5671.6) == "5.67조 달러",
      ui.fmt_usd_bn(5671.6))
check("작은 값은 억으로", ui.fmt_usd_bn(30) == "300억 달러", ui.fmt_usd_bn(30))
check("'십억' 이라고 쓰지 않는다", "십억" not in ui.fmt_usd_bn(96.4),
      "한국어가 아닙니다")
check("None 은 대시", ui.fmt_usd_bn(None) == "—")
check("부호를 붙일 수 있다", ui.fmt_usd_bn(30, signed=True).startswith("+"))

print("\n=== 공시 분류 ===")
cases = [
    ("영업(잠정)실적(공정공시)", "실적"),
    ("매출액또는손익구조30%(대규모법인은15%)이상변동", "실적"),
    ("유상증자결정", "자본조달"),
    ("[정정]전환사채권발행결정", "자본조달"),
    ("자기주식취득결정", "주주환원"),
    ("현금ㆍ현물배당결정", "주주환원"),
    ("단일판매ㆍ공급계약체결", "계약"),
    ("단일판매·공급계약체결", "계약"),
    ("최대주주변경", "지배구조"),
    ("주식등의대량보유상황보고서", "지배구조"),
    ("불성실공시법인지정", "경고"),
    ("상장폐지사유발생", "경고"),
    ("분기보고서", ""),
    ("임원ㆍ주요주주특정증권등소유상황보고서", ""),
]
for title, want in cases:
    got = dart.classify(title)
    check(f"{title[:24]} → {want or '(제외)'}", got == want, f"실제 {got!r}")
check("가운뎃점 두 종류를 모두 받는다",
      dart.classify("현금·현물배당결정") == dart.classify("현금ㆍ현물배당결정"),
      "DART 는 ㆍ(U+318D), 사람은 ·(U+00B7) 를 씁니다")
check("빈 제목도 안 죽는다", dart.classify("") == "")

f = dart.MarketFiling("2026-11-11", "삼성전자", "005930", "영업(잠정)실적",
                      "실적", rcept_no="20261111000001")
check("공시 링크를 만든다", "rcpNo=20261111000001" in f.url)
check("접수번호가 없으면 링크도 없다",
      dart.MarketFiling("d", "n", "c", "t", "k").url == "")

print("\n=== 섹터 설정 ===")
keys = [k for k, _l, _q in config.KR_SECTORS]
check("섹터 키가 중복되지 않는다", len(keys) == len(set(keys)))
check("검색어가 모두 있다",
      all(q.strip() for _k, _l, q in config.KR_SECTORS))
check("검색어가 한 단어가 아니다",
      all(len(q.split()) >= 2 for _k, _l, q in config.KR_SECTORS),
      "'반도체' 만 넣으면 제품 리뷰가 섞입니다")
check("금리와 환율이 들어 있다",
      {"rates", "fx"} <= set(keys), str(keys))

print("\n=== 화면 ===")
readings = demo_mod.demo_inflation(config.INFLATION_SERIES)
tbl = ui.render_inflation_table(readings)
check("세 속도를 모두 적는다",
      all(x in tbl for x in ("전월비", "전년동월비", "3개월 연율")))
check("방향 배지가 있다", "dash-sig-chip" in tbl)
check("비조정 계열은 전월비가 대시", tbl.count(">—<") >= 1)
check("하나도 못 받으면 그렇게 말한다",
      "하나도 받지 못했습니다" in ui.render_inflation_table([]))

nl2, extra = demo_mod.demo_liquidity()
liq = ui.render_liquidity(nl2, extra)
check("순유동성 식을 적는다", "연준 총자산 − 역레포 − 재무부 계정" in liq)
check("인과가 아님을 밝힌다", "인과가 아니라 배경" in liq)
check("구성요소를 보여준다", liq.count("dash-hit-cell") == 3)
check("참고 계열도 붙는다", "M2" in liq)
bad_liq = ui.render_liquidity(lq.NetLiquidity(error="단위가 이상합니다"))
check("계산 못 하면 이유를 적는다", "단위가 이상합니다" in bad_liq)
check("부분값 경고를 낸다", "틀린 숫자" in bad_liq)

sn, se = demo_mod.demo_sector_news(config.KR_SECTORS)
html = ui.render_sector_news(config.KR_SECTORS, sn, se)
check("섹터마다 블록", html.count("dash-sector-name") == len(config.KR_SECTORS))
check("빈 섹터도 자리를 남긴다", "dash-sector-empty" in html,
      "조용히 빼면 '오늘 뉴스가 없네' 로 오해합니다")
check("검색어를 보여준다", "한국은행 기준금리" in html)

fl = ui.render_market_filings(demo_mod.demo_market_filings())
check("공시 표를 그린다", "dash-table" in fl)
check("분류 배지", "자본조달" in fl)
check("추렸다는 걸 밝힌다", "제목으로 추렸습니다" in fl)
check("비면 왜 비었는지 적는다",
      "추려내는 유형" in ui.render_market_filings([]))
check("오류는 오류로", "키 없음" in ui.render_market_filings([], error="키 없음"))

xss_f = dart.MarketFiling("2026-11-11", "<img src=x onerror=1>", "0",
                          "<script>", "실적", rcept_no="1")
check("공시 응답을 이스케이프한다",
      "&lt;img" in ui.render_market_filings([xss_f]))

print("\n=== 앱 배선 ===")
_app = pathlib.Path("app.py").read_text(encoding="utf-8")
check("flows 탭이 디스패치에 있다", 'active == "flows"' in _app)
check("flows 가 시장을 받는다", "def render_flows_tab(use_demo: bool, *, market" in _app)
check("한국/미국을 나눠 그린다",
      "_flows_korea(use_demo)" in _app and "_flows_us(use_demo)" in _app)
check("로딩 안내가 있다", '"flows":' in _app)
check("FRED 키 지문을 캐시 키로 쓴다",
      "load_inflation(use_demo, fred.key_fingerprint())" in _app)
check("DART 키 지문도", "load_market_filings(use_demo, dart.key_fingerprint())"
      in _app)
check("한국 계열이 미검증임을 화면에 적는다",
      "한국 계열 ID 는 전부 미검증입니다" in _app)

_cfg = pathlib.Path("config.py").read_text(encoding="utf-8")
check("flows 가 탭 순서에 있다", '"flows",' in _cfg)
check("탭 라벨이 있다", '"flows": "뉴스' in _cfg)

_pv = pathlib.Path("tools/preview.py").read_text(encoding="utf-8")
check("프리뷰에도 flows 패널", "_flows_panel" in _pv)

print("\n=== 딥링크 ===")
links = ui.render_skill_links("005930", "삼성전자")
check("앱 딥링크", "claude://claude.ai/new?q=" in links)
check("웹 링크", "https://claude.ai/new?q=" in links)
check("Claude Code 링크", "claude://code/new?q=" in links)
check("세 스킬 모두", links.count("dash-skill-row") == 3)
check("URL 인코딩이 됐다", "%2Fcompany-decoder-korean" in links,
      "슬래시를 그대로 두면 경로로 해석됩니다")
check("한글 종목명도 인코딩", "%EC%82%BC%EC%84%B1" in links)
check("보내기 전에 확인할 수 있음을 밝힌다", "보내기 전에" in links)

print("\n=== 코스닥 ===")
kq = config.kosdaq_codes()
check("코스닥 후보가 있다", len(kq) >= 15, f"{len(kq)}종목")
check("코스피와 안 겹친다",
      not (kq & {c for c, _n in config.SCREEN_KR_CANDIDATES}))
check("전체 후보에 들어간다", kq <= {c for c, _n in config.screen_kr_candidates()})
check("빼고도 받을 수 있다",
      len(config.screen_kr_candidates(include_kosdaq=False))
      < len(config.screen_kr_candidates()))
check("코드가 모두 6자리 숫자",
      all(len(c) == 6 and c.isdigit() for c in kq))
import kr_screen as _ks  # noqa: E402
check("코스닥은 .KQ 를 먼저 본다",
      _ks.yahoo_symbols(sorted(kq)[0])[0].endswith(".KQ"),
      str(_ks.yahoo_symbols(sorted(kq)[0])))
check("코스피는 .KS 를 먼저 본다",
      _ks.yahoo_symbols("005930")[0].endswith(".KS"))

_diag = pathlib.Path("tools/diagnose.py").read_text(encoding="utf-8")
check("종목코드 대조 진단이 있다", "def diagnose_kr_codes" in _diag)
check("DART 이름과 맞춰본다",
      "corp_name" in _diag.split("def diagnose_kr_codes")[-1],
      "corpCode.xml 의 실제 회사명과 대조해야 의미가 있습니다")
check("진단 패널에 등록됐다", '"diagnose_kr_codes"' in _app,
      "이름 문자열로 등록합니다 — 직접 참조하면 파일이 낡았을 때 "
      "앱 전체가 죽습니다")

print("\n=== FRED 계열 검증 상태 ===")
# 2026-11-11 실측으로 매크로 14계열이 전부 확인됐습니다. '미검증' 표시를
# 남겨 두면 다음에 또 같은 진단을 돌리게 됩니다.
check("매크로 계열에 미검증이 없다",
      all(sp.verified for sp in config.MACRO_SERIES),
      str([sp.series_id for sp in config.MACRO_SERIES if not sp.verified]))

_fred_src = pathlib.Path("sources/fred.py").read_text(encoding="utf-8")
check("키가 있으면 막힌 호스트로 내려가지 않는다",
      "return _fetch_via_api(series_id, key, start)" in _fred_src,
      "fred.stlouisfed.org 는 이 환경에서 8초 타임아웃입니다 — "
      "계열마다 8초씩 버릴 이유가 없습니다")
_body = _fred_src.split("def fetch_series")[1].split("\ndef ")[0]
check("CSV 는 키가 없을 때만",
      _body.index("CSV_URL") > _body.index("_fetch_via_api"))

_diag2 = pathlib.Path("tools/diagnose.py").read_text(encoding="utf-8")
check("추가 계열 진단이 있다", "def diagnose_fred_extra" in _diag2)
check("유동성 단위를 숫자로 보여준다", "_to_billions" in _diag2,
      "단위가 틀리면 1000배 어긋나는데 화면에는 그럴듯해 보입니다")
from tools.diagnose import _to_billions as _tb  # noqa: E402
check("백만 → 십억 변환", abs(_tb(6_600_000, "millions") - 6600) < 1)
check("십억은 그대로", abs(_tb(120, "billions") - 120) < 0.01)
check("원 단위 → 십억", abs(_tb(7.41e12, "units") - 7410) < 1)
_app2 = pathlib.Path("app.py").read_text(encoding="utf-8")
check("진단 패널에 등록됐다", '"diagnose_fred_extra"' in _app2)

print("\n=== 단위를 틀렸을 때 (2026-11-11 실제 사례) ===")
# TGA 를 billions 로 적었더니 957,175십억 달러(= 95경)가 나왔습니다.
# 검사가 잡아서 숫자를 내지 않았습니다. 여기서는 (1) 다시 안 틀리는지
# (2) 틀렸을 때 **어느 단위가 맞는지까지** 말해 주는지를 봅니다.
_tga_unit = {sid: u for _k, sid, _l, u in config.LIQUIDITY_SERIES}["WTREGEN"]
check("TGA 단위가 millions 로 고쳐졌다", _tga_unit == "millions",
      f"'{_tga_unit}' — billions 로 읽으면 1000배 틀립니다")
_wal = {sid: u for _k, sid, _l, u in config.LIQUIDITY_SERIES}["WALCL"]
check("WALCL 도 millions", _wal == "millions", _wal)
_rrp = {sid: u for _k, sid, _l, u in config.LIQUIDITY_SERIES}["RRPONTSYD"]
check("역레포는 billions 그대로", _rrp == "billions",
      f"{_rrp} — 실측에서 범위 검사를 통과했습니다")

_bad = lq.Component("tga", "TGA", raw=957_175, unit="billions")
_msg = _bad.sanity()
check("틀린 단위를 잡는다", bool(_msg))
check("맞는 단위를 짚어 준다", "'millions' 로 읽으면" in _msg, _msg[-70:])
check("고칠 곳을 알려준다", "config" in _msg)
_fixed = lq.Component("tga", "TGA", raw=957_175, unit="millions")
check("고친 단위는 통과", _fixed.sanity() == "", _fixed.sanity())
check("값이 맞다", abs(_fixed.billions - 957.175) < 0.01,
      f"{_fixed.billions:,.3f}")

print("\n=== 참고 계열에도 검사가 붙었다 ===")
check("참고 계열에 범위가 있다",
      all(len(row) == 6 for row in config.LIQUIDITY_EXTRA),
      "범위가 없으면 단위가 틀려도 조용히 이상한 숫자가 나갑니다")
for _sid, _lab, _u, _cur, _lo, _hi in config.LIQUIDITY_EXTRA:
    check(f"{_sid} 범위가 말이 된다", 0 < _lo < _hi, f"{_lo}~{_hi}")
    check(f"{_sid} 통화가 적혀 있다", bool(_cur), _cur)
_yen = lq.Component("JPNASSETS", "일본은행", raw=7_420_000,
                    unit="hundred_millions", currency="엔",
                    sane_range=(300_000, 1_200_000))
check("1억 단위 배율이 있다", "hundred_millions" in lq.SCALE)
check("엔화도 범위 안", _yen.sanity() == "", _yen.sanity()[:80])
check("742조 엔으로 읽힌다", abs(_yen.billions / 1000 - 742) < 1,
      f"{_yen.billions / 1000:,.1f}조")
_yen_bad = lq.Component("JPNASSETS", "일본은행", raw=7_420_000,
                        unit="units", currency="엔",
                        sane_range=(300_000, 1_200_000))
check("단위를 틀리면 참고 계열도 잡힌다", bool(_yen_bad.sanity()))
check("참고 계열도 맞는 단위를 짚는다",
      "hundred_millions" in _yen_bad.suggest_unit(),
      _yen_bad.suggest_unit())

_app3 = pathlib.Path("app.py").read_text(encoding="utf-8")
check("화면이 참고 계열 단위를 검사한다", "problem = c.sanity()" in _app3)
check("이상하면 숫자 대신 사유", "단위 확인 필요" in _app3)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
