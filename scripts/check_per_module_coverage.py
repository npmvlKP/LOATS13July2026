#!/usr/bin/env python3
"""
Script to check per-module coverage against a floor map.
Enforces ≥80% coverage threshold for floor-mapped modules; others are informational.
This script reads coverage.json and coverage_floor_map.json.
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


def load_floor_map(floor_map_file: Path) -> dict:
    """Load coverage floor map from JSON file."""
    try:
        with open(floor_map_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading floor map: {e}")
        print(
            "Floor map is required. Using default fallback (orchestrator, trailing_stop, trade_decision, options ≥80%)."
        )
        # Fallback floor map for backward compatibility
        return {
            "floor_mapped_modules": {
                "orchestrator.py": 80.0,
                "trailing_stop.py": 80.0,
                "trade_decision.py": 80.0,
                "options.py": 80.0,
            },
            "excluded_modules": [
                "database_async_additions.py",
                "database_async_additions_clean.py",
                "database_async_additions_temp.py",
                "__init__.py",
            ],
        }


def extract_module_coverage(coverage_data: dict) -> list[tuple[str, float, int]]:
    """Extract per-module coverage information from coverage data."""
    module_coverage = []

    for file_path, file_data in coverage_data.get("files", {}).items():
        # Extract module name from file path
        if "src\\loats\\" in file_path or "src/loats/" in file_path:
            # Handle both Windows and Unix path separators
            if "src\\loats\\" in file_path:
                module_name = file_path.split("src\\loats\\")[1]
            else:
                module_name = file_path.split("src/loats/")[1]

            # Convert to forward slashes for consistency
            module_name = module_name.replace("\\", "/")

            summary = file_data.get("summary", {})
            percent_covered = summary.get("percent_covered", 0.0)
            missing_lines = summary.get("missing_lines", 0)

            module_coverage.append((module_name, percent_covered, missing_lines))

    return module_coverage


def check_floor_map_thresholds(
    module_coverage: list[tuple[str, float, int]], floor_map: dict
) -> tuple[bool, list[str], list[str]]:
    """Check if floor-mapped modules meet their coverage thresholds."""
    floor_mapped = floor_map.get("floor_mapped_modules", {})
    excluded = set(floor_map.get("excluded_modules", []))

    failures = []
    warnings = []

    for module_name, percent_covered, missing_lines in module_coverage:
        if module_name in excluded:
            continue

        if module_name in floor_mapped:
            threshold = floor_mapped[module_name]
            if percent_covered < threshold:
                failures.append(
                    f"{module_name}: {percent_covered:.1f}% coverage "
                    f"({missing_lines} statements missed) - "
                    f"BELOW {threshold}% FLOOR THRESHOLD"
                )
            else:
                pass  # Meets threshold
        # Non-mapped modules are informational only

    return len(failures) == 0, failures, warnings


def main():
    """Main function to check per-module coverage against floor map."""
    coverage_file = Path("coverage.json")
    floor_map_file = Path("coverage_floor_map.json")

    if not coverage_file.exists():
        print("Error: coverage.json file not found.")
        print("Please run pytest with coverage first to generate coverage data.")
        sys.exit(1)

    # Load coverage data
    coverage_data = load_coverage_data(coverage_file)

    # Load floor map
    floor_map = load_floor_map(floor_map_file)

    # Extract module coverage
    module_coverage = extract_module_coverage(coverage_data)

    if not module_coverage:
        print("No module coverage data found.")
        sys.exit(1)

    # Check floor map thresholds
    all_passed, failures, _ = check_floor_map_thresholds(module_coverage, floor_map)

    # Print results
    floor_mapped = floor_map.get("floor_mapped_modules", {})
    print("Per-Module Coverage Report (Floor-Mapped Enforcement)")
    print("=" * 70)

    # Print floor-mapped modules first
    print("\n[FLOOR-MAPPED MODULES - MUST MEET THRESHOLD]")
    for module_name, percent_covered, missing_lines in sorted(module_coverage):
        if module_name in floor_mapped:
            threshold = floor_mapped[module_name]
            status = "[PASS]" if percent_covered >= threshold else "[FAIL]"
            print(
                f"{status} {module_name}: {percent_covered:.1f}% "
                f"(threshold: {threshold}%, {missing_lines} statements missed)"
            )

    # Print other modules (informational only)
    print("\n[OTHER MODULES - INFORMATIONAL ONLY]")
    floor_mapped_set = set(floor_mapped.keys())
    excluded = set(floor_map.get("excluded_modules", []))

    for module_name, percent_covered, missing_lines in sorted(module_coverage):
        if module_name not in floor_mapped_set and module_name not in excluded:
            print(
                f"[INFO] {module_name}: {percent_covered:.1f}% "
                f"({missing_lines} statements missed)"
            )

    print("\n" + "=" * 70)

    if failures:
        print(f"\nFAILURE: {len(failures)} floor-mapped module(s) below threshold:")
        for failure in failures:
            print(f"  X {failure}")

        print(
            f"\nAggregate coverage: {coverage_data['totals']['percent_covered']:.1f}%"
        )
        print("Floor-mapped coverage gates: FAILED")
        print("CI will block until all floor-mapped modules meet their thresholds.")

        # Exit with non-zero code to indicate failure
        sys.exit(1)
    else:
        print("\nAll floor-mapped modules meet their coverage thresholds!")
        print(f"Aggregate coverage: {coverage_data['totals']['percent_covered']:.1f}%")
        print("Floor-mapped coverage gates: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
