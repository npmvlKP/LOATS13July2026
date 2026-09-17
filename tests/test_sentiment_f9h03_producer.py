"""F9-H-03 (TODO-4): sentiment producer effectively DEAD -- remediation pins.

Forensic root cause (recorded in
docs/audit-history/15Sep2026-FR9-forensic-review-report.md, re-verified live
17 Sep 2026): the orchestrator's producer window (settings.producer_window_seconds,
8 s) is shorter than the worst-case cold analysis (per-article newspaper4k
downloads, ~8-10 s). asyncio.wait_for cancels the gather; the cancellation
lands BEFORE analyze_symbol_sentiment's 5-minute result cache-set and before
async_create_signal, so every cycle starts cold: 2,133 "Sentiment analysis
exceeded budget: ~8000 ms" warnings in the live 17Sep log, zero producer
lines, zero sentiment signals since 13 Sep. The existing result cache is
unreachable dead weight under the loop's own cancellation semantics.

Remediation (TODO-4 spec), pinned here RED-first:

1. ARTICLE CONTENT CACHE keyed per URL (TTL 5 min): completed downloads
   survive producer cancellation, so each cycle re-downloads strictly less
   and the analysis converges inside the window.
2. LAST-KNOWN-GOOD (LKG) SERVING + DETACHED REFRESH: on result-cache miss,
   serve the previous good result immediately and refresh cache-only in a
   detached task (never awaited by the producer path -- the F8-M-02
   invariant "no signal outlives the window" is untouched because the
   background task writes caches, never signals).
3. DEGRADED TAGGING: stale LKG (beyond the LKG TTL) is still served (a
   signal beats no signal for the diversity gate) but flagged
   ``degraded=True``; the signal metadata carries the provenance tag.
4. PER-SOURCE LIVENESS ALERT: during REGULAR session, if the latest
   persisted sentiment signal is older than 15 minutes, log a WARNING
   naming the source -- the schedule-correlated blind spot FR9 called out
   ("diversity gate stays green on the other 4 sources") becomes visible.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.models import NewsItem, SentimentAnalysisResult
from loats.sentiment import LKG_TTL_SECONDS, SentimentAnalyzer

_SYMBOL = "TEST"
_URLS = ["http://test.com/feed"]


def _result(score: float = 0.5) -> SentimentAnalysisResult:
    return SentimentAnalysisResult(
        symbol=_SYMBOL,
        timestamp=datetime.now(UTC),
        sentiment_score=score,
        sentiment_label="positive" if score > 0 else "neutral",
        news_count=1,
        positive_count=1 if score > 0 else 0,
        negative_count=0,
        neutral_count=0 if score > 0 else 1,
        top_news=[],
    )


def _news(score: float) -> NewsItem:
    return NewsItem(
        title="t",
        content="c",
        source="test.com",
        url="http://test.com/1",
        published_date=datetime.now(UTC),
        sentiment_score=score,
        sentiment_label="positive" if score > 0 else "neutral",
    )


class TestArticleContentCache:
    """Part 1 -- URL-keyed article cache: downloads survive cancellation."""

    @pytest.mark.asyncio
    async def test_extract_hits_url_cache_before_network(self):
        analyzer = SentimentAnalyzer()
        from loats.sentiment import (
            _article_cache,
            _article_cache_key,
            _article_cache_lock,
        )

        key = _article_cache_key("http://test.com/a")
        with _article_cache_lock:
            _article_cache[key] = "cached body"
        try:
            with patch("loats.sentiment.Article") as mock_article:
                content = analyzer._extract_article_content("http://test.com/a")
            assert content == "cached body"
            mock_article.assert_not_called()
        finally:
            with _article_cache_lock:
                _article_cache.pop(key, None)

    @pytest.mark.asyncio
    async def test_extract_stores_content_in_url_cache(self):
        analyzer = SentimentAnalyzer()
        from loats.sentiment import (
            ARTICLE_CACHE_TTL_SECONDS,
            _article_cache,
            _article_cache_key,
            _article_cache_lock,
        )

        assert ARTICLE_CACHE_TTL_SECONDS == 300
        article = MagicMock()
        article.__enter__ = MagicMock(return_value=article)
        article.__exit__ = MagicMock(return_value=False)
        article.text = "fresh body"
        key = _article_cache_key("http://test.com/a")
        try:
            with patch("loats.sentiment.Article", return_value=article):
                content = analyzer._extract_article_content("http://test.com/a")
            assert content == "fresh body"
            with _article_cache_lock:
                assert _article_cache[key] == "fresh body"
        finally:
            with _article_cache_lock:
                _article_cache.pop(key, None)

    @pytest.mark.asyncio
    async def test_second_download_served_from_cache(self):
        """The convergence property: same URL downloaded twice = one network
        extraction; the second read is a cache hit."""
        analyzer = SentimentAnalyzer()
        from loats.sentiment import (
            _article_cache,
            _article_cache_key,
            _article_cache_lock,
        )

        key = _article_cache_key("http://test.com/a")
        with _article_cache_lock:
            _article_cache[key] = "already fetched"
        try:
            with patch("loats.sentiment.Article") as mock_article:
                first = analyzer._extract_article_content("http://test.com/a")
                second = analyzer._extract_article_content("http://test.com/a")
            assert first == "already fetched"
            assert second == "already fetched"
            mock_article.assert_not_called()
        finally:
            with _article_cache_lock:
                _article_cache.pop(key, None)

    def test_url_cache_key_is_stable_and_url_bound(self):
        from loats.sentiment import _article_cache_key

        assert _article_cache_key("http://test.com/a") == _article_cache_key(
            "http://test.com/a"
        )
        assert _article_cache_key("http://test.com/a") != _article_cache_key(
            "http://test.com/b"
        )


class TestLastKnownGoodServing:
    """Part 2 -- LKG serving + detached cache-only refresh."""

    @pytest.mark.asyncio
    async def test_result_cache_miss_serves_lkg_and_refreshes(self):
        analyzer = SentimentAnalyzer()
        good = _result(0.42)
        lkg_payload = good.model_dump_json()
        created_tasks = []
        real_create_task = asyncio.create_task

        def capture_create(coro, **kwargs):
            task = real_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        with (
            patch("loats.sentiment.cache_manager.get", new_callable=AsyncMock) as mget,
            patch(
                "loats.sentiment.cache_manager.set",
                new_callable=AsyncMock,
            ) as mset,
            patch.object(
                analyzer,
                "parse_rss_feed",
                new_callable=AsyncMock,
                return_value=[_news(0.5)],
            ) as mparse,
            patch(
                "loats.sentiment.asyncio.create_task",
                side_effect=capture_create,
            ),
        ):

            async def get_side(key: str):
                return None if "lkg" not in key else lkg_payload

            mget.side_effect = get_side
            result = await analyzer.analyze_symbol_sentiment(_SYMBOL, _URLS)
            assert result.sentiment_score == pytest.approx(0.42)
            assert result.degraded is False
            # Refresh is detached: the producer path must NOT have awaited
            # the feed parse in this cycle (checked BEFORE settling the
            # detached task).
            assert mparse.await_count == 0
            # Settle the detached refresh INSIDE the patch context -- the
            # task only runs when awaited, and the mocks must still be live.
            await asyncio.gather(*created_tasks)
        assert mparse.await_count > 0  # the detached refresh did the work
        set_keys = [c.args[0] for c in mset.call_args_list]
        assert any("lkg" not in k for k in set_keys)

    @pytest.mark.asyncio
    async def test_stale_lkg_served_with_degraded_true(self):
        analyzer = SentimentAnalyzer()
        stale_ts = datetime.now(UTC) - timedelta(seconds=LKG_TTL_SECONDS + 60)
        stale = SentimentAnalysisResult(
            symbol=_SYMBOL,
            timestamp=stale_ts,
            sentiment_score=0.3,
            sentiment_label="positive",
            news_count=2,
            positive_count=2,
            negative_count=0,
            neutral_count=0,
            top_news=[],
        )
        created_tasks = []
        real_create_task = asyncio.create_task

        def capture_create(coro, **kwargs):
            task = real_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        with (
            patch("loats.sentiment.cache_manager.get", new_callable=AsyncMock) as mget,
            patch(
                "loats.sentiment.cache_manager.set",
                new_callable=AsyncMock,
            ),
            patch.object(
                analyzer,
                "_compute_and_count",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "loats.sentiment.asyncio.create_task",
                side_effect=capture_create,
            ),
        ):

            async def get_side(key: str):
                return stale.model_dump_json() if "lkg" in key else None

            mget.side_effect = get_side
            result = await analyzer.analyze_symbol_sentiment(_SYMBOL, _URLS)
            await asyncio.gather(*created_tasks)
        assert result.degraded is True
        assert result.sentiment_score == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_no_cache_no_lkg_runs_inline_analysis(self):
        """True cold start (process boot): inline analysis still works and
        seeds BOTH caches."""
        analyzer = SentimentAnalyzer()
        with (
            patch(
                "loats.sentiment.cache_manager.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("loats.sentiment.cache_manager.set", new_callable=AsyncMock) as mset,
            patch.object(
                analyzer,
                "parse_rss_feed",
                new_callable=AsyncMock,
                return_value=[_news(0.8)],
            ),
        ):
            result = await analyzer.analyze_symbol_sentiment(_SYMBOL, _URLS)
        assert result.sentiment_score == pytest.approx(0.8)
        assert result.degraded is False
        set_keys = [c.args[0] for c in mset.call_args_list]
        assert any("lkg" in k for k in set_keys), "LKG entry must be seeded"
        assert any("lkg" not in k for k in set_keys), "result entry must be seeded"

    def test_lkg_ttl_constant_matches_spec(self):
        assert LKG_TTL_SECONDS == 900


class TestDegradedProvenance:
    """Part 3 -- degraded tag rides the signal into the audit trail."""

    @pytest.mark.asyncio
    async def test_degraded_flag_stored_on_result_model(self):
        result = _result(0.5)
        assert hasattr(result, "degraded")
        payload = json.loads(result.model_dump_json())
        assert payload["degraded"] is False

    @pytest.mark.asyncio
    async def test_orchestrator_carries_degraded_into_signal_metadata(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        ms = MagicMock()
        ms.default_symbol = "NIFTY"
        ms.producer_window_seconds = 0.05
        ms.sentiment_threshold = 0.1
        ms.rss_feeds = ["http://test.com/feed"]
        mock_result = MagicMock()
        mock_result.sentiment_score = 0.7
        mock_result.news_count = 5
        mock_result.degraded = True
        captured: dict = {}

        async def capture(signal):
            captured["metadata"] = signal.metadata
            return True

        with (
            patch("loats.orchestrator.settings", ms),
            patch("loats.orchestrator.get_settings", return_value=ms),
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("loats.orchestrator.sentiment") as msent,
            patch("loats.orchestrator.db") as mdb,
        ):
            msent.analyze_symbol_sentiment = AsyncMock(return_value=mock_result)
            mdb.async_create_signal = AsyncMock(side_effect=capture)
            await o._execute_sentiment_analysis()
        assert captured["metadata"].get("degraded") is True

    @pytest.mark.asyncio
    async def test_fresh_result_metadata_degraded_false(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        ms = MagicMock()
        ms.default_symbol = "NIFTY"
        ms.producer_window_seconds = 0.05
        ms.sentiment_threshold = 0.1
        ms.rss_feeds = ["http://test.com/feed"]
        mock_result = MagicMock()
        mock_result.sentiment_score = 0.7
        mock_result.news_count = 5
        mock_result.degraded = False
        captured: dict = {}

        async def capture(signal):
            captured["metadata"] = signal.metadata
            return True

        with (
            patch("loats.orchestrator.settings", ms),
            patch("loats.orchestrator.get_settings", return_value=ms),
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("loats.orchestrator.sentiment") as msent,
            patch("loats.orchestrator.db") as mdb,
        ):
            msent.analyze_symbol_sentiment = AsyncMock(return_value=mock_result)
            mdb.async_create_signal = AsyncMock(side_effect=capture)
            await o._execute_sentiment_analysis()
        assert captured["metadata"].get("degraded") is False


class TestPerSourceLivenessAlert:
    """Part 4 -- per-source liveness alert >15 min during REGULAR."""

    @pytest.mark.asyncio
    async def test_stale_signal_alerts_during_regular(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        stale_signal = MagicMock()
        stale_signal.timestamp = datetime.now(UTC) - timedelta(minutes=20)
        fake_rules = MagicMock()
        fake_rules.session_state.value = "REGULAR"
        fake_cfg = MagicMock()
        fake_cfg.default_symbol = "NIFTY"
        fake_cfg.sentiment_liveness_max_age_minutes = 15.0
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db") as mdb,
            patch("loats.orchestrator.rules_engine", fake_rules),
        ):
            mdb.async_get_latest_signals = AsyncMock(return_value=[stale_signal])
            result = await o._check_sentiment_liveness()
        assert result is False  # False = liveness violated

    @pytest.mark.asyncio
    async def test_fresh_signal_no_alert(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        fresh_signal = MagicMock()
        fresh_signal.timestamp = datetime.now(UTC) - timedelta(minutes=2)
        fake_rules = MagicMock()
        fake_rules.session_state.value = "REGULAR"
        fake_cfg = MagicMock()
        fake_cfg.default_symbol = "NIFTY"
        fake_cfg.sentiment_liveness_max_age_minutes = 15.0
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db") as mdb,
            patch("loats.orchestrator.rules_engine", fake_rules),
        ):
            mdb.async_get_latest_signals = AsyncMock(return_value=[fresh_signal])
            assert await o._check_sentiment_liveness() is True

    @pytest.mark.asyncio
    async def test_no_alert_outside_regular_session(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        stale_signal = MagicMock()
        stale_signal.timestamp = datetime.now(UTC) - timedelta(hours=3)
        fake_rules = MagicMock()
        fake_rules.session_state.value = "CLOSED"
        fake_cfg = MagicMock()
        fake_cfg.default_symbol = "NIFTY"
        fake_cfg.sentiment_liveness_max_age_minutes = 15.0
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db") as mdb,
            patch("loats.orchestrator.rules_engine", fake_rules),
        ):
            mdb.async_get_latest_signals = AsyncMock(return_value=[stale_signal])
            assert await o._check_sentiment_liveness() is True

    @pytest.mark.asyncio
    async def test_no_signals_at_all_alerts_during_regular(self):
        from loats.orchestrator import TradingOrchestrator

        o = TradingOrchestrator()
        fake_rules = MagicMock()
        fake_rules.session_state.value = "REGULAR"
        fake_cfg = MagicMock()
        fake_cfg.default_symbol = "NIFTY"
        fake_cfg.sentiment_liveness_max_age_minutes = 15.0
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db") as mdb,
            patch("loats.orchestrator.rules_engine", fake_rules),
        ):
            mdb.async_get_latest_signals = AsyncMock(return_value=[])
            assert await o._check_sentiment_liveness() is False
