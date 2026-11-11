"""
정의되지 않은 이름 검사 — 스트림릿 없이 app.py 의 오타를 잡습니다.

tools/xref 는 `모듈.속성` 만 봅니다. `render_sectr_heat_tab()` 처럼
**함수 이름 자체**를 틀리면 못 잡고, 그 줄이 실행돼야(= 그 탭을 눌러야)
NameError 로 드러납니다. 샌드박스에는 스트림릿이 없어서 앱을 돌려 볼 수도
없습니다. 그래서 이름이 어디선가 정의돼 있는지를 정적으로 봅니다.

중첩 함수(클로저)는 바깥 함수의 변수를 읽을 수 있으므로 **바깥 범위까지**
따라 올라가며 찾습니다.

    python -m tools.names            app.py 검사
    python -m tools.names a.py b.py  여러 파일
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}


def _bound_in(node: ast.AST) -> set[str]:
    """이 범위(함수 본문 또는 모듈)에서 묶이는 이름. 중첩 함수 안은 제외."""
    names: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = node.args
        for arg in a.posonlyargs + a.args + a.kwonlyargs:
            names.add(arg.arg)
        if a.vararg:
            names.add(a.vararg.arg)
        if a.kwarg:
            names.add(a.kwarg.arg)
    body = node.body if hasattr(node, "body") and isinstance(node.body, list) \
        else [node.body] if isinstance(node, ast.Lambda) else []

    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
            # 데코레이터·기본값은 바깥 범위에서 평가되지만 이름을 묶지 않습니다
            continue
        if isinstance(n, ast.Lambda):
            continue
        # 컴프리헨션 변수는 파이썬 3 에서 **밖으로 새지 않습니다.**
        # [y for y in xs] 다음 줄의 y 는 NameError 입니다. 다만 := 로
        # 묶은 이름은 바깥 범위로 나가므로 그것만 줍습니다.
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp,
                          ast.GeneratorExp)):
            for w in ast.walk(n):
                if isinstance(w, ast.NamedExpr) and isinstance(w.target,
                                                               ast.Name):
                    names.add(w.target.id)
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                names.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name:
            names.add(n.name)
        stack.extend(ast.iter_child_nodes(n))
    return names


def check_source(src: str, filename: str = "<src>") -> list[tuple[str, str, int]]:
    """[(함수명, 이름, 줄)] — 어느 범위에서도 정의를 못 찾은 이름."""
    tree = ast.parse(src, filename)
    module_names = _bound_in(tree) | BUILTINS
    problems: list[tuple[str, str, int]] = []

    def dispatch(node: ast.AST, chain: list[set[str]], where: str) -> None:
        """노드 **자신**을 보고 범위를 엽니다. (전에는 자식만 봐서, 함수
        본문에 바로 놓인 중첩 def 의 범위를 못 열었습니다.)"""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            outer_bits = []
            if not isinstance(node, ast.Lambda):
                outer_bits += node.decorator_list
                if node.returns is not None:
                    outer_bits.append(node.returns)
            outer_bits += node.args.defaults + [
                d for d in node.args.kw_defaults if d is not None]
            for bit in outer_bits:
                dispatch(bit, chain, where)
            inner = chain + [_bound_in(node)]
            name = getattr(node, "name", where)
            body = node.body if isinstance(node.body, list) else [node.body]
            for stmt in body:
                dispatch(stmt, inner, name)
            return
        if isinstance(node, ast.ClassDef):
            for bit in node.decorator_list + node.bases:
                dispatch(bit, chain, where)
            inner = chain + [_bound_in(node)]
            for stmt in node.body:
                dispatch(stmt, inner, node.name)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp,
                             ast.GeneratorExp)):
            comp_names: set[str] = set()
            for gen in node.generators:
                for t in ast.walk(gen.target):
                    if isinstance(t, ast.Name):
                        comp_names.add(t.id)
            inner = chain + [comp_names]
            for child in ast.iter_child_nodes(node):
                dispatch(child, inner, where)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            _check(node, chain, where)
            return
        for child in ast.iter_child_nodes(node):
            dispatch(child, chain, where)

    def _check(n: ast.Name, chain: list[set[str]], where: str) -> None:
        if n.id in module_names:
            return
        if any(n.id in scope for scope in chain):
            return
        problems.append((where, n.id, n.lineno))

    for stmt in tree.body:
        dispatch(stmt, [], "<module>")
    seen: set[tuple[str, str]] = set()
    out = []
    for where, name, line in problems:
        if (where, name) in seen:
            continue
        seen.add((where, name))
        out.append((where, name, line))
    return out


def main(argv: list[str]) -> int:
    files = [a for a in argv[1:] if a.endswith(".py")] or ["app.py"]
    total = 0
    for f in files:
        probs = check_source(pathlib.Path(f).read_text(encoding="utf-8"), f)
        for where, name, line in probs:
            print(f"  ✗ {f}:{line}  {where}() 안의 '{name}' — 정의를 못 찾음")
        total += len(probs)
    print("미정의 이름 없음" if not total else f"미정의 이름 {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
