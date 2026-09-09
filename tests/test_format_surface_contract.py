"""Format-surface contract: sweep scope == enforced scope (2026-09-09 wave).

Root cause this file pins: ruff 0.16 formats python fences inside Markdown
files, which silently widened every repository-root ``ruff format --check``
sweep from the CI-enforced surface (``src/ tests/ scripts/``) to the whole
tree -- including ``docs/audit-history/`` and ``reports/ai-generated/``,
which are point-in-time audit evidence preserved verbatim (see the E501
per-file-ignores rationale in pyproject.toml: such files "must not be
mutated"). 41 files were flagged by an unwired root-wide sweep while every
wired gate stayed green: the drift class is "a gate contract applied on one
surface and missed on another".

Contract enforced here:
  1. A root-wide format sweep is GREEN (frozen-evidence md excluded via
     pyproject ``extend-exclude`` at the ``*.md`` layer only -- tracked
     ``*.py`` under those trees remains gated by both the formatter and
     the root-scope lint job).
  2. Non-frozen Markdown python fences REMAIN gated (the freeze must not
     become a blanket md amnesty).
  3. Frozen files stay reachable through explicit paths (ruff excludes
     never apply to explicitly-passed paths) so a future reconciliation
     sweep can still format them deliberately.
  4. ``docs/var_engine.md`` (live doc) is formatter-canonical.
  5. The CI ruff job scopes stay exactly as documented; narrowing them
     would silently void this contract.
  6. Advisory-waiver surface lockstep: the ADR-0010 nltk waiver
     (PYSEC-2026-3740) must appear on BOTH audit surfaces -- CI
     (security.yml/ci.yml) and the pre-push pip-audit hook -- or every
     pre-push fails closed while CI stays green (live-verified defect,
     same surface-mismatch class).
"""

from __future__ import annotations

import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SECURITY_YML = REPO_ROOT / ".github" / "workflows" / "security.yml"
PRECOMMIT_YML = REPO_ROOT / ".pre-commit-config.yaml"
ADR_0010 = REPO_ROOT / "docs" / "adr" / "0010-nltk-dev-toolchain-triage.md"

FROZEN_DIRS = ("docs/audit-history", "reports/ai-generated")
# Live (non-frozen) markdown files whose python fences must stay gated.
GATED_MD = (
    "docs/health-verification-system.md",
    "docs/adr/0004-vollib-handrolled-migration.md",
)
WAIVED_VULN_ID = "PYSEC-2026-3740"
UNFORMATTED_FENCE = "```python\nx=1\n```\n"

RUFF_TIMEOUT_S = 120


def _repo_relative(p: Path) -> str:
    """Config-file text with forward slashes and CRLF stripped (POSIX+Windows)."""
    return p.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\\", "/")


def _ruff_format_check(*targets: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "--no-cache", *targets],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=RUFF_TIMEOUT_S,
    )


def _unlink_robust(path: Path) -> None:
    """Delete with retries: Windows AV scanners hold files briefly open."""
    for attempt in range(5):
        try:
            path.unlink()
            return
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    path.unlink(missing_ok=True)


@pytest.mark.skipif(
    not PYPROJECT_TOML.exists() or not CI_YML.exists(),
    reason="repo config surfaces absent",
)
class TestFormatSurfaceContract:
    """Root-wide format sweeps must not flag frozen evidence, and the
    freeze must not extend past the evidence trees' markdown."""

    def test_root_scope_format_sweep_is_green(self) -> None:
        r = _ruff_format_check(".")
        assert r.returncode == 0, (
            "root-wide ruff format --check is red. Frozen-evidence markdown"
            " must be excluded via pyproject [tool.ruff] extend-exclude"
            " ('docs/audit-history/*.md', 'reports/ai-generated/*.md');"
            " anything else must be formatted. Output:\n"
            f"{r.stdout[-3000:]}{r.stderr[-1000:]}"
        )

    def test_enforced_scope_format_stays_green(self) -> None:
        r = _ruff_format_check("src/", "tests/", "scripts/")
        assert r.returncode == 0, (
            "the CI-enforced surface (src/ tests/ scripts/) must stay"
            f" formatter-clean. Output:\n{r.stdout[-3000:]}{r.stderr[-1000:]}"
        )

    def test_freeze_is_scoped_to_frozen_md_only(self) -> None:
        text = _repo_relative(PYPROJECT_TOML)
        block = text[text.index("[tool.ruff]") : text.index("[tool.ruff.lint.mccabe]")]
        assert 'extend-exclude = ["docs/audit-history/*.md"' in block, (
            "pyproject [tool.ruff] extend-exclude must freeze the evidence"
            " trees at the *.md layer (first glob missing)"
        )
        assert '"reports/ai-generated/*.md"]' in block, (
            "pyproject [tool.ruff] extend-exclude must freeze the evidence"
            " trees at the *.md layer (second glob missing)"
        )
        # Directory-level freezes would amnesty the tracked *.py evidence
        # scripts too; the md-layer scoping is the contract.
        for line in block.splitlines():
            stripped = line.split("#")[0].strip().rstrip(",")
            assert stripped not in {f'"{d}"' for d in FROZEN_DIRS}, (
                f"directory-level exclusion '{stripped}' would also ungate"
                " tracked *.py under the evidence trees"
            )
            assert "**" not in stripped or stripped.startswith("#"), (
                f"recursive glob '{stripped}' in extend-exclude outruns the"
                " md-layer freeze contract"
            )

    def test_frozen_files_skipped_by_sweep_but_formattable_explicitly(self) -> None:
        frozen_dir = REPO_ROOT / "docs" / "audit-history"
        probe = frozen_dir / f"zz_format_contract_probe_{id(object()):x}.md"
        probe.write_text(UNFORMATTED_FENCE, encoding="utf-8")
        try:
            sweep = _ruff_format_check(".")
            assert sweep.returncode == 0, (
                "an unformatted fence inside docs/audit-history/ leaked into"
                f" the root sweep:\n{sweep.stdout[-2000:]}"
            )
            assert probe.name not in sweep.stdout, (
                "frozen-evidence md appeared in root sweep output; the"
                " extend-exclude freeze regressed"
            )
            # Explicit paths bypass excludes by design: the file must be
            # flagged (--check rc 1), proving deliberate reconciliation of
            # the frozen corpus stays possible.
            explicit = _ruff_format_check(probe.relative_to(REPO_ROOT).as_posix())
            assert explicit.returncode == 1, (
                "explicitly-passed frozen md was not format-checked; ruff"
                " exclude semantics changed -- re-validate the reconciliation"
                " escape hatch"
            )
            assert probe.name in explicit.stdout
        finally:
            _unlink_robust(probe)
        assert not probe.exists(), "probe file leaked into the frozen tree"

    def test_nonfrozen_markdown_fences_remain_gated(self) -> None:
        for rel in GATED_MD:
            assert (REPO_ROOT / rel).exists(), f"expected gated md missing: {rel}"
            r = _ruff_format_check(rel)
            assert r.returncode == 0, (
                f"live markdown {rel} is not formatter-canonical. Output:\n"
                f"{r.stdout[-2000:]}"
            )
        # The gate must still CATCH md drift outside the freeze: an
        # unformatted fence in a non-frozen md path is flagged by the sweep.
        probe = REPO_ROOT / "docs" / f"zz_format_contract_probe_{id(object()):x}.md"
        probe.write_text(UNFORMATTED_FENCE, encoding="utf-8")
        try:
            sweep = _ruff_format_check(".")
            assert sweep.returncode == 1, (
                "root sweep passed despite an unformatted fence in a"
                " NON-frozen md file -- the freeze has gone over-broad"
            )
            assert probe.name in sweep.stdout
        finally:
            _unlink_robust(probe)
        assert not probe.exists(), "probe file leaked into docs/"

    def test_var_engine_doc_is_formatter_canonical(self) -> None:
        r = _ruff_format_check("docs/var_engine.md")
        assert r.returncode == 0, (
            "docs/var_engine.md drifted from the pinned formatter. Run:"
            " ruff format docs/var_engine.md. Output:\n"
            f"{r.stdout[-2000:]}"
        )

    def test_ci_ruff_job_scopes_unchanged(self) -> None:
        ci = _repo_relative(CI_YML)
        assert "ruff check src/ tests/ scripts/" in ci, (
            "ci.yml scoped lint job missing; CI scope is part of this"
            " contract and may not be narrowed silently"
        )
        assert "ruff check . " in ci or "ruff check ." in ci, (
            "ci.yml root-scope lint job missing; the freeze rationale"
            " assumes a root-scope sweep exists and stays green"
        )
        assert "ruff format --check src/ tests/ scripts/" in ci, (
            "ci.yml format job scope missing"
        )

    def test_freeze_globs_cover_every_frozen_md(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "docs/audit-history", "reports/ai-generated"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.splitlines()
        frozen_md = [f for f in tracked if f.endswith(".md")]
        assert len(frozen_md) >= 100, (
            f"frozen md corpus unexpectedly small ({len(frozen_md)});"
            " evidence trees moved? re-validate this contract"
        )
        for rel in frozen_md:
            covered = any(
                rel.startswith(d + "/")
                and rel.endswith(".md")
                and "/" not in rel[len(d) + 1 : -3]
                for d in FROZEN_DIRS
            )
            assert covered, (
                f"tracked md '{rel}' under an evidence tree is NOT covered by"
                " the extend-exclude globs (nested depth?); extend the freeze"
                " deliberately before the root sweep flags it"
            )


class TestAdvisoryWaiverSurfaceLockstep:
    """The ADR-0010 nltk waiver must be present on every pip-audit surface.

    Live-verified failure mode (2026-09-09): the pre-push pip-audit hook
    ran without the waiver and exited 1 on exactly PYSEC-2026-3740 while
    CI -- carrying the same waiver -- stayed green. Every pre-push in the
    repo died at the audit step; nothing wired detected the mismatch.
    """

    def test_precommit_pip_audit_hook_carries_waiver(self) -> None:
        text = _repo_relative(PRECOMMIT_YML)
        assert f"--ignore-vuln {WAIVED_VULN_ID}" in text, (
            "pre-commit pip-audit hook lost the ADR-0010 waiver; pre-push"
            f" fails closed on {WAIVED_VULN_ID} while CI stays green"
        )

    def test_ci_carries_the_same_waiver(self) -> None:
        for yml in (CI_YML, SECURITY_YML):
            assert f"--ignore-vuln {WAIVED_VULN_ID}" in _repo_relative(yml), (
                f"{yml.name} lost the ADR-0010 waiver; CI and pre-push audit"
                " surfaces must agree"
            )

    def test_waiver_has_a_recorded_triage_adr(self) -> None:
        assert ADR_0010.exists(), (
            "the waived advisory's triage ADR is missing; re-instate"
            " docs/adr/0010-nltk-dev-toolchain-triage.md or re-triage the"
            " advisory before waiving it on any surface"
        )
        assert WAIVED_VULN_ID in ADR_0010.read_text(encoding="utf-8"), (
            "ADR-0010 no longer names the waived advisory id"
        )

    def test_triage_adr_agrees_with_enforced_surfaces(self) -> None:
        """The ADR's decision text must not contradict the surfaces.

        Drift class pinned here (2026-09-09): ADR-0010 originally
        decided CI/security.yml stay waiver-free, then ci.yml gained
        the flag (surface lockstep) and the ADR text was never amended
        -- docs claimed one contract, gates enforced another, and
        nothing detected it. If the waiver is enforced on CI surfaces
        (test_ci_carries_the_same_waiver), the ADR must not claim the
        opposite; re-triage and re-amend together or not at all.
        """
        assert f"--ignore-vuln {WAIVED_VULN_ID}" in _repo_relative(CI_YML), (
            "precondition drifted: ci.yml no longer carries the waiver;"
            " this test pins ADR/surface AGREEMENT, re-scope both"
        )
        adr_text = ADR_0010.read_text(encoding="utf-8")
        assert "left WITHOUT the ignore" not in adr_text, (
            "ADR-0010 decision text claims the CI surfaces are"
            " waiver-free while ci.yml enforces the waiver; amend the"
            " ADR to the surface-lockstep decision instead of"
            " reintroducing the contradiction"
        )

    @staticmethod
    def _installed_version(distribution: str) -> str | None:
        try:
            return version(distribution)
        except PackageNotFoundError:
            return None

    def test_waiver_still_matches_installed_toolchain(self) -> None:
        """The waived advisory must still be live where it can fire.

        Root cause being guarded: an --ignore-vuln flag is invisible
        when it waives nothing -- if nltk is upgraded past the
        vulnerable range, or safety drops the nltk dependency, every
        surface keeps passing a flag that no longer maps to any
        advisory and nothing would ever prompt its removal (ADR-0010
        documents the removal triggers; until this test nothing
        enforced them). The local full environment (safety -> nltk) is
        the one surface where the advisory can actually fire, so its
        installed versions decide currency.
        """
        nltk_version = self._installed_version("nltk")
        assert nltk_version is not None, (
            "nltk is not installed in this environment, so"
            f" {WAIVED_VULN_ID} can no longer fire: the waiver on all"
            " surfaces is dead weight -- remove it everywhere (ADR-0010"
            " removal trigger: safety drops nltk) and delete this test"
            " with it"
        )
        major_minor = tuple(int(part) for part in nltk_version.split(".")[:2])
        assert major_minor < (3, 11), (
            f"nltk {nltk_version} is past the vulnerable range (<3.11);"
            f" {WAIVED_VULN_ID} is fixed -- remove the --ignore-vuln"
            " waiver from the pre-push hook, ci.yml, security.yml and"
            " HC-11 in one sweep, then retire this test (ADR-0010"
            " removal trigger: nltk 3.11 published)"
        )
