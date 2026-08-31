"""L07 production probe: AsyncRateLimiter enforces <=3 ops/window.

Verifies that AsyncRateLimiter with max_ops=3 and window_size=60 correctly
rejects the 4th and 5th acquire() call within the same window.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.utils.rate_limiter import AsyncRateLimiter


async def main() -> None:
    rl = AsyncRateLimiter(max_ops=3, window_size=60)
    ok = 0
    for _ in range(5):
        if await rl.acquire():
            ok += 1
    assert ok == 3, f"expected 3 got {ok}"
    print(f"rate limiter ok {ok}/5")


if __name__ == "__main__":
    asyncio.run(main())
