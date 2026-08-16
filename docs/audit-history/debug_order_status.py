#!/usr/bin/env python3
"""Debug script to understand the test_async_update_order_status failure."""

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

        # Check if orders table exists and has any data
        conn = db._get_connection()
        cursor = conn.cursor()

        # Check if orders table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
        )
        table_exists = cursor.fetchone() is not None
        print(f"Orders table exists: {table_exists}")

        if table_exists:
            # Count orders
            cursor.execute("SELECT COUNT(*) FROM orders")
            count = cursor.fetchone()[0]
            print(f"Number of orders in database: {count}")

            # List all orders
            cursor.execute("SELECT order_id, status FROM orders")
            orders = cursor.fetchall()
            print(f"Orders: {orders}")
        else:
            print("Orders table does NOT exist!")

        conn.close()

        # Now test the async update function
        print("\nTesting async_update_order_status with nonexistent_order...")
        result = await db.async_update_order_status("nonexistent_order", "COMPLETED")
        print(f"Result: {result}")
        print("Expected: False")

        # Clean up
        if hasattr(db, "_async_pool") and db._async_pool:
            await db.async_close_all()
        db.close_all()


if __name__ == "__main__":
    asyncio.run(main())
