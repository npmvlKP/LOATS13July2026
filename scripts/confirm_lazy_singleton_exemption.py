#!/usr/bin/env python3
"""Confirm lazy_singleton.py 3.12 syntax exemption and Signal-source invariant.

Runs inside the project venv."""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "loats"
EXEMPT = {
    "database.py",
    "database_async_additions.py",
    "performance_analyzer.py",
    "lazy_singleton.py",
}


def is_signal_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Signal":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Signal":
        return True
    return False


def extract_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_strengthsource_value(node: ast.AST | None) -> str | None:
    from loats.strength import StrengthSource

    if (
        isinstance(node, ast.Attribute)
        and node.attr == "value"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "StrengthSource"
    ):
        try:
            return StrengthSource[node.value.attr].value
        except KeyError:
            return None
    return None


def main() -> int:
    from loats.strength import StrengthSource, resolve_source

    valid = {s.value for s in StrengthSource}
    print(f"valid StrengthSource values: {valid}")

    bad: list[tuple[pathlib.Path, int, str]] = []
    for path in SRC_ROOT.rglob("*.py"):
        if path.name in EXEMPT or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not is_signal_call(node):
                continue
            assert isinstance(node, ast.Call)
            metadata = None
            for kw in node.keywords:
                if kw.arg == "metadata":
                    metadata = kw.value
                    break
            if not isinstance(metadata, ast.Dict):
                bad.append((path, node.lineno, "metadata not dict"))
                continue
            source = None
            for k, v in zip(metadata.keys, metadata.values, strict=False):
                if isinstance(k, ast.Constant) and k.value == "source":
                    source = extract_string(v) or extract_strengthsource_value(v)
                    break
            if source is None or source not in valid:
                bad.append((path, node.lineno, f"bad source {source!r}"))
                continue
            try:
                resolve_source(source)
            except ValueError as exc:
                bad.append((path, node.lineno, f"resolve_source error {exc}"))

    if bad:
        print("BAD Signal() calls:")
        for path, lineno, reason in bad:
            print(f"  {path}:{lineno} {reason}")
        return 1

    print("All non-exempt Signal() calls have enum-valid sources")

    # lazy_singleton.py is intentionally exempt from AST scanning because it
    # uses PEP 695 syntax (class LazyProxy[T]) which is only valid in Python 3.12+.
    lazy = SRC_ROOT / "utils" / "lazy_singleton.py"
    text = lazy.read_text(encoding="utf-8")
    if "class LazyProxy[T]" in text:
        print(
            "lazy_singleton.py uses PEP 695 class syntax (class LazyProxy[T]) — exempted"
        )
    else:
        print("WARNING: expected PEP 695 syntax in lazy_singleton.py not found")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
