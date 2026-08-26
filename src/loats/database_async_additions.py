"""
Async database operations for LOATS13July2026 using aiosqlite.
This module extends the Database class with true async I/O capabilities.
"""

import asyncio

# Check for aiosqlite availability without importing
import importlib.util
import json
from datetime import UTC, datetime
from typing import Any

from .database import Database
from .models import (
    AuditLogEntry,
    FundsData,
    HistoricalData,
    Position,
    QuoteData,
    Signal,
    Trade,
    TradeDecision,
)

AIOSQLITE_AVAILABLE = importlib.util.find_spec("aiosqlite") is not None


async def _async_create_signal(self: Database, signal: Signal) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(signal.timestamp.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO signals
                (signal_id, symbol, signal_type, strength, timestamp,
                 indicators, metadata, confidence, created_at, created_at_ms,
                 timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.symbol,
                    signal.signal_type.value,
                    signal.strength,
                    signal.timestamp.isoformat(),
                    json.dumps(signal.indicators),
                    json.dumps(signal.metadata) if signal.metadata else None,
                    signal.confidence,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)

    # Async audit logging
    await _async_log_audit(
        self,
        action="CREATE",
        entity_type="signal",
        entity_id=signal.signal_id,
        new_state=self._model_to_dict(signal),
    )
    return True


async def _async_store_historical_data(
    self: Database, data: list[HistoricalData]
) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            for item in data:
                ts_ms = int(item.timestamp.timestamp() * 1000)
                await cursor.execute(
                    """
                    INSERT OR REPLACE INTO historical_data
                    (symbol, timestamp, open, high, low, close, volume,
                     interval, created_at, created_at_ms, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.symbol,
                        item.timestamp.isoformat(),
                        item.open,
                        item.high,
                        item.low,
                        item.close,
                        item.volume,
                        item.interval,
                        now_iso,
                        now_ms,
                        ts_ms,
                    ),
                )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_quote(self: Database, quote: QuoteData) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(quote.timestamp.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT OR REPLACE INTO quotes
                (symbol, last_price, open, high, low, close, volume, timestamp,
                 change, change_percent, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote.symbol,
                    quote.last_price,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.close,
                    quote.volume,
                    quote.timestamp.isoformat(),
                    quote.change,
                    quote.change_percent,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_position(self: Database, position: Position) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    # Handle potential missing timestamp Pydantic model ensuring value
    ts = getattr(position, "timestamp", None) or now
    ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
    ts_ms = int(ts.timestamp() * 1000) if isinstance(ts, datetime) else now_ms

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT OR REPLACE INTO positions
                (symbol, quantity, average_price, last_price, pnl, product_type,
                 buy_quantity, sell_quantity, timestamp, created_at, created_at_ms,
                 timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.symbol,
                    position.quantity,
                    position.average_price,
                    position.last_price,
                    position.pnl,
                    position.product_type.value,
                    position.buy_quantity,
                    position.sell_quantity,
                    ts_str,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_funds(self: Database, funds: FundsData) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(funds.timestamp.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT OR REPLACE INTO funds
                (available_cash, utilized_margin, available_margin, total_equity,
                 timestamp, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    funds.available_cash,
                    funds.utilized_margin,
                    funds.available_margin,
                    funds.total_equity,
                    funds.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_get_latest_signals(
    self: Database, symbol: str, limit: int = 10, scan_type: str | None = None
) -> list[Signal]:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return []

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            if scan_type is not None:
                await cursor.execute(
                    """
                    SELECT * FROM signals
                    WHERE symbol = ? AND json_extract(metadata, '$.scan_type') = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (symbol, scan_type, limit),
                )
            else:
                await cursor.execute(
                    """
                    SELECT * FROM signals WHERE symbol = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (symbol, limit),
                )
            rows = await cursor.fetchall()
    finally:
        await self._async_pool.release(conn)
    return [self._row_to_signal(row) for row in rows]


async def _async_update_trade(self: Database, trade: Trade) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    # Get previous state audit
    previous = await async_get_trade(self, trade.trade_id)
    previous_state = self._model_to_dict(previous) if previous else None

    entry_time_ms = (
        int(trade.entry_time.timestamp() * 1000)
        if isinstance(trade.entry_time, datetime)
        else 0
    )
    exit_time_ms = (
        int(trade.exit_time.timestamp() * 1000)
        if isinstance(trade.exit_time, datetime)
        else None
    )

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE trades SET
                    symbol = ?, quantity = ?, entry_price = ?, exit_price = ?,
                    entry_time = ?, exit_time = ?, transaction_type = ?,
                    product_type = ?, pnl = ?, status = ?, strategy = ?,
                    stop_loss = ?, take_profit = ?, trailing_stop_loss = ?,
                    metadata = ?, updated_at = ?, updated_at_ms = ?,
                    entry_time_ms = ?, exit_time_ms = ?
                WHERE trade_id = ?
                """,
                (
                    trade.symbol,
                    trade.quantity,
                    trade.entry_price,
                    trade.exit_price,
                    (
                        trade.entry_time.isoformat()
                        if isinstance(trade.entry_time, datetime)
                        else str(trade.entry_time)
                    ),
                    (
                        trade.exit_time.isoformat()
                        if isinstance(trade.exit_time, datetime)
                        else trade.exit_time
                    ),
                    trade.transaction_type.value if trade.transaction_type else None,
                    trade.product_type.value if trade.product_type else None,
                    trade.pnl,
                    trade.status,
                    trade.strategy,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.trailing_stop_loss,
                    json.dumps(trade.metadata) if trade.metadata else None,
                    now_iso,
                    now_ms,
                    entry_time_ms,
                    exit_time_ms,
                    trade.trade_id,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)

    # Async audit logging
    await _async_log_audit(
        self,
        action="UPDATE",
        entity_type="trade",
        entity_id=trade.trade_id,
        previous_state=previous_state,
        new_state=self._model_to_dict(trade),
    )
    return True


async def _async_update_order_status(
    self: Database, order_id: str, status: str
) -> bool:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return False

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            # Check if order exists first
            await cursor.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
            row = await cursor.fetchone()
            exists = row is not None

            if not exists:
                await conn.commit()  # Commit before returning
                return False

            # Update the order
            await cursor.execute(
                "UPDATE orders SET status = ?, updated_at = ?, "
                "updated_at_ms = ? WHERE order_id = ?",
                (status, now_iso, now_ms, order_id),
            )
        await conn.commit()
        return True
    finally:
        await self._async_pool.release(conn)


async def async_get_trade(self: Database, trade_id: str) -> Trade | None:
    """Async get trade by ID."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        conn = await self._async_pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_trade(row)
        finally:
            await self._async_pool.release(conn)
    else:
        # Fallback to sync method
        return self.get_trade(trade_id)


async def _async_log_audit(
    self: Database,
    action: str,
    entity_type: str,
    entity_id: str,
    user: str = "system",
    metadata: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
) -> None:
    """Async audit logging using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return

    now = datetime.now(UTC)
    entry = AuditLogEntry(
        timestamp=now,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user=user,
        metadata=metadata or {},
        previous_state=previous_state or {},
        new_state=new_state or {},
    )

    # Calculate hash over entry data WITHOUT sha256_hash field
    hash_data = self._model_to_dict(entry)
    # Remove sha256_hash (which is currently None) hashing
    hash_data.pop("sha256_hash", None)
    entry.sha256_hash = self._calculate_sha256(hash_data)

    # Re-serialize fully populated model (including hash)
    entry_data = self._model_to_dict(entry)

    # Write JSONL file first (append-only) using canonical serialization
    try:
        with self.audit_log_path.open("a", encoding="utf-8") as f:
            f.write(self._canonical_serialize(entry_data) + "\n")
    except OSError as e:
        raise RuntimeError(
            f"Failed to write audit log entry to JSONL file: {e}. "
            "Database commit aborted to maintain consistency."
        ) from e

    # Write to async database
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO audit_log
                (entry_id, timestamp, action, entity_type, entity_id, user,
                 metadata, previous_state, new_state, sha256_hash, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.timestamp.isoformat(),
                    entry.action,
                    entry.entity_type,
                    entry.entity_id,
                    entry.user,
                    json.dumps(entry.metadata),
                    json.dumps(entry.previous_state) if entry.previous_state else None,
                    json.dumps(entry.new_state) if entry.new_state else None,
                    entry.sha256_hash,
                    int(now.timestamp() * 1000),
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)


# Helper wrapper functions for async operations
async def _async_create_signal_wrapper(self: Database, signal: Signal) -> bool:
    """Async wrapper create_signal() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_create_signal(signal)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.create_signal, signal)


async def _async_store_historical_data_wrapper(
    self: Database, data: list[HistoricalData]
) -> bool:
    """Async wrapper store_historical_data() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_store_historical_data(data)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.store_historical_data, data)


async def _async_store_quote_wrapper(self: Database, quote: QuoteData) -> bool:
    """Async wrapper store_quote() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_store_quote(quote)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.store_quote, quote)


async def _async_store_position_wrapper(self: Database, position: Position) -> bool:
    """Async wrapper store_position() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_store_position(position)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.store_position, position)


async def _async_store_funds_wrapper(self: Database, funds: FundsData) -> bool:
    """Async wrapper store_funds() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_store_funds(funds)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.store_funds, funds)


async def _async_get_latest_signals_wrapper(
    self: Database, symbol: str, limit: int = 10, scan_type: str | None = None
) -> list[Signal]:
    """Async wrapper get_latest_signals() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_get_latest_signals(symbol, limit, scan_type)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(
            self.get_latest_signals, symbol, limit, scan_type
        )


async def _async_update_trade_wrapper(self: Database, trade: Trade) -> bool:
    """Async wrapper update_trade() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_update_trade(trade)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.update_trade, trade)


async def _async_update_order_status_wrapper(
    self: Database, order_id: str, status: str
) -> bool:
    """Async wrapper update_order_status() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        return await self._async_update_order_status(order_id, status)  # type: ignore[attr-defined, no-any-return]
    else:
        return await asyncio.to_thread(self.update_order_status, order_id, status)


async def _async_record_trade_decision(
    self: Database, decision: TradeDecision, response: dict[str, Any]
) -> None:
    """
    Record TradeDecision routing outcome to audit trail with dual-write consistency.

    Implements atomic dual-write: JSONL file + SQLite database.
    Persists both the TradeDecision and the Analyzer response for audit-grade
    traceability that survives restarts.

    Args:
        decision: TradeDecision that was routed
        response: Response from Analyzer routing (or disabled status)

    Dual-Write Guarantee:
    - JSONL write occurs first
    - Database commit only after successful JSONL write
    - Ensures audit trail integrity across restarts
    """
    decision_dict = decision.model_dump()
    await self._async_log_audit(
        action="ROUTE_TO_ANALYZER",
        entity_type="trade_decision",
        entity_id=decision.decision_id,
        user="system",
        metadata={
            "routing_response": response,
            "routing_timestamp": datetime.now(UTC).isoformat(),
        },
        previous_state=None,
        new_state=decision_dict,
    )


async def _async_record_trade_decision_wrapper(
    self: Database, decision: TradeDecision, response: dict[str, Any]
) -> None:
    """Async wrapper record_trade_decision() avoid blocking event loop."""
    if AIOSQLITE_AVAILABLE and hasattr(self, "_async_pool") and self._async_pool:
        await self._async_record_trade_decision(decision, response)  # type: ignore[attr-defined]
    else:
        # Fallback to synchronous audit logging
        from .database import db

        decision_dict = decision.model_dump()
        db._log_audit(
            action="ROUTE_TO_ANALYZER",
            entity_type="trade_decision",
            entity_id=decision.decision_id,
            user="system",
            metadata={
                "routing_response": response,
                "routing_timestamp": datetime.now(UTC).isoformat(),
            },
            previous_state=None,
            new_state=decision_dict,
        )


# Add async methods to Database class if they don't exist
def extend_database_class() -> None:
    """Extend the Database class with async methods."""
    from .database import Database

    # Add core async methods
    if not hasattr(Database, "_async_create_signal"):
        Database._async_create_signal = _async_create_signal  # type: ignore[attr-defined]
        Database._async_store_historical_data = _async_store_historical_data  # type: ignore[attr-defined]
        Database._async_store_quote = _async_store_quote  # type: ignore[attr-defined]
        Database._async_store_position = _async_store_position  # type: ignore[attr-defined]
        Database._async_store_funds = _async_store_funds  # type: ignore[attr-defined]
        Database._async_get_latest_signals = _async_get_latest_signals  # type: ignore[attr-defined]
        Database._async_update_trade = _async_update_trade  # type: ignore[attr-defined]
        Database._async_update_order_status = _async_update_order_status  # type: ignore[attr-defined]
        Database._async_record_trade_decision = _async_record_trade_decision  # type: ignore[attr-defined]
        Database.async_get_trade = async_get_trade  # type: ignore[attr-defined]
        Database._async_log_audit = _async_log_audit  # type: ignore[attr-defined]

    # Add optimized wrapper methods
    _add_wrapper_method(Database, "async_create_signal", _async_create_signal_wrapper)
    _add_wrapper_method(
        Database, "async_store_historical_data", _async_store_historical_data_wrapper
    )
    _add_wrapper_method(Database, "async_store_quote", _async_store_quote_wrapper)
    _add_wrapper_method(Database, "async_store_position", _async_store_position_wrapper)
    _add_wrapper_method(Database, "async_store_funds", _async_store_funds_wrapper)
    _add_wrapper_method(
        Database, "async_get_latest_signals", _async_get_latest_signals_wrapper
    )
    _add_wrapper_method(Database, "async_update_trade", _async_update_trade_wrapper)
    _add_wrapper_method(
        Database, "async_update_order_status", _async_update_order_status_wrapper
    )
    _add_wrapper_method(
        Database, "async_record_trade_decision", _async_record_trade_decision_wrapper
    )


def _add_wrapper_method(cls: type[Database], name: str, method: Any) -> None:
    """Add a wrapper method to the Database class if it doesn't exist."""
    if not hasattr(cls, name):
        setattr(cls, name, method)
        method_obj = getattr(cls, name)
        if hasattr(method_obj, "_is_optimized"):
            method_obj._is_optimized = True
        else:
            # Add the attribute dynamically - MyPy can't track this
            object.__setattr__(method_obj, "_is_optimized", True)


# Initialize the extension
extend_database_class()
