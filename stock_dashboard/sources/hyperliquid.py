"""
Hyperliquid 무기한선물 시세 (HIP-3 빌더 dex 포함).

공개 REST 엔드포인트. API 키 불필요.
  POST https://api.hyperliquid.xyz/info

요청 타입 (공식 문서 확인됨):
  {"type": "perpDexs"}
    -> [null, {"name": "...", "fullName": "...", "deployer": "0x...", ...}]
       첫 원소 null 은 기본(1차) perp dex 를 뜻합니다.

  {"type": "meta", "dex": "<이름>"}
  {"type": "metaAndAssetCtxs", "dex": "<이름>"}
    dex 는 선택값이고, 빈 문자열이면 기본 perp dex 를 가리킵니다.
    -> [ {"universe": [{"name": ..., "szDecimals": ...}, ...]},
         [ {"funding", "openInterest", "prevDayPx", "dayNtlVlm",
            "premium", "oraclePx", "markPx", "midPx", "impactPxs"}, ... ] ]
    두 번째 배열은 universe 와 같은 순서로 1:1 대응합니다.

심볼 표기:
  빌더 배포 마켓은 `dex:COIN` 형태입니다 (예: "xyz:SKHX").
  이 모듈은 "xyz:SKHX" 를 받아 dex="xyz" 로 요청하고, 응답 universe 안에서는
  "SKHX" 와 "xyz:SKHX" 양쪽으로 대조합니다 (응답 표기가 둘 중 어느 쪽이든 동작).

펀딩률:
  응답의 `funding` 은 **시간당** 비율입니다. 8시간 환산값은 ×8 입니다.
  HIP-3 dex 는 assetToFundingMultiplier 로 배수를 따로 둘 수 있어, 실제 지급액은
  dex 설정에 따라 달라질 수 있습니다. 이 모듈은 원본(1h)과 8h 환산을 모두 담습니다.
"""

from __future__ import annotations

from collections import defaultdict

import requests

from .model import MarketStatus, Quote

API_URL = "https://api.hyperliquid.xyz/info"
TIMEOUT = 10


class HyperliquidError(RuntimeError):
    pass


def _post(payload: dict) -> object:
    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise HyperliquidError(f"Hyperliquid 요청 실패: {exc}") from exc
    except ValueError as exc:
        raise HyperliquidError(f"Hyperliquid 응답 파싱 실패: {exc}") from exc


def _to_float(value: object) -> float | None:
    """Hyperliquid 는 수치를 문자열로 반환합니다."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def split_symbol(symbol: str) -> tuple[str, str]:
    """"xyz:SKHX" -> ("xyz", "SKHX"),  "BTC" -> ("", "BTC")."""
    if ":" in symbol:
        dex, coin = symbol.split(":", 1)
        return dex.strip(), coin.strip()
    return "", symbol.strip()


# ──────────────────────────────────────────────────────────────────────────────
# 탐색
# ──────────────────────────────────────────────────────────────────────────────

def list_dexes() -> list[dict]:
    """배포된 perp dex 목록. 기본 dex 는 name="" 으로 정규화해서 넣습니다."""
    data = _post({"type": "perpDexs"})
    if not isinstance(data, list):
        raise HyperliquidError("perpDexs 응답이 배열이 아닙니다.")

    out: list[dict] = []
    for entry in data:
        if entry is None:
            # 첫 원소 null = 기본 perp dex
            out.append({"name": "", "fullName": "기본 perp dex (Hyperliquid)"})
        elif isinstance(entry, dict):
            out.append(entry)
    return out


def list_universe(dex: str = "") -> list[dict]:
    """해당 dex 에 상장된 무기한선물 목록."""
    payload: dict = {"type": "meta"}
    if dex:
        payload["dex"] = dex
    data = _post(payload)
    if not isinstance(data, dict) or "universe" not in data:
        raise HyperliquidError(f"meta(dex={dex!r}) 응답에 universe 가 없습니다.")
    universe = data["universe"]
    if not isinstance(universe, list):
        raise HyperliquidError("universe 형식이 예상과 다릅니다.")
    return universe


# ──────────────────────────────────────────────────────────────────────────────
# 시세
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_one_dex(dex: str, wanted: list[str]) -> dict[str, Quote]:
    """하나의 dex 에서 요청 심볼들의 시세를 가져옵니다.

    wanted 는 원본 심볼 그대로("xyz:SKHX") 받고, 반환 키도 원본 심볼입니다.
    """
    payload: dict = {"type": "metaAndAssetCtxs"}
    if dex:
        payload["dex"] = dex

    try:
        data = _post(payload)
    except HyperliquidError as exc:
        return {s: Quote.failed(s, str(exc)) for s in wanted}

    if not (isinstance(data, list) and len(data) >= 2):
        reason = f"metaAndAssetCtxs(dex={dex!r}) 응답 형식이 예상과 다릅니다."
        return {s: Quote.failed(s, reason) for s in wanted}

    meta, ctxs = data[0], data[1]
    universe = meta.get("universe", []) if isinstance(meta, dict) else []

    if not isinstance(universe, list) or not isinstance(ctxs, list):
        reason = f"universe/assetCtxs(dex={dex!r}) 형식이 예상과 다릅니다."
        return {s: Quote.failed(s, reason) for s in wanted}

    # 응답 universe 이름 -> context
    by_name: dict[str, dict] = {}
    listed: list[str] = []
    for idx, entry in enumerate(universe):
        if not isinstance(entry, dict) or idx >= len(ctxs):
            continue
        name = entry.get("name")
        ctx = ctxs[idx]
        if not isinstance(name, str) or not isinstance(ctx, dict):
            continue
        listed.append(name)
        # 표기가 "SKHX" 인 경우와 "xyz:SKHX" 인 경우를 모두 받아둡니다
        _, bare = split_symbol(name)
        by_name[name] = ctx
        by_name[name.upper()] = ctx
        by_name[bare] = ctx
        by_name[bare.upper()] = ctx

    out: dict[str, Quote] = {}
    for sym in wanted:
        _, bare = split_symbol(sym)
        ctx = (
            by_name.get(sym)
            or by_name.get(sym.upper())
            or by_name.get(bare)
            or by_name.get(bare.upper())
        )
        if ctx is None:
            sample = ", ".join(sorted(listed)[:10])
            out[sym] = Quote.failed(
                sym,
                f"dex={dex or '(기본)'} 에 '{bare}' 가 없습니다. "
                f"상장 심볼 예: {sample} … "
                f"tools/discover_hyperliquid.py 로 전체 목록을 확인하십시오.",
            )
            continue

        mark = _to_float(ctx.get("markPx")) or _to_float(ctx.get("midPx"))
        prev = _to_float(ctx.get("prevDayPx"))
        funding_1h = _to_float(ctx.get("funding"))

        extra: dict = {}
        if funding_1h is not None:
            extra["funding_1h"] = funding_1h
            extra["funding_8h"] = funding_1h * 8.0
        for key, label in (
            ("openInterest", "open_interest"),
            ("dayNtlVlm", "day_volume_usd"),
            ("oraclePx", "oracle_px"),
            ("premium", "perp_premium"),
        ):
            val = _to_float(ctx.get(key))
            if val is not None:
                extra[label] = val

        out[sym] = Quote(
            symbol=sym,
            price=mark,
            prev_close=prev,
            currency="USD",
            status=MarketStatus.LIVE,
            extra=extra,
            error=None if mark is not None else "markPx 를 읽을 수 없습니다.",
        )

    return out


def fetch_quotes(symbols: list[str]) -> dict[str, Quote]:
    """심볼들을 dex 별로 묶어서, dex 당 한 번씩만 요청합니다."""
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return {}

    grouped: dict[str, list[str]] = defaultdict(list)
    for sym in unique:
        dex, _ = split_symbol(sym)
        grouped[dex].append(sym)

    out: dict[str, Quote] = {}
    for dex, wanted in grouped.items():
        try:
            out.update(_fetch_one_dex(dex, wanted))
        except Exception as exc:  # noqa: BLE001
            out.update({s: Quote.failed(s, f"조회 중 예외: {exc}") for s in wanted})

    return out
