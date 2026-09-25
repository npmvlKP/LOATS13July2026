"""F9-L-03 (TODO-12): audited purge script pins (provenance hygiene net).

Covers ``scripts/purge_legacy_signal_rows.py``: exact-population
preconditions, dry-run default, audited apply (dual-write DELETE entries on
the sha256 chain), second-instance chain verification, live-writer abort,
and the row classification rule shared with the insert-time guard
(``src/loats/signal_source_guard.py``).

The tests seed a throwaway store shaped like the production finding (43
untagged rows + 1 STRESS-ORD rehearsal row + valid-tagged rows that must
survive) and drive the script's ``main()`` against it. The metrics-port
live-writer probe is seam-monkeypatched in the apply test (the real probe
is network I/O); its abort path is exercised directly.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "purge_legacy_signal_rows.py"

VALID_SOURCES = ["ta", "sentiment", "volatility", "price_action", "options_flow"]


@pytest.fixture(scope="module")
def purge() -> ModuleType:
    spec = importlib.util.spec_from_file_location("purge_f9l03", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["purge_f9l03"] = module
    spec.loader.exec_module(module)
    return module


def _seed_store(data_dir: Path, untagged: int = 42, stress: int = 1) -> None:
    """Create db + empty audit log with the production-finding shape
    (42 untagged rows: 41 sentiment + 1 combined; see EXPECTED_UNTAGGED)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data_dir / "loats.db")
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE signals (
            signal_id TEXT PRIMARY KEY, symbol TEXT, signal_type TEXT,
            strength REAL, timestamp TEXT, indicators TEXT, metadata TEXT,
            confidence REAL, created_at TEXT, created_at_ms INTEGER,
            timestamp_ms INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE modification_counts (
            order_id TEXT PRIMARY KEY, modification_count INTEGER
        )
        """
    )
    # 43 untagged rows: 42 sentiment + 1 combined (production shape)
    for i in range(untagged):
        scan_type = "sentiment" if i < 41 else "combined"
        cur.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"legacy_{i:03d}",
                "NIFTY",
                "BUY",
                0.7,
                "2026-08-14T03:39:12+00:00",
                "{}",
                json.dumps({"scan_type": scan_type, "news_count": 35}),
                None,
                "2026-08-14T03:39:12.669088+00:00",
                1755142752669,
                1755142752669,
            ),
        )
    # Rows that must SURVIVE: valid enum tags (old + modern)
    for i, source in enumerate(VALID_SOURCES):
        cur.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"tagged_old_{i}",
                "NIFTY",
                "SELL",
                0.6,
                "2026-08-15T10:00:00+00:00",
                "{}",
                json.dumps({"scan_type": source, "source": source}),
                0.5,
                "2026-08-15T10:00:00+00:00",
                1755252000000,
                1755252000000,
            ),
        )
    cur.execute(
        "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "modern_001",
            "NIFTY",
            "BUY",
            0.8,
            "2026-09-22T10:00:00+00:00",
            "{}",
            json.dumps({"scan_type": "ta", "source": "ta"}),
            0.9,
            "2026-09-22T10:00:00+00:00",
            1758535200000,
            1758535200000,
        ),
    )
    if stress:
        cur.execute(
            "INSERT INTO modification_counts VALUES ('STRESS-ORD', ?)",
            (stress,),
        )
    con.commit()
    con.close()
    (data_dir / "audit.log").touch()


def _row_counts(db_path: Path) -> tuple[int, int]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        signals = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        stress = con.execute(
            "SELECT COUNT(*) FROM modification_counts WHERE order_id = 'STRESS-ORD'"
        ).fetchone()[0]
    finally:
        con.close()
    return signals, stress


def _run(
    purge: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *flags: str,
    probe: str | None = "BLOCK",
) -> int:
    monkeypatch.setattr(purge, "project_root", tmp_path)
    monkeypatch.setattr(
        purge, "REPORT_PATH", tmp_path / "reports" / "ai-generated" / "r.json"
    )
    monkeypatch.setattr("sys.argv", ["purge_legacy_signal_rows.py", *flags])
    if probe == "BLOCK":
        monkeypatch.setattr(
            purge,
            "_check_live_writer",
            lambda _: "unit-test probe: live writer simulated",
        )
    else:
        monkeypatch.setattr(purge, "_check_live_writer", lambda _: None)
    return purge.main()


def _record(purge: ModuleType) -> dict[str, object]:
    return dict(json.loads(purge.REPORT_PATH.read_text(encoding="utf-8")))


class TestRowClassification:
    def test_missing_and_unknown_tags_are_eligible(self, purge: ModuleType) -> None:
        assert purge._row_is_untagged(None) == (True, "missing_tag")
        assert purge._row_is_untagged("") == (True, "missing_tag")
        assert purge._row_is_untagged("{}") == (True, "missing_tag")
        assert purge._row_is_untagged('{"source": "bogus"}') == (True, "unknown_tag")
        assert purge._row_is_untagged("not json at all") == (
            True,
            "metadata_unparseable",
        )

    def test_valid_and_exempt_tags_are_retained(self, purge: ModuleType) -> None:
        for source in VALID_SOURCES:
            eligible, reason = purge._row_is_untagged(json.dumps({"source": source}))
            assert (eligible, reason) == (False, "valid_tag")
        eligible, reason = purge._row_is_untagged(
            json.dumps({"source": "position_conversion"})
        )
        assert (eligible, reason) == (False, "valid_tag")

    def test_test_provenance_is_retained(self, purge: ModuleType) -> None:
        eligible, reason = purge._row_is_untagged('{"test": "latency"}')
        assert (eligible, reason) == (False, "test_provenance_tag")


class TestDryRun:
    def test_dry_run_is_default_and_reports_exact_population(
        self, purge: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _seed_store(tmp_path / "data")
        before, _ = _row_counts(tmp_path / "data" / "loats.db")
        rc = _run(purge, monkeypatch, tmp_path)
        assert rc == 0
        after, stress = _row_counts(tmp_path / "data" / "loats.db")
        assert after == before, "dry-run must not delete anything"
        assert stress == 1
        record = _record(purge)
        assert record["mode"] == "DRY-RUN"
        assert len(record["eligible"]) == 42  # type: ignore[arg-type]
        assert len(record["retained_with_valid_tag"]) == 5  # type: ignore[arg-type]

    def test_population_drift_aborts_without_force(
        self, purge: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _seed_store(tmp_path / "data", untagged=44)
        rc = _run(purge, monkeypatch, tmp_path)
        assert rc == 2
        record = _record(purge)
        assert any(
            "expected" in str(problem)
            for problem in record["precondition_problems"]  # type: ignore[index]
        )


class TestAuditedApply:
    def test_apply_purges_audits_and_verifies_chain(
        self,
        purge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _seed_store(tmp_path / "data")
        before, _ = _row_counts(tmp_path / "data" / "loats.db")
        # probe=None: simulate a quiet maintenance window (the real probe
        # is network I/O; its abort path is covered in TestLiveWriterGuard)
        rc = _run(purge, monkeypatch, tmp_path, "--apply", probe="QUIET")
        assert rc == 0
        after, stress = _row_counts(tmp_path / "data" / "loats.db")
        assert after == before - 42
        assert stress == 0
        record = _record(purge)
        assert record["mode"] == "APPLY"
        assert record["row_count_before"] == before
        assert record["row_count_after"] == after
        assert record["second_instance_chain_verified"] is True
        assert len(record["deleted_ids"]) == 42  # type: ignore[arg-type]
        # Safety copies exist
        backups = record["backups"]
        assert Path(str(backups["db"])).exists()  # type: ignore[index]
        assert Path(str(backups["audit"])).exists()  # type: ignore[index]

    def test_apply_writes_dual_trail_delete_entries(
        self,
        purge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _seed_store(tmp_path / "data")
        rc = _run(purge, monkeypatch, tmp_path, "--apply", probe="QUIET")
        assert rc == 0
        lines = [
            json.loads(line)
            for line in (
                (tmp_path / "data" / "audit.log")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            if line.strip()
        ]
        assert len(lines) == 43  # 42 signal DELETEs + 1 STRESS-ORD DELETE
        assert all(entry["action"] == "DELETE" for entry in lines)
        assert all(entry["metadata"].get("finding") == "F9-L-03" for entry in lines)
        # F9-M-01 chain: every entry links to the previous hash
        for prev, entry in zip([None, *lines[:-1]], lines, strict=True):
            assert entry["previous_hash"] == (prev["sha256_hash"] if prev else None)
        # The DB trail mirrors the JSONL trail
        con = sqlite3.connect(
            f"file:{tmp_path / 'data' / 'loats.db'}?mode=ro", uri=True
        )
        try:
            rows = con.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action = 'DELETE'"
            ).fetchone()[0]
        finally:
            con.close()
        assert rows == 43

    def test_apply_twice_second_run_finds_drift(
        self,
        purge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _seed_store(tmp_path / "data")
        assert _run(purge, monkeypatch, tmp_path, "--apply", probe="QUIET") == 0
        # Re-run: the eligible population is gone -> exact-population
        # precondition fails (0 != 43) and the script refuses.
        assert _run(purge, monkeypatch, tmp_path, "--apply", probe="QUIET") == 2


class TestLiveWriterGuard:
    def test_live_writer_blocks_apply(
        self, purge: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _seed_store(tmp_path / "data")
        rc = _run(purge, monkeypatch, tmp_path, "--apply")
        assert rc == 2
        record = _record(purge)
        assert "live writer" in str(
            record["precondition_problems"]  # type: ignore[index]
        )
        after, _ = _row_counts(tmp_path / "data" / "loats.db")
        assert after == 48, "blocked apply must not touch rows"


class TestScriptHygiene:
    def test_missing_store_aborts(
        self, purge: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rc = _run(purge, monkeypatch, tmp_path)
        assert rc == 2

    def test_script_is_ascii_clean(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert text.isascii(), "src-ascii gate contract (ADR-0014)"
