"""Duplicate-listener pre-flight guard (R-08, 2026-09-30 ops window).

R-08 evidence (`docs/audit-history/24Sep2026-degraded-duplicate-recurrence.md`):
a relaunched OpenAlgo host whose :8765 WebSocket bind fails closed can
still survive as a half-alive duplicate holding a shadowed :5000 Flask
listener (SO_REUSEADDR lets the second bind succeed silently on
Windows). The duplicate serves nobody but races the primary's broker
login -- order-path ambiguity in a live-trading estate. The user's
R-08 decision (bind-or-exit) lands here as the LOATS-side pre-flight:
before touching any resource, refuse to boot when another LIVE LOATS
process already serves the OpenAlgo base URL.

Identity semantics: a 200 JSON body on ``<base_url>/metrics`` containing
the ``cycle_time_stats`` marker is a live LOATS process (this system's
own F9-C-02 metrics beacon); a foreign HTTP server on that port (the
healthy OpenAlgo host, or any other service) is CLEAR. The probe is
read-only and bounded by a short timeout; any connection failure is
clear. Skipped entirely under ``ENVIRONMENT=test`` so test suites never
probe the network.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from .loats_logging import get_logger

logger = get_logger(__name__)

_LOATS_IDENTITY_PATH = "/metrics"
_LOATS_IDENTITY_MARKER = "cycle_time_stats"
_IDENTITY_PROBE_TIMEOUT_SECONDS = 2.0
_IDENTITY_BODY_LIMIT_BYTES = 65536


class DuplicateListenerError(RuntimeError):
    """Another live LOATS process already holds the configured endpoint."""


def check_duplicate_listener(base_url: str) -> None:
    """Fail closed when another live LOATS instance serves ``base_url``.

    Called by ``TradingSystem.initialize`` BEFORE any resource
    initialization, so a refusal needs no compensating teardown. A
    foreign (non-LOATS) listener is clear: the healthy-host case.
    """
    if os.environ.get("ENVIRONMENT") == "test":
        logger.debug("Duplicate-listener preflight skipped (ENVIRONMENT=test)")
        return
    url = base_url.rstrip("/") + _LOATS_IDENTITY_PATH
    # B310: base_url is operator configuration (settings.openalgo_base_url),
    # never user input; the probe is read-only and timeout-bounded.
    try:
        with urllib.request.urlopen(
            url,
            timeout=_IDENTITY_PROBE_TIMEOUT_SECONDS,  # nosec B310
        ) as response:
            body = response.read(_IDENTITY_BODY_LIMIT_BYTES).decode(
                "utf-8", errors="replace"
            )
    except (urllib.error.URLError, OSError, TimeoutError):
        logger.debug(
            "Duplicate-listener preflight: %s not serving a LOATS identity -- clear",
            url,
        )
        return
    if _LOATS_IDENTITY_MARKER in body:
        raise DuplicateListenerError(
            f"R-08: another live LOATS process is serving {url} (metrics "
            "identity marker present) -- refusing to start a duplicate "
            "instance against the shared broker session. Kill the stale "
            "process or repoint OPENALGO_BASE_URL before relaunching."
        )
    logger.debug(
        "Duplicate-listener preflight: %s answered without a LOATS identity -- clear",
        url,
    )
