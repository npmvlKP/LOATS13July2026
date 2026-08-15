"""
Simple connection pool implementation for aiosqlite.
This provides basic connection pooling functionality since aiosqlite doesn't have built-in pooling.
"""

import asyncio
import logging
from collections import deque

import aiosqlite

logger = logging.getLogger(__name__)


class SimpleConnectionPool:
    """
    Simple async connection pool for aiosqlite.
    """

    def __init__(self, database: str, maxsize: int = 10, timeout: float = 30.0):
        self.database = database
        self.maxsize = maxsize
        self.timeout = timeout
        self._pool: deque[aiosqlite.Connection] = deque()
        self._lock = asyncio.Lock()
        self._connections_created = 0

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection."""
        if self._connections_created >= self.maxsize:
            raise RuntimeError(
                f"Maximum pool size of {self.maxsize} connections reached"
            )

        conn = await aiosqlite.connect(self.database, timeout=self.timeout)
        self._connections_created += 1
        logger.debug(
            f"Created new connection, total connections: {self._connections_created}"
        )
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool."""
        async with self._lock:
            if self._pool:
                conn = self._pool.popleft()
                logger.debug(
                    f"Reusing connection from pool, remaining in pool: {len(self._pool)}"
                )
                try:
                    # Test the connection
                    await conn.execute("SELECT 1")
                    return conn
                except Exception as e:
                    logger.warning(
                        f"Connection test failed, creating new connection: {e}"
                    )
                    # Connection is bad, create a new one
                    await conn.close()
                    self._connections_created -= 1

            # No available connections, create a new one
            conn = await self._create_connection()
            return conn

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Release a connection back to the pool."""
        async with self._lock:
            self._pool.append(conn)

    async def close(self) -> None:
        """
        Close the connection pool and wait for all connections to be returned.
        This method should be called during application shutdown to ensure
        proper cleanup of all database connections.
        """
        # First, wait for all connections to be returned to the pool
        # by checking if the pool size matches the total connections created
        max_wait_time = 30.0  # 30 seconds timeout
        wait_interval = 0.1   # 100ms between checks
        elapsed_time = 0.0

        while elapsed_time < max_wait_time:
            async with self._lock:
                if len(self._pool) == self._connections_created:
                    break  # All connections are back in the pool

            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        # Close all connections in the pool
        async with self._lock:
            while self._pool:
                conn = self._pool.popleft()
                try:
                    await conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            self._connections_created = 0
            logger.info("Async database connection pool closed properly")

    async def close_all(self) -> None:
        """Close all connections in the pool (immediate, may lose active connections)."""
        async with self._lock:
            while self._pool:
                conn = self._pool.popleft()
                try:
                    await conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            self._connections_created = 0
            logger.debug("All connections closed")

    def __del__(self) -> None:
        """Clean up connections when the pool is garbage collected."""
        # Note: This may not be reliable for async cleanup
        pass

    @property
    def size(self) -> int:
        """Current number of connections in the pool."""
        return len(self._pool)

    @property
    def total_connections(self) -> int:
        """Total number of connections created."""
        return self._connections_created
