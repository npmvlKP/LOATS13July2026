"""F8-L-06-R2 regression net: scripts/ wiring ratchet + commit-msg format gate.

The maintainability review (2026-09) measured two eroding patterns:

1. 49 of 90 tracked ``scripts/`` files were dead one-wave verifiers,
   cited only by frozen archives (docs/audit-history/, reports/
   ai-generated/) — invisible rot because nothing failed while they
   decayed. ``scripts/check_scripts_wiring.py`` makes orphaned scripts a
   hard failure on CI, pre-commit, and HC-30.

2. Status-essay commit subjects (``Update: ...``) displaced change
   descriptions for 5 consecutive commits because the configured
   commit-msg gate was never installed as a git hook and only checked
   prohibited phrases. ``scripts/commit_message_check.py`` now also
   enforces the CONTRIBUTING.md Conventional Commit first line.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "scripts" / "check_scripts_wiring.py"
HEALTH_CHECK = REPO_ROOT / "scripts" / "fr7_health_check.py"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CMC = REPO_ROOT / "scripts" / "commit_message_check.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_scripts_wiring_under_test", GUARD
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


class TestLivenessFixpoint:
    """The orphan fixpoint: seeds grow transitively, dead cliques stay dead."""

    def test_seed_only(self, guard) -> None:
        no_citations = lambda n, live: []  # noqa: E731
        live = guard._live_set(["a", "b"], {"a": ["tests/x.py"]}, no_citations)
        assert live == {"a"}

    def test_dead_clique_stays_dead(self, guard) -> None:
        # a and b cite only each other; a citation only counts when the
        # CITING script is already live (the real _script_citations
        # filter), so neither can bootstrap the other.
        citers = {"a": ["b"], "b": ["a"]}

        def citations(n, live):
            return [c for c in citers.get(n, ()) if c in live]

        live = guard._live_set(["a", "b"], {}, citations)
        assert live == set()

    def test_transitive_citation_becomes_live(self, guard) -> None:
        # tests cite a; a cites b -> b is live without its own external seed.
        def citations(n, live):
            return ["a"] if n == "b" and "a" in live else []

        live = guard._live_set(["a", "b"], {"a": ["ci.yml"]}, citations)
        assert live == {"a", "b"}

    def test_long_chain_terminates(self, guard) -> None:
        # a <- b <- c <- d dependency chain seeded only at a.
        def citations(n, live):
            order = {"b": "a", "c": "b", "d": "c"}
            cited_by = order.get(n)
            return [cited_by] if cited_by in live else []

        live = guard._live_set(
            ["a", "b", "c", "d"], {"a": ["pyproject.toml"]}, citations
        )
        assert live == {"a", "b", "c", "d"}


class TestBackReferenceRule:
    def test_win32_root_junk_grandfathered(self, guard) -> None:
        # The documented lockstep idiom (see win32_root_junk docstring):
        # guard/test surfaces import it directly after sys.path seeding.
        for line in (
            "tests/x.py:3: import win32_root_junk",
            "tests/x.py:4: from win32_root_junk import root_junk_findings",
            "scripts/check_repo_hygiene.py:30: import win32_root_junk",
        ):
            assert guard._is_allowed_back_ref(line) is True, line

    def test_other_scripts_imports_rejected(self, guard) -> None:
        for line in (
            "tests/x.py:5: import scripts.utils",
            "src/loats/core.py:9: from scripts.utils import thing",
            "tests/x.py:6: import utils",
            "src/loats/core.py:10: import cmp",
        ):
            assert guard._is_allowed_back_ref(line) is False, line

    def test_live_tree_has_no_back_references(self, guard) -> None:
        assert guard._back_reference_violations() == []


class TestLiveTree:
    def test_guard_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(GUARD)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"check_scripts_wiring.py fails on the live tree:\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-300:]}"
        )

    def test_guard_wired_into_ci(self) -> None:
        assert "check_scripts_wiring.py" in CI_YML.read_text(encoding="utf-8")

    def test_hc30_delegation_wired(self) -> None:
        text = HEALTH_CHECK.read_text(encoding="utf-8")
        assert "probe_hc30" in text, "HC-30 probe function missing"
        assert '"HC-30"' in text, (
            "HC-30 missing from the health-check registry — the TODO-28 "
            "silent-deletion class must stay impossible"
        )


@pytest.mark.parametrize(
    ("message", "expected_rc"),
    [
        ("fix(test): make P5 resume-refusal test hermetic\n\nbody\n", 0),
        ("chore: subject only\n", 0),
        ("feat(p5)!: breaking change subject\n", 0),
        ("Merge branch 'main' into fix/fr7-wave\n", 0),
        ('Revert "feat(p5): subject"\n', 0),
        ("Update: fix(test): status essay with evidence narrative\n", 1),
        ("no conventional prefix at all\n", 1),
        ("wip: almost there\n", 1),
        ("fix: ready for deployment\n", 1),
        ("fix: subject\n\nAll gates pass; ready for production.\n", 1),
        ("", 1),
    ],
)
def test_commit_message_gate(tmp_path, message, expected_rc) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(message, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CMC), str(msg_file)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == expected_rc, (
        f"expected rc={expected_rc} for {message!r}, got {proc.returncode}: "
        f"{proc.stdout}"
    )
