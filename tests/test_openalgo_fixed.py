"""
Test suite for openalgo_fixed.py module to achieve 80%+ coverage.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.loats.models import QuoteData
from src.loats.openalgo_fixed import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
    _async_check_kill_switch,
    _check_kill_switch,
)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("src.loats.openalgo_fixed.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.openalgo_api_key.get_secret_value.return_value = "test_api_key"
        mock_settings.openalgo_base_url = "https://api.test.com"
        mock_settings.request_timeout = 30.0
        mock_get_settings.return_value = mock_settings
        yield mock_get_settings


@pytest.fixture
def openalgo_client(mock_settings):
    """Create OpenAlgoClient instance for testing."""
    return OpenAlgoClient()


@pytest.fixture
def async_openalgo_client(mock_settings):
    """Create AsyncOpenAlgoClient instance for testing."""
    return AsyncOpenAlgoClient()


def test_openalgo_client_initialization(openalgo_client):
    """Test OpenAlgoClient initialization."""
    assert openalgo_client.api_key == "test_api_key"
    assert openalgo_client.base_url == "https://api.test.com"
    assert openalgo_client.timeout == 30.0
    assert openalgo_client.client is None


def test_openalgo_client_context_manager(openalgo_client):
    """Test OpenAlgoClient context manager."""
    with patch("httpx.Client") as mock_client:
        with openalgo_client:
            assert openalgo_client.client is not None
            mock_client.assert_called_once()

        assert openalgo_client.client is None


def test_openalgo_client_ensure_client(openalgo_client):
    """Test _ensure_client method."""
    with patch("httpx.Client"):
        client = openalgo_client._ensure_client()
        assert client is not None
        assert openalgo_client.client is not None

        # Second call should return same client
        same_client = openalgo_client._ensure_client()
        assert same_client is client


def test_openalgo_client_request_success(openalgo_client):
    """Test successful _request method."""
    with patch("httpx.Client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        mock_client_instance.request.return_value = MagicMock(
            status_code=200, json=lambda: {"test": "data"}
        )

        result = openalgo_client._request("GET", "/test")
        assert result == {"test": "data"}


def test_openalgo_client_request_http_error(openalgo_client):
    """Test _request method with HTTP error."""
    with patch("httpx.Client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_client_instance.request.return_value = mock_response

        with pytest.raises(OpenAlgoAPIError) as exc_info:
            openalgo_client._request("GET", "/test")

        assert exc_info.value.status_code == 404
        assert "Not Found" in str(exc_info.value)


def test_openalgo_client_request_timeout(openalgo_client):
    """Test _request method with timeout."""
    with patch("httpx.Client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        mock_client_instance.request.side_effect = httpx.TimeoutException("Timeout")

        with pytest.raises(OpenAlgoError) as exc_info:
            openalgo_client._request("GET", "/test")

        assert "Timeout error" in str(exc_info.value)


def test_openalgo_client_request_connection_error(openalgo_client):
    """Test _request method with connection error."""
    with patch("httpx.Client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        mock_client_instance.request.side_effect = httpx.ConnectError(
            "Connection failed"
        )

        with pytest.raises(OpenAlgoError) as exc_info:
            openalgo_client._request("GET", "/test")

        assert "Connection error" in str(exc_info.value)


def test_openalgo_client_convert_to_quote(openalgo_client):
    """Test _convert_to_quote method."""
    test_data = {
        "last_price": 100.50,
        "open": 99.25,
        "high": 101.75,
        "low": 98.50,
        "close": 100.25,
        "volume": 10000,
        "change": 1.25,
        "change_percent": 1.25,
    }

    quote = openalgo_client._convert_to_quote("TEST", test_data)
    assert isinstance(quote, QuoteData)
    assert quote.symbol == "TEST"
    assert quote.last_price == 100.50


def test_openalgo_client_convert_to_historical_data(openalgo_client):
    """Test _convert_to_historical_data method."""
    test_data = {
        "timestamp": "2023-01-01T10:00:00",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 5000,
    }

    historical = openalgo_client._convert_to_historical_data("TEST", "15min", test_data)
    assert historical.symbol == "TEST"
    assert historical.open == 100.0
    assert historical.interval == "15min"


def test_openalgo_client_get_quotes(openalgo_client):
    """Test get_quotes method."""
    with patch.object(openalgo_client, "_request") as mock_request:
        mock_request.return_value = {
            "TEST": {"last_price": 100.50, "open": 99.25, "high": 101.75, "low": 98.50}
        }

        result = openalgo_client.get_quotes(["TEST"])
        assert "TEST" in result
        assert isinstance(result["TEST"], dict)  # Sync version returns raw dict
        assert result["TEST"]["last_price"] == 100.50


def test_openalgo_client_place_order(openalgo_client):
    """Test place_order method."""
    with patch.object(openalgo_client, "_request") as mock_request:
        with patch("src.loats.openalgo_fixed._check_kill_switch"):
            mock_request.return_value = {
                "order_id": "test_order_123",
                "status": "success",
            }

            result = openalgo_client.place_order(
                symbol="TEST",
                quantity=10,
                price=100.50,
                order_type="LIMIT",
                product_type="INTRADAY",
            )
            assert result["order_id"] == "test_order_123"


def test_openalgo_client_place_order_kill_switch(openalgo_client):
    """Test place_order method with kill switch active."""
    with patch("src.loats.openalgo_fixed._check_kill_switch") as mock_check:
        mock_check.side_effect = KillSwitchError()

        with pytest.raises(KillSwitchError):
            openalgo_client.place_order(
                symbol="TEST",
                quantity=10,
                price=100.50,
                order_type="LIMIT",
                product_type="INTRADAY",
            )


def test_kill_switch_error():
    """Test KillSwitchError exception."""
    error = KillSwitchError("Custom message")
    assert str(error) == "Custom message"


def test_openalgo_api_error():
    """Test OpenAlgoAPIError exception."""
    error = OpenAlgoAPIError(404, "Not Found", {"detail": "Resource not found"})
    assert error.status_code == 404
    assert "Not Found" in str(error)
    assert error.details == {"detail": "Resource not found"}


def test_check_kill_switch_inactive():
    """Test _check_kill_switch when inactive."""
    with patch("src.loats.openalgo_fixed._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = False
        mock_get_alerts.return_value = mock_alerts

        # Should not raise exception
        _check_kill_switch()


def test_check_kill_switch_active():
    """Test _check_kill_switch when active."""
    with patch("src.loats.openalgo_fixed._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = True
        mock_get_alerts.return_value = mock_alerts

        with pytest.raises(KillSwitchError):
            _check_kill_switch()


@pytest.mark.asyncio
async def test_async_check_kill_switch_inactive():
    """Test async _check_kill_switch when inactive."""
    with patch("src.loats.openalgo_fixed._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = False
        mock_get_alerts.return_value = mock_alerts

        # Should not raise exception
        await _async_check_kill_switch()


@pytest.mark.asyncio
async def test_async_check_kill_switch_active():
    """Test async _check_kill_switch when active."""
    with patch("src.loats.openalgo_fixed._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = True
        mock_get_alerts.return_value = mock_alerts

        with pytest.raises(KillSwitchError):
            await _async_check_kill_switch()


@pytest.mark.asyncio
async def test_async_openalgo_client_initialization(async_openalgo_client):
    """Test AsyncOpenAlgoClient initialization."""
    assert async_openalgo_client.api_key == "test_api_key"
    assert async_openalgo_client.base_url == "https://api.test.com"
    assert async_openalgo_client.timeout == 30.0
    assert async_openalgo_client.client is None


@pytest.mark.asyncio
async def test_async_openalgo_client_context_manager(async_openalgo_client):
    """Test AsyncOpenAlgoClient context manager."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        async with async_openalgo_client:
            assert async_openalgo_client.client is not None
            mock_client_class.assert_called_once()

        assert async_openalgo_client.client is None


@pytest.mark.asyncio
async def test_async_openalgo_client_ensure_client(async_openalgo_client):
    """Test async _ensure_client method."""
    with patch("httpx.AsyncClient"):
        client = await async_openalgo_client._ensure_client()
        assert client is not None
        assert async_openalgo_client.client is not None


@pytest.mark.asyncio
async def test_async_openalgo_client_request_success(async_openalgo_client):
    """Test successful async _request method."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_client_instance.request.return_value = mock_response

        result = await async_openalgo_client._request("GET", "/test")
        assert result == {"test": "data"}


@pytest.mark.asyncio
async def test_async_openalgo_client_get_quotes(async_openalgo_client):
    """Test async get_quotes method."""
    with patch.object(async_openalgo_client, "_request") as mock_request:
        mock_request.return_value = {
            "TEST": {"last_price": 100.50, "open": 99.25, "high": 101.75, "low": 98.50}
        }

        result = await async_openalgo_client.get_quotes(["TEST"])
        assert "TEST" in result
        assert isinstance(result["TEST"], dict)  # Async version returns raw dict
        assert result["TEST"]["last_price"] == 100.50


@pytest.mark.asyncio
async def test_async_openalgo_client_place_order(async_openalgo_client):
    """Test async place_order method."""
    with patch.object(async_openalgo_client, "_request") as mock_request:
        with patch("src.loats.openalgo_fixed._async_check_kill_switch"):
            mock_request.return_value = {
                "order_id": "test_order_123",
                "status": "success",
            }

            result = await async_openalgo_client.place_order(
                symbol="TEST",
                quantity=10,
                price=100.50,
                order_type="LIMIT",
                product_type="INTRADAY",
            )
            assert result["order_id"] == "test_order_123"


@pytest.mark.asyncio
async def test_async_openalgo_client_place_order_kill_switch(async_openalgo_client):
    """Test async place_order method with kill switch active."""
    with patch("src.loats.openalgo_fixed._async_check_kill_switch") as mock_check:
        mock_check.side_effect = KillSwitchError()

        with pytest.raises(KillSwitchError):
            await async_openalgo_client.place_order(
                symbol="TEST",
                quantity=10,
                price=100.50,
                order_type="LIMIT",
                product_type="INTRADAY",
            )
