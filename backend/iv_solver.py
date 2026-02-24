"""Implied volatility solver using Brent's method.

Falls back when chain IV is missing/NaN. Uses BSM pricing (with dividend yield q).
"""

from __future__ import annotations

from typing import Literal, Optional

from scipy.optimize import brentq

from greeks import bs_price

OptionType = Literal["call", "put"]


def implied_vol_from_price(
    *,
    market_price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    q: float,
    option_type: OptionType,
    vol_low: float = 1e-6,
    vol_high: float = 5.0,
) -> Optional[float]:
    """Return sigma (decimal) such that BSM price ~= market_price.

    Returns None if inputs invalid or no root is bracketed.
    """
    if market_price is None or market_price <= 0 or S <= 0 or K <= 0 or t <= 0:
        return None

    def f(sig: float) -> float:
        return bs_price(S, K, t, r, sig, option_type, q=q) - market_price

    try:
        f_low = f(vol_low)
        f_high = f(vol_high)
        if f_low == 0:
            return vol_low
        if f_high == 0:
            return vol_high
        if f_low * f_high > 0:
            return None
        return float(brentq(f, vol_low, vol_high, maxiter=200))
    except Exception:
        return None
