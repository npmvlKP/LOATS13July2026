"""Comprehensive test suite for scheduler module coverage improvement.

This test suite targets specific lines that are missing coverage in scheduler.py.

F8-H-03 note: ta_scan and sentiment_scan were retired from the scheduler.
Coverage tests that exercised only those removed methods have been removed;
the remaining tests exercise the surviving scheduler behavior (market status,
cleanup, circuit-breaker helpers, etc.).
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.scheduler import TradingScheduler, scheduler


class TestSchedulerCoverage:
    """Comprehensive test suite for scheduler module coverage."""

    @pytest.fixture
    def scheduler_instance(self):
        """Create a TradingScheduler instance with mocked dependencies."""
        with patch("loats.scheduler.AsyncIOScheduler") as mock_aps:
            instance = TradingScheduler()
            instance.scheduler = mock_aps
            return instance

    @pytest.mark.asyncio
    async def test_is_market_open_weekday_during_hours(self, scheduler_instance):
        """Test is_market_open during market hours (lines 146-148)."""
        # Mock datetime to be during market hours on a weekday
        with patch("loats.scheduler.datetime") as mock_datetime:
            # Set up mock for weekday during market hours
            mock_now = datetime(2023, 1, 16, 10, 0, 0)  # Monday 10 AM
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            # Mock timezone
            with patch("loats.scheduler.ZoneInfo") as mock_zone:
                mock_tz = MagicMock()
                mock_zone.return_value = mock_tz

                result = scheduler_instance.is_market_open()
                assert result is True

    @pytest.mark.asyncio
    async def test_is_market_open_weekend(self, scheduler_instance):
        """Test is_market_open on weekend (lines 146-148)."""
        # Mock datetime to be on a weekend
        with patch("loats.scheduler.datetime") as mock_datetime:
            # Set up mock for weekend
            mock_now = datetime(2023, 1, 14, 10, 0, 0)  # Saturday 10 AM
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            result = scheduler_instance.is_market_open()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_market_open_holiday(self, scheduler_instance):
        """Test is_market_open on holiday (lines 146-148)."""
        # Mock datetime to be on a holiday
        with patch("loats.scheduler.datetime") as mock_datetime:
            # Set up mock for holiday (Republic Day 2026-01-26)
            mock_now = datetime(2026, 1, 26, 10, 0, 0)
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            result = scheduler_instance.is_market_open()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_market_open_before_hours(self, scheduler_instance):
        """Test is_market_open before market hours (lines 146-148)."""
        # Mock datetime to be before market hours
        with patch("loats.scheduler.datetime") as mock_datetime:
            # Set up mock for before market hours
            mock_now = datetime(2023, 1, 16, 8, 0, 0)  # Monday 8 AM
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            # Mock timezone
            with patch("loats.scheduler.ZoneInfo") as mock_zone:
                mock_tz = MagicMock()
                mock_zone.return_value = mock_tz

                result = scheduler_instance.is_market_open()
                assert result is False

    @pytest.mark.asyncio
    async def test_add_jobs_method(self, scheduler_instance):
        """Test _add_jobs method.

        F8-H-03: only support jobs (market_status_check, data_cleanup,
        backtest_sanity_check) are registered.
        """
        # Mock the add_job method
        mock_add_job = MagicMock()
        scheduler_instance.scheduler.add_job = mock_add_job

        await scheduler_instance._add_jobs()

        # _add_jobs registers market_status_check, data_cleanup, and
        # backtest_sanity_check only.
        assert mock_add_job.call_count == 3

        # Check that each job was added with correct parameters
        calls = mock_add_job.call_args_list
        for call in calls:
            args, kwargs = call
            assert "id" in kwargs
            assert "name" in kwargs
            assert "replace_existing" in kwargs

        job_ids = {kwargs["id"] for _, kwargs in calls}
        assert "market_status_check" in job_ids
        assert "data_cleanup" in job_ids
        assert "backtest_sanity_check" in job_ids
        assert "ta_scan" not in job_ids
        assert "sentiment_scan" not in job_ids

    @pytest.mark.asyncio
    async def test_shutdown_with_running_tasks(self, scheduler_instance):
        """Test shutdown method with running tasks (lines 236-239)."""
        # Mock scheduler methods
        scheduler_instance.scheduler.shutdown = MagicMock()
        scheduler_instance.running = True

        # Create proper async tasks that can be awaited
        async def mock_task_coro1():
            return None

        async def mock_task_coro2():
            return None

        # Create proper awaitable tasks
        mock_task1 = asyncio.ensure_future(mock_task_coro1())
        mock_task2 = asyncio.ensure_future(mock_task_coro2())

        # Mock the done() method
        mock_task1.done = MagicMock(return_value=False)
        mock_task2.done = MagicMock(return_value=False)

        # Mock the cancel() method
        mock_task1.cancel = MagicMock()
        mock_task2.cancel = MagicMock()

        scheduler_instance.scan_tasks = {"task1": mock_task1, "task2": mock_task2}

        await scheduler_instance.shutdown()

        # Verify tasks were cancelled
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()

        # Verify scheduler shutdown was called
        scheduler_instance.scheduler.shutdown.assert_called_once()
        assert scheduler_instance.running is False

    @pytest.mark.asyncio
    async def test_check_market_status_task(self, scheduler_instance):
        """Test check_market_status method."""

        # Mock the _market_status_check_task method with a lambda that returns None
        scheduler_instance._market_status_check_task = lambda: None

        # Mock asyncio.create_task to return a proper awaitable task
        with patch("asyncio.create_task") as mock_create_task:
            # Create a proper async task that can be awaited
            async def mock_task_coro():
                return None

            mock_task = asyncio.ensure_future(mock_task_coro())
            mock_create_task.return_value = mock_task

            # Mock the task to be stored in scan_tasks
            with patch.object(scheduler_instance, "scan_tasks", {}):
                await scheduler_instance.check_market_status()

                # Verify task was created and stored - check that it was called with a coroutine
                assert mock_create_task.called
                # The task should have been stored and then removed (due to try/finally)
                # So we just verify the create_task was called

    @pytest.mark.asyncio
    async def test_market_status_check_task_market_closed(self, scheduler_instance):
        """Test _market_status_check_task when market is closed."""
        # Mock is_market_open to return False
        scheduler_instance.is_market_open = MagicMock(return_value=False)

        # Mock scheduler.get_job and remove_job
        mock_get_job = MagicMock()
        mock_remove_job = MagicMock()
        scheduler_instance.scheduler.get_job = mock_get_job
        scheduler_instance.scheduler.remove_job = mock_remove_job

        # F8-H-03: signal-emitting jobs are retired; the market-status task only
        # needs to remove any stale signal jobs if they exist (defensive cleanup).
        mock_get_job.return_value = None

        await scheduler_instance._market_status_check_task()

        # No jobs should be removed because no stale signal jobs exist.
        mock_remove_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_market_status_check_task_market_open(self, scheduler_instance):
        """Test _market_status_check_task when market is open."""
        # Mock is_market_open to return True
        scheduler_instance.is_market_open = MagicMock(return_value=True)

        # Mock scheduler.get_job to return None (jobs don't exist)
        scheduler_instance.scheduler.get_job = MagicMock(return_value=None)

        # Mock add_job
        mock_add_job = MagicMock()
        scheduler_instance.scheduler.add_job = mock_add_job

        await scheduler_instance._market_status_check_task()

        # F8-H-03: market-status task no longer adds ta_scan/sentiment_scan jobs.
        # It only verifies the support jobs are registered.
        mock_add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_data_cleanup_task(self, scheduler_instance):
        """Test run_data_cleanup method."""

        # Mock the _data_cleanup_task method with a lambda that returns None
        scheduler_instance._data_cleanup_task = lambda: None

        # Mock asyncio.create_task to return a proper awaitable task
        with patch("asyncio.create_task") as mock_create_task:
            # Create a proper async task that can be awaited
            async def mock_task_coro():
                return None

            mock_task = asyncio.ensure_future(mock_task_coro())
            mock_create_task.return_value = mock_task

            # Mock the task to be stored in scan_tasks
            with patch.object(scheduler_instance, "scan_tasks", {}):
                await scheduler_instance.run_data_cleanup()

                # Verify task was created and stored - check that it was called with a coroutine
                assert mock_create_task.called
                # The task should have been stored and then removed (due to try/finally)
                # So we just verify the create_task was called

    @pytest.mark.asyncio
    async def test_data_cleanup_task(self, scheduler_instance):
        """Test _data_cleanup_task method."""
        # Mock database methods
        mock_cleanup = AsyncMock()
        mock_verify_audit = AsyncMock()
        mock_vacuum = AsyncMock()

        scheduler_instance.db.async_cleanup = mock_cleanup
        scheduler_instance.db.async_verify_audit_log_integrity = mock_verify_audit
        scheduler_instance.db.async_vacuum = mock_vacuum

        await scheduler_instance._data_cleanup_task()

        # Verify all database methods were called
        mock_cleanup.assert_awaited_once()
        mock_verify_audit.assert_awaited_once()
        mock_vacuum.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_data_method(self, scheduler_instance):
        """Test cleanup_old_data method."""
        # Mock the _data_cleanup_task method
        mock_cleanup_task = AsyncMock()
        scheduler_instance._data_cleanup_task = mock_cleanup_task

        await scheduler_instance.cleanup_old_data()

        # Verify the cleanup task was called
        mock_cleanup_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_method(self, scheduler_instance):
        """Test run_once method.

        F8-H-03: ta_scan and sentiment_scan are retired; run_once should log
        a warning and do nothing for them.
        """
        mock_market_status = AsyncMock()
        mock_data_cleanup = AsyncMock()

        scheduler_instance.check_market_status = mock_market_status
        scheduler_instance.run_data_cleanup = mock_data_cleanup

        # Test surviving jobs
        await scheduler_instance.run_once("market_status_check")
        mock_market_status.assert_awaited_once()

        await scheduler_instance.run_once("data_cleanup")
        mock_data_cleanup.assert_awaited_once()

        # Test retired signal-generation jobs
        with patch("loats.scheduler.logger") as mock_logger:
            await scheduler_instance.run_once("ta_scan")
            mock_logger.warning.assert_called_once_with(
                "Job '%s' is retired; signal production is handled by the orchestrator",
                "ta_scan",
            )

        with patch("loats.scheduler.logger") as mock_logger:
            await scheduler_instance.run_once("sentiment_scan")
            mock_logger.warning.assert_called_once_with(
                "Job '%s' is retired; signal production is handled by the orchestrator",
                "sentiment_scan",
            )

        # Test unknown job
        with patch("loats.scheduler.logger") as mock_logger:
            await scheduler_instance.run_once("unknown_job")
            mock_logger.warning.assert_called_once_with(
                "Unknown job ID: %s", "unknown_job"
            )

    @pytest.mark.asyncio
    async def test_get_jobs_method(self, scheduler_instance):
        """Test get_jobs method."""
        # Mock scheduler.get_jobs
        mock_job1 = MagicMock()
        mock_job1.id = "job1"
        mock_job1.name = "Test Job 1"
        mock_job1.trigger = "interval"
        mock_job1.next_run_time = datetime.now(UTC)

        mock_job2 = MagicMock()
        mock_job2.id = "job2"
        mock_job2.name = "Test Job 2"
        mock_job2.trigger = "cron"
        mock_job2.next_run_time = datetime.now(UTC)

        scheduler_instance.scheduler.get_jobs.return_value = [mock_job1, mock_job2]

        jobs = scheduler_instance.get_jobs()

        assert len(jobs) == 2
        assert jobs[0]["id"] == "job1"
        assert jobs[0]["name"] == "Test Job 1"
        assert jobs[1]["id"] == "job2"
        assert jobs[1]["name"] == "Test Job 2"

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self, scheduler_instance):
        """Test get_circuit_breaker_status method."""
        # Mock circuit breaker status
        mock_status = {"state": "CLOSED", "failure_count": 0}
        with patch("loats.scheduler.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = mock_status

            status = scheduler_instance.get_circuit_breaker_status()

            assert status == mock_status

    @pytest.mark.asyncio
    async def test_check_kill_switch_method(self, scheduler_instance):
        """Test _check_kill_switch method."""
        # Test with kill switch inactive
        with patch("loats.scheduler.alerts.is_kill_switch_active", return_value=False):
            scheduler_instance._check_kill_switch()  # Should not raise

        # Test with kill switch active
        with patch("loats.scheduler.alerts.is_kill_switch_active", return_value=True):
            with patch("loats.scheduler.logger") as mock_logger:
                with pytest.raises(Exception, match="Kill switch active"):
                    scheduler_instance._check_kill_switch()
                mock_logger.error.assert_called_once_with(
                    "Kill switch active trading operations blocked"
                )

    @pytest.mark.asyncio
    async def test_is_running_method(self, scheduler_instance):
        """Test is_running method."""
        # Test when not running
        scheduler_instance.running = False
        assert scheduler_instance.is_running() is False

        # Test when running
        scheduler_instance.running = True
        assert scheduler_instance.is_running() is True

    @pytest.mark.asyncio
    async def test_global_scheduler_instance(self):
        """Test global scheduler instance."""
        # Test that global instance is properly initialized
        assert isinstance(scheduler, TradingScheduler)

        # Test that it can be used for basic operations
        assert isinstance(scheduler.is_running(), bool)

        # Test that it has the expected methods
        assert hasattr(scheduler, "initialize")
        assert hasattr(scheduler, "start")
        assert hasattr(scheduler, "shutdown")
        assert hasattr(scheduler, "run_once")
        assert hasattr(scheduler, "get_jobs")
        assert hasattr(scheduler, "get_circuit_breaker_status")
        assert hasattr(scheduler, "is_running")

    @pytest.mark.asyncio
    async def test_safe_get_history_method(self, scheduler_instance):
        """Test _safe_get_history method with circuit breaker."""
        # Mock async_client.get_history
        with patch(
            "loats.scheduler.async_client.get_history", new_callable=AsyncMock
        ) as mock_get_history:
            mock_get_history.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_history("NIFTY", "15m")

            assert result == {"data": "test"}
            mock_get_history.assert_awaited_once_with(
                symbol="NIFTY", interval="15m", from_date=None, to_date=None
            )

    @pytest.mark.asyncio
    async def test_safe_get_quotes_method(self, scheduler_instance):
        """Test _safe_get_quotes method with circuit breaker."""
        # Mock async_client.get_quotes
        with patch(
            "loats.scheduler.async_client.get_quotes", new_callable=AsyncMock
        ) as mock_get_quotes:
            mock_get_quotes.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_quotes(["NIFTY"])

            assert result == {"data": "test"}
            mock_get_quotes.assert_awaited_once_with(["NIFTY"])

    @pytest.mark.asyncio
    async def test_safe_get_position_book_method(self, scheduler_instance):
        """Test _safe_get_position_book method with circuit breaker."""
        # Mock async_client.get_position_book
        with patch(
            "loats.scheduler.async_client.get_position_book", new_callable=AsyncMock
        ) as mock_get_position:
            mock_get_position.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_position_book()

            assert result == {"data": "test"}
            mock_get_position.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_safe_get_funds_method(self, scheduler_instance):
        """Test _safe_get_funds method with circuit breaker."""
        # Mock async_client.get_funds
        with patch(
            "loats.scheduler.async_client.get_funds", new_callable=AsyncMock
        ) as mock_get_funds:
            mock_get_funds.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_funds()

            assert result == {"data": "test"}
            mock_get_funds.assert_awaited_once()
