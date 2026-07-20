from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.loats.models import NewsItem
from src.loats.sentiment import SentimentAnalyzer


@pytest.fixture
def analyzer():
    return SentimentAnalyzer()


@pytest.mark.asyncio
async def test_analyze_text(analyzer):
    score, label = analyzer.analyze_text("good profit")
    assert score > 0
    assert label == "positive"
    score, label = analyzer.analyze_text("bad loss")
    assert score < 0
    assert label == "negative"
    score, label = analyzer.analyze_text("market open")
    assert label == "neutral"


def test_preprocess_text(analyzer):
    text = "Multiple   spaces\nnew lines "
    assert analyzer.preprocess_text(text) == "Multiple spaces new lines"


@pytest.mark.asyncio
async def test_analyze_symbol_sentiment(analyzer):
    with patch(
        "src.loats.sentiment.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
    ) as mock_parse:
        mock_parse.return_value = [
            NewsItem(
                title="Good",
                content="Profit",
                source="test",
                url="url",
                published_date=datetime.now(),
                sentiment_score=0.8,
                sentiment_label="positive",
            )
        ]
        result = await analyzer.analyze_symbol_sentiment("TEST", ["http://test.com"])
        assert result.symbol == "TEST"
        assert result.news_count == 1
        assert result.positive_count == 1
