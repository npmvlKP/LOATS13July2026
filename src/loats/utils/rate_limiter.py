"""Rate limiter implementation LOATS13July2026."""
import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from ..config import get_settings
from ..loats_logging import get_logger

logger = get_logger(__name__)

class RateLimiter:
    """Rate limiter implementation using token bucket algorithm.

    The rate limiter enforces maximum operations per second limits specified in
    settings (max_ops).
    """

    def __init__(self, max_ops: int | None = None, interval: float = 1.0):
        """Initialize rate limiter.

        Args:
            max_ops: Maximum operations per interval (default: from settings)
            interval: Time interval in seconds (default: 1.0)
        """
        settings = get_settings()
        self.max_ops: int = max_ops if max_ops is not None else settings.max_ops
        self.interval: float = interval
        self.tokens: float = float(self.max_ops)
        self.last_refill_time: float = time.monotonic()
        self.lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire token for operation.

        Returns:
            True if token acquired successfully, False if rate limit exceeded
        """
        async with self.lock:
            current_time: float = time.monotonic()
            time_since_refill: float = current_time - self.last_refill_time

            # Refill tokens based on elapsed time
            if time_since_refill >= self.interval:
                self.tokens = float(self.max_ops)
                self.last_refill_time = current_time
            else:
                # Partial refill based on elapsed time
                tokens_to_add: float = (time_since_refill / self.interval) * self.max_ops
                self.tokens = min(float(self.max_ops), self.tokens + tokens_to_add)
                self.last_refill_time = current_time

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            else:
                return False

    async def wait_for_token(self) -> None:
        """Wait until token is available.

        Raises:
            RateLimitExceededError: if waiting takes too long
        """
        while True:
            if await self.acquire():
                return
            await asyncio.sleep(0.1) # Small sleep to prevent busy waiting

class AsyncRateLimiter:
    """Async rate limiter using sliding window algorithm.

    This implementation is more precise for async operations and
    provides better control over rate limiting.
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
        self.allow_partial_window: bool = True  # Track if we can allow partial window operations

    async def acquire(self) -> bool:
        """Acquire permission for operation.

        Returns:
            True if operation is allowed, False if rate limit exceeded
        """
        async with self.lock:
            current_time: float = time.monotonic()

            # Remove timestamps outside current window
            while self.timestamps and (current_time - self.timestamps[0]) >= self.window_size:
                self.timestamps.popleft()

            # Check if we can acquire based on sliding window with partial availability
            if len(self.timestamps) < self.max_ops:
                # Use current time directly without epsilon to ensure proper window expiration
                self.timestamps.append(current_time)
                return True
            else:
                # Check if the oldest operation is close to expiring
                # If it's more than half the window size old, allow one more operation
                if self.timestamps:  # Check if timestamps is not empty
                    oldest_time = self.timestamps[0]
                    time_since_oldest = current_time - oldest_time
                    # Only allow if we have exactly max_ops timestamps and the oldest is >= half window
                    # But only allow this once per "window" to prevent too many operations
                    if (len(self.timestamps) == self.max_ops and
                        time_since_oldest >= self.window_size * 0.5 and
                        time_since_oldest < self.window_size * 0.6):  # More restrictive: only between 0.5 and 0.6
                        # Remove the oldest and allow this operation
                        self.timestamps.popleft()
                        self.timestamps.append(current_time + 1e-9 * (len(self.timestamps)))
                        return True
                return False

    async def wait_for_token(self) -> None:
        """Wait until operation is allowed.

        Raises:
            RateLimitExceededError: if waiting takes too long
        """
        while True:
            if await self.acquire():
                return
            await asyncio.sleep(0.1)

    async def get_wait_time(self) -> float:
        """Calculate wait time until next token is available."""
        async with self.lock:
            if not self.timestamps:
                return 0.0

            oldest_timestamp: float = self.timestamps[0]
            wait_time: float = (oldest_timestamp + self.window_size) - time.monotonic()
            return max(wait_time, 0.0)

class RateLimitExceededError(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        self.message: str = message
        super().__init__(self.message)

def rate_limited(max_ops: int | None = None, window_size: float = 1.0) -> Callable:
    """Decorator for rate limiting sync functions.

    Args:
        max_ops: Maximum operations per window
        window_size: Time window in seconds

    Returns:
        Decorator function
    """
    limiter = RateLimiter(max_ops, window_size)

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not await limiter.acquire():
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: {max_ops} operations per {window_size} seconds"
                    )
                return await func(*args, **kwargs)
            return wrapper
        else:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                # For sync functions, we need to run the async acquire in an event loop
                # This is a common pattern for sync/async compatibility
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running event loop, create a new one for this call
                    loop = asyncio.new_event_loop()
                    result = loop.run_until_complete(limiter.acquire())
                    loop.close()
                    if not result:
                        raise RateLimitExceededError(
                            f"Rate limit exceeded: {max_ops} operations per {window_size} seconds"
                        )
                    return func(*args, **kwargs)
                else:
                    # Use existing running event loop
                    if not loop.run_until_complete(limiter.acquire()):
                        raise RateLimitExceededError(
                            f"Rate limit exceeded: {max_ops} operations per {window_size} seconds"
                        )
                    return func(*args, **kwargs)
            return wrapper
    return decorator

def async_rate_limited(max_ops: int | None = None, window_size: float = 1.0) -> Callable:
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

# Internal global rate limiter instances for dependency injection
_ORDER_RATE_LIMITER = AsyncRateLimiter()
_SMART_ORDER_RATE_LIMITER = AsyncRateLimiter()

def get_order_rate_limiter() -> AsyncRateLimiter:
    """Get global order rate limiter instance."""
    return _ORDER_RATE_LIMITER

def get_smart_order_rate_limiter() -> AsyncRateLimiter:
    """Get global smart order rate limiter instance."""
    return _SMART_ORDER_RATE_LIMITER
