"""Tests for the F8-C-02 repository hygiene guard.

Covers scripts/check_repo_hygiene.py: pattern matching semantics, the
tracked-file ceiling, the allowlist, and live repository invariants
(tracked set is clean, guard exits 0 on the real tree).

F8-M-03 additions: outcome-scoped verification of the shared Win32-safe
root junk detector (scripts/win32_root_junk.py), the HC-15 production
emission mutation net, and the HC-21 bare-env behavioral contract.

F8-M-05 additions: compact-repo rules for evidence reports — completion
reports live only under docs/audit-history/, never at the docs/ top
level, and reports/health/ tracks only curated health-final-*.json.

F8-L-04-R2 additions: lint version lockstep — every gate tool (ruff,
mypy, isort, flake8, bandit, pip-audit) must be the single pinned value
across pyproject dev-deps, CI installs, and the pre-commit config, so
no gate surface drifts onto a different rule set than the one the tree
was verified against.

Workflow flag currency (2026-09-06): the pinned tool versions must
actually accept every flag the committed CI/security workflow steps
pass. fa75e8b repaired safety's v2->3 flag removal after
security.yml broke; the identical drift class then surfaced for mypy
(--output-format, removed in mypy 2.x) and pip-audit (--output-file,
removed in pip-audit 2.x) — committed jobs that fail the moment they
run. These tests extract each tool's flags from the workflow steps and
validate them against the installed pinned tool's own CLI parser.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "check_repo_hygiene.py"
HELPER_PATH = REPO_ROOT / "scripts" / "win32_root_junk.py"
HC15_PROBE = REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRECOMMIT_YML = REPO_ROOT / ".pre-commit-config.yaml"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"

IS_WINDOWS = sys.platform == "win32"


def _repo_relative(p: Path) -> str:
    """Config-file text with forward slashes and CRLF stripped (POSIX+Windows)."""
    return p.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\\", "/")


@pytest.mark.skipif(not CI_YML.exists(), reason="CI workflow absent")
class TestLintVersionLockstep:
    """Gate-tool versions must be single pinned values across all surfaces.

    A version drift between pyproject dev-deps, the CI installs, and the
    pre-commit config means a gate can pass on one surface and fail on
    another with zero source changes. These tests assert agreement, not
    specific versions, so deliberate upgrades stay green. bandit and
    pip-audit run in pre-commit via language:system local hooks, so their
    pre-commit surface is the project venv itself (covered by the
    pyproject pins); isort has no pre-commit surface (CI-only); mypy rides
    `.[dev]` in CI, so no bare-install assertion applies to it there.
    """

    GATE_TOOLS = ("ruff", "mypy", "isort", "flake8", "bandit", "pip-audit")

    def test_pyproject_pins_all_gate_tools(self) -> None:
        text = _repo_relative(PYPROJECT_TOML)
        for tool in self.GATE_TOOLS:
            spec = f'"{tool}=='
            pins = [ln for ln in text.splitlines() if ln.strip().startswith(spec)]
            assert len(pins) == 1, f"{tool}: expected exactly one pin, got {pins}"
            assert not fnmatch.fnmatch(text, f'*"{tool}>=*'), (
                f"{tool} dev-dep must be pinned (==), not lower-bounded (>=)"
            )

    def test_ci_installs_are_pinned(self) -> None:
        text = _repo_relative(CI_YML)
        for tool in self.GATE_TOOLS:
            bare = re.compile(rf"^\s*pip install {re.escape(tool)}\s*$", re.M)
            assert not bare.search(text), (
                f"unpinned 'pip install {tool}' remains in ci.yml"
            )
        # The three ruff jobs each pin explicitly (ruff gates the repo-root
        # scope, so this count is the frozen-dir contract's install spine).
        assert text.count('pip install "ruff==') >= 1, (
            'CI must install ruff via a pinned spec like pip install "ruff==X.Y.Z"'
        )

    def test_precommit_revs_match_pyproject_pins(self) -> None:
        pins: dict[str, str] = {}
        for ln in PYPROJECT_TOML.read_text(encoding="utf-8").splitlines():
            stripped = ln.strip()
            for tool in self.GATE_TOOLS:
                spec = f'"{tool}=='
                if stripped.startswith(spec):
                    pins[tool] = stripped[len(spec) :].strip().rstrip('",').strip()
        assert set(pins) == set(self.GATE_TOOLS), f"unreadable pins: {pins}"
        text = _repo_relative(PRECOMMIT_YML)
        assert f"rev: v{pins['ruff']}" in text, "ruff-pre-commit rev != pyproject pin"
        assert f"rev: {pins['flake8']}" in text, "flake8 hook rev != pyproject pin"
        # mypy, bandit and pip-audit run as language:system local hooks,
        # so their pre-commit surface IS the venv pinned by pyproject.
        entries = {ln.strip() for ln in text.splitlines()}
        assert "entry: python -m mypy" in entries, (
            "mypy local hook (language: system) missing from pre-commit config"
        )


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

    def test_report_run_artifacts_matched(self, guard):
        """F8-M-05/ADR-0011: verifier run artifacts never live in reports/.

        Root cause being guarded: the hygiene guard had no reports/
        rule, so machine-local verifier output (git status, absolute
        paths) was trackable at the reports/ top level even though the
        documented curation rule names only health-final-*.json for
        reports/health/. Curated subdirectory evidence (reports/security/
        dated snapshots, reports/p1_analyze_latency_*) stays legitimate.
        """
        for path in (
            "reports/f8-h-03-verification.json",
            "reports/some_verifier_output.json",
            "reports/production-verification-unlisted.json",
        ):
            assert guard._violations([path]), f"expected {path} to be flagged"

    def test_cited_root_level_evidence_allowlisted(self, guard):
        """Root-level reports/*.json with tracked consumers stay legitimate.

        The allowlist entries each name their consumer; the wiring guard
        fails when a citation goes dead (F8-L-06-R2), so a stale entry
        cannot silently persist.
        """
        for path in (
            "reports/p1_analyze_latency_20260904_040609.json",
            "reports/production-verification.json",
            "reports/todo27_eval.json",
            "reports/todo27_external.json",
            "reports/verify_f8h01_external.json",
        ):
            assert guard._violations([path]) == [], f"unexpected flag on {path}"

    def test_curated_subdir_evidence_clean(self, guard):
        """Nested evidence of record must NOT be flagged (single-segment rule)."""
        for path in (
            "reports/health/health-final-20260901.json",
            "reports/security/bandit-20260901.json",
            "reports/p1_analyze_latency_20260904_040609.json",
        ):
            assert guard._violations([path]) == [], f"unexpected flag on {path}"

    def test_nested_health_paths_out_of_guard_scope(self, guard):
        """Nested reports/health/* is TestCompactRepoDocs' contract, not the guard's.

        The guard's artifact rule is deliberately single-segment (top-level
        reports/*.json only); asserting nested paths here would demand
        fnmatch-crossing semantics that false-positive the curated
        evidence subdirectories.
        """
        assert guard._violations(["reports/health/health-full-20260906.json"]) == []

    def test_legitimate_paths_clean(self, guard):
        for path in (
            "src/loats/main.py",
            "tests/test_repo_hygiene.py",
            "scripts/check_repo_hygiene.py",
            "docs/x.md",
            "reports/health/health-final-20260901.json",
            "reports/p1_analyze_latency_20260904_040609.json",
            ".github/workflows/ci.yml",
        ):
            assert guard._violations([path]) == [], f"unexpected flag on {path}"

    def test_no_false_positive_on_env_prefixed_dirs(self, guard):
        # "ENV/*" must not catch unrelated top-level docs paths
        assert guard._violations(["environment.md"]) == []


class TestRatchetSingleSource:
    """F8-L-07: one canonical tracked-file ceiling, imported everywhere.

    The 416-vs-426 split class: four gate scripts hand-pinned the same
    integer; re-pinning one surface without the others left committed
    gates red on a clean tree. scripts/ratchet_baseline.py now owns
    TRACKED_FILE_CEILING and every ratchet surface imports it, so
    lockstep is structural rather than procedural.
    """

    CANONICAL_PATH = REPO_ROOT / "scripts" / "ratchet_baseline.py"

    @pytest.fixture()
    def canonical(self):
        spec = importlib.util.spec_from_file_location(
            "ratchet_single_source_canonical", self.CANONICAL_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_canonical_module_exists_and_pins_one_value(self, canonical, guard):
        assert canonical.TRACKED_FILE_CEILING == guard.TRACKED_FILE_CEILING
        assert 350 <= canonical.TRACKED_FILE_CEILING <= 510

    def test_hygiene_guard_imports_canonical(self):
        src = (REPO_ROOT / "scripts" / "check_repo_hygiene.py").read_text(
            encoding="utf-8"
        )
        assert "ratchet_baseline" in src, (
            "hygiene guard must take the ceiling from scripts/"
            "ratchet_baseline.py (F8-L-07)"
        )
        assert not re.search(r"TRACKED_FILE_CEILING\s*=\s*\d+", src), (
            "hygiene guard must not re-pin the ceiling with a local literal"
        )


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


class TestCompactRepoDocs:
    """F8-M-05: evidence reports are archived, never left at docs/ top level.

    Completion/fix/verification reports produced per work item belong in
    docs/audit-history/ (CMP §4/§8). The docs/ top level is a curated
    set of living documentation; reports/health/ tracks only the
    curated health-final-*.json finals.
    """

    EVIDENCE_NAME = re.compile(
        r"^(TODO|FR7|MCP_FIX|MYPY|PERFORMANCE_REVIEW|PRODUCTION_READINESS"
        r"|RISK_MATRIX|TECHNICAL_DEBT|THREAD_SAFETY)|_REPORT",
        re.IGNORECASE,
    )

    def _tracked(self) -> list[str]:
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        return out.stdout.splitlines()

    def test_no_evidence_reports_at_docs_top_level(self):
        strays = [
            p
            for p in self._tracked()
            if p.startswith("docs/")
            and p.count("/") == 1
            and self.EVIDENCE_NAME.search(Path(p).name)
        ]
        assert strays == [], (
            "evidence reports must be archived under docs/audit-history/ "
            f"(F8-M-05), found at docs/ top level: {strays}"
        )

    def test_completion_reports_are_archived(self):
        archived = [
            p for p in self._tracked() if p.startswith("docs/audit-history/TODO")
        ]
        assert len(archived) >= 10, (
            "expected the F8-M-05 archived completion reports under "
            f"docs/audit-history/, found only {len(archived)}"
        )

    def test_health_snapshots_curated(self):
        tracked = sorted(p for p in self._tracked() if p.startswith("reports/health/"))
        assert all(p.startswith("reports/health/health-final-") for p in tracked), (
            f"non-curated health snapshots tracked: {tracked}"
        )

    def test_todo26_verifier_reads_archived_report(self):
        src = (REPO_ROOT / "scripts" / "final_verify_todo26.py").read_text(
            encoding="utf-8"
        )
        assert "audit-history" in src, (
            "final_verify_todo26 must read TODO26_FINAL_REPORT.md from "
            "docs/audit-history/ (F8-M-05 relocation)"
        )


class TestSrcAsciiGate:
    """F8-M-06: scripts/check_src_ascii.py must propagate its verdict.

    The historical defect: __main__ called check_ascii_files() and
    discarded the bool, so the process exited 0 even when violations
    were found. The scan may legitimately report violations (the src
    tree currently contains non-ASCII emoji in alert message payloads
    and typographic punctuation in docstrings), so only the exit-code
    propagation is gated here, both directions, via live-tree runs.
    """

    SCRIPT = REPO_ROOT / "scripts" / "check_src_ascii.py"

    def _run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.SCRIPT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_exit_code_matches_reported_state(self):
        proc = self._run()
        found = "non-ASCII" in proc.stdout and "Found" in proc.stdout
        clean = "only ASCII" in proc.stdout
        assert found != clean, f"unparsable gate output: {proc.stdout!r}"
        if clean:
            assert proc.returncode == 0, proc.stdout
        else:
            assert proc.returncode == 1, (
                f"violations reported but exit code {proc.returncode} "
                f"(discarded-result regression): {proc.stdout[:300]}"
            )

    def test_ascii_source_addition_flips_exit_code(self):
        probe = REPO_ROOT / "src" / "loats" / "_tmp_ascii_gate_probe.py"
        try:
            probe.write_text("# non-ascii mutation ✓\n", encoding="utf-8")
            proc = self._run()
        finally:
            probe.unlink(missing_ok=True)
        assert proc.returncode == 1, (
            f"non-ASCII source file must fail the gate, got rc={proc.returncode}"
        )
        assert "_tmp_ascii_gate_probe" in proc.stdout

    def test_gate_runs_without_stderr(self):
        # Ordering-independent follow-up to the flip test: after the
        # probe file is removed the gate must run cleanly (no tracebacks
        # on stderr) and propagate its verdict either way.
        proc = self._run()
        assert proc.returncode in (0, 1)
        assert proc.stderr == "", proc.stderr


def _load_helper():
    spec = importlib.util.spec_from_file_location("win32_root_junk", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestWin32RootJunkDetector:
    """F8-M-03: outcome-scoped tests for the shared HC-26 detector."""

    @pytest.fixture()
    def helper(self):
        return _load_helper()

    @pytest.fixture()
    def root(self, tmp_path):
        return tmp_path

    def test_clean_root_passes(self, helper, root):
        assert helper.forbidden_root_junk(root) == []

    def test_plain_name_detected(self, helper, root):
        (root / "tmp_schema.db").write_text("x", encoding="utf-8")
        assert helper.forbidden_root_junk(root) == ["tmp_schema.db"]

    def test_lockstep_with_guard_names(self, helper, guard):
        # The guard imports the shared detector module (F8-M-03 single
        # source of truth); pin the references against drift.
        # (Value equality, not identity: importlib spec-loading creates a
        # second module object, so tuple identity would be meaningless.)
        assert helper.ROOT_JUNK_NAMES == guard.win32_root_junk.ROOT_JUNK_NAMES

    def test_fails_closed_on_unenumerable_root(self, helper):
        missing_root = (
            "C:\\definitely\\not\\a\\dir\\xyz"
            if IS_WINDOWS
            else "/definitely/not/a/dir/xyz"
        )
        with pytest.raises(RuntimeError, match="cannot enumerate"):
            helper.forbidden_root_junk(missing_root)

    @pytest.mark.skipif(not IS_WINDOWS, reason="Win32 dot-stripping semantics")
    def test_trailing_dot_name_invisible_to_exists_is_detected(self, helper, root):
        """The F8-M-03 false-green: real on-disk trailing-dot artifact.

        Exists-probing misses it (Win32 strips trailing dots before
        stat); os.listdir membership sees the on-disk name verbatim.
        The check must FAIL while the artifact is present.
        """
        name = "G......"
        extended = f"\\\\?\\{root}{os.sep}{name}"
        fd = os.open(extended, os.O_CREAT | os.O_WRONLY, 0o644)
        os.write(fd, b"junk")
        os.close(fd)
        # Precondition (Windows behavior, not our code): exists is blind.
        assert not (root / name).exists()
        # The detector must NOT share that blind spot.
        assert helper.forbidden_root_junk(root) == [name]

    @pytest.mark.skipif(not IS_WINDOWS, reason="Win32 phantom-creation semantics")
    def test_phantom_dot_stripped_sibling_not_flagged(self, helper, root):
        """os.open('G......') creates 'G' on Win32 (kernel strips dots).

        The old union (listdir OR exists) flagged the literal name by
        aliasing onto the phantom sibling. listdir membership must not.
        """
        fd = os.open(str(root / "G......"), os.O_CREAT | os.O_WRONLY, 0o644)
        os.write(fd, b"x")
        os.close(fd)
        on_disk = [entry.name for entry in os.scandir(root)]
        assert on_disk == ["G"], f"precondition: phantom sibling, got {on_disk}"
        assert helper.forbidden_root_junk(root) == []

    def test_case_insensitive_detection_windows_only(self, helper, root):
        (root / "TMP_SCHEMA.DB").write_text("x", encoding="utf-8")
        detected = helper.forbidden_root_junk(root)
        if IS_WINDOWS:
            assert detected == ["tmp_schema.db"]
        else:
            assert detected == []

    def test_directory_of_same_name_detected(self, helper, root):
        # listdir membership covers dirs and files alike.
        (root / "0.21.0").mkdir()
        assert helper.forbidden_root_junk(root) == ["0.21.0"]

    # ---- F8-M-04: class-wide Win32-hostile name detection ----

    def test_hostile_classification_unit(self, helper):
        """Pure-name classification: hostile classes vs legit names."""
        # Hostile: trailing dots/spaces (the F8-M-04 artifact class).
        for hostile in ("G......", "out.txt.", "x ", "weird.."):
            assert helper.is_hostile_root_name(hostile) is True, hostile
        # Hostile: reserved device names, optionally dot-extensioned.
        for hostile in ("NUL", "NUL.txt", "COM1", "com4.zip", "LPT9"):
            assert helper.is_hostile_root_name(hostile) is True, hostile
        # Hostile: colon (NT stream separator).
        assert helper.is_hostile_root_name("stream:ads") is True
        # Legitimate repo-root names must NOT be flagged.
        for legit in (
            "src",
            "tests",
            "pyproject.toml",
            "README.md",
            "docker-compose.prod.yml",
            ".env.example",
            "verify_acceptance_matrix.log",
            ".gitignore",
        ):
            assert helper.is_hostile_root_name(legit) is False, legit

    def test_findings_fail_closed_on_unenumerable_root(self, helper):
        missing_root = (
            "C:\\definitely\\not\\a\\dir\\xyz"
            if IS_WINDOWS
            else "/definitely/not/a/dir/xyz"
        )
        with pytest.raises(RuntimeError, match="cannot enumerate"):
            helper.root_junk_findings(missing_root)

    def test_future_mishap_detected_class_wide(self, helper, root):
        """A NEW trailing-dot artifact (not in ROOT_JUNK_NAMES) must fail
        the union entry point -- the F8-M-04 regression class."""
        name = "weird.."
        if IS_WINDOWS:
            # Ordinary Win32 create strips trailing dots; only the
            # NT-extended namespace materializes the verbatim name.
            extended = f"\\\\?\\{root}{os.sep}{name}"
            fd = os.open(extended, os.O_CREAT | os.O_WRONLY, 0o644)
        else:
            fd = os.open(str(root / name), os.O_CREAT | os.O_WRONLY, 0o644)
        os.write(fd, b"x")
        os.close(fd)
        on_disk = {entry.name for entry in os.scandir(root)}
        assert name in on_disk, f"precondition: verbatim name, got {on_disk}"
        assert helper.root_junk_findings(root) == [name]

    @pytest.mark.skipif(not IS_WINDOWS, reason="Win32 phantom-creation semantics")
    def test_phantom_sibling_not_flagged_class_wide(self, helper, root):
        """os.open('weird..') creates 'weird' on Win32 (dots stripped).

        The class-wide scan must NOT flag the dot-stripped sibling --
        same soundness contract as the pinned-name scan (F8-M-03).
        """
        fd = os.open(str(root / "weird.."), os.O_CREAT | os.O_WRONLY, 0o644)
        os.write(fd, b"x")
        os.close(fd)
        on_disk = [entry.name for entry in os.scandir(root)]
        assert on_disk == ["weird"], f"precondition: phantom sibling, got {on_disk}"
        assert helper.hostile_root_names(root) == []

    def test_colon_and_reserved_names_detected(self, helper, root):
        """Colon / reserved-device names: classification on Win32 (the
        legacy namespace cannot create them there), on-disk detection on
        POSIX -- where a Windows-hostile name committed from a POSIX
        mishap materializes verbatim and must fail CI's ubuntu job."""
        if IS_WINDOWS:
            assert helper.is_hostile_root_name("bad:name") is True
            assert helper.is_hostile_root_name("NUL.txt") is True
            return
        (root / "bad:name").write_text("x", encoding="utf-8")
        (root / "NUL.txt").write_text("x", encoding="utf-8")
        assert helper.hostile_root_names(root) == ["NUL.txt", "bad:name"]

    @pytest.mark.skipif(not IS_WINDOWS, reason="Win32 dot-stripping semantics")
    def test_union_dedupes_pinned_and_hostile(self, helper, root):
        """'G......' matches BOTH the pinned list and the hostile class;
        the union entry point must report it exactly once."""
        name = "G......"
        extended = f"\\\\?\\{root}{os.sep}{name}"
        fd = os.open(extended, os.O_CREAT | os.O_WRONLY, 0o644)
        os.write(fd, b"junk")
        os.close(fd)
        assert name in helper.forbidden_root_junk(root)  # pinned path
        assert name in helper.hostile_root_names(root)  # class-wide path
        assert helper.root_junk_findings(root) == [name]  # deduped union

    def test_guard_root_junk_uses_class_wide_scan(self, guard, tmp_path, monkeypatch):
        """Wire-level proof: the guard's _root_junk must surface a
        Win32-hostile name that is NOT in ROOT_JUNK_NAMES (F8-M-04)."""
        name = "weird.."
        if IS_WINDOWS:
            extended = f"\\\\?\\{tmp_path}{os.sep}{name}"
            fd = os.open(extended, os.O_CREAT | os.O_WRONLY, 0o644)
        else:
            fd = os.open(str(tmp_path / name), os.O_CREAT | os.O_WRONLY, 0o644)
        os.close(fd)
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard._root_junk() == [name]


class TestHC15MutationNet:
    """F8-M-03 test (2): deleting a producer emission site must fail HC-15.

    The live-tree HC-15 emission result (fr7_health_check + HC registry)
    verifies the PASS direction on every run; here we prove the FAIL
    direction end-to-end: a mutated orchestrator snapshot must make the
    standalone probe exit non-zero (mirrors verify_f8c01_external
    check_7 but runs the repo probe unmodified).
    """

    def test_probe_passes_on_real_tree(self):
        proc = subprocess.run(
            [sys.executable, str(HC15_PROBE)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_emission_site_deletion_fails_probe(self, tmp_path):
        orch = REPO_ROOT / "src" / "loats" / "orchestrator.py"
        text = orch.read_text(encoding="utf-8")
        anchor = '"source": StrengthSource.PRICE_ACTION.value,'
        assert anchor in text, "mutation anchor missing from orchestrator.py"
        mutated = text.replace(anchor, '"source": "mutated_out",')
        assert mutated != text

        tree = tmp_path / "snap"
        (tree / "scripts").mkdir(parents=True)
        # The probe imports loats.* (editable install resolves to the real
        # src tree) and reads src/loats/orchestrator.py relative to ITS OWN
        # location: parents[1]/src/loats/orchestrator.py. Reconstruct that
        # layout in the snapshot with ONLY orchestrator.py mutated.
        (tree / "src" / "loats").mkdir(parents=True)
        (tree / "src" / "loats" / "orchestrator.py").write_text(
            mutated, encoding="utf-8"
        )
        shutil.copy2(HC15_PROBE, tree / "scripts" / HC15_PROBE.name)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, str(tree / "scripts" / HC15_PROBE.name)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert proc.returncode != 0, (
            "HC-15 probe PASSED on producer-deleted snapshot - the "
            "production emission check is not outcome-scoped"
        )
        assert "missing emission sites" in proc.stdout or "FAIL" in proc.stdout


class TestHC21BareEnvBehavior:
    """F8-M-03 test (3): behavioral bare-env import probe.

    HC-21's outcome is "no loats module builds Settings at import in a
    bare environment (no OPENALGO_API_KEY)". That is verified
    behaviorally: import every anchor module with the variable unset
    and assert the process exits 0.
    """

    def test_bare_env_import_of_anchor_modules(self, tmp_path):
        probe = tmp_path / "bare_env_probe.py"
        probe.write_text(
            "import importlib, os, sys\n"
            "assert 'OPENALGO_API_KEY' not in os.environ, 'env leak'\n"
            "mods = [\n"
            "    'loats.alerts', 'loats.backtest_sanity', 'loats.main',\n"
            "    'loats.rules', 'loats.scheduler', 'loats.sentiment',\n"
            "    'loats.sizing', 'loats.strength', 'loats.trade_decision',\n"
            "    'loats.trailing_stop',\n"
            "]\n"
            "for m in mods:\n"
            "    importlib.import_module(m)\n"
            "print('BARE-ENV IMPORT OK')\n",
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "OPENALGO_API_KEY"}
        env["PYTHONIOENCODING"] = "utf-8"
        # cwd = tmp_path so the repo-root .env is NOT auto-loaded; the
        # venv's editable install makes `import loats` resolve to src/.
        proc = subprocess.run(
            [sys.executable, str(probe)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"bare-env import failed (HC-21 outcome violated):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
        assert "BARE-ENV IMPORT OK" in proc.stdout


@pytest.mark.skipif(not CI_YML.exists(), reason="CI workflow absent")
class TestWorkflowFlagCurrency:
    """Every flag a committed workflow passes must exist in the pinned tool.

    Root cause being guarded: gate tools drop/rename CLI flags across
    major versions (safety v2->v3 removed --json/--output-file; mypy 2.x
    has no --output-format; pip-audit 2.x renamed --output-file to
    --output). A workflow step written against the old flag then fails
    the moment it runs, on a tree where every local gate is green. The
    check is self-maintaining: extract the flags the workflow actually
    passes and ask the installed pinned tool's CLI parser whether they
    exist — no flag vocabulary is duplicated here.
    """

    SECURITY_YML = REPO_ROOT / ".github" / "workflows" / "security.yml"

    # step command line -> interpreter that knows the tool's flags
    FLAG_CHECKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        (
            "ci.yml mypy step",
            "mypy",
            ("src/", "--strict", "--config-file", "pyproject.toml"),
        ),
        (
            "ci.yml pip-audit step",
            "pip_audit",
            ("--format=json", "--output", "pip-audit-report.json"),
        ),
        (
            "security.yml pip-audit json step",
            "pip_audit",
            ("--format=json", "--output", "pip-audit-full.json"),
        ),
        (
            "security.yml pip-audit requirements step",
            "pip_audit",
            ("--format=requirements", "--output", "requirements-vulnerable.txt"),
        ),
    )

    @staticmethod
    def _workflow_run_lines(path: Path) -> list[str]:
        """All non-comment ``run:`` command lines of a workflow file."""
        return [
            stripped
            for ln in path.read_text(encoding="utf-8").splitlines()
            if (stripped := ln.strip())
            and not stripped.startswith("#")
            and not stripped.startswith("- ")
        ]

    @staticmethod
    def _pip_audit_help() -> str:
        """The pinned pip-audit's own CLI help text (format choices included)."""
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--help"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"pip_audit --help failed (rc={proc.returncode}): {proc.stderr[:300]}"
        )
        return proc.stdout + proc.stderr

    def test_security_yml_pip_audit_format_choices_are_valid(self) -> None:
        """--format=<choice> values must exist in the tool's own choice list.

        Root cause being guarded: flag NAMES can be valid while the VALUE
        is not — `--format=requirements` passed test_flags_accepted_by_
        installed_tool for weeks, yet pip-audit's format choices are
        columns/json/cyclonedx-json/cyclonedx-xml/markdown (no
        `requirements`), so the step would fail the moment it ran.
        """
        help_text = self._pip_audit_help()
        lines = self._workflow_run_lines(self.SECURITY_YML)
        pip_audit_lines = [ln for ln in lines if ln.startswith("pip-audit ")]
        for ln in pip_audit_lines:
            for token in ln.split():
                if token.startswith("--format="):
                    value = token.split("=", 1)[1]
                    assert f"{{{value}" in help_text or f"{value}," in help_text, (
                        f"security.yml passes --format={value}, which the "
                        f"installed pip-audit does not offer as a choice: {ln}"
                    )

    def test_security_yml_has_no_deprecated_gitleaks_v2(self) -> None:
        """gitleaks-action@v2 dies with the Node 20 runner removal.

        GitHub removes Node 20 from hosted runners on 2026-09-16; @v2 is
        Node 20 and has no opt-out after that date. @v3 is the Node-24
        release with unchanged inputs/behavior.
        """
        text = self.SECURITY_YML.read_text(encoding="utf-8")
        assert "gitleaks-action@v2" not in text, (
            "security.yml pins gitleaks-action@v2 (Node 20) — removed from"
            " GitHub-hosted runners on 2026-09-16; use @v3"
        )

    def test_workflows_use_node24_native_action_majors(self) -> None:
        """Every pinned action major must run on Node 24.

        Node 20 is removed from GitHub-hosted runners on 2026-09-16, so
        Node-20 actions (checkout@v4, setup-python@v5, upload-artifact@v4)
        fail regardless of ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION.
        """
        for yml in (CI_YML, self.SECURITY_YML):
            text = yml.read_text(encoding="utf-8")
            for action in (
                "actions/checkout@v4",
                "actions/setup-python@v5",
                "actions/upload-artifact@v4",
            ):
                assert action not in text, (
                    f"{yml.name} pins {action} (Node 20 runtime), which"
                    " GitHub removes from hosted runners on 2026-09-16"
                )

    def test_security_yml_pip_audit_steps_use_current_flags(self) -> None:
        lines = self._workflow_run_lines(self.SECURITY_YML)
        pip_audit_lines = [ln for ln in lines if ln.startswith("pip-audit ")]
        assert len(pip_audit_lines) == 1, (
            f"expected exactly one pip-audit invocation in security.yml "
            f"(environment mode over the installed project closure; the "
            f"--format=requirements step was removed with the 2026-09-07 "
            f"integrity wave), got {pip_audit_lines}"
        )
        for ln in pip_audit_lines:
            assert "--output-file" not in ln, (
                f"security.yml uses removed flag --output-file: {ln}"
            )
            assert "--output" in ln, f"security.yml pip-audit missing --output: {ln}"

    def test_ci_yml_mypy_step_omits_removed_output_format_flag(self) -> None:
        lines = self._workflow_run_lines(CI_YML)
        mypy_lines = [ln for ln in lines if "mypy src/" in ln]
        assert len(mypy_lines) == 1, (
            f"expected exactly one mypy invocation in ci.yml, got {mypy_lines}"
        )
        assert "--output-format" not in mypy_lines[0], (
            f"ci.yml mypy step uses removed flag --output-format: {mypy_lines[0]}"
        )

    def test_ci_yml_gating_jobs_install_editable(self) -> None:
        """Both CI gating jobs must install the package EDITABLE.

        Root cause being guarded (2026-09-06 workflow_dispatch run): a
        non-editable ``pip install ".[dev]"`` made ``--cov=src`` measure
        site-packages never executed (coverage 0, fail-under=80 tripped)
        and broke ``src/loats/rss_validation.py``'s ``parents[2]`` repo
        anchor (recorded-sources manifest "missing" -- 26 CI-only test
        failures). Local editable venvs hid all of it. Editable installs
        are not optional parity polish; they are the load-bearing
        contract for coverage measurement and repo-relative fixtures.
        """
        text = CI_YML.read_text(encoding="utf-8")
        job_blocks = re.findall(
            r"^  (mypy|pytest-coverage):\n(?:^    .*\n)*?^      - name: Install dependencies\n"
            r"(?:^        [^\n]*\n)*?^          pip install ([^\n]+)\n",
            text,
            re.MULTILINE,
        )
        installs = dict(job_blocks)
        assert set(installs) == {"mypy", "pytest-coverage"}, (
            f"expected Install dependencies steps in mypy and pytest-coverage "
            f"jobs, found {sorted(installs)}"
        )
        for job, line in installs.items():
            assert line.strip().startswith('-e "'), (
                f"ci.yml {job} job must install editable (pip install -e), "
                f"got: pip install {line.strip()}"
            )

    @pytest.mark.parametrize(
        "label, module, flags",
        [(c[0], c[1], c[2]) for c in FLAG_CHECKS],
    )
    def test_flags_accepted_by_installed_tool(
        self, label: str, module: str, flags: tuple[str, ...]
    ) -> None:
        """Ask the installed pinned tool: does its CLI accept these flags?

        Runs ``python -m <module> --help`` (a complete, side-effect-free
        parse of the real argparse config) and requires every flag from
        the workflow step to appear in its option vocabulary. If the pin
        is upgraded and drops a flag the workflow still passes, this
        fails at test time instead of in a red CI job later.
        """
        proc = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"{module} --help failed (rc={proc.returncode}): {proc.stderr[:300]}"
        )
        help_text = proc.stdout + proc.stderr
        # Compare flag NAMES (--format=json -> --format): help text renders
        # value-taking options as "--format FORMAT", never inline-assigned.
        names = [f.split("=", 1)[0] for f in flags if f.startswith("-")]
        missing = [n for n in names if n not in help_text]
        assert not missing, (
            f"{label}: installed {module} does not accept {missing}; "
            f"the workflow step would fail. Upgrade the pin or fix the step."
        )


VERIFIER = REPO_ROOT / "scripts" / "verify_f8m02_m07_external.py"
VERIFIER_SNAPSHOT_ANCHOR = "await _settle_cancelled_producers(producers)"


class TestF8M02M07ExternalVerifier:
    """F8-M-02..07 closure net: the external verifier must stay honest.

    GREEN direction: exits 0 against the live tree from a clean process.
    RED direction: on a snapshot whose orchestrator dropped the producer
    settle call (the F8-M-02 fix), the verifier must FAIL — proving it
    asserts outcomes, not the presence of remediation idioms.
    """

    def test_verifier_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(VERIFIER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "VERIFIED: " in proc.stdout
        assert "[FAIL]" not in proc.stdout

    def test_verifier_fails_on_settle_removed_snapshot(self, tmp_path) -> None:
        orch = REPO_ROOT / "src" / "loats" / "orchestrator.py"
        text = orch.read_text(encoding="utf-8")
        assert VERIFIER_SNAPSHOT_ANCHOR in text, (
            "mutation anchor missing from orchestrator.py"
        )
        mutated = text.replace(
            VERIFIER_SNAPSHOT_ANCHOR, "pass  # verifier RED snapshot"
        )
        assert mutated != text

        snapshot = tmp_path / "snap"
        (snapshot / "scripts").mkdir(parents=True)
        for script in (REPO_ROOT / "scripts").glob("*.py"):
            shutil.copy2(script, snapshot / "scripts" / script.name)
        shutil.copytree(
            REPO_ROOT / "src" / "loats",
            snapshot / "src" / "loats",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        # Apply the mutation INSIDE the snapshot (never the live tree):
        # the F8-M-02 fix must be absent for the verifier to fire.
        snap_orch = snapshot / "src" / "loats" / "orchestrator.py"
        snap_orch.write_text(mutated, encoding="utf-8")
        (snapshot / "tests").mkdir()
        shutil.copy2(Path(__file__), snapshot / "tests" / Path(__file__).name)
        shutil.copy2(REPO_ROOT / ".env.example", snapshot / ".env.example")
        subprocess.run(
            ["git", "init", "-q"], cwd=snapshot, capture_output=True, timeout=60
        )
        subprocess.run(
            ["git", "add", "-A"], cwd=snapshot, capture_output=True, timeout=300
        )

        proc = subprocess.run(
            [sys.executable, str(snapshot / "scripts" / VERIFIER.name)],
            cwd=snapshot,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode != 0, (
            "verifier PASSED on a settle-removed snapshot — it does not "
            "verify the F8-M-02 outcome"
        )
        assert "m02c_settle_wired_on_both_boundaries" in proc.stdout
        assert "[FAIL] m02c_settle_wired_on_both_boundaries" in proc.stdout


class TestFlake8HookGateAgreement:
    """The pre-commit flake8 hook must agree with the lint scope of record.

    Defect class: the hook passes explicit filenames, and flake8 does not
    apply its own `exclude` to those — so the hook false-failed on the
    tree's own files (scripts/ verifiers' late sys.path-seeded imports =
    E402; frozen regex literals in tests/ = E501) even though ruff, the
    formatter/linter of record, deliberately grants those codes per-file
    (pyproject per-file-ignores). The same gate ran `flake8 src/` clean at
    every commit: the false positive class never surfaced in CI, only as
    a broken pre-commit hook. Root cause fixed by mirroring ruff's grants
    into .flake8 per-file-ignores; this net pins the agreement in both
    directions so a future grant divergence (either side) fails here.
    """

    def test_explicit_path_mode_agrees_with_ruff(self) -> None:
        # The exact false-positive class: HEAD's own tests/scripts files,
        # in the hook's explicit-filename mode.
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flake8",
                "--config",
                str(REPO_ROOT / ".flake8"),
                str(REPO_ROOT / "scripts" / "verify_f8m01_external.py"),
                str(REPO_ROOT / "scripts" / "verify_f8m02_m07_external.py"),
                str(REPO_ROOT / "tests" / "test_repo_hygiene.py"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"flake8 hook-mode false positive on the repo's own files: "
            f"{proc.stdout[:800]}"
        )

    def test_src_scope_stays_strict(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flake8",
                "--config",
                str(REPO_ROOT / ".flake8"),
                "src/",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"src/ no longer flake8-strict: {proc.stdout[:800]}"
        )

    def test_grant_sets_match_ruff(self) -> None:
        cfg = (REPO_ROOT / ".flake8").read_text(encoding="utf-8")
        m = re.search(
            r"per-file-ignores\s*=\s*\n\s*tests/\*:([A-Z0-9,]+)\s*\n\s*scripts/\*:([A-Z0-9,]+)",
            cfg,
        )
        assert m, ".flake8 per-file-ignores block missing or reshaped"
        assert {c.strip() for c in m.group(1).split(",")} == {"E501"}, (
            "tests/ grant diverged from ruff (ruff tests/* carries E501)"
        )
        assert {c.strip() for c in m.group(2).split(",")} == {"E402", "E501"}, (
            "scripts/ grant diverged from ruff (ruff scripts/* carries E402, E501)"
        )
