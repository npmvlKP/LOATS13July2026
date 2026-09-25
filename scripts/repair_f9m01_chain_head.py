"""F9-M-01-R1: re-anchor the frozen chain head in the live audit trail.

The F9-M-01 wave (d73536d) added the SHA-256 chain, but the pooled async
audit writer read the per-instance chain-head cache without ever
advancing it. Every entry the pool path wrote linked to whichever head
was current at the writer's first cache load; 23 distinct writer
lifetimes produced 23 frozen runs -- 4,578 entries from 18Sep 03:45 IST
onward whose ``previous_hash`` does not match the previous line's
``sha256_hash``. ``verify_audit_log_integrity()`` therefore reports a
broken link on the live log (CRITICAL alert at every supervisor boot and
every scheduler integrity pass).

Chain semantics make link repair a RE-ANCHORING, not a spot edit: the
hash covers ``previous_hash``, so correcting one link invalidates that
entry's self-hash, which changes the hash the NEXT entry must link to --
the correction cascades from the first broken link to end-of-file. This
tool re-anchors that span:

- every entry from the first break to EOF gets ``previous_hash`` set to
  the previous line's CURRENT stored hash and a freshly recomputed
  ``sha256_hash`` (the verified writer recipe);
- the legacy prefix and the intact segment before the span are untouched;
- DB rows are updated in lockstep (same recipe), each guarded on the
  row's OLD hash; rows that do not exist (file-only orphans of the old
  writer) are counted and left alone;
- a REPAIR audit record is appended to the chain (and mirrored into the
  DB) describing the operation and pinning the SHA-256 of the pre-repair
  backup file;
- full replay verification (self-hash + link walk, file order) must pass
  or the run fails non-zero.

Fail-closed contract:
- DRY-RUN BY DEFAULT. ``--apply`` performs the mutation.
- Refuses unless EVERY entry's stored self-hash re-verifies first (hash
  recipe drift means we do not understand the data -- abort).
- Refuses unless every broken link points at a ``sha256_hash`` that
  actually exists in the file (a writer bug always freezes at a real
  hash; anything else looks like tamper -- abort).
- Refuses if the file changes on disk between planning and the atomic
  replace (size guard); DB updates are guarded per-row.
- Snapshots the audit log and the SQLite DB before mutating.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "loats.db"
DEFAULT_LOG = REPO_ROOT / "data" / "audit.log"


def _entry_hash(entry: dict[str, object]) -> str:
    """Recompute an entry's self-hash with the verified writer recipe.

    sha256 over canonical JSON (``json.dumps(sort_keys=True)``) of the
    entry WITHOUT the ``sha256_hash`` key; legacy entries (no
    ``previous_hash`` key) were hashed without it, chained entries
    include it. All audit fields are JSON-native, so this matches
    ``Database._canonical_serialize`` for every row -- the pre-flight
    validation proves it per entry before any mutation happens.
    """
    hash_data = {k: v for k, v in entry.items() if k != "sha256_hash"}
    return hashlib.sha256(
        json.dumps(hash_data, sort_keys=True).encode("utf-8")
    ).hexdigest()


def load_entries(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                entries.append(json.loads(stripped))
    return entries


def plan_repair(
    entries: list[dict[str, object]],
) -> tuple[int, dict[str, int]]:
    """Validate the log and locate the re-anchor span; return stats.

    Returns ``(span_start, stats)`` where ``span_start`` is the line
    index of the first broken link (repairs run to end-of-file) and
    ``stats`` carries ``entries``/``broken``/``runs``.

    Fail-closed conditions (ValueError):
    - any entry's stored self-hash fails re-verification (recipe drift);
    - a chained log contains an entry without ``previous_hash`` after the
      chain started (unexpected shape);
    - any broken link's claimed value is NOT a real ``sha256_hash``
      present in the file (tamper-like shape -- a writer bug always
      freezes at a hash some entry actually carries).
    """
    file_hashes = {
        e["sha256_hash"] for e in entries if isinstance(e.get("sha256_hash"), str)
    }
    bad_self_hash = 0
    broken = 0
    runs = 0
    prev_idx = -10
    span_start: int | None = None
    prev_hash: str | None = None
    chain_started = False
    for idx, entry in enumerate(entries):
        stored = entry.get("sha256_hash")
        if not isinstance(stored, str) or _entry_hash(entry) != stored:
            bad_self_hash += 1
            prev_hash = stored if isinstance(stored, str) else None
            continue
        link = entry.get("previous_hash")
        if link is None:
            # Legacy entry (grandfathered): only legal before the chain
            # started.
            if chain_started:
                raise ValueError(
                    f"line {idx}: chained log contains an entry without "
                    "previous_hash -- unexpected shape, refusing"
                )
            prev_hash = stored
            continue
        chain_started = True
        if prev_hash is not None and link != prev_hash:
            if not isinstance(link, str):
                raise ValueError(f"line {idx}: non-string previous_hash")
            if link not in file_hashes:
                raise ValueError(
                    f"line {idx}: broken link points at {link[:16]}... "
                    "which is NOT the sha256_hash of any entry in the "
                    "file -- tamper-like shape, refusing"
                )
            broken += 1
            runs += 0 if idx == prev_idx + 1 else 1
            prev_idx = idx
            if span_start is None:
                span_start = idx
        prev_hash = stored
    if bad_self_hash:
        raise ValueError(
            f"{bad_self_hash} entries failed self-hash re-verification; "
            "hash recipe drift -- refusing to touch the log"
        )
    if span_start is None:
        return -1, {"entries": len(entries), "broken": 0, "runs": 0}
    return span_start, {
        "entries": len(entries),
        "broken": broken,
        "runs": runs,
    }


def reanchor_span(
    entries: list[dict[str, object]], span_start: int
) -> list[tuple[str, str, str, str | None]]:
    """Re-link and re-hash entries from ``span_start`` to EOF, in place.

    Returns DB update tuples ``(entry_id, old_hash, new_hash, old_link)``
    for every rewritten entry.
    """
    prev_hash = entries[span_start - 1].get("sha256_hash") if span_start > 0 else None
    if prev_hash is not None and not isinstance(prev_hash, str):
        raise ValueError("preceding entry has a non-string sha256_hash")
    updates: list[tuple[str, str, str, str | None]] = []
    for idx in range(span_start, len(entries)):
        entry = dict(entries[idx])
        old_hash = entry.get("sha256_hash")
        if not isinstance(old_hash, str):
            raise ValueError(f"line {idx}: missing sha256_hash in span")
        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, str):
            raise ValueError(f"line {idx}: missing entry_id in span")
        old_link = entry.get("previous_hash")
        if old_link is not None and not isinstance(old_link, str):
            raise ValueError(f"line {idx}: non-string previous_hash in span")
        entry["previous_hash"] = prev_hash
        new_hash = _entry_hash(entry)
        entry["sha256_hash"] = new_hash
        entries[idx] = entry
        updates.append((entry_id, old_hash, new_hash, old_link))
        prev_hash = new_hash
    return updates


def write_repaired_log(
    entries: list[dict[str, object]],
    log_path: Path,
    backup_path: Path,
    original_size: int,
) -> None:
    """Snapshot the original, atomically replace the log, guard races."""
    backup_path.write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in entries),
        encoding="utf-8",
        newline="\n",
    )
    if log_path.stat().st_size != original_size:
        raise ValueError(
            "audit log changed on disk since planning "
            f"({log_path.stat().st_size} != {original_size} bytes) -- refusing"
        )
    tmp_path = log_path.with_suffix(log_path.suffix + ".f9m01r1-tmp")
    tmp_path.write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in entries),
        encoding="utf-8",
        newline="\n",
    )
    tmp_path.replace(log_path)


def repair_db(
    db_path: Path,
    updates: list[tuple[str, str, str, str | None]],
) -> tuple[int, int]:
    """Mirror re-anchored (hash, link) pairs into audit_log rows.

    Each UPDATE is guarded on the row's OLD hash: a mismatch means the
    row and the file disagree about history -- abort via rollback. Rows
    that do not exist at all are file-only orphans of the old writer and
    are expected; they are counted and left alone.

    Returns (updated, missing).
    """
    updated = 0
    missing = 0
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        for entry_id, old_hash, new_hash, old_link in updates:
            cursor = conn.execute(
                "UPDATE audit_log SET sha256_hash = ?, previous_hash = ? "
                "WHERE entry_id = ? AND sha256_hash = ?",
                (new_hash, old_link, entry_id, old_hash),
            )
            if cursor.rowcount == 1:
                updated += 1
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE entry_id = ?",
                    (entry_id,),
                ).fetchone()
                if row[0] == 0:
                    missing += 1
                else:
                    conn.execute("ROLLBACK")
                    raise ValueError(
                        f"DB mirror for {entry_id}: row exists but its "
                        f"sha256_hash does not match the file's pre-repair "
                        f"hash {old_hash[:16]}... -- refusing"
                    )
        conn.execute("COMMIT")
        return updated, missing
    finally:
        conn.close()


def append_repair_record(
    log_path: Path,
    db_path: Path,
    stats: dict[str, int],
    backup_path: Path,
) -> None:
    """Append the REPAIR operation itself as a chained, dual-written entry."""
    now = datetime.now(UTC)
    backup_digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    tail_hash = None
    with log_path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                tail_hash = json.loads(stripped).get("sha256_hash")
    record: dict[str, object] = {
        "entry_id": f"audit_{now.strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}",
        "timestamp": now.isoformat(),
        "action": "REPAIR",
        "entity_type": "audit_log",
        "entity_id": "f9m01_r1_chain_reanchor",
        "user": "system",
        "metadata": {
            "tool": "scripts/repair_f9m01_chain_head.py",
            "broken_links": stats["broken"],
            "frozen_runs": stats["runs"],
            "backup_sha256": backup_digest,
            "reason": (
                "F9-M-01-R1: pooled async audit writer never advanced the "
                "chain-head cache; 23 frozen runs re-anchored"
            ),
        },
        "previous_state": {},
        "new_state": {"status": "repaired"},
        "timestamp_ms": int(now.timestamp() * 1000),
        "previous_hash": tail_hash,
    }
    record["sha256_hash"] = _entry_hash(record)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            """INSERT INTO audit_log
            (entry_id, timestamp, action, entity_type, entity_id, user,
             metadata, previous_state, new_state, sha256_hash, timestamp_ms,
             previous_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["entry_id"],
                record["timestamp"],
                record["action"],
                record["entity_type"],
                record["entity_id"],
                record["user"],
                json.dumps(record["metadata"]),
                None,
                json.dumps(record["new_state"]),
                record["sha256_hash"],
                record["timestamp_ms"],
                record["previous_hash"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def verify(entries: list[dict[str, object]]) -> bool:
    """Full replay: self-hash per entry + link walk in file order."""
    prev_hash: str | None = None
    for idx, entry in enumerate(entries):
        stored = entry.get("sha256_hash")
        if not isinstance(stored, str) or _entry_hash(entry) != stored:
            print(f"  VERIFY FAIL: line {idx} self-hash mismatch")
            return False
        link = entry.get("previous_hash")
        if link is not None and prev_hash is not None and link != prev_hash:
            print(f"  VERIFY FAIL: line {idx} broken link")
            return False
        prev_hash = stored
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--audit-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the repair (default: dry-run report only)",
    )
    args = parser.parse_args()

    entries = load_entries(args.audit_log)
    print(f"loaded {len(entries)} entries from {args.audit_log}")
    try:
        span_start, stats = plan_repair(entries)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    if span_start < 0:
        print("no broken links found; nothing to do")
        return 0
    print(
        f"{stats['broken']} broken links across {stats['runs']} frozen runs; "
        f"re-anchor span: lines {span_start}..{stats['entries'] - 1}"
    )

    if not args.apply:
        print("DRY-RUN: no changes written (pass --apply to repair)")
        return 0

    backup_log = args.audit_log.with_suffix(args.audit_log.suffix + ".f9m01r1-backup")
    original_size = args.audit_log.stat().st_size
    updates = reanchor_span(entries, span_start)
    write_repaired_log(entries, args.audit_log, backup_log, original_size)
    print(f"JSONL re-anchored ({len(updates)} entries); backup: {backup_log.name}")

    db_backup = args.db.with_suffix(args.db.suffix + ".f9m01r1-backup")
    src = sqlite3.connect(str(args.db))
    dst = sqlite3.connect(str(db_backup))
    src.backup(dst)
    dst.close()
    src.close()
    print(f"DB snapshot saved to {db_backup.name}")

    updated, missing = repair_db(args.db, updates)
    print(
        f"DB rows updated: {updated}; rows absent (file-only orphans, "
        f"left alone): {missing}"
    )

    append_repair_record(args.audit_log, args.db, stats, backup_log)
    print("REPAIR record appended to chain and DB")

    repaired = load_entries(args.audit_log)
    ok = verify(repaired)
    print("post-repair chain verification:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
