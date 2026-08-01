"""
Integration tests for OpenAlgo API client.
Tests the complete flow of API interactions with proper mocking.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import Response

from src.loats.config import get_settings
from src.loats.models import OrderType, ProductType, TransactionType
from src.loats.openalgo import (
    AsyncOpenAlgoClient,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
)
from src.loats.utils.rate_limiter import RateLimitExceededError

settings = get_settings()


class TestOpenAlgoClientIntegration:
    """Integration tests for OpenAlgoClient."""

    @pytest.fixture
    def client(self) -> OpenAlgoClient:
        """Create test OpenAlgoClient instance."""
        return OpenAlgoClient()

    @pytest.fixture
    def mock_httpx_client(self) -> MagicMock:
        """Create mock httpx.Client."""
        return MagicMock(spec=httpx.Client)

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        """Create mock httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Success", "data": {}}
        return response

    def test_place_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful order placement."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {"order_id": "ORD12345", "status": "PENDING"},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"
            mock_httpx_client.post.assert_called_once()

    def test_place_smart_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful smart order placement."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "SMART12345",
                "status": "PENDING",
                "strategy": "simple",
            },
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                strategy="simple",
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "SMART12345"
            assert result["data"]["strategy"] == "simple"

    def test_modify_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful order modification."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {"order_id": "ORD12345", "status": "MODIFIED"},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.modify_order(order_id="ORD12345", quantity=2, price=18100.0)

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

    def test_cancel_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful order cancellation."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {"order_id": "ORD12345", "status": "CANCELLED"},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.cancel_order("ORD12345")

            assert result["success"] is True
            assert result["data"]["status"] == "CANCELLED"

    def test_get_position_book_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful position book retrieval."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Position book retrieved",
            "data": [
                {
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "average_price": 18000.50,
                    "last_price": 18050.75,
                    "pnl": 50.25,
                    "product_type": "MIS",
                }
            ],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["symbol"] == "NIFTY"

    def test_get_funds_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful funds retrieval."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Funds retrieved",
            "data": {
                "available_cash": 100000.00,
                "utilized_margin": 50000.00,
                "available_margin": 50000.00,
                "total_equity": 150000.00,
            },
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 100000.00

    def test_get_all_orders_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful retrieval of all orders."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Orders retrieved",
            "data": [
                {
                    "order_id": "ORD12345",
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "order_type": "MARKET",
                    "status": "OPEN",
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                }
            ],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["order_id"] == "ORD12345"

    def test_get_trade_book_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test successful trade book retrieval."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Trade book retrieved",
            "data": [
                {
                    "trade_id": "TRADE12345",
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "entry_price": 18000.50,
                    "exit_price": 18050.75,
                    "pnl": 50.25,
                    "status": "CLOSED",
                }
            ],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "TRADE12345"


class TestAsyncOpenAlgoClientIntegration:
    """Integration tests for AsyncOpenAlgoClient."""

    @pytest.fixture
    def async_client(self) -> AsyncOpenAlgoClient:
        """Create test AsyncOpenAlgoClient instance."""
        return AsyncOpenAlgoClient()

    @pytest.fixture
    def mock_async_httpx_client(self) -> AsyncMock:
        """Create mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def mock_async_response(self) -> MagicMock:
        """Create mock httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {"success": True, "message": "Success", "data": {}}
        return response

    @pytest.mark.asyncio
    async def test_async_place_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful order placement."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {"order_id": "ORD12345", "status": "PENDING"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

    @pytest.mark.asyncio
    async def test_async_place_smart_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful smart order placement."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "SMART12345",
                "status": "PENDING",
                "strategy": "simple",
            },
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                strategy="simple",
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "SMART12345"

    @pytest.mark.asyncio
    async def test_async_modify_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful order modification."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {"order_id": "ORD12345", "status": "MODIFIED"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.modify_order(
                order_id="ORD12345", quantity=2, price=18100.0
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

    @pytest.mark.asyncio
    async def test_async_cancel_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful order cancellation."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {"order_id": "ORD12345", "status": "CANCELLED"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.cancel_order("ORD12345")

            assert result["success"] is True
            assert result["data"]["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_async_get_position_book_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful position book retrieval."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Position book retrieved",
            "data": [
                {
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "average_price": 18000.50,
                    "last_price": 18050.75,
                    "pnl": 50.25,
                    "product_type": "MIS",
                }
            ],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["symbol"] == "NIFTY"

    @pytest.mark.asyncio
    async def test_async_get_funds_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful funds retrieval."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Funds retrieved",
            "data": {
                "available_cash": 100000.00,
                "utilized_margin": 50000.00,
                "available_margin": 50000.00,
                "total_equity": 150000.00,
            },
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 100000.00

    @pytest.mark.asyncio
    async def test_async_get_all_orders_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful retrieval of all orders."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Orders retrieved",
            "data": [
                {
                    "order_id": "ORD12345",
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "order_type": "MARKET",
                    "status": "OPEN",
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                }
            ],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["order_id"] == "ORD12345"

    @pytest.mark.asyncio
    async def test_async_get_trade_book_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async successful trade book retrieval."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Trade book retrieved",
            "data": [
                {
                    "trade_id": "TRADE12345",
                    "symbol": "NIFTY",
                    "quantity": 1,
                    "entry_price": 18000.50,
                    "exit_price": 18050.75,
                    "pnl": 50.25,
                    "status": "CLOSED",
                }
            ],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "TRADE12345"

    @pytest.mark.asyncio
    async def test_async_get_quotes_caching(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async quotes caching functionality."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Quotes retrieved",
            "data": {
                "NIFTY": {
                    "last_price": 18000.50,
                    "open": 17950.25,
                    "high": 18050.75,
                    "low": 17900.00,
                    "close": 17980.50,
                    "volume": 1000000,
                    "change": 20.00,
                    "change_percent": 0.11,
                }
            },
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            # First call - should hit API
            result1 = await async_client.get_quotes(["NIFTY"])
            assert result1["success"] is True
            assert "NIFTY" in result1["data"]

            # Second call - should hit cache if cache is working
            # (Note: This is a simplified test - actual cache testing is in test_cache.py)

    @pytest.mark.asyncio
    async def test_async_rate_limiting(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async rate limiting functionality."""
        # Mock the rate limiter to simulate rate limit exceeded
        with patch("src.loats.openalgo.get_order_rate_limiter") as mock_rate_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.acquire.return_value = False
            mock_rate_limiter.return_value = mock_limiter

            with pytest.raises(RateLimitExceededError):
                await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                )


class TestOpenAlgoErrorHandling:
    """Tests for error handling in OpenAlgo clients."""

    @pytest.fixture
    def client(self) -> OpenAlgoClient:
        """Create test OpenAlgoClient instance."""
        return OpenAlgoClient()

    @pytest.fixture
    def async_client(self) -> AsyncOpenAlgoClient:
        """Create test AsyncOpenAlgoClient instance."""
        return AsyncOpenAlgoClient()

    @pytest.fixture
    def mock_httpx_client(self) -> MagicMock:
        """Create mock httpx.Client."""
        return MagicMock(spec=httpx.Client)

    @pytest.fixture
    def mock_async_httpx_client(self) -> AsyncMock:
        """Create mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    def test_sync_http_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test sync HTTP error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "http://test/api/v1/quotes"),
            response=error_response,
        )

        mock_httpx_client.post.return_value = error_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert exc_info.value.status_code == 500
            assert "HTTP error: 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_http_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async HTTP error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 401
        error_response.text = "Unauthorized"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=httpx.Request("POST", "http://test/api/v1/quotes"),
            response=error_response,
        )

        mock_async_httpx_client.post.return_value = error_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )

            assert exc_info.value.status_code == 401
            assert "HTTP error: 401" in str(exc_info.value)

    def test_sync_connection_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test sync connection error handling."""
        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_connection_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async connection error handling."""
        mock_async_httpx_client.post.side_effect = httpx.ConnectError(
            "Connection failed"
        )

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError) as exc_info:
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )

            assert "Request failed" in str(exc_info.value)
