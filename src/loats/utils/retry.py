"""Retry utility with exponential backoff for LOATS13July2026.

Provides configurable retry logic for transient failures with:
- Exponential backoff between retries
- Jitter to prevent thundering herd
- Configurable retry conditions
- Async support
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from ..logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of attempts (including the first)
        base_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        jitter_factor: Factor for jitter (0.0 to 1.0, fraction of delay)
        retryable_exceptions: Tuple of exception types that should trigger retry
        excluded_exceptions: Tuple of exception types that should NOT trigger retry
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.2
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    excluded_exceptions: tuple[type[Exception], ...] = ()


def _calculate_delay(config: RetryConfig, attempt: int) -> float:
    """Calculate delay for a specific attempt with exponential backoff and jitter.

    Args:
        config: Retry configuration
        attempt: Current attempt number (1-indexed)

    Returns:
        Delay in seconds before next retry
    """
    # Exponential backoff: base_delay * (exponential_base ^ (attempt - 1))
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))

    # Cap at max_delay
    delay = min(delay, config.max_delay)

    # Add jitter to prevent thundering herd
    if config.jitter:
        jitter_range = delay * config.jitter_factor
        delay = delay + random.uniform(-jitter_range, jitter_range)  # nosec: B311
        delay = max(0.1, delay)  # Ensure minimum delay

    return delay


def retry_sync(
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for adding retry logic to synchronous functions.

    Args:
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback function(exception, attempt) called on each retry

    Returns:
        Decorated function with retry behavior

    Example:
        @retry_sync(config=RetryConfig(max_attempts=5, base_delay=2.0))
        def fetch_data():
            return http_client.get("/api/data")
    """
    cfg = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if exception is excluded from retry
                    if isinstance(e, cfg.excluded_exceptions):
                        logger.debug(f"Retry excluded for {type(e).__name__}: {e}")
                        raise

                    # Check if exception is retryable
                    if not isinstance(e, cfg.retryable_exceptions):
                        logger.debug(f"Non-retryable exception {type(e).__name__}: {e}")
                        raise

                    # Check if we have more attempts
                    if attempt >= cfg.max_attempts:
                        logger.warning(
                            f"Max retry attempts ({cfg.max_attempts}) reached for {func.__name__}"
                        )
                        raise

                    # Calculate and apply delay
                    delay = _calculate_delay(cfg, attempt)
                    logger.warning(
                        f"Retry {attempt}/{cfg.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s. Error: {e}"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic exhausted without result or exception")

        return wrapper

    return decorator


def retry_async(
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for adding retry logic to async functions.

    Args:
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback function(exception, attempt) called on each retry

    Returns:
        Decorated async function with retry behavior

    Example:
        @retry_async(config=RetryConfig(max_attempts=5, base_delay=2.0))
        async def fetch_data():
            return await http_client.get("/api/data")
    """
    cfg = config or RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if exception is excluded from retry
                    if isinstance(e, cfg.excluded_exceptions):
                        logger.debug(f"Retry excluded for {type(e).__name__}: {e}")
                        raise

                    # Check if exception is retryable
                    if not isinstance(e, cfg.retryable_exceptions):
                        logger.debug(f"Non-retryable exception {type(e).__name__}: {e}")
                        raise

                    # Check if we have more attempts
                    if attempt >= cfg.max_attempts:
                        logger.warning(
                            f"Max retry attempts ({cfg.max_attempts}) reached for {func.__name__}"
                        )
                        raise

                    # Calculate and apply delay
                    delay = _calculate_delay(cfg, attempt)
                    logger.warning(
                        f"Retry {attempt}/{cfg.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s. Error: {e}"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic exhausted without result or exception")

        return wrapper

    return decorator


# Pre-configured retry configs for common use cases
OPENALGO_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    exponential_base=2.0,
    jitter=True,
    jitter_factor=0.1,
)

HTTP_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    jitter_factor=0.15,
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=5.0,
    exponential_base=2.0,
    jitter=True,
    jitter_factor=0.1,
)
