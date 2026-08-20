"""
CMP Strategy Rules Engine for LOATS13July2026.

Implements the core gating rules for the CMP trading strategy:
- IV-rank > 40 / ADX < 25 / VIX > 15 for SELL signals
- Inverse conditions for BUY signals
- Additional risk filters and circuit breakers
"""

import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from .config import get_settings
from .loats_logging import get_logger
from .models import HistoricalData, Signal, SignalType, Trade

logger = get_logger(__name__)
settings = get_settings()


class RuleType(StrEnum):
    """Rule type enumeration."""

    GATING = "GATING"
    RISK = "RISK"
    POSITION = "POSITION"
    SESSION = "SESSION"


class TradingSession(StrEnum):
    """Trading session enumeration."""

    PRE_OPEN = "PRE_OPEN"
    REGULAR = "REGULAR"
    POST_CLOSE = "POST_CLOSE"
    AFTER_HOURS = "AFTER_HOURS"


class CMPRulesEngine:
    """CMP Strategy Rules Engine with comprehensive gating logic."""

    def __init__(self) -> None:
        """Initialize CMPRulesEngine."""
        self.modification_counter = 0
        self.session_state = TradingSession.PRE_OPEN
        self.last_session_update = datetime.datetime.now(datetime.UTC)
        self._vix_level: float | None = None

    def get_current_session(
        self, current_time: datetime.datetime | None = None
    ) -> TradingSession:
        """
        Determine current trading session based on Indian market hours.

        Indian Market Hours:
        - PRE_OPEN: 9:00 - 9:15 AM IST
        - REGULAR: 9:15 AM - 3:30 PM IST
        - POST_CLOSE: 3:30 - 4:00 PM IST
        - AFTER_HOURS: 4:00 PM - 9:00 AM IST
        """
        if current_time is None:
            current_time = datetime.datetime.now(datetime.UTC)

        # Convert to IST (UTC+5:30)
        ist_time = current_time + datetime.timedelta(hours=5, minutes=30)

        # Determine session
        if ist_time.hour == 9 and ist_time.minute < 15:
            return TradingSession.PRE_OPEN
        elif (ist_time.hour == 9 and ist_time.minute >= 15) or (
            ist_time.hour >= 10 and ist_time.hour < 15
        ):
            return TradingSession.REGULAR
        elif ist_time.hour == 15 and ist_time.minute < 30:
            return TradingSession.REGULAR
        elif ist_time.hour == 15 and ist_time.minute >= 30:
            return TradingSession.POST_CLOSE
        elif ist_time.hour > 15 or ist_time.hour < 9:
            return TradingSession.AFTER_HOURS
        else:
            return TradingSession.AFTER_HOURS

    def update_session_state(self) -> None:
        """Update current trading session state."""
        current_session = self.get_current_session()
        if current_session != self.session_state:
            logger.info(
                f"Session transition: {self.session_state} -> {current_session}"
            )
            self.session_state = current_session
            self.last_session_update = datetime.datetime.now(datetime.UTC)

    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed in current session."""
        self.update_session_state()
        return self.session_state == TradingSession.REGULAR

    def calculate_iv_rank(
        self, historical_data: list[HistoricalData], window: int = 30
    ) -> float:
        """
        Calculate IV Rank (Implied Volatility Rank).

        IV Rank = (Current IV - Min IV) / (Max IV - Min IV)

        Rolling historical volatility (5-bar std of returns, annualized)
        serves as the IV proxy. The current HV is ranked against the
        min/max HV observed within the same window, yielding a value on
        a consistent 0-100 scale.
        """
        if len(historical_data) < window:
            return 50.0  # Default neutral value (0-100 scale)

        # Extract closing prices and calculate returns
        closes = pd.Series(
            [h.close for h in historical_data[-window:]], dtype="float64"
        )
        returns = closes.pct_change()

        # Rolling 5-bar historical volatility (annualized) as IV proxy
        hv = returns.rolling(5).std() * float(np.sqrt(252))

        iv_current = hv.iloc[-1]
        iv_min = hv.min()
        iv_max = hv.max()

        if pd.isna(iv_current) or iv_max == iv_min:
            return 50.0  # Neutral when the window has no measurable spread

        iv_rank = (iv_current - iv_min) / (iv_max - iv_min)
        return float(np.clip(iv_rank * 100.0, 0.0, 100.0))

    def calculate_adx(
        self, historical_data: list[HistoricalData], period: int = 14
    ) -> float:
        """
        Calculate Average Directional Index (ADX).

        ADX < 25 indicates weak trend, ADX > 25 indicates strong trend
        """
        if len(historical_data) < period:
            return 25.0  # Default neutral value

        # Convert to DataFrame for calculation
        df = pd.DataFrame(
            {
                "high": [h.high for h in historical_data],
                "low": [h.low for h in historical_data],
                "close": [h.close for h in historical_data],
            }
        )

        # Calculate +DM, -DM, and TR
        df["+DM"] = df["high"].diff()
        df["-DM"] = -df["low"].diff()
        df.loc[df["+DM"] < 0, "+DM"] = 0
        df.loc[df["-DM"] < 0, "-DM"] = 0

        df["TR"] = pd.concat(
            [
                df["high"] - df["low"],
                abs(df["high"] - df["close"].shift()),
                abs(df["low"] - df["close"].shift()),
            ],
            axis=1,
        ).max(axis=1)

        # Calculate smoothed values
        df["+DM_smooth"] = df["+DM"].rolling(window=period).mean()
        df["-DM_smooth"] = df["-DM"].rolling(window=period).mean()
        df["TR_smooth"] = df["TR"].rolling(window=period).mean()

        # Calculate +DI and -DI
        df["+DI"] = 100 * (df["+DM_smooth"] / df["TR_smooth"])
        df["-DI"] = 100 * (df["-DM_smooth"] / df["TR_smooth"])

        # Calculate DX and ADX
        df["DX"] = 100 * abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])
        adx = df["DX"].rolling(window=period).mean().iloc[-1]

        return float(adx) if not pd.isna(adx) else 25.0

    def get_vix_level(self) -> float:
        """
        Get current VIX level.

        Returns the most recent VIX value supplied via
        :meth:`set_vix_level` by market data feeds; falls back to a
        neutral default when no feed has been attached yet.
        """
        vix = self._vix_level
        return float(vix) if vix is not None else 18.5  # Neutral default

    def set_vix_level(self, level: float) -> None:
        """Update the latest VIX level from market data feeds."""
        if level <= 0:
            raise ValueError("VIX level must be positive")
        self._vix_level = float(level)

    def apply_gating_rules(
        self,
        signal: Signal,
        historical_data: list[HistoricalData],
        current_price: float,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Apply CMP gating rules to determine if signal should be executed.

        Rules:
        - IV-rank > 40 / ADX < 25 / VIX > 15 for SELL
        - IV-rank < 60 / ADX > 25 / VIX < 15 for BUY
        - Session must be REGULAR
        - Signal strength must be sufficient
        """
        if not self.is_trading_allowed():
            return False, {
                "reason": "trading_not_allowed",
                "session": str(self.session_state),
            }

        # Calculate indicators
        iv_rank = self.calculate_iv_rank(historical_data)
        adx = self.calculate_adx(historical_data)
        vix = self.get_vix_level()

        # Apply gating rules based on signal type
        if signal.signal_type == SignalType.SELL:
            # SELL rules: IV-rank > 40 / ADX < 25 / VIX > 15
            iv_pass = iv_rank > 40
            adx_pass = adx < 25
            vix_pass = vix > 15

            if iv_pass and adx_pass and vix_pass:
                return True, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": vix,
                    "reason": "gating_passed",
                }
            else:
                return False, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": vix,
                    "reason": "gating_failed",
                    "iv_pass": iv_pass,
                    "adx_pass": adx_pass,
                    "vix_pass": vix_pass,
                }

        elif signal.signal_type == SignalType.BUY:
            # BUY rules: IV-rank < 60 / ADX > 25 / VIX < 15
            iv_pass = iv_rank < 60
            adx_pass = adx > 25
            vix_pass = vix < 15

            if iv_pass and adx_pass and vix_pass:
                return True, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": vix,
                    "reason": "gating_passed",
                }
            else:
                return False, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": vix,
                    "reason": "gating_failed",
                    "iv_pass": iv_pass,
                    "adx_pass": adx_pass,
                    "vix_pass": vix_pass,
                }

        else:
            # NEUTRAL or HOLD signals pass through
            return True, {
                "iv_rank": iv_rank,
                "adx": adx,
                "vix": vix,
                "reason": "neutral_signal",
            }

    def check_position_limits(
        self, symbol: str, current_positions: list[Trade]
    ) -> tuple[bool, dict[str, Any]]:
        """
        Check position limits according to CMP Rule 11.

        Limits:
        - 5 lots for NIFTY
        - 3 lots for BANKNIFTY
        - 1000 for other symbols (existing limit)
        """
        symbol = symbol.upper()
        current_quantity = sum(
            t.quantity for t in current_positions if t.symbol == symbol
        )

        if symbol == "NIFTY":
            max_allowed = 5 * settings.nifty_lot_size  # 5 lots * 25 = 125
        elif symbol == "BANKNIFTY":
            max_allowed = 3 * settings.nifty_lot_size  # 3 lots * 25 = 75
        else:
            max_allowed = settings.max_position_per_symbol

        if current_quantity >= max_allowed:
            return False, {
                "current_quantity": current_quantity,
                "max_allowed": max_allowed,
                "reason": "position_limit_exceeded",
            }

        return True, {
            "current_quantity": current_quantity,
            "max_allowed": max_allowed,
            "reason": "position_limit_ok",
        }

    def check_circuit_breakers(
        self, symbol: str, recent_trades: list[Trade]
    ) -> tuple[bool, dict[str, Any]]:
        """
        Check per-source circuit breakers.

        Circuit breakers trigger if:
        - 3 consecutive losing trades from same source
        - 5 losing trades in last 10 from same source
        """
        if len(recent_trades) < 3:
            return True, {"reason": "insufficient_trade_history"}

        # Group trades by source
        source_trades = {}
        for trade in recent_trades:
            source = trade.metadata.get("source", "unknown")
            if source not in source_trades:
                source_trades[source] = []
            source_trades[source].append(trade)

        # Check each source
        for source, trades in source_trades.items():
            if len(trades) < 3:
                continue

            # Check for 3 consecutive losing trades
            consecutive_losses = 0
            for trade in reversed(trades[-10:]):  # Check last 10 trades
                if trade.pnl is not None and trade.pnl < 0:
                    consecutive_losses += 1
                    if consecutive_losses >= 3:
                        return False, {
                            "source": source,
                            "reason": "consecutive_losses_circuit_breaker",
                            "consecutive_losses": consecutive_losses,
                        }
                else:
                    consecutive_losses = 0

            # Check for 5 losing trades in last 10
            losing_trades = sum(
                1 for t in trades[-10:] if t.pnl is not None and t.pnl < 0
            )
            if losing_trades >= 5:
                return False, {
                    "source": source,
                    "reason": "loss_ratio_circuit_breaker",
                    "losing_trades": losing_trades,
                    "total_trades": len(trades[-10:]),
                }

        return True, {"reason": "circuit_breakers_ok"}

    def increment_modification_counter(self) -> int:
        """Increment rule 7 modification counter."""
        self.modification_counter += 1
        return self.modification_counter

    def reset_modification_counter(self) -> None:
        """Reset rule 7 modification counter."""
        self.modification_counter = 0

    def get_modification_count(self) -> int:
        """Get current modification counter value."""
        return self.modification_counter


# Module-level singleton instance
rules_engine = CMPRulesEngine()

__all__ = ["CMPRulesEngine", "RuleType", "TradingSession", "rules_engine"]
