"""
Additional unit tests for rate limiter utility module to increase coverage.
Tests different window sizes, max operations, and concurrent scenarios.
"""

import asyncio
import time

import pytest

from loats.utils.rate_limiter import (
    AsyncRateLimiter,
    RateLimiter,
    SyncRateLimiter,
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
)


class TestRateLimiterAdditional:
    """Additional tests for RateLimiter class."""

    @pytest.fixture
    def rate_limiter(self) -> RateLimiter:
        """Create test RateLimiter instance."""
        return RateLimiter(max_ops=10, interval=1.0)

    @pytest.mark.asyncio
    async def test_rate_limiter_different_window_sizes(self) -> None:
        """Test rate limiter with different window sizes."""
        # Test with very small window
        limiter = RateLimiter(max_ops=2, window_size=0.1)  # 100ms window

        # Should be able to acquire 2 tokens quickly
        result1 = await limiter.acquire()
        result2 = await limiter.acquire()
        assert result1 is True
        assert result2 is True

        # Third should fail
        result3 = await limiter.acquire()
        assert result3 is False

        # Wait for window to expire
        await asyncio.sleep(0.11)  # 110ms

        # Should be able to acquire again
        result4 = await limiter.acquire()
        assert result4 is True

    @pytest.mark.asyncio
    async def test_rate_limiter_zero_max_ops(self) -> None:
        """Test rate limiter with zero max operations."""
        limiter = RateLimiter(max_ops=0, window_size=1.0)

        # Should always fail to acquire
        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limiter_large_max_ops(self) -> None:
        """Test rate limiter with large max operations."""
        limiter = RateLimiter(max_ops=1000, window_size=1.0)

        # Should be able to acquire many tokens
        for _i in range(100):
            result = await limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent_access(self) -> None:
        """Test rate limiter with concurrent access."""
        limiter = RateLimiter(max_ops=5, window_size=1.0)

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
    async def test_rate_limiter_backward_compatibility(self) -> None:
        """Test rate limiter backward compatibility with interval parameter."""
        # Test with interval parameter (deprecated but should still work)
        limiter = RateLimiter(max_ops=5, interval=2.0)

        assert limiter.max_ops == 5
        assert limiter.interval == 2.0
        assert limiter.window_size == 2.0

        # Should work normally
        for _i in range(5):
            result = await limiter.acquire()
            assert result is True


class TestAsyncRateLimiterAdditional:
    """Additional tests for AsyncRateLimiter class."""

    @pytest.fixture
    def async_rate_limiter(self) -> AsyncRateLimiter:
        """Create test AsyncRateLimiter instance."""
        return AsyncRateLimiter(max_ops=5, window_size=1.0)

    @pytest.mark.asyncio
    async def test_async_rate_limiter_different_window_sizes(self) -> None:
        """Test async rate limiter with different window sizes."""
        # Test with very large window
        limiter = AsyncRateLimiter(max_ops=10, window_size=10.0)  # 10 second window

        # Should be able to acquire 10 tokens
        for _i in range(10):
            result = await limiter.acquire()
            assert result is True

        # 11th should fail
        result = await limiter.acquire()
        assert result is False

        # Wait for partial window to expire
        await asyncio.sleep(5.0)  # 5 seconds

        # Should still not be able to acquire (sliding window still has recent tokens)
        result = await limiter.acquire()
        assert result is False

        # Wait for full window to expire
        await asyncio.sleep(6.0)  # Total 11 seconds

        # Should be able to acquire again
        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_async_rate_limiter_burst_then_wait(self) -> None:
        """Test async rate limiter with burst then wait pattern."""
        limiter = AsyncRateLimiter(max_ops=3, window_size=1.0)

        # Burst: acquire all tokens
        results = []
        for _i in range(5):
            result = await limiter.acquire()
            results.append(result)

        # Should have exactly 3 successful acquisitions
        successful = sum(results)
        assert successful == 3

        # Wait for tokens to become available
        start_time = time.monotonic()
        await limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed for oldest token to expire
        wait_time = end_time - start_time
        assert wait_time >= 0.1  # At least 100ms
        assert wait_time <= 1.5  # At most 1.5 seconds

    @pytest.mark.asyncio
    async def test_async_rate_limiter_multiple_waiters(self) -> None:
        """Test async rate limiter with multiple concurrent waiters."""
        limiter = AsyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the limiter
        await limiter.acquire()
        await limiter.acquire()

        async def waiter(worker_id: int) -> float:
            """Waiter function that measures wait time."""
            start_time = time.monotonic()
            await limiter.wait_for_token()
            end_time = time.monotonic()
            return end_time - start_time

        # Create multiple waiters
        waiters = [waiter(i) for i in range(4)]
        wait_times = await asyncio.gather(*waiters)

        # All waiters should eventually succeed
        assert len(wait_times) == 4
        # Wait times should be reasonable
        for wait_time in wait_times:
            assert wait_time >= 0.0
            assert (
                wait_time <= 1.1
            )  # Should not take more than window size + small buffer


class TestSyncRateLimiterAdditional:
    """Additional tests for SyncRateLimiter class."""

    @pytest.fixture
    def sync_rate_limiter(self) -> SyncRateLimiter:
        """Create test SyncRateLimiter instance."""
        return SyncRateLimiter(max_ops=5, window_size=1.0)

    def test_sync_rate_limiter_basic_functionality(self) -> None:
        """Test basic functionality of sync rate limiter."""
        limiter = SyncRateLimiter(max_ops=3, window_size=1.0)

        # Should be able to acquire 3 tokens
        for _i in range(3):
            result = limiter.acquire()
            assert result is True

        # 4th should fail
        result = limiter.acquire()
        assert result is False

    def test_sync_rate_limiter_different_window_sizes(self) -> None:
        """Test sync rate limiter with different window sizes."""
        # Test with very small window
        limiter = SyncRateLimiter(max_ops=2, window_size=0.1)  # 100ms window

        # Should be able to acquire 2 tokens
        result1 = limiter.acquire()
        result2 = limiter.acquire()
        assert result1 is True
        assert result2 is True

        # Third should fail
        result3 = limiter.acquire()
        assert result3 is False

        # Wait for window to expire
        time.sleep(0.11)  # 110ms

        # Should be able to acquire again
        result4 = limiter.acquire()
        assert result4 is True

    def test_sync_rate_limiter_backward_compatibility(self) -> None:
        """Test sync rate limiter backward compatibility with interval parameter."""
        # Test with interval parameter (deprecated but should still work)
        limiter = SyncRateLimiter(max_ops=5, interval=2.0)

        assert limiter.max_ops == 5
        assert limiter.interval == 2.0
        assert limiter.window_size == 2.0

        # Should work normally
        for _i in range(5):
            result = limiter.acquire()
            assert result is True

    def test_sync_rate_limiter_wait_for_token(self) -> None:
        """Test sync rate limiter wait for token functionality."""
        limiter = SyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the limiter
        limiter.acquire()
        limiter.acquire()

        # Wait for token should succeed
        start_time = time.monotonic()
        limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed for oldest token to expire
        wait_time = end_time - start_time
        assert wait_time >= 0.1  # At least 100ms
        assert wait_time <= 1.0  # At most 1 second


class TestGlobalRateLimitersAdditional:
    """Additional tests for global rate limiter instances."""

    def test_get_order_rate_limiter_with_custom_params(self) -> None:
        """Test getting order rate limiter with custom parameters."""
        # Get default limiter
        default_limiter = get_order_rate_limiter()
        assert default_limiter.max_ops == 3
        assert default_limiter.window_size == 1.0

        # Get custom limiter - should return the same singleton instance
        custom_limiter = get_order_rate_limiter(max_ops=75, window_size=1.5)
        # Since it's a singleton, custom parameters are ignored after first creation
        assert custom_limiter.max_ops == 3  # Should be the original default
        assert custom_limiter.window_size == 1.0  # Should be the original default

        # Should be the same instance (singleton behavior)
        assert default_limiter is custom_limiter

    def test_get_smart_order_rate_limiter_with_custom_params(self) -> None:
        """Test getting smart order rate limiter with custom parameters."""
        # Get default limiter
        default_limiter = get_smart_order_rate_limiter()
        assert default_limiter.max_ops == 3
        assert default_limiter.window_size == 1.0

        # Get custom limiter - should return the same singleton instance
        custom_limiter = get_smart_order_rate_limiter(max_ops=75, window_size=1.5)
        # Since it's a singleton, custom parameters are ignored after first creation
        assert custom_limiter.max_ops == 3  # Should be the original default
        assert custom_limiter.window_size == 1.0  # Should be the original default

        # Should be the same instance (singleton behavior)
        assert default_limiter is custom_limiter

    def test_rate_limiter_singleton_behavior(self) -> None:
        """Test that rate limiters are now singletons (fixed F-CONC-3)."""
        # Get default limiters multiple times
        order_limiter1 = get_order_rate_limiter()
        order_limiter2 = get_order_rate_limiter()
        smart_limiter1 = get_smart_order_rate_limiter()
        smart_limiter2 = get_smart_order_rate_limiter()

        # Should be the same instance (singleton behavior)
        assert order_limiter1 is order_limiter2
        assert smart_limiter1 is smart_limiter2

        # Should still be different types of limiters (different singletons)
        assert order_limiter1 is not smart_limiter1

        # All should have default max_ops=3
        assert order_limiter1.max_ops == 3
        assert order_limiter2.max_ops == 3
        assert smart_limiter1.max_ops == 3
        assert smart_limiter2.max_ops == 3

        # Each should have default max_ops=3
        assert order_limiter1.max_ops == 3
        assert order_limiter2.max_ops == 3
        assert smart_limiter1.max_ops == 3
        assert smart_limiter2.max_ops == 3


class TestRateLimiterEdgeCasesAdditional:
    """Additional tests for rate limiter edge cases."""

    @pytest.mark.asyncio
    async def test_rate_limiter_very_small_window_edge_case(self) -> None:
        """Test rate limiter with very small window edge case."""
        # Use 50ms window (Windows time.monotonic() has ~15ms resolution)
        limiter = AsyncRateLimiter(max_ops=1, window_size=0.05)

        # First acquisition should succeed
        result1 = await limiter.acquire()
        assert result1 is True

        # Second acquisition should fail immediately
        result2 = await limiter.acquire()
        assert result2 is False

        # Wait for window to expire (use 2x window to ensure reliability)
        await asyncio.sleep(0.1)

        # Should succeed again
        result3 = await limiter.acquire()
        assert result3 is True

    @pytest.mark.asyncio
    async def test_rate_limiter_large_burst_edge_case(self) -> None:
        """Test rate limiter with large burst of requests."""
        limiter = AsyncRateLimiter(max_ops=10, window_size=1.0)

        # Try to acquire many more than max_ops
        results = []
        for _i in range(100):
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

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent_burst_edge_case(self) -> None:
        """Test rate limiter with concurrent burst of requests."""
        limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)

        async def burst_worker(worker_id: int, num_requests: int) -> int:
            """Worker that makes multiple requests."""
            successful = 0
            for _i in range(num_requests):
                result = await limiter.acquire()
                if result:
                    successful += 1
            return successful

        # Create multiple workers that each try to acquire many tokens
        workers = [burst_worker(i, 10) for i in range(3)]
        results = await asyncio.gather(*workers)

        # Total successful should be exactly 5 (max_ops)
        total_successful = sum(results)
        assert total_successful == 5


class TestRateLimiterIntegrationAdditional:
    """Additional integration tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_sustained_rate_pattern(self) -> None:
        """Test rate limiter with sustained rate pattern."""
        limiter = AsyncRateLimiter(
            max_ops=5, window_size=0.5
        )  # 5 ops per 500ms = 10 ops per second

        start_time = time.monotonic()
        successful_ops = 0
        attempt_count = 0

        # Try to perform operations at a sustained rate for 1 second
        while time.monotonic() - start_time < 1.0:
            result = await limiter.acquire()
            if result:
                successful_ops += 1
            attempt_count += 1
            await asyncio.sleep(0.01)  # Small delay between attempts

        end_time = time.monotonic()
        duration = end_time - start_time

        # Should be close to expected rate (10 ops per second)
        expected_ops = int(duration * 10)  # 10 ops per second
        tolerance = max(2, int(expected_ops * 0.3))  # 30% tolerance

        assert abs(successful_ops - expected_ops) <= tolerance
        assert (
            attempt_count > successful_ops
        )  # Some attempts should have been rate limited

    @pytest.mark.asyncio
    async def test_rate_limiter_adaptive_pattern(self) -> None:
        """Test rate limiter with adaptive request pattern."""
        limiter = AsyncRateLimiter(max_ops=3, window_size=1.0)

        # Phase 1: Burst
        burst_results = []
        for _i in range(5):
            result = await limiter.acquire()
            burst_results.append(result)

        burst_successful = sum(burst_results)
        assert burst_successful == 3

        # Phase 2: Wait and try again
        await asyncio.sleep(0.5)  # Wait half the window

        second_burst_results = []
        for _i in range(3):
            result = await limiter.acquire()
            second_burst_results.append(result)

        # Should get some but not all tokens
        second_burst_successful = sum(second_burst_results)
        assert (
            second_burst_successful == 0
        )  # No tokens available yet (strict sliding window)
        # After waiting half the window (0.5s), the oldest tokens are still within the 1.0s window
        # The rate limiter correctly enforces strict limits

        # Phase 3: Wait for full window and try again
        await asyncio.sleep(0.6)  # Wait remaining time + buffer

        third_burst_results = []
        for _i in range(3):
            result = await limiter.acquire()
            third_burst_results.append(result)

        # Should get all tokens now
        third_burst_successful = sum(third_burst_results)
        assert third_burst_successful == 3
