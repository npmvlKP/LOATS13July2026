"""
Regression test for F6-C-01: Rate limiter factory functions must respect settings.max_ops.

This test verifies that the rate limiter factory functions properly use the configured
settings.max_ops value instead of the hardcoded 50 ops/sec value.

The issue: Factory functions (get_order_rate_limiter, get_smart_order_rate_limiter,
get_sync_order_rate_limiter, get_sync_smart_order_rate_limiter) were hardcoding max_ops=50
instead of using settings.max_ops (which is configured to 3).

This caused the rate limiters to allow 50 operations per second instead of the CMP-mandated
limit of 3 operations per second, violating compliance requirements.
"""

import asyncio
import pytest

from loats.config import get_settings
from loats.utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
    get_sync_order_rate_limiter,
    get_sync_smart_order_rate_limiter,
    _reset_singletons_for_testing,
)

class TestRateLimiterSettingsIntegration:
    """Test that rate limiter factories respect settings.max_ops."""

    def setup_method(self) -> None:
        """Reset singletons before each test to ensure clean state."""
        _reset_singletons_for_testing()

    def teardown_method(self) -> None:
        """Reset singletons after each test to avoid cross-test contamination."""
        _reset_singletons_for_testing()

    @pytest.mark.asyncio
    async def test_order_rate_limiter_uses_settings_max_ops(self) -> None:
        """
        Test that get_order_rate_limiter() uses settings.max_ops instead of hardcoded 50.

        This is the core regression test for F6-C-01.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get the default rate limiter (no max_ops argument)
        limiter = get_order_rate_limiter()

        # Verify it uses settings.max_ops, not the hardcoded 50
        assert limiter.max_ops == expected_max_ops, (
            f"Order rate limiter should use settings.max_ops ({expected_max_ops}), "
            f"but got {limiter.max_ops}. This indicates the F6-C-01 regression is present."
        )

        # Verify the window size is correct
        assert limiter.window_size == 1.0

    @pytest.mark.asyncio
    async def test_smart_order_rate_limiter_uses_settings_max_ops(self) -> None:
        """
        Test that get_smart_order_rate_limiter() uses settings.max_ops instead of hardcoded 50.

        This is the core regression test for F6-C-01.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get the default smart rate limiter (no max_ops argument)
        limiter = get_smart_order_rate_limiter()

        # Verify it uses settings.max_ops, not the hardcoded 50
        assert limiter.max_ops == expected_max_ops, (
            f"Smart order rate limiter should use settings.max_ops ({expected_max_ops}), "
            f"but got {limiter.max_ops}. This indicates the F6-C-01 regression is present."
        )

        # Verify the window size is correct
        assert limiter.window_size == 1.0

    def test_sync_order_rate_limiter_uses_settings_max_ops(self) -> None:
        """
        Test that get_sync_order_rate_limiter() uses settings.max_ops instead of hardcoded 50.

        This is the core regression test for F6-C-01.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get the default sync rate limiter (no max_ops argument)
        limiter = get_sync_order_rate_limiter()

        # Verify it uses settings.max_ops, not the hardcoded 50
        assert limiter.max_ops == expected_max_ops, (
            f"Sync order rate limiter should use settings.max_ops ({expected_max_ops}), "
            f"but got {limiter.max_ops}. This indicates the F6-C-01 regression is present."
        )

        # Verify the window size is correct
        assert limiter.window_size == 1.0

    def test_sync_smart_order_rate_limiter_uses_settings_max_ops(self) -> None:
        """
        Test that get_sync_smart_order_rate_limiter() uses settings.max_ops instead of hardcoded 50.

        This is the core regression test for F6-C-01.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get the default sync smart rate limiter (no max_ops argument)
        limiter = get_sync_smart_order_rate_limiter()

        # Verify it uses settings.max_ops, not the hardcoded 50
        assert limiter.max_ops == expected_max_ops, (
            f"Sync smart order rate limiter should use settings.max_ops ({expected_max_ops}), "
            f"but got {limiter.max_ops}. This indicates the F6-C-01 regression is present."
        )

        # Verify the window size is correct
        assert limiter.window_size == 1.0

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_settings_max_ops(self) -> None:
        """
        Test that the rate limiter actually enforces the settings.max_ops limit.

        This test verifies that the rate limiter doesn't just have the correct max_ops value,
        but actually enforces it by limiting operations.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get the rate limiter
        limiter = get_order_rate_limiter()

        # Make a burst of calls to test rate limiting
        successful_acquires = 0
        for _ in range(expected_max_ops + 10):  # Try more than the limit
            result = await limiter.acquire()
            if result:
                successful_acquires += 1

        # We should not exceed the max_ops limit
        assert successful_acquires <= expected_max_ops, (
            f"Rate limiter allowed {successful_acquires} operations, "
            f"but should enforce max_ops={expected_max_ops}. "
            f"This indicates rate limiting is not working correctly."
        )

        # We should get at least some successful acquires (unless rate limiter was already full)
        if successful_acquires == 0:
            # Rate limiter was already full - this is acceptable
            # Verify that all subsequent calls are also rejected
            for _ in range(5):
                result = await limiter.acquire()
                assert not result, "All calls should be rejected when rate limiter is full"
        else:
            # We got some successful acquires - verify we didn't exceed the limit
            assert successful_acquires >= 1, (
                f"Expected at least 1 successful acquire, got {successful_acquires}. "
                f"This suggests an issue with rate limiting."
            )

    @pytest.mark.asyncio
    async def test_factory_singleton_with_correct_max_ops(self) -> None:
        """
        Test that factory functions return singletons with correct max_ops.

        This verifies both the singleton pattern and the correct max_ops configuration.
        """
        settings = get_settings()
        expected_max_ops = settings.max_ops

        # Get multiple instances through the factory
        limiters = []
        for _ in range(5):
            limiter = get_order_rate_limiter()
            limiters.append(limiter)

        # All instances should be the same singleton
        for i, limiter in enumerate(limiters[1:], 1):
            assert limiter is limiters[0], (
                f"Factory call {i} should return same singleton as call 0"
            )

        # The singleton should have the correct max_ops
        assert limiters[0].max_ops == expected_max_ops, (
            f"Singleton should have max_ops={expected_max_ops}, got {limiters[0].max_ops}"
        )

    @pytest.mark.asyncio
    async def test_custom_max_ops_still_works(self) -> None:
        """
        Test that custom max_ops values still work when explicitly provided.

        This ensures we didn't break the ability to override max_ops when needed.
        """
        custom_max_ops = 10

        # Get rate limiter with custom max_ops
        limiter = get_order_rate_limiter(max_ops=custom_max_ops)

        # Verify it uses the custom value
        assert limiter.max_ops == custom_max_ops, (
            f"Custom max_ops should be {custom_max_ops}, got {limiter.max_ops}"
        )

        # Verify it actually enforces the custom limit
        successful_acquires = 0
        for _ in range(custom_max_ops + 5):
            result = await limiter.acquire()
            if result:
                successful_acquires += 1

        assert successful_acquires <= custom_max_ops, (
            f"Custom rate limiter allowed {successful_acquires} operations, "
            f"but should enforce max_ops={custom_max_ops}"
        )

    def test_settings_max_ops_value(self) -> None:
        """
        Test that settings.max_ops has the expected CMP-mandated value.

        This verifies the configuration is correct.
        """
        settings = get_settings()

        # The CMP mandates max_ops=3 for compliance
        expected_max_ops = 3
        assert settings.max_ops == expected_max_ops, (
            f"settings.max_ops should be {expected_max_ops} for CMP compliance, "
            f"got {settings.max_ops}"
        )

if __name__ == "__main__":
    pytest.main([__file__, "-v"])