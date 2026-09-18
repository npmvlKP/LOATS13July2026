"""F8-H-01 forward-test integrity regression tests (2026-09-07).

Locks the four root-cause fixes that make the P5 forward test measure the
CMP P5 mandate (route ALL TradeDecisions to Analyzer) instead of spinning
on an empty loop:

1. Producer window: the trading-cycle producer window is settings-driven
   (``producer_window_seconds``), large enough for real feed latencies so
   signals persist and decisions form; producers still never outlive the
   cycle (F8-M-02 pins live in test_orchestrator_extra.py).
2. Validator: a completed run with cycles but ZERO decisional routing
   outcomes (success/disabled/error all 0) is a hard FAIL — cycles alone
   prove nothing about decisioning. Legacy logs without ``counters`` grade
   unchanged.
3. Runner isolation: P5_RUN_LOG_DIR redirects run-log writes so test/CI
   invocations never drop smoke stubs into the production evidence dir.
4. Test-data isolation: the pytest process pins SQLITE_DB_PATH/AUDIT_LOG_PATH
   into a private temp dir (conftest), so the ``db`` singleton can never
   bind production files under test (the 186 production audit rows written
   by earlier suite runs are the motivation).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))


import verify_p5_forward_test as validator  # noqa: E402


def _base_log(**overrides: Any) -> dict[str, Any]:
    """Structurally complete 15-day completed live run log.

    Span pinned entirely BEFORE the grader's documented contamination
    windows (F9-C-02 hardening): these fixtures grade the
    decisional-activity criterion, not contamination.
    """
    log: dict[str, Any] = {
        "metadata": {
            "phase_gate": "P5",
            "finding": "F8-H-01",
            "reason": "F8-H-01 P5 forward test",
            "dry_run": False,
            "script": "scripts/run_p5_forward_test.py",
        },
        "routing": {"enabled_at_start": True},
        "started_at": "2026-08-01T00:00:00+00:00",
        "ended_at": "2026-08-16T00:00:00+00:00",
        "unhandled_exceptions": 0,
        "restarts": 1,
        "cycles_completed": 1000,
        "counters": {"success": 5, "disabled": 0, "error": 0},
        "last_sampled_at": "2026-08-16T00:00:00+00:00",
        "events": [],
        # F9-C-02 closure (2026-09-18): kill-switch verification proof
        # (CMP P5 gate) -- present and disengaged on eligible fixtures.
        "kill_switch_verified": True,
        "kill_switch_active_at_start": False,
    }
    log.update(overrides)
    return log


class TestDecisionalActivityCriterion:
    """Zero routing counters with nonzero cycles must fail the gate."""

    def test_cycles_only_run_is_hard_fail(self) -> None:
        log = _base_log(counters={"success": 0, "disabled": 0, "error": 0})
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("no decisional activity" in r for r in grade.reasons)

    def test_decisional_activity_passes_gate(self) -> None:
        log = _base_log()
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS", grade.reasons
        assert "no decisional activity" not in grade.reasons

    def test_disabled_outcomes_count_as_decisional(self) -> None:
        """Routing resolved as disabled/error still proves the engine made
        real routing decisions (the kill path was exercised)."""
        log = _base_log(counters={"success": 0, "disabled": 12, "error": 1})
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS", grade.reasons

    def test_ongoing_zero_decisional_run_is_incomplete_not_fail(self) -> None:
        """A run started outside market hours has genuinely routed nothing
        YET: while ongoing it grades INCOMPLETE (with the decisional
        reason surfaced for the operator), never FAIL. The hard FAIL
        applies only when the run ends."""
        log = _base_log(
            ended_at=None, counters={"success": 0, "disabled": 0, "error": 0}
        )
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any("no decisional activity" in r for r in grade.reasons)

    def test_legacy_log_without_counters_grades_unchanged(self) -> None:
        """Legacy semantics: a log missing the ``counters`` field has no
        activity criteria at all (``has_activity_fields`` requires BOTH
        fields), so a clean 15-day routing-enabled run still grades PASS
        — the decisional criterion must not reach into legacy logs."""
        log = _base_log()
        del log["counters"]
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"
        assert not any("no decisional activity" in r for r in grade.reasons)

    def test_error_counters_alone_fail_on_no_activity_is_impossible(
        self,
    ) -> None:
        """Errors ARE decisional: a run with only error outcomes is not
        'no activity' — it fails only via unhandled_exceptions accounting,
        never via the decisional criterion."""
        log = _base_log(
            counters={"success": 0, "disabled": 0, "error": 3},
            unhandled_exceptions=0,
        )
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS", grade.reasons


class TestProducerWindowSetting:
    """The producer window must be a real settings field, default 8 s."""

    def test_default_is_eight_seconds(self) -> None:
        from pydantic import SecretStr

        from loats.config.settings import Settings

        s = Settings(
            environment="test",
            openalgo_api_key=SecretStr("k"),
            telegram_bot_token=SecretStr("t"),
            telegram_chat_id="1",
        )
        assert s.producer_window_seconds == 8.0

    def test_orchestrator_uses_settings_window(self) -> None:
        """The cycle's wait_for must source its timeout from settings, not
        a hard-coded literal (source-level pin; behavior pinned in
        test_orchestrator_extra.TestProducerWindowLifecycle)."""
        src = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        assert "settings.producer_window_seconds" in src
        assert "timeout=0.08" not in src


class TestRunnerLogDirOverride:
    """P5_RUN_LOG_DIR must redirect run-log writes (test/CI isolation)."""

    def test_env_override_wins_over_default(self, tmp_path: Path) -> None:
        import runpy

        mod_path = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
        old = os.environ.get("P5_RUN_LOG_DIR")
        try:
            os.environ["P5_RUN_LOG_DIR"] = str(tmp_path)
            mod = runpy.run_path(str(mod_path), run_name="p5_runner_probe")
            assert str(mod["RUN_LOG_DIR"]) == str(tmp_path)
        finally:
            if old is None:
                os.environ.pop("P5_RUN_LOG_DIR", None)
            else:
                os.environ["P5_RUN_LOG_DIR"] = old

    def test_default_is_production_reports_dir(self, tmp_path: Path) -> None:
        import runpy

        mod_path = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
        old = os.environ.pop("P5_RUN_LOG_DIR", None)
        try:
            mod = runpy.run_path(str(mod_path), run_name="p5_runner_probe2")
            assert mod["RUN_LOG_DIR"] == REPO_ROOT / "reports"
        finally:
            if old is not None:
                os.environ["P5_RUN_LOG_DIR"] = old

    def test_dry_run_writes_into_override_dir_only(self, tmp_path: Path) -> None:
        """End-to-end: a dry run with the override leaves no file behind in
        the production evidence dir."""
        import subprocess

        env = {**os.environ, "P5_RUN_LOG_DIR": str(tmp_path)}
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_p5_forward_test.py"),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert list(tmp_path.glob("p5_forward_test_*.json")), (
            "dry run must write its run log into the override dir"
        )


class TestManualDryRunQuarantine:
    """A manual ``--dry-run`` (no P5_RUN_LOG_DIR) must write its stub into
    the repo's sanctioned quarantine dir, never the live evidence stream.

    Live defect (2026-09-15): the smoke command defaulted into ``reports/``
    — the F8-H-01 hygiene guard condemned the stub and both live-tree
    gates went red. Root cause: P5_RUN_LOG_DIR isolation was pinned for
    test/CI callers only; the human CLI path had no safe default. Fix:
    dry-run smokes default to ``reports/health/p5-verify-stubs``
    (gitignored — the verifier's own quarantine since the 2026-09-08
    wave); P5_RUN_LOG_DIR still wins wherever a caller pins it; live
    supervised runs are untouched.
    """

    def test_manual_dry_run_writes_quarantine_not_reports(self) -> None:
        """End-to-end: bare ``--dry-run`` leaves reports/ byte-identical."""
        import subprocess

        env = {k: v for k, v in os.environ.items() if k != "P5_RUN_LOG_DIR"}
        reports = REPO_ROOT / "reports"
        before = set(reports.glob("p5_forward_test_*.json"))
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_p5_forward_test.py"),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        after = set(reports.glob("p5_forward_test_*.json"))
        assert after == before, (
            "manual dry-run dropped a stub into reports/: "
            f"{sorted(p.name for p in after - before)}"
        )
        quarantine = reports / "health" / "p5-verify-stubs"
        assert list(quarantine.glob("p5_forward_test_*.json")), (
            "dry-run stub must land in the sanctioned quarantine dir"
        )

    def test_dry_run_log_dir_default_is_quarantine(self) -> None:
        import runpy

        mod_path = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
        old = os.environ.pop("P5_RUN_LOG_DIR", None)
        try:
            mod = runpy.run_path(str(mod_path), run_name="p5_runner_probe3")
            assert mod["DRY_RUN_LOG_DIR"] == (
                REPO_ROOT / "reports" / "health" / "p5-verify-stubs"
            )
        finally:
            if old is not None:
                os.environ["P5_RUN_LOG_DIR"] = old

    def test_dry_run_log_dir_env_override_wins(self, tmp_path: Path) -> None:
        import runpy

        mod_path = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
        old = os.environ.get("P5_RUN_LOG_DIR")
        try:
            os.environ["P5_RUN_LOG_DIR"] = str(tmp_path)
            mod = runpy.run_path(str(mod_path), run_name="p5_runner_probe4")
            assert str(mod["DRY_RUN_LOG_DIR"]) == str(tmp_path)
        finally:
            if old is None:
                os.environ.pop("P5_RUN_LOG_DIR", None)
            else:
                os.environ["P5_RUN_LOG_DIR"] = old

    def test_live_run_log_dir_default_unchanged(self) -> None:
        """Live supervised runs still default to the evidence stream — the
        quarantine is a dry-run-only redirect, never a live-run one."""
        import runpy

        mod_path = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
        old = os.environ.pop("P5_RUN_LOG_DIR", None)
        try:
            mod = runpy.run_path(str(mod_path), run_name="p5_runner_probe5")
            assert mod["RUN_LOG_DIR"] == REPO_ROOT / "reports"
        finally:
            if old is not None:
                os.environ["P5_RUN_LOG_DIR"] = old

    def test_guard_never_scans_the_quarantine(self, tmp_path, monkeypatch) -> None:
        """Self-proof: stubs parked in the sanctioned quarantine dir can
        never trip the hygiene guard — the guard scans ``reports/`` top
        level only, and the quarantine lives one level deeper."""
        import importlib.util
        import json

        guard_path = REPO_ROOT / "scripts" / "check_repo_hygiene.py"
        spec = importlib.util.spec_from_file_location(
            "check_repo_hygiene_probe_q", guard_path
        )
        assert spec is not None and spec.loader is not None
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)

        reports = tmp_path / "reports"
        quarantine = reports / "health" / "p5-verify-stubs"
        quarantine.mkdir(parents=True)
        stub = quarantine / "p5_forward_test_20260915_020551.json"
        stub.write_text(
            json.dumps(
                {
                    "metadata": {
                        "phase_gate": "P5",
                        "script": "scripts/run_p5_forward_test.py",
                        "dry_run": True,
                    },
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        assert guard._p5_dry_run_stubs() == []


class TestTestDataIsolation:
    """The pytest process must never bind production data files."""

    def test_sqlite_db_path_is_private_temp(self) -> None:
        env_db = os.environ.get("SQLITE_DB_PATH", "")
        assert env_db, "conftest must pin SQLITE_DB_PATH for the suite"
        assert "loats-test-data-" in env_db
        assert not Path(env_db).is_relative_to(REPO_ROOT)

    def test_audit_log_path_is_private_temp(self) -> None:
        env_audit = os.environ.get("AUDIT_LOG_PATH", "")
        assert env_audit, "conftest must pin AUDIT_LOG_PATH for the suite"
        assert "loats-test-data-" in env_audit
        assert not Path(env_audit).is_relative_to(REPO_ROOT)

    def test_temp_dir_exists_and_is_outside_repo(self) -> None:
        d = tempfile.gettempdir()
        assert Path(os.environ["SQLITE_DB_PATH"]).is_relative_to(d)
