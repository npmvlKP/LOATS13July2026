#!/usr/bin/env python3
"""
FR7 Final Comprehensive Verification Script.

This script performs a complete external verification that all FR7
health check fixes are in place and working correctly. It provides
detailed output suitable for production sign-off and can be run
independently as a final gate before deployment.

Usage:
    python scripts/fr7_final_verification.py
    python scripts/fr7_final_verification.py --verbose
    python scripts/fr7_final_verification.py --json verification.json

Exit Codes:
    0 - All verifications passed
    1 - One or more verifications failed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Repository root
REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_python() -> str:
    """Resolve the Python interpreter to use."""
    for cand in [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


@dataclass
class VerificationResult:
    """Result of a single verification check."""

    name: str
    category: str
    passed: bool
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def run_verification(
    name: str,
    category: str,
    command: list[str],
    timeout: int = 300,
    workdir: Path | None = None,
) -> VerificationResult:
    """Run a single verification check."""
    start_time = datetime.now(UTC)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or REPO_ROOT,
        )

        duration = (datetime.now(UTC) - start_time).total_seconds()

        return VerificationResult(
            name=name,
            category=category,
            passed=result.returncode == 0,
            duration_seconds=duration,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )

    except subprocess.TimeoutExpired as e:
        duration = (datetime.now(UTC) - start_time).total_seconds()
        return VerificationResult(
            name=name,
            category=category,
            passed=False,
            duration_seconds=duration,
            stdout=e.stdout if e.stdout else "",
            stderr=e.stderr if e.stderr else "Command timed out",
            exit_code=1,
        )
    except Exception as e:
        duration = (datetime.now(UTC) - start_time).total_seconds()
        return VerificationResult(
            name=name,
            category=category,
            passed=False,
            duration_seconds=duration,
            stderr=str(e),
            exit_code=1,
        )


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}\n")


def print_result(result: VerificationResult, verbose: bool = False) -> None:
    """Print a single verification result."""
    status = "✓ PASS" if result.passed else "✗ FAIL"
    print(f"  {status} | {result.name:<50} | {result.duration_seconds:.1f}s")

    if verbose:
        if result.stdout.strip():
            print(f"\n  ┌─ stdout ({len(result.stdout)} chars):")
            stdout_lines = result.stdout.strip().split("\n")
            for line in stdout_lines[:10]:  # Show first 10 lines
                print(f"  │ {line}")
            if len(stdout_lines) > 10:
                print(f"  │ ... ({len(stdout_lines) - 10} more lines)")
            print(f"  └─")

        if result.stderr.strip():
            print(f"\n  ┌─ stderr ({len(result.stderr)} chars):")
            stderr_lines = result.stderr.strip().split("\n")
            for line in stderr_lines[:10]:  # Show first 10 lines
                print(f"  │ {line}")
            if len(stderr_lines) > 10:
                print(f"  │ ... ({len(stderr_lines) - 10} more lines)")
            print(f"  └─")


def generate_report(
    results: list[VerificationResult],
    verbose: bool = False,
    json_path: str | None = None,
) -> dict[str, any]:
    """Generate a comprehensive verification report."""

    timestamp = datetime.now(UTC).isoformat()

    # Group results by category
    by_category: dict[str, list[VerificationResult]] = {}
    for result in results:
        if result.category not in by_category:
            by_category[result.category] = []
        by_category[result.category].append(result)

    # Calculate statistics
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_duration = sum(r.duration_seconds for r in results)

    report = {
        "timestamp": timestamp,
        "timestamp_utc": timestamp,
        "repo_root": str(REPO_ROOT),
        "python": PY,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": f"{(passed / total * 100):.1f}%" if total else "0%",
            "total_duration_seconds": round(total_duration, 2),
            "healthy": failed == 0,
        },
        "categories": {},
        "results": [],
    }

    # Print console report
    print_header(f"FR7 FINAL COMPREHENSIVE VERIFICATION — {timestamp}")

    for category in sorted(by_category.keys()):
        category_results = by_category[category]
        cat_passed = sum(1 for r in category_results if r.passed)
        cat_total = len(category_results)

        print(f"\n{category.upper():<20} | {cat_passed}/{cat_total} PASS")
        print("-" * 80)

        for result in category_results:
            print_result(result, verbose)

        # Add category to report
        report["categories"][category] = {
            "total": cat_total,
            "passed": cat_passed,
            "failed": cat_total - cat_passed,
        }

    # Final summary
    print_header(f"FINAL SUMMARY — {passed}/{total} PASSED ({(passed/total*100):.1f}%)")

    if failed == 0:
        print(f"✓ ALL VERIFICATIONS PASSED — Production Ready")
        print(f"  Total Duration: {total_duration:.1f}s")
    else:
        print(f"✗ {failed} VERIFICATION(S) FAILED — Review output above")

    # Add detailed results to report
    for result in results:
        report["results"].append(
            {
                "name": result.name,
                "category": result.category,
                "status": "PASS" if result.passed else "FAIL",
                "duration_seconds": round(result.duration_seconds, 3),
                "exit_code": result.exit_code,
                "stdout_tail": result.stdout[-1000:] if result.stdout else "",
                "stderr_tail": result.stderr[-1000:] if result.stderr else "",
            }
        )

    # Write JSON report if requested
    if json_path:
        json_path_obj = Path(json_path)
        json_path_obj.parent.mkdir(parents=True, exist_ok=True)
        json_path_obj.write_text(json.dumps(report, indent=2))
        print(f"\n✓ JSON report written to: {json_path}")

    return report


def main() -> int:
    """Run all verification checks."""
    parser = argparse.ArgumentParser(
        description="FR7 Final Comprehensive Verification Script"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed output for each check"
    )
    parser.add_argument(
        "--json", type=str, help="Write JSON report to specified path"
    )
    parser.add_argument(
        "--fast", action="store_true", help="Run only fast verifications"
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=["structural", "static", "live-probe", "gate"],
        help="Run only a specific category of verifications",
    )

    args = parser.parse_args()

    # Define verification checks
    all_verifications = [
        # STRUCTURAL
        (
            "S01: Options Math Parity",
            "structural",
            [PY, "-c", "import pathlib, sys; p=pathlib.Path('src/loats/options_math.py'); assert p.exists(), 'missing options_math.py'; sys.path.insert(0,'src'); from loats.options_math import black_scholes, delta; c=black_scholes('c',100,90,0.5,0.01,0.2); assert abs(c-12.111581435)<1e-6, f'parity {c}'; d=delta('c',49,50,0.3846,0.05,0.2); assert abs(d-0.521601633972)<1e-6, f'delta {d}'; print(f'parity c={c:.10f} delta={d:.10f}')"],
        ),
        (
            "S07: Dead Weight Removal",
            "structural",
            [PY, "scripts/verify_todo23_external.py"],
        ),
        # STATIC
        (
            "T01: Ruff Linting",
            "static",
            [PY, "-m", "ruff", "check", "src/"],
        ),
        (
            "T02: Ruff Formatting",
            "static",
            [PY, "-m", "ruff", "format", "--check", "src/", "tests/"],
        ),
        (
            "T03: Mypy Strict (Changed Files)",
            "static",
            [PY, "-m", "mypy", "src/loats/options_math.py", "src/loats/trade_decision.py", "src/loats/config/settings.py", "--strict", "--config-file", "pyproject.toml"],
        ),
        (
            "T08: Function Size/Complexity",
            "static",
            [PY, "scripts/check_function_size.py"],
        ),
        # GATE
        (
            "G02: Per-Module Coverage",
            "gate",
            [PY, "scripts/check_per_module_coverage.py"],
        ),
        (
            "G08: TODO-27 Integration",
            "gate",
            [PY, "scripts/verify_todo27_external.py"],
        ),
    ]

    # Additional checks for comprehensive run (not fast)
    comprehensive_verifications = [
        (
            "T05: Bandit Security",
            "static",
            [PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"],
        ),
        (
            "G01: Pytest Sanity",
            "gate",
            [PY, "-m", "pytest", "tests/test_trade_decision.py", "tests/test_options.py", "tests/test_ta.py", "-q"],
        ),
    ]

    # Select verifications to run
    if args.category:
        verifications = [v for v in all_verifications + comprehensive_verifications if v[1] == args.category]
    elif args.fast:
        verifications = all_verifications
    else:
        verifications = all_verifications + comprehensive_verifications

    # Run all verifications
    results = []
    for name, category, command in verifications:
        print(f"\nRunning: {name}...")
        result = run_verification(name, category, command)
        results.append(result)

        # Print immediate result
        status = "✓" if result.passed else "✗"
        print(f"  {status} {name} ({result.duration_seconds:.1f}s)")

    # Generate and print final report
    report = generate_report(results, args.verbose, args.json)

    # Exit with appropriate code
    return 0 if report["summary"]["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())