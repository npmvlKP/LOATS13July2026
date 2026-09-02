"""CMP Rule 7 per-order modification limit tests (F8-H-02).

Covers the three defects the old implementation had:
1. Persistence  — the counter lives in SQLite (``modification_counts``),
   so it survives process restarts.
2. Per-order keying — one busy order cannot consume another's budget.
3. Boundary enforcement — the gate runs inside ``modify_order`` itself
   (sync + async), not only in the trailing driver; DB failures fail
   CLOSED (modification refused), and failed broker attempts release
   their reserved slot.
"""

from __future__ import annotations

import collections.abc
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import loats.openalgo as oa
from loats.database import Database, Rule7StateError
from loats.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderVariety,
    ProductType,
    TransactionType,
)
from loats.openalgo import AsyncOpenAlgoClient, OpenAlgoClient
from loats.rules import Rule7ModificationLimitError, rules_engine
from loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER


@pytest.fixture(autouse=True)
def _reset_state() -> collections.abc.Generator[None, None, None]:
    """Isolate global circuit breaker state per test."""
    OPENALGO_CIRCUIT_BREAKER.reset()
    yield
    OPENALGO_CIRCUIT_BREAKER.reset()


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _make_db(tmp_path: Path) -> Database:
    return Database(
        db_path=tmp_path / "rule7.db",
        audit_log_path=tmp_path / "audit.jsonl",
    )


def _patch_db(database: Database):
    """Point loats.database.db (lazy singleton) at our isolated Database."""
    return patch("loats.database.db", database)


def _mock_response(payload: dict[str, Any], status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok"
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _sync_client(response: MagicMock | None = None) -> OpenAlgoClient:
    c = OpenAlgoClient(api_key="k", base_url="http://t")
    if response is not None:
        c.client = _sync_http(response)
    return c


def _sync_http(response: MagicMock) -> MagicMock:
    http = MagicMock()
    http.post.return_value = response
    http.request.return_value = response
    return http


def _async_client(response: MagicMock | None = None) -> AsyncOpenAlgoClient:
    c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
    if response is not None:
        c.client = _async_http(response)
    return c


def _async_http(response: MagicMock) -> AsyncMock:
    http = AsyncMock()
    http.post.return_value = response
    http.request.return_value = response
    return http


def _alerts_ok() -> MagicMock:
    return MagicMock(is_kill_switch_active=MagicMock(return_value=False))


def _order(order_id: str) -> Order:
    import datetime as dt

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
        timestamp=dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.UTC),
        filled_quantity=0,
    )


# --------------------------------------------------------------------- #
# 1. Persistence: counter survives "restart"
# --------------------------------------------------------------------- #


class TestCounterPersistence:
    def test_count_survives_db_reconstruction(self, tmp_path: Path) -> None:
        db1 = _make_db(tmp_path)
        for _ in range(7):
            assert db1.increment_modification_count("ORD-R") > 0
        count_before = db1.get_modification_count("ORD-R")
        db1.close()

        # Simulate a process restart: fresh Database over the same file.
        db2 = _make_db(tmp_path)
        try:
            assert db2.get_modification_count("ORD-R") == count_before == 7
            assert db2.increment_modification_count("ORD-R") == 8
        finally:
            db2.close()

    def test_table_exists_in_schema(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            conn = sqlite3.connect(db.db_path)
            try:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='modification_counts'"
                )
                assert cur.fetchone() is not None
            finally:
                conn.close()
        finally:
            db.close()

    def test_get_returns_zero_for_unknown_order(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            assert db.get_modification_count("ORD-UNKNOWN") == 0
        finally:
            db.close()


# --------------------------------------------------------------------- #
# 2. Per-order isolation via the rules engine
# --------------------------------------------------------------------- #


class TestPerOrderIsolation:
    def test_two_orders_25_each_then_26th_rejected(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            with _patch_db(db):
                for order_id in ("ORD-A", "ORD-B"):
                    for _ in range(25):
                        rules_engine.reserve_modification(order_id)
                    # 25 reached: next reservation must be refused.
                    with pytest.raises(Rule7ModificationLimitError):
                        rules_engine.reserve_modification(order_id)
        finally:
            db.close()

    def test_check_modification_limit_reflects_persisted_state(
        self, tmp_path: Path
    ) -> None:
        db = _make_db(tmp_path)
        try:
            with _patch_db(db):
                assert rules_engine.check_modification_limit("ORD-C")
                for _ in range(25):
                    rules_engine.reserve_modification("ORD-C")
                assert not rules_engine.check_modification_limit("ORD-C")
        finally:
            db.close()

    def test_release_restores_budget(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            with _patch_db(db):
                rules_engine.reserve_modification("ORD-D")
                rules_engine.release_modification("ORD-D")
                assert db.get_modification_count("ORD-D") == 0
                # Full budget available again after the failed attempt.
                for _ in range(25):
                    rules_engine.reserve_modification("ORD-D")
                with pytest.raises(Rule7ModificationLimitError):
                    rules_engine.reserve_modification("ORD-D")
        finally:
            db.close()

    def test_reserve_never_exceeds_ceiling_in_db(self, tmp_path: Path) -> None:
        """The rolled-back over-budget reservation leaves count == 25."""
        db = _make_db(tmp_path)
        try:
            with _patch_db(db):
                for _ in range(25):
                    rules_engine.reserve_modification("ORD-E")
                for _ in range(5):
                    with pytest.raises(Rule7ModificationLimitError):
                        rules_engine.reserve_modification("ORD-E")
                assert db.get_modification_count("ORD-E") == 25
        finally:
            db.close()


# --------------------------------------------------------------------- #
# 3. Fail-closed on DB error
# --------------------------------------------------------------------- #


class TestFailClosed:
    def test_db_error_on_read_refuses_modification(self) -> None:
        with patch("loats.database.db") as mdb:
            mdb.get_modification_count.side_effect = Rule7StateError(
                "database is locked"
            )
            with pytest.raises(Rule7StateError):
                rules_engine.get_modification_count("ORD-F")

    def test_db_error_on_increment_refuses_and_raises(self) -> None:
        with patch("loats.database.db") as mdb:
            mdb.increment_modification_count.side_effect = Rule7StateError("boom")
            with pytest.raises(Rule7StateError):
                rules_engine.reserve_modification("ORD-G")

    def test_sync_modify_order_fails_closed_on_counter_error(self) -> None:
        c = _sync_client(_mock_response({"status": "success", "data": {}}))
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_ok()),
            patch("loats.rules.rules_engine") as mre,
        ):
            mre.reserve_modification.side_effect = Rule7StateError("db down")
            with pytest.raises(Rule7StateError):
                c.modify_order("ORD-H", quantity=20)
        c.client.post.assert_not_called()

    def test_async_modify_order_fails_closed_on_counter_error(self) -> None:
        import asyncio

        c = _async_client(_mock_response({"status": "success", "data": {}}))
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_ok()),
            patch("loats.rules.rules_engine") as mre,
        ):
            mre.reserve_modification.side_effect = Rule7StateError("db down")
            with pytest.raises(Rule7StateError):
                asyncio.run(c.modify_order("ORD-I", price=3.0))
        c.client.post.assert_not_called()


# --------------------------------------------------------------------- #
# 4. Boundary enforcement inside modify_order itself
# --------------------------------------------------------------------- #


class TestBoundaryEnforcement:
    def test_26th_sync_modify_raises(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ok = _mock_response({"status": "success", "data": {}})
            with (
                _patch_db(db),
                patch("loats.openalgo._get_alerts", return_value=_alerts_ok()),
            ):
                c = _sync_client(ok)
                for _ in range(25):
                    c.modify_order("ORD-J", quantity=20)
                with pytest.raises(Rule7ModificationLimitError):
                    c.modify_order("ORD-J", quantity=20)
                assert db.get_modification_count("ORD-J") == 25
        finally:
            db.close()

    def test_26th_async_modify_raises(self, tmp_path: Path) -> None:
        import asyncio

        db = _make_db(tmp_path)
        try:
            ok = _mock_response({"status": "success", "data": {}})
            with (
                _patch_db(db),
                patch("loats.openalgo._get_alerts", return_value=_alerts_ok()),
            ):
                c = _async_client(ok)
                for _ in range(25):
                    asyncio.run(c.modify_order("ORD-K", price=1.0))
                with pytest.raises(Rule7ModificationLimitError):
                    asyncio.run(c.modify_order("ORD-K", price=1.0))
        finally:
            db.close()


# --------------------------------------------------------------------- #
# 5. Release on broker failure
# --------------------------------------------------------------------- #


class TestReleaseOnBrokerFailure:
    def test_sync_failed_broker_call_releases_slot(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            import httpx

            failing = MagicMock()
            failing.status_code = 500
            failing.text = "server error"
            failing.json.return_value = {}
            failing.raise_for_status.side_effect = httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "http://t/api/v1/modify_order"),
                response=httpx.Response(500, text="server error"),
            )
            with (
                _patch_db(db),
                patch("loats.openalgo._get_alerts", return_value=_alerts_ok()),
            ):
                c = _sync_client(failing)
                with pytest.raises(oa.OpenAlgoError, match="API Error 500"):
                    c.modify_order("ORD-L", quantity=5)
                assert db.get_modification_count("ORD-L") == 0
                # Full budget still available.
                ok = _mock_response({"status": "success", "data": {}})
                c2 = _sync_client(ok)
                c2.modify_order("ORD-L", quantity=5)
                assert db.get_modification_count("ORD-L") == 1
        finally:
            db.close()


# --------------------------------------------------------------------- #
# 6. Reset on order closure
# --------------------------------------------------------------------- #


class TestResetOnOrderClosure:
    def test_terminal_status_resets_counter(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            db.store_order(_order("ORD-M"))
            for _ in range(25):
                db.increment_modification_count("ORD-M")
            assert db.get_modification_count("ORD-M") == 25
            assert db.update_order_status("ORD-M", "COMPLETED") is True
            assert db.get_modification_count("ORD-M") == 0
            # Fresh budget after closure.
            assert db.increment_modification_count("ORD-M") == 1
        finally:
            db.close()

    def test_non_terminal_status_keeps_counter(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            db.store_order(_order("ORD-N"))
            for _ in range(5):
                db.increment_modification_count("ORD-N")
            db.update_order_status("ORD-N", "PENDING")
            assert db.get_modification_count("ORD-N") == 5
        finally:
            db.close()

    def test_explicit_reset_removes_row(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            db.increment_modification_count("ORD-O")
            assert db.reset_modification_count("ORD-O") is True
            assert db.get_modification_count("ORD-O") == 0
            assert db.reset_modification_count("ORD-O") is False
        finally:
            db.close()


# --------------------------------------------------------------------- #
# 7. Legacy global counter (back-compat shim)
# --------------------------------------------------------------------- #


class TestLegacyGlobalCounter:
    def test_legacy_api_still_functions(self) -> None:
        rules_engine.reset_modification_counter()
        assert rules_engine.get_modification_count() == 0
        assert rules_engine.increment_modification_counter() == 1
        rules_engine.reset_modification_counter()
