from datetime import datetime, timedelta, timezone

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


class TestTechnicalAnalysis:
    """Test suite for TechnicalAnalysis class."""

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
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 31, tzinfo=timezone.utc),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 32, tzinfo=timezone.utc),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1500,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 33, tzinfo=timezone.utc),
                open=101.5,
                high=102.5,
                low=101.0,
                close=102.0,
                volume=1800,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 34, tzinfo=timezone.utc),
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
        base_time = datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc)
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

    def test_calculate_rsi(self, sample_data: list[HistoricalData]) -> None:
        """Test RSI calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        rsi = calculate_rsi(df)

        # Should return a Series with same length as input
        assert len(rsi) == len(sample_data)
        assert isinstance(rsi, pd.Series)

        # First few values should be NaN (warmup period)
        assert pd.isna(rsi.iloc[0])
        assert pd.isna(rsi.iloc[1])

        # Test with constant prices
        constant_df = pd.DataFrame(
            {
                "timestamp": [
                    datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc),
                    datetime(2023, 1, 1, 9, 31, tzinfo=timezone.utc),
                ],
                "open": [100.0, 100.0],
                "high": [100.0, 100.0],
                "low": [100.0, 100.0],
                "close": [100.0, 100.0],
                "volume": [1000, 1000],
            },
        )

        rsi_constant = calculate_rsi(constant_df, period=2)
        assert all(pd.isna(rsi_constant))

    def test_calculate_macd(self, sample_data: list[HistoricalData]) -> None:
        """Test MACD calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        macd_line, signal_line, histogram = calculate_macd(df)

        # Should return three Series with same length as input
        assert len(macd_line) == len(sample_data)
        assert len(signal_line) == len(sample_data)
        assert len(histogram) == len(sample_data)

        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)

        # First few values should be NaN (warmup period)
        assert pd.isna(macd_line.iloc[0])
        assert pd.isna(macd_line.iloc[1])
        assert pd.isna(macd_line.iloc[2])

    def test_calculate_atr(self, sample_data: list[HistoricalData]) -> None:
        """Test ATR calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        atr = calculate_atr(df)

        # Should return a Series with same length as input
        assert len(atr) == len(sample_data)
        assert isinstance(atr, pd.Series)

        # First few values should be NaN (warmup period)
        assert pd.isna(atr.iloc[0])

    def test_calculate_supertrend(self, sample_data: list[HistoricalData]) -> None:
        """Test Supertrend calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        supertrend, direction = calculate_supertrend(df, period=3, multiplier=2)

        # Should return two Series with same length as input
        assert len(supertrend) == len(sample_data)
        assert len(direction) == len(sample_data)

        assert isinstance(supertrend, pd.Series)
        assert isinstance(direction, pd.Series)

        # First few values should be NaN (warmup period)
        assert pd.isna(supertrend.iloc[0])
        assert pd.isna(direction.iloc[0])

    def test_calculate_vwap(self, sample_data: list[HistoricalData]) -> None:
        """Test VWAP calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        vwap = calculate_vwap(df)

        # Should return a Series with same length as input
        assert len(vwap) == len(sample_data)
        assert isinstance(vwap, pd.Series)

        # First value should be valid (VWAP starts immediately)
        assert not pd.isna(vwap.iloc[0])

    def test_calculate_cmf(self, sample_data: list[HistoricalData]) -> None:
        """Test CMF calculation."""
        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "open": d.open,
                    "high": d.high,
                    "low": d.low,
                    "close": d.close,
                    "volume": d.volume,
                }
                for d in sample_data
            ],
        )

        cmf = calculate_cmf(df, period=3)

        # Should return a Series with same length as input
        assert len(cmf) == len(sample_data)
        assert isinstance(cmf, pd.Series)

        # First few values should be NaN (warmup period)
        assert pd.isna(cmf.iloc[0])
        assert pd.isna(cmf.iloc[1])

    def test_indicator_strength_calculation(self, ta: TechnicalAnalysis) -> None:
        """Test indicator strength calculation."""
        # Test RSI strength
        strength = ta.calculate_rsi_strength(25.0)
        assert 0 <= strength <= 1
        assert strength == 1.0  # RSI < 30 should have strong buy strength

        strength = ta.calculate_rsi_strength(75.0)
        assert 0 <= strength <= 1
        assert strength == 0.0  # RSI > 70 should have strong sell strength

        strength = ta.calculate_rsi_strength(50.0)
        assert 0 <= strength <= 1
        assert (
            strength == 0.3
        )  # RSI in neutral range should have moderate sell strength

        # Test MACD strength
        strength = ta.calculate_macd_strength(1.5, 0.5)
        assert 0 <= strength <= 1
        assert strength == 0.7  # MACD > signal should have buy strength

        strength = ta.calculate_macd_strength(0.5, 1.5)
        assert 0 <= strength <= 1
        assert strength == 0.3  # MACD < signal should have sell strength

        # Test supertrend strength
        strength = ta.calculate_supertrend_strength(101.0, 100.0, 1)
        assert 0 <= strength <= 1
        assert strength == 0.9  # Strong buy: price above supertrend in uptrend

        strength = ta.calculate_supertrend_strength(99.0, 100.0, -1)
        assert 0 <= strength <= 1
        assert strength == 0.1  # Strong sell: price below supertrend in downtrend

        strength = ta.calculate_supertrend_strength(99.0, 100.0, 1)
        assert 0 <= strength <= 1
        assert (
            strength == 0.7
        )  # Moderate buy: price below supertrend but direction is up

        strength = ta.calculate_supertrend_strength(101.0, 100.0, -1)
        assert 0 <= strength <= 1
        assert (
            strength == 0.3
        )  # Moderate sell: price above supertrend but direction is down

    def test_calculate_combined_strength(self, ta: TechnicalAnalysis) -> None:
        """Test combined strength calculation."""
        # Test with all indicators pointing BUY
        strengths = {
            "rsi": 0.8,
            "macd": 0.7,
            "supertrend": 0.9,
            "price_action": 0.6,
        }

        combined = ta.calculate_combined_strength(strengths)
        assert 0 <= combined <= 1
        assert combined == 0.75  # Should be average of all strengths

        # Test with mixed indicators
        strengths = {
            "rsi": 0.8,  # BUY
            "macd": 0.3,  # SELL
            "supertrend": 0.9,  # BUY
            "price_action": 0.1,  # SELL
        }

        combined = ta.calculate_combined_strength(strengths)
        assert 0 <= combined <= 1
        assert combined == 0.525  # Should be average of all strengths

        # Test with single indicator
        strengths = {"rsi": 0.8}
        combined = ta.calculate_combined_strength(strengths)
        assert combined == 0.8  # Should be same as the only indicator

    def test_calculate_price_action_strength(self, ta: TechnicalAnalysis) -> None:
        """Test price action strength calculation."""
        # Test with recent uptrend (each close higher than previous and current price > last close)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=99.0,
                high=100.0,
                low=98.5,
                close=99.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=99.5,
                high=100.5,
                low=99.0,
                close=100.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1500,
                interval="1min",
            ),
        ]

        strength = ta.calculate_price_action_strength(
            historical_data,
            current_price=101.0,
        )
        assert 0 <= strength <= 1
        assert strength == 0.8  # Should detect strong uptrend

        # Test with recent downtrend (each close lower than previous and current price < last close)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=102.0,
                high=103.0,
                low=101.5,
                close=102.5,
                volume=1500,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=101.5,
                high=102.5,
                low=101.0,
                close=102.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_price_action_strength(
            historical_data,
            current_price=99.0,
        )
        assert 0 <= strength <= 1
        assert strength == 0.2  # Should detect strong downtrend

        # Test with sideways movement (small price range relative to price)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=100.5,
                low=99.9,
                close=100.4,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.4,
                high=100.6,
                low=100.0,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.5,
                high=100.7,
                low=100.1,
                close=100.6,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_price_action_strength(
            historical_data,
            current_price=100.0,
        )
        assert 0 <= strength <= 1
        assert strength == 0.4  # Should detect sideways movement

        # Test with minimal data (only 2 data points)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
        ]

        strength = ta.calculate_price_action_strength(
            historical_data,
            current_price=101.5,
        )
        assert 0 <= strength <= 1
        assert strength == 0.7  # Should detect moderate uptrend

    def test_calculate_volatility_strength(self, ta: TechnicalAnalysis) -> None:
        """Test volatility strength calculation."""
        # Test with high volatility (recent range > 2x average range)
        # Create data where recent range (30) is ~1.8x average range (~16.67)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=95.0,
                high=100.0,
                low=90.0,
                close=95.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=95.0,
                high=100.0,
                low=90.0,
                close=95.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=95.0,
                high=115.0,  # Large range
                low=85.0,  # Large range
                close=100.0,
                volume=1500,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volatility_strength(historical_data)
        assert 0 <= strength <= 1
        assert (
            strength == 0.6
        )  # Should detect moderate high volatility (recent range is 30, avg range is ~16.67, ratio ≈ 1.8)

        # Test with moderate high volatility (recent range > 1.5x average range)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=98.0,
                high=100.0,
                low=97.0,
                close=99.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=99.0,
                high=101.0,
                low=98.0,
                close=100.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=105.0,  # Moderate range
                low=95.0,  # Moderate range
                close=102.0,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volatility_strength(historical_data)
        assert 0 <= strength <= 1
        assert strength == 0.6  # Should detect moderate high volatility

        # Test with low volatility (recent range < average range)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=99.0,
                high=100.0,
                low=98.5,
                close=99.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=99.5,
                high=100.5,
                low=99.0,
                close=100.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=100.5,  # Small range
                low=99.8,  # Small range
                close=100.3,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volatility_strength(historical_data)
        assert 0 <= strength <= 1
        assert strength == 0.2  # Should detect low volatility

    def test_calculate_volume_strength(self, ta: TechnicalAnalysis) -> None:
        """Test volume strength calculation."""
        # Test with increasing volume
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1500,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volume_strength(historical_data)
        assert -1 <= strength <= 1
        assert strength > 0  # Increasing volume should have positive strength

        # Test with decreasing volume
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1500,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1200,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volume_strength(historical_data)
        assert -1 <= strength <= 1
        assert strength < 0  # Decreasing volume should have negative strength

        # Test with stable volume
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=100.5,
                high=101.5,
                low=100.0,
                close=101.0,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime.now(timezone.utc),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.5,
                volume=1000,
                interval="1min",
            ),
        ]

        strength = ta.calculate_volume_strength(historical_data)
        assert -1 <= strength <= 1
        assert strength == 0.0  # Stable volume should have neutral strength

    def test_get_indicator_value(self, ta: TechnicalAnalysis) -> None:
        """Test get_indicator_value method."""
        indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=1.5,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="supertrend",
                value=100.5,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
        ]

        # Test existing indicator
        value = ta.get_indicator_value(indicators, "rsi")
        assert value == 25.0

        # Test non-existing indicator
        value = ta.get_indicator_value(indicators, "nonexistent")
        assert value is None

        # Test with empty indicators list
        value = ta.get_indicator_value([], "rsi")
        assert value is None

    def test_calculate_indicators_with_empty_data(
        self,
        ta: TechnicalAnalysis,
    ) -> None:
        """Test calculate_indicators with empty data."""
        indicators = ta.calculate_indicators([])
        assert indicators == []

    def test_calculate_indicators_with_insufficient_data(
        self,
        ta: TechnicalAnalysis,
    ) -> None:
        """Test calculate_indicators with insufficient data."""
        # Only 2 data points (need at least 15 for TA)
        insufficient_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000,
                interval="1min",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 31, tzinfo=timezone.utc),
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

    def test_calculate_indicators(
        self,
        ta: TechnicalAnalysis,
        sufficient_data: list[HistoricalData],
    ) -> None:
        """Test calculate_indicators method."""
        indicators = ta.calculate_indicators(sufficient_data)

        # Should return a list of indicators
        assert isinstance(indicators, list)
        # Should return some indicators for sufficient data
        assert len(indicators) > 0

        # Check that indicators have expected properties
        for indicator in indicators:
            assert hasattr(indicator, "name")
            assert hasattr(indicator, "value")
            assert hasattr(indicator, "timestamp")
            assert hasattr(indicator, "metadata")
            assert isinstance(indicator.name, str)
            assert isinstance(indicator.value, (int, float))
            assert isinstance(indicator.timestamp, datetime)
            assert isinstance(indicator.metadata, dict)

    def test_calculate_indicator_values(self) -> None:
        """Test individual indicator calculations with known values."""
        # Create test data with known values
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 9, 31, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 9, 32, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 9, 33, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 9, 34, tzinfo=timezone.utc),
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000, 1200, 1500, 1800, 2000],
        }

        df = pd.DataFrame(data)

        # Test RSI calculation
        rsi = calculate_rsi(df, period=3)
        assert len(rsi) == 5
        assert pd.isna(rsi.iloc[0])  # First value should be NaN
        assert pd.isna(rsi.iloc[1])  # Second value should be NaN

        # Test MACD calculation
        macd_line, signal_line, histogram = calculate_macd(
            df,
            fast_period=3,
            slow_period=5,
            signal_period=2,
        )
        assert len(macd_line) == 5
        assert pd.isna(macd_line.iloc[0])  # First value should be NaN
        assert pd.isna(macd_line.iloc[1])  # Second value should be NaN

        # Test ATR calculation
        atr = calculate_atr(df, period=3)
        assert len(atr) == 5
        assert pd.isna(atr.iloc[0])  # First value should be NaN

        # Test VWAP calculation
        vwap = calculate_vwap(df)
        assert len(vwap) == 5
        assert not pd.isna(vwap.iloc[0])  # First value should be valid

        # Test CMF calculation
        cmf = calculate_cmf(df, period=3)
        assert len(cmf) == 5
        assert pd.isna(cmf.iloc[0])  # First value should be NaN

    def test_edge_cases(self) -> None:
        """Test edge cases for indicator calculations."""
        # Test with constant prices (should handle division by zero)
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc),
                datetime(2023, 1, 1, 9, 31, tzinfo=timezone.utc),
            ],
            "open": [100.0, 100.0],
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "close": [100.0, 100.0],
            "volume": [1000, 1000],
        }

        df = pd.DataFrame(data)

        # These should not raise exceptions
        rsi = calculate_rsi(df, period=2)
        macd_line, signal_line, histogram = calculate_macd(df)
        atr = calculate_atr(df, period=2)
        vwap = calculate_vwap(df)
        cmf = calculate_cmf(df, period=2)

        # All values should be NaN due to insufficient data or constant prices
        assert all(pd.isna(rsi))
        assert all(pd.isna(macd_line))
        assert all(pd.isna(atr))
        assert not any(pd.isna(vwap))  # VWAP should handle constant prices
        assert all(pd.isna(cmf))

        # Test with insufficient data for period
        data = {
            "timestamp": [datetime(2023, 1, 1, 9, 30)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }

        df = pd.DataFrame(data)

        rsi = calculate_rsi(df, period=14)
        assert len(rsi) == 1
        assert pd.isna(rsi.iloc[0])

    def test_generate_signal(self, ta: TechnicalAnalysis) -> None:
        """Test signal generation."""
        # Create indicators for a strong BUY signal
        indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,  # Oversold
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=1.5,  # MACD line
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=0.5,  # Signal line
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="supertrend",
                value=100.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min", "direction": "up"},
            ),
            TAIndicator(
                name="supertrend_direction",
                value=1.0,  # 1 for up
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="vwap",
                value=99.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="cmf",
                value=0.2,  # Positive money flow
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=101.0)
        assert signal is not None
        assert signal[0] == "BUY"
        assert signal[1] > 0.5

        # Create indicators for a strong SELL signal
        indicators = [
            TAIndicator(
                name="rsi",
                value=75.0,  # Overbought
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=0.5,  # MACD line
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=1.5,  # Signal line
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="supertrend",
                value=100.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min", "direction": "down"},
            ),
            TAIndicator(
                name="supertrend_direction",
                value=-1.0,  # -1 for down
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="vwap",
                value=101.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="cmf",
                value=-0.2,  # Negative money flow
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=99.0)
        assert signal is not None
        assert signal[0] == "SELL"
        assert signal[1] > 0.5

    def test_generate_signal_with_missing_indicators(
        self,
        ta: TechnicalAnalysis,
    ) -> None:
        """Test generate_signal with missing indicators."""
        # Test with empty indicators list
        signal = ta.generate_signal([], current_price=100.0)
        assert signal is None

        # Test with minimal indicators
        indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,
                timestamp=datetime.now(timezone.utc),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] in ["BUY", "SELL", "NEUTRAL"]
