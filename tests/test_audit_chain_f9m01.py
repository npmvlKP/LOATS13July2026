"""F9-M-01 (TODO-6): audit trail is self-hashed, NOT chained -- remediation.

FR9 finding (docs/audit-history/15Sep2026-FR9-forensic-review-report.md):
``verify_audit_log_integrity`` re-computes each entry's own hash, so an
attacker (or accident) that DELETES or REORDERS entries and recomputes the
affected self-hashes is undetectable -- the README's "SHA-256 chained"
claim (README:163) was plan-level only. Remediation per TODO-6:

- ``previous_hash`` column on ``audit_log`` (appended LAST in both the
  fresh CREATE TABLE and the ALTER migration, mirroring the F8-L-02
  positional-index contract so fresh and migrated schemas agree).
- Hash = sha256(canonical entry INCLUDING previous_hash); each JSONL line
  and DB row carries the chain link.
- The verifier walks links IN FILE ORDER: a broken link => FAIL + CRITICAL
  alert. Legacy entries without the ``previous_hash`` key are grandfathered
  (self-hash only); the first post-migration entry seeds the chain at the
  legacy head (its ``previous_hash`` == the last legacy entry's hash).

P5 span safety: this wave touches the audit WRITE path. The migration is
an idempotent ALTER TABLE ADD COLUMN applied by the standard init path --
for the live ``data/loats.db`` it only ever runs at a Database
construction (post-30Sep restart); legacy rows keep ``previous_hash``
NULL and remain fully verifiable under the grandfathered rule.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from loats.database import Database


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Database bound to an insulated temp store (never the live DB)."""
    return Database(
        db_path=tmp_path / "chain.db",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _write_entries(db: Database, count: int) -> None:
    for i in range(count):
        db.log_audit(
            action="CREATE",
            entity_type="trade",
            entity_id=f"t{i}",
            metadata={"i": i},
        )


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rewrite_lines(path: Path, entries: list[dict]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


class TestChainWritePath:
    def test_new_entries_chain_in_file_order(
        self, db: Database, tmp_path: Path
    ) -> None:
        _write_entries(db, 3)
        entries = _read_lines(tmp_path / "audit.jsonl")
        assert len(entries) == 3
        assert "previous_hash" in entries[0]
        assert entries[0]["previous_hash"] is None  # fresh file: no head
        assert entries[1]["previous_hash"] == entries[0]["sha256_hash"]
        assert entries[2]["previous_hash"] == entries[1]["sha256_hash"]

    def test_db_rows_carry_previous_hash(self, db: Database) -> None:
        _write_entries(db, 2)
        rows = db.get_audit_log()
        # Root cause of a CI-only flake: get_audit_log() returns rows
        # timestamp-DESC, and timestamps round-trip at millisecond
        # precision -- same-millisecond writes are a DESC tie that the
        # stable ascending sort below preserves as insertion-REVERSED.
        # Identify entries by the unique entity_id each write carries
        # (wall-clock ordering is not the invariant under test); first
        # entry = no head seed, second links at the first's self-hash.
        by_entity = {r.entity_id: r for r in rows}
        assert set(by_entity) == {"t0", "t1"}
        assert by_entity["t0"].previous_hash is None
        assert by_entity["t1"].previous_hash == by_entity["t0"].sha256_hash

    def test_entry_hash_includes_previous_hash(
        self, db: Database, tmp_path: Path
    ) -> None:
        """The chain is genuine: entry i's own hash covers entry i-1's
        hash (removing the link field breaks the self-hash check).

        Re-computation targets the JSONL line -- the same surface the
        verifier walks (the DB row round-trips timestamp_ms, which
        truncates sub-millisecond precision by design)."""
        _write_entries(db, 2)
        lines = _read_lines(tmp_path / "audit.jsonl")
        second_line = lines[1]
        data = dict(second_line)
        data.pop("sha256_hash")
        assert db._calculate_sha256(data) == second_line["sha256_hash"]
        # And the link is load-bearing: strip previous_hash from the
        # hashed payload and the self-hash no longer matches.
        linked = dict(data)
        linked.pop("previous_hash")
        assert db._calculate_sha256(linked) != second_line["sha256_hash"]

    def test_first_entry_after_legacy_seeds_at_head(
        self, db: Database, tmp_path: Path
    ) -> None:
        """Migration seeds at the current head: a legacy prefix (entries
        without previous_hash) is extended by a chained entry whose link
        points at the last legacy hash."""
        legacy_line = json.dumps(
            {
                "entry_id": "audit_legacy1",
                "timestamp": "2026-09-01T10:00:00Z",
                "action": "CREATE",
                "entity_type": "trade",
                "entity_id": "legacy",
                "user": "system",
                "metadata": {},
                "previous_state": None,
                "new_state": None,
                "sha256_hash": "deadbeef" * 8,
            }
        )
        (tmp_path / "audit.jsonl").write_text(legacy_line + "\n", encoding="utf-8")
        _write_entries(db, 1)
        entries = _read_lines(tmp_path / "audit.jsonl")
        assert len(entries) == 2
        assert "previous_hash" not in entries[0]  # legacy line untouched
        assert entries[1]["previous_hash"] == "deadbeef" * 8


class TestLinkWalkingVerifier:
    def test_fresh_chain_passes(self, db: Database) -> None:
        _write_entries(db, 5)
        assert db.verify_audit_log_integrity() is True

    def test_delete_middle_entry_detected(self, db: Database, tmp_path: Path) -> None:
        """Self-hashes all stay valid when the middle entry vanishes --
        ONLY the chain link check catches a deletion."""
        _write_entries(db, 3)
        db._discard_audit_handle()
        entries = _read_lines(tmp_path / "audit.jsonl")
        del entries[1]
        _rewrite_lines(tmp_path / "audit.jsonl", entries)
        assert db.verify_audit_log_integrity() is False

    def test_reorder_detected(self, db: Database, tmp_path: Path) -> None:
        """Swapping two entries keeps BOTH self-hashes valid; the link
        walk is what exposes reordering."""
        _write_entries(db, 4)
        db._discard_audit_handle()
        entries = _read_lines(tmp_path / "audit.jsonl")
        entries[1], entries[2] = entries[2], entries[1]
        _rewrite_lines(tmp_path / "audit.jsonl", entries)
        assert db.verify_audit_log_integrity() is False

    def test_mutation_detected(self, db: Database, tmp_path: Path) -> None:
        _write_entries(db, 3)
        db._discard_audit_handle()
        entries = _read_lines(tmp_path / "audit.jsonl")
        entries[1]["entity_id"] = "tampered"
        _rewrite_lines(tmp_path / "audit.jsonl", entries)
        assert db.verify_audit_log_integrity() is False

    def test_legacy_prefix_grandfathered(self, db: Database, tmp_path: Path) -> None:
        """Pre-chain entries (no previous_hash key) verify under the
        self-hash rule; the verifier must not fail them for a missing link.
        The legacy entry carries a VALID self-hash (grandfathering waives
        the LINK check, never the self-hash check)."""
        legacy_entry = {
            "entry_id": "audit_legacy1",
            "timestamp": "2026-09-01T10:00:00+00:00",
            "action": "CREATE",
            "entity_type": "trade",
            "entity_id": "legacy",
            "user": "system",
            "metadata": {},
            "previous_state": None,
            "new_state": None,
        }
        legacy_entry["sha256_hash"] = db._calculate_sha256(legacy_entry)
        (tmp_path / "audit.jsonl").write_text(
            json.dumps(legacy_entry) + "\n", encoding="utf-8"
        )
        assert db.verify_audit_log_integrity() is True

    def test_failure_logs_critical(
        self, db: Database, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        _write_entries(db, 3)
        db._discard_audit_handle()
        entries = _read_lines(tmp_path / "audit.jsonl")
        del entries[1]
        _rewrite_lines(tmp_path / "audit.jsonl", entries)
        with caplog.at_level(logging.CRITICAL, logger="loats.database"):
            assert db.verify_audit_log_integrity() is False
        assert any(r.levelno >= logging.CRITICAL for r in caplog.records), (
            "a broken audit chain must raise a CRITICAL alert"
        )

    def test_thousand_entry_chain_passes(self, db: Database) -> None:
        """FR9 acceptance pin: a 1k fresh chain verifies clean."""
        _write_entries(db, 1000)
        assert db.verify_audit_log_integrity() is True


class TestSchemaMigration:
    def test_migration_adds_previous_hash_column(self, tmp_path: Path) -> None:
        """A legacy DB (schema without the column) gains previous_hash via
        the standard init migration; legacy rows read back NULL."""
        legacy_db = tmp_path / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE audit_log (
                entry_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                user TEXT NOT NULL,
                metadata TEXT,
                previous_state TEXT,
                new_state TEXT,
                sha256_hash TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO audit_log VALUES ('a1', '2026-09-01T10:00:00+00:00', "
            "'CREATE', 'trade', 'legacy', 'system', '{}', NULL, NULL, 'h', 0)"
        )
        conn.commit()
        conn.close()

        db = Database(db_path=legacy_db, audit_log_path=tmp_path / "audit.jsonl")
        check = sqlite3.connect(legacy_db)
        cols = [r[1] for r in check.execute("PRAGMA table_info(audit_log)")]
        check.close()
        assert "previous_hash" in cols
        rows = db.get_audit_log()
        assert rows[0].previous_hash is None

    def test_fresh_and_migrated_schemas_agree_on_index(self, tmp_path: Path) -> None:
        """F8-L-02 contract for audit_log: the appended column must sit at
        the SAME ordinal in a fresh CREATE TABLE and an ALTER-migrated
        table (the row reader maps positionally)."""
        legacy_db = tmp_path / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE audit_log (
                entry_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                user TEXT NOT NULL,
                metadata TEXT,
                previous_state TEXT,
                new_state TEXT,
                sha256_hash TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()
        Database(db_path=legacy_db, audit_log_path=tmp_path / "a.jsonl")

        fresh = Database(
            db_path=tmp_path / "fresh.db", audit_log_path=tmp_path / "a2.jsonl"
        )
        fresh._get_connection()  # force init

        def columns(path: Path) -> list[str]:
            c = sqlite3.connect(path)
            cols = [(r[1], r[2]) for r in c.execute("PRAGMA table_info(audit_log)")]
            c.close()
            return [name for name, _ in cols]

        migrated_cols = columns(legacy_db)
        fresh_cols = columns(tmp_path / "fresh.db")
        assert migrated_cols == fresh_cols
        assert migrated_cols[-1] == "previous_hash"

    def test_positional_row_reader_maps_previous_hash(self, db: Database) -> None:
        """The row reader must pick previous_hash up from its appended
        ordinal (guarded by row length for pre-migration rows)."""
        import time

        _write_entries(db, 1)
        row = db.get_audit_log()[0]
        assert row.previous_hash is None  # first entry ever: no head
        # Distinct millisecond: ORDER BY timestamp DESC ties otherwise.
        time.sleep(0.002)
        _write_entries(db, 1)
        latest = db.get_audit_log()[0]
        assert latest.previous_hash == row.sha256_hash


class TestSpanSafety:
    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """Constructing Database twice on the same store must not fail --
        the ALTER path checks existing columns first."""
        paths: dict[str, Path] = {"db": tmp_path / "t.db", "a": tmp_path / "a.jsonl"}

        def make_db() -> Database:
            return Database(db_path=paths["db"], audit_log_path=paths["a"])

        make_db().close_all()
        second = make_db()
        second.close_all()
        conn = sqlite3.connect(paths["db"])
        cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
        conn.close()
        assert cols.count("previous_hash") == 1
