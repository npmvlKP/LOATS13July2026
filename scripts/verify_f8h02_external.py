#!/usr/bin/env python3
"""External verification for F8-H-02 (CMP Rule 7 per-order modification gate).

Runs from a clean process against the installed package (no test suite
fixtures). Mirrors scripts/verify_f8m02_m07_external.py: exit 0 iff every
check passes; each check asserts the finding's OUTCOME contract, not the
idiom that happens to implement it.

  F8-H-02  per-order persisted Rule-7 modification budget:

    1.  Behavioral - the counter lives in SQLite and survives a full
        Database teardown/rebuild on the same files (restart endurance).
    2.  Behavioral - reserve-before-broker protocol: 25 reservations
        succeed, the 26th is refused (Rule7ModificationLimitError) and
        the budget stays intact at 25 (no over-issue).
    3.  Behavioral - the gate fires at the OpenAlgo client boundary:
        ``OpenAlgoClient.modify_order`` on an exhausted budget raises
        Rule7ModificationLimitError BEFORE any broker call (every
        caller gated, not just the trailing driver).
    4.  Behavioral - fail-closed: a broken counter store refuses the
        modification with Rule7StateError (no silent budget bypass).
    5.  Behavioral - release-on-failure: a broker error refunds the
        reserved slot, so failed attempts never consume budget.
    6.  Behavioral - terminal-status reset: an order stored and closed
        (COMPLETED) gets a fresh budget on the same order_id.
    7.  Mutation net - on a snapshot tree whose ``modify_order`` no
        longer reserves budget, THIS verifier must fail (check 3 red),
        proving it verifies behavior rather than source idioms.

Print-only: writes no artifacts (evidence lives in the suite-wired
tests/test_repo_hygiene.py net and the closure record).

Run:  python scripts/verify_f8h02_external.py
Exit: 0 iff all checks pass.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "verify_dummy")
os.environ.setdefault("OPENALGO_BASE_URL", "https://verify.invalid")
os.environ.setdefault("ENVIRONMENT", "test")

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, note: str = "") -> None:
    results.append((name, ok, note))
    print(f"{PASS_SYM if ok else FAIL_SYM} {name}" + (f"  -- {note}" if note else ""))


def _make_db(tmp: Path, name: str):
    from loats.database import Database

    return Database(db_path=tmp / f"{name}.db", audit_log_path=tmp / f"{name}.audit")


def _order(order_id: str):
    import datetime as dt

    from loats.models import (
        Order,
        OrderStatus,
        OrderType,
        OrderVariety,
        ProductType,
        TransactionType,
    )

    return Order(
        order_id=order_id,
        symbol="NIFTY",
        quantity=25,
        order_type=OrderType.LIMIT,
        price=100.0,
        variety=OrderVariety.REGULAR,
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        status=OrderStatus.OPEN,
        timestamp=dt.datetime(2026, 9, 8, 10, 0, tzinfo=dt.UTC),
        filled_quantity=0,
    )


def _no_broker_breaker():
    breaker = MagicMock()
    breaker.call = MagicMock(
        side_effect=AssertionError("broker must not be reached with exhausted budget")
    )
    return breaker


def check_1_restart_endurance(tmp: Path) -> None:
    from loats.database import Rule7StateError  # noqa: F401  (import parity)

    db = _make_db(tmp, "restart")
    try:
        for _ in range(3):
            db.increment_modification_count("ORD-RESTART")
        db.close()
    except Exception as exc:  # pragma: no cover - diagnostic path
        record("1. persistence survives restart", False, f"increment failed: {exc}")
        return
    # Full rebuild on the same files: a fresh process would construct a
    # new Database instance; the count must come back from SQLite.
    db2 = _make_db(tmp, "restart")
    try:
        count = db2.get_modification_count("ORD-RESTART")
        db2.close()
    except Exception as exc:  # pragma: no cover - diagnostic path
        record("1. persistence survives restart", False, f"read failed: {exc}")
        return
    record(
        "1. persistence survives restart",
        count == 3,
        f"count after rebuild={count}",
    )


def check_2_reserve_protocol(tmp: Path) -> None:
    from loats.database import Rule7StateError  # noqa: F401
    from loats.rules import Rule7ModificationLimitError, rules_engine

    db = _make_db(tmp, "reserve")
    refused = False
    try:
        with patch("loats.database.db", db):
            counts = [
                rules_engine.reserve_modification("ORD-RESERVE") for _ in range(25)
            ]
            try:
                rules_engine.reserve_modification("ORD-RESERVE")
            except Rule7ModificationLimitError:
                refused = True
        after = db.get_modification_count("ORD-RESERVE")
        db.close()
    except Exception as exc:
        record("2. reserve-before-broker caps at limit", False, f"error: {exc}")
        return
    record(
        "2. reserve-before-broker caps at limit",
        refused and counts == list(range(1, 26)) and after == 25,
        f"refused={refused} after_refusal_count={after}",
    )


def check_3_boundary_gate(tmp: Path) -> None:
    from loats.database import Rule7StateError  # noqa: F401
    from loats.openalgo import OpenAlgoClient
    from loats.rules import Rule7ModificationLimitError

    db = _make_db(tmp, "boundary")
    try:
        for _ in range(25):
            db.increment_modification_count("ORD-BOUNDARY")
    except Exception as exc:
        record("3. boundary gate fires at modify_order", False, f"setup: {exc}")
        return

    client = OpenAlgoClient(api_key="verify_dummy", base_url="https://verify.invalid")
    alerts = MagicMock(is_kill_switch_active=MagicMock(return_value=False))
    raised: Exception | None = None
    try:
        with (
            patch("loats.database.db", db),
            patch("loats.openalgo._get_alerts", return_value=alerts),
            patch("loats.openalgo.OPENALGO_CIRCUIT_BREAKER", _no_broker_breaker()),
        ):
            try:
                client.modify_order(
                    order_id="ORD-BOUNDARY",
                    order_type="SL-M",
                    trigger_price=100.0,
                )
            except Rule7ModificationLimitError as exc:
                raised = exc
        db.close()
    except Exception as exc:
        record("3. boundary gate fires at modify_order", False, f"error: {exc}")
        return
    record(
        "3. boundary gate fires at modify_order",
        isinstance(raised, Rule7ModificationLimitError),
        f"raised={type(raised).__name__ if raised else 'NOTHING'}",
    )


def check_4_fail_closed(tmp: Path) -> None:
    from loats.database import Rule7StateError
    from loats.openalgo import OpenAlgoClient
    from loats.rules import Rule7ModificationLimitError  # noqa: F401

    broken = MagicMock()
    broken.increment_modification_count = MagicMock(
        side_effect=Rule7StateError("simulated counter store failure")
    )
    client = OpenAlgoClient(api_key="verify_dummy", base_url="https://verify.invalid")
    alerts = MagicMock(is_kill_switch_active=MagicMock(return_value=False))
    raised: Exception | None = None
    try:
        with (
            patch("loats.database.db", broken),
            patch("loats.openalgo._get_alerts", return_value=alerts),
            patch("loats.openalgo.OPENALGO_CIRCUIT_BREAKER", _no_broker_breaker()),
        ):
            try:
                client.modify_order(
                    order_id="ORD-BROKEN",
                    order_type="SL-M",
                    trigger_price=100.0,
                )
            except Rule7StateError as exc:
                raised = exc
    except Exception as exc:
        record("4. fail-closed on counter store failure", False, f"error: {exc}")
        return
    record(
        "4. fail-closed on counter store failure",
        isinstance(raised, Rule7StateError),
        f"raised={type(raised).__name__ if raised else 'NOTHING'}",
    )


def check_5_release_on_failure(tmp: Path) -> None:
    from loats.openalgo import OpenAlgoClient

    db = _make_db(tmp, "release")
    breaker = MagicMock()
    breaker.call = MagicMock(side_effect=RuntimeError("simulated broker failure"))
    client = OpenAlgoClient(api_key="verify_dummy", base_url="https://verify.invalid")
    alerts = MagicMock(is_kill_switch_active=MagicMock(return_value=False))
    propagated: Exception | None = None
    try:
        with (
            patch("loats.database.db", db),
            patch("loats.openalgo._get_alerts", return_value=alerts),
            patch("loats.openalgo.OPENALGO_CIRCUIT_BREAKER", breaker),
        ):
            try:
                client.modify_order(
                    order_id="ORD-RELEASE",
                    order_type="SL-M",
                    trigger_price=100.0,
                )
            except RuntimeError as exc:
                propagated = exc
        count = db.get_modification_count("ORD-RELEASE")
        db.close()
    except Exception as exc:
        record("5. broker failure refunds the reserved slot", False, f"error: {exc}")
        return
    record(
        "5. broker failure refunds the reserved slot",
        isinstance(propagated, RuntimeError) and count == 0,
        f"propagated={type(propagated).__name__ if propagated else 'NOTHING'} count={count}",
    )


def check_6_terminal_reset(tmp: Path) -> None:
    from loats.database import Rule7StateError  # noqa: F401

    db = _make_db(tmp, "terminal")
    fresh = -1
    ok = False
    detail = ""
    try:
        db.store_order(_order("ORD-TERMINAL"))
        for _ in range(25):
            db.increment_modification_count("ORD-TERMINAL")
        if db.update_order_status("ORD-TERMINAL", "COMPLETED") is not True:
            detail = "update_order_status did not confirm closure"
        else:
            after_close = db.get_modification_count("ORD-TERMINAL")
            fresh = db.increment_modification_count("ORD-TERMINAL")
            ok = after_close == 0 and fresh == 1
            detail = f"after_close={after_close} fresh_budget_first={fresh}"
        db.close()
    except Exception as exc:
        record("6. terminal status grants a fresh budget", False, f"error: {exc}")
        return
    record("6. terminal status grants a fresh budget", ok, detail)


def check_7_mutation_net(tmp: Path) -> None:
    """On a snapshot with the boundary gate stripped, THIS verifier fails."""
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td) / "snap"
        (tree / "scripts").mkdir(parents=True)
        for script in (REPO_ROOT / "scripts").glob("*.py"):
            shutil.copy2(script, tree / "scripts" / script.name)
        shutil.copytree(
            REPO_ROOT / "src" / "loats",
            tree / "src" / "loats",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        target = tree / "src" / "loats" / "openalgo.py"
        src = target.read_text(encoding="utf-8")
        anchor = "rules_engine.reserve_modification(order_id)"
        if anchor not in src:
            record("7. mutation net catches gate stripping", False, "anchor missing")
            return
        target.write_text(
            src.replace(anchor, "pass  # F8-H-02 gate stripped by mutation"),
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [sys.executable, str(tree / "scripts" / "verify_f8h02_external.py")],
                capture_output=True,
                text=True,
                cwd=tree,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            record("7. mutation net catches gate stripping", False, "timeout")
            return
        failed_boundary = "[FAIL] 3. boundary gate fires at modify_order" in proc.stdout
        record(
            "7. mutation net catches gate stripping",
            proc.returncode != 0 and failed_boundary,
            f"rc={proc.returncode} boundary_check_red={failed_boundary}",
        )


def main() -> int:
    print("=" * 72)
    print("F8-H-02 EXTERNAL VERIFICATION - CMP Rule 7 per-order budget")
    print("=" * 72)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        check_1_restart_endurance(tmp)
        check_2_reserve_protocol(tmp)
        check_3_boundary_gate(tmp)
        check_4_fail_closed(tmp)
        check_5_release_on_failure(tmp)
        check_6_terminal_reset(tmp)
        check_7_mutation_net(tmp)
    print("-" * 72)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"RESULT: {passed}/{len(results)} checks passed")
    if failed:
        print("STATUS : FAILURES PRESENT - Rule-7 gate NOT verified live")
        return 1
    print("STATUS : ALL CHECKS PASSED - Rule-7 per-order gate verified live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
