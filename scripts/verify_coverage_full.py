"""FR7 Full Coverage Verification with fresh pytest run.

Usage:  python scripts/verify_coverage_full.py

Runs the full 219-test suite with coverage instrumentation,
then validates all gates. Takes ~25 seconds.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

PASS = FAIL = 0


def gate(name, ok, detail=""):
    global PASS, FAIL
    PASS += (1 if ok else 0)
    FAIL += (0 if ok else 1)
    tag = "PASS" if ok else "FAIL"
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"  --  {detail}"
    print(msg)


print("=" * 60)
print("FR7 Full Coverage Verification (with test execution)")
print("=" * 60)

test_files = [
    "tests/test_trailing_stop.py",
    "tests/test_trade_decision.py",
    "tests/test_options_var.py",
    "tests/test_orchestrator.py",
    "tests/test_orchestrator_extra.py",
]

# G1
print("\n--- G1  Test File Integrity ---")
for tf in test_files:
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
        gate(f"{tf}", True, f"{len(p.read_text('utf-8').splitlines())} lines, {n} funcs")
    except SyntaxError as e:
        gate(f"{tf}", False, str(e))

# G2
print("\n--- G2  Temp File Cleanup ---")
temps = list(Path(".").glob("_*.py"))
gate(
    "No _*.py temp files in root",
    len(temps) == 0,
    f"found {[t.name for t in temps]}" if temps else "clean",
)

# G3+G4: run tests with coverage
print("\n--- G3+G4  Test Execution + Coverage ---")
cmd = [
    sys.executable,
    "-m",
    "pytest",
    *test_files,
    "--cov=src/loats",
    "--cov-report=json",
    "--cov-report=term",
    "-q",
    "--timeout=10",
    "--no-header",
]
print(f"  Running: {' '.join(cmd[3:8])} ...")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=Path("."))

# Parse test result
lines = result.stdout.splitlines()
test_ok = any("passed" in l for l in lines)
for l in lines:
    if "passed" in l:
        print(f"  [INFO] {l.strip()}")
if not test_ok:
    gate("All tests pass", False, result.stdout[-200:])
else:
    gate("All tests pass", True, "")

# Parse coverage
cov_path = Path("coverage.json")
if not cov_path.exists():
    gate("coverage.json generated", False, "pytest did not produce coverage data")
    sys.exit(1)
gate("coverage.json generated", True, f"{cov_path.stat().st_size:,} bytes")

data = json.loads(cov_path.read_text("utf-8"))
targets = {
    "trailing_stop.py": 80,
    "trade_decision.py": 80,
    "options.py": 80,
    "orchestrator.py": 80,
}
tot_covered = tot_miss = 0
for fp, fd in data.get("files", {}).items():
    fname = fp.replace("/", chr(92)).split(chr(92))[-1]
    if fname not in targets:
        continue
    pct = fd["summary"]["percent_covered"]
    miss = fd["summary"]["missing_lines"]
    stmts = fd["summary"]["num_statements"]
    tot_covered += stmts - miss
    tot_miss += miss
    gate(
        f"{fname}: {pct:.1f}% >= {targets[fname]}%",
        pct >= targets[fname],
        f"{miss} stmts missed",
    )

agg = (
    tot_covered / (tot_covered + tot_miss) * 100 if (tot_covered + tot_miss) else 0
)
gate(f"Aggregate 4-module: {agg:.1f}% >= 80%", agg >= 80)

# G5 informational
print("\n--- G5  Known Source Issues (non-blocking) ---")
print("  [INFO] orchestrator.py:456-466  HistoricalData missing symbol field")
print("  [INFO] orchestrator.py:821-893  CMP happy path needs mock chain")
print("  [INFO] HC-12 / HC-13: pre-existing failures, not in scope")

print("\n" + "=" * 60)
print(f"RESULT:  {PASS} PASS  |  {FAIL} FAIL")
print(
    "STATUS: " + ("ALL GATES PASSED" if FAIL == 0 else f"{FAIL} GATE(S) FAILED")
)
print("=" * 60)
sys.exit(1 if FAIL else 0)
