# --- Imports ---
import json
from datetime import datetime
from datetime import timezone as UTC
from typing import Any

from loats.database import Database
from loats.models import (
    AuditLogEntry as AuditLog,
)
from loats.models import (
    FundsData as Funds,
)
from loats.models import (
    HistoricalData,
    Order,
    Position,
    QuoteData,
    Signal,
    SignalType,
    Trade,
    TradeDecision,
)

# --- Module Initialization ---
# Ensure all methods are defined and exposed
AIOSQLITE_AVAILABLE = False
try:
    import aiosqlite as _aiosqlite  # type: ignore[no-redef] - checked for availability
    AIOSQLITE_AVAILABLE = True
except ImportError:
    pass
# --- Extension Function ---
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
        "_async_store_quote",
    ]:
        if hasattr(Database, method_name):
            continue
        if method_name == "_async_create_signal":
            _add_wrapper_method(Database, method_name, _async_create_signal)
        elif method_name == "_async_store_historical_data":
            _add_wrapper_method(Database, method_name, _async_store_historical_data)
        elif method_name == "_async_store_position":
            _add_wrapper_method(Database, method_name, _async_store_position)
        elif method_name == "_async_store_funds":
            _add_wrapper_method(Database, method_name, _async_store_funds)
        elif method_name == "_async_get_latest_signals":
            _add_wrapper_method(Database, method_name, _async_get_latest_signals)
        elif method_name == "_async_update_trade":
            _add_wrapper_method(Database, method_name, _async_update_trade)
        elif method_name == "_async_update_order_status":
            _add_wrapper_method(Database, method_name, _async_update_order_status)
        elif method_name == "_async_record_trade_decision":
            _add_wrapper_method(Database, method_name, _async_record_trade_decision)
        elif method_name == "_async_log_audit":
            _add_wrapper_method(Database, method_name, _async_log_audit)
        elif method_name == "_async_store_quote":
            _add_wrapper_method(Database, method_name, _async_store_quote)


async def _async_record_trade_decision(self: Database, decision: TradeDecision) -> bool:
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
                """                INSERT INTO trade_decisions                (decision_id, symbol, decision_type, quantity, price, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    decision.decision_id,
                    decision.symbol,
                    decision.decision_type,
                    decision.quantity,
                    decision.price,
                    decision.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True

async def _async_log_audit(self: Database, audit: AuditLog) -> bool:
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
    ts_ms = int(audit.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT INTO audit_log                (action, entity_type, entity_id, details, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    audit.action,
                    audit.entity_type,
                    audit.entity_id,
                    json.dumps(audit.details),
                    audit.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
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
    ts_ms = int(trade.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(






                """                INSERT OR REPLACE INTO trades                (trade_id, symbol, quantity, price, side, status, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    trade.trade_id,
                    trade.symbol,
                    trade.quantity,
                    trade.price,
                    trade.side,
                    trade.status,
                    trade.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True

async def _async_update_order_status(self: Database, order: Order) -> bool:
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
    ts_ms = int(order.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO orders                (order_id, symbol, quantity, price, side, status, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    order.order_id,
                    order.symbol,
                    order.quantity,
                    order.price,
                    order.side,
                    order.status,
                    order.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
async def _async_store_funds(self: Database, funds: Funds) -> bool:
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
                """                INSERT OR REPLACE INTO funds                (symbol, balance, available, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?)                """,
                (
                    funds.symbol,
                    funds.balance,
                    funds.available,
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

async def _async_get_latest_signals(self: Database, scan_type: str, limit: int = 10) -> list[Signal]:
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
            await cursor.execute(
                """                SELECT signal_id, symbol, signal_type, strength, timestamp, indicators, metadata, confidence                FROM signals                WHERE scan_type = ?                ORDER BY timestamp DESC                LIMIT ?                """,
                (scan_type, limit),
            )
            rows = await cursor.fetchall()
        return [_signal_from_row(row) for row in rows]
    finally:
        await self._async_pool.release(conn)
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
                """                INSERT OR REPLACE INTO quotes                (symbol, last_price, open, high, low, close, volume, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    quote.symbol,
                    quote.last_price,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.close,
                    quote.volume,
                    quote.timestamp.isoformat(),
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
    ts_ms = int(position.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO positions                (symbol, quantity, average_price, last_price, pnl, product_type, buy_quantity, sell_quantity, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    position.symbol,
                    position.quantity,
                    getattr(position, 'average_price', 0),
                    getattr(position, 'last_price', 0),
                    getattr(position, 'pnl', 0),
                    getattr(position, 'product_type', None),
                    getattr(position, 'buy_quantity', 0),
                    getattr(position, 'sell_quantity', 0),
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
    ts_ms = int(position.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO positions                (symbol, quantity, avg_price, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?)                """,
                (
                    position.symbol,
                    position.quantity,
                    position.avg_price,
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
# --- Async Methods ---
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
                """                INSERT INTO signals                (signal_id, symbol, signal_type, strength, timestamp, indicators, metadata, confidence, scan_type, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    signal.signal_id,
                    signal.symbol,
                    signal.signal_type.value,
                    signal.strength,
                    signal.timestamp.isoformat(),
                    json.dumps(signal.indicators),
                    json.dumps(signal.metadata) if signal.metadata else None,
                    signal.confidence,
                    signal.scan_type,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True

async def _async_store_historical_data(self: Database, data: HistoricalData) -> bool:
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
    ts_ms = int(data.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT INTO historical_data                (symbol, timestamp, open, high, low, close, volume, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    data.symbol,
                    data.timestamp.isoformat(),
                    data.open,
                    data.high,
                    data.low,
                    data.close,
                    data.volume,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
# --- Helper Functions ---
def _signal_from_row(self: Database, row) -> Signal:
    """Convert a SQLite row to a Signal object."""
    return Signal(
        signal_id=row[0],
        symbol=row[1],
        signal_type=SignalType(row[2]),
        strength=row[3],
        timestamp=datetime.fromisoformat(row[4]),
        indicators=json.loads(row[5]),
        metadata=json.loads(row[6]) if row[6] else None,
        confidence=row[7],
    )

def _model_to_dict(self: Database, model: Any) -> dict:
    """Convert a model object to a dictionary."""
    return model.__dict__

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
async def _async_store_historical_data(self: Database, data: HistoricalData) -> bool:
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
    ts_ms = int(data.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT INTO historical_data                (symbol, timestamp, open, high, low, close, volume, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    data.symbol,
                    data.timestamp.isoformat(),
                    data.open,
                    data.high,
                    data.low,
                    data.close,
                    data.volume,
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
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
                """                INSERT INTO signals                (signal_id, symbol, signal_type, strength, timestamp, indicators, metadata, confidence, scan_type, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    signal.signal_id,
                    signal.symbol,
                    signal.signal_type.value,
                    signal.strength,
                    signal.timestamp.isoformat(),
                    json.dumps(signal.indicators),
                    json.dumps(signal.metadata) if signal.metadata else None,
                    signal.confidence,
                    signal.scan_type,
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
                """                INSERT OR REPLACE INTO quotes                (symbol, last_price, open, high, low, close, volume, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    quote.symbol,
                    quote.last_price,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.close,
                    quote.volume,
                    quote.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
def _model_to_dict(self: Database, model: Any) -> dict:
    """Convert a model object to a dictionary."""
    return model.__dict__
def _signal_from_row(self: Database, row) -> Signal:
    """Convert a SQLite row to a Signal object."""
    return Signal(
        signal_id=row[0],
        symbol=row[1],
        signal_type=SignalType(row[2]),
        strength=row[3],
        timestamp=datetime.fromisoformat(row[4]),
        indicators=json.loads(row[5]),
        metadata=json.loads(row[6]) if row[6] else None,
        confidence=row[7],
    )
async def _async_record_trade_decision(self: Database, decision: TradeDecision) -> bool:
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
                """                INSERT INTO trade_decisions                (decision_id, symbol, decision_type, quantity, price, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    decision.decision_id,
                    decision.symbol,
                    decision.decision_type,
                    decision.quantity,
                    decision.price,
                    decision.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
async def _async_update_order_status(self: Database, order: Order) -> bool:
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
    ts_ms = int(order.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO orders                (order_id, symbol, quantity, price, side, status, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    order.order_id,
                    order.symbol,
                    order.quantity,
                    order.price,
                    order.side,
                    order.status,
                    order.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
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
    ts_ms = int(trade.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO trades                (trade_id, symbol, quantity, price, side, status, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    trade.trade_id,
                    trade.symbol,
                    trade.quantity,
                    trade.price,
                    trade.side,
                    trade.status,
                    trade.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True
async def _async_get_latest_signals(self: Database, scan_type: str, limit: int = 10) -> list[Signal]:
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
            await cursor.execute(
                """                SELECT signal_id, symbol, signal_type, strength, timestamp, indicators, metadata, confidence                FROM signals                WHERE scan_type = ?                ORDER BY timestamp DESC                LIMIT ?                """,
                (scan_type, limit),
            )
            rows = await cursor.fetchall()
        return [_signal_from_row(row) for row in rows]
    finally:
        await self._async_pool.release(conn)
async def _async_store_funds(self: Database, funds: Funds) -> bool:
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
                """                INSERT OR REPLACE INTO funds                (symbol, balance, available, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?)                """,
                (
                    funds.symbol,
                    funds.balance,
                    funds.available,
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
"""Async database operations for LOATS13July2026 using aiosqlite. This module extends the Database class with true async I/O capabilities."""

import importlib.util  # noqa: E402
from datetime import UTC  # noqa: E402
from typing import Any  # noqa: E402

from .database import Database  # noqa: E402
from .models import (  # noqa: E402
    HistoricalData,
    Position,
    QuoteData,
    Signal,
    Trade,
    TradeDecision,
)


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
                """                INSERT INTO signals                (signal_id, symbol, signal_type, strength, timestamp,                 indicators, metadata, confidence, created_at, created_at_ms,                 timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                """,
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
# Check for aiosqlite availability
AIOSQLITE_AVAILABLE = importlib.util.find_spec("aiosqlite") is not None




async def _async_store_historical_data(self: Database, data: list[HistoricalData]) -> bool:
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
                    """                    INSERT OR REPLACE INTO historical_data                    (symbol, timestamp, open, high, low, close, volume,                     interval, created_at, created_at_ms, timestamp_ms)                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)                    """,
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


async def _async_log_audit(self: Database, action: str, entity_type: str, entity_id: str, **kwargs) -> None:
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
                """                INSERT INTO audit_log                (action, entity_type, entity_id, user, metadata, created_at, created_at_ms)                VALUES (?, ?, ?, ?, ?, ?, ?)                """,
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


def extend_database_class() -> None:
    """Extend the Database class with async methods."""
    from .database import Database  # noqa: E402
    # Add core async methods
    if not hasattr(Database, "_async_create_signal"):
        Database._async_create_signal = _async_create_signal  # type: ignore[attr-defined]
        Database._async_store_historical_data = _async_store_historical_data  # type: ignore[attr-defined]

# Initialize the extension
extend_database_class()


async def _async_log_audit(self: Database, audit: AuditLog) -> bool:
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
    ts_ms = int(audit.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT INTO audit_log                (action, entity_type, entity_id, details, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?, ?)                """,
                (
                    audit.action,
                    audit.entity_type,
                    audit.entity_id,
                    json.dumps(audit.details),
                    audit.timestamp.isoformat(),
                    now_iso,
                    now_ms,
                    ts_ms,
                ),
            )
        await conn.commit()
    finally:
        await self._async_pool.release(conn)
    return True

# Update extend_database_class to include all methods
def extend_database_class() -> None:
    """Extend the Database class with async methods."""
    from .database import Database  # noqa: E402
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
    ]:
        if hasattr(Database, method_name):
            continue
        if method_name == "_async_create_signal":
            _add_wrapper_method(Database, method_name, _async_create_signal)
        elif method_name == "_async_store_historical_data":
            _add_wrapper_method(Database, method_name, _async_store_historical_data)
        elif method_name == "_async_store_position":
            _add_wrapper_method(Database, method_name, _async_store_position)
        elif method_name == "_async_store_funds":
            _add_wrapper_method(Database, method_name, _async_store_funds)
        elif method_name == "_async_get_latest_signals":
            _add_wrapper_method(Database, method_name, _async_get_latest_signals)
        elif method_name == "_async_update_trade":
            _add_wrapper_method(Database, method_name, _async_update_trade)
        elif method_name == "_async_update_order_status":
            _add_wrapper_method(Database, method_name, _async_update_order_status)
        elif method_name == "_async_record_trade_decision":
            _add_wrapper_method(Database, method_name, _async_record_trade_decision)
        elif method_name == "_async_log_audit":
            _add_wrapper_method(Database, method_name, _async_log_audit)

# Initialize the extension
extend_database_class()


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
    ts_ms = int(position.timestamp.timestamp() * 1000)
    conn = await self._async_pool.acquire()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """                INSERT OR REPLACE INTO positions                (symbol, quantity, avg_price, timestamp, created_at, created_at_ms, timestamp_ms)                VALUES (?, ?, ?, ?, ?, ?, ?)                """,
                (
                    position.symbol,
                    position.quantity,
                    position.avg_price,
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
