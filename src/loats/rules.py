"""
CMP Strategy Rules Engine for LOATS13July2026.

Implements the core gating rules for the CMP trading strategy:
- IV-rank > 40 / ADX < 25 / VIX > 15 for SELL signals
- IV-rank < 30 / ADX > 25 / VIX < 15 for BUY signals
- Additional risk filters and circuit breakers

F9-C-01 note: iv_rank is the rank of the option-chain ATM implied
volatility in its own 252-day range when chain IVs are available; the
HV fallback is a units-consistent percentile of the current bar's
absolute return (never the legacy annualized-over-daily saturation).
Insufficient history fails both directions closed (F9-M-04).
"""

import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from .lazy_settings import LazySettings
from .loats_logging import get_logger
from .models import HistoricalData, Signal, SignalType, Trade

logger = get_logger(__name__)

# Lazy settings binding (TODO-18 / HC-21).
# Behavioral contract: importing this module builds NO Settings
# instance -- first attribute access proxies through get_settings(),
# so bare-env imports (no OPENALGO_API_KEY) stay clean.
settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()


class Rule7ModificationLimitError(RuntimeError):
    """
    CMP Rule 7 per-order modification ceiling exceeded (F8-H-02).

    Raised at the ``modify_order`` boundary when ``order_id`` has already
    consumed its ``max_modifications`` budget (persisted in SQLite).
    """


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
    CLOSED = "CLOSED"


class CMPRulesEngine:
    """CMP Strategy Rules Engine with comprehensive gating logic."""

    def __init__(self) -> None:
        """Initialize CMPRulesEngine."""
        self.modification_counter = 0
        self.session_state = TradingSession.PRE_OPEN
        self.last_session_update = datetime.datetime.now(datetime.UTC)

        # VIX state management
        self._vix_level: float | None = None  # None = unknown/failed
        self._vix_timestamp: datetime.datetime | None = None  # Last update time
        self._vix_initialized = False  # Whether VIX has been set at least once

        # F9-C-01: persisted per-symbol option-chain ATM IV series (CMP
        # true IV-rank input). Keyed by as_of_date (ISO string) so the
        # in-memory series has the same one-row-per-trading-day
        # semantics as the iv_history table -- intraday cycles REFRESH
        # today's entry instead of consuming window slots (a flat
        # observation deque would evict a full year of history within
        # ~3.4 trading days at a 5-minute cycle). Bounded to 252 days
        # (1 trading year).
        self._chain_iv_history: dict[str, float] = {}

    def _normalize_chain_iv(self, atm_iv: float) -> float | None:
        """Validate/normalize one ATM IV observation (shared boundary guard).

        Rejects non-finite and non-positive values -- an inf that
        reached persistence (malformed broker payload) and got
        warm-started unvalidated would pin rank to a degenerate constant
        forever; normalizes fraction-scale IVs (0.13 -> 13.0).
        """
        value = float(atm_iv)
        if not np.isfinite(value) or value <= 0:
            logger.warning(f"Ignoring invalid chain ATM IV: {atm_iv!r}")
            return None
        if value <= 1.5:
            value *= 100.0
        return value

    def set_chain_iv_history(
        self, atm_iv: float, as_of_date: str | None = None
    ) -> None:
        """Record one option-chain ATM IV observation (F9-C-01).

        Called by the options-flow producer once per cycle with the ATM
        IV parsed from the real broker chain. IVs in raw fraction (0.12
        == 12%) and percent points (12.0) both accepted: values <= 1.5
        are normalized x100 so a mixed-unit series cannot fold rank into
        two clusters.

        Upsert-by-day semantics: with ``as_of_date`` (the producer
        passes the snapshot date it also persists under) that day's
        entry is refreshed in place; undated feeds refresh the newest
        entry so a year of history is never evicted by intraday
        duplicates. Bounded to the latest 252 days.
        """
        value = self._normalize_chain_iv(atm_iv)
        if value is None:
            return
        if as_of_date is not None:
            self._chain_iv_history[str(as_of_date)] = value
        elif self._chain_iv_history:
            newest = next(reversed(self._chain_iv_history))
            self._chain_iv_history[newest] = value
        else:
            self._chain_iv_history["undated"] = value
        while len(self._chain_iv_history) > 252:
            oldest = next(iter(self._chain_iv_history))
            del self._chain_iv_history[oldest]

    def load_chain_iv_history(self, series: list[tuple[str, float]]) -> None:
        """Warm-start the IV series from persisted storage (F9-C-01).

        Called once at orchestrator initialize() with the 252-day
        iv_history rows (as_of_date, atm_iv). Every row passes the same
        boundary validation as live feeds -- a poisoned persisted value
        (e.g. inf from a malformed broker payload) is skipped with a
        warning instead of pinning rank to a degenerate constant after
        every restart.
        """
        self._chain_iv_history.clear()
        for key, value in series:
            normalized = self._normalize_chain_iv(value)
            if normalized is None:
                continue
            self._chain_iv_history[str(key)] = normalized

    def _iv_series_active(self) -> bool:
        """True when >= 2 distinct day-entries make an IV-series rank possible."""
        return len(self._chain_iv_history) >= 2

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
        - CLOSED: Saturdays and Sundays (all day, IST) -- NSE equity
          trading days are Monday-Friday; the weekday check runs on the
          IST datetime so a UTC-weekend instant already in an IST weekday
          resolves through that weekday's buckets.
        """
        if current_time is None:
            current_time = datetime.datetime.now(datetime.UTC)

        # Convert to IST (UTC+5:30)
        ist_time = current_time + datetime.timedelta(hours=5, minutes=30)

        # Weekends are CLOSED regardless of the intraday bucket. The
        # bucket table below is weekday-blind: without this guard a
        # weekend 11:00 IST returned REGULAR and the full CMP decision
        # funnel ran on non-trading days (observed live 2026-09-12, a
        # Saturday: 500+ signal-batch REJECT audit rows and thousands of
        # weekend cycles in the supervised P5 run).
        if ist_time.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return TradingSession.CLOSED

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

    def is_trading_allowed_at(self, current_time: datetime.datetime) -> bool:
        """Session gate evaluated at an explicit instant.

        Same semantics as :meth:`is_trading_allowed` (REGULAR only),
        resolved for *current_time* instead of "now" -- used by tests and
        backtests that must not depend on the wall clock.
        """
        return self.get_current_session(current_time) == TradingSession.REGULAR

    def calculate_iv_rank(
        self, historical_data: list[HistoricalData], window: int = 30
    ) -> float:
        """
        Calculate IV Rank (Implied Volatility Rank), CMP-conformant (Section 4).

        Rank = (current - min) / (max - min) x 100 over the instrument's
        volatility series.

        Units contract (F9-C-01 root-cause correction): the legacy body
        divided an ANNUALIZED stdev by the DAILY min/max return spread
        and clipped, saturating every result to 100.0 (527/527 live
        gating rejects) and leaving the CMP BUY gate (rank < 30)
        unreachable. The corrected computation is units-consistent:

        1. Preferred source -- option-chain ATM IV series (the CMP
           "rank of implied volatility in its own historical IV range"):
           rank = (current ATM IV - min series) / (max - min) x 100 over
           the persisted, day-keyed series bounded to 252 days (one
           trading year). Requires >= 2 distinct day-entries.
        2. Fallback -- HV percentile: percentile rank of the CURRENT
           bar's absolute return within the same window's absolute
           returns (daily vs daily). Reported via ``iv_source`` in the
           gating payload so the rank's provenance is auditable.
        3. Insufficient history (< window bars AND no IV series) is
           LOUD: returns float("-inf") -- the gating layer fails BOTH
           directions closed instead of the legacy silent 0.5, which
           passed the BUY gate on no data (F9-M-04).
        """
        # Preferred input: persisted option-chain ATM IV (true IV rank).
        iv_series = self._chain_iv_history
        if self._iv_series_active():
            values = list(iv_series.values())
            lo, hi = min(values), max(values)
            current = values[-1]  # dict preserves insertion order
            if hi > lo:
                return float((current - lo) / (hi - lo) * 100.0)
            return 50.0  # flat series: genuinely neutral, never fallback

        if len(historical_data) < window:
            # F9-M-04: LOUD insufficiency -- never a silent neutral 0.5
            # (0.5 < 30 passed the CMP BUY gate on no data).
            return float("-inf")

        # Units-consistent fallback: HV percentile of the CURRENT bar's
        # absolute return within this window's absolute returns.
        closes = [h.close for h in historical_data[-window:]]
        returns = [
            abs((closes[i] - closes[i - 1]) / closes[i - 1])
            for i in range(1, len(closes))
        ]
        lo, hi = min(returns), max(returns)
        if hi <= lo:
            # Zero |return| spread (flat window): min of a degenerate
            # range is the honest value; legacy returned 0.5 here too.
            return 0.0
        current = returns[-1]
        return float((current - lo) / (hi - lo) * 100.0)

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
        # Clip negatives without chained assignment (pandas Copy-on-Write safe)
        df["+DM"] = df["+DM"].clip(lower=0)
        df["-DM"] = df["-DM"].clip(lower=0)

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

    def set_vix_level(self, vix: float | None) -> None:
        """
        Set VIX level with timestamp tracking.

        Args:
            vix: VIX level (float) or None (if feed unavailable)

        This method should be called by the orchestrator market-data task
        every cycle when the feed is live. Setting None indicates feed failure.
        """
        self._vix_level = vix
        self._vix_timestamp = datetime.datetime.now(datetime.UTC)
        if vix is not None:
            self._vix_initialized = True
            logger.debug(f"VIX level updated: {vix:.2f}")
        else:
            logger.warning("VIX feed unavailable - set_vix_level called with None")

    def get_vix_level(self) -> float | None:
        """
        Get current VIX level.

        Returns:
            VIX level as float, or None if unknown/stale/unavailable

        Checks for stale data based on configured threshold.
        """
        if self._vix_level is None:
            return None

        # Check if data is stale
        if self._vix_timestamp is None:
            logger.warning("VIX timestamp missing - treating as unknown")
            return None

        current_time = datetime.datetime.now(datetime.UTC)
        age_seconds = (current_time - self._vix_timestamp).total_seconds()

        if age_seconds > settings.vix_stale_threshold_seconds:
            logger.warning(
                f"VIX data stale (age: {age_seconds:.1f}s > "
                f"threshold: {settings.vix_stale_threshold_seconds}s) "
                f"- treating as unknown"
            )
            return None

        return self._vix_level

    def check_vix_gate(self, direction: str) -> bool:
        """
        Check VIX gate with symmetric fail-safe.

        Args:
            direction: "BUY" or "SELL"

        Returns:
            True if gate passes, False if blocked

        Gating rules:
        - VIX > 15 required for SELL
        - VIX < 15 required for BUY
        - Unknown/stale VIX blocks BOTH directions (symmetric fail-safe)
        - No fake numbers - explicit None handling
        """
        vix = self.get_vix_level()

        if vix is None:
            fail_mode = settings.vix_fail_mode

            if fail_mode == "block_all":
                logger.warning(
                    "VIX unknown/no-feed/stale-feed - gate blocked "
                    "(symmetric fail-safe) "
                    f"direction={direction}, fail_mode={fail_mode}"
                )
                return False  # Both BUY and SELL blocked
            elif fail_mode == "block_buy":
                # Only block BUY, allow SELL through
                if direction == "BUY":
                    logger.warning(
                        "VIX unknown/no-feed/stale-feed - BUY gate blocked "
                        f"fail_mode={fail_mode}"
                    )
                    return False
                else:
                    # SELL passes even without VIX
                    logger.debug(
                        "VIX unknown/no-feed/stale-feed - SELL allowed "
                        f"fail_mode={fail_mode}"
                    )
                    return True

        # VIX available - apply directional gating. Early returns above
        # cover all vix-is-None branches per CMP fail-safe; mypy cannot
        # narrow through the literal-list compare so re-bind local.
        # Use a narrow local variable to keep mypy happy without an assert
        # that would be removed under optimised bytecode (bandit B101).
        if vix is None:
            logger.error("Unexpected vix=None after None branches; blocking")
            return False
        if direction == "SELL":
            # CMP Rule 10: SELL requires VIX above the configured threshold.
            passes: bool = vix > settings.vix_gate_threshold
            logger.debug(f"VIX gate SELL: VIX={vix:.2f}, passes={passes}")
            return passes
        if direction == "BUY":
            # CMP Rule 10: BUY requires VIX below the configured threshold.
            passes = vix < settings.vix_gate_threshold
            logger.debug(f"VIX gate BUY: VIX={vix:.2f}, passes={passes}")
            return passes
        logger.error(f"Invalid direction for VIX gate: {direction}")
        return False

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
        - IV-rank < 30 / ADX > 25 / VIX < 15 for BUY
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

        # F9-C-01 rank provenance: "iv_series" = true option-chain IV rank
        # (CMP-conformant source), "hv_percentile" = consistent-unit HV
        # fallback. The insufficient_history row below emits "none" --
        # neither source produced a rank, so audit provenance never
        # mislabels an unusable series as the rank source.
        iv_source = "iv_series" if self._iv_series_active() else "hv_percentile"

        # F9-M-04 (merged into F9-C-01): insufficient history is LOUD --
        # fail BOTH directions closed instead of the legacy silent 0.5
        # that passed the BUY gate on no data.
        if iv_rank == float("-inf"):
            iv_pass = False
            adx_pass = False
            vix_pass = False
            return False, {
                "iv_rank": iv_rank,
                "adx": adx,
                "vix": self.get_vix_level(),
                "iv_source": "none",
                "reason": "insufficient_history",
                "iv_pass": iv_pass,
                "adx_pass": adx_pass,
                "vix_pass": vix_pass,
            }

        # Apply gating rules based on signal type
        if signal.signal_type == SignalType.SELL:
            # SELL rules: IV-rank > 40 / ADX < 25 / VIX > 15
            iv_pass = iv_rank > 40
            adx_pass = adx < 25
            vix_pass = self.check_vix_gate("SELL")

            if iv_pass and adx_pass and vix_pass:
                return True, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": self.get_vix_level(),
                    "iv_source": iv_source,
                    "reason": "gating_passed",
                }
            else:
                return False, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": self.get_vix_level(),
                    "iv_source": iv_source,
                    "reason": "gating_failed",
                    "iv_pass": iv_pass,
                    "adx_pass": adx_pass,
                    "vix_pass": vix_pass,
                }

        elif signal.signal_type == SignalType.BUY:
            # BUY rules: IV-rank < 30 / ADX > 25 / VIX < 15
            iv_pass = iv_rank < 30
            adx_pass = adx > 25
            vix_pass = self.check_vix_gate("BUY")

            if iv_pass and adx_pass and vix_pass:
                return True, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": self.get_vix_level(),
                    "iv_source": iv_source,
                    "reason": "gating_passed",
                }
            else:
                return False, {
                    "iv_rank": iv_rank,
                    "adx": adx,
                    "vix": self.get_vix_level(),
                    "iv_source": iv_source,
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
                "vix": self.get_vix_level(),
                "iv_source": iv_source,
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
        source_trades: dict[str, list[Trade]] = {}
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
        """
        Increment the legacy process-global Rule-7 counter.

        .. deprecated:: F8-H-02
            Retained solely for backward compatibility with external
            callers/tests. CMP Rule 7 is enforced per-order with a
            persisted SQLite counter at the ``modify_order`` boundary --
            see :meth:`check_modification_limit` /
            :meth:`record_modification_result`. This global int has no
            enforcement role.
        """
        self.modification_counter += 1
        return self.modification_counter

    def reset_modification_counter(self) -> None:
        """Reset the legacy process-global Rule-7 counter (see F8-H-02 note)."""
        self.modification_counter = 0

    def get_modification_count(self, order_id: str | None = None) -> int:
        """
        Get the current Rule-7 modification count.

        F8-H-02: with ``order_id``, reads the persisted per-order counter
        from SQLite (survives restarts, keyed by order). Without one,
        returns the legacy process-global counter (no enforcement role).
        """
        if order_id is None:
            return self.modification_counter
        from .database import db

        return db.get_modification_count(order_id)

    def check_modification_limit(self, order_id: str, limit: int | None = None) -> bool:
        """
        Check whether ``order_id`` still has Rule-7 modification budget.

        Reads the persisted per-order counter. Raises Rule7StateError when
        the counter state cannot be read (DB failure) -- callers must treat
        that as "refuse the modification" (fail-closed).
        """
        if limit is None:
            limit = int(settings.max_modifications)
        current = self.get_modification_count(order_id)
        return current < limit

    def reserve_modification(self, order_id: str, limit: int | None = None) -> int:
        """
        Atomically reserve one Rule-7 modification slot for ``order_id``.

        F8-H-02 reserve/release protocol (race-safe AND failure-safe):
        the persisted counter is incremented BEFORE the broker call inside
        a BEGIN IMMEDIATE transaction, so two concurrent modify attempts
        can never both claim the same slot. If the increment exceeds
        ``limit`` the reservation is rolled back and
        Rule7ModificationLimitError is raised -- the caller must refuse the
        modification. Rule7StateError is raised when the counter state
        cannot be read/written (fail-closed).
        """
        from .database import db

        if limit is None:
            limit = int(settings.max_modifications)
        new_count = db.increment_modification_count(order_id)
        if new_count > limit:
            db.decrement_modification_count(order_id)
            raise Rule7ModificationLimitError(
                f"CMP Rule 7: modification limit ({limit}) exceeded for "
                f"order {order_id} (count would be {new_count})"
            )
        return new_count

    def release_modification(self, order_id: str) -> None:
        """
        Release a reserved Rule-7 slot for ``order_id`` (best-effort).

        Called when a modification was reserved but the broker request
        subsequently failed, so failed attempts never consume budget.
        Never raises: the original broker error is the actionable one.
        """
        from .database import db

        db.decrement_modification_count(order_id)


# Module-level singleton instance
rules_engine = CMPRulesEngine()

__all__ = [
    "CMPRulesEngine",
    "Rule7ModificationLimitError",
    "RuleType",
    "TradingSession",
    "rules_engine",
]
