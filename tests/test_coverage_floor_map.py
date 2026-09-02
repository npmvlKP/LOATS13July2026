"""F8-H-04: guard coverage floor map against silent narrowing."""

import json
from pathlib import Path

import pytest


def _floor_map() -> dict[str, float]:
    """Load the coverage floor map as a flat module-floor dict."""
    path = Path(__file__).resolve().parents[1] / "coverage_floor_map.json"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return dict(data["floor_mapped_modules"])


EXPECTED_FLOOR_MAP: dict[str, float] = {
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


def test_coverage_floor_map_has_exact_fr_specified_modules():
    """coverage_floor_map.json must equal the FR-specified module set.

    This is a regression guard against the F8-H-04 gate-weakening pathology:
    modules with low coverage were removed from the floor map instead of being
    tested to their floors. Any narrowing must fail CI and force an explicit
    architectural decision.
    """
    actual = _floor_map()
    assert set(actual.keys()) == set(EXPECTED_FLOOR_MAP.keys()), (
        "coverage_floor_map.json module set differs from the FR-specified set; "
        f"expected {sorted(EXPECTED_FLOOR_MAP.keys())}, got {sorted(actual.keys())}"
    )


@pytest.mark.parametrize("module,floor", list(EXPECTED_FLOOR_MAP.items()))
def test_coverage_floor_map_floor_matches_fr(module: str, floor: float) -> None:
    """Each module's floor must match the FR-specified value."""
    actual = _floor_map()
    assert actual[module] == floor, (
        f"Floor for {module} was changed from {floor} to {actual[module]}. "
        "Changing a floor requires an explicit FR review."
    )
