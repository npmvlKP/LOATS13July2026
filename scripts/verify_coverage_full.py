"""FR7 Full Coverage Verification with a fresh, CI-parity pytest run.

Usage:  python scripts/verify_coverage_full.py

Runs the FULL test suite (``tests/``) with the same coverage scope and
floors CI enforces, then validates the gates. Takes ~4-5 minutes.

Scope contract (2026-09-13): the embedded command is the CI
``pytest-coverage`` job's command (full ``tests/``, ``--cov=src``,
``--cov-branch``, ``--cov-fail-under=80``). The previous version ran a
frozen 5-file subset whose per-module totals cannot satisfy the
repo-wide ``fail_under = 80`` grading (the subset's own total is ~35%),
which made this verifier born-red on every compliant environment and
invited grading stale artifacts instead. Per-module floors are NOT
re-derived here: they are delegated to the canonical
``scripts/check_per_module_coverage.py`` gate so this repo carries one
floor map, not two that can drift.

Fresh-evidence contract: any stale root ``coverage.json`` is deleted
BEFORE the embedded pytest run and the report path is pinned explicitly
via ``--cov-report=json:coverage.json``. If the embedded run dies before
writing the report, the existence gate below fails closed.

Test-result grading contract: the run passes only when its exit code is
0 AND the parsed pytest summary shows ``> 0 passed`` and ``0 failed``.
Previously the gate grepped stdout for the substring "passed", which
also accepts a FAILING run whose summary reads ``N failed, M passed``.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

PASS = FAIL = 0

_SUMMARY_PASSED_RE = re.compile(r"(\d+) passed")
_SUMMARY_FAILED_RE = re.compile(r"(\d+) failed")

# Full-suite pytest inside a verifier budget: the CI job allows 900s
# for the same command; the outer timeout is a fail-closed backstop.
_PYTEST_TIMEOUT_S = 900


def _emit(message: str) -> None:
    """Print ``message`` even when the console encoding cannot encode it.

    Windows consoles default to a legacy codepage (cp1252); echoing
    pytest output containing e.g. U+2192 raised UnicodeEncodeError and
    replaced the diagnostic with a traceback. Degrading unencodable
    text to backslashreplace output keeps the gate's explanation
    visible on every console.
    """
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        message.encode(encoding)
    except UnicodeEncodeError:
        stream.write(message.encode(encoding, "backslashreplace").decode(encoding))
        stream.write("\n")
        stream.flush()
        return
    print(message)


def gate(name, ok, detail=""):
    global PASS, FAIL
    PASS += 1 if ok else 0
    FAIL += 0 if ok else 1
    tag = "PASS" if ok else "FAIL"
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"  --  {detail}"
    _emit(msg)


print("=" * 60)
print("FR7 Full Coverage Verification (with test execution)")
print("=" * 60)

critical_module_tests = [
    "tests/test_trailing_stop.py",
    "tests/test_trade_decision.py",
    "tests/test_options_var.py",
    "tests/test_orchestrator.py",
    "tests/test_orchestrator_extra.py",
]

# G1
print("\n--- G1  Critical Module Test Integrity ---")
for tf in critical_module_tests:
    p = Path(tf)
    if not p.exists():
        gate(f"{tf}", False, "missing")
        continue
    try:
        tree = ast.parse(p.read_text("utf-8"))
        n = sum(
            1
            for nd in ast.walk(tree)
            if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        gate(
            f"{tf}",
            True,
            f"{len(p.read_text('utf-8').splitlines())} lines, {n} funcs",
        )
    except SyntaxError as e:
        gate(f"{tf}", False, str(e))

# G2
print("\n--- G2  Temp File Cleanup ---")
temps = list(Path().glob("_*.py"))
gate(
    "No _*.py temp files in root",
    len(temps) == 0,
    f"found {[t.name for t in temps]}" if temps else "clean",
)

# G3+G4: run the FULL suite with CI-parity coverage flags
print("\n--- G3+G4  Test Execution + Coverage (full suite, CI parity) ---")
cov_path = Path("coverage.json")
# Fresh-evidence contract: the report must be produced by THIS run.
# Delete any stale report first so a crash of the embedded pytest can
# never leave an old file for the existence gate below to accept.
if cov_path.exists():
    cov_path.unlink()
cmd = [
    sys.executable,
    "-m",
    "pytest",
    "tests/",
    "--cov=src",
    "--cov-branch",
    "--cov-report=json:coverage.json",
    "--cov-report=term",
    "--cov-fail-under=80",
    "-q",
    "--no-header",
    # Keep this verifier's cache writes out of the repo it measures.
    "-p",
    "no:cacheprovider",
]
print(f"  Running: {' '.join(cmd[3:8])} ... (full suite, ~4-5 min)")
try:
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_PYTEST_TIMEOUT_S
    )
except subprocess.TimeoutExpired:
    gate("All tests pass", False, f"embedded pytest run exceeded {_PYTEST_TIMEOUT_S}s")
    sys.exit(1)

# Parse test result: exit code + explicit summary counts, never a
# substring heuristic ("passed" also matches "2 failed, 500 passed").
# pytest itself enforces --cov-fail-under=80 on the aggregate; rc==0
# therefore certifies the full-suite coverage floor as well.
lines = result.stdout.splitlines()
passed_match = _SUMMARY_PASSED_RE.search(result.stdout)
failed_match = _SUMMARY_FAILED_RE.search(result.stdout)
n_passed = int(passed_match.group(1)) if passed_match else 0
n_failed = int(failed_match.group(1)) if failed_match else 0
for line in lines:
    if "passed" in line or "failed" in line or "error" in line:
        _emit(f"  [INFO] {line.strip()}")
test_ok = result.returncode == 0 and n_passed > 0 and n_failed == 0
if not test_ok:
    detail = f"pytest rc={result.returncode}, passed={n_passed}, failed={n_failed}"
    stderr_tail = (result.stderr or "").strip()[-200:]
    if stderr_tail:
        detail += f"; stderr: {stderr_tail}"
    gate("All tests pass", False, detail)
else:
    gate(
        "All tests pass",
        True,
        f"rc=0, {n_passed} passed, {n_failed} failed",
    )

# The report exists only if THIS run wrote it (the stale copy was
# unlinked above and the path is pinned explicitly).
if not cov_path.exists():
    gate("coverage.json generated", False, "pytest did not produce coverage data")
    sys.exit(1)
gate("coverage.json generated", True, f"{cov_path.stat().st_size:,} bytes")

# G5: per-module floors via the CANONICAL floor gate. This verifier no
# longer carries its own floor map or its own aggregate -- the repo has
# one floor map (coverage_floor_map.json via check_per_module_coverage),
# and duplicating it here only invited drift.
print("\n--- G5  Per-Module Coverage Floors (canonical gate) ---")
floor_checker = Path("scripts/check_per_module_coverage.py")
if not floor_checker.exists():
    gate("check_per_module_coverage.py", False, "canonical floor gate missing")
    sys.exit(1)
try:
    floors = subprocess.run(
        [sys.executable, str(floor_checker), str(cov_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
except subprocess.TimeoutExpired:
    gate("per-module coverage floors", False, "floor check exceeded 120s")
    sys.exit(1)
for line in floors.stdout.splitlines():
    _emit(f"  {line}")
if floors.stderr.strip():
    _emit(f"  [stderr] {floors.stderr.strip()[-300:]}")
gate("per-module coverage floors (check_per_module_coverage)", floors.returncode == 0)

print("\n" + "=" * 60)
print(f"RESULT:  {PASS} PASS  |  {FAIL} FAIL")
print("STATUS: " + ("ALL GATES PASSED" if FAIL == 0 else f"{FAIL} GATE(S) FAILED"))
print("=" * 60)
sys.exit(1 if FAIL else 0)
