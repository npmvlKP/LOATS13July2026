"""Per-source circuit breakers for signal producers (CMP P5).

CMP P5 names per-source circuit breakers in addition to the global
service-level breakers (``OPENALGO_CIRCUIT_BREAKER`` /
``TELEGRAM_CIRCUIT_BREAKER``). Finding F8-L-01 (FR8, carried since FR7):
only global breakers existed — a single misbehaving producer's failures
were invisible to source-level isolation.

The registry maps every :class:`StrengthSource` member to a dedicated
:class:`CircuitBreaker`. A producer's breaker opens only for that source;
all other sources keep calling through their own breakers.

Configuration is settings-derived with code-level defaults
(``source_breaker_failure_threshold`` / ``source_breaker_timeout_seconds``,
defaulting to the global OpenAlgo breaker's 3/60.0 posture), so thresholds
stay consistent with the existing breaker fleet unless explicitly tuned.
"""

from __future__ import annotations

import threading
from typing import Any

from ..lazy_settings import LazySettings
from ..loats_logging import get_logger
from ..strength import StrengthSource
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Lazy settings binding (TODO-18 / HC-21 contract): importing this module
# builds NO Settings instance — first attribute access proxies through
# get_settings(), so bare-env imports (no OPENALGO_API_KEY) stay clean.
settings: Any = LazySettings()

logger = get_logger(__name__)

__all__ = [
    "PerSourceBreakerRegistry",
    "get_source_breaker",
    "get_source_breaker_registry",
    "get_source_breaker_status",
    "reset_source_breakers",
    "source_breaker_call_async",
]

# Settings knob names; absent settings keep the global-posture defaults.
_FAILURE_THRESHOLD_SETTING = "source_breaker_failure_threshold"
_TIMEOUT_SETTING = "source_breaker_timeout_seconds"

# Defaults mirror the global OpenAlgo breaker posture (3 failures / 60 s).
_DEFAULT_FAILURE_THRESHOLD = 3
_DEFAULT_TIMEOUT_SECONDS = 60.0


def _breaker_config() -> CircuitBreakerConfig:
    """Build the per-source breaker config from settings with fallbacks.

    Settings-derived with code-level defaults so a missing or mis-typed
    knob degrades to the global breaker posture instead of crashing the
    producer path.
    """
    failure_threshold = _DEFAULT_FAILURE_THRESHOLD
    timeout_seconds = _DEFAULT_TIMEOUT_SECONDS
    try:
        raw_threshold: Any = getattr(settings, _FAILURE_THRESHOLD_SETTING, None)
        raw_timeout: Any = getattr(settings, _TIMEOUT_SETTING, None)
    except Exception:  # pragma: no cover - LazySettings misconfiguration
        logger.warning(
            "Per-source breaker settings unavailable; using defaults "
            f"({_DEFAULT_FAILURE_THRESHOLD} failures / "
            f"{_DEFAULT_TIMEOUT_SECONDS}s timeout)"
        )
    else:
        valid_threshold = (
            isinstance(raw_threshold, int)
            and not isinstance(raw_threshold, bool)
            and raw_threshold >= 1
        )
        valid_timeout = (
            isinstance(raw_timeout, int | float)
            and not isinstance(raw_timeout, bool)
            and raw_timeout > 0
        )
        if valid_threshold:
            failure_threshold = raw_threshold
        if valid_timeout:
            timeout_seconds = float(raw_timeout)
    return CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=2,
        timeout=timeout_seconds,
    )


class PerSourceBreakerRegistry:
    """Registry mapping each *active* ``StrengthSource`` to its own breaker.

    CMP P5 / F8-L-01 scope: only sources with a real producer (an
    emission site in ``orchestrator.py``) get a breaker. Dormant enum
    members (``FUNDAMENTAL`` / ``MACHINE_LEARNING`` / ``OPTIONS_FLOW`` —
    zero-weight placeholders per the F7-L-03 disposition, no production
    emitter) are deliberately NOT tracked: a breaker that can never be
    exercised is fleet-status noise, and its state would silently read
    "closed" while measuring nothing. When a producer for a dormant
    source lands, add its member here — ``get`` fail-closes until then.

    Thread-safe: breakers are created eagerly under a lock at
    construction; ``get`` on an existing member never mutates state.
    """

    #: Enum members with a live producer in orchestrator.py. Order is
    #: irrelevant; membership is what defines the breaker fleet scope.
    ACTIVE_SOURCES: frozenset[StrengthSource] = frozenset(
        {
            StrengthSource.TECHNICAL_ANALYSIS,
            StrengthSource.SENTIMENT,
            StrengthSource.VOLATILITY,
            StrengthSource.PRICE_ACTION,
        }
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._breakers: dict[StrengthSource, CircuitBreaker] = {}
        self._build_breakers()

    def _build_breakers(self) -> None:
        with self._lock:
            config = _breaker_config()
            for source in sorted(self.ACTIVE_SOURCES):
                self._breakers[source] = CircuitBreaker(
                    name=f"source:{source.value}",
                    config=CircuitBreakerConfig(
                        failure_threshold=config.failure_threshold,
                        success_threshold=config.success_threshold,
                        timeout=config.timeout,
                    ),
                )

    def get(self, source: StrengthSource) -> CircuitBreaker:
        """Return the breaker for ``source``.

        Fail-closed on dormant sources: a ``StrengthSource`` without a
        production producer (not in ``ACTIVE_SOURCES``) raises
        ``ValueError`` rather than silently returning a breaker that
        could never be exercised.
        """
        key = StrengthSource(source)
        if key not in self.ACTIVE_SOURCES:
            raise ValueError(
                f"source '{key.value}' has no producer; per-source breakers "
                "track active producers only (add the member to "
                "PerSourceBreakerRegistry.ACTIVE_SOURCES when a producer lands)"
            )
        with self._lock:
            return self._breakers[key]

    def get_status(self) -> dict[str, Any]:
        """Status for every source breaker (monitoring/alerting)."""
        with self._lock:
            breakers = dict(self._breakers)
        return {
            source.value: breaker.get_status()
            for source, breaker in sorted(breakers.items())
        }

    def reset(self) -> None:
        """Reset every source breaker (kill-switch recovery, tests)."""
        with self._lock:
            breakers = list(self._breakers.values())
        for breaker in breakers:
            breaker.reset()


_registry_lock = threading.Lock()
_registry: PerSourceBreakerRegistry | None = None


def get_source_breaker_registry() -> PerSourceBreakerRegistry:
    """Return the process-wide per-source breaker registry (singleton)."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = PerSourceBreakerRegistry()
        return _registry


def get_source_breaker(source: StrengthSource) -> CircuitBreaker:
    """Return the breaker for ``source`` from the process-wide registry."""
    return get_source_breaker_registry().get(source)


def get_source_breaker_status() -> dict[str, Any]:
    """Status of every per-source breaker, keyed by source value."""
    return get_source_breaker_registry().get_status()


def reset_source_breakers() -> None:
    """Reset every per-source breaker (kill-switch recovery, tests)."""
    get_source_breaker_registry().reset()


async def source_breaker_call_async(
    source: StrengthSource,
    func: Any,
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Await ``func(*args, **kwargs)`` behind ``source``'s breaker.

    Raises ``CircuitBreakerOpenError`` when that source's breaker is open;
    other sources are unaffected.
    """
    breaker = get_source_breaker(source)
    return await breaker.call_async(func, *args, **kwargs)
