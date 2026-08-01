import asyncio
import time
from src.loats.utils.rate_limiter import AsyncRateLimiter

async def test_sliding_window_debug():
    limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)

    print("Filling window with 5 operations...")
    for i in range(5):
        result = await limiter.acquire()
        print(f"Operation {i+1}: {result}")

    print(f"Final timestamps: {list(limiter.timestamps)}")

    print("\nWaiting 1.1 seconds (more than full window)...")
    await asyncio.sleep(1.1)  # Wait more than full window

    current_time = time.monotonic()
    oldest_time = limiter.timestamps[0] if limiter.timestamps else 0
    print(f"Current time: {current_time}")
    print(f"Oldest timestamp: {oldest_time}")
    print(f"Time difference: {current_time - oldest_time}")
    print(f"Window size: {limiter.window_size}")
    print(f"Should remove oldest? {(current_time - oldest_time) >= limiter.window_size}")

    print(f"Timestamps before next acquire: {list(limiter.timestamps)}")

    print("\nTrying to acquire after 1.1s wait...")
    result = await limiter.acquire()
    print(f"Acquire result: {result}")
    print(f"Timestamps after acquire: {list(limiter.timestamps)}")

if __name__ == "__main__":
    asyncio.run(test_sliding_window_debug())