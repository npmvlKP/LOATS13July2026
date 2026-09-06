"""Tests for per-source circuit breakers (CMP P5 / F8-L-01).

Acceptance criteria (F8-L-01):
- A per-source breaker registry keyed by ``StrengthSource`` exists.
- One source's breaker opens WITHOUT blocking others.
- Producers' external fetches run behind their own source's breaker.
"""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource
from loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from loats.utils.per_source_breakers import (
    PerSourceBreakerRegistry,
    get_source_breaker,
    get_source_breaker_registry,
    get_source_breaker_status,
    reset_source_breakers,
    source_breaker_call_async,
)


@pytest.fixture(autouse=True)
def _fresh_breakers():
    """Isolate breaker state between tests."""
    reset_source_breakers()
    yield
    reset_source_breakers()


def open_breaker(breaker: CircuitBreaker, failures: int) -> None:
    """Drive a breaker open with consecutive failing calls."""
    for _ in range(failures):
        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))


class TestRegistry:
    def test_one_breaker_per_enum_member(self):
        registry = get_source_breaker_registry()
        for source in registry.ACTIVE_SOURCES:
            breaker = registry.get(source)
            assert isinstance(breaker, CircuitBreaker)
            assert breaker.name == f"source:{source.value}"

    def test_registry_is_singleton(self):
        assert get_source_breaker_registry() is get_source_breaker_registry()
        assert get_source_breaker(StrengthSource.SENTIMENT) is get_source_breaker(
            StrengthSource.SENTIMENT
        )

    def test_breakers_are_independent_instances(self):
        seen = {
            source: get_source_breaker(source)
            for source in get_source_breaker_registry().ACTIVE_SOURCES
        }
        assert len({id(b) for b in seen.values()}) == len(seen)

    def test_status_covers_active_producer_sources(self):
        status = get_source_breaker_status()
        assert set(status.keys()) == {
            "ta",
            "sentiment",
            "volatility",
            "price_action",
        }
        for source_status in status.values():
            assert source_status["state"] == CircuitState.CLOSED.value

    def test_active_sources_match_production_emitters(self):
        """Fleet scope must equal the orchestrator's producer set (4)."""
        registry = get_source_breaker_registry()
        assert registry.ACTIVE_SOURCES == frozenset(
            {
                StrengthSource.TECHNICAL_ANALYSIS,
                StrengthSource.SENTIMENT,
                StrengthSource.VOLATILITY,
                StrengthSource.PRICE_ACTION,
            }
        )

    def test_dormant_sources_fail_closed(self):
        """F7-L-03 dormant enum members get NO breaker: a breaker that can
        never be exercised is fleet-status noise; ``get`` fail-closes."""
        registry = get_source_breaker_registry()
        for dormant in (
            StrengthSource.FUNDAMENTAL,
            StrengthSource.MACHINE_LEARNING,
            StrengthSource.OPTIONS_FLOW,
        ):
            with pytest.raises(ValueError, match="has no producer"):
                registry.get(dormant)
        # Status never advertises dormant sources.
        assert "fundamental" not in registry.get_status()
        assert "ml" not in registry.get_status()
        assert "options_flow" not in registry.get_status()

    def test_config_from_settings(self):
        registry = PerSourceBreakerRegistry()
        breaker = registry.get(StrengthSource.TECHNICAL_ANALYSIS)
        assert breaker.config.failure_threshold == 3
        assert breaker.config.timeout == 60.0

    def test_config_falls_back_on_bad_settings(self):
        class BadSettings:
            def __getattr__(self, name: str) -> Any:
                raise RuntimeError("settings unavailable")

        with patch("loats.utils.per_source_breakers.settings", BadSettings()):
            registry = PerSourceBreakerRegistry()
        breaker = registry.get(StrengthSource.VOLATILITY)
        assert breaker.config.failure_threshold == 3
        assert breaker.config.timeout == 60.0

    def test_config_ignores_mistyped_values(self):
        with patch(
            "loats.utils.per_source_breakers.settings",
            object(),  # knobs absent -> defaults
        ):
            registry = PerSourceBreakerRegistry()
        breaker = registry.get(StrengthSource.SENTIMENT)
        assert breaker.config.failure_threshold == 3
        assert breaker.config.timeout == 60.0

    def test_get_validates_unknown_source_strings(self):
        """An unknown source string is rejected (fail-closed), not silently
        given a breaker — source identity must stay enum-canonical."""
        registry = PerSourceBreakerRegistry()
        with pytest.raises(ValueError, match="is not a valid StrengthSource"):
            registry.get("ghost_probe")  # type: ignore[arg-type]
        assert set(registry.get_status().keys()) == {
            "ta",
            "sentiment",
            "volatility",
            "price_action",
        }


class TestIsolation:
    """The F8-L-01 acceptance test: one source opens, others unaffected."""

    def test_opening_one_source_does_not_block_others(self):
        ta_breaker = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)
        open_breaker(ta_breaker, ta_breaker.config.failure_threshold)
        assert ta_breaker.state == CircuitState.OPEN

        for source in get_source_breaker_registry().ACTIVE_SOURCES:
            if source is StrengthSource.TECHNICAL_ANALYSIS:
                continue
            assert get_source_breaker(source).state == CircuitState.CLOSED

    async def test_open_source_rejects_others_pass(self):
        async def ok() -> str:
            return "ok"

        async def boom() -> None:
            raise RuntimeError("boom")

        sentiment = get_source_breaker(StrengthSource.SENTIMENT)
        for _ in range(sentiment.config.failure_threshold):
            with pytest.raises(RuntimeError):
                await sentiment.call_async(boom)
        assert sentiment.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await source_breaker_call_async(StrengthSource.SENTIMENT, ok)
        assert "source:sentiment" in str(exc_info.value)

        # Every other source still executes normally.
        for source in get_source_breaker_registry().ACTIVE_SOURCES:
            if source is StrengthSource.SENTIMENT:
                continue
            assert await source_breaker_call_async(source, ok) == "ok"

    async def test_helper_routes_to_correct_breaker(self):
        async def boom() -> None:
            raise RuntimeError("boom")

        volatility = get_source_breaker(StrengthSource.VOLATILITY)
        for _ in range(volatility.config.failure_threshold):
            with pytest.raises(RuntimeError):
                await source_breaker_call_async(StrengthSource.VOLATILITY, boom)

        assert volatility.state == CircuitState.OPEN
        assert (
            get_source_breaker(StrengthSource.PRICE_ACTION).state == CircuitState.CLOSED
        )

    def test_reset_clears_all(self):
        for source in (StrengthSource.TECHNICAL_ANALYSIS, StrengthSource.SENTIMENT):
            breaker = get_source_breaker(source)
            open_breaker(breaker, breaker.config.failure_threshold)
        reset_source_breakers()
        assert all(
            get_source_breaker(s).state == CircuitState.CLOSED
            for s in get_source_breaker_registry().ACTIVE_SOURCES
        )


class TestOrchestratorWiring:
    async def test_ta_history_runs_behind_ta_breaker(self):
        orch = TradingOrchestrator()

        async def failing_fetch(symbol: str, interval: str) -> None:
            raise RuntimeError("history down")

        ta_breaker = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)
        for _ in range(ta_breaker.config.failure_threshold):
            with pytest.raises(RuntimeError):
                await orch._guarded_source_call(
                    StrengthSource.TECHNICAL_ANALYSIS,
                    failing_fetch,
                    "NIFTY",
                    "5min",
                )
        assert ta_breaker.state == CircuitState.OPEN
        assert get_source_breaker(StrengthSource.SENTIMENT).state == CircuitState.CLOSED

    async def test_breaker_failure_threshold_opens_isolation(self):
        """Sentiment producer failures trip only the sentiment breaker."""

        class FakeResult:
            sentiment_score = 0.0
            news_count = 0

        orch = TradingOrchestrator()

        async def failing_sentiment(symbol: str, feeds: list[str]) -> None:
            raise RuntimeError("rss down")

        sentiment_breaker = get_source_breaker(StrengthSource.SENTIMENT)
        for _ in range(sentiment_breaker.config.failure_threshold):
            with pytest.raises(RuntimeError):
                await orch._guarded_source_call(
                    StrengthSource.SENTIMENT,
                    failing_sentiment,
                    "NIFTY",
                    ["https://example.invalid/rss"],
                )
        assert sentiment_breaker.state == CircuitState.OPEN

        # Other producers' breakers are untouched and still pass calls.
        async def ok() -> str:
            return "ok"

        assert await source_breaker_call_async(StrengthSource.VOLATILITY, ok) == "ok"
        assert await source_breaker_call_async(StrengthSource.PRICE_ACTION, ok) == "ok"

    def test_orchestrator_status_accessor(self):
        orch = TradingOrchestrator()
        status = orch.get_source_breaker_status()
        assert set(status.keys()) == {"ta", "sentiment", "volatility", "price_action"}

    async def test_safe_get_history_records_rejection_on_source_breaker(self, caplog):
        """Fetch failures must be recorded by the per-source breaker.

        The composition root-cause (F8-L-01): the raw fetch raises, the
        source breaker counts the failure; degradation to ``None`` happens
        at the ``_guarded_source_get`` boundary — never inside the breaker
        chain, which would hide failures from every breaker.
        """

        async def reject_history(*args: Any, **kwargs: Any) -> Any:
            raise CircuitBreakerOpenError("openalgo", 1.0)

        orch = TradingOrchestrator()
        ta = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)
        with patch("loats.orchestrator.async_client") as mock_client:
            mock_client.get_history = reject_history
            result = await orch._guarded_source_get(
                StrengthSource.TECHNICAL_ANALYSIS,
                orch._fetch_history_bare,
                "NIFTY",
                "5min",
            )
        assert result is None  # degraded at the boundary...
        assert ta.stats.failed_calls >= 1  # ...but the failure was counted
        assert ta.stats.successful_calls == 0

    async def test_failures_accumulate_then_degrade(self, caplog):
        """Full P5 lifecycle: generic failures propagate AND count on the
        source breaker; once the threshold trips, the source degrades to
        ``None`` (skipped) instead of crashing the producer gather."""
        orch = TradingOrchestrator()
        ta = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)

        async def fail(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("api down")

        # 1. Below threshold: error propagates (pre-existing semantics).
        with patch("loats.orchestrator.async_client") as mock_client:
            mock_client.get_history = fail
            for _ in range(ta.config.failure_threshold):
                with pytest.raises(RuntimeError):
                    await orch._guarded_source_get(
                        StrengthSource.TECHNICAL_ANALYSIS,
                        orch._fetch_history_bare,
                        "NIFTY",
                        "5min",
                    )
        assert ta.stats.failed_calls == ta.config.failure_threshold
        assert ta.state == CircuitState.OPEN

        # 2. After the breaker opens: degraded None, error NOT raised...
        with caplog.at_level(logging.WARNING):
            result = await orch._guarded_source_get(
                StrengthSource.TECHNICAL_ANALYSIS,
                orch._fetch_history_bare,
                "NIFTY",
                "5min",
            )
        assert result is None
        assert any("degraded" in r.message for r in caplog.records)
        # ...and the rejection was recorded (no fetch was even attempted).
        assert ta.stats.rejected_calls >= 1

        # 3. Other sources are completely unaffected.
        assert get_source_breaker(StrengthSource.SENTIMENT).state == CircuitState.CLOSED
        assert (
            get_source_breaker(StrengthSource.PRICE_ACTION).state == CircuitState.CLOSED
        )

    async def test_full_producer_isolation_under_failure(self):
        """One producer's breaker opening must not block the others' fetches
        in a live-shaped cycle (both run concurrently through their own
        breakers)."""
        orch = TradingOrchestrator()

        async def ta_fail(symbol: str, interval: str) -> None:
            raise RuntimeError("ta feed down")

        async def sentiment_ok(symbol: str, feeds: list[str]) -> str:
            return "feeds-ok"

        ta = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)
        for _ in range(ta.config.failure_threshold):
            with pytest.raises(RuntimeError):
                await orch._guarded_source_call(
                    StrengthSource.TECHNICAL_ANALYSIS, ta_fail, "NIFTY", "5min"
                )

        results = await asyncio.gather(
            orch._guarded_source_call(
                StrengthSource.TECHNICAL_ANALYSIS, ta_fail, "NIFTY", "5min"
            ),
            return_exceptions=True,
        )
        assert isinstance(results[0], CircuitBreakerOpenError)

        # Sentiment is unaffected even though TA just rejected.
        assert (
            await orch._guarded_source_call(
                StrengthSource.SENTIMENT, sentiment_ok, "NIFTY", ["feed"]
            )
            == "feeds-ok"
        )

    async def test_degraded_fetch_mirrors_open_state_to_metrics(self):
        """A source-breaker rejection must flip the :8001 gauge so operator
        dashboards see the open breaker without scraping logs."""
        orch = TradingOrchestrator()
        captured: dict[str, bool] = {}

        async def already_open(*args: Any, **kwargs: Any) -> Any:
            raise CircuitBreakerOpenError("source:volatility", 60.0)

        with patch("loats.orchestrator.set_circuit_breaker_status") as mock_set:
            mock_set.side_effect = lambda component, open_status: captured.update(
                {component: open_status}
            )
            result = await orch._guarded_source_get(
                StrengthSource.VOLATILITY,
                already_open,
            )
        assert result is None  # degraded
        assert captured == {"source:volatility": True}


class TestTelegramStatusSurface:
    def test_status_message_lists_source_breakers(self):
        """/status must surface per-source breaker states (RUNBOOK
        "Circuit Breaker Status" operator surface)."""
        from loats.alerts import AlertSystem

        alert_system = AlertSystem.__new__(AlertSystem)
        alert_system.kill_switch_active = False
        alert_system.alert_cooldown = {}

        captured: dict[str, str] = {}

        async def fake_reply(message: str, **kwargs: Any) -> None:
            captured["message"] = message

        update = MagicMock()
        update.message.reply_text = AsyncMock(side_effect=fake_reply)
        context = MagicMock()

        import asyncio

        asyncio.run(alert_system._status(update, context))
        message = captured["message"]
        assert "Source breakers:" in message
        assert "all closed" in message  # fresh registry, nothing open

    def test_status_message_lists_open_sources(self):
        """Open breakers are named explicitly, HTML-escaped."""
        from loats.alerts import AlertSystem

        alert_system = AlertSystem.__new__(AlertSystem)
        alert_system.kill_switch_active = False
        alert_system.alert_cooldown = {}

        captured: dict[str, str] = {}

        async def fake_reply(message: str, **kwargs: Any) -> None:
            captured["message"] = message

        update = MagicMock()
        update.message.reply_text = AsyncMock(side_effect=fake_reply)
        context = MagicMock()

        ta = get_source_breaker(StrengthSource.TECHNICAL_ANALYSIS)
        open_breaker(ta, ta.config.failure_threshold)

        import asyncio

        asyncio.run(alert_system._status(update, context))
        message = captured["message"]
        assert "source breakers open" in message or "ta" in message
        assert "🔴" in message
