"""Test resilience patterns for LOATS13July2026."""

import asyncio
import time
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest

from loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from loats.utils.resilience import (
    circuit_breaker_retry_async,
    circuit_breaker_retry_sync,
)
from loats.utils.retry import RetryConfig


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
        cb._state = cb._state.OPEN  # type: ignore[assignment]
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
                failure_threshold=3, excluded_exceptions=(ValueError,)
            ),
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

        with pytest.raises(ValueError):
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
        cb._state = cb._state.OPEN  # type: ignore[assignment]
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
                failure_threshold=3, excluded_exceptions=(ValueError,)
            ),
        )
        retry_config = RetryConfig(max_attempts=3)

        call_count = 0

        @circuit_breaker_retry_async(cb, retry_config)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded error")

        with pytest.raises(ValueError) as exc_info:
            await test_func()

        # Should contain the original ValueError
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
        with patch.object(cb, "call") as mock_call:
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
        with patch.object(cb, "call_async") as mock_call:
            mock_call.side_effect = RuntimeError("Unexpected circuit breaker error")

            @circuit_breaker_retry_async(cb, retry_config)
            async def test_func():
                return "should not reach"

            with pytest.raises(RuntimeError) as exc_info:
                await test_func()

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


class TestChainWallClockDeadline:
    """17Oct wave: cap the whole breaker+retry chain with a wall deadline.

    Regression shape (17Oct 12:45 IST outage): a black-holing listener
    (accepts TCP, never answers) made every attempt burn the full per-call
    timeout, so 3 retries x 30 s pinned fetch legs at ~95 s each, the
    trading cycle went dormant for ~603 s, and the PTB update queue sat
    blocked behind a /resume handler awaiting its Telegram confirmation
    for 512 s. The deadline caps the CHAIN while fast failures still
    retry within the remaining budget.
    """

    def _cb(self) -> CircuitBreaker:
        return CircuitBreaker(
            "deadline-test", CircuitBreakerConfig(failure_threshold=100)
        )

    async def test_deadline_caps_slow_attempt_chain(self) -> None:
        cb = self._cb()
        started = time.monotonic()

        @circuit_breaker_retry_async(
            cb, RetryConfig(max_attempts=3, base_delay=0.01), total_deadline=0.3
        )
        async def slow() -> str:
            await asyncio.sleep(5)
            return "never"

        with pytest.raises(TimeoutError):
            await slow()
        assert time.monotonic() - started < 3.0

    async def test_fast_failures_retry_within_deadline_then_succeed(self) -> None:
        cb = self._cb()
        calls = {"n": 0}

        @circuit_breaker_retry_async(
            cb, RetryConfig(max_attempts=3, base_delay=0.01), total_deadline=5.0
        )
        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("transient")
            return "ok"

        assert await flaky() == "ok"
        assert calls["n"] == 3

    async def test_deadline_exhaustion_raises_last_exception(self) -> None:
        cb = self._cb()

        @circuit_breaker_retry_async(
            cb,
            RetryConfig(max_attempts=50, base_delay=0.01),
            total_deadline=0.4,
        )
        async def always_fails() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await always_fails()

    async def test_no_deadline_preserves_legacy_behavior(self) -> None:
        cb = self._cb()

        @circuit_breaker_retry_async(cb, RetryConfig(max_attempts=2, base_delay=0.01))
        async def fine() -> str:
            return "ok"

        assert await fine() == "ok"

    async def test_circuit_open_still_fails_fast_under_deadline(self) -> None:
        from loats.utils.circuit_breaker import CircuitBreakerOpenError

        cb = CircuitBreaker("open-deadline", CircuitBreakerConfig(failure_threshold=1))

        @circuit_breaker_retry_async(
            cb, RetryConfig(max_attempts=2, base_delay=0.01), total_deadline=5.0
        )
        async def always_fails() -> str:
            raise ValueError("trip")

        # Attempt 1 fails through the breaker (threshold 1 -> circuit opens);
        # attempt 2 must fail fast with CircuitBreakerOpenError, deadline or not.
        with pytest.raises(CircuitBreakerOpenError):
            await always_fails()

    async def test_preconfigured_compositions_carry_deadline(self) -> None:
        from loats.utils.resilience import (
            _request_timeout_deadline,
            openalgo_circuit_breaker_retry_async,
            telegram_circuit_breaker_retry_async,
        )

        async def _probe() -> str:
            return "ok"

        for composition in (
            openalgo_circuit_breaker_retry_async,
            telegram_circuit_breaker_retry_async,
        ):
            # The pre-configured instances are DECORATORS; the deadline is
            # bound onto each wrapper they produce.
            wrapper = composition(_probe)
            bound = getattr(wrapper, "total_deadline", None)
            assert callable(bound), "pre-configured composition lost its deadline"
            deadline_value: float = cast("Callable[[], float]", bound)()
            assert deadline_value > 0
        assert _request_timeout_deadline() > 0
