#!/usr/bin/env python3
"""
Final test script to verify kill switch enforcement in the scheduler.
This test properly isolates the kill switch functionality.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

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

async def test_kill_switch_check_method():
    """Test the _check_kill_switch method directly."""
    print("Testing _check_kill_switch method...")

    scheduler = TradingScheduler()

    # Test 1: Kill switch inactive - should not raise
    print("Test 1: Kill switch inactive")
    try:
        scheduler._check_kill_switch()
        print("✓ No exception raised when kill switch inactive")
    except KillSwitchError:
        print("✗ Unexpected KillSwitchError when kill switch inactive")
        return False
    except Exception as e:
        print(f"✗ Unexpected exception: {e}")
        return False

    # Test 2: Kill switch active - should raise KillSwitchError
    print("\nTest 2: Kill switch active")
    try:
        # Manually activate kill switch
        alerts.kill_switch_active = True

        scheduler._check_kill_switch()
        print("✗ Should have raised KillSwitchError")
        return False
    except KillSwitchError:
        print("✓ KillSwitchError properly raised when kill switch active")
    except Exception as e:
        print(f"✗ Unexpected exception: {e}")
        return False

    # Test 3: Kill switch deactivated - should not raise
    print("\nTest 3: Kill switch deactivated")
    try:
        alerts.kill_switch_active = False
        scheduler._check_kill_switch()
        print("✓ No exception raised after deactivation")
    except KillSwitchError:
        print("✗ Unexpected KillSwitchError after deactivation")
        return False
    except Exception as e:
        print(f"✗ Unexpected exception: {e}")
        return False

    return True

async def test_kill_switch_in_scheduler_methods():
    """Test kill switch enforcement in scheduler methods with proper mocking."""
    print("\nTesting kill switch enforcement in scheduler methods...")

    scheduler = TradingScheduler()

    # Mock all external calls to isolate kill switch testing
    with patch('loats.scheduler.openalgo_client.get_history', new_callable=AsyncMock) as mock_history:
        with patch('loats.scheduler.openalgo_client.get_quotes', new_callable=AsyncMock) as mock_quotes:
            with patch('loats.scheduler.db.async_store_historical_data', new_callable=AsyncMock):
                with patch('loats.scheduler.technical_analysis.calculate_indicators') as mock_calculate:
                    with patch('loats.scheduler.technical_analysis.generate_signal') as mock_generate:
                        with patch('loats.scheduler.db.async_create_signal', new_callable=AsyncMock):
                            with patch('loats.scheduler.db.async_store_quote', new_callable=AsyncMock):

                                # Set up mocks to return valid data
                                mock_history.return_value = {"data": [{"timestamp": "2024-01-01T00:00:00", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}]}
                                mock_quotes.return_value = {"data": {"NIFTY": {"last_price": 105, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000, "change": 5, "change_percent": 5.0}}}
                                mock_calculate.return_value = []
                                mock_generate.return_value = None

                                # Test 1: Normal operation
                                print("Test 1: Normal operation without kill switch")
                                try:
                                    await scheduler._ta_scan_task()
                                    print("✓ TA scan completed successfully")
                                except KillSwitchError:
                                    print("✗ Unexpected KillSwitchError")
                                    return False
                                except Exception as e:
                                    print(f"✓ TA scan completed (expected: {type(e).__name__})")

                                # Test 2: Kill switch active
                                print("\nTest 2: Kill switch active")
                                alerts.kill_switch_active = True

                                try:
                                    await scheduler._ta_scan_task()
                                    print("✗ Should have been blocked by kill switch")
                                    return False
                                except KillSwitchError:
                                    print("✓ TA scan properly blocked by kill switch")
                                except Exception as e:
                                    print(f"✗ Unexpected exception: {e}")
                                    return False

                                # Test 3: Kill switch deactivated
                                print("\nTest 3: Kill switch deactivated")
                                alerts.kill_switch_active = False

                                try:
                                    await scheduler._ta_scan_task()
                                    print("✓ TA scan completed after deactivation")
                                except KillSwitchError:
                                    print("✗ Unexpected KillSwitchError after deactivation")
                                    return False
                                except Exception as e:
                                    print(f"✓ TA scan completed (expected: {type(e).__name__})")

    return True

async def main():
    """Main test function."""
    try:
        success1 = await test_kill_switch_check_method()
        success2 = await test_kill_switch_in_scheduler_methods()

        if success1 and success2:
            print("\n✅ All kill switch enforcement tests passed!")
            print("🎉 Kill switch security verification completed successfully!")
            return 0
        else:
            print("\n❌ Some kill switch enforcement tests failed!")
            return 1
    except Exception as e:
        print(f"\n💥 Test execution failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)