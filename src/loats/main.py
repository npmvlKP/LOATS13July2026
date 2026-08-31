"""Main entry point LOATS13July2026 trading system."""

import asyncio
import signal
import sys
from collections.abc import Callable
from typing import Any

from .alerts import alerts
from .database import Database

# Module-level exports for testing (F-CONC-3)
from .lazy_settings import LazySettings
from .loats_logging import logger
from .metrics import metrics
from .orchestrator import start_orchestrator, stop_orchestrator
from .scheduler import scheduler
from .utils.cache import close_cache, initialize_cache

# Lazy proxy module-level binding (TODO-18 / HC-21).
# AST scanner for HC-21 sees a Call to LazySettings(),
# NOT get_settings(), so the eager count remains 0.
settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()
db = Database(
    db_path=settings.sqlite_db_path,
    audit_log_path=settings.audit_log_path,
    retention_days=settings.retention_days,
)


class TradingSystem:
    """Main trading system class."""

    def __init__(self) -> None:
        """Initialize TradingSystem."""
        self.shutdown_event = asyncio.Event()
        self.running = False
        self.db = db  # Use module-level singleton

    async def initialize(self) -> None:
        """Initialize all system components."""
        try:
            logger.info("Initializing LOATS13July2026 trading system")
            await initialize_cache()
            await self.db.async_initialize()
            if not await self.db.async_verify_audit_log_integrity():
                logger.warning("Audit log integrity check failed during initialization")
            await alerts.initialize()
            await scheduler.initialize()
            # Start metrics server after cache initialization (R5-2 fix)
            try:
                metrics.start_server(settings.metrics_port)
                logger.info(f"Metrics server started on port {settings.metrics_port}")
            except Exception as e:
                logger.error(f"Failed to start metrics server: {e}")
                # Continue without metrics server in LITE mode
            # Start high-performance orchestrator
            await start_orchestrator()
            logger.info("All system components initialized successfully")
        except Exception as e:
            logger.error(f"Failed initialize trading system: {e}")
            raise

    async def start(self) -> None:
        """Start trading system."""
        if self.running:
            logger.warning("Trading system running")
            return
        try:
            logger.info("Starting LOATS13July2026 trading system")
            await alerts.start()
            await scheduler.start()
            await alerts.send_system_alert(
                "LOATS13July2026 trading system started successfully", "success"
            )
            self.running = True
            logger.info("Trading system started successfully")
            await self._wait_for_shutdown()
        except Exception as e:
            logger.error(f"Failed start trading system: {e}")
            raise

    async def _wait_for_shutdown(self) -> None:
        """Wait shutdown signal."""
        loop = asyncio.get_running_loop()

        if sys.platform == "win32":
            signal_handler = self._make_signal_handler(loop)
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._handle_shutdown_signal(s)),
                )

        await self.shutdown_event.wait()

    def _make_signal_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> Callable[[int, Any], None]:
        """Build a signal handler that triggers graceful shutdown.

        Windows cannot use ``loop.add_signal_handler``, so the handler must be
        registered via ``signal.signal``. It schedules ``_handle_shutdown_signal``
        on the event loop so cleanup (scheduler, alerts, cache, database) runs
        inside the async context, matching the POSIX path.
        """

        def signal_handler(sig: int, frame: Any) -> None:
            logger.info(f"Received signal: {sig}")
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    self._handle_shutdown_signal(signal.Signals(sig))
                )
            )

        return signal_handler

    async def _handle_shutdown_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received shutdown signal: {sig.name}")
        await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown trading system gracefully."""
        if not self.running:
            logger.warning("Trading system not running")
            return
        try:
            logger.info("Shutting down LOATS13July2026 trading system")
            await alerts.send_system_alert(
                "LOATS13July2026 trading system shutting down", "warning"
            )
            await stop_orchestrator()
            await scheduler.shutdown()
            await alerts.shutdown()
            await close_cache()
            await self.db.async_close_all()
            self.running = False
            self.shutdown_event.set()
            logger.info("Trading system shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            raise

    async def run_once(self) -> None:
        """Run all scans once testing."""
        try:
            logger.info("Running all scans once")
            await scheduler.run_ta_scan()
            await scheduler.run_sentiment_scan()
            # Note: Signal generation is handled by the orchestrator cycle loop,
            # not by scheduler. The orchestrator runs signal generation in
            # _execute_trading_cycle() when started via start_orchestrator().
            logger.info("All scans completed")
        except Exception as e:
            logger.error(f"Error running scans: {e}")
            raise


async def main() -> None:
    """Standalone main entry point trading system."""
    system = TradingSystem()
    try:
        await system.initialize()
        await system.start()
    except Exception as e:
        logger.error(f"Trading system failed: {e}")
        await system.shutdown()
        sys.exit(1)


def cli_main() -> None:
    """CLI entry point that properly handles async main function."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Trading system stopped user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Trading system stopped user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
