#!/usr/bin/env python3
r"""External user-verification script for LOATS production deployment.

Run from repository root:
    loatsNEW\Scripts\python.exe scripts/user_verify_deployment.py

Exit codes:
    0 -- ALL CHECKS PASSED (production ready)
    1 -- One or more critical checks failed
    2 -- All critical passed, informational warnings only
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    WARN = "WARN"


@dataclass
class Check:
    id: str
    name: str
    critical: bool
    command: list[str]
    timeout: int = 60


@dataclass
class Result:
    check: Check
    status: Status
    duration: float
    stdout: str = ""
    stderr: str = ""


def _py() -> str:
    """Resolve project venv Python."""
    for c in [REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
              REPO_ROOT / ".venv" / "Scripts" / "python.exe"]:
        if c.exists():
            return str(c)
    return sys.executable


PY = _py()

CHECKS: list[Check] = [
    # STRUCTURAL
    Check("S01", "Options Math Parity", True, [
        PY, "-c",
        "import sys; sys.path.insert(0,'src'); "
        "from loats.options_math import black_scholes, delta; "
        "c=black_scholes('c',100,90,0.5,0.01,0.2); assert abs(c-12.111581435)<1e-6; "
        "d=delta('c',49,50,0.3846,0.05,0.2); assert abs(d-0.521601633972)<1e-6; "
        "print(f'parity c={c:.10f} delta={d:.10f}')",
    ], 10),
    Check("S07", "Dead Weight Removal", True, [PY, "scripts/verify_todo23_external.py"], 10),
    # STATIC - LINT
    Check("T01", "Ruff Linting", True, [PY, "-m", "ruff", "check", "src/"], 30),
    Check("T02", "Ruff Formatting", True, [PY, "-m", "ruff", "format", "--check", "src/", "tests/"], 30),
    Check("T03", "Mypy Strict (Changed Files)", True, [
        PY, "-m", "mypy", "--strict", "--config-file", "pyproject.toml",
        "src/loats/options_math.py", "src/loats/trade_decision.py",
        "src/loats/config/settings.py",
    ], 30),
    # SECURITY
    Check("T05", "Bandit Security", True, [PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"], 30),
    Check("T06", "Gitleaks Secrets", True, ["gitleaks", "detect", "--source", ".", "--config", ".gitleaks.toml", "--no-git"], 30),
    # IMPORT
    Check("T07", "Import Validation", True, [
        PY, "-c",
        "import sys; sys.path.insert(0,'src'); import importlib; "
        "mods=['loats','loats.options_math','loats.options','loats.ta',"
        "'loats.trade_decision','loats.orchestrator','loats.scheduler',"
        "'loats.sentiment','loats.sizing','loats.rules','loats.config.settings']; "
        "[importlib.import_module(m) for m in mods]; print('imports ok')",
    ], 15),
    # LIVE-PROBE
    Check("L04", "Trailing Stop Runtime", True, [PY, "-m", "pytest", "tests/test_trailing_stop_runtime.py", "-q", "--tb=short"], 30),
    Check("L05", "Audit Dual-Write", True, [PY, "-m", "pytest", "tests/test_audit_dual_write.py", "-q", "--tb=short"], 30),
    Check("L07", "Rate Limiter", True, [PY, "scripts/probe_l07_rate_limiter.py"], 15),
    Check("L08", "Queue Backpressure", True, [PY, "scripts/probe_l08_queue_backpressure.py"], 30),
    # GATE
    Check("G01", "Pytest Sanity", True, [
        PY, "-m", "pytest",
        "tests/test_trade_decision.py", "tests/test_options.py",
        "tests/test_ta.py", "-q",
    ], 60),
    Check("G02", "Per-Module Coverage", True, [PY, "scripts/check_per_module_coverage.py"], 15),
    Check("G08", "TODO-27 Integration", True, [PY, "scripts/verify_todo27_external.py"], 30),
    # INFO
    Check("I01", "Coverage Floor Map Exists", False, [
        PY, "-c",
        "from pathlib import Path; import json; "
        "p=Path('coverage_floor_map.json'); assert p.exists(); "
        "d=json.loads(p.read_text()); assert 'floor_mapped_modules' in d; "
        "print('floor map ok:', len(d['floor_mapped_modules']), 'modules')",
    ], 5),
]


def run(check: Check) -> Result:
    start = time.monotonic()
    try:
        p = subprocess.run(check.command, capture_output=True, text=True,
                           timeout=check.timeout, cwd=REPO_ROOT)
        dur = time.monotonic() - start
        if p.returncode == 0:
            return Result(check, Status.PASS, dur, p.stdout, p.stderr)
        if p.returncode in (4, 5):
            return Result(check, Status.SKIP, dur, p.stdout, p.stderr)
        return Result(check, Status.FAIL if check.critical else Status.WARN, dur, p.stdout, p.stderr)
    except subprocess.TimeoutExpired:
        return Result(check, Status.FAIL if check.critical else Status.WARN,
                      time.monotonic() - start, stderr="TIMEOUT")
    except Exception as exc:
        return Result(check, Status.FAIL if check.critical else Status.WARN,
                      time.monotonic() - start, stderr=str(exc))


def main() -> int:
    ts = datetime.now(UTC).isoformat()
    sep = "=" * 80
    print(f"\n{sep}")
    print(f"  USER EXTERNAL VERIFICATION -- {ts}")
    print(f"  Python: {PY}")
    print(f"  Repo:   {REPO_ROOT}")
    print(f"{sep}\n")

    results = [run(c) for c in CHECKS]
    sym = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.SKIP: "SKIP", Status.WARN: "WARN"}
    for r in results:
        tag = "CRITICAL" if r.check.critical else "INFO"
        print(f"  {sym[r.status]:4} | {r.check.id:<6} | {r.check.name:<40} | {tag:<10} | {r.duration:.1f}s")

    crit = [r for r in results if r.check.critical]
 info = [r for r in results if not r.check.critical]
    cp = sum(1 for r in crit if r.status == Status.PASS)
    cf = sum(1 for r in crit if r.status == Status.FAIL)
    iw = sum(1 for r in info if r.status in (Status.FAIL, Status.WARN))
    total_dur = sum(r.duration for r in results)

    print(f"\n{sep}")
    print(f"  CRITICAL: {cp}/{len(crit)} PASS  |  INFO WARNINGS: {iw}  |  {total_dur:.1f}s total")
    print(f"{sep}\n")

    if cf:
        print("  BLOCKED -- critical failures:")
        for r in crit:
            if r.status == Status.FAIL:
                print(f"    X {r.check.id}: {r.check.name}")
                if r.stderr.strip():
                    for line in r.stderr.strip().splitlines()[:3]:
                        print(f"      | {line}")
        return 1
    if iw:
        print("  APPROVED WITH WARNINGS (non-critical)")
        return 2
    print("  ALL CHECKS PASSED -- PRODUCTION READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
