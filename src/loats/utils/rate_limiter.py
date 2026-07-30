"""Rate limiter implementation for LOATS13July2026."""

import asyncio
import time
from collections import deque
from typing import Any, Callable, Coroutine

from ..config import settings
from ..loats_logging import get_logger

logger = get_logger(__name__)

class RateLimiter:
    """Rate limiter implementation using token bucket algorithm.

    This rate limiter enforces the maximum orders per second limit
    specified in the settings (max_ops).
    """

    def __init__(self, max_ops: int = None, interval: float = 1.0) -> None:
        """Initialize rate limiter.

        Args:
            max_ops: Maximum operations per interval (default: from settings)
            interval: Time interval in seconds (default: 1.0)
        """
        self.max_ops = max_ops if max_ops is not None else settings.max_ops
        self.interval = interval
        self.tokens = self.max_ops
        self.last_refill_time = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire a token for an operation.

        Returns:
            True if token acquired successfully, False if rate limit exceeded
        """
        async with self.lock:
            current_time = time.monotonic()
            time_since_refill = current_time - self.last_refill_time

            # Refill tokens based on elapsed time
            if time_since_refill >= self.interval:
                self.tokens = self.max_ops
                self.last_refill_time = current_time
            else:
                # Partial refill based on elapsed time
                tokens_to_add = (time_since_refill / self.interval) * self.max_ops
                self.tokens = min(self.max_ops, self.tokens + tokens_to_add)
                self.last_refill_time = current_time

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            else:
                return False

    async def wait_for_token(self) -> None:
        """Wait until a token is available.

        Raises:
            RateLimitExceededError: If waiting would take too long
        """
        while True:
            if await self.acquire():
                return
            await asyncio.sleep(0.1)  # Small sleep to prevent busy waiting

class AsyncRateLimiter:
    """Async rate limiter using sliding window algorithm.

    This implementation is more precise for async operations and
    provides better control over rate limiting.
    """

    def __init__(self, max_ops: int = None, window_size: float = 1.0) -> None:
        """Initialize async rate limiter.

        Args:
            max_ops: Maximum operations per window (default: from settings)
            window_size: Time window in seconds (default: 1.0)
        """
        self.max_ops = max_ops if max_ops is not None else settings.max_ops
        self.window_size = window_size
        self.timestamps = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire permission for an operation.

        Returns:
            True if operation allowed, False if rate limit exceeded
        """
        async with self.lock:
            current_time = time.monotonic()

            # Remove timestamps outside the current window
            while self.timestamps and current_time - self.timestamps[0] > self.window_size:
                self.timestamps.popleft()

            if len(self.timestamps) < self.max_ops:
                self.timestamps.append(current_time)
                return True
            else:
                return False

    async def wait_for_token(self) -> None:
        """Wait until operation is allowed.

        Raises:
            RateLimitExceededError: If waiting would take too long
        """
        while True:
            if await self.acquire():
                return

            # Calculate when the next token will be available
            async with self.lock:
                if self.timestamps:
                    oldest_timestamp = self.timestamps[0]
                    wait_time = (oldest_timestamp + self.window_size) - time.monotonic()
                    if wait_time > 0:
                        await asyncio.sleep(min(wait_time, 0.1))
                else:
                    await asyncio.sleep(0.1)

class RateLimitExceededError(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        self.message = message
        super().__init__(self.message)

def rate_limited(max_ops: int = None, window_size: float = 1.0) -> Callable:
    """Decorator for rate limiting sync functions.

    Args:
        max_ops: Maximum operations per window
        window_size: Time window in seconds

    Returns:
        Decorator function
    """
    limiter = RateLimiter(max_ops, window_size)

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not await limiter.acquire():
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {max_ops} operations per {window_size} seconds"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def async_rate_limited(max_ops: int = None, window_size: float = 1.0) -> Callable:
    """Decorator for rate limiting async functions.

    Args:
        max_ops: Maximum operations per window
        window_size: Time window in seconds

    Returns:
        Decorator function
    """
    limiter = AsyncRateLimiter(max_ops, window_size)

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not await limiter.acquire():
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {max_ops} operations per {window_size} seconds"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Global rate limiter instances
ORDER_RATE_LIMITER = AsyncRateLimiter()
SMART_ORDER_RATE_LIMITER = AsyncRateLimiter()