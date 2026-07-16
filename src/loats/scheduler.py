"""
Scheduler module for LOATS13July2026.
Implements APScheduler for scan scheduling.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .database import db
from .logging import get_logger
from .models import FundsData, HistoricalData, Position, QuoteData, Signal, SignalType
from .openalgo import client as openalgo_client
from .sentiment import sentiment
from .ta import ta

logger = get_logger(__name__)


class TradingScheduler:
    """Scheduler for trading scans and operations."""

    def __init__(self) -> None:
        """Initialize TradingScheduler."""
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.scan_tasks: dict[str, asyncio.Task] = {}

    async def initialize(self) -> None:
        """Initialize the scheduler and set up jobs."""
        try:
            # Set up scheduler
            self.scheduler.configure(
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 30,
                },
            )

            # Add jobs
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

        # Market open/close checks (every 1 minute during market hours)
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
                for task_id, task in self.scan_tasks.items():
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
        task_id = f"ta_scan_{datetime.now(timezone.utc).isoformat()}"
        try:
            # Create task and store reference
            task = asyncio.create_task(self._ta_scan_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("TA scan task %s cancelled", task_id)
        except Exception:
            logger.exception("TA scan task %s failed", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _ta_scan_task(self) -> None:
        """Technical analysis scan task."""
        start_time = datetime.now(timezone.utc)
        logger.info("Starting technical analysis scan")

        try:
            # Get default symbol
            symbol = settings.default_symbol
            timeframe = settings.default_timeframe

            # Get historical data from OpenAlgo
            with openalgo_client as client:
                history_data = await client.get_history(
                    symbol=symbol,
                    interval=timeframe,
                    from_date=None,
                    to_date=None,
                )

                # Convert to HistoricalData objects
                historical_data = []
                for item in history_data.get("data", []):
                    historical_data.append(
                        HistoricalData(
                            symbol=symbol,
                            timestamp=datetime.fromisoformat(item["timestamp"]),
                            open=item["open"],
                            high=item["high"],
                            low=item["low"],
                            close=item["close"],
                            volume=item["volume"],
                            interval=timeframe,
                        ),
                    )

                # Store historical data
                if historical_data:
                    db.store_historical_data(historical_data)

                    # Calculate indicators
                    indicators = ta.calculate_indicators(historical_data)

                    # Get current price
                    quotes = await client.get_quotes([symbol])
                    current_price = (
                        quotes.get("data", {}).get(symbol, {}).get("last_price", 0)
                    )

                    # Generate signal
                    signal_result = ta.generate_signal(indicators, current_price)
                    if signal_result:
                        signal_type, strength = signal_result
                        signal = Signal(
                            symbol=symbol,
                            signal_type=SignalType(signal_type),
                            strength=strength,
                            timestamp=datetime.now(timezone.utc),
                            indicators={ind.name: ind.value for ind in indicators},
                            confidence=strength,
                            metadata={
                                "scan_type": "ta",
                                "timeframe": timeframe,
                                "indicators_count": len(indicators),
                            },
                        )

                        # Store signal
                        db.create_signal(signal)
                        logger.info(
                            "TA signal generated: %s with strength %.2f",
                            signal_type,
                            strength,
                        )

                        # Store quote
                        quote_data = quotes.get("data", {}).get(symbol)
                        if quote_data:
                            quote = QuoteData(
                                symbol=symbol,
                                last_price=quote_data["last_price"],
                                open=quote_data["open"],
                                high=quote_data["high"],
                                low=quote_data["low"],
                                close=quote_data["close"],
                                volume=quote_data["volume"],
                                timestamp=datetime.now(timezone.utc),
                                change=quote_data.get("change", 0),
                                change_percent=quote_data.get("change_percent", 0),
                            )
                            db.store_quote(quote)

        except Exception:
            logger.exception("Technical analysis scan failed")
        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info("Technical analysis scan completed in %.2fms", duration * 1000)

    async def run_sentiment_scan(self) -> None:
        """Run sentiment analysis scan."""
        task_id = f"sentiment_scan_{datetime.now(timezone.utc).isoformat()}"
        try:
            # Create task and store reference
            task = asyncio.create_task(self._sentiment_scan_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Sentiment scan task %s cancelled", task_id)
        except Exception:
            logger.exception("Sentiment scan task %s failed", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _sentiment_scan_task(self) -> None:
        """Sentiment analysis scan task."""
        start_time = datetime.now(timezone.utc)
        logger.info("Starting sentiment analysis scan")

        try:
            # Get default symbol
            symbol = settings.default_symbol

            # Example RSS feeds - in production these would be configured
            rss_feeds = [
                "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "https://www.moneycontrol.com/rss/latestnews.xml",
                "https://www.bloombergquint.com/markets-feed",
            ]

            # Analyze sentiment
            result = sentiment.analyze_symbol_sentiment(symbol, rss_feeds)

            # Store sentiment result in metadata
            metadata = {
                "scan_type": "sentiment",
                "news_count": result.news_count,
                "positive_count": result.positive_count,
                "negative_count": result.negative_count,
                "neutral_count": result.neutral_count,
                "top_sources": [news.source for news in result.top_news],
            }

            # Create signal based on sentiment
            signal_type = (
                SignalType.BUY if result.sentiment_score > 0 else SignalType.SELL
            )
            if abs(result.sentiment_score) < settings.sentiment_threshold:
                signal_type = SignalType.NEUTRAL

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=abs(result.sentiment_score),
                timestamp=datetime.now(timezone.utc),
                indicators={"sentiment_score": result.sentiment_score},
                confidence=abs(result.sentiment_score),
                metadata=metadata,
            )

            # Store signal
            db.create_signal(signal)
            logger.info(
                "Sentiment signal generated: %s with score %.2f",
                signal_type,
                result.sentiment_score,
            )

        except Exception:
            logger.exception("Sentiment analysis scan failed")
        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info("Sentiment analysis scan completed in %.2fms", duration * 1000)

    async def run_signal_generation(self) -> None:
        """Run signal generation scan."""
        task_id = f"signal_generation_{datetime.now(timezone.utc).isoformat()}"
        try:
            # Create task and store reference
            task = asyncio.create_task(self._signal_generation_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Signal generation task %s cancelled", task_id)
        except Exception:
            logger.exception("Signal generation task %s failed", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _signal_generation_task(self) -> None:
        """Signal generation task."""
        start_time = datetime.now(timezone.utc)
        logger.info("Starting signal generation scan")

        try:
            # Get default symbol
            symbol = settings.default_symbol

            # Get latest TA and sentiment signals
            ta_signals = db.get_latest_signals(symbol, limit=1)
            sentiment_signals = db.get_latest_signals(symbol, limit=1)

            # Get current market data
            with openalgo_client as client:
                quotes = await client.get_quotes([symbol])
                current_price = (
                    quotes.get("data", {}).get(symbol, {}).get("last_price", 0)
                )

                # Get position and funds
                position = await client.get_position_book()
                funds = await client.get_funds()

                # Store position and funds data
                if position.get("data"):
                    for pos in position["data"]:
                        if pos["symbol"] == symbol:
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
                            db.store_position(pos_model)

                if funds.get("data"):
                    funds_model = FundsData(
                        available_cash=funds["data"]["available_cash"],
                        utilized_margin=funds["data"]["utilized_margin"],
                        available_margin=funds["data"]["available_margin"],
                        total_equity=funds["data"]["total_equity"],
                        timestamp=datetime.now(timezone.utc),
                    )
                    db.store_funds(funds_model)

            # Combine signals (simple average for this example)
            ta_strength = ta_signals[0].strength if ta_signals else 0
            sentiment_strength = (
                sentiment_signals[0].strength if sentiment_signals else 0
            )

            combined_strength = (ta_strength + sentiment_strength) / 2

            # Determine signal type based on combined strength
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
                            "sentiment_score",
                            0,
                        ),
                    },
                )

            metadata = {
                "scan_type": "combined",
                "ta_strength": ta_strength,
                "sentiment_strength": sentiment_strength,
                "current_price": current_price,
                "position_size": (
                    position.get("data", [{}])[0].get("quantity", 0)
                    if position.get("data")
                    else 0
                ),
                "available_funds": (
                    funds.get("data", {}).get("available_cash", 0)
                    if funds.get("data")
                    else 0
                ),
            }

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=combined_strength,
                timestamp=datetime.now(timezone.utc),
                indicators=indicators,
                confidence=combined_strength,
                metadata=metadata,
            )

            # Store signal
            db.create_signal(signal)
            logger.info(
                "Combined signal generated: %s with strength %.2f",
                signal_type,
                combined_strength,
            )

            # Store quote
            if quotes.get("data", {}).get(symbol):
                quote_data = quotes["data"][symbol]
                quote = QuoteData(
                    symbol=symbol,
                    last_price=quote_data["last_price"],
                    open=quote_data["open"],
                    high=quote_data["high"],
                    low=quote_data["low"],
                    close=quote_data["close"],
                    volume=quote_data["volume"],
                    timestamp=datetime.now(timezone.utc),
                    change=quote_data.get("change", 0),
                    change_percent=quote_data.get("change_percent", 0),
                )
                db.store_quote(quote)

        except Exception:
            logger.exception("Signal generation scan failed")
        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info("Signal generation scan completed in %.2fms", duration * 1000)

    async def check_market_status(self) -> None:
        """Check market status and handle open/close events."""
        task_id = f"market_status_check_{datetime.now(timezone.utc).isoformat()}"
        try:
            # Create task and store reference
            task = asyncio.create_task(self._market_status_check_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Market status check task %s cancelled", task_id)
        except Exception:
            logger.exception("Market status check task %s failed", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _market_status_check_task(self) -> None:
        """Market status check task."""
        try:
            # In a real implementation, this would check actual market status
            # For this example, we'll just log the check
            logger.debug("Checking market status")

            # Example: Check if market is open (9:15 AM to 3:30 PM IST)
            now = datetime.now(timezone.utc)
            market_open = now.hour > 9 or (now.hour == 9 and now.minute >= 15)
            market_closed = now.hour > 15 or (now.hour == 15 and now.minute >= 30)

            if market_open and not market_closed:
                logger.debug("Market is open")
                # Market is open - ensure all scans are running
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
            else:
                logger.debug("Market is closed")
                # Market is closed - pause frequent scans
                self.scheduler.remove_job("ta_scan")
                self.scheduler.remove_job("sentiment_scan")
                self.scheduler.remove_job("signal_generation")

        except Exception:
            logger.exception("Market status check failed")

    async def run_data_cleanup(self) -> None:
        """Run data cleanup task."""
        task_id = f"data_cleanup_{datetime.now(timezone.utc).isoformat()}"
        try:
            # Create task and store reference
            task = asyncio.create_task(self._data_cleanup_task())
            self.scan_tasks[task_id] = task
            await task
        except asyncio.CancelledError:
            logger.info("Data cleanup task %s cancelled", task_id)
        except Exception:
            logger.exception("Data cleanup task %s failed", task_id)
        finally:
            self.scan_tasks.pop(task_id, None)

    async def _data_cleanup_task(self) -> None:
        """Data cleanup task."""
        start_time = datetime.now(timezone.utc)
        logger.info("Starting data cleanup")

        try:
            # Run database cleanup
            db._cleanup_old_data()

            # Verify audit log integrity
            if db.verify_audit_log_integrity():
                logger.info("Audit log integrity verified")
            else:
                logger.warning("Audit log integrity check failed")

            # Optimize database
            db.vacuum()

        except Exception:
            logger.exception("Data cleanup failed")
        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info("Data cleanup completed in %.2fms", duration * 1000)

    async def run_once(self, job_id: str) -> None:
        """
        Run a specific job once immediately.

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
        """
        Get list of scheduled jobs.

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

    def is_running(self) -> bool:
        """
        Check if scheduler is running.

        Returns:
            True if scheduler is running
        """
        return self.running


# Export default instance
scheduler = TradingScheduler()
