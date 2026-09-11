"""Wire-contract regression: the live deployment's REST route names.

Verified 10Sep2026 against the running gateway (127.0.0.1:5000, gateway
commit d36936a6): the deployment serves underscore-free one-word routes
under /api/v1 -- /positionbook, /tradebook, /orderbook, /orderstatus,
/placeorder, /placesmartorder, /modifyorder, /cancelorder. LOATS's
snake_case spellings (position_book, trade_book, all_orders,
order_status, place_order, place_smart_order, modify_order,
cancel_order) return HTTP 404 on every call -- the live supervised P5
run logged 10,332 position_book 404s, which flapped the openalgo
circuit breaker open (52,804 trading-cycle errors) and starved the CMP
decision funnel (zero decisions during 10Sep market hours).

The pre-fix client fails these tests (RED verified before the rename);
the fix renames every endpoint string to the deployment's route. The
/analyze question (the gateway has no decision-intake endpoint) is
deliberately NOT fixed here -- recorded in ADR-006 as an open question
for a later session.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from loats.openalgo import AsyncOpenAlgoClient, OpenAlgoClient

_SRC = Path(__file__).resolve().parents[1] / "src" / "loats" / "openalgo.py"


def _patch_async_request(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    """Patch AsyncOpenAlgoClient._request to record (method, endpoint, json)."""
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(
        self: AsyncOpenAlgoClient, method: str, endpoint: str, **kwargs: Any
    ) -> dict[str, Any]:
        calls.append((method, endpoint, kwargs.get("json") or {}))
        return response

    monkeypatch.setattr(AsyncOpenAlgoClient, "_request", fake_request)
    return calls


def _make_async_client() -> AsyncOpenAlgoClient:
    return AsyncOpenAlgoClient(api_key="k", base_url="http://t")


class TestAsyncUnderscoreFreeRoutes:
    """Every async client endpoint must hit the deployment's real route."""

    def test_position_book_hits_positionbook(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().get_position_book())
        assert calls[0][1] == "positionbook", (
            f"endpoint {calls[0][1]!r} is a guaranteed 404 on the live "
            "deployment; the route is /api/v1/positionbook"
        )

    def test_trade_book_hits_tradebook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().get_trade_book())
        assert calls[0][1] == "tradebook"

    def test_all_orders_hits_orderbook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().get_all_orders())
        assert calls[0][1] == "orderbook"

    def test_order_status_hits_orderstatus(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().get_order_status("ORD1"))
        assert calls[0][1] == "orderstatus"
        assert calls[0][2] == {"order_id": "ORD1"}

    def test_place_order_hits_placeorder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().place_order("NIFTY", 25, "LIMIT", price=100.0))
        assert calls[0][1] == "placeorder"

    def test_place_smart_order_hits_placesmartorder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(
            _make_async_client().place_smart_order("NIFTY", 25, "LIMIT", price=100.0)
        )
        assert calls[0][1] == "placesmartorder"

    def test_modify_order_hits_modifyorder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(
            _make_async_client().modify_order("ORD1", order_type="LIMIT", price=101.0)
        )
        assert calls[0][1] == "modifyorder"

    def test_cancel_order_hits_cancelorder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch_async_request(monkeypatch, {"status": "success", "data": []})
        asyncio.run(_make_async_client().cancel_order("ORD1"))
        assert calls[0][1] == "cancelorder"


class TestPositionBookFieldVocabulary:
    """The deployment's position rows use ``ltp``; callers read ``last_price``.

    Verified 10Sep2026 in the gateway source (broker/<x>/mapping/
    order_data.py transform_positions_data emits symbol/exchange/product/
    quantity/pnl/average_price/ltp). Without the alias, fixing the 404
    would trade a 404 for a KeyError('last_price') in the orchestrator's
    _create_position_model -- the same drift class already fixed for
    funds (available_cash) and quotes (last_price/close).
    """

    def test_ltp_aliased_to_last_price(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_async_request(
            monkeypatch,
            {
                "status": "success",
                "data": [
                    {
                        "symbol": "NIFTY",
                        "quantity": 25,
                        "average_price": 100.5,
                        "ltp": 101.25,
                        "pnl": 18.75,
                        "product": "MIS",
                    }
                ],
            },
        )
        result = asyncio.run(_make_async_client().get_position_book())
        row = result["data"][0]
        assert row["last_price"] == 101.25
        assert row["ltp"] == 101.25  # original field preserved

    def test_explicit_last_price_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_async_request(
            monkeypatch,
            {
                "status": "success",
                "data": [{"symbol": "X", "last_price": 55.0, "ltp": 44.0}],
            },
        )
        result = asyncio.run(_make_async_client().get_position_book())
        assert result["data"][0]["last_price"] == 55.0

    def test_non_list_data_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {"status": "error", "message": "boom"}
        _patch_async_request(monkeypatch, payload)
        result = asyncio.run(_make_async_client().get_position_book())
        assert result is payload


class TestSyncClientSameContract:
    """The sync client shares the route-name contract."""

    def test_sync_position_book_route_and_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        calls: list[str] = []

        def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(endpoint)
            return {
                "status": "success",
                "data": [{"symbol": "X", "quantity": 1, "ltp": 9.5}],
            }

        monkeypatch.setattr(client, "_request", fake_request)
        result = client.get_position_book()
        assert calls[0] == "positionbook"
        assert result["data"][0]["last_price"] == 9.5

    def test_sync_trade_book_route(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        calls: list[str] = []

        def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(endpoint)
            return {"status": "success", "data": []}

        monkeypatch.setattr(client, "_request", fake_request)
        client.get_trade_book()
        assert calls[0] == "tradebook"


class TestNoSnakeCaseRouteStringsRemain:
    """The dead spellings must not survive as endpoint literals."""

    def test_no_snake_case_endpoint_literals(self) -> None:
        src = _SRC.read_text(encoding="utf-8")
        for bad in (
            '"position_book"',
            '"trade_book"',
            '"all_orders"',
            '"order_status"',
            '"place_order"',
            '"place_smart_order"',
            '"modify_order"',
            '"cancel_order"',
        ):
            assert bad not in src, (
                f"{bad} is a guaranteed 404 on the live deployment; the "
                "client must use the deployment's underscore-free route"
            )
