"""
Comprehensive test suite for scheduler module coverage improvement.
This test suite targets specific lines that are missing coverage in scheduler.py.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, UTC

from src.loats.scheduler import TradingScheduler, scheduler
from src.loats.models import Signal, SignalType


class TestSchedulerCoverage:
    """Comprehensive test suite for scheduler module coverage."""

    @pytest.fixture
    def scheduler_instance(self):
        """Create a TradingScheduler instance with mocked dependencies."""
        with patch("src.loats.scheduler.AsyncIOScheduler") as mock_aps:
            instance = TradingScheduler()
            instance.scheduler = mock_aps
            return instance

    @pytest.mark.asyncio
    async def test_is_market_open_weekday_during_hours(self, scheduler_instance):
        """Test is_market_open during market hours (lines 146-148)."""
        # Mock datetime to be during market hours on a weekday
        with patch("src.loats.scheduler.datetime") as mock_datetime:
            # Set up mock for weekday during market hours
            mock_now = datetime(2023, 1, 16, 10, 0, 0)  # Monday 10 AM
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            # Mock timezone
            with patch("src.loats.scheduler.ZoneInfo") as mock_zone:
                mock_tz = MagicMock()
                mock_zone.return_value = mock_tz

                result = scheduler_instance.is_market_open()
                assert result is True

    @pytest.mark.asyncio
    async def test_is_market_open_weekend(self, scheduler_instance):
        """Test is_market_open on weekend (lines 146-148)."""
        # Mock datetime to be on a weekend
        with patch("src.loats.scheduler.datetime") as mock_datetime:
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
        with patch("src.loats.scheduler.datetime") as mock_datetime:
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
        with patch("src.loats.scheduler.datetime") as mock_datetime:
            # Set up mock for before market hours
            mock_now = datetime(2023, 1, 16, 8, 0, 0)  # Monday 8 AM
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date

            # Mock timezone
            with patch("src.loats.scheduler.ZoneInfo") as mock_zone:
                mock_tz = MagicMock()
                mock_zone.return_value = mock_tz

                result = scheduler_instance.is_market_open()
                assert result is False

    @pytest.mark.asyncio
    async def test_add_jobs_method(self, scheduler_instance):
        """Test _add_jobs method (lines 204-206, 215-216, 219, 225-227)."""
        # Mock the add_job method
        mock_add_job = MagicMock()
        scheduler_instance.scheduler.add_job = mock_add_job

        await scheduler_instance._add_jobs()

        # Verify that add_job was called for all expected jobs
        assert mock_add_job.call_count == 5

        # Check that each job was added with correct parameters
        calls = mock_add_job.call_args_list
        for call in calls:
            args, kwargs = call
            assert "id" in kwargs
            assert "name" in kwargs
            assert "replace_existing" in kwargs

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
    async def test_run_ta_scan_task(self, scheduler_instance):
        """Test run_ta_scan method (lines 253-254, 265-266)."""

        # Mock the _ta_scan_task method
        async def mock_scan_coro():
            return None

        mock_scan_task = AsyncMock(side_effect=mock_scan_coro)
        scheduler_instance._ta_scan_task = mock_scan_task

        # Mock asyncio.create_task to return a proper awaitable task
        with patch("asyncio.create_task") as mock_create_task:
            # Create a proper async task that can be awaited
            async def mock_task_coro():
                return None

            mock_task = asyncio.ensure_future(mock_task_coro())
            mock_create_task.return_value = mock_task

            # Mock the task to be stored in scan_tasks
            with patch.object(scheduler_instance, "scan_tasks", {}):
                await scheduler_instance.run_ta_scan()

                # Verify task was created and stored - check that it was called with a coroutine
                assert mock_create_task.called
                # The task should have been stored and then removed (due to try/finally)
                # So we just verify the create_task was called

    @pytest.mark.asyncio
    async def test_ta_scan_task_with_kill_switch(self, scheduler_instance):
        """Test _ta_scan_task with kill switch active (lines 282-283)."""
        # Mock kill switch to be active
        with patch(
            "src.loats.scheduler.alerts.is_kill_switch_active", return_value=True
        ):
            with pytest.raises(Exception):  # KillSwitchError
                await scheduler_instance._ta_scan_task()

    @pytest.mark.asyncio
    async def test_ta_scan_task_with_no_history_data(self, scheduler_instance):
        """Test _ta_scan_task with no history data (lines 293-307)."""
        # Mock dependencies
        with (
            patch.object(
                scheduler_instance,
                "_safe_get_history",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                scheduler_instance, "_safe_get_quotes", new_callable=AsyncMock
            ),
            patch(
                "src.loats.scheduler.alerts.is_kill_switch_active", return_value=False
            ),
        ):
            await scheduler_instance._ta_scan_task()

            # Should complete without error and log warning

    @pytest.mark.asyncio
    async def test_run_sentiment_scan_task(self, scheduler_instance):
        """Test run_sentiment_scan method (lines 346, 348-349)."""

        # Mock the _sentiment_scan_task method
        async def mock_scan_coro():
            return None

        mock_scan_task = AsyncMock(side_effect=mock_scan_coro)
        scheduler_instance._sentiment_scan_task = mock_scan_task

        # Mock asyncio.create_task to return a proper awaitable task
        with patch("asyncio.create_task") as mock_create_task:
            # Create a proper async task that can be awaited
            async def mock_task_coro():
                return None

            mock_task = asyncio.ensure_future(mock_task_coro())
            mock_create_task.return_value = mock_task

            # Mock the task to be stored in scan_tasks
            with patch.object(scheduler_instance, "scan_tasks", {}):
                await scheduler_instance.run_sentiment_scan()

                # Verify task was created and stored - check that it was called with a coroutine
                assert mock_create_task.called
                # The task should have been stored and then removed (due to try/finally)
                # So we just verify the create_task was called

    @pytest.mark.asyncio
    async def test_sentiment_scan_task_with_kill_switch(self, scheduler_instance):
        """Test _sentiment_scan_task with kill switch active (lines 365-368)."""
        # Mock kill switch to be active
        with patch(
            "src.loats.scheduler.alerts.is_kill_switch_active", return_value=True
        ):
            with pytest.raises(Exception):  # KillSwitchError
                await scheduler_instance._sentiment_scan_task()

    @pytest.mark.asyncio
    async def test_run_signal_generation_task(self, scheduler_instance):
        """Test run_signal_generation method (lines 396-399)."""

        # Mock the _signal_generation_task method
        async def mock_scan_coro():
            return None

        mock_scan_task = AsyncMock(side_effect=mock_scan_coro)
        scheduler_instance._signal_generation_task = mock_scan_task

        # Mock asyncio.create_task to return a proper awaitable task
        with patch("asyncio.create_task") as mock_create_task:
            # Create a proper async task that can be awaited
            async def mock_task_coro():
                return None

            mock_task = asyncio.ensure_future(mock_task_coro())
            mock_create_task.return_value = mock_task

            # Mock the task to be stored in scan_tasks
            with patch.object(scheduler_instance, "scan_tasks", {}):
                await scheduler_instance.run_signal_generation()

                # Verify task was created and stored - check that it was called with a coroutine
                assert mock_create_task.called
                # The task should have been stored and then removed (due to try/finally)
                # So we just verify the create_task was called

    @pytest.mark.asyncio
    async def test_signal_generation_task_with_kill_switch(self, scheduler_instance):
        """Test _signal_generation_task with kill switch active (lines 420-424)."""
        # Mock kill switch to be active
        with patch(
            "src.loats.scheduler.alerts.is_kill_switch_active", return_value=True
        ):
            with pytest.raises(Exception):  # KillSwitchError
                await scheduler_instance._signal_generation_task()

    @pytest.mark.asyncio
    async def test_check_market_status_task(self, scheduler_instance):
        """Test check_market_status method (lines 438-441)."""

        # Mock the _market_status_check_task method
        async def mock_scan_coro():
            return None

        mock_scan_task = AsyncMock(side_effect=mock_scan_coro)
        scheduler_instance._market_status_check_task = mock_scan_task

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
        """Test _market_status_check_task when market is closed (lines 450-455)."""
        # Mock is_market_open to return False
        scheduler_instance.is_market_open = MagicMock(return_value=False)

        # Mock scheduler.get_job and remove_job
        mock_get_job = MagicMock()
        mock_remove_job = MagicMock()
        scheduler_instance.scheduler.get_job = mock_get_job
        scheduler_instance.scheduler.remove_job = mock_remove_job

        # Mock jobs to exist
        mock_get_job.side_effect = lambda job_id: (
            MagicMock()
            if job_id in ["ta_scan", "sentiment_scan", "signal_generation"]
            else None
        )

        await scheduler_instance._market_status_check_task()

        # Verify jobs were removed
        assert mock_remove_job.call_count == 3

    @pytest.mark.asyncio
    async def test_market_status_check_task_market_open(self, scheduler_instance):
        """Test _market_status_check_task when market is open (lines 462-467)."""
        # Mock is_market_open to return True
        scheduler_instance.is_market_open = MagicMock(return_value=True)

        # Mock scheduler.get_job to return None (jobs don't exist)
        scheduler_instance.scheduler.get_job = MagicMock(return_value=None)

        # Mock add_job
        mock_add_job = MagicMock()
        scheduler_instance.scheduler.add_job = mock_add_job

        await scheduler_instance._market_status_check_task()

        # Verify jobs were added
        assert mock_add_job.call_count == 3

    @pytest.mark.asyncio
    async def test_run_data_cleanup_task(self, scheduler_instance):
        """Test run_data_cleanup method (lines 486-487)."""

        # Mock the _data_cleanup_task method
        async def mock_scan_coro():
            return None

        mock_scan_task = AsyncMock(side_effect=mock_scan_coro)
        scheduler_instance._data_cleanup_task = mock_scan_task

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
        """Test _data_cleanup_task method (lines 496-507)."""
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
        """Test cleanup_old_data method (lines 529-532)."""
        # Mock the _data_cleanup_task method
        mock_cleanup_task = AsyncMock()
        scheduler_instance._data_cleanup_task = mock_cleanup_task

        await scheduler_instance.cleanup_old_data()

        # Verify the cleanup task was called
        mock_cleanup_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_method(self, scheduler_instance):
        """Test run_once method (lines 591, 593-594)."""
        # Mock the various run methods
        mock_ta_scan = AsyncMock()
        mock_sentiment_scan = AsyncMock()
        mock_signal_generation = AsyncMock()
        mock_market_status = AsyncMock()
        mock_data_cleanup = AsyncMock()

        scheduler_instance.run_ta_scan = mock_ta_scan
        scheduler_instance.run_sentiment_scan = mock_sentiment_scan
        scheduler_instance.run_signal_generation = mock_signal_generation
        scheduler_instance.check_market_status = mock_market_status
        scheduler_instance.run_data_cleanup = mock_data_cleanup

        # Test each job type
        await scheduler_instance.run_once("ta_scan")
        mock_ta_scan.assert_awaited_once()

        await scheduler_instance.run_once("sentiment_scan")
        mock_sentiment_scan.assert_awaited_once()

        await scheduler_instance.run_once("signal_generation")
        mock_signal_generation.assert_awaited_once()

        await scheduler_instance.run_once("market_status_check")
        mock_market_status.assert_awaited_once()

        await scheduler_instance.run_once("data_cleanup")
        mock_data_cleanup.assert_awaited_once()

        # Test unknown job
        with patch("src.loats.scheduler.logger") as mock_logger:
            await scheduler_instance.run_once("unknown_job")
            mock_logger.warning.assert_called_once_with(
                "Unknown job ID: %s", "unknown_job"
            )

    @pytest.mark.asyncio
    async def test_get_jobs_method(self, scheduler_instance):
        """Test get_jobs method (lines 612-615)."""
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
        """Test get_circuit_breaker_status method (lines 629-630)."""
        # Mock circuit breaker status
        mock_status = {"state": "CLOSED", "failure_count": 0}
        with patch("src.loats.scheduler.OPENALGO_CIRCUIT_BREAKER") as mock_cb:
            mock_cb.get_status.return_value = mock_status

            status = scheduler_instance.get_circuit_breaker_status()

            assert status == mock_status

    @pytest.mark.asyncio
    async def test_check_kill_switch_method(self, scheduler_instance):
        """Test _check_kill_switch method (lines 655-656)."""
        # Test with kill switch inactive
        with patch(
            "src.loats.scheduler.alerts.is_kill_switch_active", return_value=False
        ):
            scheduler_instance._check_kill_switch()  # Should not raise

        # Test with kill switch active
        with patch(
            "src.loats.scheduler.alerts.is_kill_switch_active", return_value=True
        ):
            with patch("src.loats.scheduler.logger") as mock_logger:
                with pytest.raises(Exception):  # KillSwitchError
                    scheduler_instance._check_kill_switch()
                mock_logger.error.assert_called_once_with(
                    "Kill switch active trading operations blocked"
                )

    @pytest.mark.asyncio
    async def test_is_running_method(self, scheduler_instance):
        """Test is_running method (lines 665-668)."""
        # Test when not running
        scheduler_instance.running = False
        assert scheduler_instance.is_running() is False

        # Test when running
        scheduler_instance.running = True
        assert scheduler_instance.is_running() is True

    @pytest.mark.asyncio
    async def test_global_scheduler_instance(self):
        """Test global scheduler instance (lines 681-682, 691, 707-709, 730-731)."""
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
        """Test _safe_get_history method with circuit breaker (lines 236-239)."""
        # Mock async_client.get_history
        with patch(
            "src.loats.scheduler.async_client.get_history", new_callable=AsyncMock
        ) as mock_get_history:
            mock_get_history.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_history("NIFTY", "15m")

            assert result == {"data": "test"}
            mock_get_history.assert_awaited_once_with(
                symbol="NIFTY", interval="15m", from_date=None, to_date=None
            )

    @pytest.mark.asyncio
    async def test_safe_get_quotes_method(self, scheduler_instance):
        """Test _safe_get_quotes method with circuit breaker (lines 253-254, 265-266)."""
        # Mock async_client.get_quotes
        with patch(
            "src.loats.scheduler.async_client.get_quotes", new_callable=AsyncMock
        ) as mock_get_quotes:
            mock_get_quotes.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_quotes(["NIFTY"])

            assert result == {"data": "test"}
            mock_get_quotes.assert_awaited_once_with(["NIFTY"])

    @pytest.mark.asyncio
    async def test_safe_get_position_book_method(self, scheduler_instance):
        """Test _safe_get_position_book method with circuit breaker (lines 438-441)."""
        # Mock async_client.get_position_book
        with patch(
            "src.loats.scheduler.async_client.get_position_book", new_callable=AsyncMock
        ) as mock_get_position:
            mock_get_position.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_position_book()

            assert result == {"data": "test"}
            mock_get_position.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_safe_get_funds_method(self, scheduler_instance):
        """Test _safe_get_funds method with circuit breaker (lines 450-455)."""
        # Mock async_client.get_funds
        with patch(
            "src.loats.scheduler.async_client.get_funds", new_callable=AsyncMock
        ) as mock_get_funds:
            mock_get_funds.return_value = {"data": "test"}

            result = await scheduler_instance._safe_get_funds()

            assert result == {"data": "test"}
            mock_get_funds.assert_awaited_once()
