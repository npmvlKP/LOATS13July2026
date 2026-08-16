#!/usr/bin/env python3
"""
LOATS13July2026 - Comprehensive Project Health Verification
LITE Philosophy: Extended health checks for development and CI/CD
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str]) -> bool:
    """Run a command and return success status"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_code_quality() -> bool:
    """Check code quality tools are available"""
    tools = [
        ["ruff", "--version"],
        ["black", "--version"],
        ["isort", "--version"],
        ["mypy", "--version"],
        ["bandit", "--version"],
    ]

    print("[TOOLS] Checking code quality tools...")
    for tool in tools:
        if not run_command(tool):
            print(f"[FAIL] Missing or broken tool: {' '.join(tool)}")
            return False
        print(f"[PASS] Tool available: {' '.join(tool)}")

    return True


def check_test_suite() -> bool:
    """Check test suite can be discovered"""
    print("[TESTS] Checking test suite...")

    test_files = list(Path("tests").glob("test_*.py"))
    if not test_files:
        print("[FAIL] No test files found")
        return False

    print(f"[PASS] Found {len(test_files)} test files")
    return True


def check_dependencies() -> bool:
    """Check dependency files exist"""
    print("[DEPS] Checking dependencies...")

    required_files = ["requirements-core.txt", "pyproject.toml"]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing dependency file: {file_path}")
            return False

    print("[PASS] All dependency files present")
    return True


def check_docker_setup() -> bool:
    """Check Docker configuration"""
    print("[DOCKER] Checking Docker setup...")

    required_files = ["Dockerfile", "docker-compose.yml"]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing Docker file: {file_path}")
            return False

    print("[PASS] Docker configuration present")
    return True


def check_ci_cd_setup() -> bool:
    """Check CI/CD configuration"""
    print("[CI/CD] Checking CI/CD setup...")

    ci_files = [
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        ".pre-commit-config.yaml",
    ]

    for file_path in ci_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing CI/CD file: {file_path}")
            return False

    print("[PASS] CI/CD configuration present")
    return True


def check_security_configuration() -> bool:
    """Check security configuration files"""
    print("[SECURITY] Checking security configuration...")

    security_files = [".gitleaks.toml", ".gitignore"]

    for file_path in security_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing security file: {file_path}")
            return False

    print("[PASS] Security configuration present")
    return True


def check_documentation() -> bool:
    """Check basic documentation exists"""
    print("[DOCS] Checking documentation...")

    doc_files = ["README.md", "DEPLOY.md", "RUNBOOK.md"]
    for file_path in doc_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing documentation file: {file_path}")
            return False

    print("[PASS] Documentation present")
    return True


def main() -> int:
    """Run comprehensive health verification"""
    print("LOATS13July2026 Comprehensive Health Verification")
    print("=" * 60)

    checks = [
        check_code_quality,
        check_test_suite,
        check_dependencies,
        check_docker_setup,
        check_ci_cd_setup,
        check_security_configuration,
        check_documentation,
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] {check.__name__} failed with exception: {e}")
            results.append(False)

    print("=" * 60)
    if all(results):
        print("[PASS] All comprehensive health checks passed")
        return 0
    else:
        print("[FAIL] Some comprehensive health checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
