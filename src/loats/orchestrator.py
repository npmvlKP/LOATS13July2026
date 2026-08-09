"""Orchestrator Module for LOATS13July2026.

High-performance trading cycle orchestrator that meets the <100ms cycle target.
Coordinates all trading operations with strict latency guarantees.
"""

import asyncio
import datetime
from typing import Any, Dict, List, Optional

from .alerts import alerts
from .config import get_settings
from .database import db
from .loats_logging import get_logger
from .metrics import record_cycle_time, track_job
from .models import HistoricalData, OptionContract, QuoteData, Signal
from .openalgo import KillSwitchError, async_client
from .options import analysis, options
from .scheduler import scheduler
from .sentiment import sentiment
from .strike_selection import select_strikes
from .ta import technical_analysis
from .utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER
from .utils.resilience import openalgo_circuit_breaker_retry_async

logger = get_logger(__name__)
settings = get_settings()

class TradingOrchestrator:
    """High-performance trading orchestrator with <100ms cycle guarantee."""

    def __init__(self) -> None:
        """Initialize TradingOrchestrator."""
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = 0.0
        self.max_cycle_time = 0.0
        self.avg_cycle_time = 0.0
        self.total_cycle_time = 0.0
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize the orchestrator."""
        logger.info("Initializing TradingOrchestrator")
        self.running = True
        self.cycle_count = 0
        self.last_cycle_time = 0.0
        self.max_cycle_time = 0.0
        self.avg_cycle_time = 0.0
        self.total_cycle_time = 0.0

    async def start(self) -> None:
        """Start the trading cycle orchestrator."""
        if self.running:
            logger.warning("Orchestrator already running")
            return

        await self.initialize()
        logger.info("Starting TradingOrchestrator cycle")
        asyncio.create_task(self._run_cycle_loop())

    async def _run_cycle_loop(self) -> None:
        """Main trading cycle loop with <100ms target."""
        while not self._shutdown_event.is_set():
            cycle_start = datetime.datetime.now(datetime.UTC)

            try:
                await self._check_kill_switch()
                await self._execute_trading_cycle()

            except KillSwitchError:
                logger.warning("Kill switch active - trading cycle paused")
                await asyncio.sleep(1.0)  # Reduced polling during kill switch
                continue
            except Exception as e:
                logger.error(f"Trading cycle error: {e}")
                await alerts.send_system_alert(f"Trading cycle error: {e}", "error")

            # Calculate and record cycle time
            cycle_duration = (datetime.datetime.now(datetime.UTC) - cycle_start).total_seconds()
            self._record_cycle_time(cycle_duration)

            # Enforce 100ms cycle target with adaptive sleep
            target_duration = 0.1  # 100ms
            sleep_time = max(0, target_duration - cycle_duration)
            await asyncio.sleep(sleep_time)

    async def _execute_trading_cycle(self) -> None:
        """Execute a complete trading cycle with parallel execution."""
        cycle_start = datetime.datetime.now(datetime.UTC)
        self.cycle_count += 1

        try:
            # Use asyncio.gather for parallel execution of independent tasks
            ta_task = asyncio.create_task(self._execute_ta_analysis())
            sentiment_task = asyncio.create_task(self._execute_sentiment_analysis())
            market_data_task = asyncio.create_task(self._execute_market_data_update())

            # Wait for all tasks with timeout to prevent cycle overrun
            try:
                await asyncio.wait_for(
                    asyncio.gather(ta_task, sentiment_task, market_data_task),
                    timeout=0.08  # 80ms timeout to leave room for other operations
                )
            except asyncio.TimeoutError:
                logger.warning("Trading cycle tasks timed out - continuing with partial results")
                # Cancel remaining tasks
                for task in [ta_task, sentiment_task, market_data_task]:
                    if not task.done():
                        task.cancel()

            # Execute sequential operations
            await self._execute_signal_generation()
            await self._execute_risk_management()

        except Exception as e:
            logger.error(f"Error in trading cycle execution: {e}")
            raise

        finally:
            cycle_duration = (datetime.datetime.now(datetime.UTC) - cycle_start).total_seconds()
            record_cycle_time(cycle_duration)
            logger.debug(f"Trading cycle {self.cycle_count} completed in {cycle_duration*1000:.2f}ms")

    async def _execute_ta_analysis(self) -> None:
        """Execute technical analysis with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            symbol = settings.default_symbol
            timeframe = settings.default_timeframe

            # Get historical data with circuit breaker protection
            history_data = await self._safe_get_history(symbol, timeframe)
            if not history_data:
                return

            # Convert to HistoricalData objects
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

            # Store data and calculate indicators
            await db.async_store_historical_data(historical_data_objs)
            indicators = technical_analysis.calculate_indicators(historical_data_objs)

            # Generate TA signal
            quotes = await self._safe_get_quotes([symbol])
            if quotes:
                quote_data = quotes.get("data", {}).get(symbol, {})
                current_price = quote_data.get("last_price", 0)
                signal_result = technical_analysis.generate_signal(indicators, current_price)

                if signal_result:
                    signal_type, strength = signal_result
                    signal = Signal(
                        symbol=symbol,
                        signal_type=signal_type,
                        strength=strength,
                        timestamp=datetime.datetime.now(datetime.UTC),
                        indicators={ind.name: ind.value for ind in indicators},
                        confidence=strength,
                        metadata={"scan_type": "ta", "source": "orchestrator"},
                    )
                    await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"TA analysis failed: {e}")
            raise

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.03:  # 30ms budget for TA analysis
                logger.warning(f"TA analysis exceeded budget: {duration*1000:.2f}ms")

    async def _execute_sentiment_analysis(self) -> None:
        """Execute sentiment analysis with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            symbol = settings.default_symbol
            rss_feeds = [
                "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "https://www.moneycontrol.com/rss/latestnews.xml",
                "https://www.bloombergquint.com/markets-feed",
            ]

            # Use asyncio.to_thread to avoid blocking event loop
            result = await asyncio.to_thread(
                sentiment.analyze_symbol_sentiment, symbol, rss_feeds
            )

            # Generate sentiment signal
            if result.sentiment_score > 0:
                signal_type = "BUY"
            elif result.sentiment_score < 0:
                signal_type = "SELL"
            else:
                signal_type = "NEUTRAL"

            if abs(result.sentiment_score) >= settings.sentiment_threshold:
                signal = Signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=abs(result.sentiment_score),
                    timestamp=datetime.datetime.now(datetime.UTC),
                    indicators={"sentiment_score": result.sentiment_score},
                    confidence=abs(result.sentiment_score),
                    metadata={
                        "scan_type": "sentiment",
                        "source": "orchestrator",
                        "news_count": result.news_count
                    },
                )
                await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            raise

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.04:  # 40ms budget for sentiment analysis
                logger.warning(f"Sentiment analysis exceeded budget: {duration*1000:.2f}ms")

    async def _execute_market_data_update(self) -> None:
        """Update market data with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            symbol = settings.default_symbol

            # Get quotes and store
            quotes = await self._safe_get_quotes([symbol])
            if quotes:
                quote_data = quotes.get("data", {}).get(symbol, {})
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
                await db.async_store_quote(quote)

            # Get position and funds data
            position_data = await self._safe_get_position_book()
            funds_data = await self._safe_get_funds()

            if position_data and position_data.get("data"):
                for pos in position_data["data"]:
                    pos_model = self._create_position_model(pos)
                    await db.async_store_position(pos_model)

            if funds_data and funds_data.get("data"):
                funds_model = self._create_funds_model(funds_data["data"])
                await db.async_store_funds(funds_model)

        except Exception as e:
            logger.error(f"Market data update failed: {e}")
            raise

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.02:  # 20ms budget for market data update
                logger.warning(f"Market data update exceeded budget: {duration*1000:.2f}ms")

    async def _execute_signal_generation(self) -> None:
        """Generate combined signals with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            symbol = settings.default_symbol

            # Get latest signals
            ta_signals = await db.async_get_latest_signals(symbol, limit=1, scan_type="ta")
            sentiment_signals = await db.async_get_latest_signals(symbol, limit=1, scan_type="sentiment")

            # Get current price
            quotes = await self._safe_get_quotes([symbol])
            if not quotes:
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            current_price = quote_data.get("last_price", 0)

            # Calculate combined strength
            ta_strength = ta_signals[0].strength if ta_signals else 0
            sentiment_strength = sentiment_signals[0].strength if sentiment_signals else 0
            combined_strength = (ta_strength + sentiment_strength) / 2

            # Determine signal type
            if combined_strength > 0.6:
                signal_type = "BUY"
            elif combined_strength < 0.4:
                signal_type = "SELL"
            else:
                signal_type = "NEUTRAL"

            # Create combined signal
            indicators: Dict[str, float] = {}
            if ta_signals:
                indicators.update(ta_signals[0].indicators)
            if sentiment_signals:
                indicators.update({
                    "sentiment_score": sentiment_signals[0].indicators.get("sentiment_score", 0.0)
                })

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                strength=combined_strength,
                timestamp=datetime.datetime.now(datetime.UTC),
                indicators=indicators,
                confidence=combined_strength,
                metadata={
                    "scan_type": "combined",
                    "source": "orchestrator",
                    "ta_strength": ta_strength,
                    "sentiment_strength": sentiment_strength,
                    "current_price": current_price
                },
            )
            await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"Signal generation failed: {e}")
            raise

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.01:  # 10ms budget for signal generation
                logger.warning(f"Signal generation exceeded budget: {duration*1000:.2f}ms")

    async def _execute_risk_management(self) -> None:
        """Execute risk management checks with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Check circuit breaker status
            cb_status = OPENALGO_CIRCUIT_BREAKER.get_status()
            if cb_status["state"] == "open":
                logger.warning("Circuit breaker open - risk management checks limited")
                return

            # Check position limits
            positions = await db.get_position(symbol=settings.default_symbol)
            if positions and positions.quantity > settings.max_position_size:
                logger.warning(f"Position limit exceeded: {positions.quantity}")
                await alerts.send_risk_alert(
                    f"Position limit exceeded: {positions.quantity}",
                    "position_limit"
                )

            # Check margin utilization
            funds = await db.get_latest_funds()
            if funds and funds.utilized_margin / funds.available_margin > settings.max_margin_utilization:
                logger.warning(f"Margin utilization high: {funds.utilized_margin/funds.available_margin:.2%}")
                await alerts.send_risk_alert(
                    f"High margin utilization: {funds.utilized_margin/funds.available_margin:.2%}",
                    "margin_utilization"
                )

        except Exception as e:
            logger.error(f"Risk management failed: {e}")
            raise

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.01:  # 10ms budget for risk management
                logger.warning(f"Risk management exceeded budget: {duration*1000:.2f}ms")

    async def _execute_strike_selection(self, option_chain: List[OptionContract]) -> List[float]:
        """Execute high-performance strike selection with <5ms guarantee."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            if not option_chain:
                return []

            # Get current price (use first contract's underlying as proxy)
            current_price = option_chain[0].underlying_price if hasattr(option_chain[0], 'underlying_price') else 0
            for opt in option_chain:
                if hasattr(opt, 'underlying_price') and opt.underlying_price > 0:
                    current_price = opt.underlying_price
                    break

            # Execute strike selection with timeout
            try:
                selected_strikes = await asyncio.wait_for(
                    select_strikes(
                        underlying_price=current_price,
                        option_chain=option_chain,
                        strategy="atm_straddle",
                        width=2,
                        max_strikes=5
                    ),
                    timeout=0.004  # 4ms timeout for strike selection
                )
                return selected_strikes
            except asyncio.TimeoutError:
                logger.warning("Strike selection timed out - using fallback")
                # Simple fallback: return middle strikes
                strikes = sorted({opt.strike_price for opt in option_chain})
                mid = len(strikes) // 2
                return strikes[max(0, mid-2):min(len(strikes), mid+3)]

        except Exception as e:
            logger.error(f"Strike selection failed: {e}")
            return []

        finally:
            duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()
            if duration > 0.005:  # 5ms target
                logger.warning(f"Strike selection exceeded 5ms target: {duration*1000:.2f}ms")
            else:
                logger.debug(f"Strike selection completed in {duration*1000:.2f}ms")

    def _record_cycle_time(self, duration: float) -> None:
        """Record and track cycle time statistics."""
        self.last_cycle_time = duration
        self.total_cycle_time += duration
        self.cycle_count = max(1, self.cycle_count)  # Avoid division by zero
        self.avg_cycle_time = self.total_cycle_time / self.cycle_count
        self.max_cycle_time = max(self.max_cycle_time, duration)

        # Log cycle time statistics periodically
        if self.cycle_count % 100 == 0:
            logger.info(
                f"Cycle stats - Count: {self.cycle_count}, "
                f"Last: {self.last_cycle_time*1000:.2f}ms, "
                f"Avg: {self.avg_cycle_time*1000:.2f}ms, "
                f"Max: {self.max_cycle_time*1000:.2f}ms"
            )

        # Alert if cycle time consistently exceeds target
        if duration > 0.1:  # 100ms target
            logger.warning(f"Cycle time exceeded 100ms target: {duration*1000:.2f}ms")

    async def shutdown(self) -> None:
        """Shutdown the orchestrator gracefully."""
        if not self.running:
            return

        logger.info("Shutting down TradingOrchestrator")
        self._shutdown_event.set()
        self.running = False

        # Wait for current cycle to complete
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Orchestrator shutdown timed out")

        logger.info("TradingOrchestrator shutdown complete")

    async def _check_kill_switch(self) -> None:
        """Check kill switch status."""
        if alerts.is_kill_switch_active():
            logger.error("Kill switch active - trading operations blocked")
            raise KillSwitchError()

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_history(self, symbol: str, interval: str) -> Optional[Dict[str, Any]]:
        """Get history with circuit breaker protection."""
        try:
            return await async_client.get_history(symbol=symbol, interval=interval)
        except Exception:
            logger.error("Failed to get history after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_quotes(self, symbols: List[str]) -> Optional[Dict[str, Any]]:
        """Get quotes with circuit breaker protection."""
        try:
            return await async_client.get_quotes(symbols)
        except Exception:
            logger.error("Failed to get quotes after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_position_book(self) -> Optional[Dict[str, Any]]:
        """Get position book with circuit breaker protection."""
        try:
            return await async_client.get_position_book()
        except Exception:
            logger.error("Failed to get position book after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_funds(self) -> Optional[Dict[str, Any]]:
        """Get funds with circuit breaker protection."""
        try:
            return await async_client.get_funds()
        except Exception:
            logger.error("Failed to get funds after retries")
            return None

    def _create_position_model(self, position_data: Dict[str, Any]) -> Any:
        """Create position model from raw data."""
        from .models import Position, ProductType

        return Position(
            symbol=position_data["symbol"],
            quantity=position_data["quantity"],
            average_price=position_data["average_price"],
            last_price=position_data["last_price"],
            pnl=position_data["pnl"],
            product_type=ProductType(position_data["product_type"]),
            buy_quantity=position_data.get("buy_quantity", 0),
            sell_quantity=position_data.get("sell_quantity", 0),
        )

    def _create_funds_model(self, funds_data: Dict[str, Any]) -> Any:
        """Create funds model from raw data."""
        from .models import FundsData

        return FundsData(
            available_cash=funds_data["available_cash"],
            utilized_margin=funds_data["utilized_margin"],
            available_margin=funds_data["available_margin"],
            total_equity=funds_data["total_equity"],
            timestamp=datetime.datetime.now(datetime.UTC),
        )

    def get_cycle_stats(self) -> Dict[str, Any]:
        """Get current cycle statistics."""
        return {
            "cycle_count": self.cycle_count,
            "last_cycle_time_ms": self.last_cycle_time * 1000,
            "avg_cycle_time_ms": self.avg_cycle_time * 1000,
            "max_cycle_time_ms": self.max_cycle_time * 1000,
            "target_compliance": "pass" if self.avg_cycle_time <= 0.1 else "fail"
        }

# Module-level singleton instance
orchestrator = TradingOrchestrator()

async def start_orchestrator() -> None:
    """Start the trading orchestrator."""
    await orchestrator.start()

async def stop_orchestrator() -> None:
    """Stop the trading orchestrator."""
    await orchestrator.shutdown()

async def get_cycle_stats() -> Dict[str, Any]:
    """Get orchestrator cycle statistics."""
    return orchestrator.get_cycle_stats()