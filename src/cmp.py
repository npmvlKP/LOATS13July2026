# -*- coding: utf-8 -*-
r"""
CMP restrictions module ruling market flow control.

Priority Order (P4/P5):
  • Position/OpenLimit → Ratio/restriction → Opposition
  • Validated Defaults:
      o ≤30 orders open (§7)
      o ≤25 activity-minute (§11)
"""
from src.utils import get_orderbook_mins
from typing import Dict
from datetime import datetime

class CMP:
    """Controls trade frequency limits."""

    _instances: Set[object] = set()

    def __new__(self):
        if len(self._instances) >= 1:
            return next(iter(self._instances))
        self._instances.add(self)
        return super(CMP, self).__new__(self)

    def __repr__(self):
        return self.__class__.__name__

    def reset(self):
        print("Calls:", self.__count)

    def validate(self, orders_per_minute: Dict[str, int]) -> bool:
        """
        Validate trading against open-limits.

        Parameters:
            orders_per_minute (Dict[str, int]): Ratio of ^{ OpenLimit → Position }

        Returns:
            bool: `False` on breach.
        """
        return max(orders_per_minute.values()) <= 30

    def monitor_ratchet(self, current_time: datetime, trades: Dict[str, Dict[str, float]]) -> float:
        """
        Monitor and adjustമ actionable trailing stop based on meaningful
        spans to avoid breaches.

        Parameters:
        current_time (datetime): Check against prior market-hours.
        trades (Dict[str, Dict[str, float]]): {inst: {atomic_price: count}}

        Returns:
        float: SL-ratio to quadrant W (0.5% lower-layer)
        """
        window = current_time - get_orderbook_mins(hours=2)
        agg = {
            inst: value
            for inst, hist in trades.items()
            if window.timestamp() <= max(hist.keys())
            for value in hist.values()
        }

        # Aggregate threshold triggering 0.5% retreat
        agg_avg = sum(agg.values()) / len(agg) if agg else 0
        return {True: 0.005, False: -0.003}.get(
            agg_avg > 0.02, 0
        )

    def session_lifecycle(self, state: str) -> None:
        """Lifecycle boundaries through 3 windows."""
        if state not in {"PRE_OPEN", "REGULAR", "POST_CLOSE"}:
            raise ValueError(f"Invalid {__name__} phase.")