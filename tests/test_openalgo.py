"""
Tests OpenAlgo client module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import Response

from src.loats.config import get_settings
from src.loats.models import OrderType
from src.loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
)

settings = get_settings()


class TestAsyncOpenAlgoClient:
    """Test suite AsyncOpenAlgoClient."""

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
    async def test_initialization(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test AsyncOpenAlgoClient initialization."""
        assert async_client.base_url == settings.openalgo_base_url
        assert async_client.api_key == settings.openalgo_api_key.get_secret_value()
        assert async_client.timeout == settings.request_timeout
        assert async_client.client is None

    @pytest.mark.asyncio
    async def test_enter_exit_context(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test async context manager enter/exit."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            async with async_client:
                assert async_client.client is not None
                mock_client_class.assert_called_once()
            mock_client.aclose.assert_called_once()
            assert async_client.client is None

    @pytest.mark.asyncio
    async def test_get_quotes(
        self,
        async_client: AsyncOpenAlgoClient,
        mock_async_httpx_client: AsyncMock,
        mock_async_response: MagicMock,
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
                }
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
            mock_async_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(
        self, async_client: AsyncOpenAlgoClient, mock_async_httpx_client: AsyncMock
    ) -> None:
        """Test error handling AsyncOpenAlgoClient."""
        # 1. HTTP Error
        error_response = MagicMock(spec=Response)
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "http://test/api/v1/quotes"),
            response=error_response,
        )

        mock_async_httpx_client.post.return_value = error_response
        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoAPIError):
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )

        # 2. Timeout error
        mock_async_httpx_client.post.side_effect = httpx.TimeoutException("Timeout")
        with patch.object(
            async_client, "_ensure_client", return_value=mock_async_httpx_client
        ):
            with pytest.raises(OpenAlgoError):
                await async_client._request(
                    "POST", "quotes", json={"symbols": ["NIFTY"]}
                )

    @pytest.mark.asyncio
    async def test_kill_switch_error(self, async_client: AsyncOpenAlgoClient) -> None:
        """Test KillSwitchError handling."""
        with patch(
            "src.loats.openalgo._async_check_kill_switch",
            side_effect=KillSwitchError("Kill switch active"),
        ):
            with pytest.raises(KillSwitchError):
                await async_client.place_order(
                    symbol="NIFTY", quantity=1, order_type=OrderType.MARKET
                )


class TestOpenAlgoClient:
    """Test suite OpenAlgoClient."""

    @pytest.fixture
    def client(self) -> OpenAlgoClient:
        """Create test OpenAlgoClient instance."""
        return OpenAlgoClient()

    def test_initialization(self, client: OpenAlgoClient) -> None:
        """Test OpenAlgoClient initialization."""
        assert client.base_url == settings.openalgo_base_url
        assert client.api_key == settings.openalgo_api_key.get_secret_value()
        assert client.timeout == settings.request_timeout
        assert client.client is None
