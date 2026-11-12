"""
대시보드 종목/지표 설정.

================================================================================
티커 검증 상태 (2026-11-04 웹 확인 완료)
================================================================================
이전 버전의 추정 티커를 실제 확인값으로 교체했습니다. 확인 내역:

  SMSN      런던증권거래소(IOB) 상장. 정식명 "GDR (EACH REP 25 COM STK KRW100)
            (REG S)" -> 1 GDR = 보통주 25주 확정. USD 호가.
  SMSD      같은 런던 상장이나 "GDS (REPR 25 NON VTG PFD)" = 우선주 GDS.
            따라서 비교 대상은 005930 이 아니라 삼성전자우(005935).
  SKHY      SK하이닉스 ADR. 나스닥 글로벌 셀렉트, 2026-07-10 상장.
            1 ADR = 보통주 1/10주 -> common_shares_per_unit = 0.1
            (이전 버전의 0.5 는 틀린 값이었음)
  HXSCL     구 비스폰서 OTC DR. SKHY 상장 후에도 존재하나 유동성이 얕아 제외.
  DRAM      Roundhill Memory ETF. 2026-04-02 상장, Cboe BZX.
            MU/삼성전자/SK하이닉스가 약 75% 비중.
  xyz:*     Hyperliquid HIP-3 주식 무기한선물. trade.xyz 가 운영하는 별도 dex.
            SMSN / SKHX / SKHY / KR200 등. API 호출 시 dex="xyz" 필요.
            KR200(코스피200 지수 perp)이 있어서 야간 코스피 선물 공백을 메움.

verified=False 로 남은 항목은 2차 자료(가이드 사이트)에서만 확인된 것으로,
아래 명령으로 최종 확인하십시오.

    python -m tools.validate_tickers
    python -m tools.discover_hyperliquid        # dex 목록 + 심볼 전체
================================================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

# ──────────────────────────────────────────────────────────────────────────────
# 전역 설정
# ──────────────────────────────────────────────────────────────────────────────

#: 시세 캐시. 20초였을 때는 섹션 버튼을 누를 때마다(20초가 지났으면)
#: 시세 수십 개를 다시 받느라 화면 전환이 매번 몇 초씩 걸렸습니다.
#: 야간 대체시세는 1분 단위로 봐도 충분합니다.
AUTO_REFRESH_SEC = 60
AUTO_REFRESH_DEFAULT = False
CACHE_TTL_SEC = 60

#: 기본 테마. "dark"(나이트) 또는 "light"(데이).
DEFAULT_THEME: Literal["dark", "light"] = "dark"

#: 등락 색상 관례. "kr" = 상승 적색, "us" = 상승 녹색.
COLOR_CONVENTION: Literal["kr", "us"] = "kr"

#: 원화 환산 환율. None 이면 실시간 USD/KRW(KRW=X) 사용.
FX_OVERRIDE: float | None = None

#: Hyperliquid HIP-3 dex 이름. 주식 무기한선물은 trade.xyz 가 운영합니다.
HIP3_DEX = "xyz"

#: 분석 자료(스킬 산출물)를 넣어둘 폴더
ANALYSIS_DIR = "analysis"

#: 증시 브리핑 파일 폴더. 파일명이 날짜(YYYY-MM-DD.md|html)입니다 —
#: briefing_store 가 파일명에서 날짜를 읽으므로 meta 파일이 없습니다.
BRIEFING_DIR = "briefings"


# ──────────────────────────────────────────────────────────────────────────────
# 변화 감지 (SEC EDGAR + 뉴스)
# ──────────────────────────────────────────────────────────────────────────────

#: SEC 가 요구하는 User-Agent. **연락처를 넣으십시오.**
#: SEC 는 키를 요구하지 않는 대신 "앱 이름 + 연락처" 형식의 User-Agent 를 요구하고,
#: 없으면 403 으로 거부합니다. 아래 your-email 부분을 본인 주소로 바꾸십시오.
#: SEC 가 요구하는 연락처. 없으면 403 으로 거부합니다.
#: 환경변수(또는 Streamlit Secrets)에 두면 공개 리포지터리에 이메일을 넣지
#: 않아도 됩니다 — Streamlit 의 루트 레벨 시크릿은 환경변수로도 노출됩니다.
EDGAR_USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "stock-dashboard/1.0 (personal research; your-email@example.com)",
).strip()

#: 티커 → CIK 직접 지정. 자동 매핑이 실패할 때만 씁니다.
#: 매핑은 https://www.sec.gov/files/company_tickers.json 에서 확인할 수 있습니다.
EDGAR_CIK_OVERRIDES: dict[str, int] = {}

#: 종목당 가져올 공시 건수
EDGAR_FILING_LIMIT = 12

#: EDGAR 응답 캐시 시간(초). 공시는 실시간 갱신되지만 하루에 몇 건이라 길게 둡니다.
EDGAR_CACHE_TTL_SEC = 1800

#: 티커→CIK 매핑 캐시 시간(초). 거의 안 바뀌므로 하루.
EDGAR_MAP_CACHE_TTL_SEC = 86_400

#: 뉴스를 붙일 종목 수 상한. 공시·급등락 신호가 잡힌 종목에만 붙습니다.
NEWS_MAX_TICKERS = 4

#: 종목당 헤드라인 개수
NEWS_PER_TICKER = 3

#: 뉴스 캐시 시간(초)
NEWS_CACHE_TTL_SEC = 900

#: 변화 감지 임계값
SIGNAL_MOVE_PCT = 5.0          # 하루 등락률 절댓값
SIGNAL_DRAWDOWN_PCT = 25.0     # 52주 고점 대비 낙폭
SIGNAL_EXTREME_PCT = 3.0       # 52주 고/저점 근접
SIGNAL_EARNINGS_DAYS = 14      # 실적 발표 임박
SIGNAL_STALE_DAYS = 90         # 분석 노후화


# ──────────────────────────────────────────────────────────────────────────────
# DART (한국 공시) + 반도체 사이클 레이어 2
# ──────────────────────────────────────────────────────────────────────────────

#: DART 인증키는 **환경변수 DART_API_KEY 로만** 받습니다.
#: 여기에 적어 두면 압축 파일이나 저장소에 섞여 나갑니다.
#:   export DART_API_KEY="40자리키"      (macOS/Linux)
#:   setx DART_API_KEY "40자리키"        (Windows, 새 터미널부터 적용)
#: 발급: https://opendart.fss.or.kr → 인증키 신청/관리 → 오픈API 이용현황

#: 종목코드 → DART 고유번호 직접 지정. 자동 매핑이 실패할 때만.
DART_CORP_CODE_OVERRIDES: dict[str, str] = {}

#: 공시 조회 기간(일)과 건수
DART_DISCLOSURE_DAYS = 180
DART_DISCLOSURE_LIMIT = 15
#: '내 종목만' 공시 — 종목마다 이 기간 · 이 건수까지 (유형을 가리지 않음)
MY_FILINGS_DAYS = 90
MY_FILINGS_LIMIT = 30

#: 캐시 — 공시 30분, 고유번호 매핑 24시간, 재무제표 12시간(분기마다 바뀜)
DART_CACHE_TTL_SEC = 1800
DART_MAP_CACHE_TTL_SEC = 86_400
DART_FINANCIALS_CACHE_TTL_SEC = 43_200

#: 재고 지표를 계산할 국내 종목코드 (DART 경로). 지표체계 v2 레이어 2 대상.
CYCLE_STOCK_CODES: tuple[str, ...] = ("005930", "000660")

#: 재고 지표를 계산할 미국 티커 (EDGAR XBRL 경로, 키 불필요).
#: 메모리 3사를 같은 화면에서 비교하려면 MU 가 필요합니다.
CYCLE_US_TICKERS: tuple[str, ...] = ("MU",)

#: XBRL 에서 수집할 분기 수
CYCLE_XBRL_QUARTERS = 6

#: 수집할 분기 수 (뒤로 몇 분기까지). 밴드를 만들려면 최소 3개는 필요합니다.
CYCLE_QUARTERS_BACK = 5

#: 연결(CFS)/별도(OFS). 반도체는 해외 생산법인이 커서 연결이 맞습니다.
CYCLE_FS_DIV = "CFS"

#: DIO 가 이 분기 수 이상 연속 상승하면 신호 (체크리스트 항목)
SIGNAL_DIO_RISING_QUARTERS = 2


# ──────────────────────────────────────────────────────────────────────────────
# 버핏식 스크리닝 — EDGAR companyfacts (인증키 불필요)
# ──────────────────────────────────────────────────────────────────────────────
#
# 기업당 1회 요청으로 10년치를 받습니다. 30~50개면 몇 초면 끝납니다.
# 종목을 더하고 싶으면 SCREEN_CANDIDATES 에 티커만 넣으십시오 — 관심종목은
# 자동으로 포함되므로 중복해서 적지 않아도 됩니다.

SCREEN_YEARS = 10              # 몇 개 회계연도를 볼지
SCREEN_CACHE_TTL_SEC = 86_400  # 24시간 — 연간 재무는 1년에 한 번 바뀝니다
#: 재무 심사는 **30일 묵은 값까지** 바로 보여주고 뒤에서 새로 받습니다.
#: 사업보고서는 1년에 한 번 바뀌는데, 받는 데는 종목당 4회 × 50종목 =
#: 200회 요청(12초 안팎)이 듭니다. 2026-11-12 실측 "국내 재무 심사 12.7초".
SCREEN_STALE_SEC = 30 * 86_400

#: 차트 조건을 다시 계산하는 간격 — 장중 5분, 장이 닫히면 1시간.
CHART_TTL_OPEN_SEC = 300
CHART_TTL_CLOSED_SEC = 3_600
#: 묵은 시세를 보여주기 전에 새 시세를 기다려 주는 시간(초). 0 이면 안 기다림.
QUOTE_WAIT_FRESH_SEC = 3.0
#: 아침 수집기가 올려 두는 스냅샷 (저장소의 data 브랜치). 서버가 막 깨어나
#: 값이 하나도 없을 때 이걸 읽어 채웁니다. 환경변수 SEED_URL 로 바꿀 수
#: 있고, 빈 값이면 읽지 않습니다.
SEED_URL = os.environ.get(
    "SEED_URL",
    "https://raw.githubusercontent.com/MaCho-guy/REALMAN-INVEST/data/seed.pkl.gz")

#: 리포트 AI 요약 — 수집기가 Claude API 로 만들어 data 브랜치에 올리는 파일.
SUMMARY_URL = os.environ.get(
    "SUMMARY_URL",
    "https://raw.githubusercontent.com/MaCho-guy/REALMAN-INVEST/data/summaries.json")
#: 요약에 쓸 모델. 가장 싼 것으로 시작합니다 — 품질이 아쉬우면 여기만 바꿉니다.
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "claude-haiku-5-5")
#: 묶음(반도체 산업 · 삼성전자 · SK하이닉스)마다 최근 몇 건까지 요약 대상으로 보나.
SUMMARY_PER_LIST = 10
#: 수집기가 한 번 돌 때 새로 요약하는 최대 건수 (비용 상한).
SUMMARY_MAX_NEW = 12
#: 리포트마다 앞의 몇 쪽까지 읽히나. 2026-11-12 실제 실행에서 쪽당 약 2,500
#: 토큰이었습니다 (30쪽 ≈ 7.5만 토큰). 늘리면 긴 전망 리포트의 뒤쪽까지
#: 읽지만 비용이 쪽수만큼 늡니다.
SUMMARY_MAX_PAGES = 30
#: 받아 오는 PDF 크기 상한. 넘으면 받다가 그만둡니다 (보내는 것은 앞쪽만).
SUMMARY_MAX_DOWNLOAD = 60 * 1024 * 1024
#: 한 번 돌 때 쓰는 입력 토큰 상한 — 넘으면 남은 리포트는 다음 번에.
SUMMARY_MAX_INPUT_TOKENS = 600_000

#: 관심종목 외에 함께 돌릴 후보. 미국 종목(SEC 신고 기업)만 됩니다 —
#: 삼성전자·SK하이닉스는 SEC 에 신고하지 않아 이 스크리너로는 안 됩니다.
#: 아래 목록은 '버핏식 기준을 적용해볼 만한' 성격의 종목을 업종별로 넓게
#: 깔아둔 것이고, 추천 목록이 아닙니다.
SCREEN_CANDIDATES: tuple[str, ...] = (
    # 소비재 — 버핏이 전통적으로 선호한 영역
    "KO", "PEP", "PG", "CL", "KMB", "MDLZ", "HSY", "MKC", "CHD", "CLX",
    # 소매·외식
    "COST", "WMT", "TGT", "HD", "LOW", "MCD", "SBUX", "YUM", "DPZ", "TJX",
    # 금융 — 버크셔 보유 이력이 있는 영역
    "AXP", "BAC", "V", "MA", "USB", "MCO", "SPGI", "CB", "TRV", "PGR",
    # 헬스케어
    "JNJ", "ABT", "MDT", "SYK", "BDX", "ZTS", "EW", "ISRG",
    # 산업·소재
    "MMM", "HON", "ITW", "EMR", "DOV", "ROP", "GWW", "FAST", "SHW", "ECL",
    # 기술 — AAPL 은 버크셔 최대 보유였던 이력이 있습니다
    "MSFT", "AAPL", "ADBE", "ORCL", "TXN", "ADP", "INTU", "CSCO", "AMAT",
    # 통신·미디어
    "CMCSA", "VZ", "T", "DIS",
    # 에너지 — 버크셔가 최근 비중을 늘린 영역
    "CVX", "XOM", "OXY",
    # 버크셔 본체 (기준의 기준점으로 같이 봅니다)
    "BRK-B",
)

#: 스크리닝 기준선. buffett.Thresholds 의 기본값을 덮어씁니다.
#: 숫자의 출처는 각 기준의 provenance 로 화면에 표시됩니다 —
#: '버핏 원문' / '인용 관행' / '제 기준' 중 뒤 두 개는 바꿔도 됩니다.
SCREEN_THRESHOLDS: dict[str, float] = {
    "roe_min": 15.0,                      # % — 인용 관행
    "roe_years_required": 8,              # 10년 중 — 제 기준
    "owner_earnings_years_required": 8,   # 제 기준
    "capex_heavy_years_allowed": 3,       # 제 기준
    "debt_to_equity_max": 0.5,            # 인용 관행
    "debt_years_max": 4.0,                # 인용 관행
    "margin_stdev_max": 5.0,              # %p — 제 기준
    "bad_years_allowed": 1,               # 제 기준
    "earnings_drop_pct": 30.0,            # % — 제 기준
    "min_years": 5,                       # 제 기준
}


#: 스크리닝에서 제외. ETF·펀드는 사업 재무제표가 없어 ROE·마진이 의미가 없습니다
#: (SEC 에 신고는 하지만 us-gaap 손익 계정을 그렇게 쓰지 않습니다).
SCREEN_EXCLUDE: frozenset[str] = frozenset({
    "QQQ", "SCHD", "DRAM", "EWY", "SOXX", "SMH", "EWJ", "SPY", "VOO",
})


#: 국내 스크리닝 대상 (종목코드). 관심종목의 국내 종목은 자동 포함됩니다.
#: KOSPI 대형주를 업종별로 깔아둔 것이고 **추천 목록이 아닙니다.**
SCREEN_KR_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("005930", "삼성전자"),
    ("000660", "SK하이닉스"),
    ("005380", "현대차"),
    ("000270", "기아"),
    ("005490", "POSCO홀딩스"),
    ("051910", "LG화학"),
    ("006400", "삼성SDI"),
    ("035420", "NAVER"),
    ("035720", "카카오"),
    ("207940", "삼성바이오로직스"),
    ("068270", "셀트리온"),
    ("105560", "KB금융"),
    ("055550", "신한지주"),
    ("086790", "하나금융지주"),
    ("015760", "한국전력"),
    ("017670", "SK텔레콤"),
    ("030200", "KT"),
    ("033780", "KT&G"),
    ("097950", "CJ제일제당"),
    ("271560", "오리온"),
    ("282330", "BGF리테일"),
    ("161390", "한국타이어앤테크놀로지"),
    ("009150", "삼성전기"),
    ("012330", "현대모비스"),
    ("010140", "삼성중공업"),
    ("034730", "SK"),
    ("003550", "LG"),
    ("018260", "삼성에스디에스"),
    ("032830", "삼성생명"),
    ("316140", "우리금융지주"),
)


#: 코스닥 후보. **코스피와 성격이 다릅니다** — 시가총액이 작고 변동성이
#: 훨씬 크며, 적자 기업이 많아 PER 이 아예 안 나오는 경우가 흔합니다.
#: 변동성 스크리너가 의미를 갖는 건 사실 이쪽입니다.
#:
#: 종목코드는 **제 기억에서 적은 것이라 검증되지 않았습니다.** 6자리
#: 숫자가 하나만 틀려도 엉뚱한 회사의 재무를 가져오는데, 화면에는
#: 아무 이상이 없어 보입니다. 그래서 진단 패널에 '국내 종목코드 대조'
#: 를 넣었습니다 — DART 의 corpCode.xml 에서 실제 회사명을 받아
#: 아래 이름과 맞는지 기계가 확인합니다. 배포 후 한 번 돌리십시오.
SCREEN_KQ_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("247540", "에코프로비엠"),
    ("086520", "에코프로"),
    ("196170", "알테오젠"),
    ("028300", "HLB"),
    ("141080", "리가켐바이오"),
    ("068760", "셀트리온제약"),
    ("277810", "레인보우로보틱스"),
    ("348370", "엔켐"),
    ("257720", "실리콘투"),
    ("058470", "리노공업"),
    ("036930", "주성엔지니어링"),
    ("005290", "동진쎄미켐"),
    ("240810", "원익IPS"),
    ("140860", "파크시스템스"),
    ("403870", "HPSP"),
    ("039030", "이오테크닉스"),
    ("263750", "펄어비스"),
    ("293490", "카카오게임즈"),
    ("041510", "에스엠"),
    ("035900", "JYP Ent."),
)

#: 국내 사업보고서를 몇 개 받을지. 보고서당 3년이므로 4개면 약 12년입니다.
SCREEN_KR_REPORTS = 4


def screen_kr_candidates(include_kosdaq: bool = True) -> list[tuple[str, str]]:
    """국내 스크리닝 대상 — 관심종목 국내 종목 + 코스피 후보 + 코스닥 후보.

    코스닥을 섞는 게 맞는가: 변동성 스크리너 입장에서는 맞습니다. 코스피
    대형주는 1년 변동성이 대체로 25~35% 대라 '수축' 이 잘 안 보입니다.
    코스닥은 50% 를 넘는 종목이 흔해서 수축이 일어나면 눈에 띕니다.
    대신 **전통 밸류 스크리너에서는 거의 안 걸립니다** — PBR 이 높고
    적자가 많아 PER 이 안 나옵니다. 그건 고장이 아니라 사실입니다.
    """
    seen: dict[str, str] = {}
    for inst in SECTION_WATCHLIST.instruments:
        if inst.source == "naver" and inst.symbol.isdigit():
            seen[inst.symbol] = inst.name
    for code, name in SCREEN_KR_CANDIDATES:
        seen.setdefault(code, name)
    if include_kosdaq:
        for code, name in SCREEN_KQ_CANDIDATES:
            seen.setdefault(code, name)
    return list(seen.items())


def kosdaq_codes() -> frozenset[str]:
    """코스닥 후보 코드. 화면에서 시장을 표시할 때 씁니다."""
    return frozenset(c for c, _n in SCREEN_KQ_CANDIDATES)


def screen_tickers() -> list[str]:
    """스크리닝 대상 — 관심종목(미국 개별 종목만) + 후보. 중복 제거.

    제외되는 것: ETF(재무제표 없음), 한국 종목(SEC 미신고), 선물·지수.
    """
    seen: dict[str, None] = {}
    for inst in SECTION_WATCHLIST.instruments:
        symbol = inst.symbol.upper()
        if inst.source != "yahoo" or "." in symbol or symbol in SCREEN_EXCLUDE:
            continue
        seen[symbol] = None
    for ticker in SCREEN_CANDIDATES:
        if ticker.upper() not in SCREEN_EXCLUDE:
            seen[ticker.upper()] = None
    return list(seen)


def screen_thresholds():
    """config 값으로 채운 Thresholds."""
    from buffett import Thresholds

    fields = {}
    for key, value in SCREEN_THRESHOLDS.items():
        fields[key] = int(value) if key.endswith(("_required", "_allowed",
                                                  "_years")) else value
    return Thresholds(**fields)


# ──────────────────────────────────────────────────────────────────────────────
# 매크로 지표 — FRED (인증키 불필요)
# ──────────────────────────────────────────────────────────────────────────────
#
# 왜 가격 카드와 따로 두는가:
#   · 시장가격이 있는 것(10년물 금리, 환율, VIX)은 야후에서 **실시간**으로 옵니다
#     → SECTION_MACRO 의 카드
#   · 통계(CPI, 고용, 산업생산)는 가격이 없고 **발표 지연**이 있습니다
#     → 이 목록, FRED CSV 경로
# 둘을 섞으면 "어제 CPI" 같은 착각이 생깁니다. 그래서 화면에서도 분리하고
# 통계에는 관측일과 지연일수를 항상 함께 표시합니다.

MACRO_CACHE_TTL_SEC = 21_600   # 6시간 — 월간 통계는 하루에 여러 번 봐도 같습니다
MACRO_SERIES_YEARS = 4         # 받아올 기간 (밴드·전년대비에 충분)
MACRO_NEWS_LIMIT = 3           # 신호가 난 지표당 헤드라인 수
MACRO_MAX_NEWS_TARGETS = 3     # 뉴스를 붙일 지표 수 상한 (받은편지함 보호)
MACRO_STALE_MULTIPLIER = 2.5   # 통상 발표주기의 N 배를 넘으면 '지연' 경고


@dataclass(frozen=True)
class MacroSeries:
    """FRED 계열 하나 + 그걸 보는 이유 + 신호 임계값."""

    key: str
    name: str
    series_id: str
    group: str                  # rates / inflation / labor / semi
    unit: str = ""              # 표시 단위 ("%", "천명", "건")
    mode: str = "level"         # level(레벨) / yoy(전년대비 %) / diff(직전 대비 변화)
    decimals: int = 2

    #: 이 지표를 왜 보는가 — 수빈님 보유 종목과의 연결. 화면에 그대로 띄웁니다.
    why: str = ""

    #: 발표 주기(일). 지연 경고 기준.
    period_days: int = 30

    #: FRED 계열 ID 를 이 세션에서 실제로 확인했는가.
    #: False 면 `python -m tools.diagnose --fred` 로 검증해야 합니다.
    verified: bool = False

    #: 신호가 났을 때 검색할 뉴스 질의 (한국어). 비우면 뉴스를 붙이지 않습니다.
    news_query: str = ""

    #: 같은 것을 **지금 시세**로 볼 수 있는 야후 심볼 (있을 때만). FRED 의
    #: 일별 금리는 다음 영업일에야 올라오므로, 화면에는 이 시세를 함께
    #: 적습니다. 임계값 판정은 그대로 FRED 값으로 합니다.
    live_symbol: str = ""
    #: 이 통계가 속한 FRED 발표 묶음 번호 (calendar_events.FRED_RELEASES).
    #: 있으면 '다음 발표 11/13' 을 적습니다.
    release_id: int | None = None

    # ── 임계값 — 전부 None 이면 신호를 내지 않고 표시만 합니다 ──────────────
    #: 표시값(mode 기준)이 이 값을 넘으면 신호
    level_above: float | None = None
    #: 표시값이 이 값을 밑돌면 신호
    level_below: float | None = None
    #: change_periods 개 관측치 전 대비 절대 변화가 이 값을 넘으면 신호
    change_abs: float | None = None
    change_periods: int = 1
    #: 레벨의 부호가 바뀌면 신호 (2s10s 역전/정상화)
    sign_flip: bool = False
    #: 전년대비 증감률의 부호가 바뀌면 신호 (사이클 전환)
    yoy_flip: bool = False
    #: 최근 mean_periods 평균 대비 이 % 이상 벗어나면 신호
    pct_vs_mean: float | None = None
    mean_periods: int = 4


#: 임계값은 수빈님 판단으로 바꾸십시오 — 아래 숫자는 제 판단이고 근거는 why 에 있습니다.
MACRO_SERIES: tuple[MacroSeries, ...] = (
    # ── 금리·신용 — O(리츠)와 QQQ 밸류에이션에 직결 ─────────────────────────
    MacroSeries(
        "ust10", "미국 10년 국채 금리", "DGS10", "rates", "%",
        mode="level", decimals=2, period_days=1, verified=True,
        live_symbol="^TNX",
        why="할인율의 기준입니다. O(리츠)는 금리와 역방향으로 움직이고, "
            "QQQ 같은 성장주 묶음은 듀레이션이 길어 금리 상승에 더 민감합니다.",
        change_abs=0.50, change_periods=20,
        news_query="미국 10년물 국채 금리",
    ),
    MacroSeries(
        "ust2", "미국 2년 국채 금리", "DGS2", "rates", "%",
        mode="level", decimals=2, period_days=1, verified=True,
        why="연준 정책 기대를 가장 직접 반영합니다. 10년물보다 먼저 움직입니다.",
        change_abs=0.50, change_periods=20,
    ),
    MacroSeries(
        "curve", "10년-2년 스프레드", "T10Y2Y", "rates", "%p",
        mode="level", decimals=2, period_days=1, verified=True,
        why="마이너스는 장단기 금리 역전입니다. 역전 진입도 신호지만 "
            "**역전에서 플러스로 되돌아올 때**가 역사적으로 더 중요한 국면이었습니다. "
            "부호가 바뀔 때만 알립니다.",
        sign_flip=True,
        news_query="장단기 금리 역전",
    ),
    # ── 크레딧 — 설비투자가 큰 반도체는 자금 조달 여건에 직접 영향받습니다 ──
    MacroSeries(
        "hy_spread", "하이일드 스프레드 (HY OAS)", "BAMLH0A0HYM2", "rates", "%p",
        mode="level", decimals=2, period_days=1, verified=True,
        why="투기등급 회사채가 국채 대비 얹어주는 금리입니다. 신용 투자자가 "
            "부도 위험을 어떻게 보는지 매일 보여주고, 주가보다 먼저 벌어지는 "
            "경우가 있습니다. MU 처럼 설비투자가 큰 기업은 자금 조달 비용이 "
            "투자 계획에 직접 영향을 받습니다. 확대는 위험 회피, 축소는 위험 "
            "선호로 **해석할 여지**가 있습니다.<br>"
            "<b>임계값 근거</b>: 5.0%p 는 불황기에 도달하는 수준이라 "
            "**조기 경보가 아니라 위기 표시**입니다. 조기 신호는 "
            "<b>자기 20일 평균 대비 +20%</b> 쪽이 담당합니다 — 절대값 "
            "기준(예: +1.0%p)은 스프레드가 3%p 일 때와 8%p 일 때 의미가 "
            "달라져서, 자기 수준에 대한 상대 변화로 둡니다.",
        level_above=5.0,
        pct_vs_mean=20.0, mean_periods=20,
        news_query="하이일드 스프레드 신용 위험",
    ),
    MacroSeries(
        "ig_oas", "투자등급 스프레드 (IG OAS)", "BAMLC0A0CM", "rates", "%p",
        mode="level", decimals=2, period_days=1, verified=True,
        why="투자등급 회사채의 국채 대비 스프레드입니다. 하이일드와 같이 보면 "
            "위험이 **등급 전반으로 번지는지** 투기등급에 국한되는지 구분됩니다. "
            "둘이 같이 벌어질 때가 더 넓은 신용 긴축입니다.<br>"
            "<b>임계값 근거</b>: 하이일드와 같은 방식(자기 20일 평균 대비 "
            "+20%)입니다. 레벨 기준 2.0%p 는 투자등급으로서는 상당히 "
            "벌어진 수준입니다.",
        level_above=2.0,
        pct_vs_mean=20.0, mean_periods=20,
    ),

    # ── 인플레이션 — 금리 경로를 결정합니다 ────────────────────────────────
    MacroSeries(
        "cpi", "CPI (전년대비)", "CPIAUCSL", "inflation", "%",
        mode="yoy", decimals=1, period_days=30, verified=True,
        release_id=10,
        why="헤드라인 물가입니다. 에너지·식품이 섞여 변동이 큽니다.",
        change_abs=0.3,
        news_query="미국 소비자물가지수 CPI",
    ),
    MacroSeries(
        "core_cpi", "코어 CPI (전년대비)", "CPILFESL", "inflation", "%",
        mode="yoy", decimals=1, period_days=30, verified=True,
        release_id=10,
        why="에너지·식품을 뺀 추세 물가입니다. 헤드라인보다 금리 경로에 더 영향을 줍니다.",
        change_abs=0.3,
    ),
    MacroSeries(
        "core_pce", "코어 PCE (전년대비)", "PCEPILFE", "inflation", "%",
        mode="yoy", decimals=1, period_days=30, verified=True,
        release_id=54,
        why="**연준이 공식 목표(2%)로 삼는 지표**입니다. CPI 보다 늦게 나오지만 "
            "정책 판단에는 이쪽이 쓰입니다.",
        level_above=2.5, change_abs=0.2,
        news_query="코어 PCE 물가",
    ),
    MacroSeries(
        "breakeven", "5년후 5년 기대인플레", "T5YIFR", "inflation", "%",
        mode="level", decimals=2, period_days=1, verified=True,
        why="시장이 보는 장기 기대인플레입니다. 2% 근처를 벗어나면 "
            "연준의 신뢰도 문제로 번질 수 있어 따로 봅니다.",
        level_above=2.5, level_below=1.8,
    ),

    # ── 고용·경기 ─────────────────────────────────────────────────────────
    MacroSeries(
        "claims", "주간 신규 실업수당 청구", "ICSA", "labor", "건",
        mode="level", decimals=0, period_days=7, verified=True,
        why="**주간으로 나오는 가장 빠른 경기 지표**입니다. 월간 고용지표보다 "
            "3~6주 앞섭니다. 4주 평균 대비 급증이 신호입니다.",
        pct_vs_mean=15.0, mean_periods=4,
        news_query="미국 신규 실업수당 청구건수",
    ),
    MacroSeries(
        "unrate", "실업률", "UNRATE", "labor", "%",
        mode="level", decimals=1, period_days=30, verified=True,
        release_id=50,
        why="저점 대비 0.3%p 이상 상승은 과거 침체 국면의 공통 패턴이었습니다 "
            "(Sahm rule 의 근사). 3개월 변화로 봅니다.",
        change_abs=0.3, change_periods=3,
        news_query="미국 실업률 고용보고서",
    ),
    MacroSeries(
        "payrolls", "비농업 고용 (전월 대비)", "PAYEMS", "labor", "천명",
        mode="diff", decimals=0, period_days=30, verified=True,
        release_id=50,
        why="월간 고용 증감입니다. 마이너스 전환은 명확한 경기 신호입니다.",
        level_below=0.0,
        news_query="미국 비농업 고용 지표",
    ),

    # ── 반도체 — 지표체계 v2 의 레이어 1·4 대리 지표 ───────────────────────
    # 공시로는 계산할 수 없다고 적어둔 층입니다. 완전한 대체는 아니지만
    # 키 없이 얻을 수 있는 유일한 공적 계열입니다.
    MacroSeries(
        "semi_ip", "반도체 산업생산 (전년대비)", "IPG3344S", "semi", "%",
        mode="yoy", decimals=1, period_days=30, verified=True,
        why="미국 반도체·전자부품 **실물 생산량**입니다 (NAICS 3344). "
            "레이어 4(수요)의 대리 지표 — 전년대비 증감률의 부호가 바뀌는 지점이 "
            "생산 사이클 전환입니다. 지수 레벨은 기준연도가 바뀌므로 쓰지 않습니다.",
        yoy_flip=True,
        news_query="반도체 생산 사이클",
    ),
    MacroSeries(
        "semi_ppi", "반도체 생산자물가 (전년대비)", "PCU334413334413", "semi", "%",
        mode="yoy", decimals=1, period_days=30, verified=True,
        release_id=46,
        why="반도체·관련소자 제조업 **출하 가격**입니다. "
            "레이어 1(가격)의 대리 지표 — DRAM 현물가의 대체는 못 되지만, "
            "키 없이 얻을 수 있는 유일한 공적 가격 계열입니다. "
            "세부 품목 계열은 결측이 많아 광의 계열을 씁니다.",
        yoy_flip=True,
        news_query="메모리 반도체 가격",
    ),
)

MACRO_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("rates", "금리 · 신용", "할인율과 신용 여건 — O · SCHD · QQQ 에 직결"),
    ("inflation", "인플레이션", "금리 경로를 결정하는 층"),
    ("labor", "고용 · 경기", "침체 진입 여부 — 주간 지표가 가장 빠릅니다"),
    ("semi", "반도체 사이클", "지표체계 레이어 1·4 대리 — 공시로는 못 구하는 층"),
)


def macro_series(group: str | None = None) -> list[MacroSeries]:
    """매크로 계열 목록. group 을 주면 그 그룹만."""
    if group is None:
        return list(MACRO_SERIES)
    return [s for s in MACRO_SERIES if s.group == group]


def macro_series_ids() -> list[str]:
    return [s.series_id for s in MACRO_SERIES]


def macro_series_by_key(key: str) -> MacroSeries | None:
    for s in MACRO_SERIES:
        if s.key == key:
            return s
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Instrument:
    """대시보드에 표시할 단일 종목/지표."""

    name: str
    symbol: str
    source: Literal["yahoo", "hyperliquid", "naver", "manual"]
    exchange: str = ""
    currency: str = "USD"
    verified: bool = False
    note: str = ""

    #: 1순위 심볼이 실패하면 순서대로 시도할 대체 심볼.
    #: 야후는 같은 종목을 거래소별로 다르게 표기해서(SMSN.IL / SMSN.L) 필요합니다.
    alt_symbols: tuple[str, ...] = ()

    #: 괴리율 계산용. 이 종목 1단위 = 국내 본주 몇 주인가.
    #:   삼성전자 런던 GDR  1 GDR = 25주   -> 25.0
    #:   SK하이닉스 ADR     1 ADR = 0.1주  -> 0.1
    common_shares_per_unit: float | None = None

    #: 괴리율 비교 대상 국내 본주 코드(6자리)
    local_peer: str | None = None

    decimals: int | None = None

    #: 표시 전 가격에 곱할 배수 (호가 단위 보정)
    scale: float = 1.0

    #: 가격 뒤 단위 기호 ("%" 등)
    suffix: str = ""

    #: 카드 제목을 누르면 열릴 주소. 비우면 source 기준으로 자동 생성.
    link: str = ""

    #: 밸류에이션 표에서 쓸 야후 심볼. 비우면 symbol 사용.
    #: 한국 종목은 naver 코드(005930)와 야후 심볼(005930.KS)이 달라서 필요합니다.
    fundamental_symbol: str = ""

    #: 공시 분석(스킬 산출물) 폴더명. 비우면 분석 패널을 띄우지 않습니다.
    analysis_key: str = ""

    def resolved_link(self) -> str:
        """카드 제목에 걸 주소를 돌려줍니다."""
        if self.link:
            return self.link
        if self.source == "yahoo":
            return f"https://finance.yahoo.com/quote/{self.symbol}"
        if self.source == "naver":
            return f"https://finance.naver.com/item/main.naver?code={self.symbol}"
        if self.source == "hyperliquid":
            coin = self.symbol.split(":", 1)[-1]
            return f"https://app.hyperliquid.xyz/trade/{coin}"
        return ""

    def fundamentals_ticker(self) -> str:
        return self.fundamental_symbol or self.symbol


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    short: str = ""            # 탭 라벨 (짧게)
    subtitle: str = ""
    instruments: tuple[Instrument, ...] = field(default_factory=tuple)
    columns: int = 3
    footnote: str = ""

    def tab_label(self) -> str:
        return self.short or self.title


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 1 — DEX 무기한선물 (Hyperliquid HIP-3 / trade.xyz)
# ──────────────────────────────────────────────────────────────────────────────
# 주의: 이 마켓은 Hyperliquid 가 아니라 trade.xyz 가 HIP-3 프레임워크로
#       배포·운영합니다. 오라클 가격을 쓰므로 기초자산 거래소의 비정상 체결이
#       그대로 전달될 수 있습니다 (footnote 참조).

SECTION_DEX = Section(
    key="dex",
    title="DEX 무기한선물",
    short="DEX 선물",
    subtitle="Hyperliquid HIP-3 · trade.xyz 운영 · 24시간 거래",
    columns=3,
    instruments=(
        Instrument("삼성전자 PERP", "xyz:SMSN", "hyperliquid", "trade.xyz", "USD",
                   verified=False, local_peer="005930",
                   note="오라클이 본주 원화가를 USD 환산한 값"),
        Instrument("SK하이닉스 PERP", "xyz:SKHX", "hyperliquid", "trade.xyz", "USD",
                   verified=False, local_peer="000660",
                   note="보통주 1주의 USD 가치를 추종"),
        Instrument("SK하이닉스 ADS PERP", "xyz:SKHY", "hyperliquid", "trade.xyz", "USD",
                   verified=False,
                   note="ADR(SKHY) 기준 — 본주 perp(SKHX)와 다른 상품"),
        Instrument("코스피200 PERP", "xyz:KR200", "hyperliquid", "trade.xyz", "USD",
                   verified=False,
                   note="야간 코스피200 방향성 대체 지표"),
        Instrument("나스닥100 PERP", "xyz:XYZ100", "hyperliquid", "trade.xyz", "USD",
                   verified=False),
        Instrument("닛케이225 PERP", "xyz:JP225", "hyperliquid", "trade.xyz", "USD",
                   verified=False),
        Instrument("DRAM 가격지수 PERP", "xyz:DRAM", "hyperliquid", "trade.xyz", "USD",
                   verified=False,
                   note="ETF 가 아니라 글로벌 DRAM 계약가격 지수"),
    ),
    footnote=(
        "펀딩률은 시간당 지급분을 8시간으로 환산한 값입니다. 양수면 롱이 숏에게 지급합니다. "
        "이 마켓은 trade.xyz 가 HIP-3 로 배포한 것이며 Hyperliquid 본체가 운영하지 않습니다. "
        "오라클이 기초자산 거래소 가격을 받아오므로, 2026년 7월 28일 한국 NXT 에서 "
        "SK하이닉스 1주가 비정상 체결되자 SKHX 가 17.9% 급락하고 960개 계정 약 5,740만 달러가 "
        "청산된 사례가 있습니다. 오라클 기반 상품의 구조적 위험입니다."
    ),
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 2 — ADR · GDR 괴리율
# ──────────────────────────────────────────────────────────────────────────────

SECTION_ADR = Section(
    key="adr",
    title="ADR · GDR 괴리율",
    short="괴리율",
    subtitle="해외 상장 한국 종목의 국내 본주 대비 프리미엄",
    columns=3,
    instruments=(
        Instrument("SK하이닉스 ADR", "SKHY", "yahoo", "NASDAQ", "USD",
                   verified=True,
                   common_shares_per_unit=0.1, local_peer="000660",
                   decimals=2,
                   note="1 ADR = 보통주 1/10주 · 2026-07-10 나스닥 상장",
                   analysis_key="SKHY"),
        Instrument("삼성전자 GDR", "SMSN.IL", "yahoo", "London IOB", "USD",
                   verified=True, alt_symbols=("SMSN.L",),
                   common_shares_per_unit=25.0, local_peer="005930",
                   decimals=2,
                   note="1 GDR = 보통주 25주"),
        Instrument("삼성전자우 GDS", "SMSD.IL", "yahoo", "London IOB", "USD",
                   verified=False, alt_symbols=("SMSD.L",),
                   common_shares_per_unit=25.0, local_peer="005935",
                   decimals=2,
                   note="우선주 GDS · 비교 대상은 삼성전자우(005935)"),
    ),
    footnote=(
        "괴리율 = (해외가격 × 환율 ÷ 환산주수) ÷ 국내 본주가 − 1. "
        "국내 장 마감 중에는 본주가 종가로 고정되므로 이 수치는 실제 가격차가 아니라 "
        "마감 이후 해외에서 벌어진 움직임입니다. "
        "SK하이닉스 ADR 은 본주→ADR 전환이 발행주식수의 2.5% 로 제한되어 있어 "
        "차익거래로 괴리가 좁혀지기 어렵습니다 — 괴리율이 크다는 사실만으로 "
        "차익거래 기회라고 볼 수 없습니다."
    ),
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 3 — 국내 본주
# ──────────────────────────────────────────────────────────────────────────────

SECTION_LOCAL = Section(
    key="local",
    title="국내 본주",
    short="국내 본주",
    subtitle="괴리율 계산 기준 가격 (괴리율 탭에 합쳐졌습니다)",
    columns=4,
    instruments=(
        Instrument("삼성전자", "005930", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0, fundamental_symbol="005930.KS"),
        Instrument("삼성전자우", "005935", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0, fundamental_symbol="005935.KS"),
        Instrument("SK하이닉스", "000660", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0, fundamental_symbol="000660.KS"),
        Instrument("현대차", "005380", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0, fundamental_symbol="005380.KS"),
    ),
    footnote="네이버 금융 실시간 폴링 API 를 쓰고, 실패하면 야후(.KS/.KQ)로 폴백합니다.",
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 4 — 글로벌 선물
# ──────────────────────────────────────────────────────────────────────────────

SECTION_FUTURES = Section(
    key="futures",
    title="글로벌 선물",
    short="선물",
    subtitle="야간 시간대 방향성 참고",
    columns=3,
    instruments=(
        Instrument("나스닥 100 선물", "NQ=F", "yahoo", "CME", "USD", verified=True, decimals=2),
        Instrument("S&P 500 선물", "ES=F", "yahoo", "CME", "USD", verified=True, decimals=2),
        Instrument("다우 선물", "YM=F", "yahoo", "CME", "USD", verified=True, decimals=0),
        Instrument("러셀 2000 선물", "RTY=F", "yahoo", "CME", "USD", verified=True, decimals=1),
        Instrument("닛케이 225 선물", "NIY=F", "yahoo", "CME", "JPY",
                   verified=False, decimals=0, alt_symbols=("NKD=F",),
                   note="NIY=F 실패 시 NKD=F 로 재시도"),
    ),
    footnote="코스피200 야간선물은 야후에 없습니다. DEX 선물 탭의 KR200 PERP 를 대체 지표로 쓰십시오.",
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 5 — 매크로
# ──────────────────────────────────────────────────────────────────────────────

SECTION_MACRO = Section(
    key="macro",
    title="매크로",
    short="매크로",
    subtitle="금리 · 환율 · 원자재 · 변동성",
    columns=4,
    instruments=(
        # ^TNX 는 야후가 금리를 10배로 줍니다(4.21% -> 42.1). scale 로
        # 되돌려 놓았습니다. 전에는 이 주의사항을 note 로 넣어 **화면에
        # 그대로 노출**됐는데, note 는 사용자가 읽는 자리입니다.
        Instrument("미국 10년 국채 금리", "^TNX", "yahoo", "CBOE", "",
                   verified=True, decimals=3, suffix="%"),
        Instrument("미국 13주 T-bill", "^IRX", "yahoo", "CBOE", "",
                   verified=True, decimals=3, suffix="%"),
        Instrument("원/달러 환율", "KRW=X", "yahoo", "FX", "KRW",
                   verified=True, decimals=2),
        Instrument("달러 인덱스", "DX-Y.NYB", "yahoo", "ICE", "",
                   verified=True, decimals=2),
        Instrument("WTI 원유", "CL=F", "yahoo", "NYMEX", "USD",
                   verified=True, decimals=2),
        Instrument("금", "GC=F", "yahoo", "COMEX", "USD",
                   verified=True, decimals=2),
        Instrument("VIX", "^VIX", "yahoo", "CBOE", "",
                   verified=True, decimals=2),
    ),
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 6 — 미국 ETF 프록시
# ──────────────────────────────────────────────────────────────────────────────

SECTION_ETF_PROXY = Section(
    key="etf_proxy",
    title="미국 ETF 프록시",
    short="ETF",
    subtitle="한국 증시 · 반도체 업황 대리 지표",
    columns=3,
    instruments=(
        Instrument("DRAM (메모리 ETF)", "DRAM", "yahoo", "Cboe BZX", "USD",
                   verified=True, decimals=2,
                   note="Roundhill Memory ETF · MU·삼성전자·SK하이닉스가 약 75%",
                   analysis_key="DRAM"),
        Instrument("EWY (한국 ETF)", "EWY", "yahoo", "NYSE Arca", "USD",
                   verified=True, decimals=2),
        Instrument("SOXX (반도체 ETF)", "SOXX", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2),
        Instrument("SMH (반도체 ETF)", "SMH", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2),
        Instrument("EWJ (일본 ETF)", "EWJ", "yahoo", "NYSE Arca", "USD",
                   verified=True, decimals=2),
    ),
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 7 — 관심종목
# ──────────────────────────────────────────────────────────────────────────────
# 사용자 지정: MSFT, AAPL, MU, O, QQQ, SCHD, UNH, AMT, CRCL, GOOGL,
#              삼성전자, SK하이닉스, 삼성증권, SK스퀘어

SECTION_WATCHLIST = Section(
    key="watchlist",
    title="관심종목",
    short="관심종목",
    subtitle="클릭하면 야후·네이버 종목 페이지로 이동",
    columns=3,
    instruments=(
        Instrument("Microsoft", "MSFT", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2, analysis_key="MSFT"),
        Instrument("Apple", "AAPL", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2, analysis_key="AAPL"),
        Instrument("Micron", "MU", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2, analysis_key="MU"),
        Instrument("Realty Income", "O", "yahoo", "NYSE", "USD",
                   verified=True, decimals=2, analysis_key="O",
                   note="월배당 리츠(REIT)"),
        Instrument("Invesco QQQ", "QQQ", "yahoo", "NASDAQ", "USD",
                   verified=True, decimals=2, analysis_key="QQQ",
                   note="나스닥100 추종 ETF"),
        Instrument("Schwab US Dividend", "SCHD", "yahoo", "NYSE Arca", "USD",
                   verified=True, decimals=2, analysis_key="SCHD",
                   note="미국 배당주 ETF"),
        Instrument("UnitedHealth", "UNH", "yahoo", "NYSE", "USD",
                   verified=True, decimals=2, analysis_key="UNH"),
        # 2026-11-12 추가 (미국 보유): AMT · CRCL · GOOGL. 시세는 올린 뒤 실제
        # 화면에서 확인합니다 — verified 는 그때 켭니다.
        Instrument("American Tower", "AMT", "yahoo", "NYSE", "USD",
                   decimals=2, analysis_key="AMT", note="통신탑 리츠(REIT)"),
        Instrument("Circle Internet", "CRCL", "yahoo", "NYSE", "USD",
                   decimals=2, analysis_key="CRCL"),
        Instrument("Alphabet (A)", "GOOGL", "yahoo", "NASDAQ", "USD",
                   decimals=2, analysis_key="GOOGL"),
        Instrument("삼성전자", "005930", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0,
                   fundamental_symbol="005930.KS", analysis_key="005930"),
        Instrument("SK하이닉스", "000660", "naver", "KOSPI", "KRW",
                   verified=True, decimals=0,
                   fundamental_symbol="000660.KS", analysis_key="000660"),
        # 2026-11-12 추가 (국내 보유): 삼성증권 · SK스퀘어
        Instrument("삼성증권", "016360", "naver", "KOSPI", "KRW",
                   decimals=0, fundamental_symbol="016360.KS", analysis_key="016360"),
        Instrument("SK스퀘어", "402340", "naver", "KOSPI", "KRW",
                   decimals=0, fundamental_symbol="402340.KS", analysis_key="402340"),
    ),
    footnote="프리장·애프터장 시세가 있으면 함께 표시합니다. 공시 분석은 '공시 분석' 탭에 있습니다.",
)


# ──────────────────────────────────────────────────────────────────────────────
# 밸류에이션 지표
# ──────────────────────────────────────────────────────────────────────────────

VALUATION_TICKERS: tuple[tuple[str, str], ...] = tuple(
    (inst.name, inst.fundamentals_ticker()) for inst in SECTION_WATCHLIST.instruments
)

VALUATION_FIELDS = (
    ("trailingPE", "PER (Trailing)", "num2"),
    ("forwardPE", "Forward PER", "num2"),
    ("priceToBook", "PBR", "num2"),
    ("priceToSalesTrailing12Months", "PSR", "num2"),
    ("enterpriseToEbitda", "EV/EBITDA", "num2"),
    ("grossMargins", "매출총이익률 (Gross Margin)", "pct"),
    ("operatingMargins", "영업이익률 (Operating Margin)", "pct"),
    ("profitMargins", "순이익률 (Net Margin)", "pct"),
    ("returnOnEquity", "ROE", "pct"),
    ("dividendYield", "배당수익률", "pct"),
    ("payoutRatio", "배당성향 (Payout Ratio)", "pct"),
    ("marketCap", "시가총액 (Market Cap)", "bigusd"),
)


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 레지스트리
# ──────────────────────────────────────────────────────────────────────────────

SECTIONS: tuple[Section, ...] = (
    SECTION_WATCHLIST,
    SECTION_DEX,
    SECTION_ADR,
    SECTION_LOCAL,
    SECTION_FUTURES,
    SECTION_MACRO,
    SECTION_ETF_PROXY,
)

SECTION_BY_KEY = {s.key: s for s in SECTIONS}

#: 탭 순서. 섹션 key 또는 특수 key("signals", "valuation", "analysis").
#: '변화 감지' 가 첫 탭입니다 — 뭘 봐야 하는지 알려주는 화면이므로.
TAB_ORDER: tuple[str, ...] = (
    # 목적 기준 5개. 기능을 쌓지 않고 '무엇을 하려는 화면인가' 로 묶었습니다.
    # 요약은 축이 다릅니다 — 5개는 "무엇을 하려는 화면인가", 요약은 "휴대폰에서
    # 10초". 휴대폰으로 간간히 보는 용도라면 탭 5개를 돌 게 아니라 한 화면에서
    # 끝나야 하므로 맨 앞에 둡니다.
    "summary",      # 요약 — 지금 알아야 할 것만
    "holdings",     # 내가 가진 종목 — 변화 감지 + 시세 + 공시 분석
    "discover",     # 종목 발굴 — 미국 버핏식 / 한국 변동성·밸류
    "valuation",    # 걸러낸 종목 밸류에이션 — 역DCF + 사분면
    "chart",        # 차트 조건 — 일목 양운 · CCI · MACD · DMI (일봉)
    "sector_heat",  # 한국 — 섹터 온도 (KODEX 업종 ETF)
    "research",     # 한국 — 증권사 산업분석 리포트 목록 (업종별)
    "semi_research",  # 한국 — 반도체 리포트 (산업 · 삼성전자 · SK하이닉스) 요약
    "kr_flows",     # 한국 — 섹터 뉴스 · 주요 공시 · 경제지표
    "macro",        # 미국 중심 매크로 — 금리·환율·원자재·VIX·FRED
    "us_flows",     # 미국 — 물가 속도 · 글로벌 유동성
    "cycle",        # 메모리 사이클 — 한·미 3사를 같이 봐야 하는 화면
    "calendar",     # 주요 일정 — FOMC·금통위·지표 발표·만기·휴장·실적·배당락
    "supply",       # 한국 — 종목별 외국인·기관 수급
    "earnings",     # 실적 서프라이즈 — 발표치 vs 추정치
)

#: 탭에서 내린 섹션들. **코드는 그대로 남아 있습니다** — 아래 목록에서
#: 지우고 TAB_ORDER 에 key 를 넣으면 되돌아옵니다.
#: 야간 대체가격(괴리율·DEX 선물·지수 선물·ETF 프록시)은 "코스피가 닫힌 동안
#: 한국 시장이 어디로 가는가" 라는 하나의 주제였는데, 목적 기준 5개에 들어가지
#: 않아 내렸습니다. 분석의 본질이 아니라 야간 참고용이었습니다.
#: 섹션 key 는 TAB_ORDER · SECTIONS_MERGED_INTO · TABS_RETIRED 중
#: **정확히 하나**에 있어야 합니다. 테스트가 이걸 검사합니다 — 선언 없이
#: 빠지면 화면에서 조용히 사라지기 때문입니다.
TABS_RETIRED: dict[str, str] = {
    "adr": "괴리율 · 국내 본주",
    "dex": "DEX 선물 (하이퍼리퀴드)",
    "futures": "지수 선물",
    "etf_proxy": "ETF 프록시",
    # 아래는 섹션이 아니라 '예전 탭 이름' 입니다 — 어디로 갔는지 기록용입니다.
    "signals": "변화 감지 → 내 종목 탭 상단",
    "analysis": "공시 분석 → 내 종목 탭",
    "screen": "발굴 · 미국 → 종목 발굴 탭",
    "screen_kr": "발굴 · 국내 → 종목 발굴 탭",
    "diag": "진단 → 화면 위쪽 패널",
}

#: 섹션(= 종목 묶음)으로 존재하면서 탭에서 내려간 것만. 되돌리려면 이 목록에서
#: 지우고 TAB_ORDER 에 key 를 넣으십시오.
SECTIONS_RETIRED: frozenset[str] = frozenset({
    "adr", "dex", "futures", "etf_proxy",
})

#: 자기 탭 없이 **다른 탭 안에서** 렌더링되는 섹션.
#: 국내 본주는 괴리율 계산의 한쪽이라 따로 두면 사슬이 안 보입니다 —
#: 그래서 괴리율 탭에 합쳤습니다. 탭 노출 검사에서 제외됩니다.
SECTIONS_MERGED_INTO: dict[str, str] = {
    # 자기 탭 없이 **다른 탭 안에서** 렌더링되는 섹션.
    # 국내 본주는 보유 종목이라 '내 종목' 탭에 들어갑니다.
    "watchlist": "holdings",
    "local": "holdings",
}


#: **시장이 최상위 축입니다.** (2026-11-11)
#:
#: 전에는 '보는 시장' 라디오를 내비 맨 아래 두고 목록을 거르는 방식이었는데,
#: 기본값이 '전체' 라 처음 열면 아무것도 갈리지 않았고 어느 시장을 보는지
#: 화면 어디에도 안 적혀 있었습니다. 분리가 아니라 숨은 필터였습니다.
#:
#: 이제는 맨 위에서 한국/미국을 먼저 고르고, 시장마다 **다른 섹션 목록**을
#: 봅니다. 모닝 브리프가 index.html / kr.html 을 따로 두는 것과 같은
#: 구조입니다. '전체' 는 없앴습니다.
#:
#: '공통' 은 시장을 바꿔도 같은 화면입니다. 메모리 사이클은 한·미 3사를
#: 나란히 봐야 의미가 있고, 매크로(금리·환율·유가·VIX)는 어느 시장을
#: 보든 같은 배경입니다.
MARKET_TABS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "kr": (
        ("오늘", ("summary", "holdings", "earnings")),
        ("찾기", ("discover", "valuation", "chart")),
        ("한국 시장", ("sector_heat", "supply", "research", "semi_research",
                   "kr_flows")),
        ("공통", ("calendar", "macro", "cycle")),
    ),
    "us": (
        ("오늘", ("summary", "holdings", "earnings")),
        ("찾기", ("discover", "valuation", "chart")),
        ("미국 시장", ("macro", "us_flows")),
        ("공통", ("calendar", "cycle")),
    ),
}

#: 처음 열었을 때의 시장
DEFAULT_MARKET = "kr"


SPECIAL_TAB_LABELS = {
    "summary": "요약",
    "holdings": "내 종목",
    "discover": "종목 발굴",
    "macro": "매크로",
    "sector_heat": "섹터 온도",
    "kr_flows": "뉴스 · 공시 · 지표",
    "us_flows": "물가 · 유동성",
    "valuation": "밸류에이션",
    "chart": "차트 조건",
    "research": "산업 리포트",
    "semi_research": "반도체 리포트",
    "calendar": "주요 일정",
    "cycle": "메모리 사이클",
    "supply": "수급",
    "earnings": "실적 서프라이즈",
}

# ──────────────────────────────────────────────────────────────────────────────
# 전일 장 브리핑 · 산업 리포트
# ──────────────────────────────────────────────────────────────────────────────

#: 미국 업종 ETF (SPDR 11개 섹터). 전일 브리핑의 '업종' 줄에 씁니다.
US_SECTOR_ETFS: tuple[tuple[str, str], ...] = (
    ("XLK", "기술"), ("XLC", "커뮤니케이션"), ("XLY", "경기소비재"),
    ("XLP", "필수소비재"), ("XLF", "금융"), ("XLV", "헬스케어"),
    ("XLI", "산업재"), ("XLE", "에너지"), ("XLB", "소재"),
    ("XLU", "유틸리티"), ("XLRE", "부동산"),
)

#: 시장별 브리핑 정의. cutoff = 현지 마감 + 10분 (이 시각 전에는 오늘 봉을
#: '끝난 날' 로 치지 않습니다). news = (키, 이름, 검색어) — 마감 기사 제목용.
DAILY_BRIEF = {
    "kr": {
        "title": "한국장", "tz": "Asia/Seoul", "cutoff": (15, 40),
        "indices": (("^KS11", "코스피"), ("^KQ11", "코스닥")),
        "extras": (("KRW=X", "원/달러", "pct"),),
        "news": ("kr_close", "한국장 마감", "코스피 코스닥 마감 시황"),
    },
    "us": {
        "title": "미국장", "tz": "America/New_York", "cutoff": (16, 10),
        "indices": (("^GSPC", "S&P 500"), ("^IXIC", "나스닥"),
                    ("^DJI", "다우"), ("^SOX", "필라델피아 반도체")),
        "extras": (("^TNX", "미 10년물", "rate"), ("^VIX", "VIX", "pct"),
                   ("CL=F", "WTI", "pct")),
        "news": ("us_close", "미국장 마감", "뉴욕증시 마감 나스닥 S&P500"),
    },
}

#: 산업 리포트를 몇 쪽 받을지 (쪽당 30건 안팎).
RESEARCH_PAGES = 3
#: 반도체 리포트 화면 — 산업분석을 몇 쪽 훑나 (쪽당 30건, 그중 반도체만 남김),
#: 미리보기·의견을 채울 건수(목록마다), 종목 리포트 쪽수(쪽당 20건).
SEMI_RESEARCH_PAGES = 6
SEMI_DETAIL_LIMIT = 10
SEMI_STOCK_PAGES = 1


def daily_brief_spec(market: str) -> dict:
    """DAILY_BRIEF 에 업종 ETF 와 보유 종목(야후 심볼)을 채워 돌려줍니다."""
    spec = dict(DAILY_BRIEF[market])
    if market == "kr":
        spec["sectors"] = tuple(
            (f"{s[0]}.KS", s[1]) for s in KR_SECTOR_ETFS
            if not (len(s) > 3 and s[3]) and s[0] != "229200")
        kq = kosdaq_codes()
        spec["holdings"] = tuple(
            (f"{i.symbol}.{'KQ' if i.symbol in kq else 'KS'}", i.name)
            for i in SECTION_WATCHLIST.instruments if i.source == "naver")
    else:
        spec["sectors"] = tuple(US_SECTOR_ETFS)
        spec["holdings"] = tuple(
            (i.symbol, i.name) for i in SECTION_WATCHLIST.instruments
            if i.source == "yahoo")
    return spec


def daily_brief_symbols(market: str) -> list[str]:
    spec = daily_brief_spec(market)
    out = [s for s, _l in spec["indices"]] + [s for s, _l, _k in spec["extras"]]
    out += [s for s, _l in spec["sectors"]] + [s for s, _l in spec["holdings"]]
    return list(dict.fromkeys(out))


def chart_candidates(market: str) -> list[tuple[str, str]]:
    """차트 조건을 볼 종목 (코드/티커, 이름).

    한국: 국내 스크리너 후보 전부 (코스피 + 코스닥, 관심종목 포함).
    미국: 관심종목(ETF 포함 — 차트 지표는 ETF 에도 의미가 있습니다) +
          버핏식 스크리너 후보. 관심종목이 앞에 옵니다.
    """
    if market == "kr":
        return list(screen_kr_candidates())
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for inst in SECTION_WATCHLIST.instruments:
        if inst.source == "yahoo" and inst.symbol not in seen:
            seen.add(inst.symbol)
            out.append((inst.symbol, inst.name))
    for tk in SCREEN_CANDIDATES:
        if tk not in seen:
            seen.add(tk)
            out.append((tk, tk))
    return out


def cycle_instruments() -> list[Instrument]:
    """재고 지표 대상 종목의 Instrument. 관심종목·국내 본주 섹션에서 찾습니다."""
    pool: dict[str, Instrument] = {}
    for section in (SECTION_WATCHLIST, SECTION_LOCAL):
        for inst in section.instruments:
            if inst.source == "naver" and inst.symbol in CYCLE_STOCK_CODES:
                pool.setdefault(inst.symbol, inst)
    return [pool[c] for c in CYCLE_STOCK_CODES if c in pool]


def dart_stock_codes() -> list[str]:
    """DART 로 공시를 조회할 종목코드 — 관심종목의 한국 종목."""
    seen: list[str] = []
    for inst in SECTION_WATCHLIST.instruments:
        if inst.source == "naver" and inst.symbol not in seen:
            seen.append(inst.symbol)
    return seen


def edgar_tickers() -> list[str]:
    """EDGAR 로 공시를 조회할 티커 — 미국 상장(yahoo 소스) 관심종목만.

    한국 종목은 EDGAR 에 없습니다 (DART 오픈API 는 키 발급이 필요합니다).
    ETF 는 기업 공시가 없으므로 제외합니다.
    """
    skip = {"QQQ", "SCHD", "DRAM", "EWY", "SOXX", "SMH", "EWJ"}
    return [
        inst.analysis_key or inst.symbol
        for inst in SECTION_WATCHLIST.instruments
        if inst.source == "yahoo" and (inst.analysis_key or inst.symbol) not in skip
    ]


def tab_labels() -> list[tuple[str, str]]:
    """(key, 라벨) 목록을 탭 순서대로 반환합니다."""
    out: list[tuple[str, str]] = []
    for key in TAB_ORDER:
        if key in SPECIAL_TAB_LABELS:
            out.append((key, SPECIAL_TAB_LABELS[key]))
        else:
            section = SECTION_BY_KEY.get(key)
            if section is not None:
                out.append((key, section.tab_label()))
    return out


def analysis_instruments() -> list[Instrument]:
    """공시 분석 패널을 띄울 종목 목록 (중복 제거)."""
    seen: dict[str, Instrument] = {}
    for section in SECTIONS:
        for inst in section.instruments:
            if inst.analysis_key and inst.analysis_key not in seen:
                seen[inst.analysis_key] = inst
    return list(seen.values())


def all_instruments() -> list[Instrument]:
    """모든 섹션의 종목. 발굴 탭이 이미 정의된 종목 정보를 재사용합니다."""
    out: list[Instrument] = []
    seen: set[tuple[str, str]] = set()
    for section in SECTIONS:
        for inst in section.instruments:
            key = (inst.source, inst.symbol)
            if key not in seen:
                seen.add(key)
                out.append(inst)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 시장 띠 — 모든 화면 맨 위의 숫자 6개
# ──────────────────────────────────────────────────────────────────────────────
#
# 2026-11-11 "허접하고 획일적". 어느 화면이든 첫 줄이 설명 문단이나 같은
# 모양의 카드였고, **지금 시장이 어떤가**를 숫자로 보여주는 자리가 없었습니다.
# 참고한 대시보드(모닝 브리프·주식봇)는 모두 맨 위에 지수·환율·선물을 큰
# 숫자로 둡니다. 시장마다 6개 — 그 이상이면 첫 줄이 안 읽힙니다.

#: 다른 섹션에 없는 지수. 시세 받기에만 쓰고 카드로는 그리지 않습니다.
STRIP_EXTRA = (
    Instrument("코스피", "^KS11", "yahoo", "KRX", "KRW", decimals=2),
    Instrument("코스닥", "^KQ11", "yahoo", "KRX", "KRW", decimals=2),
)

#: (심볼, 띠에 쓸 짧은 이름). 심볼은 섹션이나 STRIP_EXTRA 에 있어야 합니다.
MARKET_STRIP = {
    "kr": (("^KS11", "코스피"), ("^KQ11", "코스닥"),
           ("xyz:KR200", "코스피200 야간"), ("KRW=X", "원/달러"),
           ("NQ=F", "나스닥100 선물"), ("^TNX", "미 10년물")),
    "us": (("ES=F", "S&P 500 선물"), ("NQ=F", "나스닥100 선물"),
           ("^TNX", "미 10년물"), ("DX-Y.NYB", "달러 인덱스"),
           ("^VIX", "VIX"), ("CL=F", "WTI")),
}


def strip_instruments(market: str) -> list[tuple[Instrument, str]]:
    """시장 띠에 그릴 (종목, 짧은 이름). 정의가 없는 심볼은 건너뜁니다."""
    by_sym: dict[str, Instrument] = {}
    for section in SECTIONS:
        for inst in section.instruments:
            by_sym.setdefault(inst.symbol, inst)
    for inst in STRIP_EXTRA:
        by_sym.setdefault(inst.symbol, inst)
    out = []
    for sym, label in MARKET_STRIP.get(market, ()):
        if sym in by_sym:
            out.append((by_sym[sym], label))
    return out


def live_symbols(source: str) -> list[str]:
    """**화면에 실제로 보이는** 종목의 심볼만 — 시세 받기에 씁니다.

    2026-11-11: 탭에서 내려간 구역(ADR · DEX · 선물 · ETF 프록시, 위
    SECTIONS_RETIRED)의 시세 약 20개를 아직도 1분마다 받고 있었습니다.
    야후는 종목마다 요청이 따로 나가서, 안 보이는 숫자를 받느라 화면이
    기다렸습니다. 시장 띠에 쓰는 것(선물 2개 · 코스피200 야간)만 남깁니다.
    """
    seen: list[str] = []

    def add(inst) -> None:
        if inst.source != source:
            return
        for sym in (inst.symbol, *inst.alt_symbols):
            if sym not in seen:
                seen.append(sym)
        if source == "naver" and inst.local_peer and inst.local_peer not in seen:
            seen.append(inst.local_peer)

    for section in SECTIONS:
        if section.key in SECTIONS_RETIRED:
            continue
        for inst in section.instruments:
            add(inst)
    for m in MARKETS:
        for inst, _label in strip_instruments(m):
            add(inst)
    # 보유 평가(Secrets 의 PORTFOLIO)에 적힌 종목 — 관심종목에 없어도 시세가 필요
    try:
        import portfolio  # noqa: PLC0415
        for sym in portfolio.symbols(portfolio.load()[0], source):
            if sym not in seen:
                seen.append(sym)
    except Exception:  # noqa: BLE001
        pass
    if source == "yahoo":
        for fx in ("KRW=X", "EURUSD=X"):
            if fx not in seen:
                seen.append(fx)
    return seen


def light_yahoo_symbols() -> list[str]:
    """가격만 있으면 되는 야후 심볼 — 관심종목이 아닌 것 전부.

    관심종목은 변화 감지가 프리장 가격 · 52주 고저 · 실적 발표일을 써서
    상세정보(.info)가 필요합니다. 지수 · 환율 · 금리 · 선물은 아닙니다.
    """
    rich = {s for i in SECTION_WATCHLIST.instruments if i.source == "yahoo"
            for s in (i.symbol, *i.alt_symbols)}
    return [s for s in live_symbols("yahoo") if s not in rich]


def all_yahoo_symbols() -> list[str]:
    """야후로 조회할 모든 심볼 (대체 심볼 포함, 환율 포함)."""
    seen: list[str] = [i.symbol for i in STRIP_EXTRA if i.source == "yahoo"]
    for section in SECTIONS:
        for inst in section.instruments:
            if inst.source != "yahoo":
                continue
            for sym in (inst.symbol, *inst.alt_symbols):
                if sym not in seen:
                    seen.append(sym)
    for fx in ("KRW=X", "EURUSD=X"):
        if fx not in seen:
            seen.append(fx)
    return seen


def all_naver_codes() -> list[str]:
    seen: list[str] = []
    for section in SECTIONS:
        for inst in section.instruments:
            if inst.source == "naver" and inst.symbol not in seen:
                seen.append(inst.symbol)
            if inst.local_peer and inst.local_peer not in seen:
                seen.append(inst.local_peer)
    return seen


def all_hyperliquid_symbols() -> list[str]:
    seen: list[str] = []
    for section in SECTIONS:
        for inst in section.instruments:
            if inst.source == "hyperliquid" and inst.symbol not in seen:
                seen.append(inst.symbol)
    return seen

# ──────────────────────────────────────────────────────────────────────────────
# 시장 구분
# ──────────────────────────────────────────────────────────────────────────────
#
# 한국과 미국을 한 화면에 섞으면 비교가 아니라 잡음이 됩니다. 거래 시간이
# 다르고(장중/장마감이 엇갈림), 회계 기준이 다르고(K-IFRS vs US-GAAP),
# 공시 출처가 다르고(DART vs EDGAR), 등락 색 관행까지 반대입니다.
# 종목이 어느 쪽인지는 Instrument 가 이미 알고 있습니다 — source 와
# currency 가 그것입니다. 새 필드를 만들지 않고 그걸 읽습니다.

MARKETS: dict[str, str] = {
    "kr": "한국",
    "us": "미국",
}


def market_of(inst) -> str:
    """Instrument 의 시장. 'kr' 또는 'us'."""
    if getattr(inst, "source", "") == "naver":
        return "kr"
    if getattr(inst, "currency", "") == "KRW":
        return "kr"
    return "us"


def in_market(inst, market: str) -> bool:
    """market 이 'all' 이면 전부 통과."""
    return market in ("", "all", None) or market_of(inst) == market


def filter_instruments(instruments, market: str) -> list:
    return [i for i in instruments if in_market(i, market)]

# 뉴스 검색용 한국어 종목명.
#
# 구글 뉴스를 hl=ko 로 불러도 검색어가 영어면 영어 기사가 주로 돌아옵니다.
# 한국 매체는 'Microsoft' 가 아니라 '마이크로소프트' 라고 씁니다. 여기에
# 없는 종목은 영문 이름을 그대로 씁니다 — 모르는 이름을 지어내지 않습니다.
# ETF 는 한국 매체도 티커로 부르므로 티커가 맞는 검색어입니다.
NEWS_NAME_KO: dict[str, str] = {
    "MSFT": "마이크로소프트",
    "AAPL": "애플",
    "MU": "마이크론",
    "O": "리얼티인컴",
    "QQQ": "QQQ ETF",
    "SCHD": "SCHD ETF",
    "UNH": "유나이티드헬스",
    "005930": "삼성전자",
    "000660": "SK하이닉스",
}


# ──────────────────────────────────────────────────────────────────────────────
# 물가 · 유동성 계열 (FRED)
# ──────────────────────────────────────────────────────────────────────────────
#
# MACRO_SERIES 와 따로 두는 이유: 저쪽은 '임계값을 넘었나' 를 보는 지표고,
# 여기는 **지수를 속도로 바꿔서** 보는 계열입니다. 쓰는 계산이 다릅니다.
#
# 계열 ID 는 **실제 응답으로 검증되지 않았습니다.** 진단 패널의
# '경제지표 계열 확인' 을 돌리면 어느 ID 가 살아 있는지 알려줍니다.

#: 물가. (계열ID, 표시이름, 계절조정 여부)
#: 계절조정이 아니면 전월비·3개월 연율을 계산하지 않습니다 — 계절 패턴이
#: 물가 상승으로 보입니다.
INFLATION_SERIES: tuple[tuple[str, str, bool], ...] = (
    ("CPIAUCSL", "CPI (헤드라인)", True),
    ("CPILFESL", "CPI 근원", True),
    ("PCEPI", "PCE (헤드라인)", True),
    ("PCEPILFE", "PCE 근원", True),
    ("PPIFIS", "PPI 최종수요", True),
    ("PPIACO", "PPI 전체상품", False),
)

#: 유동성. (키, 계열ID, 표시이름, 단위)
#: **단위가 계열마다 다릅니다** — WALCL 은 백만, 나머지는 십억으로
#: 알려져 있습니다. 그냥 빼면 1000배 틀립니다. liquidity.py 가 받은
#: 값의 크기로 한 번 더 확인하고, 안 맞으면 숫자를 내지 않습니다.
LIQUIDITY_SERIES: tuple[tuple[str, str, str, str], ...] = (
    ("fed_assets", "WALCL", "연준 총자산", "millions"),
    ("rrp", "RRPONTSYD", "역레포 (ON RRP)", "billions"),
    # 2026-11-11 실측으로 고쳤습니다. billions 로 읽으니 957,175십억
    # 달러(= 95경 7천조)가 나왔고 단위 검사가 잡았습니다. millions 로
    # 읽으면 957십억 달러로 정상입니다. WALCL 과 같은 H.4.1 자료라
    # 단위도 같았던 것인데, 제가 역레포와 묶어서 billions 로 적었습니다.
    ("tga", "WTREGEN", "재무부 일반계정 (TGA)", "millions"),
)

#: 참고용 유동성 계열 — 순유동성 계산에는 안 들어갑니다.
#: (계열ID, 이름, 단위, 통화, 정상범위 하한, 상한)
#:
#: **범위를 같이 적는 이유.** TGA 단위를 틀려서 95경 달러가 나온 적이
#: 있습니다. 참고 계열에는 검사가 없어서 틀려도 조용히 지나갑니다.
#: 범위를 적어 두면 화면이 "단위가 이상합니다" 라고 말하고 숫자를
#: 내지 않습니다. 범위는 현지통화 **십억 단위** 기준입니다.
LIQUIDITY_EXTRA: tuple[tuple[str, str, str, str, float, float], ...] = (
    ("M2SL", "미국 M2 통화량", "billions", "달러", 15_000, 35_000),
    ("ECBASSETSW", "ECB 총자산", "millions", "유로", 3_000, 12_000),
    # 일본은행 자산은 FRED 가 '1억 엔' 단위로 줍니다 — 미확인입니다.
    # 700조 엔 근처가 정상이므로 범위를 그렇게 잡아 두고, 벗어나면
    # 화면이 숫자 대신 사유를 적습니다. 진단으로 확인한 뒤 고치십시오.
    ("JPNASSETS", "일본은행 총자산", "hundred_millions", "엔",
     300_000, 1_200_000),
)

#: 한국 경제지표. **전부 미검증입니다** — FRED 의 한국 계열은 OECD
#: 경유라 ID 체계가 미국 계열과 다르고, 중단된 계열도 많습니다.
#: 진단으로 확인한 뒤 안 되는 것은 지우십시오.
KR_MACRO_SERIES: tuple[tuple[str, str], ...] = (
    # 2026-11-12 FRED 에서 직접 확인한 마지막 관측 (같은 날 기준):
    #   끊김  KORCPIALLMINMEI 소비자물가 2023-11 · KORPROINDMISMEI 광공업생산
    #         2024-03 · KORLOLITONOSTSAM 선행지수 2024-01
    #   살아 있음  아래 여덟 개 (2026-08 ~ 2026-09)
    # 소비자물가는 FRED 에 살아 있는 한국 계열이 없습니다 (근원물가
    # CPGRLE01KRM659N 도 2025-04 에서 끊김). 물가 대신 금리·실업률을 둡니다.
    ("KORPRINTO01GYSAM", "한국 산업생산 (전년동월비)"),
    ("KORLOLITOAASTSAM", "한국 OECD 경기선행지수"),
    ("BSCICP02KRM460S", "한국 제조업 기업심리"),
    ("XTEXVA01KRM667S", "한국 수출액"),
    ("XTIMVA01KRM667S", "한국 수입액"),
    ("LRHUTTTTKRM156S", "한국 실업률"),
    ("IR3TIB01KRM156N", "한국 3개월 시장금리"),
    ("IRLTLT01KRM156N", "한국 10년 국채금리"),
)

#: 계열마다 **값을 어떻게 읽나**. 2026-11-12 실제 화면: 수출액이
#: '100,418,800,000.00' 으로, 금리가 '3.17 (+23.8% YoY)' 로 나왔습니다 —
#: 달러 원단위를 그대로 찍고, 금리의 전년비를 % 로 낸 것입니다.
#:   index  지수 — 레벨은 기준연도에 따라 달라 뜻이 없으므로 전년동월비를 앞에
#:   usd    달러 금액 — 억 달러로
#:   rate   금리(%) — 변화는 %p
#:   pct    이미 전년동월비(%)로 오는 계열 — 그대로
#:   level  100 근처에서 오르내리는 지수(선행지수) — 레벨이 뜻이 있음
#:   balance 긍정 − 부정 응답 비율(%p) — 0 이 중립
KR_MACRO_KIND: dict[str, str] = {
    "KORPRINTO01GYSAM": "pct", "KORLOLITOAASTSAM": "level",
    "BSCICP02KRM460S": "balance",
    "XTEXVA01KRM667S": "usd", "XTIMVA01KRM667S": "usd",
    "LRHUTTTTKRM156S": "rate", "IR3TIB01KRM156N": "rate",
    "IRLTLT01KRM156N": "rate",
}


# ──────────────────────────────────────────────────────────────────────────────
# 한국 섹터별 뉴스
# ──────────────────────────────────────────────────────────────────────────────
#
# 종목 뉴스와 다릅니다. 종목 뉴스는 '내 종목에 무슨 일이' 고, 이건
# '내 종목이 속한 업종에 무슨 바람이' 입니다. 업종 뉴스가 먼저 움직이고
# 종목이 따라가는 경우가 많아 따로 봅니다.
#
# 검색어는 **업종 + 한정어** 로 씁니다. '반도체' 만 넣으면 해외 기사와
# 제품 리뷰가 섞입니다. 구글 뉴스를 hl=ko 로 부르므로 한국 매체가
# 우선 나옵니다.

KR_SECTORS: tuple[tuple[str, str, str], ...] = (
    ("rates", "금리 · 통화", "한국은행 기준금리 국고채"),
    ("fx", "환율", "원달러 환율 외환시장"),
    ("semi", "반도체", "반도체 업황 메모리 가격"),
    ("battery", "2차전지", "2차전지 배터리 수주 전기차"),
    ("auto", "자동차", "현대차 기아 완성차 판매"),
    ("ship", "조선 · 방산", "조선 수주 방산 수출"),
    ("bio", "바이오 · 제약", "제약 바이오 임상 기술수출"),
    ("platform", "플랫폼 · 게임", "네이버 카카오 게임 실적"),
    ("policy", "정책 · 수급", "금융위 공매도 밸류업 외국인 수급"),
)

#: 섹터당 가져올 헤드라인 수. 9섹터 × 3건 = 27건이면 한 화면입니다.
SECTOR_NEWS_PER = 3

def tab_groups(market: str = "kr") -> list[tuple[str, list[tuple[str, str]]]]:
    """[(그룹명, [(key, 라벨), …]), …] — 그 시장에서 보이는 섹션만."""
    labels = dict(tab_labels())
    groups = MARKET_TABS.get(market) or MARKET_TABS[DEFAULT_MARKET]
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for group, keys in groups:
        items = [(k, labels[k]) for k in keys if k in labels]
        if items:
            out.append((group, items))
    return out


def market_tab_keys(market: str) -> list[str]:
    """그 시장에서 보이는 섹션 key 순서대로."""
    return [k for _g, items in tab_groups(market) for k, _l in items]


# ──────────────────────────────────────────────────────────────────────────────
# 섹터 온도 — KODEX 업종 ETF
# ──────────────────────────────────────────────────────────────────────────────
#
# (6자리 코드, 업종 이름, 야후 이름에 들어 있어야 할 말들, 기준선 여부)
#
# 업종지수를 직접 받을 공개 경로가 없어 ETF 를 대용으로 씁니다.
#
# **코드는 검증되지 않았습니다.** 틀리면 다른 ETF 의 수익률이 이 이름표를
# 달고 나오는데, 화면에서는 이상이 안 보입니다. 그래서 세 번째 칸에 야후가
# 돌려줄 이름에 들어 있어야 할 말을 적어 두고, 화면이 대조해서 안 맞으면
# 그 줄에 ✗ 를 붙입니다. 야후는 국내 ETF 이름을 영어로 줄 때가 많아
# 한글·영어를 둘 다 적습니다.
KR_SECTOR_ETFS: tuple[tuple, ...] = (
    ("069500", "KODEX 200", ("200",), True),
    ("229200", "코스닥150", ("코스닥150", "kosdaq150", "kosdaq 150")),
    ("091160", "반도체", ("반도체", "semicon")),
    ("305720", "2차전지", ("2차전지", "battery", "secondary")),
    ("091180", "자동차", ("자동차", "auto")),
    ("244580", "바이오", ("바이오", "bio")),
    ("091170", "은행", ("은행", "bank")),
    ("102970", "증권", ("증권", "securities")),
    ("140700", "보험", ("보험", "insurance")),
    ("117460", "에너지화학", ("에너지", "energy", "chem")),
    ("117680", "철강", ("철강", "steel")),
    ("117700", "건설", ("건설", "construction")),
    # 야후가 이 ETF 의 이름을 'KODEX MACHINARY & EQUIPMENT' 로 줍니다 (철자가
    # machinery 가 아님 — 2026-11-12 실제 화면). 코드는 맞는데 낱말이 안 맞아
    # '✗ 코드 확인' 이 떴습니다. 'machin' · 'equipment' 로 받습니다.
    ("102960", "기계장비", ("기계", "machin", "equipment")),
    ("140710", "운송", ("운송", "transport")),
)
