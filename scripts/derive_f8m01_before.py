#!/usr/bin/env python3
"""Re-derive the F8-M-01 BEFORE baseline from the pre-fix git tree.

Creates a disposable git worktree at the pre-fix HEAD, injects a
self-contained probe script, runs it with the project venv python, and
prints the score.

Exit 0 always (so the caller can treat failure as missing data and fall
back to a documented hard-coded floor).  Prints:
    C1_mixed_batch_passes:0 ...
    SCORE:2/10
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Case-score line emitted by the injected probe: C<digits>_<name>:1 = pass.
_CASE_PASS_RE = re.compile(r"^C\d+_[a-z0-9_]+:1$")

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_REF = "a22d6ca"  # pre-F8-M-01 HEAD (fix/fr7-wave)
PY = os.environ.get("LOATS_PY", REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe")

PROBE_SOURCE = r'''#!/usr/bin/env python3
"""Self-contained probe for the pre-F8-M-01 behaviour."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "before_probe")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "before_probe")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")


def _score(name: str, cond: bool) -> None:
    print(f"{name}:{int(cond)}")


class _Sig:
    """Minimal Signal stand-in (metadata + strength + signal_type)."""

    def __init__(self, source: str, strength: float = 0.75):
        self.metadata = {"source": source, "scan_type": "probe"}
        self.strength = strength
        self.signal_type = "BUY"


def main() -> None:
    from loats.strength import StrengthEngine

    engine = StrengthEngine()

    def sigs(srcs):
        return [_Sig(s) for s in srcs]

    def case(name, fn):
        """Score a case; an exception (the pre-fix landmine) scores 0."""
        try:
            _score(name, fn())
        except Exception:
            _score(name, False)

    # C1: mixed batch (4 valid + 1 unknown) passes validation
    def c1():
        ok, _ = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        return ok is True

    case("C1_mixed_batch_passes", c1)

    # C2: mixed batch (3 valid + 1 unknown) fails on a CMP gate with the
    # exclusion recorded (not unknown_source)
    def c2():
        ok, d = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action", "stray"])
        )
        return (
            ok is False
            and d.get("reason") == "insufficient_source_diversity"
            and d.get("excluded_unknown_sources") == ["stray"]
        )

    case("C2_mixed_batch_gate_failure_records_exclusion", c2)

    # C3: all-unknown batch rejects loudly with the offender list.
    # Order-independent: the pre-fix code collects offenders from a set,
    # so their order is hash-nondeterministic across runs.
    def c3():
        ok, d = engine.validate_signal_sources(sigs(["ghost", "ghost2"]))
        return (
            ok is False
            and d.get("reason") == "unknown_source"
            and sorted(d.get("offenders", [])) == ["ghost", "ghost2"]
        )

    case("C3_all_unknown_loud_rejection", c3)

    # C4: exclusion is reported in the passing details
    def c4():
        ok, d = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        return ok is True and d.get("excluded_unknown_sources") == ["stray"]

    case("C4_pass_details_report_exclusion", c4)

    # C5: offender excluded from the validated source set
    def c5():
        ok, d = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        return ok is True and "stray" not in d.get("sources", [])

    case("C5_offender_not_in_sources", c5)

    # C6: empty batch -> insufficient_unique_sources (not unknown_source)
    def c6():
        ok, d = engine.validate_signal_sources([])
        return ok is False and d.get("reason") == "insufficient_unique_sources"

    case("C6_empty_batch_count_failure", c6)

    # C7: composite strength excludes unknown sources (no ValueError)
    def c7():
        cs, d = engine.calculate_composite_strength(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        return cs > 0.0 and d.get("excluded_unknown_sources") == ["stray"]

    case("C7_composite_survives_unknown", c7)

    # C8: breakdown excludes unknown sources (no ValueError)
    def c8():
        bd = engine.get_source_strength_breakdown(
            sigs(["ta", "sentiment", "price_action", "volatility", "stray"])
        )
        return "stray" not in bd["sources"]

    case("C8_breakdown_survives_unknown", c8)

    # C9: diversity calculation excludes unknown sources (no ValueError)
    def c9():
        score = engine.calculate_strength_diversity(
            {"stray": [], "ta": [], "sentiment": [], "price_action": []}
        )
        return 0.0 <= score <= 1.0

    case("C9_diversity_survives_unknown", c9)

    # C10: gate math unchanged (3 distinct -> diversity failure, 4 -> pass)
    def c10():
        ok3, d3 = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action"])
        )
        ok4, _ = engine.validate_signal_sources(
            sigs(["ta", "sentiment", "price_action", "volatility"])
        )
        return (
            ok3 is False
            and ok4 is True
            and d3.get("reason") == "insufficient_source_diversity"
        )

    case("C10_gate_math_unchanged", c10)


if __name__ == "__main__":
    main()
'''


def _derive_before_score() -> int:
    """Re-derive the pre-fix baseline live from the pre-fix git tree."""
    passed = 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        worktree = Path(td) / "wt"
        proc = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(worktree),
                BASE_REF,
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            return -1
        try:
            probe = worktree / "_before_f8m01_probe.py"
            probe.write_text(PROBE_SOURCE, encoding="utf-8")
            run = subprocess.run(
                [str(PY), str(probe)],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env={
                    **os.environ,
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                },
            )
            print(run.stdout, end="")
            if run.stderr.strip():
                print("--- stderr ---", file=sys.stderr)
                print(run.stderr, file=sys.stderr)
            for line in run.stdout.splitlines():
                # Count only PASSING case-score lines (C<digits>_<name>:1).
                if _CASE_PASS_RE.match(line.strip()):
                    passed += 1
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
    return passed


if __name__ == "__main__":
    score = _derive_before_score()
    print(f"SCORE:{score}/10")
    sys.exit(0)
