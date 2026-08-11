import asyncio
import time
from src.loats.utils.rate_limiter import get_order_rate_limiter, get_smart_order_rate_limiter

async def test_singleton_behavior():
    print("Testing singleton behavior...")

    # Get limiters
    order_limiter = get_order_rate_limiter()
    smart_limiter = get_smart_order_rate_limiter()

    print(f"Order limiter: {id(order_limiter)}, max_ops: {order_limiter.max_ops}")
    print(f"Smart limiter: {id(smart_limiter)}, max_ops: {smart_limiter.max_ops}")

    # Test if they're the same instance
    print(f"Are they the same? {order_limiter is smart_limiter}")

    # Get them again
    order_limiter2 = get_order_rate_limiter()
    smart_limiter2 = get_smart_order_rate_limiter()

    print(f"Order limiter2: {id(order_limiter2)}")
    print(f"Smart limiter2: {id(smart_limiter2)}")
    print(f"Order limiter is order limiter2? {order_limiter is order_limiter2}")
    print(f"Smart limiter is smart limiter2? {smart_limiter is smart_limiter2}")

async def test_basic_functionality():
    print("\nTesting basic functionality...")

    limiter = get_order_rate_limiter()

    # Test basic acquire
    result1 = await limiter.acquire()
    print(f"First acquire: {result1}")

    # Test rapid acquires
    successful = 0
    for i in range(10):
        result = await limiter.acquire()
        if result:
            successful += 1
        # Small delay
        await asyncio.sleep(0.01)

    print(f"Successful acquires in 10 attempts: {successful}")

    # Wait for window to expire
    await asyncio.sleep(1.1)

    # Test after window expires
    result_after = await limiter.acquire()
    print(f"Acquire after window expires: {result_after}")

if __name__ == "__main__":
    asyncio.run(test_singleton_behavior())
    asyncio.run(test_basic_functionality())