"""
Options module for LOATS13July2026.
Implements IV calculation, Greeks, and Black-Scholes model.
"""

from datetime import datetime

import numpy as np
from py_vollib.black_scholes import black_scholes
from py_vollib.black_scholes.greeks.analytical import delta, gamma, rho, theta, vega
from py_vollib.ref_python.black_scholes.implied_volatility import implied_volatility
from scipy.optimize import newton

from .logging import get_logger
from .models import Greeks, OptionContract, OptionType

logger = get_logger(__name__)


class OptionsEngine:
    """Options pricing and analysis engine."""

    def __init__(self):
        """Initialize OptionsEngine."""
        self.risk_free_rate = 0.05  # Default risk-free rate (5%)

    def set_risk_free_rate(self, rate: float) -> None:
        """
        Set the risk-free rate.

        Args:
            rate: Risk-free rate as decimal (e.g., 0.05 for 5%)
        """
        self.risk_free_rate = rate

    def calculate_greeks(
        self,
        S: float,
        K: float,
        t: float,
        r: float | None = None,
        sigma: float = 0.2,
        option_type: OptionType = OptionType.CALL,
    ) -> Greeks:
        """
        Calculate Greeks for an option using Black-Scholes model.

        Args:
            S: Current stock/underlying price
            K: Strike price
            t: Time to expiration in years
            r: Risk-free rate (uses instance rate if None)
            sigma: Volatility
            option_type: Option type (CALL or PUT)

        Returns:
            Greeks object with delta, gamma, theta, vega, rho, and implied_volatility
        """
        r = r or self.risk_free_rate
        flag = option_type.value.lower()

        # Calculate Greeks
        delta_val = delta(flag, S, K, t, r, sigma)
        gamma_val = gamma(flag, S, K, t, r, sigma)
        theta_val = theta(flag, S, K, t, r, sigma)
        vega_val = vega(flag, S, K, t, r, sigma)
        rho_val = rho(flag, S, K, t, r, sigma)

        return Greeks(
            delta=delta_val,
            gamma=gamma_val,
            theta=theta_val,
            vega=vega_val,
            rho=rho_val,
            implied_volatility=sigma,
        )

    def calculate_implied_volatility(
        self,
        price: float,
        S: float,
        K: float,
        t: float,
        r: float | None = None,
        option_type: OptionType = OptionType.CALL,
        max_iter: int = 100,
        tolerance: float = 1e-5,
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method.

        Args:
            price: Market price of the option
            S: Current stock/underlying price
            K: Strike price
            t: Time to expiration in years
            r: Risk-free rate (uses instance rate if None)
            option_type: Option type (CALL or PUT)
            max_iter: Maximum iterations
            tolerance: Convergence tolerance

        Returns:
            Implied volatility as decimal

        Raises:
            ValueError: If implied volatility cannot be calculated
        """
        r = r or self.risk_free_rate
        flag = option_type.value.lower()

        try:
            # Use py_vollib's implied volatility function
            iv = implied_volatility(price, S, K, t, r, flag)
            return iv
        except Exception as e:
            logger.warning(
                f"py_vollib IV calculation failed: {e}. Using fallback method.",
            )

            # Fallback to Newton-Raphson method
            def objective_function(sigma: float) -> float:
                """Objective function for Newton-Raphson: BS price - market price."""
                return black_scholes(flag, S, K, t, r, sigma) - price

            try:
                iv = newton(
                    objective_function,
                    x0=0.2,  # Initial guess
                    maxiter=max_iter,
                    tol=tolerance,
                )
                return float(iv)
            except Exception as e:
                logger.error(f"Failed to calculate implied volatility: {e}")
                raise ValueError(f"Could not calculate implied volatility: {e}")

    def calculate_black_scholes(
        self,
        S: float,
        K: float,
        t: float,
        sigma: float,
        r: float | None = None,
        option_type: OptionType = OptionType.CALL,
    ) -> float:
        """
        Calculate Black-Scholes option price.

        Args:
            S: Current stock/underlying price
            K: Strike price
            t: Time to expiration in years
            sigma: Volatility
            r: Risk-free rate (uses instance rate if None)
            option_type: Option type (CALL or PUT)

        Returns:
            Option price
        """
        r = r or self.risk_free_rate
        flag = option_type.value.lower()
        return black_scholes(flag, S, K, t, r, sigma)

    def calculate_time_to_expiration(self, expiry: datetime) -> float:
        """
        Calculate time to expiration in years.

        Args:
            expiry: Expiration datetime

        Returns:
            Time to expiration in years
        """
        now = datetime.now()
        days_to_expiry = (expiry - now).total_seconds() / (24 * 60 * 60)
        return days_to_expiry / 365.0

    def analyze_option_chain(
        self,
        option_chain: list[OptionContract],
        underlying_price: float,
    ) -> list[OptionContract]:
        """
        Analyze an option chain and calculate Greeks for each contract.

        Args:
            option_chain: List of OptionContract objects
            underlying_price: Current underlying price

        Returns:
            List of OptionContract objects with calculated Greeks
        """
        analyzed_chain = []

        for contract in option_chain:
            try:
                t = self.calculate_time_to_expiration(contract.expiry)

                # Calculate implied volatility if not provided
                if contract.implied_volatility is None:
                    contract.implied_volatility = self.calculate_implied_volatility(
                        price=contract.last_price,
                        S=underlying_price,
                        K=contract.strike_price,
                        t=t,
                        option_type=contract.option_type,
                    )

                # Calculate Greeks
                greeks = self.calculate_greeks(
                    S=underlying_price,
                    K=contract.strike_price,
                    t=t,
                    sigma=contract.implied_volatility,
                    option_type=contract.option_type,
                )

                # Update contract with Greeks
                contract.delta = greeks.delta
                contract.gamma = greeks.gamma
                contract.theta = greeks.theta
                contract.vega = greeks.vega
                contract.rho = greeks.rho

                analyzed_chain.append(contract)

            except Exception as e:
                logger.error(f"Failed to analyze option {contract.symbol}: {e}")
                # Keep the contract even if analysis fails
                analyzed_chain.append(contract)

        return analyzed_chain

    def calculate_volatility_smile(
        self,
        option_chain: list[OptionContract],
        underlying_price: float,
    ) -> list[tuple[float, float]]:
        """
        Calculate volatility smile/skew from option chain.

        Args:
            option_chain: List of OptionContract objects
            underlying_price: Current underlying price

        Returns:
            List of (strike, implied_volatility) tuples
        """
        smile = []

        for contract in option_chain:
            if contract.implied_volatility is not None:
                smile.append((contract.strike_price, contract.implied_volatility))

        # Sort by strike price
        smile.sort(key=lambda x: x[0])
        return smile

    def calculate_put_call_parity(
        self,
        call_price: float,
        put_price: float,
        S: float,
        K: float,
        t: float,
        r: float | None = None,
    ) -> float:
        """
        Calculate put-call parity relationship.

        Args:
            call_price: Call option price
            put_price: Put option price
            S: Current stock/underlying price
            K: Strike price
            t: Time to expiration in years
            r: Risk-free rate (uses instance rate if None)

        Returns:
            Put-call parity difference (should be close to zero)
        """
        r = r or self.risk_free_rate
        parity = call_price - put_price - S + K * np.exp(-r * t)
        return parity


# Export default instance
options = OptionsEngine()
