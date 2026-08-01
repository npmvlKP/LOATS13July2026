import asyncio
import time
from src.loats.utils.rate_limiter import AsyncRateLimiter

async def test_sliding_window_debug():
    limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)

    print("Filling window with 5 operations...")
    for i in range(5):
        result = await limiter.acquire()
        print(f"Operation {i+1}: {result}")
        if i < 4:
            print(f"Timestamps after op {i+1}: {list(limiter.timestamps)}")

    print(f"Final timestamps: {list(limiter.timestamps)}")

    print("\nWaiting 0.5 seconds...")
    await asyncio.sleep(0.5)

    current_time = time.monotonic()
    print(f"Current time: {current_time}")
    print(f"Oldest timestamp: {limiter.timestamps[0] if limiter.timestamps else 'None'}")
    print(f"Time difference: {current_time - limiter.timestamps[0] if limiter.timestamps else 'N/A'}")
    print(f"Window size: {limiter.window_size}")
    print(f"Should remove oldest? {(current_time - limiter.timestamps[0]) >= limiter.window_size if limiter.timestamps else 'N/A'}")

    print(f"Timestamps before next acquire: {list(limiter.timestamps)}")

    print("\nTrying to acquire after 0.5s wait...")
    result = await limiter.acquire()
    print(f"Acquire result: {result}")
    print(f"Timestamps after acquire: {list(limiter.timestamps)}")

if __name__ == "__main__":
    asyncio.run(test_sliding_window_debug())