#!/usr/bin/env python3
"""
Test script for Redis cache functionality.
"""

import asyncio
from src.loats.utils.cache import CacheManager, CacheConfig

async def test_redis_cache():
    """Test Redis cache with fallback to in-memory."""
    print("Testing Redis cache functionality...")

    # Test 1: In-memory cache (default)
    print("\n1. Testing in-memory cache...")
    config_memory = CacheConfig(cache_type="memory")
    cache_memory = CacheManager(config_memory)
    await cache_memory.initialize()

    # Test set/get
    await cache_memory.set("test_key", "test_value")
    result = await cache_memory.get("test_key")
    print(f"   Set 'test_key' = 'test_value', Got: {result}")

    # Test stats
    stats = await cache_memory.get_cache_stats()
    print(f"   Cache stats: {stats}")

    await cache_memory.close()

    # Test 2: Redis cache (will fallback to in-memory if Redis not available)
    print("\n2. Testing Redis cache (with fallback)...")
    config_redis = CacheConfig(
        cache_type="redis",
        redis_host="localhost",
        redis_port=6379,
        redis_password=""
    )
    cache_redis = CacheManager(config_redis)
    await cache_redis.initialize()

    # Test set/get
    await cache_redis.set("redis_key", "redis_value")
    result = await cache_redis.get("redis_key")
    print(f"   Set 'redis_key' = 'redis_value', Got: {result}")

    # Test stats
    stats = await cache_redis.get_cache_stats()
    print(f"   Cache stats: {stats}")

    await cache_redis.close()

    print("\n✅ All cache tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_redis_cache())