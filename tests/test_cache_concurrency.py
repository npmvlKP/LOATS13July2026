"""
Concurrency stress test for cache thread-safety.
Tests that the cache can handle concurrent access from multiple threads.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from loats.utils.cache import CacheConfig, CacheManager


class TestCacheConcurrency:
    """Tests for cache thread-safety under concurrent access."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig(max_size=1000, ttl_seconds=60)
        return CacheManager(config)

    @pytest.mark.asyncio
    async def test_concurrent_get_set_operations(
        self, cache_manager: CacheManager
    ) -> None:
        """Test concurrent get and set operations from multiple threads."""
        await cache_manager.initialize()

        async def worker_thread(worker_id: int, num_operations: int = 100) -> list[str]:
            """Worker function that performs concurrent cache operations."""
            results = []

            for i in range(num_operations):
                # Set operation
                key = f"worker_{worker_id}_key_{i}"
                value = f"worker_{worker_id}_value_{i}"
                success = await cache_manager.set(key, value)
                results.append(f"set_{key}_{success}")

                # Get operation
                cached_value = await cache_manager.get(key)
                results.append(f"get_{key}_{cached_value == value}")

                # Small delay to simulate real work
                await asyncio.sleep(0.001)

            return results

        # Run multiple worker threads concurrently
        num_workers = 10
        tasks = [worker_thread(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)

        # Verify all operations completed successfully
        all_results = [item for sublist in results for item in sublist]
        set_operations = [r for r in all_results if r.startswith("set_")]
        get_operations = [r for r in all_results if r.startswith("get_")]

        # All set operations should succeed
        assert all("True" in op for op in set_operations)

        # All get operations should return correct values
        assert all("True" in op for op in get_operations)

        # Verify cache contains expected number of items
        stats = await cache_manager.get_cache_stats()
        assert stats["current_size"] == num_workers * 100  # 100 operations per worker

    @pytest.mark.asyncio
    async def test_concurrent_delete_operations(
        self, cache_manager: CacheManager
    ) -> None:
        """Test concurrent delete operations from multiple threads."""
        await cache_manager.initialize()

        # Pre-populate cache
        for i in range(50):
            await cache_manager.set(f"test_key_{i}", f"test_value_{i}")

        async def worker_thread(worker_id: int, num_deletes: int = 25) -> list[bool]:
            """Worker function that performs concurrent cache deletes."""
            results = []

            for i in range(num_deletes):
                key = f"test_key_{worker_id * num_deletes + i}"
                success = await cache_manager.delete(key)
                results.append(success)

                # Small delay to simulate real work
                await asyncio.sleep(0.001)

            return results

        # Run multiple worker threads concurrently
        num_workers = 2
        tasks = [worker_thread(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)

        # Verify all delete operations completed without errors
        all_results = [item for sublist in results for item in sublist]
        assert len(all_results) == num_workers * 25

    @pytest.mark.asyncio
    async def test_concurrent_clear_operations(
        self, cache_manager: CacheManager
    ) -> None:
        """Test concurrent clear operations from multiple threads."""
        await cache_manager.initialize()

        # Pre-populate cache
        for i in range(100):
            await cache_manager.set(f"test_key_{i}", f"test_value_{i}")

        async def worker_thread(worker_id: int) -> int:
            """Worker function that performs cache clear."""
            # Clear with pattern
            cleared = await cache_manager.clear(f"test_key_{worker_id}*")
            return cleared

        # Run multiple worker threads concurrently
        num_workers = 5
        tasks = [worker_thread(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)

        # Verify all clear operations completed without errors
        assert len(results) == num_workers
        assert all(isinstance(result, int) for result in results)

    @pytest.mark.asyncio
    async def test_concurrent_get_or_set_operations(
        self, cache_manager: CacheManager
    ) -> None:
        """Test concurrent get_or_set operations from multiple threads."""
        await cache_manager.initialize()

        async def fetch_function(key: str) -> str:
            """Mock fetch function for get_or_set."""
            return f"fresh_value_{key}"

        async def worker_thread(worker_id: int, num_operations: int = 50) -> list[str]:
            """Worker function that performs concurrent get_or_set operations."""
            results = []

            for i in range(num_operations):
                key = f"get_or_set_key_{worker_id}_{i}"

                # First call should fetch and cache
                value1 = await cache_manager.get_or_set(
                    key, lambda bound_key=key: fetch_function(bound_key)
                )
                results.append(f"first_{key}_{value1}")

                # Second call should return cached value
                value2 = await cache_manager.get_or_set(
                    key, lambda bound_key=key: fetch_function(bound_key)
                )
                results.append(f"second_{key}_{value2}")

                # Both should be the same
                assert value1 == value2

                # Small delay to simulate real work
                await asyncio.sleep(0.001)

            return results

        # Run multiple worker threads concurrently
        num_workers = 10
        tasks = [worker_thread(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)

        # Verify all operations completed successfully
        all_results = [item for sublist in results for item in sublist]
        assert len(all_results) == num_workers * 100  # 100 operations per worker

    @pytest.mark.asyncio
    async def test_stress_test_high_concurrency(
        self, cache_manager: CacheManager
    ) -> None:
        """Stress test with high concurrency to detect race conditions."""
        await cache_manager.initialize()

        async def mixed_operations(worker_id: int, num_ops: int = 200) -> int:
            """Perform mixed cache operations under high concurrency."""
            completed = 0

            for i in range(num_ops):
                key = f"stress_{worker_id}_{i}"
                value = f"stress_value_{worker_id}_{i}"

                # Randomly choose operation type
                op_type = i % 4

                if op_type == 0:
                    # Set operation
                    await cache_manager.set(key, value)
                elif op_type == 1:
                    # Get operation
                    await cache_manager.get(key)
                elif op_type == 2:
                    # Delete operation
                    await cache_manager.delete(key)
                else:
                    # Set operation (most common)
                    await cache_manager.set(key, value)

                completed += 1

            return completed

        # Run high number of concurrent workers
        num_workers = 20
        tasks = [mixed_operations(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)

        # Verify all operations completed
        total_completed = sum(results)
        assert total_completed == num_workers * 200

        # Verify no crashes or exceptions occurred
        stats = await cache_manager.get_cache_stats()
        assert stats["enabled"] is True

    @pytest.mark.asyncio
    async def test_thread_pool_concurrency(self, cache_manager: CacheManager) -> None:
        """Test cache operations from actual threading.ThreadPoolExecutor."""
        await cache_manager.initialize()

        def sync_worker(worker_id: int, num_ops: int = 50) -> list[str]:
            """Synchronous worker function for thread pool."""
            results = []

            # Create asyncio event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def async_work():
                for i in range(num_ops):
                    key = f"thread_pool_{worker_id}_{i}"
                    value = f"thread_pool_value_{worker_id}_{i}"

                    # Set operation
                    success = await cache_manager.set(key, value)
                    results.append(f"set_{key}_{success}")

                    # Get operation
                    cached_value = await cache_manager.get(key)
                    results.append(f"get_{key}_{cached_value == value}")

            try:
                loop.run_until_complete(async_work())
            finally:
                loop.close()

            return results

        # Run workers in thread pool
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(sync_worker, i) for i in range(5)]
            results = [future.result() for future in futures]

        # Verify all operations completed successfully
        all_results = [item for sublist in results for item in sublist]
        set_operations = [r for r in all_results if r.startswith("set_")]
        get_operations = [r for r in all_results if r.startswith("get_")]

        assert all("True" in op for op in set_operations)
        assert all("True" in op for op in get_operations)
