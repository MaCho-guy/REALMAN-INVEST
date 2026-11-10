"""
================================================================================
증시 브리핑 저장소 — 다른 대화에서 쓴 글을 대시보드로 가져옵니다.
================================================================================

analysis_store 와 왜 다른가:

  analysis_store : 종목별    analysis/<티커>/decoder.html  (meta.json 필요)
  briefing_store : 날짜별    briefings/2026-11-10.md       (meta 불필요)

브리핑은 종목이 아니라 **시장 단위**이고 날짜가 본질입니다. 그래서 날짜를
**파일명에서** 읽습니다. meta.json 에 날짜를 따로 적게 하면, 파일을 복사해
새 브리핑을 쓸 때 날짜 고치는 걸 잊습니다 — 그러면 지난주 글이 최신으로
올라옵니다. 파일명은 잊을 수가 없습니다.

────────────────────────────────────────────────────────────────────────────────
넣는 방법

  briefings/2026-11-10.md     ← 마크다운
  briefings/2026-11-07.html   ← HTML (아티팩트에서 복사한 경우)

둘 다 받습니다. 다른 대화에서 쓴 글이 마크다운이면 그대로, 아티팩트를
내려받은 것이면 HTML 로 두면 됩니다. 확장자로 판별합니다.

앞머리(front matter)는 **선택**입니다. 없으면 본문 첫 제목 줄을 제목으로
씁니다:

    ---
    title: 11월 2주 증시 브리핑
    sources:
      - https://www.federalreserve.gov/...
      - https://ir.micron.com/...
    ---

    본문...

YAML 파서를 쓰지 않습니다. requirements.txt 에 의존성을 더하지 않으려는
것이고, 필요한 건 두 필드뿐입니다.

────────────────────────────────────────────────────────────────────────────────
오래됨 기준

분석 문서는 90일이지만 브리핑은 7일입니다. 시장 브리핑은 한 주가 지나면
현재 상태를 설명하지 못합니다. 오래된 브리핑을 최신인 것처럼 보여주는 것이
아예 안 보여주는 것보다 나쁩니다.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field

#: 파일명이 이 형태여야 읽습니다. 경로 조작과 날짜 오류를 동시에 막습니다 —
#: '../../etc/passwd' 는 이 정규식을 통과하지 못합니다.
NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.(md|markdown|html|htm)$")

#: 이 일수를 넘으면 '오래됨'
STALE_DAYS = 7

#: 요약 탭 한 줄에 쓸 제목 최대 길이
TITLE_MAX = 60

#: 출처 링크로 허용하는 스킴. 본인이 쓴 파일이라 위험은 낮지만,
#: HTML 이스케이프는 `javascript:` 를 막지 못합니다 — 따옴표를 바꿔도
#: 스킴은 그대로 살아서 href 에 들어갑니다. 읽는 지점에서 걸러냅니다.
ALLOWED_SCHEMES = ("http://", "https://")


@dataclass
class Briefing:
    """브리핑 한 편."""

    date: str                    # YYYY-MM-DD (파일명에서)
    title: str = ""
    body: str = ""
    fmt: str = "md"              # md | html
    sources: list[str] = field(default_factory=list)
    path: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def age_days(self) -> int | None:
        try:
            made = dt.date.fromisoformat(self.date)
        except ValueError:
            return None
        return (dt.date.today() - made).days

    @property
    def is_stale(self) -> bool:
        age = self.age_days
        return age is not None and age > STALE_DAYS

    @property
    def is_html(self) -> bool:
        return self.fmt == "html"

    @property
    def short_title(self) -> str:
        """요약 탭 한 줄용. 길면 자릅니다."""
        t = self.title or "제목 없음"
        if len(t) <= TITLE_MAX:
            return t
        return t[:TITLE_MAX - 1] + "…"

    @property
    def age_label(self) -> str:
        age = self.age_days
        if age is None:
            return ""
        if age == 0:
            return "오늘"
        if age == 1:
            return "어제"
        return f"{age}일 전"


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    """앞머리와 본문을 분리합니다. 앞머리가 없으면 ({}, 원문) 입니다.

    `---` 로 시작하지 않으면 손대지 않습니다 — 마크다운에서 `---` 는
    수평선이기도 해서, 본문 중간의 `---` 를 앞머리로 착각하면 글이 잘립니다.
    그래서 **첫 줄에 있을 때만** 앞머리로 봅니다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        # 닫는 `---` 가 없습니다. 앞머리로 보지 않고 전부 본문으로 둡니다.
        return {}, text

    meta: dict[str, object] = {}
    key = ""
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip():
            continue
        # 목록 항목 ("  - https://...")
        if line.lstrip().startswith("- ") and key:
            item = line.lstrip()[2:].strip()
            if item:
                meta.setdefault(key, [])
                if isinstance(meta[key], list):
                    meta[key].append(item)
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        key = k.strip().lower()
        val = v.strip()
        meta[key] = val if val else []

    return meta, "\n".join(lines[end + 1:]).lstrip("\n")


def _title_from_body(body: str, fmt: str) -> str:
    """본문에서 제목을 추측합니다. 앞머리에 title 이 없을 때만 씁니다."""
    if fmt == "html":
        m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        if m:
            return m.group(1).strip()
        return ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            # 첫 비어 있지 않은 줄 — 제목 표시가 없으면 이걸 씁니다
            return stripped[:TITLE_MAX]
    return ""


def load_one(path: str) -> Briefing | None:
    """파일 하나를 읽습니다. 파일명 규칙에 안 맞으면 None 입니다."""
    name = os.path.basename(path)
    m = NAME_RE.match(name)
    if not m:
        return None

    y, mo, d, ext = m.groups()
    try:
        date = dt.date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        # 2026-02-30 같은 날짜. 파일명 형태는 맞지만 실재하지 않습니다.
        return None

    fmt = "html" if ext in ("html", "htm") else "md"
    bf = Briefing(date=date, fmt=fmt, path=path)

    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        bf.warnings.append(f"읽기 실패: {exc}")
        return bf

    if not text.strip():
        bf.warnings.append("파일이 비어 있습니다.")
        return bf

    # HTML 에는 앞머리를 쓰지 않습니다 — 아티팩트에서 그대로 복사해 넣는
    # 용도라 손대지 않는 게 맞습니다.
    if fmt == "md":
        meta, body = split_front_matter(text)
    else:
        meta, body = {}, text

    bf.body = body
    title = meta.get("title")
    bf.title = str(title).strip() if isinstance(title, str) and title.strip() \
        else _title_from_body(body, fmt)

    raw_src: list[str] = []
    src = meta.get("sources")
    if isinstance(src, list):
        raw_src = [str(s).strip() for s in src if str(s).strip()]
    elif isinstance(src, str) and src.strip():
        raw_src = [src.strip()]

    bf.sources = [u for u in raw_src
                  if u.lower().startswith(ALLOWED_SCHEMES)]
    dropped = len(raw_src) - len(bf.sources)
    if dropped:
        bf.warnings.append(
            f"출처 {dropped}개를 제외했습니다 — http:// 또는 https:// 로 "
            "시작하는 주소만 링크로 만듭니다.")

    return bf


def load_all(base_dir: str, *, limit: int = 30) -> list[Briefing]:
    """briefings/ 를 읽어 **최신순**으로 돌려줍니다.

    폴더가 없으면 빈 목록입니다 — 브리핑을 아직 안 넣은 상태가 정상이고
    오류가 아닙니다.
    """
    if not os.path.isdir(base_dir):
        return []
    out: list[Briefing] = []
    try:
        names = os.listdir(base_dir)
    except OSError:
        return []
    for name in names:
        bf = load_one(os.path.join(base_dir, name))
        if bf is not None:
            out.append(bf)
    out.sort(key=lambda b: b.date, reverse=True)
    return out[:limit]


def latest(base_dir: str) -> Briefing | None:
    items = load_all(base_dir, limit=1)
    return items[0] if items else None


def example_file() -> str:
    """브리핑 파일을 처음 만들 때 붙여넣을 틀."""
    today = dt.date.today().isoformat()
    return (
        f"briefings/{today}.md 로 저장하세요.\n\n"
        "---\n"
        "title: 제목을 여기에\n"
        "sources:\n"
        "  - https://출처1\n"
        "  - https://출처2\n"
        "---\n\n"
        "본문을 마크다운으로 쓰세요.\n"
        "앞머리(--- 사이)는 생략해도 되고, 그러면 첫 제목 줄이 제목이 됩니다.\n"
    )
