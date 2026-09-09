"""
Hand-rolled Black-Scholes mathematics for LOATS13July2026.

Replaces the deprecated `vollib` dependency (TODO-27a / VOLLIB_MIGRATION_PLAN Phase 2).

Provides a zero-external-dependency (except numpy + scipy which are already
required) implementation that is byte-for-byte compatible with vollib's
analytical formulas and scaling conventions:

- theta is returned per-day (annual theta / 365)
- vega is per 1% IV change (annual vega * 0.01)
- rho is per 1% rate change (annual rho * 0.01)

These scalings match vollib.black_scholes.greeks.analytical exactly
(see vollib source for rationale + Hull textbook references).

Implied volatility uses Brent's method (scipy.optimize.brentq) with a
Newton fallback, matching the robustness strategy in src/loats/options.py.

The module is intentionally pure-Python + numpy/scipy so that mypy
--strict passes without missing-import overrides and no compiled
extension (lets_be_rational) is required.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq, newton
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Helpers: d1 / d2 / pdf
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Standard normal CDF (alias for scipy)."""
    return float(norm.cdf(x))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF (matches vollib.helpers.pdf)."""
    return float(norm.pdf(x))


def d1(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Calculate d1 component of Black-Scholes PDE.

    Matches vollib.ref_python.black_scholes.d1 (Hull 7th ed, p.294).

    Args:
        S: spot, K: strike, t: years to expiry (>0), r: risk-free rate,
           sigma: volatility (>0).
    """
    if t <= 0 or sigma <= 0:
        # Guard against division by zero; callers validate t before invoking.
        # Return 0.0 as a safe sentinel -- price formulas handle expiry via
        # intrinsic fallback in OptionsEngine.
        return 0.0
    sigma_sq = sigma * sigma
    numerator = math.log(S / K) + (r + sigma_sq / 2.0) * t
    denominator = sigma * math.sqrt(t)
    return numerator / denominator


def d2(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Calculate d2 = d1 - sigma*sqrt(t)."""
    return d1(S, K, t, r, sigma) - sigma * math.sqrt(t)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def black_scholes(
    flag: str,
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
) -> float:
    """
    Black-Scholes option price (pure Python, no lets_be_rational).

    Args:
        flag: 'c' for call, 'p' for put.
        S: underlying price, K: strike, t: years to expiry,
           r: risk-free rate, sigma: volatility.

    Returns:
        Option price as float.

    Reference: Hull, Options, Futures and Other Derivatives, 7th ed.
    Matches vollib.black_scholes.black_scholes within <1e-10 for
    standard test vectors (external parity anchors live in
    tests/test_options.py::TestOptionsMathExternalParity).
    """
    if t <= 0:
        # At expiry: intrinsic value
        if flag == "c":
            return max(0.0, S - K)
        return max(0.0, K - S)

    D1 = d1(S, K, t, r, sigma)
    D2 = d2(S, K, t, r, sigma)
    disc = math.exp(-r * t)

    if flag == "c":
        return float(S * _norm_cdf(D1) - K * disc * _norm_cdf(D2))
    # put
    return float(-S * _norm_cdf(-D1) + K * disc * _norm_cdf(-D2))


# ---------------------------------------------------------------------------
# Greeks -- analytical, with vollib-compatible scaling
# ---------------------------------------------------------------------------


def delta(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Black-Scholes delta.

    Call: N(d1); Put: N(d1) - 1.
    Matches vollib.black_scholes.greeks.analytical.delta.
    """
    D1 = d1(S, K, t, r, sigma)
    if flag == "p":
        return float(_norm_cdf(D1) - 1.0)
    return float(_norm_cdf(D1))


def gamma(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Black-Scholes gamma (same for call and put).

    gamma = pdf(d1) / (S * sigma * sqrt(t)).
    Matches vollib.black_scholes.greeks.analytical.gamma.
    """
    D1 = d1(S, K, t, r, sigma)
    return float(_norm_pdf(D1) / (S * sigma * math.sqrt(t)))


def vega(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Black-Scholes vega per 1% vol change.

    Raw vega = S * pdf(d1) * sqrt(t); scaled *0.01 to match vollib.
    Matches vollib.black_scholes.greeks.analytical.vega.
    """
    D1 = d1(S, K, t, r, sigma)
    return float(S * _norm_pdf(D1) * math.sqrt(t) * 0.01)


def theta(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Black-Scholes theta per calendar day.

    Uses vollib's formula: (first_term +/- second_term) / 365.0.
    A negative value means time decay.

    Matches vollib.black_scholes.greeks.analytical.theta.
    """
    two_sqrt_t = 2.0 * math.sqrt(t)
    D1 = d1(S, K, t, r, sigma)
    D2 = d2(S, K, t, r, sigma)
    first_term = (-S * _norm_pdf(D1) * sigma) / two_sqrt_t

    disc = math.exp(-r * t)
    if flag == "c":
        second_term = r * K * disc * _norm_cdf(D2)
        return float((first_term - second_term) / 365.0)
    # put
    second_term = r * K * disc * _norm_cdf(-D2)
    return float((first_term + second_term) / 365.0)


def rho(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """
    Black-Scholes rho per 1% rate change.

    Scaled *0.01 to match vollib.
    Matches vollib.black_scholes.greeks.analytical.rho.
    """
    D2 = d2(S, K, t, r, sigma)
    disc = math.exp(-r * t)
    if flag == "c":
        return float(t * K * disc * _norm_cdf(D2) * 0.01)
    return float(-t * K * disc * _norm_cdf(-D2) * 0.01)


# ---------------------------------------------------------------------------
# Implied volatility -- Brent + Newton fallback
# ---------------------------------------------------------------------------


def implied_volatility(
    price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    flag: str,
    *,
    tolerance: float = 1e-5,
    max_iter: int = 100,
) -> float:
    """
    Implied volatility via Brent's method with Newton fallback.

    Mirrors the fallback strategy in OptionsEngine.calculate_implied_volatility
    and standalone helper, but as a pure function without external state.

    Args:
        price: market option price.
        S, K, t, r, flag: same as black_scholes.
        tolerance: brentq xtol.
        max_iter: Newton maxiter.

    Raises:
        ValueError: if t <= 0 (no implied vol at expiry), if flag is not
                    'c'/'p', or if price violates no-arbitrage bounds
                    (callers wanting a silent 0.2 fallback -- e.g.
                    OptionsEngine -- should check bounds before calling).
    """

    # Expiry has no implied volatility: the option prices at intrinsic.
    if t <= 0:
        raise ValueError(
            f"implied volatility is undefined for non-positive time to expiry (t={t})"
        )

    # No-arbitrage bounds (Hull 6.2, dividend-free): discounted-strike
    # bound K*e^{-rt} for calls, K*e^{-rt} upper bound for puts. Bounds
    # are validated BEFORE solving: a Brent bracket that cannot close
    # must not silently resolve to garbage (pre-fix this returned
    # sigma=-0.41 for a below-intrinsic price).
    discount = math.exp(-r * t)
    if flag == "c":
        lower, upper = max(0.0, S - K * discount), S
    elif flag == "p":
        lower, upper = max(0.0, K * discount - S), K * discount
    else:
        raise ValueError(f"invalid option flag: {flag!r} (expected 'c' or 'p')")

    if price <= lower or price >= upper:
        raise ValueError(
            f"price {price} violates arbitrage bounds [{lower}, {upper}]"
            f" (flag={flag!r}, S={S}, K={K}, t={t}, r={r})"
        )

    def _objective(sigma: float) -> float:
        return float(black_scholes(flag, S, K, t, r, sigma) - price)

    # Quick bracket check: use [1e-4, 5.0] (wider than vollib's [1e-4,10] but safe)
    low, high = 1e-4, 5.0
    try:
        if _objective(low) * _objective(high) < 0:
            return float(brentq(_objective, low, high, xtol=tolerance))
    except Exception:  # nosec B110
        pass

    # Newton fallback -- needs vega as derivative
    try:

        def _fprime(sigma: float) -> float:
            return float(S * _norm_pdf(d1(S, K, t, r, sigma)) * math.sqrt(t))

        return float(
            newton(
                _objective,
                x0=0.2,
                fprime=_fprime,
                maxiter=max_iter,
                tol=tolerance,
            )
        )
    except (RuntimeError, OverflowError) as exc:
        raise ValueError(
            f"implied volatility did not converge for price={price} "
            f"(S={S}, K={K}, t={t}, r={r}, flag={flag!r})"
        ) from exc


# ---------------------------------------------------------------------------
# Convenience: batch helpers that mirror vollib module layout for easy migration
# ---------------------------------------------------------------------------

# Re-export d1/d2 style helpers if needed by external callers that previously
# did `from vollib.ref_python.black_scholes import d1, d2`
__all__ = [
    "black_scholes",
    "d1",
    "d2",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "implied_volatility",
]
