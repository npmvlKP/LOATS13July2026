#!/usr/bin/env python3
"""
Test script to verify rate limiter functionality.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from loats.utils.rate_limiter import AsyncRateLimiter, RateLimitExceededError
from loats.config import settings

async def test_rate_limiter():
    """Test that rate limiter works correctly."""
    print(f"Testing rate limiter with max_ops={settings.max_ops}")

    limiter = AsyncRateLimiter(max_ops=settings.max_ops, window_size=1.0)

    # Test 1: First few requests should succeed
    success_count = 0
    for i in range(settings.max_ops):
        if await limiter.acquire():
            success_count += 1
            print(f"Request {i+1}: Allowed")
        else:
            print(f"Request {i+1}: Denied (unexpected)")

    if success_count != settings.max_ops:
        print(f"FAIL: Expected {settings.max_ops} successful requests, got {success_count}")
        return False

    # Test 2: Additional request should be denied
    if await limiter.acquire():
        print("FAIL: Rate limit should have been exceeded")
        return False
    else:
        print(f"Request {settings.max_ops + 1}: Denied (expected - rate limit reached)")

    # Test 3: Wait for window to reset and try again
    print("Waiting for rate limit window to reset...")
    await asyncio.sleep(1.1)  # Wait slightly more than window size

    if await limiter.acquire():
        print("Request after reset: Allowed (expected - rate limit reset)")
        return True
    else:
        print("FAIL: Rate limit should have reset")
        return False

async def test_order_rate_limiter():
    """Test the global order rate limiter."""
    print("\nTesting global ORDER_RATE_LIMITER...")

    from loats.utils import ORDER_RATE_LIMITER

    # Test rapid requests
    start_time = time.monotonic()
    allowed = 0
    denied = 0

    for i in range(settings.max_ops * 2):  # Try more than the limit
        if await ORDER_RATE_LIMITER.acquire():
            allowed += 1
        else:
            denied += 1
        await asyncio.sleep(0.01)  # Small delay between requests

    elapsed = time.monotonic() - start_time
    print(f"Made {settings.max_ops * 2} requests in {elapsed:.2f} seconds")
    print(f"Allowed: {allowed}, Denied: {denied}")

    # Should have allowed approximately max_ops requests
    if allowed >= settings.max_ops and denied > 0:
        print("SUCCESS: Rate limiter working correctly")
        return True
    else:
        print("FAIL: Rate limiter not working as expected")
        return False

async def main():
    """Main test function."""
    try:
        success1 = await test_rate_limiter()
        success2 = await test_order_rate_limiter()

        if success1 and success2:
            print("\n✅ All rate limiter tests passed!")
            return 0
        else:
            print("\n❌ Some rate limiter tests failed!")
            return 1
    except Exception as e:
        print(f"\n❌ Error running rate limiter tests: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)