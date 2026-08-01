"""
Integration tests OpenAlgo client real API calls.
Tests actual HTTP requests, latency, real API responses.
"""
import asyncio
import os
import time
from collections.abc import AsyncGenerator, Generator

import httpx
import pytest

from src.loats.alerts import alerts
from src.loats.config import get_settings
from src.loats.models import (
    HistoricalData,
    OrderType,
    ProductType,
    QuoteData,
    TransactionType,
)
from src.loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
)

settings = get_settings()

# Test configuration - use sandbox if available, otherwise skip integration tests
OPENALGO_SANDBOX_ENABLED = os.getenv("OPENALGO_SANDBOX_ENABLED", "false").lower() == "true"
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY") or (
    settings.openalgo_api_key.get_secret_value()
    if hasattr(settings.openalgo_api_key, "get_secret_value")
    else settings.openalgo_api_key
)
TEST_SYMBOL = "NIFTY"

def is_sandbox_available() -> bool:
    """Check OpenAlgo sandbox available testing."""
    if not OPENALGO_SANDBOX_ENABLED:
        return False
    try:
        # Test connection sandbox
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{settings.openalgo_base_url}/api/v1/ping",
                headers={"x-api-key": OPENALGO_API_KEY},
            )
            return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False

# Skip integration tests if sandbox not available
pytestmark = pytest.mark.skipif(
    not is_sandbox_available(), reason="OpenAlgo sandbox not available integration testing"
)

class TestOpenAlgoClientIntegration:
    """Integration tests OpenAlgoClient real API calls."""

    @pytest.fixture
    def client(self) -> Generator[OpenAlgoClient, None, None]:
        """Create real OpenAlgoClient instance integration testing."""
        client = OpenAlgoClient()
        yield client

    def test_get_quotes_real_api(self, client: OpenAlgoClient) -> None:
        """Test get_quotes real API call."""
        start_time = time.time()
        result = client.get_quotes([TEST_SYMBOL])
        latency = time.time() - start_time
        assert result["success"] is True
        assert TEST_SYMBOL in result["data"]
        assert isinstance(result["data"][TEST_SYMBOL]["last_price"], (int, float))
        assert latency < 2.0  # respond within 2 seconds

        # Validate model conversion
        quote = client._convert_to_quote(TEST_SYMBOL, result["data"][TEST_SYMBOL])
        assert isinstance(quote, QuoteData)
        assert quote.symbol == TEST_SYMBOL
        assert quote.last_price == result["data"][TEST_SYMBOL]["last_price"]

    def test_get_history_real_api(self, client: OpenAlgoClient) -> None:
        """Test get_history real API call."""
        start_time = time.time()
        result = client.get_history(
            symbol=TEST_SYMBOL,
            interval="1min",
            from_date="2023-01-01",
            to_date="2023-01-02",
        )
        latency = time.time() - start_time
        assert result["success"] is True
        assert len(result["data"]) > 0
        assert latency < 3.0  # respond within 3 seconds

        # Validate model conversion
        historical = client._convert_to_historical_data(
            TEST_SYMBOL, "1min", result["data"][0]
        )
        assert isinstance(historical, HistoricalData)
        assert historical.symbol == TEST_SYMBOL
        assert historical.interval == "1min"

    def test_error_handling_real_api(self, client: OpenAlgoClient) -> None:
        """Test error handling real API invalid symbol."""
        with pytest.raises(OpenAlgoAPIError) as exc_info:
            client.get_quotes(["INVALID_SYMBOL_123"])
        assert exc_info.value.status_code in (400, 404, 500)
        assert "error" in exc_info.value.message.lower()

    def test_kill_switch_real_scenario(self, client: OpenAlgoClient) -> None:
        """Test kill switch blocks order placement real scenario."""
        # Temporarily activate kill switch testing
        original_state = alerts.is_kill_switch_active()
        alerts.activate_kill_switch()
        try:
            with pytest.raises(KillSwitchError) as exc_info:
                client.place_order(
                    symbol=TEST_SYMBOL,
                    quantity=1,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                )
            assert "kill switch active" in str(exc_info.value).lower()
        finally:
            # Restore original kill switch state
            if not original_state:
                alerts.deactivate_kill_switch()

    def test_place_and_cancel_order(self, client: OpenAlgoClient) -> None:
        """Test complete order lifecycle: place then cancel."""
        # Place order
        place_result = client.place_order(
            symbol=TEST_SYMBOL,
            quantity=1,
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
        )
        assert place_result["success"] is True
        order_id = place_result["data"]["order_id"]

        # Cancel order
        cancel_result = client.cancel_order(order_id)
        assert cancel_result["success"] is True
        assert cancel_result["data"]["order_id"] == order_id
        assert cancel_result["data"]["status"] == "CANCELLED"

    def test_load_testing_multiple_requests(self, client: OpenAlgoClient) -> None:
        """Test client performance under multiple concurrent requests."""
        start_time = time.time()
        latencies = []
        # Make multiple requests test load handling
        for _ in range(5):
            request_start = time.time()
            result = client.get_quotes([TEST_SYMBOL])
            latencies.append(time.time() - request_start)
            assert result["success"] is True
            assert TEST_SYMBOL in result["data"]

        total_time = time.time() - start_time
        avg_latency = sum(latencies) / len(latencies)
        # handle 5 requests under 5 seconds
        assert total_time < 5.0
        # Average latency reasonable
        assert avg_latency < 1.5

class TestAsyncOpenAlgoClientIntegration:
    """Integration tests AsyncOpenAlgoClient real API calls."""

    @pytest.fixture
    async def async_client(self) -> AsyncGenerator[AsyncOpenAlgoClient, None]:
        """Create real AsyncOpenAlgoClient instance integration testing."""
        async with AsyncOpenAlgoClient() as client:
            yield client

    async def test_async_get_quotes_real_api(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async get_quotes real API call."""
        start_time = time.time()
        result = await async_client.get_quotes([TEST_SYMBOL])
        latency = time.time() - start_time
        assert result["success"] is True
        assert TEST_SYMBOL in result["data"]
        assert isinstance(result["data"][TEST_SYMBOL]["last_price"], (int, float))
        assert latency < 2.0  # respond within 2 seconds

    async def test_async_error_handling_real_api(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async error handling real API invalid symbol."""
        with pytest.raises(OpenAlgoAPIError) as exc_info:
            await async_client.get_quotes(["INVALID_SYMBOL_123"])
        assert exc_info.value.status_code in (400, 404, 500)
        assert "error" in exc_info.value.message.lower()

    async def test_async_kill_switch_real_scenario(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async kill switch blocks order placement real scenario."""
        # Temporarily activate kill switch testing
        original_state = alerts.is_kill_switch_active()
        alerts.activate_kill_switch()
        try:
            with pytest.raises(KillSwitchError) as exc_info:
                await async_client.place_order(
                    symbol=TEST_SYMBOL,
                    quantity=1,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                )
            assert "kill switch active" in str(exc_info.value).lower()
        finally:
            # Restore original kill switch state
            if not original_state:
                alerts.deactivate_kill_switch()

    async def test_async_load_testing(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async client performance under multiple concurrent requests."""
        async def make_request() -> float:
            req_start = time.time()
            result = await async_client.get_quotes([TEST_SYMBOL])
            assert result["success"] is True
            assert TEST_SYMBOL in result["data"]
            return time.time() - req_start

        start_time = time.time()
        tasks = [make_request() for _ in range(5)]
        latencies = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        # handle 5 concurrent requests under 3 seconds
        assert total_time < 3.0
        # Average latency reasonable
        assert sum(latencies) / len(latencies) < 1.5

class TestPerformanceBenchmarks:
    """Performance benchmarks OpenAlgo clients."""

    def test_latency_benchmark_sync(self, benchmark) -> None:
        """Benchmark sync client latency."""
        client = OpenAlgoClient()

        def get_quotes():
            return client.get_quotes([TEST_SYMBOL])

        result = benchmark(get_quotes)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_latency_benchmark_async(self, benchmark) -> None:
        """Benchmark async client latency."""
        async with AsyncOpenAlgoClient() as client:
            async def get_quotes():
                return await client.get_quotes([TEST_SYMBOL])

            result = await benchmark(get_quotes)
            assert result["success"] is True

    def test_throughput_benchmark(self) -> None:
        """Test client throughput under load."""
        client = OpenAlgoClient()
        start_time = time.time()
        request_count = 0
        # Make requests 5 seconds
        while time.time() - start_time < 5.0:
            result = client.get_quotes([TEST_SYMBOL])
            assert result["success"] is True
            request_count += 1
        # handle least 10 requests per second
        assert request_count >= 50  # 10 requests/sec * 5 seconds
