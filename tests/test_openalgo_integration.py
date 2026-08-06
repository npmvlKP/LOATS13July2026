"""
Integration tests for OpenAlgo order operations.
Tests sync + async place_order, place_smart_order, modify_order, cancel_order
including kill-switch and rate-limit paths.
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
    RateLimitExceededError,
)

settings = get_settings()


class TestOrderOperationsIntegration:
    """Integration tests for order operations."""

    @pytest.fixture
    def async_client(self) -> AsyncOpenAlgoClient:
        """Create test AsyncOpenAlgoClient instance."""
        return AsyncOpenAlgoClient()

    @pytest.fixture
    def sync_client(self) -> OpenAlgoClient:
        """Create test OpenAlgoClient instance."""
        return OpenAlgoClient()

    @pytest.fixture
    def mock_async_httpx_client(self) -> AsyncMock:
        """Create mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def mock_sync_httpx_client(self) -> MagicMock:
        """Create mock httpx.Client."""
        return MagicMock(spec=httpx.Client)

    @pytest.fixture
    def mock_success_response(self) -> MagicMock:
        """Create mock successful httpx.Response."""
        response = MagicMock(spec=Response)
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "message": "Order placed successfully",
            "data": {
                "order_id": "test_order_123",
                "status": "PENDING",
                "symbol": "NIFTY",
                "quantity": 1,
                "order_type": "MARKET",
                "transaction_type": "BUY",
                "product_type": "MIS",
            },
        }
        return response

    @pytest.fixture
    def mock_rate_limit_response(self) -> MagicMock:
        """Create mock rate limit exceeded response."""
        response = MagicMock(spec=Response)
        response.status_code = 429
        response.json.return_value = {
            "success": False,
            "message": "Rate limit exceeded",
            "error": "too_many_requests",
        }
        return response

    @pytest.mark.asyncio
    async def test_async_place_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test async place_order success path."""
        mock_async_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = True
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            result = await async_client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            assert result["data"]["symbol"] == "NIFTY"
            assert result["data"]["quantity"] == 1
            mock_async_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_place_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_order with kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                await async_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )

    @pytest.mark.asyncio
    async def test_async_place_order_rate_limit(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_order with rate limit exceeded."""
        with (
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = False
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            with pytest.raises(RateLimitExceededError):
                await async_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )

    @pytest.mark.asyncio
    async def test_async_place_smart_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test async place_smart_order success path."""
        mock_success_response.json.return_value["data"]["strategy"] = "simple"
        mock_async_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_smart_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = True
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            result = await async_client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                strategy="simple",
                stop_loss=17900.0,
                take_profit=18100.0,
            )

            assert result["success"] is True
            assert result["data"]["strategy"] == "simple"
            assert result["data"]["stop_loss"] == 17900.0
            assert result["data"]["take_profit"] == 18100.0

    @pytest.mark.asyncio
    async def test_async_place_smart_order_rate_limit(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async place_smart_order with rate limit exceeded."""
        with (
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_smart_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = False
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            with pytest.raises(RateLimitExceededError):
                await async_client.place_smart_order(
                    symbol="NIFTY",
                    quantity=1,
                    order_type=OrderType.MARKET,
                    strategy="simple",
                )

    @pytest.mark.asyncio
    async def test_async_modify_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test async modify_order success path."""
        mock_success_response.json.return_value["data"]["order_id"] = "test_order_123"
        mock_success_response.json.return_value["data"]["status"] = "MODIFIED"
        mock_async_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
        ):
            result = await async_client.modify_order(
                order_id="test_order_123", quantity=2, price=18050.0
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            assert result["data"]["status"] == "MODIFIED"

    @pytest.mark.asyncio
    async def test_async_modify_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async modify_order with kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                await async_client.modify_order(order_id="test_order_123", quantity=2)

    @pytest.mark.asyncio
    async def test_async_cancel_order_success(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test async cancel_order success path."""
        mock_success_response.json.return_value["data"]["order_id"] = "test_order_123"
        mock_success_response.json.return_value["data"]["status"] = "CANCELLED"
        mock_async_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
        ):
            result = await async_client.cancel_order("test_order_123")

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            assert result["data"]["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_async_cancel_order_kill_switch(
        self, async_client: AsyncOpenAlgoClient
    ) -> None:
        """Test async cancel_order with kill switch active."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                await async_client.cancel_order("test_order_123")

    def test_sync_place_order_success(
        self,
        sync_client: OpenAlgoClient,
        mock_sync_httpx_client: MagicMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test sync place_order success path."""
        mock_sync_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            result = sync_client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            mock_sync_httpx_client.post.assert_called_once()

    def test_sync_place_order_kill_switch(self, sync_client: OpenAlgoClient) -> None:
        """Test sync place_order with kill switch active."""
        with patch(
            "src.loats.openalgo._check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                sync_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )

    def test_sync_place_smart_order_success(
        self,
        sync_client: OpenAlgoClient,
        mock_sync_httpx_client: MagicMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test sync place_smart_order success path."""
        mock_success_response.json.return_value["data"]["strategy"] = "simple"
        mock_sync_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            result = sync_client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                strategy="simple",
                stop_loss=17900.0,
                take_profit=18100.0,
            )

            assert result["success"] is True
            assert result["data"]["strategy"] == "simple"
            assert result["data"]["stop_loss"] == 17900.0
            assert result["data"]["take_profit"] == 18100.0

    def test_sync_modify_order_success(
        self,
        sync_client: OpenAlgoClient,
        mock_sync_httpx_client: MagicMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test sync modify_order success path."""
        mock_success_response.json.return_value["data"]["order_id"] = "test_order_123"
        mock_success_response.json.return_value["data"]["status"] = "MODIFIED"
        mock_sync_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            result = sync_client.modify_order(
                order_id="test_order_123", quantity=2, price=18050.0
            )

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            assert result["data"]["status"] == "MODIFIED"

    def test_sync_modify_order_kill_switch(self, sync_client: OpenAlgoClient) -> None:
        """Test sync modify_order with kill switch active."""
        with patch(
            "src.loats.openalgo._check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                sync_client.modify_order(order_id="test_order_123", quantity=2)

    def test_sync_cancel_order_success(
        self,
        sync_client: OpenAlgoClient,
        mock_sync_httpx_client: MagicMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test sync cancel_order success path."""
        mock_success_response.json.return_value["data"]["order_id"] = "test_order_123"
        mock_success_response.json.return_value["data"]["status"] = "CANCELLED"
        mock_sync_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            result = sync_client.cancel_order("test_order_123")

            assert result["success"] is True
            assert result["data"]["order_id"] == "test_order_123"
            assert result["data"]["status"] == "CANCELLED"

    def test_sync_cancel_order_kill_switch(self, sync_client: OpenAlgoClient) -> None:
        """Test sync cancel_order with kill switch active."""
        with patch(
            "src.loats.openalgo._check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                sync_client.cancel_order("test_order_123")

    @pytest.mark.asyncio
    async def test_async_order_operations_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test async order operations error handling."""
        # Test API error
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "http://test/api/v1/place_order"),
            response=error_response,
        )

        mock_async_httpx_client.post.return_value = error_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = True
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            with pytest.raises(OpenAlgoAPIError):
                await async_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )

    def test_sync_order_operations_error_handling(
        self, sync_client: OpenAlgoClient, mock_sync_httpx_client: MagicMock
    ) -> None:
        """Test sync order operations error handling."""
        # Test API error
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "http://test/api/v1/place_order"),
            response=error_response,
        )

        mock_sync_httpx_client.post.return_value = error_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            with pytest.raises(OpenAlgoAPIError):
                sync_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )

    @pytest.mark.asyncio
    async def test_async_order_operations_with_all_parameters(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test async order operations with all optional parameters."""
        mock_async_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                async_client, "_ensure_client", return_value=mock_async_httpx_client
            ),
            patch("src.loats.openalgo._async_check_kill_switch", return_value=None),
            patch(
                "src.loats.utils.rate_limiter.get_order_rate_limiter"
            ) as mock_rate_limiter,
        ):
            mock_rate_limiter_instance = AsyncMock()
            mock_rate_limiter_instance.acquire.return_value = True
            mock_rate_limiter.return_value = mock_rate_limiter_instance

            # Test place_order with all parameters
            result = await async_client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                variety=OrderVariety.STOPLOSS,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                trigger_price=18050.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=17800.0,
            )

            assert result["success"] is True

            # Test place_smart_order with all parameters
            mock_success_response.json.return_value["data"]["strategy"] = "advanced"
            result = await async_client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                trigger_price=18050.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=17800.0,
                strategy="advanced",
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                metadata={"source": "automated"},
            )

            assert result["success"] is True
            assert result["data"]["strategy"] == "advanced"
            assert result["data"]["metadata"]["source"] == "automated"

    def test_sync_order_operations_with_all_parameters(
        self,
        sync_client: OpenAlgoClient,
        mock_sync_httpx_client: MagicMock,
        mock_success_response: MagicMock,
    ) -> None:
        """Test sync order operations with all optional parameters."""
        mock_sync_httpx_client.post.return_value = mock_success_response

        with (
            patch.object(
                sync_client, "_ensure_client", return_value=mock_sync_httpx_client
            ),
            patch("src.loats.openalgo._check_kill_switch", return_value=None),
        ):
            # Test place_order with all parameters
            result = sync_client.place_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                variety=OrderVariety.STOPLOSS,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                trigger_price=18050.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=17800.0,
            )

            assert result["success"] is True

            # Test place_smart_order with all parameters
            mock_success_response.json.return_value["data"]["strategy"] = "advanced"
            result = sync_client.place_smart_order(
                symbol="NIFTY",
                quantity=1,
                order_type=OrderType.LIMIT,
                price=18000.0,
                trigger_price=18050.0,
                stop_loss=17900.0,
                take_profit=18100.0,
                trailing_stop_loss=17800.0,
                strategy="advanced",
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                metadata={"source": "automated"},
            )

            assert result["success"] is True
            assert result["data"]["strategy"] == "advanced"
            assert result["data"]["metadata"]["source"] == "automated"
