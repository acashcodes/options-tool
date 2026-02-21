"""Black-Scholes Greeks and option pricing.

Provides delta, gamma, theta, vega calculations for European options,
plus BS option pricing for pre-expiration payoff curves.
"""

from __future__ import annotations

import math
from typing import Optional

from scipy.stats import norm


# ---------------------------------------------------------------------------
# Core Black-Scholes helpers
# ---------------------------------------------------------------------------

def _d1(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Compute d1 in the Black-Scholes formula."""
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))


def _d2(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Compute d2 in the Black-Scholes formula."""
    return _d1(S, K, t, r, sigma) - sigma * math.sqrt(t)


# ---------------------------------------------------------------------------
# Option pricing
# ---------------------------------------------------------------------------

def bs_price(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> float:
    """Black-Scholes European option price.

    Args:
        S: Current stock price
        K: Strike price
        t: Time to expiration in years (must be > 0)
        r: Risk-free rate (annualised, e.g. 0.05 for 5%)
        sigma: Implied volatility (annualised, e.g. 0.30 for 30%)
        option_type: 'call' or 'put'

    Returns:
        Theoretical option price
    """
    if t <= 0:
        # At expiration, return intrinsic value
        if option_type == "call":
            return max(0.0, S - K)
        return max(0.0, K - S)

    d1 = _d1(S, K, t, r, sigma)
    d2 = d1 - sigma * math.sqrt(t)

    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * t) * norm.cdf(d2)
    else:
        return K * math.exp(-r * t) * norm.cdf(-d2) - S * norm.cdf(-d1)


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------

def delta(
    S: float, K: float, t: float, r: float, sigma: float, option_type: str = "call"
) -> float:
    """Option delta — rate of change of price w.r.t. underlying."""
    if t <= 0:
        if option_type == "call":
            return 1.0 if S > K else (0.5 if S == K else 0.0)
        return -1.0 if S < K else (-0.5 if S == K else 0.0)

    d1 = _d1(S, K, t, r, sigma)
    if option_type == "call":
        return norm.cdf(d1)
    return norm.cdf(d1) - 1.0


def gamma(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Option gamma — rate of change of delta w.r.t. underlying.
    Same for calls and puts.
    """
    if t <= 0:
        return 0.0
    d1 = _d1(S, K, t, r, sigma)
    return norm.pdf(d1) / (S * sigma * math.sqrt(t))


def theta(
    S: float, K: float, t: float, r: float, sigma: float, option_type: str = "call"
) -> float:
    """Option theta — daily time decay (in $/day per share, negative means losing value)."""
    if t <= 0:
        return 0.0

    d1 = _d1(S, K, t, r, sigma)
    d2 = d1 - sigma * math.sqrt(t)
    sqrt_t = math.sqrt(t)

    # Common term: -S * N'(d1) * sigma / (2 * sqrt(t))
    common = -S * norm.pdf(d1) * sigma / (2 * sqrt_t)

    if option_type == "call":
        annual = common - r * K * math.exp(-r * t) * norm.cdf(d2)
    else:
        annual = common + r * K * math.exp(-r * t) * norm.cdf(-d2)

    return annual / 365.0  # per calendar day


def vega(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Option vega — price change per 1% change in IV.
    Same for calls and puts. Returns $ per 1% IV move per share.
    """
    if t <= 0:
        return 0.0
    d1 = _d1(S, K, t, r, sigma)
    return S * norm.pdf(d1) * math.sqrt(t) / 100.0


def rho(
    S: float, K: float, t: float, r: float, sigma: float, option_type: str = "call"
) -> float:
    """Option rho — price change per 1% change in interest rate."""
    if t <= 0:
        return 0.0
    d2 = _d2(S, K, t, r, sigma)
    if option_type == "call":
        return K * t * math.exp(-r * t) * norm.cdf(d2) / 100.0
    return -K * t * math.exp(-r * t) * norm.cdf(-d2) / 100.0


# ---------------------------------------------------------------------------
# Convenience: compute all Greeks at once
# ---------------------------------------------------------------------------

def compute_greeks(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict[str, Optional[float]]:
    """Compute all Greeks for a single option.

    Args:
        S: Current stock price
        K: Strike price
        t: Time to expiration in years
        r: Risk-free rate (annualised decimal, e.g. 0.05)
        sigma: Implied volatility (annualised decimal, e.g. 0.30)
        option_type: 'call' or 'put'

    Returns:
        Dict with keys: delta, gamma, theta, vega, rho, price
    """
    if sigma is None or sigma <= 0 or S <= 0 or K <= 0:
        return {
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
            "price": None,
        }

    ot = option_type.lower()

    return {
        "delta": round(delta(S, K, t, r, sigma, ot), 4),
        "gamma": round(gamma(S, K, t, r, sigma), 4),
        "theta": round(theta(S, K, t, r, sigma, ot), 4),
        "vega": round(vega(S, K, t, r, sigma), 4),
        "rho": round(rho(S, K, t, r, sigma, ot), 4),
        "price": round(bs_price(S, K, t, r, sigma, ot), 4),
    }


# ---------------------------------------------------------------------------
# Probability of profit
# ---------------------------------------------------------------------------

def prob_above(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Probability stock price will be above K at time t (log-normal model).
    Uses N(d2) from Black-Scholes.
    """
    if t <= 0:
        return 1.0 if S > K else 0.0
    if sigma <= 0:
        return 1.0 if S * math.exp(r * t) > K else 0.0
    d2 = _d2(S, K, t, r, sigma)
    return float(norm.cdf(d2))


def prob_below(S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Probability stock price will be below K at time t."""
    return 1.0 - prob_above(S, K, t, r, sigma)


def prob_itm(
    S: float, K: float, t: float, r: float, sigma: float, option_type: str = "call"
) -> float:
    """Probability option finishes in the money."""
    if option_type.lower() == "call":
        return prob_above(S, K, t, r, sigma)
    return prob_below(S, K, t, r, sigma)
