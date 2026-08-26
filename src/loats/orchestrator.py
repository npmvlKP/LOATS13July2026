"""Orchestrator Module for LOATS13July2026.

High-performance trading cycle orchestrator that meets the <100ms cycle target.
Coordinates all trading operations with strict latency guarantees.
"""

import asyncio
import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np

from .alerts import alerts
from .config import get_settings
from .database import db
from .loats_logging import get_logger
from .metrics import record_cycle_time, record_cmp_chain_rejection
from .models import HistoricalData, OptionContract, QuoteData, Signal
from .openalgo import KillSwitchError, async_client
from .rules import rules_engine
from .sentiment import sentiment
from .strength import StrengthSource
from .strike_selection import select_strikes
from .ta import technical_analysis
from .trade_decision import trade_decision_engine
from .utils.cache import cache_manager
from .utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER
from .utils.resilience import openalgo_circuit_breaker_retry_async

logger = get_logger(__name__)
settings = None


async def _fetch_cached_vix() -> float | None:
    """
    Fetch India VIX via cached OpenAlgo quote.

    Returns:
        VIX level as float, or None if unavailable

    Uses TTL cache to minimize API calls while keeping data fresh.
    """
    try:
        global settings
        if settings is None:
            settings = get_settings()

        vix_symbol = settings.vix_symbol
        cache_key = f"vix_quote:{vix_symbol}"

        # Check cache first
        cached_vix = await cache_manager.get(cache_key)
        if cached_vix is not None:
            try:
                vix_value = float(cached_vix)
                logger.debug(f"VIX from cache: {vix_value:.2f}")
                return vix_value
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid cached VIX value: {e}")
                # Fall through to fetch fresh

        # Fetch from OpenAlgo
        quotes = await async_client.get_quotes(symbols=[vix_symbol])
        if not quotes or "data" not in quotes:
            logger.warning(f"No VIX data available for {vix_symbol}")
            return None

        vix_data = quotes["data"].get(vix_symbol, {})
        vix_value = vix_data.get("last_price")

        if vix_value is None:
            logger.warning(f"VIX last_price missing for {vix_symbol}")
            return None

        try:
            vix_float = float(vix_value)

            # Cache the value
            await cache_manager.set(
                cache_key, str(vix_float), ttl=settings.vix_cache_ttl_seconds
            )

            logger.debug(f"VIX fetched and cached: {vix_float:.2f}")
            return vix_float

        except (ValueError, TypeError) as e:
            logger.error(f"Invalid VIX value from OpenAlgo: {vix_value}, error: {e}")
            return None

    except Exception as e:
        logger.error(f"VIX fetch failed: {e}")
        return None


async def validate_rss_feed(url: str, timeout: int = 5) -> bool:
    """Validate RSS feed URL with timeout and error handling."""
    try:
        # Basic URL validation
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            logger.warning(f"Invalid RSS feed URL format: {url}")
            return False

        # Check if URL is HTTP/HTTPS
        if parsed.scheme not in ["http", "https"]:
            logger.warning(f"Unsupported RSS feed URL scheme: {parsed.scheme}")
            return False

        # Try to fetch the feed with timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    # Check if content looks like XML/RSS
                    content_type = response.headers.get("content-type", "").lower()
                    if "xml" in content_type or "rss" in content_type:
                        return True
                    # Simple content check for RSS feeds
                    content = response.text.lower()
                    if any(tag in content for tag in ["<rss", "<feed", "<channel"]):
                        return True
                    logger.warning(f"RSS feed URL returned non-RSS content: {url}")
                    return False
                else:
                    logger.warning(
                        f"RSS feed URL returned status {response.status_code}: {url}"
                    )
                    return False
            except httpx.ConnectTimeout:
                logger.warning(f"RSS feed URL connection timeout: {url}")
                return False
            except httpx.ReadTimeout:
                logger.warning(f"RSS feed URL read timeout: {url}")
                return False
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"RSS feed URL HTTP error {e.response.status_code}: {url}"
                )
                return False
            except Exception as e:
                logger.warning(f"RSS feed URL validation error for {url}: {e}")
                return False

    except Exception as e:
        logger.error(f"Unexpected error validating RSS feed {url}: {e}")
        return False


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
        self._cycle_task: asyncio.Task[None] | None = None
        self._last_alert_time = 0.0
        # CMP chain rejection tracking
        self._last_insufficient_signals_warning_time = 0.0
        self._insufficient_signals_count = 0
        self._last_session_state = ""
        self._insufficient_signals_warning_interval = 60.0  # Log every 60 seconds

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
        if hasattr(self, "_cycle_task") and self._cycle_task is not None:
            logger.warning("Orchestrator already running")
            return

        if not self.running:
            await self.initialize()
        logger.info("Starting TradingOrchestrator cycle")
        self._cycle_task = asyncio.create_task(self._run_cycle_loop())
        self._cycle_task.add_done_callback(self._handle_cycle_task_completion)

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
                # Add alert backoff to prevent alert floods
                current_time = datetime.datetime.now(datetime.UTC).timestamp()
                if current_time - self._last_alert_time > 60:  # Max 1 alert per minute
                    await alerts.send_system_alert(f"Trading cycle error: {e}", "error")
                    self._last_alert_time = current_time

            # Calculate and record cycle time
            cycle_duration = (
                datetime.datetime.now(datetime.UTC) - cycle_start
            ).total_seconds()
            self._record_cycle_time(cycle_duration)

            # Enforce 100ms cycle target with adaptive sleep
            target_duration = 0.1  # 100ms
            sleep_time = max(0, target_duration - cycle_duration)
            await asyncio.sleep(sleep_time)

    async def _execute_trading_cycle(self) -> None:
        """Execute a complete trading cycle with parallel execution."""
        cycle_start = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

            # Run TA analysis, sentiment and market data updates in parallel
            # with timeout
            ta_task = asyncio.create_task(self._execute_ta_analysis())
            sentiment_task = asyncio.create_task(self._execute_sentiment_analysis())
            volatility_task = asyncio.create_task(self._execute_volatility_analysis())
            market_data_task = asyncio.create_task(self._execute_market_data_update())

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        ta_task, sentiment_task, volatility_task, market_data_task
                    ),
                    timeout=0.08,
                )
            except TimeoutError:
                logger.warning(
                    "Trading cycle tasks timed out - continuing with partial results"
                )
                for task in [ta_task, sentiment_task, market_data_task]:
                    if not task.done():
                        task.cancel()

            # Execute sequential operations
            await self._execute_risk_management()

            # Execute CMP strategy (only if trading is allowed in current session)
            if rules_engine.is_trading_allowed():
                await self._execute_cmp_strategy()
            else:
                logger.debug(
                    f"CMP strategy skipped - session: {rules_engine.session_state}"
                )

        except Exception as e:
            logger.error(f"Error in trading cycle execution: {e}")
            raise

        finally:
            cycle_duration = (
                datetime.datetime.now(datetime.UTC) - cycle_start
            ).total_seconds()
            record_cycle_time(cycle_duration)
            logger.debug(
                f"Trading cycle {self.cycle_count} completed in "
                f"{cycle_duration * 1000:.2f}ms"
            )

    async def _execute_ta_analysis(self) -> None:
        """Execute technical analysis with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

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
                signal_result = technical_analysis.generate_signal(
                    indicators, current_price
                )

                if signal_result:
                    signal_type, strength = signal_result
                    from .models import SignalType

                    signal = Signal(
                        symbol=symbol,
                        signal_type=SignalType(signal_type),
                        strength=strength,
                        timestamp=datetime.datetime.now(datetime.UTC),
                        indicators={ind.name: ind.value for ind in indicators},
                        confidence=strength,
                        metadata={
                            "scan_type": "ta",
                            "source": StrengthSource.TECHNICAL_ANALYSIS.value,
                        },
                    )
                    await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"TA analysis failed: {e}")
            raise

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.03:  # 30ms budget for TA analysis
                logger.warning(f"TA analysis exceeded budget: {duration * 1000:.2f}ms")

    async def _execute_sentiment_analysis(self) -> None:
        """Execute sentiment analysis with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

            symbol = settings.default_symbol
            rss_feeds = [
                "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "https://www.moneycontrol.com/rss/latestnews.xml",
                "https://www.bloombergquint.com/markets-feed",
            ]

            # Validate RSS feeds and filter out invalid ones
            valid_feeds = []
            for feed_url in rss_feeds:
                if await validate_rss_feed(feed_url):
                    valid_feeds.append(feed_url)
                else:
                    logger.warning(f"Skipping invalid RSS feed: {feed_url}")

            if not valid_feeds:
                logger.warning("No valid RSS feeds available for sentiment analysis")
                return

            # Call the async sentiment analysis function directly with validated feeds
            result = await sentiment.analyze_symbol_sentiment(symbol, valid_feeds)

            # Generate sentiment signal
            if result.sentiment_score > 0:
                signal_type = "BUY"
            elif result.sentiment_score < 0:
                signal_type = "SELL"
            else:
                signal_type = "NEUTRAL"

            if abs(result.sentiment_score) >= settings.sentiment_threshold:
                from .models import SignalType

                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType(signal_type),
                    strength=abs(result.sentiment_score),
                    timestamp=datetime.datetime.now(datetime.UTC),
                    indicators={"sentiment_score": result.sentiment_score},
                    confidence=abs(result.sentiment_score),
                    metadata={
                        "scan_type": "sentiment",
                        "source": StrengthSource.SENTIMENT.value,
                        "news_count": result.news_count,
                    },
                )
                await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            raise

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.04:  # 40ms budget for sentiment analysis
                logger.warning(
                    f"Sentiment analysis exceeded budget: {duration * 1000:.2f}ms"
                )

    async def _execute_volatility_analysis(self) -> None:
        """Execute volatility analysis — 4th signal producer for diversity gate.

        Uses existing TA machinery (ATR, VWAP) and adds Hurst exponent
        regime detection. Runs inside the 80ms parallel window.
        """
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            global settings
            if settings is None:
                settings = get_settings()

            symbol = settings.default_symbol
            timeframe = settings.timeframe

            historical_data_raw = await async_client.get_historical_data(
                symbol=symbol,
                exchange=settings.exchange,
                interval=timeframe,
                limit=100,
            )

            if not historical_data_raw or not historical_data_raw.get("data"):
                logger.warning("No historical data for volatility analysis")
                return

            historical_data_objs = [
                HistoricalData(
                    timestamp=datetime.datetime.fromisoformat(item["timestamp"]),
                    open=item["open"],
                    high=item["high"],
                    low=item["low"],
                    close=item["close"],
                    volume=item["volume"],
                    interval=timeframe,
                )
                for item in historical_data_raw["data"]
            ]

            if len(historical_data_objs) < 50:
                logger.warning(
                    f"Insufficient bars for volatility: {len(historical_data_objs)}"
                )
                return

            import pandas as pd
            from .ta import calculate_atr, calculate_vwap
            from .models import SignalType

            df = pd.DataFrame(
                {
                    "timestamp": [h.timestamp for h in historical_data_objs],
                    "open": [h.open for h in historical_data_objs],
                    "high": [h.high for h in historical_data_objs],
                    "low": [h.low for h in historical_data_objs],
                    "close": [h.close for h in historical_data_objs],
                    "volume": [h.volume for h in historical_data_objs],
                }
            )

            atr_series = calculate_atr(df, period=14)
            current_atr = atr_series.iloc[-1] if not pd.isna(atr_series.iloc[-1]) else 0

            current_price = df["close"].iloc[-1]
            atr_pct = (current_atr / current_price * 100) if current_price > 0 else 0

            vwap_series = calculate_vwap(df)
            current_vwap = (
                vwap_series.iloc[-1]
                if not pd.isna(vwap_series.iloc[-1])
                else current_price
            )

            hurst_exponent = self._calculate_hurst_exponent(df["close"].values)
            regime = (
                "trending"
                if hurst_exponent is not None and hurst_exponent > 0.5
                else "mean_reverting"
                if hurst_exponent is not None
                else "unknown"
            )

            vol_score = min(atr_pct / 2.0, 1.0)

            signal_type = "NEUTRAL"
            signal_strength = 0.5

            if regime == "trending" and vol_score > 0.6:
                signal_type = "BUY" if current_price > current_vwap else "SELL"
                signal_strength = 0.7 + vol_score * 0.2
            elif regime == "mean_reverting" and vol_score > 0.5:
                signal_type = "SELL" if current_price > current_vwap else "BUY"
                signal_strength = 0.65 + vol_score * 0.15
            elif vol_score < 0.3:
                signal_type = "NEUTRAL"
                signal_strength = 0.4

            signal = Signal(
                symbol=symbol,
                signal_type=SignalType(signal_type),
                strength=signal_strength,
                timestamp=datetime.datetime.now(datetime.UTC),
                indicators={
                    "atr": float(current_atr),
                    "atr_pct": float(atr_pct),
                    "vwap": float(current_vwap),
                    "hurst_exponent": (
                        float(hurst_exponent) if hurst_exponent is not None else 0.5
                    ),
                },
                confidence=signal_strength,
                metadata={
                    "scan_type": "volatility",
                    "source": StrengthSource.VOLATILITY.value,
                    "regime": regime,
                    "atr_pct": float(atr_pct),
                    "hurst": (
                        float(hurst_exponent) if hurst_exponent is not None else 0.5
                    ),
                },
            )
            await db.async_create_signal(signal)

        except Exception as e:
            logger.error(f"Volatility analysis failed: {e}")
            raise
        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.03:
                logger.warning(
                    f"Volatility analysis exceeded budget: {duration * 1000:.2f}ms"
                )

    def _calculate_hurst_exponent(
        self,
        close_prices: np.ndarray,
    ) -> float | None:
        """Hurst exponent via R/S analysis.

        H < 0.5 = mean-reverting, H > 0.5 = trending.
        """
        try:
            from scipy import stats as sp_stats

            if len(close_prices) < 50:
                return None

            returns = np.diff(np.log(close_prices))
            if len(returns) < 30:
                return None

            window_sizes = [10, 20, 30, 40]
            rs_values: list[tuple[int, float]] = []

            for w in window_sizes:
                if w >= len(returns):
                    continue
                n_sub = len(returns) // w
                if n_sub < 1:
                    continue
                rs_sub: list[float] = []
                for i in range(n_sub):
                    subset = returns[i * w : (i + 1) * w]
                    if len(subset) < 2:
                        continue
                    mean_s = np.mean(subset)
                    devs = np.cumsum(subset - mean_s)
                    r = np.max(devs) - np.min(devs)
                    s = np.std(subset, ddof=1)
                    if s > 0:
                        rs_sub.append(float(r / s))
                if rs_sub:
                    rs_values.append((w, float(np.mean(rs_sub))))

            if len(rs_values) < 2:
                return None

            log_n = np.log([x[0] for x in rs_values])
            log_rs = np.log([x[1] for x in rs_values])
            slope, _, _, _, _ = sp_stats.linregress(log_n, log_rs)
            return float(slope)

        except Exception as e:
            logger.warning(f"Failed to calculate Hurst exponent: {e}")
            return None

    async def _execute_market_data_update(self) -> None:
        """Update market data with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

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

            # Fetch and update VIX level (within 80ms window)
            vix_level = await _fetch_cached_vix()
            rules_engine.set_vix_level(vix_level)

        except Exception as e:
            logger.error(f"Market data update failed: {e}")
            raise

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.02:  # 20ms budget for market data update
                logger.warning(
                    f"Market data update exceeded budget: {duration * 1000:.2f}ms"
                )

    async def _execute_risk_management(self) -> None:
        """Execute risk management checks with performance monitoring."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

            # Check circuit breaker status
            cb_status = OPENALGO_CIRCUIT_BREAKER.get_status()
            if cb_status["state"] == "open":
                logger.warning("Circuit breaker open - risk management checks limited")
                return

            # Check position limits
            positions = await asyncio.to_thread(
                db.get_position, symbol=settings.default_symbol
            )
            if positions and positions.quantity > settings.max_position_size:
                logger.warning(f"Position limit exceeded: {positions.quantity}")
                await alerts.send_alert(
                    f"Position limit exceeded: {positions.quantity}", "position_limit"
                )

            # Check margin utilization with zero division guard
            funds = await asyncio.to_thread(db.get_latest_funds)
            if funds:
                available_margin = funds.available_margin
                if available_margin > 0:
                    margin_ratio = funds.utilized_margin / available_margin
                    if margin_ratio > settings.max_margin_utilization:
                        logger.warning(f"Margin utilization high: {margin_ratio:.2%}")
                        await alerts.send_alert(
                            f"High margin utilization: {margin_ratio:.2%}",
                            "margin_utilization",
                        )
                else:
                    logger.warning(
                        "Available margin is zero - cannot calculate utilization ratio"
                    )

        except Exception as e:
            logger.error(f"Risk management failed: {e}")
            raise

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.01:  # 10ms budget for risk management
                logger.warning(
                    f"Risk management exceeded budget: {duration * 1000:.2f}ms"
                )

    async def _execute_cmp_strategy(self) -> None:
        """Execute CMP strategy with TradeDecision creation and Analyzer routing."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            # Lazy load settings to avoid import-time failures
            global settings
            if settings is None:
                settings = get_settings()

            symbol = settings.default_symbol

            # Get all available signals for CMP strategy (≥3 sources required)
            all_signals = await db.async_get_latest_signals(symbol, limit=10)

            # Filter out only recent signals (last 5 minutes)
            cutoff_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
                minutes=5
            )
            recent_signals = [s for s in all_signals if s.timestamp >= cutoff_time]

            if len(recent_signals) < 3:
                # Track CMP chain rejection
                record_cmp_chain_rejection("insufficient_signals")

                # Increment counter
                self._insufficient_signals_count += 1

                # Check for session state change
                current_session_state = rules_engine.session_state.value
                session_changed = self._last_session_state != current_session_state
                if session_changed:
                    self._last_session_state = current_session_state
                    # Reset counter on session state change
                    self._insufficient_signals_count = 1

                # Periodic warning log to prevent noise (every 60 seconds)
                current_time = datetime.datetime.now(datetime.UTC).timestamp()
                if (
                    current_time - self._last_insufficient_signals_warning_time
                    >= self._insufficient_signals_warning_interval
                    or session_changed
                ):
                    logger.warning(
                        f"Insufficient signals for CMP strategy: "
                        f"{len(recent_signals)} signals "
                        f"(rejected {self._insufficient_signals_count} "
                        f"times since last session change)"
                    )
                    self._last_insufficient_signals_warning_time = current_time
                return

            # Get historical data for gating rules
            history_data = await self._safe_get_history(symbol, "5min")
            if not history_data:
                logger.warning("No historical data available for CMP strategy")
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
                        interval="5min",
                    )
                )

            # Get current price and funds
            quotes = await self._safe_get_quotes([symbol])
            if not quotes:
                logger.warning("No quote data available for CMP strategy")
                return

            quote_data = quotes.get("data", {}).get(symbol, {})
            current_price = quote_data.get("last_price", 0)

            funds_data = await self._safe_get_funds()
            if not funds_data or not funds_data.get("data"):
                logger.warning("No funds data available for CMP strategy")
                return

            funds = self._create_funds_model(funds_data["data"])

            # Get current positions
            current_positions = await asyncio.to_thread(db.get_position, symbol=symbol)

            # Convert Position to list of Trades for TradeDecisionEngine
            current_trades = []
            if current_positions:
                # Create a Trade object from the Position
                from .models import Trade, TransactionType

                transaction_type = (
                    TransactionType.BUY
                    if current_positions.quantity > 0
                    else TransactionType.SELL
                )

                trade = Trade(
                    trade_id=f"temp_{symbol}_trade",
                    symbol=symbol,
                    quantity=current_positions.quantity,
                    entry_price=current_positions.average_price,
                    transaction_type=transaction_type,
                    product_type=current_positions.product_type,
                    status="OPEN",
                    entry_time=datetime.datetime.now(datetime.UTC),
                    metadata={"source": "position_conversion"},
                )
                current_trades.append(trade)

            # Create TradeDecision using CMP strategy
            (
                decision,
                creation_result,
            ) = await trade_decision_engine.create_trade_decision(
                signals=recent_signals,
                historical_data=historical_data_objs,
                current_price=current_price,
                funds=funds,
                current_positions=current_trades,
            )

            if decision is None:
                logger.info(
                    f"CMP strategy decision not created: {creation_result['reason']}"
                )
                return

            # Route TradeDecision to Analyzer
            routing_result = await trade_decision_engine.route_to_analyzer(decision)

            if routing_result["status"] == "success":
                logger.info(
                    f"Successfully created and routed CMP TradeDecision: "
                    f"{decision.decision_id}"
                )
                logger.debug(f"TradeDecision details: {decision.to_analyzer_payload()}")

                # Store the decision in database
                await db.async_create_trade_decision(decision)
            else:
                logger.warning(f"Failed to route CMP TradeDecision: {routing_result}")

        except Exception as e:
            logger.error(f"CMP strategy execution failed: {e}")
            raise

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.05:  # 50ms budget for CMP strategy
                logger.warning(f"CMP strategy exceeded budget: {duration * 1000:.2f}ms")

    async def _execute_strike_selection(
        self, option_chain: list[OptionContract]
    ) -> list[float]:
        """Execute high-performance strike selection with <5ms guarantee."""
        start_time = datetime.datetime.now(datetime.UTC)

        try:
            if not option_chain:
                return []

            # Get current price (use first contract's underlying as proxy)
            current_price = (
                option_chain[0].underlying_price
                if hasattr(option_chain[0], "underlying_price")
                else 0
            )
            for opt in option_chain:
                if hasattr(opt, "underlying_price") and opt.underlying_price > 0:
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
                        max_strikes=5,
                    ),
                    timeout=0.004,  # 4ms timeout for strike selection
                )
                return selected_strikes
            except TimeoutError:
                logger.warning("Strike selection timed out - using fallback")
                # Simple fallback: return middle strikes
                strikes = sorted({opt.strike_price for opt in option_chain})
                mid = len(strikes) // 2
                return strikes[max(0, mid - 2) : min(len(strikes), mid + 3)]

        except Exception as e:
            logger.error(f"Strike selection failed: {e}")
            return []

        finally:
            duration = (
                datetime.datetime.now(datetime.UTC) - start_time
            ).total_seconds()
            if duration > 0.005:  # 5ms target
                logger.warning(
                    f"Strike selection exceeded 5ms target: {duration * 1000:.2f}ms"
                )
            else:
                logger.debug(f"Strike selection completed in {duration * 1000:.2f}ms")

    def _record_cycle_time(self, duration: float) -> None:
        """Record and track cycle time statistics."""
        self.last_cycle_time = duration
        self.total_cycle_time += duration
        self.cycle_count += 1
        self.avg_cycle_time = self.total_cycle_time / self.cycle_count
        self.max_cycle_time = max(self.max_cycle_time, duration)

        # Log cycle time statistics periodically
        if self.cycle_count % 100 == 0:
            logger.info(
                f"Cycle stats - Count: {self.cycle_count}, "
                f"Last: {self.last_cycle_time * 1000:.2f}ms, "
                f"Avg: {self.avg_cycle_time * 1000:.2f}ms, "
                f"Max: {self.max_cycle_time * 1000:.2f}ms"
            )

        # Alert if cycle time consistently exceeds target
        if duration > 0.1:  # 100ms target
            logger.warning(f"Cycle time exceeded 100ms target: {duration * 1000:.2f}ms")

    async def shutdown(self) -> None:
        """Shutdown the orchestrator gracefully."""
        if not self.running:
            return

        logger.info("Shutting down TradingOrchestrator")
        self._shutdown_event.set()
        self.running = False

        # Wait for the cycle task to complete with timeout
        if hasattr(self, "_cycle_task") and self._cycle_task:
            try:
                await asyncio.wait_for(self._cycle_task, timeout=5.0)
            except TimeoutError:
                logger.warning(
                    "Orchestrator shutdown timed out - cycle task still running"
                )
                # Cancel the task if it's still running
                self._cycle_task.cancel()
            except asyncio.CancelledError:
                pass

        logger.info("TradingOrchestrator shutdown complete")

    async def _check_kill_switch(self) -> None:
        """Check kill switch status."""
        if alerts.is_kill_switch_active():
            logger.error("Kill switch active - trading operations blocked")
            raise KillSwitchError()

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_history(
        self, symbol: str, interval: str
    ) -> dict[str, Any] | None:
        """Get history with circuit breaker protection."""
        try:
            return await async_client.get_history(symbol=symbol, interval=interval)
        except Exception:
            logger.error("Failed to get history after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_quotes(self, symbols: list[str]) -> dict[str, Any] | None:
        """Get quotes with circuit breaker protection."""
        try:
            return await async_client.get_quotes(symbols)
        except Exception:
            logger.error("Failed to get quotes after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_position_book(self) -> dict[str, Any] | None:
        """Get position book with circuit breaker protection."""
        try:
            return await async_client.get_position_book()
        except Exception:
            logger.error("Failed to get position book after retries")
            return None

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_funds(self) -> dict[str, Any] | None:
        """Get funds with circuit breaker protection."""
        try:
            return await async_client.get_funds()
        except Exception:
            logger.error("Failed to get funds after retries")
            return None

    def _create_position_model(self, position_data: dict[str, Any]) -> Any:
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

    def _create_funds_model(self, funds_data: dict[str, Any]) -> Any:
        """Create funds model from raw data."""
        from .models import FundsData

        available_margin = funds_data.get("available_margin", 0)
        return FundsData(
            available_cash=funds_data["available_cash"],
            utilized_margin=funds_data["utilized_margin"],
            available_margin=available_margin,
            total_equity=funds_data["total_equity"],
            timestamp=datetime.datetime.now(datetime.UTC),
        )

    def get_cycle_stats(self) -> dict[str, Any]:
        """Get current cycle statistics."""
        return {
            "cycle_count": self.cycle_count,
            "last_cycle_time_ms": self.last_cycle_time * 1000,
            "avg_cycle_time_ms": self.avg_cycle_time * 1000,
            "max_cycle_time_ms": self.max_cycle_time * 1000,
            "target_compliance": "pass" if self.avg_cycle_time <= 0.1 else "fail",
        }

    def _handle_cycle_task_completion(self, task: asyncio.Task[None]) -> None:
        """Handle completion of the cycle task."""
        try:
            # Check if task is done and get result (this will re-raise any exception)
            if task.done():
                task.result()
        except Exception as e:
            logger.error(f"Cycle task completed with exception: {e}")
            self.running = False
            # Re-raise the exception to ensure it's properly handled
            raise


# Module-level singleton instance
orchestrator = TradingOrchestrator()


async def start_orchestrator() -> None:
    """Start the trading orchestrator."""
    await orchestrator.start()


async def stop_orchestrator() -> None:
    """Stop the trading orchestrator."""
    await orchestrator.shutdown()


async def get_cycle_stats() -> dict[str, Any]:
    """Get orchestrator cycle statistics."""
    return orchestrator.get_cycle_stats()
