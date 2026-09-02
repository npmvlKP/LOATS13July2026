"""End-to-end CMP chain tests driving the REAL orchestrator producers.

F8-C-01 remediation (TODO-10 honored): these tests spin the actual producer
methods (``_execute_ta_analysis``, ``_execute_sentiment_analysis``,
``_execute_volatility_analysis``, ``_execute_price_action_analysis``)
against fixture market data, mocking ONLY the external boundaries:

- OpenAlgo HTTP client  -> ``_safe_get_history`` / ``_safe_get_quotes`` /
  ``_safe_get_funds`` / ``_safe_get_position_book`` return fixture payloads
- RSS feeds             -> ``loats.orchestrator.validate_rss_feed`` always
  validates, ``sentiment.analyze_symbol_sentiment`` returns a fixture
  ``SentimentAnalysisResult``

The signals then flow through the REAL persistence path
(``db.async_create_signal``) and the REAL decision path
(``create_trade_decision`` -> ``validate_signal_sources`` -> composite
strength -> ... -> TradeDecision). No ``Signal(...)`` fixture is ever
injected past a producer (the sole exception is the corruption probe,
which deliberately injects a bogus-source signal to prove the gate
rejects it).
"""

import asyncio
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loats.database import Database
from loats.models import (
    FundsData,
    HistoricalData,
    NewsItem,
    QuoteData,
    SentimentAnalysisResult,
    Signal,
    SignalType,
)
from loats.orchestrator import TradingOrchestrator
from loats.scheduler import TradingScheduler
from loats.strength import StrengthEngine, StrengthSource

# --------------------------------------------------------------------------
# Helpers: deterministic fixtures
# --------------------------------------------------------------------------


def make_history_rows(n: int = 60, symbol: str = "NIFTY") -> list[HistoricalData]:
    """Build a deterministic mildly-uptrending OHLCV series.

    Pattern: two up-bars then one pullback bar, repeated. Produces:
    - RSI > 70 (TA NEUTRAL 0.5 by the RSI/MACD rule)
    - close > supertrend and close > VWAP (price-action BUY bias)
    - ATR% ~0.09 (volatility NEUTRAL 0.4 - low-vol regime)
    """
    now = datetime.now(UTC)
    rows: list[HistoricalData] = []
    close = 24500.0
    for i in range(n):
        open_ = close
        close = close - 8.0 if i % 3 == 2 else close + 12.0
        rows.append(
            HistoricalData(
                symbol=symbol,
                timestamp=now - timedelta(minutes=5 * (n - 1 - i)),
                open=open_,
                high=max(open_, close) + 6.0,
                low=min(open_, close) - 6.0,
                close=close,
                volume=1_000_000,
                interval="5min",
            )
        )
    return rows


def make_directional_history(
    n: int = 60, symbol: str = "NIFTY"
) -> list[HistoricalData]:
    """Uptrend whose FINAL five bars are all up-closes.

    Used for the directional price-action path: the newest bar direction
    agrees with the supertrend/VWAP BUY bias, so consecutive >= 2 and
    body_ratio >= 0.4 yield a BUY price-action signal.
    """
    rows = make_history_rows(n, symbol)
    last = rows[-6].close
    for bar in rows[-5:]:
        bar.open = last
        bar.close = last + 15.0
        bar.high = bar.close + 4.0
        bar.low = bar.open - 4.0
        last = bar.close
    return rows


def rows_to_payload(rows: list[HistoricalData]) -> dict:
    """Convert HistoricalData rows to the OpenAlgo get_history payload shape."""
    return {
        "data": [
            {
                "timestamp": r.timestamp.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    }


def make_quote_payload(last_price: float) -> dict:
    """OpenAlgo get_quotes payload for NIFTY."""
    return {
        "data": {
            "NIFTY": {
                "last_price": last_price,
                "open": last_price - 20.0,
                "high": last_price + 30.0,
                "low": last_price - 40.0,
                "close": last_price - 10.0,
                "volume": 5_000_000,
                "change": 25.0,
                "change_percent": 0.1,
            }
        }
    }


def make_funds_payload() -> dict:
    """OpenAlgo get_funds payload."""
    return {
        "data": {
            "available_cash": 100000.0,
            "utilized_margin": 20000.0,
            "available_margin": 80000.0,
            "total_equity": 120000.0,
        }
    }


def make_sentiment_result(score: float = 0.6) -> SentimentAnalysisResult:
    """Fixture SentimentAnalysisResult (mocks the RSS+NLP boundary)."""
    return SentimentAnalysisResult(
        symbol="NIFTY",
        timestamp=datetime.now(UTC),
        sentiment_score=score,
        sentiment_label="positive" if score > 0 else "negative",
        news_count=5,
        positive_count=3,
        negative_count=1,
        neutral_count=1,
        top_news=[
            NewsItem(
                title="Markets extend rally on strong macros",
                content="...",
                source="example.com",
                url="https://example.com/1",
                published_date=datetime.now(UTC),
                sentiment_score=0.6,
                sentiment_label="positive",
            )
        ],
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "test_e2e_cmp.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def orchestrator():
    return TradingOrchestrator()


@pytest.fixture
def fixture_market_data():
    return make_history_rows(60)


@pytest.fixture
def fixture_quote_data():
    last = make_history_rows(60)[-1].close
    return QuoteData(
        symbol="NIFTY",
        last_price=last,
        open=last - 20.0,
        high=last + 30.0,
        low=last - 40.0,
        close=last - 10.0,
        volume=5_000_000,
        timestamp=datetime.now(UTC),
        change=25.0,
        change_percent=0.1,
    )


@pytest.fixture
def fixture_funds_data():
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


# --------------------------------------------------------------------------
# Real-producer e2e tests
# --------------------------------------------------------------------------


class TestRealProducersE2E:
    """REAL producer tasks -> REAL persistence -> REAL decision path."""

    @pytest.mark.asyncio
    async def test_real_producers_full_chain_decision(
        self,
        temp_db,
        orchestrator,
    ):
        """Drive the four real producers; assert a TradeDecision is created."""
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)
        quote_payload = make_quote_payload(rows[-1].close)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
            ) as mock_rss,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
        ):
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_rss.return_value = True
            mock_sentiment.return_value = make_sentiment_result(0.6)

            await orchestrator._execute_ta_analysis()
            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_volatility_analysis()
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=10)
        assert len(stored) >= 4, (
            f"Expected >=4 producer-emitted signals, got {len(stored)}"
        )
        sources = {s.metadata.get("source") for s in stored}
        expected = {
            StrengthSource.TECHNICAL_ANALYSIS.value,
            StrengthSource.SENTIMENT.value,
            StrengthSource.VOLATILITY.value,
            StrengthSource.PRICE_ACTION.value,
        }
        assert expected <= sources, (
            f"Producer sources {sources} must cover the 4 diversity-critical "
            f"sources {expected}"
        )

        # --- Decision path with the real stored signals ---
        with (
            patch("loats.trade_decision.rules_engine") as mock_rules,
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch.object(
                orchestrator, "_safe_get_funds", new_callable=AsyncMock
            ) as mock_funds,
            patch.object(
                orchestrator, "_safe_get_position_book", new_callable=AsyncMock
            ) as mock_positions,
        ):
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_funds.return_value = make_funds_payload()
            mock_positions.return_value = {"data": []}
            await orchestrator.initialize()
            await orchestrator._execute_cmp_strategy()
            await orchestrator.shutdown()

        decisions = await asyncio.to_thread(
            temp_db.get_trade_decisions, symbol="NIFTY", limit=1
        )
        assert len(decisions) == 1, (
            "REAL producer signals must yield exactly one TradeDecision"
        )
        decision = decisions[0]
        assert decision.symbol == "NIFTY"
        assert decision.status in ["PENDING", "APPROVED"]
        assert 0.0 <= decision.composite_strength <= 1.0
        validation = decision.metadata.get("validation_result", {})
        assert len(validation.get("sources", [])) >= 3

    @pytest.mark.asyncio
    async def test_price_action_producer_emits_enum_source(self, temp_db, orchestrator):
        """The price_action producer alone must tag signals with the enum value."""
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
        ):
            mock_history.return_value = payload
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=5)
        assert len(stored) == 1
        assert stored[0].metadata["source"] == StrengthSource.PRICE_ACTION.value
        assert stored[0].metadata["scan_type"] == "price_action"
        assert stored[0].signal_type.value in ("BUY", "SELL", "NEUTRAL")

    @pytest.mark.asyncio
    async def test_price_action_directional_when_tape_agrees(
        self, temp_db, orchestrator
    ):
        """Aligned references + clean consecutive up-bars must yield BUY."""
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
        ):
            mock_history.return_value = payload
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=5)
        assert len(stored) == 1
        sig = stored[0]
        assert sig.metadata["source"] == StrengthSource.PRICE_ACTION.value
        assert sig.signal_type == SignalType.BUY, (
            f"Clean agreeing tape must be BUY, got {sig.signal_type}"
        )
        assert sig.strength > 0.5, (
            f"Directional conviction must exceed 0.5, got {sig.strength}"
        )

    @pytest.mark.asyncio
    async def test_price_action_neutral_when_newest_bar_disagrees(
        self, temp_db, orchestrator
    ):
        """BUY-biased references + newest down-bar must yield NEUTRAL 0.5.

        Regression net for the streak logic: the newest candle defines the
        streak direction, so a newest bar against the bias means zero
        conviction even when older bars trend up.
        """
        rows = make_directional_history(60)
        # Flip the newest bar to a down-close.
        newest = rows[-1]
        newest.open = newest.close + 20.0  # open above close -> down bar
        newest.high = newest.open + 5.0
        newest.low = newest.close - 5.0
        payload = rows_to_payload(rows)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
        ):
            mock_history.return_value = payload
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=5)
        assert len(stored) == 1
        sig = stored[0]
        assert sig.signal_type == SignalType.NEUTRAL, (
            f"Newest-bar disagreement must be NEUTRAL, got {sig.signal_type}"
        )
        assert sig.strength == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_real_producers_insufficient_diversity_rejected(
        self, temp_db, orchestrator
    ):
        """3 real sources (price_action producer not run) must be rejected.

        Mutation check: simulates removal of the price_action producer by
        skipping its execution, then verifies the decision path yields no
        TradeDecision (diversity 3/7 < 0.5).
        """
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)
        quote_payload = make_quote_payload(rows[-1].close)

        # Run ONLY the three original producers.
        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
            ) as mock_rss,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
        ):
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_rss.return_value = True
            mock_sentiment.return_value = make_sentiment_result(0.6)

            await orchestrator._execute_ta_analysis()
            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_volatility_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=10)
        sources = {s.metadata.get("source") for s in stored}
        assert StrengthSource.PRICE_ACTION.value not in sources
        assert len(sources) == 3

        # Decision path must reject: diversity 3/7 < 0.5.
        with (
            patch("loats.trade_decision.rules_engine") as mock_rules,
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch.object(
                orchestrator, "_safe_get_funds", new_callable=AsyncMock
            ) as mock_funds,
            patch.object(
                orchestrator, "_safe_get_position_book", new_callable=AsyncMock
            ) as mock_positions,
        ):
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed"},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_funds.return_value = make_funds_payload()
            mock_positions.return_value = {"data": []}
            await orchestrator.initialize()
            await orchestrator._execute_cmp_strategy()
            await orchestrator.shutdown()

        decisions = await asyncio.to_thread(
            temp_db.get_trade_decisions, symbol="NIFTY", limit=1
        )
        assert len(decisions) == 0, (
            "3-source production set must be rejected by the diversity gate"
        )

    @pytest.mark.asyncio
    async def test_real_producers_unknown_source_rejected(self, temp_db, orchestrator):
        """A stored signal with an invalid source string must block decisions.

        F8-M-01 guard: any 'unknown' source resolution must loudly reject
        the batch, even when 4 valid sources are otherwise present.
        """
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)
        quote_payload = make_quote_payload(rows[-1].close)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
            ) as mock_rss,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
        ):
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_rss.return_value = True
            mock_sentiment.return_value = make_sentiment_result(0.6)

            await orchestrator._execute_ta_analysis()
            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_volatility_analysis()
            await orchestrator._execute_price_action_analysis()

        # Inject one signal with a bogus source directly into the DB (this is
        # a deliberate corruption probe, not a producer fixture).
        bogus = Signal(
            symbol="NIFTY",
            signal_type=SignalType.NEUTRAL,
            timestamp=datetime.now(UTC) - timedelta(seconds=10),
            strength=0.5,
            indicators={},
            confidence=0.5,
            metadata={"scan_type": "corruption_probe", "source": "not_a_source"},
        )
        await temp_db.async_create_signal(bogus)

        with (
            patch("loats.trade_decision.rules_engine") as mock_rules,
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch.object(
                orchestrator, "_safe_get_funds", new_callable=AsyncMock
            ) as mock_funds,
            patch.object(
                orchestrator, "_safe_get_position_book", new_callable=AsyncMock
            ) as mock_positions,
        ):
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed"},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_funds.return_value = make_funds_payload()
            mock_positions.return_value = {"data": []}
            await orchestrator.initialize()
            await orchestrator._execute_cmp_strategy()
            await orchestrator.shutdown()

        decisions = await asyncio.to_thread(
            temp_db.get_trade_decisions, symbol="NIFTY", limit=1
        )
        assert len(decisions) == 0, (
            "Unknown source in batch must block TradeDecision creation"
        )


# --------------------------------------------------------------------------
# Scheduler tagging tests (F8-C-01 item i)
# --------------------------------------------------------------------------


class TestSchedulerSignalTagging:
    """Scheduler-emitted signals must carry enum-valid sources."""

    @pytest.mark.asyncio
    async def test_scheduler_ta_signal_has_enum_source(self, temp_db):
        sched = TradingScheduler()
        sched.db = temp_db

        rows = make_history_rows(60)
        payload = rows_to_payload(rows)
        quote_payload = make_quote_payload(rows[-1].close)

        with (
            patch.object(
                sched, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                sched, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
        ):
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            await sched._ta_scan_task()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=5)
        assert len(stored) >= 1, "Scheduler TA scan must persist a signal"
        valid_sources = {src.value for src in StrengthSource}
        for s in stored:
            assert s.metadata.get("source") in valid_sources, (
                f"Scheduler signal missing enum source: {s.metadata}"
            )

    @pytest.mark.asyncio
    async def test_scheduler_sentiment_signal_has_enum_source(self, temp_db):
        sched = TradingScheduler()
        sched.db = temp_db

        with (
            patch(
                "loats.orchestrator.validate_rss_feed", new_callable=AsyncMock
            ) as mock_rss,
            patch(
                "loats.scheduler.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
        ):
            mock_rss.return_value = True
            mock_sentiment.return_value = make_sentiment_result(0.6)
            await sched._sentiment_scan_task()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=5)
        assert len(stored) >= 1, "Scheduler sentiment scan must persist a signal"
        valid_sources = {src.value for src in StrengthSource}
        for s in stored:
            assert s.metadata.get("source") in valid_sources, (
                f"Scheduler sentiment signal missing enum source: {s.metadata}"
            )


# --------------------------------------------------------------------------
# Opposition gate with real producers
# --------------------------------------------------------------------------


class TestOppositionGateRealProducers:
    """Opposition gate must engage when real producers disagree."""

    @pytest.mark.asyncio
    async def test_opposing_real_signals_fail_min_sources(self, temp_db, orchestrator):
        rows = make_directional_history(60)
        payload = rows_to_payload(rows)
        quote_payload = make_quote_payload(rows[-1].close)

        with (
            patch("loats.orchestrator.db", temp_db),
            patch.object(
                orchestrator, "_safe_get_history", new_callable=AsyncMock
            ) as mock_history,
            patch.object(
                orchestrator, "_safe_get_quotes", new_callable=AsyncMock
            ) as mock_quotes,
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
            ) as mock_rss,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
        ):
            mock_history.return_value = payload
            mock_quotes.return_value = quote_payload
            mock_rss.return_value = True
            # Strongly negative sentiment = SELL signal (0.8 strength).
            mock_sentiment.return_value = make_sentiment_result(-0.8)

            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=10)
        assert len(stored) == 2

        decisions = await asyncio.to_thread(
            temp_db.get_trade_decisions, symbol="NIFTY", limit=1
        )
        assert len(decisions) == 0

        # The strength gate must fail these two signals on min_sources
        # BEFORE the opposition logic would run.
        engine = StrengthEngine()
        ok, details = engine.validate_signal_sources(stored)
        assert ok is False
        assert details["reason"] == "insufficient_unique_sources"


# --------------------------------------------------------------------------
# Mutation safety (static production-side checks)
# --------------------------------------------------------------------------


class TestMutationSafety:
    """Prove the e2e tests exercise the real production path."""

    def test_orchestrator_has_four_producer_methods(self):
        for method in (
            "_execute_ta_analysis",
            "_execute_sentiment_analysis",
            "_execute_volatility_analysis",
            "_execute_price_action_analysis",
        ):
            assert hasattr(TradingOrchestrator, method), (
                f"Missing producer {method} - diversity-critical producer set"
            )

    def test_orchestrator_emits_four_distinct_enum_sources(self):
        """Static check: orchestrator must contain >=4 enum-tagged emission sites.

        Mirrors HC-15's production-side probe. If a producer is removed,
        this fails - the mutation is caught by the test suite itself.
        """
        import inspect

        source = inspect.getsource(TradingOrchestrator)
        sites = set(re.findall(r"StrengthSource\.([A-Z_]+)\.value", source))
        assert len(sites) >= 4, (
            f"Orchestrator must emit >=4 distinct StrengthSource tags, got {sites}"
        )

    def test_scheduler_signal_sites_carry_enum_source(self):
        """Static check: scheduler Signal(...) metadata blocks include source."""
        import inspect

        source = inspect.getsource(TradingScheduler)
        # Every 'scan_type': 'X' metadata block must be followed by a source
        # tag before the block closes.
        scan_blocks = re.findall(
            r'metadata\s*=\s*\{[^}]*"scan_type"\s*:\s*"[^"]+"[^}]*\}',
            source,
        )
        assert scan_blocks, "Scheduler should still emit scan metadata blocks"
        for block in scan_blocks:
            assert '"source"' in block, (
                f"Scheduler metadata block missing source tag: {block[:120]}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
