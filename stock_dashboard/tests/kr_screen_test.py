"""
국내 스크리너 테스트 — 변동성 계산과 교집합 규칙.

샌드박스에서 야후가 막혀 있어 실제 일봉으로는 못 돌립니다. 대신 성질을
아는 인공 시계열(조용한 구간 / 시끄러운 구간 / 추세)을 만들어, 계산이
그 성질을 **실제로 잡아내는지**를 봅니다. 숫자가 그럴듯한지가 아니라
이론값과 맞는지를 확인합니다.
"""

from __future__ import annotations

import math
import os
import pathlib
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
import config  # noqa: E402
import demo as demo_mod  # noqa: E402
import kr_screen as ks  # noqa: E402
import sources.dart as dart  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}"
          f"{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def walk(n: int, daily_sd: float, drift: float = 0.0,
         start: float = 100.0, seed: int = 1) -> list[float]:
    rnd = random.Random(seed)
    out, p = [], start
    for _ in range(n):
        p *= math.exp(rnd.gauss(drift, daily_sd))
        out.append(p)
    return out


print("=== 연율 변동성 ===")
# 일간 표준편차 2% → 연율 2% × √252 ≈ 31.7%
v = ks.annualized_vol(walk(500, 0.02, seed=3), 252)
check("이론값 근처로 나온다", v is not None and 27 < v < 37, f"{v:.1f}% (이론 31.7)")
v2 = ks.annualized_vol(walk(500, 0.005, seed=3), 252)
check("조용한 계열은 낮게", v2 is not None and v2 < v / 2, f"{v2:.1f}%")
check("표본이 모자라면 None", ks.annualized_vol([100.0] * 10, 252) is None)
check("0·음수 가격을 걸러낸다",
      ks.annualized_vol([100.0, 0.0, -5.0, 101.0], 252) is None)
check("가격이 안 변하면 0", ks.annualized_vol([100.0] * 60, 252) == 0.0)

print("\n=== 변동성 수축 ===")
noisy = walk(240, 0.025, seed=11)
quiet = walk(70, 0.006, start=noisy[-1], seed=12)
p = ks.profile("A", "조용해진 종목", noisy + quiet)
check("수축을 잡아낸다", p.contraction is not None and p.contraction < 0.6,
      f"{p.contraction:.2f}")
p_flat = ks.profile("B", "계속 시끄러운 종목", walk(310, 0.025, seed=13))
check("안 잦아들었으면 1 근처",
      p_flat.contraction is not None and 0.6 < p_flat.contraction < 1.8,
      f"{p_flat.contraction:.2f}")
check("변동이 없으면 수축비를 못 낸다",
      ks.profile("C", "정지", [100.0] * 300).contraction is None,
      "0 으로 나누면 안 됩니다")

print("\n=== 데이터 부족 ===")
short = ks.profile("D", "신규", [100.0 + i for i in range(60)])
check("최소 일봉 미만이면 ok=False", not short.ok)
check("몇 개인지 적는다", "60개" in short.error, short.error[:50])
check("빈 입력도 죽지 않는다", not ks.profile("E", "빈", []).ok)
check("빈 입력 사유를 적는다", ks.profile("E", "빈", []).error != "")

print("\n=== 52주 위치 ===")
up = ks.profile("UP", "상승", [100 + i * 0.3 for i in range(300)])
check("신고가는 100%", up.pct_of_high == 100.0)
check("구간 위치도 100%", up.band_position == 100.0)
down = ks.profile("DN", "하락", [200 - i * 0.3 for i in range(300)])
check("신저가는 구간 위치 0%", down.band_position == 0.0)
check("신저가의 고가 대비는 100% 미만",
      down.pct_of_high is not None and down.pct_of_high < 60,
      f"{down.pct_of_high:.1f}%")

print("\n=== 교집합 규칙 ===")
# 조용하지만 바닥 / 신고가지만 시끄러운 / 둘 다 — 셋 중 하나만 통과해야 합니다
quiet_bottom = ks.profile("QB", "조용한 바닥",
                          walk(240, 0.025, seed=21)
                          + [walk(240, 0.025, seed=21)[-1] * 0.995 ** i
                             for i in range(70)])
loud_high = ks.profile("LH", "시끄러운 신고가",
                       walk(240, 0.01, seed=22)
                       + walk(70, 0.05, drift=0.01,
                              start=walk(240, 0.01, seed=22)[-1], seed=23))
quiet_high = ks.profile("QH", "조용한 신고가",
                        walk(240, 0.03, drift=0.002, seed=24)
                        + walk(70, 0.004, drift=0.0005,
                               start=walk(240, 0.03, drift=0.002,
                                          seed=24)[-1], seed=25))
# 이 세 프로파일에는 거래량이 없습니다. 여기서 보려는 건 변동성·위치
# 교집합이지 유동성이 아니므로 그 조건은 끕니다 — 유동성은 아래에서
# 따로 봅니다.
hits = ks.contraction_hits([quiet_bottom, loud_high, quiet_high],
                           require_liquid=False)
names = [h.ticker for h in hits]
check("조용한 바닥은 안 걸린다", "QB" not in names, str(names))
check("시끄러운 신고가는 안 걸린다", "LH" not in names, str(names))
check("조용한 신고가는 걸린다", "QH" in names, str(names))

print("\n=== 통과 사유를 남긴다 ===")
if hits:
    h = hits[0]
    check("유동성을 끄면 이유도 두 줄", len(h.reasons) == 2, str(h.reasons))
    check("안 본 조건을 적지 않는다",
          not any("거래대금" in r for r in h.reasons),
          "require_liquid=False 인데 '기준 5억 이상' 이라고 적으면 거짓말입니다")
    check("기준값이 이유에 적힌다",
          any("기준" in r for r in h.reasons), str(h.reasons))
    check("지표를 함께 돌려준다", len(h.metrics) >= 4, str(len(h.metrics)))
    labels = [lab for lab, _v in h.metrics]
    check("수축비가 지표에 있다", "변동성 수축비" in labels, str(labels))

print("\n=== 정렬 ===")
ps = [ks.profile(f"S{i}", f"종목{i}",
                 walk(240, 0.03, drift=0.002, seed=30 + i)
                 + walk(70, 0.002 + i * 0.001, drift=0.0006,
                        start=walk(240, 0.03, drift=0.002,
                                   seed=30 + i)[-1], seed=40 + i))
      for i in range(5)]
ranked = ks.contraction_hits(ps, require_liquid=False)
check("많이 잦아든 순",
      all(ranked[i].sort_key <= ranked[i + 1].sort_key
          for i in range(len(ranked) - 1)),
      str([round(h.sort_key, 2) for h in ranked]))

print("\n=== 신고가만 보는 스크리너 ===")
nh = ks.near_high_hits([quiet_bottom, loud_high, quiet_high],
                       require_liquid=False)
check("①의 상위집합이다",
      set(h.ticker for h in hits) <= set(h.ticker for h in nh),
      "변동성 조건을 뺀 것이므로 ①은 전부 ②에 있어야 합니다")
check("고가 대비 높은 순",
      all(nh[i].sort_key <= nh[i + 1].sort_key for i in range(len(nh) - 1)))

print("\n=== 전통 밸류 ===")
good = ks.ValueRow("1", "셋 다 통과", pbr=0.7, per=8.0, div_yield=4.0)
check("셋 다 통과", good.passed == 3)
two = ks.ValueRow("2", "둘 통과", pbr=0.7, per=8.0, div_yield=1.0)
check("둘만 통과", two.passed == 2)
one = ks.ValueRow("3", "하나만", pbr=3.0, per=30.0, div_yield=4.0)
check("하나만 통과", one.passed == 1)
unk = ks.ValueRow("4", "적자기업", pbr=0.5, per=None, div_yield=None)
check("PER 없으면 unknown",
      any(v == "unknown" for _l, v, _d in unk.checks()))
check("unknown 은 통과로 세지 않는다", unk.passed == 1, str(unk.passed))
check("적자 설명을 적는다",
      any("적자" in d for _l, v, d in unk.checks() if v == "unknown"))
vh = ks.value_hits([good, two, one, unk], min_pass=2)
check("2개 이상만 통과", {h.ticker for h in vh} == {"1", "2"},
      str([h.ticker for h in vh]))
check("많이 통과한 순", vh[0].ticker == "1")
check("오류 있는 행은 뺀다",
      not ks.value_hits([ks.ValueRow("9", "오류", pbr=0.1, per=1.0,
                                     div_yield=9.0, error="못 받음")]))

print("\n=== 야후 심볼 ===")
check("국내 코드는 .KS 먼저",
      ks.yahoo_symbols("005930") == ("005930.KS", "005930.KQ"))
check("접미사가 있으면 그대로", ks.yahoo_symbols("005930.KQ") == ("005930.KQ",))
check("미국 티커는 그대로", ks.yahoo_symbols("MU") == ("MU",))
check("빈 값은 빈 튜플", ks.yahoo_symbols("") == ())
check("중복 없이 모은다",
      len(ks.all_symbols([("005930", "a"), ("005930", "b")])) == 2)

print("\n=== 프로파일 조립 ===")
cands = [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("999999", "없음")]
closes = {"005930.KS": [100 + i * 0.2 for i in range(300)],
          "000660.KQ": walk(300, 0.02, seed=50)}
profiles, errors = ks.build_profiles(cands, closes)
check("받은 것만 프로파일로", len(profiles) == 2, str(len(profiles)))
check("코스닥 폴백이 된다",
      any(p.ticker == "000660" for p in profiles),
      ".KS 가 비면 .KQ 를 봐야 합니다")
check("못 받은 종목은 사유를 남긴다", "999999" in errors)
check("조용히 빼지 않는다", errors["999999"] != "")

print("\n=== 기준값이 쓸모 있는 범위인가 ===")
# 30종목 모집단에서 0개나 30개가 나오면 스크리너가 아닙니다
demo_cands = list(config.screen_kr_candidates())
demo_profiles, _ = demo_mod.demo_kr_vol_profiles(demo_cands)
n_c = len(ks.contraction_hits(demo_profiles))
n_h = len(ks.near_high_hits(demo_profiles))
check("수축+신고가가 1~12종목", 1 <= n_c <= 12, f"{n_c}종목 / {len(demo_cands)}")
check("신고가만은 그보다 많거나 같다", n_h >= n_c, f"{n_h} vs {n_c}")
check("전부 통과하지는 않는다", n_h < len(demo_cands), f"{n_h}")
demo_rows = demo_mod.demo_kr_value_rows(demo_cands)
n_v = len(ks.value_hits(demo_rows))
# 후보가 늘면(보유 종목 추가) 같이 늘 수 있어 절반 이하로 봅니다
check("밸류가 1종목 이상 · 후보의 절반 이하", 1 <= n_v <= len(demo_cands) // 2, f"{n_v}종목 / {len(demo_cands)}")

print("\n=== 유동성 바닥 ===")
check("기준이 5억 원", ks.MIN_TURNOVER == 500_000_000.0)
_thick = ks.profile("A", "충분", [1000.0] * 300, [600_000.0] * 300)
_thin = ks.profile("B", "부족", [1000.0] * 300, [100.0] * 300)
_novol = ks.profile("C", "거래량없음", [1000.0] * 300)
check("거래대금을 계산한다", _thick.turnover is not None
      and abs(_thick.turnover - 6e8) < 1e6, str(_thick.turnover))
check("억 단위로 적는다", "억" in _thick.turnover_label, _thick.turnover_label)
check("충분하면 통과", _thick.liquid)
check("부족하면 탈락", not _thin.liquid)
check("모르면 통과시키지 않는다", not _novol.liquid,
      "거래량을 못 받은 종목을 '유동성 충분' 으로 보면 거르는 의미가 없습니다")
# 같은 프로파일인데 유동성만 다르면 결과가 갈려야 합니다
# 가격 5만 원대(국내 대형주 수준)로 둡니다. 거래대금은 가격 × 거래량이라
# 가격 눈금이 틀리면 유동성 판정이 통째로 엇나갑니다.
_up = [50_000 + i * 50 for i in range(300)]
_a = ks.profile("UP1", "유동", _up, [30_000.0] * 300)     # 약 20억
_b = ks.profile("UP2", "비유동", _up, [500.0] * 300)      # 약 3천만
_got = {h.ticker for h in ks.contraction_hits([_a, _b])}
check("유동성만으로 갈린다", _got == {"UP1"}, str(_got))
check("끄면 둘 다 통과",
      len(ks.contraction_hits([_a, _b], require_liquid=False)) == 2)
check("지표에 거래대금이 들어간다",
      any(lab == "20일 평균 거래대금"
          for lab, _v in ks.contraction_hits([_a])[0].metrics))
check("표본이 모자라면 None",
      ks.average_turnover([1000.0] * 3, [100.0] * 3) is None)
check("스크리너 설명에 거래대금 기준",
      "거래대금" in ks.KR_SCREENS[0][2])

print("\n=== 화면 ===")
h = ks.contraction_hits(demo_profiles)[0]
head = ui.render_screener_head("제목", "기준 <b>설명</b>", 5, "주의")
check("기준을 제목 옆에 적는다", "기준" in head and "<b>설명</b>" in head)
check("종목 수를 적는다", "5종목" in head)
check("주의가 따로 들어간다", "dash-scr-caveat" in head)
mt = ui.render_hit_metrics(h)
check("지표가 가로 줄로", "dash-hit-row" in mt)
check("라벨과 값이 짝", mt.count("dash-hit-label") == mt.count("dash-hit-value"))
why = ui.render_hit_reasons(h)
check("이유가 목록으로", "<li>" in why)

prof = dart.CompanyProfile(stock_code="005930", corp_name="삼성전자",
                           ceo="홍길동", established="19690113",
                           fiscal_month="12", industry_code="2612",
                           address="경기도 수원시")
ov = ui.render_company_overview(prof, search_name="삼성전자")
check("개요가 표로", "dash-kv" in ov)
check("설립일을 사람이 읽게", "1969-01-13" in ov)
check("DART 링크가 회사명으로", "textCrpNm=%EC%82%BC%EC%84%B1" in ov,
      "종목코드로 넣으면 검색 결과가 빕니다")
check("업종명을 지어내지 않는다", "업종명은 적지 않습니다" in ov)
check("표준산업분류 코드는 그대로", "2612" in ov)
err = ui.render_company_overview(
    dart.CompanyProfile(stock_code="x", error="키 없음"))
check("실패도 화면에 적는다", "키 없음" in err)
check("None 도 안 죽는다", ui.render_company_overview(None) != "")

xss = dart.CompanyProfile(stock_code="x", ceo='<img src=x onerror=alert(1)>')
check("기업개황을 이스케이프한다",
      "&lt;img" in ui.render_company_overview(xss),
      "DART 응답도 외부 입력입니다")

print("\n=== 홈페이지 링크 ===")
http = dart.CompanyProfile(stock_code="x", homepage="https://example.com")
check("https 는 링크로", 'href="https://example.com"'
      in ui.render_company_overview(http))
bad = dart.CompanyProfile(stock_code="x", homepage="javascript:alert(1)")
check("javascript: 는 링크로 만들지 않는다",
      "javascript:" not in ui.render_company_overview(bad))

print("\n=== 앱 배선 ===")
_app = pathlib.Path("app.py").read_text(encoding="utf-8")
check("발굴이 시장마다 갈린다",
      "_discover_kr(use_demo, part=\"funnel\")" in _app and "_discover_us(use_demo)" in _app)
check("미국에서 52주 위치를 뺐다",
      "render_discover_map" not in _app and "render_discover_table" not in _app,
      "사분면·52주 표가 남아 있으면 안 됩니다")
check("국내 카드에 기업개황",
      "render_company_overview" in _app)
check("국내 카드에 뉴스", "render_news_block(items, limit=5)" in _app)
check("국내 카드에 3대 분석 버튼", "_render_skill_buttons" in _app)
check("CLI 가 있을 때만 실행 버튼을 그린다", "if cli.available:" in _app,
      "없는 환경에서 눌리면 아무 일도 안 일어납니다")
check("CLI 없으면 딥링크로 안내한다",
      "ui.render_skill_links(code, name)" in _app)
check("CLI 없을 때 붙여넣을 명령을 준다",
      "analysis_store.skill_command(k, code, name)" in _app)
check("'느린 게 아니라 없다' 를 밝힌다",
      "느린 게 아니라" in _app or "느려서' 가 아니라" in _app)
check("메모리 사이클은 시장을 따르지 않는다",
      "이 화면만은 **시장 선택을 따르지 않습니다.**" in _app)
check("사이클 로더를 조건부로 돌리지 않는다",
      "if kr_instruments else ({}, {})" not in _app)

_ks = pathlib.Path("kr_screen.py").read_text(encoding="utf-8")
check("스크리너 정의가 streamlit 밖에 있다", "KR_SCREENS" in _ks,
      "프리뷰 생성기도 같은 정의를 써야 합니다")
check("kr_screen 이 streamlit 을 임포트하지 않는다",
      "import streamlit" not in _ks,
      "임포트하면 프리뷰 생성기에서 못 씁니다")
_pv = pathlib.Path("tools/preview.py").read_text(encoding="utf-8")
check("프리뷰도 같은 정의를 쓴다", "kr_screen.KR_SCREENS" in _pv)

print("\n=== 걸러진 단계 (0건 원인 구분) ===")
import random as _rnd  # noqa: E402
import kr_screen  # noqa: E402
from kr_screen import VolProfile as _VP, vol_funnel as _vf, value_funnel as _vlf, ValueRow as _VR  # noqa: E402

_rnd.seed(1)
_cl = [100 * (1 + 0.001 * i) for i in range(300)]
_good = kr_screen.profile("A", "a", _cl, [1e7] * 300)
_steps = _vf(10, [_good])
check("일봉 받은 수가 적으면 출처 문제라고 적는다",
      _steps[1].count == 1 and "출처" in _steps[1].note, str(_steps[1]))
check("단계는 줄어들기만 한다",
      all(_steps[i].count >= _steps[i + 1].count for i in range(1, len(_steps) - 1)))
_novol = kr_screen.profile("B", "b", _cl, None)
_s2 = _vf(1, [_novol])
check("거래량 못 받은 종목 수를 적는다", "거래량을 못 받은" in _s2[3].note, _s2[3].note)
_v = _vlf([_VR("A", "a", error="네이버 실패"), _VR("B", "b", pbr=0.8, per=8, div_yield=3)])
check("지표 단계: 받은 1 · 통과 1", _v[1].count == 1 and _v[3].count == 1, str(_v))

print("\n=== 네이버 응답 해석 ===")
from sources import naver as _nv  # noqa: E402

_xml = ('<chartdata name="삼성전자"><item data="20251107|1|1|1|1050|12345" />'
        '<item data="20251110|1|1|1|1010|2000" /><item data="x|y" /></chartdata>')
_c, _vv, _n = _nv.parse_chart_xml(_xml)
check("일봉: 종가·거래량·이름", _c == [1050.0, 1010.0] and _vv == [12345.0, 2000.0]
      and _n == "삼성전자")
check("일봉: 빈 응답은 빈 목록", _nv.parse_chart_xml("")[0] == [])
_i = _nv.parse_integration({"stockName": "삼성전자", "totalInfos": [
    {"code": "cnsPer", "key": "추정PER", "value": "9.10배"},
    {"code": "per", "key": "PER", "value": "13.52배"},
    {"code": "pbr", "key": "PBR", "value": "1.10배"},
    {"code": "dividendYieldRatio", "key": "배당수익률", "value": "1.84%"}]})
check("지표: 추정PER 이 아니라 PER", _i["per"] == 13.52, str(_i))
check("지표: PBR·배당", _i["pbr"] == 1.10 and _i["div_yield"] == 1.84)
check("지표: 'N/A' 는 None", _nv.parse_integration(
    {"totalInfos": [{"code": "per", "value": "N/A"}]})["per"] is None)
check("지표: 이상한 응답에도 안 죽는다", _nv.parse_integration([1, 2])["per"] is None)

print("\n" + "=" * 54)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
