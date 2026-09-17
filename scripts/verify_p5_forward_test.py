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
    # F9-C-02 follow-up (2026-09-17): documented-outage disclosures.
    # Annotations are NON-GRADING: they never enter ``reasons``, so they
    # cannot flip a verdict -- an otherwise eligible run still PASSes
    # (with disclosure), a contaminated run still FAILs. The 30Sep
    # grading checkpoint reads these via the validator CLI's NOTE lines.
    annotations: tuple[str, ...] = ()


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


def _grade_divergence_evidence(
    run_log: dict[str, Any],
    reasons: list[str],
    started: datetime.datetime,
    ended: datetime.datetime | None,
) -> int:
    """Grade the DB-derived divergence evidence field (F9-C-02).

    Returns the effective divergence count: > 0 = proven divergence
    inside the span (hard FAIL), 0 = verifiably clean or absent,
    < 0 = present but unverifiable (can never grade PASS).
    Appends the corresponding reasons.
    """
    divergence = run_log.get("disabled_routes_during_enabled_window")
    effective = 0
    window: dict[str, Any] = {}
    if "disabled_routes_during_enabled_window" in run_log and not isinstance(
        divergence, dict
    ):
        reasons.append(
            "divergence evidence could not be verified (malformed "
            "disabled_routes_during_enabled_window) -- run cannot grade "
            "PASS on unverified evidence"
        )
        return -1
    if not isinstance(divergence, dict):
        return 0
    raw_count = divergence.get("count")
    if isinstance(raw_count, bool) or not isinstance(raw_count, (int, float)):
        reasons.append(
            "divergence evidence could not be verified (missing or "
            "non-numeric count) -- run cannot grade PASS on unverified "
            "evidence"
        )
        effective = -1
    else:
        effective = int(raw_count)
    raw_window = divergence.get("window")
    window = raw_window if isinstance(raw_window, dict) else {}
    if effective > 0:
        first_at = _parse_ts(window.get("first_disabled_route_at"))
        last_at = _parse_ts(window.get("last_disabled_route_at"))
        if first_at is None and last_at is None:
            # A claimed divergence with NO verifiable window bounds
            # cannot be dismissed as out-of-span.
            reasons.append(
                "divergence evidence could not be verified (count without "
                "parseable window stamps)"
            )
            effective = -1
        else:
            span_end = ended if ended is not None else _now_utc()
            # Partial stamps: fall back to whichever bound exists -- a
            # missing stamp must not whitelist the window.
            lower = first_at if first_at is not None else last_at
            upper = last_at if last_at is not None else first_at
            assert lower is not None and upper is not None
            if not (lower <= span_end and upper >= started):
                effective = 0
    if effective > 0:
        reasons.append(
            f"ROUTING DIVERGENCE (F9-C-02): {effective} ROUTE row(s) with "
            f"routing_enabled:false inside the claimed-enabled span "
            f"({window.get('first_disabled_route_at', '?')} .. "
            f"{window.get('last_disabled_route_at', '?')}) -- evidence for "
            "this run is VOID"
        )
    if effective < 0 and not any("could not be verified" in r for r in reasons):
        reasons.append(
            "divergence evidence could not be verified -- run cannot grade "
            "PASS on unverified evidence"
        )
    return effective


def _collect_outage_annotations(
    started: datetime.datetime, span_end: datetime.datetime
) -> list[str]:
    """Return documented-outage disclosures for a run span (F9-C-02).

    Factored out of grade_run_log (C901). Closed windows overlap by the
    standard interval test; open-ended windows (end None = outage still
    live at record time) overlap whenever the window's start precedes
    the span end -- the hole keeps growing until the closing addendum
    pins the end stamp. Never mutates grading state: callers append the
    result to Grade.annotations, NOT reasons.
    """
    notes: list[str] = []
    for out_start_raw, out_end_raw, out_why in DOCUMENTED_OUTAGE_WINDOWS:
        out_start = _parse_ts(out_start_raw)
        if out_start is None:
            continue
        if out_end_raw is None:
            # Open-ended: the outage had no verified end at record time.
            if out_start <= span_end:
                notes.append(
                    f"run span overlaps a documented outage window (open) "
                    f"(from {out_start_raw}, end not yet pinned): {out_why}"
                )
            continue
        out_end = _parse_ts(out_end_raw)
        if out_end is None:
            continue
        if out_start <= span_end and out_end >= started:
            notes.append(
                f"run span overlaps a documented outage window "
                f"({out_start_raw} .. {out_end_raw}): {out_why}"
            )
    return notes


def grade_run_log(run_log: dict[str, Any]) -> Grade:
    """Grade one P5 run-log dict against the phase-gate criteria."""
    reasons: list[str] = []
    # F9-C-02 follow-up (2026-09-17): documented-outage disclosures ride
    # here (NOT in ``reasons``) -- see the DOCUMENTED_OUTAGE_WINDOWS block.
    # Distinct local name: the module-level ``annotations`` is the
    # __future__ feature import, not a list.
    outage_notes: list[str] = []

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
    counters_decisional: int | None = None
    activity_recorded: bool | None = None
    if has_activity_fields:
        try:
            total_activity = int(run_log.get("cycles_completed", 0) or 0) + sum(
                int(v) for v in (run_log.get("counters") or {}).values()
            )
            counters_decisional = sum(
                int(v) for v in (run_log.get("counters") or {}).values()
            )
        except (TypeError, ValueError):
            total_activity = 0
            counters_decisional = 0
        activity_recorded = total_activity > 0
        if not activity_recorded:
            reasons.append(
                "no measured activity recorded "
                "(cycles_completed and routing counters all zero — "
                "run measures nothing)"
            )
        elif counters_decisional == 0:
            # F8-H-01 hard criterion (2026-09-07): cycles alone prove the
            # loop spun, not that the P5 mandate (route ALL TradeDecisions
            # to Analyzer) was exercised. A multi-day run in which the
            # engine never routed a single decision — success, disabled,
            # or error — measures nothing about decisioning and must not
            # grade PASS on cycle counts alone. Legacy logs without a
            # ``counters`` field keep grading unchanged (criterion is
            # None there).
            reasons.append(
                "no decisional activity recorded "
                "(routing counters all zero — no TradeDecision was ever "
                "routed to the Analyzer; cycles alone do not satisfy P5)"
            )

    data_freshness: str | None = None
    last_sampled = _parse_ts(run_log.get("last_sampled_at"))
    if last_sampled is not None:
        ended_or_now = ended if ended is not None else _now_utc()
        data_freshness = f"{(ended_or_now - last_sampled).total_seconds():.0f}s"

    # F9-C-02 (2026-09-15): self-verifying evidence. The supervisor folds
    # ``disabled_routes_during_enabled_window`` (DB-derived, see
    # collect_disabled_route_rows) into the run log; ROUTE rows with
    # ``routing_enabled:false`` INSIDE the claimed-enabled span are the
    # exact divergence that voided the 15Sep P5 evidence. Graded by
    # _grade_divergence_evidence: > 0 proven divergence (hard FAIL),
    # < 0 present-but-unverifiable (can never grade PASS), 0 clean/absent.
    divergence_effective = _grade_divergence_evidence(run_log, reasons, started, ended)

    # F9-C-02 (adversarial hardening): engine-carried divergence flag.
    # The orchestrator cycle loop swallows exceptions, so a divergence
    # that fired mid-cycle survives only in this counter; any positive
    # count voids the run.
    engine_divergences = int(
        (run_log.get("counters") or {}).get("routing_divergence_detected", 0) or 0
    )
    if engine_divergences > 0:
        reasons.append(
            f"ROUTING DIVERGENCE (F9-C-02): routing engine reported "
            f"{engine_divergences} divergence(s) during the run -- evidence "
            "for this run is VOID"
        )

    # Hard criterion: routing must have been enabled for the run.
    routing = run_log.get("routing") or {}
    if not routing.get("enabled_at_start"):
        reasons.append("routing was NOT enabled at run start (measures nothing)")

    # F9-C-02 follow-up (2026-09-17): documented-outage disclosure. A run
    # whose span overlaps a documented outage window carries an
    # annotation (never a reason): the outage degraded DECISIONAL
    # EVIDENCE DENSITY, not routing provenance, so the span is not voided
    # -- but the gate grader must see the hole. This deliberately runs
    # before verdict construction so the note rides on every verdict.
    # See _collect_outage_annotations for the overlap semantics.
    span_end_for_outage = ended if ended is not None else _now_utc()
    outage_notes = _collect_outage_annotations(started, span_end_for_outage)

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

    # F9-C-02 (adversarial hardening): legacy logs carry no divergence
    # evidence field, so they cannot prove their own cleanliness. If
    # their span overlaps a documented contamination window, VOID them.
    legacy_contaminated = False
    if "disabled_routes_during_enabled_window" not in run_log and ended is not None:
        for win_start_raw, win_end_raw in CONTAMINATION_WINDOWS:
            win_start = _parse_ts(win_start_raw)
            win_end = _parse_ts(win_end_raw)
            if win_start is None or win_end is None:
                continue
            if win_start <= ended and win_end >= started:
                legacy_contaminated = True
                reasons.append(
                    f"legacy run span overlaps a documented contamination "
                    f"window ({win_start_raw} .. {win_end_raw}) -- evidence "
                    "for this run is VOID (cannot prove its own cleanliness)"
                )
                break

    hard_violation = bool(reasons) and (
        exceptions > 0
        or not routing.get("enabled_at_start")
        or activity_recorded is False
        # F8-H-01 (2026-09-07): zero decisional routing outcomes fail an
        # ENDED run (a finished 14-day span with no routed decision
        # measured nothing). An ONGOING zero-decision run stays
        # INCOMPLETE — e.g. a run started outside market hours has
        # genuinely produced nothing yet. Legacy logs without
        # ``counters`` keep None here and grade unchanged.
        or (counters_decisional == 0 and ended is not None)
        # F9-C-02 (2026-09-15): DB-proven divergence hard-fails even an
        # otherwise-clean span.
        or divergence_effective > 0
        # Adversarial hardening: an engine-reported divergence voids the
        # run even when the DB probe missed it.
        or engine_divergences > 0
        # Adversarial hardening: legacy logs (no divergence field) that
        # overlap a documented contamination window are VOID.
        or legacy_contaminated
    )
    if hard_violation:
        return Grade(
            "FAIL", reasons, activity_recorded, data_freshness, tuple(outage_notes)
        )
    if reasons:
        return Grade(
            "INCOMPLETE",
            reasons,
            activity_recorded,
            data_freshness,
            tuple(outage_notes),
        )
    return Grade(
        "PASS",
        [f"span {span_days:.2f}d, 0 exceptions, routing enabled"],
        activity_recorded,
        data_freshness,
        tuple(outage_notes),
    )


RUN_LOG_GLOB = "p5_forward_test_*.json"

# F9-C-02 (adversarial hardening): documented evidence-contamination
# windows. Legacy run logs (those carrying no divergence-evidence field)
# whose span overlaps a window are VOID -- they cannot prove their own
# cleanliness and must never be cited as P5 evidence. Extend this tuple
# when a new contamination window is documented in docs/audit-history/.
CONTAMINATION_WINDOWS: tuple[tuple[str, str], ...] = (
    # 15Sep2026 F9-C-02 poisoning (second default-OFF process writing
    # routing_enabled:false ROUTE rows; see
    # docs/audit-history/15Sep2026-F9C02-TODO2-resolution.md).
    ("2026-09-15T01:00:00+00:00", "2026-09-15T05:00:00+00:00"),
)

# F9-C-02 follow-up (2026-09-17): documented OUTAGE windows. Unlike the
# contamination registry, a documented outage is NOT evidence poisoning:
# during the 17Sep OpenAlgo re-auth outage the breaker-protected degraded
# fetch kept routing provenance clean (zero routing_enabled:false ROUTE
# rows, routing_divergence_detected: 0) -- the hole is DECISIONAL
# EVIDENCE DENSITY, not divergence. A run whose span overlaps a window
# here is annotated (Grade.annotations, NOTE lines in the CLI output) so
# the gate grader sees the hole, but the annotation never enters
# ``reasons``: it cannot flip PASS/INCOMPLETE/FAIL. Extend this tuple
# when a new outage is documented in docs/audit-history/, citing the
# dated record in the ``why`` field. An OPEN-ENDED window (end None)
# marks an outage that was still live when documented -- a closing
# addendum to the cited record pins the end stamp once resolved.
DOCUMENTED_OUTAGE_WINDOWS: tuple[tuple[str, str | None, str], ...] = (
    # 17Sep2026 OpenAlgo broker-session loss (operator-side re-auth
    # outage; first observed auth failure 23:31:21Z = 05:01 IST). Still
    # LIVE at record time (last observed auth failure 09:31:23Z = 14:31
    # IST, breaker still open-cycling) -- registered open-ended; the
    # closing addendum pins the end after operator re-auth is verified.
    (
        "2026-09-16T23:31:21+00:00",
        None,
        "17Sep OpenAlgo broker-session loss: breaker-protected degraded "
        "fetch, zero decisional evidence (routing provenance clean); "
        "see docs/audit-history/17Sep2026-p5-openalgo-auth-outage.md",
    ),
)


def collect_disabled_route_rows(
    database: Any,
    since: datetime.datetime,
    until: datetime.datetime,
) -> list[tuple[str, datetime.datetime]]:
    """Reconcile routing evidence from DB ROUTE rows (source of record).

    F9-C-02 remediation 5: the supervisor's in-process counters never
    moved while the shared DB accumulated routing outcomes that
    contradicted the claimed state, because a SECOND default-OFF LOATS
    process was writing ROUTE rows. The DB is the source of record: this
    helper returns every ROUTE audit row with ``routing_enabled:false``
    whose timestamp falls inside ``[since, until]`` as
    ``(entity_id, timestamp)`` tuples.

    ``database`` is any object exposing ``get_audit_log(entity_type=...)``
    (the loats ``Database`` singleton in production, a real temp
    ``Database`` in tests). Rows with unparseable metadata are skipped
    (they cannot prove either state); rows missing a parseable timestamp
    are skipped for the same reason.

    Adversarial hardening: a STORE FAILURE propagates -- swallowing it
    into ``[]`` would be indistinguishable from a clean DB and fold a
    false zero into the run log. The caller (the supervisor's snapshot
    probe) converts the failure into an unverified-evidence record the
    grader treats as INCOMPLETE, never PASS.
    """
    entries = database.get_audit_log(entity_type="trade_decision", limit=10000)
    rows: list[tuple[str, datetime.datetime]] = []
    for entry in entries:
        if entry.action != "ROUTE":
            continue
        ts = entry.timestamp
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.UTC)
        if not (since <= ts <= until):
            continue
        metadata = entry.metadata
        if not isinstance(metadata, dict):
            continue
        if metadata.get("routing_enabled") is False:
            rows.append((entry.entity_id, ts))
    return rows


# A supervised run folds live counters into its run log every
# run_p5_forward_test._SAMPLE_INTERVAL_S (60 s). A live-shape log whose
# last sample is older than this is an abandoned run (supervisor died);
# it still outranks smoke stubs as the evidence carrier, but a fresher
# live run outranks it.
_LIVE_SAMPLE_STALE_S = 1800.0


def _read_log_dict(path: Path) -> dict[str, Any] | None:
    """Read one run-log file; return None when unreadable or not a dict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def select_default_run_log(root: Path | None = None) -> Path | None:
    """Pick the run log that default grading / ``--status`` must surface.

    Single source of default-selection policy (shared with
    run_p5_forward_test.py). Preference order:

    1. a live-shape run log (``dry_run`` false, ``ended_at`` null) with a
       fresh ``last_sampled_at`` — an actively supervised run is always
       the current story;
    2. the newest live-shape log — an abandoned ongoing run (supervisor
       died mid-span) is the evidence carrier and must NOT be shadowed by
       smoke-test stubs that merely have newer mtimes;
    3. the newest readable log of any kind (e.g. an ended supervised run);
    4. the newest file outright, so a corrupt tree still surfaces its
       newest log for grading (the FAIL reason shows the corruption)
       instead of reporting "no logs found".

    Returns None only when no matching file exists at all.
    """
    root = root if root is not None else REPO_ROOT / "reports"
    candidates = sorted(
        root.glob(RUN_LOG_GLOB), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        return None
    live: list[Path] = []
    readable: list[Path] = []
    for path in candidates:
        data = _read_log_dict(path)
        if data is None:
            continue
        readable.append(path)
        metadata = data.get("metadata") or {}
        if not metadata.get("dry_run") and data.get("ended_at") is None:
            live.append(path)
    now = datetime.datetime.now(datetime.UTC)
    for path in live:
        data = _read_log_dict(path)
        sampled = _parse_ts((data or {}).get("last_sampled_at"))
        if sampled is not None and (now - sampled).total_seconds() <= (
            _LIVE_SAMPLE_STALE_S
        ):
            return path
    if live:
        return live[0]
    if readable:
        return readable[0]
    return candidates[0]


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
        selected = select_default_run_log()
        if selected is None:
            print(f"{FAIL_SYM} no reports/{RUN_LOG_GLOB} run logs found")
            print("  Run scripts/run_p5_forward_test.py to begin the P5 forward test")
            return 1
        paths = [selected]

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
        # F9-C-02 follow-up (2026-09-17): documented-outage disclosures.
        # NOTE lines never affect the exit code; the 30Sep grading
        # checkpoint reads them from exactly this output.
        for note in grade.annotations:
            print(f"    - NOTE: {note}")
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
