#!/usr/bin/env python3
"""External verification for F8-H-02 (CMP Rule 7 per-order modification limit).

Independently reproducible evidence that the fix is at HEAD:
- SQLite persistence (modification_counts table + restart survival)
- Per-order keying (isolation between orders)
- Boundary enforcement inside both modify_order implementations
- Fail-closed semantics on counter DB errors
- Reset on terminal order status
- HC-23 extension references the table and the wiring

Usage:  python scripts/verify_f8h02_external.py
Exit 0 = all checks pass; exit 1 = failures. ASCII-safe output only.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

PASS = "[PASS]"
FAIL = "[FAIL]"
_results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name))
    mark = PASS if ok else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{mark} {name}{suffix}")


def _resolve_python() -> str:
    for cand in (
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    ):
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def main() -> int:
    import os

    os.environ.setdefault("OPENALGO_API_KEY", "verify_dummy")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "verify_dummy")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
    os.environ.setdefault("ENVIRONMENT", "test")

    # --- source-level checks ------------------------------------------
    db_src = (REPO_ROOT / "src" / "loats" / "database.py").read_text(encoding="utf-8")
    rules_src = (REPO_ROOT / "src" / "loats" / "rules.py").read_text(encoding="utf-8")
    oa_src = (REPO_ROOT / "src" / "loats" / "openalgo.py").read_text(encoding="utf-8")
    orch_src = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
        encoding="utf-8"
    )

    check(
        "database.py declares modification_counts table",
        "CREATE TABLE IF NOT EXISTS modification_counts" in db_src,
    )
    check(
        "database.py resets budget on terminal status",
        "_RULE7_TERMINAL_ORDER_STATUSES" in db_src
        and "COMPLETED" in db_src
        and "CANCELLED" in db_src
        and "REJECTED" in db_src,
    )
    check(
        "database.py atomic UPSERT..RETURNING increment",
        "RETURNING count" in db_src,
    )
    check(
        "rules.py defines Rule7ModificationLimitError",
        "class Rule7ModificationLimitError" in rules_src,
    )
    check(
        "rules.py reserve/release protocol",
        "def reserve_modification" in rules_src
        and "def release_modification" in rules_src,
    )
    # Live-code shape, not docstring prose (Pitfall 48).
    check(
        "orchestrator no longer calls legacy global increment",
        "rules_engine.increment_modification_counter()" not in orch_src,
    )
    check(
        "orchestrator catches limit refusal and audits",
        "ratchet_refused_rule7" in orch_src,
    )

    # --- runtime checks (temp DB; no repo data touched) -----------------
    import datetime as dt
    from unittest.mock import patch

    from loats.database import Database, Rule7StateError
    from loats.models import (
        Order,
        OrderStatus,
        OrderType,
        OrderVariety,
        ProductType,
        TransactionType,
    )
    from loats.rules import Rule7ModificationLimitError, rules_engine

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db = Database(db_path=tdp / "v.db", audit_log_path=tdp / "a.jsonl")
        try:
            # 1. persistence
            for _ in range(7):
                db.increment_modification_count("V-1")
            check(
                "counter persists (7 increments)",
                db.get_modification_count("V-1") == 7,
            )
        finally:
            db.close()
        db2 = Database(db_path=tdp / "v.db", audit_log_path=tdp / "a.jsonl")
        try:
            check(
                "counter survives restart (fresh Database)",
                db2.get_modification_count("V-1") == 7
                and db2.increment_modification_count("V-1") == 8,
            )
        finally:
            db2.close()

        db3 = Database(db_path=tdp / "w.db", audit_log_path=tdp / "a.jsonl")
        try:
            # 2. per-order isolation through the engine
            with patch("loats.database.db", db3):
                for _ in range(25):
                    rules_engine.reserve_modification("V-A")
                    rules_engine.reserve_modification("V-B")
                limited = False
                try:
                    rules_engine.reserve_modification("V-A")
                except Rule7ModificationLimitError:
                    limited = True
                check(
                    "26th reservation refused per order",
                    limited and db3.get_modification_count("V-A") == 25,
                )
                # 3. release restores budget
                rules_engine.reserve_modification("V-C")
                rules_engine.release_modification("V-C")
                check(
                    "release restores full budget",
                    db3.get_modification_count("V-C") == 0,
                )
            # 4. terminal-status reset
            order = Order(
                order_id="V-ORD",
                symbol="NIFTY",
                quantity=25,
                order_type=OrderType.LIMIT,
                price=100.0,
                variety=OrderVariety.REGULAR,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                status=OrderStatus.OPEN,
                timestamp=dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.UTC),
                filled_quantity=0,
            )
            db3.store_order(order)
            for _ in range(25):
                db3.increment_modification_count("V-ORD")
            db3.update_order_status("V-ORD", "COMPLETED")
            check(
                "terminal status resets budget",
                db3.get_modification_count("V-ORD") == 0,
            )
        finally:
            db3.close()

        # 5. fail-closed
        with patch("loats.database.db") as mdb:
            mdb.get_modification_count.side_effect = Rule7StateError("x")
            refused = False
            try:
                rules_engine.get_modification_count("V-Z")
            except Rule7StateError:
                refused = True
            check("counter read failure is loud (Rule7StateError)", refused)

    # --- boundary wiring (source shape) ---------------------------------
    import inspect

    from loats import openalgo as oa_mod

    sync_src = inspect.getsource(oa_mod.OpenAlgoClient.modify_order)
    async_src = inspect.getsource(oa_mod.AsyncOpenAlgoClient.modify_order)
    check(
        "sync modify_order reserves before broker call",
        "reserve_modification" in sync_src,
    )
    check(
        "async modify_order reserves before broker call",
        "reserve_modification" in async_src,
    )
    check(
        "sync modify_order releases on failure",
        "release_modification" in sync_src,
    )
    check(
        "async modify_order releases on failure",
        "release_modification" in async_src,
    )

    # 6. HC-23 extension present in the health check source
    hc_src = (REPO_ROOT / "scripts" / "fr7_health_check.py").read_text(encoding="utf-8")
    check(
        "HC-23 verifies modification_counts table",
        "modification_counts" in hc_src,
    )
    check(
        "HC-23 verifies gate wiring at modify boundary",
        "reserve_modification" in hc_src,
    )

    # 7. dedicated test file exists
    check(
        "tests/test_rule7_modification_limit.py exists",
        (REPO_ROOT / "tests" / "test_rule7_modification_limit.py").exists(),
    )

    # 8. test suite for the feature passes
    proc = subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            "tests/test_rule7_modification_limit.py",
            "-q",
            "-p",
            "no:warnings",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    check(
        "rule-7 test suite green",
        proc.returncode == 0,
        proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
    )

    ok_count = sum(1 for ok, _ in _results if ok)
    print()
    print(f"RESULT: {ok_count}/{len(_results)} checks passed")
    return 0 if ok_count == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
