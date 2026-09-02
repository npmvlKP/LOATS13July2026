"""HC-15 production probe: strength-gate math + production emission set.

The strength gate is diversity against the full canonical source space (7
members in ``StrengthSource``). 3 distinct sources gives 3/7 ≈ 0.429,
which is below the 0.5 floor and is rejected. 4 distinct sources gives
4/7 ≈ 0.571, which passes. This reflects the CMP requirement that a
valid composite needs at least 4 independent producers.

F8-C-01 hardening: the gate math alone cannot detect a production side
that emits fewer sources than the gate requires. This probe now ALSO
statically asserts that ``orchestrator.py`` contains emission sites for
at least 4 distinct ``StrengthSource`` members — the exact producer set
the gate needs to pass in a live cycle.
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.models import Signal, SignalType
from loats.strength import strength_engine


def _build(n: int) -> list[Signal]:
    valid_sources = ["ml", "sentiment", "ta", "options_flow", "volatility"]
    chosen = valid_sources[:n]
    ts = datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC)
    return [
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            timestamp=ts,
            indicators={},
            confidence=0.6,
            metadata={"source": src, "scan_type": "x"},
        )
        for src in chosen
    ]


def _production_emission_sources() -> set[str]:
    """Return the distinct StrengthSource members emitted by orchestrator.py."""
    orch_path = (
        Path(__file__).resolve().parents[1] / "src" / "loats" / "orchestrator.py"
    )
    text = orch_path.read_text(encoding="utf-8")
    return set(re.findall(r"StrengthSource\.([A-Z_]+)\.value", text))


def main() -> int:
    problems: list[str] = []

    # --- Part 1: gate math (original HC-15) ---
    sig3 = _build(3)
    sig4 = _build(4)
    ok3, det3 = strength_engine.validate_signal_sources(sig3)
    ok4, det4 = strength_engine.validate_signal_sources(sig4)
    print(
        f"3 valid sources -> ok={ok3} diversity={det3.get('diversity_score')} reason={det3.get('reason')}"
    )
    print(
        f"4 valid sources -> ok={ok4} diversity={det4.get('diversity_score')} reason={det4.get('reason')}"
    )
    div3 = det3.get("diversity_score")
    div4 = det4.get("diversity_score")
    score_ok = (
        isinstance(div3, (int, float))
        and isinstance(div4, (int, float))
        and div3 < 0.5
        and div4 >= 0.5
    )
    print(f"3-src rejected AND 4-src accepted: {score_ok}")
    if not score_ok:
        problems.append("gate math: 3-src/4-src expectation violated")

    # --- Part 2 (F8-C-01): production-side emission check ---
    emitted = _production_emission_sources()
    required = {
        "TECHNICAL_ANALYSIS",
        "SENTIMENT",
        "VOLATILITY",
        "PRICE_ACTION",
    }
    print(f"orchestrator emission sites: {sorted(emitted)}")
    print(f"required producers: {sorted(required)}")
    missing = required - emitted
    if missing:
        problems.append(f"orchestrator missing emission sites for: {sorted(missing)}")
    else:
        print("production emission set covers all 4 required producers: True")

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
