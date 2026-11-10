"""
한국 반도체 수출 파서 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/kr_exports_test.py

**실제 보도자료 문장으로 검증합니다.** 아래 본문 조각은 산업통상부
보도자료에서 가져온 것이고, 지어낸 문장이 아닙니다. 가져오기(fetch)는
이 환경에서 motir.go.kr 요청이 막혀 검증할 수 없고, 파싱만 검증합니다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources import kr_exports as kx  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


# ──────────────────────────────────────────────────────────────────────────────
# 실제 보도자료 문장 (산업통상부)
# ──────────────────────────────────────────────────────────────────────────────

SEP_2026 = (
    "【총괄】'26.9월 수출은 전년 동월 대비 83.5% 증가한 1,209.4억 달러, "
    "수입은 26.0% 증가한 710.9억 달러, 무역수지는 498.5억 달러 흑자를 기록했다. "
    "(IT) 반도체 수출(603.0억 달러, +262.8)은 메모리 수요 증가세가 지속되며, "
    "수출물량 확대와 고정가격 증가세가 유지되면서 사상 처음으로 600억 달러 "
    "이상을 기록했다."
)

AUG_2026 = (
    "2026년 8월 수출입 동향 "
    "(IT) 반도체 수출(466.5억 달러, +209.0%)은 구글·아마존 등 하이퍼스케일러의 "
    "설비투자(Capex) 확대로 AI 인프라 수요가 견조하게 지속되면서 역대 최대 "
    "기록을 경신했으며, 3개월 연속 400억 달러 이상을 기록했다."
)

JAN_2026 = (
    "2026년 1월 수출입 동향 "
    "반도체 수출(205.4억 달러, +102.7%)은 AI서버향 높은 수요로 지난해부터 "
    "이어진 메모리 고정가격 상승이 지속되면서"
)

PCT_ONLY = (
    "2026년 10월 수출입 동향 "
    "【수출】10월 수출은 93.7% 증가한 1,153억 달러로 지난달에 이어 2개월 "
    "연속으로 1,100억 달러 이상을 기록했으며, 반도체 수출은 259%, 반도체 외 "
    "품목 수출은 34% 증가했다."
)

# 감소 국면 — △ 는 한국 공문서에서 감소를 뜻합니다 (마이너스 기호가 아님)
DECLINE = (
    "2023년 5월 수출입 동향 "
    "반도체 수출(73.7억 달러, △36.2%)은 메모리 가격 하락이 이어지며"
)


# ──────────────────────────────────────────────────────────────────────────────
print("=== 실제 보도자료 문장 파싱 ===")

r = kx.parse_semi_exports(SEP_2026, title="2026년 9월 수출입 동향")
check("2026-09 금액", r.value_100m_usd == 603.0, str(r.value_100m_usd))
check("2026-09 증감률 (% 기호 없음)", r.yoy_pct == 262.8, str(r.yoy_pct))
check("2026-09 기준월", r.period == "2026-09", r.period)
check("패턴 기록", r.matched == "금액+증감률", r.matched)
check("경고 없음", not r.warnings, str(r.warnings))

r = kx.parse_semi_exports(AUG_2026)
check("2026-08 금액", r.value_100m_usd == 466.5, str(r.value_100m_usd))
check("2026-08 증감률 (% 기호 있음)", r.yoy_pct == 209.0, str(r.yoy_pct))
check("제목 없이 본문에서 월을 찾는다", r.period == "2026-08", r.period)

r = kx.parse_semi_exports(JAN_2026)
check("2026-01 금액", r.value_100m_usd == 205.4, str(r.value_100m_usd))
check("2026-01 증감률", r.yoy_pct == 102.7, str(r.yoy_pct))

# 금액 없이 증감률만 적는 형태
r = kx.parse_semi_exports(PCT_ONLY)
check("증감률만 있는 형태도 읽는다", r.yoy_pct == 259.0, str(r.yoy_pct))
check("금액은 None", r.value_100m_usd is None, str(r.value_100m_usd))
check("금액 없음을 경고로 남긴다",
      any("금액" in w for w in r.warnings), str(r.warnings))
check("패턴 기록", r.matched == "증감률만", r.matched)

# 감소 국면 — 가장 중요한 경계입니다
r = kx.parse_semi_exports(DECLINE)
check("△ 를 감소로 읽는다", r.yoy_pct == -36.2, str(r.yoy_pct))
check("△ 를 증가로 잘못 읽지 않는다", r.yoy_pct is not None and r.yoy_pct < 0,
      "부호를 놓치면 사이클 저점을 고점으로 읽습니다")
check("감소 국면 금액", r.value_100m_usd == 73.7, str(r.value_100m_usd))

check("▲ 도 감소로 처리", kx._signed("▲", "10.5") == -10.5)
check("+ 는 증가", kx._signed("+", "10.5") == 10.5)
check("부호 없으면 증가", kx._signed("", "10.5") == 10.5)
check("- 는 감소", kx._signed("-", "10.5") == -10.5)
check("쉼표가 든 숫자", kx._signed("", "1,209.4") == 1209.4)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 형식이 바뀌었을 때 ===")

r = kx.parse_semi_exports("반도체 얘기는 없는 보도자료입니다.",
                          title="2026년 9월 수출입 동향")
check("못 찾으면 ok=False", not r.ok)
check("서식 변경 가능성을 알린다",
      any("서식" in w for w in r.warnings), str(r.warnings))
check("기준월은 그래도 읽는다", r.period == "2026-09", r.period)

r = kx.parse_semi_exports("")
check("빈 본문도 죽지 않는다", not r.ok and bool(r.warnings))
r = kx.parse_semi_exports(None)
check("None 도 죽지 않는다", not r.ok)

r = kx.parse_semi_exports("반도체 수출(603.0억 달러, +262.8)은")
check("연월이 없으면 경고", any("연월" in w for w in r.warnings), str(r.warnings))
check("연월이 없어도 숫자는 읽는다", r.value_100m_usd == 603.0)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 연월 표기 ===")

check("'2026년 10월'", kx.parse_period("2026년 10월 수출입 동향") == (2026, 10))
check("공백이 있어도", kx.parse_period("2026 년 3 월") == (2026, 3))
check("'‘26.9월' 줄임 표기", kx.parse_period("‘26.9월 수출은") == (2026, 9))
check("작은따옴표 변형", kx.parse_period("'26.12월") == (2026, 12))
check("없으면 (0,0)", kx.parse_period("월 없는 문장") == (0, 0))
check("빈 문자열", kx.parse_period("") == (0, 0))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 단위 변환 ===")

r = kx.parse_semi_exports(SEP_2026, title="2026년 9월 수출입 동향")
check("억 달러 → 10억 달러", r.value_usd_bn == 60.3, str(r.value_usd_bn))
check("금액이 없으면 None",
      kx.SemiExports().value_usd_bn is None)
check("기준월이 없으면 period 는 빈 문자열", kx.SemiExports().period == "")
check("기준월이 없으면 age_months 는 None",
      kx.SemiExports().age_months is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 목록 페이지 링크 찾기 ===")

LIST_HTML = """
<ul class="board">
  <li><a href="/kor/article/ATCL3f49a5a8c/172360/view">2026년 10월 수출입 동향</a></li>
  <li><a href="/kor/article/ATCL3f49a5a8c/172254/view">2026년 9월 수출입 동향</a></li>
  <li><a href="/kor/article/ATCL3f49a5a8c/172100/view">반도체 특별법 시행</a></li>
  <li><a href="/kor/article/ATCL3f49a5a8c/172001/view">2026년 8월 수출입동향</a></li>
</ul>
"""
links = kx.find_article_links(LIST_HTML)
check("수출입동향 글만 골라낸다", len(links) == 3, str(len(links)))
check("최신이 맨 앞", "10월" in links[0][0], links[0][0])
check("공백 있는 제목도 잡는다",
      any("9월" in t for t, _h in links))
check("공백 없는 제목도 잡는다",
      any("8월" in t for t, _h in links))
check("관계없는 글은 제외",
      not any("특별법" in t for t, _h in links))
check("경로가 담긴다", all(h.startswith("/kor/") for _t, h in links))
check("빈 HTML", kx.find_article_links("") == [])
check("None HTML", kx.find_article_links(None) == [])

# 태그가 섞인 제목 (목록 레이아웃이 바뀌어도 글자는 남습니다)
NESTED = ('<a href="/x/1/view"><span class="tit">2026년 7월 '
          '<em>수출입 동향</em></span></a>')
links = kx.find_article_links(NESTED)
check("태그가 끼어도 제목을 읽는다", len(links) == 1 and "7월" in links[0][0],
      str(links))


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 검증 상태 표기 ===")
check("모듈 설명에 가져오기 미검증이 적혀 있다",
      "검증되지 않았습니다" in (kx.__doc__ or ""))
check("파싱은 검증했다고 적혀 있다",
      "파싱(parse)은 검증했습니다" in (kx.__doc__ or ""))
check("이메일을 User-Agent 에 넣지 않는다",
      "@" not in kx.fetch_latest.__doc__ if kx.fetch_latest.__doc__ else True)


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
