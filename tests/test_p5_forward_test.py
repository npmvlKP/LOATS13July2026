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
import subprocess
import sys
from pathlib import Path
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


class TestP5RunnerSmoke:
    """Runner dry-run must exit 0 and produce a gradeable run log."""

    def test_dry_run_creates_run_log(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
        logs = sorted(
            (REPO_ROOT / "reports").glob("p5_forward_test_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        assert logs, "dry-run must leave a run log under reports/"
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
