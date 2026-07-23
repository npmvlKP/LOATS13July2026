"""Tests for utility modules: circuit_breaker and retry.

Verifies fault tolerance patterns for OpenAlgo and Telegram integrations.
"""

from __future__ import annotations

import time

import pytest

from src.loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerStats,
    CircuitState,
)
from src.loats.utils.retry import (
    DATABASE_RETRY_CONFIG,
    HTTP_RETRY_CONFIG,
    OPENALGO_RETRY_CONFIG,
    RetryConfig,
    _calculate_delay,
    retry_async,
    retry_sync,
)

# =============================================================================
# Circuit Breaker Tests
# =============================================================================


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 30.0
        assert config.excluded_exceptions == ()

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout=60.0,
            excluded_exceptions=(ValueError,),
        )
        assert config.failure_threshold == 3
        assert config.success_threshold == 1
        assert config.timeout == 60.0
        assert config.excluded_exceptions == (ValueError,)


class TestCircuitBreakerStats:
    """Tests for CircuitBreakerStats dataclass."""

    def test_default_stats(self) -> None:
        """Test default statistics values."""
        stats = CircuitBreakerStats()
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0
        assert stats.last_failure_time is None
        assert stats.last_success_time is None
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0


class TestCircuitBreakerOpenError:
    """Tests for CircuitBreakerOpenError exception."""

    def test_error_message(self) -> None:
        """Test exception message formatting."""
        error = CircuitBreakerOpenError("openalgo", 25.5)
        assert error.circuit_name == "openalgo"
        assert error.remaining_timeout == 25.5
        assert "openalgo" in str(error)
        assert "25.5" in str(error)


class TestCircuitBreaker:
    """Tests for CircuitBreaker implementation."""

    def test_initial_state_closed(self) -> None:
        """Test circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_successful_call_updates_stats(self) -> None:
        """Test successful call increments stats."""
        cb = CircuitBreaker("test")
        result = cb.call(lambda: 42)
        assert result == 42
        stats = cb.stats
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        assert stats.consecutive_failures == 0

    def test_failed_call_opens_circuit_after_threshold(self) -> None:
        """Test circuit opens after consecutive failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config=config)

        def fail() -> None:
            raise RuntimeError("Test error")

        # Fail 2 times - should still be closed
        with pytest.raises(RuntimeError):
            cb.call(fail)
        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.CLOSED

        # Third failure - should open
        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_rejects_calls(self) -> None:
        """Test rejected calls when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config=config)

        def fail() -> None:
            raise RuntimeError("Test error")

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.OPEN

        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(lambda: 42)
        assert exc_info.value.circuit_name == "test"

        # Check rejection was recorded
        stats = cb.stats
        assert stats.rejected_calls == 1

    def test_excluded_exception_not_counted_as_failure(self) -> None:
        """Test excluded exceptions don't trigger circuit open."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            excluded_exceptions=(ValueError,),
        )
        cb = CircuitBreaker("test", config=config)

        def raise_value_error() -> None:
            raise ValueError("Excluded")

        # Should not open circuit for excluded exception
        with pytest.raises(ValueError):
            cb.call(raise_value_error)
        with pytest.raises(ValueError):
            cb.call(raise_value_error)
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_timeout(self) -> None:
        """Test circuit transitions to HALF_OPEN after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout=0.1,  # 100ms timeout
        )
        cb = CircuitBreaker("test", config=config)

        def fail() -> None:
            raise RuntimeError("Test error")

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        # Access state to trigger transition check
        state = cb.state
        assert state == CircuitState.HALF_OPEN

    def test_half_open_closes_after_success_threshold(self) -> None:
        """Test circuit closes after successes in half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout=0.05,
        )
        cb = CircuitBreaker("test", config=config)

        # Open circuit with a proper error
        def fail_once() -> None:
            raise RuntimeError("Test error")

        with pytest.raises(RuntimeError):
            cb.call(fail_once)

        # Wait for half-open
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Successful calls in half-open
        cb.call(lambda: 42)
        assert cb.state == CircuitState.HALF_OPEN
        cb.call(lambda: 43)
        assert cb.state == CircuitState.CLOSED

    def test_get_status_returns_dict(self) -> None:
        """Test get_status returns expected dictionary structure."""
        cb = CircuitBreaker("test")
        cb.call(lambda: 42)

        status = cb.get_status()
        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["failure_threshold"] == 5
        assert status["success_threshold"] == 2
        assert status["total_calls"] == 1
        assert status["successful_calls"] == 1

    def test_reset_clears_state(self) -> None:
        """Test reset returns circuit to closed state."""
        cb = CircuitBreaker("test")

        # Open circuit with a proper error
        def fail_once() -> None:
            raise RuntimeError("Test error")

        with pytest.raises(RuntimeError):
            cb.call(fail_once)
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        stats = cb.stats
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0

    def test_call_with_args_and_kwargs(self) -> None:
        """Test function calls with positional and keyword arguments."""
        cb = CircuitBreaker("test")

        def func(a: int, b: int, c: int = 10) -> int:
            return a + b + c

        result = cb.call(func, 1, 2, c=3)
        assert result == 6


class TestCircuitBreakerAsync:
    """Tests for async circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_async_successful_call(self) -> None:
        """Test successful async call."""
        cb = CircuitBreaker("test")

        async def async_func() -> str:
            return "async result"

        result = await cb.call_async(async_func)
        assert result == "async result"
        stats = cb.stats
        assert stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_async_failed_call_opens_circuit(self) -> None:
        """Test async failure opens circuit."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config=config)

        async def async_fail() -> None:
            raise RuntimeError("Async error")

        with pytest.raises(RuntimeError):
            await cb.call_async(async_fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_open_circuit_rejects(self) -> None:
        """Test async rejected calls when circuit open."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config=config)

        async def async_fail() -> None:
            raise RuntimeError("Error")

        async def async_success() -> str:
            return "success"

        # Open circuit
        with pytest.raises(RuntimeError):
            await cb.call_async(async_fail)

        # Should reject
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(async_success)

        stats = cb.stats
        assert stats.rejected_calls == 1


# =============================================================================
# Retry Tests
# =============================================================================


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.jitter_factor == 0.2

    def test_preset_configs(self) -> None:
        """Test pre-configured retry presets."""
        assert OPENALGO_RETRY_CONFIG.max_attempts == 3
        assert OPENALGO_RETRY_CONFIG.max_delay == 10.0

        assert HTTP_RETRY_CONFIG.max_attempts == 5
        assert HTTP_RETRY_CONFIG.max_delay == 30.0

        assert DATABASE_RETRY_CONFIG.max_attempts == 3
        assert DATABASE_RETRY_CONFIG.max_delay == 5.0


class TestCalculateDelay:
    """Tests for delay calculation with exponential backoff."""

    def test_exponential_backoff(self) -> None:
        """Test exponential backoff calculation."""
        config = RetryConfig(jitter=False)
        # Attempt 1: base_delay * 2^0 = 1.0
        # Attempt 2: base_delay * 2^1 = 2.0
        # Attempt 3: base_delay * 2^2 = 4.0
        assert _calculate_delay(config, 1) == 1.0
        assert _calculate_delay(config, 2) == 2.0
        assert _calculate_delay(config, 3) == 4.0

    def test_max_delay_capped(self) -> None:
        """Test delay is capped at max_delay."""
        config = RetryConfig(base_delay=10.0, max_delay=15.0, jitter=False)
        # Would be 40.0, but capped at 15.0
        delay = _calculate_delay(config, 3)
        assert delay == 15.0

    def test_jitter_adds_randomness(self) -> None:
        """Test jitter adds variation to delays."""
        config = RetryConfig(jitter=True, jitter_factor=0.2)
        delays = [_calculate_delay(config, 1) for _ in range(10)]
        # With jitter, delays should vary
        assert len(set(delays)) > 1
        # Delays should still be reasonable (around base_delay)
        for d in delays:
            assert 0.5 <= d <= 1.5  # 1.0 ± 0.5 (accounting for factor)

    def test_minimum_delay_with_jitter(self) -> None:
        """Test minimum delay enforced even with negative jitter."""
        config = RetryConfig(jitter=True, jitter_factor=1.0, base_delay=0.1)
        delay = _calculate_delay(config, 1)
        assert delay >= 0.1  # Minimum enforced


class TestRetrySync:
    """Tests for synchronous retry decorator."""

    def test_successful_call_no_retry(self) -> None:
        """Test successful call doesn't trigger retry."""
        call_count = 0

        @retry_sync()
        def success_func() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        result = success_func()
        assert result == 42
        assert call_count == 1

    def test_retries_on_failure(self) -> None:
        """Test retry on transient failure."""
        call_count = 0

        config = RetryConfig(max_attempts=3)

        @retry_sync(config=config)
        def flaky_func() -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient")
            return 100

        result = flaky_func()
        assert result == 100
        assert call_count == 3

    def test_max_attempts_exceeded(self) -> None:
        """Test exception raised after max attempts."""
        call_count = 0

        config = RetryConfig(max_attempts=2)

        @retry_sync(config=config)
        def always_fail() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            always_fail()
        assert call_count == 2

    def test_non_retryable_exception_raises_immediately(self) -> None:
        """Test non-retryable exceptions raise immediately."""
        call_count = 0

        config = RetryConfig(retryable_exceptions=(ConnectionError,))

        @retry_sync(config=config)
        def non_retryable_fail() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            non_retryable_fail()
        assert call_count == 1

    def test_excluded_exception_not_retried(self) -> None:
        """Test excluded exceptions don't trigger retry."""
        call_count = 0

        config = RetryConfig(excluded_exceptions=(ValueError,))

        @retry_sync(config=config)
        def excluded_fail() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded")

        with pytest.raises(ValueError):
            excluded_fail()
        assert call_count == 1

    def test_on_retry_callback(self) -> None:
        """Test on_retry callback is called on each retry."""
        retry_info: list[tuple[Exception, int]] = []

        def on_retry(exc: Exception, attempt: int) -> None:
            retry_info.append((exc, attempt))

        @retry_sync(on_retry=on_retry)
        def fail_twice() -> int:
            if len(retry_info) < 2:
                raise ConnectionError("Retry")
            return 42

        result = fail_twice()
        assert result == 42
        assert len(retry_info) == 2
        assert retry_info[0][1] == 1
        assert retry_info[1][1] == 2


class TestRetryAsync:
    """Tests for async retry decorator."""

    @pytest.mark.asyncio
    async def test_async_success_no_retry(self) -> None:
        """Test successful async call doesn't retry."""
        call_count = 0

        @retry_async()
        async def async_success() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        result = await async_success()
        assert result == 42
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retries_on_failure(self) -> None:
        """Test async retry on transient failure."""
        call_count = 0

        config = RetryConfig(max_attempts=3)

        @retry_async(config=config)
        async def async_flaky() -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient")
            return 100

        result = await async_flaky()
        assert result == 100
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_attempts_exceeded(self) -> None:
        """Test async exception after max attempts."""
        call_count = 0

        config = RetryConfig(max_attempts=2)

        @retry_async(config=config)
        async def async_always_fail() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await async_always_fail()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_excluded_exception_raises_immediately(self) -> None:
        """Test async excluded exceptions don't retry."""
        call_count = 0

        config = RetryConfig(excluded_exceptions=(ValueError,))

        @retry_async(config=config)
        async def async_excluded_fail() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded")

        with pytest.raises(ValueError):
            await async_excluded_fail()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_on_retry_callback(self) -> None:
        """Test async on_retry callback is called."""
        retry_info: list[tuple[Exception, int]] = []

        def on_retry(exc: Exception, attempt: int) -> None:
            retry_info.append((exc, attempt))

        @retry_async(on_retry=on_retry)
        async def async_fail_twice() -> int:
            if len(retry_info) < 2:
                raise ConnectionError("Retry")
            return 42

        result = await async_fail_twice()
        assert result == 42
        assert len(retry_info) == 2
