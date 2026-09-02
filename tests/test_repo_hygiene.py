"""Tests for the F8-C-02 repository hygiene guard.

Covers scripts/check_repo_hygiene.py: pattern matching semantics, the
tracked-file ceiling, the allowlist, and live repository invariants
(tracked set is clean, guard exits 0 on the real tree).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "check_repo_hygiene.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_repo_hygiene", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


class TestForbiddenPatterns:
    """Unit-test the pattern semantics of the guard."""

    def test_venv_paths_matched(self, guard):
        for path in (
            "loatsNEW/Scripts/python.exe",
            "loatsNEW/pyvenv.cfg",
            ".venv/Lib/site-packages/pydantic/__init__.py",
            "venv/bin/python",
            "some/venv/pyvenv.cfg",
        ):
            hits = guard._violations([path])
            assert hits, f"expected {path} to be flagged"
            assert hits[0][0] == path

    def test_tilde_junk_matched(self, guard):
        hits = guard._violations(["~/AppData/Local/Python Entry Points/abc"])
        assert hits, "literal ~ directory must be flagged"

    def test_env_files_matched(self, guard):
        for path in (".env", ".env.test", ".env.local"):
            assert guard._violations([path]), f"expected {path} to be flagged"

    def test_env_example_allowlisted(self, guard):
        assert guard._violations([".env.example"]) == []

    def test_tool_output_matched(self, guard):
        for path in (
            "node_modules/@upstash/context7-mcp/index.js",
            "htmlcov/index.html",
            "mypy-report/index.html",
            "coverage.json",
        ):
            assert guard._violations([path]), f"expected {path} to be flagged"

    def test_legitimate_paths_clean(self, guard):
        for path in (
            "src/loats/main.py",
            "tests/test_repo_hygiene.py",
            "scripts/check_repo_hygiene.py",
            "docs/x.md",
            "reports/health/health-final-20260901.json",
            "reports/p1_analyze_latency_20260828_084822.json",
            ".github/workflows/ci.yml",
        ):
            assert guard._violations([path]) == [], f"unexpected flag on {path}"

    def test_no_false_positive_on_env_prefixed_dirs(self, guard):
        # "ENV/*" must not catch unrelated top-level docs paths
        assert guard._violations(["environment.md"]) == []


class TestCeiling:
    def test_ceiling_is_sane(self, guard):
        assert 350 <= guard.TRACKED_FILE_CEILING <= 510

    def test_ceiling_above_current_count(self, guard):
        tracked = guard._tracked_files()
        assert len(tracked) <= guard.TRACKED_FILE_CEILING


class TestLiveRepository:
    """Live invariants of the real working tree (F8-C-02 acceptance)."""

    def test_no_tracked_venv(self):
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        tracked = out.stdout.splitlines()
        venv = [p for p in tracked if p.startswith(("loatsNEW/", ".venv/", "venv/"))]
        assert venv == [], f"tracked venv files remain: {venv[:5]}"

    def test_no_tracked_tilde(self):
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        tilde = [p for p in out.stdout.splitlines() if p.startswith("~/")]
        assert tilde == []

    def test_env_test_untracked_but_example_tracked(self):
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        tracked = set(out.stdout.splitlines())
        assert ".env.test" not in tracked
        assert ".env.example" in tracked

    def test_guard_passes_on_real_tree(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD_PATH)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_gitignore_covers_venv(self):
        for path in ("loatsNEW/Scripts/python.exe", ".env.test", "package.json"):
            proc = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT)
            assert proc.returncode == 0, f"{path} not ignored"
