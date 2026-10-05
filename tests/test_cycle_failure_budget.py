"""M-01 net: the trading-cycle loop must not swallow persistent faults forever.

Audit finding M-01 (05Oct2026): ``TradingOrchestrator._run_cycle_loop``
catches every non-``KillSwitchError`` exception, logs it, alerts at most
once per minute, and resumes -- so a persistent producer fault fails
silently at 1 Hz forever. The fix is a consecutive-failure budget:
``CYCLE_FAILURE_BUDGET`` consecutive cycle failures escalate to a kill
switch activation (halt) instead of another silent continue. The budget
exceeds the largest observed self-healing recovery burst (~350
consecutive breaker-open failures in the 05Oct logs) so routine breaker
recoveries never escalate.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import loats.orchestrator as orch_module
from loats import alerts as alerts_module
from loats.latency_budget import CYCLE_FAILURE_BUDGET
from loats.openalgo import KillSwitchError
from loats.orchestrator import TradingOrchestrator

ACTIVATE_PATH = "loats.orchestrator.alerts.activate_kill_switch"


@pytest.fixture()
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Isolate the loop's I/O surfaces and record the sleep cadence.

    Patches ``asyncio.sleep`` (real cadence sleeps) AND the alerts
    singleton's ``send_system_alert`` (the loop's except-branch alert --
    a real Telegram dispatch attempt must never fire from a unit net).
    """
    calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(alerts_module.alerts, "send_system_alert", AsyncMock())
    return calls


class TestBudgetConstant:
    def test_budget_is_pinned(self) -> None:
        # Above the largest observed self-healing burst (~350 consecutive
        # breaker-open failures, 05Oct logs); below values so large the
        # escalation would never fire within a session.
        assert CYCLE_FAILURE_BUDGET == 500

    def test_budget_is_exported(self) -> None:
        import loats.latency_budget as lb

        assert "CYCLE_FAILURE_BUDGET" in lb.__all__


class TestConsecutiveFailureBudget:
    @pytest.mark.asyncio
    async def test_single_failure_resumes_without_escalation(
        self, fast_sleep: list[float]
    ) -> None:
        orch = TradingOrchestrator()
        calls = {"n": 0}

        async def _fail_once() -> None:
            calls["n"] += 1
            if calls["n"] >= 3:
                orch._shutdown_event.set()
            raise RuntimeError("transient producer fault")

        with patch.object(orch, "_execute_trading_cycle", side_effect=_fail_once):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new_callable=AsyncMock) as activate:
                    await orch._run_cycle_loop()

        assert activate.await_count == 0
        assert orch._consecutive_cycle_failures >= 1

    @pytest.mark.asyncio
    async def test_burst_below_budget_then_success_never_escalates(
        self, fast_sleep: list[float]
    ) -> None:
        orch = TradingOrchestrator()
        calls = {"n": 0}
        burst = 30  # << CYCLE_FAILURE_BUDGET: the observed breaker-recovery shape

        async def _burst_then_recover() -> None:
            calls["n"] += 1
            if calls["n"] <= burst:
                raise RuntimeError("circuit breaker open")
            orch._shutdown_event.set()

        with patch.object(
            orch, "_execute_trading_cycle", side_effect=_burst_then_recover
        ):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new_callable=AsyncMock) as activate:
                    await orch._run_cycle_loop()

        assert activate.await_count == 0
        # Recovery reset the streak -- a fresh burst gets a fresh budget.
        assert orch._consecutive_cycle_failures == 0

    @pytest.mark.asyncio
    async def test_budget_exhaustion_escalates_to_kill_switch(
        self, monkeypatch: pytest.MonkeyPatch, fast_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(orch_module, "CYCLE_FAILURE_BUDGET", 3)
        orch = TradingOrchestrator()
        calls = {"n": 0}
        reasons: list[str] = []

        async def _always_fail() -> None:
            calls["n"] += 1
            if calls["n"] >= 5:
                # escape hatch: stop after the escalation at failure 3
                # plus two post-escalation failures (streak 4, 5)
                orch._shutdown_event.set()
            raise RuntimeError("persistent datastore fault")

        async def _true_activate(reason: str = "") -> bool:
            reasons.append(reason)
            return True

        with patch.object(orch, "_execute_trading_cycle", side_effect=_always_fail):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new=_true_activate):
                    await orch._run_cycle_loop()

        assert len(reasons) == 1
        reason = reasons[0]
        assert "3 consecutive" in reason
        assert "persistent datastore fault" in reason
        # The escalation re-arms the budget instead of killing the loop:
        # the loop kept cycling after the escalation (5 cycles ran) and
        # the streak restarted from 0 toward the next budget.
        assert calls["n"] == 5
        assert 0 <= orch._consecutive_cycle_failures < 3

    @pytest.mark.asyncio
    async def test_refused_escalation_keeps_loop_alive_and_re_escalates(
        self, monkeypatch: pytest.MonkeyPatch, fast_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(orch_module, "CYCLE_FAILURE_BUDGET", 3)
        orch = TradingOrchestrator()
        calls = {"n": 0}
        escalations = {"n": 0}

        async def _always_fail() -> None:
            calls["n"] += 1
            if calls["n"] >= 8:
                orch._shutdown_event.set()
            raise RuntimeError("persistent datastore fault")

        async def _refuse(reason: str = "") -> bool:
            escalations["n"] += 1
            return False  # broker unreachable: activation refused

        with patch.object(orch, "_execute_trading_cycle", side_effect=_always_fail):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new=_refuse):
                    await orch._run_cycle_loop()

        # Escalated at failure 3, re-armed, escalated again at failure 6.
        assert escalations["n"] == 2
        assert calls["n"] >= 7

    @pytest.mark.asyncio
    async def test_success_after_failures_resets_streak(
        self, monkeypatch: pytest.MonkeyPatch, fast_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(orch_module, "CYCLE_FAILURE_BUDGET", 3)
        orch = TradingOrchestrator()
        calls = {"n": 0}

        async def _flap_then_healthy() -> None:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("blip")
            orch._shutdown_event.set()

        with patch.object(
            orch, "_execute_trading_cycle", side_effect=_flap_then_healthy
        ):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new_callable=AsyncMock) as activate:
                    await orch._run_cycle_loop()

        assert activate.await_count == 0
        assert orch._consecutive_cycle_failures == 0

    @pytest.mark.asyncio
    async def test_kill_switch_cycles_do_not_count_as_failures(
        self, monkeypatch: pytest.MonkeyPatch, fast_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(orch_module, "CYCLE_FAILURE_BUDGET", 3)
        orch = TradingOrchestrator()
        state = {"tick": 0}

        async def _halt_then_blip_then_recover() -> None:
            # Called only on non-halted cycles: ticks 4 and 5 fail
            # ("blip after release"), tick 6 recovers and stops the loop.
            if state["tick"] <= 5:
                raise RuntimeError("blip after release")
            orch._shutdown_event.set()

        async def _check() -> None:
            state["tick"] += 1
            if state["tick"] <= 3:
                raise KillSwitchError()

        with patch.object(
            orch, "_execute_trading_cycle", side_effect=_halt_then_blip_then_recover
        ):
            with patch.object(orch, "_check_kill_switch", side_effect=_check):
                with patch(ACTIVATE_PATH, new_callable=AsyncMock) as activate:
                    await orch._run_cycle_loop()

        # The 3 halted cycles consumed NONE of the failure budget: the
        # 2-failure blip stayed under the (shrunken) budget of 3 and the
        # recovery reset the streak -- no escalation ever fired.
        assert activate.await_count == 0
        assert orch._consecutive_cycle_failures == 0


class TestEscalationReasonHygiene:
    @pytest.mark.asyncio
    async def test_reason_is_capped_and_non_empty(
        self, monkeypatch: pytest.MonkeyPatch, fast_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(orch_module, "CYCLE_FAILURE_BUDGET", 2)
        orch = TradingOrchestrator()
        calls = {"n": 0}

        async def _fail_big() -> None:
            calls["n"] += 1
            if calls["n"] >= 4:
                orch._shutdown_event.set()
            raise RuntimeError("x" * 5000)

        with patch.object(orch, "_execute_trading_cycle", side_effect=_fail_big):
            with patch.object(orch, "_check_kill_switch", new_callable=AsyncMock):
                with patch(ACTIVATE_PATH, new_callable=AsyncMock) as activate:
                    await orch._run_cycle_loop()

        reason = activate.await_args.kwargs["reason"]
        assert len(reason) <= 300
        assert "2 consecutive" in reason
