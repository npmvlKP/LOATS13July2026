"""R-19/H-02: scheduled support jobs gate on the kill switch.

Audit finding H-02 (05Oct2026): ``Scheduler._check_kill_switch`` was defined
and unit-tested but had NO production call site -- APScheduler support jobs
(market-status refresh, session-activation report, data cleanup, backtest
sanity) kept running while the halt was engaged. Live enforcement existed
only in the orchestrator cycle loop and the OpenAlgo order-placement gates,
so no order path was exposed -- but a halt was not a support-job halt.

The fix calls ``_check_kill_switch`` as the FIRST statement of each public
job entry method (before the wrapper's ``try`` block, which would otherwise
swallow ``KillSwitchError``), exactly where APScheduler enters: a job fired
while the halt is engaged refuses its body, logs the halt, and lets
APScheduler log-and-continue scheduling. ``run_once`` and the boot sweep in
``main.py`` dispatch through the same public methods, so the single gate
covers every entry path. At boot the in-memory halt flag is always
disengaged (``src/loats/alerts.py``), so the boot sweep can never observe
an engaged halt in production.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from loats.openalgo import KillSwitchError
from loats.scheduler import TradingScheduler

HALT_LOG_LINE = "Kill switch active trading operations blocked"


def _scheduler() -> TradingScheduler:
    """A fresh TradingScheduler without touching the module singleton."""
    return TradingScheduler()


def _gate_stub(active: bool) -> Any:
    """Patch the halt-flag probe the gate reads (module-attribute lookup)."""
    return patch("loats.scheduler.alerts.is_kill_switch_active", return_value=active)


# ---------------------------------------------------------------------------
# market_status_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_market_status_body_refused_when_halt_engaged() -> None:
    """Halt engaged: the market-status body never runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(True), patch.object(s, "_market_status_check_task", body):
        with pytest.raises(KillSwitchError):
            await s.check_market_status()
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_market_status_body_runs_when_halt_disengaged() -> None:
    """Halt disengaged: behavior is unchanged -- the body runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(False), patch.object(s, "_market_status_check_task", body):
        await s.check_market_status()
    body.assert_awaited_once()


# ---------------------------------------------------------------------------
# market_activation_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_market_activation_body_refused_when_halt_engaged() -> None:
    """Halt engaged: the session-activation report body never runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(True), patch("loats.scheduler.market_status_service") as service:
        service.run_activation_check = body
        with pytest.raises(KillSwitchError):
            await s.run_market_activation()
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_market_activation_body_runs_when_halt_disengaged() -> None:
    """Halt disengaged: the session-activation report body runs."""
    s = _scheduler()
    with _gate_stub(False), patch("loats.scheduler.market_status_service") as service:
        service.run_activation_check = AsyncMock()
        await s.run_market_activation()
    service.run_activation_check.assert_awaited_once()


# ---------------------------------------------------------------------------
# data_cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_cleanup_body_refused_when_halt_engaged() -> None:
    """Halt engaged: the data-cleanup body (DB writes, vacuum) never runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(True), patch.object(s, "_data_cleanup_task", body):
        with pytest.raises(KillSwitchError):
            await s.run_data_cleanup()
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_data_cleanup_body_runs_when_halt_disengaged() -> None:
    """Halt disengaged: the data-cleanup body runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(False), patch.object(s, "_data_cleanup_task", body):
        await s.run_data_cleanup()
    body.assert_awaited_once()


# ---------------------------------------------------------------------------
# backtest_sanity_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backtest_sanity_body_refused_when_halt_engaged() -> None:
    """Halt engaged: the backtest-sanity body (fetches, alerts) never runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(True), patch.object(s, "_backtest_sanity_task", body):
        with pytest.raises(KillSwitchError):
            await s.run_backtest_sanity_check()
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_backtest_sanity_body_runs_when_halt_disengaged() -> None:
    """Halt disengaged: the backtest-sanity body runs."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(False), patch.object(s, "_backtest_sanity_task", body):
        await s.run_backtest_sanity_check()
    body.assert_awaited_once()


# ---------------------------------------------------------------------------
# run_once dispatch and gate-message pin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_refuses_body_when_halt_engaged() -> None:
    """run_once dispatches through the gated public method: body refused."""
    s = _scheduler()
    body = AsyncMock()
    with _gate_stub(True), patch.object(s, "_data_cleanup_task", body):
        # run_once's dispatcher catches the gate error by design (APScheduler
        # parity); the assertion is that the BODY never executed.
        await s.run_once("data_cleanup")
    body.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_logs_the_pinned_halt_line() -> None:
    """The gate keeps the exact evidence line the coverage test pins."""
    s = _scheduler()
    with _gate_stub(True), patch("loats.scheduler.logger") as mock_logger:
        with pytest.raises(KillSwitchError):
            await s.check_market_status()
    mock_logger.error.assert_called_once_with(HALT_LOG_LINE)
