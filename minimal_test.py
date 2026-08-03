#!/usr/bin/env python3
"""
Minimal test to isolate cache issue.
"""

import asyncio
from src.loats.utils.cache import CacheManager, CacheConfig

async def minimal_test():
    """Minimal test of cache functionality."""
    print("Running minimal cache test...")

    # Create fresh cache instance
    config = CacheConfig(cache_type="memory")
    cache = CacheManager(config)

    # Initialize
    await cache.initialize()
    print(f"Cache initialized: type={cache._cache_type}, cache={cache._cache is not None}")

    # Test direct cache access
    cache_key = "loats:test"
    cache._cache[cache_key] = "direct_value"
    direct_result = cache._cache.get(cache_key)
    print(f"Direct access: {direct_result}")

    # Test through methods
    set_result = await cache.set("test", "method_value")
    get_result = await cache.get("test")
    print(f"Method set: {set_result}, get: {get_result}")

    # Check cache contents
    print(f"Cache contents: {dict(cache._cache)}")

if __name__ == "__main__":
    asyncio.run(minimal_test())