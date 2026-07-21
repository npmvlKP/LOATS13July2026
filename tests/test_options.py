"""
Tests for options module.
"""

from datetime import datetime

import pytest
from vollib.black_scholes import black_scholes
from vollib.black_scholes.implied_volatility import implied_volatility

from src.loats.models import Greeks, OptionContract, OptionType
from src.loats.options import (
    ExpiredContractError,
    OptionsAnalysis,
    calculate_greeks,
    calculate_historical_var,
    calculate_implied_volatility,
    calculate_var,
)


class TestOptionsAnalysis:
    """Test suite for OptionsAnalysis class."""

    @pytest.fixture
    def options(self) -> OptionsAnalysis:
        """Create an OptionsAnalysis instance."""
        return OptionsAnalysis()

    @pytest.fixture
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

    def test_calculate_greeks(self, options: OptionsAnalysis) -> None:
        """Test calculate_greeks function."""
        # Test call option
        greeks = options.engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks, Greeks)
        assert 0 <= greeks.delta <= 1  # Delta for call options is between 0 and 1
        assert greeks.gamma >= 0
        assert greeks.vega >= 0
        assert greeks.theta <= 0  # Theta is typically negative
        # Rho can be larger than 1 for long-dated options, so we check it's a reasonable number
        assert -100 <= greeks.rho <= 100

        # Test standalone function
        greeks2 = calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks2, Greeks)
        assert greeks2.delta > 0  # Call delta should be positive
        assert greeks2.gamma > 0
        assert greeks2.theta < 0  # Theta should be negative
        assert greeks2.vega > 0
        assert greeks2.rho > 0  # Call rho should be positive

        # Test put option
        greeks_put = calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            sigma=0.25,
            option_type=OptionType.PUT,
        )

        assert isinstance(greeks_put, Greeks)
        assert greeks_put.delta < 0  # Put delta should be negative
        assert greeks_put.gamma > 0
        assert greeks_put.theta < 0  # Theta should be negative
        assert greeks_put.vega > 0
        assert greeks_put.rho < 0  # Put rho should be negative

    def test_calculate_implied_volatility(self, options: OptionsAnalysis) -> None:
        """Test calculate_implied_volatility function."""
        # Test call option
        iv = options.engine.calculate_implied_volatility(
            price=150.50,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.CALL,
        )

        assert isinstance(iv, float)
        assert 0 <= iv <= 1

        # Test standalone function
        iv2 = calculate_implied_volatility(
            price=150.50,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.CALL,
        )

        assert isinstance(iv2, float)
        assert iv2 > 0
        assert iv2 < 1  # IV should be between 0 and 1

        # Test with known values (should match vollib result)
        # Using vollib directly to get expected IV
        expected_iv = implied_volatility(
            price=150.50,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            flag="c",
        )

        iv3 = calculate_implied_volatility(
            price=150.50,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.CALL,
        )

        assert abs(iv3 - expected_iv) < 0.01  # Should be close to vollib result

    def test_calculate_var(self) -> None:
        """Test calculate_var function."""
        # Calculate returns from prices
        prices = [18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950]
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]

        var = calculate_var(
            returns=returns,
            confidence_level=0.95,
        )

        assert isinstance(var, float)
        assert var <= 0  # VaR should be negative or zero

        # Test with different confidence levels
        var_90 = calculate_var(returns, confidence_level=0.90)
        var_99 = calculate_var(returns, confidence_level=0.99)

        assert var_90 <= 0
        assert var_99 <= 0

    def test_calculate_historical_var(self) -> None:
        """Test calculate_historical_var function."""
        prices = [18000, 18050, 17950, 18100, 17900, 18000, 18050, 17950]

        var = calculate_historical_var(prices, confidence_level=0.95)

        assert isinstance(var, float)
        assert var <= 0  # VaR should be negative or zero

        # Test with different confidence levels
        var_90 = calculate_historical_var(prices, confidence_level=0.90)
        var_99 = calculate_historical_var(prices, confidence_level=0.99)

        assert var_90 <= 0
        assert var_99 <= 0

    def test_get_atm_strike(
        self,
        options: OptionsAnalysis,
        sample_option_chain: dict,
    ) -> None:
        """Test get_atm_strike method."""
        # Test with spot price at 18000 (exact strike)
        atm_strike = options.get_atm_strike(sample_option_chain, 18000.0)
        assert atm_strike == 18000.0

        # Test with spot price between strikes (18050 is closer to 18000 than 18100)
        atm_strike = options.get_atm_strike(sample_option_chain, 18050.0)
        assert atm_strike == 18000.0  # Should round to nearest strike

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
        call_strikes = [opt["strike_price"] for opt in analysis["call_options"]]
        put_strikes = [opt["strike_price"] for opt in analysis["put_options"]]

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
        assert "oi_change" in metrics
        assert "volume_change" in metrics

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

    def test_black_scholes_consistency(self, options: OptionsAnalysis) -> None:
        """Test that our Black-Scholes implementation is consistent with vollib."""
        # Test parameters
        S = 18000.0  # Spot price
        K = 18000.0  # Strike price
        t = 30 / 365  # Time to expiry (30 days)
        r = 0.05  # Risk-free rate
        sigma = 0.25  # Volatility

        # Calculate call price using vollib
        expected_call_price = black_scholes(flag="c", S=S, K=K, t=t, r=r, sigma=sigma)

        # Calculate call price using our implementation
        calculated_call_price = options.engine.calculate_black_scholes(
            S=S, K=K, t=t, sigma=sigma, option_type=OptionType.CALL
        )

        # The calculated price should be very close to vollib
        assert abs(calculated_call_price - expected_call_price) < 0.01

        # Test put option
        expected_put_price = black_scholes(flag="p", S=S, K=K, t=t, r=r, sigma=sigma)

        calculated_put_price = options.engine.calculate_black_scholes(
            S=S, K=K, t=t, sigma=sigma, option_type=OptionType.PUT
        )
        assert abs(calculated_put_price - expected_put_price) < 0.01

    def test_edge_cases(self, options: OptionsAnalysis) -> None:
        """Test edge cases for options calculations."""
        # Test ExpiredContractError is raised for t=0.0 (expired contract)
        with pytest.raises(ExpiredContractError) as exc_info:
            options.engine.calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=0.0,
                r=0.05,
                sigma=0.25,
                option_type=OptionType.CALL,
            )
        assert exc_info.value.time_to_expiry == 0.0

        # Test allow_expired=True returns Greeks for expired contracts
        greeks = options.engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=0.0,
            r=0.05,
            sigma=0.25,
            option_type=OptionType.CALL,
            allow_expired=True,
        )
        assert isinstance(greeks, Greeks)

        # Test standalone calculate_greeks raises ExpiredContractError
        with pytest.raises(ExpiredContractError):
            calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=0.0,
                r=0.05,
                sigma=0.25,
                option_type=OptionType.CALL,
            )

        # Test implied volatility raises ExpiredContractError for expired contract
        with pytest.raises(ExpiredContractError):
            options.engine.calculate_implied_volatility(
                price=100.0,
                S=18000.0,
                K=18000.0,
                t=0.0,
                r=0.05,
                option_type=OptionType.CALL,
            )

        # Test with very small time to expiry (should clamp to 0.0001)
        greeks = options.engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=0.00001,
            r=0.05,
            sigma=0.25,
            option_type=OptionType.CALL,
        )
        assert isinstance(greeks, Greeks)

        # Test with very small volatility
        greeks = options.engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            sigma=0.001,
            option_type=OptionType.CALL,
        )

        assert greeks.delta > 0.9  # Should be very close to 1 for very low volatility

        # Test with very high volatility
        greeks = options.engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            sigma=10.0,  # 1000% volatility
            option_type=OptionType.CALL,
        )

        # For very high volatility, delta should be between 0 and 1
        # The actual value depends on the Black-Scholes model implementation
        assert 0.0 <= greeks.delta <= 1.0

        # Test implied volatility with extreme prices
        iv = options.engine.calculate_implied_volatility(
            price=10000.0,  # Extremely high price
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.CALL,
        )

        assert iv > 1.0  # Should be very high

        # Test VaR with empty price list
        with pytest.raises(ValueError):
            calculate_var([], confidence_level=0.95)

        # Test VaR with single price
        var = calculate_var([0.01], confidence_level=0.95)
        assert var == 0.01  # Only one return value

    def test_expired_contract_error_attributes(self, options: OptionsAnalysis) -> None:
        """Test ExpiredContractError has correct attributes."""
        try:
            options.engine.calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=-0.5,  # Negative time (expired)
                r=0.05,
                sigma=0.25,
                option_type=OptionType.CALL,
            )
            pytest.fail("Expected ExpiredContractError to be raised")
        except ExpiredContractError as e:
            assert e.symbol is None  # Not provided in this call
            assert e.expiry is None  # Not provided in this call
            assert e.time_to_expiry == -0.5
            assert isinstance(e.symbol, (type(None), str))
            assert isinstance(e.expiry, (type(None), datetime))

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

        # Test with negative strike price (should not raise ValueError)
        # The OptionContract model doesn't have validation for negative strike price
        contract = OptionContract(
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
        assert contract.strike_price == -18000.0

        # Test with negative price (should raise ValueError)
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
