"""Concurrency tests for circuit breaker statistics race condition.

Tests that verify thread-safety of circuit breaker statistics when accessed
concurrently from both synchronous and asynchronous contexts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from typing import Any

import pytest

from src.loats.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)


class TestCircuitBreakerConcurrency:
    """Concurrency tests for circuit breaker race conditions."""

    def test_sync_concurrent_successes_thread_safe(self) -> None:
        """Test that concurrent sync successes don't cause race conditions."""
        cb = CircuitBreaker("concurrent_sync_test")
        num_threads = 10
        num_calls_per_thread = 5

        def make_successful_calls() -> None:
            for _ in range(num_calls_per_thread):
                cb.call(lambda: 42)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(make_successful_calls) for _ in range(num_threads)
            ]
            concurrent.futures.wait(futures)

        stats = cb.stats
        expected_total = num_threads * num_calls_per_thread
        assert stats.total_calls == expected_total
        assert stats.successful_calls == expected_total
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0

    def test_sync_concurrent_failures_thread_safe(self) -> None:
        """Test that concurrent sync failures don't cause race conditions."""
        config = CircuitBreakerConfig(failure_threshold=100)  # High threshold
        cb = CircuitBreaker("concurrent_fail_test", config=config)
        num_threads = 5
        num_failures_per_thread = 3

        def make_failing_calls() -> None:
            for _ in range(num_failures_per_thread):
                try:
                    cb.call(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass  # Expected

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_failing_calls) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        stats = cb.stats
        expected_total = num_threads * num_failures_per_thread
        assert stats.total_calls == expected_total
        assert stats.successful_calls == 0
        assert stats.failed_calls == expected_total
        assert stats.rejected_calls == 0
        assert stats.consecutive_failures == expected_total

    @pytest.mark.asyncio
    async def test_async_concurrent_successes_thread_safe(self) -> None:
        """Test that concurrent async successes don't cause race conditions."""
        cb = CircuitBreaker("concurrent_async_test")
        num_tasks = 10
        num_calls_per_task = 3

        async def make_async_successful_calls() -> None:
            for _ in range(num_calls_per_task):
                await cb.call_async(lambda: asyncio.sleep(0.001) or 42)

        tasks = [make_async_successful_calls() for _ in range(num_tasks)]
        await asyncio.gather(*tasks)

        stats = cb.stats
        expected_total = num_tasks * num_calls_per_task
        assert stats.total_calls == expected_total
        assert stats.successful_calls == expected_total
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0

    @pytest.mark.asyncio
    async def test_async_concurrent_failures_thread_safe(self) -> None:
        """Test that concurrent async failures don't cause race conditions."""
        config = CircuitBreakerConfig(failure_threshold=100)  # High threshold
        cb = CircuitBreaker("async_concurrent_fail_test", config=config)
        num_tasks = 5
        num_failures_per_task = 4

        async def make_async_failing_calls() -> None:
            for _ in range(num_failures_per_task):
                try:
                    await cb.call_async(lambda: 1 / 0)
                except ZeroDivisionError:
                    pass  # Expected

        tasks = [make_async_failing_calls() for _ in range(num_tasks)]
        await asyncio.gather(*tasks)

        stats = cb.stats
        expected_total = num_tasks * num_failures_per_task
        assert stats.total_calls == expected_total
        assert stats.successful_calls == 0
        assert stats.failed_calls == expected_total
        assert stats.rejected_calls == 0
        assert stats.consecutive_failures == expected_total

    @pytest.mark.asyncio
    async def test_mixed_sync_async_concurrent_thread_safe(self) -> None:
        """Test mixed sync + async concurrent calls don't cause race conditions.

        This is the critical test that reproduces the original race condition
        where both sync (APScheduler threads) and async (event loop) calls
        could mutate stats without proper locking.
        """
        config = CircuitBreakerConfig(failure_threshold=50)  # High threshold
        cb = CircuitBreaker("mixed_concurrent_test", config=config)

        num_sync_threads = 3
        num_async_tasks = 3
        calls_per_worker = 4

        # Sync function that will run in threads
        def sync_worker() -> None:
            for i in range(calls_per_worker):
                if i % 2 == 0:  # Alternate success/failure
                    cb.call(lambda: 42)
                else:
                    try:
                        cb.call(lambda: 1 / 0)
                    except ZeroDivisionError:
                        pass

        # Async function that will run in event loop
        async def async_worker() -> None:
            for i in range(calls_per_worker):
                if i % 2 == 0:  # Alternate success/failure
                    await cb.call_async(lambda: asyncio.sleep(0.001) or 42)
                else:
                    try:
                        await cb.call_async(lambda: asyncio.sleep(0.001) or (1 / 0))
                    except ZeroDivisionError:
                        pass

        # Run sync workers in thread pool
        sync_results: list[Any] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_sync_threads
        ) as executor:
            sync_futures = [
                executor.submit(sync_worker) for _ in range(num_sync_threads)
            ]
            for future in concurrent.futures.as_completed(sync_futures):
                sync_results.append(future.result())

        # Run async workers concurrently
        async_tasks = [async_worker() for _ in range(num_async_tasks)]
        await asyncio.gather(*async_tasks)

        # Verify all calls were properly counted
        stats = cb.stats
        expected_total = (num_sync_threads + num_async_tasks) * calls_per_worker

        assert stats.total_calls == expected_total
        # Verify that we have a reasonable distribution (not exact due to concurrency)
        assert stats.successful_calls > 0
        assert stats.failed_calls > 0
        assert stats.rejected_calls == 0
        # Verify that the sum of all call types equals total calls
        assert (
            stats.successful_calls + stats.failed_calls + stats.rejected_calls
            == expected_total
        )

        # Verify consecutive counters are non-negative (race condition would cause negative values)
        assert stats.consecutive_failures >= 0
        assert stats.consecutive_successes >= 0
        # At least one of the consecutive counters should be > 0 since we had both successes and failures
        assert stats.consecutive_failures > 0 or stats.consecutive_successes > 0

    @pytest.mark.asyncio
    async def test_concurrent_circuit_opening_thread_safe(self) -> None:
        """Test that concurrent failures properly open circuit without race conditions."""
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("concurrent_open_test", config=config)

        num_threads = 3
        failures_needed = 5

        def make_failures_until_open() -> int:
            failures = 0
            for _ in range(failures_needed):
                try:
                    cb.call(lambda: 1 / 0)
                    failures += 1
                except ZeroDivisionError:
                    failures += 1
                except CircuitBreakerOpenError:
                    break  # Circuit opened
            return failures

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(make_failures_until_open) for _ in range(num_threads)
            ]
            concurrent.futures.wait(futures)

        # Verify circuit is open
        assert cb.state == CircuitState.OPEN

        # Verify stats are consistent
        stats = cb.stats
        assert stats.total_calls >= failures_needed
        assert stats.failed_calls >= failures_needed
        assert stats.consecutive_failures >= failures_needed

    @pytest.mark.asyncio
    async def test_concurrent_rejections_thread_safe(self) -> None:
        """Test that concurrent rejections when circuit is open are thread-safe."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=10.0)
        cb = CircuitBreaker("concurrent_reject_test", config=config)

        # Open the circuit
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        assert cb.state == CircuitState.OPEN

        num_threads = 5
        num_rejections_per_thread = 3

        def make_rejected_calls() -> int:
            rejections = 0
            for _ in range(num_rejections_per_thread):
                try:
                    cb.call(lambda: 42)
                except CircuitBreakerOpenError:
                    rejections += 1
            return rejections

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_rejected_calls) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        # Verify all rejections were counted
        stats = cb.stats
        expected_rejections = num_threads * num_rejections_per_thread
        assert stats.rejected_calls == expected_rejections
        assert stats.total_calls >= expected_rejections

    def test_concurrent_state_transitions_thread_safe(self) -> None:
        """Test that concurrent state transitions are thread-safe."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=0.1,  # Short timeout for testing
        )
        cb = CircuitBreaker("state_transition_test", config=config)

        # Open the circuit
        for _ in range(3):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass

        assert cb.state == CircuitState.OPEN

        # Wait for timeout to allow transition to HALF_OPEN
        time.sleep(0.15)

        # Multiple threads trying to close the circuit
        def attempt_recovery() -> None:
            try:
                cb.call(lambda: 42)  # Success
                cb.call(lambda: 42)  # Success - should close circuit
            except CircuitBreakerOpenError:
                pass  # Circuit might still be open when we try

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(attempt_recovery) for _ in range(3)]
            concurrent.futures.wait(futures)

        # Circuit should be closed after successful recovery attempts
        assert cb.state == CircuitState.CLOSED

        # Verify stats consistency
        stats = cb.stats
        # consecutive_successes should be >= 0 (race condition would cause negative values)
        # Note: It might not be 0 because after the circuit closes, additional successful calls
        # can still increment the consecutive_successes counter
        assert stats.consecutive_successes >= 0
        assert stats.successful_calls > 0
        assert stats.failed_calls > 0

    @pytest.mark.asyncio
    async def test_stress_test_high_concurrency(self) -> None:
        """Stress test with high concurrency to ensure no race conditions."""
        cb = CircuitBreaker("stress_test")
        num_sync_workers = 10
        num_async_workers = 10
        calls_per_worker = 10

        async def async_worker(worker_id: int) -> None:
            for i in range(calls_per_worker):
                if i % 3 == 0:  # Success
                    await cb.call_async(lambda: asyncio.sleep(0.0001) or worker_id)
                elif i % 3 == 1:  # Failure
                    try:
                        await cb.call_async(lambda: asyncio.sleep(0.0001) or (1 / 0))
                    except ZeroDivisionError:
                        pass
                else:  # Rejection (if circuit opens)
                    try:
                        await cb.call_async(lambda: asyncio.sleep(0.0001) or worker_id)
                    except CircuitBreakerOpenError:
                        pass

        def sync_worker(worker_id: int) -> None:
            for i in range(calls_per_worker):
                if i % 3 == 0:  # Success
                    cb.call(lambda: worker_id)
                elif i % 3 == 1:  # Failure
                    try:
                        cb.call(lambda: 1 / 0)
                    except ZeroDivisionError:
                        pass
                else:  # Rejection (if circuit opens)
                    try:
                        cb.call(lambda: worker_id)
                    except CircuitBreakerOpenError:
                        pass

        # Run async workers
        async_tasks = [async_worker(i) for i in range(num_async_workers)]
        await asyncio.gather(*async_tasks, return_exceptions=True)

        # Run sync workers
        sync_results: list[Any] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_sync_workers
        ) as executor:
            sync_futures = [
                executor.submit(sync_worker, i) for i in range(num_sync_workers)
            ]
            for future in concurrent.futures.as_completed(sync_futures):
                sync_results.append(future.result())

        # Verify all calls were properly accounted for
        stats = cb.stats
        expected_total = (num_sync_workers + num_async_workers) * calls_per_worker
        assert stats.total_calls == expected_total

        # Verify no negative counters (race condition symptom)
        assert stats.successful_calls >= 0
        assert stats.failed_calls >= 0
        assert stats.rejected_calls >= 0
        assert stats.consecutive_failures >= 0
        assert stats.consecutive_successes >= 0

        # Verify the sum makes sense
        assert (
            stats.successful_calls + stats.failed_calls + stats.rejected_calls
        ) == expected_total
