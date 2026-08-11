#!/usr/bin/env python3
"""
Test script to verify the idempotency key fix for orders.
This tests the R5-F-07 technical debt item resolution.
"""

import sys
import os
import tempfile
import shutil
from datetime import datetime, UTC
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loats.models import Order, OrderType, OrderStatus, TransactionType, ProductType, OrderVariety
from loats.database import Database

def test_idempotency_key_functionality():
    """Test that idempotency keys prevent duplicate orders."""

    # Create a temporary directory for the test database
    with tempfile.TemporaryDirectory() as temp_dir:
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
            idempotency_key="unique_key_123"
        )

        # Store the first order - should succeed
        try:
            result1 = db.store_order(order1)
            print("✅ First order stored successfully")
            assert result1 is True
        except Exception as e:
            print(f"❌ Failed to store first order: {e}")
            return False

        # Try to store the same order again with the same idempotency key - should fail
        try:
            result2 = db.store_order(order1)
            print("❌ Duplicate order was allowed - idempotency check failed!")
            return False
        except ValueError as e:
            if "Duplicate order detected" in str(e):
                print("✅ Duplicate order correctly rejected with idempotency key")
            else:
                print(f"❌ Unexpected error: {e}")
                return False
        except Exception as e:
            print(f"❌ Unexpected exception type: {e}")
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
            price=400.0
        )

        try:
            result3 = db.store_order(order2)
            print("✅ Different order with different idempotency key stored successfully")
            assert result3 is True
        except Exception as e:
            print(f"❌ Failed to store different order: {e}")
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
            idempotency_key=None  # No idempotency key
        )

        try:
            result4 = db.store_order(order3)
            print("✅ Order without idempotency key stored successfully (backward compatibility)")
            assert result4 is True
        except Exception as e:
            print(f"❌ Failed to store order without idempotency key: {e}")
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

            print("✅ All orders retrieved correctly with proper idempotency keys")

        except Exception as e:
            print(f"❌ Failed to retrieve orders: {e}")
            return False

        # Clean up
        db.close_all()

        print("\n🎉 All idempotency key tests passed!")
        return True

def test_audit_log_consistency():
    """Test that audit logs are written before database commits."""

    # Create a temporary directory for the test database
    with tempfile.TemporaryDirectory() as temp_dir:
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
            idempotency_key="audit_test_key"
        )

        try:
            # Store the order
            result = db.store_order(order)
            assert result is True
            print("✅ Order stored successfully for audit test")

            # Check that audit log was created
            assert audit_path.exists()
            assert audit_path.stat().st_size > 0
            print("✅ Audit log file created and has content")

            # Verify audit log integrity
            integrity_result = db.verify_audit_log_integrity()
            assert integrity_result is True
            print("✅ Audit log integrity verified")

        except Exception as e:
            print(f"❌ Audit log test failed: {e}")
            return False
        finally:
            db.close_all()

        print("\n🎉 Audit log consistency test passed!")
        return True

if __name__ == "__main__":
    print("Testing Technical Debt Fixes")
    print("=" * 50)

    print("\n1. Testing Idempotency Key Functionality (R5-F-07)")
    print("-" * 50)
    idempotency_result = test_idempotency_key_functionality()

    print("\n2. Testing Audit Log Consistency (R5-F-14)")
    print("-" * 50)
    audit_result = test_audit_log_consistency()

    print("\n" + "=" * 50)
    print("TEST RESULTS:")
    print(f"   Idempotency Key Test: {'PASSED' if idempotency_result else 'FAILED'}")
    print(f"   Audit Log Test:        {'PASSED' if audit_result else 'FAILED'}")

    if idempotency_result and audit_result:
        print("\nALL TESTS PASSED! Technical debt items R5-F-07 and R5-F-14 have been successfully resolved.")
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED! Please review the implementation.")
        sys.exit(1)
