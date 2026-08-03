#!/usr/bin/env python3
"""
Debug cache state issue.
"""

import asyncio
from src.loats.utils.cache import cache_manager, initialize_cache, close_cache

async def debug_cache_state():
    """Debug cache state issue."""
    print("Debugging cache state...")

    # Check initial state
    print(f"Initial cache_type: {cache_manager._cache_type}")
    print(f"Initial cache: {cache_manager._cache}")

    # Initialize
    await initialize_cache()
    print(f"After init cache_type: {cache_manager._cache_type}")
    print(f"After init cache: {cache_manager._cache}")

    # Test set with debug
    print("\nTesting set operation...")
    cache_key = "loats:debug_key"
    print(f"Cache key: {cache_key}")

    # Try direct cache access first
    print(f"Before direct set - cache contents: {dict(cache_manager._cache)}")
    cache_manager._cache[cache_key] = "debug_value"
    print(f"After direct set - cache contents: {dict(cache_manager._cache)}")
    direct_result = cache_manager._cache.get(cache_key)
    print(f"Direct get result: {direct_result}")

    # Now try through method
    print(f"\nBefore method set - cache contents: {dict(cache_manager._cache)}")
    success = await cache_manager.set("debug_key", "debug_value")
    print(f"Set method result: {success}")
    print(f"After method set - cache contents: {dict(cache_manager._cache)}")
    method_result = await cache_manager.get("debug_key")
    print(f"Method get result: {method_result}")

    # Check if cache is being cleared somewhere
    print(f"\nFinal cache contents: {dict(cache_manager._cache)}")

if __name__ == "__main__":
    asyncio.run(debug_cache_state())