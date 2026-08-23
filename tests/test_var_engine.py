"""Test cases for Value-at-Risk module"""

from decimal import Decimal
from unittest import TestCase, mock

import numpy as np
import pytest

from src.var_engine import VaREngine


class TestVaREngine(TestCase):
    def setUp(self):
        self.engine = VaREngine(confidence_level=0.99, window_size=252)

        self.bond_prices = [Decimal(str(i)) for i in range(50, 100)]  # 50 data points
        self.equity_prices = [Decimal(str(100 + i)) for i in range(252)]
        self.extreme_vol_prices = [Decimal(str(i * i)) for i in range(20, 30)]
        self.small_sample = [Decimal(str(i)) for i in range(10)]

    def test_historical_standalone(self):
        """Test basic historical simulation method"""
        values = [100, 50000, 1000000]

        for val in values:
            result = self.engine.historical_standalone(
                self.equity_prices, Decimal(str(val))
            )

            assert isinstance(result["var"], Decimal)
            assert isinstance(result["expected_shortfall"], Decimal)
            assert 0 <= result["cv"] <= Decimal("0.5")

    def test_historical_standalone_delta_risk(self):
        """Test historical standalone with delta risk enabled"""
        result = self.engine.historical_standalone(
            self.equity_prices, Decimal("50000"), delta_risk=True
        )

        assert isinstance(result["var"], Decimal)
        assert isinstance(result["delta"], Decimal)
        assert isinstance(result["expected_shortfall"], Decimal)

    def test_historical_standalone_multi_day(self):
        """Test historical standalone with multi-day holding period (days > 1)"""
        # This tests the multi-day returns calculation path (lines 91-93)
        result = self.engine.historical_standalone(
            self.equity_prices, Decimal("50000"), days=5
        )

        assert isinstance(result["var"], Decimal)
        assert isinstance(result["expected_shortfall"], Decimal)

    def test_historical_standalone_insufficient_data(self):
        """Test historical standalone with insufficient data"""
        small_engine = VaREngine(window_size=10)
        with pytest.raises(ValueError, match="Insufficient historical data"):
            small_engine.historical_standalone(self.equity_prices[:5], Decimal("50000"))

    def test_parametric_normal(self):
        """Test basic parametric method"""
        # Use enough data points for the days parameter
        result = self.engine.parametric_normal(
            self.bond_prices,  # 50 data points
            Decimal("50000"),
            days=10,  # Need days < len(prices)
        )

        assert isinstance(result["var"], Decimal)
        # z_score for 99% confidence is negative (left tail)
        assert result["z_score"] < Decimal("-2.32")  # ~99th percentile (negative)

        # Test fat tail adjustment
        fat_tail_result = self.engine.parametric_normal(
            self.bond_prices, Decimal("50000"), days=10, fat_tail_adjustment=1.5
        )

        # With fat_tail_adjustment > 1, z_score becomes more negative
        assert fat_tail_result["z_score"] < result["z_score"]
        # And VaR becomes larger (more conservative)
        assert fat_tail_result["var"] > result["var"]

    def test_parametric_normal_es_adjustment(self):
        """Test parametric normal with ES adjustment (Cornish-Fisher)"""
        # This tests _calculate_es_adjustment (lines 290-299)
        result = self.engine.parametric_normal(
            self.equity_prices, Decimal("100000"), days=10, fat_tail_adjustment=1.5
        )

        assert isinstance(result["var"], Decimal)
        assert isinstance(result["expected_shortfall"], Decimal)
        # ES should be >= VaR
        assert result["expected_shortfall"] >= result["var"]

    def test_parametric_normal_bond_volatility(self):
        """Test parametric normal with bond volatility path (< 50 price)"""
        # This tests _calculate_volatility bond path (line 309)
        bond_prices_low = [Decimal(str(i)) for i in range(10, 30)]  # prices < 50
        result = self.engine.parametric_normal(
            bond_prices_low, Decimal("50000"), days=5
        )

        assert isinstance(result["var"], Decimal)

    def test_monte_carlo_basic(self):
        """Test basic Monte Carlo simulation"""
        result = self.engine.monte_carlo(
            current_price=Decimal("200"), value=Decimal("200000"), samples=1000
        )

        assert isinstance(result["var"], Decimal)
        # CVaR (Expected Shortfall) should be >= VaR (more conservative)
        assert result["cvar"] >= result["var"]
        assert result["ci_width"] > Decimal("0")

    def test_monte_carlo_jensen_uhlenbeck(self):
        """Test Monte Carlo with Jensen-Uhlenbeck mean-reverting process"""
        # This tests _brownian_jensen_uhlenbeck (lines 410-426)
        result = self.engine.monte_carlo(
            current_price=Decimal("200"),
            value=Decimal("200000"),
            samples=500,
            JensenUhlenbeck=True,
            tau=0.05,
        )

        assert isinstance(result["var"], Decimal)
        assert isinstance(result["cvar"], Decimal)

    def test_monte_carlo_float32_encoding(self):
        """Test Monte Carlo with float32 encoding"""
        # This tests the float32 encoding path (lines 437-440)
        result = self.engine.monte_carlo(
            current_price=Decimal("200"),
            value=Decimal("200000"),
            samples=500,
            encoding="float32",
        )

        assert isinstance(result["var"], Decimal)

    def test_monte_carlo_free_cash_flows(self):
        """Test Monte Carlo with free cash flows adjustment"""
        # This tests the free_cash_flows path and _calculate_fcf_impact (lines 469-484)
        result = self.engine.monte_carlo(
            current_price=Decimal("200"),
            value=Decimal("200000"),
            samples=500,
            free_cash_flows=True,
            days=15,  # Need days > 10 for FCF impact
        )

        assert isinstance(result["var"], Decimal)
        assert "fcf_impact" in result
        assert "adjusted_var" in result

    def test_monte_carlo_anticorrelated(self):
        """Test Monte Carlo with anticorrelated generator"""
        result = self.engine.monte_carlo(
            current_price=Decimal("200"),
            value=Decimal("200000"),
            samples=500,
            anticorrelated=True,
        )

        assert isinstance(result["var"], Decimal)

    def test_edge_cases(self):
        """Test edge cases for all methods"""
        # Historical simulation with small window
        small_engine = VaREngine(window_size=10)
        with pytest.raises(ValueError):
            small_engine.historical_standalone(self.equity_prices[:5], Decimal("50000"))

        # Parametric with low data points - just test it runs with warning
        with mock.patch("src.var_engine.logger") as mock_logger:
            self.engine.parametric_normal(self.small_sample, Decimal("50000"), days=5)
            assert mock_logger.warning.called

        # Monte Carlo with invalid samples
        with pytest.raises(ValueError):
            self.engine.monte_carlo(
                current_price=Decimal("100"), value=Decimal("50000"), samples=0
            )

    def test_method_comparison(self):
        """Compare results from different methods"""
        # These are not meant to be exact but test for general consistency
        methods = [
            self.engine.historical_standalone,
            self.engine.parametric_normal,
            lambda prices, value: self.engine.monte_carlo(
                current_price=prices[-1] if prices else Decimal("100"), value=value
            ),
        ]

        # Get baseline from historical method
        historical_result = self.engine.historical_standalone(
            self.equity_prices, Decimal("250000")
        )
        historical_var = historical_result["var"]

        for method in methods[1:]:
            result = method(self.equity_prices, Decimal("250000"))

            if isinstance(result, dict):
                test_var = result.get("var", result.get("var_value", None))
            else:
                test_var = result

            if test_var is not None:
                ratio = abs((test_var - historical_var) / historical_var)
                # Different VaR methods can produce significantly different results
                # This test just ensures they produce reasonable positive values
                assert ratio < Decimal("2.0"), (
                    "Methods should produce reasonable results"
                )

    def test_rounding_differences(self):
        """Test handling of rounding differences in Decimal calculations"""
        abs_diff = abs(self.engine._to_decimal(0.1) - Decimal("0.1"))
        assert abs_diff <= Decimal("1e-15"), "Basic rounding error"

        calculation = Decimal("100.25") * Decimal("0.84")
        assert calculation == self.engine._to_decimal(100.25 * 0.84)

    def test_numeric_integrity_historical(self):
        """Test basic numeric integrity for historical method"""
        method = self.engine.historical_standalone
        args = (self.equity_prices, Decimal("50000"))

        result = method(*args)

        assert isinstance(result, dict), "Should return dict"
        assert "var" in result, "Missing var key"
        assert result["var"] >= Decimal("0"), "Negative VaR"
        assert Decimal("-Infinity") < result["var"] < Decimal("Infinity"), (
            "Out of bounds"
        )

    def test_numeric_integrity_parametric(self):
        """Test basic numeric integrity for parametric method"""
        method = self.engine.parametric_normal
        args = (self.equity_prices, Decimal("50000"))

        result = method(*args)

        assert isinstance(result, dict), "Should return dict"
        assert "var" in result, "Missing var key"
        assert result["var"] >= Decimal("0"), "Negative VaR"
        assert Decimal("-Infinity") < result["var"] < Decimal("Infinity"), (
            "Out of bounds"
        )

    def test_numeric_integrity_monte_carlo(self):
        """Test basic numeric integrity for monte carlo method"""
        method = self.engine.monte_carlo
        args = (Decimal("220"), Decimal("44000"), 5)

        result = method(*args)

        assert isinstance(result, dict), "Should return dict"
        assert "var" in result, "Missing var key"
        assert result["var"] >= Decimal("0"), "Negative VaR"
        assert Decimal("-Infinity") < result["var"] < Decimal("Infinity"), (
            "Out of bounds"
        )


class TestVaREngineValidation(TestCase):
    """Test validation methods"""

    def test_validate_confidence_invalid_high(self):
        """Test confidence level validation - too high"""
        with pytest.raises(
            ValueError, match="Confidence level must be between 0 and 1"
        ):
            VaREngine(confidence_level=1.5)

    def test_validate_confidence_invalid_low(self):
        """Test confidence level validation - too low"""
        with pytest.raises(
            ValueError, match="Confidence level must be between 0 and 1"
        ):
            VaREngine(confidence_level=-0.1)

    def test_validate_confidence_boundary_zero(self):
        """Test confidence level validation - zero boundary"""
        engine = VaREngine(confidence_level=0.0)
        assert engine.confidence_level == 0.0

    def test_validate_confidence_boundary_one(self):
        """Test confidence level validation - one boundary"""
        engine = VaREngine(confidence_level=1.0)
        assert engine.confidence_level == 1.0

    def test_validate_window_invalid_zero(self):
        """Test window size validation - zero"""
        with pytest.raises(ValueError, match="Window size must be > 0"):
            VaREngine(window_size=0)

    def test_validate_window_invalid_negative(self):
        """Test window size validation - negative"""
        with pytest.raises(ValueError, match="Window size must be > 0"):
            VaREngine(window_size=-5)

    def test_validate_datetime_valid(self):
        """Test datetime validation with valid datetime"""
        from datetime import datetime

        engine = VaREngine()
        dt = datetime(2024, 1, 15, 10, 30)
        result = engine._validate_datetime(dt)
        assert result.tzinfo is not None

    def test_validate_datetime_invalid_type(self):
        """Test datetime validation with invalid type"""
        engine = VaREngine()
        with pytest.raises(ValueError, match="Must provide datetime object"):
            engine._validate_datetime("2024-01-15")

    def test_validate_datetime_none(self):
        """Test datetime validation with None"""
        engine = VaREngine()
        with pytest.raises(ValueError, match="Must provide datetime object"):
            engine._validate_datetime(None)


class TestVaREngineHistoricalPortfolio(TestCase):
    """Test historical portfolio method"""

    def setUp(self):
        self.engine = VaREngine(confidence_level=0.95, window_size=50)

    def test_historical_portfolio_basic(self):
        """Test historical portfolio VaR calculation"""
        positions = {
            "RELIANCE": (Decimal("100"), 2500.0),
            "TCS": (Decimal("50"), 3200.0),
            "INFY": (Decimal("75"), 1450.0),
        }
        portfolio_value, var = self.engine.historical_portfolio(positions)

        assert isinstance(portfolio_value, Decimal)
        assert isinstance(var, Decimal)
        assert portfolio_value > Decimal("0")
        assert var >= Decimal("0")

    def test_historical_portfolio_empty(self):
        """Test historical portfolio with empty positions"""
        positions = {}
        portfolio_value, var = self.engine.historical_portfolio(positions)

        assert portfolio_value == Decimal("0")
        assert var == Decimal("0")


class TestVaREngineCalculate(TestCase):
    """Test the CMP-compliant calculate entry point"""

    def setUp(self):
        self.engine = VaREngine(confidence_level=0.95, window_size=10)

    def test_calculate_historical_standalone(self):
        """Test calculate with historical_standalone method"""
        prices = [Decimal(str(i)) for i in range(50, 100)]
        result = self.engine.calculate(
            "historical_standalone", prices=prices, value=Decimal("50000")
        )

        assert isinstance(result, dict)
        assert "var" in result
        assert result["var"] >= Decimal("0")

    def test_calculate_historical_portfolio(self):
        """Test calculate with historical_portfolio method"""
        positions = {
            "RELIANCE": (Decimal("100"), 2500.0),
            "TCS": (Decimal("50"), 3200.0),
        }
        result = self.engine.calculate("historical_portfolio", positions=positions)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] >= Decimal("0")
        assert result[1] >= Decimal("0")

    def test_calculate_parametric_normal(self):
        """Test calculate with parametric_normal method"""
        prices = [Decimal(str(i)) for i in range(50, 100)]
        result = self.engine.calculate(
            "parametric_normal", prices=prices, value=Decimal("50000"), days=10
        )

        assert isinstance(result, dict)
        assert "var" in result

    def test_calculate_monte_carlo(self):
        """Test calculate with monte_carlo method"""
        result = self.engine.calculate(
            "monte_carlo",
            current_price=Decimal("100"),
            value=Decimal("50000"),
            samples=100,
        )

        assert isinstance(result, dict)
        assert "var" in result

    def test_calculate_invalid_method(self):
        """Test calculate with invalid method"""
        with pytest.raises(ValueError, match="Unsupported method"):
            self.engine.calculate("invalid_method")

    def test_calculate_error_handling(self):
        """Test calculate method error handling (lines 516-518)"""
        # This triggers the exception handling in calculate()
        with pytest.raises(ValueError, match="Unsupported method"):
            self.engine.calculate("invalid_method")


class TestVaREngineCalculateDelta(TestCase):
    """Test _calculate_delta method"""

    def setUp(self):
        self.engine = VaREngine()

    def test_calculate_delta_with_sufficient_data(self):
        """Test delta calculation with enough returns data"""
        returns = np.random.normal(0, 0.02, 2000)
        result = self.engine._calculate_delta(returns)

        assert isinstance(result, Decimal)

    def test_calculate_delta_with_insufficient_data(self):
        """Test delta calculation with insufficient data (< 1000)"""
        returns = np.random.normal(0, 0.02, 500)
        result = self.engine._calculate_delta(returns)

        # Should handle gracefully, may return NaN or a value
        assert isinstance(result, Decimal)


class TestVaREngineCondVar(TestCase):
    """Test _calculate_cond_var method"""

    def setUp(self):
        self.engine = VaREngine()

    def test_calculate_cond_var_empty_array(self):
        """Test cond var with empty array (line 144)"""
        returns = np.array([])
        var_percent = -0.02
        result = self.engine._calculate_cond_var(returns, var_percent)

        assert result.is_nan()

    def test_calculate_cond_var_normal(self):
        """Test cond var with normal array"""
        returns = np.random.normal(0, 0.02, 1000)
        var_percent = np.percentile(returns, 5)  # 5th percentile for 95% confidence
        result = self.engine._calculate_cond_var(returns, var_percent)

        assert isinstance(result, Decimal)
        # Conditional VaR should be <= VaR percentile (more negative)
        assert float(result) <= var_percent


class TestVaREngineCV(TestCase):
    """Test _calculate_cv method"""

    def setUp(self):
        self.engine = VaREngine()

    def test_calculate_cv_zero_mean(self):
        """Test CV with zero mean returns"""
        returns = np.array([0.0, 0.0, 0.0])
        result = self.engine._calculate_cv(returns)

        assert result == Decimal("0")

    def test_calculate_cv_normal(self):
        """Test CV with normal returns"""
        returns = np.random.normal(0.01, 0.02, 1000)
        result = self.engine._calculate_cv(returns)

        assert isinstance(result, Decimal)
        assert result >= Decimal("0")


class TestVaREngineIntegration(TestCase):
    def setUp(self):
        self.engine = VaREngine(confidence_level=0.95, window_size=10)

    def test_cmp_integration(self):
        """Verify calculate method works"""
        # Use enough data points for the window size
        prices = [Decimal(str(i)) for i in range(50, 100)]
        result = self.engine.calculate(
            "historical_standalone", prices=prices, value=Decimal("50000")
        )

        assert isinstance(result, dict), type(result)
        assert "var" in result
        assert result["var"] >= Decimal("0")


class TestVaREngineToDecimal(TestCase):
    """Test _to_decimal helper method"""

    def setUp(self):
        self.engine = VaREngine()

    def test_to_decimal_various_inputs(self):
        """Test _to_decimal with various inputs"""
        test_cases = [
            (0.0, Decimal("0")),
            (0.1, Decimal("0.1")),
            (1.5, Decimal("1.5")),
            (-0.5, Decimal("-0.5")),
            (100.25, Decimal("100.25")),
            (1e-10, Decimal("1E-10")),
        ]

        for float_val, expected in test_cases:
            result = self.engine._to_decimal(float_val)
            assert result == expected, (
                f"Failed for {float_val}: got {result}, expected {expected}"
            )


class TestVaREngineUncoveredLines(TestCase):
    """Test uncovered lines in var_engine.py"""

    def setUp(self):
        self.engine = VaREngine(confidence_level=0.95, window_size=10)

    def test_calculate_delta_insufficient_data_returns_nan(self):
        """Test _calculate_delta with < 4 data points returns NaN (line 132)"""
        returns = np.array([0.01, 0.02])  # Only 2 points
        result = self.engine._calculate_delta(returns)
        assert result.is_nan()

    def test_calculate_cond_var_empty_grounded_returns_nan(self):
        """Test _calculate_cond_var when no returns below VaR threshold (line 155)"""
        returns = np.array([0.1, 0.2, 0.3])  # All positive, above VaR
        var_percent = -0.05
        result = self.engine._calculate_cond_var(returns, var_percent)
        assert result.is_nan()

    def test_historical_portfolio_zero_total_value(self):
        """Test historical_portfolio when total_value is zero (line 187)"""
        positions = {
            "ASSET1": (Decimal("0"), 100.0),
            "ASSET2": (Decimal("0"), 200.0),
        }
        portfolio_value, var = self.engine.historical_portfolio(positions)
        assert portfolio_value == Decimal("0")
        assert var == Decimal("0")

    def test_estimate_asset_volatility_low_price(self):
        """Test _estimate_asset_volatility for price < 50 (line 221)"""
        result = self.engine._estimate_asset_volatility("BOND", Decimal("30"))
        assert result == Decimal("0.05")

    def test_estimate_asset_volatility_mid_price(self):
        """Test _estimate_asset_volatility for price 50-500 (line 224)"""
        result = self.engine._estimate_asset_volatility("STOCK", Decimal("200"))
        assert result == Decimal("0.25")

    def test_estimate_asset_volatility_high_price(self):
        """Test _estimate_asset_volatility for price >= 500 (line 227)"""
        result = self.engine._estimate_asset_volatility("INDEX", Decimal("1000"))
        assert result == Decimal("0.20")

    def test_parametric_normal_not_enough_prices_for_days(self):
        """Test parametric_normal raises error when days >= len(prices) (line 265)"""
        prices = [Decimal(str(i)) for i in range(10)]  # 10 prices
        with pytest.raises(ValueError, match="Not enough prices for 10-day returns"):
            self.engine.parametric_normal(prices, Decimal("50000"), days=10)

    def test_parametric_normal_no_valid_returns_after_filtering(self):
        """Test parametric_normal raises error when all returns are NaN/Inf (line 289)"""
        # Create prices that will produce NaN/Inf after diff
        prices = [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
        with pytest.raises(
            ValueError, match="No valid returns calculated after filtering"
        ):
            self.engine.parametric_normal(prices, Decimal("50000"), days=1)

    def test_parametric_normal_invalid_fat_tail_adjustment(self):
        """Test parametric_normal raises error for invalid fat_tail_adjustment (line 297)"""
        prices = [Decimal(str(i)) for i in range(50, 100)]
        with pytest.raises(ValueError, match="fat_tail_adjustment must be > 0"):
            self.engine.parametric_normal(
                prices, Decimal("50000"), days=5, fat_tail_adjustment=0
            )
        with pytest.raises(ValueError, match="fat_tail_adjustment must be > 0"):
            self.engine.parametric_normal(
                prices, Decimal("50000"), days=5, fat_tail_adjustment=-1
            )

    def test_parametric_normal_risk_contribution_placeholder(self):
        """Test risk_contribution path in parametric_normal (line 325)"""
        prices = [Decimal(str(i)) for i in range(50, 100)]
        result = self.engine.parametric_normal(
            prices, Decimal("50000"), days=5, risk_contribution=True
        )
        # risk_contributions should be empty dict (placeholder)
        assert result["risk_contributions"] == {}

    def test_calculate_volatility_bond_path(self):
        """Test _calculate_volatility for bond prices < 50 (line 366)"""
        vol = self.engine._calculate_volatility(Decimal("30"), 10)
        assert vol == 0.05

    def test_calculate_method_exception_handling(self):
        """Test calculate method exception handling (lines 573-575)"""
        # This triggers the exception handling in calculate()
        # by passing invalid args to a valid method
        with pytest.raises(ValueError):
            self.engine.calculate(
                "historical_standalone", prices=[], value=Decimal("50000")
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
