#!/usr/bin/env python3
"""
Test script to verify the audit log dual-write consistency fix.
This test verifies that the fix for R5-F-14 works correctly.
"""

import tempfile
from pathlib import Path
import json
from datetime import datetime, timezone, UTC
import sqlite3

# Add the src directory to the path so we can import the Database class
import sys

sys.path.insert(0, "src")

from loats.database import Database
from loats.models import Trade, TransactionType, ProductType


def test_audit_log_dual_write_consistency():
    """Test that audit log dual-write maintains consistency."""

    # Create temporary database and audit log files
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_log_path)

        # Create a test trade
        trade = Trade(
            trade_id="test_trade_123",
            symbol="TEST",
            quantity=10,
            entry_price=100.0,
            exit_price=110.0,
            entry_time=datetime.now(UTC),
            exit_time=datetime.now(UTC),
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=100.0,
            status="COMPLETED",
            strategy="test_strategy",
        )

        # Test successful audit log write
        print("Testing successful audit log write...")
        db.create_trade(trade)

        # Verify both audit trails exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_trade_123",)
        )
        db_count = cursor.fetchone()[0]
        conn.close()

        # Check JSONL file
        with open(audit_log_path, "r", encoding="utf-8") as f:
            jsonl_lines = f.readlines()

        jsonl_count = sum(1 for line in jsonl_lines if "test_trade_123" in line)

        print(f"Database audit entries: {db_count}")
        print(f"JSONL audit entries: {jsonl_count}")

        assert db_count == 1, f"Expected 1 DB audit entry, got {db_count}"
        assert jsonl_count == 1, f"Expected 1 JSONL audit entry, got {jsonl_count}"

        # Test JSONL write failure scenario
        print("\nTesting JSONL write failure scenario...")

        # Make audit log file read-only to simulate write failure
        Path(audit_log_path).chmod(0o444)  # Read-only

        try:
            # This should raise an exception due to JSONL write failure
            trade2 = Trade(
                trade_id="test_trade_456",
                symbol="TEST2",
                quantity=5,
                entry_price=50.0,
                exit_price=55.0,
                entry_time=datetime.now(UTC),
                exit_time=datetime.now(UTC),
                transaction_type=TransactionType.SELL,
                product_type=ProductType.NRML,
                pnl=25.0,
                status="COMPLETED",
                strategy="test_strategy_2",
            )

            try:
                db.create_trade(trade2)
                raise AssertionError("Expected RuntimeError due to JSONL write failure")
            except RuntimeError as e:
                print(f"[+] Correctly caught expected error: {e}")
                assert "Failed to write audit log entry to JSONL file" in str(e)
                assert "Database commit aborted to maintain consistency" in str(e)

        finally:
            # Restore write permissions
            Path(audit_log_path).chmod(0o644)

        # Verify that no partial audit trail was created
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_trade_456",)
        )
        db_count_after_failure = cursor.fetchone()[0]
        conn.close()

        with open(audit_log_path, "r", encoding="utf-8") as f:
            jsonl_lines_after = f.readlines()

        jsonl_count_after = sum(
            1 for line in jsonl_lines_after if "test_trade_456" in line
        )

        print(f"Database audit entries after failure: {db_count_after_failure}")
        print(f"JSONL audit entries after failure: {jsonl_count_after}")

        assert (
            db_count_after_failure == 0
        ), f"Expected 0 DB audit entries after failure, got {db_count_after_failure}"
        assert (
            jsonl_count_after == 0
        ), f"Expected 0 JSONL audit entries after failure, got {jsonl_count_after}"

        print("✓ Dual-write consistency maintained - no partial audit trails created")

        # Test successful write after recovery
        print("\nTesting successful write after recovery...")
        trade3 = Trade(
            trade_id="test_trade_789",
            symbol="TEST3",
            quantity=15,
            entry_price=75.0,
            exit_price=80.0,
            entry_time=datetime.now(UTC),
            exit_time=datetime.now(UTC),
            transaction_type=TransactionType.BUY,
            product_type=ProductType.CNC,
            pnl=75.0,
            status="COMPLETED",
            strategy="test_strategy_3",
        )

        db.create_trade(trade3)

        # Verify both audit trails were created successfully
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_trade_789",)
        )
        db_count_recovery = cursor.fetchone()[0]
        conn.close()

        with open(audit_log_path, "r", encoding="utf-8") as f:
            jsonl_lines_recovery = f.readlines()

        jsonl_count_recovery = sum(
            1 for line in jsonl_lines_recovery if "test_trade_789" in line
        )

        print(f"Database audit entries after recovery: {db_count_recovery}")
        print(f"JSONL audit entries after recovery: {jsonl_count_recovery}")

        assert (
            db_count_recovery == 1
        ), f"Expected 1 DB audit entry after recovery, got {db_count_recovery}"
        assert (
            jsonl_count_recovery == 1
        ), f"Expected 1 JSONL audit entry after recovery, got {jsonl_count_recovery}"

        print("✓ Recovery successful - both audit trails created consistently")

        db.close()
        print(
            "\n✅ All tests passed! Audit log dual-write consistency fix is working correctly."
        )


if __name__ == "__main__":
    test_audit_log_dual_write_consistency()
