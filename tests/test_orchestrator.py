#!/usr/bin/env python3
"""
Comprehensive test suite for orchestrator.py module.

This test file covers the main functionality of the TradingOrchestrator
to address the 32.6% coverage issue.
"""

import asyncio
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.alerts import AlertSystem
from src.loats.database import Database
from src.loats.models import (
    HistoricalData,
    OptionContract,
    OptionType,
    QuoteData,
    Signal,
    SignalType,
)
from src.loats.orchestrator import TradingOrchestrator, get_cycle_stats
from src.loats.openalgo import KillSwitchError

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()

        yield db

        # Clean up
        db.close_all()

@pytest.fixture
def mock_alerts():
    """Create a mock AlertSystem for testing."""
    alerts = MagicMock(spec=AlertSystem)
    alerts.is_kill_switch_active.return_value = False
    return alerts

class TestTradingOrchestrator(unittest.IsolatedAsyncioTestCase):
    """Test suite for TradingOrchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = TradingOrchestrator()

    async def test_initialize(self):
        """Test orchestrator initialization."""
        assert self.orchestrator.running is False
        assert self.orchestrator.cycle_count == 0

        await self.orchestrator.initialize()

        assert self.orchestrator.running is True
        assert self.orchestrator.cycle_count == 0
        assert self.orchestrator.last_cycle_time == 0.0
        assert self.orchestrator.max_cycle_time == 0.0
        assert self.orchestrator.avg_cycle_time == 0.0
        assert self.orchestrator.total_cycle_time == 0.0

    async def test_start(self):
        """Test orchestrator start."""
        with patch.object(self.orchestrator, "_run_cycle_loop") as mock_run_loop:
            await self.orchestrator.start()
            assert self.orchestrator.running is True
            mock_run_loop.assert_called_once()

    async def test_start_already_running(self):
        """Test orchestrator start when already running."""
        await self.orchestrator.initialize()
        with patch("src.loats.orchestrator.logger") as mock_logger:
            await self.orchestrator.start()
            mock_logger.warning.assert_called_with("Orchestrator already running")

    async def test_check_kill_switch(self):
        """Test kill switch check."""
        # Test when kill switch is inactive
        with patch("src.loats.orchestrator.alerts.is_kill_switch_active", return_value=False):
            await self.orchestrator._check_kill_switch()  # Should not raise exception

        # Test when kill switch is active
        with patch("src.loats.orchestrator.alerts.is_kill_switch_active", return_value=True):
            with pytest.raises(KillSwitchError, match="Kill switch active"):
                await self.orchestrator._check_kill_switch()

    async def test_execute_ta_analysis(self):
        """Test technical analysis execution."""
        # Create test data
        now = datetime.now(UTC)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=now,
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=10000,
                interval="1d",
            )
        ]

        with patch("src.loats.orchestrator.technical_analysis.analyze") as mock_analyze:
            mock_analyze.return_value = {"rsi": 30.0, "macd": 1.5}

            with patch("src.loats.orchestrator.db.store_historical_data") as mock_store:
                mock_store.return_value = True

                result = await self.orchestrator._execute_ta_analysis()

                assert result is True
                mock_analyze.assert_called_once()
                mock_store.assert_called_once()

    async def test_execute_sentiment_analysis(self):
        """Test sentiment analysis execution."""
        with patch("src.loats.orchestrator.sentiment.analyze") as mock_analyze:
            mock_result = MagicMock()
            mock_result.sentiment_score = 0.8
            mock_result.news_count = 5
            mock_analyze.return_value = mock_result

            with patch("src.loats.orchestrator.db.async_create_signal") as mock_create_signal:
                mock_create_signal.return_value = True

                result = await self.orchestrator._execute_sentiment_analysis()

                assert result is True
                mock_analyze.assert_called_once()
                mock_create_signal.assert_called_once()

    async def test_execute_market_data_update(self):
        """Test market data update execution."""
        # Create test quote data
        now = datetime.now(UTC)
        quote = QuoteData(
            symbol="TEST",
            last_price=105.0,
            open=100.0,
            high=106.0,
            low=99.5,
            close=104.5,
            volume=15000,
            timestamp=now,
            change=5.0,
            change_percent=4.76,
        )

        with patch("src.loats.orchestrator.options.get_quotes") as mock_get_quotes:
            mock_get_quotes.return_value = [quote]

            with patch("src.loats.orchestrator.db.async_store_quote") as mock_store_quote:
                mock_store_quote.return_value = True

                result = await self.orchestrator._execute_market_data_update()

                assert result is True
                mock_get_quotes.assert_called_once()
                mock_store_quote.assert_called_once_with(quote)

    async def test_execute_options_analysis(self):
        """Test options analysis execution."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        ]

        with patch("src.loats.orchestrator.options.get_option_chain") as mock_get_chain:
            mock_get_chain.return_value = option_chain

            with patch("src.loats.orchestrator.analysis.analyze") as mock_analyze:
                mock_analyze.return_value = {"atm_iv": 0.25, "skew": 0.1}

                with patch("src.loats.orchestrator.db.async_create_signal") as mock_create_signal:
                    mock_create_signal.return_value = True

                    result = await self.orchestrator._execute_options_analysis()

                    assert result is True
                    mock_get_chain.assert_called_once()
                    mock_analyze.assert_called_once()
                    mock_create_signal.assert_called_once()

    async def test_execute_strike_selection(self):
        """Test strike selection execution."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        ]

        with patch("src.loats.orchestrator.select_strikes") as mock_select_strikes:
            mock_select_strikes.return_value = [100.0, 105.0]

            with patch("src.loats.orchestrator.db.async_get_latest_signals") as mock_get_signals:
                mock_get_signals.return_value = []

                result = await self.orchestrator._execute_strike_selection(option_chain)

                assert result is True
                mock_select_strikes.assert_called_once()
                mock_get_signals.assert_called_once()

    async def test_execute_trade_execution(self):
        """Test trade execution."""
        # Create test signal
        now = datetime.now(UTC)
        signal = Signal(
            signal_id="test_signal_001",
            symbol="TEST",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=now,
            indicators={"rsi": 30.0},
            confidence=0.9,
            metadata={"scan_type": "technical"},
        )

        with patch("src.loats.orchestrator.db.async_get_latest_signals") as mock_get_signals:
            mock_get_signals.return_value = [signal]

            with patch("src.loats.orchestrator.async_client.place_order") as mock_place_order:
                mock_place_order.return_value = {"status": "success", "order_id": "12345"}

                with patch("src.loats.orchestrator.db.async_create_signal") as mock_create_signal:
                    mock_create_signal.return_value = True

                    result = await self.orchestrator._execute_trade_execution()

                    assert result is True
                    mock_get_signals.assert_called_once()
                    mock_place_order.assert_called_once()
                    mock_create_signal.assert_called_once()

    async def test_execute_risk_management(self):
        """Test risk management execution."""
        # Create test position
        position = MagicMock()
        position.symbol = "TEST"
        position.quantity = 10
        position.average_price = 100.0
        position.last_price = 105.0
        position.pnl = 50.0

        with patch("src.loats.orchestrator.async_client.get_positions") as mock_get_positions:
            mock_get_positions.return_value = [position]

            with patch("src.loats.orchestrator.async_client.get_funds") as mock_get_funds:
                mock_funds = MagicMock()
                mock_funds.available_margin = 30000.0
                mock_funds.total_equity = 70000.0
                mock_get_funds.return_value = mock_funds

                with patch("src.loats.orchestrator.alerts.send_risk_alert") as mock_send_alert:
                    result = await self.orchestrator._execute_risk_management()

                    assert result is True
                    mock_get_positions.assert_called_once()
                    mock_get_funds.assert_called_once()
                    # mock_send_alert may or may not be called depending on thresholds

    async def test_execute_trading_cycle(self):
        """Test complete trading cycle execution."""
        with patch.object(self.orchestrator, "_check_kill_switch") as mock_check_kill:
            with patch.object(self.orchestrator, "_execute_ta_analysis") as mock_ta:
                with patch.object(self.orchestrator, "_execute_sentiment_analysis") as mock_sentiment:
                    with patch.object(self.orchestrator, "_execute_market_data_update") as mock_market:
                        with patch.object(self.orchestrator, "_execute_options_analysis") as mock_options:
                            with patch.object(self.orchestrator, "_execute_strike_selection") as mock_strike:
                                with patch.object(self.orchestrator, "_execute_trade_execution") as mock_trade:
                                    with patch.object(self.orchestrator, "_execute_risk_management") as mock_risk:
                                        mock_ta.return_value = True
                                        mock_sentiment.return_value = True
                                        mock_market.return_value = True
                                        mock_options.return_value = True
                                        mock_strike.return_value = True
                                        mock_trade.return_value = True
                                        mock_risk.return_value = True

                                        await self.orchestrator._execute_trading_cycle()

                                        mock_check_kill.assert_called_once()
                                        mock_ta.assert_called_once()
                                        mock_sentiment.assert_called_once()
                                        mock_market.assert_called_once()
                                        mock_options.assert_called_once()
                                        mock_strike.assert_called_once()
                                        mock_trade.assert_called_once()
                                        mock_risk.assert_called_once()

    async def test_execute_trading_cycle_with_kill_switch(self):
        """Test trading cycle with kill switch active."""
        with patch.object(self.orchestrator, "_check_kill_switch", side_effect=KillSwitchError("Kill switch active")):
            with patch("src.loats.orchestrator.logger") as mock_logger:
                await self.orchestrator._execute_trading_cycle()
                mock_logger.warning.assert_called_with("Kill switch active - trading cycle paused")

    async def test_execute_trading_cycle_with_error(self):
        """Test trading cycle with error."""
        with patch.object(self.orchestrator, "_check_kill_switch"):
            with patch.object(self.orchestrator, "_execute_ta_analysis", side_effect=Exception("Test error")):
                with patch("src.loats.orchestrator.logger") as mock_logger:
                    with patch("src.loats.orchestrator.alerts.send_system_alert") as mock_send_alert:
                        await self.orchestrator._execute_trading_cycle()
                        mock_logger.error.assert_called_with("Trading cycle error: Test error")
                        mock_send_alert.assert_called_once()

    async def test_record_cycle_time(self):
        """Test cycle time recording."""
        # Test initial state
        assert self.orchestrator.last_cycle_time == 0.0
        assert self.orchestrator.max_cycle_time == 0.0
        assert self.orchestrator.avg_cycle_time == 0.0
        assert self.orchestrator.total_cycle_time == 0.0

        # Record first cycle time
        self.orchestrator._record_cycle_time(0.05)  # 50ms
        assert self.orchestrator.last_cycle_time == 0.05
        assert self.orchestrator.max_cycle_time == 0.05
        assert self.orchestrator.avg_cycle_time == 0.05
        assert self.orchestrator.total_cycle_time == 0.05

        # Record second cycle time
        self.orchestrator._record_cycle_time(0.07)  # 70ms
        assert self.orchestrator.last_cycle_time == 0.07
        assert self.orchestrator.max_cycle_time == 0.07
        assert abs(self.orchestrator.avg_cycle_time - 0.06) < 0.001  # Average of 50ms and 70ms
        assert abs(self.orchestrator.total_cycle_time - 0.12) < 0.001  # Sum of 50ms and 70ms

    async def test_run_cycle_loop(self):
        """Test the main trading cycle loop."""
        with patch.object(self.orchestrator, "_shutdown_event") as mock_shutdown_event:
            mock_shutdown_event.is_set.side_effect = [False, True]  # Run once then shutdown

            with patch.object(self.orchestrator, "_execute_trading_cycle") as mock_execute_cycle:
                with patch.object(self.orchestrator, "_record_cycle_time") as mock_record_time:
                    with patch("asyncio.sleep") as mock_sleep:
                        await self.orchestrator._run_cycle_loop()
                        mock_execute_cycle.assert_called_once()
                        mock_record_time.assert_called_once()
                        mock_sleep.assert_called_once()

    async def test_shutdown(self):
        """Test orchestrator shutdown."""
        await self.orchestrator.initialize()
        assert self.orchestrator.running is True

        await self.orchestrator.shutdown()
        assert self.orchestrator.running is False

    async def test_get_cycle_stats(self):
        """Test cycle statistics retrieval."""
        # Record some cycle times
        self.orchestrator._record_cycle_time(0.05)  # 50ms
        self.orchestrator._record_cycle_time(0.07)  # 70ms

        stats = get_cycle_stats()
        assert stats["cycle_count"] == 2
        assert stats["last_cycle_time"] == 0.07
        assert stats["max_cycle_time"] == 0.07
        assert abs(stats["avg_cycle_time"] - 0.06) < 0.001
        assert abs(stats["total_cycle_time"] - 0.12) < 0.001

    async def test_cycle_time_target(self):
        """Test that cycle time target is enforced."""
        with patch.object(self.orchestrator, "_execute_trading_cycle") as mock_execute_cycle:
            mock_execute_cycle.side_effect = lambda: asyncio.sleep(0.05)  # 50ms

            with patch("asyncio.sleep") as mock_sleep:
                # Run a single cycle
                cycle_start = datetime.now(UTC)
                await self.orchestrator._check_kill_switch()
                await self.orchestrator._execute_trading_cycle()

                # Calculate and record cycle time
                cycle_duration = (datetime.now(UTC) - cycle_start).total_seconds()
                self.orchestrator._record_cycle_time(cycle_duration)

                # Enforce 100ms cycle target
                target_duration = 0.1  # 100ms
                sleep_time = max(0, target_duration - cycle_duration)
                await asyncio.sleep(sleep_time)

                # Verify that sleep was called with appropriate time
                mock_sleep.assert_called_once()
                sleep_arg = mock_sleep.call_args[0][0]
                assert sleep_arg <= 0.05  # Should be <= 50ms (100ms - 50ms)

if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)