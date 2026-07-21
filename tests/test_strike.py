"""
Tests for Strike Selection Module.
Validates <5ms latency target and strike selection accuracy.
"""

from datetime import UTC, datetime

import pytest

from src.loats.models import OptionContract, OptionType
from src.strike import Strike, StrikeSelection, StrikeSelector, select_strike


@pytest.fixture
def option_chain() -> list[OptionContract]:
    """Create sample option chain for testing."""
    now = datetime.now(UTC)
    return [
        OptionContract(
            symbol="NIFTY",
            strike_price=25000.0,
            expiry=now,
            option_type=OptionType.CALL,
            last_price=150.0,
            open_interest=50000,
            volume=10000,
            delta=0.50,
            gamma=0.02,
            theta=-5.0,
            vega=0.15,
        ),
        OptionContract(
            symbol="NIFTY",
            strike_price=25100.0,
            expiry=now,
            option_type=OptionType.CALL,
            last_price=120.0,
            open_interest=75000,
            volume=15000,
            delta=0.45,
            gamma=0.022,
            theta=-5.5,
            vega=0.16,
        ),
        OptionContract(
            symbol="NIFTY",
            strike_price=25200.0,
            expiry=now,
            option_type=OptionType.CALL,
            last_price=95.0,
            open_interest=60000,
            volume=12000,
            delta=0.40,
            gamma=0.021,
            theta=-5.2,
            vega=0.15,
        ),
        OptionContract(
            symbol="NIFTY",
            strike_price=24900.0,
            expiry=now,
            option_type=OptionType.PUT,
            last_price=130.0,
            open_interest=55000,
            volume=11000,
            delta=-0.45,
            gamma=0.022,
            theta=-5.3,
            vega=0.16,
        ),
        OptionContract(
            symbol="NIFTY",
            strike_price=24800.0,
            expiry=now,
            option_type=OptionType.PUT,
            last_price=110.0,
            open_interest=45000,
            volume=9000,
            delta=-0.40,
            gamma=0.020,
            theta=-4.8,
            vega=0.14,
        ),
    ]


@pytest.fixture
def strike_selector() -> StrikeSelector:
    """Create StrikeSelector instance."""
    return StrikeSelector()


@pytest.fixture
def strike() -> Strike:
    """Create Strike instance for backward compatibility."""
    return Strike()


class TestStrikeSelector:
    """Tests for StrikeSelector class."""

    def test_select_strike_call_options(self, strike_selector, option_chain) -> None:
        """Test strike selection for call options."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
            sentiment_score=0.2,
        )

        assert isinstance(result, StrikeSelection)
        assert result.option_type == "CE"
        assert result.atm_strike == 25000.0  # Closest to underlying
        assert result.selected_strike > 0
        assert result.latency_ms < 5.0  # Within 5ms target
        assert -1.0 <= result.moneyness <= 1.0
        assert 0.0 <= result.final_score <= 1.0

    def test_select_strike_put_options(self, strike_selector, option_chain) -> None:
        """Test strike selection for put options."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="PE",
            sentiment_score=-0.2,
        )

        assert result.option_type == "PE"
        assert result.selected_strike > 0
        assert result.latency_ms < 5.0

    def test_select_strike_bullish_sentiment(
        self, strike_selector, option_chain
    ) -> None:
        """Test strike selection adjusts for bullish sentiment."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
            sentiment_score=0.5,  # Strong bullish
        )

        # Bullish sentiment should select slightly OTM strikes
        assert result.selected_strike >= result.atm_strike
        assert result.sentiment_adjustment > 0

    def test_select_strike_bearish_sentiment(
        self, strike_selector, option_chain
    ) -> None:
        """Test strike selection adjusts for bearish sentiment."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="PE",
            sentiment_score=-0.5,  # Strong bearish
        )

        # Bearish sentiment should select slightly OTM puts
        assert result.sentiment_adjustment > 0  # Abs of negative sentiment

    def test_select_strike_with_explicit_delta_target(
        self, strike_selector, option_chain
    ) -> None:
        """Test strike selection with explicit delta target."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
            delta_target=0.40,
        )

        assert result.delta_target == 0.40
        assert result.selected_strike == 25200.0  # Delta ~0.40

    def test_select_strike_prefers_high_oi(self, strike_selector, option_chain) -> None:
        """Test that OI weighting influences strike selection."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
            prefer_oi=True,
        )

        # When prefer_oi=True, OI weight should be calculated
        assert result.oi_weight > 0
        # Strike 25100 has highest OI, should be selected or ATM used as fallback
        assert result.selected_strike in [25000.0, 25100.0]

    def test_select_strike_empty_chain(self, strike_selector) -> None:
        """Test strike selection with empty chain."""
        result = strike_selector.select_strike(
            option_chain=[],
            underlying_price=25000.0,
            option_type="CE",
        )

        assert result.selection_reason == "No options available for selection"
        assert result.final_score == 0.0

    def test_select_strike_latency_target(self, strike_selector, option_chain) -> None:
        """Test that strike selection meets <5ms target."""
        latencies = []
        for _ in range(10):
            result = strike_selector.select_strike(
                option_chain=option_chain,
                underlying_price=25050.0,
                option_type="CE",
            )
            latencies.append(result.latency_ms)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 5.0, (
            f"Average latency {avg_latency:.2f}ms exceeds 5ms target"
        )


class TestStrikeClass:
    """Tests for backward-compatible Strike class."""

    def test_strike_calculate_call(self, strike, option_chain) -> None:
        """Test Strike.calculate() for calls."""
        data = {
            "option_chain": option_chain,
            "underlying_price": 25050.0,
            "option_type": "CE",
            "sentiment_score": 0.2,
        }

        result = strike.calculate(data)

        assert isinstance(result, dict)
        assert "selected_strike" in result
        assert "atm_strike" in result
        assert "latency_ms" in result
        assert result["option_type"] == "CE"
        assert result["latency_ms"] < 5.0

    def test_strike_calculate_put(self, strike, option_chain) -> None:
        """Test Strike.calculate() for puts."""
        data = {
            "option_chain": option_chain,
            "underlying_price": 25050.0,
            "option_type": "PE",
            "sentiment_score": -0.2,
        }

        result = strike.calculate(data)

        assert result["option_type"] == "PE"
        assert "selected_strike" in result

    def test_strike_calculate_empty_chain(self, strike) -> None:
        """Test Strike.calculate() with empty chain."""
        data = {
            "option_chain": [],
            "underlying_price": 25000.0,
            "option_type": "CE",
        }

        result = strike.calculate(data)

        assert "selection_reason" in result
        assert result["selection_reason"] == "No options available for selection"

    def test_strike_calculate_with_delta_target(self, strike, option_chain) -> None:
        """Test Strike.calculate() with explicit delta target."""
        data = {
            "option_chain": option_chain,
            "underlying_price": 25050.0,
            "option_type": "CE",
            "delta_target": 0.45,
        }

        result = strike.calculate(data)

        assert result["delta_target"] == 0.45


class TestSelectStrikeFunction:
    """Tests for module-level select_strike function."""

    def test_select_strike_function(self, option_chain) -> None:
        """Test convenience function."""
        result = select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
        )

        assert isinstance(result, StrikeSelection)
        assert result.selected_strike > 0
        assert result.latency_ms < 5.0


class TestMoneyness:
    """Tests for moneyness calculations."""

    def test_atm_moneyness(self, strike_selector, option_chain) -> None:
        """Test ATM strike has near-zero moneyness."""
        # Verify ATM strike exists in option chain
        _ = next(opt for opt in option_chain if opt.strike_price == 25000.0)

        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25000.0,  # Exact ATM
            option_type="CE",
        )

        # Moneyness should be near zero for ATM
        assert abs(result.moneyness) < 0.01

    def test_otm_call_moneyness(self, strike_selector, option_chain) -> None:
        """Test OTM call has negative moneyness."""
        # 25200 is OTM call for 25050 underlying
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
        )

        # OTM call (strike > underlying) should have negative moneyness
        if result.selected_strike > result.atm_strike:
            assert result.moneyness < 0

    def test_otm_put_moneyness(self, strike_selector, option_chain) -> None:
        """Test OTM put has positive moneyness."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="PE",
        )

        # Verify selection was made
        assert result.selected_strike > 0
        assert result.option_type == "PE"

        # OTM put (strike < underlying) moneyness formula: (K-S)/S
        # For K < S, this is positive
        assert result.moneyness > 0


class TestSelectionReason:
    """Tests for selection reason generation."""

    def test_selection_reason_contains_strike(
        self, strike_selector, option_chain
    ) -> None:
        """Test selection reason includes strike info."""
        result = strike_selector.select_strike(
            option_chain=option_chain,
            underlying_price=25050.0,
            option_type="CE",
        )

        assert str(result.selected_strike) in result.selection_reason
        assert "call" in result.selection_reason.lower()
        assert "delta" in result.selection_reason.lower()
