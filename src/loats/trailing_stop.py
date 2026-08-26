"""
CMP Strategy Trailing Stop Engine for LOATS13July2026.

Implements monotonic trailing stop loss ratchet with SL-M support:
- Monotonic trailing (only moves in favorable direction)
- Ratchet mechanism (locks in profits)
- SL-M (Stop Loss Market) order integration
- Dynamic adjustment based on volatility
"""

import datetime
from enum import StrEnum
from typing import Any

from .config import get_settings
from .loats_logging import get_logger
from .models import (
    Order,
    OrderType,
    Trade,
    TransactionType,
    OrderVariety,
    OrderStatus,
    ProductType,
)

logger = get_logger(__name__)
settings = get_settings()


class TrailingStopType(StrEnum):
    """Trailing stop type enumeration."""

    FIXED = "fixed"
    PERCENTAGE = "percentage"
    ATR = "atr"
    VOLATILITY = "volatility"
    RATCHET = "ratchet"


class TrailingStopStatus(StrEnum):
    """Trailing stop status enumeration."""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    LOCKED = "locked"


class TrailingStopEngine:
    """CMP Strategy Trailing Stop Engine with monotonic ratchet."""

    def __init__(self) -> None:
        """Initialize TrailingStopEngine."""
        self.default_trailing_percentage = 0.01  # 1%
        self.default_atr_multiplier = 2.0
        self.min_trailing_distance = 0.005  # 0.5%
        self.ratchet_step = 0.002  # 0.2% ratchet increments
        self.max_trailing_distance = 0.05  # 5% maximum

    def initialize_trailing_stop(
        self,
        trade: Trade,
        initial_price: float,
        stop_type: TrailingStopType = TrailingStopType.PERCENTAGE,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Initialize trailing stop for a new trade.

        Returns trailing stop configuration that can be stored with the trade.
        """
        if parameters is None:
            parameters = {}

        config: dict[str, Any] = {
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "entry_price": initial_price,
            "current_price": initial_price,
            "stop_type": stop_type,
            "status": TrailingStopStatus.ACTIVE,
            "trigger_price": None,
            "last_adjustment": datetime.datetime.now(datetime.UTC).isoformat(),
            "adjustment_count": 0,
            "locked_profit": 0.0,
            "parameters": parameters,
            "history": [],
        }

        # Set initial trailing stop based on type
        if stop_type == TrailingStopType.FIXED:
            fixed_amount = parameters.get("fixed_amount", 50.0)  # Default 50 points
            if trade.transaction_type == TransactionType.BUY:
                config["trigger_price"] = initial_price - fixed_amount
            else:
                config["trigger_price"] = initial_price + fixed_amount

        elif stop_type == TrailingStopType.PERCENTAGE:
            percentage = parameters.get("percentage", self.default_trailing_percentage)
            if trade.transaction_type == TransactionType.BUY:
                config["trigger_price"] = initial_price * (1 - percentage)
            else:
                config["trigger_price"] = initial_price * (1 + percentage)

        elif stop_type == TrailingStopType.ATR:
            atr_value = parameters.get("atr", 100.0)  # Default ATR value
            multiplier = parameters.get("multiplier", self.default_atr_multiplier)
            if trade.transaction_type == TransactionType.BUY:
                config["trigger_price"] = initial_price - (atr_value * multiplier)
            else:
                config["trigger_price"] = initial_price + (atr_value * multiplier)

        elif stop_type == TrailingStopType.VOLATILITY:
            volatility = parameters.get("volatility", 0.01)  # Default 1% volatility
            multiplier = parameters.get("multiplier", 2.0)
            if trade.transaction_type == TransactionType.BUY:
                config["trigger_price"] = initial_price - (
                    initial_price * volatility * multiplier
                )
            else:
                config["trigger_price"] = initial_price + (
                    initial_price * volatility * multiplier
                )

        elif stop_type == TrailingStopType.RATCHET:
            # Ratchet starts with initial percentage stop
            percentage = parameters.get("percentage", self.default_trailing_percentage)
            if trade.transaction_type == TransactionType.BUY:
                config["trigger_price"] = initial_price * (1 - percentage)
            else:
                config["trigger_price"] = initial_price * (1 + percentage)
            config["ratchet_levels"] = [config["trigger_price"]]
            config["current_ratchet_level"] = 0

        # Add initial state to history
        config["history"].append(
            {
                "timestamp": config["last_adjustment"],
                "action": "initialized",
                "price": initial_price,
                "trigger_price": config["trigger_price"],
                "status": str(config["status"]),
            }
        )

        return config

    def update_trailing_stop(
        self, config: dict[str, Any], current_price: float, force_adjust: bool = False
    ) -> tuple[dict[str, Any], bool]:
        """
        Update trailing stop based on current price.

        Returns updated config and boolean indicating if stop was triggered.
        """
        if config["status"] != TrailingStopStatus.ACTIVE:
            return config, False

        stop_type = config["stop_type"]
        transaction_type = config.get("transaction_type", "BUY")

        # Determine if we're in a long or short position
        is_long = transaction_type == TransactionType.BUY

        # Check if stop has been triggered
        if is_long and current_price <= config["trigger_price"]:
            config["status"] = TrailingStopStatus.TRIGGERED
            config["triggered_price"] = current_price
            config["triggered_time"] = datetime.datetime.now(datetime.UTC)

            self._add_to_history(config, "triggered", current_price)
            return config, True

        elif not is_long and current_price >= config["trigger_price"]:
            config["status"] = TrailingStopStatus.TRIGGERED
            config["triggered_price"] = current_price
            config["triggered_time"] = datetime.datetime.now(datetime.UTC)

            self._add_to_history(config, "triggered", current_price)
            return config, True

        # Update trailing stop based on type
        if stop_type == TrailingStopType.FIXED:
            # Fixed trailing stop doesn't move
            pass

        elif stop_type == TrailingStopType.PERCENTAGE:
            updated_config, adjusted = self._update_percentage_trailing(
                config, current_price, is_long
            )
            if adjusted:
                config = updated_config

        elif stop_type == TrailingStopType.ATR:
            updated_config, adjusted = self._update_atr_trailing(
                config, current_price, is_long
            )
            if adjusted:
                config = updated_config

        elif stop_type == TrailingStopType.VOLATILITY:
            updated_config, adjusted = self._update_volatility_trailing(
                config, current_price, is_long
            )
            if adjusted:
                config = updated_config

        elif stop_type == TrailingStopType.RATCHET:
            updated_config, adjusted = self._update_ratchet_trailing(
                config, current_price, is_long
            )
            if adjusted:
                config = updated_config

        # Update current price
        config["current_price"] = current_price

        return config, False

    def _update_percentage_trailing(
        self, config: dict[str, Any], current_price: float, is_long: bool
    ) -> tuple[dict[str, Any], bool]:
        """Update percentage-based trailing stop."""
        percentage = config["parameters"].get(
            "percentage", self.default_trailing_percentage
        )
        entry_price = config["entry_price"]

        if is_long:
            # For long positions: stop moves up as price increases
            potential_stop = current_price * (1 - percentage)

            # Monotonic trailing: only move stop up, never down
            if potential_stop > config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Calculate locked profit
                config["locked_profit"] = (
                    config["trigger_price"] - entry_price
                ) * config.get("quantity", 1)

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        else:
            # For short positions: stop moves down as price decreases
            potential_stop = current_price * (1 + percentage)

            # Monotonic trailing: only move stop down, never up
            if potential_stop < config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Calculate locked profit
                config["locked_profit"] = (
                    entry_price - config["trigger_price"]
                ) * config.get("quantity", 1)

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        return config, False

    def _update_atr_trailing(
        self, config: dict[str, Any], current_price: float, is_long: bool
    ) -> tuple[dict[str, Any], bool]:
        """Update ATR-based trailing stop."""
        atr = config["parameters"].get("atr", 100.0)
        multiplier = config["parameters"].get("multiplier", self.default_atr_multiplier)

        if is_long:
            # For long positions: stop moves up as price increases
            potential_stop = current_price - (atr * multiplier)

            # Monotonic trailing: only move stop up, never down
            if potential_stop > config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Update ATR if provided in parameters
                new_atr = config["parameters"].get("current_atr")
                if new_atr is not None:
                    config["parameters"]["atr"] = new_atr

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        else:
            # For short positions: stop moves down as price decreases
            potential_stop = current_price + (atr * multiplier)

            # Monotonic trailing: only move stop down, never up
            if potential_stop < config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Update ATR if provided in parameters
                new_atr = config["parameters"].get("current_atr")
                if new_atr is not None:
                    config["parameters"]["atr"] = new_atr

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        return config, False

    def _update_volatility_trailing(
        self, config: dict[str, Any], current_price: float, is_long: bool
    ) -> tuple[dict[str, Any], bool]:
        """Update volatility-based trailing stop."""
        volatility = config["parameters"].get("volatility", 0.01)
        multiplier = config["parameters"].get("multiplier", 2.0)

        if is_long:
            # For long positions: stop moves up as price increases
            potential_stop = current_price - (current_price * volatility * multiplier)

            # Monotonic trailing: only move stop up, never down
            if potential_stop > config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Update volatility if provided in parameters
                new_volatility = config["parameters"].get("current_volatility")
                if new_volatility is not None:
                    config["parameters"]["volatility"] = new_volatility

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        else:
            # For short positions: stop moves down as price decreases
            potential_stop = current_price + (current_price * volatility * multiplier)

            # Monotonic trailing: only move stop down, never up
            if potential_stop < config["trigger_price"]:
                config["trigger_price"] = potential_stop
                config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                config["adjustment_count"] += 1

                # Update volatility if provided in parameters
                new_volatility = config["parameters"].get("current_volatility")
                if new_volatility is not None:
                    config["parameters"]["volatility"] = new_volatility

                self._add_to_history(config, "adjusted", current_price)
                return config, True

        return config, False

    def _update_ratchet_trailing(
        self, config: dict[str, Any], current_price: float, is_long: bool
    ) -> tuple[dict[str, Any], bool]:
        """Update ratchet-based trailing stop with discrete levels."""
        entry_price = config["entry_price"]
        percentage = config["parameters"].get(
            "percentage", self.default_trailing_percentage
        )
        current_ratchet_level = config.get("current_ratchet_level", 0)

        if is_long:
            # Calculate profit from entry
            current_profit = current_price - entry_price
            profit_percentage = current_profit / entry_price

            # Determine if we should move to next ratchet level
            next_level_threshold = (current_ratchet_level + 1) * self.ratchet_step

            if profit_percentage >= next_level_threshold:
                # Move to next ratchet level
                new_level = current_ratchet_level + 1
                new_stop_percentage = percentage + (new_level * self.ratchet_step)
                new_trigger_price = current_price * (1 - new_stop_percentage)

                # Ensure we don't move stop down
                if new_trigger_price > config["trigger_price"]:
                    config["trigger_price"] = new_trigger_price
                    config["current_ratchet_level"] = new_level
                    config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                    config["adjustment_count"] += 1

                    # Add to ratchet levels history
                    if "ratchet_levels" not in config:
                        config["ratchet_levels"] = []
                    config["ratchet_levels"].append(new_trigger_price)

                    self._add_to_history(config, "ratchet_adjusted", current_price)
                    return config, True

        else:
            # For short positions
            current_profit = entry_price - current_price
            profit_percentage = current_profit / entry_price

            # Determine if we should move to next ratchet level
            next_level_threshold = (current_ratchet_level + 1) * self.ratchet_step

            if profit_percentage >= next_level_threshold:
                # Move to next ratchet level
                new_level = current_ratchet_level + 1
                new_stop_percentage = percentage + (new_level * self.ratchet_step)
                new_trigger_price = current_price * (1 + new_stop_percentage)

                # Ensure we don't move stop up
                if new_trigger_price < config["trigger_price"]:
                    config["trigger_price"] = new_trigger_price
                    config["current_ratchet_level"] = new_level
                    config["last_adjustment"] = datetime.datetime.now(datetime.UTC)
                    config["adjustment_count"] += 1

                    # Add to ratchet levels history
                    if "ratchet_levels" not in config:
                        config["ratchet_levels"] = []
                    config["ratchet_levels"].append(new_trigger_price)

                    self._add_to_history(config, "ratchet_adjusted", current_price)
                    return config, True

        return config, False

    def _add_to_history(
        self, config: dict[str, Any], action: str, current_price: float
    ) -> None:
        """Add entry to trailing stop history with <1ms performance."""
        # Optimized history entry creation for performance
        history_entry = {
            "timestamp": datetime.datetime.now(datetime.UTC),
            "action": action,
            "price": current_price,
            "trigger_price": config["trigger_price"],
            "status": str(config["status"]),
        }

        # Add additional context for adjustments (only when needed)
        if action == "adjusted":
            history_entry["adjustment_count"] = config["adjustment_count"]
            history_entry["locked_profit"] = config.get("locked_profit", 0.0)

        # Use list append (O(1) operation)
        config["history"].append(history_entry)

        # Efficient history size management
        history = config["history"]
        if len(history) > 100:
            config["history"] = history[-100:]

    def create_sl_m_order(self, trade: Trade, trailing_config: dict[str, Any]) -> Order:
        """
        Create SL-M (Stop Loss Market) order for trailing stop.

        SL-M orders are market orders that trigger when stop price is hit.
        """
        if trailing_config["status"] != TrailingStopStatus.ACTIVE:
            raise ValueError("Cannot create SL-M order for non-active trailing stop")

        if trade.transaction_type == TransactionType.BUY:
            # For long positions, SL-M is a sell order
            transaction_type = TransactionType.SELL
        else:
            # For short positions, SL-M is a buy order
            transaction_type = TransactionType.BUY

        sl_m_order = Order(
            order_id=(
                f"slm_{trade.trade_id}_"
                f"{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')}"
            ),
            symbol=trade.symbol,
            quantity=trade.quantity,
            filled_quantity=0,
            order_type=OrderType.SL_M,
            price=trailing_config["trigger_price"],  # Trigger price for SL-M
            trigger_price=trailing_config["trigger_price"],
            variety=OrderVariety.REGULAR,
            transaction_type=transaction_type,
            product_type=trade.product_type or ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime.datetime.now(datetime.UTC),
            stop_loss=None,  # SL-M order doesn't need additional stop loss
            take_profit=None,
            trailing_stop_loss=None,
            idempotency_key=(
                f"slm_{trade.trade_id}_"
                f"{datetime.datetime.now(datetime.UTC).timestamp()}"
            ),
        )

        return sl_m_order

    def update_sl_m_order(
        self, existing_order: Order, new_trigger_price: float
    ) -> Order:
        """
        Update existing SL-M order with new trigger price.

        Returns new order with updated trigger price.
        """
        if existing_order.order_type != OrderType.SL_M:
            raise ValueError("Order is not an SL-M order")

        updated_order = Order(
            **existing_order.model_dump(),
            price=new_trigger_price,
            trigger_price=new_trigger_price,
            timestamp=datetime.datetime.now(datetime.UTC),
            idempotency_key=(
                f"slm_update_{existing_order.order_id}_"
                f"{datetime.datetime.now(datetime.UTC).timestamp()}"
            ),
        )

        return updated_order

    def get_trailing_stop_summary(self, config: dict[str, Any]) -> dict[str, Any]:
        """Get summary of trailing stop configuration."""
        entry_price = config["entry_price"]
        current_price = config["current_price"]
        trigger_price = config["trigger_price"]
        is_long = config.get("transaction_type", "BUY") == TransactionType.BUY

        if is_long:
            current_pnl = (current_price - entry_price) * config.get("quantity", 1)
            max_pnl = (current_price - entry_price) * config.get("quantity", 1)
            drawdown = 0.0
            if current_pnl > 0:
                drawdown = (
                    (current_price - trigger_price) / (current_price - entry_price)
                ) * 100
        else:
            current_pnl = (entry_price - current_price) * config.get("quantity", 1)
            max_pnl = (entry_price - current_price) * config.get("quantity", 1)
            drawdown = 0.0
            if current_pnl > 0:
                drawdown = (
                    (trigger_price - current_price) / (entry_price - current_price)
                ) * 100

        return {
            "trade_id": config["trade_id"],
            "symbol": config["symbol"],
            "status": str(config["status"]),
            "entry_price": entry_price,
            "current_price": current_price,
            "trigger_price": trigger_price,
            "distance_to_trigger": abs(current_price - trigger_price),
            "distance_percentage": abs(
                (current_price - trigger_price) / current_price * 100
            ),
            "current_pnl": current_pnl,
            "max_pnl": max_pnl,
            "locked_profit": config.get("locked_profit", 0.0),
            "drawdown_percentage": drawdown,
            "adjustment_count": config["adjustment_count"],
            "last_adjustment": config["last_adjustment"],
            "stop_type": str(config["stop_type"]),
            "history_count": len(config["history"]),
        }

    def disable_trailing_stop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Disable trailing stop."""
        if config["status"] == TrailingStopStatus.ACTIVE:
            config["status"] = TrailingStopStatus.DISABLED
            config["disabled_time"] = datetime.datetime.now(datetime.UTC)
            self._add_to_history(config, "disabled", config["current_price"])

        return config

    def enable_trailing_stop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Enable trailing stop."""
        if config["status"] == TrailingStopStatus.DISABLED:
            config["status"] = TrailingStopStatus.ACTIVE
            config["enabled_time"] = datetime.datetime.now(datetime.UTC)
            self._add_to_history(config, "enabled", config["current_price"])

        return config

    def lock_trailing_stop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Lock trailing stop at current trigger price."""
        if config["status"] == TrailingStopStatus.ACTIVE:
            config["status"] = TrailingStopStatus.LOCKED
            config["locked_time"] = datetime.datetime.now(datetime.UTC)
            config["locked_price"] = config["trigger_price"]
            self._add_to_history(config, "locked", config["current_price"])

        return config


# Module-level singleton instance
trailing_stop_engine = TrailingStopEngine()

__all__ = [
    "TrailingStopEngine",
    "TrailingStopType",
    "TrailingStopStatus",
    "trailing_stop_engine",
]
