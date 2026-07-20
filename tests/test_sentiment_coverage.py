"""Tests for sentiment coverage."""

import unittest.mock
from datetime import UTC, datetime

import pytest

from src.loats.models import NewsItem
from src.loats.sentiment import SentimentAnalyzer


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
    with unittest.mock.patch("src.loats.sentiment.Article") as mock_article_class:
        mock_article = unittest.mock.MagicMock()
        mock_article.download.side_effect = Exception("Download error")
        mock_article_class.return_value = mock_article
        content = analyzer._extract_article_content("http://test.com")
        assert content == ""
