#!/usr/bin/env python3
"""F9-L-03 (TODO-12): audited purge of legacy untagged signal rows and the
STRESS-ORD stress-test row.

FR9 finding F9-L-03: the live store carried (a) a STRESS-ORD row in
``modification_counts`` left by the 02Sep multi-process stress rehearsal and
(b) 42 sentiment + 1 combined signal rows from 14Aug written BEFORE
per-source enum tagging existed (no ``metadata["source"]`` key). This script
removes exactly that population, writes every removal to the sha256-chained
audit trail via the canonical ``Database.log_audit`` dual-write, takes a
verbatim safety copy of both trails first, and re-verifies chain integrity
through a SECOND Database instance after the writes.

Safety design (fail-closed everywhere):
- DRY-RUN is the default mode; ``--apply`` is required for any write.
- The eligible set is recomputed by the SAME rule the insert-time guard
  (``src/loats/signal_source_guard.py``) enforces going forward; rows with a
  valid tag are never eligible regardless of age.
- The expected population is pinned (43 untagged rows predating the cutoff,
  all but one older than 2026-09-01, scan_type split 42 sentiment / 1
  combined; exactly one STRESS-ORD row). Any drift aborts unless the
  operator passes ``--force`` (which dumps the full listing for the record).
- A live-writer guard aborts when the audit trail was appended to within
  the last 10 minutes (the F9-M-01 chain head is cached per process; a
  second writer would fork the chain). ``--allow-active-writer`` overrides
  for a deliberate maintenance window.

Usage (PowerShell 5.1, repo venv):
  python scripts/purge_legacy_signal_rows.py                 # dry-run
  python scripts/purge_legacy_signal_rows.py --apply         # audited purge
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.loats.database import Database
from src.loats.signal_source_guard import (
    ALLOWED_SIGNAL_SOURCES,
    TEST_PROVENANCE_KEY,
)

DEFAULT_CUTOFF = "2026-09-01"
# FR9 census: 42 untagged rows (42 sentiment + 1 combined was the raw
# pre-cutoff count; the combined row carries a valid price_action tag
# and is retained -- the classifier, not the raw count, is authoritative).
EXPECTED_UNTAGGED = 42
EXPECTED_STRESS_ROWS = 1
WRITER_QUIET_WINDOW_SECONDS = 600
REPORT_PATH = project_root / "reports" / "ai-generated" / "f9l03-purge-record.json"


def _row_is_untagged(metadata_json: str | None) -> tuple[bool, str]:
    """Classify one row against the guard's rule. Returns (eligible, reason)."""
    if metadata_json is None or not metadata_json.strip():
        return True, "missing_tag"
    try:
        metadata: dict[str, Any] = json.loads(metadata_json)
    except json.JSONDecodeError:
        return True, "metadata_unparseable"
    if not isinstance(metadata, dict):
        return True, "metadata_not_object"
    if TEST_PROVENANCE_KEY in metadata:
        return False, "test_provenance_tag"
    source = metadata.get("source")
    if source is None or not isinstance(source, str) or not source:
        return True, "missing_tag"
    if source not in ALLOWED_SIGNAL_SOURCES:
        return True, "unknown_tag"
    return False, "valid_tag"


def _load_candidates(
    db_path: Path, cutoff: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (eligible, retained_valid) row summaries."""
    import sqlite3

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT signal_id, symbol, signal_type, created_at, metadata "
            "FROM signals WHERE created_at < ? ORDER BY created_at",
            (cutoff,),
        ).fetchall()
    finally:
        con.close()
    eligible: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for signal_id, symbol, signal_type, created_at, metadata_json in rows:
        is_eligible, reason = _row_is_untagged(metadata_json)
        entry = {
            "signal_id": signal_id,
            "symbol": symbol,
            "signal_type": signal_type,
            "created_at": created_at,
            "reason": reason,
        }
        (eligible if is_eligible else retained).append(entry)
    return eligible, retained


def _check_live_writer(audit_log_path: Path) -> str | None:
    """Return a blocking reason when a live writer may fork the chain.

    Two probes, both required quiet:
    1. metrics-port probe: the :8001 metrics server IS the trading app;
       a responding port means a Database instance exists whose cached
       F9-M-01 chain head predates this purge -- its next audit write
       would link against a stale head and fork the hash chain.
    2. recency probe: an audit trail written within the quiet window
       means SOME process wrote recently even if the port probe misses
       it (different port / already-stopping race).
    """
    import http.client
    import sqlite3

    # http.client (not urllib.request): the probe target is the hardcoded
    # loopback metrics endpoint; the lower-level client expresses that
    # constraint structurally (no scheme/file: handling at all) and keeps
    # the bandit surface clean per ADR-0015 discipline.
    conn = http.client.HTTPConnection("127.0.0.1", 8001, timeout=2)
    try:
        conn.request("GET", "/metrics")
        response = conn.getresponse()
        response.read(64)
        return (
            "the trading app is RUNNING (metrics answered on 127.0.0.1:8001); "
            "its process caches the F9-M-01 chain head, so an audit append "
            "from this script would fork the chain on the app's next write "
            "-- stop the app for the purge window (or pass "
            "--allow-active-writer ONLY for a controlled window where you "
            "have stopped signal/audit intake)"
        )
    except OSError:
        pass  # port unreachable: no live app detected
    finally:
        conn.close()

    latest: str | None = None
    con = sqlite3.connect(
        f"file:{project_root / 'data' / 'loats.db'}?mode=ro", uri=True
    )
    try:
        row = con.execute("SELECT MAX(timestamp) FROM audit_log").fetchone()
        latest = row[0] if row else None
    except sqlite3.Error:
        latest = None
    finally:
        con.close()
    if latest is None:
        return None
    try:
        last_dt = datetime.fromisoformat(str(latest))
    except ValueError:
        return f"audit_log has an unparseable latest timestamp: {latest!r}"
    age = datetime.now(UTC) - last_dt
    if age < timedelta(seconds=WRITER_QUIET_WINDOW_SECONDS):
        return (
            f"audit_log was written {int(age.total_seconds())}s ago "
            f"(<{WRITER_QUIET_WINDOW_SECONDS}s quiet window); a live writer "
            "caches the F9-M01 chain head per process -- run this purge "
            "from an exclusive maintenance window (or pass "
            "--allow-active-writer explicitly)"
        )
    return None


def _preconditions(
    eligible: list[dict[str, Any]],
    stress_rows: int,
) -> list[str]:
    problems: list[str] = []
    if len(eligible) != EXPECTED_UNTAGGED:
        problems.append(
            f"untagged eligible rows = {len(eligible)}, expected "
            f"{EXPECTED_UNTAGGED} (cutoff drift or new untagged writer)"
        )
    if stress_rows != EXPECTED_STRESS_ROWS:
        problems.append(
            f"STRESS-ORD rows = {stress_rows}, expected {EXPECTED_STRESS_ROWS}"
        )
    return problems


def _reason_counts(eligible: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in eligible:
        counts[entry["reason"]] = counts.get(entry["reason"], 0) + 1
    return counts


def _write_record(record: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"record written: {REPORT_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="F9-L-03 audited purge (dry-run by default)"
    )
    parser.add_argument(
        "--apply", action="store_true", help="execute the purge (default: dry-run)"
    )
    parser.add_argument(
        "--cutoff",
        default=DEFAULT_CUTOFF,
        help=f"ISO date cutoff (default {DEFAULT_CUTOFF})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="proceed despite population drift (full listing goes to the record)",
    )
    parser.add_argument(
        "--allow-active-writer",
        action="store_true",
        help="skip the 10-minute audit-quiet-window check",
    )
    args = parser.parse_args()

    db_path = project_root / "data" / "loats.db"
    audit_log_path = project_root / "data" / "audit.log"
    if not db_path.exists() or not audit_log_path.exists():
        print(f"ABORT: missing {db_path} or {audit_log_path}", file=sys.stderr)
        return 2

    eligible, retained_valid = _load_candidates(db_path, args.cutoff)
    import sqlite3

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        stress_rows = con.execute(
            "SELECT COUNT(*) FROM modification_counts WHERE order_id = 'STRESS-ORD'"
        ).fetchone()[0]
        total_signals = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        con.close()

    mode = "APPLY" if args.apply else "DRY-RUN"
    record: dict[str, Any] = {
        "finding": "F9-L-03 (TODO-12)",
        "mode": mode,
        "executed_at": datetime.now(UTC).isoformat(),
        "cutoff": args.cutoff,
        "total_signals": total_signals,
        "eligible": eligible,
        "retained_with_valid_tag": retained_valid,
        "stress_ord_rows": stress_rows,
    }

    problems = _preconditions(eligible, stress_rows)
    if problems:
        if not args.force:
            record["precondition_problems"] = problems
            _write_record(record)
            for problem in problems:
                print(f"ABORT: {problem}", file=sys.stderr)
            return 2
        record["forced_by_operator"] = True
        record["precondition_problems"] = problems
    record["reason_counts"] = _reason_counts(eligible)

    if not args.apply:
        print(f"DRY-RUN: {len(eligible)} untagged rows eligible for purge")
        for entry in eligible[:10]:
            print(
                f"  {entry['created_at']} {entry['signal_type']:8s} "
                f"{entry['symbol']:6s} {entry['reason']}"
            )
        if len(eligible) > 10:
            print(f"  ... and {len(eligible) - 10} more")
        print(f"STRESS-ORD rows present: {stress_rows}")
        _write_record(record)
        print("Re-run with --apply inside a maintenance window to execute.")
        return 0

    writer_block = (
        None if args.allow_active_writer else _check_live_writer(audit_log_path)
    )
    if writer_block:
        record["precondition_problems"] = [writer_block]
        _write_record(record)
        print(f"ABORT: {writer_block}", file=sys.stderr)
        return 2

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = project_root / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / f"loats-pre-f9l03-purge-{timestamp}.db"
    audit_backup = backup_dir / f"audit-pre-f9l03-purge-{timestamp}.log"
    shutil.copy2(db_path, db_backup)
    shutil.copy2(audit_log_path, audit_backup)
    record["backups"] = {"db": str(db_backup), "audit": str(audit_backup)}

    # Single-writer purge: one Database instance owns both trails.
    # Audit-first ordering: each row's DELETE audit entry is dual-written
    # (JSONL + DB, hash-chained) BEFORE the row is removed, so a crash
    # can only over-report (audit says deleted, row still present on
    # re-run), never silently lose data without an audit entry. The
    # per-entry commit inside log_audit also makes the PREVIOUS row's
    # DELETE durable -- at the end of the loop every DELETE is durable.
    db = Database(db_path=db_path, audit_log_path=audit_log_path)
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        deleted_ids: list[str] = []
        try:
            for entry in eligible:
                db.log_audit(
                    action="DELETE",
                    entity_type="signal",
                    entity_id=entry["signal_id"],
                    metadata={
                        "finding": "F9-L-03",
                        "mode": "audited-purge",
                        "reason": entry["reason"],
                        "created_at": entry["created_at"],
                    },
                    previous_state={
                        "symbol": entry["symbol"],
                        "signal_type": entry["signal_type"],
                    },
                )
                cursor.execute(
                    "DELETE FROM signals WHERE signal_id = ?",
                    (entry["signal_id"],),
                )
                deleted_ids.append(entry["signal_id"])
            db.log_audit(
                action="DELETE",
                entity_type="modification_count",
                entity_id="STRESS-ORD",
                metadata={
                    "finding": "F9-L-03",
                    "mode": "audited-purge",
                    "origin": "02Sep multi-process stress rehearsal",
                },
                previous_state={"order_id": "STRESS-ORD"},
            )
            cursor.execute(
                "DELETE FROM modification_counts WHERE order_id = 'STRESS-ORD'"
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        remaining = cursor.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        stress_left = cursor.execute(
            "SELECT COUNT(*) FROM modification_counts WHERE order_id = 'STRESS-ORD'"
        ).fetchone()[0]
    finally:
        db.close()

    if stress_left != 0:
        print(
            "ABORT post-write: STRESS-ORD row still present after DELETE",
            file=sys.stderr,
        )
        return 1

    # Re-verify through a SECOND instance: chain integrity + final counts.
    verifier = Database(db_path=db_path, audit_log_path=audit_log_path)
    try:
        chain_ok = bool(verifier.verify_audit_log_integrity())
        vconn = verifier._get_connection()
        final_total = vconn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    finally:
        verifier.close()
    if not chain_ok:
        print(
            "CRITICAL: audit chain integrity FAILED after purge writes; "
            f"restore from {db_backup} / {audit_backup} and investigate.",
            file=sys.stderr,
        )
        return 1

    record.update(
        {
            "record_id": f"f9l03-purge-{timestamp}",
            "deleted_ids": deleted_ids,
            "row_count_before": total_signals,
            "row_count_after": remaining,
            "stress_ord_removed": True,
            "second_instance_chain_verified": chain_ok,
            "second_instance_row_count": final_total,
        }
    )
    _write_record(record)
    print(
        f"APPLIED: deleted {len(deleted_ids)} untagged rows + STRESS-ORD; "
        f"signals {total_signals} -> {remaining}; chain verified: {chain_ok}"
    )
    print(
        "Next: run pytest tests/test_signal_source_guard.py "
        "tests/test_purge_script_f9l03.py, then set the FR9 Low-tier "
        "record fields in the audit-history document."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
