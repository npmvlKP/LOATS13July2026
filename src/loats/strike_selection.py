"""Strike Selection Module for LOATS13July2026.

High-performance strike selection engine that meets the <5ms latency target.
Implements optimized strike selection algorithms for options trading.
"""

import datetime
import math
import re
import statistics
import threading
from typing import Any

import numpy as np
from cachetools import TTLCache

from .loats_logging import get_logger
from .models import HistoricalData, OptionContract, OptionType

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# F9-M-05 (TODO-15): CMP S4 conformance constants.
#
# CMP S4 strike spec: "delta 0.50-0.60 buy; 2SD sell; OI check". The
# former implementation used an open "prefer close to 0.5" heuristic
# (abs(delta - 0.5) < 0.1) that rejected delta == 0.60 exactly and let
# delta == 0.41 through, and had no sell-side logic at all (FR9 F9-M-05).
# ---------------------------------------------------------------------------
DELTA_BAND_LOW = 0.50
DELTA_BAND_HIGH = 0.60
STD_DEVIATION_MULTIPLE = 2.0
MIN_OI_CONFIRMATION = 1

# Trading-day length for the sell-side horizon scaling. Root source:
# TradingRulesEngine.get_current_session() -- REGULAR session is
# 09:15-15:30 IST = 6 h 15 m. Scaling per-bar sigma to a horizon of
# trading days therefore multiplies by sqrt(days * 22500 / bar_seconds),
# which keeps per-bar history sigma and any 252-day annualized sigma in
# consistent units (252 * 22500/22500 == 252 bars).
TRADING_DAY_SECONDS = 22500.0

# Bar-interval labels are "<n>min" strings throughout the codebase
# (settings.default_timeframe is "1min"). Anything else is unit-ambiguous
# and must fail closed rather than guess a seconds-per-bar value.
_INTERVAL_PATTERN = re.compile(r"^(\d+)min$")


def _interval_seconds(interval: str | None) -> float | None:
    """Convert a bar-interval label to seconds; None when unparseable.

    Fail-closed by design (F9-M-05): a label the codebase never produces
    ("daily", "1h", "") must not silently default to a guessed unit --
    a wrong seconds-per-bar value scales the sell band quadratically.
    """
    if not interval:
        return None
    match = _INTERVAL_PATTERN.match(interval)
    if match is None:
        return None
    seconds = float(match.group(1)) * 60.0
    return seconds if seconds > 0.0 else None


def delta_in_buy_band(delta: float | None) -> bool:
    """CMP S4 BUY-side eligibility: |delta| within the closed [0.50, 0.60] band.

    Closed on both ends (0.50 and 0.60 are eligible); a contract without
    a delta is never eligible (fail-closed).
    """
    if delta is None:
        return False
    magnitude = abs(delta)
    return DELTA_BAND_LOW <= magnitude <= DELTA_BAND_HIGH


def estimate_bar_sigma(
    historical_data: list[HistoricalData],
) -> tuple[float, float] | None:
    """Estimate per-bar sigma and bar length from close prices.

    Sigma is the sample stdev of simple per-bar returns computed over a
    SINGLE-interval series; the series interval is validated before use.
    Returns None (fail-closed) when the history is too short for a
    sample stdev (fewer than 3 bars -> fewer than 2 returns), when
    intervals are mixed, or when the interval label is unparseable.
    """
    if len(historical_data) < 3:
        return None

    intervals = {bar.interval for bar in historical_data}
    if len(intervals) != 1:
        return None
    bar_seconds = _interval_seconds(intervals.pop())
    if bar_seconds is None:
        return None

    closes = [float(bar.close) for bar in historical_data]
    returns = [
        closes[i] / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] > 0.0
    ]
    if len(returns) < 2:
        return None
    return statistics.stdev(returns), bar_seconds


def two_sigma_sell_band(
    underlying_price: float,
    bar_sigma: float | None,
    bar_seconds: float | None,
    holding_days: float,
) -> tuple[float, float] | None:
    """SELL-side two-sigma price band for a holding horizon.

    Converts the per-bar sigma into a horizon sigma using the trading-day
    length (bars per day = TRADING_DAY_SECONDS / bar_seconds), so per-bar
    and annualized sigma conventions produce consistent units -- the FR9
    "consistent units" requirement. Returns None when any input is
    missing or non-positive (fail-closed).
    """
    if bar_sigma is None or bar_seconds is None:
        return None
    if underlying_price <= 0.0 or holding_days <= 0.0 or bar_seconds <= 0.0:
        return None
    bars_in_horizon = holding_days * TRADING_DAY_SECONDS / bar_seconds
    half_width = STD_DEVIATION_MULTIPLE * bar_sigma * math.sqrt(bars_in_horizon)
    band_half_width = underlying_price * half_width
    return (underlying_price - band_half_width, underlying_price + band_half_width)


class StrikeSelectionEngine:
    """High-performance strike selection engine with <5ms latency guarantee."""

    def __init__(self) -> None:
        """Initialize StrikeSelectionEngine."""
        self._cache: TTLCache[str, list[float]] = TTLCache(maxsize=1000, ttl=300)
        self._cache_lock = threading.RLock()  # Add thread-safe cache access
        self._cache_hits = 0
        self._cache_misses = 0
        self._initialized = True

    async def select_strikes(
        self,
        underlying_price: float,
        option_chain: list[OptionContract],
        strategy: str = "atm_straddle",
        width: int = 1,
        max_strikes: int = 5,
    ) -> list[float]:
        """Select optimal strikes based on strategy with <5ms latency.

        Args:
            underlying_price: Current price of underlying asset
            option_chain: List of available option contracts
            strategy: Selection strategy ('atm_straddle', 'delta_neutral', 'oi_based')
            width: Number of strikes on each side of ATM
            max_strikes: Maximum number of strikes to return

        Returns:
            List of selected strike prices

        Performance:
            - Uses pre-sorted data and binary search for O(log n) lookups
            - Avoids expensive computations in hot path
            - Designed for <5ms execution time
            - Optimized cache key generation
        """
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            if not option_chain:
                return []

            # Use cached result if available and parameters match
            # Optimized cache key generation for performance
            chain_sig = (
                len(option_chain),
                option_chain[0].strike_price if option_chain else 0,
            )
            cache_key = (
                f"{underlying_price:.2f}_{strategy}_{width}_{max_strikes}_{chain_sig}"
            )
            with self._cache_lock:
                if cache_key in self._cache:
                    self._cache_hits += 1
                    return self._cache[cache_key]
                self._cache_misses += 1

            # Extract and sort strike prices (O(n log n) but n is typically small)
            strikes = sorted({opt.strike_price for opt in option_chain})

            if strategy == "atm_straddle":
                selected = await self._select_atm_straddle_strikes(
                    underlying_price, strikes, width, max_strikes
                )
            elif strategy == "delta_neutral":
                selected = await self._select_delta_neutral_strikes(
                    underlying_price, option_chain, width, max_strikes
                )
            elif strategy == "oi_based":
                selected = await self._select_oi_based_strikes(
                    underlying_price, option_chain, width, max_strikes
                )
            else:
                # Default to ATM straddle
                selected = await self._select_atm_straddle_strikes(
                    underlying_price, strikes, width, max_strikes
                )

            # Cache result for future use
            with self._cache_lock:
                self._cache[cache_key] = selected
            return selected

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.005:  # 5ms threshold
                logger.warning(
                    f"Strike selection exceeded 5ms target: {duration * 1000:.2f}ms"
                )
            else:
                logger.debug(f"Strike selection completed in {duration * 1000:.2f}ms")

    async def _select_atm_straddle_strikes(
        self,
        underlying_price: float,
        strikes: list[float],
        width: int,
        max_strikes: int,
    ) -> list[float]:
        """Select ATM straddle strikes using binary search for O(log n) performance."""
        if not strikes:
            return []

        # Find closest strike to underlying price using binary search
        left, right = 0, len(strikes) - 1
        best_idx = 0

        while left <= right:
            mid = (left + right) // 2
            if strikes[mid] < underlying_price:
                left = mid + 1
            elif strikes[mid] > underlying_price:
                right = mid - 1
            else:
                best_idx = mid
                break

        # Handle case where exact match not found
        if left > right:
            # Price below all strikes
            if right == -1:
                best_idx = 0
            # Price above all strikes
            elif left >= len(strikes):
                best_idx = len(strikes) - 1
            else:
                # Choose closer strike (existing logic)
                if right >= 0 and (
                    left >= len(strikes)
                    or abs(strikes[right] - underlying_price)
                    <= abs(strikes[left] - underlying_price)
                ):
                    best_idx = right
                else:
                    best_idx = left

        # Edge cases: price below all strikes or above all strikes
        # Return nearest strike
        if right == -1 or left >= len(strikes):
            return [strikes[best_idx]][:max_strikes]

        # Select strikes around ATM for normal cases
        selected: list[float] = []
        start_idx = max(0, best_idx - width)
        end_idx = min(len(strikes) - 1, best_idx + width)

        for i in range(start_idx, end_idx + 1):
            if len(selected) >= max_strikes:
                break
            selected.append(strikes[i])

        # Ensure we don't exceed max_strikes
        return selected[:max_strikes]

    async def _select_delta_neutral_strikes(
        self,
        underlying_price: float,
        option_chain: list[OptionContract],
        width: int,
        max_strikes: int,
    ) -> list[float]:
        """Select delta-band strikes per CMP S4 (F9-M-05).

        BUY-side eligibility is the closed delta band |delta| in
        [0.50, 0.60] with OI confirmation (fail-closed on zero OI and on
        missing delta). The closest-to-ATM eligible call and put strike
        seed the selection (delta-neutral legs); remaining eligible
        strikes fill up to ``max_strikes`` nearest-first. Output is
        deduplicated -- the previous implementation appended the ATM call
        and put strikes unconditionally and produced ``[K, K]`` for the
        standard ATM pair.
        """
        if not option_chain:
            return []

        eligible = [
            opt
            for opt in option_chain
            if delta_in_buy_band(opt.delta) and opt.open_interest >= MIN_OI_CONFIRMATION
        ]
        if not eligible:
            return []

        selected: list[float] = []

        # Delta-neutral seed legs: nearest eligible call and put to ATM.
        calls = [opt for opt in eligible if opt.option_type == OptionType.CALL]
        puts = [opt for opt in eligible if opt.option_type == OptionType.PUT]
        calls.sort(key=lambda x: abs(x.strike_price - underlying_price))
        puts.sort(key=lambda x: abs(x.strike_price - underlying_price))
        for opt in (calls[0] if calls else None, puts[0] if puts else None):
            if opt is not None and opt.strike_price not in selected:
                selected.append(opt.strike_price)

        # Fill remaining slots nearest-ATM first among eligible strikes.
        for opt in sorted(
            eligible, key=lambda x: abs(x.strike_price - underlying_price)
        ):
            if len(selected) >= max_strikes:
                break
            if opt.strike_price not in selected:
                selected.append(opt.strike_price)

        return selected[:max_strikes]

    async def build_sell_two_sigma_band(
        self,
        underlying_price: float,
        historical_data: list[HistoricalData],
        holding_days: float = 1.0,
    ) -> tuple[float, float] | None:
        """Build the CMP S4 SELL-side two-sigma band from price history.

        Returns None when the history cannot support a unit-consistent
        sigma estimate (too short, mixed intervals, unparseable labels) --
        fail-closed, never a fabricated band.
        """
        estimate = estimate_bar_sigma(historical_data)
        if estimate is None:
            return None
        bar_sigma, bar_seconds = estimate
        return two_sigma_sell_band(
            underlying_price, bar_sigma, bar_seconds, holding_days
        )

    async def _select_oi_based_strikes(
        self,
        underlying_price: float,
        option_chain: list[OptionContract],
        width: int,
        max_strikes: int,
    ) -> list[float]:
        """Select strikes based on open interest analysis."""
        if not option_chain:
            return []

        # Sort by open interest (descending)
        sorted_by_oi = sorted(option_chain, key=lambda x: x.open_interest, reverse=True)

        selected: list[float] = []
        for opt in sorted_by_oi:
            if len(selected) >= max_strikes:
                break
            if opt.strike_price not in selected:
                selected.append(opt.strike_price)

        return selected

    async def calculate_optimal_strike_spacing(
        self, underlying_price: float, implied_volatility: float, days_to_expiry: int
    ) -> float:
        """Calculate optimal strike spacing based on market conditions.

        Uses Black-Scholes framework to determine appropriate strike spacing
        based on expected price movement.

        Args:
            underlying_price: Current price of underlying
            implied_volatility: Annualized implied volatility
            days_to_expiry: Days until option expiry

        Returns:
            Optimal strike spacing
        """
        if days_to_expiry <= 0:
            return 0.0

        # Convert to years
        time_to_expiry = days_to_expiry / 252.0  # Trading days

        # Calculate expected price movement (1 standard deviation)
        expected_move = float(
            underlying_price * implied_volatility * np.sqrt(time_to_expiry)
        )

        # Use 0.5 standard deviations as optimal spacing
        return max(5.0, expected_move * 0.5)  # Minimum 5 point spacing

    async def analyze_strike_efficiency(
        self,
        selected_strikes: list[float],
        option_chain: list[OptionContract],
        underlying_price: float,
    ) -> dict[str, Any]:
        """Analyze efficiency of selected strikes.

        Args:
            selected_strikes: List of selected strike prices
            option_chain: Full option chain for comparison
            underlying_price: Current underlying price

        Returns:
            Efficiency analysis metrics
        """
        if not selected_strikes or not option_chain:
            return {
                "coverage_score": 0.0,
                "liquidity_score": 0.0,
                "delta_coverage": 0.0,
                "atm_proximity": 0.0,
            }

        # Calculate coverage score
        all_strikes = {opt.strike_price for opt in option_chain}
        coverage = len(set(selected_strikes) & all_strikes) / len(selected_strikes)

        # Calculate liquidity score (average OI of selected strikes)
        selected_contracts = [
            opt for opt in option_chain if opt.strike_price in selected_strikes
        ]
        avg_oi = (
            sum(opt.open_interest for opt in selected_contracts)
            / len(selected_contracts)
            if selected_contracts
            else 0
        )

        # Calculate delta coverage
        deltas = [abs(opt.delta) for opt in selected_contracts if opt.delta is not None]
        delta_range = max(deltas) - min(deltas) if deltas else 0

        # Calculate ATM proximity
        atm_distances = [abs(strike - underlying_price) for strike in selected_strikes]
        avg_atm_distance = (
            sum(atm_distances) / len(atm_distances) if atm_distances else 0
        )
        atm_proximity = 1.0 / (1.0 + avg_atm_distance) if avg_atm_distance > 0 else 1.0

        return {
            "coverage_score": float(coverage),
            "liquidity_score": float(avg_oi),
            "delta_coverage": float(delta_range),
            "atm_proximity": float(atm_proximity),
            "selected_count": len(selected_strikes),
            "available_count": len(all_strikes),
        }

    def clear_cache(self) -> None:
        """Clear the strike selection cache."""
        with self._cache_lock:
            self._cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            hit_rate = self._cache_hits / (self._cache_hits + self._cache_misses + 1e-6)
            return {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "current_size": len(self._cache),
                "max_size": self._cache.maxsize,
                "hit_rate": hit_rate,
            }

    def cleanup(self) -> None:
        """Clean up resources and clear cache."""
        with self._cache_lock:
            self._cache.clear()
            self._initialized = False


# Module-level singleton instance
strike_selector = StrikeSelectionEngine()


# Async wrapper for module-level access
async def select_strikes(
    underlying_price: float,
    option_chain: list[OptionContract],
    strategy: str = "atm_straddle",
    width: int = 1,
    max_strikes: int = 5,
) -> list[float]:
    """Async wrapper for strike selection."""
    return await strike_selector.select_strikes(
        underlying_price, option_chain, strategy, width, max_strikes
    )
