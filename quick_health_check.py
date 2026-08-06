#!/usr/bin/env python3
"""
LOATS13July2026 - Quick Health Check
LITE Philosophy: Minimal health check for container and CI/CD
"""

import importlib.util
import os
import sys
from pathlib import Path


def check_python_version():
    """Check Python version is 3.12+"""
    if sys.version_info < (3, 12):
        print("[FAIL] Python version check failed")
        return False
    print("[PASS] Python version check passed")
    return True

def check_environment():
    """Check required environment variables (lenient for local testing)"""
    # For container/CI environments, these should be set
    # For local testing, we'll warn but not fail
    required_vars = ['TZ', 'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED']
    missing_vars = [var for var in required_vars if var not in os.environ]

    if missing_vars:
        print(f"[WARN] Missing environment variables: {missing_vars} (ok for local testing)")
        # Only fail if we're in a container (indicated by presence of some container-specific env vars)
        if any(var in os.environ for var in ['CONTAINER', 'DOCKER', 'KUBERNETES_SERVICE_HOST']):
            return False
    print("[PASS] Environment variables check passed")
    return True

def check_imports():
    """Check critical imports work"""
    critical_modules = ['src', 'src.loats', 'src.loats.utils']

    for module_name in critical_modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                print(f"[FAIL] Cannot import {module_name}")
                return False
        except ImportError:
            print(f"[FAIL] Cannot import {module_name}")
            return False

    print("[PASS] Critical imports check passed")
    return True

def check_file_structure():
    """Check basic file structure exists"""
    required_files = [
        'src/__init__.py',
        'pyproject.toml',
        'requirements-core.txt',
        'Dockerfile',
        'docker-compose.yml'
    ]

    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[FAIL] Missing required file: {file_path}")
            return False

    print("[PASS] File structure check passed")
    return True

def main():
    """Run all health checks"""
    print("LOATS13July2026 Quick Health Check")
    print("=" * 50)

    checks = [
        check_python_version,
        check_environment,
        check_imports,
        check_file_structure
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] {check.__name__} failed with exception: {e}")
            results.append(False)

    print("=" * 50)
    if all(results):
        print("[PASS] All health checks passed")
        return 0
    else:
        print("[FAIL] Some health checks failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
