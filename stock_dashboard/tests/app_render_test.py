"""app.py 의 화면을 **끝까지 그려 보는** 테스트 (2026-11-19).

    python tests/app_render_test.py

다른 테스트는 app.py 를 글자로만 검사합니다 (스트림릿 없이도 돌아야 해서). 그래서
화면 함수 안의 오타 · 없는 속성은 배포해야 드러났습니다 — 11/19 구조 점검 때
`cli.label`(CliInfo 에 없는 속성)이 그렇게 숨어 있었습니다.

여기서는 가짜 스트림릿(tools/fakest.py) 위에서 두 시장의 모든 화면을 데모 값으로
그립니다. 네트워크는 쓰지 않습니다. 검사하는 것:

  1. 모든 화면이 예외 없이 그려진다
  2. 메뉴 7칸 · 안쪽 탭 · 화면 성격 띠(차트 조건 / 거래 스크리너 / 실험)
  3. 요약에는 카드만 있다 (구역 제목 띠가 없다) · 카드는 전부 실제 화면으로 가는 링크
  4. 화면 문구가 없는 메뉴를 가리키지 않는다
  5. CSS 주석 · 중괄호 짝, 글자 크기 변수
"""
from __future__ import annotations

import os
import re
import sys
import traceback

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
os.environ.setdefault("DART_API_KEY", "x" * 40)      # 지문 계산용 — 호출은 하지 않습니다
os.environ.setdefault("FRED_API_KEY", "x" * 32)

from tools import fakest  # noqa: E402

st = fakest.install()

import config  # noqa: E402
import theme  # noqa: E402

FAILS: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


# 네트워크를 막습니다 — 데모는 원래 안 쓰지만, 실수로 쓰는 경로가 생기면 여기서 드러납니다
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

NET: list[str] = []


def _no_net(req, *a, **k):
    NET.append(getattr(req, "full_url", str(req))[:80])
    raise urllib.error.URLError("테스트는 네트워크를 쓰지 않습니다")


urllib.request.urlopen = _no_net

import app  # noqa: E402

print("=== 모든 화면이 끝까지 그려진다 (데모) ===")
PAGES: dict[tuple[str, str], str] = {}
for market in config.MARKETS:
    for key in config.market_tab_keys(market):
        try:
            PAGES[(market, key)] = fakest.render_screen(app, st, market, key, demo=True)
            ok, why = True, ""
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc().strip().splitlines()
            where = [ln.strip() for ln in tb if 'File "' in ln][-1:]
            ok, why = False, f"{type(exc).__name__}: {str(exc)[:80]} {where}"
        check(f"{market} · {key}", ok, why)
check("데모 화면은 네트워크를 쓰지 않는다", not NET, str(NET[:3]))

print("\n=== 메뉴 7칸 · 안쪽 탭 ===")
for market in config.MARKETS:
    groups = config.tab_groups(market)
    check(f"{market}: 메뉴 7칸", len(groups) == 7, str([g for g, _i in groups]))
    fakest.render_screen(app, st, market, groups[0][1][0][0], demo=True)
    nav = [w for w in fakest.WIDGETS if w[0] == "button" and str(w[2]).startswith("navbtn_")
           and not str(w[2]).endswith("_m")]
    check(f"{market}: 내비 버튼 = 메뉴 이름", [w[1] for w in nav] == [g for g, _i in groups],
          str([w[1] for w in nav]))
    for gi, (gname, items) in enumerate(groups):
        for key, _label in items:
            page = PAGES.get((market, key), "")
            has_sub = f'data-key="subnav_{market}_{gi}"' in page
            check(f"{market} · {key}: 안쪽 탭 {'있음' if len(items) > 1 else '없음'}",
                  has_sub == (len(items) > 1))
            crumb = re.search(r'<div class="dash-crumb[^"]*">(.*?)</div>', page, re.S)
            check(f"{market} · {key}: 맨 위 알약에 메뉴 이름",
                  crumb is not None and gname in crumb.group(1))

print("\n=== 차트 조건 · 거래 스크리너 · 실험 — 묶어 두되 구분 ===")
kinds = {k[0]: k for k in config.SCREEN_KINDS}
for market in config.MARKETS:
    here = [k for k in config.market_tab_keys(market) if k in kinds]
    for key in here:
        page = PAGES.get((market, key), "")
        check(f"{market} · {key}: 성격 띠에서 이 화면이 켜져 있다",
              f'dk-cell dk-{key} dk-on' in page and kinds[key][1] in page
              and kinds[key][3] in page)
        others = [k for k in here if k != key]
        check(f"{market} · {key}: 나머지 화면도 나란히 보인다 (꺼진 채)",
              all(f'dk-cell dk-{o}"' in page for o in others), str(others))
        check(f"{market} · {key}: 화면마다 구역 색이 다르다",
              theme.kind_vars_css(key) in page)
    other = PAGES.get((market, "summary"), "")
    check(f"{market}: 다른 메뉴에는 성격 띠가 없다", "dash-kinds" not in other)
check("세 화면의 색이 서로 다르다", len({theme.KIND_TONES[k] for k in kinds}) == 3)
check("실험 화면 = 모의 매수 + 차트 전략 백테스트",
      "모의 매수" in PAGES[("kr", "paper")] and "차트 전략 백테스트" in PAGES[("kr", "paper")])
check("차트 조건 화면에는 백테스트 보기가 없다", "백테스트" not in "".join(
    re.findall(r'<div class="fs-seg"[^>]*chart_view2.*?</div>', PAGES[("kr", "timing")], re.S)))

print("\n=== 요약에는 카드만 ===")
for market in config.MARKETS:
    page = PAGES[(market, "summary")]
    body = page.split('<div class="dash-navmark"></div>')[-1]
    check(f"{market}: 구역 제목 띠가 없다 (섹터 막대 · 후보 · 뉴스 · 전일 장 블록은 각자 화면에)",
          "dash-section-head" not in body, str(re.findall(r'dash-section-title">([^<]*)', body)))
    hrefs = re.findall(r'<a class="dash-srow dash-srow-link [a-z]+" href="([^"]+)"', body)
    rows = len(re.findall(r'class="dash-srow(?: dash-srow-link)? [a-z]+"', body))
    check(f"{market}: 카드가 전부 링크", rows >= 6 and len(hrefs) == rows, f"{len(hrefs)}/{rows}")
    targets = [re.search(r"s=([a-z_]+)", h).group(1) for h in hrefs]
    check(f"{market}: 링크가 그 시장에 실제로 있는 화면으로 간다",
          all(t in config.market_tab_keys(market) for t in targets), str(targets))
check("두 시장 요약 모두 뉴스 줄이 있고, 각자 그 시장의 뉴스 화면으로 간다",
      "s=us_news" in PAGES[("us", "summary")] and "s=kr_flows" not in PAGES[("us", "summary")]
      and "s=kr_flows" in PAGES[("kr", "summary")])
kr_only = [lbl for _k, lbl, _q in config.KR_SECTORS
           if lbl not in {l2 for _k2, l2, _q2 in config.US_SECTORS}]
# 11/19: 뉴스 화면 = 보기 둘 (오늘 중요한 것 · 섹터/주제별 전체). 주제 이름 전부는 '전체' 보기에.
US_ALL = fakest.render_screen(app, st, "us", "us_news", state={"news_view_us": "all"})
KR_ALL = fakest.render_screen(app, st, "kr", "kr_flows", state={"news_view_kr": "all"})
check("미국 뉴스 화면에는 미국 주제만 (한국 섹터 이름이 없다)",
      all(lbl in US_ALL for _k, lbl, _q in config.US_SECTORS[:-1])
      and not [lbl for lbl in kr_only if f">{lbl}<" in US_ALL + PAGES[("us", "us_news")]],
      str([lbl for lbl in kr_only if f">{lbl}<" in US_ALL + PAGES[("us", "us_news")]]))
check("뉴스 화면: 기본 보기는 카드(꼭 읽기), 전체 보기는 섹터 카드 — 서로 섞이지 않는다",
      all('class="dash-tri"' in PAGES[k] and 'class="dash-sectors ' not in PAGES[k]
          for k in (("kr", "kr_flows"), ("us", "us_news")))
      and all('class="dash-sectors ' in p and 'class="dash-tri"' not in p for p in (US_ALL, KR_ALL)))
check("뉴스 화면: 설명 문단이 화면 위에 펼쳐져 있지 않다 (접힌 '고른 기준')",
      all('details class="dash-newsrule"' in PAGES[k] and "dash-legend" not in PAGES[k]
          for k in (("kr", "kr_flows"), ("us", "us_news"))))
_sg = re.search(r'class="dash-sgrid ([^"]*)"', PAGES[("kr", "summary")])
check("요약 카드 격자: 장 수에 맞춰 맨 앞 카드가 남는 칸을 채운다 (7장 → 4칸에서 2칸 차지)",
      bool(_sg) and _sg.group(1) == "a2 b3 c2" and PAGES[("kr", "summary")].count("dash-srow ") == 7,
      str(_sg and _sg.group(1)))
import components as _ui  # noqa: E402
check("카드 줄 채우기: 5장 → 3 + 2, 9장 → 3 + 3 + 3, 4장 → 넓으면 4 · 중간 2 + 2",
      [_ui._fill_cls(n) for n in (1, 4, 5, 6, 9)]
      == ["dash-fill w1 m1", "dash-fill w4 m2", "dash-fill w3 m3", "dash-fill w3 m3", "dash-fill w3 m3"],
      str([_ui._fill_cls(n) for n in (1, 4, 5, 6, 9)]))
# 11/19 저녁: 볼 만함 카드에 바탕색 · 넓은 화면에서 왼쪽에만 몰려 있던 두 곳
_css = theme.build_css("kr")
_more = re.search(r"ol\.dash-tri-more > li\.dash-tri-card \{([^}]*)\}", _css)
check("볼 만함 카드: 투명이 아니라 메뉴 색을 섞은 바탕 (화면 바탕과 구분)",
      bool(_more) and "transparent" not in _more.group(1) and "--grp-tint" in _more.group(1),
      _more.group(1) if _more else "규칙 없음")
check("연준 순유동성 카드 · 강세/약세 칩: 넓은 화면 규칙이 있고 폰 규칙은 건드리지 않는다",
      "dash-exp dash-liq" in PAGES[("us", "us_flows")]
      and ".dash-exp.dash-liq { display: grid" in _css and ".heat-sum { display: grid" in _css
      and _css.index(".heat-sum { display: grid") > _css.rindex("@media (min-width: 1200px)", 0, _css.index(".heat-sum { display: grid")))
check("한국: 뉴스 · 공시 · 지표가 화면 셋으로 나뉘었다 (내용은 그대로)",
      "주요 공시" not in PAGES[("kr", "kr_flows")] and "경제지표" not in PAGES[("kr", "kr_flows")]
      and "한국 — 주요 공시" in PAGES[("kr", "kr_filings")] and 'class="dash-tri"' not in PAGES[("kr", "kr_filings")]
      and "한국 — 경제지표" in PAGES[("kr", "kr_macro")] and "주요 공시" not in PAGES[("kr", "kr_macro")])
check("한국 읽기 메뉴 안쪽 탭 = 아침 브리핑 · 뉴스 · 공시 · 산업 리포트, 한국 지표는 시장 메뉴",
      [config.subtab_label(k, "kr") for k, _l in dict(config.tab_groups("kr"))["읽기"]]
      == ["아침 브리핑", "뉴스", "공시", "산업 리포트"]
      and "kr_macro" in [k for k, _l in dict(config.tab_groups("kr"))["시장"]])
check("전일 장 숫자는 읽기 › 아침 브리핑에", "전일 장 마감 숫자" in PAGES[("kr", "briefing")]
      and "전일 장 마감 숫자" not in PAGES[("kr", "summary")])

print("\n=== 종목 상세 ===")
for market in config.MARKETS:
    page = PAGES[(market, "stock")]
    first = config.filter_instruments(config.SECTION_WATCHLIST.instruments, market)[0]
    check(f"{market}: 첫 종목의 머리가 있다", "dash-stockhead" in page and first.name in page)
    need = ["변한 것", "최근 공시", "재무 기준", "차트", "일정"] + (["수급"] if market == "kr" else [])
    check(f"{market}: 구역이 순서대로", all(f'dash-section-title">{n}' in page for n in need)
          and [page.index(f'dash-section-title">{n}') for n in need[:5]]
          == sorted(page.index(f'dash-section-title">{n}') for n in need[:5]))
    check(f"{market}: 구역을 못 그렸다는 안내가 없다", "구역을 그리지 못했습니다" not in page)
second = config.filter_instruments(config.SECTION_WATCHLIST.instruments, "kr")[1]
page = fakest.render_screen(app, st, "kr", "stock", demo=True, query={"c": second.symbol})
check("주소(?c=)로 들어오면 그 종목", f'sh-code">{second.symbol}<' in page, second.symbol)
check("주소에 고른 종목을 남긴다", st.query_params.get("c") == second.symbol)
check("내 종목 표에서 종목 상세로 가는 링크",
      f's=stock&amp;c={second.symbol}' in PAGES[("kr", "holdings")])

print("\n=== 화면 문구가 없는 메뉴를 가리키지 않는다 ===")
STALE = ("찾기 ›", "공통 ›", "오늘 ›", "한국 › 뉴스", "차트·거래", "야간 대체시세",
         "종목 발굴 탭", "발굴·밸류에이션 탭", "모의 매수 탭", "한국 시장 ›", "미국 시장 ›")
for word in STALE:
    hit = [f"{m}:{k}" for (m, k), page in PAGES.items() if word in page]
    check(f"'{word}' 가 어느 화면에도 없다", not hit, str(hit[:4]))
src = open("app.py", encoding="utf-8").read()
check("위치 문구는 config.where 로 만든다", src.count("config.where(") >= 8)
for market in config.MARKETS:
    for key in config.market_tab_keys(market):
        w = config.where(key, market)
        check(f"where({market}, {key}) 가 그 화면의 메뉴 이름으로 시작",
              w.startswith(config.tab_groups(market)[config.menu_of(market, key)][0]), w)
check("다른 시장에만 있는 화면은 시장 이름을 붙인다",
      config.where("screener", "us").startswith("한국 시장"), config.where("screener", "us"))

print("\n=== CSS — 주석 · 중괄호 짝, 글자 크기 ===")
css = theme.build_css("kr")
inner = css[len("<style>"):-len("</style>")]
bare = re.sub(r"/\*.*?\*/", "", inner, flags=re.S)
check("닫히지 않은 주석이 없다", "/*" not in bare and "*/" not in bare)
check("중괄호 짝이 맞다", bare.count("{") == bare.count("}"),
      f"{bare.count('{')} vs {bare.count('}')}")
root = bare.split("@media", 1)[0]
sizes = {}
for n in range(1, 10):
    m = re.search(rf"--fs-{n}:\s*([0-9.]+)rem", root)
    sizes[n] = float(m.group(1)) * 16 if m else None
check("글자 크기 변수 9개가 다 정의돼 있다 (주석에 먹히지 않았다)",
      all(v is not None for v in sizes.values()), str(sizes))
check("넓은 화면의 글 단계는 넷 — 12 · 14 · 16 · 18px",
      sorted({sizes[n] for n in range(1, 7)}) == [12.0, 14.0, 16.0, 18.0],
      str([sizes[n] for n in range(1, 7)]))
phone = re.search(r"@media \(max-width: 640px\) \{\s*:root \{(.*?)\}", bare, re.S)
check("휴대폰 본문 13px 은 그대로 (11/13 사용자가 맞춘 값)",
      phone is not None and "--fs-3: 0.82rem" in phone.group(1))
check("메뉴 규칙이 휴대폰 글자 규칙보다 뒤에 실린다",
      css.rfind(theme.build_menu_rules()) > css.rfind(theme.build_type_rules()) > 0)
check("휴대폰에서 지수 카드는 한 줄", ".dash-mstrip { display: flex;" in theme.build_menu_rules())

# ── 공시 분석 칸: 올려 둔 서버에서는 실행 버튼 · PC 설치 안내를 숨긴다 (2026-11-25) ──
print("\n=== 공시 분석 — 서버 / PC ===")
import runner  # noqa: E402

_cli_info, _hosted_env = runner.cli_info, os.environ.get("DASH_HOSTED")
runner.cli_info = lambda: runner.CliInfo(available=False, error="claude CLI 를 PATH 에서 찾을 수 없습니다.")
try:
    os.environ["DASH_HOSTED"] = "1"
    check("is_hosted: DASH_HOSTED=1 이면 서버", runner.is_hosted() is True)
    srv = fakest.render_screen(app, st, "us", "holdings", demo=True)
    os.environ["DASH_HOSTED"] = "0"
    check("is_hosted: DASH_HOSTED=0 이면 PC", runner.is_hosted() is False)
    pc = fakest.render_screen(app, st, "us", "holdings", demo=True)
    os.environ.pop("DASH_HOSTED")
    check("is_hosted: 이 시험 환경(판별 못 함)은 PC 취급", runner.is_hosted() is False)
finally:
    runner.cli_info = _cli_info
    if _hosted_env is None:
        os.environ.pop("DASH_HOSTED", None)
    else:
        os.environ["DASH_HOSTED"] = _hosted_env
_run_btn = re.compile(r'<span class="fs-btn[^"]*">(분석 실행|다시 실행|3종 모두 실행)</span>')
check("서버: 공시 분석 칸이 그려진다", "공시 분석" in srv)
check("서버: 실행 버튼이 없다", not _run_btn.search(srv), str(_run_btn.findall(srv)[:3]))
check("서버: PC 설치 안내 · CLI 문구가 없다",
      "PC 에서 직접 실행하려면" not in srv and "PATH 에서" not in srv and "npm install" not in srv)
check("서버: 새 분석을 얻는 길 한 줄", "Claude 대화에서 요청하면 여기에 올라옵니다" in srv)
check("서버: 본문 보기 칸은 그대로", "전문 보기" in srv)
check("PC(claude 없음): 꺼진 실행 버튼 · 접힌 설치 안내는 예전 그대로",
      bool(_run_btn.search(pc)) and "PC 에서 직접 실행하려면" in pc and "PATH 에서" in pc)
import components as _ui  # noqa: E402
_m_srv = _ui.render_analysis_missing("기업 해독기", "/company-decoder-korean Apple", "AAPL", "decoder",
                                     hosted=True, name="Apple")
_m_pc = _ui.render_analysis_missing("기업 해독기", "/company-decoder-korean Apple", "AAPL", "decoder")
check("서버: 없는 분석은 '요청하면 올라온다' 만 안내",
      "Apple 분석해서 올려줘" in _m_srv and "분석 실행" not in _m_srv and "저장 경로" not in _m_srv)
check("PC: 없는 분석 안내는 예전 그대로", "분석 실행" in _m_pc and "analysis/AAPL/decoder.html" in _m_pc)

print("\n" + "=" * 56)
if FAILS:
    print(f"실패 {len(FAILS)}건:")
    for f in FAILS:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1)
print("전부 통과")
sys.stdout.flush()
os._exit(0)          # 뒤에서 도는 받기 스레드를 기다리지 않습니다
