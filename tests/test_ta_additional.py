"""
Additional unit tests for technical analysis module to increase coverage.
Tests more technical analysis functions, edge cases, and signal generation logic.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from src.loats.models import HistoricalData, TAIndicator
from src.loats.ta import (
    TechnicalAnalysis,
    calculate_atr,
    calculate_cmf,
    calculate_macd,
    calculate_rsi,
    calculate_supertrend,
    calculate_vwap,
)


class TestTechnicalAnalysisAdditional:
    """Additional tests for TechnicalAnalysis class."""

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

    @pytest.fixture
    def sufficient_data(self) -> list[HistoricalData]:
        """Fixture for sufficient historical data (15+ points)."""
        base_time = datetime(2023, 1, 1, 9, 30, tzinfo=UTC)
        return [
            HistoricalData(
                symbol="TEST",
                timestamp=base_time + timedelta(minutes=i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.5 + i,
                close=100.5 + i,
                volume=1000 + i * 100,
                interval="1min",
            )
            for i in range(20)
        ]

    def test_calculate_rsi_edge_cases(self) -> None:
        """Test RSI calculation with edge cases."""
        # Test with all gains (should result in RSI = 100)
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=3)

        # Check that we get some valid RSI values
        assert len(rsi) == 5
        assert pd.isna(rsi.iloc[0])  # First value should be NaN
        assert pd.isna(rsi.iloc[1])  # Second value should be NaN

        # Test with all losses (should result in RSI = 0)
        data["close"] = [100.5, 99.5, 98.5, 97.5, 96.5]
        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=3)

        # Check that we get some valid RSI values
        assert len(rsi) == 5
        assert pd.isna(rsi.iloc[0])  # First value should be NaN
        assert pd.isna(rsi.iloc[1])  # Second value should be NaN

    def test_calculate_macd_edge_cases(self) -> None:
        """Test MACD calculation with edge cases."""
        # Test with constant prices
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0, 100.0, 100.0],
            "low": [100.0, 100.0, 100.0, 100.0, 100.0],
            "close": [100.0, 100.0, 100.0, 100.0, 100.0],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        macd_line, signal_line, histogram = calculate_macd(
            df, fast_period=3, slow_period=5, signal_period=2
        )

        # All values should be NaN due to constant prices
        assert len(macd_line) == 5
        assert len(signal_line) == 5
        assert len(histogram) == 5

    def test_calculate_atr_edge_cases(self) -> None:
        """Test ATR calculation with edge cases."""
        # Test with very small price movements
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 100.01, 100.02, 100.03, 100.04],
            "high": [100.01, 100.02, 100.03, 100.04, 100.05],
            "low": [99.99, 100.0, 100.01, 100.02, 100.03],
            "close": [100.0, 100.01, 100.02, 100.03, 100.04],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        atr = calculate_atr(df, period=3)

        # Should return valid ATR values
        assert len(atr) == 5
        assert pd.isna(atr.iloc[0])  # First value should be NaN

    def test_calculate_supertrend_edge_cases(self) -> None:
        """Test Supertrend calculation with edge cases."""
        # Test with very volatile data
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 110.0, 90.0, 120.0, 80.0],
            "high": [105.0, 115.0, 95.0, 125.0, 85.0],
            "low": [95.0, 105.0, 85.0, 115.0, 75.0],
            "close": [102.0, 112.0, 88.0, 122.0, 78.0],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)
        supertrend, direction = calculate_supertrend(df, period=3, multiplier=2)

        # Should return valid supertrend values
        assert len(supertrend) == 5
        assert len(direction) == 5
        assert pd.isna(supertrend.iloc[0])  # First value should be NaN
        assert pd.isna(direction.iloc[0])  # First value should be NaN

    def test_calculate_vwap_edge_cases(self) -> None:
        """Test VWAP calculation with edge cases."""
        # Test with zero volume
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [0, 0, 0, 0, 0],  # Zero volume
        }

        df = pd.DataFrame(data)
        vwap = calculate_vwap(df)

        # Should handle zero volume gracefully
        assert len(vwap) == 5
        assert not pd.isna(vwap.iloc[0])  # Should still return a value

    def test_calculate_cmf_edge_cases(self) -> None:
        """Test CMF calculation with edge cases."""
        # Test with zero volume
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 31, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 32, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 33, tzinfo=UTC),
                datetime(2023, 1, 1, 9, 34, tzinfo=UTC),
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [0, 0, 0, 0, 0],  # Zero volume
        }

        df = pd.DataFrame(data)
        cmf = calculate_cmf(df, period=3)

        # Should handle zero volume gracefully
        assert len(cmf) == 5
        assert pd.isna(cmf.iloc[0])  # First value should be NaN

    def test_calculate_rsi_strength_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test RSI strength calculation with edge cases."""
        # Test with RSI exactly at boundaries
        assert ta.calculate_rsi_strength(30.0) == 0.3  # Exactly at 30
        assert ta.calculate_rsi_strength(70.0) == 0.3  # Exactly at 70

        # Test with RSI just below/above boundaries
        assert ta.calculate_rsi_strength(29.9) == 1.0  # Just below 30
        assert ta.calculate_rsi_strength(70.1) == 0.0  # Just above 70

        # Test with extreme RSI values
        assert ta.calculate_rsi_strength(0.0) == 1.0  # Extremely oversold
        assert ta.calculate_rsi_strength(100.0) == 0.0  # Extremely overbought

    def test_calculate_macd_strength_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test MACD strength calculation with edge cases."""
        # Test with MACD exactly equal to signal
        assert ta.calculate_macd_strength(1.0, 1.0) == 0.3  # Equal values

        # Test with very small differences
        assert (
            ta.calculate_macd_strength(1.001, 1.0) == 0.7
        )  # MACD slightly above signal
        assert (
            ta.calculate_macd_strength(0.999, 1.0) == 0.3
        )  # MACD slightly below signal

        # Test with extreme values
        assert (
            ta.calculate_macd_strength(100.0, 0.0) == 0.7
        )  # MACD much higher than signal
        assert (
            ta.calculate_macd_strength(0.0, 100.0) == 0.3
        )  # MACD much lower than signal

    def test_calculate_supertrend_strength_edge_cases(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test supertrend strength calculation with edge cases."""
        # Test with price exactly at supertrend value
        assert (
            ta.calculate_supertrend_strength(100.0, 100.0, 1) == 0.7
        )  # Price equals supertrend in uptrend
        assert (
            ta.calculate_supertrend_strength(100.0, 100.0, -1) == 0.3
        )  # Price equals supertrend in downtrend

        # Test with very small differences
        assert (
            ta.calculate_supertrend_strength(100.1, 100.0, 1) == 0.9
        )  # Price just above supertrend in uptrend
        assert (
            ta.calculate_supertrend_strength(99.9, 100.0, -1) == 0.1
        )  # Price just below supertrend in downtrend

        # Test with direction changes
        assert (
            ta.calculate_supertrend_strength(101.0, 100.0, -1) == 0.3
        )  # Price above supertrend but direction is down
        assert (
            ta.calculate_supertrend_strength(99.0, 100.0, 1) == 0.7
        )  # Price below supertrend but direction is up

    def test_calculate_combined_strength_edge_cases(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test combined strength calculation with edge cases."""
        # Test with empty strengths dict
        assert ta.calculate_combined_strength({}) == 0.5  # Default value for empty dict

        # Test with single indicator
        assert (
            ta.calculate_combined_strength({"rsi": 0.8}) == 0.8
        )  # Should return the single value

        # Test with extreme values
        strengths = {
            "rsi": 1.0,
            "macd": 1.0,
            "supertrend": 1.0,
        }
        assert ta.calculate_combined_strength(strengths) == 1.0  # All max values

        strengths = {
            "rsi": 0.0,
            "macd": 0.0,
            "supertrend": 0.0,
        }
        assert ta.calculate_combined_strength(strengths) == 0.0  # All min values

    def test_calculate_price_action_strength_edge_cases(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test price action strength calculation with edge cases."""
        # Test with minimal data (only 1 data point)
        historical_data = [
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

        strength = ta.calculate_price_action_strength(
            historical_data, current_price=101.0
        )
        assert strength == 0.5  # Default value for minimal data

        # Test with price exactly at last close
        historical_data = [
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
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
        ]

        strength = ta.calculate_price_action_strength(
            historical_data, current_price=101.0
        )
        assert strength == 0.5  # Price equals last close

    def test_calculate_volatility_strength_edge_cases(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test volatility strength calculation with edge cases."""
        # Test with minimal data (only 1 data point)
        historical_data = [
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

        strength = ta.calculate_volatility_strength(historical_data)
        assert strength == 0.5  # Default value for minimal data

        # Test with zero range
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volatility_strength(historical_data)
        assert strength == 0.5  # Default value for zero range

    def test_calculate_volume_strength_edge_cases(self, ta: TechnicalAnalysis) -> None:
        """Test volume strength calculation with edge cases."""
        # Test with minimal data (only 1 data point)
        historical_data = [
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

        strength = ta.calculate_volume_strength(historical_data)
        assert strength == 0.0  # Default value for minimal data

        # Test with constant volume
        historical_data = [
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
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(UTC),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1000,  # Same volume
                interval="1min",
            ),
        ]

        strength = ta.calculate_volume_strength(historical_data)
        assert strength == 0.0  # Constant volume should be neutral

    def test_calculate_indicators_with_empty_data(self, ta: TechnicalAnalysis) -> None:
        """Test calculate_indicators with empty data."""
        indicators = ta.calculate_indicators([])
        assert indicators == []

    def test_calculate_indicators_with_insufficient_data(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test calculate_indicators with insufficient data."""
        # Only 2 data points (need at least 15 for TA)
        insufficient_data = [
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
        ]

        indicators = ta.calculate_indicators(insufficient_data)
        # Should return empty list for insufficient data
        assert indicators == []

    def test_generate_signal_with_missing_indicators(
        self, ta: TechnicalAnalysis
    ) -> None:
        """Test generate_signal with missing indicators."""
        # Test with empty indicators list
        signal = ta.generate_signal([], current_price=100.0)
        assert signal is None

        # Test with only RSI indicator
        indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] in ["BUY", "SELL", "NEUTRAL"]

        # Test with only MACD indicators
        indicators = [
            TAIndicator(
                name="macd",
                value=1.5,
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=0.5,
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # Should be neutral without RSI

    def test_generate_signal_boundary_conditions(self, ta: TechnicalAnalysis) -> None:
        """Test generate_signal with boundary conditions."""
        # Test with RSI exactly at 30 (not oversold)
        indicators = [
            TAIndicator(
                name="rsi",
                value=30.0,  # Exactly at boundary
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=1.5,
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=0.5,
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # RSI=30 is not < 30, so no BUY signal

        # Test with RSI exactly at 70 (not overbought)
        indicators[0].value = 70.0
        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # RSI=70 is not > 70, so no SELL signal

        # Test with MACD exactly equal to signal
        indicators[1].value = 0.5  # MACD = signal
        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # MACD not > signal, so no BUY signal
