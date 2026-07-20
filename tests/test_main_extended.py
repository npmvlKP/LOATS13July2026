import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.main import TradingSystem, main


@pytest.fixture
def trading_system():
    return TradingSystem()


@pytest.mark.asyncio
async def test_trading_system_initialization_failure(trading_system):
    mock_settings = MagicMock()
    mock_settings.initialize.side_effect = Exception("Init error")
    with patch("src.loats.main.settings", mock_settings):
        with pytest.raises(Exception, match="Init error"):
            await trading_system.initialize()


@pytest.mark.asyncio
async def test_trading_system_start_failure(trading_system):
    with patch("src.loats.main.alerts.start", side_effect=Exception("Start error")):
        with pytest.raises(Exception, match="Start error"):
            await trading_system.start()


@pytest.mark.asyncio
async def test_trading_system_shutdown_not_running(trading_system):
    trading_system.running = False
    await trading_system.shutdown()
    assert not trading_system.running


@pytest.mark.asyncio
async def test_trading_system_run_once_failure(trading_system):
    with patch(
        "src.loats.main.scheduler.run_ta_scan", side_effect=Exception("Scan error")
    ):
        with pytest.raises(Exception, match="Scan error"):
            await trading_system.run_once()


@pytest.mark.asyncio
async def test_handle_shutdown_signal(trading_system):
    with patch.object(
        trading_system, "shutdown", new_callable=AsyncMock
    ) as mock_shutdown:
        await trading_system._handle_shutdown_signal(signal.SIGINT)
        mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_main_function_success():
    with (
        patch(
            "src.loats.main.TradingSystem.initialize", new_callable=AsyncMock
        ) as mock_init,
        patch(
            "src.loats.main.TradingSystem.start", new_callable=AsyncMock
        ) as mock_start,
    ):
        await main()
        mock_init.assert_called_once()
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_main_function_failure():
    with (
        patch(
            "src.loats.main.TradingSystem.initialize",
            side_effect=Exception("Main error"),
        ),
        patch(
            "src.loats.main.TradingSystem.shutdown", new_callable=AsyncMock
        ) as mock_shutdown,
        patch("sys.exit") as mock_exit,
    ):
        await main()
        mock_shutdown.assert_called_once()
        mock_exit.assert_called_with(1)


@pytest.mark.asyncio
async def test_start_already_running(trading_system):
    trading_system.running = True
    with patch(
        "src.loats.main.alerts.start", new_callable=AsyncMock
    ) as mock_alerts_start:
        await trading_system.start()
        mock_alerts_start.assert_not_called()
