"""Async database operations for LOATS13July2026 using aiosqlite. This module extends the Database class with true async I/O capabilities."""

import importlib.util
import json
from datetime import UTC, datetime

from .database import Database
from .models import (
    Signal,
)

# Check for aiosqlite availability
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
