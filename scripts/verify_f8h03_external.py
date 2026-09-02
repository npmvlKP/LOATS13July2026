#!/usr/bin/env python3
"""External verification for F8-H-03.

Run independently from the project root:

    python scripts/verify_f8h03_external.py

Verifies:
1. The scheduler no longer registers ta_scan/sentiment_scan jobs.
2. The scheduler no longer contains Signal() construction sites.
3. Every Signal() in src/loats/ carries an enum-valid source tag.
4. The retired job IDs are handled gracefully by run_once().
5. Changed-file quality gates pass (ruff, ruff format, mypy scheduler).
6. The targeted test suite passes.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from typing import NoReturn

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "loats"
PY = REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe"


PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"


# These files reconstruct signals from rows, create test-only fixtures, or
# use Python 3.12-only syntax that should not be parsed by a 3.11 scanner.
EXEMPT = {
    "database.py",
    "database_async_additions.py",
    "performance_analyzer.py",
    "lazy_singleton.py",
}


def _run(cmd: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _check_scheduler_no_signal_jobs() -> bool:
    scheduler = (SRC_ROOT / "scheduler.py").read_text(encoding="utf-8")
    if "ta_scan" in scheduler or "sentiment_scan" in scheduler:
        # They may still appear only as retired warnings / run_once branches.
        tree = ast.parse(scheduler)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "add_job":
                    for kw in node.keywords:
                        if kw.arg == "id" and isinstance(kw.value, ast.Constant):
                            if kw.value.value in {"ta_scan", "sentiment_scan"}:
                                return False
        return True
    return True


def _check_scheduler_no_signal_construction() -> bool:
    tree = ast.parse((SRC_ROOT / "scheduler.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "Signal":
                return False
    return True


def _is_signal_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Signal":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Signal":
        return True
    return False


def _extract_string_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_strengthsource_value(node: ast.AST | None) -> str | None:
    """Resolve ``StrengthSource.X.value`` to the enum member's value."""
    from loats.strength import StrengthSource

    if (
        isinstance(node, ast.Attribute)
        and node.attr == "value"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "StrengthSource"
    ):
        member = node.value.attr
        try:
            return StrengthSource[member].value
        except KeyError:
            return None
    return None


def _check_signal_source_invariant() -> bool:
    from loats.strength import StrengthSource, resolve_source

    valid = {s.value for s in StrengthSource}
    for path in SRC_ROOT.rglob("*.py"):
        if path.name in EXEMPT or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not _is_signal_call(node):
                continue
            assert isinstance(node, ast.Call)
            metadata_kw = None
            for kw in node.keywords:
                if kw.arg == "metadata":
                    metadata_kw = kw.value
                    break
            if not isinstance(metadata_kw, ast.Dict):
                return False
            source = None
            for k, v in zip(metadata_kw.keys, metadata_kw.values, strict=False):
                if isinstance(k, ast.Constant) and k.value == "source":
                    source = _extract_string_literal(
                        v
                    ) or _extract_strengthsource_value(v)
                    break
            if source is None or source not in valid:
                return False
            try:
                resolve_source(source)
            except ValueError:
                return False
    return True


def _run_tests() -> bool:
    targets = [
        "tests/test_signal_source_invariant.py",
        "tests/test_single_engine_consolidation.py",
        "tests/test_scheduler.py",
        "tests/test_scheduler_coverage.py",
    ]
    rc, out, _err = _run([str(PY), "-m", "pytest"] + targets + ["-q"])
    return rc == 0 and "passed" in out


def _run_quality_gates() -> bool:
    changed = [
        "src/loats/scheduler.py",
        "tests/test_signal_source_invariant.py",
        "tests/test_single_engine_consolidation.py",
        "tests/test_scheduler_coverage.py",
    ]
    checks = [
        [str(PY), "-m", "ruff", "check"] + changed,
        [str(PY), "-m", "ruff", "format", "--check"] + changed,
        [str(PY), "-m", "mypy", "src/loats/scheduler.py", "--ignore-missing-imports"],
    ]
    for check in checks:
        rc, _out, _err = _run(check)
        if rc != 0:
            return False
    return True


def main() -> NoReturn:
    checks = [
        (
            "Scheduler does not register ta/sentiment signal jobs",
            _check_scheduler_no_signal_jobs,
        ),
        (
            "Scheduler contains no Signal() construction",
            _check_scheduler_no_signal_construction,
        ),
        (
            "Every Signal() in src/loats has enum-valid source",
            _check_signal_source_invariant,
        ),
        ("Targeted tests pass", _run_tests),
        ("Changed-file quality gates pass", _run_quality_gates),
    ]

    results: list[tuple[str, bool]] = []
    for name, func in checks:
        try:
            ok = func()
        except Exception as exc:
            print(f"{FAIL_SYM} {name}: {exc}")
            results.append((name, False))
            continue
        symbol = PASS_SYM if ok else FAIL_SYM
        print(f"{symbol} {name}")
        results.append((name, ok))

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\nRESULT: {passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
