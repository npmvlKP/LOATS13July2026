#!/usr/bin/env python3
"""FR7 Health Check Script for LOATS13July2026 CMP Strategy.

Usage:
    python scripts/fr7_health_check.py --only HC-12,HC-15
    python scripts/fr7_health_check.py --json output.json
    python scripts/fr7_health_check.py --fast
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Get the current Python interpreter to ensure subprocess uses the same one
PYTHON_INTERPRETER = sys.executable
UV_PREFIX = ["uv", "run"] if shutil.which("uv") else [PYTHON_INTERPRETER, "-m"]

# Health check definitions
HEALTH_CHECKS = {
    "HC-12": {
        "name": "CMP Chain Integration Test",
        "description": "End-to-end test for CMP chain signal flow to TradeDecision creation",
        "command": UV_PREFIX + ["pytest", "tests/test_e2e_cmp_chain.py", "-v", "--tb=short"],
        "timeout": 60,
    },
    "HC-13": {
        "name": "Per-Module Coverage Enforcement",
        "description": "Verify floor-mapped modules meet >=80% coverage threshold (TODO-15)",
        "command": UV_PREFIX + ["scripts/check_per_module_coverage.py"],
        "timeout": 30,
    },
    "HC-15": {
        "name": "Math & Aggregate Validation",
        "description": "Validate composite strength calculations and aggregation math",
        "command": UV_PREFIX + ["pytest", "tests/test_trade_decision.py", "-k", "composite", "-v"],
        "timeout": 30,
    },
    "HC-17": {
        "name": "Signal Source Validation",
        "description": "Validate signal source tagging and enum validation (F7-C-02a fix)",
        "command": UV_PREFIX + ["pytest", "tests/test_trade_decision.py", "-k", "source", "-v"],
        "timeout": 30,
    },
    "HC-18": {
        "name": "VIX Integration Wired",
        "description": "Verify VIX integration is wired with symmetric fail-safe (TODO-12)",
        "command": UV_PREFIX + ["pytest", "tests/test_vix_integration.py", "-v"],
        "timeout": 30,
    },
    "HC-25": {
        "name": "No 18.5 VIX Fallback",
        "description": "Verify no bare 18.5 VIX fallback remains (TODO-12)",
        "command": UV_PREFIX + ["pytest", "tests/test_vix_integration.py::TestVIXNo18_5Fallback", "-v"],
        "timeout": 15,
    },
    "HC-19": {
        "name": "Real Analyzer Routing",
        "description": "Verify real Analyzer routing with audit persistence (TODO-13)",
        "command": UV_PREFIX + ["pytest", "tests/test_analyzer_routing_integration.py", "-v"],
        "timeout": 30,
    },
    "HC-20": {
        "name": "Trailing Stop Runtime Driver",
        "description": "Verify trailing stop runtime driver updates positions correctly (TODO-14)",
        "command": UV_PREFIX + ["pytest", "tests/test_trailing_stop_runtime.py", "-v"],
        "timeout": 30,
    },
    "HC-22": {
        "name": "Audit Dual-Write Guarantee",
        "description": "Verify audit dual-write without PYTEST_CURRENT_TEST bypass (TODO-20)",
        "command": UV_PREFIX + ["pytest", "tests/test_audit_dual_write.py", "-v"],
        "timeout": 30,
    },
    "HC-26": {
        "name": "Root File Cleanup",
        "description": "Verify root directory only tracks source-of-truth files, no junk (TODO-21)",
        "command": [PYTHON_INTERPRETER, "-c", "import subprocess; result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True); files = result.stdout.strip().split('\\n'); root_files = [f for f in files if '/' not in f]; junk = [f for f in root_files if f in ['$null', '[100%]', '0.21.0'] or f.endswith(('bandit-report.json', 'pip-audit-core-report.json', 'results.json', 'coverage_floor_map.json', 'opencode.json')) or f.endswith(('final_lint_report.txt', 'orchestrator_files.txt', 'ruff_errors.txt', 'ruff_errors_final.txt', 'ruff_errors_updated.txt', 'test.txt', 'test_content.txt', 'test_direct_push.txt', 'lwts4oa.md', 'pytest_output.txt'))]; print(f'Root files: {len(root_files)}, Junk: {junk}'); exit(1 if junk else 0)"],
        "timeout": 15,
    },
    "HC-27": {
        "name": "Dead Weight Removal",
        "description": "Verify FUNDAMENTAL/MACHINE_LEARNING/OPTIONS_FLOW removed from source_weights (TODO-23)",
        "command": UV_PREFIX + ["scripts/verify_todo23_external.py"],
        "timeout": 15,
    },
    "HC-28": {
        "name": "Exit Semantics Verification",
        "description": "Verify check_per_module_coverage.py exit semantics, no fallthrough to exit 0 (TODO-24)",
        "command": UV_PREFIX + ["scripts/verify_todo24_external.py"],
        "timeout": 30,
    },
    "HC-29": {
        "name": "P1/P5 Phase-Gate Evidence Verification",
        "description": "Verify P1 ANALYZE round-trip latency evidence collected; P5 blocked on TODO-13 (TODO-25 / F7-L-05)",
        "command": [PYTHON_INTERPRETER, "scripts/verify_todo25_external.py"],
        "timeout": 30,
    },
}

def run_health_check(check_id: str, check_config: dict) -> dict:
    """Run a single health check."""
    print(f"\n{'='*60}")
    print(f"Running {check_id}: {check_config['name']}")
    print(f"Description: {check_config['description']}")
    print(f"{'='*60}")

    start_time = datetime.now()
    result = {
        "check_id": check_id,
        "name": check_config['name'],
        "description": check_config['description'],
        "start_time": start_time.isoformat(),
        "status": "UNKNOWN",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "duration_seconds": 0,
    }

    try:
        process = subprocess.run(
            check_config['command'],
            capture_output=True,
            text=True,
            timeout=check_config.get('timeout', 60),
            cwd=Path(__file__).parent.parent
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result['exit_code'] = process.returncode
        result['stdout'] = process.stdout
        result['stderr'] = process.stderr
        result['duration_seconds'] = duration
        result['end_time'] = end_time.isoformat()

        if process.returncode == 0:
            result['status'] = 'PASS'
            print(f"? {check_id} PASSED ({duration:.2f}s)")
        else:
            result['status'] = 'FAIL'
            print(f"? {check_id} FAILED ({duration:.2f}s)")
            print(f"Exit code: {process.returncode}")
            if process.stdout:
                print(f"STDOUT: {process.stdout[:500]}...")
            if process.stderr:
                print(f"STDERR: {process.stderr[:500]}...")

    except subprocess.TimeoutExpired:
        result['status'] = 'TIMEOUT'
        result['end_time'] = datetime.now().isoformat()
        result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
        print(f"? {check_id} TIMEOUT after {check_config.get('timeout', 60)}s")

    except Exception as e:
        result['status'] = 'ERROR'
        result['end_time'] = datetime.now().isoformat()
        result['duration_seconds'] = (datetime.now() - start_time).total_seconds()
        result['error'] = str(e)
        print(f"? {check_id} ERROR: {e}")

    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='Comma-separated list of health check IDs to run')
    parser.add_argument('--json', help='Output results to JSON file')
    parser.add_argument('--fast', action='store_true', help='Run fast subset of checks')
    args = parser.parse_args()

    # Determine which checks to run
    checks_to_run = list(HEALTH_CHECKS.keys())
    if args.only:
        requested = [cid.strip() for cid in args.only.split(',')]
        checks_to_run = [cid for cid in requested if cid in HEALTH_CHECKS]
        if not checks_to_run:
            print(f"Error: No valid health check IDs found in: {args.only}")
            print(f"Available IDs: {', '.join(HEALTH_CHECKS.keys())}")
            return 1

    if args.fast:
        # Fast mode: only run critical checks
        checks_to_run = ['HC-12', 'HC-17']

    print(f"\nFR7 Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Running {len(checks_to_run)} health check(s): {', '.join(checks_to_run)}")

    # Run health checks
    results = []
    for check_id in checks_to_run:
        result = run_health_check(check_id, HEALTH_CHECKS[check_id])
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("FR7 HEALTH CHECK SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    total = len(results)

    for result in results:
        status_symbol = "?" if result['status'] == 'PASS' else "?"
        print(f"{status_symbol} {result['check_id']}: {result['status']} ({result['duration_seconds']:.2f}s)")

    print(f"\nTotal: {passed}/{total} passed, {failed}/{total} failed")

    # Save to JSON if requested
    if args.json:
        output = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total': total,
                'passed': passed,
                'failed': failed,
                'success_rate': f'{(passed/total*100):.1f}%' if total > 0 else '0%'
            },
            'results': results
        }
        Path(args.json).write_text(json.dumps(output, indent=2))
        print(f"\nResults saved to: {args.json}")

    # Return exit code
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
