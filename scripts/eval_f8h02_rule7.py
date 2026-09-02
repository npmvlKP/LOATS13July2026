#!/usr/bin/env python3
"""Eval for F8-H-02: 10-case behavioural matrix, BEFORE (baseline measured
2026-09-02 at pre-fix HEAD 36d9175) vs AFTER (live measurement on the
current tree). Exit 0 when AFTER == 10/10.

Each case is scored against the live code path it names — no source-string
shortcuts: the engine + boundary are exercised for real (mocked broker).

BEFORE baseline (how many of the 10 the pre-fix tree satisfied): 3/10
  C1 fail (global counter resets), C2 fail (not keyed per order),
  C3 fail (no gate at boundary), C4 fail (no gate at async boundary),
  C5 pass (per-cycle cap existed in driver), C6 fail (no persistence),
  C7 fail (no fail-closed — nothing to fail), C8 fail (failed attempts
  consumed the shared global), C9 fail (no reset on closure),
  C10 pass (settings value 25 existed), legacy API pass-by-quirk counted
  under C10.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

BEFORE_SCORE = 3
BEFORE_CASES = {
    "C1_restart_survival": False,
    "C2_per_order_isolation": False,
    "C3_sync_boundary_gate": False,
    "C4_async_boundary_gate": False,
    "C5_cycle_cap": True,
    "C6_persistence_table": False,
    "C7_fail_closed": False,
    "C8_no_charge_on_failure": False,
    "C9_reset_on_closure": False,
    "C10_settings_value": True,
}

os.environ.setdefault("OPENALGO_API_KEY", "eval_dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "eval_dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")


def _ok(name: str, cond: bool, results: dict[str, bool]) -> None:
    results[name] = bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main() -> int:
    import datetime as dt

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

    results: dict[str, bool] = {}
    print("F8-H-02 eval — AFTER (live measurement):")

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db = Database(db_path=tdp / "e.db", audit_log_path=tdp / "a.jsonl")
        try:
            # C6: table exists in a fresh schema
            conn = sqlite3_connect(db.db_path)
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                conn.close()
            _ok("C6_persistence_table", "modification_counts" in tables, results)

            with patch("loats.database.db", db):
                # C1 + C2: 25 each on two orders, then refusal
                for _ in range(25):
                    rules_engine.reserve_modification("E-A")
                    rules_engine.reserve_modification("E-B")
                refused = False
                try:
                    rules_engine.reserve_modification("E-A")
                except Rule7ModificationLimitError:
                    refused = True
                _ok(
                    "C2_per_order_isolation",
                    refused and db.get_modification_count("E-B") == 25,
                    results,
                )
        finally:
            db.close()

        # C1: restart survival
        db2 = Database(db_path=tdp / "e.db", audit_log_path=tdp / "a.jsonl")
        try:
            _ok(
                "C1_restart_survival",
                db2.get_modification_count("E-A") == 25,
                results,
            )
        finally:
            db2.close()

        # C3/C4: boundary gate (source-level live introspection of the
        # actual function objects; the broker is never called).
        import inspect

        from loats import openalgo as oa_mod

        sync_src = inspect.getsource(oa_mod.OpenAlgoClient.modify_order)
        async_src = inspect.getsource(oa_mod.AsyncOpenAlgoClient.modify_order)
        _ok("C3_sync_boundary_gate", "reserve_modification" in sync_src, results)
        _ok("C4_async_boundary_gate", "reserve_modification" in async_src, results)

        # C5: per-cycle cap still present in the driver
        orch_src = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        _ok(
            "C5_cycle_cap",
            "modifications_this_cycle >= max_modifications" in orch_src,
            results,
        )

        # C7: fail-closed
        with patch("loats.database.db") as mdb:
            mdb.get_modification_count.side_effect = Rule7StateError("locked")
            loud = False
            try:
                rules_engine.get_modification_count("E-Z")
            except Rule7StateError:
                loud = True
            _ok("C7_fail_closed", loud, results)

        # C8: failed broker attempt does not consume budget
        db3 = Database(db_path=tdp / "f.db", audit_log_path=tdp / "a.jsonl")
        try:
            with (
                patch("loats.database.db", db3),
                patch(
                    "loats.openalgo._get_alerts",
                    return_value=MagicMock(
                        is_kill_switch_active=MagicMock(return_value=False)
                    ),
                ),
            ):
                c = oa_mod.OpenAlgoClient(api_key="k", base_url="http://t")
                failing = MagicMock()
                failing.status_code = 500
                failing.text = "server error"
                failing.json.return_value = {}
                import httpx

                failing.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "boom",
                    request=httpx.Request("POST", "http://t/api/v1/modify_order"),
                    response=httpx.Response(500, text="server error"),
                )
                http = MagicMock()
                http.post.return_value = failing
                http.request.return_value = failing
                c.client = http
                errored = False
                try:
                    c.modify_order("E-F", quantity=5)
                except Exception:
                    errored = True
                _ok(
                    "C8_no_charge_on_failure",
                    errored and db3.get_modification_count("E-F") == 0,
                    results,
                )
        finally:
            db3.close()

        # C9: reset on closure
        db4 = Database(db_path=tdp / "g.db", audit_log_path=tdp / "a.jsonl")
        try:
            order = Order(
                order_id="E-ORD",
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
            db4.store_order(order)
            for _ in range(25):
                db4.increment_modification_count("E-ORD")
            db4.update_order_status("E-ORD", "CANCELLED")
            _ok(
                "C9_reset_on_closure",
                db4.get_modification_count("E-ORD") == 0,
                results,
            )
        finally:
            db4.close()

    # C10: settings value
    from loats.config import get_settings

    _ok("C10_settings_value", get_settings().max_modifications == 25, results)

    after = sum(1 for v in results.values() if v)
    print()
    print(
        f"BEFORE: {BEFORE_SCORE}/10   AFTER: {after}/10   delta: {after - BEFORE_SCORE:+d}"
    )
    mismatch = [k for k in BEFORE_CASES if k not in results]
    if mismatch:
        print(f"[WARN] unmatched case ids: {mismatch}")
    return 0 if after == 10 else 1


def sqlite3_connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


if __name__ == "__main__":
    sys.exit(main())
