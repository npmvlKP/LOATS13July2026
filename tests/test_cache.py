"""
Unit tests for cache utility module.
Tests in-memory TTL caching functionality.
"""

import json
from unittest.mock import patch

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


class TestCacheConfig:
    """Tests for CacheConfig class."""

    def test_default_config(self) -> None:
        """Test default cache configuration."""
        config = CacheConfig()
        assert config.ttl_seconds == 300
        assert config.prefix == "loats"
        assert config.max_size == 1000

    def test_custom_config(self) -> None:
        """Test custom cache configuration."""
        config = CacheConfig(ttl_seconds=600, prefix="test", max_size=2000)
        assert config.ttl_seconds == 600
        assert config.prefix == "test"
        assert config.max_size == 2000


class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig()
        return CacheManager(config)

    @pytest.mark.asyncio
    async def test_initialize_success(self, cache_manager: CacheManager) -> None:
        """Test successful in-memory cache initialization."""
        await cache_manager.initialize()
        assert cache_manager._cache is not None
        assert isinstance(cache_manager._cache, TTLCache)

    @pytest.mark.asyncio
    async def test_close(self, cache_manager: CacheManager) -> None:
        """Test closing in-memory cache."""
        await cache_manager.initialize()
        await cache_manager.close()
        # Cache is cleared but not set to None
        assert len(cache_manager._cache) == 0

    @pytest.mark.asyncio
    async def test_get_cache_key(self, cache_manager: CacheManager) -> None:
        """Test cache key generation."""
        cache_key = cache_manager._get_cache_key("test_key")
        assert cache_key == "loats:test_key"

    @pytest.mark.asyncio
    async def test_get_success(self, cache_manager: CacheManager) -> None:
        """Test successful cache get."""
        await cache_manager.initialize()
        # Manually add item to cache for testing
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "cached_value"

        result = await cache_manager.get("test_key")
        assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_get_not_found(self, cache_manager: CacheManager) -> None:
        """Test cache get with missing key."""
        await cache_manager.initialize()
        result = await cache_manager.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_no_cache(self, cache_manager: CacheManager) -> None:
        """Test cache get with no cache initialized."""
        result = await cache_manager.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_string(self, cache_manager: CacheManager) -> None:
        """Test setting string value in cache."""
        await cache_manager.initialize()
        result = await cache_manager.set("test_key", "test_value", ttl=60)
        assert result is True

        # Verify the value was stored
        cache_key = cache_manager._get_cache_key("test_key")
        assert cache_manager._cache[cache_key] == "test_value"

    @pytest.mark.asyncio
    async def test_set_basemodel(self, cache_manager: CacheManager) -> None:
        """Test setting BaseModel in cache."""

        class TestModel(BaseModel):
            name: str
            value: int

        await cache_manager.initialize()
        model = TestModel(name="test", value=42)
        result = await cache_manager.set("model_key", model, ttl=60)
        assert result is True

        # Verify the value was stored as JSON
        cache_key = cache_manager._get_cache_key("model_key")
        cached_value = cache_manager._cache[cache_key]
        assert isinstance(cached_value, str)
        assert "test" in cached_value
        assert "42" in cached_value

    @pytest.mark.asyncio
    async def test_set_dict(self, cache_manager: CacheManager) -> None:
        """Test setting dict in cache."""
        await cache_manager.initialize()
        data = {"name": "test", "value": 42}
        result = await cache_manager.set("dict_key", data, ttl=60)
        assert result is True

        # Verify the value was stored as JSON
        cache_key = cache_manager._get_cache_key("dict_key")
        cached_value = cache_manager._cache[cache_key]
        assert isinstance(cached_value, str)
        assert "test" in cached_value
        assert "42" in cached_value

    @pytest.mark.asyncio
    async def test_set_no_cache(self, cache_manager: CacheManager) -> None:
        """Test setting value with no cache initialized (auto-initializes now)."""
        result = await cache_manager.set("test_key", "test_value")
        assert result is True  # Cache now auto-initializes
        # Verify the value was actually cached
        cached_value = await cache_manager.get("test_key")
        assert cached_value == "test_value"

    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(self, cache_manager: CacheManager) -> None:
        """Test get_or_set with cache hit."""
        await cache_manager.initialize()

        # Pre-populate cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = json.dumps({"cached": "value"})

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)
        assert result == {"cached": "value"}

    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss(self, cache_manager: CacheManager) -> None:
        """Test get_or_set with cache miss."""
        await cache_manager.initialize()

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)
        assert result == {"fresh": "value"}

        # Verify the result was cached
        cache_key = cache_manager._get_cache_key("test_key")
        assert cache_key in cache_manager._cache

    @pytest.mark.asyncio
    async def test_get_or_set_force_refresh(self, cache_manager: CacheManager) -> None:
        """Test get_or_set with force refresh."""
        await cache_manager.initialize()

        # Pre-populate cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = json.dumps({"cached": "value"})

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set(
            "test_key", fetch_func, force_refresh=True
        )
        assert result == {"fresh": "value"}

    @pytest.mark.asyncio
    async def test_get_or_set_no_cache(self, cache_manager: CacheManager) -> None:
        """Test get_or_set with no cache initialized."""

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)
        assert result == {"fresh": "value"}

    @pytest.mark.asyncio
    async def test_delete_success(self, cache_manager: CacheManager) -> None:
        """Test successful cache delete."""
        await cache_manager.initialize()

        # Add item to cache
        cache_key = cache_manager._get_cache_key("test_key")
        cache_manager._cache[cache_key] = "test_value"

        result = await cache_manager.delete("test_key")
        assert result is True
        assert cache_key not in cache_manager._cache

    @pytest.mark.asyncio
    async def test_delete_not_found(self, cache_manager: CacheManager) -> None:
        """Test cache delete with missing key."""
        await cache_manager.initialize()
        result = await cache_manager.delete("missing_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_no_cache(self, cache_manager: CacheManager) -> None:
        """Test cache delete with no cache initialized."""
        result = await cache_manager.delete("test_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_success(self, cache_manager: CacheManager) -> None:
        """Test successful cache clear."""
        await cache_manager.initialize()

        # Add items to cache
        cache_manager._cache["loats:key1"] = "value1"
        cache_manager._cache["loats:key2"] = "value2"

        result = await cache_manager.clear()
        assert result == 2
        assert len(cache_manager._cache) == 0

    @pytest.mark.asyncio
    async def test_clear_pattern(self, cache_manager: CacheManager) -> None:
        """Test cache clear with pattern."""
        await cache_manager.initialize()

        # Add items to cache
        cache_manager._cache["loats:test1"] = "value1"
        cache_manager._cache["loats:test2"] = "value2"
        cache_manager._cache["loats:other"] = "value3"

        result = await cache_manager.clear("test")
        assert result == 2
        assert len(cache_manager._cache) == 1
        assert "loats:other" in cache_manager._cache

    @pytest.mark.asyncio
    async def test_clear_no_cache(self, cache_manager: CacheManager) -> None:
        """Test cache clear with no cache initialized."""
        result = await cache_manager.clear()
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_cache_stats_success(self, cache_manager: CacheManager) -> None:
        """Test successful cache stats retrieval."""
        await cache_manager.initialize()

        # Add some items to cache
        cache_manager._cache["loats:key1"] = "value1"
        cache_manager._cache["loats:key2"] = "value2"

        # Simulate some cache operations
        cache_manager._cache_stats["hits"] = 10
        cache_manager._cache_stats["misses"] = 5

        stats = await cache_manager.get_cache_stats()

        assert stats["enabled"] is True
        assert stats["connected"] is True
        assert stats["cache_type"] == "lightweight_in_memory"
        assert stats["current_size"] == 2
        assert stats["max_size"] == 1000
        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["hit_rate"] > 0

    @pytest.mark.asyncio
    async def test_get_cache_stats_no_cache(self, cache_manager: CacheManager) -> None:
        """Test cache stats with no cache initialized."""
        stats = await cache_manager.get_cache_stats()
        assert stats["enabled"] is False
        assert stats["error"] == "Cache not initialized"


class TestCacheUtilities:
    """Tests for cache utility functions."""

    def test_model_to_cache_key(self) -> None:
        """Test model to cache key conversion."""

        class TestModel(BaseModel):
            name: str
            value: int

        model = TestModel(name="test", value=42)
        cache_key = model_to_cache_key(model)

        assert cache_key.startswith("TestModel:")
        assert len(cache_key) > len("TestModel:")

    def test_dict_to_cache_key(self) -> None:
        """Test dict to cache key conversion."""
        data = {"name": "test", "value": 42}
        cache_key = dict_to_cache_key(data)

        assert cache_key.startswith("dict:")
        assert len(cache_key) > len("dict:")


class TestGlobalCacheManager:
    """Tests for global cache manager instance."""

    @pytest.mark.asyncio
    async def test_global_cache_manager(self) -> None:
        """Test global cache manager initialization."""
        # Test that global cache_manager is properly configured
        assert cache_manager.config.ttl_seconds == 300
        assert cache_manager.config.prefix == "loats"

    @pytest.mark.asyncio
    async def test_initialize_cache_function(self) -> None:
        """Test initialize_cache function."""
        with patch.object(cache_manager, "initialize") as mock_initialize:
            await initialize_cache()
            mock_initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cache_function(self) -> None:
        """Test close_cache function."""
        with patch.object(cache_manager, "close") as mock_close:
            await close_cache()
            mock_close.assert_called_once()
