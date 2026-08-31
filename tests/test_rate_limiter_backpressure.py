"""Integration tests for RateLimiter backpressure."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_rate_limiter_max_ops_caps_acquires() -> None:
    from loats.utils.rate_limiter import RateLimiter

    rl = RateLimiter(max_ops=3, window_size=1.0)
    results = await asyncio.gather(*[rl.acquire() for _ in range(5)])
    accepted = sum(1 for r in results if r)
    rejected = sum(1 for r in results if not r)
    assert accepted == 3
    assert rejected == 2


@pytest.mark.asyncio
async def test_rate_limiter_singleton_factory() -> None:
    from loats.utils.rate_limiter import get_order_rate_limiter

    rl_a = get_order_rate_limiter()
    rl_b = get_order_rate_limiter()
    rl_c = get_order_rate_limiter()
    assert rl_a is rl_b is rl_c


@pytest.mark.asyncio
async def test_async_rate_limiter_max_ops_caps() -> None:
    from loats.utils.rate_limiter import AsyncRateLimiter

    rl = AsyncRateLimiter(max_ops=3)
    accepted = 0
    for _ in range(5):
        if await rl.acquire():
            accepted += 1
    assert accepted == 3
