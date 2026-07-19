"""
Technical Analysis module LOATS13July2026.
Implements custom indicators: Supertrend, VWAP, CMF.
Provides standalone indicator calculation functions.
"""
import numpy as np
import pandas as pd

from .logging import get_logger
from .models import HistoricalData, TAIndicator

logger = get_logger(__name__)

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    if len(df) < period:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=np.float64)

    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = delta.where(delta < 0, 0)

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
    macd_line.iloc[:slow_period - 1] = np.nan
    signal_line.iloc[:slow_period + signal_period - 2] = np.nan
    histogram.iloc[:slow_period + signal_period - 2] = np.nan

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

def calculate_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """Calculate Supertrend indicator."""
    if len(df) < period:
        return (
            pd.Series([np.nan] * len(df), index=df.index),
            pd.Series([np.nan] * len(df), index=df.index),
        )

    high = df["high"]
    low = df["low"]
    close = df["close"]

    atr = calculate_atr(df, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(np.nan, index=close.index)
    curr_dir = 1

    for i in range(period, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            curr_dir = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            curr_dir = -1

        direction.iloc[i] = curr_dir

        if curr_dir == 1:
            supertrend.iloc[i] = lower_band.iloc[i]
            if not pd.isna(supertrend.iloc[i - 1]) and direction.iloc[i - 1] == 1:
                supertrend.iloc[i] = max(supertrend.iloc[i], supertrend.iloc[i - 1])
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
            if not pd.isna(supertrend.iloc[i - 1]) and direction.iloc[i - 1] == -1:
                supertrend.iloc[i] = min(supertrend.iloc[i], supertrend.iloc[i - 1])

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

    vwap = cumulative_tpv / cumulative_volume
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

class TechnicalAnalysis:
    """Technical Analysis engine custom indicators."""

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate_rsi_strength(self, rsi_value: float) -> float:
        if rsi_value < 30:
            return 1.0
        elif rsi_value > 70:
            return 0.0
        return 0.3

    def calculate_macd_strength(self, macd_value: float, macd_signal_value: float) -> float:
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
            if (current_price > closes[-1] and closes[-1] > closes[-2] and closes[-2] > closes[-3]):
                return 0.8
            # Check strong downtrend
            elif (current_price < closes[-1] and closes[-1] < closes[-2] and closes[-2] < closes[-3]):
                return 0.2
            # Check sideways movement
            elif max(closes + [current_price]) - min(closes + [current_price]) / current_price < 0.01:
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
        # Calculate avg previous ranges
        avg_range = sum(ranges[:-1]) / (len(ranges) - 1) if len(ranges) > 1 else ranges[0]
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

        df = pd.DataFrame({
            "timestamp": [h.timestamp for h in historical_data],
            "open": [h.open for h in historical_data],
            "high": [h.high for h in historical_data],
            "low": [h.low for h in historical_data],
            "close": [h.close for h in historical_data],
            "volume": [h.volume for h in historical_data],
        })

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
            rsi is not None and rsi < 30 and
            macd is not None and macd_signal is not None and
            macd > macd_signal
        ):
            return ("BUY", 0.8)

        # SELL signal
        if (
            rsi is not None and rsi > 70 and
            macd is not None and macd_signal is not None and
            macd < macd_signal
        ):
            return ("SELL", 0.8)

        return ("NEUTRAL", 0.5)

# Module-level singleton instance (alias `ta` for convenience)
technical_analysis = TechnicalAnalysis()
ta = technical_analysis
