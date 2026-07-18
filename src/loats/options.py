"""
Options module for LOATS13July2026.
Implements calculation of Greeks, Black-Scholes model, and volatility analysis.
"""

from datetime import UTC, datetime
from typing import Any

import numpy as np
from scipy.optimize import brentq, newton
from vollib.black_scholes import black_scholes
from vollib.black_scholes.greeks.analytical import delta, gamma, rho, theta, vega
from vollib.ref_python.black_scholes.implied_volatility import implied_volatility

from .logging import get_logger
from .models import Greeks, OptionContract, OptionType

logger = get_logger(__name__)


class OptionsEngine:
    """Options pricing and analysis engine."""

    def __init__(self) -> None:
        """Initialize OptionsEngine."""
        self.risk_free_rate = 0.05  # Default risk-free rate (5%)

    def set_risk_free_rate(self, rate: float) -> None:
        """
        Set the risk-free rate.
        Args:
            rate: Risk-free rate as a decimal (e.g., 0.05 for 5%)
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
        Calculate Greeks for an option using the Black-Scholes model.
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"

        # Handle edge cases
        t = max(t, 0.0001)  # Small time to avoid division by zero

        try:
            delta_val = delta(flag, S, K, t, r, sigma)
            gamma_val = gamma(flag, S, K, t, r, sigma)
            theta_val = theta(flag, S, K, t, r, sigma)
            if theta_val is None:
                theta_val = 0.0
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
        Calculate implied volatility using robust methods.
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"
        t = max(t, 0.0001)

        try:
            return float(implied_volatility(price, S, K, t, r, flag))
        except Exception:
            logger.warning("vollib calculation failed. Using fallback method.")

        def objective_function(sigma: float) -> float:
            return float(black_scholes(flag, S, K, t, r, sigma) - price)

        # Try brentq
        try:
            return float(brentq(objective_function, 1e-4, 5.0, xtol=tolerance))
        except Exception:
            # Fallback to Newton
            try:

                def fprime(sigma: float) -> float:
                    return float(vega(flag, S, K, t, r, sigma))

                return float(
                    newton(
                        objective_function,
                        x0=0.2,
                        fprime=fprime,
                        maxiter=max_iter,
                        tol=tolerance,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to calculate implied volatility: {e}")
                raise ValueError(f"Could not calculate implied volatility: {e}") from e

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
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"
        t = max(t, 0.0001)

        return float(black_scholes(flag, S, K, t, r, sigma))

    def calculate_time_to_expiration(self, expiry: datetime) -> float:
        """
        Calculate time to expiration in years.
        """
        now = datetime.now(UTC)
        days_to_expiry = (expiry - now).total_seconds() / (24 * 60 * 60)
        return days_to_expiry / 365.0

    def analyze_option_chain(
        self, option_chain: list[OptionContract], underlying_price: float
    ) -> list[OptionContract]:
        """
        Analyze an option chain and calculate Greeks for each contract.
        """
        analyzed_chain = []
        for contract in option_chain:
            try:
                t = self.calculate_time_to_expiration(contract.expiry)
                if contract.implied_volatility is None:
                    contract.implied_volatility = self.calculate_implied_volatility(
                        price=contract.last_price,
                        S=underlying_price,
                        K=contract.strike_price,
                        t=t,
                        option_type=contract.option_type,
                    )

                greeks = self.calculate_greeks(
                    S=underlying_price,
                    K=contract.strike_price,
                    t=t,
                    sigma=contract.implied_volatility,
                    option_type=contract.option_type,
                )

                contract.delta = greeks.delta
                contract.gamma = greeks.gamma
                contract.theta = greeks.theta
                contract.vega = greeks.vega
                contract.rho = greeks.rho

                analyzed_chain.append(contract)
            except Exception as e:
                logger.error(f"Failed to analyze option {contract.symbol}: {e}")
                analyzed_chain.append(contract)

        return analyzed_chain

    def calculate_volatility_smile(
        self, option_chain: list[OptionContract], underlying_price: float
    ) -> list[tuple[float, float]]:
        """
        Calculate volatility smile/skew for an option chain.
        """
        smile = []
        for contract in option_chain:
            if contract.implied_volatility is not None:
                smile.append((contract.strike_price, contract.implied_volatility))

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
        """
        r = r if r is not None else self.risk_free_rate
        parity = call_price - put_price + K * np.exp(-r * t)
        return float(parity)


def calculate_greeks(
    S: float, K: float, t: float, r: float, sigma: float, option_type: OptionType
) -> Greeks:
    """
    Standalone function to calculate Greeks for an option.
    """
    flag = "c" if option_type == OptionType.CALL else "p"
    t = max(t, 0.0001)

    try:
        delta_val = delta(flag, S, K, t, r, sigma)
        gamma_val = gamma(flag, S, K, t, r, sigma)
        vega_val = vega(flag, S, K, t, r, sigma)
        theta_val = theta(flag, S, K, t, r, sigma)
        if theta_val is None:
            theta_val = 0.0
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
        if option_type == OptionType.CALL:
            return Greeks(
                delta=1.0 if S > K else 0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                rho=0.0,
                implied_volatility=sigma,
            )
        return Greeks(
            delta=-1.0 if S < K else 0.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
            implied_volatility=sigma,
        )


def calculate_implied_volatility(
    price: float, S: float, K: float, t: float, r: float, option_type: OptionType
) -> float:
    """
    Standalone function to calculate implied volatility using robust methods.
    """
    flag = "c" if option_type == OptionType.CALL else "p"
    t = max(t, 0.0001)

    try:
        return float(implied_volatility(price, S, K, t, r, flag))
    except Exception:
        # Fallback to a reasonable value
        return 0.2


def calculate_var(returns: list[float], confidence_level: float = 0.95) -> float:
    """
    Calculate Value at Risk (VaR) using the historical method.
    """
    if not returns:
        raise ValueError("Returns list cannot be empty")

    sorted_returns = sorted(returns)
    index = int((1 - confidence_level) * len(sorted_returns))
    return sorted_returns[index]


def calculate_historical_var(
    prices: list[float], confidence_level: float = 0.95
) -> float:
    """
    Calculate historical Value at Risk (VaR).
    """
    if len(prices) < 2:
        return 0.0

    returns = []
    for i in range(1, len(prices)):
        returns.append((prices[i] - prices[i - 1]) / prices[i - 1])

    return calculate_var(returns, confidence_level)


class OptionsAnalysis:
    """Options analysis class for portfolio-level calculations."""

    def __init__(self) -> None:
        self.engine = OptionsEngine()

    def get_atm_strike(
        self, option_chain: dict[str, Any], underlying_price: float
    ) -> float:
        """Get at-the-money strike price."""
        if not option_chain.get("options"):
            return underlying_price

        strikes = sorted({opt["strike_price"] for opt in option_chain["options"]})
        atm_strike = min(strikes, key=lambda x: abs(x - underlying_price))
        return float(atm_strike)

    def analyze_option_chain(
        self, option_chain: dict[str, Any], underlying_price: float
    ) -> dict[str, Any]:
        """Analyze an option chain and return a structured analysis."""
        atm_strike = self.get_atm_strike(option_chain, underlying_price)

        call_options = [
            opt for opt in option_chain["options"] if opt["option_type"] == "CE"
        ]
        put_options = [
            opt for opt in option_chain["options"] if opt["option_type"] == "PE"
        ]

        call_options.sort(key=lambda x: x["strike_price"])
        put_options.sort(key=lambda x: x["strike_price"])

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

    def _calculate_open_interest_analysis(
        self, option_chain: dict[str, Any]
    ) -> dict[str, Any]:
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

    def _calculate_volatility_analysis(
        self, option_chain: dict[str, Any]
    ) -> dict[str, Any]:
        call_ivs = [
            opt["implied_volatility"]
            for opt in option_chain["options"]
            if opt["option_type"] == "CE" and opt["implied_volatility"] is not None
        ]

        put_ivs = [
            opt["implied_volatility"]
            for opt in option_chain["options"]
            if opt["option_type"] == "PE" and opt["implied_volatility"] is not None
        ]

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
        self, option_data: dict[str, Any], underlying_price: float
    ) -> dict[str, Any]:
        strike_price = option_data["strike_price"]
        option_type = option_data["option_type"]
        last_price = option_data["last_price"]

        if option_type == "CE":
            intrinsic_value = max(underlying_price - strike_price, 0)
        else:
            intrinsic_value = max(strike_price - underlying_price, 0)

        extrinsic_value = last_price - intrinsic_value
        moneyness = (underlying_price - strike_price) / strike_price
        leverage = underlying_price / last_price if last_price > 0 else 0.0

        return {
            "intrinsic_value": intrinsic_value,
            "extrinsic_value": extrinsic_value,
            "moneyness": moneyness,
            "leverage": leverage,
            "oi_change": 0,  # Placeholder
            "volume_change": 0,  # Placeholder
        }

    def calculate_portfolio_greeks(
        self,
        contracts: list[OptionContract],
        underlying_price: float,
        risk_free_rate: float | None = None,
        volatility: float = 0.2,
    ) -> Greeks:
        portfolio_delta = 0.0
        portfolio_gamma = 0.0
        portfolio_vega = 0.0
        portfolio_theta = 0.0
        portfolio_rho = 0.0

        r = risk_free_rate if risk_free_rate is not None else self.engine.risk_free_rate

        for contract in contracts:
            t = self.engine.calculate_time_to_expiration(contract.expiry)
            contract_volatility = (
                contract.implied_volatility
                if contract.implied_volatility is not None
                else volatility
            )

            greeks = self.engine.calculate_greeks(
                S=underlying_price,
                K=contract.strike_price,
                t=t,
                r=r,
                sigma=contract_volatility,
                option_type=contract.option_type,
            )

            quantity = 1  # Assuming quantity 1 for now
            portfolio_delta += greeks.delta * quantity
            portfolio_gamma += greeks.gamma * quantity
            portfolio_vega += greeks.vega * quantity
            portfolio_theta += greeks.theta * quantity
            portfolio_rho += greeks.rho * quantity

        return Greeks(
            delta=portfolio_delta,
            gamma=portfolio_gamma,
            vega=portfolio_vega,
            theta=portfolio_theta,
            rho=portfolio_rho,
            implied_volatility=0.0,
        )


options = OptionsEngine()
analysis = OptionsAnalysis()

__all__ = [
    "OptionsAnalysis",
    "OptionsEngine",
    "analysis",
    "calculate_greeks",
    "calculate_historical_var",
    "calculate_implied_volatility",
    "calculate_var",
    "options",
]
