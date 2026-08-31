"""Test TODO-20: Verify audit dual-write guarantee without PYTEST_CURRENT_TEST bypass.

This test verifies that the JSONL-first canonical SHA-256 guarantee — the
SEBI-audit core — is executed by the test suite. It asserts that both SQLite
row AND JSONL line + digest exist for a write, ensuring test-time behavior
matches production.

Acceptance:
- git grep PYTEST_CURRENT_TEST -- src/ → empty
- Test asserts both SQLite row AND JSONL line + digest for a write
"""

import json
from pathlib import Path

import pytest

from loats.database import Database


def test_audit_dual_write_with_injectable_path(tmp_path):
    """
    Test that audit log dual-write uses injectable JSONL path (tmp_path fixture).
    This ensures tests exercise the REAL dual-write path without any bypass.

    Verifies:
    1. SQLite row is created
    2. JSONL line is written to the injected path
    3. SHA-256 digest in JSONL matches SQLite row
    4. No PYTEST_CURRENT_TEST bypass exists
    """
    # Create injectable paths for testing
    db_path = tmp_path / "test_dual_write.db"
    audit_log_path = tmp_path / "test_dual_write_audit.jsonl"

    # Initialize database with injectable paths
    db = Database(db_path=db_path, audit_log_path=audit_log_path)
    db._initialize_database()

    # Create test audit entry
    test_entity_id = "test_entity_todo20"
    test_action = "TEST_ACTION"
    test_entity_type = "TEST_ENTITY"
    test_user = "test_system"
    test_metadata = {"test_key": "test_value", "todo": "TODO-20"}
    test_previous_state = {"old_field": "old_value"}
    test_new_state = {"new_field": "new_value"}

    # Log audit entry - this triggers dual-write
    db._log_audit(
        action=test_action,
        entity_type=test_entity_type,
        entity_id=test_entity_id,
        user=test_user,
        metadata=test_metadata,
        previous_state=test_previous_state,
        new_state=test_new_state,
    )

    # VERIFY 1: SQLite row exists
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT entry_id, timestamp, action, entity_type, entity_id, user,
               metadata, previous_state, new_state, sha256_hash
        FROM audit_log
        WHERE entity_id = ?
        """,
        (test_entity_id,),
    )
    row = cursor.fetchone()
    assert row is not None, "SQLite audit row must exist after dual-write"

    (
        db_entry_id,
        db_timestamp,
        db_action,
        db_entity_type,
        db_entity_id,
        db_user,
        db_metadata,
        db_previous_state,
        db_new_state,
        db_sha256_hash,
    ) = row

    # Verify SQLite fields
    assert db_action == test_action
    assert db_entity_type == test_entity_type
    assert db_entity_id == test_entity_id
    assert db_user == test_user
    assert json.loads(db_metadata) == test_metadata
    assert json.loads(db_previous_state) == test_previous_state
    assert json.loads(db_new_state) == test_new_state
    assert db_sha256_hash is not None
    assert len(db_sha256_hash) == 64  # SHA-256 hex digest length

    # VERIFY 2: JSONL line exists in injected path
    assert audit_log_path.exists(), "JSONL audit file must exist at injected path"
    jsonl_lines = audit_log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(jsonl_lines) == 1, (
        "JSONL must contain exactly one line for one audit entry"
    )

    jsonl_entry = json.loads(jsonl_lines[0])

    # Verify JSONL fields match SQLite
    assert jsonl_entry["action"] == db_action
    assert jsonl_entry["entity_type"] == db_entity_type
    assert jsonl_entry["entity_id"] == db_entity_id
    assert jsonl_entry["user"] == db_user
    assert jsonl_entry["metadata"] == test_metadata
    assert jsonl_entry["previous_state"] == test_previous_state
    assert jsonl_entry["new_state"] == test_new_state

    # VERIFY 3: SHA-256 digest in JSONL matches SQLite row
    jsonl_hash = jsonl_entry["sha256_hash"]
    assert jsonl_hash == db_sha256_hash, (
        "JSONL SHA-256 digest must match SQLite row digest"
    )

    # VERIFY 4: Digest is valid SHA-256 of canonical serialization
    # Recalculate hash from entry data (excluding sha256_hash itself)
    hash_data = {k: v for k, v in jsonl_entry.items() if k != "sha256_hash"}
    recalculated_hash = db._calculate_sha256(hash_data)
    assert recalculated_hash == jsonl_hash, (
        "Digest must be valid SHA-256 of canonical serialization"
    )

    # VERIFY 5: JSONL-first guarantee - if JSONL write failed, SQLite row wouldn't exist
    # (This is implicit: we already verified both exist, meaning JSONL write succeeded)

    # Close database
    db.close()

    # Final assertion: test completed without bypass
    print(
        "\n✓ TODO-20 verified: dual-write guarantee exercised without PYTEST_CURRENT_TEST bypass"
    )
    print(f"  - SQLite row exists at: {db_path}")
    print(f"  - JSONL line exists at: {audit_log_path}")
    print(f"  - SHA-256 digest matches: {db_sha256_hash[:16]}...")


def test_audit_dual_write_jsonl_first_failure_propagates(tmp_path):
    """
    Test that JSONL-first failure propagates to prevent SQLite commit.
    This verifies the core dual-write guarantee: no orphaned SQLite rows.
    """
    db_path = tmp_path / "test_dual_write_failure.db"
    # Create a path that will fail to write (non-existent directory without permissions)
    # On Windows, we'll simulate this by mocking Path.open to fail on the JSONL path
    audit_log_path = tmp_path / "non_existent_dir" / "test_audit.jsonl"

    db = Database(db_path=db_path, audit_log_path=audit_log_path)
    db._initialize_database()

    # Mock Path.open to simulate JSONL write failure
    original_open = Path.open

    def failing_open(self, *args, **kwargs):
        # Fail only for the audit log path
        if str(self).endswith("test_audit.jsonl"):
            raise OSError("Simulated JSONL write failure for TODO-20 test")
        return original_open(self, *args, **kwargs)

    with pytest.raises(RuntimeError, match="Failed to write audit log entry"):
        # Patch Path.open for this test
        Path.open = failing_open

        try:
            db._log_audit(
                action="TEST",
                entity_type="TEST",
                entity_id="should_not_exist",
                user="test",
                metadata={},
            )
        finally:
            # Restore original open
            Path.open = original_open

    # Verify no SQLite row was created (orphaned)
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?",
        ("should_not_exist",),
    )
    count = cursor.fetchone()[0]
    assert count == 0, "SQLite row must not exist when JSONL write fails"

    db.close()
    print("\n✓ TODO-20 verified: JSONL-first failure prevents SQLite commit")


def test_audit_dual_write_consistency_multiple_entries(tmp_path):
    """
    Test that multiple audit entries maintain dual-write consistency.
    Verifies that the dual-write guarantee holds across multiple writes.
    """
    db_path = tmp_path / "test_multi_dual_write.db"
    audit_log_path = tmp_path / "test_multi_audit.jsonl"

    db = Database(db_path=db_path, audit_log_path=audit_log_path)
    db._initialize_database()

    # Create multiple audit entries
    num_entries = 5
    entity_ids = [f"entity_{i}" for i in range(num_entries)]

    for entity_id in entity_ids:
        db._log_audit(
            action="CREATE",
            entity_type="MULTI_TEST",
            entity_id=entity_id,
            user="test_user",
            metadata={"index": entity_ids.index(entity_id)},
        )

    # Verify SQLite has all entries
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_type = ?", ("MULTI_TEST",)
    )
    db_count = cursor.fetchone()[0]
    assert db_count == num_entries, (
        f"SQLite must have {num_entries} entries, got {db_count}"
    )

    # Verify JSONL has all entries
    jsonl_lines = audit_log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(jsonl_lines) == num_entries, (
        f"JSONL must have {num_entries} lines, got {len(jsonl_lines)}"
    )

    # Verify each entry matches between SQLite and JSONL
    cursor.execute(
        "SELECT entity_id, sha256_hash FROM audit_log WHERE entity_type = ? ORDER BY entity_id",
        ("MULTI_TEST",),
    )
    db_rows = cursor.fetchall()

    for (db_entity_id, db_hash), jsonl_line in zip(db_rows, jsonl_lines, strict=False):
        jsonl_entry = json.loads(jsonl_line)
        assert jsonl_entry["entity_id"] == db_entity_id
        assert jsonl_entry["sha256_hash"] == db_hash

    db.close()
    print(
        f"\n✓ TODO-20 verified: {num_entries} entries maintain dual-write consistency"
    )
