"""NVIDIA NIM rate limiting guard implementation."""

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from structlog import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class NimRateGuard:
    """Rate limiting guard for NVIDIA NIM API calls.

    Implements strict rate limiting to prevent 429 "Too Many Requests" errors
    from NVIDIA NIM API. Follows the conservative rate budget from loats.md §1.1.
    """

    MAX_PER_MINUTE = 20  # Conservative (provider cap = 30)
    MIN_GAP_SECONDS = 3.0
    MAX_CONCURRENT = 1

    def __init__(self) -> None:
        """Initialize the rate guard."""
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._timestamps: deque[float] = deque()
        self._last_call: float = 0.0

    async def acquire(self) -> None:
        """Acquire permission to make an API call.

        Enforces both the minimum gap between calls and the sliding window
        rate limit.
        """
        async with self._semaphore:  # Serial only
            now = time.monotonic()

            # Gap enforcement
            gap = now - self._last_call
            if gap < self.MIN_GAP_SECONDS:
                sleep_time = self.MIN_GAP_SECONDS - gap
                logger.debug(
                    "NIM rate guard: waiting for gap",
                    sleep_time=sleep_time,
                    last_call=self._last_call,
                )
                await asyncio.sleep(sleep_time)

            # Sliding 60s window enforcement
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] > 60.0:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.MAX_PER_MINUTE:
                wait = 60.0 - (now - self._timestamps[0]) + 1.0
                logger.debug(
                    "NIM rate guard: waiting for window",
                    wait_time=wait,
                    current_calls=len(self._timestamps),
                )
                await asyncio.sleep(wait)

            self._timestamps.append(time.monotonic())
            self._last_call = time.monotonic()
            logger.debug("NIM rate guard: acquired", current_calls=len(self._timestamps))
            return


async def nim_call_with_backoff(
    fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 4,
    **kwargs: Any,
) -> T:
    """Make a NVIDIA NIM API call with automatic rate limiting and backoff.

    Args:
        fn: The async function to call
        *args: Positional arguments to pass to fn
        max_retries: Maximum number of retries on 429 errors
        **kwargs: Keyword arguments to pass to fn

    Returns:
        The result of the API call

    Raises:
        Exception: If the API call fails after all retries
    """
    _guard = NimRateGuard()
    delays = [30, 60, 120, 300]

    for attempt in range(max_retries + 1):
        await _guard.acquire()
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            if hasattr(e, "response") and e.response.status_code == 429 and attempt < max_retries:
                wait_time = delays[attempt]
                logger.warning(
                    "NIM API 429 error, retrying",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    wait_time=wait_time,
                )
                await asyncio.sleep(wait_time)
                continue
            raise

    # This line should never be reached but satisfies mypy
    raise RuntimeError("Unexpected error in nim_call_with_backoff")
