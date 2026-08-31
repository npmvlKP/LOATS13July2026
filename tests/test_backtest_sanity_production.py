"""Test suite for TODO-26 backtest_sanity production integration.

This test suite validates that backtest_sanity is properly wired
as a production driver in the LOATS system.

Tests:
1. Module importability and exports
2. Scheduler weekly job registration
3. On-demand execution via run_once()
4. No-lookahead validation logic
5. Walk-forward window iterator
6. Exit gate compliance (80% pass rate)
"""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest


def _find_project_root() -> Path:
    """Resolve project root robustly from this test file's location."""
    # __file__ resolves through WSL/cygwin-style paths on some agents;
    # use a real Windows absolute path with correct case.
    this_file = Path(__file__).resolve()
    # repo root contains both 'src' and 'tests' directories
    candidate = this_file.parent.parent
    if (candidate / "src").is_dir() and (candidate / "tests").is_dir():
        return candidate
    # Fallback: walk up until markers are found
    for parent in this_file.parents:
        if (parent / "src").is_dir() and (parent / "tests").is_dir():
            return parent
    raise FileNotFoundError("Could not resolve project root (missing src/tests)")


# Add project root to path
PROJECT_ROOT = _find_project_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestBacktestSanityModule:
    """Test backtest_sanity module structure and exports."""

    def test_module_importable(self) -> None:
        """Test that backtest_sanity module can be imported."""
        import loats.backtest_sanity  # noqa: F401

    def test_required_exports_present(self) -> None:
        """Test that all required exports are present."""
        import loats.backtest_sanity as bs

        required_exports = [
            "BacktestSanityResult",
            "BacktestWindow",
            "PnLResult",
            "WalkForwardWindowIterator",
            "run_backtest_sanity_check",
            "backtest_sanity_pass_gate",
            "calculate_simple_pnl",
            "validate_no_lookahead",
        ]

        for export in required_exports:
            assert hasattr(bs, export), f"Missing export: {export}"

    def test_walk_forward_iterator_methods(self) -> None:
        """Test WalkForwardWindowIterator has required methods."""
        import loats.backtest_sanity as bs

        required_methods = ["__init__", "__iter__", "__next__", "__len__"]

        for method in required_methods:
            assert hasattr(bs.WalkForwardWindowIterator, method), (
                f"WalkForwardWindowIterator missing method: {method}"
            )


class TestWalkForwardIterator:
    """Test WalkForwardWindowIterator functionality."""

    @pytest.fixture
    def sample_historical_data(self) -> list:
        """Create sample historical data for testing."""
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        return [
            HistoricalData(
                timestamp=base_time,
                symbol="NIFTY",
                open=19500.0,
                high=19550.0,
                low=19480.0,
                close=19520.0,
                volume=1000000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time.replace(minute=20),
                symbol="NIFTY",
                open=19520.0,
                high=19570.0,
                low=19500.0,
                close=19550.0,
                volume=1100000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time.replace(minute=25),
                symbol="NIFTY",
                open=19550.0,
                high=19600.0,
                low=19530.0,
                close=19580.0,
                volume=1200000,
                interval="5min",
            ),
        ]

    def test_iterator_initialization(self, sample_historical_data: list) -> None:
        """Test WalkForwardWindowIterator initialization."""
        import loats.backtest_sanity as bs

        iterator = bs.WalkForwardWindowIterator(
            sample_historical_data, window_size=2, step_size=1
        )

        assert iterator.window_size == 2
        assert iterator.step_size == 1
        assert iterator.current_index == 0

    def test_iterator_raises_on_empty_data(self) -> None:
        """Test iterator raises ValueError on empty data."""
        import loats.backtest_sanity as bs

        with pytest.raises(ValueError, match="Historical data cannot be empty"):
            bs.WalkForwardWindowIterator([])

    def test_iterator_raises_on_invalid_window_size(
        self, sample_historical_data: list
    ) -> None:
        """Test iterator raises ValueError when window_size > len(data)."""
        import loats.backtest_sanity as bs

        with pytest.raises(ValueError, match=r"Window size .* cannot exceed"):
            bs.WalkForwardWindowIterator(sample_historical_data, window_size=10)

    def test_iterator_raises_on_unsorted_data(self) -> None:
        """Test iterator raises ValueError when data is not sorted by timestamp."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        # Create unsorted data
        unsorted_data = [
            HistoricalData(
                timestamp=base_time.replace(minute=25),  # Later timestamp first
                symbol="NIFTY",
                open=Decimal("19550.0"),
                high=Decimal("19600.0"),
                low=Decimal("19530.0"),
                close=Decimal("19580.0"),
                volume=1200000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time,  # Earlier timestamp last
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19550.0"),
                low=Decimal("19480.0"),
                close=Decimal("19520.0"),
                volume=1000000,
                interval="5min",
            ),
        ]

        # Default window_size is 20; pass 2 so sort check runs before size check.
        with pytest.raises(ValueError, match="must be sorted by timestamp"):
            bs.WalkForwardWindowIterator(unsorted_data, window_size=2)

    def test_iterator_iteration(self, sample_historical_data: list) -> None:
        """Test WalkForwardWindowIterator produces correct windows."""
        import loats.backtest_sanity as bs

        iterator = bs.WalkForwardWindowIterator(
            sample_historical_data, window_size=2, step_size=1
        )

        windows = list(iterator)

        assert len(windows) == 2  # 3 data points, window size 2, step 1

        # First window: indices 0-1
        assert windows[0][0] == 0
        assert len(windows[0][1]) == 2
        assert windows[0][1][0].timestamp == sample_historical_data[0].timestamp
        assert windows[0][1][1].timestamp == sample_historical_data[1].timestamp

        # Second window: indices 1-2
        assert windows[1][0] == 1
        assert len(windows[1][1]) == 2
        assert windows[1][1][0].timestamp == sample_historical_data[1].timestamp
        assert windows[1][1][1].timestamp == sample_historical_data[2].timestamp


class TestNoLookaheadValidation:
    """Test no-lookahead validation logic."""

    def test_validate_no_lookahead_with_sorted_data(self) -> None:
        """Test validate_no_lookahead returns True for sorted data."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        sorted_data = [
            HistoricalData(
                timestamp=base_time,
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19550.0"),
                low=Decimal("19480.0"),
                close=Decimal("19520.0"),
                volume=1000000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time.replace(minute=20),
                symbol="NIFTY",
                open=Decimal("19520.0"),
                high=Decimal("19570.0"),
                low=Decimal("19500.0"),
                close=Decimal("19550.0"),
                volume=1100000,
                interval="5min",
            ),
        ]

        assert bs.validate_no_lookahead(sorted_data) is True

    def test_validate_no_lookahead_with_unsorted_data(self) -> None:
        """Test validate_no_lookahead returns False for unsorted data."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        unsorted_data = [
            HistoricalData(
                timestamp=base_time.replace(minute=20),
                symbol="NIFTY",
                open=Decimal("19520.0"),
                high=Decimal("19570.0"),
                low=Decimal("19500.0"),
                close=Decimal("19550.0"),
                volume=1100000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time,
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19550.0"),
                low=Decimal("19480.0"),
                close=Decimal("19520.0"),
                volume=1000000,
                interval="5min",
            ),
        ]

        assert bs.validate_no_lookahead(unsorted_data) is False

    def test_validate_no_lookahead_with_empty_data(self) -> None:
        """Test validate_no_lookahead returns True for empty data."""
        import loats.backtest_sanity as bs

        assert bs.validate_no_lookahead([]) is True


class TestSimplePnLCalculation:
    """Test simple PnL calculation."""

    def test_calculate_simple_pnl_profit(self) -> None:
        """Test PnL calculation for profitable window."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        window = [
            HistoricalData(
                timestamp=base_time,
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19550.0"),
                low=Decimal("19480.0"),
                close=Decimal("19520.0"),
                volume=1000000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time.replace(minute=20),
                symbol="NIFTY",
                open=Decimal("19520.0"),
                high=Decimal("19570.0"),
                low=Decimal("19500.0"),
                close=Decimal("19550.0"),
                volume=1100000,
                interval="5min",
            ),
        ]

        pnl = bs.calculate_simple_pnl(window)

        # Expected: (19550 - 19500) / 19500 * 100 = 50 / 19500 * 100 ≈ 0.256
        assert pnl > Decimal("0")

    def test_calculate_simple_pnl_loss(self) -> None:
        """Test PnL calculation for loss-making window."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        base_time = datetime(2026, 7, 13, 9, 15, tzinfo=UTC)

        window = [
            HistoricalData(
                timestamp=base_time,
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19510.0"),
                low=Decimal("19490.0"),
                close=Decimal("19500.0"),
                volume=1000000,
                interval="5min",
            ),
            HistoricalData(
                timestamp=base_time.replace(minute=20),
                symbol="NIFTY",
                open=Decimal("19495.0"),
                high=Decimal("19500.0"),
                low=Decimal("19480.0"),
                close=Decimal("19480.0"),
                volume=1100000,
                interval="5min",
            ),
        ]

        pnl = bs.calculate_simple_pnl(window)

        # Expected: (19480 - 19500) / 19500 * 100 = -20 / 19500 * 100 ≈ -0.102
        assert pnl < Decimal("0")

    def test_calculate_simple_pnl_single_bar(self) -> None:
        """Test PnL calculation returns 0 for single bar window."""
        import loats.backtest_sanity as bs
        from loats.models import HistoricalData

        window = [
            HistoricalData(
                timestamp=datetime(2026, 7, 13, 9, 15, tzinfo=UTC),
                symbol="NIFTY",
                open=Decimal("19500.0"),
                high=Decimal("19550.0"),
                low=Decimal("19480.0"),
                close=Decimal("19520.0"),
                volume=1000000,
                interval="5min",
            ),
        ]

        pnl = bs.calculate_simple_pnl(window)
        assert pnl == Decimal("0")


class TestBacktestSanityPassGate:
    """Test backtest sanity pass gate logic."""

    def test_pass_gate_with_high_pass_rate(self) -> None:
        """Test pass gate returns True when pass rate meets threshold."""
        import loats.backtest_sanity as bs

        result = bs.BacktestSanityResult(
            symbol="NIFTY",
            timestamp=datetime.now(UTC),
            total_windows=10,
            total_bars=200,
            total_pnl=Decimal("15.5"),
            avg_pnl_per_window=Decimal("1.55"),
            windows_passed=9,
            windows_failed=1,
            pass_rate=Decimal("90.0"),
            details=[],
        )

        assert bs.backtest_sanity_pass_gate(result) is True

    def test_pass_gate_with_custom_threshold(self) -> None:
        """Test pass gate respects custom threshold."""
        import loats.backtest_sanity as bs

        result = bs.BacktestSanityResult(
            symbol="NIFTY",
            timestamp=datetime.now(UTC),
            total_windows=10,
            total_bars=200,
            total_pnl=Decimal("15.5"),
            avg_pnl_per_window=Decimal("1.55"),
            windows_passed=7,
            windows_failed=3,
            pass_rate=Decimal("70.0"),
            details=[],
        )

        # Should pass with 70% threshold
        assert bs.backtest_sanity_pass_gate(result, min_pass_rate=Decimal("70")) is True

        # Should fail with 80% threshold
        assert (
            bs.backtest_sanity_pass_gate(result, min_pass_rate=Decimal("80")) is False
        )

    def test_pass_gate_fails_below_threshold(self) -> None:
        """Test pass gate returns False when pass rate below threshold."""
        import loats.backtest_sanity as bs

        result = bs.BacktestSanityResult(
            symbol="NIFTY",
            timestamp=datetime.now(UTC),
            total_windows=10,
            total_bars=200,
            total_pnl=Decimal("15.5"),
            avg_pnl_per_window=Decimal("1.55"),
            windows_passed=5,
            windows_failed=5,
            pass_rate=Decimal("50.0"),
            details=[],
        )

        assert bs.backtest_sanity_pass_gate(result) is False


class TestSchedulerIntegration:
    """Test scheduler integration for backtest_sanity."""

    def test_scheduler_has_backtest_sanity_method(self) -> None:
        """Test scheduler has run_backtest_sanity_check method."""
        from loats.scheduler import TradingScheduler

        assert hasattr(TradingScheduler, "run_backtest_sanity_check")

    def test_scheduler_has_weekly_job_registration(self) -> None:
        """Test scheduler registers backtest_sanity as weekly job."""
        scheduler_code = (PROJECT_ROOT / "src" / "loats" / "scheduler.py").read_text(
            encoding="utf-8", errors="ignore"
        )

        # Check for CronTrigger with Sunday schedule
        assert 'CronTrigger(day_of_week="sun"' in scheduler_code
        assert '"backtest_sanity_check"' in scheduler_code
        assert "run_backtest_sanity_check" in scheduler_code

    def test_scheduler_run_once_supports_backtest_sanity(self) -> None:
        """Test scheduler.run_once includes backtest_sanity_check case."""
        scheduler_code = (PROJECT_ROOT / "src" / "loats" / "scheduler.py").read_text(
            encoding="utf-8", errors="ignore"
        )

        assert 'job_id == "backtest_sanity_check"' in scheduler_code
        assert "await self.run_backtest_sanity_check()" in scheduler_code


class TestHealthCheckIntegration:
    """Test health check integration (S05, formerly HC-30)."""

    def test_hc30_exists(self) -> None:
        """S05 (legacy HC-30) still gates backtest-sanity wiring."""
        health_check_code = (
            PROJECT_ROOT / "scripts" / "fr7_health_check.py"
        ).read_text(encoding="utf-8", errors="ignore")

        assert 'id="S05"' in health_check_code
        assert "backtest sanity" in health_check_code.lower()
        assert "TODO-26" in health_check_code or "F7-L-06" in health_check_code
        assert "backtest_sanity.py" in health_check_code
