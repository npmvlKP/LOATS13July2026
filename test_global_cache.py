#!/usr/bin/env python3
"""
Test global cache manager functionality.
"""

import asyncio

from src.loats.utils.cache import cache_manager, close_cache, initialize_cache


async def test_global_cache():
    """Test global cache manager functionality."""
    print("Testing global cache manager...")

    # Initialize global cache
    await initialize_cache()
    print("Global cache initialized")

    # Check cache state
    print(f"Cache type: {cache_manager._cache_type}")
    print(f"Cache object: {cache_manager._cache}")
    print(f"Cache is not None: {cache_manager._cache is not None}")

    # Test direct cache access
    cache_key = "loats:test_key"
    cache_manager._cache[cache_key] = "test_value"
    result = cache_manager._cache.get(cache_key)
    print(f"Direct cache access: {result}")

    # Test through methods
    success = await cache_manager.set("test_key", "test_value")
    print(f"Set method result: {success}")
    result = await cache_manager.get("test_key")
    print(f"Get method result: {result}")

    # Test stats
    stats = await cache_manager.get_cache_stats()
    print(f"Cache stats: {stats}")

    # Close cache
    await close_cache()
    print("Global cache closed")

if __name__ == "__main__":
    asyncio.run(test_global_cache())
