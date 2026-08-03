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
        """Test place_order successfully."""
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
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/place_order"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["quantity"] == 1
            assert payload["order_type"] == "MARKET"
            assert payload["variety"] == "regular"
            assert payload["transaction_type"] == "BUY"
            assert payload["product_type"] == "MIS"

    def test_place_order_with_all_params(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test place_order with all parameters successfully."""
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
                order_type=OrderType.LIMIT,
                price=18000.0,
                variety="regular",
                transaction_type=TransactionType.SELL,
                product_type=ProductType.NRML,
                trigger_price=17950.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=50.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/place_order"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["quantity"] == 1
            assert payload["order_type"] == "LIMIT"
            assert payload["price"] == 18000.0
            assert payload["variety"] == "regular"
            assert payload["transaction_type"] == "SELL"
            assert payload["product_type"] == "NRML"
            assert payload["trigger_price"] == 17950.0
            assert payload["stop_loss"] == 17900.0
            assert payload["take_profit"] == 18100.0
            assert payload["trailing_stop_loss"] == 50.0

    def test_place_smart_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test place_smart_order successfully."""
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
                order_type=OrderType.MARKET,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "SMART12345"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/place_smart_order"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["quantity"] == 1
            assert payload["order_type"] == "MARKET"
            assert payload["strategy"] == "simple"

    def test_modify_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test modify_order successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {"order_id": "ORD12345", "status": "MODIFIED"},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.modify_order(
                order_id="ORD12345",
                quantity=2,
                order_type=OrderType.LIMIT,
                price=18100.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/modify_order"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"
            assert payload["quantity"] == 2
            assert payload["order_type"] == "LIMIT"
            assert payload["price"] == 18100.0

    def test_cancel_order_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test cancel_order successfully."""
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

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/cancel_order"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"

    def test_get_order_status_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_order_status successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order status retrieved successfully",
            "data": {"order_id": "ORD12345", "status": "COMPLETED"},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_order_status("ORD12345")

            assert result["success"] is True
            assert result["data"]["status"] == "COMPLETED"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/order_status"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"

    def test_get_all_orders_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_all_orders successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Orders retrieved successfully",
            "data": [{"order_id": "ORD12345", "status": "COMPLETED"}],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["order_id"] == "ORD12345"

            # Verify endpoint
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/all_orders"

    def test_get_trade_book_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_trade_book successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Trade book retrieved successfully",
            "data": [{"trade_id": "TRADE12345", "order_id": "ORD12345"}],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "TRADE12345"

            # Verify endpoint
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/trade_book"

    def test_get_position_book_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_position_book successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Position book retrieved successfully",
            "data": [{"symbol": "NIFTY", "quantity": 100}],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["symbol"] == "NIFTY"

            # Verify endpoint
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/position_book"

    def test_get_funds_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_funds successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Funds retrieved successfully",
            "data": {"available_cash": 10000.0, "utilized_margin": 5000.0},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 10000.0

            # Verify endpoint
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/funds"

    def test_get_quotes_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_quotes successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Quotes retrieved successfully",
            "data": {"NIFTY": {"last_price": 18000.0}},
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is True
            assert result["data"]["NIFTY"]["last_price"] == 18000.0

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/quotes"
            payload = call_args[1]["json"]
            assert payload["symbols"] == ["NIFTY"]

    def test_get_history_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_history successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Historical data retrieved successfully",
            "data": [{"timestamp": "2023-01-01", "close": 18000.0}],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_history("NIFTY", "1d")

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["close"] == 18000.0

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/history"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["interval"] == "1d"

    def test_get_option_chain_success(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_option_chain successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Option chain retrieved successfully",
            "data": [{"strike": 18000, "option_type": "CE"}],
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_option_chain("NIFTY")

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["strike"] == 18000

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/option_chain"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"


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
        """Test async place_order successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {"order_id": "ORD12345", "status": "PENDING"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo.get_order_rate_limiter"
            ) as mock_rate_limiter:
                mock_limiter = AsyncMock()
                mock_limiter.acquire.return_value = True
                mock_rate_limiter.return_value = mock_limiter

                result = await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "ORD12345"

                # Verify payload
                call_args = mock_async_httpx_client.post.call_args
                assert call_args[0][0] == "/api/v1/place_order"
                payload = call_args[1]["json"]
                assert payload["symbol"] == "NIFTY"
                assert payload["quantity"] == 1
                assert payload["order_type"] == "MARKET"
                assert payload["variety"] == "regular"
                assert payload["transaction_type"] == "BUY"
                assert payload["product_type"] == "MIS"

    @pytest.mark.asyncio
    async def test_async_place_order_with_all_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_order with all parameters successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {"order_id": "ORD12345", "status": "PENDING"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo.get_order_rate_limiter"
            ) as mock_rate_limiter:
                mock_limiter = AsyncMock()
                mock_limiter.acquire.return_value = True
                mock_rate_limiter.return_value = mock_limiter

                result = await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                    variety="regular",
                    transaction_type=TransactionType.SELL,
                    product_type=ProductType.NRML,
                    trigger_price=17950.0,
                    stop_loss=17900.0,
                    take_profit=18100.0,
                    trailing_stop_loss=50.0,
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "ORD12345"

                # Verify payload
                call_args = mock_async_httpx_client.post.call_args
                assert call_args[0][0] == "/api/v1/place_order"
                payload = call_args[1]["json"]
                assert payload["symbol"] == "NIFTY"
                assert payload["quantity"] == 1
                assert payload["order_type"] == "LIMIT"
                assert payload["price"] == 18000.0
                assert payload["variety"] == "regular"
                assert payload["transaction_type"] == "SELL"
                assert payload["product_type"] == "NRML"
                assert payload["trigger_price"] == 17950.0
                assert payload["stop_loss"] == 17900.0
                assert payload["take_profit"] == 18100.0
                assert payload["trailing_stop_loss"] == 50.0

    @pytest.mark.asyncio
    async def test_async_place_smart_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_smart_order successfully."""
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
            with patch(
                "src.loats.openalgo.get_smart_order_rate_limiter"
            ) as mock_rate_limiter:
                mock_limiter = AsyncMock()
                mock_limiter.acquire.return_value = True
                mock_rate_limiter.return_value = mock_limiter

                result = await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "SMART12345"

                # Verify payload
                call_args = mock_async_httpx_client.post.call_args
                assert call_args[0][0] == "/api/v1/place_smart_order"
                payload = call_args[1]["json"]
                assert payload["symbol"] == "NIFTY"
                assert payload["quantity"] == 1
                assert payload["order_type"] == "MARKET"
                assert payload["strategy"] == "simple"

    @pytest.mark.asyncio
    async def test_async_modify_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async modify_order successfully."""
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
                order_id="ORD12345",
                quantity=2,
                order_type=OrderType.LIMIT,
                price=18100.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "ORD12345"

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/modify_order"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"
            assert payload["quantity"] == 2
            assert payload["order_type"] == "LIMIT"
            assert payload["price"] == 18100.0

    @pytest.mark.asyncio
    async def test_async_cancel_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async cancel_order successfully."""
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

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/cancel_order"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"

    @pytest.mark.asyncio
    async def test_async_get_order_status_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_order_status successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order status retrieved successfully",
            "data": {"order_id": "ORD12345", "status": "COMPLETED"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_order_status("ORD12345")

            assert result["success"] is True
            assert result["data"]["status"] == "COMPLETED"

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/order_status"
            payload = call_args[1]["json"]
            assert payload["order_id"] == "ORD12345"

    @pytest.mark.asyncio
    async def test_async_get_all_orders_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_all_orders successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Orders retrieved successfully",
            "data": [{"order_id": "ORD12345", "status": "COMPLETED"}],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["order_id"] == "ORD12345"

            # Verify endpoint
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/all_orders"

    @pytest.mark.asyncio
    async def test_async_get_trade_book_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_trade_book successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Trade book retrieved successfully",
            "data": [{"trade_id": "TRADE12345", "order_id": "ORD12345"}],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "TRADE12345"

            # Verify endpoint
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/trade_book"

    @pytest.mark.asyncio
    async def test_async_get_position_book_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_position_book successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Position book retrieved successfully",
            "data": [{"symbol": "NIFTY", "quantity": 100}],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["symbol"] == "NIFTY"

            # Verify endpoint
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/position_book"

    @pytest.mark.asyncio
    async def test_async_get_funds_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_funds successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Funds retrieved successfully",
            "data": {"available_cash": 10000.0, "utilized_margin": 5000.0},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 10000.0

            # Verify endpoint
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/funds"

    @pytest.mark.asyncio
    async def test_async_get_quotes_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_quotes successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Quotes retrieved successfully",
            "data": {"NIFTY": {"last_price": 18000.0}},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_quotes(["NIFTY"])

            assert result["success"] is True
            assert result["data"]["NIFTY"]["last_price"] == 18000.0

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/quotes"
            payload = call_args[1]["json"]
            assert payload["symbols"] == ["NIFTY"]

    @pytest.mark.asyncio
    async def test_async_get_history_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_history successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Historical data retrieved successfully",
            "data": [{"timestamp": "2023-01-01", "close": 18000.0}],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_history("NIFTY", "1d")

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["close"] == 18000.0

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/history"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["interval"] == "1d"

    @pytest.mark.asyncio
    async def test_async_get_option_chain_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_option_chain successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Option chain retrieved successfully",
            "data": [{"strike": 18000, "option_type": "CE"}],
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_option_chain("NIFTY")

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["strike"] == 18000

            # Verify payload
            call_args = mock_async_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/option_chain"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"

    @pytest.mark.asyncio
    async def test_async_get_quotes_caching(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_quotes caching."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Quotes retrieved successfully",
            "data": {"NIFTY": {"last_price": 18000.0}},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            # First call - should cache
            result1 = await async_client.get_quotes(["NIFTY"])
            assert result1["success"] is True

            # Second call - should use cache
            with patch("src.loats.utils.cache.cache_manager.get") as mock_cache_get:
                mock_cache_get.return_value = (
                    '{"success": true, "data": {"NIFTY": {"last_price": 18000.0}}}'
                )
                result2 = await async_client.get_quotes(["NIFTY"])
                assert result2["success"] is True

    @pytest.mark.asyncio
    async def test_async_rate_limiting(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async rate limiting."""
        with patch("src.loats.openalgo.get_order_rate_limiter") as mock_rate_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.acquire.return_value = False
            mock_rate_limiter.return_value = mock_limiter

            with pytest.raises(RateLimitExceededError):
                await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
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
            assert "Internal Server Error" in str(exc_info.value)

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
            assert "Unauthorized" in str(exc_info.value)

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

            assert "Connection error" in str(exc_info.value)
