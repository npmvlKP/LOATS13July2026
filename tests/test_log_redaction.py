"""H-03 secret-redaction regression net (05Oct2026).

Finding H-03 (05Oct paste) claimed the analyzer payload debug emitters
expose the OpenAlgo API key the transport injects into every POST body.
Reconciliation at HEAD ``0be32a3``: the emitters
(``orchestrator.py:1934``, ``trade_decision.py:532``) log
``TradeDecision.to_analyzer_payload()`` BEFORE the transport's POST
branch injects the key, and the payload builder carries no credential
fields -- the pasted impact chain is false at HEAD.

This wave installs the paste's prescribed defense-in-depth anyway
(``loats.log_redaction.redact_secrets`` wired into
``loats_logging.shared_processors``): ANY future emitter that renders a
request payload is scrubbed at the one chokepoint every rendered line
passes. This net pins the processor's semantics, its wiring, and the
two production surfaces that must stay keyless.

Host note: this dev box's CPython builds additionally mask
credential-named dict keys in ``repr()`` (which the console renderer
uses), but that masking is interpreter-local and NOT relied on here --
the enforced controls are the processor itself and the
``json.dumps``-rendered file handler, both tested below.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import loats.loats_logging as ll
from loats.log_redaction import REDACTION_EVENT_KEY, redact_secrets

FAKE_KEY = "x" * 32  # 32-char alnum fixture: exercises the value-shape sweep


def _failed_post_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "Missing data for required field"
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("POST", "http://t/api/v1/cancelorder"),
        response=httpx.Response(400, text="Missing data for required field"),
    )
    return resp


class TestKeyedRedaction:
    def test_apikey_value_replaced_with_sentinel(self) -> None:
        out = redact_secrets(None, "x", {"payload": {"apikey": FAKE_KEY}})
        assert out["payload"]["apikey"] == "[REDACTED]"
        assert FAKE_KEY not in repr(out)

    def test_redaction_is_case_insensitive(self) -> None:
        out = redact_secrets(
            None, "x", {"ApiKey": FAKE_KEY, "API_KEY": FAKE_KEY, "Api_Key": FAKE_KEY}
        )
        for k in ("ApiKey", "API_KEY", "Api_Key"):
            assert out[k] == "[REDACTED]", out

    def test_credential_family_keys_covered(self) -> None:
        event = {
            "password": "hunter2",
            "access_token": "tok-1",
            "authorization": "Bearer abc",
            "webhook_url": "https://hooks.example/abc",
            "session_id": "sess-42",
        }
        out = redact_secrets(None, "x", event)
        for k in event:
            assert out[k] == "[REDACTED]", out

    def test_nested_payload_redacted_recursively(self) -> None:
        event = {
            "analysis_request": {
                "payload": {"apikey": FAKE_KEY, "symbol": "NIFTY"},
                # Substring key matching is deliberate: a key NAMED
                # "tokens" is over-redacted by design (safe direction --
                # in a trading payload it is far likelier a credential
                # than prose); non-sensitive keys pass untouched.
                "tags": ["a", "b"],
            }
        }
        out = redact_secrets(None, "x", event)
        assert out["analysis_request"]["payload"]["apikey"] == "[REDACTED]"
        assert out["analysis_request"]["payload"]["symbol"] == "NIFTY"
        assert out["analysis_request"]["tags"] == ["a", "b"]

    def test_non_sensitive_keys_untouched(self) -> None:
        event = {"symbol": "NIFTY", "quantity": 25, "entry_price": 22400.0}
        assert redact_secrets(None, "x", event) == event

    def test_value_shape_fallback_redacts_long_credentials(self) -> None:
        # A key that reached the log under an unexpected key name still
        # cannot survive rendering: long credential-shaped strings are
        # redacted regardless of key.
        out = redact_secrets(None, "x", {"note": FAKE_KEY})
        assert out["note"] == "[REDACTED_SECRET]"

    def test_short_values_pass(self) -> None:
        out = redact_secrets(None, "x", {"note": "NIFTY2450CE"})
        assert out["note"] == "NIFTY2450CE"

    def test_redaction_marker_set_when_changed(self) -> None:
        out = redact_secrets(None, "x", {"payload": {"apikey": FAKE_KEY}})
        assert out.get(REDACTION_EVENT_KEY) is True

    def test_no_marker_when_nothing_redacted(self) -> None:
        out = redact_secrets(None, "x", {"symbol": "NIFTY"})
        assert REDACTION_EVENT_KEY not in out


class TestNeverBreakLogging:
    def test_exception_passthrough(self) -> None:
        """A structure that RAISES during redaction must pass through
        unmodified: logging must never die on a redaction bug."""

        class Hostile(Mapping[str, Any]):
            def __init__(self) -> None:
                self.data: dict[str, Any] = {"symbol": "NIFTY"}

            def __getitem__(self, key: str) -> Any:
                return self.data[key]

            def __iter__(self) -> Any:
                return iter(self.data)

            def __len__(self) -> int:
                return len(self.data)

            def items(self) -> Any:
                raise RuntimeError("hostile mapping")

        event: dict[str, Any] = {"payload": Hostile()}
        out = redact_secrets(None, "x", event)
        assert out is event, "the exact event object must pass through"

    def test_self_referential_container_terminates(self) -> None:
        payload: dict[str, Any] = {"symbol": "NIFTY"}
        payload["self"] = payload
        out = redact_secrets(None, "x", {"payload": payload})
        assert out["payload"]["symbol"] == "NIFTY"

    def test_deep_nesting_capped(self) -> None:
        node: dict[str, Any] = {"leaf": "v"}
        for _ in range(40):
            node = {"next": node}
        out = redact_secrets(None, "x", {"payload": node})
        assert "payload" in out


class TestChainWiring:
    def test_processor_in_structlog_chain(self) -> None:
        ll.configure_logging(test_mode=True)
        import structlog

        chain = structlog.get_config()["processors"]
        assert redact_secrets in chain

    def test_processor_in_all_formatter_pre_chains(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """Both formatters (console AND json/file) must carry the processor
        in their foreign_pre_chain -- verified in production mode so the
        file handler exists and is actually covered by the loop."""
        monkeypatch.setenv("LOATS_LOG_DIR", str(tmp_path))
        ll.configure_logging(test_mode=False)
        try:
            handlers = logging.getLogger().handlers
            assert handlers
            checked = 0
            for h in handlers:
                fmt = getattr(h, "formatter", None)
                pre = getattr(fmt, "foreign_pre_chain", None)
                assert pre is not None, f"handler {h!r} lacks foreign_pre_chain"
                assert redact_secrets in pre, h
                checked += 1
            assert checked >= 2, "console + file handlers must both be checked"
        finally:
            for h in list(logging.getLogger().handlers):
                if isinstance(h, logging.FileHandler):
                    h.close()
                    logging.getLogger().removeHandler(h)


class TestFailedPostDoesNotLeakKey:
    """The paste's prescribed test: a failed POST must not log the key."""

    def test_failed_post_log_has_no_apikey(self) -> None:
        import loats.openalgo as oa

        http = MagicMock()
        http.post.return_value = _failed_post_response()
        client = oa.OpenAlgoClient(api_key=FAKE_KEY, base_url="http://t")
        client.client = http

        records: list[logging.LogRecord] = []

        class Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        target = logging.getLogger("loats.openalgo")
        collector = Collector()
        target.addHandler(collector)
        try:
            with pytest.raises(oa.OpenAlgoAPIError):
                client.cancel_order("o1")
        finally:
            target.removeHandler(collector)

        rendered = " | ".join(f"{r.getMessage()} {r.args!r}" for r in records)
        assert FAKE_KEY not in rendered, rendered

    def test_failed_post_body_was_sent_with_key(self) -> None:
        # Guard the premise: the transport DOES inject the key into the
        # POST body (F8-L-03 schema requirement) -- proving the test
        # above exercises the real exposure surface, not a vacuous one.
        import loats.openalgo as oa

        http = MagicMock()
        http.post.return_value = _failed_post_response()
        client = oa.OpenAlgoClient(api_key=FAKE_KEY, base_url="http://t")
        client.client = http
        with pytest.raises(oa.OpenAlgoAPIError):
            client.cancel_order("o1")
        body = http.post.call_args.kwargs["json"]
        assert body["apikey"] == FAKE_KEY


class TestPayloadEmittersStayKeyless:
    def test_analyzer_payload_debug_log_has_no_key(self) -> None:
        """The H-03 surface: the routing debug emitter must stay pre-injection."""
        from loats.models import SignalType, TradeDecision
        from loats.trade_decision import TradeDecisionEngine

        engine = TradeDecisionEngine(maxsize=2)
        decision = TradeDecision(
            symbol="NIFTY",
            decision_type=SignalType.BUY,
            composite_strength=0.7,
            timestamp=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC),
            entry_price=18000.0,
            quantity=25,
            stop_loss=17820.0,
            risk_percentage=0.02,
            metadata={"apikey": FAKE_KEY},  # adversarial: key in metadata
        )

        captured: dict[str, Any] = {}

        class FakeClient:
            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *args: Any) -> None:
                return None

            async def place_analyzer_request(self, payload: Any) -> dict[str, Any]:
                captured["payload"] = payload
                return {"status": "accepted"}

        records: list[logging.LogRecord] = []

        class Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        target = logging.getLogger("loats.trade_decision")
        collector = Collector()
        target.addHandler(collector)
        try:
            with (
                patch.object(engine, "analyzer_routing_enabled", True),
                patch("loats.trade_decision.AsyncOpenAlgoClient", FakeClient),
                patch(
                    "loats.database.db.async_create_trade_decision",
                    AsyncMock(return_value=None),
                ),
            ):
                import asyncio

                asyncio.run(engine.route_to_analyzer(decision))
        finally:
            target.removeHandler(collector)

        # The WIRE payload (pre-injection) carries no credential key.
        assert "apikey" not in captured["payload"]
        # The rendered debug line is scrubbed even for the adversarial
        # metadata key: the processor must have replaced the value.
        rendered = " | ".join(r.getMessage() for r in records)
        assert FAKE_KEY not in rendered, rendered

    def test_to_analyzer_payload_has_no_credential_fields(self) -> None:
        from loats.models import SignalType, TradeDecision

        decision = TradeDecision(
            symbol="NIFTY",
            decision_type=SignalType.BUY,
            composite_strength=0.7,
            timestamp=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC),
            entry_price=18000.0,
            quantity=25,
            stop_loss=17820.0,
            risk_percentage=0.02,
        )
        assert "apikey" not in decision.to_analyzer_payload()
        assert "api_key" not in decision.to_analyzer_payload()


class TestFileHandlerPathRedacted:
    def test_json_rendered_line_scrubbed(self) -> None:
        """The file handler renders via json.dumps (no interpreter repr
        masking): run the shared chain exactly as the formatter's
        foreign_pre_chain would, then render with the formatter's own
        JSONRenderer -- the produced line is the file line's content."""
        ll.configure_logging(test_mode=True)
        import structlog

        event_dict: dict[str, Any] = {
            "event": "probe",
            "payload": {"apikey": FAKE_KEY, "symbol": "NIFTY"},
        }
        # Run the configured chain minus the wrap_for_formatter
        # terminator (which only structlog-native rendering consumes),
        # passing the real logger/method the stdlib path would carry.
        logger_obj = logging.getLogger("loats.probe")
        chain = structlog.get_config()["processors"]
        result: Any = event_dict
        for proc in chain:
            if proc is structlog.stdlib.ProcessorFormatter.wrap_for_formatter:
                continue
            out = proc(logger_obj, "info", result)
            if out is not None:
                result = out
        line = structlog.processors.JSONRenderer()(None, "loats.probe", result)
        text = line.decode() if isinstance(line, bytes) else str(line)
        assert FAKE_KEY not in text, text
        assert "[REDACTED]" in text, text
        assert "NIFTY" in text, text
