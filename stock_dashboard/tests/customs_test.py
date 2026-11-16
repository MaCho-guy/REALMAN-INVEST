"""
관세청 메모리 수출 단가(sources.customs_trade) 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/customs_test.py

검증 범위: XML 파싱(총계 행 제외, 오류 응답), 월별 합계 · 중복 제거, 1년 이하 구간 자르기,
           단가 · 전월/전년 변화, 키 없음 · Encoding 키 풀기, 국가코드 없이 전체가 오는 경우와
           안 와서 주요국을 더하는 경우, 화면 문구.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import components as ui  # noqa: E402
from sources import customs_trade as ct  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def item(year, cnty, hs, name, kg, usd):
    return (f"<item><year>{year}</year><statCd>{cnty}</statCd><statCdCntnKor1>x</statCdCntnKor1>"
            f"<statKor>{name}</statKor><hsCd>{hs}</hsCd><expWgt>{kg}</expWgt><expDlr>{usd}</expDlr>"
            "<impWgt>0</impWgt><impDlr>0</impDlr><balPayments>0</balPayments></item>")


def resp(items, code="00", msg="NORMAL SERVICE."):
    return (f"<response><header><resultCode>{code}</resultCode><resultMsg>{msg}</resultMsg></header>"
            f"<body><items>{''.join(items)}</items></body></response>")


print("── 파싱")
xml = resp([item("2026.09", "CN", "8542321010", "디램", 1000, 5_000_000),
            item("2026.09", "CN", "8542322000", "플래시", 500, 1_000_000),
            item("총계", "", "", "", 1500, 6_000_000)])
code, msg, rows = ct.parse_xml(xml)
check("결과코드 00", code == "00")
check("총계 행은 뺌 → 2행", len(rows) == 2)
check("월 표기 2026-09", rows[0].month == "2026-09")
c2, m2, r2 = ct.parse_xml("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
                          "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
                          "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
check("게이트웨이 오류 응답도 코드 · 메시지로 읽음", c2 == "30" and "NOT_REGISTERED" in m2 and r2 == [])
try:
    ct.parse_xml("not xml")
    check("XML 아니면 CustomsError", False)
except ct.CustomsError:
    check("XML 아니면 CustomsError", True)

print("── 집계")
rows3 = rows + [ct.Row("2026-09", "CN", "8542321010", "디램", 1000, 5_000_000),       # 중복
                ct.Row("2026-09", "US", "8542321010", "디램", 200, 1_200_000),
                ct.Row("2026-09", "US", "8541100000", "다이오드", 9, 9),               # 다른 품목
                ct.Row("2025-09", "CN", "8542321010", "디램", 1000, 2_000_000),
                ct.Row("2026-08", "CN", "8542321010", "디램", 1100, 5_500_000)]
s = ct.aggregate(rows3, "테스트")
sep = s.get("2026-09")
check("중복 (월·국가·HS) 한 번만 · 다른 품목 제외", sep.kg == 1700 and sep.usd == 7_200_000)
check("단가 = 7,200,000 ÷ 1,700", abs(sep.unit - 7_200_000 / 1700) < 1e-9)
check("하위 품목 2개", set(sep.by_item) == {"8542321010", "8542322000"})
check("전월 대비 = 단가/단가 − 1", abs(s.change("2026-09", 1) - ((7_200_000 / 1700) / (5_500_000 / 1100) - 1) * 100) < 1e-9)
check("전년 대비", abs(s.change("2026-09", 12) - ((7_200_000 / 1700) / 2000 - 1) * 100) < 1e-9)
check("없는 달은 None", s.change("2026-09", 3) is None)

print("── 구간")
w = ct.windows("2026-10", 25)
check("25개월 → 3구간 · 각 12개월 이하", len(w) == 3 and w[0][0] == "202410" and w[-1][1] == "202610", str(w))
check("구간 이어짐", all(ct.shift_month(f"{b[:4]}-{b[4:]}", 1).replace("-", "") == w[i + 1][0]
                       for i, (a, b) in enumerate(w[:-1])))

print("── 키")
os.environ.pop(ct.KEY_ENV, None)
r = ct.fetch(dt.date(2026, 11, 16))
check("키 없으면 오류로 담음 · 루트 레벨 안내", not r.ok and "루트 레벨" in r.error)
os.environ[ct.KEY_ENV] = "abc%2Bdef%3D%3D"
check("Encoding 키는 한 번 풂", ct.api_key() == "abc+def==")
check("지문은 8자리 · 키 자체 아님", len(ct.key_fingerprint()) == 8 and "abc" not in ct.key_fingerprint())
check("오류 문구에서 키를 지움", "abc+def==" not in ct._scrub("url?serviceKey=abc+def==", "abc+def=="))

print("── 받기 (가짜 응답)")
calls: list[dict] = []


def fake_all(params, key):
    calls.append(params)
    a = params["strtYymm"]
    y, m = int(a[:4]), int(a[4:])
    items = []
    end = params["endYymm"]
    for k in range(12):
        mm = (m - 1 + k) % 12 + 1
        yy = y + (m - 1 + k) // 12
        if f"{yy}{mm:02d}" > end:
            break
        items += [item(f"{yy}.{mm:02d}", "CN", "8542321010", "디램", 100, 100 * (yy - 2023) * 1000),
                  item(f"{yy}.{mm:02d}", "TW", "8542321010", "디램", 50, 50 * (yy - 2023) * 1000)]
    return ct.parse_xml(resp(items))


orig = ct._get
ct._get = fake_all
r = ct.fetch(dt.date(2026, 11, 16))
check("국가코드 없이 전체가 오면 '전체 국가'", r.ok and r.coverage == "전체 국가", r.error)
check("국가코드를 보내지 않음", all("cntyCd" not in c for c in calls))
check("최신 달 = 2026-10", r.latest.month == "2026-10")

calls.clear()


def fake_need_country(params, key):
    calls.append(params)
    if "cntyCd" not in params:
        return ct.parse_xml(resp([], code="10", msg="INVALID_REQUEST_PARAMETER_ERROR"))
    if params["cntyCd"] == "JP":
        raise ct.CustomsError("관세청 HTTP 500")
    if params["cntyCd"] not in ("CN", "HK"):
        return ct.parse_xml(resp([]))
    return ct.parse_xml(resp([item("2026.10", params["cntyCd"], "8542321010", "디램", 10, 1000)]))


ct._get = fake_need_country
r = ct.fetch(dt.date(2026, 11, 16))
check("국가코드가 필요하면 주요국을 하나씩 더함", r.ok and r.get("2026-10").kg == 20, r.error)
check("범위에 '전체 아님' · 실패한 국가는 빠짐", "전체 아님" in r.coverage and "JP" not in r.coverage
      and "주요 11개국" in r.coverage, r.coverage)
check("실패 · 첫 호출 오류를 메모에 남김", any("JP" in w for w in r.warnings)
      and any("INVALID" in w for w in r.warnings))
ct._get = lambda p, k: ct.parse_xml(resp([], code="30", msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
r = ct.fetch(dt.date(2026, 11, 16))
check("전부 실패면 오류에 사유", not r.ok and "NOT_REGISTERED" in r.error, r.error)
ct._get = orig

print("── 화면")
html = ui.render_customs_unit(s)
check("최신 단가 · 전월 · 전년", "2026-09 메모리 수출 단가" in html and "전월 대비" in html and "전년 대비" in html)
check("하위 품목 표 (2개 이상일 때)", "하위 품목" in html and "디램" in html)
check("제품 구성 주의 · 범위 표기", "제품 구성" in html and "범위: 테스트" in html)
check("오류면 사유", "키가" in ui.render_customs_unit(None, "키가 없습니다"))

print()
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
