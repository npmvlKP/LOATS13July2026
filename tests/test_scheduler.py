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


@pytest.mark.asyncio
async def test_ta_scan_task_tracks_metrics(scheduler):
    """TA scan task must record job execution metrics via track_job."""
    from src.loats.metrics import MetricsManager

    manager = MetricsManager()
    manager.reset_for_testing()

    with (
        patch.object(
            scheduler,
            "_safe_get_history",
            new_callable=AsyncMock,
            return_value={"data": []},
        ),
        patch.object(
            scheduler, "_safe_get_quotes", new_callable=AsyncMock, return_value=None
        ),
        patch("src.loats.scheduler.alerts.is_kill_switch_active", return_value=False),
        patch(
            "src.loats.scheduler.technical_analysis.calculate_indicators",
            return_value=[],
        ),
        patch(
            "src.loats.scheduler.technical_analysis.generate_signal",
            return_value=None,
        ),
        patch.object(
            scheduler.db, "async_store_historical_data", new_callable=AsyncMock
        ),
    ):
        await scheduler._ta_scan_task()

    assert manager.job_execution_stats["total"] == 1
    assert manager.job_execution_stats["success"] == 1
    assert manager.job_latency_stats["count"] == 1
