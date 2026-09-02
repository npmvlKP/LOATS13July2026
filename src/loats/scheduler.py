"""Scheduler module LOATS13July2026.

Implements APScheduler scan scheduling retry circuit breaker patterns.

F8-H-03 architectural note: signal production is consolidated to the
orchestrator's 100 ms trading cycle, which is the sole engine of record for
CMP decisions.  The scheduler keeps market-status, data-cleanup and
backtest-sanity support jobs, but does NOT emit trading signals.
"""

import asyncio
import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .alerts import alerts
from .database import db
from .lazy_settings import LazySettings
from .loats_logging import get_logger
from .openalgo import KillSwitchError, async_client
from .utils.circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
)
from .utils.resilience import openalgo_circuit_breaker_retry_async

# Lazy proxy module-level binding (TODO-18 / HC-21).
# AST scanner for HC-21 sees a Call to LazySettings(),
# NOT get_settings(), so the eager count remains 0.
settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()

logger = get_logger(__name__)

# NSE / BSE trading-holidays calendar (3-year rolling window).
# 2026 = official NSE Indices calendar (niftyindices.com).
# 2027-2028 = projected per calendarlabs.com; re-verify against the
# official NSE circular (published ~Dec) before each trading year.
_NSE_HOLIDAY_TUPLES: tuple[tuple[int, int, int], ...] = (
    # 2026 - official NSE / NSE Indices calendar
    (2026, 1, 15),
    (2026, 1, 26),
    (2026, 3, 3),
    (2026, 3, 26),
    (2026, 3, 31),
    (2026, 4, 3),
    (2026, 4, 14),
    (2026, 5, 1),
    (2026, 5, 28),
    (2026, 6, 26),
    (2026, 9, 14),
    (2026, 10, 2),
    (2026, 10, 20),
    (2026, 11, 10),
    (2026, 11, 24),
    (2026, 12, 25),
    # 2027 - projected (verify vs official NSE circular)
    (2027, 1, 26),
    (2027, 3, 6),
    (2027, 3, 10),
    (2027, 3, 22),
    (2027, 3, 26),
    (2027, 4, 14),
    (2027, 4, 15),
    (2027, 4, 19),
    (2027, 5, 1),
    (2027, 5, 17),
    (2027, 6, 15),
    (2027, 8, 15),
    (2027, 9, 4),
    (2027, 10, 2),
    (2027, 10, 10),
    (2027, 10, 29),
    (2027, 11, 14),
    (2027, 12, 25),
    # 2028 - projected (verify vs official NSE circular; Good Friday corrected)
    (2028, 1, 26),
    (2028, 2, 23),
    (2028, 2, 27),
    (2028, 3, 11),
    (2028, 4, 4),
    (2028, 4, 7),
    (2028, 4, 13),
    (2028, 4, 14),
    (2028, 5, 1),
    (2028, 5, 5),
    (2028, 6, 3),
    (2028, 8, 15),
    (2028, 8, 23),
    (2028, 9, 27),
    (2028, 10, 2),
    (2028, 10, 17),
    (2028, 10, 18),
    (2028, 11, 2),
    (2028, 12, 25),
)
NSE_HOLIDAYS: frozenset[datetime.date] = frozenset(
    datetime.date(y, m, d) for y, m, d in _NSE_HOLIDAY_TUPLES
)


def is_market_open(now: datetime.datetime | None = None) -> bool:
    """Check whether Indian markets are open for the given timestamp.

    Args:
        now: Timestamp to evaluate (defaults to current time in settings.timezone).

    Returns:
        True if the timestamp falls on a weekday, non-holiday, between 9:15
        and 15:30 IST; otherwise False.
    """
    tz = ZoneInfo(settings.timezone)
    if now is None:
        now = datetime.datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    if now.weekday() >= 5:
        return False

    if now.date() in NSE_HOLIDAYS:
        return False

    market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open_time <= now <= market_close_time


class TradingScheduler:
    """Scheduler trading scans operations."""

    def is_market_open(self) -> bool:
        """Check market open considering IST timezone, weekdays, holidays."""
        return is_market_open()

    def __init__(self) -> None:
        """Initialize TradingScheduler."""
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.scan_tasks: dict[str, asyncio.Task[dict[str, Any] | None]] = {}
        # Use shared module-level db singleton to avoid resource leaks on shutdown
        self.db = db

    async def initialize(self) -> None:
        """Initialize scheduler set jobs."""
        try:
            self.scheduler.configure(
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 30,
                }
            )
            await self._add_jobs()
            logger.info("Trading scheduler initialized")
        except Exception:
            logger.exception("Failed initialize scheduler")
            raise

    async def _add_jobs(self) -> None:
        """Add scheduled jobs scheduler.

        F8-H-03 (TODO-19 completion): signal production is consolidated to the
        orchestrator's 100 ms cycle, which is the sole engine of record for CMP
        decisions.  The scheduler therefore does NOT register ta_scan or
        sentiment_scan signal-emitting jobs; it keeps market-status,
        data-cleanup and backtest-sanity support jobs.
        """
        # Market status checks (every 1 minute)
        self.scheduler.add_job(
            self.check_market_status,
            IntervalTrigger(minutes=1),
            id="market_status_check",
            name="Market Status Check",
            replace_existing=True,
        )
        # Data cleanup (daily at 3 AM)
        self.scheduler.add_job(
            self.run_data_cleanup,
            CronTrigger(hour=3, minute=0),
            id="data_cleanup",
            name="Data Cleanup",
            replace_existing=True,
        )
        # Backtest sanity check (weekly on Sunday at 4 AM IST)
        self.scheduler.add_job(
            self.run_backtest_sanity_check,
            CronTrigger(day_of_week="sun", hour=4, minute=0),
            id="backtest_sanity_check",
            name="Backtest Sanity Check",
            replace_existing=True,
        )

    async def start(self) -> None:
        """Start scheduler.

        F8-H-03: ta_scan and sentiment_scan are no longer scheduled; the
        orchestrator produces all signals.  Only market-status is kicked off.
        """
        if not self.running:
            try:
                self.scheduler.start()
                self.running = True
                logger.info("Trading scheduler started")
                # Run initial market-status check so open/close logic is current
                await self.check_market_status()
            except Exception:
                logger.exception("Failed start scheduler")
                raise

    async def shutdown(self) -> None:
        """Shutdown scheduler."""
        if self.running:
            try:
                # Cancel all running scan tasks
                tasks = list(self.scan_tasks.values())
                for task in tasks:
                    if not task.done():
                        task.cancel()
                # Wait for tasks to cancel
                if self.scan_tasks:
                    await asyncio.gather(
                        *self.scan_tasks.values(), return_exceptions=True
                    )
                self.scheduler.shutdown(wait=False)
                self.running = False
                logger.info("Trading scheduler shutdown complete")

                # FIX-R5-F-02: Close database connection pool to prevent leaks
                # The scheduler uses the shared module-level db singleton.
                # Ensure proper cleanup of async resources during shutdown.
                if hasattr(self, "db") and self.db:
                    try:
                        await self.db.async_close_all()
                        logger.info("Scheduler database connections closed")
                    except Exception as e:
                        logger.warning(
                            f"Error closing scheduler database connections: {e}"
                        )
            except Exception:
                logger.exception("Error shutting down scheduler")
                raise

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_history(
        self, symbol: str, interval: str, count: int | None = None
    ) -> dict[str, Any] | None:
        """Get history retry circuit breaker protection."""
        try:
            return await async_client.get_history(
                symbol=symbol, interval=interval, from_date=None, to_date=None
            )
        except Exception:
            logger.error("Failed get history after retries")
            raise  # Re-raise to allow circuit breaker to record failure

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_quotes(self, symbols: list[str]) -> dict[str, Any] | None:
        """Get quotes retry circuit breaker protection."""
        try:
            return await async_client.get_quotes(symbols)
        except Exception:
            logger.error("Failed get quotes after retries")
            raise  # Re-raise to allow test to catch it

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_position_book(self) -> dict[str, Any] | None:
        """Get position book retry circuit breaker protection."""
        try:
            return await async_client.get_position_book()
        except Exception:
            logger.error("Failed get position book after retries")
            raise

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_funds(self) -> dict[str, Any] | None:
        """Get funds retry circuit breaker protection."""
        try:
            return await async_client.get_funds()
        except Exception:
            logger.error("Failed get funds after retries")
            raise

    async def check_market_status(self) -> None:
        """Check market status handle open/close events."""
        task_id = (
            f"market_status_check_{datetime.datetime.now(datetime.UTC).isoformat()}"
        )
        try:
            task = asyncio.create_task(self._market_status_check_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Market status check task cancelled: %s", task_id)
        except Exception:
            logger.exception("Market status check task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _market_status_check_task(self) -> None:
        """Market status check task.

        F8-H-03: signal production (ta_scan / sentiment_scan) has been removed
        from the scheduler.  This method now only logs market state; signal
        producers live in the orchestrator's 100 ms cycle and are not dynamically
        added or removed here.
        """
        try:
            logger.debug("Checking market status")
            if not self.is_market_open():
                logger.debug("Market closed")
                return

            logger.debug("Market open")
        except Exception:
            logger.exception("Market status check failed")

    async def run_data_cleanup(self) -> None:
        """Run data cleanup task."""
        task_id = f"data_cleanup_{datetime.datetime.now(datetime.UTC).isoformat()}"
        try:
            task = asyncio.create_task(self._data_cleanup_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Data cleanup task cancelled: %s", task_id)
        except Exception:
            logger.exception("Data cleanup task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _data_cleanup_task(self) -> None:
        """Data cleanup task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting data cleanup")
        try:
            await self.db.async_cleanup()
            await self.db.async_verify_audit_log_integrity()
            logger.info("Audit log integrity verified")
            await self.db.async_vacuum()
        except Exception:
            logger.exception("Data cleanup failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Data cleanup completed %.2fms", duration * 1000)

    async def run_backtest_sanity_check(self) -> None:
        """Run backtest sanity check task (CMP P4 exit gate)."""
        task_id = f"backtest_sanity_{datetime.datetime.now(datetime.UTC).isoformat()}"
        try:
            task = asyncio.create_task(self._backtest_sanity_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Backtest sanity task cancelled: %s", task_id)
        except Exception:
            logger.exception("Backtest sanity task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _backtest_sanity_task(self) -> None:
        """Backtest sanity check task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting backtest sanity check")
        try:
            # Import here to avoid circular dependencies
            from .backtest_sanity import (
                backtest_sanity_pass_gate,
            )
            from .backtest_sanity import run_backtest_sanity_check as run_sanity

            # Run sanity check on default symbol for 30 days
            result = await run_sanity(
                symbol=settings.default_symbol,
                days_back=30,
                window_size=20,
                step_size=10,
            )

            # Check if gate passes (80% pass rate)
            passes = backtest_sanity_pass_gate(result)

            logger.info(
                "Backtest sanity check completed: %s",
                "PASS" if passes else "FAIL",
                extra={
                    "symbol": result.symbol,
                    "total_windows": result.total_windows,
                    "pass_rate": float(result.pass_rate),
                    "windows_passed": result.windows_passed,
                    "windows_failed": result.windows_failed,
                    "avg_pnl": float(result.avg_pnl_per_window),
                    "passes_gate": passes,
                },
            )

            # Alert if gate fails
            if not passes:
                from .alerts import alerts

                await alerts.send_alert(
                    f"Backtest Sanity Check Failed: {result.symbol}",
                    f"Backtest sanity check failed for {result.symbol}. "
                    f"Pass rate: {result.pass_rate:.1f}% (target: 80%). "
                    f"Total windows: {result.total_windows}, "
                    f"Failed: {result.windows_failed}",
                )

        except Exception:
            logger.exception("Backtest sanity check failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Backtest sanity check completed %.2fms", duration * 1000)

    async def cleanup_old_data(self) -> None:
        """Cleanup old data method for testing."""
        await self._data_cleanup_task()

    async def run_once(self, job_id: str) -> None:
        """Run specific job once immediately.

        F8-H-03: ``ta_scan`` and ``sentiment_scan`` are no longer supported;
        they are retired with the dual-engine consolidation.  Only support jobs
        (market_status_check, data_cleanup, backtest_sanity_check) remain.
        """
        try:
            if job_id in {"ta_scan", "sentiment_scan"}:
                logger.warning(
                    "Job '%s' is retired; signal production is "
                    "handled by the orchestrator",
                    job_id,
                )
                return
            if job_id == "market_status_check":
                await self.check_market_status()
            elif job_id == "data_cleanup":
                await self.run_data_cleanup()
            elif job_id == "backtest_sanity_check":
                await self.run_backtest_sanity_check()
            else:
                logger.warning("Unknown job ID: %s", job_id)
        except Exception:
            logger.exception("Failed run job %s", job_id)

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get list all scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": job.next_run_time,
            }
            for job in self.scheduler.get_jobs()
        ]

    def get_circuit_breaker_status(self) -> dict[str, Any]:
        """Get OpenAlgo circuit breaker status monitoring."""
        return OPENALGO_CIRCUIT_BREAKER.get_status()

    def _check_kill_switch(self) -> None:
        """Check kill switch active raise KillSwitchError so."""
        if alerts.is_kill_switch_active():
            logger.error("Kill switch active trading operations blocked")
            raise KillSwitchError()

    def is_running(self) -> bool:
        """Check scheduler running."""
        return self.running


# Export default instance and provide backward-compatible alias
scheduler = TradingScheduler()
Scheduler = TradingScheduler  # Backward compatibility alias
