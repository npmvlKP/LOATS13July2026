"""
Options module LOATS13July2026.
Implements calculation Greeks, Black-Scholes model, volatility analysis.
"""

from datetime import UTC, datetime
from typing import Any

import numpy as np
from scipy.optimize import brentq, newton
from scipy.stats import norm
from vollib.black_scholes import black_scholes
from vollib.black_scholes.greeks.analytical import delta, gamma, rho, theta, vega
from vollib.ref_python.black_scholes.implied_volatility import implied_volatility

from .loats_logging import get_logger
from .models import Greeks, OptionContract, OptionType, Trade, VaRResult

logger = get_logger(__name__)


class ExpiredContractError(ValueError):
    """Raised when calculating Greeks for an expired option contract.

    M6: Replaces silent clamping of negative time-to-expiry values.
    Expired contracts must be handled explicitly, not producing misleading Greeks.
    """

    def __init__(
        self,
        message: str,
        symbol: str | None = None,
        expiry: datetime | None = None,
        time_to_expiry: float | None = None,
    ) -> None:
        """Initialize ExpiredContractError.

        Args:
            message: Human-readable error message.
            symbol: Option contract symbol (optional).
            expiry: Contract expiry datetime (optional).
            time_to_expiry: Calculated time to expiry in years (optional).
        """
        self.symbol = symbol
        self.expiry = expiry
        self.time_to_expiry = time_to_expiry
        super().__init__(message)


class OptionsEngine:
    """Options pricing analysis engine."""

    def __init__(self) -> None:
        """Initialize OptionsEngine."""
        self.risk_free_rate = 0.05  # Default risk-free rate (5%)

    def set_risk_free_rate(self, rate: float) -> None:
        """
        Set risk-free rate.

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
        allow_expired: bool = False,
    ) -> Greeks:
        """
        Calculate Greeks for an option using Black-Scholes model.

        Args:
            S: Spot price.
            K: Strike price.
            t: Time to expiration in years.
            r: Risk-free rate (optional, defaults to self.risk_free_rate).
            sigma: Volatility.
            option_type: OptionType.CALL or OptionType.PUT.
            allow_expired: If False (default), raises ExpiredContractError when t <= 0.

        Raises:
            ExpiredContractError: If t <= 0 and allow_expired is False.
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"

        # M6: Validate time to expiry - raise error for expired contracts
        if t <= 0:
            if allow_expired:
                # Return Greeks at expiry (intrinsic value only)
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
            raise ExpiredContractError(
                f"Cannot calculate Greeks for expired contract (t={t:.6f} years)",
                time_to_expiry=t,
            )

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
        except (ValueError, TypeError, ZeroDivisionError) as e:
            # Fallback for specific numerical errors
            logger.warning(f"Numerical error in Greeks calculation: {e}")
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
        except Exception as e:
            # Catch any other unexpected exceptions and return fallback values
            logger.error(f"Unexpected error in Greeks calculation: {e}")
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

        Raises:
            ExpiredContractError: If t <= 0.
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"

        # M6: Validate time to expiry - raise error for expired contracts
        if t <= 0:
            raise ExpiredContractError(
                f"Cannot calculate implied volatility for "
                f"expired contract (t={t:.6f} years)",
                time_to_expiry=t,
            )

        # M6: Only clamp very small positive values to avoid numerical issues
        t = max(t, 0.0001)

        # Check price within arbitrage bounds to avoid solver failure (H9)
        if flag == "c":
            if price <= max(0, S - K * np.exp(-r * t)) or price >= S:
                logger.debug(f"Call price {price} out of bounds for S={S}, K={K}")
                return 0.2
        else:
            if price <= max(0, K * np.exp(-r * t) - S) or price >= K * np.exp(-r * t):
                logger.debug(f"Put price {price} out of bounds for S={S}, K={K}")
                return 0.2

        try:
            return float(implied_volatility(price, S, K, t, r, flag))
        except Exception:
            logger.debug("vollib calculation failed. Using fallback method.")

            def objective_function(sigma: float) -> float:
                try:
                    return float(black_scholes(flag, S, K, t, r, sigma) - price)
                except Exception:
                    return 1e6

            # Try brentq with wider bounds
            try:
                # Check for bracket
                if objective_function(1e-4) * objective_function(10.0) < 0:
                    return float(brentq(objective_function, 1e-4, 10.0, xtol=tolerance))
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
                    return 0.2  # Return default volatility on total failure

        return 0.2  # Default fallback

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

        Raises:
            ExpiredContractError: If t <= 0.
        """
        r = r if r is not None else self.risk_free_rate
        flag = "c" if option_type == OptionType.CALL else "p"

        # M6: Validate time to expiry - raise error for expired contracts
        if t <= 0:
            raise ExpiredContractError(
                f"Cannot calculate Black-Scholes for "
                f"expired contract (t={t:.6f} years)",
                time_to_expiry=t,
            )

        # M6: Only clamp very small positive values to avoid numerical issues
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
        Analyze option chain and calculate Greeks for each contract.
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
            except (ValueError, TypeError, ZeroDivisionError) as e:
                logger.warning(
                    f"Numerical error analyzing option {contract.symbol}: {e}"
                )
                analyzed_chain.append(contract)
            except Exception as e:
                logger.error(
                    f"Unexpected error analyzing option {contract.symbol}: {e}"
                )
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

    Raises:
        ExpiredContractError: If t <= 0.
    """
    flag = "c" if option_type == OptionType.CALL else "p"

    # M6: Validate time to expiry - raise error for expired contracts
    if t <= 0:
        raise ExpiredContractError(
            f"Cannot calculate Greeks for expired contract (t={t:.6f} years)",
            time_to_expiry=t,
        )

    # Only clamp very small positive values to avoid numerical issues
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
    except (ValueError, TypeError, ZeroDivisionError) as e:
        logger.warning(f"Numerical error in standalone Greeks calculation: {e}")
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
    except Exception as e:
        logger.error(f"Unexpected error in standalone Greeks calculation: {e}")
        raise


def calculate_implied_volatility(
    price: float, S: float, K: float, t: float, r: float, option_type: OptionType
) -> float:
    """
    Standalone function to calculate implied volatility using robust methods.

    Raises:
        ExpiredContractError: If t <= 0.
    """
    flag = "c" if option_type == OptionType.CALL else "p"

    # M6: Validate time to expiry - raise error for expired contracts
    if t <= 0:
        raise ExpiredContractError(
            f"Cannot calculate implied volatility for "
            f"expired contract (t={t:.6f} years)",
            time_to_expiry=t,
        )

    # Only clamp very small positive values to avoid numerical issues
    t = max(t, 0.0001)

    try:
        return float(implied_volatility(price, S, K, t, r, flag))
    except (ValueError, TypeError, ZeroDivisionError) as e:
        logger.warning(
            f"Numerical error in standalone implied volatility calculation: {e}"
        )
        # Fallback to a reasonable value
        return 0.2
    except Exception as e:
        logger.error(
            f"Unexpected error in standalone implied volatility calculation: {e}"
        )
        raise


def calculate_var(returns: list[float], confidence_level: float = 0.95) -> float:
    """
    Calculate Value at Risk (VaR) using historical method.
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
        """Analyze option chain and return structured analysis."""
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
        r: float | None = None,  # Backward compatibility (H1)
    ) -> Greeks:
        portfolio_delta = 0.0
        portfolio_gamma = 0.0
        portfolio_vega = 0.0
        portfolio_theta = 0.0
        portfolio_rho = 0.0

        # Support both 'r' and 'risk_free_rate' parameters (H1)
        if r is not None:
            r_val = r
        elif risk_free_rate is not None:
            r_val = risk_free_rate
        else:
            r_val = self.engine.risk_free_rate

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
                r=r_val,
                sigma=contract_volatility,
                option_type=contract.option_type,
            )

            # Use contract quantity for position sizing (defaults to 1)
            contract_quantity = contract.quantity
            portfolio_delta += greeks.delta * contract_quantity
            portfolio_gamma += greeks.gamma * contract_quantity
            portfolio_vega += greeks.vega * contract_quantity
            portfolio_theta += greeks.theta * contract_quantity
            portfolio_rho += greeks.rho * contract_quantity

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


def calculate_parametric_var(
    returns: list[float],
    confidence_level: float = 0.95,
    mean: float | None = None,
    std_dev: float | None = None,
) -> float:
    """
    Calculate parametric VaR using normal distribution.

    Assumes returns are normally distributed.
    """
    if not returns:
        raise ValueError("Returns list cannot be empty")

    # Calculate mean and std dev if not provided
    if mean is None:
        mean = float(np.mean(returns))
    if std_dev is None:
        std_dev = float(np.std(returns))

    # Calculate VaR using inverse normal distribution
    z_score = norm.ppf(1 - confidence_level)
    parametric_var = mean + z_score * std_dev

    return float(parametric_var)


def calculate_monte_carlo_var(
    prices: list[float],
    confidence_level: float = 0.95,
    simulations: int = 1000,
    days: int = 1,
) -> float:
    """
    Calculate VaR using Monte Carlo simulation.

    Generates random price paths based on historical volatility.
    """
    if len(prices) < 2:
        return 0.0

    # Calculate historical returns and volatility
    returns = [
        (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
    ]
    mean_return = np.mean(returns)
    std_return = np.std(returns)

    # Generate random returns using normal distribution
    np.random.seed(42)  # For reproducibility
    random_returns = np.random.normal(mean_return, std_return, simulations)

    # Calculate simulated price changes
    current_price = prices[-1]
    simulated_prices = current_price * (1 + random_returns)

    # Calculate simulated returns
    simulated_returns = [(p - current_price) / current_price for p in simulated_prices]

    # Calculate VaR
    sorted_returns = sorted(simulated_returns)
    index = int((1 - confidence_level) * len(sorted_returns))
    monte_carlo_var = sorted_returns[index]

    return float(monte_carlo_var)


def calculate_portfolio_var(
    positions: list[Trade],
    confidence_level: float = 0.95,
    correlation_matrix: np.ndarray | None = None,
) -> VaRResult:
    """
    Calculate portfolio VaR considering position correlations.

    Returns comprehensive VaRResult with multiple calculation methods.
    """
    if not positions:
        return VaRResult(
            confidence_level=confidence_level,
            time_horizon=1,
            var_value=0.0,
            var_percent=0.0,
            historical_var=0.0,
            method="portfolio",
            timestamp=datetime.now(UTC),
        )

    # Calculate individual position VaRs
    position_vars = []
    total_portfolio_value = 0.0

    for position in positions:
        if position.entry_price is not None and position.exit_price is not None:
            # Simple daily return calculation
            daily_return = (
                position.exit_price - position.entry_price
            ) / position.entry_price
            position_vars.append(daily_return)
            total_portfolio_value += position.exit_price * position.quantity

    if not position_vars or total_portfolio_value <= 0:
        return VaRResult(
            confidence_level=confidence_level,
            time_horizon=1,
            var_value=0.0,
            var_percent=0.0,
            historical_var=0.0,
            method="portfolio",
            timestamp=datetime.now(UTC),
        )

    # Calculate historical VaR
    historical_var = calculate_var(position_vars, confidence_level)

    # Calculate parametric VaR
    mean_return = float(np.mean(position_vars))
    std_return = float(np.std(position_vars))
    parametric_var = calculate_parametric_var(
        position_vars, confidence_level, mean_return, std_return
    )

    # Calculate Monte Carlo VaR
    # For portfolio, we use the average return and std dev
    exit_prices = [p.exit_price for p in positions if p.exit_price is not None]
    if len(exit_prices) >= 2:
        calculate_monte_carlo_var(exit_prices, confidence_level)

    # Use parametric VaR as primary (most reliable for normal markets)
    # Note: Monte Carlo VaR is calculated but not used as parametric VaR is preferred
    primary_var = parametric_var
    var_value = total_portfolio_value * abs(primary_var)
    var_percent = abs(primary_var) * 100

    return VaRResult(
        confidence_level=confidence_level,
        time_horizon=1,
        var_value=float(var_value),
        var_percent=float(var_percent),
        historical_var=float(historical_var),
        method="portfolio_comprehensive",
        timestamp=datetime.now(UTC),
    )


def calculate_option_portfolio_var(
    option_positions: list[OptionContract],
    underlying_price: float,
    confidence_level: float = 0.95,
) -> VaRResult:
    """
    Calculate VaR for options portfolio using delta-gamma approximation.

    Considers non-linear payoff characteristics of options.
    """
    if not option_positions:
        return VaRResult(
            confidence_level=confidence_level,
            time_horizon=1,
            var_value=0.0,
            var_percent=0.0,
            historical_var=0.0,
            method="options_delta_gamma",
            timestamp=datetime.now(UTC),
        )

    # Calculate portfolio Greeks
    portfolio_delta = 0.0
    portfolio_gamma = 0.0
    portfolio_value = 0.0

    for contract in option_positions:
        if contract.delta is not None:
            portfolio_delta += contract.delta * contract.quantity
        if contract.gamma is not None:
            portfolio_gamma += contract.gamma * contract.quantity
        portfolio_value += contract.last_price * contract.quantity

    if portfolio_value <= 0:
        return VaRResult(
            confidence_level=confidence_level,
            time_horizon=1,
            var_value=0.0,
            var_percent=0.0,
            historical_var=0.0,
            method="options_delta_gamma",
            timestamp=datetime.now(UTC),
        )

    # Estimate underlying volatility (simplified)
    # In production, this would use actual volatility estimates
    underlying_volatility = 0.015  # 1.5% daily volatility (approx 24% annual)

    # Calculate VaR using delta-gamma approximation
    z_score = norm.ppf(1 - confidence_level)

    # Delta component (linear approximation)
    delta_var = portfolio_delta * underlying_price * underlying_volatility * z_score

    # Gamma component (convexity adjustment)
    gamma_var = (
        0.5
        * portfolio_gamma
        * (underlying_price * underlying_volatility * z_score) ** 2
    )

    # Total VaR
    total_var = abs(delta_var + gamma_var)
    var_percent = (total_var / portfolio_value) * 100

    return VaRResult(
        confidence_level=confidence_level,
        time_horizon=1,
        var_value=float(total_var),
        var_percent=float(var_percent),
        historical_var=float(delta_var),  # Store delta component as historical
        method="options_delta_gamma",
        timestamp=datetime.now(UTC),
    )


def calculate_comprehensive_var_analysis(
    trades: list[Trade],
    option_contracts: list[OptionContract],
    historical_prices: list[float],
    confidence_levels: list[float] | None = None,
) -> dict[str, Any]:
    """
    Perform comprehensive VaR analysis across multiple methods and confidence levels.

    Returns detailed analysis with multiple VaR calculations.
    """
    # Set default confidence levels if not provided
    if confidence_levels is None:
        confidence_levels = [0.95, 0.99]

    analysis_results: dict[str, Any] = {
        "timestamp": datetime.now(UTC),
        "confidence_levels": confidence_levels,
        "portfolio_analysis": {},
        "options_analysis": {},
        "historical_analysis": {},
    }

    # Portfolio VaR analysis
    for confidence_level in confidence_levels:
        portfolio_var = calculate_portfolio_var(trades, confidence_level)
        analysis_results["portfolio_analysis"][f"var_{int(confidence_level * 100)}"] = {
            "var_value": portfolio_var.var_value,
            "var_percent": portfolio_var.var_percent,
            "historical_var": portfolio_var.historical_var,
            "method": portfolio_var.method,
        }

    # Options VaR analysis
    if option_contracts:
        underlying_price = historical_prices[-1] if historical_prices else 18000.0
        for confidence_level in confidence_levels:
            options_var = calculate_option_portfolio_var(
                option_contracts, underlying_price, confidence_level
            )
            analysis_results["options_analysis"][
                f"var_{int(confidence_level * 100)}"
            ] = {
                "var_value": options_var.var_value,
                "var_percent": options_var.var_percent,
                "historical_var": options_var.historical_var,
                "method": options_var.method,
            }

    # Historical VaR analysis
    for confidence_level in confidence_levels:
        historical_var = calculate_historical_var(historical_prices, confidence_level)
        monte_carlo_var = calculate_monte_carlo_var(historical_prices, confidence_level)
        parametric_var = calculate_parametric_var(
            [
                (historical_prices[i] - historical_prices[i - 1])
                / historical_prices[i - 1]
                for i in range(1, len(historical_prices))
            ],
            confidence_level,
        )

        analysis_results["historical_analysis"][
            f"var_{int(confidence_level * 100)}"
        ] = {
            "historical_var": historical_var,
            "monte_carlo_var": monte_carlo_var,
            "parametric_var": parametric_var,
        }

    return analysis_results


__all__ = [
    "ExpiredContractError",
    "OptionsAnalysis",
    "OptionsEngine",
    "analysis",
    "calculate_comprehensive_var_analysis",
    "calculate_greeks",
    "calculate_historical_var",
    "calculate_implied_volatility",
    "calculate_monte_carlo_var",
    "calculate_option_portfolio_var",
    "calculate_parametric_var",
    "calculate_portfolio_var",
    "calculate_var",
    "options",
]
