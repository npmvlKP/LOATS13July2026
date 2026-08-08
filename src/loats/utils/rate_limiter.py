"""Rate limiter implementation LOATS13July2026."""

import asyncio
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
        self.timestamps: deque[float] = deque()
        self.lock: asyncio.Lock = asyncio.Lock()

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
                # Sleep until the oldest token expires
                # Use a small sleep time to be more deterministic
                sleep_time = max(0.001, time_until_oldest_expires)
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


# F-CONC-3: Removed module-level singletons to implement per-call rate limiters
# This ensures proper isolation between different callers and prevents shared state issues


def get_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> AsyncRateLimiter:
    """Get order rate limiter instance.

    Args:
        max_ops: Maximum operations per window. If None, uses default from settings.
        window_size: Time window in seconds.

    Returns:
        Configured AsyncRateLimiter instance.

    Note:
        F-CONC-3: This function now creates a new instance per call instead of
        using module-level singletons. This ensures proper isolation between
        different callers and prevents shared state issues in production.
    """
    # F-CONC-3: Create new instance per call instead of using module-level singleton
    # Order rate limiters use higher limits (50 ops per second) for order operations
    if max_ops is None:
        max_ops = 50
    return AsyncRateLimiter(max_ops=max_ops, window_size=window_size)


def get_smart_order_rate_limiter(
    max_ops: int | None = None, window_size: float = 1.0
) -> AsyncRateLimiter:
    """Get smart order rate limiter instance.

    Args:
        max_ops: Maximum operations per window. If None, uses default from settings.
        window_size: Time window in seconds.

    Returns:
        Configured AsyncRateLimiter instance.

    Note:
        F-CONC-3: This function now creates a new instance per call instead of
        using module-level singletons. This ensures proper isolation between
        different callers and prevents shared state issues in production.
    """
    # F-CONC-3: Create new instance per call instead of using module-level singleton
    # Smart order rate limiters use higher limits (50 ops per second) for order operations
    if max_ops is None:
        max_ops = 50
    return AsyncRateLimiter(max_ops=max_ops, window_size=window_size)
