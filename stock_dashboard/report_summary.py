"""
리포트 AI 요약 — 무엇을 요약하고, 어떻게 저장하고, 얼마나 쓰나.

수집기가 Claude API 로 요약한 글을 summaries.json 한 파일에 모아 data
브랜치에 올립니다. 앱은 그 파일을 읽어 반도체 리포트 카드에 붙입니다.

    {"version": 1, "items": {"industry:46967": {"summary": "…", "title": …,
      "broker": …, "date": …, "model": …, "at": 1794450000,
      "input_tokens": …, "output_tokens": …}}}

**비용을 묶는 장치.**
  · 이미 요약한 리포트는 다시 보내지 않습니다 (리서치 번호로 기억).
  · 한 번 돌 때 새로 요약하는 건수에 상한이 있습니다 (config.SUMMARY_MAX_NEW).
  · 목록마다 최근 몇 건만 봅니다 (config.SUMMARY_PER_LIST).
  · 리포트마다 앞 SUMMARY_MAX_PAGES 쪽만 보냅니다. 큰 PDF 도 받아서 앞쪽만
    자르고, 자른 것이 20 MB 를 넘으면 쪽수를 더 줄입니다.

**요약에 넣지 않는 것.** 투자의견 · 목표주가 · 매수/매도 권유. 이 대시보드는
추천과 목표주가를 제시하지 않습니다 (증권사가 낸 숫자는 카드의 '증권사
제시' 줄에 따로 있습니다).
"""
from __future__ import annotations

import json
import time

VERSION = 1
#: 저장 파일에 남겨 둘 최대 건수 (오래된 것부터 버림).
KEEP_MAX = 400

PROMPT = """첨부한 PDF 는 한국 증권사의 리포트다. 한국어로 요약해라.

형식 (이 세 줄머리를 그대로 쓰고, 각 항목은 '- ' 로 시작하는 짧은 문장):
핵심 주장
- (최대 3개)
근거 숫자
- (최대 3개. 숫자와 단위, 괄호 안에 쪽수. 예: DRAM 계약가 +12% (3쪽))
가정 · 위험
- (리포트가 스스로 밝힌 전제나 위험, 최대 2개. 없으면 '- 리포트에 언급 없음')

규칙:
- 문서에 적힌 내용만 쓴다. 문서에 없는 해석이나 배경 지식을 더하지 않는다.
- 투자의견, 목표주가, 매수·매도 권유, 업종 비중 의견(비중확대·축소), 추천 종목은 옮기지 않는다.
- 문서의 일부(앞쪽)만 받았을 수 있다. 받은 쪽에 있는 내용만 쓴다.
- 문장을 그대로 베끼지 말고 짧게 다시 쓴다.
- 전체 450자 이내. 머리말이나 맺음말을 붙이지 않는다."""


def key_of(report) -> str:
    """리포트를 가리키는 이름 — 'industry:46967' · 'company:97570'."""
    rid = (getattr(report, "research_id", "") or "").strip()
    if not rid:
        return ""
    kind = "company" if getattr(report, "kind", "") == "company" else "industry"
    return f"{kind}:{rid}"


def parse(text: str) -> dict:
    """저장 파일 글 → {이름: 항목}. 깨졌으면 빈 묶음."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        return {}
    return {str(k): v for k, v in items.items()
            if isinstance(v, dict) and isinstance(v.get("summary"), str) and v["summary"].strip()}


def dump(items: dict) -> str:
    """{이름: 항목} → 저장 파일 글. 최근 KEEP_MAX 건만."""
    ordered = sorted(items.items(), key=lambda kv: kv[1].get("at", 0), reverse=True)[:KEEP_MAX]
    return json.dumps({"version": VERSION, "made": int(time.time()),
                       "items": dict(ordered)}, ensure_ascii=False, indent=1)


def targets(lists: dict, existing: dict, per_list: int, max_new: int) -> list:
    """새로 요약할 리포트들. lists: {묶음 이름: [Report]} — 묶음을 돌아가며 고릅니다.

    PDF 주소가 있고 아직 요약이 없는 것만. 한 묶음이 상한을 다 쓰지 않게
    묶음마다 한 건씩 번갈아 뽑습니다 (최신 것부터).
    """
    queues = []
    for reports in lists.values():
        q = [r for r in list(reports)[:per_list]
             if key_of(r) and (key_of(r) not in existing or needs_redo(existing[key_of(r)]))
             and str(getattr(r, "pdf", "") or "").startswith(("https://", "http://"))]
        if q:
            queues.append(q)
    out, seen = [], set()
    while queues and len(out) < max_new:
        for q in list(queues):
            if not q:
                queues.remove(q)
                continue
            r = q.pop(0)
            if key_of(r) not in seen:
                seen.add(key_of(r))
                out.append(r)
            if len(out) >= max_new:
                break
        queues = [q for q in queues if q]
    return out


def entry(report, summary: str, model: str, usage: dict | None = None) -> dict:
    usage = usage or {}
    return {
        "summary": clean(summary), "title": getattr(report, "title", ""),
        "broker": getattr(report, "broker", ""), "date": getattr(report, "date", ""),
        "model": model, "at": int(time.time()),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "pages_total": int(usage.get("pages_total") or 0),
        "pages_sent": int(usage.get("pages_sent") or 0),
    }


def needs_redo(item: dict) -> bool:
    """저장된 요약이 잘린 것인가 — 그렇다면 다시 요약합니다.

    2026-11-12 첫 실행(max_tokens 700)에서 출력이 딱 700 토큰에 끊긴 요약이
    저장됐습니다. 그때는 쪽수 칸이 없었으므로 그것으로 가립니다.
    """
    return (not item.get("pages_sent")) and int(item.get("output_tokens") or 0) == 700


def clean(text: str, limit: int = 900) -> str:
    """요약 글을 다듬습니다 — 빈 줄·마크다운 굵은 표시 제거, 너무 길면 자름."""
    lines = []
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip().replace("**", "").lstrip("#").strip()
        if line:
            lines.append(line)
    out = "\n".join(lines)
    return out if len(out) <= limit else out[:limit].rstrip() + "…"


def blocks(summary: str) -> list[tuple[str, list[str]]]:
    """요약 글 → [(줄머리, [항목…])]. 줄머리가 없으면 ('', [줄…]) 하나."""
    out: list[tuple[str, list[str]]] = []
    for line in clean(summary).split("\n"):
        if line.startswith(("- ", "• ", "· ")):
            if not out:
                out.append(("", []))
            out[-1][1].append(line[2:].strip())
        else:
            out.append((line.rstrip(":："), []))
    return [(h, items) for h, items in out if h or items]


def cost_usd(items: dict, in_per_mtok: float, out_per_mtok: float) -> float:
    """저장된 사용량으로 대략 든 돈 (참고용 — 실제 청구는 Console 을 보십시오)."""
    tin = sum(int(v.get("input_tokens") or 0) for v in items.values())
    tout = sum(int(v.get("output_tokens") or 0) for v in items.values())
    return tin / 1e6 * in_per_mtok + tout / 1e6 * out_per_mtok
