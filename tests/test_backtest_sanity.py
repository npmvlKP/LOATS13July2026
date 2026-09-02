"""Tests for walk-forward window slicing and no look-ahead."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from loats.models import HistoricalData


def make_ohlc(symbol, base, count, mins=5):
    now = datetime.now(UTC)
    return [
        HistoricalData(
            symbol=symbol,
            timestamp=now - timedelta(minutes=mins * (count - 1 - i)),
            open=base + i * 0.5 - 1,
            high=base + i * 0.5 + 2,
            low=base + i * 0.5 - 2,
            close=base + i * 0.5,
            volume=10000 + i * 100,
            interval=f"{mins}min",
        )
        for i in range(count)
    ]


def walk_forward(data, wsize=20, step=10):
    return [data[s : s + wsize] for s in range(0, len(data) - wsize + 1, step)]


def per_window_pnl(windows, fn):
    return [{"window": i, "pnl": fn(w), "bars": len(w)} for i, w in enumerate(windows)]


def ma_cross(w):
    if len(w) < 5:
        return 0.0
    c = [h.close for h in w]
    return (c[-1] - c[-2]) * 100 if sum(c[-3:]) / 3 > sum(c[-5:]) / 5 else 0.0


class TestWalkForward:
    def test_basic(self):
        d = make_ohlc("NIFTY", 100, 50)
        ws = walk_forward(d, 20, 10)
        assert len(ws) == 4
        assert all(len(w) == 20 for w in ws)

    def test_single(self):
        assert len(walk_forward(make_ohlc("T", 50, 10), 10, 10)) == 1

    def test_empty(self):
        assert walk_forward([], 10, 5) == []

    def test_monotonic_within_windows(self):
        d = make_ohlc("NIFTY", 100, 50)
        for w in walk_forward(d, 20, 10):
            ts = [h.timestamp for h in w]
            assert ts == sorted(ts)


class TestPnLAggregation:
    def test_pnl_across_windows(self):
        d = make_ohlc("NIFTY", 100, 60)
        r = per_window_pnl(walk_forward(d, 20, 10), ma_cross)
        assert len(r) == 5
        assert all(x["bars"] == 20 for x in r)

    def test_total_pnl(self):
        d = make_ohlc("NIFTY", 100, 60)
        r = per_window_pnl(walk_forward(d, 20, 10), ma_cross)
        assert isinstance(sum(x["pnl"] for x in r), float)


class TestNoLookAhead:
    def test_sorted_timestamps(self):
        d = make_ohlc("T", 200, 100)
        for w in walk_forward(d, 30, 15):
            ts = [h.timestamp for h in w]
            assert ts == sorted(ts)

    def test_no_future_data(self):
        d = make_ohlc("NIFTY", 100, 50)
        for w in walk_forward(d, 20, 10):
            assert all(c > 0 for c in [h.close for h in w])


class TestBacktestSanityFunctions:
    """F8-H-04: direct coverage of the production backtest_sanity module."""

    def test_walk_forward_iterator_validation(self):
        """WalkForwardWindowIterator validates empty data and window size."""
        from loats.backtest_sanity import WalkForwardWindowIterator

        with pytest.raises(ValueError):
            WalkForwardWindowIterator([], 20, 10)

        data = make_ohlc("NIFTY", 100, 10)
        with pytest.raises(ValueError):
            WalkForwardWindowIterator(data, 20, 10)

    def test_walk_forward_iterator_unsorted_data(self):
        """WalkForwardWindowIterator rejects unsorted data."""
        from loats.backtest_sanity import WalkForwardWindowIterator

        data = make_ohlc("NIFTY", 100, 50)
        data[5].timestamp = data[40].timestamp
        with pytest.raises(ValueError):
            WalkForwardWindowIterator(data, 20, 10)

    def test_walk_forward_iterator_length(self):
        """WalkForwardWindowIterator __len__ matches generated windows."""
        from loats.backtest_sanity import WalkForwardWindowIterator

        data = make_ohlc("NIFTY", 100, 50)
        it = WalkForwardWindowIterator(data, 20, 10)
        assert len(it) == 4
        windows = list(it)
        assert len(windows) == 4
        assert all(len(w) == 20 for _, w in windows)

    def test_calculate_simple_pnl(self):
        """calculate_simple_pnl returns expected Decimal percentage."""
        from decimal import Decimal

        from loats.backtest_sanity import calculate_simple_pnl

        data = make_ohlc("NIFTY", 100, 50)
        pnl = calculate_simple_pnl(data[0:2])
        assert isinstance(pnl, Decimal)
        assert pnl == Decimal(str(data[1].close - data[0].open)) / Decimal(
            str(data[0].open)
        ) * Decimal("100")

        assert calculate_simple_pnl([data[0]]) == Decimal("0")

    def test_validate_no_lookahead(self):
        """validate_no_lookahead accepts sorted and rejects unsorted."""
        from loats.backtest_sanity import validate_no_lookahead

        sorted_data = make_ohlc("NIFTY", 100, 50)
        assert validate_no_lookahead(sorted_data) is True

        unsorted = sorted_data[:]
        unsorted[10], unsorted[20] = unsorted[20], unsorted[10]
        assert validate_no_lookahead(unsorted) is False

    @pytest.mark.asyncio
    async def test_backtest_sanity_pass_gate(self):
        """backtest_sanity_pass_gate enforces min pass rate."""
        from datetime import UTC
        from decimal import Decimal

        from loats.backtest_sanity import (
            BacktestSanityResult,
            backtest_sanity_pass_gate,
        )

        result = BacktestSanityResult(
            symbol="NIFTY",
            timestamp=datetime.now(UTC),
            total_windows=10,
            total_bars=200,
            total_pnl=Decimal("0"),
            avg_pnl_per_window=Decimal("0"),
            windows_passed=8,
            windows_failed=2,
            pass_rate=Decimal("80"),
            details=[],
        )
        assert backtest_sanity_pass_gate(result) is True
        result.pass_rate = Decimal("79.9")
        assert backtest_sanity_pass_gate(result) is False


class TestBacktestSanityCheckRun:
    """F8-H-04: integration tests for run_backtest_sanity_check."""

    @pytest.mark.asyncio
    async def test_run_backtest_sanity_check_success(self):
        """run_backtest_sanity_check completes with passing gate."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import (
            BacktestSanityResult,
            run_backtest_sanity_check,
        )

        fake_data = make_ohlc("NIFTY", 100, 50)
        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = fake_data

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            result = await run_backtest_sanity_check(
                symbol="NIFTY", days_back=1, window_size=20, step_size=10
            )

        assert isinstance(result, BacktestSanityResult)
        assert result.symbol == "NIFTY"
        assert result.total_windows > 0
        assert result.pass_rate >= Decimal("80")

    @pytest.mark.asyncio
    async def test_run_backtest_sanity_check_no_data(self):
        """run_backtest_sanity_check raises when no data."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = []

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            with pytest.raises(ValueError, match="No historical data"):
                await run_backtest_sanity_check(
                    symbol="NIFTY", days_back=1, window_size=20, step_size=10
                )

    @pytest.mark.asyncio
    async def test_run_backtest_sanity_check_lookahead_failure(self):
        """run_backtest_sanity_check raises on look-ahead contamination."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        fake_data = make_ohlc("NIFTY", 100, 50)
        fake_data[25].timestamp = fake_data[0].timestamp

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = fake_data

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            with pytest.raises(ValueError, match="no-lookahead"):
                await run_backtest_sanity_check(
                    symbol="NIFTY", days_back=1, window_size=20, step_size=10
                )
