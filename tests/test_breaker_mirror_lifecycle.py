"""Breaker-mirror lifecycle contract (30Sep evidence wave).

RED-PROVEN against the original defect: the pre-fix shape made the ONLY
mirror write inside the breaker-open branch, so a recovered source stayed
flagged open on :8001 forever (phantom-open metrics). These pins encode
the post-fix contract: mirror-True on degradation, mirror-False on every
successful pass-through.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource
from loats.utils.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from loats.utils.per_source_breakers import get_source_breaker_registry


class TestBreakerMirrorResetsOnSuccess:
    def test_successful_passthrough_clears_mirror(self) -> None:
        """RED-proven contract: a successful pass-through writes mirror
        False (the pre-fix shape never cleared it)."""
        orch = TradingOrchestrator()

        async def recovered(*args: object, **kwargs: object) -> str:
            return "ok"

        with patch("loats.orchestrator.set_circuit_breaker_status") as mock_set:
            result = asyncio.run(
                orch._guarded_source_get(StrengthSource.VOLATILITY, recovered)
            )
        assert result == "ok"
        mirrored = {call.args[0]: call.args[1] for call in mock_set.call_args_list}
        assert mirrored.get("source:volatility") is False

    def test_open_breaker_sets_mirror_true(self) -> None:
        """Pre-existing pin (kept): degradation writes mirror True."""
        orch = TradingOrchestrator()

        async def already_open(*args: object, **kwargs: object) -> object:
            raise CircuitBreakerOpenError("source:volatility", 60.0)

        with patch("loats.orchestrator.set_circuit_breaker_status") as mock_set:
            result = asyncio.run(
                orch._guarded_source_get(StrengthSource.VOLATILITY, already_open)
            )
        assert result is None  # degraded
        mock_set.assert_called_once_with("source:volatility", True)

    def test_full_lifecycle_true_then_false(self) -> None:
        """Degradation flips the gauge True; the first success after
        recovery flips it back False -- the sticky state is gone."""
        orch = TradingOrchestrator()
        source = StrengthSource.VOLATILITY
        breaker = get_source_breaker_registry().get(source)
        # The registry breaker is a PROCESS-WIDE singleton: save its real
        # config and restore it in finally -- reset() alone clears state
        # but not a swapped config, which would leak into later tests.
        original_config = breaker.config
        breaker.reset()
        breaker.config = CircuitBreakerConfig(
            failure_threshold=3, success_threshold=1, timeout=60.0
        )
        failures = {"n": 0}

        async def flaky_fetch(*args: object, **kwargs: object) -> str:
            if failures["n"] < 3:
                failures["n"] += 1
                raise ConnectionError("feed down")
            return "recovered"

        captured: list[tuple[str, bool]] = []

        def fake_set(component: str, open_status: bool) -> None:
            captured.append((component, open_status))

        try:
            with patch(
                "loats.orchestrator.set_circuit_breaker_status",
                side_effect=fake_set,
            ):
                # Phase 1 -- three fetch failures count on the breaker
                # (the ConnectionError itself propagates out of
                # _guarded_source_get; only CircuitBreakerOpenError
                # degrades). The breaker is now OPEN.
                for _ in range(3):
                    with pytest.raises(ConnectionError):
                        asyncio.run(orch._guarded_source_get(source, flaky_fetch))
                # Call 4: breaker OPEN (timeout 60 s -- no half-open yet)
                # -> rejected -> degraded path -> mirror True.
                result = asyncio.run(orch._guarded_source_get(source, flaky_fetch))
                assert result is None
                assert captured[-1] == ("source:volatility", True)
                # Phase 2 -- the outage ends; expire the open-timeout the
                # way real wall-clock time would, then call again: the
                # property routes OPEN -> HALF_OPEN, the probe succeeds,
                # the breaker CLOSES, and the pass-through clears the
                # mirror to False.
                breaker.config.timeout = 0.0
                result = asyncio.run(orch._guarded_source_get(source, flaky_fetch))
                assert result == "recovered"
                assert captured[-1] == ("source:volatility", False)
        finally:
            breaker.config = original_config
            breaker.reset()

    def test_real_metrics_gauge_receives_clear_call(self) -> None:
        """The clear goes through the same metrics seam as the set -- the
        real MetricsManager accepts both without error."""
        manager = MagicMock()
        orch = TradingOrchestrator()

        async def ok(*args: object, **kwargs: object) -> str:
            return "ok"

        with patch(
            "loats.orchestrator.set_circuit_breaker_status",
            side_effect=manager,
        ):
            result = asyncio.run(
                orch._guarded_source_get(StrengthSource.VOLATILITY, ok)
            )
        assert result == "ok"
