#!/usr/bin/env python3
"""External probe for TODO-26 backtest sanity driver wiring."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    backtest_path = REPO_ROOT / "src" / "loats" / "backtest_sanity.py"
    scheduler_path = REPO_ROOT / "src" / "loats" / "scheduler.py"

    assert backtest_path.exists(), "src/loats/backtest_sanity.py missing"
    backtest_code = backtest_path.read_text(encoding="utf-8")
    scheduler_code = scheduler_path.read_text(encoding="utf-8")

    required_backtest_exports = [
        "BacktestSanityResult",
        "BacktestWindow",
        "PnLResult",
        "WalkForwardWindowIterator",
        "run_backtest_sanity_check",
        "backtest_sanity_pass_gate",
        "calculate_simple_pnl",
        "validate_no_lookahead",
    ]
    for name in required_backtest_exports:
        assert name in backtest_code, f"{name} missing from backtest_sanity.py"

    assert "backtest_sanity" in scheduler_code.lower(), (
        "backtest_sanity not wired in scheduler.py"
    )
    assert 'CronTrigger(day_of_week="sun"' in scheduler_code, (
        "weekly CronTrigger missing in scheduler.py"
    )
    assert '"backtest_sanity_check"' in scheduler_code, (
        "backtest_sanity_check job id missing in scheduler.py"
    )
    assert "run_backtest_sanity_check" in scheduler_code, (
        "run_backtest_sanity_check not referenced in scheduler.py"
    )

    print("TODO-26 backtest sanity driver wiring OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
