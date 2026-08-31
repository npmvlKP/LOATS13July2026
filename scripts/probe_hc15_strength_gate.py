"""HC-15 production probe: strength-gate math.

After the legacy 3/7=0.4286 deadlock fix (see strength.py:294-296),
the current diversity formula is `min(len(source_types)/min_sources, 1.0)`.
3 unique valid sources yield diversity = 3/3 = 1.0 (>= 0.5 threshold -> pass).
4 unique valid sources yield still 1.0 (clipped) -> pass.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loats.models import Signal, SignalType  # noqa: E402
from loats.strength import strength_engine  # noqa: E402


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


def main() -> int:
    sig3 = _build(3)
    sig4 = _build(4)
    ok3, det3 = strength_engine.validate_signal_sources(sig3)
    ok4, det4 = strength_engine.validate_signal_sources(sig4)
    print(f"3 valid sources -> ok={ok3} diversity={det3.get('diversity_score')} reason={det3.get('reason')}")
    print(f"4 valid sources -> ok={ok4} diversity={det4.get('diversity_score')} reason={det4.get('reason')}")
    div3 = det3.get("diversity_score")
    div4 = det4.get("diversity_score")
    score_ok = (
        isinstance(div3, (int, float))
        and isinstance(div4, (int, float))
        and div3 >= 0.5
        and div4 >= 0.5
    )
    print(f"BOTH gate verdicts >=0.5: {score_ok}")
    sys.exit(0 if score_ok else 1)


if __name__ == "__main__":
    sys.exit(main())
