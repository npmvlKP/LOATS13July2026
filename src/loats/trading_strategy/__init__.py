"""Trading Strategy Core for LOATS13July2026."""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.1.0"
__all__ = [
    "TradingStrategyCore",
    "trading_strategy_core",
]

from .core import TradingStrategyCore

# Module-level singleton instance
trading_strategy_core = TradingStrategyCore()

if TYPE_CHECKING:
    from .core import TradingStrategyCore
