"""
Regression test for rate limiter concurrency behavior.
This test verifies that the rate limiter properly enforces limits
when multiple calls are made concurrently, addressing the F-CONC-3 issue.
"""

import asyncio
import time

import pytest

from src.loats.utils.rate_limiter import (
    AsyncRateLimiter,
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
)


class TestRateLimiterConcurrencyRegression:
    """Regression tests for rate limiter concurrency behavior."""

    @pytest.mark.asyncio
    async def test_order_rate_limiter_concurrency(self) -> None:
        """Test that order rate limiter enforces limits under concurrent access."""
        # The singleton pattern uses 50 ops/sec as default, ignoring custom parameters
        limiter = get_order_rate_limiter()  # Uses singleton with 50 ops/sec default

        async def make_request(request_id: int) -> bool:
            """Simulate an order request."""
            try:
                return await limiter.acquire()
            except Exception:
                return False

        # Create 100 rapid requests to test concurrency
        tasks = [make_request(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        # Should have approximately 50 successful acquisitions (max_ops from singleton default)
        # Allow for small timing variations in concurrent scenarios (45-55 range)
        successful = sum(results)
        assert 45 <= successful <= 55, (
            f"Expected 45-55 successful acquisitions, got {successful}"
        )

        # Verify that the singleton behavior works correctly
        limiter1 = get_order_rate_limiter()
        limiter2 = get_order_rate_limiter()
        assert limiter1 is limiter2, "Rate limiter should be a singleton"

    @pytest.mark.asyncio
    async def test_smart_order_rate_limiter_concurrency(self) -> None:
        """Test that smart order rate limiter enforces limits under concurrent access."""
        # The singleton pattern uses 50 ops/sec as default, ignoring custom parameters
        limiter = (
            get_smart_order_rate_limiter()
        )  # Uses singleton with 50 ops/sec default

        async def make_request(request_id: int) -> bool:
            """Simulate a smart order request."""
            try:
                return await limiter.acquire()
            except Exception:
                return False

        # Create 100 rapid requests to test concurrency
        tasks = [make_request(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        # Should have approximately 50 successful acquisitions (max_ops from singleton default)
        # Allow for small timing variations in concurrent scenarios (45-55 range)
        successful = sum(results)
        assert 45 <= successful <= 55, (
            f"Expected 45-55 successful acquisitions, got {successful}"
        )

        # Verify that the singleton behavior works correctly
        limiter1 = get_smart_order_rate_limiter()
        limiter2 = get_smart_order_rate_limiter()
        assert limiter1 is limiter2, "Rate limiter should be a singleton"

    @pytest.mark.asyncio
    async def test_mixed_rate_limiter_concurrency(self) -> None:
        """Test concurrent access to both order and smart order rate limiters."""
        # The singleton pattern uses 50 ops/sec as default, ignoring custom parameters
        order_limiter = (
            get_order_rate_limiter()
        )  # Uses singleton with 50 ops/sec default
        smart_limiter = (
            get_smart_order_rate_limiter()
        )  # Uses singleton with 50 ops/sec default

        async def make_order_request(request_id: int) -> bool:
            """Simulate an order request."""
            try:
                return await order_limiter.acquire()
            except Exception:
                return False

        async def make_smart_order_request(request_id: int) -> bool:
            """Simulate a smart order request."""
            try:
                return await smart_limiter.acquire()
            except Exception:
                return False

        # Create mixed requests
        all_tasks = [make_order_request(i) for i in range(50)] + [
            make_smart_order_request(i) for i in range(50, 100)
        ]
        results = await asyncio.gather(*all_tasks)

        # Should have approximately 50 successful order acquisitions (from singleton default)
        # Allow for small timing variations in concurrent scenarios (45-55 range)
        order_successful = sum(results[:50])
        assert 45 <= order_successful <= 55, (
            f"Expected 45-55 successful order acquisitions, got {order_successful}"
        )

        # Should have approximately 50 successful smart order acquisitions (from singleton default)
        # Allow for small timing variations in concurrent scenarios (45-55 range)
        smart_successful = sum(results[50:])
        assert 45 <= smart_successful <= 55, (
            f"Expected 45-55 successful smart order acquisitions, got {smart_successful}"
        )

        # Verify that both limiters are singletons
        order_limiter1 = get_order_rate_limiter()
        order_limiter2 = get_order_rate_limiter()
        assert order_limiter1 is order_limiter2, (
            "Order rate limiter should be a singleton"
        )

        smart_limiter1 = get_smart_order_rate_limiter()
        smart_limiter2 = get_smart_order_rate_limiter()
        assert smart_limiter1 is smart_limiter2, (
            "Smart order rate limiter should be a singleton"
        )

    @pytest.mark.asyncio
    async def test_rate_limiter_time_window_enforcement(self) -> None:
        """Test that rate limiter properly enforces time window limits."""
        limiter = get_order_rate_limiter(
            max_ops=10, window_size=1.0
        )  # 10 ops per second

        # First, fill the limiter
        for _ in range(10):
            await limiter.acquire()

        # All subsequent requests should fail immediately
        results = []
        for _ in range(10):
            result = await limiter.acquire()
            results.append(result)

        # Should all fail
        assert all(not result for result in results), (
            "All requests after max_ops should fail"
        )

        # Wait for the window to expire
        await asyncio.sleep(1.1)  # Slightly more than window size

        # Should be able to acquire again
        result = await limiter.acquire()
        assert result is True, "Should be able to acquire after window expires"

    @pytest.mark.asyncio
    async def test_rate_limiter_sustained_concurrent_load(self) -> None:
        """Test rate limiter with sustained concurrent load over time."""
        # Create a direct instance to test specific rate limits
        # (avoid singleton pattern which uses fixed 50 ops/sec)
        limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)  # 5 ops per second

        start_time = time.monotonic()
        successful_ops = 0
        attempt_count = 0

        # Run for 2 seconds with rapid requests
        while time.monotonic() - start_time < 2.0:
            result = await limiter.acquire()
            if result:
                successful_ops += 1
            attempt_count += 1
            await asyncio.sleep(0.01)  # Small delay between attempts

        end_time = time.monotonic()
        duration = end_time - start_time

        # Should be close to expected rate (5 ops per second)
        expected_ops = int(duration * 5)  # 5 ops per second
        tolerance = max(2, int(expected_ops * 0.2))  # 20% tolerance

        assert abs(successful_ops - expected_ops) <= tolerance, (
            f"Expected ~{expected_ops} successful ops in {duration}s, "
            f"got {successful_ops} (tolerance: {tolerance})"
        )

        # Verify singleton behavior
        limiter1 = get_order_rate_limiter()
        limiter2 = get_order_rate_limiter()
        assert limiter1 is limiter2, "Rate limiter should be a singleton"

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent_waiters(self) -> None:
        """Test rate limiter with multiple concurrent waiters."""
        limiter = get_order_rate_limiter(max_ops=2, window_size=0.5)  # 2 ops per 500ms

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
        assert len(wait_times) == 4, "All waiters should complete"

        # Wait times should be reasonable (not too long)
        # Allow for some small timing variations due to system scheduling
        for wait_time in wait_times:
            assert wait_time >= 0.0, "Wait time should be non-negative"
            assert wait_time <= 1.2, (
                f"Wait time {wait_time} should not exceed window size + buffer (allowing for small timing variations)"
            )

        # Verify singleton behavior
        limiter1 = get_order_rate_limiter()
        limiter2 = get_order_rate_limiter()
        assert limiter1 is limiter2, "Rate limiter should be a singleton"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
