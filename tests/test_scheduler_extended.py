import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.loats.scheduler import TradingScheduler


@pytest.fixture
def scheduler():
    return TradingScheduler()


@pytest.mark.asyncio
async def test_is_market_open_logic(scheduler):
    # Test Saturday (Should be closed)
    saturday = datetime.datetime(2026, 7, 18, 10, 0)
    with patch("src.loats.scheduler.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = saturday
        assert scheduler.is_market_open() is False

    # Test Sunday (Should be closed)
    sunday = datetime.datetime(2026, 7, 19, 10, 0)
    with patch("src.loats.scheduler.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = sunday
        assert scheduler.is_market_open() is False


@pytest.mark.asyncio
async def test_run_once_all_jobs(scheduler):
    scheduler.run_ta_scan = AsyncMock()
    scheduler.run_sentiment_scan = AsyncMock()
    scheduler.run_signal_generation = AsyncMock()
    scheduler.check_market_status = AsyncMock()
    scheduler.run_data_cleanup = AsyncMock()

    await scheduler.run_once("ta_scan")
    scheduler.run_ta_scan.assert_awaited_once()

    await scheduler.run_once("sentiment_scan")
    scheduler.run_sentiment_scan.assert_awaited_once()

    await scheduler.run_once("signal_generation")
    scheduler.run_signal_generation.assert_awaited_once()

    await scheduler.run_once("market_status_check")
    scheduler.check_market_status.assert_awaited_once()

    await scheduler.run_once("data_cleanup")
    scheduler.run_data_cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_jobs_empty(scheduler):
    assert isinstance(scheduler.get_jobs(), list)


@pytest.mark.asyncio
async def test_is_running(scheduler):
    assert scheduler.is_running() is False
    scheduler.running = True
    assert scheduler.is_running() is True
