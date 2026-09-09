#!/usr/bin/env python3
"""External verification for F8-M-02..F8-M-07 (01Sep2026-FR section 13).

Runs from a clean process against the installed package (no test suite
fixtures). Mirrors scripts/verify_f8m01_external.py: exit 0 iff every
check passes; each check asserts the finding's OUTCOME contract, not the
idiom that happens to implement it.

  F8-M-02  producer-window cancellation:
    1.  Behavioral - the REAL ``_execute_trading_cycle`` runs against a
        hung volatility producer; the 80 ms window times out; every
        producer task is terminal within the cycle and the hung one was
        CANCELLED (not unblocked).
    2.  Behavioral - a producer raising into the gather must not strand
        its hung sibling (the leak the pre-fix tree really had; the
        timeout path was already closed by gather propagation).
    3.  Structural - ``_settle_cancelled_producers(producers)`` is
        awaited at BOTH cycle boundaries (timeout branch AND exception
        branch), per ADR-0007's amendment.

  F8-M-03  health-check integrity:
    4.  strength.py states the behavioral bare-env contract (no
        "scanner evasion" rationale).
    5.  HC-15 production emission scan passes on the live tree.
    6.  The HC-15 emission-deletion mutation net is present.
    7.  HC-26 implementations delegate to the Win32-safe scandir helper
        (no exists-probing blind spot).
    8.  Behavioral - a trailing-dot fixture name is detected by the
        shared helper (the exact F8-M-03c false-green).

  F8-M-04  root junk:
    9.  Live root listing (os.scandir) holds no pinned junk name and no
        Win32-hostile class name (the check that catches the next
        ``G......`` regardless of name).
    10. The class-wide detector is wired into the hygiene guard.

  F8-M-05  report/run-artifact sprawl:
    11. ``git ls-files`` top-level reports/*.json are exactly the
        deliberate evidence-of-record set (ADR-0011 discipline).

  F8-M-06  .env.test tracked:
    12. ``git ls-files -- .env*`` returns only ``.env.example``.

  F8-M-07  VIX threshold inline:
    13. Settings conformance - ``vix_gate_threshold == 15.0`` and the
        gate reads the setting (no inline ``> 15`` / ``< 15`` literal).
    14. Behavioral - directional gating unchanged: BUY passes below the
        threshold, SELL above; unknown VIX blocks per fail-safe.

Exit 0 iff all checks pass.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("OPENALGO_API_KEY", "verify_dummy")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "verify_dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ENVIRONMENT", "test")

from loats.config import get_settings
from loats.orchestrator import TradingOrchestrator
from loats.rules import CMPRulesEngine

_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _CHECKS.append((name, bool(cond), detail))


async def _hung() -> None:
    await asyncio.Event().wait()  # never set: only cancellation ends this


async def _run_cycle(
    hang_name: str, raise_name: str | None
) -> tuple[list[asyncio.Task[object]], BaseException | None]:
    """Run one REAL trading cycle with producer mocks and a create_task
    spy. Returns (recorded producer tasks, cycle exception or None)."""
    o = TradingOrchestrator()
    producers_mock = {
        name: AsyncMock()
        for name in (
            "_execute_ta_analysis",
            "_execute_sentiment_analysis",
            "_execute_volatility_analysis",
            "_execute_price_action_analysis",
            "_execute_options_flow_analysis",
            "_execute_market_data_update",
        )
    }
    producers_mock[hang_name] = AsyncMock(side_effect=_hung)
    if raise_name is not None:
        producers_mock[raise_name] = AsyncMock(
            side_effect=RuntimeError("F8-M-02 verifier boom")
        )

    recorded: list[asyncio.Task[object]] = []
    real_create_task = asyncio.create_task

    def spy(coro: object, **kwargs: object) -> asyncio.Task[object]:
        task = real_create_task(coro)  # type: ignore[arg-type]
        recorded.append(task)
        return task

    ms = MagicMock()
    ms.default_symbol = "NIFTY"
    ms.producer_window_seconds = 0.05  # F8-H-01: explicit fast window
    error: BaseException | None = None
    with patch.object(o, "_execute_risk_management", new_callable=AsyncMock):
        with (
            patch("loats.orchestrator.settings", ms),
            patch("loats.orchestrator.record_cycle_time"),
            patch("loats.orchestrator.asyncio.create_task", side_effect=spy),
            patch("loats.rules.rules_engine") as mre,
        ):
            mre.is_trading_allowed.return_value = False
            for name, mock in producers_mock.items():
                ctx = patch.object(o, name, mock)
                ctx.start()
            try:
                await o._execute_trading_cycle()
            except BaseException as exc:  # the exception branch re-raises
                error = exc
    return recorded, error


def _producers_settled(recorded: list[asyncio.Task[object]]) -> tuple[bool, str]:
    done = [t for t in recorded if t.done()]
    pending = [t for t in recorded if not t.done()]
    if pending:
        return False, f"pending producers: {pending}"
    if not any(t.cancelled() for t in done):
        return False, "no producer task was CANCELLED"
    return True, f"{len(done)} producers terminal, cancellation delivered"


def verify_m02() -> None:
    # 1. Timeout branch: hung volatility producer stopped within the cycle.
    recorded, error = asyncio.run(_run_cycle("_execute_volatility_analysis", None))
    ok, detail = _producers_settled(recorded)
    check("m02a_timeout_stops_hung_volatility_producer", ok and error is None, detail)

    # 2. Exception branch: raising market-data sibling must not strand the
    # hung volatility producer (gather does NOT cancel survivors itself).
    recorded, error = asyncio.run(
        _run_cycle("_execute_volatility_analysis", "_execute_market_data_update")
    )
    ok, detail = _producers_settled(recorded)
    re_raised = isinstance(error, RuntimeError)
    check(
        "m02b_exception_path_stops_surviving_producers",
        ok and re_raised,
        f"{detail}; re-raised={re_raised}",
    )

    # 3. Structural: settle awaited at BOTH boundaries (ADR-0007).
    orch_src = (REPO_ROOT / "src" / "loats" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    n_calls = orch_src.count("await _settle_cancelled_producers(producers)")
    check(
        "m02c_settle_wired_on_both_boundaries",
        n_calls == 2,
        f"found {n_calls} settle call sites, need exactly 2",
    )


def verify_m03() -> None:
    strength_src = (REPO_ROOT / "src" / "loats" / "strength.py").read_text(
        encoding="utf-8"
    )
    check(
        "m03a_strength_comment_states_behavioral_contract",
        "Behavioral contract" in strength_src and "scanner evasion" not in strength_src,
        "HC-21 rationale must be the behavioral contract, not evasion",
    )

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    check(
        "m03b_hc15_production_emission_scan_passes_live",
        proc.returncode == 0,
        (proc.stdout + proc.stderr).strip()[-200:],
    )

    hygiene_test = (REPO_ROOT / "tests" / "test_repo_hygiene.py").read_text(
        encoding="utf-8"
    )
    check(
        "m03c_hc15_emission_mutation_net_present",
        "TestHC15MutationNet" in hygiene_test,
        "deleting a producer emission site must fail HC-15 in pytest",
    )

    for rel in (
        "scripts/fr7_health_check.py",
        "scripts/verify_hc_registry.py",
        "scripts/check_repo_hygiene.py",
    ):
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        check(
            f"m03d_hc26_delegates_to_scandir_helper_{Path(rel).stem}",
            "root_junk_findings" in src or "win32_root_junk" in src,
            f"{rel} must use the Win32-safe scandir detector",
        )

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "f8m_verifier_win32_root_junk",
        REPO_ROOT / "scripts" / "win32_root_junk.py",
    )
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    check(
        "m03e_hc26_trailing_dot_classification",
        helper.is_hostile_root_name("G......")
        and helper.is_hostile_root_name("out.txt.")
        and not helper.is_hostile_root_name("src"),
        "class-wide hostile-name detection must flag trailing-dot names",
    )
    if sys.platform == "win32":
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            name = "G......"
            extended = f"\\\\?\\{Path(td)}\\{name}"
            fd = os.open(extended, os.O_CREAT | os.O_WRONLY, 0o644)
            os.write(fd, b"junk")
            os.close(fd)
            try:
                findings = helper.root_junk_findings(td)
            finally:
                # Normal Win32 paths cannot address the trailing-dot name
                # (the hostile property itself) - remove via the extended
                # path or the temp dir is undeletable (WinError 145).
                Path(extended).unlink()
        check(
            "m03f_hc26_trailing_dot_fixture_detected",
            findings == [name],
            f"root_junk_findings returned {findings}",
        )
    else:
        check(
            "m03f_hc26_trailing_dot_fixture_detected",
            True,
            "skipped fixture creation on POSIX (Win32 dot-stripping semantics);"
            " classification covered by m03e and the ubuntu CI job",
        )


def verify_m04() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "f8m_verifier_win32_root_junk",
        REPO_ROOT / "scripts" / "win32_root_junk.py",
    )
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    findings = helper.root_junk_findings(REPO_ROOT)
    check(
        "m04a_no_root_junk_on_live_tree",
        findings == [],
        f"root junk findings: {findings}",
    )

    guard_src = (REPO_ROOT / "scripts" / "check_repo_hygiene.py").read_text(
        encoding="utf-8"
    )
    check(
        "m04b_class_wide_detector_wired_into_guard",
        "root_junk_findings" in guard_src,
        "the hygiene guard must scan hostile classes, not only pinned names",
    )


# Deliberate evidence of record (scripts/check_repo_hygiene.py ALLOWLIST):
# curated artifacts with named consumers; anything else tracked at the
# top level of reports/*.json is sprawl (F8-M-05).
_EVIDENCE_OF_RECORD = frozenset(
    {
        "reports/p1_analyze_latency_20260904_040609.json",
        "reports/production-verification.json",
        "reports/todo27_eval.json",
        "reports/todo27_external.json",
    }
)


def _tracked(paths: str) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "--", paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return [f"<git ls-files failed: {proc.stderr.strip()[:120]}>"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def verify_m05() -> None:
    top_level = [
        p for p in _tracked("reports/") if re.fullmatch(r"reports/[^/]+\.json", p)
    ]
    sprawl = sorted(set(top_level) - _EVIDENCE_OF_RECORD)
    check(
        "m05a_top_level_report_artifacts_curated",
        not sprawl,
        f"sprawl beyond evidence of record: {sprawl}",
    )


def verify_m06() -> None:
    tracked_env = _tracked(".env*")
    check(
        "m06a_only_env_example_tracked",
        tracked_env == [".env.example"],
        f"git ls-files .env* -> {tracked_env}",
    )


def verify_m07() -> None:
    settings = get_settings()
    check(
        "m07a_threshold_settings_conformance",
        settings.vix_gate_threshold == 15.0,
        f"vix_gate_threshold={settings.vix_gate_threshold}",
    )
    rules_src = (REPO_ROOT / "src" / "loats" / "rules.py").read_text(encoding="utf-8")
    gate_src = rules_src[
        rules_src.index("def check_vix_gate") : rules_src.index(
            "def apply_gating_rules"
        )
    ]
    inline = re.findall(r"vix\s*[<>]\s*15", gate_src)
    check(
        "m07b_no_inline_threshold_literal",
        not inline and "settings.vix_gate_threshold" in gate_src,
        f"inline literals: {inline}",
    )

    engine = CMPRulesEngine()
    engine.set_vix_level(14.9)
    below = (engine.check_vix_gate("BUY"), engine.check_vix_gate("SELL"))
    engine.set_vix_level(15.1)
    above = (engine.check_vix_gate("BUY"), engine.check_vix_gate("SELL"))
    check(
        "m07c_gate_directional_behavior_unchanged",
        below == (True, False) and above == (False, True),
        f"below threshold (BUY,SELL)={below}, above={above}",
    )
    engine.set_vix_level(None)
    check(
        "m07d_unknown_vix_blocks_by_default",
        engine.check_vix_gate("BUY") is False
        and engine.check_vix_gate("SELL") is False,
        "unknown VIX must block both directions (block_all fail-safe)",
    )


def main() -> int:
    verify_m02()
    verify_m03()
    verify_m04()
    verify_m05()
    verify_m06()
    verify_m07()

    passed = sum(1 for _, ok, _ in _CHECKS if ok)
    for name, ok, detail in _CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    print(f"VERIFIED: {passed}/{len(_CHECKS)}")
    return 0 if passed == len(_CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
