#!/usr/bin/env python3
"""
Quick verification test for idempotency key functionality (without TTL test).
This test verifies that the idempotency key system is working correctly.
"""

import sys

sys.path.append("src")

from loats.openalgo import _get_idempotency_key, _order_payload_digest


def test_idempotency_key_generation():
    """Test that idempotency keys are generated correctly."""
    print("Testing idempotency key generation...")

    # Test 1: Same identity should return same key within TTL
    identity = "test_order_123"
    key1 = _get_idempotency_key(identity)
    key2 = _get_idempotency_key(identity)

    assert key1 == key2, f"Expected same key for same identity, got {key1} != {key2}"
    print(f"[OK] Same identity returns same key: {key1}")

    # Test 2: Different identities should return different keys
    identity2 = "test_order_456"
    key3 = _get_idempotency_key(identity2)

    assert key1 != key3, (
        f"Expected different keys for different identities, got {key1} == {key3}"
    )
    print(f"[OK] Different identities return different keys: {key1} != {key3}")

    # Test 3: Test payload digest function
    payload1 = {"symbol": "RELIANCE", "quantity": 10, "order_type": "MARKET"}
    payload2 = {"symbol": "RELIANCE", "quantity": 10, "order_type": "MARKET"}
    payload3 = {"symbol": "RELIANCE", "quantity": 20, "order_type": "MARKET"}

    digest1 = _order_payload_digest(payload1)
    digest2 = _order_payload_digest(payload2)
    digest3 = _order_payload_digest(payload3)

    assert digest1 == digest2, (
        f"Expected same digest for same payload, got {digest1} != {digest2}"
    )
    assert digest1 != digest3, (
        f"Expected different digest for different payload, got {digest1} == {digest3}"
    )
    print(
        "[OK] Payload digest works correctly: same payloads have same digest, different payloads have different digests"
    )

    print("All idempotency tests passed! [OK]")


if __name__ == "__main__":
    test_idempotency_key_generation()
