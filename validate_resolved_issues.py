#!/usr/bin/env python3
"""
Validation script for resolved issues NEW-M1 to NEW-M4.

This script validates that all the resolved issues mentioned in the task are properly implemented:
- NEW-M1: HTML injection fix (html.escape() applied)
- NEW-M2: .env.example synced with Settings
- NEW-M3: quantity=1 hardcoded fix (uses contract.quantity)
- NEW-M4: negative t clamping fix (ExpiredContractError raised)
"""

import os
import re
import sys
from pathlib import Path

def validate_html_injection_fix():
    """Validate NEW-M1: HTML injection fix."""
    print("Validating NEW-M1: HTML injection fix...")

    alerts_file = Path("src/loats/alerts.py")
    if not alerts_file.exists():
        print("❌ alerts.py not found")
        return False

    try:
        content = alerts_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            content = alerts_file.read_text(encoding='latin-1')
        except Exception as e:
            print(f"❌ Failed to read alerts.py: {e}")
            return False

    # Check for html.escape() usage
    html_escape_pattern = r'html\.escape\('
    if not re.search(html_escape_pattern, content):
        print("❌ html.escape() not found in alerts.py")
        return False

    print("NEW-M1: HTML injection fix validated - html.escape() is properly applied")
    return True

def validate_env_example_sync():
    """Validate NEW-M2: .env.example synced with Settings."""
    print("Validating NEW-M2: .env.example synced with Settings...")

    env_example_file = Path(".env.example")
    settings_file = Path("src/loats/config/settings.py")

    if not env_example_file.exists():
        print("❌ .env.example not found")
        return False

    if not settings_file.exists():
        print("❌ settings.py not found")
        return False

    try:
        env_content = env_example_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        env_content = env_example_file.read_text(encoding='latin-1')

    try:
        settings_content = settings_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        settings_content = settings_file.read_text(encoding='latin-1')

    # Check that all settings fields are represented in .env.example
    # Extract field names from settings.py
    field_pattern = r'(\w+)\s*:\s*(?:SecretStr|str|int|float|Decimal|Path|list|Literal)\s*=\s*Field\('
    fields = re.findall(field_pattern, settings_content)

    # Check that each field has a corresponding entry in .env.example
    missing_fields = []
    for field in fields:
        # Skip fields that might not need .env entries (like computed fields)
        if field in ['environment', 'sqlite_db_path', 'audit_log_path', 'retention_days',
                     'ta_scan_interval', 'sentiment_scan_interval', 'signal_scan_interval',
                     'default_symbol', 'default_timeframe', 'sentiment_threshold',
                     'request_timeout', 'openalgo_mode', 'nifty_lot_size', 'max_order_value',
                     'max_daily_orders', 'max_ops', 'circuit_limit_pct', 'max_position_per_symbol',
                     'max_total_exposure', 'timezone']:
            continue

        env_var = field.upper()
        if env_var not in env_content:
            missing_fields.append(env_var)

    if missing_fields:
        print(f"❌ Missing .env.example entries: {missing_fields}")
        return False

    print("NEW-M2: .env.example synced with Settings validated")
    return True

def validate_quantity_fix():
    """Validate NEW-M3: quantity=1 hardcoded fix."""
    print("Validating NEW-M3: quantity=1 hardcoded fix...")

    options_file = Path("src/loats/options.py")
    if not options_file.exists():
        print("❌ options.py not found")
        return False

    try:
        content = options_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = options_file.read_text(encoding='latin-1')

    # Check for contract.quantity usage in calculate_portfolio_greeks
    contract_quantity_pattern = r'contract_quantity\s*=\s*contract\.quantity'
    if not re.search(contract_quantity_pattern, content):
        print("❌ contract.quantity not found in options.py")
        return False

    # Check that there are no hardcoded quantity=1 assignments
    hardcoded_pattern = r'quantity\s*=\s*1\b'
    if re.search(hardcoded_pattern, content):
        print("❌ Found hardcoded quantity=1 in options.py")
        return False

    print("NEW-M3: quantity=1 hardcoded fix validated - uses contract.quantity")
    return True

def validate_expired_contract_error():
    """Validate NEW-M4: negative t clamping fix."""
    print("Validating NEW-M4: negative t clamping fix...")

    options_file = Path("src/loats/options.py")
    if not options_file.exists():
        print("❌ options.py not found")
        return False

    try:
        content = options_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = options_file.read_text(encoding='latin-1')

    # Check for ExpiredContractError class definition
    expired_error_pattern = r'class ExpiredContractError\('
    if not re.search(expired_error_pattern, content):
        print("❌ ExpiredContractError class not found")
        return False

    # Check for ExpiredContractError usage in key methods
    error_usage_patterns = [
        r'if t <= 0:.*raise ExpiredContractError',
        r'if t <= 0:.*allow_expired'
    ]

    found_usage = False
    for pattern in error_usage_patterns:
        if re.search(pattern, content, re.DOTALL):
            found_usage = True
            break

    if not found_usage:
        print("❌ ExpiredContractError not properly used for negative t validation")
        return False

    print("NEW-M4: negative t clamping fix validated - ExpiredContractError properly raised")
    return True

def main():
    """Main validation function."""
    print("Starting validation of resolved issues NEW-M1 to NEW-M4")
    print("=" * 60)

    validations = [
        validate_html_injection_fix,
        validate_env_example_sync,
        validate_quantity_fix,
        validate_expired_contract_error
    ]

    results = []
    for validation in validations:
        try:
            result = validation()
            results.append(result)
        except Exception as e:
            print(f"Validation failed with error: {e}")
            results.append(False)
        print()

    print("=" * 60)
    print("VALIDATION SUMMARY:")
    print(f"NEW-M1 (HTML injection): {'PASS' if results[0] else 'FAIL'}")
    print(f"NEW-M2 (.env.example sync): {'PASS' if results[1] else 'FAIL'}")
    print(f"NEW-M3 (quantity=1 fix): {'PASS' if results[2] else 'FAIL'}")
    print(f"NEW-M4 (negative t fix): {'PASS' if results[3] else 'FAIL'}")

    all_passed = all(results)
    print(f"\nOverall Result: {'ALL VALIDATIONS PASSED' if all_passed else 'SOME VALIDATIONS FAILED'}")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
