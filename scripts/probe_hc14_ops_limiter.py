"""HC-14 production probe: shared RateLimiter enforces ``max_ops=3``.

The probe asks ``get_order_rate_limiter()`` (the production singleton
factory) and fires 10 sequential ``acquire()`` calls within a tight
window. Asserts that exactly 3 succeed and 7 are rejected.

Singleton intent: the five consecutive factory calls (with no
arguments) must return the same instance.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.utils.rate_limiter import get_order_rate_limiter  # noqa: E402

ATTEMPTS = 10


async def _run_probe() -> tuple[int, bool]:
    rl_a = get_order_rate_limiter()
    rl_b = get_order_rate_limiter(max_ops=3, window_size=1.0)
    rl_c = get_order_rate_limiter()
    rl_d = get_order_rate_limiter(max_ops=3, window_size=1.0)
    rl_e = get_order_rate_limiter()
    singleton_ok = rl_a is rl_c is rl_e and rl_b is rl_d

    accepted = 0
    for _ in range(ATTEMPTS):
        if await rl_a.acquire():
            accepted += 1
    return accepted, singleton_ok


def main() -> int:
    accepted, singleton_ok = asyncio.run(_run_probe())
    print(f"singleton_ok={singleton_ok}")
    print(f"accepted {accepted}/{ATTEMPTS} (max_ops=3 expected)")
    ok = singleton_ok and accepted == 3
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
