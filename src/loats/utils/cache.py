"""
Caching utilities for LOATS13July2026.
Implements Redis-based caching with in-memory fallback for performance optimization.
"""

import json
from collections.abc import Callable
from typing import Any, TypeVar

from cachetools import TTLCache
from pydantic import BaseModel

from ..loats_logging import get_logger

# Optional Redis import for enhanced caching
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = get_logger(__name__)

T = TypeVar("T")


class CacheConfig:
    """Configuration for cache operations (Redis or in-memory)."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        prefix: str = "loats",
        max_size: int = 1000,
        cache_type: str = "memory",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str = "",
    ):
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self.max_size = max_size
        self.cache_type = cache_type
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_password = redis_password


class CacheManager:
    """Cache manager for LOATS13July2026 with Redis support and in-memory fallback.
    Uses Redis for distributed caching when available, falls back to in-memory TTLCache.
    """

    def __init__(self, config: CacheConfig):
        self.config = config
        self._cache: TTLCache[str, Any] | None = None
        self._redis: redis.Redis | None = None
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }
        self._cache_type: str = "uninitialized"

    async def initialize(self) -> None:
        """Initialize cache with Redis support and graceful fallback to in-memory."""
        try:
            # Try Redis first if configured and available
            if self.config.cache_type == "redis" and REDIS_AVAILABLE:
                try:
                    self._redis = redis.Redis(
                        host=self.config.redis_host,
                        port=self.config.redis_port,
                        password=self.config.redis_password,
                        decode_responses=True,
                        health_check_interval=30,
                    )
                    # Test Redis connection
                    await self._redis.ping()
                    self._cache_type = "redis"
                    logger.info(
                        f"Redis cache initialized (host={self.config.redis_host}:{self.config.redis_port})"
                    )
                    return
                except Exception as e:
                    logger.warning(
                        f"Redis connection failed, falling back to in-memory cache: {e}"
                    )
                    # Fall through to in-memory initialization

            # Initialize in-memory cache as fallback
            self._cache = TTLCache(
                maxsize=self.config.max_size,
                ttl=self.config.ttl_seconds,
            )
            self._cache_type = "in_memory_ttl"
            logger.info(
                f"In-memory cache initialized (max_size={self.config.max_size}, ttl={self.config.ttl_seconds}s)"
            )

        except Exception as e:
            logger.error(f"Cache initialization failed: {e}")
            raise

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
        """Get value from cache (Redis or in-memory)."""
        cache_key = self._get_cache_key(key)

        try:
            if self._cache_type == "redis" and self._redis:
                # Try Redis first
                try:
                    result = await self._redis.get(cache_key)
                    if result is not None:
                        self._cache_stats["hits"] += 1
                        return (
                            result.decode("utf-8")
                            if isinstance(result, bytes)
                            else str(result)
                        )
                    else:
                        self._cache_stats["misses"] += 1
                        return None
                except Exception as redis_error:
                    logger.warning(
                        f"Redis get failed for key {key}, falling back to in-memory: {redis_error}"
                    )
                    # Fall through to in-memory cache

            # Use in-memory cache
            if self._cache:
                result = self._cache.get(cache_key)
                if result is not None:
                    self._cache_stats["hits"] += 1
                    return str(result) if result else None
                else:
                    self._cache_stats["misses"] += 1
                    return None
            return None

        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(
        self, key: str, value: str | BaseModel | dict[str, Any], ttl: int | None = None
    ) -> bool:
        """Set value in cache (Redis or in-memory)."""
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

            # Try Redis first if available
            if self._cache_type == "redis" and self._redis:
                try:
                    await self._redis.setex(cache_key, ttl_seconds, value_str)
                    self._cache_stats["sets"] += 1
                    return True
                except Exception as redis_error:
                    logger.warning(
                        f"Redis set failed for key {key}, falling back to in-memory: {redis_error}"
                    )
                    # Fall through to in-memory cache

            # Use in-memory cache
            if self._cache is not None:
                self._cache[cache_key] = value_str
                self._cache_stats["sets"] += 1
                return True

            return False

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
        """Delete key from cache (Redis or in-memory)."""
        cache_key = self._get_cache_key(key)

        try:
            # Try Redis first if available
            if self._cache_type == "redis" and self._redis:
                try:
                    deleted = await self._redis.delete(cache_key)
                    if deleted:
                        self._cache_stats["deletes"] += 1
                        return True
                    return False
                except Exception as redis_error:
                    logger.warning(
                        f"Redis delete failed for key {key}, falling back to in-memory: {redis_error}"
                    )
                    # Fall through to in-memory cache

            # Use in-memory cache
            if self._cache and cache_key in self._cache:
                del self._cache[cache_key]
                self._cache_stats["deletes"] += 1
                return True

            return False

        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def clear(self, pattern: str = "*") -> int:
        """Clear cache by pattern (Redis or in-memory)."""
        try:
            if self._cache_type == "redis" and self._redis:
                try:
                    if pattern == "*":
                        # Clear all Redis keys with our prefix
                        keys = await self._redis.keys(f"{self.config.prefix}:*")
                        if keys:
                            await self._redis.delete(*keys)
                        count = len(keys)
                        self._cache_stats["evictions"] += count
                        return count
                    else:
                        # Pattern matching for Redis
                        search_pattern = f"{self.config.prefix}:{pattern}"
                        keys = await self._redis.keys(search_pattern)
                        if keys:
                            await self._redis.delete(*keys)
                        count = len(keys)
                        self._cache_stats["evictions"] += count
                        return count
                except Exception as redis_error:
                    logger.warning(
                        f"Redis clear failed, falling back to in-memory: {redis_error}"
                    )
                    # Fall through to in-memory cache

            # Use in-memory cache
            if self._cache:
                if pattern == "*":
                    # Clear all cache
                    count = len(self._cache)
                    self._cache.clear()
                    self._cache_stats["evictions"] += count
                    return count
                else:
                    # Pattern matching - clear keys that match the pattern
                    prefix_pattern = f"{self.config.prefix}:{pattern}"
                    keys_to_delete = [
                        k
                        for k in self._cache.keys()
                        if pattern in k or k.startswith(prefix_pattern)
                    ]

                    count = 0
                    for key in keys_to_delete:
                        if key in self._cache:
                            del self._cache[key]
                            count += 1

                    self._cache_stats["evictions"] += count
                    return count

            return 0

        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return 0

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if self._cache_type == "uninitialized":
            return {"enabled": False, "error": "Cache not initialized"}

        try:
            if self._cache_type == "redis" and self._redis:
                try:
                    # Get Redis info
                    redis_info = await self._redis.info()
                    keys_count = await self._redis.dbsize()

                    return {
                        "enabled": True,
                        "connected": True,
                        "cache_type": "redis",
                        "current_size": keys_count,
                        "max_size": redis_info.get("maxmemory", "unlimited"),
                        "hits": self._cache_stats["hits"],
                        "misses": self._cache_stats["misses"],
                        "sets": self._cache_stats["sets"],
                        "deletes": self._cache_stats["deletes"],
                        "evictions": self._cache_stats["evictions"],
                        "hit_rate": self._cache_stats["hits"]
                        / (
                            self._cache_stats["hits"]
                            + self._cache_stats["misses"]
                            + 1e-6
                        ),
                        "redis_version": redis_info.get("redis_version", "unknown"),
                        "used_memory": redis_info.get("used_memory", "unknown"),
                    }
                except Exception as redis_error:
                    logger.warning(
                        f"Redis stats failed, falling back to basic stats: {redis_error}"
                    )
                    # Fall through to basic stats

            # Basic stats for in-memory or fallback
            current_size = len(self._cache) if self._cache else 0
            return {
                "enabled": True,
                "connected": True,
                "cache_type": self._cache_type,
                "current_size": current_size,
                "max_size": (
                    self.config.max_size
                    if self._cache_type == "in_memory_ttl"
                    else "unlimited"
                ),
                "hits": self._cache_stats["hits"],
                "misses": self._cache_stats["misses"],
                "sets": self._cache_stats["sets"],
                "deletes": self._cache_stats["deletes"],
                "evictions": self._cache_stats["evictions"],
                "hit_rate": self._cache_stats["hits"]
                / (self._cache_stats["hits"] + self._cache_stats["misses"] + 1e-6),
            }

        except Exception as e:
            logger.error(f"Cache stats failed: {e}")
            return {"enabled": False, "error": str(e)}


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
    # Include trade_id if available for better cache key uniqueness
    if hasattr(model, "trade_id") and model.trade_id:
        return f"{model.__class__.__name__}:{model.trade_id}:{hash(model.model_dump_json())}"
    return f"{model.__class__.__name__}:{hash(model.model_dump_json())}"


def dict_to_cache_key(data: dict[str, Any]) -> str:
    """Convert dict to cache key."""
    return f"dict:{hash(json.dumps(data, sort_keys=True))}"
