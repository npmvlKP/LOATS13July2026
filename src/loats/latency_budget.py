"""Single enforcement source for the amended CMP latency budget.

ADR-0021 (R-01 decision (b), 2026-09-30 checkpoint): the CMP cycle
budget is amended to the measured architecture (1 Hz cadence), and every
enforcement surface reads its constants from this module -- no
enforcement surface hardcodes a budget number any more. The producer
warning threshold equals the TA stage budget (80 ms,
``scripts/collect_p1_phase_gate_evidence.py``), replacing the
pre-producer-window 30/40 ms noise class (supersession register S-14).

The 8.0 s producer window itself is NOT a compliance target: cycles
whose producers use the full window count non-compliant by design
(fail-visible), and the window's own value lives in
``config.settings.producer_window_seconds`` -- untouched mid-span
(ADR-0021 SDecision.5).
"""

from __future__ import annotations

# ADR-0021 SDecision.1: compliant cycle budget = the 1 Hz cadence,
# replacing the unreachable legacy 100 ms target (0/26,413 + 0/1,278
# cycles compliant across the checkpoint spans; every isolated stage
# meets its own budget -- the gap IS the bounded 8 s producer window).
CYCLE_COMPLIANCE_TARGET_SECONDS: float = 1.0

# ADR-0021 SDecision.2: producer budget warnings derive from the TA
# stage budget (80 ms) -- the warning fires on a real stage-budget
# breach instead of on every producer execution (S-14 resolution).
PRODUCER_BUDGET_WARNING_SECONDS: float = 0.080

__all__ = [
    "CYCLE_COMPLIANCE_TARGET_SECONDS",
    "PRODUCER_BUDGET_WARNING_SECONDS",
]
