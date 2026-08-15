"""Edge-branch tests for loats.utils.resilience composition decorators."""

from __future__ import annotations

import pytest

from loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)
from loats.utils.resilience import (
    CircuitBreakerRetryCompositionError,
    circuit_breaker_retry_async,
    circuit_breaker_retry_sync,
)
from loats.utils.retry import RetryConfig


def _breaker(**kwargs: object) -> CircuitBreaker:
    cfg = CircuitBreakerConfig(failure_threshold=50, **kwargs)  # type: ignore[arg-type]
    return CircuitBreaker("test-cb", cfg)


class TestCircuitBreakerRetrySync:
    def test_non_retryable_exception_propagates(self) -> None:
        cb = _breaker()
        cfg = RetryConfig(
            max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )

        @circuit_breaker_retry_sync(cb, cfg)
        def boom() -> int:
            raise KeyError("nope")

        with pytest.raises(KeyError):
            boom()

    def test_on_retry_callback_invoked(self) -> None:
        cb = _breaker()
        calls: list[tuple[str, int]] = []
        cfg = RetryConfig(
            max_attempts=2, base_delay=0.01, retryable_exceptions=(ValueError,)
        )

        @circuit_breaker_retry_sync(
            cb, cfg, on_retry=lambda e, a: calls.append((str(e), a))
        )
        def flaky() -> str:
            if len(calls) == 0:
                raise ValueError("first fails")
            return "ok"

        assert flaky() == "ok"
        assert calls == [("first fails", 1)]

    def test_open_circuit_fails_fast(self) -> None:
        cb = _breaker()
        cb._state = CircuitState.OPEN

        @circuit_breaker_retry_sync(cb, RetryConfig(max_attempts=3, base_delay=0.01))
        def fn() -> int:
            return 1

        with pytest.raises(CircuitBreakerOpenError):
            fn()


class TestCircuitBreakerRetryAsync:
    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates(self) -> None:
        cb = _breaker()
        cfg = RetryConfig(
            max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )

        @circuit_breaker_retry_async(cb, cfg)
        async def boom() -> int:
            raise KeyError("nope")

        with pytest.raises(KeyError):
            await boom()

    @pytest.mark.asyncio
    async def test_on_retry_callback_invoked(self) -> None:
        cb = _breaker()
        calls: list[tuple[str, int]] = []
        cfg = RetryConfig(
            max_attempts=2, base_delay=0.01, retryable_exceptions=(ValueError,)
        )

        @circuit_breaker_retry_async(
            cb, cfg, on_retry=lambda e, a: calls.append((str(e), a))
        )
        async def flaky() -> str:
            if len(calls) == 0:
                raise ValueError("first fails")
            return "ok"

        assert await flaky() == "ok"
        assert calls == [("first fails", 1)]


class TestCompositionError:
    def test_error_carries_context(self) -> None:
        original = ValueError("root")
        err = CircuitBreakerRetryCompositionError("cb-x", original)
        assert err.circuit_name == "cb-x"
        assert err.original_error is original
        assert "cb-x" in str(err)
        assert "root" in str(err)
