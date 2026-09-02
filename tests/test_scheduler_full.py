"""Tests for the F8-H-03 scheduler support jobs and job lifecycle."""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats import backtest_sanity as backtest_sanity_module
from loats.scheduler import TradingScheduler, is_market_open


@pytest.fixture
def scheduler():
    with patch("loats.scheduler.AsyncIOScheduler") as mock_aps:
        instance = TradingScheduler()
        instance.scheduler = mock_aps
        return instance


@pytest.mark.asyncio
async def test_add_jobs_registers_support_jobs(scheduler):
    """F8-H-03: only market-status, data-cleanup and backtest-sanity jobs are registered."""
    mock_add_job = MagicMock()
    scheduler.scheduler.add_job = mock_add_job
    await scheduler._add_jobs()
    ids = {call.kwargs["id"] for call in mock_add_job.call_args_list}
    assert ids == {
        "market_status_check",
        "data_cleanup",
        "backtest_sanity_check",
    }
    assert "ta_scan" not in ids
    assert "sentiment_scan" not in ids


@pytest.mark.asyncio
async def test_start_runs_initial_market_status(scheduler):
    """start() must kick off the initial market-status check and set running."""
    scheduler.check_market_status = AsyncMock()
    scheduler.scheduler.start = MagicMock()
    await scheduler.start()
    assert scheduler.running is True
    scheduler.scheduler.start.assert_called_once()
    scheduler.check_market_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_market_status_task_logs_market_closed(scheduler):
    """Market-closed path should log and return without spawning scans."""
    scheduler.is_market_open = MagicMock(return_value=False)
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler._market_status_check_task()
    mock_logger.debug.assert_called()


@pytest.mark.asyncio
async def test_check_market_status_task_logs_market_open(scheduler):
    """Market-open path should log market open."""
    scheduler.is_market_open = MagicMock(return_value=True)
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler._market_status_check_task()
    assert any(
        "Market open" in str(call.args[0]) for call in mock_logger.debug.call_args_list
    )


@pytest.mark.asyncio
async def test_check_market_status_catches_exception(scheduler):
    """Exception in market status check must be caught and logged."""
    scheduler.is_market_open = MagicMock(side_effect=Exception("market check boom"))
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.check_market_status()
    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_data_cleanup_task_invokes_db_cleanup(scheduler):
    """Data cleanup should call async_cleanup, audit integrity and vacuum."""
    db_instance = MagicMock()
    db_instance.async_cleanup = AsyncMock(return_value=True)
    db_instance.async_verify_audit_log_integrity = AsyncMock(return_value=True)
    db_instance.async_vacuum = AsyncMock(return_value=True)
    scheduler.db = db_instance
    await scheduler._data_cleanup_task()
    db_instance.async_cleanup.assert_awaited_once()
    db_instance.async_verify_audit_log_integrity.assert_awaited_once()
    db_instance.async_vacuum.assert_awaited_once()


@pytest.mark.asyncio
async def test_backtest_sanity_task_logs_when_gate_passes(scheduler):
    """Backtest sanity task should call the sanity module and log a pass."""
    db_instance = MagicMock()
    scheduler.db = db_instance

    fake_result = MagicMock()
    fake_result.symbol = "NIFTY"
    fake_result.total_windows = 10
    fake_result.windows_passed = 9
    fake_result.windows_failed = 1
    fake_result.pass_rate = 90.0
    fake_result.avg_pnl_per_window = 1.0

    with (
        patch.object(
            backtest_sanity_module,
            "run_backtest_sanity_check",
            new_callable=AsyncMock,
        ) as mock_run,
        patch.object(
            backtest_sanity_module, "backtest_sanity_pass_gate", return_value=True
        ),
        patch("loats.scheduler.logger") as mock_logger,
    ):
        mock_run.return_value = fake_result
        await scheduler._backtest_sanity_task(symbol="NIFTY")
    mock_run.assert_awaited_once()
    mock_logger.info.assert_called()


@pytest.mark.asyncio
async def test_backtest_sanity_task_sends_alert_when_gate_fails(scheduler):
    """Backtest sanity task should alert when pass rate is below the gate."""
    db_instance = MagicMock()
    scheduler.db = db_instance

    fake_result = MagicMock()
    fake_result.symbol = "NIFTY"
    fake_result.total_windows = 10
    fake_result.windows_passed = 5
    fake_result.windows_failed = 5
    fake_result.pass_rate = 50.0
    fake_result.avg_pnl_per_window = 1.0

    with (
        patch.object(
            backtest_sanity_module,
            "run_backtest_sanity_check",
            new_callable=AsyncMock,
        ) as mock_run,
        patch.object(
            backtest_sanity_module, "backtest_sanity_pass_gate", return_value=False
        ),
        patch(
            "loats.scheduler.alerts.send_alert", new_callable=AsyncMock
        ) as mock_alert,
        patch("loats.scheduler.logger") as mock_logger,
    ):
        mock_run.return_value = fake_result
        await scheduler._backtest_sanity_task(symbol="NIFTY")
    mock_run.assert_awaited_once()
    mock_alert.assert_awaited_once()
    mock_logger.info.assert_called()


def test_is_market_open_weekend():
    """Market should be closed on Saturday and Sunday."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    saturday = datetime.datetime(2026, 9, 12, 10, 0, 0, tzinfo=tz)
    sunday = datetime.datetime(2026, 9, 13, 10, 0, 0, tzinfo=tz)
    assert is_market_open(saturday) is False
    assert is_market_open(sunday) is False


def test_is_market_open_holiday():
    """Market should be closed on NSE holidays."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    republic_day = datetime.datetime(2026, 1, 26, 10, 0, 0, tzinfo=tz)
    assert is_market_open(republic_day) is False


def test_is_market_open_trading_hours():
    """Market should be open during trading hours on a weekday."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    tuesday = datetime.datetime(2026, 9, 15, 10, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is True


def test_is_market_open_before_hours():
    """Market should be closed before 9:15 IST."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    tuesday = datetime.datetime(2026, 9, 15, 9, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is False


def test_is_market_open_after_hours():
    """Market should be closed after 15:30 IST."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")
    tuesday = datetime.datetime(2026, 9, 15, 16, 0, 0, tzinfo=tz)
    assert is_market_open(tuesday) is False


def test_get_jobs_returns_list(scheduler):
    """get_jobs must return a list (empty when scheduler has no jobs)."""
    scheduler.scheduler.get_jobs.return_value = []
    assert scheduler.get_jobs() == []


@pytest.mark.asyncio
async def test_start_market_status_check_failure_caught(scheduler):
    """start() should catch and log initial market-status failure."""
    scheduler.scheduler.start = MagicMock()
    scheduler._start_market_status_check = AsyncMock(
        side_effect=Exception("market check boom")
    )
    with pytest.raises(Exception, match="market check boom"):
        await scheduler.start()


@pytest.mark.asyncio
async def test_check_market_status_task_catches_exception(scheduler):
    """_market_status_check_task logs exceptions."""
    scheduler.is_market_open = MagicMock(side_effect=Exception("boom"))
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler._market_status_check_task()
    mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_data_cleanup_task_logs_exception(scheduler):
    """_data_cleanup_task logs exception path and re-raises."""
    db_instance = MagicMock()
    db_instance.async_cleanup = AsyncMock(side_effect=Exception("cleanup boom"))
    scheduler.db = db_instance
    with patch("loats.scheduler.logger") as mock_logger:
        with pytest.raises(Exception, match="cleanup boom"):
            await scheduler._data_cleanup_task()
    mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_backtest_sanity_task_logs_exception(scheduler):
    """_backtest_sanity_task logs exception path."""
    with (
        patch.object(
            backtest_sanity_module,
            "run_backtest_sanity_check",
            new_callable=AsyncMock,
            side_effect=Exception("sanity boom"),
        ),
        patch("loats.scheduler.logger") as mock_logger,
    ):
        await scheduler._backtest_sanity_task(symbol="NIFTY")
    mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_run_data_cleanup_catches_cancel(scheduler):
    """run_data_cleanup catches CancelledError."""
    scheduler._data_cleanup_task = AsyncMock(side_effect=asyncio.CancelledError)
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.run_data_cleanup()
    args = mock_logger.info.call_args_list
    assert args
    assert "Data cleanup task cancelled" in args[-1][0][0]


@pytest.mark.asyncio
async def test_run_backtest_sanity_catches_cancel(scheduler):
    """run_backtest_sanity_check catches CancelledError."""
    scheduler._backtest_sanity_task = AsyncMock(side_effect=asyncio.CancelledError)
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.run_backtest_sanity_check()
    args = mock_logger.info.call_args_list
    assert args
    assert "Backtest sanity task cancelled" in args[-1][0][0]


@pytest.mark.asyncio
async def test_shutdown_closes_db_connection(scheduler):
    """shutdown closes async database connections."""
    db_instance = MagicMock()
    db_instance.async_close_all = AsyncMock(return_value=True)
    scheduler.db = db_instance
    scheduler.running = True
    scheduler.scheduler.shutdown = MagicMock()
    scheduler.scan_tasks = {}
    await scheduler.shutdown()
    db_instance.async_close_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_warns_on_close_error(scheduler):
    """shutdown logs warning when db close fails."""
    db_instance = MagicMock()
    db_instance.async_close_all = AsyncMock(side_effect=Exception("close boom"))
    scheduler.db = db_instance
    scheduler.running = True
    scheduler.scheduler.shutdown = MagicMock()
    scheduler.scan_tasks = {}
    with patch("loats.scheduler.logger") as mock_logger:
        await scheduler.shutdown()
    mock_logger.warning.assert_called()


def test_get_circuit_breaker_status(scheduler):
    """get_circuit_breaker_status returns status dict with circuit name."""
    status = scheduler.get_circuit_breaker_status()
    assert status is not None
    assert status.get("circuit_name") == "openalgo"


def test_check_kill_switch_raises(scheduler):
    """_check_kill_switch raises KillSwitchError when active."""
    from loats.openalgo import KillSwitchError

    with patch("loats.scheduler.alerts.is_kill_switch_active", return_value=True):
        with pytest.raises(KillSwitchError):
            scheduler._check_kill_switch()


def test_check_kill_switch_not_active(scheduler):
    """_check_kill_switch is a no-op when not active."""
    with patch("loats.scheduler.alerts.is_kill_switch_active", return_value=False):
        scheduler._check_kill_switch()  # should not raise
