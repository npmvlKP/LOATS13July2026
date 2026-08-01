import asyncio
import time
from src.loats.utils.rate_limiter import AsyncRateLimiter

async def test_full_window_debug():
    limiter = AsyncRateLimiter(max_ops=5, window_size=1.0)

    print("Filling window with 5 operations...")
    for i in range(5):
        result = await limiter.acquire()
        print(f"Operation {i+1}: {result}")

    print(f"Timestamps after filling: {list(limiter.timestamps)}")

    print("\nWaiting 1.0 seconds (full window)...")
    await asyncio.sleep(1.0)

    current_time = time.monotonic()
    print(f"Current time: {current_time}")
    print(f"Timestamps before next acquire: {list(limiter.timestamps)}")

    # Check if timestamps should be removed
    for i, ts in enumerate(limiter.timestamps):
        age = current_time - ts
        print(f"Timestamp {i}: {ts}, age: {age}, should remove: {age >= limiter.window_size}")

    print("\nTrying to acquire after 1.0s wait...")
    result = await limiter.acquire()
    print(f"Acquire result: {result}")
    print(f"Timestamps after acquire: {list(limiter.timestamps)}")

if __name__ == "__main__":
    asyncio.run(test_full_window_debug())