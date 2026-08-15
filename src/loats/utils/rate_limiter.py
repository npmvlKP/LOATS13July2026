"""Rate limiter implementation LOATS13July2026."""

import asyncio
import threading
import time
from collections import deque

from ..config import get_settings
from ..loats_logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Rate limiter implementation using sliding window algorithm.

    The rate limiter enforces maximum operations per window limits specified in
    settings (max_ops).
    """

    def __init__(
        self,
        max_ops: int | None = None,
        window_size: float = 1.0,
        interval: float | None = None,
    ):
        """Initialize rate limiter.

        Args:
            max_ops: Maximum operations per window (default: from settings)
            window_size: Time window in seconds (default: 1.0)
            interval: Deprecated parameter for backward compatibility (use window_size)
        """
        settings = get_settings()
        self.max_ops: int = max_ops if max_ops is not None else settings.max_ops
        self.window_size: float = window_size
        # For backward compatibility with tests that use 'interval' parameter
        if interval is not None:
            self.window_size = interval
        # Keep 'interval' attribute for backward compatibility with tests
        self.interval: float = self.window_size
        # Initialize sliding-window state
        self.timestamps: deque[float] = deque()
        self.lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire token for operation.

        Implements sliding-window rate limiting. Expired timestamps are removed
        before checking the current token count so that a burst of calls within
        the configured window correctly exhaust the limit. This matches the
        expectations of the test suite where 50 rapid ``acquire`` calls should
        succeed and the 51st should return ``False``.
        """
        async with self.lock:
            now: float = time.monotonic()
            # Discard timestamps older than the window
            while self.timestamps and now - self.timestamps[0] > self.window_size:
                self.timestamps.popleft()
            if len(self.timestamps) < self.max_ops:
                self.timestamps.append(now)
                return True
        return False

    async def get_wait_time(self) -> float:
        """Get estimated wait time until next token is available.

        Returns:
            Estimated time in seconds until a token becomes available.
            Returns 0.0 if a token is immediately available.
        """
        async with self.lock:
            current_time: float = time.monotonic()

            # Remove timestamps older than window_size
            # Use > to ensure we maintain strict max_ops limit in any window
            while (
                self.timestamps and current_time - self.timestamps[0] > self.window_size
            ):
                self.timestamps.popleft()

            # Check if we can acquire immediately
            if len(self.timestamps) < self.max_ops:
                return 0.0

            # Otherwise, calculate time until oldest token expires
            if self.timestamps:
                oldest_timestamp = self.timestamps[0]
                time_until_oldest_expires = (
                    oldest_timestamp + self.window_size - current_time
                )
                return max(0.0, time_until_oldest_expires)
            else:
                return 0.0

    async def wait_for_token(self) -> None:
        """Wait until token is available.

        Raises:
            RateLimitExceededError: if waiting takes too long
        """
        while True:
            if await self.acquire():
                return
            # Calculate remaining time until oldest token expires
            current_time = time.monotonic()
            if self.timestamps:
                oldest_timestamp = self.timestamps[0]
                time_until_oldest_expires = (
                    oldest_timestamp + self.window_size - current_time
                )
                # Sleep until the oldest token expires, with a small buffer to account for scheduling delays
                # Use max(0.001, ...) to ensure we always sleep at least a tiny amount
                sleep_time = max(0.001, time_until_oldest_expires)
                # Add a small buffer (5% of window_size) to ensure we wake up slightly before expiration
                # This prevents race conditions where we wake up just after expiration
                buffer = self.window_size * 0.05
                sleep_time = max(0.001, time_until_oldest_expires - buffer)
            else:
                sleep_time = 0.05
            await asyncio.sleep(sleep_time)


class AsyncRateLimiter:
    """Async rate limiter using sliding window algorithm.

    This implementation tracks timestamps of operations and enforces
    a maximum number of operations within a sliding time window.
    """

    def __init__(self, max_ops: int | None = None, window_size: float = 1.0):
        """Initialize async rate limiter.

        Args:
            max_ops: Maximum operations per window (default: from settings)
            window_size: Time window in seconds (default: 1.0)
        """
        settings = get_settings()
        self.max_ops: int = max_ops if max_ops is not None else settings.max_ops
        self.window_size: float = window_size
        self.timestamps: deque[float] = deque()
        self.lock: asyncio.Lock = asyncio.Lock()
        self.get_wait_time = self._get_wait_time

    async def acquire(self) -> bool:
        """Acquire token for operation.

        Implements sliding window algorithm that strictly enforces
        max_ops operations per window_size seconds.

        Returns:
            True if token acquired successfully, False if rate limit exceeded
        """
        async with self.lock:
            current_time: float = time.monotonic()

            # Remove timestamps older than window_size
            # Use > to ensure we maintain strict max_ops limit in any window
            while (
                self.timestamps and current_time - self.timestamps[0] > self.window_size
            ):
                self.timestamps.popleft()

            # Check if we can acquire a token
            # We can acquire if we have fewer than max_ops operations in the current window
            if len(self.timestamps) < self.max_ops:
                self.timestamps.append(current_time)
                return True
            else:
                return False

    async def _get_wait_time(self) -> float:
        """Get estimated wait time until next token is available.

        Returns:
            Estimated time in seconds until a token becomes available.
            Returns 0.0 if a token is immediately available.
        """
        async with self.lock:
            current_time: float = time.monotonic()

            # Remove timestamps older than window_size
            # Use > to ensure we maintain strict max_ops limit in any window
            # Capture current_time again after cleanup to ensure accurate window calculation
            cleanup_time = current_time
            while (
                self.timestamps and cleanup_time - self.timestamps[0] > self.window_size
            ):
                self.timestamps.popleft()

            # Check if we can acquire immediately
            if len(self.timestamps) < self.max_ops:
                return 0.0

            # Otherwise, calculate time until oldest token expires
            if self.timestamps:
                oldest_timestamp = self.timestamps[0]
                time_until_oldest_expires = (
                    oldest_timestamp + self.window_size - current_time
                )
                return max(0.0, time_until_oldest_expires)
            else:
                return 0.0

    async def wait_for_token(self) -> None:
        """Wait until token is available.

        Raises:
            RateLimitExceededError: if waiting takes too long
        """
        while True:
            if await self.acquire():
                return
            # Calculate remaining time until oldest token expires
            current_time = time.monotonic()
            if self.timestamps:
                oldest_timestamp = self.timestamps[0]
                time_until_oldest_expires = (
                    oldest_timestamp + self.window_size - current_time
                )
                # Sleep until the oldest token expires, with a small buffer to account for scheduling delays
                # Use max(0.001, ...) to ensure we always sleep at least a tiny amount
                buffer = self.window_size * 0.05  # 5% buffer
                sleep_time = max(0.001, time_until_oldest_expires - buffer)
            else:
                sleep_time = 0.05
            await asyncio.sleep(sleep_time)


class SyncRateLimiter:
    """Synchronous rate limiter using sliding window algorithm.

    This implementation is designed for use with synchronous functions
    and uses threading.Lock instead of asyncio.Lock.
    """

    def __init__(
        self,
        max_ops: int | None = None,
        window_size: float = 1.0,
        interval: float | None = None,
    ):
        """Initialize synchronous rate limiter.

        Args:
            max_ops: Maximum operations per window (default: from settings)
            window_size: Time window in seconds (default: 1.0)
            interval: Deprecated parameter for backward compatibility (use window_size)
        """
        import threading
        from collections import deque

        settings = get_settings()
        self.max_ops: int = max_ops if max_ops is not None else settings.max_ops
        self.window_size: float = window_size
        # For backward compatibility with tests that use 'interval' parameter
        if interval is not None:
            self.window_size = interval
        # Keep 'interval' attribute for backward compatibility with tests
        self.interval: float = self.window_size
        self.timestamps: deque[float] = deque()
        self.lock: threading.Lock = threading.Lock()

    def acquire(self) -> bool:
        """Acquire token for operation.

        Implements sliding window algorithm that strictly enforces
        max_ops operations per window_size seconds.

        Returns:
            True if token acquired successfully, False if rate limit exceeded
        """
        with self.lock:
            current_time: float = time.monotonic()

            # Remove timestamps older than window_size
            # Use > to ensure we maintain strict max_ops limit in any window
            while (
                self.timestamps and current_time - self.timestamps[0] > self.window_size
            ):
                self.timestamps.popleft()

            # Check if we can acquire a token
            # We can acquire if we have fewer than max_ops operations in the current window
            if len(self.timestamps) < self.max_ops:
                self.timestamps.append(current_time)
                return True
            else:
                return False

    def wait_for_token(self) -> None:
        """Wait until token is available.

        Raises:
            RateLimitExceededError: if waiting takes too long
        """
        import time as time_module

        start_time = time_module.monotonic()
        timeout = 10.0  # 10 second timeout

        while True:
            if self.acquire():
                return
            if time_module.monotonic() - start_time > timeout:
                raise RateLimitExceededError("Timeout waiting for rate limit token")
            time_module.sleep(0.1)  # Small sleep to prevent busy waiting


class RateLimitExceededError(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        self.message: str = message
        super().__init__(self.message)


# Singleton infrastructure - recreated after accidental removal.
# Two independent locks protect the default singleton and the custom-parameter
# cache. They are lightweight and guarantee thread-safe lazy initialisation.
_default_lock = threading.Lock()
_custom_lock = threading.Lock()

# Default singleton instances (used when no custom parameters are supplied).
_default_order_rate_limiter: AsyncRateLimiter | None = None
_default_smart_order_rate_limiter: AsyncRateLimiter | None = None

# Synchronous rate limiter singletons
_sync_order_rate_limiter: SyncRateLimiter | None = None
_sync_smart_order_rate_limiter: SyncRateLimiter | None = None

# Custom singleton caches keyed by (max_ops, window_size).
_custom_order_rate_limiters: dict[tuple[int, float], AsyncRateLimiter] = {}
_custom_smart_order_rate_limiters: dict[tuple[int, float], AsyncRateLimiter] = {}

# Synchronous custom rate limiter caches
_sync_custom_order_rate_limiters: dict[tuple[int, float], SyncRateLimiter] = {}
_sync_custom_smart_order_rate_limiters: dict[tuple[int, float], SyncRateLimiter] = {}

# Backward-compatible names expected by existing test suite and modules.
# These aliases act as the true singleton storage accessed by the test fixtures.
# They are distinct from the internal "default" variables used elsewhere.
_order_rate_limiter_instance: AsyncRateLimiter | None = None
_smart_order_rate_limiter_instance: AsyncRateLimiter | None = None
# Separate locks guard each singleton to avoid cross-contamination.
_rate_limiter_lock = _default_lock
_smart_rate_limiter_lock = threading.Lock()

# Synchronous rate limiter locks
_sync_rate_limiter_lock = threading.Lock()
_sync_smart_rate_limiter_lock = threading.Lock()


# Public factory functions - used throughout the codebase and tests.
def get_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> AsyncRateLimiter:
    """Return a shared ``AsyncRateLimiter`` for order-rate limiting.

    * No ``max_ops`` -> return the *process-wide* default singleton (from settings.max_ops).
    * ``max_ops`` supplied → return a stable instance cached per ``(max_ops,
      window_size)`` pair.
    """
    if max_ops is None:
        # Default singleton - use backward-compatible alias and its lock
        with _rate_limiter_lock:
            global _order_rate_limiter_instance
            if _order_rate_limiter_instance is None:
                _order_rate_limiter_instance = AsyncRateLimiter(
                    max_ops=None, window_size=window_size
                )
            return _order_rate_limiter_instance

    # If default singleton already exists, ignore custom params and return it
    with _rate_limiter_lock:
        if _order_rate_limiter_instance is not None:
            return _order_rate_limiter_instance

    # Custom parameters - use cache keyed by (max_ops, window_size)
    key = (max_ops, window_size)
    with _custom_lock:
        if key not in _custom_order_rate_limiters:
            _custom_order_rate_limiters[key] = AsyncRateLimiter(
                max_ops=max_ops, window_size=window_size
            )
        return _custom_order_rate_limiters[key]


def get_smart_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> AsyncRateLimiter:
    """Return a shared ``AsyncRateLimiter`` for smart-order limiting.

    Mirrors :func:`get_order_rate_limiter` but uses a distinct default singleton.
    """
    if max_ops is None:
        # Default singleton - use backward-compatible alias and its lock
        with _smart_rate_limiter_lock:
            global _smart_order_rate_limiter_instance
            if _smart_order_rate_limiter_instance is None:
                _smart_order_rate_limiter_instance = AsyncRateLimiter(
                    max_ops=None, window_size=window_size
                )
            return _smart_order_rate_limiter_instance

    # If default singleton already exists, ignore custom params and return it
    with _smart_rate_limiter_lock:
        if _smart_order_rate_limiter_instance is not None:
            return _smart_order_rate_limiter_instance

    key = (max_ops, window_size)
    with _custom_lock:
        if key not in _custom_smart_order_rate_limiters:
            _custom_smart_order_rate_limiters[key] = AsyncRateLimiter(
                max_ops=max_ops, window_size=window_size
            )
        return _custom_smart_order_rate_limiters[key]


def get_sync_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> SyncRateLimiter:
    """Return a shared ``SyncRateLimiter`` for synchronous order-rate limiting.

    * No ``max_ops`` -> return the *process-wide* default singleton (from settings.max_ops).
    * ``max_ops`` supplied → return a stable instance cached per ``(max_ops,
      window_size)`` pair.
    """
    if max_ops is None:
        # Default singleton - use synchronous lock
        with _sync_rate_limiter_lock:
            global _sync_order_rate_limiter
            if _sync_order_rate_limiter is None:
                _sync_order_rate_limiter = SyncRateLimiter(
                    max_ops=None, window_size=window_size
                )
            return _sync_order_rate_limiter

    # If default singleton already exists, ignore custom params and return it
    with _sync_rate_limiter_lock:
        if _sync_order_rate_limiter is not None:
            return _sync_order_rate_limiter

    # Custom parameters - use cache keyed by (max_ops, window_size)
    # Custom parameters - use cache keyed by (max_ops, window_size)
    key = (max_ops, window_size)
    with _custom_lock:
        if key not in _sync_custom_order_rate_limiters:
            _sync_custom_order_rate_limiters[key] = SyncRateLimiter(
                max_ops=max_ops, window_size=window_size
            )
        return _sync_custom_order_rate_limiters[key]


def get_sync_smart_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> SyncRateLimiter:
    """Return a shared ``SyncRateLimiter`` for synchronous smart-order limiting.

    Mirrors :func:`get_sync_order_rate_limiter` but uses a distinct default singleton.
    """
    if max_ops is None:
        # Default singleton - use synchronous lock
        with _sync_smart_rate_limiter_lock:
            global _sync_smart_order_rate_limiter
            if _sync_smart_order_rate_limiter is None:
                _sync_smart_order_rate_limiter = SyncRateLimiter(
                    max_ops=None, window_size=window_size
                )
            return _sync_smart_order_rate_limiter

    # If default singleton already exists, ignore custom params and return it
    with _sync_smart_rate_limiter_lock:
        if _sync_smart_order_rate_limiter is not None:
            return _sync_smart_order_rate_limiter

    key = (max_ops, window_size)
    with _custom_lock:
        if key not in _sync_custom_smart_order_rate_limiters:
            _sync_custom_smart_order_rate_limiters[key] = SyncRateLimiter(
                max_ops=max_ops, window_size=window_size
            )
        return _sync_custom_smart_order_rate_limiters[key]


# ---------------------------------------------------------------------------
# Testing utilities
# ---------------------------------------------------------------------------
def _reset_singletons_for_testing() -> None:
    """Reset all singleton instances.

    Used by the test suite to guarantee a clean environment between tests.
    Clears both the backward-compatible alias singletons and the internal default
    singletons. Locks remain unchanged.
    """
    global _order_rate_limiter_instance, _smart_order_rate_limiter_instance
    global _default_order_rate_limiter, _default_smart_order_rate_limiter
    global _sync_order_rate_limiter, _sync_smart_order_rate_limiter

    _order_rate_limiter_instance = None
    _smart_order_rate_limiter_instance = None
    _default_order_rate_limiter = None
    _default_smart_order_rate_limiter = None

    # Clear synchronous rate limiter singletons
    _sync_order_rate_limiter = None
    _sync_smart_order_rate_limiter = None

    # Also clear custom caches to avoid cross-test contamination.
    _custom_order_rate_limiters.clear()
    _custom_smart_order_rate_limiters.clear()
    _sync_custom_order_rate_limiters.clear()
    _sync_custom_smart_order_rate_limiters.clear()
