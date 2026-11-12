"""
Claude API — 리포트 PDF 요약에만 씁니다 (아침 수집기에서).

2026-11-12 요청: "리포트 요약해줄 수 있는 AI … 반도체 산업 및 삼전 하닉만".

**어디서 부르나.** 앱이 아니라 수집기(tools/collect.py, GitHub Actions)입니다.
앱에서 부르면 화면을 열 때마다 돈이 나가고 느립니다. 수집기는 새 리포트만
한 번 요약해 결과를 data 브랜치에 저장하고, 앱은 그 글을 읽기만 합니다.

**키.** 환경변수 ANTHROPIC_API_KEY 로만 받습니다 (GitHub Secrets). 파일에
적지 않고, 오류 문구에도 남기지 않습니다. 키가 없으면 요약 단계를 통째로
건너뜁니다 — 나머지 수집은 그대로 돕니다.

요청 모양은 공식 문서의 Messages API · PDF 지원을 따릅니다
(platform.claude.com/docs/en/build-with-claude/pdf-support). PDF 는 수집기가
받아서 base64 로 보냅니다 — 주소만 넘기면 Anthropic 서버가 네이버에서 직접
받아야 하는데, 그쪽에서 막힐 수 있습니다.
"""
from __future__ import annotations

import base64
import os

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
ENV_KEY = "ANTHROPIC_API_KEY"
TIMEOUT = (10, 120)
#: 이보다 큰 PDF 는 보내지 않습니다 (쪽수가 많아 비용이 튑니다).
MAX_PDF_BYTES = 8 * 1024 * 1024


class ClaudeError(RuntimeError):
    """요청 실패. 문구에서 키를 지웁니다."""

    def __init__(self, *args):
        from . import safe  # noqa: PLC0415
        super().__init__(*(safe.scrub(a) if isinstance(a, str) else a for a in args))


def api_key() -> str:
    return (os.environ.get(ENV_KEY) or "").strip()


def trim_pdf(pdf: bytes, max_pages: int) -> tuple[bytes, int, int]:
    """PDF 를 앞 max_pages 쪽으로 자릅니다. (자른 PDF, 전체 쪽수, 보낸 쪽수)

    2026-11-12 첫 실제 실행에서 리포트 한 건이 입력 21만 토큰이었습니다
    (수십 쪽짜리 전망 리포트 — 쪽마다 글 + 그림으로 셉니다). 쪽수를 묶지
    않으면 비용이 리포트 길이를 그대로 따라갑니다. 증권사 리포트는 요약과
    핵심 근거가 앞쪽에 있어서 앞부분만 읽힙니다.
    쪽수를 셀 수 없으면(pypdf 없음 · 깨진 파일) 보내지 않습니다 — 얼마가
    들지 모르는 요청은 하지 않습니다.
    """
    import io  # noqa: PLC0415

    try:
        from pypdf import PdfReader, PdfWriter  # noqa: PLC0415
    except ImportError:
        raise ClaudeError("pypdf 가 없어 쪽수를 셀 수 없습니다 (requirements.txt 확인).") from None
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise ClaudeError("암호가 걸린 PDF 입니다.")
        total = len(reader.pages)
        if total <= max_pages:
            return pdf, total, total
        writer = PdfWriter()
        for i in range(max_pages):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
    except ClaudeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ClaudeError(f"PDF 를 읽지 못했습니다: {type(exc).__name__}") from None
    return buf.getvalue(), total, max_pages


def build_request(pdf: bytes, prompt: str, model: str, max_tokens: int,
                  effort: str = "low") -> dict:
    """요청 본문.

    생각(thinking)은 이 모델에서 기본으로 켜져 있고 max_tokens 안에서 셉니다.
    2026-11-12 첫 실행은 max_tokens 700 이라 12건 중 9건이 생각만 하다 끝나
    글이 없었습니다. 그래서 (1) effort 를 낮춰 생각을 줄이고 (2) max_tokens 에
    여유를 둡니다. 생각을 아예 끄는 설정은 effort 조합에 따라 400 이 날 수
    있어 쓰지 않습니다 (문서: build-with-claude/thinking).
    """
    return {
        "model": model,
        "max_tokens": max_tokens,
        "output_config": {"effort": effort},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": base64.standard_b64encode(pdf).decode("ascii")}},
                {"type": "text", "text": prompt},
            ],
        }],
    }


def parse_response(payload) -> tuple[str, dict]:
    """응답 → (글, 사용량). 글이 없으면 ClaudeError."""
    if not isinstance(payload, dict):
        raise ClaudeError("응답 형식이 예상과 다릅니다.")
    if payload.get("type") == "error" or "error" in payload:
        err = payload.get("error") or {}
        raise ClaudeError(f"API 오류: {err.get('type', '')} — {str(err.get('message', ''))[:200]}")
    parts = [b.get("text", "") for b in payload.get("content") or []
             if isinstance(b, dict) and b.get("type") == "text"]
    text = "\n".join(p for p in parts if p).strip()
    stop = str(payload.get("stop_reason") or "")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    if not text:
        kinds = ",".join(str(b.get("type")) for b in payload.get("content") or []
                         if isinstance(b, dict)) or "없음"
        raise ClaudeError(
            f"응답에 글이 없습니다 (stop_reason={stop or '?'} · 블록 {kinds} · "
            f"입력 {int(usage.get('input_tokens') or 0):,} · "
            f"출력 {int(usage.get('output_tokens') or 0):,} 토큰).")
    if stop == "max_tokens":
        # 잘린 요약을 저장하면 다시 요약하지 않으므로 실패로 칩니다
        raise ClaudeError(
            f"요약이 중간에 잘렸습니다 (stop_reason=max_tokens · "
            f"출력 {int(usage.get('output_tokens') or 0):,} 토큰).")
    return text, {"input_tokens": int(usage.get("input_tokens") or 0),
                  "output_tokens": int(usage.get("output_tokens") or 0),
                  "stop_reason": str(payload.get("stop_reason") or "")}


def summarize_pdf(pdf: bytes, prompt: str, *, model: str, max_tokens: int = 3000,
                  max_pages: int = 30, post=None) -> tuple[str, dict]:
    """PDF 한 건을 요약합니다. (글, 사용량 — pages_total · pages_sent 포함)"""
    key = api_key()
    if not key:
        raise ClaudeError(f"{ENV_KEY} 가 없습니다.")
    if not pdf or not pdf.startswith(b"%PDF"):
        raise ClaudeError("PDF 가 아닙니다.")
    if len(pdf) > MAX_PDF_BYTES:
        raise ClaudeError(f"PDF 가 너무 큽니다 ({len(pdf) / 1e6:.1f} MB).")
    pdf, total, sent = trim_pdf(pdf, max_pages)
    body = build_request(pdf, prompt, model, max_tokens)
    headers = {"x-api-key": key, "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    if post is None:
        import requests  # noqa: PLC0415

        def post(url, json, headers, timeout):       # noqa: A002
            resp = requests.post(url, json=json, headers=headers, timeout=timeout)
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                raise ClaudeError(f"HTTP {resp.status_code} — JSON 이 아닙니다.") from None
            if resp.status_code >= 400 and "error" not in data:
                raise ClaudeError(f"HTTP {resp.status_code}")
            return data
    def send(b):
        try:
            return post(API_URL, json=b, headers=headers, timeout=TIMEOUT)
        except ClaudeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ClaudeError(f"요청 실패: {type(exc).__name__}") from None

    payload = send(body)
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict) and err.get("type") == "invalid_request_error" and any(
            w in str(err.get("message", "")) for w in ("output_config", "effort")):
        # effort 칸을 받지 않는 경우 — 그 칸만 빼고 한 번 더 (400 은 청구되지 않습니다)
        body.pop("output_config", None)
        payload = send(body)
    text, usage = parse_response(payload)
    usage["pages_total"], usage["pages_sent"] = total, sent
    return text, usage
