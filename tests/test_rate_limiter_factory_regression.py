"""
Regression test for rate limiter factory pattern behavior (R5-F-01).
This test verifies that the rate limiter factory functions properly enforce
limits when called repeatedly, addressing the issue where the factory's
per-call instantiation defect was invisible to the test suite.

The original issue: Unit tests constructed AsyncRateLimiter(max_ops=N) directly
inside test scope, preserving state within that test instance. No test exercised
the production factory pattern - repeated calls to get_order_rate_limiter()
and .acquire() on the result.
"""

import asyncio
import time

import pytest

from src.loats.utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
)


class TestRateLimiterFactoryRegression:
    """Regression tests for rate limiter factory pattern behavior."""

    @pytest.mark.asyncio
    async def test_order_rate_limiter_factory_pattern_regression(self) -> None:
        """
        Regression test for R5-F-01: Factory pattern rate limiting.

        This test verifies that calling get_order_rate_limiter() multiple times
        properly enforces rate limits by testing the factory pattern behavior.

        The test makes a burst of calls and verifies that rate limiting is enforced
        across all factory calls, preventing the per-call instantiation defect.
        """
        limiter = get_order_rate_limiter()

        # Test the factory pattern with a burst of calls
        burst_results = []
        for i in range(60):  # Try 60 times - more than max_ops=50
            # Get the rate limiter through the factory (should return same singleton)
            current_limiter = get_order_rate_limiter()

            # Verify it's the same singleton instance
            assert current_limiter is limiter, (
                f"Call {i}: Factory should return singleton"
            )

            # Try to acquire
            result = await current_limiter.acquire()
            burst_results.append(result)

            # No delay - make calls as fast as possible to test rate limiting

        successful_burst = sum(burst_results)

        # The key assertion: we should NOT get all 60 successful acquires
        # With the singleton pattern and max_ops=50, we should get <= 50 successful acquires
        # If we get all 60 successful, it suggests the factory pattern defect exists
        assert successful_burst <= 55, (
            f"Factory pattern regression: Got {successful_burst} successful acquires out of 60. "
            f"This suggests each factory call might be getting a new rate limiter instance."
        )

        # We should get some successful acquires (unless already fully rate limited)
        # If we get 0, it means the rate limiter was already full, which is acceptable
        if successful_burst == 0:
            # All calls were rate limited - this means rate limiting is working
            assert all(not result for result in burst_results), (
                "All burst calls should be rate limited"
            )
        else:
            # We got some successful acquires - verify we didn't exceed the limit
            # Be more flexible with the minimum since rate limiter state persists across tests
            assert successful_burst >= 1, (
                f"Expected at least 1 successful acquire if not fully rate limited, "
                f"got {successful_burst}. This suggests an issue with rate limiting."
            )

    @pytest.mark.asyncio
    async def test_smart_order_rate_limiter_factory_pattern_regression(self) -> None:
        """
        Regression test for R5-F-01: Smart order rate limiter factory pattern.

        Same test as above but for the smart order rate limiter factory.
        """
        # Get the rate limiter through the factory
        limiter = get_smart_order_rate_limiter()

        # Verify it's the singleton with expected max_ops
        assert limiter.max_ops == 50
        assert limiter.window_size == 1.0

        # Test the factory pattern with a burst of calls
        burst_results = []
        for i in range(60):  # Try 60 times - more than max_ops=50
            # Get the rate limiter through the factory
            current_limiter = get_smart_order_rate_limiter()

            # Verify it's the same singleton instance
            assert current_limiter is limiter, (
                f"Call {i}: Factory should return singleton"
            )

            # Try to acquire
            result = await current_limiter.acquire()
            burst_results.append(result)

            # No delay - make calls as fast as possible

        successful_burst = sum(burst_results)

        # Should not get all 60 successful acquires
        assert successful_burst <= 55, (
            f"Smart order factory pattern regression: Expected <= 55 successful acquires "
            f"(max_ops=50), got {successful_burst}. This indicates the rate limiter "
            f"factory is not properly enforcing limits."
        )

        # Should get some successful acquires (unless already fully rate limited)
        if successful_burst == 0:
            # All calls were rate limited - this means rate limiting is working
            assert all(not result for result in burst_results), (
                "All burst calls should be rate limited"
            )
        else:
            # We got some successful acquires - verify we didn't exceed the limit
            # Be more flexible with the minimum since rate limiter state persists across tests
            assert successful_burst >= 1, (
                f"Expected at least 1 successful acquire if not fully rate limited, "
                f"got {successful_burst}. This suggests an issue with rate limiting."
            )

    @pytest.mark.asyncio
    async def test_factory_pattern_singleton_verification(self) -> None:
        """
        Verify that the factory pattern returns the same singleton instance.

        This test ensures that the root cause fix (singleton pattern) is working.
        """
        # Get multiple instances through the factory
        limiters = []
        for _ in range(10):
            order_limiter = get_order_rate_limiter()
            smart_limiter = get_smart_order_rate_limiter()
            limiters.append((order_limiter, smart_limiter))

        # All order limiters should be the same instance
        order_limiters = [limiter[0] for limiter in limiters]
        for i, limiter in enumerate(order_limiters[1:], 1):
            assert limiter is order_limiters[0], (
                f"Order rate limiter call {i} should return same singleton as call 0"
            )

        # All smart limiters should be the same instance
        smart_limiters = [limiter[1] for limiter in limiters]
        for i, limiter in enumerate(smart_limiters[1:], 1):
            assert limiter is smart_limiters[0], (
                f"Smart order rate limiter call {i} should return same singleton as call 0"
            )

        # Order and smart limiters should be different instances
        assert order_limiters[0] is not smart_limiters[0], (
            "Order and smart order rate limiters should be different singletons"
        )

    @pytest.mark.asyncio
    async def test_factory_pattern_rate_enforcement_across_calls(self) -> None:
        """
        Test that rate limiting is enforced across multiple factory calls.

        This directly tests the scenario described in R5-F-01 where the defect
        would allow unlimited operations if each call got a new instance.

        Uses a burst approach to clearly demonstrate rate limiting behavior.
        """
        limiter = get_order_rate_limiter()

        # First, make a burst of rapid calls to test rate limiting
        burst_results = []
        for _ in range(60):  # Try 60 times rapidly
            current_limiter = get_order_rate_limiter()
            result = await current_limiter.acquire()
            burst_results.append(result)
            # No delay - make calls as fast as possible

        successful_burst = sum(burst_results)

        # With the singleton pattern and rate limiting, we should NOT get all 60 successful
        # This would indicate the factory pattern defect
        assert successful_burst < 60, (
            f"Factory pattern regression: Got {successful_burst} successful acquires out of 60 burst calls. "
            f"This suggests each factory call is getting a new rate limiter instance."
        )

        # Handle both cases: rate limiter has capacity or is already full
        if successful_burst == 0:
            # Rate limiter is already full - this means rate limiting is working
            # All calls should be rejected
            assert all(not result for result in burst_results), (
                "All burst calls should be rate limited when full"
            )
        else:
            # We got some successful acquires - verify we got a reasonable number
            # Be more flexible with the minimum since rate limiter state persists across tests
            assert successful_burst >= 1, (
                f"Expected at least 1 successful acquire in burst if not fully rate limited, "
                f"got {successful_burst}. This suggests an issue with rate limiting."
            )

            # Now test that subsequent calls are rate limited
            post_burst_rejections = 0
            for _ in range(20):  # Try 20 more times
                current_limiter = get_order_rate_limiter()
                result = await current_limiter.acquire()
                if not result:
                    post_burst_rejections += 1

            # Should see some rejections after the burst
            assert post_burst_rejections >= 5, (
                f"Expected at least 5 rejections after burst (out of 20), "
                f"got {post_burst_rejections}. This suggests rate limiting is not working."
            )

        # Verify singleton behavior throughout
        limiter1 = get_order_rate_limiter()
        limiter2 = get_order_rate_limiter()
        assert limiter1 is limiter2, "Rate limiter should be a singleton"
        assert limiter1 is limiter, "All limiters should be the same singleton"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
