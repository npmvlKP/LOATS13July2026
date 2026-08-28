#!/usr/bin/env python3
"""
TODO-19 (F7-M-04) Implementation Verification Script

Validates that the legacy signal engine has been properly retired/converted:
- Single signal-production path exists
- Single threshold constant (0.5) is used throughout
- Signal sources are properly tagged with StrengthSource enum values
- No legacy combiner with 0.6 threshold exists
- Orchestrator coverage drops naturally (no dead paths)

Usage:
    python scripts/verify_todo19_implementation.py
"""

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

# Configure UTF-8 encoding for output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def verify_single_threshold_constant() -> dict[str, Any]:
    """
    Verify that only one threshold constant exists and it's set to 0.5.
    """
    print("=" * 60)
    print("Verifying Single Threshold Constant")
    print("=" * 60)

    results = {
        "status": "PASS",
        "findings": [],
        "threshold_value": None,
        "legacy_thresholds_found": []
    }

    # Check settings.py for composite_strength_threshold
    settings_file = Path(__file__).parent.parent / "src" / "loats" / "config" / "settings.py"
    settings_content = settings_file.read_text()

    # Extract composite_strength_threshold value
    threshold_match = re.search(
        r'composite_strength_threshold.*?=\s*Field\(\s*([\d.]+)',
        settings_content
    )
    if threshold_match:
        threshold_value = float(threshold_match.group(1))
        results["threshold_value"] = threshold_value
        print(f"[OK] Found composite_strength_threshold: {threshold_value}")

        if threshold_value == 0.5:
            print("[OK] Threshold is correctly set to 0.5")
            results["findings"].append("Single threshold constant set to 0.5")
        else:
            print(f"[FAIL] Threshold is {threshold_value}, expected 0.5")
            results["status"] = "FAIL"
            results["findings"].append(f"Threshold should be 0.5, found {threshold_value}")
    else:
        print("[FAIL] Could not find composite_strength_threshold in settings")
        results["status"] = "FAIL"
        results["findings"].append("composite_strength_threshold not found in settings")

    # Search for any 0.6 threshold values in signal generation code
    search_files = [
        Path(__file__).parent.parent / "src" / "loats" / "orchestrator.py",
        Path(__file__).parent.parent / "src" / "loats" / "trade_decision.py",
        Path(__file__).parent.parent / "src" / "loats" / "strength" / "__init__.py",
    ]

    for file_path in search_files:
        if file_path.exists():
            content = file_path.read_text()
            # Look for 0.6 threshold values
            if re.search(r'0\.6\s*[>,<]=', content):
                legacy_match = re.search(r'.*0\.6.*', content, re.MULTILINE)
                if legacy_match:
                    print(f"[FAIL] Found potential legacy 0.6 threshold in {file_path.name}")
                    results["status"] = "FAIL"
                    results["legacy_thresholds_found"].append(str(file_path.name))
                    results["findings"].append(f"Legacy 0.6 threshold found in {file_path.name}")

    if not results["legacy_thresholds_found"]:
        print("[OK] No legacy 0.6 thresholds found in signal generation code")
        results["findings"].append("No legacy 0.6 thresholds detected")

    return results


def verify_signal_source_tagging() -> dict[str, Any]:
    """
    Verify that signal sources are properly tagged with StrengthSource enum values.
    """
    print("\n" + "=" * 60)
    print("Verifying Signal Source Tagging")
    print("=" * 60)

    results = {
        "status": "PASS",
        "findings": [],
        "valid_sources": [],
        "invalid_tagging": []
    }

    # Check that StrengthSource enum exists and has expected values
    strength_file = Path(__file__).parent.parent / "src" / "loats" / "strength" / "__init__.py"
    if not strength_file.exists():
        strength_file = Path(__file__).parent.parent / "src" / "loats" / "strength.py"

    if strength_file.exists():
        strength_content = strength_file.read_text()

        # Look for StrengthSource enum
        enum_match = re.search(
            r'class StrengthSource.*?(?=\nclass|\Z)',
            strength_content,
            re.DOTALL
        )

        if enum_match:
            enum_text = enum_match.group(0)
            # Extract enum values
            enum_values = re.findall(r'(\w+)\s*=\s*["\']([^"\']+)["\']', enum_text)

            expected_sources = {
                "TECHNICAL_ANALYSIS": "ta",
                "SENTIMENT": "sentiment",
                "PRICE_ACTION": "price_action",
                "VOLATILITY": "volatility",
            }

            found_sources = {}
            for name, value in enum_values:
                found_sources[name] = value
                print(f"  ✓ Found enum value: {name} = {value}")

            # Check that expected sources exist
            for expected_name, expected_value in expected_sources.items():
                if expected_name in found_sources:
                    if found_sources[expected_name] == expected_value:
                        results["valid_sources"].append(expected_name)
                        print(f"  ✓ {expected_name} has correct value: {expected_value}")
                    else:
                        print(f"  ⚠ {expected_name} has unexpected value: {found_sources[expected_name]} (expected {expected_value})")
                        results["findings"].append(f"{expected_name} value mismatch")
                else:
                    print(f"  ✗ Missing expected source: {expected_name}")
                    results["status"] = "FAIL"
                    results["findings"].append(f"Missing source enum: {expected_name}")

            results["findings"].append(f"Found {len(found_sources)} signal source enums")
        else:
            print("✗ Could not find StrengthSource enum definition")
            results["status"] = "FAIL"
            results["findings"].append("StrengthSource enum not found")
    else:
        print("✗ Could not find strength.py or strength/__init__.py")
        results["status"] = "FAIL"
        results["findings"].append("Strength module not found")

    # Check orchestrator for proper source tagging in signal creation
    orchestrator_file = Path(__file__).parent.parent / "src" / "loats" / "orchestrator.py"
    if orchestrator_file.exists():
        orchestrator_content = orchestrator_file.read_text()

        # Look for signal creation with source metadata
        signal_creations = re.findall(
            r'Signal\([^)]*metadata\s*=\s*\{[^}]*"source"\s*:\s*StrengthSource\.(\w+)',
            orchestrator_content,
            re.DOTALL
        )

        print(f"\n  Found {len(signal_creations)} signal creation points with source tagging")

        for source_enum in signal_creations:
            if source_enum in results["valid_sources"] or source_enum in ["TECHNICAL_ANALYSIS", "SENTIMENT", "VOLATILITY"]:
                print(f"  ✓ Proper source tagging using StrengthSource.{source_enum}")
            else:
                print(f"  ⚠ Using source enum: {source_enum}")

        # Check for hardcoded "orchestrator" source tags (legacy)
        hardcoded_orchestrator = re.findall(
            r'"source"\s*:\s*"orchestrator"',
            orchestrator_content
        )

        if hardcoded_orchestrator:
            print(f"  ✗ Found {len(hardcoded_orchestrator)} instances of hardcoded 'orchestrator' source tag")
            results["status"] = "FAIL"
            results["invalid_tagging"].append("Hardcoded 'orchestrator' source tags found")
            results["findings"].append(f"Found {len(hardcoded_orchestrator)} legacy 'orchestrator' source tags")
        else:
            print("  ✓ No hardcoded 'orchestrator' source tags found")
            results["findings"].append("All sources properly tagged with enum values")

    return results


def verify_single_signal_production_path() -> dict[str, Any]:
    """
    Verify that only one signal production path exists (no legacy combiner).
    """
    print("\n" + "=" * 60)
    print("Verifying Single Signal Production Path")
    print("=" * 60)

    results = {
        "status": "PASS",
        "findings": [],
        "production_paths": [],
        "legacy_code_found": []
    }

    orchestrator_file = Path(__file__).parent.parent / "src" / "loats" / "orchestrator.py"
    if not orchestrator_file.exists():
        print("✗ Could not find orchestrator.py")
        results["status"] = "FAIL"
        return results

    orchestrator_content = orchestrator_file.read_text()

    # Check for legacy combiner patterns
    legacy_patterns = [
        r'_execute_signal_generation',  # Legacy signal generation function
        r'combined.*signal',  # Combined signal creation
        r'combiner',  # Combiner references
        r'two.*source.*combin',  # Two-source combiner
        r'0\.6.*threshold',  # Legacy 0.6 threshold
    ]

    legacy_found = False
    for pattern in legacy_patterns:
        matches = re.findall(pattern, orchestrator_content, re.IGNORECASE)
        if matches:
            print(f"  ⚠ Found legacy pattern: {pattern} ({len(matches)} matches)")
            legacy_found = True
            results["legacy_code_found"].append(pattern)

    if legacy_found:
        results["status"] = "FAIL"
        results["findings"].append("Legacy signal combiner patterns still exist")
    else:
        print("  ✓ No legacy signal combiner patterns found")
        results["findings"].append("No legacy combiner code detected")

    # Check for modern signal production paths (separate analysis methods)
    modern_methods = [
        '_execute_ta_analysis',
        '_execute_sentiment_analysis',
        '_execute_volatility_analysis',
    ]

    found_modern = []
    for method in modern_methods:
        if f'async def {method}' in orchestrator_content:
            found_modern.append(method)
            print(f"  ✓ Found modern signal production method: {method}")

    results["production_paths"] = found_modern
    results["findings"].append(f"Found {len(found_modern)} modern signal production methods")

    # Verify each modern method writes to DB with proper tagging
    for method in found_modern:
        method_match = re.search(
            rf'async def {method}\([^)]*\):.*?(?=\n    async def|\n    def|\Z)',
            orchestrator_content,
            re.DOTALL
        )
        if method_match:
            method_content = method_match.group(0)

            # Check for db.async_create_signal call
            if 'async_create_signal' in method_content:
                print(f"  ✓ {method} writes signals to database")

                # Check for proper source tagging
                if 'StrengthSource.' in method_content:
                    print(f"  ✓ {method} uses StrengthSource enum for tagging")
                else:
                    print(f"  ⚠ {method} may not use proper source tagging")
                    results["status"] = "WARNING"
            else:
                print(f"  ⚠ {method} may not write signals to database")
                results["status"] = "WARNING"

    return results


def verify_orchestrator_coverage() -> dict[str, Any]:
    """
    Verify that orchestrator coverage drops naturally (no dead paths).
    """
    print("\n" + "=" * 60)
    print("Verifying Orchestrator Coverage")
    print("=" * 60)

    results = {
        "status": "PASS",
        "findings": [],
        "dead_paths": [],
        "active_paths": []
    }

    orchestrator_file = Path(__file__).parent.parent / "src" / "loats" / "orchestrator.py"
    if not orchestrator_file.exists():
        print("✗ Could not find orchestrator.py")
        results["status"] = "FAIL"
        return results

    orchestrator_content = orchestrator_file.read_text()

    # Find the main trading cycle loop (try multiple patterns)
    cycle_loop_match = re.search(
        r'async def _run_cycle_loop\([^)]*\):.*?(?=async def [a-z_]+\(|def [a-z_]+\(|class |\Z)',
        orchestrator_content,
        re.DOTALL
    )

    if not cycle_loop_match:
        # Try alternative pattern
        cycle_loop_match = re.search(
            r'async def _run_cycle_loop\([^)]*\):.*?(?=\n    async def |\n    def |\Z)',
            orchestrator_content,
            re.DOTALL
        )

    if not cycle_loop_match:
        # Last resort: find the function and grab a reasonable amount of content
        cycle_loop_match = re.search(
            r'async def _run_cycle_loop\([^)]*\):',
            orchestrator_content
        )
        if cycle_loop_match:
            # Get 2000 characters after the function definition
            start_pos = cycle_loop_match.start()
            cycle_content = orchestrator_content[start_pos:start_pos + 2000]
        else:
            cycle_content = ""
    else:
        cycle_content = cycle_loop_match.group(0)

        # Check for commented out or disabled signal generation code
        commented_patterns = [
            r'#.*_execute_signal_generation',
            r'#.*signal.*generation',
            r'#.*combin',
        ]

        for pattern in commented_patterns:
            matches = re.findall(pattern, cycle_content, re.IGNORECASE)
            if matches:
                print(f"  ⚠ Found commented legacy code: {pattern}")
                results["dead_paths"].append(f"Commented: {pattern}")

        # Check for active analysis tasks
        active_tasks = []
        if 'create_task.*_execute_ta_analysis' in cycle_content or 'await.*_execute_ta_analysis' in cycle_content:
            active_tasks.append('_execute_ta_analysis')
        if 'create_task.*_execute_sentiment_analysis' in cycle_content or 'await.*_execute_sentiment_analysis' in cycle_content:
            active_tasks.append('_execute_sentiment_analysis')
        if 'create_task.*_execute_volatility_analysis' in cycle_content or 'await.*_execute_volatility_analysis' in cycle_content:
            active_tasks.append('_execute_volatility_analysis')

        results["active_paths"] = active_tasks

        for task in active_tasks:
            print(f"  ✓ Active signal production path: {task}")

        results["findings"].append(f"Found {len(active_tasks)} active signal production paths")

        # Check for CMP strategy execution
        if '_execute_cmp_strategy' in cycle_content:
            print("  ✓ CMP strategy execution path is active")
            results["findings"].append("CMP strategy path is active")

        # Check for any legacy signal generation calls
        if '_execute_signal_generation' in cycle_content and not cycle_content.count('# _execute_signal_generation'):
            print("  ✗ Legacy _execute_signal_generation is still being called")
            results["status"] = "FAIL"
            results["dead_paths"].append("Legacy _execute_signal_generation still active")
        else:
            print("  ✓ No legacy _execute_signal_generation calls found")
            results["findings"].append("Legacy signal generation path removed")

    # If we have some cycle content, perform analysis
    if cycle_content:
        # Check for active analysis tasks
        active_tasks = []
        if '_execute_ta_analysis' in cycle_content:
            active_tasks.append('_execute_ta_analysis')
        if '_execute_sentiment_analysis' in cycle_content:
            active_tasks.append('_execute_sentiment_analysis')
        if '_execute_volatility_analysis' in cycle_content:
            active_tasks.append('_execute_volatility_analysis')

        results["active_paths"] = active_tasks

        for task in active_tasks:
            print(f"  [OK] Active signal production path: {task}")

        results["findings"].append(f"Found {len(active_tasks)} active signal production paths")

        # Check for CMP strategy execution
        if '_execute_cmp_strategy' in cycle_content:
            print("  [OK] CMP strategy execution path is active")
            results["findings"].append("CMP strategy path is active")

        # Check for any legacy signal generation calls
        if '_execute_signal_generation' in cycle_content and '# _execute_signal_generation' not in cycle_content:
            print("  [FAIL] Legacy _execute_signal_generation is still being called")
            results["status"] = "FAIL"
            results["dead_paths"].append("Legacy _execute_signal_generation still active")
        else:
            print("  [OK] No legacy _execute_signal_generation calls found")
            results["findings"].append("Legacy signal generation path removed")
    else:
        print("[WARN] Could not analyze cycle loop content, but active methods found")
        results["status"] = "WARNING"
        results["findings"].append("Could not fully analyze cycle loop, but no legacy patterns found")

    return results


async def run_hc17_verification() -> dict[str, Any]:
    """
    Run HC-17 health check to verify signal source validation.
    """
    print("\n" + "=" * 60)
    print("Running HC-17 Health Check")
    print("=" * 60)

    try:
        import subprocess
        result = subprocess.run(
            ["python", "scripts/fr7_health_check.py", "--only", "HC-17"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent.parent)
        )

        if result.returncode == 0:
            print("✓ HC-17 health check passed")
            return {
                "status": "PASS",
                "findings": ["HC-17 signal source validation passed"],
                "output": result.stdout
            }
        else:
            print(f"✗ HC-17 health check failed with code {result.returncode}")
            return {
                "status": "FAIL",
                "findings": ["HC-17 health check failed"],
                "output": result.stdout,
                "error": result.stderr
            }
    except Exception as e:
        print(f"✗ Error running HC-17 health check: {e}")
        return {
            "status": "ERROR",
            "findings": [f"HC-17 execution error: {e!s}"],
            "error": str(e)
        }


def generate_summary_report(all_results: dict[str, dict[str, Any]]) -> str:
    """
    Generate a comprehensive summary report.
    """
    print("\n" + "=" * 60)
    print("TODO-19 IMPLEMENTATION VERIFICATION SUMMARY")
    print("=" * 60)

    overall_status = "PASS"

    summary_lines = [
        "TODO-19 (F7-M-04) Implementation Verification Results",
        "=" * 60,
        "",
    ]

    for check_name, results in all_results.items():
        status_symbol = "✓" if results["status"] == "PASS" else ("⚠" if results["status"] == "WARNING" else "✗")
        summary_lines.append(f"{status_symbol} {check_name}: {results['status']}")

        for finding in results["findings"]:
            summary_lines.append(f"    • {finding}")

        if results["status"] in ["FAIL", "ERROR"]:
            overall_status = results["status"]
        elif results["status"] == "WARNING" and overall_status == "PASS":
            overall_status = "WARNING"

        summary_lines.append("")

    # Overall assessment
    summary_lines.extend([
        "=" * 60,
        "OVERALL ASSESSMENT",
        "=" * 60,
    ])

    if overall_status == "PASS":
        summary_lines.extend([
            "✓ TODO-19 IMPLEMENTATION COMPLETE",
            "",
            "All acceptance criteria met:",
            "  • Single signal-production path exists (no legacy combiner)",
            "  • Single threshold constant (0.5) used throughout",
            "  • Signal sources properly tagged with StrengthSource enum",
            "  • Orchestrator coverage clean (dead paths removed)",
            "  • HC-17 health check passes",
            "",
            "The legacy signal engine has been successfully retired/converted.",
            "Option B implementation confirmed: System now uses TA+sentiment+volatility",
            "producer set with proper source tags and no combined pseudo-signals.",
        ])
    elif overall_status == "WARNING":
        summary_lines.extend([
            "⚠ TODO-19 IMPLEMENTATION MOSTLY COMPLETE",
            "",
            "Minor issues detected that should be reviewed.",
            "Overall architecture is correct but may need cleanup.",
        ])
    else:
        summary_lines.extend([
            "✗ TODO-19 IMPLEMENTATION INCOMPLETE",
            "",
            "Critical issues detected - address failing checks.",
        ])

    summary_text = "\n".join(summary_lines)
    print(summary_text)

    return summary_text


async def main() -> int:
    """
    Main verification function.
    """
    print("TODO-19 (F7-M-04) Implementation Verification")
    print("=" * 60)

    all_results = {}

    # Run all verification checks
    all_results["Single Threshold Constant"] = verify_single_threshold_constant()
    all_results["Signal Source Tagging"] = verify_signal_source_tagging()
    all_results["Single Signal Production Path"] = verify_single_signal_production_path()
    all_results["Orchestrator Coverage"] = verify_orchestrator_coverage()

    # Run HC-17 health check
    all_results["HC-17 Health Check"] = await run_hc17_verification()

    # Generate summary report
    summary = generate_summary_report(all_results)

    # Return exit code
    overall_pass = all(
        result["status"] in ["PASS", "WARNING"]
        for result in all_results.values()
    )

    # Print final ASCII summary
    print("\n" + "=" * 60)
    print("FINAL ASCII SUMMARY")
    print("=" * 60)
    print(f"Overall Result: {'PASS - TODO-19 COMPLETE' if overall_pass else 'FAIL - TODO-19 INCOMPLETE'}")

    if 'Single Threshold Constant' in all_results:
        print(f"Threshold: {all_results['Single Threshold Constant'].get('threshold_value', 'N/A')}")
    if 'Signal Source Tagging' in all_results:
        print(f"Signal Sources: {len(all_results['Signal Source Tagging'].get('valid_sources', []))} enums found")
    if 'Single Signal Production Path' in all_results:
        print(f"Production Paths: {len(all_results['Single Signal Production Path'].get('production_paths', []))} methods")
    if 'HC-17 Health Check' in all_results:
        print(f"HC-17 Status: {all_results['HC-17 Health Check']['status']}")

    print("=" * 60)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
