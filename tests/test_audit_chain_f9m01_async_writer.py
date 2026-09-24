"""F9-M-01-R1: frozen chain head in the pooled async audit writer.

The F9-M-01 wave (d73536d) added the SHA-256 chain, but only the canonical
sync writer advanced the per-instance chain-head cache after a successful
dual write (``Database._advance_chain_head``). The aiosqlite pool-path
writer ``DatabaseAsyncAdditions._async_log_audit`` READ the cached head but
never advanced it, so every entry it wrote linked to whichever head was
current when the cache was first loaded -- a frozen head. Live evidence
(data/audit.log, probed 24Sep): 4,578 consecutive entries from 18Sep
03:45 IST onward share ``previous_hash`` ``be01854c...`` while
``verify_audit_log_integrity()`` returns False (broken link on the first
frozen-head entry). The resolution doc's claim that the second writer
carries "identical chain semantics" was wrong; this wave fixes the root
cause and pins it.

Pins, mirroring tests/test_audit_chain_f9m01.py conventions:

1. Pooled async writes chain in file order (each entry links the previous
   line's sha256_hash) and the head cache advances after each write.
2. Alternating sync/async writes interleave into ONE chain (both writers
   serialize; no frozen head).
3. Concurrent pooled async writes (gather) produce an intact chain --
   the critical section makes read->hash->append->advance atomic.
4. Mixed-writer concurrency stress: N sync + N async interleaved, chain
   verifies at the end.
5. The async path's DB rows carry the same previous_hash as its JSONL
   lines (dual-write consistency).
6. The verifier passes on a chain produced purely by the async writer and
   still fails if a middle entry is mutated (link walk intact).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from loats.database import Database
from loats.database_async_additions import (
    AIOSQLITE_AVAILABLE,
    extend_database_class,
)


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Database bound to an insulated temp store (never the live DB)."""
    database = Database(
        db_path=tmp_path / "chain.db",
        audit_log_path=tmp_path / "audit.jsonl",
    )
    database._initialize_database()
    extend_database_class()
    return database


@pytest.fixture()
async def pooled_db(db: Database) -> Database:
    """Attach the aiosqlite pool exactly like the production init path."""
    if not AIOSQLITE_AVAILABLE:
        pytest.skip("aiosqlite not available")
    await db.async_initialize()
    assert db._async_pool is not None
    return db


async def _async_write(db: Database, i: int) -> None:
    await db.async_log_audit(
        action="CREATE",
        entity_type="trade",
        entity_id=f"a{i}",
        metadata={"i": i, "writer": "async"},
    )


def _sync_write(db: Database, i: int) -> None:
    db.log_audit(
        action="CREATE",
        entity_type="trade",
        entity_id=f"s{i}",
        metadata={"i": i, "writer": "sync"},
    )


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestFrozenHeadRegression:
    """The pooled async writer must chain and advance the head."""

    async def test_async_pool_writes_chain_in_file_order(self, pooled_db):
        await _async_write(pooled_db, 0)
        await _async_write(pooled_db, 1)
        await _async_write(pooled_db, 2)

        lines = _read_lines(pooled_db.audit_log_path)
        assert len(lines) == 3
        assert lines[1]["previous_hash"] == lines[0]["sha256_hash"]
        assert lines[2]["previous_hash"] == lines[1]["sha256_hash"]

    async def test_async_pool_writes_advance_head_cache(self, pooled_db):
        await _async_write(pooled_db, 0)
        first_hash = _read_lines(pooled_db.audit_log_path)[0]["sha256_hash"]
        assert pooled_db._chain_head_loaded
        assert pooled_db._chain_head == first_hash

        # A sync write AFTER an async write must link the async entry's
        # hash -- this is the exact seam the frozen-head bug broke.
        _sync_write(pooled_db, 1)
        lines = _read_lines(pooled_db.audit_log_path)
        assert lines[1]["previous_hash"] == lines[0]["sha256_hash"]

    async def test_sync_async_alternation_single_chain(self, pooled_db):
        _sync_write(pooled_db, 0)
        await _async_write(pooled_db, 0)
        _sync_write(pooled_db, 1)
        await _async_write(pooled_db, 1)

        lines = _read_lines(pooled_db.audit_log_path)
        assert len(lines) == 4
        for prev_line, entry in pairwise(lines):
            assert entry["previous_hash"] == prev_line["sha256_hash"]
        assert pooled_db.verify_audit_log_integrity() is True

    async def test_concurrent_async_writes_intact_chain(self, pooled_db):
        await asyncio.gather(*(_async_write(pooled_db, i) for i in range(25)))

        lines = _read_lines(pooled_db.audit_log_path)
        assert len(lines) == 25
        for prev_line, entry in pairwise(lines):
            assert entry["previous_hash"] == prev_line["sha256_hash"]
        assert pooled_db.verify_audit_log_integrity() is True

    async def test_mixed_writer_concurrency_stress(self, pooled_db):
        async def mixed(i: int) -> None:
            if i % 2 == 0:
                _sync_write(pooled_db, i)
            else:
                await _async_write(pooled_db, i)

        await asyncio.gather(*(mixed(i) for i in range(40)))

        lines = _read_lines(pooled_db.audit_log_path)
        assert len(lines) == 40
        for prev_line, entry in pairwise(lines):
            assert entry["previous_hash"] == prev_line["sha256_hash"]
        assert pooled_db.verify_audit_log_integrity() is True

    async def test_async_db_rows_carry_same_link_as_jsonl(self, pooled_db):
        await _async_write(pooled_db, 0)
        await _async_write(pooled_db, 1)

        import sqlite3

        conn = sqlite3.connect(pooled_db.db_path)
        rows = conn.execute(
            "SELECT entry_id, sha256_hash, previous_hash FROM audit_log "
            "ORDER BY timestamp_ms, entry_id"
        ).fetchall()
        conn.close()
        lines = {d["entry_id"]: d for d in _read_lines(pooled_db.audit_log_path)}
        assert len(rows) == 2
        for entry_id, file_hash, file_prev in (
            (r[0], lines[r[0]]["sha256_hash"], lines[r[0]]["previous_hash"])
            for r in rows
        ):
            db_row = next(r for r in rows if r[0] == entry_id)
            assert db_row[1] == file_hash
            assert db_row[2] == file_prev

    async def test_async_only_chain_verifies_and_still_catches_mutation(
        self, pooled_db
    ):
        for i in range(10):
            await _async_write(pooled_db, i)
        assert pooled_db.verify_audit_log_integrity() is True

        # Mutate a middle entry's payload, keep its hashes: the link walk
        # must still fail it (self-hash layer).
        path = pooled_db.audit_log_path
        lines = _read_lines(path)
        lines[5]["metadata"]["tampered"] = True
        path.write_text(
            "".join(json.dumps(d, sort_keys=True) + "\n" for d in lines),
            encoding="utf-8",
        )
        assert pooled_db.verify_audit_log_integrity() is False

    def test_timestamp_helper_matches_sync_format(self, db):
        from loats.database_async_additions import _audit_timestamp_ms

        now = datetime.now(UTC)
        assert _audit_timestamp_ms(now) == int(now.timestamp() * 1000)


class TestLiveParity:
    """Grandfathering regression guard: legacy prefix stays verifiable."""

    async def test_legacy_file_then_async_writes_seed_and_chain(self, pooled_db):
        legacy = {
            "entry_id": "legacy_1",
            "timestamp": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
            "action": "CREATE",
            "entity_type": "trade",
            "entity_id": "legacy",
            "user": "system",
            "metadata": {},
            "previous_state": None,
            "new_state": None,
            "timestamp_ms": 1_785_600_000_000,
        }
        import hashlib

        legacy_hash = hashlib.sha256(
            json.dumps(legacy, sort_keys=True).encode()
        ).hexdigest()
        legacy["sha256_hash"] = legacy_hash
        path = pooled_db.audit_log_path
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(legacy, sort_keys=True) + "\n")

        await _async_write(pooled_db, 0)
        lines = _read_lines(path)
        assert len(lines) == 2
        assert lines[1]["previous_hash"] == legacy_hash
        assert pooled_db.verify_audit_log_integrity() is True
