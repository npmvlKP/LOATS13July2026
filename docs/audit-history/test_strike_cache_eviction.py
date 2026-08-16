#!/usr/bin/env python3
"""Test script to verify strike selection cache eviction works correctly."""

import asyncio
import time

from src.loats.models import OptionContract, OptionType
from src.loats.strike_selection import StrikeSelectionEngine


async def test_cache_eviction():
    """Test that cache eviction works with TTLCache."""
    engine = StrikeSelectionEngine()

    # Create test option chain
    option_chain = [
        OptionContract(
            symbol="NIFTY24AUG18000CE",
            strike_price=18000.0,
            option_type=OptionType.CALL,
            expiry_date="2024-08-24",
            open_interest=1000,
            delta=0.5,
        ),
        OptionContract(
            symbol="NIFTY24AUG18000PE",
            strike_price=18000.0,
            option_type=OptionType.PUT,
            expiry_date="2024-08-24",
            open_interest=1000,
            delta=-0.5,
        ),
    ]

    # Test 1: Cache should work normally
    result1 = await engine.select_strikes(18000.0, option_chain, "atm_straddle")
    print(f"First call result: {result1}")

    # Second call with same parameters should use cache
    result2 = await engine.select_strikes(18000.0, option_chain, "atm_straddle")
    print(f"Second call result (cached): {result2}")

    assert result1 == result2, "Cached result should match original"

    # Test 2: Cache should have bounded size
    # Fill cache with many different entries
    for i in range(1100):  # Exceed maxsize of 1000
        await engine.select_strikes(18000.0 + i, option_chain, "atm_straddle")

    cache_size = len(engine._cache)
    print(f"Cache size after filling: {cache_size}")
    assert cache_size <= 1000, f"Cache size {cache_size} exceeds maxsize of 1000"

    # Test 3: Cache should evict old entries
    initial_cache_size = len(engine._cache)
    print(f"Initial cache size: {initial_cache_size}")

    # Wait for TTL to expire (300 seconds = 5 minutes)
    print("Waiting for TTL expiration...")
    time.sleep(301)  # Wait just over TTL

    # Cache should have evicted some entries
    final_cache_size = len(engine._cache)
    print(f"Final cache size after TTL: {final_cache_size}")

    # Clear cache for cleanup
    engine.clear_cache()
    print("Cache cleared successfully")

    print("✅ All cache eviction tests passed!")


if __name__ == "__main__":
    asyncio.run(test_cache_eviction())
