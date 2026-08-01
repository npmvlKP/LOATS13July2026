"""
Fixed test to verify kill switch functionality.
"""

from unittest.mock import MagicMock, patch

def test_kill_switch_check():
    """Test _check_kill_switch function raises KillSwitchError when active."""
    with patch("src.loats.alerts.alerts") as mock_alerts:
        mock_alerts.is_kill_switch_active.return_value = True

        from src.loats.openalgo import _check_kill_switch, KillSwitchError

        try:
            _check_kill_switch()
            print("FAILED: Should have raised KillSwitchError")
            return False
        except KillSwitchError:
            print("SUCCESS: KillSwitchError raised as expected")
            return True
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            return False

def test_async_kill_switch_check():
    """Test _async_check_kill_switch function raises KillSwitchError when active."""
    with patch("src.loats.alerts.alerts") as mock_alerts:
        mock_alerts.is_kill_switch_active.return_value = True

        from src.loats.openalgo import _async_check_kill_switch, KillSwitchError
        import asyncio

        try:
            asyncio.run(_async_check_kill_switch())
            print("FAILED: Should have raised KillSwitchError")
            return False
        except KillSwitchError:
            print("SUCCESS: KillSwitchError raised as expected")
            return True
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            return False

if __name__ == "__main__":
    success1 = test_kill_switch_check()
    success2 = test_async_kill_switch_check()

    if success1 and success2:
        print("All kill switch tests passed!")
    else:
        print("Some kill switch tests failed!")