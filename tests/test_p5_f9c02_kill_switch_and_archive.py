"""F9-C-02 closure wave (2026-09-18): kill-switch verification + evidence archive.

FR9 F9-C-02's suggested resolution listed six items; the 15Sep wave landed
items 2-5, the 16Sep restart record executed item 6's span restart, and the
18Sep archive record discharges the deferred item 1 (INVALID-EVIDENCE
archival). Two gaps remained open and are pinned here:

1. CMP P5 gate: "include a Telegram kill-switch verification event". The
   supervisor now probes ``alerts.is_kill_switch_active()`` at supervision
   start (fresh AND resumed), records the outcome as run-log fields
   (``kill_switch_verified`` / ``kill_switch_active_at_start``) plus a
   ``kill_switch_verified`` / ``kill_switch_alarm`` event, and the grader
   FAIL-closes any ENDED run that cannot prove the emergency halt was
   operational and DISengaged at span start. Fail-closed by design: an
   unprovable kill switch is exactly what the finding forbids citing.
2. The poisoned 15Sep run log's INVALID-EVIDENCE archive record exists,
   cites the official grader's rc=1 verdict, and the grader's divergence
   hard-FAIL (proven live against the real artifact) stays pinned.

Hermeticity: the supervisor probe reads the real ``alerts`` singleton with
no credentials required (construction is env-free; only Telegram SENDS need
tokens), and a test-only env hook (``LOATS_KILL_SWITCH_ACTIVE_TEST=1``)
simulates an engaged switch without touching the singleton.

The poisoned run log itself is gitignored live-system residue
(``reports/*.json`` is supervisor-host quarantine), so the evidence pins
below grade a tracked verbatim snapshot of it
(``tests/fixtures/p5_run_log_20260912_150243_snapshot.json``,
programmatically projected from the artifact of record) instead of the
machine-local file -- a fresh checkout carries the full evidence chain.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
VALIDATOR = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
ARCHIVE_RECORD = (
    REPO_ROOT / "docs" / "audit-history" / "18Sep2026-F9C02-invalid-evidence-archive.md"
)
# Verbatim graded-field snapshot of the gitignored live artifact (written
# programmatically from reports/p5_forward_test_20260912_150243.json on the
# supervisor host); tracked so fresh checkouts can grade the same evidence.
POISONED_LOG_SNAPSHOT = (
    REPO_ROOT / "tests" / "fixtures" / "p5_run_log_20260912_150243_snapshot.json"
)


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p5_runner_f9c02_killswitch", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "p5_validator_f9c02_killswitch", VALIDATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _eligible_log() -> dict[str, Any]:
    """An otherwise fully-eligible ENDED run (14d+ span, measured activity).

    Dates pinned entirely BEFORE the documented contamination and outage
    windows so these fixtures grade the kill-switch criterion alone.
    """
    return {
        "routing": {"enabled_at_start": True},
        "started_at": "2026-08-01T00:00:00+00:00",
        "ended_at": "2026-08-16T00:00:00+00:00",
        "unhandled_exceptions": 0,
        "cycles_completed": 5000,
        "counters": {
            "success": 400,
            "disabled": 0,
            "error": 0,
            "routed_decisions": 400,
            "routing_divergence_detected": 0,
        },
        "disabled_routes_during_enabled_window": {
            "count": 0,
            "window": {
                "first_disabled_route_at": None,
                "last_disabled_route_at": None,
            },
        },
        "kill_switch_verified": True,
        "kill_switch_active_at_start": False,
    }


# ---------------------------------------------------------------------------
# 1. Supervisor probe + run-log verification record
# ---------------------------------------------------------------------------


class TestKillSwitchVerificationProbe:
    """The probe reads the real alert system and reports (verified, alarm)."""

    def test_probe_reports_verified_when_switch_disengaged(self) -> None:
        runner = _load_runner()
        # No patching: the real alerts singleton constructs env-free and
        # starts with the kill switch INACTIVE -- the production default.
        verified, alarm = runner._probe_kill_switch()
        assert verified is True
        assert alarm is False

    def test_probe_flags_engaged_switch(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        runner = _load_runner()
        engaged = SimpleNamespace(is_kill_switch_active=lambda: True)
        with patch("loats.alerts.alerts", engaged):
            verified, engaged_now = runner._probe_kill_switch()
        # The primitive ANSWERED (verified) -- but it reports ENGAGED,
        # which is itself span-voiding (the grader fails on engaged).
        assert verified is True
        assert engaged_now is True

    def test_probe_env_hook_simulates_engaged_switch(self) -> None:
        from unittest.mock import patch

        runner = _load_runner()
        env = {**os.environ, "LOATS_KILL_SWITCH_ACTIVE_TEST": "1"}
        with patch.dict(os.environ, env, clear=True):
            verified, engaged = runner._probe_kill_switch()
        assert verified is True
        assert engaged is True


class TestSupervisorRecordsVerification:
    """Supervision start (fresh, resumed, dry-run) records the event."""

    def test_record_verification_writes_fields_and_event(self, tmp_path: Path) -> None:
        import unittest.mock as mock

        runner = _load_runner()
        # _init_run_log derives its path from DRY_RUN_LOG_DIR, so patch
        # the module constant for a deterministic tmp_path target (never
        # the production quarantine dir).
        with mock.patch.object(runner, "DRY_RUN_LOG_DIR", tmp_path):
            run_log = runner._init_run_log("kill-switch verification pin", dry_run=True)
        runner._record_kill_switch_verification(run_log)
        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["kill_switch_verified"] is True
        assert data["kill_switch_active_at_start"] is False
        kinds = [event["kind"] for event in data["events"]]
        assert "kill_switch_verified" in kinds
        assert "kill_switch_alarm" not in kinds

    def test_record_verification_alarms_when_engaged(self, tmp_path: Path) -> None:
        import unittest.mock as mock

        runner = _load_runner()
        with mock.patch.object(runner, "DRY_RUN_LOG_DIR", tmp_path):
            run_log = runner._init_run_log("alarm pin", dry_run=True)
        env = {**os.environ, "LOATS_KILL_SWITCH_ACTIVE_TEST": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            runner._record_kill_switch_verification(run_log)
        data = json.loads(run_log.read_text(encoding="utf-8"))
        # The primitive ANSWERED (verified) and reports ENGAGED -- the
        # engagement is what alarms (and the grader fails the span on it).
        assert data["kill_switch_verified"] is True
        assert data["kill_switch_active_at_start"] is True
        kinds = [event["kind"] for event in data["events"]]
        assert "kill_switch_alarm" in kinds
        alarm = next(e for e in data["events"] if e["kind"] == "kill_switch_alarm")
        assert "ACTIVE" in alarm["detail"]

    def test_dry_run_records_kill_switch_verified_event(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
            env={**os.environ, "P5_RUN_LOG_DIR": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        logs = sorted(tmp_path.glob("p5_forward_test_*.json"))
        assert logs
        data = json.loads(logs[-1].read_text(encoding="utf-8"))
        assert data["kill_switch_verified"] is True
        kinds = [event["kind"] for event in data["events"]]
        assert "kill_switch_verified" in kinds

    def test_dry_run_records_alarm_when_switch_engaged(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
            env={
                **os.environ,
                "P5_RUN_LOG_DIR": str(tmp_path),
                "LOATS_KILL_SWITCH_ACTIVE_TEST": "1",
            },
        )
        assert result.returncode == 0, result.stderr
        logs = sorted(tmp_path.glob("p5_forward_test_*.json"))
        assert logs
        data = json.loads(logs[-1].read_text(encoding="utf-8"))
        # Answered-but-engaged: verified True, engagement alarms.
        assert data["kill_switch_verified"] is True
        assert data["kill_switch_active_at_start"] is True
        kinds = [event["kind"] for event in data["events"]]
        assert "kill_switch_alarm" in kinds


# ---------------------------------------------------------------------------
# 2. Grader: kill-switch proof is gate-mandatory (fail-closed)
# ---------------------------------------------------------------------------


class TestGraderKillSwitchCriterion:
    """An ENDED run without kill-switch proof cannot PASS (CMP P5 gate)."""

    def test_eligible_log_with_verification_passes(self) -> None:
        validator = _load_validator()
        grade = validator.grade_run_log(_eligible_log())
        assert grade.verdict == "PASS", grade.reasons

    def test_missing_verification_fails_ended_run(self) -> None:
        validator = _load_validator()
        log = _eligible_log()
        del log["kill_switch_verified"]
        del log["kill_switch_active_at_start"]
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any(
            "kill switch" in r.lower() or "kill-switch" in r.lower()
            for r in grade.reasons
        )

    def test_verification_failure_fails_ended_run(self) -> None:
        validator = _load_validator()
        log = _eligible_log() | {"kill_switch_verified": False}
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any(
            "kill switch" in r.lower() or "kill-switch" in r.lower()
            for r in grade.reasons
        )

    def test_engaged_switch_fails_even_if_verified_true(self) -> None:
        validator = _load_validator()
        log = _eligible_log() | {"kill_switch_active_at_start": True}
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("active" in r.lower() for r in grade.reasons)

    def test_ongoing_run_without_verification_stays_incomplete(self) -> None:
        validator = _load_validator()
        log = _eligible_log()
        log["ended_at"] = None
        del log["kill_switch_verified"]
        del log["kill_switch_active_at_start"]
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any(
            "kill switch" in r.lower() or "kill-switch" in r.lower()
            for r in grade.reasons
        )


# ---------------------------------------------------------------------------
# 3. INVALID-EVIDENCE archive record (deferred item 1, discharged 18Sep)
# ---------------------------------------------------------------------------


class TestInvalidEvidenceArchive:
    """The poisoned 15Sep run log has its dated INVALID-EVIDENCE record."""

    def test_archive_record_exists_and_declares_invalid_evidence(self) -> None:
        assert ARCHIVE_RECORD.exists(), (
            "the dated INVALID-EVIDENCE archive record must exist under "
            "docs/audit-history/"
        )
        text = ARCHIVE_RECORD.read_text(encoding="utf-8")
        assert "INVALID-EVIDENCE" in text
        assert "p5_forward_test_20260912_150243" in text

    def test_archive_record_cites_the_official_fail_verdict(self) -> None:
        text = ARCHIVE_RECORD.read_text(encoding="utf-8")
        assert "verify_p5_forward_test" in text
        assert "rc=1" in text or "exit 1" in text or "EXIT=1" in text
        # The exact divergence signature must be quoted, not paraphrased.
        assert "routing_enabled:false" in text
        assert "15" in text

    def test_official_grader_still_condemns_the_poisoned_log(self) -> None:
        """Live proof, re-run in-suite: the graded evidence FAILs rc=1.

        Grades the tracked verbatim snapshot of the artifact of record
        (hermetic across fresh checkouts; the gitignored live file is
        supervisor-host residue by contract).
        """
        assert POISONED_LOG_SNAPSHOT.is_file(), (
            "the tracked snapshot of the poisoned run log must stay in the "
            "tree (evidence of record projection; the archive record "
            "supplements it, it does not replace it)"
        )
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(POISONED_LOG_SNAPSHOT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=120,
        )
        assert proc.returncode == 1
        assert "ROUTING DIVERGENCE" in proc.stdout
        assert "VOID" in proc.stdout

    def test_poisoned_log_grades_fail_with_its_embedded_evidence(self) -> None:
        validator = _load_validator()
        data = json.loads(POISONED_LOG_SNAPSHOT.read_text(encoding="utf-8"))
        grade = validator.grade_run_log(data)
        assert grade.verdict == "FAIL"
        divergence_field = data["disabled_routes_during_enabled_window"]
        assert divergence_field["count"] == 15
        assert any("divergence" in r.lower() for r in grade.reasons)
