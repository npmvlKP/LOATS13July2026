"""Tests the complete CMP (Composite Market Position) chain from signal generation
through TradeDecision creation, following the production signal flow.

TODO-10 (F7-C-02d): End-to-end test for REAL orchestrator signals to create_trade_decision
"""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loats.database import Database
from loats.models import (
    FundsData,
    HistoricalData,
    QuoteData,
    Signal,
    SignalType,
)
from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "test_e2e_cmp.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def orchestrator():
    return TradingOrchestrator()


@pytest.fixture
def fixture_market_data():
    now = datetime.now(UTC)
    return [
        HistoricalData(
            symbol="NIFTY",
            timestamp=now - timedelta(minutes=5 * (30 - i)),
            open=24550.0,
            high=24600.0,
            low=24520.0,
            close=24560.0,
            volume=1050000,
            interval="5min",
        )
        for i in range(30)
    ]


@pytest.fixture
def fixture_quote_data():
    return QuoteData(
        symbol="NIFTY",
        last_price=24500.0,
        open=24450.0,
        high=24550.0,
        low=24400.0,
        close=24480.0,
        volume=5000000,
        timestamp=datetime.now(UTC),
        change=50.0,
        change_percent=0.2,
    )


@pytest.fixture
def fixture_funds_data():
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def fixture_signals():
    now = datetime.now(UTC)
    return [
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.75,
            timestamp=now,
            indicators={"rsi": 65.0},
            confidence=0.8,
            metadata={
                "scan_type": "combined",
                "source": StrengthSource.TECHNICAL_ANALYSIS.value,
                "current_price": 24500.0,
            },
        ),
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.7,
            timestamp=now - timedelta(seconds=30),
            indicators={"sentiment_score": 0.6},
            confidence=0.75,
            metadata={
                "scan_type": "combined",
                "source": StrengthSource.SENTIMENT.value,
                "current_price": 24500.0,
            },
        ),
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.68,
            timestamp=now - timedelta(seconds=60),
            indicators={"momentum": 0.5},
            confidence=0.72,
            metadata={
                "scan_type": "combined",
                "source": StrengthSource.PRICE_ACTION.value,
                "current_price": 24500.0,
            },
        ),
    ]


class TestE2ECMPChain:
    """End-to-end CMP chain integration tests."""

    @pytest.fixture
    def fixture_signals(self):
        now = datetime.now(UTC)
        return [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.75,
                timestamp=now,
                indicators={"rsi": 65.0},
                confidence=0.8,
                metadata={
                    "scan_type": "combined",
                    "source": StrengthSource.TECHNICAL_ANALYSIS.value,
                    "current_price": 24500.0,
                },
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.7,
                timestamp=now - timedelta(seconds=30),
                indicators={"sentiment_score": 0.6},
                confidence=0.75,
                metadata={
                    "scan_type": "combined",
                    "source": StrengthSource.SENTIMENT.value,
                    "current_price": 24500.0,
                },
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.68,
                timestamp=now - timedelta(seconds=60),
                indicators={"momentum": 0.5},
                confidence=0.72,
                metadata={
                    "scan_type": "combined",
                    "source": StrengthSource.PRICE_ACTION.value,
                    "current_price": 24500.0,
                },
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.65,
                timestamp=now - timedelta(seconds=90),
                indicators={"vix": 15.0},
                confidence=0.7,
                metadata={
                    "scan_type": "combined",
                    "source": StrengthSource.VOLATILITY.value,
                    "current_price": 24500.0,
                },
            ),
        ]

    @pytest.mark.asyncio
    async def test_cmp_chain_with_production_signals(
        self,
        temp_db,
        orchestrator,
        fixture_market_data,
        fixture_quote_data,
        fixture_funds_data,
        fixture_signals,
    ):
        for signal in fixture_signals:
            await temp_db.async_create_signal(signal)
        stored_signals = await temp_db.async_get_latest_signals("NIFTY", limit=10)
        assert len(stored_signals) == 4, "All 4 signals should be stored in DB"
        sources = {s.metadata.get("source") for s in stored_signals}
        expected_sources = {
            StrengthSource.TECHNICAL_ANALYSIS.value,
            StrengthSource.SENTIMENT.value,
            StrengthSource.PRICE_ACTION.value,
            StrengthSource.VOLATILITY.value,
        }
        assert sources == expected_sources, (
            "Signal sources must match production enum values"
        )

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
            with patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_get_history:
                with patch.object(
                    orchestrator, "_safe_get_quotes", new_callable=AsyncMock
                ) as mock_get_quotes:
                    with patch.object(
                        orchestrator, "_safe_get_funds", new_callable=AsyncMock
                    ) as mock_get_funds:
                        with patch.object(
                            orchestrator,
                            "_safe_get_position_book",
                            new_callable=AsyncMock,
                        ) as mock_get_positions:
                            with patch("loats.orchestrator.db", temp_db):
                                mock_get_history.return_value = {
                                    "data": [
                                        {
                                            "timestamp": h.timestamp.isoformat(),
                                            "open": h.open,
                                            "high": h.high,
                                            "low": h.low,
                                            "close": h.close,
                                            "volume": h.volume,
                                        }
                                        for h in fixture_market_data
                                    ]
                                }
                                mock_get_quotes.return_value = {
                                    "data": {
                                        "NIFTY": {
                                            "last_price": fixture_quote_data.last_price,
                                            "open": fixture_quote_data.open,
                                            "high": fixture_quote_data.high,
                                            "low": fixture_quote_data.low,
                                            "close": fixture_quote_data.close,
                                            "volume": fixture_quote_data.volume,
                                            "change": fixture_quote_data.change,
                                            "change_percent": fixture_quote_data.change_percent,
                                        }
                                    }
                                }
                                mock_get_funds.return_value = {
                                    "data": {
                                        "available_cash": fixture_funds_data.available_cash,
                                        "utilized_margin": fixture_funds_data.utilized_margin,
                                        "available_margin": fixture_funds_data.available_margin,
                                        "total_equity": fixture_funds_data.total_equity,
                                    }
                                }
                                mock_get_positions.return_value = {"data": []}
                                await orchestrator.initialize()
                                await orchestrator._execute_cmp_strategy()
                                trade_decisions = await asyncio.to_thread(
                                    temp_db.get_trade_decisions, symbol="NIFTY", limit=1
                                )
                                assert len(trade_decisions) > 0, (
                                    "TradeDecision should be created by CMP strategy"
                                )
                                decision = trade_decisions[0]
                                assert decision.symbol == "NIFTY", (
                                    "Decision should be for NIFTY"
                                )
                                assert decision.status in ["PENDING", "APPROVED"], (
                                    "Decision should have valid status"
                                )
                                assert 0.0 <= decision.composite_strength <= 1.0, (
                                    "Composite strength must be in [0, 1]"
                                )
                                assert "validation_result" in decision.metadata, (
                                    "Decision metadata should include validation result"
                                )
                                assert (
                                    len(
                                        decision.metadata["validation_result"][
                                            "sources"
                                        ]
                                    )
                                    >= 3
                                ), "Decision should use >=3 signal sources"
                                await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_cmp_chain_rejects_insufficient_signals(
        self,
        temp_db,
        orchestrator,
        fixture_market_data,
        fixture_quote_data,
        fixture_funds_data,
    ):
        now = datetime.now(UTC)
        signal1 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.7,
            timestamp=now,
            indicators={"rsi": 60.0},
            confidence=0.7,
            metadata={
                "scan_type": "ta",
                "source": StrengthSource.TECHNICAL_ANALYSIS.value,
            },
        )
        signal2 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.65,
            timestamp=now - timedelta(seconds=30),
            indicators={"sentiment_score": 0.6},
            confidence=0.65,
            metadata={
                "scan_type": "sentiment",
                "source": StrengthSource.SENTIMENT.value,
            },
        )
        await temp_db.async_create_signal(signal1)
        await temp_db.async_create_signal(signal2)

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
            with patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_get_history:
                with patch.object(
                    orchestrator, "_safe_get_quotes", new_callable=AsyncMock
                ) as mock_get_quotes:
                    with patch.object(
                        orchestrator, "_safe_get_funds", new_callable=AsyncMock
                    ) as mock_get_funds:
                        with patch.object(
                            orchestrator,
                            "_safe_get_position_book",
                            new_callable=AsyncMock,
                        ) as mock_get_positions:
                            with patch("loats.orchestrator.db", temp_db):
                                mock_get_history.return_value = {
                                    "data": [
                                        {
                                            "timestamp": h.timestamp.isoformat(),
                                            "open": h.open,
                                            "high": h.high,
                                            "low": h.low,
                                            "close": h.close,
                                            "volume": h.volume,
                                        }
                                        for h in fixture_market_data
                                    ]
                                }
                                mock_get_quotes.return_value = {
                                    "data": {
                                        "NIFTY": {
                                            "last_price": fixture_quote_data.last_price,
                                            "open": fixture_quote_data.open,
                                            "high": fixture_quote_data.high,
                                            "low": fixture_quote_data.low,
                                            "close": fixture_quote_data.close,
                                            "volume": fixture_quote_data.volume,
                                            "change": fixture_quote_data.change,
                                            "change_percent": fixture_quote_data.change_percent,
                                        }
                                    }
                                }
                                mock_get_funds.return_value = {
                                    "data": {
                                        "available_cash": fixture_funds_data.available_cash,
                                        "utilized_margin": fixture_funds_data.utilized_margin,
                                        "available_margin": fixture_funds_data.available_margin,
                                        "total_equity": fixture_funds_data.total_equity,
                                    }
                                }
                                mock_get_positions.return_value = {"data": []}
                                await orchestrator.initialize()
                                await orchestrator._execute_cmp_strategy()
                                trade_decisions = await asyncio.to_thread(
                                    temp_db.get_trade_decisions, symbol="NIFTY", limit=1
                                )
                                assert len(trade_decisions) == 0, (
                                    "No TradeDecision should be created with <3 signals"
                                )
                                await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_cmp_chain_rejects_unknown_source(
        self,
        temp_db,
        orchestrator,
        fixture_market_data,
        fixture_quote_data,
        fixture_funds_data,
    ):
        now = datetime.now(UTC)
        signal1 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.7,
            timestamp=now,
            indicators={"rsi": 60.0},
            confidence=0.7,
            metadata={
                "scan_type": "ta",
                "source": StrengthSource.TECHNICAL_ANALYSIS.value,
            },
        )
        signal2 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.65,
            timestamp=now - timedelta(seconds=30),
            indicators={"sentiment_score": 0.6},
            confidence=0.65,
            metadata={
                "scan_type": "sentiment",
                "source": StrengthSource.SENTIMENT.value,
            },
        )
        signal3 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            timestamp=now - timedelta(seconds=60),
            indicators={"momentum": 0.5},
            confidence=0.6,
            metadata={
                "scan_type": "momentum",
                "source": "invalid_source_that_does_not_exist",
            },
        )
        await temp_db.async_create_signal(signal1)
        await temp_db.async_create_signal(signal2)
        await temp_db.async_create_signal(signal3)

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
            with patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_get_history:
                with patch.object(
                    orchestrator, "_safe_get_quotes", new_callable=AsyncMock
                ) as mock_get_quotes:
                    with patch.object(
                        orchestrator, "_safe_get_funds", new_callable=AsyncMock
                    ) as mock_get_funds:
                        with patch.object(
                            orchestrator,
                            "_safe_get_position_book",
                            new_callable=AsyncMock,
                        ) as mock_get_positions:
                            with patch("loats.orchestrator.db", temp_db):
                                mock_get_history.return_value = {
                                    "data": [
                                        {
                                            "timestamp": h.timestamp.isoformat(),
                                            "open": h.open,
                                            "high": h.high,
                                            "low": h.low,
                                            "close": h.close,
                                            "volume": h.volume,
                                        }
                                        for h in fixture_market_data
                                    ]
                                }
                                mock_get_quotes.return_value = {
                                    "data": {
                                        "NIFTY": {
                                            "last_price": fixture_quote_data.last_price,
                                            "open": fixture_quote_data.open,
                                            "high": fixture_quote_data.high,
                                            "low": fixture_quote_data.low,
                                            "close": fixture_quote_data.close,
                                            "volume": fixture_quote_data.volume,
                                            "change": fixture_quote_data.change,
                                            "change_percent": fixture_quote_data.change_percent,
                                        }
                                    }
                                }
                                mock_get_funds.return_value = {
                                    "data": {
                                        "available_cash": fixture_funds_data.available_cash,
                                        "utilized_margin": fixture_funds_data.utilized_margin,
                                        "available_margin": fixture_funds_data.available_margin,
                                        "total_equity": fixture_funds_data.total_equity,
                                    }
                                }
                                mock_get_positions.return_value = {"data": []}
                                await orchestrator.initialize()
                                await orchestrator._execute_cmp_strategy()
                                trade_decisions = await asyncio.to_thread(
                                    temp_db.get_trade_decisions, symbol="NIFTY", limit=1
                                )
                                assert len(trade_decisions) == 0, (
                                    "No TradeDecision should be created with unknown source"
                                )
                                await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_cmp_chain_with_opposing_signals(
        self,
        temp_db,
        orchestrator,
        fixture_market_data,
        fixture_quote_data,
        fixture_funds_data,
    ):
        now = datetime.now(UTC)
        signal1 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=now,
            indicators={"rsi": 70.0},
            confidence=0.8,
            metadata={
                "scan_type": "ta",
                "source": StrengthSource.TECHNICAL_ANALYSIS.value,
            },
        )
        signal2 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.75,
            timestamp=now - timedelta(seconds=30),
            indicators={"sentiment_score": 0.7},
            confidence=0.75,
            metadata={
                "scan_type": "sentiment",
                "source": StrengthSource.SENTIMENT.value,
            },
        )
        signal3 = Signal(
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.6,
            timestamp=now - timedelta(seconds=60),
            indicators={"momentum": -0.3},
            confidence=0.6,
            metadata={
                "scan_type": "momentum",
                "source": StrengthSource.PRICE_ACTION.value,
            },
        )
        await temp_db.async_create_signal(signal1)
        await temp_db.async_create_signal(signal2)
        await temp_db.async_create_signal(signal3)

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
            with patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_get_history:
                with patch.object(
                    orchestrator, "_safe_get_quotes", new_callable=AsyncMock
                ) as mock_get_quotes:
                    with patch.object(
                        orchestrator, "_safe_get_funds", new_callable=AsyncMock
                    ) as mock_get_funds:
                        with patch.object(
                            orchestrator,
                            "_safe_get_position_book",
                            new_callable=AsyncMock,
                        ) as mock_get_positions:
                            with patch("loats.orchestrator.db", temp_db):
                                mock_get_history.return_value = {
                                    "data": [
                                        {
                                            "timestamp": h.timestamp.isoformat(),
                                            "open": h.open,
                                            "high": h.high,
                                            "low": h.low,
                                            "close": h.close,
                                            "volume": h.volume,
                                        }
                                        for h in fixture_market_data
                                    ]
                                }
                                mock_get_quotes.return_value = {
                                    "data": {
                                        "NIFTY": {
                                            "last_price": fixture_quote_data.last_price,
                                            "open": fixture_quote_data.open,
                                            "high": fixture_quote_data.high,
                                            "low": fixture_quote_data.low,
                                            "close": fixture_quote_data.close,
                                            "volume": fixture_quote_data.volume,
                                            "change": fixture_quote_data.change,
                                            "change_percent": fixture_quote_data.change_percent,
                                        }
                                    }
                                }
                                mock_get_funds.return_value = {
                                    "data": {
                                        "available_cash": fixture_funds_data.available_cash,
                                        "utilized_margin": fixture_funds_data.utilized_margin,
                                        "available_margin": fixture_funds_data.available_margin,
                                        "total_equity": fixture_funds_data.total_equity,
                                    }
                                }
                                mock_get_positions.return_value = {"data": []}
                                await orchestrator.initialize()
                                await orchestrator._execute_cmp_strategy()
                                trade_decisions = await asyncio.to_thread(
                                    temp_db.get_trade_decisions, symbol="NIFTY", limit=1
                                )
                                if len(trade_decisions) > 0:
                                    decision = trade_decisions[0]
                                    assert decision.composite_strength < 0.85, (
                                        "Opposition should cap composite strength below pure-BUY level"
                                    )
                                await orchestrator.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
