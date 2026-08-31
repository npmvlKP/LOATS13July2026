"""Integration tests for analyzer routing.

HC-19 FR consolidated gate: routing must be real (HTTP via
``AsyncOpenAlgoClient.place_analyzer_request``), routing must be **off**
by default (``analyzer_routing_enabled=False``), the integration test
itself must populate ``def test_`` functions (not a 0-byte stub), and
errors must propagate (no fabricated success).
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_routing_disabled_by_default_in_factory() -> None:
    """``TradeDecisionEngine`` constructs with ``analyzer_routing_enabled``
    inheriting ``Settings.analyzer_routing_enabled`` (False in production)."""
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    assert engine.analyzer_routing_enabled is False, (
        "Default must NOT be on (FR HC-19: 'no default-on')"
    )


@pytest.mark.asyncio
async def test_routing_disabled_returns_disabled_status_and_audits() -> None:
    from loats.models import SignalType, TradeDecision
    from loats.strength import StrengthSource
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    decision = TradeDecision(
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
        metadata={"source": StrengthSource.TECHNICAL_ANALYSIS.value},
    )

    audit_calls: list[Any] = []

    async def fake_record(decision_arg: Any) -> None:
        audit_calls.append(decision_arg)

    with (
        patch.object(engine, "analyzer_routing_enabled", False),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(side_effect=fake_record),
        ),
    ):
        result = await engine.route_to_analyzer(decision)

    assert result["status"] == "disabled"
    assert result["reason"] == "analyzer_routing_disabled"
    assert len(audit_calls) == 1, "decision must be audited even when routing disabled"


@pytest.mark.asyncio
async def test_routing_enabled_makes_real_http_call() -> None:
    from loats.models import SignalType, TradeDecision
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    decision = TradeDecision(
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

    fake_response = {"status": "accepted", "analyzer_id": "abc-123"}

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def place_analyzer_request(self, payload: Any) -> dict[str, Any]:
            assert isinstance(payload, dict), "must be Analyzer JSON payload"
            return fake_response

    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.openalgo.AsyncOpenAlgoClient", FakeClient),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=None),
        ),
    ):
        result = await engine.route_to_analyzer(decision)

    assert result["status"] == "success"
    assert result["analyzer_response"] == fake_response


@pytest.mark.asyncio
async def test_routing_propagates_errors_no_fabrication() -> None:
    from loats.models import SignalType, TradeDecision
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    decision = TradeDecision(
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

    class FailingClient:
        async def __aenter__(self) -> FailingClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def place_analyzer_request(self, payload: Any) -> dict[str, Any]:
            raise RuntimeError("simulated HTTP failure")

    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.openalgo.AsyncOpenAlgoClient", FailingClient),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(RuntimeError, match="simulated HTTP failure"):
            await engine.route_to_analyzer(decision)
