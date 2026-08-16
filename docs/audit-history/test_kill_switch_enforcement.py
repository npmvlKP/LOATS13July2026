#!/usr/bin/env python3
"""
Test script to verify kill switch enforcement in the scheduler.
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from loats.alerts import alerts
from loats.openalgo import KillSwitchError
from loats.scheduler import TradingScheduler


async def test_kill_switch_enforcement():
    """Test that kill switch is properly enforced in scheduler operations."""

    # Create scheduler
    scheduler = TradingScheduler()

    # Initialize scheduler
    await scheduler.initialize()

    # Test 1: Normal operation without kill switch
    try:
        await scheduler._ta_scan_task()
    except KillSwitchError:
        return False
    except Exception:
        pass

    # Test 2: Activate kill switch
    try:
        # Directly set the kill switch flag to bypass API dependencies
        alerts.kill_switch_active = True
    except Exception:
        return False

    # Test 3: Verify kill switch is active
    if alerts.is_kill_switch_active():
        pass
    else:
        return False

    # Test 4: Try to run TA scan with kill switch active
    try:
        await scheduler._ta_scan_task()
        return False
    except KillSwitchError:
        pass
    except Exception:
        return False

    # Test 5: Try to run sentiment scan with kill switch active
    try:
        await scheduler._sentiment_scan_task()
        return False
    except KillSwitchError:
        pass
    except Exception:
        return False

    # Test 6: Try to run signal generation with kill switch active
    try:
        await scheduler._signal_generation_task()
        return False
    except KillSwitchError:
        pass
    except Exception:
        return False

    # Test 7: Deactivate kill switch
    try:
        # Directly set the kill switch flag to bypass API dependencies
        alerts.kill_switch_active = False
    except Exception:
        return False

    # Test 8: Verify normal operation resumes
    try:
        await scheduler._ta_scan_task()
    except KillSwitchError:
        return False
    except Exception:
        pass

    return True


async def main():
    """Main test function."""
    try:
        success = await test_kill_switch_enforcement()
        if success:
            return 0
        else:
            return 1
    except Exception:
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
