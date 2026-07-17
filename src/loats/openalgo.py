"""
OpenAlgo client implementation for LOATS13July2026.
"""

from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings
from .logging import get_logger
from .models import (
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

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """
        Initialize OpenAlgo client.

        Args:
            api_key: OpenAlgo API key. If not provided, uses settings.openalgo_api_key
            base_url: OpenAlgo base URL. If not provided,
            uses settings.openalgo_base_url

        """
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()

        self.base_url = str(base_url or settings.openalgo_base_url)
        self.timeout = settings.request_timeout
        self.client: httpx.Client | None = None

    def __enter__(self) -> "OpenAlgoClient":
        """Context manager entry."""
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"x-api-key": self.api_key},
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self.client:
            self.client.close()
            self.client = None

    def _ensure_client(self) -> httpx.Client:
        """Ensure the HTTP client is available."""
        if self.client is None:
            self.client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"x-api-key": self.api_key},
            )
        return self.client

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """
        Make an API request to OpenAlgo.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to httpx

        Returns:
            Dictionary containing the API response with success, message, data keys
        """
        client = self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "POST":
                response = client.post(url, **kwargs)
            else:
                response = client.request(method, url, **kwargs)

            # Check for HTTP error status codes
            if hasattr(response, "status_code") and response.status_code >= 400:
                return {
                    "success": False,
                    "message": f"HTTP error: {response.status_code}",
                    "data": {},
                }

            try:
                data = response.json()
                return data  # type: ignore[no-any-return]
            except ValueError as e:
                logger.error(f"JSON decode error: {e}")
                return {
                    "success": False,
                    "message": f"JSON decode error: {e}",
                    "data": {},
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            return {
                "success": False,
                "message": f"HTTP error: {e.response.status_code}",
                "data": {},
            }
        except httpx.TimeoutException:
            logger.error("Request timed out")
            return {
                "success": False,
                "message": "Timeout error",
                "data": {},
            }
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            return {
                "success": False,
                "message": f"Connection error: {e}",
                "data": {},
            }
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {
                "success": False,
                "message": f"Request failed: {e}",
                "data": {},
            }

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _convert_to_quote(self, symbol: str, data: dict[str, Any]) -> QuoteData:
        """Convert API response data to QuoteData model."""
        return QuoteData(
            symbol=symbol,
            last_price=data.get("last_price", 0.0),
            open=data.get("open", 0.0),
            high=data.get("high", 0.0),
            low=data.get("low", 0.0),
            close=data.get("close", 0.0),
            volume=data.get("volume", 0),
            timestamp=datetime.now(timezone.utc),
            change=data.get("change", 0.0),
            change_percent=data.get("change_percent", 0.0),
        )

    def _convert_to_historical_data(
        self, symbol: str, interval: str, data: dict[str, Any]
    ) -> HistoricalData:
        """Convert API response data to HistoricalData model."""
        timestamp_str = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = timestamp_str

        return HistoricalData(
            symbol=symbol,
            timestamp=timestamp,
            open=data.get("open", 0.0),
            high=data.get("high", 0.0),
            low=data.get("low", 0.0),
            close=data.get("close", 0.0),
            volume=data.get("volume", 0),
            interval=interval,
        )

    def _convert_to_position(self, data: dict[str, Any]) -> Position:
        """Convert API response data to Position model."""
        return Position(
            symbol=data.get("symbol", ""),
            quantity=data.get("quantity", 0),
            average_price=data.get("average_price", 0.0),
            last_price=data.get("last_price", 0.0),
            pnl=data.get("pnl", 0.0),
            product_type=ProductType(data.get("product_type", "MIS")),
            buy_quantity=data.get("buy_quantity", 0),
            sell_quantity=data.get("sell_quantity", 0),
        )

    def _convert_to_order(self, data: dict[str, Any]) -> Order:
        """Convert API response data to Order model."""
        timestamp_str = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = timestamp_str

        return Order(
            order_id=data.get("order_id", ""),
            symbol=data.get("symbol", ""),
            quantity=data.get("quantity", 0),
            order_type=OrderType(data.get("order_type", "MARKET")),
            price=data.get("price"),
            trigger_price=data.get("trigger_price"),
            variety=OrderVariety(data.get("variety", "regular")),
            transaction_type=TransactionType(data.get("transaction_type", "BUY")),
            product_type=ProductType(data.get("product_type", "MIS")),
            status=OrderStatus(data.get("status", "PENDING")),
            timestamp=timestamp,
            filled_quantity=data.get("filled_quantity", 0),
            average_price=data.get("average_price"),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            trailing_stop_loss=data.get("trailing_stop_loss"),
        )

    # ------------------------------------------------------------------
    # API Endpoints
    # ------------------------------------------------------------------

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        """
        Get quotes for multiple symbols.

        Args:
            symbols: List of symbol names

        Returns:
            Dictionary containing quote data
        """
        payload = {"symbols": symbols}
        return self._request("POST", "quotes", json=payload)

    def get_history(
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
        return self._request("POST", "history", json=payload)

    def get_option_chain(
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
        return self._request("POST", "option_chain", json=payload)

    def get_position_book(self) -> dict[str, Any]:
        """Get current position book."""
        return self._request("POST", "position_book")

    def get_funds(self) -> dict[str, Any]:
        """Get available funds."""
        return self._request("POST", "funds")

    def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: float | None = None,
        variety: str | OrderVariety = "regular",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
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
            trailing_stop_loss: Trailing stop loss amount

        Returns:
            Dictionary containing order response
        """
        # Normalize enum values to strings
        if isinstance(order_type, OrderType):
            order_type = order_type.value
        if isinstance(variety, OrderVariety):
            variety = variety.value
        if isinstance(transaction_type, TransactionType):
            transaction_type = transaction_type.value
        if isinstance(product_type, ProductType):
            product_type = product_type.value

        payload: dict[str, Any] = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "variety": variety,
            "transaction_type": transaction_type,
            "product_type": product_type,
        }

        # Add optional fields
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss

        return self._request("POST", "place_order", json=payload)

    def place_smart_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: float | None = None,
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
        strategy: str = "simple",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        metadata: dict[str, Any] | None = None,
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
            product_type: MIS, NRML, CNC
            metadata: Additional metadata

        Returns:
            Dictionary containing smart order response
        """
        # Normalize enum values to strings
        if isinstance(order_type, OrderType):
            order_type = order_type.value
        if isinstance(transaction_type, TransactionType):
            transaction_type = transaction_type.value
        if isinstance(product_type, ProductType):
            product_type = product_type.value

        payload: dict[str, Any] = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "strategy": strategy,
            "transaction_type": transaction_type,
            "product_type": product_type,
        }

        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss
        if metadata is not None:
            payload["metadata"] = metadata

        return self._request("POST", "place_smart_order", json=payload)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        order_type: str | OrderType | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
    ) -> dict[str, Any]:
        """
        Modify an existing order.

        Args:
            order_id: Order ID to modify
            quantity: New quantity
            order_type: New order type
            price: New price
            trigger_price: New trigger price
            stop_loss: New stop loss price
            take_profit: New take profit price
            trailing_stop_loss: New trailing stop loss amount

        Returns:
            Dictionary containing modification response
        """
        if isinstance(order_type, OrderType):
            order_type = order_type.value

        payload: dict[str, Any] = {"order_id": order_id}

        if quantity is not None:
            payload["quantity"] = quantity
        if order_type is not None:
            payload["order_type"] = order_type
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss

        return self._request("POST", "modify_order", json=payload)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            Dictionary containing cancellation response
        """
        payload = {"order_id": order_id}
        return self._request("POST", "cancel_order", json=payload)

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        """
        Get status of an order.

        Args:
            order_id: Order ID to check

        Returns:
            Dictionary containing order status
        """
        payload = {"order_id": order_id}
        return self._request("POST", "order_status", json=payload)

    def get_all_orders(self) -> dict[str, Any]:
        """
        Get all orders.

        Returns:
            Dictionary containing all orders
        """
        return self._request("POST", "all_orders")

    def get_trade_book(self) -> dict[str, Any]:
        """
        Get trade book.

        Returns:
            Dictionary containing trade book data
        """
        return self._request("POST", "trade_book")


# Export a default client instance
client = OpenAlgoClient()


class AsyncOpenAlgoClient:
    """Async client for interacting with OpenAlgo API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """
        Initialize AsyncOpenAlgoClient.

        Args:
            api_key: OpenAlgo API key. If not provided, uses settings.openalgo_api_key
            base_url: OpenAlgo base URL. If not provided,
            uses settings.openalgo_base_url

        """
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url = str(base_url or settings.openalgo_base_url)
        self.timeout = settings.request_timeout
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AsyncOpenAlgoClient":
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"x-api-key": self.api_key},
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP async client is available."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"x-api-key": self.api_key},
            )
        return self.client

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make an async API request to OpenAlgo.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments to pass to httpx

        Returns:
            Dictionary containing the API response

        Raises:
            OpenAlgoAPIError: For API response errors
            OpenAlgoError: For other request errors
        """
        client = await self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "POST":
                response = await client.post(url, **kwargs)
            else:
                response = await client.request(method, url, **kwargs)

            # Check for HTTP error status codes
            if hasattr(response, "status_code") and response.status_code >= 400:
                raise OpenAlgoAPIError(
                    status_code=response.status_code,
                    message=f"HTTP error: {response.status_code}",
                    details={"response": response.text},
                )

            try:
                data = response.json()
                return data  # type: ignore[no-any-return]
            except ValueError as e:
                logger.error(f"JSON decode error: {e}")
                raise OpenAlgoError(f"JSON decode error: {e}") from e

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            raise OpenAlgoAPIError(
                status_code=e.response.status_code,
                message=f"HTTP error: {e.response.status_code}",
                details={"response": e.response.text},
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out: {e}")
            raise OpenAlgoError(f"Timeout error: {e}") from e
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            raise OpenAlgoError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise OpenAlgoError(f"Request failed: {e}") from e

    # ------------------------------------------------------------------
    # API Endpoints
    # ------------------------------------------------------------------

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
        """Get current position book."""
        return await self._request("POST", "position_book")

    async def get_funds(self) -> dict[str, Any]:
        """Get available funds."""
        return await self._request("POST", "funds")

    async def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: float | None = None,
        variety: str | OrderVariety = "regular",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
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
            trailing_stop_loss: Trailing stop loss amount

        Returns:
            Dictionary containing order response
        """
        # Normalize enum values to strings
        if isinstance(order_type, OrderType):
            order_type = order_type.value
        if isinstance(variety, OrderVariety):
            variety = variety.value
        if isinstance(transaction_type, TransactionType):
            transaction_type = transaction_type.value
        if isinstance(product_type, ProductType):
            product_type = product_type.value

        payload: dict[str, Any] = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "variety": variety,
            "transaction_type": transaction_type,
            "product_type": product_type,
        }

        # Add optional fields
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss

        return await self._request("POST", "place_order", json=payload)

    async def place_smart_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: float | None = None,
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
        strategy: str = "simple",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        metadata: dict[str, Any] | None = None,
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
            product_type: MIS, NRML, CNC
            metadata: Additional metadata

        Returns:
            Dictionary containing smart order response
        """
        # Normalize enum values to strings
        if isinstance(order_type, OrderType):
            order_type = order_type.value
        if isinstance(transaction_type, TransactionType):
            transaction_type = transaction_type.value
        if isinstance(product_type, ProductType):
            product_type = product_type.value

        payload: dict[str, Any] = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "strategy": strategy,
            "transaction_type": transaction_type,
            "product_type": product_type,
        }

        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss
        if metadata is not None:
            payload["metadata"] = metadata

        return await self._request("POST", "place_smart_order", json=payload)

    async def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        order_type: str | OrderType | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_loss: float | None = None,
    ) -> dict[str, Any]:
        """
        Modify an existing order.

        Args:
            order_id: Order ID to modify
            quantity: New quantity
            order_type: New order type
            price: New price
            trigger_price: New trigger price
            stop_loss: New stop loss price
            take_profit: New take profit price
            trailing_stop_loss: New trailing stop loss amount

        Returns:
            Dictionary containing modification response
        """
        if isinstance(order_type, OrderType):
            order_type = order_type.value

        payload: dict[str, Any] = {"order_id": order_id}

        if quantity is not None:
            payload["quantity"] = quantity
        if order_type is not None:
            payload["order_type"] = order_type
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit
        if trailing_stop_loss is not None:
            payload["trailing_stop_loss"] = trailing_stop_loss

        return await self._request("POST", "modify_order", json=payload)

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

    async def get_all_orders(self) -> dict[str, Any]:
        """
        Get all orders.

        Returns:
            Dictionary containing all orders
        """
        return await self._request("POST", "all_orders")

    async def get_trade_book(self) -> dict[str, Any]:
        """
        Get trade book.

        Returns:
            Dictionary containing trade book data
        """
        return await self._request("POST", "trade_book")


# Export async client instance for scheduler
async_client = AsyncOpenAlgoClient()
