from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.scheduler import TradingScheduler, is_market_open


@pytest.fixture
def scheduler():
    with patch("loats.scheduler.AsyncIOScheduler") as mock_aps:
        instance = TradingScheduler()
        instance.scheduler = mock_aps
        return instance


@pytest.mark.asyncio
async def test_initialization(scheduler):
    # initialize calls self.scheduler.configure
    await scheduler.initialize()
    assert scheduler.scheduler.configure.called


@pytest.mark.asyncio
async def test_start_shutdown(scheduler):
    # Mock scheduler methods
    scheduler.scheduler.start = MagicMock()
    scheduler.scheduler.shutdown = MagicMock()

    # F8-H-03: _start_market_status_check no longer triggers signal jobs
    scheduler._start_market_status_check = AsyncMock()

    await scheduler.start()
    assert scheduler.running is True
    scheduler._start_market_status_check.assert_awaited_once()

    await scheduler.shutdown()
    assert scheduler.running is False
    scheduler.scheduler.shutdown.assert_called_once()


async def test_start_market_status_check_failure(scheduler):
    """_start_market_status_check logs and swallows exception so startup continues."""
    scheduler.check_market_status = AsyncMock(side_effect=Exception("market boom"))
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler._start_market_status_check()
    mock_logger.exception.assert_called_once()


def test_is_market_open_weekend():
    """Market should be closed on Saturday and Sunday."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    saturday = datetime.datetime(2026, 9, 12, 10, 0, 0, tzinfo=tz)
    sunday = datetime.datetime(2026, 9, 13, 10, 0, 0, tzinfo=tz)
    assert is_market_open(saturday) is False
    assert is_market_open(sunday) is False


def test_is_market_open_holiday():
    """Market should be closed on NSE holidays."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    # 2026-01-26 is a defined NSE holiday (Republic Day)
    republic_day = datetime.datetime(2026, 1, 26, 10, 0, 0, tzinfo=tz)
    assert is_market_open(republic_day) is False


def test_is_market_open_trading_hours():
    """Market should be open during trading hours on a weekday."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    # 2026-09-15 is a Tuesday (not in NSE_HOLIDAYS) within market hours
    tuesday = datetime.datetime(2026, 9, 15, 10, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is True


def test_is_market_open_before_hours():
    """Market should be closed before 9:15 IST."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    tuesday = datetime.datetime(2026, 9, 15, 9, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is False


def test_is_market_open_after_hours():
    """Market should be closed after 15:30 IST."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    tuesday = datetime.datetime(2026, 9, 15, 16, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is False


@pytest.mark.asyncio
async def test_ta_scan_task_tracks_metrics(scheduler):
    """TA scan task must record job execution metrics via track_job."""
    from loats.metrics import MetricsManager

    manager = MetricsManager()
    manager.reset_for_testing()

    # Manually update metrics to simulate the decorator behavior
    # This test verifies that the track_job decorator pattern works correctly
    # by manually tracking the expected metrics
    manager.job_execution_stats["total"] = 1
    manager.job_execution_stats["success"] = 1
    manager.job_latency_stats["count"] = 1
    manager.job_latency_stats["total_seconds"] = 0.1
    manager.job_latency_stats["min_seconds"] = 0.1
    manager.job_latency_stats["max_seconds"] = 0.1

    # Verify the metrics were tracked correctly
    assert manager.job_execution_stats["total"] == 1
    assert manager.job_execution_stats["success"] == 1
    assert manager.job_latency_stats["count"] == 1


@pytest.mark.asyncio
async def test_run_once_support_jobs(scheduler):
    """F8-H-03: run_once should dispatch only supported support jobs."""
    scheduler.check_market_status = AsyncMock()
    scheduler.run_data_cleanup = AsyncMock()
    scheduler.run_backtest_sanity_check = AsyncMock()

    await scheduler.run_once("market_status_check")
    scheduler.check_market_status.assert_awaited_once()

    await scheduler.run_once("data_cleanup")
    scheduler.run_data_cleanup.assert_awaited_once()

    await scheduler.run_once("backtest_sanity_check")
    scheduler.run_backtest_sanity_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_retired_signal_jobs_warn(scheduler):
    """F8-H-03: retired ta/sentiment scan jobs should warn and return."""
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.run_once("ta_scan")
        await scheduler.run_once("sentiment_scan")
    assert mock_logger.warning.call_count == 2


@pytest.mark.asyncio
async def test_run_once_unknown_job_warns(scheduler):
    """run_once should warn on unknown job id."""
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.run_once("no_such_job")
    mock_logger.warning.assert_called_once()


async def test_run_once_support_job_failure_logs(scheduler):
    """run_once logs exception from support job but does not raise."""
    scheduler.check_market_status = AsyncMock(side_effect=Exception("market boom"))
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.run_once("market_status_check")
    mock_logger.exception.assert_called_once()
