import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.models import SentimentAnalysisResult
from src.loats.scheduler import TradingScheduler


@pytest.fixture
def scheduler():
    with patch("src.loats.scheduler.AsyncIOScheduler"):
        mock_aps = MagicMock()
        instance = TradingScheduler()
        instance.scheduler = mock_aps
        return instance


@pytest.mark.asyncio
async def test_run_ta_scan_success(scheduler):
    with (
        patch(
            "src.loats.scheduler.openalgo_client", new_callable=AsyncMock
        ) as mock_client,
        patch("src.loats.scheduler.db") as mock_db,
        patch("src.loats.scheduler.technical_analysis") as mock_ta,
    ):

        mock_client.get_history.return_value = {
            "data": [
                {
                    "timestamp": "2026-07-19T10:00:00",
                    "open": 100,
                    "high": 110,
                    "low": 90,
                    "close": 105,
                    "volume": 1000,
                }
            ]
        }
        mock_client.get_quotes.return_value = {
            "data": {
                "NSE:NIFTY50": {
                    "last_price": 105,
                    "open": 100,
                    "high": 110,
                    "low": 90,
                    "close": 105,
                    "volume": 1000,
                }
            }
        }
        mock_ta.calculate_indicators.return_value = {}
        mock_ta.generate_signal.return_value = ("BUY", 0.8)

        # Mock async methods
        mock_db.async_store_historical_data = AsyncMock(return_value=True)
        mock_db.async_create_signal = AsyncMock(return_value=True)
        mock_db.async_store_quote = AsyncMock(return_value=True)

        await scheduler.run_ta_scan()

        assert mock_db.async_create_signal.called
        assert mock_db.async_store_historical_data.called


@pytest.mark.asyncio
async def test_run_sentiment_scan_success(scheduler):
    with (
        patch(
            "src.loats.scheduler.sentiment", new_callable=AsyncMock
        ) as mock_sentiment,
        patch("src.loats.scheduler.db") as mock_db,
    ):

        mock_result = SentimentAnalysisResult(
            symbol="NSE:NIFTY50",
            timestamp=datetime.datetime.now(datetime.UTC),
            sentiment_score=0.5,
            sentiment_label="POSITIVE",
            news_count=10,
            positive_count=7,
            negative_count=2,
            neutral_count=1,
            top_news=[],
        )
        mock_sentiment.analyze_symbol_sentiment.return_value = mock_result

        # Mock async methods
        mock_db.async_create_signal = AsyncMock(return_value=True)

        await scheduler.run_sentiment_scan()
        assert mock_db.async_create_signal.called


@pytest.mark.asyncio
async def test_run_signal_generation_success(scheduler):
    with (
        patch(
            "src.loats.scheduler.openalgo_client", new_callable=AsyncMock
        ) as mock_client,
        patch("src.loats.scheduler.db") as mock_db,
    ):

        # Mock async methods
        mock_db.async_get_latest_signals = AsyncMock(
            return_value=[MagicMock(strength=0.8, indicators={})]
        )
        mock_db.async_store_position = AsyncMock(return_value=True)
        mock_db.async_store_funds = AsyncMock(return_value=True)
        mock_db.async_create_signal = AsyncMock(return_value=True)
        mock_db.async_store_quote = AsyncMock(return_value=True)

        mock_client.get_quotes.return_value = {
            "data": {"NSE:NIFTY50": {"last_price": 105}}
        }
        mock_client.get_position_book.return_value = {"data": []}
        mock_client.get_funds.return_value = {
            "data": {
                "available_cash": 100000,
                "utilized_margin": 0,
                "available_margin": 100000,
                "total_equity": 100000,
            }
        }

        await scheduler.run_signal_generation()
        assert mock_db.async_create_signal.called


@pytest.mark.asyncio
async def test_check_market_status_open(scheduler):
    scheduler.is_market_open = MagicMock(return_value=True)
    scheduler.scheduler.get_job.return_value = None

    await scheduler.check_market_status()
    assert scheduler.scheduler.add_job.call_count >= 1


@pytest.mark.asyncio
async def test_check_market_status_closed(scheduler):
    scheduler.is_market_open = MagicMock(return_value=False)
    scheduler.scheduler.get_job.return_value = MagicMock()

    await scheduler.check_market_status()
    assert scheduler.scheduler.remove_job.called


@pytest.mark.asyncio
async def test_run_data_cleanup_success(scheduler):
    with patch("src.loats.scheduler.db") as mock_db:
        # Mock async methods
        mock_db.async_cleanup = AsyncMock(return_value=True)
        mock_db.async_verify_audit_log_integrity = AsyncMock(return_value=True)
        mock_db.async_vacuum = AsyncMock(return_value=True)

        await scheduler.run_data_cleanup()
        assert mock_db.async_cleanup.called
        assert mock_db.async_verify_audit_log_integrity.called
        assert mock_db.async_vacuum.called
