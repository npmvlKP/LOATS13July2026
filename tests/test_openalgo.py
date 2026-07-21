"""
Tests for OpenAlgo client module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import Response

from src.loats.config import settings
from src.loats.models import (
    HistoricalData,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    QuoteData,
    TransactionType,
)
from src.loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
)


class TestAsyncOpenAlgoClient:
    """Test suite for AsyncOpenAlgoClient."""

    @pytest.fixture
    def async_client(self) -> AsyncOpenAlgoClient:
        """Create a test AsyncOpenAlgoClient instance."""
        return AsyncOpenAlgoClient()

    @pytest.fixture
    def mock_async_httpx_client(self) -> AsyncMock:
        """Create a mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def mock_async_response(self) -> MagicMock:
        """Create a mock httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {},
        }
        return response

    async def test_initialization(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test AsyncOpenAlgoClient initialization."""
        assert async_client.base_url == settings.openalgo_base_url
        assert async_client.api_key == settings.openalgo_api_key.get_secret_value()
        assert async_client.timeout == settings.request_timeout
        assert async_client.client is None

    async def test_enter_exit_context(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async context manager enter and exit."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            async with async_client:
                assert async_client.client is not None
                mock_client_class.assert_called_once_with(
                    base_url=async_client.base_url,
                    timeout=async_client.timeout,
                    headers={"x-api-key": async_client.api_key},
                )

            mock_client.aclose.assert_called_once()
            assert async_client.client is None

    async def test_get_quotes(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: AsyncMock,
    ) -> None:
        """Test get_quotes method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
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
                },
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_quotes(["NIFTY"])

            assert result["success"] is True
            assert "NIFTY" in result["data"]
            assert result["data"]["NIFTY"]["last_price"] == 18000.50

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/quotes",
                json={"symbols": ["NIFTY"]},
            )

    async def test_error_handling(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
    ) -> None:
        """Test error handling in AsyncOpenAlgoClient."""
        # Test HTTP error - should raise OpenAlgoAPIError
        error_response = AsyncMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        mock_async_httpx_client.post.return_value = error_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(Exception) as exc_info:  # Should raise OpenAlgoAPIError
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )
            assert "API Error 500" in str(exc_info.value)

        # Test JSON decode error - should raise OpenAlgoError
        mock_response = AsyncMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Not JSON"
        mock_async_httpx_client.post.return_value = mock_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(Exception) as exc_info:  # Should raise OpenAlgoError
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )
            assert "JSON decode error" in str(exc_info.value)

        # Test timeout error - should raise OpenAlgoError
        mock_async_httpx_client.post.side_effect = httpx.TimeoutException("Timeout")

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError) as exc_info:
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )
            assert "Timeout error" in str(exc_info.value)

        # Test connection error - should raise OpenAlgoError
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


class TestOpenAlgoClient:
    """Test suite for OpenAlgoClient."""

    @pytest.fixture
    def client(self) -> OpenAlgoClient:
        """Create a test OpenAlgoClient instance."""
        return OpenAlgoClient()

    @pytest.fixture
    def mock_httpx_client(self) -> MagicMock:
        """Create a mock httpx.Client."""
        return MagicMock(spec=httpx.Client)

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        """Create a mock httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {},
        }
        return response

    def test_initialization(self, client: OpenAlgoClient) -> None:
        """Test OpenAlgoClient initialization."""
        assert client.base_url == settings.openalgo_base_url
        assert client.api_key == settings.openalgo_api_key.get_secret_value()
        assert client.timeout == settings.request_timeout
        assert client.client is None

    def test_enter_exit_context(self, client: OpenAlgoClient) -> None:
        """Test context manager enter and exit."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with client:
                assert client.client is not None
                mock_client_class.assert_called_once_with(
                    base_url=client.base_url,
                    timeout=client.timeout,
                    headers={"x-api-key": client.api_key},
                )

            mock_client.close.assert_called_once()
            assert client.client is None

    def test_get_quotes(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_quotes method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
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
                },
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is True
            assert "NIFTY" in result["data"]
            assert result["data"]["NIFTY"]["last_price"] == 18000.50

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/quotes",
                json={"symbols": ["NIFTY"]},
            )

    def test_get_history(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_history method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "timestamp": "2023-01-01T09:15:00",
                    "open": 17950.25,
                    "high": 18000.50,
                    "low": 17900.00,
                    "close": 17980.50,
                    "volume": 500000,
                },
                {
                    "timestamp": "2023-01-01T09:16:00",
                    "open": 17980.50,
                    "high": 18020.75,
                    "low": 17950.25,
                    "close": 18000.50,
                    "volume": 600000,
                },
            ],
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_history(
                symbol="NIFTY",
                interval="1min",
                from_date="2023-01-01",
                to_date="2023-01-02",
            )

            assert result["success"] is True
            assert len(result["data"]) == 2
            assert result["data"][0]["open"] == 17950.25

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/history",
                json={
                    "symbol": "NIFTY",
                    "interval": "1min",
                    "from_date": "2023-01-01",
                    "to_date": "2023-01-02",
                },
            )

    def test_get_option_chain(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_option_chain method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {
                "expiry_dates": ["2023-01-26", "2023-02-02"],
                "options": [
                    {
                        "symbol": "NIFTY23JAN18000CE",
                        "strike_price": 18000.0,
                        "expiry": "2023-01-26T15:30:00",
                        "option_type": "CE",
                        "last_price": 150.50,
                        "open_interest": 10000,
                        "volume": 5000,
                        "implied_volatility": 0.25,
                        "delta": 0.5,
                        "gamma": 0.02,
                        "theta": -0.05,
                        "vega": 0.1,
                        "rho": 0.03,
                    },
                ],
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_option_chain("NIFTY", "2023-01-26")

            assert result["success"] is True
            assert len(result["data"]["expiry_dates"]) == 2
            assert len(result["data"]["options"]) == 1
            assert result["data"]["options"][0]["symbol"] == "NIFTY23JAN18000CE"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/option_chain",
                json={
                    "symbol": "NIFTY",
                    "expiry": "2023-01-26",
                },
            )

    def test_get_position_book(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_position_book method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "average_price": 17950.0,
                    "last_price": 18000.50,
                    "pnl": 5050.0,
                    "product_type": "MIS",
                    "buy_quantity": 100,
                    "sell_quantity": 0,
                },
            ],
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["symbol"] == "NIFTY"
            assert result["data"][0]["pnl"] == 5050.0

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with("/api/v1/position_book")

    def test_get_funds(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_funds method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {
                "available_cash": 50000.0,
                "utilized_margin": 10000.0,
                "available_margin": 40000.0,
                "total_equity": 50000.0,
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 50000.0
            assert result["data"]["total_equity"] == 50000.0

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with("/api/v1/funds")

    def test_place_order(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test place_order method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": "order_12345",
                "status": "OPEN",
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.place_order(
                symbol="NIFTY",
                quantity=100,
                order_type=OrderType.LIMIT,
                price=18000.0,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                stop_loss=17950.0,
                take_profit=18100.0,
                trailing_stop_loss=50.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "order_12345"
            assert result["data"]["status"] == "OPEN"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/place_order",
                json={
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "order_type": "LIMIT",
                    "price": 18000.0,
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "variety": "regular",
                    "stop_loss": 17950.0,
                    "take_profit": 18100.0,
                    "trailing_stop_loss": 50.0,
                },
            )

    def test_place_smart_order(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test place_smart_order method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "smart_order_12345",
                "status": "OPEN",
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.place_smart_order(
                symbol="NIFTY",
                quantity=100,
                order_type=OrderType.LIMIT,
                price=18000.0,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                strategy="supertrend",
                stop_loss=17950.0,
                take_profit=18100.0,
                trailing_stop_loss=50.0,
                metadata={"key": "value"},
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "smart_order_12345"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/place_smart_order",
                json={
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "order_type": "LIMIT",
                    "price": 18000.0,
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "strategy": "supertrend",
                    "stop_loss": 17950.0,
                    "take_profit": 18100.0,
                    "trailing_stop_loss": 50.0,
                    "metadata": {"key": "value"},
                },
            )

    def test_modify_order(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test modify_order method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {
                "order_id": "order_12345",
                "status": "OPEN",
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.modify_order(
                order_id="order_12345",
                quantity=150,
                order_type=OrderType.LIMIT,
                price=18050.0,
                stop_loss=18000.0,
                take_profit=18200.0,
                trailing_stop_loss=60.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "order_12345"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/modify_order",
                json={
                    "order_id": "order_12345",
                    "quantity": 150,
                    "order_type": "LIMIT",
                    "price": 18050.0,
                    "stop_loss": 18000.0,
                    "take_profit": 18200.0,
                    "trailing_stop_loss": 60.0,
                },
            )

    def test_cancel_order(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test cancel_order method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {
                "order_id": "order_12345",
                "status": "CANCELLED",
            },
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.cancel_order("order_12345")

            assert result["success"] is True
            assert result["data"]["order_id"] == "order_12345"
            assert result["data"]["status"] == "CANCELLED"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/cancel_order",
                json={"order_id": "order_12345"},
            )

    def test_get_order_status(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_order_status method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "order_id": "order_12345",
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "order_type": "LIMIT",
                    "price": 18000.0,
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "status": "COMPLETED",
                    "filled_quantity": 100,
                    "average_price": 18000.0,
                    "timestamp": "2023-01-01T10:00:00",
                },
            ],
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_order_status("order_12345")

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["order_id"] == "order_12345"
            assert result["data"][0]["status"] == "COMPLETED"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with(
                "/api/v1/order_status",
                json={"order_id": "order_12345"},
            )

    def test_error_handling(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
    ) -> None:
        """Test error handling in OpenAlgoClient.

        Now raises exceptions instead of returning error dictionaries,
        matching AsyncOpenAlgoClient behavior (F-CONC-5 fix).
        """
        # Test HTTP error - should raise OpenAlgoAPIError
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        mock_httpx_client.post.return_value = error_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                client.get_quotes(["NIFTY"])

            assert exc_info.value.status_code == 500
            assert "HTTP error" in exc_info.value.message

        # Test JSON decode error - should raise OpenAlgoError
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Not JSON"
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client.get_quotes(["NIFTY"])

            assert "JSON decode error" in str(exc_info.value)

        # Test timeout error - should raise OpenAlgoError
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Timeout")

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client.get_quotes(["NIFTY"])

            assert "Timeout error" in str(exc_info.value)

        # Test connection error - should raise OpenAlgoError
        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client.get_quotes(["NIFTY"])

            assert "Connection error" in str(exc_info.value)

    def test_model_conversion(self, client: OpenAlgoClient) -> None:
        """Test conversion between OpenAlgo responses and models."""
        # Test quote conversion
        quote_data = {
            "last_price": 18000.50,
            "open": 17950.25,
            "high": 18050.75,
            "low": 17900.00,
            "close": 17980.50,
            "volume": 1000000,
            "change": 20.00,
            "change_percent": 0.11,
        }

        quote = client._convert_to_quote("NIFTY", quote_data)
        assert isinstance(quote, QuoteData)
        assert quote.symbol == "NIFTY"
        assert quote.last_price == 18000.50
        assert quote.change == 20.00

        # Test historical data conversion
        history_data = {
            "timestamp": "2023-01-01T09:15:00",
            "open": 17950.25,
            "high": 18000.50,
            "low": 17900.00,
            "close": 17980.50,
            "volume": 500000,
        }

        historical = client._convert_to_historical_data("NIFTY", "1min", history_data)
        assert isinstance(historical, HistoricalData)
        assert historical.symbol == "NIFTY"
        assert historical.interval == "1min"
        assert historical.open == 17950.25

        # Test position conversion
        position_data = {
            "symbol": "NIFTY",
            "quantity": 100,
            "average_price": 17950.0,
            "last_price": 18000.50,
            "pnl": 5050.0,
            "product_type": "MIS",
            "buy_quantity": 100,
            "sell_quantity": 0,
        }

        position = client._convert_to_position(position_data)
        assert isinstance(position, Position)
        assert position.symbol == "NIFTY"
        assert position.quantity == 100
        assert position.pnl == 5050.0

        # Test order conversion
        order_data = {
            "order_id": "order_12345",
            "symbol": "NIFTY",
            "quantity": 100,
            "order_type": "LIMIT",
            "price": 18000.0,
            "transaction_type": "BUY",
            "product_type": "MIS",
            "status": "OPEN",
            "timestamp": "2023-01-01T10:00:00",
            "filled_quantity": 0,
            "average_price": None,
        }

        order = client._convert_to_order(order_data)
        assert isinstance(order, Order)
        assert order.order_id == "order_12345"
        assert order.symbol == "NIFTY"
        assert order.status == OrderStatus.OPEN

    def test_get_all_orders(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_all_orders method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "order_id": "order_12345",
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "order_type": "LIMIT",
                    "price": 18000.0,
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "status": "COMPLETED",
                    "filled_quantity": 100,
                    "average_price": 18000.0,
                    "timestamp": "2023-01-01T10:00:00",
                },
                {
                    "order_id": "order_67890",
                    "symbol": "BANKNIFTY",
                    "quantity": 50,
                    "order_type": "MARKET",
                    "price": None,
                    "transaction_type": "SELL",
                    "product_type": "MIS",
                    "status": "OPEN",
                    "filled_quantity": 0,
                    "average_price": None,
                    "timestamp": "2023-01-01T10:05:00",
                },
            ],
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 2
            assert result["data"][0]["order_id"] == "order_12345"
            assert result["data"][1]["status"] == "OPEN"

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with("/api/v1/all_orders")

    def test_get_trade_book(
        self,
        client: OpenAlgoClient,
        mock_httpx_client: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Test get_trade_book method."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "trade_id": "trade_12345",
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "entry_price": 17950.0,
                    "exit_price": 18050.0,
                    "entry_time": "2023-01-01T10:00:00",
                    "exit_time": "2023-01-01T15:30:00",
                    "transaction_type": "BUY",
                    "product_type": "MIS",
                    "pnl": 10000.0,
                    "status": "CLOSED",
                },
            ],
        }

        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "trade_12345"
            assert result["data"][0]["pnl"] == 10000.0

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with("/api/v1/trade_book")

    def test_kill_switch_blocks_place_order(self, client: OpenAlgoClient) -> None:
        """Test that kill switch blocks sync place_order.

        Verifies the safety mechanism that prevents order placement
        when the kill switch is active (emergency shutdown).
        """
        with patch("src.loats.openalgo._check_kill_switch") as mock_check:
            mock_check.side_effect = KillSwitchError("Kill switch active")

            with pytest.raises(KillSwitchError) as exc_info:
                client.place_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                )

            assert "Kill switch active" in str(exc_info.value)
            mock_check.assert_called_once()

    def test_kill_switch_blocks_place_smart_order(self, client: OpenAlgoClient) -> None:
        """Test that kill switch blocks sync place_smart_order.

        Verifies the safety mechanism that prevents smart order placement
        when the kill switch is active (emergency shutdown).
        """
        with patch("src.loats.openalgo._check_kill_switch") as mock_check:
            mock_check.side_effect = KillSwitchError("Kill switch active")

            with pytest.raises(KillSwitchError) as exc_info:
                client.place_smart_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                )

            assert "Kill switch active" in str(exc_info.value)
            mock_check.assert_called_once()


class TestAsyncOpenAlgoClientFinancialPaths:
    """Test async financial operations for AsyncOpenAlgoClient.

    These tests cover the critical async order placement and modification
    paths that are essential for trading system operation.
    """

    @pytest.fixture
    def async_client(self) -> AsyncOpenAlgoClient:
        """Create a test AsyncOpenAlgoClient instance."""
        return AsyncOpenAlgoClient()

    @pytest.fixture
    def mock_async_httpx_client(self) -> AsyncMock:
        """Create a mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def mock_async_response(self) -> MagicMock:
        """Create a mock httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {},
        }
        return response

    async def test_async_place_order(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_order method with all parameters.

        Verifies:
        - Kill switch check is called before placing order
        - All order parameters are correctly serialized to payload
        - Response is properly returned on success
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": "async_order_12345",
                "status": "OPEN",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
            ):
                result = await async_client.place_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    stop_loss=17950.0,
                    take_profit=18100.0,
                    trailing_stop_loss=50.0,
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "async_order_12345"
                assert result["data"]["status"] == "OPEN"

                # Verify request was made correctly with all parameters
                mock_async_httpx_client.post.assert_called_once_with(
                    "/api/v1/place_order",
                    json={
                        "symbol": "NIFTY",
                        "quantity": 100,
                        "order_type": "LIMIT",
                        "variety": "regular",
                        "transaction_type": "BUY",
                        "product_type": "MIS",
                        "price": 18000.0,
                        "stop_loss": 17950.0,
                        "take_profit": 18100.0,
                        "trailing_stop_loss": 50.0,
                    },
                )

    async def test_async_place_order_with_string_enums(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_order with string enum values.

        Verifies that string enum values are handled correctly
        without conversion.
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": "async_order_str_12345",
                "status": "OPEN",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
            ):
                # Use string values instead of enums
                result = await async_client.place_order(
                    symbol="BANKNIFTY",
                    quantity=50,
                    order_type="MARKET",
                    transaction_type="SELL",
                    product_type="NRML",
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "async_order_str_12345"

                # Verify payload contains string values directly
                call_args = mock_async_httpx_client.post.call_args
                payload = call_args.kwargs["json"]
                assert payload["order_type"] == "MARKET"
                assert payload["transaction_type"] == "SELL"
                assert payload["product_type"] == "NRML"

    async def test_async_place_order_minimal_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_order with only required parameters.

        Verifies that optional parameters are not included in payload
        when not provided.
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": "async_order_min_12345",
                "status": "OPEN",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
            ):
                result = await async_client.place_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.MARKET,
                )

                assert result["success"] is True

                # Verify only required parameters are in payload
                call_args = mock_async_httpx_client.post.call_args
                payload = call_args.kwargs["json"]
                assert "symbol" in payload
                assert "quantity" in payload
                assert "order_type" in payload
                assert "price" not in payload  # Optional
                assert "stop_loss" not in payload  # Optional
                assert "take_profit" not in payload  # Optional

    async def test_async_place_order_kill_switch_blocks(
        self,
        async_client: AsyncOpenAlgoClient,
    ) -> None:
        """Test that kill switch blocks async place_order.

        Verifies the safety mechanism that prevents async order placement
        when the kill switch is active (emergency shutdown).
        """
        with patch(
            "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = KillSwitchError("Kill switch active")

            with pytest.raises(KillSwitchError) as exc_info:
                await async_client.place_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                )

            assert "Kill switch active" in str(exc_info.value)
            mock_check.assert_called_once()

    async def test_async_place_smart_order(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_smart_order method with all parameters.

        Verifies:
        - Kill switch check is called before placing smart order
        - Strategy and metadata are correctly included in payload
        - All order parameters are correctly serialized
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "async_smart_order_12345",
                "status": "OPEN",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
            ):
                result = await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    strategy="supertrend",
                    stop_loss=17950.0,
                    take_profit=18100.0,
                    trailing_stop_loss=50.0,
                    metadata={"strategy_name": "momentum", "signal_id": "sig_001"},
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "async_smart_order_12345"

                # Verify request was made correctly with all parameters
                mock_async_httpx_client.post.assert_called_once_with(
                    "/api/v1/place_smart_order",
                    json={
                        "symbol": "NIFTY",
                        "quantity": 100,
                        "order_type": "LIMIT",
                        "strategy": "supertrend",
                        "transaction_type": "BUY",
                        "product_type": "MIS",
                        "price": 18000.0,
                        "stop_loss": 17950.0,
                        "take_profit": 18100.0,
                        "trailing_stop_loss": 50.0,
                        "metadata": {
                            "strategy_name": "momentum",
                            "signal_id": "sig_001",
                        },
                    },
                )

    async def test_async_place_smart_order_default_strategy(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_smart_order with default strategy.

        Verifies that the default 'simple' strategy is used when
        not explicitly specified.
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "async_smart_simple_12345",
                "status": "OPEN",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch(
                "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
            ):
                result = await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.SELL,
                )

                assert result["success"] is True

                # Verify default strategy is 'simple'
                call_args = mock_async_httpx_client.post.call_args
                payload = call_args.kwargs["json"]
                assert payload["strategy"] == "simple"

    async def test_async_place_smart_order_kill_switch_blocks(
        self,
        async_client: AsyncOpenAlgoClient,
    ) -> None:
        """Test that kill switch blocks async place_smart_order.

        Verifies the safety mechanism that prevents async smart order placement
        when the kill switch is active (emergency shutdown).
        """
        with patch(
            "src.loats.openalgo._async_check_kill_switch", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = KillSwitchError("Kill switch active")

            with pytest.raises(KillSwitchError) as exc_info:
                await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=100,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                )

            assert "Kill switch active" in str(exc_info.value)
            mock_check.assert_called_once()

    async def test_async_modify_order(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async modify_order method with all parameters.

        Verifies:
        - Order ID is correctly included in payload
        - All modification parameters are correctly serialized
        - No kill switch check (modify is allowed during kill switch)
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {
                "order_id": "order_12345",
                "status": "MODIFIED",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.modify_order(
                order_id="order_12345",
                quantity=150,
                order_type=OrderType.LIMIT,
                price=18050.0,
                stop_loss=18000.0,
                take_profit=18200.0,
                trailing_stop_loss=60.0,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "order_12345"
            assert result["data"]["status"] == "MODIFIED"

            # Verify request was made correctly with all parameters
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/modify_order",
                json={
                    "order_id": "order_12345",
                    "quantity": 150,
                    "order_type": "LIMIT",
                    "price": 18050.0,
                    "stop_loss": 18000.0,
                    "take_profit": 18200.0,
                    "trailing_stop_loss": 60.0,
                },
            )

    async def test_async_modify_order_minimal_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async modify_order with only order_id.

        Verifies that optional parameters are not included in payload
        when not provided.
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {
                "order_id": "order_min_12345",
                "status": "MODIFIED",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.modify_order(order_id="order_min_12345")

            assert result["success"] is True

            # Verify only order_id is in payload
            call_args = mock_async_httpx_client.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["order_id"] == "order_min_12345"
            assert "quantity" not in payload
            assert "price" not in payload

    async def test_async_modify_order_partial_update(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async modify_order with partial parameter update.

        Verifies that only provided parameters are included in payload,
        allowing partial updates to existing orders.
        """
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order modified successfully",
            "data": {
                "order_id": "order_partial_12345",
                "status": "MODIFIED",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            # Only update price and stop_loss
            result = await async_client.modify_order(
                order_id="order_partial_12345",
                price=18100.0,
                stop_loss=18050.0,
            )

            assert result["success"] is True

            # Verify only specified parameters are in payload
            call_args = mock_async_httpx_client.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["order_id"] == "order_partial_12345"
            assert payload["price"] == 18100.0
            assert payload["stop_loss"] == 18050.0
            assert "quantity" not in payload
            assert "take_profit" not in payload

    async def test_async_get_history(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_history method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "timestamp": "2023-01-01T09:15:00",
                    "open": 17950.25,
                    "high": 18000.50,
                    "low": 17900.00,
                    "close": 17980.50,
                    "volume": 500000,
                },
            ],
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_history(
                symbol="NIFTY",
                interval="1min",
                from_date="2023-01-01",
                to_date="2023-01-02",
            )

            assert result["success"] is True
            assert len(result["data"]) == 1

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/history",
                json={
                    "symbol": "NIFTY",
                    "interval": "1min",
                    "from_date": "2023-01-01",
                    "to_date": "2023-01-02",
                },
            )

    async def test_async_get_option_chain(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_option_chain method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {
                "expiry_dates": ["2023-01-26"],
                "options": [],
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_option_chain("NIFTY", "2023-01-26")

            assert result["success"] is True
            assert len(result["data"]["expiry_dates"]) == 1

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/option_chain",
                json={
                    "symbol": "NIFTY",
                    "expiry": "2023-01-26",
                },
            )

    async def test_async_get_position_book(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_position_book method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "symbol": "NIFTY",
                    "quantity": 100,
                    "pnl": 5000.0,
                },
            ],
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_position_book()

            assert result["success"] is True
            assert len(result["data"]) == 1

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/position_book"
            )

    async def test_async_get_funds(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_funds method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": {
                "available_cash": 50000.0,
                "available_margin": 40000.0,
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_funds()

            assert result["success"] is True
            assert result["data"]["available_cash"] == 50000.0

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with("/api/v1/funds")

    async def test_async_cancel_order(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async cancel_order method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order cancelled successfully",
            "data": {
                "order_id": "order_12345",
                "status": "CANCELLED",
            },
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.cancel_order("order_12345")

            assert result["success"] is True
            assert result["data"]["status"] == "CANCELLED"

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/cancel_order",
                json={"order_id": "order_12345"},
            )

    async def test_async_get_order_status(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_order_status method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "order_id": "order_12345",
                    "status": "COMPLETED",
                },
            ],
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_order_status("order_12345")

            assert result["success"] is True
            assert result["data"][0]["order_id"] == "order_12345"

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with(
                "/api/v1/order_status",
                json={"order_id": "order_12345"},
            )

    async def test_async_get_all_orders(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_all_orders method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "order_id": "order_12345",
                    "status": "OPEN",
                },
                {
                    "order_id": "order_67890",
                    "status": "COMPLETED",
                },
            ],
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_all_orders()

            assert result["success"] is True
            assert len(result["data"]) == 2

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with("/api/v1/all_orders")

    async def test_async_get_trade_book(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async get_trade_book method."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Success",
            "data": [
                {
                    "trade_id": "trade_12345",
                    "pnl": 10000.0,
                },
            ],
        }

        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            result = await async_client.get_trade_book()

            assert result["success"] is True
            assert result["data"][0]["trade_id"] == "trade_12345"

            # Verify request was made correctly
            mock_async_httpx_client.post.assert_called_once_with("/api/v1/trade_book")
