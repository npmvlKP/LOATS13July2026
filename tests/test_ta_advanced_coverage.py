"""
Additional tests for ta.py to improve coverage of advanced technical analysis functions.
Focuses on complex calculations and edge cases.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from loats.models import HistoricalData, TAIndicator
from loats.ta import (
    TechnicalAnalysis,
    calculate_atr,
    calculate_cmf,
    calculate_macd,
    calculate_rsi,
    calculate_supertrend,
    calculate_vwap,
)


class TestAdvancedTACoverage:
    """Additional tests for advanced technical analysis functionality."""

    @pytest.fixture
    def ta(self) -> TechnicalAnalysis:
        """Fixture for TechnicalAnalysis instance."""
        return TechnicalAnalysis()

    @pytest.fixture
    def sample_data(self) -> list[HistoricalData]:
        """Fixture for sample historical data."""
        return [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1500,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                open=101.5,
                high=102.5,
                low=101.0,
                close=102.0,
                volume=1800,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
                open=102.0,
                high=103.0,
                low=101.5,
                close=102.5,
                volume=2000,
                interval="1min",
            ),
        ]

    def test_calculate_rsi_with_extreme_values(self) -> None:
        """Test RSI calculation with extreme price movements."""
        # Test with very large gains
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 150.0, 200.0, 250.0, 300.0],  # Extreme gains
            "low": [100.0, 100.0, 100.0, 100.0, 100.0],
            "close": [100.0, 150.0, 200.0, 250.0, 300.0],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=3)

        # Should handle extreme values without errors
        assert len(rsi) == 5
        assert not all(pd.isna(rsi))  # Should have some valid values

    def test_calculate_macd_with_volatile_data(self) -> None:
        """Test MACD calculation with highly volatile data."""
        # Test with volatile price swings
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 150.0, 80.0, 120.0, 90.0],  # Volatile swings
            "high": [105.0, 160.0, 85.0, 130.0, 95.0],
            "low": [95.0, 140.0, 75.0, 110.0, 85.0],
            "close": [102.0, 155.0, 82.0, 125.0, 92.0],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        macd_line, signal_line, histogram = calculate_macd(
            df, fast_period=3, slow_period=5, signal_period=2
        )

        # Should handle volatile data without errors
        assert len(macd_line) == 5
        assert len(signal_line) == 5
        assert len(histogram) == 5

    def test_calculate_atr_with_gaps(self) -> None:
        """Test ATR calculation with price gaps."""
        # Test with large price gaps
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0, 99.0, 99.0],
            "close": [100.5, 100.5, 100.5, 100.5, 100.5],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        atr = calculate_atr(df, period=3)

        # Should handle small price movements without errors
        assert len(atr) == 5
        assert not all(pd.isna(atr))  # Should have some valid values

    def test_calculate_supertrend_with_stable_prices(self) -> None:
        """Test Supertrend calculation with stable price range."""
        # Test with very stable prices
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.1, 100.0, 100.1, 100.0],  # Very stable
            "high": [100.5, 100.6, 100.5, 100.6, 100.5],
            "low": [99.5, 99.4, 99.5, 99.4, 99.5],
            "close": [100.0, 100.1, 100.0, 100.1, 100.0],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        supertrend, direction = calculate_supertrend(df, period=3, multiplier=2)

        # Should handle stable prices without errors
        assert len(supertrend) == 5
        assert len(direction) == 5

    def test_calculate_vwap_with_varying_volumes(self) -> None:
        """Test VWAP calculation with varying volume patterns."""
        # Test with extreme volume variations
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0, 99.0, 99.0],
            "close": [100.5, 100.5, 100.5, 100.5, 100.5],
            "volume": [100, 10000, 50, 8000, 200],  # Extreme volume variations
        }

        df = pd.DataFrame(data)
        vwap = calculate_vwap(df)

        # Should handle volume variations without errors
        assert len(vwap) == 5
        assert not all(pd.isna(vwap))  # Should have some valid values

    def test_calculate_cmf_with_mixed_flow(self) -> None:
        """Test CMF calculation with mixed money flow patterns."""
        # Test with alternating positive/negative money flow
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [102.0, 101.0, 102.0, 101.0, 102.0],  # Alternating high/low closes
            "low": [98.0, 99.0, 98.0, 99.0, 98.0],
            "close": [101.5, 99.5, 101.5, 99.5, 101.5],  # Alternating up/down
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        cmf = calculate_cmf(df, period=3)

        # Should handle mixed flow patterns without errors
        assert len(cmf) == 5
        assert not all(pd.isna(cmf))  # Should have some valid values

    def test_technical_analysis_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test TechnicalAnalysis class edge cases."""
        # Test with minimal historical data
        minimal_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
        ]

        # Should handle minimal data gracefully
        strength = ta.calculate_price_action_strength(minimal_data, current_price=101.0)
        assert 0 <= strength <= 1

        # Test with empty data
        empty_data = []
        strength = ta.calculate_volatility_strength(empty_data)
        assert 0 <= strength <= 1

        # Test with single data point
        single_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volume_strength(single_data)
        assert -1 <= strength <= 1

    def test_indicator_strength_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test indicator strength calculations with edge cases."""
        # Test RSI strength with boundary values
        assert 0 <= ta.calculate_rsi_strength(0.0) <= 1
        assert 0 <= ta.calculate_rsi_strength(100.0) <= 1
        assert 0 <= ta.calculate_rsi_strength(50.0) <= 1

        # Test MACD strength with equal values
        assert 0 <= ta.calculate_macd_strength(1.0, 1.0) <= 1
        assert 0 <= ta.calculate_macd_strength(0.0, 0.0) <= 1

        # Test supertrend strength with boundary conditions
        assert 0 <= ta.calculate_supertrend_strength(100.0, 100.0, 1) <= 1
        assert 0 <= ta.calculate_supertrend_strength(100.0, 100.0, -1) <= 1

        # Test combined strength with empty dict
        assert 0 <= ta.calculate_combined_strength({}) <= 1

        # Test combined strength with single indicator
        assert 0 <= ta.calculate_combined_strength({"rsi": 0.5}) <= 1

    def test_signal_generation_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test signal generation with edge cases."""
        # Test with minimal indicators
        minimal_indicators = [
            TAIndicator(
                name="rsi",
                value=50.0,  # Neutral RSI
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(minimal_indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"

        # Test with conflicting indicators
        conflicting_indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,  # Oversold
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=0.5,  # Bearish
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=1.5,  # Bullish signal
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(conflicting_indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # Should be neutral due to conflicting signals

    def test_calculate_indicators_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test calculate_indicators with edge cases."""
        # Test with exactly 15 data points (minimum for TA)
        boundary_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=UTC)
                + timedelta(minutes=i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.5 + i,
                close=100.5 + i,
                volume=1000 + i * 100,
                interval="1min",
            )
            for i in range(15)
        ]

        indicators = ta.calculate_indicators(boundary_data)
        # Should work with exactly 15 data points
        assert isinstance(indicators, list)

        # Test with 16 data points (just above minimum)
        above_boundary_data = boundary_data + [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=UTC)
                + timedelta(minutes=15),
                open=115.5,
                high=116.5,
                low=114.5,
                close=115.5,
                volume=2500,
                interval="1min",
            )
        ]

        indicators = ta.calculate_indicators(above_boundary_data)
        # Should work with 16 data points
        assert isinstance(indicators, list)
        assert len(indicators) > 0  # Should have some indicators
