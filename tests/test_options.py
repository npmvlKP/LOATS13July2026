"""
Tests for options module.
"""

from datetime import datetime

import pytest
from py_vollib.black_scholes import black_scholes
from py_vollib.black_scholes.implied_volatility import implied_volatility

from src.loats.models import (
    Greeks,
    OptionContract,
    OptionType,
    VaRResult,
)
from src.loats.options import (
    OptionsAnalysis,
    calculate_greeks,
    calculate_historical_var,
    calculate_implied_volatility,
    calculate_var,
)


class TestOptionsAnalysis:
    """Test suite for OptionsAnalysis class."""

    @pytest.fixture()
    def options(self) -> OptionsAnalysis:
        """Create an OptionsAnalysis instance."""
        return OptionsAnalysis()

    @pytest.fixture()
    def sample_option_chain(self) -> dict:
        """Create sample option chain data for testing."""
        return {
            "expiry_dates": ["2023-01-26", "2023-02-02"],
            "options": [
                {
                    "symbol": "NIFTY23JAN18000CE",
                    "strike_price": 18000.0,
                    "expiry": "2023-01-26T15:30:00",
                    "option_type": "CE",
                    "last_price": 150.50,
                    "open_interest": 10000,
                    "volume": 5000,
                    "implied_volatility": 0.25,
                    "delta": 0.5,
                    "gamma": 0.02,
                    "theta": -0.05,
                    "vega": 0.1,
                    "rho": 0.03,
                },
                {
                    "symbol": "NIFTY23JAN18000PE",
                    "strike_price": 18000.0,
                    "expiry": "2023-01-26T15:30:00",
                    "option_type": "PE",
                    "last_price": 140.25,
                    "open_interest": 12000,
                    "volume": 6000,
                    "implied_volatility": 0.26,
                    "delta": -0.5,
                    "gamma": 0.02,
                    "theta": -0.06,
                    "vega": 0.1,
                    "rho": -0.03,
                },
                {
                    "symbol": "NIFTY23JAN18100CE",
                    "strike_price": 18100.0,
                    "expiry": "2023-01-26T15:30:00",
                    "option_type": "CE",
                    "last_price": 100.75,
                    "open_interest": 8000,
                    "volume": 4000,
                    "implied_volatility": 0.24,
                    "delta": 0.4,
                    "gamma": 0.015,
                    "theta": -0.04,
                    "vega": 0.08,
                    "rho": 0.025,
                },
                {
                    "symbol": "NIFTY23JAN18100PE",
                    "strike_price": 18100.0,
                    "expiry": "2023-01-26T15:30:00",
                    "option_type": "PE",
                    "last_price": 160.50,
                    "open_interest": 9000,
                    "volume": 4500,
                    "implied_volatility": 0.27,
                    "delta": -0.6,
                    "gamma": 0.025,
                    "theta": -0.07,
                    "vega": 0.12,
                    "rho": -0.04,
                },
            ],
        }

    def test_calculate_greeks(self) -> None:
        """Test calculate_greeks function."""
        # Test call option
        greeks = calculate_greeks(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,  # 30 days
            risk_free_rate=0.05,
            volatility=0.25,
            option_price=150.50,
        )

        assert isinstance(greeks, Greeks)
        assert greeks.delta > 0  # Call delta should be positive
        assert greeks.gamma > 0
        assert greeks.theta < 0  # Theta should be negative
        assert greeks.vega > 0
        assert greeks.rho > 0  # Call rho should be positive
        assert greeks.implied_volatility == 0.25

        # Test put option
        greeks = calculate_greeks(
            option_type=OptionType.PUT,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            volatility=0.25,
            option_price=140.25,
        )

        assert isinstance(greeks, Greeks)
        assert greeks.delta < 0  # Put delta should be negative
        assert greeks.gamma > 0
        assert greeks.theta < 0  # Theta should be negative
        assert greeks.vega > 0
        assert greeks.rho < 0  # Put rho should be negative

    def test_calculate_implied_volatility(self) -> None:
        """Test calculate_implied_volatility function."""
        # Test call option
        iv = calculate_implied_volatility(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            option_price=150.50,
        )

        assert isinstance(iv, float)
        assert iv > 0
        assert iv < 1  # IV should be between 0 and 1

        # Test put option
        iv = calculate_implied_volatility(
            option_type=OptionType.PUT,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            option_price=140.25,
        )

        assert isinstance(iv, float)
        assert iv > 0
        assert iv < 1

        # Test with known values (should match py_vollib result)
        # Using py_vollib directly to get expected IV
        expected_iv = implied_volatility(
            price=150.50,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            flag="c",
        )

        iv = calculate_implied_volatility(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            option_price=150.50,
        )

        assert abs(iv - expected_iv) < 0.01  # Should be close to py_vollib result

    def test_calculate_var(self) -> None:
        """Test calculate_var function."""
        # Test with historical method
        var = calculate_var(
            prices=[18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950],
            confidence_level=0.95,
            time_horizon=1,
            method="historical",
        )

        assert isinstance(var, VaRResult)
        assert var.confidence_level == 0.95
        assert var.time_horizon == 1
        assert var.method == "historical"
        assert var.var_value > 0
        assert 0 < var.var_percent < 100

        # Test with parametric method
        var = calculate_var(
            prices=[18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950],
            confidence_level=0.95,
            time_horizon=1,
            method="parametric",
        )

        assert isinstance(var, VaRResult)
        assert var.method == "parametric"
        assert var.var_value > 0

        # Test with monte_carlo method
        var = calculate_var(
            prices=[18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950],
            confidence_level=0.95,
            time_horizon=1,
            method="monte_carlo",
        )

        assert isinstance(var, VaRResult)
        assert var.method == "monte_carlo"
        assert var.var_value > 0

    def test_calculate_historical_var(self) -> None:
        """Test calculate_historical_var function."""
        prices = [18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950]

        var = calculate_historical_var(prices, confidence_level=0.95)

        assert isinstance(var, VaRResult)
        assert var.confidence_level == 0.95
        assert var.method == "historical"
        assert var.var_value > 0
        assert 0 < var.var_percent < 100

        # Test with different confidence levels
        var_90 = calculate_historical_var(prices, confidence_level=0.90)
        var_99 = calculate_historical_var(prices, confidence_level=0.99)

        assert (
            var_90.var_value < var_95.var_value
        )  # Lower confidence should have lower VaR
        assert (
            var_99.var_value > var_95.var_value
        )  # Higher confidence should have higher VaR

    def test_get_atm_strike(
        self,
        options: OptionsAnalysis,
        sample_option_chain: dict,
    ) -> None:
        """Test get_atm_strike method."""
        # Test with spot price at 18000 (exact strike)
        atm_strike = options.get_atm_strike(sample_option_chain, 18000.0)
        assert atm_strike == 18000.0

        # Test with spot price between strikes
        atm_strike = options.get_atm_strike(sample_option_chain, 18050.0)
        assert atm_strike == 18100.0  # Should round to nearest strike

        # Test with spot price below lowest strike
        atm_strike = options.get_atm_strike(sample_option_chain, 17900.0)
        assert atm_strike == 18000.0  # Should return lowest strike

        # Test with spot price above highest strike
        atm_strike = options.get_atm_strike(sample_option_chain, 18200.0)
        assert atm_strike == 18100.0  # Should return highest strike

    def test_analyze_option_chain(
        self,
        options: OptionsAnalysis,
        sample_option_chain: dict,
    ) -> None:
        """Test analyze_option_chain method."""
        analysis = options.analyze_option_chain(sample_option_chain, 18000.0)

        assert isinstance(analysis, dict)
        assert "atm_strike" in analysis
        assert "call_options" in analysis
        assert "put_options" in analysis
        assert "expiry_dates" in analysis
        assert "oi_analysis" in analysis
        assert "volatility_analysis" in analysis

        assert analysis["atm_strike"] == 18000.0
        assert len(analysis["call_options"]) == 2
        assert len(analysis["put_options"]) == 2
        assert len(analysis["expiry_dates"]) == 2

        # Check that options are properly sorted
        call_strikes = [opt.strike_price for opt in analysis["call_options"]]
        put_strikes = [opt.strike_price for opt in analysis["put_options"]]

        assert call_strikes == sorted(call_strikes)  # Should be sorted ascending
        assert put_strikes == sorted(put_strikes)  # Should be sorted ascending

    def test_calculate_open_interest_analysis(
        self,
        options: OptionsAnalysis,
        sample_option_chain: dict,
    ) -> None:
        """Test calculate_open_interest_analysis method."""
        analysis = options._calculate_open_interest_analysis(sample_option_chain)

        assert isinstance(analysis, dict)
        assert "total_call_oi" in analysis
        assert "total_put_oi" in analysis
        assert "put_call_ratio" in analysis
        assert "max_call_oi" in analysis
        assert "max_put_oi" in analysis
        assert "max_call_strike" in analysis
        assert "max_put_strike" in analysis

        assert analysis["total_call_oi"] == 18000  # 10000 + 8000
        assert analysis["total_put_oi"] == 21000  # 12000 + 9000
        assert analysis["put_call_ratio"] == 21000 / 18000
        assert analysis["max_call_oi"] == 10000
        assert analysis["max_put_oi"] == 12000
        assert analysis["max_call_strike"] == 18000.0
        assert analysis["max_put_strike"] == 18000.0

    def test_calculate_volatility_analysis(
        self,
        options: OptionsAnalysis,
        sample_option_chain: dict,
    ) -> None:
        """Test calculate_volatility_analysis method."""
        analysis = options._calculate_volatility_analysis(sample_option_chain)

        assert isinstance(analysis, dict)
        assert "avg_call_iv" in analysis
        assert "avg_put_iv" in analysis
        assert "iv_skew" in analysis
        assert "max_call_iv" in analysis
        assert "max_put_iv" in analysis
        assert "min_call_iv" in analysis
        assert "min_put_iv" in analysis

        assert analysis["avg_call_iv"] == (0.25 + 0.24) / 2
        assert analysis["avg_put_iv"] == (0.26 + 0.27) / 2
        assert analysis["iv_skew"] == analysis["avg_put_iv"] - analysis["avg_call_iv"]
        assert analysis["max_call_iv"] == 0.25
        assert analysis["max_put_iv"] == 0.27
        assert analysis["min_call_iv"] == 0.24
        assert analysis["min_put_iv"] == 0.26

    def test_calculate_option_metrics(self, options: OptionsAnalysis) -> None:
        """Test calculate_option_metrics method."""
        # Test call option
        option_data = {
            "symbol": "NIFTY23JAN18000CE",
            "strike_price": 18000.0,
            "expiry": "2023-01-26T15:30:00",
            "option_type": "CE",
            "last_price": 150.50,
            "open_interest": 10000,
            "volume": 5000,
            "implied_volatility": 0.25,
            "delta": 0.5,
            "gamma": 0.02,
            "theta": -0.05,
            "vega": 0.1,
            "rho": 0.03,
        }

        metrics = options._calculate_option_metrics(option_data, 18000.0)

        assert isinstance(metrics, dict)
        assert "intrinsic_value" in metrics
        assert "extrinsic_value" in metrics
        assert "moneyness" in metrics
        assert "leverage" in metrics
        assert "oi_change" in metrics  # Should be 0 since we don't have previous OI
        assert (
            "volume_change" in metrics
        )  # Should be 0 since we don't have previous volume

        assert metrics["intrinsic_value"] == 0.0  # ATM option
        assert metrics["extrinsic_value"] == 150.50
        assert metrics["moneyness"] == 0.0  # ATM
        assert metrics["leverage"] > 0

        # Test ITM call option
        option_data["strike_price"] = 17900.0
        metrics = options._calculate_option_metrics(option_data, 18000.0)

        assert metrics["intrinsic_value"] == 100.0  # 18000 - 17900
        assert metrics["extrinsic_value"] == 50.50  # 150.50 - 100.0
        assert metrics["moneyness"] > 0  # ITM

        # Test OTM call option
        option_data["strike_price"] = 18100.0
        metrics = options._calculate_option_metrics(option_data, 18000.0)

        assert metrics["intrinsic_value"] == 0.0  # OTM option
        assert metrics["extrinsic_value"] == 150.50
        assert metrics["moneyness"] < 0  # OTM

        # Test put option
        option_data = {
            "symbol": "NIFTY23JAN18000PE",
            "strike_price": 18000.0,
            "expiry": "2023-01-26T15:30:00",
            "option_type": "PE",
            "last_price": 140.25,
            "open_interest": 12000,
            "volume": 6000,
            "implied_volatility": 0.26,
            "delta": -0.5,
            "gamma": 0.02,
            "theta": -0.06,
            "vega": 0.1,
            "rho": -0.03,
        }

        metrics = options._calculate_option_metrics(option_data, 18000.0)

        assert metrics["intrinsic_value"] == 0.0  # ATM option
        assert metrics["extrinsic_value"] == 140.25

        # Test ITM put option
        option_data["strike_price"] = 18100.0
        metrics = options._calculate_option_metrics(option_data, 18000.0)

        assert metrics["intrinsic_value"] == 100.0  # 18100 - 18000
        assert metrics["extrinsic_value"] == 40.25  # 140.25 - 100.0

    def test_black_scholes_consistency(self) -> None:
        """Test that our Black-Scholes implementation is consistent with py_vollib."""
        # Test parameters
        S = 18000.0  # Spot price
        K = 18000.0  # Strike price
        t = 30 / 365  # Time to expiry (30 days)
        r = 0.05  # Risk-free rate
        sigma = 0.25  # Volatility

        # Calculate call price using py_vollib
        expected_call_price = black_scholes(flag="c", S=S, K=K, t=t, r=r, sigma=sigma)

        # Calculate call price using our implementation
        greeks = calculate_greeks(
            option_type=OptionType.CALL,
            spot_price=S,
            strike_price=K,
            time_to_expiry=t,
            risk_free_rate=r,
            volatility=sigma,
            option_price=expected_call_price,  # Use the same price for consistency
        )

        # The calculated price should be very close to py_vollib
        calculated_call_price = greeks.price
        assert abs(calculated_call_price - expected_call_price) < 0.01

        # Test put option
        expected_put_price = black_scholes(flag="p", S=S, K=K, t=t, r=r, sigma=sigma)

        greeks = calculate_greeks(
            option_type=OptionType.PUT,
            spot_price=S,
            strike_price=K,
            time_to_expiry=t,
            risk_free_rate=r,
            volatility=sigma,
            option_price=expected_put_price,
        )

        calculated_put_price = greeks.price
        assert abs(calculated_put_price - expected_put_price) < 0.01

    def test_edge_cases(self) -> None:
        """Test edge cases for options calculations."""
        # Test with zero time to expiry
        greeks = calculate_greeks(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=0.0,
            risk_free_rate=0.05,
            volatility=0.25,
            option_price=0.0,
        )

        # For zero time to expiry, ATM option should have delta ~0.5
        assert abs(greeks.delta - 0.5) < 0.1

        # Test with very small volatility
        greeks = calculate_greeks(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            volatility=0.001,
            option_price=0.0,
        )

        assert greeks.delta > 0.9  # Should be very close to 1 for very low volatility

        # Test with very high volatility
        greeks = calculate_greeks(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            volatility=10.0,  # 1000% volatility
            option_price=0.0,
        )

        assert (
            abs(greeks.delta - 0.5) < 0.1
        )  # Should be close to 0.5 for very high volatility

        # Test implied volatility with extreme prices
        iv = calculate_implied_volatility(
            option_type=OptionType.CALL,
            spot_price=18000.0,
            strike_price=18000.0,
            time_to_expiry=30 / 365,
            risk_free_rate=0.05,
            option_price=10000.0,  # Extremely high price
        )

        assert iv > 1.0  # Should be very high

        # Test VaR with empty price list
        with pytest.raises(ValueError):
            calculate_var([], confidence_level=0.95, time_horizon=1)

        # Test VaR with single price
        var = calculate_var([18000.0], confidence_level=0.95, time_horizon=1)
        assert var.var_value == 0.0  # No variation with single price

    def test_option_contract_model(self) -> None:
        """Test OptionContract model."""
        contract = OptionContract(
            symbol="NIFTY23JAN18000CE",
            strike_price=18000.0,
            expiry=datetime(2023, 1, 26, 15, 30),
            option_type=OptionType.CALL,
            last_price=150.50,
            open_interest=10000,
            volume=5000,
            implied_volatility=0.25,
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            rho=0.03,
        )

        assert contract.symbol == "NIFTY23JAN18000CE"
        assert contract.strike_price == 18000.0
        assert contract.option_type == OptionType.CALL
        assert contract.last_price == 150.50
        assert contract.implied_volatility == 0.25
        assert contract.delta == 0.5

        # Test model validation
        with pytest.raises(ValueError):
            OptionContract(
                symbol="NIFTY23JAN18000CE",
                strike_price=-18000.0,  # Negative strike price
                expiry=datetime(2023, 1, 26, 15, 30),
                option_type=OptionType.CALL,
                last_price=150.50,
                open_interest=10000,
                volume=5000,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.02,
                theta=-0.05,
                vega=0.1,
                rho=0.03,
            )

        with pytest.raises(ValueError):
            OptionContract(
                symbol="NIFTY23JAN18000CE",
                strike_price=18000.0,
                expiry=datetime(2023, 1, 26, 15, 30),
                option_type=OptionType.CALL,
                last_price=-150.50,  # Negative price
                open_interest=10000,
                volume=5000,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.02,
                theta=-0.05,
                vega=0.1,
                rho=0.03,
            )

    def test_greeks_model(self) -> None:
        """Test Greeks model."""
        greeks = Greeks(
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            rho=0.03,
            implied_volatility=0.25,
        )

        assert greeks.delta == 0.5
        assert greeks.gamma == 0.02
        assert greeks.theta == -0.05
        assert greeks.vega == 0.1
        assert greeks.rho == 0.03
        assert greeks.implied_volatility == 0.25

        # Test that price is calculated correctly
        # For a call option with these greeks, price should be approximately:
        # delta * S + 0.5 * gamma * S^2 + theta * t + vega * sigma + rho * r
        # But this is a simplification - actual price calculation is more complex
        assert greeks.price is not None

    def test_var_result_model(self) -> None:
        """Test VaRResult model."""
        var = VaRResult(
            confidence_level=0.95,
            time_horizon=1,
            var_value=1000.0,
            var_percent=1.0,
            historical_var=950.0,
            method="historical",
            timestamp=datetime.now(),
        )

        assert var.confidence_level == 0.95
        assert var.time_horizon == 1
        assert var.var_value == 1000.0
        assert var.var_percent == 1.0
        assert var.historical_var == 950.0
        assert var.method == "historical"

        # Test model validation
        with pytest.raises(ValueError):
            VaRResult(
                confidence_level=1.5,  # Invalid confidence level
                time_horizon=1,
                var_value=1000.0,
                var_percent=1.0,
                historical_var=950.0,
                method="historical",
            )

        with pytest.raises(ValueError):
            VaRResult(
                confidence_level=0.95,
                time_horizon=-1,  # Negative time horizon
                var_value=1000.0,
                var_percent=1.0,
                historical_var=950.0,
                method="historical",
            )
