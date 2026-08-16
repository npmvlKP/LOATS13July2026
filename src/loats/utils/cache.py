"""
Lightweight caching utilities for LOATS13July2026 LITE edition.
Implements simple in-memory caching optimized for minimal resource usage.
"""
import asyncio
import hashlib
import json
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from cachetools import TTLCache
from pydantic import BaseModel

from ..loats_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

class CacheConfig:
    """Configuration for cache operations (LITE edition - in-memory only)."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        prefix: str = "loats",
        max_size: int = 1000,
        cache_type: str = "memory",
    ):
        """Initialize cache configuration.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
            prefix: Prefix for cache keys to avoid collisions
            max_size: Maximum number of entries in cache
            cache_type: Type of cache backend ('memory' only for LITE edition)
        """
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self.max_size = max_size
        self.cache_type = cache_type

class CacheManager:
    """Cache manager for LOATS13July2026 LITE edition.
    Uses in-memory caching only.
    """

    def __init__(self, config: CacheConfig):
        """Initialize cache manager with in-memory cache."""
        self.config = config
        self._cache: TTLCache[str, Any] | None = None
        self._cache_lock = threading.RLock()  # FIX-F-THREAD-1: Use threading.RLock for thread safety
        self._init_lock = threading.RLock()  # FIX-F-THREAD-8: Use threading.RLock instead of asyncio.Lock for thread safety
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }
        self._cache_type: str = "uninitialized"
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize in-memory cache (LITE edition)."""
        try:
            logger.debug("DEBUG INIT: Starting initialization")
            # Use in-memory cache only for LITE edition
            logger.debug("DEBUG INIT: Creating in-memory cache")
            self._cache = TTLCache(
                maxsize=self.config.max_size,
                ttl=self.config.ttl_seconds,
            )
            self._cache_type = "in_memory_ttl"
            logger.debug(
                f"DEBUG INIT: Created cache - _cache={self._cache is not None}"
            )

            self._initialized = True
            logger.info(
                f"Cache initialized (type={self._cache_type}, max_size={self.config.max_size}, ttl={self.config.ttl_seconds}s)"
            )
        except Exception as e:
            logger.error(f"Cache initialization failed: {e}")
            raise

    async def close(self) -> None:
        """Close and clear the in-memory cache."""
        if self._cache:
            self._cache.clear()
            logger.info("Lightweight in-memory cache closed")
        self._initialized = False

    def _get_cache_key(self, key: str) -> str:
        """Generate cache key with prefix."""
        return f"{self.config.prefix}:{key}"

    async def get(self, key: str) -> str | None:
        """Get value from in-memory cache."""
        if not self._initialized:
            return None

        cache_key = self._get_cache_key(key)

        try:
            if self._cache:
                # FIX-F-THREAD-2: Use threading.RLock for cross-thread safety
                with self._cache_lock:
                    result = self._cache.get(cache_key)
                    if result is not None:
                        self._cache_stats["hits"] += 1
                        return str(result)
                    else:
                        self._cache_stats["misses"] += 1
                        return None
            else:
                return None
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(
        self, key: str, value: str | BaseModel | dict[str, Any], ttl: int | None = None
    ) -> bool:
        """Set value in in-memory cache."""
        # Ensure cache is initialized
        logger.debug(f"DEBUG SET: Initial check - _initialized={self._initialized}")
        if not self._initialized:
            logger.debug("DEBUG SET: Cache not initialized, initializing...")
            with self._init_lock:
                if not self._initialized:
                    await self.initialize()
            logger.debug(
                f"DEBUG SET: After init - _initialized={self._initialized}, _cache={self._cache is not None}"
            )

        # After initialization, check if we have a valid cache backend
        logger.debug(f"DEBUG SET: Backend check - _cache={self._cache is not None}")
        if self._cache is None:
            # This should not happen, but if it does, try to initialize again
            logger.error(
                f"Cache not properly initialized: _cache={self._cache}, _initialized={self._initialized}"
            )
            with self._init_lock:
                if self._cache is None:
                    await self.initialize()

            # Final check - if still no backend, fail
            if self._cache is None:
                logger.error("Failed to initialize cache after retry")
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
            logger.debug(f"Setting cache key: {cache_key}, value: {value_str}")

            # FIX-F-THREAD-3: Use threading.RLock for cross-thread safety
            with self._cache_lock:
                self._cache[cache_key] = value_str
                self._cache_stats["sets"] += 1
                cache_size = len(self._cache)
            logger.debug(
                f"In-memory cache set successful. Current cache size: {cache_size}"
            )
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
        # Ensure cache is initialized
        if not self._initialized:
            await self.initialize()

        if force_refresh:
            # Forced refresh - call fetch function directly
            try:
                return await fetch_func()
            except Exception as e:
                logger.error(f"Fetch function failed: {e}")
                raise

        # Try to get from cache
        cache_key = self._get_cache_key(key)
        cached_value = None

        if self._cache is not None:
            # FIX-F-THREAD-4: Use threading.RLock for cross-thread safety
            with self._cache_lock:
                result = self._cache.get(cache_key)
                if result is not None:
                    self._cache_stats["hits"] += 1
                    cached_value = str(result)
                else:
                    self._cache_stats["misses"] += 1

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
        """Delete key from in-memory cache."""
        if not self._initialized:
            return False

        cache_key = self._get_cache_key(key)

        try:
            if self._cache:
                # FIX-F-THREAD-5: Use threading.RLock for cross-thread safety
                with self._cache_lock:
                    if cache_key in self._cache:
                        del self._cache[cache_key]
                        self._cache_stats["deletes"] += 1
                        return True
                    return False
            else:
                return False
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def clear(self, pattern: str = "*") -> int:
        """Clear in-memory cache by pattern."""
        if not self._initialized:
            return 0

        try:
            if self._cache:
                # FIX-F-THREAD-6: Use threading.RLock for cross-thread safety
                with self._cache_lock:
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
            else:
                return 0

        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return 0

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self._initialized:
            return {"enabled": False, "error": "Cache not initialized"}

        try:
            current_size = 0
            if self._cache:
                # FIX-F-THREAD-7: Use threading.RLock for cross-thread safety
                with self._cache_lock:
                    current_size = len(self._cache)

            return {
                "enabled": True,
                "connected": self._cache is not None,
                "cache_type": "lightweight_in_memory",
                "current_size": current_size,
                "max_size": self.config.max_size,
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

# Global cache manager instance (LITE edition - in-memory only)
cache_config = CacheConfig(
    ttl_seconds=300,  # 5 minutes default TTL
    prefix="loats",
    max_size=500,  # Reduced max size for LITE edition
    cache_type="memory",  # Default to memory
)

cache_manager = CacheManager(cache_config)

async def initialize_cache() -> None:
    """Initialize the lightweight global cache manager."""
    await cache_manager.initialize()

async def close_cache() -> None:
    """Close the lightweight global cache manager."""
    await cache_manager.close()

def _hash_text(text: str) -> str:
    """Return deterministic SHA-256 digest for cache keys.

    ``hash()`` is randomized per process (PYTHONHASHSEED) which produces
    different cache keys across processes, defeating shared caches.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def model_to_cache_key(model: BaseModel) -> str:
    """Convert BaseModel to cache key."""
    # Include trade_id if available for better cache key uniqueness
    if hasattr(model, "trade_id") and model.trade_id:
        return (
            f"{model.__class__.__name__}:{model.trade_id}:"
            f"{_hash_text(model.model_dump_json())}"
        )
    return f"{model.__class__.__name__}:{_hash_text(model.model_dump_json())}"

def dict_to_cache_key(data: dict[str, Any]) -> str:
    """Convert dict to cache key."""
    return f"dict:{_hash_text(json.dumps(data, sort_keys=True))}"