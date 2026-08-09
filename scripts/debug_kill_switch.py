"""
Debug script to understand kill switch functionality.
"""

from unittest.mock import patch


def test_kill_switch_directly():
    """Test kill switch function directly."""
    # Import the function after patching
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    with patch("src.loats.alerts.alerts") as mock_alerts:
        mock_alerts.is_kill_switch_active.return_value = True

        from src.loats.openalgo import KillSwitchError, _check_kill_switch

        try:
            _check_kill_switch()
            print("ERROR: Should have raised KillSwitchError")
        except KillSwitchError:
            print("SUCCESS: KillSwitchError raised as expected")
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")


if __name__ == "__main__":
    test_kill_switch_directly()
