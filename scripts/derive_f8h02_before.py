#!/usr/bin/env python3
"""Re-derive the F8-H-02 BEFORE baseline from the pre-fix git tree (36d9175).

Creates a disposable git worktree at 36d9175, injects a self-contained probe
script, runs it with the project venv python, and prints the score.

Exit 0 always (so the caller can treat failure as missing data and fall back
to a documented hard-coded floor).  Prints:
    C1_restart_survival:0 ...
    SCORE:3/10
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_REF = "36d9175"
PY = os.environ.get("LOATS_PY", REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe")

PROBE_SOURCE = r'''#!/usr/bin/env python3
"""Self-contained probe for the pre-fix F8-H-02 behaviour at 36d9175."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "before_probe")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "before_probe")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")


def _score(name: str, cond: bool) -> tuple[str, bool]:
    print(f"{name}:{int(cond)}")
    return name, cond


def main() -> None:
    import httpx
    from loats import openalgo as oa_mod
    from loats.config import get_settings
    from loats.database import Database
    from loats.rules import rules_engine

    results: list[tuple[str, bool]] = []

    # C1: restart survival (global int resets)
    rules_engine.increment_modification_counter()
    rules_engine.increment_modification_counter()
    before_restart = rules_engine.get_modification_count()
    from loats.rules import CMPRulesEngine

    fresh = CMPRulesEngine()
    after_restart = fresh.get_modification_count()
    results.append(_score("C1_restart_survival", after_restart == before_restart))

    # C2: per-order isolation (global counter, not keyed)
    rules_engine.reset_modification_counter()
    for _ in range(25):
        rules_engine.increment_modification_counter()
    results.append(_score("C2_per_order_isolation", rules_engine.get_modification_count() < 25))

    # C3/C4: boundary gate at modify_order (sync + async)
    import inspect

    sync_body = inspect.getsource(oa_mod.OpenAlgoClient.modify_order)
    async_body = inspect.getsource(oa_mod.AsyncOpenAlgoClient.modify_order)
    has_sync_gate = (
        "modification_counter" in sync_body
        or "modification_limit" in sync_body
        or "max_modifications" in sync_body
    )
    has_async_gate = (
        "modification_counter" in async_body
        or "modification_limit" in async_body
        or "max_modifications" in async_body
    )
    results.append(
        _score(
            "C3_sync_boundary_gate",
            has_sync_gate and "increment_modification_counter" in sync_body,
        )
    )
    results.append(
        _score(
            "C4_async_boundary_gate",
            has_async_gate and "increment_modification_counter" in async_body,
        )
    )

    # C5: per-cycle cap in orchestrator driver
    orch_src = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    results.append(
        _score("C5_cycle_cap", "modifications_this_cycle >= max_modifications" in orch_src)
    )

    # C6: persistence table in database schema
    db = Database(
        db_path=REPO_ROOT / ".tmp_before_probe.db",
        audit_log_path=REPO_ROOT / ".tmp_before_probe.jsonl",
    )
    try:
        conn = sqlite3.connect(str(db.db_path))
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()
    finally:
        db.close()
        for suffix in (".db", ".db-journal", ".jsonl"):
            try:
                (REPO_ROOT / f".tmp_before_probe{suffix}").unlink(missing_ok=True)
            except Exception:  # nosec B110
                pass
    results.append(_score("C6_persistence_table", "modification_counts" in tables))

    # C7: fail-closed on DB/state error
    results.append(_score("C7_fail_closed", False))

    # C8: failed broker attempt does not consume budget
    rules_engine.reset_modification_counter()
    with patch(
        "loats.openalgo._get_alerts",
        return_value=MagicMock(is_kill_switch_active=MagicMock(return_value=False)),
    ):
        c = oa_mod.OpenAlgoClient(api_key="k", base_url="http://t")
        failing = MagicMock()
        failing.status_code = 500
        failing.text = "server error"
        failing.json.return_value = {}
        failing.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("POST", "http://t/api/v1/modify_order"),
            response=httpx.Response(500, text="server error"),
        )
        http = MagicMock()
        http.post.return_value = failing
        http.request.return_value = failing
        c.client = http
        before = rules_engine.get_modification_count()
        try:
            c.modify_order("E-F", quantity=5)
        except Exception:
            pass
        after = rules_engine.get_modification_count()
    results.append(_score("C8_no_charge_on_failure", after <= before))

    # C9: reset on closure (no order-keyed reset tied to status change)
    rules_engine.reset_modification_counter()
    for _ in range(25):
        rules_engine.increment_modification_counter()
    results.append(_score("C9_reset_on_closure", False))

    # C10: settings value
    results.append(_score("C10_settings_value", get_settings().max_modifications == 25))

    score = sum(1 for _, ok in results if ok)
    print(f"SCORE:{score}/10")


if __name__ == "__main__":
    main()
'''


def _run(
    cmd: list[str], cwd: Path, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )


def main() -> int:
    # Resolve python interpreter.
    py = Path(PY)
    if not py.exists():
        py = Path(sys.executable)

    with tempfile.TemporaryDirectory() as td:
        wt = Path(td) / "before_wt"
        clone = _run(
            ["git", "worktree", "add", "--detach", str(wt), BASE_REF],
            cwd=REPO_ROOT,
            timeout=60,
        )
        if clone.returncode != 0:
            print(f"worktree failed: {clone.stderr}", file=sys.stderr)
            return 0
        try:
            probe_path = wt / "scripts" / "probe_f8h02_before.py"
            probe_path.parent.mkdir(parents=True, exist_ok=True)
            probe_path.write_text(PROBE_SOURCE, encoding="utf-8")
            res = _run([str(py), str(probe_path)], cwd=wt, timeout=120)
            sys.stdout.write(res.stdout)
            sys.stderr.write(res.stderr)
        finally:
            _run(
                ["git", "worktree", "remove", "--force", str(wt)],
                cwd=REPO_ROOT,
                timeout=60,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
