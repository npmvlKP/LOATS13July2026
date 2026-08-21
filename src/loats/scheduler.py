"""Scheduler module LOATS13July2026.

Implements APScheduler scan scheduling retry circuit breaker patterns.
"""

import asyncio
import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .alerts import alerts
from .config import get_settings
from .database import db
from .loats_logging import get_logger
from .metrics import record_signal, track_job
from .models import (
    FundsData,
    HistoricalData,
    Position,
    QuoteData,
    Signal,
    SignalType,
)
from .openalgo import KillSwitchError, async_client
from .sentiment import sentiment
from .ta import technical_analysis
from .utils.circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
)
from .utils.resilience import openalgo_circuit_breaker_retry_async

settings = get_settings()

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


class TradingScheduler:
    """Scheduler trading scans operations."""

    def is_market_open(self) -> bool:
        """Check market open considering IST timezone, weekdays, holidays."""
        tz = ZoneInfo(settings.timezone)
        now = datetime.datetime.now(tz)
        # Check weekday (Monday=0, Sunday=6)
        # Indian markets open Monday-Friday
        if now.weekday() >= 5:  # Saturday (5) Sunday (6)
            return False

        # Indian markets closed on NSE/BSE trading holidays
        if now.date() in NSE_HOLIDAYS:
            return False

        # Indian market hours: 9:15 - 15:30 IST
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open_time <= now <= market_close_time

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
        """Add scheduled jobs scheduler."""
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

    async def start(self) -> None:
        """Start scheduler."""
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

    @track_job("ta_scan")
    async def _ta_scan_task(self) -> None:
        """Technical analysis scan task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting technical analysis scan")
        try:
            self._check_kill_switch()
            symbol = settings.default_symbol
            timeframe = settings.default_timeframe
            history_data = await self._safe_get_history(symbol, timeframe)
            if history_data is None:
                logger.warning("Skipping scan, unable fetch historical data")
                return

            historical_data_objs = []
            for item in history_data.get("data", []):
                historical_data_objs.append(
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

            await self.db.async_store_historical_data(historical_data_objs)
            indicators = technical_analysis.calculate_indicators(historical_data_objs)
            quotes = await self._safe_get_quotes([symbol])
            if quotes is None:
                logger.warning("Skipping signal generation, unable fetch quotes")
                return

            # Validate quote dict shape on entry (R5-F-09)
            if not quotes.get("data"):
                logger.warning("Skipping signal generation, quotes data missing")
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            if not quote_data:
                logger.warning(
                    "Skipping signal generation, quote data for symbol missing"
                )
                return

            # Validate required quote fields
            required_fields = ["last_price", "open", "high", "low", "close", "volume"]
            missing_fields = [f for f in required_fields if f not in quote_data]
            if missing_fields:
                logger.warning(
                    "Skipping signal generation, "
                    f"missing quote fields: {missing_fields}"
                )
                return
            current_price = quote_data.get("last_price", 0)

            signal_result = technical_analysis.generate_signal(
                indicators, current_price
            )
            if signal_result:
                signal_type, strength = signal_result
                record_signal(signal_type, "ta")
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
                await self.db.async_create_signal(signal)
                logger.info(
                    "TA signal generated: %s, strength %.2f", signal_type, strength
                )

            quote = QuoteData(
                symbol=symbol,
                last_price=quote_data.get("last_price", 0),
                open=quote_data.get("open", 0),
                high=quote_data.get("high", 0),
                low=quote_data.get("low", 0),
                close=quote_data.get("close", 0),
                volume=quote_data.get("volume", 0),
                timestamp=datetime.datetime.now(datetime.UTC),
                change=quote_data.get("change", 0),
                change_percent=quote_data.get("change_percent", 0),
            )
            await self.db.async_store_quote(quote)
        except KillSwitchError:
            logger.warning("Kill switch active - TA scan aborted")
            raise
        except Exception:
            logger.exception("Technical analysis scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Technical analysis scan completed %.2fms", duration * 1000)

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

    @track_job("sentiment_scan")
    async def _sentiment_scan_task(self) -> None:
        """Sentiment analysis scan task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting sentiment analysis scan")
        try:
            self._check_kill_switch()
            symbol = settings.default_symbol
            rss_feeds = [
                "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "https://www.moneycontrol.com/rss/latestnews.xml",
                "https://www.bloombergquint.com/markets-feed",
            ]
            result = await sentiment.analyze_symbol_sentiment(symbol, rss_feeds)
            metadata = {
                "scan_type": "sentiment",
                "news_count": result.news_count,
                "positive_count": result.positive_count,
                "negative_count": result.negative_count,
                "neutral_count": result.neutral_count,
                "top_sources": [news.source for news in result.top_news],
            }
            if result.sentiment_score > 0:
                signal_type = SignalType.BUY
            elif result.sentiment_score < 0:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.NEUTRAL

            if abs(result.sentiment_score) < settings.sentiment_threshold:
                signal_type = SignalType.NEUTRAL

            record_signal(signal_type.value, "sentiment")
            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=abs(result.sentiment_score),
                timestamp=datetime.datetime.now(datetime.UTC),
                indicators={"sentiment_score": result.sentiment_score},
                confidence=abs(result.sentiment_score),
                metadata=metadata,
            )
            await self.db.async_create_signal(signal)
            logger.info(
                "Sentiment signal generated: %s, score %.2f",
                signal_type,
                result.sentiment_score,
            )
        except KillSwitchError:
            logger.warning("Kill switch active - sentiment scan aborted")
            raise
        except Exception:
            logger.exception("Sentiment analysis scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Sentiment analysis scan completed %.2fms", duration * 1000)

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

    @track_job("signal_generation")
    async def _signal_generation_task(self) -> None:
        """Signal generation task."""
        start_time = datetime.datetime.now(datetime.UTC)
        logger.info("Starting signal generation scan")
        try:
            self._check_kill_switch()
            symbol = settings.default_symbol
            ta_signals = await self.db.async_get_latest_signals(
                symbol, limit=1, scan_type="ta"
            )
            sentiment_signals = await self.db.async_get_latest_signals(
                symbol, limit=1, scan_type="sentiment"
            )

            quotes = await self._safe_get_quotes([symbol])
            if quotes is None:
                logger.warning("Skipping signal generation, unable fetch quotes")
                return

            # Validate quote dict shape on entry (R5-F-09)
            if not quotes.get("data"):
                logger.warning("Skipping signal generation, quotes data missing")
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            if not quote_data:
                logger.warning(
                    "Skipping signal generation, quote data for symbol missing"
                )
                return

            # Validate required quote fields
            required_fields = ["last_price", "open", "high", "low", "close", "volume"]
            missing_fields = [f for f in required_fields if f not in quote_data]
            if missing_fields:
                logger.warning(
                    f"Skipping signal generation, "
                    f"missing quote fields: {missing_fields}"
                )
                return

            current_price = quote_data.get("last_price", 0)

            position_data = await self._safe_get_position_book()
            funds_data = await self._safe_get_funds()

            if position_data and position_data.get("data"):
                positions = position_data.get("data", [])
                for pos in positions:
                    pos_model = Position(
                        symbol=pos.get("symbol", ""),
                        quantity=pos.get("quantity", 0),
                        average_price=pos.get("average_price", 0.0),
                        last_price=pos.get("last_price", 0.0),
                        pnl=pos.get("pnl", 0.0),
                        product_type=pos.get("product_type", "MIS"),
                        buy_quantity=pos.get("buy_quantity", 0),
                        sell_quantity=pos.get("sell_quantity", 0),
                    )
                    await self.db.async_store_position(pos_model)

            if funds_data and funds_data.get("data"):
                funds = funds_data.get("data", {})
                funds_model = FundsData(
                    available_cash=funds.get("available_cash", 0.0),
                    utilized_margin=funds.get("utilized_margin", 0.0),
                    available_margin=funds.get("available_margin", 0.0),
                    total_equity=funds.get("total_equity", 0.0),
                    timestamp=datetime.datetime.now(datetime.UTC),
                )
                await self.db.async_store_funds(funds_model)

            ta_strength = ta_signals[0].strength if ta_signals else 0
            sentiment_strength = (
                sentiment_signals[0].strength if sentiment_signals else 0
            )

            combined_strength = (ta_strength + sentiment_strength) / 2

            if combined_strength > 0.6:
                signal_type = SignalType.BUY
            elif combined_strength < 0.4:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.NEUTRAL

            indicators: dict[str, float] = {}
            if ta_signals:
                indicators.update(ta_signals[0].indicators)
            if sentiment_signals:
                indicators.update(
                    {
                        "sentiment_score": sentiment_signals[0].indicators.get(
                            "sentiment_score", 0.0
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
                    if (position_data and position_data.get("data"))
                    else 0
                ),
                "available_funds": (
                    funds_data.get("data", {}).get("available_cash", 0)
                    if (funds_data and funds_data.get("data"))
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
            await self.db.async_create_signal(signal)
            logger.info(
                "Combined signal generated: %s, strength %.2f",
                signal_type,
                combined_strength,
            )

            quote = QuoteData(
                symbol=symbol,
                last_price=quote_data.get("last_price", 0),
                open=quote_data.get("open", 0),
                high=quote_data.get("high", 0),
                low=quote_data.get("low", 0),
                close=quote_data.get("close", 0),
                volume=quote_data.get("volume", 0),
                timestamp=datetime.datetime.now(datetime.UTC),
                change=quote_data.get("change", 0),
                change_percent=quote_data.get("change_percent", 0),
            )
            await self.db.async_store_quote(quote)
        except KillSwitchError:
            logger.warning("Kill switch active - signal generation aborted")
            raise
        except Exception:
            logger.exception("Signal generation scan failed")
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            logger.info("Signal generation scan completed %.2fms", duration * 1000)

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
        """Market status check task."""
        try:
            logger.debug("Checking market status")
            if not self.is_market_open():
                logger.debug("Market closed")
                for job_id in ["ta_scan", "sentiment_scan", "signal_generation"]:
                    if self.scheduler.get_job(job_id):
                        try:
                            self.scheduler.remove_job(job_id)
                        except Exception:
                            logger.warning("Failed remove job %s", job_id)
                return

            logger.debug("Market open")
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

    async def cleanup_old_data(self) -> None:
        """Cleanup old data method for testing."""
        await self._data_cleanup_task()

    async def run_once(self, job_id: str) -> None:
        """Run specific job once immediately."""
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
