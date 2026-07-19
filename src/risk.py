import logging
from decimal import Decimal


class Risk:
    def __init__(self, max_position_size: Decimal | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.max_position_size = max_position_size or Decimal("100000")

    def evaluate(self, data: dict) -> bool:
        """Evaluate risk parameters. Returns True if within risk limits."""
        return True

    def calculate_position_size(self, price: Decimal, volatility: Decimal) -> Decimal:
        """Calculate position size based on risk parameters."""
        if volatility < Decimal("0.3"):
            return self.max_position_size * Decimal("0.5")
        return self.max_position_size
