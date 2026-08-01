"""
Comprehensive tests for OpenAlgo client covering all missing coverage areas.
Focuses on kill switch, rate limiting, error handling, and comprehensive order path testing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import Response

from src.loats.config import get_settings
from src.loats.models import OrderType, OrderVariety, ProductType, TransactionType
from src.loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
    RateLimitExceededError,
)

settings = get_settings()

class TestOpenAlgoClientComprehensive:
    """Comprehensive tests for OpenAlgoClient covering missing coverage."""

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

    def test_kill_switch_check(self) -> None:
        """Test _check_kill_switch function raises KillSwitchError when active."""
        from src.loats.openalgo import _check_kill_switch
        with patch("src.loats.openalgo._get_alerts") as mock_get_alerts:
            mock_alerts = MagicMock()
            mock_alerts.is_kill_switch_active.return_value = True
            mock_get_alerts.return_value = mock_alerts

            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                _check_kill_switch()

    def test_async_kill_switch_check(self) -> None:
        """Test _async_check_kill_switch function raises KillSwitchError when active."""
        from src.loats.openalgo import _async_check_kill_switch
        with patch("src.loats.openalgo._get_alerts") as mock_get_alerts:
            mock_alerts = MagicMock()
            mock_alerts.is_kill_switch_active.return_value = True
            mock_get_alerts.return_value = mock_alerts

            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                import asyncio
                asyncio.run(_async_check_kill_switch())

    def test_client_context_manager(self, client: OpenAlgoClient) -> None:
        """Test OpenAlgoClient context manager enter/exit."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with client:
                assert client.client is not None
                mock_client_class.assert_called_once_with(
                    base_url=settings.openalgo_base_url,
                    timeout=settings.request_timeout,
                    headers={"x-api-key": settings.openalgo_api_key.get_secret_value()},
                )

            mock_client.close.assert_called_once()
            assert client.client is None

    def test_client_ensure_client(self, client: OpenAlgoClient) -> None:
        """Test OpenAlgoClient._ensure_client method."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # First call should create client
            result_client = client._ensure_client()
            assert result_client is not None
            mock_client_class.assert_called_once_with(
                base_url=settings.openalgo_base_url,
                timeout=settings.request_timeout,
                headers={"x-api-key": settings.openalgo_api_key.get_secret_value()},
            )

            # Second call should return existing client
            mock_client_class.reset_mock()
            result_client2 = client._ensure_client()
            assert result_client2 is result_client
            mock_client_class.assert_not_called()

    def test_place_order_kill_switch(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test place_order raises KillSwitchError when kill switch active."""
        with patch("src.loats.openalgo._check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

    def test_place_order_success_all_params(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock, mock_response: MagicMock
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
                variety=OrderVariety.REGULAR,
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

    def test_place_order_minimal_params(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock, mock_response: MagicMock
    ) -> None:
        """Test place_order with minimal parameters successfully."""
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
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["quantity"] == 1
            assert payload["order_type"] == "MARKET"
            assert "price" not in payload
            assert payload["variety"] == "regular"
            assert payload["transaction_type"] == "BUY"
            assert payload["product_type"] == "MIS"

    def test_place_order_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test place_order error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 400
        error_response.text = "Invalid order parameters"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=httpx.Request("POST", "http://test/api/v1/place_order"),
            response=error_response,
        )

        mock_httpx_client.post.return_value = error_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

            assert exc_info.value.status_code == 400
            assert "Invalid order parameters" in str(exc_info.value)

    def test_place_smart_order_kill_switch(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test place_smart_order raises KillSwitchError when kill switch active."""
        with patch("src.loats.openalgo._check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

    def test_place_smart_order_success_all_params(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock, mock_response: MagicMock
    ) -> None:
        """Test place_smart_order with all parameters successfully."""
        mock_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "SMART12345",
                "status": "PENDING",
                "strategy": "advanced",
            },
        }
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            result = client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                trigger_price=17950.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=50.0,
                strategy="advanced",
                transaction_type=TransactionType.SELL,
                product_type=ProductType.NRML,
                metadata={"key": "value"},
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "SMART12345"
            assert result["data"]["strategy"] == "advanced"

            # Verify payload
            call_args = mock_httpx_client.post.call_args
            assert call_args[0][0] == "/api/v1/place_smart_order"
            payload = call_args[1]["json"]
            assert payload["symbol"] == "NIFTY"
            assert payload["quantity"] == 1
            assert payload["order_type"] == "LIMIT"
            assert payload["price"] == 18000.0
            assert payload["strategy"] == "advanced"
            assert payload["transaction_type"] == "SELL"
            assert payload["product_type"] == "NRML"
            assert payload["trigger_price"] == 17950.0
            assert payload["stop_loss"] == 17900.0
            assert payload["take_profit"] == 18100.0
            assert payload["trailing_stop_loss"] == 50.0
            assert payload["metadata"] == {"key": "value"}

    def test_modify_order_kill_switch(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test modify_order raises KillSwitchError when kill switch active."""
        with patch("src.loats.openalgo._check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                client.modify_order(order_id="ORD12345", quantity=2)

    def test_modify_order_success_all_params(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock, mock_response: MagicMock
    ) -> None:
        """Test modify_order with all parameters successfully."""
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
                trigger_price=18050.0,
                stop_loss=18000.0,
                take_profit=18200.0,
                trailing_stop_loss=60.0,
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
            assert payload["trigger_price"] == 18050.0
            assert payload["stop_loss"] == 18000.0
            assert payload["take_profit"] == 18200.0
            assert payload["trailing_stop_loss"] == 60.0

    def test_cancel_order_kill_switch(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test cancel_order raises KillSwitchError when kill switch active."""
        with patch("src.loats.openalgo._check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                client.cancel_order("ORD12345")

    def test_cancel_order_success(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock, mock_response: MagicMock
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

    def test_cancel_order_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test cancel_order error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 404
        error_response.text = "Order not found"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("POST", "http://test/api/v1/cancel_order"),
            response=error_response,
        )

        mock_httpx_client.post.return_value = error_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                client.cancel_order("ORD12345")

            assert exc_info.value.status_code == 404
            assert "Order not found" in str(exc_info.value)

class TestAsyncOpenAlgoClientComprehensive:
    """Comprehensive tests for AsyncOpenAlgoClient covering missing coverage."""

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
    async def test_async_client_context_manager(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test AsyncOpenAlgoClient context manager enter/exit."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            async with async_client:
                assert async_client.client is not None
                mock_client_class.assert_called_once_with(
                    base_url=settings.openalgo_base_url,
                    timeout=settings.request_timeout,
                    headers={"x-api-key": settings.openalgo_api_key.get_secret_value()},
                )

            mock_client.aclose.assert_called_once()
            assert async_client.client is None

    @pytest.mark.asyncio
    async def test_async_client_ensure_client(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test AsyncOpenAlgoClient._ensure_client method."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # First call should create client
            result_client = await async_client._ensure_client()
            assert result_client is not None
            mock_client_class.assert_called_once_with(
                base_url=settings.openalgo_base_url,
                timeout=settings.request_timeout,
                headers={"x-api-key": settings.openalgo_api_key.get_secret_value()},
            )

            # Second call should return existing client
            mock_client_class.reset_mock()
            result_client2 = await async_client._ensure_client()
            assert result_client2 is result_client
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_place_order_kill_switch(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async place_order raises KillSwitchError when kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")
        ):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

    @pytest.mark.asyncio
    async def test_async_place_order_rate_limit(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_order raises RateLimitExceededError when rate limit exceeded."""
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

    @pytest.mark.asyncio
    async def test_async_place_order_success_all_params(
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
            with patch("src.loats.openalgo.get_order_rate_limiter") as mock_rate_limiter:
                mock_limiter = AsyncMock()
                mock_limiter.acquire.return_value = True
                mock_rate_limiter.return_value = mock_limiter

                result = await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                    variety=OrderVariety.REGULAR,
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
    async def test_async_place_order_minimal_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_order with minimal parameters successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {"order_id": "ORD12345", "status": "PENDING"},
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch("src.loats.openalgo.get_order_rate_limiter") as mock_rate_limiter:
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
                payload = call_args[1]["json"]
                assert payload["symbol"] == "NIFTY"
                assert payload["quantity"] == 1
                assert payload["order_type"] == "MARKET"
                assert "price" not in payload
                assert payload["variety"] == "regular"
                assert payload["transaction_type"] == "BUY"
                assert payload["product_type"] == "MIS"

    @pytest.mark.asyncio
    async def test_async_place_order_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async place_order error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 400
        error_response.text = "Invalid order parameters"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=httpx.Request("POST", "http://test/api/v1/place_order"),
            response=error_response,
        )

        mock_async_httpx_client.post.return_value = error_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                await async_client.place_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

            assert exc_info.value.status_code == 400
            assert "Invalid order parameters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_place_smart_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_smart_order raises KillSwitchError when kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")
        ):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

    @pytest.mark.asyncio
    async def test_async_place_smart_order_rate_limit(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_smart_order raises RateLimitExceededError when rate limit exceeded."""
        with patch("src.loats.openalgo.get_smart_order_rate_limiter") as mock_rate_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.acquire.return_value = False
            mock_rate_limiter.return_value = mock_limiter

            with pytest.raises(RateLimitExceededError):
                await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                )

    @pytest.mark.asyncio
    async def test_async_place_smart_order_success_all_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async place_smart_order with all parameters successfully."""
        mock_async_response.json.return_value = {
            "success": True,
            "message": "Smart order placed successfully",
            "data": {
                "order_id": "SMART12345",
                "status": "PENDING",
                "strategy": "advanced",
            },
        }
        mock_async_httpx_client.post.return_value = mock_async_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with patch("src.loats.openalgo.get_smart_order_rate_limiter") as mock_rate_limiter:
                mock_limiter = AsyncMock()
                mock_limiter.acquire.return_value = True
                mock_rate_limiter.return_value = mock_limiter

                result = await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.LIMIT,
                    price=18000.0,
                    trigger_price=17950.0,
                    stop_loss=17900.0,
                    take_profit=18100.0,
                    trailing_stop_loss=50.0,
                    strategy="advanced",
                    transaction_type=TransactionType.SELL,
                    product_type=ProductType.NRML,
                    metadata={"key": "value"},
                )

                assert result["success"] is True
                assert result["data"]["order_id"] == "SMART12345"
                assert result["data"]["strategy"] == "advanced"

                # Verify payload
                call_args = mock_async_httpx_client.post.call_args
                assert call_args[0][0] == "/api/v1/place_smart_order"
                payload = call_args[1]["json"]
                assert payload["symbol"] == "NIFTY"
                assert payload["quantity"] == 1
                assert payload["order_type"] == "LIMIT"
                assert payload["price"] == 18000.0
                assert payload["strategy"] == "advanced"
                assert payload["transaction_type"] == "SELL"
                assert payload["product_type"] == "NRML"
                assert payload["trigger_price"] == 17950.0
                assert payload["stop_loss"] == 17900.0
                assert payload["take_profit"] == 18100.0
                assert payload["trailing_stop_loss"] == 50.0
                assert payload["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_async_modify_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async modify_order raises KillSwitchError when kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")
        ):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                await async_client.modify_order(order_id="ORD12345", quantity=2)

    @pytest.mark.asyncio
    async def test_async_modify_order_success_all_params(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
    ) -> None:
        """Test async modify_order with all parameters successfully."""
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
                trigger_price=18050.0,
                stop_loss=18000.0,
                take_profit=18200.0,
                trailing_stop_loss=60.0,
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
            assert payload["trigger_price"] == 18050.0
            assert payload["stop_loss"] == 18000.0
            assert payload["take_profit"] == 18200.0
            assert payload["trailing_stop_loss"] == 60.0

    @pytest.mark.asyncio
    async def test_async_cancel_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async cancel_order raises KillSwitchError when kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch", side_effect=KillSwitchError("Kill switch active, order placement blocked")
        ):
            with pytest.raises(KillSwitchError, match="Kill switch active, order placement blocked"):
                await async_client.cancel_order("ORD12345")

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
    async def test_async_cancel_order_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async cancel_order error handling."""
        error_response = MagicMock(spec=Response)
        error_response.status_code = 404
        error_response.text = "Order not found"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("POST", "http://test/api/v1/cancel_order"),
            response=error_response,
        )

        mock_async_httpx_client.post.return_value = error_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoAPIError) as exc_info:
                await async_client.cancel_order("ORD12345")

            assert exc_info.value.status_code == 404
            assert "Order not found" in str(exc_info.value)

class TestOpenAlgoErrorScenarios:
    """Tests for various error scenarios in OpenAlgo clients."""

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

    def test_sync_timeout_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test sync timeout error handling."""
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Request timed out")

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "Timeout error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_timeout_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async timeout error handling."""
        mock_async_httpx_client.post.side_effect = httpx.TimeoutException("Request timed out")

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError) as exc_info:
                await async_client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "Timeout error" in str(exc_info.value)

    def test_sync_json_decode_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test sync JSON decode error handling."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_httpx_client.post.return_value = mock_response

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "JSON decode error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_json_decode_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async JSON decode error handling."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_async_httpx_client.post.return_value = mock_response

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError) as exc_info:
                await async_client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "JSON decode error" in str(exc_info.value)

    def test_sync_generic_error_handling(
        self, client: OpenAlgoClient, mock_httpx_client: MagicMock
    ) -> None:
        """Test sync generic error handling."""
        mock_httpx_client.post.side_effect = Exception("Unexpected error")

        with patch.object(client, "_ensure_client", return_value=mock_httpx_client):
            with pytest.raises(OpenAlgoError) as exc_info:
                client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "Request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_generic_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async generic error handling."""
        mock_async_httpx_client.post.side_effect = Exception("Unexpected error")

        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError) as exc_info:
                await async_client._request("POST", "quotes", json={"symbols": ["NIFTY"]})

            assert "Request failed" in str(exc_info.value)