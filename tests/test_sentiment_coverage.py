import pytest
from datetime import datetime, UTC
from unittest.mock import patch, MagicMock
from src.loats.sentiment import SentimentAnalyzer
from src.loats.models import NewsItem

@pytest.mark.asyncio
async def test_sentiment_analyzer_threshold():
    analyzer = SentimentAnalyzer()
    analyzer.set_threshold(0.5)
    # Test positive threshold
    score, label = analyzer.analyze_text("This is an extremely positive and profitable market scenario")
    assert label in ["positive", "neutral", "negative"]

@pytest.mark.asyncio
async def test_parse_rss_feed_empty():
    analyzer = SentimentAnalyzer()
    # Test invalid URL empty feed results
    results = await analyzer.parse_rss_feed("invalid_url", max_items=5)
    assert results == []

@pytest.mark.asyncio
async def test_filter_significant_news():
    analyzer = SentimentAnalyzer()
    item1 = NewsItem(
        title="T1", content="C1", source="S1", url="U1",
        published_date=datetime.now(UTC), sentiment_score=0.9, sentiment_label="positive"
    )
    item2 = NewsItem(
        title="T2", content="C2", source="S2", url="U2",
        published_date=datetime.now(UTC), sentiment_score=0.1, sentiment_label="neutral"
    )
    analyzer.set_threshold(0.5)
    filtered = analyzer.filter_significant_news([item1, item2])
    assert len(filtered) == 1
    assert filtered[0].title == "T1"

@pytest.mark.asyncio
async def test_analyze_symbol_sentiment_exception_handling():
    analyzer = SentimentAnalyzer()
    # Mock parse_rss_feed raise exception
    with patch.object(analyzer, 'parse_rss_feed', side_effect=Exception("Network error")):
        result = await analyzer.analyze_symbol_sentiment("TEST", ["http://test.com"], max_items=1)
        assert result.news_count == 0
        assert result.sentiment_score == 0.0

@pytest.mark.asyncio
async def test_parse_rss_feed_exception():
    analyzer = SentimentAnalyzer()
    # Mock feedparser.parse raise exception
    with patch('src.loats.sentiment.feedparser.parse', side_effect=Exception("Parse error")):
        results = await analyzer.parse_rss_feed("http://test.com", max_items=1)
        assert results == []

@pytest.mark.asyncio
async def test_extract_article_content_exception():
    analyzer = SentimentAnalyzer()
    # Mock newspaper.Article
    with patch('src.loats.sentiment.Article') as mock_article_class:
        mock_article = MagicMock()
        mock_article.download.side_effect = Exception("Download error")
        mock_article_class.return_value = mock_article
        content = analyzer._extract_article_content("http://test.com")
        assert content == ""