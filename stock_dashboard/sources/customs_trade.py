"""
관세청 품목별 수출입실적 — 메모리 반도체 수출 단가 (2026-11-16).

================================================================================
왜 이게 필요한가 — 레이어 1 의 두 번째 출처
================================================================================
지표체계의 가격 층(레이어 1)은 TrendForce/DRAMeXchange 한 곳에 의존합니다(§6 한계 7).
거부권을 가진 층이 교차검증 불가능하다는 뜻입니다. 관세청 통관 자료는 완전히 다른
경로(수출신고)라서, **수출금액 ÷ 수출중량 = kg 당 단가** 를 보면 메모리 가격 방향을
독립적으로 확인할 수 있습니다.

  API     관세청_품목별 국가별 수출입실적(GW) — data.go.kr 15100475
  URL     https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList
  인자    serviceKey · strtYymm · endYymm (1년 이내) · hsSgn(선택) · cntyCd(필수)
  응답    year("2026.09") · statCd · statKor(품목명) · hsCd · expWgt(kg) · expDlr($) …
  갱신    전월 자료를 매월 15일경

  품목    HS 8542.32 (메모리). 10단위 하위 코드가 있으면 하위 품목별로도 나눠 봅니다.

================================================================================
함정
================================================================================
1. **국가코드가 필수입니다.** 전체 합계 코드가 문서에 없습니다. 그래서 먼저 국가코드
   없이 한 번 불러 보고(전체가 오면 그걸 씀), 안 되면 주요 수출국을 하나씩 불러
   더합니다. 이 경우 화면에 '주요 N개국 합계' 라고 밝힙니다 — 전체가 아닙니다.
2. **단가는 제품 구성의 영향을 받습니다.** HBM 처럼 비싼 제품 비중이 늘면 가격이
   그대로여도 kg 당 단가가 오릅니다. 방향 확인용이지 가격 그 자체가 아닙니다.
3. 인증키는 '일반 인증키(Decoding)' 를 씁니다. Encoding 키(%2B 같은 것이 섞인)를
   넣어도 한 번 풀어서 씁니다 — 두 번 인코딩되면 SERVICE_KEY_IS_NOT_REGISTERED.
4. 키는 오류 메시지 · 캐시 키에 남기지 않습니다 (key_fingerprint).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
KEY_ENV = "DATA_GO_KR_KEY"
HS_MEMORY = "854232"
TIMEOUT = 20
MIN_INTERVAL = 0.2

#: 국가코드 없이 안 될 때 더할 주요 수출국. 메모리 수출 대부분이 여기로 갑니다
#: (목록은 화면에 그대로 적습니다 — 전체가 아니라는 표시).
MAJOR_COUNTRIES: tuple[str, ...] = (
    "CN", "HK", "TW", "VN", "US", "SG", "PH", "MY", "JP", "IN", "MX", "TH")

_last = 0.0


class CustomsError(RuntimeError):
    pass


class CustomsKeyMissing(CustomsError):
    pass


def api_key() -> str:
    key = (os.environ.get(KEY_ENV) or "").strip().strip('"')
    if not key:
        raise CustomsKeyMissing(
            f"{KEY_ENV} 가 설정되지 않았습니다. Streamlit Cloud 앱 설정 → Secrets 에 "
            f'{KEY_ENV} = "일반 인증키(Decoding)" 를 **루트 레벨**로 넣으십시오.')
    if "%" in key:          # Encoding 키를 넣은 경우 — 한 번 풉니다
        key = urllib.parse.unquote(key)
    return key


def key_fingerprint() -> str:
    key = (os.environ.get(KEY_ENV) or "").strip()
    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else ""


def _scrub(text: str, key: str) -> str:
    if not key:
        return text
    for k in {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}:
        text = text.replace(k, "…")
    return text


# ──────────────────────────────────────────────────────────────────────────────
# 파싱 — 네트워크 없이 테스트합니다
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Row:
    month: str              # "2026-09"
    country: str
    hs: str
    name: str
    exp_kg: float
    exp_usd: float


def _f(text: str | None) -> float:
    try:
        return float((text or "0").replace(",", ""))
    except ValueError:
        return 0.0


def parse_xml(xml_text: str) -> tuple[str, str, list[Row]]:
    """응답 XML → (결과코드, 결과메시지, 행 목록). 기간이 'YYYY.MM' 이 아닌 행(총계 등)은 뺍니다."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise CustomsError(f"응답이 XML 이 아닙니다: {exc}") from None
    code = (root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or "").strip()
    msg = (root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg")
           or root.findtext(".//errMsg") or "").strip()
    rows: list[Row] = []
    for it in root.iter("item"):
        year = (it.findtext("year") or "").strip()
        if len(year) != 7 or year[4] != "." or not (year[:4] + year[5:]).isdigit():
            continue
        rows.append(Row(
            month=f"{year[:4]}-{year[5:]}", country=(it.findtext("statCd") or "").strip(),
            hs=(it.findtext("hsCd") or "").strip(), name=(it.findtext("statKor") or "").strip(),
            exp_kg=_f(it.findtext("expWgt")), exp_usd=_f(it.findtext("expDlr"))))
    return code, msg, rows


# ──────────────────────────────────────────────────────────────────────────────
# 집계
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Month:
    month: str
    usd: float = 0.0
    kg: float = 0.0
    by_item: dict = field(default_factory=dict)     # hs → [name, usd, kg]

    @property
    def unit(self) -> float | None:
        """kg 당 달러."""
        return self.usd / self.kg if self.kg > 0 else None


@dataclass
class Series:
    months: list[Month]
    coverage: str                    # "전체 국가" / "주요 12개국 합계 (CN·HK…)"
    hs: str = HS_MEMORY
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and any(m.kg > 0 for m in self.months)

    def get(self, month: str) -> Month | None:
        return next((m for m in self.months if m.month == month), None)

    @property
    def latest(self) -> Month | None:
        return next((m for m in reversed(self.months) if m.kg > 0), None)

    def change(self, month: str, back: int, attr: str = "unit") -> float | None:
        """month 대비 back 개월 전 변화율(%)."""
        cur = self.get(month)
        prev = self.get(shift_month(month, -back))
        if cur is None or prev is None:
            return None
        a, b = getattr(cur, attr), getattr(prev, attr)
        if a is None or not b:
            return None
        return (a / b - 1) * 100


def shift_month(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def aggregate(rows: list[Row], coverage: str, hs_prefix: str = HS_MEMORY) -> Series:
    """행 → 월별 합계. 같은 (월, 국가, HS) 가 두 번 오면 한 번만 셉니다
    (국가코드 없이 부른 결과와 국가별 결과가 섞이는 경우 대비)."""
    seen: set[tuple[str, str, str]] = set()
    by_month: dict[str, Month] = {}
    for r in rows:
        if not r.hs.startswith(hs_prefix):
            continue
        k = (r.month, r.country, r.hs)
        if k in seen:
            continue
        seen.add(k)
        m = by_month.setdefault(r.month, Month(r.month))
        m.usd += r.exp_usd
        m.kg += r.exp_kg
        item = m.by_item.setdefault(r.hs, [r.name, 0.0, 0.0])
        item[1] += r.exp_usd
        item[2] += r.exp_kg
    return Series(months=[by_month[k] for k in sorted(by_month)], coverage=coverage, hs=hs_prefix)


# ──────────────────────────────────────────────────────────────────────────────
# 받기
# ──────────────────────────────────────────────────────────────────────────────

def _get(params: dict, key: str) -> tuple[str, str, list[Row]]:
    global _last
    gap = time.monotonic() - _last
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last = time.monotonic()
    try:
        resp = requests.get(URL, params={"serviceKey": key, **params}, timeout=TIMEOUT)
        text = resp.text
    except requests.RequestException as exc:
        raise CustomsError(_scrub(f"관세청 요청 실패: {exc}", key)) from None
    if resp.status_code != 200:
        raise CustomsError(_scrub(f"관세청 HTTP {resp.status_code}: {text[:160]}", key))
    return parse_xml(text)


def windows(end_month: str, months: int = 24) -> list[tuple[str, str]]:
    """end_month 까지 months 개월을 12개월 이하 구간으로 자릅니다 (API 가 1년 이내만 받음)."""
    start = shift_month(end_month, -(months - 1))
    out = []
    cur = start
    while cur <= end_month:
        stop = min(shift_month(cur, 11), end_month)
        out.append((cur.replace("-", ""), stop.replace("-", "")))
        cur = shift_month(stop, 1)
    return out


def fetch(today: dt.date | None = None, months: int = 25, hs: str = HS_MEMORY) -> Series:
    """최근 months 개월 메모리 수출. 실패해도 던지지 않고 Series(error=...) 로 돌려줍니다."""
    today = today or dt.date.today()
    try:
        key = api_key()
    except CustomsKeyMissing as exc:
        return Series([], "", error=str(exc))
    end = shift_month(f"{today.year}-{today.month:02d}", -1)
    wins = windows(end, months)
    warnings: list[str] = []

    # 1) 국가코드 없이 — 전체가 오면 그걸 씁니다
    try:
        code, msg, rows = _get({"strtYymm": wins[-1][0], "endYymm": wins[-1][1], "hsSgn": hs}, key)
    except CustomsError as exc:
        return Series([], "", error=str(exc))
    if code in ("00", "0", "") and rows and len({r.country for r in rows}) > 1:
        all_rows = list(rows)
        for a, b in wins[:-1]:
            try:
                _c, _m, more = _get({"strtYymm": a, "endYymm": b, "hsSgn": hs}, key)
                all_rows += more
            except CustomsError as exc:
                warnings.append(str(exc))
        s = aggregate(all_rows, "전체 국가", hs)
        s.warnings = warnings
        return s
    if code and code not in ("00", "0"):
        warnings.append(f"국가코드 없이 호출 → {code} {msg}".strip())

    # 2) 주요 수출국을 하나씩
    all_rows = []
    failed: list[str] = []
    for c in MAJOR_COUNTRIES:
        got_any = False
        for a, b in wins:
            try:
                code, msg, rows = _get({"strtYymm": a, "endYymm": b, "hsSgn": hs, "cntyCd": c}, key)
            except CustomsError as exc:
                failed.append(f"{c}: {exc}")
                break
            if code and code not in ("00", "0"):
                failed.append(f"{c}: {code} {msg}".strip())
                break
            all_rows += rows
            got_any = got_any or bool(rows)
        if not got_any and not any(f.startswith(c + ":") for f in failed):
            warnings.append(f"{c}: 해당 기간 수출 없음")
    if not all_rows:
        reason = failed[0] if failed else "응답에 행이 없습니다"
        return Series([], "", error=f"관세청 자료를 받지 못했습니다 — {reason}", warnings=warnings)
    covered = [c for c in MAJOR_COUNTRIES if not any(f.startswith(c + ":") for f in failed)]
    s = aggregate(all_rows, f"주요 {len(covered)}개국 합계 ({'·'.join(covered)}) — 전체 아님", hs)
    s.warnings = warnings + failed
    return s
