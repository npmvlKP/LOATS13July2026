"""
Test cases for vacuum and cleanup functionality in the Database class.
"""

import gc
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.loats.database import Database
from src.loats.models import Trade


def test_vacuum_method():
    """Test that the vacuum method works correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_loats.db"
        audit_log_path = Path(temp_dir) / "test_audit.log"

        # Create database instance
        db = Database(db_path, audit_log_path)
        db.retention_days = 7  # Set retention days directly

        # Initialize database
        db.initialize()

        # Test vacuum method
        try:
            db.vacuum()
            # If no exception, vacuum worked
            assert True
        except Exception as e:
            pytest.fail(f"Vacuum method failed: {e}")
        finally:
            db.close()
            del db
            gc.collect()


def test_cleanup_method():
    """Test that the cleanup method works correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_loats.db"
        audit_log_path = Path(temp_dir) / "test_audit.log"

        # Create database instance
        db = Database(db_path, audit_log_path)
        db.retention_days = 7  # Set retention days directly

        # Initialize database
        db.initialize()

        # Create test trades
        now = datetime.now()

        # Create old trade (older than retention)
        old_trade = Trade(
            trade_id="old_trade_1",
            symbol="TEST",
            quantity=25,
            entry_price=100.0,
            entry_time=now - timedelta(days=8),
            transaction_type="BUY",
            product_type="MIS",
            status="OPEN",
            strategy="test_strategy",
        )

        # Create recent trade
        recent_trade = Trade(
            trade_id="recent_trade_1",
            symbol="TEST",
            quantity=25,
            entry_price=100.0,
            entry_time=now,
            transaction_type="BUY",
            product_type="MIS",
            status="OPEN",
            strategy="test_strategy",
        )

        # Add trades to database
        db.create_trade(old_trade)
        db.create_trade(recent_trade)

        # Verify both trades exist
        old_trade_retrieved = db.get_trade("old_trade_1")
        recent_trade_retrieved = db.get_trade("recent_trade_1")

        assert old_trade_retrieved is not None
        assert recent_trade_retrieved is not None

        # Test cleanup method
        try:
            db.cleanup()
        except Exception as e:
            pytest.fail(f"Cleanup method failed: {e}")
        else:
            # Verify old trade was deleted and recent trade still exists
            old_trade_after = db.get_trade("old_trade_1")
            recent_trade_after = db.get_trade("recent_trade_1")

            assert old_trade_after is None, "Old trade should have been deleted"
            assert recent_trade_after is not None, "Recent trade should still exist"
        finally:
            db.close()
            del db
            gc.collect()


def test_vacuum_and_cleanup_together():
    """Test that vacuum and cleanup work together correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_loats.db"
        audit_log_path = Path(temp_dir) / "test_audit.log"

        # Create database instance
        db = Database(db_path, audit_log_path)
        db.retention_days = 7  # Set retention days directly

        # Initialize database
        db.initialize()

        # Create test trades
        now = datetime.now()

        # Create old trade (older than retention)
        old_trade = Trade(
            trade_id="old_trade_1",
            symbol="TEST",
            quantity=25,
            entry_price=100.0,
            entry_time=now - timedelta(days=8),
            transaction_type="BUY",
            product_type="MIS",
            status="OPEN",
            strategy="test_strategy",
        )

        # Create recent trade
        recent_trade = Trade(
            trade_id="recent_trade_1",
            symbol="TEST",
            quantity=25,
            entry_price=100.0,
            entry_time=now,
            transaction_type="BUY",
            product_type="MIS",
            status="OPEN",
            strategy="test_strategy",
        )

        # Add trades to database
        db.create_trade(old_trade)
        db.create_trade(recent_trade)

        # Test both methods
        try:
            db.vacuum()
            db.cleanup()
        except Exception as e:
            pytest.fail(f"Vacuum or cleanup failed: {e}")
        else:
            # Verify cleanup worked
            old_trade_after = db.get_trade("old_trade_1")
            recent_trade_after = db.get_trade("recent_trade_1")

            assert old_trade_after is None, "Old trade should have been deleted"
            assert recent_trade_after is not None, "Recent trade should still exist"
        finally:
            db.close()
            del db
            gc.collect()
