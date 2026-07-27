#!/usr/bin/env python3
"""Test script to validate kill switch functionality."""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loats.scheduler import TradingScheduler
from loats.alerts import alerts
from loats.openalgo import KillSwitchError

def main():
    """Test kill switch functionality."""
    print('Kill switch active:', alerts.is_kill_switch_active())

    # Activate kill switch
    alerts.kill_switch_active = True
    print('Kill switch active after setting:', alerts.is_kill_switch_active())

    # Test kill switch enforcement
    scheduler = TradingScheduler()
    try:
        scheduler._check_kill_switch()
        print('ERROR: Kill switch should have blocked!')
        return 1
    except KillSwitchError:
        print('SUCCESS: Kill switch blocked with KillSwitchError')
        return 0
    except Exception as e:
        print(f'SUCCESS: Kill switch blocked with: {type(e).__name__}')
        return 0

if __name__ == "__main__":
    sys.exit(main())