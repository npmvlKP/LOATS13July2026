#!/usr/bin/env python3
"""
Comprehensive test suite for openalgo.py module.

This test file covers the main functionality of the OpenAlgo client
to address the 33.7% coverage issue.
"""

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.loats.alerts import AlertSystem
from src.loats.database import Database
from src.loats.models import (
    HistoricalData,
    Order,
    OrderStatus,
    OrderType,
    OrderVariety,
    Position,
    ProductType,
    QuoteData,
    TransactionType,
)
from src.loats.openalgo import (
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
    _async_check_kill_switch,
    _check_kill_switch,
    _get_idempotency_key,
    _order_payload_digest,
)
from src.loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()

        yield db

        # Clean up
        db.close_all()

@pytest.fixture
def mock_alerts():
    """Create a mock AlertSystem for testing."""
    alerts = MagicMock(spec=AlertSystem)
    alerts.is_kill_switch_active.return_value = False
    return alerts

@pytest.fixture
def openalgo_client():
    """Create an OpenAlgoClient instance for testing."""
    return OpenAlgoClient()

class TestOpenAlgoUtilities(unittest.IsolatedAsyncioTestCase):
    """Test suite for OpenAlgo utility functions."""

    def test_get_idempotency_key(self):
        """Test idempotency key generation and caching."""
        # Test that the same identity returns the same key
        key1 = _get_idempotency_key("test_identity_1")
        key2 = _get_idempotency_key("test_identity_1")
        assert key1 == key2

        # Test that different identities return different keys
        key3 = _get_idempotency_key("test_identity_2")
        assert key1 != key3

        # Test that keys expire after TTL
        with patch("src.loats.openalgo._IDEMPOTENCY_TTL_SECONDS", 0.01):
            with patch("src.loats.openalgo.time.monotonic", return_value=0):
                key4 = _get_idempotency_key("test_identity_3")
                with patch("src.loats.openalgo.time.monotonic", return_value=1):
                    key5 = _get_idempotency_key("test_identity_3")
                    assert key4 != key5

    def test_order_payload_digest(self):
        """Test order payload digest generation."""
        payload1 = {"symbol": "TEST", "quantity": 10, "order_type": "MARKET"}
        payload2 = {"symbol": "TEST", "quantity": 10, "order_type": "MARKET"}
        payload3 = {"symbol": "TEST", "quantity": 20, "order_type": "MARKET"}

        # Test that identical payloads produce identical digests
        digest1 = _order_payload_digest(payload1)
        digest2 = _order_payload_digest(payload2)
        assert digest1 == digest2

        # Test that different payloads produce different digests
        digest3 = _order_payload_digest(payload3)
        assert digest1 != digest3

        # Test that order of keys doesn't matter (canonical serialization)
        payload4 = {"order_type": "MARKET", "quantity": 10, "symbol": "TEST"}
        digest4 = _order_payload_digest(payload4)
        assert digest1 == digest4

    async def test_check_kill_switch(self, mock_alerts):
        """Test kill switch check function."""
        # Test when kill switch is inactive
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            _check_kill_switch()  # Should not raise exception

        # Test when kill switch is active
        mock_alerts.is_kill_switch_active.return_value = True
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with pytest.raises(KillSwitchError, match="Kill switch active"):
                _check_kill_switch()

    async def test_async_check_kill_switch(self, mock_alerts):
        """Test async kill switch check function."""
        # Test when kill switch is inactive
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            await _async_check_kill_switch()  # Should not raise exception

        # Test when kill switch is active
        mock_alerts.is_kill_switch_active.return_value = True
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with pytest.raises(KillSwitchError, match="Kill switch active"):
                await _async_check_kill_switch()

class TestOpenAlgoClient(unittest.IsolatedAsyncioTestCase):
    """Test suite for OpenAlgoClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = OpenAlgoClient()

    async def test_initialize(self):
        """Test client initialization."""
        assert self.client is not None
        assert self.client.base_url == "https://api.openalgo.in"
        assert self.client.timeout == 30.0

    async def test_place_order_success(self, mock_alerts):
        """Test successful order placement."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "order_id": "12345"}

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", return_value=mock_response):
                # Create test order
                order = Order(
                    order_id="test_order_001",
                    symbol="RELIANCE",
                    quantity=10,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    variety=OrderVariety.REGULAR,
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(UTC),
                    filled_quantity=0,
                )

                # Test order placement
                result = await self.client.place_order(order)
                assert result == {"status": "success", "order_id": "12345"}

    async def test_place_order_kill_switch(self, mock_alerts):
        """Test order placement blocked by kill switch."""
        # Activate kill switch
        mock_alerts.is_kill_switch_active.return_value = True

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            # Create test order
            order = Order(
                order_id="test_order_002",
                symbol="RELIANCE",
                quantity=10,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                variety=OrderVariety.REGULAR,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(UTC),
                filled_quantity=0,
            )

            # Test that kill switch blocks order placement
            with pytest.raises(KillSwitchError, match="Kill switch active"):
                await self.client.place_order(order)

    async def test_place_order_api_error(self, mock_alerts):
        """Test order placement with API error."""
        # Mock the HTTP client to return error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Invalid order parameters"}

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", return_value=mock_response):
                # Create test order
                order = Order(
                    order_id="test_order_003",
                    symbol="RELIANCE",
                    quantity=10,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    variety=OrderVariety.REGULAR,
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(UTC),
                    filled_quantity=0,
                )

                # Test that API error is raised
                with pytest.raises(OpenAlgoAPIError, match="API Error 400"):
                    await self.client.place_order(order)

    async def test_place_order_circuit_breaker_open(self, mock_alerts):
        """Test order placement when circuit breaker is open."""
        # Open the circuit breaker
        OPENALGO_CIRCUIT_BREAKER._state = "open"
        OPENALGO_CIRCUIT_BREAKER._opened_at = 1.0

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            # Create test order
            order = Order(
                order_id="test_order_004",
                symbol="RELIANCE",
                quantity=10,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                variety=OrderVariety.REGULAR,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(UTC),
                filled_quantity=0,
            )

            # Test that circuit breaker blocks order placement
            with pytest.raises(Exception, match="Circuit is open"):
                await self.client.place_order(order)

        # Reset circuit breaker
        OPENALGO_CIRCUIT_BREAKER.reset()

    async def test_place_smart_order_success(self, mock_alerts):
        """Test successful smart order placement."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "order_id": "12345"}

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", return_value=mock_response):
                # Test smart order placement
                result = await self.client.place_smart_order(
                    symbol="RELIANCE",
                    quantity=10,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    strategy="momentum",
                    target_price=110.0,
                    stop_loss=95.0,
                    trailing_stop_loss=5.0,
                )
                assert result == {"status": "success", "order_id": "12345"}

    async def test_modify_order_success(self, mock_alerts):
        """Test successful order modification."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "order_id": "12345"}

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", return_value=mock_response):
                # Test order modification
                result = await self.client.modify_order(
                    order_id="12345",
                    quantity=20,
                    price=105.0,
                    trigger_price=104.0,
                )
                assert result == {"status": "success", "order_id": "12345"}

    async def test_cancel_order_success(self, mock_alerts):
        """Test successful order cancellation."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "order_id": "12345"}

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", return_value=mock_response):
                # Test order cancellation
                result = await self.client.cancel_order("12345")
                assert result == {"status": "success", "order_id": "12345"}

    async def test_get_positions_success(self, mock_alerts):
        """Test successful positions retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "positions": [
                {
                    "symbol": "RELIANCE",
                    "quantity": 10,
                    "average_price": 100.0,
                    "last_price": 105.0,
                    "pnl": 50.0,
                    "product_type": "MIS",
                }
            ],
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test positions retrieval
                result = await self.client.get_positions()
                assert len(result) == 1
                assert result[0].symbol == "RELIANCE"
                assert result[0].quantity == 10

    async def test_get_quotes_success(self, mock_alerts):
        """Test successful quotes retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "quotes": [
                {
                    "symbol": "RELIANCE",
                    "last_price": 105.0,
                    "open": 100.0,
                    "high": 106.0,
                    "low": 99.5,
                    "close": 104.5,
                    "volume": 15000,
                    "timestamp": "2024-01-15T10:30:00Z",
                    "change": 5.0,
                    "change_percent": 4.76,
                }
            ],
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test quotes retrieval
                result = await self.client.get_quotes(["RELIANCE"])
                assert len(result) == 1
                assert result[0].symbol == "RELIANCE"
                assert result[0].last_price == 105.0

    async def test_get_historical_data_success(self, mock_alerts):
        """Test successful historical data retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "historical_data": [
                {
                    "symbol": "RELIANCE",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "volume": 10000,
                    "interval": "1d",
                }
            ],
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test historical data retrieval
                result = await self.client.get_historical_data(
                    symbol="RELIANCE",
                    interval="1d",
                    from_date="2024-01-01",
                    to_date="2024-01-15",
                )
                assert len(result) == 1
                assert result[0].symbol == "RELIANCE"
                assert result[0].close == 104.0

    async def test_get_order_book_success(self, mock_alerts):
        """Test successful order book retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "order_book": [
                {
                    "order_id": "12345",
                    "symbol": "RELIANCE",
                    "quantity": 10,
                    "order_type": "MARKET",
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "status": "COMPLETED",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "filled_quantity": 10,
                    "price": 100.0,
                }
            ],
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test order book retrieval
                result = await self.client.get_order_book()
                assert len(result) == 1
                assert result[0].order_id == "12345"
                assert result[0].status == OrderStatus.COMPLETED

    async def test_get_trade_book_success(self, mock_alerts):
        """Test successful trade book retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "trade_book": [
                {
                    "trade_id": "67890",
                    "symbol": "RELIANCE",
                    "quantity": 10,
                    "entry_price": 100.0,
                    "exit_price": 105.0,
                    "entry_time": "2024-01-15T10:30:00Z",
                    "exit_time": "2024-01-15T11:30:00Z",
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "pnl": 50.0,
                    "status": "COMPLETED",
                }
            ],
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test trade book retrieval
                result = await self.client.get_trade_book()
                assert len(result) == 1
                assert result[0].trade_id == "67890"
                assert result[0].pnl == 50.0

    async def test_get_funds_success(self, mock_alerts):
        """Test successful funds retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "funds": {
                "available_cash": 50000.0,
                "utilized_margin": 20000.0,
                "available_margin": 30000.0,
                "total_equity": 70000.0,
                "timestamp": "2024-01-15T10:30:00Z",
            },
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test funds retrieval
                result = await self.client.get_funds()
                assert result.available_cash == 50000.0
                assert result.total_equity == 70000.0

    async def test_get_order_status_success(self, mock_alerts):
        """Test successful order status retrieval."""
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "order_status": {
                "order_id": "12345",
                "symbol": "RELIANCE",
                "quantity": 10,
                "order_type": "MARKET",
                "transaction_type": "BUY",
                "product_type": "MIS",
                "status": "COMPLETED",
                "timestamp": "2024-01-15T10:30:00Z",
                "filled_quantity": 10,
                "price": 100.0,
            },
        }

        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "get", return_value=mock_response):
                # Test order status retrieval
                result = await self.client.get_order_status("12345")
                assert result.order_id == "12345"
                assert result.status == OrderStatus.COMPLETED

    async def test_rate_limit_handling(self, mock_alerts):
        """Test rate limit handling."""
        from src.loats.utils.rate_limiter import RateLimitExceededError

        # Mock the rate limiter to raise RateLimitExceededError
        with patch("src.loats.openalgo.get_order_rate_limiter") as mock_rate_limiter:
            mock_rate_limiter.return_value.acquire.side_effect = RateLimitExceededError(
                "Rate limit exceeded"
            )

            with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
                # Create test order
                order = Order(
                    order_id="test_order_005",
                    symbol="RELIANCE",
                    quantity=10,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    variety=OrderVariety.REGULAR,
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(UTC),
                    filled_quantity=0,
                )

                # Test that rate limit error is raised
                with pytest.raises(RateLimitExceededError, match="Rate limit exceeded"):
                    await self.client.place_order(order)

    async def test_network_error_handling(self, mock_alerts):
        """Test network error handling."""
        # Mock the HTTP client to raise network error
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", side_effect=httpx.NetworkError("Network error")):
                # Create test order
                order = Order(
                    order_id="test_order_006",
                    symbol="RELIANCE",
                    quantity=10,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    variety=OrderVariety.REGULAR,
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(UTC),
                    filled_quantity=0,
                )

                # Test that network error is handled
                with pytest.raises(OpenAlgoError, match="Network error"):
                    await self.client.place_order(order)

    async def test_timeout_handling(self, mock_alerts):
        """Test timeout handling."""
        # Mock the HTTP client to raise timeout error
        with patch("src.loats.openalgo._get_alerts", return_value=mock_alerts):
            with patch.object(self.client._client, "post", side_effect=httpx.TimeoutException("Request timeout")):
                # Create test order
                order = Order(
                    order_id="test_order_007",
                    symbol="RELIANCE",
                    quantity=10,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    variety=OrderVariety.REGULAR,
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(UTC),
                    filled_quantity=0,
                )

                # Test that timeout error is handled
                with pytest.raises(OpenAlgoError, match="Request timeout"):
                    await self.client.place_order(order)

if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)