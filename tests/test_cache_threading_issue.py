"""
Test to demonstrate the threading issue with asyncio.Lock in cache initialization.
This test shows that asyncio.Lock is not thread-safe when accessed from multiple threads.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from loats.utils.cache import CacheConfig, CacheManager


class TestCacheThreadingIssue:
    """Tests to demonstrate threading issues with asyncio.Lock."""

    @pytest.fixture
    def cache_manager(self) -> CacheManager:
        """Create test CacheManager instance."""
        config = CacheConfig(max_size=1000, ttl_seconds=60)
        return CacheManager(config)

    def test_asyncio_lock_not_thread_safe(self, cache_manager: CacheManager):
        """
        Test that demonstrates asyncio.Lock is not thread-safe.
        This test should fail or show issues when multiple threads try to initialize.
        """
        errors = []

        def worker(thread_id: int):
            """Worker function that tries to initialize cache from different thread."""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def init_cache():
                    await cache_manager.initialize()
                    return True

                # Try to initialize cache
                result = loop.run_until_complete(init_cache())
                return f"thread_{thread_id}_success_{result}"
            except Exception as e:
                errors.append(f"thread_{thread_id}_error_{e!s}")
                return f"thread_{thread_id}_error_{e!s}"
            finally:
                loop.close()

        # Run multiple threads trying to initialize simultaneously
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            results = [future.result() for future in futures]

        # Check if any errors occurred
        print(f"Results: {results}")
        print(f"Errors: {errors}")

        # The test passes if no errors occurred, but this doesn't mean the lock is thread-safe
        # It just means we didn't hit the race condition in this run
        assert len(errors) == 0, f"Threading errors occurred: {errors}"

    @pytest.mark.asyncio
    async def test_mixed_async_thread_access(self, cache_manager: CacheManager):
        """
        Test mixed access patterns: async calls from main thread and sync calls from worker threads.
        """
        await cache_manager.initialize()

        async def async_worker():
            """Async worker in main event loop."""
            for i in range(10):
                await cache_manager.set(f"async_key_{i}", f"async_value_{i}")
                await cache_manager.get(f"async_key_{i}")

        def sync_worker():
            """Sync worker in separate thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def worker_tasks():
                for i in range(10):
                    await cache_manager.set(f"sync_key_{i}", f"sync_value_{i}")
                    await cache_manager.get(f"sync_key_{i}")

            try:
                loop.run_until_complete(worker_tasks())
            finally:
                loop.close()

        # Run async and sync workers concurrently
        async_task = asyncio.create_task(async_worker())

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(sync_worker) for _ in range(2)]
            for future in futures:
                future.result()

        await async_task

        # Verify all operations completed
        stats = await cache_manager.get_cache_stats()
        assert stats["sets"] >= 30  # 10 async + 20 sync
        assert stats["hits"] >= 10  # async gets
