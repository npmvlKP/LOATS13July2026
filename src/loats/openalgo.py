"""
OpenAlgo client implementation LOATS13July2026.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Optional, TYPE_CHECKING

import httpx

from .config import get_settings
from .loats_logging import get_logger
from .utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
    RateLimitExceededError,
)
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
from .utils.cache import cache_manager

if TYPE_CHECKING:
    from .alerts import AlertSystem

logger = get_logger(__name__)

class OpenAlgoError(Exception):
    """Base exception OpenAlgo client errors."""

class KillSwitchError(OpenAlgoError):
    """Exception raised when order placement attempted while kill switch active."""

    def __init__(self, message: str = "Kill switch active, order placement blocked") -> None:
        self.message = message
        super().__init__(self.message)

class OpenAlgoAPIError(OpenAlgoError):
    """Exception API response errors."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"API Error {status_code}: {message}")

def _get_alerts() -> AlertSystem:
    """Lazy import alerts avoid circular import."""
    from .alerts import alerts
    return alerts

def _check_kill_switch() -> None:
    """Check kill switch active."""
    alerts = _get_alerts()
    if alerts.is_kill_switch_active():
        logger.error("Kill switch active, order placement blocked")
        raise KillSwitchError()

async def _async_check_kill_switch() -> None:
    """Async version: Check kill switch active."""
    alerts = _get_alerts()
    if alerts.is_kill_switch_active():
        logger.error("Kill switch active, order placement blocked")
        raise KillSwitchError()

class OpenAlgoClient:
    """Client interacting OpenAlgo API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url: str = base_url or settings.openalgo_base_url
        self.timeout: float = settings.request_timeout
        self.client: Optional[httpx.Client] = None

    def __enter__(self) -> OpenAlgoClient:
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"x-api-key": self.api_key},
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.client:
            self.client.close()
            self.client = None

    def _ensure_client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"x-api-key": self.api_key},
            )
        return self.client

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        client = self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "POST":
                response = client.post(url, **kwargs)
            else:
                response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            logger.error(f"API HTTP error {e.response.status_code}: {e.response.text}")
            raise OpenAlgoAPIError(
                status_code=e.response.status_code,
                message=f"HTTP error: {e.response.status_code}",
                details={"response": e.response.text},
            )
        except ValueError as e:
            logger.error(f"JSON decode error: {e}")
            raise OpenAlgoError(f"JSON decode error: {e}")
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out: {e}")
            raise OpenAlgoError(f"Timeout error: {e}")
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            raise OpenAlgoError(f"Connection error: {e}")
        except OpenAlgoError:
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise OpenAlgoError(f"Request failed: {e}")

    def _convert_to_quote(self, symbol: str, data: dict[str, Any]) -> QuoteData:
        return QuoteData(
            symbol=symbol,
            last_price=data.get("last_price", 0.0),
            open=data.get("open", 0.0),
            high=data.get("high", 0.0),
            low=data.get("low", 0.0),
            close=data.get("close", 0.0),
            volume=data.get("volume", 0),
            timestamp=datetime.now(UTC),
            change=data.get("change", 0.0),
            change_percent=data.get("change_percent", 0.0),
        )

    def _convert_to_historical_data(
        self, symbol: str, interval: str, data: dict[str, Any]
    ) -> HistoricalData:
        timestamp_str = data.get("timestamp", datetime.now(UTC).isoformat())
        timestamp = (
            datetime.fromisoformat(timestamp_str)
            if isinstance(timestamp_str, str)
            else timestamp_str
        )
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
        timestamp_str = data.get("timestamp", datetime.now(UTC).isoformat())
        timestamp = (
            datetime.fromisoformat(timestamp_str)
            if isinstance(timestamp_str, str)
            else timestamp_str
        )
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

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        payload = {"symbols": symbols}
        return self._request("POST", "quotes", json=payload)

    def get_history(
        self,
        symbol: str,
        interval: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
        }
        return self._request("POST", "history", json=payload)

    def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> dict[str, Any]:
        payload = {"symbol": symbol, "expiry": expiry}
        return self._request("POST", "option_chain", json=payload)

    def get_position_book(self) -> dict[str, Any]:
        return self._request("POST", "position_book")

    def get_funds(self) -> dict[str, Any]:
        return self._request("POST", "funds")

    def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: Optional[float] = None,
        variety: str | OrderVariety = "regular",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
    ) -> dict[str, Any]:
        _check_kill_switch()
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
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
        strategy: str = "simple",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        _check_kill_switch()
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
        quantity: Optional[int] = None,
        order_type: Optional[str | OrderType] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
    ) -> dict[str, Any]:
        _check_kill_switch()
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
        _check_kill_switch()
        payload = {"order_id": order_id}
        return self._request("POST", "cancel_order", json=payload)

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        payload = {"order_id": order_id}
        return self._request("POST", "order_status", json=payload)

    def get_all_orders(self) -> dict[str, Any]:
        return self._request("POST", "all_orders")

    def get_trade_book(self) -> dict[str, Any]:
        return self._request("POST", "trade_book")

class AsyncOpenAlgoClient:
    """Async client interacting OpenAlgo API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url: str = base_url or settings.openalgo_base_url
        self.timeout: float = settings.request_timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> AsyncOpenAlgoClient:
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"x-api-key": self.api_key},
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"x-api-key": self.api_key},
            )
        return self.client

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        client = await self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "POST":
                response = await client.post(url, **kwargs)
            else:
                response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            logger.error(f"API HTTP error {e.response.status_code}: {e.response.text}")
            raise OpenAlgoAPIError(
                status_code=e.response.status_code,
                message=f"HTTP error: {e.response.status_code}",
                details={"response": e.response.text},
            )
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise OpenAlgoError(f"Request failed: {e}")

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        symbols_sorted = sorted(symbols)
        cache_key = f"quotes:{hash(frozenset(symbols_sorted))}"
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug(f"Quotes cache hit {symbols}")
                return json.loads(cached_result)  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning(f"Failed parse cached quotes: {e}")
        payload = {"symbols": symbols}
        result = await self._request("POST", "quotes", json=payload)
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=60)
            logger.debug(f"Cached quotes {symbols}")
        except Exception as e:
            logger.warning(f"Failed cache quotes: {e}")
        return result

    async def get_history(
        self,
        symbol: str,
        interval: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
        }
        return await self._request("POST", "history", json=payload)

    async def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> dict[str, Any]:
        payload = {"symbol": symbol, "expiry": expiry}
        return await self._request("POST", "option_chain", json=payload)

    async def get_position_book(self) -> dict[str, Any]:
        return await self._request("POST", "position_book")

    async def get_funds(self) -> dict[str, Any]:
        return await self._request("POST", "funds")

    async def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str | OrderType,
        price: Optional[float] = None,
        variety: str | OrderVariety = "regular",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
    ) -> dict[str, Any]:
        await _async_check_kill_switch()
        if not await get_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded order placement")
            raise RateLimitExceededError("Rate limit exceeded")
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
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
        strategy: str = "simple",
        transaction_type: str | TransactionType = "BUY",
        product_type: str | ProductType = "MIS",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        await _async_check_kill_switch()
        if not await get_smart_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded smart order placement")
            raise RateLimitExceededError("Rate limit exceeded")
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
        quantity: Optional[int] = None,
        order_type: Optional[str | OrderType] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: Optional[float] = None,
    ) -> dict[str, Any]:
        await _async_check_kill_switch()
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
        await _async_check_kill_switch()
        payload = {"order_id": order_id}
        return await self._request("POST", "cancel_order", json=payload)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        payload = {"order_id": order_id}
        return await self._request("POST", "order_status", json=payload)

    async def get_all_orders(self) -> dict[str, Any]:
        return await self._request("POST", "all_orders")

    async def get_trade_book(self) -> dict[str, Any]:
        return await self._request("POST", "trade_book")

async_client = AsyncOpenAlgoClient()