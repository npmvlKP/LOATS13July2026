"""F9-L-03 (TODO-12): insert-time enum-source provenance guard for signals.

Every production signal writer (the five orchestrator producers) tags its
signals with ``metadata["source"] = <StrengthSource value>``; the lifecycle
conversion path tags ``source="position_conversion"`` and the benchmark
fixtures tag ``source="benchmark"`` (or carry the explicit ``test``
provenance key). This module is the insert-time gate that makes untagged or
unknown-source signal rows impossible to create again: the 14Aug legacy
population (42 sentiment rows + 1 combined row, written before per-source
tagging existed) entered the store untagged and had to be removed by the
audited purge script (``scripts/purge_legacy_signal_rows.py``). The purge
cleared the existing population; this guard is the root-cause half that
prevents the recurrence.

Deliberately strict: a missing tag raises (fail-closed), an unknown tag
raises (no silent acceptance of free-form strings), and the only exemptions
are documented constants below. Any new legitimate non-enum source must be
added to ``EXEMPT_SIGNAL_SOURCES`` with a comment naming its writer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .strength import StrengthSource

if TYPE_CHECKING:  # pragma: no cover - import used only for typing
    from .models import Signal

#: Non-producer writers that tag signals with a legitimate non-enum
#: source. ``position_conversion`` is written by the orchestrator
#: lifecycle path (open-position conversion); ``benchmark`` by the
#: performance benchmarker's fixture signals. Anything else must come
#: from ``StrengthSource`` -- no other provenance is accepted.
EXEMPT_SIGNAL_SOURCES: frozenset[str] = frozenset({"position_conversion", "benchmark"})

#: Metadata key that marks a signal as explicit test/benchmark provenance
#: (e.g. ``performance_analyzer`` latency fixtures use ``{"test": ...}``).
#: Such rows declare themselves non-production and bypass the enum-source
#: requirement without ever being mistaken for producer signals.
TEST_PROVENANCE_KEY = "test"

#: Every accepted ``metadata["source"]`` value: the enum values plus the
#: documented exemptions. Derived once; treat as read-only.
ALLOWED_SIGNAL_SOURCES: frozenset[str] = (
    frozenset(source.value for source in StrengthSource) | EXEMPT_SIGNAL_SOURCES
)


class InvalidSignalSourceError(ValueError):
    """A signal insert carried missing or unknown source provenance.

    Raised by :func:`validate_signal_provenance` at insert time; the
    database write paths call it before any row touches the store, so a
    guard violation aborts the insert (and its audit trail) entirely.
    """


def validate_signal_provenance(signal: Signal) -> None:
    """Fail-closed check that ``signal`` carries valid source provenance.

    Accepts exactly one of:
    - ``metadata["source"]`` holding a ``StrengthSource`` value;
    - ``metadata["source"]`` holding a documented exemption
      (``EXEMPT_SIGNAL_SOURCES``);
    - ``metadata[TEST_PROVENANCE_KEY]`` present (explicit test fixture).

    Anything else -- missing tag, ``None``, empty string, or a string
    outside the allow-list -- raises :class:`InvalidSignalSourceError`.
    """
    metadata = signal.metadata or {}
    if TEST_PROVENANCE_KEY in metadata:
        return
    source = metadata.get("source")
    if source is None or not isinstance(source, str) or not source:
        raise InvalidSignalSourceError(
            "signal metadata is missing the required 'source' tag "
            f"(a StrengthSource value); signal_id={signal.signal_id!r} "
            "(F9-L-03: untagged rows are rejected at insert time)"
        )
    if source not in ALLOWED_SIGNAL_SOURCES:
        raise InvalidSignalSourceError(
            f"signal metadata 'source'={source!r} is not a known "
            f"StrengthSource value or documented exemption "
            f"(allowed: {sorted(ALLOWED_SIGNAL_SOURCES)}); "
            f"signal_id={signal.signal_id!r}"
        )
