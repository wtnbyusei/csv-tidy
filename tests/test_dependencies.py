"""依存の向きを確かめる（設計書 1章・7.3、NFR-03）。

コアは Web の窓口（FastAPI など）に依存せず、v0.4（候補）でブラウザ内の Python
（Pyodide）でも動かせるよう、ブラウザで使えない標準ライブラリにも依存しない。
"""

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "csv_tidy" / "core"

# コアが import してはいけないモジュール（先頭の名前で判定する）
FORBIDDEN = {
    # Web の窓口とその部品
    "fastapi",
    "pydantic",
    "starlette",
    "uvicorn",
    "orjson",
    "csv_tidy.api",
    "csv_tidy.web",
    # ブラウザ内の Python（Pyodide）で使えない、または使うべきでないもの
    "threading",
    "multiprocessing",
    "subprocess",
    "socket",
    "http",
    "urllib.request",
}


def _module_of(path: Path, base: Path) -> list[str]:
    """ファイルのモジュール名を、パッケージの区切りごとのリストで返す。"""
    parts = list(path.relative_to(base.parent.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return parts


def imported_modules(path: Path, base: Path = CORE_DIR) -> set[str]:
    """ファイルが import しているモジュール名を返す。相対 import は絶対名に直す。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _module_of(path, base)
    if path.name != "__init__.py":
        package = package[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package[: len(package) - node.level + 1]
                prefix = ".".join(anchor + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            names.add(prefix)
            names.update(f"{prefix}.{alias.name}" for alias in node.names)
    return names


def forbidden_imports(path: Path, base: Path = CORE_DIR) -> set[str]:
    """ファイルの import のうち、禁止されているものを返す。"""
    return {
        name
        for name in imported_modules(path, base)
        if any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN)
    }


def test_core_does_not_import_forbidden_modules():
    files = sorted(CORE_DIR.rglob("*.py"))
    assert files, "コアのファイルが見つからない"
    violations = {
        str(f.relative_to(CORE_DIR)): sorted(bad)
        for f in files
        if (bad := forbidden_imports(f))
    }
    assert violations == {}


# --- 判定の仕組みそのものが正しく働くかを確かめる -----------------------------


def _write(tmp_path: Path, relative: str, source: str) -> tuple[Path, Path]:
    base = tmp_path / "src" / "csv_tidy" / "core"
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path, base


def test_detects_absolute_import(tmp_path):
    path, base = _write(tmp_path, "x.py", "import fastapi\nfrom pydantic import BaseModel\n")
    assert forbidden_imports(path, base) == {"fastapi", "pydantic", "pydantic.BaseModel"}


def test_detects_relative_import_into_api(tmp_path):
    path, base = _write(tmp_path, "x.py", "from ..api import app\n")
    assert forbidden_imports(path, base) == {"csv_tidy.api", "csv_tidy.api.app"}


def test_detects_browser_unfriendly_stdlib(tmp_path):
    path, base = _write(tmp_path, "x.py", "import threading\nfrom urllib.request import urlopen\n")
    assert forbidden_imports(path, base) == {
        "threading",
        "urllib.request",
        "urllib.request.urlopen",
    }


def test_allows_stdlib_and_core_modules(tmp_path):
    source = "import csv\nimport codecs\nfrom . import models\nfrom .models import Record\n"
    path, base = _write(tmp_path, "x.py", source)
    assert forbidden_imports(path, base) == set()
