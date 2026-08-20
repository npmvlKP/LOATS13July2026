"""
Unit tests for synchronous rate limiter utility module.
Tests SyncRateLimiter class and synchronous factory functions.
"""

import threading
import time

from loats.config import get_settings
from loats.loats_logging import get_logger
from loats.utils.rate_limiter import (
    RateLimitExceededError,
    SyncRateLimiter,
    _reset_singletons_for_testing,
    get_sync_order_rate_limiter,
    get_sync_smart_order_rate_limiter,
)

logger = get_logger(__name__)


class TestSyncRateLimiter:
    """Tests for SyncRateLimiter (synchronous sliding window algorithm)."""

    def test_initialization_with_defaults(self) -> None:
        """Test initialization with default settings."""
        limiter = SyncRateLimiter()
        settings = get_settings()
        assert limiter.max_ops == settings.max_ops
        assert limiter.window_size == 1.0

    def test_initialization_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        limiter = SyncRateLimiter(max_ops=3, window_size=2.0)
        assert limiter.max_ops == 3
        assert limiter.window_size == 2.0
        assert len(limiter.timestamps) == 0

    def test_acquire_success(self) -> None:
        """Test successful token acquisition."""
        limiter = SyncRateLimiter(max_ops=5, window_size=1.0)

        # Should be able to acquire tokens up to max_ops
        for _i in range(5):
            result = limiter.acquire()
            assert result is True

        # Next acquisition should fail
        result = limiter.acquire()
        assert result is False

    def test_sliding_window(self) -> None:
        """Test sliding window behavior."""
        limiter = SyncRateLimiter(max_ops=3, window_size=1.0)

        # Fill the window
        for _ in range(3):
            limiter.acquire()

        # Wait slightly more than window size to ensure oldest timestamp expires
        time.sleep(1.1)

        # Should be able to acquire tokens again as old ones expire
        result = limiter.acquire()
        assert result is True

    def test_full_window_expiration(self) -> None:
        """Test full window expiration."""
        limiter = SyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the window
        for _ in range(2):
            limiter.acquire()

        # Wait slightly more than window size to ensure all timestamps expire
        time.sleep(0.6)

        # Should be able to acquire all tokens again
        for _ in range(2):
            result = limiter.acquire()
            assert result is True

    def test_wait_for_token_success(self) -> None:
        """Test waiting for token successfully."""
        limiter = SyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the window
        for _ in range(2):
            limiter.acquire()

        # This should wait and eventually succeed
        start_time = time.monotonic()
        limiter.wait_for_token()
        end_time = time.monotonic()

        # Should take approximately the time needed for oldest timestamp to expire
        assert end_time - start_time >= 0.1  # At least 100ms

    def test_wait_for_token_timeout(self) -> None:
        """Test wait_for_token timeout."""
        limiter = SyncRateLimiter(max_ops=1, window_size=2.0)

        # Consume the token
        limiter.acquire()

        # Start waiting in a thread
        def wait_and_catch():
            try:
                limiter.wait_for_token()
                return True
            except RateLimitExceededError:
                return False

        # Start thread
        thread = threading.Thread(target=wait_and_catch)
        thread.start()

        # Wait for thread to finish
        thread.join(timeout=0.2)  # Should timeout before completing

        # Verify thread is still alive (meaning it's waiting)
        assert thread.is_alive()

        # Clean up
        thread.join(timeout=0.1)


class TestSyncRateLimiterEdgeCases:
    """Tests for synchronous rate limiter edge cases."""

    def test_zero_max_ops(self) -> None:
        """Test rate limiter with zero max ops."""
        limiter = SyncRateLimiter(max_ops=0, window_size=1.0)

        # Should always fail to acquire
        result = limiter.acquire()
        assert result is False

    def test_very_small_window(self) -> None:
        """Test rate limiter with very small window."""
        limiter = SyncRateLimiter(max_ops=1, window_size=0.01)  # 10ms window

        # First acquisition should succeed
        result1 = limiter.acquire()
        assert result1 is True

        # Second acquisition should fail immediately
        result2 = limiter.acquire()
        assert result2 is False

        # Wait for window to expire
        time.sleep(0.02)  # 20ms

        # Should succeed again
        result3 = limiter.acquire()
        assert result3 is True

    def test_large_burst(self) -> None:
        """Test rate limiter with large burst of requests."""
        limiter = SyncRateLimiter(max_ops=10, window_size=1.0)

        # Try to acquire more than max_ops
        results = []
        for _ in range(20):
            result = limiter.acquire()
            results.append(result)

        # Should have exactly 10 successful acquisitions
        successful = sum(results)
        assert successful == 10

        # Wait for window to expire
        time.sleep(1.1)

        # Should be able to acquire again
        result = limiter.acquire()
        assert result is True


class TestSyncGlobalRateLimiters:
    """Tests for synchronous global rate limiter instances."""

    def setup_method(self) -> None:
        """Reset singletons before each test."""
        _reset_singletons_for_testing()

    def test_get_sync_order_rate_limiter(self) -> None:
        """Test getting synchronous order rate limiter."""
        limiter = get_sync_order_rate_limiter()
        assert isinstance(limiter, SyncRateLimiter)
        # Order rate limiter uses max_ops from settings
        settings = get_settings()
        assert limiter.max_ops == settings.max_ops
        assert limiter.window_size == 1.0

    def test_get_sync_smart_order_rate_limiter(self) -> None:
        """Test getting synchronous smart order rate limiter."""
        limiter = get_sync_smart_order_rate_limiter()
        assert isinstance(limiter, SyncRateLimiter)
        # Smart order rate limiter uses max_ops from settings
        settings = get_settings()
        assert limiter.max_ops == settings.max_ops
        assert limiter.window_size == 1.0

    def test_sync_rate_limiter_singleton_behavior(self) -> None:
        """Test that synchronous rate limiters are singletons."""
        limiter1 = get_sync_order_rate_limiter()
        limiter2 = get_sync_order_rate_limiter()
        # Should be the same instance (singleton behavior)
        assert limiter1 is limiter2

        smart_limiter1 = get_sync_smart_order_rate_limiter()
        smart_limiter2 = get_sync_smart_order_rate_limiter()
        # Should be the same instance (singleton behavior)
        assert smart_limiter1 is smart_limiter2

        # Order and smart order limiters should be different instances (different singletons)
        assert limiter1 is not smart_limiter1

        # All should have default max_ops from settings
        settings = get_settings()
        assert limiter1.max_ops == settings.max_ops
        assert limiter2.max_ops == settings.max_ops
        assert smart_limiter1.max_ops == settings.max_ops
        assert smart_limiter2.max_ops == settings.max_ops

    def test_sync_rate_limiter_custom_parameters(self) -> None:
        """Test synchronous rate limiter with custom parameters."""
        # Reset to ensure clean state
        _reset_singletons_for_testing()

        # Get limiter with custom parameters
        limiter1 = get_sync_order_rate_limiter(max_ops=10, window_size=2.0)
        assert limiter1.max_ops == 10
        assert limiter1.window_size == 2.0

        # Get another limiter with same parameters - should be same instance
        limiter2 = get_sync_order_rate_limiter(max_ops=10, window_size=2.0)
        assert limiter1 is limiter2

        # Get limiter with different parameters - should be different instance
        limiter3 = get_sync_order_rate_limiter(max_ops=5, window_size=1.0)
        assert limiter1 is not limiter3
        assert limiter3.max_ops == 5
        assert limiter3.window_size == 1.0

    def test_sync_rate_limiter_default_ignores_custom_params(self) -> None:
        """Test that default singleton ignores custom parameters (F6-C-01)."""
        # Reset to ensure clean state
        _reset_singletons_for_testing()

        # Get default singleton first
        default_limiter = get_sync_order_rate_limiter()
        assert default_limiter.max_ops == get_settings().max_ops
        assert default_limiter.window_size == 1.0

        # Now try to get with custom parameters - should return default singleton
        custom_limiter = get_sync_order_rate_limiter(max_ops=20, window_size=3.0)
        assert custom_limiter is default_limiter  # Should be same instance
        assert (
            custom_limiter.max_ops == get_settings().max_ops
        )  # Should use default max_ops
        assert custom_limiter.window_size == 1.0  # Should use default window_size

    def test_sync_smart_rate_limiter_default_ignores_custom_params(self) -> None:
        """Test that smart order default singleton ignores custom parameters."""
        # Reset to ensure clean state
        _reset_singletons_for_testing()

        # Get default singleton first
        default_limiter = get_sync_smart_order_rate_limiter()
        assert default_limiter.max_ops == get_settings().max_ops
        assert default_limiter.window_size == 1.0

        # Now try to get with custom parameters - should return default singleton
        custom_limiter = get_sync_smart_order_rate_limiter(max_ops=20, window_size=3.0)
        assert custom_limiter is default_limiter  # Should be same instance
        assert (
            custom_limiter.max_ops == get_settings().max_ops
        )  # Should use default max_ops
        assert custom_limiter.window_size == 1.0  # Should use default window_size


class TestSyncRateLimiterConcurrency:
    """Tests for synchronous rate limiter concurrency behavior."""

    def test_concurrent_access(self) -> None:
        """Test concurrent access to synchronous rate limiter."""
        limiter = SyncRateLimiter(max_ops=5, window_size=1.0)

        def worker(worker_id: int) -> bool:
            """Worker function that tries to acquire token."""
            try:
                return limiter.acquire()
            except Exception:
                return False

        # Create multiple threads
        threads = []
        results = []

        def worker_wrapper():
            results.append(worker(0))

        # Start 10 threads
        for _ in range(10):
            thread = threading.Thread(target=worker_wrapper)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have exactly 5 successful acquisitions
        successful = sum(results)
        assert successful == 5

    def test_concurrent_wait(self) -> None:
        """Test concurrent waiting for tokens."""
        limiter = SyncRateLimiter(max_ops=2, window_size=0.5)

        # Fill the limiter
        limiter.acquire()
        limiter.acquire()

        results = []
        threads = []

        def worker(worker_id: int) -> None:
            """Worker function that waits for token."""
            try:
                limiter.wait_for_token()
                results.append(True)
            except Exception:
                results.append(False)

        # Start 3 threads
        for i in range(3):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for threads to complete (they should all eventually succeed)
        for thread in threads:
            thread.join(timeout=5.0)

        # All workers should have succeeded
        assert len(results) == 3
        assert all(results)


class TestSyncRateLimiterIntegration:
    """Integration tests for synchronous rate limiter with real timing."""

    def test_sustained_rate(self) -> None:
        """Test sustained rate over multiple windows."""
        limiter = SyncRateLimiter(max_ops=5, window_size=0.5)  # 5 ops per 500ms

        start_time = time.monotonic()
        successful_ops = 0

        # Try to perform operations at a sustained rate
        while time.monotonic() - start_time < 2.0:  # Run for 2 seconds
            result = limiter.acquire()
            if result:
                successful_ops += 1
            time.sleep(0.05)  # Small delay between attempts

        end_time = time.monotonic()
        duration = end_time - start_time

        # Should be close to expected rate (5 ops per 0.5s = 10 ops per second)
        expected_ops = int(duration * 10)  # 10 ops per second
        tolerance = max(2, int(expected_ops * 0.2))  # 20% tolerance

        assert abs(successful_ops - expected_ops) <= tolerance

    def test_burst_then_sustained(self) -> None:
        """Test burst followed by sustained rate."""
        limiter = SyncRateLimiter(max_ops=3, window_size=1.0)

        # Initial burst - should get 3 successful operations
        burst_results = []
        for _ in range(5):
            result = limiter.acquire()
            burst_results.append(result)

        burst_successful = sum(burst_results)
        assert burst_successful == 3

        # Wait for window to expire so we can acquire more
        time.sleep(1.1)

        # Should be able to get more operations
        second_burst_results = []
        for _ in range(3):
            result = limiter.acquire()
            second_burst_results.append(result)

        second_burst_successful = sum(second_burst_results)
        assert second_burst_successful >= 1  # Should get at least 1
        assert second_burst_successful <= 3  # Should get at most 3
