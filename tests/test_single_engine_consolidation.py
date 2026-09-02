"""F8-H-03 single-engine consolidation tests.

Verify that the scheduler no longer competes with the orchestrator for signal
production and that the orchestrator remains the sole engine of record.
"""

import asyncio
import inspect
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.models import HistoricalData, NewsItem, SentimentAnalysisResult
from loats.orchestrator import TradingOrchestrator
from loats.scheduler import TradingScheduler
from loats.strength import StrengthSource

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "test_single_engine.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def orchestrator():
    return TradingOrchestrator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(n: int = 60, symbol: str = "NIFTY") -> list[HistoricalData]:
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
    last = rows[-6].close
    for bar in rows[-5:]:
        bar.open = last
        bar.close = last + 15.0
        bar.high = bar.close + 4.0
        bar.low = bar.open - 4.0
        last = bar.close
    return rows


def _history_payload(rows: list[HistoricalData]) -> dict:
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


def _quote_payload(last_price: float) -> dict:
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


def _funds_payload() -> dict:
    return {
        "data": {
            "available_cash": 100000.0,
            "utilized_margin": 20000.0,
            "available_margin": 80000.0,
            "total_equity": 120000.0,
        }
    }


def _sentiment_result(score: float = 0.6) -> SentimentAnalysisResult:
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchedulerDoesNotEmitSignals:
    """Scheduler jobs must not create signal records after F8-H-03."""

    @pytest.mark.asyncio
    async def test_scheduler_adds_only_support_jobs(self):
        sched = TradingScheduler()
        mock_add_job = AsyncMock()
        sched.scheduler.add_job = mock_add_job
        await sched._add_jobs()

        ids = {call.kwargs["id"] for call in mock_add_job.call_args_list}
        assert ids == {
            "market_status_check",
            "data_cleanup",
            "backtest_sanity_check",
        }
        assert "ta_scan" not in ids
        assert "sentiment_scan" not in ids

    @pytest.mark.asyncio
    async def test_run_once_retired_signal_jobs_warn_and_no_op(self):
        sched = TradingScheduler()
        with patch("loats.scheduler.logger") as mock_logger:
            await sched.run_once("ta_scan")
            await sched.run_once("sentiment_scan")

        warnings = [
            call.args[0]
            for call in mock_logger.warning.call_args_list
            if "retired" in call.args[0]
        ]
        assert len(warnings) == 2

    @pytest.mark.asyncio
    async def test_scheduler_start_does_not_run_signal_scans(self):
        sched = TradingScheduler()
        sched.scheduler.start = MagicMock()
        sched._start_market_status_check = AsyncMock()

        # Verify by source inspection that start() does not reference the
        # retired signal scans.  The methods no longer exist on the class.
        from loats import scheduler as sched_module

        source = inspect.getsource(sched_module.TradingScheduler.start)
        assert "run_ta_scan" not in source
        assert "run_sentiment_scan" not in source

        await sched.start()


class TestOrchestratorSoleEngineOfRecord:
    """With the scheduler retired, the orchestrator populates the signal table."""

    @pytest.mark.asyncio
    async def test_orchestrator_cycle_populates_signals_and_decides(
        self, temp_db, orchestrator
    ):
        rows = _make_history(60)
        history_payload = _history_payload(rows)
        quote_payload = _quote_payload(rows[-1].close)

        with (
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
            patch(
                "loats.orchestrator.validate_rss_feed",
                new_callable=AsyncMock,
            ) as mock_rss,
            patch(
                "loats.orchestrator.sentiment.analyze_symbol_sentiment",
                new_callable=AsyncMock,
            ) as mock_sentiment,
            patch("loats.trade_decision.rules_engine") as mock_rules,
        ):
            mock_history.return_value = history_payload
            mock_quotes.return_value = quote_payload
            mock_funds.return_value = _funds_payload()
            mock_positions.return_value = {"data": []}
            mock_rss.return_value = True
            mock_sentiment.return_value = _sentiment_result(0.6)
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "gating_passed"},
            )
            mock_rules.check_position_limits.return_value = (
                True,
                {"reason": "within_limits"},
            )
            mock_rules.session_state = "REGULAR"

            await orchestrator._execute_ta_analysis()
            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_volatility_analysis()
            await orchestrator._execute_price_action_analysis()

            stored = await temp_db.async_get_latest_signals("NIFTY", limit=10)
            sources = {s.metadata.get("source") for s in stored}
            assert sources >= {
                StrengthSource.TECHNICAL_ANALYSIS.value,
                StrengthSource.SENTIMENT.value,
                StrengthSource.VOLATILITY.value,
                StrengthSource.PRICE_ACTION.value,
            }

            await orchestrator.initialize()
            await orchestrator._execute_cmp_strategy()
            await orchestrator.shutdown()

        decisions = await asyncio.to_thread(
            temp_db.get_trade_decisions, symbol="NIFTY", limit=1
        )
        assert len(decisions) >= 1, (
            "Orchestrator must reach a TradeDecision with only its own signals"
        )

    @pytest.mark.asyncio
    async def test_no_scheduler_window_contention(self, temp_db, orchestrator):
        """Scheduler retired: a full orchestrator run leaves no duplicate-source
        pollution from the scheduler, and the 4-source window is valid.
        """
        rows = _make_history(60)
        history_payload = _history_payload(rows)
        quote_payload = _quote_payload(rows[-1].close)

        # Run the scheduler paths that remain; they must not write signals.
        sched = TradingScheduler()
        sched.db = temp_db
        await sched.run_once("market_status_check")
        await sched.run_once("data_cleanup")

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
            mock_history.return_value = history_payload
            mock_quotes.return_value = quote_payload
            mock_rss.return_value = True
            mock_sentiment.return_value = _sentiment_result(0.6)
            await orchestrator._execute_ta_analysis()
            await orchestrator._execute_sentiment_analysis()
            await orchestrator._execute_volatility_analysis()
            await orchestrator._execute_price_action_analysis()

        stored = await temp_db.async_get_latest_signals("NIFTY", limit=10)
        source_counts: dict[str, int] = {}
        for sig in stored:
            source_counts[sig.metadata.get("source", "unknown")] = (
                source_counts.get(sig.metadata.get("source", "unknown"), 0) + 1
            )

        # With only the orchestrator writing, recent signals should have 4
        # distinct canonical sources.  A duplicate-source overflow is impossible
        # because the scheduler is retired.
        canonical = {s.value for s in StrengthSource}
        assert all(src in canonical for src in source_counts), source_counts
        assert len(source_counts) >= 4, source_counts
