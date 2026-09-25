"""Transaction-hygiene pins: a failed DML must leave NO open write
transaction on the connection it used.

Root cause (25Sep2026, benchmark PARTIAL 8/10 at ``ba4febd``): sync
writers with no rollback on the error path left the implicit transaction
OPEN on their thread-local connection; in multi-threaded consumers
(benchmark comprehensive analysis) the next writer on a DIFFERENT thread
stalled for the full 30 s busy_timeout ("database is locked"). Two runs
of the same commit produced 12:59 PARTIAL vs 13:13 PASS -- the grading
blast radius is nondeterministic because it depends on which sample
window catches the stall. The rollback-on-error idiom already existed in
this module (``_store_ratchet_event``); these tests pin it onto every
error path instead of letting each new writer re-invent it.
"""

from __future__ import annotations

import datetime
import sqlite3
import threading
from pathlib import Path

import pytest

from src.loats.database import Database
from src.loats.models import HistoricalData

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def xdb(db: Database):
    """``db`` plus cross-thread teardown: worker threads in these tests
    create their own thread-local connections, which the shared ``db``
    fixture's single-thread ``close()`` does not reach (Windows holds the
    file lock and the temp-dir teardown errors)."""
    yield db
    db.close_all()


def _dup_signal(sample_signal, signal_id: str):
    """A production-valid signal copy with a pinned, colliding id."""
    return sample_signal.model_copy(update={"signal_id": signal_id})


class TestSyncWriterRollsBackOnError:
    """A failed INSERT must roll back before the exception propagates."""

    def test_failed_signal_insert_releases_the_write_lock(
        self, xdb: Database, sample_signal
    ) -> None:
        db = xdb
        first = _dup_signal(sample_signal, "txn_hygiene_dup")
        second = _dup_signal(sample_signal, "txn_hygiene_dup")
        assert db.create_signal(first) is True

        with pytest.raises(sqlite3.IntegrityError):
            db.create_signal(second)

        # THE PIN: the failed INSERT must not leave the transaction open
        # on the thread-local connection this call used.
        conn = db._get_connection()
        assert conn.in_transaction is False, (
            "create_signal left an open transaction after a failed INSERT; "
            "the connection holds SQLite's write lock until the next "
            "commit/rollback on that thread"
        )

    def test_failed_historical_insert_releases_the_write_lock(
        self, xdb: Database
    ) -> None:
        db = xdb
        # NOT NULL violation via model_construct (bypasses pydantic
        # validation; the DB-level constraint is the thing under test).
        bad = HistoricalData.model_construct(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 15),
            open=100.0,
            high=101.0,
            low=99.0,
            close=None,
            volume=1000,
            interval="1min",
        )
        conn = db._get_connection()
        with pytest.raises(sqlite3.IntegrityError):
            db.store_historical_data([bad])

        assert conn.in_transaction is False, (
            "store_historical_data left an open transaction after a failed INSERT"
        )


class TestNoCrossThreadStarvation:
    """One thread's failed write must not starve another thread's write.

    Regression shape found live 25Sep2026: the UNIQUE violation on one
    thread kept ITS thread-local transaction open; writers on other
    threads then waited the full 30 s busy_timeout each ("database is
    locked"), which is what turned a single bad sample into a PARTIAL
    benchmark verdict.
    """

    def test_failed_insert_does_not_starve_other_threads(
        self, xdb: Database, sample_signal
    ) -> None:
        db = xdb
        poison_entered = threading.Event()
        poison_release = threading.Event()
        writer_done = threading.Event()
        errors: list[BaseException] = []

        # Pre-create the row the poison thread will collide with, so its
        # write fails with the UNIQUE violation (the leak trigger).
        assert db.create_signal(_dup_signal(sample_signal, "txn_starve_dup")) is True

        def poison() -> None:
            try:
                db.create_signal(_dup_signal(sample_signal, "txn_starve_dup"))
            except sqlite3.IntegrityError as exc:  # expected
                errors.append(exc)
            poison_entered.set()
            # Stay alive holding this thread's thread-local connection so
            # the leaked transaction (if any) is observable deterministically.
            poison_release.wait(timeout=10)

        def independent_writer() -> None:
            try:
                fresh = _dup_signal(sample_signal, "txn_starve_fresh")
                db.create_signal(fresh)
                writer_done.set()
            except BaseException as exc:
                errors.append(exc)

        t1 = threading.Thread(target=poison, name="poison")
        t2: threading.Thread | None = None
        t1.start()
        try:
            assert poison_entered.wait(timeout=10), "poison thread never ran"
            # The poison write must actually have failed with the UNIQUE
            # violation (guards the fixture against silent-pass drift).
            assert any(isinstance(e, sqlite3.IntegrityError) for e in errors), errors

            t2 = threading.Thread(target=independent_writer, name="writer")
            t2.start()
            # 5 s is far below the 30 s busy_timeout: any wait here means
            # the poison thread's leaked transaction is blocking writers.
            assert writer_done.wait(timeout=5), (
                "independent writer starved by a leaked write transaction "
                "from the failed INSERT on another thread"
            )
        finally:
            poison_release.set()
            t1.join(timeout=10)
            if t2 is not None:
                t2.join(timeout=10)


class TestBenchmarkIdUniqueness:
    """Benchmark signal ids must be iteration-unique by construction.

    The id templates previously used wall-clock milliseconds; the sync
    and async create legs of the same benchmark iteration collide when
    they execute within the same millisecond (found live 25Sep2026:
    "UNIQUE constraint failed: signals.signal_id" at 13:10:54, the
    poison step of the starvation cascade). The templates must be built
    from ``uuid4().hex`` -- unique per call, wall-clock independent.
    """

    def test_id_templates_are_uuid_based(self) -> None:
        analyzer_src = (
            REPO_ROOT / "src" / "loats" / "performance_analyzer.py"
        ).read_text(encoding="utf-8")
        script_src = (REPO_ROOT / "scripts" / "benchmark_performance.py").read_text(
            encoding="utf-8"
        )

        # The analyzer module owns the benchmark id templates (all three
        # create legs); the script only drives it. The script's pin is the
        # negative half: it must never grow a wall-clock template of its own.
        assert "uuid4().hex" in analyzer_src, (
            "performance_analyzer.py no longer mints benchmark ids from "
            "uuid4; the wall-clock millisecond template collides across "
            "the sync/async legs of one iteration"
        )
        for name, src in (
            ("performance_analyzer.py", analyzer_src),
            ("benchmark_performance.py", script_src),
        ):
            assert "int(time.time() * 1000)}" not in src, (
                f"{name} still derives a benchmark signal id from "
                "wall-clock milliseconds (deterministic UNIQUE collision)"
            )
