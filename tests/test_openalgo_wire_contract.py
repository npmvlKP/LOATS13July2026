"""Wire-contract regression tests for the OpenAlgo client.

These pin the LIVE deployment contract verified 08Sep2026 (P5 cycle,
127.0.0.1:5000): every request shape below was confirmed against the
running OpenAlgo instance, where the previous client behavior produced
HTTP 400s (or silently-wrong parses) on every P5 cycle since 05Sep.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pytest

import loats.openalgo as oa
from loats.openalgo import AsyncOpenAlgoClient, OpenAlgoClient
from loats.orchestrator import TradingOrchestrator
from loats.utils.cache import cache_manager


def _capturing_sync_client(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> tuple[OpenAlgoClient, list[tuple[str, str, dict[str, Any]]]]:
    """Sync client whose ``_request`` captures (method, endpoint, json)."""
    client = OpenAlgoClient(api_key="k", base_url="http://t")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, endpoint, kwargs.get("json") or {}))
        return response

    monkeypatch.setattr(client, "_request", fake_request)
    return client, calls


@pytest.fixture(autouse=True)
def _clear_expiry_memo() -> None:
    """Isolate the module-level listed-expiry memo between tests."""
    oa._EXPIRY_CACHE.clear()


class TestQuoteExchangeRouting:
    """Index symbols must be quoted on NSE_INDEX, cash symbols on NSE."""

    def test_index_symbol_routes_to_nse_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, calls = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": {"ltp": 1.0}}
        )
        client.get_quotes(["NIFTY"])
        assert calls[0][1] == "quotes"
        assert calls[0][2]["exchange"] == "NSE_INDEX"
        assert calls[0][2]["symbol"] == "NIFTY"

    def test_stock_symbol_stays_on_nse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, calls = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": {"ltp": 1.0}}
        )
        client.get_quotes(["RELIANCE"])
        assert calls[0][2]["exchange"] == "NSE"

    def test_all_configured_index_symbols_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, calls = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": {"ltp": 1.0}}
        )
        symbols = [
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
            "NIFTYNXT50",
            "INDIAVIX",
        ]
        client.get_quotes(symbols)
        assert len(calls) == len(symbols)
        assert all(call[2]["exchange"] == "NSE_INDEX" for call in calls)


class TestQuoteResponseNormalization:
    """The deployment returns ONE flat quote dict per /quotes response."""

    def test_flat_response_keyed_under_symbol_and_aliased(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, _ = _capturing_sync_client(
            monkeypatch,
            {
                "status": "success",
                "data": {"ltp": 23635.1, "prev_close": 23779.15, "oi": 0},
            },
        )
        result = client.get_quotes(["NIFTY"])
        quote = result["data"]["NIFTY"]
        assert quote["ltp"] == 23635.1
        assert quote["last_price"] == 23635.1  # canonical alias added
        assert quote["close"] == 23779.15  # canonical alias added
        assert quote["prev_close"] == 23779.15  # broker field preserved

    def test_symbol_keyed_response_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, _ = _capturing_sync_client(
            monkeypatch,
            {"status": "success", "data": {"RELIANCE": {"ltp": 1294.9}}},
        )
        result = client.get_quotes(["RELIANCE"])
        assert result["data"]["RELIANCE"]["last_price"] == 1294.9


class TestHistoryPayload:
    """The deployment requires exchange + start_date/end_date."""

    def test_payload_has_required_fields_and_routed_exchange(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, calls = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": []}
        )
        client.get_history("NIFTY", "5min", "2026-09-01", "2026-09-05")
        payload = calls[0][2]
        assert calls[0][1] == "history"
        assert payload["exchange"] == "NSE_INDEX"
        assert payload["interval"] == "5m"  # repo '5min' normalized
        assert payload["start_date"] == "2026-09-01"
        assert payload["end_date"] == "2026-09-05"
        assert "from_date" not in payload and "to_date" not in payload

    def test_default_dates_are_iso_dates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, calls = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": []}
        )
        client.get_history("RELIANCE", "1min")
        payload = calls[0][2]
        assert payload["exchange"] == "NSE"
        assert payload["interval"] == "1m"
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", payload["start_date"])
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", payload["end_date"])

    def test_interval_normalizer_matrix(self) -> None:
        assert oa._normalize_interval("5min") == "5m"
        assert oa._normalize_interval("1min") == "1m"
        assert oa._normalize_interval("15min") == "15m"
        assert oa._normalize_interval("5m") == "5m"
        assert oa._normalize_interval("D") == "D"
        assert oa._normalize_interval("1h") == "1h"


class TestOptionChainPayload:
    """The deployment endpoint is /optionchain with {underlying, expiry_date, exchange}."""

    def test_payload_schema_and_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str, dict[str, Any]]] = []

        # /expiry listing is consulted first; its front listing is used.
        def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            if endpoint == "expiry":
                assert kwargs["json"]["instrumenttype"] == "options"
                assert kwargs["json"]["symbol"] == "NIFTY"
                return {"status": "success", "data": ["01-JAN-49", "08-JAN-49"]}
            calls.append((method, endpoint, kwargs.get("json") or {}))
            return {"status": "success", "data": []}

        client = OpenAlgoClient(api_key="k", base_url="http://t")
        monkeypatch.setattr(client, "_request", fake_request)
        client.get_option_chain("NIFTY")
        assert len(calls) == 1
        assert calls[0][1] == "optionchain"
        payload = calls[0][2]
        assert payload["underlying"] == "NIFTY"
        # Front LISTED expiry, normalized to the compact wire format.
        assert payload["expiry_date"] == "01JAN49"
        assert payload["exchange"] == "NFO"
        assert "symbol" not in payload and "expiry" not in payload

    def test_expiry_listing_unavailable_falls_back_to_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str, dict[str, Any]]] = []
        monkeypatch.setattr(
            oa, "_option_chain_expiry_date", lambda days_ahead=7: "15SEP26"
        )

        def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            if endpoint == "expiry":
                raise oa.OpenAlgoError("endpoint gone")
            calls.append((method, endpoint, kwargs.get("json") or {}))
            return {"status": "success", "data": []}

        client = OpenAlgoClient(api_key="k", base_url="http://t")
        monkeypatch.setattr(client, "_request", fake_request)
        client.get_option_chain("NIFTY")
        assert calls[0][2]["expiry_date"] == "15SEP26"

    def test_hint_is_compact_ddmmmyy(self) -> None:
        assert re.match(r"^\d{2}[A-Z]{3}\d{2}$", oa._option_chain_expiry_date())

    def test_choose_listed_expiry_picks_front_listing_and_compacts(self) -> None:
        picked = oa._choose_listed_expiry(["08-JAN-49", "01-JAN-49", "15-JAN-49"])
        assert picked == "01JAN49"

    def test_choose_listed_expiry_skips_expired_entries(self) -> None:
        picked = oa._choose_listed_expiry(["01-JAN-26", "01-JAN-49"])
        assert picked == "01JAN49"

    def test_choose_listed_expiry_falls_back_without_listing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            oa, "_option_chain_expiry_date", lambda days_ahead=7: "15SEP26"
        )
        assert oa._choose_listed_expiry(None) == "15SEP26"
        assert oa._choose_listed_expiry(["garbage"]) == "15SEP26"

    def test_nested_chain_flattened_to_contract_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        nested = {
            "status": "success",
            "underlying_ltp": 23635.1,
            "chain": [
                {
                    "strike": 23650.0,
                    "ce": {"symbol": "NIFTY08SEP2623650CE", "volume": 5, "iv": 12.0},
                    "pe": {"symbol": "NIFTY08SEP2623650PE", "volume": 9, "iv": 14.0},
                }
            ],
        }
        client, _ = _capturing_sync_client(monkeypatch, nested)
        result = client.get_option_chain("NIFTY")
        rows = result["data"]
        assert len(rows) == 2
        ce = next(r for r in rows if r["option_type"] == "CE")
        pe = next(r for r in rows if r["option_type"] == "PE")
        assert ce["strike"] == 23650.0 and ce["volume"] == 5
        assert pe["strike"] == 23650.0 and pe["volume"] == 9
        # The orchestrator's parse helpers (the producer's actual readers)
        # must extract flow numbers from these flattened rows:
        assert TradingOrchestrator._chain_int(ce, ("volume", "volume_btn")) == 5
        assert TradingOrchestrator._chain_int(pe, ("volume", "volume_btn")) == 9
        assert (
            TradingOrchestrator._chain_float(ce, ("implied_volatility", "iv")) == 12.0
        )
        assert (
            TradingOrchestrator._chain_float(pe, ("implied_volatility", "iv")) == 14.0
        )
        assert TradingOrchestrator._chain_int(ce, ("oi",)) == 0  # missing -> 0

    def test_payload_without_chain_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        flat = {"status": "success", "data": [{"option_type": "CE", "volume": 1}]}
        client, _ = _capturing_sync_client(monkeypatch, flat)
        result = client.get_option_chain("NIFTY")
        assert result["data"][0]["option_type"] == "CE"


class TestAsyncQuoteRouting:
    """Async client follows the same contract (P5 uses the async path)."""

    @pytest.mark.asyncio
    async def test_index_symbol_routes_and_normalizes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        calls: list[dict[str, Any]] = []

        async def fake_request(
            method: str, endpoint: str, **kwargs: Any
        ) -> dict[str, Any]:
            calls.append(kwargs.get("json") or {})
            return {
                "status": "success",
                "data": {"ltp": 23635.1, "prev_close": 23779.15},
            }

        monkeypatch.setattr(client, "_request", fake_request)
        result = await client.get_quotes(["NIFTY"])
        assert calls[0]["exchange"] == "NSE_INDEX"
        quote = result["data"]["NIFTY"]
        assert quote["last_price"] == 23635.1
        assert quote["close"] == 23779.15

    @pytest.mark.asyncio
    async def test_history_and_chain_schemas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        calls: list[tuple[str, dict[str, Any]]] = []

        async def fake_request(
            method: str, endpoint: str, **kwargs: Any
        ) -> dict[str, Any]:
            calls.append((endpoint, kwargs.get("json") or {}))
            if endpoint == "expiry":
                return {"status": "success", "data": ["01-JAN-49", "08-JAN-49"]}
            if endpoint == "optionchain":
                return {
                    "status": "success",
                    "chain": [
                        {"strike": 1.0, "ce": {"volume": 2}, "pe": {"volume": 3}}
                    ],
                }
            return {"status": "success", "data": []}

        monkeypatch.setattr(client, "_request", fake_request)
        await client.get_history("NIFTY", "1min")
        assert calls[0][0] == "history"
        assert calls[0][1]["exchange"] == "NSE_INDEX"
        assert calls[0][1]["interval"] == "1m"

        # optionchain resolution fires /expiry first (uncached here), then
        # the chain call itself.
        await client.get_option_chain("NIFTY")
        assert calls[1][0] == "expiry"
        assert calls[2][0] == "optionchain"
        assert calls[2][1]["underlying"] == "NIFTY"
        assert calls[2][1]["exchange"] == "NFO"
        assert calls[2][1]["expiry_date"] == "01JAN49"


class TestAdversarialRoundFindings:
    """Regressions for the adversarial-review findings (08Sep2026)."""

    def test_missing_ltp_is_not_fabricated_as_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # P0-1: a leg without ltp/prev_close must stay missing, not 0.0 --
        # the VIX gate's explicit `get("last_price") is None` handling
        # depends on it.
        client, _ = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": {"oi": 5, "volume": 0}}
        )
        quote = client.get_quotes(["INDIAVIX"])["data"]["INDIAVIX"]
        assert "last_price" not in quote
        assert "close" not in quote

    def test_response_dict_is_never_mutated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # P0-1: the response object can be cached; aliases must land on a
        # copy so the live payload keeps broker-only vocabulary.
        captured: dict[str, Any] = {"data": {"ltp": 100.0, "prev_close": 99.0}}
        client, _ = _capturing_sync_client(
            monkeypatch, {"status": "success", "data": captured["data"]}
        )
        client.get_quotes(["NIFTY"])
        assert captured["data"] == {"ltp": 100.0, "prev_close": 99.0}

    def test_partial_symbol_failure_is_isolated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # P1-4: one bad symbol must not starve the others' consumers.
        client = OpenAlgoClient(api_key="k", base_url="http://t")

        def flaky_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            symbol = (kwargs.get("json") or {}).get("symbol")
            if symbol == "BAD":
                raise oa.OpenAlgoError("transient")
            return {"status": "success", "data": {"ltp": 50.0, "prev_close": 49.0}}

        monkeypatch.setattr(client, "_request", flaky_request)
        result = client.get_quotes(["GOOD1", "BAD", "GOOD2"])
        assert result["data"]["GOOD1"]["last_price"] == 50.0
        assert result["data"]["GOOD2"]["last_price"] == 50.0
        assert "BAD" not in result["data"]

    def test_total_failure_still_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The circuit breaker must see a total outage.
        client = OpenAlgoClient(api_key="k", base_url="http://t")

        def dead_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            raise oa.OpenAlgoError("broker down")

        monkeypatch.setattr(client, "_request", dead_request)
        with pytest.raises(oa.OpenAlgoError):
            client.get_quotes(["A", "B"])

    def test_minute_suffix_interval_normalized(self) -> None:
        # P1-2: '5minute' appears in the wild and must not 400 on the wire.
        assert oa._normalize_interval("5minute") == "5m"
        assert oa._normalize_interval("1minute") == "1m"

    def test_empty_chain_payload_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # P0-2: never overwrite an existing data payload with [].
        payload = {"status": "success", "chain": [], "data": {"options": [{"x": 1}]}}
        client, _ = _capturing_sync_client(monkeypatch, payload)
        result = client.get_option_chain("NIFTY")
        assert result["data"] == {"options": [{"x": 1}]}


class TestExpiryResolutionMemoization:
    """The /expiry listing is memoized (sync + async share the cache)."""

    def test_sync_resolution_cached_within_ttl(self) -> None:
        calls: list[str] = []

        def request(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload["symbol"])
            return {"status": "success", "data": ["01-JAN-49", "08-JAN-49"]}

        first = oa._resolve_expiry_date("NIFTY", "NFO", request)
        second = oa._resolve_expiry_date("NIFTY", "NFO", request)
        assert first == second == "01JAN49"
        assert len(calls) == 1  # second call served from the memo

    def test_failed_lookup_is_not_cached(self) -> None:
        attempts: list[int] = []

        def flaky_request(payload: dict[str, Any]) -> dict[str, Any]:
            attempts.append(1)
            raise oa.OpenAlgoError("listing unavailable")

        first = oa._resolve_expiry_date("NIFTY", "NFO", flaky_request)
        second = oa._resolve_expiry_date("NIFTY", "NFO", flaky_request)
        # Both fall back to the computed hint and BOTH attempted the wire.
        assert first == second
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_async_shares_the_memo_with_sync(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")

        async def fake_request(
            method: str, endpoint: str, **kwargs: Any
        ) -> dict[str, Any]:
            assert endpoint == "expiry"
            return {"status": "success", "data": ["01-JAN-49", "08-JAN-49"]}

        monkey_patch = pytest.MonkeyPatch()
        try:
            monkey_patch.setattr(client, "_request", fake_request)
            first = await client._resolve_expiry_date_async("NIFTY", "NFO")
            second = await client._resolve_expiry_date_async("NIFTY", "NFO")
            assert first == second == "01JAN49"
            assert oa._EXPIRY_CACHE[("NIFTY", "NFO")][1] == "01JAN49"
        finally:
            monkey_patch.undo()


class TestHistoryTimestampNormalization:
    """History rows carry epoch timestamps; consumers parse ISO strings."""

    def test_epoch_timestamps_converted_to_iso(self) -> None:
        result = oa._normalize_history_rows(
            {
                "status": "success",
                "data": [
                    {"close": 23838.4, "timestamp": 1788752700},
                    {"close": 23850.0, "timestamp": 1788752760},
                ],
            }
        )
        first = result["data"][0]["timestamp"]
        assert isinstance(first, str)
        parsed = datetime.fromisoformat(first)
        assert parsed.year == 2026 and parsed.tzinfo is not None

    def test_iso_rows_pass_through_untouched(self) -> None:
        original = {"timestamp": "2026-09-08T10:00:00+00:00"}
        result = oa._normalize_history_rows({"data": [dict(original)]})
        assert result["data"][0]["timestamp"] == original["timestamp"]

    def test_non_list_and_missing_timestamp_pass_through(self) -> None:
        payload = {"status": "error", "message": "x"}
        assert oa._normalize_history_rows(payload) is payload
        row_only = {"data": [{"close": 1.0}]}
        assert oa._normalize_history_rows(row_only)["data"] == row_only["data"]

    @pytest.mark.asyncio
    async def test_async_history_normalizes_before_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The value stored in the cache must already be ISO-parsable."""
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")

        async def fake_request(
            method: str, endpoint: str, **kwargs: Any
        ) -> dict[str, Any]:
            assert endpoint == "history"
            return {"status": "success", "data": [{"close": 1.0, "timestamp": 0}]}

        monkeypatch.setattr(client, "_request", fake_request)
        await cache_manager.initialize()
        result = await client.get_history("NIFTY", "1min")
        ts = result["data"][0]["timestamp"]
        assert isinstance(ts, str)
        datetime.fromisoformat(ts)
