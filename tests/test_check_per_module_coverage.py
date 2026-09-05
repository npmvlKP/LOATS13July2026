"""F8-H-04: mutation tests for the per-module coverage checker."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "check_per_module_coverage.py"
)


def _write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _run_script(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with valid coverage and floor map."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    valid_floor_map = {
        "floor_mapped_modules": {
            "alerts.py": 80.0,
            "backtest_sanity.py": 80.0,
            "database.py": 80.0,
            "database_async_additions.py": 80.0,
            "options.py": 85.0,
            "orchestrator.py": 80.0,
            "scheduler.py": 80.0,
            "strike_selection.py": 75.0,
            "trade_decision.py": 80.0,
            "trailing_stop.py": 80.0,
        },
        "excluded_modules": ["__init__.py"],
    }
    _write_json(workspace / "coverage_floor_map.json", valid_floor_map)

    valid_coverage = {
        "files": {
            "src\\loats\\alerts.py": {
                "summary": {"percent_covered": 85.0, "missing_lines": 10}
            },
            "src\\loats\\scheduler.py": {
                "summary": {"percent_covered": 82.0, "missing_lines": 8}
            },
        },
        "totals": {"percent_covered": 83.5},
    }
    _write_json(workspace / "coverage.json", valid_coverage)
    return workspace


def test_valid_floor_map_passes(tmp_workspace: Path) -> None:
    """All modules above floor -> exit 0."""
    result = _run_script(tmp_workspace)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_missing_module_in_floor_map_fails(tmp_workspace: Path) -> None:
    """Narrowing the floor map by removing a module -> exit 1 (F8-H-04 guard)."""
    floor_map = json.loads((tmp_workspace / "coverage_floor_map.json").read_text())
    floor_map["floor_mapped_modules"].pop("alerts.py")
    _write_json(tmp_workspace / "coverage_floor_map.json", floor_map)

    result = _run_script(tmp_workspace)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "F8-H-04" in result.stdout or "gate-weakening" in result.stdout


def test_lowered_floor_fails(tmp_workspace: Path) -> None:
    """Lowering a floor -> exit 1 (F8-H-04 guard)."""
    floor_map = json.loads((tmp_workspace / "coverage_floor_map.json").read_text())
    floor_map["floor_mapped_modules"]["alerts.py"] = 60.0
    _write_json(tmp_workspace / "coverage_floor_map.json", floor_map)

    result = _run_script(tmp_workspace)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "lowered" in result.stdout.lower() or "weakened" in result.stdout.lower()


def test_coverage_below_floor_fails(tmp_workspace: Path) -> None:
    """Coverage below a tracked floor -> exit 1."""
    coverage = json.loads((tmp_workspace / "coverage.json").read_text())
    coverage["files"]["src\\loats\\alerts.py"]["summary"]["percent_covered"] = 75.0
    _write_json(tmp_workspace / "coverage.json", coverage)

    result = _run_script(tmp_workspace)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BELOW" in result.stdout


def test_missing_coverage_json_fails(tmp_workspace: Path) -> None:
    """No coverage.json -> exit 1."""
    (tmp_workspace / "coverage.json").unlink()
    result = _run_script(tmp_workspace)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not found" in result.stdout.lower()


def test_stale_coverage_json_fails(tmp_workspace: Path) -> None:
    """coverage.json older than the freshness bound -> exit 1 (2026-09-05).

    Root cause being fixed: a stale, gitignored coverage.json once produced
    a misleading floor PASS because the gate never checked artifact age.
    """
    stale = time.time() - 25 * 3600
    os.utime(tmp_workspace / "coverage.json", (stale, stale))
    result = _run_script(tmp_workspace)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "stale" in result.stdout.lower()


def test_explicit_coverage_path_argument_honored(tmp_workspace: Path) -> None:
    """argv[1] selects the graded artifact (HC-13 contract, 2026-09-05).

    The health check passes reports/health/coverage.json explicitly; that
    argument used to be silently ignored while the root artifact was graded.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_workspace / "coverage.json")],
        cwd=tmp_workspace,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_explicit_stale_coverage_path_fails(tmp_workspace: Path) -> None:
    """The freshness bound applies to the explicit path too."""
    stale = time.time() - 30 * 3600
    os.utime(tmp_workspace / "coverage.json", (stale, stale))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_workspace / "coverage.json")],
        cwd=tmp_workspace,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "stale" in result.stdout.lower()
