#!/usr/bin/env python3
"""
pip-audit wrapper script for TODO-4
Uses system Python 3.12 pip-audit to avoid venv corruption issues
"""

import subprocess
import sys
from pathlib import Path


def main():
    # Use system Python 3.12 interpreter with pip-audit module
    # This bypasses all PATH and venv issues
    system_python = Path(r"C:\Program Files\Python312\python.exe")
    system_pip_audit = Path(r"C:\Program Files\Python312\Scripts\pip-audit.exe")

    # Determine command
    if system_pip_audit.exists():
        # Use absolute Windows path with python.exe to execute
        cmd = [str(system_python.resolve()), str(system_pip_audit.resolve())] + sys.argv[1:]
    elif system_python.exists():
        # Fallback: use system python with -m pip_audit
        cmd = [str(system_python.resolve()), "-m", "pip_audit"] + sys.argv[1:]
    else:
        # Last resort: try pip-audit from PATH
        cmd = ["pip-audit"] + sys.argv[1:]

    # Important: Don't use shell=True (security risk)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False
    )

    # Write stdout and preserve exit code
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
