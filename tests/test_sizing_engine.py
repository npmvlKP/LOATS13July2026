"""Unit tests for loats.sizing SizingEngine (HC-12/13 coverage lift)."""

from __future__ import annotations

from datetime import UTC, datetime

from loats.models import FundsData, Trade, TransactionType
from loats.sizing import SizingEngine, SizingMethod, sizing_engine


def _funds(cash: float = 500_000.0, margin: float = 200_000.0) -> FundsData:
    return FundsData(
        available_cash=cash,
        utilized_margin=0.0,
        available_margin=margin,
        total_equity=cash + margin,
        timestamp=datetime.now(UTC),
    )


def test_enums_and_singleton() -> None:
    assert SizingMethod.FIXED_FRACTION.value == "fixed_fraction"
    assert isinstance(sizing_engine, SizingEngine)


def test_fixed_fraction_basic_and_invalid() -> None:
    eng = SizingEngine()
    funds = _funds()

    size, info = eng.calculate_fixed_fraction_size(funds, 100.0, 95.0, "NIFTY")
    assert size > 0
    assert info["method"] == "fixed_fraction"
    assert info["final_size"] == size

    size_b, _ = eng.calculate_fixed_fraction_size(funds, 100.0, 95.0, "BANKNIFTY")
    assert size_b > 0

    size_o, _ = eng.calculate_fixed_fraction_size(funds, 50.0, 45.0, "RELIANCE")
    assert size_o > 0

    z, info_z = eng.calculate_fixed_fraction_size(funds, 0.0, 95.0)
    assert z == 0
    assert info_z["reason"] == "invalid_prices"

    z2, info_z2 = eng.calculate_fixed_fraction_size(funds, 100.0, 100.0)
    assert z2 == 0
    assert info_z2["reason"] == "invalid_risk_per_share"


def test_volatility_kelly_margin_cost() -> None:
    eng = SizingEngine()
    funds = _funds()

    s, info = eng.calculate_volatility_adjusted_size(funds, 100.0, 95.0, 0.08, "NIFTY")
    assert s >= 1
    assert info["method"] == "volatility_adjusted"

    z, info_z = eng.calculate_volatility_adjusted_size(funds, 0.0, 95.0, 0.05)
    assert z == 0
    assert info_z.get("volatility_adjustment") == "skipped"

    k, kinfo = eng.calculate_kelly_criterion_size(funds, 0.55, 1.5, "NIFTY")
    assert k >= 0
    assert kinfo["method"] == "kelly_criterion"

    bad_p, info_p = eng.calculate_kelly_criterion_size(funds, 0.0, 1.5)
    assert bad_p == 0
    assert info_p["reason"] == "invalid_win_probability"

    bad_r, info_r = eng.calculate_kelly_criterion_size(funds, 0.55, 0.0)
    assert bad_r == 0
    assert info_r["reason"] == "invalid_win_loss_ratio"

    m, minfo = eng.calculate_margin_aware_size(funds, 100.0, 95.0, 0.2, "NIFTY")
    assert m >= 0
    assert minfo["method"] == "margin_aware"

    m0, _ = eng.calculate_margin_aware_size(funds, 0.0, 95.0, 0.2)
    assert m0 == 0

    # force high margin utilization path
    tight = _funds(cash=10_000.0, margin=5_000.0)
    m2, minfo2 = eng.calculate_margin_aware_size(tight, 100.0, 90.0, 0.5, "NIFTY")
    assert minfo2["method"] == "margin_aware"
    assert m2 >= 0

    c, cinfo = eng.calculate_cost_aware_size(funds, 100.0, 95.0, 50.0, "NIFTY")
    assert c >= 0
    assert cinfo["method"] == "cost_aware"

    c2, cinfo2 = eng.calculate_cost_aware_size(funds, 100.0, 95.0, 5.0, "RELIANCE")
    assert cinfo2["method"] == "cost_aware"

    c0, _ = eng.calculate_cost_aware_size(funds, 0.0, 95.0, 50.0)
    assert c0 == 0

    # costs exceed risk capital
    tiny = _funds(cash=100.0, margin=0.0)
    cz, czinfo = eng.calculate_cost_aware_size(tiny, 100.0, 95.0, 10_000.0, "NIFTY")
    assert cz == 0
    assert czinfo.get("cost_adjustment") == "blocked_by_costs"


def test_portfolio_risk_and_recommendation() -> None:
    eng = SizingEngine()
    funds = _funds()
    trades = [
        Trade(
            symbol="NIFTY",
            quantity=25,
            entry_price=100.0,
            entry_time=datetime.now(UTC),
            transaction_type=TransactionType.BUY,
            stop_loss=95.0,
        )
    ]
    alloc = eng.calculate_portfolio_risk_allocation(funds, trades)
    assert "remaining_risk_budget" in alloc
    assert "position_risk_breakdown" in alloc
    assert alloc["risk_utilization"] >= 0.0

    empty = eng.calculate_portfolio_risk_allocation(funds, [])
    assert empty["current_risk_exposure"] == 0.0

    assert eng.get_recommended_sizing_method(0.02) == SizingMethod.FIXED_FRACTION
    assert (
        eng.get_recommended_sizing_method(0.02, win_probability=0.7)
        == SizingMethod.KELLY_CRITERION
    )
    assert (
        eng.get_recommended_sizing_method(0.02, margin_requirement=0.2)
        == SizingMethod.RISK_PARITY
    )
    assert eng.get_recommended_sizing_method(0.08) == SizingMethod.VOLATILITY_BASED
