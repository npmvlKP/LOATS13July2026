"""Tests for the F8-C-02 repository hygiene guard.

Covers scripts/check_repo_hygiene.py: pattern matching semantics, the
tracked-file ceiling, the allowlist, and live repository invariants
(tracked set is clean, guard exits 0 on the real tree).

F8-M-03 additions: outcome-scoped verification of the shared Win32-safe
root junk detector (scripts/win32_root_junk.py), the HC-15 production
emission mutation net, and the HC-21 bare-env behavioral contract.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "check_repo_hygiene.py"
HELPER_PATH = REPO_ROOT / "scripts" / "win32_root_junk.py"
HC15_PROBE = REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py"

IS_WINDOWS = sys.platform == "win32"


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
