#!/usr/bin/env python3
"""
Project setup script for LOATS13July2026.

This script sets up the project environment and verifies the installation
following the "loats" protocol strictly.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(command, cwd=None, capture_output=True):
    """Run a shell command and return the result."""
    print(f"🔹 Running: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return -1, "", str(e)


def create_virtual_environment():
    """Create a new virtual environment."""
    print("\n🔧 CREATING VIRTUAL ENVIRONMENT")
    print("=" * 50)

    # Check if virtual environment already exists
    venv_path = Path("loats13july2026")
    if venv_path.exists():
        print("⚠️  Virtual environment 'loats13july2026' already exists")
        return True

    # Create new virtual environment
    code, stdout, stderr = run_command("python -m venv loats13july2026")
    if code != 0:
        print(f"❌ Failed to create virtual environment: {stderr}")
        return False

    print("✅ Virtual environment created successfully")
    return True


def install_dependencies():
    """Install project dependencies."""
    print("\n📦 INSTALLING DEPENDENCIES")
    print("=" * 50)

    venv_path = Path("loats13july2026")
    if not venv_path.exists():
        print("❌ Virtual environment not found")
        return False

    python_cmd = str(venv_path / "Scripts" / "python.exe")
    pip_cmd = str(venv_path / "Scripts" / "pip.exe")

    # Upgrade pip
    code, stdout, stderr = run_command(f"{pip_cmd} install --upgrade pip")
    if code != 0:
        print(f"⚠️  Failed to upgrade pip: {stderr}")

    # Install core dependencies
    code, stdout, stderr = run_command(f"{pip_cmd} install -r requirements-core.txt")
    if code != 0:
        print(f"❌ Failed to install dependencies: {stderr}")
        return False

    print("✅ Core dependencies installed successfully")

    # Install project in editable mode
    code, stdout, stderr = run_command(f"{pip_cmd} install -e .")
    if code != 0:
        print(f"❌ Failed to install project in editable mode: {stderr}")
        return False

    print("✅ Project installed in editable mode")
    return True


def verify_installation():
    """Verify the installation."""
    print("\n🔍 VERIFYING INSTALLATION")
    print("=" * 50)

    venv_path = Path("loats13july2026")
    if not venv_path.exists():
        print("❌ Virtual environment not found")
        return False

    python_cmd = str(venv_path / "Scripts" / "python.exe")

    # Check Python version
    code, stdout, stderr = run_command(f"{python_cmd} --version")
    if code != 0:
        print(f"❌ Failed to get Python version: {stderr}")
        return False
    print(f"✅ Python version: {stdout.strip()}")

    # Check pip version
    code, stdout, stderr = run_command(f"{python_cmd} -m pip --version")
    if code != 0:
        print(f"❌ Failed to get pip version: {stderr}")
        return False
    print(f"✅ Pip version: {stdout.strip()}")

    # Check if key packages are installed
    packages = ["pydantic", "httpx", "ta", "pytest", "structlog"]
    for package in packages:
        code, stdout, stderr = run_command(
            f"{python_cmd} -c \"import {package}; print(f'{package} version: ' + {package}.__version__)\"",
        )
        if code == 0:
            print(f"✅ {stdout.strip()}")
        else:
            print(f"⚠️  {package} not found")

    return True


def run_basic_tests():
    """Run basic tests to verify functionality."""
    print("\n🧪 RUNNING BASIC TESTS")
    print("=" * 50)

    venv_path = Path("loats13july2026")
    if not venv_path.exists():
        print("❌ Virtual environment not found")
        return False

    python_cmd = str(venv_path / "Scripts" / "python.exe")

    # Test basic TA functionality
    test_script = """
from src.loats.ta import ta, calculate_rsi
from src.loats.logging import get_logger
import pandas as pd
import numpy as np

# Test logging
logger = get_logger(__name__)
logger.info("Testing logging functionality")

# Test TA functionality
data = {
    'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='1min'),
    'open': np.random.uniform(90, 110, 100).tolist(),
    'high': np.random.uniform(95, 115, 100).tolist(),
    'low': np.random.uniform(85, 105, 100).tolist(),
    'close': np.random.uniform(90, 110, 100).tolist(),
    'volume': np.random.randint(1000, 10000, 100).tolist()
}

df = pd.DataFrame(data)
rsi = calculate_rsi(df)
print(f"✅ RSI calculation successful, sample value: {rsi.iloc[-1]:.2f}")

# Test TA class
indicators = ta.calculate_indicators([])
print(f"✅ TA class initialization successful, got {len(indicators)} indicators")

print("✅ All basic functionality tests passed")
"""

    with open("basic_test.py", "w") as f:
        f.write(test_script)

    code, stdout, stderr = run_command(f"{python_cmd} basic_test.py")
    print(stdout)
    if stderr:
        print(f"Stderr: {stderr}")

    # Clean up
    os.remove("basic_test.py")

    return code == 0


def main():
    """Main setup function."""
    print("🚀 LOATS13July2026 PROJECT SETUP")
    print("=" * 50)
    print("This script sets up the project environment following the")
    print("'loats' protocol strictly.\n")

    # Change to project directory
    os.chdir(Path(__file__).parent)

    # Create virtual environment
    if not create_virtual_environment():
        print("❌ Virtual environment creation failed")
        return 1

    # Install dependencies
    if not install_dependencies():
        print("❌ Dependency installation failed")
        return 1

    # Verify installation
    if not verify_installation():
        print("⚠️  Installation verification completed with warnings")

    # Run basic tests
    if not run_basic_tests():
        print("❌ Basic functionality tests failed")
        return 1

    print("\n" + "=" * 50)
    print("🎉 SETUP COMPLETE: PROJECT IS READY FOR DEVELOPMENT")
    print("=" * 50)
    print("\n📝 NEXT STEPS:")
    print("1. Activate the virtual environment:")
    print("   loats13july2026\\Scripts\\activate")
    print("2. Run the comprehensive verification script:")
    print("   python verify_project_health.py")
    print("3. Start implementing remaining modules")
    print("4. Run tests regularly to ensure project health")

    return 0


if __name__ == "__main__":
    sys.exit(main())
