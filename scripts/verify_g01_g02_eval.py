#!/usr/bin/env python3
"""10-case before/after eval for G01 pytest-all and G02 coverage-floor.

BEFORE scores are the forensic baseline captured 2026-08-31 from:
  python scripts/fr7_health_check.py  -> G01 FAIL 7.3s, G02 TIMEOUT 120s
  pytest tests/ -q                     -> 5 failed / 1124 passed / 245s

AFTER is measured live against the current repository.

Usage:
    python scripts/verify_g01_g02_eval.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("OPENALGO_API_KEY", "test-health-check-key")
os.environ.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
os.environ.setdefault("OPENALGO_MODE", "ANALYZE")


def get_project_root() -> Path:
    try:
        script_file = Path(__file__).resolve()
        if "scripts" in script_file.parts:
            idx = script_file.parts.index("scripts")
            return Path(*script_file.parts[:idx])
    except Exception:
        pass
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "scripts").exists():
            return parent
    return cwd


ROOT = get_project_root()
PY = str(
    next(
        (
            p
            for p in (
                ROOT / "loatsNEW" / "Scripts" / "python.exe",
                ROOT / ".venv" / "Scripts" / "python.exe",
            )
            if p.exists()
        ),
        Path(sys.executable),
    )
)

# Forensic BEFORE (do not "improve" these; they are the measured baseline).
BEFORE: dict[str, bool] = {
    "C1 G01 first-fail is not HC-30 string mismatch": False,
    "C2 ATM call greeks fallback delta==0": False,
    "C3 ATM put greeks fallback delta==0": False,
    "C4 G02 command is check_per_module_coverage.py": False,
    "C5 G02 does not full-suite --cov-fail-under=80": False,
    "C6 G01 timeout >= 300s": False,
    "C7 _log_audit conn.commit after INSERT": False,
    "C8 PRAGMA busy_timeout on sync connections": False,
    "C9 per-module coverage floor script exits 0": True,
    "C10 S05 still wires backtest_sanity.py": True,
}


def _health_text() -> str:
    return (ROOT / "scripts" / "fr7_health_check.py").read_text(encoding="utf-8")


def _g02_block() -> str:
    text = _health_text()
    return text.split('id="G02"', 1)[-1].split("Check(", 1)[0]


def _g01_timeout() -> int:
    text = _health_text()
    block = text.split('id="G01"', 1)[-1].split("Check(", 1)[0]
    m = re.search(r"timeout\s*=\s*(\d+)", block)
    return int(m.group(1)) if m else 0


def _pytest_one(nodeid: str) -> bool:
    proc = subprocess.run(
        [PY, "-m", "pytest", nodeid, "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    return proc.returncode == 0


def measure_after() -> dict[str, bool]:
    health = _health_text()
    g02 = _g02_block()
    db = (ROOT / "src" / "loats" / "database.py").read_text(encoding="utf-8")
    idx = db.find("INSERT INTO audit_log")
    audit_window = db[idx : idx + 1200] if idx >= 0 else ""
    cov_proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "check_per_module_coverage.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return {
        "C1 G01 first-fail is not HC-30 string mismatch": _pytest_one(
            "tests/test_backtest_sanity_production.py::TestHealthCheckIntegration::test_hc30_exists"
        ),
        "C2 ATM call greeks fallback delta==0": _pytest_one(
            "tests/test_options_var.py::TestGreeksFallbacks::test_calculate_greeks_numerical_error_call"
        ),
        "C3 ATM put greeks fallback delta==0": _pytest_one(
            "tests/test_options_var.py::TestGreeksFallbacks::test_calculate_greeks_numerical_error_put"
        ),
        "C4 G02 command is check_per_module_coverage.py": "check_per_module_coverage.py"
        in g02,
        "C5 G02 does not full-suite --cov-fail-under=80": "--cov-fail-under=80"
        not in g02,
        "C6 G01 timeout >= 300s": _g01_timeout() >= 300,
        "C7 _log_audit conn.commit after INSERT": "conn.commit()" in audit_window,
        "C8 PRAGMA busy_timeout on sync connections": "PRAGMA busy_timeout" in db,
        "C9 per-module coverage floor script exits 0": cov_proc.returncode == 0,
        "C10 S05 still wires backtest_sanity.py": 'id="S05"' in health
        and "backtest_sanity.py" in health,
    }


def main() -> int:
    print("=" * 70)
    print("G01/G02 10-case eval")
    print("=" * 70)
    after = measure_after()
    before_score = sum(1 for v in BEFORE.values() if v)
    after_score = sum(1 for v in after.values() if v)
    print(f"\n{'CASE':<52} {'BEFORE':<8} AFTER")
    print("-" * 70)
    for key in BEFORE:
        b = "PASS" if BEFORE[key] else "FAIL"
        a = "PASS" if after[key] else "FAIL"
        print(f"{key:<52} {b:<8} {a}")
    print("-" * 70)
    print(
        f"SCORE  BEFORE {before_score}/10  ->  AFTER {after_score}/10  delta {after_score - before_score:+d}"
    )
    if after_score < 10:
        print("[FAIL] eval did not reach 10/10")
        return 1
    print("[PASS] eval 10/10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
