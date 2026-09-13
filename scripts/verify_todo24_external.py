#!/usr/bin/env python3
"""External verification script for TODO-24 (F7-L-04) exit semantics.

Validates, against the canonical per-module coverage gate
(scripts/check_per_module_coverage.py):

1. Exit code 0 on success, exit code 1 on all failure paths
2. No failure exit may appear after the success exit (fallthrough)
3. Unit tests exist for the gate's behavioral classes (success path,
   failure paths, stale-artifact rejection, explicit artifact path)
4. The unit tests pass
5. Health-check integration (G02, formerly HC-13) is intact

Outcome-scoped grading (2026-09-13): earlier revisions of this verifier
pinned implementation idioms that the gate legitimately outgrew -- the
line number of the success ``sys.exit(0)``, an exact historical unit-test
name list, and docstring prose ("80%", "threshold"). When the gate
evolved (stale-artifact rejection, explicit artifact path, grading-loop
repair), those pins went stale and failed on a correct implementation.
The pins now assert the CONTRACT (ordering, behavioral coverage,
documented fallback floor map), not the historical text.

Exit codes:
    0: All verification passed
    1: One or more verifications failed
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import traceback
from pathlib import Path

_PY_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "loatsNEW" / "Scripts" / "python.exe",
    Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe",
)


def get_project_root() -> Path:
    """Get project root directory robustly."""
    try:
        script_file = Path(__file__).resolve()
        if "scripts" in script_file.parts:
            idx = script_file.parts.index("scripts")
            return Path(*script_file.parts[:idx])
    except Exception:
        pass

    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists() and (cwd / "scripts").is_dir():
        return cwd

    for parent in list(cwd.parents):
        if (parent / "pyproject.toml").exists() and (parent / "scripts").is_dir():
            return parent

    return cwd


def _python() -> str:
    """Resolve the repo venv interpreter (falls back to the current one)."""
    for cand in _PY_CANDIDATES:
        if cand.exists():
            return str(cand)
    return sys.executable


PROJECT_ROOT = get_project_root()
COVERAGE_SCRIPT = PROJECT_ROOT / "scripts" / "check_per_module_coverage.py"
TEST_FILE = PROJECT_ROOT / "tests" / "test_check_per_module_coverage.py"
HEALTH_CHECK_FILE = PROJECT_ROOT / "scripts" / "fr7_health_check.py"

_SUMMARY_PASSED_RE = re.compile(r"(\d+) passed")
_SUMMARY_FAILED_RE = re.compile(r"(\d+) failed")


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run command and return exit code, stdout, stderr."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd or PROJECT_ROOT
    )
    return result.returncode, result.stdout, result.stderr


def verify_exit_semantics_source() -> bool:
    """Verify exit semantics by POSITION, not by line number.

    Contract: exactly one success exit (sys.exit(0)), at least four
    failure exits (sys.exit(1)), and the success exit must be the LAST
    exit statement in the file -- which is the fallthrough-safety
    property itself, independent of how many lines the script has.
    """
    try:
        if not COVERAGE_SCRIPT.is_file():
            print(f"X FAILED: Script not found at {COVERAGE_SCRIPT}")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()

        exit_lines = []
        for i, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if "sys.exit" in line and not line.startswith("#"):
                exit_lines.append((i, line))

        print("\n=== EXIT SEMANTICS SOURCE VERIFICATION ===")
        print(f"Found {len(exit_lines)} sys.exit() calls:")

        exit_0_count = 0
        exit_1_count = 0

        for line_num, line in exit_lines:
            print(f"  Line {line_num}: {line}")
            if "sys.exit(0)" in line:
                exit_0_count += 1
            elif "sys.exit(1)" in line:
                exit_1_count += 1

        if exit_0_count != 1:
            print(f"\nX FAILED: Expected exactly 1 sys.exit(0), found {exit_0_count}")
            return False

        if exit_1_count < 4:
            print(
                f"\nX FAILED: Expected at least 4 sys.exit(1) calls, found {exit_1_count}"
            )
            return False

        last_line_num, last_line_text = exit_lines[-1]
        if "sys.exit(0)" not in last_line_text:
            print(
                f"\nX FAILED: Final exit statement must be sys.exit(0), got line "
                f"{last_line_num}: {last_line_text}"
            )
            return False

        print("\n  Exit semantics verified:")
        print("  - sys.exit(0): 1 call (success path only, final exit)")
        print(f"  - sys.exit(1): {exit_1_count} calls (all error paths)")

        return True

    except Exception:
        print("\nX FAILED: verify_exit_semantics_source() crashed:")
        traceback.print_exc()
        return False


def _test_function_names(source: str) -> set[str]:
    """Collect every ``test_*`` function name via AST (module + classes)."""
    names: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.add(node.name)
    return names


def verify_unit_tests_exist() -> bool:
    """Verify behavioral-class coverage of the gate's unit tests.

    The suite must cover: the success path, at least three failure
    paths, stale-artifact rejection, and explicit artifact path
    handling. Names are matched by behavioral suffix (``_passes`` /
    ``_fails`` / ``stale`` / ``explicit``), never by an exact
    historical name list -- the gate may rename or add tests freely.
    """
    try:
        print("\n=== UNIT TEST VERIFICATION ===")

        if not TEST_FILE.is_file():
            print(f"X FAILED: Unit test file not found at {TEST_FILE}")
            return False

        names = _test_function_names(TEST_FILE.read_text(encoding="utf-8"))
        if not names:
            print("X FAILED: No test functions discovered in test file")
            return False

        pass_class = {n for n in names if n.endswith("_passes")}
        fail_class = {n for n in names if n.endswith("_fails")}
        stale_class = {n for n in names if "stale" in n}
        explicit_class = {n for n in names if "explicit" in n}

        missing: list[str] = []
        if not pass_class:
            missing.append("success-path test (name ending _passes)")
        if len(fail_class) < 3:
            missing.append(
                f"failure-path tests (name ending _fails), found {len(fail_class)}"
            )
        if not stale_class:
            missing.append("stale-artifact rejection test (name containing stale)")
        if not explicit_class:
            missing.append("explicit artifact path test (name containing explicit)")

        if missing:
            print("X FAILED: Missing required behavioral test classes:")
            for item in missing:
                print(f"  - {item}")
            return False

        print("  Behavioral test classes present:")
        print(f"  - success path: {sorted(pass_class)}")
        print(f"  - failure paths ({len(fail_class)}): {sorted(fail_class)}")
        print(f"  - stale-artifact rejection: {sorted(stale_class)}")
        print(f"  - explicit artifact path: {sorted(explicit_class)}")

        return True

    except Exception:
        print("\nX FAILED: verify_unit_tests_exist() crashed:")
        traceback.print_exc()
        return False


def run_unit_tests() -> bool:
    """Run the gate's unit tests with the repo venv interpreter.

    Grading contract: exit code 0 AND a parsed pytest summary with
    >0 passed and 0 failed. A substring check for "passed" would also
    accept a failing summary such as "2 failed, 500 passed".
    """
    try:
        print("\n=== RUNNING UNIT TESTS ===")

        cmd = [
            _python(),
            "-m",
            "pytest",
            str(TEST_FILE),
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ]

        exit_code, stdout, stderr = run_command(cmd)

        print(stdout)
        if stderr:
            print("STDERR:", stderr)

        passed_match = _SUMMARY_PASSED_RE.search(stdout)
        failed_match = _SUMMARY_FAILED_RE.search(stdout)
        n_passed = int(passed_match.group(1)) if passed_match else 0
        n_failed = int(failed_match.group(1)) if failed_match else 0

        if exit_code != 0:
            print(f"\nX FAILED: Unit tests failed with exit code {exit_code}")
            return False

        if n_passed == 0 or n_failed != 0:
            print(
                f"\nX FAILED: Tests did not report a clean summary "
                f"(passed={n_passed}, failed={n_failed})"
            )
            return False

        print(f"\n  All unit tests passed ({n_passed} passed, 0 failed)")
        return True

    except Exception:
        print("\nX FAILED: run_unit_tests() crashed:")
        traceback.print_exc()
        return False


def verify_integration_with_health_check() -> bool:
    """Verify integration with the FR7 health-check catalogue (G02)."""
    try:
        print("\n=== HEALTH CHECK INTEGRATION VERIFICATION ===")

        if not HEALTH_CHECK_FILE.is_file():
            print("X FAILED: Health check script not found")
            return False

        content = HEALTH_CHECK_FILE.read_text(encoding="utf-8")

        # Accept both legacy (HC-13) and new grouped catalogue (G02):
        # both must reference check_per_module_coverage.py with TODO-15.
        has_gate = ("HC-13" in content) or ('id="G02"' in content)
        if not has_gate or "check_per_module_coverage.py" not in content:
            print(
                "X FAILED: health check does not reference check_per_module_coverage.py (G02/HC-13)"
            )
            return False

        if "TODO-15" not in content:
            print("X FAILED: coverage gate missing TODO-15 reference")
            return False

        print("  Coverage gate (G02, formerly HC-13) properly configured:")
        print("  - References check_per_module_coverage.py")
        print("  - Linked to TODO-15 (folded from TODO-24)")

        return True

    except Exception:
        print("\nX FAILED: verify_integration_with_health_check() crashed:")
        traceback.print_exc()
        return False


def verify_no_fallthrough_paths() -> bool:
    """Verify no failure exit can precede the success exit."""
    try:
        print("\n=== FALLTHROUGH PATH ANALYSIS ===")

        if not COVERAGE_SCRIPT.is_file():
            print("X FAILED: Script not found")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")

        all_exit_calls = list(re.finditer(r"sys\.exit\((\d+)\)", content))

        if len(all_exit_calls) < 5:
            print(
                f"X FAILED: Expected at least 5 sys.exit calls, found {len(all_exit_calls)}"
            )
            return False

        last_exit = all_exit_calls[-1]
        if last_exit.group(1) != "0":
            print(
                f"X FAILED: Last sys.exit is not sys.exit(0), it's sys.exit({last_exit.group(1)})"
            )
            return False

        exit_0_positions = [
            i for i, call in enumerate(all_exit_calls) if call.group(1) == "0"
        ]
        exit_1_positions = [
            i for i, call in enumerate(all_exit_calls) if call.group(1) == "1"
        ]

        if exit_1_positions and exit_0_positions:
            if max(exit_1_positions) > min(exit_0_positions):
                print("X FAILED: Exit(1) found after exit(0) - fallthrough risk")
                return False

        print("  No fallthrough paths detected:")
        print(f"  - Total sys.exit calls: {len(all_exit_calls)}")
        print(f"  - sys.exit(1): {len(exit_1_positions)} calls (all error paths)")
        print(f"  - sys.exit(0): {len(exit_0_positions)} call (success path)")
        print("  - All error exits occur before success exit")
        print(f"  - Final exit is sys.exit(0) (position {len(all_exit_calls) - 1})")

        return True

    except Exception:
        print("\nX FAILED: verify_no_fallthrough_paths() crashed:")
        traceback.print_exc()
        return False


def verify_documentation() -> bool:
    """Verify the gate documents its fail-closed contract.

    The docstring must state the load-bearing contract -- per-module
    coverage floors over a floor map with an identical fallback so the
    gate can never be silently narrowed -- not a historical percentage.
    """
    try:
        print("\n=== DOCUMENTATION VERIFICATION ===")

        if not COVERAGE_SCRIPT.is_file():
            print("X FAILED: Script not found")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")

        if '"""' not in content[:200]:
            print("X FAILED: Script missing docstring")
            return False

        doc_match = re.search(r'"""(.+?)"""', content[:500], re.DOTALL)
        if not doc_match:
            print("X FAILED: Could not extract docstring")
            return False

        docstring = doc_match.group(1).lower()

        # Contract keywords: the gate enforces coverage floors from a
        # floor map, with a fallback map that prevents silent narrowing.
        required_keywords = ["coverage", "floor map", "fallback"]
        missing_keywords = [kw for kw in required_keywords if kw not in docstring]

        if missing_keywords:
            print(f"X FAILED: Docstring missing contract keywords: {missing_keywords}")
            return False

        print("  Documentation verified:")
        print("  - Script has docstring")
        print(f"  - States the fail-closed contract: {', '.join(required_keywords)}")

        return True

    except Exception:
        print("\nX FAILED: verify_documentation() crashed:")
        traceback.print_exc()
        return False


def main() -> int:
    """Main verification routine."""
    print("=" * 70)
    print("TODO-24 (F7-L-04) Exit Semantics Verification")
    print("=" * 70)

    results = [
        ("Exit Semantics Source", verify_exit_semantics_source()),
        ("Unit Tests Exist", verify_unit_tests_exist()),
        ("Unit Tests Pass", run_unit_tests()),
        ("Health Check Integration", verify_integration_with_health_check()),
        ("No Fallthrough Paths", verify_no_fallthrough_paths()),
        ("Documentation", verify_documentation()),
    ]

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\nTODO-24 VERIFICATION COMPLETE: All checks passed")
        print("Exit semantics verified. Unit tests added. Integrated with TODO-15.")
        return 0
    else:
        print(f"\nTODO-24 VERIFICATION FAILED: {total - passed} check(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
