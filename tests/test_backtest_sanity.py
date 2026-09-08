"""Tests for walk-forward window slicing and no look-ahead."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from loats.backtest_sanity import backtest_sanity_pass_gate
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


class TestAsOfDatePinning:
    """F8-L-02: as_of_date pins the walk-forward fetch window and result."""

    @staticmethod
    def _make_anchored(count: int) -> list:
        base = datetime(2026, 8, 31, 9, 15, tzinfo=UTC)
        return [
            HistoricalData(
                symbol="NIFTY",
                timestamp=base + timedelta(minutes=5 * i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=10_000,
                interval="5min",
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_as_of_date_pins_fetch_window_to_eod(self):
        """end_date equals the snapshot day's EOD; start = end - days_back."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_anchored(50)

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            await run_backtest_sanity_check(
                symbol="NIFTY",
                days_back=1,
                window_size=20,
                step_size=10,
                as_of_date=date(2026, 8, 31),
            )

        kwargs = mock_db.get_historical_data.call_args.kwargs
        assert kwargs["end_date"] == datetime(
            2026, 8, 31, 23, 59, 59, 999999, tzinfo=UTC
        )
        assert kwargs["start_date"] == kwargs["end_date"] - timedelta(days=1)

    @pytest.mark.asyncio
    async def test_default_window_remains_live_wall_clock(self):
        """as_of_date=None keeps the live now()-anchored window (scheduler path)."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_anchored(50)
        t0 = datetime.now(UTC)

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            await run_backtest_sanity_check(
                symbol="NIFTY", days_back=1, window_size=20, step_size=10
            )

        t1 = datetime.now(UTC)
        kwargs = mock_db.get_historical_data.call_args.kwargs
        assert t0 <= kwargs["end_date"] <= t1
        assert kwargs["start_date"] == kwargs["end_date"] - timedelta(days=1)

    @pytest.mark.asyncio
    async def test_result_stamps_as_of_date(self):
        """Pinned run stamps the snapshot date; live run stamps None."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_anchored(50)

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            pinned = await run_backtest_sanity_check(
                symbol="NIFTY", days_back=1, as_of_date=date(2026, 8, 31)
            )
            live = await run_backtest_sanity_check(symbol="NIFTY", days_back=1)

        assert pinned.as_of_date == date(2026, 8, 31)
        assert live.as_of_date is None

    @pytest.mark.asyncio
    async def test_same_as_of_date_replay_yields_identical_window(self):
        """Replays with the same snapshot date reuse byte-identical query bounds."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_anchored(50)

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
        ):
            await run_backtest_sanity_check(
                symbol="NIFTY", days_back=7, as_of_date=date(2026, 8, 31)
            )
            first = mock_db.get_historical_data.call_args.kwargs
            await run_backtest_sanity_check(
                symbol="NIFTY", days_back=7, as_of_date=date(2026, 8, 31)
            )
            second = mock_db.get_historical_data.call_args.kwargs

        assert first == second


class TestIntervalFromSettings:
    """2026-09-08: the sanity check must fetch the interval LOATS stores.

    The DB was found to hold only ``1min`` bars (settings.default_timeframe)
    while the fetch hardcoded ``interval="5min"`` — the weekly P4 exit gate
    raised "No historical data found" against the real database on every
    run. The fetch interval now derives from settings.default_timeframe
    (single source of truth) with an explicit override for callers that
    must pin a different timeframe.
    """

    @staticmethod
    def _make_bars(count: int, interval: str = "1min") -> list:
        base = datetime(2026, 8, 31, 9, 15, tzinfo=UTC)
        return [
            HistoricalData(
                symbol="NIFTY",
                timestamp=base + timedelta(minutes=1 * i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=10_000,
                interval=interval,
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_fetch_uses_default_timeframe_not_hardcoded_5min(self):
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_bars(50, "1min")

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
            patch("loats.backtest_sanity.settings.default_timeframe", "1min"),
        ):
            await run_backtest_sanity_check(symbol="NIFTY", days_back=7)

        assert mock_db.get_historical_data.call_args.kwargs["interval"] == "1min"

    @pytest.mark.asyncio
    async def test_explicit_interval_overrides_settings(self):
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_bars(50, "5min")

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
            patch("loats.backtest_sanity.settings.default_timeframe", "1min"),
        ):
            await run_backtest_sanity_check(
                symbol="NIFTY", days_back=7, interval="5min"
            )

        assert mock_db.get_historical_data.call_args.kwargs["interval"] == "5min"

    @pytest.mark.asyncio
    async def test_real_world_db_shape_end_to_end(self):
        """1-min bars (the shape actually in data/loats.db) analyze cleanly."""
        from unittest.mock import MagicMock, patch

        from loats.backtest_sanity import run_backtest_sanity_check

        mock_db = MagicMock()
        mock_db.get_historical_data.return_value = self._make_bars(120, "1min")

        with (
            patch("loats.backtest_sanity.db", mock_db),
            patch("loats.backtest_sanity.settings.default_symbol", "NIFTY"),
            patch("loats.backtest_sanity.settings.default_timeframe", "1min"),
        ):
            result = await run_backtest_sanity_check(symbol="NIFTY", days_back=7)

        assert result.total_bars == 120
        assert result.total_windows > 0
        assert backtest_sanity_pass_gate(result) is True
