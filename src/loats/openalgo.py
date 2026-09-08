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

import asyncio
import hashlib
import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
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
from .utils.lazy_singleton import lazy_singleton
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


#: Exchange segment holding index symbols on NSE. Indices are NOT quotable on
#: the cash segment: the live deployment rejects ``{"exchange": "NSE",
#: "symbol": "NIFTY"}`` with HTTP 400 "Symbol 'NIFTY' not found for exchange
#: 'NSE'" while ``NSE_INDEX`` resolves every NSE index symbol (verified live
#: 08Sep2026: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50, INDIAVIX).
_INDEX_EXCHANGES = frozenset(
    {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "INDIAVIX"}
)


def _quote_request_shape(symbol: str) -> dict[str, str]:
    """Route a symbol to the exchange segment the deployment can quote.

    Index symbols must go to ``NSE_INDEX``; everything else stays on the
    cash segment. Verified live 08Sep2026 against the running OpenAlgo
    deployment (RELIANCE -> 200 on NSE, NIFTY -> 200 on NSE_INDEX / 400
    on NSE).
    """
    exchange = "NSE_INDEX" if symbol.strip().upper() in _INDEX_EXCHANGES else "NSE"
    return {"exchange": exchange, "symbol": symbol}


def _normalize_interval(interval: str) -> str:
    """Map repo interval spellings onto the deployment's vocabulary.

    The live /history endpoint validates against {1s, 5s, 10s, 15s, 30s,
    45s, 1m, 2m, 3m, 5m, 10m, 15m, 20m, 30m, 1h, 2h, 3h, 4h, D, W, M, Q,
    Y} (verified 08Sep2026 -- ``5min``/``5minute``/``1min`` are rejected
    with HTTP 400). LOATS settings and call sites use ``<N>min`` (and
    ``<N>minute`` appears in the wild); both map to ``Nm``. Already-valid
    values (``5m``, ``1h``, ``D``) pass through untouched.
    """
    text = interval.strip()
    for suffix in ("minute", "min"):
        if text.endswith(suffix) and text[: -len(suffix)].isdigit():
            return f"{text[: -len(suffix)]}m"
    return interval


#: Exchange-local timezone for default history windows. LOATS trades the
#: NSE calendar (IST, UTC+05:30); defaulting the window in UTC made
#: ``end_date`` roll to tomorrow's calendar date after 18:30 IST.
_IST = timezone(timedelta(hours=5, minutes=30))

#: Memoized listed-expiry resolutions (the /expiry listing moves at most
#: once a day; the producer cadence is ~100ms).
_EXPIRY_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_EXPIRY_CACHE_LOCK = threading.Lock()
_EXPIRY_TTL = 600.0


def _normalize_flat_quotes(
    symbols: list[str], fetch: Callable[[str], dict[str, Any]]
) -> dict[str, Any]:
    """Fan out per-symbol quote requests and reshape into canonical form.

    Two live deployment behaviors are normalized here (both verified
    08Sep2026):
    - each per-symbol /quotes response returns ``data`` as ONE flat quote
      dict ({ltp, prev_close, ...}) with NO symbol key, while every LOATS
      caller parses ``quotes["data"][symbol]`` -- the flat dict is keyed
      back under the requested symbol;
    - the deployment speaks broker vocabulary (``ltp`` / ``prev_close``)
      while callers read canonical QuoteData names (``last_price`` /
      ``close``) -- canonical aliases are added on a COPY of each quote
      dict (the response object is never mutated: it can be cached and
      re-read) and only when the broker field is PRESENT, so a missing
      ``ltp``/``prev_close`` stays missing -- callers' explicit
      ``get(..., None)`` handling (e.g. the VIX gate) keeps working and
      no fabricated 0.0 price can be injected.

      A per-symbol fetch failure is isolated: the remaining symbols still
      populate the result, and the exception is re-raised only when EVERY
      requested symbol failed (a total outage must reach the circuit
      breaker; one bad symbol must not starve the others' consumers).
    """
    data: dict[str, Any] = {}
    errors: list[tuple[str, Exception]] = []
    for symbol in symbols:
        try:
            result = fetch(symbol)
        except Exception as exc:
            errors.append((symbol, exc))
            continue
        raw = result.get("data") or {}
        if (
            isinstance(raw, dict)
            and raw
            and all(not isinstance(value, dict) for value in raw.values())
        ):
            # Flat single-quote response: key it under the requested symbol.
            # (Discriminated by value type -- a symbol-keyed batch response
            # carries dict values, a flat quote only scalars.)
            raw = {symbol: raw}
        if not isinstance(raw, dict):
            raw = {}
        normalized: dict[str, Any] = {}
        for key, quote in raw.items():
            if isinstance(quote, dict):
                quote = dict(quote)
                if "ltp" in quote:
                    quote.setdefault("last_price", quote["ltp"])
                if "prev_close" in quote:
                    quote.setdefault("close", quote["prev_close"])
            normalized[key] = quote
        data.update(normalized)
    if errors and len(errors) == len(symbols):
        raise errors[0][1]
    for symbol, err in errors:
        logger.warning("Quote fetch failed for %s (isolated): %s", symbol, err)
    return {"status": "success", "data": data}


def _option_chain_expiry_date(days_ahead: int = 7) -> str:
    """Fallback expiry hint in the deployment's compact ``DDMMMYY`` format.

    The live /optionchain schema is {underlying, expiry_date, exchange}
    (verified 08Sep2026: ``symbol``/``expiry`` fields are rejected as
    unknown), and the strike lookup slices ``expiry_date[:2]-[2:5]-[5:]``
    positionally, so only compact 7-char DDMMMYY strings like ``08SEP26``
    reach the database. The hint is a FLOOR only --
    ``_resolve_expiry_date`` resolves the nearest LISTED expiry through
    the /expiry endpoint first; this computed guess is used solely when
    that resolution fails.
    """
    return (datetime.now(UTC) + timedelta(days=days_ahead)).strftime("%d%b%y").upper()


def _parse_expiry_dates(items: list[Any]) -> list[tuple[date, str]]:
    """Parse broker expiry strings ({DD-MMM-YY, DDMMMYY, ISO} observed)
    into (date, original) pairs, dropping unparseable entries."""
    parsed: list[tuple[date, str]] = []
    for item in items:
        text = str(item).strip().upper().replace(" ", "")
        candidate: date | None = None
        for fmt in ("%d-%b-%y", "%d%b%y", "%Y-%m-%d"):
            try:
                candidate = datetime.strptime(text, fmt).replace(tzinfo=_IST).date()
                break
            except ValueError:
                continue
        if candidate is not None:
            parsed.append((candidate, str(item)))
    return parsed


def _compact_expiry(expiry: str) -> str:
    """Normalize a broker expiry string to compact ``DDMMMYY``."""
    text = expiry.strip().upper().replace(" ", "")
    if re.fullmatch(r"\d{2}[A-Z]{3}\d{2}", text):
        return text
    for fmt in ("%d-%b-%y", "%Y-%m-%d"):
        try:
            return (
                datetime.strptime(text, fmt)
                .replace(tzinfo=_IST)
                .strftime("%d%b%y")
                .upper()
            )
        except ValueError:
            continue
    return expiry


def _choose_listed_expiry(items: Any, days_ahead: int = 7) -> str:
    """Pick the nearest listed expiry at/after today (IST) from a broker
    expiry listing; compact computed hint as the no-listing fallback."""
    parsed = _parse_expiry_dates(items) if isinstance(items, list) else []
    today = datetime.now(_IST).date()
    candidates = [(d, raw) for d, raw in parsed if d >= today]
    if candidates:
        return _compact_expiry(min(candidates, key=lambda pair: pair[0])[1])
    return _option_chain_expiry_date(days_ahead)


def _resolve_expiry_date(
    underlying: str,
    exchange: str,
    request: Callable[[dict[str, Any]], dict[str, Any]],
    days_ahead: int = 7,
) -> str:
    """Nearest LISTED expiry for the underlying, hint-clamped (sync path).

    Probes the deployment's /expiry endpoint
    ({exchange, symbol, instrumenttype: 'options'} -- verified 08Sep2026:
    lists the underlying's real expiries, e.g. NIFTY ->
    ['08-SEP-26', '15-SEP-26', ...]) and picks the front listing, so an
    expiry hint landing between listed dates never 404s the chain. The
    listing is the source of truth for expiry format, so a broker-side
    format change surfaces here rather than as empty chains.

    The resolution is memoized per (underlying, exchange) for
    ``_EXPIRY_TTL`` seconds: the listing moves at most once a day, while
    the producer cadence is ~100ms -- memoization removes one broker
    round-trip per chain call; a fresh call right after the roll finds
    the new listing within the TTL anyway (chain cache and expiry cache
    then agree).
    """
    now = time.monotonic()
    cache_key = (underlying.upper(), exchange.upper())
    with _EXPIRY_CACHE_LOCK:
        cached = _EXPIRY_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _EXPIRY_TTL:
            return cached[1]
    try:
        listing = request(
            {
                "exchange": exchange,
                "symbol": underlying,
                "instrumenttype": "options",
            }
        )
        items = listing.get("data")
    except Exception:
        items = None
    resolved = _choose_listed_expiry(items, days_ahead)
    if items is not None:
        # Only successful listings are cached: a failed lookup retries on
        # the next call instead of pinning the computed hint for the TTL.
        with _EXPIRY_CACHE_LOCK:
            _EXPIRY_CACHE[cache_key] = (now, resolved)
    return resolved


def _normalize_option_chain(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten the deployment's nested chain rows into contract rows.

    The live response carries ``chain: [{strike, ce: {...}, pe: {...}}]``
    (verified 08Sep2026). ``Orchestrator._extract_chain_rows`` and
    ``_chain_int``/``_chain_float`` parse FLAT rows with ``option_type``
    CE/PE, so each leg is flattened (strike + option_type merged in).
    Payloads without a recognizable chain list -- or with no flattenable
    entries -- pass through UNCHANGED, so provider-dependent shapes keep
    reaching the tolerant extractor and an existing ``data`` payload is
    never overwritten with an empty list.
    """
    chain = result.get("chain")
    if not isinstance(chain, list):
        data = result.get("data")
        chain = data.get("chain") if isinstance(data, dict) else None
        if not isinstance(chain, list):
            return result
    rows: list[dict[str, Any]] = []
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        strike = entry.get("strike")
        for opt_type, leg_key in (("CE", "ce"), ("PE", "pe")):
            leg = entry.get(leg_key)
            if isinstance(leg, dict):
                row = dict(leg)
                row["strike"] = strike
                row["option_type"] = opt_type
                if "expiry" in entry:
                    row["expiry"] = entry["expiry"]
                rows.append(row)
    if not rows:
        # Nothing flattenable -- never replace an existing data payload
        # with []: the producer must see the payload as delivered.
        return result
    return {**result, "data": rows}


def _normalize_history_rows(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize history rows into the shape every consumer parses.

    The live deployment returns ``timestamp`` as INTEGER EPOCH SECONDS
    (verified 08Sep2026: row = {open, high, low, close, volume, oi,
    timestamp: 1788752700}), while the orchestrator's history consumers
    parse ``datetime.fromisoformat(item["timestamp"])`` -- an int crashes
    all three chart producers ("fromisoformat: argument must be str").
    Epoch values are converted to timezone-aware UTC ISO-8601 strings;
    string timestamps pass through untouched (a ISO-speaking deployment
    must not be double-normalized). Rows lacking a timestamp, or a
    non-list ``data`` payload, pass through unchanged.
    """
    rows = result.get("data")
    if not isinstance(rows, list):
        return result
    normalized = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts = row.get("timestamp")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            row["timestamp"] = datetime.fromtimestamp(ts, tz=UTC).isoformat()
            normalized = True
    if not normalized:
        return result
    return {**result, "data": rows}


def _history_payload(
    symbol: str, interval: str, from_date: str | None, to_date: str | None
) -> dict[str, Any]:
    """Build a /history body that satisfies the live deployment schema.

    Verified 08Sep2026: ``exchange`` is a REQUIRED field (its absence
    yields 400 "Missing data for required field" -- the previous client
    never sent it, so every history call failed), dates are
    ``start_date``/``end_date`` (the repo's ``from_date``/``to_date``
    names are rejected) and both are required; omitted dates default to a
    5-day window ending today ON THE EXCHANGE CALENDAR (IST): defaulting
    in UTC rolled ``end_date`` to tomorrow's date after 18:30 IST. Index
    symbols route via ``_quote_request_shape`` (a NIFTY index history on
    ``NSE`` 400s).
    """
    now_ist = datetime.now(_IST)
    end = to_date or now_ist.strftime("%Y-%m-%d")
    start = from_date or (now_ist - timedelta(days=5)).strftime("%Y-%m-%d")
    return {
        **_quote_request_shape(symbol),
        "interval": _normalize_interval(interval),
        "start_date": start,
        "end_date": end,
    }


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
        if method.upper() == "POST":
            # OpenAlgo deployments validate `apikey` as a REQUIRED JSON body
            # field (F8-L-03 live verification: header-only auth fails schema
            # on every endpoint with 400 "Missing data for required field").
            # Inject it into the JSON body so the client works against both
            # body-auth (current deployments) and header-auth deployments.
            json_body = dict(kwargs.pop("json", None) or {})
            json_body.setdefault("apikey", self.api_key)
            kwargs["json"] = json_body
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
        # Deployment contract (verified live, F8-L-03): POST /quotes accepts a
        # SINGLE {apikey, exchange, symbol} body -- batch quotes belong to
        # /multiquotes. Fan out sequentially and reshape into the canonical
        # {"data": {symbol: {...}}} form every caller parses.
        return _normalize_flat_quotes(symbols, self._request_quotes_single)

    def _request_quotes_single(self, symbol: str) -> dict[str, Any]:
        return self._request("POST", "quotes", json=_quote_request_shape(symbol))

    def get_history(
        self,
        symbol: str,
        interval: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        payload = _history_payload(symbol, interval, from_date, to_date)
        result = self._request("POST", "history", json=payload)
        return _normalize_history_rows(result)

    def get_option_chain(
        self, symbol: str, expiry: str | None = None
    ) -> dict[str, Any]:
        # Note: caching is intentionally omitted here; the shared cache_manager is
        # async-only and cannot be awaited from this synchronous client. Use
        # AsyncOpenAlgoClient.get_option_chain for cached access.
        payload = {
            "underlying": symbol,
            "expiry_date": (
                _compact_expiry(expiry)
                if expiry
                else _resolve_expiry_date(symbol, "NFO", self._expiry_listing)
            ),
            "exchange": "NFO",
        }
        result = self._request("POST", "optionchain", json=payload)
        return _normalize_option_chain(result)

    def _expiry_listing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "expiry", json=payload)

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

        CMP Rule 7 (F8-H-02): a persisted, per-order modification budget
        (settings.max_modifications, default 25) is enforced HERE, at the
        API boundary, so every caller is gated -- not just the trailing
        driver. The slot is reserved before the broker call and released
        if the broker request fails, so failed attempts never consume
        budget. Counter state is read from SQLite (survives restarts); a
        counter DB failure fails closed (modification refused).
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

        # CMP Rule 7: reserve budget before touching the broker. Raises
        # Rule7ModificationLimitError (refuse) or Rule7StateError (fail closed).
        from .rules import rules_engine

        rules_engine.reserve_modification(order_id)

        # Wrap order modification in circuit breaker without retry
        def _modify_order_impl() -> dict[str, Any]:
            return self._request(
                "POST",
                "modify_order",
                json=payload,
                idempotency_key=_get_idempotency_key(f"modify:{order_id}"),
            )

        try:
            return OPENALGO_CIRCUIT_BREAKER.call(_modify_order_impl)
        except Exception:
            # Broker/circuit failure: give the reserved slot back so the
            # failed attempt does not consume Rule-7 budget.
            rules_engine.release_modification(order_id)
            raise

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
        if method.upper() == "POST":
            # OpenAlgo deployments validate `apikey` as a REQUIRED JSON body
            # field (F8-L-03 live verification: header-only auth fails schema
            # on every endpoint with 400 "Missing data for required field").
            # Inject it into the JSON body so the client works against both
            # body-auth (current deployments) and header-auth deployments.
            json_body = dict(kwargs.pop("json", None) or {})
            json_body.setdefault("apikey", self.api_key)
            kwargs["json"] = json_body
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
        # Deployment contract (verified live, F8-L-03): POST /quotes accepts a
        # SINGLE {apikey, exchange, symbol} body -- batch quotes belong to
        # /multiquotes. Fan out per symbol and reshape into the canonical
        # {"data": {symbol: {...}}} form every caller parses. The synthesized
        # result is cached under the pre-existing digest key (60s TTL).
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

        data: dict[str, Any] = {}
        result: dict[str, Any] = {}
        errors: list[tuple[str, Exception]] = []
        for symbol in symbols_sorted:
            try:
                result = await self._request(
                    "POST", "quotes", json=_quote_request_shape(symbol)
                )
            except Exception as exc:
                errors.append((symbol, exc))
                continue
            raw = result.get("data") or {}
            if (
                isinstance(raw, dict)
                and raw
                and all(not isinstance(value, dict) for value in raw.values())
            ):
                # Flat single-quote response: key it under the requested
                # symbol (value-type discrimination -- a symbol-keyed batch
                # response carries dict values, a flat quote only scalars).
                raw = {symbol: raw}
            if not isinstance(raw, dict):
                raw = {}
            normalized: dict[str, Any] = {}
            for key, quote in raw.items():
                if isinstance(quote, dict):
                    quote = dict(quote)
                    if "ltp" in quote:
                        quote.setdefault("last_price", quote["ltp"])
                    if "prev_close" in quote:
                        quote.setdefault("close", quote["prev_close"])
                normalized[key] = quote
            data.update(normalized)
        if errors and len(errors) == len(symbols):
            raise errors[0][1]
        for symbol, err in errors:
            logger.warning("Quote fetch failed for %s (isolated): %s", symbol, err)
        merged = {**result, "data": data}

        try:
            await cache_manager.set(cache_key, json.dumps(merged), ttl=60)
            logger.debug(f"Cached quotes {symbols}")
        except Exception as e:
            logger.warning(f"Failed cache quotes: {e}")
        return merged

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
        payload = _history_payload(symbol, interval, from_date, to_date)
        result = await self._request("POST", "history", json=payload)
        result = _normalize_history_rows(result)

        # Cache the result for 5 minutes (300 seconds)
        try:
            await cache_manager.set(cache_key, json.dumps(result), ttl=300)
            logger.debug(f"Cached history for {symbol} {interval}")
        except Exception as e:
            logger.warning(f"Failed to cache history result: {e}")

        return result

    async def _resolve_expiry_date_async(self, underlying: str, exchange: str) -> str:
        """Listed-expiry resolution for the async client (mirrors
        ``_resolve_expiry_date``, sharing its memo cache): the /expiry
        listing is the format and roll date source of truth; falls back
        to the computed hint. Failed lookups stay uncached and retry."""
        cache_key = (underlying.upper(), exchange.upper())
        now = time.monotonic()
        with _EXPIRY_CACHE_LOCK:
            cached = _EXPIRY_CACHE.get(cache_key)
            if cached is not None and now - cached[0] < _EXPIRY_TTL:
                return cached[1]
        try:
            listing = await self._request(
                "POST",
                "expiry",
                json={
                    "exchange": exchange,
                    "symbol": underlying,
                    "instrumenttype": "options",
                },
            )
            items = listing.get("data")
        except Exception:
            items = None
        resolved = _choose_listed_expiry(items)
        if items is not None:
            with _EXPIRY_CACHE_LOCK:
                _EXPIRY_CACHE[cache_key] = (now, resolved)
        return resolved

    async def get_option_chain(
        self, symbol: str, expiry: str | None = None
    ) -> dict[str, Any]:
        # Create cache key based on parameters. The RESOLVED expiry (not the
        # caller's None) is baked into the key so a 5-minute cached chain can
        # never survive the expiry rollover: when /expiry flips to the next
        # listing, the key changes and the stale chain cannot be served.
        resolved_expiry = (
            _compact_expiry(expiry)
            if expiry
            else await self._resolve_expiry_date_async(symbol, "NFO")
        )
        cache_key_data = f"{symbol}:{resolved_expiry}"
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
        payload = {
            "underlying": symbol,
            "expiry_date": resolved_expiry,
            "exchange": "NFO",
        }
        result = await self._request("POST", "optionchain", json=payload)
        result = _normalize_option_chain(result)

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

        # CMP Rule 7 (F8-H-02): reserve budget before touching the broker.
        # Raises Rule7ModificationLimitError (refuse) or Rule7StateError
        # (fail closed) -- identical semantics to the sync client.
        from .rules import rules_engine

        rules_engine.reserve_modification(order_id)

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

        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(_modify_order_impl)
        except Exception:
            # Broker/circuit failure: give the reserved slot back so the
            # failed attempt does not consume Rule-7 budget.
            await asyncio.to_thread(rules_engine.release_modification, order_id)
            raise

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


# F8-C-03 (2026-09-02): ``AsyncOpenAlgoClient.__init__`` reads ``Settings()``
# (fail-closed: a real client must have an API key), so the previous eager
# ``async_client = AsyncOpenAlgoClient()`` crashed ``import loats.*`` on any
# fresh checkout without OPENALGO_API_KEY. The LazyProxy defers construction
# to first attribute access; ``patch("loats.openalgo.async_client.<attr>")``
# keeps working (patched attributes land in the proxy __dict__).
async_client: AsyncOpenAlgoClient = lazy_singleton(AsyncOpenAlgoClient)
