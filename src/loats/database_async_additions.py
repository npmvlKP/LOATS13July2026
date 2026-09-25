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
from uuid import uuid4

if TYPE_CHECKING:
    from .database import Database

# SQLite (even in WAL mode) serialises writers across connections.  Use a
# module-level write lock so that all aiosqlite-backed writes are serialised
# without contending for the database lock.  Reads remain unblocked.
_async_write_lock = asyncio.Lock()


def _audit_timestamp_ms(now: datetime) -> int:
    """Sync-writer parity: audit_log.timestamp_ms = int(now.timestamp()*1000)."""
    return int(now.timestamp() * 1000)


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
from .signal_outcomes import SignalOutcomeState  # noqa: E402
from .signal_source_guard import validate_signal_provenance  # noqa: E402


def _get_pool(self: Database) -> Any | None:
    """Return the async connection pool when it is available."""
    pool: Any = getattr(self, "_async_pool", None)
    if pool is None or not AIOSQLITE_AVAILABLE:
        return None
    return pool


async def _async_create_signal(self: Database, signal: Signal) -> bool:
    """True async implementation using aiosqlite."""
    # F9-L-03 (TODO-12): fail-closed provenance gate BEFORE any write,
    # mirroring the sync path so the async pool cannot bypass the guard.
    validate_signal_provenance(signal)
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


async def _async_record_signal_outcome_open(
    self: Database,
    signal_id: str,
    horizon_minutes: int,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Pool-native outcome-open insert (mirrors ``_async_create_signal``).

    Mirrors the sync ``record_signal_outcome_open`` exactly (same
    ``INSERT OR IGNORE``, same columns); ``to_thread`` fallback would be
    equally correct -- the pool path is preferred for symmetric behavior
    with the signal write that precedes it.
    """
    pool = _get_pool(self)
    if pool is None:
        return await asyncio.to_thread(
            self.record_signal_outcome_open, signal_id, horizon_minutes, metadata
        )

    now = datetime.now(UTC)
    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT OR IGNORE INTO signal_outcomes
                    (signal_id, outcome_state, horizon_minutes, created_at,
                     metadata)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        signal_id,
                        SignalOutcomeState.OPEN.value,
                        int(horizon_minutes),
                        now.isoformat(),
                        json.dumps(metadata) if metadata else None,
                    ),
                )
            await conn.commit()
        finally:
            await pool.release(conn)
    return True


async def _async_resolve_signal_outcomes(
    self: Database,
    now: datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Async resolve; offloads the sync resolver to a worker thread.

    The resolver does one JOIN scan plus per-row history reads; running
    it on the synchronous connection inside ``asyncio.to_thread`` follows
    the F8-H-04 thread-offload precedent and keeps a single code path,
    so a verdict can never differ between pool and non-pool deployments.
    """
    return await asyncio.to_thread(self.resolve_signal_outcomes, now, limit)


async def _async_get_signal_outcome_summary(self: Database) -> dict[str, Any]:
    """Async wrapper get_signal_outcome_summary(); avoids blocking the loop."""
    return await asyncio.to_thread(self.get_signal_outcome_summary)


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
                     timestamp_ms, as_of_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?)""",
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
                        # F8-L-02: ISO-8601 snapshot date (nullable).
                        (
                            decision.as_of_date.isoformat()
                            if decision.as_of_date is not None
                            else None
                        ),
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
    """Async dual-write audit log matching the canonical _log_audit behavior.

    F9-M-01-R1: the chain read -> hash -> JSONL append -> head-advance
    sequence runs as ONE ``asyncio.to_thread`` hop inside the shared
    ``_audit_lock`` -- the same critical section the canonical sync
    writer uses -- so sync and async writers serialize against each
    other and the per-instance chain-head cache stays honest. The
    aiosqlite INSERT then completes on the loop under
    ``_async_write_lock`` (resolving pool awaits inside the worker
    deadlocks: the single-threaded pool queues on the very loop the
    worker's future is blocking). It replaces the previous shape --
    entry_id generated on the loop (microsecond timestamp + ``id(self)``
    suffix, colliding under concurrency and mass-falling back via the
    UNIQUE-constraint path) and a JSONL append on the loop thread
    outside any lock (orphan lines, frozen chain head: the head was read
    but never advanced, so every pooled entry linked to whichever head
    was current at first cache load -- 4,578 broken links in the live
    log before this fix).

    Direct on-loop ``log_audit()`` calls remain loop-blocking by design;
    they cannot share the sync writer's critical section from the loop
    thread because the threading lock is re-entrant per thread. Call
    ``async_log_audit`` from coroutines.
    """
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

    def _pooled_write() -> dict[str, Any]:
        """Chain + JSONL append under _audit_lock; returns the entry."""
        with self._audit_lock:
            new_state_resolved = new_state or {}
            # Model-parity entry_id: microsecond timestamp + uuid suffix.
            # The old id(self) suffix collided between same-microsecond
            # writes and mass-triggered the UNIQUE-constraint fallback.
            entry_id = f"audit_{now.strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}"
            entry_data: dict[str, Any] = {
                "entry_id": entry_id,
                "timestamp": now.isoformat(),
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "user": user,
                "metadata": metadata,
                "previous_state": previous_state,
                "new_state": new_state_resolved,
                "timestamp_ms": _audit_timestamp_ms(now),
            }

            # F9-M-01 (TODO-6): hash-chain link, same semantics as the
            # canonical sync writer -- link to the last line's
            # sha256_hash, seeded at the legacy head for grandfathered
            # files.
            entry_data["previous_hash"] = self._read_chain_head()
            # Calculate SHA-256 hash over data excluding the hash field
            # itself
            hash_data = dict(entry_data)
            hash_data.pop("sha256_hash", None)
            entry_data["sha256_hash"] = self._calculate_sha256(hash_data)

            # Write JSONL first; abort the DB write on failure to keep the
            # dual trails consistent (same ordering as the sync writer).
            try:
                self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.audit_log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry_data, sort_keys=True) + "\n")
            except OSError as e:
                raise RuntimeError(
                    "Failed to write audit log entry to JSONL file: "
                    f"{e}. Database commit aborted to maintain consistency."
                ) from e

            # F9-M-01-R1: advance the chain head exactly like the sync
            # writer. Every writer appends inside ``_audit_lock``, so our
            # line IS the file's last line at this point; if the DB insert
            # below fails, the fallback entry links to OUR hash (head
            # already advanced), keeping the file chain unbroken -- the
            # entry stays file-only, which is the documented sync-path
            # failure mode as well.
            self._advance_chain_head(entry_data["sha256_hash"])

            # DB insert second, inside the same critical section.
            return entry_data

    async with _async_write_lock:
        conn = await pool.acquire()
        try:
            entry_data = await asyncio.to_thread(_pooled_write)
        except BaseException:
            await pool.release(conn)
            raise

    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT INTO audit_log
                (entry_id, timestamp, action, entity_type, entity_id, user,
                 metadata, previous_state, new_state, sha256_hash, timestamp_ms,
                 previous_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    entry_data["previous_hash"],
                ),
            )
        await conn.commit()
    except Exception as exc:
        raise RuntimeError(
            f"aiosqlite pooled audit insert failed for {entry_data['entry_id']}: {exc}"
        ) from exc
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
        "_async_record_signal_outcome_open": _async_record_signal_outcome_open,
        "_async_resolve_signal_outcomes": _async_resolve_signal_outcomes,
        "_async_get_signal_outcome_summary": _async_get_signal_outcome_summary,
    }

    for method_name, method in method_map.items():
        if not hasattr(Database, method_name):
            _add_wrapper_method(Database, method_name, method)


# Initialize the extension
extend_database_class()
