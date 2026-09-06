"""F8-L-05 tests — RSS feed validation with recorded fallback.

Covers:
* manifest loading (missing / malformed / structurally invalid -> fail-closed)
* recorded-source validation (signature, <item> presence, host identity,
  defunct bloombergquint marker guard)
* the startup gate (offline authoritative, live pass advisory/degraded)
* orchestrator wiring (start() runs the gate; gate errors never crash)
* live repo integrity: manifest sources == settings.rss_feeds; fixtures valid
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loats.rss_validation import (
    DEFUNCT_FEED_MARKER,
    RssManifestError,
    load_manifest,
    run_offline_manifest_validation,
    run_startup_gate,
    validate_feed,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_validation():
    return run_offline_manifest_validation()


# ----------------------------------------------------------------- helpers --

_VALID_BODY = (
    '<?xml version="1.0"?><rss version="2.0"><channel>'
    "<title>t</title><link>https://example.com/rss</link>"
    "<item><title>a</title><link>https://example.com/a</link></item>"
    "</channel></rss>"
)


def _make_manifest(tmp_path: Path, body: str = _VALID_BODY, url: str | None = None):
    """Build a minimal-but-valid recorded manifest under tmp_path."""
    fixture_rel = "tests/fixtures/rss/example-feed.xml"
    fixture = tmp_path / fixture_rel
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(body, encoding="utf-8")
    manifest_dir = tmp_path / "tests" / "fixtures" / "rss"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / "recorded-sources.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "name": "Example",
                        "url": url or "https://example.com/rss",
                        "fixture": fixture_rel,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


# ------------------------------------------------------------ manifest load --


class TestLoadManifest:
    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(RssManifestError, match="missing"):
            load_manifest(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        bad = tmp_path / "m.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(RssManifestError, match="malformed"):
            load_manifest(bad)

    def test_empty_sources_raises(self, tmp_path):
        bad = tmp_path / "m.json"
        bad.write_text(json.dumps({"sources": []}), encoding="utf-8")
        with pytest.raises(RssManifestError, match="sources"):
            load_manifest(bad)

    def test_entry_missing_url_raises(self, tmp_path):
        bad = tmp_path / "m.json"
        bad.write_text(
            json.dumps({"sources": [{"name": "x", "fixture": "f.xml"}]}),
            encoding="utf-8",
        )
        with pytest.raises(RssManifestError, match="url/fixture"):
            load_manifest(bad)


# --------------------------------------------------- recorded source checks --


class TestRecordedSourceValidation:
    def test_valid_source_passes(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert result.ok
        assert result.urls == ["https://example.com/rss"]

    def test_missing_fixture_fails(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        (tmp_path / "tests/fixtures/rss/example-feed.xml").unlink()
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("fixture missing" in p for p in result.failures[0].problems)

    def test_non_rss_body_fails(self, tmp_path):
        manifest = _make_manifest(tmp_path, body="<html><body>not a feed</body></html>")
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("signature" in p for p in result.failures[0].problems)

    def test_zero_items_fails(self, tmp_path):
        body = (
            '<?xml version="1.0"?><rss version="2.0"><channel>'
            "<link>https://example.com/rss</link></channel></rss>"
        )
        manifest = _make_manifest(tmp_path, body=body)
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("zero <item>" in p for p in result.failures[0].problems)

    def test_host_mismatch_fails(self, tmp_path):
        manifest = _make_manifest(tmp_path, url="https://other-domain.com/rss")
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("miss source host" in p for p in result.failures[0].problems)

    def test_defunct_marker_rejected(self, tmp_path):
        manifest = _make_manifest(
            tmp_path, url=f"https://{DEFUNCT_FEED_MARKER}.com/markets-feed"
        )
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any(DEFUNCT_FEED_MARKER in p for p in result.failures[0].problems)

    def test_non_http_url_rejected(self, tmp_path):
        manifest = _make_manifest(tmp_path, url="ftp://example.com/rss")
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("not http(s)" in p for p in result.failures[0].problems)

    def test_unreadable_fixture_reported(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        # Replace the fixture file with a directory: read_text raises
        # PermissionError (an OSError subclass) on every platform.
        fixture = tmp_path / "tests/fixtures/rss/example-feed.xml"
        fixture.unlink()
        fixture.mkdir()
        result = run_offline_manifest_validation(
            repo_root=tmp_path, manifest_path=manifest
        )
        assert not result.ok
        assert any("fixture unreadable" in p for p in result.failures[0].problems)


# ------------------------------------------------------------- startup gate --


class TestStartupGate:
    @pytest.mark.asyncio
    async def test_gate_passes_with_recorded_fallback(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        with patch(
            "loats.rss_validation.validate_feed",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ):
            ok = await run_startup_gate(repo_root=tmp_path, manifest_path=manifest)
        assert ok is True

    @pytest.mark.asyncio
    async def test_live_failure_degrades_to_warning_not_block(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        with patch(
            "loats.rss_validation.validate_feed",
            new_callable=AsyncMock,
            return_value=(False, "timeout"),
        ):
            ok = await run_startup_gate(repo_root=tmp_path, manifest_path=manifest)
        assert ok is True  # recorded fallback: live outage never blocks startup

    @pytest.mark.asyncio
    async def test_live_false_skips_network_pass(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        mock_feed = AsyncMock(return_value=(True, "ok"))
        with patch("loats.rss_validation.validate_feed", mock_feed):
            ok = await run_startup_gate(
                repo_root=tmp_path, manifest_path=manifest, live=False
            )
        assert ok is True
        mock_feed.assert_not_called()  # no I/O when live pass is deferred

    @pytest.mark.asyncio
    async def test_invalid_manifest_fails_gate_without_live_pass(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        (tmp_path / "tests/fixtures/rss/example-feed.xml").write_text(
            "<html>defunct</html>", encoding="utf-8"
        )
        mock_feed = AsyncMock(return_value=(True, "ok"))
        with patch("loats.rss_validation.validate_feed", mock_feed):
            ok = await run_startup_gate(repo_root=tmp_path, manifest_path=manifest)
        assert ok is False
        mock_feed.assert_not_called()  # no live pass when offline layer fails

    def test_structural_manifest_error_propagates(self, tmp_path):
        missing = tmp_path / "tests" / "fixtures" / "rss" / "nope.json"
        with pytest.raises(RssManifestError):
            run_offline_manifest_validation(repo_root=tmp_path, manifest_path=missing)


class TestEffectiveSettingsGuard:
    """H2 (adversarial review): the EFFECTIVE settings.rss_feeds guard."""

    def test_defunct_url_in_override_rejected(self):
        from loats.rss_validation import check_effective_feed_settings

        with patch("loats.config.get_settings") as mock_settings:
            mock_settings.return_value.rss_feeds = [
                "https://www.bloombergquint.com/markets-feed"
            ]
            ok, problems = check_effective_feed_settings()
        assert ok is False
        assert any("bloombergquint" in p for p in problems)

    def test_non_http_url_in_override_rejected(self):
        from loats.rss_validation import check_effective_feed_settings

        with patch("loats.config.get_settings") as mock_settings:
            mock_settings.return_value.rss_feeds = ["ftp://example.com/rss"]
            ok, problems = check_effective_feed_settings()
        assert ok is False
        assert any("not http(s)" in p for p in problems)

    def test_unknown_extra_feed_tolerated_with_warning(self):
        from loats.rss_validation import check_effective_feed_settings

        with patch("loats.config.get_settings") as mock_settings:
            mock_settings.return_value.rss_feeds = [
                "https://example.com/unrecorded-but-valid"
            ]
            ok, problems = check_effective_feed_settings()
        assert ok is True  # warning only; runtime filtering is the safety net
        assert problems == []

    def test_unreadable_settings_degrade_to_skip(self):
        from loats.rss_validation import check_effective_feed_settings

        with patch("loats.config.get_settings", side_effect=RuntimeError("no env")):
            ok, problems = check_effective_feed_settings()
        assert ok is True  # graceful skip: manifest checks stay authoritative
        assert problems == []

    @pytest.mark.asyncio
    async def test_gate_fails_when_effective_settings_invalid(self, tmp_path):
        manifest = _make_manifest(tmp_path)
        mock_feed = AsyncMock(return_value=(True, "ok"))
        with (
            patch("loats.rss_validation.validate_feed", mock_feed),
            patch(
                "loats.rss_validation.check_effective_feed_settings",
                return_value=(False, ["defunct feed in effective settings"]),
            ),
        ):
            ok = await run_startup_gate(repo_root=tmp_path, manifest_path=manifest)
        assert ok is False
        mock_feed.assert_not_called()  # no live pass when the guard fails


# ------------------------------------------------------- orchestrator wiring --


class TestOrchestratorWiring:
    @pytest.mark.asyncio
    async def test_gate_failure_does_not_crash_startup_hook(self):
        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        with patch(
            "loats.rss_validation.run_startup_gate",
            new_callable=AsyncMock,
            return_value=False,
        ):
            # Must not raise even when the gate reports failure.
            await orch._validate_rss_startup_gate()
        assert orch._rss_drift_task is None  # no live pass after gate failure

    @pytest.mark.asyncio
    async def test_gate_exception_does_not_crash_startup_hook(self):
        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        with patch(
            "loats.rss_validation.run_startup_gate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await orch._validate_rss_startup_gate()
        assert orch._rss_drift_task is None

    @pytest.mark.asyncio
    async def test_gate_success_schedules_detached_live_pass(self):
        import asyncio

        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        mock_gate = AsyncMock(return_value=True)
        with patch("loats.rss_validation.run_startup_gate", mock_gate):
            await orch._validate_rss_startup_gate()
        mock_gate.assert_awaited_once_with(live=False)  # inline pass is offline-only
        assert orch._rss_drift_task is not None
        # The detached pass MUST be re-patched before awaiting: a fire-and-
        # forget task body necessarily runs AFTER the schedule-point context
        # exits, so a single mock spanning the whole test was tried here and
        # PROVEN to leak live HTTP (await_args_list showed only the inline
        # entry while real feeds were fetched). Re-patching keeps the test
        # hermetic and immune to network latency under suite load.
        live_gate = AsyncMock(return_value=True)
        with patch("loats.rss_validation.run_startup_gate", live_gate):
            await asyncio.wait_for(orch._rss_drift_task, timeout=5)
        live_gate.assert_awaited_once_with(live=True)

    @pytest.mark.asyncio
    async def test_detached_live_pass_swallows_gate_exception(self):
        import asyncio

        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        with patch(
            "loats.rss_validation.run_startup_gate",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await orch._validate_rss_startup_gate()
        assert orch._rss_drift_task is not None
        # The detached pass re-enters run_startup_gate with live=True; make
        # it raise to prove the wrapper converts exceptions to warnings.
        with patch(
            "loats.rss_validation.run_startup_gate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network down"),
        ):
            await asyncio.wait_for(orch._rss_drift_task, timeout=5)  # must not raise

    def test_start_source_runs_the_gate(self):
        import inspect

        from loats.orchestrator import TradingOrchestrator

        src = inspect.getsource(TradingOrchestrator.start)
        assert "_validate_rss_startup_gate" in src

    @pytest.mark.asyncio
    async def test_start_runs_gate_before_cycle_task(self):
        """H9 (adversarial review): real end-to-end start() execution.

        A source-grep test cannot catch a regression that MOVES the gate
        call after the cycle task is created; this test executes the real
        start() path and asserts the ordering by observation.
        """
        import asyncio

        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        order: list[str] = []

        async def fake_gate(**kwargs):
            order.append("gate")
            return True

        async def fake_cycle_loop():
            order.append("cycle")
            orch._shutdown_event.set()  # end the loop immediately

        with (
            patch(
                "loats.rss_validation.run_startup_gate",
                side_effect=fake_gate,
            ),
            patch.object(
                TradingOrchestrator, "_run_cycle_loop", side_effect=fake_cycle_loop
            ),
            patch.object(TradingOrchestrator, "_handle_cycle_task_completion"),
        ):
            await orch.start()
            assert orch._cycle_task is not None
            await asyncio.wait_for(orch._cycle_task, timeout=5)
            # The INLINE (offline) gate must have COMPLETED before the cycle
            # task first ran. The detached drift pass re-enters the same
            # gate mock, so "gate" may legitimately appear twice; the
            # ordering contract under test is gate-before-cycle.
            assert "cycle" in order
            assert order.index("gate") < order.index("cycle"), order
            # Drain the detached drift pass (same fake gate) for cleanliness.
            if orch._rss_drift_task is not None:
                await asyncio.wait_for(orch._rss_drift_task, timeout=5)

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_drift_task(self):
        import asyncio

        from loats.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        orch.running = True

        async def never_done() -> None:
            await asyncio.Event().wait()

        orch._rss_drift_task = asyncio.create_task(never_done())
        await orch.shutdown()
        assert orch._rss_drift_task is None


# --------------------------------------------------- live repo integrity -----


class TestLiveRepositoryContract:
    """The real tree: manifest, fixtures, and settings stay in lockstep."""

    def test_manifest_sources_match_settings(self, live_validation):
        import sys

        sys.path.insert(0, str(REPO_ROOT / "src"))
        from loats.config import get_settings

        settings_urls = list(get_settings().rss_feeds)
        assert sorted(live_validation.urls) == sorted(settings_urls)

    def test_live_manifest_passes_offline_validation(self, live_validation):
        assert live_validation.ok, [
            (r.name, r.problems) for r in live_validation.failures
        ]

    def test_settings_contain_no_defunct_feed(self):
        import sys

        sys.path.insert(0, str(REPO_ROOT / "src"))
        from loats.config import get_settings

        assert all(
            DEFUNCT_FEED_MARKER not in u.lower() for u in get_settings().rss_feeds
        )

    def test_fixtures_are_real_rss_with_items(self):
        manifest = load_manifest()
        for source in manifest:
            body = (REPO_ROOT / str(source["fixture"])).read_text(
                encoding="utf-8", errors="replace"
            )
            assert re.search(r"<rss", body, re.IGNORECASE), source["name"]
            assert re.search(r"<item[ >]", body, re.IGNORECASE), source["name"]


# --------------------------------------------------------------- live path ---


class TestValidateFeed:
    @pytest.mark.asyncio
    async def test_scheme_rejection_via_orchestrator(self):
        # Non-URL input must fail fast through the underlying validator
        # without network I/O of consequence.
        ok, detail = await validate_feed("not-a-url")
        assert ok is False
        assert detail

    @pytest.mark.asyncio
    async def test_validator_exception_is_reported_not_raised(self):
        # Any exception from the underlying orchestrator validator is
        # converted to (False, detail) -- the gate must never crash.
        with patch(
            "loats.orchestrator.validate_rss_feed",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network exploded"),
        ):
            ok, detail = await validate_feed("https://example.com/rss")
        assert ok is False
        assert "network exploded" in detail
