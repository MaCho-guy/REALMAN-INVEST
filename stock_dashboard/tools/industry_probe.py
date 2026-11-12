"""네이버 업종 응답 확인 — survey 워크플로 market=industry (2026-11-13).

차트 조건 탭의 '반도체 먼저' 분류가 첫 실행에서 실패했습니다 (업종 목록 페이지에서
'반도체' 를 못 찾음). 실제 응답의 모양을 로그에 찍습니다. 데이터 파일은 건드리지 않습니다.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from sources import naver, universe_src  # noqa: E402

URLS = [
    universe_src.GROUPS_API_URL.format(page=1, size=100),
    universe_src.GROUP_API_URL.format(no=278, page=1, size=5),
]


def _json(text: str):
    import json  # noqa: PLC0415

    try:
        return json.loads(text)
    except ValueError:
        return {}


def show(url: str) -> None:
    print(f"\n=== {url}")
    for hdr in ({**naver.HEADERS, "Accept": "application/json"},
                {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}):
        try:
            r = requests.get(url, headers=hdr, timeout=15)
        except Exception as exc:  # noqa: BLE001
            print(f"  요청 실패: {type(exc).__name__}: {exc}")
            continue
        raw = r.content or b""
        text = ""
        for enc in ("utf-8", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        print(f"  UA={hdr['User-Agent'][:20]} 상태 {r.status_code} · {len(raw)} B · "
              f"type {r.headers.get('Content-Type')} · 인코딩 {enc}")
        print("  앞부분:", re.sub(r"\s+", " ", text[:600]))
        links = re.findall(r"type=upjong[^\"'>]{0,40}", text)
        print(f"  upjong 링크 {len(links)}개 예: {links[:5]}")
        i = text.find("반도체")
        near = re.sub(r"\s+", " ", text[max(0, i - 250):i + 120]) if i >= 0 else "-"
        print(f"  '반도체' 위치 {i}: {near}")
        n_codes = len(re.findall(r"code=(\d{6})", text))
        print(f"  종목 코드 링크 {n_codes}개")
        print(f"  파서: 업종 {[g for g in universe_src.parse_groups(_json(text)) if '반도체' in g['name']]}")


for u in URLS:
    show(u)
try:
    codes, info = universe_src.fetch_kr_industry()
    print(f"\n결과: {info} · 예 {sorted(codes)[:10]}")
except Exception as exc:  # noqa: BLE001
    print(f"\n결과: 실패 — {exc}")
