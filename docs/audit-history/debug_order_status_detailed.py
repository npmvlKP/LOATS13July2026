#!/usr/bin/env python3
"""Detailed debug script to understand the test_async_update_order_status failure."""

import asyncio
import tempfile
from pathlib import Path

from loats.database import Database
from loats.database_async_additions import extend_database_class


async def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()

        # Ensure async methods are extended
        extend_database_class()

        # Initialize async pool
        await db.async_initialize()

        # Manually test the query inside the async function
        print("Testing query manually...")
        conn = await db._async_pool.acquire()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT 1 FROM orders WHERE order_id = ?", ("nonexistent_order",)
                )
                row = await cursor.fetchone()
                print(f"Row from SELECT: {row}")
                print(f"Row is None: {row is None}")
                print(f"Row is not None: {row is not None}")
        finally:
            await db._async_pool.release(conn)

        # Now test the actual async_update_order_status function
        print("\nTesting async_update_order_status...")
        result = await db.async_update_order_status("nonexistent_order", "COMPLETED")
        print(f"Result: {result}")
        print(f"Expected: False")

        # Clean up
        if hasattr(db, "_async_pool") and db._async_pool:
            await db.async_close_all()
        db.close_all()


if __name__ == "__main__":
    asyncio.run(main())
