"""
Tests to verify kill switch functionality.
"""

from unittest.mock import patch

import pytest

from src.loats.openalgo import (
    KillSwitchError,
    _async_check_kill_switch,
    _check_kill_switch,
)


def test_kill_switch_check():
    """Test _check_kill_switch function raises KillSwitchError when active."""
    with patch("src.loats.alerts.alerts") as mock_alerts:
        mock_alerts.is_kill_switch_active.return_value = True

        with pytest.raises(KillSwitchError):
            _check_kill_switch()


def test_async_kill_switch_check():
    """Test _async_check_kill_switch function raises KillSwitchError when active."""
    import asyncio

    with patch("src.loats.alerts.alerts") as mock_alerts:
        mock_alerts.is_kill_switch_active.return_value = True

        with pytest.raises(KillSwitchError):
            asyncio.run(_async_check_kill_switch())


if __name__ == "__main__":
    test_kill_switch_check()
    test_async_kill_switch_check()
    print("All kill switch tests passed!")
