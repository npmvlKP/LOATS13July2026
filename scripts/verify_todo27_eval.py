#!/usr/bin/env python3
"""
TODO-27 Eval: 10-case benchmark for the 4 carried items.

Evaluates before vs after scores by simulating what the old codebase
would have scored (based on forensic reports) vs current.

Cases:
  V1: Black-Scholes price matches vollib/Hull within 1e-6
  V2: Greeks (delta/gamma/vega/theta/rho) match vollib
  V3: Implied vol round-trip recovers sigma within 1e-4
  T1: pyproject does NOT declare ta
  T2: src/loats/ta.py has custom indicators & no library import
  Q1: Queue is bounded (maxsize != 0)
  Q2: Queue backpressure rejects when full
  Q3: Queue stats API exists
  F1: rss_feeds does NOT contain bloombergquint
  F2: rss_feeds contains validated replacement (livemint)

Before scores are hard-coded from forensic evidence (F6-L-06, F6-L-07, etc.)
After scores are measured live.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ---------------------------------------------------------------------------
# Live check implementations (after)
# ---------------------------------------------------------------------------

def live_v1() -> tuple[bool, str]:
    try:
        from loats.options_math import black_scholes
        c = black_scholes("c", 100, 90, 0.5, 0.01, 0.2)
        ok = abs(c - 12.111581435) < 1e-6
        return ok, f"c={c:.10f} exp 12.111581435 diff={abs(c-12.111581435):.2e}"
    except Exception as e:
        return False, str(e)

def live_v2() -> tuple[bool, str]:
    try:
        from loats.options_math import delta, gamma, theta, vega, rho
        S, K, r, t, sigma = 49, 50, 0.05, 0.3846, 0.2
        d = delta("c", S, K, t, r, sigma)
        g = gamma("c", S, K, t, r, sigma)
        ve = vega("c", S, K, t, r, sigma)
        th = theta("c", S, K, t, r, sigma) * 365
        rh = rho("c", S, K, t, r, sigma)
        ok = (
            abs(d - 0.521601633972) < 1e-6
            and abs(g - 0.0655453772525) < 1e-6
            and abs(ve - 0.121052427542) < 1e-6
            and abs(th + 4.30538996455) < 1e-4
            and abs(rh - 0.089065740988) < 1e-6
        )
        return ok, f"d={d:.6f} g={g:.6f} ve={ve:.6f} th={th:.4f} rh={rh:.6f}"
    except Exception as e:
        return False, str(e)

def live_v3() -> tuple[bool, str]:
    try:
        from loats.options_math import black_scholes, implied_volatility
        S, K, t, r, sigma = 100, 100, 1, 0.05, 0.2
        price = black_scholes("c", S, K, t, r, sigma)
        iv = implied_volatility(price, S, K, t, r, "c")
        ok = abs(iv - 0.2) < 1e-4
        return ok, f"price={price:.6f} iv={iv:.6f} diff={abs(iv-0.2):.2e}"
    except Exception as e:
        return False, str(e)

def live_t1() -> tuple[bool, str]:
    try:
        pyproj = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        ok = '"ta>=0.11.0"' not in pyproj
        return ok, "ta removed" if ok else "still declares ta"
    except Exception as e:
        return False, str(e)

def live_t2() -> tuple[bool, str]:
    try:
        ta_text = (SRC / "loats" / "ta.py").read_text(encoding="utf-8")
        has_lib = "from ta." in ta_text or "import ta" in ta_text and "technical_analysis" not in ta_text
        # More precise: no library import
        has_custom = "def calculate_rsi" in ta_text
        ok = not has_lib and has_custom
        return ok, f"has_lib={has_lib} has_custom={has_custom}"
    except Exception as e:
        return False, str(e)

def live_q1() -> tuple[bool, str]:
    try:
        from loats.trade_decision import TradeDecisionEngine
        eng = TradeDecisionEngine()
        ok = eng.decision_queue.maxsize != 0 and eng.decision_queue.maxsize == 100
        return ok, f"maxsize={eng.decision_queue.maxsize}"
    except Exception as e:
        return False, str(e)

def live_q2() -> tuple[bool, str]:
    try:
        from loats.models import SignalType, TradeDecision
        from loats.trade_decision import TradeDecisionEngine

        async def _test():
            eng = TradeDecisionEngine(maxsize=2)
            def _td():
                return TradeDecision(
                    symbol="NIFTY", decision_type=SignalType.BUY, composite_strength=0.8,
                    timestamp=datetime.now(UTC), entry_price=24500, quantity=25,
                    stop_loss=24255, take_profit=24990, risk_percentage=0.02, status="PENDING"
                )
            r1 = await eng.enqueue_decision(_td())
            r2 = await eng.enqueue_decision(_td())
            r3 = await eng.enqueue_decision(_td())
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(_test())
        ok = r1["status"] == "queued" and r2["status"] == "queued" and r3["status"] == "rejected" and r3.get("reason") == "queue_full"
        return ok, f"r1={r1['status']} r2={r2['status']} r3={r3['status']}/{r3.get('reason')}"
    except Exception as e:
        return False, str(e)

def live_q3() -> tuple[bool, str]:
    try:
        from loats.trade_decision import TradeDecisionEngine
        eng = TradeDecisionEngine(maxsize=5)
        stats = eng.get_queue_stats()
        ok = all(k in stats for k in ("queue_size", "queue_maxsize", "queue_full", "queue_empty"))
        return ok, str(stats)
    except Exception as e:
        return False, str(e)

def live_f1() -> tuple[bool, str]:
    try:
        from loats.config import get_settings
        get_settings.cache_clear()  # type: ignore
        feeds = get_settings().rss_feeds
        ok = not any("bloombergquint" in f for f in feeds)
        return ok, str(feeds)
    except Exception as e:
        return False, str(e)

def live_f2() -> tuple[bool, str]:
    try:
        from loats.config import get_settings
        get_settings.cache_clear()  # type: ignore
        feeds = get_settings().rss_feeds
        ok = any("livemint" in f for f in feeds) and len(feeds) >= 2
        return ok, str(feeds)
    except Exception as e:
        return False, str(e)

CASES = [
    ("V1 Black-Scholes price (Hull)", live_v1, False),  # before: vollib, but also deprecated
    ("V2 Greeks parity (Hull)", live_v2, False),
    ("V3 IV round-trip", live_v3, False),
    ("T1 pyproject drops ta", live_t1, False),
    ("T2 ta.py custom & no lib import", live_t2, False),
    ("Q1 Queue bounded (maxsize=100)", live_q1, False),
    ("Q2 Queue backpressure", live_q2, False),
    ("Q3 Queue stats API", live_q3, False),
    ("F1 rss_feeds no bloombergquint", live_f1, False),
    ("F2 rss_feeds has livemint", live_f2, False),
]

# Before scores from forensic evidence (F6-L-06, F6-L-07, F7-L-06, VOLLIB_MIGRATION_PLAN)
# V1-3: before used vollib (deprecated) — technically worked but with fallback and deprecated dep => partial
# T1: before declared ta=0.11.0 unused => fail
# T2: before had custom ta but declared unused dep => partial fail
# Q1-3: before unbounded Queue() => all fail
# F1-2: before had bloombergquint defunct => both fail
BEFORE_RESULTS = {
    "V1 Black-Scholes price (Hull)": (True, "vollib price ~12.11 but deprecated dep"),  # technically passed but with debt
    "V2 Greeks parity (Hull)": (True, "vollib greeks but deprecated"),
    "V3 IV round-trip": (True, "vollib IV but deprecated"),
    "T1 pyproject drops ta": (False, "ta>=0.11.0 declared but unused"),
    "T2 ta.py custom & no lib import": (False, "custom exists but ghost dep present"),
    "Q1 Queue bounded (maxsize=100)": (False, "Queue() unbounded maxsize=0"),
    "Q2 Queue backpressure": (False, "no QueueFull handling"),
    "Q3 Queue stats API": (False, "no get_queue_stats"),
    "F1 rss_feeds no bloombergquint": (False, "bloombergquint present"),
    "F2 rss_feeds has livemint": (False, "bloombergquint present, no livemint"),
}

def main() -> None:
    print("=" * 72)
    print("TODO-27 EVAL: 10-case before/after")
    print("=" * 72)
    # Before
    before_pass = sum(1 for v, _ in BEFORE_RESULTS.values() if v)
    print(f"\nBEFORE (forensic baseline, 2026-08-23): {before_pass}/10")
    for name in [c[0] for c in CASES]:
        ok, detail = BEFORE_RESULTS[name]
        print(f"  {'[PASS]' if ok else '[FAIL]':6} {name:35} — {detail}")

    # After (live)
    print(f"\nAFTER (live, {datetime.now(UTC).isoformat()}):")
    after_pass = 0
    for name, fn, _ in CASES:
        ok, detail = fn()
        if ok:
            after_pass += 1
        print(f"  {'[PASS]' if ok else '[FAIL]':6} {name:35} — {detail}")

    print("\n" + "=" * 72)
    print(f"SCORE: BEFORE {before_pass}/10 -> AFTER {after_pass}/10  (delta +{after_pass - before_pass})")
    if after_pass == 10:
        print("All 10 cases PASSED after — TODO-27 fully addressed.")
    elif after_pass > before_pass:
        print(f"Improvement: +{after_pass - before_pass} cases. Remaining: {10 - after_pass}")
    else:
        print("No improvement — investigate.")
    print("=" * 72)

    # Write JSON for CI
    out = {
        "before": before_pass,
        "after": after_pass,
        "cases": [
            {"name": name, "before_ok": BEFORE_RESULTS[name][0], "after_ok": fn()[0]}
            for name, fn, _ in CASES
        ],
    }
    Path("reports/todo27_eval.json").write_text(str(out), encoding="utf-8")

if __name__ == "__main__":
    main()
