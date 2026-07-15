"""
Tests for OpenAlgo client module.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import Response

from src.loats.config import settings
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
from src.loats.openalgo import OpenAlgoClient


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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.place_order(
                symbol="NIFTY",
                quantity=100,
                order_type=OrderType.LIMIT,
                price=18000.0,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                variety=OrderVariety.REGULAR,
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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
        """Test error handling in OpenAlgoClient."""
        # Test HTTP error
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        mock_httpx_client.post.return_value = error_response

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is False
            assert "HTTP error" in result["message"]

        # Test JSON decode error
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Not JSON"
        mock_httpx_client.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is False
            assert "JSON decode error" in result["message"]

        # Test timeout error
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Timeout")

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is False
            assert "Timeout error" in result["message"]

        # Test connection error
        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.get_quotes(["NIFTY"])

            assert result["success"] is False
            assert "Connection error" in result["message"]

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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
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

        with patch("httpx.Client", return_value=mock_httpx_client), client:
            result = client.get_trade_book()

            assert result["success"] is True
            assert len(result["data"]) == 1
            assert result["data"][0]["trade_id"] == "trade_12345"
            assert result["data"][0]["pnl"] == 10000.0

            # Verify request was made correctly
            mock_httpx_client.post.assert_called_once_with("/api/v1/trade_book")
