"""
DART 오픈API (금융감독원 전자공시) — 한국 종목 공시·재무제표.

================================================================================
EDGAR 와 다른 점 — 키가 필요합니다
================================================================================
SEC EDGAR 는 키 없이 쓸 수 있지만, DART 는 무료지만 **인증키 발급이 필요**합니다.

  1. https://opendart.fss.or.kr 회원가입 (이메일 인증)
  2. '인증키 신청/관리' → 신청 → 메일 인증
  3. '오픈API 이용현황' 에서 40자리 키 확인

키는 **환경변수로만** 받습니다. config.py 에 적어 두면 압축 파일이나 저장소에
섞여 나갈 수 있습니다.

    export DART_API_KEY="40자리키"          # macOS/Linux
    setx DART_API_KEY "40자리키"            # Windows (새 터미널부터 적용)

호출 한도는 인증키당 하루 20,000건입니다. 이 모듈은 캐시를 길게 두고,
종목 2~3개만 조회하므로 한도에 근접할 일은 없습니다.

================================================================================
엔드포인트
================================================================================
고유번호    GET /api/corpCode.xml        → ZIP(binary) 안에 CORPCODE.xml
공시검색    GET /api/list.json           → 접수일자 역순 공시 목록
전체재무제표 GET /api/fnlttSinglAcntAll.json → 계정 단위 전 항목

종목코드(005930)와 DART 고유번호(corp_code, 8자리)는 **다릅니다.**
그래서 corpCode.xml 을 받아 stock_code → corp_code 로 변환한 뒤 호출합니다.

보고서 코드: 11013=1분기, 11012=반기, 11014=3분기, 11011=사업보고서
재무제표 구분: CFS=연결, OFS=별도

주의 — 분기 손익계산서의 thstrm_amount 는 **3개월 금액**이고,
thstrm_add_amount 가 누적 금액입니다. DIO 계산 시 기간을 맞춰야 합니다.
재무정보 API 는 2015년 이후 데이터만 제공합니다.

상태 코드: 000 정상 / 010 미등록 키 / 011 사용중지 키 / 013 데이터 없음
          / 020 요청 제한 초과 / 100 필드 부적절 / 800 시스템 점검 / 901 키 오류
"""

from __future__ import annotations

import datetime as dt
import io
import os
import time
import xml.etree.ElementTree as ET
import threading
import zipfile
from dataclasses import dataclass

import requests

BASE = "https://opendart.fss.or.kr/api"
TIMEOUT = 20
MIN_INTERVAL = 0.12          # 8.3건/초 — DART 는 일일 한도(2만건)가 주 제약입니다

REPORT_CODES = {
    "1Q": "11013",
    "2Q": "11012",   # 반기
    "3Q": "11014",
    "FY": "11011",   # 사업보고서
}
REPORT_LABELS = {
    "11013": "1분기보고서",
    "11012": "반기보고서",
    "11014": "3분기보고서",
    "11011": "사업보고서",
}

STATUS_MESSAGES = {
    "000": "정상",
    "010": "등록되지 않은 인증키입니다. opendart.fss.or.kr 에서 발급받은 40자리 키인지 확인하십시오.",
    "011": "사용할 수 없는 인증키입니다 (일시 중지 상태).",
    "012": "접근할 수 없는 IP 입니다.",
    "013": "조회된 데이터가 없습니다. 해당 분기 보고서가 아직 공시되지 않았을 수 있습니다.",
    "014": "파일이 존재하지 않습니다.",
    "020": "요청 제한을 초과했습니다 (인증키당 하루 20,000건).",
    "021": "조회 가능한 회사 개수가 초과했습니다.",
    "100": "필드의 부적절한 값입니다.",
    "101": "부적절한 접근입니다.",
    "800": "시스템 점검 중입니다.",
    "900": "정의되지 않은 오류입니다.",
    "901": "인증키가 올바르지 않습니다.",
}

#: 관심 공시 유형 — 보고서명에 이 문구가 들어가면 중요도 2
IMPORTANT_REPORT_KEYWORDS = (
    "사업보고서", "반기보고서", "분기보고서",
    "주요사항보고서", "영업(잠정)실적", "매출액또는손익구조",
    "유상증자", "무상증자", "주식분할", "합병", "분할",
    "자기주식", "현금·현물배당",
)

_last_request_at = 0.0
_throttle_lock = threading.Lock()


class DartError(RuntimeError):
    pass


class DartKeyMissing(DartError):
    """키가 없어서 호출조차 못 한 경우 — UI 가 안내를 띄우도록 구분합니다."""


def api_key() -> str:
    """환경변수에서 키를 읽습니다. 없으면 DartKeyMissing."""
    key = (os.environ.get("DART_API_KEY") or "").strip()
    if not key:
        raise DartKeyMissing(
            "DART_API_KEY 가 설정되지 않았습니다. "
            "opendart.fss.or.kr 에서 무료로 발급받은 뒤,\n"
            "· 내 컴퓨터: 환경변수로 설정하거나 "
            ".streamlit/secrets.toml 에 넣으십시오\n"
            "· Streamlit Cloud: 앱 설정 → Secrets 에 "
            "DART_API_KEY = \"...\" 를 **루트 레벨**로 넣으십시오 "
            "([섹션] 안에 넣으면 환경변수로 노출되지 않습니다)"
        )
    if len(key) != 40:
        raise DartKeyMissing(
            f"DART_API_KEY 가 40자리가 아닙니다 (현재 {len(key)}자리). "
            f"'오픈API 이용현황' 의 인증키를 그대로 복사했는지 확인하십시오."
        )
    return key


def key_fingerprint() -> str:
    """인증키의 **지문**. 키 자체가 아니라 해시 앞자리입니다.

    왜 필요한가: Streamlit 캐시는 인자가 같으면 결과를 재사용합니다.
    키가 없어 실패한 결과가 24시간 캐시에 남으면, Secrets 에 키를 넣어도
    그대로 실패가 보입니다. 지문을 인자로 넘기면 **키가 생기거나 바뀌는
    순간 캐시 키가 달라져** 자동으로 다시 받아옵니다.

    키를 그대로 넘기지 않는 이유는, 캐시 키가 로그나 오류 메시지에 찍힐
    수 있기 때문입니다.
    """
    import hashlib

    key = (os.environ.get("DART_API_KEY") or "").strip()
    if not key:
        return ""
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def key_status() -> tuple[bool, str]:
    """UI 표시용 — (사용 가능 여부, 설명)."""
    try:
        key = api_key()
    except DartKeyMissing as exc:
        return False, str(exc)
    return True, f"DART 인증키 설정됨 (…{key[-4:]})"


def _throttle() -> None:
    """요청 **시작 시점**을 MIN_INTERVAL 간격으로 벌립니다.

    잠금이 필요한 이유는 edgar_facts._throttle 과 같습니다 — 전역 변수만
    보고 판단하면 두 스레드가 같은 틈을 읽고 동시에 나갑니다.
    """
    global _last_request_at
    with _throttle_lock:
        gap = time.monotonic() - _last_request_at
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_request_at = time.monotonic()


def _check_status(payload: dict, context: str) -> None:
    status = str(payload.get("status") or "")
    if status in ("", "000"):
        return
    message = STATUS_MESSAGES.get(status, payload.get("message") or "알 수 없는 오류")
    raise DartError(f"DART {context} 실패 [{status}]: {message}")


def _get(endpoint: str, params: dict, *, binary: bool = False) -> object:
    _throttle()
    query = {"crtfc_key": api_key(), **params}
    url = f"{BASE}/{endpoint}"
    try:
        resp = requests.get(
            url, params=query, timeout=TIMEOUT,
            headers={"User-Agent": "stock-dashboard/1.0 (personal dashboard)"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DartError(f"DART 요청 실패 ({endpoint}): {exc}") from exc

    if binary:
        # 오류일 때는 바이너리가 아니라 JSON/XML 로 상태를 돌려줍니다
        head = resp.content[:200]
        if not resp.content[:2] == b"PK":
            text = head.decode("utf-8", errors="replace")
            for code, msg in STATUS_MESSAGES.items():
                if f'"status":"{code}"' in text or f"<status>{code}</status>" in text:
                    if code != "000":
                        raise DartError(f"DART 고유번호 조회 실패 [{code}]: {msg}")
            raise DartError(f"DART 고유번호 응답이 ZIP 이 아닙니다: {text[:120]}")
        return resp.content

    try:
        payload = resp.json()
    except ValueError as exc:
        raise DartError(f"DART 응답 파싱 실패 ({endpoint}): {exc}") from exc
    if not isinstance(payload, dict):
        raise DartError(f"DART 응답 형식이 예상과 다릅니다 ({endpoint}).")
    _check_status(payload, endpoint)
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# 고유번호 (corp_code)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_corp_codes() -> dict[str, dict[str, str]]:
    """stock_code(6자리) -> {corp_code, corp_name} 매핑.

    corpCode.xml 은 ZIP 이고 안에 CORPCODE.xml 이 있습니다. 상장사만 추려
    stock_code 로 키를 잡습니다 (비상장사는 stock_code 가 비어 있음).
    약 10만 건이라 호출하는 쪽에서 길게 캐시하십시오.
    """
    raw = _get("corpCode.xml", {}, binary=True)
    assert isinstance(raw, bytes)

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise DartError("corpCode ZIP 안에 XML 이 없습니다.")
            with zf.open(names[0]) as fh:
                tree = ET.parse(fh)
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        raise DartError(f"corpCode 압축/XML 파싱 실패: {exc}") from exc

    out: dict[str, dict[str, str]] = {}
    for node in tree.getroot().iter("list"):
        stock = (node.findtext("stock_code") or "").strip()
        corp = (node.findtext("corp_code") or "").strip()
        name = (node.findtext("corp_name") or "").strip()
        if stock and corp and stock != " ":
            out[stock] = {"corp_code": corp, "corp_name": name}
    if not out:
        raise DartError("corpCode.xml 에서 상장사를 찾지 못했습니다.")
    return out


def resolve_corp_code(stock_code: str, corp_map: dict[str, dict[str, str]],
                      overrides: dict[str, str] | None = None) -> str | None:
    """종목코드 → corp_code. 우선주처럼 매핑에 없으면 보통주로 폴백합니다."""
    if overrides and stock_code in overrides:
        return overrides[stock_code]
    entry = corp_map.get(stock_code)
    if entry:
        return entry["corp_code"]
    # 삼성전자우(005935) 처럼 우선주는 별도 stock_code 지만 같은 법인입니다.
    # 끝자리만 다른 보통주 코드를 시도합니다.
    if len(stock_code) == 6 and stock_code[-1] != "0":
        sibling = stock_code[:-1] + "0"
        entry = corp_map.get(sibling)
        if entry:
            return entry["corp_code"]
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 공시 목록
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Disclosure:
    """공시 한 건."""

    corp_name: str
    report_nm: str          # 보고서명
    rcept_no: str           # 접수번호 (14자리)
    rcept_dt: str           # 접수일자 YYYYMMDD
    flr_nm: str = ""        # 공시 제출인명
    stock_code: str = ""
    rm: str = ""            # 비고 (정정, 첨부 등)

    @property
    def date_iso(self) -> str:
        d = self.rcept_dt
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

    @property
    def url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"

    @property
    def importance(self) -> int:
        return 2 if any(k in self.report_nm for k in IMPORTANT_REPORT_KEYWORDS) else 1

    @property
    def days_ago(self) -> int | None:
        try:
            d = dt.date.fromisoformat(self.date_iso)
        except ValueError:
            return None
        return (dt.date.today() - d).days

    # ── EDGAR Filing 과 같은 모양으로 맞추기 ──────────────────────────────────
    # signals.detect() 가 두 소스를 구분 없이 다룰 수 있게, EDGAR Filing 이
    # 쓰는 속성명을 그대로 제공합니다. (덕 타이핑)

    @property
    def filing_date(self) -> str:
        return self.date_iso

    @property
    def form(self) -> str:
        """보고서명 앞부분 — 화면의 태그로 쓰기 좋게 짧게 잘라냅니다."""
        name = self.report_nm.split("(")[0].strip()
        return name[:18] if name else "공시"

    @property
    def label(self) -> str:
        return self.report_nm

    @property
    def items(self) -> str:
        return self.rm


def fetch_disclosures(corp_code: str, *, since_days: int = 180,
                      limit: int = 20) -> list[Disclosure]:
    """한 기업의 최근 공시 목록 (접수일자 역순)."""
    today = dt.date.today()
    begin = today - dt.timedelta(days=since_days)
    payload = _get("list.json", {
        "corp_code": corp_code,
        "bgn_de": begin.strftime("%Y%m%d"),
        "end_de": today.strftime("%Y%m%d"),
        "page_count": str(min(limit, 100)),
        "sort": "date",
        "sort_mth": "desc",
    })
    assert isinstance(payload, dict)

    rows = payload.get("list")
    if not isinstance(rows, list):
        return []

    out: list[Disclosure] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(Disclosure(
            corp_name=str(row.get("corp_name") or ""),
            report_nm=str(row.get("report_nm") or ""),
            rcept_no=str(row.get("rcept_no") or ""),
            rcept_dt=str(row.get("rcept_dt") or ""),
            flr_nm=str(row.get("flr_nm") or ""),
            stock_code=str(row.get("stock_code") or ""),
            rm=str(row.get("rm") or ""),
        ))
        if len(out) >= limit:
            break
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 전체 재무제표
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Account:
    """재무제표 계정 한 줄."""

    sj_div: str             # BS 재무상태표 / IS 손익계산서 / CIS 포괄손익 / CF 현금흐름
    sj_nm: str
    account_id: str        # XBRL 표준계정ID (표준이 아니면 "-표준계정코드 미사용-")
    account_nm: str
    thstrm_amount: float | None        # 당기 (분기 IS 는 3개월 금액)
    thstrm_add_amount: float | None    # 당기 누적
    frmtrm_amount: float | None        # 전기
    bfefrmtrm_amount: float | None     # 전전기
    thstrm_nm: str = ""


def _amount(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in ("-", "—"):
        return None
    neg = text.startswith("(") and text.endswith(")")
    if neg:
        text = text[1:-1]
    try:
        out = float(text)
    except ValueError:
        return None
    return -out if neg else out


def fetch_financials(corp_code: str, year: int, quarter: str,
                     *, fs_div: str = "CFS") -> list[Account]:
    """단일회사 전체 재무제표.

    quarter 는 "1Q"/"2Q"/"3Q"/"FY". fs_div 는 CFS(연결) 또는 OFS(별도).
    해당 보고서가 아직 공시되지 않으면 상태 013 으로 DartError 가 납니다.
    """
    if quarter not in REPORT_CODES:
        raise DartError(f"알 수 없는 분기 코드: {quarter}")

    payload = _get("fnlttSinglAcntAll.json", {
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPORT_CODES[quarter],
        "fs_div": fs_div,
    })
    assert isinstance(payload, dict)

    rows = payload.get("list")
    if not isinstance(rows, list):
        return []

    out: list[Account] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(Account(
            sj_div=str(row.get("sj_div") or ""),
            sj_nm=str(row.get("sj_nm") or ""),
            account_id=str(row.get("account_id") or ""),
            account_nm=str(row.get("account_nm") or ""),
            thstrm_amount=_amount(row.get("thstrm_amount")),
            thstrm_add_amount=_amount(row.get("thstrm_add_amount")),
            frmtrm_amount=_amount(row.get("frmtrm_amount")),
            bfefrmtrm_amount=_amount(row.get("bfefrmtrm_amount")),
            thstrm_nm=str(row.get("thstrm_nm") or ""),
        ))
    return out


#: 정기보고서 제출 기한. 분기·반기보고서는 기준일 후 45일, 사업보고서는 90일입니다.
#: 하루 여유를 둬서 46일로 잡고, 그래도 없으면(013) 호출하는 쪽이 한 분기 물러섭니다.
FILING_LAG_DAYS = 46

#: 사업보고서는 사업연도 경과 후 90일
ANNUAL_FILING_LAG_DAYS = 91


def latest_available_quarter(today: dt.date | None = None) -> tuple[int, str]:
    """지금 시점에 공시됐을 가능성이 가장 높은 (연도, 분기) 를 추정합니다.

    주의 — **실적발표(잠정)와 정기보고서는 시점이 다릅니다.** 기업은 분기말 후
    2~4주에 잠정실적을 발표하지만, 재고자산 주석이 담긴 분기보고서는 45일 뒤에
    나옵니다. 그래서 이 함수가 돌려주는 분기는 헤드라인 실적보다 한 분기
    뒤처질 수 있습니다. 그게 맞습니다 — 없는 보고서를 조회하면 013 입니다.

    추정이므로, 호출 결과가 013(데이터 없음)이면 호출하는 쪽에서
    previous_quarter() 로 한 분기 물러서야 합니다.
    """
    d = today or dt.date.today()

    # 과거 3년치 분기말을 모두 후보로 둡니다. 전년도 분기를 빼면 연초(1~3월)에
    # '전년 3분기'를 놓치고 엉뚱하게 2년 전 사업보고서로 떨어집니다.
    candidates: list[tuple[dt.date, int, str]] = []
    for year in range(d.year - 3, d.year + 1):
        candidates.append((dt.date(year, 3, 31), year, "1Q"))
        candidates.append((dt.date(year, 6, 30), year, "2Q"))
        candidates.append((dt.date(year, 9, 30), year, "3Q"))
        candidates.append((dt.date(year, 12, 31), year, "FY"))

    available = [
        (end, year, q) for end, year, q in candidates
        if (d - end).days >= (ANNUAL_FILING_LAG_DAYS if q == "FY" else FILING_LAG_DAYS)
    ]
    if not available:
        return d.year - 2, "FY"

    _end, year, quarter = max(available, key=lambda t: t[0])
    return year, quarter


def previous_quarter(year: int, quarter: str) -> tuple[int, str]:
    """한 분기 뒤로 물러섭니다 (FY → 3Q → 2Q → 1Q → 전년 FY)."""
    order = ["1Q", "2Q", "3Q", "FY"]
    idx = order.index(quarter)
    if idx == 0:
        return year - 1, "FY"
    return year, order[idx - 1]


# ──────────────────────────────────────────────────────────────────────────────
# 기업개황 (company.json)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CompanyProfile:
    """DART 기업개황. 숫자가 아니라 '이 회사가 뭐 하는 곳인가' 입니다."""

    stock_code: str
    corp_name: str = ""
    ceo: str = ""
    industry_code: str = ""       # 표준산업분류 코드
    established: str = ""         # YYYYMMDD
    fiscal_month: str = ""        # 결산월 (MM)
    homepage: str = ""
    address: str = ""
    error: str = ""

    @property
    def established_ko(self) -> str:
        d = (self.established or "").strip()
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return d

    @property
    def fiscal_ko(self) -> str:
        m = (self.fiscal_month or "").strip().lstrip("0")
        return f"{m}월" if m else ""


def fetch_company(corp_code: str, stock_code: str = "") -> CompanyProfile:
    """기업개황 한 건.

    **업종명은 돌려주지 않습니다.** DART 가 주는 건 표준산업분류
    *코드*(induty_code)뿐이고, 코드→이름 표는 이 API 에 없습니다.
    코드를 제가 임의로 이름으로 바꾸면 틀릴 수 있어서 코드 그대로 둡니다.
    """
    payload = _get("company.json", {"corp_code": corp_code})
    assert isinstance(payload, dict)
    return CompanyProfile(
        stock_code=stock_code or str(payload.get("stock_code") or "").strip(),
        corp_name=str(payload.get("corp_name") or "").strip(),
        ceo=str(payload.get("ceo_nm") or "").strip(),
        industry_code=str(payload.get("induty_code") or "").strip(),
        established=str(payload.get("est_dt") or "").strip(),
        fiscal_month=str(payload.get("acc_mt") or "").strip(),
        homepage=str(payload.get("hm_url") or "").strip(),
        address=str(payload.get("adres") or "").strip(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 시장 전체 주요 공시
# ──────────────────────────────────────────────────────────────────────────────
#
# corp_code 없이 list.json 을 부르면 **전체 시장**의 공시가 돌아옵니다.
# 하루에 수백 건이라 그대로 보면 못 읽습니다. 그래서 보고서 제목으로
# 추립니다 — 주가에 바로 영향을 주는 유형만 남깁니다.
#
# 제목 매칭의 한계: DART 보고서명은 정해진 양식이라 비교적 안정적이지만,
# 같은 사건이 회사마다 조금씩 다른 이름으로 올라올 수 있습니다. 놓치는
# 쪽(false negative)이 있어도 **엉뚱한 걸 올리는 것보다 낫다**고 보고
# 좁게 잡았습니다.

#: (분류, 제목에 들어가는 말들). 위에 있을수록 중요하게 봅니다.
DISCLOSURE_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("실적", ("영업(잠정)실적", "매출액또는손익구조")),
    ("자본조달", ("유상증자결정", "전환사채권발행결정",
                  "신주인수권부사채권발행결정", "교환사채권발행결정")),
    ("주주환원", ("자기주식취득", "자기주식소각", "현금·현물배당",
                  "무상증자결정")),
    ("지배구조", ("최대주주변경", "주식등의대량보유상황보고",
                  "합병결정", "분할결정", "영업양수도")),
    ("계약", ("단일판매·공급계약체결", "수주")),
    ("경고", ("관리종목", "상장폐지", "감사의견", "불성실공시")),
)


@dataclass
class MarketFiling:
    """시장 전체 공시 한 건."""

    date: str              # YYYY-MM-DD
    corp_name: str
    stock_code: str
    title: str
    kind: str              # DISCLOSURE_KINDS 의 분류
    rcept_no: str = ""

    @property
    def url(self) -> str:
        if not self.rcept_no:
            return ""
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"


#: 가운뎃점은 DART 가 ㆍ(U+318D) 를 쓰고 사람은 ·(U+00B7) 를 씁니다.
#: 생긴 게 거의 같아서 눈으로는 못 잡고, 매칭만 조용히 실패합니다.
_SEPARATORS = (" ", "·", "ㆍ", "・", "．", ".", ",", "ㆍ")


def _flatten(text: str) -> str:
    out = text or ""
    for ch in _SEPARATORS:
        out = out.replace(ch, "")
    return out


def classify(title: str) -> str:
    """보고서명 → 분류. 해당 없으면 빈 문자열."""
    flat = _flatten(title)
    for kind, needles in DISCLOSURE_KINDS:
        if any(_flatten(n) in flat for n in needles):
            return kind
    return ""


def fetch_market_filings(*, days: int = 3, pages: int = 3,
                         limit: int = 60) -> list[MarketFiling]:
    """최근 며칠간 시장 전체 공시 중 **주요 유형만**.

    corp_code 를 넣지 않으면 전체 시장이 돌아옵니다. 하루 수백 건이므로
    페이지를 몇 장만 받고 제목으로 추립니다. 유가증권·코스닥만 봅니다
    (corp_cls Y/K) — 기타법인까지 넣으면 비상장 공시가 대부분입니다.
    """
    today = dt.date.today()
    begin = today - dt.timedelta(days=max(1, days))
    out: list[MarketFiling] = []
    seen: set[str] = set()

    for corp_cls in ("Y", "K"):          # Y=유가증권, K=코스닥
        for page in range(1, max(1, pages) + 1):
            payload = _get("list.json", {
                "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": today.strftime("%Y%m%d"),
                "corp_cls": corp_cls,
                "page_no": str(page),
                "page_count": "100",
                "sort": "date",
                "sort_mth": "desc",
            })
            assert isinstance(payload, dict)
            rows = payload.get("list")
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                title = str(row.get("report_nm") or "").strip()
                kind = classify(title)
                if not kind:
                    continue
                rcept = str(row.get("rcept_no") or "").strip()
                if rcept in seen:
                    continue
                seen.add(rcept)
                raw_date = str(row.get("rcept_dt") or "").strip()
                nice = (f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                        if len(raw_date) == 8 else raw_date)
                out.append(MarketFiling(
                    date=nice,
                    corp_name=str(row.get("corp_name") or "").strip(),
                    stock_code=str(row.get("stock_code") or "").strip(),
                    title=title, kind=kind, rcept_no=rcept,
                ))
            total_page = int(payload.get("total_page") or 1)
            if page >= total_page:
                break

    order = {k: i for i, (k, _n) in enumerate(DISCLOSURE_KINDS)}
    out.sort(key=lambda f: (f.date, -order.get(f.kind, 99)), reverse=True)
    return out[:limit]
