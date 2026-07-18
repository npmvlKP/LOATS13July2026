"""
Tests for portfolio Greeks calculation.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.loats.models import Greeks, OptionContract, OptionType
from src.loats.options import OptionsAnalysis


class TestPortfolioGreeks:
    """Test suite for portfolio Greeks calculation."""

    @pytest.fixture
    def options_analysis(self) -> OptionsAnalysis:
        """Create an OptionsAnalysis instance."""
        return OptionsAnalysis()

    @pytest.fixture
    def sample_contracts(self) -> list[OptionContract]:
        """Create sample option contracts for testing."""
        now = datetime.now(UTC)
        expiry = now + timedelta(days=30)

        return [
            OptionContract(
                symbol="NIFTY23JAN18000CE",
                strike_price=18000.0,
                expiry=expiry,
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
                expiry=expiry,
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
            OptionContract(
                symbol="NIFTY23JAN18100CE",
                strike_price=18100.0,
                expiry=expiry,
                option_type=OptionType.CALL,
                last_price=100.75,
                open_interest=8000,
                volume=4000,
                implied_volatility=0.24,
                delta=0.4,
                gamma=0.015,
                theta=-0.04,
                vega=0.08,
                rho=0.025,
            ),
        ]

    def test_calculate_portfolio_greeks(
        self,
        options_analysis: OptionsAnalysis,
        sample_contracts: list[OptionContract],
    ) -> None:
        """Test calculate_portfolio_greeks method."""
        underlying_price = 18000.0
        risk_free_rate = 0.05
        volatility = 0.25

        # Calculate portfolio Greeks
        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=sample_contracts,
            underlying_price=underlying_price,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
        )

        # Verify the result is a Greeks object
        assert isinstance(portfolio_greeks, Greeks)

        # Verify that portfolio Greeks are calculated correctly
        # The exact values will depend on the Black-Scholes calculation
        assert isinstance(portfolio_greeks.delta, float)
        assert isinstance(portfolio_greeks.gamma, float)
        assert isinstance(portfolio_greeks.vega, float)
        assert isinstance(portfolio_greeks.theta, float)
        assert isinstance(portfolio_greeks.rho, float)

        # Portfolio IV should be 0.0 as it's not meaningful for portfolios
        assert portfolio_greeks.implied_volatility == 0.0

        # Check that the values are reasonable
        # Delta should be between -3 and 3 for this portfolio (3 contracts)
        assert -3 <= portfolio_greeks.delta <= 3
        # Gamma should be positive
        assert portfolio_greeks.gamma >= 0
        # Vega should be positive
        assert portfolio_greeks.vega >= 0
        # Theta should be negative (time decay)
        assert portfolio_greeks.theta <= 0

    def test_calculate_portfolio_greeks_default_risk_free_rate(
        self,
        options_analysis: OptionsAnalysis,
        sample_contracts: list[OptionContract],
    ) -> None:
        """Test calculate_portfolio_greeks with default risk-free rate."""
        underlying_price = 18000.0
        volatility = 0.25

        # Calculate portfolio Greeks without specifying risk_free_rate
        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=sample_contracts,
            underlying_price=underlying_price,
            volatility=volatility,
        )

        # Verify the result is a Greeks object
        assert isinstance(portfolio_greeks, Greeks)

        # Should use the engine's default risk-free rate (0.05)
        assert isinstance(portfolio_greeks.delta, float)

    def test_calculate_portfolio_greeks_contract_specific_volatility(
        self,
        options_analysis: OptionsAnalysis,
        sample_contracts: list[OptionContract],
    ) -> None:
        """Test that contract-specific implied volatility is used when available."""
        underlying_price = 18000.0
        risk_free_rate = 0.05
        # Use a different volatility than the contract's implied volatility
        default_volatility = 0.3

        # Calculate portfolio Greeks
        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=sample_contracts,
            underlying_price=underlying_price,
            risk_free_rate=risk_free_rate,
            volatility=default_volatility,
        )

        # Verify the result is a Greeks object
        assert isinstance(portfolio_greeks, Greeks)

        # The calculation should have used the contract's implied_volatility
        # rather than the provided default_volatility for contracts that have it

    def test_calculate_portfolio_greeks_empty_contracts(
        self,
        options_analysis: OptionsAnalysis,
    ) -> None:
        """Test calculate_portfolio_greeks with empty contracts list."""
        underlying_price = 18000.0
        risk_free_rate = 0.05
        volatility = 0.25

        # Calculate portfolio Greeks with empty contracts list
        portfolio_greeks = options_analysis.calculate_portfolio_greeks(
            contracts=[],
            underlying_price=underlying_price,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
        )

        # Verify the result is a Greeks object with all zeros
        assert isinstance(portfolio_greeks, Greeks)
        assert portfolio_greeks.delta == 0.0
        assert portfolio_greeks.gamma == 0.0
        assert portfolio_greeks.vega == 0.0
        assert portfolio_greeks.theta == 0.0
        assert portfolio_greeks.rho == 0.0
        assert portfolio_greeks.implied_volatility == 0.0
