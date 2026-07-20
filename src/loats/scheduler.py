"""Scheduler module LOATS13July2026.

Implements APScheduler scan scheduling with retry and circuit breaker patterns.
"""

import asyncio
import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .database import db
from .logging import get_logger
from .models import FundsData, HistoricalData, Position, QuoteData, Signal, SignalType
from .openalgo import async_client as openalgo_client
from .sentiment import sentiment
from .ta import technical_analysis
from .utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER, CircuitBreakerOpenError
from .utils.retry import OPENALGO_RETRY_CONFIG, retry_async

logger = get_logger(__name__)


class TradingScheduler:
    """Scheduler for trading scans and operations."""

    def is_market_open(self) -> bool:
        """Check if market is open considering IST timezone, weekdays, and holidays.

        Returns:
            True if market is open, False otherwise
        """
        tz = ZoneInfo(settings.timezone)
        now = datetime.datetime.now(tz)

        # Check weekday (Monday=0, Sunday=6)
        # Indian markets are open Monday-Friday
        if now.weekday() >= 5:  # Saturday (5) or Sunday (6)
            return False

        # Indian market hours: 9:15 AM to 3:30 PM IST
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

        return market_open_time <= now <= market_close_time

    def __init__(self) -> None:
        """Initialize TradingScheduler."""
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.scan_tasks: dict[str, asyncio.Task[Any]] = {}

    async def initialize(self) -> None:
        """Initialize scheduler and set up jobs."""
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
            logger.exception("Failed to initialize scheduler")
            raise

    async def _add_jobs(self) -> None:
        """Add scheduled jobs to the scheduler."""
        # Technical Analysis scan (every 1 minute)
        self.scheduler.add_job(
            self.run_ta_scan,
            IntervalTrigger(seconds=settings.ta_scan_interval),
            id="ta_scan",
            name="Technical Analysis Scan",
            replace_existing=True,
        )

        # Sentiment scan (every 5 minutes)
        self.scheduler.add_job(
            self.run_sentiment_scan,
            IntervalTrigger(seconds=settings.sentiment_scan_interval),
            id="sentiment_scan",
            name="Sentiment Analysis Scan",
            replace_existing=True,
        )

        # Signal generation (every 30 seconds)
        self.scheduler.add_job(
            self.run_signal_generation,
            IntervalTrigger(seconds=settings.signal_scan_interval),
            id="signal_generation",
            name="Signal Generation",
            replace_existing=True,
        )

        # Market status checks (every 1 minute during market hours)
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

    async def start(self) -> None:
        """Start the scheduler."""
        if not self.running:
            try:
                self.scheduler.start()
                self.running = True
                logger.info("Trading scheduler started")

                # Run initial scans
                await self.run_ta_scan()
                await self.run_sentiment_scan()
                await self.run_signal_generation()
            except Exception:
                logger.exception("Failed to start scheduler")
                raise

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.running:
            try:
                # Cancel all running scan tasks
                for task_id, task in list(self.scan_tasks.items()):
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            logger.exception("Error cancelling task %s", task_id)

                self.scheduler.shutdown(wait=False)
                self.running = False
                logger.info("Trading scheduler shutdown complete")
            except Exception:
                logger.exception("Error shutting down scheduler")
                raise

    async def run_ta_scan(self) -> None:
        """Run technical analysis scan."""
        task_id = f"ta_scan_{datetime.datetime.now(datetime.UTC).isoformat()}"
        try:
            task = asyncio.create_task(self._ta_scan_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("TA scan task cancelled: %s", task_id)
        except Exception:
            logger.exception("TA scan task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _safe_get_history(self, symbol: str, interval: str) -> dict[str, Any] | None:
        """Get history with retry and circuit breaker protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: openalgo_client.get_history(
                        symbol=symbol, interval=interval, from_date=None, to_date=None
                    )
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_history: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get history after retries: %s", e)
            return None

    async def _safe_get_quotes(self, symbols: list[str]) -> dict[str, Any] | None:
        """Get quotes with retry and circuit breaker protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: openalgo_client.get_quotes(symbols)
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_quotes: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get quotes after retries: %s", e)
            return None

    async def _ta_scan_task(self) -> None:
        """Technical analysis scan task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting technical analysis scan")
        try:
            symbol = settings.default_symbol
            timeframe = settings.default_timeframe

            # Get historical data from OpenAlgo with retry and circuit breaker
            history_data = await self._safe_get_history(symbol, timeframe)

            if history_data is None:
                logger.warning("Skipping TA scan - unable to fetch historical data")
                return

            # Convert to HistoricalData objects
            historical_data = []
            for item in history_data.get("data", []):
                historical_data.append(
                    HistoricalData(
                        symbol=symbol,
                        timestamp=datetime.datetime.fromisoformat(item["timestamp"]),
                        open=item["open"],
                        high=item["high"],
                        low=item["low"],
                        close=item["close"],
                        volume=item["volume"],
                        interval=timeframe,
                    )
                )

            # Store historical data
            if historical_data:
                await db.async_store_historical_data(historical_data)

            # Calculate indicators
            indicators = technical_analysis.calculate_indicators(historical_data)

            # Get current price with retry and circuit breaker
            quotes = await self._safe_get_quotes([symbol])
            if quotes is None:
                logger.warning("Skipping signal generation - unable to fetch quotes")
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            current_price = quote_data.get("last_price", 0)

            # Generate signal
            signal_result = technical_analysis.generate_signal(
                indicators, current_price
            )
            if signal_result:
                signal_type, strength = signal_result
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType(signal_type),
                    strength=strength,
                    timestamp=datetime.datetime.now(datetime.UTC),
                    indicators={ind.name: ind.value for ind in indicators},
                    confidence=strength,
                    metadata={
                        "scan_type": "ta",
                        "timeframe": timeframe,
                        "indicators_count": len(indicators),
                    },
                )

                # Store signal
                await db.async_create_signal(signal)
                logger.info(
                    "TA signal generated: %s, strength %.2f", signal_type, strength
                )

                # Store quote
                if quote_data:
                    quote = QuoteData(
                        symbol=symbol,
                        last_price=quote_data["last_price"],
                        open=quote_data["open"],
                        high=quote_data["high"],
                        low=quote_data["low"],
                        close=quote_data["close"],
                        volume=quote_data["volume"],
                        timestamp=datetime.datetime.now(datetime.UTC),
                        change=quote_data.get("change", 0),
                        change_percent=quote_data.get("change_percent", 0),
                    )
                    await db.async_store_quote(quote)

        except Exception:
            logger.exception("Technical analysis scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Technical analysis scan completed in %.2fms", duration * 1000)

    async def run_sentiment_scan(self) -> None:
        """Run sentiment analysis scan."""
        task_id = f"sentiment_scan_{datetime.datetime.now(datetime.UTC).isoformat()}"
        try:
            task = asyncio.create_task(self._sentiment_scan_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Sentiment scan task cancelled: %s", task_id)
        except Exception:
            logger.exception("Sentiment scan task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _sentiment_scan_task(self) -> None:
        """Sentiment analysis scan task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting sentiment analysis scan")
        try:
            symbol = settings.default_symbol

            # Example RSS feeds
            rss_feeds = [
                "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "https://www.moneycontrol.com/rss/latestnews.xml",
                "https://www.bloombergquint.com/markets-feed",
            ]

            # Analyze sentiment
            result = await sentiment.analyze_symbol_sentiment(symbol, rss_feeds)

            # Store sentiment result
            metadata = {
                "scan_type": "sentiment",
                "news_count": result.news_count,
                "positive_count": result.positive_count,
                "negative_count": result.negative_count,
                "neutral_count": result.neutral_count,
                "top_sources": [news.source for news in result.top_news],
            }

            # Create signal based on sentiment
            if result.sentiment_score > 0:
                signal_type = SignalType.BUY
            elif result.sentiment_score < 0:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.NEUTRAL

            if abs(result.sentiment_score) < settings.sentiment_threshold:
                signal_type = SignalType.NEUTRAL

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=abs(result.sentiment_score),
                timestamp=datetime.datetime.now(datetime.UTC),
                indicators={"sentiment_score": result.sentiment_score},
                confidence=abs(result.sentiment_score),
                metadata=metadata,
            )

            # Store signal
            await db.async_create_signal(signal)
            logger.info(
                "Sentiment signal generated: %s, score %.2f",
                signal_type,
                result.sentiment_score,
            )

        except Exception:
            logger.exception("Sentiment analysis scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Sentiment analysis scan completed in %.2fms", duration * 1000)

    async def run_signal_generation(self) -> None:
        """Run signal generation scan."""
        task_id = f"signal_generation_{datetime.datetime.now(datetime.UTC).isoformat()}"
        try:
            task = asyncio.create_task(self._signal_generation_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Signal generation task cancelled: %s", task_id)
        except Exception:
            logger.exception("Signal generation task failed: %s", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _safe_get_position_book(self) -> dict[str, Any] | None:
        """Get position book with retry and circuit breaker protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: openalgo_client.get_position_book()
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_position_book: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get position book after retries: %s", e)
            return None

    async def _safe_get_funds(self) -> dict[str, Any] | None:
        """Get funds with retry and circuit breaker protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: openalgo_client.get_funds()
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_funds: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get funds after retries: %s", e)
            return None

    async def _signal_generation_task(self) -> None:
        """Signal generation task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting signal generation scan")
        try:
            symbol = settings.default_symbol

            # Get latest technical and sentiment signals
            ta_signals = await db.async_get_latest_signals(symbol, limit=1)
            sentiment_signals = await db.async_get_latest_signals(symbol, limit=1)

            # Get current market data with retry and circuit breaker
            quotes = await self._safe_get_quotes([symbol])
            if quotes is None:
                logger.warning("Skipping signal generation - unable to fetch quotes")
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            current_price = quote_data.get("last_price", 0)

            # Get current position and funds with retry and circuit breaker
            position_data = await self._safe_get_position_book()
            funds_data = await self._safe_get_funds()

            # Store position and funds data
            if position_data and position_data.get("data"):
                for pos in position_data["data"]:
                    pos_model = Position(
                        symbol=pos["symbol"],
                        quantity=pos["quantity"],
                        average_price=pos["average_price"],
                        last_price=pos["last_price"],
                        pnl=pos["pnl"],
                        product_type=pos["product_type"],
                        buy_quantity=pos["buy_quantity"],
                        sell_quantity=pos["sell_quantity"],
                    )
                    await db.async_store_position(pos_model)

            if funds_data and funds_data.get("data"):
                funds = funds_data["data"]
                funds_model = FundsData(
                    available_cash=funds["available_cash"],
                    utilized_margin=funds["utilized_margin"],
                    available_margin=funds["available_margin"],
                    total_equity=funds["total_equity"],
                    timestamp=datetime.datetime.now(datetime.UTC),
                )
                await db.async_store_funds(funds_model)

            # Combine signals
            ta_strength = ta_signals[0].strength if ta_signals else 0
            sentiment_strength = (
                sentiment_signals[0].strength if sentiment_signals else 0
            )

            combined_strength = (ta_strength + sentiment_strength) / 2

            # Determine signal type
            if combined_strength > 0.6:
                signal_type = SignalType.BUY
            elif combined_strength < 0.4:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.NEUTRAL

            # Create combined signal
            indicators = {}
            if ta_signals:
                indicators.update(ta_signals[0].indicators)
            if sentiment_signals:
                indicators.update(
                    {
                        "sentiment_score": sentiment_signals[0].indicators.get(
                            "sentiment_score", 0
                        )
                    }
                )

            metadata = {
                "scan_type": "combined",
                "ta_strength": ta_strength,
                "sentiment_strength": sentiment_strength,
                "current_price": current_price,
                "position_size": (
                    position_data.get("data", [{}])[0].get("quantity", 0)
                    if position_data and position_data.get("data")
                    else 0
                ),
                "available_funds": (
                    funds_data.get("data", {}).get("available_cash", 0)
                    if funds_data and funds_data.get("data")
                    else 0
                ),
            }

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=combined_strength,
                timestamp=datetime.datetime.now(datetime.UTC),
                indicators=indicators,
                confidence=combined_strength,
                metadata=metadata,
            )

            # Store signal
            await db.async_create_signal(signal)
            logger.info(
                "Combined signal generated: %s, strength %.2f",
                signal_type,
                combined_strength,
            )

            # Store quote
            if quote_data:
                quote = QuoteData(
                    symbol=symbol,
                    last_price=quote_data["last_price"],
                    open=quote_data["open"],
                    high=quote_data["high"],
                    low=quote_data["low"],
                    close=quote_data["close"],
                    volume=quote_data["volume"],
                    timestamp=datetime.datetime.now(datetime.UTC),
                    change=quote_data.get("change", 0),
                    change_percent=quote_data.get("change_percent", 0),
                )
                await db.async_store_quote(quote)

        except Exception:
            logger.exception("Signal generation scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Signal generation scan completed in %.2fms", duration * 1000)

    async def check_market_status(self) -> None:
        """Check market status and handle open/close events."""
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
        """Market status check task."""
        try:
            logger.debug("Checking market status")

            if not self.is_market_open():
                logger.debug("Market is closed")
                # Pause frequent scans
                for job_id in ["ta_scan", "sentiment_scan", "signal_generation"]:
                    if self.scheduler.get_job(job_id):
                        try:
                            self.scheduler.remove_job(job_id)
                        except Exception:
                            logger.warning("Failed to remove %s job", job_id)
                return

            logger.debug("Market is open")
            # Ensure all scans are running
            if not self.scheduler.get_job("ta_scan"):
                self.scheduler.add_job(
                    self.run_ta_scan,
                    IntervalTrigger(seconds=settings.ta_scan_interval),
                    id="ta_scan",
                    name="Technical Analysis Scan",
                )

            if not self.scheduler.get_job("sentiment_scan"):
                self.scheduler.add_job(
                    self.run_sentiment_scan,
                    IntervalTrigger(seconds=settings.sentiment_scan_interval),
                    id="sentiment_scan",
                    name="Sentiment Analysis Scan",
                )

            if not self.scheduler.get_job("signal_generation"):
                self.scheduler.add_job(
                    self.run_signal_generation,
                    IntervalTrigger(seconds=settings.signal_scan_interval),
                    id="signal_generation",
                    name="Signal Generation",
                )

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
            # Run database cleanup using public API
            await db.async_cleanup()

            # Verify audit log integrity
            if await db.async_verify_audit_log_integrity():
                logger.info("Audit log integrity verified")
            else:
                logger.warning("Audit log integrity check failed")

            # Optimize database
            await db.async_vacuum()
        except Exception:
            logger.exception("Data cleanup failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Data cleanup completed in %.2fms", duration * 1000)

    async def run_once(self, job_id: str) -> None:
        """Run a specific job once immediately.

        Args:
            job_id: ID of the job to run
        """
        try:
            if job_id == "ta_scan":
                await self.run_ta_scan()
            elif job_id == "sentiment_scan":
                await self.run_sentiment_scan()
            elif job_id == "signal_generation":
                await self.run_signal_generation()
            elif job_id == "market_status_check":
                await self.check_market_status()
            elif job_id == "data_cleanup":
                await self.run_data_cleanup()
            else:
                logger.warning("Unknown job ID: %s", job_id)
        except Exception:
            logger.exception("Failed to run job %s", job_id)

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get list of all scheduled jobs.

        Returns:
            List of job information
        """
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
        """Get OpenAlgo circuit breaker status for monitoring.

        Returns:
            Dictionary with circuit breaker status
        """
        return OPENALGO_CIRCUIT_BREAKER.get_status()

    def is_running(self) -> bool:
        """Check if scheduler is running.

        Returns:
            True if scheduler is running
        """
        return self.running


# Export default instance
scheduler = TradingScheduler()
