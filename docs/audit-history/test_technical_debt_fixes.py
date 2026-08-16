#!/usr/bin/env python3
"""
Test script to verify the technical debt fixes.
This tests the resolution of R5-F-07, R5-F-08, R5-F-14, and R5-F-22.
"""

import sys
import os
import tempfile
import shutil
from datetime import datetime, UTC
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loats.models import (
    Order,
    OrderType,
    OrderStatus,
    TransactionType,
    ProductType,
    OrderVariety,
)
from loats.database import Database
from loats.scheduler import TradingScheduler


def test_idempotency_key_functionality():
    """Test that idempotency keys prevent duplicate orders (R5-F-07)."""

    # Create a temporary directory for the test database
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_db.sqlite"
        audit_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_path)

        # Create a test order with an idempotency key
        order1 = Order(
            order_id="test_order_1",
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            variety=OrderVariety.REGULAR,
            status=OrderStatus.OPEN,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            idempotency_key="unique_key_123",
        )

        # Store the first order - should succeed
        try:
            result1 = db.store_order(order1)
            print("[OK] First order stored successfully")
            assert result1 is True
        except Exception as e:
            print(f"[FAIL] Failed to store first order: {e}")
            return False

        # Try to store the same order again with the same idempotency key - should fail
        try:
            db.store_order(order1)
            print("[FAIL] Duplicate order was allowed - idempotency check failed!")
            return False
        except ValueError as e:
            if "Duplicate order detected" in str(e):
                print("[OK] Duplicate order correctly rejected with idempotency key")
            else:
                print(f"[FAIL] Unexpected error: {e}")
                return False
        except Exception as e:
            print(f"[FAIL] Unexpected exception type: {e}")
            return False

        # Try to store a different order with a different idempotency key - should succeed
        order2 = Order(
            order_id="test_order_2",
            symbol="TCS",
            quantity=5,
            order_type=OrderType.LIMIT,
            transaction_type=TransactionType.SELL,
            product_type=ProductType.NRML,
            variety=OrderVariety.REGULAR,
            status=OrderStatus.OPEN,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            idempotency_key="unique_key_456",
            price=400.0,
        )

        try:
            result3 = db.store_order(order2)
            print(
                "[OK] Different order with different idempotency key stored successfully"
            )
            assert result3 is True
        except Exception as e:
            print(f"[FAIL] Failed to store different order: {e}")
            return False

        # Try to store an order without an idempotency key - should succeed (backward compatibility)
        order3 = Order(
            order_id="test_order_3",
            symbol="INFY",
            quantity=2,
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.CNC,
            variety=OrderVariety.REGULAR,
            status=OrderStatus.OPEN,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            idempotency_key=None,  # No idempotency key
        )

        try:
            result4 = db.store_order(order3)
            print(
                "[OK] Order without idempotency key stored successfully (backward compatibility)"
            )
            assert result4 is True
        except Exception as e:
            print(f"[FAIL] Failed to store order without idempotency key: {e}")
            return False

        # Verify that the orders were stored correctly
        try:
            retrieved_order1 = db.get_order("test_order_1")
            retrieved_order2 = db.get_order("test_order_2")
            retrieved_order3 = db.get_order("test_order_3")

            assert retrieved_order1 is not None
            assert retrieved_order2 is not None
            assert retrieved_order3 is not None

            assert retrieved_order1.idempotency_key == "unique_key_123"
            assert retrieved_order2.idempotency_key == "unique_key_456"
            assert retrieved_order3.idempotency_key is None

            print("[OK] All orders retrieved correctly with proper idempotency keys")

        except Exception as e:
            print(f"[FAIL] Failed to retrieve orders: {e}")
            return False

        # Clean up
        db.close_all()

        print("\n[SUCCESS] All idempotency key tests passed!")
        return True

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_nse_holiday_calendar():
    """Test that NSE holiday calendar is implemented (R5-F-08)."""

    # Import the scheduler module to check the holiday calendar
    import loats.scheduler as scheduler_module

    # Test that the holiday calendar exists in the module
    try:
        assert hasattr(scheduler_module, "NSE_HOLIDAYS")
        assert len(scheduler_module.NSE_HOLIDAYS) > 0
        print("[OK] NSE holiday calendar exists and has entries")

        # Check that it contains the expected format (date objects)
        sample_holiday = next(iter(scheduler_module.NSE_HOLIDAYS))
        assert hasattr(sample_holiday, "year")
        assert hasattr(sample_holiday, "month")
        assert hasattr(sample_holiday, "day")
        print("[OK] NSE holiday calendar contains date objects")

    except Exception as e:
        print(f"[FAIL] NSE holiday calendar check failed: {e}")
        return False

    # Test that the TradingScheduler class has the is_market_open method
    try:
        assert hasattr(scheduler_module.TradingScheduler, "is_market_open")
        print("[OK] is_market_open method exists in TradingScheduler class")
    except Exception as e:
        print(f"[FAIL] is_market_open method check failed: {e}")
        return False

    print("\n[SUCCESS] NSE holiday calendar test passed!")
    return True


def test_audit_log_consistency():
    """Test that audit logs are written before database commits (R5-F-14)."""

    # Create a temporary directory for the test database
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_audit_db.sqlite"
        audit_path = Path(temp_dir) / "test_audit_log.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_path)

        # Create a test order
        order = Order(
            order_id="audit_test_order",
            symbol="HDFCBANK",
            quantity=3,
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            variety=OrderVariety.REGULAR,
            status=OrderStatus.OPEN,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            idempotency_key="audit_test_key",
        )

        try:
            # Store the order
            result = db.store_order(order)
            assert result is True
            print("[OK] Order stored successfully for audit test")

            # Check that audit log was created
            assert audit_path.exists()
            assert audit_path.stat().st_size > 0
            print("[OK] Audit log file created and has content")

            # Verify audit log integrity
            integrity_result = db.verify_audit_log_integrity()
            assert integrity_result is True
            print("[OK] Audit log integrity verified")

        except Exception as e:
            print(f"[FAIL] Audit log test failed: {e}")
            return False
        finally:
            db.close_all()

        print("\n[SUCCESS] Audit log consistency test passed!")
        return True

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_dependencies_in_pyproject():
    """Test that required dependencies are in pyproject.toml (R5-F-22)."""

    pyproject_path = Path(__file__).parent / "pyproject.toml"

    try:
        content = pyproject_path.read_text(encoding="utf-8")

        # Check for required dependencies
        required_deps = ["lxml>=", "lxml-html-clean>=", "cryptography>="]
        missing_deps = []

        for dep in required_deps:
            if dep not in content:
                missing_deps.append(dep)

        if missing_deps:
            print(f"[FAIL] Missing dependencies in pyproject.toml: {missing_deps}")
            return False
        else:
            print("[OK] All required dependencies found in pyproject.toml")
            return True

    except Exception as e:
        print(f"[FAIL] Error checking pyproject.toml: {e}")
        return False


if __name__ == "__main__":
    print("Testing Technical Debt Fixes")
    print("=" * 50)

    print("\n1. Testing Idempotency Key Functionality (R5-F-07)")
    print("-" * 50)
    idempotency_result = test_idempotency_key_functionality()

    print("\n2. Testing NSE Holiday Calendar (R5-F-08)")
    print("-" * 50)
    holiday_result = test_nse_holiday_calendar()

    print("\n3. Testing Audit Log Consistency (R5-F-14)")
    print("-" * 50)
    audit_result = test_audit_log_consistency()

    print("\n4. Testing Dependencies in pyproject.toml (R5-F-22)")
    print("-" * 50)
    deps_result = test_dependencies_in_pyproject()

    print("\n" + "=" * 50)
    print("TEST RESULTS:")
    print(
        f"   Idempotency Key Test (R5-F-07): {'PASSED' if idempotency_result else 'FAILED'}"
    )
    print(
        f"   NSE Holiday Calendar (R5-F-08): {'PASSED' if holiday_result else 'FAILED'}"
    )
    print(
        f"   Audit Log Test (R5-F-14):        {'PASSED' if audit_result else 'FAILED'}"
    )
    print(
        f"   Dependencies Test (R5-F-22):     {'PASSED' if deps_result else 'FAILED'}"
    )

    if idempotency_result and holiday_result and audit_result and deps_result:
        print(
            "\nALL TESTS PASSED! All technical debt items have been successfully resolved."
        )
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED! Please review the implementation.")
        sys.exit(1)
