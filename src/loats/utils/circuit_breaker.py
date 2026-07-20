"""Circuit breaker implementation for LOATS13July2026.

Provides fault tolerance for external service calls (OpenAlgo, Telegram) by
opening the circuit after a threshold of failures and failing fast instead
of exhausting resources with repeated retry attempts.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from ..logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is tripped, requests fail immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit
        success_threshold: Number of successes in half-open state to close circuit
        timeout: Seconds to wait before transitioning from OPEN to HALF_OPEN
        excluded_exceptions: Exception types that should not count as failures
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0
    excluded_exceptions: tuple[type[Exception], ...] = ()


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # Calls rejected while circuit is open
    last_failure_time: float | None = None
    last_success_time: float | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, circuit_name: str, remaining_timeout: float) -> None:
        self.circuit_name = circuit_name
        self.remaining_timeout = remaining_timeout
        super().__init__(
            f"Circuit breaker '{circuit_name}' is open. "
            f"Retry in {remaining_timeout:.1f} seconds."
        )


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.

    The circuit breaker monitors failures and opens (rejects requests) when
    a threshold is reached, preventing cascade failures and allowing the
    downstream service time to recover.

    States:
        - CLOSED: Normal operation, all requests pass through
        - OPEN: Circuit is tripped, requests fail immediately with CircuitBreakerOpenError
        - HALF_OPEN: After timeout, allows a limited number of requests to test recovery
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker (e.g., "openalgo", "telegram")
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._state_lock = threading.Lock()
        self._stats = CircuitBreakerStats()
        self._opened_at: float | None = None
        self._half_open_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning to HALF_OPEN if timeout expired."""
        with self._state_lock:
            if self._state == CircuitState.OPEN and self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_at = time.monotonic()
                logger.info(
                    f"Circuit breaker '{self.name}' transitioning to HALF_OPEN"
                )
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get current statistics (thread-safe copy)."""
        with self._state_lock:
            return CircuitBreakerStats(
                total_calls=self._stats.total_calls,
                successful_calls=self._stats.successful_calls,
                failed_calls=self._stats.failed_calls,
                rejected_calls=self._stats.rejected_calls,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
                consecutive_failures=self._stats.consecutive_failures,
                consecutive_successes=self._stats.consecutive_successes,
            )

    def _should_attempt_reset(self) -> bool:
        """Check if timeout has elapsed to attempt reset."""
        if self._opened_at is None:
            return False
        elapsed = time.monotonic() - self._opened_at
        return elapsed >= self.config.timeout

    def _record_success(self) -> None:
        """Record a successful call."""
        now = time.monotonic()
        self._stats.successful_calls += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = now

        # In HALF_OPEN state, check if we should close the circuit
        if self._state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._opened_at = None
                self._half_open_at = None
                self._stats.consecutive_successes = 0
                logger.info(f"Circuit breaker '{self.name}' CLOSED after recovery")

    def _record_failure(self) -> None:
        """Record a failed call."""
        now = time.monotonic()
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = now

        # Check if we should open the circuit
        if self._stats.consecutive_failures >= self.config.failure_threshold:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    f"Circuit breaker '{self.name}' OPENED after "
                    f"{self._stats.consecutive_failures} consecutive failures"
                )

    def _record_rejection(self) -> None:
        """Record a rejected call (circuit was open)."""
        self._stats.rejected_calls += 1

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function with circuit breaker protection (sync version).

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Any exception from the function (after checking exclusions)
        """
        self._stats.total_calls += 1

        if self.state == CircuitState.OPEN:
            self._record_rejection()
            remaining = self.config.timeout
            if self._opened_at is not None:
                remaining = max(
                    0, self.config.timeout - (time.monotonic() - self._opened_at)
                )
            raise CircuitBreakerOpenError(self.name, remaining)

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            # Check if exception should be excluded from failure count
            if isinstance(e, self.config.excluded_exceptions):
                logger.debug(
                    f"Circuit breaker '{self.name}': excluded exception {type(e).__name__}"
                )
                raise

            self._record_failure()
            raise

    async def call_async(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """
        Execute an async function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the async function call

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Any exception from the function (after checking exclusions)
        """
        self._stats.total_calls += 1

        if self.state == CircuitState.OPEN:
            self._record_rejection()
            remaining = self.config.timeout
            if self._opened_at is not None:
                remaining = max(
                    0, self.config.timeout - (time.monotonic() - self._opened_at)
                )
            raise CircuitBreakerOpenError(self.name, remaining)

        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            # Check if exception should be excluded from failure count
            if isinstance(e, self.config.excluded_exceptions):
                logger.debug(
                    f"Circuit breaker '{self.name}': excluded exception {type(e).__name__}"
                )
                raise

            self._record_failure()
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._state_lock:
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_at = None
            self._stats.consecutive_failures = 0
            self._stats.consecutive_successes = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring/alerting."""
        with self._state_lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
                "consecutive_successes": self._stats.consecutive_successes,
                "last_failure_time": self._stats.last_failure_time,
                "last_success_time": self._stats.last_success_time,
            }


# Pre-configured circuit breakers for common services
OPENALGO_CIRCUIT_BREAKER = CircuitBreaker(
    name="openalgo",
    config=CircuitBreakerConfig(
        failure_threshold=3,  # Open after 3 consecutive failures
        success_threshold=2,  # Close after 2 successes in half-open
        timeout=60.0,  # Wait 60 seconds before testing recovery
    ),
)

TELEGRAM_CIRCUIT_BREAKER = CircuitBreaker(
    name="telegram",
    config=CircuitBreakerConfig(
        failure_threshold=5,  # More tolerant for Telegram
        success_threshold=2,
        timeout=30.0,  # Shorter timeout for alerts
    ),
)
