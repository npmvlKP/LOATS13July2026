"""Tests for F8-H-01 remediation: P5 analyzer-routing conformance.

Covers the F8-H-01 Recommended Tests:
1. Enabled path: real HTTP (mock transport) fires AND a ROUTE audit row
   with the routing outcome exists per decision.
2. Disabled path: no HTTP call, audited ``disabled`` status, decision
   persisted.
3. Error path: propagates without fabrication AND the error outcome is
   audited.
4. ``get_decision_status`` reads real DB state (NOT_FOUND when absent).
5. P5 forward-test run-log validator grading (PASS/INCOMPLETE/FAIL).
6. P5 runner dry-run smoke (subprocess).
7. Persistence-failure tolerance (routing response still returned).
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
VALIDATOR = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"


def make_decision() -> Any:
    from loats.models import SignalType, TradeDecision

    return TradeDecision(
        symbol="NIFTY",
        decision_type=SignalType.BUY,
        composite_strength=0.7,
        timestamp=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC),
        entry_price=18000.0,
        quantity=25,
        stop_loss=17820.0,
        position_size_method="fixed_fraction",
        risk_percentage=0.02,
        var_analysis={"var_value": 0.0, "var_percent": 0.0, "method": "parametric"},
    )


class FakeClient:
    """Mock Analyzer transport returning a canned accepted response."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"status": "accepted", "analyzer_id": "t-1"}
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def place_analyzer_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return self.response


class FailingClient:
    """Mock Analyzer transport that always fails."""

    async def __aenter__(self) -> FailingClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def place_analyzer_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("simulated HTTP failure")


@pytest.fixture
def engine():
    from loats.trade_decision import TradeDecisionEngine

    return TradeDecisionEngine(maxsize=2)


def _last_audit_kwargs(audit: AsyncMock) -> dict[str, Any]:
    assert audit.await_args is not None, "async_log_audit never called"
    return dict(audit.await_args.kwargs)


class TestEnabledPath:
    """F8-H-01 Recommended Test 1: enabled path fires HTTP + audits."""

    @pytest.mark.asyncio
    async def test_enabled_http_fires_and_audits_outcome(self, engine) -> None:
        client = FakeClient()
        created = AsyncMock(return_value=True)
        audit = AsyncMock()
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: client),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_create_trade_decision", created),
            patch("loats.database.db.async_log_audit", audit),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "success"
        assert resp["analyzer_response"]["analyzer_id"] == "t-1"
        assert len(client.calls) == 1, "exactly one real HTTP request must fire"
        assert client.calls[0]["symbol"] == "NIFTY"
        assert created.await_count == 1, "decision row created when missing"
        kw = _last_audit_kwargs(audit)
        assert kw["action"] == "ROUTE"
        assert kw["entity_type"] == "trade_decision"
        assert kw["metadata"]["routing_outcome"]["status"] == "success"
        assert kw["metadata"]["routing_outcome"]["analyzer_response"] == (
            client.response
        )

    @pytest.mark.asyncio
    async def test_enabled_skips_duplicate_decision_row(self, engine) -> None:
        """Orchestrator pre-persists; engine must not INSERT twice."""
        decision = make_decision()
        created = AsyncMock(return_value=True)
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FakeClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=decision),
            ),
            patch("loats.database.db.async_create_trade_decision", created),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            resp = await engine.route_to_analyzer(decision)

        assert resp["status"] == "success"
        assert created.await_count == 0, "existing decision row must not be re-created"


class TestDisabledPath:
    """F8-H-01 Recommended Test 2: disabled path — no HTTP, audited."""

    @pytest.mark.asyncio
    async def test_disabled_no_http_and_audited(self, engine) -> None:
        created = AsyncMock(return_value=True)
        audit = AsyncMock()

        class Bomb:
            def __call__(self, *a: Any, **k: Any) -> None:
                raise AssertionError("HTTP client constructed while disabled")

        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch("loats.trade_decision.AsyncOpenAlgoClient", Bomb),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_create_trade_decision", created),
            patch("loats.database.db.async_log_audit", audit),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "disabled"
        assert resp["reason"] == "analyzer_routing_disabled"
        assert created.await_count == 1
        kw = _last_audit_kwargs(audit)
        assert kw["action"] == "ROUTE"
        assert kw["metadata"]["routing_outcome"]["status"] == "disabled"
        assert kw["metadata"]["routing_enabled"] is False


class TestErrorPath:
    """F8-H-01: error path propagates AND audits the error outcome."""

    @pytest.mark.asyncio
    async def test_error_propagates_and_audits(self, engine) -> None:
        audit = AsyncMock()
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FailingClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch(
                "loats.database.db.async_create_trade_decision",
                AsyncMock(return_value=True),
            ),
            patch("loats.database.db.async_log_audit", audit),
        ):
            with pytest.raises(RuntimeError, match="simulated HTTP failure"):
                await engine.route_to_analyzer(make_decision())

        kw = _last_audit_kwargs(audit)
        assert kw["action"] == "ROUTE"
        assert kw["metadata"]["routing_outcome"]["status"] == "error"
        assert "simulated HTTP failure" in kw["metadata"]["routing_outcome"]["error"]


class TestPersistenceTolerance:
    """Audit-store failure must not cascade into the routing result."""

    @pytest.mark.asyncio
    async def test_audit_failure_non_fatal(self, engine) -> None:
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FakeClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch(
                "loats.database.db.async_create_trade_decision",
                AsyncMock(return_value=True),
            ),
            patch(
                "loats.database.db.async_log_audit",
                AsyncMock(side_effect=RuntimeError("audit store down")),
            ),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "success", "routing result survives audit failure"

    @pytest.mark.asyncio
    async def test_decision_row_failure_non_fatal(self, engine) -> None:
        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "disabled"


class TestDecisionStatusReal:
    """get_decision_status must read persisted state, never fabricate."""

    @pytest.mark.asyncio
    async def test_status_not_found(self, engine) -> None:
        with patch(
            "loats.database.db.async_get_trade_decision",
            AsyncMock(return_value=None),
        ):
            resp = await engine.get_decision_status("decision_missing_1")

        assert resp["status"] == "NOT_FOUND"
        assert resp["decision_id"] == "decision_missing_1"
        assert resp["source"] == "database"

    @pytest.mark.asyncio
    async def test_status_returns_persisted_row(self, engine) -> None:
        decision = make_decision()
        with patch(
            "loats.database.db.async_get_trade_decision",
            AsyncMock(return_value=decision),
        ):
            resp = await engine.get_decision_status(decision.decision_id)

        assert resp["status"] == "PENDING"
        assert resp["symbol"] == "NIFTY"
        assert resp["decision_type"] == "BUY"
        assert resp["source"] == "database"


def _load_validator():
    spec = importlib.util.spec_from_file_location("p5_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestP5ValidatorGrading:
    """F8-H-01 Recommended Test 3: run-log validator verdicts."""

    @staticmethod
    def _fixture(
        span_days: int = 14, exc: int = 0, routing: bool = True, ended: bool = True
    ) -> dict[str, Any]:
        start = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        record: dict[str, Any] = {
            "routing": {"enabled_at_start": routing},
            "started_at": start.isoformat(),
            "ended_at": (
                (start + datetime.timedelta(days=span_days)).isoformat()
                if ended
                else None
            ),
            "unhandled_exceptions": exc,
            "restarts": 0,
            "cycles_completed": 5,
            "counters": {"success": 5, "disabled": 0, "error": 0},
        }
        return record

    def test_pass(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(span_days=14, exc=0))
        assert grade.verdict == "PASS", grade.reasons

    def test_incomplete_short_span(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(span_days=1, exc=0))
        assert grade.verdict == "INCOMPLETE"
        assert any("span" in r for r in grade.reasons)

    def test_incomplete_ongoing(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(ended=False))
        assert grade.verdict == "INCOMPLETE"
        assert any("in progress" in r for r in grade.reasons)

    def test_fail_on_exceptions(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(span_days=15, exc=2))
        assert grade.verdict == "FAIL"
        assert any("exception" in r for r in grade.reasons)

    def test_fail_on_routing_disabled(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(span_days=15, exc=0, routing=False))
        assert grade.verdict == "FAIL"
        assert any("routing" in r.lower() for r in grade.reasons)

    def test_fail_on_missing_started_at(self) -> None:
        mod = _load_validator()
        fixture = self._fixture(span_days=15, exc=0)
        del fixture["started_at"]
        grade = mod.grade_run_log(fixture)
        assert grade.verdict == "FAIL"
        assert any("started_at" in r for r in grade.reasons)


class TestP5ActivityGate:
    """A PASS without measured activity proves nothing (2026-09-05)."""

    @staticmethod
    def _fixture(
        cycles: int | None = 5, success: int = 5, legacy: bool = False
    ) -> dict[str, Any]:
        start = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        record: dict[str, Any] = {
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": (start + datetime.timedelta(days=15)).isoformat(),
            "unhandled_exceptions": 0,
            "restarts": 0,
        }
        if not legacy:
            record["cycles_completed"] = cycles
            record["counters"] = {
                "success": success,
                "disabled": 0,
                "error": 0,
            }
        return record

    def test_legacy_log_without_activity_fields_still_passes(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(legacy=True))
        assert grade.verdict == "PASS", grade.reasons
        assert grade.activity_recorded is None

    def test_zero_activity_fails_hard(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(cycles=0, success=0))
        assert grade.verdict == "FAIL"
        assert grade.activity_recorded is False
        assert any("no measured activity" in r for r in grade.reasons)

    def test_measured_activity_sets_signal(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(self._fixture(cycles=3, success=2))
        assert grade.verdict == "PASS", grade.reasons
        assert grade.activity_recorded is True

    def test_data_freshness_reported_when_sampled(self) -> None:
        mod = _load_validator()
        fixture = self._fixture()
        fixture["last_sampled_at"] = fixture["ended_at"]
        grade = mod.grade_run_log(fixture)
        assert grade.verdict == "PASS", grade.reasons
        assert grade.data_freshness is not None
        assert grade.data_freshness == "0s"

    def test_bad_counter_types_do_not_crash_grader(self) -> None:
        mod = _load_validator()
        fixture = self._fixture()
        fixture["counters"] = {"success": "not-an-int"}
        grade = mod.grade_run_log(fixture)
        assert grade.verdict == "FAIL"
        assert grade.activity_recorded is False


class TestP5RunnerSmoke:
    """Runner dry-run must exit 0 and produce a gradeable run log."""

    def test_dry_run_creates_run_log(self, tmp_path: Path) -> None:
        # F8-H-01 (2026-09-07): the smoke run must NOT drop its stub into
        # the production evidence directory. P5_RUN_LOG_DIR redirects the
        # runner's run-log writes to this test's private temp dir; the
        # ≈200 stub logs that accumulated in reports/ came from this test
        # globbing the real tree.
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
            env={**os.environ, "P5_RUN_LOG_DIR": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        logs = sorted(
            tmp_path.glob("p5_forward_test_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        assert logs, "dry-run must leave a run log under P5_RUN_LOG_DIR"
        data = json.loads(logs[-1].read_text(encoding="utf-8"))
        assert data["routing"]["enabled_at_start"] is True
        assert data["unhandled_exceptions"] == 0
        assert data["ended_at"] is not None

    def test_live_requires_ack(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
        assert result.returncode == 2
        assert "--ack-live-endpoint" in result.stderr


class TestOrchestratorPrePersistIdempotence:
    """Engine + orchestrator must not double-INSERT the decision row."""

    @pytest.mark.asyncio
    async def test_route_after_orchestrator_persist(self, engine) -> None:
        decision = make_decision()
        created = AsyncMock(return_value=True)
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FakeClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=decision),
            ),
            patch("loats.database.db.async_create_trade_decision", created),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            resp = await engine.route_to_analyzer(decision)

        assert resp["status"] == "success"
        assert created.await_count == 0


def test_module_importable_without_side_effects() -> None:
    """Importing the runner module must not start any run."""
    spec = importlib.util.spec_from_file_location("p5_runner_probe", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert callable(module.main)
    assert module.MIN_SPAN_DAYS == 14
    _ = asyncio


class TestRoutingCounters:
    """Routing counters must reflect resolved routing calls only."""

    @pytest.mark.asyncio
    async def test_success_increments_success_counter(self, engine) -> None:
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FakeClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_create_trade_decision", AsyncMock()),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "success"
        assert engine.get_routing_stats() == {
            "success": 1,
            "disabled": 0,
            "error": 0,
        }

    @pytest.mark.asyncio
    async def test_disabled_increments_disabled_counter(self, engine) -> None:
        with (
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_create_trade_decision", AsyncMock()),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            resp = await engine.route_to_analyzer(make_decision())

        assert resp["status"] == "disabled"
        stats = engine.get_routing_stats()
        assert stats["disabled"] == 1
        assert stats["success"] == 0

    @pytest.mark.asyncio
    async def test_error_increments_error_counter_and_raises(self, engine) -> None:
        with (
            patch.object(engine, "analyzer_routing_enabled", True),
            patch("loats.trade_decision.AsyncOpenAlgoClient", lambda: FailingClient()),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_create_trade_decision", AsyncMock()),
            patch("loats.database.db.async_log_audit", AsyncMock()),
        ):
            with pytest.raises(RuntimeError):
                await engine.route_to_analyzer(make_decision())

        stats = engine.get_routing_stats()
        assert stats["error"] == 1
        assert stats["success"] == 0


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p5_runner_mod", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSystem:
    def __init__(self) -> None:
        self.running = False


class TestSupervisorLiveSampling:
    """Supervisor folds live singleton counters into the run log."""

    @staticmethod
    def _write_run_log(path: Path) -> None:
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        record = {
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": None,
            "unhandled_exceptions": 0,
            "restarts": 0,
            "cycles_completed": 0,
            "cycles_completed_baseline": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
            "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
            "events": [],
        }
        path.write_text(json.dumps(record), encoding="utf-8")

    @pytest.mark.asyncio
    async def test_sample_folds_live_deltas_into_run_log(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        self._write_run_log(run_log)
        system = _FakeSystem()
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=7),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 4,
                        "disabled": 1,
                        "error": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
        ):
            runner._sample_live_activity(system, run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["cycles_completed"] == 7
        assert data["counters"] == {"success": 4, "disabled": 1, "error": 0}
        assert data["system_healthy"] == {
            "system_running": False,
            "kill_switch_active": False,
        }
        assert "last_sampled_at" in data

    @pytest.mark.asyncio
    async def test_counter_reset_mid_run_clamps_to_zero(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        self._write_run_log(run_log)
        system = _FakeSystem()
        baseline = {
            "cycles_completed": 5,
            "counters": {"success": 3, "disabled": 0, "error": 0},
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=2),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 1,
                        "disabled": 0,
                        "error": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
        ):
            runner._sample_live_activity(system, run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["cycles_completed"] == 0
        assert data["counters"]["success"] == 0

    @pytest.mark.asyncio
    async def test_supervise_stops_when_gate_passes(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        record = {
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": None,
            "unhandled_exceptions": 0,
            "restarts": 0,
            "cycles_completed": 12,
            "cycles_completed_baseline": 0,
            "counters": {"success": 5, "disabled": 0, "error": 0},
            "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
            "events": [],
        }
        run_log.write_text(json.dumps(record), encoding="utf-8")
        system = _FakeSystem()
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=12),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 5,
                        "disabled": 0,
                        "error": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
        ):
            unhandled = await runner._supervise_live(
                system, run_log, baseline, None, None
            )

        assert unhandled == 0
        data = json.loads(run_log.read_text(encoding="utf-8"))
        kinds = [event["kind"] for event in data["events"]]
        assert "gate_pass_detected" in kinds

    @pytest.mark.asyncio
    async def test_supervise_records_system_task_failure(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        self._write_run_log(run_log)
        system = _FakeSystem()
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
        }

        async def _die() -> None:
            raise RuntimeError("orchestrator exploded")

        task = asyncio.create_task(_die())
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=0),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {"success": 0, "disabled": 0, "error": 0}
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
        ):
            unhandled = await runner._supervise_live(
                system, run_log, baseline, None, task
            )

        assert unhandled == 1
        data = json.loads(run_log.read_text(encoding="utf-8"))
        kinds = [event["kind"] for event in data["events"]]
        assert "unhandled_exception" in kinds


class TestResumeBaseline:
    """Resume must continue the span without inflating measured activity."""

    def test_seamless_continuation_after_restart(self) -> None:
        runner = _load_runner()
        raw = {
            "cycles_completed": 10,
            "counters": {"success": 4, "disabled": 1, "error": 0},
        }
        baseline = runner._effective_resume_baseline(
            raw,
            logged_cycles=7,
            logged_counters={"success": 2, "disabled": 1, "error": 0},
        )
        assert baseline["cycles_completed"] == 3
        assert baseline["counters"] == {"success": 2, "disabled": 0, "error": 0}

    def test_counter_reset_never_inflates(self) -> None:
        runner = _load_runner()
        raw = {
            "cycles_completed": 2,
            "counters": {"success": 1, "disabled": 0, "error": 0},
        }
        baseline = runner._effective_resume_baseline(
            raw,
            logged_cycles=7,
            logged_counters={"success": 4, "disabled": 1, "error": 0},
        )
        assert baseline["cycles_completed"] == 0
        assert baseline["counters"] == {"success": 0, "disabled": 0, "error": 0}

    @staticmethod
    def _write_log(path: Path, *, dry_run: bool = False, ended: bool = True) -> None:
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        record = {
            "metadata": {"phase_gate": "P5", "dry_run": dry_run},
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": (
                (start + datetime.timedelta(hours=1)).isoformat() if ended else None
            ),
            "unhandled_exceptions": 0,
            "restarts": 0,
            "cycles_completed": 3,
            "cycles_completed_baseline": 0,
            "counters": {"success": 2, "disabled": 0, "error": 0},
            "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
            "events": [],
        }
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_resolve_explicit_target_rejects_ineligible(self, tmp_path: Path) -> None:
        runner = _load_runner()
        missing = tmp_path / "missing.json"
        assert runner._resolve_resume_target(missing) is None

        unreadable = tmp_path / "unreadable.json"
        unreadable.write_text("{not json", encoding="utf-8")
        assert runner._resolve_resume_target(unreadable) is None

        dry = tmp_path / "dry.json"
        self._write_log(dry, dry_run=True, ended=False)
        assert runner._resolve_resume_target(dry) is None

        ended = tmp_path / "ended.json"
        self._write_log(ended, ended=True)
        assert runner._resolve_resume_target(ended) is None

    def test_resolve_auto_picks_newest_eligible(self, tmp_path: Path) -> None:
        runner = _load_runner()
        original_dir = runner.RUN_LOG_DIR
        runner.RUN_LOG_DIR = tmp_path
        try:
            valid = tmp_path / "p5_forward_test_001.json"
            self._write_log(valid, ended=False)
            older_mtime = time.time() - 300
            os.utime(valid, (older_mtime, older_mtime))

            dry = tmp_path / "p5_forward_test_002.json"
            self._write_log(dry, dry_run=True, ended=False)
            ended = tmp_path / "p5_forward_test_003.json"
            self._write_log(ended, ended=True)

            assert runner._resolve_resume_target(None) == valid
        finally:
            runner.RUN_LOG_DIR = original_dir

    def test_select_default_prefers_live_run_over_newer_stub(
        self, tmp_path: Path
    ) -> None:
        """Default selection must surface the ongoing evidence run.

        A dry-run smoke stub with a newer mtime (e.g. one written by an
        external cron) must not shadow the live supervised run — exactly
        the mis-gradation observed live 2026-09-05 when ``--status``
        graded a dry-run stub while the evidence run was ongoing.
        """
        validator = _load_validator()
        live = tmp_path / "p5_forward_test_001.json"
        self._write_log(live, ended=False)
        older_mtime = time.time() - 300
        os.utime(live, (older_mtime, older_mtime))

        ended = tmp_path / "p5_forward_test_002.json"
        self._write_log(ended, ended=True)

        stub = tmp_path / "p5_forward_test_003.json"
        self._write_log(stub, dry_run=True, ended=False)

        assert validator.select_default_run_log(tmp_path) == live

    def test_select_default_prefers_fresh_sample_over_stale(
        self, tmp_path: Path
    ) -> None:
        """Among live-shape logs, a fresh sample outranks a newer mtime."""
        validator = _load_validator()
        now = datetime.datetime.now(datetime.UTC)

        def write_live(path: Path, sampled_at: datetime.datetime) -> None:
            record = {
                "metadata": {"phase_gate": "P5", "dry_run": False},
                "routing": {"enabled_at_start": True},
                "started_at": (now - datetime.timedelta(days=1)).isoformat(),
                "ended_at": None,
                "unhandled_exceptions": 0,
                "restarts": 0,
                "cycles_completed": 1,
                "cycles_completed_baseline": 0,
                "counters": {"success": 0, "disabled": 0, "error": 0},
                "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
                "last_sampled_at": sampled_at.isoformat(),
                "events": [],
            }
            path.write_text(json.dumps(record), encoding="utf-8")

        stale = tmp_path / "p5_forward_test_001.json"
        write_live(stale, now - datetime.timedelta(hours=2))
        fresh = tmp_path / "p5_forward_test_002.json"
        write_live(fresh, now - datetime.timedelta(seconds=30))
        newest_mtime = time.time()
        os.utime(stale, (newest_mtime, newest_mtime))
        older_mtime = newest_mtime - 600
        os.utime(fresh, (older_mtime, older_mtime))

        assert validator.select_default_run_log(tmp_path) == fresh

    def test_select_default_prefers_readable_over_unreadable(
        self, tmp_path: Path
    ) -> None:
        """Newest unreadable file must not hide the newest readable log."""
        validator = _load_validator()
        good = tmp_path / "p5_forward_test_001.json"
        self._write_log(good, ended=True)
        older_mtime = time.time() - 300
        os.utime(good, (older_mtime, older_mtime))

        junk = tmp_path / "p5_forward_test_002.json"
        junk.write_text("{not json", encoding="utf-8")

        assert validator.select_default_run_log(tmp_path) == good

    def test_select_default_empty_dir_returns_none(self, tmp_path: Path) -> None:
        validator = _load_validator()
        assert validator.select_default_run_log(tmp_path) is None

    def test_status_targets_live_run_not_newer_stub(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--status`` must grade the ongoing live run, not a newer stub.

        Runs in-process with ``RUN_LOG_DIR`` pointed at a tmp directory —
        status only reads, so it cannot spawn a supervisor as a side
        effect (unlike ``--resume``, see
        test_resume_cli_refuses_when_no_eligible_log).
        """
        runner: Any = _load_runner()
        live = tmp_path / "p5_forward_test_001.json"
        self._write_log(live, ended=False)
        older_mtime = time.time() - 300
        os.utime(live, (older_mtime, older_mtime))

        stub = tmp_path / "p5_forward_test_002.json"
        self._write_log(stub, dry_run=True, ended=False)

        original_dir = runner.RUN_LOG_DIR
        original_argv = sys.argv
        runner.RUN_LOG_DIR = tmp_path
        sys.argv = [str(RUNNER), "--status"]
        try:
            rc = runner.main()
        finally:
            runner.RUN_LOG_DIR = original_dir
            sys.argv = original_argv
        out = capsys.readouterr().out
        assert rc == 0
        assert str(live) in out
        assert str(stub) not in out

    def test_status_warns_when_live_sample_is_stale(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An ongoing log with no recent sample must say so, loudly."""
        runner: Any = _load_runner()
        live = tmp_path / "p5_forward_test_001.json"
        self._write_log(live, ended=False)
        record = json.loads(live.read_text(encoding="utf-8"))
        record["last_sampled_at"] = (
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=3)
        ).isoformat()
        live.write_text(json.dumps(record), encoding="utf-8")

        original_dir = runner.RUN_LOG_DIR
        original_argv = sys.argv
        runner.RUN_LOG_DIR = tmp_path
        sys.argv = [str(RUNNER), "--status"]
        try:
            rc = runner.main()
        finally:
            runner.RUN_LOG_DIR = original_dir
            sys.argv = original_argv
        out = capsys.readouterr().out
        assert rc == 0
        assert "WARNING" in out
        assert "no supervisor is writing" in out

    def test_resume_cli_refuses_when_no_eligible_log(self, tmp_path, capsys) -> None:
        """``--resume`` with no eligible log refuses with exit code 2.

        Runs in-process with ``RUN_LOG_DIR`` pointed at an empty directory.
        A bare ``--resume`` subprocess against the real ``reports/`` would
        RESUME (not refuse) on a gate host with an ongoing live run — the
        required production state — spawning a second live supervisor as a
        test side effect (observed live 2026-09-05: the stray supervisor
        ended the run under supervision).
        """
        runner: Any = _load_runner()
        original_dir = runner.RUN_LOG_DIR
        original_argv = sys.argv
        runner.RUN_LOG_DIR = tmp_path
        sys.argv = [str(RUNNER), "--resume"]
        try:
            rc = runner.main()
        finally:
            runner.RUN_LOG_DIR = original_dir
            sys.argv = original_argv
        assert rc == 2
        assert "no resumable run log" in capsys.readouterr().err

    def test_resume_cli_exit_code_contract_via_subprocess(self, tmp_path: Path) -> None:
        """``--resume --run-log <missing>`` refuses with exit code 2 through
        the real ``sys.exit(main())`` entry point.

        Side-effect-free by construction: a missing explicit target can
        never resolve to a live run log, so the subprocess cannot spawn a
        second supervisor on a gate host.
        """
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--resume",
                "--run-log",
                str(tmp_path / "missing.json"),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
        assert result.returncode == 2
        assert "resume target not found" in result.stderr


def _find_unrelated_alive_pid(max_probe: int = 10000) -> int | None:
    """Find an alive PID whose image is NOT this test's interpreter.

    Exercises the image-mismatch arm of the writer-liveness check: the PID
    is alive, but runs a different binary, so the guard must treat the
    recorded writer as dead (PID reuse) and allow takeover. Returns None
    when no such PID exists.
    """
    runner = _load_runner()
    current_pid = os.getpid()
    for pid in range(1, max_probe):
        if pid == current_pid:
            continue
        image = runner._process_image_path(pid)
        if image in ("", runner._PROCESS_IMAGE_UNREADABLE):
            continue  # free or uninspectable — not usable for this scenario
        if os.path.normcase(Path(image).resolve()) != runner._CURRENT_IMAGE_NORMCASE:
            return pid
    return None


class TestSingleWriterGuard:
    """Resume must never start a second writer on an actively-supervised log.

    2026-09-08: the logon watchdog (LOATS_P5_Resume) was found DISABLED
    while the evidence run sat abandoned; re-enabling it while an operator
    also resumes manually would let two supervisors fold interleaved
    counter baselines into one run log, corrupting the measured counters
    the P5 gate grades. Resume must refuse when a live writer holds the
    target log, and claim writer-ship atomically when it proceeds.
    """

    @staticmethod
    def _write_live_log(path: Path, supervisor_pid: int | None) -> None:
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2)
        record: dict[str, Any] = {
            "metadata": {"phase_gate": "P5", "dry_run": False},
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": None,
            "unhandled_exceptions": 0,
            "resume_refusal": None,
            "supervisor_pid": supervisor_pid,
            "restarts": 0,
            "cycles_completed": 3,
            "cycles_completed_baseline": 0,
            "counters": {"success": 2, "disabled": 0, "error": 0},
            "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
            "events": [],
        }
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_refuses_when_live_writer_holds_log(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_live.json"
        self._write_live_log(log, os.getpid())
        # This test process is a real, alive interpreter recorded as the
        # writer: refusing is the only safe answer.
        assert runner._resolve_resume_target(log) is None

    def test_takes_over_when_recorded_pid_is_dead(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_dead.json"
        self._write_live_log(log, 0)
        # PID 0 is a reserved system pseudo-process, never a supervisor.
        assert runner._resolve_resume_target(log) == log

    def test_takes_over_when_no_pid_recorded(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_legacy.json"
        self._write_live_log(log, None)
        assert runner._resolve_resume_target(log) == log

    def test_image_mismatch_pid_counts_as_dead_writer(self, tmp_path: Path) -> None:
        unrelated = _find_unrelated_alive_pid()
        if unrelated is None:
            pytest.skip("no alive unrelated-image PID found to probe with")
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_pidreuse.json"
        self._write_live_log(log, unrelated)
        assert runner._resolve_resume_target(log) == log

    def test_current_image_matches_own_process_image(self) -> None:
        """The comparator baseline must equal this process's REAL image.

        uv-venv trampolines make ``sys.executable`` differ from the actual
        running image; comparing against it misclassifies live writers as
        dead (fail-open). The baseline must be the queried self-image.
        """
        runner = _load_runner()
        own = runner._process_image_path(os.getpid())
        if own in ("", runner._PROCESS_IMAGE_UNREADABLE):
            pytest.skip("own process image unreadable on this host")
        assert runner._CURRENT_IMAGE_NORMCASE == os.path.normcase(Path(own).resolve())

    def test_claim_records_live_pid(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_claim.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] == os.getpid()

    def test_second_claimant_loses(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_race.json"
        self._write_live_log(log, None)
        # Winner records its own (alive) PID.
        assert runner._claim_run_log(log) is True
        # A second claimant must lose and must not overwrite the claim.
        assert runner._claim_run_log(log, refusal="second writer detected") is False
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] == os.getpid()
        assert data["ended_at"] is None

    def test_graceful_exit_clears_claim(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_release.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        runner._release_run_log(log)
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] is None

    def test_release_never_resurrects_ended_log(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_ended.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        data = json.loads(log.read_text(encoding="utf-8"))
        data["ended_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        log.write_text(json.dumps(data), encoding="utf-8")
        runner._release_run_log(log)
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["ended_at"] is not None
        assert data["supervisor_pid"] is None

    def test_resume_refusal_is_persisted_and_cleared(self, tmp_path: Path) -> None:
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_refusal.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        assert (
            runner._claim_run_log(
                log, refusal="second writer detected (operator resume)"
            )
            is False
        )
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["resume_refusal"] is not None
        # A later self-re-claim (same live PID) clears the stale refusal.
        assert runner._claim_run_log(log) is True
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["resume_refusal"] is None
        assert data["supervisor_pid"] == os.getpid()


def _spawn_same_image_child() -> tuple[Any, int, str]:
    """Spawn a live child on THIS interpreter image and return its identity.

    sys.executable on a venv is a launcher whose CHILD is the real
    interpreter; Popen on it would return the launcher (different image).
    Spawning the queried self image directly yields a genuine same-image
    process — a legitimate stand-in for a live supervisor.
    """
    runner = _load_runner()
    image = runner._current_process_image()
    proc = subprocess.Popen(
        [image, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    created = runner._process_creation_time(proc.pid)
    assert created is not None, "child creation time unreadable"
    return proc, proc.pid, created


class TestWriterIdentity:
    """Writer identity must survive PID recycling, and claims must be an
    OS-level lock, not a JSON read-modify-write (adversarial review
    2026-09-08, blocking findings 1 and 2).

    Finding 1: exact-image liveness matches ANY live same-image process;
    ~19 unrelated python processes share the base image on the gate host,
    so a recycled supervisor PID permanently blocks takeover of an
    in-span evidence run. Binding the claim to the writer's process
    creation time makes recycling detectable.
    Finding 2: two claimants can interleave read/write and both proceed;
    a lockfile held for the writer's lifetime (auto-released on death)
    closes the race deterministically.
    """

    @staticmethod
    def _write_live_log(
        path: Path,
        supervisor_pid: int | None,
        supervisor_started_at: str | None = None,
    ) -> None:
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2)
        record: dict[str, Any] = {
            "metadata": {"phase_gate": "P5", "dry_run": False},
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": None,
            "unhandled_exceptions": 0,
            "resume_refusal": None,
            "supervisor_pid": supervisor_pid,
            "supervisor_started_at": supervisor_started_at,
            "restarts": 0,
            "cycles_completed": 3,
            "cycles_completed_baseline": 0,
            "counters": {"success": 2, "disabled": 0, "error": 0},
            "counters_baseline": {"success": 0, "disabled": 0, "error": 0},
            "events": [],
        }
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_recycled_pid_same_image_allows_takeover(self, tmp_path: Path) -> None:
        """A recorded PID now held by a DIFFERENT same-image process is dead."""
        runner = _load_runner()
        proc, pid, created = _spawn_same_image_child()
        try:
            log = tmp_path / "p5_forward_test_recycled.json"
            # Simulate recycle: the PID is alive but its creation time
            # differs from the one the real writer recorded.
            recycled_ts = (
                datetime.datetime.fromisoformat(created) + datetime.timedelta(seconds=1)
            ).isoformat()
            self._write_live_log(log, pid, recycled_ts)
            assert runner._resolve_resume_target(log) == log
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_exact_identity_alive_writer_blocks(self, tmp_path: Path) -> None:
        """A recorded (pid, creation-time) pair that still matches reality
        is a live writer: resume must refuse."""
        runner = _load_runner()
        proc, pid, created = _spawn_same_image_child()
        try:
            log = tmp_path / "p5_forward_test_exact.json"
            self._write_live_log(log, pid, created)
            assert runner._resolve_resume_target(log) is None
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_lock_sidecar_blocks_concurrent_claim(self, tmp_path: Path) -> None:
        """The second claim must lose even when the recorded writer is dead:
        the sidecar lock (held for the first writer's lifetime) is the
        serialization point, not the JSON file."""
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_locked.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        # A foreign claimant arriving while the lock is held: the JSON
        # path alone would let it take over a dead writer's claim.
        foreign = runner._claim_run_log(
            log,
            refusal="second writer detected",
            identity=(424242, "2000-01-01T00:00:00.000000+00:00"),
        )
        assert foreign is False
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] == os.getpid()

    def test_lock_auto_released_on_death(self, tmp_path: Path) -> None:
        """A writer that dies holding the lock must not block its successor:
        the OS releases the lock, takeover re-locks and proceeds."""
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_deceased.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        # Simulate the writer's death: release our handle without the
        # graceful _release_run_log path (as a hard kill would).
        runner._ACTIVE_CLAIM.release()
        runner._ACTIVE_CLAIM = None
        assert runner._claim_run_log(log) is True

    def test_external_lock_holder_blocks_claim(self, tmp_path: Path) -> None:
        """A foreign process holding the sidecar lock blocks the claim."""
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_foreign.json"
        self._write_live_log(log, None)
        sidecar = tmp_path / "p5_forward_test_foreign.json.claim"
        fh = open(sidecar, "a+b")
        try:
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            assert runner._claim_run_log(log) is False
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            fh.close()
        assert runner._claim_run_log(log) is True

    def test_release_is_identity_scoped(self, tmp_path: Path) -> None:
        """Release clears only THIS writer's claim, never a successor's."""
        runner = _load_runner()
        log = tmp_path / "p5_forward_test_scoped.json"
        self._write_live_log(log, None)
        assert runner._claim_run_log(log) is True
        # Simulate a successor having taken over: the log records its pid.
        runner._update_run_log(log, {"supervisor_pid": 424242})
        runner._release_run_log(log)
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] == 424242  # foreign claim untouched
        # Our own recorded claim is still releasable.
        runner._update_run_log(log, {"supervisor_pid": os.getpid()})
        runner._release_run_log(log)
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["supervisor_pid"] is None

    def test_resolver_persists_refusal(self, tmp_path: Path) -> None:
        """A resolver-level refusal is persisted for --status visibility."""
        runner = _load_runner()
        proc, pid, created = _spawn_same_image_child()
        try:
            log = tmp_path / "p5_forward_test_persist.json"
            self._write_live_log(log, pid, created)
            assert runner._resolve_resume_target(log) is None
            data = json.loads(log.read_text(encoding="utf-8"))
            assert data["resume_refusal"] is not None
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_run_exit2_when_claim_refused(self, tmp_path: Path) -> None:
        """_run's enforcement point exits 2 when the claim is refused."""
        runner = _load_runner()
        proc, pid, created = _spawn_same_image_child()
        try:
            log = tmp_path / "p5_forward_test_run2.json"
            self._write_live_log(log, pid, created)
            rc = asyncio.run(
                runner._run(
                    dry_run=False, reason="guard probe", duration=None, resume_log=log
                )
            )
            assert rc == 2
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_free_pid_takeover_exercises_openprocess_error_path(
        self, tmp_path: Path
    ) -> None:
        """A verified-free PID (not reserved PID 0) exercises the real
        OpenProcess ERROR_INVALID_PARAMETER mapping to 'PID free'."""
        runner = _load_runner()
        free = next(
            (p for p in range(1, 100000) if runner._process_image_path(p) == ""),
            None,
        )
        if free is None:
            pytest.skip("no free PID found to probe with")
        log = tmp_path / "p5_forward_test_free.json"
        self._write_live_log(log, free)
        assert runner._resolve_resume_target(log) == log
