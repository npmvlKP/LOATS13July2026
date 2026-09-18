#!/usr/bin/env python3
"""Read-only forensic exporter for pre-fix ``-Infinity`` audit taint.

F9-C-01-R1. The 18Sep F9-C-01 wave stopped NEW ``-Infinity`` leaks at the
payload boundary (rules.py reports JSON ``null`` decision-facing), but
audit rows written BEFORE that fix still carry the non-RFC-8259 token
``-Infinity`` in:

* the audit JSONL (``data/audit.log``, SHA-256 hash chain),
* ``trade_decisions.gating_rules_result`` (SQLite TEXT), and
* the ``audit_log`` state columns (``new_state`` / ``previous_state`` /
  ``metadata``).

The hash chain makes those rows immutable by design (a rewrite breaks
every downstream link), so remediation is NOT a data migration: this
tool inventories the tainted rows into a sidecar RFC 8259 manifest so
any downstream JSON consumer has a bounded, provable roster of rows to
special-case. Read-only is a hard guarantee: the JSONL is only ever
read, and SQLite is opened with ``mode=ro`` (the exporter physically
cannot create or write the store).

Taint detection is the same idiom the F9-C-01 tests pin: the substring
``Infinity`` in the raw text (bare non-RFC-8259 constants only ever
originate from ``json.dumps`` of a non-finite float). Lines that fail
``json.loads`` are still flagged, with ``parse_error: true``.

Exit semantics: inventory, not error - taint presence still exits 0.
Non-zero exit is reserved for operator failures (bad arguments,
unwritable output path).

Usage:
    python scripts/export_infinity_taint.py \
        --db data/loats.db --audit-log data/audit.log \
        --out reports/infinity-taint-manifest.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_TOOL = "export_infinity_taint"
TAINT_MARKER = "Infinity"
EXCERPT_LIMIT = 200


def _excerpt(text: str) -> str:
    """Bounded raw excerpt; quoted string content inside the manifest."""
    return text[:EXCERPT_LIMIT]


def _scan_jsonl(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Scan the audit JSONL; returns (records, total_lines, tainted)."""
    records: list[dict[str, Any]] = []
    total = 0
    tainted = 0
    if not path.is_file():
        return records, total, tainted
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, raw in enumerate(handle, start=1):
            total += 1
            if TAINT_MARKER not in raw:
                continue
            tainted += 1
            record: dict[str, Any] = {
                "source": "audit_jsonl",
                "locator": {"line_number": line_number},
                "payload_excerpt": _excerpt(raw.strip()),
            }
            try:
                entry = json.loads(raw)
                if isinstance(entry, dict):
                    record["entry_id"] = entry.get("entry_id")
                    record["sha256_hash"] = entry.get("sha256_hash")
                    record["previous_hash"] = entry.get("previous_hash")
                    record["timestamp"] = entry.get("timestamp")
            except json.JSONDecodeError:
                record["parse_error"] = True
            records.append(record)
    return records, total, tainted


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open SQLite strictly read-only; raises if the file is absent."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _scan_trade_decisions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Inventory tainted ``gating_rules_result`` rows."""
    if not _table_exists(conn, "trade_decisions"):
        return []
    records: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT decision_id, timestamp, gating_rules_result"
        " FROM trade_decisions WHERE gating_rules_result LIKE ?",
        (f"%{TAINT_MARKER}%",),
    ).fetchall()
    for decision_id, timestamp, payload in rows:
        if not isinstance(payload, str) or TAINT_MARKER not in payload:
            continue
        records.append(
            {
                "source": "trade_decisions",
                "entry_id": decision_id,
                "locator": {"column": "gating_rules_result"},
                "timestamp": timestamp,
                "payload_excerpt": _excerpt(payload),
            }
        )
    return records


def _scan_audit_log(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Inventory tainted ``audit_log`` state columns."""
    if not _table_exists(conn, "audit_log"):
        return []
    records: list[dict[str, Any]] = []
    columns = ("new_state", "previous_state", "metadata")
    rows = conn.execute(
        "SELECT entry_id, timestamp, new_state, previous_state, metadata FROM audit_log"
    ).fetchall()
    for entry_id, timestamp, new_state, previous_state, metadata in rows:
        for column, value in zip(
            columns, (new_state, previous_state, metadata), strict=True
        ):
            if not isinstance(value, str) or TAINT_MARKER not in value:
                continue
            records.append(
                {
                    "source": "audit_log",
                    "entry_id": entry_id,
                    "locator": {"column": column},
                    "timestamp": timestamp,
                    "payload_excerpt": _excerpt(value),
                }
            )
    return records


def build_manifest(db_path: Path, jsonl_path: Path) -> dict[str, Any]:
    """Run the three-surface scan and assemble the manifest dict."""
    jsonl_records, jsonl_total, jsonl_tainted = _scan_jsonl(jsonl_path)

    decision_records: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    if db_path.is_file():
        conn = _connect_readonly(db_path)
        try:
            decision_records = _scan_trade_decisions(conn)
            audit_records = _scan_audit_log(conn)
        finally:
            conn.close()

    counts = {
        "jsonl_lines_total": jsonl_total,
        "jsonl_lines_tainted": jsonl_tainted,
        "trade_decisions_tainted": len(decision_records),
        "audit_log_tainted": len(audit_records),
    }
    return {
        "tool": MANIFEST_TOOL,
        "generated_at": datetime.now(UTC).isoformat(),
        "store": {"db": str(db_path), "audit_log": str(jsonl_path)},
        "counts": counts,
        "records": jsonl_records + decision_records + audit_records,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog=MANIFEST_TOOL,
        description=(
            "Read-only forensic exporter: inventory pre-fix -Infinity"
            " audit rows into a sidecar RFC 8259 manifest (F9-C-01-R1)."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/loats.db"),
        help="SQLite store (opened read-only; never written).",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=Path("data/audit.log"),
        help="Audit JSONL (read-only; never written).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/infinity-taint-manifest.json"),
        help="Manifest output path (the only file this tool writes).",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(args.db, args.audit_log)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: the manifest that inventories non-RFC-8259 taint
    # must itself be strictly RFC 8259 - a stray non-finite float raises
    # instead of leaking the token it exists to report.
    args.out.write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    counts = manifest["counts"]
    print(
        f"{MANIFEST_TOOL}: jsonl {counts['jsonl_lines_tainted']}"
        f"/{counts['jsonl_lines_total']} lines tainted, "
        f"{counts['trade_decisions_tainted']} trade_decisions rows, "
        f"{counts['audit_log_tainted']} audit_log rows. "
        f"Manifest: {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
