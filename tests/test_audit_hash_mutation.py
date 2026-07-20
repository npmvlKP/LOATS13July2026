import json
from datetime import UTC, datetime

from src.loats.database import Database
from src.loats.models import AuditLogEntry


def test_canonical_serialization(db: Database):
    """
    Test that canonical serialization produces deterministic output.
    """
    # Test with datetime that has timezone info
    dt_with_tz = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    # Test with datetime without timezone info
    dt_without_tz = datetime(2024, 1, 15, 10, 30, 0)

    # Test with various data types
    data = {
        "timestamp": dt_with_tz,
        "another_timestamp": dt_without_tz,
        "string_field": "value",
        "number_field": 123.456,
        "none_field": None,
        "list_field": [1, 2, 3],
        "nested": {
            "key": "nested_value",
            "float": 0.0001,
        },
    }

    # Serialize twice - should produce identical results
    serialized1 = db._canonical_serialize(data)
    serialized2 = db._canonical_serialize(data)

    assert serialized1 == serialized2, "Canonical serialization should be deterministic"

    # Verify the serialized output is valid JSON
    parsed = json.loads(serialized1)
    assert parsed["timestamp"] == "2024-01-15T10:30:00Z"  # UTC normalized
    assert parsed["another_timestamp"] == "2024-01-15T10:30:00Z"  # UTC normalized
    assert parsed["string_field"] == "value"
    assert parsed["number_field"] == 123.456
    assert parsed["none_field"] is None


def test_canonical_hash_is_deterministic(db: Database):
    """
    Test that hash computation is deterministic across multiple calls.
    """
    dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
    data = {
        "timestamp": dt,
        "action": "CREATE",
        "entity_type": "test",
        "entity_id": "123",
    }

    hash1 = db._calculate_sha256(data)
    hash2 = db._calculate_sha256(data)

    assert hash1 == hash2, "Hash should be deterministic"
    assert len(hash1) == 64, "SHA-256 hash should be 64 hex characters"


def test_audit_log_hash_integrity(db: Database):
    """
    Test that audit log hash computation uses canonical serialization
    and is independent of Pydantic's internal serialization.
    """
    # Create an entry
    entry = AuditLogEntry(
        timestamp=datetime.now(UTC),
        action="TEST_ACTION",
        entity_type="TEST_ENTITY",
        entity_id="123",
        user="tester",
        metadata={"key": "value"},
    )

    # Get the model as dict (Pydantic serialization)
    entry_data = db._model_to_dict(entry)
    hash_data = {k: v for k, v in entry_data.items() if k != "sha256_hash"}

    # Calculate hash using the canonical method
    calculated_hash = db._calculate_sha256(hash_data)

    # Verify the hash field is not in the data being hashed
    assert "sha256_hash" not in hash_data

    # Set hash on entry
    entry.sha256_hash = calculated_hash

    # Re-serialize
    re_serialized_data = db._model_to_dict(entry)

    # Verify hash is in the re-serialized data
    assert "sha256_hash" in re_serialized_data
    assert re_serialized_data["sha256_hash"] == calculated_hash

    # Verify the hash can be recalculated from the data (excluding hash itself)
    check_data = {k: v for k, v in re_serialized_data.items() if k != "sha256_hash"}
    recalculated_hash = db._calculate_sha256(check_data)

    assert recalculated_hash == calculated_hash, "Hash should be reproducible after re-serialization"
    assert recalculated_hash == re_serialized_data["sha256_hash"], "Hash should match stored hash"

    print(f"\nCanonical Hash: {calculated_hash}")
    assert True


def test_hash_independence_from_pydantic_version(db: Database):
    """
    Test that the canonical serialization does not depend on Pydantic's
    internal serialization format.

    This test verifies that:
    1. Datetime values are normalized to ISO-8601 UTC format
    2. Float values are handled consistently
    3. Keys are sorted for deterministic output
    """
    # Simulate data that might come from Pydantic
    pydantic_data = {
        "timestamp": datetime(2024, 6, 15, 14, 30, 0, 123456, tzinfo=UTC),
        "action": "UPDATE",
        "entity_type": "position",
        "entity_id": "pos_001",
        "float_value": 123.456789012345,
        "nested": {
            "z_key": 1,
            "a_key": 2,
        },
    }

    # Serialize using canonical method
    canonical = db._canonical_serialize(pydantic_data)

    # Should produce sorted keys
    parsed = json.loads(canonical)
    keys = list(parsed.keys())
    assert keys == sorted(keys), "Keys should be sorted"

    # Verify datetime is in ISO-8601 format with Z suffix
    assert parsed["timestamp"] == "2024-06-15T14:30:00.123456Z"

    print(f"\nCanonical output: {canonical}")
    assert True
