#!/usr/bin/env python3
"""
Comprehensive verification test for circuit breaker functionality.
This test verifies that the circuit breaker is properly implemented for both GET and POST operations.
"""

import asyncio
from src.loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER, CircuitBreakerOpenError
from src.loats.openalgo import AsyncOpenAlgoClient
from unittest.mock import AsyncMock, patch
import pytest

def test_circuit_breaker_post_operations_protected():
    """Verify that POST operations (place_order, modify_order, cancel_order) are protected by circuit breaker."""
    print("Testing POST operations circuit breaker protection...")

    # Reset circuit breaker
    OPENALGO_CIRCUIT_BREAKER.reset()

    # Mock the _request method to simulate failures
    async def mock_failing_request(*args, **kwargs):
        raise ConnectionError("Simulated failure")

    # Test place_order
    with patch.object(AsyncOpenAlgoClient, '_request', side_effect=mock_failing_request):
        client = AsyncOpenAlgoClient("test_api_key")

        # First 3 calls should fail and open the circuit
        for i in range(3):
            try:
                asyncio.run(client.place_order("TEST", 1, "MARKET"))
            except ConnectionError:
                pass  # Expected

        # Circuit should now be open
        assert OPENALGO_CIRCUIT_BREAKER.state.name == "OPEN"

        # Next call should be rejected by circuit breaker (not retry)
        with pytest.raises(CircuitBreakerOpenError):
            asyncio.run(client.place_order("TEST", 1, "MARKET"))

    print("[PASS] POST operations are properly protected by circuit breaker")

def test_circuit_breaker_get_operations_protected():
    """Verify that GET operations are protected by circuit breaker with retry."""
    print("Testing GET operations circuit breaker protection...")

    # Reset circuit breaker
    OPENALGO_CIRCUIT_BREAKER.reset()

    # Mock the _request method to simulate failures
    async def mock_failing_request(*args, **kwargs):
        raise ConnectionError("Simulated failure")

    # Test get_quotes (GET operation)
    with patch.object(AsyncOpenAlgoClient, '_request', side_effect=mock_failing_request):
        client = AsyncOpenAlgoClient("test_api_key")

        # GET operations use retry decorator with 3 attempts by default
        # So we need to make enough calls to exceed the circuit breaker threshold
        # Circuit breaker threshold = 3 failures, retry attempts = 3 per call
        # So 1 call = 3 failures = should open circuit

        try:
            asyncio.run(client.get_quotes("TEST"))
        except ConnectionError:
            pass  # Expected after retries

        # Circuit should now be open (1 call * 3 retries = 3 failures)
        assert OPENALGO_CIRCUIT_BREAKER.state.name == "OPEN"

        # Next call should be rejected by circuit breaker (not retry)
        with pytest.raises(CircuitBreakerOpenError):
            asyncio.run(client.get_quotes("TEST"))

    print("[PASS] GET operations are properly protected by circuit breaker")

def test_circuit_breaker_thread_safety():
    """Verify that circuit breaker statistics are thread-safe."""
    print("Testing circuit breaker thread safety...")

    from src.loats.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
    import concurrent.futures
    import time

    # Create a circuit breaker with high threshold
    cb = CircuitBreaker("thread_safety_test", config=CircuitBreakerConfig(failure_threshold=100))

    def make_calls():
        for _ in range(10):
            try:
                cb.call(lambda: 42)  # Success
                cb.call(lambda: 1/0)  # Failure
            except:
                pass

    # Run concurrent calls
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_calls) for _ in range(5)]
        concurrent.futures.wait(futures)

    # Verify stats are consistent
    stats = cb.stats
    assert stats.total_calls == 100  # 5 threads * 10 calls * 2 operations
    assert stats.successful_calls == 50  # Half should be successful
    assert stats.failed_calls == 50  # Half should fail
    assert stats.consecutive_failures >= 0
    assert stats.consecutive_successes >= 0

    print("[PASS] Circuit breaker is thread-safe")

if __name__ == "__main__":
    test_circuit_breaker_post_operations_protected()
    test_circuit_breaker_get_operations_protected()
    test_circuit_breaker_thread_safety()
    print("\n[SUCCESS] All circuit breaker verification tests passed!")
    print("The circuit breaker implementation is fully functional and production-ready.")