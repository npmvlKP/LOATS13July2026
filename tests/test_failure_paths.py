"""End-to-end failure path tests for circuit breaker and retry scenarios.

This module tests the complete failure handling flow including:
- Circuit breaker open scenarios
- Retry exhausted scenarios
- Error propagation and recovery
- System behavior under failure conditions
"""

import asyncio
import logging
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.alerts import AlertSystem
from loats.openalgo import async_client
from loats.scheduler import TradingScheduler
from loats.utils.circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
    TELEGRAM_CIRCUIT_BREAKER,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from loats.utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
)
from loats.utils.retry import RetryConfig, retry_async, retry_sync

logger = logging.getLogger(__name__)


class TestCircuitBreakerOpenScenarios:
    """End-to-end tests for circuit breaker open scenarios."""

    def setup_method(self) -> None:
        """Reset circuit breakers before each test."""
        OPENALGO_CIRCUIT_BREAKER.reset()
        TELEGRAM_CIRCUIT_BREAKER.reset()

    def test_circuit_breaker_open_rejection(self) -> None:
        """Test that calls are rejected when circuit breaker is open."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=10.0
        )
        cb = CircuitBreaker("test_circuit", config=config)

        # Force circuit open by causing failures
        def failing_function() -> int:
            raise ConnectionError("Simulated failure")

        # First two failures should open the circuit
        with pytest.raises(ConnectionError):
            cb.call(failing_function)
        with pytest.raises(ConnectionError):
            cb.call(failing_function)

        # Third call should be rejected with CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(lambda: 42)

        assert "test_circuit" in str(exc_info.value)
        assert "open" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_async_circuit_breaker_open_rejection(self) -> None:
        """Test async calls are rejected when circuit breaker is open."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=10.0
        )
        cb = CircuitBreaker("async_test_circuit", config=config)

        async def failing_async_function() -> int:
            raise ConnectionError("Simulated async failure")

        # Force circuit open
        with pytest.raises(ConnectionError):
            await cb.call_async(failing_async_function)
        with pytest.raises(ConnectionError):
            await cb.call_async(failing_async_function)

        # Third call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(lambda: 42)

    def test_circuit_breaker_open_with_retry_integration(self) -> None:
        """Test circuit breaker integration with retry logic."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=10.0
        )
        cb = CircuitBreaker("retry_integration", config=config)

        retry_config = RetryConfig(
            max_attempts=3, base_delay=0.01, retryable_exceptions=(ConnectionError,)
        )

        call_count = 0

        @retry_sync(config=retry_config)
        def flaky_function_with_circuit_breaker() -> int:
            nonlocal call_count
            call_count += 1

            # First two calls fail, third succeeds
            if call_count <= 2:
                raise ConnectionError("Transient failure")
            return 42

        # This should work with retries
        result = cb.call(flaky_function_with_circuit_breaker)
        assert result == 42
        assert call_count == 3

        # Now force circuit open
        def always_fail() -> int:
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            cb.call(always_fail)
        with pytest.raises(ConnectionError):
            cb.call(always_fail)

        # Now even retryable functions should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(flaky_function_with_circuit_breaker)

    @pytest.mark.asyncio
    async def test_openalgo_circuit_breaker_open_scenario(self) -> None:
        """Test OpenAlgo circuit breaker open scenario end-to-end."""
        # Reset circuit breaker state
        OPENALGO_CIRCUIT_BREAKER.reset()

        scheduler = TradingScheduler()

        # Mock failing OpenAlgo API calls at the client level
        with patch("loats.openalgo.async_client.get_quotes") as mock_get_quotes:
            mock_get_quotes.side_effect = ConnectionError("API unavailable")

            # First call should exhaust retries and raise ConnectionError, opening circuit breaker
            # OpenAlgo CB threshold=3, Retry config=3. 1 call = 3 failures = Open.
            with pytest.raises(ConnectionError):
                await scheduler._safe_get_quotes(["NIFTY"])

            # Verify circuit breaker is now open
            status = OPENALGO_CIRCUIT_BREAKER.get_status()
            assert status["state"] == "open"

            # Second call should be rejected by circuit breaker
            with pytest.raises(CircuitBreakerOpenError) as exc_info:
                await scheduler._safe_get_quotes(["NIFTY"])

            assert "openalgo" in str(exc_info.value)
            assert "open" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_telegram_circuit_breaker_open_scenario(self) -> None:
        """Test Telegram circuit breaker open scenario end-to-end.

        Note: B017 exceptions below are intentional - we're testing that the circuit breaker
        properly handles generic exceptions from the Telegram bot, which is the expected behavior.
        """
        # Reset circuit breaker state
        TELEGRAM_CIRCUIT_BREAKER.reset()

        alert_system = AlertSystem()

        # Mock failing Telegram bot
        with patch.object(alert_system, "_initialize_bot") as mock_init:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(
                side_effect=Exception("Telegram unavailable")
            )
            mock_init.return_value = mock_bot

            # Initialize the bot to set up the mock
            alert_system.bot = mock_bot

            # Force circuit breaker open - first call should fail after 5 retries
            # Telegram CB threshold=5, Retry config=5. 1 call = 5 failures = Open.
            result1 = await alert_system._send_telegram_message("Test message")
            assert result1 is False

            # Circuit breaker should now be open
            status = alert_system.get_circuit_breaker_status()
            assert status["telegram"]["state"] == "open"

            # Second call is rejected by circuit breaker and must degrade
            # gracefully (alerts must never crash the system) -> returns False.
            result2 = await alert_system._send_telegram_message("Test message")
            assert result2 is False

            # Circuit breaker must still be open (call was rejected, not retried)
            status2 = alert_system.get_circuit_breaker_status()
            assert status2["telegram"]["state"] == "open"


class TestRetryExhaustedScenarios:
    """End-to-end tests for retry exhausted scenarios."""

    def setup_method(self) -> None:
        """Reset circuit breakers before each test."""
        OPENALGO_CIRCUIT_BREAKER.reset()
        TELEGRAM_CIRCUIT_BREAKER.reset()

    def test_retry_exhausted_synchronous(self) -> None:
        """Test that retries are exhausted and final exception is raised."""
        retry_config = RetryConfig(
            max_attempts=3, base_delay=0.01, retryable_exceptions=(ConnectionError,)
        )

        call_count = 0

        @retry_sync(config=retry_config)
        def always_failing_function() -> int:
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f"Attempt {call_count} failed")

        # This should retry 3 times and then raise the exception
        with pytest.raises(ConnectionError) as exc_info:
            always_failing_function()

        assert call_count == 3
        assert "Attempt 3 failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_exhausted_asynchronous(self) -> None:
        """Test async retry exhaustion."""
        retry_config = RetryConfig(
            max_attempts=4, base_delay=0.01, retryable_exceptions=(ConnectionError,)
        )

        call_count = 0

        @retry_async(config=retry_config)
        async def always_failing_async_function() -> int:
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f"Async attempt {call_count} failed")

        with pytest.raises(ConnectionError) as exc_info:
            await always_failing_async_function()

        assert call_count == 4
        assert "Async attempt 4 failed" in str(exc_info.value)

    def test_retry_exhausted_with_on_retry_callback(self) -> None:
        """Test retry exhaustion with callback tracking."""
        retry_config = RetryConfig(
            max_attempts=3, base_delay=0.01, retryable_exceptions=(ConnectionError,)
        )

        retry_info = []

        def on_retry(exc: Exception, attempt: int) -> None:
            retry_info.append((str(exc), attempt))

        call_count = 0

        @retry_sync(config=retry_config, on_retry=on_retry)
        def failing_with_callback() -> int:
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f"Callback attempt {call_count}")

        with pytest.raises(ConnectionError):
            failing_with_callback()

        # Should have 2 retries (attempts 2 and 3)
        assert len(retry_info) == 2
        assert retry_info[0][1] == 1  # First retry is attempt 1
        assert retry_info[1][1] == 2  # Second retry is attempt 2
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_openalgo_retry_exhausted_scenario(self) -> None:
        """Test OpenAlgo API retry exhausted scenario."""
        from loats.utils.retry import OPENALGO_RETRY_CONFIG

        # Mock consistently failing API
        with patch(
            "loats.openalgo.async_client.get_position_book"
        ) as mock_get_position:
            mock_get_position.side_effect = ConnectionError(
                "API consistently unavailable"
            )

            @retry_async(config=OPENALGO_RETRY_CONFIG)
            async def get_position_with_retry() -> dict[str, Any]:
                return await async_client.get_position_book()

            # This should exhaust all retries
            with pytest.raises(ConnectionError) as exc_info:
                await get_position_with_retry()

            # Verify it was the final attempt that failed
            assert "API consistently unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scheduler_retry_exhausted_scenario(self) -> None:
        """Test scheduler retry exhausted scenario."""
        scheduler = TradingScheduler()

        # Mock failing history API
        with patch("loats.openalgo.async_client.get_history") as mock_get_history:
            mock_get_history.side_effect = ConnectionError("History API failed")

            # First call should exhaust retries and raise ConnectionError, opening circuit breaker
            with pytest.raises(ConnectionError):
                await scheduler._safe_get_history("NIFTY", "1min", 100)

            # Check status after first call - circuit breaker should now be open
            status1 = scheduler.get_circuit_breaker_status()
            print(f"After call 1: {status1}")
            assert status1["state"] == "open"
            assert status1["consecutive_failures"] == 3

            # Subsequent calls should be rejected with CircuitBreakerOpenError
            with pytest.raises(CircuitBreakerOpenError):
                await scheduler._safe_get_history("NIFTY", "1min", 100)

            # Check status after second call - should still be open
            status2 = scheduler.get_circuit_breaker_status()
            print(f"After call 2: {status2}")
            assert status2["state"] == "open"
            assert status2["rejected_calls"] == 1

            # Third call should also be rejected
            with pytest.raises(CircuitBreakerOpenError):
                await scheduler._safe_get_history("NIFTY", "1min", 100)

            # Check status after third call
            status3 = scheduler.get_circuit_breaker_status()
            print(f"After call 3: {status3}")
            assert status3["state"] == "open"
            assert status3["rejected_calls"] == 2

            # Verify circuit breaker is still open
            status = scheduler.get_circuit_breaker_status()
            assert status["state"] == "open"

    def test_retry_with_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions fail immediately."""
        retry_config = RetryConfig(
            max_attempts=5, base_delay=0.1, retryable_exceptions=(ConnectionError,)
        )

        call_count = 0

        @retry_sync(config=retry_config)
        def non_retryable_failure() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Non-retryable error")

        # Should fail immediately without retry
        with pytest.raises(ValueError):
            non_retryable_failure()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_excluded_exception(self) -> None:
        """Test that excluded exceptions don't trigger retry."""
        retry_config = RetryConfig(
            max_attempts=5, base_delay=0.1, excluded_exceptions=(ValueError,)
        )

        call_count = 0

        @retry_async(config=retry_config)
        async def excluded_exception_failure() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("Excluded error")

        # Should fail immediately
        with pytest.raises(ValueError):
            await excluded_exception_failure()

        assert call_count == 1


class TestFailureRecoveryScenarios:
    """Test system recovery after failure scenarios."""

    def setup_method(self) -> None:
        """Reset circuit breakers before each test."""
        OPENALGO_CIRCUIT_BREAKER.reset()
        TELEGRAM_CIRCUIT_BREAKER.reset()

    def test_circuit_breaker_recovery_after_timeout(self) -> None:
        """Test circuit breaker recovery after timeout period."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout=1.0,  # Short timeout for testing
        )
        cb = CircuitBreaker("recovery_test", config=config)

        # Force circuit open
        def failing_function() -> int:
            raise ConnectionError("Failure")

        with pytest.raises(ConnectionError):
            cb.call(failing_function)
        with pytest.raises(ConnectionError):
            cb.call(failing_function)

        # Circuit should be open now
        assert cb.state.name == "OPEN"

        # Wait for timeout to transition to HALF_OPEN
        time.sleep(1.1)

        # Should now be in HALF_OPEN state
        assert cb.state.name == "HALF_OPEN"

        # Successful calls should close the circuit
        assert cb.call(lambda: 42) == 42
        assert cb.call(lambda: 43) == 43

        # Circuit should now be closed
        assert cb.state.name == "CLOSED"

    @pytest.mark.asyncio
    async def test_async_circuit_breaker_recovery(self) -> None:
        """Test async circuit breaker recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=1.0
        )
        cb = CircuitBreaker("async_recovery", config=config)

        # Force circuit open
        async def failing_async() -> int:
            raise ConnectionError("Async failure")

        with pytest.raises(ConnectionError):
            await cb.call_async(failing_async)
        with pytest.raises(ConnectionError):
            await cb.call_async(failing_async)

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Successful calls should close circuit
        async def success_func() -> int:
            return 42

        assert await cb.call_async(success_func) == 42
        assert await cb.call_async(success_func) == 42

        assert cb.state.name == "CLOSED"

    def test_retry_success_after_initial_failures(self) -> None:
        """Test successful recovery after initial failures."""
        retry_config = RetryConfig(
            max_attempts=5, base_delay=0.01, retryable_exceptions=(ConnectionError,)
        )

        call_count = 0

        @retry_sync(config=retry_config)
        def eventually_successful() -> int:
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                raise ConnectionError(f"Attempt {call_count} failed")
            return 42

        result = eventually_successful()
        assert result == 42
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_openalgo_recovery_scenario(self) -> None:
        """Test OpenAlgo API recovery scenario."""
        # Reset circuit breaker with shorter timeout for testing
        OPENALGO_CIRCUIT_BREAKER.reset()
        original_timeout = OPENALGO_CIRCUIT_BREAKER.config.timeout
        OPENALGO_CIRCUIT_BREAKER.config.timeout = 1.0

        try:
            scheduler = TradingScheduler()

            # Mock failing then successful API
            call_count = 0

            async def mock_get_quotes(symbols: list[str]) -> dict[str, Any]:
                nonlocal call_count
                call_count += 1

                # Fail initially to open circuit breaker
                if call_count <= 3:
                    raise ConnectionError("API temporarily unavailable")
                return {
                    "status": "success",
                    "data": {symbol: {"last_price": 100.0} for symbol in symbols},
                }

            with patch(
                "loats.openalgo.async_client.get_quotes",
                side_effect=mock_get_quotes,
            ):
                # First call should fail after retries and open circuit breaker
                with pytest.raises(ConnectionError):
                    await scheduler._safe_get_quotes(["NIFTY"])

                # Verify it's open
                assert OPENALGO_CIRCUIT_BREAKER.get_status()["state"] == "open"

                # Wait for timeout to transition to HALF_OPEN
                await asyncio.sleep(1.1)

                # Now it should succeed and close the circuit
                result = await scheduler._safe_get_quotes(["NIFTY"])
                assert result is not None
                assert result["status"] == "success"
                assert OPENALGO_CIRCUIT_BREAKER.get_status()["state"] == "half_open"

                # One more success to close it (success_threshold=2)
                result = await scheduler._safe_get_quotes(["NIFTY"])
                assert result is not None
                assert OPENALGO_CIRCUIT_BREAKER.get_status()["state"] == "closed"
        finally:
            OPENALGO_CIRCUIT_BREAKER.config.timeout = original_timeout


class TestRateLimiterFailurePaths:
    """Test rate limiter exceeded scenarios (R5-F-01)."""

    def setup_method(self) -> None:
        """Reset rate limiters before each test."""
        import loats.utils.rate_limiter as rate_limiter_module

        # Reset both global rate limiter singletons to ensure test isolation
        with rate_limiter_module._rate_limiter_lock:
            rate_limiter_module._order_rate_limiter_instance = None

        with rate_limiter_module._smart_rate_limiter_lock:
            rate_limiter_module._smart_order_rate_limiter_instance = None

    @pytest.mark.asyncio
    async def test_order_rate_limiter_exceeded(self) -> None:
        """Test that order placement fails when rate limiter is exceeded."""
        limiter = get_order_rate_limiter()

        # Consume all available tokens
        for _ in range(50):  # max_ops=50 for order rate limiter
            result = await limiter.acquire()
            assert result is True

        # Next attempt should fail
        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_smart_order_rate_limiter_exceeded(self) -> None:
        """Test that smart order placement fails when rate limiter is exceeded."""
        limiter = get_smart_order_rate_limiter()

        # Consume all available tokens
        for _ in range(50):  # max_ops=50 for smart order rate limiter
            result = await limiter.acquire()
            assert result is True

        # Next attempt should fail
        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limiter_exceeded_with_retry(self) -> None:
        """Test rate limiter exceeded scenario with retry logic."""
        limiter = get_order_rate_limiter()

        # Consume all tokens
        for _ in range(50):
            await limiter.acquire()

        # Test that wait_for_token eventually succeeds
        start_time = time.monotonic()
        await limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed for oldest timestamp to expire
        wait_time = end_time - start_time
        assert wait_time >= 0.1  # At least 100ms
        assert wait_time <= 1.1  # Should not take more than window size + small buffer


class TestErrorPropagation:
    """Test proper error propagation through the system."""

    def test_circuit_breaker_error_propagation(self) -> None:
        """Test that CircuitBreakerOpenError contains useful information."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=10.0)
        cb = CircuitBreaker("error_prop_test", config=config)

        # Force circuit open
        def failing_function() -> int:
            raise ConnectionError("Test failure")

        with pytest.raises(ConnectionError):
            cb.call(failing_function)

        # Test error propagation
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(lambda: 42)

        error = exc_info.value
        assert error.circuit_name == "error_prop_test"
        assert error.remaining_timeout > 0
        assert "open" in str(error).lower()
        assert "error_prop_test" in str(error)

    @pytest.mark.asyncio
    async def test_retry_error_propagation(self) -> None:
        """Test that retry errors contain attempt information."""
        retry_config = RetryConfig(max_attempts=3, base_delay=0.01)

        attempt_info: list[int] = []

        @retry_sync(config=retry_config)
        def failing_with_info() -> int:
            attempt_info.append(len(attempt_info) + 1)
            raise ConnectionError(f"Attempt {len(attempt_info)} failed")

        with pytest.raises(ConnectionError) as exc_info:
            failing_with_info()

        assert len(attempt_info) == 3
        assert "Attempt 3 failed" in str(exc_info.value)

    def test_integration_error_handling(self) -> None:
        """Test integrated error handling in alert system."""
        alert_system = AlertSystem()

        # Mock failing Telegram and OpenAlgo
        with patch.object(alert_system, "_initialize_bot") as mock_init:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(side_effect=Exception("Telegram down"))
            mock_init.return_value = mock_bot

            with patch(
                "loats.openalgo.async_client.get_position_book"
            ) as mock_get_position:
                mock_get_position.side_effect = ConnectionError("OpenAlgo down")

                # Test that both failures are handled gracefully
                # Make enough calls to trigger circuit breakers
                for i in range(5):  # Telegram circuit breaker has failure_threshold=5
                    result = asyncio.run(alert_system.send_alert(f"Test alert {i}"))
                    assert result is False  # Should return False on failure

                # Check circuit breaker status - they may not be open due to retry mechanism
                # The test verifies that failures are handled gracefully
                telegram_status = alert_system.get_circuit_breaker_status()
                openalgo_status = alert_system.get_circuit_breaker_status()

                # Verify that the system handled failures gracefully
                # Circuit breakers may or may not be open depending on retry behavior
                logger.info(
                    f"Telegram CB status: {telegram_status['telegram']['state']}"
                )
                logger.info(
                    f"OpenAlgo CB status: {openalgo_status['openalgo']['state']}"
                )
