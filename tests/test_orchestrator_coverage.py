"""
Additional coverage tests for orchestrator.py module.
Focuses on missing coverage areas to improve coverage of the orchestrator.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from loats.config import get_settings
from loats.orchestrator import TradingOrchestrator, validate_rss_feed


class TestValidateRSSFeed:
    """Test suite for validate_rss_feed function."""

    @pytest.mark.asyncio
    async def test_validate_rss_feed_valid_url(self):
        """Test validate_rss_feed with valid RSS feed URL."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/rss+xml"}
            mock_response.text = (
                '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
            )
            mock_client.get.return_value = mock_response

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_rss_feed_valid_url_with_feed_tag(self):
        """Test validate_rss_feed with valid URL containing <feed> tag."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/xml"}
            mock_response.text = (
                '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
            )
            mock_client.get.return_value = mock_response

            result = await validate_rss_feed("https://example.com/feed.atom")
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_rss_feed_invalid_url_format(self):
        """Test validate_rss_feed with invalid URL format."""
        result = await validate_rss_feed("invalid-url")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_unsupported_scheme(self):
        """Test validate_rss_feed with unsupported URL scheme."""
        result = await validate_rss_feed("ftp://example.com/feed.rss")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_connection_timeout(self):
        """Test validate_rss_feed with connection timeout."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client.get.side_effect = httpx.ConnectTimeout("Connection timeout")

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_read_timeout(self):
        """Test validate_rss_feed with read timeout."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client.get.side_effect = httpx.ReadTimeout("Read timeout")

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_http_error(self):
        """Test validate_rss_feed with HTTP error."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.get.return_value = mock_response

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_non_rss_content(self):
        """Test validate_rss_feed with non-RSS content."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = "<html><body>Not an RSS feed</body></html>"
            mock_client.get.return_value = mock_response

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_general_exception(self):
        """Test validate_rss_feed with general exception."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client.get.side_effect = Exception("Unexpected error")

            result = await validate_rss_feed("https://example.com/feed.rss")
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_rss_feed_timeout_parameter(self):
        """Test validate_rss_feed with custom timeout."""
        with patch("loats.orchestrator.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/rss+xml"}
            mock_response.text = '<?xml version="1.0"?><rss version="2.0"></rss>'
            mock_client.get.return_value = mock_response

            result = await validate_rss_feed("https://example.com/feed.rss", timeout=10)
            assert result is True
            mock_client_class.assert_called_with(timeout=10)


class TestTradingOrchestratorCoverage(unittest.IsolatedAsyncioTestCase):
    """Additional coverage tests for TradingOrchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = TradingOrchestrator()

    async def test_execute_trading_cycle_with_timeout(self):
        """_execute_trading_cycle cancels unfinished tasks on timeout."""
        with (
            patch.object(
                self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_market_data_update", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_signal_generation", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_risk_management", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_cmp_strategy", new_callable=AsyncMock
            ),
            patch("loats.orchestrator.asyncio.create_task") as mock_create_task,
            patch("loats.orchestrator.asyncio.gather") as mock_gather,
            patch("loats.orchestrator.asyncio.wait_for") as mock_wait_for,
        ):
            # Simulate wait_for raising TimeoutError after gather
            mock_wait_for.side_effect = TimeoutError("Task timeout")

            # Tasks must expose done()/cancel() like real asyncio tasks
            ta_task = MagicMock()
            sentiment_task = MagicMock()
            market_data_task = MagicMock()
            for task in (ta_task, sentiment_task, market_data_task):
                task.done.return_value = False

            # create_task is mocked, so the AsyncMock coroutines are never
            # awaited; capture them for explicit close to avoid RuntimeWarnings.
            created_coroutines = []
            task_iter = iter([ta_task, sentiment_task, market_data_task])

            def fake_create_task(coro):
                created_coroutines.append(coro)
                return next(task_iter)

            mock_create_task.side_effect = fake_create_task

            gather_future = asyncio.Future()
            gather_future.set_result(None)
            mock_gather.return_value = gather_future

            with patch(
                "loats.orchestrator.rules_engine.is_trading_allowed",
                return_value=True,
            ):
                await self.orchestrator._execute_trading_cycle()

            # Verify unfinished tasks were cancelled
            ta_task.cancel.assert_called_once()
            sentiment_task.cancel.assert_called_once()
            market_data_task.cancel.assert_called_once()

            # Close un-awaited mock coroutines to prevent RuntimeWarnings
            for coro in created_coroutines:
                coro.close()

    async def test_execute_trading_cycle_with_exception(self):
        """_execute_trading_cycle re-raises exceptions from sequential steps."""
        with (
            patch.object(
                self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_market_data_update", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_signal_generation", new_callable=AsyncMock
            ),
            patch.object(self.orchestrator, "_execute_risk_management") as mock_risk,
        ):
            mock_risk.side_effect = ValueError("Test error")

            with patch(
                "loats.orchestrator.rules_engine.is_trading_allowed",
                return_value=True,
            ):
                with self.assertRaises(ValueError):
                    await self.orchestrator._execute_trading_cycle()

    async def test_execute_trading_cycle_trading_not_allowed(self):
        """_execute_trading_cycle skips CMP strategy outside trading session."""
        with (
            patch.object(
                self.orchestrator, "_execute_ta_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_sentiment_analysis", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_market_data_update", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_signal_generation", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_risk_management", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_cmp_strategy", new_callable=AsyncMock
            ),
        ):
            with patch(
                "loats.orchestrator.rules_engine.is_trading_allowed",
                return_value=False,
            ):
                with patch("loats.orchestrator.logger") as mock_logger:
                    await self.orchestrator._execute_trading_cycle()

                    self.orchestrator._execute_cmp_strategy.assert_not_called()
                    mock_logger.debug.assert_called()

    async def test_run_cycle_loop_with_kill_switch(self):
        """_run_cycle_loop sleeps at reduced polling while kill switch active."""
        from loats.openalgo import KillSwitchError

        def stop_loop(_delay):
            # First sleep happens inside the kill-switch branch; stop the
            # while-loop so exactly one iteration runs.
            self.orchestrator._shutdown_event.set()

        with (
            patch.object(
                self.orchestrator, "_check_kill_switch"
            ) as mock_check_kill_switch,
            patch.object(
                self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
            ),
            patch("loats.orchestrator.asyncio.sleep") as mock_sleep,
        ):
            mock_check_kill_switch.side_effect = KillSwitchError()
            mock_sleep.side_effect = stop_loop

            await self.orchestrator._run_cycle_loop()

            mock_check_kill_switch.assert_called()
            mock_sleep.assert_any_call(1.0)

    async def test_run_cycle_loop_with_exception(self):
        """_run_cycle_loop sends throttled system alert on cycle error."""
        with (
            patch.object(
                self.orchestrator, "_check_kill_switch", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
            ),
            patch("loats.orchestrator.asyncio.sleep") as mock_sleep,
            patch("loats.orchestrator.alerts.send_system_alert") as mock_send_alert,
        ):
            self.orchestrator._execute_trading_cycle.side_effect = ValueError(
                "Test error"
            )

            def stop_loop(_delay):
                self.orchestrator._shutdown_event.set()

            mock_sleep.side_effect = stop_loop

            await self.orchestrator._run_cycle_loop()

            mock_send_alert.assert_called_once()
            mock_send_alert.assert_called_with(
                "Trading cycle error: Test error", "error"
            )

    async def test_record_cycle_time(self):
        """Test _record_cycle_time method."""
        with patch("loats.orchestrator.record_cycle_time") as mock_record:
            self.orchestrator._record_cycle_time(0.05)  # 50ms cycle

            mock_record.assert_called_once_with(0.05)

            assert self.orchestrator.cycle_count == 1
            assert self.orchestrator.last_cycle_time == 0.05
            assert self.orchestrator.max_cycle_time == 0.05
            assert self.orchestrator.total_cycle_time == 0.05
            assert self.orchestrator.avg_cycle_time == 0.05

    async def test_record_cycle_time_multiple_cycles(self):
        """Test _record_cycle_time with multiple cycles."""
        with patch("loats.orchestrator.record_cycle_time"):
            self.orchestrator._record_cycle_time(0.05)  # 50ms
            self.orchestrator._record_cycle_time(0.08)  # 80ms
            self.orchestrator._record_cycle_time(0.12)  # 120ms

            assert self.orchestrator.cycle_count == 3
            assert self.orchestrator.last_cycle_time == 0.12
            assert self.orchestrator.max_cycle_time == 0.12
            assert abs(self.orchestrator.total_cycle_time - 0.25) < 1e-9
            assert abs(self.orchestrator.avg_cycle_time - 0.0833) < 0.001

    async def test_handle_cycle_task_completion(self):
        """_handle_cycle_task_completion logs nothing for successful tasks."""
        task = MagicMock()
        task.done.return_value = True
        task.exception.return_value = None
        task.result.return_value = None

        with patch("loats.orchestrator.logger") as mock_logger:
            self.orchestrator._handle_cycle_task_completion(task)

            mock_logger.info.assert_not_called()
            mock_logger.error.assert_not_called()

    async def test_handle_cycle_task_completion_with_exception(self):
        """_handle_cycle_task_completion logs and re-raises task exceptions."""
        task = MagicMock()
        task.done.return_value = True
        task.result.side_effect = ValueError("Task failed")

        with patch("loats.orchestrator.logger") as mock_logger:
            with self.assertRaises(ValueError):
                self.orchestrator._handle_cycle_task_completion(task)

            mock_logger.error.assert_called()

    async def test_shutdown(self):
        """Test shutdown method."""
        self.orchestrator.running = True

        # Use a real completed task: shutdown awaits it via asyncio.wait_for
        loop = asyncio.get_event_loop()
        cycle_task = loop.create_task(asyncio.sleep(0))
        await cycle_task
        self.orchestrator._cycle_task = cycle_task

        with patch("loats.orchestrator.logger") as mock_logger:
            await self.orchestrator.shutdown()

            assert self.orchestrator._shutdown_event.is_set()
            assert self.orchestrator.running is False
            mock_logger.info.assert_any_call("TradingOrchestrator shutdown complete")

    async def test_shutdown_not_running(self):
        """Test shutdown when orchestrator is not running."""
        with patch("loats.orchestrator.logger") as mock_logger:
            await self.orchestrator.shutdown()

            mock_logger.info.assert_not_called()


class TestTradingOrchestratorEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Edge case tests for TradingOrchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = TradingOrchestrator()

    async def test_execute_ta_analysis(self):
        """_execute_ta_analysis fetches history and calculates indicators."""
        history = {
            "data": [
                {
                    "timestamp": "2023-01-01T09:15:00+00:00",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000,
                },
                {
                    "timestamp": "2023-01-01T09:16:00+00:00",
                    "open": 100.5,
                    "high": 102.0,
                    "low": 100.2,
                    "close": 101.5,
                    "volume": 1100,
                },
            ]
        }
        with (
            patch("loats.orchestrator.settings", get_settings()),
            patch.object(
                self.orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch(
                "loats.orchestrator.db.async_store_historical_data",
                new_callable=AsyncMock,
            ),
            patch(
                "loats.orchestrator.technical_analysis.calculate_indicators"
            ) as mock_calculate,
            patch.object(
                self.orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
        ):
            mock_history.return_value = history
            mock_calculate.return_value = []
            mock_quotes.return_value = None  # Skip signal generation branch

            await self.orchestrator._execute_ta_analysis()

            mock_calculate.assert_called_once()

    async def test_execute_ta_analysis_with_exception(self):
        """_execute_ta_analysis logs and re-raises indicator failures."""
        history = {
            "data": [
                {
                    "timestamp": "2023-01-01T09:15:00+00:00",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000,
                }
            ]
        }
        with (
            patch.object(
                self.orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch(
                "loats.orchestrator.db.async_store_historical_data",
                new_callable=AsyncMock,
            ),
            patch(
                "loats.orchestrator.technical_analysis.calculate_indicators"
            ) as mock_calculate,
        ):
            mock_history.return_value = history
            mock_calculate.side_effect = ValueError("TA error")

            with patch("loats.orchestrator.logger") as mock_logger:
                with self.assertRaises(ValueError):
                    await self.orchestrator._execute_ta_analysis()

                mock_logger.error.assert_called()

    async def test_execute_sentiment_analysis(self):
        """_execute_sentiment_analysis runs against validated feeds."""
        with (
            patch("loats.orchestrator.settings", get_settings()),
            patch(
                "loats.orchestrator.validate_rss_feed", new_callable=AsyncMock
            ) as mock_validate,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            from loats.models import SentimentAnalysisResult

            mock_validate.return_value = True
            # Real model instance: result.sentiment_score must be an attribute
            from datetime import UTC, datetime

            mock_analyze.return_value = SentimentAnalysisResult(
                symbol="NIFTY",
                timestamp=datetime.now(UTC),
                sentiment_score=0.0,
                sentiment_label="neutral",
                news_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                top_news=[],
            )

            await self.orchestrator._execute_sentiment_analysis()

            mock_analyze.assert_called_once()

    async def test_execute_market_data_update(self):
        """_execute_market_data_update fetches and stores quote data."""
        with (
            patch.object(
                self.orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_get_quotes,
            patch.object(
                self.orchestrator, "_safe_get_position_book", new_callable=AsyncMock
            ) as mock_positions,
            patch.object(
                self.orchestrator, "_safe_get_funds", new_callable=AsyncMock
            ) as mock_funds,
            patch(
                "loats.orchestrator.db.async_store_quote", new_callable=AsyncMock
            ) as mock_store_quote,
        ):
            mock_get_quotes.return_value = {"data": {"NIFTY": {"last_price": 100.0}}}
            mock_positions.return_value = None
            mock_funds.return_value = None

            await self.orchestrator._execute_market_data_update()

            mock_get_quotes.assert_called_once()
            mock_store_quote.assert_called_once()

    async def test_execute_signal_generation(self):
        """_execute_signal_generation combines TA and sentiment signals."""
        from datetime import UTC, datetime

        from loats.models import Signal as SignalModel
        from loats.models import SignalType

        ta_signal = SignalModel(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            indicators={"rsi": 55.0},
            timestamp=datetime.now(UTC),
        )
        sentiment_signal = SignalModel(
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.2,
            indicators={"sentiment_score": -0.3},
            timestamp=datetime.now(UTC),
        )

        with (
            patch(
                "loats.orchestrator.db.async_get_latest_signals", new_callable=AsyncMock
            ) as mock_get_signals,
            patch.object(
                self.orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch(
                "loats.orchestrator.db.async_create_signal", new_callable=AsyncMock
            ) as mock_create,
        ):
            # First call: ta signals; second call: sentiment signals
            mock_get_signals.side_effect = [[ta_signal], [sentiment_signal]]
            mock_quotes.return_value = {"data": {"NIFTY": {"last_price": 100.0}}}

            await self.orchestrator._execute_signal_generation()

            mock_get_signals.assert_called()
            mock_create.assert_called_once()

    async def test_execute_risk_management(self):
        """_execute_risk_management checks position and margin."""
        with (
            patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb,
            patch(
                "loats.orchestrator.asyncio.to_thread", new_callable=AsyncMock
            ) as mock_to_thread,
        ):
            mock_cb.get_status.return_value = {"state": "closed"}
            mock_to_thread.side_effect = [None, None]  # position, funds

            await self.orchestrator._execute_risk_management()

            # Position and funds both checked via to_thread
            assert mock_to_thread.call_count == 2

    async def test_execute_risk_management_circuit_open(self):
        """_execute_risk_management returns early when breaker open."""
        with (
            patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mock_cb,
            patch(
                "loats.orchestrator.asyncio.to_thread", new_callable=AsyncMock
            ) as mock_to_thread,
        ):
            mock_cb.get_status.return_value = {"state": "open"}

            await self.orchestrator._execute_risk_management()

            mock_to_thread.assert_not_called()

    async def test_execute_cmp_strategy(self):
        """_execute_cmp_strategy skips decision with insufficient signals."""
        with (
            patch(
                "loats.orchestrator.db.async_get_latest_signals", new_callable=AsyncMock
            ),
            patch(
                "loats.orchestrator.trade_decision_engine.create_trade_decision",
                new_callable=AsyncMock,
            ) as mock_create_decision,
        ):
            # AsyncMock default: empty list -> 0 recent signals -> early return
            await self.orchestrator._execute_cmp_strategy()

            mock_create_decision.assert_not_called()

    async def test_execute_cmp_strategy_few_signals_path(self):
        """CMP strategy early-returns when insufficient recent signals."""
        from datetime import UTC, datetime

        from loats.models import Signal as SignalModel
        from loats.models import SignalType

        recent = SignalModel(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.7,
            timestamp=datetime.now(UTC),
            indicators={},
        )

        with (
            patch(
                "loats.orchestrator.db.async_get_latest_signals", new_callable=AsyncMock
            ) as mock_get_signals,
            patch(
                "loats.orchestrator.trade_decision_engine.create_trade_decision",
                new_callable=AsyncMock,
            ) as mock_create_decision,
        ):
            mock_get_signals.return_value = [recent]  # 1 signal < 3 required

            await self.orchestrator._execute_cmp_strategy()

            mock_create_decision.assert_not_called()

    async def test_get_cycle_stats(self):
        """Test get_cycle_stats returns documented keys."""
        stats = self.orchestrator.get_cycle_stats()

        assert "cycle_count" in stats
        assert "last_cycle_time" in stats
        assert "last_cycle_time_ms" in stats
        assert "max_cycle_time" in stats
        assert "max_cycle_time_ms" in stats
        assert "avg_cycle_time" in stats
        assert "avg_cycle_time_ms" in stats
        assert "total_cycle_time" in stats
        assert "target_compliance" in stats

    async def test_cycle_time_enforcement(self):
        """_run_cycle_loop sleeps for the remaining budget after fast cycle."""
        with (
            patch.object(
                self.orchestrator, "_check_kill_switch", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_trading_cycle", new_callable=AsyncMock
            ),
            patch("loats.orchestrator.asyncio.sleep") as mock_sleep,
        ):

            def stop_loop(_delay):
                self.orchestrator._shutdown_event.set()

            mock_sleep.side_effect = stop_loop

            await self.orchestrator._run_cycle_loop()

            # Adaptive sleep: remaining budget = 0.1 - actual (near-zero) duration
            args, _ = mock_sleep.call_args
            sleep_value = args[0]
            assert isinstance(sleep_value, float)
            assert 0.0 <= sleep_value <= 0.1

    async def test_cycle_time_no_sleep_when_over_target(self):
        """_run_cycle_loop sleeps zero when cycle exceeds 100ms target."""

        # asyncio.sleep is mocked by the patch below, so the slow cycle uses a
        # blocking sleep to consume real wall-clock time.
        async def slow_cycle():
            time.sleep(0.15)  # Exceeds 100ms target

        with (
            patch.object(
                self.orchestrator, "_check_kill_switch", new_callable=AsyncMock
            ),
            patch.object(
                self.orchestrator, "_execute_trading_cycle", side_effect=slow_cycle
            ),
            patch("loats.orchestrator.asyncio.sleep") as mock_sleep,
        ):

            def stop_loop(_delay):
                self.orchestrator._shutdown_event.set()

            mock_sleep.side_effect = stop_loop

            await self.orchestrator._run_cycle_loop()

            # Cycle exceeded target: sleep_time = max(0, 0.1 - ~0.15) = 0.0
            args, _ = mock_sleep.call_args
            assert args[0] == 0.0
