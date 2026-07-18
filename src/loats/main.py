"""Main entry point LOATS13July2026 trading system."""

import asyncio
import signal
import sys

from .alerts import alerts
from .config import settings
from .database import db
from .logging import logger
from .scheduler import scheduler


class TradingSystem:
    """Main trading system class."""

    def __init__(self) -> None:
        """Initialize TradingSystem."""
        self.shutdown_event = asyncio.Event()
        self.running = False

    async def initialize(self) -> None:
        """Initialize all system components."""
        try:
            logger.info("Initializing LOATS13July2026 trading system")

            # Initialize settings
            settings.initialize()

            # Initialize database
            db._initialize_database()
            if not db.verify_audit_log_integrity():
                logger.warning("Audit log integrity check failed during initialization")

            # Initialize alert system
            await alerts.initialize()

            # Initialize scheduler
            await scheduler.initialize()

            logger.info("All system components initialized successfully")

        except Exception as e:
            logger.error(f"Failed initialize trading system: {e}")
            raise

    async def start(self) -> None:
        """Start trading system."""
        if self.running:
            logger.warning("Trading system already running")
            return

        try:
            logger.info("Starting LOATS13July2026 trading system")

            # Start alert system
            await alerts.start()

            # Start scheduler
            await scheduler.start()

            # Send system startup alert
            await alerts.send_system_alert(
                "LOATS13July2026 trading system started successfully",
                "success",
            )

            self.running = True
            logger.info("Trading system started successfully")

            # Wait for shutdown
            await self._wait_for_shutdown()

        except Exception as e:
            logger.error(f"Failed start trading system: {e}")
            raise

    async def _wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()

        if sys.platform == "win32":
            # Windows: use add_signal_handler for SIGINT only
            sig = signal.SIGINT
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_shutdown_signal(sig)),  # type: ignore[misc]
            )
        else:
            # Unix: add multiple signal handlers
            loop.add_signal_handler(
                signal.SIGINT,
                lambda: asyncio.create_task(
                    self._handle_shutdown_signal(signal.SIGINT)
                ),  # type: ignore[misc]
            )
            loop.add_signal_handler(
                signal.SIGTERM,
                lambda: asyncio.create_task(
                    self._handle_shutdown_signal(signal.SIGTERM)
                ),  # type: ignore[misc]
            )

        # Wait for shutdown event
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

            # Send system shutdown alert
            await alerts.send_system_alert(
                "LOATS13July2026 trading system shutting down",
                "warning",
            )

            # Shutdown scheduler
            await scheduler.shutdown()

            # Shutdown alert system
            await alerts.shutdown()

            # Close database connections
            db.close()

            self.running = False
            self.shutdown_event.set()
            logger.info("Trading system shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            raise

    async def run_once(self) -> None:
        """Run all scans once for testing."""
        try:
            logger.info("Running all scans once")

            # Run TA scan
            await scheduler.run_ta_scan()

            # Run sentiment scan
            await scheduler.run_sentiment_scan()

            # Run signal generation
            await scheduler.run_signal_generation()

            logger.info("All scans completed")

        except Exception as e:
            logger.error(f"Error running scans: {e}")
            raise


async def main() -> None:
    """Main entry point for trading system."""
    system = TradingSystem()
    try:
        # Initialize system
        await system.initialize()

        # Start system
        await system.start()

    except Exception as e:
        logger.error(f"Trading system failed: {e}")
        await system.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Trading system stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
