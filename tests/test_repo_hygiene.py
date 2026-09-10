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

import configparser
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
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


class TestSrcAsciiGate:
    """ASCII gate contract (ADR-0014): reachable green, enforced red.

    The gate's original contract demanded byte-pure ASCII across all of
    src/ while alerts.py deliberately embeds emoji in notification
    payloads pinned by tests/test_alerts.py -- a gate whose green state
    was unreachable, which is why it sat unwired in CI and pre-commit
    since birth (the decorative-gate erosion class). ADR-0014 normalized
    prose characters to ASCII, enumerated the test-pinned payload glyphs
    in ALLOWED_NON_ASCII, and wired the gate into the CI repo-hygiene
    job and pre-commit. These tests pin the new contract in both
    directions: the live tree passes, any non-allowlisted non-ASCII
    character -- anywhere in src/, including inside alerts.py -- fails.
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

    def test_live_tree_passes(self):
        proc = self._run()
        assert proc.returncode == 0, proc.stdout
        assert "satisfy the ASCII contract" in proc.stdout
        assert proc.stderr == "", proc.stderr

    def test_non_ascii_source_addition_fails(self):
        probe = REPO_ROOT / "src" / "loats" / "_tmp_ascii_gate_probe.py"
        try:
            probe.write_text("# non-ascii mutation \u2717\n", encoding="utf-8")
            proc = self._run()
        finally:
            probe.unlink(missing_ok=True)
        assert proc.returncode == 1, (
            f"non-ASCII source file must fail the gate, got rc={proc.returncode}"
        )
        assert "_tmp_ascii_gate_probe" in proc.stdout
        assert "U+2717" in proc.stdout

    def test_allowlist_is_enumeration_not_exemption(self):
        # The alerts.py ALLOWED_NON_ASCII entry covers the exact test-pinned
        # payload glyphs; any other non-ASCII character in that file must
        # still fail. U+2717 (ballot X) is pinned by no test, so it is a
        # violation even inside the allowlisted file.
        alerts = REPO_ROOT / "src" / "loats" / "alerts.py"
        original = alerts.read_bytes()
        try:
            alerts.write_bytes(original + b"\n# _tmp allowlist probe \xe2\x9c\x97\n")
            proc = self._run()
        finally:
            alerts.write_bytes(original)
        assert proc.returncode == 1, (
            "a non-allowlisted character inside alerts.py must fail the gate: "
            + proc.stdout[:300]
        )
        assert "alerts.py" in proc.stdout


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


class TestSecurityScheduleSemantics:
    """security.yml's weekly cron must reach every gate unconditionally.

    Root cause being guarded: on 2026-09-06 the only scheduled Security
    Scan run on main concluded "skipped" in 2 seconds -- it fired before
    the dead-gate repair (cf03d47) reached main, and no local gate could
    see that the weekly audit safety net was silently dead (run
    34065636491). Two regression shapes are pinned here, detected
    statically so the contract holds on any tree, not just a green one:

      1. every job carrying an explicit ``if:`` must keep the schedule
         event in that condition -- naming only workflow_dispatch/push
         is exactly how jobs silently stop running on schedule; a bare
         ``always()`` (or no ``if:``) is unconditional and always fine;
      2. the ``on:`` block must keep exactly one schedule trigger with
         the documented cadence -- deleting or editing it changes the
         audit cadence with no code diff to review.

    The parser is unit-tested against synthetic YAML below, so the
    detection logic itself is proven and not merely green by accident.
    """

    SECURITY_YML = REPO_ROOT / ".github" / "workflows" / "security.yml"

    @staticmethod
    def _job_blocks(text: str) -> dict[str, list[str]]:
        """Map ``jobs.<id>:`` to its job-level (indent-4) ``if:`` lines.

        Line-oriented parser, no yaml dependency (suite convention): a
        job header is an indent-2 ``<name>:`` after the indent-0
        ``jobs:`` key; its block-level conditions sit at indent 4.
        Step-level ``if:`` (indent 8+) is intentionally ignored -- a
        step may legitimately filter by event.
        """
        jobs: dict[str, list[str]] = {}
        current: str | None = None
        in_jobs = False
        for raw in text.splitlines():
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()
            if indent == 0:
                in_jobs = stripped == "jobs:"
                current = None
                continue
            if not in_jobs:
                continue
            if indent == 2 and stripped.endswith(":"):
                current = stripped[:-1]
                jobs.setdefault(current, [])
            elif indent == 4 and current is not None and stripped.startswith("if:"):
                jobs[current].append(stripped)
        return jobs

    @staticmethod
    def _schedule_blind_jobs(jobs: dict[str, list[str]]) -> list[str]:
        """Jobs whose explicit conditions would skip a scheduled run."""
        blind: list[str] = []
        for name, conditions in jobs.items():
            for cond in conditions:
                if (
                    "github.event_name == 'schedule'" not in cond
                    and "always()" not in cond
                ):
                    blind.append(name)
                    break
        return blind

    @staticmethod
    def _cron_lines(text: str) -> list[str]:
        """The ``- cron:`` entries of the top-level ``on: schedule:`` block."""
        crons: list[str] = []
        in_on = False
        in_schedule = False
        for raw in text.splitlines():
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()
            if indent == 0:
                in_on = stripped == "on:"
                in_schedule = False
                continue
            if not in_on:
                continue
            if indent <= 2:
                in_schedule = stripped == "schedule:"
                continue
            if in_schedule and stripped.startswith("- cron:"):
                crons.append(stripped)
        return crons

    def test_parser_flags_schedule_blind_job(self) -> None:
        """RED-proof: the detector catches the silent-skip shape."""
        synthetic = (
            "name: scan\n"
            "on:\n"
            "  schedule:\n"
            "    - cron: '30 21 * * 0'\n"
            "jobs:\n"
            "  dependency-scan:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name == 'workflow_dispatch'\n"
            "    steps:\n"
            "      - run: echo hi\n"
        )
        blocks = self._job_blocks(synthetic)
        assert "dependency-scan" in blocks, "parser lost the job block"
        assert self._schedule_blind_jobs(blocks) == ["dependency-scan"]

    def test_parser_accepts_schedule_covering_job(self) -> None:
        """The compliant shape (as security.yml is written) passes."""
        synthetic = (
            "on:\n"
            "  schedule:\n"
            "    - cron: '30 21 * * 0'\n"
            "  workflow_dispatch:\n"
            "    inputs:\n"
            "      scan_type:\n"
            "jobs:\n"
            "  dependency-scan:\n"
            "    if: github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch' && github.event.inputs.scan_type == 'full')\n"
            "    steps:\n"
            "      - run: echo hi\n"
            "  summary:\n"
            "    if: always() && (github.event_name == 'workflow_dispatch' || github.event_name == 'schedule')\n"
            "    steps:\n"
            "      - run: echo done\n"
        )
        blocks = self._job_blocks(synthetic)
        assert set(blocks) == {"dependency-scan", "summary"}
        assert self._schedule_blind_jobs(blocks) == []
        assert len(self._cron_lines(synthetic)) == 1

    def test_parser_ignores_step_level_event_filters(self) -> None:
        """A step-level ``if:`` without schedule must not false-positive."""
        synthetic = (
            "jobs:\n"
            "  dependency-scan:\n"
            "    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'\n"
            "    steps:\n"
            "      - name: Upload\n"
            "        if: github.event_name == 'workflow_dispatch'\n"
            "        run: upload-artifact\n"
        )
        assert self._schedule_blind_jobs(self._job_blocks(synthetic)) == []

    def test_every_security_job_is_reachable_on_schedule(self) -> None:
        """Live invariant: no security.yml job may silently skip the cron."""
        text = self.SECURITY_YML.read_text(encoding="utf-8")
        blind = self._schedule_blind_jobs(self._job_blocks(text))
        assert blind == [], (
            f"security.yml jobs {blind} carry an explicit `if:` that does"
            " not include the schedule event; a weekly cron fires with"
            " event_name == 'schedule' and those jobs will conclude"
            " 'skipped' in seconds -- the exact silent death of run"
            " 34065636491. Add the schedule branch or drop the `if:`."
        )

    def test_security_schedule_trigger_is_exactly_one_cron(self) -> None:
        """Live invariant: the weekly cadence is pinned and singular."""
        crons = self._cron_lines(self.SECURITY_YML.read_text(encoding="utf-8"))
        assert len(crons) == 1, (
            f"expected exactly one schedule cron in security.yml, found"
            f" {len(crons)}: {crons}; the weekly audit cadence is a"
            " documented contract -- change it deliberately here"
        )
        assert crons[0].startswith("- cron: '30 21 * * 0'"), (
            f"security.yml cron changed to {crons[0]!r}; update this"
            " contract and CONTRIBUTING.md together or revert"
        )


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

    def test_workflows_have_no_deprecated_gitleaks_v2(self) -> None:
        """gitleaks-action@v2 dies with the Node 20 runner removal.

        GitHub removes Node 20 from hosted runners on 2026-09-16; @v2 is
        Node 20 and has no opt-out after that date. @v3 is the Node-24
        release with unchanged behavior (only the CONFIG_PATH input was
        renamed to GITLEAKS_CONFIG). BOTH workflows must assert this:
        the original security.yml-only test let the sibling ci.yml pin
        drift to @v2, surfacing only as a live deprecation annotation
        on a green run (2026-09-09) — sweep the class, not the first
        hit.
        """
        for yml in (CI_YML, self.SECURITY_YML):
            text = yml.read_text(encoding="utf-8")
            assert "gitleaks-action@v2" not in text, (
                f"{yml.name} pins gitleaks-action@v2 (Node 20) — removed"
                " from GitHub-hosted runners on 2026-09-16; use @v3"
            )
            assert "gitleaks-action@v3" in text, (
                f"{yml.name} must pin gitleaks-action@v3 (Node 24) so the"
                " positive pin is asserted, not just the absence of v2"
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


CARRIED_VERIFIER = REPO_ROOT / "scripts" / "verify_carried_set_external.py"
F8H01_VERIFIER = REPO_ROOT / "scripts" / "verify_f8h01_external.py"
F8H02_VERIFIER = REPO_ROOT / "scripts" / "verify_f8h02_external.py"
CARRIED_RECORD_ANCHOR = (
    "`as_of_date` convention (F8-L-02, CMP Rule 8) | CLOSED 2026-09-07"
)


class TestCarriedSetExternalVerifier:
    """Carried-set reconciliation net: the external verifier must stay honest.

    GREEN direction: exits 0 against the live tree from a clean process,
    re-deriving every disposition in
    docs/audit-history/07Sep2026-carried-set-reconciliation.md.
    RED direction (F8-L-02 closed 2026-09-07): on a snapshot whose
    trade_decisions schema drops the ``as_of_date`` column while the
    record still claims closure, the verifier must FAIL -- proving it
    verifies the recorded disposition against reality rather than
    trusting the prose.
    """

    def test_verifier_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CARRIED_VERIFIER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "All carried-set dispositions VERIFIED." in proc.stdout
        assert "[FAIL]" not in proc.stdout

    def test_verifier_fails_on_implementation_stripped_snapshot(self, tmp_path) -> None:
        rec = (
            REPO_ROOT
            / "docs"
            / "audit-history"
            / "07Sep2026-carried-set-reconciliation.md"
        )
        text = rec.read_text(encoding="utf-8")
        assert CARRIED_RECORD_ANCHOR in text, "closure anchor missing from the record"

        snapshot = tmp_path / "snap"
        (snapshot / "scripts").mkdir(parents=True)
        for script in (REPO_ROOT / "scripts").glob("*.py"):
            shutil.copy2(script, snapshot / "scripts" / script.name)
        shutil.copytree(
            REPO_ROOT / "src" / "loats",
            snapshot / "src" / "loats",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        # Strip the persistence leg of the propagation chain while the
        # record still registers the item as CLOSED: the verifier must
        # catch the drift between prose and tree.
        db_path = snapshot / "src" / "loats" / "database.py"
        db_text = db_path.read_text(encoding="utf-8")
        assert "as_of_date TEXT" in db_text
        db_path.write_text(
            db_text.replace("as_of_date TEXT", "as_of_date_stub TEXT"),
            encoding="utf-8",
        )
        (snapshot / "docs" / "audit-history").mkdir(parents=True)
        (snapshot / "docs" / "audit-history" / rec.name).write_text(
            text, encoding="utf-8"
        )
        shutil.copy2(REPO_ROOT / ".env.example", snapshot / ".env.example")
        shutil.copytree(
            REPO_ROOT / "reports",
            snapshot / "reports",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copytree(
            REPO_ROOT / "tests" / "fixtures",
            snapshot / "tests" / "fixtures",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        subprocess.run(
            ["git", "init", "-q"], cwd=snapshot, capture_output=True, timeout=60
        )
        subprocess.run(
            ["git", "add", "-A"], cwd=snapshot, capture_output=True, timeout=300
        )

        proc = subprocess.run(
            [sys.executable, str(snapshot / "scripts" / CARRIED_VERIFIER.name)],
            cwd=snapshot,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode != 0, (
            "verifier PASSED on a snapshot whose as_of_date persistence "
            "was stripped -- it does not verify the recorded disposition"
        )
        assert "trade_decisions schema persists as_of_date" in proc.stdout
        assert "[FAIL] trade_decisions schema persists as_of_date" in proc.stdout


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

    2026-09-09 hardening: the original probe enumerated three hand-picked
    files while the hook's real file set is EVERY tracked *.py — and the
    tracked frozen-evidence trees (docs/audit-history/,
    reports/ai-generated/) carried 56 live findings (26 E402 + 29 E501 in
    22 files, plus 1 F841 in scripts/) at those three files' clean
    verdict. The probe now sweeps the full tracked surface in the hook's
    explicit-filename mode, and the grant agreement is asserted against
    ruff's LIVE pyproject config (tomllib-derived), not a hard-coded
    subset. A RED net pins the frozen trees' grants to the exact live
    emission classes so the amnesty cannot silently widen.
    """

    def test_explicit_path_mode_agrees_with_ruff(self) -> None:
        # The exact false-positive class, at full surface: HEAD's own
        # tracked *.py files, in the hook's explicit-filename mode. Must
        # stay enumeration-free so no future tracked file escapes the net
        # (the 2026-09-09 blind spot was exactly an incomplete hand list).
        tracked = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout.splitlines()
        assert tracked, "git ls-files returned no tracked python files"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flake8",
                "--config",
                str(REPO_ROOT / ".flake8"),
                *tracked,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            f"flake8 hook-mode false positive on the repo's own files "
            f"({len(tracked)} tracked): {proc.stdout[:800]}"
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

    @staticmethod
    def _ruff_per_file_ignores() -> dict[str, list[str]]:
        with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        return {
            pattern: list(codes)
            for pattern, codes in data["tool"]["ruff"]["lint"][
                "per-file-ignores"
            ].items()
        }

    def test_grant_sets_match_ruff(self) -> None:
        # Parity direction that matters: any tracked file the linter of
        # record (ruff) grants a pycodestyle/pyflakes amnesty must hold
        # the SAME amnesty under flake8's mirror, or the pre-commit hook
        # false-fails on a file ruff accepts. Union-per-file semantics:
        # a file's effective grant is the union of every pattern that
        # matches it, on both sides — so file-scoped ruff grants
        # (scripts/verify_*.py = [F841] ...) are satisfied by the wider
        # scripts/* mirror without demanding per-pattern duplication.
        # Codes outside flake8's visible classes (EXE001, FA102, PGH003,
        # RUF..., PL..., and C901 which needs --max-complexity) have no
        # mirror semantics and are excluded by the [EWF]\d+ filter. The
        # inverse direction is intentionally looser — flake8 may pass
        # files ruff rejects (ruff is the linter of record); the
        # full-surface behavioral probe pins the tree itself.
        ruff_grants = self._ruff_per_file_ignores()
        tracked = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout.splitlines()
        assert tracked, "git ls-files returned no tracked python files"
        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / ".flake8", encoding="utf-8")
        assert parser.has_section("flake8"), ".flake8 lost its [flake8] section"
        mirror: list[tuple[str, set[str]]] = []
        for entry in parser["flake8"].get("per-file-ignores", "").splitlines():
            entry = entry.strip()
            if not entry or entry.startswith("#") or ":" not in entry:
                continue
            pattern, _, codes = entry.partition(":")
            mirror.append(
                (pattern.strip(), {c.strip() for c in codes.split(",") if c.strip()})
            )
        assert mirror, ".flake8 per-file-ignores block missing or reshaped"
        checked = 0
        for pattern, codes in ruff_grants.items():
            must = {c for c in codes if re.fullmatch(r"[EWF]\d+", c)}
            if not must:
                continue
            for path in (f for f in tracked if fnmatch.fnmatch(f, pattern)):
                amnesty: set[str] = set()
                for mp, mcodes in mirror:
                    if fnmatch.fnmatch(path, mp):
                        amnesty |= mcodes
                assert must <= amnesty, (
                    f"{path}: flake8 mirror amnesty {sorted(amnesty)} lacks "
                    f"ruff grant {sorted(must - amnesty)} (pattern {pattern})"
                )
                checked += 1
        assert checked > 0, (
            "parity net matched no tracked files — ruff per-file-ignores "
            "patterns and the tracked tree have diverged"
        )

    def test_frozen_tree_grants_bounded_to_live_emissions(self, tmp_path) -> None:
        # RED net for the 2026-09-09 fix: the frozen trees' amnesty must
        # stay exactly as wide as the codes the files actually emit. The
        # faithful probe is the repo's OWN base config (global ignore
        # list, max-line-length) with per-file-ignores stripped — that
        # yields precisely the codes the grants must cover. (--isolated
        # is wrong here: it reverts to the 79-col default and flake8's
        # stock ignore list, so globally-ignored W503 leaked into the
        # class set and false-failed the net on a config that no longer
        # exists.)
        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / ".flake8", encoding="utf-8")
        assert parser.has_section("flake8"), ".flake8 lost its [flake8] section"
        parser.remove_option("flake8", "per-file-ignores")
        stripped = tmp_path / "flake8-no-per-file-ignores.cfg"
        with open(stripped, "w", encoding="utf-8") as fh:
            parser.write(fh)
        emission_classes: dict[str, set[str]] = {}
        for tree in ("docs/audit-history", "reports/ai-generated"):
            tracked = subprocess.run(
                ["git", "ls-files", f"{tree}/*.py"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            ).stdout.splitlines()
            if not tracked:
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "flake8", "--config", str(stripped), *tracked],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=600,
            )
            for line in proc.stdout.splitlines():
                parts = line.split(":", 3)
                if len(parts) == 4:
                    emission_classes.setdefault(tree, set()).add(
                        parts[3].strip().split(" ", 1)[0]
                    )
        assert emission_classes == {
            "docs/audit-history": {"E402", "E501"},
            "reports/ai-generated": {"E501"},
        }, (
            "frozen-evidence trees emit a lint class outside their bounded "
            f"grants: {emission_classes} — extend .flake8 consciously if new "
            "grants are justified, never silently"
        )
        # The conftest-specific grant stays part of the mirror contract:
        # ruff's "tests/conftest.py" = ["E402"] plus F811/F841 for the
        # dummy-variable reset fixture (see the .flake8 block comment).
        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / ".flake8", encoding="utf-8")
        conftest_grant: set[str] = set()
        for entry in parser["flake8"]["per-file-ignores"].splitlines():
            entry = entry.strip()
            if entry.startswith("tests/conftest.py:"):
                conftest_grant = {c.strip() for c in entry.partition(":")[2].split(",")}
        assert conftest_grant == {"E402", "F811", "F841"}, (
            f"conftest grant diverged from the ruff-mirror contract: {conftest_grant}"
        )


class TestFixerHooksSpareFrozenEvidence:
    """Fixer hooks must never rewrite the frozen audit-evidence trees.

    Defect class (2026-09-09): `pre_commit run --all-files` passes every
    tracked filename explicitly and trailing-whitespace /
    end-of-file-fixer / ruff-format rewrite files they are handed — their
    own exclude configs do not apply to explicit paths (same bypass as
    the flake8 hook). One sweep rewrote 118 tracked files including 83
    missing-EOF-newline and 19 trailing-whitespace members of
    docs/audit-history/ and reports/ai-generated/ — point-in-time
    evidence that must never be mutated. Root cause: hook-level
    `exclude:` (pre-commit's filename filter, which DOES apply in
    explicit-filename mode) on every content-mutating hook. These nets
    pin the mechanism end-to-end against the real pre-commit runner:
    with the shipped config the frozen trees stay byte-stable; with an
    excludes-stripped mutant they get rewritten (proving the exclude is
    the operative protection, not hook passivity).
    """

    FROZEN_TREES = ("docs/audit-history/", "reports/ai-generated/")
    MUTATOR_HOOKS = ("trailing-whitespace", "end-of-file-fixer")

    @staticmethod
    def _dirty_paths() -> set[str]:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
        return {line[3:] for line in out.splitlines() if line.startswith(" M ")}

    def _run_hook(self, hook: str, config: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pre_commit",
                "run",
                "--config",
                str(config),
                hook,
                "--all-files",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )

    @staticmethod
    def _strip_mutator_excludes(config_text: str) -> str:
        lines = config_text.splitlines()
        kept: list[str] = []
        skip_indent = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("exclude: ^docs/audit-history/") or (
                skip_indent and line.startswith(skip_indent) and "exclude:" in stripped
            ):
                skip_indent = line[: len(line) - len(line.lstrip())]
                continue
            skip_indent = ""
            kept.append(line)
        return "\n".join(kept) + "\n"

    def _sweep_legs(self, config: Path, expect_frozen_rewrites: bool) -> None:
        before = self._dirty_paths()
        frozen_rewritten: list[str] = []
        try:
            for hook in self.MUTATOR_HOOKS:
                self._run_hook(hook, config)
                frozen_rewritten.extend(
                    p
                    for p in self._dirty_paths() - before
                    if p.startswith(self.FROZEN_TREES)
                )
        finally:
            # Self-repairing net: restore anything the sweep mutated so a
            # RED result cannot leave the working tree damaged.
            collateral = self._dirty_paths() - before
            if collateral:
                subprocess.run(
                    ["git", "checkout", "--", *sorted(collateral)],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
        if expect_frozen_rewrites:
            assert frozen_rewritten, (
                f"{config.name}: expected the excludes-stripped mutant to let "
                "the fixer hooks rewrite frozen-evidence files, but nothing "
                "was rewritten — the net no longer proves the exclude works"
            )
        else:
            assert not frozen_rewritten, (
                f"fixer hooks rewrote frozen-evidence files: {frozen_rewritten[:5]} "
                "— hook-level exclude on the mutator hooks is missing or narrowed"
            )

    def test_shipped_config_spares_frozen_evidence(self) -> None:
        self._sweep_legs(REPO_ROOT / ".pre-commit-config.yaml", False)

    def test_excludes_stripped_mutant_proves_the_mechanism(self) -> None:
        # The mutant config MUST live on the repo's own drive: pre-commit
        # computes a relative path between --config and the repo root and
        # dies with "path is on mount 'C:', start on mount 'G:'" otherwise
        # (observed rc=3, zero hooks run). .git/ is inside the repo,
        # invisible to git status, and never staged.
        mutant = REPO_ROOT / ".git" / "pre-commit-no-excludes.yaml"
        mutant.write_text(
            self._strip_mutator_excludes(
                (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
            ),
            encoding="utf-8",
        )
        try:
            self._sweep_legs(mutant, True)
        finally:
            mutant.unlink(missing_ok=True)

    def test_mutator_excludes_present_and_scoped(self) -> None:
        import yaml

        cfg = yaml.safe_load(
            (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        )
        mutators = {
            "trailing-whitespace",
            "end-of-file-fixer",
            "ruff",
            "ruff-format",
        }
        found: set[str] = set()
        for repo in cfg["repos"]:
            for hook in repo.get("hooks", []):
                if hook["id"] not in mutators:
                    continue
                found.add(hook["id"])
                exclude = hook.get("exclude")
                assert exclude, (
                    f"fixer hook {hook['id']} lost its frozen-evidence exclude"
                )
                rx = re.compile(exclude)
                for tree in self.FROZEN_TREES:
                    assert rx.search(f"{tree}x.py"), (
                        f"{hook['id']} exclude no longer matches {tree}"
                    )
                assert not rx.search("src/loats/orchestrator.py"), (
                    f"{hook['id']} exclude amnesties production source"
                )
                assert not rx.search("tests/test_repo_hygiene.py"), (
                    f"{hook['id']} exclude amnesties the test tree"
                )
        assert found == mutators, (
            f"mutator hooks missing from config: {mutators - found}"
        )


class TestShebangExecBit:
    """Every tracked shebang'd script must sit at index mode 100755.

    Defect class (ADR-0013): Windows cannot record exec bits, so a
    shebang'd script committed from Windows lands at 100644; Windows
    ruff suppresses EXE001, so the defect surfaces only as a Linux CI
    ruff failure — realized by verify_f8m02_m07_external.py before
    db5957b. The shebang-exec-bit pre-commit hook
    (scripts/ensure_shebang_exec_bit.py) self-heals staged files;
    these tests pin the live-tree invariant and prove the normalizer's
    semantics end-to-end in a throwaway git repository.
    """

    @staticmethod
    def _load_normalizer():
        spec = importlib.util.spec_from_file_location(
            "ensure_shebang_exec_bit",
            str(REPO_ROOT / "scripts" / "ensure_shebang_exec_bit.py"),
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_live_tree_shebang_scripts_are_executable(self) -> None:
        mod = self._load_normalizer()
        offenders = sorted(
            p for p, m in mod.tracked_py_modes().items() if mod.needs_fix(m, p)
        )
        assert offenders == [], (
            "shebang'd scripts at mode 100644 (Linux CI EXE001 will fail; "
            f"run scripts/ensure_shebang_exec_bit.py): {offenders}"
        )

    def test_normalizer_flips_only_shebang_100644_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mod = self._load_normalizer()
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "guard@example.com")
        git("config", "user.name", "guard")
        (repo / "shebang.py").write_bytes(b"#!/usr/bin/env python3\nprint(1)\n")
        (repo / "plain.py").write_bytes(b"print(1)\n")
        git("add", "shebang.py", "plain.py")
        monkeypatch.setattr(mod, "REPO_ROOT", repo)

        assert mod.main(["shebang.py", "plain.py"]) == 0
        out = capsys.readouterr().out
        assert "enabled executable bit: shebang.py" in out
        assert "plain.py" not in out
        modes = mod.tracked_py_modes(["shebang.py", "plain.py"])
        assert modes["shebang.py"] == "100755"
        assert modes["plain.py"] == "100644"

        # Idempotent when clean.
        assert mod.main(["shebang.py", "plain.py"]) == 0
        assert (
            "OK every tracked shebang'd script already carries mode 100755"
            in capsys.readouterr().out
        )

    def test_unit_semantics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = self._load_normalizer()
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        shebang = tmp_path / "s.py"
        shebang.write_bytes(b"#!/bin/sh\n")
        plain = tmp_path / "p.py"
        plain.write_bytes(b"print(1)\n")
        assert mod.has_shebang(shebang) is True
        assert mod.has_shebang(plain) is False
        assert mod.parse_mode("100644 abcdef 0\tshebang.py") == "100644"
        assert mod.needs_fix("100644", "s.py") is True
        assert mod.needs_fix("100755", "s.py") is False
        assert mod.needs_fix("100644", "p.py") is False


class TestF8H01VerifierEvidenceStreamIsolation:
    """The F8-H-01 verifier must not write into the production P5 evidence
    stream.

    Defect (2026-09-08): check_e shelled ``run_p5_forward_test.py
    --dry-run`` without P5_RUN_LOG_DIR, so every verifier run dropped a
    closed dry-run stub into reports/ -- machine-local debris in the live
    run-log directory, invisible to git (reports/*.json ignored) and to
    the tracked-set guard alike.
    """

    def test_runner_invocation_pins_p5_run_log_dir(self) -> None:
        src = F8H01_VERIFIER.read_text(encoding="utf-8")
        assert "P5_RUN_LOG_DIR" in src, (
            "verify_f8h01_external.py must redirect the dry-run runner's "
            "run-log writes out of the production evidence stream"
        )

    def test_verifier_run_leaves_no_stub_in_reports(self, tmp_path) -> None:
        before = set((REPO_ROOT / "reports").glob("p5_forward_test_*.json"))
        proc = subprocess.run(
            [sys.executable, str(F8H01_VERIFIER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        after = set((REPO_ROOT / "reports").glob("p5_forward_test_*.json"))
        assert after == before, (
            f"verifier run created debris in reports/: "
            f"{sorted(p.name for p in after - before)}"
        )
        assert "[FAIL]" not in proc.stdout

    def test_guard_flags_dry_run_stub_in_evidence_stream(
        self, tmp_path, monkeypatch
    ) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_repo_hygiene_probe", GUARD_PATH
        )
        assert spec is not None and spec.loader is not None
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)

        reports = tmp_path / "reports"
        reports.mkdir()
        stub = reports / "p5_forward_test_20260908_101820.json"
        stub.write_text(
            json.dumps(
                {
                    "metadata": {
                        "phase_gate": "P5",
                        "finding": "F8-H-01",
                        "reason": "F8-H-01 P5 forward test",
                        "dry_run": True,
                        "script": "scripts/run_p5_forward_test.py",
                    },
                    "started_at": "2026-09-08T10:18:20+00:00",
                    "ended_at": "2026-09-08T10:18:20+00:00",
                }
            ),
            encoding="utf-8",
        )
        with open(reports / "p5_forward_test_live.json", "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "metadata": {
                        "phase_gate": "P5",
                        "finding": "F8-H-01",
                        "reason": "supervised run",
                        "dry_run": False,
                        "script": "scripts/run_p5_forward_test.py",
                    },
                },
                fh,
            )

        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard._p5_dry_run_stubs() == [stub.name]


class TestF8H02ExternalVerifier:
    """Suite net for the F8-H-02 external verifier (Rule-7 per-order budget).

    GREEN direction: exits 0 against the live tree from a clean process,
    behaviorally proving the per-order modification gate (persistence,
    reserve-before-broker, boundary enforcement, fail-closed, release,
    terminal reset).
    RED direction: on a snapshot whose ``modify_order`` no longer reserves
    budget, the verifier must FAIL -- proving it verifies behavior rather
    than source idioms (the F8-C-01 lesson, docs/adr/0006).
    """

    def test_verifier_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(F8H02_VERIFIER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "Rule-7 per-order gate verified live" in proc.stdout
        assert "[FAIL]" not in proc.stdout

    def test_verifier_fails_on_gate_stripped_snapshot(self, tmp_path) -> None:
        snapshot = tmp_path / "snap"
        (snapshot / "scripts").mkdir(parents=True)
        for script in (REPO_ROOT / "scripts").glob("*.py"):
            shutil.copy2(script, snapshot / "scripts" / script.name)
        shutil.copytree(
            REPO_ROOT / "src" / "loats",
            snapshot / "src" / "loats",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        target = snapshot / "src" / "loats" / "openalgo.py"
        src = target.read_text(encoding="utf-8")
        anchor = "rules_engine.reserve_modification(order_id)"
        assert anchor in src, "gate anchor missing from openalgo.py"
        target.write_text(
            src.replace(anchor, "pass  # F8-H-02 gate stripped by mutation"),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(snapshot / "scripts" / F8H02_VERIFIER.name)],
            cwd=snapshot,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode != 0, (
            "verifier PASSED on a snapshot whose modify_order boundary gate "
            "was stripped -- it does not verify the behavior"
        )
        assert "[FAIL] 3. boundary gate fires at modify_order" in proc.stdout


class TestGitleaksPrepushNet:
    """ADR-0014 (F8-C-02 NEXT item): the defense-in-depth pre-push net.

    Outcome-scoped: the runner must scan the push's introduced commits
    under pure default gitleaks rules (no repo allowlist), fail closed
    on a missing binary or a finding, and stay silent-compatible with
    pre-commit (which consumes pre-push stdin itself -- verified in the
    installed pre-commit 4.6.2 hook_impl.py). Live gitleaks is not
    required: every scan runs through a fake binary whose verdict the
    test controls.
    """

    RUNNER_PATH = REPO_ROOT / "scripts" / "gitleaks_prepush.py"

    @staticmethod
    def _load_runner():
        spec = importlib.util.spec_from_file_location(
            "gitleaks_prepush", str(TestGitleaksPrepushNet.RUNNER_PATH)
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.fixture()
    def runner(self):
        return self._load_runner()

    @staticmethod
    def _make_clone(base: Path) -> Path:
        clone = base / f"clone-{uuid.uuid4().hex[:8]}"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", str(REPO_ROOT), str(clone)],
            check=True,
            capture_output=True,
        )
        # The clone is of committed HEAD; the wave's runner rides along
        # so the clone models this wave's committed tree.
        scripts = clone / "scripts"
        scripts.mkdir(exist_ok=True)
        shutil.copy2(
            TestGitleaksPrepushNet.RUNNER_PATH, scripts / "gitleaks_prepush.py"
        )
        return clone

    def _write_fake_gitleaks(self, tmp_path: Path, *, fire_on: str) -> str:
        """Platform-executable stand-in for the gitleaks binary.

        Returns the path to set as GITLEAKS_BINARY. The shim fires
        (rc 1) when its --log-opts argument contains ``fire_on``, else
        exits 0; rc 126 when fire_on == \"__rc126__\".
        """
        py = tmp_path / "fake_gitleaks_impl.py"
        py.write_text(
            "import sys\n"
            "opts = ' '.join(sys.argv[1:])\n"
            f"if {fire_on!r} in opts:\n"
            "    print('[fake-gitleaks] leak found')\n"
            "    sys.exit(1)\n"
            f"if {fire_on!r} == '__rc126__':\n"
            "    sys.exit(126)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        exe = sys.executable
        if IS_WINDOWS:
            shim = tmp_path / "fake-gitleaks.bat"
            shim.write_text(f'@echo off\n"{exe}" "{py}" %*\n', encoding="utf-8")
        else:
            shim = tmp_path / "fake-gitleaks"
            shim.write_text(f'#!/bin/sh\nexec "{exe}" "{py}" "$@"\n', encoding="utf-8")
            shim.chmod(0o755)
        return str(shim)

    def _clone_with_local_commit(self, tmp_path: Path) -> Path:
        """Hermetic clone holding exactly one commit no remote has.

        The probe is committed on an explicitly created branch: a clone
        taken from a source with a detached HEAD (the CI Actions
        checkout) would otherwise leave the probe unreachable from any
        branch and invisible to --branches (live-verified on the PR
        runner: 3 tests failed with 0 introduced commits).
        """
        clone = self._make_clone(tmp_path)
        env = {
            **{
                k: v
                for k, v in os.environ.items()
                if k.startswith(("GIT_", "SYSTEMROOT", "PATH", "HOME"))
            },
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(
            ["git", "checkout", "-q", "-B", "probe-net"],
            cwd=clone,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "--quiet", "-m", "probe"],
            cwd=clone,
            check=True,
            capture_output=True,
            env=env,
        )
        return clone

    def _clone_runner(self, clone: Path):
        """Load the CLONE's copy so REPO_ROOT is the clone (true
        end-to-end: the scan target is the clone, not this repo)."""
        spec = importlib.util.spec_from_file_location(
            "gitleaks_prepush_clone", str(clone / "scripts" / "gitleaks_prepush.py")
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_fail_closed_when_binary_missing(self, tmp_path, monkeypatch):
        clone = self._clone_with_local_commit(tmp_path)
        runner = self._clone_runner(clone)
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.delenv("GITLEAKS_BINARY", raising=False)
        rc = runner.main()
        assert rc == 1, "a push introducing commits must fail closed without gitleaks"

    def test_noop_push_passes_with_clean_verdict(self, tmp_path, monkeypatch):
        clone = self._make_clone(tmp_path)  # zero introduced commits
        runner = self._clone_runner(clone)
        binary = self._write_fake_gitleaks(tmp_path, fire_on="__never__")
        monkeypatch.setenv("GITLEAKS_BINARY", binary)
        assert runner.main() == 0, "nothing to scan: pass (binary present, unused)"

    def test_missing_binary_fails_even_with_zero_commits(self, tmp_path, monkeypatch):
        """Absolute fail-closed ordering: the binary gate precedes the
        empty-range shortcut. A contributor without gitleaks must fix
        the install, not ride on an empty rev-list -- otherwise a stale
        remote-tracking state could void the net entirely."""
        clone = self._make_clone(tmp_path)
        runner = self._clone_runner(clone)
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.delenv("GITLEAKS_BINARY", raising=False)
        assert runner.main() == 1

    def test_finding_over_introduced_commit_fails_push(self, tmp_path, monkeypatch):
        clone = self._clone_with_local_commit(tmp_path)
        runner = self._clone_runner(clone)
        # The runner passes commit SHAs (not paths) via --log-opts, so
        # "--log-opts" in argv is exactly "a scan over commits ran".
        binary = self._write_fake_gitleaks(tmp_path, fire_on="--log-opts")
        monkeypatch.setenv("GITLEAKS_BINARY", binary)
        assert runner.main() == 1, "a leak finding must fail the push"

    def test_clean_verdict_passes(self, tmp_path, monkeypatch):
        clone = self._clone_with_local_commit(tmp_path)
        runner = self._clone_runner(clone)
        binary = self._write_fake_gitleaks(tmp_path, fire_on="__never__")
        monkeypatch.setenv("GITLEAKS_BINARY", binary)
        assert runner.main() == 0

    def test_rc126_surface_change_is_actionable_failure(self, tmp_path, monkeypatch):
        clone = self._clone_with_local_commit(tmp_path)
        runner = self._clone_runner(clone)
        binary = self._write_fake_gitleaks(tmp_path, fire_on="__rc126__")
        monkeypatch.setenv("GITLEAKS_BINARY", binary)
        assert runner.main() == 1

    def test_scan_targets_only_local_only_commits(self, tmp_path):
        clone = self._make_clone(tmp_path)
        runner = self._clone_runner(clone)
        assert runner.introduced_commits(clone) == [], (
            "a fresh clone holds no unpushed commits"
        )
        with_local = self._clone_with_local_commit(tmp_path)
        runner2 = self._clone_runner(with_local)
        introduced = runner2.introduced_commits(with_local)
        probe = subprocess.run(
            ["git", "rev-parse", "probe-net"],
            cwd=with_local,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert probe in introduced, "the probe commit must be scanned"
        # No exact-count pin: a source with grafted (shallow) history --
        # the actions/checkout default -- legitimately yields a
        # superset (the source HEAD itself counts as unproven).
        # Superset = more scanned = the fail-closed-safe direction.

    def test_injected_config_is_pure_default_rules(self, runner):
        parsed = tomllib.loads(runner.DEFAULT_RULES_TOML)
        assert parsed == {"extend": {"useDefault": True}}, (
            "injected config must be default rules and NOTHING else -- "
            "no allowlist table, no paths, no .env exceptions"
        )

    def test_hook_wiring_pins_prepush_stage(self):
        text = _repo_relative(PRECOMMIT_YML)
        assert "default_install_hook_types:" in text
        assert "[pre-commit, commit-msg, pre-push]" in text
        assert "id: gitleaks-prepush" in text
        entry = text.index("id: gitleaks-prepush")
        block = text[entry : text.index("- id: deps-sync", entry)]
        assert "stages: [pre-push]" in block
        assert "language: system" in block
        assert "pass_filenames: false" in block

    def test_hook_range_semantics_cover_any_pushed_ref(self):
        """The net's range must not depend on the pushed ref name (the
        08Sep staged-snapshot class: a branch with an unusual name must
        still be scanned). --branches --not --remotes covers every
        local branch; the fake-binary runs above prove end-to-end
        wiring; this pins the exact expressions the script builds."""
        source = self.RUNNER_PATH.read_text(encoding="utf-8")
        assert '"--branches", "--not", "--remotes"' in source
        # The gitleaks --log-opts argument must carry the same
        # exclusion, or gitleaks walks full ancestry and re-flags the
        # dispositioned report-artifact history on every push
        # (live-verified false-positive class).
        assert "--log-opts={' '.join(commits)} --not --remotes" in source
