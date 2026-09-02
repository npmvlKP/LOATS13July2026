import asyncio
import signal
from unittest.mock import AsyncMock, patch

import pytest

from loats.main import TradingSystem


@pytest.fixture
def trading_system():
    return TradingSystem()


@pytest.mark.asyncio
async def test_trading_system_initialization(trading_system):
    # patch function, not frozen instance method
    with (
        patch("loats.main.db.async_initialize", new_callable=AsyncMock) as mock_db_init,
        patch(
            "loats.main.db.async_verify_audit_log_integrity",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_db_verify,
        patch(
            "loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
        patch("loats.main.metrics.start_server") as mock_metrics_start,
    ):
        await trading_system.initialize()
        mock_db_init.assert_called_once()
        mock_db_verify.assert_called_once()
        mock_alerts_init.assert_called_once()
        mock_scheduler_init.assert_called_once()
        mock_metrics_start.assert_called_once()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_start_shutdown(trading_system):
    with (
        patch("loats.main.alerts.start", new_callable=AsyncMock) as mock_alerts_start,
        patch(
            "loats.main.scheduler.start", new_callable=AsyncMock
        ) as mock_scheduler_start,
        patch(
            "loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch("loats.main.TradingSystem._wait_for_shutdown", new_callable=AsyncMock),
    ):
        await trading_system.start()
        assert trading_system.running is True
        mock_alerts_start.assert_called_once()
        mock_scheduler_start.assert_called_once()
        mock_send_alert.assert_called_once()

        with (
            patch(
                "loats.main.scheduler.shutdown", new_callable=AsyncMock
            ) as mock_scheduler_shutdown,
            patch(
                "loats.main.alerts.shutdown", new_callable=AsyncMock
            ) as mock_alerts_shutdown,
            patch(
                "loats.main.db.async_close_all", new_callable=AsyncMock
            ) as mock_db_close_all,
        ):
            await trading_system.shutdown()
            assert trading_system.running is False
            mock_scheduler_shutdown.assert_called_once()
            mock_alerts_shutdown.assert_called_once()
            mock_db_close_all.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_run_once(trading_system):
    """Test run_once executes scheduler support jobs.

    F8-H-03: TA and sentiment signal scans have been retired from the
    scheduler; the orchestrator is the sole signal engine. run_once now only
    exercises support jobs (market status, data cleanup, backtest sanity check).
    """
    with patch.object(
        trading_system, "_run_scheduler_support_jobs", new_callable=AsyncMock
    ) as mock_support:
        await trading_system.run_once()
        mock_support.assert_called_once()


@pytest.mark.asyncio
async def test_run_once_exception(trading_system):
    """Test run_once exception handling when a support job fails."""
    with patch.object(
        trading_system,
        "_run_scheduler_support_jobs",
        side_effect=Exception("Support job error"),
    ):
        with pytest.raises(Exception, match="Support job error"):
            await trading_system.run_once()


@pytest.mark.asyncio
async def test_signal_handler_triggers_graceful_shutdown(trading_system):
    """Signal handler must trigger full graceful shutdown (Windows path)."""
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
        patch(
            "loats.main.db.async_close_all", new_callable=AsyncMock
        ) as mock_db_close_all,
    ):
        trading_system.running = True
        loop = asyncio.get_running_loop()
        handler = trading_system._make_signal_handler(loop)

        handler(signal.SIGINT, None)

        async def wait_shutdown():
            for _ in range(100):
                if not trading_system.running:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("graceful shutdown was not triggered")

        await wait_shutdown()

        assert not trading_system.running
        mock_send_alert.assert_called_once()
        mock_scheduler_shutdown.assert_called_once()
        mock_alerts_shutdown.assert_called_once()
        mock_close_cache.assert_called_once()
        mock_db_close_all.assert_called_once()
