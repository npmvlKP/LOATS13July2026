"""
Sentiment analysis module LOATS13July2026.
Implements RSS news sentiment analysis using Vader Sentiment.
"""

import asyncio
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlparse

import feedparser
from newspaper import Article
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .config import settings
from .logging import get_logger
from .models import NewsItem, SentimentAnalysisResult

logger = get_logger(__name__)


class SentimentAnalyzer:
    """Sentiment analysis engine news social media."""

    def __init__(self) -> None:
        """Initialize SentimentAnalyzer."""
        self.analyzer = SentimentIntensityAnalyzer()
        self.threshold = settings.sentiment_threshold

    def set_threshold(self, threshold: float) -> None:
        """Set sentiment threshold filtering."""
        self.threshold = threshold

    def analyze_text(self, text: str) -> tuple[float, str]:
        """Analyze sentiment text string."""
        scores = self.analyzer.polarity_scores(text)
        compound_score = scores["compound"]
        if compound_score >= self.threshold:
            label = "positive"
        elif compound_score <= -self.threshold:
            label = "negative"
        else:
            label = "neutral"
        return compound_score, label

    async def parse_rss_feed(self, url: str, max_items: int = 20) -> list[NewsItem]:
        """Parse RSS feed extract news items asynchronously."""
        try:
            feed = await asyncio.to_thread(feedparser.parse, url)
            news_items: list[NewsItem] = []
            for entry in feed.entries[:max_items]:
                try:
                    content = await asyncio.to_thread(
                        self._extract_article_content, entry.link
                    )
                    sentiment_score, sentiment_label = self.analyze_text(
                        f"{entry.title}. {content}"
                    )
                    published_date = datetime.now(UTC)
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pp = entry.published_parsed
                        published_date = datetime(
                            pp[0], pp[1], pp[2], pp[3], pp[4], pp[5], tzinfo=UTC
                        )

                    news_item = NewsItem(
                        title=entry.title,
                        content=content,
                        source=urlparse(url).netloc,
                        url=entry.link,
                        published_date=published_date,
                        sentiment_score=sentiment_score,
                        sentiment_label=sentiment_label,
                    )
                    news_items.append(news_item)
                except Exception:
                    logger.warning("Failed process RSS item %s", entry.link)
                    continue
            return news_items
        except Exception:
            logger.exception("Failed parse RSS feed %s", url)
            return []

    def _extract_article_content(self, url: str) -> str:
        """Extract article content URL using newspaper4k."""
        try:
            article = Article(url)
            article.download()
            article.parse()
            return self.preprocess_text(article.text)
        except Exception:
            logger.warning("Failed extract article content %s", url)
            return ""

    async def analyze_symbol_sentiment(
        self,
        symbol: str,
        rss_urls: list[str],
        max_items: int = 20,
    ) -> SentimentAnalysisResult:
        """Analyze sentiment specific symbol across multiple RSS feeds asynchronously."""
        all_news: list[NewsItem] = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        tasks = [self.parse_rss_feed(url, max_items) for url in rss_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.exception("Failed process RSS feed: %s", result)
                continue

            news_items = cast(list[NewsItem], result)
            all_news.extend(news_items)
            for item in news_items:
                if item.sentiment_label == "positive":
                    positive_count += 1
                elif item.sentiment_label == "negative":
                    negative_count += 1
                else:
                    neutral_count += 1

        avg_score = 0.0
        if all_news:
            avg_score = sum(item.sentiment_score for item in all_news) / len(all_news)

        if avg_score >= self.threshold:
            label = "positive"
        elif avg_score <= -self.threshold:
            label = "negative"
        else:
            label = "neutral"

        sorted_news = sorted(
            all_news, key=lambda x: abs(x.sentiment_score), reverse=True
        )
        return SentimentAnalysisResult(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            sentiment_score=avg_score,
            sentiment_label=label,
            news_count=len(all_news),
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            top_news=sorted_news[:5],
        )

    def filter_significant_news(self, news_items: list[NewsItem]) -> list[NewsItem]:
        """Filter news items significant sentiment."""
        return [
            item for item in news_items if abs(item.sentiment_score) >= self.threshold
        ]

    def preprocess_text(self, text: str) -> str:
        """Preprocess text sentiment analysis."""
        return " ".join(text.split())


sentiment = SentimentAnalyzer()
