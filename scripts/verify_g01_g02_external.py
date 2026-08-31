#!/usr/bin/env python3
"""External verification for G01 (pytest all) and G02 (coverage floor).

ASCII-safe for Windows subprocess capture. Exit 0 iff every check passes.

Usage:
    python scripts/verify_g01_g02_external.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("OPENALGO_API_KEY", "test-health-check-key")
os.environ.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
os.environ.setdefault("OPENALGO_MODE", "ANALYZE")


def get_project_root() -> Path:
    """Resolve repo root from this script or cwd markers."""
    try:
        script_file = Path(__file__).resolve()
        if "scripts" in script_file.parts:
            idx = script_file.parts.index("scripts")
            return Path(*script_file.parts[:idx])
    except (NameError, Exception):
        pass
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "scripts").exists():
            return parent
    return cwd


ROOT = get_project_root()


def _resolve_python() -> str:
    candidates = [
        ROOT / "loatsNEW" / "Scripts" / "python.exe",
        ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()
PASS, FAIL = "[PASS]", "[FAIL]"


def _ok(name: str, passed: bool, details: str = "") -> bool:
    mark = PASS if passed else FAIL
    print(f"  {mark} {name}")
    if details:
        print(f"       {details}")
    return passed


def check_g02_catalog() -> bool:
    print("\n=== G02 CATALOG (per-module coverage, not full-suite --cov) ===")
    path = ROOT / "scripts" / "fr7_health_check.py"
    text = path.read_text(encoding="utf-8")
    ok = True
    ok &= _ok(
        "G02 uses check_per_module_coverage.py",
        "check_per_module_coverage.py" in text and 'id="G02"' in text,
    )
    ok &= _ok(
        "G02 does not re-run full pytest --cov-fail-under",
        "--cov-fail-under=80"
        not in text.split('id="G02"', 1)[-1].split('id="G03"', 1)[0],
    )
    ok &= _ok("TODO-15 referenced in health check", "TODO-15" in text)
    ok &= _ok("TODO-24 referenced in health check", "TODO-24" in text)
    # timeout for G02 should be a file-check, not 120s suite
    g02_block = text.split('id="G02"', 1)[-1].split("Check(", 1)[0]
    ok &= _ok(
        "G02 timeout is short (file check)",
        "timeout=30" in g02_block or "timeout=20" in g02_block,
        g02_block[g02_block.find("timeout") : g02_block.find("timeout") + 16]
        if "timeout" in g02_block
        else "timeout missing",
    )
    return ok


def check_g01_timeout() -> bool:
    print("\n=== G01 CATALOG (full suite needs >120s) ===")
    text = (ROOT / "scripts" / "fr7_health_check.py").read_text(encoding="utf-8")
    g01_block = text.split('id="G01"', 1)[-1].split("Check(", 1)[0]
    # timeout=400 (or any value >= 300)
    import re

    m = re.search(r"timeout\s*=\s*(\d+)", g01_block)
    timeout = int(m.group(1)) if m else 0
    return _ok(
        "G01 timeout >= 300s (suite measured 245s without coverage)",
        timeout >= 300,
        f"timeout={timeout}",
    )


def check_greeks_fallback() -> bool:
    print("\n=== GREEKS FAIL-SAFE FALLBACK ===")
    src = (ROOT / "src" / "loats" / "options.py").read_text(encoding="utf-8")
    ok = True
    ok &= _ok(
        "_fallback_greeks takes S and K",
        "def _fallback_greeks(" in src and "S: float" in src,
    )
    ok &= _ok(
        "ATM intrinsic: delta 1 only if S > K",
        "delta_val = 1.0 if S > K else 0.0" in src,
    )
    ok &= _ok(
        "call sites pass S, K into fallback",
        src.count("_fallback_greeks(option_type, sigma, S, K)") >= 2,
    )
    return ok


def check_audit_commit() -> bool:
    print("\n=== AUDIT DUAL-WRITE COMMIT (sync lock root cause) ===")
    src = (ROOT / "src" / "loats" / "database.py").read_text(encoding="utf-8")
    # After the audit_log INSERT in _log_audit there must be conn.commit()
    idx = src.find("INSERT INTO audit_log")
    window = src[idx : idx + 1200] if idx >= 0 else ""
    ok = True
    ok &= _ok("_log_audit INSERT exists", idx >= 0)
    ok &= _ok(
        "_log_audit commits after INSERT",
        "conn.commit()" in window,
        "prevents uncommitted IMMEDIATE writer lock",
    )
    ok &= _ok(
        "PRAGMA busy_timeout present",
        "PRAGMA busy_timeout" in src,
    )
    return ok


def check_hc30_s05_test() -> bool:
    print("\n=== S05 / LEGACY HC-30 TEST ALIGNMENT ===")
    src = (ROOT / "tests" / "test_backtest_sanity_production.py").read_text(
        encoding="utf-8"
    )
    health = (ROOT / "scripts" / "fr7_health_check.py").read_text(encoding="utf-8")
    ok = True
    ok &= _ok('test asserts id="S05"', 'id="S05"' in src)
    ok &= _ok(
        "test no longer requires missing verify_todo26_external.py",
        "verify_todo26_external.py" not in src,
    )
    ok &= _ok(
        "S05 still in health catalogue", 'id="S05"' in health and "TODO-26" in health
    )
    ok &= _ok("S05 mentions backtest_sanity.py", "backtest_sanity.py" in health)
    return ok


def run_targeted_pytest() -> bool:
    print("\n=== TARGETED PYTEST (previously failing G01 cases) ===")
    tests = [
        "tests/test_backtest_sanity_production.py::TestHealthCheckIntegration::test_hc30_exists",
        "tests/test_options_coverage.py::TestOptionsCoverage::test_calculate_greeks_exception_fallback",
        "tests/test_options_var.py::TestGreeksFallbacks::test_calculate_greeks_numerical_error_call",
        "tests/test_options_var.py::TestGreeksFallbacks::test_calculate_greeks_numerical_error_put",
        "tests/test_audit_dual_write.py",
        "tests/test_e2e_cmp_chain.py::TestE2ECMPChain::test_cmp_chain_with_opposing_signals",
    ]
    cmd = [PY, "-m", "pytest", *tests, "-q", "--tb=line"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
    except Exception:
        traceback.print_exc()
        return _ok("targeted pytest ran", False)
    tail = (proc.stdout or "")[-400:]
    return _ok(
        "targeted pytest exit 0",
        proc.returncode == 0,
        tail.replace("\n", " | ")[:300],
    )


def run_g02_script() -> bool:
    print("\n=== G02 SCRIPT (check_per_module_coverage.py) ===")
    cov = ROOT / "coverage.json"
    if not cov.exists():
        return _ok("coverage.json exists", False)
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "check_per_module_coverage.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = True
    ok &= _ok(
        "check_per_module_coverage.py exit 0",
        proc.returncode == 0,
        out[-200:].replace("\n", " | "),
    )
    ok &= _ok(
        "floor-mapped gates PASSED in output",
        "Floor-mapped coverage gates: PASSED" in out,
    )
    return ok


def run_health_g02() -> bool:
    print("\n=== FR7 HEALTH --only G02 ===")
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "fr7_health_check.py"), "--only", "G02"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return _ok(
        "health G02 exit 0",
        proc.returncode == 0 and "G02" in out,
        f"exit={proc.returncode}",
    )


def main() -> int:
    print("=" * 70)
    print("G01 / G02 external verification")
    print(f"root: {ROOT}")
    print(f"py:   {PY}")
    print("=" * 70)
    results = [
        ("G02 catalog", check_g02_catalog()),
        ("G01 timeout", check_g01_timeout()),
        ("Greeks fallback", check_greeks_fallback()),
        ("Audit commit", check_audit_commit()),
        ("S05 test", check_hc30_s05_test()),
        ("Targeted pytest", run_targeted_pytest()),
        ("G02 script", run_g02_script()),
        ("Health G02", run_health_g02()),
    ]
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = 0
    for name, ok in results:
        print(f"  {PASS if ok else FAIL} {name}")
        if ok:
            passed += 1
    print(f"\n{passed}/{len(results)} groups passed")
    if passed != len(results):
        print("[FAIL] G01/G02 verification")
        return 1
    print("[PASS] G01/G02 verification")
    return 0


if __name__ == "__main__":
    sys.exit(main())
