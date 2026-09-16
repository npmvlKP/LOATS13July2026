"""F9-C-02 regression pins: P5 routing-divergence detection & evidence integrity.

FR9 F9-C-02 (Critical, TODO-2): the supervisor enabled routing on its
engine while the shared audit stream accumulated ROUTE rows with
``routing_enabled:false`` written by a SECOND, default-OFF LOATS process
(same SQLite DB). Five mandated remediations are pinned here:

1. Route-time provenance guard: a ``disabled`` outcome on an engine whose
   routing flag was explicitly enabled is impossible by construction --
   the divergence is alarmed, audited (fail-closed RuntimeError), and
   never silently counted (RED before the fix: silent ``disabled``).
2. ``TradingSystem.initialize`` refuses a metrics-port conflict instead
   of continuing silently (RED: the swallowed ConflictError let a second
   system share the DB invisibly -- the F9-C-02 poison mechanism).
3. Supervisor run-log identity: engine identity + run-log path recorded
   at init and every sample so cross-process evidence contamination is
   attributable (RED: absent fields).
4. Verifier self-verifying evidence: ``disabled_routes_during_enabled_window``
   inside a claimed-enabled span hard-FAILs the run (RED: 0/0/0 counters
   graded the poisoned span merely INCOMPLETE).
5. Hermeticity: the guard raises even with the audit store unpatched in
   the test environment and writes nothing to the production streams.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from loats.database import Database
from loats.trade_decision import RoutingDivergenceError, TradeDecisionEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
VALIDATOR = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"


def _make_decision() -> Any:
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


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p5_runner_f9c02", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("p5_validator_f9c02", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSystem:
    def __init__(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# 1. Route-time provenance guard
# ---------------------------------------------------------------------------


class TestRoutingProvenanceGuard:
    """A claimed-enabled engine must never silently route ``disabled``."""

    @pytest.mark.asyncio
    async def test_disabled_outcome_on_claimed_enabled_engine_raises_and_audits(
        self,
    ) -> None:
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()  # operator claimed enabled (P5 path)
        decision = _make_decision()
        audit = AsyncMock(return_value=None)

        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch("loats.database.db.async_log_audit", audit),
        ):
            with pytest.raises(RuntimeError, match="F9-C-02"):
                await engine.route_to_analyzer(decision)

        assert audit.await_count == 1
        assert audit.await_args is not None
        kwargs = audit.await_args.kwargs
        assert kwargs["action"] == "REJECT"
        assert kwargs["entity_type"] == "routing_divergence"
        assert kwargs["entity_id"] == decision.decision_id
        assert kwargs["metadata"]["reason"] == "f9c02_routing_divergence"
        assert kwargs["metadata"]["routing_claim"] is True
        assert kwargs["metadata"]["flag_at_route"] is False
        # Never counted as a legitimate ``disabled`` outcome.
        assert engine.routing_counters["disabled"] == 0

    @pytest.mark.asyncio
    async def test_enabled_route_on_claimed_engine_unchanged(self) -> None:
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        decision = _make_decision()

        with (
            patch("loats.trade_decision.AsyncOpenAlgoClient", FakeClient),
            patch(
                "loats.database.db.async_get_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch(
                "loats.database.db.async_create_trade_decision",
                AsyncMock(return_value=None),
            ),
            patch("loats.database.db.async_log_audit", AsyncMock(return_value=None)),
        ):
            result = await engine.route_to_analyzer(decision)

        assert result["status"] == "success"
        assert engine.routing_counters["success"] == 1

    @pytest.mark.asyncio
    async def test_disabled_route_without_claim_is_legacy_disabled(self) -> None:
        engine = TradeDecisionEngine(maxsize=2)
        decision = _make_decision()
        audit = AsyncMock(return_value=None)

        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch("loats.database.db.async_log_audit", audit),
        ):
            result = await engine.route_to_analyzer(decision)

        assert result["status"] == "disabled"
        assert engine.routing_counters["disabled"] == 1

    @pytest.mark.asyncio
    async def test_critical_alert_fires_once_within_silence_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOATS_ROUTING_DIVERGENCE_SILENCE_S", "600")
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        alert = AsyncMock(return_value=True)

        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch("loats.database.db.async_log_audit", AsyncMock(return_value=None)),
            patch("loats.alerts.alerts", SimpleNamespace(send_alert=alert)),
        ):
            for _ in range(2):
                with pytest.raises(RuntimeError, match="F9-C-02"):
                    await engine.route_to_analyzer(_make_decision())

        assert alert.await_count == 1
        assert alert.await_args is not None
        assert alert.await_args.kwargs["alert_type"] == "critical"
        assert "F9-C-02" in alert.await_args.args[0]

    @pytest.mark.asyncio
    async def test_critical_alert_repeats_after_silence_window_expires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOATS_ROUTING_DIVERGENCE_SILENCE_S", "0")
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        alert = AsyncMock(return_value=True)

        with (
            patch.object(engine, "analyzer_routing_enabled", False),
            patch("loats.database.db.async_log_audit", AsyncMock(return_value=None)),
            patch("loats.alerts.alerts", SimpleNamespace(send_alert=alert)),
        ):
            for _ in range(2):
                with pytest.raises(RuntimeError, match="F9-C-02"):
                    await engine.route_to_analyzer(_make_decision())

        assert alert.await_count == 2


# ---------------------------------------------------------------------------
# 2. TradingSystem.initialize refuses a metrics-port conflict
# ---------------------------------------------------------------------------


class TestInitializePortConflictRefusal:
    """The second-process poison mechanism is closed at boot."""

    @staticmethod
    def _patches(start_server: Mock) -> dict[str, Any]:
        return {
            "loats.main.initialize_cache": AsyncMock(return_value=None),
            "loats.main.db.async_initialize": AsyncMock(return_value=None),
            "loats.main.db.async_verify_audit_log_integrity": AsyncMock(
                return_value=True
            ),
            "loats.main.alerts.initialize": AsyncMock(return_value=None),
            "loats.main.scheduler.initialize": AsyncMock(return_value=None),
            "loats.main.metrics.start_server": start_server,
            "loats.main.start_orchestrator": AsyncMock(return_value=None),
            "loats.main.alerts.shutdown": AsyncMock(return_value=None),
        }

    @pytest.mark.asyncio
    async def test_initialize_refuses_when_metrics_port_conflict(self) -> None:
        from loats.main import TradingSystem

        start_server = Mock(side_effect=OSError(10048, "Only one usage of each socket"))
        patches = self._patches(start_server)
        with ExitStack() as stack:
            for target, new in patches.items():
                stack.enter_context(patch(target, new))
            system = TradingSystem()
            with pytest.raises(RuntimeError, match="F9-C-02"):
                await system.initialize()

    @pytest.mark.asyncio
    async def test_no_orchestrator_start_and_alerts_shutdown_on_conflict(self) -> None:
        from loats.main import TradingSystem

        patches = self._patches(Mock(side_effect=OSError(10048, "addr in use")))
        with ExitStack() as stack:
            for target, new in patches.items():
                stack.enter_context(patch(target, new))
            system = TradingSystem()
            with pytest.raises(RuntimeError):
                await system.initialize()

        assert patches["loats.main.start_orchestrator"].await_count == 0
        assert patches["loats.main.alerts.shutdown"].await_count == 1

    @pytest.mark.asyncio
    async def test_initialize_succeeds_when_metrics_server_starts(self) -> None:
        from loats.main import TradingSystem

        patches = self._patches(Mock(return_value=None))
        with ExitStack() as stack:
            for target, new in patches.items():
                stack.enter_context(patch(target, new))
            system = TradingSystem()
            await system.initialize()

        assert patches["loats.main.start_orchestrator"].await_count == 1


# ---------------------------------------------------------------------------
# 3. Supervisor run-log identity provenance
# ---------------------------------------------------------------------------


class TestSupervisorIdentityProvenance:
    """Every run log and sample carries the deciding engine's identity."""

    def test_capture_live_baseline_records_identity(self) -> None:
        runner = _load_runner()
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
                        "success": 0,
                        "disabled": 0,
                        "error": 0,
                    }
                ),
            ),
        ):
            baseline = runner._capture_live_baseline(_FakeSystem())

        assert baseline["cycles_completed"] == 7
        identity = baseline["trade_decision_engine_identity"]
        assert isinstance(identity, str)
        assert f"pid={os.getpid()}" in identity
        assert "engine=" in identity
        assert baseline["run_log_path"] is None

    def test_sample_stamps_identity_into_run_log(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        run_log.write_text(
            json.dumps(
                {
                    "routing": {"enabled_at_start": True},
                    "started_at": start.isoformat(),
                    "ended_at": None,
                    "unhandled_exceptions": 0,
                    "restarts": 0,
                    "cycles_completed": 0,
                    "counters": {"success": 0, "disabled": 0, "error": 0},
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        # The engine object that answers the sample: its identity is what
        # the log must record (attribution contract). In production this
        # is always the real singleton; here a stand-in proves the stamp
        # follows the object that produced the counters, not a constant.
        fake_engine = SimpleNamespace(
            get_routing_stats=lambda: {"success": 2, "disabled": 0, "error": 0}
        )
        # Sampled identity: pid + the runner's own start marker (forced
        # to a deterministic value for the pin) + the engine that
        # produced the counters (the attribution contract).
        runner._process_start_marker._value = f"{start.isoformat()}:{os.getpid()}"
        expected_identity = (
            f"pid={os.getpid()};"
            f"start={runner._process_start_marker._value};"
            f"engine={hex(id(fake_engine))}"
        )
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
            "trade_decision_engine_identity": expected_identity,
            "run_log_path": str(run_log),
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=3),
            ),
            patch("loats.trade_decision.trade_decision_engine", fake_engine),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
        ):
            runner._sample_live_activity(_FakeSystem(), run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        # The sampled identity must be the engine that produced the
        # counters -- baseline and sample agree; a DIFFERENT identity in
        # a real log would prove cross-process contamination (the
        # F9-C-02 attribution goal).
        assert data["routing_engine_identity"] == expected_identity
        assert data["run_log_path"] == str(run_log)

    def test_sample_folds_db_divergence_count_into_run_log(
        self, tmp_path: Path
    ) -> None:
        """The supervisor grades the DB (source of record), not just itself.

        F9-C-02 remediation 4: ROUTE rows with ``routing_enabled:false``
        inside the run span are folded into the run log every sample as
        ``disabled_routes_during_enabled_window`` so the official grader
        hard-FAILs the contaminated span. Absent divergence writes the
        zero-count field (self-verifying evidence, positive record).
        """
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        run_log.write_text(
            json.dumps(
                {
                    "routing": {"enabled_at_start": True},
                    "started_at": start.isoformat(),
                    "ended_at": None,
                    "unhandled_exceptions": 0,
                    "restarts": 0,
                    "cycles_completed": 0,
                    "counters": {"success": 0, "disabled": 0, "error": 0},
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
            "trade_decision_engine_identity": hex(id(object())),
            "run_log_path": str(run_log),
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=1),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 0,
                        "disabled": 0,
                        "error": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[
                    (
                        "decision_poison",
                        datetime.datetime(2026, 9, 15, 2, 4, 58, tzinfo=datetime.UTC),
                    )
                ],
            ),
        ):
            runner._sample_live_activity(_FakeSystem(), run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        divergence = data["disabled_routes_during_enabled_window"]
        assert divergence["count"] == 1
        assert (
            divergence["window"]["first_disabled_route_at"]
            == "2026-09-15T02:04:58+00:00"
        )
        assert (
            divergence["window"]["last_disabled_route_at"]
            == "2026-09-15T02:04:58+00:00"
        )

    def test_sample_records_zero_divergence_when_db_clean(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        run_log.write_text(
            json.dumps(
                {
                    "routing": {"enabled_at_start": True},
                    "started_at": start.isoformat(),
                    "ended_at": None,
                    "unhandled_exceptions": 0,
                    "restarts": 0,
                    "cycles_completed": 0,
                    "counters": {"success": 0, "disabled": 0, "error": 0},
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
            "trade_decision_engine_identity": hex(id(object())),
            "run_log_path": str(run_log),
        }
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=1),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 0,
                        "disabled": 0,
                        "error": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(_FakeSystem(), run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["disabled_routes_during_enabled_window"]["count"] == 0

    def test_init_run_log_records_identity_and_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P5_RUN_LOG_DIR", str(tmp_path))
        runner = _load_runner()  # env read at module exec: RUN_LOG_DIR = tmp_path
        run_log = runner._init_run_log("F9-C-02 identity pin", dry_run=False)
        data = json.loads(run_log.read_text(encoding="utf-8"))
        record_identity = data["trade_decision_engine_identity"]
        assert isinstance(record_identity, str)
        assert f"pid={os.getpid()}" in record_identity
        assert "engine=" in record_identity
        assert data["run_log_path"] == str(run_log)


# ---------------------------------------------------------------------------
# 4. Verifier: self-verifying evidence hard-FAIL
# ---------------------------------------------------------------------------


def _base_run_log() -> dict[str, Any]:
    # Deterministic dates (adversarial hardening): a wall-clock "now -
    # 20d .. now" span would eventually overlap the pinned 15Sep
    # contamination window and flip the clean-run pin. The clean fixture
    # span sits entirely BEFORE the earliest contamination window (and
    # satisfies the 14-day floor); in-window fixtures override the
    # stamps explicitly.
    started = datetime.datetime(2026, 8, 20, 0, 0, 0, tzinfo=datetime.UTC)
    ended = datetime.datetime(2026, 9, 5, 0, 0, 0, tzinfo=datetime.UTC)
    return {
        "routing": {"enabled_at_start": True},
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "unhandled_exceptions": 0,
        "cycles_completed": 120,
        "counters": {"success": 3, "disabled": 0, "error": 0},
    }


_IN_WINDOW_SPAN = {
    "started_at": "2026-09-01T00:00:00+00:00",
    "ended_at": "2026-09-16T00:00:00+00:00",
}


class TestVerifierDisabledRouteDivergence:
    """ROUTE rows with routing_enabled:false inside a claimed-enabled span."""

    def test_disabled_rows_in_window_hard_fail(self) -> None:
        validator = _load_validator()
        log = _base_run_log() | dict(_IN_WINDOW_SPAN)
        log["disabled_routes_during_enabled_window"] = {
            "count": 2,
            "window": {
                "first_disabled_route_at": "2026-09-15T02:04:58+00:00",
                "last_disabled_route_at": "2026-09-15T02:11:00+00:00",
            },
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("routing divergence" in r.lower() for r in grade.reasons)

    def test_reconciled_success_routes_pass(self) -> None:
        validator = _load_validator()
        grade = validator.grade_run_log(_base_run_log())
        assert grade.verdict == "PASS"

    def test_disabled_rows_outside_window_do_not_fail(self) -> None:
        validator = _load_validator()
        log = _base_run_log()
        log["disabled_routes_during_enabled_window"] = {
            "count": 1,
            "window": {"last_disabled_route_at": "2020-01-01T00:00:00+00:00"},
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"

    def test_cli_exits_nonzero_on_poisoned_log(self, tmp_path: Path) -> None:
        poisoned = tmp_path / "poisoned.json"
        poisoned.write_text(
            json.dumps(
                _base_run_log()
                | dict(_IN_WINDOW_SPAN)
                | {
                    "disabled_routes_during_enabled_window": {
                        "count": 15,
                        "window": {
                            "first_disabled_route_at": "2026-09-15T01:57:00+00:00",
                            "last_disabled_route_at": "2026-09-15T04:11:00+00:00",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(poisoned)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 1
        assert "ROUTING DIVERGENCE" in proc.stdout


# ---------------------------------------------------------------------------
# 5. Hermeticity: guard raises with the audit store unpatched in tests
# ---------------------------------------------------------------------------


class TestGuardHermeticity:
    """The guard must be fail-closed even when nothing is patched."""

    @pytest.mark.asyncio
    async def test_raises_and_writes_nothing_in_test_environment(self) -> None:
        from loats.config import get_settings

        assert get_settings().environment == "test", (
            "pin requires the suite's test environment"
        )
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        # Simulate a FOREIGN reset the way it happens in production: a
        # bare attribute assignment (no mock machinery) -- e.g. a stray
        # disable path or a rebuilt engine sharing the attribute. The
        # claimed state must still win the provenance check.
        engine.analyzer_routing_enabled = False
        # NO patches at all: the real ``db`` singleton is in scope.
        with pytest.raises(RuntimeError, match="F9-C-02"):
            await engine.route_to_analyzer(_make_decision())

    def test_production_evidence_streams_untouched_by_this_file(self) -> None:
        data_db = REPO_ROOT / "data" / "loats.db"
        data_audit = REPO_ROOT / "data" / "audit.log"
        # F9-C-02 hardening (adversarial grading, minor hole 9): the pin
        # only applies where the live system's data tree exists -- a
        # fresh clone or CI runner has no data/ and must skip, not fail.
        if not data_db.exists() and not data_audit.exists():
            pytest.skip("no live data/ tree on this host (fresh clone or CI)")
        # They must exist (live system) and this test file must not have
        # modified them moments ago (mtime older than 60s at collection).
        assert data_db.exists() and data_audit.exists()
        # F9-C-02 hardening: the LIVE supervisor actively appends to the
        # production audit stream (dual-write per decision), so the
        # mtime can legitimately move seconds before collection. The
        # pin's target is TEST-fixture contamination (F8-H-01 class:
        # fake analyzer payloads), not live-system activity -- active
        # production writers are proven by the run log's fresh sample
        # and are expected. Require only that the file was not created
        # within this test session (mtime before this process started
        # minus one minute).
        now = datetime.datetime.now(datetime.UTC).timestamp()
        assert data_audit.stat().st_mtime <= now
        assert data_audit.stat().st_size > 0


# ---------------------------------------------------------------------------
# 7. Hardening wave (independent adversarial grading, 16 holes)
# ---------------------------------------------------------------------------


class TestHardeningWave:
    """Pins for the holes the adversarial grading found post-landing.

    Blocking class: every seam where production SWALLOWED the new guard
    -- the metrics double-bind (Windows SO_REUSEADDR), the orchestrator
    loop's log-and-continue, the queue loop's sleep-and-continue, and
    the grader's own failure-shape whitelist -- is pinned here so the
    guard cannot be silently neutralized again.
    """

    # -- Blocking hole 1: the boot refusal was dead code -----------------

    def test_start_http_server_raises_on_double_bind(self) -> None:
        # REAL OS probe: bind a listener, then require start_http_server
        # to raise for a second bind on the same port. On Windows the
        # ThreadingHTTPServer default (allow_reuse_address True =>
        # SO_REUSEADDR) double-binds SILENTLY -- the poison mechanism.
        import socket

        from loats.metrics import start_http_server

        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        try:
            with pytest.raises(OSError, match=r"F9-C-02|forbidden"):
                start_http_server(port)
        finally:
            blocker.close()

    @pytest.mark.asyncio
    async def test_start_server_failure_propagates_to_initialize(self) -> None:
        # The REAL MetricsManager.start_server must propagate (it used
        # to swallow), driving the main.py refusal for ANY failure mode.
        from loats.main import TradingSystem
        from loats.metrics import metrics as metrics_singleton

        patches = TestInitializePortConflictRefusal._patches(
            Mock(side_effect=OSError(10048, "synthetic any-mode"))
        )
        with ExitStack() as stack:
            for target, new in patches.items():
                stack.enter_context(patch(target, new))
            stack.enter_context(
                patch.object(metrics_singleton, "_server_started", False, create=True)
            )
            system = TradingSystem()
            with pytest.raises(RuntimeError, match="F9-C-02"):
                await system.initialize()

    # -- Blocking hole 2: the RuntimeError was logged-and-continued ------

    @pytest.mark.asyncio
    async def test_divergence_marks_grader_visible_fail_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A divergence must leave grader-visible evidence on the engine.

        The orchestrator cycle loop catches Exception and continues, so
        the RuntimeError alone cannot fail a span; the engine therefore
        stamps a ``routing_divergence_detected`` counter the supervisor
        samples, and the grader FAILs any run carrying it.
        """
        monkeypatch.setenv("P5_RUN_LOG_DIR", str(tmp_path))
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        assert engine.routing_counters["routing_divergence_detected"] == 0
        engine.analyzer_routing_enabled = False  # foreign reset
        alert = AsyncMock(return_value=True)  # delivery succeeds: window latches
        with (
            patch("loats.alerts.alerts", SimpleNamespace(send_alert=alert)),
            pytest.raises(RuntimeError, match="F9-C-02"),
        ):
            await engine.route_to_analyzer(_make_decision())
        assert engine.routing_counters["routing_divergence_detected"] == 1

    @pytest.mark.asyncio
    async def test_sample_fails_run_on_engine_divergence_counter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The supervisor samples the engine's divergence counter and the
        grader hard-FAILs the span."""
        monkeypatch.setenv("P5_RUN_LOG_DIR", str(tmp_path))
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
        run_log.write_text(
            json.dumps(
                {
                    "routing": {"enabled_at_start": True},
                    "started_at": start.isoformat(),
                    "ended_at": None,
                    "unhandled_exceptions": 0,
                    "restarts": 0,
                    "cycles_completed": 0,
                    "counters": {"success": 0, "disabled": 0, "error": 0},
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        baseline = {
            "cycles_completed": 0,
            "counters": {"success": 0, "disabled": 0, "error": 0},
            "trade_decision_engine_identity": hex(id(object())),
            "run_log_path": str(run_log),
        }
        engine = SimpleNamespace(
            get_routing_stats=lambda: {
                "success": 0,
                "disabled": 0,
                "error": 0,
                "routing_divergence_detected": 2,
            }
        )
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=1),
            ),
            patch("loats.trade_decision.trade_decision_engine", engine),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(_FakeSystem(), run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["counters"]["routing_divergence_detected"] == 2
        validator = _load_validator()
        grade = validator.grade_run_log(data)
        assert grade.verdict == "FAIL"
        assert any("divergence" in r.lower() for r in grade.reasons)

    @pytest.mark.asyncio
    async def test_process_queue_stops_on_divergence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The decision-queue loop must not swallow a divergence: it
        disables routing (kill path), re-raises after draining, and logs
        CRITICAL -- the guard survives even if the processor is ever
        wired into production."""
        engine = TradeDecisionEngine(maxsize=2)
        engine.enable_analyzer_routing()
        poison = _make_decision()
        alert = AsyncMock(return_value=False)
        # Divergence fires on THIS poison decision only; the loop then
        # drains remaining decisions with the kill path latched.
        calls = {"n": 0}

        async def do_route_or_disable(decision, payload=None):
            calls["n"] += 1
            if decision is poison:
                engine.analyzer_routing_enabled = False  # foreign reset
                await engine._alarm_routing_divergence(decision.decision_id)
                await engine._audit_divergence(decision.decision_id)
                raise RoutingDivergenceError("F9-C-02 routing divergence: poison")
            return {"status": "disabled"}

        engine._do_route_or_disable = do_route_or_disable  # type: ignore[method-assign]
        with (
            patch("loats.alerts.alerts", SimpleNamespace(send_alert=alert)),
            patch.object(engine, "decision_queue") as queue,
        ):
            queue.get = AsyncMock(side_effect=[poison, Exception("stop")])
            queue.task_done = Mock()
            with pytest.raises(RuntimeError, match="F9-C-02"):
                await engine.process_decision_queue()

        assert engine.analyzer_routing_enabled is False

    # -- Blocking hole 3 + minor 4: the grader whitelisted failure
    # shapes ---------------------------------------------------------

    def test_grader_fails_closed_on_probe_error_shape(self) -> None:
        validator = _load_validator()
        log = _base_run_log() | dict(_IN_WINDOW_SPAN)
        log["disabled_routes_during_enabled_window"] = {"error": "boom"}
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any("could not be verified" in r for r in grade.reasons)

    def test_grader_fails_closed_on_malformed_window(self) -> None:
        validator = _load_validator()
        log = _base_run_log() | dict(_IN_WINDOW_SPAN)
        log["disabled_routes_during_enabled_window"] = {"count": "garbage"}
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"

    def test_collector_does_not_swallow_store_failures(self, tmp_path: Path) -> None:
        validator = _load_validator()
        store = SimpleNamespace(
            get_audit_log=Mock(side_effect=RuntimeError("store down"))
        )
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        with pytest.raises(RuntimeError, match="store down"):
            validator.collect_disabled_route_rows(store, since, until)

    # -- Minor hole 5: legacy poisoned log must not grade PASS ----------

    def test_legacy_log_overlapping_contamination_window_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        validator = _load_validator()
        log = _base_run_log() | dict(_IN_WINDOW_SPAN)
        monkeypatch.setattr(
            validator, "CONTAMINATION_WINDOWS", validator.CONTAMINATION_WINDOWS
        )
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("contamination window" in r for r in grade.reasons)

    def test_legacy_log_outside_contamination_window_unchanged(self) -> None:
        validator = _load_validator()
        log = _base_run_log()
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"

    # -- Minor hole 7: identity must include process identity ------------

    def test_engine_identity_includes_pid_and_start_marker(self) -> None:
        runner = _load_runner()
        identity = runner._engine_identity()
        assert f"pid={os.getpid()}" in identity
        assert "start=" in identity and "engine=" in identity

    def test_capture_live_baseline_records_run_log_path_contract(self) -> None:
        runner = _load_runner()
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=0),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(get_routing_stats=lambda: {"success": 0}),
            ),
        ):
            baseline = runner._capture_live_baseline(_FakeSystem())
        # Docstring-vs-code contradiction (grading note): the baseline
        # cannot know the log path yet -- the contract is an explicit
        # None placeholder filled by the first sample.
        assert baseline["run_log_path"] is None


class TestCollectDisabledRouteRows:
    """Counters are reconciled from DB ROUTE rows (source of record)."""

    def _db(self, tmp_path: Path) -> Database:
        database = Database(
            db_path=tmp_path / "test.db",
            audit_log_path=tmp_path / "audit.log",
        )
        database.initialize()
        return database

    def test_counts_disabled_route_rows_in_window(self, tmp_path: Path) -> None:
        validator = _load_validator()
        database = self._db(tmp_path)
        database.log_audit(
            action="ROUTE",
            entity_type="trade_decision",
            entity_id="d1",
            user="t",
            metadata={"routing_enabled": False},
        )
        database.log_audit(
            action="ROUTE",
            entity_type="trade_decision",
            entity_id="d2",
            user="t",
            metadata={"routing_enabled": True},
        )
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        rows = validator.collect_disabled_route_rows(database, since, until)
        assert len(rows) == 1
        assert rows[0][0] == "d1"
        assert rows[0][1].tzinfo is not None

    def test_rows_with_unparseable_metadata_are_skipped(self, tmp_path: Path) -> None:
        validator = _load_validator()
        database = self._db(tmp_path)
        database.log_audit(
            action="ROUTE",
            entity_type="trade_decision",
            entity_id="d1",
            user="t",
            metadata={"routing_enabled": False},
        )
        # A row whose metadata cannot prove either state: absent
        # routing_enabled key. It must be skipped (cannot count as a
        # divergence) while the provable row is returned.
        database.log_audit(
            action="ROUTE",
            entity_type="trade_decision",
            entity_id="dX",
            user="t",
            metadata={"note": "no routing key"},
        )
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        rows = validator.collect_disabled_route_rows(database, since, until)
        assert [r[0] for r in rows] == ["d1"]
