"""Isolated pytest child environments for verifier scripts.

Root cause (2026-09-26, live-proven): verifier scripts spawn pytest
subprocesses that inherit the caller's environment. When an operator
shell exports ``PYTEST_ADDOPTS`` (the documented private ``--basetemp``
suite-insulation recipe), the child adopts the OUTER suite's basetemp
as its own and pytest's session start ``rm_rf``-es that shared root --
demolishing the outer suite's live ``tmp_path`` fixtures mid-run
(TODO-24 live-gate leg wedged/falsely failed 06:07 IST; the numbered
``%TEMP%/pytest-of-*`` variant killed the lock-guard smoke child
05:01 IST). Canary-proven deterministically: a ``tmp_path``-consuming
child with inherited ``PYTEST_ADDOPTS`` deletes the shared root's
contents before its first test runs.

Contract pinned by ``tests/test_verifier_pytest_isolation.py``: every
pytest spawned from ``scripts/`` runs with ``PYTEST_ADDOPTS`` scrubbed
from its environment AND an explicit private ``--basetemp`` of its own
-- never the caller's root, never the shared numbered temp root.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def pytest_child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a subprocess child: ``PYTEST_ADDOPTS`` scrubbed.

    The caller's addopts must never leak into a verifier's pytest child:
    the child would otherwise re-grade itself under the operator's
    flags -- including the shared ``--basetemp`` that turns the child's
    session start into an outer-suite demolition. ``extra`` is applied
    last so script-specific variables (OPENALGO_* probes, USERPROFILE
    repairs) keep their existing behavior.
    """
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    if extra:
        env.update(extra)
    return env


def pytest_child_cmd(
    *targets: str,
    extra_args: list[str] | None = None,
    basetemp: str | Path | None = None,
) -> list[str]:
    """Argv (after the interpreter) for an isolated pytest child.

    The private ``--basetemp`` rides as DIRECT argv -- never via
    ``PYTEST_ADDOPTS``, which shlex parses and would consume Windows
    backslash separators. Default basetemp is a unique directory under
    the interpreter's resolved system temp dir, so two children in one
    process never share a root. The directory is created by pytest
    itself at child session start; this helper only names it.
    """
    if basetemp is None:
        basetemp = (
            Path(tempfile.gettempdir()) / f"pytest-verifier-{uuid.uuid4().hex[:8]}"
        )
    cmd = ["-m", "pytest", "--basetemp", str(basetemp)]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(targets)
    return cmd


def with_private_basetemp(cmd: list[str], label: str = "verifier") -> list[str]:
    """Insert a private ``--basetemp`` into an EXISTING pytest argv.

    For call sites that pre-build the full command list (health-check
    gate tables): finds the ``-m pytest`` pair and inserts ``--basetemp
    <unique root>`` right after it, returning a new list. Non-pytest
    commands (pip-audit, gitleaks, flake8 probes) pass through
    untouched, so generic runners can apply it unconditionally.
    """
    try:
        m = cmd.index("-m")
    except ValueError:
        return list(cmd)
    if m + 1 >= len(cmd) or cmd[m + 1] != "pytest":
        return list(cmd)
    root = Path(tempfile.gettempdir()) / f"pytest-{label}-{uuid.uuid4().hex[:8]}"
    return [*cmd[: m + 2], "--basetemp", str(root), *cmd[m + 2 :]]
