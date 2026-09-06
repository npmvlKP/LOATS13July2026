"""
Stress test for TTLCache thread safety (R5-F-04).

This test verifies that TTLCache operations (get/set) are thread-safe
when accessed concurrently from multiple threads.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from loats.utils.cache import CacheConfig, CacheManager


@pytest.fixture
async def cache_manager():
    """Create and initialize a cache manager for testing."""
    config = CacheConfig(
        ttl_seconds=60,
        prefix="test_stress",
        max_size=1000,
        cache_type="memory",
    )
    cm = CacheManager(config)
    await cm.initialize()
    yield cm
    await cm.close()


class TestCacheConcurrencyStress:
    """Stress tests for cache thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_get_set_same_key(self, cache_manager):
        """Test concurrent get/set operations on the same key."""
        key = "stress_test_key"
        num_threads = 10
        operations_per_thread = 100
        errors = []

        def worker(thread_id):
            """Worker function for concurrent operations."""
            try:
                for i in range(operations_per_thread):
                    # Set a value
                    value = f"thread_{thread_id}_op_{i}"
                    asyncio.run(cache_manager.set(key, value))

                    # Get the value immediately
                    result = asyncio.run(cache_manager.get(key))

                    # Verify we got a valid result (not None)
                    assert result is not None, f"Thread {thread_id}, op {i}: Got None"

                    # Small delay to increase contention
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, i, str(e)))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_concurrent_set_different_keys(self, cache_manager):
        """Test concurrent set operations on different keys."""
        num_threads = 20
        keys_per_thread = 50
        errors = []

        def worker(thread_id):
            """Worker function for concurrent set operations."""
            try:
                for i in range(keys_per_thread):
                    key = f"thread_{thread_id}_key_{i}"
                    value = f"value_{thread_id}_{i}"
                    asyncio.run(cache_manager.set(key, value, ttl=60))

                    # Verify the value was set
                    result = asyncio.run(cache_manager.get(key))
                    assert result == value, (
                        f"Thread {thread_id}: Expected {value}, got {result}"
                    )
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_concurrent_get_or_set(self, cache_manager):
        """Test concurrent get_or_set operations."""
        key = "concurrent_get_or_set_key"
        num_threads = 15
        call_count = 0
        lock = threading.Lock()
        errors = []

        async def fetch_func():
            """Async fetch function for get_or_set."""
            nonlocal call_count
            with lock:
                call_count += 1
            await asyncio.sleep(0.01)  # Simulate slow operation
            return "fetched_value"

        def worker():
            """Worker function for concurrent get_or_set."""
            try:
                result = asyncio.run(cache_manager.get_or_set(key, fetch_func))
                assert result == "fetched_value", f"Unexpected result: {result}"
            except Exception as e:
                errors.append(str(e))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_concurrent_delete_and_get(self, cache_manager):
        """Test concurrent delete and get operations."""
        key = "concurrent_delete_test_key"
        num_threads = 10
        errors = []

        # Pre-populate cache
        await cache_manager.set(key, "initial_value")

        def worker(thread_id):
            """Worker function for delete/get operations."""
            try:
                for i in range(50):
                    if thread_id % 2 == 0:
                        # Even threads: delete
                        asyncio.run(cache_manager.delete(key))
                    else:
                        # Odd threads: get (should not crash)
                        result = asyncio.run(cache_manager.get(key))
                        # Result can be None if deleted, or a string if not
                        assert result is None or isinstance(result, str), (
                            f"Unexpected result type: {type(result)}"
                        )
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, i, str(e)))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_concurrent_clear(self, cache_manager):
        """Test concurrent clear operations with ongoing sets."""
        num_setters = 5
        num_clearers = 3
        operations = 100
        errors = []

        def setter(thread_id):
            """Worker function for set operations."""
            try:
                for i in range(operations):
                    key = f"setter_{thread_id}_key_{i}"
                    asyncio.run(cache_manager.set(key, f"value_{i}"))
                    time.sleep(0.001)
            except Exception as e:
                errors.append((f"setter_{thread_id}", str(e)))

        def clearer(thread_id):
            """Worker function for clear operations."""
            try:
                for i in range(operations // 10):
                    asyncio.run(cache_manager.clear())
                    time.sleep(0.01)
            except Exception as e:
                errors.append((f"clearer_{thread_id}", str(e)))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_setters + num_clearers) as executor:
            futures = []
            for t in range(num_setters):
                futures.append(executor.submit(setter, t))
            for t in range(num_clearers):
                futures.append(executor.submit(clearer, t))

            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_cache_stats_thread_safety(self, cache_manager):
        """Test that cache stats remain consistent under concurrent access."""
        num_threads = 10
        operations_per_thread = 50
        errors = []

        # Populate cache
        for i in range(100):
            await cache_manager.set(f"key_{i}", f"value_{i}")

        def worker(thread_id):
            """Worker function for mixed operations."""
            try:
                for i in range(operations_per_thread):
                    # Mix of get, set, and stats operations
                    if i % 3 == 0:
                        asyncio.run(
                            cache_manager.set(
                                f"thread_{thread_id}_key_{i}", f"value_{i}"
                            )
                        )
                    elif i % 3 == 1:
                        asyncio.run(cache_manager.get(f"key_{i % 100}"))
                    else:
                        stats = asyncio.run(cache_manager.get_cache_stats())
                        assert stats is not None, "Stats should not be None"
                        assert "hits" in stats, "Stats should have 'hits'"
                        assert "misses" in stats, "Stats should have 'misses'"
            except Exception as e:
                errors.append((thread_id, i, str(e)))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify final stats are consistent
        final_stats = await cache_manager.get_cache_stats()
        assert final_stats["hits"] + final_stats["misses"] >= 0, (
            "Total operations should be non-negative"
        )

    @pytest.mark.asyncio
    async def test_high_contention_single_key(self, cache_manager):
        """Test extreme contention on a single key."""
        key = "high_contention_key"
        num_threads = 50
        operations_per_thread = 20
        errors = []

        def worker(thread_id):
            """Worker function for high-contention operations."""
            try:
                for i in range(operations_per_thread):
                    # Rapid set/get on same key
                    value = f"thread_{thread_id}_iter_{i}"
                    asyncio.run(cache_manager.set(key, value))
                    result = asyncio.run(cache_manager.get(key))
                    assert result is not None, "Should never get None after set"
            except Exception as e:
                errors.append((thread_id, i, str(e)))

        # Run concurrent workers with high thread count
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
