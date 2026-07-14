"""
OpenAlgo client implementation for LOATS13July2026.
"""

from typing import Any

import httpx

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class OpenAlgoError(Exception):
    """Base exception for OpenAlgo client errors."""


class OpenAlgoAPIError(OpenAlgoError):
    """Exception for API response errors."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")


class OpenAlgoClient:
    """Client for interacting with OpenAlgo API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """
        Initialize OpenAlgo client.

        Args:
            api_key: OpenAlgo API key. If not provided, uses settings.openalgo_api_key
            base_url: OpenAlgo base URL. If not provided, uses settings.openalgo_base_url
        """
        self.api_key = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url = str(base_url or settings.openalgo_base_url)

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """
        Make an API request to OpenAlgo.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            Dictionary containing the API response

        Raises:
            OpenAlgoAPIError: If the API request fails
            OpenAlgoError: For other client errors
        """
        url = f"/api/v1/{endpoint.lstrip('/')}"
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()

            data = response.json()
            if not data.get("success", True):
                raise OpenAlgoAPIError(
                    status_code=response.status_code,
                    message=data.get("message", "Unknown API error"),
                    details=data,
                )

            return data

        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                raise OpenAlgoAPIError(
                    status_code=e.response.status_code,
                    message=error_data.get("message", str(e)),
                    details=error_data,
                )
            except ValueError:
                raise OpenAlgoAPIError(
                    status_code=e.response.status_code,
                    message=str(e),
                    details={"response_text": e.response.text},
                )
        except httpx.RequestError as e:
            raise OpenAlgoError(f"Request failed: {e!s}")
        except ValueError as e:
            raise OpenAlgoError(f"Failed to parse response: {e!s}")

    # API Endpoints

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        """
        Get quotes for multiple symbols.

        Args:
            symbols: List of symbol names

        Returns:
            Dictionary containing quote data
        """
        payload = {"symbols": symbols}
        return await self._request("POST", "quotes", json=payload)

    async def get_history(
        self,
        symbol: str,
        interval: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Get historical data for a symbol.

        Args:
            symbol: Symbol name
            interval: Time interval (e.g., "1min", "5min", "1day")
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            Dictionary containing historical data
        """
        payload = {
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
        }
        return await self._request("POST", "history", json=payload)

    async def get_option_chain(
        self,
        symbol: str,
        expiry: str | None = None,
    ) -> dict[str, Any]:
        """
        Get option chain for a symbol.

        Args:
            symbol: Symbol name
            expiry: Expiry date in YYYY-MM-DD format

        Returns:
            Dictionary containing option chain data
        """
        payload = {"symbol": symbol, "expiry": expiry}
        return await self._request("POST", "option_chain", json=payload)

    async def get_position_book(self) -> dict[str, Any]:
        """
        Get current position book.

        Returns:
            Dictionary containing position book data
        """
        return await self._request("POST", "position_book")

    async def get_funds(self) -> dict[str, Any]:
        """
        Get available funds.

        Returns:
            Dictionary containing funds data
        """
        return await self._request("POST", "funds")

    async def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str,
        price: float | None = None,
        variety: str = "regular",
        transaction_type: str = "BUY",
        product_type: str = "MIS",
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """
        Place an order.

        Args:
            symbol: Symbol name
            quantity: Order quantity
            order_type: Order type (MARKET, LIMIT, SL, SL-M)
            price: Order price (required for LIMIT, SL, SL-M)
            variety: Order variety (regular, amo)
            transaction_type: BUY or SELL
            product_type: MIS, NRML, CNC
            trigger_price: Trigger price for SL orders
            stop_loss: Stop loss price
            take_profit: Take profit price

        Returns:
            Dictionary containing order response
        """
        payload = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "variety": variety,
            "transaction_type": transaction_type,
            "product_type": product_type,
            "price": price,
            "trigger_price": trigger_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        return await self._request("POST", "place_order", json=payload)

    async def place_smart_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str,
        price: float | None = None,
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
        strategy: str = "simple",
        transaction_type: str = "BUY",
    ) -> dict[str, Any]:
        """
        Place a smart order with advanced features.

        Args:
            symbol: Symbol name
            quantity: Order quantity
            order_type: Order type (MARKET, LIMIT, SL, SL-M)
            price: Order price
            trigger_price: Trigger price for SL orders
            stop_loss: Stop loss price
            take_profit: Take profit price
            trailing_stop_loss: Trailing stop loss amount
            strategy: Strategy type (simple, bracket, cover)
            transaction_type: BUY or SELL

        Returns:
            Dictionary containing smart order response
        """
        payload = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "price": price,
            "trigger_price": trigger_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop_loss": trailing_stop_loss,
            "strategy": strategy,
            "transaction_type": transaction_type,
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        return await self._request("POST", "place_smart_order", json=payload)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            Dictionary containing cancellation response
        """
        payload = {"order_id": order_id}
        return await self._request("POST", "cancel_order", json=payload)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        """
        Get status of an order.

        Args:
            order_id: Order ID to check

        Returns:
            Dictionary containing order status
        """
        payload = {"order_id": order_id}
        return await self._request("POST", "order_status", json=payload)


# Export a default client instance
client = OpenAlgoClient()
