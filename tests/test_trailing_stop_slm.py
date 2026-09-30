"""S-15 SL-M ratchet fixture legs (30Sep R-01 decision wave).

Per the rider work order
(``docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md``): the
CMP Rule 12 trailing ratchet must be exercised through its SL-M
emission path, including the Rule-7 degradation branch -- a
``Rule7ModificationLimitError`` on the modification path must leave the
ratchet state consistent (stop retained at the pre-move level) and the
position protected (no exception escapes; the ratchet continues with
the next position). Audit trail: a refusal writes the
``ratchet_refused_rule7`` audit row; an executed move writes
``ratchet_update``. Transport faked end-to-end -- no broker, no network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from loats import orchestrator as orch_module
from loats.models import Position, ProductType, TransactionType
from loats.rules import Rule7ModificationLimitError
from loats.trailing_stop import (
    TrailingStopStatus,
    TrailingStopType,
)


def _make_position(symbol: str = "NIFTY") -> Position:
    return Position(
        symbol=symbol,
        quantity=75,
        average_price=22500.0,
        last_price=22500.0,
        pnl=0.0,
        product_type=ProductType.MIS,
        buy_quantity=75,
        sell_quantity=0,
    )


def _trailing_config() -> dict[str, Any]:
    return {
        "trade_id": "t-1",
        "symbol": "NIFTY",
        "entry_price": 22500.0,
        "current_price": 22500.0,
        "stop_type": TrailingStopType.RATCHET,
        "status": TrailingStopStatus.ACTIVE,
        "trigger_price": 22400.0,
        "adjustment_count": 0,
        "current_ratchet_level": 0,
        "transaction_type": TransactionType.BUY,
        "history": [],
    }


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.modify_calls: list[dict[str, Any]] = []
        self.modify_error: Exception | None = None
        self.positions: list[dict[str, Any]] = []
        self.quotes: dict[str, dict[str, Any]] = {}

    async def get_position_book(self) -> dict[str, Any]:
        return {"data": self.positions}

    async def get_quotes(self, symbols: list[str]) -> dict[str, Any]:
        return {"data": {s: self.quotes.get(s, {}) for s in symbols}}

    async def modify_order(self, **kwargs: Any) -> dict[str, Any]:
        self.modify_calls.append(kwargs)
        if self.modify_error is not None:
            raise self.modify_error
        return {"status": "success"}


class _FakeDb:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}
        self.audit_rows: list[dict[str, Any]] = []

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def store_position(self, position: Position) -> None:
        self.positions[position.symbol] = position

    async def async_log_audit(self, **kwargs: Any) -> None:
        self.audit_rows.append(kwargs)


@pytest.fixture
def fake_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> tuple[_FakeAsyncClient, _FakeDb]:
    client = _FakeAsyncClient()
    fake_db = _FakeDb()
    monkeypatch.setattr(orch_module, "async_client", client)
    monkeypatch.setattr(orch_module, "db", fake_db)
    # The driver reads max_modifications via get_settings(); serve a
    # stub whose value can never gate these fixtures.
    monkeypatch.setattr(
        orch_module,
        "get_settings",
        lambda: SimpleNamespace(max_modifications=25),
    )
    return client, fake_db


def _stage_ratcheting_position(
    client: _FakeAsyncClient,
    fake_db: _FakeDb,
    symbol: str = "NIFTY",
) -> Position:
    """Book a position whose trailing config will ratchet at the price."""
    position = _make_position(symbol)
    position.metadata = {  # type: ignore[union-attr]
        "trailing_config": _trailing_config(),
        "order_id": "ord-1",
    }
    fake_db.positions[symbol] = position
    client.positions.append({"symbol": symbol})
    client.quotes[symbol] = {"last_price": 23250.0}
    return position


class TestSLMRatchetEmission:
    async def test_ratchet_advances_to_slm_modification(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        """A price advance must emit an SL-M modify with the new trigger."""
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db)

        await orch_module.update_trailing_stops()

        assert len(client.modify_calls) == 1
        call = client.modify_calls[0]
        assert call["order_id"] == "ord-1"
        assert call["order_type"] == "SL-M"
        assert call["trigger_price"] > 22400.0, call
        stored = fake_db.positions["NIFTY"]
        new_trigger = stored.metadata["trailing_config"]["trigger_price"]
        assert new_trigger == call["trigger_price"]

    async def test_monotonic_ratchet_never_lowers_the_stop(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        """Two advances: the second trigger must be >= the first."""
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db)

        await orch_module.update_trailing_stops()
        first = client.modify_calls[0]["trigger_price"]

        client.quotes["NIFTY"] = {"last_price": 23500.0}
        await orch_module.update_trailing_stops()
        second = client.modify_calls[1]["trigger_price"]
        assert second > first

    async def test_ratchet_update_writes_audit_row(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db)

        await orch_module.update_trailing_stops()

        actions = [row["action"] for row in fake_db.audit_rows]
        assert "ratchet_update" in actions


class TestRule7Degradation:
    async def test_rule7_refusal_keeps_stop_and_position_protected(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        """The 26th-modification error must degrade WITHOUT losing the stop.

        State contract: the stored config keeps a stop at the PRE-move
        level (still ACTIVE, still protecting the position); no
        exception escapes the driver; the refusal is audited as
        ``ratchet_refused_rule7``; the broker was called exactly once.
        """
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db)
        client.modify_error = Rule7ModificationLimitError(
            "per-order modification budget exhausted"
        )

        await orch_module.update_trailing_stops()

        assert len(client.modify_calls) == 1
        actions = [row["action"] for row in fake_db.audit_rows]
        assert "ratchet_refused_rule7" in actions
        assert "ratchet_update" not in actions
        config = fake_db.positions["NIFTY"].metadata["trailing_config"]
        assert config["status"] == TrailingStopStatus.ACTIVE
        assert config["trigger_price"] == 22400.0

    async def test_rule7_refusal_on_first_position_does_not_block_the_second(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        """The ``continue`` degradation keeps the driver alive."""
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db, "NIFTY")
        _stage_ratcheting_position(client, fake_db, "BANKNIFTY")
        client.modify_error = Rule7ModificationLimitError("budget exhausted")

        await orch_module.update_trailing_stops()

        assert len(client.modify_calls) == 2
        actions = [row["action"] for row in fake_db.audit_rows]
        assert actions.count("ratchet_refused_rule7") == 2

    async def test_second_position_after_successful_first(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        """Happy path on position 1 does not consume position 2's move."""
        client, fake_db = fake_stack
        _stage_ratcheting_position(client, fake_db, "NIFTY")
        _stage_ratcheting_position(client, fake_db, "BANKNIFTY")

        await orch_module.update_trailing_stops()

        assert len(client.modify_calls) == 2
        assert all(c["order_type"] == "SL-M" for c in client.modify_calls)


class TestDrivePathContract:
    async def test_no_position_book_returns_silently(
        self, fake_stack: tuple[_FakeAsyncClient, _FakeDb]
    ) -> None:
        client, _ = fake_stack
        client.positions = []
        await orch_module.update_trailing_stops()
        assert client.modify_calls == []
