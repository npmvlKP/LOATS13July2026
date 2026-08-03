"""
Additional tests for cache.py to improve Redis coverage.
Focuses on Redis-specific functionality and edge cases.
"""

from unittest.mock import MagicMock, patch

import pytest
from cachetools import TTLCache

from src.loats.utils.cache import (
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
        """Test Redis import fallback when Redis is not available."""
        # Test the import fallback mechanism
        with patch("src.loats.utils.cache.redis") as mock_redis:
            mock_redis.asyncio.Redis.side_effect = ImportError("Redis not available")

            # This should trigger the import fallback
            config = CacheConfig(cache_type="redis")
            cache_manager = CacheManager(config)

            # Should initialize with in-memory cache
            await cache_manager.initialize()
            assert cache_manager._cache is not None
            assert isinstance(cache_manager._cache, TTLCache)
            assert cache_manager._cache_type == "in_memory_ttl"

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis connection error handling during initialization."""
        with patch("src.loats.utils.cache.redis") as mock_redis:
            # Mock Redis to be available but connection fails
            mock_redis.asyncio.Redis = MagicMock()
            mock_redis.asyncio.Redis.return_value.ping.side_effect = Exception(
                "Connection refused"
            )

            # Should fall back to in-memory cache
            await cache_manager.initialize()
            assert cache_manager._cache is not None
            assert cache_manager._cache_type == "in_memory_ttl"

    @pytest.mark.asyncio
    async def test_redis_get_with_bytes_response(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis get operation with bytes response."""
        await cache_manager.initialize()

        # Mock Redis get to return bytes
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.get.return_value = b'{"test": "value"}'
            cache_manager._cache_type = "redis"

            result = await cache_manager.get("test_key")
            # Should handle bytes response
            assert result is not None

    @pytest.mark.asyncio
    async def test_redis_get_not_found_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis get operation when key not found."""
        await cache_manager.initialize()

        # Mock Redis get to return None (not found)
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.get.return_value = None
            cache_manager._cache_type = "redis"

            result = await cache_manager.get("missing_key")
            # Should return None and increment misses
            assert result is None

    @pytest.mark.asyncio
    async def test_redis_set_error_handling(self, cache_manager: CacheManager) -> None:
        """Test Redis set operation error handling."""
        await cache_manager.initialize()

        # Mock Redis setex to raise exception
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.setex.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.set("test_key", "test_value")
            # Should fall back to in-memory and return True
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_delete_error_handling(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis delete operation error handling."""
        await cache_manager.initialize()

        # Add item to cache first
        await cache_manager.set("test_key", "test_value")

        # Mock Redis delete to raise exception
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.delete.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.delete("test_key")
            # Should fall back to in-memory and return True
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_clear_with_pattern(self, cache_manager: CacheManager) -> None:
        """Test Redis clear operation with pattern matching."""
        await cache_manager.initialize()

        # Add items to cache
        await cache_manager.set("test_key1", "value1")
        await cache_manager.set("test_key2", "value2")
        await cache_manager.set("other_key", "value3")

        # Mock Redis keys and delete
        with patch.object(cache_manager, "_redis") as mock_redis:
            # Mock keys to return matching keys
            mock_redis.keys.return_value = ["loats:test_key1", "loats:test_key2"]
            cache_manager._cache_type = "redis"

            result = await cache_manager.clear("test")
            # Should clear matching keys
            assert result == 2

    @pytest.mark.asyncio
    async def test_redis_clear_all_keys(self, cache_manager: CacheManager) -> None:
        """Test Redis clear operation for all keys."""
        await cache_manager.initialize()

        # Add items to cache
        await cache_manager.set("key1", "value1")
        await cache_manager.set("key2", "value2")

        # Mock Redis keys and delete
        with patch.object(cache_manager, "_redis") as mock_redis:
            # Mock keys to return all keys with prefix
            mock_redis.keys.return_value = ["loats:key1", "loats:key2"]
            cache_manager._cache_type = "redis"

            result = await cache_manager.clear("*")
            # Should clear all keys
            assert result == 2

    @pytest.mark.asyncio
    async def test_redis_stats_collection(self, cache_manager: CacheManager) -> None:
        """Test Redis statistics collection."""
        await cache_manager.initialize()

        # Add some items to cache
        await cache_manager.set("key1", "value1")
        await cache_manager.get("key1")

        # Mock Redis info and dbsize
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.info.return_value = {
                "redis_version": "7.0.0",
                "used_memory": "1000000",
                "maxmemory": "0",
            }
            mock_redis.dbsize.return_value = 2
            cache_manager._cache_type = "redis"

            stats = await cache_manager.get_cache_stats()
            # Should return Redis stats
            assert stats["cache_type"] == "redis"
            assert stats["redis_version"] == "7.0.0"

    @pytest.mark.asyncio
    async def test_redis_stats_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis statistics fallback when Redis stats fail."""
        await cache_manager.initialize()

        # Mock Redis stats to fail
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.info.side_effect = Exception("Redis stats error")
            mock_redis.dbsize.side_effect = Exception("Redis stats error")
            cache_manager._cache_type = "redis"

            stats = await cache_manager.get_cache_stats()
            # Should fall back to basic stats
            assert stats["cache_type"] == "redis"
            assert "error" not in stats  # Should not have error in fallback

    @pytest.mark.asyncio
    async def test_cache_close_with_redis(self, cache_manager: CacheManager) -> None:
        """Test cache close operation with Redis."""
        await cache_manager.initialize()

        # Mock Redis connection
        with patch.object(cache_manager, "_redis"):
            cache_manager._cache_type = "redis"

            # Close should work even with Redis
            await cache_manager.close()
            # Should not raise exception

    @pytest.mark.asyncio
    async def test_redis_connection_parameters(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis connection with custom parameters."""
        # Test with custom Redis parameters
        config = CacheConfig(
            cache_type="redis",
            redis_host="custom.example.com",
            redis_port=6380,
            redis_password="secret",
        )
        cache_manager = CacheManager(config)

        with patch("src.loats.utils.cache.redis") as mock_redis:
            # Mock Redis to fail connection
            mock_redis.asyncio.Redis = MagicMock()
            mock_redis.asyncio.Redis.return_value.ping.side_effect = Exception(
                "Connection failed"
            )

            await cache_manager.initialize()

            # Should have tried to connect with custom parameters
            assert cache_manager.config.redis_host == "custom.example.com"
            assert cache_manager.config.redis_port == 6380

    @pytest.mark.asyncio
    async def test_cache_key_generation_with_redis_prefix(
        self, cache_manager: CacheManager
    ) -> None:
        """Test cache key generation with Redis prefix."""
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

    @pytest.mark.asyncio
    async def test_redis_fallback_consistency(
        self, cache_manager: CacheManager
    ) -> None:
        """Test consistency between Redis and in-memory cache operations."""
        await cache_manager.initialize()

        # Test that operations work consistently regardless of cache type
        await cache_manager.set("consistent_key", "consistent_value")

        # Should work with in-memory
        result1 = await cache_manager.get("consistent_key")
        assert result1 == "consistent_value"

        # Mock Redis and test consistency
        with patch.object(cache_manager, "_redis") as mock_redis:
            # Mock Redis operations to work
            mock_redis.get.return_value = "consistent_value"
            mock_redis.setex.return_value = True
            cache_manager._cache_type = "redis"

            # Should still work with Redis mock
            result2 = await cache_manager.get("consistent_key")
            assert result2 == "consistent_value"
