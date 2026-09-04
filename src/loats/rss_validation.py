"""F8-L-05 — RSS feed validation with recorded fallback (startup + CI gate).

Closes the carried finding "bloombergquint RSS feed still unvalidated"
(carried since FR1 as F6-L-06, re-carried as F8-L-05). TODO-27d removed the
defunct bloombergquint feed from settings; this module adds the *proof*
layer that was still missing:

* :func:`validate_feed` -- live HTTP validation for a single URL.
* :func:`run_offline_manifest_validation` -- validates the recorded-source
  manifest (tests/fixtures/rss/recorded-sources.json) with zero network
  access: fixture presence, RSS/XML signature, at least one ``<item>``,
  channel-link host identity, and a defunct-feed marker guard.
* :func:`run_startup_gate` -- the startup gate: offline manifest validation
  always runs; live re-validation of each manifest source is attempted and
  any failure degrades to a WARNING (the recorded fallback is the safety
  net, so startup is never blocked by a transient feed outage).

Fail-closed posture: a missing or malformed manifest raises
:class:`RssManifestError`.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .loats_logging import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "tests" / "fixtures" / "rss" / "recorded-sources.json"

# Signatures accepted as "looks like a syndicated feed" (case-insensitive).
# Tightened after adversarial review (H8, 2026-09-04): bare `<?xml` and
# `<channel` accepted ANY well-formed XML, so the sniff proved nothing.
# The surviving roots (<rss, <feed, <rdf:rdf) are the actual document
# elements of RSS 2.0 / Atom / RSS 1.0; the >=1 <item> requirement stays
# as a second factor. Content-type acceptance in the live validator is
# unchanged (that path also verifies HTTP 200).
FEED_SIGNATURES: tuple[str, ...] = ("<rss", "<feed", "<rdf:rdf")

# The defunct-feed class of bug (F6-L-06 / TODO-27d): this domain migrated to
# bqprime/ndtvprofit and its markets-feed endpoint went 404 non-RSS. Any
# reappearance in the manifest is rejected outright.
DEFUNCT_FEED_MARKER = "bloombergquint"


class RssManifestError(RuntimeError):
    """Raised when the recorded-sources manifest is missing or malformed."""


@dataclass
class SourceValidationResult:
    """Outcome of validating one recorded source."""

    name: str
    url: str
    fixture: str
    ok: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class ManifestValidationResult:
    """Aggregated outcome of offline manifest validation."""

    results: list[SourceValidationResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> list[SourceValidationResult]:
        return [r for r in self.results if not r.ok]

    @property
    def urls(self) -> list[str]:
        return [r.url for r in self.results]


def load_manifest(path: Path | None = None) -> list[dict[str, Any]]:
    """Load and structurally validate the recorded-sources manifest.

    Raises:
        RssManifestError: manifest missing, unreadable, or malformed.
    """
    manifest = path if path is not None else MANIFEST_PATH
    if not manifest.exists():
        raise RssManifestError(f"recorded-sources manifest missing: {manifest}")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RssManifestError(f"manifest unreadable/malformed: {exc}") from exc
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list) or not sources:
        raise RssManifestError("manifest has no non-empty 'sources' list")
    for entry in sources:
        if (
            not isinstance(entry, dict)
            or not entry.get("url")
            or not entry.get("fixture")
        ):
            raise RssManifestError(
                f"manifest source entry missing url/fixture: {entry!r}"
            )
    return sources


def _body_signature_ok(body: str) -> bool:
    return any(sig in body[:4096].lower() for sig in FEED_SIGNATURES)


def validate_recorded_source(
    source: dict[str, Any], repo_root: Path
) -> SourceValidationResult:
    """Offline-validate one recorded source against its fixture."""
    name = str(source.get("name", "<unnamed>"))
    url = str(source.get("url", ""))
    fixture_rel = str(source.get("fixture", ""))
    fixture = repo_root / fixture_rel
    problems: list[str] = []

    if not url.startswith(("http://", "https://")):
        problems.append("source url not http(s)")
    if DEFUNCT_FEED_MARKER in url.lower() or DEFUNCT_FEED_MARKER in (
        fixture.name.lower()
    ):
        problems.append(f"defunct feed marker {DEFUNCT_FEED_MARKER!r} present")

    if not fixture.exists():
        problems.append(f"fixture missing: {fixture_rel}")
    else:
        try:
            body = fixture.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"fixture unreadable: {exc}")
        else:
            if not _body_signature_ok(body):
                problems.append("no RSS/Atom/XML signature in fixture body")
            if not re.findall(r"<item[ >]", body, re.IGNORECASE):
                problems.append("fixture has zero <item> entries")
            channel_links = re.findall(
                r"<link>\s*(https?://[^<\s]+)", body, re.IGNORECASE
            )
            url_host = urlparse(url).netloc
            link_hosts = {urlparse(link).netloc for link in channel_links}
            if url_host not in link_hosts:
                problems.append(
                    f"channel link hosts {sorted(link_hosts)} "
                    f"miss source host {url_host}"
                )

    return SourceValidationResult(
        name=name, url=url, fixture=fixture_rel, ok=not problems, problems=problems
    )


def run_offline_manifest_validation(
    repo_root: Path | None = None, manifest_path: Path | None = None
) -> ManifestValidationResult:
    """Validate the recorded manifest without any network access.

    CI / startup recorded-fallback entry point: deterministic, offline, and
    fail-closed on manifest structural problems (RssManifestError).
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    sources = load_manifest(
        manifest_path if manifest_path is not None else MANIFEST_PATH
    )
    return ManifestValidationResult(
        results=[validate_recorded_source(s, root) for s in sources]
    )


async def validate_feed(url: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Validate one live URL via loats.orchestrator.validate_rss_feed."""
    try:
        # Imported here to avoid an import cycle: orchestrator imports
        # sentiment, strength, and database; nothing in this module's
        # dependency set imports back into rss_validation.
        from .orchestrator import validate_rss_feed

        ok = await asyncio.wait_for(
            validate_rss_feed(url, timeout=int(timeout)), timeout + 5
        )
    except Exception as exc:
        return False, f"validator error: {exc!r}"
    return bool(ok), "live validation passed" if ok else "live validation failed"


def check_effective_feed_settings() -> tuple[bool, list[str]]:
    """Guard the EFFECTIVE settings.rss_feeds (H2, adversarial review).

    The offline manifest check proves the recorded sources; this proves the
    operationally configured list. A deployment overriding RSS_FEEDS with a
    defunct or non-http(s) URL must fail the gate even though the manifest
    is pristine. Non-manifest extra feeds are tolerated with a warning
    (the per-cycle runtime filtering remains their safety net).

    Settings that cannot be loaded (e.g. bare CI runner without
    OPENALGO_API_KEY) degrade to a skip -- the manifest checks stay
    authoritative there, and the in-process startup path always has
    settings available.
    """
    try:
        # Local import: no module-level eager settings (HC-21 contract).
        from .config import get_settings

        effective = list(get_settings().rss_feeds)
    except Exception as exc:
        logger.warning(
            "Effective feed-settings guard skipped (settings unreadable): %r", exc
        )
        return True, []

    manifest_urls = set(run_offline_manifest_validation().urls)
    problems: list[str] = []
    for url in effective:
        if not url.startswith(("http://", "https://")):
            problems.append(f"effective feed not http(s): {url}")
        if DEFUNCT_FEED_MARKER in url.lower():
            problems.append(f"defunct feed in effective settings: {url}")
        elif url not in manifest_urls:
            logger.warning(
                "Effective RSS feed not in recorded manifest (unproven, "
                "runtime filtering applies): %s",
                url,
            )
    return not problems, problems


async def run_startup_gate(
    repo_root: Path | None = None,
    live_timeout: float = 15.0,
    manifest_path: Path | None = None,
    live: bool = True,
) -> bool:
    """Startup gate: recorded-fallback validation; live pass optional.

    1. Offline manifest validation MUST pass (fail-closed: raises
       RssManifestError on structural problems, returns False on any
       recorded-source anomaly).
    2. When ``live`` is True, each manifest source is re-validated over the
       network best-effort; a failure or timeout only logs a WARNING
       (transient outage must not block startup -- the recorded fixtures
       are the fallback). Callers that must not block on I/O pass
       ``live=False`` and re-run with ``live=True`` from a detached task.

    Returns True when the offline gate passes (live results are advisory).
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    manifest = run_offline_manifest_validation(
        repo_root=root, manifest_path=manifest_path
    )
    for result in manifest.results:
        if result.ok:
            logger.info(
                "RSS recorded source valid: %s (%s)", result.name, result.fixture
            )
        else:
            for problem in result.problems:
                logger.error(
                    "RSS recorded source INVALID: %s -- %s", result.name, problem
                )
    if not manifest.ok:
        logger.error(
            "RSS startup gate FAILED: %d of %d recorded sources invalid",
            len(manifest.failures),
            len(manifest.results),
        )
        return False

    # H2 (adversarial review): the manifest proves the recorded sources;
    # the gate must also reject defunct/non-http URLs arriving through the
    # RSS_FEEDS runtime override in the EFFECTIVE settings.
    eff_ok, eff_problems = check_effective_feed_settings()
    for problem in eff_problems:
        logger.error("RSS effective-settings guard: %s", problem)
    if not eff_ok:
        logger.error(
            "RSS startup gate FAILED: effective settings.rss_feeds invalid "
            "(RSS_FEEDS override) -- see guard problems above"
        )
        return False

    logger.info(
        "RSS startup gate: %d recorded sources valid; starting live drift pass",
        len(manifest.results),
    )
    if not live:
        return True
    for url in manifest.urls:
        ok, detail = await validate_feed(url, timeout=live_timeout)
        if ok:
            logger.info("RSS live validation passed: %s", url)
        else:
            logger.warning(
                "RSS live validation failed (recorded fallback remains active): "
                "%s -- %s",
                url,
                detail,
            )
    return True
