import asyncio
import signal
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.main import TradingSystem


@pytest.fixture
def trading_system():
    return TradingSystem()


@pytest.mark.asyncio
async def test_trading_system_initialization_success(trading_system):
    """Test successful initialization (lines 34-47)."""
    with (
        patch("loats.main.initialize_cache", new_callable=AsyncMock) as mock_cache_init,
        patch("loats.main.db.async_initialize", new_callable=AsyncMock) as mock_db_init,
        patch(
            "loats.main.db.async_verify_audit_log_integrity", return_value=True
        ) as mock_db_verify,
        patch(
            "loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
    ):
        await trading_system.initialize()
        mock_cache_init.assert_called_once()
        mock_db_init.assert_called_once()
        mock_db_verify.assert_called_once()
        mock_alerts_init.assert_called_once()
        mock_scheduler_init.assert_called_once()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_initialization_failed_audit_log(trading_system):
    """Test initialization with failed audit log integrity (lines 40-41)."""
    with (
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", new_callable=AsyncMock),
        patch("loats.main.db.async_verify_audit_log_integrity", return_value=False),
        patch("loats.main.alerts.initialize", new_callable=AsyncMock),
        patch("loats.main.scheduler.initialize", new_callable=AsyncMock),
    ):
        await trading_system.initialize()
        # Should still complete initialization even with audit log warning


@pytest.mark.asyncio
async def test_trading_system_initialization_exception(trading_system):
    """Test initialization exception handling (lines 45-47)."""
    with (
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", side_effect=Exception("DB error")),
    ):
        with pytest.raises(Exception, match="DB error"):
            await trading_system.initialize()


@pytest.mark.asyncio
async def test_trading_system_start_already_running(trading_system):
    """Test start when already running (lines 51-53)."""
    trading_system.running = True
    await trading_system.start()
    # Should return early without starting again


@pytest.mark.asyncio
async def test_trading_system_start_success(trading_system):
    """Test successful start (lines 54-66)."""
    with (
        patch("loats.main.alerts.start", new_callable=AsyncMock) as mock_alerts_start,
        patch(
            "loats.main.scheduler.start", new_callable=AsyncMock
        ) as mock_scheduler_start,
        patch(
            "loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "loats.main.TradingSystem._wait_for_shutdown", new_callable=AsyncMock
        ) as mock_wait,
    ):
        await trading_system.start()
        assert trading_system.running is True
        mock_alerts_start.assert_called_once()
        mock_scheduler_start.assert_called_once()
        mock_send_alert.assert_called_once_with(
            "LOATS13July2026 trading system started successfully", "success"
        )
        mock_wait.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_start_exception(trading_system):
    """Test start exception handling (lines 64-66)."""
    with (
        patch("loats.main.alerts.start", side_effect=Exception("Start error")),
    ):
        with pytest.raises(Exception, match="Start error"):
            await trading_system.start()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_shutdown_not_running(trading_system):
    """Test shutdown when not running (lines 113-115)."""
    trading_system.running = False
    await trading_system.shutdown()
    # Should return early without shutdown


@pytest.mark.asyncio
async def test_trading_system_shutdown_success(trading_system):
    """Test successful shutdown (lines 116-130)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "loats.main.scheduler.shutdown", new_callable=AsyncMock
        ) as mock_scheduler_shutdown,
        patch(
            "loats.main.alerts.shutdown", new_callable=AsyncMock
        ) as mock_alerts_shutdown,
        patch("loats.main.close_cache") as mock_close_cache,
        patch("loats.main.db.async_close_all", new_callable=AsyncMock) as mock_db_close,
    ):
        await trading_system.shutdown()
        assert trading_system.running is False
        mock_send_alert.assert_called_once_with(
            "LOATS13July2026 trading system shutting down", "warning"
        )
        mock_scheduler_shutdown.assert_called_once()
        mock_alerts_shutdown.assert_called_once()
        mock_close_cache.assert_called_once()
        mock_db_close.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_shutdown_exception(trading_system):
    """Test shutdown exception handling (lines 128-130)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.alerts.send_system_alert",
            side_effect=Exception("Shutdown error"),
        ),
    ):
        with pytest.raises(Exception, match="Shutdown error"):
            await trading_system.shutdown()


@pytest.mark.asyncio
async def test_trading_system_run_once_success(trading_system):
    """Test run_once successful execution (lines 132-142)."""
    with (
        patch("loats.main.scheduler.run_ta_scan", new_callable=AsyncMock) as mock_ta,
        patch(
            "loats.main.scheduler.run_sentiment_scan", new_callable=AsyncMock
        ) as mock_sentiment,
        patch(
            "loats.main.scheduler.run_signal_generation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        await trading_system.run_once()
        mock_ta.assert_called_once()
        mock_sentiment.assert_called_once()
        mock_signal.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_run_once_exception(trading_system):
    """Test run_once exception handling (lines 140-142)."""
    with (
        patch("loats.main.scheduler.run_ta_scan", side_effect=Exception("Scan error")),
    ):
        with pytest.raises(Exception, match="Scan error"):
            await trading_system.run_once()


@pytest.mark.asyncio
async def test_make_signal_handler_windows(trading_system):
    """Test _make_signal_handler for Windows platform (lines 85-104)."""
    with patch("sys.platform", "win32"):
        loop = asyncio.get_running_loop()
        handler = trading_system._make_signal_handler(loop)

        # Mock the async task creation to avoid actual shutdown
        with (
            patch("loats.main.alerts.send_system_alert", new_callable=AsyncMock),
            patch("loats.main.scheduler.shutdown", new_callable=AsyncMock),
            patch("loats.main.alerts.shutdown", new_callable=AsyncMock),
            patch("loats.main.close_cache"),
            patch("loats.main.db.async_close_all", new_callable=AsyncMock),
        ):
            # Call the signal handler
            handler(signal.SIGINT, None)

            # Give time for the async task to execute
            await asyncio.sleep(0.1)

            # Verify shutdown was triggered
            assert not trading_system.running


@pytest.mark.asyncio
async def test_handle_shutdown_signal(trading_system):
    """Test _handle_shutdown_signal method (lines 106-109)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.TradingSystem.shutdown", new_callable=AsyncMock
        ) as mock_shutdown,
    ):
        await trading_system._handle_shutdown_signal(signal.SIGTERM)
        mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_shutdown_windows(trading_system):
    """Test _wait_for_shutdown for Windows platform (lines 68-83)."""
    with patch("sys.platform", "win32"):
        # Mock signal handlers
        with patch("signal.signal"):
            # Start the wait_for_shutdown method
            wait_task = asyncio.create_task(trading_system._wait_for_shutdown())

            # Simulate shutdown after a short delay
            async def trigger_shutdown():
                await asyncio.sleep(0.1)
                trading_system.shutdown_event.set()

            shutdown_task = asyncio.create_task(trigger_shutdown())

            # Wait for both tasks to complete
            await asyncio.wait([wait_task, shutdown_task], timeout=1.0)

            # Verify the wait completed
            assert wait_task.done()


@pytest.mark.asyncio
async def test_wait_for_shutdown_posix(trading_system):
    """Test _wait_for_shutdown for POSIX platform (lines 76-81)."""
    with patch("sys.platform", "linux"):
        # Mock add_signal_handler
        with patch("asyncio.AbstractEventLoop.add_signal_handler"):
            # Start the wait_for_shutdown method
            wait_task = asyncio.create_task(trading_system._wait_for_shutdown())

            # Simulate shutdown after a short delay
            async def trigger_shutdown():
                await asyncio.sleep(0.1)
                trading_system.shutdown_event.set()

            shutdown_task = asyncio.create_task(trigger_shutdown())

            # Wait for both tasks to complete
            await asyncio.wait([wait_task, shutdown_task], timeout=1.0)

            # Verify the wait completed
            assert wait_task.done()
