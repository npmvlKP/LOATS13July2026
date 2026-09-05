#!/usr/bin/env python3
"""P5 forward-test supervisor (F8-H-01).

Runs the real LOATS trading system (``loats.main`` TradingSystem) with
Analyzer routing ENABLED for the CMP P5 2-week forward test, appending
heartbeat run-log records to ``reports/p5_forward_test_<ts>.json`` so
``scripts/verify_p5_forward_test.py`` can grade conformance.

F8-H-01 closing step: the CMP P5 gate requires routing ALL TradeDecisions
to Analyzer mode. This supervisor enables routing ONLY for the duration
of the supervised run — the production default stays OFF (runtime kill
path preserved), per ADR-006.

Safety:
- Requires an explicit operator acknowledgement that a live OpenAlgo
  endpoint is reachable (``--ack-live-endpoint``) or runs with
  ``--dry-run`` (enables routing in-process, issues no HTTP because the
  orchestrator cycle is not started).
- The kill switch (settings + DB) remains active throughout.

Usage:
    python scripts/run_p5_forward_test.py --dry-run          # smoke
    python scripts/run_p5_forward_test.py --ack-live-endpoint  # real run
    python scripts/run_p5_forward_test.py --status            # inspect log
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RUN_LOG_DIR = REPO_ROOT / "reports"
RUN_LOG_GLOB = "p5_forward_test_*.json"
MIN_SPAN_DAYS = 14
# Live-activity sampling cadence for supervised runs: fold real system
# counters into the run log every 60 s so graded evidence is measured,
# never estimated.
_SAMPLE_INTERVAL_S = 60.0

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"


def _load_validator() -> Any | None:
    """Import ``scripts/verify_p5_forward_test.py`` as a module.

    The P5 gate definition lives in one place (the validator's
    ``grade_run_log``); the supervisor reuses it so gate-pass detection
    during a live run can never drift from the official grader.
    """
    cache = getattr(_load_validator, "_module", None)
    if cache is not None:
        return cache
    validator = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
    spec = importlib.util.spec_from_file_location("p5_forward_validator", validator)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _load_validator._module = module  # type: ignore[attr-defined]
    return module


def _grade_current_run(run_log: Path, pretend_ended: bool = False) -> Any | None:
    """Grade the current run-log state; returns a Grade or None.

    With ``pretend_ended=True`` the grade answers "would this run clear the
    gate if it ended now?" — used by the supervisor's gate-stop check, since
    the on-disk log stays ``ended_at: null`` (ongoing) until shutdown.
    """
    validator = _load_validator()
    if validator is None:
        return None
    try:
        data = json.loads(run_log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if pretend_ended and data.get("ended_at") is None:
        data["ended_at"] = _utcnow_iso()
    return validator.grade_run_log(data)


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _find_run_log(path: Path | None) -> Path | None:
    """Return the given path or the newest existing run log."""
    if path is not None:
        return path if path.exists() else None
    candidates = sorted(
        RUN_LOG_DIR.glob(RUN_LOG_GLOB), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _init_run_log(reason: str, dry_run: bool) -> Path:
    """Create a fresh run-log file with the run's initial state."""
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    path = RUN_LOG_DIR / f"p5_forward_test_{stamp}.json"
    record: dict[str, Any] = {
        "metadata": {
            "phase_gate": "P5",
            "finding": "F8-H-01",
            "reason": reason,
            "dry_run": dry_run,
            "script": "scripts/run_p5_forward_test.py",
        },
        "routing": {
            "enabled_at_start": True,  # supervisor always enables routing
            "env_flag_default": False,
            "note": (
                "production default remains OFF (ADR-006); routing enabled "
                "only for the supervised P5 run via enable_analyzer_routing()"
            ),
        },
        "started_at": _utcnow_iso(),
        "ended_at": None,
        "unhandled_exceptions": 0,
        "restarts": 0,
        # cycles_completed/counters are LIVE samples (orchestrator cycle
        # count, TradeDecisionEngine routing outcomes) folded in by the
        # supervised loop — never estimates. Baselines are captured at run
        # start so the deltas measure only this run's activity.
        "cycles_completed": 0,
        "cycles_completed_baseline": None,
        "counters": {"success": 0, "disabled": 0, "error": 0},
        "counters_baseline": None,
        "events": [],
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def _update_run_log(path: Path, mutate: dict[str, Any]) -> None:
    """Atomically merge ``mutate`` into the run log JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update(mutate)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_event(path: Path, kind: str, detail: str) -> None:
    """Append a timestamped event to the run log."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    events = data.setdefault("events", [])
    events.append({"timestamp": _utcnow_iso(), "kind": kind, "detail": detail})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _capture_live_baseline(system: Any) -> dict[str, Any]:
    """Read the live counter baselines before the supervised window starts.

    Deltas against these baselines measure only THIS run's activity; the
    process may have been importing/initializing long before started_at.
    """
    from loats.orchestrator import orchestrator
    from loats.trade_decision import trade_decision_engine

    return {
        "cycles_completed": orchestrator.cycle_count,
        "counters": trade_decision_engine.get_routing_stats(),
    }


def _effective_resume_baseline(
    raw: dict[str, Any], logged_cycles: int, logged_counters: dict[str, int]
) -> dict[str, Any]:
    """Shift a fresh process's live counters so a resumed run log continues
    from where the previous process's last sample left off.

    Per key: baseline = max(live_now - logged, 0). When live >= logged the
    log continues seamlessly (deltas keep accumulating); when a counter
    RESET happened across the restart (live < logged) the baseline floors
    at the live value, so only post-resume activity is counted — a drop in
    the log, never inflation.
    """
    live_counters = raw["counters"]
    return {
        "cycles_completed": max(int(raw["cycles_completed"]) - int(logged_cycles), 0),
        "counters": {
            key: max(
                int(live_counters.get(key, 0)) - int(logged_counters.get(key, 0)),
                0,
            )
            for key in ("success", "disabled", "error")
        },
    }


def _resolve_resume_target(path: Path | None) -> Path | None:
    """Validate an explicit resume target, or find the newest eligible one.

    Eligible = structurally readable run log, dry_run false, still ongoing
    (``ended_at`` null). Prints the reason and returns None when nothing is
    resumable — resuming a dry-run or an ended run would fabricate a span.
    """
    candidates: list[Path]
    if path is not None:
        candidates = [path]
    else:
        candidates = sorted(
            RUN_LOG_DIR.glob(RUN_LOG_GLOB),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    for candidate in candidates:
        if not candidate.exists():
            if path is not None:
                print(
                    f"{FAIL_SYM} resume target not found: {candidate}", file=sys.stderr
                )
                return None
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if path is not None:
                print(
                    f"{FAIL_SYM} resume target unreadable: {candidate}", file=sys.stderr
                )
                return None
            continue
        metadata = data.get("metadata") or {}
        if metadata.get("dry_run"):
            if path is not None:
                print(
                    f"{FAIL_SYM} {candidate.name}: dry-run log — nothing to resume",
                    file=sys.stderr,
                )
                return None
            continue
        if data.get("ended_at") is not None:
            if path is not None:
                print(
                    f"{FAIL_SYM} {candidate.name}: run already ended — "
                    "start a new run instead",
                    file=sys.stderr,
                )
                return None
            continue
        return candidate
    if path is None:
        print(
            f"{FAIL_SYM} no resumable run log (dry_run=false, ended_at=null) "
            f"under {RUN_LOG_DIR}",
            file=sys.stderr,
        )
    return None


def _sample_live_activity(system: Any, run_log: Path, baseline: dict[str, Any]) -> None:
    """Fold live system counters into the run log (deltas over baseline).

    Sources (read-only, never fabricated):
    - ``orchestrator.cycle_count``  → ``cycles_completed`` delta
    - ``trade_decision_engine.get_routing_stats()`` → ``counters`` delta
    - ``system.running`` / kill switch state → ``system_healthy`` sample
    """
    from loats.alerts import alerts
    from loats.orchestrator import orchestrator
    from loats.trade_decision import trade_decision_engine

    live_cycles = max(0, orchestrator.cycle_count - baseline["cycles_completed"])
    live_counters = trade_decision_engine.get_routing_stats()
    base_counters = baseline["counters"]
    deltas = {
        key: max(0, int(live_counters.get(key, 0)) - int(base_counters.get(key, 0)))
        for key in ("success", "disabled", "error")
    }
    _update_run_log(
        run_log,
        {
            "cycles_completed": live_cycles,
            "counters": deltas,
            "last_sampled_at": _utcnow_iso(),
            "system_healthy": {
                "system_running": bool(system.running),
                "kill_switch_active": alerts.is_kill_switch_active(),
            },
        },
    )


async def _supervise_live(
    system: Any,
    run_log: Path,
    baseline: dict[str, Any],
    duration: float | None,
    task: asyncio.Task[None] | None,
) -> int:
    """Sample live activity until the duration expires, the system task
    ends, or the P5 gate (per the official validator) is satisfied.

    Returns the number of unhandled exceptions observed while supervising.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration if duration is not None else None
    unhandled = 0
    while True:
        _sample_live_activity(system, run_log, baseline)
        grade = _grade_current_run(run_log, pretend_ended=True)
        if grade is not None and grade.verdict == "PASS":
            _append_event(
                run_log,
                "gate_pass_detected",
                "verify_p5_forward_test.grade_run_log verdict=PASS "
                f"(span >= {MIN_SPAN_DAYS}d, 0 exceptions, routing enabled)",
            )
            print(
                f"{PASS_SYM} P5 gate satisfied (>= {MIN_SPAN_DAYS}d span, "
                "0 exceptions, routing enabled); ending supervised run"
            )
            break
        now = loop.time()
        if deadline is not None and now >= deadline:
            break
        if task is not None and task.done():
            if not task.cancelled() and task.exception() is not None:
                exc = task.exception()
                unhandled += 1
                _append_event(
                    run_log,
                    "unhandled_exception",
                    f"system task ended: {type(exc).__name__}: {exc}",
                )
                print(f"{FAIL_SYM} system task ended: {exc}", file=sys.stderr)
            break
        delay = _SAMPLE_INTERVAL_S
        if deadline is not None:
            delay = min(delay, max(0.0, deadline - now))
        if task is not None:
            # Wake on whichever comes first: the sample interval or the
            # system task completing. asyncio.wait never cancels ``task``.
            await asyncio.wait({task}, timeout=delay)
        else:
            await asyncio.sleep(delay)
    return unhandled


async def _run(
    dry_run: bool, reason: str, duration: float | None, resume_log: Path | None = None
) -> int:
    """Supervise one P5 forward-test run with routing enabled.

    With ``resume_log`` set, continue that ongoing run log in this fresh
    process instead of starting a new one — the 14-day span must survive
    host restarts. Counter continuity is guaranteed by
    ``_effective_resume_baseline`` (continues seamlessly, never inflates).
    """
    from loats.trade_decision import trade_decision_engine

    resumed = resume_log is not None and not dry_run
    if resumed:
        assert resume_log is not None
        run_log = resume_log
        print(f"[P5] resuming run log: {run_log}")
    else:
        run_log = _init_run_log(reason, dry_run)
        print(f"[P5] run log: {run_log}")
    print(f"[P5] dry_run={dry_run} duration={duration or 'until stopped'}")

    unhandled = 0
    task: asyncio.Task[None] | None = None
    system = None
    baseline: dict[str, Any] | None = None

    try:
        if dry_run:
            # Smoke path: enable routing in-process, exercise the disabled
            # -> enabled transition and the run-log writer, no orchestrator
            # cycle, no HTTP.
            trade_decision_engine.enable_analyzer_routing()
            assert trade_decision_engine.analyzer_routing_enabled is True
            _append_event(run_log, "routing_enabled", "dry-run smoke")
            await asyncio.sleep(0)
            print(
                "[P5] dry-run complete: routing enable path exercised, "
                "run log initialized"
            )
        else:
            from loats.main import TradingSystem

            system = TradingSystem()
            await system.initialize()
            # Enable routing for the supervised run (default stays OFF).
            trade_decision_engine.enable_analyzer_routing()
            if resumed:
                _append_event(
                    run_log, "routing_enabled", "live supervised run (resumed)"
                )
                prior = json.loads(run_log.read_text(encoding="utf-8"))
                logged_cycles = int(prior.get("cycles_completed") or 0)
                logged_counters_raw = prior.get("counters") or {}
                logged_counters = {
                    key: int(logged_counters_raw.get(key) or 0)
                    for key in ("success", "disabled", "error")
                }
                prior_restarts = int(prior.get("restarts") or 0)
                baseline = _effective_resume_baseline(
                    _capture_live_baseline(system),
                    logged_cycles,
                    logged_counters,
                )
                _update_run_log(
                    run_log,
                    {
                        "restarts": prior_restarts + 1,
                        "cycles_completed_baseline": baseline["cycles_completed"],
                        "counters_baseline": dict(baseline["counters"]),
                        "last_sampled_at": _utcnow_iso(),
                    },
                )
            else:
                _append_event(run_log, "routing_enabled", "live supervised run")
                baseline = _capture_live_baseline(system)
                _update_run_log(
                    run_log,
                    {
                        "cycles_completed_baseline": baseline["cycles_completed"],
                        "counters_baseline": dict(baseline["counters"]),
                    },
                )
            task = asyncio.create_task(system.start())
            unhandled += await _supervise_live(
                system, run_log, baseline, duration, task
            )
    except (KeyboardInterrupt, asyncio.CancelledError):
        _append_event(run_log, "interrupted", "operator interrupt")
    except Exception as exc:
        unhandled += 1
        _append_event(run_log, "unhandled_exception", f"{type(exc).__name__}: {exc}")
        print(f"{FAIL_SYM} unhandled exception: {exc}", file=sys.stderr)
    finally:
        if system is not None:
            try:
                await system.shutdown()
            except Exception as exc:
                unhandled += 1
                _append_event(run_log, "shutdown_error", f"{type(exc).__name__}: {exc}")
        if task is not None and not task.done():
            task.cancel()
        if system is not None and baseline is not None:
            # Final sample so the ended run log carries the last measured
            # activity state, not the previous interval's.
            try:
                _sample_live_activity(system, run_log, baseline)
            except Exception:
                pass
        try:
            trade_decision_engine.disable_analyzer_routing()
        except Exception:
            pass
        _update_run_log(
            run_log,
            {
                "ended_at": _utcnow_iso(),
                "unhandled_exceptions": unhandled,
            },
        )
        print("[P5] run ended; grading with scripts/verify_p5_forward_test.py")

    return 0 if unhandled == 0 else 1


def _status(path: Path | None) -> int:
    """Print the current state of the newest (or given) run log."""
    run_log = _find_run_log(path)
    if run_log is None:
        print("no P5 run log found (reports/p5_forward_test_*.json)")
        return 1
    data = json.loads(run_log.read_text(encoding="utf-8"))
    started = data.get("started_at")
    ended = data.get("ended_at")
    span = ""
    if started:
        s = datetime.datetime.fromisoformat(started)
        e = (
            datetime.datetime.fromisoformat(ended)
            if ended
            else datetime.datetime.now(datetime.UTC)
        )
        if e.tzinfo is None:
            e = e.replace(tzinfo=datetime.UTC)
        if s.tzinfo is None:
            s = s.replace(tzinfo=datetime.UTC)
        span = f"{(e - s).total_seconds() / 86400:.2f}d"
    print(f"run log   : {run_log}")
    print(f"started_at: {started}")
    ended_or_now = (
        datetime.datetime.fromisoformat(ended)
        if ended
        else datetime.datetime.now(datetime.UTC)
    )
    counters = data.get("counters") or {}
    cycles = data.get("cycles_completed")
    activity = (
        cycles + sum(int(v) for v in counters.values()) if cycles is not None else None
    )
    if activity is not None:
        sampled = data.get("last_sampled_at")
        freshness = ""
        if sampled:
            s = datetime.datetime.fromisoformat(sampled)
            if s.tzinfo is None:
                s = s.replace(tzinfo=datetime.UTC)
            if ended_or_now.tzinfo is None:
                ended_or_now = ended_or_now.replace(tzinfo=datetime.UTC)
            freshness = (
                f", last sample {(ended_or_now - s).total_seconds():.0f}s before end"
            )
        print(
            f"activity  : {activity} measured (cycles={cycles}, "
            f"counters={counters}{freshness})"
        )
    else:
        print("activity  : none recorded (legacy log — no live sampling)")
    process = "ongoing" if not ended else "ended"
    print(f"ended_at  : {ended or '(ongoing)'} [{process}]")
    print(f"span      : {span} (required >= {MIN_SPAN_DAYS}d)")
    print(f"exceptions: {data.get('unhandled_exceptions')}")
    print(f"counters  : {counters}")
    grade = _grade_current_run(run_log)
    print(f"verdict   : {grade.verdict if grade is not None else 'ungradeable'}")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="P5 forward-test supervisor (F8-H-01)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="smoke test: exercise routing enable + run-log init, no HTTP",
    )
    mode.add_argument(
        "--ack-live-endpoint",
        action="store_true",
        help=(
            "acknowledge a reachable OpenAlgo Analyzer endpoint; starts the "
            "real supervised run (production default stays OFF)"
        ),
    )
    mode.add_argument("--status", action="store_true", help="inspect run log")
    mode.add_argument(
        "--resume",
        action="store_true",
        help=(
            "resume the newest ongoing live run (or the --run-log target) in "
            "this process — survives host restarts without breaking the "
            "14-day span; refused for dry-run or ended logs"
        ),
    )
    parser.add_argument(
        "--run-log",
        type=Path,
        default=None,
        help="explicit run-log path (default: newest under reports/)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="supervise for N seconds then stop (testing)",
    )
    parser.add_argument(
        "--reason", default="F8-H-01 P5 forward test", help="run-log reason"
    )
    args = parser.parse_args()

    if args.status:
        return _status(args.run_log)

    if args.dry_run:
        return asyncio.run(_run(dry_run=True, reason=args.reason, duration=None))

    if args.resume:
        target = _resolve_resume_target(args.run_log)
        if target is None:
            return 2
        return asyncio.run(
            _run(
                dry_run=False,
                reason=args.reason,
                duration=args.duration,
                resume_log=target,
            )
        )

    if not args.ack_live_endpoint:
        print(
            f"{FAIL_SYM} live run requires --ack-live-endpoint "
            "(operator confirms reachable Analyzer endpoint)",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run(dry_run=False, reason=args.reason, duration=args.duration))


if __name__ == "__main__":
    # Exit-code contract (2026-09-05): main()'s return value is the process
    # exit code. Previously the bare main() call discarded it, so a failed
    # live run (unhandled exceptions) exited 0 — invisible to Task
    # Scheduler / CI / any wrapper scripting on the outcome.
    sys.exit(main())
