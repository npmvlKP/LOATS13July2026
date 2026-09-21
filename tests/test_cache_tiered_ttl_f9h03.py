"""BG-1 (F9-H-03 close-out): CacheManager must honor per-entry TTL.

Defect this file pins (found by the independent adversarial audit of the
F9-H-03 remediation): ``CacheManager.set(key, value, ttl=...)`` accepted a
per-call ``ttl`` but never used it -- every entry landed in the single
cache-wide TTLCache (default 300 s). Two production consequences:

1. The sentiment LKG entry written with ``ttl=LKG_TTL_SECONDS`` (900 s)
   actually expired with the ordinary 300 s result window -- the LKG
   resilience horizon the TODO-4 spec mandated did not exist.
2. The degraded provenance trigger (``age > LKG_TTL_SECONDS``) was
   unreachable dead code: an entry retrieved from a 300 s cache can never
   be older than ~300 s, so a persisted signal could never carry
   ``degraded=True``. All prior pins passed because they stub
   ``cache_manager`` and inject payloads directly.

Root-cause fix contract pinned here: CacheManager keeps per-TTL tier
stores. Entries with the default TTL live in the original ``_cache``
TTLCache (existing tests reach into it directly -- public contract);
entries with a longer per-call TTL live in a dedicated tier store with
that TTL; re-setting a key with a different TTL re-tiers it; expiry is
strict (no grace window); ``delete``/``clear``/``get_cache_stats`` span
all tiers.

Also pinned (in test_sentiment_ttl_horizons_f9h03.py, kept separate for
atomic commits): the sentiment constants contract -- the horizon chain
must be freshness < degraded-threshold < retention, i.e. the degraded
threshold sits strictly INSIDE the LKG retention horizon (600 s within
900 s), otherwise ``degraded=True`` stays unreachable even with honored
TTLs: an entry older than its retention is evicted and can never be
served, so a threshold at or beyond retention (a first-draft 1500 s
variant, or the shipped-at-HEAD threshold == retention) is dead code by
construction.
"""

import asyncio

import pytest

from loats.utils.cache import CacheConfig, CacheManager


def _manager() -> CacheManager:
    return CacheManager(CacheConfig(ttl_seconds=300, prefix="t", max_size=100))


class TestPerEntryTTLHonored:
    @pytest.mark.asyncio
    async def test_set_with_custom_ttl_reads_back(self) -> None:
        manager = _manager()
        assert await manager.set("k", "v", ttl=60) is True
        assert await manager.get("k") == "v"

    @pytest.mark.asyncio
    async def test_long_entry_outlives_default_ttl(self) -> None:
        """The strict BG-1 pin: a ttl=4 entry must survive past the
        cache-wide 2 s window while a default entry expires on time."""
        manager = CacheManager(CacheConfig(ttl_seconds=2, prefix="t", max_size=100))
        await manager.set("short", "s", ttl=2)
        await manager.set("long", "l", ttl=4)
        await asyncio.sleep(2.3)
        assert await manager.get("short") is None, (
            "default-TTL entry must expire at the cache-wide window"
        )
        assert await manager.get("long") == "l", (
            "per-entry ttl=4 entry must survive past the cache-wide window"
        )

    @pytest.mark.asyncio
    async def test_expired_long_entry_not_served(self) -> None:
        """Strict expiry: a per-entry TTL must evict on time -- no grace
        window from landing in a longer tier."""
        manager = CacheManager(CacheConfig(ttl_seconds=300, prefix="t", max_size=100))
        await manager.set("k", "v", ttl=1)
        await asyncio.sleep(1.15)
        assert await manager.get("k") is None

    @pytest.mark.asyncio
    async def test_reset_with_shorter_ttl_expires_soon(self) -> None:
        """Re-setting a key with a shorter TTL must re-tier it: the entry
        expires at the new horizon, not the original one."""
        manager = _manager()
        await manager.set("k", "v1", ttl=900)
        await manager.set("k", "v2", ttl=1)
        await asyncio.sleep(1.15)
        assert await manager.get("k") is None

    @pytest.mark.asyncio
    async def test_none_ttl_uses_default(self) -> None:
        manager = _manager()
        assert await manager.set("k", "v") is True
        assert await manager.get("k") == "v"

    @pytest.mark.asyncio
    async def test_non_positive_ttl_clamped_to_default(self) -> None:
        """ttl=0 must not create a zero/dead tier -- it clamps to the
        cache-wide default (documented normalization)."""
        manager = _manager()
        assert await manager.set("k", "v", ttl=0) is True
        assert await manager.get("k") == "v"


class TestTierSpanningOperations:
    @pytest.mark.asyncio
    async def test_clear_removes_all_tiers(self) -> None:
        manager = _manager()
        await manager.set("a", "1")
        await manager.set("b", "2", ttl=900)
        count = await manager.clear()
        assert count == 2
        assert await manager.get("a") is None
        assert await manager.get("b") is None

    @pytest.mark.asyncio
    async def test_delete_spans_tiers(self) -> None:
        manager = _manager()
        await manager.set("a", "1", ttl=900)
        assert await manager.delete("a") is True
        assert await manager.get("a") is None

    @pytest.mark.asyncio
    async def test_stats_reflect_all_tiers(self) -> None:
        manager = _manager()
        await manager.set("a", "1")
        await manager.set("b", "2", ttl=900)
        stats = await manager.get_cache_stats()
        assert stats["current_size"] == 2
