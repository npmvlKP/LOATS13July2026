"""Thread-safety tests for circuit breaker (R5-3 fix).

Tests that circuit breaker state and statistics remain consistent under
parallel sync and async calls, verifying the thread-safety locks work correctly.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)


class TestCircuitBreakerThreadSafety:
    """Test thread-safety of circuit breaker under concurrent access."""

    def test_parallel_sync_calls_record_success(self):
        """Test that parallel sync calls safely record successes."""
        config = CircuitBreakerConfig(failure_threshold=10, success_threshold=5)
        cb = CircuitBreaker(name="test_sync_success", config=config)

        num_calls = 50

        def successful_call():
            return "success"

        # Execute parallel sync calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(cb.call, successful_call) for _ in range(num_calls)
            ]
            results = [f.result() for f in futures]

        # All calls should succeed
        assert all(r == "success" for r in results)

        # Stats should be consistent
        stats = cb.stats
        assert stats.total_calls == num_calls
        assert stats.successful_calls == num_calls
        assert stats.failed_calls == 0
        assert stats.consecutive_failures == 0

    def test_parallel_sync_calls_record_failure(self):
        """Test that parallel sync calls safely record failures."""
        config = CircuitBreakerConfig(failure_threshold=5, success_threshold=2)
        cb = CircuitBreaker(name="test_sync_failure", config=config)

        num_calls = 20
        failure_count = 0

        def failing_call():
            raise RuntimeError("Intentional failure")

        # Execute parallel sync calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cb.call, failing_call) for _ in range(num_calls)]
            for f in futures:
                try:
                    f.result()
                except RuntimeError:
                    failure_count += 1
                except CircuitBreakerOpenError:
                    # Circuit opened, this is expected
                    pass

        # At least failure_threshold calls should fail
        assert failure_count >= config.failure_threshold

        # Circuit should be open
        assert cb.state.name == "OPEN"

        # Stats should be consistent
        stats = cb.stats
        assert stats.failed_calls >= config.failure_threshold
        assert stats.consecutive_failures >= config.failure_threshold

    def test_parallel_async_calls_record_success(self):
        """Test that parallel async calls safely record successes."""
        config = CircuitBreakerConfig(failure_threshold=10, success_threshold=5)
        cb = CircuitBreaker(name="test_async_success", config=config)

        num_calls = 50

        async def successful_call():
            return "success"

        # Execute parallel async calls
        async def run_parallel():
            tasks = [cb.call_async(successful_call) for _ in range(num_calls)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_parallel())

        # All calls should succeed
        assert all(r == "success" for r in results)

        # Stats should be consistent
        stats = cb.stats
        assert stats.total_calls == num_calls
        assert stats.successful_calls == num_calls
        assert stats.failed_calls == 0
        assert stats.consecutive_failures == 0

    def test_parallel_async_calls_record_failure(self):
        """Test that parallel async calls safely record failures."""
        config = CircuitBreakerConfig(failure_threshold=5, success_threshold=2)
        cb = CircuitBreaker(name="test_async_failure", config=config)

        num_calls = 20
        failure_count = 0

        async def failing_call():
            raise RuntimeError("Intentional failure")

        # Execute parallel async calls
        async def run_parallel():
            tasks = []
            for _ in range(num_calls):
                try:
                    tasks.append(cb.call_async(failing_call))
                except CircuitBreakerOpenError:
                    pass
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(run_parallel())

        for result in results:
            if isinstance(result, Exception) and not isinstance(
                result, CircuitBreakerOpenError
            ):
                failure_count += 1

        # At least failure_threshold calls should fail
        assert failure_count >= config.failure_threshold

        # Circuit should be open
        assert cb.state.name == "OPEN"

        # Stats should be consistent
        stats = cb.stats
        assert stats.failed_calls >= config.failure_threshold
        assert stats.consecutive_failures >= config.failure_threshold

    def test_mixed_sync_async_calls(self):
        """Test that mixed sync and async calls are thread-safe."""
        config = CircuitBreakerConfig(failure_threshold=10, success_threshold=5)
        cb = CircuitBreaker(name="test_mixed", config=config)

        success_count = 0
        failure_count = 0
        num_sync_calls = 25
        num_async_calls = 25

        def successful_sync_call():
            return "sync_success"

        def failing_sync_call():
            raise RuntimeError("Sync failure")

        async def successful_async_call():
            return "async_success"

        async def failing_async_call():
            raise RuntimeError("Async failure")

        # Run mixed sync and async calls in parallel
        def run_sync_calls():
            nonlocal success_count, failure_count
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Mix of success and failure calls
                for i in range(num_sync_calls):
                    if i % 3 == 0:  # Every 3rd call fails
                        try:
                            executor.submit(cb.call, failing_sync_call).result()
                        except RuntimeError:
                            failure_count += 1
                        except CircuitBreakerOpenError:
                            pass
                    else:
                        try:
                            result = executor.submit(
                                cb.call, successful_sync_call
                            ).result()
                            if result == "sync_success":
                                success_count += 1
                        except CircuitBreakerOpenError:
                            pass

        async def run_async_calls():
            nonlocal success_count, failure_count
            tasks = []
            for i in range(num_async_calls):
                if i % 3 == 0:  # Every 3rd call fails
                    tasks.append(cb.call_async(failing_async_call))
                else:
                    tasks.append(cb.call_async(successful_async_call))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(
                    result, CircuitBreakerOpenError
                ):
                    failure_count += 1
                elif result in ("sync_success", "async_success"):
                    success_count += 1

        # Run sync and async concurrently in separate threads
        sync_thread = threading.Thread(target=run_sync_calls)
        async_thread = threading.Thread(target=lambda: asyncio.run(run_async_calls()))

        sync_thread.start()
        async_thread.start()
        sync_thread.join()
        async_thread.join()

        # Stats should be consistent
        stats = cb.stats
        assert stats.total_calls == success_count + failure_count
        assert stats.successful_calls == success_count
        assert stats.failed_calls == failure_count

    def test_concurrent_state_transitions(self):
        """Test that state transitions are thread-safe under concurrent access."""
        config = CircuitBreakerConfig(
            failure_threshold=3, success_threshold=2, timeout=0.5
        )
        cb = CircuitBreaker(name="test_state_transition", config=config)

        num_workers = 20
        num_iterations = 5

        def worker_func():
            for _ in range(num_iterations):
                try:
                    # Mix of success and failure
                    if time.time() % 2 < 1:
                        result = cb.call(lambda: "success")
                        assert result == "success"
                    else:
                        try:
                            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
                        except RuntimeError:
                            pass
                except CircuitBreakerOpenError:
                    # Wait for timeout and retry
                    time.sleep(0.6)

        # Run multiple workers concurrently
        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=worker_func)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Circuit breaker should maintain consistency
        stats = cb.stats
        assert stats.total_calls >= 0
        assert stats.successful_calls >= 0
        assert stats.failed_calls >= 0
        assert (
            stats.total_calls
            == stats.successful_calls + stats.failed_calls + stats.rejected_calls
        )

    def test_stats_consistency_under_load(self):
        """Test that statistics remain consistent under heavy concurrent load."""
        config = CircuitBreakerConfig(failure_threshold=100, success_threshold=10)
        cb = CircuitBreaker(name="test_stats_consistency", config=config)

        num_calls = 200

        def mixed_call(call_num):
            if call_num % 4 == 0:  # 25% failure rate
                raise RuntimeError("Intentional failure")
            return "success"

        # Execute many parallel calls
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(cb.call, mixed_call, i) for i in range(num_calls)
            ]
            results = []
            for f in futures:
                try:
                    results.append(("success", f.result()))
                except RuntimeError:
                    results.append(("failure", None))
                except CircuitBreakerOpenError:
                    results.append(("rejected", None))

        # Count results
        success_count = sum(1 for r, _ in results if r == "success")
        failure_count = sum(1 for r, _ in results if r == "failure")
        rejected_count = sum(1 for r, _ in results if r == "rejected")

        # Verify stats consistency
        stats = cb.stats
        assert stats.successful_calls == success_count
        assert stats.failed_calls == failure_count
        assert stats.rejected_calls == rejected_count
        assert stats.total_calls == success_count + failure_count + rejected_count

    def test_concurrent_get_status(self):
        """Test that get_status is thread-safe under concurrent access."""
        config = CircuitBreakerConfig(failure_threshold=10, success_threshold=5)
        cb = CircuitBreaker(name="test_get_status", config=config)

        num_threads = 20
        num_iterations = 10
        statuses = []

        def get_status_worker():
            for _ in range(num_iterations):
                status = cb.get_status()
                statuses.append(status)

        # Run concurrent status checks
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=get_status_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All status dictionaries should have the required fields
        required_fields = [
            "circuit_name",
            "name",
            "state",
            "failure_threshold",
            "success_threshold",
            "timeout",
            "total_calls",
            "successful_calls",
            "failed_calls",
            "rejected_calls",
            "consecutive_failures",
            "consecutive_successes",
        ]

        for status in statuses:
            assert all(field in status for field in required_fields)
            assert status["circuit_name"] == "test_get_status"
            assert status["name"] == "test_get_status"

    def test_concurrent_reset(self):
        """Test that reset is thread-safe under concurrent access."""
        config = CircuitBreakerConfig(failure_threshold=5, success_threshold=2)
        cb = CircuitBreaker(name="test_reset", config=config)

        # Generate some activity
        for _ in range(10):
            try:
                cb.call(lambda: "success")
            except CircuitBreakerOpenError:
                pass

        # Reset while other threads are accessing
        def reset_worker():
            cb.reset()

        def access_worker():
            try:
                cb.call(lambda: "success")
            except Exception:
                pass

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=reset_worker))

        for _ in range(10):
            threads.append(threading.Thread(target=access_worker))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # After all threads complete, stats should be reset or consistent
        stats = cb.stats
        # Either reset happened (all zeros) or we have consistent stats
        if stats.total_calls == 0:
            assert stats.successful_calls == 0
            assert stats.failed_calls == 0
            assert stats.consecutive_failures == 0
            assert stats.consecutive_successes == 0
        else:
            assert (
                stats.total_calls
                == stats.successful_calls + stats.failed_calls + stats.rejected_calls
            )
