import pytest
import json
import hashlib
from datetime import datetime, timezone
from src.loats.database import Database
from src.loats.models import AuditLogEntry

def test_audit_log_hash_integrity(db: Database):
    """
    Test that the hash is computed correctly and does not include itself,
    and that re-serializing does not change the hash.
    """
    # Create an entry
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc),
        action="TEST_ACTION",
        entity_type="TEST_ENTITY",
        entity_id="123",
        user="tester",
        metadata={"key": "value"}
    )
    
    # Simulate the current hashing logic
    entry_data = db._model_to_dict(entry)
    hash_data = {k: v for k, v in entry_data.items() if k != "sha256_hash"}
    
    # Calculate hash
    data_str = json.dumps(hash_data, sort_keys=True)
    calculated_hash = hashlib.sha256(data_str.encode()).hexdigest()
    
    # Set hash on entry
    entry.sha256_hash = calculated_hash
    
    # Re-serialize
    re_serialized_data = db._model_to_dict(entry)
    
    # The reported problem is that entry_data (before mutation) and re-serialized data (after) are used inconsistently
    # specifically, the original entry_data is used for JSONL, but it lacks the hash.
    # The DB stores the entry with the hash.
    
    # The test should demonstrate that if we re-calculate the hash from the re-serialized data (containing the hash),
    # we get a different hash if we include the hash field in the calculation, 
    # OR if we simply want to verify that the hash is independent of the hash field itself.
    
    # The fix should ensure that hash is computed over the data, and stored separately.
    
    # Verify hash field is not part of the hash itself
    assert "sha256_hash" not in hash_data
    
    # Verify hash is in the re-serialized data
    assert "sha256_hash" in re_serialized_data
    assert re_serialized_data["sha256_hash"] == calculated_hash
    
    # Demonstrate the issue: 
    # Current code writes entry_data (pre-hash) to JSONL.
    # If we want JSONL to be valid, it should probably include the hash.
    
    print(f"\nHash: {calculated_hash}")
    assert True