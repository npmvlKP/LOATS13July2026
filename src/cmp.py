"""
CMP restrictions module ruling market flow control.

Priority Order (P4/P5):
  - Position/OpenLimit -> Ratio/restriction -> Opposition
  - Validated Defaults:
      - <=30 orders open (§7)
      - <=25 activity-minute (§11)
"""
from src.utils import get_orderbook_mins
from datetime import datetime, timedelta


class CMP:
    """Controls trade frequency limits."""

    _instances: set["CMP"] = set()

    def __new__(cls) -> "CMP":
        if len(cls._instances) >= 1:
            return next(iter(cls._instances))
        instance = super().__new__(cls)
        cls._instances.add(instance)
        return instance

    def __repr__(self) -> str:
        return self.__class__.__name__

    def reset(self) -> None:
        print("Calls:", getattr(self, "__count", 0))

    def validate(self, orders_per_minute: dict[str, int] | set[int]) -> bool:
        """
        Validate trading against open-limits.

        Parameters:
            orders_per_minute (dict[str, int] | set): Ratio of ^
            { OpenLimit -> Position }

        Returns:
            bool: `False` on breach.
        """
        if isinstance(orders_per_minute, set):
            return max(orders_per_minute) <= 30
        return max(orders_per_minute.values()) <= 30

    def monitor_ratchet(
        self, current_time: datetime, trades: dict[str, dict[str, float]]
    ) -> float:
        """
        Monitor and adjust actionable trailing stop based on meaningful
        spans to avoid breaches.

        Parameters:
            current_time (datetime): Check against prior market-hours.
            trades (dict[str, dict[str, float]]): {inst: {atomic_price:
                count}}

        Returns:
            float: SL-ratio to quadrant W (0.5% lower-layer)
        """
        # The function should check trades within the last 2 hours from
        # current_time. So the window is [current_time - 2 hours,
        # current_time]
        two_hours_before_current = current_time - timedelta(hours=2)

        # Include trades where timestamp is within the 2-hour window from
        # current_time
        agg: dict[str, float] = {
            inst: value
            for inst, hist in trades.items()
            if two_hours_before_current.timestamp()
            <= max(float(key) for key in hist.keys())
            <= current_time.timestamp()
            for value in hist.values()
        }

        # Aggregate threshold triggering 0.5% retreat
        agg_avg = sum(agg.values()) / len(agg) if agg else 0
        if agg_avg > 0.02:
            return 0.005
        if agg_avg < -0.02:
            return -0.003
        return 0

    def session_lifecycle(self, state: str) -> None:
        """Lifecycle boundaries through 3 windows."""
        if state not in {"PRE_OPEN", "REGULAR", "POST_CLOSE"}:
            raise ValueError(f"Invalid session state")
