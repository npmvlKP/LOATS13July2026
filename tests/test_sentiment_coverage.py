"""Tests for sentiment coverage."""

import unittest.mock
from datetime import UTC, datetime

import pytest

from loats.models import NewsItem
from loats.sentiment import SentimentAnalyzer


@pytest.mark.asyncio
async def test_sentiment_analyzer_threshold():
    """Test sentiment threshold."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.5)
    score, label = analyzer.analyze_text(
        "This extremely positive profitable market scenario"
    )
    assert label in ["positive", "neutral", "negative"]


@pytest.mark.asyncio
async def test_parse_rss_feed_empty():
    """Test invalid URL empty feed results."""
    analyzer = SentimentAnalyzer()
    results = await analyzer.parse_rss_feed("invalid_url", max_items=5)
    assert results == []


@pytest.mark.asyncio
async def test_filter_significant_news():
    """Test filtering news by sentiment threshold."""
    analyzer = SentimentAnalyzer()
    item1 = NewsItem(
        title="T1",
        content="C1",
        source="S1",
        url="U1",
        published_date=datetime.now(UTC),
        sentiment_score=0.9,
        sentiment_label="positive",
    )
    item2 = NewsItem(
        title="T2",
        content="C2",
        source="S2",
        url="U2",
        published_date=datetime.now(UTC),
        sentiment_score=0.1,
        sentiment_label="neutral",
    )
    analyzer.set_threshold(0.5)
    filtered = analyzer.filter_significant_news([item1, item2])
    assert len(filtered) == 1
    assert filtered[0].title == "T1"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_exception_handling():
    """Test exception handling in analyze_symbol_sentiment."""
    analyzer = SentimentAnalyzer()
    with unittest.mock.patch.object(
        analyzer, "parse_rss_feed", side_effect=Exception("Network error")
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=1
        )
        assert result.news_count == 0
        assert result.sentiment_score == 0.0


@pytest.mark.asyncio
async def test_parse_rss_feed_exception():
    """Test exception handling in parse_rss_feed."""
    analyzer = SentimentAnalyzer()
    with unittest.mock.patch(
        "src.loats.sentiment.feedparser.parse", side_effect=Exception("Parse error")
    ):
        results = await analyzer.parse_rss_feed("http://test.com", max_items=1)
        assert results == []


@pytest.mark.asyncio
async def test_extract_article_content_exception():
    """Test exception handling in _extract_article_content."""
    analyzer = SentimentAnalyzer()
    with unittest.mock.patch("loats.sentiment.Article") as mock_article_class:
        mock_article = unittest.mock.MagicMock()
        mock_article.download.side_effect = Exception("Download error")
        mock_article_class.return_value = mock_article
        content = analyzer._extract_article_content("http://test.com")
        assert content == ""


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_cache_hit():
    """Test cache hit in analyze_symbol_sentiment (lines 114-121)."""
    analyzer = SentimentAnalyzer()
    with unittest.mock.patch(
        "loats.sentiment.cache_manager.get",
        return_value='{"symbol": "TEST", "sentiment_score": 0.5, "sentiment_label": "positive", "news_count": 10, "positive_count": 6, "negative_count": 2, "neutral_count": 2, "top_news": [], "timestamp": "2023-01-01T00:00:00Z"}',
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=5
        )
        assert result.symbol == "TEST"
        assert result.sentiment_score == 0.5
        assert result.sentiment_label == "positive"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_cache_miss():
    """Test cache miss in analyze_symbol_sentiment (lines 122-181)."""
    analyzer = SentimentAnalyzer()
    with (
        unittest.mock.patch("loats.sentiment.cache_manager.get", return_value=None),
        unittest.mock.patch.object(
            analyzer, "parse_rss_feed", return_value=[]
        ) as mock_parse,
        unittest.mock.patch("loats.sentiment.cache_manager.set") as mock_cache_set,
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=5
        )
        assert result.symbol == "TEST"
        assert result.sentiment_score == 0.0
        assert result.sentiment_label == "neutral"
        mock_parse.assert_called_once()
        mock_cache_set.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_with_news_items():
    """Test analyze_symbol_sentiment with actual news items (lines 138-155)."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.1)

    # Create mock news items
    news_items = [
        NewsItem(
            title="Positive News",
            content="Great earnings report",
            source="test.com",
            url="http://test.com/1",
            published_date=datetime.now(UTC),
            sentiment_score=0.8,
            sentiment_label="positive",
        ),
        NewsItem(
            title="Negative News",
            content="Poor performance",
            source="test.com",
            url="http://test.com/2",
            published_date=datetime.now(UTC),
            sentiment_score=-0.6,
            sentiment_label="negative",
        ),
        NewsItem(
            title="Neutral News",
            content="Regular update",
            source="test.com",
            url="http://test.com/3",
            published_date=datetime.now(UTC),
            sentiment_score=0.05,
            sentiment_label="neutral",
        ),
    ]

    with (
        unittest.mock.patch("loats.sentiment.cache_manager.get", return_value=None),
        unittest.mock.patch.object(analyzer, "parse_rss_feed", return_value=news_items),
        unittest.mock.patch("loats.sentiment.cache_manager.set"),
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=5
        )
        assert result.symbol == "TEST"
        assert result.news_count == 3
        assert result.positive_count == 1
        assert result.negative_count == 1
        assert result.neutral_count == 1
        # Average score: (0.8 - 0.6 + 0.05) / 3 = 0.25 / 3 ≈ 0.083
        assert abs(result.sentiment_score - 0.083) < 0.01
        assert result.sentiment_label == "neutral"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_positive_overall():
    """Test analyze_symbol_sentiment with positive overall sentiment (lines 150-155)."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.1)

    news_items = [
        NewsItem(
            title="Great News",
            content="Excellent results",
            source="test.com",
            url="http://test.com/1",
            published_date=datetime.now(UTC),
            sentiment_score=0.9,
            sentiment_label="positive",
        )
    ]

    with (
        unittest.mock.patch("loats.sentiment.cache_manager.get", return_value=None),
        unittest.mock.patch.object(analyzer, "parse_rss_feed", return_value=news_items),
        unittest.mock.patch("loats.sentiment.cache_manager.set"),
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=5
        )
        assert result.sentiment_score == 0.9
        assert result.sentiment_label == "positive"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_negative_overall():
    """Test analyze_symbol_sentiment with negative overall sentiment (lines 152-155)."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.1)

    news_items = [
        NewsItem(
            title="Bad News",
            content="Poor performance",
            source="test.com",
            url="http://test.com/1",
            published_date=datetime.now(UTC),
            sentiment_score=-0.8,
            sentiment_label="negative",
        )
    ]

    with (
        unittest.mock.patch("loats.sentiment.cache_manager.get", return_value=None),
        unittest.mock.patch.object(analyzer, "parse_rss_feed", return_value=news_items),
        unittest.mock.patch("loats.sentiment.cache_manager.set"),
    ):
        result = await analyzer.analyze_symbol_sentiment(
            "TEST", ["http://test.com"], max_items=5
        )
        assert result.sentiment_score == -0.8
        assert result.sentiment_label == "negative"


@pytest.mark.asyncio
async def test_parse_rss_feed_with_valid_entries():
    """Test parse_rss_feed with valid RSS entries (lines 51-87)."""
    analyzer = SentimentAnalyzer()

    # Mock feedparser response
    mock_feed = unittest.mock.MagicMock()
    mock_feed.entries = [
        unittest.mock.MagicMock(
            title="Test News",
            link="http://test.com/news1",
            published_parsed=(2023, 1, 1, 12, 0, 0, 0, 0, 0),
        )
    ]

    with (
        unittest.mock.patch(
            "src.loats.sentiment.feedparser.parse", return_value=mock_feed
        ),
        unittest.mock.patch.object(
            analyzer, "_extract_article_content", return_value="Test content"
        ),
        unittest.mock.patch.object(
            analyzer, "analyze_text", return_value=(0.5, "positive")
        ),
    ):
        results = await analyzer.parse_rss_feed("http://test.com/rss", max_items=5)
        assert len(results) == 1
        assert results[0].title == "Test News"
        assert results[0].sentiment_label == "positive"


def test_preprocess_text():
    """Test preprocess_text method (lines 189-191)."""
    analyzer = SentimentAnalyzer()
    # Test with extra whitespace
    result = analyzer.preprocess_text("  Hello    world  ")
    assert result == "Hello world"
    # Test with newlines and tabs
    result = analyzer.preprocess_text("Hello\nworld\twith\nextra\tspaces")
    assert result == "Hello world with extra spaces"


def test_filter_significant_news_empty():
    """Test filter_significant_news with empty list."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.5)
    result = analyzer.filter_significant_news([])
    assert result == []


def test_filter_significant_news_all_significant():
    """Test filter_significant_news where all items are significant."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.1)

    news_items = [
        NewsItem(
            title="T1",
            content="C1",
            source="S1",
            url="U1",
            published_date=datetime.now(UTC),
            sentiment_score=0.9,
            sentiment_label="positive",
        ),
        NewsItem(
            title="T2",
            content="C2",
            source="S2",
            url="U2",
            published_date=datetime.now(UTC),
            sentiment_score=-0.8,
            sentiment_label="negative",
        ),
    ]

    result = analyzer.filter_significant_news(news_items)
    assert len(result) == 2


def test_filter_significant_news_none_significant():
    """Test filter_significant_news where no items are significant."""
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.5)

    news_items = [
        NewsItem(
            title="T1",
            content="C1",
            source="S1",
            url="U1",
            published_date=datetime.now(UTC),
            sentiment_score=0.1,
            sentiment_label="neutral",
        ),
        NewsItem(
            title="T2",
            content="C2",
            source="S2",
            url="U2",
            published_date=datetime.now(UTC),
            sentiment_score=-0.2,
            sentiment_label="neutral",
        ),
    ]

    result = analyzer.filter_significant_news(news_items)
    assert len(result) == 0
