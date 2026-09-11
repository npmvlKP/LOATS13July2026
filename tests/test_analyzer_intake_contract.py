"""Analyzer intake-contract pinning (ADR-006 Amendment 5).

Amendment 4 deferred the gateway-side decision-telemetry intake as a P5
follow-up. Until that endpoint exists, every routed decision resolves as
an honestly-counted HTTP-404 ``error`` outcome, and the intake path lived
as a hard-coded literal inside ``place_analyzer_request`` — so activating
the future endpoint would have required a code change and, with it, a
restart of the accruing 14-day P5 span.

The contract pinned here (Amendment 5):

1. The intake path is a real settings field: ``analyzer_intake_path``.
2. The default is exactly ``"analyze"`` — zero behaviour change while the
   read-only semantic is live (the gateway 404s it by design).
3. The client resolves the field per call via ``get_settings()`` — no
   constructor-time capture, so an operator can flip the route without
   touching the supervised run.
4. The path flows into ``_request`` as the endpoint (surfaced at
   ``/api/v1/<path>`` by the client's URL builder).
5. ``TradeDecision.to_analyzer_payload`` is untouched: the wire shape the
   future intake must accept stays pinned.
6. The tracked-file ceiling stays single-source (adding this test file
   consumes ratchet headroom; the re-pin is the canonical module's).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from loats.config.settings import Settings, get_settings
from loats.openalgo import AsyncOpenAlgoClient

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_settings(**overrides: Any) -> Settings:
    return Settings(
        environment="test",
        openalgo_api_key=SecretStr("k"),
        telegram_bot_token=SecretStr("t"),
        telegram_chat_id="1",
        **overrides,
    )


@pytest.fixture()
def client() -> AsyncOpenAlgoClient:
    return AsyncOpenAlgoClient(api_key="test-key", base_url="http://gateway.test")


class TestIntakePathSetting:
    """Contract 1+2: real field, default exactly today's behaviour."""

    def test_field_defaults_to_analyze(self) -> None:
        assert _make_settings().analyzer_intake_path == "analyze"

    def test_field_is_operator_settable(self) -> None:
        s = _make_settings(analyzer_intake_path="analyzer/decisions")
        assert s.analyzer_intake_path == "analyzer/decisions"

    def test_settings_singleton_carries_default(self) -> None:
        assert get_settings().analyzer_intake_path == "analyze"


class TestIntakePathFlow:
    """Contract 3+4: per-call resolution into the real request seam."""

    async def test_routes_to_settings_path_not_literal(
        self, client: AsyncOpenAlgoClient
    ) -> None:
        with (
            patch.object(
                AsyncOpenAlgoClient, "_request", new_callable=AsyncMock
            ) as req,
            patch("loats.openalgo.get_settings", return_value=_make_settings()),
        ):
            req.return_value = {"status": "accepted"}
            await client.place_analyzer_request({"decision_id": "d1"})
        req.assert_awaited_once_with("POST", "analyze", json={"decision_id": "d1"})

    async def test_path_change_takes_effect_without_reconstruction(
        self, client: AsyncOpenAlgoClient
    ) -> None:
        """Per-call resolution: flipping the setting moves the endpoint even
        for a client constructed before the flip (no restart needed)."""
        with patch.object(
            AsyncOpenAlgoClient, "_request", new_callable=AsyncMock
        ) as req:
            req.return_value = {"status": "accepted"}
            with patch("loats.openalgo.get_settings", return_value=_make_settings()):
                await client.place_analyzer_request({"decision_id": "d1"})
            req.assert_any_await("POST", "analyze", json={"decision_id": "d1"})
            with patch(
                "loats.openalgo.get_settings",
                return_value=_make_settings(analyzer_intake_path="analyzer/decisions"),
            ):
                await client.place_analyzer_request({"decision_id": "d2"})
            req.assert_any_await(
                "POST", "analyzer/decisions", json={"decision_id": "d2"}
            )
        assert req.await_count == 2


class TestPayloadUnchanged:
    """Contract 5: the wire shape stays pinned for the future intake."""

    def test_to_analyzer_payload_not_touched(self) -> None:
        src = (REPO_ROOT / "src" / "loats" / "models.py").read_text(encoding="utf-8")
        assert '"decision_id": self.decision_id' in src
        assert '"as_of_date"' in src
        assert re.search(r"def to_analyzer_payload\(self\)", src)


class TestRatchetSingleSource:
    """Contract 6: this wave's ceiling re-pin lands in the canonical module."""

    def test_ceiling_pinned_once(self) -> None:
        src = (REPO_ROOT / "scripts" / "ratchet_baseline.py").read_text(
            encoding="utf-8"
        )
        pins = re.findall(r"TRACKED_FILE_CEILING\s*=\s*(\d+)", src)
        assert len(pins) == 1
        assert 405 <= int(pins[0]) <= 510
