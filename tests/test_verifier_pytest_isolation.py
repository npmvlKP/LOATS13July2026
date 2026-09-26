"""Verifier pytest children must be isolated from ambient pytest config.

Defect class (2026-09-26, canary-proven): scripts/ verifiers spawn
pytest subprocesses that inherit the caller's environment. With
``PYTEST_ADDOPTS`` exported (the documented private-basetemp suite
insulation), the child adopts the OUTER suite's basetemp and pytest's
session-start ``rm_rf`` demolishes that shared root mid-run -- outer
``tmp_path`` fixtures die and innocent legs falsely fail (live: the
TODO-24 live-gate leg 06:07 IST; the numbered-root variant killed the
lock-guard smoke child 05:01 IST). Without any basetemp, children
share (and, exiting first, prune) the numbered ``pytest-of-*`` tree.

Contract: each of the five pytest-spawning verifiers uses
``scripts/pytest_isolation.py`` -- child env scrubbed of
``PYTEST_ADDOPTS``, private ``--basetemp`` via direct argv (built by
``pytest_child_cmd`` or injected by ``with_private_basetemp``).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ISOLATION = REPO_ROOT / "scripts" / "pytest_isolation.py"

# script -> the cmd-side helper its spawn sites must call. Env-side,
# every script must call pytest_child_env() verbatim.
SPAWNING_SCRIPTS = {
    "verify_todo24_external.py": "pytest_child_cmd(",
    "verify_coverage_full.py": "pytest_child_cmd(",
    "fr7_health_check.py": "with_private_basetemp(",
    "verify_hc_all.py": "with_private_basetemp(",
    "eval_f8l05.py": "pytest_child_cmd(",
}


@pytest.fixture(scope="module")
def isolation_mod() -> object:
    spec = importlib.util.spec_from_file_location(
        "pytest_isolation_under_test", ISOLATION
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("script", "cmd_marker"), sorted(SPAWNING_SCRIPTS.items()))
def test_verifier_wires_the_isolation_helper(script: str, cmd_marker: str) -> None:
    """Each pytest-spawning verifier imports AND applies the helper.

    Import alone is not enough: the child's env and cmd must both flow
    through the helper, so both call names are required verbatim.
    """
    source = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "pytest_isolation" in source, (
        f"scripts/{script} spawns pytest without the isolation helper "
        "(ambient PYTEST_ADDOPTS / shared numbered temp root leak in)"
    )
    assert "pytest_child_env()" in source, (
        f"scripts/{script} must scrub PYTEST_ADDOPTS from the child env"
    )
    assert cmd_marker in source, (
        f"scripts/{script} must give its pytest child a private --basetemp "
        f"(via {cmd_marker.rstrip('(')})"
    )


def test_child_env_strips_pytest_addopts(isolation_mod) -> None:
    """The scrub is real: a poisoned environ comes out clean."""
    os.environ["PYTEST_ADDOPTS"] = "--basetemp=C:/outer-suite-root"
    try:
        env = isolation_mod.pytest_child_env()
    finally:
        del os.environ["PYTEST_ADDOPTS"]
    assert "PYTEST_ADDOPTS" not in env
    # Extras survive (script-specific probes keep their behavior).
    env2 = isolation_mod.pytest_child_env(extra={"OPENALGO_MODE": "ANALYZE"})
    assert env2["OPENALGO_MODE"] == "ANALYZE"
    assert "PYTEST_ADDOPTS" not in env2


def test_child_cmd_pins_private_basetemp(isolation_mod) -> None:
    """--basetemp rides as direct argv, unique per child, targets last."""
    cmd = isolation_mod.pytest_child_cmd(
        "tests/test_x.py",
        extra_args=["-q", "--no-header"],
    )
    assert cmd[0:3] == ["-m", "pytest", "--basetemp"], (
        "the private basetemp must precede everything an inherited "
        "addopts-like flag could reorder against"
    )
    bt = cmd[3]
    assert bt not in ("", "."), "basetemp must be an explicit path"
    assert cmd[-1] == "tests/test_x.py" and "-q" in cmd
    # Two children in one process never share a root.
    cmd2 = isolation_mod.pytest_child_cmd("tests/test_y.py")
    assert cmd2[3] != bt, "default basetemps must be unique per child"


def test_child_cmd_accepts_explicit_basetemp(isolation_mod) -> None:
    """Callers with their own scratch dir can pin the root verbatim."""
    cmd = isolation_mod.pytest_child_cmd("t.py", basetemp="C:/scratch/pt-x")
    assert cmd[3] == "C:/scratch/pt-x"


def test_with_private_basetemp_inserts_and_passes_through(isolation_mod) -> None:
    """Prebuilt-cmd runners: pytest argv gets the root, others don't."""
    pytest_cmd = ["py", "-m", "pytest", "tests/", "-q"]
    out = isolation_mod.with_private_basetemp(pytest_cmd, label="hc-12")
    assert out[:5] == ["py", "-m", "pytest", "--basetemp", out[4]]
    assert out[4] != pytest_cmd[0], "root must be a fresh path, unique per call"
    assert out[5:] == ["tests/", "-q"]
    # Non-pytest commands pass through untouched (generic runners).
    other = ["pip-audit", "--progress-spinner", "off"]
    assert isolation_mod.with_private_basetemp(other) == other
    # Malformed -m tail (nothing after -m) is left alone.
    assert isolation_mod.with_private_basetemp(["py", "-m"]) == ["py", "-m"]
