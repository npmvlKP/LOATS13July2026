"""
Technical Analysis module LOATS13July2026.
Implements custom indicators: Supertrend, VWAP, CMF.
Provides standalone indicator calculation functions.
"""

from typing import Any

import numpy as np
import pandas as pd
from pandas import Series

from .loats_logging import get_logger
from .models import HistoricalData, TAIndicator

# Optional Numba import for performance optimization
try:
    from numba import njit

    NUMBA_AVAILABLE = True
    # Test if cache parameter is supported in this numba version
    try:
        # Test cache support by trying to compile a simple function
        def _test_cache_support_func(x: Any) -> Any:
            return x

        njit(cache=True)(_test_cache_support_func)
        NJIT_SUPPORTS_CACHE = True
    except TypeError:
        # Fallback for older numba versions that don't support cache parameter
        NJIT_SUPPORTS_CACHE = False

    # Test if fastmath parameter is supported in this numba version
    try:
        # Test fastmath support by trying to compile a simple function
        def _test_fastmath_support_func(x: Any) -> Any:
            return x

        njit(fastmath=True)(_test_fastmath_support_func)
        NJIT_SUPPORTS_FASTMATH = True
    except TypeError:
        # Fallback for numba versions that don't support fastmath parameter
        NJIT_SUPPORTS_FASTMATH = False
except ImportError:
    NUMBA_AVAILABLE = False
    NJIT_SUPPORTS_CACHE = False
    NJIT_SUPPORTS_FASTMATH = False

    # Define dummy decorator if Numba not available
    def njit(func: Any) -> Any:
        return func


# Create the appropriate decorator based on cache and fastmath support
if NJIT_SUPPORTS_CACHE and NJIT_SUPPORTS_FASTMATH:

    def _supertrend_njit_decorator(func: Any) -> Any:
        return njit(cache=True, fastmath=True)(func)

elif NJIT_SUPPORTS_CACHE:

    def _supertrend_njit_decorator(func: Any) -> Any:
        return njit(cache=True)(func)

elif NJIT_SUPPORTS_FASTMATH:

    def _supertrend_njit_decorator(func: Any) -> Any:
        return njit(fastmath=True)(func)

else:

    def _supertrend_njit_decorator(func: Any) -> Any:
        return njit(func)


logger = get_logger(__name__)


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Series:
    """Calculate Relative Strength Index (RSI)."""
    if len(df) < period:
        return Series([np.nan] * len(df), index=df.index, dtype=np.float64)

    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Handle cases where avg_loss is 0
    if (avg_loss == 0).all() and (avg_gain > 0).any():
        rsi = rsi.fillna(100.0)
    else:
        rsi = rsi.fillna(50.0)

    rsi.iloc[:period] = np.nan
    return rsi.astype(np.float64)


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Moving Average Convergence Divergence (MACD)."""
    if len(df) < slow_period:
        return (
            pd.Series([np.nan] * len(df), index=df.index),
            pd.Series([np.nan] * len(df), index=df.index),
            pd.Series([np.nan] * len(df), index=df.index),
        )

    close = df["close"]
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    # Warmup period check
    macd_line.iloc[: slow_period - 1] = np.nan
    signal_line.iloc[: slow_period + signal_period - 2] = np.nan
    histogram.iloc[: slow_period + signal_period - 2] = np.nan

    return macd_line, signal_line, histogram


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    if len(df) < period:
        return pd.Series([np.nan] * len(df), index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    atr.iloc[:period] = np.nan
    return atr


@_supertrend_njit_decorator
def _supertrend_core(
    close_arr: np.ndarray,
    upper_band_arr: np.ndarray,
    lower_band_arr: np.ndarray,
    period: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Numba-optimized core Supertrend calculation.

    Performance-optimized version that reduces branching and improves cache locality.
    Uses pre-computation and state tracking to minimize per-iteration overhead.
    """
    n = len(close_arr)

    # Pre-allocate NumPy arrays for output
    supertrend_arr = np.full(n, np.nan, dtype=np.float64)
    direction_arr = np.full(n, np.nan, dtype=np.float64)

    # Initialize direction as 1 (bullish) - standard Supertrend convention
    curr_dir = 1
    prev_dir = 1  # Track previous direction to avoid array lookups
    prev_st = np.nan  # Track previous supertrend value

    # Initialize first valid position
    if period > 0:
        # Set initial supertrend value based on first period
        initial_close = close_arr[period - 1]
        initial_upper = upper_band_arr[period - 1]
        initial_lower = lower_band_arr[period - 1]

        if initial_close > initial_upper:
            curr_dir = 1
            supertrend_arr[period - 1] = initial_lower
        elif initial_close < initial_lower:
            curr_dir = -1
            supertrend_arr[period - 1] = initial_upper
        else:
            # Default to bullish if within bands
            supertrend_arr[period - 1] = initial_lower

        direction_arr[period - 1] = curr_dir
        prev_st = supertrend_arr[period - 1]
        prev_dir = curr_dir

    # Optimized loop with reduced branching and better cache locality
    for i in range(period, n):
        # Determine direction using direct comparison (optimized branching)
        close_val = close_arr[i]
        upper_prev = upper_band_arr[i - 1]
        lower_prev = lower_band_arr[i - 1]

        # Direction determination with minimal branching
        if close_val > upper_prev:
            curr_dir = 1
        elif close_val < lower_prev:
            curr_dir = -1
        # Else: keep current direction (no change)

        direction_arr[i] = curr_dir

        # Optimized supertrend calculation using state tracking
        if curr_dir == 1:
            st_val = lower_band_arr[i]
            # Apply trailing stop only if continuing bullish trend
            if prev_dir == 1 and not np.isnan(prev_st):
                st_val = max(st_val, prev_st)
        else:
            st_val = upper_band_arr[i]
            # Apply trailing stop only if continuing bearish trend
            if prev_dir == -1 and not np.isnan(prev_st):
                st_val = min(st_val, prev_st)

        supertrend_arr[i] = st_val

        # Update state for next iteration (avoids array lookups)
        prev_dir = curr_dir
        prev_st = st_val

    return supertrend_arr, direction_arr


def calculate_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """Calculate Supertrend indicator using optimized NumPy/Numba operations.

    Performance-optimized version that uses:
    1. Vectorized NumPy operations for band calculations
    2. Numba JIT compilation for the state-dependent loop
    3. Efficient NumPy array indexing

    The Supertrend algorithm is inherently sequential (direction depends on
    previous direction), so we cannot fully vectorize. However, by using
    Numba to compile the loop to machine code, we achieve significant speedup
    for large datasets while maintaining identical results.
    """
    n = len(df)

    if n < period:
        return (
            pd.Series([np.nan] * n, index=df.index),
            pd.Series([np.nan] * n, index=df.index),
        )

    # Extract data as NumPy arrays for faster access
    close_arr: np.ndarray = np.asarray(df["close"].values, dtype=np.float64)
    high_arr: np.ndarray = np.asarray(df["high"].values, dtype=np.float64)
    low_arr: np.ndarray = np.asarray(df["low"].values, dtype=np.float64)

    # Vectorized ATR calculation
    atr = calculate_atr(df, period)
    atr_arr: np.ndarray = np.asarray(atr.values, dtype=np.float64)

    # Vectorized band calculations
    hl2_arr = (high_arr + low_arr) / 2.0
    upper_band_arr = hl2_arr + (multiplier * atr_arr)
    lower_band_arr = hl2_arr - (multiplier * atr_arr)

    # Initialize arrays before the conditional
    supertrend_arr: np.ndarray[tuple[int], np.dtype[np.float64]] = np.full(
        n, np.nan, dtype=np.float64
    )
    direction_arr: np.ndarray[tuple[int], np.dtype[np.float64]] = np.full(
        n, np.nan, dtype=np.float64
    )

    # Use optimized core function
    if NUMBA_AVAILABLE:
        supertrend_arr, direction_arr = _supertrend_core(
            close_arr, upper_band_arr, lower_band_arr, period
        )
    else:
        # Optimized fallback implementation if Numba not available
        # Uses state tracking to minimize array lookups and improve performance

        # Initialize state variables for performance optimization
        curr_dir = 1
        prev_dir = 1  # Track previous direction to avoid array lookups
        prev_st = np.nan  # Track previous supertrend value

        # Initialize first valid position
        if period > 0:
            initial_close = close_arr[period - 1]
            initial_upper = upper_band_arr[period - 1]
            initial_lower = lower_band_arr[period - 1]

            if initial_close > initial_upper:
                curr_dir = 1
                supertrend_arr[period - 1] = initial_lower
            elif initial_close < initial_lower:
                curr_dir = -1
                supertrend_arr[period - 1] = initial_upper
            else:
                # Default to bullish if within bands
                supertrend_arr[period - 1] = initial_lower

            direction_arr[period - 1] = curr_dir
            prev_st = supertrend_arr[period - 1]
            prev_dir = curr_dir

        # Performance-optimized loop with state tracking
        for i in range(period, n):
            # Determine direction using direct comparison
            if close_arr[i] > upper_band_arr[i - 1]:
                curr_dir = 1
            elif close_arr[i] < lower_band_arr[i - 1]:
                curr_dir = -1
            # Else: keep current direction (no change)

            direction_arr[i] = curr_dir

            # Optimized supertrend calculation using state tracking
            if curr_dir == 1:
                st_val = lower_band_arr[i]
                # Apply trailing stop only if continuing bullish trend
                if prev_dir == 1 and not np.isnan(prev_st):
                    st_val = max(st_val, prev_st)
            else:
                st_val = upper_band_arr[i]
                # Apply trailing stop only if continuing bearish trend
                if prev_dir == -1 and not np.isnan(prev_st):
                    st_val = min(st_val, prev_st)

            supertrend_arr[i] = st_val

            # Update state for next iteration (avoids array lookups)
            prev_dir = curr_dir
            prev_st = st_val

    # Convert back to pandas Series with proper index
    supertrend = Series(supertrend_arr, index=df.index, dtype=np.float64)
    direction = Series(direction_arr, index=df.index, dtype=np.float64)

    return supertrend, direction


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price (VWAP)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    typical_price = (high + low + close) / 3
    cumulative_tpv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()

    # Handle zero volume case to avoid NaN
    vwap = cumulative_tpv / cumulative_volume
    # When volume is zero, return the typical price instead of NaN
    vwap = vwap.fillna(typical_price)
    return vwap


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Calculate Chaikin Money Flow (CMF)."""
    if len(df) < period:
        return pd.Series([np.nan] * len(df), index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    mfm = ((close - low) - (high - close)) / ((high - low).replace(0, 1))
    mfv = mfm * volume
    cmf = mfv.rolling(period).sum() / volume.rolling(period).sum()

    cmf.iloc[:period] = np.nan
    return cmf

def calculate_bbands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands (BBANDS).

    Returns: (upper_band, middle_band, lower_band)
    """
    if len(df) < period:
        return (
            pd.Series([np.nan] * len(df), index=df.index),
            pd.Series([np.nan] * len(df), index=df.index),
            pd.Series([np.nan] * len(df), index=df.index),
        )

    close = df["close"]
    middle_band = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()

    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)

    # Set initial values to NaN for warmup period
    upper_band.iloc[:period] = np.nan
    middle_band.iloc[:period] = np.nan
    lower_band.iloc[:period] = np.nan

    return upper_band, middle_band, lower_band

def calculate_cci(
    df: pd.DataFrame, period: int = 20, constant: float = 0.015
) -> pd.Series:
    """Calculate Commodity Channel Index (CCI).

    CCI measures the difference between current price and historical average price.
    Values above +100 indicate overbought, below -100 indicate oversold.
    """
    if len(df) < period:
        return pd.Series([np.nan] * len(df), index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Calculate Typical Price
    typical_price = (high + low + close) / 3

    # Calculate Simple Moving Average of Typical Price
    sma = typical_price.rolling(window=period).mean()

    # Calculate Mean Deviation
    mean_deviation = typical_price.rolling(window=period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )

    # Calculate CCI
    cci = (typical_price - sma) / (mean_deviation * constant)

    cci.iloc[:period] = np.nan
    return cci

def calculate_hurst_exponent(
    df: pd.DataFrame, period: int = 100, min_lag: int = 10, max_lag: int = 50
) -> float:
    """Calculate Hurst exponent for regime detection.

    Hurst exponent measures long-term memory of time series:
    - H = 0.5: Random walk (Brownian motion)
    - H > 0.5: Trending/mean-reverting behavior
    - H < 0.5: Mean-reverting behavior

    Uses rescaled range (R/S) analysis method.
    """
    if len(df) < period:
        return 0.5  # Default neutral value

    close_prices = df["close"].values[-period:]
    returns = np.diff(np.log(close_prices))

    # Calculate R/S for different lags
    lags = range(min_lag, max_lag + 1)
    rs_values = []

    for lag in lags:
        if len(returns) < lag:
            continue

        # Split into chunks
        n_chunks = len(returns) // lag
        if n_chunks < 2:
            continue

        rs_chunk = []
        for i in range(n_chunks):
            chunk = returns[i * lag : (i + 1) * lag]
            if len(chunk) < lag:
                continue

            # Calculate mean and cumulative deviation
            mean = np.mean(chunk)
            cum_dev = np.cumsum(chunk - mean)

            # Calculate range (R) and standard deviation (S)
            R = np.max(cum_dev) - np.min(cum_dev)
            S = np.std(chunk)

            if S > 0:
                rs_chunk.append(R / S)

        if rs_chunk:
            rs_values.append((lag, np.mean(rs_chunk)))

    if len(rs_values) < 3:
        return 0.5

    # Fit linear regression to log(R/S) vs log(lag)
    log_lags = np.log([x[0] for x in rs_values])
    log_rs = np.log([x[1] for x in rs_values])

    # Calculate Hurst exponent as slope of regression
    A = np.vstack([log_lags, np.ones(len(log_lags))]).T
    slope, _ = np.linalg.lstsq(A, log_rs, rcond=None)[0]

    return float(np.clip(slope, 0.0, 1.0))

def detect_regime(
    df: pd.DataFrame,
    hurst_period: int = 100,
    adx_period: int = 14,
    cci_period: int = 20,
) -> str:
    """Detect market regime using multiple indicators.

    Returns: "TRENDING", "MEAN_REVERTING", or "RANGING"
    """
    if len(df) < max(hurst_period, adx_period, cci_period):
        return "RANGING"  # Default conservative regime

    # Calculate Hurst exponent
    hurst = calculate_hurst_exponent(df, period=hurst_period)

    # Calculate ADX (already available in rules module, but we'll implement here too)
    adx = calculate_adx_standalone(df, period=adx_period)

    # Calculate CCI
    cci = calculate_cci(df, period=cci_period)
    cci_value = cci.iloc[-1] if not pd.isna(cci.iloc[-1]) else 0

    # Regime detection logic
    if hurst > 0.6 and adx > 25:  # Strong trending behavior
        return "TRENDING"
    elif hurst < 0.4 and adx < 20:  # Strong mean-reverting behavior
        return "MEAN_REVERTING"
    elif abs(cci_value) > 100:  # Overbought/oversold conditions
        return "MEAN_REVERTING"
    else:  # Default to ranging
        return "RANGING"

def calculate_adx_standalone(
    df: pd.DataFrame, period: int = 14
) -> float:
    """Standalone ADX calculation for TA module consistency."""
    if len(df) < period:
        return 25.0  # Default neutral value

    # Calculate +DM, -DM, and TR
    df_copy = df.copy()
    df_copy["+DM"] = df_copy["high"].diff()
    df_copy["-DM"] = -df_copy["low"].diff()
    df_copy.loc[df_copy["+DM"] < 0, "+DM"] = 0
    df_copy.loc[df_copy["-DM"] < 0, "-DM"] = 0

    df_copy["TR"] = pd.concat(
        [
            df_copy["high"] - df_copy["low"],
            abs(df_copy["high"] - df_copy["close"].shift()),
            abs(df_copy["low"] - df_copy["close"].shift()),
        ],
        axis=1,
    ).max(axis=1)

    # Calculate smoothed values
    df_copy["+DM_smooth"] = df_copy["+DM"].rolling(window=period).mean()
    df_copy["-DM_smooth"] = df_copy["-DM"].rolling(window=period).mean()
    df_copy["TR_smooth"] = df_copy["TR"].rolling(window=period).mean()

    # Calculate +DI and -DI
    df_copy["+DI"] = 100 * (df_copy["+DM_smooth"] / df_copy["TR_smooth"])
    df_copy["-DI"] = 100 * (df_copy["-DM_smooth"] / df_copy["TR_smooth"])

    # Calculate DX and ADX
    df_copy["DX"] = 100 * abs(df_copy["+DI"] - df_copy["-DI"]) / (df_copy["+DI"] + df_copy["-DI"])
    adx = df_copy["DX"].rolling(window=period).mean().iloc[-1]

    return float(adx) if not pd.isna(adx) else 25.0


class TechnicalAnalysis:
    """Technical Analysis engine with custom indicators."""

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate_rsi_strength(self, rsi_value: float) -> float:
        if rsi_value < 30:
            return 1.0
        elif rsi_value > 70:
            return 0.0
        return 0.3

    def calculate_macd_strength(
        self, macd_value: float, macd_signal_value: float
    ) -> float:
        if macd_value > macd_signal_value:
            return 0.7
        return 0.3

    def calculate_supertrend_strength(
        self, current_price: float, supertrend_value: float, direction: int
    ) -> float:
        if direction == 1:
            return 0.9 if current_price > supertrend_value else 0.7
        return 0.1 if current_price < supertrend_value else 0.3

    def calculate_combined_strength(self, strengths: dict[str, float]) -> float:
        if not strengths:
            return 0.5
        return sum(strengths.values()) / len(strengths)

    def calculate_price_action_strength(
        self, historical_data: list[HistoricalData], current_price: float
    ) -> float:
        if len(historical_data) < 2:
            return 0.5

        closes = [h.close for h in historical_data]
        if len(closes) >= 3:
            # Check strong uptrend
            if (
                current_price > closes[-1]
                and closes[-1] > closes[-2]
                and closes[-2] > closes[-3]
            ):
                return 0.8
            # Check strong downtrend
            elif (
                current_price < closes[-1]
                and closes[-1] < closes[-2]
                and closes[-2] < closes[-3]
            ):
                return 0.2
            # Check sideways movement
            elif (
                max(closes + [current_price]) - min(closes + [current_price])
            ) / current_price < 0.01:
                return 0.4

        # Basic trend detection
        if current_price > closes[-1]:
            return 0.7
        elif current_price < closes[-1]:
            return 0.3
        return 0.5

    def calculate_volatility_strength(
        self, historical_data: list[HistoricalData]
    ) -> float:
        if len(historical_data) < 2:
            return 0.5

        ranges = [(h.high - h.low) for h in historical_data]
        # Calculate avg of previous ranges
        avg_range = (
            sum(ranges[:-1]) / (len(ranges) - 1) if len(ranges) > 1 else ranges[0]
        )
        recent_range = ranges[-1]

        if avg_range == 0:
            return 0.5

        ratio = recent_range / avg_range
        # General volatility behavior
        if ratio > 1.5:
            return 0.6
        elif ratio < 0.8:
            return 0.2
        return 0.5

    def calculate_volume_strength(self, historical_data: list[HistoricalData]) -> float:
        if len(historical_data) < 2:
            return 0.0

        volumes = [h.volume for h in historical_data]
        # Increasing volume
        if all(volumes[i] < volumes[i + 1] for i in range(len(volumes) - 1)):
            return 0.5
        # Decreasing volume
        elif all(volumes[i] > volumes[i + 1] for i in range(len(volumes) - 1)):
            return -0.5
        return 0.0

    def get_indicator_value(
        self, indicators: list[TAIndicator], name: str
    ) -> float | None:
        for indicator in indicators:
            if indicator.name == name:
                return float(indicator.value)
        return None

    def calculate_indicators(
        self, historical_data: list[HistoricalData]
    ) -> list[TAIndicator]:
        indicators: list[TAIndicator] = []
        if not historical_data or len(historical_data) < 15:
            return indicators

        df = pd.DataFrame(
            {
                "timestamp": [h.timestamp for h in historical_data],
                "open": [h.open for h in historical_data],
                "high": [h.high for h in historical_data],
                "low": [h.low for h in historical_data],
                "close": [h.close for h in historical_data],
                "volume": [h.volume for h in historical_data],
            }
        )

        rsi = calculate_rsi(df).iloc[-1]
        if not pd.isna(rsi):
            indicators.append(
                TAIndicator(
                    name="rsi",
                    value=float(rsi),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard"},
                )
            )

        macd, signal, _ = calculate_macd(df)
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]
        if not pd.isna(macd_val):
            indicators.append(
                TAIndicator(
                    name="macd",
                    value=float(macd_val),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard"},
                )
            )
        if not pd.isna(signal_val):
            indicators.append(
                TAIndicator(
                    name="macd_signal",
                    value=float(signal_val),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard"},
                )
            )

        st_val, st_dir = calculate_supertrend(df)
        if not pd.isna(st_val.iloc[-1]):
            indicators.append(
                TAIndicator(
                    name="supertrend",
                    value=float(st_val.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={
                        "type": "standard",
                        "direction": "up" if st_dir.iloc[-1] == 1 else "down",
                    },
                )
            )
            indicators.append(
                TAIndicator(
                    name="supertrend_direction",
                    value=float(st_dir.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard"},
                )
            )

        # Add BBANDS indicators
        upper_band, middle_band, lower_band = calculate_bbands(df)
        if not pd.isna(upper_band.iloc[-1]):
            indicators.append(
                TAIndicator(
                    name="bbands_upper",
                    value=float(upper_band.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard", "period": 20},
                )
            )
            indicators.append(
                TAIndicator(
                    name="bbands_middle",
                    value=float(middle_band.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard", "period": 20},
                )
            )
            indicators.append(
                TAIndicator(
                    name="bbands_lower",
                    value=float(lower_band.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard", "period": 20},
                )
            )

        # Add CCI indicator
        cci = calculate_cci(df)
        if not pd.isna(cci.iloc[-1]):
            indicators.append(
                TAIndicator(
                    name="cci",
                    value=float(cci.iloc[-1]),
                    timestamp=historical_data[-1].timestamp,
                    metadata={"type": "standard", "period": 20},
                )
            )

        # Add Hurst exponent
        hurst = calculate_hurst_exponent(df)
        indicators.append(
            TAIndicator(
                name="hurst",
                value=float(hurst),
                timestamp=historical_data[-1].timestamp,
                metadata={"type": "regime", "period": 100},
            )
        )

        # Add regime detection
        regime = detect_regime(df)
        indicators.append(
            TAIndicator(
                name="regime",
                value=0.9 if regime == "TRENDING" else 0.5 if regime == "MEAN_REVERTING" else 0.3,
                timestamp=historical_data[-1].timestamp,
                metadata={"type": "regime", "regime": regime},
            )
        )

        return indicators

    def generate_signal(
        self, indicators: list[TAIndicator], current_price: float
    ) -> tuple[str, float] | None:
        if not indicators:
            return None

        rsi = self.get_indicator_value(indicators, "rsi")
        macd = self.get_indicator_value(indicators, "macd")
        macd_signal = self.get_indicator_value(indicators, "macd_signal")

        # BUY signal
        if (
            rsi is not None
            and rsi < 30
            and macd is not None
            and macd_signal is not None
            and macd > macd_signal
        ):
            return ("BUY", 0.8)

        # SELL signal
        if (
            rsi is not None
            and rsi > 70
            and macd is not None
            and macd_signal is not None
            and macd < macd_signal
        ):
            return ("SELL", 0.8)

        return ("NEUTRAL", 0.5)


# Module-level singleton instance (alias `ta` for convenience)
technical_analysis = TechnicalAnalysis()
ta = technical_analysis
