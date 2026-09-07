#!/usr/bin/env python3
"""Quarantine test-contaminated trade-decision rows (F8-H-01 follow-up, P2).

ADR-006 Amendment 2 forensics proved suite runs wrote into production
data via the unpatched ``db`` singleton: 186 audit rows carry the test
fixture's analyzer response (``analyzer_id: "abc-123"``) and reference
test-created decisions. Any metric computed over ``trade_decisions`` is
therefore skewed until those rows are quarantined.

Principles (SEBI audit-trail rules):
- The JSONL audit log is append-only and SHA-256-chained: this tool NEVER
  rewrites or deletes audit history. Contamination is proven by the
  fingerprint in the row itself, so quarantining the SQLite rows suffices
  and the audit trail remains the immutable record of what happened.
- Rows are MOVED, not deleted: ``trade_decisions_quarantined`` (schema
  cloned from ``trade_decisions`` + ``quarantine_reason``) keeps the data
  available for analysis while excluding it from production queries.
- Fingerprint-only classification: a decision is quarantined ONLY when an
  audit ROUTE row for it carries the test-fixture fingerprint. No time
  heuristics — false quarantines are worse than residue.

Usage:
    python scripts/quarantine_test_data.py                 # scan + report
    python scripts/quarantine_test_data.py --json out.json # machine report
    python scripts/quarantine_test_data.py --apply --yes   # move rows

Exit codes: 0 success (scan or apply), 2 usage/refusal.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "loats.db"
DEFAULT_AUDIT = REPO_ROOT / "data" / "audit.log"
DEFAULT_MANIFEST_DIR = REPO_ROOT / "reports"

# The test fixture's canned analyzer response ids. Any audit row carrying
# one is test output by construction; the decisions its ROUTE rows
# reference are quarantine targets.
#   abc-123  — tests/test_analyzer_routing_integration.py:90 fake_response
#   t-1      — tests/test_p5_forward_test.py FakeEngine (never persisted;
#              kept listed for defense against future leakage)
CONFIRMED_FINGERPRINTS = ("abc-123", "t-1")

# SUSPECT shape: an analyzer_response of exactly {"status": "accepted"}
# with no analyzer_id — the AsyncMock in tests/test_trade_decision.py:472.
# A real Analyzer response could legitimately omit analyzer_id, so this
# shape alone is reported but NOT moved unless --include-suspect is given.
SUSPECT_REASON = (
    "bare accepted response without analyzer_id (matches "
    "tests/test_trade_decision.py:472 AsyncMock shape)"
)

DECISION_ID_IN_LINE = re.compile(r"decision_[0-9]+_[0-9a-f]+")


def _classify_audit(audit_log: Path) -> tuple[set[str], set[str]]:
    """Return (confirmed_ids, suspect_ids) from ROUTE audit rows.

    Confirmed: the row carries a fixture fingerprint (``abc-123``).
    Suspect: the routing_outcome's analyzer_response is exactly
    ``{"status": "accepted"}`` with no analyzer_id (the AsyncMock shape
    from tests/test_trade_decision.py). Suspects are reported, not
    moved, unless the caller opts in.
    """
    confirmed: set[str] = set()
    suspect: set[str] = set()
    if not audit_log.exists():
        return confirmed, suspect
    with audit_log.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"ROUTE"' not in line:
                continue
            ids = DECISION_ID_IN_LINE.findall(line)
            if not ids:
                continue
            confirmed_hit = any(fp in line for fp in CONFIRMED_FINGERPRINTS)
            suspect_hit = False
            if not confirmed_hit:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    row = None
                if row is not None:
                    outcome = (row.get("metadata") or {}).get("routing_outcome") or {}
                    response = outcome.get("analyzer_response")
                    if (
                        isinstance(response, dict)
                        and response.get("status") == "accepted"
                        and "analyzer_id" not in response
                    ):
                        suspect_hit = True
            if confirmed_hit:
                confirmed.update(ids)
            elif suspect_hit:
                suspect.update(ids)
    return confirmed, suspect


def _ensure_quarantine_table(con: sqlite3.Connection) -> None:
    """Mirror ``trade_decisions`` schema + quarantine columns (idempotent).

    The clone is rebuilt whenever the live table gains columns the
    quarantine copy lacks, so moved rows always carry every live field.
    """
    live_cols = [
        row[1] for row in con.execute("PRAGMA table_info(trade_decisions)").fetchall()
    ]
    if not live_cols:
        raise SystemExit("trade_decisions table not found in DB")
    extra = ("quarantine_reason", "quarantined_at")
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='trade_decisions_quarantined'"
    ).fetchone()
    if exists:
        have = [
            row[1]
            for row in con.execute(
                "PRAGMA table_info(trade_decisions_quarantined)"
            ).fetchall()
        ]
        if set(live_cols).issubset(set(have)):
            return
        con.execute("DROP TABLE trade_decisions_quarantined")
    con.execute(
        "CREATE TABLE trade_decisions_quarantined AS "
        "SELECT * FROM trade_decisions WHERE 0"
    )
    for col in extra:
        con.execute(f"ALTER TABLE trade_decisions_quarantined ADD COLUMN {col} TEXT")


def scan(db_path: Path, audit_log: Path) -> dict[str, object]:
    """Classify contamination without touching the DB."""
    confirmed, suspect = _classify_audit(audit_log)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        present = {
            did
            for did in confirmed | suspect
            if con.execute(
                "SELECT 1 FROM trade_decisions WHERE decision_id = ?", (did,)
            ).fetchone()
        }
        confirmed_present = sorted(present & confirmed)
        suspect_present = sorted(present & suspect)
    finally:
        con.close()
    return {
        "confirmed_fingerprints": list(CONFIRMED_FINGERPRINTS),
        "confirmed_audit_ids": len(confirmed),
        "suspect_audit_ids": len(suspect),
        "confirmed_rows_in_trade_decisions": len(confirmed_present),
        "suspect_rows_in_trade_decisions": len(suspect_present),
        "confirmed_decision_ids": confirmed_present,
        "suspect_decision_ids": suspect_present,
    }


def apply_quarantine(
    db_path: Path,
    audit_log: Path,
    manifest_dir: Path,
    include_suspect: bool = False,
) -> dict[str, object]:
    """Move fingerprinted rows into the quarantine table + write manifest."""
    report = scan(db_path, audit_log)
    targets: list[str] = list(report["confirmed_decision_ids"])  # type: ignore[arg-type]
    if include_suspect:
        targets += list(report["suspect_decision_ids"])  # type: ignore[arg-type]
    reason = (
        f"test contamination ({', '.join(CONFIRMED_FINGERPRINTS)}); ADR-006 Amendment 2"
    )
    if include_suspect:
        reason += f"; {SUSPECT_REASON}"
    moved: list[str] = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        _ensure_quarantine_table(con)
        for did in targets:
            # Move semantics: INSERT..SELECT FIRST (so the source row still
            # exists), verify the insert landed, and only then DELETE the
            # source. Never the reverse order — a DELETE-then-SELECT would
            # silently drop the row.
            cur = con.execute(
                "INSERT INTO trade_decisions_quarantined "
                "SELECT t.*, ?, ? FROM trade_decisions t "
                "WHERE t.decision_id = ?",
                (reason, now, did),
            )
            if cur.rowcount:
                con.execute("DELETE FROM trade_decisions WHERE decision_id = ?", (did,))
                moved.append(did)
        con.commit()
    finally:
        con.close()
    manifest = {
        "generated_at": now,
        "tool": "scripts/quarantine_test_data.py",
        "scanned": report,
        "moved_count": len(moved),
        "moved_decision_ids": moved,
        "note": (
            "audit.log untouched (append-only, SHA-256-chained); rows moved "
            "to trade_decisions_quarantined with reason + timestamp"
        ),
    }
    manifest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    out = manifest_dir / f"quarantine_manifest_{stamp}.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest, "manifest_path": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quarantine test-contaminated trade decisions (F8-H-01 P2)."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--audit-log", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="move flagged rows (default: scan-only report)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="explicit acknowledgement required with --apply",
    )
    parser.add_argument(
        "--include-suspect",
        action="store_true",
        help=(
            "with --apply: also move suspect-shape rows (bare accepted "
            "response without analyzer_id). Default: report only."
        ),
    )
    parser.add_argument("--json", type=Path, default=None, help="also write report")
    args = parser.parse_args(argv)

    if args.apply and not args.yes:
        print(
            "[FAIL] --apply requires --yes (rows are MOVED out of "
            "trade_decisions); scan-only run first and review the report",
            file=sys.stderr,
        )
        return 2
    if not args.db.exists():
        print(f"[FAIL] DB not found: {args.db}", file=sys.stderr)
        return 2

    if args.apply:
        result = apply_quarantine(
            args.db,
            args.audit_log,
            DEFAULT_MANIFEST_DIR,
            include_suspect=args.include_suspect,
        )
        print(
            f"[OK] moved {result['moved_count']} row(s) to "
            "trade_decisions_quarantined; manifest: "
            f"{result['manifest_path']}"
        )
    else:
        result = scan(args.db, args.audit_log)
        print(
            f"[SCAN] confirmed fingerprints {result['confirmed_fingerprints']}: "
            f"{result['confirmed_audit_ids']} audit id(s) "
            f"({result['confirmed_rows_in_trade_decisions']} still in "
            "trade_decisions); "
            f"{result['suspect_audit_ids']} suspect-shape id(s) "
            f"({result['suspect_rows_in_trade_decisions']} still present)"
        )
        for did in result["confirmed_decision_ids"]:  # type: ignore[index]
            print(f"    [confirmed] {did}")
        for did in result["suspect_decision_ids"]:  # type: ignore[index]
            print(f"    [suspect]   {did}")
        if result["confirmed_rows_in_trade_decisions"]:
            print(
                "  Run with --apply --yes to quarantine confirmed rows "
                "(audit log is never rewritten). Add --include-suspect "
                "to also move suspect-shape rows."
            )
    if args.json is not None:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
