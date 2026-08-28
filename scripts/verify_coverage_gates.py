"""FR7 Coverage Gate Verification.

Usage:  python scripts/verify_coverage_gates.py

Prerequisites:  coverage.json in project root (from prior pytest --cov run).

Validates:
    1. All 5 test files exist and parse as valid Python.
    2. No temporary _*.py files in project root.
    3. Per-module coverage >= 80% for the 4 target modules.
    4. Aggregate 4-module coverage >= 80%.
"""

import ast
import json
import sys
from pathlib import Path

PASS = FAIL = 0

def gate(name, ok, detail=""):
    global PASS, FAIL
    PASS += (1 if ok else 0)
    FAIL += (0 if ok else 1)
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}{'  --  ' + detail if detail else ''}")

print("=" * 60)
print("FR7 Coverage Gate Verification")
print("=" * 60)

# G1
print("G1  Test File Integrity")
for tf in ["tests/test_trailing_stop.py", "tests/test_trade_decision.py",
           "tests/test_options_var.py", "tests/test_orchestrator.py",
           "tests/test_orchestrator_extra.py"]:
    p = Path(tf)
    if not p.exists():
        gate(f"{tf}", False, "missing"); continue
    try:
        tree = ast.parse(p.read_text("utf-8"))
        n = sum(1 for nd in ast.walk(tree) if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef)))
        gate(f"{tf}", True, f"{len(p.read_text('utf-8').splitlines())} lines, {n} funcs")
    except SyntaxError as e:
        gate(f"{tf}", False, str(e))

# G2
print("G2  Temp File Cleanup")
temps = list(Path().glob("_*.py"))
gate("No _*.py temp files in root", len(temps) == 0,
     f"found {[t.name for t in temps]}" if temps else "clean")

# G3
print("G3  Coverage Data")
cov_path = Path("coverage.json")
if not cov_path.exists():
    gate("coverage.json exists", False, "run: pytest --cov=src/loats --cov-report=json")
    sys.exit(1)
gate("coverage.json exists", True, f"{cov_path.stat().st_size:,} bytes")

# G4
print("G4  Per-Module Coverage Gates")
data = json.loads(cov_path.read_text("utf-8"))
targets = {"trailing_stop.py": 80, "trade_decision.py": 80,
           "options.py": 80, "orchestrator.py": 80}
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
    gate(f"{fname}: {pct:.1f}% >= {targets[fname]}%", pct >= targets[fname],
         f"{miss} stmts missed")

agg = tot_covered / (tot_covered + tot_miss) * 100 if (tot_covered + tot_miss) else 0
gate(f"Aggregate 4-module: {agg:.1f}% >= 80%", agg >= 80)

# G5 informational
print("G5  Known Source Issues (non-blocking)")
print("  [INFO] orchestrator.py:456-466  HistoricalData missing 'symbol' field")
print("  [INFO] orchestrator.py:821-893  CMP happy path needs trade_decision mock")
print("  [INFO] HC-12: tests/test_e2e_cmp_chain.py missing (pre-existing)")

print("\n" + "=" * 60)
print(f"RESULT:  {PASS} PASS  |  {FAIL} FAIL")
print("STATUS: " + ("ALL GATES PASSED" if FAIL == 0 else f"{FAIL} GATE(S) FAILED"))
print("=" * 60)
sys.exit(1 if FAIL else 0)
