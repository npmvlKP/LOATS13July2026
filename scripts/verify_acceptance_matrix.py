#!/usr/bin/env python3
r"""
LOATS13July2026 Acceptance Matrix Verification (TODO-14..TODO-27)
=================================================================
One-command external verification that re-executes every gate and
probe required to close the acceptance matrix.

Run from the project root with the project venv interpreter:

    loatsNEW\Scripts\python.exe scripts\verify_acceptance_matrix.py

Pass --full to also run a standalone pytest suite (the HC registry already
includes coverage, so --full is optional).  The default mode is quick and
avoids duplicate long-running suites.

Exit codes:
    0 - all acceptance checks passed
    1 - one or more checks failed

This script is deliberately self-contained, uses only the project venv,
invokes every subprocess as a list argument (shell=False), and writes
ASCII-only output so it is safe to run from a captured subprocess on Windows.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_python() -> str:
    """Prefer the project venv interpreter, fall back to sys.executable."""
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()

PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"


def safe_print(text: str) -> None:
    """Write to stdout; fall back to ASCII if Windows encoding breaks."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")
        sys.stdout.flush()


def run(
    cmd: list[str], timeout: int = 300, env_overrides: dict[str, str] | None = None
) -> tuple[int, str, str, float]:
    """Run a command in the project root and return (rc, stdout, stderr, elapsed)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if env_overrides:
        env.update(env_overrides)
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=False,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    elapsed = time.perf_counter() - start
    return proc.returncode, proc.stdout, proc.stderr, elapsed


def check(
    name: str,
    cmd: list[str],
    must_pass: bool = True,
    timeout: int = 300,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    safe_print(f"\n=== {name} ===")
    rc, out, err, elapsed = run(cmd, timeout=timeout, env_overrides=env_overrides)
    ok = rc == 0
    sym = PASS_SYM if ok else FAIL_SYM
    safe_print(f"{sym} exit={rc} elapsed={elapsed:.1f}s")
    if not ok and must_pass:
        tail = (out + "\n" + err).strip().splitlines()
        for line in tail[-20:]:
            safe_print(f"    {line}")
    return {
        "name": name,
        "ok": ok,
        "rc": rc,
        "elapsed": elapsed,
        "stdout": out,
        "stderr": err,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full",
        action="store_true",
        help="run a standalone pytest full suite in addition to the consolidated gates",
    )
    args = ap.parse_args()

    if not Path(PY).exists():
        safe_print(f"{FAIL_SYM} project venv python not found at {PY}")
        return 1

    safe_print("=" * 70)
    safe_print("LOATS13July2026 Acceptance Matrix Verification (TODO-14..TODO-27)")
    safe_print(f"Interpreter: {PY}")
    safe_print("=" * 70)

    results: list[dict[str, Any]] = []

    # Consolidated HC registry (covers most acceptance matrix items incl. HC-12 coverage)
    results.append(
        check(
            "TODO-14/16/17/18/19/20/21/27: HC registry (HC-20/24/23/21/17/22/26/27)",
            [PY, str(REPO_ROOT / "scripts" / "verify_hc_registry.py")],
            timeout=300,
        )
    )

    # Structural / quality delegate (HC-01..HC-13)
    results.append(
        check(
            "TODO-15/22/24/28: structural + quality delegate (HC-01..HC-13)",
            [PY, str(REPO_ROOT / "scripts" / "verify_hc_all.py")],
            timeout=300,
        )
    )

    # FR7 full health check (fast mode)
    results.append(
        check(
            "TODO-14..TODO-27: FR7 health check --fast",
            [PY, str(REPO_ROOT / "scripts" / "fr7_health_check.py"), "--fast"],
            timeout=300,
        )
    )

    # 4th producer / ADR verification (TODO-8 / HC-15)
    results.append(
        check(
            "TODO-8: 4th producer / ADR verification (HC-15)",
            [PY, str(REPO_ROOT / "scripts" / "verify_todo8_external.py")],
            timeout=60,
        )
    )

    # P1/P5 phase-gate evidence (TODO-25)
    results.append(
        check(
            "TODO-25: P1/P5 phase-gate evidence",
            [PY, str(REPO_ROOT / "scripts" / "verify_todo25_external.py")],
            timeout=60,
        )
    )

    # Carried-set verification (TODO-27)
    results.append(
        check(
            "TODO-27: carried-set verification (42 checks)",
            [PY, str(REPO_ROOT / "scripts" / "verify_todo27_external.py")],
            timeout=120,
        )
    )

    # Optional standalone pytest full suite + coverage
    if args.full:
        results.append(
            check(
                "TODO-15/24: pytest full suite + coverage",
                [
                    PY,
                    "-m",
                    "pytest",
                    "tests/",
                    "--cov=src",
                    "--cov-fail-under=80",
                    "--cov-report=json",
                    "-q",
                ],
                timeout=600,
            )
        )

    # Quality gates (TODO-22 / TODO-28)
    results.append(
        check(
            "TODO-22/28: ruff check",
            [
                PY,
                "-m",
                "ruff",
                "check",
                "src/",
                "tests/",
                "scripts/",
                "--config",
                str(REPO_ROOT / "pyproject.toml"),
            ],
            timeout=180,
        )
    )
    results.append(
        check(
            "TODO-22/28: ruff format check",
            [
                PY,
                "-m",
                "ruff",
                "format",
                "src/",
                "tests/",
                "scripts/",
                "--config",
                str(REPO_ROOT / "pyproject.toml"),
                "--check",
            ],
            timeout=180,
        )
    )
    results.append(
        check(
            "TODO-22/28: isort check",
            [
                PY,
                "-m",
                "isort",
                "--check-only",
                "src/",
                "tests/",
                "scripts/",
                "--settings-path",
                str(REPO_ROOT / "pyproject.toml"),
            ],
            timeout=180,
        )
    )
    results.append(
        check(
            "TODO-22/28: flake8",
            [PY, "-m", "flake8", "src/", "tests/", "scripts/"],
            timeout=180,
        )
    )
    results.append(
        check(
            "TODO-28: mypy strict",
            [
                PY,
                "-m",
                "mypy",
                "src/",
                "--strict",
                "--config-file",
                str(REPO_ROOT / "pyproject.toml"),
            ],
            timeout=300,
        )
    )

    # Security scans (TODO-20 / TODO-22)
    results.append(
        check(
            "TODO-20: bandit",
            [
                PY,
                "-m",
                "bandit",
                "-r",
                "src/",
                "-c",
                str(REPO_ROOT / "pyproject.toml"),
                "-q",
            ],
            timeout=180,
        )
    )
    results.append(
        check(
            "TODO-4/19/23: pip-audit",
            [
                PY,
                "-m",
                "pip_audit",
                "--format=json",
                "--desc",
                "-o",
                str(REPO_ROOT / "reports" / "security" / "pip-audit-20260901.json"),
            ],
            timeout=240,
        )
    )

    # Note: reports/verification-external.py is available separately.  It repeats
    # the pytest full-suite step that verify_hc_registry.py already covers
    # (HC-12), so we do not duplicate it here to keep the matrix run bounded.

    # Summary
    safe_print("\n" + "=" * 70)
    safe_print("ACCEPTANCE MATRIX VERIFICATION SUMMARY")
    safe_print("=" * 70)
    for r in results:
        sym = PASS_SYM if r["ok"] else FAIL_SYM
        safe_print(f"{sym} {r['name']} (rc={r['rc']}, {r['elapsed']:.1f}s)")

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    safe_print(f"\nTOTAL: {passed}/{total} checks passed")

    safe_print("\n" + "=" * 70)
    safe_print("TODO -> CHECK -> DONE-WHEN MAPPING")
    safe_print("=" * 70)
    mapping = [
        (
            "TODO-14 trailing driver",
            "HC-20",
            "ratchet driven per position; Rule-7-gated; audited",
        ),
        ("TODO-15 per-module blocking", "HC-13", "floors enforced in CI"),
        ("TODO-16 BUY IV<30", "HC-24", "literal 30; tests pin"),
        (
            "TODO-17 mods=25 wired/persisted/fail-closed",
            "HC-23",
            "settings=gate=25; counter survives restart",
        ),
        ("TODO-18 lazy settings x11", "HC-21", "AST scan zero; bare-env import works"),
        (
            "TODO-19 single signal engine",
            "HC-17 + review",
            "one producer path, one threshold",
        ),
        (
            "TODO-20 kill audit bypass",
            "HC-22",
            "no PYTEST_CURRENT_TEST; dual-write tested",
        ),
        ("TODO-21 untrack junk", "HC-26", "root clean; tracked count down"),
        (
            "TODO-22 ruff ignore shrink",
            "HC-05/06/07/08",
            "F401/I001/E402/PGH003 gone from ignore",
        ),
        ("TODO-23 dead weights", "review", "removed or annotated-pending"),
        ("TODO-24 cov-script exits", "review", "exit-code unit test green"),
        (
            "TODO-25 P1/P5 evidence",
            "review",
            "latency logs + forward test begun (post-13)",
        ),
        ("TODO-26 backtest driver", "review", "invoked by scheduler/job"),
        ("TODO-27 carried set", "HC-27 (c)", "queue bounded; rest per plan docs"),
    ]
    for todo, check_id, done_when in mapping:
        safe_print(f"{todo:<35} -> {check_id:<18} ({done_when})")

    if passed == total:
        safe_print("\n[SUCCESS] All acceptance matrix checks passed.")
        return 0

    safe_print("\n[FAILED] One or more acceptance matrix checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
