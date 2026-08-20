"""
Comprehensive test coverage for sizing.py module.
This test file aims to achieve 80%+ coverage for the SizingEngine class.
"""

import datetime

from loats.models import FundsData, Trade
from loats.sizing import SizingEngine, SizingMethod, sizing_engine


class TestSizingEngineInitialization:
    """Test SizingEngine initialization and basic properties."""

    def test_initialization(self) -> None:
        """Test that SizingEngine initializes correctly."""
        engine = SizingEngine()
        assert engine.fixed_fraction == 0.02  # 2% risk per trade
        assert engine.max_position_size > 0
        assert engine.nifty_lot_size == 25
        assert engine.max_order_value > 0
        assert engine.slippage_buffer == 0.005  # 0.5%

    def test_sizing_method_enum(self) -> None:
        """Test SizingMethod enumeration."""
        assert SizingMethod.FIXED_FRACTION == "fixed_fraction"
        assert SizingMethod.VOLATILITY_BASED == "volatility_based"
        assert SizingMethod.KELLY_CRITERION == "kelly_criterion"
        assert SizingMethod.RISK_PARITY == "risk_parity"


class TestFixedFractionSizing:
    """Test fixed fraction sizing calculations."""

    def test_calculate_fixed_fraction_size_basic(self) -> None:
        """Test basic fixed fraction sizing calculation."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with NIFTY
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=95.0, symbol="NIFTY"
        )

        assert position_size > 0
        assert details["method"] == "fixed_fraction"
        assert details["fixed_fraction"] == 0.02
        assert details["available_capital"] == 15000.0
        assert details["risk_capital"] == 300.0  # 2% of 15000
        assert details["risk_per_share"] == 5.0  # 100 - 95
        assert details["symbol"] == "NIFTY"

    def test_calculate_fixed_fraction_size_invalid_prices(self) -> None:
        """Test fixed fraction sizing with invalid prices."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid entry price
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=0.0, stop_loss=95.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_prices"

        # Test with invalid stop loss
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=0.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_prices"

    def test_calculate_fixed_fraction_size_invalid_risk_per_share(self) -> None:
        """Test fixed fraction sizing with invalid risk per share."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with same entry and stop loss (zero risk)
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=100.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_risk_per_share"

    def test_calculate_fixed_fraction_size_nifty_limits(self) -> None:
        """Test fixed fraction sizing with NIFTY position limits."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=100000.0,
            utilized_margin=20000.0,
            available_margin=50000.0,
            total_equity=150000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test NIFTY position limit (5 lots max = 125 units)
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=95.0, symbol="NIFTY"
        )

        # Should be limited to 125 (5 lots * 25)
        assert position_size <= 125
        assert details["final_size"] <= 125

    def test_calculate_fixed_fraction_size_banknifty_limits(self) -> None:
        """Test fixed fraction sizing with BANKNIFTY position limits."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=100000.0,
            available_margin=50000.0,
            total_equity=150000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test BANKNIFTY position limit (3 lots max = 75 units)
        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=95.0, symbol="BANKNIFTY"
        )

        # Should be limited to 75 (3 lots * 25)
        assert position_size <= 75
        assert details["final_size"] <= 75

    def test_calculate_fixed_fraction_size_other_symbols(self) -> None:
        """Test fixed fraction sizing with other symbols."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        position_size, details = engine.calculate_fixed_fraction_size(
            funds, entry_price=100.0, stop_loss=95.0, symbol="RELIANCE"
        )

        assert position_size > 0
        assert details["symbol"] == "RELIANCE"


class TestSizingConstraints:
    """Test sizing constraint applications."""

    def test_apply_sizing_constraints_max_order_value(self) -> None:
        """Test max order value constraint."""
        engine = SizingEngine()

        # Test with very large position that would exceed max order value
        position_size = 10000
        entry_price = 100.0

        constrained_size = engine._apply_sizing_constraints(
            position_size, entry_price, "NIFTY"
        )

        # Should be limited by max_order_value
        max_possible = int(float(engine.max_order_value) / entry_price)
        assert constrained_size <= max_possible

    def test_apply_sizing_constraints_minimum_size(self) -> None:
        """Test minimum position size constraint."""
        engine = SizingEngine()

        # Test with very small position
        position_size = 1
        entry_price = 100.0

        constrained_size = engine._apply_sizing_constraints(
            position_size, entry_price, "NIFTY"
        )

        # Should be at least 1 lot (25 units) for NIFTY
        assert constrained_size >= 25

        # Test with other symbol
        constrained_size = engine._apply_sizing_constraints(
            position_size, entry_price, "RELIANCE"
        )

        # Should be at least 1 for other symbols
        assert constrained_size >= 1


class TestVolatilityAdjustedSizing:
    """Test volatility-adjusted sizing calculations."""

    def test_calculate_volatility_adjusted_size_basic(self) -> None:
        """Test basic volatility-adjusted sizing."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with moderate volatility
        position_size, details = engine.calculate_volatility_adjusted_size(
            funds, entry_price=100.0, stop_loss=95.0, volatility=0.05, symbol="NIFTY"
        )

        assert position_size > 0
        assert details["method"] == "volatility_adjusted"
        assert details["volatility"] == 0.05
        assert details["normalized_volatility"] == 0.05
        assert "volatility_factor" in details
        assert "base_size" in details
        assert "adjusted_size" in details

    def test_calculate_volatility_adjusted_size_high_volatility(self) -> None:
        """Test volatility-adjusted sizing with high volatility."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            utilized_margin=2000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with high volatility (should result in smaller position)
        position_size_high, details_high = engine.calculate_volatility_adjusted_size(
            funds, entry_price=100.0, stop_loss=95.0, volatility=0.10, symbol="NIFTY"
        )

        # Test with low volatility (should result in larger position)
        position_size_low, details_low = engine.calculate_volatility_adjusted_size(
            funds, entry_price=100.0, stop_loss=95.0, volatility=0.01, symbol="NIFTY"
        )

        # High volatility should give smaller position than low volatility
        assert position_size_high <= position_size_low

    def test_calculate_volatility_adjusted_size_zero_base(self) -> None:
        """Test volatility-adjusted sizing when base size is zero."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid prices (should result in zero base size)
        position_size, details = engine.calculate_volatility_adjusted_size(
            funds, entry_price=0.0, stop_loss=95.0, volatility=0.05, symbol="NIFTY"
        )

        assert position_size == 0
        assert details["volatility_adjustment"] == "skipped"


class TestKellyCriterionSizing:
    """Test Kelly Criterion sizing calculations."""

    def test_calculate_kelly_criterion_size_basic(self) -> None:
        """Test basic Kelly Criterion sizing."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with good win probability and ratio
        position_size, details = engine.calculate_kelly_criterion_size(
            funds, win_probability=0.65, win_loss_ratio=2.0, symbol="NIFTY"
        )

        assert position_size > 0
        assert details["method"] == "kelly_criterion"
        assert details["win_probability"] == 0.65
        assert details["win_loss_ratio"] == 2.0
        assert "kelly_fraction" in details
        assert "effective_fraction" in details

    def test_calculate_kelly_criterion_size_invalid_probability(self) -> None:
        """Test Kelly Criterion sizing with invalid win probability."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid probability (<= 0)
        position_size, details = engine.calculate_kelly_criterion_size(
            funds, win_probability=0.0, win_loss_ratio=2.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_win_probability"

        # Test with invalid probability (>= 1)
        position_size, details = engine.calculate_kelly_criterion_size(
            funds, win_probability=1.0, win_loss_ratio=2.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_win_probability"

    def test_calculate_kelly_criterion_size_invalid_ratio(self) -> None:
        """Test Kelly Criterion sizing with invalid win/loss ratio."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid ratio (<= 0)
        position_size, details = engine.calculate_kelly_criterion_size(
            funds, win_probability=0.6, win_loss_ratio=0.0, symbol="NIFTY"
        )
        assert position_size == 0
        assert details["reason"] == "invalid_win_loss_ratio"

    def test_calculate_kelly_criterion_size_fractional_kelly(self) -> None:
        """Test Kelly Criterion sizing with fractional Kelly."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with high probability (should use 1/4 Kelly)
        position_size, details = engine.calculate_kelly_criterion_size(
            funds, win_probability=0.7, win_loss_ratio=3.0, symbol="NIFTY"
        )

        assert details["effective_fraction"] == details["kelly_fraction"] * 0.25


class TestMarginAwareSizing:
    """Test margin-aware sizing calculations."""

    def test_calculate_margin_aware_size_basic(self) -> None:
        """Test basic margin-aware sizing."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with reasonable margin requirement
        position_size, details = engine.calculate_margin_aware_size(
            funds,
            entry_price=100.0,
            stop_loss=95.0,
            margin_requirement=0.1,
            symbol="NIFTY",
        )

        assert position_size > 0
        assert details["method"] == "margin_aware"
        assert details["margin_requirement"] == 0.1
        assert "margin_per_unit" in details
        assert "total_margin_required" in details
        assert "available_margin" in details
        assert "margin_utilization" in details

    def test_calculate_margin_aware_size_high_margin(self) -> None:
        """Test margin-aware sizing with high margin requirement."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=2000.0,  # Low available margin
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with high margin requirement that exceeds available margin
        position_size, details = engine.calculate_margin_aware_size(
            funds,
            entry_price=100.0,
            stop_loss=95.0,
            margin_requirement=0.2,
            symbol="NIFTY",
        )

        assert position_size > 0
        assert details["adjusted_size"] <= details["base_size"]

    def test_calculate_margin_aware_size_zero_base(self) -> None:
        """Test margin-aware sizing when base size is zero."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid prices (should result in zero base size)
        position_size, details = engine.calculate_margin_aware_size(
            funds,
            entry_price=0.0,
            stop_loss=95.0,
            margin_requirement=0.1,
            symbol="NIFTY",
        )

        assert position_size == 0
        assert details["margin_adjustment"] == "skipped"


class TestCostAwareSizing:
    """Test cost-aware sizing calculations."""

    def test_calculate_cost_aware_size_basic(self) -> None:
        """Test basic cost-aware sizing."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with reasonable cost per lot
        position_size, details = engine.calculate_cost_aware_size(
            funds, entry_price=100.0, stop_loss=95.0, cost_per_lot=10.0, symbol="NIFTY"
        )

        assert position_size > 0
        assert details["method"] == "cost_aware"
        assert details["cost_per_lot"] == 10.0
        assert "total_cost" in details
        assert "risk_capital" in details
        assert "net_risk_capital" in details

    def test_calculate_cost_aware_size_high_costs(self) -> None:
        """Test cost-aware sizing with high costs."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=1000.0,
            utilized_margin=200.0,
            available_margin=500.0,
            total_equity=1500.0,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with high costs that exceed risk capital
        position_size, details = engine.calculate_cost_aware_size(
            funds, entry_price=100.0, stop_loss=95.0, cost_per_lot=100.0, symbol="NIFTY"
        )

        assert position_size == 0
        assert details["cost_adjustment"] == "blocked_by_costs"

    def test_calculate_cost_aware_size_zero_base(self) -> None:
        """Test cost-aware sizing when base size is zero."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        # Test with invalid prices (should result in zero base size)
        position_size, details = engine.calculate_cost_aware_size(
            funds, entry_price=0.0, stop_loss=95.0, cost_per_lot=10.0, symbol="NIFTY"
        )

        assert position_size == 0
        assert details["cost_adjustment"] == "skipped"


class TestPortfolioRiskAllocation:
    """Test portfolio risk allocation calculations."""

    def test_calculate_portfolio_risk_allocation_basic(self) -> None:
        """Test basic portfolio risk allocation."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="NIFTY",
                quantity=50,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            ),
            Trade(
                trade_id="trade-002",
                symbol="BANKNIFTY",
                quantity=30,
                entry_price=200.0,
                stop_loss=190.0,
                target=210.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            ),
        ]

        result = engine.calculate_portfolio_risk_allocation(
            funds, current_positions, target_risk_per_position=0.02
        )

        assert result["available_capital"] == 15000.0
        assert result["total_portfolio_value"] == 15000.0
        assert "current_risk_exposure" in result
        assert "max_total_risk" in result
        assert "remaining_risk_budget" in result
        assert "position_risk_breakdown" in result
        assert "risk_utilization" in result

    def test_calculate_portfolio_risk_allocation_no_positions(self) -> None:
        """Test portfolio risk allocation with no current positions."""
        engine = SizingEngine()

        funds = FundsData(
            available_cash=10000.0,
            available_margin=5000.0,
            total_equity=15000.0,
            utilized_margin=2000.0,
            margin_utilization=0.15,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
        )

        result = engine.calculate_portfolio_risk_allocation(
            funds, [], target_risk_per_position=0.02
        )

        assert result["current_risk_exposure"] == 0.0
        assert result["position_risk_breakdown"] == {}


class TestSizingMethodRecommendation:
    """Test sizing method recommendation functionality."""

    def test_get_recommended_sizing_method_high_probability(self) -> None:
        """Test sizing method recommendation with high win probability."""
        engine = SizingEngine()

        method = engine.get_recommended_sizing_method(
            volatility=0.03, win_probability=0.7, margin_requirement=0.05
        )

        assert method == SizingMethod.KELLY_CRITERION

    def test_get_recommended_sizing_method_high_margin(self) -> None:
        """Test sizing method recommendation with high margin requirement."""
        engine = SizingEngine()

        method = engine.get_recommended_sizing_method(
            volatility=0.03, win_probability=0.5, margin_requirement=0.15
        )

        assert method == SizingMethod.FIXED_FRACTION

    def test_get_recommended_sizing_method_high_volatility(self) -> None:
        """Test sizing method recommendation with high volatility."""
        engine = SizingEngine()

        method = engine.get_recommended_sizing_method(
            volatility=0.08, win_probability=0.5, margin_requirement=0.05
        )

        assert method == SizingMethod.VOLATILITY_BASED

    def test_get_recommended_sizing_method_default(self) -> None:
        """Test default sizing method recommendation."""
        engine = SizingEngine()

        method = engine.get_recommended_sizing_method(
            volatility=0.02, win_probability=0.5, margin_requirement=0.05
        )

        assert method == SizingMethod.FIXED_FRACTION


class TestModuleLevelSingleton:
    """Test module-level singleton instance."""

    def test_sizing_engine_singleton(self) -> None:
        """Test that sizing_engine is a proper singleton."""

        assert isinstance(sizing_engine, SizingEngine)
        assert sizing_engine.fixed_fraction == 0.02

        # Test that it's the same instance
        from loats.sizing import sizing_engine as sizing_engine_2

        assert sizing_engine is sizing_engine_2
