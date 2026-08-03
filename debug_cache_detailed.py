#!/usr/bin/env python3
"""
Detailed debug cache functionality.
"""

import asyncio
from src.loats.utils.cache import CacheManager, CacheConfig

async def debug_cache_detailed():
    """Debug cache functionality in detail."""
    print("Debugging cache functionality in detail...")

    # Create a new cache manager with explicit configuration
    config = CacheConfig(cache_type="memory", ttl_seconds=300)
    cache = CacheManager(config)

    # Initialize cache
    await cache.initialize()
    print(f"After init - cache_type: {cache._cache_type}")
    print(f"After init - cache: {cache._cache}")
    print(f"After init - cache is not None: {cache._cache is not None}")

    # Debug set method step by step
    key = "test_key"
    value = "test_value"
    cache_key = cache._get_cache_key(key)
    print(f"Cache key: {cache_key}")

    # Test the cache directly
    print(f"Before set - cache contents: {dict(cache._cache)}")
    cache._cache[cache_key] = value
    print(f"After direct set - cache contents: {dict(cache._cache)}")
    result = cache._cache.get(cache_key)
    print(f"Direct get result: {result}")

    # Now test through the method
    success = await cache.set(key, value)
    print(f"Set method result: {success}")
    print(f"After set method - cache contents: {dict(cache._cache)}")
    result = await cache.get(key)
    print(f"Get method result: {result}")

if __name__ == "__main__":
    asyncio.run(debug_cache_detailed())