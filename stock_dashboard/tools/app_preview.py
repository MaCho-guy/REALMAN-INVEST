"""앱 코드로 그리는 정적 프리뷰 (2026-11-19).

    python -m tools.app_preview                    # app_preview.html (데모 값)
    python -m tools.app_preview --data ../data     # 수집기 파일(JSON)은 그 폴더의 실제 값
    python -m tools.app_preview --out x.html

tools/preview.py 와 무엇이 다른가
    preview.py 는 화면을 **따로** 조립합니다 (패널 함수 1,800줄). 그래서 앱에 화면이
    생겨도 프리뷰에는 없고(후보 · 근거 · 차트 조건 · 실험 · 아침 브리핑), CSS 도 일부만
    실었습니다. 이 도구는 `app.render_body` 를 가짜 스트림릿(tools/fakest.py) 위에서
    **그대로** 돌려 받아 적습니다 — 화면 조립 코드가 한 벌입니다.

한계 (프리뷰에 적혀 나옵니다)
    · 위젯은 눌리지 않는 그림입니다. 메뉴 · 안쪽 탭 · 요약 카드 · 종목 고르기 · 보기 전환만
      이 파일의 스크립트가 미리 그려 둔 화면으로 바꿔 줍니다.
    · 스트림릿이 만드는 DOM 에 기대는 CSS(내비 버튼 색 · 간격)는 여기서 확인되지 않습니다.
    · --data 를 줘도 시세 · 공시 · 뉴스는 받지 않습니다 (데모 값). 수집기 파일로 그리는
      화면(FILE_SCREENS)만 실제 값입니다.
"""
from __future__ import annotations

import html as _html
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from tools import fakest  # noqa: E402

#: 수집기 파일만으로 그리는 화면 — --data 가 있으면 데모가 아니라 그 파일로 그립니다
FILE_SCREENS = ("picks", "basis", "timing", "screener", "paper")

#: 화면 안의 '보기' 를 프리뷰에서도 바꿔 볼 수 있게 미리 그려 둘 것 — {화면: (세션 key 틀, 값들)}
VIEW_VARIANTS = {
    "timing": ("chart_view2_{m}", ("chart",)),
    "paper": ("lab_view_{m}", ("test",)),
}

SHELL_CSS = """
  body { margin: 0; background: var(--dash-page); color: var(--dash-ink);
         font-family: system-ui, -apple-system, "Segoe UI", "Apple SD Gothic Neo", sans-serif; }
  .pv-wrap { max-width: 1240px; margin: 0 auto; padding: 14px 16px 60px; }
  .pv-banner { font-size: .8rem; background: #fff7df; border: 1px solid #e6cf8a;
    border-radius: 8px; padding: 7px 12px; margin: 0 0 12px; line-height: 1.5; }
  .pv-mkts { display: flex; gap: 6px; margin: 0 0 10px; }
  .pv-mkt, .pv-menu { font: inherit; cursor: pointer; border-radius: 999px;
    border: 1px solid var(--dash-border); background: var(--dash-surface);
    padding: 5px 16px; font-weight: 650; color: var(--dash-ink); }
  .pv-mkt[aria-pressed="true"] { background: var(--dash-accent); color: #fff;
    border-color: var(--dash-accent); }
  .pv-shell { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 18px;
    align-items: start; }
  .pv-side { background: var(--dash-surface); border: 1px solid var(--dash-border);
    border-radius: var(--r-card); padding: 10px 8px; display: grid; gap: 6px;
    position: sticky; top: 10px; }
  .pv-menu { border-radius: var(--r-inner); text-align: left; padding: 9px 12px;
    font-size: var(--fs-4); font-weight: 500; background: var(--t-tint);
    border: 1px solid transparent; }
  .pv-menu:hover { background: var(--t-mid); border-color: var(--t-line); }
  .pv-menu[aria-current="true"] { background: var(--t-mid); border: 1.5px solid var(--t-line);
    font-weight: 750; }
  [hidden] { display: none !important; }
  /* 가짜 위젯 — 눌리지 않는 그림 */
  .fs-seg { display: inline-flex; flex-wrap: wrap; gap: 0; margin: 2px 0 10px;
    border: 1px solid var(--dash-border); border-radius: 8px; overflow: hidden;
    background: var(--dash-surface); }
  .fs-seg-i { padding: 6px 15px; font-size: var(--fs-4); font-weight: 600;
    border-right: 1px solid var(--dash-border); color: var(--dash-ink-2); }
  .fs-seg-i:last-child { border-right: 0; }
  .fs-seg-i.on { background: var(--grp-mid, var(--dash-raised)); color: var(--dash-ink);
    font-weight: 750; }
  .fs-seg.live .fs-seg-i { cursor: pointer; }
  .fs-seg.live .fs-seg-i:hover { background: var(--grp-tint, var(--dash-raised)); }
  .fs-toggle { display: flex; align-items: center; gap: 8px; font-size: var(--fs-3);
    color: var(--dash-ink-2); margin: 6px 0; }
  .fs-toggle i { width: 30px; height: 16px; border-radius: 999px; background: #c9cdd3;
    position: relative; flex: 0 0 auto; }
  .fs-toggle i::after { content: ""; position: absolute; top: 2px; left: 2px; width: 12px;
    height: 12px; border-radius: 50%; background: #fff; }
  .fs-toggle.on i { background: var(--dash-accent); }
  .fs-toggle.on i::after { left: 16px; }
  .fs-select { display: inline-block; border: 1px solid var(--dash-border); border-radius: 8px;
    background: var(--dash-surface); padding: 6px 12px; font-size: var(--fs-3); margin: 2px 0 8px; }
  .fs-btn { display: inline-block; border: 1px solid var(--dash-border); border-radius: 8px;
    background: var(--dash-surface); padding: 5px 12px; font-size: var(--fs-3); margin: 2px 4px 6px 0; }
  details.fs-exp { border: 1px solid var(--dash-border); border-radius: 8px;
    background: var(--dash-surface); margin: 6px 0; padding: 0 12px; }
  details.fs-exp > summary { cursor: pointer; padding: 9px 0; font-size: var(--fs-3);
    font-weight: 600; }
  details.fs-exp[open] { padding-bottom: 10px; }
  .fs-box { font-size: var(--fs-3); border-radius: 8px; padding: 8px 12px; margin: 6px 0;
    background: var(--dash-raised); color: var(--dash-ink-2); }
  .fs-warning { background: #fff7df; }
  .fs-code { font-size: var(--fs-2); background: var(--dash-raised); border-radius: 8px;
    padding: 10px 12px; overflow-x: auto; white-space: pre-wrap; }
  @media (max-width: 760px) {
    .pv-wrap { padding: 10px 10px 40px; }
    .pv-shell { grid-template-columns: minmax(0, 1fr); gap: 8px; }
    .pv-side { position: static; display: flex; overflow-x: auto; padding: 6px;
      scrollbar-width: none; }
    .pv-menu { flex: 0 0 auto; padding: 5px 11px; font-size: .82rem; white-space: nowrap; }
    .dash-crumb { display: none; }
  }
"""

SCRIPT = """
(function () {
  var panels = Array.prototype.slice.call(document.querySelectorAll('.pv-panel'));
  var byId = {};
  panels.forEach(function (p) { byId[p.dataset.id] = p; });
  function first(market) {
    var b = document.querySelector('.pv-side[data-market="' + market + '"] .pv-menu');
    return b ? b.dataset.go : null;
  }
  function show(id) {
    if (!byId[id]) { id = id.split('#')[0]; }
    if (!byId[id]) { return; }
    var market = id.split(':')[0];
    panels.forEach(function (p) { p.hidden = p.dataset.id !== id; });
    document.querySelectorAll('.pv-side').forEach(function (n) {
      n.hidden = n.dataset.market !== market;
      if (!n.hidden) { byId[id].querySelector('.pv-navslot').appendChild(n); } });
    document.querySelectorAll('.pv-mkt').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.market === market)); });
    var menu = byId[id].dataset.menu;
    document.querySelectorAll('.pv-menu').forEach(function (b) {
      b.setAttribute('aria-current', String(b.dataset.menu === menu
        && b.closest('.pv-side').dataset.market === market)); });
    try { history.replaceState(null, '', '#' + encodeURIComponent(id)); } catch (e) {}
    window.scrollTo(0, 0);
  }
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    var go = t.closest('[data-go]');
    if (go) { show(go.dataset.go); return; }
    var mk = t.closest('.pv-mkt');
    if (mk) { var f = first(mk.dataset.market); if (f) { show(f); } return; }
    var seg = t.closest('.fs-seg-i');
    if (seg && seg.closest('.fs-seg.live')) {
      var panel = seg.closest('.pv-panel');
      var base = panel.dataset.id.split('#')[0];
      var key = seg.dataset.key, val = seg.dataset.val;
      if (key.indexOf('subnav_') === 0) { show(base.split(':')[0] + ':' + val); return; }
      var want = base + '#' + key + '=' + val;
      show(byId[want] ? want : base);
      return;
    }
    var a = t.closest('a[href^="?"]');
    if (a) {
      var q = new URLSearchParams(a.getAttribute('href').slice(1));
      if (q.get('m') && q.get('s')) {
        ev.preventDefault();
        var id = q.get('m') + ':' + q.get('s');
        if (q.get('c')) { id += '#stock_pick_' + q.get('m') + '=' + q.get('c'); }
        show(id);
      }
    }
  });
  var start = decodeURIComponent((location.hash || '').slice(1));
  show(byId[start] ? start : panels[0].dataset.id);
})();
"""


def _offline(data_dir: str | None) -> None:
    """네트워크를 막습니다. data_dir 가 있으면 저장소 data 브랜치 주소만 그 폴더의 JSON 으로."""
    import urllib.error
    import urllib.request

    import config

    class _Resp(io.BytesIO):
        headers: dict = {}
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    prefix = config.GITHUB_RAW_PREFIX + "data/"

    def urlopen(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if data_dir and url.startswith(prefix):
            name = os.path.basename(url.split("?")[0])
            path = os.path.join(data_dir, name)
            # JSON 만 읽습니다 — 스냅샷(seed.pkl.gz)은 pickle 이라 프리뷰에서 풀지 않습니다
            if name.endswith(".json") and os.path.isfile(path):
                with open(path, "rb") as fh:
                    return _Resp(fh.read())
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        raise urllib.error.URLError("프리뷰는 네트워크를 쓰지 않습니다")

    urllib.request.urlopen = urlopen
    try:
        import requests

        def _no(*a, **k):
            raise requests.exceptions.ConnectionError("프리뷰는 네트워크를 쓰지 않습니다")

        requests.Session.request = _no
        requests.get = _no
        requests.post = _no
    except Exception:  # noqa: BLE001
        pass


def _split(page: str) -> tuple[str, str]:
    """받아 적은 화면 → (머리 부분, 본문). 내비 칸 표식 앞뒤로 가릅니다."""
    mark = '<div class="dash-navmark"></div>'
    at = page.find(mark)
    if at < 0:
        return page, ""
    top, rest = page[:at], page[at + len(mark):]
    # 표식 바로 뒤의 <style>(내비 버튼 색)는 스트림릿 DOM 용이라 버립니다
    rest = re.sub(r"^\s*<style>.*?</style>", "", rest, count=1, flags=re.S)
    # 내비 칸(fs-col)이 표식 앞에서 열리고 뒤에서 닫힙니다 — 가르면서 짝을 맞춥니다
    col = '<div class="fs-col">'
    cut = top.rfind(col)
    if cut >= 0 and "</div>" in rest:
        top = top[:cut] + top[cut + len(col):]
        rest = rest.replace("</div>", "", 1)
    return top, rest


def _scope(body: str, pid: str) -> str:
    """화면마다 넣는 :root 변수(묶음 색)를 그 패널 안으로 가둡니다 — 한 파일에 화면이 여럿."""
    sel = f'.pv-panel[data-id="{_html.escape(pid, quote=True)}"]'
    return body.replace(":root{--grp-", sel + "{--grp-")


def _live(body: str) -> str:
    """안쪽 탭 · 미리 그려 둔 보기 · 종목 고르기는 누를 수 있게 표시합니다."""
    def mark(m):
        key = m.group(1)
        live = key.startswith(("subnav_", "stock_pick_")) or any(
            key.startswith(tpl.split("{")[0]) for tpl, _v in VIEW_VARIANTS.values())
        return f'<div class="fs-seg{" live" if live else ""}" data-key="{key}">'
    return re.sub(r'<div class="fs-seg" data-key="([^"]*)">', mark, body)


def build(data_dir: str | None = None) -> str:
    os.environ.setdefault("DART_API_KEY", "x" * 40)      # 지문 계산만 — 호출은 막혀 있습니다
    os.environ.setdefault("FRED_API_KEY", "x" * 32)
    st = fakest.install()
    import config
    import theme

    _offline(data_dir)
    import app
    import demo as demo_mod

    if data_dir:
        # 수집기 파일로 그리는 화면도 머리의 시세 칸은 데모 값으로 (네트워크를 안 쓰므로)
        app._quotes_fn = lambda: (lambda _use_demo: demo_mod.demo_payload())

    panels: list[str] = []
    navs: list[str] = []
    failed: list[str] = []

    def one(market: str, key: str, gi: int, *, state=None, query=None, suffix="") -> None:
        pid = f"{market}:{key}{suffix}"
        demo = not (data_dir and key in FILE_SCREENS)
        try:
            page = fakest.render_screen(app, st, market, key, demo=demo,
                                        state=state, query=query)
        except Exception as exc:  # noqa: BLE001 - 한 화면이 프리뷰 전체를 막지 않게
            failed.append(f"{pid}: {type(exc).__name__}: {exc}")
            page = (f'<div class="dash-navmark"></div><div class="fs-box fs-error">'
                    f"이 화면을 그리지 못했습니다 — {_html.escape(type(exc).__name__)}</div>")
        top, body = _split(page)
        panels.append(
            f'<section class="pv-panel" data-id="{_html.escape(pid, quote=True)}" '
            f'data-menu="{gi}" hidden>'
            f'<div class="pv-top">{_scope(top, pid)}</div>'
            f'<div class="pv-shell"><div class="pv-navslot" data-market="{market}"></div>'
            f'<main class="pv-main">{_live(_scope(body, pid))}</main></div></section>')

    for market in config.MARKETS:
        groups = config.tab_groups(market)
        buttons = []
        for gi, (gname, items) in enumerate(groups):
            _k, tint, mid, line = theme.group_tone(gi)
            buttons.append(
                f'<button class="pv-menu" type="button" data-menu="{gi}" '
                f'data-go="{market}:{items[0][0]}" '
                f'style="--t-tint:{tint};--t-mid:{mid};--t-line:{line}">'
                f"{_html.escape(gname)}</button>")
            for key, _label in items:
                one(market, key, gi)
                tpl, values = VIEW_VARIANTS.get(key, ("", ()))
                for val in values:
                    wkey = tpl.format(m=market)
                    one(market, key, gi, state={wkey: val}, suffix=f"#{wkey}={val}")
                if key == "stock":
                    wkey = f"stock_pick_{market}"
                    shown = config.filter_instruments(
                        config.SECTION_WATCHLIST.instruments, market)
                    for inst in shown[1:]:
                        one(market, key, gi, query={"c": inst.symbol},
                            suffix=f"#{wkey}={inst.symbol}")
        navs.append(f'<nav class="pv-side" data-market="{market}" hidden>'
                    + "".join(buttons) + "</nav>")

    banner = (
        '<div class="pv-banner"><b>프리뷰 — 앱 코드(app.render_body)를 그대로 돌려 받아 적은 '
        "정적 화면입니다.</b> 숫자는 데모 값"
        + (" (후보 · 근거 · 차트 조건 · 거래 스크리너 · 실험은 수집기 파일의 실제 값)"
           if data_dir else "")
        + ". 메뉴 · 안쪽 탭 · 요약 카드 · 종목 고르기는 눌러 볼 수 있고, 그 밖의 스위치 · "
          "선택 상자는 그림입니다."
        + (f" <b>그리지 못한 화면 {len(failed)}개.</b>" if failed else "")
        + "</div>")
    mkts = ('<div class="pv-mkts">' + "".join(
        f'<button class="pv-mkt" type="button" data-market="{m}" aria-pressed="false">'
        f"{_html.escape(label)} 시장</button>" for m, label in config.MARKETS.items())
        + "</div>")
    # 내비는 시장마다 한 벌 — 스크립트가 지금 보이는 패널의 자리(pv-navslot)로 옮깁니다
    page = "\n".join((
        "<!DOCTYPE html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>주식 대시보드 — 프리뷰</title>",
        theme.build_css("kr"),
        f"<style>{SHELL_CSS}</style>",
        "</head><body><div class=\"pv-wrap\">",
        banner, mkts,
        '<div class="pv-frame">' + "".join(navs) + "".join(panels) + "</div>",
        "</div>",
        f"<script>{SCRIPT}</script>",
        "</body></html>",
    ))
    if failed:
        print("그리지 못한 화면:", *failed, sep="\n  ", file=sys.stderr)
    return page


def main(argv: list[str]) -> int:
    data_dir = None
    out = "app_preview.html"
    if "--data" in argv:
        data_dir = os.path.abspath(argv[argv.index("--data") + 1])
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    os.chdir(HERE)
    text = build(data_dir)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"{out} 생성 ({len(text):,} bytes) — 화면 {text.count('class=\"pv-panel\"')}개")
    return 0


if __name__ == "__main__":
    code = main(sys.argv)
    sys.stdout.flush()
    os._exit(code)          # 뒤에서 도는 받기 스레드를 기다리지 않습니다
