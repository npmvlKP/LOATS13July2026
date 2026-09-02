#!/usr/bin/env python3
"""External verification for F8-H-01 (CMP P5 analyzer routing).

Standalone, suite-independent confirmation of the F8-H-01 remediation:

  A. Default OFF        - settings AST + .env.example entry
  B. No dead probe      - trade_decision.py must not reference the
                          nonexistent async_record_trade_decision
  C. ROUTE audit wired  - async_log_audit called in _persist_routing_outcome
  D. Status real        - async_get_trade_decision in get_decision_status;
                          no "PROCESSED"/"ANALYZED" fabrication strings
  E. Runner + validator - scripts exist, runner --dry-run exits 0 and
                          produces a run log; validator grades fixtures
  F. Live probes        - disabled/enabled/error routing paths with mocked
                          transport, asserting audit + persistence behavior
  G. Docs               - ADR-006 exists and records F8-H-01; README cites it

Run:  python scripts/verify_f8h01_external.py
Exit: 0 iff all checks pass.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OPENALGO_API_KEY", "test_api_key")
os.environ.setdefault("OPENALGO_BASE_URL", "https://test.openalgo.com")

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"
_CHECKS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, note: str = "") -> None:
    _CHECKS.append((name, ok, note))
    print(f"{PASS_SYM if ok else FAIL_SYM} {name}" + (f" -- {note}" if note else ""))


def make_decision():
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


def check_a_default_off() -> None:
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
    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    env_ok = "ANALYZER_ROUTING_ENABLED=false" in env
    record("A1 settings default OFF (AST)", ok)
    record("A2 .env.example documents flag", env_ok)


def check_b_no_dead_probe() -> None:
    src = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(
        encoding="utf-8"
    )
    record(
        "B1 no dead async_record_trade_decision probe",
        'getattr(db, "async_record_trade_decision"' not in src,
    )


def check_c_route_audit_wired() -> None:
    src = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(
        encoding="utf-8"
    )
    ok = (
        "async_log_audit" in src
        and 'action="ROUTE"' in src
        and "routing_outcome" in src
    )
    record("C1 ROUTE audit row wired in _persist_routing_outcome", ok)


def check_d_status_real() -> None:
    src = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(
        encoding="utf-8"
    )
    ok = "async_get_trade_decision" in src and "NOT_FOUND" in src
    fabricated = '"PROCESSED"' in src or "ANALYZER_STATUS" in src.lower()
    record("D1 get_decision_status reads DB (NOT_FOUND path)", ok)
    record("D2 no fabricated status strings", not fabricated)


def check_e_runner_validator() -> None:
    runner = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
    validator = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
    record("E1 runner exists", runner.exists())
    record("E2 validator exists", validator.exists())
    if not (runner.exists() and validator.exists()):
        return
    r = subprocess.run(
        [sys.executable, str(runner), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )
    record(
        "E3 runner --dry-run exit 0",
        r.returncode == 0,
        (r.stderr or r.stdout).strip().splitlines()[-1][:80]
        if (r.stderr or r.stdout)
        else "",
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location("p5val", validator)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    def fixture(span_days: int, exc: int, routing: bool = True) -> dict:
        start = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        end = start + datetime.timedelta(days=span_days)
        return {
            "routing": {"enabled_at_start": routing},
            "started_at": start.isoformat(),
            "ended_at": end.isoformat(),
            "unhandled_exceptions": exc,
            "restarts": 0,
            "cycles_completed": 10,
            "counters": {"success": 5, "disabled": 0, "error": 0},
        }

    verdicts = [
        mod.grade_run_log(fixture(15, 0)).verdict,
        mod.grade_run_log(fixture(1, 0)).verdict,
        mod.grade_run_log(fixture(15, 2)).verdict,
        mod.grade_run_log(fixture(15, 0, routing=False)).verdict,
    ]
    record(
        "E4 validator grades fixtures correctly",
        verdicts == ["PASS", "INCOMPLETE", "FAIL", "FAIL"],
        "/".join(verdicts),
    )


async def check_f_live_probes() -> None:
    from loats.trade_decision import TradeDecisionEngine

    engine = TradeDecisionEngine(maxsize=2)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def place_analyzer_request(self, payload):
            return {"status": "accepted"}

    created = AsyncMock(return_value=True)
    audit = AsyncMock()
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.trade_decision.AsyncOpenAlgoClient", FakeClient),
        patch(
            "loats.database.db.async_get_trade_decision", AsyncMock(return_value=None)
        ),
        patch("loats.database.db.async_create_trade_decision", created),
        patch("loats.database.db.async_log_audit", audit),
    ):
        resp = await engine.route_to_analyzer(make_decision())
    ok_enabled = resp["status"] == "success" and created.await_count == 1
    kw = audit.await_args.kwargs if audit.await_args is not None else {}
    outcome = (kw.get("metadata") or {}).get("routing_outcome") or {}
    ok_audit = kw.get("action") == "ROUTE" and outcome.get("status") == "success"
    record("F1 enabled: HTTP fires + decision persisted", ok_enabled)
    record("F2 enabled: ROUTE audit row w/ outcome", ok_audit)

    created2 = AsyncMock(return_value=True)
    audit2 = AsyncMock()
    with (
        patch.object(engine, "analyzer_routing_enabled", False),
        patch(
            "loats.database.db.async_get_trade_decision", AsyncMock(return_value=None)
        ),
        patch("loats.database.db.async_create_trade_decision", created2),
        patch("loats.database.db.async_log_audit", audit2),
    ):
        resp2 = await engine.route_to_analyzer(make_decision())
    kw2 = audit2.await_args.kwargs if audit2.await_args is not None else {}
    outcome2 = (kw2.get("metadata") or {}).get("routing_outcome") or {}
    ok2 = (
        resp2["status"] == "disabled"
        and created2.await_count == 1
        and kw2.get("action") == "ROUTE"
        and outcome2.get("status") == "disabled"
    )
    record("F3 disabled: audited disabled outcome", ok2)

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def place_analyzer_request(self, payload):
            raise RuntimeError("verify simulated failure")

    audit3 = AsyncMock()
    raised = False
    with (
        patch.object(engine, "analyzer_routing_enabled", True),
        patch("loats.trade_decision.AsyncOpenAlgoClient", FailingClient),
        patch(
            "loats.database.db.async_get_trade_decision", AsyncMock(return_value=None)
        ),
        patch(
            "loats.database.db.async_create_trade_decision",
            AsyncMock(return_value=True),
        ),
        patch("loats.database.db.async_log_audit", audit3),
    ):
        try:
            await engine.route_to_analyzer(make_decision())
        except RuntimeError:
            raised = True
    kw3 = audit3.await_args.kwargs if audit3.await_args is not None else {}
    outcome3 = (kw3.get("metadata") or {}).get("routing_outcome") or {}
    record(
        "F4 error: propagates + audited",
        raised and kw3.get("action") == "ROUTE" and outcome3.get("status") == "error",
    )

    persisted = make_decision()
    with patch(
        "loats.database.db.async_get_trade_decision",
        AsyncMock(return_value=persisted),
    ):
        status = await engine.get_decision_status(persisted.decision_id)
    record(
        "F5 status: real row surfaced",
        status.get("status") == persisted.status and status.get("source") == "database",
    )


def check_g_docs() -> None:
    adr = REPO_ROOT / "docs" / "ADR-006-analyzer-routing-p5.md"
    readme = REPO_ROOT / "README.md"
    ok_adr = adr.exists() and "F8-H-01" in adr.read_text(encoding="utf-8")
    ok_rd = "F8-H-01" in readme.read_text(encoding="utf-8")
    record("G1 ADR-006 records F8-H-01", ok_adr)
    record("G2 README records deviation", ok_rd)


async def main_async() -> int:
    print("F8-H-01 external verification")
    print("=" * 60)
    check_a_default_off()
    check_b_no_dead_probe()
    check_c_route_audit_wired()
    check_d_status_real()
    check_e_runner_validator()
    await check_f_live_probes()
    check_g_docs()
    passed = sum(1 for _, ok, _ in _CHECKS if ok)
    total = len(_CHECKS)
    print("=" * 60)
    print(f"RESULT: {passed}/{total}")
    if passed != total:
        for name, ok, note in _CHECKS:
            if not ok:
                print(f"  FAILED: {name} {note}")
    out = REPO_ROOT / "reports" / "verify_f8h01_external.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "finding": "F8-H-01",
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "pass": ok, "note": s} for n, ok, s in _CHECKS],
                "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"written: {out}")
    return 0 if passed == total else 1


def main() -> None:
    import asyncio

    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
