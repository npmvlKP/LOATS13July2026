"""F9-M-01-R2: repair-tool backup fidelity (R-15).

The 29Sep R-15 finding: ``scripts/repair_f9m01_chain_head.py`` mutated the
in-memory entry list (``reanchor_span``) BEFORE ``write_repaired_log``
serialized the same list to the file named ``*.f9m01r1-backup`` — so the
"backup" held the REPAIRED content, not the pre-repair state. Both real
runs (24Sep, 29Sep) wrote repaired-content backups; the docstring's
"snapshots the audit log before mutating" was false for the JSONL leg
(the SQLite DB snapshot is genuine — taken before ``repair_db``).

Pins (fixture = healthy 3-entry chain + one frozen-head entry):
1. the JSONL backup must contain the pre-repair broken link (≥1) and
   must not contain the REPAIR record;
2. re-anchoring the BACKUP must reproduce the repaired file's hashes
   (the backup is sufficient to redo the repair);
3. the DB backup must hold the PRE-repair row hash for the re-anchored
   entry (regression pin for behaviour that was already correct);
4. dry-run writes nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "repair_f9m01_chain_head.py"
_spec = importlib.util.spec_from_file_location("_repair_f9m01", _SCRIPT)
assert _spec is not None and _spec.loader is not None
repair = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_repair_f9m01", repair)
_spec.loader.exec_module(repair)

FROZEN_HEAD = "f" * 64


def _hash_entry(entry: dict[str, object]) -> str:
    data = {k: v for k, v in entry.items() if k != "sha256_hash"}
    import hashlib

    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def _entry(idx: int, previous_hash: str | None) -> dict[str, object]:
    entry: dict[str, object] = {
        "entry_id": f"audit_test_{idx:04d}",
        "timestamp": f"2026-09-29T10:00:{idx:02d}.000000+00:00",
        "action": "REJECT",
        "entity_type": "signal_batch",
        "entity_id": f"batch_{idx:04d}",
        "user": "trade_decision_engine",
        "metadata": {"seq": idx},
        "previous_state": {},
        "new_state": {},
        "timestamp_ms": 1780000000000 + idx,
        "previous_hash": previous_hash,
    }
    entry["sha256_hash"] = _hash_entry(entry)
    return entry


def _walk_breaks(text: str) -> int:
    prev: str | None = None
    broken = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        ph = d.get("previous_hash")
        if ph is not None and ph != prev:
            broken += 1
        prev = d.get("sha256_hash")
    return broken


@pytest.fixture()
def damaged(tmp_path: Path) -> tuple[Path, Path, str]:
    """audit.jsonl with entries 0-2 healthy and 3 frozen at an earlier hash."""
    h0 = _hash_entry(e0 := _entry(0, None))
    h1 = _hash_entry(e1 := _entry(1, h0))
    e2 = _entry(2, h1)
    e3 = _entry(3, FROZEN_HEAD)  # frozen link must point at a REAL hash
    e3["previous_hash"] = h1
    e3["sha256_hash"] = _hash_entry(e3)
    log = tmp_path / "audit.jsonl"
    log.write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in (e0, e1, e2, e3)),
        encoding="utf-8",
    )
    db = tmp_path / "loats.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE audit_log (
            entry_id TEXT PRIMARY KEY, timestamp TEXT, action TEXT,
            entity_type TEXT, entity_id TEXT, user TEXT, metadata TEXT,
            previous_state TEXT, new_state TEXT, sha256_hash TEXT,
            timestamp_ms INTEGER, previous_hash TEXT)"""
    )
    for e in (e0, e1, e2, e3):
        conn.execute(
            "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(e["entry_id"]),
                str(e["timestamp"]),
                str(e["action"]),
                str(e["entity_type"]),
                str(e["entity_id"]),
                str(e["user"]),
                json.dumps(e["metadata"]),
                None,
                None,
                str(e["sha256_hash"]),
                int(e["timestamp_ms"]),  # type: ignore[arg-type]
                e.get("previous_hash"),
            ),
        )
    conn.commit()
    conn.close()
    return log, db, str(e3["sha256_hash"])


def _run_apply(log: Path, db: Path) -> int:
    argv = sys.argv
    sys.argv = [
        "repair_f9m01_chain_head.py",
        "--db",
        str(db),
        "--audit-log",
        str(log),
        "--apply",
    ]
    try:
        return repair.main()
    finally:
        sys.argv = argv


def test_jsonl_backup_holds_pre_repair_state(damaged) -> None:
    log, db, old_hash = damaged
    assert _run_apply(log, db) == 0
    backup = log.with_suffix(log.suffix + ".f9m01r1-backup")
    assert backup.exists(), "repair must write a JSONL backup"
    backup_text = backup.read_text(encoding="utf-8")
    assert _walk_breaks(backup_text) >= 1, (
        "R-15: the backup must contain the PRE-repair broken link; a "
        "backup identical to the repaired content cannot restore or "
        "re-derive the pre-repair state"
    )
    assert "REPAIR" not in backup_text, (
        "the backup predates the repair record and must not contain it"
    )
    repaired_text = log.read_text(encoding="utf-8")
    assert _walk_breaks(repaired_text) == 0
    assert "REPAIR" in repaired_text


def test_backup_roundtrips_to_the_repaired_result(damaged) -> None:
    log, db, _old_hash = damaged
    assert _run_apply(log, db) == 0
    backup = log.with_suffix(log.suffix + ".f9m01r1-backup")
    entries = repair.load_entries(backup)
    span_start, _stats = repair.plan_repair(entries)
    assert span_start >= 0
    repair.reanchor_span(entries, span_start)
    re_derived = [repair._entry_hash(e) for e in entries]
    repaired_lines = log.read_text(encoding="utf-8").splitlines()
    repaired_hashes = [
        json.loads(ln)["sha256_hash"]
        for ln in repaired_lines
        if json.loads(ln).get("action") != "REPAIR"
    ]
    assert re_derived == repaired_hashes, (
        "the pre-repair backup must be sufficient to re-derive the repair"
    )


def test_db_backup_is_genuine_pre_repair_snapshot(damaged) -> None:
    log, db, old_hash = damaged
    assert _run_apply(log, db) == 0
    db_backup = db.with_suffix(db.suffix + ".f9m01r1-backup")
    conn = sqlite3.connect(str(db_backup))
    row = conn.execute(
        "SELECT sha256_hash FROM audit_log WHERE entry_id = ?",
        ("audit_test_0003",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == old_hash, (
        "the DB backup must hold the PRE-repair hash for the re-anchored row"
    )


def test_dry_run_writes_nothing(damaged, capsys: pytest.CaptureFixture[str]) -> None:
    log, db, _old_hash = damaged
    before = log.read_text(encoding="utf-8")
    argv = sys.argv
    sys.argv = ["repair_f9m01_chain_head.py", "--db", str(db), "--audit-log", str(log)]
    try:
        assert repair.main() == 0
    finally:
        sys.argv = argv
    assert log.read_text(encoding="utf-8") == before
    assert not log.with_suffix(log.suffix + ".f9m01r1-backup").exists()
    capsys.readouterr()
