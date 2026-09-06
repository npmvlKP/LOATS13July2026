#!/usr/bin/env python3
"""
Script to check per-module coverage against a floor map.

F8-H-04: enforces the FR-specified per-module floor map
(coverage_floor_map.json) against coverage.json. The fallback floor map is
intentionally identical to the tracked map so that the script never silently
accepts a narrowed gate.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Staleness guard (root-cause fix, 2026-09-05): a floor gate graded
# against a stale, gitignored coverage.json is a false PASS. CI always
# regenerates the artifact in the same job (see .github/workflows/ci.yml),
# so this bound only bites local/interactive invocations that would
# otherwise silently reuse an old artifact.
MAX_COVERAGE_AGE_HOURS = 24.0

# F8-H-04 canonical FR-specified floor map. Kept in one place so the fallback
# and the tracked json file cannot drift apart.
FR_FLOOR_MAP: dict[str, float] = {
    "orchestrator.py": 80.0,
    "trailing_stop.py": 80.0,
    "trade_decision.py": 80.0,
    "options.py": 85.0,
    "database.py": 80.0,
    "database_async_additions.py": 80.0,
    "alerts.py": 80.0,
    "scheduler.py": 80.0,
    "backtest_sanity.py": 80.0,
    "strike_selection.py": 75.0,
}

EXCLUDED_MODULES: list[str] = [
    "database_async_additions.py",
    "database_async_additions_clean.py",
    "database_async_additions_temp.py",
    "__init__.py",
]


def load_coverage_data(coverage_file: Path) -> dict:
    """Load coverage data from coverage.json file."""
    try:
        with open(coverage_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading coverage data: {e}")
        sys.exit(1)


def load_floor_map(floor_map_file: Path) -> dict:
    """Load coverage floor map from JSON file.

    F8-H-04: fallback is the canonical FR floor map, not a narrowed gate.
    """
    try:
        with open(floor_map_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: could not load floor map ({e}); using FR fallback.")
        return {
            "floor_mapped_modules": FR_FLOOR_MAP,
            "excluded_modules": EXCLUDED_MODULES,
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


def main() -> None:
    """Main function to check per-module coverage against floor map."""
    # Optional argv[1] = explicit coverage.json path (used by
    # fr7_health_check.py HC-13 to grade its own freshly generated
    # reports/health/coverage.json). Without it, the CI/root default
    # ./coverage.json is graded. The argument was previously accepted and
    # silently ignored — HC-13 unknowingly graded the root artifact.
    coverage_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("coverage.json")
    floor_map_file = Path("coverage_floor_map.json")

    if not coverage_file.exists():
        print("Error: coverage.json file not found.")
        print("Please run pytest with coverage first to generate coverage data.")
        sys.exit(1)

    # Staleness guard (root-cause fix, 2026-09-05): coverage.json is a
    # gitignored artifact that can survive from an older suite run. A PASS
    # graded against a stale artifact is a false read, so the gate demands
    # the artifact be younger than MAX_COVERAGE_AGE_HOURS. Delete and
    # regenerate (pytest --cov) to clear.
    coverage_stat = coverage_file.stat()
    age_h = (datetime.now(UTC).timestamp() - coverage_stat.st_mtime) / 3600.0
    if age_h > MAX_COVERAGE_AGE_HOURS:
        print(
            f"Error: coverage.json is stale (age {age_h:.1f}h > "
            f"max {MAX_COVERAGE_AGE_HOURS:.0f}h). A floor gate PASS must "
            "measure the current tree — regenerate it with "
            "`pytest --cov=src/loats --cov-report=json:coverage.json`."
        )
        sys.exit(1)

    # Load coverage data
    coverage_data = load_coverage_data(coverage_file)

    # Load floor map
    floor_map = load_floor_map(floor_map_file)

    # Safety check: if the tracked floor map is missing modules or has lowered
    # floors, this script fails-closed (F8-H-04 regression guard).
    tracked = floor_map.get("floor_mapped_modules", {})
    if set(tracked.keys()) != set(FR_FLOOR_MAP.keys()):
        print(
            "CRITICAL: coverage_floor_map.json module set does not match the "
            "FR-specified set. This is the F8-H-04 gate-weakening pathology."
        )
        print(f"Expected: {sorted(FR_FLOOR_MAP.keys())}")
        print(f"Got: {sorted(tracked.keys())}")
        sys.exit(1)

    lowered = [
        module
        for module in FR_FLOOR_MAP
        if tracked.get(module, 0.0) < FR_FLOOR_MAP[module]
    ]
    if lowered:
        print(
            "CRITICAL: coverage_floor_map.json has lowered floors for "
            f"{', '.join(lowered)}. Floors must not be weakened."
        )
        sys.exit(1)

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
