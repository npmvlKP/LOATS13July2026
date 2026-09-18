"""Regression tests for scripts/export_infinity_taint.py (F9-C-01-R1).

The 18Sep F9-C-01 wave stopped NEW ``-Infinity`` leaks at the payload
boundary (rules.py reports JSON ``null`` decision-facing), but audit rows
written BEFORE that fix still carry the non-RFC-8259 token in the
SHA-256-chained audit JSONL and in SQLite TEXT columns. The chain makes
those rows immutable by design (rewrite = chain break), so remediation is
a READ-ONLY forensic exporter that inventories the tainted rows into a
sidecar manifest. These tests pin that contract:

* taint detection across all three surfaces (JSONL raw lines,
  trade_decisions.gating_rules_result, audit_log state columns),
* the read-only guarantee (store bytes identical before/after),
* inventory-not-error semantics (exit 0 with taint present),
* the manifest itself is strict RFC 8259 JSON (never emits Infinity),
* graceful empty-store handling (missing/blank store yields a clean,
  zero-count manifest rather than a crash).

The exporter is exercised exactly as an operator runs it: subprocess
against a temp store, plus a module load for unit-level assertions.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_infinity_taint.py"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _load_module() -> ModuleType:
    """Load the exporter script as a module (it has no package parent)."""
    spec = importlib.util.spec_from_file_location(
        "export_infinity_taint_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_exporter(
    tmp_path: Path, db_path: Path | None, jsonl_path: Path | None
) -> subprocess.CompletedProcess[str]:
    """Run the exporter exactly as pre-commit/CI/an operator would."""
    out_path = tmp_path / "manifest.json"
    argv = [sys.executable, str(SCRIPT_PATH)]
    if db_path is not None:
        argv += ["--db", str(db_path)]
    if jsonl_path is not None:
        argv += ["--audit-log", str(jsonl_path)]
    argv += ["--out", str(out_path)]
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=120, check=False
    )


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_minimal_db(
    db_path: Path, decisions: list[dict[str, Any]], audit_rows: list[dict[str, Any]]
) -> None:
    """Create the two audited tables with production column names.

    The exporter must work against the COLUMN CONTRACT (decision_id /
    gating_rules_result / entry_id / new_state / previous_state /
    metadata / timestamp), not against the full LOATS schema - a fresh
    store legitimately lacks one or both tables.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE trade_decisions ("
            " decision_id TEXT PRIMARY KEY,"
            " timestamp TEXT NOT NULL,"
            " gating_rules_result TEXT)"
        )
        conn.execute(
            "CREATE TABLE audit_log ("
            " entry_id TEXT PRIMARY KEY,"
            " timestamp TEXT NOT NULL,"
            " new_state TEXT,"
            " previous_state TEXT,"
            " metadata TEXT)"
        )
        for d in decisions:
            conn.execute(
                "INSERT INTO trade_decisions (decision_id, timestamp,"
                " gating_rules_result) VALUES (?, ?, ?)",
                (d["decision_id"], d["timestamp"], d.get("gating_rules_result")),
            )
        for a in audit_rows:
            conn.execute(
                "INSERT INTO audit_log (entry_id, timestamp, new_state,"
                " previous_state, metadata) VALUES (?, ?, ?, ?, ?)",
                (
                    a["entry_id"],
                    a["timestamp"],
                    a.get("new_state"),
                    a.get("previous_state"),
                    a.get("metadata"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _tainted_payload() -> str:
    """A pre-fix gating payload: raw -inf serializes to -Infinity."""
    return json.dumps({"reason": "insufficient_history", "iv_rank": float("-inf")})


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------
def test_clean_store_reports_zero_taint_and_exit_zero(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(db, decisions=[], audit_rows=[])
    jsonl.write_text("", encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {
        "jsonl_lines_total": 0,
        "jsonl_lines_tainted": 0,
        "trade_decisions_tainted": 0,
        "audit_log_tainted": 0,
    }
    assert manifest["records"] == []


def test_jsonl_line_with_infinity_token_is_flagged(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(db, decisions=[], audit_rows=[])
    clean = json.dumps({"entry_id": "e1", "action": "gate", "iv_rank": 42.0})
    tainted = json.dumps({"entry_id": "e2", "action": "gate", "iv_rank": float("-inf")})
    jsonl.write_text(clean + "\n" + tainted + "\n", encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["jsonl_lines_total"] == 2
    assert manifest["counts"]["jsonl_lines_tainted"] == 1
    (record,) = [r for r in manifest["records"] if r["source"] == "audit_jsonl"]
    assert record["locator"] == {"line_number": 2}
    assert record["entry_id"] == "e2"
    # Chain context must ride along so the manifest is usable evidence.
    assert "sha256_hash" in record
    assert "previous_hash" in record


def test_unparseable_jsonl_line_with_token_is_still_flagged(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(db, decisions=[], audit_rows=[])
    jsonl.write_text('not-json {"iv_rank": -Infinity} trailing\n', encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["jsonl_lines_tainted"] == 1
    (record,) = [r for r in manifest["records"] if r["source"] == "audit_jsonl"]
    assert record.get("parse_error") is True


def test_trade_decisions_gating_taint_is_flagged(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(
        db,
        decisions=[
            {
                "decision_id": "d-clean",
                "timestamp": "2026-09-10T09:15:00+05:30",
                "gating_rules_result": json.dumps({"iv_rank": 30.0}),
            },
            {
                "decision_id": "d-taint",
                "timestamp": "2026-09-12T09:15:00+05:30",
                "gating_rules_result": _tainted_payload(),
            },
        ],
        audit_rows=[],
    )
    jsonl.write_text("", encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["trade_decisions_tainted"] == 1
    (record,) = [r for r in manifest["records"] if r["source"] == "trade_decisions"]
    assert record["entry_id"] == "d-taint"
    assert record["locator"] == {"column": "gating_rules_result"}


def test_audit_log_state_column_taint_is_flagged(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(
        db,
        decisions=[],
        audit_rows=[
            {
                "entry_id": "a-taint",
                "timestamp": "2026-09-11T10:00:00+05:30",
                "new_state": _tainted_payload(),
                "previous_state": None,
                "metadata": json.dumps({"ok": True}),
            }
        ],
    )
    jsonl.write_text("", encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["audit_log_tainted"] == 1
    (record,) = [r for r in manifest["records"] if r["source"] == "audit_log"]
    assert record["entry_id"] == "a-taint"
    assert record["locator"] == {"column": "new_state"}


def test_store_is_never_mutated_by_the_scan(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(
        db,
        decisions=[
            {
                "decision_id": "d-taint",
                "timestamp": "2026-09-12T09:15:00+05:30",
                "gating_rules_result": _tainted_payload(),
            }
        ],
        audit_rows=[],
    )
    jsonl.write_text('{"iv_rank": -Infinity}\n', encoding="utf-8")
    db_before = _file_digest(db)
    jsonl_before = _file_digest(jsonl)

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    assert _file_digest(db) == db_before, "exporter mutated the SQLite store"
    assert _file_digest(jsonl) == jsonl_before, "exporter mutated the audit JSONL"


def test_taint_presence_is_inventory_not_error(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(
        db,
        decisions=[
            {
                "decision_id": "d-taint",
                "timestamp": "2026-09-12T09:15:00+05:30",
                "gating_rules_result": _tainted_payload(),
            }
        ],
        audit_rows=[],
    )
    jsonl.write_text('{"iv_rank": -Infinity}\n', encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["trade_decisions_tainted"] == 1
    assert manifest["counts"]["jsonl_lines_tainted"] == 1
    assert manifest["counts"]["audit_log_tainted"] == 0


def test_missing_or_blank_store_yields_clean_manifest(tmp_path: Path) -> None:
    db = tmp_path / "does-not-exist.db"
    jsonl = tmp_path / "does-not-exist.log"

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["trade_decisions_tainted"] == 0
    assert manifest["counts"]["audit_log_tainted"] == 0
    assert manifest["counts"]["jsonl_lines_tainted"] == 0


def test_manifest_is_strict_rfc8259_json(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(
        db,
        decisions=[
            {
                "decision_id": "d-taint",
                "timestamp": "2026-09-12T09:15:00+05:30",
                "gating_rules_result": _tainted_payload(),
            }
        ],
        audit_rows=[],
    )
    jsonl.write_text('{"iv_rank": -Infinity}\n', encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    raw = (tmp_path / "manifest.json").read_bytes()
    # Strict parse: the manifest that inventories non-RFC-8259 taint must
    # itself never emit the token it exists to report.
    manifest = json.loads(raw, parse_constant=_reject_constant)
    assert manifest["tool"] == "export_infinity_taint"
    assert "generated_at" in manifest
    # The taint tokens quoted INSIDE record payloads are escaped string
    # content, never bare JSON constants - already proven by the strict
    # parse above.


def _reject_constant(value: str) -> float:
    raise AssertionError(f"manifest emitted non-RFC-8259 constant: {value}")


def test_stdout_summary_names_manifest_and_counts(tmp_path: Path) -> None:
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(db, decisions=[], audit_rows=[])
    jsonl.write_text('{"iv_rank": -Infinity}\n', encoding="utf-8")

    proc = _run_exporter(tmp_path, db, jsonl)

    assert proc.returncode == 0, proc.stderr
    assert "manifest.json" in proc.stdout
    assert "1" in proc.stdout


# ---------------------------------------------------------------------------
# Module-level contract (no subprocess): CLI rejects unknown args loudly.
# ---------------------------------------------------------------------------
def test_module_rejects_unknown_args(tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(SystemExit):
        module.main(["--db", str(tmp_path / "x.db"), "--bogus-flag"])


def test_module_main_returns_zero_on_clean_scan(tmp_path: Path) -> None:
    module = _load_module()
    db = tmp_path / "loats.db"
    jsonl = tmp_path / "audit.log"
    _seed_minimal_db(db, decisions=[], audit_rows=[])
    jsonl.write_text("", encoding="utf-8")
    rc = module.main(
        [
            "--db",
            str(db),
            "--audit-log",
            str(jsonl),
            "--out",
            str(tmp_path / "m.json"),
        ]
    )
    assert rc == 0
