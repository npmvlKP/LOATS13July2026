#!/usr/bin/env python3
"""Tests for TradeDecision composite strength and signal source validation.

HC-15: Math and Aggregate Validation
HC-17: Signal Source Validation (F7-C-02a fix)
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from loats.database import Database
from loats.models import (
    FundsData,
    HistoricalData,
    Signal,
    SignalType,
)
from loats.strength import StrengthSource, StrengthEngine, resolve_source
from loats.trade_decision import TradeDecisionEngine


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Database(
            db_path=Path(td) / "test_td.db",
            audit_log_path=Path(td) / "test_audit.jsonl",
        )
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def strength_engine():
    return StrengthEngine()


@pytest.fixture
def trade_decision_engine():
    return TradeDecisionEngine()


@pytest.fixture
def fixture_funds():
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def fixture_historical_data():
    now = datetime.now(UTC)
    return [
        HistoricalData(
            symbol="NIFTY",
            timestamp=now - timedelta(minutes=5 * (30 - i)),
            open=24500.0 + i * 10,
            high=24550.0 + i * 10,
            low=24470.0 + i * 10,
            close=24510.0 + i * 10,
            volume=1000000 + i * 10000,
            interval="5min",
        )
        for i in range(30)
    ]


def _make_signals(count, strength_base=0.75, signal_type=SignalType.BUY):
    """Create *count* signals with distinct valid sources."""
    sources = [
        StrengthSource.TECHNICAL_ANALYSIS,
        StrengthSource.SENTIMENT,
        StrengthSource.PRICE_ACTION,
    ]
    now = datetime.now(UTC)
    return [
        Signal(
            symbol="NIFTY",
            signal_type=signal_type,
            strength=strength_base - i * 0.05,
            timestamp=now - timedelta(seconds=i * 30),
            indicators={"val": 0.5 + i * 0.1},
            confidence=0.8 - i * 0.05,
            metadata={"source": sources[i].value},
        )
        for i in range(min(count, 3))
    ]


class TestCompositeStrengthCalculation:
    """HC-15: Validate composite strength calculations and aggregation math."""

    def test_composite_strength_with_three_sources(self, strength_engine):
        cs, details = strength_engine.calculate_composite_strength(_make_signals(3))
        assert 0.0 <= cs <= 1.0
        assert details["sources"] == 3

    def test_composite_strength_weighted_by_confidence(self, strength_engine):
        cs, _ = strength_engine.calculate_composite_strength(_make_signals(3, 0.9))
        assert cs > 0.7

    def test_composite_strength_diversity_score(self, strength_engine):
        cs, details = strength_engine.calculate_composite_strength(_make_signals(3))
        assert "opposition_check" in details

    def test_composite_strength_with_opposing_signals(self, strength_engine):
        now = datetime.now(UTC)
        signals = [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=now,
                indicators={},
                confidence=0.8,
                metadata={"source": StrengthSource.TECHNICAL_ANALYSIS.value},
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.75,
                timestamp=now - timedelta(seconds=30),
                indicators={},
                confidence=0.75,
                metadata={"source": StrengthSource.SENTIMENT.value},
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.SELL,
                strength=0.6,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.6,
                metadata={"source": StrengthSource.PRICE_ACTION.value},
            ),
        ]
        cs, _ = strength_engine.calculate_composite_strength(signals)
        assert 0.0 <= cs <= 1.0

    def test_composite_strength_insufficient_sources(self, strength_engine):
        cs, details = strength_engine.calculate_composite_strength(_make_signals(2))
        assert cs == 0.0
        assert details["reason"] == "insufficient_sources"


class TestSignalSourceValidation:
    """HC-17: Signal Source Validation (F7-C-02a fix)."""

    def test_validate_three_valid_sources(self, strength_engine):
        ok, d = strength_engine.validate_signal_sources(_make_signals(3))
        assert ok is True
        assert d["reason"] == "source_validation_passed"
        assert d["unique_sources"] == 3

    def test_validate_rejects_insufficient_sources(self, strength_engine):
        ok, d = strength_engine.validate_signal_sources(_make_signals(2))
        assert ok is False
        assert d["reason"] == "insufficient_unique_sources"
        assert d["available"] == 2

    def test_validate_rejects_unknown_source(self, strength_engine):
        now = datetime.now(UTC)
        signals = _make_signals(2) + [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.68,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.72,
                metadata={"source": "invalid_unknown_source"},
            ),
        ]
        ok, d = strength_engine.validate_signal_sources(signals)
        assert ok is False
        assert d["reason"] == "unknown_source"

    def test_validate_rejects_duplicate_sources(self, strength_engine):
        now = datetime.now(UTC)
        signals = [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.75,
                timestamp=now,
                indicators={},
                confidence=0.8,
                metadata={"source": StrengthSource.TECHNICAL_ANALYSIS.value},
            ),
        ] * 3
        ok, d = strength_engine.validate_signal_sources(signals)
        assert ok is False
        assert d["available"] == 1

    def test_resolve_source_valid(self):
        assert resolve_source("ta") == StrengthSource.TECHNICAL_ANALYSIS
        assert resolve_source("sentiment") == StrengthSource.SENTIMENT
        assert resolve_source("price_action") == StrengthSource.PRICE_ACTION

    def test_resolve_source_invalid(self):
        with pytest.raises(ValueError):
            resolve_source("invalid_source")


class TestTradeDecisionCreation:
    """Test TradeDecision creation workflow."""

    @pytest.mark.asyncio
    async def test_create_decision_valid_signals(
        self, trade_decision_engine, fixture_historical_data, fixture_funds
    ):
        with patch("loats.trade_decision.rules_engine") as mock_rules:
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"
            decision, _ = await trade_decision_engine.create_trade_decision(
                signals=_make_signals(3),
                historical_data=fixture_historical_data,
                current_price=24500.0,
                funds=fixture_funds,
                current_positions=[],
            )
        assert decision is not None
        assert decision.symbol == "NIFTY"
        assert decision.decision_type == SignalType.BUY
        assert 0.0 <= decision.composite_strength <= 1.0
        assert decision.quantity > 0

    @pytest.mark.asyncio
    async def test_create_decision_rejects_weak_signals(
        self, trade_decision_engine, fixture_historical_data, fixture_funds
    ):
        with patch("loats.trade_decision.rules_engine") as mock_rules:
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"
            decision, r = await trade_decision_engine.create_trade_decision(
                signals=_make_signals(3, 0.2),
                historical_data=fixture_historical_data,
                current_price=24500.0,
                funds=fixture_funds,
                current_positions=[],
            )
        assert decision is None
        assert r["reason"] == "insufficient_strength"

    @pytest.mark.asyncio
    async def test_create_decision_rejects_invalid_sources(
        self, trade_decision_engine, fixture_historical_data, fixture_funds
    ):
        now = datetime.now(UTC)
        signals = _make_signals(2) + [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.68,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.72,
                metadata={"source": "bad_source"},
            ),
        ]
        decision, r = await trade_decision_engine.create_trade_decision(
            signals=signals,
            historical_data=fixture_historical_data,
            current_price=24500.0,
            funds=fixture_funds,
            current_positions=[],
        )
        assert decision is None
        assert r["reason"] == "signal_validation_failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
