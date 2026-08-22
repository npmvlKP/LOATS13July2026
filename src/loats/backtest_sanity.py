"""
CMP Backtest Sanity Checks for LOATS13July2026.

Implements P4 requirement: backtest sanity validation to ensure
trading strategy performance meets minimum quality thresholds.

Sanity checks include:
- Minimum win rate validation
- Maximum drawdown limits
- Risk-adjusted return checks (Sharpe, Sortino)
- Transaction cost impact
- Sample size requirements
- Overfitting detection
"""

import datetime
from decimal import Decimal
from typing import Any

import numpy as np

from .config import get_settings
from .loats_logging import get_logger
from .models import Trade

logger = get_logger(__name__)
settings = get_settings()


class BacktestSanityResult:
    """Result of backtest sanity checks."""

    def __init__(
        self,
        passed: bool,
        checks: dict[str, dict[str, Any]],
        overall_score: float,
        details: dict[str, Any],
    ) -> None:
        self.passed = passed
        self.checks = checks
        self.overall_score = overall_score
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "passed": self.passed,
            "overall_score": self.overall_score,
            "checks": self.checks,
            "details": self.details,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }


class BacktestSanityEngine:
    """CMP Backtest Sanity Check Engine."""

    def __init__(self) -> None:
        """Initialize BacktestSanityEngine."""
        # Minimum thresholds for sanity checks
        self.min_win_rate = 0.45  # 45% minimum win rate
        self.max_drawdown = 0.25  # 25% maximum drawdown
        self.min_sharpe_ratio = 0.5  # Minimum Sharpe ratio
        self.min_sortino_ratio = 0.6  # Minimum Sortino ratio
        self.max_transaction_cost_ratio = 0.15  # Max 15% transaction cost impact
        self.min_sample_size = 30  # Minimum 30 trades for statistical significance
        self.max_overfitting_score = 0.7  # Overfitting detection threshold

    def run_sanity_checks(
        self,
        trades: list[Trade],
        initial_capital: float,
        transaction_cost_per_trade: float = 20.0,
    ) -> BacktestSanityResult:
        """
        Run comprehensive backtest sanity checks.

        Args:
            trades: List of completed trades with PnL
            initial_capital: Starting capital for backtest
            transaction_cost_per_trade: Cost per trade (brokerage + taxes)

        Returns:
            BacktestSanityResult with detailed check results
        """
        if not trades:
            logger.warning("No trades provided for sanity checks")
            return BacktestSanityResult(
                passed=False,
                checks={},
                overall_score=0.0,
                details={"reason": "no_trades"},
            )

        checks: dict[str, dict[str, Any]] = {}
        details: dict[str, Any] = {}

        # Check 1: Sample size
        checks["sample_size"] = self._check_sample_size(trades)

        # Check 2: Win rate
        checks["win_rate"] = self._check_win_rate(trades)

        # Check 3: Maximum drawdown
        checks["max_drawdown"] = self._check_max_drawdown(
            trades, initial_capital
        )

        # Check 4: Risk-adjusted returns
        checks["sharpe_ratio"] = self._check_sharpe_ratio(trades)
        checks["sortino_ratio"] = self._check_sortino_ratio(trades)

        # Check 5: Transaction cost impact
        checks["transaction_cost"] = self._check_transaction_cost(
            trades, transaction_cost_per_trade, initial_capital
        )

        # Check 6: Profit factor
        checks["profit_factor"] = self._check_profit_factor(trades)

        # Check 7: Average reward/risk ratio
        checks["reward_risk_ratio"] = self._check_reward_risk_ratio(trades)

        # Check 8: Overfitting detection
        checks["overfitting"] = self._check_overfitting(trades)

        # Calculate overall score
        passed_checks = sum(
            1 for check in checks.values() if check["passed"]
        )
        total_checks = len(checks)
        overall_score = passed_checks / total_checks

        # Overall result
        overall_passed = (
            overall_score >= 0.7 and all(checks.values()["passed"] for checks in [
                checks["sample_size"],
                checks["max_drawdown"],
                checks["win_rate"],
            ])
        )

        details["total_trades"] = len(trades)
        details["initial_capital"] = initial_capital
        details["final_capital"] = self._calculate_final_capital(
            trades, initial_capital
        )
        details["total_return"] = (
            details["final_capital"] / initial_capital - 1.0
        )

        logger.info(
            f"Backtest sanity check completed: "
            f"score={overall_score:.2%}, passed={overall_passed}"
        )

        return BacktestSanityResult(
            passed=overall_passed,
            checks=checks,
            overall_score=overall_score,
            details=details,
        )

    def _check_sample_size(self, trades: list[Trade]) -> dict[str, Any]:
        """Check if sample size meets minimum requirements."""
        sample_size = len(trades)
        passed = sample_size >= self.min_sample_size

        return {
            "passed": passed,
            "value": sample_size,
            "threshold": self.min_sample_size,
            "message": (
                f"Sample size {sample_size} "
                f"{'meets' if passed else 'below'} minimum of {self.min_sample_size}"
            ),
        }

    def _check_win_rate(self, trades: list[Trade]) -> dict[str, Any]:
        """Check if win rate meets minimum threshold."""
        profitable_trades = sum(
            1 for t in trades if t.pnl is not None and t.pnl > 0
        )
        total_trades = len(trades)
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0.0

        passed = win_rate >= self.min_win_rate

        return {
            "passed": passed,
            "value": win_rate,
            "threshold": self.min_win_rate,
            "message": (
                f"Win rate {win_rate:.2%} "
                f"{'meets' if passed else 'below'} minimum of {self.min_win_rate:.2%}"
            ),
        }

    def _check_max_drawdown(
        self, trades: list[Trade], initial_capital: float
    ) -> dict[str, Any]:
        """Check if maximum drawdown is within acceptable limits."""
        if not trades:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.max_drawdown,
                "message": "No trades to calculate drawdown",
            }

        # Calculate equity curve
        equity_curve = [initial_capital]
        for trade in trades:
            if trade.pnl is not None:
                equity_curve.append(equity_curve[-1] + float(trade.pnl))

        # Calculate drawdown
        peak = equity_curve[0]
        max_drawdown = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)

        passed = max_drawdown <= self.max_drawdown

        return {
            "passed": passed,
            "value": max_drawdown,
            "threshold": self.max_drawdown,
            "message": (
                f"Maximum drawdown {max_drawdown:.2%} "
                f"{'within' if passed else 'exceeds'} limit of {self.max_drawdown:.2%}"
            ),
        }

    def _check_sharpe_ratio(self, trades: list[Trade]) -> dict[str, Any]:
        """Check if Sharpe ratio meets minimum threshold."""
        if not trades:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.min_sharpe_ratio,
                "message": "No trades to calculate Sharpe ratio",
            }

        # Calculate daily returns
        returns = [
            float(t.pnl) / 10000.0  # Normalize to percentage
            for t in trades
            if t.pnl is not None
        ]

        if not returns or len(returns) < 2:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.min_sharpe_ratio,
                "message": "Insufficient data for Sharpe ratio",
            }

        # Calculate Sharpe ratio (annualized)
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        if std_return == 0:
            sharpe_ratio = 0.0
        else:
            # Assume 252 trading days per year
            sharpe_ratio = (mean_return / std_return) * np.sqrt(252)

        passed = sharpe_ratio >= self.min_sharpe_ratio

        return {
            "passed": passed,
            "value": sharpe_ratio,
            "threshold": self.min_sharpe_ratio,
            "message": (
                f"Sharpe ratio {sharpe_ratio:.2f} "
                f"{'meets' if passed else 'below'} minimum of {self.min_sharpe_ratio:.2f}"
            ),
        }

    def _check_sortino_ratio(self, trades: list[Trade]) -> dict[str, Any]:
        """Check if Sortino ratio meets minimum threshold."""
        if not trades:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.min_sortino_ratio,
                "message": "No trades to calculate Sortino ratio",
            }

        # Calculate daily returns
        returns = [
            float(t.pnl) / 10000.0  # Normalize to percentage
            for t in trades
            if t.pnl is not None
        ]

        if not returns or len(returns) < 2:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.min_sortino_ratio,
                "message": "Insufficient data for Sortino ratio",
            }

        # Calculate downside deviation
        mean_return = np.mean(returns)
        downside_returns = [r for r in returns if r < 0]

        if not downside_returns:
            sortino_ratio = float('inf') if mean_return > 0 else 0.0
        else:
            downside_std = np.std(downside_returns, ddof=1)
            if downside_std == 0:
                sortino_ratio = 0.0
            else:
                sortino_ratio = (mean_return / downside_std) * np.sqrt(252)

        passed = sortino_ratio >= self.min_sortino_ratio

        return {
            "passed": passed,
            "value": float(sortino_ratio) if sortino_ratio != float('inf') else 999.0,
            "threshold": self.min_sortino_ratio,
            "message": (
                f"Sortino ratio {sortino_ratio:.2f} "
                f"{'meets' if passed else 'below'} minimum of {self.min_sortino_ratio:.2f}"
            ),
        }

    def _check_transaction_cost(
        self,
        trades: list[Trade],
        cost_per_trade: float,
        initial_capital: float,
    ) -> dict[str, Any]:
        """Check if transaction costs are not eroding profits."""
        if not trades:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": self.max_transaction_cost_ratio,
                "message": "No trades to calculate transaction cost",
            }

        total_cost = len(trades) * cost_per_trade
        total_pnl = sum(float(t.pnl) for t in trades if t.pnl is not None)

        if total_pnl <= 0:
            cost_ratio = 1.0  # 100% if no profit
        else:
            cost_ratio = total_cost / abs(total_pnl)

        passed = cost_ratio <= self.max_transaction_cost_ratio

        return {
            "passed": passed,
            "value": cost_ratio,
            "threshold": self.max_transaction_cost_ratio,
            "message": (
                f"Transaction cost ratio {cost_ratio:.2%} "
                f"{'within' if passed else 'exceeds'} limit of {self.max_transaction_cost_ratio:.2%}"
            ),
        }

    def _check_profit_factor(self, trades: list[Trade]) -> dict[str, Any]:
        """Check profit factor (gross profit / gross loss)."""
        gross_profit = sum(
            float(t.pnl) for t in trades if t.pnl is not None and t.pnl > 0
        )
        gross_loss = abs(
            sum(float(t.pnl) for t in trades if t.pnl is not None and t.pnl < 0)
        )

        if gross_loss == 0:
            profit_factor = float('inf') if gross_profit > 0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

        # Profit factor >= 1.5 is considered good
        passed = profit_factor >= 1.5

        return {
            "passed": passed,
            "value": float(profit_factor) if profit_factor != float('inf') else 999.0,
            "threshold": 1.5,
            "message": (
                f"Profit factor {profit_factor:.2f} "
                f"{'meets' if passed else 'below'} minimum of 1.5"
            ),
        }

    def _check_reward_risk_ratio(self, trades: list[Trade]) -> dict[str, Any]:
        """Check average reward/risk ratio."""
        if not trades:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": 1.0,
                "message": "No trades to calculate reward/risk ratio",
            }

        # Calculate reward/risk for each trade
        rr_ratios = []
        for trade in trades:
            if (
                trade.pnl is not None
                and trade.stop_loss is not None
                and trade.entry_price is not None
            ):
                risk = abs(float(trade.entry_price) - float(trade.stop_loss))
                if risk > 0:
                    reward = abs(float(trade.pnl)) / float(trade.quantity)
                    rr_ratios.append(reward / risk)

        if not rr_ratios:
            return {
                "passed": False,
                "value": 0.0,
                "threshold": 1.0,
                "message": "Insufficient data for reward/risk ratio",
            }

        avg_rr_ratio = np.mean(rr_ratios)
        passed = avg_rr_ratio >= 1.0

        return {
            "passed": passed,
            "value": float(avg_rr_ratio),
            "threshold": 1.0,
            "message": (
                f"Average reward/risk ratio {avg_rr_ratio:.2f} "
                f"{'meets' if passed else 'below'} minimum of 1.0"
            ),
        }

    def _check_overfitting(self, trades: list[Trade]) -> dict[str, Any]:
        """Check for signs of overfitting in backtest results."""
        if len(trades) < 30:
            return {
                "passed": True,  # Skip if insufficient data
                "value": 0.0,
                "threshold": self.max_overfitting_score,
                "message": "Insufficient data for overfitting check",
            }

        # Calculate overfitting score based on:
        # 1. Excessive win rate (> 70%)
        # 2. Unusually low volatility in returns
        # 3. Perfect execution (no slippage)

        # Win rate check
        win_rate = sum(
            1 for t in trades if t.pnl is not None and t.pnl > 0
        ) / len(trades)

        # Volatility check
        returns = [
            float(t.pnl) for t in trades if t.pnl is not None
        ]
        volatility = np.std(returns) / np.mean(returns) if np.mean(returns) != 0 else 0.0

        # Overfitting score (0-1, higher = more likely overfitted)
        overfitting_score = 0.0

        if win_rate > 0.7:
            overfitting_score += 0.5  # High win rate suspicious

        if 0 < volatility < 0.5:  # Very low volatility suspicious
            overfitting_score += 0.3

        passed = overfitting_score < self.max_overfitting_score

        return {
            "passed": passed,
            "value": overfitting_score,
            "threshold": self.max_overfitting_score,
            "message": (
                f"Overfitting score {overfitting_score:.2f} "
                f"{'within' if passed else 'exceeds'} limit of {self.max_overfitting_score:.2f}"
            ),
        }

    def _calculate_final_capital(
        self, trades: list[Trade], initial_capital: float
    ) -> float:
        """Calculate final capital from trades."""
        final_capital = initial_capital
        for trade in trades:
            if trade.pnl is not None:
                final_capital += float(trade.pnl)
        return final_capital


# Module-level singleton instance
backtest_sanity_engine = BacktestSanityEngine()

__all__ = [
    "BacktestSanityEngine",
    "BacktestSanityResult",
    "backtest_sanity_engine",
]