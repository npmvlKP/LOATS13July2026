#!/usr/bin/env python
"""Final validation of P2 fixes."""
import subprocess
import sys

print("=== FINAL VALIDATION ===\n")

print("1. MyPy Strict Mode:")
result = subprocess.run([sys.executable, "-m", "mypy", "src/", "--strict"], capture_output=True, text=True)
if result.returncode == 0:
    print("   PASSED")
else:
    print("   FAILED")
    print(result.stdout)

print("\n2. Ruff Linting:")
result = subprocess.run([sys.executable, "-m", "ruff", "check", "src/"], capture_output=True, text=True)
if result.returncode == 0:
    print("   PASSED")
else:
    print("   FAILED")
    print(result.stdout)

print("\n3. Original 3 Failing Tests:")
result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_metrics.py::TestMetricsServer::test_start_metrics_server_exception_handling",
        "tests/test_orchestrator.py::TestTradingOrchestrator::test_execute_risk_management",
        "tests/test_sentiment_coverage.py::test_analyze_symbol_sentiment_cache_hit",
        "-v",
    ],
    capture_output=True,
    text=True,
)
passed = "3 passed" in result.stdout
if passed:
    print("   PASSED")
else:
    print("   FAILED")
    print(result.stdout)

print("\n=== ALL VALIDATIONS COMPLETE ===")