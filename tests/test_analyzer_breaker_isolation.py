"""Analyzer-routing failure isolation (P5 forward-test integrity).

ADR-006 Amendment 4 records the read-only Analyzer-intake semantic: until
the gateway grows a decision-intake endpoint, every routed decision will
resolve as an honest HTTP-404 ``error`` outcome. At HEAD those failures
counted against the SHARED ``OPENALGO_CIRCUIT_BREAKER`` (threshold 3): three
consecutive routing 404s opened the same breaker every market-data call
flows through, mechanically reproducing the Amendment 3 starvation cascade
(breaker flap -> cycle errors -> CMP funnel starvation) through a different
route — poisoning the very evidence the P5 run exists to collect.

The isolation contract (mirrors the F8-L-01 per-source fleet rules):

1. Routing failures count on a dedicated ``ANALYZER_CIRCUIT_BREAKER``.
2. The shared OpenAlgo breaker never sees analyzer-routing outcomes.
3. The analyzer breaker opening must not reject market-data calls
   (one opens, others pass).
4. The operator status surface exposes the analyzer member.
5. The dedicated breaker's posture tolerates an error BUDGET (threshold 5,
   timeout 120 s): under the read-only semantic, routing 404s are expected
   telemetry, not a gateway-outage signal.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from loats.models import SignalType, TradeDecision
from loats.openalgo import OpenAlgoAPIError
from loats.utils.circuit_breaker import (
    ANALYZER_CIRCUIT_BREAKER,
    OPENALGO_CIRCUIT_BREAKER,
    CircuitBreakerOpenError,
)


def _decision() -> TradeDecision:
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


# The gateway's missing /analyze intake, expressed at the network seam.
# Deliberately NOT a fake client class: ``place_analyzer_request`` is the
# breaker-wrapped production method under test, so only the HTTP seam
# (``AsyncOpenAlgoClient._request``) below it is patched on the REAL class.
# Replacing the whole client would discard the breaker logic this suite
# exists to pin.
_ANALYZER_404 = OpenAlgoAPIError(
    status_code=404,
    message="Not Found",
    details={"response": "404 Not Found"},
)


@pytest.fixture(autouse=True)
def _reset_breakers():
    """Isolate breaker state per test; restore a clean fleet afterwards."""
    ANALYZER_CIRCUIT_BREAKER.reset()
    OPENALGO_CIRCUIT_BREAKER.reset()
    yield
    ANALYZER_CIRCUIT_BREAKER.reset()
    OPENALGO_CIRCUIT_BREAKER.reset()


async def _route_once() -> None:
    """Run one real ``route_to_analyzer`` against the 404-ing endpoint.

    Only the HTTP seam (``AsyncOpenAlgoClient._request``) is patched on the
    real class; the real client and its real breaker-wrapped
    ``place_analyzer_request`` execute.
    """
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch(
            "loats.openalgo.AsyncOpenAlgoClient._request",
            AsyncMock(side_effect=_ANALYZER_404),
        ),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=None),
        ),
    ):
        await engine.route_to_analyzer(_decision())


@pytest.mark.asyncio
async def test_routing_failures_count_on_dedicated_breaker_not_openalgo() -> None:
    """Driving the analyzer breaker to its threshold opens ONLY the analyzer
    breaker; the shared OpenAlgo breaker stays closed with zero recorded
    failures, and the next routing attempt is rejected by the dedicated
    breaker before any HTTP call."""
    threshold = ANALYZER_CIRCUIT_BREAKER.config.failure_threshold
    for _ in range(threshold):
        with pytest.raises(OpenAlgoAPIError):
            await _route_once()

    # Next attempt: the dedicated breaker is open and rejects (Circuit-
    # BreakerOpenError, not the API error).
    with pytest.raises(CircuitBreakerOpenError):
        await _route_once()

    analyzer_status = ANALYZER_CIRCUIT_BREAKER.get_status()
    assert analyzer_status["state"] == "open"
    assert analyzer_status["failed_calls"] >= threshold

    openalgo_status = OPENALGO_CIRCUIT_BREAKER.get_status()
    assert openalgo_status["state"] == "closed", (
        "analyzer-routing failures must never touch the shared OpenAlgo breaker"
    )
    assert openalgo_status["failed_calls"] == 0
    assert openalgo_status["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_open_analyzer_breaker_does_not_reject_market_data_calls() -> None:
    """Acceptance contract (one opens, others pass): with the analyzer
    breaker OPEN, a market-data-shaped call through the shared breaker
    executes normally."""
    for _ in range(ANALYZER_CIRCUIT_BREAKER.config.failure_threshold):
        with pytest.raises(OpenAlgoAPIError):
            await _route_once()

    assert ANALYZER_CIRCUIT_BREAKER.get_status()["state"] == "open"

    async def _quotes_probe() -> dict[str, Any]:
        return {"data": {}}

    result = await OPENALGO_CIRCUIT_BREAKER.call_async(_quotes_probe)
    assert result == {"data": {}}


def test_analyzer_breaker_member_in_alert_status_surface() -> None:
    """Operator surface: the analyzer breaker is visible in
    ``AlertSystem.get_circuit_breaker_status()`` alongside openalgo/telegram
    (state invisible to operators is isolation that didn't happen)."""
    from loats.alerts import AlertSystem

    status = AlertSystem().get_circuit_breaker_status()
    assert set(status) == {"openalgo", "telegram", "analyzer"}
    assert status["analyzer"]["circuit_name"] == "analyzer"


def test_analyzer_breaker_posture_tolerates_expected_error_budget() -> None:
    """The dedicated breaker tolerates an error BUDGET, not 3 strikes:
    threshold 5 (> shared breaker's 3) and timeout 120 s (> 60 s) — under
    the Am4 read-only semantic, routing 404s are expected telemetry, not a
    gateway-outage signal."""
    assert ANALYZER_CIRCUIT_BREAKER.name == "analyzer"
    assert ANALYZER_CIRCUIT_BREAKER.config.failure_threshold == 5
    assert ANALYZER_CIRCUIT_BREAKER.config.timeout == 120.0
