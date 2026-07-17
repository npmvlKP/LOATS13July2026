"""
Sentiment analysis module for LOATS13July2026.
Implements RSS news sentiment analysis using Vader Sentiment.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
from newspaper import Article
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .config import settings
from .logging import get_logger
from .models import NewsItem, SentimentAnalysisResult

logger = get_logger(__name__)


class SentimentAnalyzer:
    """Sentiment analysis engine for news and social media."""

    def __init__(self) -> None:
        """Initialize SentimentAnalyzer."""
        self.analyzer = SentimentIntensityAnalyzer()
        self.threshold = settings.sentiment_threshold

    def set_threshold(self, threshold: float) -> None:
        """
        Set sentiment threshold for filtering.

        Args:
            threshold: Sentiment threshold (absolute value)
        """
        self.threshold = threshold

    def analyze_text(self, text: str) -> tuple[float, str]:
        """
        Analyze sentiment of a text string.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (sentiment_score, sentiment_label)
        """
        scores = self.analyzer.polarity_scores(text)

        # Calculate compound score
        compound_score = scores["compound"]

        # Determine sentiment label
        if compound_score >= self.threshold:
            label = "positive"
        elif compound_score <= -self.threshold:
            label = "negative"
        else:
            label = "neutral"

        return compound_score, label

    def parse_rss_feed(self, url: str, max_items: int = 20) -> list[NewsItem]:
        """
        Parse RSS feed and extract news items.

        Args:
            url: RSS feed URL
            max_items: Maximum number of items to process

        Returns:
            List of NewsItem objects
        """
        try:
            feed = feedparser.parse(url)
            news_items = []

            for entry in feed.entries[:max_items]:
                try:
                    # Extract content using newspaper4k if available
                    content = self._extract_article_content(entry.link)

                    # Analyze sentiment
                    sentiment_score, sentiment_label = self.analyze_text(
                        f"{entry.title}. {content}",
                    )

                    # Parse published date safely
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pp = entry.published_parsed
                        published_date = datetime(
                            pp[0],
                            pp[1],
                            pp[2],
                            pp[3],
                            pp[4],
                            pp[5],
                            tzinfo=timezone.utc,
                        )
                    else:
                        published_date = datetime.now(timezone.utc)

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

                except Exception as e:
                    logger.warning("Failed to process RSS item %s: %s", entry.link, e)
                    continue

            return news_items

        except Exception:
            logger.exception("Failed to parse RSS feed %s", url)
            return []

    def _extract_article_content(self, url: str) -> str:
        """
        Extract article content from URL using newspaper4k.

        Args:
            url: Article URL

        Returns:
            Extracted article content
        """
        try:
            article = Article(url)
            article.download()
            article.parse()
            text = article.text
            return self.preprocess_text(text)
        except Exception as e:
            logger.warning("Failed to extract article content from %s: %s", url, e)
            return ""

    def analyze_symbol_sentiment(
        self,
        symbol: str,
        rss_urls: list[str],
        max_items: int = 20,
    ) -> SentimentAnalysisResult:
        """
        Analyze sentiment for a specific symbol across multiple RSS feeds.

        Args:
            symbol: Symbol to analyze sentiment for
            rss_urls: List of RSS feed URLs
            max_items: Maximum number of items to process per feed

        Returns:
            SentimentAnalysisResult object
        """
        all_news = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        for url in rss_urls:
            try:
                news_items = self.parse_rss_feed(url, max_items)
                all_news.extend(news_items)

                # Count sentiment categories
                for item in news_items:
                    if item.sentiment_label == "positive":
                        positive_count += 1
                    elif item.sentiment_label == "negative":
                        negative_count += 1
                    else:
                        neutral_count += 1

            except Exception:
                logger.exception("Failed to process RSS feed %s", url)
                continue

        # Calculate overall sentiment score
        if all_news:
            avg_score = sum(item.sentiment_score for item in all_news) / len(all_news)
        else:
            avg_score = 0.0

        # Determine overall sentiment label
        if avg_score >= self.threshold:
            label = "positive"
        elif avg_score <= -self.threshold:
            label = "negative"
        else:
            label = "neutral"

        # Sort news by absolute sentiment score (most extreme first)
        sorted_news = sorted(
            all_news,
            key=lambda x: abs(x.sentiment_score),
            reverse=True,
        )

        return SentimentAnalysisResult(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            sentiment_score=avg_score,
            sentiment_label=label,
            news_count=len(all_news),
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            top_news=sorted_news[:5],  # Top 5 most extreme sentiment news items
        )

    def filter_significant_news(
        self,
        news_items: list[NewsItem],
    ) -> list[NewsItem]:
        """
        Filter news items with significant sentiment.

        Args:
            news_items: List of NewsItem objects

        Returns:
            List of NewsItem objects with significant sentiment
        """
        return [
            item for item in news_items if abs(item.sentiment_score) >= self.threshold
        ]

    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for sentiment analysis.

        Args:
            text: Raw text

        Returns:
            Preprocessed text
        """
        # Basic preprocessing - can be expanded as needed
        text = text.replace("\n", " ").replace("\r", " ")
        return " ".join(text.split())  # Remove extra whitespace


# Export default instance
sentiment = SentimentAnalyzer()
