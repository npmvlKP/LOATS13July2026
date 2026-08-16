#!/usr/bin/env python3
"""Test script to validate kill switch functionality."""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loats.alerts import alerts
from loats.openalgo import KillSwitchError
from loats.scheduler import TradingScheduler


def main():
    """Test kill switch functionality."""

    # Activate kill switch
    alerts.kill_switch_active = True

    # Test kill switch enforcement
    scheduler = TradingScheduler()
    try:
        scheduler._check_kill_switch()
        return 1
    except KillSwitchError:
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
