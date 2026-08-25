"""
CMP Strategy Sizing Engine for LOATS13July2026.

Implements 2% fixed-fraction position sizing with:
- Cost-aware calculations
- Margin-aware risk management
- Position size limits
- Volatility-based adjustments
"""

from enum import StrEnum
from typing import Any

import numpy as np

from .config import get_settings
from .loats_logging import get_logger
from .models import FundsData, Trade
from loats import settings

logger = get_logger(__name__)


class SizingMethod(StrEnum):
    """Position sizing method enumeration."""

    FIXED_FRACTION = "fixed_fraction"
    VOLATILITY_BASED = "volatility_based"
    KELLY_CRITERION = "kelly_criterion"
    RISK_PARITY = "risk_parity"


class SizingEngine:
    """CMP Strategy Sizing Engine with 2% fixed-fraction risk management."""

    def __init__(self) -> None:
        """Initialize SizingEngine."""
        self.fixed_fraction = 0.02  # 2% risk per trade
        self.max_position_size = settings.max_position_size
        self.nifty_lot_size = settings.nifty_lot_size
        self.max_order_value = settings.max_order_value
        self.slippage_buffer = 0.005  # 0.5% slippage buffer

    def calculate_fixed_fraction_size(
        self,
        funds: FundsData,
        entry_price: float,
        stop_loss: float,
        symbol: str = "NIFTY",
    ) -> tuple[int, dict[str, Any]]:
        """
        Calculate position size using 2% fixed-fraction method.

        Fixed fraction formula:
        Position Size = (Account Size * Risk Percentage) / (Entry Price - Stop Loss)
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 0, {
                "reason": "invalid_prices",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
            }

        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0, {
                "reason": "invalid_risk_per_share",
                "risk_per_share": risk_per_share,
            }

        # Calculate available capital for risk
        available_capital = funds.available_cash + funds.available_margin
        risk_capital = available_capital * self.fixed_fraction

        # Calculate base position size
        base_size = risk_capital / risk_per_share

        # Apply symbol-specific lot size constraints
        if symbol.upper() == "NIFTY":
            max_lots = 5  # CMP Rule 11: 5 lots max for NIFTY
            position_size = min(int(base_size), max_lots * self.nifty_lot_size)
        elif symbol.upper() == "BANKNIFTY":
            max_lots = 3  # CMP Rule 11: 3 lots max for BANKNIFTY
            position_size = min(int(base_size), max_lots * self.nifty_lot_size)
        else:
            position_size = min(int(base_size), self.max_position_size)

        # Apply additional constraints
        position_size = self._apply_sizing_constraints(
            position_size, entry_price, symbol
        )

        return position_size, {
            "method": "fixed_fraction",
            "fixed_fraction": self.fixed_fraction,
            "available_capital": available_capital,
            "risk_capital": risk_capital,
            "risk_per_share": risk_per_share,
            "base_size": base_size,
            "final_size": position_size,
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
        }

    def _apply_sizing_constraints(
        self, position_size: int, entry_price: float, symbol: str
    ) -> int:
        """Apply additional sizing constraints."""
        # Maximum order value constraint
        order_value = position_size * entry_price
        if order_value > float(self.max_order_value):
            max_size_by_value = int(float(self.max_order_value) / entry_price)
            position_size = min(position_size, max_size_by_value)

        # Minimum position size (1 lot)
        if symbol.upper() in ["NIFTY", "BANKNIFTY"]:
            min_size = self.nifty_lot_size
        else:
            min_size = 1

        position_size = max(position_size, min_size)

        return position_size

    def calculate_volatility_adjusted_size(
        self,
        funds: FundsData,
        entry_price: float,
        stop_loss: float,
        volatility: float,
        symbol: str = "NIFTY",
    ) -> tuple[int, dict[str, Any]]:
        """
        Calculate volatility-adjusted position size.

        Adjusts position size based on market volatility:
        - Higher volatility = smaller position size
        - Lower volatility = larger position size
        """
        # Get base fixed fraction size
        base_size, base_info = self.calculate_fixed_fraction_size(
            funds, entry_price, stop_loss, symbol
        )

        if base_size <= 0:
            return 0, {**base_info, "volatility_adjustment": "skipped"}

        # Normalize volatility (typical range 0.01-0.10 for daily moves)
        normalized_volatility = np.clip(volatility, 0.01, 0.10)

        # Calculate volatility adjustment factor
        # Higher volatility -> smaller position
        volatility_factor = 1.0 / (1.0 + normalized_volatility * 10)

        # Apply volatility adjustment
        adjusted_size = int(base_size * volatility_factor)

        # Ensure minimum size
        adjusted_size = max(adjusted_size, 1)

        return adjusted_size, {
            **base_info,
            "method": "volatility_adjusted",
            "volatility": volatility,
            "normalized_volatility": normalized_volatility,
            "volatility_factor": volatility_factor,
            "base_size": base_size,
            "adjusted_size": adjusted_size,
        }

    def calculate_kelly_criterion_size(
        self,
        funds: FundsData,
        win_probability: float,
        win_loss_ratio: float,
        symbol: str = "NIFTY",
    ) -> tuple[int, dict[str, Any]]:
        """
        Calculate position size using Kelly Criterion.

        Kelly formula: f* = p - (1-p)/b
        where p = win probability, b = win/loss ratio
        """
        if win_probability <= 0 or win_probability >= 1:
            return 0, {
                "reason": "invalid_win_probability",
                "win_probability": win_probability,
            }

        if win_loss_ratio <= 0:
            return 0, {
                "reason": "invalid_win_loss_ratio",
                "win_loss_ratio": win_loss_ratio,
            }

        # Calculate Kelly fraction
        kelly_fraction = win_probability - ((1 - win_probability) / win_loss_ratio)
        kelly_fraction = np.clip(kelly_fraction, 0.0, 1.0)

        # Apply fractional Kelly (typically 1/2 to 1/4 of full Kelly)
        effective_fraction = kelly_fraction * 0.25  # 1/4 Kelly

        # Calculate position size based on available capital
        available_capital = funds.available_cash + funds.available_margin
        position_value = available_capital * effective_fraction

        # Convert to quantity based on current price (approximate)
        # For options, we need the current option price
        approximate_price = 100.0  # Placeholder - should be actual option price
        position_size = int(position_value / approximate_price)

        # Apply constraints
        position_size = self._apply_sizing_constraints(
            position_size, approximate_price, symbol
        )

        return position_size, {
            "method": "kelly_criterion",
            "win_probability": win_probability,
            "win_loss_ratio": win_loss_ratio,
            "kelly_fraction": kelly_fraction,
            "effective_fraction": effective_fraction,
            "available_capital": available_capital,
            "position_value": position_value,
            "approximate_price": approximate_price,
            "position_size": position_size,
        }

    def calculate_margin_aware_size(
        self,
        funds: FundsData,
        entry_price: float,
        stop_loss: float,
        margin_requirement: float,
        symbol: str = "NIFTY",
    ) -> tuple[int, dict[str, Any]]:
        """
        Calculate margin-aware position size.

        Considers margin requirements and available margin.
        """
        # Get base fixed fraction size
        base_size, base_info = self.calculate_fixed_fraction_size(
            funds, entry_price, stop_loss, symbol
        )

        if base_size <= 0:
            return 0, {**base_info, "margin_adjustment": "skipped"}

        # Calculate margin required for the position
        margin_per_unit = entry_price * margin_requirement
        total_margin_required = margin_per_unit * base_size

        # Check against available margin
        available_margin = funds.available_margin
        margin_utilization = (
            total_margin_required / available_margin if available_margin > 0 else 1.0
        )

        # Apply margin constraint
        if margin_utilization > settings.max_margin_utilization:
            # Reduce position size to stay within margin limits
            max_margin_allowed = available_margin * settings.max_margin_utilization
            max_size_by_margin = int(max_margin_allowed / margin_per_unit)
            adjusted_size = min(base_size, max_size_by_margin)
        else:
            adjusted_size = base_size

        return adjusted_size, {
            **base_info,
            "method": "margin_aware",
            "margin_requirement": margin_requirement,
            "margin_per_unit": margin_per_unit,
            "total_margin_required": total_margin_required,
            "available_margin": available_margin,
            "margin_utilization": margin_utilization,
            "max_margin_utilization": settings.max_margin_utilization,
            "base_size": base_size,
            "adjusted_size": adjusted_size,
        }

    def calculate_cost_aware_size(
        self,
        funds: FundsData,
        entry_price: float,
        stop_loss: float,
        cost_per_lot: float,
        symbol: str = "NIFTY",
    ) -> tuple[int, dict[str, Any]]:
        """
        Calculate cost-aware position size.

        Considers transaction costs, slippage, and other trading costs.
        """
        # Get base fixed fraction size
        base_size, base_info = self.calculate_fixed_fraction_size(
            funds, entry_price, stop_loss, symbol
        )

        if base_size <= 0:
            return 0, {**base_info, "cost_adjustment": "skipped"}

        # Calculate total cost for the position
        if symbol.upper() in ["NIFTY", "BANKNIFTY"]:
            lots = base_size / self.nifty_lot_size
            total_cost = lots * cost_per_lot
        else:
            total_cost = base_size * cost_per_lot

        # Calculate cost-adjusted risk capital
        available_capital = funds.available_cash + funds.available_margin
        risk_capital = available_capital * self.fixed_fraction
        net_risk_capital = risk_capital - total_cost

        if net_risk_capital <= 0:
            return 0, {
                **base_info,
                "cost_adjustment": "blocked_by_costs",
                "total_cost": total_cost,
                "risk_capital": risk_capital,
                "net_risk_capital": net_risk_capital,
            }

        # Recalculate position size with net risk capital
        risk_per_share = abs(entry_price - stop_loss)
        adjusted_size = int(net_risk_capital / risk_per_share)

        # Apply constraints
        adjusted_size = self._apply_sizing_constraints(
            adjusted_size, entry_price, symbol
        )

        return adjusted_size, {
            **base_info,
            "method": "cost_aware",
            "cost_per_lot": cost_per_lot,
            "total_cost": total_cost,
            "risk_capital": risk_capital,
            "net_risk_capital": net_risk_capital,
            "base_size": base_size,
            "adjusted_size": adjusted_size,
        }

    def calculate_portfolio_risk_allocation(
        self,
        funds: FundsData,
        current_positions: list[Trade],
        target_risk_per_position: float = 0.02,
    ) -> dict[str, Any]:
        """
        Calculate risk allocation across portfolio.

        Ensures no single position exceeds target risk percentage.
        """
        available_capital = funds.available_cash + funds.available_margin
        total_portfolio_value = funds.total_equity

        # Calculate current risk exposure
        current_risk_exposure = 0.0
        position_risk_breakdown = {}

        for position in current_positions:
            if position.entry_price is not None and position.stop_loss is not None:
                risk_per_unit = abs(position.entry_price - position.stop_loss)
                position_risk = position.quantity * risk_per_unit
                position_risk_percentage = position_risk / total_portfolio_value

                position_risk_breakdown[position.trade_id] = {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "entry_price": position.entry_price,
                    "stop_loss": position.stop_loss,
                    "risk_per_unit": risk_per_unit,
                    "position_risk": position_risk,
                    "risk_percentage": position_risk_percentage,
                }

                current_risk_exposure += position_risk

        # Calculate remaining risk budget
        max_total_risk = total_portfolio_value * 0.10  # 10% max total risk
        remaining_risk_budget = max_total_risk - current_risk_exposure

        return {
            "available_capital": available_capital,
            "total_portfolio_value": total_portfolio_value,
            "current_risk_exposure": current_risk_exposure,
            "max_total_risk": max_total_risk,
            "remaining_risk_budget": remaining_risk_budget,
            "target_risk_per_position": target_risk_per_position,
            "position_risk_breakdown": position_risk_breakdown,
            "risk_utilization": (
                current_risk_exposure / max_total_risk if max_total_risk > 0 else 0.0
            ),
        }

    def get_recommended_sizing_method(
        self,
        volatility: float,
        win_probability: float | None = None,
        margin_requirement: float | None = None,
    ) -> SizingMethod:
        """
        Recommend appropriate sizing method based on market conditions.

        Defaults to fixed fraction for most cases.
        """
        if win_probability is not None and win_probability > 0.6:
            return SizingMethod.KELLY_CRITERION
        elif margin_requirement is not None and margin_requirement > 0.1:
            return SizingMethod.FIXED_FRACTION  # MARGIN_AWARE not in enum
        elif volatility > 0.05:  # High volatility
            return SizingMethod.VOLATILITY_BASED
        else:
            return SizingMethod.FIXED_FRACTION


# Module-level singleton instance
sizing_engine = SizingEngine()

__all__ = ["SizingEngine", "SizingMethod", "sizing_engine"]
