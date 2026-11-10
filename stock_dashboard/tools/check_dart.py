"""
DART 연동 환경을 점검합니다.

실행:
    cd stock_dashboard
    python -m tools.check_dart              # 키 확인 + 실제 호출 1회
    python -m tools.check_dart --no-call    # 키만 확인 (호출 안 함)
    python -m tools.check_dart --inventory  # 재고 지표까지 실제로 계산

키 발급:
    1. https://opendart.fss.or.kr 회원가입 (이메일 인증)
    2. '인증키 신청/관리' → 신청
    3. '오픈API 이용현황' 에서 40자리 키 확인
    4. export DART_API_KEY="40자리키"   (Windows: setx DART_API_KEY "40자리키")
"""

from __future__ import annotations

import sys

import config
import cycle
from sources import dart

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def step(n: int, title: str) -> None:
    print(f"\n{'=' * 72}\n{n}. {title}\n{'=' * 72}")


def check_key() -> bool:
    step(1, "인증키")
    ok, msg = dart.key_status()
    if ok:
        print(f"  {GREEN}OK{RESET}   {msg}")
        return True
    print(f"  {RED}FAIL{RESET} {msg}")
    print()
    print("  발급 절차:")
    print("    1) https://opendart.fss.or.kr 회원가입 (이메일 인증)")
    print("    2) '인증키 신청/관리' → 신청")
    print("    3) '오픈API 이용현황' 에서 40자리 키 확인")
    print()
    print("  환경변수 설정:")
    print('    macOS/Linux   export DART_API_KEY="40자리키"')
    print('    Windows       setx DART_API_KEY "40자리키"   (새 터미널부터 적용)')
    print()
    print(f"  {DIM}키는 환경변수로만 받습니다 — config.py 에 적으면 압축 파일이나")
    print(f"  저장소에 섞여 나갑니다.{RESET}")
    return False


def check_corp_codes() -> dict | None:
    step(2, "고유번호 매핑 (corpCode.xml)")
    print(f"  {DIM}약 1MB ZIP 을 받아 상장사 목록을 추립니다…{RESET}")
    try:
        corp_map = dart.fetch_corp_codes()
    except dart.DartError as exc:
        print(f"  {RED}FAIL{RESET} {exc}")
        return None

    print(f"  {GREEN}OK{RESET}   상장사 {len(corp_map):,}개")
    for code in config.dart_stock_codes():
        corp = dart.resolve_corp_code(code, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if corp:
            name = (corp_map.get(code) or {}).get("corp_name", "")
            print(f"         {GREEN}✓{RESET} {code} → {corp}  {name}")
        else:
            print(f"         {RED}✗{RESET} {code} → 찾지 못함 "
                  f"(config.DART_CORP_CODE_OVERRIDES 에 직접 지정 가능)")
    return corp_map


def check_disclosures(corp_map: dict) -> None:
    step(3, "공시 목록 (list.json)")
    for code in config.dart_stock_codes():
        corp = dart.resolve_corp_code(code, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if not corp:
            continue
        try:
            items = dart.fetch_disclosures(corp, since_days=120, limit=6)
        except dart.DartError as exc:
            print(f"  {RED}FAIL{RESET} {code}: {exc}")
            continue
        print(f"\n  {code} — 최근 {len(items)}건")
        for d in items:
            mark = "●" if d.importance >= 2 else "○"
            ago = f"{d.days_ago}일 전" if d.days_ago is not None else d.date_iso
            print(f"    {mark} {d.date_iso}  {d.report_nm[:44]:<44} {DIM}{ago}{RESET}")


def check_inventory(corp_map: dict) -> None:
    step(4, "재고 지표 (fnlttSinglAcntAll.json)")
    for inst in config.cycle_instruments():
        corp = dart.resolve_corp_code(
            inst.symbol, corp_map, config.DART_CORP_CODE_OVERRIDES)
        if not corp:
            continue

        collected: list = []
        warnings: list[str] = []
        year, quarter = dart.latest_available_quarter()
        print(f"\n  {inst.name} ({inst.symbol}) — "
              f"{year} {quarter} 부터 {config.CYCLE_QUARTERS_BACK}분기 역순 수집")

        for _ in range(config.CYCLE_QUARTERS_BACK):
            try:
                accounts = dart.fetch_financials(
                    corp, year, quarter, fs_div=config.CYCLE_FS_DIV)
                if accounts:
                    collected.append((year, quarter, config.CYCLE_FS_DIV, accounts))
                    print(f"    {GREEN}OK{RESET}   {year} {quarter}  계정 {len(accounts)}건")
                else:
                    print(f"    {DIM}빈 응답 {year} {quarter}{RESET}")
            except dart.DartError as exc:
                if "조회된 데이터가 없습니다" in str(exc):
                    print(f"    {DIM}없음 {year} {quarter} (미공시){RESET}")
                else:
                    print(f"    {RED}FAIL{RESET} {year} {quarter}: {exc}")
                    warnings.append(f"{year} {quarter}: {exc}")
            year, quarter = dart.previous_quarter(year, quarter)

        if not collected:
            print(f"    {RED}수집된 분기가 없습니다.{RESET}")
            continue

        trend = cycle.build_trend(inst.name, inst.symbol, collected, warnings)
        print()
        for q in trend.quarters:
            dio = f"{q.dio:.0f}일" if q.dio is not None else (
                f"{q.dio_raw:.0f}일 {RED}(제외){RESET}" if q.dio_raw else "—")
            print(f"    {q.label:<12} 재고 {_won(q.inventory):>12}  "
                  f"매출원가 {_won(q.cost_of_sales):>12}  DIO {dio}")

        band = trend.dio_band
        if band:
            print(f"\n    밴드 {band[0]:.0f}~{band[2]:.0f}일 (중간 {band[1]:.0f}) · "
                  f"현재 위치 {trend.dio_position:.0f}%")
        if trend.dio_qoq_change is not None:
            print(f"    직전 분기 대비 {trend.dio_qoq_change:+.1f}일 · "
                  f"연속 상승 {trend.dio_rising_quarters}분기")
        if trend.inventory_revenue_gap is not None:
            print(f"    재고-매출 증가율 갭 {trend.inventory_revenue_gap:+.1f}%포인트")
        if trend.all_missing:
            print(f"    {YELLOW}못 찾은 계정: {', '.join(trend.all_missing)}{RESET}")
        for w in trend.dio_warnings:
            print(f"    {RED}{w}{RESET}")

        print()
        for c in cycle.checklist(trend):
            mark = (f"{RED}점등{RESET}" if c.lit else
                    (f"{DIM}판정불가{RESET}" if c.lit is None else "미점등"))
            print(f"    [{mark}] {c.label}")
            if c.detail:
                print(f"              {DIM}{c.detail[:72]}{RESET}")


def _won(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1_0000_0000_0000:
        return f"{value / 1_0000_0000_0000:,.1f}조"
    if abs(value) >= 1_0000_0000:
        return f"{value / 1_0000_0000:,.0f}억"
    return f"{value:,.0f}"


def main(argv: list[str]) -> int:
    if not check_key():
        return 1
    if "--no-call" in argv:
        print("\n--no-call 이므로 실제 호출은 건너뜁니다.")
        return 0

    corp_map = check_corp_codes()
    if corp_map is None:
        return 1

    check_disclosures(corp_map)
    if "--inventory" in argv:
        check_inventory(corp_map)
    else:
        print(f"\n{DIM}재고 지표까지 확인하려면 --inventory 를 붙이십시오 "
              f"(종목당 최대 {config.CYCLE_QUARTERS_BACK}회 호출).{RESET}")

    print(f"\n{'=' * 72}")
    print("점검 완료. 호출 한도는 인증키당 하루 20,000건입니다.")
    print(f"{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
