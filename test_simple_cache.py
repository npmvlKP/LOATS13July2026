#!/usr/bin/env python3
"""
Simple test script for cache functionality.
"""

import asyncio

from src.loats.utils.cache import cache_manager, close_cache, initialize_cache


async def test_simple_cache():
    """Test basic cache functionality."""
    print("Testing basic cache functionality...")

    # Initialize cache
    await initialize_cache()
    print("Cache initialized")

    # Test set/get
    success = await cache_manager.set("test_key", "test_value")
    print(f"Set result: {success}")
    result = await cache_manager.get("test_key")
    print(f"Set 'test_key' = 'test_value', Got: {result}")

    # Test stats
    stats = await cache_manager.get_cache_stats()
    print(f"Cache stats: {stats}")

    # Test delete
    delete_result = await cache_manager.delete("test_key")
    print(f"Delete result: {delete_result}")
    result = await cache_manager.get("test_key")
    print(f"After delete, Got: {result}")

    # Close cache
    await close_cache()
    print("Cache closed")

    print("\nAll basic cache tests passed!")

if __name__ == "__main__":
    asyncio.run(test_simple_cache())
