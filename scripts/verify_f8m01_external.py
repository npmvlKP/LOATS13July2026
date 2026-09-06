#!/usr/bin/env python3
"""External verification for F8-M-01 (per-signal unknown-source exclusion).

Runs from a clean process against the installed package (no test suite,
no mocks). Verifies the observable contract end-to-end:

  1. Mixed batch (4 valid + 1 unknown) validates; offender excluded and
     reported in ``excluded_unknown_sources``.
  2. Mixed batch (3 valid + 1 unknown) fails a CMP gate with the
     exclusion recorded (no batch-fatal unknown_source veto).
  3. All-unknown batch rejects loudly with the complete offender list.
  4. Empty batch is a count failure, not an unknown-source one.
  5. Composite strength / diversity / breakdown exclude unknown sources
     without raising (the downstream landmine is defused).
  6. The production decision path stamps ``excluded_unknown_sources``
     into decision metadata (static wiring check).
  7. The validator logs a loud per-offender warning (F8-M-01 tagged).
  8. Trade decision workflow applies the exclusion before direction
     selection (an unknown-source signal can never drive a decision).

Exit 0 iff all checks pass.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "verify_dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "verify_dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")

import loats.strength as strength_mod
from loats.strength import (
    StrengthEngine,
    exclude_unknown_source_signals,
)

_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _CHECKS.append((name, bool(cond), detail))


class _Sig:
    """Minimal Signal stand-in."""

    def __init__(self, source: str, strength: float = 0.75):
        self.metadata = {"source": source, "scan_type": "probe"}
        self.strength = strength
        self.signal_type = "BUY"
        self.indicators: dict[str, float] = {}
        self.symbol = "NIFTY"


def main() -> int:
    engine = StrengthEngine()

    def sigs(srcs: list[str]) -> list[_Sig]:
        return [_Sig(s) for s in srcs]

    # 1. Mixed batch validates with exclusion recorded.
    ok, d = engine.validate_signal_sources(
        sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
    )
    check(
        "1_mixed_batch_validates_excluding_offender",
        ok is True
        and d.get("excluded_unknown_sources") == ["stray"]
        and "stray" not in d.get("sources", []),
        f"ok={ok} d={d}",
    )

    # 2. 3 valid + 1 unknown -> CMP gate failure with exclusion, no veto.
    ok, d = engine.validate_signal_sources(
        sigs(["ta", "sentiment", "price_action", "stray"])
    )
    check(
        "2_mixed_batch_gate_failure_records_exclusion",
        ok is False
        and d.get("reason") == "insufficient_source_diversity"
        and d.get("excluded_unknown_sources") == ["stray"],
        f"ok={ok} reason={d.get('reason')}",
    )

    # 3. All-unknown batch -> loud unknown_source with full offender list.
    ok, d = engine.validate_signal_sources(sigs(["ghost", "ghost2"]))
    check(
        "3_all_unknown_loud_rejection",
        ok is False
        and d.get("reason") == "unknown_source"
        and sorted(d.get("offenders", [])) == ["ghost", "ghost2"],
        f"ok={ok} reason={d.get('reason')} offenders={d.get('offenders')}",
    )

    # 4. Empty batch -> insufficient_unique_sources.
    ok, d = engine.validate_signal_sources([])
    check(
        "4_empty_batch_count_failure",
        ok is False and d.get("reason") == "insufficient_unique_sources",
        f"reason={d.get('reason')}",
    )

    # 5. Downstream engines exclude unknown sources without raising.
    try:
        cs, cd = engine.calculate_composite_strength(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        composite_ok = cs > 0.0 and cd.get("excluded_unknown_sources") == ["stray"]
    except ValueError as e:
        composite_ok = False
        cd = {"error": str(e)}
    check("5a_composite_survives_unknown", composite_ok, f"{cd}")

    try:
        div = engine.calculate_strength_diversity(
            {"stray": [], "ta": [], "sentiment": [], "price_action": []}
        )
        div_ok = 0.0 <= div <= 1.0
    except ValueError as e:
        div_ok = False
        div = f"raised {e}"
    check("5b_diversity_survives_unknown", div_ok, f"score={div}")

    try:
        bd = engine.get_source_strength_breakdown(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        bd_ok = "stray" not in bd["sources"]
    except ValueError as e:
        bd_ok = False
        bd = {"error": str(e)}
    check("5c_breakdown_survives_unknown", bd_ok, f"{bd}")

    # 6. Production decision path wires the exclusion into metadata.
    td_src = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(
        encoding="utf-8"
    )
    check(
        "6a_workflow_excludes_before_validation",
        "exclude_unknown_source_signals(signals)" in td_src
        and "validate_signal_sources(valid_signals)" in td_src,
        "trade_decision.py must filter once at Step 0 and validate the filtered list",
    )
    check(
        "6b_workflow_stamps_exclusion_into_metadata",
        '"excluded_unknown_sources": excluded_unknown' in td_src,
        "decision metadata must carry the authoritative exclusion record",
    )
    check(
        "6c_direction_uses_valid_signals",
        "max(valid_signals" in td_src,
        "unknown-source signal must never set trade direction",
    )

    # 7. Validator warns loudly per offender (F8-M-01 tag).
    strength_src = (REPO_ROOT / "src" / "loats" / "strength.py").read_text(
        encoding="utf-8"
    )
    check(
        "7_loud_per_offender_warning",
        "F8-M-01: excluded signal with unknown source" in strength_src,
        "strength.py must log a tagged warning per offender",
    )

    # 8. Shared primitive is exported and partitions correctly.
    known, unknown = exclude_unknown_source_signals(sigs(["ta", "ghost", "volatility"]))
    check(
        "8_shared_primitive_partitions",
        len(known) == 2
        and unknown == ["ghost"]
        and hasattr(strength_mod, "exclude_unknown_source_signals"),
        f"known={len(known)} unknown={unknown}",
    )

    passed = sum(1 for _, okc, _ in _CHECKS if okc)
    for name, okc, detail in _CHECKS:
        print(f"[{'PASS' if okc else 'FAIL'}] {name} {detail}")
    print(f"VERIFIED: {passed}/{len(_CHECKS)}")
    return 0 if passed == len(_CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
