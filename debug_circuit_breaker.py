#!/usr/bin/env python3
"""
Debug script to check circuit breaker state after GET operations.
"""

import asyncio
from src.loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER, CircuitBreakerOpenError
from src.loats.openalgo import AsyncOpenAlgoClient
from unittest.mock import AsyncMock, patch

def debug_get_operations():
    """Debug GET operations circuit breaker behavior."""
    print("Debugging GET operations circuit breaker behavior...")

    # Reset circuit breaker
    OPENALGO_CIRCUIT_BREAKER.reset()
    print(f"Initial state: {OPENALGO_CIRCUIT_BREAKER.state.name}")
    print(f"Initial stats: {OPENALGO_CIRCUIT_BREAKER.stats}")

    # Mock the _request method to simulate failures
    async def mock_failing_request(*args, **kwargs):
        print(f"Mock request called: {args}, {kwargs}")
        raise ConnectionError("Simulated failure")

    # Test get_quotes (GET operation)
    with patch.object(AsyncOpenAlgoClient, '_request', side_effect=mock_failing_request):
        client = AsyncOpenAlgoClient("test_api_key")

        try:
            print("Calling get_quotes...")
            asyncio.run(client.get_quotes("TEST"))
        except ConnectionError as e:
            print(f"ConnectionError caught: {e}")
        except Exception as e:
            print(f"Other exception caught: {e}")

        print(f"State after call: {OPENALGO_CIRCUIT_BREAKER.state.name}")
        print(f"Stats after call: {OPENALGO_CIRCUIT_BREAKER.stats}")

if __name__ == "__main__":
    debug_get_operations()