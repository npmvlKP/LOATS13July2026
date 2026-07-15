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
        flag = "c" if option_type == OptionType.CALL else "p"

        # Handle edge cases
        if t <= 0:
            t = 0.0001  # Small time to avoid division by zero

        try:
            # Calculate Greeks
            delta_val = delta(flag, S, K, t, r, sigma)
            gamma_val = gamma(flag, S, K, t, r, sigma)
            theta_val = theta(flag, S, K, t, r, sigma) or 0.0  # Handle None values
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
        except Exception:
            # Fallback values for edge cases
            if option_type == OptionType.CALL:
                return Greeks(
                    delta=1.0 if S > K else 0.0,
                    gamma=0.0,
                    theta=0.0,
                    vega=0.0,
                    rho=0.0,
                    implied_volatility=sigma,
                )
            else:
                return Greeks(
                    delta=-1.0 if S < K else 0.0,
                    gamma=0.0,
                    theta=0.0,
                    vega=0.0,
                    rho=0.0,
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
        flag = "c" if option_type == OptionType.CALL else "p"

        # Handle edge cases
        if t <= 0:
            t = 0.0001  # Small time to avoid division by zero

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
        flag = "c" if option_type == OptionType.CALL else "p"

        # Handle edge cases
        if t <= 0:
            t = 0.0001  # Small time to avoid division by zero

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


def calculate_greeks(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_type: OptionType,
) -> Greeks:
    """
    Calculate Greeks for an option.

    Args:
        S: Underlying asset price
        K: Strike price
        t: Time to expiration (in years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Option type (CALL or PUT)

    Returns:
        Greeks object
    """
    flag = "c" if option_type == OptionType.CALL else "p"

    # Handle edge cases
    if t <= 0:
        t = 0.0001  # Small time to avoid division by zero

    try:
        # Calculate Greeks using py_vollib
        delta_val = delta(flag, S, K, t, r, sigma)
        gamma_val = gamma(flag, S, K, t, r, sigma)
        vega_val = vega(flag, S, K, t, r, sigma)
        theta_val = theta(flag, S, K, t, r, sigma) or 0.0  # Handle None values
        rho_val = rho(flag, S, K, t, r, sigma)

        return Greeks(
            delta=delta_val,
            gamma=gamma_val,
            vega=vega_val,
            theta=theta_val,
            rho=rho_val,
            implied_volatility=sigma,
        )
    except Exception:
        # Fallback values for edge cases
        if option_type == OptionType.CALL:
            return Greeks(
                delta=1.0 if S > K else 0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                rho=0.0,
                implied_volatility=sigma,
            )
        else:
            return Greeks(
                delta=-1.0 if S < K else 0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                rho=0.0,
                implied_volatility=sigma,
            )


def calculate_implied_volatility(
    price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    option_type: OptionType,
) -> float:
    """
    Calculate implied volatility using Newton-Raphson method.

    Args:
        price: Option market price
        S: Underlying asset price
        K: Strike price
        t: Time to expiration (in years)
        r: Risk-free rate
        option_type: Option type (CALL or PUT)

    Returns:
        Implied volatility
    """
    flag = "c" if option_type == OptionType.CALL else "p"

    # Handle edge cases
    if t <= 0:
        t = 0.0001  # Small time to avoid division by zero

    try:
        # Use py_vollib's implied volatility function
        iv = implied_volatility(price, S, K, t, r, flag)
        return iv
    except Exception as e:
        logger.warning(f"Failed to calculate implied volatility: {e}")
        return 0.2  # Default reasonable volatility value


def calculate_var(
    returns: list[float],
    confidence_level: float = 0.95,
) -> float:
    """
    Calculate Value at Risk (VaR) using historical method.

    Args:
        returns: List of historical returns
        confidence_level: Confidence level (e.g., 0.95 for 95%)

    Returns:
        VaR value

    Raises:
        ValueError: If returns list is empty
    """
    if not returns:
        raise ValueError("Returns list cannot be empty")

    # Sort returns and find the appropriate percentile
    sorted_returns = sorted(returns)
    index = int((1 - confidence_level) * len(sorted_returns))
    return sorted_returns[index]


def calculate_historical_var(
    prices: list[float],
    confidence_level: float = 0.95,
) -> float:
    """
    Calculate historical Value at Risk (VaR).

    Args:
        prices: List of historical prices
        confidence_level: Confidence level (e.g., 0.95 for 95%)

    Returns:
        VaR value
    """
    if len(prices) < 2:
        return 0.0

    # Calculate returns
    returns = [
        (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
    ]

    return calculate_var(returns, confidence_level)


class OptionsAnalysis:
    """Options analysis class for portfolio-level calculations."""

    def __init__(self):
        """Initialize OptionsAnalysis."""
        self.engine = OptionsEngine()

    def get_atm_strike(self, option_chain: dict, underlying_price: float) -> float:
        """
        Get the at-the-money strike price.

        Args:
            option_chain: Option chain data
            underlying_price: Current underlying price

        Returns:
            ATM strike price
        """
        if not option_chain.get("options"):
            return underlying_price

        # Get all unique strike prices
        strikes = sorted({opt["strike_price"] for opt in option_chain["options"]})

        # Find the strike closest to the underlying price
        atm_strike = min(strikes, key=lambda x: abs(x - underlying_price))
        return atm_strike

    def analyze_option_chain(self, option_chain: dict, underlying_price: float) -> dict:
        """
        Analyze an option chain and return structured analysis.

        Args:
            option_chain: Option chain data
            underlying_price: Current underlying price

        Returns:
            Structured analysis of the option chain
        """
        # Get ATM strike
        atm_strike = self.get_atm_strike(option_chain, underlying_price)

        # Separate calls and puts
        call_options = [
            opt for opt in option_chain["options"] if opt["option_type"] == "CE"
        ]
        put_options = [
            opt for opt in option_chain["options"] if opt["option_type"] == "PE"
        ]

        # Sort by strike price
        call_options.sort(key=lambda x: x["strike_price"])
        put_options.sort(key=lambda x: x["strike_price"])

        # Calculate OI and volatility analysis
        oi_analysis = self._calculate_open_interest_analysis(option_chain)
        volatility_analysis = self._calculate_volatility_analysis(option_chain)

        return {
            "atm_strike": atm_strike,
            "call_options": call_options,
            "put_options": put_options,
            "expiry_dates": option_chain["expiry_dates"],
            "oi_analysis": oi_analysis,
            "volatility_analysis": volatility_analysis,
        }

    def _calculate_open_interest_analysis(self, option_chain: dict) -> dict:
        """
        Calculate open interest analysis.

        Args:
            option_chain: Option chain data

        Returns:
            Open interest analysis
        """
        total_call_oi = 0
        total_put_oi = 0
        max_call_oi = 0
        max_put_oi = 0
        max_call_strike = 0.0
        max_put_strike = 0.0

        for opt in option_chain["options"]:
            if opt["option_type"] == "CE":
                total_call_oi += opt["open_interest"]
                if opt["open_interest"] > max_call_oi:
                    max_call_oi = opt["open_interest"]
                    max_call_strike = opt["strike_price"]
            elif opt["option_type"] == "PE":
                total_put_oi += opt["open_interest"]
                if opt["open_interest"] > max_put_oi:
                    max_put_oi = opt["open_interest"]
                    max_put_strike = opt["strike_price"]

        put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

        return {
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "put_call_ratio": put_call_ratio,
            "max_call_oi": max_call_oi,
            "max_put_oi": max_put_oi,
            "max_call_strike": max_call_strike,
            "max_put_strike": max_put_strike,
        }

    def _calculate_volatility_analysis(self, option_chain: dict) -> dict:
        """
        Calculate volatility analysis.

        Args:
            option_chain: Option chain data

        Returns:
            Volatility analysis
        """
        call_ivs = []
        put_ivs = []

        for opt in option_chain["options"]:
            if opt["option_type"] == "CE" and opt["implied_volatility"] is not None:
                call_ivs.append(opt["implied_volatility"])
            elif opt["option_type"] == "PE" and opt["implied_volatility"] is not None:
                put_ivs.append(opt["implied_volatility"])

        avg_call_iv = sum(call_ivs) / len(call_ivs) if call_ivs else 0.0
        avg_put_iv = sum(put_ivs) / len(put_ivs) if put_ivs else 0.0
        iv_skew = avg_put_iv - avg_call_iv

        return {
            "avg_call_iv": avg_call_iv,
            "avg_put_iv": avg_put_iv,
            "iv_skew": iv_skew,
            "max_call_iv": max(call_ivs) if call_ivs else 0.0,
            "max_put_iv": max(put_ivs) if put_ivs else 0.0,
            "min_call_iv": min(call_ivs) if call_ivs else 0.0,
            "min_put_iv": min(put_ivs) if put_ivs else 0.0,
        }

    def _calculate_option_metrics(
        self, option_data: dict, underlying_price: float
    ) -> dict:
        """
        Calculate option metrics.

        Args:
            option_data: Option data
            underlying_price: Current underlying price

        Returns:
            Option metrics
        """
        strike_price = option_data["strike_price"]
        option_type = option_data["option_type"]
        last_price = option_data["last_price"]

        # Calculate intrinsic and extrinsic value
        if option_type == "CE":
            intrinsic_value = max(underlying_price - strike_price, 0)
        else:  # PE
            intrinsic_value = max(strike_price - underlying_price, 0)

        extrinsic_value = last_price - intrinsic_value
        moneyness = (underlying_price - strike_price) / strike_price
        leverage = underlying_price / last_price if last_price > 0 else 0.0

        return {
            "intrinsic_value": intrinsic_value,
            "extrinsic_value": extrinsic_value,
            "moneyness": moneyness,
            "leverage": leverage,
            "oi_change": 0,  # Placeholder - would need previous OI data
            "volume_change": 0,  # Placeholder - would need previous volume data
        }

    def calculate_portfolio_greeks(
        self,
        contracts: list[OptionContract],
    ) -> Greeks:
        """
        Calculate portfolio-level Greeks.

        Args:
            contracts: List of option contracts

        Returns:
            Portfolio Greeks
        """
        portfolio_delta = 0.0
        portfolio_gamma = 0.0
        portfolio_vega = 0.0
        portfolio_theta = 0.0
        portfolio_rho = 0.0

        for contract in contracts:
            # Calculate Greeks for each contract
            greeks = calculate_greeks(
                S=contract.underlying_price,
                K=contract.strike_price,
                t=contract.time_to_expiration,
                r=contract.risk_free_rate,
                sigma=contract.volatility,
                option_type=contract.option_type,
            )

            # Adjust for contract size
            portfolio_delta += greeks.delta * contract.quantity
            portfolio_gamma += greeks.gamma * contract.quantity
            portfolio_vega += greeks.vega * contract.quantity
            portfolio_theta += greeks.theta * contract.quantity
            portfolio_rho += greeks.rho * contract.quantity

        return Greeks(
            delta=portfolio_delta,
            gamma=portfolio_gamma,
            vega=portfolio_vega,
            theta=portfolio_theta,
            rho=portfolio_rho,
            implied_volatility=0.0,  # Portfolio IV not meaningful
        )


# Export default instances
options = OptionsEngine()
analysis = OptionsAnalysis()

# Export functions
__all__ = [
    "OptionsEngine",
    "OptionsAnalysis",
    "calculate_greeks",
    "calculate_implied_volatility",
    "calculate_var",
    "calculate_historical_var",
    "options",
    "analysis",
]
