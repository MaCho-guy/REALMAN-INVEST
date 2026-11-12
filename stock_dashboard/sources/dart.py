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
import json
import tempfile
import os
import time
import xml.etree.ElementTree as ET
import threading
import zipfile
from dataclasses import dataclass, field

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
    """요청이 실패했을 때."""

    def __init__(self, *args):
        # 연결 실패 문구에는 요청 주소(인증키 포함)가 통째로 들어옵니다.
        # 오류가 만들어지는 순간에 지워, 어디로 흘러가든 키가 없게 합니다.
        from . import safe  # noqa: PLC0415
        super().__init__(*(safe.scrub(a) if isinstance(a, str) else a for a in args))


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


#: corpCode.xml 은 수 MB 짜리 ZIP 입니다. 해외(스트림릿 클라우드는 미국)
#: 에서 받으면 20초 안에 못 끝날 때가 있어 따로 길게 잡고 한 번 더 시도합니다.
#: (연결 10초, 읽기 90초)
BIG_TIMEOUT = (10, 90)
BIG_ENDPOINTS = ("corpCode.xml",)


def _describe(exc: Exception) -> str:
    """requests 예외를 사람이 읽는 원인으로. 전문도 뒤에 붙입니다.

    'HTTPSConnectionPool(host=...' 로 시작하는 원문은 앞부분만 보이면
    무엇이 문제인지 알 수 없습니다 — 원인 종류를 **앞에** 적습니다.
    """
    from . import safe  # noqa: PLC0415
    name = type(exc).__name__
    text = safe.scrub(str(exc))      # 요청 주소에 든 인증키를 지웁니다
    if isinstance(exc, requests.ConnectTimeout) or "ConnectTimeout" in text:
        kind = "연결 시간 초과 — 서버에 닿지 못함 (해외 접속 차단 가능성)"
    elif isinstance(exc, requests.ReadTimeout) or "Read timed out" in text:
        kind = "응답 시간 초과 — 연결은 됐지만 내려받기가 끝나지 않음"
    elif "NameResolution" in text or "getaddrinfo" in text:
        kind = "주소 조회 실패 (DNS)"
    elif "SSL" in text:
        kind = "보안 연결(SSL) 실패"
    elif "Connection refused" in text or "ConnectionResetError" in text \
            or "RemoteDisconnected" in text:
        kind = "서버가 연결을 끊음"
    elif isinstance(exc, requests.HTTPError):
        kind = f"HTTP 오류 {getattr(exc.response, 'status_code', '')}"
    else:
        kind = name
    return f"{kind} · 원문: {text[:300]}"


def _get(endpoint: str, params: dict, *, binary: bool = False) -> object:
    query = {"crtfc_key": api_key(), **params}
    url = f"{BASE}/{endpoint}"
    big = endpoint in BIG_ENDPOINTS
    attempts = 2 if big else 1
    last: Exception | None = None
    for _i in range(attempts):
        _throttle()
        try:
            resp = requests.get(
                url, params=query, timeout=BIG_TIMEOUT if big else TIMEOUT,
                headers={"User-Agent": "stock-dashboard/1.0 (personal dashboard)"},
            )
            resp.raise_for_status()
            last = None
            break
        except requests.RequestException as exc:
            last = exc
    if last is not None:
        raise DartError(f"DART 요청 실패 ({endpoint}): {_describe(last)}") from last

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

#: 고유번호 매핑을 디스크에 둡니다. 스트림릿 캐시는 앱이 다시 켜지면
#: 사라지는데, 이 파일은 수 MB 를 매번 해외에서 받아야 합니다.
CORP_CACHE = os.path.join(tempfile.gettempdir(), "dash_dart_corp_codes.json")
CORP_CACHE_MAX_AGE = 7 * 86_400


def _read_corp_cache(max_age: float = CORP_CACHE_MAX_AGE) -> dict | None:
    try:
        if time.time() - os.path.getmtime(CORP_CACHE) > max_age:
            return None
        with open(CORP_CACHE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and data else None
    except (OSError, ValueError):
        return None


def _write_corp_cache(data: dict) -> None:
    try:
        tmp = CORP_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, CORP_CACHE)
    except OSError:
        pass


def fetch_corp_codes() -> dict[str, dict[str, str]]:
    """디스크에 7일 안쪽 사본이 있으면 그걸, 없으면 DART 에서 받습니다.

    받기에 실패해도 **오래된 사본**이 있으면 그걸 씁니다 — 상장사의
    고유번호는 거의 바뀌지 않습니다.
    """
    cached = _read_corp_cache()
    if cached:
        return cached
    try:
        fresh = _fetch_corp_codes_remote()
    except DartError:
        stale = _read_corp_cache(max_age=10 ** 9)
        if stale:
            return stale
        raise
    _write_corp_cache(fresh)
    return fresh


def _fetch_corp_codes_remote() -> dict[str, dict[str, str]]:
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
        # 가운뎃점(· / ㆍ)과 띄어쓰기를 지우고 비교합니다 — 예전에는
        # '현금·현물배당'(U+00B7)이 DART 의 'ㆍ'(U+318D) 와 안 맞아 배당
        # 공시가 중요도 1 로 묻혔습니다. 시장 공시 세부 유형도 중요로 봅니다.
        flat = _flatten(self.report_nm)
        if any(_flatten(k) in flat for k in IMPORTANT_REPORT_KEYWORDS):
            return 2
        return 2 if classify_detail(self.report_nm) else 1

    @property
    def category(self) -> str:
        """시장 공시와 같은 세부 유형 이름 (없으면 빈 문자열)."""
        kind = classify_detail(self.report_nm)
        return kind.label if kind else ""

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

@dataclass(frozen=True)
class DisclosureType:
    """공시 세부 유형 하나.

    group 은 큰 묶음(화면의 색 배지), label 은 세부 이름(표에 함께 적힘),
    why 는 '이 공시가 뜨면 무엇을 보면 되는가' 입니다. why 는 좋다/나쁘다를
    판정하지 않고 **구조**만 적습니다 — 같은 유상증자라도 시설투자용과
    운영자금용은 의미가 다르고, 그 판단은 보고서 본문을 봐야 합니다.
    """

    group: str
    label: str
    needles: tuple[str, ...]
    why: str


#: 큰 묶음. 이 순서가 같은 날짜 안에서의 정렬 순서이자 배지 순서입니다.
DISCLOSURE_GROUPS: tuple[str, ...] = (
    "경고", "실적", "희석·물량", "주주환원", "지분·M&A",
    "사업·계약", "주식수 변동", "일정·IR",
)

#: 묶음별 배지 색 (theme.py 의 .dash-fk-* 클래스).
GROUP_TONE: dict[str, str] = {
    "경고": "risk", "실적": "earn", "희석·물량": "dilute",
    "주주환원": "return", "지분·M&A": "owner", "사업·계약": "biz",
    "주식수 변동": "neutral", "일정·IR": "neutral",
}

#: 세부 유형. **위에서부터 처음 맞는 것** 하나로 분류합니다. 그래서
#: 겹치는 말은 구체적인 쪽을 위에 둡니다 — 예: '자기주식취득신탁' 이
#: '자기주식취득' 보다 위, '주식분할' 이 '회사분할' 과 다른 바늘을 씀,
#: '유무상증자' 가 '무상증자' 보다 위.
DISCLOSURE_TYPES: tuple[DisclosureType, ...] = (
    # ── 경고 ────────────────────────────────────────────────────────────
    DisclosureType("경고", "상장폐지", ("상장폐지",),
                   "상장폐지 사유 발생·실질심사 대상 여부. 거래정지와 "
                   "정리매매로 이어질 수 있어 사유와 일정부터 확인합니다."),
    DisclosureType("경고", "관리종목", ("관리종목",),
                   "관리종목 지정·해제. 지정 사유(자본잠식, 매출 미달, "
                   "감사의견 등)가 해소되지 않으면 상장폐지 심사로 갑니다."),
    DisclosureType("경고", "회생·부도", ("회생절차", "파산신청", "부도발생",
                                       "은행거래정지"),
                   "회생절차·파산·부도. 기존 주주의 권리가 크게 줄 수 있는 "
                   "사건입니다."),
    DisclosureType("경고", "감사의견", ("감사의견", "감사범위제한"),
                   "감사의견 비적정(한정·부적정·거절) 관련. 의견거절은 "
                   "상장폐지 사유입니다."),
    DisclosureType("경고", "횡령·배임", ("횡령", "배임"),
                   "임직원 횡령·배임 혐의 발생·확인. 금액이 자기자본 대비 "
                   "몇 %인지가 보고서에 적힙니다."),
    DisclosureType("경고", "거래정지", ("매매거래정지", "거래정지"),
                   "매매거래 정지·재개. 정지 사유가 감자·병합 같은 절차인지, "
                   "사건인지에 따라 다릅니다."),
    DisclosureType("경고", "불성실공시", ("불성실공시",),
                   "공시 번복·지연 등으로 지정. 벌점이 쌓이면 관리종목 "
                   "사유가 됩니다."),
    DisclosureType("경고", "투자경고·위험", ("투자경고", "투자위험",
                                           "투자주의환기"),
                   "거래소가 단기 급등·이상 거래로 지정. 지정 중에는 "
                   "매매가 제한될 수 있습니다."),
    DisclosureType("경고", "소송", ("소송등의제기", "소송등의판결",
                                  "경영권분쟁소송"),
                   "소송 제기·판결. 청구 금액이 자기자본 대비 몇 %인지 "
                   "보고서에 적힙니다."),
    DisclosureType("경고", "조회·해명", ("조회공시요구", "풍문또는보도"),
                   "주가 급변이나 보도에 대해 거래소가 묻고 회사가 답한 것. "
                   "'미확정' 답변은 아직 결정되지 않았다는 뜻이며 재공시 "
                   "기한이 붙습니다."),
    # ── 실적 ────────────────────────────────────────────────────────────
    DisclosureType("실적", "잠정실적", ("영업(잠정)실적",),
                   "분기 실적 속보. 감사 전 숫자라 정기보고서에서 바뀔 수 "
                   "있습니다. 전년 동기·직전 분기 대비를 같이 봅니다."),
    DisclosureType("실적", "손익구조 변동", ("매출액또는손익구조",),
                   "연간 매출·손익이 직전 연도 대비 30%(대규모법인 15%) "
                   "이상 바뀌면 내는 공시. 연말 결산 전에 나옵니다."),
    DisclosureType("실적", "실적 전망", ("영업실적등에대한전망",),
                   "회사가 스스로 낸 전망(공정공시). 이후 실제 실적과 "
                   "비교할 기준점입니다."),
    DisclosureType("실적", "결산 예고", ("결산실적공시예고",),
                   "실적 발표 날짜 예고."),
    # ── 희석·물량 ───────────────────────────────────────────────────────
    DisclosureType("희석·물량", "유상증자", ("유무상증자", "유상증자결정"),
                   "새 주식을 돈 받고 발행 → 주식 수 증가. 배정 방식(주주·"
                   "제3자·일반공모), 할인율, 자금 용도를 봅니다."),
    DisclosureType("희석·물량", "전환사채(CB)", ("전환사채권발행결정",),
                   "나중에 주식으로 바뀔 수 있는 채권. 전환가액, 리픽싱 "
                   "하한, 전환 가능 시점이 희석 규모를 정합니다."),
    DisclosureType("희석·물량", "신주인수권부사채(BW)",
                   ("신주인수권부사채권발행결정",),
                   "새 주식을 살 권리가 붙은 채권. 행사가액과 행사 시점을 "
                   "봅니다."),
    DisclosureType("희석·물량", "교환사채(EB)", ("교환사채권발행결정",),
                   "회사가 가진 주식(자사주 등)으로 바꿔 주는 채권. 새 주식은 "
                   "안 늘지만 교환되면 그 주식이 시장에 나옵니다."),
    DisclosureType("희석·물량", "가액 조정(리픽싱)",
                   ("전환가액의조정", "행사가액의조정", "교환가액의조정",
                    "행사가액조정"),
                   "주가가 내려 전환·행사 가격이 낮아짐 → 같은 사채로 받는 "
                   "주식 수가 늘어납니다."),
    DisclosureType("희석·물량", "전환·행사 청구",
                   ("전환청구권행사", "신주인수권행사", "교환청구권행사"),
                   "사채가 실제 주식으로 바뀜. 상장일 이후 매도 가능한 "
                   "물량입니다."),
    DisclosureType("희석·물량", "추가상장", ("추가상장",),
                   "전환·증자 등으로 생긴 주식이 실제로 상장되는 날."),
    DisclosureType("희석·물량", "자사주 처분", ("자기주식처분",),
                   "회사가 가진 자사주를 시장·특정인에게 넘김. 소각과 반대 "
                   "방향입니다."),
    DisclosureType("희석·물량", "감자", ("감자결정",),
                   "자본금 감소. 무상감자(대가 없음)인지 유상감자인지, "
                   "감자 비율과 거래정지 기간을 봅니다."),
    # ── 주주환원 ────────────────────────────────────────────────────────
    DisclosureType("주주환원", "자사주 신탁", ("자기주식취득신탁",),
                   "증권사 신탁으로 자사주를 사는 계약. 계약 금액만큼 다 "
                   "산다는 보장은 없어 이후 결과 보고를 봅니다."),
    DisclosureType("주주환원", "자사주 취득", ("자기주식취득결정", "자기주식취득결과"),
                   "회사가 직접 자사주 매입. 취득 후 소각할지 보유할지가 "
                   "같이 적히는지 봅니다."),
    DisclosureType("주주환원", "소각", ("주식소각결정", "자기주식소각"),
                   "주식을 없앰 → 주식 수 감소."),
    DisclosureType("주주환원", "배당", ("배당결정", "배당기준일"),
                   "배당 결정·기준일. 주당 배당금, 시가배당률, 기준일을 "
                   "봅니다."),
    # ── 지분·M&A ────────────────────────────────────────────────────────
    DisclosureType("지분·M&A", "최대주주 변경", ("최대주주변경",),
                   "경영권이 바뀌거나 바뀌기로 계약. 새 최대주주와 양수도 "
                   "가격을 봅니다."),
    DisclosureType("지분·M&A", "공개매수", ("공개매수",),
                   "정해진 가격에 주식을 사겠다는 공개 제안. 매수 가격·"
                   "기간·목표 지분을 봅니다."),
    DisclosureType("지분·M&A", "5% 대량보유", ("주식등의대량보유상황보고",),
                   "누군가 5% 이상 보유하게 됐거나 1%p 이상 변동. 보유 "
                   "목적(단순투자·일반투자·경영참여)을 봅니다."),
    DisclosureType("지분·M&A", "분할", ("회사분할", "분할합병", "물적분할",
                                      "인적분할"),
                   "회사를 나눔. 물적분할은 자회사로, 인적분할은 기존 주주가 "
                   "새 회사 주식도 받습니다."),
    DisclosureType("지분·M&A", "합병", ("합병결정",),
                   "회사를 합침. 합병비율과 반대 주주 매수청구가격을 봅니다."),
    DisclosureType("지분·M&A", "주식교환·이전", ("주식교환", "주식이전결정"),
                   "완전자회사로 만드는 절차. 교환비율을 봅니다."),
    DisclosureType("지분·M&A", "영업 양수도", ("영업양수", "영업양도"),
                   "사업부를 사고팖."),
    DisclosureType("지분·M&A", "타법인 주식", ("타법인주식및출자증권",),
                   "다른 회사 지분을 사거나 팖. 금액이 자기자본 대비 몇 "
                   "%인지 적힙니다."),
    DisclosureType("지분·M&A", "유형자산 양수도", ("유형자산취득", "유형자산처분",
                                               "유형자산양수", "유형자산양도"),
                   "공장·토지·건물 등을 사고팖."),
    # ── 사업·계약 ───────────────────────────────────────────────────────
    DisclosureType("사업·계약", "공급계약 해지", ("공급계약해지",),
                   "이미 공시한 공급계약이 해지됨. 원래 계약 금액을 같이 "
                   "봅니다."),
    DisclosureType("사업·계약", "공급계약", ("공급계약체결",),
                   "일정 규모 이상 판매·공급 계약. 계약 금액이 최근 매출 "
                   "대비 몇 %인지와 계약 기간을 봅니다."),
    DisclosureType("사업·계약", "시설투자", ("신규시설투자",),
                   "공장 등 새 시설 투자. 투자 금액이 자기자본 대비 몇 "
                   "%인지 봅니다."),
    DisclosureType("사업·계약", "기술·임상", ("기술이전", "기술도입", "임상시험",
                                           "품목허가"),
                   "기술이전 계약·임상 진행·허가. 계약금(선급금)과 조건부 "
                   "금액(마일스톤)을 나눠 봅니다."),
    DisclosureType("사업·계약", "수주", ("수주",),
                   "수주 공시."),
    DisclosureType("사업·계약", "특허", ("특허권취득",),
                   "특허 취득."),
    # ── 주식수 변동 (가치 변화 없음) ───────────────────────────────────
    DisclosureType("주식수 변동", "무상증자", ("무상증자결정",),
                   "주식을 공짜로 나눠 줌. 주식 수가 늘고 권리락으로 주가가 "
                   "조정됩니다 — 회사 가치는 그대로입니다."),
    DisclosureType("주식수 변동", "액면분할", ("주식분할결정",),
                   "한 주를 여러 주로 쪼갬. 회사 가치는 그대로입니다."),
    DisclosureType("주식수 변동", "주식병합", ("주식병합결정",),
                   "여러 주를 한 주로 합침. 회사 가치는 그대로입니다."),
    # ── 일정·IR ─────────────────────────────────────────────────────────
    DisclosureType("일정·IR", "IR 개최", ("기업설명회",),
                   "기업설명회 일정. 자료가 IR 페이지에 올라옵니다."),
    DisclosureType("일정·IR", "주총 소집", ("주주총회소집결의",),
                   "주주총회 안건(이사 선임, 정관 변경 등)."),
)

#: 예전 이름 → 지금 묶음. 화면이나 테스트가 옛 이름을 써도 안 깨지게.
DISCLOSURE_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    (g, tuple(n for t in DISCLOSURE_TYPES if t.group == g for n in t.needles))
    for g in DISCLOSURE_GROUPS
)


@dataclass
class MarketFiling:
    """시장 전체 공시 한 건."""

    date: str              # YYYY-MM-DD
    corp_name: str
    stock_code: str
    title: str
    kind: str              # 큰 묶음 (DISCLOSURE_GROUPS)
    rcept_no: str = ""
    sub: str = ""          # 세부 유형 (DisclosureType.label)
    market: str = ""       # 코스피 / 코스닥
    flags: tuple[str, ...] = ()   # 정정 · 자회사 · 철회 …
    filer: str = ""        # 제출인 — 대량보유는 '누가' 가 핵심

    @property
    def url(self) -> str:
        if not self.rcept_no:
            return ""
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"

    @property
    def tone(self) -> str:
        return GROUP_TONE.get(self.kind, "neutral")


@dataclass
class FilingScan:
    """시장 공시를 훑은 결과 — 무엇을 받았고 어디까지 봤는가."""

    filings: list[MarketFiling]
    scanned: int = 0                      # 읽은 공시 수 (추리기 전)
    begin: str = ""                       # 요청한 시작일
    gaps: list[str] = field(default_factory=list)   # '여기까지만 봤다'
    fallback: bool = False                # 유형 필터가 안 먹어 옛 방식으로


#: 가운뎃점은 DART 가 ㆍ(U+318D) 를 쓰고 사람은 ·(U+00B7) 를 씁니다.
#: 생긴 게 거의 같아서 눈으로는 못 잡고, 매칭만 조용히 실패합니다.
_SEPARATORS = (" ", "·", "ㆍ", "・", "．", ".", ",", "ㆍ")


def _flatten(text: str) -> str:
    out = text or ""
    for ch in _SEPARATORS:
        out = out.replace(ch, "")
    return out


def classify_detail(title: str) -> DisclosureType | None:
    """보고서명 → 세부 유형. 해당 없으면 None."""
    flat = _flatten(title)
    if not flat:
        return None
    for kind in DISCLOSURE_TYPES:
        if any(_flatten(n) in flat for n in kind.needles):
            return kind
    return None


def classify(title: str) -> str:
    """보고서명 → 큰 묶음. 해당 없으면 빈 문자열."""
    kind = classify_detail(title)
    return kind.group if kind else ""


def title_flags(title: str, rm: str = "") -> tuple[str, ...]:
    """제목 앞 [기재정정] 같은 꼬리표와 비고(rm)를 짧은 표시로.

    rm 은 DART 비고 칸의 한 글자 코드입니다: 정=이후 정정공시 있음,
    철=철회, 연=연결 기준. 유·코·채·넥·공 은 공시 접수처라 뺍니다.
    """
    flags: list[str] = []
    head = (title or "").strip()
    if head.startswith("["):
        tag = head[1:head.find("]")] if "]" in head else ""
        if "정정" in tag:
            flags.append("정정")
        elif tag:
            flags.append(tag[:8])
    flat = _flatten(title)
    if "자회사의주요경영사항" in flat or "(자회사" in (title or ""):
        flags.append("자회사")
    if "철" in (rm or ""):
        flags.append("철회")
    elif "정" in (rm or "") and "정정" not in flags:
        flags.append("이후 정정")
    return tuple(flags)


def _nice_date(raw: str) -> str:
    raw = (raw or "").strip()
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 else raw


_MARKET_OF = {"Y": "코스피", "K": "코스닥"}

#: 공시 유형별로 몇 쪽(100건)까지 볼지. B=주요사항보고(증자·사채·자사주·
#: 합병), I=거래소공시(실적·공급계약·조회공시·관리종목), D=지분공시
#: (5% 대량보유 + 임원·주요주주 — 임원 보고가 대부분이라 많이 봐도 남는 게
#: 적어 쪽수를 줄입니다).
SCAN_PAGES: tuple[tuple[str, str, int], ...] = (
    ("B", "주요사항보고", 3),
    ("I", "거래소공시", 6),
    ("D", "지분공시", 3),
)


def _row_to_filing(row: dict, market: str) -> MarketFiling | None:
    title = str(row.get("report_nm") or "").strip()
    kind = classify_detail(title)
    if kind is None:
        return None
    return MarketFiling(
        date=_nice_date(str(row.get("rcept_dt") or "")),
        corp_name=str(row.get("corp_name") or "").strip(),
        stock_code=str(row.get("stock_code") or "").strip(),
        title=title, kind=kind.group,
        rcept_no=str(row.get("rcept_no") or "").strip(),
        sub=kind.label, market=market,
        flags=title_flags(title, str(row.get("rm") or "")),
        filer=str(row.get("flr_nm") or "").strip(),
    )


def _sort_filings(out: list[MarketFiling]) -> None:
    order = {g: i for i, g in enumerate(DISCLOSURE_GROUPS)}
    # 날짜 최신 → 같은 날은 묶음 순서(경고·실적 먼저) → 접수 최신.
    out.sort(key=lambda f: (f.date, -order.get(f.kind, 99), f.rcept_no),
             reverse=True)


def scan_market_filings(*, days: int = 5, limit: int = 300,
                        today: dt.date | None = None,
                        get=None) -> FilingScan:
    """최근 며칠간 시장 전체 공시를 **세부 유형으로** 추립니다.

    corp_code 없이 부르면 전체 시장이 옵니다. 정기·발행·펀드 공시까지 섞이면
    하루 수천 건이라, 공시 유형(pblntf_ty)으로 먼저 거르고 제목으로 한 번 더
    추립니다. 유가증권·코스닥(corp_cls Y/K)만 남깁니다.

    유형 필터가 한 건도 안 돌려주면(API 가 매개변수를 무시하거나 바뀐 경우)
    예전 방식 — 시장별로 전체 목록을 몇 쪽 — 으로 한 번 더 봅니다.
    """
    get = get or _get
    today = today or dt.date.today()
    begin = today - dt.timedelta(days=max(1, days))
    base = {
        "bgn_de": begin.strftime("%Y%m%d"),
        "end_de": today.strftime("%Y%m%d"),
        "page_count": "100", "sort": "date", "sort_mth": "desc",
    }
    out: list[MarketFiling] = []
    seen: set[str] = set()
    scanned = 0
    gaps: list[str] = []

    def take(rows: list, forced_market: str = "") -> None:
        nonlocal scanned
        for row in rows:
            if not isinstance(row, dict):
                continue
            scanned += 1
            market = forced_market or _MARKET_OF.get(
                str(row.get("corp_cls") or "").strip(), "")
            if not market:
                continue
            filing = _row_to_filing(row, market)
            if filing is None or filing.rcept_no in seen:
                continue
            seen.add(filing.rcept_no)
            out.append(filing)

    def walk(params: dict, pages: int, name: str, forced: str = "") -> int:
        got = 0
        oldest = ""
        for page in range(1, pages + 1):
            payload = get("list.json", {**base, **params,
                                        "page_no": str(page)})
            if not isinstance(payload, dict):
                break
            rows = payload.get("list")
            if not isinstance(rows, list) or not rows:
                break
            got += len(rows)
            oldest = str(rows[-1].get("rcept_dt") or oldest) \
                if isinstance(rows[-1], dict) else oldest
            take(rows, forced)
            try:
                total = int(payload.get("total_page") or 1)
            except (TypeError, ValueError):
                total = 1
            if page >= total:
                break
            if page == pages and oldest and oldest > base["bgn_de"]:
                gaps.append(f"{name}는 {_nice_date(oldest)[5:]} 이후만 "
                            f"훑었습니다 ({pages}쪽 한도)")
        return got

    total_rows = 0
    for ty, name, pages in SCAN_PAGES:
        try:
            total_rows += walk({"pblntf_ty": ty}, pages, name)
        except DartError as exc:
            # '조회된 데이터가 없습니다'(013) 는 오류가 아니라 0건입니다.
            if "013" not in str(exc):
                raise

    fallback = False
    if total_rows == 0:
        fallback = True
        for cls, market in _MARKET_OF.items():
            try:
                walk({"corp_cls": cls}, 3, market, forced=market)
            except DartError as exc:
                if "013" not in str(exc):
                    raise

    _sort_filings(out)
    return FilingScan(filings=out[:limit], scanned=scanned,
                      begin=begin.isoformat(), gaps=gaps, fallback=fallback)


def fetch_market_filings(*, days: int = 5, pages: int = 3,
                         limit: int = 300) -> list[MarketFiling]:
    """예전 호출 모양 — 목록만 돌려줍니다. pages 는 이제 쓰지 않습니다."""
    return scan_market_filings(days=days, limit=limit).filings


#: 큰 묶음에 들지 않는 공시(정기보고서·기타)에 붙이는 이름.
OTHER_GROUP = "기타 공시"


def to_market_filing(d: "Disclosure", stock_code: str = "") -> MarketFiling:
    """종목별 공시 한 건을 시장 공시 표가 그리는 모양으로.

    시장 공시는 '중요한 유형' 만 추려 300건까지 담습니다. 그래서 '내 종목만'
    을 켜면 대부분 비었습니다 (내 종목에 그 며칠 사이 그런 공시가 없으면
    0건). 내 종목은 **유형을 가리지 않고 전부** 보여주는 것이 맞아서,
    종목별로 받은 공시를 이 모양으로 바꿔 같은 표에 넣습니다.
    """
    kind = classify_detail(d.report_nm)
    return MarketFiling(
        date=d.date_iso, corp_name=d.corp_name,
        stock_code=d.stock_code or stock_code, title=d.report_nm,
        kind=kind.group if kind else OTHER_GROUP,
        rcept_no=d.rcept_no, sub=kind.label if kind else "",
        flags=title_flags(d.report_nm, d.rm), filer=d.flr_nm)


def filter_filings(filings: list[MarketFiling], *, groups=(), subs=(),
                   market: str = "", codes=None) -> list[MarketFiling]:
    """화면 필터. 비어 있는 조건은 '전부' 로 봅니다."""
    groups, subs = set(groups or ()), set(subs or ())
    out = []
    for f in filings:
        if groups and f.kind not in groups:
            continue
        if subs and f.sub not in subs:
            continue
        if market and f.market != market:
            continue
        if codes is not None and f.stock_code not in codes:
            continue
        out.append(f)
    return out


def count_filings(filings: list[MarketFiling]) -> list[tuple[str, int, list[tuple[str, int]]]]:
    """[(묶음, 건수, [(세부, 건수) …])] — 묶음 순서대로, 0건 묶음은 뺌."""
    by: dict[str, dict[str, int]] = {}
    for f in filings:
        by.setdefault(f.kind, {})
        by[f.kind][f.sub or f.kind] = by[f.kind].get(f.sub or f.kind, 0) + 1
    out = []
    for g in DISCLOSURE_GROUPS:
        if g in by:
            subs = sorted(by[g].items(), key=lambda kv: -kv[1])
            out.append((g, sum(by[g].values()), subs))
    for g, subs_map in by.items():          # 알 수 없는 묶음도 버리지 않음
        if g not in DISCLOSURE_GROUPS:
            out.append((g, sum(subs_map.values()), list(subs_map.items())))
    return out
