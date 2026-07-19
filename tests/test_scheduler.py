from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.scheduler import TradingScheduler


@pytest.fixture
def scheduler():
    with patch("src.loats.scheduler.AsyncIOScheduler") as mock_aps:
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
    # Mock scan methods to avoid real async calls during start
    scheduler.run_ta_scan = AsyncMock()
    scheduler.run_sentiment_scan = AsyncMock()
    scheduler.run_signal_generation = AsyncMock()

    # Mock scheduler methods
    scheduler.scheduler.start = MagicMock()
    scheduler.scheduler.shutdown = MagicMock()

    await scheduler.start()
    assert scheduler.running is True

    await scheduler.shutdown()
    assert scheduler.running is False
    scheduler.scheduler.shutdown.assert_called_once()
