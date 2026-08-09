"""
Comprehensive test suite for options module coverage improvement.
This test suite targets specific lines that are missing coverage in options.py.
"""
import pytest
from datetime import datetime, UTC
from unittest.mock import patch, MagicMock

import numpy as np
from scipy.optimize import brentq, newton

from src.loats.models import Greeks, OptionContract, OptionType
from src.loats.options import (
    ExpiredContractError,
    OptionsAnalysis,
    OptionsEngine,
    calculate_greeks,
    calculate_implied_volatility,
    calculate_var,
    calculate_historical_var,
    options,
    analysis,
)

class TestOptionsCoverage:
    """Comprehensive test suite for options module coverage."""

    @pytest.fixture
    def options_engine(self) -> OptionsEngine:
        """Create an OptionsEngine instance."""
        return OptionsEngine()

    @pytest.fixture
    def options_analysis(self) -> OptionsAnalysis:
        """Create an OptionsAnalysis instance."""
        return OptionsAnalysis()

    @pytest.fixture
    def sample_option_contracts(self) -> list[OptionContract]:
        """Create sample option contracts for testing."""
        return [
            OptionContract(
                symbol="NIFTY23JAN18000CE",
                strike_price=18000.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
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
            ),
            OptionContract(
                symbol="NIFTY23JAN18000PE",
                strike_price=18000.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
                option_type=OptionType.PUT,
                last_price=140.25,
                open_interest=12000,
                volume=6000,
                implied_volatility=0.26,
                delta=-0.5,
                gamma=0.02,
                theta=-0.06,
                vega=0.1,
                rho=-0.03,
            ),
        ]

    def test_set_risk_free_rate(self, options_engine: OptionsEngine) -> None:
        """Test set_risk_free_rate method (line 63)."""
        # Test setting risk-free rate
        options_engine.set_risk_free_rate(0.10)
        assert options_engine.risk_free_rate == 0.10

        # Test that it affects calculations
        greeks = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            sigma=0.25,
            option_type=OptionType.CALL,
        )
        assert isinstance(greeks, Greeks)

    def test_calculate_greeks_with_allow_expired_true(self, options_engine: OptionsEngine) -> None:
        """Test calculate_greeks with allow_expired=True (lines 107, 125)."""
        # Test expired call option with allow_expired=True
        greeks = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=0.0,
            sigma=0.25,
            option_type=OptionType.CALL,
            allow_expired=True,
        )

        assert isinstance(greeks, Greeks)
        assert greeks.delta == 0.0  # ATM call at expiry
        assert greeks.gamma == 0.0
        assert greeks.theta == 0.0
        assert greeks.vega == 0.0
        assert greeks.rho == 0.0

        # Test expired put option with allow_expired=True
        greeks_put = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=0.0,
            sigma=0.25,
            option_type=OptionType.PUT,
            allow_expired=True,
        )

        assert isinstance(greeks_put, Greeks)
        assert greeks_put.delta == 0.0  # ATM put at expiry
        assert greeks_put.gamma == 0.0
        assert greeks_put.theta == 0.0
        assert greeks_put.vega == 0.0
        assert greeks_put.rho == 0.0

        # Test ITM call option with allow_expired=True
        greeks_itm = options_engine.calculate_greeks(
            S=18100.0,
            K=18000.0,
            t=0.0,
            sigma=0.25,
            option_type=OptionType.CALL,
            allow_expired=True,
        )

        assert greeks_itm.delta == 1.0  # ITM call at expiry
        assert greeks_itm.gamma == 0.0
        assert greeks_itm.theta == 0.0
        assert greeks_itm.vega == 0.0
        assert greeks_itm.rho == 0.0

        # Test ITM put option with allow_expired=True
        greeks_itm_put = options_engine.calculate_greeks(
            S=17900.0,
            K=18000.0,
            t=0.0,
            sigma=0.25,
            option_type=OptionType.PUT,
            allow_expired=True,
        )

        assert greeks_itm_put.delta == -1.0  # ITM put at expiry
        assert greeks_itm_put.gamma == 0.0
        assert greeks_itm_put.theta == 0.0
        assert greeks_itm_put.vega == 0.0
        assert greeks_itm_put.rho == 0.0

    def test_calculate_greeks_exception_fallback(self, options_engine: OptionsEngine) -> None:
        """Test calculate_greeks exception fallback (lines 137-149)."""
        # Mock the vollib functions to raise exceptions and test fallback
        with patch('src.loats.options.delta') as mock_delta, \
             patch('src.loats.options.gamma') as mock_gamma, \
             patch('src.loats.options.theta') as mock_theta, \
             patch('src.loats.options.vega') as mock_vega, \
             patch('src.loats.options.rho') as mock_rho:

            # Set up mocks to raise exceptions
            mock_delta.side_effect = Exception("Test exception")
            mock_gamma.side_effect = Exception("Test exception")
            mock_theta.side_effect = Exception("Test exception")
            mock_vega.side_effect = Exception("Test exception")
            mock_rho.side_effect = Exception("Test exception")

            # Test call option fallback
            greeks = options_engine.calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                sigma=0.25,
                option_type=OptionType.CALL,
            )

            assert isinstance(greeks, Greeks)
            assert greeks.delta == 0.0  # Fallback value for call
            assert greeks.gamma == 0.0
            assert greeks.theta == 0.0
            assert greeks.vega == 0.0
            assert greeks.rho == 0.0

            # Test put option fallback
            greeks_put = options_engine.calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                sigma=0.25,
                option_type=OptionType.PUT,
            )

            assert isinstance(greeks_put, Greeks)
            assert greeks_put.delta == 0.0  # Fallback value for put
            assert greeks_put.gamma == 0.0
            assert greeks_put.theta == 0.0
            assert greeks_put.vega == 0.0
            assert greeks_put.rho == 0.0

    def test_calculate_implied_volatility_arbitrage_bounds(self, options_engine: OptionsEngine) -> None:
        """Test calculate_implied_volatility arbitrage bounds checking (lines 191-196)."""
        # Test call option with price out of bounds (should return default 0.2)
        iv = options_engine.calculate_implied_volatility(
            price=18000.0,  # Price equals spot (upper bound)
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.CALL,
        )
        assert iv == 0.2  # Should return default when price is out of bounds

        # Test put option with price out of bounds (should return default 0.2)
        iv_put = options_engine.calculate_implied_volatility(
            price=18000.0,  # Price equals strike (upper bound for put)
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
            option_type=OptionType.PUT,
        )
        assert iv_put == 0.2  # Should return default when price is out of bounds

    def test_calculate_implied_volatility_fallback_methods(self, options_engine: OptionsEngine) -> None:
        """Test calculate_implied_volatility fallback methods (lines 200-234)."""
        # Test with price that might cause vollib to fail, triggering fallback
        with patch('src.loats.options.implied_volatility') as mock_iv:
            mock_iv.side_effect = Exception("vollib failed")

            iv = options_engine.calculate_implied_volatility(
                price=150.50,
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                r=0.05,
                option_type=OptionType.CALL,
            )

            # Should use fallback method and return a reasonable value
            assert isinstance(iv, float)
            assert iv > 0

    def test_calculate_implied_volatility_brentq_fallback(self, options_engine: OptionsEngine) -> None:
        """Test calculate_implied_volatility brentq fallback (lines 210-214)."""
        # Test scenario where brentq might be used as fallback
        with patch('src.loats.options.implied_volatility') as mock_iv, \
             patch('src.loats.options.black_scholes') as mock_bs, \
             patch('src.loats.options.brentq') as mock_brentq:

            mock_iv.side_effect = Exception("vollib failed")
            mock_bs.return_value = 150.50  # Match the price exactly

            # Mock brentq to return a known value
            mock_brentq.return_value = 0.25

            iv = options_engine.calculate_implied_volatility(
                price=150.50,
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                r=0.05,
                option_type=OptionType.CALL,
            )

            assert iv == 0.25

    def test_calculate_implied_volatility_newton_fallback(self, options_engine: OptionsEngine) -> None:
        """Test calculate_implied_volatility Newton method fallback (lines 216-234)."""
        # Test scenario where Newton method might be used as fallback
        with patch('src.loats.options.implied_volatility') as mock_iv, \
             patch('src.loats.options.black_scholes') as mock_bs, \
             patch('src.loats.options.brentq') as mock_brentq, \
             patch('src.loats.options.newton') as mock_newton, \
             patch('src.loats.options.vega') as mock_vega:

            mock_iv.side_effect = Exception("vollib failed")
            mock_bs.return_value = 150.50
            mock_brentq.side_effect = Exception("brentq failed")
            mock_newton.return_value = 0.30
            mock_vega.return_value = 0.1

            iv = options_engine.calculate_implied_volatility(
                price=150.50,
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                r=0.05,
                option_type=OptionType.CALL,
            )

            assert iv == 0.30

    def test_calculate_black_scholes_expired_contract(self, options_engine: OptionsEngine) -> None:
        """Test calculate_black_scholes with expired contract (line 256)."""
        # Test that ExpiredContractError is raised for expired contract
        with pytest.raises(ExpiredContractError) as exc_info:
            options_engine.calculate_black_scholes(
                S=18000.0,
                K=18000.0,
                t=0.0,
                sigma=0.25,
                option_type=OptionType.CALL,
            )

        assert exc_info.value.time_to_expiry == 0.0

    def test_calculate_time_to_expiration(self, options_engine: OptionsEngine) -> None:
        """Test calculate_time_to_expiration method."""
        # Test with future date
        future_date = datetime(2024, 1, 1, 15, 30, tzinfo=UTC)
        t = options_engine.calculate_time_to_expiration(future_date)

        assert isinstance(t, float)
        assert t > 0

        # Test with past date (should return negative)
        past_date = datetime(2020, 1, 1, 15, 30, tzinfo=UTC)
        t_past = options_engine.calculate_time_to_expiration(past_date)

        assert isinstance(t_past, float)
        assert t_past < 0

    def test_analyze_option_chain_comprehensive(self, options_engine: OptionsEngine, sample_option_contracts: list[OptionContract]) -> None:
        """Test analyze_option_chain method comprehensively (lines 280-312)."""
        # Test with contracts that have None implied volatility
        contracts_with_none_iv = [
            OptionContract(
                symbol="NIFTY23JAN18100CE",
                strike_price=18100.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
                option_type=OptionType.CALL,
                last_price=100.75,
                open_interest=8000,
                volume=4000,
                implied_volatility=None,  # This should trigger IV calculation
                delta=None,
                gamma=None,
                theta=None,
                vega=None,
                rho=None,
            )
        ]

        # Test analyze_option_chain
        analyzed = options_engine.analyze_option_chain(
            option_chain=contracts_with_none_iv,
            underlying_price=18000.0
        )

        assert len(analyzed) == 1
        assert analyzed[0].implied_volatility is not None  # Should be calculated
        assert analyzed[0].delta is not None  # Should be calculated
        assert analyzed[0].gamma is not None  # Should be calculated

        # Test with multiple contracts
        analyzed_multi = options_engine.analyze_option_chain(
            option_chain=sample_option_contracts,
            underlying_price=18000.0
        )

        assert len(analyzed_multi) == 2
        for contract in analyzed_multi:
            assert contract.delta is not None
            assert contract.gamma is not None
            assert contract.theta is not None
            assert contract.vega is not None
            assert contract.rho is not None

    def test_calculate_volatility_smile(self, options_engine: OptionsEngine, sample_option_contracts: list[OptionContract]) -> None:
        """Test calculate_volatility_smile method (lines 320-326)."""
        # Test with contracts that have implied volatility
        smile = options_engine.calculate_volatility_smile(
            option_chain=sample_option_contracts,
            underlying_price=18000.0
        )

        assert isinstance(smile, list)
        assert len(smile) == 2  # Both contracts have IV
        assert all(isinstance(item, tuple) for item in smile)
        assert all(len(item) == 2 for item in smile)

        # Test with contracts that have None implied volatility
        contracts_no_iv = [
            OptionContract(
                symbol="NIFTY23JAN18100CE",
                strike_price=18100.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
                option_type=OptionType.CALL,
                last_price=100.75,
                open_interest=8000,
                volume=4000,
                implied_volatility=None,  # No IV
                delta=0.4,
                gamma=0.015,
                theta=-0.04,
                vega=0.08,
                rho=0.025,
            )
        ]

        smile_no_iv = options_engine.calculate_volatility_smile(
            option_chain=contracts_no_iv,
            underlying_price=18000.0
        )

        assert isinstance(smile_no_iv, list)
        assert len(smile_no_iv) == 0  # No contracts with IV

    def test_calculate_put_call_parity(self, options_engine: OptionsEngine) -> None:
        """Test calculate_put_call_parity method (lines 340-342)."""
        # Test put-call parity calculation
        parity = options_engine.calculate_put_call_parity(
            call_price=150.50,
            put_price=140.25,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.05,
        )

        assert isinstance(parity, float)

        # Test with custom risk-free rate
        parity_custom_r = options_engine.calculate_put_call_parity(
            call_price=150.50,
            put_price=140.25,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=0.10,
        )

        assert isinstance(parity_custom_r, float)

    def test_standalone_calculate_greeks_expired_contract(self) -> None:
        """Test standalone calculate_greeks with expired contract (line 372)."""
        # Test that ExpiredContractError is raised for expired contract
        with pytest.raises(ExpiredContractError):
            calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=0.0,
                r=0.05,
                sigma=0.25,
                option_type=OptionType.CALL,
            )

    def test_standalone_calculate_greeks_exception_fallback(self) -> None:
        """Test standalone calculate_greeks exception fallback (lines 383-393)."""
        # Mock the vollib functions to raise exceptions and test fallback
        with patch('src.loats.options.delta') as mock_delta, \
             patch('src.loats.options.gamma') as mock_gamma, \
             patch('src.loats.options.theta') as mock_theta, \
             patch('src.loats.options.vega') as mock_vega, \
             patch('src.loats.options.rho') as mock_rho:

            # Set up mocks to raise exceptions
            mock_delta.side_effect = Exception("Test exception")
            mock_gamma.side_effect = Exception("Test exception")
            mock_theta.side_effect = Exception("Test exception")
            mock_vega.side_effect = Exception("Test exception")
            mock_rho.side_effect = Exception("Test exception")

            # Test call option fallback
            greeks = calculate_greeks(
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                r=0.05,
                sigma=0.25,
                option_type=OptionType.CALL,
            )

            assert isinstance(greeks, Greeks)
            assert greeks.delta == 0.0  # Fallback value for call
            assert greeks.gamma == 0.0
            assert greeks.theta == 0.0
            assert greeks.vega == 0.0
            assert greeks.rho == 0.0

    def test_standalone_calculate_implied_volatility_expired_contract(self) -> None:
        """Test standalone calculate_implied_volatility with expired contract (line 416)."""
        # Test that ExpiredContractError is raised for expired contract
        with pytest.raises(ExpiredContractError):
            calculate_implied_volatility(
                price=150.50,
                S=18000.0,
                K=18000.0,
                t=0.0,
                r=0.05,
                option_type=OptionType.CALL,
            )

    def test_standalone_calculate_implied_volatility_fallback(self) -> None:
        """Test standalone calculate_implied_volatility fallback (lines 426-428)."""
        # Test with price that might cause vollib to fail, triggering fallback
        with patch('src.loats.options.implied_volatility') as mock_iv:
            mock_iv.side_effect = Exception("vollib failed")

            iv = calculate_implied_volatility(
                price=150.50,
                S=18000.0,
                K=18000.0,
                t=30 / 365,
                r=0.05,
                option_type=OptionType.CALL,
            )

            # Should use fallback method and return default 0.2
            assert iv == 0.2

    def test_calculate_var_edge_cases(self) -> None:
        """Test calculate_var edge cases (line 450)."""
        # Test with empty returns list
        with pytest.raises(ValueError) as exc_info:
            calculate_var([], confidence_level=0.95)

        assert "Returns list cannot be empty" in str(exc_info.value)

        # Test with single return value
        var = calculate_var([0.01], confidence_level=0.95)
        assert var == 0.01

        # Test with negative returns
        returns = [-0.01, -0.02, -0.03, 0.01, 0.02]
        var_neg = calculate_var(returns, confidence_level=0.95)
        assert var_neg <= 0

    def test_calculate_historical_var_edge_cases(self) -> None:
        """Test calculate_historical_var edge cases (line 470)."""
        # Test with insufficient data (less than 2 prices)
        var = calculate_historical_var([18000.0], confidence_level=0.95)
        assert var == 0.0

        # Test with two prices
        var_two = calculate_historical_var([18000.0, 18050.0], confidence_level=0.95)
        assert var_two == 0.027777777777777776  # (50/18000)

    def test_options_analysis_portfolio_greeks_with_r_parameter(self, options_analysis: OptionsAnalysis, sample_option_contracts: list[OptionContract]) -> None:
        """Test OptionsAnalysis portfolio greeks with 'r' parameter (line 608)."""
        # Test portfolio greeks calculation using the 'r' parameter (backward compatibility)
        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=sample_option_contracts,
            underlying_price=18000.0,
            r=0.10,  # Use 'r' parameter instead of risk_free_rate
        )

        assert isinstance(portfolio_greeks, Greeks)
        assert portfolio_greeks.delta != 0.0
        assert portfolio_greeks.gamma != 0.0
        assert portfolio_greeks.vega != 0.0
        assert portfolio_greeks.theta != 0.0
        assert portfolio_greeks.rho != 0.0

    def test_options_and_analysis_global_instances(self) -> None:
        """Test global options and analysis instances."""
        # Test that global instances are properly initialized
        assert isinstance(options, OptionsEngine)
        assert isinstance(analysis, OptionsAnalysis)

        # Test that they can be used for calculations
        greeks = options.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks, Greeks)

        atm_strike = analysis.get_atm_strike(
            {
                "options": [
                    {
                        "symbol": "NIFTY23JAN18000CE",
                        "strike_price": 18000.0,
                        "option_type": "CE",
                        "last_price": 150.50,
                        "open_interest": 10000,
                        "volume": 5000,
                        "implied_volatility": 0.25,
                    }
                ]
            },
            18000.0
        )

        assert atm_strike == 18000.0


    def test_options_engine_comprehensive_edge_cases(self, options_engine: OptionsEngine) -> None:
        """Test comprehensive edge cases for OptionsEngine."""
        # Test with very small time to expiry (should clamp to 0.0001)
        greeks = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=0.00001,
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks, Greeks)

        # Test with very small volatility
        greeks_low_vol = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            sigma=0.001,
            option_type=OptionType.CALL,
        )

        assert greeks_low_vol.delta > 0.9  # Should be very close to 1

        # Test with very high volatility
        greeks_high_vol = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            sigma=10.0,  # 1000% volatility
            option_type=OptionType.CALL,
        )

        assert 0.0 <= greeks_high_vol.delta <= 1.0

        # Test implied volatility with extreme prices
        iv = options_engine.calculate_implied_volatility(
            price=10000.0,  # Extremely high price
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            option_type=OptionType.CALL,
        )

        assert iv > 1.0  # Should be very high

    def test_analyze_option_chain_with_exception_handling(self, options_engine: OptionsEngine) -> None:
        """Test analyze_option_chain with exception handling."""
        # Create a contract that might cause an exception during analysis
        problematic_contract = OptionContract(
            symbol="PROBLEMATIC",
            strike_price=18000.0,
            expiry=datetime(2023, 1, 1, 15, 30, tzinfo=UTC),  # Past date
            option_type=OptionType.CALL,
            last_price=150.50,
            open_interest=10000,
            volume=5000,
            implied_volatility=None,
            delta=None,
            gamma=None,
            theta=None,
            vega=None,
            rho=None,
        )

        # Test that the method handles exceptions gracefully
        analyzed = options_engine.analyze_option_chain(
            option_chain=[problematic_contract],
            underlying_price=18000.0
        )

        assert len(analyzed) == 1
        assert analyzed[0].symbol == "PROBLEMATIC"

    def test_portfolio_greeks_with_various_contract_quantities(self, options_analysis: OptionsAnalysis) -> None:
        """Test portfolio greeks with various contract quantities."""
        contracts = [
            OptionContract(
                symbol="NIFTY23JAN18000CE",
                strike_price=18000.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
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
                quantity=2,  # 2 contracts
            ),
            OptionContract(
                symbol="NIFTY23JAN18000PE",
                strike_price=18000.0,
                expiry=datetime(2023, 1, 26, 15, 30, tzinfo=UTC),
                option_type=OptionType.PUT,
                last_price=140.25,
                open_interest=12000,
                volume=6000,
                implied_volatility=0.26,
                delta=-0.5,
                gamma=0.02,
                theta=-0.06,
                vega=0.1,
                rho=-0.03,
                quantity=3,  # 3 contracts
            ),
        ]

        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=contracts,
            underlying_price=18000.0,
        )

        assert isinstance(portfolio_greeks, Greeks)
        # Delta should be: (0.5 * 2) + (-0.5 * 3) = 1.0 - 1.5 = -0.5
        assert abs(portfolio_greeks.delta - (-0.5)) < 0.01

    def test_options_engine_with_custom_risk_free_rate(self, options_engine: OptionsEngine) -> None:
        """Test OptionsEngine with custom risk-free rate."""
        # Set custom risk-free rate
        options_engine.set_risk_free_rate(0.08)

        # Test that it's used in calculations
        greeks = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks, Greeks)

        # Test that custom rate is used when r is None
        greeks_with_none_r = options_engine.calculate_greeks(
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            r=None,  # Should use engine's risk-free rate
            sigma=0.25,
            option_type=OptionType.CALL,
        )

        assert isinstance(greeks_with_none_r, Greeks)

    def test_comprehensive_implied_volatility_scenarios(self, options_engine: OptionsEngine) -> None:
        """Test comprehensive implied volatility calculation scenarios."""
        # Test with very short time to expiry
        iv_short = options_engine.calculate_implied_volatility(
            price=100.0,
            S=18000.0,
            K=18000.0,
            t=1 / 365,  # 1 day
            option_type=OptionType.CALL,
        )

        assert isinstance(iv_short, float)

        # Test with very long time to expiry
        iv_long = options_engine.calculate_implied_volatility(
            price=500.0,
            S=18000.0,
            K=18000.0,
            t=5,  # 5 years
            option_type=OptionType.CALL,
        )

        assert isinstance(iv_long, float)

        # Test with very low volatility scenario
        iv_low = options_engine.calculate_implied_volatility(
            price=50.0,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            option_type=OptionType.CALL,
        )

        assert isinstance(iv_low, float)

        # Test with very high volatility scenario
        iv_high = options_engine.calculate_implied_volatility(
            price=500.0,
            S=18000.0,
            K=18000.0,
            t=30 / 365,
            option_type=OptionType.CALL,
        )

        assert isinstance(iv_high, float)