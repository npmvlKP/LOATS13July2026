#!/usr/bin/env python3
"""
COMPREHENSIVE BUILD VERIFICATION SCRIPT FOR LOATS13July2026
Verifies complete implementation including TODO-26 requirements
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, timeout=60):
    """Execute command with timeout and return results"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd='G:\.OA\LOATS-13July2026\LOATS13July2026'
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expired"
    except Exception as e:
        return -1, "", str(e)

def verify_todo26_implementation():
    """Verify TODO-26 specific implementation"""
    print("="*60)
    print("VERIFYING TODO-26 IMPLEMENTATION")
    print("="*60)

    # Verify external verification script
    print("\n1. Running TODO-26 external verification...")
    code, stdout, stderr = run_command("python Scripts\\verify_todo26_external.py")
    todo26_pass = code == 0 and "PASS" in stdout
    print(f"   Result: {'PASS' if todo26_pass else 'FAIL'}")
    if not todo26_pass:
        print(f"   Error: {stderr[:200]}...")

    # Verify health check integration
    print("\n2. Running HC-30 health check...")
    code, stdout, stderr = run_command("python Scripts\\fr7_health_check.py --only HC-30 --json /dev/null")
    hc30_pass = code == 0 and "HC-30: PASS" in stdout
    print(f"   Result: {'PASS' if hc30_pass else 'FAIL'}")
    if not hc30_pass:
        print(f"   Error: {stderr[:200]}...")

    return todo26_pass