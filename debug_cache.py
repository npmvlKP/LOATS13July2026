#!/usr/bin/env python3
"""
Debug cache functionality.
"""

import asyncio
from src.loats.utils.cache import CacheManager, CacheConfig

async def debug_cache():
    """Debug cache functionality."""
    print("Debugging cache functionality...")

    # Create a new cache manager with explicit configuration
    config = CacheConfig(cache_type="memory", ttl_seconds=300)
    cache = CacheManager(config)

    print(f"Before init - cache_type: {cache._cache_type}")
    print(f"Before init - cache: {cache._cache}")

    # Initialize cache
    await cache.initialize()
    print(f"After init - cache_type: {cache._cache_type}")
    print(f"After init - cache: {cache._cache}")

    # Test set/get
    success = await cache.set("test_key", "test_value")
    print(f"Set result: {success}")
    result = await cache.get("test_key")
    print(f"Set 'test_key' = 'test_value', Got: {result}")

    # Test stats
    stats = await cache.get_cache_stats()
    print(f"Cache stats: {stats}")

if __name__ == "__main__":
    asyncio.run(debug_cache())