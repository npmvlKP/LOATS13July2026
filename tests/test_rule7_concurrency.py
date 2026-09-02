"""Multi-process stress test for the Rule-7 per-order modification ceiling."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe"
STRESS = REPO_ROOT / "scripts" / "stress_rule7_concurrency.py"


@pytest.mark.skipif(not PY.exists(), reason="project venv not present")
def test_rule7_concurrent_reservations_never_overshoot() -> None:
    """
    Many worker processes racing to reserve the same order's budget must not
    exceed max_modifications (25).  This exercises SQLite's database-level
    write lock + the single-statement RETURNING UPSERT gate.
    """
    db = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "test_r7_concurrency.db"
    )
    for path in [
        db,
        Path(str(db) + "-wal"),
        Path(str(db) + "-shm"),
        db.with_suffix(".jsonl"),
    ]:
        path.unlink(missing_ok=True)

    try:
        proc = subprocess.run(
            [str(PY), str(STRESS), str(db), "--workers", "8", "--attempts", "6"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        assert proc.returncode == 0, f"stress script failed: {proc.stderr}"
        lines = proc.stdout.splitlines()
        json_start = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("{")), None
        )
        assert json_start is not None, "no JSON object in stress script stdout"
        summary = json.loads("\n".join(lines[json_start:]))
        assert summary["overshoot"] is False
        assert summary["accepted"] == summary["limit"]
        assert summary["final_count"] == summary["limit"]
    finally:
        for path in [
            db,
            Path(str(db) + "-wal"),
            Path(str(db) + "-shm"),
            db.with_suffix(".jsonl"),
        ]:
            path.unlink(missing_ok=True)
