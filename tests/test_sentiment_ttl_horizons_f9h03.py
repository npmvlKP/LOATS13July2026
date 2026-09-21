"""F9-H-03 sentiment TTL horizons contract (BG-1 close-out).

Kept separate from the CacheManager tier-store pins
(test_cache_tiered_ttl_f9h03.py) so each fix lands as a self-contained,
atomic commit: these pins bind the sentiment horizon chain; the cache
pins bind the per-entry-TTL storage semantics.

Horizon chain (the invariant that makes degraded tagging reachable):
freshness < degraded-threshold < retention. The LKG entry exists only up
to its retention horizon (honored cache TTL), so a degraded threshold at
or beyond retention can never fire -- the tag must trigger strictly
inside the served window.
"""

import pytest


class TestSentimentCacheContract:
    """The F9-H-03 LKG/degraded contract, pinned against real constants."""

    def test_lkg_retention_exceeds_result_freshness(self) -> None:
        from loats.sentiment import LKG_TTL_SECONDS, RESULT_TTL_SECONDS

        assert LKG_TTL_SECONDS > RESULT_TTL_SECONDS

    def test_degraded_threshold_inside_served_window(self) -> None:
        from loats.sentiment import (
            DEGRADED_THRESHOLD_SECONDS,
            LKG_TTL_SECONDS,
            RESULT_TTL_SECONDS,
        )

        assert RESULT_TTL_SECONDS < DEGRADED_THRESHOLD_SECONDS, (
            "degraded must trigger beyond the result-freshness window"
        )
        assert DEGRADED_THRESHOLD_SECONDS < LKG_TTL_SECONDS, (
            "degraded must trigger strictly inside the LKG retention "
            "horizon -- an entry older than retention is evicted and "
            "can never be served with the tag"
        )

    @pytest.mark.asyncio
    async def test_result_and_lkg_coexist_in_real_cache(self) -> None:
        """End-to-end against the REAL global cache manager (the exact
        blind spot of the stubbed pins that let BG-1 through): both the
        result entry and the LKG entry must be readable after their
        honored-TTL writes."""
        from loats.sentiment import LKG_TTL_SECONDS, RESULT_TTL_SECONDS
        from loats.utils.cache import cache_manager as real_cm

        await real_cm.set("sentiment:bg1:res", "R", ttl=RESULT_TTL_SECONDS)
        await real_cm.set("sentiment:bg1:lkg", "L", ttl=LKG_TTL_SECONDS)
        assert await real_cm.get("sentiment:bg1:res") == "R"
        assert await real_cm.get("sentiment:bg1:lkg") == "L"
        await real_cm.delete("sentiment:bg1:res")
        await real_cm.delete("sentiment:bg1:lkg")
