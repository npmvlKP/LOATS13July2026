"""R-14 bounded sentiment producer + F9-H-03 liveness alert delivery.

R-14 (28-29Sep live evidence): the sentiment producer's newspaper4k
download leg ran untimed inside the 8.0 s producer window -- cold-article
churn crossed the window, every sweep was cancelled pre-aggregation, the
15-min freshness gate starved (95+ min live 29Sep) while transport
counters stayed green. Fix shape (i)+(iv) from the risk register:
bounds INSIDE the thread leg (per-entry asyncio wait bound + socket
timeout + global concurrency cap + per-feed fetch timeout + per-feed
sweep budget with partial retention) and sustained-starvation
escalation to run health via the F9-H-03 liveness alert now actually
DELIVERING to Telegram (episode-deduplicated, recovery-reset).

Negative caching: a failed/timed-out extract previously re-downloaded
EVERY cycle (the moneycontrol 16-26 s/article churn that never
converged); failures are now remembered for the negative TTL so a cold
feed converges within bounded sweeps.
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import loats.sentiment as sentiment_module
from loats.orchestrator import TradingOrchestrator
from loats.sentiment import SentimentAnalyzer


def _make_entry(title: str, link: str) -> MagicMock:
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.published_parsed = None
    return entry


def _make_feed(entries: list[MagicMock]) -> MagicMock:
    feed = MagicMock()
    feed.entries = entries
    return feed


class TestArticleExtractBounds:
    """Bounds INSIDE the thread leg: wait-bound, socket timeout, cap."""

    async def test_extract_wait_bounded_slow_download_skipped(self):
        """A download exceeding the wait bound cannot stall the feed loop."""
        analyzer = SentimentAnalyzer()
        started = threading.Event()

        def slow_download(url: str) -> str:
            started.set()
            time.sleep(1.2)
            return "slow body"

        entries = [_make_entry("t1", "https://example.com/slow")]
        with (
            patch.object(sentiment_module, "ARTICLE_EXTRACT_WAIT_SECONDS", 0.2),
            patch.object(analyzer, "_extract_article_content", slow_download),
            patch.object(
                sentiment_module.feedparser,
                "parse",
                return_value=_make_feed(entries),
            ),
        ):
            started_at = time.monotonic()
            items = await analyzer.parse_rss_feed("https://feeds.example/slow")
            elapsed = time.monotonic() - started_at
        # The slow entry is skipped; the loop did NOT wait for the download.
        assert items == []
        assert elapsed < 1.0

    async def test_extract_success_still_produces_item(self):
        """The bound must not break the healthy path."""
        analyzer = SentimentAnalyzer()
        entries = [_make_entry("good news", "https://example.com/good")]
        with (
            patch.object(analyzer, "_extract_article_content", return_value="body"),
            patch.object(
                sentiment_module.feedparser,
                "parse",
                return_value=_make_feed(entries),
            ),
        ):
            items = await analyzer.parse_rss_feed("https://feeds.example/good")
        assert len(items) == 1
        assert items[0].title == "good news"

    async def test_newspaper_config_carries_socket_timeout(self):
        """The thread-side Article construction carries a socket timeout."""
        cfg = sentiment_module._news_config
        assert cfg.request_timeout == (
            sentiment_module.ARTICLE_EXTRACT_SOCKET_TIMEOUT_SECONDS
        )
        assert sentiment_module.ARTICLE_EXTRACT_SOCKET_TIMEOUT_SECONDS > 0

    async def test_concurrency_cap_enforced(self):
        """At most ARTICLE_EXTRACT_CONCURRENCY downloads run at once."""
        analyzer = SentimentAnalyzer()
        active = 0
        max_active = 0
        lock = threading.Lock()

        def tracked_download(url: str) -> str:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.15)
            with lock:
                active -= 1
            return "body"

        def feed_for(url: str) -> MagicMock:
            idx = url.rsplit("f", 1)[-1]
            return _make_feed(
                [
                    _make_entry(f"t{idx}{i}", f"https://example.com/f{idx}a{i}")
                    for i in range(10)
                ]
            )

        sentiment_module._ARTICLE_FAILURE_CACHE.clear()
        with (
            patch.object(sentiment_module, "ARTICLE_EXTRACT_WAIT_SECONDS", 2.0),
            patch.object(analyzer, "_extract_article_content", tracked_download),
            patch.object(
                sentiment_module.feedparser,
                "parse",
                side_effect=feed_for,
            ),
        ):
            await asyncio.gather(
                *(
                    analyzer.parse_rss_feed(f"https://feeds.example/f{i}")
                    for i in range(3)
                )
            )
        assert max_active <= sentiment_module.ARTICLE_EXTRACT_CONCURRENCY


class TestExtractNegativeCache:
    """Failed extracts must not re-download every cycle (convergence)."""

    def setup_method(self) -> None:
        sentiment_module._ARTICLE_FAILURE_CACHE.clear()

    async def test_failed_extract_negative_cached(self):
        """A failed extract is remembered; the retry reuses the failure."""
        analyzer = SentimentAnalyzer()
        instantiations = {"n": 0}

        class FailingArticle:
            def __init__(self, url: str, **kwargs: Any) -> None:
                instantiations["n"] += 1

            def download(self) -> FailingArticle:
                raise RuntimeError("connection reset")

            def parse(self) -> None:
                pass

        with (
            patch.object(sentiment_module, "ARTICLE_FAILURE_NEGATIVE_TTL_SECONDS", 60),
            patch.object(sentiment_module, "Article", FailingArticle),
        ):
            assert analyzer._extract_article_content("https://x/bad") == ""
            assert analyzer._extract_article_content("https://x/bad") == ""
        assert instantiations["n"] == 1  # second call served from negative cache

    async def test_negative_cache_expires_allows_redispatch(self):
        """Once the negative entry expires, the URL is re-dispatched."""
        analyzer = SentimentAnalyzer()
        instantiations = {"n": 0}

        class FailingArticle:
            def __init__(self, url: str, **kwargs: Any) -> None:
                instantiations["n"] += 1

            def download(self) -> FailingArticle:
                raise RuntimeError("connection reset")

            def parse(self) -> None:
                pass

        with (
            patch.object(sentiment_module, "ARTICLE_FAILURE_NEGATIVE_TTL_SECONDS", 60),
            patch.object(sentiment_module, "Article", FailingArticle),
        ):
            assert analyzer._extract_article_content("https://x/bad2") == ""
            assert analyzer._extract_article_content("https://x/bad2") == ""
            assert instantiations["n"] == 1  # second call negative-cached
            with sentiment_module._ARTICLE_FAILURE_LOCK:
                sentiment_module._ARTICLE_FAILURE_CACHE.clear()
            assert analyzer._extract_article_content("https://x/bad2") == ""
            assert instantiations["n"] == 2  # expired entry re-dispatched

    async def test_successful_extract_not_negative_cached(self):
        """Only failures enter the negative cache; successes are positive."""
        analyzer = SentimentAnalyzer()

        class OkArticle:
            text = ""

            def __init__(self, url: str, **kwargs: Any) -> None:
                OkArticle.text = ""

            def download(self) -> OkArticle:
                return self

            def parse(self) -> None:
                OkArticle.text = "clean body text"

        with (
            patch.object(sentiment_module, "ARTICLE_FAILURE_NEGATIVE_TTL_SECONDS", 60),
            patch.object(sentiment_module, "Article", OkArticle),
        ):
            assert (
                analyzer._extract_article_content("https://x/ok") == "clean body text"
            )
        with sentiment_module._ARTICLE_FAILURE_LOCK:
            assert not sentiment_module._ARTICLE_FAILURE_CACHE


class TestFeedBudgets:
    """Per-feed fetch timeout and sweep budget with partial retention."""

    async def test_feed_fetch_timeout_returns_empty_bounded(self):
        analyzer = SentimentAnalyzer()

        def slow_parse(url: Any) -> MagicMock:
            time.sleep(1.2)
            return _make_feed([])

        with (
            patch.object(sentiment_module, "FEED_FETCH_TIMEOUT_SECONDS", 0.2),
            patch.object(sentiment_module.feedparser, "parse", slow_parse),
        ):
            started = time.monotonic()
            items = await analyzer.parse_rss_feed("https://feeds.example/dead")
            elapsed = time.monotonic() - started
        assert items == []
        assert elapsed < 1.0

    async def test_feed_sweep_budget_retains_partial_items(self):
        """Work extracted before the budget fires is RETAINED, not lost."""
        analyzer = SentimentAnalyzer()
        entries = [_make_entry(f"t{i}", f"https://example.com/p{i}") for i in range(6)]

        def slow_extract(url: str) -> str:
            time.sleep(0.5)
            return "body"

        with (
            patch.object(sentiment_module, "FEED_SWEEP_BUDGET_SECONDS", 0.8),
            patch.object(analyzer, "_extract_article_content", slow_extract),
            patch.object(
                sentiment_module.feedparser,
                "parse",
                return_value=_make_feed(entries),
            ),
        ):
            items = await analyzer.parse_rss_feed("https://feeds.example/slowfeed")
        assert 0 < len(items) < 6  # partial retention inside the budget

    async def test_healthy_feed_completes_within_budget(self):
        analyzer = SentimentAnalyzer()
        entries = [_make_entry(f"t{i}", f"https://example.com/q{i}") for i in range(3)]
        with (
            patch.object(sentiment_module, "FEED_SWEEP_BUDGET_SECONDS", 5.0),
            patch.object(analyzer, "_extract_article_content", return_value="b"),
            patch.object(
                sentiment_module.feedparser,
                "parse",
                return_value=_make_feed(entries),
            ),
        ):
            items = await analyzer.parse_rss_feed("https://feeds.example/ok")
        assert len(items) == 3


class TestLivenessAlertDelivery:
    """F9-H-03 acceptance: the liveness ALERT reaches Telegram."""

    def _orchestrator(self) -> TradingOrchestrator:
        return TradingOrchestrator()

    def _regular_patches(self, latest_signal: Any) -> tuple[Any, Any, Any]:
        stale_signal = MagicMock()
        stale_signal.timestamp = latest_signal
        fake_rules = MagicMock()
        fake_rules.session_state.value = "REGULAR"
        fake_cfg = MagicMock()
        fake_cfg.default_symbol = "NIFTY"
        fake_cfg.sentiment_liveness_max_age_minutes = 15.0
        mdb = MagicMock()
        mdb.async_get_latest_signals = AsyncMock(return_value=[stale_signal])
        return fake_rules, fake_cfg, mdb

    async def test_stale_liveness_sends_telegram_once_per_episode(self):
        o = self._orchestrator()
        fake_rules, fake_cfg, mdb = self._regular_patches(
            datetime.now(UTC) - timedelta(minutes=95)
        )
        fake_alerts = MagicMock()
        fake_alerts.send_system_alert = AsyncMock(return_value=True)
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db", mdb),
            patch("loats.orchestrator.rules_engine", fake_rules),
            patch("loats.orchestrator.alerts", fake_alerts),
        ):
            assert await o._check_sentiment_liveness() is False
            assert fake_alerts.send_system_alert.await_count == 1
            args, kwargs = fake_alerts.send_system_alert.await_args
            assert "sentiment" in args[0].lower()
            assert kwargs.get("alert_type") == "warning"
            # Episode dedupe: the next stale cycle does NOT re-send.
            assert await o._check_sentiment_liveness() is False
            assert fake_alerts.send_system_alert.await_count == 1

    async def test_recovery_resets_episode_and_logs(self):
        o = self._orchestrator()
        fake_rules, fake_cfg, mdb = self._regular_patches(
            datetime.now(UTC) - timedelta(minutes=95)
        )
        fake_alerts = MagicMock()
        fake_alerts.send_system_alert = AsyncMock(return_value=True)
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db", mdb),
            patch("loats.orchestrator.rules_engine", fake_rules),
            patch("loats.orchestrator.alerts", fake_alerts),
        ):
            await o._check_sentiment_liveness()
            # Recover: fresh signal persisted.
            fresh = MagicMock()
            fresh.timestamp = datetime.now(UTC)
            mdb.async_get_latest_signals = AsyncMock(return_value=[fresh])
            assert await o._check_sentiment_liveness() is True
            assert o._sentiment_liveness_alerted is False
            # A NEW starvation episode alerts again.
            mdb.async_get_latest_signals = AsyncMock(
                return_value=[
                    MagicMock(timestamp=datetime.now(UTC) - timedelta(minutes=40))
                ]
            )
            assert await o._check_sentiment_liveness() is False
            assert fake_alerts.send_system_alert.await_count == 2

    async def test_delivery_failure_is_loud_in_logs(self, caplog):
        import logging

        o = self._orchestrator()
        fake_rules, fake_cfg, mdb = self._regular_patches(
            datetime.now(UTC) - timedelta(minutes=95)
        )
        fake_alerts = MagicMock()
        fake_alerts.send_system_alert = AsyncMock(return_value=False)
        with (
            patch("loats.orchestrator.get_settings", return_value=fake_cfg),
            patch("loats.orchestrator.db", mdb),
            patch("loats.orchestrator.rules_engine", fake_rules),
            patch("loats.orchestrator.alerts", fake_alerts),
            caplog.at_level(logging.ERROR, logger="loats.orchestrator"),
        ):
            assert await o._check_sentiment_liveness() is False
        assert any("NOT delivered" in rec.getMessage() for rec in caplog.records)


class TestAlertSuppressionVisibility:
    """The silent-False class: suppression must be observable."""

    async def test_uninitialized_bot_warning(self, caplog):
        import logging

        from loats.alerts import AlertSystem

        system = AlertSystem()
        with caplog.at_level(logging.WARNING, logger="loats.alerts"):
            result = await system.send_alert("hello", "info")
        assert result is False
        assert any(
            "not delivered" in rec.getMessage().lower() for rec in caplog.records
        )

    async def test_polling_task_failure_logged_and_rearmed(self):
        """A dead polling task must log loudly and clear _running."""
        from loats.alerts import AlertSystem

        system = AlertSystem()
        app = MagicMock()
        app.updater = MagicMock()
        app.initialize = AsyncMock()
        app.start = AsyncMock()
        system.application = app
        captured: dict[str, Any] = {}

        def fake_create_task(coro: Any) -> MagicMock:
            coro.close()  # never scheduled
            task = MagicMock()

            def capture_callback(cb: Any) -> None:
                captured["cb"] = cb

            task.add_done_callback = capture_callback
            return task

        with patch("asyncio.create_task", side_effect=fake_create_task):
            await system.start()
        assert system._running is True
        callback = captured.get("cb")
        assert callable(callback)

        done_task = MagicMock()
        done_task.cancelled.return_value = False
        done_task.exception.return_value = RuntimeError("409 conflict")
        callback(done_task)
        assert system._running is False
