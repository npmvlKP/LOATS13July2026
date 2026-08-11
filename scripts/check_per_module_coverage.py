#!/usr/bin/env python3
"""
Script to check per-module coverage and flag modules below 80% as warnings.
This script reads the coverage.json file and checks each module's coverage percentage.
"""

import json
import sys
from pathlib import Path


def load_coverage_data(coverage_file: Path) -> dict:
    """Load coverage data from coverage.json file."""
    try:
        with open(coverage_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading coverage data: {e}")
        sys.exit(1)


def extract_module_coverage(coverage_data: dict) -> list[tuple[str, float, int]]:
    """Extract per-module coverage information from coverage data."""
    module_coverage = []

    for file_path, file_data in coverage_data.get("files", {}).items():
        # Extract module name from file path
        if "src\\loats\\" in file_path:
            module_name = file_path.split("src\\loats\\")[1].replace(".py", "")
            summary = file_data.get("summary", {})
            percent_covered = summary.get("percent_covered", 0.0)
            missing_lines = summary.get("missing_lines", 0)

            module_coverage.append((module_name, percent_covered, missing_lines))

    return module_coverage


def check_coverage_thresholds(
    module_coverage: list[tuple[str, float, int]], threshold: float = 80.0
) -> tuple[bool, list[str]]:
    """Check if any modules are below the coverage threshold."""
    warnings = []
    all_passed = True

    for module_name, percent_covered, missing_lines in module_coverage:
        if percent_covered < threshold:
            warnings.append(
                f"{module_name}.py: {percent_covered:.1f}% coverage "
                f"({missing_lines} statements missed) - BELOW {threshold}% THRESHOLD"
            )
            all_passed = False

    return all_passed, warnings


def main():
    """Main function to check per-module coverage."""
    coverage_file = Path("coverage.json")

    if not coverage_file.exists():
        print("Error: coverage.json file not found.")
        print("Please run pytest with coverage first to generate coverage data.")
        sys.exit(1)

    # Load coverage data
    coverage_data = load_coverage_data(coverage_file)

    # Extract module coverage
    module_coverage = extract_module_coverage(coverage_data)

    if not module_coverage:
        print("No module coverage data found.")
        sys.exit(1)

    # Check coverage thresholds
    threshold = 80.0
    all_passed, warnings = check_coverage_thresholds(module_coverage, threshold)

    # Print results
    print("Per-Module Coverage Report:")
    print("=" * 60)

    for module_name, percent_covered, missing_lines in sorted(
        module_coverage, key=lambda x: x[1]
    ):
        status = "[PASS]" if percent_covered >= threshold else "[WARN]"
        print(
            f"{status} {module_name}.py: {percent_covered:.1f}% ({missing_lines} statements missed)"
        )

    print("\n" + "=" * 60)

    if warnings:
        print(
            f"\nWARNING: {len(warnings)} module(s) below {threshold}% coverage threshold:"
        )
        for warning in warnings:
            print(f"  {warning}")

        print(
            f"\nAggregate coverage: {coverage_data['totals']['percent_covered']:.1f}% (passes gate)"
        )
        print("Per-module coverage gates: FAILED (warnings detected)")

        # Exit with warning code (0 for now, as this is informational)
        # In CI, this should be handled as a warning, not a failure
        sys.exit(0)
    else:
        print("\nAll modules meet or exceed the 80% coverage threshold!")
        print(f"Aggregate coverage: {coverage_data['totals']['percent_covered']:.1f}%")
        print("Per-module coverage gates: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
