"""HC-16 production probe: unknown source string loudly rejected.

Exercises StrengthEngine.validate_signal_sources with a fabricated source
that is NOT in StrengthSource. Asserts the engine returns
``reason == "unknown_source"`` with the offender listed.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.models import Signal, SignalType  # noqa: E402
from loats.strength import strength_engine  # noqa: E402


def main() -> int:
    ts = datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC)
    offenders = [
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            timestamp=ts,
            indicators={},
            confidence=0.6,
            metadata={"source": "fabricated", "scan_type": "x"},
        ),
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            timestamp=ts,
            indicators={},
            confidence=0.6,
            metadata={"source": "fabricated-2", "scan_type": "x"},
        ),
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            timestamp=ts,
            indicators={},
            confidence=0.6,
            metadata={"source": "fabricated-3", "scan_type": "x"},
        ),
    ]
    ok_signal, details = strength_engine.validate_signal_sources(offenders)
    print(f"validate_signal_sources(offenders)=\n{details}")
    rejected = not ok_signal and details.get("reason") == "unknown_source"
    sys.exit(0 if rejected else 1)


if __name__ == "__main__":
    sys.exit(main())
