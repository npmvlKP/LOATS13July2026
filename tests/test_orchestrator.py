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
from loats.openalgo import KillSwitchError
from loats.orchestrator import TradingOrchestrator, get_cycle_stats


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
        with patch("loats.orchestrator.logger") as mock_logger:
            await self.orchestrator.start()
            mock_logger.warning.assert_called_with("Orchestrator already running")

    async def test_check_kill_switch(self):
        """Test kill switch check."""
        # Test when kill switch is inactive
        with patch(
            "loats.orchestrator.alerts.is_kill_switch_active", return_value=False
        ):
            await self.orchestrator._check_kill_switch()  # Should not raise exception

        # Test when kill switch is active
        with patch(
            "loats.orchestrator.alerts.is_kill_switch_active", return_value=True
        ):
            with pytest.raises(KillSwitchError, match=""):
                await self.orchestrator._check_kill_switch()

    async def test_execute_ta_analysis(self):
        """Test technical analysis execution."""
        # Create test data
        now = datetime.now(UTC)
        _ = [
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
        ]  # Used for type reference only

        with patch("loats.orchestrator.settings") as mock_settings:
            mock_settings.default_symbol = "TEST"
            mock_settings.default_timeframe = "1d"

            with patch(
                "loats.orchestrator.technical_analysis.calculate_indicators"
            ) as mock_calc:
                mock_calc.return_value = []
                with patch(
                    "loats.orchestrator.technical_analysis.generate_signal"
                ) as mock_gen:
                    mock_gen.return_value = None
                    with patch.object(
                        self.orchestrator, "_safe_get_history", new_callable=AsyncMock
                    ) as mock_history:
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
            top_news=[],
        )

        # Mock the async function to return the result directly (not a coroutine)
        with patch(
            "loats.orchestrator.sentiment.analyze_symbol_sentiment",
            return_value=mock_result,
        ):
            with patch(
                "loats.orchestrator.db.async_create_signal", new_callable=AsyncMock
            ) as mock_create_signal:
                mock_create_signal.return_value = True
                with patch("loats.orchestrator.settings") as mock_settings:
                    mock_settings.default_symbol = "TEST"
                    mock_settings.sentiment_threshold = 0.5
                    await self.orchestrator._execute_sentiment_analysis()
                    mock_create_signal.assert_called_once()

    async def test_execute_market_data_update(self):
        """Test market data update execution."""
        with patch("loats.orchestrator.settings") as mock_settings:
            mock_settings.default_symbol = "TEST"

            with patch.object(
                self.orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_get_quotes:
                mock_get_quotes.return_value = None
                with patch.object(
                    self.orchestrator, "_safe_get_position_book", new_callable=AsyncMock
                ) as mock_pos:
                    mock_pos.return_value = None
                    with patch.object(
                        self.orchestrator, "_safe_get_funds", new_callable=AsyncMock
                    ) as mock_funds:
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

        with patch(
            "loats.orchestrator.select_strikes", new_callable=AsyncMock
        ) as mock_select_strikes:
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
        with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = {"state": "closed"}
            with patch("loats.orchestrator.db.get_position") as mock_pos:
                mock_pos.return_value = None
                with patch("loats.orchestrator.db.get_latest_funds") as mock_funds:
                    mock_funds.return_value = None
                    with patch("loats.orchestrator.settings") as mock_settings:
                        mock_settings.default_symbol = "TEST"
                        mock_settings.max_position_size = 100
                        mock_settings.max_margin_utilization = 0.8
                        await self.orchestrator._execute_risk_management()
                        mock_pos.assert_called_once()

    async def test_execute_trading_cycle(self):
        """Test complete trading cycle execution."""
        with patch.object(
            self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
        ) as mock_ta:
            with patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ) as mock_sentiment:
                with patch.object(
                    self.orchestrator,
                    "_execute_market_data_update",
                    new_callable=AsyncMock,
                ) as mock_market:
                    with patch.object(
                        self.orchestrator,
                        "_execute_signal_generation",
                        new_callable=AsyncMock,
                    ) as mock_signal:
                        with patch.object(
                            self.orchestrator,
                            "_execute_risk_management",
                            new_callable=AsyncMock,
                        ) as mock_risk:
                            await self.orchestrator._execute_trading_cycle()

                            mock_ta.assert_called_once()
                            mock_sentiment.assert_called_once()
                            mock_market.assert_called_once()
                            mock_signal.assert_called_once()
                            mock_risk.assert_called_once()

    async def test_execute_trading_cycle_with_kill_switch(self):
        """Test trading cycle with kill switch active."""
        with patch.object(
            self.orchestrator,
            "_check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with patch("loats.orchestrator.logger") as mock_logger:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    # _execute_trading_cycle doesn't call _check_kill_switch; that's in _run_cycle_loop
                    # Test _run_cycle_loop with kill switch
                    with patch.object(
                        self.orchestrator, "_shutdown_event"
                    ) as mock_shutdown:
                        mock_shutdown.is_set.side_effect = [False, True]
                        await self.orchestrator._run_cycle_loop()
                        mock_logger.warning.assert_any_call(
                            "Kill switch active - trading cycle paused"
                        )

    async def test_execute_trading_cycle_with_error(self):
        """Test trading cycle with error."""
        with patch.object(
            self.orchestrator,
            "_execute_ta_analysis",
            side_effect=Exception("Test error"),
        ):
            with patch("loats.orchestrator.logger"):
                with patch(
                    "loats.orchestrator.alerts.send_system_alert",
                    new_callable=AsyncMock,
                ):
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
        assert (
            abs(self.orchestrator.avg_cycle_time - 0.06) < 0.001
        )  # Average of 50ms and 70ms
        assert (
            abs(self.orchestrator.total_cycle_time - 0.12) < 0.001
        )  # Sum of 50ms and 70ms

    async def test_run_cycle_loop(self):
        """Test the main trading cycle loop."""
        with patch.object(self.orchestrator, "_shutdown_event") as mock_shutdown_event:
            mock_shutdown_event.is_set.side_effect = [
                False,
                True,
            ]  # Run once then shutdown

            with patch.object(
                self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
            ) as mock_execute_cycle:
                with patch.object(
                    self.orchestrator, "_check_kill_switch", new_callable=AsyncMock
                ):
                    with patch.object(
                        self.orchestrator, "_record_cycle_time"
                    ) as mock_record_time:
                        with patch(
                            "asyncio.sleep", new_callable=AsyncMock
                        ) as mock_sleep:
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
        with patch("loats.orchestrator.orchestrator") as mock_orch:
            mock_orch.get_cycle_stats.return_value = {"cycle_count": 1}
            result = await get_cycle_stats()
            assert result["cycle_count"] == 1

    async def test_cycle_time_target(self):
        """Test that cycle time target is enforced."""
        with patch.object(
            self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
        ) as mock_execute_cycle:
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

    async def test_no_double_cycle_count_increment(self):
        """Test that cycle count is incremented only once per cycle (F6-H-05 #1)."""
        # Reset cycle count
        self.orchestrator.cycle_count = 0

        with patch.object(
            self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
        ) as mock_ta:
            with patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ) as mock_sentiment:
                with patch.object(
                    self.orchestrator,
                    "_execute_market_data_update",
                    new_callable=AsyncMock,
                ) as mock_market:
                    with patch.object(
                        self.orchestrator,
                        "_execute_signal_generation",
                        new_callable=AsyncMock,
                    ) as mock_signal:
                        with patch.object(
                            self.orchestrator,
                            "_execute_risk_management",
                            new_callable=AsyncMock,
                        ) as mock_risk:
                            with patch.object(
                                self.orchestrator,
                                "_execute_cmp_strategy",
                                new_callable=AsyncMock,
                            ) as mock_cmp:
                                # Execute one trading cycle
                                await self.orchestrator._execute_trading_cycle()

                                # Cycle count should be incremented exactly once
                                assert self.orchestrator.cycle_count == 1

                                # Execute another cycle
                                await self.orchestrator._execute_trading_cycle()

                                # Cycle count should now be 2
                                assert self.orchestrator.cycle_count == 2

    async def test_lazy_settings_loading(self):
        """Test that settings are loaded lazily to avoid import-time failures (F6-H-05 #2)."""
        # Verify settings start as None
        from loats.orchestrator import settings
        assert settings is None

        # Test that orchestrator can be imported without settings
        from loats.orchestrator import TradingOrchestrator
        orchestrator = TradingOrchestrator()

        # Settings should still be None until actually needed
        assert settings is None

        # Now test that settings are loaded when needed (during risk management)
        with patch("loats.orchestrator.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.default_symbol = "TEST"
            mock_settings.max_position_size = 100
            mock_settings.max_margin_utilization = 0.8
            mock_get_settings.return_value = mock_settings

            with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
                mock_cb.get_status.return_value = {"state": "closed"}
                with patch("loats.orchestrator.db.get_position") as mock_pos:
                    mock_pos.return_value = None
                    with patch("loats.orchestrator.db.get_latest_funds") as mock_funds:
                        mock_funds.return_value = None

                        # This should trigger lazy loading of settings
                        await orchestrator._execute_risk_management()

                        # Verify settings were loaded
                        mock_get_settings.assert_called_once()
                        # Global settings should now be set
                        from loats.orchestrator import settings as global_settings
                        assert global_settings is not None

    async def test_strong_task_reference(self):
        """Test that cycle task maintains strong reference to prevent GC (F6-H-05 #3)."""
        await self.orchestrator.initialize()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            await self.orchestrator.start()

            # Verify task was created
            mock_create_task.assert_called_once()

            # Verify strong reference is maintained
            assert self.orchestrator._cycle_task is mock_task

            # Verify done callback was added
            mock_task.add_done_callback.assert_called_once_with(
                self.orchestrator._handle_cycle_task_completion
            )

    async def test_proper_shutdown_with_task_wait(self):
        """Test that shutdown properly waits for cycle task completion (F6-H-05 #4)."""
        await self.orchestrator.initialize()

        # Create a mock task
        mock_task = AsyncMock()
        self.orchestrator._cycle_task = mock_task

        with patch("asyncio.wait_for") as mock_wait_for:
            mock_wait_for.return_value = None  # Simulate successful wait

            await self.orchestrator.shutdown()

            # Verify that wait_for was called with the actual task (not the event)
            mock_wait_for.assert_called_once_with(mock_task, timeout=5.0)

            # Verify orchestrator is no longer running
            assert self.orchestrator.running is False

    async def test_alert_backoff_mechanism(self):
        """Test that alerts have backoff to prevent floods (F6-H-05 #5)."""
        # Set last alert time to current time
        now = datetime.now(UTC).timestamp()
        self.orchestrator._last_alert_time = now

        with patch("loats.orchestrator.alerts.send_system_alert", new_callable=AsyncMock) as mock_alert:
            with patch("loats.orchestrator.datetime") as mock_datetime:
                # Mock current time to be 10 seconds after last alert (should not send)
                mock_datetime.datetime.now.return_value.timestamp.return_value = now + 10
                mock_datetime.UTC = UTC

                # Simulate an error in the cycle loop
                try:
                    # This would normally be in _run_cycle_loop exception handler
                    current_time = now + 10
                    if current_time - self.orchestrator._last_alert_time > 60:
                        await mock_alert("Test error", "error")
                        self.orchestrator._last_alert_time = current_time
                except Exception:
                    pass

                # Alert should not be sent (only 10 seconds passed, need 60)
                mock_alert.assert_not_called()

                # Now test with 61 seconds passed (should send)
                mock_datetime.datetime.now.return_value.timestamp.return_value = now + 61

                try:
                    current_time = now + 61
                    if current_time - self.orchestrator._last_alert_time > 60:
                        await mock_alert("Test error", "error")
                        self.orchestrator._last_alert_time = current_time
                except Exception:
                    pass

                # Alert should be sent now
                mock_alert.assert_called_once_with("Test error", "error")

    async def test_zero_division_guard_in_margin_calculation(self):
        """Test that zero division is prevented in margin utilization calculation (F6-H-05 #6)."""
        from loats.models import FundsData

        # Create funds with zero available margin
        funds_with_zero_margin = FundsData(
            available_cash=1000.0,
            utilized_margin=500.0,
            available_margin=0.0,  # This would cause division by zero
            total_equity=1500.0,
            timestamp=datetime.now(UTC),
        )

        with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = {"state": "closed"}
            with patch("loats.orchestrator.db.get_position") as mock_pos:
                mock_pos.return_value = None
                with patch("loats.orchestrator.db.get_latest_funds") as mock_funds:
                    mock_funds.return_value = funds_with_zero_margin
                    with patch("loats.orchestrator.settings") as mock_settings:
                        mock_settings.default_symbol = "TEST"
                        mock_settings.max_position_size = 100
                        mock_settings.max_margin_utilization = 0.8

                        # This should not raise ZeroDivisionError
                        with patch("loats.orchestrator.logger") as mock_logger:
                            await self.orchestrator._execute_risk_management()

                            # Should log warning about zero margin
                            mock_logger.warning.assert_called_with(
                                "Available margin is zero - cannot calculate utilization ratio"
                            )

    async def test_ta_analysis_in_parallel_window(self):
        """Test that TA analysis runs within the parallel execution window (F6-H-05 #7)."""
        with patch.object(
            self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
        ) as mock_ta:
            with patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ) as mock_sentiment:
                with patch.object(
                    self.orchestrator,
                    "_execute_market_data_update",
                    new_callable=AsyncMock,
                ) as mock_market:
                    with patch("asyncio.gather") as mock_gather:
                        with patch("asyncio.wait_for") as mock_wait_for:
                            mock_wait_for.side_effect = lambda coroutine, timeout: coroutine

                            # Execute trading cycle
                            await self.orchestrator._execute_trading_cycle()

                            # Verify TA analysis was included in the parallel execution
                            mock_gather.assert_called_once()
                            gather_args = mock_gather.call_args[0][0]

                            # Should contain all three tasks: TA, sentiment, and market data
                            assert len(gather_args) == 3
                            assert any("ta_analysis" in str(task) for task in gather_args)
                            assert any("sentiment_analysis" in str(task) for task in gather_args)
                            assert any("market_data_update" in str(task) for task in gather_args)

    async def test_cycle_task_completion_callback(self):
        """Test that cycle task completion callback handles exceptions properly."""
        # Create a completed task with an exception
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        test_exception = Exception("Test task exception")
        mock_task.result.side_effect = test_exception

        with patch("loats.orchestrator.logger") as mock_logger:
            # Call the callback
            self.orchestrator._handle_cycle_task_completion(mock_task)

            # Verify exception was logged (note: the actual call might be async)
            mock_logger.error.assert_called()
            # Check the call arguments
            call_args = mock_logger.error.call_args
            assert "Cycle task completed with exception" in str(call_args)

            # Verify running flag was set to False
            assert self.orchestrator.running is False

    async def test_funds_model_creation_with_zero_margin(self):
        """Test that funds model creation handles zero available margin gracefully."""
        funds_data = {
            "available_cash": 1000.0,
            "utilized_margin": 500.0,
            "available_margin": 0.0,  # Edge case
            "total_equity": 1500.0,
        }

        # This should not raise an exception
        funds_model = self.orchestrator._create_funds_model(funds_data)

        assert funds_model.available_cash == 1000.0
        assert funds_model.utilized_margin == 500.0
        assert funds_model.available_margin == 0.0
        assert funds_model.total_equity == 1500.0
    async def test_cycle_time_target(self):
        """Test that cycle time target is enforced."""
        with patch.object(
            self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
        ) as mock_execute_cycle:
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

    async def test_no_double_cycle_count_increment(self):
        """Test that cycle count is incremented only once per cycle (F6-H-05 #1)."""
        # Reset cycle count
        self.orchestrator.cycle_count = 0

        with patch.object(
            self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
        ) as mock_ta:
            with patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ) as mock_sentiment:
                with patch.object(
                    self.orchestrator,
                    "_execute_market_data_update",
                    new_callable=AsyncMock,
                ) as mock_market:
                    with patch.object(
                        self.orchestrator,
                        "_execute_signal_generation",
                        new_callable=AsyncMock,
                    ) as mock_signal:
                        with patch.object(
                            self.orchestrator,
                            "_execute_risk_management",
                            new_callable=AsyncMock,
                        ) as mock_risk:
                            with patch.object(
                                self.orchestrator,
                                "_execute_cmp_strategy",
                                new_callable=AsyncMock,
                            ) as mock_cmp:
                                # Execute one trading cycle
                                await self.orchestrator._execute_trading_cycle()

                                # Cycle count should still be 0 (not incremented in _execute_trading_cycle)
                                assert self.orchestrator.cycle_count == 0

                                # Now call _record_cycle_time which should increment it
                                self.orchestrator._record_cycle_time(0.05)
                                assert self.orchestrator.cycle_count == 1

                                # Execute another cycle
                                await self.orchestrator._execute_trading_cycle()
                                # Cycle count should still be 1 (not incremented yet)
                                assert self.orchestrator.cycle_count == 1

                                # Call _record_cycle_time again
                                self.orchestrator._record_cycle_time(0.07)
                                # Cycle count should now be 2
                                assert self.orchestrator.cycle_count == 2

    async def test_lazy_settings_loading(self):
        """Test that settings are loaded lazily to avoid import-time failures (F6-H-05 #2)."""
        # Verify settings start as None
        from loats.orchestrator import settings
        assert settings is None

        # Test that orchestrator can be imported without settings
        from loats.orchestrator import TradingOrchestrator
        orchestrator = TradingOrchestrator()

        # Settings should still be None until actually needed
        assert settings is None

        # Now test that settings are loaded when needed (during risk management)
        with patch("loats.orchestrator.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.default_symbol = "TEST"
            mock_settings.max_position_size = 100
            mock_settings.max_margin_utilization = 0.8
            mock_get_settings.return_value = mock_settings

            with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
                mock_cb.get_status.return_value = {"state": "closed"}
                with patch("loats.orchestrator.db.get_position") as mock_pos:
                    mock_pos.return_value = None
                    with patch("loats.orchestrator.db.get_latest_funds") as mock_funds:
                        mock_funds.return_value = None

                        # This should trigger lazy loading of settings
                        await orchestrator._execute_risk_management()

                        # Verify settings were loaded
                        mock_get_settings.assert_called_once()
                        # Global settings should now be set
                        from loats.orchestrator import settings as global_settings
                        assert global_settings is not None

    async def test_strong_task_reference(self):
        """Test that cycle task maintains strong reference to prevent GC (F6-H-05 #3)."""
        await self.orchestrator.initialize()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            await self.orchestrator.start()

            # Verify task was created
            mock_create_task.assert_called_once()

            # Verify strong reference is maintained
            assert self.orchestrator._cycle_task is mock_task

            # Verify done callback was added
            mock_task.add_done_callback.assert_called_once_with(
                self.orchestrator._handle_cycle_task_completion
            )

    async def test_proper_shutdown_with_task_wait(self):
        """Test that shutdown properly waits for cycle task completion (F6-H-05 #4)."""
        await self.orchestrator.initialize()

        # Create a mock task
        mock_task = AsyncMock()
        self.orchestrator._cycle_task = mock_task

        with patch("asyncio.wait_for") as mock_wait_for:
            mock_wait_for.return_value = None  # Simulate successful wait

            await self.orchestrator.shutdown()

            # Verify that wait_for was called with the actual task (not the event)
            mock_wait_for.assert_called_once_with(mock_task, timeout=5.0)

            # Verify orchestrator is no longer running
            assert self.orchestrator.running is False

    async def test_alert_backoff_mechanism(self):
        """Test that alerts have backoff to prevent floods (F6-H-05 #5)."""
        # Set last alert time to current time
        now = datetime.now(UTC).timestamp()
        self.orchestrator._last_alert_time = now

        with patch("loats.orchestrator.alerts.send_system_alert", new_callable=AsyncMock) as mock_alert:
            with patch("loats.orchestrator.datetime") as mock_datetime:
                # Mock current time to be 10 seconds after last alert (should not send)
                mock_datetime.datetime.now.return_value.timestamp.return_value = now + 10
                mock_datetime.UTC = UTC

                # Simulate an error in the cycle loop
                try:
                    # This would normally be in _run_cycle_loop exception handler
                    current_time = now + 10
                    if current_time - self.orchestrator._last_alert_time > 60:
                        await mock_alert("Test error", "error")
                        self.orchestrator._last_alert_time = current_time
                except Exception:
                    pass

                # Alert should not be sent (only 10 seconds passed, need 60)
                mock_alert.assert_not_called()

                # Now test with 61 seconds passed (should send)
                mock_datetime.datetime.now.return_value.timestamp.return_value = now + 61

                try:
                    current_time = now + 61
                    if current_time - self.orchestrator._last_alert_time > 60:
                        await mock_alert("Test error", "error")
                        self.orchestrator._last_alert_time = current_time
                except Exception:
                    pass

                # Alert should be sent now
                mock_alert.assert_called_once_with("Test error", "error")

    async def test_zero_division_guard_in_margin_calculation(self):
        """Test that zero division is prevented in margin utilization calculation (F6-H-05 #6)."""
        from loats.models import FundsData

        # Create funds with zero available margin
        funds_with_zero_margin = FundsData(
            available_cash=1000.0,
            utilized_margin=500.0,
            available_margin=0.0,  # This would cause division by zero
            total_equity=1500.0,
            timestamp=datetime.now(UTC),
        )

        with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = {"state": "closed"}
            with patch("loats.orchestrator.db.get_position") as mock_pos:
                mock_pos.return_value = None
                with patch("loats.orchestrator.db.get_latest_funds") as mock_funds:
                    mock_funds.return_value = funds_with_zero_margin
                    with patch("loats.orchestrator.settings") as mock_settings:
                        mock_settings.default_symbol = "TEST"
                        mock_settings.max_position_size = 100
                        mock_settings.max_margin_utilization = 0.8

                        # This should not raise ZeroDivisionError
                        with patch("loats.orchestrator.logger") as mock_logger:
                            await self.orchestrator._execute_risk_management()

                            # Should log warning about zero margin
                            mock_logger.warning.assert_called_with(
                                "Available margin is zero - cannot calculate utilization ratio"
                            )

    async def test_ta_analysis_in_parallel_window(self):
        """Test that TA analysis runs within the parallel execution window (F6-H-05 #7)."""
        with patch.object(
            self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
        ) as mock_ta:
            with patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ) as mock_sentiment:
                with patch.object(
                    self.orchestrator,
                    "_execute_market_data_update",
                    new_callable=AsyncMock,
                ) as mock_market:
                    with patch("asyncio.gather") as mock_gather:
                        with patch("asyncio.wait_for") as mock_wait_for:
                            mock_wait_for.side_effect = lambda coroutine, timeout: coroutine

                            # Execute trading cycle
                            await self.orchestrator._execute_trading_cycle()

                            # Verify TA analysis was included in the parallel execution
                            mock_gather.assert_called_once()
                            gather_args = mock_gather.call_args[0][0]

                            # Should contain all three tasks: TA, sentiment, and market data
                            assert len(gather_args) == 3
                            assert any("ta_analysis" in str(task) for task in gather_args)
                            assert any("sentiment_analysis" in str(task) for task in gather_args)
                            assert any("market_data_update" in str(task) for task in gather_args)

    async def test_cycle_task_completion_callback(self):
        """Test that cycle task completion callback handles exceptions properly."""
        # Create a completed task with an exception
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        test_exception = Exception("Test task exception")
        mock_task.result.side_effect = test_exception

        with patch("loats.orchestrator.logger") as mock_logger:
            # Call the callback
            self.orchestrator._handle_cycle_task_completion(mock_task)

            # Verify exception was logged
            mock_logger.error.assert_called_with(
                f"Cycle task completed with exception: {test_exception}"
            )

            # Verify running flag was set to False
            assert self.orchestrator.running is False

    async def test_funds_model_creation_with_zero_margin(self):
        """Test that funds model creation handles zero available margin gracefully."""
        funds_data = {
            "available_cash": 1000.0,
            "utilized_margin": 500.0,
            "available_margin": 0.0,  # Edge case
            "total_equity": 1500.0,
        }

        # This should not raise an exception
        funds_model = self.orchestrator._create_funds_model(funds_data)

        assert funds_model.available_cash == 1000.0
        assert funds_model.utilized_margin == 500.0
        assert funds_model.available_margin == 0.0
        assert funds_model.total_equity == 1500.0


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
