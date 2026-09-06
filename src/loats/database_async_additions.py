"""Async additions for the Database class.

This module extends the Database class with additional async core methods.
Where true async aiosqlite variants are missing, methods delegate to the
Database class's existing sync methods via ``asyncio.to_thread`` so that
behavior exactly matches the canonical implementation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import Database

# SQLite (even in WAL mode) serialises writers across connections.  Use a
# module-level write lock so that all aiosqlite-backed writes are serialised
# without contending for the database lock.  Reads remain unblocked.
_async_write_lock = asyncio.Lock()

try:
    import aiosqlite  # noqa: F401 - availability probe, flag used below

    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

from .models import (  # noqa: E402 - imports after availability probe and lock creation
    FundsData,
    HistoricalData,
    Position,
    QuoteData,
    Signal,
    Trade,
    TradeDecision,
)


def _get_pool(self: Database) -> Any | None:
    """Return the async connection pool when it is available."""
    pool: Any = getattr(self, "_async_pool", None)
    if pool is None or not AIOSQLITE_AVAILABLE:
        return None
    return pool


async def _async_create_signal(self: Database, signal: Signal) -> bool:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_create_signal(signal)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(signal.timestamp.timestamp() * 1000)

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR REPLACE INTO signals
                    (signal_id, symbol, signal_type, strength, timestamp, indicators,
                     confidence, metadata, created_at, created_at_ms, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        signal.signal_id,
                        signal.symbol,
                        signal.signal_type.value,
                        float(signal.strength),
                        signal.timestamp.isoformat(),
                        json.dumps(signal.indicators),
                        float(signal.confidence)
                        if signal.confidence is not None
                        else 0.0,
                        json.dumps(signal.metadata),
                        now_iso,
                        now_ms,
                        ts_ms,
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_store_historical_data(
    self: Database, data: list[HistoricalData]
) -> bool:
    """True async implementation using aiosqlite for bulk insert."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_store_historical_data(data)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    records = []
    for item in data:
        ts_ms = int(item.timestamp.timestamp() * 1000)
        records.append(
            (
                item.symbol,
                item.timestamp.isoformat(),
                float(item.open),
                float(item.high),
                float(item.low),
                float(item.close),
                int(item.volume),
                item.interval,
                now_iso,
                now_ms,
                ts_ms,
            )
        )

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.executemany(
                    """INSERT OR REPLACE INTO historical_data
                    (symbol, timestamp, open, high, low, close, volume, interval,
                     created_at, created_at_ms, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    records,
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_store_quote(self: Database, quote: QuoteData) -> bool:
    """Async storage for quote data."""
    return await asyncio.to_thread(self.store_quote, quote)


async def _async_store_position(self: Database, position: Position) -> bool:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_store_position(position)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(position.timestamp.timestamp() * 1000)

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR REPLACE INTO positions
                    (symbol, quantity, average_price, last_price, pnl, product_type,
                     buy_quantity, sell_quantity, timestamp, created_at,
                     created_at_ms, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        position.symbol,
                        int(position.quantity),
                        float(position.average_price),
                        float(position.last_price),
                        float(position.pnl),
                        (
                            position.product_type.value
                            if hasattr(position.product_type, "value")
                            else str(position.product_type)
                        ),
                        int(position.buy_quantity),
                        int(position.sell_quantity),
                        position.timestamp.isoformat(),
                        now_iso,
                        now_ms,
                        ts_ms,
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_store_funds(self: Database, funds: FundsData) -> bool:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_store_funds(funds)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(funds.timestamp.timestamp() * 1000)

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR REPLACE INTO funds
                    (available_cash, utilized_margin, available_margin,
                     total_equity, timestamp, created_at, created_at_ms,
                     timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        float(funds.available_cash),
                        float(funds.utilized_margin),
                        float(funds.available_margin),
                        float(funds.total_equity),
                        funds.timestamp.isoformat(),
                        now_iso,
                        now_ms,
                        ts_ms,
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_get_latest_signals(
    self: Database,
    symbol: str,
    limit: int = 10,
    scan_type: str | None = None,
) -> list[Signal]:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_get_latest_signals(symbol, limit, scan_type)

    conn = await pool.acquire()
    try:
        async with conn.cursor() as cursor:
            if scan_type is not None:
                await cursor.execute(
                    """SELECT symbol, signal_type, strength, timestamp, indicators,
                              confidence, metadata, timestamp_ms
                       FROM signals
                       WHERE symbol = ? AND json_extract(metadata, '$.scan_type') = ?
                       ORDER BY timestamp_ms DESC
                       LIMIT ?""",
                    (symbol, scan_type, limit),
                )
            else:
                await cursor.execute(
                    """SELECT symbol, signal_type, strength, timestamp, indicators,
                              confidence, metadata, timestamp_ms
                       FROM signals
                       WHERE symbol = ?
                       ORDER BY timestamp_ms DESC
                       LIMIT ?""",
                    (symbol, limit),
                )
            rows = await cursor.fetchall()

        signals: list[Signal] = []
        for row in rows:
            if row[7]:
                ts = datetime.fromtimestamp(row[7] / 1000, tz=UTC)
            else:
                ts = datetime.fromisoformat(row[3])

            signals.append(
                Signal(
                    symbol=row[0],
                    signal_type=row[1],
                    strength=row[2],
                    timestamp=ts,
                    indicators=json.loads(row[4]) if row[4] else {},
                    confidence=row[5],
                    metadata=json.loads(row[6]) if row[6] else {},
                )
            )
        return signals
    finally:
        await pool.release(conn)


async def _async_update_trade(self: Database, trade: Trade) -> bool:
    """Async update trade by trade_id using a full Trade object."""
    return await asyncio.to_thread(self.update_trade, trade)


async def _async_update_order_status(
    self: Database, order_id: str, status: str, filled_qty: int | None = None
) -> bool:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_update_order_status(order_id, status)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                # Verify the order exists (consistent with sync update_order_status)
                await cursor.execute(
                    "SELECT 1 FROM orders WHERE order_id = ?", (order_id,)
                )
                if await cursor.fetchone() is None:
                    return False

                if filled_qty is not None:
                    await cursor.execute(
                        """UPDATE orders
                        SET status = ?, filled_quantity = ?, updated_at = ?,
                            updated_at_ms = ?
                        WHERE order_id = ?""",
                        (status, filled_qty, now_iso, now_ms, order_id),
                    )
                else:
                    await cursor.execute(
                        """UPDATE orders
                        SET status = ?, updated_at = ?, updated_at_ms = ?
                        WHERE order_id = ?""",
                        (status, now_iso, now_ms, order_id),
                    )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_get_trade(self: Database, trade_id: str) -> Trade | None:
    """Async retrieval of a trade by trade_id."""
    return await asyncio.to_thread(self.get_trade, trade_id)


async def _async_record_trade_decision(self: Database, decision: TradeDecision) -> bool:
    """True async implementation using aiosqlite."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_create_trade_decision(decision)

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    ts_ms = int(decision.timestamp.timestamp() * 1000)

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR REPLACE INTO trade_decisions
                    (decision_id, symbol, decision_type, composite_strength,
                     timestamp, entry_price, quantity, stop_loss, take_profit,
                     trailing_stop_config, position_size_method, risk_percentage,
                     var_analysis, gating_rules_result, source_breakdown, metadata,
                     status, created_at, updated_at, created_at_ms, updated_at_ms,
                     timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?)""",
                    (
                        decision.decision_id,
                        decision.symbol,
                        decision.decision_type.value,
                        float(decision.composite_strength),
                        decision.timestamp.isoformat(),
                        float(decision.entry_price),
                        int(decision.quantity),
                        float(decision.stop_loss),
                        decision.take_profit,
                        json.dumps(decision.trailing_stop_config),
                        decision.position_size_method,
                        float(decision.risk_percentage),
                        json.dumps(decision.var_analysis),
                        json.dumps(decision.gating_rules_result),
                        json.dumps(decision.source_breakdown),
                        json.dumps(decision.metadata),
                        decision.status,
                        now_iso,
                        now_iso,
                        now_ms,
                        now_ms,
                        ts_ms,
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


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
    """Async dual-write audit log matching the canonical _log_audit behavior."""
    pool = _get_pool(self)
    if pool is None:
        return await self.async_log_audit(
            action,
            entity_type,
            entity_id,
            user,
            metadata,
            previous_state,
            new_state,
        )

    now = datetime.now(UTC)
    metadata = metadata or {}
    previous_state = previous_state or {}
    new_state = new_state or {}

    entry_id = f"audit_{now.strftime('%Y%m%d%H%M%S%f')}_{id(self)}"
    entry_data: dict[str, Any] = {
        "entry_id": entry_id,
        "timestamp": now.isoformat(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user": user,
        "metadata": metadata,
        "previous_state": previous_state,
        "new_state": new_state,
        "timestamp_ms": int(now.timestamp() * 1000),
    }

    # Calculate SHA-256 hash over data excluding the hash field itself
    hash_data = dict(entry_data)
    hash_data.pop("sha256_hash", None)
    entry_data["sha256_hash"] = self._calculate_sha256(hash_data)

    # Write JSONL first; abort DB write on failure to keep dual trails consistent
    try:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry_data, sort_keys=True) + "\n")
    except OSError as e:
        raise RuntimeError(
            f"Failed to write audit log entry to JSONL file: {e}. "
            "Database commit aborted to maintain consistency."
        ) from e

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO audit_log
                    (entry_id, timestamp, action, entity_type, entity_id, user,
                     metadata, previous_state, new_state, sha256_hash, timestamp_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry_data["entry_id"],
                        entry_data["timestamp"],
                        entry_data["action"],
                        entry_data["entity_type"],
                        entry_data["entity_id"],
                        entry_data["user"],
                        json.dumps(entry_data["metadata"]),
                        json.dumps(entry_data["previous_state"]),
                        json.dumps(entry_data["new_state"]),
                        entry_data["sha256_hash"],
                        entry_data["timestamp_ms"],
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)


async def _async_get_historical_data(
    self: Database, symbol: str, start_time: datetime | None = None
) -> list[HistoricalData]:
    """Async fetch of historical data."""
    return await asyncio.to_thread(
        self.get_historical_data,
        symbol,
        "1d",
        start_time or datetime.min.replace(tzinfo=UTC),
        datetime.now(UTC),
    )


def _add_wrapper_method(cls: type[Database], name: str, method: Any) -> None:
    """Add a wrapper method to the Database class if it doesn't exist."""
    if not hasattr(cls, name):
        setattr(cls, name, method)
        method_obj = getattr(cls, name)
        if hasattr(method_obj, "_is_optimized"):
            method_obj._is_optimized = True
        else:
            object.__setattr__(method_obj, "_is_optimized", True)


def extend_database_class() -> None:
    """Extend the Database class with async methods."""
    from .database import Database

    method_map = {
        "_async_create_signal": _async_create_signal,
        "_async_store_historical_data": _async_store_historical_data,
        "_async_store_quote": _async_store_quote,
        "_async_store_position": _async_store_position,
        "_async_store_funds": _async_store_funds,
        "_async_get_latest_signals": _async_get_latest_signals,
        "_async_update_trade": _async_update_trade,
        "_async_update_order_status": _async_update_order_status,
        "_async_get_trade": _async_get_trade,
        "_async_record_trade_decision": _async_record_trade_decision,
        "_async_log_audit": _async_log_audit,
        "_async_get_historical_data": _async_get_historical_data,
    }

    for method_name, method in method_map.items():
        if not hasattr(Database, method_name):
            _add_wrapper_method(Database, method_name, method)


# Initialize the extension
extend_database_class()
