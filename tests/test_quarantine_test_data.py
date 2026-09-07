"""Tests for scripts/quarantine_test_data.py (F8-H-01 P2 follow-up).

Locks the contamination-quarantine contract: fingerprint-only
classification (audit ROUTE rows carrying the test fixture's
``abc-123`` response id), move-not-delete semantics into
``trade_decisions_quarantined`` (audit JSONL is append-only and is
never rewritten), explicit-ack apply, and idempotent re-runs.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "quarantine_test_data",
        REPO_ROOT / "scripts" / "quarantine_test_data.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_db(tmp_path: Path, decision_ids: list[str]) -> Path:
    """Minimal production-shaped DB: one row per decision id."""
    db = tmp_path / "loats.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE trade_decisions ("
        " decision_id TEXT PRIMARY KEY, symbol TEXT, status TEXT)"
    )
    for did in decision_ids:
        con.execute(
            "INSERT INTO trade_decisions VALUES (?, ?, ?)",
            (did, "NIFTY", "PENDING"),
        )
    con.commit()
    con.close()
    return db


def _make_audit(tmp_path: Path, lines: list[str]) -> Path:
    audit = tmp_path / "audit.log"
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit


CONTAMINATED_ROUTE = (
    '{"action": "ROUTE", "entity_id": "decision_20260907_abc1", '
    '"metadata": {"routing_outcome": {"analyzer_id": "abc-123"}}}'
)
SUSPECT_ROUTE = (
    '{"action": "ROUTE", "entity_id": "decision_20260907_5ba11", '
    '"metadata": {"routing_outcome": {"analyzer_response": '
    '{"status": "accepted"}}}}'
)
CLEAN_ROUTE = (
    '{"action": "ROUTE", "entity_id": "decision_20260907_cafe01", '
    '"metadata": {"routing_outcome": {"analyzer_response": '
    '{"status": "accepted", "analyzer_id": "real-999"}}}}'
)


class TestScan:
    def test_flags_only_fingerprinted_decisions(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                "decision_20260907_abc1",
                "decision_20260907_5ba11",
                "decision_20260907_cafe01",
            ],
        )
        audit = _make_audit(tmp_path, [CONTAMINATED_ROUTE, SUSPECT_ROUTE, CLEAN_ROUTE])
        tool = _load_tool()
        report = tool.scan(db, audit)
        assert report["confirmed_decision_ids"] == ["decision_20260907_abc1"]
        assert report["suspect_decision_ids"] == ["decision_20260907_5ba11"]
        assert "decision_20260907_cafe01" not in (
            report["confirmed_decision_ids"] + report["suspect_decision_ids"]
        )

    def test_missing_audit_log_scans_zero(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path, ["decision_20260907_abc1"])
        tool = _load_tool()
        report = tool.scan(db, tmp_path / "nope.log")
        assert report["confirmed_rows_in_trade_decisions"] == 0
        assert report["suspect_rows_in_trade_decisions"] == 0


class TestApply:
    def test_apply_moves_confirmed_only_and_suspects_stay(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                "decision_20260907_abc1",
                "decision_20260907_5ba11",
                "decision_20260907_cafe01",
            ],
        )
        audit = _make_audit(tmp_path, [CONTAMINATED_ROUTE, SUSPECT_ROUTE, CLEAN_ROUTE])
        tool = _load_tool()
        manifest_dir = tmp_path / "reports"
        result = tool.apply_quarantine(db, audit, manifest_dir)

        con = sqlite3.connect(db)
        live = {r[0] for r in con.execute("SELECT decision_id FROM trade_decisions")}
        quarantined = con.execute(
            "SELECT decision_id, quarantine_reason, quarantined_at "
            "FROM trade_decisions_quarantined"
        ).fetchall()
        con.close()
        assert live == {"decision_20260907_5ba11", "decision_20260907_cafe01"}, (
            "suspect rows stay unless --include-suspect"
        )
        assert [q[0] for q in quarantined] == ["decision_20260907_abc1"]
        assert "abc-123" in quarantined[0][1]
        assert quarantined[0][2]
        assert result["moved_count"] == 1
        manifest = json.loads(Path(result["manifest_path"]).read_text())
        assert manifest["moved_decision_ids"] == ["decision_20260907_abc1"]

    def test_include_suspect_moves_both(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                "decision_20260907_abc1",
                "decision_20260907_5ba11",
                "decision_20260907_cafe01",
            ],
        )
        audit = _make_audit(tmp_path, [CONTAMINATED_ROUTE, SUSPECT_ROUTE, CLEAN_ROUTE])
        tool = _load_tool()
        result = tool.apply_quarantine(
            db, audit, tmp_path / "reports", include_suspect=True
        )
        assert result["moved_count"] == 2
        con = sqlite3.connect(db)
        live = {r[0] for r in con.execute("SELECT decision_id FROM trade_decisions")}
        con.close()
        assert live == {"decision_20260907_cafe01"}

    def test_apply_is_idempotent(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path, ["decision_20260907_abc1"])
        audit = _make_audit(tmp_path, [CONTAMINATED_ROUTE])
        tool = _load_tool()
        manifest_dir = tmp_path / "reports"
        tool.apply_quarantine(db, audit, manifest_dir)
        result = tool.apply_quarantine(db, audit, manifest_dir)
        assert result["moved_count"] == 0
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM trade_decisions_quarantined").fetchone()[
            0
        ]
        con.close()
        assert n == 1, "re-run must not duplicate quarantined rows"

    def test_schema_mirrors_live_table(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path, ["decision_20260907_abc1"])
        audit = _make_audit(tmp_path, [CONTAMINATED_ROUTE])
        tool = _load_tool()
        tool.apply_quarantine(db, audit, tmp_path / "reports")
        con = sqlite3.connect(db)
        live_cols = {r[1] for r in con.execute("PRAGMA table_info(trade_decisions)")}
        q_cols = {
            r[1] for r in con.execute("PRAGMA table_info(trade_decisions_quarantined)")
        }
        con.close()
        assert live_cols.issubset(q_cols)
        assert {"quarantine_reason", "quarantined_at"}.issubset(q_cols)


class TestCli:
    def test_apply_without_yes_is_refused(self, tmp_path: Path, capsys: Any) -> None:
        tool = _load_tool()
        rc = tool.main(
            [
                "--db",
                str(_make_db(tmp_path, [])),
                "--audit-log",
                str(_make_audit(tmp_path, [CONTAMINATED_ROUTE])),
                "--apply",
            ]
        )
        assert rc == 2
        assert "--apply requires --yes" in capsys.readouterr().err

    def test_scan_exit_zero(self, tmp_path: Path, capsys: Any) -> None:
        tool = _load_tool()
        rc = tool.main(
            [
                "--db",
                str(_make_db(tmp_path, ["decision_20260907_abc1"])),
                "--audit-log",
                str(_make_audit(tmp_path, [CONTAMINATED_ROUTE])),
            ]
        )
        assert rc == 0
        assert "[SCAN]" in capsys.readouterr().out

    def test_scan_reports_both_tiers(self, tmp_path: Path, capsys: Any) -> None:
        tool = _load_tool()
        rc = tool.main(
            [
                "--db",
                str(
                    _make_db(
                        tmp_path,
                        ["decision_20260907_abc1", "decision_20260907_5ba11"],
                    )
                ),
                "--audit-log",
                str(_make_audit(tmp_path, [CONTAMINATED_ROUTE, SUSPECT_ROUTE])),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "[confirmed] decision_20260907_abc1" in out
        assert "[suspect]   decision_20260907_5ba11" in out
