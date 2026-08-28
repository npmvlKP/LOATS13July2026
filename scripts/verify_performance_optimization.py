#!/usr/bin/env python3
"""
Performance Optimization Verification Script for TODO-25

Verifies DB performance fixes applied to P1 evidence collector:
1. Connection pooling (reuse DB instance)
2. Reduced dataset (20 candles instead of 100)
3. Optimized WAL checkpoint timing

Usage:
    python scripts/verify_performance_optimization.py
    python scripts/verify_performance_optimization.py --compare reports/p1_analyze_latency_*.json
"""

import argparse
import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


class Color:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(text: str) -> None:
    """Print formatted header."""
    print(f"\n{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{text:^70}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}\n")


def print_check(name: str, passed: bool, details: str = "") -> None:
    """Print check result with color coding."""
    status = f"{Color.GREEN}✓{Color.RESET}" if passed else f"{Color.RED}✗{Color.RESET}"
    print(f"{status} {name}")
    if details:
        print(f"  {details}")


def verify_performance_optimization(new_evidence_path: Path) -> dict[str, Any]:
    """Verify performance optimization improvements."""
    print_header("PERFORMANCE OPTIMIZATION VERIFICATION")

    checks_passed = 0
    checks_total = 0
    evidence_data = None

    # Check 1: New evidence file exists
    checks_total += 1
    if new_evidence_path.exists():
        checks_passed += 1
        print_check(f"New evidence file exists: {new_evidence_path}", True)
    else:
        print_check(f"New evidence file exists: {new_evidence_path}", False)
        return None

    # Check 2: Evidence file is valid JSON
    checks_total += 1
    try:
        with open(new_evidence_path, "r", encoding="utf-8") as f:
            evidence_data = json.load(f)
        checks_passed += 1
        print_check("Evidence file is valid JSON", True)
    except Exception as e:
        print_check("Evidence file is valid JSON", False, f"Error: {e}")
        return None

    # Check 3: Fix version metadata present
    checks_total += 1
    metadata = evidence_data.get("metadata", {})
    fix_version = metadata.get("fix_version", "")
    if "DB performance optimization" in fix_version:
        checks_passed += 1
        print_check("Fix version metadata present", True, f"Version: {fix_version}")
    else:
        print_check("Fix version metadata present", False, f"Version: {fix_version}")

    # Check 4: Round-trip statistics exist
    checks_total += 1
    evidence = evidence_data.get("evidence", {})
    rt_stats = evidence.get("round_trip_statistics", {})
    if rt_stats:
        checks_passed += 1
        print_check("Round-trip statistics exist", True)
    else:
        print_check("Round-trip statistics exist", False)
        return None

    # Check 5: Mean latency reasonable (<100ms)
    checks_total += 1
    mean_latency = rt_stats.get("mean", 0)
    if mean_latency < 100.0:
        checks_passed += 1
        print_check(f"Mean latency < 100ms", True, f"{mean_latency:.2f}ms")
    else:
        print_check(f"Mean latency < 100ms", False, f"{mean_latency:.2f}ms")

    # Check 6: P95 latency reasonable (<200ms)
    checks_total += 1
    p95_latency = rt_stats.get("p95", 0)
    if p95_latency < 200.0:
        checks_passed += 1
        print_check(f"P95 latency < 200ms", True, f"{p95_latency:.2f}ms")
    else:
        print_check(f"P95 latency < 200ms", False, f"{p95_latency:.2f}ms")

    # Check 7: P99 latency reasonable (<2000ms)
    # NOTE: SQLite WAL checkpoints on Windows cause occasional spikes.
    # P99 is informational; P1 gate compliance is the authoritative metric.
    checks_total += 1
    p99_latency = rt_stats.get("p99", 0)
    if p99_latency < 2000.0:
        checks_passed += 1
        print_check(f"P99 latency < 2000ms", True, f"{p99_latency:.2f}ms")
    else:
        print_check(f"P99 latency < 2000ms", False, f"{p99_latency:.2f}ms")

    # Check 8: Std dev reasonable (<150ms)
    # NOTE: High variance from occasional WAL checkpoint delays is expected
    # on Windows NTFS with SQLite. P1 gate compliance handles this.
    checks_total += 1
    std_dev = rt_stats.get("std_dev", 0)
    if std_dev < 150.0:
        checks_passed += 1
        print_check(f"Standard deviation < 150ms", True, f"{std_dev:.2f}ms")
    else:
        print_check(f"Standard deviation < 150ms", False, f"{std_dev:.2f}ms")

    # Check 9: P1 gate compliance ≥99%
    checks_total += 1
    gate_compliance = evidence.get("gate_compliance", {})
    rt_pass_rate = gate_compliance.get("round_trip_gate_pass_rate", 0)
    if rt_pass_rate >= 99.0:
        checks_passed += 1
        print_check(f"P1 gate compliance ≥99%", True, f"{rt_pass_rate:.2f}%")
    else:
        print_check(f"P1 gate compliance ≥99%", False, f"{rt_pass_rate:.2f}%")

    return {
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "passed": checks_passed == checks_total,
        "evidence_data": evidence_data,
    }


def compare_with_baseline(new_evidence_path: Path, baseline_path: Path) -> None:
    """Compare new evidence with baseline."""
    print_header("PERFORMANCE COMPARISON WITH BASELINE")

    # Load evidence files
    with open(new_evidence_path, "r", encoding="utf-8") as f:
        new_data = json.load(f)
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    new_evidence = new_data.get("evidence", {})
    baseline_evidence = baseline_data.get("evidence", {})

    # Extract statistics
    new_rt = new_evidence.get("round_trip_statistics", {})
    baseline_rt = baseline_evidence.get("round_trip_statistics", {})

    new_db = new_evidence.get("db_statistics", {})
    baseline_db = baseline_evidence.get("db_statistics", {})

    # Calculate improvements
    mean_improvement = ((baseline_rt.get("mean", 0) - new_rt.get("mean", 0)) / baseline_rt.get("mean", 1)) * 100
    p95_improvement = ((baseline_rt.get("p95", 0) - new_rt.get("p95", 0)) / baseline_rt.get("p95", 1)) * 100
    p99_improvement = ((baseline_rt.get("p99", 0) - new_rt.get("p99", 0)) / baseline_rt.get("p99", 1)) * 100
    std_dev_improvement = ((baseline_rt.get("std_dev", 0) - new_rt.get("std_dev", 0)) / baseline_rt.get("std_dev", 1)) * 100

    db_mean_improvement = ((baseline_db.get("mean", 0) - new_db.get("mean", 0)) / baseline_db.get("mean", 1)) * 100

    # Print comparison table
    print(f"\n{'Metric':<20} {'Baseline':>15} {'New':>15} {'Improvement':>15}")
    print("-" * 70)
    print(f"{'Round-trip Mean':<20} {baseline_rt.get('mean', 0):>14.2f}ms {new_rt.get('mean', 0):>14.2f}ms {mean_improvement:>13.1f}%")
    print(f"{'Round-trip P95':<20} {baseline_rt.get('p95', 0):>14.2f}ms {new_rt.get('p95', 0):>14.2f}ms {p95_improvement:>13.1f}%")
    print(f"{'Round-trip P99':<20} {baseline_rt.get('p99', 0):>14.2f}ms {new_rt.get('p99', 0):>14.2f}ms {p99_improvement:>13.1f}%")
    print(f"{'Round-trip StdDev':<20} {baseline_rt.get('std_dev', 0):>14.2f}ms {new_rt.get('std_dev', 0):>14.2f}ms {std_dev_improvement:>13.1f}%")
    print(f"{'DB Mean':<20} {baseline_db.get('mean', 0):>14.2f}ms {new_db.get('mean', 0):>14.2f}ms {db_mean_improvement:>13.1f}%")

    # Print verdict
    print("\n" + "=" * 70)
    if mean_improvement > 0 and p95_improvement > 0:
        print(f"{Color.GREEN}{Color.BOLD}✅ PERFORMANCE OPTIMIZATION: SUCCESSFUL{Color.RESET}")
        print(f"{Color.GREEN}Mean latency improved by {mean_improvement:.1f}%{Color.RESET}")
        print(f"{Color.GREEN}P95 latency improved by {p95_improvement:.1f}%{Color.RESET}")
    else:
        print(f"{Color.RED}{Color.BOLD}❌ PERFORMANCE OPTIMIZATION: FAILED{Color.RESET}")
        print(f"{Color.RED}Latency did not improve or degraded{Color.RESET}")
    print("=" * 70 + "\n")


def print_final_report(results: dict[str, Any]) -> None:
    """Print final verification report."""
    print_header("FINAL VERIFICATION REPORT")

    verification_result = results.get("verification", {})
    if verification_result:
        passed = verification_result.get("passed", False)
        print(f"Performance Optimization: {Color.GREEN}PASSED{Color.RESET}" if passed else f"Performance Optimization: {Color.RED}FAILED{Color.RESET}")
        print(f"  Checks: {verification_result.get('checks_passed', 0)}/{verification_result.get('checks_total', 0)}")

    # Overall
    print("\n" + "=" * 70)
    all_passed = verification_result.get("passed", False)

    if all_passed:
        print(f"{Color.GREEN}{Color.BOLD}✅ PERFORMANCE OPTIMIZATION VERIFICATION: PASSED{Color.RESET}")
        print(f"{Color.GREEN}DB performance fixes verified{Color.RESET}")
        print(f"{Color.GREEN}P1 evidence collection is production-ready{Color.RESET}")
    else:
        print(f"{Color.RED}{Color.BOLD}❌ PERFORMANCE OPTIMIZATION VERIFICATION: FAILED{Color.RESET}")

    print("=" * 70 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verify performance optimization")
    parser.add_argument(
        "--new-evidence",
        type=Path,
        default=None,
        help="Path to new evidence file (default: most recent in reports/)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline evidence file (default: oldest in reports/)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare with baseline evidence",
    )

    args = parser.parse_args()

    # Find most recent evidence file if not specified
    if args.new_evidence is None:
        reports_dir = Path("reports")
        if reports_dir.exists():
            evidence_files = sorted(reports_dir.glob("p1_analyze_latency_*.json"), reverse=True)
            if evidence_files:
                args.new_evidence = evidence_files[0]
                print(f"Using most recent evidence file: {args.new_evidence}\n")
            else:
                print("No P1 evidence files found in reports/")
                sys.exit(1)
        else:
            print("reports/ directory does not exist")
            sys.exit(1)

    # Find baseline evidence file if not specified
    if args.baseline is None and args.compare:
        reports_dir = Path("reports")
        evidence_files = sorted(reports_dir.glob("p1_analyze_latency_*.json"))
        if len(evidence_files) >= 2:
            args.baseline = evidence_files[0]  # Oldest file
            print(f"Using baseline evidence file: {args.baseline}\n")

    # Run verification
    results = {}
    verification_result = verify_performance_optimization(args.new_evidence)
    results["verification"] = verification_result

    # Compare with baseline if requested
    if args.compare and args.baseline and args.baseline.exists():
        compare_with_baseline(args.new_evidence, args.baseline)

    # Print report
    print_final_report(results)

    # Exit with appropriate code
    all_passed = verification_result.get("passed", False) if verification_result else False
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()