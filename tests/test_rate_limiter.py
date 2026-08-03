"""
Unit tests for rate limiter utility module.
Tests token bucket and sliding window rate limiting algorithms.
"""

import asyncio
import time

import pytest

from src.loats.config import get_settings
from src.loats.utils.rate_limiter import (
    AsyncRateLimiter,
    RateLimiter,
    RateLimitExceededError,
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
)


class TestRateLimiter:
    """Tests for RateLimiter (token bucket algorithm)."""

    @pytest.fixture
    def rate_limiter(self) -> RateLimiter:
        """Create test RateLimiter instance."""
        return RateLimiter(max_ops=10, interval=1.0)

    def test_initialization_with_defaults(self) -> None:
        """Test initialization with default settings."""
        limiter = RateLimiter()
        settings = get_settings()
        assert limiter.max_ops == settings.max_ops
        assert limiter.interval == 1.0

    def test_initialization_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        limiter = RateLimiter(max_ops=5, interval=2.0)
        assert limiter.max_ops == 5
        assert limiter.interval == 2.0

    @pytest.mark.asyncio
    async def test_acquire_success(self, rate_limiter: RateLimiter) -> None:
        """Test successful token acquisition."""
        # Should be able to acquire tokens up to max_ops
        for _i in range(10):
            result = await rate_limiter.acquire()
            assert result is True

        # Next acquisition should fail
        result = await rate_limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_token_refill(self, rate_limiter: RateLimiter) -> None:
        """Test token refill over time - sliding window behavior."""
        # Consume all tokens (sliding window tracks timestamps)
        for _ in range(10):
            await rate_limiter.acquire()

        # Wait for partial window to pass (0.5 seconds = half the window)
        await asyncio.sleep(0.5)

        # With sliding window, we need to wait until oldest timestamp expires
        # Oldest timestamp was from ~0.5s ago, window is 1.0s, so it should expire
        # Wait a bit more to ensure oldest timestamp is removed
        await asyncio.sleep(
            0.6
        )  # Total wait: 1.1s, oldest timestamp (0s) + 1.0s window = expired

        # Now we should be able to acquire a token
        result = await rate_limiter.acquire()
        assert result is True

        # Consume another token
        result = await rate_limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_full_refill(self, rate_limiter: RateLimiter) -> None:
        """Test full token refill after interval using sliding window."""
        # Consume all tokens
        for _ in range(10):
            await rate_limiter.acquire()

        # Wait for full window to expire (oldest timestamp + window_size)
        await asyncio.sleep(1.1)  # Slightly more than window_size to ensure expiration

        # Should be able to acquire tokens again as old ones expire
        for _ in range(10):
            result = await rate_limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_token_success(self, rate_limiter: RateLimiter) -> None:
        """Test waiting for token successfully."""
        # Consume all tokens
        for _ in range(10):
            await rate_limiter.acquire()

        # This should wait and eventually succeed
        start_time = time.monotonic()
        await rate_limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed to refill one token
        assert end_time - start_time >= 0.1  # At least 100ms

    @pytest.mark.asyncio
    async def test_wait_for_token_interrupted(self, rate_limiter: RateLimiter) -> None:
        """Test waiting for token with interruption."""
        # Consume all tokens
        for _ in range(10):
            await rate_limiter.acquire()

        # Start waiting in a task
        wait_task = asyncio.create_task(rate_limiter.wait_for_token())

        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        wait_task.cancel()

        try:
            await wait_task
        except asyncio.CancelledError:
            pass  # Expected


class TestAsyncRateLimiter:
    """Tests for AsyncRateLimiter (sliding window algorithm)."""

    @pytest.fixture
    def async_rate_limiter(self) -> AsyncRateLimiter:
        """Create test AsyncRateLimiter instance."""
        return AsyncRateLimiter(max_ops=5, window_size=1.0)

    def test_initialization_with_defaults(self) -> None:
        """Test initialization with default settings."""
        limiter = AsyncRateLimiter()
        settings = get_settings()
        assert limiter.max_ops == settings.max_ops
        assert limiter.window_size == 1.0
        assert len(limiter.timestamps) == 0

    def test_initialization_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        limiter = AsyncRateLimiter(max_ops=3, window_size=2.0)
        assert limiter.max_ops == 3
        assert limiter.window_size == 2.0
        assert len(limiter.timestamps) == 0

    @pytest.mark.asyncio
    async def test_acquire_success(self, async_rate_limiter: AsyncRateLimiter) -> None:
        """Test successful token acquisition."""
        # Should be able to acquire tokens up to max_ops
        for _i in range(5):
            result = await async_rate_limiter.acquire()
            assert result is True

        # Next acquisition should fail
        result = await async_rate_limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_sliding_window(self, async_rate_limiter: AsyncRateLimiter) -> None:
        """Test sliding window behavior."""
        # Fill the window
        for _ in range(5):
            await async_rate_limiter.acquire()

        # Wait slightly more than window size to ensure oldest timestamp expires
        await asyncio.sleep(1.1)

        # Should be able to acquire tokens again as old ones expire
        result = await async_rate_limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_full_window_expiration(
        self, async_rate_limiter: AsyncRateLimiter
    ) -> None:
        """Test full window expiration."""
        # Fill the window
        for _ in range(5):
            await async_rate_limiter.acquire()

        # Wait slightly more than window size to ensure all timestamps expire
        await asyncio.sleep(1.1)

        # Should be able to acquire all tokens again
        for _ in range(5):
            result = await async_rate_limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_get_wait_time(self, async_rate_limiter: AsyncRateLimiter) -> None:
        """Test wait time calculation."""
        # Fill the window
        for _ in range(5):
            await async_rate_limiter.acquire()

        # Wait time should be the time until the oldest timestamp falls out of window
        wait_time = await async_rate_limiter.get_wait_time()
        assert wait_time > 0
        assert wait_time <= 1.0  # Should be <= window size

        # Wait for the calculated time
        await asyncio.sleep(wait_time + 0.01)  # Add small buffer

        # Should be able to acquire now
        result = await async_rate_limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_token_success(
        self, async_rate_limiter: AsyncRateLimiter
    ) -> None:
        """Test waiting for token successfully."""
        # Fill the window
        for _ in range(5):
            await async_rate_limiter.acquire()

        # This should wait and eventually succeed
        start_time = time.monotonic()
        await async_rate_limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed for oldest timestamp to expire
        assert end_time - start_time >= 0.1  # At least 100ms


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError exception."""

    def test_error_message(self) -> None:
        """Test exception message."""
        error = RateLimitExceededError("Custom message")
        assert str(error) == "Custom message"
        assert error.message == "Custom message"

    def test_default_message(self) -> None:
        """Test default exception message."""
        error = RateLimitExceededError()
        assert str(error) == "Rate limit exceeded"
        assert error.message == "Rate limit exceeded"


class TestGlobalRateLimiters:
    """Tests for global rate limiter instances."""

    def test_get_order_rate_limiter(self) -> None:
        """Test getting order rate limiter."""
        limiter = get_order_rate_limiter()
        assert isinstance(limiter, AsyncRateLimiter)
        # Order rate limiter uses max_ops=50 for order operations
        assert limiter.max_ops == 50
        assert limiter.window_size == 1.0

    def test_get_smart_order_rate_limiter(self) -> None:
        """Test getting smart order rate limiter."""
        limiter = get_smart_order_rate_limiter()
        assert isinstance(limiter, AsyncRateLimiter)
        # Smart order rate limiter uses max_ops=50 (configured in rate_limiter.py)
        assert limiter.max_ops == 50
        assert limiter.window_size == 1.0

    def test_rate_limiter_singleton(self) -> None:
        """Test that rate limiters are singletons."""
        limiter1 = get_order_rate_limiter()
        limiter2 = get_order_rate_limiter()
        assert limiter1 is limiter2

        smart_limiter1 = get_smart_order_rate_limiter()
        smart_limiter2 = get_smart_order_rate_limiter()
        assert smart_limiter1 is smart_limiter2

        # Order and smart order limiters should be different instances
        assert limiter1 is not smart_limiter1


class TestRateLimiterConcurrency:
    """Tests for rate limiter concurrency behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_access(self) -> None:
        """Test concurrent access to rate limiter."""
        limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)

        async def worker(worker_id: int) -> bool:
            """Worker function that tries to acquire token."""
            try:
                return await limiter.acquire()
            except Exception:
                return False

        # Create multiple workers
        workers = [worker(i) for i in range(10)]
        results = await asyncio.gather(*workers)

        # Should have exactly 5 successful acquisitions
        successful = sum(results)
        assert successful == 5

    @pytest.mark.asyncio
    async def test_concurrent_wait(self) -> None:
        """Test concurrent waiting for tokens."""
        limiter = AsyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the limiter
        await limiter.acquire()
        await limiter.acquire()

        async def worker(worker_id: int) -> float:
            """Worker function that waits for token and measures time."""
            start_time = time.monotonic()
            await limiter.wait_for_token()
            end_time = time.monotonic()
            return end_time - start_time

        # Create multiple workers
        workers = [worker(i) for i in range(3)]
        wait_times = await asyncio.gather(*workers)

        # All workers should eventually succeed
        assert len(wait_times) == 3
        # Wait times should be reasonable
        for wait_time in wait_times:
            assert wait_time >= 0.0
            assert (
                wait_time <= 1.1
            )  # Should not take more than window size + small buffer


class TestRateLimiterEdgeCases:
    """Tests for rate limiter edge cases."""

    @pytest.mark.asyncio
    async def test_zero_max_ops(self) -> None:
        """Test rate limiter with zero max ops."""
        limiter = AsyncRateLimiter(max_ops=0, window_size=1.0)

        # Should always fail to acquire
        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_very_small_window(self) -> None:
        """Test rate limiter with very small window."""
        limiter = AsyncRateLimiter(max_ops=1, window_size=0.01)  # 10ms window

        # First acquisition should succeed
        result1 = await limiter.acquire()
        assert result1 is True

        # Second acquisition should fail immediately
        result2 = await limiter.acquire()
        assert result2 is False

        # Wait for window to expire
        await asyncio.sleep(0.02)  # 20ms

        # Should succeed again
        result3 = await limiter.acquire()
        assert result3 is True

    @pytest.mark.asyncio
    async def test_large_burst(self) -> None:
        """Test rate limiter with large burst of requests."""
        limiter = AsyncRateLimiter(max_ops=10, window_size=1.0)

        # Try to acquire more than max_ops
        results = []
        for _ in range(20):
            result = await limiter.acquire()
            results.append(result)

        # Should have exactly 10 successful acquisitions
        successful = sum(results)
        assert successful == 10

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should be able to acquire again
        result = await limiter.acquire()
        assert result is True


class TestRateLimiterIntegration:
    """Integration tests for rate limiter with real timing."""

    @pytest.mark.asyncio
    async def test_sustained_rate(self) -> None:
        """Test sustained rate over multiple windows."""
        limiter = AsyncRateLimiter(max_ops=5, window_size=0.5)  # 5 ops per 500ms

        start_time = time.monotonic()
        successful_ops = 0

        # Try to perform operations at a sustained rate
        while time.monotonic() - start_time < 2.0:  # Run for 2 seconds
            result = await limiter.acquire()
            if result:
                successful_ops += 1
            await asyncio.sleep(0.05)  # Small delay between attempts

        end_time = time.monotonic()
        duration = end_time - start_time

        # Should be close to expected rate (5 ops per 0.5s = 10 ops per second)
        expected_ops = int(duration * 10)  # 10 ops per second
        tolerance = max(2, int(expected_ops * 0.2))  # 20% tolerance

        assert abs(successful_ops - expected_ops) <= tolerance

    @pytest.mark.asyncio
    async def test_burst_then_sustained(self) -> None:
        """Test burst followed by sustained rate."""
        limiter = AsyncRateLimiter(max_ops=3, window_size=1.0)

        # Initial burst - should get 3 successful operations
        burst_results = []
        for _ in range(5):
            result = await limiter.acquire()
            burst_results.append(result)

        burst_successful = sum(burst_results)
        assert burst_successful == 3

        # Wait for window to expire so we can acquire more
        await asyncio.sleep(1.1)

        # Should be able to get more operations
        second_burst_results = []
        for _ in range(3):
            result = await limiter.acquire()
            second_burst_results.append(result)

        second_burst_successful = sum(second_burst_results)
        assert second_burst_successful >= 1  # Should get at least 1
        assert second_burst_successful <= 3  # Should get at most 3
