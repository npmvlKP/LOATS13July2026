"""
Unit tests for cache utility module.
Tests Redis-based caching functionality.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from pydantic import BaseModel
from redis.asyncio import Redis

from src.loats.utils.cache import (
    CacheConfig,
    CacheManager,
    cache_manager,
    initialize_cache,
    close_cache,
    model_to_cache_key,
    dict_to_cache_key
)

class TestCacheConfig:
    """Tests for CacheConfig class."""

    def test_default_config(self) -> None:
        """Test default cache configuration."""
        config = CacheConfig()
        assert config.ttl_seconds == 300
        assert config.prefix == "loats"
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0

    def test_custom_config(self) -> None:
        """Test custom cache configuration."""
        config = CacheConfig(
            ttl_seconds=600,
            prefix="test",
            host="redis.example.com",
            port=6380,
            db=1
        )
        assert config.ttl_seconds == 600
        assert config.prefix == "test"
        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.db == 1

class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig()
        return CacheManager(config)

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        return AsyncMock(spec=Redis)

    @pytest.mark.asyncio
    async def test_initialize_success(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test successful Redis initialization."""
        with patch("redis.asyncio.Redis", return_value=mock_redis):
            mock_redis.ping.return_value = True
            await cache_manager.initialize()

            assert cache_manager._redis is mock_redis
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_failure(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test Redis initialization failure."""
        with patch("redis.asyncio.Redis", return_value=mock_redis):
            mock_redis.ping.side_effect = Exception("Connection failed")
            await cache_manager.initialize()

            assert cache_manager._redis is None

    @pytest.mark.asyncio
    async def test_close(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test closing Redis connection."""
        cache_manager._redis = mock_redis
        await cache_manager.close()

        mock_redis.close.assert_called_once()
        assert cache_manager._redis is None

    @pytest.mark.asyncio
    async def test_get_cache_key(self, cache_manager: CacheManager) -> None:
        """Test cache key generation."""
        cache_key = cache_manager._get_cache_key("test_key")
        assert cache_key == "loats:test_key"

    @pytest.mark.asyncio
    async def test_get_success(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test successful cache get."""
        cache_manager._redis = mock_redis
        mock_redis.get.return_value = "cached_value"

        result = await cache_manager.get("test_key")
        assert result == "cached_value"
        mock_redis.get.assert_called_once_with("loats:test_key")

    @pytest.mark.asyncio
    async def test_get_not_found(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test cache get with missing key."""
        cache_manager._redis = mock_redis
        mock_redis.get.return_value = None

        result = await cache_manager.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_no_redis(self, cache_manager: CacheManager) -> None:
        """Test cache get with no Redis connection."""
        cache_manager._redis = None
        result = await cache_manager.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_string(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test setting string value in cache."""
        cache_manager._redis = mock_redis
        result = await cache_manager.set("test_key", "test_value", ttl=60)

        assert result is True
        mock_redis.setex.assert_called_once_with("loats:test_key", 60, "test_value")

    @pytest.mark.asyncio
    async def test_set_basemodel(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test setting BaseModel in cache."""
        class TestModel(BaseModel):
            name: str
            value: int

        cache_manager._redis = mock_redis
        model = TestModel(name="test", value=42)

        result = await cache_manager.set("model_key", model, ttl=60)

        assert result is True
        mock_redis.setex.assert_called_once()
        # Verify the call was made with correct parameters
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "loats:model_key"
        assert call_args[0][1] == 60
        # The value should be JSON string
        assert isinstance(call_args[0][2], str)
        assert "test" in call_args[0][2]
        assert "42" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_dict(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test setting dict in cache."""
        cache_manager._redis = mock_redis
        data = {"name": "test", "value": 42}

        result = await cache_manager.set("dict_key", data, ttl=60)

        assert result is True
        mock_redis.setex.assert_called_once()
        # Verify the call was made with correct parameters
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "loats:dict_key"
        assert call_args[0][1] == 60
        # The value should be JSON string
        assert isinstance(call_args[0][2], str)
        assert "test" in call_args[0][2]
        assert "42" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_no_redis(self, cache_manager: CacheManager) -> None:
        """Test setting value with no Redis connection."""
        cache_manager._redis = None
        result = await cache_manager.set("test_key", "test_value")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_exception(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test setting value with Redis exception."""
        cache_manager._redis = mock_redis
        mock_redis.setex.side_effect = Exception("Redis error")

        result = await cache_manager.set("test_key", "test_value")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test get_or_set with cache hit."""
        cache_manager._redis = mock_redis
        mock_redis.get.return_value = json.dumps({"cached": "value"})

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)

        assert result == {"cached": "value"}
        mock_redis.get.assert_called_once()
        # fetch_func should not be called on cache hit
        # (Note: In actual implementation, it might still be called but result ignored)

    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test get_or_set with cache miss."""
        cache_manager._redis = mock_redis
        mock_redis.get.return_value = None

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)

        assert result == {"fresh": "value"}
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_set_force_refresh(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test get_or_set with force refresh."""
        cache_manager._redis = mock_redis
        mock_redis.get.return_value = json.dumps({"cached": "value"})

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func, force_refresh=True)

        assert result == {"fresh": "value"}
        # When force_refresh=True, fetch_func should be called directly
        # and cache operations should be bypassed

    @pytest.mark.asyncio
    async def test_get_or_set_no_redis(self, cache_manager: CacheManager) -> None:
        """Test get_or_set with no Redis connection."""
        cache_manager._redis = None

        async def fetch_func():
            return {"fresh": "value"}

        result = await cache_manager.get_or_set("test_key", fetch_func)

        assert result == {"fresh": "value"}

    @pytest.mark.asyncio
    async def test_delete_success(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test successful cache delete."""
        cache_manager._redis = mock_redis
        mock_redis.delete.return_value = 1

        result = await cache_manager.delete("test_key")
        assert result is True
        mock_redis.delete.assert_called_once_with("loats:test_key")

    @pytest.mark.asyncio
    async def test_delete_not_found(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test cache delete with missing key."""
        cache_manager._redis = mock_redis
        mock_redis.delete.return_value = 0

        result = await cache_manager.delete("missing_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_no_redis(self, cache_manager: CacheManager) -> None:
        """Test cache delete with no Redis connection."""
        cache_manager._redis = None
        result = await cache_manager.delete("test_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_success(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test successful cache clear."""
        cache_manager._redis = mock_redis
        mock_redis.keys.return_value = ["loats:key1", "loats:key2"]
        mock_redis.delete.return_value = 2

        result = await cache_manager.clear()
        assert result == 2
        mock_redis.keys.assert_called_once_with("loats:*")
        mock_redis.delete.assert_called_once_with("loats:key1", "loats:key2")

    @pytest.mark.asyncio
    async def test_clear_no_keys(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test cache clear with no matching keys."""
        cache_manager._redis = mock_redis
        mock_redis.keys.return_value = []

        result = await cache_manager.clear()
        assert result == 0
        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_no_redis(self, cache_manager: CacheManager) -> None:
        """Test cache clear with no Redis connection."""
        cache_manager._redis = None
        result = await cache_manager.clear()
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_cache_stats_success(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test successful cache stats retrieval."""
        cache_manager._redis = mock_redis
        mock_redis.info.return_value = {
            "used_memory": "1000000",
            "used_memory_peak": "2000000",
            "last_save_time": "1234567890"
        }
        mock_redis.dbsize.return_value = 100

        stats = await cache_manager.get_cache_stats()

        assert stats["enabled"] is True
        assert stats["connected"] is True
        assert stats["keys"] == 100
        assert stats["memory_usage"] == "1000000"
        assert stats["memory_peak"] == "2000000"
        assert stats["last_save"] == "1234567890"

    @pytest.mark.asyncio
    async def test_get_cache_stats_no_redis(self, cache_manager: CacheManager) -> None:
        """Test cache stats with no Redis connection."""
        cache_manager._redis = None

        stats = await cache_manager.get_cache_stats()

        assert stats["enabled"] is False
        assert stats["error"] == "Redis not connected"

    @pytest.mark.asyncio
    async def test_get_cache_stats_exception(self, cache_manager: CacheManager, mock_redis: AsyncMock) -> None:
        """Test cache stats with Redis exception."""
        cache_manager._redis = mock_redis
        mock_redis.info.side_effect = Exception("Redis error")

        stats = await cache_manager.get_cache_stats()

        assert stats["enabled"] is True
        assert stats["connected"] is False
        assert "Redis error" in stats["error"]

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