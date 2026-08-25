"""Value-at-Risk (VaR) Calculation Engine

Implements multiple VaR calculation methods for risk management
with support for different asset classes and risk parameters.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
from dateutil import tz

# Import scipy modules at the top to avoid circular import issues
from scipy.stats import norm

# Setup logger
logger = logging.getLogger(__name__)


class VaREngine:
    """Main Value-at-Risk calculation engine"""

    def __init__(self, confidence_level: float = 0.95, window_size: int = 252):
        """Initialize VaR engine with default parameters

        Args:
            confidence_level: Confidence level for VaR calculations (default: 0.95)
            window_size: Number of trading days for historical data (default: 252)
        """
        self.confidence_level = self._validate_confidence(confidence_level)
        self.window_size = self._validate_window(window_size)
        self.tz = tz.gettz("Asia/Kolkata")

    def _validate_confidence(self, confidence_level: float) -> float:
        """Validate confidence level parameter"""
        if not 0 <= confidence_level <= 1:
            raise ValueError("Confidence level must be between 0 and 1")
        return confidence_level

    def _validate_window(self, window_size: int) -> int:
        """Validate window size parameter"""
        if window_size <= 0:
            raise ValueError("Window size must be > 0")
        return window_size

    def _validate_datetime(self, dt: datetime) -> datetime:
        """Validate and localize datetime to IST"""
        if not isinstance(dt, datetime):
            raise ValueError("Must provide datetime object")
        return dt.astimezone(self.tz)

    def _to_decimal(self, value: float) -> Decimal:
        """Convert float to Decimal for financial precision"""
        return Decimal(str(value))

    def historical_standalone(
        self,
        prices: list[Decimal],
        value: Decimal,
        days: int = 1,
        delta_risk: bool = False,
    ) -> dict[str, Decimal]:
        """
        Calculate standalone VaR using historical simulation.

        Args:
            prices: List of historical prices (new rather than returns)
            value: Portfolio value
            days: Holding period for VaR calculation (default: 1)
            delta_risk: Whether to calculate delta-adjusted VaR (default: False)

        Returns:
            Dictionary of VaRs and other risk measures:
                {'var': 0.0, 'delta': 0.0, 'expected_shortfall': 0.0, 'cv': 0.0}

        Raises:
            ValueError: If not enough historical data
        """
        if len(prices) < self.window_size:
            raise ValueError(
                f"Insufficient historical data. Need at least "
                f"{self.window_size} prices, got {len(prices)}"
            )

        prices_array = np.array([float(p) for p in prices])

        # Calculate returns
        if days == 1:
            returns_array = np.diff(prices_array) / prices_array[:-1]
        else:
            # Multi-day returns using compounding
            returns_array = np.empty(len(prices_array) - days, dtype=np.float64)
            for i in range(len(prices_array) - days):
                returns_array[i] = (prices_array[i + days] / prices_array[i]) - 1

        # Only use most recent window_size returns if we have more
        if len(returns_array) > self.window_size:
            returns_array = returns_array[-self.window_size :]

        # Calculate basic VaR
        var_percent = np.percentile(returns_array, 100 * (1 - self.confidence_level))

        # Calculate delta if requested
        delta_result = (
            Decimal("NaN") if not delta_risk else self._calculate_delta(returns_array)
        )

        # Calculate expected shortfall
        cond_var = self._calculate_cond_var(returns_array, var_percent)

        # Calculate coefficient of variation
        cv = self._calculate_cv(returns_array)

        results = {
            "var": value * (1 + Decimal(str(var_percent))),
            "delta": delta_result,
            "expected_shortfall": value * (1 + cond_var),
            "cv": cv,
        }

        logger.debug(
            f"Historical VaR Results: p={var_percent:.4f}, Delta={delta_result:.4f}"
        )

        return results

    def _calculate_delta(self, returns_array: np.ndarray) -> Decimal:
        """
        Calculate delta (sensitivity of asset value to small price changes)
        using second-order finite differences.
        """
        if len(returns_array) < 4:
            return Decimal("NaN")

        # Use first 1000 returns or all available
        n = min(1000, len(returns_array))
        data = returns_array[:n]

        # Second order finite differences:
        # delta = d^2r/ds^2 ≈ (r[i+2] - 2*r[i+1] + r[i])
        # Use diff with n=2 which gives length n-2
        delta_arr = np.diff(data, n=2)
        return self._to_decimal(float(np.mean(delta_arr)))

    def _calculate_cond_var(
        self, returns_array: np.ndarray, var_percent: float
    ) -> Decimal:
        """
        Calculate Conditional VaR (Expected Shortfall) - the average of returns
        below the VaR threshold.
        """
        if len(returns_array) == 0:
            return Decimal("NaN")

        grounded = returns_array[returns_array <= var_percent]
        if len(grounded) == 0:
            return Decimal("NaN")
        return self._to_decimal(np.mean(grounded))

    def _calculate_cv(self, returns_array: np.ndarray) -> Decimal:
        """
        Calculate coefficient of variation - standard deviation
        normalized by expected value.
        """
        std = np.std(returns_array)
        mean = np.mean(returns_array)
        return self._to_decimal(std / mean) if mean != 0 else Decimal("0")

    def historical_portfolio(
        self, positions: dict[str, tuple[Decimal, float]]
    ) -> tuple[Decimal, Decimal]:
        """Calculate portfolio VaR using historical simulation

        Args:
            positions: Dictionary of asset positions {asset_id: (quantity, price)}

        Returns:
            Tuple of portfolio value and VaR as Decimal
        """
        if not positions:
            return Decimal("0"), Decimal("0")

        # Calculate total portfolio value
        total_value = Decimal("0")
        for asset_id, (quantity, price) in positions.items():
            total_value += quantity * Decimal(str(price))

        if total_value == Decimal("0"):
            return Decimal("0"), Decimal("0")

        # For portfolio VaR, we need historical returns for each asset
        # Since we only have current prices, we'll use a simplified approach
        # This uses the parametric normal approach conceptually
        # but returns a basic VaR estimate based on asset weights

        # Calculate weighted average volatility
        weighted_vol = Decimal("0")
        for asset_id, (quantity, price) in positions.items():
            weight = (quantity * Decimal(str(price))) / total_value
            # Use a default volatility estimate based on asset type
            # In practice, this would come from historical data
            asset_vol = self._estimate_asset_volatility(asset_id, Decimal(str(price)))
            weighted_vol += weight * asset_vol

        # Calculate VaR using normal distribution approximation
        z_score = norm.ppf(self.confidence_level)
        var_amount = total_value * weighted_vol * Decimal(str(z_score))

        return total_value, var_amount

    def _estimate_asset_volatility(self, asset_id: str, price: Decimal) -> Decimal:
        """
        Estimate asset volatility based on asset type and price.
        In production, this would use actual historical data.
        """
        # Default volatility estimates by asset category
        # Equity: ~20-30% annual, Index: ~15-20%, Bonds: ~5-10%
        price_float = float(price)

        if price_float < 50:
            # Likely bonds or low-priced instruments
            return Decimal("0.05")  # 5% annual volatility
        elif price_float < 500:
            # Mid-cap stocks
            return Decimal("0.25")  # 25% annual volatility
        else:
            # Large-cap stocks or indices
            return Decimal("0.20")  # 20% annual volatility

    def parametric_normal(
        self,
        prices: list[Decimal],
        value: Decimal,
        days: int = 1,
        fat_tail_adjustment: float = 1.0,
        risk_contribution: bool = False,
    ) -> dict[str, Decimal | dict[str, Decimal]]:
        """
        Calculate VaR using parametric (normal distribution) approach with enhancements.

        Args:
            prices: List of historical prices
            value: Portfolio value
            days: Holding period for VaR calculation
            fat_tail_adjustment: Adjustment factor for fat tails (default: 1.0).
            risk_contribution: Whether to calculate individual risk
                contributions (default: False).

        Returns:
            Dictionary of VaR and related statistics:
                {'var': 0.0, 'z_score': 0.0, 'volatility': 0.0, 'vol}*days': 0.0,
                 'expected_shortfall': 0.0, 'dtails': 0.0, 'risk_contributions': {}}
        """

        if len(prices) < 50:
            logger.warning(
                f"Limited data points ({len(prices)}) for parametric approach. "
                "Results may be unreliable. Consider historical simulation instead."
            )

        prices_array = np.array([float(p) for p in prices])

        # Check if we have enough data for the requested days
        if days >= len(prices_array):
            raise ValueError(
                f"Not enough prices for {days}-day returns. "
                f"Need at least {days + 1} prices."
            )

        # Calculate returns
        if days == 1:
            # Avoid division by zero
            with np.errstate(divide="ignore", invalid="ignore"):
                returns_array = np.diff(prices_array) / prices_array[:-1]
            returns_array = returns_array[~np.isnan(returns_array)]
        else:
            returns_array = np.empty(len(prices_array) - days)
            for i in range(len(prices_array) - days):
                if prices_array[i] != 0:
                    returns_array[i] = prices_array[i + days] / prices_array[i] - 1
                else:
                    returns_array[i] = np.nan

        # Filter out NaN and infinite values
        returns_array = returns_array[~np.isnan(returns_array)]
        returns_array = returns_array[~np.isinf(returns_array)]

        if len(returns_array) == 0:
            raise ValueError("No valid returns calculated after filtering")

        # Calculate statistics
        mean = np.mean(returns_array)
        std = np.std(returns_array)

        # Calculate z-score for confidence level with fat tail adjustment
        if fat_tail_adjustment <= 0:
            raise ValueError("fat_tail_adjustment must be > 0")

        adjusted_z = norm.ppf(1 - self.confidence_level) * fat_tail_adjustment

        # Calculate VaR
        vol = std
        vol_multidays = std * np.sqrt(days)
        var_value = float(value) * (1 + mean) * (1 - adjusted_z * vol_multidays)

        # Calculate expected shortfall (conditional VaR)
        es_z = (1 - (1 / adjusted_z)) / (1 - self.confidence_level)
        es_std_adj = self._calculate_fat_tail_es_adjustment(
            std, days, self.confidence_level, fat_tail_adjustment
        )
        expected_shortfall = (
            float(value)
            * (1 + mean)
            * (
                1
                - adjusted_z * vol_multidays
                + 0.5 * es_z * float(es_std_adj) * vol_multidays * fat_tail_adjustment
            )
        )

        # Calculate individual risk contributions if requested
        risk_contributions: dict[str, Decimal] = {}
        if risk_contribution:
            # Implementation for calculating individual risk contributions
            pass  # Placeholder for potential implementation

        results: dict[str, Decimal | dict[str, Decimal]] = {
            "var": self._to_decimal(var_value),
            "z_score": self._to_decimal(adjusted_z),
            "volatility": self._to_decimal(vol),
            "vol_at_days": self._to_decimal(vol_multidays),
            "expected_shortfall": self._to_decimal(expected_shortfall),
            "fat_tail_adj": self._to_decimal(fat_tail_adjustment),
            "risk_contributions": risk_contributions,
        }

        return results

    def _calculate_fat_tail_es_adjustment(
        self, volatility: float, days: int, confidence_level: float, fat_tail_adj: float
    ) -> Decimal:
        """
        Calculate expected shortfall adjustment for fat tails.

        Implements Cornish-Fisher expansion for ES.
        """

        z = norm.ppf(1 - confidence_level)
        delta = (z**3 - z) / 6  # Skewness adjustment factor

        adjustment = (
            volatility * np.sqrt(days) * fat_tail_adj * (1 + delta / np.sqrt(days))
        )

        return self._to_decimal(adjustment)

    def _calculate_volatility(self, current_price: Decimal, days: int) -> float:
        """
        Calculate bond and equity volatility based on asset type.
        """
        from math import sqrt

        # Bond volatility - use a simple function
        if current_price < Decimal("50.0"):
            return 0.05  # Fixed income volatility

        # Equity volatility calculation
        atr = max(0.1 * float(current_price), 5)
        # Using ATR equivalent on closing prices
        avg_stddev = sqrt(days) * atr * sqrt(2)
        vol = min(avg_stddev, 0.5)

        return float(vol)

    def monte_carlo(
        self,
        current_price: Decimal,
        value: Decimal,
        days: int = 1,
        samples: int = 50_000,
        JensenUhlenbeck: bool = False,
        free_cash_flows: bool = False,
        tau: float = 0.02,
        encoding: str = "float",
        anticorrelated: bool = False,
    ) -> dict[str, Decimal]:
        """
        Monte Carlo Value-at-Risk calculation with advanced options.

        Args:
            current_price: Current market price
            value: Portfolio value
            days: Holding period
            samples: Number of simulations
            JensenUhlenbeck: Whether to use mean-reverting process
            free_cash_flows: Consider free cash flows in option valuation
            tau: Mean reversion speed
            encoding: Type of random number generator encoding
            anticorrelated: Whether to use an anticorrelated generator

        Returns:
            Dictionary of VaR results:
                {'var': 0.0, 'expected_shortfall': 0.0,
                 'ci_width': 0.0, 'simulated_paths': 0,
                 'underlying': 0.0}
        """
        # Define the seed for reproducibility
        SEED: int = 0x437

        # Validate samples
        if samples <= 0:
            raise ValueError("samples must be > 0")

        # Import required libraries
        from math import sqrt

        from numpy.random import default_rng

        rng = default_rng(SEED)

        def _brownian_basic(s0: float, r: float, v: float, t: float) -> np.ndarray:
            """
            Basic Geometric Brownian Motion path generator.

            Args:
                s0: Initial stock price
                r: Annual risk-free rate
                v: Volatility
                t: Time period

            Returns:
                Simulated stock prices array
            """
            t / samples
            r * t
            ln_rtn = (r - 0.5 * v**2) * t + v * sqrt(t) * rng.normal(size=samples)

            # Avoid zero or negative prices
            final_prices = s0 * np.exp(ln_rtn)
            final_prices = np.clip(final_prices, 0.01, None)

            return final_prices

        def _brownian_jensen_uhlenbeck(
            s0: float,
            r: float,
            v: float,
            t: float,
            theta: float = 0.05,
            tau: float = 0.02,
        ) -> np.ndarray:
            """
            Jensen-Uhlenbeck mean-reverting Brownian Motion path generator.

            Args:
                s0: Initial stock price
                r: Annual risk-free rate
                v: Volatility
                t: Time period
                theta: Long-term mean
                tau: Mean reversion speed

            Returns:
                Simulated stock prices array
            """
            dt = t / samples
            drift = theta + tau * (theta - s0)
            v * np.sqrt(t)

            r * t
            dWt = rng.normal(size=samples) * sqrt(dt)

            # Calculate OU terms
            term1 = theta * (1 - np.exp(-tau * t))
            term2 = s0 * np.exp(-tau * t)
            term3 = v * np.sqrt((1 - np.exp(-2 * tau * t)) / (2 * tau)) * dWt

            # Avoid zero or negative prices
            simulated_prices = np.clip(term1 + term2 + term3, 0.01, None)
            simulated_prices = simulated_prices + drift

            return simulated_prices  # type: ignore[no-any-return]

        brownian_func = (
            _brownian_jensen_uhlenbeck if JensenUhlenbeck else _brownian_basic
        )

        # Calculate variance and volatility
        volatility = self._calculate_volatility(current_price, days)

        # Run simulations
        if encoding == "float32":
            prices_float = brownian_func(
                float(current_price),
                0.05,
                volatility,
                days,  # risk-free rate
            ).astype(np.float32)
            simulated_prices = np.clip(prices_float, 0.001 * float(current_price), None)
        else:
            prices_arr = brownian_func(
                float(current_price),
                0.05,
                volatility,
                days,  # risk-free rate
            )
            simulated_prices = np.asarray(prices_arr, dtype=np.float64)

        # Calculate percentage returns
        pct_returns = (simulated_prices - float(current_price)) / float(current_price)
        percentage_returns = pct_returns

        vaR = -np.sort(percentage_returns)[int((1 - self.confidence_level) * samples)]
        cvar = np.mean(percentage_returns[percentage_returns <= -vaR])
        sd_ci = np.std(percentage_returns) / sqrt(samples)

        # Calculate value at risk, expected shortfall
        var_value = value * (1 - Decimal(str(vaR)))

        # Build results dictionary
        results = {
            "r": Decimal("0.05"),
            "var": var_value,
            "cvar": value * (1 - Decimal(str(vaR)) - Decimal(str(cvar))),
            "ci_width": Decimal(str(2 * sd_ci)),
            "simulated_paths": Decimal(str(samples)),
            "underlying": value * (1 + Decimal(str(np.mean(percentage_returns)))),
        }

        if free_cash_flows:
            fcf_result = self._calculate_fcf_impact(percentage_returns, days)
            results["fcf_impact"] = fcf_result
            results["adjusted_var"] = results["var"] * (1 - fcf_result)

        return results

    def _calculate_fcf_impact(self, returns: np.ndarray, days: int) -> Decimal:
        """
        Calculate the optional adjustment for free cash flows in option pricing.
        """
        deterministic_term = 0.10
        stochastic_term = np.mean(returns) * float(days)

        return self._to_decimal(
            deterministic_term * np.exp(1 - stochastic_term) if days > 10 else 0
        )

    def calculate(
        self, method: str, *args: Any, **kwargs: Any
    ) -> dict[str, Decimal | dict[str, Decimal]] | tuple[Decimal, Decimal]:
        """CMP-compliant entry point for VaR calculations

        Args:
            method: Calculation method (historical_standalone,
                parametric_normal, monte_carlo)
            *args: Positional arguments for selected method
            **kwargs: Keyword arguments for selected method

        Returns:
            VaR results as dict or tuple depending on method
        """
        from collections.abc import Callable
        from typing import Any

        method_map: dict[str, Callable[..., Any]] = {
            "historical_standalone": self.historical_standalone,
            "historical_portfolio": self.historical_portfolio,
            "parametric_normal": self.parametric_normal,
            "monte_carlo": self.monte_carlo,
        }

        if method not in method_map:
            raise ValueError(f"Unsupported method: {method}")

        try:
            logger.info(f"Calculating VaR using {method} method")
            result: Any = method_map[method](*args, **kwargs)
            return result  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"VaR calculation failed: {e!s}")
            raise
