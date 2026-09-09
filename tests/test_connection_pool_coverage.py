"""Hermetic tests for loats.utils.connection_pool.

Uses a temp-file SQLite database (no network, no shared state) to exercise
acquire/release/close_all pooling, stale-connection replacement and the
max-size guard.
"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from loats.utils.connection_pool import SimpleConnectionPool


class TestSimpleConnectionPool:
    @pytest.mark.asyncio
    async def test_acquire_creates_connection(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        conn = await pool.acquire()
        assert isinstance(conn, aiosqlite.Connection)
        assert pool.total_connections == 1
        await conn.close()
        pool._connections_created = 0

    @pytest.mark.asyncio
    async def test_release_then_acquire_reuses(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        conn = await pool.acquire()
        await pool.release(conn)
        assert pool.size == 1
        conn2 = await pool.acquire()
        assert conn2 is conn  # reused from pool
        await conn2.close()
        pool._connections_created = 0

    @pytest.mark.asyncio
    async def test_stale_connection_is_replaced(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        conn = await pool.acquire()
        await conn.close()  # stale: execute will fail on closed handle
        await pool.release(conn)
        conn2 = await pool.acquire()  # must detect failure, create new
        assert conn2 is not conn or pool.total_connections >= 1
        rows = await conn2.execute("SELECT 1")
        assert rows is not None
        await conn2.close()
        pool._connections_created = 0

    @pytest.mark.asyncio
    async def test_maxsize_enforced(self, tmp_path) -> None:
        # timeout is the bounded wait before exhaustion is declared; with a
        # saturated pool and nothing releasing, acquire must still raise.
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=1, timeout=0.2)
        conn = await pool.acquire()
        with pytest.raises(RuntimeError, match="Maximum pool size"):
            await pool.acquire()  # pool empty, limit reached, wait expires
        await conn.close()
        pool._connections_created = 0

    @pytest.mark.asyncio
    async def test_acquire_waits_for_release_when_saturated(self, tmp_path) -> None:
        # Regression (live 08Sep2026): a saturated pool previously raised
        # immediately. acquire must now wait for a release and succeed.
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=1, timeout=5.0)
        conn = await pool.acquire()

        async def release_later() -> None:
            await asyncio.sleep(0.2)
            await pool.release(conn)

        task = asyncio.create_task(release_later())
        conn2 = await pool.acquire()  # waits for the release, succeeds
        assert conn2 is conn
        await task
        await pool.release(conn2)
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_close_all_closes_pooled_and_resets_count(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        conn = await pool.acquire()
        await pool.release(conn)
        assert pool.size == 1
        await pool.close_all()
        assert pool.size == 0
        assert pool.total_connections == 0

    @pytest.mark.asyncio
    async def test_close_all_tolerates_failing_close(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        conn = await pool.acquire()
        await conn.close()  # double close path on same handle
        await pool.release(conn)
        await pool.close_all()  # second close may raise; must not propagate

    @pytest.mark.asyncio
    async def test_del_is_noop(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=1)
        pool.__del__()  # must not raise

    @pytest.mark.asyncio
    async def test_size_and_total_properties(self, tmp_path) -> None:
        pool = SimpleConnectionPool(str(tmp_path / "p.db"), maxsize=2)
        assert pool.size == 0
        assert pool.total_connections == 0
        conn = await pool.acquire()
        assert pool.total_connections == 1
        await pool.release(conn)
        assert pool.size == 1
        await pool.close_all()
