"""C-02 order-mode gate + H-01 armed-refusal net (04Oct2026 wave).

CMP gap C-02: ``OPENALGO_MODE`` was a declared deployment knob with zero
enforcement consumers -- any caller holding the API key could reach the
broker's placeorder/placesmartorder routes regardless of mode. This wave
makes ``place_order``/``place_smart_order`` HARD-REFUSE unless
``OPENALGO_MODE=LIVE`` **and** ``OPENALGO_ARMING`` are both set, and
extends the same armed refusal to ``modify_order`` (H-01: the Rule-12
driver's default-off ``enable_trailing_stops`` plus the persisted Rule-7
budget stay the primary per-cycle/per-order controls; the mode gate is
the client-boundary backstop).

RED-proven: this module was executed against the pre-gate tree and
failed on import (no ``OpenAlgoModeBlockedError``/``OpenAlgoModeArmingError``)
plus every refusal assertion before the gate landed.

Settings are resolved live through ``get_settings`` with
``monkeypatch.setenv`` so an operator ``.env`` cannot flip a verdict
(process env overrides ``env_file`` in pydantic-settings). Transport
faked end-to-end -- no broker, no network; the audit row written on a
refusal is patched out so no test touches the real data store.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.config import get_settings
from loats.openalgo import (
    AsyncOpenAlgoClient,
    KillSwitchError,
    OpenAlgoClient,
    OpenAlgoModeArmingError,
    OpenAlgoModeBlockedError,
)


@pytest.fixture(autouse=True)
def _fresh_settings_cache() -> Any:
    """Resolve settings from THIS test's env, never a stale cached value."""
    get_settings.cache_clear()
    yield
    # Teardown clear: the next test's first get_settings() must re-read
    # its own environment, not this test's monkeypatched one.
    get_settings.cache_clear()


def _mock_response(payload: dict[str, Any], status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok"
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _sync_client() -> OpenAlgoClient:
    c = OpenAlgoClient(api_key="k", base_url="http://t")
    http = MagicMock()
    http.post.return_value = _mock_response({"status": "success", "data": {}})
    c.client = http
    return c


def _async_client() -> AsyncOpenAlgoClient:
    c = AsyncOpenAlgoClient(api_key="k", base_url="http://t")
    http = AsyncMock()
    http.post.return_value = _mock_response({"status": "success"})
    c.client = http
    return c


def _alerts(active: bool) -> MagicMock:
    return MagicMock(is_kill_switch_active=MagicMock(return_value=active))


def _live_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENALGO_MODE", "LIVE")
    monkeypatch.setenv("OPENALGO_ARMING", "true")


class TestSyncModeGate:
    def test_place_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                c.place_order("X", 10, "MARKET")
        c.client.post.assert_not_called()

    def test_place_smart_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                c.place_smart_order("X", 10, "MARKET")
        c.client.post.assert_not_called()

    def test_place_order_refused_when_live_without_arming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENALGO_MODE", "LIVE")
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeArmingError):
                c.place_order("X", 10, "MARKET")
        c.client.post.assert_not_called()

    def test_place_order_passes_when_live_and_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live_armed(monkeypatch)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch(
                "loats.openalgo.get_sync_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: True),
            ),
        ):
            result = c.place_order("X", 10, "MARKET")
        assert result["status"] == "success"
        assert c.client.post.call_args.kwargs["json"]["symbol"] == "X"

    def test_place_smart_order_passes_when_live_and_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live_armed(monkeypatch)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch(
                "loats.openalgo.get_sync_smart_order_rate_limiter",
                return_value=MagicMock(acquire=lambda: True),
            ),
        ):
            result = c.place_smart_order("X", 5, "LIMIT", price=1.0)
        assert result["status"] == "success"

    def test_kill_switch_precedes_mode_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The emergency stop stays the highest-priority refusal even in a
        # LIVE+armed configuration.
        _live_armed(monkeypatch)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(True)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(KillSwitchError):
                c.place_order("X", 1, "MARKET")
        c.client.post.assert_not_called()

    def test_mode_refusal_writes_block_audit_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit") as audit,
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                c.place_order("X", 1, "MARKET")
        kwargs = audit.call_args.kwargs
        assert kwargs["action"] == "BLOCK"
        assert kwargs["metadata"]["reason"] == "order_mode_gate"

    def test_modify_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # H-01 armed-refusal: the mutation path backstops the driver's
        # default-off enablement at the client boundary.
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                c.modify_order("o1", trigger_price=100.0, order_type="SL-M")
        c.client.post.assert_not_called()

    def test_modify_order_passes_when_live_and_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live_armed(monkeypatch)
        c = _sync_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.rules.rules_engine"),
        ):
            result = c.modify_order("o1", quantity=20)
        assert result["status"] == "success"


class TestAsyncModeGate:
    @pytest.mark.asyncio
    async def test_place_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                await c.place_order("X", 10, "MARKET")
        c.client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_smart_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                await c.place_smart_order("X", 10, "MARKET")
        c.client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_order_refused_when_live_without_arming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENALGO_MODE", "LIVE")
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeArmingError):
                await c.place_order("X", 10, "MARKET")
        c.client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_order_passes_when_live_and_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live_armed(monkeypatch)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch(
                "loats.openalgo.get_order_rate_limiter",
                return_value=MagicMock(acquire=AsyncMock(return_value=True)),
            ),
        ):
            result = await c.place_order("X", 10, "MARKET")
        assert result["status"] == "success"
        assert c.client.post.call_args.kwargs["json"]["symbol"] == "X"

    @pytest.mark.asyncio
    async def test_modify_order_refused_in_default_analyze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENALGO_ARMING", raising=False)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.database.db._log_audit"),
        ):
            with pytest.raises(OpenAlgoModeBlockedError):
                await c.modify_order("o1", trigger_price=100.0, order_type="SL-M")
        c.client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_modify_order_passes_when_live_and_armed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live_armed(monkeypatch)
        c = _async_client()
        with (
            patch("loats.openalgo._get_alerts", return_value=_alerts(False)),
            patch("loats.rules.rules_engine"),
        ):
            result = await c.modify_order("o1", price=3.0, quantity=7)
        assert result["status"] == "success"
