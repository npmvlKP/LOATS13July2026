#!/usr/bin/env python3
"""
External verification for TODO-27 (carried items).

Verifies:
(a) vollib -> py_vollib successor via hand-rolled options_math (Phase 2)
(b) ta dependency drop-or-adopt (dropped)
(c) bounded decision queue + backpressure
(d) bloombergquint feed re-validation

Usage:
    .\\LOATS13July2026\\Scripts\\python.exe scripts\\verify_todo27_external.py
    .\\LOATS13July2026\\Scripts\\python.exe scripts\\verify_todo27_external.py --json output.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src is on path
PROJECT_ROOT = Path(__file__).parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check_vollib_migration() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    # 1. options_math exists
    p = SRC / "loats" / "options_math.py"
    ok = p.exists()
    results.append(("options_math.py exists", ok, str(p) if ok else "missing"))

    # 2. options_math imports without vollib
    try:
        from loats.options_math import (  # type: ignore[import-not-found]
            black_scholes,
            delta,
            gamma,
            vega,
        )

        # Parity check vs known Hull values
        S, K, r, t, sigma = 49, 50, 0.05, 0.3846, 0.2
        d = delta("c", S, K, t, r, sigma)
        g = gamma("c", S, K, t, r, sigma)
        ve = vega("c", S, K, t, r, sigma)
        # Expected from Hull / vollib docstrings
        ok_delta = abs(d - 0.521601633972) < 1e-6
        ok_gamma = abs(g - 0.0655453772525) < 1e-6
        ok_vega = abs(ve - 0.121052427542) < 1e-6
        # Black-Scholes price
        c_price = black_scholes("c", 100, 90, 0.5, 0.01, 0.2)
        ok_price = abs(c_price - 12.111581435) < 1e-6
        ok_all = ok_delta and ok_gamma and ok_vega and ok_price
        msg = f"delta={d:.10f} gamma={g:.10f} vega={ve:.10f} price={c_price:.10f}"
        results.append(("options_math parity vs Hull/vollib", ok_all, msg))
    except Exception as e:
        results.append(
            ("options_math parity vs Hull/vollib", False, f"import/error: {e}")
        )

    # 3. options.py no longer imports vollib
    try:
        opts_text = (SRC / "loats" / "options.py").read_text(encoding="utf-8")
        has_vollib_import = "from vollib" in opts_text or "import vollib" in opts_text
        results.append(
            (
                "options.py does NOT import vollib",
                not has_vollib_import,
                "found vollib import" if has_vollib_import else "clean",
            )
        )
        has_math_import = "from .options_math import" in opts_text
        results.append(
            (
                "options.py imports from options_math",
                has_math_import,
                "found" if has_math_import else "missing",
            )
        )
    except Exception as e:
        results.append(("options.py import check", False, str(e)))

    # 4. pyproject no longer declares vollib
    try:
        pyproj = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        has_vollib_dep = "vollib" in pyproj
        results.append(
            (
                "pyproject.toml drops vollib",
                not has_vollib_dep,
                "still declares vollib" if has_vollib_dep else "removed",
            )
        )
        # Also check ta dropped? That's part of (b) but also related
        has_ta_dep = '"ta>=' in pyproj or "'ta>=" in pyproj or '    "ta' in pyproj
        # More precise: check dependencies list contains ta
        # Use simple string search for `"ta>=` in dependencies block
        results.append(
            (
                "pyproject.toml drops ta (also checked in a)",
                not has_ta_dep,
                "still declares ta" if has_ta_dep else "removed",
            )
        )
        # Check mypy override for vollib removed
        has_vollib_mypy = 'module = "vollib' in pyproj
        results.append(
            (
                "pyproject mypy override for vollib removed",
                not has_vollib_mypy,
                "still present" if has_vollib_mypy else "removed",
            )
        )
    except Exception as e:
        results.append(("pyproject check", False, str(e)))

    # 5. requirements-core no vollib/ta
    try:
        req_core = (PROJECT_ROOT / "requirements-core.txt").read_text(encoding="utf-8")
        has_vollib_req = "vollib" in req_core
        has_ta_req = "ta>=" in req_core or "ta==" in req_core or "\nta\n" in req_core
        results.append(
            (
                "requirements-core.txt drops vollib",
                not has_vollib_req,
                "still present" if has_vollib_req else "removed",
            )
        )
        results.append(
            (
                "requirements-core.txt drops ta",
                not has_ta_req,
                "still present" if has_ta_req else "removed",
            )
        )
    except Exception as e:
        results.append(("requirements-core check", False, str(e)))

    return results


def check_ta_dependency() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    # 1. src/loats/ta.py exists and does NOT import ta library
    try:
        ta_text = (SRC / "loats" / "ta.py").read_text(encoding="utf-8")
        # Check for `import ta` or `from ta.` that would indicate library use
        has_lib_import = False
        for line in ta_text.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("import ta")
                and "technical_analysis" not in stripped
            ):
                # `import ta` alone would be library
                if stripped in ("import ta", "from ta import", "import ta as"):
                    has_lib_import = True
            if stripped.startswith(("from ta.", "import ta.")):
                has_lib_import = True
        results.append(
            (
                "src/loats/ta.py does NOT import ta library",
                not has_lib_import,
                "found library import" if has_lib_import else "clean",
            )
        )
        # Verify custom indicators exist
        has_custom = (
            "def calculate_rsi" in ta_text and "def calculate_supertrend" in ta_text
        )
        results.append(
            (
                "src/loats/ta.py has custom indicators",
                has_custom,
                "found" if has_custom else "missing",
            )
        )
    except Exception as e:
        results.append(("ta.py check", False, str(e)))

    # 2. No src file imports ta library
    try:
        # Use grep via Python
        found = []
        for p in (SRC / "loats").rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                # Detect `import ta` at top level not referring to loats.ta
                if s == "import ta" or s.startswith(
                    ("import ta ", "from ta ", "from ta.")
                ):
                    # Exclude `from loats.ta import`
                    if "loats.ta" not in line and "loats/ta" not in str(p):
                        found.append(f"{p.name}:{lineno}:{line.strip()}")
        ok = len(found) == 0
        results.append(
            ("No src imports ta library", ok, ", ".join(found) if not ok else "none")
        )
    except Exception as e:
        results.append(("ta library import scan", False, str(e)))

    # 3. pyproject already checked but duplicate for (b) clarity
    try:
        pyproj = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        has_ta = '"ta>=0.11.0"' in pyproj or "'ta>=0.11.0'" in pyproj
        results.append(
            (
                "pyproject.toml ta declared? (should be False)",
                not has_ta,
                "still present" if has_ta else "removed",
            )
        )
    except Exception as e:
        results.append(("pyproject ta check", False, str(e)))

    return results


def check_bounded_queue() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    # 1. settings has decision_queue_maxsize
    try:
        settings_text = (SRC / "loats" / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        has_field = "decision_queue_maxsize" in settings_text
        results.append(
            (
                "settings.py has decision_queue_maxsize",
                has_field,
                "found" if has_field else "missing",
            )
        )
        has_validator = "validate_decision_queue_maxsize" in settings_text
        results.append(
            (
                "settings has validator for maxsize",
                has_validator,
                "found" if has_validator else "missing",
            )
        )
        has_default_100 = (
            "decision_queue_maxsize" in settings_text and "100" in settings_text
        )
        results.append(
            (
                "settings default maxsize 100",
                has_default_100,
                "found" if has_default_100 else "missing",
            )
        )
    except Exception as e:
        results.append(("settings queue check", False, str(e)))

    # 2. trade_decision uses bounded Queue
    try:
        td_text = (SRC / "loats" / "trade_decision.py").read_text(encoding="utf-8")
        has_maxsize = "asyncio.Queue(maxsize" in td_text or "Queue(maxsize" in td_text
        results.append(
            (
                "trade_decision uses Queue(maxsize=)",
                has_maxsize,
                "found" if has_maxsize else "missing unbounded Queue()",
            )
        )
        has_backpressure = "QueueFull" in td_text and "put_nowait" in td_text
        results.append(
            (
                "trade_decision has backpressure (put_nowait+QueueFull)",
                has_backpressure,
                "found" if has_backpressure else "missing",
            )
        )
        has_queue_stats = "get_queue_stats" in td_text
        results.append(
            (
                "trade_decision has get_queue_stats()",
                has_queue_stats,
                "found" if has_queue_stats else "missing",
            )
        )
        has_reject_reason = "queue_full" in td_text
        results.append(
            (
                "trade_decision rejects with queue_full",
                has_reject_reason,
                "found" if has_reject_reason else "missing",
            )
        )
    except Exception as e:
        results.append(("trade_decision queue check", False, str(e)))

    # 3. Live runtime check: bounded behavior
    try:
        import asyncio
        from datetime import UTC, datetime

        from loats.config import get_settings
        from loats.models import SignalType, TradeDecision
        from loats.trade_decision import TradeDecisionEngine

        # Clear settings cache to pick up new defaults
        get_settings.cache_clear()  # type: ignore[attr-defined]
        settings = get_settings()
        # Check that default maxsize is 100 and valid
        ok_default = settings.decision_queue_maxsize == 100
        results.append(
            (
                "runtime settings.decision_queue_maxsize == 100",
                ok_default,
                f"got {settings.decision_queue_maxsize}",
            )
        )

        # Check engine bounded
        engine = TradeDecisionEngine(maxsize=2)
        ok_bounded = engine.decision_queue.maxsize == 2
        results.append(
            (
                "runtime engine Queue maxsize=2",
                ok_bounded,
                f"got {engine.decision_queue.maxsize}",
            )
        )
        ok_not_unbounded = engine.decision_queue.maxsize != 0
        results.append(
            (
                "runtime engine is bounded (maxsize != 0)",
                ok_not_unbounded,
                "unbounded!" if not ok_not_unbounded else "bounded",
            )
        )

        # Check that engine default (no override) uses settings (100)
        engine2 = TradeDecisionEngine()
        # Need to clear again after potential env override
        ok_default2 = engine2.decision_queue.maxsize == settings.decision_queue_maxsize
        results.append(
            (
                "runtime default engine uses settings maxsize",
                ok_default2,
                f"engine={engine2.decision_queue.maxsize} settings={settings.decision_queue_maxsize}",
            )
        )

        # Live enqueue backpressure test
        async def _run_queue_test() -> tuple[bool, str]:
            eng = TradeDecisionEngine(maxsize=2)

            def _make_td():
                return TradeDecision(
                    symbol="NIFTY",
                    decision_type=SignalType.BUY,
                    composite_strength=0.8,
                    timestamp=datetime.now(UTC),
                    entry_price=24500.0,
                    quantity=25,
                    stop_loss=24255.0,
                    take_profit=24990.0,
                    risk_percentage=0.02,
                    status="PENDING",
                )

            r1 = await eng.enqueue_decision(_make_td())
            r2 = await eng.enqueue_decision(_make_td())
            r3 = await eng.enqueue_decision(_make_td())
            ok = (
                r1["status"] == "queued"
                and r2["status"] == "queued"
                and r3["status"] == "rejected"
                and r3.get("reason") == "queue_full"
            )
            msg = f"r1={r1['status']} r2={r2['status']} r3={r3['status']}/{r3.get('reason')} qsize={eng.decision_queue.qsize()}"
            return ok, msg

        ok_q, msg_q = asyncio.run(_run_queue_test())
        results.append(
            ("live bounded queue backpressure (2 queued, 3rd rejected)", ok_q, msg_q)
        )

        # Check get_queue_stats
        engine3 = TradeDecisionEngine(maxsize=5)
        stats = engine3.get_queue_stats()
        ok_stats = (
            "queue_size" in stats and "queue_maxsize" in stats and "queue_full" in stats
        )
        results.append(("get_queue_stats returns expected keys", ok_stats, str(stats)))

    except Exception as e:
        import traceback

        results.append(
            (
                "runtime bounded queue live test",
                False,
                f"{e}\n{traceback.format_exc()[:500]}",
            )
        )

    return results


def check_bloomberg_feed() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    # 1. settings no bloombergquint, has livemint
    try:
        settings_text = (SRC / "loats" / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        # Check that the default rss_feeds value does NOT contain the defunct URL
        # (allow mention in comments/descriptions about removal)
        has_bq_url_in_default = (
            '"https://www.bloombergquint.com/markets-feed"' in settings_text
        )
        results.append(
            (
                "settings.py default rss_feeds does NOT contain bloombergquint URL",
                not has_bq_url_in_default,
                "still contains bloombergquint URL in default"
                if has_bq_url_in_default
                else "clean",
            )
        )
        has_livemint = "livemint" in settings_text.lower()
        results.append(
            (
                "settings.py contains livemint replacement",
                has_livemint,
                "found" if has_livemint else "missing",
            )
        )
        has_rss_feeds = "rss_feeds" in settings_text
        results.append(
            (
                "settings.py has rss_feeds field",
                has_rss_feeds,
                "found" if has_rss_feeds else "missing",
            )
        )
    except Exception as e:
        results.append(("settings feed check", False, str(e)))

    # 2. orchestrator uses settings.rss_feeds
    try:
        orch_text = (SRC / "loats" / "orchestrator.py").read_text(encoding="utf-8")
        uses_settings = (
            "get_settings().rss_feeds" in orch_text or "settings.rss_feeds" in orch_text
        )
        results.append(
            (
                "orchestrator uses settings.rss_feeds",
                uses_settings,
                "found" if uses_settings else "still hardcoded",
            )
        )
        # Check that hardcoded list with bloomberg URL is gone (allow comment mentions)
        has_bq_hardcoded_final = (
            '"https://www.bloombergquint.com/markets-feed"' in orch_text
            and "rss_feeds = [" in orch_text
        )
        results.append(
            (
                "orchestrator hardcoded bloombergquint removed",
                not has_bq_hardcoded_final,
                "still hardcoded!" if has_bq_hardcoded_final else "clean",
            )
        )
        has_validate = "validate_rss_feed" in orch_text
        results.append(
            (
                "orchestrator has validate_rss_feed",
                has_validate,
                "found" if has_validate else "missing",
            )
        )
    except Exception as e:
        results.append(("orchestrator feed check", False, str(e)))

    # 3. scheduler RSS posture (F8-M-06, post-F8-H-03): the scheduler
    # was restructured to a support-job-only module — it consumes NO
    # RSS feeds and emits NO signals (orchestrator is the single
    # signal engine of record; see ADR-0005). The pre-restructure
    # checks ("scheduler uses settings.rss_feeds" / "scheduler
    # validates feeds") asserted the old dual-engine architecture.
    # The surviving outcomes: no RSS consumption left behind AND no
    # hardcoded bloombergquint anywhere in the module.
    try:
        sched_text = (SRC / "loats" / "scheduler.py").read_text(encoding="utf-8")
        sched_rss_free = "rss_feeds" not in sched_text
        results.append(
            (
                "scheduler is RSS-free (single-engine, F8-H-03)",
                sched_rss_free,
                "clean" if sched_rss_free else "rss_feeds reference remains",
            )
        )
        has_bq_sched = "bloombergquint.com/markets-feed" in sched_text
        results.append(
            (
                "scheduler hardcoded bloombergquint removed",
                not has_bq_sched,
                "still hardcoded!" if has_bq_sched else "clean",
            )
        )
    except Exception as e:
        results.append(("scheduler feed check", False, str(e)))

    # 4. .env.example documents new feeds
    try:
        env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        has_rss_env = "RSS_FEEDS" in env_example
        results.append(
            (
                ".env.example documents RSS_FEEDS",
                has_rss_env,
                "found" if has_rss_env else "missing",
            )
        )
        # Check that the actual RSS_FEEDS value (not comments) does NOT contain bloombergquint
        has_bq_in_value = False
        for line in env_example.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("RSS_FEEDS=")
                and "bloombergquint" in stripped.lower()
            ):
                has_bq_in_value = True
                break
        results.append(
            (
                ".env.example RSS_FEEDS value does NOT contain bloombergquint",
                not has_bq_in_value,
                "still contains in value!" if has_bq_in_value else "clean",
            )
        )
        has_queue_env = "DECISION_QUEUE_MAXSIZE" in env_example
        results.append(
            (
                ".env.example documents DECISION_QUEUE_MAXSIZE",
                has_queue_env,
                "found" if has_queue_env else "missing",
            )
        )
    except Exception as e:
        results.append((".env.example check", False, str(e)))

    # 5. Validate feed URLs shape (no network fetch, just format)
    try:
        from loats.config import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        settings = get_settings()
        feeds = settings.rss_feeds
        ok_len = len(feeds) >= 2
        results.append(
            ("runtime rss_feeds has >=2 entries", ok_len, f"got {len(feeds)}: {feeds}")
        )
        has_bq_runtime = any("bloombergquint" in f.lower() for f in feeds)
        results.append(
            (
                "runtime rss_feeds does NOT contain bloombergquint",
                not has_bq_runtime,
                "still contains bq" if has_bq_runtime else "clean",
            )
        )
        has_livemint_runtime = any("livemint" in f.lower() for f in feeds)
        results.append(
            (
                "runtime rss_feeds contains livemint",
                has_livemint_runtime,
                "found" if has_livemint_runtime else "missing",
            )
        )
        # Check all feeds are http/https
        all_http = all(f.startswith(("http://", "https://")) for f in feeds)
        results.append(("runtime rss_feeds all http/https", all_http, str(feeds)))
    except Exception as e:
        results.append(("runtime feed check", False, str(e)))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify TODO-27 carried items")
    parser.add_argument("--json", dest="json_out", help="Write JSON output to file")
    args = parser.parse_args()

    all_checks: list[tuple[str, str, bool, str]] = []

    suites = [
        ("(a) vollib -> hand-rolled options_math", check_vollib_migration),
        ("(b) ta drop-or-adopt", check_ta_dependency),
        ("(c) bounded decision queue", check_bounded_queue),
        ("(d) bloombergquint re-validation", check_bloomberg_feed),
    ]

    total = 0
    passed = 0
    failed = 0

    print("=" * 72)
    print("TODO-27 EXTERNAL VERIFICATION")
    print("=" * 72)

    for suite_name, fn in suites:
        print(f"\n[{suite_name}]")
        results = fn()
        for name, ok, detail in results:
            total += 1
            if ok:
                passed += 1
                print(f"  [PASS] {name} -- {detail}")
                all_checks.append((suite_name, name, True, detail))
            else:
                failed += 1
                print(f"  [FAIL] {name} -- {detail}")
                all_checks.append((suite_name, name, False, detail))

    print("\n" + "=" * 72)
    print(f"TOTAL: {passed}/{total} passed, {failed} failed")
    print("=" * 72)
    if failed == 0:
        print("All TODO-27 checks PASSED.")
    else:
        print(f"{failed} check(s) FAILED -- see details above.")

    if args.json_out:
        out = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "checks": [
                {"suite": s, "name": n, "ok": ok, "detail": d}
                for s, n, ok, d in all_checks
            ],
        }
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nJSON written to {args.json_out}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
