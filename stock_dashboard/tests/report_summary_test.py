"""리포트 AI 요약 검증 — 요청 모양 · 대상 고르기 · 수집기 단계 · 카드 · 키 지우기.

    python tests/report_summary_test.py

실제 API 는 부르지 않습니다 (가짜 응답). 실제 호출은 키가 GitHub Secrets 에
들어간 뒤 collect 로그로 확인합니다.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import tempfile

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
sys.path.insert(0, "tools")

FAKE_KEY = "sk-ant-" + "api03-" + "T" * 24 + "_test-0001"
os.environ.pop("ANTHROPIC_API_KEY", None)

import components as ui  # noqa: E402
import config  # noqa: E402
import demo  # noqa: E402
import report_summary as rs  # noqa: E402
import semi_research  # noqa: E402
from sources import claude_api, safe  # noqa: E402
from sources.research import Report  # noqa: E402

FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def rep(kind, rid, title="제목", pdf="https://x.test/a.pdf", broker="가증권", date="2026-11-12"):
    return Report(kind=kind, title=title, broker=broker, date=date, pdf=pdf, research_id=rid)


def make_pdf(pages: int) -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


PDF = make_pdf(3)
SUMMARY = ("**핵심 주장**\n- 가격이 오른다고 본다\n\n근거 숫자\n- DRAM 계약가 +12% (3쪽)\n"
           "가정 · 위험\n- 수요 가정이 바뀌면 달라진다")

print("\n=== 요청 모양 (Messages API · PDF) ===")
body = claude_api.build_request(PDF, "요약해라", "claude-haiku-5-5", 700)
doc, text = body["messages"][0]["content"]
check("document 블록이 먼저, 글이 뒤", doc["type"] == "document" and text["type"] == "text")
check("effort 를 낮춰 생각을 줄임 · thinking 칸은 보내지 않음",
      body["output_config"] == {"effort": "low"} and "thinking" not in body)
check("PDF 를 base64 로", doc["source"] == {
    "type": "base64", "media_type": "application/pdf",
    "data": base64.standard_b64encode(PDF).decode()})
check("모델 · max_tokens", body["model"] == "claude-haiku-5-5" and body["max_tokens"] == 700)

seen = {}


def fake_post(url, json, headers, timeout):  # noqa: A002
    seen.update(url=url, headers=headers, body=json)
    return {"type": "message", "content": [{"type": "text", "text": SUMMARY}],
            "usage": {"input_tokens": 7000, "output_tokens": 300}, "stop_reason": "end_turn"}


try:
    claude_api.summarize_pdf(PDF, "p", model="m", post=fake_post)
    check("키가 없으면 부르지 않음", False)
except claude_api.ClaudeError:
    check("키가 없으면 부르지 않음", not seen)

os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
got, usage = claude_api.summarize_pdf(PDF, "p", model="claude-haiku-5-5", post=fake_post)
check("쪽수를 사용량에 적음", usage["pages_total"] == 3 and usage["pages_sent"] == 3)
check("기본 max_tokens 에 생각할 여유", seen["body"]["max_tokens"] >= 2000)
check("주소 · 머리글", seen["url"] == "https://api.anthropic.com/v1/messages"
      and seen["headers"]["x-api-key"] == FAKE_KEY
      and seen["headers"]["anthropic-version"] == "2023-06-01")
check("글과 사용량을 돌려줌", got == SUMMARY and usage["input_tokens"] == 7000
      and usage["output_tokens"] == 300)
for label, bad in (("PDF 가 아니면 거절", b"<html>"), ("빈 파일 거절", b""),
                   ("너무 큰 PDF 거절", b"%PDF" + b"0" * (claude_api.MAX_PDF_BYTES + 1))):
    seen.clear()
    try:
        claude_api.summarize_pdf(bad, "p", model="m", post=fake_post)
        check(label, False)
    except claude_api.ClaudeError:
        check(label, not seen)


def post_error(url, json, headers, timeout):  # noqa: A002
    return {"type": "error", "error": {"type": "authentication_error",
                                       "message": f"invalid x-api-key {FAKE_KEY}"}}


try:
    claude_api.summarize_pdf(PDF, "p", model="m", post=post_error)
    check("API 오류는 예외", False)
except claude_api.ClaudeError as exc:
    check("API 오류는 예외 · 종류를 남김", "authentication_error" in str(exc))
    check("오류 문구에 키가 없음", FAKE_KEY not in str(exc) and "T" * 24 not in str(exc), str(exc))


def post_boom(url, json, headers, timeout):  # noqa: A002
    raise RuntimeError(f"connection reset while sending {headers['x-api-key']}")


try:
    claude_api.summarize_pdf(PDF, "p", model="m", post=post_boom)
    check("통신 예외는 ClaudeError 로", False)
except claude_api.ClaudeError as exc:
    check("통신 예외 문구에 키가 없음", FAKE_KEY not in str(exc), str(exc))
check("safe.scrub 이 환경변수의 키를 지움",
      FAKE_KEY not in safe.scrub(f"x {FAKE_KEY} y") and "***" in safe.scrub(f"x {FAKE_KEY} y"))
OTHER = "sk-ant-" + "api03-" + "Z" * 30          # 환경변수에 없는, 모양만 키인 글
check("환경변수에 없어도 sk-ant 모양이면 지움",
      safe.scrub(f"key={OTHER}!") .count("Z" * 30) == 0 and "sk-ant-***" in safe.scrub(f"x {OTHER} y"),
      safe.scrub(f"x {OTHER} y"))
check("ANTHROPIC_API_KEY 가 지울 이름 목록에", "ANTHROPIC_API_KEY" in safe.SECRET_ENVS)

print("\n=== 쪽수 자르기 · 글 없는 응답 (2026-11-12 첫 실제 실행) ===")
from pypdf import PdfReader  # noqa: E402
import io  # noqa: E402

big = make_pdf(45)
cut, total, sent = claude_api.trim_pdf(big, 30)
check("45쪽 → 앞 30쪽", (total, sent) == (45, 30) and len(PdfReader(io.BytesIO(cut)).pages) == 30)
same, total, sent = claude_api.trim_pdf(PDF, 30)
check("짧으면 그대로", same == PDF and (total, sent) == (3, 3))
try:
    claude_api.trim_pdf(b"%PDF-1.4 broken", 30)
    check("깨진 PDF 는 보내지 않음", False)
except claude_api.ClaudeError:
    check("깨진 PDF 는 보내지 않음", True)
seen.clear()
got, usage = claude_api.summarize_pdf(big, "p", model="m", max_pages=10, post=fake_post)
sent_pdf = base64.standard_b64decode(seen["body"]["messages"][0]["content"][0]["source"]["data"])
check("보내는 PDF 가 실제로 잘려 있음", len(PdfReader(io.BytesIO(sent_pdf)).pages) == 10
      and usage["pages_total"] == 45 and usage["pages_sent"] == 10)


def post_thinking_only(url, json, headers, timeout):  # noqa: A002
    return {"type": "message", "content": [{"type": "thinking", "thinking": "", "signature": "x"}],
            "usage": {"input_tokens": 150000, "output_tokens": 700}, "stop_reason": "max_tokens"}


try:
    claude_api.summarize_pdf(PDF, "p", model="m", post=post_thinking_only)
    check("생각만 하고 끝난 응답은 실패", False)
except claude_api.ClaudeError as exc:
    check("생각만 하고 끝난 응답은 실패 — 이유를 적음",
          "stop_reason=max_tokens" in str(exc) and "thinking" in str(exc) and "150,000" in str(exc),
          str(exc))


def post_cut(url, json, headers, timeout):  # noqa: A002
    return {"type": "message", "content": [{"type": "text", "text": "핵심 주장\n- 가격이"}],
            "usage": {"input_tokens": 30000, "output_tokens": 3000}, "stop_reason": "max_tokens"}


tries = []


def post_no_effort(url, json, headers, timeout):  # noqa: A002
    tries.append("output_config" in json)
    if "output_config" in json:
        return {"type": "error", "error": {"type": "invalid_request_error",
                                           "message": "output_config.effort: not supported"}}
    return fake_post(url, json, headers, timeout)


got, _u = claude_api.summarize_pdf(PDF, "p", model="m", post=post_no_effort)
check("effort 칸을 거절하면 그 칸만 빼고 한 번 더", tries == [True, False] and got == SUMMARY)

try:
    claude_api.summarize_pdf(PDF, "p", model="m", post=post_cut)
    check("잘린 요약은 저장하지 않게 실패로", False)
except claude_api.ClaudeError as exc:
    check("잘린 요약은 저장하지 않게 실패로", "잘렸습니다" in str(exc))

old_cut = {"summary": "핵심 주장\n- 3Q26 실적은", "output_tokens": 700, "input_tokens": 33532}
new_ok = {"summary": "s", "output_tokens": 700, "pages_sent": 12, "pages_total": 12}
check("첫 실행의 잘린 요약은 다시 요약 대상", rs.needs_redo(old_cut) and not rs.needs_redo(new_ok)
      and not rs.needs_redo({"summary": "s", "output_tokens": 596}))
redo = rs.targets({"삼성": [rep("company", "97245")]}, {"company:97245": old_cut}, 5, 9)
check("다시 요약 대상이 목록에 들어감", [rs.key_of(r) for r in redo] == ["company:97245"])
e = rs.entry(rep("industry", "1"), SUMMARY, "m", {"pages_total": 45, "pages_sent": 30})
check("저장 항목에 쪽수", e["pages_total"] == 45 and e["pages_sent"] == 30)
check("설정 — 쪽수 · 입력 토큰 상한", 5 <= config.SUMMARY_MAX_PAGES <= 60
      and 100_000 <= config.SUMMARY_MAX_INPUT_TOKENS <= 2_000_000)
check("지시문 — 업종 비중 의견도 옮기지 않게", "비중" in rs.PROMPT)
check("requirements 에 pypdf", "pypdf" in pathlib.Path("requirements.txt").read_text(encoding="utf-8"))

print("\n=== 이름 · 저장 · 대상 고르기 ===")
check("이름 — 산업 / 종목", rs.key_of(rep("industry", "46967")) == "industry:46967"
      and rs.key_of(rep("company", "97570")) == "company:97570")
check("번호가 없으면 이름도 없음", rs.key_of(rep("industry", "")) == "")
items = {"industry:1": rs.entry(rep("industry", "1"), SUMMARY, "m", {"input_tokens": 5, "output_tokens": 2})}
back = rs.parse(rs.dump(items))
check("저장했다 읽으면 그대로", back["industry:1"]["summary"] == items["industry:1"]["summary"]
      and back["industry:1"]["input_tokens"] == 5)
check("깨진 파일은 빈 묶음", rs.parse("{oops") == {} and rs.parse("[]") == {} and rs.parse("") == {})
check("굵은 표시 · 빈 줄 정리", "**" not in items["industry:1"]["summary"]
      and "\n\n" not in items["industry:1"]["summary"])
bl = rs.blocks(SUMMARY)
check("세 줄머리로 나뉨", [h for h, _ in bl] == ["핵심 주장", "근거 숫자", "가정 · 위험"]
      and bl[1][1] == ["DRAM 계약가 +12% (3쪽)"], str(bl))
many = {f"industry:{i}": {"summary": "s", "at": i} for i in range(rs.KEEP_MAX + 50)}
kept = rs.parse(rs.dump(many))
check("오래된 것부터 버림", len(kept) == rs.KEEP_MAX and "industry:0" not in kept
      and f"industry:{rs.KEEP_MAX + 49}" in kept)

lists = {"산업": [rep("industry", str(i)) for i in range(1, 9)],
         "삼성": [rep("company", str(i)) for i in range(11, 19)],
         "하닉": [rep("company", str(i)) for i in range(21, 29)]}
picked = rs.targets(lists, {}, per_list=5, max_new=7)
check("상한을 넘지 않음", len(picked) == 7)
check("묶음을 번갈아 뽑음", [rs.key_of(r) for r in picked[:3]] ==
      ["industry:1", "company:11", "company:21"], str([rs.key_of(r) for r in picked]))
check("묶음마다 앞의 몇 건만", all(int(r.research_id) % 10 <= 5 for r in rs.targets(lists, {}, 5, 99))
      and len(rs.targets(lists, {}, 5, 99)) == 15)
done = {"industry:1": {"summary": "s"}, "company:11": {"summary": "s"}}
again = [rs.key_of(r) for r in rs.targets(lists, done, 5, 99)]
check("이미 요약한 것은 다시 보내지 않음", "industry:1" not in again and "company:11" not in again
      and len(again) == 13)
nopdf = {"산업": [rep("industry", "1", pdf=""), rep("industry", "2", pdf="javascript:x"),
                 rep("industry", "3")]}
check("PDF 주소가 없으면 제외", [rs.key_of(r) for r in rs.targets(nopdf, {}, 5, 9)] == ["industry:3"])
dup = {"a": [rep("company", "7")], "b": [rep("company", "7")]}
check("같은 리포트는 한 번만", len(rs.targets(dup, {}, 5, 9)) == 1)
check("설정 — 비용 상한이 있음", 0 < config.SUMMARY_MAX_NEW <= 30 and 0 < config.SUMMARY_PER_LIST <= 20
      and config.SUMMARY_PER_LIST <= config.SEMI_DETAIL_LIMIT,
      "PDF 주소는 상세를 받은 건에만 있습니다")
check("요약 지시문 — 의견·목표주가를 옮기지 않게", "목표주가" in rs.PROMPT and "옮기지 않는다" in rs.PROMPT
      and "쪽수" in rs.PROMPT)

print("\n=== 수집기 단계 ===")
import collect  # noqa: E402


class FakeApp:
    def __init__(self, data):
        self.data = data

    def load_semi_research(self, use_demo):
        return self.data


data = {"industry": [rep("industry", "1"), rep("industry", "2")],
        "stocks": {"005930": [rep("company", "11")], "000660": [rep("company", "21")]}}
calls = {"fetch": [], "sum": 0}


def fetch(url):
    calls["fetch"].append(url)
    return PDF


def summarize(pdf, prompt, *, model, max_pages):
    calls["sum"] += 1
    assert prompt == rs.PROMPT and model == config.SUMMARY_MODEL
    assert max_pages == config.SUMMARY_MAX_PAGES
    return SUMMARY, {"input_tokens": 7000, "output_tokens": 300,
                     "pages_total": 40, "pages_sent": 30}


def missing():
    raise FileNotFoundError("404")


with tempfile.TemporaryDirectory() as out:
    os.environ.pop("ANTHROPIC_API_KEY", None)
    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=summarize,
                                  load_existing=missing)
    check("키가 없으면 건너뜀 (호출 0 · 파일 없음)", r["skipped"] and calls["sum"] == 0
          and not os.path.exists(os.path.join(out, "summaries.json")), str(r))

    os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=summarize,
                                  load_existing=missing)
    path = pathlib.Path(out, "summaries.json")
    saved = rs.parse(path.read_text(encoding="utf-8"))
    check("네 건 요약해 저장", r["new"] == 4 and r["total"] == 4 and len(saved) == 4
          and not r["failed"], str(r))
    check("파일에 키가 없음", FAKE_KEY not in path.read_text(encoding="utf-8"))
    check("삼성전자 · SK하이닉스 묶음 포함", {"company:11", "company:21"} <= set(saved))

    before = calls["sum"]
    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=summarize,
                                  load_existing=lambda: path.read_text(encoding="utf-8"))
    check("다시 돌리면 새로 보내는 것이 없음", r["new"] == 0 and calls["sum"] == before
          and r["total"] == 4, str(r))

    data2 = {"industry": [rep("industry", "3")] + data["industry"], "stocks": data["stocks"]}
    r = collect.summarize_reports(FakeApp(data2), out, fetch=fetch, summarize=summarize,
                                  load_existing=lambda: path.read_text(encoding="utf-8"))
    check("새 리포트만 한 건 더", r["new"] == 1 and calls["sum"] == before + 1 and r["total"] == 5)

with tempfile.TemporaryDirectory() as out:
    n = {"i": 0}

    def flaky(pdf, prompt, *, model, max_pages):
        n["i"] += 1
        if n["i"] == 2:
            raise claude_api.ClaudeError(f"API 오류: overloaded_error — {FAKE_KEY}")
        return SUMMARY, {}

    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=flaky,
                                  load_existing=missing)
    check("한 건 실패해도 나머지는 저장", r["new"] == 3 and len(r["failed"]) == 1, str(r))
    check("실패 문구에 키가 없음", FAKE_KEY not in " ".join(r["failed"]))

with tempfile.TemporaryDirectory() as out:
    n = {"i": 0}

    def no_credit(pdf, prompt, *, model, max_pages):
        n["i"] += 1
        raise claude_api.ClaudeError("API 오류: invalid_request_error — Your credit balance is too low")

    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=no_credit,
                                  load_existing=missing)
    check("잔액 부족이면 첫 건에서 멈춤", n["i"] == 1 and r["new"] == 0 and r["skipped"], str(r))
    check("아무것도 없으면 파일을 만들지 않음",
          not os.path.exists(os.path.join(out, "summaries.json")))

many_data = {"industry": [rep("industry", str(i)) for i in range(1, 11)], "stocks": {}}
with tempfile.TemporaryDirectory() as out:
    n = {"i": 0}

    def empty(pdf, prompt, *, model, max_pages):
        n["i"] += 1
        raise claude_api.ClaudeError("응답에 글이 없습니다 (stop_reason=max_tokens)")

    r = collect.summarize_reports(FakeApp(many_data), out, fetch=fetch, summarize=empty,
                                  load_existing=missing)
    check("연달아 3건 실패하면 멈춤 (돈만 나가지 않게)", n["i"] == 3 and r["skipped"], str(r))

with tempfile.TemporaryDirectory() as out:
    n = {"i": 0}

    def heavy(pdf, prompt, *, model, max_pages):
        n["i"] += 1
        return SUMMARY, {"input_tokens": 250_000, "output_tokens": 500}

    r = collect.summarize_reports(FakeApp(many_data), out, fetch=fetch, summarize=heavy,
                                  load_existing=missing)
    check("입력 토큰 상한에 닿으면 멈춤", n["i"] == 3 and r["new"] == 3 and "상한" in r["skipped"],
          f"{n['i']}건 · {r['skipped']}")

with tempfile.TemporaryDirectory() as out:
    class Broken:
        def load_semi_research(self, use_demo):
            raise RuntimeError("목록 실패")

    old = rs.dump({"industry:9": {"summary": "예전 요약", "at": 5}})
    r = collect.summarize_reports(Broken(), out, fetch=fetch, summarize=summarize,
                                  load_existing=lambda: old)
    kept = rs.parse(pathlib.Path(out, "summaries.json").read_text(encoding="utf-8"))
    check("목록을 못 받아도 지난 요약은 넘김", r["skipped"] and "industry:9" in kept, str(r))

with tempfile.TemporaryDirectory() as out:
    # 워크플로가 git 으로 미리 꺼내 둔 파일이 있으면 그것을 이어 씁니다
    pathlib.Path(out, "summaries.json").write_text(
        rs.dump({"industry:1": {"summary": "예전 요약", "at": 5}}), encoding="utf-8")
    before = calls["sum"]
    r = collect.summarize_reports(FakeApp(data), out, fetch=fetch, summarize=summarize)
    kept = rs.parse(pathlib.Path(out, "summaries.json").read_text(encoding="utf-8"))
    check("미리 꺼내 둔 파일을 이어 씀 (있는 것은 다시 안 보냄)",
          r["new"] == 3 and calls["sum"] == before + 3
          and kept["industry:1"]["summary"] == "예전 요약" and len(kept) == 4, str(r))

src = pathlib.Path("tools/collect.py").read_text(encoding="utf-8")
check("수집기 — 지울 이름 목록에 키", '"ANTHROPIC_API_KEY"' in src.split("SECRET_ENVS")[1][:200])
wf = pathlib.Path("tools/collect_workflow.yml").read_text(encoding="utf-8")
check("워크플로 — 지난 요약을 먼저 꺼냄 (수집보다 앞)",
      "git show FETCH_HEAD:summaries.json" in wf
      and wf.index("git show FETCH_HEAD:summaries.json") < wf.index("tools/collect.py --out"))
check("워크플로 — Secrets 에서 키를 넘김",
      "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in wf)

print("\n=== 화면 ===")
summaries = {"industry:1": rs.entry(rep("industry", "1"), SUMMARY, "claude-haiku-5-5")}
r1 = rep("industry", "1", title="<b>반도체</b> 점검")
r1.preview = "본문 앞부분"
r2 = rep("industry", "2")
r2.preview = "두 번째 미리보기"
html = ui.render_report_cards([r1, r2], summaries=summaries)
check("요약이 있는 카드에 'AI 요약' 표시", html.count("rp-ai") == 1 and "AI 요약 · claude-haiku-5-5" in html)
part = {"industry:1": {**summaries["industry:1"], "pages_total": 84, "pages_sent": 30}}
check("일부만 읽었으면 카드에 적음",
      "앞 30쪽만 읽음 (전체 84쪽)" in ui.render_report_cards([r1], summaries=part)
      and "쪽만 읽음" not in html)
check("요약이 있으면 미리보기 대신", "본문 앞부분" not in html and "두 번째 미리보기" in html)
check("줄머리와 항목", '<div class="ai-h">근거 숫자</div>' in html
      and "<li>DRAM 계약가 +12% (3쪽)</li>" in html)
evil = {"industry:1": {"summary": "핵심 주장\n- <script>alert(1)</script>", "model": "<i>m</i>"}}
html = ui.render_report_cards([r1], summaries=evil)
check("요약 글은 HTML 로 해석하지 않음", "<script>" not in html and "<i>m</i>" not in html)
check("요약이 없으면 예전 그대로", ui.render_report_cards([r1, r2]) == ui.render_report_cards([r1, r2], summaries={}))
dsum = demo.demo_report_summaries()
ddata = demo.demo_semi_research()
keys = {rs.key_of(r) for r in ddata["industry"]} | {
    rs.key_of(r) for v in ddata["stocks"].values() for r in v}
check("데모 요약이 데모 리포트에 붙음", dsum and set(dsum) <= keys
      and all("(데모)" in v["summary"] for v in dsum.values()))
check("요약 대상은 세 묶음뿐", [c for c, _ in semi_research.STOCKS] == ["005930", "000660"])

app_src = pathlib.Path("app.py").read_text(encoding="utf-8")
check("앱 — 요약 파일을 읽는 함수 · 받은 시각 이름",
      "def load_report_summaries(" in app_src and '"load_report_summaries": "AI 요약"' in app_src)
check("앱은 Claude API 를 부르지 않음", "claude_api" not in app_src and "api.anthropic.com" not in app_src)
check("카드에 요약을 넘김", "render_report_cards(picked, limit=20, summaries=summaries)" in app_src)

print("\n=== 반도체 리포트 화면을 실제로 그려 본다 (가짜 st) ===")
import ast  # noqa: E402
import datetime as dt  # noqa: E402
import html as _html  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from sources import research  # noqa: E402

_fn = [n for n in ast.parse(app_src).body
       if isinstance(n, ast.FunctionDef) and n.name == "render_semi_research_tab"]


class _Exp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSt:
    def __init__(self, choice=None):
        self.md, self.choice = [], choice

    def markdown(self, html, **k):
        self.md.append(html)

    def segmented_control(self, label, keys, default=None, key=None, format_func=None,
                          label_visibility=None):
        [format_func(k) for k in keys]
        return self.choice or default

    def expander(self, label, expanded=False):
        return _Exp()


def run_tab(summ, choice=None, data=None):
    st = FakeSt(choice)

    def load_summ(use_demo):
        if isinstance(summ, Exception):
            raise summ
        return summ

    ns = {"st": st, "ui": ui, "config": config, "semi_research": semi_research,
          "report_summary": rs, "research": research, "dt": dt, "KST": ZoneInfo("Asia/Seoul"),
          "_esc_plain": lambda t: _html.escape(str(t), quote=True),
          "load_semi_research": lambda use_demo: data or ddata,
          "load_report_summaries": load_summ}
    exec(compile(ast.Module(body=_fn, type_ignores=[]), "app.py", "exec"), ns)
    ns["render_semi_research_tab"](True)
    return "".join(st.md)


_n_shown = sum(1 for r in ddata["industry"] + [x for v in ddata["stocks"].values() for x in v]
               if rs.key_of(r) in dsum)
page = run_tab({"items": dsum, "made": 1_794_450_000, "note": ""})
check("요약이 있으면 카드에 붙고 안내에 건수 · 만든 때", page.count('class="rp-ai"') == 2
      and f"카드 {_n_shown}건" in page and "마지막으로 만든 때" in page,
      str(page.count('class="rp-ai"')))
check("숫자를 원문과 맞춰 보라고 적는다", "AI 는 숫자를 잘못 옮길 수 있습니다" in page)
page = run_tab({"items": dsum, "made": 0, "note": ""}, choice="005930")
check("삼성전자 보기에도 요약", page.count('class="rp-ai"') == 2)
page = run_tab({"items": {}, "made": 0, "note": "아직 요약 파일이 없습니다"})
check("요약이 없으면 켜는 방법을 안내", 'class="rp-ai"' not in page
      and "ANTHROPIC_API_KEY" in page and "아직 요약 파일이 없습니다" in page
      and "rp-card" in page)
page = run_tab(RuntimeError("timeout"))
check("요약 파일을 못 받아도 리포트는 보인다", "rp-card" in page and "받지 못했습니다" in page)

os.environ.pop("ANTHROPIC_API_KEY", None)
print("\n" + ("전부 통과" if not FAILURES else f"실패 {len(FAILURES)}건: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
