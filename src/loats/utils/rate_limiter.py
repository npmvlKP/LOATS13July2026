"""Rate limiter implementation LOATS13July2026."""
import asyncio
import time
from collections import deque
from typing import Any, Callable, Coroutine, Optional

from ..config import get_settings
from ..loats_logging import get_logger

logger = get_logger(__name__)

class RateLimiter:
    """Rate limiter implementation using token bucket algorithm.
    
    The rate limiter enforces maximum operations per second limits specified in
    settings (max_ops).
    """

    def __init__(self, max_ops: Optional[int] = None, interval: float = 1.0):
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

    def __init__(self, max_ops: Optional[int] = None, window_size: float = 1.0):
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

    async def acquire(self) -> bool:
        """Acquire permission for operation.
        
        Returns:
            True if operation is allowed, False if rate limit exceeded
        """
        async with self.lock:
            current_time: float = time.monotonic()
            
            # Remove timestamps outside current window
            while self.timestamps and (current_time - self.timestamps[0]) > self.window_size:
                self.timestamps.popleft()
            
            if len(self.timestamps) < self.max_ops:
                self.timestamps.append(current_time)
                return True
            else:
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

def rate_limited(max_ops: Optional[int] = None, window_size: float = 1.0) -> Callable:
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

def async_rate_limited(max_ops: Optional[int] = None, window_size: float = 1.0) -> Callable:
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