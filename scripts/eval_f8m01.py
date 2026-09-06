#!/usr/bin/env python3
"""Eval for F8-M-01: 10-case behavioural matrix.

BEFORE baseline is re-derived live from the pre-fix git tree
(scripts/derive_f8m01_before.py) — 3/10 (documented floor: C3 loud
all-unknown rejection, C6 empty-batch semantics, C10 gate math all
pre-date this fix).

AFTER is measured live on the current tree below. Exit 0 when AFTER
scores 10/10 (i.e. >= BEFORE + 7). Each case scores the live code path
it names — no source-string shortcuts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "eval_dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "eval_dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")

from loats.strength import StrengthEngine, StrengthSource

_CASES: dict[str, bool] = {
    "C1_mixed_batch_passes": False,
    "C2_mixed_batch_gate_failure_records_exclusion": False,
    "C3_all_unknown_loud_rejection": False,
    "C4_pass_details_report_exclusion": False,
    "C5_offender_not_in_sources": False,
    "C6_empty_batch_count_failure": False,
    "C7_composite_survives_unknown": False,
    "C8_breakdown_survives_unknown": False,
    "C9_diversity_survives_unknown": False,
    "C10_gate_math_unchanged": False,
}


class _Sig:
    """Minimal Signal stand-in (metadata + strength + signal_type)."""

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

    # C1: mixed batch (4 valid + 1 unknown) passes validation.
    ok, d = engine.validate_signal_sources(
        sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
    )
    _CASES["C1_mixed_batch_passes"] = ok is True

    # C2: mixed batch (3 valid + 1 unknown) fails on a CMP gate with the
    # exclusion recorded (not unknown_source).
    ok, d = engine.validate_signal_sources(
        sigs(["ta", "sentiment", "price_action", "stray"])
    )
    _CASES["C2_mixed_batch_gate_failure_records_exclusion"] = (
        ok is False
        and d.get("reason") == "insufficient_source_diversity"
        and d.get("excluded_unknown_sources") == ["stray"]
    )

    # C3: all-unknown batch rejects loudly with the complete offender
    # list, in deterministic (input) order post-fix.
    ok, d = engine.validate_signal_sources(sigs(["ghost", "ghost2"]))
    _CASES["C3_all_unknown_loud_rejection"] = (
        ok is False
        and d.get("reason") == "unknown_source"
        and d.get("offenders") == ["ghost", "ghost2"]
    )

    # C4: exclusion is reported in the passing details.
    ok, d = engine.validate_signal_sources(
        sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
    )
    _CASES["C4_pass_details_report_exclusion"] = ok is True and d.get(
        "excluded_unknown_sources"
    ) == ["stray"]

    # C5: offender excluded from the validated source set.
    _CASES["C5_offender_not_in_sources"] = ok is True and "stray" not in d.get(
        "sources", []
    )

    # C6: empty batch -> insufficient_unique_sources (not unknown_source).
    ok, d = engine.validate_signal_sources([])
    _CASES["C6_empty_batch_count_failure"] = (
        ok is False and d.get("reason") == "insufficient_unique_sources"
    )

    # C7: composite strength excludes unknown sources (no ValueError).
    cs, d = engine.calculate_composite_strength(
        sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
    )
    _CASES["C7_composite_survives_unknown"] = cs > 0.0 and d.get(
        "excluded_unknown_sources"
    ) == ["stray"]

    # C8: breakdown excludes unknown sources (no ValueError).
    bd = engine.get_source_strength_breakdown(
        sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
    )
    _CASES["C8_breakdown_survives_unknown"] = "stray" not in bd["sources"]

    # C9: diversity calculation excludes unknown sources (no ValueError).
    score = engine.calculate_strength_diversity(
        {"stray": [], "ta": [], "sentiment": [], "price_action": []}
    )
    _CASES["C9_diversity_survives_unknown"] = 0.0 <= score <= 1.0

    # C10: gate math unchanged (3 distinct -> diversity failure, 4 -> pass),
    # and the production 4-source emission set still passes.
    ok3, d3 = engine.validate_signal_sources(sigs(["ta", "sentiment", "price_action"]))
    ok4, _ = engine.validate_signal_sources(sigs([s.value for s in StrengthSource][:4]))
    _CASES["C10_gate_math_unchanged"] = (
        ok3 is False
        and ok4 is True
        and d3.get("reason") == "insufficient_source_diversity"
    )

    passed = sum(1 for v in _CASES.values() if v)
    for name, ok_case in _CASES.items():
        print(f"{name}:{int(ok_case)}")
    print(f"SCORE:{passed}/10")
    return 0 if passed == 10 else 1


if __name__ == "__main__":
    sys.exit(main())
