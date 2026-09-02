#!/usr/bin/env python3
"""Multi-process stress test for the F8-H-02 Rule-7 per-order ceiling.

Spawns N worker processes that all race to reserve modification budget for
the same order.  SQLite WAL + busy_timeout must make the single-statement
RETURNING UPSERT atomic, so the final count can never exceed max_modifications.

Usage:
    python scripts/stress_rule7_concurrency.py <db_path> [order_id] [workers] [attempts_per_worker]

Prints JSON summary and exits 0 if no overshoot, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if TYPE_CHECKING:
    from loats.database import Database
    from loats.rules import CMPRulesEngine

_db: Database | None = None
_order_id: str | None = None
_rules_engine: CMPRulesEngine | None = None

os.environ.setdefault("OPENALGO_API_KEY", "stress")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "stress")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")


def _worker_init(db_path: str, order_id: str) -> None:
    """Initializer for each worker process: import the heavy modules once."""
    from loats.database import Database
    from loats.rules import rules_engine

    global _db, _order_id, _rules_engine
    _db = Database(
        db_path=Path(db_path),
        audit_log_path=Path(db_path).with_suffix(".jsonl"),
    )
    _order_id = order_id
    _rules_engine = rules_engine


def _attempt_once(_: int) -> dict[str, bool]:
    """Single reservation attempt; returns whether it was accepted."""
    assert _db is not None and _order_id is not None and _rules_engine is not None
    # reserve_modification does a lazy `from .database import db`, so we
    # rebind the module-level singleton to the worker's Database instance.
    import loats.database as _dbmod

    _dbmod.db = _db

    try:
        _rules_engine.reserve_modification(_order_id)
        return {"accepted": True, "rejected": False}
    except Exception as exc:
        # Only count Rule7ModificationLimitError as a clean rejection.
        # Any other exception is a fatal error (e.g. DB lock failure).
        from loats.rules import Rule7ModificationLimitError

        if isinstance(exc, Rule7ModificationLimitError):
            return {"accepted": False, "rejected": True}
        raise


def _rm_f(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:  # nosec B110 - cleanup
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--order-id", default="STRESS-ORD")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()

    from loats.config import get_settings
    from loats.database import Database

    global _db

    limit = get_settings().max_modifications

    # Wipe any pre-existing DB/WAL/SHM/audit files so the test starts fresh.
    db_path = Path(args.db_path)
    _rm_f(db_path)
    _rm_f(Path(str(db_path) + "-wal"))
    _rm_f(Path(str(db_path) + "-shm"))
    _rm_f(db_path.with_suffix(".jsonl"))

    # Main-process DB instance for schema initialization and final count.
    _db = Database(
        db_path=db_path,
        audit_log_path=db_path.with_suffix(".jsonl"),
    )

    total_attempts = args.workers * args.attempts
    with Pool(
        processes=args.workers,
        initializer=_worker_init,
        initargs=(str(db_path), args.order_id),
    ) as pool:
        outcomes = pool.map(_attempt_once, range(total_attempts))

    accepted = sum(1 for o in outcomes if o["accepted"])
    rejected = sum(1 for o in outcomes if o["rejected"])

    # Read the final count from the same DB instance the workers shared.
    final_count = _db.get_modification_count(args.order_id)
    _db.close()

    overshoot = final_count > limit or accepted > limit
    summary = {
        "limit": limit,
        "workers": args.workers,
        "attempts_per_worker": args.attempts,
        "accepted": accepted,
        "rejected": rejected,
        "final_count": final_count,
        "overshoot": overshoot,
    }
    print(json.dumps(summary, indent=2))
    return 1 if overshoot else 0


if __name__ == "__main__":
    sys.exit(main())
