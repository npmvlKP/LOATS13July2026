"""Test resilience patterns for LOATS13July2026."""

import time
from unittest.mock import patch

import pytest

from src.loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from src.loats.utils.resilience import (
    CircuitBreakerRetryCompositionError,
    circuit_breaker_retry_async,
    circuit_breaker_retry_sync,
)
from src.loats.utils.retry import RetryConfig


class TestCircuitBreakerRetryComposition:
    """Test circuit breaker + retry composition patterns."""

    def test_sync_successful_call(self):
        """Test successful synchronous call with composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"
        stats = cb.stats
        assert stats.successful_calls == 1
        assert stats.failed_calls == 0

    def test_sync_failed_call_opens_circuit(self):
        """Test failed synchronous call that opens circuit."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        retry_config = RetryConfig(max_attempts=2)

        call_count = 0

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # Will fail enough times to open circuit
                raise ValueError("Test error")
            return "success"

        with pytest.raises(ValueError):
            test_func()

        # Circuit should be open now
        assert cb.state.value == "open"

        # Subsequent calls should fail fast
        with pytest.raises(CircuitBreakerOpenError):
            test_func()

    def test_sync_circuit_breaker_open_fails_fast(self):
        """Test that open circuit fails fast without retry."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        retry_config = RetryConfig(max_attempts=3)

        # Manually open the circuit
        cb._state = cb._state.OPEN  # type: ignore
        # Set opened_at to a future time to prevent transition to HALF_OPEN
        cb._opened_at = time.monotonic() + 3600  # 1 hour in the future

        call_count = 0

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Should not be called")

        # Should fail immediately without retrying
        with pytest.raises(CircuitBreakerOpenError):
            test_func()

        # Function should not have been called
        assert call_count == 0

    def test_sync_excluded_exception_not_retried(self):
        """Test that excluded exceptions are not retried."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=3,
                excluded_exceptions=(ValueError,)
            )
        )
        retry_config = RetryConfig(max_attempts=3)

        call_count = 0

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded error")

        with pytest.raises(ValueError):
            test_func()

        # Should only be called once since ValueError is excluded
        assert call_count == 1

    async def test_async_successful_call(self):
        """Test successful async call with composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"
        stats = cb.stats
        assert stats.successful_calls == 1
        assert stats.failed_calls == 0

    async def test_async_failed_call_opens_circuit(self):
        """Test failed async call that opens circuit."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        retry_config = RetryConfig(max_attempts=2)

        call_count = 0

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # Will fail enough times to open circuit
                raise ValueError("Test error")
            return "success"

        with pytest.raises(CircuitBreakerRetryCompositionError):
            await test_func()

        # Circuit should be open now
        assert cb.state.value == "open"

        # Subsequent calls should fail fast
        with pytest.raises(CircuitBreakerOpenError):
            await test_func()

    async def test_async_circuit_breaker_open_fails_fast(self):
        """Test that open circuit fails fast without retry."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
        retry_config = RetryConfig(max_attempts=3)

        # Manually open the circuit
        cb._state = cb._state.OPEN  # type: ignore
        cb._opened_at = time.monotonic() + 3600  # 1 hour in the future

        call_count = 0

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Should not be called")

        # Should fail immediately without retrying
        with pytest.raises(CircuitBreakerOpenError):
            await test_func()

        # Function should not have been called
        assert call_count == 0

    async def test_async_excluded_exception_not_retried(self):
        """Test that excluded exceptions are not retried (but get wrapped in composition error)."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=3,
                excluded_exceptions=(ValueError,)
            )
        )
        retry_config = RetryConfig(max_attempts=3)

        call_count = 0

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded error")

        with pytest.raises(CircuitBreakerRetryCompositionError) as exc_info:
            await test_func()

        # Should contain the original ValueError
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert "Excluded error" in str(exc_info.value)

        # Should only be called once since ValueError is excluded from retry
        assert call_count == 1

    def test_sync_retry_then_circuit_breaker_success(self):
        """Test retry succeeds after initial failures, circuit breaker stays closed."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=3)

        call_count = 0

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:  # Fail once, succeed on retry
                raise ValueError("Temporary error")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2  # Called twice (once failed, once succeeded)

        # Circuit breaker should still be closed
        assert cb.state.value == "closed"
        stats = cb.stats
        assert stats.successful_calls == 1
        assert stats.failed_calls == 1  # One failure recorded

    async def test_async_retry_then_circuit_breaker_success(self):
        """Test async retry succeeds after initial failures, circuit breaker stays closed."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=3)

        call_count = 0

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:  # Fail once, succeed on retry
                raise ValueError("Temporary error")
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 2  # Called twice (once failed, once succeeded)

        # Circuit breaker should still be closed
        assert cb.state.value == "closed"
        stats = cb.stats
        assert stats.successful_calls == 1
        assert stats.failed_calls == 1  # One failure recorded

    def test_sync_type_preservation(self):
        """Test that type annotations are preserved in sync composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func() -> str:
            return "hello"

        # Should return correct type
        result = test_func()
        assert isinstance(result, str)
        assert result == "hello"

    async def test_async_type_preservation(self):
        """Test that type annotations are preserved in async composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func() -> str:
            return "hello"

        # Should return correct type
        result = await test_func()
        assert isinstance(result, str)
        assert result == "hello"

    def test_sync_composition_error_handling(self):
        """Test composition error handling for unexpected failures."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        # Mock the circuit breaker to raise an unexpected error
        with patch.object(cb, 'call') as mock_call:
            mock_call.side_effect = RuntimeError("Unexpected circuit breaker error")

            @circuit_breaker_retry_sync(cb, retry_config)
            def test_func():
                return "should not reach"

            with pytest.raises(RuntimeError):
                test_func()

    async def test_async_composition_error_handling(self):
        """Test async composition error handling for unexpected failures."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        # Mock the circuit breaker to raise an unexpected error
        with patch.object(cb, 'call_async') as mock_call:
            mock_call.side_effect = RuntimeError("Unexpected circuit breaker error")

            @circuit_breaker_retry_async(cb, retry_config)
            async def test_func():
                return "should not reach"

            with pytest.raises(CircuitBreakerRetryCompositionError) as exc_info:
                await test_func()

            assert "test" in str(exc_info.value)
            assert "Unexpected circuit breaker error" in str(exc_info.value)

    def test_sync_stats_tracking(self):
        """Test that stats are properly tracked in sync composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func():
            return "success"

        # Make multiple successful calls
        for _ in range(3):
            test_func()

        stats = cb.stats
        assert stats.total_calls == 3
        assert stats.successful_calls == 3
        assert stats.failed_calls == 0

    async def test_async_stats_tracking(self):
        """Test that stats are properly tracked in async composition."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            return "success"

        # Make multiple successful calls
        for _ in range(3):
            await test_func()

        stats = cb.stats
        assert stats.total_calls == 3
        assert stats.successful_calls == 3
        assert stats.failed_calls == 0

    def test_sync_with_args_and_kwargs(self):
        """Test composition with arguments and keyword arguments."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_sync(cb, retry_config)
        def test_func(a: int, b: str, *, c: float = 1.0) -> str:
            return f"{a}-{b}-{c}"

        result = test_func(1, "test", c=2.5)
        assert result == "1-test-2.5"

    async def test_async_with_args_and_kwargs(self):
        """Test async composition with arguments and keyword arguments."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        retry_config = RetryConfig(max_attempts=2)

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func(a: int, b: str, *, c: float = 1.0) -> str:
            return f"{a}-{b}-{c}"

        result = await test_func(1, "test", c=2.5)
        assert result == "1-test-2.5"
