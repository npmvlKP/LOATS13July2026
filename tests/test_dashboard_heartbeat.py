"""Dashboard Option A "full heartbeat" tests (28Oct2026 control-room wave).

Pins the three operator-facing contracts:
1. One ``dashboard_heartbeat`` row is inserted every 5 minutes by the
   scheduler job (cadence + dispatch + persistence).
2. Rows are USER-DELETABLE via the Telegram admin commands
   /delete_heartbeat and /clear_heartbeats (unauthorized callers refused).
3. Every beat is delivered over the EXISTING Telegram channel via
   ``AlertSystem.send_heartbeat`` -- a dedicated no-cooldown path, because
   a cooldown-suppressed beat is indistinguishable from a dead system.
"""

from __future__ import annotations

import collections.abc
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.alerts import AlertSystem
from loats.database import Database
from loats.scheduler import TradingScheduler


@pytest.fixture
def db() -> collections.abc.Generator[Database, None, None]:
    """Module-local Database fixture (shadows conftest's).

    Teardown uses ``close_all()`` -- not ``close()`` -- because this
    module exercises the ``asyncio.to_thread`` wrappers, whose worker
    threads hold thread-local SQLite connections that ``close()``
    (current thread only) cannot release; on Windows the lingering
    handle then breaks the temp-dir cleanup with WinError 32. This is
    the FIX-WINDOWS-SHUTDOWN/M-02 remedy, applied at the fixture that
    creates the leak.
    """
    with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        database = Database(
            db_path=Path(temp_dir) / "test_dashboard.db",
            audit_log_path=Path(temp_dir) / "test_audit.jsonl",
        )
        try:
            yield database
        finally:
            database.close_all()


@pytest.fixture
def scheduler() -> TradingScheduler:
    """TradingScheduler with the APScheduler handle mocked (per test_scheduler)."""
    with patch("loats.scheduler.AsyncIOScheduler") as mock_aps:
        instance = TradingScheduler()
        instance.scheduler = mock_aps
        return instance


@pytest.fixture
def alert_system(db: Database) -> AlertSystem:
    """AlertSystem with an explicit injected temp Database (NEW-M5 DI)."""
    return AlertSystem(database=db)


def _make_update(user_id: str | None = None) -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    if user_id is None:
        update.effective_user = None
    else:
        update.effective_user = MagicMock(id=user_id)
    return update


def _make_context(args: list[str] | None = None) -> MagicMock:
    context = MagicMock()
    context.args = args or []
    return context


def _seed_heartbeat(
    database: Database,
    *,
    market_open: bool = True,
    kill_switch_active: bool = False,
    breakers_open: int = 0,
    telegram_delivered: bool = True,
) -> int:
    return database.record_dashboard_heartbeat(
        market_open=market_open,
        kill_switch_active=kill_switch_active,
        breakers_open=breakers_open,
        telegram_delivered=telegram_delivered,
        detail="{}",
        message="DASHBOARD HEARTBEAT",
    )


class TestDashboardHeartbeatStore:
    """The dashboard_heartbeat table: insert, read, count, delete, clear."""

    async def test_heartbeat_table_created_on_init(self, db: Database) -> None:
        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name='dashboard_heartbeat'"
            )
            assert cursor.fetchone() is not None
        finally:
            db._release_connection(conn)

    async def test_record_and_read_round_trip(self, db: Database) -> None:
        row_id = _seed_heartbeat(db, market_open=True, breakers_open=1)
        assert row_id > 0
        rows = db.get_dashboard_heartbeats()
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == row_id
        assert row["market_open"] is True
        assert row["kill_switch_active"] is False
        assert row["breakers_open"] == 1
        assert row["telegram_delivered"] is True
        assert row["message"] == "DASHBOARD HEARTBEAT"
        # tz-aware UTC timestamp, consistent with every store timestamp.
        assert "T" in row["timestamp"]
        assert "+" in row["timestamp"] or row["timestamp"].endswith("Z")

    async def test_read_newest_first_with_limit(self, db: Database) -> None:
        first = _seed_heartbeat(db)
        second = _seed_heartbeat(db)
        third = _seed_heartbeat(db)
        rows = db.get_dashboard_heartbeats(limit=2)
        assert [r["id"] for r in rows] == [third, second]
        assert first < second < third

    async def test_delete_single_row_true_then_false(self, db: Database) -> None:
        row_id = _seed_heartbeat(db)
        assert db.delete_dashboard_heartbeat(row_id) is True
        assert db.delete_dashboard_heartbeat(row_id) is False
        assert db.count_dashboard_heartbeats() == 0

    async def test_clear_reports_deleted_count(self, db: Database) -> None:
        _seed_heartbeat(db)
        _seed_heartbeat(db)
        _seed_heartbeat(db)
        assert db.clear_dashboard_heartbeats() == 3
        assert db.count_dashboard_heartbeats() == 0
        assert db.clear_dashboard_heartbeats() == 0

    async def test_count_matches_rows(self, db: Database) -> None:
        assert db.count_dashboard_heartbeats() == 0
        _seed_heartbeat(db)
        assert db.count_dashboard_heartbeats() == 1

    async def test_schema_survives_reinit(self, db: Database) -> None:
        row_id = _seed_heartbeat(db)
        db.initialize()  # public alias for _initialize_database
        assert db.count_dashboard_heartbeats() == 1
        assert db.delete_dashboard_heartbeat(row_id) is True

    async def test_async_wrappers_match_sync_semantics(self, db: Database) -> None:
        row_id = await db.async_record_dashboard_heartbeat(
            market_open=False,
            kill_switch_active=True,
            breakers_open=2,
            telegram_delivered=False,
            detail='{"beat_index": 1}',
            message="async beat",
        )
        assert row_id > 0
        rows = await db.async_get_dashboard_heartbeats(limit=5)
        assert rows[0]["kill_switch_active"] is True
        assert rows[0]["telegram_delivered"] is False
        assert json.loads(rows[0]["detail"])["beat_index"] == 1
        assert await db.async_count_dashboard_heartbeats() == 1
        assert await db.async_delete_dashboard_heartbeat(row_id) is True
        assert await db.async_clear_dashboard_heartbeats() == 0


class TestSchedulerHeartbeatJob:
    """The 5-minute control-room heartbeat job."""

    def test_add_jobs_registers_five_minute_heartbeat(
        self, scheduler: TradingScheduler
    ) -> None:
        mock_add_job = MagicMock()
        scheduler.scheduler.add_job = mock_add_job

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(scheduler._add_jobs())
        finally:
            loop.close()

        heartbeat_calls = [
            call
            for call in mock_add_job.call_args_list
            if call.kwargs.get("id") == "dashboard_heartbeat"
        ]
        assert len(heartbeat_calls) == 1
        call = heartbeat_calls[0]
        trigger = call.args[1]
        assert trigger.interval == timedelta(minutes=5)
        assert call.kwargs["name"] == "Dashboard Heartbeat (Control Room)"
        assert call.kwargs["replace_existing"] is True

    async def test_run_once_dispatches_heartbeat(
        self, scheduler: TradingScheduler
    ) -> None:
        scheduler.run_dashboard_heartbeat = AsyncMock()
        await scheduler.run_once("dashboard_heartbeat")
        scheduler.run_dashboard_heartbeat.assert_awaited_once()

    async def test_run_once_heartbeat_failure_logs_not_raises(
        self, scheduler: TradingScheduler
    ) -> None:
        scheduler.run_dashboard_heartbeat = AsyncMock(
            side_effect=RuntimeError("beat boom")
        )
        with patch("loats.scheduler.logger") as mock_logger:
            await scheduler.run_once("dashboard_heartbeat")
        mock_logger.exception.assert_called_once()

    def _beat_env(self, scheduler: TradingScheduler, db: Database) -> MagicMock:
        """Wire the scheduler to the temp store and a stubbed alert bus."""
        scheduler.db = db
        scheduler.running = True
        scheduler.get_jobs = MagicMock(return_value=[{}, {}, {}, {}, {}])
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = False
        mock_alerts.get_circuit_breaker_status.return_value = {
            "openalgo": {"state": "closed"},
            "telegram": {"state": "closed"},
            "analyzer": {"state": "closed"},
        }
        mock_alerts.send_heartbeat = AsyncMock(return_value=True)
        return mock_alerts

    async def test_heartbeat_inserts_row_and_delivers(
        self, scheduler: TradingScheduler, db: Database
    ) -> None:
        mock_alerts = self._beat_env(scheduler, db)
        with (
            patch("loats.scheduler.alerts", mock_alerts),
            patch("loats.scheduler.is_market_open", return_value=True),
        ):
            await scheduler.run_dashboard_heartbeat()
            await scheduler.run_dashboard_heartbeat()

        assert mock_alerts.send_heartbeat.await_count == 2
        assert db.count_dashboard_heartbeats() == 2
        rows = db.get_dashboard_heartbeats()
        beat_numbers = sorted(json.loads(r["detail"])["beat_index"] for r in rows)
        assert beat_numbers == [1, 2]
        newest = rows[0]
        assert newest["market_open"] is True
        assert newest["kill_switch_active"] is False
        assert newest["breakers_open"] == 0
        assert newest["telegram_delivered"] is True
        detail = json.loads(newest["detail"])
        assert detail["scheduler_running"] is True
        assert detail["job_count"] == 5
        assert detail["open_breakers"] == []
        assert "DASHBOARD HEARTBEAT #2" in newest["message"]

    async def test_heartbeat_row_records_failed_delivery(
        self, scheduler: TradingScheduler, db: Database
    ) -> None:
        mock_alerts = self._beat_env(scheduler, db)
        mock_alerts.send_heartbeat = AsyncMock(return_value=False)
        with (
            patch("loats.scheduler.alerts", mock_alerts),
            patch("loats.scheduler.is_market_open", return_value=False),
        ):
            await scheduler.run_dashboard_heartbeat()

        # The row MUST exist even when Telegram delivery failed: the row is
        # the liveness record of the system, delivery is best-effort.
        rows = db.get_dashboard_heartbeats()
        assert len(rows) == 1
        assert rows[0]["telegram_delivered"] is False
        assert rows[0]["market_open"] is False

    async def test_heartbeat_swallows_store_failure(
        self, scheduler: TradingScheduler
    ) -> None:
        failing_db = MagicMock()
        failing_db.async_count_dashboard_heartbeats = AsyncMock(
            side_effect=RuntimeError("store down")
        )
        scheduler.db = failing_db
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = False
        mock_alerts.get_circuit_breaker_status.return_value = {}
        with (
            patch("loats.scheduler.alerts", mock_alerts),
            patch("loats.scheduler.is_market_open", return_value=True),
        ):
            with patch("loats.scheduler.logger") as mock_logger:
                await scheduler.run_dashboard_heartbeat()
        mock_logger.exception.assert_called_once()

    async def test_heartbeat_reports_open_breakers(
        self, scheduler: TradingScheduler, db: Database
    ) -> None:
        mock_alerts = self._beat_env(scheduler, db)
        mock_alerts.get_circuit_breaker_status.return_value = {
            "openalgo": {"state": "open"},
            "telegram": {"state": "closed"},
            "analyzer": {"state": "closed"},
        }
        with (
            patch("loats.scheduler.alerts", mock_alerts),
            patch("loats.scheduler.is_market_open", return_value=True),
            patch(
                "loats.utils.per_source_breakers.get_source_breaker_status",
                return_value={
                    "rss": {"state": "closed"},
                    "ta": {"state": "open"},
                },
            ),
        ):
            await scheduler.run_dashboard_heartbeat()

        row = db.get_dashboard_heartbeats()[0]
        assert row["breakers_open"] == 1
        assert "openalgo" in row["message"]
        assert "ta" in row["message"]
        detail = json.loads(row["detail"])
        assert detail["open_breakers"] == ["openalgo"]
        assert detail["open_sources"] == ["ta"]

    async def test_heartbeat_card_glyphs_are_pinned(
        self, scheduler: TradingScheduler, db: Database
    ) -> None:
        """Named pin: justifies scheduler.py ALLOWED_NON_ASCII entry.

        scripts/check_src_ascii.py admits a non-ASCII literal only when a
        named test asserts the exact glyph in a rendered payload. These
        are those assertions for the heartbeat card.
        """
        mock_alerts = self._beat_env(scheduler, db)
        with (
            patch("loats.scheduler.alerts", mock_alerts),
            patch("loats.scheduler.is_market_open", return_value=True),
        ):
            await scheduler.run_dashboard_heartbeat()
        message = db.get_dashboard_heartbeats()[0]["message"]
        assert "\U0001f940" in message  # heartbeat card identity
        assert "\U0001f7e2" in message  # green circle (open / disengaged)
        assert "\U0001f534" not in message  # nothing red on a healthy beat


class TestTelegramHeartbeatDelivery:
    """send_heartbeat: existing channel, no cooldown suppression."""

    async def test_send_heartbeat_delivers_without_cooldown(
        self, alert_system: AlertSystem
    ) -> None:
        with patch.object(
            alert_system, "_send_telegram_message", new=AsyncMock(return_value=True)
        ) as mock_send:
            first = await alert_system.send_heartbeat("beat 1")
            second = await alert_system.send_heartbeat("beat 2")
        assert first is True
        assert second is True
        # Two back-to-back beats MUST both reach the wire: a per-type
        # cooldown would swallow the second and fake a dead system.
        assert mock_send.await_count == 2

    async def test_send_heartbeat_returns_false_when_bot_missing(self) -> None:
        system = AlertSystem(database=MagicMock())
        system.bot = None
        assert await system.send_heartbeat("beat") is False


class TestDashboardCommands:
    """/heartbeats, /delete_heartbeat, /clear_heartbeats."""

    async def test_heartbeats_lists_recent_rows(
        self, alert_system: AlertSystem, db: Database
    ) -> None:
        _seed_heartbeat(db)
        _seed_heartbeat(db)
        update = _make_update()
        await alert_system._heartbeats(update, _make_context())
        reply = update.message.reply_text.await_args.args[0]
        assert "DASHBOARD HEARTBEATS" in reply
        assert "#2" in reply

    async def test_heartbeats_empty_store(self, alert_system: AlertSystem) -> None:
        update = _make_update()
        await alert_system._heartbeats(update, _make_context())
        reply = update.message.reply_text.await_args.args[0]
        assert "No dashboard heartbeats" in reply

    async def test_heartbeats_invalid_count_shows_usage(
        self, alert_system: AlertSystem
    ) -> None:
        update = _make_update()
        await alert_system._heartbeats(update, _make_context(["abc"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "Usage: /heartbeats" in reply

    async def test_heartbeats_count_clamped_to_twenty(self) -> None:
        mock_db = MagicMock()
        mock_db.async_get_dashboard_heartbeats = AsyncMock(return_value=[])
        system = AlertSystem(database=mock_db)
        update = _make_update()
        await system._heartbeats(update, _make_context(["999"]))
        mock_db.async_get_dashboard_heartbeats.assert_awaited_once_with(limit=20)

    async def test_delete_heartbeat_requires_admin(
        self, alert_system: AlertSystem, db: Database
    ) -> None:
        row_id = _seed_heartbeat(db)
        update = _make_update(user_id=999999)
        context = _make_context([str(row_id)])
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._delete_heartbeat(update, context)
        reply = update.message.reply_text.await_args.args[0]
        assert "Unauthorized" in reply
        assert db.count_dashboard_heartbeats() == 1  # NOT deleted

    async def test_delete_heartbeat_deletes_and_confirms(
        self, alert_system: AlertSystem, db: Database
    ) -> None:
        row_id = _seed_heartbeat(db)
        update = _make_update(user_id="123456789")
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._delete_heartbeat(update, _make_context([str(row_id)]))
        reply = update.message.reply_text.await_args.args[0]
        assert f"Heartbeat #{row_id} deleted" in reply
        assert db.count_dashboard_heartbeats() == 0

    async def test_delete_heartbeat_not_found(self, alert_system: AlertSystem) -> None:
        update = _make_update(user_id="123456789")
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._delete_heartbeat(update, _make_context(["4242"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "not found" in reply

    async def test_delete_heartbeat_invalid_id(self, alert_system: AlertSystem) -> None:
        update = _make_update(user_id="123456789")
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._delete_heartbeat(update, _make_context(["xyz"]))
        reply = update.message.reply_text.await_args.args[0]
        assert "Invalid heartbeat id" in reply

    async def test_delete_heartbeat_requires_id(
        self, alert_system: AlertSystem
    ) -> None:
        update = _make_update(user_id="123456789")
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._delete_heartbeat(update, _make_context([]))
        reply = update.message.reply_text.await_args.args[0]
        assert "Usage: /delete_heartbeat" in reply

    async def test_clear_heartbeats_requires_admin(
        self, alert_system: AlertSystem, db: Database
    ) -> None:
        _seed_heartbeat(db)
        update = _make_update(user_id=None)
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._clear_heartbeats(update, _make_context())
        reply = update.message.reply_text.await_args.args[0]
        assert "Unauthorized" in reply
        assert db.count_dashboard_heartbeats() == 1  # NOT cleared

    async def test_clear_heartbeats_reports_count(
        self, alert_system: AlertSystem, db: Database
    ) -> None:
        _seed_heartbeat(db)
        _seed_heartbeat(db)
        update = _make_update(user_id="123456789")
        with patch("loats.alerts.settings") as mock_settings:
            mock_settings.telegram_admin_ids = ["123456789"]
            await alert_system._clear_heartbeats(update, _make_context())
        reply = update.message.reply_text.await_args.args[0]
        assert "Cleared 2 heartbeat row(s)" in reply
        assert db.count_dashboard_heartbeats() == 0

    async def test_start_help_lists_heartbeat_commands(
        self, alert_system: AlertSystem
    ) -> None:
        update = _make_update()
        await alert_system._start(update, _make_context())
        reply = update.message.reply_text.await_args.args[0]
        assert "/heartbeats" in reply
        assert "/delete_heartbeat" in reply
        assert "/clear_heartbeats" in reply


class TestSupportJobWiring:
    """main.py's support-job enumeration includes the heartbeat."""

    async def test_support_jobs_enumerate_heartbeat(self) -> None:
        from loats.main import TradingSystem

        system = TradingSystem()
        with patch("loats.main.scheduler") as mock_scheduler:
            mock_scheduler.run_once = AsyncMock()
            await system._run_scheduler_support_jobs()
        job_ids = [call.args[0] for call in mock_scheduler.run_once.await_args_list]
        assert job_ids == [
            "market_status_check",
            "data_cleanup",
            "backtest_sanity_check",
            "dashboard_heartbeat",
        ]
