"""Signal-outcome wiring contract (30Sep evidence wave).

Pins the orchestrator-side integration: emission hooks open outcome rows
(directional only), the cycle-loop resolver is throttled and best-effort,
and the shutdown path flushes once more.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from loats.orchestrator import TradingOrchestrator


class TestSignalOutcomeWiring:
    def test_directional_signal_opens_outcome_row(self) -> None:
        """Emission hook: a BUY signal triggers an outcome-open write on
        the module db (detached task)."""
        from loats.models import Signal, SignalType

        orch = TradingOrchestrator()
        signal = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={},
            confidence=0.8,
            metadata={"scan_type": "ta", "source": "ta"},
        )
        with (
            patch("loats.orchestrator.db") as mock_db,
            patch("loats.orchestrator.settings", new=None),
            patch("loats.orchestrator.get_settings") as mock_get_settings,
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_get_settings.return_value = MagicMock(
                signal_outcome_horizon_minutes=60
            )
            # MagicMock (not AsyncMock): create_task is patched, so the
            # awaitable is never awaited -- a MagicMock return keeps the
            # never-awaited-coroutine warning class out of the run.
            mock_db.async_record_signal_outcome_open = MagicMock(return_value=True)
            orch._track_signal_outcome_open(signal)
        mock_create_task.assert_called_once()
        args, kwargs = mock_db.async_record_signal_outcome_open.call_args
        assert args[0] == signal.signal_id
        assert args[1] == 60
        assert kwargs.get("metadata") == {
            "scan_type": "ta",
            "source": "ta",
        }

    def test_non_directional_signal_skips_outcome_row(self) -> None:
        from loats.models import Signal, SignalType

        orch = TradingOrchestrator()
        signal = Signal(
            symbol="NIFTY",
            signal_type=SignalType.HOLD,
            strength=0.4,
            timestamp=datetime.now(UTC),
            indicators={},
            metadata={"scan_type": "ta"},
        )
        with (
            patch("loats.orchestrator.db") as mock_db,
            patch("asyncio.create_task") as mock_create_task,
        ):
            orch._track_signal_outcome_open(signal)
        mock_create_task.assert_not_called()
        mock_db.async_record_signal_outcome_open.assert_not_called()

    def test_throttle_blocks_second_immediate_pass(self) -> None:
        orch = TradingOrchestrator()
        with (
            patch("loats.orchestrator.db") as mock_db,
            patch("loats.orchestrator.time.monotonic", return_value=1000.0),
        ):
            mock_db.async_resolve_signal_outcomes = AsyncMock(return_value=[])
            asyncio.run(orch._maybe_resolve_signal_outcomes())
            assert mock_db.async_resolve_signal_outcomes.await_count == 1
            # Second pass within the interval: throttled away.
            asyncio.run(orch._maybe_resolve_signal_outcomes())
            assert mock_db.async_resolve_signal_outcomes.await_count == 1

    def test_throttle_allows_pass_after_interval(self) -> None:
        orch = TradingOrchestrator()
        clock = {"t": 1000.0}

        def fake_monotonic() -> float:
            return clock["t"]

        async def drive() -> None:
            await orch._maybe_resolve_signal_outcomes()  # runs
            clock["t"] = 1500.0
            await orch._maybe_resolve_signal_outcomes()  # throttled
            clock["t"] = 2900.0
            await orch._maybe_resolve_signal_outcomes()  # runs

        with (
            patch("loats.orchestrator.db") as mock_db,
            patch("loats.orchestrator.time.monotonic", side_effect=fake_monotonic),
        ):
            mock_db.async_resolve_signal_outcomes = AsyncMock(return_value=[])
            asyncio.run(drive())
        assert mock_db.async_resolve_signal_outcomes.await_count == 2

    def test_store_failure_never_raises(self) -> None:
        orch = TradingOrchestrator()
        with (
            patch("loats.orchestrator.db") as mock_db,
            patch("loats.orchestrator.time.monotonic", return_value=1000.0),
        ):
            mock_db.async_resolve_signal_outcomes = AsyncMock(
                side_effect=RuntimeError("store down")
            )
            # Must not raise: instrumentation never fails the cycle.
            asyncio.run(orch._maybe_resolve_signal_outcomes())

    def test_shutdown_flushes_outcomes_once_more(self) -> None:
        orch = TradingOrchestrator()
        orch.running = True

        async def cycle_task() -> None:
            return None

        async def drive() -> None:
            orch._cycle_task = asyncio.create_task(cycle_task())
            await orch.shutdown()

        with patch("loats.orchestrator.db") as mock_db:
            mock_db.async_resolve_signal_outcomes = AsyncMock(
                return_value=[{"signal_id": "s1", "outcome_state": "positive"}]
            )
            asyncio.run(drive())
        mock_db.async_resolve_signal_outcomes.assert_awaited_once()

    def test_shutdown_flush_failure_is_swallowed(self) -> None:
        orch = TradingOrchestrator()
        orch.running = True

        async def cycle_task() -> None:
            return None

        async def drive() -> None:
            orch._cycle_task = asyncio.create_task(cycle_task())
            await orch.shutdown()

        with patch("loats.orchestrator.db") as mock_db:
            mock_db.async_resolve_signal_outcomes = AsyncMock(
                side_effect=RuntimeError("store down at shutdown")
            )
            # Must not raise: the shutdown path completes.
            asyncio.run(drive())
