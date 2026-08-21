"""Rate limiter probe to verify CMP Rule 4 compliance."""
import asyncio
import os
import sys
sys.path.append('g:\\.OA\\LOATS-13July2026\\LOATS13July2026')
from loats.config import get_settings
from loats.utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
    _reset_singletons_for_testing,
)

def main():
    """Probe rate limiter behavior to verify CMP compliance."""
    print("=== CMP Rule 4 Compliance Probe ===")

    # Set required environment variable
    os.environ["OPENALGO_API_KEY"] = "probe_key"

    # Reset singletons for clean test
    _reset_singletons_for_testing()

    # Get settings
    settings = get_settings()
    print(f"1. Settings max_ops: {settings.max_ops}")

    # Test order rate limiter
    print("\n2. Testing Order Rate Limiter:")
    order_limiter = get_order_rate_limiter()
    print(f"   - Order limiter max_ops: {order_limiter.max_ops}")
    print(f"   - Singleton identity check: {order_limiter is get_order_rate_limiter()}")

    # Test smart order rate limiter
    print("\n3. Testing Smart Order Rate Limiter:")
    smart_limiter = get_smart_order_rate_limiter()
    print(f"   - Smart limiter max_ops: {smart_limiter.max_ops}")
    print(f"   - Singleton identity check: {smart_limiter is get_smart_order_rate_limiter()}")

    # Test actual rate limiting behavior
    print("\n4. Testing Actual Rate Limiting Behavior:")

    async def test_order_limiter():
        """Test order rate limiter enforcement."""
        limiter = get_order_rate_limiter()
        acquired = 0
        for i in range(10):  # Try more than max_ops
            if await limiter.acquire():
                acquired += 1
            else:
                break
        return acquired

    async def test_smart_limiter():
        """Test smart order rate limiter enforcement."""
        limiter = get_smart_order_rate_limiter()
        acquired = 0
        for i in range(10):  # Try more than max_ops
            if await limiter.acquire():
                acquired += 1
            else:
                break
        return acquired

    # Run async tests
    order_acquired = asyncio.run(test_order_limiter())
    smart_acquired = asyncio.run(test_smart_limiter())

    print(f"   - Order limiter allowed: {order_acquired}/10 (expected: {settings.max_ops})")
    print(f"   - Smart limiter allowed: {smart_acquired}/10 (expected: {settings.max_ops})")

    # Compliance verification
    print("\n5. CMP Rule 4 Compliance Verification:")
    print(f"   - NSE threshold (<=10): {'PASS' if settings.max_ops <= 10 else 'FAIL'}")
    print(f"   - Self-limit (<=3): {'PASS' if settings.max_ops <= 3 else 'FAIL'}")
    print(f"   - Exact setting (3): {'PASS' if settings.max_ops == 3 else 'FAIL'}")
    print(f"   - Order limiter enforcement: {'PASS' if order_acquired == settings.max_ops else 'FAIL'}")
    print(f"   - Smart limiter enforcement: {'PASS' if smart_acquired == settings.max_ops else 'FAIL'}")

    # Overall compliance
    compliant = (
        settings.max_ops <= 10 and
        settings.max_ops <= 3 and
        settings.max_ops == 3 and
        order_acquired == settings.max_ops and
        smart_acquired == settings.max_ops
    )

    print(f"\n6. Overall CMP Rule 4 Compliance: {'FULLY COMPLIANT' if compliant else 'NON-COMPLIANT'}")

    # Clean up
    del os.environ["OPENALGO_API_KEY"]
    _reset_singletons_for_testing()

if __name__ == "__main__":
    main()