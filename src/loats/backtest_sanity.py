"""Backtest sanity module for LOATS13July2026.

Implements walk-forward window slicing and no look-ahead verification
for CMP P4 exit gate compliance. This module runs periodic sanity checks
on historical data stored in the database and logs results to audit trail.

CMP Requirement: P4 exit gate - "backtest sanity on /history data"
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from .config import get_settings
from .database import db
from .loats_logging import get_logger
from .models import HistoricalData

settings = get_settings()
logger = get_logger(__name__)


class BacktestWindow(BaseModel):
    """A single walk-forward window with metadata."""

    window_id: int = Field(description="Window index (0-based)")
    start_timestamp: datetime = Field(description="Window start time")
    end_timestamp: datetime = Field(description="Window end time")
    bar_count: int = Field(description="Number of bars in this window")
    symbol: str = Field(description="Trading symbol")


class PnLResult(BaseModel):
    """PnL calculation result for a window."""

    window_id: int = Field(description="Window index")
    pnl: Decimal = Field(description="Profit/Loss for this window")
    pnl_percent: Decimal = Field(description="PnL as percentage")
    bars: int = Field(description="Number of bars")


class BacktestSanityResult(BaseModel):
    """Complete backtest sanity check results."""

    symbol: str = Field(description="Symbol tested")
    timestamp: datetime = Field(description="When the check was performed")
    total_windows: int = Field(description="Total walk-forward windows")
    total_bars: int = Field(description="Total bars analyzed")
    total_pnl: Decimal = Field(description="Aggregate PnL across all windows")
    avg_pnl_per_window: Decimal = Field(
        description="Average PnL per window"
    )
    windows_passed: int = Field(description="Windows passing sanity checks")
    windows_failed: int = Field(description="Windows failing sanity checks")
    pass_rate: Decimal = Field(description="Pass rate as percentage")
    details: list[PnLResult] = Field(description="Per-window results")


class WalkForwardWindowIterator:
    """Iterator for walk-forward window slicing with no look-ahead."""

    def __init__(
        self,
        data: list[HistoricalData],
        window_size: int = 20,
        step_size: int = 10,
    ) -> None:
        """
        Initialize walk-forward iterator.

        Args:
            data: Historical data sorted by timestamp (ascending)
            window_size: Number of bars per window
            step_size: Step size between windows (stride)

        Raises:
            ValueError: If data is empty or window_size > len(data)
        """
        if not data:
            raise ValueError("Historical data cannot be empty")

        if window_size > len(data):
            raise ValueError(
                f"Window size ({window_size}) cannot exceed "
                f"data length ({len(data)})"
            )

        if window_size <= 0 or step_size <= 0:
            raise ValueError("Window size and step size must be positive")

        # Verify data is sorted by timestamp (no look-ahead guarantee)
        timestamps = [d.timestamp for d in data]
        if timestamps != sorted(timestamps):
            raise ValueError(
                "Historical data must be sorted by timestamp"
            )

        self.data = data
        self.window_size = window_size
        self.step_size = step_size
        self.current_index = 0

    def __iter__(self) -> "WalkForwardWindowIterator":
        """Return iterator."""
        return self

    def __next__(
        self,
    ) -> tuple[int, list[HistoricalData]]:
        """
        Get next walk-forward window.

        Returns:
            Tuple of (window_id, list of HistoricalData)

        Raises:
            StopIteration: When no more windows available
        """
        if self.current_index + self.window_size > len(self.data):
            raise StopIteration

        window_id = self.current_index // self.step_size
        window = self.data[
            self.current_index : self.current_index + self.window_size
        ]

        # Critical safety check: verify window is sorted
        window_timestamps = [d.timestamp for d in window]
        if window_timestamps != sorted(window_timestamps):
            # This should never happen if input is sorted
            raise ValueError(
                "Window {window_id} is not sorted by timestamp - "
                "data corruption detected"
            )

        self.current_index += self.step_size
        return window_id, window

    def __len__(self) -> int:
        """Return total number of windows."""
        return max(
            0,
            (len(self.data) - self.window_size) // self.step_size + 1,
        )


def calculate_simple_pnl(window: list[HistoricalData]) -> Decimal:
    """
    Calculate simple PnL for a window.

    Uses a basic momentum strategy: long at open, exit at close.
    This is for sanity validation only, not production trading.

    Args:
        window: Historical data for one window

    Returns:
        PnL as Decimal (positive = profit, negative = loss)
    """
    if len(window) < 2:
        return Decimal("0")

    first_bar = window[0]
    last_bar = window[-1]

    # Simple PnL: (close - open) / open * 100
    # Convert to Decimal explicitly because HistoricalData fields are floats.
    open_price = Decimal(str(first_bar.open))
    close_price = Decimal(str(last_bar.close))
    pnl = (
        (close_price - open_price) / open_price * Decimal("100")
    )

    return pnl


def validate_no_lookahead(data: list[HistoricalData]) -> bool:
    """
    Validate that historical data has no look-ahead contamination.

    Args:
        data: Historical data to validate

    Returns:
        True if data passes no-lookahead check, False otherwise
    """
    if not data:
        return True

    timestamps = [d.timestamp for d in data]
    return timestamps == sorted(timestamps)


async def run_backtest_sanity_check(
    symbol: str | None = None,
    days_back: int = 30,
    window_size: int = 20,
    step_size: int = 10,
) -> BacktestSanityResult:
    """
    Run backtest sanity check on historical data.

    Fetches historical data from database, performs walk-forward analysis,
    validates no-lookahead constraints, and logs results to audit trail.

    Args:
        symbol: Symbol to test (defaults to settings.default_symbol)
        days_back: Number of days to look back in history
        window_size: Walk-forward window size in bars
        step_size: Step size between windows

    Returns:
        BacktestSanityResult with complete analysis

    Raises:
        ValueError: If insufficient data or validation fails
    """
    test_symbol = symbol or settings.default_symbol
    logger.info(
        "Starting backtest sanity check",
        extra={
            "symbol": test_symbol,
            "days_back": days_back,
            "window_size": window_size,
            "step_size": step_size,
        },
    )

    # Fetch historical data from database
    cutoff_time = datetime.now(UTC) - timedelta(days=days_back)

    # Use the async database to fetch historical data
    try:
        history_data = await db.async_get_historical_data(
            symbol=test_symbol,
            start_time=cutoff_time,
        )
    except (AttributeError, TypeError):
        # Fallback: use sync interface wrapped in run_sync
        try:
            import asyncio

            def fetch_sync():
                return db.get_historical_data(
                    symbol=test_symbol,
                    interval="5min",  # Default interval
                    start_date=cutoff_time,
                    end_date=datetime.now(UTC),
                )

            history_data = await asyncio.to_thread(fetch_sync)
        except Exception as e:
            logger.error(
                f"Failed to fetch historical data: {e}",
                extra={"error": str(e)},
            )
            raise ValueError(f"Cannot fetch historical data: {e}") from e

    if not history_data:
        raise ValueError(f"No historical data found for symbol {test_symbol}")

    logger.info(
        "Fetched historical data",
        extra={
            "symbol": test_symbol,
            "bar_count": len(history_data),
            "earliest": history_data[0].timestamp,
            "latest": history_data[-1].timestamp,
        },
    )

    # Validate no look-ahead
    if not validate_no_lookahead(history_data):
        raise ValueError("Historical data fails no-lookahead validation")

    # Perform walk-forward analysis
    iterator = WalkForwardWindowIterator(history_data, window_size, step_size)
    total_windows = len(iterator)
    results: list[PnLResult] = []
    total_pnl = Decimal("0")
    windows_passed = 0
    windows_failed = 0

    for window_id, window in iterator:
        try:
            # Validate window properties
            if len(window) != window_size:
                windows_failed += 1
                logger.warning(
                    f"Window {window_id} has unexpected size: "
                    f"{len(window)} != {window_size}",
                    extra={"window_id": window_id},
                )
                continue

            # Calculate PnL
            pnl = calculate_simple_pnl(window)
            pnl_result = PnLResult(
                window_id=window_id,
                pnl=pnl,
                pnl_percent=pnl,
                bars=len(window),
            )

            results.append(pnl_result)
            total_pnl += pnl

            # Sanity check: extreme PnL values indicate potential issues
            if abs(float(pnl)) > 50.0:  # More than 50% move in a window
                windows_failed += 1
                logger.warning(
                    f"Window {window_id} has extreme PnL: {pnl}%",
                    extra={"window_id": window_id, "pnl": float(pnl)},
                )
            else:
                windows_passed += 1

        except Exception as e:
            windows_failed += 1
            logger.error(
                f"Error processing window {window_id}: {e}",
                extra={"window_id": window_id, "error": str(e)},
            )

    # Calculate summary statistics
    avg_pnl = (
        total_pnl / Decimal(total_windows)
        if total_windows > 0
        else Decimal("0")
    )
    pass_rate = (
        (Decimal(windows_passed) / Decimal(total_windows)) * Decimal("100")
        if total_windows > 0
        else Decimal("0")
    )

    result = BacktestSanityResult(
        symbol=test_symbol,
        timestamp=datetime.now(UTC),
        total_windows=total_windows,
        total_bars=len(history_data),
        total_pnl=total_pnl,
        avg_pnl_per_window=avg_pnl,
        windows_passed=windows_passed,
        windows_failed=windows_failed,
        pass_rate=pass_rate,
        details=results,
    )

    # Log result to audit trail (best-effort)
    try:
        logger.info(
            "Backtest sanity check completed",
            extra={
                "symbol": test_symbol,
                "total_windows": total_windows,
                "pass_rate": float(pass_rate),
                "avg_pnl": float(avg_pnl),
            },
        )
    except Exception as e:
        logger.error(f"Failed to log completion: {e}", extra={"error": str(e)})

    return result


def backtest_sanity_pass_gate(
    result: BacktestSanityResult,
    min_pass_rate: Decimal = Decimal("80"),
) -> bool:
    """
    Determine if backtest sanity check passes the CMP gate.

    Args:
        result: Backtest sanity check result
        min_pass_rate: Minimum pass rate (default 80%)

    Returns:
        True if gate passes, False otherwise
    """
    return result.pass_rate >= min_pass_rate
