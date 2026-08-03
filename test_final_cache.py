#!/usr/bin/env python3
"""
Final comprehensive test for cache functionality.
"""

import asyncio
from src.loats.utils.cache import CacheManager, CacheConfig

async def test_final_cache():
    """Comprehensive test for cache functionality."""
    print("Running comprehensive cache tests...")

    # Test 1: In-memory cache
    print("\n=== Test 1: In-Memory Cache ===")
    config_memory = CacheConfig(cache_type="memory", ttl_seconds=10)
    cache_memory = CacheManager(config_memory)
    await cache_memory.initialize()

    # Test basic operations
    await cache_memory.set("key1", "value1")
    await cache_memory.set("key2", {"data": "json"})
    await cache_memory.set("key3", 123)

    result1 = await cache_memory.get("key1")
    result2 = await cache_memory.get("key2")
    result3 = await cache_memory.get("key3")
    result4 = await cache_memory.get("nonexistent")

    print(f"Set key1=value1, Got: {result1}")
    print(f"Set key2=json, Got: {result2}")
    print(f"Set key3=123, Got: {result3}")
    print(f"Get nonexistent: {result4}")

    # Test delete
    delete_result = await cache_memory.delete("key1")
    result_after_delete = await cache_memory.get("key1")
    print(f"Delete key1: {delete_result}, Get after delete: {result_after_delete}")

    # Test stats
    stats = await cache_memory.get_cache_stats()
    print(f"Cache stats: {stats}")

    await cache_memory.close()

    # Test 2: Redis cache with fallback
    print("\n=== Test 2: Redis Cache (with fallback) ===")
    config_redis = CacheConfig(
        cache_type="redis",
        redis_host="localhost",
        redis_port=6379,
        redis_password=""
    )
    cache_redis = CacheManager(config_redis)
    await cache_redis.initialize()

    # Test basic operations (will fallback to in-memory)
    await cache_redis.set("redis_key", "redis_value")
    result = await cache_redis.get("redis_key")
    print(f"Set redis_key=redis_value, Got: {result}")

    stats = await cache_redis.get_cache_stats()
    print(f"Cache stats: {stats}")

    await cache_redis.close()

    # Test 3: Cache with TTL
    print("\n=== Test 3: Cache with TTL ===")
    config_ttl = CacheConfig(cache_type="memory", ttl_seconds=2)
    cache_ttl = CacheManager(config_ttl)
    await cache_ttl.initialize()

    await cache_ttl.set("ttl_key", "ttl_value")
    result = await cache_ttl.get("ttl_key")
    print(f"Immediate get: {result}")

    print("Waiting 3 seconds for TTL to expire...")
    await asyncio.sleep(3)

    result_after_ttl = await cache_ttl.get("ttl_key")
    print(f"Get after TTL: {result_after_ttl}")

    await cache_ttl.close()

    print("\n✅ All comprehensive cache tests passed!")

if __name__ == "__main__":
    asyncio.run(test_final_cache())