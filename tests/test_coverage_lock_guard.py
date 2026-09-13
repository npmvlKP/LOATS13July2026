"""Coverage mutual-exclusion guard (tests/conftest.py), 2026-09-13 incident.

On 2026-09-13 a manual ``pytest --cov`` run collided with a concurrently
running ``scripts/verify_coverage_full.py`` (PID 33876): both pytest
processes wrote parallel coverage data files in the repo root, and the
manual run's ``pytest-cov`` combine step swept the verifier's still-open
data file — ``PermissionError: [WinError 32]`` raised from
``coverage.data.combine_parallel_data`` as a pytest INTERNALERROR after
1815 passes, losing the run's verdict (its one real failure was also
rendered unrecoverable because the green verifier run overwrote
``.pytest_cache/v/cache/lastfailed``).

Contract pinned here (guard lives in tests/conftest.py — the single
choke point every coverage writer in this repo passes through: manual
runs, CI, pre-push hooks, and the embedded runs of
verify_coverage_full.py / fr7_health_check.py HC-12 / verify_hc_all.py):

1. pytest processes invoked with any ``--cov*`` flag take an exclusive
   cross-process lock (``.git/coverage_gate.lock``, msvcrt/fcntl
   byte-range) for the whole session. A second concurrent writer is
   refused fail-closed (exit code 4, before any test runs) instead of
   crashing at combine time.
2. Non-coverage pytest invocations are never gated (nested test-inside-
   test subprocesses, ``python tests/test_x.py`` legacies).
3. The kill switch ``LOATS_COV_LOCK_DISABLED=1`` bypasses the lock for
   documented single-writer-certain situations.
4. The acquisition site is ``pytest_configure`` and nothing else —
   session scope, never per-test.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = REPO_ROOT / "tests" / "conftest.py"
_CONFTEST_ALIAS = "conftest_cov_guard_under_test"


@pytest.fixture(scope="module")
def conftest_mod() -> object:
    """Load tests/conftest.py under a unique alias (house loader idiom)."""
    spec = importlib.util.spec_from_file_location(_CONFTEST_ALIAS, CONFTEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestCovGuardPresence:
    def test_conftest_defines_coverage_lock_guard(self, conftest_mod) -> None:
        for name in ("COV_LOCK_ENABLED", "_cov_lock_path", "_acquire_coverage_lock"):
            assert hasattr(conftest_mod, name), f"conftest missing {name}"
        assert conftest_mod.COV_LOCK_ENABLED is True


class TestCovDetection:
    """Any --cov* token requests coverage; plain pytest runs do not."""

    def test_plain_pytest_not_detected(self, conftest_mod) -> None:
        assert conftest_mod._cov_requested(["-m", "pytest", "tests/", "-q"]) is False

    def test_dash_dash_cov_detected(self, conftest_mod) -> None:
        assert conftest_mod._cov_requested(["-m", "pytest", "--cov", "tests/"]) is True

    def test_cov_equals_form_detected(self, conftest_mod) -> None:
        assert conftest_mod._cov_requested(["--cov=src", "--cov-branch"]) is True

    def test_cov_report_only_detected(self, conftest_mod) -> None:
        assert conftest_mod._cov_requested(["--cov-report=json:coverage.json"]) is True

    def test_after_double_dash_detected(self, conftest_mod) -> None:
        assert conftest_mod._cov_requested(["-m", "pytest", "--", "--cov"]) is True


class TestCovLockExclusion:
    def test_second_cov_writer_refused_then_reacquirable(
        self, conftest_mod, tmp_path
    ) -> None:
        lock = conftest_mod._cov_lock_path(tmp_path)
        first = conftest_mod._acquire_coverage_lock(lock)
        assert first is not None
        try:
            second = conftest_mod._acquire_coverage_lock(lock)
            assert second is None, "second concurrent writer must be refused"
        finally:
            conftest_mod._release_coverage_lock(first)
        third = conftest_mod._acquire_coverage_lock(lock)
        assert third is not None, "lock must be reacquirable after release"
        conftest_mod._release_coverage_lock(third)

    def test_release_tolerates_refused_handle(self, conftest_mod, tmp_path) -> None:
        lock = conftest_mod._cov_lock_path(tmp_path)
        holder = conftest_mod._acquire_coverage_lock(lock)
        assert holder is not None
        refused = conftest_mod._acquire_coverage_lock(lock)
        assert refused is None
        conftest_mod._release_coverage_lock(refused)  # must not raise
        conftest_mod._release_coverage_lock(holder)


class TestCovLockKillSwitch:
    def test_disabled_env_admits_cov_run_despite_held_lock(self, conftest_mod) -> None:
        """LOATS_COV_LOCK_DISABLED=1 bypasses the guard end-to-end.

        The child pytest process reads the kill switch at conftest import
        (the same production read path), so with the guard disabled its
        --cov run must complete even while this process holds the lock.
        """
        holder = conftest_mod._acquire_coverage_lock(
            conftest_mod._cov_lock_path(REPO_ROOT)
        )
        # Under a --cov parent suite this acquire returns None because the
        # parent's own pytest_configure already holds the gate -- the lock
        # IS held either way, which is the only precondition under test.
        try:
            proc = subprocess.run(
                [
                    *_base_child_cmd(
                        REPO_ROOT / "tests" / "test_coverage_lock_guard.py"
                    ),
                    "--cov=src",
                    "--cov-fail-under=1",
                    "-k",
                    "test_plain_pytest_not_detected",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=300,
                env={**os.environ, "LOATS_COV_LOCK_DISABLED": "1"},
            )
        finally:
            conftest_mod._release_coverage_lock(holder)
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "1 passed" in proc.stdout


class TestCovGuardWiring:
    """The guard is wired exactly once, at session scope."""

    def test_pytest_configure_acquires_session_lock(self) -> None:
        tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
        holders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            calls = [
                sub
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "_acquire_coverage_lock"
            ]
            if calls:
                holders.append(node.name)
        assert holders == ["pytest_configure"], (
            "lock acquisition must live only in pytest_configure "
            f"(session scope); found in: {holders}"
        )

    def test_detection_reads_sys_argv(self) -> None:
        tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
        configure = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "pytest_configure"
        )
        assert "sys.argv" in ast.unparse(configure)


def _write_smoke_test(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "test_cov_guard_smoke.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )


def _base_child_cmd(test_dir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        str(test_dir),
    ]


class TestNonCovRunPasses:
    def test_bare_pytest_smoke_completes(self, tmp_path) -> None:
        """A non-coverage pytest run is never gated by the guard."""
        _write_smoke_test(tmp_path)
        proc = subprocess.run(
            _base_child_cmd(tmp_path),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=240,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "1 passed" in proc.stdout

    def test_cov_run_passes_when_lock_free(self) -> None:
        """A legitimate --cov run on a free lock completes normally.

        Runs a fast slice of this very test file through the REAL repo
        conftest (the production acquisition path). Skipped when the
        parent suite itself holds the cov lock (i.e. this suite was
        launched with --cov): the child would be refused by the very
        guard under test, which is the other test's contract, not this
        one's.
        """
        if os.environ.get("LOATS_COV_LOCK_ACTIVE") == "1":
            pytest.skip("parent suite holds the cov lock (--cov run)")
        proc = subprocess.run(
            [
                *_base_child_cmd(REPO_ROOT / "tests" / "test_coverage_lock_guard.py"),
                "--cov=src",
                "--cov-fail-under=1",
                "-k",
                "TestCovGuardPresence",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "1 passed" in proc.stdout


class TestConcurrentCovRefusal:
    """End-to-end: a --cov pytest run is refused while the lock is held.

    The lock file is the REAL repo gate (cross-process by design); the
    in-process holder below excludes the child exactly as a concurrent
    verifier run would be excluded in production. Under a --cov parent
    suite the parent already holds the lock via pytest_configure (the
    in-process acquire returns None and its release is a no-op), and the
    child is still excluded by the parent's session lock — valid in both
    parent modes.
    """

    def test_cov_run_refused_while_lock_held(self, conftest_mod) -> None:
        holder = conftest_mod._acquire_coverage_lock(
            conftest_mod._cov_lock_path(REPO_ROOT)
        )
        try:
            proc = subprocess.run(
                [
                    *_base_child_cmd(
                        REPO_ROOT / "tests" / "test_coverage_lock_guard.py"
                    ),
                    "--cov=src",
                    "--cov-fail-under=1",
                    "-k",
                    "test_plain_pytest_not_detected",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=300,
            )
        finally:
            conftest_mod._release_coverage_lock(holder)
        assert proc.returncode == 4, (
            f"refused cov run must exit 4, got {proc.returncode}: {proc.stdout[-1500:]}"
        )
        # pytest.exit routes its message to stderr; grade the combined stream.
        refusal_output = proc.stdout + proc.stderr
        assert "--cov" in refusal_output, "refusal banner must name the flag"
        assert "LOATS_COV_LOCK_DISABLED" in refusal_output, (
            "refusal banner must document the kill switch"
        )
        assert "1 passed" not in refusal_output, "refused run must not execute tests"
