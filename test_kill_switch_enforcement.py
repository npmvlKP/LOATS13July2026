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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from loats.scheduler import TradingScheduler
from loats.alerts import alerts
from loats.openalgo import KillSwitchError

async def test_kill_switch_enforcement():
    """Test that kill switch is properly enforced in scheduler operations."""
    print("Testing kill switch enforcement...")

    # Create scheduler
    scheduler = TradingScheduler()

    # Initialize scheduler
    await scheduler.initialize()

    # Test 1: Normal operation without kill switch
    print("Test 1: Normal operation without kill switch")
    try:
        await scheduler._ta_scan_task()
        print("✓ TA scan task completed successfully")
    except KillSwitchError:
        print("✗ Unexpected KillSwitchError when kill switch is inactive")
        return False
    except Exception as e:
        print(f"✓ TA scan task completed (expected error: {type(e).__name__})")

    # Test 2: Activate kill switch
    print("\nTest 2: Activating kill switch")
    try:
        # Directly set the kill switch flag to bypass API dependencies
        alerts.kill_switch_active = True
        print("✓ Kill switch activated successfully")
    except Exception as e:
        print(f"✗ Failed to activate kill switch: {e}")
        return False

    # Test 3: Verify kill switch is active
    print("\nTest 3: Verifying kill switch is active")
    if alerts.is_kill_switch_active():
        print("✓ Kill switch is active")
    else:
        print("✗ Kill switch should be active but isn't")
        return False

    # Test 4: Try to run TA scan with kill switch active
    print("\nTest 4: Running TA scan with kill switch active")
    try:
        await scheduler._ta_scan_task()
        print("✗ TA scan should have been blocked by kill switch")
        return False
    except KillSwitchError:
        print("✓ TA scan properly blocked by kill switch")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

    # Test 5: Try to run sentiment scan with kill switch active
    print("\nTest 5: Running sentiment scan with kill switch active")
    try:
        await scheduler._sentiment_scan_task()
        print("✗ Sentiment scan should have been blocked by kill switch")
        return False
    except KillSwitchError:
        print("✓ Sentiment scan properly blocked by kill switch")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

    # Test 6: Try to run signal generation with kill switch active
    print("\nTest 6: Running signal generation with kill switch active")
    try:
        await scheduler._signal_generation_task()
        print("✗ Signal generation should have been blocked by kill switch")
        return False
    except KillSwitchError:
        print("✓ Signal generation properly blocked by kill switch")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

    # Test 7: Deactivate kill switch
    print("\nTest 7: Deactivating kill switch")
    try:
        # Directly set the kill switch flag to bypass API dependencies
        alerts.kill_switch_active = False
        print("✓ Kill switch deactivated successfully")
    except Exception as e:
        print(f"✗ Failed to deactivate kill switch: {e}")
        return False

    # Test 8: Verify normal operation resumes
    print("\nTest 8: Verifying normal operation after deactivation")
    try:
        await scheduler._ta_scan_task()
        print("✓ TA scan task completed successfully after kill switch deactivation")
    except KillSwitchError:
        print("✗ Unexpected KillSwitchError after deactivation")
        return False
    except Exception as e:
        print(f"✓ TA scan task completed (expected error: {type(e).__name__})")

    print("\n🎉 All kill switch enforcement tests passed!")
    return True

async def main():
    """Main test function."""
    try:
        success = await test_kill_switch_enforcement()
        if success:
            print("\n✅ Kill switch enforcement verification completed successfully!")
            return 0
        else:
            print("\n❌ Kill switch enforcement verification failed!")
            return 1
    except Exception as e:
        print(f"\n💥 Test execution failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)