"""Integration tests for VIX symmetric fail-safe.

HC-25: no bare ``18.5`` VIX fallback may remain in ``rules.py``.
HC-12: symmetric fail-safe — VIX unknown → block BOTH BUY and SELL.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_no_bare_18_5_in_rules_py() -> None:

    repo = Path(__file__).resolve().parents[1]
    rules = (repo / "src" / "loats" / "rules.py").read_text(encoding="utf-8")
    code_only = "\n".join(
        line for line in rules.splitlines() if not line.lstrip().startswith("#")
    )
    assert "18.5" not in code_only, "rules.py must not hard-code 18.5 VIX fallback"


@pytest.mark.asyncio
async def test_vix_unknown_blocks_both_buy_and_sell() -> None:
    from loats.rules import CMPRulesEngine

    eng = CMPRulesEngine()
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is False


@pytest.mark.asyncio
async def test_vix_set_below_15_passes_buy_blocks_sell() -> None:
    from loats.rules import CMPRulesEngine

    eng = CMPRulesEngine()
    eng.set_vix_level(12.0)
    assert eng.check_vix_gate("BUY") is True
    assert eng.check_vix_gate("SELL") is False


@pytest.mark.asyncio
async def test_vix_set_above_15_passes_sell_blocks_buy() -> None:
    from loats.rules import CMPRulesEngine

    eng = CMPRulesEngine()
    eng.set_vix_level(20.0)
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is True


@pytest.mark.asyncio
async def test_vix_set_none_still_blocks() -> None:
    from loats.rules import CMPRulesEngine

    eng = CMPRulesEngine()
    eng.set_vix_level(None)
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is False


@pytest.mark.asyncio
async def test_vix_outcome_does_not_use_fabricated_18_5() -> None:
    from loats.rules import CMPRulesEngine

    eng = CMPRulesEngine()
    assert eng.get_vix_level() is None
    eng.set_vix_level(15.0)
    assert eng.get_vix_level() == 15.0
    eng.set_vix_level(None)
    assert eng.get_vix_level() is None
