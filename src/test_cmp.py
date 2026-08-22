import pytest
from datetime import datetime, timedelta, timezone, UTC
from src.cmp import CMP
from src.utils import get_orderbook_mins


class TestCmp:
    """Tests for CMP module."""

    @pytest.fixture
    def instance(self) -> CMP:
        return CMP()

    def test_uniqueness(self) -> None:
        """Test enforces singleton pattern."""
        # Test that CMP instances are singletons
        cmp1 = CMP()
        cmp2 = CMP()
        assert cmp1 is cmp2, "CMP should be a singleton"
        assert cmp1.__repr__() == cmp2.__repr__(), (
            "Singleton instances should have same repr"
        )

    @pytest.mark.parametrize(
        "orders_per_minute, expected",
        [
            ({10}, True),
            ({25}, True),
            ({50}, False),
        ],
    )
    def test_validate(
        self, orders_per_minute: set[int], expected: bool, instance: CMP
    ) -> None:
        """Test open-order limit enforcement."""
        assert instance.validate(orders_per_minute) is expected

    def test_session_lifecycle(self, instance: CMP) -> None:
        """Test lifecycle boundary stability."""
        states = ["PRE_OPEN", "REGULAR", "POST_CLOSE"]

        # Transitions across all windows
        for state in states:
            instance.session_lifecycle(state)

        # Invalid transitions
        with pytest.raises(ValueError, match="Invalid session state"):
            instance.session_lifecycle("INVALID")

    def test_monitor_ratchet(self, instance: CMP) -> None:
        """Test trailing ratio ammo against price deviations."""
        now = datetime.now(UTC)
        trades = {
            "SBI": {str(now.timestamp()): 2.5},
            "RELIANCE": {str(now.timestamp() + 600): 3.0}
        }

        # Old window
        old = instance.monitor_ratchet(
            now - timedelta(hours=3), trades
        )
        assert old == 0

        # Current ratchet
        actual = instance.monitor_ratchet(now, trades)
        assert actual == 0.005
