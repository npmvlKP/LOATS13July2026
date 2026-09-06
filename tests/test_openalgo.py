"""Hermetic tests for loats.openalgo (sync + async clients).

All HTTP interactions are mocked at the httpx transport boundary; no test
performs network I/O. Covers request plumbing, error mapping, idempotency
keys, kill-switch enforcement, rate limiting, circuit-breaker wrapping and
the async response cache.
"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import loats.openalgo as oa
from loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoAPIError,
    OpenAlgoClient,
    OpenAlgoError,
    _async_check_kill_switch,
    _check_kill_switch,
    _get_idempotency_key,
    _order_payload_digest,
)
from loats.utils.cache import cache_manager
from loats.utils.circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
    CircuitBreakerOpenError,
)
from loats.utils.rate_limiter import RateLimitExceededError


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Isolate global circuit breaker and idempotency-key state per test."""
    OPENALGO_CIRCUIT_BREAKER.reset()
    with oa._idempotency_lock:
        oa._idempotency_keys.clear()
    yield
    OPENALGO_CIRCUIT_BREAKER.reset()
    with oa._idempotency_lock:
        oa._idempotency_keys.clear()


def _mock_response(payload: dict[str, Any], status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok"
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _failing_response(status: int = 500, text: str = "server error") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("POST", "http://test/api/v1/x"),
        response=httpx.Response(status, text=text),
    )
    return resp


def _sync_http(response: MagicMock) -> MagicMock:
    http = MagicMock()
    http.post.return_value = response
    http.request.return_value = response
    return http


def _async_http(response: MagicMock) -> AsyncMock:
    http = AsyncMock()
    http.post.return_value = response
    http.request.return_value = response
    return http


def _alerts_mock(active: bool) -> MagicMock:
    return MagicMock(is_kill_switch_active=MagicMock(return_value=active))


class TestIdempotencyKeys:
    def test_same_identity_reuses_key(self) -> None:
        key1 = _get_idempotency_key("place:abc")
        key2 = _get_idempotency_key("place:abc")
        assert key1 == key2
        assert len(key1) == 36  # UUIDv4

    def test_different_identity_gets_new_key(self) -> None:
        assert _get_idempotency_key("a") != _get_idempotency_key("b")

    def test_expired_entry_regenerates_key(self) -> None:
        with oa._idempotency_lock:
            oa._idempotency_keys["x"] = ("old-key", -1.0)  # already expired
        new_key = _get_idempotency_key("x")
        assert new_key != "old-key"  # expired entry must not be reused
        with oa._idempotency_lock:
            stored = oa._idempotency_keys["x"]
        assert stored[0] == new_key

    def test_ttl_entries_evicted_when_over_limit(self) -> None:
        with oa._idempotency_lock:
            oa._idempotency_keys.clear()
            # Fill beyond limit with mostly-expired entries
            for i in range(1024):
                oa._idempotency_keys[f"id{i}"] = (f"key{i}", -1.0)
            oa._idempotency_keys["fresh"] = ("fk", 1e18)
        _get_idempotency_key("overflow-id")  # triggers expired-entry eviction
        with oa._idempotency_lock:
            assert "id0" not in oa._idempotency_keys  # expired removed
            assert "fresh" in oa._idempotency_keys  # live retained

    def test_digest_is_canonical(self) -> None:
        a = {"symbol": "X", "qty": 1}
        b = {"qty": 1, "symbol": "X"}
        assert _order_payload_digest(a) == _order_payload_digest(b)
        assert _order_payload_digest(a) != _order_payload_digest({"qty": 2})


class TestExceptionsAndKillSwitch:
    def test_kill_switch_error_defaults(self) -> None:
        err = KillSwitchError()
        assert err.message == "Kill switch active, order placement blocked"

    def test_api_error_attributes(self) -> None:
        err = OpenAlgoAPIError(503, "unavailable", {"r": "x"})
        assert err.status_code == 503
        assert err.message == "unavailable"
        assert err.details == {"r": "x"}
        assert "503" in str(err)

    def test_sync_kill_switch_inactive_passes(self) -> None:
        with patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)):
            _check_kill_switch()  # must not raise

    def test_sync_kill_switch_active_blocks(self) -> None:
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(True)),
            patch("loats.database.db._log_audit") as mock_audit,
        ):
            with pytest.raises(KillSwitchError):
                _check_kill_switch()
            mock_audit.assert_called_once()

    def test_sync_kill_switch_audit_failure_still_blocks(self) -> None:
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(True)),
            patch(
                "loats.database.db._log_audit",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            with pytest.raises(KillSwitchError):
                _check_kill_switch()

    @pytest.mark.asyncio
    async def test_async_kill_switch_active_blocks(self) -> None:
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(True)),
            patch("loats.database.db._log_audit") as mock_audit,
        ):
            with pytest.raises(KillSwitchError):
                await _async_check_kill_switch()
            mock_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_kill_switch_inactive_passes(self) -> None:
        with patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)):
            await _async_check_kill_switch()


class TestSyncClientRequest:
    def test_context_manager_lifecycle(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://test")
        with patch("loats.openalgo.httpx.Client") as mock_cls:
            client.__enter__()
            mock_cls.assert_called_once()
            injected = client.client
            client.__exit__(None, None, None)
            injected.close.assert_called_once()
            assert client.client is None  # released for GC

    def test_ensure_client_lazy(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://test")
        with patch("loats.openalgo.httpx.Client") as mock_cls:
            client._ensure_client()
            client._ensure_client()
            assert mock_cls.call_count == 1

    def test_request_post_success_with_idempotency(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://test")
        http = _sync_http(_mock_response({"status": "success"}))
        client.client = http
        result = client._request(
            "POST", "place_order", json={"a": 1}, idempotency_key="idem-1"
        )
        assert result == {"status": "success"}
        sent_headers = http.post.call_args.kwargs["headers"]
        assert sent_headers["Idempotency-Key"] == "idem-1"

    def test_request_get_uses_request_method(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://test")
        http = _sync_http(_mock_response({"ok": True}))
        client.client = http
        assert client._request("GET", "things") == {"ok": True}
        http.request.assert_called_once()

    def test_request_http_status_error(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://test")
        client.client = _sync_http(_failing_response(500, "boom"))
        with pytest.raises(OpenAlgoAPIError) as exc:
            client._request("POST", "x")
        assert exc.value.status_code == 500

    def test_request_json_decode_error(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("bad json")
        client.client = _sync_http(resp)
        with pytest.raises(OpenAlgoError, match="JSON decode"):
            client._request("POST", "x")

    def test_request_timeout(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        http = MagicMock()
        http.post.side_effect = httpx.TimeoutException("t/o")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Timeout"):
            client._request("POST", "x")

    def test_request_connect_error(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        http = MagicMock()
        http.post.side_effect = httpx.ConnectError("refused")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Connection"):
            client._request("POST", "x")

    def test_request_unexpected_error_wrapped(self) -> None:
        client = OpenAlgoClient(api_key="k", base_url="http://t")
        http = MagicMock()
        http.post.side_effect = RuntimeError("unexpected")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Request failed"):
            client._request("POST", "x")


class TestSyncClientConverters:
    def test_convert_to_quote(self) -> None:
        c = OpenAlgoClient(api_key="k", base_url="http://t")
        q = c._convert_to_quote("NIFTY", {"last_price": 100.5, "volume": 10})
        assert q.symbol == "NIFTY"
        assert q.last_price == 100.5
        assert q.volume == 10

    def test_convert_to_historical_data(self) -> None:
        c = OpenAlgoClient(api_key="k", base_url="http://t")
        h = c._convert_to_historical_data(
            "X",
            "1min",
            {
                "timestamp": "2024-01-01T10:00:00",
                "open": 8.0,
                "high": 10.0,
                "low": 7.5,
                "close": 9.0,
                "volume": 100,
            },
        )
        assert h.close == 9.0
        assert h.interval == "1min"

    def test_convert_to_position(self) -> None:
        c = OpenAlgoClient(api_key="k", base_url="http://t")
        p = c._convert_to_position({"symbol": "X", "quantity": 5, "pnl": -1.5})
        assert p.symbol == "X"
        assert p.quantity == 5
        assert p.pnl == -1.5

    def test_convert_to_order(self) -> None:
        c = OpenAlgoClient(api_key="k", base_url="http://t")
        o = c._convert_to_order(
            {
                "order_id": "1",
                "symbol": "X",
                "quantity": 2,
                "timestamp": "2024-01-01T10:00:00",
                "price": 12.0,
            }
        )
        assert o.order_id == "1"
        assert o.price == 12.0


class TestSyncClientEndpoints:
    def _client(self) -> OpenAlgoClient:
        c = OpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _sync_http(_mock_response({"status": "success", "data": {}}))
        return c

    def test_get_quotes(self) -> None:
        assert self._client().get_quotes(["A"]) == {"status": "success", "data": {}}

    def test_get_history(self) -> None:
        assert self._client().get_history("A", "1min")["status"] == "success"

    def test_get_option_chain(self) -> None:
        assert self._client().get_option_chain("A")["status"] == "success"

    def test_get_position_book(self) -> None:
        assert self._client().get_position_book()["status"] == "success"

    def test_get_funds(self) -> None:
        assert self._client().get_funds()["status"] == "success"

    def test_get_order_status(self) -> None:
        assert self._client().get_order_status("o1")["status"] == "success"

    def test_get_all_orders(self) -> None:
        assert self._client().get_all_orders()["status"] == "success"

    def test_get_trade_book(self) -> None:
        assert self._client().get_trade_book()["status"] == "success"

    def test_place_order_sends_idempotency_header(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_sync_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: True),
            ),
        ):
            c.place_order("X", 10, "MARKET")
        headers = c.client.post.call_args.kwargs["headers"]
        assert "Idempotency-Key" in headers

    def test_place_smart_order_success(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_sync_smart_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: True),
            ),
        ):
            result = c.place_smart_order("X", 5, "LIMIT", price=1.0)
        assert result["status"] == "success"
        payload = c.client.post.call_args.kwargs["json"]
        assert payload["price"] == 1.0

    def test_modify_order_success(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            # Rule-7 gate (F8-H-02) must not persist counters into the real
            # data/loats.db during unit tests; boundary coverage lives in
            # tests/test_rule7_modification_limit.py against a temp DB.
            patch("loats.rules.rules_engine"),
        ):
            c.modify_order("o1", quantity=20)
        payload = c.client.post.call_args.kwargs["json"]
        assert payload["order_id"] == "o1"
        assert payload["quantity"] == 20

    def test_cancel_order_success(self) -> None:
        c = self._client()
        with patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)):
            c.cancel_order("o1")
        payload = c.client.post.call_args.kwargs["json"]
        assert payload == {"order_id": "o1", "apikey": "k"}

    def test_place_order_kill_switch_blocks(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(True)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(KillSwitchError):
                c.place_order("X", 1, "MARKET")
        c.client.post.assert_not_called()

    def test_place_order_rate_limited(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_sync_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: False),
            ),
        ):
            with pytest.raises(RateLimitExceededError):
                c.place_order("X", 1, "MARKET")
        c.client.post.assert_not_called()

    def test_place_smart_order_rate_limited(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_sync_smart_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: False),
            ),
        ):
            with pytest.raises(RateLimitExceededError):
                c.place_smart_order("X", 1, "MARKET")

    def test_order_methods_fail_fast_when_circuit_open(self) -> None:
        c = self._client()
        breaker = MagicMock()
        breaker.call.side_effect = CircuitBreakerOpenError("openalgo", 5.0)
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_sync_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: True),
            ),
            patch("loats.openalgo.OPENALGO_CIRCUIT_BREAKER", breaker),
        ):
            with pytest.raises(CircuitBreakerOpenError):
                c.place_order("X", 1, "MARKET")


class TestAsyncClientRequest:
    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        with patch("loats.openalgo.httpx.AsyncClient", return_value=AsyncMock()):
            entered = await client.__aenter__()
            assert entered is client
            injected = client.client
            await client.__aexit__(None, None, None)
            injected.aclose.assert_awaited_once()
            assert client.client is None  # released for GC

    @pytest.mark.asyncio
    async def test_ensure_client_lazy(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        with patch("loats.openalgo.httpx.AsyncClient") as mock_cls:
            await client._ensure_client()
            await client._ensure_client()
            assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_request_post_success_with_idempotency(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        http = _async_http(_mock_response({"status": "success"}))
        client.client = http
        result = await client._request(
            "POST", "place_order", json={"a": 1}, idempotency_key="idem-2"
        )
        assert result == {"status": "success"}
        assert http.post.call_args.kwargs["headers"]["Idempotency-Key"] == "idem-2"

    @pytest.mark.asyncio
    async def test_request_get_uses_request(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        http = _async_http(_mock_response({"ok": 1}))
        client.client = http
        await client._request("GET", "things")
        http.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_http_status_error(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        client.client = _async_http(_failing_response(429, "rate"))
        with pytest.raises(OpenAlgoAPIError) as exc:
            await client._request("POST", "x")
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_request_json_decode_error(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("nope")
        client.client = _async_http(resp)
        with pytest.raises(OpenAlgoError, match="JSON decode"):
            await client._request("POST", "x")

    @pytest.mark.asyncio
    async def test_request_timeout(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        http = AsyncMock()
        http.post.side_effect = httpx.TimeoutException("t/o")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Timeout"):
            await client._request("POST", "x")

    @pytest.mark.asyncio
    async def test_request_connect_error(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        http = AsyncMock()
        http.post.side_effect = httpx.ConnectError("refused")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Connection"):
            await client._request("POST", "x")

    @pytest.mark.asyncio
    async def test_request_unexpected_error(self) -> None:
        client = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        http = AsyncMock()
        http.post.side_effect = RuntimeError("x")
        client.client = http
        with pytest.raises(OpenAlgoError, match="Request failed"):
            await client._request("POST", "x")


class TestAsyncClientCaching:
    async def _cached_client(self) -> AsyncOpenAlgoClient:
        await cache_manager.initialize()
        c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _async_http(_mock_response({"status": "success", "src": "api"}))
        return c

    @pytest.mark.asyncio
    async def test_quotes_cache_roundtrip(self) -> None:
        c = await self._cached_client()
        r1 = await c.get_quotes(["ZQ1"])
        r2 = await c.get_quotes(["ZQ1"])
        assert r1["src"] == "api"
        assert r2["src"] == "api"
        assert c.client.post.await_count == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_quotes_cache_corrupt_falls_back_to_api(self) -> None:
        c = await self._cached_client()
        import hashlib

        digest = hashlib.sha256(b"ZQ2").hexdigest()
        await cache_manager.set(f"quotes:{digest}", "{not-json", ttl=60)
        result = await c.get_quotes(["ZQ2"])
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_history_cache_roundtrip(self) -> None:
        c = await self._cached_client()
        await c.get_history("ZH1", "1min")
        await c.get_history("ZH1", "1min")
        assert c.client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_option_chain_cache_roundtrip(self) -> None:
        c = await self._cached_client()
        await c.get_option_chain("ZO1")
        await c.get_option_chain("ZO1")
        assert c.client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_position_book_cache_roundtrip(self) -> None:
        c = await self._cached_client()
        await c.get_position_book()
        await c.get_position_book()
        assert c.client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_funds_cache_roundtrip(self) -> None:
        c = await self._cached_client()
        await c.get_funds()
        await c.get_funds()
        assert c.client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_write_failure_is_non_fatal(self) -> None:
        c = await self._cached_client()
        with patch.object(
            cache_manager, "set", new=AsyncMock(side_effect=RuntimeError("cache"))
        ):
            result = await c.get_funds()
        assert result["status"] == "success"


class TestAsyncClientOrders:
    def _client(self) -> AsyncOpenAlgoClient:
        c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _async_http(_mock_response({"status": "success"}))
        return c

    @pytest.mark.asyncio
    async def test_place_order_success_sends_idempotency(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=True)),
            ),
        ):
            await c.place_order("X", 10, "MARKET")
        headers = c.client.post.call_args.kwargs["headers"]
        assert "Idempotency-Key" in headers

    @pytest.mark.asyncio
    async def test_place_order_kill_switch_blocks(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(True)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(KillSwitchError):
                await c.place_order("X", 1, "MARKET")
        c.client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_order_rate_limited(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=False)),
            ),
        ):
            with pytest.raises(RateLimitExceededError):
                await c.place_order("X", 1, "MARKET")

    @pytest.mark.asyncio
    async def test_place_smart_order_success_and_metadata(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_smart_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=True)),
            ),
        ):
            await c.place_smart_order("X", 3, "LIMIT", price=2.0, metadata={"m": 1})
        payload = c.client.post.call_args.kwargs["json"]
        assert payload["metadata"] == {"m": 1}
        assert payload["price"] == 2.0

    @pytest.mark.asyncio
    async def test_place_smart_order_rate_limited(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_smart_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=False)),
            ),
        ):
            with pytest.raises(RateLimitExceededError):
                await c.place_smart_order("X", 1, "MARKET")

    @pytest.mark.asyncio
    async def test_modify_order_success(self) -> None:
        c = self._client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            # Rule-7 gate (F8-H-02) mocked out here; boundary coverage lives
            # in tests/test_rule7_modification_limit.py against a temp DB.
            patch("loats.rules.rules_engine"),
        ):
            await c.modify_order("o1", price=3.0, quantity=7)
        payload = c.client.post.call_args.kwargs["json"]
        assert payload["price"] == 3.0
        assert payload["quantity"] == 7

    @pytest.mark.asyncio
    async def test_cancel_order_success(self) -> None:
        c = self._client()
        with patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)):
            await c.cancel_order("o1")
        payload = c.client.post.call_args.kwargs["json"]
        assert payload == {"order_id": "o1", "apikey": "k"}

    @pytest.mark.asyncio
    async def test_order_fail_fast_when_circuit_open(self) -> None:
        c = self._client()
        breaker = MagicMock()
        breaker.call_async = AsyncMock(
            side_effect=CircuitBreakerOpenError("openalgo", 5.0)
        )
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts_mock(False)),
            patch(
                "loats.openalgo.get_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=True)),
            ),
            patch("loats.openalgo.OPENALGO_CIRCUIT_BREAKER", breaker),
        ):
            with pytest.raises(CircuitBreakerOpenError):
                await c.place_order("X", 1, "MARKET")


class TestAsyncClientUncachedEndpoints:
    @pytest.mark.asyncio
    async def test_get_order_status(self) -> None:
        c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _async_http(_mock_response({"status": "open"}))
        assert await c.get_order_status("o1") == {"status": "open"}

    @pytest.mark.asyncio
    async def test_get_all_orders(self) -> None:
        c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _async_http(_mock_response({"data": []}))
        assert await c.get_all_orders() == {"data": []}

    @pytest.mark.asyncio
    async def test_get_trade_book(self) -> None:
        c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
        c.client = _async_http(_mock_response({"trades": []}))
        assert await c.get_trade_book() == {"trades": []}


class TestThreadSafety:
    def test_concurrent_idempotency_key_generation(self) -> None:
        keys: dict[str, str] = {}
        lock = threading.Lock()

        def worker(identity: str) -> None:
            key = _get_idempotency_key(identity)
            with lock:
                keys[identity] = key

        threads = [
            threading.Thread(target=worker, args=(f"ident-{i % 5}",)) for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(keys.values())) <= 5
        with oa._idempotency_lock:
            assert len(oa._idempotency_keys) == 5
