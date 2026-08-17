"""Resilience patterns for LOATS13July2026.

Provides robust composition of circuit breaker and retry patterns with proper
type safety and error handling.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from ..loats_logging import get_logger
from .circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
    TELEGRAM_CIRCUIT_BREAKER,
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from .retry import (
    HTTP_RETRY_CONFIG,
    OPENALGO_RETRY_CONFIG,
    RetryConfig,
    _calculate_delay,
)

logger = get_logger(__name__)

T = TypeVar("T")
U = TypeVar("U")


class CircuitBreakerRetryCompositionError(Exception):
    """Raised when circuit breaker + retry composition fails in unexpected ways."""

    def __init__(self, circuit_name: str, original_error: Exception) -> None:
        self.circuit_name = circuit_name
        self.original_error = original_error
        super().__init__(
            f"Circuit breaker '{circuit_name}' composition failed: {original_error}"
        )


def circuit_breaker_retry_sync(
    circuit_breaker: CircuitBreaker,
    retry_config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Compose circuit breaker and retry patterns for synchronous functions.

    This decorator provides proper type safety and error handling for the
    composition of circuit breaker and retry patterns. It ensures that:
    1. Circuit breaker state is checked before retry attempts
    2. CircuitBreakerOpenError is not retried (fail-fast)
    3. Retry exceptions are properly counted by the circuit breaker
    4. Type annotations are preserved throughout the composition

    Args:
        circuit_breaker: The circuit breaker instance to use
        retry_config: Retry configuration (uses defaults if None)
        on_retry: Optional callback function(exception, attempt) called on each retry

    Returns:
        Decorator function with composed circuit breaker and retry behavior
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Apply retry logic manually to ensure circuit breaker sees each attempt
            # FIX-R5-PERF-2: Cache the retry config to avoid rebinding on every call
            cfg = retry_config or RetryConfig()
            last_exception: Exception | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    # Call through circuit breaker to track success/failure
                    return circuit_breaker.call(func, *args, **kwargs)

                except CircuitBreakerOpenError:
                    # Circuit breaker is open, fail fast without retry
                    # The circuit breaker has already recorded the rejection
                    raise
                except Exception as e:
                    last_exception = e

                    # Check if exception is excluded from retry
                    if isinstance(e, circuit_breaker.config.excluded_exceptions):
                        exc_name = type(e).__name__
                        msg = f"Circuit '{circuit_breaker.name}': excluded {exc_name}"
                        logger.debug(msg)
                        raise e

                    # Check if exception is retryable
                    if not isinstance(e, cfg.retryable_exceptions):
                        logger.debug(f"Non-retryable exception {type(e).__name__}: {e}")
                        raise e

                    # Check if we have more attempts
                    if attempt >= cfg.max_attempts:
                        logger.warning(
                            f"Max attempts ({cfg.max_attempts}) for {func.__name__}"
                        )
                        raise e

                    # Calculate and apply delay
                    delay = _calculate_delay(cfg, attempt)
                    logger.warning(
                        f"Retry {attempt}/{cfg.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s. Error: {e}"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(delay)

            # Should not reach here
            if last_exception:
                raise CircuitBreakerRetryCompositionError(
                    circuit_breaker.name, last_exception
                )
            raise RuntimeError("Retry logic exhausted without result or exception")

        return wrapper

    return decorator


def circuit_breaker_retry_async(
    circuit_breaker: CircuitBreaker,
    retry_config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]
]:
    """
    Compose circuit breaker and retry patterns for async functions.

    This decorator provides proper type safety and error handling for the
    composition of circuit breaker and retry patterns. It ensures that:
    1. Circuit breaker state is checked before retry attempts
    2. CircuitBreakerOpenError is not retried (fail-fast)
    3. Retry exceptions are properly counted by the circuit breaker
    4. Type annotations are preserved throughout the composition

    Args:
        circuit_breaker: The circuit breaker instance to use
        retry_config: Retry configuration (uses defaults if None)
        on_retry: Optional callback function(exception, attempt) called on each retry

    Returns:
        Decorator function with composed circuit breaker and retry behavior
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Apply retry logic manually to ensure circuit breaker sees each attempt
            # FIX-R5-PERF-2: Cache the retry config to avoid rebinding on every call
            cfg = retry_config or RetryConfig()
            last_exception: Exception | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    # Call through circuit breaker to track success/failure
                    return cast(
                        T, await circuit_breaker.call_async(func, *args, **kwargs)
                    )

                except CircuitBreakerOpenError:
                    # Circuit breaker is open, fail fast without retry
                    # The circuit breaker has already recorded the rejection
                    raise
                except Exception as e:
                    last_exception = e

                    # Check if exception is excluded from retry
                    if isinstance(e, circuit_breaker.config.excluded_exceptions):
                        exc_name = type(e).__name__
                        msg = f"Circuit '{circuit_breaker.name}': excluded {exc_name}"
                        logger.debug(msg)
                        raise

                    # Check if exception is retryable
                    if not isinstance(e, cfg.retryable_exceptions):
                        logger.debug(f"Non-retryable exception {type(e).__name__}: {e}")
                        raise

                    # Check if we have more attempts
                    if attempt >= cfg.max_attempts:
                        logger.warning(
                            f"Max attempts ({cfg.max_attempts}) for {func.__name__}"
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

            # Should not reach here
            if last_exception:
                raise CircuitBreakerRetryCompositionError(
                    circuit_breaker.name, last_exception
                )
            raise RuntimeError("Retry logic exhausted without result or exception")

        return wrapper

    return decorator


# Pre-configured compositions for common use cases

# OpenAlgo composition (3 retries, circuit opens after 3 failures)
openalgo_circuit_breaker_retry_sync = circuit_breaker_retry_sync(
    OPENALGO_CIRCUIT_BREAKER, OPENALGO_RETRY_CONFIG
)
openalgo_circuit_breaker_retry_async = circuit_breaker_retry_async(
    OPENALGO_CIRCUIT_BREAKER, OPENALGO_RETRY_CONFIG
)

# Telegram composition (3 retries, circuit opens after 5 failures)
telegram_circuit_breaker_retry_sync = circuit_breaker_retry_sync(
    TELEGRAM_CIRCUIT_BREAKER, HTTP_RETRY_CONFIG
)
telegram_circuit_breaker_retry_async = circuit_breaker_retry_async(
    TELEGRAM_CIRCUIT_BREAKER, HTTP_RETRY_CONFIG
)

__all__ = [
    "circuit_breaker_retry_sync",
    "circuit_breaker_retry_async",
    "CircuitBreakerRetryCompositionError",
    "openalgo_circuit_breaker_retry_sync",
    "openalgo_circuit_breaker_retry_async",
    "telegram_circuit_breaker_retry_sync",
    "telegram_circuit_breaker_retry_async",
]
