"""F9-M-03 audited-attempt semantics (ADR-006 Amendment 7).

Operator decision 2026-09-18: option (a) — the gateway-side
decision-telemetry intake stays deferred, and P5 decisional acceptance is
redefined so every honestly-resolved ROUTED ATTEMPT is the evidence.

Contracts pinned here (RED-first):

1. Single semantic source: ``TradeDecisionEngine.analyzer_intake_semantic``
   exposes the accepted semantic as machine-readable data.
2. Engine counting: ``routed_decisions`` increments exactly once per
   enabled route BEFORE any outcome exists — success and the designed
   gateway-404 error each count one attempt; the disabled path (engine
   flag off, non-claimed) counts none; attempts >= outcome total always.
3. Grader: ``counters["routed_decisions"]`` is the decisional metric.
   A post-semantic ended run with a zero attempt total while outcomes
   exist FAILs (ongoing: INCOMPLETE); legacy logs (no key) keep grading
   unchanged; the attempt total never whitewashes divergence.
4. Supervisor flow: the new counter folds into run logs through the
   existing delta machinery with no supervisor change (baseline capture
   + live sample), so resumed spans carry it too.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
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
    """Mock Analyzer transport that always fails (the gateway-404 class)."""

    async def __aenter__(self) -> FailingClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def place_analyzer_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("simulated gateway 404 (read-only semantic)")


@pytest.fixture
def engine():
    from loats.trade_decision import TradeDecisionEngine

    return TradeDecisionEngine(maxsize=2)


def _load_validator():
    spec = importlib.util.spec_from_file_location("p5_validator_f9m03", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_runner():
    spec = importlib.util.spec_from_file_location("p5_runner_f9m03", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestSemanticSource:
    """Contract 1: the accepted semantic lives as data on the engine."""

    def test_semantic_pinned_exact(self) -> None:
        from loats.trade_decision import TradeDecisionEngine

        assert TradeDecisionEngine.analyzer_intake_semantic == {
            "intake_semantic": "audited_attempt",
            "audited_attempt_outcomes": ["success", "disabled", "error"],
            "adr": "ADR-006 Amendment 7",
            "decision": "F9-M-03 option (a)",
        }

    def test_admitted_outcomes_match_counter_surface(self) -> None:
        """The admitted-outcome list can never drift from the counters."""
        from loats.trade_decision import TradeDecisionEngine

        semantic = TradeDecisionEngine.analyzer_intake_semantic
        admitted = set(semantic["audited_attempt_outcomes"])
        outcome_counters = admitted | {"routed_decisions"}
        counters = TradeDecisionEngine(maxsize=2).routing_counters
        assert outcome_counters <= set(counters), (
            "every admitted outcome and the attempt total must be a real counter"
        )
        assert "routing_divergence_detected" not in admitted, (
            "divergence is a void signal, never admitted evidence"
        )


class TestEngineAttemptCounting:
    """Contract 2: one attempt per enabled route, counted before outcomes."""

    @pytest.mark.asyncio
    async def test_success_counts_one_attempt(self, engine) -> None:
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
        assert engine.routing_counters["routed_decisions"] == 1

    @pytest.mark.asyncio
    async def test_designed_404_counts_one_attempt(self, engine) -> None:
        """The read-only-semantic error outcome IS an audited attempt."""
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
        assert stats["routed_decisions"] == 1
        assert stats["error"] == 1

    @pytest.mark.asyncio
    async def test_disabled_path_counts_no_attempt(self, engine) -> None:
        """Flag-off (non-claimed) resolves without any HTTP attempt."""
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
        assert engine.routing_counters["routed_decisions"] == 0
        assert engine.routing_counters["disabled"] == 1

    @pytest.mark.asyncio
    async def test_attempts_never_undercount_outcomes(self, engine) -> None:
        """Invariant: routed_decisions >= success + error on every path."""
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
            await engine.route_to_analyzer(make_decision())

            patcher = patch(
                "loats.trade_decision.AsyncOpenAlgoClient", lambda: FailingClient()
            )
            with patcher:
                with pytest.raises(RuntimeError):
                    await engine.route_to_analyzer(make_decision())

        stats = engine.get_routing_stats()
        assert stats["routed_decisions"] == 2
        assert stats["success"] + stats["error"] == 2

    def test_fresh_engine_carries_attempt_counter(self, engine) -> None:
        stats = engine.get_routing_stats()
        assert stats["routed_decisions"] == 0
        assert stats["routing_divergence_detected"] == 0


class TestGraderAuditedAttempt:
    """Contract 3: the official grader grades the audited-attempt semantic."""

    @staticmethod
    def _fixture(
        counters: dict[str, int],
        span_days: int = 14,
        ended: bool = True,
        cycles: int = 5,
    ) -> dict[str, Any]:
        # Span pinned entirely BEFORE the grader's documented
        # contamination windows (F9-C-02 hardening) and carrying the
        # clean-divergence field, exactly like a real supervisor log.
        start = datetime.datetime(2026, 8, 20, tzinfo=datetime.UTC)
        record: dict[str, Any] = {
            "routing": {"enabled_at_start": True},
            "started_at": start.isoformat(),
            "ended_at": (
                (start + datetime.timedelta(days=span_days)).isoformat()
                if ended
                else None
            ),
            "unhandled_exceptions": 0,
            "restarts": 0,
            "cycles_completed": cycles,
            "counters": counters,
            "disabled_routes_during_enabled_window": {"count": 0, "window": {}},
            # F9-C-02 closure (2026-09-18): kill-switch verification proof
            # (CMP P5 gate) -- present and disengaged on eligible fixtures.
            "kill_switch_verified": True,
            "kill_switch_active_at_start": False,
        }
        return record

    def test_routed_attempts_satisfy_decisional_gate(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture(
                {"success": 5, "disabled": 0, "error": 3, "routed_decisions": 8}
            )
        )
        assert grade.verdict == "PASS", grade.reasons

    def test_attempts_alone_are_decisional_activity(self) -> None:
        """Zero cycles would fail; zero cycles with routed attempts pass."""
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture(
                {"success": 0, "disabled": 0, "error": 8, "routed_decisions": 8},
                cycles=0,
            )
        )
        assert grade.verdict == "PASS", grade.reasons

    def test_ended_zero_attempts_with_outcomes_fails(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture(
                {"success": 5, "disabled": 0, "error": 0, "routed_decisions": 0}
            )
        )
        assert grade.verdict == "FAIL"
        assert any("routed_decisions" in r for r in grade.reasons)

    def test_ongoing_zero_attempts_with_outcomes_incomplete(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture(
                {"success": 5, "disabled": 0, "error": 0, "routed_decisions": 0},
                ended=False,
            )
        )
        assert grade.verdict == "INCOMPLETE"
        assert any("routed_decisions" in r for r in grade.reasons)

    def test_legacy_log_without_key_grades_unchanged(self) -> None:
        """The accruing pre-semantic span must keep its current verdict."""
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture({"success": 5, "disabled": 0, "error": 0})
        )
        assert grade.verdict == "PASS", grade.reasons
        assert not any("routed_decisions" in r for r in grade.reasons)

    def test_attempt_total_never_whitewashes_divergence(self) -> None:
        mod = _load_validator()
        grade = mod.grade_run_log(
            self._fixture(
                {
                    "success": 5,
                    "disabled": 0,
                    "error": 3,
                    "routed_decisions": 8,
                    "routing_divergence_detected": 1,
                }
            )
        )
        assert grade.verdict == "FAIL"
        assert any("divergence" in r.lower() for r in grade.reasons)


class TestSupervisorCarriesAttemptCounter:
    """Contract 4: the counter reaches run logs with no supervisor change."""

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

    def test_baseline_captures_attempt_counter(self, tmp_path: Path) -> None:
        runner = _load_runner()
        with (
            patch(
                "loats.orchestrator.orchestrator",
                SimpleNamespace(cycle_count=3),
            ),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: {
                        "success": 2,
                        "disabled": 0,
                        "error": 0,
                        "routed_decisions": 4,
                        "routing_divergence_detected": 0,
                    }
                ),
            ),
        ):
            baseline = runner._capture_live_baseline(SimpleNamespace(running=False))
        assert baseline["counters"]["routed_decisions"] == 4

    def test_sample_folds_attempt_delta_into_run_log(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = tmp_path / "run.json"
        self._write_run_log(run_log)
        system = SimpleNamespace(running=False)
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
                        "routed_decisions": 5,
                        "routing_divergence_detected": 0,
                    }
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch.object(runner, "_db_divergence_snapshot", lambda _log: None),
        ):
            runner._sample_live_activity(system, run_log, baseline)

        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["counters"]["routed_decisions"] == 5
        assert data["counters"]["success"] == 4
