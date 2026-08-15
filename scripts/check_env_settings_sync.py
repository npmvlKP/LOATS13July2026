#!/usr/bin/env python3
"""
CI check to verify that .env.example keys match Settings field names.

This script ensures that all environment variables in .env.example have
corresponding fields in the Settings class, and vice versa.
"""

import re
import sys
from pathlib import Path


def extract_env_vars_from_dotenv(dotenv_path: Path) -> set[str]:
    """Extract environment variable names from .env.example file."""
    env_vars = set()
    if not dotenv_path.exists():
        print(f"Error: {dotenv_path} does not exist")
        return env_vars

    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if line.startswith("#") or not line or "=" not in line:
                continue
            # Extract variable name (before =)
            var_name = line.split("=")[0].strip()
            env_vars.add(var_name)

    return env_vars


def extract_settings_fields(settings_path: Path) -> set[str]:
    """Extract field names from Settings class."""
    fields = set()
    if not settings_path.exists():
        print(f"Error: {settings_path} does not exist")
        return fields

    with open(settings_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all field definitions in Settings class
    # Pattern matches: field_name: type = Field(...) or field_name: type = value
    field_pattern = r"(\w+)\s*:\s*(?:[^=]+=\s*)?Field\("
    matches = re.findall(field_pattern, content)

    for match in matches:
        fields.add(match)

    return fields


def env_to_settings_name(env_var: str) -> str:
    """Convert environment variable name to settings field name."""
    # Convert UPPER_CASE to snake_case (they should already be snake_case)
    # Remove any prefixes and convert to lowercase
    return env_var.lower()


def main() -> int:
    """Main function to check .env.example vs Settings sync."""
    repo_root = Path(__file__).parent.parent
    dotenv_path = repo_root / ".env.example"
    settings_path = repo_root / "src" / "loats" / "config" / "settings.py"

    print("Checking .env.example vs Settings synchronization...")

    # Extract variables from both sources
    env_vars = extract_env_vars_from_dotenv(dotenv_path)
    settings_fields = extract_settings_fields(settings_path)

    print(f"Found {len(env_vars)} environment variables in .env.example")
    print(f"Found {len(settings_fields)} fields in Settings class")

    # Check for missing mappings
    missing_in_settings = []
    missing_in_dotenv = []

    for env_var in env_vars:
        # Convert to settings field name format
        expected_field = env_var.lower()
        if expected_field not in settings_fields:
            missing_in_settings.append(f"{env_var} -> {expected_field}")

    for field in settings_fields:
        # Convert to env var format
        expected_env_var = field.upper()
        if expected_env_var not in env_vars:
            missing_in_dotenv.append(f"{field} -> {expected_env_var}")

    # Report results
    if missing_in_settings:
        print(
            "\n❌ Environment variables in .env.example without corresponding Settings fields:"
        )
        for missing in missing_in_settings:
            print(f"  - {missing}")

    if missing_in_dotenv:
        print(
            "\n❌ Settings fields without corresponding environment variables in .env.example:"
        )
        for missing in missing_in_dotenv:
            print(f"  - {missing}")

    if missing_in_settings or missing_in_dotenv:
        print("\n[X] Synchronization check FAILED")
        return 1

    print("\n[OK] Synchronization check PASSED")
    print(
        "All .env.example variables have corresponding Settings fields and vice versa."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
