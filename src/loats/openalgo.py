"""
OpenAlgo client implementation LOATS13July2026.

Circuit Breaker Pattern for Order Operations:
------------------------------------------
Order placement methods (place_order, place_smart_order, modify_order, cancel_order)
use circuit breaker protection WITHOUT retry to prevent duplicate orders.

Rationale:
- Retrying POST operations can create duplicate orders if the original request
  succeeded but the response was lost
- Circuit breaker provides fail-fast behavior when OpenAlgo is down
- When circuit is open, methods fail immediately with CircuitBreakerOpenError
- This conserves resources and provides faster operator alerting

Contrast with GET operations:
- Read-only operations use circuit_breaker_retry_async decorator
- These can safely retry as they don't modify state
- Example: scheduler's _safe_get_* methods, alerts' _safe_get_* methods

Idempotency Keys for Order Operations:
-------------------------------------
Every order placement sends an Idempotency-Key header (UUID v4) so a broker
can deduplicate retried submissions. Keys are persisted in a TTL-bounded
local store keyed by a stable request identity so retries reuse the same key:
- modify_order / cancel_order: keyed by order_id (stable across retries)
- place_order / place_smart_order: keyed by canonical payload digest

This covers the kill-switch cancel path in alerts.py, which retries
cancel_order up to 3 attempts via openalgo_circuit_breaker_retry_async.
NOTE: OpenAlgo server-side honoring of Idempotency-Key is unconfirmed; the
header is inert if ignored. The no-retry circuit breaker on order placement
remains the primary duplicate-order control.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from .config import get_settings
from .loats_logging import get_logger
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
from .utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER
from .utils.payload_builder import (
    build_modify_order_payload,
    build_place_order_payload,
    build_place_smart_order_payload,
)
from .utils.rate_limiter import (
    RateLimitExceededError,
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
    get_sync_order_rate_limiter,
    get_sync_smart_order_rate_limiter,
)

if TYPE_CHECKING:
    from .alerts import AlertSystem

logger = get_logger(__name__)


_IDEMPOTENCY_TTL_SECONDS = 300.0
_IDEMPOTENCY_KEY_MAX_ENTRIES = 1024
_idempotency_keys: dict[str, tuple[str, float]] = {}
_idempotency_lock = threading.Lock()


def _get_idempotency_key(identity: str) -> str:
    """Get-or-create idempotency key for a stable request identity.

    Retries of the same logical order reuse the same key within the TTL
    window, letting the broker deduplicate repeated submissions.
    """
    now = time.monotonic()
    with _idempotency_lock:
        entry = _idempotency_keys.get(identity)
        if entry is not None and now < entry[1]:
            return entry[0]
        key = str(uuid.uuid4())
        _idempotency_keys[identity] = (key, now + _IDEMPOTENCY_TTL_SECONDS)
        if len(_idempotency_keys) > _IDEMPOTENCY_KEY_MAX_ENTRIES:
            expired = [
                ident
                for ident, (_, expiry) in _idempotency_keys.items()
                if expiry < now
            ]
            for ident in expired:
                del _idempotency_keys[ident]
        return key


def _order_payload_digest(payload: dict[str, Any]) -> str:
    """Canonical digest identifying a logical order placement."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


class OpenAlgoError(Exception):
    """Base exception OpenAlgo client errors."""


class KillSwitchError(OpenAlgoError):
    """Exception raised when order placement attempted while kill switch active."""

    def __init__(
        self, message: str = "Kill switch active, order placement blocked"
    ) -> None:
        self.message = message
        super().__init__(self.message)


class OpenAlgoAPIError(OpenAlgoError):
    """Exception API response errors."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: dict[str, Any] | None = None,
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
        # Log audit entry for kill switch activation
        try:
            from .database import db

            db._log_audit(
                action="BLOCK",
                entity_type="order",
                entity_id="kill_switch_blocked",
                user="system",
                metadata={"reason": "Kill switch active"},
                previous_state=None,
                new_state={"status": "blocked", "reason": "kill_switch_active"},
            )
        except Exception as e:
            logger.error(f"Failed to write audit log for kill switch block: {e}")
        raise KillSwitchError("Kill switch active, order placement blocked")


async def _async_check_kill_switch() -> None:
    """Async version: Check kill switch active."""
    alerts = _get_alerts()
    if alerts.is_kill_switch_active():
        logger.error("Kill switch active, order placement blocked")
        # Log audit entry for kill switch activation
        try:
            from .database import db

            db._log_audit(
                action="BLOCK",
                entity_type="order",
                entity_id="kill_switch_blocked",
                user="system",
                metadata={"reason": "Kill switch active"},
                previous_state=None,
                new_state={"status": "blocked", "reason": "kill_switch_active"},
            )
        except Exception as e:
            logger.error(f"Failed to write audit log for kill switch block: {e}")
        raise KillSwitchError("Kill switch active, order placement blocked")


class OpenAlgoClient:
    """Client interacting OpenAlgo API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url: str = base_url or settings.openalgo_base_url
        self.timeout: float = settings.request_timeout
        self.client: httpx.Client | None = None

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

    def _request(
        self,
        method: str,
        endpoint: str,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"
        if idempotency_key is not None:
            headers = dict(kwargs.pop("headers", None) or {})
            headers["Idempotency-Key"] = idempotency_key
            kwargs["headers"] = headers
        try:
            if method.upper() == "POST":
                response = client.post(url, **kwargs)
            else:
                response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return, unused-ignore]
        except httpx.HTTPStatusError as e:
            logger.error(f"API HTTP error {e.response.status_code}: {e.response.text}")
            raise OpenAlgoAPIError(
                status_code=e.response.status_code,
                message=e.response.text,
                details={"response": e.response.text},
            ) from e
        except ValueError as e:
            logger.error(f"JSON decode error: {e}")
            raise OpenAlgoError(f"JSON decode error: {e}") from e
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out: {e}")
            raise OpenAlgoError(f"Timeout error: {e}") from e
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            raise OpenAlgoError(f"Connection error: {e}") from e
        except OpenAlgoError:
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise OpenAlgoError(f"Request failed: {e}") from e

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
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
        }
        return self._request("POST", "history", json=payload)

    def get_option_chain(
        self, symbol: str, expiry: str | None = None
    ) -> dict[str, Any]:
        # Note: caching is intentionally omitted here; the shared cache_manager is
        # async-only and cannot be awaited from this synchronous client. Use
        # AsyncOpenAlgoClient.get_option_chain for cached access.
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
        Place an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate orders.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        _check_kill_switch()
        # Use configured rate limits for order operations
        if not get_sync_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded order placement")
            raise RateLimitExceededError("Rate limit exceeded")

        payload = build_place_order_payload(
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            price=price,
            variety=variety,
            transaction_type=transaction_type,
            product_type=product_type,
            trigger_price=trigger_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_loss=trailing_stop_loss,
        )

        # Wrap order placement in circuit breaker without retry
        def _place_order_impl() -> dict[str, Any]:
            return self._request(
                "POST",
                "place_order",
                json=payload,
                idempotency_key=_get_idempotency_key(
                    f"place:{_order_payload_digest(payload)}"
                ),
            )

        return OPENALGO_CIRCUIT_BREAKER.call(_place_order_impl)

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
        Place a smart order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate orders.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        _check_kill_switch()
        # Use configured rate limits for smart order operations
        if not get_sync_smart_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded smart order placement")
            raise RateLimitExceededError("Rate limit exceeded")

        payload = build_place_smart_order_payload(
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_loss=trailing_stop_loss,
            strategy=strategy,
            transaction_type=transaction_type,
            product_type=product_type,
            metadata=metadata,
        )

        # Wrap smart order placement in circuit breaker without retry
        def _place_smart_order_impl() -> dict[str, Any]:
            return self._request(
                "POST",
                "place_smart_order",
                json=payload,
                idempotency_key=_get_idempotency_key(
                    f"place_smart_order:{_order_payload_digest(payload)}"
                ),
            )

        return OPENALGO_CIRCUIT_BREAKER.call(_place_smart_order_impl)

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
        Modify an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate modifications.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        _check_kill_switch()
        payload = build_modify_order_payload(
            order_id=order_id,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_loss=trailing_stop_loss,
        )

        # Wrap order modification in circuit breaker without retry
        def _modify_order_impl() -> dict[str, Any]:
            return self._request(
                "POST",
                "modify_order",
                json=payload,
                idempotency_key=_get_idempotency_key(f"modify:{order_id}"),
            )

        return OPENALGO_CIRCUIT_BREAKER.call(_modify_order_impl)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate cancellations.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        _check_kill_switch()
        payload = {"order_id": order_id}

        # Wrap order cancellation in circuit breaker without retry
        def _cancel_order_impl() -> dict[str, Any]:
            return self._request(
                "POST",
                "cancel_order",
                json=payload,
                idempotency_key=_get_idempotency_key(f"cancel:{order_id}"),
            )

        return OPENALGO_CIRCUIT_BREAKER.call(_cancel_order_impl)

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        payload = {"order_id": order_id}
        return self._request("POST", "order_status", json=payload)

    def get_all_orders(self) -> dict[str, Any]:
        return self._request("POST", "all_orders")

    def get_trade_book(self) -> dict[str, Any]:
        return self._request("POST", "trade_book")


class AsyncOpenAlgoClient:
    """Async client interacting OpenAlgo API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.api_key: str = api_key or settings.openalgo_api_key.get_secret_value()
        self.base_url: str = base_url or settings.openalgo_base_url
        self.timeout: float = settings.request_timeout
        self.client: httpx.AsyncClient | None = None

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

    async def _request(
        self,
        method: str,
        endpoint: str,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = await self._ensure_client()
        url = f"/api/v1/{endpoint.lstrip('/')}"
        if idempotency_key is not None:
            headers = dict(kwargs.pop("headers", None) or {})
            headers["Idempotency-Key"] = idempotency_key
            kwargs["headers"] = headers
        try:
            if method.upper() == "POST":
                response = await client.post(url, **kwargs)
            else:
                response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return, unused-ignore]
        except httpx.HTTPStatusError as e:
            logger.error(f"API HTTP error {e.response.status_code}: {e.response.text}")
            raise OpenAlgoAPIError(
                status_code=e.response.status_code,
                message=e.response.text,
                details={"response": e.response.text},
            ) from e
        except ValueError as e:
            logger.error(f"JSON decode error: {e}")
            raise OpenAlgoError(f"JSON decode error: {e}") from e
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out: {e}")
            raise OpenAlgoError(f"Timeout error: {e}") from e
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            raise OpenAlgoError(f"Connection error: {e}") from e
        except OpenAlgoError:
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise OpenAlgoError(f"Request failed: {e}") from e

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        symbols_sorted = sorted(symbols)
        symbols_digest = hashlib.sha256(
            ",".join(symbols_sorted).encode("utf-8")
        ).hexdigest()
        cache_key = f"quotes:{symbols_digest}"
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
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        # Create cache key based on parameters
        cache_key_data = f"{symbol}:{interval}:{from_date}:{to_date}"
        cache_key = (
            f"history:{hashlib.sha256(cache_key_data.encode('utf-8')).hexdigest()}"
        )

        # Try to get cached result first
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug(f"History cache hit for {symbol} {interval}")
                return json.loads(cached_result)  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning(f"Failed to parse cached history result: {e}")

        # Cache miss - fetch from API
        payload = {
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
        }
        result = await self._request("POST", "history", json=payload)

        # Cache the result for 5 minutes (300 seconds)
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=300)
            logger.debug(f"Cached history for {symbol} {interval}")
        except Exception as e:
            logger.warning(f"Failed to cache history result: {e}")

        return result

    async def get_option_chain(
        self, symbol: str, expiry: str | None = None
    ) -> dict[str, Any]:
        # Create cache key based on parameters
        cache_key_data = f"{symbol}:{expiry}"
        cache_key = (
            f"option_chain:{hashlib.sha256(cache_key_data.encode('utf-8')).hexdigest()}"
        )

        # Try to get cached result first
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug(f"Option chain cache hit for {symbol}")
                return json.loads(cached_result)  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning(f"Failed to parse cached option chain result: {e}")

        # Cache miss - fetch from API
        payload = {"symbol": symbol, "expiry": expiry}
        result = await self._request("POST", "option_chain", json=payload)

        # Cache the result for 5 minutes (300 seconds)
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=300)
            logger.debug(f"Cached option chain for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to cache option chain result: {e}")

        return result

    async def get_position_book(self) -> dict[str, Any]:
        cache_key = "position_book:global"

        # Try to get cached result first
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug("Position book cache hit")
                return json.loads(cached_result)  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning(f"Failed to parse cached position book result: {e}")

        # Cache miss - fetch from API
        result = await self._request("POST", "position_book")

        # Cache the result for 30 seconds
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=30)
            logger.debug("Cached position book")
        except Exception as e:
            logger.warning(f"Failed to cache position book result: {e}")

        return result

    async def get_funds(self) -> dict[str, Any]:
        cache_key = "funds:global"

        # Try to get cached result first
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            try:
                logger.debug("Funds cache hit")
                return json.loads(cached_result)  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning(f"Failed to parse cached funds result: {e}")

        # Cache miss - fetch from API
        result = await self._request("POST", "funds")

        # Cache the result for 60 seconds
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=60)
            logger.debug("Cached funds")
        except Exception as e:
            logger.warning(f"Failed to cache funds result: {e}")

        return result

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
        Place an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate orders.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        await _async_check_kill_switch()
        # Use configured rate limits for order operations
        if not await get_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded order placement")
            raise RateLimitExceededError("Rate limit exceeded")

        # Wrap order placement in circuit breaker without retry
        async def _place_order_impl() -> dict[str, Any]:
            # Convert enum parameters to values
            order_type_val = (
                order_type.value if isinstance(order_type, OrderType) else order_type
            )
            variety_val = (
                variety.value if isinstance(variety, OrderVariety) else variety
            )
            transaction_type_val = (
                transaction_type.value
                if isinstance(transaction_type, TransactionType)
                else transaction_type
            )
            product_type_val = (
                product_type.value
                if isinstance(product_type, ProductType)
                else product_type
            )

            payload: dict[str, Any] = {
                "symbol": symbol,
                "quantity": quantity,
                "order_type": order_type_val,
                "variety": variety_val,
                "transaction_type": transaction_type_val,
                "product_type": product_type_val,
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

            return await self._request(
                "POST",
                "place_order",
                json=payload,
                idempotency_key=_get_idempotency_key(
                    f"place:{_order_payload_digest(payload)}"
                ),
            )

        return await OPENALGO_CIRCUIT_BREAKER.call_async(_place_order_impl)

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
        Place a smart order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate orders.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        await _async_check_kill_switch()
        # Use configured rate limits for smart order operations
        if not await get_smart_order_rate_limiter().acquire():
            logger.warning("Rate limit exceeded smart order placement")
            raise RateLimitExceededError("Rate limit exceeded")

        # Wrap smart order placement in circuit breaker without retry
        async def _place_smart_order_impl() -> dict[str, Any]:
            # Convert enum parameters to values
            order_type_val = (
                order_type.value if isinstance(order_type, OrderType) else order_type
            )
            transaction_type_val = (
                transaction_type.value
                if isinstance(transaction_type, TransactionType)
                else transaction_type
            )
            product_type_val = (
                product_type.value
                if isinstance(product_type, ProductType)
                else product_type
            )

            payload: dict[str, Any] = {
                "symbol": symbol,
                "quantity": quantity,
                "order_type": order_type_val,
                "strategy": strategy,
                "transaction_type": transaction_type_val,
                "product_type": product_type_val,
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

            return await self._request(
                "POST",
                "place_smart_order",
                json=payload,
                idempotency_key=_get_idempotency_key(
                    f"place_smart_order:{_order_payload_digest(payload)}"
                ),
            )

        return await OPENALGO_CIRCUIT_BREAKER.call_async(_place_smart_order_impl)

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
        Modify an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate modifications.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        await _async_check_kill_switch()

        # Wrap order modification in circuit breaker without retry
        async def _modify_order_impl() -> dict[str, Any]:
            # Convert enum parameter to value if needed
            order_type_val = (
                order_type.value if isinstance(order_type, OrderType) else order_type
            )

            payload: dict[str, Any] = {"order_id": order_id}
            if quantity is not None:
                payload["quantity"] = quantity
            if order_type is not None:
                payload["order_type"] = order_type_val
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

            return await self._request(
                "POST",
                "modify_order",
                json=payload,
                idempotency_key=_get_idempotency_key(f"modify:{order_id}"),
            )

        return await OPENALGO_CIRCUIT_BREAKER.call_async(_modify_order_impl)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an order with circuit breaker protection.

        Note: Circuit breaker is applied without retry to avoid duplicate cancellations.
        When the circuit is open, this method fails fast with CircuitBreakerOpenError.
        """
        await _async_check_kill_switch()

        # Wrap order cancellation in circuit breaker without retry
        async def _cancel_order_impl() -> dict[str, Any]:
            payload = {"order_id": order_id}
            return await self._request(
                "POST",
                "cancel_order",
                json=payload,
                idempotency_key=_get_idempotency_key(f"cancel:{order_id}"),
            )

        return await OPENALGO_CIRCUIT_BREAKER.call_async(_cancel_order_impl)

    async def place_analyzer_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Submit a TradeDecision payload to the Analyzer service for analysis.

        Routes the decision payload via OpenAlgo's ANALYZE mode endpoint.
        Returns the real response from the Analyzer service without fabrication.

        Args:
            payload: TradeDecision payload from decision.to_analyzer_payload()

        Returns:
            Real response from Analyzer service

        Raises:
            OpenAlgoError: If the Analyzer request fails (propagated, not fabricated)
            OpenAlgoAPIError: If the API returns an error status
            CircuitBreakerOpenError: If circuit breaker is open

        Note:
            - No asyncio.sleep simulation - real HTTP call
            - Errors propagate, no fabricated success responses
            - Uses circuit breaker pattern for resilience
        """

        # Analyzer requests don't require kill switch check (analysis-only, not trading)
        # Use circuit breaker with retry for analyzer requests
        # (idempotent GET-like behavior)
        async def _analyze_impl() -> dict[str, Any]:
            return await self._request("POST", "analyze", json=payload)

        return await OPENALGO_CIRCUIT_BREAKER.call_async(_analyze_impl)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        payload = {"order_id": order_id}
        return await self._request("POST", "order_status", json=payload)

    async def get_all_orders(self) -> dict[str, Any]:
        return await self._request("POST", "all_orders")

    async def get_trade_book(self) -> dict[str, Any]:
        return await self._request("POST", "trade_book")


async_client = AsyncOpenAlgoClient()
