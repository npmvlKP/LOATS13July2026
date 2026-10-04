import asyncio
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from loats.database import Database
from loats.main import AuditIntegrityGateError, TradingSystem


@pytest.fixture
def trading_system():
    return TradingSystem()


@pytest.mark.asyncio
async def test_trading_system_initialization_success(trading_system):
    """Test successful initialization (lines 34-47)."""
    with (
        patch("loats.main.initialize_cache", new_callable=AsyncMock) as mock_cache_init,
        patch("loats.main.db.async_initialize", new_callable=AsyncMock) as mock_db_init,
        patch(
            "loats.main.db.async_verify_audit_log_integrity", return_value=True
        ) as mock_db_verify,
        patch(
            "loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
        # F9-C-02: the metrics server start PROPAGATES failures now, so
        # unit tests must not bind the real port (a live system on this
        # host owns 8001) -- patch the manager like any collaborator.
        patch("loats.main.metrics.start_server"),
    ):
        await trading_system.initialize()
        mock_cache_init.assert_called_once()
        mock_db_init.assert_called_once()
        mock_db_verify.assert_called_once()
        mock_alerts_init.assert_called_once()
        mock_scheduler_init.assert_called_once()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_initialization_refuses_failed_audit_log(
    trading_system,
):
    """C-01: a failed integrity verify REFUSES boot (was: warn + continue)."""
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", new_callable=AsyncMock),
        patch(
            "loats.main.db.async_verify_audit_log_integrity",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("loats.main.db.async_log_audit", new_callable=AsyncMock) as mock_bg_audit,
        patch("loats.main.alerts.initialize", new_callable=AsyncMock),
        patch("loats.main.scheduler.initialize", new_callable=AsyncMock),
        patch("loats.main.metrics.start_server"),
    ):
        with pytest.raises(AuditIntegrityGateError, match="C-01"):
            await trading_system.initialize()
        # The refusal fires BEFORE the alert/orchestrator legs: no
        # break-glass audit row was written on the broken trail.
        mock_bg_audit.assert_not_called()


@pytest.mark.asyncio
async def test_trading_system_initialization_break_glass_continues(
    trading_system,
):
    """C-01: break-glass continues boot with an error alert + audited row."""
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", new_callable=AsyncMock),
        patch(
            "loats.main.db.async_verify_audit_log_integrity",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("loats.main.db.async_log_audit", new_callable=AsyncMock) as mock_bg_audit,
        patch(
            "loats.main.alerts.send_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
        patch("loats.main.metrics.start_server"),
        patch("loats.main.start_orchestrator", new_callable=AsyncMock),
        patch(
            "loats.main._load_settings",
            return_value=SimpleNamespace(audit_integrity_break_glass=True),
        ),
    ):
        await trading_system.initialize()
        mock_send_alert.assert_awaited_once()
        assert mock_send_alert.call_args.args[0].startswith(
            "AUDIT INTEGRITY BREAK-GLASS"
        )
        assert mock_send_alert.call_args.kwargs.get("alert_type") == "error"
        mock_bg_audit.assert_awaited_once()
        assert (
            mock_bg_audit.call_args.kwargs.get("action")
            == "AUDIT_INTEGRITY_BREAK_GLASS"
        )
        # The override is a CONTINUE: every later boot leg still ran.
        mock_alerts_init.assert_awaited_once()
        mock_scheduler_init.assert_awaited_once()


@pytest.mark.asyncio
async def test_trading_system_initialization_failed_audit_log_test_env_skips_gate(
    trading_system,
):
    """C-01: under ENVIRONMENT=test a failed verify logs and CONTINUES.

    Keeps the test suites hermetic: they exercise every boot path without
    the production refusal firing.
    """
    with (
        patch.dict(os.environ, {"ENVIRONMENT": "test"}),
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", new_callable=AsyncMock),
        patch(
            "loats.main.db.async_verify_audit_log_integrity",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "loats.main.alerts.initialize", new_callable=AsyncMock
        ) as mock_alerts_init,
        patch(
            "loats.main.scheduler.initialize", new_callable=AsyncMock
        ) as mock_scheduler_init,
        patch("loats.main.metrics.start_server"),
    ):
        await trading_system.initialize()
        mock_alerts_init.assert_awaited_once()
        mock_scheduler_init.assert_awaited_once()


@pytest.mark.asyncio
async def test_trading_system_initialization_exception(trading_system):
    """Test initialization exception handling (lines 45-47)."""
    with (
        patch("loats.main.initialize_cache", new_callable=AsyncMock),
        patch("loats.main.db.async_initialize", side_effect=Exception("DB error")),
    ):
        with pytest.raises(Exception, match="DB error"):
            await trading_system.initialize()


@pytest.mark.asyncio
async def test_trading_system_start_already_running(trading_system):
    """Test start when already running (lines 51-53)."""
    trading_system.running = True
    await trading_system.start()
    # Should return early without starting again


@pytest.mark.asyncio
async def test_trading_system_start_success(trading_system):
    """Test successful start (lines 54-66)."""
    with (
        patch("loats.main.alerts.start", new_callable=AsyncMock) as mock_alerts_start,
        patch(
            "loats.main.scheduler.start", new_callable=AsyncMock
        ) as mock_scheduler_start,
        patch(
            "loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "loats.main.TradingSystem._wait_for_shutdown", new_callable=AsyncMock
        ) as mock_wait,
    ):
        await trading_system.start()
        assert trading_system.running is True
        mock_alerts_start.assert_called_once()
        mock_scheduler_start.assert_called_once()
        mock_send_alert.assert_called_once_with(
            "LOATS13July2026 trading system started successfully", "success"
        )
        mock_wait.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_start_exception(trading_system):
    """Test start exception handling (lines 64-66)."""
    with (
        patch("loats.main.alerts.start", side_effect=Exception("Start error")),
    ):
        with pytest.raises(Exception, match="Start error"):
            await trading_system.start()
        assert trading_system.running is False


@pytest.mark.asyncio
async def test_trading_system_shutdown_not_running(trading_system):
    """Test shutdown when not running (lines 113-115)."""
    trading_system.running = False
    await trading_system.shutdown()
    # Should return early without shutdown


@pytest.mark.asyncio
async def test_trading_system_shutdown_success(trading_system):
    """Test successful shutdown (lines 116-130)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.alerts.send_system_alert", new_callable=AsyncMock
        ) as mock_send_alert,
        patch(
            "loats.main.scheduler.shutdown", new_callable=AsyncMock
        ) as mock_scheduler_shutdown,
        patch(
            "loats.main.alerts.shutdown", new_callable=AsyncMock
        ) as mock_alerts_shutdown,
        patch("loats.main.close_cache") as mock_close_cache,
        patch("loats.main.db.async_close_all", new_callable=AsyncMock) as mock_db_close,
    ):
        await trading_system.shutdown()
        assert trading_system.running is False
        mock_send_alert.assert_called_once_with(
            "LOATS13July2026 trading system shutting down", "warning"
        )
        mock_scheduler_shutdown.assert_called_once()
        mock_alerts_shutdown.assert_called_once()
        mock_close_cache.assert_called_once()
        mock_db_close.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_shutdown_exception(trading_system):
    """Test shutdown exception handling (lines 128-130)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.alerts.send_system_alert",
            side_effect=Exception("Shutdown error"),
        ),
    ):
        with pytest.raises(Exception, match="Shutdown error"):
            await trading_system.shutdown()


@pytest.mark.asyncio
async def test_trading_system_run_once_success(trading_system):
    """Test run_once successful execution (F8-H-03 support jobs only)."""
    with patch.object(
        trading_system, "_run_scheduler_support_jobs", new_callable=AsyncMock
    ) as mock_support:
        await trading_system.run_once()
        mock_support.assert_called_once()


@pytest.mark.asyncio
async def test_trading_system_run_once_exception(trading_system):
    """Test run_once exception handling (F8-H-03 support jobs only)."""
    with patch.object(
        trading_system,
        "_run_scheduler_support_jobs",
        side_effect=Exception("Support job error"),
    ):
        with pytest.raises(Exception, match="Support job error"):
            await trading_system.run_once()


@pytest.mark.asyncio
async def test_make_signal_handler_windows(trading_system):
    """Test _make_signal_handler for Windows platform (lines 85-104)."""
    with patch("sys.platform", "win32"):
        loop = asyncio.get_running_loop()
        handler = trading_system._make_signal_handler(loop)

        # Mock the async task creation to avoid actual shutdown
        with (
            patch("loats.main.alerts.send_system_alert", new_callable=AsyncMock),
            patch("loats.main.scheduler.shutdown", new_callable=AsyncMock),
            patch("loats.main.alerts.shutdown", new_callable=AsyncMock),
            patch("loats.main.close_cache"),
            patch("loats.main.db.async_close_all", new_callable=AsyncMock),
        ):
            # Call the signal handler
            handler(signal.SIGINT, None)

            # Give time for the async task to execute
            await asyncio.sleep(0.1)

            # Verify shutdown was triggered
            assert not trading_system.running


@pytest.mark.asyncio
async def test_handle_shutdown_signal(trading_system):
    """Test _handle_shutdown_signal method (lines 106-109)."""
    trading_system.running = True
    with (
        patch(
            "loats.main.TradingSystem.shutdown", new_callable=AsyncMock
        ) as mock_shutdown,
    ):
        await trading_system._handle_shutdown_signal(signal.SIGTERM)
        mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_shutdown_windows(trading_system):
    """Test _wait_for_shutdown for Windows platform (lines 68-83)."""
    with patch("sys.platform", "win32"):
        # Mock signal handlers
        with patch("signal.signal"):
            # Start the wait_for_shutdown method
            wait_task = asyncio.create_task(trading_system._wait_for_shutdown())

            # Simulate shutdown after a short delay
            async def trigger_shutdown():
                await asyncio.sleep(0.1)
                trading_system.shutdown_event.set()

            shutdown_task = asyncio.create_task(trigger_shutdown())

            # Wait for both tasks to complete
            await asyncio.wait([wait_task, shutdown_task], timeout=1.0)

            # Verify the wait completed
            assert wait_task.done()


@pytest.mark.asyncio
async def test_wait_for_shutdown_posix(trading_system):
    """Test _wait_for_shutdown for POSIX platform (lines 76-81)."""
    with patch("sys.platform", "linux"):
        # Mock add_signal_handler
        with patch("asyncio.AbstractEventLoop.add_signal_handler"):
            # Start the wait_for_shutdown method
            wait_task = asyncio.create_task(trading_system._wait_for_shutdown())

            # Simulate shutdown after a short delay
            async def trigger_shutdown():
                await asyncio.sleep(0.1)
                trading_system.shutdown_event.set()

            shutdown_task = asyncio.create_task(trigger_shutdown())

            # Wait for both tasks to complete
            await asyncio.wait([wait_task, shutdown_task], timeout=1.0)

            # Verify the wait completed
            assert wait_task.done()


# ---------------------------------------------------------------------------
# C-01 end-to-end: corrupt one JSONL entry's hash, boot through the REAL
# verifier, and the system must REFUSE (the paste acceptance test: "corrupt
# one JSONL hash, boot, assert process exit and zero new audit rows").
# Uses the conftest hermetic Database fixture -- a real Database instance
# over a temp-dir audit trail, with the boot gate left unmocked.
# ---------------------------------------------------------------------------


class TestC01AuditIntegrityBootGateEndToEnd:
    @pytest.mark.asyncio
    async def test_corrupt_jsonl_hash_refuses_boot(self, db: Database) -> None:
        # Seed ONE real chained entry via the actual writer, then corrupt
        # its stored self-hash (the paste's tamper class).
        db.log_audit(
            action="E2E_SEED",
            entity_type="TEST_ENTITY",
            entity_id="e2e-seed",
            user="tester",
            metadata={"e2e": "c01"},
        )
        lines = Path(db.audit_log_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, "seed exactly one chained entry"
        first = json.loads(lines[0])
        first["sha256_hash"] = "0" * 64
        lines[0] = json.dumps(first)
        Path(db.audit_log_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

        # The REAL two-layer verifier reports the corruption.
        assert db.verify_audit_log_integrity() is False

        with (
            patch.dict(os.environ, {"ENVIRONMENT": "production"}),
            patch("loats.main.db", db),
            patch("loats.main.db.async_log_audit", new_callable=AsyncMock) as mock_bg,
            patch("loats.main.db.async_verify_audit_log_integrity") as mock_verify,
            patch("loats.main.initialize_cache", new_callable=AsyncMock),
            patch("loats.main.db.async_initialize", new_callable=AsyncMock),
            patch("loats.main.alerts.initialize", new_callable=AsyncMock),
            patch("loats.main.scheduler.initialize", new_callable=AsyncMock),
            patch("loats.main.metrics.start_server"),
            patch(
                "loats.main.start_orchestrator", new_callable=AsyncMock
            ) as mock_start,
        ):
            # Construct INSIDE the patched context: TradingSystem binds
            # the module-level db singleton at __init__ time.
            system = TradingSystem()
            mock_verify.side_effect = db.verify_audit_log_integrity
            with pytest.raises(AuditIntegrityGateError, match="C-01"):
                await system.initialize()
            mock_bg.assert_not_called()
            # The refusal fires BEFORE the orchestrator leg starts.
            mock_start.assert_not_called()

        tail = Path(db.audit_log_path).read_text(encoding="utf-8").splitlines()
        assert len(tail) == 1, "boot refusal must not append audit rows"
