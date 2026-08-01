"""
Caching utilities for LOATS13July2026.
Implements in-memory TTL cache for performance optimization.
Consistent with LITE philosophy: zero external services.
"""

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

from cachetools import TTLCache
from pydantic import BaseModel

from ..loats_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheConfig:
    """Configuration for in-memory cache operations."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        prefix: str = "loats",
        max_size: int = 1000,
    ):
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self.max_size = max_size


class CacheManager:
    """In-memory TTL cache manager for LOATS13July2026.
    Uses cachetools.TTLCache for zero-dependency caching.
    """

    def __init__(self, config: CacheConfig):
        self.config = config
        self._cache: TTLCache[str, Any] | None = None
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }

    async def initialize(self) -> None:
        """Initialize in-memory cache."""
        self._cache = TTLCache(
            maxsize=self.config.max_size,
            ttl=self.config.ttl_seconds,
        )
        logger.info(f"In-memory cache initialized (max_size={self.config.max_size}, ttl={self.config.ttl_seconds}s)")

    async def close(self) -> None:
        """Close in-memory cache."""
        if self._cache:
            self._cache.clear()
            # Don't set to None, just clear the contents
            logger.info("In-memory cache closed")

    def _get_cache_key(self, key: str) -> str:
        """Generate cache key with prefix."""
        return f"{self.config.prefix}:{key}"

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        if not self._cache:
            return None

        cache_key = self._get_cache_key(key)
        try:
            result = self._cache.get(cache_key)
            if result is not None:
                self._cache_stats["hits"] += 1
                return str(result) if result else None
            else:
                self._cache_stats["misses"] += 1
                return None
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(
        self, key: str, value: str | BaseModel | dict, ttl: int | None = None
    ) -> bool:
        """Set value in cache."""
        if self._cache is None:
            return False

        try:
            # Convert BaseModel or dict to JSON string
            if isinstance(value, BaseModel):
                value_str = value.model_dump_json()
            elif isinstance(value, dict):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            cache_key = self._get_cache_key(key)
            ttl_seconds = ttl if ttl is not None else self.config.ttl_seconds

            # For TTLCache, we need to handle TTL manually for individual items
            # Since TTLCache has a global TTL, we'll use the default TTL
            self._cache[cache_key] = value_str
            self._cache_stats["sets"] += 1

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
        if self._cache is None or force_refresh:
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
        if not self._cache:
            return False

        try:
            cache_key = self._get_cache_key(key)
            if cache_key in self._cache:
                del self._cache[cache_key]
                self._cache_stats["deletes"] += 1
                return True
            return False
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def clear(self, pattern: str = "*") -> int:
        """Clear cache by pattern."""
        if not self._cache:
            return 0

        try:
            if pattern == "*":
                # Clear all cache
                count = len(self._cache)
                self._cache.clear()
                self._cache_stats["evictions"] += count
                return count
            else:
                # Pattern matching - clear keys that match the pattern
                prefix_pattern = f"{self.config.prefix}:{pattern}"
                keys_to_delete = [k for k in self._cache.keys() if pattern in k or k.startswith(prefix_pattern)]

                count = 0
                for key in keys_to_delete:
                    if key in self._cache:
                        del self._cache[key]
                        count += 1

                self._cache_stats["evictions"] += count
                return count
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return 0

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self._cache:
            return {"enabled": False, "error": "Cache not initialized"}

        return {
            "enabled": True,
            "connected": True,
            "cache_type": "in_memory_ttl",
            "current_size": len(self._cache),
            "max_size": self.config.max_size,
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "sets": self._cache_stats["sets"],
            "deletes": self._cache_stats["deletes"],
            "evictions": self._cache_stats["evictions"],
            "hit_rate": self._cache_stats["hits"] / (self._cache_stats["hits"] + self._cache_stats["misses"] + 1e-6),
        }


# Global cache manager instance
cache_config = CacheConfig(
    ttl_seconds=300,  # 5 minutes default TTL
    prefix="loats",
    max_size=1000,  # Maximum cache entries
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
