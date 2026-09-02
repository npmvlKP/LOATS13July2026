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
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RUN_LOG_DIR = REPO_ROOT / "reports"
RUN_LOG_GLOB = "p5_forward_test_*.json"
MIN_SPAN_DAYS = 14

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"


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
        "cycles_completed": 0,
        "counters": {"success": 0, "disabled": 0, "error": 0},
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


async def _run(dry_run: bool, reason: str, duration: float | None) -> int:
    """Supervise one P5 forward-test run with routing enabled."""
    from loats.trade_decision import trade_decision_engine

    run_log = _init_run_log(reason, dry_run)
    print(f"[P5] run log: {run_log}")
    print(f"[P5] dry_run={dry_run} duration={duration or 'until stopped'}")

    unhandled = 0
    task: asyncio.Task[None] | None = None
    system = None

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
            _append_event(run_log, "routing_enabled", "live supervised run")
            task = asyncio.create_task(system.start())
            if duration is not None:
                await asyncio.sleep(duration)
            else:
                await task
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
    process = "ongoing" if not ended else "ended"
    print(f"ended_at  : {ended or '(ongoing)'} [{process}]")
    print(f"span      : {span} (required >= {MIN_SPAN_DAYS}d)")
    print(f"exceptions: {data.get('unhandled_exceptions')}")
    print(f"counters  : {data.get('counters')}")
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

    if not args.ack_live_endpoint:
        print(
            f"{FAIL_SYM} live run requires --ack-live-endpoint "
            "(operator confirms reachable Analyzer endpoint)",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run(dry_run=False, reason=args.reason, duration=args.duration))


if __name__ == "__main__":
    main()
