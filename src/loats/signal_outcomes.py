"""Signal-outcome instrumentation (30Sep evidence wave).

CMP outcome loop for the ANALYZE horizon: every emitted BUY/SELL signal
gets an outcome row that is later resolved against independently recorded
market data -- the >=80% positive-outcome signal gate (user horizon lock,
2026-09-23; ADR-0020 context) grades these verdicts, so the verdict must
be honest by construction:

- a signal whose horizon window carries no recorded bars stays OPEN
  (an honest hole) instead of being fabricated from a snapshot;
- HOLD/NEUTRAL signals are NON_DIRECTIONAL -- they carry no tradeable
  verdict and must never dilute the directional gate;
- rows that cannot be graded at all (invalid enum value, unparseable
  timestamp) fail closed to UNRESOLVABLE instead of guessing.

This module is the pure grading core: no I/O, no clocks (``now`` is
injected), fully deterministic. ``Database.resolve_signal_outcomes``
supplies the rows and persists the verdict; ``orchestrator`` runs the
resolver on the cycle loop.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from enum import StrEnum

from .models import HistoricalData, SignalType


class SignalOutcomeState(StrEnum):
    """Lifecycle states of a signal-outcome row.

    OPEN is the only non-terminal state; the resolver's guarded UPDATE
    (``WHERE outcome_state = 'open'``) makes the first terminal write
    win, so re-running resolution is a no-op even across processes.
    """

    OPEN = "open"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NON_DIRECTIONAL = "non_directional"
    UNRESOLVABLE = "unresolvable"


TERMINAL_OUTCOME_STATES: frozenset[SignalOutcomeState] = frozenset(
    {
        SignalOutcomeState.POSITIVE,
        SignalOutcomeState.NEGATIVE,
        SignalOutcomeState.NON_DIRECTIONAL,
        SignalOutcomeState.UNRESOLVABLE,
    }
)

#: Outcome-evaluation horizon bounds (minutes). The floor keeps the
#: horizon meaningful (an emission must have a window to be graded in);
#: the ceiling caps stranding (rows can never wait more than a day).
MIN_OUTCOME_HORIZON_MINUTES = 1
MAX_OUTCOME_HORIZON_MINUTES = 1440


def validate_signal_outcome_horizon(minutes: int) -> int:
    """Return the clamped outcome horizon in minutes.

    Non-integers and bools degrade to the 60-minute default; values
    outside ``[MIN, MAX]`` clamp to the nearest bound -- instrumentation
    must never fail a signal's producer path.
    """
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        return 60
    if minutes < MIN_OUTCOME_HORIZON_MINUTES:
        return MIN_OUTCOME_HORIZON_MINUTES
    if minutes > MAX_OUTCOME_HORIZON_MINUTES:
        return MAX_OUTCOME_HORIZON_MINUTES
    return minutes


def parse_signal_type(value: str) -> SignalType | None:
    """Return the ``SignalType`` for ``value``, or ``None`` when invalid.

    Invalid enum values are a storage-integrity defect, not a grading
    decision -- the caller maps ``None`` to UNRESOLVABLE (fail-closed)
    rather than guessing a direction.
    """
    try:
        return SignalType(value)
    except ValueError:
        return None


def evaluate_signal_outcome(
    signal_id: str,
    signal_type: str,
    timestamp: datetime.datetime,
    bars: list[HistoricalData],
    horizon_minutes: int,
    strength: float | None = None,
    indicators: Mapping[str, float] | None = None,
    metadata: Mapping[str, object] | None = None,
    confidence: float | None = None,
) -> tuple[SignalOutcomeState, dict[str, object] | None]:
    """Grade one emitted signal against independently recorded bars.

    Args:
        signal_id: Emitted signal's id (echoed back in the outcome
            metadata for auditability).
        signal_type: Stored signal-type value (``BUY``/``SELL``/
            ``HOLD``/``NEUTRAL``); an invalid value fails closed.
        timestamp: Signal emission timestamp (tz-aware); opens the
            horizon window ``[timestamp, timestamp + horizon_minutes]``.
        bars: Independently recorded market data overlapping the window
            (may be empty -- an honest OPEN, never fabricated).
        horizon_minutes: Evaluation horizon in minutes.
        strength: Signal strength (echoed into outcome metadata).
        indicators: Signal indicator snapshot (echoed into metadata).
        metadata: Signal metadata (echoed into metadata).
        confidence: Signal confidence (echoed into metadata).

    Returns:
        ``(state, outcome_metadata)``. ``OPEN`` carries no metadata (the
        row stays untouched); terminal states carry the graded evidence.
    """
    parsed = parse_signal_type(signal_type)
    if parsed in (SignalType.HOLD, SignalType.NEUTRAL):
        return SignalOutcomeState.NON_DIRECTIONAL, None
    if parsed is None:
        return (
            SignalOutcomeState.UNRESOLVABLE,
            {"reason": "invalid_signal_type", "signal_type": signal_type},
        )
    if not bars:
        # No independently recorded bars in the window: stays OPEN -- the
        # verdict would otherwise be fabricated from missing data.
        return SignalOutcomeState.OPEN, None

    entry_price = float(bars[0].open)
    exit_price = float(bars[-1].close)
    favorable = max(float(bar.high) for bar in bars)
    adverse = min(float(bar.low) for bar in bars)
    direction = 1.0 if parsed == SignalType.BUY else -1.0
    if (exit_price - entry_price) * direction > 0:
        state = SignalOutcomeState.POSITIVE
    else:
        state = SignalOutcomeState.NEGATIVE
    return state, {
        "signal_id": signal_id,
        "signal_type": signal_type,
        "horizon_minutes": int(horizon_minutes),
        "bars": len(bars),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "favorable_excursion": favorable,
        "adverse_excursion": adverse,
        "strength": (float(strength) if strength is not None else None),
        "confidence": (float(confidence) if confidence is not None else None),
        "indicators": dict(indicators or {}),
        "signal_metadata": dict(metadata or {}),
    }
