"""Integration tests for bounded decision-queue backpressure (TODO-27c)."""

from __future__ import annotations

import datetime

import pytest


def _mk_decision(symbol: str = "NIFTY"):
    from loats.models import SignalType, TradeDecision

    return TradeDecision(
        symbol=symbol,
        decision_type=SignalType.BUY,
        composite_strength=0.5,
        timestamp=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC),
        entry_price=18000.0,
        quantity=25,
        stop_loss=17820.0,
        position_size_method="fixed_fraction",
        risk_percentage=0.02,
        var_analysis={"var_value": 0.0, "var_percent": 0.0, "method": "parametric"},
    )


@pytest.mark.asyncio
async def test_queue_full_returns_rejected_no_blocking() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    r1 = await engine.enqueue_decision(_mk_decision("NIFTY"))
    r2 = await engine.enqueue_decision(_mk_decision("NIFTY"))
    r3 = await engine.enqueue_decision(_mk_decision("NIFTY"))
    assert r1["status"] == "queued"
    assert r2["status"] == "queued"
    assert r3["status"] == "rejected"
    assert r3["reason"] == "queue_full"
    assert r3["queue_size"] <= 2
    assert r3["queue_maxsize"] == 2


@pytest.mark.asyncio
async def test_get_queue_stats_reports_size_and_capacity() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=4)
    stats0 = engine.get_queue_stats()
    assert stats0["queue_size"] == 0
    assert stats0["queue_maxsize"] == 4
    assert stats0["queue_empty"] is True
    assert stats0["queue_full"] is False

    await engine.enqueue_decision(_mk_decision("NIFTY"))
    await engine.enqueue_decision(_mk_decision("NIFTY"))
    stats1 = engine.get_queue_stats()
    assert stats1["queue_size"] == 2
    assert stats1["queue_empty"] is False
    assert stats1["queue_full"] is False


@pytest.mark.asyncio
async def test_default_maxsize_uses_settings_decision_queue_maxsize() -> None:
    from loats.config import get_settings
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine()
    stats = engine.get_queue_stats()
    assert stats["queue_maxsize"] == get_settings().decision_queue_maxsize
