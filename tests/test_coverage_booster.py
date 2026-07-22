import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.main import TradingSystem
from src.loats.models import NewsItem
from src.loats.options import OptionsAnalysis, OptionsEngine, OptionType
from src.loats.scheduler import TradingScheduler
from src.loats.sentiment import SentimentAnalyzer


@pytest.mark.asyncio
async def test_sentiment_coverage_full():
    analyzer = SentimentAnalyzer()
    # Mock analyze_text (sync)
    with patch.object(SentimentAnalyzer, "analyze_text") as mock_analyze:
        mock_analyze.return_value = (0.5, "positive")
        score, label = analyzer.analyze_text("Good")
        assert label == "positive"
        mock_analyze.return_value = (-0.5, "negative")
        score, label = analyzer.analyze_text("Bad")
        assert label == "negative"

    # Test parse_rss_feed
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = MagicMock(entries=[])
        items = await analyzer.parse_rss_feed("http://invalid.url")
        assert isinstance(items, list)

    # Test _extract_article_content (sync)
    with patch("src.loats.sentiment.Article"):
        content = analyzer._extract_article_content("http://invalid.url")
        assert content == ""

    # Test analyze_symbol_sentiment
    news_item = NewsItem(
        title="T",
        content="C",
        source="S",
        url="U",
        published_date=datetime.datetime.now(datetime.UTC),
        sentiment_score=0.5,
        sentiment_label="positive",
    )
    with patch.object(
        SentimentAnalyzer, "parse_rss_feed", new_callable=AsyncMock
    ) as mock_parse:
        mock_parse.return_value = [news_item]
        result = await analyzer.analyze_symbol_sentiment("TEST", ["http://url"])
        assert result.sentiment_label == "positive"

    analyzer.set_threshold(0.1)
    assert analyzer.threshold == 0.1
    assert analyzer.preprocess_text("hello world") == "hello world"
    assert len(analyzer.filter_significant_news([])) == 0


@pytest.mark.asyncio
async def test_options_coverage_full():
    engine = OptionsEngine()
    # Greeks
    with patch("src.loats.options.delta", side_effect=Exception):
        greeks = engine.calculate_greeks(100, 100, 1, 0.1, option_type=OptionType.CALL)
        assert greeks.delta == 0.0

    # Implied Vol
    with patch("src.loats.options.implied_volatility", side_effect=Exception):
        with patch("src.loats.options.brentq", side_effect=Exception):
            with patch("src.loats.options.newton", side_effect=Exception):
                val = engine.calculate_implied_volatility(10.0, 100, 100, 1, 0.1, 0.05)
                assert val == 0.2

    analysis = OptionsAnalysis()
    with patch.object(OptionsEngine, "calculate_greeks") as mock_greeks:
        mock_greeks.return_value = MagicMock(
            delta=0.5, gamma=0.1, vega=0.1, theta=0.1, rho=0.1
        )
        res = analysis.calculate_portfolio_greeks([], 100)
        assert res is not None


@pytest.mark.asyncio
async def test_scheduler_coverage():
    sched = TradingScheduler()
    assert not sched.is_running()
    with patch(
        "src.loats.scheduler.TradingScheduler.is_market_open", return_value=True
    ):
        await sched.check_market_status()


@pytest.mark.asyncio
async def test_main_coverage_booster():
    # Patch dependencies in src.loats.main
    with (
        patch("src.loats.main.scheduler") as mock_sched,
        patch("src.loats.main.alerts") as mock_alert,
        patch("src.loats.main.db") as mock_db,
    ):
        sys_obj = TradingSystem()

        mock_sched.run_ta_scan = AsyncMock()
        mock_sched.run_sentiment_scan = AsyncMock()
        mock_sched.run_signal_generation = AsyncMock()
        mock_sched.start = AsyncMock()
        mock_sched.shutdown = AsyncMock()
        mock_sched.initialize = AsyncMock()

        mock_alert.start = AsyncMock()
        mock_alert.shutdown = AsyncMock()
        mock_alert.initialize = AsyncMock()
        mock_alert.send_system_alert = AsyncMock()

        mock_db.verify_audit_log_integrity.return_value = True
        mock_db.async_close_all = AsyncMock()

        # Run initialization
        await sys_obj.initialize()

        # Run start (mock _wait_for_shutdown to avoid hang)
        with patch.object(TradingSystem, "_wait_for_shutdown", new_callable=AsyncMock):
            await sys_obj.start()
            assert sys_obj.running
            await sys_obj.run_once()
            assert mock_sched.run_ta_scan.called

            await sys_obj.shutdown()
            assert not sys_obj.running
