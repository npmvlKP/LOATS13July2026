"""
Additional tests for cache.py to improve Redis coverage.
Focuses on Redis-specific functionality and edge cases.
"""

import pytest
from cachetools import TTLCache

from loats.utils.cache import (
    CacheConfig,
    CacheManager,
)


class TestCacheRedisCoverage:
    """Additional tests for Redis-specific cache functionality."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig(cache_type="redis")
        return CacheManager(config)

    @pytest.mark.asyncio
    async def test_redis_import_fallback(self) -> None:
        """Test in-memory cache initialization (Redis removed in LITE edition)."""
        # For LITE edition, always use in-memory cache regardless of Redis config
        config = CacheConfig(cache_type="redis")
        cache_manager = CacheManager(config)

        # Should initialize with in-memory cache
        await cache_manager.initialize()
        assert cache_manager._cache is not None
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test in-memory cache initialization (Redis removed in LITE edition)."""
        # For LITE edition, always use in-memory cache regardless of Redis config
        await cache_manager.initialize()
        assert cache_manager._cache is not None
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_get_with_bytes_response(
        self, cache_manager: CacheManager
    ) -> None:
        """Test in-memory get operation (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Test in-memory get operation
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "cached_value"

        result = await cache_manager.get("test_key")
        assert result == "cached_value"
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_get_not_found_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test in-memory get operation when key not found (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Test in-memory get operation for missing key
        result = await cache_manager.get("missing_key")
        # Should return None and increment misses
        assert result is None
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_set_error_handling(self, cache_manager: CacheManager) -> None:
        """Test in-memory set operation (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        result = await cache_manager.set("test_key", "test_value")
        # Should work with in-memory cache
        assert result is True
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_delete_error_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test in-memory delete operation (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Add item to cache first
        await cache_manager.set("test_key", "test_value")

        result = await cache_manager.delete("test_key")
        # Should work with in-memory cache
        assert result is True
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_clear_with_pattern(self, cache_manager: CacheManager) -> None:
        """Test in-memory clear operation with pattern matching (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Add items to cache
        await cache_manager.set("test_key1", "value1")
        await cache_manager.set("test_key2", "value2")
        await cache_manager.set("other_key", "value3")

        result = await cache_manager.clear("test")
        # Should clear matching keys
        assert result == 2
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_clear_all_keys(self, cache_manager: CacheManager) -> None:
        """Test in-memory clear operation for all keys (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Add items to cache
        await cache_manager.set("key1", "value1")
        await cache_manager.set("key2", "value2")

        result = await cache_manager.clear("*")
        # Should clear all keys
        assert result == 2
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_stats_collection(self, cache_manager: CacheManager) -> None:
        """Test in-memory statistics collection (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Add some items to cache
        await cache_manager.set("key1", "value1")
        await cache_manager.get("key1")

        stats = await cache_manager.get_cache_stats()
        # Should return in-memory stats
        assert stats["cache_type"] == "lightweight_in_memory"
        assert stats["current_size"] == 1
        assert stats["hits"] == 1
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_stats_fallback(self, cache_manager: CacheManager) -> None:
        """Test in-memory statistics (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        stats = await cache_manager.get_cache_stats()
        # Should return in-memory stats
        assert stats["cache_type"] == "lightweight_in_memory"
        assert stats["enabled"] is True
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_cache_close_with_redis(self, cache_manager: CacheManager) -> None:
        """Test cache close operation (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Close should work with in-memory cache
        await cache_manager.close()
        # Should not raise exception
        assert cache_manager._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_connection_parameters(
        self, cache_manager: CacheManager
    ) -> None:
        """Test that Redis parameters are not supported in LITE edition."""
        # Test that Redis parameters are not accepted in LITE edition
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            CacheConfig(
                cache_type="redis",
                redis_host="custom.example.com",
                redis_port=6380,
                redis_password="secret",
            )

        # Test that only in-memory cache is supported
        config = CacheConfig(cache_type="memory")
        cache_manager = CacheManager(config)

        await cache_manager.initialize()

        # Should use in-memory cache only
        assert cache_manager._cache_type == "in_memory_simple_ttl"
        assert config.cache_type == "memory"

    @pytest.mark.asyncio
    async def test_cache_key_generation_with_redis_prefix(
        self, cache_manager: CacheManager
    ) -> None:
        """Test cache key generation (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Test key generation
        cache_key = cache_manager._get_cache_key("test_key")
        assert cache_key == "loats:test_key"

        # Test with custom prefix
        config = CacheConfig(prefix="custom")
        cache_manager_custom = CacheManager(config)
        await cache_manager_custom.initialize()

        cache_key_custom = cache_manager_custom._get_cache_key("test_key")
        assert cache_key_custom == "custom:test_key"
        assert cache_manager_custom._cache_type == "in_memory_simple_ttl"

    @pytest.mark.asyncio
    async def test_redis_fallback_consistency(
        self, cache_manager: CacheManager
    ) -> None:
        """Test in-memory cache consistency (Redis removed in LITE edition)."""
        await cache_manager.initialize()

        # Test that operations work consistently with in-memory cache
        await cache_manager.set("consistent_key", "consistent_value")

        # Should work with in-memory
        result1 = await cache_manager.get("consistent_key")
        assert result1 == "consistent_value"

        # Verify cache type is in-memory
        assert cache_manager._cache_type == "in_memory_simple_ttl"
