#!/usr/bin/env python3
"""P5 forward-test run-log validator (F8-H-01 Recommended Test 3).

Grades ``reports/p5_forward_test_*.json`` run logs produced by
``scripts/run_p5_forward_test.py`` against the CMP P5 phase-gate
acceptance criteria from the F8-H-01 finding:

- span of at least 14 days (2 weeks) between ``started_at`` and ``ended_at``
- zero ``unhandled_exceptions``
- routing was enabled for the run (``routing.enabled_at_start`` true)
- measured activity (2026-09-05): when the log carries
  ``cycles_completed``/``counters`` (live supervisor samples), zero total
  activity is a hard FAIL — an idle run measures nothing. Logs without
  those fields (legacy) are graded unchanged.

Verdicts:
- PASS        — all criteria met
- INCOMPLETE  — structurally valid but criteria not yet met or run ongoing
- FAIL        — a completed run that violates a hard criterion (exceptions,
                routing disabled, no measured activity)

Usage:
    python scripts/verify_p5_forward_test.py            # newest run log
    python scripts/verify_p5_forward_test.py <file...>  # specific logs

Exit code 0 iff at least one run log grades PASS (and none FAIL hard).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_SPAN_DAYS = 14  # CMP P5: 2-week forward test

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"


@dataclass
class Grade:
    """Grading result for one run log."""

    verdict: str  # PASS | INCOMPLETE | FAIL
    reasons: list[str] = field(default_factory=list)
    # Measured-activity / freshness signals (set only when the run log
    # carries them — legacy logs grade unchanged).
    activity_recorded: bool | None = None
    data_freshness: str | None = None


def _parse_ts(value: Any) -> datetime.datetime | None:
    """Parse an ISO-8601 timestamp; return None when absent/invalid."""
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.UTC)
    return ts


def _now_utc() -> datetime.datetime:
    """Current UTC time (factored for testability)."""
    return datetime.datetime.now(datetime.UTC)


def grade_run_log(run_log: dict[str, Any]) -> Grade:
    """Grade one P5 run-log dict against the phase-gate criteria."""
    reasons: list[str] = []

    # Structural minimums: a run log without these is not gradeable.
    started = _parse_ts(run_log.get("started_at"))
    if started is None:
        return Grade("FAIL", ["missing or invalid started_at"])
    ended = _parse_ts(run_log.get("ended_at"))

    # Measured-activity / freshness signals (never fabricate: absence keeps
    # legacy logs gradeable, but a PASS without measured activity proves
    # nothing about decisioning, so it does not clear the gate).
    has_activity_fields = "cycles_completed" in run_log and "counters" in run_log
    total_activity = 0
    activity_recorded: bool | None = None
    if has_activity_fields:
        try:
            total_activity = int(run_log.get("cycles_completed", 0) or 0) + sum(
                int(v) for v in (run_log.get("counters") or {}).values()
            )
        except (TypeError, ValueError):
            total_activity = 0
        activity_recorded = total_activity > 0
        if not activity_recorded:
            reasons.append(
                "no measured activity recorded "
                "(cycles_completed and routing counters all zero — "
                "run measures nothing)"
            )

    data_freshness: str | None = None
    last_sampled = _parse_ts(run_log.get("last_sampled_at"))
    if last_sampled is not None:
        ended_or_now = ended if ended is not None else _now_utc()
        data_freshness = f"{(ended_or_now - last_sampled).total_seconds():.0f}s"

    # Hard criterion: routing must have been enabled for the run.
    routing = run_log.get("routing") or {}
    if not routing.get("enabled_at_start"):
        reasons.append("routing was NOT enabled at run start (measures nothing)")

    # Hard criterion: zero unhandled exceptions.
    exceptions = int(run_log.get("unhandled_exceptions", 0) or 0)
    if exceptions > 0:
        reasons.append(f"{exceptions} unhandled exception(s)")

    if ended is None:
        span_days = 0.0
        reasons.append("run still in progress (no ended_at)")
    else:
        span_days = (ended - started).total_seconds() / 86400.0
        if span_days < MIN_SPAN_DAYS:
            reasons.append(f"span {span_days:.2f}d < required {MIN_SPAN_DAYS}d")

    hard_violation = bool(reasons) and (
        exceptions > 0
        or not routing.get("enabled_at_start")
        or activity_recorded is False
    )
    if hard_violation:
        return Grade("FAIL", reasons, activity_recorded, data_freshness)
    if reasons:
        return Grade("INCOMPLETE", reasons, activity_recorded, data_freshness)
    return Grade(
        "PASS",
        [f"span {span_days:.2f}d, 0 exceptions, routing enabled"],
        activity_recorded,
        data_freshness,
    )


def _load(path: Path) -> dict[str, Any] | None:
    """Load a run-log JSON file, returning None on parse failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def main() -> int:
    """CLI entry: grade run logs and exit with conformance status."""
    parser = argparse.ArgumentParser(
        description="P5 forward-test run-log validator (F8-H-01)."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        type=Path,
        help="run-log files (default: newest reports/p5_forward_test_*.json)",
    )
    args = parser.parse_args()

    paths = list(args.logs)
    if not paths:
        candidates = sorted(
            (REPO_ROOT / "reports").glob("p5_forward_test_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            print(f"{FAIL_SYM} no reports/p5_forward_test_*.json run logs found")
            print("  Run scripts/run_p5_forward_test.py to begin the P5 forward test")
            return 1
        paths = [candidates[0]]

    verdicts: list[tuple[Path, Grade]] = []
    for path in paths:
        data = _load(path)
        if data is None:
            print(f"{FAIL_SYM} {path.name}: unreadable or invalid JSON")
            verdicts.append((path, Grade("FAIL", ["unparseable run log"])))
            continue
        grade = grade_run_log(data)
        verdicts.append((path, grade))
        sym = PASS_SYM if grade.verdict == "PASS" else FAIL_SYM
        print(f"{sym} {path.name}: {grade.verdict}")
        if grade.activity_recorded is False:
            print("    - WARN: no measured activity (cycles/counters all zero)")
        if grade.data_freshness is not None:
            print(
                f"    - data freshness: last sample {grade.data_freshness} before end"
            )
        for reason in grade.reasons:
            print(f"    - {reason}")

    any_pass = any(g.verdict == "PASS" for _, g in verdicts)
    any_fail = any(g.verdict == "FAIL" for _, g in verdicts)
    overall = "PASS" if (any_pass and not any_fail) else "NOT-YET-PASSING"
    print(f"\nP5 forward-test conformance: {overall}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
