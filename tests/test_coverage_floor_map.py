"""F8-H-04: guard the coverage floor map against silent narrowing.

The floor map's enforcement single source of truth is ``FR_FLOOR_MAP``
in ``scripts/check_per_module_coverage.py``. ``coverage_floor_map.json``
itself is a deliberately UNTRACKED artifact (a TODO-21 junk pattern,
gitignored), so a fresh CI checkout has no such file -- an earlier
version of this module read it from the repo root and failed on every
GitHub-hosted run with ``FileNotFoundError``. The regression guard is
therefore a double-entry check: the script's enforced map AND its
fail-closed fallback must both equal the FR-specified map pinned here.
Any narrowing (module removed, floor lowered) fails CI and forces an
explicit architectural decision -- exactly the F8-H-04 gate-weakening
pathology this guard exists to prevent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "check_per_module_coverage.py"
)

_spec = importlib.util.spec_from_file_location("_check_per_module_coverage", _SCRIPT)
assert _spec is not None and _spec.loader is not None  # repo layout invariant
_check_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_check_module)

# FR-specified floor map. This frozen copy is the independent second entry:
# scripts/check_per_module_coverage.py must not weaken or extend it.
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


def test_enforced_floor_map_matches_fr_exactly():
    """The enforced map must equal the FR-specified set AND floors.

    A missing module, an extra module, or a lowered floor all break dict
    equality and fail this guard.
    """
    assert _check_module.FR_FLOOR_MAP == EXPECTED_FLOOR_MAP


def test_fallback_floor_map_matches_fr_exactly(tmp_path):
    """The script's fail-closed fallback must match the FR map.

    When the untracked ``coverage_floor_map.json`` is absent (every fresh
    CI checkout), ``load_floor_map`` must fall back to the canonical FR
    map -- never to a narrowed gate.
    """
    fallback = _check_module.load_floor_map(tmp_path / "does-not-exist.json")
    assert fallback["floor_mapped_modules"] == EXPECTED_FLOOR_MAP


@pytest.mark.parametrize("module,floor", sorted(EXPECTED_FLOOR_MAP.items()))
def test_floor_values_match_fr(module: str, floor: float) -> None:
    """Per-module diagnosability: each floor must equal its FR value."""
    assert _check_module.FR_FLOOR_MAP[module] == pytest.approx(floor)
