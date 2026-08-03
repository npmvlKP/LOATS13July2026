"""
Additional unit tests for cache utility module to increase coverage.
Tests Redis functionality, error handling, and edge cases.
"""

from unittest.mock import MagicMock, patch

import pytest
from cachetools import TTLCache
from pydantic import BaseModel

from src.loats.utils.cache import (
    CacheConfig,
    CacheManager,
    cache_manager,
    close_cache,
    dict_to_cache_key,
    initialize_cache,
    model_to_cache_key,
)


class TestCacheConfigAdditional:
    """Additional tests for CacheConfig class."""

    def test_config_with_redis_settings(self) -> None:
        """Test cache configuration with Redis settings."""
        config = CacheConfig(
            cache_type="redis",
            redis_host="redis.example.com",
            redis_port=6380,
            redis_password="secret",
        )
        assert config.cache_type == "redis"
        assert config.redis_host == "redis.example.com"
        assert config.redis_port == 6380
        assert config.redis_password == "secret"


class TestCacheManagerAdditional:
    """Additional tests for CacheManager class."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig()
        return CacheManager(config)

    @pytest.mark.asyncio
    async def test_initialize_redis_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis initialization with fallback to in-memory."""
        # Mock Redis to be unavailable
        with patch("src.loats.utils.cache.redis") as mock_redis:
            mock_redis.asyncio.Redis.side_effect = ImportError("Redis not available")

            await cache_manager.initialize()
            assert cache_manager._cache is not None
            assert isinstance(cache_manager._cache, TTLCache)
            assert cache_manager._cache_type == "in_memory_ttl"

    @pytest.mark.asyncio
    async def test_initialize_redis_connection_error(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis connection error handling."""
        # Mock Redis to raise connection error
        with patch("src.loats.utils.cache.redis") as mock_redis:
            mock_redis.asyncio.Redis = MagicMock()
            mock_redis.asyncio.Redis.return_value.ping.side_effect = Exception(
                "Connection failed"
            )

            await cache_manager.initialize()
            assert cache_manager._cache is not None
            assert isinstance(cache_manager._cache, TTLCache)
            assert cache_manager._cache_type == "in_memory_ttl"

    @pytest.mark.asyncio
    async def test_get_redis_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis get operation with fallback to in-memory."""
        await cache_manager.initialize()

        # Add item to in-memory cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "cached_value"

        # Mock Redis to raise error
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.get.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.get("test_key")
            assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_set_redis_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis set operation with fallback to in-memory."""
        await cache_manager.initialize()

        # Mock Redis to raise error
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.setex.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.set("test_key", "test_value")
            assert result is True

            # Verify it was stored in in-memory cache
            cache_key = cache_manager._get_cache_key("test_key")
            assert cache_manager._cache[cache_key] == "test_value"

    @pytest.mark.asyncio
    async def test_delete_redis_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis delete operation with fallback to in-memory."""
        await cache_manager.initialize()

        # Add item to in-memory cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "test_value"

        # Mock Redis to raise error
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.delete.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.delete("test_key")
            assert result is True
            assert cache_key not in cache_manager._cache

    @pytest.mark.asyncio
    async def test_clear_redis_fallback(self, cache_manager: CacheManager) -> None:
        """Test Redis clear operation with fallback to in-memory."""
        await cache_manager.initialize()

        # Add items to in-memory cache
        cache_manager._cache["loats:key1"] = "value1"
        cache_manager._cache["loats:key2"] = "value2"

        # Mock Redis to raise error
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.keys.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            result = await cache_manager.clear()
            assert result == 2
            assert len(cache_manager._cache) == 0

    @pytest.mark.asyncio
    async def test_get_cache_stats_redis_fallback(
        self, cache_manager: CacheManager
    ) -> None:
        """Test Redis stats operation with fallback to basic stats."""
        await cache_manager.initialize()

        # Add some items to cache
        cache_manager._cache["loats:key1"] = "value1"
        cache_manager._cache["loats:key2"] = "value2"

        # Simulate some cache operations
        cache_manager._cache_stats["hits"] = 10
        cache_manager._cache_stats["misses"] = 5

        # Mock Redis to raise error
        with patch.object(cache_manager, "_redis") as mock_redis:
            mock_redis.info.side_effect = Exception("Redis error")
            mock_redis.dbsize.side_effect = Exception("Redis error")
            cache_manager._cache_type = "redis"

            stats = await cache_manager.get_cache_stats()
            assert stats["enabled"] is True
            assert stats["cache_type"] == "redis"
            assert stats["current_size"] == 2
            assert stats["hits"] == 10
            assert stats["misses"] == 5

    @pytest.mark.asyncio
    async def test_get_or_set_error_handling(self, cache_manager: CacheManager) -> None:
        """Test get_or_set error handling."""
        await cache_manager.initialize()

        async def failing_fetch_func():
            raise Exception("Fetch failed")

        # Test with cache disabled
        cache_manager._cache = None
        with pytest.raises(Exception, match="Fetch failed"):
            await cache_manager.get_or_set("test_key", failing_fetch_func)

    @pytest.mark.asyncio
    async def test_get_or_set_json_decode_error(
        self, cache_manager: CacheManager
    ) -> None:
        """Test get_or_set with JSON decode error."""
        await cache_manager.initialize()

        # Add invalid JSON to cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "not valid json"

        async def fetch_func():
            return "fresh_value"

        result = await cache_manager.get_or_set("test_key", fetch_func)
        assert (
            result == "not valid json"
        )  # Should return raw value on JSON decode error

    @pytest.mark.asyncio
    async def test_cache_statistics_tracking(self, cache_manager: CacheManager) -> None:
        """Test cache statistics tracking."""
        await cache_manager.initialize()

        # Test initial stats
        assert cache_manager._cache_stats["hits"] == 0
        assert cache_manager._cache_stats["misses"] == 0
        assert cache_manager._cache_stats["sets"] == 0
        assert cache_manager._cache_stats["deletes"] == 0
        assert cache_manager._cache_stats["evictions"] == 0

        # Perform operations and check stats
        await cache_manager.set("key1", "value1")
        assert cache_manager._cache_stats["sets"] == 1

        await cache_manager.get("key1")
        assert cache_manager._cache_stats["hits"] == 1

        await cache_manager.get("missing_key")
        assert cache_manager._cache_stats["misses"] == 1

        await cache_manager.delete("key1")
        assert cache_manager._cache_stats["deletes"] == 1

        # Clear an empty cache should result in 0 evictions
        await cache_manager.clear()
        assert cache_manager._cache_stats["evictions"] == 0

    @pytest.mark.asyncio
    async def test_cache_pattern_matching(self, cache_manager: CacheManager) -> None:
        """Test cache pattern matching in clear method."""
        await cache_manager.initialize()

        # Add various keys
        cache_manager._cache["loats:test1"] = "value1"
        cache_manager._cache["loats:test2"] = "value2"
        cache_manager._cache["loats:other1"] = "value3"
        cache_manager._cache["loats:test3"] = "value4"

        # Clear with pattern
        result = await cache_manager.clear("test")
        assert result == 3  # Should clear test1, test2, test3
        assert len(cache_manager._cache) == 1
        assert "loats:other1" in cache_manager._cache

    @pytest.mark.asyncio
    async def test_cache_key_generation_edge_cases(
        self, cache_manager: CacheManager
    ) -> None:
        """Test cache key generation with edge cases."""
        # Test with empty key
        cache_key = cache_manager._get_cache_key("")
        assert cache_key == "loats:"

        # Test with special characters
        cache_key = cache_manager._get_cache_key("key/with/special:chars")
        assert cache_key == "loats:key/with/special:chars"

        # Test with unicode
        cache_key = cache_manager._get_cache_key("key_with_unicode_🚀")
        assert "loats:key_with_unicode_🚀" == cache_key


class TestCacheUtilitiesAdditional:
    """Additional tests for cache utility functions."""

    def test_model_to_cache_key_consistency(self) -> None:
        """Test model to cache key consistency."""

        class TestModel(BaseModel):
            name: str
            value: int

        model1 = TestModel(name="test", value=42)
        model2 = TestModel(name="test", value=42)

        key1 = model_to_cache_key(model1)
        key2 = model_to_cache_key(model2)

        # Same content should produce same key
        assert key1 == key2

    def test_dict_to_cache_key_consistency(self) -> None:
        """Test dict to cache key consistency."""
        data1 = {"name": "test", "value": 42}
        data2 = {"name": "test", "value": 42}

        key1 = dict_to_cache_key(data1)
        key2 = dict_to_cache_key(data2)

        # Same content should produce same key
        assert key1 == key2

    def test_dict_to_cache_key_order_independence(self) -> None:
        """Test dict to cache key is independent of key order."""
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "b": 2, "a": 1}

        key1 = dict_to_cache_key(data1)
        key2 = dict_to_cache_key(data2)

        # Different order should produce same key
        assert key1 == key2


class TestGlobalCacheManagerAdditional:
    """Additional tests for global cache manager instance."""

    @pytest.mark.asyncio
    async def test_global_cache_initialization_error_handling(self) -> None:
        """Test global cache initialization error handling."""
        # Mock the initialize method to raise an error
        with patch.object(
            cache_manager, "initialize", side_effect=Exception("Init failed")
        ):
            with pytest.raises(Exception, match="Init failed"):
                await initialize_cache()

    @pytest.mark.asyncio
    async def test_global_cache_close_error_handling(self) -> None:
        """Test global cache close error handling."""
        # Mock the close method to raise an error
        with patch.object(
            cache_manager, "close", side_effect=Exception("Close failed")
        ):
            with pytest.raises(Exception, match="Close failed"):
                await close_cache()
