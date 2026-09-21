"""
Sentiment analysis module LOATS13July2026.
Implements RSS news sentiment analysis using Vader Sentiment.
"""

import asyncio
import hashlib
import json
import os
import re
import threading
import warnings
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

# F8-L-06 root cause: this knob MUST be read from the process environment
# BEFORE the newspaper import below. newspaper4k's parsers module emits the
# benign "nltk is not installed" UserWarning at *import* time when the
# optional [nlp] extra is absent, so a filter installed after that import is
# a verified no-op (regression-tested in tests/test_sentiment.py::
# TestNltkWarningSuppression). The filter is scoped to that exact message;
# no other warning is silenced. The knob works only via the process
# environment: pydantic-settings loads .env into the Settings model, never
# into os.environ, so a .env line cannot reach this guard. The durable fix
# is installing the optional extra once:  pip install 'newspaper4k[nlp]'
if os.environ.get("LOATS_SUPPRESS_NLTK_WARNING") == "1":
    warnings.filterwarnings(
        "ignore",
        message=re.escape("nltk is not installed"),
        category=UserWarning,
    )

import feedparser
from cachetools import TTLCache
from newspaper import Article
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .lazy_settings import LazySettings
from .loats_logging import get_logger
from .models import NewsItem, SentimentAnalysisResult
from .utils.cache import cache_manager
from .utils.lazy_singleton import lazy_singleton

# Lazy settings binding (TODO-18 / HC-21).
# Behavioral contract: importing this module builds NO Settings
# instance -- first attribute access proxies through get_settings(),
# so bare-env imports (no OPENALGO_API_KEY) stay clean.
settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()

logger = get_logger(__name__)

# F9-H-03 (TODO-4): article-content cache + last-known-good (LKG) serving.
# Per-article newspaper4k downloads are the cold-analysis cost that overran
# the producer window (root cause in
# tests/test_sentiment_f9h03_producer.py's module docstring). Caching
# completed extractions per URL makes every cycle strictly cheaper than the
# last -- finished downloads survive producer cancellation, unfinished ones
# retry next cycle against whatever has already accumulated. The legacy
# 5-minute RESULT cache is unchanged; a longer-TTL LKG entry lets the
# producer serve the previous good result immediately and refresh it
# cache-only in a detached task (the F8-M-02 invariant -- no signal outlives
# the producer window -- is untouched because the detached task writes
# caches, never signals).
ARTICLE_CACHE_TTL_SECONDS = 300
# Result-freshness window (ordinary 5-minute result cache entries).
RESULT_TTL_SECONDS = 300
# LKG retention horizon: how long the last-known-good entry survives in
# the cache (CacheManager honors per-entry TTL as of the BG-1 fix).
LKG_TTL_SECONDS = 900
# Degraded provenance threshold: an LKG result older than this is served
# with degraded=True. BG-1 close-out: this MUST sit strictly inside the
# retention horizon (freshness < threshold < retention). An entry older
# than retention is evicted and can never be served, so a threshold at or
# beyond retention (the original implementation, threshold == retention)
# made degraded=True unreachable dead code. 600 s = 2x the freshness
# window, leaving a 300 s band where stale-but-served LKG signals carry
# the degraded audit tag before a true cold start.
DEGRADED_THRESHOLD_SECONDS = 600

# F9-H-05 (TODO-14, ADR-0017): CMP P3 ensemble/decay/bounds delivery.
# CMP P3: "RSS+VADER ensemble (news 70/social 30), decay. Gate: scores
# always [-1,+1]".
# - Bounds ship as a HARD model invariant (Field(ge=-1, le=1) on BOTH
#   NewsItem.sentiment_score and SentimentAnalysisResult.sentiment_score
#   in models.py), so every future producer and every deserialized
#   payload crosses the gate -- not just this module's arithmetic.
# - Decay: each article contributes its VADER score weighted by
#   0.5 ** (age_hours / 4) (4-hour half-life, CMP P3 "decay"), applied
#   BEFORE averaging. Ages are timezone-aware UTC; non-positive ages
#   (future-dated items: clock skew, wrong feed tz) clamp to the fresh
#   weight 1.0 so skewed feeds cannot earn above-full weight.
# - Ensemble: ENSEMBLE_WEIGHTS is the DECLARATIVE leg-weight scaffold
#   CMP P3 asks for -- the news leg at 1.0 on the CMP 70% scale. It is
#   a machine-readable contract (imported and shape-pinned), NOT an
#   aggregation input: the system produces exactly one leg today, so
#   per-article weights are the recency factor alone. Wiring real 70/30
#   math when a social producer exists means an ADR amendment PLUS leg
#   tagging on items PLUS weighted-leg aggregation -- a code change,
#   stated here so no one expects one-key activation (adversarial round
#   2, AR-1: the earlier "falls out of the weights" phrasing
#   overclaimed). Semantic note: the normalized weighted
#   mean expresses RELATIVE recency -- mixed-age sets reweight toward
#   the fresh side (hand-computed pins in
#   tests/test_sentiment_p3_ensemble_f9h05.py), while a uniformly-aged
#   set scores its plain mean; whole-set staleness is surfaced by the
#   result timestamp and the F9-H-03 degraded chain, not the score.
SENTIMENT_HALF_LIFE_HOURS = 4.0
ENSEMBLE_WEIGHTS: dict[str, float] = {"news": 1.0}

# Module-level (not CacheManager): _extract_article_content runs on worker
# threads via asyncio.to_thread, so the cache needs a synchronous,
# thread-safe surface. cachetools TTLCache + an RLock gives exactly that,
# with per-entry TTL equal to the legacy result-cache TTL.
_article_cache: TTLCache[str, str] = TTLCache(
    maxsize=512, ttl=ARTICLE_CACHE_TTL_SECONDS
)
_article_cache_lock = threading.RLock()


def _article_cache_key(url: str) -> str:
    """Stable, URL-bound cache key for one article's extracted content."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"sentiment:article:{digest}:{url}"


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
        """Extract article content URL using newspaper4k.

        F9-H-03: downloads are cached per URL (thread-safe TTLCache, TTL
        5 min). A completed download survives producer cancellation, so
        every cycle re-downloads strictly less and cold analysis converges
        inside the producer window instead of timing out forever.
        """
        key = _article_cache_key(url)
        with _article_cache_lock:
            cached: str | None = _article_cache.get(key)
        if cached is not None:
            return cached
        try:
            article = Article(url)
            article.download()
            article.parse()
            content = self.preprocess_text(article.text)
        except Exception:
            logger.warning("Failed extract article content %s", url)
            return ""
        with _article_cache_lock:
            _article_cache[key] = content
        return content

    async def analyze_symbol_sentiment(
        self,
        symbol: str,
        rss_urls: list[str],
        max_items: int = 20,
    ) -> SentimentAnalysisResult:
        """Analyze sentiment for a specific symbol across multiple RSS feeds
        asynchronously."""
        # Create cache key based on symbol and RSS URLs
        urls_digest = hashlib.sha256(
            "\n".join(sorted(rss_urls)).encode("utf-8")
        ).hexdigest()
        cache_key = f"sentiment:{symbol}:{urls_digest}:{max_items}"
        lkg_key = f"sentiment:lkg:{symbol}:{urls_digest}:{max_items}"

        # Try to get cached result first
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug(f"Sentiment cache hit for {symbol}")
                return SentimentAnalysisResult(**json.loads(cached_result))
            except Exception as e:
                logger.warning(f"Failed to parse cached sentiment result: {e}")

        # F9-H-03: result-cache miss -- serve last-known-good immediately and
        # refresh cache-only in a DETACHED task. The producer window must not
        # pay network cost; the detached task persists caches (never signals),
        # so the F8-M-02 invariant (no signal outlives the window) is intact.
        lkg_raw = await cache_manager.get(lkg_key)
        if lkg_raw:
            try:
                lkg_result = SentimentAnalysisResult(**json.loads(lkg_raw))
                age_s = (datetime.now(UTC) - lkg_result.timestamp).total_seconds()
                lkg_result.degraded = age_s > DEGRADED_THRESHOLD_SECONDS
                asyncio.create_task(
                    self._refresh_caches_only(
                        cache_key, lkg_key, symbol, rss_urls, max_items
                    )
                )
                logger.debug(
                    "Sentiment LKG served for %s (age=%.0fs, degraded=%s)",
                    symbol,
                    age_s,
                    lkg_result.degraded,
                )
                return lkg_result
            except Exception as e:
                logger.warning(f"Failed to serve sentiment LKG for {symbol}: {e}")

        # True cold start: run the SHARED aggregation core (F9-H-05: the
        # ensemble/decay semantics live in exactly one place; the inline
        # duplicate that preceded the ensemble was drift-prone
        # copy-paste) and store BOTH the 5-minute result entry and the
        # longer-TTL LKG entry. Seeding the per-article URL cache still
        # happens inside parse_rss_feed.
        sentiment_result = await self._compute_and_count(symbol, rss_urls, max_items)

        # Cache the result for 5 minutes (300 seconds), and seed the
        # longer-TTL LKG entry (F9-H-03) so future cache misses serve
        # immediately with the detached refresh.
        try:
            await cache_manager.set(
                cache_key, sentiment_result.model_dump_json(), ttl=RESULT_TTL_SECONDS
            )
            await cache_manager.set(
                lkg_key, sentiment_result.model_dump_json(), ttl=LKG_TTL_SECONDS
            )
            logger.debug(f"Cached sentiment result for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to cache sentiment result: {e}")

        return sentiment_result

    async def _refresh_caches_only(
        self,
        cache_key: str,
        lkg_key: str,
        symbol: str,
        rss_urls: list[str],
        max_items: int,
    ) -> None:
        """Detached cache-only refresh (F9-H-03).

        Runs OUTSIDE the producer window: re-runs the feed analysis with the
        SAME feed list the served LKG was built from (passed in explicitly --
        the composite key's digest is one-way and cannot be reversed) and
        overwrites the result + LKG entries. Never touches signals or the
        database -- the F8-M-02 invariant (producers never outlive the
        window; no late signal) is structurally preserved because this
        task cannot produce one.
        """
        try:
            fresh = await self._compute_and_count(symbol, rss_urls, max_items)
            await cache_manager.set(
                cache_key, fresh.model_dump_json(), ttl=RESULT_TTL_SECONDS
            )
            await cache_manager.set(
                lkg_key, fresh.model_dump_json(), ttl=LKG_TTL_SECONDS
            )
        except Exception as e:
            logger.warning(f"Sentiment background refresh failed: {e}")

    async def _compute_and_count(
        self,
        symbol: str,
        rss_urls: list[str],
        max_items: int,
    ) -> SentimentAnalysisResult:
        """Shared aggregation core: gather feeds, score, count, label.

        F9-H-05: this is the SINGLE ensemble implementation -- the
        inline cold-start path delegates here so the semantics cannot
        drift between the two callers. Neither caches nor persists --
        callers own the cache keys.
        """
        tasks = [self.parse_rss_feed(url, max_items) for url in rss_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_news: list[NewsItem] = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error("Sentiment analysis: feed failed: %s", result)
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
        # F9-H-05 (ADR-0017): recency-weighted ensemble mean. Each
        # article's VADER compound score is scaled by the 4-hour
        # half-life decay BEFORE the weighted average (CMP P3
        # "decay"); future-dated items clamp to the fresh weight 1.0
        # so clock-skewed feeds cannot earn above-full weight. The
        # final clamp enforces the CMP P3 gate at the aggregation
        # boundary (belt-and-braces: VADER is bounded and weighted
        # means of bounded values are bounded; the HARD gate is the
        # model Field(ge=-1, le=1) invariant).
        avg_score = 0.0
        if all_news:
            now = datetime.now(UTC)
            total_weight = 0.0
            weighted_sum = 0.0
            for item in all_news:
                age_hours = (now - item.published_date).total_seconds() / 3600.0
                weight = 0.5 ** (max(age_hours, 0.0) / SENTIMENT_HALF_LIFE_HOURS)
                weighted_sum += item.sentiment_score * weight
                total_weight += weight
            if total_weight > 0.0:
                avg_score = max(-1.0, min(1.0, weighted_sum / total_weight))
            else:
                # Adversarial round 2 (AR-2): every weight underflowed to
                # exactly 0.0 in binary64 -- all items older than ~179
                # days (0.5**(age/4) underflows below the smallest
                # subnormal). The deleted inline path returned the plain
                # mean for the identical input; degrade identically
                # instead of raising ZeroDivisionError out of the cold
                # path. Pinned in
                # tests/test_sentiment_p3_ensemble_f9h05.py::
                # TestAdversarialRound2.
                avg_score = max(
                    -1.0,
                    min(
                        1.0,
                        sum(i.sentiment_score for i in all_news) / len(all_news),
                    ),
                )
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


# F8-C-03 (2026-09-02): __init__ reads Settings() (sentiment_threshold);
# defer construction so imports stay credential-free (see
# utils/lazy_singleton.py). Test patches keep working via proxy __dict__.
sentiment: SentimentAnalyzer = lazy_singleton(SentimentAnalyzer)
