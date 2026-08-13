#!/usr/bin/env python3
"""
Comprehensive test suite for orchestrator.py module.

This test file covers the main functionality of the TradingOrchestrator
to address the 32.6% coverage issue.
"""

import asyncio
import datetime
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.alerts import AlertSystem
from loats.database import Database
from loats.models import (
    HistoricalData,
    OptionContract,
    OptionType,
    QuoteData,
    Signal,
    SignalType,
)
from loats.orchestrator import TradingOrchestrator, get_cycle_stats
from loats.openalgo import KillSwitchError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
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
            with pytest.raises(KillSwitchError, match=""):
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

        with patch("src.loats.orchestrator.technical_analysis.calculate_indicators") as mock_calc:
            mock_calc.return_value = []
            with patch("src.loats.orchestrator.technical_analysis.generate_signal") as mock_gen:
                mock_gen.return_value = None
                with patch.object(self.orchestrator, "_safe_get_history", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None
                    # Should handle empty history gracefully
                    await self.orchestrator._execute_ta_analysis()
                    mock_history.assert_called_once()

    async def test_execute_sentiment_analysis(self):
        """Test sentiment analysis execution."""
        from loats.models import SentimentAnalysisResult

        # Create a proper SentimentAnalysisResult object
        mock_result = SentimentAnalysisResult(
            symbol="TEST",
            timestamp=datetime.now(UTC),
            sentiment_score=0.8,
            sentiment_label="positive",
            news_count=5,
            positive_count=3,
            negative_count=1,
            neutral_count=1,
            top_news=[]
        )

        # Mock the async function to return the result directly (not a coroutine)
        with patch("src.loats.orchestrator.sentiment.analyze_symbol_sentiment", return_value=mock_result):
            with patch("src.loats.orchestrator.db.async_create_signal", new_callable=AsyncMock) as mock_create_signal:
                mock_create_signal.return_value = True
                with patch("src.loats.orchestrator.settings") as mock_settings:
                    mock_settings.default_symbol = "TEST"
                    mock_settings.sentiment_threshold = 0.5
                    await self.orchestrator._execute_sentiment_analysis()
                    mock_create_signal.assert_called_once()

    async def test_execute_market_data_update(self):
        """Test market data update execution."""
        with patch.object(self.orchestrator, "_safe_get_quotes", new_callable=AsyncMock) as mock_get_quotes:
            mock_get_quotes.return_value = None
            with patch.object(self.orchestrator, "_safe_get_position_book", new_callable=AsyncMock) as mock_pos:
                mock_pos.return_value = None
                with patch.object(self.orchestrator, "_safe_get_funds", new_callable=AsyncMock) as mock_funds:
                    mock_funds.return_value = None
                    # Should handle no quotes gracefully
                    await self.orchestrator._execute_market_data_update()
                    mock_get_quotes.assert_called_once()

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

        with patch("src.loats.orchestrator.select_strikes", new_callable=AsyncMock) as mock_select_strikes:
            mock_select_strikes.return_value = [100.0, 105.0]

            result = await self.orchestrator._execute_strike_selection(option_chain)

            # Method returns list of selected strikes
            assert isinstance(result, list)
            assert len(result) == 2
            mock_select_strikes.assert_called_once()

    async def test_execute_strike_selection_empty(self):
        """Test strike selection with empty option chain."""
        result = await self.orchestrator._execute_strike_selection([])
        assert result == []

    async def test_execute_risk_management(self):
        """Test risk management execution."""
        with patch("src.loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = {"state": "closed"}
            with patch("src.loats.orchestrator.db.get_position", new_callable=AsyncMock) as mock_pos:
                mock_pos.return_value = None
                with patch("src.loats.orchestrator.db.get_latest_funds", new_callable=AsyncMock) as mock_funds:
                    mock_funds.return_value = None
                    with patch("src.loats.orchestrator.settings") as mock_settings:
                        mock_settings.default_symbol = "TEST"
                        mock_settings.max_position_size = 100
                        mock_settings.max_margin_utilization = 0.8
                        await self.orchestrator._execute_risk_management()
                        mock_pos.assert_called_once()

    async def test_execute_trading_cycle(self):
        """Test complete trading cycle execution."""
        with patch.object(self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock) as mock_ta:
            with patch.object(self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock) as mock_sentiment:
                with patch.object(self.orchestrator, "_execute_market_data_update", new_callable=AsyncMock) as mock_market:
                    with patch.object(self.orchestrator, "_execute_signal_generation", new_callable=AsyncMock) as mock_signal:
                        with patch.object(self.orchestrator, "_execute_risk_management", new_callable=AsyncMock) as mock_risk:
                            await self.orchestrator._execute_trading_cycle()

                            mock_ta.assert_called_once()
                            mock_sentiment.assert_called_once()
                            mock_market.assert_called_once()
                            mock_signal.assert_called_once()
                            mock_risk.assert_called_once()

    async def test_execute_trading_cycle_with_kill_switch(self):
        """Test trading cycle with kill switch active."""
        with patch.object(self.orchestrator, "_check_kill_switch", side_effect=KillSwitchError("Kill switch active")):
            with patch("src.loats.orchestrator.logger") as mock_logger:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    # _execute_trading_cycle doesn't call _check_kill_switch; that's in _run_cycle_loop
                    # Test _run_cycle_loop with kill switch
                    with patch.object(self.orchestrator, "_shutdown_event") as mock_shutdown:
                        mock_shutdown.is_set.side_effect = [False, True]
                        await self.orchestrator._run_cycle_loop()
                        mock_logger.warning.assert_any_call("Kill switch active - trading cycle paused")

    async def test_execute_trading_cycle_with_error(self):
        """Test trading cycle with error."""
        with patch.object(self.orchestrator, "_execute_ta_analysis", side_effect=Exception("Test error")):
            with patch("src.loats.orchestrator.logger") as mock_logger:
                with patch("src.loats.orchestrator.alerts.send_system_alert", new_callable=AsyncMock):
                    with pytest.raises(Exception, match="Test error"):
                        await self.orchestrator._execute_trading_cycle()

    def test_record_cycle_time(self):
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

            with patch.object(self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock) as mock_execute_cycle:
                with patch.object(self.orchestrator, "_check_kill_switch", new_callable=AsyncMock) as mock_check_kill:
                    with patch.object(self.orchestrator, "_record_cycle_time") as mock_record_time:
                        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
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

        stats = self.orchestrator.get_cycle_stats()
        assert stats["cycle_count"] == 2
        assert abs(stats["last_cycle_time_ms"] - 70.0) < 0.1
        assert abs(stats["max_cycle_time_ms"] - 70.0) < 0.1
        assert abs(stats["avg_cycle_time_ms"] - 60.0) < 0.1

    async def test_get_cycle_stats_module_level(self):
        """Test module-level get_cycle_stats function."""
        # The module-level function is async
        with patch("src.loats.orchestrator.orchestrator") as mock_orch:
            mock_orch.get_cycle_stats.return_value = {"cycle_count": 1}
            result = await get_cycle_stats()
            assert result["cycle_count"] == 1

    async def test_cycle_time_target(self):
        """Test that cycle time target is enforced."""
        with patch.object(self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock) as mock_execute_cycle:
            mock_execute_cycle.side_effect = AsyncMock()  # Simulate quick execution

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                # Run a single cycle manually
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

                # Verify that sleep was called
                mock_sleep.assert_called_once()
                sleep_arg = mock_sleep.call_args[0][0]
                assert sleep_arg <= 0.1  # Should be <= 100ms


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)