"""모든 파일의 `모듈.속성` 참조가 실제로 존재하는지 검사.

Streamlit Cloud 는 import 하고 실행해 봐야 AttributeError 가 나옵니다.
배포 한 번에 1분씩 걸리니, 올리기 전에 정적으로 잡습니다.
"""
import ast, pathlib, sys

def scan(root: "pathlib.Path") -> list[tuple]:
    """root 아래 모든 .py 에서 존재하지 않는 `모듈.속성` 참조를 찾습니다."""
    root = pathlib.Path(root)
    files = sorted(p for p in root.rglob("*.py")
                   if "__pycache__" not in str(p) and ".venv" not in str(p))

    exports: dict[str, set[str]] = {}
    for p in files:
        rel = p.relative_to(root).with_suffix("")
        mod = ".".join(rel.parts)
        tree = ast.parse(p.read_text(encoding="utf-8"))
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                # A, B = 1, 2 같은 튜플 분해도 최상위 이름입니다 —
                # 이걸 빼먹으면 멀쩡한 상수를 '없다' 고 오탐합니다.
                stack = list(node.targets)
                while stack:
                    t = stack.pop()
                    if isinstance(t, ast.Name):
                        names.add(t.id)
                    elif isinstance(t, (ast.Tuple, ast.List)):
                        stack.extend(t.elts)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                                ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.asname or a.name.split(".")[0])
        exports[mod] = names

    # 패키지 하위 모듈이 파일로 존재하는지 — sources/ 폴더가 빠진 채
    # 올라가서 ModuleNotFoundError 로 죽은 적이 있습니다. 가장 먼저 봅니다.
    pkgs = {d.name for d in root.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()}
    problems = []
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    parts = a.name.split(".")
                    if parts[0] in pkgs and len(parts) > 1:
                        if not (root / a.name.replace(".", "/")).with_suffix(
                                ".py").exists():
                            problems.append((str(p.relative_to(root)),
                                             node.lineno, "import",
                                             a.name, "<파일 없음>"))
            elif (isinstance(node, ast.ImportFrom) and node.module
                  and node.level == 0
                  and node.module.split(".")[0] in pkgs):
                base = root / node.module.replace(".", "/")
                if not base.with_suffix(".py").exists():
                    for a in node.names:
                        if not (base / f"{a.name}.py").exists():
                            problems.append((str(p.relative_to(root)),
                                             node.lineno, "from",
                                             f"{node.module}.{a.name}",
                                             "<파일 없음>"))
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        alias: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in exports:
                        alias[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    if full in exports:
                        alias[a.asname or a.name] = full
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in alias):
                mod = alias[node.value.id]
                if (node.attr not in exports[mod]
                        and not node.attr.startswith("__")):
                    problems.append((str(p.relative_to(root)), node.lineno,
                                     node.value.id, mod, node.attr))
    return problems


if __name__ == "__main__":
    probs = scan(pathlib.Path(__file__).resolve().parent.parent)
    if probs:
        print(f"!! 존재하지 않는 참조 {len(probs)}건")
        for f, ln, al, mod, at in probs:
            print(f"   {f}:{ln}  {al}.{at}  (-> {mod} 에 없음)")
        sys.exit(1)
    print("모듈 간 참조 이상 없음")
