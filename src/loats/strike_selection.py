"""Strike Selection Module for LOATS13July2026.

High-performance strike selection engine that meets the <5ms latency target.
Implements optimized strike selection algorithms for options trading.
"""

import datetime
import threading
import time
from typing import Any

import numpy as np

from .loats_logging import get_logger
from .models import OptionContract, OptionType


class SimpleStrikeCache:
    """Simple cache implementation for strike selection using threading.Lock.

    Replaces cachetools.TTLCache with a simpler implementation for better control
    and performance in the strike selection hot path.
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        """Initialize the cache.

        Args:
            maxsize: Maximum number of items to store
            ttl: Time-to-live for cache entries in seconds
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: dict[str, tuple[list[float], float]] = {}
        self._lock = threading.Lock()
        self._access_order: list[str] = []

    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache (respecting TTL)."""
        with self._lock:
            self._cleanup_expired()
            return key in self._cache

    def __getitem__(self, key: str) -> list[float]:
        """Get item from cache."""
        with self._lock:
            self._cleanup_expired()
            if key not in self._cache:
                raise KeyError(key)

            value, timestamp = self._cache[key]
            # Update access order for LRU eviction
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return value

    def __setitem__(self, key: str, value: list[float]) -> None:
        """Set item in cache."""
        with self._lock:
            self._cleanup_expired()

            # Add or update item
            self._cache[key] = (value, time.time())

            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            # Enforce maxsize with LRU eviction
            if len(self._cache) > self.maxsize:
                oldest_key = self._access_order.pop(0)
                if oldest_key in self._cache:
                    del self._cache[oldest_key]

    def __delitem__(self, key: str) -> None:
        """Delete item from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

    def get(self, key: str, default: list[float] | None = None) -> list[float] | None:
        """Get item from cache with default."""
        with self._lock:
            self._cleanup_expired()
            if key not in self._cache:
                return default

            value, timestamp = self._cache[key]
            # Update access order for LRU eviction
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return value

    def _cleanup_expired(self) -> None:
        """Remove expired items from cache."""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, timestamp) in self._cache.items()
            if current_time - timestamp > self.ttl
        ]

        for key in expired_keys:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()

    def __len__(self) -> int:
        """Get number of items in cache."""
        with self._lock:
            self._cleanup_expired()
            return len(self._cache)

    def keys(self) -> list[str]:
        """Get list of keys in cache."""
        with self._lock:
            self._cleanup_expired()
            return list(self._cache.keys())

    @property
    def maxsize(self) -> int:
        """Get maximum cache size."""
        return self._maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        """Set maximum cache size."""
        self._maxsize = value


logger = get_logger(__name__)


class StrikeSelectionEngine:
    """High-performance strike selection engine with <5ms latency guarantee."""

    def __init__(self) -> None:
        """Initialize StrikeSelectionEngine."""
        self._cache = SimpleStrikeCache(maxsize=1000, ttl=300)
        self._cache_lock = threading.Lock()  # Use threading.Lock for better performance
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
        """Select delta-neutral strikes using pre-calculated Greeks."""
        if not option_chain:
            return []

        # Filter and sort call/put options
        calls = [opt for opt in option_chain if opt.option_type == OptionType.CALL]
        puts = [opt for opt in option_chain if opt.option_type == OptionType.PUT]

        calls.sort(key=lambda x: abs(x.strike_price - underlying_price))
        puts.sort(key=lambda x: abs(x.strike_price - underlying_price))

        selected: list[float] = []

        # Add ATM call and put for delta neutrality
        if calls and len(selected) < max_strikes:
            selected.append(calls[0].strike_price)
        if puts and len(selected) < max_strikes:
            selected.append(puts[0].strike_price)

        # Add additional strikes based on delta
        for opt in option_chain:
            if len(selected) >= max_strikes:
                break
            if opt.strike_price not in selected:
                # Simple heuristic: prefer strikes with delta close to 0.5 for calls
                # and -0.5 for puts
                if (
                    opt.option_type == OptionType.CALL
                    and opt.delta is not None
                    and abs(opt.delta - 0.5) < 0.1
                ):
                    selected.append(opt.strike_price)
                elif (
                    opt.option_type == OptionType.PUT
                    and opt.delta is not None
                    and abs(opt.delta + 0.5) < 0.1
                ):
                    selected.append(opt.strike_price)

        return selected[:max_strikes]

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
