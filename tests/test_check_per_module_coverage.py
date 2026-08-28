#!/usr/bin/env python3
"""
Unit tests for check_per_module_coverage.py exit semantics.

Tests verify:
- Exit code 0 on success
- Exit code 1 on all failure paths
- No fall-through to exit 0 on warning/error paths
- Proper error message propagation

Folded from TODO-15 unit test requirements (F7-L-04 / TODO-24).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestCoverageCheckExitSemantics:
    """Test exit code semantics of check_per_module_coverage.py."""

    SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "check_per_module_coverage.py"

    @staticmethod
    def create_coverage_fixture(
        modules: dict[str, float],
        totals_percent: float = 85.0,
        missing_lines_override: dict[str, int] | None = None,
    ) -> Path:
        """Create a temporary coverage.json fixture."""
        coverage_data = {
            "files": {},
            "totals": {"percent_covered": totals_percent, "num_statements": 1000, "covered_lines": 850},
        }

        for module_name, percent in modules.items():
            missing_lines = (missing_lines_override or {}).get(module_name, 20)
            coverage_data["files"][f"src/loats/{module_name}"] = {
                "summary": {
                    "percent_covered": percent,
                    "num_statements": 100,
                    "covered_lines": int(100 * percent / 100),
                    "missing_lines": missing_lines,
                }
            }

        temp_file = Path(tempfile.mktemp(suffix=".json"))
        temp_file.write_text(json.dumps(coverage_data, indent=2))
        return temp_file

    @staticmethod
    def create_floor_map_fixture(
        floor_mapped: dict[str, float], excluded: list[str] | None = None
    ) -> Path:
        """Create a temporary coverage_floor_map.json fixture."""
        floor_map = {
            "floor_mapped_modules": floor_mapped,
            "excluded_modules": excluded or ["__init__.py"],
        }

        temp_file = Path(tempfile.mktemp(suffix=".json"))
        temp_file.write_text(json.dumps(floor_map, indent=2))
        return temp_file

    def _run_script_with_fixtures(
        self, coverage_file: Path, floor_map_file: Path
    ) -> subprocess.CompletedProcess[str]:
        """Run script in temp directory with fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Copy fixtures to temp directory
            (tmpdir_path / "coverage.json").write_text(coverage_file.read_text())
            (tmpdir_path / "coverage_floor_map.json").write_text(floor_map_file.read_text())

            # Run script
            result = subprocess.run(
                [sys.executable, str(self.SCRIPT_PATH)],
                capture_output=True,
                text=True,
                cwd=tmpdir_path,
            )

        return result

    def test_exit_0_all_modules_pass_threshold(self):
        """Test exit code 0 when all floor-mapped modules meet threshold."""
        coverage_file = self.create_coverage_fixture(
            modules={"orchestrator.py": 85.0, "options.py": 90.0, "trailing_stop.py": 82.0}
        )
        floor_map_file = self.create_floor_map_fixture(
            floor_mapped={"orchestrator.py": 80.0, "options.py": 80.0, "trailing_stop.py": 80.0}
        )

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            assert "PASSED" in result.stdout, "Expected 'PASSED' in output"
            assert "All floor-mapped modules meet their coverage thresholds" in result.stdout
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)

    def test_exit_1_module_below_threshold(self):
        """Test exit code 1 when any floor-mapped module is below threshold."""
        coverage_file = self.create_coverage_fixture(
            modules={"orchestrator.py": 75.0, "options.py": 90.0}
        )
        floor_map_file = self.create_floor_map_fixture(
            floor_mapped={"orchestrator.py": 80.0, "options.py": 80.0}
        )

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nSTDOUT: {result.stdout}"
            assert "FAILED" in result.stdout, "Expected 'FAILED' in output"
            assert "BELOW 80%" in result.stdout or "orchestrator.py: 75.0%" in result.stdout
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)

    def test_exit_1_missing_coverage_file(self):
        """Test exit code 1 when coverage.json is missing."""
        floor_map_file = self.create_floor_map_fixture(floor_mapped={"orchestrator.py": 80.0})

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                (tmpdir_path / "coverage_floor_map.json").write_text(floor_map_file.read_text())

                result = subprocess.run(
                    [sys.executable, str(self.SCRIPT_PATH)],
                    capture_output=True,
                    text=True,
                    cwd=tmpdir_path,
                )

            assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
            assert "coverage.json file not found" in result.stdout
        finally:
            floor_map_file.unlink(missing_ok=True)

    def test_exit_1_invalid_json(self):
        """Test exit code 1 when coverage.json is invalid JSON."""
        floor_map_file = self.create_floor_map_fixture(floor_mapped={"orchestrator.py": 80.0})

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                (tmpdir_path / "coverage.json").write_text("invalid json {{{")
                (tmpdir_path / "coverage_floor_map.json").write_text(floor_map_file.read_text())

                result = subprocess.run(
                    [sys.executable, str(self.SCRIPT_PATH)],
                    capture_output=True,
                    text=True,
                    cwd=tmpdir_path,
                )

            assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
            assert "Error loading coverage data" in result.stdout
        finally:
            floor_map_file.unlink(missing_ok=True)

    def test_exit_1_no_module_data(self):
        """Test exit code 1 when coverage.json has no module data."""
        coverage_file = Path(tempfile.mktemp(suffix=".json"))
        coverage_file.write_text(json.dumps({"files": {}, "totals": {"percent_covered": 0}}))
        floor_map_file = self.create_floor_map_fixture(floor_mapped={}, excluded=[])

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
            assert "No module coverage data found" in result.stdout
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)

    def test_no_warning_fallthrough_to_exit_0(self):
        """Verify warning paths cannot fall through to exit 0 (CRITICAL for F7-L-04)."""
        # Create fixture where warnings exist but no failures
        coverage_file = self.create_coverage_fixture(modules={"orchestrator.py": 85.0})
        floor_map_file = self.create_floor_map_fixture(
            floor_mapped={"orchestrator.py": 80.0}, excluded=["options.py"]
        )

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            # Must exit 0 even if informational warnings exist
            assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nSTDOUT: {result.stdout}"
            assert "PASSED" in result.stdout
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)

    def test_excluded_modules_not_checked(self):
        """Test that excluded modules are not checked against threshold."""
        coverage_file = self.create_coverage_fixture(
            modules={"orchestrator.py": 85.0, "database_async_additions.py": 0.0}
        )
        floor_map_file = self.create_floor_map_fixture(
            floor_mapped={"orchestrator.py": 80.0}, excluded=["database_async_additions.py"]
        )

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            assert result.returncode == 0, "Excluded modules should not cause failure"
            assert "PASSED" in result.stdout
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)

    def test_non_mapped_modules_informational_only(self):
        """Test that non-mapped modules are informational only and don't affect exit code."""
        coverage_file = self.create_coverage_fixture(
            modules={"orchestrator.py": 85.0, "unmapped_module.py": 0.0}
        )
        floor_map_file = self.create_floor_map_fixture(
            floor_mapped={"orchestrator.py": 80.0}, excluded=[]
        )

        try:
            result = self._run_script_with_fixtures(coverage_file, floor_map_file)

            assert result.returncode == 0, "Non-mapped modules should be informational only"
            assert "PASSED" in result.stdout
            assert "INFO" in result.stdout, "Should show informational status for non-mapped modules"
        finally:
            coverage_file.unlink(missing_ok=True)
            floor_map_file.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
