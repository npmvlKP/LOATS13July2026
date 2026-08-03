"""Main entry point LOATS13July2026 trading system."""

import asyncio
import signal
import sys
from typing import Any

from .alerts import alerts
from .config import get_settings
from .database import Database
from .loats_logging import logger
from .metrics import start_metrics_server
from .scheduler import scheduler
from .utils.cache import close_cache, initialize_cache

# Module-level exports for testing (F-CONC-3)
settings = get_settings()
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
            start_metrics_server()
            await initialize_cache()
            await self.db.async_initialize()
            if not await self.db.async_verify_audit_log_integrity():
                logger.warning("Audit log integrity check failed during initialization")
            await alerts.initialize()
            await scheduler.initialize()
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

        def signal_handler(sig: int, frame: Any) -> None:
            logger.info(f"Received signal: {sig}")
            loop.call_soon_threadsafe(self.shutdown_event.set)

        if sys.platform == "win32":
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._handle_shutdown_signal(s)),
                )

        await self.shutdown_event.wait()

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
            await scheduler.run_signal_generation()
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Trading system stopped user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
