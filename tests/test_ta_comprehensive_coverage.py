"""
Comprehensive test suite for ta.py to achieve 80%+ coverage.
Focuses on missing coverage areas including Numba logic, supertrend core functions,
and edge cases.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from loats.models import HistoricalData, TAIndicator
from loats.ta import (
    NJIT_SUPPORTS_CACHE,
    NJIT_SUPPORTS_FASTMATH,
    NUMBA_AVAILABLE,
    TechnicalAnalysis,
    _supertrend_njit_decorator,
    calculate_atr,
    calculate_cmf,
    calculate_macd,
    calculate_rsi,
    calculate_supertrend,
    calculate_vwap,
)


class TestTANumbaCoverage:
    """Test Numba-related functionality and initialization."""

    def test_numba_import_and_initialization(self):
        """Test Numba import and variable initialization."""
        # These variables should be defined regardless of Numba availability
        assert isinstance(NUMBA_AVAILABLE, bool)
        assert isinstance(NJIT_SUPPORTS_CACHE, bool)
        assert isinstance(NJIT_SUPPORTS_FASTMATH, bool)

        # Test that the decorator is callable
        assert callable(_supertrend_njit_decorator)

    def test_numba_decorator_behavior(self):
        """Test that the Numba decorator works correctly."""

        @_supertrend_njit_decorator
        def test_function(x: float) -> float:
            return x * 2.0

        # Should work regardless of Numba availability
        result = test_function(5.0)
        assert isinstance(result, (float, np.ndarray, np.generic))

    def test_numba_fallback_behavior(self):
        """Test behavior when Numba is not available."""
        # Test that we can still use the functions even if Numba fails
        data = {
            "timestamp": [datetime(2023, 1, 1, 9, 30, tzinfo=UTC)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
        df = pd.DataFrame(data)

        # These should work regardless of Numba availability
        rsi = calculate_rsi(df)
        assert len(rsi) == 1

        macd_line, signal_line, histogram = calculate_macd(df)
        assert len(macd_line) == 1

        atr = calculate_atr(df)
        assert len(atr) == 1

        supertrend, direction = calculate_supertrend(df)
        assert len(supertrend) == 1
        assert len(direction) == 1

        vwap = calculate_vwap(df)
        assert len(vwap) == 1

        cmf = calculate_cmf(df)
        assert len(cmf) == 1


class TestSupertrendCoreCoverage:
    """Test the supertrend core function and fallback implementation."""

    @pytest.fixture
    def sample_data_for_supertrend(self) -> list[HistoricalData]:
        """Fixture for sample historical data suitable for supertrend testing."""
        base_time = datetime(2023, 1, 1, 9, 30, tzinfo=UTC)
        return [
            HistoricalData(
                symbol="TEST",
                timestamp=base_time + timedelta(minutes=i),
                open=100.0 + i * 0.5,
                high=101.0 + i * 0.5,
                low=99.0 + i * 0.5,
                close=100.5 + i * 0.5,
                volume=1000 + i * 100,
                interval="1min",
            )
            for i in range(20)
        ]

    def test_supertrend_core_function_direct(self):
        """Test the _supertrend_core function directly."""
        # Import the core function
        from loats.ta import _supertrend_core

        # Create test data
        n = 10
        close_arr = np.array(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        )
        upper_band_arr = np.array(
            [102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0]
        )
        lower_band_arr = np.array(
            [98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
        )
        period = 3

        # Call the core function directly (it's already decorated)
        if hasattr(_supertrend_core, "py_func"):
            # If it's a Numba-compiled function, use the Python version
            supertrend_arr, direction_arr = _supertrend_core.py_func(
                close_arr, upper_band_arr, lower_band_arr, period
            )
        else:
            # If Numba is not available, call directly
            supertrend_arr, direction_arr = _supertrend_core(
                close_arr, upper_band_arr, lower_band_arr, period
            )

        # Verify outputs
        assert len(supertrend_arr) == n
        assert len(direction_arr) == n
        assert isinstance(supertrend_arr, np.ndarray)
        assert isinstance(direction_arr, np.ndarray)

    def test_supertrend_fallback_implementation(self, sample_data_for_supertrend):
        """Test the fallback supertrend implementation when Numba is not available."""
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
                for d in sample_data_for_supertrend
            ],
        )

        # Test with Numba disabled by mocking
        with patch("loats.ta.NUMBA_AVAILABLE", False):
            supertrend, direction = calculate_supertrend(df, period=5, multiplier=2.0)

            # Should still work with fallback implementation
            assert len(supertrend) == len(df)
            assert len(direction) == len(df)
            assert isinstance(supertrend, pd.Series)
            assert isinstance(direction, pd.Series)

            # Check that we get some valid values (not all NaN)
            assert not all(pd.isna(supertrend))
            assert not all(pd.isna(direction))

    def test_supertrend_with_various_periods(self, sample_data_for_supertrend):
        """Test supertrend calculation with different period values."""
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
                for d in sample_data_for_supertrend
            ],
        )

        # Test with different periods
        for period in [3, 5, 10]:
            supertrend, direction = calculate_supertrend(
                df, period=period, multiplier=2.0
            )

            assert len(supertrend) == len(df)
            assert len(direction) == len(df)

            # First few values should be NaN (warmup period)
            assert pd.isna(supertrend.iloc[0])
            assert pd.isna(direction.iloc[0])

    def test_supertrend_with_various_multipliers(self, sample_data_for_supertrend):
        """Test supertrend calculation with different multiplier values."""
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
                for d in sample_data_for_supertrend
            ],
        )

        # Test with different multipliers
        for multiplier in [1.0, 2.0, 3.0, 5.0]:
            supertrend, direction = calculate_supertrend(
                df, period=5, multiplier=multiplier
            )

            assert len(supertrend) == len(df)
            assert len(direction) == len(df)

            # Should have some valid values
            assert not all(pd.isna(supertrend))
            assert not all(pd.isna(direction))


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions for all TA functions."""

    def test_rsi_edge_case_all_gains(self):
        """Test RSI calculation when all prices are gains."""
        # Create data with all gains
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(20)
            ],
            "open": [100.0] * 20,
            "high": [100.0 + i for i in range(20)],
            "low": [100.0] * 20,
            "close": [100.0 + i for i in range(20)],
            "volume": [1000] * 20,
        }

        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=5)

        # Should handle all gains without errors
        assert len(rsi) == 20
        assert not all(pd.isna(rsi))

        # Check that we get high RSI values for strong uptrend
        valid_rsi = rsi.dropna()
        if len(valid_rsi) > 0:
            assert all(valid_rsi >= 50.0)  # Should be bullish

    def test_rsi_edge_case_all_losses(self):
        """Test RSI calculation when all prices are losses."""
        # Create data with all losses
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(20)
            ],
            "open": [100.0] * 20,
            "high": [100.0] * 20,
            "low": [100.0 - i for i in range(20)],
            "close": [100.0 - i for i in range(20)],
            "volume": [1000] * 20,
        }

        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=5)

        # Should handle all losses without errors
        assert len(rsi) == 20
        assert not all(pd.isna(rsi))

        # Check that we get low RSI values for strong downtrend
        valid_rsi = rsi.dropna()
        if len(valid_rsi) > 0:
            assert all(valid_rsi <= 50.0)  # Should be bearish

    def test_macd_edge_case_constant_prices(self):
        """Test MACD calculation with constant prices."""
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(30)
            ],
            "open": [100.0] * 30,
            "high": [100.0] * 30,
            "low": [100.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000] * 30,
        }

        df = pd.DataFrame(data)
        macd_line, signal_line, histogram = calculate_macd(
            df, fast_period=5, slow_period=10, signal_period=3
        )

        # Should handle constant prices without errors
        assert len(macd_line) == 30
        assert len(signal_line) == 30
        assert len(histogram) == 30

        # All values should be NaN or zero due to constant prices
        assert all(pd.isna(macd_line) | (macd_line == 0))
        assert all(pd.isna(signal_line) | (signal_line == 0))
        assert all(pd.isna(histogram) | (histogram == 0))

    def test_atr_edge_case_small_ranges(self):
        """Test ATR calculation with very small price ranges."""
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(20)
            ],
            "open": [100.0] * 20,
            "high": [100.01] * 20,  # Very small range
            "low": [99.99] * 20,  # Very small range
            "close": [100.0] * 20,
            "volume": [1000] * 20,
        }

        df = pd.DataFrame(data)
        atr = calculate_atr(df, period=5)

        # Should handle small ranges without errors
        assert len(atr) == 20
        assert not all(pd.isna(atr))

        # ATR values should be very small
        valid_atr = atr.dropna()
        if len(valid_atr) > 0:
            assert all(valid_atr < 0.1)  # Should be very small ATR values

    def test_vwap_edge_case_zero_volume(self):
        """Test VWAP calculation with zero volume."""
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(10)
            ],
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.5] * 10,
            "volume": [0] * 10,  # Zero volume
        }

        df = pd.DataFrame(data)
        vwap = calculate_vwap(df)

        # Should handle zero volume gracefully
        assert len(vwap) == 10
        assert not all(pd.isna(vwap))  # Should return typical price when volume is zero

    def test_cmf_edge_case_zero_volume(self):
        """Test CMF calculation with zero volume."""
        data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(20)
            ],
            "open": [100.0] * 20,
            "high": [101.0] * 20,
            "low": [99.0] * 20,
            "close": [100.5] * 20,
            "volume": [0] * 20,  # Zero volume
        }

        df = pd.DataFrame(data)
        cmf = calculate_cmf(df, period=5)

        # Should handle zero volume gracefully
        assert len(cmf) == 20
        # Should be NaN due to division by zero in CMF calculation
        assert all(pd.isna(cmf))


class TestTechnicalAnalysisClassEdgeCases:
    """Test edge cases for the TechnicalAnalysis class methods."""

    @pytest.fixture
    def ta(self) -> TechnicalAnalysis:
        """Fixture for TechnicalAnalysis instance."""
        return TechnicalAnalysis()

    def test_calculate_price_action_strength_edge_cases(self, ta: TechnicalAnalysis):
        """Test price action strength with various edge cases."""
        # Test with exactly 2 data points
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

        # Test with current price exactly at last close
        strength = ta.calculate_price_action_strength(
            historical_data, current_price=101.0
        )
        assert strength == 0.5  # Should be neutral

        # Test with current price slightly above last close
        strength = ta.calculate_price_action_strength(
            historical_data, current_price=101.1
        )
        assert strength == 0.7  # Should be bullish

        # Test with current price slightly below last close
        strength = ta.calculate_price_action_strength(
            historical_data, current_price=100.9
        )
        assert strength == 0.3  # Should be bearish

    def test_calculate_volatility_strength_edge_cases(self, ta: TechnicalAnalysis):
        """Test volatility strength with edge cases."""
        # Test with exactly 2 data points
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

        strength = ta.calculate_volatility_strength(historical_data)
        assert 0 <= strength <= 1

        # Test with zero range in one of the data points
        historical_data[0].high = 100.0
        historical_data[0].low = 100.0

        strength = ta.calculate_volatility_strength(historical_data)
        assert 0 <= strength <= 1

    def test_calculate_volume_strength_edge_cases(self, ta: TechnicalAnalysis):
        """Test volume strength with edge cases."""
        # Test with exactly 2 data points with same volume
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
        assert strength == 0.0  # Should be neutral for same volume

        # Test with very small volume difference
        historical_data[1].volume = 1001
        strength = ta.calculate_volume_strength(historical_data)
        assert strength > 0  # Should be slightly positive

    def test_calculate_indicators_with_boundary_data(self, ta: TechnicalAnalysis):
        """Test calculate_indicators with exactly 15 data points (minimum)."""
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
            for i in range(15)  # Exactly 15 data points
        ]

        indicators = ta.calculate_indicators(boundary_data)

        # Should work with exactly 15 data points
        assert isinstance(indicators, list)
        # Should have some indicators
        assert len(indicators) > 0

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
        assert isinstance(indicators, list)
        assert len(indicators) > 0

    def test_generate_signal_with_boundary_rsi_values(self, ta: TechnicalAnalysis):
        """Test signal generation with RSI exactly at boundaries."""
        # Test with RSI exactly at 30 (not < 30)
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

        # Test with RSI exactly at 70 (not > 70)
        indicators[0].value = 70.0
        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # RSI=70 is not > 70, so no SELL signal

    def test_generate_signal_with_equal_macd_values(self, ta: TechnicalAnalysis):
        """Test signal generation when MACD equals signal line."""
        indicators = [
            TAIndicator(
                name="rsi",
                value=25.0,  # Oversold
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd",
                value=1.0,  # MACD line
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
            TAIndicator(
                name="macd_signal",
                value=1.0,  # Signal line (equal to MACD)
                timestamp=datetime.now(UTC),
                metadata={"timeframe": "1min"},
            ),
        ]

        signal = ta.generate_signal(indicators, current_price=100.0)
        assert signal is not None
        assert signal[0] == "NEUTRAL"  # MACD not > signal, so no BUY signal


class TestPerformanceAndStressTests:
    """Test performance and stress scenarios."""

    def test_large_dataset_performance(self):
        """Test that TA functions can handle large datasets without crashing."""
        # Create a large dataset
        large_data = {
            "timestamp": [
                datetime(2023, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i)
                for i in range(1000)  # Large dataset
            ],
            "open": [100.0 + i * 0.1 for i in range(1000)],
            "high": [101.0 + i * 0.1 for i in range(1000)],
            "low": [99.0 + i * 0.1 for i in range(1000)],
            "close": [100.5 + i * 0.1 for i in range(1000)],
            "volume": [1000 + i * 10 for i in range(1000)],
        }

        df = pd.DataFrame(large_data)

        # These should all complete without errors
        rsi = calculate_rsi(df, period=14)
        assert len(rsi) == 1000

        macd_line, signal_line, histogram = calculate_macd(df)
        assert len(macd_line) == 1000

        atr = calculate_atr(df, period=14)
        assert len(atr) == 1000

        supertrend, direction = calculate_supertrend(df, period=10, multiplier=3.0)
        assert len(supertrend) == 1000
        assert len(direction) == 1000

        vwap = calculate_vwap(df)
        assert len(vwap) == 1000

        cmf = calculate_cmf(df, period=20)
        assert len(cmf) == 1000

    def test_ta_class_with_large_dataset(self):
        """Test TechnicalAnalysis class with large datasets."""
        ta = TechnicalAnalysis()

        # Create large historical data
        large_historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=datetime(2023, 1, 1, 9, 30, tzinfo=UTC)
                + timedelta(minutes=i),
                open=100.0 + i * 0.1,
                high=101.0 + i * 0.1,
                low=99.0 + i * 0.1,
                close=100.5 + i * 0.1,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(100)  # Large enough for TA
        ]

        # These should all complete without errors
        indicators = ta.calculate_indicators(large_historical_data)
        assert isinstance(indicators, list)
        assert len(indicators) > 0

        # Test signal generation
        signal = ta.generate_signal(indicators, current_price=150.0)
        assert signal is not None
        assert signal[0] in ["BUY", "SELL", "NEUTRAL"]
