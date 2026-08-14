"""
Simple test to verify kill switch functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from loats.openalgo import KillSwitchError


def test_kill_switch_check():
    """Test _check_kill_switch function raises KillSwitchError when active."""
    with patch("loats.openalgo._get_alerts") as mock_get_alerts:
        mock_alerts = MagicMock()
        mock_alerts.is_kill_switch_active.return_value = True
        mock_get_alerts.return_value = mock_alerts

        from loats.openalgo import _check_kill_switch

        with pytest.raises(KillSwitchError):
            _check_kill_switch()


if __name__ == "__main__":
    test_kill_switch_check()
    print("Kill switch test passed!")
