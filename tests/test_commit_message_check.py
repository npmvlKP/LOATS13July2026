"""Regression tests for scripts/commit_message_check.py.

2026-09-06 incident: the hook correctly rejected a non-conventional
commit subject but crashed printing the rejection diagnostic — the
subject contained U+2192, unencodable on a cp1252 console — so the
operator saw a Python traceback instead of the gate's rejection
diagnostic, with no indication whether the message or the tooling
failed. These tests pin both sides of the contract:

* the format rule itself (F8-L-06-R2), including the exact rejection
  class that exposed the crash, and
* encoding-safety: every diagnostic path must survive a console whose
  encoding cannot represent the commit subject, by degrading to
  backslash escapes instead of raising.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "commit_message_check.py"

PROHIBITED_SUBJECT = "feat: ready for production"
# The 2026-09-06 incident subject class: a status-essay subject whose
# content includes a non-ASCII arrow, exactly as the operator's
# evidence-bearing draft did (U+2192 at reason position 362).
INVALID_SUBJECT = "Update: routing \u2192 live - 2026-09-06"
VALID_SUBJECT = "fix(gate): repair cp1252 rejection crash in commit gate"
ARROW_BODY = "Signed-off reasoning: a -> b with an arrow\n"
MERGE_SUBJECT = "Merge branch 'feature/x' into fix/fr7-wave"


def _load_module() -> ModuleType:
    """Load the hook script as a module (it has no package parent)."""
    spec = importlib.util.spec_from_file_location(
        "commit_message_check_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_hook(message: str | None, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the hook exactly as pre-commit does: message file + argv.

    ``message=None`` skips writing the file entirely (missing-file path).
    """
    msg_file = tmp_path / "COMMIT_EDITMSG"
    if message is not None:
        msg_file.write_text(message, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(msg_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        check=False,
    )


class TestFormatRule:
    """F8-L-06-R2: first line must be Conventional Commit shaped."""

    @pytest.mark.parametrize(
        ("subject", "expected_type"),
        [
            (VALID_SUBJECT, "fix"),
            ("feat!: breaking change to the gate API", "feat"),
            ("docs(adr): record the artifact policy", "docs"),
            ("chore: routine dependency pin bump", "chore"),
            (MERGE_SUBJECT, None),
        ],
    )
    def test_valid_subjects_pass(
        self, subject: str, expected_type: str | None, tmp_path: Path
    ) -> None:
        message = subject if expected_type is None else f"{subject}\n\n{ARROW_BODY}"
        result = _run_hook(message, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK Commit message validation passed" in result.stdout

    @pytest.mark.parametrize(
        "subject",
        [
            INVALID_SUBJECT,
            "updated the gate",
            "fix - no colon separator",
            "Fix(gate): capitalised type is rejected",
            "feat(gate):",
        ],
    )
    def test_invalid_subjects_fail_with_reason(
        self, subject: str, tmp_path: Path
    ) -> None:
        result = _run_hook(subject, tmp_path)
        assert result.returncode == 1
        assert "ERROR COMMIT REJECTED" in result.stdout
        assert "first line" in result.stdout or "commit type" in result.stdout

    def test_invalid_subject_with_non_ascii_body_is_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        """The 2026-09-06 incident: rejection must not depend on console cp."""
        message = f"{INVALID_SUBJECT}\n\n{ARROW_BODY}"
        result = _run_hook(message, tmp_path)
        assert result.returncode == 1
        assert "UnicodeEncodeError" not in (result.stdout + result.stderr)
        assert "Traceback" not in result.stderr
        assert "violates the required format" in result.stdout


class TestProhibitedPhrases:
    """Rule 1: deployment-readiness claims are rejected whole-message."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "ready for deployment",
            "production ready",
            "ready for production",
            "production-ready",
            "deployment-ready",
        ],
    )
    def test_prohibited_phrases_rejected_anywhere(
        self, phrase: str, tmp_path: Path
    ) -> None:
        result = _run_hook(f"feat: ship it now {phrase}", tmp_path)
        assert result.returncode == 1
        assert "prohibited phrases" in result.stdout

    def test_phrase_in_body_is_caught_not_just_subject(self, tmp_path: Path) -> None:
        phrase = PROHIBITED_SUBJECT.split(": ", 1)[1]
        result = _run_hook(f"feat: add gate\n\nthis makes the gate {phrase}", tmp_path)
        assert result.returncode == 1

    def test_merge_commit_still_checked_for_phrases(self, tmp_path: Path) -> None:
        result = _run_hook(f"{MERGE_SUBJECT}\n\nready for production", tmp_path)
        assert result.returncode == 1
        assert "prohibited phrases" in result.stdout


class TestEncodingSafety:
    """The root cause: cp1252 consoles must not turn a rejection into a
    UnicodeEncodeError that masks the diagnostic."""

    def test_emit_degrades_to_backslash_escapes_on_cp1252(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _load_module()
        module._emit("subject \u2192 arrow, em \u2014 dash")
        out = capsys.readouterr().out
        assert "\u2192" in out or "\\u2192" in out
        assert "UnicodeEncodeError" not in out

    def test_main_survives_unencodable_console(self, tmp_path: Path) -> None:
        """Direct main() call with a cp1252-locked stdout: the original
        crash (UnicodeEncodeError out of the rejection diagnostic) must
        stay replaced by a backslash-degraded, still-reasoned rejection."""
        module = _load_module()
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text(
            f"{INVALID_SUBJECT}\n\n\u2192 \u2014 \u2713", encoding="utf-8"
        )
        written: list[str] = []

        class _Cp1252Stream:
            encoding = "cp1252"

            def write(self, text: str) -> None:
                # Mirrors a real cp1252 console: raw unencodable text
                # raises here, so a plain print() regression would blow
                # up exactly like the 2026-09-06 incident.
                text.encode("cp1252")
                written.append(text)

            def flush(self) -> None:
                return None

        real_stdout = sys.stdout
        # main() reads the message path from sys.argv; under pytest that
        # argv points at the test module itself (which contains the
        # prohibited-phrase literals), so pin the hook's real argv.
        real_argv = sys.argv
        sys.argv = [str(SCRIPT_PATH), str(msg_file)]
        sys.stdout = _Cp1252Stream()  # type: ignore[assignment]
        try:
            rc = module.main()
        finally:
            sys.stdout = real_stdout
            sys.argv = real_argv
        assert rc == 1
        output = "".join(written)
        assert "violates the required format" in output
        assert "\\u2192" in output  # arrow degraded to backslash escape
        assert "\u2192" not in output  # raw arrow never reaches the console


class TestCliSurface:
    """Argv contract as pre-commit invokes it."""

    def test_missing_argument_fails_cleanly(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 1
        assert "No commit message file provided" in result.stdout

    def test_missing_file_fails_cleanly(self, tmp_path: Path) -> None:
        result = _run_hook(None, tmp_path)
        assert result.returncode == 1
        assert "not found" in result.stdout or "ERROR" in result.stdout

    def test_hook_entry_matches_precommit_config(self) -> None:
        """The config must keep pointing at this script (rename lockstep)."""
        text = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        assert "python scripts/commit_message_check.py" in text
