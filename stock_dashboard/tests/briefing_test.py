"""
증시 브리핑 저장소 테스트 — 네트워크 불필요.

실행:
    cd stock_dashboard
    python tests/briefing_test.py

검증 범위: 파일명 규칙(경로 조작·없는 날짜 거부), 앞머리 분리(본문의 수평선과
           구분), 제목 추측, 최신순 정렬, 오래됨 판정, md/html 혼용.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import briefing_store as bs  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def write(folder: str, name: str, text: str) -> str:
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ──────────────────────────────────────────────────────────────────────────────
print("=== 파일명 규칙 ===")

with tempfile.TemporaryDirectory() as d:
    ok = write(d, "2026-11-10.md", "# 제목\n본문")
    check("YYYY-MM-DD.md 를 읽는다", bs.load_one(ok) is not None)
    check("확장자 html 도 읽는다",
          bs.load_one(write(d, "2026-11-09.html", "<h1>제목</h1>")) is not None)
    check("확장자 htm 도 읽는다",
          bs.load_one(write(d, "2026-11-08.htm", "<h1>x</h1>")) is not None)

    check("날짜 아닌 이름은 거부",
          bs.load_one(write(d, "브리핑.md", "x")) is None)
    check("날짜 형태가 어긋나면 거부",
          bs.load_one(write(d, "2026-11-1.md", "x")) is None)
    check("지원 안 하는 확장자 거부",
          bs.load_one(write(d, "2026-11-07.txt", "x")) is None)
    # 실재하지 않는 날짜 — 파일명 형태는 맞습니다
    check("없는 날짜(2월 30일) 거부",
          bs.load_one(write(d, "2026-02-30.md", "x")) is None)
    check("13월 거부", bs.load_one(write(d, "2026-13-01.md", "x")) is None)

    # 경로 조작 — 정규식이 basename 만 보므로 통과할 수 없습니다
    check("경로 조작 거부", bs.load_one("/tmp/../etc/passwd") is None)
    check("숨김 파일 거부", bs.load_one(write(d, ".2026-11-10.md", "x")) is None)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 앞머리 분리 ===")

meta, body = bs.split_front_matter(
    "---\ntitle: 11월 2주 증시 브리핑\nsources:\n  - https://a\n  - https://b\n---\n\n본문입니다\n")
check("title 을 읽는다", meta.get("title") == "11월 2주 증시 브리핑", str(meta.get("title")))
check("sources 목록을 읽는다", meta.get("sources") == ["https://a", "https://b"],
      str(meta.get("sources")))
check("본문에 앞머리가 섞이지 않는다", body.strip() == "본문입니다", repr(body))

meta, body = bs.split_front_matter("# 제목\n\n본문\n\n---\n\n다음 절\n")
check("앞머리가 없으면 원문 그대로", meta == {} and body.startswith("# 제목"))
check("본문 중간의 수평선을 앞머리로 보지 않는다", "다음 절" in body, repr(body[-20:]))

# 닫는 --- 가 없는 경우 — 글이 통째로 사라지면 안 됩니다
meta, body = bs.split_front_matter("---\ntitle: 미완성\n\n본문이 이어집니다\n")
check("닫는 구분선이 없으면 전부 본문", meta == {} and "본문이 이어집니다" in body)

meta, body = bs.split_front_matter("")
check("빈 문자열도 처리", meta == {} and body == "")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 제목 추측 ===")

with tempfile.TemporaryDirectory() as d:
    bf = bs.load_one(write(d, "2026-11-10.md", "# 마크다운 제목\n\n본문"))
    check("마크다운 # 줄을 제목으로", bf.title == "마크다운 제목", bf.title)

    bf = bs.load_one(write(d, "2026-11-09.md", "앞머리 없는 첫 줄\n\n본문"))
    check("제목 표시가 없으면 첫 줄", bf.title == "앞머리 없는 첫 줄", bf.title)

    bf = bs.load_one(write(d, "2026-11-08.html",
                           "<html><title>타이틀</title><h1>H1 제목</h1></html>"))
    check("HTML 은 h1 을 우선", bf.title == "H1 제목", bf.title)

    bf = bs.load_one(write(d, "2026-11-07.html", "<html><title>타이틀만</title></html>"))
    check("h1 이 없으면 title 태그", bf.title == "타이틀만", bf.title)

    bf = bs.load_one(write(d, "2026-11-06.md",
                           "---\ntitle: 앞머리 제목\n---\n# 본문 제목\n"))
    check("앞머리 title 이 본문보다 우선", bf.title == "앞머리 제목", bf.title)

    bf = bs.load_one(write(d, "2026-11-05.md", "   \n\n  \n"))
    check("내용이 없으면 경고", bool(bf.warnings), str(bf.warnings))

    long_title = "가" * 100
    bf = bs.load_one(write(d, "2026-11-04.md", f"---\ntitle: {long_title}\n---\n본문"))
    check("긴 제목은 요약용으로 자른다",
          len(bf.short_title) <= bs.TITLE_MAX and bf.short_title.endswith("…"),
          f"{len(bf.short_title)}자")
    check("원래 제목은 보존", bf.title == long_title)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 정렬과 오래됨 ===")

with tempfile.TemporaryDirectory() as d:
    today = dt.date.today()
    for off, name in ((0, "오늘"), (3, "3일전"), (10, "10일전"), (1, "어제")):
        day = (today - dt.timedelta(days=off)).isoformat()
        write(d, f"{day}.md", f"# {name}\n본문")

    items = bs.load_all(d)
    check("4편을 읽는다", len(items) == 4, str(len(items)))
    check("최신이 맨 앞", items[0].title == "오늘", items[0].title)
    check("날짜 내림차순",
          [b.date for b in items] == sorted((b.date for b in items), reverse=True))

    check("최신 한 편만 가져오기", bs.latest(d).title == "오늘")
    check("limit 이 적용된다", len(bs.load_all(d, limit=2)) == 2)

    by_title = {b.title: b for b in items}
    check("오늘은 age 0", by_title["오늘"].age_days == 0)
    check("오늘 라벨", by_title["오늘"].age_label == "오늘")
    check("어제 라벨", by_title["어제"].age_label == "어제")
    check("3일 전 라벨", by_title["3일전"].age_label == "3일 전")

    check("7일 이내는 오래되지 않음", not by_title["3일전"].is_stale)
    check("10일 전은 오래됨", by_title["10일전"].is_stale)
    check("오래됨 기준이 분석 문서(90일)보다 짧다", bs.STALE_DAYS < 90,
          f"{bs.STALE_DAYS}일")


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 폴더가 없을 때 ===")

check("없는 폴더는 빈 목록", bs.load_all("/tmp/__없는폴더__") == [])
check("없는 폴더의 latest 는 None", bs.latest("/tmp/__없는폴더__") is None)

with tempfile.TemporaryDirectory() as d:
    check("빈 폴더도 빈 목록", bs.load_all(d) == [])
    write(d, "readme.txt", "관계없는 파일")
    check("관계없는 파일만 있으면 빈 목록", bs.load_all(d) == [])


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== md / html 혼용 ===")

with tempfile.TemporaryDirectory() as d:
    write(d, "2026-11-10.md", "# 마크다운\n본문")
    write(d, "2026-11-09.html", "<h1>HTML</h1><p>본문</p>")
    items = bs.load_all(d)
    fmts = {b.fmt for b in items}
    check("두 형식이 함께 읽힌다", fmts == {"md", "html"}, str(fmts))
    html_one = [b for b in items if b.fmt == "html"][0]
    check("html 플래그", html_one.is_html)
    md_one = [b for b in items if b.fmt == "md"][0]
    check("md 는 html 아님", not md_one.is_html)

    # HTML 에는 앞머리를 적용하지 않습니다 — 아티팩트 원문을 손대면 안 됩니다
    write(d, "2026-11-08.html", "---\ntitle: 무시됨\n---\n<h1>진짜</h1>")
    bf = bs.load_one(os.path.join(d, "2026-11-08.html"))
    check("HTML 본문은 앞머리 분리를 하지 않는다",
          "---" in bf.body and bf.title == "진짜", bf.title)


print("\n=== 사용 안내문 ===")
tpl = bs.example_file()
check("오늘 날짜가 들어간 경로를 보여준다",
      dt.date.today().isoformat() in tpl and "briefings/" in tpl)
check("앞머리 생략 가능함을 알려준다", "생략" in tpl)


# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 출처 링크 스킴 ===")

with tempfile.TemporaryDirectory() as d:
    write(d, "2026-11-10.md",
          "---\nsources:\n  - https://ok.example/a\n  - http://ok.example/b\n"
          "  - javascript:alert(1)\n  - JAVASCRIPT:alert(2)\n"
          "  - data:text/html,<script>x</script>\n  - /상대경로\n---\n본문")
    bf = bs.load_one(os.path.join(d, "2026-11-10.md"))
    check("http/https 만 남는다", bf.sources == ["https://ok.example/a",
                                               "http://ok.example/b"],
          str(bf.sources))
    check("javascript: 제외", not any("javascript" in u.lower() for u in bf.sources))
    check("대문자 JAVASCRIPT: 도 제외",
          not any("JAVASCRIPT" in u for u in bf.sources))
    check("data: 제외", not any(u.startswith("data:") for u in bf.sources))
    check("상대경로 제외", not any(u.startswith("/") for u in bf.sources))
    check("제외 사실을 경고로 남긴다",
          any("출처" in w and "제외" in w for w in bf.warnings), str(bf.warnings))

    write(d, "2026-11-09.md", "---\nsources:\n  - https://only.example\n---\n본문")
    bf2 = bs.load_one(os.path.join(d, "2026-11-09.md"))
    check("전부 정상이면 경고 없음", not bf2.warnings, str(bf2.warnings))


print("\n" + "=" * 56)
if FAILURES:
    print(f"실패 {len(FAILURES)}건: {', '.join(FAILURES)}")
    sys.exit(1)
print("전부 통과")
