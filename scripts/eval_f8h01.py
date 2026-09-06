#!/usr/bin/env python3
"""F8-H-01 conformance eval: 10 cases, before/after score.

Grades the analyzer-routing deviation state (CMP P5) against the finding's
Recommended Tests plus the latent defects discovered in its blast radius:

  1. Routing disabled by default (settings).
  2. Disabled path: deterministic response, NO HTTP call.
  3. Disabled path: decision persisted (async_create_trade_decision).
  4. Disabled path: ROUTE audit row with routing outcome exists.   [was broken]
  5. Enabled path: real HTTP fires, success, decision persisted.
  6. Enabled path: ROUTE audit row with routing outcome.           [was broken]
  7. Error path: propagates AND error outcome audited.             [was broken]
  8. get_decision_status: real DB state, NOT_FOUND when absent.    [was fabricated]
  9. P5 forward-test run-log validator exists + grades fixtures.   [was missing]
 10. Deviation recorded (ADR-006 + README).                        [was missing]

Usage:  python scripts/eval_f8h01.py --phase before|after
Exit 0 iff 10/10 (informational for 'before').
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OPENALGO_API_KEY", "test_api_key")
os.environ.setdefault("OPENALGO_BASE_URL", "https://test.openalgo.com")

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, note: str = "") -> None:
    results.append((name, ok, note))
    print(f"{PASS_SYM if ok else FAIL_SYM} {name}" + (f"  -- {note}" if note else ""))


def make_decision():
    """Build a minimal TradeDecision for routing probes."""
    from loats.models import SignalType, TradeDecision

    return TradeDecision(
        symbol="NIFTY",
        decision_type=SignalType.BUY,
        composite_strength=0.7,
        timestamp=datetime.datetime(2026, 9, 1, 9, 30, tzinfo=datetime.UTC),
        entry_price=18000.0,
        quantity=25,
        stop_loss=17820.0,
        position_size_method="fixed_fraction",
        risk_percentage=0.02,
        var_analysis={"var_value": 0.0, "var_percent": 0.0, "method": "parametric"},
    )


def case_1_default_off() -> None:
    src = (REPO_ROOT / "src" / "loats" / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    ok = False
    for node in ast.walk(ast.parse(src)):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "analyzer_routing_enabled"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "Field"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and node.value.args[0].value is False
        ):
            ok = True
    record("1 default OFF in settings", ok)


async def case_2_disabled_no_http() -> None:
    from loats.trade_decision import TradeDecisionEngine

    class Bomb:
        def __call__(self, *a, **k):
            raise AssertionError("HTTP client constructed while routing disabled")

    engine = TradeDecisionEngine(maxsize=2)
    with (
        patch.object(engine, "analyzer_routing_enabled", False),
        patch("loats.trade_decision.AsyncOpenAlgoClient", Bomb()),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=True),
        ),
        patch("loats.database.db.async_log_audit", AsyncMock()),
    ):
        resp = await engine.route_to_analyzer(make_decision())
    ok = resp.get("status") == "disabled" and resp.get("reason") == (
        "analyzer_routing_disabled"
    )
    record("2 disabled: deterministic response, no HTTP", ok, str(resp.get("status")))


async def case_3_disabled_persists_decision() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    created = AsyncMock(return_value=True)
    with (
        patch.object(engine, "analyzer_routing_enabled", False),
        patch("loats.database.db.async_create_trade_decision", created),
        patch("loats.database.db.async_log_audit", AsyncMock()),
    ):
        await engine.route_to_analyzer(make_decision())
    record("3 disabled: decision persisted", created.await_count == 1)


async def case_4_disabled_audit_outcome() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    audit = AsyncMock()
    with (
        patch.object(engine, "analyzer_routing_enabled", False),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=True),
        ),
        patch("loats.database.db.async_log_audit", audit),
    ):
        resp = await engine.route_to_analyzer(make_decision())
    ok = False
    note = f"audit calls={audit.await_count}"
    if audit.await_count and audit.await_args is not None:
        kw = audit.await_args.kwargs
        meta = kw.get("metadata") or {}
        outcome = meta.get("routing_outcome") or {}
        ok = (
            kw.get("action", "").startswith("ROUTE")
            and outcome.get("status") == resp.get("status") == "disabled"
        )
        note += f" action={kw.get('action')}"
    record("4 disabled: ROUTE audit row w/ outcome", ok, note)


async def case_5_enabled_http() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    seen: list[dict] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def place_analyzer_request(self, payload):
            seen.append(payload)
            return {"status": "accepted", "analyzer_id": "p5-eval"}

    created = AsyncMock(return_value=True)
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.trade_decision.AsyncOpenAlgoClient", FakeClient),
        patch("loats.database.db.async_create_trade_decision", created),
        patch("loats.database.db.async_log_audit", AsyncMock()),
    ):
        resp = await engine.route_to_analyzer(make_decision())
    ok = (
        len(seen) == 1
        and resp.get("status") == "success"
        and resp.get("analyzer_response")
        == {"status": "accepted", "analyzer_id": "p5-eval"}
        and created.await_count == 1
    )
    record("5 enabled: real HTTP + persisted", ok, f"http_calls={len(seen)}")


async def case_6_enabled_audit_outcome() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def place_analyzer_request(self, payload):
            return {"status": "accepted"}

    audit = AsyncMock()
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.trade_decision.AsyncOpenAlgoClient", FakeClient),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=True),
        ),
        patch("loats.database.db.async_log_audit", audit),
    ):
        resp = await engine.route_to_analyzer(make_decision())
    ok = False
    note = f"audit calls={audit.await_count}"
    if audit.await_count and audit.await_args is not None:
        kw = audit.await_args.kwargs
        outcome = (kw.get("metadata") or {}).get("routing_outcome") or {}
        ok = kw.get("action", "").startswith("ROUTE") and outcome.get("status") == (
            "success"
        )
        note += f" outcome={outcome.get('status')}"
    record("6 enabled: ROUTE audit row w/ outcome", ok, note)


async def case_7_error_path() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def place_analyzer_request(self, payload):
            raise RuntimeError("eval simulated HTTP failure")

    audit = AsyncMock()
    raised = False
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.trade_decision.AsyncOpenAlgoClient", FailingClient),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=True),
        ),
        patch("loats.database.db.async_log_audit", audit),
    ):
        try:
            await engine.route_to_analyzer(make_decision())
        except RuntimeError:
            raised = True
    ok = False
    note = f"raised={raised} audit={audit.await_count}"
    if raised and audit.await_count and audit.await_args is not None:
        kw = audit.await_args.kwargs
        outcome = (kw.get("metadata") or {}).get("routing_outcome") or {}
        ok = outcome.get("status") == "error" and "eval simulated" in str(
            outcome.get("error", "")
        )
    record("7 error: propagates + audited outcome", ok, note)


async def case_8_status_no_fabrication() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)
    with patch(
        "loats.database.db.async_get_trade_decision", AsyncMock(return_value=None)
    ):
        resp = await engine.get_decision_status("decision_eval_nonexistent")
    ok = resp.get("status") == "NOT_FOUND"
    record(
        "8 status: NOT_FOUND (no fabrication)",
        ok,
        f"status={resp.get('status')}",
    )


def case_9_validator() -> None:
    vpath = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
    if not vpath.exists():
        record("9 P5 run-log validator", False, "script missing")
        return
    import importlib.util

    spec = importlib.util.spec_from_file_location("p5val", vpath)
    if spec is None or spec.loader is None:
        record("9 P5 run-log validator", False, "module spec unavailable")
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    def fixture(span_days: int, exc: int, routing: bool = True) -> dict:
        start = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        end = start + datetime.timedelta(days=span_days)
        return {
            "metadata": {"phase_gate": "P5"},
            "routing": {"enabled_at_start": routing},
            "started_at": start.isoformat(),
            "ended_at": end.isoformat(),
            "unhandled_exceptions": exc,
            "restarts": 0,
            "cycles_completed": 10,
            "counters": {"success": 5, "disabled": 0, "error": 0},
        }

    g1 = mod.grade_run_log(fixture(15, 0))
    g2 = mod.grade_run_log(fixture(1, 0))
    g3 = mod.grade_run_log(fixture(15, 2))
    g4 = mod.grade_run_log(fixture(15, 0, routing=False))
    ok = (
        g1.verdict == "PASS"
        and g2.verdict == "INCOMPLETE"
        and g3.verdict == "FAIL"
        and g4.verdict == "FAIL"
    )
    record(
        "9 P5 run-log validator",
        ok,
        f"{g1.verdict}/{g2.verdict}/{g3.verdict}/{g4.verdict}",
    )


def case_10_docs() -> None:
    adr = REPO_ROOT / "docs" / "ADR-006-analyzer-routing-p5.md"
    readme = REPO_ROOT / "README.md"
    ok = adr.exists() and "F8-H-01" in adr.read_text(encoding="utf-8")
    ok = ok and "F8-H-01" in readme.read_text(encoding="utf-8")
    record("10 deviation recorded (ADR-006 + README)", ok)


async def main_async(phase: str) -> None:
    print(f"F8-H-01 eval -- phase={phase}")
    print("=" * 60)
    case_1_default_off()
    await case_2_disabled_no_http()
    await case_3_disabled_persists_decision()
    await case_4_disabled_audit_outcome()
    await case_5_enabled_http()
    await case_6_enabled_audit_outcome()
    await case_7_error_path()
    await case_8_status_no_fabrication()
    case_9_validator()
    case_10_docs()
    passed = sum(1 for _, ok, _ in results if ok)
    print("=" * 60)
    print(f"RESULT: {passed}/{len(results)} ({phase})")
    out = REPO_ROOT / "reports" / f"eval_f8h01_{phase}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase,
        "passed": passed,
        "total": len(results),
        "cases": [{"name": n, "pass": ok, "note": note} for n, ok, note in results],
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["before", "after"], default="before")
    args = parser.parse_args()
    import asyncio

    asyncio.run(main_async(args.phase))
    passed = sum(1 for _, ok, _ in results if ok)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
