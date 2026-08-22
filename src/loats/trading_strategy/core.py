"""Trading Strategy Core Implementation for LOATS13July2026."""

from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any

from ..config import get_settings
from ..loats_logging import get_logger
from ..models import Signal, Trade, Order

logger = get_logger(__name__)
settings = get_settings()


class StrategyMode(StrEnum):
    """Trading strategy mode enumeration."""

    ANALYZE = "ANALYZE"
    LIVE = "LIVE"
    BACKTEST = "BACKTEST"


class TradingStrategyCore:
    """Core trading strategy implementation."""

    def __init__(self) -> None:
        """Initialize TradingStrategyCore."""
        self.mode = StrategyMode.ANALYZE
        self.active_trades: dict[str, Trade] = {}
        self.pending_orders: dict[str, Order] = {}
        self.strategy_state: dict[str, Any] = {}
        
        # Initialize with settings
        self.max_ops = settings.max_ops
        self.max_daily_orders = settings.max_daily_orders
        self.nifty_lot_size = settings.nifty_lot_size
        
        logger.info("TradingStrategyCore initialized")

    def set_mode(self, mode: StrategyMode) -> None:
        """Set the trading strategy mode."""
        self.mode = mode
        logger.info(f"Strategy mode set to {mode}")

    def validate_trade(self, trade: Trade) -> tuple[bool, dict[str, Any]]:
        """Validate a trade against strategy rules."""
        validation_result = {
            "valid": True,
            "reasons": [],
            "warnings": [],
        }

        # Check if we're in analyze mode
        if self.mode == StrategyMode.ANALYZE:
            validation_result["warnings"].append("Running in ANALYZE mode - no real trades")

        # Check position limits
        if trade.symbol == "NIFTY":
            max_positions = settings.max_nifty_positions
        elif trade.symbol == "BANKNIFTY":
            max_positions = settings.max_banknifty_positions
        else:
            max_positions = settings.max_position_per_symbol

        current_positions = len([
            t for t in self.active_trades.values() 
            if t.symbol == trade.symbol
        ])

        if current_positions >= max_positions:
            validation_result["valid"] = False
            validation_result["reasons"].append(
                f"Position limit reached for {trade.symbol} (max: {max_positions})"
            )

        # Check order value limits
        if trade.order_value > settings.max_order_value:
            validation_result["valid"] = False
            validation_result["reasons"].append(
                f"Order value {trade.order_value} exceeds max {settings.max_order_value}"
            )

        return validation_result["valid"], validation_result

    def execute_trade(self, signal: Signal) -> tuple[bool, Trade | None]:
        """Execute a trade based on a signal."""
        if self.mode != StrategyMode.LIVE:
            logger.info(f"Would execute trade in {self.mode} mode: {signal}")
            return False, None

        # Create trade from signal
        trade = Trade(
            trade_id=f"trade_{datetime.datetime.now(datetime.UTC).timestamp()}",
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            entry_price=signal.price,
            quantity=self.nifty_lot_size,  # Use standard lot size
            entry_time=datetime.datetime.now(datetime.UTC),
            status="PENDING",
            metadata={"source": "strategy_core"}
        )

        # Validate trade
        is_valid, validation = self.validate_trade(trade)
        if not is_valid:
            logger.warning(f"Trade validation failed: {validation}")
            return False, None

        # Add to active trades
        self.active_trades[trade.trade_id] = trade
        logger.info(f"Trade executed: {trade.trade_id}")

        return True, trade

    def manage_position(self, trade_id: str, action: str) -> bool:
        """Manage an existing position."""
        trade = self.active_trades.get(trade_id)
        if not trade:
            logger.warning(f"Trade not found: {trade_id}")
            return False

        if action == "CLOSE":
            trade.status = "CLOSED"
            trade.exit_time = datetime.datetime.now(datetime.UTC)
            logger.info(f"Position closed: {trade_id}")
            return True

        elif action == "MODIFY":
            # Check modification limits
            modification_count = trade.metadata.get("modification_count", 0)
            if modification_count >= settings.max_modifications:
                logger.warning(f"Modification limit reached for trade: {trade_id}")
                return False

            trade.metadata["modification_count"] = modification_count + 1
            logger.info(f"Position modified: {trade_id}")
            return True

        else:
            logger.warning(f"Unknown action: {action}")
            return False

    def get_active_trades(self) -> list[Trade]:
        """Get all active trades."""
        return list(self.active_trades.values())

    def get_trade_status(self, trade_id: str) -> dict[str, Any]:
        """Get status of a specific trade."""
        trade = self.active_trades.get(trade_id)
        if not trade:
            return {"status": "NOT_FOUND", "trade_id": trade_id}

        return {
            "status": trade.status,
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "entry_price": trade.entry_price,
            "current_price": trade.current_price if hasattr(trade, 'current_price') else None,
            "pnl": trade.pnl if hasattr(trade, 'pnl') else None,
            "modifications": trade.metadata.get("modification_count", 0)
        }

    def check_ops_limit(self) -> bool:
        """Check if OPS limit would be exceeded."""
        # This is a placeholder - the actual OPS limiting should be done
        # by the rate limiter in the utils package
        return len(self.pending_orders) < self.max_ops

    def get_strategy_metrics(self) -> dict[str, Any]:
        """Get current strategy metrics."""
        return {
            "active_trades": len(self.active_trades),
            "pending_orders": len(self.pending_orders),
            "mode": str(self.mode),
            "max_ops": self.max_ops,
            "max_daily_orders": self.max_daily_orders,
            "current_exposure": sum(
                trade.order_value for trade in self.active_trades.values()
                if hasattr(trade, 'order_value')
            ),
            "max_exposure": float(settings.max_total_exposure)
        }

    def reset(self) -> None:
        """Reset strategy state."""
        self.active_trades.clear()
        self.pending_orders.clear()
        self.strategy_state.clear()
        logger.info("Strategy state reset")

    def update_market_data(self, data: dict[str, Any]) -> None:
        """Update strategy with latest market data."""
        self.strategy_state["market_data"] = data
        logger.debug(f"Market data updated: {list(data.keys())}")

    def get_strategy_config(self) -> dict[str, Any]:
        """Get current strategy configuration."""
        return {
            "mode": str(self.mode),
            "max_ops": self.max_ops,
            "max_daily_orders": self.max_daily_orders,
            "nifty_lot_size": self.nifty_lot_size,
            "max_order_value": float(settings.max_order_value),
            "max_total_exposure": float(settings.max_total_exposure),
            "max_nifty_positions": settings.max_nifty_positions,
            "max_banknifty_positions": settings.max_banknifty_positions
        }
