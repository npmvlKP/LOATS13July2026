from unittest.mock import AsyncMock, patch

import pytest

from src.loats.main import TradingSystem


@pytest.fixture
def trading_system():
    return TradingSystem()


@pytest.mark.asyncio
async def test_trading_system_initialization(trading_system):
    # patch function, not frozen instance method
    with (
        patch("src.loats.main.db._initialize_database") as mock_db_init,
        patch(
            "src.loats.main.db.verify_audit_log_integrity", return_value=True
        ) as mock_db_verify,
        patch(
            "src.loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "src.loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
    ):
        await trading_system.initialize()
        mock_db_init.assert_called_once()
        mock_db_verify.assert_called_once()
        mock_alerts_init.assert_called_once()
        mock_scheduler_init.assert_called_once()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_start_shutdown(trading_system):
    with (
        patch(
            "src.loats.main.alerts.start", new_callable=AsyncMock
        ) as mock_alerts_start,
        patch(
            "src.loats.main.scheduler.start", new_callable=AsyncMock
        ) as mock_scheduler_start,
        patch(
            "src.loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "src.loats.main.TradingSystem._wait_for_shutdown", new_callable=AsyncMock
        ),
    ):
        await trading_system.start()
        assert trading_system.running is True
        mock_alerts_start.assert_called_once()
        mock_scheduler_start.assert_called_once()
        mock_send_alert.assert_called_once()

        with (
            patch(
                "src.loats.main.scheduler.shutdown", new_callable=AsyncMock
            ) as mock_scheduler_shutdown,
            patch(
                "src.loats.main.alerts.shutdown", new_callable=AsyncMock
            ) as mock_alerts_shutdown,
            patch(
                "src.loats.main.db.async_close_all", new_callable=AsyncMock
            ) as mock_db_close_all,
        ):
            await trading_system.shutdown()
            assert trading_system.running is False
            mock_scheduler_shutdown.assert_called_once()
            mock_alerts_shutdown.assert_called_once()
            mock_db_close_all.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_run_once(trading_system):
    with (
        patch(
            "src.loats.main.scheduler.run_ta_scan", new_callable=AsyncMock
        ) as mock_ta,
        patch(
            "src.loats.main.scheduler.run_sentiment_scan", new_callable=AsyncMock
        ) as mock_sentiment,
        patch(
            "src.loats.main.scheduler.run_signal_generation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        await trading_system.run_once()
        mock_ta.assert_called_once()
        mock_sentiment.assert_called_once()
        mock_signal.assert_called_once()
