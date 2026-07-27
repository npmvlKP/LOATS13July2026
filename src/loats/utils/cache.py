"""
Caching utilities for LOATS13July2026.
Implements Redis-based caching layer for performance optimization.
"""

import json
from collections.abc import Callable
from typing import Any, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel

from ..logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheConfig:
    """Configuration for cache operations."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        prefix: str = "loats",
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
    ):
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self.host = host
        self.port = port
        self.db = db


class CacheManager:
    """Redis-based cache manager for LOATS13July2026."""

    def __init__(self, config: CacheConfig):
        self.config = config
        self._redis: redis.Redis | None = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            self._redis = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                decode_responses=True,
                health_check_interval=30,
            )
            # Test connection
            await self._redis.ping()
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Cache will be disabled.")
            self._redis = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _get_cache_key(self, key: str) -> str:
        """Generate cache key with prefix."""
        return f"{self.config.prefix}:{key}"

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        if not self._redis:
            return None

        try:
            result = await self._redis.get(self._get_cache_key(key))
            return str(result) if result else None
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(
        self, key: str, value: str | BaseModel | dict, ttl: int | None = None
    ) -> bool:
        """Set value in cache."""
        if not self._redis:
            return False

        try:
            # Convert BaseModel or dict to JSON string
            if isinstance(value, BaseModel):
                value_str = value.model_dump_json()
            elif isinstance(value, dict):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            ttl_seconds = ttl if ttl is not None else self.config.ttl_seconds
            await self._redis.setex(self._get_cache_key(key), ttl_seconds, value_str)
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for key {key}: {e}")
            return False

    async def get_or_set(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: int | None = None,
        force_refresh: bool = False,
    ) -> Any:
        """
        Get value from cache or set it if not found.

        Args:
            key: Cache key
            fetch_func: Function to call if cache miss occurs
            ttl: Time-to-live in seconds (overrides default if provided)
            force_refresh: Force refresh even if cached value exists

        Returns:
            Cached or freshly fetched value
        """
        if not self._redis or force_refresh:
            # Cache disabled or forced refresh - call fetch function directly
            try:
                return await fetch_func()
            except Exception as e:
                logger.error(f"Fetch function failed: {e}")
                raise

        # Try to get from cache
        cached_value = await self.get(key)
        if cached_value is not None and not force_refresh:
            logger.debug(f"Cache hit for key: {key}")
            try:
                return json.loads(cached_value)
            except json.JSONDecodeError:
                return cached_value

        # Cache miss - call fetch function
        logger.debug(f"Cache miss for key: {key}")
        try:
            fresh_value = await fetch_func()

            # Cache the result
            if isinstance(fresh_value, (BaseModel, dict, str)):
                await self.set(key, fresh_value, ttl)

            return fresh_value
        except Exception as e:
            logger.error(f"Fetch function failed: {e}")
            raise

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self._redis:
            return False

        try:
            result = await self._redis.delete(self._get_cache_key(key))
            return bool(result)
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def clear(self, pattern: str = "*") -> int:
        """Clear cache by pattern."""
        if not self._redis:
            return 0

        try:
            keys = await self._redis.keys(f"{self.config.prefix}:{pattern}")
            if keys:
                result = await self._redis.delete(*keys)
                return int(result) if result else 0
            return 0
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return 0

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self._redis:
            return {"enabled": False, "error": "Redis not connected"}

        try:
            info = await self._redis.info("memory")
            keys = await self._redis.dbsize()

            return {
                "enabled": True,
                "connected": True,
                "keys": keys,
                "memory_usage": info.get("used_memory", "N/A"),
                "memory_peak": info.get("used_memory_peak", "N/A"),
                "last_save": info.get("last_save_time", "N/A"),
            }
        except Exception as e:
            return {"enabled": True, "connected": False, "error": str(e)}


# Global cache manager instance
cache_config = CacheConfig(
    ttl_seconds=300,  # 5 minutes default TTL
    prefix="loats",
    host="localhost",
    port=6379,
    db=0,
)

cache_manager = CacheManager(cache_config)


async def initialize_cache() -> None:
    """Initialize the global cache manager."""
    await cache_manager.initialize()


async def close_cache() -> None:
    """Close the global cache manager."""
    await cache_manager.close()


def model_to_cache_key(model: BaseModel) -> str:
    """Convert BaseModel to cache key."""
    return f"{model.__class__.__name__}:{hash(model.model_dump_json())}"


def dict_to_cache_key(data: dict) -> str:
    """Convert dict to cache key."""
    return f"dict:{hash(json.dumps(data, sort_keys=True))}"
