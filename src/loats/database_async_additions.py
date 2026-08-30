"""Async additions for the Database class.

This module extends the Database class with async methods using aiosqlite.
All methods are monkey-patched onto the Database class during initialization.
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import Database

try:
    import aiosqlite

    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

from .models import (
    FundsData,
    HistoricalData,
    Position,
    Signal,
    TradeDecision,
)


async def _async_create_signal(self: "Database", signal: Signal) -> bool:
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
                """INSERT INTO signals
                (symbol, signal_type, strength, timestamp, indicators,
                 confidence, metadata, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.symbol,
                    signal.signal_type.value,
                    float(signal.strength),
                    signal.timestamp.isoformat(),
                    json.dumps(signal.indicators),
                    float(signal.confidence),
                    json.dumps(signal.metadata),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_historical_data(self: "Database", data: list[HistoricalData]) -> bool:
    """True async implementation using aiosqlite for bulk insert."""
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
            # Use executemany for bulk insert
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

            await cursor.executemany(
                """INSERT OR REPLACE INTO historical_data
                (symbol, timestamp, open, high, low, close, volume, interval,
                 created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                records,
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_position(self: "Database", position: Position) -> bool:
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
    ts_ms = int(position.timestamp.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT OR REPLACE INTO positions
                (symbol, quantity, avg_price, timestamp, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    position.symbol,
                    float(position.quantity),
                    float(position.avg_price),
                    position.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_store_funds(self: "Database", funds: FundsData) -> bool:
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
                """INSERT OR REPLACE INTO funds
                (total, available, timestamp, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    float(funds.total),
                    float(funds.available),
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
    self: "Database", limit: int = 10, minutes_ago: int = 5
) -> list[Signal]:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return []

    cutoff_ms = int((datetime.now(UTC).timestamp() - minutes_ago * 60) * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT symbol, signal_type, strength, timestamp, indicators,
                          confidence, metadata, timestamp_ms
                   FROM signals
                   WHERE timestamp_ms >= ?
                   ORDER BY timestamp_ms DESC
                   LIMIT ?""",
                (cutoff_ms, limit),
            )
            rows = await cursor.fetchall()

        signals = []
        for row in rows:
            if row[7]:
                ts_ms = row[7]
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
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
        await self._async_pool.release(conn)


async def _async_update_trade(
    self: "Database", trade_id: str, status: str, filled_qty: int, filled_price: float
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
            await cursor.execute(
                """UPDATE trades
                SET status = ?, filled_qty = ?, filled_price = ?,
                    updated_at = ?, updated_at_ms = ?
                WHERE id = ?""",
                (status, filled_qty, filled_price, now_iso, now_ms, trade_id),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_update_order_status(
    self: "Database", order_id: str, status: str, filled_qty: int | None = None
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
            if filled_qty is not None:
                await cursor.execute(
                    """UPDATE orders
                    SET status = ?, filled_qty = ?, updated_at = ?, updated_at_ms = ?
                    WHERE id = ?""",
                    (status, filled_qty, now_iso, now_ms, order_id),
                )
            else:
                await cursor.execute(
                    """UPDATE orders
                    SET status = ?, updated_at = ?, updated_at_ms = ?
                    WHERE id = ?""",
                    (status, now_iso, now_ms, order_id),
                )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_record_trade_decision(
    self: "Database", decision: TradeDecision
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
    ts_ms = int(decision.timestamp.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT OR REPLACE INTO trade_decisions
                (decision_id, symbol, decision_type, confidence, strength,
                 timestamp, metadata, created_at, created_at_ms, timestamp_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.decision_id,
                    decision.symbol,
                    decision.decision_type.value,
                    float(decision.confidence),
                    float(decision.strength),
                    decision.timestamp.isoformat(),
                    json.dumps(decision.metadata),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True


async def _async_log_audit(
    self: "Database", action: str, entity_type: str, entity_id: str, **kwargs: Any
) -> None:
    """True async implementation using aiosqlite."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT INTO audit_log
                (action, entity_type, entity_id, user, metadata, created_at, created_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    action,
                    entity_type,
                    entity_id,
                    kwargs.get("user", "system"),
                    json.dumps(kwargs.get("metadata", {})),
                    now_iso,
                    now_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)


async def _async_get_historical_data(
    self: "Database", symbol: str, start_time: datetime | None = None
) -> list[HistoricalData]:
    """True async implementation using aiosqlite to fetch historical data."""
    if (
        not AIOSQLITE_AVAILABLE
        or not hasattr(self, "_async_pool")
        or self._async_pool is None
    ):
        return []

    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            if start_time:
                start_ms = int(start_time.timestamp() * 1000)
                await cursor.execute(
                    """SELECT symbol, timestamp, open, high, low, close, volume,
                              interval, timestamp_ms
                       FROM historical_data
                       WHERE symbol = ? AND timestamp_ms >= ?
                       ORDER BY timestamp_ms ASC""",
                    (symbol, start_ms),
                )
            else:
                await cursor.execute(
                    """SELECT symbol, timestamp, open, high, low, close, volume,
                              interval, timestamp_ms
                       FROM historical_data
                       WHERE symbol = ?
                       ORDER BY timestamp_ms ASC""",
                    (symbol,),
                )

            rows = await cursor.fetchall()

        data = []
        for row in rows:
            if row[8]:
                ts_ms = row[8]
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            else:
                ts = datetime.fromisoformat(row[1])

            data.append(
                HistoricalData(
                    symbol=row[0],
                    timestamp=ts,
                    open=row[2],
                    high=row[3],
                    low=row[4],
                    close=row[5],
                    volume=row[6],
                    interval=row[7],
                )
            )
        return data
    finally:
        await self._async_pool.release(conn)


def _add_wrapper_method(cls: type["Database"], name: str, method: Any) -> None:
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

    # Add all async methods
    for method_name in [
        "_async_create_signal",
        "_async_store_historical_data",
        "_async_store_position",
        "_async_store_funds",
        "_async_get_latest_signals",
        "_async_update_trade",
        "_async_update_order_status",
        "_async_record_trade_decision",
        "_async_log_audit",
        "_async_get_historical_data",
        "async_log_audit",  # Public wrapper for _async_log_audit
        "async_get_historical_data",  # Public wrapper for _async_get_historical_data
    ]:
        if hasattr(Database, method_name):
            continue

        # Map method names to their implementations
        method_map = {
            "_async_create_signal": _async_create_signal,
            "_async_store_historical_data": _async_store_historical_data,
            "_async_store_position": _async_store_position,
            "_async_store_funds": _async_store_funds,
            "_async_get_latest_signals": _async_get_latest_signals,
            "_async_update_trade": _async_update_trade,
            "_async_update_order_status": _async_update_order_status,
            "_async_record_trade_decision": _async_record_trade_decision,
            "_async_log_audit": _async_log_audit,
            "_async_get_historical_data": _async_get_historical_data,
        }

        if method_name in method_map:
            _add_wrapper_method(Database, method_name, method_map[method_name])


# Initialize the extension
extend_database_class()
